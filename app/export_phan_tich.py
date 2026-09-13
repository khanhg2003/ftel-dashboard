"""Xuất Excel trang Phân tích bán hàng: mỗi bảng một sheet, tiêu đề cột tiếng Việt, tỷ lệ dạng %."""
from __future__ import annotations

import io

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from app.export_excel import KHUNG


def _sheet(wb: Workbook, ten: str, tieu_de: str, df: pd.DataFrame,
           cot: list[tuple[str, str, str]]) -> None:
    """cot: [(khoá, tên cột, kiểu so|pct|text)]."""
    ws = wb.create_sheet(ten[:31])
    ws["A1"] = tieu_de
    ws["A1"].font = Font(bold=True, size=13, color="0B2E4F")
    for j, (_, nhan, _) in enumerate(cot, start=1):
        o = ws.cell(row=3, column=j, value=nhan)
        o.font = Font(bold=True, size=10, color="FFFFFF")
        o.fill = PatternFill("solid", fgColor="0072BC")
        o.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        o.border = KHUNG
    for i, r in enumerate(df.to_dict("records"), start=4):
        la_tong = r.get("loai_dong") in ("subtotal", "total")
        for j, (khoa, _, kieu) in enumerate(cot, start=1):
            v = r.get(khoa)
            o = ws.cell(row=i, column=j)
            if kieu == "pct" and v is not None and not pd.isna(v):
                o.value, o.number_format = float(v) / 100, "0%"
            elif kieu == "so" and v is not None and not pd.isna(v):
                o.value, o.number_format = float(v), "#,##0.#" if float(v) % 1 else "#,##0"
            else:
                o.value = None if v is None or (isinstance(v, float) and pd.isna(v)) else v
            o.border = KHUNG
            o.alignment = Alignment(horizontal="left" if kieu == "text" else "center")
            if la_tong:
                o.font = Font(bold=True)
                o.fill = PatternFill("solid", fgColor="DCE8F4")
    ws.row_dimensions[3].height = 32
    ws.freeze_panes = "B4"
    for j, (_, nhan, kieu) in enumerate(cot, start=1):
        ws.column_dimensions[get_column_letter(j)].width = 24 if kieu == "text" else max(11, len(nhan) + 2)


def xuat_phan_tich(ten_file: str, tieu_de: str, bang: list[tuple[str, pd.DataFrame, list]]) -> bytes:
    """bang: [(tên sheet, dữ liệu, cột)] - sheet trống thì bỏ qua."""
    wb = Workbook()
    wb.remove(wb.active)
    for ten, df, cot in bang:
        if df is not None and len(df):
            _sheet(wb, ten, f"{tieu_de} · {ten}", df, cot)
    if not wb.sheetnames:
        wb.create_sheet("Trống")["A1"] = "Không có dữ liệu"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
