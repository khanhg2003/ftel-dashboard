"""Xuất Excel giữ nguyên định dạng: header gộp nhóm, heatmap, dòng tổng in đậm."""
from __future__ import annotations

import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.config import rules_config
from app.overview import bang_tong_quan

XANH_DAM = "0B2E4F"
HEAT = ["F7BDBD", "FBD9AE", "FCEBB4", "D3EBD4", "A5DCAF"]
VIEN = Side(style="thin", color="D8DEE7")
KHUNG = Border(left=VIEN, right=VIEN, top=VIEN, bottom=VIEN)

# (tiêu đề nhóm, [(tiêu đề cột, khoá dữ liệu, kiểu)]) - kiểu: so | pct:<ngưỡng> | text
def cau_truc(thang: str, ngay: int):
    thang_so = int(thang[5:7])
    return [
        ("", [("PKD", "phong", "text"), ("Nhân sự", "nhan_su", "so")]),
        (f"INTERNET THÁNG {thang_so}", [("Mục tiêu", "mt_internet", "so"),
                                        ("Số tồn", "so_ton", "so"),
                                        ("Số online", "online", "so"),
                                        ("Tỷ lệ HTKH", "htkh_internet", "pct:htkh")]),
        ("TĂNG TRƯỞNG", [("Số online", "ck_online", "so"), ("Tỷ lệ", "tang_truong",
                                                            "pct:tang_truong")]),
        ("FPT PLAY", [("Combo", "fpl_combo", "so"), ("Tỷ lệ FPL/NET", "fpl_ty_le", "pct:ty_le")]),
        ("PTTB CNQL", [("Số online", "cnql", "so"), ("Tỷ lệ", "cnql_ty_le", "pct:ty_le")]),
        ("COMBO VVIP", [("Số VVIP", "vvip", "so"),
                        ("Tỷ lệ VVIP/PTTB", "vvip_ty_le", "pct:ty_le")]),
        ("CAMERA", [("Mục tiêu", "mt_camera", "so"), ("Thực hiện", "camera", "so"),
                    ("Tỷ lệ HTKH", "htkh_camera", "pct:htkh")]),
        (f"KẾT QUẢ THỰC HIỆN NGÀY {ngay:02d}", [("Mục tiêu", "mt_ngay", "so"),
                                                ("Bán mới", "ngay_ban_moi", "so"),
                                                ("Online", "ngay_online", "so"),
                                                ("VVIP", "ngay_vvip", "so"),
                                                ("Kết luận", "ket_luan", "text")]),
    ]


def mau_heat(kind: str, gia_tri) -> str | None:
    if gia_tri is None:
        return None
    t = rules_config()["heatmap"][kind]
    moc = [t["rat_kem"], t["kem"], t["trung_binh"], t["kha"]]
    for i, m in enumerate(moc):
        if gia_tri < m:
            return HEAT[i]
    return HEAT[-1]


def xuat_tong_quan(thang: str, ngay: int | None = None,
                   chi_phong: list[str] | None = None) -> tuple[bytes, str]:
    """Trả về (nội dung file xlsx, tên file)."""
    df, ngay = bang_tong_quan(thang, ngay, chi_phong=chi_phong)
    ct = cau_truc(thang, ngay)

    wb = Workbook()
    ws = wb.active
    ws.title = f"Tong quan {thang}"

    ws["A1"] = f"BÁO CÁO TỔNG QUAN NGÀY {ngay:02d}/{thang[5:7]}/{thang[:4]}"
    ws["A1"].font = Font(bold=True, size=14, color=XANH_DAM)
    ws["A2"] = f"Xuất lúc {datetime.now():%d/%m/%Y %H:%M} · FPT Telecom - Chi nhánh Đà Nẵng & Quảng Nam"
    ws["A2"].font = Font(size=10, color="667789")

    r_nhom, r_cot, r_dau = 4, 5, 6
    col = 1
    for ten_nhom, cot in ct:
        if ten_nhom:
            ws.merge_cells(start_row=r_nhom, start_column=col, end_row=r_nhom,
                           end_column=col + len(cot) - 1)
            o = ws.cell(row=r_nhom, column=col, value=ten_nhom)
            o.font = Font(bold=True, size=10, color="FFFFFF")
            o.fill = PatternFill("solid", fgColor="0072BC")
            o.alignment = Alignment(horizontal="center", vertical="center")
        for ten_cot, _, _ in cot:
            o = ws.cell(row=r_cot, column=col, value=ten_cot)
            o.font = Font(bold=True, size=9, color="17212E")
            o.fill = PatternFill("solid", fgColor="E9F1F9")
            o.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            o.border = KHUNG
            col += 1

    for i, row in enumerate(df.to_dict("records")):
        r = r_dau + i
        col = 1
        la_tong = row.get("loai_dong") in ("subtotal", "total", "nhomkhac")
        nen = {"subtotal": "EDF3F9", "total": "DCE8F4", "nhomkhac": "FFF6EC"}.get(
            row.get("loai_dong"))
        chu = {"subtotal": "C8372D", "total": "003057", "nhomkhac": "8A4B08"}.get(
            row.get("loai_dong"), "17212E")
        for _, cot in ct:
            for _, khoa, kieu in cot:
                v = row.get(khoa)
                o = ws.cell(row=r, column=col)
                if kieu.startswith("pct") and v is not None:
                    o.value = v / 100
                    o.number_format = "0%"
                    mau = mau_heat(kieu.split(":")[1], v)
                    if mau:
                        o.fill = PatternFill("solid", fgColor=mau)
                elif kieu == "so":
                    o.value = v if v is not None else None
                    o.number_format = "#,##0"
                else:
                    o.value = v
                o.border = KHUNG
                o.alignment = Alignment(horizontal="left" if khoa == "phong" else "center")
                o.font = Font(bold=la_tong or khoa == "phong", size=10, color=chu)
                if nen and not (kieu.startswith("pct") and v is not None):
                    o.fill = PatternFill("solid", fgColor=nen)
                if khoa == "ket_luan" and v in ("Đạt", "Không đạt"):
                    o.fill = PatternFill("solid", fgColor="DCF5E6" if v == "Đạt" else "FBE3E1")
                col += 1

    ws.freeze_panes = ws.cell(row=r_dau, column=2)
    ws.column_dimensions["A"].width = 22
    for c in range(2, col):
        ws.column_dimensions[get_column_letter(c)].width = 12
    ws.row_dimensions[r_cot].height = 30

    buf = io.BytesIO()
    wb.save(buf)
    ten_file = f"TongQuan_{thang.replace('-', '')}_ngay{ngay:02d}.xlsx"
    return buf.getvalue(), ten_file
