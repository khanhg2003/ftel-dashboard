"""Ảnh PNG và file Excel "Báo cáo phòng" - để Trưởng phòng gửi nhóm Zalo của phòng mỗi sáng.

Dùng chung bộ font, cỡ chữ và cách căn chữ với ảnh Báo cáo Tổng (app/export_png.py) để hai ảnh
nhìn cùng một bộ nhận diện.
"""
from __future__ import annotations

import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from PIL import Image, ImageDraw

from app import bao_cao_phong as bp
from app.export_excel import KHUNG, MAU_KET_LUAN, dong_trang_thai
from app.export_png import (CAO_COT, CAO_DONG, CAO_NHOM, CHU_THUONG, CHU_TOTAL, DEM, LE, NEN,
                            NEN_COT, NEN_TOTAL, RONG_MUC_TIEU, TY_LE_MAX, TY_LE_MIN, VIEN, VIEN_DAM,
                            XAM_CHU, XANH_DAM, XANH_FPT, _Bo, _chia_dong, _giua, _giua_nhieu_dong,
                            _o_chu, gio_viet_nam)

MAU_TOT, MAU_VUA, MAU_KEM = "D3EBD4", "FCEBB4", "F7BDBD"
COT_CHU = {"ho_ten", "acc", "tham_nien_bucket", "muc_chu_y", "chu_y"}


def cau_truc_phong(thang: str, ngay: int):
    """(nhóm, [(tên cột, khoá, kiểu)]) dùng chung cho ảnh và Excel."""
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
    """Màu nền một ô nhân sự (không có dấu #). Tỷ lệ so với mức chung của phòng."""
    if v is None:
        return None
    if khoa in ("kem_vvip", "kem_camera") and tong.get(khoa) is not None:
        chung = float(tong[khoa])
        if v >= chung + 5:
            return MAU_TOT
        if v <= chung - 10:
            return MAU_KEM
        if v < chung - 5:
            return MAU_VUA
    if khoa == "ton_qua_7" and v > 0:
        return MAU_KEM if v >= 3 else MAU_VUA
    if khoa == "ngay_lien_chua_co_so" and v >= bp.NGAY_LIEN_CANH_BAO:
        return MAU_KEM if v >= 7 else MAU_VUA
    return None


def _tom_tat(thang: str, ngay: int, dong: dict, ss) -> list[tuple[str, str, str]]:
    """Dải chỉ số đầu ảnh: (nhãn, giá trị, dòng phụ)."""
    def pct(v):
        return "–" if v is None else f"{float(v):.0f}%"

    def so(v):
        return _o_chu("so", v) or "0"

    hang = ss[ss.khoa == "htkh_internet"].iloc[0] if len(ss) else None
    if hang is None or hang.hang is None:
        hang = ss[ss.khoa == "online"].iloc[0]
    kl = dong.get("ket_luan") or "—"
    return [
        ("Online tháng", so(dong.get("online")),
         f"Mục tiêu {so(dong.get('mt_internet'))} · HTKH {pct(dong.get('htkh_internet'))}"),
        ("Tăng trưởng", "–" if dong.get("tang_truong") is None else f"{dong['tang_truong']:+.0f}%",
         f"Cùng kỳ {bp.thang_truoc_nhan(thang)}: {so(dong.get('ck_online'))}"),
        ("VVIP/PTTB", pct(dong.get("vvip_ty_le")), f"{so(dong.get('vvip'))} V.VIP"),
        ("Camera", so(dong.get("camera")),
         f"Mục tiêu {so(dong.get('mt_camera'))} · HTKH {pct(dong.get('htkh_camera'))}"),
        (f"Online ngày {ngay:02d}/{thang[5:7]}", so(dong.get("ngay_online")),
         f"Mục tiêu {so(dong.get('mt_ngay'))} · {kl}"),
        ("Hạng phòng", f"{hang.hang}/{hang.so_phong}" if hang.hang else "–",
         "Theo tỷ lệ HTKH" if hang.khoa == "htkh_internet" else "Theo số online"),
    ]


