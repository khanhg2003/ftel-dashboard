"""Chụp ảnh báo cáo ra file PNG (vẽ thẳng bằng Pillow, không qua trình duyệt).

Vì sao không chụp màn hình bằng JavaScript: bảng trên giao diện chỉ dựng những cột
đang nhìn thấy, chụp ra sẽ thiếu. Vẽ ở máy chủ thì luôn đủ 100% dòng và cột, nét,
và không phụ thuộc người dùng đang để cỡ bảng bao nhiêu.
"""
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.export_excel import (MAU_KET_LUAN, TEN_FILE, cau_truc, dong_trang_thai, mau_heat,
                              tieu_de_bao_cao)
from app.overview import bang_tong_quan

SCALE = 2                     # vẽ gấp đôi rồi giữ nguyên -> ảnh nét khi phóng to trên điện thoại
NEN = "#FFFFFF"
XANH_FPT = "#0072BC"
XANH_DAM = "#0B2E4F"
XAM_CHU = "#667789"
VIEN = "#D8DEE7"
NEN_COT = "#E9F1F9"
NEN_SUB = "#EDF3F9"
NEN_TOTAL = "#DCE8F4"
NEN_KHAC = "#FFF6EC"
CHU_SUB = "#C8372D"
CHU_TOTAL = "#003057"
CHU_KHAC = "#8A4B08"

CAO_NHOM, CAO_COT, CAO_DONG = 30, 38, 27
LE = 22
DEM_NGANG = 9                 # khoảng đệm trái/phải trong mỗi ô

