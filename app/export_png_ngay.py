"""Ảnh báo cáo đầu ngày (PNG) để gửi nhóm Zalo - vẽ thẳng bằng Pillow như `export_png.py`.

Bố cục theo mẫu chủ app đưa (24/09/2026): dải tiêu đề -> ba khối số (kết quả hôm qua · tình hình
sáng nay · luỹ kế tháng, có vòng tròn tỷ lệ) -> bảng chỉ số toàn bộ nhân sự -> ba khối chữ
(trọng tâm · đánh giá · thông điệp). Số lấy thẳng từ `bao_cao_ngay`, chữ lấy từ phần Trưởng phòng
đã duyệt, nên ảnh luôn khớp những gì đang thấy trên trang.
"""
from __future__ import annotations

import io
from datetime import date

from PIL import Image, ImageDraw

from app import bao_cao_ngay as bc
from app.export_png import _font, _giua, _so
from app.org import phong_order

RONG = 1240                       # bề ngang khi vẽ ở tỷ lệ 1
TY_LE = 2.0                       # ảnh ra ~2.480px: Zalo giữ nguyên độ nét ở mức này

NAVY = "#0B2E4F"
NAVY_NHAT = "#14416E"
CAM = "#F26522"
TRANG = "#FFFFFF"
NEN = "#EEF3F8"
VIEN = "#C9D8E6"
CHU = "#14212E"
CHU_NHAT = "#5B7287"
XANH = "#0A7A3E"
DO = "#B42318"
VANG = "#8A5A00"
NEN_SOC = "#F6F9FC"

LE = 18
KHE = 12


def _k(v: float) -> int:
    return round(v * TY_LE)


def _hop(d, x, y, w, h, nen=TRANG, vien=VIEN, bo=8):
    d.rounded_rectangle([_k(x), _k(y), _k(x + w), _k(y + h)], radius=_k(bo), fill=nen,
                        outline=vien, width=max(1, _k(1)))


def _nhan(d, x, y, w, chu, f, mau=CHU, trai=0):
    d.text((_k(x + trai), _k(y)), chu, font=f, fill=mau)


def _phai(d, x_phai, y, chu, f, mau=CHU):
    d.text((_k(x_phai) - d.textlength(chu, font=f), _k(y)), chu, font=f, fill=mau)


def _cat(d, chu: str, f, rong_px: int) -> str:
    if d.textlength(chu, font=f) <= rong_px:
        return chu
    while chu and d.textlength(chu + "…", font=f) > rong_px:
        chu = chu[:-1]
    return chu + "…"


def _xuong_dong(d, chu: str, f, rong_px: int, toi_da: int) -> list[str]:
    ra, dong = [], ""
    for tu in str(chu or "").split():
        thu = f"{dong} {tu}".strip()
        if d.textlength(thu, font=f) <= rong_px or not dong:
            dong = thu
        else:
            ra.append(dong)
            dong = tu
        if len(ra) == toi_da:
            return ra
    if dong:
        ra.append(dong)
    return ra[:toi_da]


def _dong_chu(chu: str) -> list[str]:
    return [x.strip(" -•*\t") for x in str(chu or "").splitlines() if x.strip(" -•*\t")]


# ------------------------------------------------------------------ các khối
def _dai_tieu_de(d, ten_phong: str, ngay: date, y: int) -> int:
    cao = 78
    d.rectangle([0, 0, _k(RONG), _k(y + cao)], fill=NAVY)
    d.rectangle([0, _k(y + cao) - _k(4), _k(RONG), _k(y + cao)], fill=CAM)
    f1, f2 = _font("rat_dam", 30, TY_LE), _font("thuong", 13, TY_LE)
    t = f"BÁO CÁO ĐẦU NGÀY {ngay:%d/%m}"
    _giua(d, 0, _k(y + 12), _k(RONG), _k(38), t, f1, TRANG)
    _giua(d, 0, _k(y + 52), _k(RONG), _k(18), f"{ten_phong} · tình hình hôm nay & chỉ số toàn bộ nhân sự",
          f2, "#9FC0DA")
    return y + cao + KHE


def _dau_khoi(d, x, y, w, so: str, ten: str):
    d.rounded_rectangle([_k(x), _k(y), _k(x + w), _k(y + 30)], radius=_k(8), fill=NAVY)
    d.rectangle([_k(x), _k(y + 16), _k(x + w), _k(y + 30)], fill=NAVY)
    d.rounded_rectangle([_k(x + 8), _k(y + 6), _k(x + 26), _k(y + 24)], radius=_k(4), fill=CAM)
    _giua(d, _k(x + 8), _k(y + 6), _k(18), _k(18), so, _font("rat_dam", 12, TY_LE), TRANG)
    _nhan(d, x + 34, y + 8, w, ten, _font("rat_dam", 14, TY_LE), TRANG)


