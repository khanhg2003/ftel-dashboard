"""Theo dõi Online trong ngày: mục nằm dưới bảng của trang Báo cáo ngày (chốt 12/10/2026, bật cùng phòng với Báo cáo ngày).

Quy tắc đã chốt với chủ app:
- Mỗi mã hợp đồng là MỘT phiếu (ca) riêng, gắn nhân viên + khung giờ dự kiến + trạng thái. Sale PHẢI khai khung giờ cho số ca
  đã nhập ở ô ONL sáng / ONL chiều của bảng: chỉ người có dự kiến online MÀ chưa khai đủ giờ mới bị cảnh báo (người dự kiến 0 ẩn hẳn,
  chủ app chốt 12/10/2026), KHÔNG chặn các phần khác của trang. Ca "Chưa hẹn giờ" cũng tính là chưa khai giờ.
- Trạng thái: Dự kiến → Đang triển khai → Đã online. Sale tự cập nhật, KHÔNG lấy từ file Internet (cùng cách với ô "Đã online").
  Dời khung giờ hay dời sang ngày mai thì ghi vào lịch sử của phiếu. Không lưu tên khách hàng.
- NỐI với bảng Báo cáo ngày: mỗi lần phiếu của một nhân viên đổi thì app TÍNH LẠI và ghi vào ba ô của người đó: ONL sáng (phiếu
  ở khung buổi sáng), ONL chiều (phiếu buổi chiều + sau 17h30), Đã online (phiếu đã online). "Đã online" luôn ghi đúng số phiếu. ONL
  sáng / chiều chỉ ghi khi số phiếu ĐỦ so với số sale đã gõ (không thì số gõ bị ghi đè nhỏ hơn và mất cảnh báo thiếu); riêng huỷ ca,
  dời sang ngày mai là việc chủ ý bớt ca nên luôn ghi đúng số phiếu. Ca "Chưa hẹn giờ" chưa tính vào ô nào.
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
from app.models import OnlineCa
from app.thoi_gian import gio_viet_nam, utc_bay_gio

TRANG_THAI = ("du_kien", "dang_lam", "da_online")        # sale tự đặt; "doi_mai" là trạng thái app đặt khi dời sang ngày kế
COT_THEM = {"khung_dau": "VARCHAR(16)", "online_luc": "TIMESTAMP"}
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
    {"ma": "sau", "nhan": "Sau 17h30", "buoi": "chieu", "tu": "17:30", "den": "23:59", "phu": True},
    {"ma": "chua", "nhan": "Chưa hẹn giờ", "buoi": "", "tu": "", "den": "", "phu": True},
]


class LoiOnline(ValueError):
    """Lỗi hiện thẳng cho người dùng (đã viết bằng tiếng Việt)."""


def dam_bao_bang() -> None:
    global _da_tao
    if not _da_tao:
        OnlineCa.__table__.create(engine, checkfirst=True)
        from sqlalchemy import inspect
        co = {c["name"] for c in inspect(engine).get_columns("online_ca")}
        for ten, kieu in COT_THEM.items():
            if ten not in co:
                with engine.begin() as c:
                    c.execute(text(f"ALTER TABLE online_ca ADD COLUMN {ten} {kieu}"))
        _da_tao = True


def khung() -> list[dict]:
    """Các khung giờ trong ngày, đặt ở config/rules.yml → bao_cao_ngay.khung_online (không có thì dùng mặc định)."""
    ds = (rules_config().get("bao_cao_ngay") or {}).get("khung_online") or KHUNG_MAC_DINH
    return [{"ma": str(k["ma"]), "nhan": str(k["nhan"]), "buoi": str(k.get("buoi") or ""),
             "tu": str(k.get("tu") or ""), "den": str(k.get("den") or ""), "phu": bool(k.get("phu"))} for k in ds]


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
    ls = _ls(r)
    return {"id": r.id, "ma": r.ma_hd, "acc": r.acc_norm, "khung": r.khung, "tt": r.trang_thai, "gc": r.ghi_chu or "",
            "ls": ls, "ai": r.cap_nhat_boi or r.tao_boi or "", "doi": sum(x.get("viec", "").startswith("Dời") for x in ls)}


def ds_ca(phong: list[str], ngay: date) -> list[dict]:
    dam_bao_bang()
    thu_tu = {k["ma"]: i for i, k in enumerate(khung())}
    with session_scope() as s:
        rows = s.execute(select(OnlineCa).where(OnlineCa.ngay == ngay, OnlineCa.phong_code.in_(phong),
                                                OnlineCa.trang_thai != "doi_mai")).scalars().all()       # ca đã dời sang mai không còn trên bảng
        ca = [_dict(r) for r in rows]
    return sorted(ca, key=lambda c: (thu_tu.get(c["khung"], 99), c["id"]))


def dk_nhap(phong: list[str], ngay: date) -> dict[str, int]:
    """Số dự kiến online (ONL sáng + ONL chiều) mỗi người đã gõ ở bảng Báo cáo ngày: {acc_norm: số}."""
    bc.dam_bao_bang()
    ma = {f"p{i}": c for i, c in enumerate(phong)}
    cho = ", ".join(f":{k}" for k in ma)
    with engine.connect() as c:
        rows = c.execute(text(f"""SELECT acc_norm, COALESCE(onl_sang, 0) + COALESCE(onl_chieu, 0) FROM bao_cao_ngay
                                  WHERE ngay = :n AND phong_code IN ({cho})"""), {**ma, "n": ngay.isoformat()}).all()
    return {a: int(n) for a, n in rows if n}


def moc(phong: list[str], ngay: date) -> str:
    """Dấu vết lần sửa gần nhất của phiếu và của bảng Báo cáo ngày, để trang tự nạp lại khi người khác vừa cập nhật."""
    dam_bao_bang()
    ma = {f"p{i}": c for i, c in enumerate(phong)}
    cho = ", ".join(f":{k}" for k in ma)
    with engine.connect() as c:
        a = c.execute(text(f"SELECT COUNT(*), MAX(cap_nhat_luc) FROM online_ca WHERE ngay = :n AND phong_code IN ({cho})"),
                      {**ma, "n": ngay.isoformat()}).one()
    return f"{a[0]}|{a[1] or ''}|{bc.moc_cap_nhat(phong, ngay)}"


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


def thieu_gio(ca: list[dict], dk: dict, hen: dict | None = None) -> dict:
    """Những người CÓ ca (đã gõ dự kiến online hoặc đã có phiếu): {acc: {can, khai, chua, thieu}}.
    can = số ca người đó cần khai = lớn hơn giữa số dự kiến đã gõ và số phiếu; khai = phiếu đã có khung giờ; chua = phiếu "Chưa hẹn giờ";
    thieu = can - khai (số ca còn phải khai giờ). `hen` = {acc: số ca hẹn thi công đúng ngày theo Nhập tồn mà chưa có ca}: những ca đó cũng là ca người
    đó phải khai giờ nên cộng vào `can`. Người dự kiến 0, chưa có phiếu và không có ca hẹn thì không có mặt ở đây (ẩn hẳn khỏi mục theo dõi).
    assets/online.js có bản tính y hệt để cập nhật tức thì (có test đối chiếu)."""
    out = {}
    hen = hen or {}
    for a in dict.fromkeys([*dk, *hen, *(c["acc"] for c in ca)]):
        khai = sum(c["acc"] == a and c["khung"] != "chua" for c in ca)
        chua = sum(c["acc"] == a and c["khung"] == "chua" for c in ca)
        can = max(int(dk.get(a, 0) or 0), khai + chua + int(hen.get(a, 0) or 0))
        if can > 0:
            out[a] = {"can": can, "khai": khai, "chua": chua, "thieu": can - khai}
    return out


def du_lieu(phong: list[str], ngay: date) -> dict:
    """Gói dữ liệu duy nhất gửi trình duyệt vẽ mục Theo dõi Online (assets/online.js)."""
    nv = nhan_vien(tuple(phong), ngay.isoformat())
    from app import online_ton as ot
    ca, dk = ds_ca(phong, ngay), dk_nhap(phong, ngay)
    hen = ot.hen_cho_ngay(phong, ngay)
    return {"ngay": ngay.isoformat(), "hom_nay": bc.hom_nay().isoformat(), "khung": khung(), "nv": nv, "ca": ca, "dk": dk, "hen": hen,
            "lech": ot.lech_ngay(ca, ngay, phong), "thieu": thieu_gio(ca, dk, {a: len(v) for a, v in hen.items()}),
            "ton": ton_tat_ca(phong, ngay), "xa_nhat": bc.ngay_xa_nhat().isoformat(), "moc": moc(phong, ngay)}


# ------------------------------------------------------------------ ghi
def _ghi_ls(r: OnlineCa, ai: str, viec: str) -> None:
    ls = _ls(r)
    ls.append({"luc": gio_viet_nam().isoformat(timespec="minutes"), "ai": ai, "viec": viec})
    r.lich_su = json.dumps(ls[-LS_TOI_DA:], ensure_ascii=False)


def _dau(r: OnlineCa, ai: str) -> None:
    r.cap_nhat_luc, r.cap_nhat_boi = utc_bay_gio(), ai[:60]


def dong_bo_bang(ngay: date, phong: list[str], accs, ai: str, ep: bool = False) -> None:
    """Tính lại ONL sáng / ONL chiều / Đã online của các nhân viên từ phiếu rồi ghi vào bảng Báo cáo ngày.

    Số phiếu còn ÍT hơn số sale đã gõ ở ô dự kiến (chưa khai đủ) thì KHÔNG ghi đè ONL sáng / chiều, nếu không số gõ bị thay bằng số nhỏ
    hơn và cảnh báo thiếu biến mất. `ep=True` (huỷ ca, dời sang ngày khác) là chủ ý bớt ca nên luôn ghi đúng số phiếu."""
    buoi = {k["ma"]: k["buoi"] for k in khung()}
    ca, dk = ds_ca(phong, ngay), dk_nhap(phong, ngay)
    for a in dict.fromkeys(a for a in accs if a):
        cua = [c for c in ca if c["acc"] == a]
        so = {"da_online": sum(c["tt"] == "da_online" for c in cua)}
        if ep or len(cua) >= dk.get(a, 0):
            so["onl_sang"] = sum(buoi.get(c["khung"]) == "sang" for c in cua)
            so["onl_chieu"] = sum(buoi.get(c["khung"]) == "chieu" for c in cua)
        bc.luu(a, so, phong, ai, ngay, ghi_ten=ai, kiem_ca=False)


def _tim(s, id_: int, phong: list[str]) -> OnlineCa:
    r = s.get(OnlineCa, int(id_))
    if r is None or r.phong_code not in set(phong):
        raise LoiOnline("Không tìm thấy ca này (có thể người khác vừa xoá).")
    return r


def tach_ma(chu) -> tuple[list[str], list[str]]:
    """Tách nhiều mã hợp đồng dán một lần (cách nhau dấu cách, phẩy, chấm phẩy, xuống dòng): (mã hợp lệ không trùng, chữ sai)."""
    dung, sai = [], []
    for t in re.split(r"[\s,;]+", str(chu or "")):
        if not t:
            continue
        try:
            ma = chuan_ma(t)
        except LoiOnline:
            sai.append(t[:20])
            continue
        if ma not in dung:
            dung.append(ma)
    return dung, sai


def them_nhieu(chu, acc_norm: str, khung_ma: str, phong: list[str], ai: str, ngay: date, ghi_chu: str = "", xac_nhan: bool = False) -> dict:
    """Thêm một hoặc nhiều ca cùng nhân viên + khung giờ. Trả {"them": [mã], "bo_qua": [(mã hoặc chữ, lý do)], "hoi": [{ma, loai, ngay}]}.
    Mã đã có trong ngày thì bỏ qua và báo lại, các mã còn lại vẫn thêm. Mã mà Nhập tồn đang hẹn / trả về NGÀY KHÁC thì KHÔNG thêm mà đưa vào "hoi"
    để trang hỏi sale xác nhận; xác nhận rồi (`xac_nhan=True`) thì thêm và ngày hẹn ở Nhập tồn tự đổi theo (`online_ton`)."""
    dam_bao_bang()
    ma_ds, sai = tach_ma(chu)
    if not ma_ds:
        raise LoiOnline("Mã hợp đồng gồm chữ và số, VD: DAAAP6381." if not sai else f"Mã không hợp lệ: {', '.join(sai)}.")
    if not acc_norm or acc_norm not in {x["a"] for x in nhan_vien(tuple(phong), ngay.isoformat())}:
        raise LoiOnline("Chọn nhân viên phụ trách ca này.")
    _khung_hop_le(khung_ma)
    from app import online_ton as ot
    xd = {x["ma"]: x for x in ot.xung_dot(ma_ds, ngay, phong)}
    ket = {"them": [], "bo_qua": [(t, "mã không hợp lệ") for t in sai], "hoi": []}
    with session_scope() as s:
        da = {r.ma_hd: r.trang_thai for r in s.execute(select(OnlineCa).where(OnlineCa.ngay == ngay, OnlineCa.phong_code == phong[0])).scalars()}
        for ma in ma_ds:
            if ma in da:
                ket["bo_qua"].append((ma, "đã dời sang ngày mai" if da[ma] == "doi_mai" else "đã có trong ngày"))
                continue
            if ma in xd and not xac_nhan:
                ket["hoi"].append(xd[ma])
                continue
            r = OnlineCa(ngay=ngay, phong_code=phong[0], ma_hd=ma, acc_norm=acc_norm, khung=khung_ma, khung_dau=khung_ma,
                         trang_thai="du_kien", ghi_chu=(ghi_chu or "").strip()[:GHI_CHU_TOI_DA] or None, tao_luc=utc_bay_gio(), tao_boi=ai[:60])
            _ghi_ls(r, ai, f"Tạo ca, khung {_nhan_khung(khung_ma)}")
            _dau(r, ai)
            s.add(r)
            ket["them"].append(ma)
    if not ket["them"] and not ket["hoi"]:
        raise LoiOnline("; ".join(f"{m}: {ly}" for m, ly in ket["bo_qua"]) + ".")
    if ket["them"]:
        dong_bo_bang(ngay, phong, [acc_norm], ai)
        ot.dong_bo_hen(ket["them"], ngay, phong, ai)
    return ket


def them(ma_hd, acc_norm: str, khung_ma: str, phong: list[str], ai: str, ngay: date, ghi_chu: str = "") -> int:
    """Thêm đúng một ca (mã sai hoặc đã có thì báo lỗi). Trả id của ca."""
    ma = chuan_ma(ma_hd)
    ket = them_nhieu(ma, acc_norm, khung_ma, phong, ai, ngay, ghi_chu, xac_nhan=True)
    with session_scope() as s:
        return s.execute(select(OnlineCa.id).where(OnlineCa.ngay == ngay, OnlineCa.phong_code == phong[0], OnlineCa.ma_hd == ket["them"][0])).scalar()


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
        r.online_luc = utc_bay_gio() if tt == "da_online" else None
        _dau(r, ai)
        ngay, acc, ma = r.ngay, r.acc_norm, r.ma_hd
    dong_bo_bang(ngay, phong, [acc], ai)
    from app import online_ton as ot
    ot.dong_bo_tt(ma, tt, phong, ai)


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


def doi_ngay(id_: int, phong: list[str], ai: str, ngay_moi=None) -> date:
    """Dời ca sang một ngày SAU (mặc định ngày kế tiếp; `ngay_moi` là date hoặc chuỗi YYYY-MM-DD), tối đa tới ngày xa nhất Báo cáo ngày cho nhập
    trước (`bc.ngay_xa_nhat`). Ca cũ giữ lại ở ngày của nó với trạng thái "doi_mai" (không hiện trên bảng, nhưng tính là ca không lên đúng
    hẹn khi thống kê); ca mới ở ngày đích về Dự kiến + "Chưa hẹn giờ" để hôm đó sale chọn khung."""
    dam_bao_bang()
    if isinstance(ngay_moi, str):
        try:
            ngay_moi = date.fromisoformat(ngay_moi[:10])
        except ValueError:
            raise LoiOnline("Ngày không hợp lệ.") from None
    with session_scope() as s:
        r = _tim(s, id_, phong)
        moi = ngay_moi or r.ngay + timedelta(days=1)
        if moi <= r.ngay:
            raise LoiOnline("Chọn một ngày sau ngày hiện tại của ca.")
        if moi > bc.ngay_xa_nhat():
            raise LoiOnline(f"Chỉ dời được tới ngày {bc.ngay_xa_nhat():%d/%m} (xa nhất Báo cáo ngày cho nhập trước).")
        if s.execute(select(OnlineCa.id).where(OnlineCa.ngay == moi, OnlineCa.phong_code == r.phong_code,
                                               OnlineCa.ma_hd == r.ma_hd)).first():
            raise LoiOnline(f"HĐ {r.ma_hd} đã có trong ngày {moi:%d/%m} rồi.")
        cu, acc, ma = r.ngay, r.acc_norm, r.ma_hd
        _ghi_ls(r, ai, f"Dời sang ngày {moi:%d/%m}")
        r.trang_thai, r.online_luc = "doi_mai", None
        _dau(r, ai)
        n = OnlineCa(ngay=moi, phong_code=r.phong_code, ma_hd=r.ma_hd, acc_norm=acc, khung="chua", khung_dau="chua", trang_thai="du_kien",
                     ghi_chu=r.ghi_chu, lich_su=r.lich_su, tao_luc=utc_bay_gio(), tao_boi=ai[:60])
        _dau(n, ai)
        s.add(n)
    dong_bo_bang(cu, phong, [acc], ai, ep=True)
    dong_bo_bang(moi, phong, [acc], ai)
    from app import online_ton as ot
    ot.dong_bo_hen([ma], moi, phong, ai)
    return moi


def dong_bo_ngay_hen(id_: int, phong: list[str], ai: str) -> int:
    """Đặt ngày hẹn thi công ở Nhập tồn bằng đúng ngày của ca này (dùng khi thẻ báo Nhập tồn đang hẹn ngày khác)."""
    from app import online_ton as ot
    dam_bao_bang()
    with session_scope() as s:
        r = _tim(s, id_, phong)
        ma, ngay = r.ma_hd, r.ngay
    return ot.dong_bo_hen([ma], ngay, phong, ai)


def doi_nhieu(ids, loai: str, khung_ma: str, phong: list[str], ai: str) -> dict:
    """Dời nhiều ca một lần: loai = "khung" (sang khung_ma) hoặc "mai". Trả {"xong": số ca, "loi": [chữ lỗi]}."""
    xong, loi = 0, []
    for i in ids or []:
        try:
            if loai == "mai":
                doi_ngay(i, phong, ai)
            else:
                doi_khung(i, khung_ma, phong, ai)
            xong += 1
        except LoiOnline as e:
            loi.append(str(e))
    return {"xong": xong, "loi": loi}


def sua_ghi_chu(id_: int, ghi_chu: str, phong: list[str], ai: str) -> None:
    """Sửa ghi chú của ca. KHÔNG có đổi người phụ trách: mỗi HĐ gắn đúng người bán, không có chuyện chuyển hay sai HĐ (chủ app chốt 12/10/2026)."""
    dam_bao_bang()
    with session_scope() as s:
        r = _tim(s, id_, phong)
        r.ghi_chu = (ghi_chu or "").strip()[:GHI_CHU_TOI_DA] or None
        _dau(r, ai)


def xoa(id_: int, phong: list[str], ai: str) -> dict:
    """Xoá ca (huỷ). Trả {ma_hd, ngay} để trang ghi nhật ký."""
    dam_bao_bang()
    with session_scope() as s:
        r = _tim(s, id_, phong)
        thong_tin = {"ma_hd": r.ma_hd, "ngay": r.ngay}
        acc = r.acc_norm
        s.execute(delete(OnlineCa).where(OnlineCa.id == r.id))
    dong_bo_bang(thong_tin["ngay"], phong, [acc], ai, ep=True)
    return thong_tin


def ton_tat_ca(phong: list[str], ngay: date) -> dict[str, list[dict]]:
    """Hợp đồng TỒN (đã ký, chưa online, xem trang Nhập tồn) của từng nhân viên mà hôm nay chưa có ca: {acc: [{ma, ton: số ngày chờ, goi}]}.
    Gửi cả phòng một lần cùng gói dữ liệu để sale chọn mã thay vì gõ. Không lấy tên khách hàng."""
    from app import phan_tich as pt
    ton = pt.hop_dong_ton(list(phong))
    if ton.empty:
        return {}
    with session_scope() as s:
        co = set(s.execute(select(OnlineCa.ma_hd).where(OnlineCa.ngay == ngay, OnlineCa.phong_code.in_(phong))).scalars())
    ton = ton[~ton.hop_dong.isin(co)].sort_values("so_ngay_cho", ascending=False)
    out: dict[str, list[dict]] = {}
    for r in ton.itertuples():
        ds = out.setdefault(r.acc_norm, [])
        if len(ds) < 40:
            ds.append({"ma": r.hop_dong, "ton": int(r.so_ngay_cho or 0), "goi": str(r.goi_dich_vu or "")})
    return out


def ton_cua(acc_norm: str, phong: list[str], ngay: date) -> list[dict]:
    return ton_tat_ca(phong, ngay).get(acc_norm, []) if acc_norm else []
