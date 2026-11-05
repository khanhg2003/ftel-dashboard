"""Ảnh BANNER gói cước cho bot Zalo Tra cứu giá (giai đoạn 2, chủ app chốt 05/11/2026): ảnh vuông dựng bằng Pillow, nửa trên xanh FPT
có tên gói, nửa dưới navy có GIÁ vàng rất lớn, tốc độ, viên thuốc cam nêu quà / ưu đãi, phí hòa mạng, cách trả trước có lợi nhất.
Chỉ hình khối đơn giản + logo và font đi kèm app (`export_png._font`), không ảnh có bản quyền.

Ảnh quảng cáo của gói (`images[0].url` của dịch vụ fpt.vn, đã vào `gia_fpt._chuan_goi` thành trường `anh`) được tải về làm PHẦN TRÊN của banner
(khổ dọc rộng 1080, cắt giữa về tỉ lệ cố định `ANH_TY_LE`), khối giá navy nằm dưới. Gói không có ảnh hoặc tải / đọc ảnh lỗi thì dùng banner
tự vẽ (vuông) làm dự phòng, không báo lỗi. Chống SSRF: chỉ tải `https://s3-api.fpt.vn` (đúng tên máy, cổng 443, không đăng nhập trong địa chỉ),
KHÔNG đi theo chuyển hướng, tối đa 3 MB, hạn 5 giây, phải mở được bằng Pillow (JPEG / PNG / WEBP); nhớ tạm trong tiến trình.

Số liệu CÙNG NGUỒN với tin chữ (`gia_fpt`: `goi_theo_phuong`, `chi_tiet_goi`); thiếu dữ liệu nào thì bỏ dòng đó. Phí hòa mạng thiếu ghi
"Chưa rõ", không bao giờ "Miễn phí" (chỉ khi dịch vụ ghi rõ phí 0).

Gửi ảnh: Zalo `sendPhoto` chỉ nhận ĐƯỜNG DẪN, nên app mở `GET /api/zalo-gia/anh/<mã>.png` không đăng nhập. Mã = `<tỉnh>.<phường>.<mã gói>.<hạn Unix>.<chữ ký>`,
HMAC-SHA256 bằng khoá dẫn xuất từ `APP_SECRET_KEY` (nhãn riêng "zalo-gia-anh", KHÁC khoá webhook và khoá ảnh Bản tin), hạn 15 phút.
Mã chỉ chứa số / mã gói (không chữ tự do của người dùng); mã sai, hết hạn, hỏng hay dựng lỗi đều trả cùng một 404.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import re
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageDraw

from app import gia_fpt as gf
from app import zalo_gia_nd as nd
from app.config import SECRET_KEY
from app.export_png import _font
from app.thoi_gian import chu_gio_vn, utc_bay_gio

HAN_ANH_GIAY = 15 * 60
DUONG_DAN = "/api/zalo-gia/anh/"
_NHAN_KHOA = b"zalo-gia-anh"
HOST_ANH = "s3-api.fpt.vn"             # nguồn ảnh duy nhất được tải (chống SSRF)
TOI_DA_BYTE_ANH = 3 * 1024 * 1024
HAN_TAI_ANH = 5                        # giây; sendPhoto của bot chờ 8 giây gồm cả tải ảnh + dựng
ANH_TY_LE = 1.4                        # rộng : cao của phần ảnh fpt.vn (mọi ảnh cùng chiều cao)
_TON_ANH, _TON_ANH_LOI = 3600, 120     # giây nhớ ảnh đã tải / nhớ việc tải hỏng (khỏi chờ 5 giây mỗi lượt)
_anh_cache: dict = {}
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
_TON_CACHE = 180                      # giây giữ PNG đã dựng (không bắt buộc: Vercel có thể đổi máy)
_TOI_DA_CACHE = 24
_cache: dict = {}
_MA_GOI = re.compile(r"[A-Za-z0-9_-]{1,80}")

W = 1080                              # cạnh ảnh cuối (px); vẽ ở 2 lần rồi thu nhỏ cho viền mượt
S = 2
XANH, XANH_SANG, XANH_VACH = (0, 114, 188), (28, 139, 211), (18, 128, 204)
NAVY, NAVY_SANG = (11, 46, 79), (22, 66, 108)
CAM, VANG, TRANG, NHAT = (243, 111, 33), (255, 210, 31), (255, 255, 255), (170, 205, 238)
LOGO = Path(__file__).resolve().parent.parent / "assets" / "fpt_logo.png"
_QUA = re.compile(r"modem|wi-?fi|camera|cloud|v\.?vip|truyền hình|fpt play|mesh", re.I)


# ------------------------------------------------------------------ mã ký + đường dẫn
def _ky(tinh: int, phuong: int, code: str, han: int) -> str:
    khoa = hmac.new(SECRET_KEY.encode(), _NHAN_KHOA, hashlib.sha256).digest()
    return hmac.new(khoa, f"{tinh}.{phuong}.{code}.{han}".encode(), hashlib.sha256).hexdigest()[:32]


def tao_ma(tinh: int, phuong: int, code: str, bay_gio: float | None = None) -> str:
    han = int((time.time() if bay_gio is None else bay_gio) + HAN_ANH_GIAY)
    return f"{int(tinh)}.{int(phuong)}.{code}.{han}.{_ky(int(tinh), int(phuong), code, han)}"


def doc_ma(ma: str, bay_gio: float | None = None) -> tuple[int, int, str] | None:
    """(tỉnh, phường, mã gói) nếu mã đúng chữ ký và còn hạn; ngược lại None (không nói vì sao)."""
    try:
        phan = str(ma).split(".")
        if len(phan) != 5:
            return None
        tinh, phuong, code, han_s, ky = int(phan[0]), int(phan[1]), phan[2], phan[3], phan[4]
        han = int(han_s)
        if not _MA_GOI.fullmatch(code) or not hmac.compare_digest(ky.encode(), _ky(tinh, phuong, code, han).encode()):
            return None
        return (tinh, phuong, code) if han >= (time.time() if bay_gio is None else bay_gio) else None
    except Exception:
        return None


def url_anh(goc_https: str, tinh: int, phuong: int, code: str) -> str | None:
    """Đường dẫn ảnh tạm; None nếu mã gói có ký tự lạ (không ký được)."""
    if not _MA_GOI.fullmatch(code or ""):
        return None
    return f"{goc_https}{DUONG_DAN}{tao_ma(tinh, phuong, code)}.png"


def _nhan_goi(ten: str) -> str:
    """"Gói Giga" (website đã ghi sẵn chữ Gói thì không thêm lần nữa), "Gói Sky" cho "Internet Sky"."""
    ten_goi = re.sub(r"^internet\s+", "", ten or "", flags=re.I)
    return ten_goi if re.match(r"^(g[oó]i|combo)\s", ten_goi, flags=re.I) else f"Gói {ten_goi}"


def chu_thich(ten: str, vi_tri: str, gia) -> str:
    """Caption ngắn của ảnh: "Gói Giga · Phường Nam Nha Trang · 195.000đ/tháng"."""
    gia_chu = f"{gf.chu_tien(gia)}/tháng" if gia is not None else "chưa rõ giá"
    return f"{_nhan_goi(ten)} · {vi_tri.split(',')[0]} · {gia_chu}"


def dung_theo_ma(tinh: int, phuong: int, code: str) -> bytes:
    """Dựng banner từ dữ liệu `gia_fpt` của đúng gói đó (ném lỗi nếu không có gói / dịch vụ lỗi)."""
    ngay = chu_gio_vn(utc_bay_gio(), "%Y-%m-%d")
    khoa = (tinh, phuong, code, ngay)
    cu = _cache.get(khoa)
    if cu and time.monotonic() - cu[0] < _TON_CACHE:
        return cu[1]
    res = gf.goi_theo_phuong(tinh, phuong)
    g = next(x for x in res["goi"] if x["code"] == code)
    try:
        ct = gf.chi_tiet_goi(code, tinh, phuong, g["gia"])
    except gf.LoiGia:
        ct = None
    ten_phuong = next(p["ten"] for p in gf.danh_sach_phuong(tinh) if p["id"] == phuong)
    ten_tinh = next((t["ten"] for t in gf.danh_sach_tinh() if t["id"] == tinh), "")
    png = ve_banner(g, ct, f"{ten_phuong}, {ten_tinh}".strip(", "), res.get("luc"))
    if len(_cache) >= _TOI_DA_CACHE:
        _cache.pop(next(iter(_cache)))
    _cache[khoa] = (time.monotonic(), png)
    return png


# ------------------------------------------------------------------ ảnh gói của fpt.vn
class _KhongChuyenHuong(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):          # chuyển hướng sang máy khác là cách vượt rào SSRF: không đi theo
        return None


_opener = urllib.request.build_opener(_KhongChuyenHuong)


def url_anh_hop_le(url: str) -> bool:
    try:
        p = urlparse(url or "")
        return p.scheme == "https" and p.hostname == HOST_ANH and p.port in (None, 443) and not p.username and not p.password
    except ValueError:
        return False


def _tai_byte(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "image/*"})
    with _opener.open(req, timeout=HAN_TAI_ANH) as r:
        dai = r.headers.get("Content-Length")
        if dai and int(dai) > TOI_DA_BYTE_ANH:
            raise ValueError("ảnh quá lớn")
        b = r.read(TOI_DA_BYTE_ANH + 1)
    if len(b) > TOI_DA_BYTE_ANH:
        raise ValueError("ảnh quá lớn")
    return b


def tai_anh_goc(url: str) -> Image.Image | None:
    """Ảnh quảng cáo của gói đã mở bằng Pillow; None nếu địa chỉ không hợp lệ, tải lỗi, quá lớn hay không phải ảnh."""
    if not url_anh_hop_le(url):
        return None
    cu = _anh_cache.get(url)
    if cu and time.monotonic() - cu[0] < (_TON_ANH if cu[1] else _TON_ANH_LOI):
        b = cu[1]
    else:
        try:
            b = _tai_byte(url)
        except Exception:
            b = None
        if len(_anh_cache) >= 16:
            _anh_cache.pop(next(iter(_anh_cache)))
        _anh_cache[url] = (time.monotonic(), b)
    if not b:
        return None
    try:
        im = Image.open(io.BytesIO(b))
        im.load()
        return im if im.format in ("JPEG", "PNG", "WEBP") and max(im.size) <= 6000 else None
    except Exception:
        return None


def _bia_anh(anh: Image.Image) -> Image.Image:
    """Đưa ảnh về rộng `W`, cao `W / ANH_TY_LE`: phủ kín khung, cắt phần thừa ở giữa."""
    cao = round(W / ANH_TY_LE)
    ty = max(W / anh.width, cao / anh.height)
    a = anh.convert("RGB").resize((max(W, round(anh.width * ty)), max(cao, round(anh.height * ty))), Image.LANCZOS)
    x0, y0 = (a.width - W) // 2, (a.height - cao) // 2
    return a.crop((x0, y0, x0 + W, y0 + cao))


# ------------------------------------------------------------------ dữ liệu hiển thị
def _tien(v) -> str:
    return "Miễn phí" if v == 0 else gf.chu_tien(v)


def _phi(ct: dict | None) -> str:
    nhom = (ct or {}).get("phi_nhom") or []
    if not nhom:
        return "Chưa rõ"
    ds = [p for _, p in nhom]
    return _tien(ds[0]) if len(set(ds)) == 1 else f"{_tien(min(ds))} - {_tien(max(ds))}"


def _tra_truoc_loi_nhat(lua_chon: list[dict]) -> dict | None:
    """Cách trả trước nhiều tháng tặng nhất (bằng nhau thì kỳ dài hơn); không có cách trả trước nào thì None."""
    ds = [z for z in lua_chon if z.get("tong") and not gf._la_tra_sau(z["hinh_thuc"], z["thang"])]
    return max(ds, key=lambda z: (z.get("tang") or 0, z["thang"])) if ds else None


def _chu_vien_thuoc(g: dict, ct: dict | None, tt: dict | None) -> list[str]:
    ra: list[str] = []
    for chu in [g.get("uu_dai"), (tt or {}).get("qua"), *[d for d in ((ct or {}).get("mo_ta") or g.get("mo_ta") or []) if _QUA.search(d)]]:
        chu = " ".join(str(chu or "").split())
        if chu and chu.casefold() not in {x.casefold() for x in ra}:
            ra.append(chu)
    return ra[:2]


def du_lieu(g: dict, ct: dict | None) -> dict:
    """Mọi thứ cần vẽ; khoá thiếu / rỗng nghĩa là dữ liệu không có và dòng đó bị bỏ."""
    toc = [x.strip() for x in (g.get("toc_do") or "").split("/") if x.strip()]
    tt = _tra_truoc_loi_nhat(ct["lua_chon"]) if ct else None
    return {"ten": g["ten"], "ten_goi": re.sub(r"^internet\s+", "", g["ten"], flags=re.I), "gia": g.get("gia"),
            "toc": toc, "phi": _phi(ct) if ct is not None else "Chưa rõ", "tra_truoc": tt, "pills": _chu_vien_thuoc(g, ct, tt),
            "han": nd._han_chinh_sach(ct["lua_chon"]) if ct else ""}


# ------------------------------------------------------------------ vẽ
def _k(v: float) -> int:
    return round(v * S)


def _f(kieu: str, co: float):
    return _font(kieu, co, S)


def _rong(d, chu: str, fo) -> float:
    return d.textlength(chu, font=fo)


def _cat(d, chu: str, fo, toi_da: float) -> str:
    if _rong(d, chu, fo) <= _k(toi_da):
        return chu
    while chu and _rong(d, chu + "…", fo) > _k(toi_da):
        chu = chu[:-1]
    return chu + "…"


def _dong(d, x: float, y: float, doan: list[tuple], toi_da: float = W - 96, can_giua: bool = False) -> None:
    """Một dòng gồm nhiều đoạn (chữ, kiểu font, cỡ, màu) trên cùng đường cơ sở `y`; quá bề ngang thì thu nhỏ đều."""
    he = 1.0
    while True:
        fs = [_f(k, c * he) for _, k, c, _ in doan]
        tong = sum(_rong(d, t, fo) for (t, *_), fo in zip(doan, fs))
        if tong <= _k(toi_da) or he < 0.55:
            break
        he -= 0.05
    cx = _k(x) + ((_k(toi_da) - tong) / 2 if can_giua else 0)
    for (t, _, _, mau), fo in zip(doan, fs):
        d.text((cx, _k(y)), t, font=fo, fill=mau, anchor="ls")
        cx += _rong(d, t, fo)


def _mui_ten(d, x: float, y: float, xuong: bool, mau) -> None:
    """Mũi tên tải xuống / tải lên cao ~34px, đáy ở đường cơ sở `y`."""
    c, t = _k(x + 13), _k(y - 34)
    if xuong:
        d.rectangle([c - _k(4), t, c + _k(4), t + _k(18)], fill=mau)
        d.polygon([(c - _k(13), t + _k(16)), (c + _k(13), t + _k(16)), (c, t + _k(34))], fill=mau)
    else:
        d.rectangle([c - _k(4), t + _k(16), c + _k(4), t + _k(34)], fill=mau)
        d.polygon([(c - _k(13), t + _k(18)), (c + _k(13), t + _k(18)), (c, t)], fill=mau)


def _tieu_de(d, ten: str) -> tuple[list[str], float]:
    """Tên gói IN HOA vừa bề ngang: một dòng nếu được, không thì hai dòng cân nhau."""
    chu = ten.upper()
    for co in range(124, 60, -4):
        if _rong(d, chu, _f("rat_dam", co)) <= _k(W - 120):
            return [chu], co
    tu = chu.split()
    if len(tu) >= 2:
        i = min(range(1, len(tu)), key=lambda i: abs(len(" ".join(tu[:i])) - len(" ".join(tu[i:]))))
        dong = [" ".join(tu[:i]), " ".join(tu[i:])]
    else:
        dong = [chu]
    for co in range(96, 40, -4):
        if all(_rong(d, x, _f("rat_dam", co)) <= _k(W - 120) for x in dong):
            return dong, co
    return dong, 40


def _nen(img_w: int, cao_xanh: float):
    img = Image.new("RGBA", (_k(img_w), _k(img_w)), XANH)
    d = ImageDraw.Draw(img, "RGBA")
    d.ellipse([_k(W - 330), _k(-170), _k(W + 160), _k(320)], fill=(*XANH_SANG, 255))           # hình tròn lớn góc phải
    d.ellipse([_k(-120), _k(cao_xanh - 190), _k(210), _k(cao_xanh + 140)], fill=(*XANH_SANG, 255))
    for x0, rong in ((330, 70), (470, 34)):                                                  # vạch chéo
        d.polygon([(_k(x0), 0), (_k(x0 + rong), 0), (_k(x0 + rong - 150), _k(cao_xanh)), (_k(x0 - 150), _k(cao_xanh))], fill=(*XANH_VACH, 255))
    d.polygon([(_k(W - 210), 0), (_k(W), 0), (_k(W), _k(210))], fill=(*CAM, 255))             # góc cam
    d.rounded_rectangle([0, _k(cao_xanh), _k(W), _k(W + 120)], radius=_k(58), fill=(*NAVY, 255))
    d.ellipse([_k(W - 250), _k(W - 250), _k(W + 170), _k(W + 170)], fill=(*NAVY_SANG, 255))   # hình tròn mờ góc dưới phải
    return img, d


def _logo(img) -> None:
    d = ImageDraw.Draw(img, "RGBA")
    d.rounded_rectangle([_k(48), _k(40), _k(48 + 172), _k(40 + 172)], radius=_k(28), fill=(255, 255, 255, 255))
    if LOGO.exists():
        lg = Image.open(LOGO).convert("RGBA")
        lg.thumbnail((_k(162), _k(162)))
        img.alpha_composite(lg, (_k(48 + 86) - lg.width // 2, _k(40 + 86) - lg.height // 2))


def _vien_thuoc(d, y: float, chu: list[str]) -> float:
    """Các viên thuốc cam trên một hàng (cái nào không vừa thì bỏ). Trả về đường cơ sở dưới của hàng."""
    fo, x, cao = _f("dam", 33), 48, 62
    for t in chu:
        t = _cat(d, t, fo, W - 96 - 56)
        rong = _rong(d, t, fo) / S + 56
        if x + rong > W - 48 and x > 48:
            break
        d.rounded_rectangle([_k(x), _k(y), _k(x + rong), _k(y + cao)], radius=_k(cao / 2), fill=(*CAM, 255))
        d.text((_k(x + 28), _k(y + cao / 2)), t, font=fo, fill=TRANG, anchor="lm")
        x += rong + 16
    return y + cao


def _logo_nho(img, x: float, y: float) -> None:
    d = ImageDraw.Draw(img, "RGBA")
    d.rounded_rectangle([_k(x), _k(y), _k(x + 84), _k(y + 84)], radius=_k(18), fill=(255, 255, 255, 255))
    if LOGO.exists():
        lg = Image.open(LOGO).convert("RGBA")
        lg.thumbnail((_k(80), _k(80)))
        img.alpha_composite(lg, (_k(x + 42) - lg.width // 2, _k(y + 42) - lg.height // 2))


def _khoi_duoi(img, d, y: float, dl: dict, y_toi_da: float, logo: bool = False) -> float:
    """Khối giá: "Gói ...", GIÁ vàng, tốc độ, viên thuốc cam, phí hòa mạng, trả trước, hạn. Trả về đường cơ sở của dòng cuối đã vẽ.
    Dòng hạn bị bỏ nếu quá `y_toi_da` (không đè chân ảnh)."""
    if dl["ten_goi"]:
        nhan = _cat(d, _nhan_goi(dl["ten_goi"]), _f("dam", 44), W - 96 - (110 if logo else 0))
        d.text((_k(48), _k(y + 14)), nhan, font=_f("dam", 44), fill=(*NHAT, 255), anchor="ls")
        if logo:
            _logo_nho(img, W - 48 - 84, y - 32)
        y += 70 if logo else 62
    if dl["gia"] is not None:
        y += 112
        _dong(d, 48, y, [(gf.chu_tien(dl["gia"]), "rat_dam", 168, VANG), (" /tháng", "dam", 52, TRANG)])
    else:
        y += 90
        _dong(d, 48, y, [("Chưa rõ giá", "rat_dam", 92, VANG)])
    if dl["toc"]:
        y += 62
        _ve_toc_do(d, y, dl["toc"])
    if dl["pills"]:
        y = _vien_thuoc(d, y + 26, dl["pills"]) + 10
    else:
        y += 4
    y += 50
    _dong(d, 48, y, [("Phí hòa mạng  ", "thuong", 36, TRANG), (dl["phi"], "rat_dam", 36, TRANG)])
    if dl["tra_truoc"]:
        z, y = dl["tra_truoc"], y + 50
        doan = [(f"Trả trước {z['thang']} tháng chỉ  ", "thuong", 36, TRANG), (gf.chu_tien(z["tong"]), "rat_dam", 36, VANG)]
        if z.get("tang"):
            doan.append((f"  (tặng {z['tang']:g} tháng)", "thuong", 36, TRANG))
        _dong(d, 48, y, doan)
    if dl["han"] and y + 44 <= y_toi_da:
        y += 44
        _dong(d, 48, y, [(dl["han"], "thuong", 28, (*NHAT, 255))])
    return y


def _chan_anh(d, y_duong: float, vi_tri: str, luc) -> None:
    ngay = chu_gio_vn(luc or utc_bay_gio(), "%d/%m/%Y")
    pie = _cat(d, f"Giá tại {vi_tri} · fpt.vn · {ngay}", _f("thuong", 25), W - 96)
    d.line([(_k(48), _k(y_duong)), (_k(W - 48), _k(y_duong))], fill=(255, 255, 255, 40), width=_k(2))
    d.text((_k(48), _k(y_duong + 36)), pie, font=_f("thuong", 25), fill=(*NHAT, 255), anchor="ls")


def _png(img, rong: int, cao: int) -> bytes:
    ra = io.BytesIO()
    img.convert("RGB").resize((rong, cao), Image.LANCZOS).save(ra, "PNG", optimize=True)
    return ra.getvalue()


def ve_banner(g: dict, ct: dict | None, vi_tri: str, luc=None) -> bytes:
    """Banner của một gói: có ảnh fpt.vn thì khổ dọc (ảnh trên, khối giá dưới), không thì bản tự vẽ vuông (dự phòng, không báo lỗi)."""
    anh = tai_anh_goc(g.get("anh") or "")
    if anh is not None:
        try:
            return _ve_voi_anh(g, ct, vi_tri, luc, anh)
        except Exception:
            pass
    return _ve_tu_ve(g, ct, vi_tri, luc)


def _ve_voi_anh(g: dict, ct: dict | None, vi_tri: str, luc, anh: Image.Image) -> bytes:
    """PNG rộng 1080: ảnh quảng cáo fpt.vn ở trên (đã bo góc dưới bằng khối navy chồng lên), khối giá dưới, chân ảnh."""
    dl = du_lieu(g, ct)
    cao_anh, chong = round(W / ANH_TY_LE), 36
    lop = Image.new("RGBA", (_k(W), _k(1500)), (0, 0, 0, 0))
    d = ImageDraw.Draw(lop, "RGBA")
    d.rounded_rectangle([0, 0, _k(W), _k(1560)], radius=_k(40), fill=(*NAVY, 255))
    y = _khoi_duoi(lop, d, 78, dl, 10 ** 6, logo=True)
    _chan_anh(d, y + 34, vi_tri, luc)
    cao_lop = round(y + 34 + 36 + 34)
    duoi = lop.crop((0, 0, _k(W), _k(cao_lop))).resize((W, cao_lop), Image.LANCZOS)
    ra = Image.new("RGBA", (W, cao_anh - chong + cao_lop), (*NAVY, 255))
    ra.paste(_bia_anh(anh), (0, 0))
    ra.alpha_composite(duoi, (0, cao_anh - chong))
    b = io.BytesIO()
    ra.convert("RGB").save(b, "PNG", optimize=True)
    return b.getvalue()


def _ve_tu_ve(g: dict, ct: dict | None, vi_tri: str, luc=None) -> bytes:
    """PNG vuông 1080x1080 tự vẽ (xem docstring đầu file): dùng khi gói không có ảnh fpt.vn."""
    dl = du_lieu(g, ct)
    d0 = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    dong_tieu_de, co = _tieu_de(d0, dl["ten"])
    co_dong = co * 1.04
    y_dau = 236 + co * 0.9
    y_phu = y_dau + co_dong * (len(dong_tieu_de) - 1) + 58
    cao_xanh = y_phu + 38
    img, d = _nen(W, cao_xanh)
    _logo(img)
    for i, t in enumerate(dong_tieu_de):
        d.text((_k(48), _k(y_dau + i * co_dong)), t, font=_f("rat_dam", co), fill=TRANG, anchor="ls")
    d.text((_k(48), _k(y_phu)), "Internet cáp quang FPT Telecom", font=_f("dam", 34), fill=(*NHAT, 255), anchor="ls")
    _khoi_duoi(img, d, cao_xanh + 46, dl, W - 96)
    _chan_anh(d, W - 72, vi_tri, luc)
    return _png(img, W, W)


def _ve_toc_do(d, y: float, toc: list[str]) -> None:
    fo_nhan, fo_so = _f("dam", 38), _f("rat_dam", 44)
    d.text((_k(48), _k(y)), "Tốc độ", font=fo_nhan, fill=(*NHAT, 255), anchor="ls")
    x = 48 + _rong(d, "Tốc độ", fo_nhan) / S + 26
    if len(toc) == 2:
        for xuong, so in ((True, toc[0]), (False, toc[1])):
            _mui_ten(d, x, y, xuong, VANG)
            d.text((_k(x + 36), _k(y)), so, font=fo_so, fill=TRANG, anchor="ls")
            x += 36 + _rong(d, so, fo_so) / S + 34
    else:
        d.text((_k(x), _k(y)), toc[0], font=fo_so, fill=TRANG, anchor="ls")
