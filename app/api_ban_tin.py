"""Đường cho đồng hồ (n8n / cron) gọi Bản tin 8h sáng, không đăng nhập, xác thực bằng khoá bí mật.

- POST /api/ban-tin/chay : header `X-Ban-Tin-Khoa: <BAN_TIN_KHOA>`; `?kho=1` = chạy thử (dựng nội dung, không gửi,
  không ghi nhật ký, trả luôn nội dung để xem). App tự quyết có gửi không (xem app/ban_tin.py), gọi dư cũng không sao.
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
        kq = ban_tin.chay(kho=kho)
    except Exception as e:                      # chỉ trả tên lỗi: thông báo gốc có thể chứa chuỗi kết nối
        return jsonify({"ok": False, "loi": f"Lỗi khi chạy bản tin ({type(e).__name__})."}), 500
    kq.setdefault("noi_dung", None)
    if not kho:
        kq.pop("noi_dung")
    return jsonify({"ok": not kq["loi"], **kq}), 200
