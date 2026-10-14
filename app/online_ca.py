"""Theo dõi Online trong ngày: mục nằm dưới bảng của trang Báo cáo ngày (chốt 12/10/2026, bật cùng phòng với Báo cáo ngày).

Quy tắc đã chốt với chủ app:
- Mỗi mã hợp đồng là MỘT phiếu (ca) riêng, gắn nhân viên + khung giờ dự kiến + trạng thái.
- Trạng thái: Dự kiến → Đang triển khai → Đã online. Sale tự cập nhật, KHÔNG lấy từ file Internet.
  Dời khung giờ hay dời sang ngày khác thì ghi vào lịch sử của phiếu. Không lưu tên khách hàng.
- Liên kết MỘT chiều với bảng Báo cáo ngày (chủ app chốt 13/10/2026, phương án A): từ hôm nay trở về trước ONL sáng / ONL chiều / Đã online của bảng tự đếm từ ca
  (`dem_theo_nguoi`), còn ngày chưa tới thì sale gõ tay trên bảng; mục này không ghi gì vào bảng. Còn nối với Nhập tồn (ngày hẹn, trạng thái, ghi chú).
- Phiếu giữ lại sau ngày (khác báo cáo đầu ngày bị xoá), để sau này xem lại tỷ lệ ca lên đúng giờ.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta

import pandas as pd
from sqlalchemy import delete, select, text

from app import bao_cao_ngay as bc
from app.bo_nho import nho
from app.config import rules_config
from app.db import engine, session_scope
from app.models import OnlineCa, TonTheoDoi
from app.thoi_gian import gio_viet_nam, sang_gio_vn, utc_bay_gio

TRANG_THAI = ("du_kien", "dang_lam", "da_online")        # sale tự đặt; "doi_mai" là trạng thái app đặt khi dời sang ngày kế
COT_THEM = {"khung_dau": "VARCHAR(16)", "online_luc": "TIMESTAMP"}
NHAN_TT = {"du_kien": "Dự kiến", "dang_lam": "Đang triển khai", "da_online": "Đã online"}
GHI_CHU_TOI_DA = 500                    # bằng ghi chú ở Nhập tồn (`nhap_ton.GHI_CHU_TOI_DA`): hai bên là cùng một chữ nên không được ngắn hơn
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


def _den_cua(r: OnlineCa) -> date | None:
    """Ngày mà phiếu `doi_mai` này đã được dời tới: lấy từ lần "Dời sang ngày" gần nhất (phiếu cũ chỉ có dd/mm thì suy ra năm)."""
    for x in reversed(_ls(r)):
        if x.get("den"):
            try:
                return date.fromisoformat(x["den"])
            except ValueError:
                return None
        m = re.match(r"Dời sang ngày (\d\d)/(\d\d)", x.get("viec", ""))
        if m:
            try:
                d = date(r.ngay.year, int(m[2]), int(m[1]))
            except ValueError:
                return None
            return d if d >= r.ngay else date(r.ngay.year + 1, d.month, d.day)
    return None


def ca_doi(phong: list[str], ngay: date) -> dict[str, list[dict]]:
    """Thống kê ca dời của ngày đang xem (chủ app 13/10/2026, mục này ẨN sẵn, bấm mới mở): `di` = ca của ngày này đã dời sang ngày khác (kèm ngày
    đích), `den` = ca từ ngày khác dời về ngày này (kèm ngày gốc, chỉ tính ca hiện còn ở ngày này). Mỗi ca một dòng: {ma, a: acc_norm, den | tu: ISO}."""
    dam_bao_bang()
    with session_scope() as s:
        rows = s.execute(select(OnlineCa).where(OnlineCa.phong_code.in_(phong), OnlineCa.trang_thai == "doi_mai",
                                                OnlineCa.ngay.between(ngay - timedelta(days=45), ngay + timedelta(days=45)))).scalars().all()
        song = {}                                          # mã -> các ngày mà phiếu đang HOẠT ĐỘNG (không phải doi_mai) trong khoảng đang xét
        for ma, d in s.execute(select(OnlineCa.ma_hd, OnlineCa.ngay).where(OnlineCa.phong_code.in_(phong), OnlineCa.trang_thai != "doi_mai",
                                                                          OnlineCa.ngay.between(ngay - timedelta(days=45), ngay + timedelta(days=45)))).all():
            song.setdefault(ma, []).append(d)
        di, den = [], []
        for r in rows:
            dich = _den_cua(r)
            if r.ngay == ngay and dich:
                # ca có thể đã được dời tiếp (A -> B -> C) hoặc đã huỷ: lấy nơi ca ĐANG Ở, huỷ rồi thì không còn là "dời đi"
                hien = sorted(d for d in song.get(r.ma_hd, []) if d != ngay)
                if hien:
                    di.append({"ma": r.ma_hd, "a": r.acc_norm, "den": (dich if dich in hien else hien[0]).isoformat()})
            elif r.ngay != ngay and dich == ngay and ngay in song.get(r.ma_hd, []):
                den.append({"ma": r.ma_hd, "a": r.acc_norm, "tu": r.ngay.isoformat()})
    return {"di": sorted(di, key=lambda x: (x["den"], x["ma"])), "den": sorted(den, key=lambda x: (x["tu"], x["ma"]))}


def ca_dang_o(phong: list[str], ma: str, quanh: date) -> dict | None:
    """Phiếu đang HOẠT ĐỘNG (không phải doi_mai) của một mã trong khoảng 45 ngày quanh `quanh`, gần `quanh` nhất; không có (đã huỷ) thì None."""
    dam_bao_bang()
    with session_scope() as s:
        rows = s.execute(select(OnlineCa).where(OnlineCa.phong_code.in_(phong), OnlineCa.ma_hd == ma, OnlineCa.trang_thai != "doi_mai",
                                                OnlineCa.ngay.between(quanh - timedelta(days=45), quanh + timedelta(days=45)))).scalars().all()
        rows.sort(key=lambda r: abs((r.ngay - quanh).days))
        return _dict(rows[0]) | {"ngay": rows[0].ngay} if rows else None


def moc(phong: list[str], ngay: date) -> str:
    """Dấu vết lần sửa gần nhất của các phiếu trong ngày VÀ của các HĐ Nhập tồn đang hẹn đúng ngày này, để trang tự nạp lại khi người khác vừa cập nhật
    (đổi ngày hẹn bên Nhập tồn cũng phải làm hộp "hẹn hôm nay" và ca được kéo về hiện ra, chủ app 13/10/2026)."""
    dam_bao_bang()
    from app import nhap_ton as nt
    nt.dam_bao_bang()
    ma = {f"p{i}": c for i, c in enumerate(phong)}
    cho = ", ".join(f":{k}" for k in ma)
    with engine.connect() as c:
        a = c.execute(text(f"SELECT COUNT(*), MAX(cap_nhat_luc) FROM online_ca WHERE ngay = :n AND phong_code IN ({cho})"),
                      {**ma, "n": ngay.isoformat()}).one()
        h = c.execute(text("SELECT COUNT(*), MAX(cap_nhat_luc) FROM ton_theo_doi WHERE loai_moc = 'hen' AND ngay_moc = :n"), {"n": ngay.isoformat()}).one()
    return f"{a[0]}|{a[1] or ''}|{h[0]}|{h[1] or ''}"


def dem_theo_nguoi(phong: list[str], ngay: date) -> dict[str, dict]:
    """Số ca của từng người trong `ngay` để điền vào ONL sáng / ONL chiều / Đã online của bảng Báo cáo ngày (chủ app 13/10/2026: từ HÔM NAY trở về
    trước các ô đó tự đếm từ ca, sale chỉ xếp khung giờ và đổi tình trạng ở thẻ ca). {acc: {sang, chieu, da_onl, chua, tong}}.
    Ca ở khung buổi sáng / chiều tính vào ô đúng buổi; ca "Chưa hẹn giờ" CHƯA tính vào ô nào (đếm riêng ở `chua`) cho tới khi đã online: lúc đó tính vào buổi
    của giờ sale bấm Đã online, nhờ vậy "đã online" luôn nằm trong "dự kiến" và Còn phải ONL không bao giờ âm vì ca chưa xếp giờ. Ca đã dời sang ngày khác không tính."""
    dam_bao_bang()
    buoi = {k["ma"]: k["buoi"] for k in khung()}
    out: dict[str, dict] = {}
    with session_scope() as s:
        rows = s.execute(select(OnlineCa.acc_norm, OnlineCa.khung, OnlineCa.trang_thai, OnlineCa.online_luc)
                         .where(OnlineCa.ngay == ngay, OnlineCa.phong_code.in_(phong), OnlineCa.trang_thai != "doi_mai")).all()
    for acc, kh, tt, luc in rows:
        o = out.setdefault(acc, {"sang": 0, "chieu": 0, "da_onl": 0, "chua": 0, "tong": 0})
        o["tong"] += 1
        b = buoi.get(kh, "")
        if tt == "da_online":
            o["da_onl"] += 1
            if not b:
                gio = sang_gio_vn(luc)
                b = "sang" if gio is not None and gio.hour < 12 else "chieu"
        elif not b:
            o["chua"] += 1
        if b in ("sang", "chieu"):
            o[b] += 1
    return out


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


def dong_bo_ghi_chu_ngay(phong: list[str], ngay: date, ai: str = "tự đồng bộ") -> int:
    """Kéo ghi chú các ca của `ngay` về KHỚP Nhập tồn (chủ app 13/10/2026: "đang có như nào thì đồng bộ luôn", chạy mỗi lần nạp mục này nên ca cũ
    tạo trước khi có liên kết hai chiều cũng tự khớp): HĐ có "Ghi chú tình trạng" ở Nhập tồn thì ca lấy đúng chữ đó; Nhập tồn trống mà ca có chữ
    thì chép chữ của ca sang Nhập tồn. Trả số ca đã đổi. Chỉ ghi khi có chỗ lệch nên bình thường là một câu đọc."""
    dam_bao_bang()
    from app import online_ton as ot
    with session_scope() as s:
        rows = s.execute(select(OnlineCa).where(OnlineCa.ngay == ngay, OnlineCa.phong_code.in_(phong), OnlineCa.trang_thai != "doi_mai")).scalars().all()
        if not rows:
            return 0
        gc_ton = ot.ghi_chu_ton({r.ma_hd for r in rows})
        n, sang_ton = 0, {}
        for r in rows:
            ton = gc_ton.get(r.ma_hd, "")
            if ton and (r.ghi_chu or "") != ton[:GHI_CHU_TOI_DA]:
                r.ghi_chu = ton[:GHI_CHU_TOI_DA]
                _dau(r, ai)
                n += 1
            elif not ton and r.ghi_chu:
                sang_ton[r.ma_hd] = r.ghi_chu
    for ma, gc in sang_ton.items():
        ot.ca_sang_ton(ma, gc, phong, ai)
    return n


def du_lieu(phong: list[str], ngay: date) -> dict:
    """Gói dữ liệu duy nhất gửi trình duyệt vẽ mục Theo dõi Online (assets/online.js)."""
    try:
        keo_ca_ve_ngay(phong, ngay)
    except Exception:                                      # noqa: BLE001 - kéo ca hỏng cũng không được làm mất cả mục
        logging.getLogger(__name__).exception("Không kéo được ca về ngày hẹn Nhập tồn")
    try:
        dong_bo_ghi_chu_ngay(phong, ngay)
    except Exception:                                      # noqa: BLE001 - đồng bộ ghi chú hỏng cũng không được làm mất cả mục
        logging.getLogger(__name__).exception("Không đồng bộ được ghi chú Nhập tồn")
    nv = nhan_vien(tuple(phong), ngay.isoformat())
    from app import online_ton as ot
    ca = ds_ca(phong, ngay)
    return {"ngay": ngay.isoformat(), "hom_nay": bc.hom_nay().isoformat(), "khung": khung(), "nv": nv, "ca": ca, "hen": ot.hen_cho_ngay(phong, ngay),
            "lech": ot.lech_ngay(ca, ngay, phong),
            "ton": ton_tat_ca(phong, ngay), "doi": ca_doi(phong, ngay), "xa_nhat": bc.ngay_xa_nhat().isoformat(), "moc": moc(phong, ngay)}


# ------------------------------------------------------------------ ghi
def _ghi_ls(r: OnlineCa, ai: str, viec: str, them: dict | None = None) -> None:
    ls = _ls(r)
    ls.append({"luc": gio_viet_nam().isoformat(timespec="minutes"), "ai": ai, "viec": viec, **(them or {})})
    r.lich_su = json.dumps(ls[-LS_TOI_DA:], ensure_ascii=False)


def _dau(r: OnlineCa, ai: str) -> None:
    r.cap_nhat_luc, r.cap_nhat_boi = utc_bay_gio(), ai[:60]


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
    gc_ton = ot.ghi_chu_ton(ma_ds)
    ket = {"them": [], "bo_qua": [(t, "mã không hợp lệ") for t in sai], "hoi": []}
    sang_ton = {}                                           # mã -> ghi chú mới cần chép sang Nhập tồn
    with session_scope() as s:
        da = {r.ma_hd: r for r in s.execute(select(OnlineCa).where(OnlineCa.ngay == ngay, OnlineCa.phong_code == phong[0])).scalars()}
        for ma in ma_ds:
            if ma in da and da[ma].trang_thai != "doi_mai":
                ket["bo_qua"].append((ma, "đã có trong ngày"))
                continue
            if ma in da and s.execute(select(OnlineCa.id).where(OnlineCa.ma_hd == ma, OnlineCa.phong_code == phong[0], OnlineCa.ngay != ngay,
                                                                OnlineCa.trang_thai != "doi_mai")).first():
                ket["bo_qua"].append((ma, "đã dời sang ngày mai"))      # ca đang sống ở ngày khác: muốn đưa về thì dời ca đó, không tạo phiếu thứ hai
                continue
            if ma in xd and not xac_nhan:
                ket["hoi"].append(xd[ma])
                continue
            gc = ot.gop_ghi_chu(gc_ton.get(ma, ""), ghi_chu)
            if gc != gc_ton.get(ma, "") and (ghi_chu or "").strip() in gc:
                sang_ton[ma] = gc
            if ma in da:                                    # phiếu đã dời đi ngày này rồi nay được hẹn lại đúng ngày: sống lại, không tạo phiếu thứ hai
                r = da[ma]
                r.trang_thai, r.online_luc, r.acc_norm, r.khung, r.khung_dau = "du_kien", None, acc_norm, khung_ma, khung_ma
                r.ghi_chu = gc[:GHI_CHU_TOI_DA] or None
                _ghi_ls(r, ai, f"Thêm lại vào ngày này, khung {_nhan_khung(khung_ma)}")
                _dau(r, ai)
                ket["them"].append(ma)
                continue
            r = OnlineCa(ngay=ngay, phong_code=phong[0], ma_hd=ma, acc_norm=acc_norm, khung=khung_ma, khung_dau=khung_ma,
                         trang_thai="du_kien", ghi_chu=gc[:GHI_CHU_TOI_DA] or None, tao_luc=utc_bay_gio(), tao_boi=ai[:60])
            _ghi_ls(r, ai, f"Tạo ca, khung {_nhan_khung(khung_ma)}")
            _dau(r, ai)
            s.add(r)
            ket["them"].append(ma)
    if not ket["them"] and not ket["hoi"]:
        raise LoiOnline("; ".join(f"{m}: {ly}" for m, ly in ket["bo_qua"]) + ".")
    if ket["them"]:
        ot.dong_bo_hen(ket["them"], ngay, phong, ai)
        for ma, gc in sang_ton.items():
            ot.ca_sang_ton(ma, gc, phong, ai)
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
        ma = r.ma_hd
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


def doi_nguoi(id_: int, acc_moi: str, phong: list[str], ai: str) -> None:
    """Chuyển ca cho SALE PHỤ TRÁCH khác (chủ app 13/10/2026: một acc có thể gồm ca của hai người, vd 6 ca của Ngọc Khái có 4 ca là của DNG.Tu).
    Chỉ đổi người của phiếu này (ngày này); người nhận phải thuộc danh sách nhân sự của phòng. Ghi lịch sử "Chuyển phụ trách A → B"."""
    dam_bao_bang()
    with session_scope() as s:
        r = _tim(s, id_, phong)
        if r.acc_norm == acc_moi:
            return
        ten = {x["a"]: x["t"] for x in nhan_vien(tuple(phong), r.ngay.isoformat())}
        if acc_moi not in ten:
            raise LoiOnline("Chọn một nhân viên của phòng.")
        _ghi_ls(r, ai, f"Chuyển phụ trách {ten.get(r.acc_norm, r.acc_norm)} → {ten[acc_moi]}")
        r.acc_norm = acc_moi
        _dau(r, ai)


def doi_ngay(id_: int, phong: list[str], ai: str, ngay_moi=None, khung_moi: str | None = None) -> date:
    """Dời ca sang một ngày KHÁC (mặc định ngày kế tiếp; `ngay_moi` là date hoặc chuỗi YYYY-MM-DD), tối đa tới ngày xa nhất Báo cáo ngày cho nhập
    trước (`bc.ngay_xa_nhat`). Ca cũ giữ lại ở ngày của nó với trạng thái "doi_mai" (không hiện trên bảng, nhưng tính là ca không lên đúng
    hẹn khi thống kê); ca mới ở ngày đích về Dự kiến, khung giờ do sale chọn lúc dời (`khung_moi`, bỏ trống = "Chưa hẹn giờ" để hôm đó xếp sau),
    ghi chú giữ nguyên.

    Dời NHẦM rồi dời VỀ LẠI ngày cũ (chủ app 13/10/2026): ngày đó còn phiếu "doi_mai" của chính mã này nên phiếu ấy được hồi sinh (về Dự kiến,
    giữ khung cũ nếu không chọn khung mới) thay vì tạo phiếu thứ hai; chỉ được lùi về ngày chưa tới hạn khi đó là hồi sinh. Ngày hẹn ở Nhập tồn
    luôn đổi theo ngày đích, nên hai bên khớp nhau cả khi dời qua dời lại."""
    dam_bao_bang()
    khung_moi = khung_moi or None
    if khung_moi:
        _khung_hop_le(khung_moi)
    if isinstance(ngay_moi, str):
        try:
            ngay_moi = date.fromisoformat(ngay_moi[:10])
        except ValueError:
            raise LoiOnline("Ngày không hợp lệ.") from None
    with session_scope() as s:
        r = _tim(s, id_, phong)
        moi = ngay_moi or r.ngay + timedelta(days=1)
        if moi == r.ngay:
            raise LoiOnline("Chọn một ngày khác ngày hiện tại của ca.")
        if moi > bc.ngay_xa_nhat():
            raise LoiOnline(f"Chỉ dời được tới ngày {bc.ngay_xa_nhat():%d/%m} (xa nhất Báo cáo ngày cho nhập trước).")
        cu_row = s.execute(select(OnlineCa).where(OnlineCa.ngay == moi, OnlineCa.phong_code == r.phong_code, OnlineCa.ma_hd == r.ma_hd)).scalars().first()
        if cu_row is not None and cu_row.trang_thai != "doi_mai":
            raise LoiOnline(f"HĐ {r.ma_hd} đã có trong ngày {moi:%d/%m} rồi.")
        if cu_row is None and moi < r.ngay and moi < bc.hom_nay():
            raise LoiOnline("Chỉ dời được từ hôm nay trở đi.")
        acc, ma = r.acc_norm, r.ma_hd
        _ghi_ls(r, ai, f"Dời sang ngày {moi:%d/%m}", {"tt": r.trang_thai, "onl": r.online_luc.isoformat() if r.online_luc else None, "den": moi.isoformat()})   # nhớ trạng thái để dời về lại thì trả đúng
        r.trang_thai, r.online_luc = "doi_mai", None
        _dau(r, ai)
        if cu_row is not None:
            nho = next((x for x in reversed(_ls(cu_row)) if x.get("tt") in TRANG_THAI), {})
            tt_cu = nho.get("tt", "du_kien")
            _ghi_ls(cu_row, ai, f"Dời về lại ngày {moi:%d/%m}")
            cu_row.trang_thai, cu_row.ghi_chu = tt_cu, r.ghi_chu
            try:
                cu_row.online_luc = datetime.fromisoformat(nho["onl"]) if tt_cu == "da_online" and nho.get("onl") else None
            except ValueError:
                cu_row.online_luc = None
            if khung_moi:
                cu_row.khung = khung_moi
            _dau(cu_row, ai)
        else:
            n = OnlineCa(ngay=moi, phong_code=r.phong_code, ma_hd=r.ma_hd, acc_norm=acc, khung=khung_moi or "chua", khung_dau=khung_moi or "chua",
                         trang_thai="du_kien", ghi_chu=r.ghi_chu, lich_su=r.lich_su, tao_luc=utc_bay_gio(), tao_boi=ai[:60])
            _dau(n, ai)
            s.add(n)
    from app import online_ton as ot
    ot.dong_bo_hen([ma], moi, phong, ai)
    return moi


def keo_ca_theo_ton(ma: str, phong: list[str], ai: str) -> bool:
    """Sale đổi mốc "Hẹn thi công" của HĐ ở Nhập tồn sang ngày D (chủ app 13/10/2026: đang hẹn 15/10, sửa thành 13/10) thì ca còn sống của HĐ đó
    (Dự kiến / Đang triển khai, từ hôm nay trở đi) được DỜI về D, vào "Chưa hẹn giờ" để sale xếp lại khung giờ - ngày cũ giữ phiếu `doi_mai` nên Hiệu quả vẫn
    tính đúng. HĐ chưa có ca thì không làm gì (hộp "Nhập tồn hẹn hôm nay" nhắc xếp ca). Trả True nếu đã dời. Lỗi (ngày quá xa, đã có ca ở D...) thì bỏ qua."""
    from app import nhap_ton as nt
    from app import online_ton as ot
    dam_bao_bang()
    x = ot._moc([ma]).get(ma)
    if not x or x["loai"] != "hen" or x["ngay"] is None or not bc.hom_nay() <= x["ngay"] <= bc.ngay_xa_nhat():
        return False
    if x["pa"] in (nt.PA_HUY, nt.PA_DA_TRIEN_KHAI):               # đã chốt hướng xử lý: không kéo ca về nữa (giống hộp nhắc `hen_cho_ngay`)
        return False
    if ma not in set(ot._ton(phong).hop_dong):                    # HĐ không còn trong tồn thì Nhập tồn không ghi được nữa: mốc ở đó là số CŨ, không được kéo ca về theo
        return False
    d = x["ngay"]
    with session_scope() as s:
        luc_ton = s.get(TonTheoDoi, ma).cap_nhat_luc
        rows = s.execute(select(OnlineCa).where(OnlineCa.ma_hd == ma, OnlineCa.phong_code.in_(phong), OnlineCa.ngay >= bc.hom_nay(),
                                                OnlineCa.trang_thai.in_(("du_kien", "dang_lam"))).order_by(OnlineCa.ngay)).scalars().all()
        if not rows or any(r.ngay == d for r in rows):
            return False
        # Chỉ kéo khi Nhập tồn được sửa SAU lần cuối ca đổi. Sale vừa dời ca ở Theo dõi Online (ca mới hơn Nhập tồn) thì ý sale là ngày của ca, không được kéo ngược
        # (lỗi thật 13/10/2026: dời ca sang ngày khác, tải lại thì ca về chỗ cũ).
        if luc_ton is not None and rows[0].cap_nhat_luc is not None and luc_ton <= rows[0].cap_nhat_luc:
            return False
        id_ = rows[0].id
    try:
        doi_ngay(id_, phong, ai, d)
    except LoiOnline:
        return False
    return True


def keo_ca_ve_ngay(phong: list[str], ngay: date, ai: str = "tự đồng bộ") -> int:
    """Mỗi lần nạp mục Theo dõi Online của `ngay` (từ hôm nay trở đi): HĐ mà Nhập tồn đang hẹn đúng `ngay` nhưng ca còn sống đang nằm ở ngày khác thì dời về
    (xem `keo_ca_theo_ton`). Bắt cả ca đã lệch từ trước khi có liên kết hoặc lúc trang Nhập tồn chưa kịp dời. Trả số ca đã dời."""
    if ngay < bc.hom_nay():
        return 0
    from app import nhap_ton as nt
    from app import online_ton as ot
    nt.dam_bao_bang()
    with session_scope() as s:
        hen = [r.hop_dong for r in s.execute(select(TonTheoDoi).where(TonTheoDoi.loai_moc == "hen", TonTheoDoi.ngay_moc == ngay)).scalars()]
    return sum(keo_ca_theo_ton(m, phong, ai) for m in hen) if hen and not ot._ton(phong).empty else 0


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
    """Sửa ghi chú của ca. KHÔNG có đổi người phụ trách: mỗi HĐ gắn đúng người bán, không có chuyện chuyển hay sai HĐ (chủ app chốt 12/10/2026).
    Ghi chú liên kết hai chiều với "Ghi chú tình trạng" ở Nhập tồn (xem `online_ton`): sửa ở đây thì Nhập tồn đổi theo."""
    dam_bao_bang()
    with session_scope() as s:
        r = _tim(s, id_, phong)
        r.ghi_chu = (ghi_chu or "").strip()[:GHI_CHU_TOI_DA] or None
        _dau(r, ai)
        ma, moi = r.ma_hd, r.ghi_chu or ""
    from app import online_ton as ot
    ot.ca_sang_ton(ma, moi, phong, ai)


def ghi_chu_tu_ton(ma: str, ghi_chu: str, phong: list[str], ai: str) -> int:
    """Nhập tồn vừa sửa "Ghi chú tình trạng" của một HĐ: chép sang các ca ĐANG CÒN (từ hôm nay trở đi) của HĐ đó ở Theo dõi Online. Trả số ca đã đổi."""
    dam_bao_bang()
    moi = (ghi_chu or "").strip()[:GHI_CHU_TOI_DA] or None
    n = 0
    with session_scope() as s:
        for r in s.execute(select(OnlineCa).where(OnlineCa.ma_hd == ma, OnlineCa.phong_code.in_(phong), OnlineCa.trang_thai != "doi_mai",
                                                  OnlineCa.ngay >= bc.hom_nay())).scalars():
            if (r.ghi_chu or None) != moi:
                r.ghi_chu = moi
                _dau(r, ai)
                n += 1
    return n


def xoa(id_: int, phong: list[str], ai: str) -> dict:
    """Xoá ca (huỷ). Trả {ma_hd, ngay} để trang ghi nhật ký."""
    dam_bao_bang()
    with session_scope() as s:
        r = _tim(s, id_, phong)
        thong_tin = {"ma_hd": r.ma_hd, "ngay": r.ngay}
        s.execute(delete(OnlineCa).where(OnlineCa.id == r.id))
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