# Ưu tiên font đi kèm app (assets/fonts) để ảnh giống nhau ở mọi nơi - máy chủ Vercel không có
# sẵn font tiếng Việt nào. Không có thì mới dùng font của máy (Windows / Linux).
FONT_DIRS = [Path(__file__).resolve().parent.parent / "assets" / "fonts",
             Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu")]
FONT_THUONG = ["BeVietnamPro-Regular.ttf", "segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"]
FONT_DAM = ["BeVietnamPro-SemiBold.ttf", "segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"]


def _font(dam: bool, co: int) -> ImageFont.FreeTypeFont:
    for ten in (FONT_DAM if dam else FONT_THUONG):
        for d in FONT_DIRS:
            f = d / ten
            if f.exists():
                return ImageFont.truetype(str(f), co * SCALE)
    return ImageFont.load_default(co * SCALE)


def _rong(draw: ImageDraw.ImageDraw, chu: str, font) -> int:
    return int(draw.textlength(chu or "", font=font))


def _so(v) -> str:
    if v is None or v == "":
        return ""
    try:
        return f"{int(round(float(v))):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(v)


def _pct(v) -> str:
    return "" if v is None else f"{round(float(v)):.0f}%"


def _o_chu(kieu: str, v) -> str:
    if kieu.startswith("pct"):
        return _pct(v)
    if kieu == "so":
        return _so(v)
    return "" if v is None else str(v)


def anh_tong_quan(thang: str, ngay: int | None = None,
                  chi_phong: list[str] | None = None, chi_nhanh: str = "all",
                  tam_tinh: bool = False, luc: datetime | None = None) -> tuple[bytes, str]:
    """Trả về (nội dung PNG, tên file) - toàn bộ bảng Báo cáo Tổng trong một ảnh."""
    df, ngay = bang_tong_quan(thang, ngay, chi_phong=chi_phong, chi_nhanh=chi_nhanh,
                              tam_tinh=tam_tinh)
    ct = cau_truc(thang, ngay)
    rows = df.to_dict("records")

    f_tieu_de = _font(True, 17)
    f_phu = _font(False, 10)
    f_nhom = _font(True, 10)
    f_cot = _font(True, 9)
    f_o = _font(False, 11)
    f_o_dam = _font(True, 11)

    do = ImageDraw.Draw(Image.new("RGB", (10, 10)))

    # ---- bề rộng từng cột: đủ chứa tiêu đề (2 dòng) lẫn giá trị dài nhất
    cols: list[tuple[str, str, str]] = [c for _, nhom in ct for c in nhom]
    rong: list[int] = []
    for ten_cot, khoa, kieu in cols:
        w = max(_rong(do, d, f_cot) for d in _chia_dong(ten_cot)) + DEM_NGANG * 2 * SCALE
        for r in rows:
            font = f_o_dam if r.get("loai_dong") != "data" else f_o
            w = max(w, _rong(do, _o_chu(kieu, r.get(khoa)), font) + DEM_NGANG * 2 * SCALE)
        rong.append(int(w) + 4 * SCALE)

    rong_bang = sum(rong)
    cao_tieu_de = 62 * SCALE
    cao = (cao_tieu_de + (CAO_NHOM + CAO_COT) * SCALE + len(rows) * CAO_DONG * SCALE
           + 26 * SCALE + LE * SCALE)
    img = Image.new("RGB", (rong_bang + LE * 2 * SCALE, cao), NEN)
    d = ImageDraw.Draw(img)

    x0, y = LE * SCALE, 14 * SCALE
    d.text((x0, y), tieu_de_bao_cao(thang, ngay, chi_nhanh), font=f_tieu_de, fill=XANH_DAM)
    y += 24 * SCALE
    trang_thai = dong_trang_thai(tam_tinh, luc)
    x_phu = x0
    if trang_thai:
        f_tt = f_nhom if tam_tinh else f_phu
        d.text((x_phu, y), trang_thai, font=f_tt, fill="#B45309" if tam_tinh else XAM_CHU)
        x_phu += _rong(d, trang_thai + "  ·  ", f_tt)
    d.text((x_phu, y), "FPT Telecom · Chi nhánh Đà Nẵng & Quảng Nam", font=f_phu, fill=XAM_CHU)
    y = cao_tieu_de

    # ---- hàng tiêu đề nhóm
    x = x0
    for ten_nhom, nhom in ct:
        w = sum(rong[len(_truoc(ct, ten_nhom)):len(_truoc(ct, ten_nhom)) + len(nhom)])
        if ten_nhom:
            d.rectangle([x, y, x + w, y + CAO_NHOM * SCALE], fill=XANH_FPT)
            _giua(d, x, y, w, CAO_NHOM * SCALE, ten_nhom, f_nhom, "#FFFFFF")
        x += w
    y += CAO_NHOM * SCALE

    # ---- hàng tên cột (xuống dòng khi dài)
    x = x0
    for i, (ten_cot, _, _) in enumerate(cols):
        d.rectangle([x, y, x + rong[i], y + CAO_COT * SCALE], fill=NEN_COT, outline=VIEN)
        _giua_nhieu_dong(d, x, y, rong[i], CAO_COT * SCALE, _chia_dong(ten_cot), f_cot, XANH_DAM)
        x += rong[i]
    y += CAO_COT * SCALE

    # ---- các dòng dữ liệu
    for r in rows:
        loai = r.get("loai_dong")
        nen_dong = {"subtotal": NEN_SUB, "total": NEN_TOTAL, "nhomkhac": NEN_KHAC}.get(loai)
        mau_chu = {"subtotal": CHU_SUB, "total": CHU_TOTAL, "nhomkhac": CHU_KHAC}.get(loai,
                                                                                      "#17212E")
        dam = loai != "data"
        x = x0
        for i, (_, khoa, kieu) in enumerate(cols):
            v = r.get(khoa)
            nen_o = nen_dong
            if kieu.startswith("pct") and v is not None:
                mau = mau_heat(kieu.split(":")[1], v)
                if mau:
                    nen_o = "#" + mau
            if khoa == "ket_luan" and v in MAU_KET_LUAN:
                nen_o = "#" + MAU_KET_LUAN[v]
            d.rectangle([x, y, x + rong[i], y + CAO_DONG * SCALE],
                        fill=nen_o or NEN, outline=VIEN)
            chu = _o_chu(kieu, v)
            font = f_o_dam if (dam or khoa == "phong") else f_o
            if khoa == "phong":
                d.text((x + DEM_NGANG * SCALE, y + 6 * SCALE), chu, font=font, fill=mau_chu)
            else:
                _giua(d, x, y, rong[i], CAO_DONG * SCALE, chu, font, mau_chu)
            x += rong[i]
        y += CAO_DONG * SCALE

    d.text((x0, y + 8 * SCALE),
           "Nguồn: hệ thống Sales & HR Dashboard · số liệu luỹ kế từ đầu tháng đến ngày báo cáo",
           font=f_phu, fill=XAM_CHU)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    ten = f"BaoCaoTong_{TEN_FILE.get(chi_nhanh, 'ToanCN')}_{thang.replace('-', '')}_ngay{ngay:02d}.png"
    return buf.getvalue(), ten


def _truoc(ct, ten_nhom: str) -> list:
    """Các cột đứng trước nhóm này - dùng để tính vị trí vẽ."""
    out = []
    for ten, nhom in ct:
        if ten == ten_nhom:
            break
        out += list(nhom)
    return out


def _chia_dong(ten: str) -> list[str]:
    """Tiêu đề dài thì tách 2 dòng cho khỏi phải kéo cột rộng ra."""
    tu = ten.split()
    if len(ten) <= 11 or len(tu) < 2:
        return [ten]
    giua = len(ten) // 2
    tot, vi_tri = None, 0
    for i in range(1, len(tu)):
        do_dai = len(" ".join(tu[:i]))
        if tot is None or abs(do_dai - giua) < tot:
            tot, vi_tri = abs(do_dai - giua), i
    return [" ".join(tu[:vi_tri]), " ".join(tu[vi_tri:])]


def _giua(d, x, y, w, h, chu, font, mau):
    if not chu:
        return
    tw = d.textlength(chu, font=font)
    d.text((x + (w - tw) / 2, y + (h - font.size) / 2 - 1 * SCALE), chu, font=font, fill=mau)


def _giua_nhieu_dong(d, x, y, w, h, dong: list[str], font, mau):
    cao_dong = font.size + 3 * SCALE
    bat_dau = y + (h - cao_dong * len(dong)) / 2
    for i, dg in enumerate(dong):
        tw = d.textlength(dg, font=font)
        d.text((x + (w - tw) / 2, bat_dau + i * cao_dong), dg, font=font, fill=mau)
