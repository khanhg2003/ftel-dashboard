"""Ảnh báo cáo đầu ngày (PNG) để gửi nhóm Zalo - vẽ thẳng bằng Pillow như `export_png.py`.

Bố cục, màu và hoạ tiết theo đúng mẫu chủ app đưa (24/09/2026): nền xanh đậm có vệt chéo và tia sét,
góc cam; ba khối số (mỗi dòng một biểu tượng tròn), bảng chỉ số toàn bộ nhân sự với dòng TỔNG nền cam,
ba khối chữ (trọng tâm · đánh giá · thông điệp) và dải nguồn số liệu cuối ảnh.

Font Be Vietnam Pro đi kèm app không có bản nghiêng, nên chữ nghiêng trong mẫu được làm bằng cách
kéo xiên (`_nghieng`) - nhìn giống bản nghiêng thật ở cỡ chữ này.
"""
from __future__ import annotations

import io
from datetime import date

from PIL import Image, ImageDraw

from app import bao_cao_ngay as bc
from app.export_png import _font, _so
from app.org import phong_order

RONG = 1456                       # bề ngang khi vẽ ở tỷ lệ 1 (đúng khung mẫu)
TY_LE = 1.7                       # ảnh ra ~2.475px: Zalo giữ nguyên độ nét ở mức này

NEN_1 = (13, 42, 92)              # xanh đậm góc dưới
NEN_2 = (24, 74, 150)             # xanh sáng hơn phía trên
NAVY = "#122A52"
CAM = "#F0641E"
CAM_NHAT = "#F7CDB4"
KEM = "#FFF8F0"
TRANG = "#FFFFFF"
CHU = "#14212E"
CHU_NHAT = "#5B7287"
XANH_LA = "#1E9E52"
DO = "#E03A2F"
XAM_VONG = "#D5DEE8"

LE = 18
KHE = 12
CAO_DONG = 30


def _k(v: float) -> int:
    return round(v * TY_LE)


# ------------------------------------------------------------------ chữ
def _nghieng(img, x, y, chu, f, mau, goc: float = 0.2) -> int:
    """Chữ nghiêng giả (font đi kèm app không có bản nghiêng). Trả về bề ngang đã vẽ."""
    if not chu:
        return 0
    w = int(ImageDraw.Draw(img).textlength(chu, font=f)) + 6
    h = int(f.size * 1.6)
    lop = Image.new("RGBA", (w + int(h * goc), h), (0, 0, 0, 0))
    ImageDraw.Draw(lop).text((0, 0), chu, font=f, fill=mau)
    lop = lop.transform(lop.size, Image.AFFINE, (1, goc, -goc * h, 0, 1, 0), resample=Image.BICUBIC)
    img.alpha_composite(lop, (int(x), int(y)))
    return lop.width


def _giua(d, x, y, w, h, chu, f, mau, trai: int | None = None):
    """Căn giữa ô theo chiều cao chữ số "0" để các ô cùng hàng thẳng dòng."""
    if not chu:
        return
    l, _, r, _ = d.textbbox((0, 0), chu, font=f)
    _, t, _, b = d.textbbox((0, 0), "0", font=f)
    tx = x + trai if trai is not None else x + (w - (r - l)) / 2 - l
    d.text((tx, y + (h - (b - t)) / 2 - t), chu, font=f, fill=mau)


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


# ------------------------------------------------------------------ hoạ tiết nền
def _nen(img):
    """Nền chuyển màu xanh + vệt chéo sáng phía trên phải, hai góc cam như mẫu."""
    w, h = img.size
    nen = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(nen)
    for i in range(h):
        t = i / h
        d.line([(0, i), (w, i)], fill=tuple(round(NEN_2[c] + (NEN_1[c] - NEN_2[c]) * t) for c in range(3)))
    v = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dv = ImageDraw.Draw(v)
    cao = h * 0.11
    for x0, rong, mo in ((0.62, 0.15, 34), (0.76, 0.09, 26), (0.87, 0.12, 40)):
        x = w * x0
        dv.polygon([(x, 0), (x + w * rong, 0), (x + w * rong - cao, cao), (x - cao, cao)],
                   fill=(130, 195, 255, mo))
    dv.polygon([(0, 0), (w * .08, 0), (0, cao)], fill=(240, 100, 30, 255))
    dv.polygon([(w, 0), (w, cao * .8), (w * .945, 0)], fill=(240, 100, 30, 255))
    nen.paste(v, (0, 0), v)
    img.paste(nen.convert("RGBA"), (0, 0))


