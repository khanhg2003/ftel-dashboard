"""Chụp ảnh báo cáo ra file PNG (vẽ thẳng bằng Pillow, không qua trình duyệt).

Vì sao không chụp màn hình bằng JavaScript: bảng trên giao diện chỉ dựng những cột
đang nhìn thấy, chụp ra sẽ thiếu. Vẽ ở máy chủ thì luôn đủ 100% dòng và cột, nét,
và không phụ thuộc người dùng đang để cỡ bảng bao nhiêu.

Ảnh được thiết kế để gửi nhóm Zalo và xem trên điện thoại:
- Font Be Vietnam Pro đi kèm app (assets/fonts) - máy chủ Vercel không có font tiếng Việt nào,
  dùng font hệ thống sẽ ra ô vuông thay cho chữ có dấu.
- Ô bảng sát chữ như bảng tính, chữ số đậm vừa: bảng kín khung, không thừa lề trắng.
- Tự chọn tỷ lệ vẽ để bề ngang ảnh luôn khoảng 2.400px: Zalo giữ nguyên độ nét ở mức này
  (ảnh rộng hơn sẽ bị Zalo thu nhỏ lại, chữ nhoè).
"""
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.export_excel import (MAU_KET_LUAN, TEN_FILE, cau_truc, dong_trang_thai, hau_to_ky, mau_heat,
                              mo_ta_ky, tieu_de_bao_cao)
from app.overview import LECH_GIO_VN, bang_tong_quan

RONG_MUC_TIEU = 2400          # bề ngang ảnh mong muốn (px)
TY_LE_MIN, TY_LE_MAX = 1.5, 3.0

NEN = "#FFFFFF"
XANH_FPT = "#0072BC"
XANH_DAM = "#0B2E4F"
XAM_CHU = "#5B6B7C"
VIEN = "#C5CFDA"
VIEN_DAM = "#8FA0B3"
NEN_COT = "#E3EEF8"
NEN_SUB = "#D5E3F1"
NEN_TOTAL = "#A9C6E3"
NEN_KHAC = "#FCE7CC"
NEN_CN = "#C3D8EC"
CHU_THUONG = "#141C26"
CHU_SUB = "#B01E14"
CHU_TOTAL = "#002B4E"
CHU_KHAC = "#8A4B08"

# kích thước ở tỷ lệ 1 (sẽ nhân với tỷ lệ vẽ)
CO_TIEU_DE, CO_PHU, CO_NHOM, CO_COT, CO_O = 21, 12, 12.5, 11.5, 13
CAO_NHOM, CAO_COT, CAO_DONG = 26, 40, 25
LE = 16
DEM = 7                       # đệm trái/phải trong ô


def gio_viet_nam() -> datetime:
    """Giờ Việt Nam - máy chủ Vercel chạy giờ UTC nên không dùng thẳng datetime.now()."""
    return datetime.utcnow() + LECH_GIO_VN


THU_MUC_FONT = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FONT_DU_PHONG = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu")]
FONT = {
    "thuong": ["BeVietnamPro-Regular.ttf", "segoeui.ttf", "DejaVuSans.ttf"],
    "vua": ["BeVietnamPro-Medium.ttf", "segoeui.ttf", "DejaVuSans.ttf"],
    "dam": ["BeVietnamPro-SemiBold.ttf", "segoeuisb.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf"],
    "rat_dam": ["BeVietnamPro-Bold.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf"],
}


def _duong_dan_font(kieu: str) -> Path:
    for ten in FONT[kieu]:
        for d in [THU_MUC_FONT, *FONT_DU_PHONG]:
            if (d / ten).exists():
                return d / ten
    raise FileNotFoundError(
        f"Thiếu font tiếng Việt cho ảnh PNG ({FONT[kieu][0]}) trong {THU_MUC_FONT}")


def _font(kieu: str, co: float, ty_le: float) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_duong_dan_font(kieu)), round(co * ty_le))


def _so(v) -> str:
    if v is None or v == "":
        return ""
    try:
        return f"{int(round(float(v))):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(v)


def _o_chu(kieu: str, v) -> str:
    if kieu.startswith("pct"):
        return "" if v is None else f"{round(float(v)):.0f}%"
    if kieu == "so":
        return _so(v)
    return "" if v is None else str(v)