def _dong_so(d, x, y, w, nhan: str, gia_tri: str, mau=CHU):
    f, fs = _font("thuong", 13, TY_LE), _font("rat_dam", 15, TY_LE)
    _nhan(d, x, y, w, nhan, f, CHU_NHAT)
    _phai(d, x + w, y - 1, gia_tri, fs, mau)


def _vong_tron(d, cx, cy, r, pct: float):
    """Vòng tròn tỷ lệ hoàn thành - phần đã đạt màu cam, phần còn lại xám nhạt."""
    hop = [_k(cx - r), _k(cy - r), _k(cx + r), _k(cy + r)]
    d.ellipse(hop, fill="#DCE6F0")
    if pct > 0:
        d.pieslice(hop, -90, -90 + min(pct, 100) * 3.6, fill=CAM)
    trong = _k(r * 0.74)
    d.ellipse([_k(cx) - trong, _k(cy) - trong, _k(cx) + trong, _k(cy) + trong], fill=TRANG)
    _giua(d, _k(cx - r), _k(cy - 13), _k(r * 2), _k(16), f"{pct:g}%", _font("rat_dam", 14, TY_LE), NAVY)
    _giua(d, _k(cx - r), _k(cy + 2), _k(r * 2), _k(11), "hoàn thành", _font("thuong", 8.5, TY_LE), CHU_NHAT)


def _ba_khoi(d, t: dict, y: int) -> int:
    cao, w = 156, (RONG - LE * 2 - KHE * 2) / 3
    for i, x in enumerate([LE + (w + KHE) * i for i in range(3)]):
        _hop(d, x, y, w, cao)
        _dau_khoi(d, x, y, w, str(i + 1), [f"KẾT QUẢ NGÀY {t['hom_qua']:%d/%m}",
                                           f"TÌNH HÌNH SÁNG {t['ngay']:%d/%m}", "LUỸ KẾ THÁNG"][i])
    x1, x2, x3 = [LE + (w + KHE) * i for i in range(3)]
    dx, dw, y0 = 12, w - 24, y + 42

    ty = t["hq_ty_le"]
    for i, (nhan, gt, mau) in enumerate([
            ("Kết quả thực tế", f"{_so(t['hq_thuc_te'])} PTTB", CHU),
            ("Mục tiêu ngày", f"{_so(t['hq_muc_tieu'])} PTTB", CHU),
            ("Thiếu mục tiêu", f"{_so(t['hq_thieu'])} PTTB", DO if t["hq_thieu"] else XANH),
            ("Tỷ lệ đạt", f"{ty}%", XANH if ty >= 100 else VANG if ty >= 80 else DO)]):
        _dong_so(d, x1 + dx, y0 + i * 26, dw, nhan, gt, mau)

    for i, (nhan, gt, mau) in enumerate([
            ("KHTN hiện có", _so(t["khtn"]), CHU),
            ("Mục tiêu PTTB/ngày", _so(t["mt_ngay"]), CHU),
            ("Dự kiến ONL sáng · chiều", f"{_so(t['onl_sang'])} · {_so(t['onl_chieu'])}", CHU),
            ("Tổng dự kiến online", _so(t["dk_onl"]), NAVY),
            ("Đã online", _so(t["da_online"]), XANH if t["da_online"] else CHU),
            ("Còn phải online", _so(t["con_phai_onl"]), VANG if t["con_phai_onl"] else XANH)]):
        _dong_so(d, x2 + dx, y0 - 6 + i * 20, dw, nhan, gt, mau)

    rw = 92
    for i, (nhan, gt, mau) in enumerate([
            ("PTTB luỹ kế", _so(t["luy_ke"]), CHU),
            ("Mục tiêu tháng", _so(t["mt_thang"]), CHU),
            ("Còn thiếu", _so(t["con_thieu"]), DO if t["con_thieu"] else XANH),
            ("Tỷ lệ hoàn thành", f"{t['ty_le_thang']:g}%", XANH if t["ty_le_thang"] >= 90 else VANG)]):
        _dong_so(d, x3 + dx, y0 + i * 26, dw - rw, nhan, gt, mau)
    _vong_tron(d, x3 + w - 12 - 40, y + cao / 2 + 16, 40, t["ty_le_thang"])
    return y + cao + KHE


