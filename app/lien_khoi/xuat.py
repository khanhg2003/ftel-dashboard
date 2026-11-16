"""Xuất danh sách việc liên khối ra file Excel để quản lý gửi cho nhân sự (nhánh thi-lien-khoi).

Phạm vi lấy đúng như trang Theo dõi: quản lý ở ô "Tôi là" (kèm các team cấp dưới) và bộ lọc "Xem". Không có tên khách hàng
(chỉ mã hợp đồng, luật, lý do, đề xuất). Giờ trong file là giờ Việt Nam (dữ liệu lưu giờ UTC, cộng 7 giờ như trên màn hình).
Sheet 1 "Tất cả việc", sheet 2 "Theo nhân viên" (tổng hợp), rồi mỗi nhân viên một sheet riêng để gửi thẳng cho người đó.
"""
from __future__ import annotations

import io
import re
from datetime import datetime

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.lien_khoi import theo_doi as td, zalo_viec as zv

TOI_DA_SHEET_NHAN_VIEN = 40
COT = [("so_hd", "Mã hợp đồng", 14), ("ten_luat", "Loại việc", 24), ("muc", "Mức", 9), ("vai_tro_ten", "Vai trò", 11), ("phu_trach", "Người phụ trách", 24),
       ("quan_ly_ten", "Quản lý", 24), ("trang_thai_ten", "Trạng thái", 16), ("tao", "Giao lúc", 14), ("han", "Hạn", 14), ("con_lai", "Còn lại", 14),
       ("ly_do", "Lý do", 60), ("de_xuat", "Đề xuất xử lý", 60), ("ghi_chu", "Ghi chú", 40)]
XANH, DO, XAM = "0072BC", "B42318", "EEF3F8"
VIEN = Border(*(Side(style="thin", color="D0D7DE"),) * 4)


def _vn(t) -> str:
    return "" if t is None or pd.isna(t) else (pd.Timestamp(t) + pd.Timedelta(hours=7)).strftime("%d/%m/%Y %H:%M")


def _con_lai(r) -> str:
    if not r["dang_mo"]:
        return ""
    g = abs(r["con_lai_gio"])
    return f"Quá {g:.0f} giờ" if r["con_lai_gio"] < 0 else f"Còn {g:.0f} giờ"


def dung_bang(d: pd.DataFrame) -> pd.DataFrame:
    """Bảng việc dạng dễ đọc cho người nhận file: tên người thay cho mã, tiếng Việt, giờ Việt Nam."""
    if d.empty:
        return pd.DataFrame(columns=[c for c, _, _ in COT] + ["qua_han", "dang_mo"])
    ds = td.nguoi_nhan().fillna("")
    ten = dict(zip(ds["ma"], ds["ten"]))
    o = d.copy()
    giao_cho = o["giao_cho"].fillna("") if "giao_cho" in o.columns else pd.Series("", index=o.index)
    o["phu_trach"] = [ten.get(g or n, g or n) for g, n in zip(giao_cho, o["nguoi"])]
    o["quan_ly_ten"] = o["quan_ly"].map(lambda m: ten.get(m, m or ""))
    o["vai_tro_ten"] = o["vai_tro"].map(td.VAI_TRO)
    o["trang_thai_ten"] = o["trang_thai"].map(td.TRANG_THAI)
    o["con_lai"] = o.apply(_con_lai, axis=1)
    o["tao"], o["han"] = o["tao_luc"].map(_vn), o["han_luc"].map(_vn)
    for c in ("ly_do", "de_xuat", "ghi_chu"):
        o[c] = o[c].fillna("")
    return o[[c for c, _, _ in COT] + ["qua_han", "dang_mo"]].reset_index(drop=True)


def _ten_sheet(ten: str, da_dung: set[str]) -> str:
    s = re.sub(r"[\[\]:*?/\\]", " ", ten or "Chưa giao").strip()[:28] or "Nhân viên"
    goc, i = s, 2
    while s.lower() in da_dung:
        s, i = f"{goc[:25]} {i}", i + 1
    da_dung |= {s.lower()}
    return s


