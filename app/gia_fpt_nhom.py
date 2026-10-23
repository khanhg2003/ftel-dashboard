"""Nhóm gói của Tra cứu giá: chia ĐÚNG như website fpt.vn (chủ app chốt 23/10/2026), thay cách đoán theo tên gói.

Website lấy danh sách gói của từng nhóm từ cấu hình CMS nằm ngay trong HTML (dữ liệu của Next.js, dấu nháy bị escape `\\"`).
Mã `product_code` ở đó TRÙNG chuỗi `code` của dịch vụ `packages/list` nên ghép thẳng được. Ba trang được đọc:
- fpt.vn/vi: 5 tab (cá nhân, gia đình, Wifi 7, game thủ, Combo Internet Camera);
- fpt.vn/internet/doanh-nghiep: khối "spdv-internet-doanh-nghiep";
- fpt.vn/internet/ca-nhan: khối "spdv-internet-truyen-hinh" (Combo Internet + V.VIP).
Một gói được nằm ở NHIỀU nhóm nếu website đặt nó ở nhiều nhóm (vd Lux800). Gói có ở dịch vụ giá mà không nằm trong danh sách nào
thì vào nhóm cuối "Gói khác"; gói website liệt kê mà phường đó không bán thì bỏ qua.

Đây không phải API chính thức nên có `BAN_CHUP` (bản chụp ngày 23/10/2026) làm dự phòng: chỉ nhận kết quả đọc được khi ĐỦ mọi nhóm,
không thì dùng nguyên bản chụp (không trộn nửa thật nửa chụp). FPT đổi cấu hình trang chủ thì cập nhật `BAN_CHUP`.
"""
from __future__ import annotations

import re
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from app.bo_nho import nho

TTL_NHOM = 21600              # cấu hình website ít đổi: nhớ tạm 6 giờ
NGHI_SAU_LOI = 300            # lỗi thì nghỉ 5 phút không gọi lại (website chặn thì khỏi tốn 5 giây x 3 trang mỗi lượt)
HAN_TAI = 5                   # giây chờ một trang
NHOM_KHAC = "Gói khác"
TRANG_CHU, TRANG_DN, TRANG_CN = "https://fpt.vn/vi", "https://fpt.vn/internet/doanh-nghiep", "https://fpt.vn/internet/ca-nhan"
_TRINH_DUYET = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

# (nhãn nút, trang, khoá CMS) theo thứ tự nút trên trang. "tab" = tab của trang chủ, "khoi" = khối của trang sản phẩm.
NGUON = [
    ("Internet cá nhân", TRANG_CHU, "internet-ca-nhan-trang-chu"),
    ("Internet gia đình", TRANG_CHU, "internet-gia-dinh-trang-chu"),
    ("Wifi 7", TRANG_CHU, "wifi-7-trang-chu"),
    ("Internet game thủ", TRANG_CHU, "internet-game-thu-trang-chu"),
    ("Combo Internet Camera", TRANG_CHU, "combo-internet-camera-trang-internet"),
    ("Internet doanh nghiệp", TRANG_DN, "spdv-internet-doanh-nghiep"),
    ("Combo Internet + V.VIP", TRANG_CN, "spdv-internet-truyen-hinh"),
]

# Bản chụp 23/10/2026: (nhãn nút, danh sách mã theo thứ tự của website).
BAN_CHUP = [
    ("Internet cá nhân", ["goi-speedx1", "goi-giga", "goi-sky", "goi-sky-f1", "goi-sky-f2"]),
    ("Internet gia đình", ["goi-speedx1-f1", "goi-sky-f1", "goi-sky-f2", "goi-meta-f1"]),
    ("Wifi 7", ["goi-speedx1", "goi-speedx1-f1", "combo-internet-speedx1-vvip-lite", "combo-internet-speedx1-f1-vvip-lite",
                "fpt-speedx2", "speed-x2-pro", "combo-internet-speedx2-vvip-lite"]),
    ("Internet game thủ", ["goi-speedx1", "goi-f-game"]),
    ("Combo Internet Camera", ["goi-giga-eyes3-play4", "goi-giga-eyes3-iq4s", "goi-sky-eyes3-play4", "goi-sky-eyes3-iq4s"]),
    ("Internet doanh nghiệp", ["super-300-biz", "super-300-biz-plus", "combo-internet-lux800-vvip-lite"]),
    ("Combo Internet + V.VIP", ["combo-internet-giga-vvip-lite", "combo-internet-sky-vvip-lite", "combo-internet-meta-vvip-lite",
                                "combo-internet-speedx1-vvip-lite", "combo-internet-lux800-vvip-lite"]),
]

_khoa_tai = threading.Lock()
_loi_luc: float | None = None              # lần tải hỏng gần nhất (đồng hồ monotonic)
_tot_luc: tuple[float, dict] | None = None  # lần tải đúng gần nhất, để nhiều lượt nguội cùng lúc chỉ tải một lần