def _tia_set(d, x, y, cao, mau):
    c = cao
    d.polygon([(x + c * .52, y), (x + c * .12, y + c * .55), (x + c * .40, y + c * .55),
               (x + c * .16, y + c), (x + c * .70, y + c * .40), (x + c * .40, y + c * .40),
               (x + c * .78, y)], fill=mau)


def _bia(d, x, y, r):
    """Bia bắn cung ở góc trái tiêu đề."""
    for i, mau in enumerate((TRANG, CAM, TRANG, CAM)):
        rr = r * (1 - i * 0.23)
        d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=mau)
    d.line([(x - r * 1.6, y + r * 1.6), (x + r * .25, y - r * .25)], fill=TRANG, width=max(2, _k(2.5)))


def _cham_tron(d, x, y, w, h, buoc, mau):
    for i in range(int(w / buoc) + 1):
        for j in range(int(h / buoc) + 1):
            d.ellipse([x + i * buoc, y + j * buoc, x + i * buoc + buoc * .34, y + j * buoc + buoc * .34],
                      fill=mau)


# ------------------------------------------------------------------ biểu tượng tròn
def _bt(d, cx, cy, r, ten: str, nen=NAVY, mau=TRANG):
    """Biểu tượng nhỏ trong vòng tròn - vẽ bằng hình đơn giản cho nhẹ và luôn nét."""
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=nen)
    s, n = r * 0.52, max(1, round(r * 0.13))
    if ten == "cot":
        for i, c in enumerate((0.45, 0.95, 0.7)):
            d.rectangle([cx - s + i * s * .72, cy + s - 2 * s * c * .7, cx - s + i * s * .72 + s * .45,
                         cy + s], fill=mau)
    elif ten == "bia":
        d.ellipse([cx - s, cy - s, cx + s, cy + s], outline=mau, width=n)
        d.ellipse([cx - s * .32, cy - s * .32, cx + s * .32, cy + s * .32], fill=mau)
    elif ten == "canh_bao":
        d.rectangle([cx - n, cy - s, cx + n, cy + s * .2], fill=mau)
        d.ellipse([cx - n, cy + s * .5, cx + n, cy + s], fill=mau)
    elif ten == "tang":
        d.line([(cx - s, cy + s * .55), (cx - s * .2, cy - s * .15), (cx + s * .25, cy + s * .3),
                (cx + s * .95, cy - s * .55)], fill=mau, width=n)
        d.polygon([(cx + s, cy - s * .75), (cx + s, cy - s * .05), (cx + s * .35, cy - s * .65)], fill=mau)
    elif ten == "thu":
        d.rectangle([cx - s, cy - s * .65, cx + s, cy + s * .65], outline=mau, width=n)
        d.line([(cx - s, cy - s * .65), (cx, cy + s * .1), (cx + s, cy - s * .65)], fill=mau, width=n)
    elif ten == "nguoi":
        d.ellipse([cx - s * .42, cy - s * .85, cx + s * .42, cy], fill=mau)
        d.pieslice([cx - s * .95, cy, cx + s * .95, cy + s * 1.7], 180, 360, fill=mau)
    elif ten == "nhom":
        for dx in (-s * .52, s * .52):
            d.ellipse([cx + dx - s * .34, cy - s * .8, cx + dx + s * .34, cy - s * .1], fill=mau)
            d.pieslice([cx + dx - s * .72, cy - s * .1, cx + dx + s * .72, cy + s * 1.2], 180, 360, fill=mau)
    elif ten == "man_hinh":
        d.rectangle([cx - s, cy - s * .75, cx + s, cy + s * .3], outline=mau, width=n)
        d.rectangle([cx - s * .35, cy + s * .35, cx + s * .35, cy + s * .7], fill=mau)
    elif ten == "lich":
        d.rectangle([cx - s, cy - s * .62, cx + s, cy + s * .8], outline=mau, width=n)
        d.line([(cx - s, cy - s * .18), (cx + s, cy - s * .18)], fill=mau, width=n)
        for dx in (-s * .45, s * .45):
            d.line([(cx + dx, cy - s * .95), (cx + dx, cy - s * .5)], fill=mau, width=n)
    elif ten == "set":
        _tia_set(d, cx - s * .55, cy - s, s * 1.9, mau)
    elif ten == "loa":
        d.polygon([(cx - s, cy - s * .32), (cx + s * .15, cy - s * .32), (cx + s * .95, cy - s * .9),
                   (cx + s * .95, cy + s * .9), (cx + s * .15, cy + s * .32), (cx - s, cy + s * .32)],
                  fill=mau)