def _ve_sheet(ws, b: pd.DataFrame) -> None:
    """Đầu bảng xanh, đóng băng dòng đầu, có bộ lọc, mức Cao và việc quá hạn tô đỏ, chữ tự xuống dòng."""
    ws.append([t for _, t, _ in COT])
    for _, r in b.iterrows():
        ws.append([r[c] for c, _, _ in COT])
    for i, (_, _, w) in enumerate(COT, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    for c in ws[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor=XANH)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 24
    for i, (_, r) in enumerate(b.iterrows(), 2):
        for j in range(1, len(COT) + 1):
            c = ws.cell(i, j)
            c.alignment, c.border = Alignment(vertical="top", wrap_text=True), VIEN
        if r["muc"] == "Cao":
            ws.cell(i, 3).font = Font(bold=True, color=DO)
        if r["qua_han"]:
            ws.cell(i, 10).font = Font(bold=True, color=DO)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COT))}{max(len(b) + 1, 2)}"


def _tong_hop(b: pd.DataFrame) -> pd.DataFrame:
    if b.empty:
        return pd.DataFrame(columns=["Người phụ trách", "Tổng việc", "Đang mở", "Quá hạn", "Mức Cao đang mở", "Đã xong", "Không làm được"])
    g = b.groupby("phu_trach")
    t = pd.DataFrame({"Tổng việc": g.size(), "Đang mở": g["dang_mo"].sum(), "Quá hạn": g["qua_han"].sum(),
                      "Mức Cao đang mở": b[b["dang_mo"] & (b["muc"] == "Cao")].groupby("phu_trach").size(),
                      "Đã xong": b[b["trang_thai_ten"] == "Đã xong"].groupby("phu_trach").size(),
                      "Không làm được": b[b["trang_thai_ten"] == "Không làm được"].groupby("phu_trach").size()}).fillna(0).astype(int)
    return t.sort_values(["Quá hạn", "Đang mở"], ascending=False).reset_index().rename(columns={"phu_trach": "Người phụ trách"})


def xuat_excel(ma_ql: str | None = "all", loc: str | None = "mo", now: datetime | None = None) -> bytes:
    """Nội dung file .xlsx của phạm vi một quản lý (`ma_ql` "all" = toàn chi nhánh) và bộ lọc `loc` (mo | qua_han | da_xong | ... | all)."""
    d = td.loc_trang_thai(td.loc_pham_vi(td.danh_sach(now), ma_ql), loc)
    b = dung_bang(d)
    wb = Workbook()
    ws = wb.active
    ws.title = "Tất cả việc"
    _ve_sheet(ws, b)
    th = _tong_hop(b)
    w2 = wb.create_sheet("Theo nhân viên")
    w2.append(list(th.columns))
    for r in th.itertuples(index=False):
        w2.append(list(r))
    for i, w in enumerate((28, 11, 11, 11, 17, 11, 15), 1):
        w2.column_dimensions[get_column_letter(i)].width = w
    for c in w2[1]:
        c.font, c.fill, c.alignment = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor=XANH), Alignment(horizontal="center", wrap_text=True)
    for row in w2.iter_rows(min_row=2):
        for c in row:
            c.border = VIEN
        if row[3].value:
            row[3].font = Font(bold=True, color=DO)
    w2.freeze_panes = "A2"
    dung: set[str] = {"tất cả việc", "theo nhân viên"}
    for ten in list(th["Người phụ trách"])[:TOI_DA_SHEET_NHAN_VIEN]:
        _ve_sheet(wb.create_sheet(_ten_sheet(ten, dung)), b[b["phu_trach"] == ten])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def ten_file(ma_ql: str | None, now: datetime | None = None) -> str:
    ds = td.nguoi_nhan().fillna("")
    ten = "" if not ma_ql or ma_ql == "all" else next((str(r["ten"]) for r in ds.to_dict("records") if r["ma"] == ma_ql), "")
    hom_nay = (pd.Timestamp(now or td.bay_gio()) + pd.Timedelta(hours=7)).strftime("%Y%m%d")
    return f"ViecLienKhoi_{re.sub(r'[^0-9A-Za-z]+', '', zv._bo_dau(ten)) or 'ToanChiNhanh'}_{hom_nay}.xlsx"