COT = [("Nhân sự", "ho_ten", 168), ("MT ngày", "muc_tieu", 78), ("KHTN", "khtn", 70),
       ("ONL sáng", "onl_sang", 84), ("ONL chiều", "onl_chieu", 88), ("DK ONL", "dk_onl", 78),
       ("Đã ONL", "thuc_hien", 78), ("PTTB tháng", "pttb_thang", 104), ("V.VIP", "vvip_thang", 74)]


def _bang(d, df, y: int, mt_thang_phong: int) -> int:
    w = RONG - LE * 2
    rong = [c[2] for c in COT]
    rong[0] += w - sum(rong)                      # cột tên co giãn cho vừa bề ngang
    cao_dau, cao_dong = 30, 25
    d.rounded_rectangle([_k(LE), _k(y), _k(LE + w), _k(y + 28)], radius=_k(8), fill=NAVY)
    d.rectangle([_k(LE), _k(y + 14), _k(LE + w), _k(y + 28)], fill=NAVY)
    _giua(d, _k(LE), _k(y + 7), _k(w), _k(16), "BẢNG CHỈ SỐ TOÀN BỘ NHÂN SỰ",
          _font("rat_dam", 14, TY_LE), TRANG)
    y += 28

    f_cot, f_o, f_dam = _font("dam", 11, TY_LE), _font("vua", 11.5, TY_LE), _font("rat_dam", 11.5, TY_LE)
    d.rectangle([_k(LE), _k(y), _k(LE + w), _k(y + cao_dau)], fill="#DCE8F3")
    x = LE
    for (ten, khoa, _), rw in zip(COT, rong):
        _giua(d, _k(x), _k(y), _k(rw), _k(cao_dau), ten, f_cot, NAVY,
              trai=_k(10) if khoa == "ho_ten" else None)
        x += rw
    y += cao_dau

    for i, r in enumerate(df.itertuples()):
        if i % 2:
            d.rectangle([_k(LE), _k(y), _k(LE + w), _k(y + cao_dong)], fill=NEN_SOC)
        x = LE
        for (_, khoa, _), rw in zip(COT, rong):
            if khoa == "ho_ten":
                _giua(d, _k(x), _k(y), _k(rw), _k(cao_dong),
                      _cat(d, str(r.ho_ten), f_dam, _k(rw - 16)), f_dam, CHU, trai=_k(10))
            elif khoa == "pttb_thang":
                _giua(d, _k(x), _k(y), _k(rw), _k(cao_dong),
                      f"{_so(r.pttb_thang)}/{_so(r.mt_thang)}" if r.mt_thang else _so(r.pttb_thang),
                      f_dam, CHU)
            else:
                v = getattr(r, khoa)
                _giua(d, _k(x), _k(y), _k(rw), _k(cao_dong), _so(v), f_o, CHU if v else CHU_NHAT)
            x += rw
        d.line([_k(LE), _k(y + cao_dong), _k(LE + w), _k(y + cao_dong)], fill="#E4ECF4", width=1)
        y += cao_dong

    d.rectangle([_k(LE), _k(y), _k(LE + w), _k(y + cao_dong + 2)], fill=CAM)
    x = LE
    tong = {k: int(df[k].sum()) for _, k, _ in COT if k != "ho_ten"}
    for (_, khoa, _), rw in zip(COT, rong):
        # dòng TỔNG lấy mục tiêu tháng CỦA PHÒNG, không cộng mục tiêu từng người: hai số này có thể
        # khác nhau, mà khối 3 phía trên đã ghi mục tiêu phòng - trong một ảnh phải thống nhất một số
        chu = "TỔNG" if khoa == "ho_ten" else (
            f"{_so(tong['pttb_thang'])}/{_so(mt_thang_phong)}" if khoa == "pttb_thang" and mt_thang_phong
            else _so(tong[khoa]))
        _giua(d, _k(x), _k(y), _k(rw), _k(cao_dong + 2), chu, f_dam, TRANG,
              trai=_k(10) if khoa == "ho_ten" else None)
        x += rw
    return y + cao_dong + 2 + KHE


