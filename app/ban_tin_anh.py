"""Ảnh báo cáo cho Bản tin 8h (Zalo `sendPhoto` chỉ nhận ĐƯỜNG DẪN ảnh để tự tải về): Báo cáo Tổng cho Ban Giám đốc
và trưởng phòng, Báo cáo PHÒNG cho đúng trưởng phòng của phòng đó.

Vì sao đường dẫn tạm: Zalo không nhận file tải lên, nên app mở một đường công khai `GET /api/ban-tin/anh/<mã>.png`
chỉ tồn tại `HAN_ANH_GIAY` giây. Mã loại tổng = `<ngày số>.<hạn Unix>.<chữ ký>`; mã loại phòng =
`<ngày số>.<hạn Unix>.<mã phòng>.<chữ ký>`. Chữ ký HMAC-SHA256 bằng khoá dẫn xuất từ `APP_SECRET_KEY` (nhãn riêng, KHÁC khoá
webhook) và phủ cả loại + mã phòng, nên đổi mã phòng trong mã là chữ ký sai. Đường này chỉ có hai kiểu báo cáo cố định
(Báo cáo Tổng toàn chi nhánh, hoặc Báo cáo của MỘT phòng bán hàng ở chế độ bán hàng), không nhận tham số nào khác:
link của phòng A không mở được phòng B. Mã sai, hết hạn hay hỏng đều trả cùng một phản hồi 404, không tiết lộ lý do.
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
_TOI_DA_CACHE = 12
_cache: dict = {}


def _cong_tac(khoa: str) -> str:
    v = str(((config.rules_config().get("ban_tin") or {}).get(khoa)) or "anh").strip().lower()
    return "chu" if v == "chu" else "anh"


def cong_tac() -> str:
    """Ban Giám đốc: `anh` (mặc định) hoặc `chu` ở `config/rules.yml` → `ban_tin.bgd_dang`; giá trị lạ coi như `anh`."""
    return _cong_tac("bgd_dang")


def cong_tac_tp() -> str:
    """Trưởng phòng: `anh` (mặc định, ảnh phòng + ảnh tổng + nhận định) hoặc `chu` (hành vi cũ: tin chữ tổng quan + nhân sự)."""
    return _cong_tac("tp_dang")


def app_url() -> str:
    """Địa chỉ gốc https của app; Zalo chỉ tải được ảnh từ địa chỉ công khai https nên http / rỗng coi như chưa cài."""
    goc = (os.environ.get("APP_URL") or "").strip().rstrip("/")
    return goc if goc.lower().startswith("https://") else ""


def _ky(ngay_iso: str, han: int, phong: str | None = None) -> str:
    khoa = hmac.new(SECRET_KEY.encode(), _NHAN_KHOA, hashlib.sha256).digest()
    noi_dung = f"{ngay_iso}.{han}" if phong is None else f"{ngay_iso}.{han}.phong:{phong}"
    return hmac.new(khoa, noi_dung.encode(), hashlib.sha256).hexdigest()[:32]


def tao_ma(ngay_iso: str, bay_gio: float | None = None, phong: str | None = None) -> str:
    han = int((time.time() if bay_gio is None else bay_gio) + HAN_ANH_GIAY)
    if phong is None:
        return f"{ngay_iso}.{han}.{_ky(ngay_iso, han)}"
    return f"{ngay_iso}.{han}.{phong}.{_ky(ngay_iso, han, phong)}"


def _phong_hop_le(phong: str) -> bool:
    from app import ban_tin_phong as tp
    return phong in {p["code"] for p in tp.phong_chon_duoc()}


def doc_ma(ma: str, bay_gio: float | None = None) -> tuple[str, str | None] | None:
    """(ngày số YYYY-MM-DD, mã phòng hoặc None cho loại tổng) nếu mã đúng chữ ký, còn hạn, ngày số hợp lệ và (loại phòng)
    là phòng bán hàng; ngược lại None (không nói vì sao)."""
    try:
        phan = str(ma).split(".")
        if len(phan) not in (3, 4):
            return None
        ngay_iso, han_s, ky = phan[0], phan[1], phan[-1]
        phong = phan[2] if len(phan) == 4 else None
        han = int(han_s)
        if len(ngay_iso) != 10 or not hmac.compare_digest(ky.encode(), _ky(ngay_iso, han, phong).encode()):
            return None
        if han < (time.time() if bay_gio is None else bay_gio):
            return None
        moi = metrics.ngay_moi_nhat()
        if not (moi and date.fromisoformat(ngay_iso) <= date.fromisoformat(moi)):
            return None
        if phong is not None and not _phong_hop_le(phong):
            return None
        return ngay_iso, phong
    except Exception:
        return None


def url_anh(ngay_iso: str, phong: str | None = None) -> str | None:
    """Đường dẫn ảnh tạm cho một người nhận (hạn tính từ lúc gọi); None nếu chưa có `APP_URL` https."""
    goc = app_url()
    return f"{goc}{DUONG_DAN}{tao_ma(ngay_iso, phong=phong)}.png" if goc else None


def dung_anh(ngay_iso: str, phong: str | None = None) -> bytes:
    """PNG đúng ảnh nút "Chụp ảnh" của Báo cáo Tổng (toàn chi nhánh) hoặc, có `phong`, của Báo cáo phòng ở chế độ bán hàng:
    luỹ kế tới ngày số, số đã chốt, không nhận xét AI. Nhớ tạm theo (loại, phòng, ngày số, giờ nạp cuối) vài phút trong
    tiến trình; máy chủ khác thì tự dựng lại."""
    _, luc = overview.trang_thai_ngay(ngay_iso)
    khoa = (phong, ngay_iso, luc)
    cu = _cache.get(khoa)
    if cu and time.monotonic() - cu[0] < _TON_CACHE:
        return cu[1]
    d = date.fromisoformat(ngay_iso)
    luc_nap = luc if isinstance(luc, datetime) else None
    if phong is None:
        from app.export_png import anh_tong_quan
        png, _ = anh_tong_quan(f"{d.year}-{d.month:02d}", d.day, chi_phong=None, chi_nhanh="all",
                               tam_tinh=False, luc=luc_nap)
    else:
        from app.export_phong import anh_bao_cao_phong
        png, _ = anh_bao_cao_phong(f"{d.year}-{d.month:02d}", d.day, phong, tam_tinh=False, luc=luc_nap, che_do="ban_hang")
    if len(_cache) >= _TOI_DA_CACHE:
        _cache.pop(next(iter(_cache)))
    _cache[khoa] = (time.monotonic(), png)
    return png
