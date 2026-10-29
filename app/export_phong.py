"""Ảnh PNG và file Excel "Báo cáo phòng" - để Trưởng phòng gửi nhóm Zalo của phòng mỗi sáng.

Ảnh PNG vẽ ĐÚNG bảng đang xem trên web (cùng cột, thứ tự, chữ, màu - lấy từ `app/cot_phong.py`, nguồn chung
với `ui/pages/phong.py`) và dùng chung bộ font, cỡ chữ, cách căn chữ với ảnh Báo cáo Tổng (`export_png.py`).
Excel thì giữ bộ cột đầy đủ riêng (thêm Acc, Vị trí, tỷ lệ chất lượng...) nên không theo chế độ xem.
"""
from __future__ import annotations

import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from PIL import Image, ImageDraw

from app import bao_cao_phong as bp
from app import cot_phong as cp
from app.export_excel import KHUNG, MAU_KET_LUAN, dong_trang_thai
from app.export_png import (CAO_COT, CAO_DONG, CAO_NHOM, CHU_THUONG, DEM, LE, NEN, RONG_MUC_TIEU,
                            TY_LE_MAX, TY_LE_MIN, VIEN, VIEN_DAM, XAM_CHU, XANH_DAM, _Bo, _do_rong_cot,
                            _giua, _noi_rong_theo_nhom, gio_viet_nam, ve_dau_bang)

COT_CHU = {"ho_ten", "acc", "tham_nien_bucket", "muc_chu_y", "chu_y"}
KHOA_LUAT = {"kem_vvip": "kem_vvip", "kem_camera": "kem_camera", "ton_qua_7": "ton7",
             "ngay_lien_chua_co_so": "ngay_lien"}      # cột Excel có tô màu -> khoá cột trong cot_phong
NEN_TONG = "#DCE8F4"      # dòng TỔNG PHÒNG, đúng màu dòng ghim của bảng trên web
CHU_TONG = "#003057"
MAU_VACH = {"ok": "#00A650", "warn": "#C2791B", "bad": "#C8372D"}
MAU_VACH_VI_TRI = ["#0072BC", "#F37021", "#00A650", "#37A5E6", "#8C6FD1"]    # vạch đầu thẻ khi chưa có trạng thái
CAO_THE, KHE_THE = 64, 8


def cau_truc_phong(thang: str, ngay: int):
    """(nhóm, [(tên cột, khoá, kiểu)]) của file Excel - đủ mọi chỉ số (ảnh PNG dùng `cot_phong`)."""
    m = int(thang[5:7])
    return [
        ("", [("Hạng", "hang", "so"), ("Nhân sự", "ho_ten", "text"),
              ("Thâm niên", "tham_nien_bucket", "text")]),
        (f"LUỸ KẾ THÁNG {m}", [("Online", "online", "so"),
                               (f"Cùng kỳ {bp.thang_truoc_nhan(thang)}", "ck_online", "so"),
                               ("V.VIP", "vvip", "so"), ("VVIP/PTTB", "kem_vvip", "pct"),
                               ("Camera", "camera", "so"), ("Camera/PTTB", "kem_camera", "pct")]),
        (f"NGÀY {ngay:02d}/{m:02d}", [("Bán mới", "ban_moi_ngay", "so"),
                                     ("Online", "online_ngay", "so")]),
        ("SỐ TỒN", [("Chưa online", "ton", "so"), ("Chờ từ 7 ngày", "ton_qua_7", "so")]),
        ("THEO DÕI", [("Ngày liền chưa có số", "ngay_lien_chua_co_so", "so"),
                      ("Tuần này", "tuan_nay", "so"), ("Tuần trước", "tuan_truoc", "so")]),
        ("CẦN CHÚ Ý", [("Mức", "muc_chu_y", "text"), ("Nội dung", "chu_y", "text")]),
    ]


def tieu_de_phong(thang: str, ngay: int, code: str) -> str:
    return f"BÁO CÁO PHÒNG {bp.ten_phong(code).upper()} · NGÀY {ngay:02d}/{thang[5:7]}/{thang[:4]}"