# ------------------------------------------------------------------ khối
def _the(d, x, y, w, h, bo=10):
    d.rounded_rectangle([_k(x), _k(y), _k(x + w), _k(y + h)], radius=_k(bo), fill=TRANG)


def _dau_the(d, x, y, w, so: str | None, ten: str, bt: str | None = None, cao=34, giua=False):
    """Thanh tiêu đề navy bo góc trên, có ô cam đánh số (hoặc biểu tượng) rồi tới chữ."""
    d.rounded_rectangle([_k(x), _k(y), _k(x + w), _k(y + cao + 10)], radius=_k(10), fill=NAVY)
    d.rectangle([_k(x), _k(y + cao - 6), _k(x + w), _k(y + cao)], fill=NAVY)
    if so is not None:
        d.rounded_rectangle([_k(x + 10), _k(y + 7), _k(x + 33), _k(y + cao - 7)], radius=_k(4), fill=CAM)
        _giua(d, _k(x + 10), _k(y + 7), _k(23), _k(cao - 14), so, _font("rat_dam", 15, TY_LE), TRANG)
    if bt is not None:
        _bt(d, _k(x + 24), _k(y + cao / 2), _k(12), bt, nen=CAM)
    f = _font("rat_dam", 17.5 if not giua else 19, TY_LE)
    _giua(d, _k(x), _k(y), _k(w), _k(cao), ten, f, TRANG, trai=None if giua else _k(44))


def _dong_so(img, d, x, y, w, bt: str, nhan: str, gt: str, mau=CHU, co=17, r=14):
    """Một dòng "biểu tượng · nhãn: giá trị". Nhãn và giá trị căn giữa chung một ô cao r*2 nên luôn
    thẳng dòng với biểu tượng, không tự tính bằng hệ số như trước (hay lệch, dòng đầu bị đè)."""
    cao = _k(r * 2)
    _bt(d, _k(x + r), _k(y + r), _k(r), bt)
    f, fg = _font("vua", co, TY_LE), _font("rat_dam", co + 1, TY_LE)
    x0 = _k(x + r * 2 + 11)
    _giua(d, x0, _k(y), 0, cao, f"{nhan}:", f, CHU, trai=0)
    rong = d.textlength(f"{nhan}:", font=f)
    _nghieng(img, x0 + rong + _k(7), _k(y) + (cao - fg.size * 1.22) / 2, gt, fg, mau)


def _vong_tron(d, cx, cy, r, pct: float):
    hop = [_k(cx - r), _k(cy - r), _k(cx + r), _k(cy + r)]
    d.ellipse(hop, fill=XAM_VONG)
    if pct > 0:
        d.pieslice(hop, -90, -90 + min(pct, 100) * 3.6, fill=NAVY)
    trong = _k(r * 0.76)
    d.ellipse([_k(cx) - trong, _k(cy) - trong, _k(cx) + trong, _k(cy) + trong], fill=TRANG)
    _giua(d, _k(cx - r), _k(cy - 19), _k(r * 2), _k(21), f"{pct:g}%", _font("rat_dam", 19, TY_LE), NAVY)
    _giua(d, _k(cx - r), _k(cy + 4), _k(r * 2), _k(13), "hoàn thành", _font("thuong", 11, TY_LE), CHU_NHAT)