def _chu_o(kieu: str, khoa: str, r: dict) -> str:
    """Chữ trong ô. PTTB CNQL ở dòng có `mttn_hien` kèm số MTTN trong ngoặc như trên web (`tongquan.SO_CNQL_MTTN`):
    "17 (24)" và "33% (47%)"."""
    chu = _o_chu(kieu, r.get(khoa))
    if chu and r.get("mttn_hien"):
        if khoa == "cnql" and r.get("mttn") is not None:
            chu += f" ({_so(r['mttn'])})"
        elif khoa == "cnql_ty_le" and r.get("mttn_ty_le") is not None:
            chu += f" ({round(float(r['mttn_ty_le']))}%)"
    return chu


def _gia_tri_mau(khoa: str, r: dict):
    """Số dùng để tô màu: tỷ lệ CNQL ở dòng có MTTN tô theo số MTTN, giống web (`tongquan._GIA_TRI_HEAT_CNQL`)."""
    if khoa == "cnql_ty_le" and r.get("mttn_hien") and r.get("mttn_ty_le") is not None:
        return r["mttn_ty_le"]
    return r.get(khoa)


def _chia_dong(ten: str) -> list[str]:
    """Tiêu đề dài thì tách 2 dòng cho khỏi phải kéo cột rộng ra."""
    tu = ten.split()
    if len(ten) <= 9 or len(tu) < 2:
        return [ten]
    giua = len(ten) / 2
    vi_tri = min(range(1, len(tu)), key=lambda i: abs(len(" ".join(tu[:i])) - giua))
    return [" ".join(tu[:vi_tri]), " ".join(tu[vi_tri:])]


class _Bo:
    """Bộ font + kích thước đã nhân tỷ lệ."""

    def __init__(self, ty_le: float):
        self.k = ty_le
        self.tieu_de = _font("rat_dam", CO_TIEU_DE, ty_le)
        self.phu = _font("thuong", CO_PHU, ty_le)
        self.phu_dam = _font("dam", CO_PHU, ty_le)
        self.nhom = _font("rat_dam", CO_NHOM, ty_le)
        self.cot = _font("dam", CO_COT, ty_le)
        self.o = _font("vua", CO_O, ty_le)
        self.o_dam = _font("rat_dam", CO_O, ty_le)

    def px(self, x: float) -> int:
        return round(x * self.k)


def _do_rong_cot(cols, rows, bo: _Bo) -> list[int]:
    do = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    rong = []
    for ten_cot, khoa, kieu in cols:
        w = max(do.textlength(d, font=bo.cot) for d in _chia_dong(ten_cot))
        for r in rows:
            font = bo.o if r.get("loai_dong") == "data" and khoa != "phong" else bo.o_dam
            w = max(w, do.textlength(_chu_o(kieu, khoa, r), font=font))
        rong.append(int(w) + bo.px(DEM * 2))
    return rong


def _noi_rong_theo_nhom(ct, rong: list[int], bo: _Bo) -> None:
    """Tên nhóm dài hơn tổng các cột bên dưới (VD "TĂNG TRƯỞNG" trên 2 cột số) thì chia đều
    phần thiếu cho các cột trong nhóm, để chữ không chạm mép ô."""
    do = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    i = 0
    for ten_nhom, nhom in ct:
        n = len(nhom)
        thieu = do.textlength(ten_nhom, font=bo.nhom) + bo.px(DEM * 3) - sum(rong[i:i + n])
        if ten_nhom and thieu > 0:
            for j in range(i, i + n):
                rong[j] += int(thieu / n) + 1
        i += n


