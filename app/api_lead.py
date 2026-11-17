"""Đường cho cron gọi cảnh báo SLA lead, và webhook Messenger tự bắt lead - không đăng nhập, tự xác thực.

- POST /api/lead/canh-bao : header `X-Lead-Khoa: <LEAD_CANH_BAO_KHOA>`, gọi mỗi 15-30 phút (n8n / Render Cron Job).
- GET  /api/lead/fb-webhook : Meta xác thực lần đầu khi khai báo webhook (so khớp `FB_WEBHOOK_VERIFY_TOKEN`).
- POST /api/lead/fb-webhook : Meta gọi khi page nhận tin nhắn Messenger - LUÔN trả 200 khi chữ ký đúng (kể cả sự
  kiện không dùng được, để Meta khỏi gửi lại), xác minh `X-Hub-Signature-256` bằng HMAC-SHA256 với `FB_APP_SECRET`
  trước khi xử lý - đường này public, không đăng nhập, phải tự bảo vệ bằng chữ ký của Meta.
"""
from __future__ import annotations

import hashlib
import hmac
import os

from flask import Blueprint, jsonify, request

bp = Blueprint("api_lead", __name__)


def _khoa_dung(khoa: str | None) -> bool:
    that = (os.environ.get("LEAD_CANH_BAO_KHOA") or "").encode()
    return bool(that) and hmac.compare_digest((khoa or "").encode(), that)


@bp.post("/api/lead/canh-bao")
def canh_bao():
    if not _khoa_dung(request.headers.get("X-Lead-Khoa")):
        return jsonify({"ok": False}), 403
    from app import canh_bao_lead
    try:
        kq = canh_bao_lead.quet_va_canh_bao()
    except Exception as e:                      # chỉ trả tên lỗi: thông báo gốc có thể chứa chuỗi kết nối
        return jsonify({"ok": False, "loi": f"Lỗi khi quét cảnh báo lead ({type(e).__name__})."}), 500
    return jsonify({"ok": True, **kq}), 200


@bp.get("/api/lead/fb-webhook")
def fb_verify():
    """Meta gọi khi khai báo URL callback: trả đúng `hub.challenge` nếu `hub.verify_token` khớp."""
    token = (os.environ.get("FB_WEBHOOK_VERIFY_TOKEN") or "").strip()
    if (not token or request.args.get("hub.mode") != "subscribe"
            or not hmac.compare_digest(request.args.get("hub.verify_token") or "", token)):
        return "Từ chối.", 403
    return request.args.get("hub.challenge") or "", 200


def _chu_ky_dung(body: bytes, chu_ky: str | None) -> bool:
    secret = (os.environ.get("FB_APP_SECRET") or "").strip()
    if not secret or not chu_ky or not chu_ky.startswith("sha256="):
        return False
    tinh = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(tinh, chu_ky[len("sha256="):])


@bp.post("/api/lead/fb-webhook")
def fb_webhook():
    if not _chu_ky_dung(request.get_data(), request.headers.get("X-Hub-Signature-256")):
        return jsonify({"ok": False}), 403
    from app import leads_messenger
    leads_messenger.xu_ly_su_kien(request.get_json(silent=True) or {})
    return jsonify({"ok": True}), 200


@bp.post("/api/lead/zalo-dich-nhom")
def zalo_dich_nhom():
    """TẠM THỜI (chốt 17/11/2026): ghi log thô sự kiện bot Zalo mới để tìm chat_id của 1 nhóm - xoá đường này
    và webhook phía Zalo sau khi lấy được chat_id, không dùng lâu dài."""
    from app.auth import ghi_log
    ghi_log("lead_zalo_dich_nhom", request.get_data(as_text=True)[:2000])
    return jsonify({"ok": True}), 200
