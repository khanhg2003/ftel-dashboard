"""Nhập tồn: sale ghi tình trạng từng hợp đồng chưa online, Trưởng phòng theo dõi (thay sheet "Mục tiêu và công việc
đầu ngày"). Chốt với chủ app 21/09/2026.

- Danh sách = đúng "Số tồn" của phòng (`phan_tich.hop_dong_ton`): HĐ online thì tự rời danh sách, HĐ mới tự thêm.
  Hợp đồng, tên KH, ngày tạo, acc lấy từ file Internet; sale chỉ ghi 3 mục (đều bắt buộc): Ghi chú tình trạng,
  Mốc tick (Hẹn thi công / Trả về + ngày), Phương án. Ghi theo mã HĐ nên giữ qua các ngày.
- Hẹn thi công: quá ngày mà chưa online -> đỏ, đúng hôm nay -> vàng.
- Trả về ngày D: hạn xử lý hết ngày D + `han_tra_ve_ngay` (3), quá hạn HĐ tự huỷ -> luôn đỏ để TP nắm.
- Phương án "Huỷ": dồn cuối nhóm, không cảnh báo. "Đã triển khai": chờ hệ thống lên online, không cảnh báo hẹn.
- Tài khoản dùng chung của phòng (Nhân viên KD): phải chọn tên mình ở bộ lọc mới sửa được, chỉ sửa ca của người
  đó, và "cập nhật bởi" ghi tên người đó (chốt 21/09/2026). Không chống được người cố chọn tên người khác, nhưng đủ
  để TP biết ai cập nhật. Tài khoản riêng (TP, Quản trị) ghi tên tài khoản.
"""
from __future__ import annotations

import io
import re
import unicodedata
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select, text

from app import phan_tich as pt
from app.config import rules_config
from app.db import engine, session_scope
from app.models import AuditLog, TonTheoDoi
from app.thoi_gian import chu_gio_vn, gio_viet_nam, utc_bay_gio

LOAI_MOC = {"hen": "Hẹn thi công", "tra_ve": "Trả về"}
PA_HUY, PA_DA_TRIEN_KHAI = "Huỷ", "Đã triển khai"
GHI_CHU_TOI_DA = 500
_da_tao = False


def cau_hinh() -> dict:
    c = rules_config().get("nhap_ton") or {}
    return {"phong": list(c.get("phong") or []), "han_tra_ve": int(c.get("han_tra_ve_ngay") or 3),
            "phuong_an": [_nfc(x) for x in c.get("phuong_an") or [PA_HUY]]}


def dam_bao_bang() -> None:
    global _da_tao
    if not _da_tao:
        TonTheoDoi.__table__.create(engine, checkfirst=True)
        _da_tao = True


def _nfc(v) -> str:
    return unicodedata.normalize("NFC", str(v or "")).strip()


def hom_nay() -> date:
    return gio_viet_nam().date()


# ------------------------------------------------------------------ cảnh báo
def trang_thai(loai: str | None, ngay: date | None, phuong_an: str | None, hom: date,
               han: int = 3) -> tuple[str, str, int]:
    """(mức "do" / "vang" / "huy" / "", chữ cảnh báo, thứ tự xếp - nhỏ lên trước)."""
    if phuong_an == PA_HUY:
        return "huy", "Đã chọn Huỷ", 9
    if phuong_an == PA_DA_TRIEN_KHAI:
        return "", "Đã triển khai · chờ online", 7
    if loai == "tra_ve" and ngay:
        han_chot = ngay + timedelta(days=han)
        con = (han_chot - hom).days
        if con < 0:
            return "do", f"Quá hạn {-con} ngày · có thể đã tự huỷ", 0
        if con == 0:
            return "do", "Trả về · hạn hết hôm nay", 1
        return "do", f"Trả về · còn {con} ngày (hạn {han_chot:%d/%m})", 1
    if loai == "hen" and ngay:
        tre = (hom - ngay).days
        if tre > 0:
            return "do", f"Quá hẹn {tre} ngày", 2
        if tre == 0:
            return "vang", "Đến hạn hôm nay", 3
        return "", f"Còn {-tre} ngày tới hẹn", 5
    return "", "", 5