def _ba_khoi(img, d, t: dict, y: int) -> int:
    cao = 268
    w = (RONG - LE * 2 - KHE * 2) / 3
    x1, x2, x3 = [LE + (w + KHE) * i for i in range(3)]
    for i, x in enumerate((x1, x2, x3)):
        _the(d, x, y, w, cao)
        _dau_the(d, x, y, w, f"{i + 1}.", [f"KẾT QUẢ NGÀY {t['hom_qua']:%d/%m}",
                                           f"TÌNH HÌNH SÁNG NAY {t['ngay']:%d/%m}", "LUỸ KẾ THÁNG"][i])
    y0, dx = y + 54, 16
    ty = t["hq_ty_le"]
    for i, (bt, nhan, gt, mau) in enumerate([
            ("cot", "Kết quả thực tế", f"{_so(t['hq_thuc_te'])} PTTB", CHU),
            ("bia", "Mục tiêu ngày", f"{_so(t['hq_muc_tieu'])} PTTB", CHU),
            ("canh_bao", "Thiếu mục tiêu", f"{_so(t['hq_thieu'])} PTTB", DO if t["hq_thieu"] else XANH_LA),
            ("tang", "Tỷ lệ đạt", f"{ty}%", XANH_LA if ty >= 80 else DO)]):
        _dong_so(img, d, x1 + dx, y0 + i * 50, w, bt, nhan, gt, mau)

    for i, (bt, nhan, gt) in enumerate([
            ("thu", "KHTN hiện có", _so(t["khtn"])),
            ("bia", "Mục tiêu PTTB/ngày", _so(t["mt_ngay"])),
            ("nguoi", "DK Online sáng", _so(t["onl_sang"])),
            ("nguoi", "DK Online chiều", _so(t["onl_chieu"])),
            ("tang", "Tổng DK Online", _so(t["dk_onl"])),
            ("man_hinh", "Đã Online", _so(t["da_online"])),
            ("nhom", "Còn phải Online", _so(t["con_phai_onl"]))]):
        _dong_so(img, d, x2 + dx, y0 - 4 + i * 29, w, bt, nhan, gt, co=15, r=12)

    for i, (bt, nhan, gt, mau) in enumerate([
            ("lich", "PTTB luỹ kế", _so(t["luy_ke"]), CHU),
            ("bia", "Mục tiêu tháng", _so(t["mt_thang"]), CHU),
            ("canh_bao", "Còn thiếu", _so(t["con_thieu"]), DO if t["con_thieu"] else XANH_LA),
            ("tang", "Tỷ lệ hoàn thành", f"{t['ty_le_thang']:g}%",
             XANH_LA if t["ty_le_thang"] >= 80 else DO)]):
        _dong_so(img, d, x3 + dx, y0 + i * 50, w - 140, bt, nhan, gt, mau)
    _vong_tron(d, x3 + w - 20 - 62, y + cao / 2 + 26, 62, t["ty_le_thang"])
    return y + cao + KHE


COT = [("Nhân sự", "ho_ten", 300), ("MT ngày", "muc_tieu", 160), ("KHTN", "khtn", 150),
       ("ONL sáng", "onl_sang", 170), ("ONL chiều", "onl_chieu", 175), ("DK ONL", "dk_onl", 155),
       ("PTTB tháng", "pttb_thang", 190), ("Pay", "vvip_thang", 120)]