def anh_tong_quan(thang: str, ngay: int | None = None,
                  chi_phong: list[str] | None = None, chi_nhanh: str = "all",
                  tam_tinh: bool = False, luc: datetime | None = None,
                  tu: str | None = None, nhan_xet: tuple[str, str] | None = None) -> tuple[bytes, str]:
    """Trả về (nội dung PNG, tên file) - toàn bộ bảng Báo cáo Tổng trong một ảnh.

    `nhan_xet` = (tiêu đề, nội dung) của trợ lý AI, in thành khối ngắn dưới bảng.
    """
    df, ngay = bang_tong_quan(thang, ngay, chi_phong=chi_phong, chi_nhanh=chi_nhanh,
                              tam_tinh=tam_tinh, tu=tu)
    ct = cau_truc(thang, ngay, tu)
    cols: list[tuple[str, str, str]] = [c for _, nhom in ct for c in nhom]
    rows = df.to_dict("records")

    # đo ở tỷ lệ 1 để chọn tỷ lệ vẽ, rồi đo lại chính xác ở tỷ lệ đã chọn
    rong_goc = sum(_do_rong_cot(cols, rows, _Bo(1))) + LE * 2
    ty_le = max(TY_LE_MIN, min(TY_LE_MAX, RONG_MUC_TIEU / rong_goc))
    bo = _Bo(ty_le)
    rong = _do_rong_cot(cols, rows, bo)
    _noi_rong_theo_nhom(ct, rong, bo)

    rong_bang = sum(rong)
    le = bo.px(LE)
    cao_dau = bo.px(62)
    dong_nx = _dong_nhan_xet(nhan_xet[1], bo.o, rong_bang - bo.px(2 * DEM)) if nhan_xet else []
    cao_nx = (bo.px(40) + len(dong_nx) * bo.px(CO_O * 1.6) + bo.px(14)) if dong_nx else 0
    cao = (cao_dau + bo.px(CAO_NHOM + CAO_COT) + len(rows) * bo.px(CAO_DONG)
           + bo.px(30) + cao_nx + le)
    img = Image.new("RGB", (rong_bang + le * 2, cao), NEN)
    d = ImageDraw.Draw(img)

    # ---- tiêu đề + trạng thái số liệu
    x0 = le
    d.text((x0, bo.px(12)), tieu_de_bao_cao(thang, ngay, chi_nhanh, tu), font=bo.tieu_de,
           fill=XANH_DAM)
    y_phu = bo.px(42)
    trang_thai = dong_trang_thai(tam_tinh, luc)
    x = x0
    if trang_thai:
        f_tt = bo.phu_dam if tam_tinh else bo.phu
        d.text((x, y_phu), trang_thai, font=f_tt, fill="#B45309" if tam_tinh else XAM_CHU)
        x += d.textlength(trang_thai + "   ·   ", font=f_tt)
    d.text((x, y_phu), "FPT Telecom · Chi nhánh Đà Nẵng & Quảng Nam", font=bo.phu, fill=XAM_CHU)
    y = cao_dau

    # ---- hàng tiêu đề nhóm (ô trống ở cột PKD/Nhân sự được gộp với hàng tên cột)
    x, i = x0, 0
    for ten_nhom, nhom in ct:
        w = sum(rong[i:i + len(nhom)])
        if ten_nhom:
            d.rectangle([x, y, x + w, y + bo.px(CAO_NHOM)], fill=XANH_FPT, outline="#FFFFFF",
                        width=max(1, bo.px(1)))
            _giua(d, x, y, w, bo.px(CAO_NHOM), ten_nhom, bo.nhom, "#FFFFFF")
        i += len(nhom)
        x += w
    y_cot = y + bo.px(CAO_NHOM)

    # ---- hàng tên cột
    x = x0
    so_cot_khong_nhom = len(ct[0][1]) if not ct[0][0] else 0
    for i, (ten_cot, _, _) in enumerate(cols):
        tren = y if i < so_cot_khong_nhom else y_cot
        d.rectangle([x, tren, x + rong[i], y_cot + bo.px(CAO_COT)], fill=NEN_COT, outline=VIEN)
        _giua_nhieu_dong(d, x, tren, rong[i], y_cot + bo.px(CAO_COT) - tren,
                         _chia_dong(ten_cot), bo.cot, XANH_DAM)
        x += rong[i]
    y = y_cot + bo.px(CAO_COT)

    # ---- các dòng dữ liệu
    h = bo.px(CAO_DONG)
    for r in rows:
        loai = r.get("loai_dong")
        nen_dong = {"subtotal": NEN_SUB, "total": NEN_TOTAL, "nhomkhac": NEN_KHAC,
                    "chinhanh": NEN_CN}.get(loai)
        mau_chu = {"subtotal": CHU_SUB, "total": CHU_TOTAL, "nhomkhac": CHU_KHAC,
                   "chinhanh": CHU_TOTAL}.get(
            loai, CHU_THUONG)
        x = x0
        for i, (_, khoa, kieu) in enumerate(cols):
            v = r.get(khoa)
            nen_o = nen_dong
            vm = _gia_tri_mau(khoa, r)
            if kieu.startswith("pct") and vm is not None:
                mau = mau_heat(kieu.split(":")[1], vm)
                nen_o = "#" + mau if mau else nen_o
            if khoa == "ket_luan" and v in MAU_KET_LUAN:
                nen_o = "#" + MAU_KET_LUAN[v]
            d.rectangle([x, y, x + rong[i], y + h], fill=nen_o or NEN, outline=VIEN)
            chu = _chu_o(kieu, khoa, r)
            font = bo.o_dam if (loai != "data" or khoa == "phong") else bo.o
            if khoa == "phong":
                _giua(d, x, y, rong[i], h, chu, font, mau_chu, trai=bo.px(DEM))
            else:
                _giua(d, x, y, rong[i], h, chu, font, mau_chu)
            x += rong[i]
        if loai in ("subtotal", "total", "chinhanh"):   # kẻ đậm ngăn cách từng bầy như bảng tính
            d.line([x0, y + h, x0 + rong_bang, y + h], fill=VIEN_DAM, width=max(2, bo.px(1.5)))
        y += h

    # đường dọc đậm giữa các khối cột (INTERNET, TĂNG TRƯỞNG, FPT PLAY...) như trên web
    x, i = x0, 0
    for ten_nhom, nhom in ct:
        if i:
            d.line([x, cao_dau, x, y], fill=VIEN_DAM, width=max(2, bo.px(1.5)))
        x += sum(rong[i:i + len(nhom)])
        i += len(nhom)
    d.rectangle([x0, cao_dau, x0 + rong_bang, y], outline=VIEN_DAM, width=max(2, bo.px(1.2)))
    d.text((x0, y + bo.px(9)),
           f"Nguồn: Sales & HR Dashboard · {mo_ta_ky(thang, ngay, tu)}"
           f" · xuất lúc {gio_viet_nam():%H:%M %d/%m/%Y}", font=bo.phu, fill=XAM_CHU)
    if dong_nx:
        y_nx = y + bo.px(40)
        d.rounded_rectangle([x0, y_nx - bo.px(6), x0 + rong_bang, y_nx + cao_nx - bo.px(40)],
                            radius=bo.px(6), fill="#F1F7FD", outline="#CFE1F2")
        d.text((x0 + bo.px(DEM), y_nx), nhan_xet[0] + " (trợ lý AI)", font=bo.phu_dam, fill=XANH_FPT)
        for i, dong in enumerate(dong_nx, start=1):
            d.text((x0 + bo.px(DEM), y_nx + i * bo.px(CO_O * 1.6)), dong, font=bo.o, fill=CHU_THUONG)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    ten = f"BaoCaoTong_{TEN_FILE.get(chi_nhanh, 'ToanCN')}_{hau_to_ky(thang, ngay, tu)}.png"
    return buf.getvalue(), ten