def _acc(ton: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """(acc hiển thị, acc_norm) của từng HĐ; thiếu acc chuẩn hoá thì lấy acc viết thường."""
    acc = ton.acc_nhan_vien.fillna(ton.acc_norm).fillna("Chưa rõ")
    return acc, ton.acc_norm.fillna(acc.str.lower())


def ten_cua(acc_norm: str) -> str | None:
    """Họ tên của một acc (danh mục nhân viên) - máy chủ tự tra, không tin tên trình duyệt gửi lên."""
    with engine.connect() as c:
        return c.execute(text("SELECT ho_ten FROM dim_employee WHERE acc_norm = :a AND ho_ten IS NOT NULL"),
                         {"a": acc_norm}).scalar()


def _ten_ngan(ai) -> str:
    """"Bùi Ngô Anh Thắng" -> "Thắng"; tên tài khoản (không có dấu cách) giữ nguyên."""
    ai = str(ai or "").strip()
    return ai.split()[-1] if " " in ai else ai


def _ngay_iso(v) -> str:
    return "" if v is None or pd.isna(v) else str(v)[:10]


def danh_sach(phong: list[str]) -> pd.DataFrame:
    """Mỗi dòng một HĐ tồn của các phòng, kèm phần sale đã ghi và cảnh báo. Xếp theo nhân viên, trong nhóm:
    đỏ -> vàng -> chưa cập nhật -> còn lại -> đã triển khai -> huỷ, cùng mức thì HĐ cũ trước."""
    dam_bao_bang()
    ton = pt.hop_dong_ton(list(phong), ten_kh=True)
    if ton.empty:
        return pd.DataFrame()
    ghi = pd.read_sql_query(text("SELECT * FROM ton_theo_doi"), engine)
    df = ton.merge(ghi, on="hop_dong", how="left")
    ten = pd.read_sql_query(text("SELECT acc_norm, ho_ten FROM dim_employee WHERE acc_norm IS NOT NULL"), engine)
    ten = ten.drop_duplicates("acc_norm").set_index("acc_norm").ho_ten
    df["acc"], df["acc_norm"] = _acc(df)
    df["ho_ten"] = df.acc_norm.map(ten).fillna(df.acc)
    ch, hom = cau_hinh(), hom_nay()
    df["ngay_moc_d"] = pd.to_datetime(df.ngay_moc, errors="coerce").dt.date
    tt = [trang_thai(lo if isinstance(lo, str) else None, None if pd.isna(n) else n,
                     pa if isinstance(pa, str) else None, hom, ch["han_tra_ve"])
          for lo, n, pa in zip(df.loai_moc, df.ngay_moc_d, df.phuong_an)]
    df["muc"], df["canh_bao"], df["thu_tu"] = zip(*tt) if tt else ([], [], [])
    trong = [df[c].isna() | (df[c].astype(str).str.strip() == "") for c in ("ghi_chu", "loai_moc", "phuong_an")]
    df["thieu"] = (trong[0] | trong[1] | trong[2] | df.ngay_moc_d.isna()) & (df.muc != "huy")
    df.loc[df.thieu & (df.thu_tu == 5), "thu_tu"] = 4
    df["ngay_tao_hd"] = df.ngay_tao_hd.dt.strftime("%Y-%m-%d")
    df["ngay_moc"] = df.ngay_moc_d.map(_ngay_iso)
    df["cap_nhat"] = [" · ".join(x for x in (_luc(v), _ten_ngan(b)) if x) if _luc(v) else ""
                      for v, b in zip(df.cap_nhat_luc, df.cap_nhat_boi)]
    df["cap_nhat_boi"] = df.cap_nhat_boi.where(df.cap_nhat_boi.notna(), "")
    df["id"] = df.hop_dong
    df = df.sort_values(["ho_ten", "acc_norm", "thu_tu", "ngay_tao_hd", "hop_dong"]).reset_index(drop=True)
    cot = ["id", "hop_dong", "ten_khach_hang", "ngay_tao_hd", "so_ngay_cho", "acc", "acc_norm", "ho_ten",
           "ghi_chu", "loai_moc", "ngay_moc", "phuong_an", "cap_nhat", "cap_nhat_boi", "muc", "canh_bao",
           "thu_tu", "thieu"]
    out = df[cot].copy()
    for c in ("ghi_chu", "loai_moc", "phuong_an", "ten_khach_hang"):
        out[c] = out[c].where(out[c].notna(), "")
    return out


def _luc(v) -> str:
    """Giờ cập nhật dạng ngắn: "08:15" nếu hôm nay, "20/09 08:15" nếu ngày khác."""
    chu = chu_gio_vn(v, "%d/%m/%Y %H:%M")
    if not chu:
        return ""
    return chu[11:] if chu[:10] == f"{hom_nay():%d/%m/%Y}" else chu[:5] + chu[10:]


def tong_hop_nv(df: pd.DataFrame) -> pd.DataFrame:
    """Mỗi nhân viên một dòng: tồn, chưa cập nhật, trả về, quá hẹn, đến hạn hôm nay (không tính ca Huỷ)."""
    if df.empty:
        return pd.DataFrame()
    g = df.assign(tra_ve=df.thu_tu.isin([0, 1]), qua_hen=df.thu_tu == 2,
                  den_han=df.thu_tu == 3, huy=df.muc == "huy").groupby(["acc_norm", "acc", "ho_ten"], sort=False)
    out = g.agg(ton=("hop_dong", "size"), chua_cap_nhat=("thieu", "sum"), tra_ve=("tra_ve", "sum"),
                qua_hen=("qua_hen", "sum"), den_han=("den_han", "sum"), huy=("huy", "sum")).reset_index()
    out["gap"] = out.tra_ve + out.qua_hen
    return out


def dem(df: pd.DataFrame) -> dict:
    t = tong_hop_nv(df)
    if t.empty:
        return {"ton": 0, "chua_cap_nhat": 0, "gap": 0, "den_han": 0, "tra_ve": 0, "qua_hen": 0, "huy": 0}
    return {k: int(t[k].sum()) for k in ("ton", "chua_cap_nhat", "gap", "den_han", "tra_ve", "qua_hen", "huy")}


def loc(df: pd.DataFrame, acc: str | list | None = None, nhanh: str | None = None,
        tim: str | None = None) -> pd.DataFrame:
    """`acc`: một acc, danh sách acc (chọn nhiều người), hoặc rỗng / "all" = mọi người."""
    if df.empty:
        return df
    ds = [a for a in ([acc] if isinstance(acc, str) else acc or []) if a and a != "all"]
    if ds:
        df = df[df.acc_norm.isin(ds)]
    if nhanh == "gap":
        df = df[df.thu_tu.isin([0, 1, 2])]
    elif nhanh == "den_han":
        df = df[df.thu_tu == 3]
    elif nhanh == "thieu":
        df = df[df.thieu]
    if tim and tim.strip():
        k = _nfc(tim).lower()
        df = df[df.hop_dong.str.lower().str.contains(k, regex=False)
                | df.ten_khach_hang.str.lower().str.contains(k, regex=False)]
    return df


# ------------------------------------------------------------------ ghi
class LoiNhapTon(ValueError):
    pass


def _chuan(truong: dict) -> dict:
    """Kiểm và chuẩn hoá các mục sale gửi lên. Chỉ các khoá có trong `truong` được ghi (sửa từng ô)."""
    ch, out = cau_hinh(), {}
    if "ghi_chu" in truong:
        gc = _nfc(truong["ghi_chu"])
        if len(gc) > GHI_CHU_TOI_DA:
            raise LoiNhapTon(f"Ghi chú tối đa {GHI_CHU_TOI_DA} ký tự.")
        out["ghi_chu"] = gc or None
    if "loai_moc" in truong:
        lo = truong["loai_moc"] or None
        lo = {v: k for k, v in LOAI_MOC.items()}.get(lo, lo)
        if lo is not None and lo not in LOAI_MOC:
            raise LoiNhapTon("Loại mốc chỉ là Hẹn thi công hoặc Trả về.")
        out["loai_moc"] = lo
    if "ngay_moc" in truong:
        v = truong["ngay_moc"]
        try:
            out["ngay_moc"] = date.fromisoformat(str(v)[:10]) if v else None
        except ValueError:
            raise LoiNhapTon("Ngày mốc không đúng.") from None
    if "phuong_an" in truong:
        pa = _nfc(truong["phuong_an"]) or None
        if pa is not None and pa not in ch["phuong_an"]:
            raise LoiNhapTon("Phương án không có trong danh sách.")
        out["phuong_an"] = pa
    return out


def luu(hop_dong: str, truong: dict, phong: list[str], nguoi: str, chi_acc: str | None = None,
        ghi_ten: str | None = None) -> None:
    """Ghi phần sale nhập cho một HĐ. Máy chủ kiểm HĐ còn tồn và thuộc phòng người ghi được xem.

    `chi_acc`: tài khoản dùng chung chỉ được ghi ca của người này. `ghi_ten`: tên lưu vào "cập nhật bởi" thay
    cho tên tài khoản dùng chung (nhật ký vẫn ghi tài khoản thật)."""
    dam_bao_bang()
    hop_dong = _nfc(hop_dong)
    ton = pt.hop_dong_ton(list(phong))
    dong = ton[ton.hop_dong == hop_dong]
    if dong.empty:
        raise LoiNhapTon(f"{hop_dong} không còn trong danh sách tồn (có thể đã online).")
    if chi_acc is not None and _acc(dong)[1].iloc[0] != chi_acc:
        raise LoiNhapTon(f"{hop_dong} không phải ca của người đang chọn ở ô Nhân viên.")
    d = _chuan(truong)
    if not d:
        return
    with session_scope() as s:
        row = s.get(TonTheoDoi, hop_dong) or TonTheoDoi(hop_dong=hop_dong)
        for k, v in d.items():
            setattr(row, k, v)
        row.cap_nhat_luc, row.cap_nhat_boi = utc_bay_gio(), (ghi_ten or nguoi)[:60]
        s.add(row)
        s.add(AuditLog(username=nguoi, action="nhap_ton",
                       detail=f"{hop_dong}: {', '.join(d)}" + (f" · ghi dưới tên {ghi_ten}" if ghi_ten else "")))


# ------------------------------------------------------------------ nạp sheet cũ (một lần khi chuyển sang app)
_NGAY = re.compile(r"(\d{1,2})\s*/\s*(\d{1,2})(?:\s*/\s*(\d{2,4}))?")
_TRA_VE = re.compile(r"^\s*tr[aảá]\s*v[eềèé]", re.I)


def doc_moc(chu: str, hom: date) -> tuple[str | None, date | None]:
    """"29/9" -> Hẹn thi công 29/9; "trả về 19/9" -> Trả về 19/9; kiểu khác ("treo 13/9", "đang hoàn tiền")
    -> (None, None) để ghi vào ghi chú."""
    chu = _nfc(chu)
    m = _NGAY.search(chu)
    if not m:
        return None, None
    if _TRA_VE.match(chu):
        loai = "tra_ve"
    elif _NGAY.fullmatch(chu):
        loai = "hen"
    else:
        return None, None
    nam = int(m.group(3)) if m.group(3) else hom.year
    nam += 2000 if nam < 100 else 0
    try:
        d = date(nam, int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None, None
    if not m.group(3) and d > hom + timedelta(days=180):      # "28/12" đọc hồi tháng 1 là năm trước
        d = d.replace(year=nam - 1)
    return loai, d


def _cot(cols, *dau) -> str | None:
    for c in cols:
        k = _nfc(c).lower()
        if any(k.startswith(d) for d in dau):
            return c
    return None


def nap_sheet(noi_dung: bytes, ten_file: str, phong: list[str], nguoi: str) -> dict:
    """Nạp file sheet cũ (.csv / .xlsx: Hợp đồng, Ghi chú tình trạng, Mốc tick hẹn, Chốt/Phương án). Chỉ HĐ còn
    tồn của phòng; HĐ đã ghi trên app thì giữ bản trên app (mới hơn sheet)."""
    dam_bao_bang()
    if ten_file.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(noi_dung), dtype=str)
    else:
        df = pd.read_csv(io.BytesIO(noi_dung), dtype=str, encoding="utf-8-sig")
    c_hd, c_gc = _cot(df.columns, "hợp đồng"), _cot(df.columns, "ghi chú")
    c_moc, c_pa = _cot(df.columns, "mốc"), _cot(df.columns, "phương án", "chốt")
    if not c_hd:
        raise LoiNhapTon("File không có cột Hợp đồng.")
    ton = set(pt.hop_dong_ton(list(phong)).hop_dong)
    ch, hom = cau_hinh(), hom_nay()
    pa_chuan = {_nfc(x).lower().replace("hủy", "huỷ"): x for x in ch["phuong_an"]}
    with session_scope() as s:
        da_co = set(s.execute(select(TonTheoDoi.hop_dong)).scalars())
        kq = {"da_nap": 0, "da_co": 0, "khong_ton": 0, "moc_vao_ghi_chu": 0}
        for r in df.fillna("").to_dict("records"):
            hd = _nfc(r[c_hd]).upper()
            if not hd:
                continue
            if hd not in ton:
                kq["khong_ton"] += 1
                continue
            if hd in da_co:
                kq["da_co"] += 1
                continue
            gc, moc = _nfc(r.get(c_gc, "")), _nfc(r.get(c_moc, ""))
            loai, ngay = doc_moc(moc, hom) if moc else (None, None)
            if moc and loai is None:
                gc = f"{gc} (Mốc cũ: {moc})".strip()
                kq["moc_vao_ghi_chu"] += 1
            pa = pa_chuan.get(_nfc(r.get(c_pa, "")).lower().replace("hủy", "huỷ")) if c_pa else None
            s.add(TonTheoDoi(hop_dong=hd, ghi_chu=gc[:GHI_CHU_TOI_DA] or None, loai_moc=loai, ngay_moc=ngay,
                             phuong_an=pa, cap_nhat_luc=utc_bay_gio(), cap_nhat_boi=nguoi))
            da_co.add(hd)
            kq["da_nap"] += 1
        s.add(AuditLog(username=nguoi, action="nap_sheet_ton", detail=f"{ten_file}: {kq}"))
    return kq


def file_excel(df: pd.DataFrame) -> pd.DataFrame:
    """Bảng xuất Excel đúng thứ tự cột như sheet cũ."""
    return pd.DataFrame({
        "Nhân viên": df.ho_ten, "Acc": df.acc, "Hợp đồng": df.hop_dong, "Tên khách hàng": df.ten_khach_hang,
        "Ngày tạo HĐ": pd.to_datetime(df.ngay_tao_hd).dt.strftime("%d/%m/%Y"), "Số ngày chờ": df.so_ngay_cho,
        "Ghi chú tình trạng": df.ghi_chu, "Loại mốc": df.loai_moc.map(LOAI_MOC).fillna(""),
        "Ngày mốc": pd.to_datetime(df.ngay_moc, errors="coerce").dt.strftime("%d/%m/%Y").fillna(""),
        "Phương án": df.phuong_an, "Cảnh báo": df.canh_bao, "Cập nhật": df.cap_nhat})
