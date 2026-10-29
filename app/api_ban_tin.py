"""Đường cho đồng hồ (n8n / cron) gọi Bản tin 8h sáng, không đăng nhập, xác thực bằng khoá bí mật.

- POST /api/ban-tin/chay : header `X-Ban-Tin-Khoa: <BAN_TIN_KHOA>`; `?kho=1` = chạy thử (dựng nội dung, không gửi,
  không ghi nhật ký, trả luôn nội dung để xem; thêm `&phong=<mã>` thì kèm tin của đúng phòng đó cho trưởng phòng). App tự quyết có gửi không (xem app/ban_tin.py), gọi dư cũng không sao.
- POST /api/ban-tin/zalo-webhook : Zalo gọi khi có người nhắn bot, header `X-Bot-Api-Secret-Token` (khoá dẫn xuất từ APP_SECRET_KEY).
Thiếu biến môi trường hoặc sai khoá đều trả 403 giống hệt nhau, không tiết lộ gì thêm.
"""
from __future__ import annotations

import hmac
import os

from flask import Blueprint, jsonify, request

bp = Blueprint("api_ban_tin", __name__)


def _khoa_dung(khoa: str | None) -> bool:
    that = (os.environ.get("BAN_TIN_KHOA") or "").encode()
    return bool(that) and hmac.compare_digest((khoa or "").encode(), that)


@bp.post("/api/ban-tin/chay")
def chay():
    if not _khoa_dung(request.headers.get("X-Ban-Tin-Khoa")):
        return jsonify({"ok": False}), 403
    from app import ban_tin
    kho = request.args.get("kho", "").lower() in ("1", "true", "yes")
    try:
        kq = ban_tin.chay(kho=kho, phong=request.args.get("phong") if kho else None)
    except Exception as e:                      # chỉ trả tên lỗi: thông báo gốc có thể chứa chuỗi kết nối
        return jsonify({"ok": False, "loi": f"Lỗi khi chạy bản tin ({type(e).__name__})."}), 500
    kq.setdefault("noi_dung", None)
    if not kho:
        kq.pop("noi_dung")
    return jsonify({"ok": not kq["loi"], **kq}), 200


@bp.post("/api/ban-tin/zalo-webhook")
def zalo_webhook():
    """Zalo gọi khi có người nhắn bot (xem app/ban_tin_cho_duyet.py). Sai / thiếu khoá → 403 như đường trên;
    đúng khoá thì LUÔN trả 200 (kể cả sự kiện không dùng được hay lỗi database) để Zalo khỏi gửi lại."""
    from app import ban_tin_cho_duyet as cd
    if not cd.khoa_dung(request.headers.get("X-Bot-Api-Secret-Token")):
        return jsonify({"ok": False}), 403
    cd.xu_ly_su_kien(request.get_json(silent=True))
    return jsonify({"ok": True}), 200
