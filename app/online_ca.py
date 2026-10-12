"""Theo dõi Online trong ngày: mục nằm dưới bảng của trang Báo cáo ngày (chốt 12/10/2026, bật cùng phòng với Báo cáo ngày).

Quy tắc đã chốt với chủ app:
- Mỗi mã hợp đồng là MỘT phiếu (ca) riêng, gắn nhân viên + khung giờ dự kiến + trạng thái. Sale PHẢI khai khung giờ dự kiến đầu
  ngày; ai chưa khai (và chưa bấm "không có ca") thì hiện cảnh báo, KHÔNG chặn các phần khác của trang.
- Trạng thái: Dự kiến → Đang triển khai → Đã online. Sale tự cập nhật, KHÔNG lấy từ file Internet (cùng cách với ô "Đã online").
  Dời khung giờ hay dời sang ngày mai thì ghi vào lịch sử của phiếu. Không lưu tên khách hàng.
- NỐI với bảng Báo cáo ngày: mỗi lần phiếu của một nhân viên đổi thì app TÍNH LẠI và ghi vào ba ô của người đó: ONL sáng (phiếu
  ở khung buổi sáng), ONL chiều (phiếu buổi chiều + sau 17h30), Đã online (phiếu đã online). Ca "Chưa hẹn giờ" chưa tính vào ô nào
  cho tới khi chọn khung. Ô trong bảng vẫn gõ tay được; lần sau phiếu đổi thì số tính từ phiếu ghi đè (sale hai nơi thì nhìn một số).
- Phiếu giữ lại sau ngày (khác báo cáo đầu ngày bị xoá), để sau này xem lại tỷ lệ ca lên đúng giờ.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import delete, select, text

from app import bao_cao_ngay as bc
from app.bo_nho import nho
from app.config import rules_config
from app.db import engine, session_scope
from app.models import OnlineCa, OnlineKhongCa
from app.thoi_gian import gio_viet_nam, utc_bay_gio

TRANG_THAI = ("du_kien", "dang_lam", "da_online")
NHAN_TT = {"du_kien": "Dự kiến", "dang_lam": "Đang triển khai", "da_online": "Đã online"}
GHI_CHU_TOI_DA = 300
LS_TOI_DA = 30                                  # số dòng lịch sử giữ lại cho mỗi phiếu
MA_HD = re.compile(r"^[A-Z0-9]{5,20}$")
_da_tao = False

KHUNG_MAC_DINH = [
    {"ma": "08-10", "nhan": "08h–10h", "buoi": "sang", "tu": "08:00", "den": "10:00"},
    {"ma": "10-12", "nhan": "10h–12h", "buoi": "sang", "tu": "10:00", "den": "12:00"},
    {"ma": "1330-1530", "nhan": "13h30–15h30", "buoi": "chieu", "tu": "13:30", "den": "15:30"},
    {"ma": "1530-1730", "nhan": "15h30–17h30", "buoi": "chieu", "tu": "15:30", "den": "17:30"},
    {"ma": "sau", "nhan": "Sau 17h30", "buoi": "chieu", "tu": "17:30", "den": "23:59"},
    {"ma": "chua", "nhan": "Chưa hẹn giờ", "buoi": "", "tu": "", "den": ""},
]


class LoiOnline(ValueError):
    """Lỗi hiện thẳng cho người dùng (đã viết bằng tiếng Việt)."""


def dam_bao_bang() -> None:
    global _da_tao
    if not _da_tao:
        OnlineCa.__table__.create(engine, checkfirst=True)
        OnlineKhongCa.__table__.create(engine, checkfirst=True)
        _da_tao = True


def khung() -> list[dict]:
    """Các khung giờ trong ngày, đặt ở config/rules.yml → bao_cao_ngay.khung_online (không có thì dùng mặc định)."""
    ds = (rules_config().get("bao_cao_ngay") or {}).get("khung_online") or KHUNG_MAC_DINH
    return [{"ma": str(k["ma"]), "nhan": str(k["nhan"]), "buoi": str(k.get("buoi") or ""),
             "tu": str(k.get("tu") or ""), "den": str(k.get("den") or "")} for k in ds]


def _khung_hop_le(ma: str) -> str:
    if ma not in {k["ma"] for k in khung()}:
        raise LoiOnline("Chọn khung giờ trong danh sách.")
    return ma


def chuan_ma(v) -> str:
    ma = re.sub(r"[\s\-_.]", "", str(v or "")).upper()
    if not MA_HD.match(ma):
        raise LoiOnline("Mã hợp đồng gồm chữ và số, VD: DAAAP6381.")
    return ma


# ------------------------------------------------------------------ đọc
@nho("so_lieu")
def nhan_vien(phong: tuple, ngay_iso: str) -> list[dict]:
    """Nhân sự đang làm của phòng (cùng danh sách bảng Báo cáo ngày): [{a: acc_norm, t: họ tên}]."""
    ngay = date.fromisoformat(ngay_iso)
    dau = date(ngay.year, ngay.month, 1)
    staff = bc._nhan_su_dang_lam(list(phong), dau, ngay)
    if staff.empty:
        return []
    ten = pd.read_sql_query(text("SELECT acc_norm, ho_ten FROM dim_employee WHERE acc_norm IS NOT NULL"), engine)
    ten = ten.drop_duplicates("acc_norm").set_index("acc_norm").ho_ten
    tam = staff.set_index("acc_norm").ten_hien_thi.replace("", None)
    tam = tam[~tam.index.duplicated()]
    out = [{"a": a, "t": str(ten.get(a) or tam.get(a) or a)} for a in dict.fromkeys(staff.acc_norm)]
    return sorted(out, key=lambda x: x["t"].split()[-1] if x["t"].split() else x["t"])


def _ls(r) -> list[dict]:
    try:
        return json.loads(r.lich_su or "[]")
    except ValueError:
        return []


def _dict(r: OnlineCa) -> dict:
    return {"id": r.id, "ma": r.ma_hd, "acc": r.acc_norm, "khung": r.khung, "tt": r.trang_thai, "gc": r.ghi_chu or "",
            "ls": _ls(r), "ai": r.cap_nhat_boi or r.tao_boi or ""}


def ds_ca(phong: list[str], ngay: date) -> list[dict]:
    dam_bao_bang()
    thu_tu = {k["ma"]: i for i, k in enumerate(khung())}
    with session_scope() as s:
        rows = s.execute(select(OnlineCa).where(OnlineCa.ngay == ngay, OnlineCa.phong_code.in_(phong))).scalars().all()
        ca = [_dict(r) for r in rows]
    return sorted(ca, key=lambda c: (thu_tu.get(c["khung"], 99), c["id"]))


def ds_khong_ca(phong: list[str], ngay: date) -> list[str]:
    dam_bao_bang()
    with session_scope() as s:
        return list(s.execute(select(OnlineKhongCa.acc_norm).where(OnlineKhongCa.ngay == ngay,
                                                                  OnlineKhongCa.phong_code.in_(phong))).scalars())


def moc(phong: list[str], ngay: date) -> str:
    """Dấu vết lần sửa gần nhất của cả phòng, để trang tự nạp lại khi người khác vừa cập nhật."""
    dam_bao_bang()
    ma = {f"p{i}": c for i, c in enumerate(phong)}
    cho = ", ".join(f":{k}" for k in ma)
    with engine.connect() as c:
        a = c.execute(text(f"SELECT COUNT(*), MAX(cap_nhat_luc) FROM online_ca WHERE ngay = :n AND phong_code IN ({cho})"),
                      {**ma, "n": ngay.isoformat()}).one()
        b = c.execute(text(f"SELECT COUNT(*), MAX(cap_nhat_luc) FROM online_khong_ca WHERE ngay = :n AND phong_code IN ({cho})"),
                      {**ma, "n": ngay.isoformat()}).one()
    return f"{a[0]}|{a[1] or ''}|{b[0]}|{b[1] or ''}"


def thong_ke(ca: list[dict]) -> dict:
    """Số ca theo khung giờ và theo nhân viên: {tong, cho, dang, online, khung: {ma: {...}}, nv: {acc: {...}}, chua_hen}.
    `cho` = Dự kiến, `dang` = Đang triển khai. assets/online.js có bản tính y hệt để cập nhật tức thì (có test đối chiếu)."""
    def so(ds):
        return {"tong": len(ds), "cho": sum(c["tt"] == "du_kien" for c in ds), "dang": sum(c["tt"] == "dang_lam" for c in ds),
                "online": sum(c["tt"] == "da_online" for c in ds)}
    out = so(ca)
    out["khung"] = {k["ma"]: so([c for c in ca if c["khung"] == k["ma"]]) for k in khung()}
    out["nv"] = {a: so([c for c in ca if c["acc"] == a]) for a in dict.fromkeys(c["acc"] for c in ca)}
    out["chua_hen"] = sum(c["khung"] == "chua" for c in ca)
    return out


def chua_khai(ca: list[dict], nv: list[dict], khong_ca: list[str]) -> list[str]:
    """Nhân viên chưa khai ca nào và chưa báo "không có ca" (acc_norm)."""
    co = {c["acc"] for c in ca} | set(khong_ca)
    return [x["a"] for x in nv if x["a"] not in co]


def du_lieu(phong: list[str], ngay: date) -> dict:
    """Gói dữ liệu duy nhất gửi trình duyệt vẽ mục Theo dõi Online (assets/online.js)."""
    nv = nhan_vien(tuple(phong), ngay.isoformat())
    ca, kc = ds_ca(phong, ngay), ds_khong_ca(phong, ngay)
    return {"ngay": ngay.isoformat(), "hom_nay": bc.hom_nay().isoformat(), "khung": khung(), "nv": nv, "ca": ca, "khong_ca": kc,
            "chua_khai": chua_khai(ca, nv, kc), "moc": moc(phong, ngay)}


# ------------------------------------------------------------------ ghi
def _ghi_ls(r: OnlineCa, ai: str, viec: str) -> None:
    ls = _ls(r)
    ls.append({"luc": gio_viet_nam().isoformat(timespec="minutes"), "ai": ai, "viec": viec})
    r.lich_su = json.dumps(ls[-LS_TOI_DA:], ensure_ascii=False)


def _dau(r: OnlineCa, ai: str) -> None:
    r.cap_nhat_luc, r.cap_nhat_boi = utc_bay_gio(), ai[:60]


def dong_bo_bang(ngay: date, phong: list[str], accs, ai: str) -> None:
    """Tính lại ONL sáng / ONL chiều / Đã online của các nhân viên từ phiếu rồi ghi vào bảng Báo cáo ngày."""
    buoi = {k["ma"]: k["buoi"] for k in khung()}
    ca = ds_ca(phong, ngay)
    for a in dict.fromkeys(a for a in accs if a):
        cua = [c for c in ca if c["acc"] == a]
        bc.luu(a, {"onl_sang": sum(buoi.get(c["khung"]) == "sang" for c in cua),
                   "onl_chieu": sum(buoi.get(c["khung"]) == "chieu" for c in cua),
                   "da_online": sum(c["tt"] == "da_online" for c in cua)}, phong, ai, ngay, ghi_ten=ai)


def _tim(s, id_: int, phong: list[str]) -> OnlineCa:
    r = s.get(OnlineCa, int(id_))
    if r is None or r.phong_code not in set(phong):
        raise LoiOnline("Không tìm thấy ca này (có thể người khác vừa xoá).")
    return r


def them(ma_hd, acc_norm: str, khung_ma: str, phong: list[str], ai: str, ngay: date, ghi_chu: str = "") -> int:
    dam_bao_bang()
    ma = chuan_ma(ma_hd)
    if not acc_norm or acc_norm not in {x["a"] for x in nhan_vien(tuple(phong), ngay.isoformat())}:
        raise LoiOnline("Chọn nhân viên phụ trách ca này.")
    _khung_hop_le(khung_ma)
    with session_scope() as s:
        da = s.execute(select(OnlineCa).where(OnlineCa.ngay == ngay, OnlineCa.phong_code == phong[0],
                                              OnlineCa.ma_hd == ma)).scalars().first()
        if da is not None:
            raise LoiOnline(f"HĐ {ma} đã có trong ngày {ngay:%d/%m} rồi.")
        r = OnlineCa(ngay=ngay, phong_code=phong[0], ma_hd=ma, acc_norm=acc_norm, khung=khung_ma, trang_thai="du_kien",
                     ghi_chu=(ghi_chu or "").strip()[:GHI_CHU_TOI_DA] or None, tao_luc=utc_bay_gio(), tao_boi=ai[:60])
        _ghi_ls(r, ai, f"Tạo ca, khung {_nhan_khung(khung_ma)}")
        _dau(r, ai)
        s.add(r)
        s.flush()
        id_ = r.id
    dong_bo_bang(ngay, phong, [acc_norm], ai)
    return id_


def _nhan_khung(ma: str) -> str:
    return next((k["nhan"] for k in khung() if k["ma"] == ma), ma)


def doi_trang_thai(id_: int, tt: str, phong: list[str], ai: str) -> None:
    if tt not in TRANG_THAI:
        raise LoiOnline("Trạng thái không hợp lệ.")
    dam_bao_bang()
    with session_scope() as s:
        r = _tim(s, id_, phong)
        if r.trang_thai == tt:
            return
        _ghi_ls(r, ai, f"{NHAN_TT[r.trang_thai]} → {NHAN_TT[tt]}")
        r.trang_thai = tt
        _dau(r, ai)
        ngay, acc = r.ngay, r.acc_norm
    dong_bo_bang(ngay, phong, [acc], ai)


def doi_khung(id_: int, khung_ma: str, phong: list[str], ai: str) -> None:
    _khung_hop_le(khung_ma)
    dam_bao_bang()
    with session_scope() as s:
        r = _tim(s, id_, phong)
        if r.khung == khung_ma:
            return
        _ghi_ls(r, ai, f"Dời khung {_nhan_khung(r.khung)} → {_nhan_khung(khung_ma)}")
        r.khung = khung_ma
        _dau(r, ai)
        ngay, acc = r.ngay, r.acc_norm
    dong_bo_bang(ngay, phong, [acc], ai)


def doi_ngay_mai(id_: int, phong: list[str], ai: str) -> date:
    """Dời ca sang ngày kế tiếp, về trạng thái Dự kiến và "Chưa hẹn giờ" để sáng mai sale chọn khung."""
    dam_bao_bang()
    with session_scope() as s:
        r = _tim(s, id_, phong)
        moi = r.ngay + timedelta(days=1)
        if moi > bc.ngay_xa_nhat():
            raise LoiOnline("Chỉ dời được tới ngày xa nhất mà Báo cáo ngày cho nhập trước.")
        if s.execute(select(OnlineCa.id).where(OnlineCa.ngay == moi, OnlineCa.phong_code == r.phong_code,
                                               OnlineCa.ma_hd == r.ma_hd)).first():
            raise LoiOnline(f"HĐ {r.ma_hd} đã có trong ngày {moi:%d/%m} rồi.")
        cu, acc = r.ngay, r.acc_norm
        _ghi_ls(r, ai, f"Dời sang ngày {moi:%d/%m}")
        r.ngay, r.khung, r.trang_thai = moi, "chua", "du_kien"
        _dau(r, ai)
    dong_bo_bang(cu, phong, [acc], ai)
    dong_bo_bang(moi, phong, [acc], ai)
    return moi


def sua(id_: int, acc_norm: str, ghi_chu: str, phong: list[str], ai: str) -> None:
    """Đổi người phụ trách và ghi chú của ca."""
    dam_bao_bang()
    with session_scope() as s:
        r = _tim(s, id_, phong)
        if acc_norm not in {x["a"] for x in nhan_vien(tuple(phong), r.ngay.isoformat())}:
            raise LoiOnline("Chọn nhân viên phụ trách ca này.")
        cu = r.acc_norm
        if acc_norm != cu:
            _ghi_ls(r, ai, "Đổi người phụ trách")
        r.acc_norm, r.ghi_chu = acc_norm, (ghi_chu or "").strip()[:GHI_CHU_TOI_DA] or None
        _dau(r, ai)
        ngay = r.ngay
    dong_bo_bang(ngay, phong, [cu, acc_norm], ai)


def xoa(id_: int, phong: list[str], ai: str) -> dict:
    """Xoá ca (huỷ). Trả {ma_hd, ngay} để trang ghi nhật ký."""
    dam_bao_bang()
    with session_scope() as s:
        r = _tim(s, id_, phong)
        thong_tin = {"ma_hd": r.ma_hd, "ngay": r.ngay}
        acc = r.acc_norm
        s.execute(delete(OnlineCa).where(OnlineCa.id == r.id))
    dong_bo_bang(thong_tin["ngay"], phong, [acc], ai)
    return thong_tin


def khong_ca(acc_norm: str, phong: list[str], ngay: date, co: bool, ai: str) -> None:
    """Nhân viên báo hôm nay không có ca online (co=True) hoặc bỏ báo (co=False)."""
    dam_bao_bang()
    if acc_norm not in {x["a"] for x in nhan_vien(tuple(phong), ngay.isoformat())}:
        raise LoiOnline("Không có nhân viên này trong phòng.")
    with session_scope() as s:
        r = s.execute(select(OnlineKhongCa).where(OnlineKhongCa.ngay == ngay,
                                                  OnlineKhongCa.acc_norm == acc_norm)).scalars().first()
        if co and r is None:
            s.add(OnlineKhongCa(ngay=ngay, phong_code=phong[0], acc_norm=acc_norm, cap_nhat_luc=utc_bay_gio(), cap_nhat_boi=ai[:60]))
        elif not co and r is not None:
            s.delete(r)