def _dong_nhan_xet(noi_dung: str, font, rong: int) -> list[str]:
    """Bỏ ký hiệu markdown, ngắt dòng vừa bề ngang ảnh."""
    do = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    ra: list[str] = []
    for goc in noi_dung.replace("**", "").replace("__", "").splitlines():
        goc = goc.strip().lstrip("-*• ").strip()
        if not goc:
            continue
        dong = "•"
        for tu in goc.split():
            if do.textlength(f"{dong} {tu}", font=font) > rong:
                ra.append(dong)
                dong = "  " + tu
            else:
                dong = f"{dong} {tu}"
        ra.append(dong)
    return ra[:12]


def _giua(d, x, y, w, h, chu, font, mau, trai: int | None = None):
    """Viết chữ căn giữa ô. Căn theo chiều cao chữ số "0" cho mọi ô để các ô cùng hàng
    thẳng dòng với nhau (căn theo từng chữ thì chữ có dấu sẽ lệch lên xuống)."""
    if not chu:
        return
    l, _, r, _ = d.textbbox((0, 0), chu, font=font)
    _, t, _, b = d.textbbox((0, 0), "0", font=font)
    ty = y + (h - (b - t)) / 2 - t
    tx = x + trai if trai is not None else x + (w - (r - l)) / 2 - l
    d.text((tx, ty), chu, font=font, fill=mau)


def _giua_nhieu_dong(d, x, y, w, h, dong: list[str], font, mau):
    _, t, _, b = d.textbbox((0, 0), "ĐÂgy", font=font)
    cao_dong = (b - t) * 1.25
    bat_dau = y + (h - cao_dong * len(dong)) / 2 + (cao_dong - (b - t)) / 2 - t
    for i, dg in enumerate(dong):
        tw = d.textlength(dg, font=font)
        d.text((x + (w - tw) / 2, bat_dau + i * cao_dong), dg, font=font, fill=mau)