def _cao_khoi_chu(d, chu: dict) -> int:
    """Chiều cao vừa đủ cho khối chữ dài nhất - khối rỗng vẫn giữ mức tối thiểu cho cân đối."""
    w = (RONG - LE * 2 - KHE * 2) / 3
    f, f_trich = _font("thuong", 11.5, TY_LE), _font("vua", 12.5, TY_LE)
    can = [len(_xuong_dong(d, chu["thong_diep"], f_trich, _k(w - 30), 8)) * 18]
    for khoa in ("trong_tam", "nhan_dinh"):
        n = sum(len(_xuong_dong(d, m, f, _k(w - 42), 3)) * 16 + 5 for m in _dong_chu(chu[khoa])[:5])
        can.append(n)
    return max(110, min(max(can) + 44, 320))


def _khoi_chu(d, chu: dict, y: int, cao: int) -> int:
    w = (RONG - LE * 2 - KHE * 2) / 3
    muc = [("TRỌNG TÂM HÔM NAY", _dong_chu(chu["trong_tam"]), "cham"),
           ("ĐÁNH GIÁ & NHẬN ĐỊNH", _dong_chu(chu["nhan_dinh"]), "so"),
           ("THÔNG ĐIỆP NGÀY MỚI", [chu["thong_diep"]] if chu["thong_diep"] else [], "trich")]
    f_dau, f = _font("rat_dam", 12.5, TY_LE), _font("thuong", 11.5, TY_LE)
    f_trich = _font("vua", 12.5, TY_LE)
    for i, (ten, dong, kieu) in enumerate(muc):
        x = LE + (w + KHE) * i
        _hop(d, x, y, w, cao, nen=TRANG)
        d.rounded_rectangle([_k(x), _k(y), _k(x + w), _k(y + 26)], radius=_k(8), fill=NAVY_NHAT)
        d.rectangle([_k(x), _k(y + 14), _k(x + w), _k(y + 26)], fill=NAVY_NHAT)
        _nhan(d, x + 12, y + 6, w, ten, f_dau, TRANG)
        yy, rw = y + 34, _k(w - 42)
        if not dong:
            _nhan(d, x + 12, yy, w, "(Chưa có nội dung)", f, CHU_NHAT)
            continue
        if kieu == "trich":
            for j, l in enumerate(_xuong_dong(d, dong[0], f_trich, _k(w - 30), 8)):
                _nhan(d, x + 15, yy + j * 18, w, l, f_trich, CHU)
            continue
        for j, muc_chu in enumerate(dong[:5]):
            dd = _xuong_dong(d, muc_chu, f, rw, 3)
            if kieu == "so":
                d.ellipse([_k(x + 12), _k(yy + 1), _k(x + 26), _k(yy + 15)], fill=CAM)
                _giua(d, _k(x + 12), _k(yy + 1), _k(14), _k(14), str(j + 1),
                      _font("rat_dam", 9, TY_LE), TRANG)
            else:
                d.ellipse([_k(x + 14), _k(yy + 5), _k(x + 22), _k(yy + 13)], fill=CAM)
            for k, l in enumerate(dd):
                _nhan(d, x + 32, yy + k * 16, w, l, f, CHU)
            yy += 16 * len(dd) + 5
            if yy > y + cao - 18:
                break
    return y + cao + KHE


# ------------------------------------------------------------------ vẽ cả ảnh
def anh_bao_cao_ngay(phong_code: str, ngay: date | None = None) -> bytes:
    ngay = ngay or bc.hom_nay()
    df = bc.bang([phong_code], ngay)
    t = bc.tom_tat([phong_code], ngay)
    ten_phong = {p["code"]: p["ten"] for p in phong_order()}.get(phong_code, phong_code)
    cao = 78 + KHE + 156 + KHE + 28 + 30 + 25 * max(len(df), 1) + 27 + KHE + 320 + KHE + 30
    img = Image.new("RGB", (_k(RONG), _k(cao)), NEN)
    d = ImageDraw.Draw(img)

    y = _dai_tieu_de(d, ten_phong, ngay, 0)
    y = _ba_khoi(d, t, y)
    if not df.empty:
        y = _bang(d, df, y, t["mt_thang"])
    chu = bc.chu(phong_code, ngay)
    y = _khoi_chu(d, chu, y, _cao_khoi_chu(d, chu))
    _giua(d, _k(LE), _k(y), _k(RONG - LE * 2), _k(16),
          f"Nguồn: file Internet đã nạp + phần sale nhập trên app · {ngay:%d/%m/%Y}",
          _font("thuong", 10, TY_LE), CHU_NHAT)

    ra = io.BytesIO()
    img.crop((0, 0, _k(RONG), min(_k(y + 26), img.height))).save(ra, "PNG", optimize=True)
    return ra.getvalue()