# ------------------------------------------------------------------ PNG
def anh_bao_cao_phong(thang: str, ngay: int, code: str, tam_tinh: bool = False,
                      luc: datetime | None = None) -> tuple[bytes, str]:
    nv = bp.bang_nhan_su(thang, ngay, code)
    ss, dong = bp.so_sanh_phong(thang, ngay, code, tam_tinh)
    ct = cau_truc_phong(thang, ngay)
    cols = [c for _, nhom in ct for c in nhom]
    rows = nv.to_dict("records")
    tong = next((r for r in rows if r.get("loai_dong") == "total"), {})

    def do_rong(bo):
        do = ImageDraw.Draw(Image.new("RGB", (4, 4)))
        rong = []
        for ten, khoa, kieu in cols:
            w = max(do.textlength(x, font=bo.cot) for x in _chia_dong(ten))
            for r in rows:
                f = bo.o_dam if (r.get("loai_dong") != "data" or khoa == "ho_ten") else bo.o
                w = max(w, do.textlength(_o_chu(kieu, r.get(khoa)), font=f))
            rong.append(int(w) + bo.px(DEM * 2))
        return rong

    rong_goc = sum(do_rong(_Bo(1))) + LE * 2
    ty_le = max(TY_LE_MIN, min(TY_LE_MAX, RONG_MUC_TIEU * 0.8 / rong_goc))
    bo = _Bo(ty_le)
    rong = do_rong(bo)
    # tên nhóm dài hơn các cột bên dưới thì nới đều
    do = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    i = 0
    for ten_nhom, nhom in ct:
        n = len(nhom)
        thieu = do.textlength(ten_nhom, font=bo.nhom) + bo.px(DEM * 3) - sum(rong[i:i + n])
        if ten_nhom and thieu > 0:
            for j in range(i, i + n):
                rong[j] += int(thieu / n) + 1
        i += n

    the = _tom_tat(thang, ngay, dong, ss)
    rong_bang = sum(rong)
    le = bo.px(LE)
    cao_dau = bo.px(62)
    cao_the = bo.px(64)
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

    # ---- dải 6 chỉ số của phòng
    y = cao_dau
    w_the = rong_bang / len(the)
    for k, (nhan, gia_tri, phu) in enumerate(the):
        xt = x0 + k * w_the
        d.rectangle([xt, y, xt + w_the, y + cao_the], fill="#F4F8FC", outline=VIEN)
        d.text((xt + bo.px(10), y + bo.px(7)), nhan.upper(), font=bo.cot, fill=XAM_CHU)
        d.text((xt + bo.px(10), y + bo.px(22)), gia_tri, font=bo.tieu_de, fill=XANH_DAM)
        d.text((xt + bo.px(10), y + bo.px(47)), phu, font=bo.phu, fill=XAM_CHU)
    y += cao_the + bo.px(14)

    # ---- tiêu đề nhóm + tên cột
    x, i = x0, 0
    y_bang = y
    for ten_nhom, nhom in ct:
        w = sum(rong[i:i + len(nhom)])
        if ten_nhom:
            d.rectangle([x, y, x + w, y + bo.px(CAO_NHOM)], fill=XANH_FPT, outline="#FFFFFF",
                        width=max(1, bo.px(1)))
            _giua(d, x, y, w, bo.px(CAO_NHOM), ten_nhom, bo.nhom, "#FFFFFF")
        i += len(nhom)
        x += w
    y_cot = y + bo.px(CAO_NHOM)
    x = x0
    so_khong_nhom = len(ct[0][1])
    for i, (ten, _, _) in enumerate(cols):
        tren = y if i < so_khong_nhom else y_cot
        d.rectangle([x, tren, x + rong[i], y_cot + bo.px(CAO_COT)], fill=NEN_COT, outline=VIEN)
        _giua_nhieu_dong(d, x, tren, rong[i], y_cot + bo.px(CAO_COT) - tren, _chia_dong(ten),
                         bo.cot, XANH_DAM)
        x += rong[i]
    y = y_cot + bo.px(CAO_COT)

    # ---- dòng nhân sự
    h = bo.px(CAO_DONG)
    for r in rows:
        la_tong = r.get("loai_dong") == "total"
        x = x0
        for i, (_, khoa, kieu) in enumerate(cols):
            v = r.get(khoa)
            nen = NEN_TOTAL if la_tong else NEN
            if not la_tong:
                m = mau_o(khoa, v, tong)
                nen = "#" + m if m else nen
            d.rectangle([x, y, x + rong[i], y + h], fill=nen, outline=VIEN)
            f = bo.o_dam if (la_tong or khoa == "ho_ten") else bo.o
            mau_chu = CHU_TOTAL if la_tong else CHU_THUONG
            chu = _o_chu(kieu, v)
            _giua(d, x, y, rong[i], h, chu, f, mau_chu,
                  trai=bo.px(DEM) if khoa in COT_CHU else None)
            x += rong[i]
        y += h
    d.rectangle([x0, y_bang, x0 + rong_bang, y], outline=VIEN_DAM, width=max(2, bo.px(1.2)))
    d.text((x0, y + bo.px(9)),
           f"Nguồn: Sales & HR Dashboard · luỹ kế từ 01/{thang[5:7]} đến {ngay:02d}/{thang[5:7]}"
           f" · Hạng phòng so với {int(ss.so_phong.max() or 0)} phòng cùng nhóm"
           f" · xuất lúc {gio_viet_nam():%H:%M %d/%m/%Y}", font=bo.phu, fill=XAM_CHU)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue(), f"BaoCaoPhong_{code}_{thang.replace('-', '')}_ngay{ngay:02d}.png"


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
