"""Đường cho Zalo gọi vào bot GIAO VIỆC LIÊN KHỐI (nhánh thi-lien-khoi, xem app/lien_khoi/zalo_viec.py), không đăng nhập, xác thực bằng khoá
dẫn xuất từ APP_SECRET_KEY.

POST /api/lien-khoi/zalo-webhook : header `X-Bot-Api-Secret-Token`. Sai / thiếu khoá, hoặc chưa cấu hình gửi thật -> 403; đúng khoá thì LUÔN 200
(kể cả sự kiện lạ hay lỗi) để Zalo khỏi gửi lại.
GET /lien-khoi/xuat.xlsx?ql=<mã quản lý>&loc=<bộ lọc> : file Excel danh sách việc, CẦN đăng nhập + quyền Quản trị (đường này không nằm trong nhóm miễn đăng nhập).
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


@bp.get("/lien-khoi/xuat.xlsx")
def xuat_excel():
    """Tải danh sách việc (phạm vi một quản lý, bộ lọc "Xem") thành Excel. Cần đăng nhập (kiểm ở `_bat_buoc_dang_nhap`) và quyền Quản trị như trang Theo dõi."""
    from flask import Response
    from flask_login import current_user
    from app.lien_khoi import xuat
    if not getattr(current_user, "duoc_cau_hinh", False):
        return Response("Không có quyền.", status=403)
    ql, loc = request.args.get("ql") or "all", request.args.get("loc") or "mo"
    return Response(xuat.xuat_excel(ql, loc), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{xuat.ten_file(ql)}"'})
