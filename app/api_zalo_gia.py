"""Đường cho Zalo gọi vào bot TRA CỨU GIÁ (xem app/zalo_gia.py), không đăng nhập, xác thực bằng khoá dẫn xuất từ APP_SECRET_KEY.

POST /api/zalo-gia/webhook : header `X-Bot-Api-Secret-Token`. Sai / thiếu khoá -> 403; đúng khoá thì LUÔN 200 (kể cả sự kiện lạ
hay lỗi) để Zalo khỏi gửi lại.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

bp = Blueprint("api_zalo_gia", __name__)


@bp.post("/api/zalo-gia/webhook")
def webhook():
    from app import zalo_gia
    if not zalo_gia.khoa_dung(request.headers.get("X-Bot-Api-Secret-Token")):
        return jsonify({"ok": False}), 403
    zalo_gia.xu_ly_su_kien(request.get_json(silent=True))
    return jsonify({"ok": True}), 200

