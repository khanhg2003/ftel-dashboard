"""Đường nhận dữ liệu quảng cáo từ n8n (không cần đăng nhập, xác thực bằng mã kết nối ở Quản trị → Ads IBB7).

- POST /api/ads/chi-tieu : n8n 7h30 gửi chi tiêu hôm qua. JSON: {"page": "KON TUM", "rows": [{"camp": "...",
  "tinh_trang": "HOẠT ĐỘNG", "ngay": "2026-09-18", "chi_tieu": 4.56, "tin_nhan": 3}]} (hoặc danh sách dòng có "page").
- POST /api/ads/lead     : bot Telegram báo có số / PTTB. JSON: {"page": "QUẢNG NGÃI", "lead": 1, "pttb": 1,
  "ngay": "2026-09-19" (bỏ trống = hôm nay), "nguoi": "tên người nhập", "ghi_chu": "..."}.
Mã kết nối gửi ở header `X-Ads-Token` (hoặc tham số ?token=). Gửi lại cùng page + camp + ngày thì ghi đè.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from app import ads

bp = Blueprint("api_ads", __name__)


def _xu_ly(ham):
    tok = request.headers.get("X-Ads-Token") or request.args.get("token")
    if not ads.kiem_token(tok):
        return jsonify({"ok": False, "loi": "Sai hoặc thiếu mã kết nối (X-Ads-Token)."}), 401
    du_lieu = request.get_json(silent=True)
    if du_lieu is None:
        return jsonify({"ok": False, "loi": "Nội dung phải là JSON."}), 400
    try:
        kq = ham(du_lieu)
    except ads.LoiAds as e:
        return jsonify({"ok": False, "loi": str(e)}), 400
    return jsonify({"ok": not kq["loi"], **kq}), 200


@bp.post("/api/ads/chi-tieu")
def chi_tieu():
    return _xu_ly(lambda d: ads.nhan_chi_tieu(d, nguon="n8n", nguoi="n8n"))


@bp.post("/api/ads/lead")
def lead():
    return _xu_ly(lambda d: ads.nhan_lead(d, nguon="telegram", nguoi=None))