def mau_o(khoa: str, v, tong: dict) -> str | None:
    """Màu nền một ô nhân sự trong Excel (không có dấu #); luật màu lấy từ `cot_phong` như bảng web."""
    k = cp.kieu_o(KHOA_LUAT[khoa], v, tong) if khoa in KHOA_LUAT else None
    return k[0] if k else None


# ------------------------------------------------------------------ PNG
def _o_phong(khoa: str, c, r: dict, tong: dict, ghim: bool) -> dict:
    """Một ô của ảnh: chữ, nền (None = trắng), màu chữ, đậm - cùng luật với bảng web (`ui/pages/phong.py`)."""
    v = r.get(c.field)
    nen, mau, dam = (NEN_TONG, CHU_TONG, True) if ghim else (None, CHU_THUONG, c.dam)
    if khoa == "chu_y":
        mau = "#" + cp.MAU_CHU_Y
    elif khoa == "ten" and not ghim:
        mau = "#" + cp.MAU_TEN
    k = cp.kieu_o(khoa, v, tong, ghim)
    if k:
        nen = "#" + k[0] if k[0] else nen
        mau, dam = "#" + k[1], k[2]
    return {"chu": cp.chu_o(c.kieu, v), "nen": nen, "mau_chu": mau, "dam": dam}


def luoi_phong(thang: str, ngay: int, code: str, che_do: str = "ban_hang", chi_chu_y: bool = False,
               tam_tinh: bool = False) -> dict:
    """Toàn bộ nội dung ảnh Báo cáo phòng (bảng + thẻ) dưới dạng chữ và màu từng ô.

    Cột, thứ tự hàng, chữ và màu lấy từ `app/cot_phong.py` - cùng nguồn với bảng trên web. Tách riêng để test
    so ô-với-ô với bảng web mà không phải đọc ảnh."""
    che_do = cp.chuan_che_do(che_do)
    nv = bp.bang_nhan_su(thang, ngay, code)
    ss, dong = bp.so_sanh_phong(thang, ngay, code, tam_tinh)
    rows, tong = cp.dong_nhan_su(nv, chi_chu_y)
    cot = cp.cot_phang(che_do, thang, ngay, "mttn" in tong)
    ct: list = []
    for nhom, _, c in cot:                       # gom cột liền nhau cùng nhóm; cột lẻ (nhóm rỗng) đứng riêng
        if ct and nhom and ct[-1][0] == nhom:
            ct[-1][1].append((c.ten, c.field))
        else:
            ct.append((nhom, [(c.ten, c.field)]))
    dong_o = [{"loai": "data", "o": [_o_phong(k, c, r, tong, False) for _, k, c in cot]} for r in rows]
    dong_o.append({"loai": "total", "o": [_o_phong(k, c, tong, tong, True) for _, k, c in cot]})
    return {"che_do": che_do, "cot": cot, "ct": ct, "dong": dong_o, "ss": ss, "dong_phong": dong,
            "the": cp.the_tom_tat(thang, ngay, code, dong, ss, tam_tinh)}