def _bang(d, df, y: int, mt_phong: int) -> int:
    w = RONG - LE * 2
    rong = [c[2] for c in COT]
    rong[0] += w - sum(rong)
    _dau_the(d, LE, y, w, None, "BẢNG CHỈ SỐ TOÀN BỘ NHÂN SỰ", bt="nhom", cao=40, giua=True)
    y += 40

    f_cot, f_o, f_dam = _font("dam", 14, TY_LE), _font("vua", 15, TY_LE), _font("rat_dam", 15, TY_LE)
    cao_cot = 34
    d.rectangle([_k(LE), _k(y), _k(LE + w), _k(y + cao_cot)], fill="#E6ECF3")
    x = LE
    for (ten, khoa, _), rw in zip(COT, rong):
        if x > LE:
            d.line([(_k(x), _k(y + 4)), (_k(x), _k(y + cao_cot - 4))], fill="#BFCEDD", width=1)
        _giua(d, _k(x), _k(y), _k(rw), _k(cao_cot), ten, f_cot, NAVY,
              trai=_k(12) if khoa == "ho_ten" else None)
        x += rw
    y += cao_cot

    for r in df.itertuples():
        d.rectangle([_k(LE), _k(y), _k(LE + w), _k(y + CAO_DONG)], fill=TRANG)
        x = LE
        for (_, khoa, _), rw in zip(COT, rong):
            if khoa == "ho_ten":
                _giua(d, _k(x), _k(y), _k(rw), _k(CAO_DONG), _cat(d, str(r.ho_ten), f_dam, _k(rw - 20)),
                      f_dam, CHU, trai=_k(12))
            elif khoa == "pttb_thang":
                _giua(d, _k(x), _k(y), _k(rw), _k(CAO_DONG),
                      f"{_so(r.pttb_thang)}/{_so(r.mt_thang)}" if r.mt_thang else _so(r.pttb_thang),
                      f_o, CHU)
            else:
                _giua(d, _k(x), _k(y), _k(rw), _k(CAO_DONG), _so(getattr(r, khoa)), f_o, CHU)
            x += rw
        d.line([(_k(LE), _k(y + CAO_DONG)), (_k(LE + w), _k(y + CAO_DONG))], fill="#E7EDF3", width=1)
        y += CAO_DONG

    d.rounded_rectangle([_k(LE), _k(y), _k(LE + w), _k(y + CAO_DONG + 6)], radius=_k(8), fill=CAM)
    d.rectangle([_k(LE), _k(y), _k(LE + w), _k(y + 8)], fill=CAM)
    x = LE
    tong = {k: int(df[k].sum()) for _, k, _ in COT if k != "ho_ten"}
    for (_, khoa, _), rw in zip(COT, rong):
        # dòng TỔNG lấy mục tiêu tháng CỦA PHÒNG, không cộng mục tiêu từng người: khối 3 phía trên
        # đã ghi mục tiêu phòng, trong một ảnh phải thống nhất một số
        chu = "TỔNG" if khoa == "ho_ten" else (
            f"{_so(tong['pttb_thang'])}/{_so(mt_phong)}" if khoa == "pttb_thang" and mt_phong
            else _so(tong[khoa]))
        _giua(d, _k(x), _k(y), _k(rw), _k(CAO_DONG + 6), chu, f_dam, TRANG,
              trai=_k(12) if khoa == "ho_ten" else None)
        x += rw
    return y + CAO_DONG + 6 + KHE


def _cao_khoi_chu(d, chu: dict) -> int:
    w = (RONG - LE * 2 - KHE * 2) / 3
    f, f_trich = _font("thuong", 14.5, TY_LE), _font("vua", 15.5, TY_LE)
    can = [len(_xuong_dong(d, chu["thong_diep"], f_trich, _k(w - 74), 9)) * 24 + 38]
    for khoa in ("trong_tam", "nhan_dinh"):
        can.append(sum(len(_xuong_dong(d, m, f, _k(w - 58), 3)) * 20 + 8 for m in _dong_chu(chu[khoa])[:5]))
    return max(140, min(max(can) + 58, 360))


