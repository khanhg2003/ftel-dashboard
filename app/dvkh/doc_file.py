"""Đọc file Excel "Báo cáo DVKH" thành dữ liệu sạch (chưa ghi database).

File có hai sheet SR khai báo hơn 1 triệu dòng nhưng chỉ vài nghìn dòng có chữ, nên đọc theo kiểu "gặp 200 dòng trống
liên tiếp thì dừng". Cột được nhận theo TÊN tiêu đề, không theo vị trí.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from io import BytesIO

import pandas as pd
from openpyxl import load_workbook

TRONG = ("", None, "N/A", "NaN", "nan", "#N/A", "#DIV/0!", "#VALUE!", "#REF!")
DUNG_SAU_DONG_TRONG = 200

# tiêu đề trong file -> tên cột trong database
COT_SR_BD = {
    "Chi nhánh": "chi_nhanh", "Quận huyện": "quan", "Mã SR": "ma_sr", "Số hợp đồng": "so_hd", "Loại yêu cầu": "loai_yc",
    "Loại khiếu nại / thay đổi/ giải đáp": "phan_loai", "Hình thức khiếu nại": "hinh_thuc_kn",
    "Nguyên nhân 1": "nguyen_nhan_1", "Nguyên nhân 2": "nguyen_nhan_2", "Nguyên nhân 3": "nguyen_nhan_3",
    "Loại dịch vụ": "loai_dv", "Kênh tiếp nhận": "kenh", "Nguồn tạo": "nguon_tao", "Thời gian yêu cầu": "tg_yc",
    "Kết quả liên hệ": "ket_qua_lien_he", "Công cụ liên hệ": "cong_cu", "Thời gian cập nhật lần đầu": "tg_cn_dau",
    "Kết quả tư vấn": "ket_qua_tu_van", "Tình trạng xử lý": "tinh_trang", "Phương án xử lý": "phuong_an",
    "Thời gian cập nhật lần cuối": "tg_cn_cuoi", "Tình trạng NET khi tạo yêu cầu": "net_tao",
    "Tình trạng NET hiện tại": "net_hien", "Tình trạng Pay hiện tại": "pay_hien", "Tình trạng Cam hiện tại": "cam_hien",
    "Người xử lý": "nguoi_xu_ly", "Đơn vị xử lý": "don_vi_xu_ly", "Nhân sự AU": "nhan_su_au", "Account tạo": "acc_tao",
    "Phí": "phi", "Miễn giảm phí": "mien_giam_phi", "Số lần cập nhật": "so_lan_cap_nhat", "Quá hạn": "qua_han",
}
COT_SR_CD = {
    "Mã chi nhánh": "chi_nhanh", "Quận huyện": "quan", "Mã SR": "ma_sr", "Số hợp đồng": "so_hd",
    "Nhóm chương trình": "nhom_ct", "Chương trình": "chuong_trinh", "Tình trạng ban đầu": "tinh_trang_dau",
    "Độ ưu tiên": "do_uu_tien", "Điểm nguy cơ RM": "diem_rm", "Ưu Tiên Chăm Sóc": "uu_tien_cs",
    "Nguồn phân phối": "nguon_pp", "Thời gian đổ dữ liệu": "tg_do", "Kết quả liên hệ": "ket_qua_lien_he",
    "Công cụ liên hệ": "cong_cu", "Thời gian cập nhật lần đầu": "tg_cn_dau", "Kết quả tư vấn": "ket_qua_tu_van",
    "Tình trạng xử lý": "tinh_trang", "Phương án xử lý": "phuong_an", "Thời gian cập nhật lần cuối": "tg_cn_cuoi",
    "Người xử lý": "nguoi_xu_ly", "Nhân sự AU": "nhan_su_au", "Thời gian phân công nhân sự xử lý": "tg_phan_cong",
    "Số lần chăm sóc": "so_lan_cs", "Lý do không cần liên hệ": "ly_do_khong_lh", "Lý do mất kết nối": "ly_do_mat_kn",
    "Quá hạn": "qua_han", "Trùng SR bị đông": "sr_bd_trung",
}
COT_SR_BD_THEM = {
    "Mã SR": "ma_sr", "Gói dịch vụ Net hiện tại": "goi_net", "Gói dịch vụ Pay hiện tại": "goi_pay", "Gói dịch vụ Cam hiện tại": "goi_cam",
    "Đơn vị của account tạo": "don_vi_tao", "Tình trạng duyệt đề xuất": "duyet_de_xuat", "Trùng": "trung",
}
COT_THOI_GIAN = {"tg_yc", "tg_cn_dau", "tg_cn_cuoi", "tg_do", "tg_phan_cong"}
COT_SO = {"phi", "mien_giam_phi", "so_lan_cap_nhat", "diem_rm", "so_lan_cs", "trung"}
# tiêu đề bảng rời mạng (bỏ dấu, chữ thường) -> cột database
COT_ROI_MANG = {
    "kh hien hanh": "kh_active", "kh active hien hanh": "kh_active", "kh dau ky": "kh_dau_ky", "kh active dau ky": "kh_dau_ky",
    "gross pttb": "gross_pttb", "huy tsd": "huy_tsd", "huy ssd": "huy_ssd", "ctbdv": "ctbdv",
    "ctbdv khoi phuc dv": "ctbdv_khoi_phuc", "hssd khoi phuc": "hssd_khoi_phuc", "ctbdv chuyen hssd": "ctbdv_chuyen_hssd",
    "cho thanh ly": "cho_thanh_ly", "cho thanh ly kpdv": "cho_tl_kpdv", "cho thanh ly hssd": "cho_tl_hssd",
    "ctbdv du kien": "ctbdv_du_kien", "kh roi mang": "kh_roi_mang",
    "ty le roi mang so voi kh active hien hanh": "ty_le_roi_active", "ty le % roi mang so voi kh active hien hanh": "ty_le_roi_active",
    "ty le roi mang so voi gross pttb": "ty_le_roi_gross", "ty le % roi mang so voi gross pttb": "ty_le_roi_gross",
    "net pttb": "net_pttb", "ty le giu lai": "ty_le_giu", "ty le % giu lai": "ty_le_giu",
    "ty le tang truong": "ty_le_tang", "ty le % tang truong": "ty_le_tang",
}
# phường / xã mới -> quận cũ (bảng "Quy tắc phường mới và quận cũ" của file; dùng khi file không có bảng này)
QUAN_CU = {
    "Phường An Hải": "Quận Sơn Trà", "Phường An Khê": "Quận Cẩm Lệ", "Phường Cẩm Lệ": "Quận Cẩm Lệ",
    "Phường Hải Châu": "Quận Hải Châu", "Phường Hải Vân": "Quận Liên Chiểu", "Phường Hòa Cường": "Quận Hải Châu",
    "Phường Hòa Khánh": "Quận Liên Chiểu", "Phường Hòa Xuân": "Quận Cẩm Lệ", "Phường Liên Chiểu": "Quận Liên Chiểu",
    "Phường Ngũ Hành Sơn": "Quận Ngũ Hành Sơn", "Phường Sơn Trà": "Quận Sơn Trà", "Phường Thanh Khê": "Quận Thanh Khê",
    "Xã Bà Nà": "Huyện Hòa Vang", "Xã Hòa Tiến": "Huyện Hòa Vang", "Xã Hòa Vang": "Huyện Hòa Vang",
}


def bo_dau(s) -> str:
    s = unicodedata.normalize("NFD", str(s or "")).replace("đ", "d").replace("Đ", "D")
    return re.sub(r"\s+", " ", "".join(c for c in s if not unicodedata.combining(c))).strip().lower()


def _sach(v):
    if isinstance(v, str):
        v = v.strip()
    return None if v in TRONG else v


def doc_sheet(ws) -> list[list]:
    """Các dòng của sheet, bỏ dòng trống ở cuối (kể cả khi file khai báo hàng triệu dòng)."""
    out, trong = [], 0
    for r in ws.iter_rows(values_only=True):
        if any(v not in ("", None) for v in r):
            out.append(list(r))
            trong = 0
        else:
            out.append([])
            trong += 1
            if trong >= DUNG_SAU_DONG_TRONG:
                break
    while out and not out[-1]:
        out.pop()
    return out


def _bang_tu_dong(dong: list[list], cot: dict[str, str]) -> pd.DataFrame:
    """Dòng đầu là tiêu đề; chỉ giữ cột có trong `cot`, đổi tên, làm sạch kiểu dữ liệu."""
    if not dong:
        return pd.DataFrame(columns=list(cot.values()))
    tieu_de = [str(v).strip() if v not in ("", None) else "" for v in dong[0]]
    vi_tri = {}
    for j, t in enumerate(tieu_de):
        if t in cot and cot[t] not in vi_tri:
            vi_tri[cot[t]] = j
    rows = [{k: (r[j] if j < len(r) else None) for k, j in vi_tri.items()} for r in dong[1:] if r]
    df = pd.DataFrame(rows, columns=list(vi_tri))
    for c in df.columns:
        df[c] = df[c].map(_sach)
    for c in COT_THOI_GIAN & set(df.columns):
        df[c] = pd.to_datetime(df[c], errors="coerce")
        df.loc[df[c] < pd.Timestamp("2000-01-01"), c] = pd.NaT          # giờ mặc định 1899 của Excel = chưa có
    for c in COT_SO & set(df.columns):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[df["ma_sr"].notna()].drop_duplicates("ma_sr", keep="last").reset_index(drop=True)
    return df


def _chuan_hoa_sr(df: pd.DataFrame, chuoi_hoa: tuple[str, ...]) -> pd.DataFrame:
    for c in ("nhan_su_au", "nguoi_xu_ly"):
        if c in df.columns:
            df[c] = df[c].map(lambda v: str(v).strip().lower() if v is not None and not pd.isna(v) else None)
    if "nguon_pp" in df.columns:
        df["nguon_pp"] = df["nguon_pp"].map(lambda v: str(v).strip().upper() if v is not None and not pd.isna(v) else None)
    if "qua_han" in df.columns:
        df["qua_han"] = df["qua_han"].map(lambda v: str(v).strip() if v is not None and not pd.isna(v) else None)
    for c in ("so_hd", "chi_nhanh"):
        if c in df.columns:
            df[c] = df[c].map(lambda v: str(v).strip().upper() if v is not None and not pd.isna(v) else None)
    for c in chuoi_hoa:
        if c in df.columns:
            df[c] = df[c].map(lambda v: str(v) if v is not None and not pd.isna(v) else None)
    return df


# ------------------------------------------------------------------ rời mạng
def doc_roi_mang(dong: list[list]) -> list[dict]:
    """Hai bảng: theo phòng (tiêu đề "Chi nhánh" + một dòng tiêu đề phụ) và theo quận / phường (tiêu đề "Name")."""
    out: list[dict] = []
    i = 0
    while i < len(dong):
        a = str((dong[i] + [""])[0]).strip()
        if a in ("Chi nhánh", "Name"):
            cap = "phong" if a == "Chi nhánh" else "quan"
            tieu_de = dong[i + 1] if cap == "phong" else dong[i]
            cot = {j: COT_ROI_MANG[bo_dau(t)] for j, t in enumerate(tieu_de) if j > 0 and bo_dau(t) in COT_ROI_MANG}
            k = i + 2 if cap == "phong" else i + 1
            while k < len(dong) and dong[k] and dong[k][0] not in ("", None):
                ten = str(dong[k][0]).strip()
                if ten.lower().startswith("tổng"):                         # dòng tổng: bảng phòng ghi chữ "1,080", bảng quận ghi "Tổng cộng"
                    k += 1
                    continue
                dl = {f: _so(dong[k][j]) if j < len(dong[k]) else None for j, f in cot.items()}
                if any(v is not None for v in dl.values()):
                    out.append({"cap": cap, "ten": ten, **dl})
                k += 1
            i = k
        i += 1
    return out


def _so(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    if isinstance(v, str):
        s = v.replace(",", "").replace("%", "").strip()
        try:
            return float(s)
        except ValueError:
            return None
    return None


# ------------------------------------------------------------------ công nợ
def _ky_no(nhan: str) -> str | None:
    m = re.search(r"(\d{1,2})\s*[./]\s*(\d{2,4})", nhan or "")
    if not m:
        return None
    thang, nam = int(m.group(1)), int(m.group(2))
    return f"{2000 + nam if nam < 100 else nam}-{thang:02d}" if 1 <= thang <= 12 else None


def _ky_no_dang_nam_thang(nhan: str) -> str | None:
    m = re.match(r"(\d{4})[./](\d{1,2})$", str(nhan or "").strip())
    return f"{m.group(1)}-{int(m.group(2)):02d}" if m else None


def doc_cong_no(dong: list[list]) -> tuple[list[dict], list[dict]]:
    """(chuỗi theo ngày, ảnh chụp hệ thống đổ hằng ngày).

    Chuỗi theo ngày: khối tiêu đề "Công nợ T8.26" (theo phòng) hoặc "Tháng 8.2026" (theo quận) có các ngày nằm ở cột
    2, 4, 6... mỗi ngày hai cột (Tỷ lệ DT, Tỷ lệ bill)."""
    chuoi: list[dict] = []
    chot: list[dict] = []
    i = 0
    while i < len(dong):
        r = dong[i]
        a = str((r + [""])[0]).strip()
        la_khoi_phong = a.startswith("Công nợ T")
        la_khoi_quan = bool(re.match(r"Tháng \d{1,2}\.\d{4}$", a))
        if la_khoi_phong or la_khoi_quan:
            ky = _ky_no(a)
            ngay = {j: v.date() if isinstance(v, datetime) else v for j, v in enumerate(r) if isinstance(v, (datetime, date))}
            cap = "phong" if la_khoi_phong else "quan"
            k = i + 2                                           # bỏ dòng "Ty le DT / Tỉ lệ bill"
            while k < len(dong) and dong[k] and dong[k][0] not in ("", None):
                ten = str(dong[k][0]).strip()
                for j, d in ngay.items():
                    dt = _so(dong[k][j]) if j < len(dong[k]) else None
                    bill = _so(dong[k][j + 1]) if j + 1 < len(dong[k]) else None
                    if dt is not None or bill is not None:
                        chuoi.append({"ky_no": ky, "ngay": d, "cap": cap, "ten": ten, "ty_le_dt": dt, "ty_le_bill": bill})
                k += 1
            i = k
            continue
        if a == "Tháng" and any("Số HĐ" in str(v) for v in r):                 # ảnh chụp theo phòng
            chot += _doc_anh_chup(dong, i, cap="phong", cot_ten=0, cot_so=1)
        elif a == "Quận lắp đặt":                                             # ảnh chụp theo phường / xã
            chot += _doc_anh_chup(dong, i, cap="quan", cot_ten=0, cot_so=2)
        i += 1
    return chuoi, chot


def _doc_anh_chup(dong: list[list], i: int, *, cap: str, cot_ten: int, cot_so: int) -> list[dict]:
    out, ky, nhom = [], None, "DNG_1"
    k = i + 1
    while k < len(dong) and dong[k]:
        r = dong[k] + [None] * 12
        ten = str(r[cot_ten]).strip() if r[cot_ten] not in ("", None) else ""
        nhan_thang = str(r[1]).strip() if cap == "quan" else ten
        ky = _ky_no_dang_nam_thang(nhan_thang) or ky
        so = [_so(x) for x in r[cot_so:cot_so + 8]]
        if cap == "phong":
            if ten.startswith("+Tổng DNG_1"):
                out.append(_dong_chot(cap, "DNG_1", "DNG_1", ky, so))
            elif ten.startswith("+Tổng DNG_2"):
                out.append(_dong_chot(cap, "DNG_2", "DNG_2", ky, so))
            elif ten.startswith("++Tổng"):
                out.append(_dong_chot(cap, "", "Đà Nẵng", ky, so))
        else:
            tong = str(r[1]).strip()
            if not ten and tong.startswith("+Tổng DNG_1"):
                nhom = "DNG_2"                                              # hết khối DNG_1, các phường tiếp theo thuộc DNG_2
            elif ten and ten != "KXD" and so[0] is not None:
                out.append(_dong_chot(cap, nhom, ten, ky, so))
        k += 1
    return out


def _dong_chot(cap, chi_nhanh, ten, ky, so) -> dict:
    ten_cot = ("so_hd", "tong_tien", "hd_da_tt", "tt_da_tt", "hd_con_no", "tt_con_no", "ty_le_dt", "ty_le_bill")
    return {"cap": cap, "chi_nhanh": chi_nhanh, "ten": ten, "ky_no": ky, **dict(zip(ten_cot, so))}


# ------------------------------------------------------------------ số khách mỗi CSKH phụ trách
def doc_so_kh_au(dong: list[list]) -> list[dict]:
    """Bảng "Count of Acc NVVP" nằm cuối sheet BC SR bị động: mỗi CSKH (Account IS) đang phụ trách bao nhiêu khách."""
    for i, r in enumerate(dong):
        if len(r) > 1 and str(r[0]).strip() == "Row Labels" and "nvvp" in bo_dau(r[1]):
            out: dict[str, int] = {}
            k = i + 1
            while k < len(dong) and dong[k] and dong[k][0] not in ("", None):
                ten, so = str(dong[k][0]).strip().lower(), _so(dong[k][1]) if len(dong[k]) > 1 else None
                if so and not ten.startswith("grand total"):
                    out[ten] = int(so)
                k += 1
            return [{"acc": a, "so_kh": n} for a, n in out.items()]
    return []


# ------------------------------------------------------------------ cả file
def doc_file(noi_dung: bytes | str) -> dict:
    """Đọc cả workbook. Trả {"sr_bd", "sr_bd_them", "sr_cd", "roi_mang", "chuoi_cong_no", "chot_cong_no", "ych", "no_cuoc", "so_kh_au", "canh_bao"}."""
    wb = load_workbook(BytesIO(noi_dung) if isinstance(noi_dung, bytes) else noi_dung, read_only=True, data_only=True)
    ten = {bo_dau(n): n for n in wb.sheetnames}
    canh_bao: list[str] = []

    def sheet(*khoa):
        for k in khoa:
            if k in ten:
                return doc_sheet(wb[ten[k]])
        canh_bao.append(f"Thiếu sheet “{khoa[0]}” trong file.")
        return []

    dong_bd = sheet("sr bi dong")
    sr_bd = _chuan_hoa_sr(_bang_tu_dong(dong_bd, COT_SR_BD), ("loai_dv",))
    sr_bd_them = _bang_tu_dong(dong_bd, COT_SR_BD_THEM)
    sr_cd = _chuan_hoa_sr(_bang_tu_dong(sheet("sr chu dong"), COT_SR_CD), ())
    so_kh_au = doc_so_kh_au(doc_sheet(wb[ten["bc sr bi dong"]])) if "bc sr bi dong" in ten else []
    roi = doc_roi_mang(sheet("roi mang"))
    chuoi, chot = doc_cong_no(sheet("cong no"))
    ds = sheet("data")
    ych = sorted({str(r[0]).strip().upper() for r in ds[1:] if r and r[0] not in ("", None)})
    no = sorted({str(r[2]).strip().upper() for r in ds[1:] if len(r) > 2 and r[2] not in ("", None)})
    if sr_bd.empty:
        canh_bao.append("Không đọc được dòng SR bị động nào.")
    if sr_cd.empty:
        canh_bao.append("Không đọc được dòng SR chủ động nào.")
    return {"sr_bd": sr_bd, "sr_bd_them": sr_bd_them, "sr_cd": sr_cd, "roi_mang": roi, "chuoi_cong_no": chuoi, "chot_cong_no": chot,
            "ych": ych, "no_cuoc": no, "so_kh_au": so_kh_au, "canh_bao": canh_bao}
