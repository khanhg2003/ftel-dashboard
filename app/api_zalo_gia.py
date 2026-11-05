"""Đường cho Zalo gọi vào bot TRA CỨU GIÁ (xem app/zalo_gia.py), không đăng nhập, xác thực bằng khoá dẫn xuất từ APP_SECRET_KEY.

GET /api/zalo-gia/anh/<mã>.png : banner một gói cho Zalo `sendPhoto` tự tải, mã ký có hạn (app/zalo_gia_anh.py), 404 chung.
POST /api/zalo-gia/webhook : header `X-Bot-Api-Secret-Token`. Sai / thiếu khoá -> 403; đúng khoá thì LUÔN 200 (kể cả sự kiện lạ
hay lỗi) để Zalo khỏi gửi lại.
"""
from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

bp = Blueprint("api_zalo_gia", __name__)


@bp.post("/api/zalo-gia/webhook")
def webhook():
    from app import zalo_gia
    if not zalo_gia.khoa_dung(request.headers.get("X-Bot-Api-Secret-Token")):
        return jsonify({"ok": False}), 403
    zalo_gia.xu_ly_su_kien(request.get_json(silent=True))
    return jsonify({"ok": True}), 200


@bp.get("/api/zalo-gia/anh/<ma>.png")
def anh_banner(ma: str):
    """Banner đúng MỘT gói theo mã ký có hạn (xem app/zalo_gia_anh.py), không nhận tham số nào khác. Mã sai / hết hạn / hỏng /
    dựng lỗi đều trả cùng một 404 giống hệt nhau; không ghi mã ra log."""
    from app import zalo_gia_anh as za
    khong_co = Response("Không tìm thấy.", 404, mimetype="text/plain")
    doc = za.doc_ma(ma)
    if not doc:
        return khong_co
    try:
        png = za.dung_theo_ma(*doc)
    except Exception:
        return khong_co
    r = Response(png, 200, mimetype="image/png")
    r.headers["Cache-Control"] = "private, no-store"
    return r
