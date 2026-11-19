"""Đường cho cron gọi cảnh báo SLA lead, và webhook Messenger tự bắt lead - không đăng nhập, tự xác thực.

- POST /api/lead/canh-bao : header `X-Lead-Khoa: <LEAD_CANH_BAO_KHOA>`, gọi mỗi 15-30 phút (n8n / Render Cron Job).
  Cùng lượt còn đồng bộ KHTN của Phòng Online từ Lead Online (`bao_cao_ngay.dong_bo_khtn`, chốt 19/11/2026).
- GET  /api/lead/fb-webhook : Meta xác thực lần đầu khi khai báo webhook (so khớp `FB_WEBHOOK_VERIFY_TOKEN`).
- POST /api/lead/fb-webhook : Meta gọi khi page nhận tin nhắn Messenger - LUÔN trả 200 khi chữ ký đúng (kể cả sự
  kiện không dùng được, để Meta khỏi gửi lại), xác minh `X-Hub-Signature-256` bằng HMAC-SHA256 với `FB_APP_SECRET`
  trước khi xử lý - đường này public, không đăng nhập, phải tự bảo vệ bằng chữ ký của Meta.
- POST /api/lead/zalo-webhook : Zalo gọi khi nhóm cảnh báo SLA có tin mới (`app/leads_zalo_nhan.py`, "nhận
  lead" bằng cách trả lời kèm mã). Header `X-Bot-Api-Secret-Token` so khớp khoá dẫn xuất từ `APP_SECRET_KEY`
  (đúng kiểu webhook bot Tra giá / Bản tin), LUÔN trả 200 để Zalo khỏi gửi lại.
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
    from app import bao_cao_ngay
    try:                                         # đồng bộ KHTN của Phòng Online - lỗi ở đây không chặn kết quả cảnh báo SLA
        kq["khtn_dong_bo"] = bao_cao_ngay.dong_bo_khtn()
    except Exception:
        kq["khtn_dong_bo"] = None
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


@bp.post("/api/lead/zalo-webhook")
def zalo_webhook():
    from app import leads_zalo_nhan
    dung_khoa = leads_zalo_nhan.khoa_dung(request.headers.get("X-Bot-Api-Secret-Token"))
    # [TẠM, dò lượt nhận lead qua Zalo 19/11/2026] log mọi lượt gọi tới đường này, kể cả sai khoá, để biết
    # chắc Zalo CÓ gọi webhook hay không trước khi dò tiếp phần đọc sự kiện - xoá khi đã rõ nguyên nhân.
    leads_zalo_nhan.ghi_debug_request(dung_khoa)
    if not dung_khoa:
        return jsonify({"ok": False}), 403
    leads_zalo_nhan.xu_ly_su_kien(request.get_json(silent=True))
    return jsonify({"ok": True}), 200
