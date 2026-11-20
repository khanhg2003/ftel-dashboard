"""Đường cho đồng hồ (n8n / cron) gọi Bản tin 8h sáng, không đăng nhập, xác thực bằng khoá bí mật.

- POST /api/ban-tin/chay : header `X-Ban-Tin-Khoa: <BAN_TIN_KHOA>`; `?kho=1` = chạy thử (dựng nội dung, không gửi,
  không ghi nhật ký, trả luôn nội dung để xem; thêm `&phong=<mã>` thì kèm tin của đúng phòng đó cho trưởng phòng). App tự quyết có gửi không (xem app/ban_tin.py), gọi dư cũng không sao.
- GET /api/ban-tin/anh/<mã>.png : ảnh Báo cáo Tổng, hoặc Báo cáo của MỘT phòng (mã ký chứa loại + phòng), cho Zalo `sendPhoto`
  tự tải, KHÔNG đăng nhập, bảo vệ bằng mã ký có hạn 15 phút (xem app/ban_tin_anh.py). Mã sai / hết hạn đều trả đúng một phản hồi 404 giống hệt nhau.
- POST /api/ban-tin/zalo-webhook : Zalo gọi khi có người nhắn bot, header `X-Bot-Api-Secret-Token` (khoá dẫn xuất từ APP_SECRET_KEY).
- POST /api/ban-tin/tro-ly/chay : một vòng của Trợ lý điều hành cho đồng hồ bên ngoài, cùng khoá `X-Ban-Tin-Khoa`; CHỈ chạy khi `rules.yml` → `tro_ly_dieu_hanh` có `bat` và `tu_dong`
  đều true (mặc định tắt), tắt thì trả 403 giống sai khoá. Mặc định KHÔNG gắn vào lịch nào.
Thiếu biến môi trường hoặc sai khoá đều trả 403 giống hệt nhau, không tiết lộ gì thêm.
"""
from __future__ import annotations

import hmac
import os

from flask import Blueprint, Response, jsonify, request

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


@bp.post("/api/ban-tin/tro-ly/chay")
def tro_ly_chay():
    from app import tro_ly_dieu_hanh as tdh, tro_ly_dieu_hanh_so as so
    if not _khoa_dung(request.headers.get("X-Ban-Tin-Khoa")) or not (so.bat() and so.cau_hinh()["tu_dong"]):
        return jsonify({"ok": False}), 403
    try:
        kq = tdh.vong_tu_dong()
    except Exception as e:                      # chỉ trả tên lỗi: thông báo gốc có thể chứa chuỗi kết nối
        return jsonify({"ok": False, "loi": f"Lỗi khi chạy trợ lý điều hành ({type(e).__name__})."}), 500
    return jsonify({"ok": True, **kq}), 200


@bp.post("/api/ban-tin/zalo-webhook")
def zalo_webhook():
    """Zalo gọi khi có người nhắn bot (xem app/ban_tin_cho_duyet.py). Sai / thiếu khoá → 403 như đường trên;
    đúng khoá thì LUÔN trả 200 (kể cả sự kiện không dùng được hay lỗi database) để Zalo khỏi gửi lại."""
    from app import ban_tin_cho_duyet as cd
    if not cd.khoa_dung(request.headers.get("X-Bot-Api-Secret-Token")):
        return jsonify({"ok": False}), 403
    cd.xu_ly_su_kien(request.get_json(silent=True))
    return jsonify({"ok": True}), 200


@bp.get("/api/ban-tin/anh/<ma>.png")
def anh_bao_cao(ma: str):
    """Đường chỉ phát báo cáo cố định theo mã (không nhận tham số nào khác). Không ghi mã ra log ứng dụng."""
    from app import ban_tin_anh as ba
    khong_co = Response("Không tìm thấy.", 404, mimetype="text/plain")
    doc = ba.doc_ma(ma)
    if not doc:
        return khong_co
    try:
        png = ba.dung_anh(*doc)
    except Exception:
        return Response("Chưa dựng được ảnh.", 500, mimetype="text/plain")
    r = Response(png, 200, mimetype="image/png")
    r.headers["Cache-Control"] = "private, no-store"
    return r