def _khoi_chu(img, d, chu: dict, y: int, cao: int) -> int:
    w = (RONG - LE * 2 - KHE * 2) / 3
    muc = [("TRỌNG TÂM HÔM NAY", "set", _dong_chu(chu["trong_tam"]), "cham"),
           ("ĐÁNH GIÁ & NHẬN ĐỊNH", "cot", _dong_chu(chu["nhan_dinh"]), "so"),
           ("THÔNG ĐIỆP NGÀY MỚI", "loa", [chu["thong_diep"]] if chu["thong_diep"] else [], "trich")]
    f, f_trich = _font("thuong", 14.5, TY_LE), _font("vua", 15.5, TY_LE)
    for i, (ten, bt, dong, kieu) in enumerate(muc):
        x = LE + (w + KHE) * i
        _the(d, x, y, w, cao)
        _dau_the(d, x, y, w, None, ten, bt=bt, cao=36)
        yy = y + 52
        if not dong:
            d.text((_k(x + 18), _k(yy)), "(Chưa có nội dung)", font=f, fill=CHU_NHAT)
            continue
        if kieu == "trich":
            d.rounded_rectangle([_k(x + 12), _k(yy - 8), _k(x + w - 12), _k(y + cao - 10)],
                                radius=_k(8), fill=KEM, outline=CAM_NHAT, width=max(1, _k(1)))
            fq = _font("rat_dam", 32, TY_LE)
            d.text((_k(x + 18), _k(yy - 18)), "“", font=fq, fill=CAM)
            for j, l in enumerate(_xuong_dong(d, dong[0], f_trich, _k(w - 74), 9)):
                _nghieng(img, _k(x + 38), _k(yy + 8 + j * 24), l, f_trich, CHU)
            continue
        for j, m in enumerate(dong[:5]):
            dd = _xuong_dong(d, m, f, _k(w - 58), 3)
            if kieu == "so":
                d.ellipse([_k(x + 14), _k(yy - 1), _k(x + 35), _k(yy + 20)], fill=CAM)
                _giua(d, _k(x + 14), _k(yy - 1), _k(21), _k(21), str(j + 1),
                      _font("rat_dam", 11.5, TY_LE), TRANG)
            else:
                d.ellipse([_k(x + 19), _k(yy + 5), _k(x + 30), _k(yy + 16)], fill=CAM)
            for k, l in enumerate(dd):
                d.text((_k(x + 44), _k(yy + k * 20)), l, font=f, fill=CHU)
            yy += 20 * len(dd) + 8
            if yy > y + cao - 20:
                break
    return y + cao + KHE


def _chan(img, d, ngay: date, y: int) -> int:
    cao, f = 46, _font("vua", 14, TY_LE)
    _bt(d, _k(LE + 22), _k(y + cao / 2), _k(15), "cot", nen=CAM)
    _nghieng(img, _k(LE + 48), _k(y + cao / 2) - f.size * 0.80,
             f"Nguồn số liệu: file Internet đã nạp trên app + phần sale nhập sáng {ngay:%d/%m}", f, TRANG)
    _cham_tron(d, _k(RONG - 200), _k(y + 8), _k(170), _k(24), _k(11), (240, 100, 30, 255))
    return y + cao


# ------------------------------------------------------------------ vẽ cả ảnh
def anh_bao_cao_ngay(phong_code: str, ngay: date | None = None) -> bytes:
    ngay = ngay or bc.hom_nay()
    df = bc.bang([phong_code], ngay)
    t = bc.tom_tat([phong_code], ngay)
    chu = bc.chu(phong_code, ngay)
    ten_phong = {p["code"]: p["ten"] for p in phong_order()}.get(phong_code, phong_code)

    cao = 124 + 268 + KHE + 40 + 34 + CAO_DONG * max(len(df), 1) + 36 + KHE + 360 + KHE + 54
    img = Image.new("RGBA", (_k(RONG), _k(cao)))
    _nen(img)
    d = ImageDraw.Draw(img)

    _bia(d, _k(116), _k(56), _k(34))
    _tia_set(d, _k(RONG - 196), _k(16), _k(74), "#2F6FE4")
    _tia_set(d, _k(RONG - 132), _k(10), _k(82), "#FFC61A")
    t1 = f"BÁO CÁO ĐẦU NGÀY {ngay:%d/%m}"
    _giua(d, 0, _k(12), _k(RONG), _k(52), t1, _font("rat_dam", 44, TY_LE), TRANG)
    f2 = _font("vua", 18, TY_LE)
    phu = f"{ten_phong} · tình hình hôm nay & chỉ số toàn bộ nhân sự"
    _nghieng(img, (_k(RONG) - d.textlength(phu, font=f2)) / 2, _k(72), phu, f2, "#CFE2F7")

    y = _ba_khoi(img, d, t, 124)
    if not df.empty:
        y = _bang(d, df, y, t["mt_thang"])
    y = _khoi_chu(img, d, chu, y, _cao_khoi_chu(d, chu))
    y = _chan(img, d, ngay, y)

    ra = io.BytesIO()
    img.convert("RGB").crop((0, 0, _k(RONG), min(_k(y + 8), img.height))).save(ra, "PNG", optimize=True)
    return ra.getvalue()
