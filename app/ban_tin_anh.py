"""Ảnh Báo cáo Tổng cho Bản tin 8h của Ban Giám đốc (Zalo `sendPhoto` chỉ nhận ĐƯỜNG DẪN ảnh để tự tải về).

Vì sao đường dẫn tạm: Zalo không nhận file tải lên, nên app mở một đường công khai `GET /api/ban-tin/anh/<mã>.png`
chỉ tồn tại `HAN_ANH_GIAY` giây. Mã = `<ngày số>.<hạn Unix>.<chữ ký>`, ký HMAC-SHA256 bằng khoá dẫn xuất từ `APP_SECRET_KEY`
(nhãn riêng, KHÁC khoá webhook). Đường này chỉ ra đúng MỘT báo cáo cố định (Báo cáo Tổng toàn chi nhánh, bản đủ cột,
không nhận xét AI): không có tham số nào chọn phòng hay chi nhánh, nên link có rò ra cũng không mở rộng được phạm vi.
Mã sai, hết hạn hay hỏng đều trả cùng một phản hồi 404, không tiết lộ lý do.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from datetime import date, datetime

from app import config, metrics, overview
from app.config import SECRET_KEY

HAN_ANH_GIAY = 15 * 60
DUONG_DAN = "/api/ban-tin/anh/"
_NHAN_KHOA = b"ban-tin-anh"
_TON_CACHE = 120                                  # giây giữ PNG đã dựng cho nhiều người nhận cùng lượt (không bắt buộc)
_cache: dict = {}


def cong_tac() -> str:
    """`anh` (mặc định) hoặc `chu` ở `config/rules.yml` → `ban_tin.bgd_dang`; giá trị lạ coi như `anh`."""
    v = str(((config.rules_config().get("ban_tin") or {}).get("bgd_dang")) or "anh").strip().lower()
    return "chu" if v == "chu" else "anh"


def app_url() -> str:
    """Địa chỉ gốc https của app; Zalo chỉ tải được ảnh từ địa chỉ công khai https nên http / rỗng coi như chưa cài."""
    goc = (os.environ.get("APP_URL") or "").strip().rstrip("/")
    return goc if goc.lower().startswith("https://") else ""


def _ky(ngay_iso: str, han: int) -> str:
    khoa = hmac.new(SECRET_KEY.encode(), _NHAN_KHOA, hashlib.sha256).digest()
    return hmac.new(khoa, f"{ngay_iso}.{han}".encode(), hashlib.sha256).hexdigest()[:32]


def tao_ma(ngay_iso: str, bay_gio: float | None = None) -> str:
    han = int((time.time() if bay_gio is None else bay_gio) + HAN_ANH_GIAY)
    return f"{ngay_iso}.{han}.{_ky(ngay_iso, han)}"


def doc_ma(ma: str, bay_gio: float | None = None) -> str | None:
    """Ngày số (YYYY-MM-DD) nếu mã đúng chữ ký, còn hạn và là ngày số hợp lệ; ngược lại None (không nói vì sao)."""
    try:
        ngay_iso, han_s, ky = str(ma).split(".")
        han = int(han_s)
        if len(ngay_iso) != 10 or not hmac.compare_digest(ky.encode(), _ky(ngay_iso, han).encode()):
            return None
        if han < (time.time() if bay_gio is None else bay_gio):
            return None
        moi = metrics.ngay_moi_nhat()
        return ngay_iso if moi and date.fromisoformat(ngay_iso) <= date.fromisoformat(moi) else None
    except Exception:
        return None


def url_anh(ngay_iso: str) -> str | None:
    """Đường dẫn ảnh tạm cho một người nhận (hạn tính từ lúc gọi); None nếu chưa có `APP_URL` https."""
    goc = app_url()
    return f"{goc}{DUONG_DAN}{tao_ma(ngay_iso)}.png" if goc else None


def dung_anh(ngay_iso: str) -> bytes:
    """PNG đúng ảnh nút "Chụp ảnh" của Báo cáo Tổng: toàn chi nhánh, luỹ kế tới ngày số, số đã chốt, không nhận xét AI.
    Nhớ tạm theo (ngày số, giờ nạp cuối) vài phút trong tiến trình; máy chủ khác thì tự dựng lại."""
    from app.export_png import anh_tong_quan
    _, luc = overview.trang_thai_ngay(ngay_iso)
    khoa = (ngay_iso, luc)
    cu = _cache.get("anh")
    if cu and cu[0] == khoa and time.monotonic() - cu[1] < _TON_CACHE:
        return cu[2]
    d = date.fromisoformat(ngay_iso)
    png, _ = anh_tong_quan(f"{d.year}-{d.month:02d}", d.day, chi_phong=None, chi_nhanh="all",
                           tam_tinh=False, luc=luc if isinstance(luc, datetime) else None)
    _cache["anh"] = (khoa, time.monotonic(), png)
    return png
