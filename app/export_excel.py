"""Xuất Excel giữ nguyên định dạng: header gộp nhóm, heatmap, dòng tổng in đậm."""
from __future__ import annotations

import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.config import rules_config
from app.overview import TEN_PHAM_VI, bang_tong_quan

XANH_DAM = "0B2E4F"
HEAT = ["F7BDBD", "FBD9AE", "FCEBB4", "D3EBD4", "A5DCAF"]
VIEN = Side(style="thin", color="D8DEE7")
KHUNG = Border(left=VIEN, right=VIEN, top=VIEN, bottom=VIEN)
TEN_FILE = {"all": "ToanCN", "DNG": "DaNang", "QNM": "QuangNam"}
MAU_KET_LUAN = {"Đạt": "DCF5E6", "Không đạt": "FBE3E1", "Chưa đạt": "FDF1D8"}


def _khoang(thang: str, ngay: int, tu: str | None):
    from datetime import date
    den = date.fromisoformat(f"{thang}-{ngay:02d}")
    return (date.fromisoformat(tu) if tu else den.replace(day=1)), den


def la_luy_ke(thang: str, ngay: int, tu: str | None) -> bool:
    a, b = _khoang(thang, ngay, tu)
    return a == b.replace(day=1)


def tieu_de_bao_cao(thang: str, ngay: int, chi_nhanh: str = "all", tu: str | None = None) -> str:
    pham_vi = TEN_PHAM_VI.get(chi_nhanh, TEN_PHAM_VI["all"]).upper()
    if la_luy_ke(thang, ngay, tu):
        return f"BÁO CÁO TỔNG · {pham_vi} · NGÀY {ngay:02d}/{thang[5:7]}/{thang[:4]}"
    a, b = _khoang(thang, ngay, tu)
    return f"BÁO CÁO TỔNG · {pham_vi} · TỪ {a:%d/%m} ĐẾN {b:%d/%m/%Y}"


def mo_ta_ky(thang: str, ngay: int, tu: str | None = None) -> str:
    a, b = _khoang(thang, ngay, tu)
    return (f"luỹ kế từ {a:%d/%m} đến {b:%d/%m/%Y}" if la_luy_ke(thang, ngay, tu)
            else f"từ {a:%d/%m/%Y} đến {b:%d/%m/%Y}")


def hau_to_ky(thang: str, ngay: int, tu: str | None = None) -> str:
    """Phần tên file theo kỳ: 202609_ngay14 (luỹ kế) hoặc 20260908_den20260914."""
    a, b = _khoang(thang, ngay, tu)
    return (f"{thang.replace('-', '')}_ngay{ngay:02d}" if la_luy_ke(thang, ngay, tu)
            else f"{a:%Y%m%d}_den{b:%Y%m%d}")


def dong_trang_thai(tam_tinh: bool, luc: datetime | None) -> str:
    if tam_tinh and luc:
        return f"Số tạm tính, cập nhật lúc {luc:%H:%M %d/%m}"
    return f"Số đã chốt · cập nhật lần cuối {luc:%H:%M %d/%m}" if luc else ""


# (tiêu đề nhóm, [(tiêu đề cột, khoá dữ liệu, kiểu)]) - kiểu: so | pct:<ngưỡng> | text
def cau_truc(thang: str, ngay: int, tu: str | None = None):
    from app.overview import ten_khoang
    thang_so = int(thang[5:7])
    thang_truoc = 12 if thang_so == 1 else thang_so - 1
    a, b = _khoang(thang, ngay, tu)
    return [
        ("", [("PKD", "phong", "text"), ("Nhân sự", "nhan_su", "so")]),
        (f"INTERNET {ten_khoang(a, b)}", [("Mục tiêu", "mt_internet", "so"),
                                        ("Số tồn", "so_ton", "so"),
                                        ("Số online", "online", "so"),
                                        ("Tỷ lệ HTKH", "htkh_internet", "pct:htkh")]),
        ("TĂNG TRƯỞNG", [(f"Cùng kỳ T{thang_truoc}" if a == b.replace(day=1) else "Cùng kỳ tháng trước",
                          "ck_online", "so"), ("Tỷ lệ", "tang_truong",
                                                            "pct:tang_truong")]),
        ("FPT PLAY", [("Combo", "fpl_combo", "so"), ("Tỷ lệ FPL/NET", "fpl_ty_le", "pct:ty_le")]),
        ("PTTB CNQL", [("Số online", "cnql", "so"), ("Tỷ lệ", "cnql_ty_le", "pct:ty_le")]),
        ("COMBO VVIP", [("Số VVIP", "vvip", "so"),
                        ("Tỷ lệ VVIP/PTTB", "vvip_ty_le", "pct:ty_le")]),
        ("CAMERA", [("Mục tiêu", "mt_camera", "so"), ("Thực hiện", "camera", "so"),
                    ("Tỷ lệ HTKH", "htkh_camera", "pct:htkh")]),
        (f"KẾT QUẢ NGÀY {ngay:02d}/{thang_so:02d}", [("Mục tiêu", "mt_ngay", "so"),
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
                   chi_phong: list[str] | None = None, chi_nhanh: str = "all",
                   tam_tinh: bool = False, luc: datetime | None = None,
                   tu: str | None = None) -> tuple[bytes, str]:
    """Trả về (nội dung file xlsx, tên file)."""
    df, ngay = bang_tong_quan(thang, ngay, chi_phong=chi_phong, chi_nhanh=chi_nhanh,
                              tam_tinh=tam_tinh, tu=tu)
    ct = cau_truc(thang, ngay, tu)

    wb = Workbook()
    ws = wb.active
    ws.title = f"Tong quan {thang}"

    ws["A1"] = tieu_de_bao_cao(thang, ngay, chi_nhanh, tu)
    ws["A1"].font = Font(bold=True, size=14, color=XANH_DAM)
    ws["A2"] = " · ".join(x for x in (dong_trang_thai(tam_tinh, luc),
                                      "FPT Telecom - Chi nhánh Đà Nẵng & Quảng Nam") if x)
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
        la_tong = row.get("loai_dong") in ("subtotal", "total", "nhomkhac", "chinhanh")
        nen = {"subtotal": "D5E3F1", "total": "A9C6E3", "nhomkhac": "FCE7CC",
               "chinhanh": "C3D8EC"}.get(row.get("loai_dong"))
        chu = {"subtotal": "B01E14", "total": "002B4E", "nhomkhac": "7A3F06",
               "chinhanh": "003057"}.get(
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
                if khoa == "ket_luan" and v in MAU_KET_LUAN:
                    o.fill = PatternFill("solid", fgColor=MAU_KET_LUAN[v])
                col += 1

    ws.freeze_panes = ws.cell(row=r_dau, column=2)
    ws.column_dimensions["A"].width = 22
    for c in range(2, col):
        ws.column_dimensions[get_column_letter(c)].width = 12
    ws.row_dimensions[r_cot].height = 30

    buf = io.BytesIO()
    wb.save(buf)
    ten_file = f"BaoCaoTong_{TEN_FILE.get(chi_nhanh, 'ToanCN')}_{hau_to_ky(thang, ngay, tu)}.xlsx"
    return buf.getvalue(), ten_file
