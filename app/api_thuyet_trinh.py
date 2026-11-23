"""Đường cho trang Thuyết trình AI xin giọng đọc tiếng Việt (xem app/thuyet_trinh_giong.py). Cần đăng nhập (bộ chặn chung của app) VÀ là Ban Giám đốc (`duoc_cau_hinh`).

POST /api/thuyet-trinh/doc  {"chu": "một câu"}  ->  audio/mpeg; lỗi trả JSON {"loi": "..."} bằng tiếng Việt.
"""
from __future__ import annotations

from flask import Blueprint, Response, jsonify, request
from flask_login import current_user

bp = Blueprint("api_thuyet_trinh", __name__)


@bp.post("/api/thuyet-trinh/doc")
def doc():
    from app import thuyet_trinh_giong as giong, tro_ly
    if not getattr(current_user, "duoc_cau_hinh", False):
        return jsonify({"loi": "Chỉ Ban Giám đốc dùng được giọng đọc này."}), 403
    chu = (request.get_json(silent=True) or {}).get("chu")
    try:
        am = giong.doc(current_user, chu if isinstance(chu, str) else "")
    except tro_ly.LoiAI as e:
        return jsonify({"loi": str(e)}), 400
    except Exception:                                        # không để lộ chi tiết kỹ thuật
        return jsonify({"loi": "Chưa tạo được giọng đọc, thử lại sau."}), 502
    return Response(am, mimetype="audio/mpeg", headers={"Cache-Control": "private, max-age=3600"})