class LoiNhom(Exception):
    """Không đọc được cấu hình nhóm từ website (mạng, trang đổi cấu trúc...)."""


def ban_chup() -> dict:
    return {"nhom": [(nhan, list(ma)) for nhan, ma in BAN_CHUP], "nguon": "luu_san"}


def _tai_trang(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _TRINH_DUYET, "Accept-Language": "vi"})
    with urllib.request.urlopen(req, timeout=HAN_TAI) as r:
        return r.read().decode("utf-8", "replace")


def _ma_trong(doan: str) -> list[str]:
    ra: list[str] = []
    for m in re.findall(r'"product_code":"([^"]+)"', doan):
        if m not in ra:
            ra.append(m)
    return ra


def _doc_khoa(html: str, khoa: str) -> list[str]:
    """Mã gói (đúng thứ tự `items`) của tab / khối có tên CMS là `khoa`; không thấy thì rỗng."""
    m = re.search(r'"name":"' + re.escape(khoa) + r'","title":"[^"]*","type":"[^"]*"[\s\S]{0,1500}?"items":\[([^\]]*)\]', html)
    return _ma_trong(m.group(1)) if m else []


def _phan_tich(trang: dict[str, str]) -> dict:
    """{"nhom": [(nhãn, [mã])], "nguon": "website"} từ HTML ba trang; thiếu bất kỳ nhóm nào (hoặc nhóm rỗng) thì ném `LoiNhom`."""
    nhom = []
    for nhan, url, khoa in NGUON:
        html = (trang.get(url) or "").replace('\\"', '"')
        ma = _doc_khoa(html, khoa)
        if not ma:
            raise LoiNhom(f"Không thấy nhóm {nhan} trên {url}")
        nhom.append((nhan, ma))
    return {"nhom": nhom, "nguon": "website"}


def _tai_tat_ca() -> dict:
    urls = sorted({u for _, u, _ in NGUON})
    with ThreadPoolExecutor(len(urls)) as ex:
        html = list(ex.map(_tai_trang, urls))
    return _phan_tich(dict(zip(urls, html)))


@nho("gia_fpt", TTL_NHOM)
def _tai_cau_hinh() -> dict:
    """Tải + đọc từ website; NÉM LỖI khi hỏng để `nho` không ghim bản chụp suốt 6 giờ vì website lỗi thoáng qua."""
    global _loi_luc, _tot_luc
    with _khoa_tai:                                    # nhiều lượt nguội cùng lúc: chỉ một lượt tải, các lượt kia dùng kết quả của nó
        bay_gio = time.monotonic()
        if _tot_luc and bay_gio - _tot_luc[0] < TTL_NHOM:
            return _tot_luc[1]
        if _loi_luc is not None and bay_gio - _loi_luc < NGHI_SAU_LOI:
            raise LoiNhom("Vừa tải hỏng, nghỉ ít phút")
        try:
            kq = _tai_tat_ca()
        except Exception as e:
            _loi_luc = bay_gio
            raise LoiNhom("Chưa lấy được nhóm gói từ fpt.vn") from e
        _tot_luc, _loi_luc = (bay_gio, kq), None
        return kq


def cau_hinh() -> dict:
    """{"nhom": [(nhãn, [mã...])], "nguon": "website" | "luu_san"}: lấy một lần mỗi lượt callback rồi truyền xuống. Không bao giờ ném lỗi."""
    try:
        return _tai_cau_hinh()
    except Exception:
        return ban_chup()


def chia_nhom(goi: list[dict], ch: dict | None = None) -> dict[str, list[dict]]:
    """{nhãn: các gói} theo thứ tự nút, bỏ nhóm rỗng, "Gói khác" cuối. Trong nhóm giữ thứ tự `items` của website; một gói có thể ở nhiều nhóm."""
    ch = ch or cau_hinh()
    theo_ma = {g["code"]: g for g in goi}
    ra: dict[str, list[dict]] = {}
    da: set = set()
    for nhan, ma in ch["nhom"]:
        gs = [theo_ma[m] for m in ma if m in theo_ma]
        if gs:
            ra[nhan] = gs
            da.update(g["code"] for g in gs)
    khac = sorted((g for g in goi if g["code"] not in da), key=lambda g: (g["gia"] or 0, g["ten"]))
    if khac:
        ra[NHOM_KHAC] = khac
    return ra


def nhom_cua_goi(goi: list[dict], ch: dict | None = None) -> dict[str, str]:
    """{mã gói: "Nhóm A · Nhóm B"} cho cột Nhóm ở các bảng so sánh."""
    ra: dict[str, list[str]] = {}
    for nhan, gs in chia_nhom(goi, ch).items():
        for g in gs:
            ra.setdefault(g["code"], []).append(nhan)
    return {code: " · ".join(ds) for code, ds in ra.items()}
