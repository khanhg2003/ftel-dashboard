"""File Excel mẫu và import hàng loạt: danh mục nhân sự, cơ cấu Bầy / Phòng.

Cách dùng chung cho cả hai loại:
1. Tải file mẫu - file đã điền sẵn dữ liệu đang có trên app, sửa trực tiếp trên đó cho nhanh.
2. Import lại - app đọc file và cho XEM TRƯỚC từng thay đổi (thêm mới / đổi phòng / đánh dấu nghỉ /
   dòng lỗi), bấm Áp dụng mới ghi. Dòng lỗi bị bỏ qua, các dòng khác vẫn áp dụng.

Danh mục nhân sự: file là DANH SÁCH ĐẦY ĐỦ - acc đang có trên app mà không có trong file được
ghi chú "Nghỉ" (không xoá, để giữ lịch sử và sửa lại được).
Cơ cấu: chỉ thêm / sửa bầy, phòng có trong file; muốn ngừng dùng thì ghi "Không" ở cột Đang dùng.
"""
from __future__ import annotations

import io
from datetime import date, datetime

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy import select

from app.db import session_scope
from app.ingest.normalize import norm_acc, norm_manv, norm_text, parse_date
from app.models import AuditLog, Bay, Phong, StaffMap
from app.org import LOAI_PHONG, xoa_cache_org

COT_NHAN_SU = ["Acc inside", "Phòng kinh doanh", "Mã NV", "Hiệu lực từ", "Hiệu lực đến", "Ghi chú"]
COT_BAY = ["Mã bầy", "Tên bầy", "Tên dòng tổng", "Thứ tự", "Đang dùng"]
COT_PHONG = ["Mã phòng", "Tên phòng", "Bầy", "Loại", "Chi nhánh", "Gộp nhóm Khác", "Thứ tự",
             "Đang dùng"]
XANH, NEN_DAU = "0072BC", "E9F1F9"
LOAI_THAY_DOI = ["Lỗi", "Thêm mới", "Đổi phòng", "Cập nhật", "Đánh dấu nghỉ", "Không đổi"]


# ------------------------------------------------------------------ viết file
def _dau_bang(ws, cot: list[str], bat_buoc: set[str], rong: list[int]) -> None:
    for j, ten in enumerate(cot, start=1):
        o = ws.cell(row=1, column=j, value=ten + (" *" if ten in bat_buoc else ""))
        o.font = Font(bold=True, color="FFFFFF")
        o.fill = PatternFill("solid", fgColor=XANH)
        o.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[o.column_letter].width = rong[j - 1]
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "A2"


def _huong_dan(wb: Workbook, dong: list[str]) -> None:
    ws = wb.create_sheet("Hướng dẫn")
    ws.column_dimensions["A"].width = 110
    for i, chu in enumerate(dong, start=1):
        o = ws.cell(row=i, column=1, value=chu)
        o.alignment = Alignment(wrap_text=True, vertical="top")
        if i == 1:
            o.font = Font(bold=True, size=13, color="0B2E4F")


def _danh_sach(wb: Workbook, ten: str, gia_tri: list[str]) -> str:
    """Sheet ẩn chứa danh sách chọn; trả về vùng tham chiếu cho ô chọn."""
    ws = wb.create_sheet(ten)
    for i, v in enumerate(gia_tri, start=1):
        ws.cell(row=i, column=1, value=v)
    ws.sheet_state = "hidden"
    return f"'{ten}'!$A$1:$A${max(1, len(gia_tri))}"


def _o_chon(ws, cot_chu: str, vung: str, so_dong: int = 2000) -> None:
    dv = DataValidation(type="list", formula1=vung, allow_blank=True, showErrorMessage=False)
    ws.add_data_validation(dv)
    dv.add(f"{cot_chu}2:{cot_chu}{so_dong}")


def _ngay(v) -> str | None:
    return v.strftime("%d/%m/%Y") if isinstance(v, (date, datetime)) else None


