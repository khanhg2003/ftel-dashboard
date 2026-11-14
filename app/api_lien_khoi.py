"""Đường cho Zalo gọi vào bot GIAO VIỆC LIÊN KHỐI (nhánh thi-lien-khoi, xem app/lien_khoi/zalo_viec.py), không đăng nhập, xác thực bằng khoá
dẫn xuất từ APP_SECRET_KEY.

POST /api/lien-khoi/zalo-webhook : header `X-Bot-Api-Secret-Token`. Sai / thiếu khoá, hoặc chưa cấu hình gửi thật -> 403; đúng khoá thì LUÔN 200
(kể cả sự kiện lạ hay lỗi) để Zalo khỏi gửi lại.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

bp = Blueprint("api_lien_khoi", __name__)


@bp.post("/api/lien-khoi/zalo-webhook")
def webhook():
    from app.lien_khoi import zalo_viec
    if not zalo_viec.khoa_dung(request.headers.get("X-Bot-Api-Secret-Token")):
        return jsonify({"ok": False}), 403
    zalo_viec.xu_ly_su_kien(request.get_json(silent=True))
    return jsonify({"ok": True}), 200