def _xep_the(d, the: list, rong_bang: int, bo: _Bo) -> tuple[int, int]:
    """(số thẻ mỗi hàng, số hàng): một hàng nếu đủ rộng, không thì chia nhiều hàng cho chữ không tràn thẻ."""
    can = max(max(d.textlength(t.nhan.upper(), font=bo.cot), d.textlength(t.gia_tri, font=bo.tieu_de),
                  d.textlength(t.phu, font=bo.phu)) for t in the) + bo.px(22)
    moi_hang = len(the)
    while moi_hang > 1 and rong_bang / moi_hang < can:
        moi_hang -= 1
    so_hang = -(-len(the) // moi_hang)
    return -(-len(the) // so_hang), so_hang        # chia đều các hàng cho khỏi lẻ một thẻ


def _ve_the(d, the: list, x0: int, y: int, rong_bang: int, bo: _Bo) -> int:
    """Dải thẻ chỉ số đầu ảnh, y hệt thẻ trên web: nhãn, số lớn, dòng phụ và vạch màu đầu thẻ.
    Trả về toạ độ y ngay dưới dải thẻ."""
    moi_hang, so_hang = _xep_the(d, the, rong_bang, bo)
    w, cao, khe = rong_bang / moi_hang, bo.px(CAO_THE), bo.px(KHE_THE)
    for k, t in enumerate(the):
        xt, yt = x0 + (k % moi_hang) * w, y + (k // moi_hang) * (cao + khe)
        vach = MAU_VACH.get(t.tt) or MAU_VACH_VI_TRI[k if k < len(MAU_VACH_VI_TRI) else 0]
        d.rectangle([xt, yt, xt + w, yt + cao], fill="#FFFFFF", outline=VIEN)
        d.rectangle([xt, yt, xt + w, yt + bo.px(3)], fill=vach)
        d.text((xt + bo.px(10), yt + bo.px(9)), t.nhan.upper(), font=bo.cot, fill=XAM_CHU)
        d.text((xt + bo.px(10), yt + bo.px(23)), t.gia_tri, font=bo.tieu_de, fill=XANH_DAM)
        d.text((xt + bo.px(10), yt + bo.px(48)), t.phu, font=bo.phu, fill=XAM_CHU)
    return y + so_hang * cao + (so_hang - 1) * khe


def anh_bao_cao_phong(thang: str, ngay: int, code: str, tam_tinh: bool = False,
                      luc: datetime | None = None, che_do: str = "ban_hang",
                      chi_chu_y: bool = False) -> tuple[bytes, str]:
    """Ảnh Báo cáo phòng đúng bảng đang xem trên web: `che_do` = ban_hang | theo_doi | tat_ca."""
    lu = luoi_phong(thang, ngay, code, che_do, chi_chu_y, tam_tinh)
    che_do, cot, ct, rows, the, ss = lu["che_do"], lu["cot"], lu["ct"], lu["dong"], lu["the"], lu["ss"]
    ten_cot = [(c.ten, k, c.kieu) for _, k, c in cot]

    rong_goc = sum(_do_rong_cot(ten_cot, rows, _Bo(1))) + LE * 2
    bo = _Bo(max(TY_LE_MIN, min(TY_LE_MAX, RONG_MUC_TIEU / rong_goc)))
    rong = _do_rong_cot(ten_cot, rows, bo)
    _noi_rong_theo_nhom(ct, rong, bo)
    rong_bang, le, cao_dau = sum(rong), bo.px(LE), bo.px(62)

    do = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    _, so_hang_the = _xep_the(do, the, rong_bang, bo)
    cao_the = so_hang_the * bo.px(CAO_THE) + (so_hang_the - 1) * bo.px(KHE_THE)
    cao = (cao_dau + cao_the + bo.px(14) + bo.px(CAO_NHOM + CAO_COT)
           + len(rows) * bo.px(CAO_DONG) + bo.px(30) + le)
    img = Image.new("RGB", (rong_bang + le * 2, cao), NEN)
    d = ImageDraw.Draw(img)
    x0 = le

    d.text((x0, bo.px(12)), tieu_de_phong(thang, ngay, code), font=bo.tieu_de, fill=XANH_DAM)
    trang_thai = dong_trang_thai(tam_tinh, luc)
    x = x0
    if trang_thai:
        f_tt = bo.phu_dam if tam_tinh else bo.phu
        d.text((x, bo.px(42)), trang_thai, font=f_tt, fill="#B45309" if tam_tinh else XAM_CHU)
        x += d.textlength(trang_thai + "   ·   ", font=f_tt)
    d.text((x, bo.px(42)), "FPT Telecom · Chi nhánh Đà Nẵng & Quảng Nam", font=bo.phu, fill=XAM_CHU)

    y_bang = _ve_the(d, the, x0, cao_dau, rong_bang, bo) + bo.px(14)
    y = ve_dau_bang(d, ct, rong, x0, y_bang, bo)
    h = bo.px(CAO_DONG)
    for r in rows:
        x = x0
        for i, o in enumerate(r["o"]):
            d.rectangle([x, y, x + rong[i], y + h], fill=o["nen"] or NEN, outline=VIEN)
            c = cot[i][2]
            _giua(d, x, y, rong[i], h, o["chu"], bo.o_dam if o["dam"] else bo.o, o["mau_chu"],
                  trai=bo.px(DEM) if c.kieu == "chu" and c.field != "tham_nien_bucket" else None)
            x += rong[i]
        y += h
    d.rectangle([x0, y_bang, x0 + rong_bang, y], outline=VIEN_DAM, width=max(2, bo.px(1.2)))
    ghi = " · chỉ người cần chú ý" if chi_chu_y else ""
    d.text((x0, y + bo.px(9)),
           f"Nguồn: Sales & HR Dashboard · luỹ kế từ 01/{thang[5:7]} đến {ngay:02d}/{thang[5:7]}"
           f" · Hạng phòng so với {int(ss.so_phong.max() or 0)} phòng cùng nhóm{ghi}"
           f" · xuất lúc {gio_viet_nam():%H:%M %d/%m/%Y}", font=bo.phu, fill=XAM_CHU)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    hau = "" if che_do == "ban" else f"_{che_do.replace('_', '')}"
    return buf.getvalue(), f"BaoCaoPhong_{code}_{thang.replace('-', '')}_ngay{ngay:02d}{hau}.png"


# ------------------------------------------------------------------ Excel
COT_EXCEL_THEM = [("Acc", "acc", "text"), ("Vị trí", "vi_tri", "text"),
                  ("Bán mới tháng", "ban_moi", "so"), ("Đủ 3 DV", "du_3", "pct"),
                  ("Trả trước", "tra_truoc", "pct"), ("Online trong 1 ngày", "onl_1_ngay", "pct"),
                  ("Số ngày có số", "so_ngay_co_so", "so"), ("Điểm NSLĐ kỳ trước", "diem_tong", "so"),
                  ("NSLĐ kỳ trước", "ket_luan", "text")]


def xuat_bao_cao_phong(thang: str, ngay: int, code: str, tam_tinh: bool = False,
                       luc: datetime | None = None) -> tuple[bytes, str]:
    nv = bp.bang_nhan_su(thang, ngay, code)
    ct = cau_truc_phong(thang, ngay) + [("THÊM", COT_EXCEL_THEM)]
    rows = nv.to_dict("records")
    tong = next((r for r in rows if r.get("loai_dong") == "total"), {})

    wb = Workbook()
    ws = wb.active
    ws.title = f"Phong {code}"
    ws["A1"] = tieu_de_phong(thang, ngay, code)
    ws["A1"].font = Font(bold=True, size=14, color="0B2E4F")
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
        for ten, _, _ in cot:
            o = ws.cell(row=r_cot, column=col, value=ten)
            o.font = Font(bold=True, size=9, color="17212E")
            o.fill = PatternFill("solid", fgColor="E9F1F9")
            o.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            o.border = KHUNG
            col += 1

    for i, row in enumerate(rows):
        la_tong = row.get("loai_dong") == "total"
        c = 1
        for _, cot in ct:
            for _, khoa, kieu in cot:
                v = row.get(khoa)
                o = ws.cell(row=r_dau + i, column=c)
                if kieu == "pct" and v is not None:
                    o.value, o.number_format = float(v) / 100, "0%"
                elif kieu == "so":
                    o.value, o.number_format = v, "#,##0"
                else:
                    o.value = v
                o.border = KHUNG
                o.alignment = Alignment(horizontal="left" if khoa in COT_CHU else "center")
                o.font = Font(bold=la_tong or khoa == "ho_ten", size=10)
                if la_tong:
                    o.fill = PatternFill("solid", fgColor="DCE8F4")
                else:
                    m = mau_o(khoa, v, tong)
                    if m:
                        o.fill = PatternFill("solid", fgColor=m)
                    if khoa == "ket_luan" and v == "NOT OK":
                        o.fill = PatternFill("solid", fgColor=MAU_KET_LUAN["Không đạt"])
                c += 1

    ws.freeze_panes = ws.cell(row=r_dau, column=3)
    for k in range(1, col):
        ws.column_dimensions[get_column_letter(k)].width = 11
    ws.column_dimensions["B"].width = 24
    ws.column_dimensions[get_column_letter(col - 1)].width = 48
    ws.row_dimensions[r_cot].height = 30

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), f"BaoCaoPhong_{code}_{thang.replace('-', '')}_ngay{ngay:02d}.xlsx"