def _luu(wb: Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def mau_nhan_su() -> bytes:
    with session_scope() as s:
        phong = s.execute(select(Phong).order_by(Phong.thu_tu)).scalars().all()
        ten_phong = {p.code: p.ten for p in phong}
        ds_phong = [p.ten for p in phong if p.active]
        staff = s.execute(select(StaffMap).order_by(StaffMap.phong_code, StaffMap.acc)).scalars().all()
        rows = [[r.acc, ten_phong.get(r.phong_code, r.phong_code), r.ma_nv, _ngay(r.hieu_luc_tu),
                 _ngay(r.hieu_luc_den), r.ghi_chu] for r in staff]
    wb = Workbook()
    ws = wb.active
    ws.title = "Nhân sự"
    _dau_bang(ws, COT_NHAN_SU, {"Acc inside", "Phòng kinh doanh"}, [24, 24, 12, 14, 14, 40])
    for r in rows:
        ws.append(r)
    _o_chon(ws, "B", _danh_sach(wb, "ds_phong", ds_phong))
    _huong_dan(wb, [
        "HƯỚNG DẪN IMPORT DANH MỤC NHÂN SỰ",
        "File đã điền sẵn danh mục đang có trên app. Sửa trực tiếp rồi import lại ở Quản trị → "
        "Danh mục nhân sự → Import Excel.",
        "• Acc inside *: gõ đúng như trên hệ thống (VD DNG.AnhNV1). Không phân biệt hoa thường.",
        "• Phòng kinh doanh *: chọn trong danh sách (đúng tên phòng trên app).",
        "• Hiệu lực từ / đến: dd/mm/yyyy, chỉ cần khi nhân sự chuyển phòng giữa kỳ. Để trống nếu "
        "áp dụng mọi thời điểm.",
        "• Ghi chú: ghi “Nghỉ” cho người đã nghỉ việc.",
        "• QUAN TRỌNG: file là danh sách ĐẦY ĐỦ. Acc đang có trên app mà không có trong file sẽ "
        "được ghi chú “Nghỉ” (không bị xoá).",
        "• Trước khi ghi, app cho xem trước từng thay đổi. Dòng lỗi bị bỏ qua.",
        "• Sau khi áp dụng, app tự tính lại phòng cho các hợp đồng đã nạp.",
    ])
    return _luu(wb)


def mau_co_cau() -> bytes:
    with session_scope() as s:
        bays = s.execute(select(Bay).order_by(Bay.thu_tu)).scalars().all()
        ten_bay = {b.code: b.ten for b in bays}
        bay_rows = [[b.code, b.ten, b.ten_tong, b.thu_tu, "Có" if b.active else "Không"] for b in bays]
        phong_rows = [[p.code, p.ten, ten_bay.get(p.bay, p.bay), p.loai, p.chi_nhanh, p.nhom_khac,
                       p.thu_tu, "Có" if p.active else "Không"]
                      for p in s.execute(select(Phong).order_by(Phong.bay, Phong.thu_tu)).scalars()]
        ds_bay = [b.ten for b in bays]
    wb = Workbook()
    ws_b = wb.active
    ws_b.title = "Bầy"
    _dau_bang(ws_b, COT_BAY, {"Tên bầy"}, [14, 22, 26, 10, 12])
    for r in bay_rows:
        ws_b.append(r)
    ws_p = wb.create_sheet("Phòng")
    _dau_bang(ws_p, COT_PHONG, {"Tên phòng", "Bầy", "Loại", "Chi nhánh"},
              [16, 24, 18, 12, 12, 16, 10, 12])
    for r in phong_rows:
        ws_p.append(r)
    co_khong = _danh_sach(wb, "ds_co_khong", ["Có", "Không"])
    _o_chon(ws_b, "E", co_khong)
    _o_chon(ws_p, "C", _danh_sach(wb, "ds_bay", ds_bay))
    _o_chon(ws_p, "D", _danh_sach(wb, "ds_loai", LOAI_PHONG))
    _o_chon(ws_p, "E", _danh_sach(wb, "ds_chi_nhanh", ["DNG", "QNM"]))
    _o_chon(ws_p, "F", _danh_sach(wb, "ds_nhom_khac", ["DNG", "QNM"]))
    _o_chon(ws_p, "H", co_khong)
    _huong_dan(wb, [
        "HƯỚNG DẪN IMPORT CƠ CẤU BẦY / PHÒNG",
        "File đã điền sẵn cơ cấu đang có. Sửa rồi import lại ở Quản trị → Cơ cấu tổ chức → Import Excel.",
        "• Sheet Bầy: Tên bầy * bắt buộc. Mã bầy để trống khi thêm bầy mới - app tự tạo mã.",
        "• Sheet Phòng: Tên phòng, Bầy (tên bầy), Loại, Chi nhánh bắt buộc. Mã phòng để trống khi "
        "thêm phòng mới.",
        "• Loại: IBB / DIABAN (phòng bán hàng trực tiếp) · KT · CUS · ECOM · KHAC.",
        "• Gộp nhóm Khác: DNG hoặc QNM nếu phòng gộp vào dòng “Khác”, để trống nếu không.",
        "• Bầy / phòng không có trong file giữ nguyên. Muốn ngừng dùng thì ghi “Không” ở cột "
        "Đang dùng (không xoá, để giữ số liệu cũ).",
        "• Đổi bầy cho riêng một tháng thì dùng bảng “Cơ cấu Bầy của kỳ đang chọn”, không dùng file này.",
    ])
    return _luu(wb)


# ------------------------------------------------------------------- đọc file
def _doc_sheet(noi_dung: bytes, ten_sheet: str | None, cot_dau: str) -> pd.DataFrame:
    """Đọc sheet, tự tìm hàng tiêu đề (hàng có chữ `cot_dau`), bỏ dấu * ở tên cột."""
    xls = pd.ExcelFile(io.BytesIO(noi_dung))
    sheet = ten_sheet if ten_sheet in xls.sheet_names else xls.sheet_names[0]
    tho = pd.read_excel(xls, sheet_name=sheet, header=None, dtype=object)
    hang = next((i for i, r in tho.iterrows()
                 if any(norm_text(v).lower().startswith(cot_dau.lower()) for v in r.values)), None)
    if hang is None:
        raise ValueError(f"Không tìm thấy cột “{cot_dau}” trong sheet {sheet}. Hãy dùng file mẫu.")
    df = tho.iloc[hang + 1:].copy()
    df.columns = [norm_text(c).replace("*", "").strip() for c in tho.iloc[hang].values]
    df = df.dropna(how="all")
    df["_dong"] = df.index + 1
    return df


def _v(r, cot: str) -> str:
    v = r.get(cot)
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return norm_text(v)


def _ngay_nhap(r, cot: str):
    v = r.get(cot)
    if v is None or (isinstance(v, float) and pd.isna(v)) or norm_text(v) == "":
        return None, ""
    if isinstance(v, (datetime, date, pd.Timestamp)):
        return (v.date() if isinstance(v, (datetime, pd.Timestamp)) else v), ""
    s = norm_text(v)
    try:
        return datetime.strptime(s, "%d/%m/%Y").date(), ""
    except ValueError:
        d = parse_date(s)
        return (d, "") if d else (None, f"{cot} “{s}” không đúng dạng dd/mm/yyyy")


def la_nghi(ghi_chu: str | None) -> bool:
    return "nghỉ" in (ghi_chu or "").lower()


def xem_truoc_nhan_su(noi_dung: bytes) -> pd.DataFrame:
    """Mỗi dòng một thay đổi: loai, acc, phong_cu, phong_moi, chi_tiet, dong (dòng trong file)."""
    df = _doc_sheet(noi_dung, "Nhân sự", "Acc")
    with session_scope() as s:
        phong = s.execute(select(Phong)).scalars().all()
        staff = s.execute(select(StaffMap)).scalars().all()
        tra_phong = {}
        for p in phong:
            tra_phong[norm_text(p.ten).lower()] = p
            tra_phong[p.code.lower()] = p
        ten = {p.code: p.ten for p in phong}
        hien_co = [{"id": r.id, "acc": r.acc, "acc_norm": r.acc_norm, "phong": r.phong_code,
                    "ma_nv": r.ma_nv or "", "tu": r.hieu_luc_tu, "den": r.hieu_luc_den,
                    "ghi_chu": r.ghi_chu or ""} for r in staff]

    out, da_gap, acc_trong_file = [], set(), set()
    for r in df.to_dict("records"):
        acc = _v(r, "Acc inside")
        ten_p = _v(r, "Phòng kinh doanh")
        tu, loi_tu = _ngay_nhap(r, "Hiệu lực từ")
        den, loi_den = _ngay_nhap(r, "Hiệu lực đến")
        dong = {"dong": int(r["_dong"]), "acc": acc, "phong_moi": ten_p, "phong_cu": "",
                "ma_nv": norm_manv(_v(r, "Mã NV")), "tu": tu, "den": den,
                "ghi_chu": _v(r, "Ghi chú"), "id": None}
        loi = [x for x in (loi_tu, loi_den) if x]
        if not acc:
            loi.append("Thiếu Acc inside")
        p = tra_phong.get(ten_p.lower()) if ten_p else None
        if not ten_p:
            loi.append("Thiếu Phòng kinh doanh")
        elif p is None:
            loi.append(f"Phòng “{ten_p}” không có trên app")
        khoa = (norm_acc(acc), tu)
        if acc and khoa in da_gap:
            loi.append("Acc bị lặp trong file")
        da_gap.add(khoa)
        if loi:
            out.append({**dong, "loai": "Lỗi", "chi_tiet": "; ".join(loi)})
            continue
        acc_trong_file.add(norm_acc(acc))
        dong["phong_moi"], dong["phong_code"] = p.ten, p.code
        cung_acc = [h for h in hien_co if h["acc_norm"] == norm_acc(acc)]
        cu = next((h for h in cung_acc if h["tu"] == tu), None)
        if cu is None and tu is None and len(cung_acc) == 1:
            cu = cung_acc[0]
        if cu is None:
            out.append({**dong, "loai": "Thêm mới", "chi_tiet": ""})
            continue
        dong["id"], dong["phong_cu"] = cu["id"], ten.get(cu["phong"], cu["phong"])
        doi = []
        if cu["phong"] != p.code:
            doi.append(f"phòng {dong['phong_cu']} → {p.ten}")
        if dong["ma_nv"] and dong["ma_nv"] != norm_manv(cu["ma_nv"]):
            doi.append("mã NV")
        if (cu["den"], cu["tu"]) != (den, tu):
            doi.append("ngày hiệu lực")
        if dong["ghi_chu"] != cu["ghi_chu"]:
            doi.append(f"ghi chú “{cu['ghi_chu']}” → “{dong['ghi_chu']}”")
        loai = "Đổi phòng" if cu["phong"] != p.code else ("Cập nhật" if doi else "Không đổi")
        out.append({**dong, "loai": loai, "chi_tiet": ", ".join(doi)})

    for h in hien_co:
        if h["acc_norm"] not in acc_trong_file and not la_nghi(h["ghi_chu"]):
            out.append({"dong": None, "acc": h["acc"], "phong_cu": ten.get(h["phong"], h["phong"]),
                        "phong_moi": ten.get(h["phong"], h["phong"]), "phong_code": h["phong"],
                        "id": h["id"], "ma_nv": h["ma_nv"], "tu": h["tu"], "den": h["den"],
                        "ghi_chu": h["ghi_chu"], "loai": "Đánh dấu nghỉ",
                        "chi_tiet": "Không có trong file → ghi chú “Nghỉ”"})
    kq = pd.DataFrame(out)
    if kq.empty:
        return kq
    kq["_o"] = kq.loai.map({k: i for i, k in enumerate(LOAI_THAY_DOI)})
    return kq.sort_values(["_o", "acc"]).drop(columns="_o").reset_index(drop=True)


def ap_dung_nhan_su(noi_dung: bytes, ten_file: str, nguoi: str) -> dict:
    kq = xem_truoc_nhan_su(noi_dung)
    dem = {k: int((kq.loai == k).sum()) for k in LOAI_THAY_DOI} if len(kq) else {}
    hom_nay = date.today().strftime("%d/%m/%Y")
    with session_scope() as s:
        for r in kq.to_dict("records"):
            if r["loai"] in ("Lỗi", "Không đổi"):
                continue
            row = s.get(StaffMap, int(r["id"])) if r.get("id") and not pd.isna(r["id"]) else None
            if r["loai"] == "Đánh dấu nghỉ":
                if row is not None:
                    row.ghi_chu = (f"Nghỉ (import {hom_nay})" + (f" · {row.ghi_chu}" if row.ghi_chu else ""))[:200]
                continue
            if row is None:
                row = StaffMap(acc=r["acc"], acc_norm=norm_acc(r["acc"]), phong_code=r["phong_code"])
                s.add(row)
            row.acc, row.acc_norm, row.phong_code = r["acc"], norm_acc(r["acc"]), r["phong_code"]
            row.ma_nv = r["ma_nv"] or row.ma_nv
            row.hieu_luc_tu = r["tu"] if not pd.isna(r["tu"]) else None
            row.hieu_luc_den = r["den"] if not pd.isna(r["den"]) else None
            row.ghi_chu = r["ghi_chu"] or None
            row.nguon = f"import {ten_file}"[:50]
        s.add(AuditLog(username=nguoi, action="import_danh_muc_nv", detail=f"{ten_file} | {dem}"))
    from app.ingest.commit import recompute_phong
    with session_scope() as s:
        dem["gan_lai_hop_dong"] = recompute_phong(s)
    return dem


# ------------------------------------------------------------- cơ cấu bầy/phòng
def _co(v: str) -> bool:
    return v.strip().lower() not in ("không", "khong", "0", "false", "no")


def xem_truoc_co_cau(noi_dung: bytes) -> pd.DataFrame:
    """Mỗi dòng một thay đổi: doi_tuong (Bầy/Phòng), loai, ma, ten, chi_tiet, dong."""
    bay_df = _doc_sheet(noi_dung, "Bầy", "Tên bầy")
    phong_df = _doc_sheet(noi_dung, "Phòng", "Tên phòng")
    with session_scope() as s:
        bays = {b.code: b for b in s.execute(select(Bay)).scalars()}
        phongs = {p.code: p for p in s.execute(select(Phong)).scalars()}
        bay_cu = {c: dict(ten=b.ten, ten_tong=b.ten_tong or "", thu_tu=b.thu_tu, active=b.active)
                  for c, b in bays.items()}
        phong_cu = {c: dict(ten=p.ten, bay=p.bay, loai=p.loai, chi_nhanh=p.chi_nhanh,
                            nhom_khac=p.nhom_khac or "", thu_tu=p.thu_tu, active=p.active)
                    for c, p in phongs.items()}

    out = []
    ten_bay_moi = {}                                   # tên bầy (thường) -> mã (cũ hoặc "mới")
    for c, b in bay_cu.items():
        ten_bay_moi[b["ten"].lower()] = c
    for r in bay_df.to_dict("records"):
        ma, ten = _v(r, "Mã bầy").upper(), _v(r, "Tên bầy")
        if not ten:
            out.append({"doi_tuong": "Bầy", "loai": "Lỗi", "ma": ma, "ten": "", "dong": int(r["_dong"]),
                        "chi_tiet": "Thiếu Tên bầy"})
            continue
        ma = ma or ten_bay_moi.get(ten.lower(), "")
        moi = dict(ten=ten, ten_tong=_v(r, "Tên dòng tổng"), thu_tu=int(float(_v(r, "Thứ tự") or 0)),
                   active=_co(_v(r, "Đang dùng") or "Có"))
        ten_bay_moi[ten.lower()] = ma or f"(mới) {ten}"
        cu = bay_cu.get(ma)
        if cu is None:
            loai, ct = "Thêm mới", ""
        else:
            doi = [k for k in moi if moi[k] != cu[k] and not (k == "ten_tong" and not moi[k])]
            loai, ct = ("Cập nhật", ", ".join(doi)) if doi else ("Không đổi", "")
        out.append({"doi_tuong": "Bầy", "loai": loai, "ma": ma, "ten": ten, "dong": int(r["_dong"]),
                    "chi_tiet": ct, **{f"_{k}": v for k, v in moi.items()}})

    ten_phong = {p["ten"].lower(): c for c, p in phong_cu.items()}
    for r in phong_df.to_dict("records"):
        ma, ten = _v(r, "Mã phòng").upper(), _v(r, "Tên phòng")
        bay, loai_p = _v(r, "Bầy"), _v(r, "Loại").upper()
        cn, nk = _v(r, "Chi nhánh").upper(), _v(r, "Gộp nhóm Khác").upper()
        loi = []
        if not ten:
            loi.append("Thiếu Tên phòng")
        ma_bay = ten_bay_moi.get(bay.lower()) or (bay.upper() if bay.upper() in bay_cu else None)
        if not bay:
            loi.append("Thiếu Bầy")
        elif not ma_bay:
            loi.append(f"Bầy “{bay}” không có trên app hoặc sheet Bầy")
        if loai_p not in LOAI_PHONG:
            loi.append(f"Loại “{loai_p}” không hợp lệ (IBB/DIABAN/KT/CUS/ECOM/KHAC)")
        if cn not in ("DNG", "QNM"):
            loi.append("Chi nhánh phải là DNG hoặc QNM")
        if nk and nk not in ("DNG", "QNM"):
            loi.append("Gộp nhóm Khác chỉ nhận DNG, QNM hoặc để trống")
        if loi:
            out.append({"doi_tuong": "Phòng", "loai": "Lỗi", "ma": ma, "ten": ten,
                        "dong": int(r["_dong"]), "chi_tiet": "; ".join(loi)})
            continue
        ma = ma or ten_phong.get(ten.lower(), "")
        moi = dict(ten=ten, bay=ma_bay, loai=loai_p, chi_nhanh=cn, nhom_khac=nk,
                   thu_tu=int(float(_v(r, "Thứ tự") or 0)), active=_co(_v(r, "Đang dùng") or "Có"))
        cu = phong_cu.get(ma)
        if cu is None:
            loai, ct = "Thêm mới", ""
        else:
            doi = [k for k in moi if moi[k] != cu[k]]
            loai = "Cập nhật" if doi else "Không đổi"
            ct = ", ".join(("bầy " + bays[cu["bay"]].ten + " → " + bay) if k == "bay" and cu["bay"] in bays
                           else k for k in doi)
        out.append({"doi_tuong": "Phòng", "loai": loai, "ma": ma, "ten": ten, "dong": int(r["_dong"]),
                    "chi_tiet": ct, **{f"_{k}": v for k, v in moi.items()}})
    kq = pd.DataFrame(out)
    if kq.empty:
        return kq
    kq["_o"] = kq.loai.map({k: i for i, k in enumerate(LOAI_THAY_DOI)})
    return kq.sort_values(["_o", "doi_tuong", "ten"]).drop(columns="_o").reset_index(drop=True)


def ap_dung_co_cau(noi_dung: bytes, ten_file: str, nguoi: str) -> dict:
    from app.org import _ma_moi
    kq = xem_truoc_co_cau(noi_dung)
    can = kq[kq.loai.isin(["Thêm mới", "Cập nhật"])] if len(kq) else kq
    dem = {k: int((kq.loai == k).sum()) for k in LOAI_THAY_DOI} if len(kq) else {}
    with session_scope() as s:
        ma_bay = {b.code for b in s.execute(select(Bay)).scalars()}
        tao_moi = {}
        for r in can[can.doi_tuong == "Bầy"].to_dict("records"):
            ma = r["ma"] or _ma_moi(r["ten"], ma_bay)
            ma_bay.add(ma)
            tao_moi[f"(mới) {r['ten']}"] = ma
            row = s.get(Bay, ma) or Bay(code=ma)
            row.ten, row.thu_tu, row.active = r["ten"], r["_thu_tu"], r["_active"]
            row.ten_tong = r["_ten_tong"] or row.ten_tong or f"TỔNG {r['ten'].upper()}"
            s.add(row)
        s.flush()
        ma_phong = {p.code for p in s.execute(select(Phong)).scalars()}
        for r in can[can.doi_tuong == "Phòng"].to_dict("records"):
            ma = r["ma"] or _ma_moi(r["ten"], ma_phong)
            ma_phong.add(ma)
            row = s.get(Phong, ma) or Phong(code=ma)
            row.ten, row.loai, row.chi_nhanh = r["_ten"], r["_loai"], r["_chi_nhanh"]
            row.bay = tao_moi.get(r["_bay"], r["_bay"])
            row.nhom_khac = r["_nhom_khac"] or None
            row.thu_tu, row.active = r["_thu_tu"], r["_active"]
            s.add(row)
        s.add(AuditLog(username=nguoi, action="import_co_cau", detail=f"{ten_file} | {dem}"))
    xoa_cache_org()
    return dem
