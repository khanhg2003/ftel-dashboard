"""Thêm người nhận Bản tin 8h bằng cách NHẮN BOT: Zalo gọi webhook của app, app ghi người đó vào danh sách "chờ duyệt",
Quản trị bấm Thêm ở tab Bản tin Zalo.

Vì sao webhook: lấy chat_id bằng getUpdates phải chạy lệnh tay, và Zalo chỉ cho dùng MỘT trong hai (webhook hoặc
getUpdates). Khoá webhook DẪN XUẤT từ `APP_SECRET_KEY` nên không phải lưu thêm gì; đổi `APP_SECRET_KEY` thì bấm
"Kết nối webhook" lại. Không lưu nội dung tin nhắn, chỉ chat_id + tên hiển thị + hai mốc giờ.
"""
from __future__ import annotations

import hashlib
import hmac
import os

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app import ban_tin, zalo_bot
from app.auth import ghi_log
from app.config import SECRET_KEY
from app.db import engine, session_scope
from app.models import BanTinChoDuyet, BanTinNguoiNhan
from app.thoi_gian import chu_gio_vn, utc_bay_gio

DUONG_DAN = "/api/ban-tin/zalo-webhook"
LOI_CHAO = "Đã ghi nhận. Quản trị viên sẽ duyệt để bạn nhận bản tin hằng ngày."
LOAI_CHAT_RIENG = ("PRIVATE", "USER")        # tài liệu Zalo: chat_type PRIVATE hoặc GROUP (nhóm đang Beta, bỏ qua)


def dam_bao_bang() -> None:
    try:
        BanTinChoDuyet.__table__.create(bind=engine, checkfirst=True)
    except Exception:
        pass


dam_bao_bang()


# ------------------------------------------------------------------ khoá và địa chỉ webhook
def khoa_webhook() -> str:
    """HMAC-SHA256(APP_SECRET_KEY, "zalo-webhook") dạng hex: 64 ký tự, nằm trong khoảng 8-256 mà Zalo yêu cầu."""
    return hmac.new(SECRET_KEY.encode(), b"zalo-webhook", hashlib.sha256).hexdigest()


def khoa_dung(khoa: str | None) -> bool:
    return hmac.compare_digest((khoa or "").encode(), khoa_webhook().encode())


def url_webhook() -> str | None:
    goc = (os.environ.get("APP_URL") or "").strip().rstrip("/")
    return f"{goc}{DUONG_DAN}" if goc else None


# ------------------------------------------------------------------ nhận sự kiện
def _chat_rieng(payload) -> tuple[str, str] | None:
    """(chat_id, tên hiển thị) nếu là tin nhắn riêng của người thật, ngược lại None."""
    if not isinstance(payload, dict):
        return None
    ev = str(payload.get("event_name") or "")
    msg = payload.get("message")
    if not (ev.startswith("message.") and ev.endswith(".received")) or not isinstance(msg, dict):
        return None
    nguoi, chat = msg.get("from"), msg.get("chat")
    if not isinstance(nguoi, dict) or not isinstance(chat, dict) or nguoi.get("is_bot"):
        return None
    if str(chat.get("chat_type") or "").upper() not in LOAI_CHAT_RIENG:
        return None
    chat_id = str(chat.get("id") or "").strip()[:80]
    if not chat_id:
        return None
    return chat_id, (str(nguoi.get("display_name") or "").strip() or "Chưa rõ tên")[:120]


def ghi_nhan(payload) -> bool:
    """Ghi người nhắn vào danh sách chờ. True khi đây là người MỚI vào danh sách (để bot chào một lần)."""
    kq = _chat_rieng(payload)
    if not kq:
        return False
    chat_id, ten = kq
    bay_gio = utc_bay_gio()
    try:
        with session_scope() as s:
            if s.execute(select(BanTinNguoiNhan.id).where(BanTinNguoiNhan.chat_id == chat_id).limit(1)).first():
                return False
            dong = s.execute(select(BanTinChoDuyet).where(BanTinChoDuyet.chat_id == chat_id)).scalar_one_or_none()
            if dong:
                dong.nhan_cuoi, dong.ten = bay_gio, ten
                return False
            s.add(BanTinChoDuyet(chat_id=chat_id, ten=ten, nhan_dau=bay_gio, nhan_cuoi=bay_gio))
        return True
    except IntegrityError:          # hai tin tới cùng lúc: dòng kia đã vào trước, người này không còn là "mới"
        return False


def xu_ly_su_kien(payload) -> None:
    """Không bao giờ ném lỗi: webhook phải trả 200 để Zalo khỏi gửi lại."""
    try:
        moi = ghi_nhan(payload)
    except Exception:
        return
    if not moi:
        return
    chat_id = _chat_rieng(payload)[0]
    try:
        zalo_bot.gui_tin(chat_id, LOI_CHAO, han=4)
    except Exception:               # chào hỏng không làm mất việc ghi
        pass


# ------------------------------------------------------------------ danh sách chờ
def ds_cho_duyet() -> list[dict]:
    with session_scope() as s:
        q = select(BanTinChoDuyet).order_by(BanTinChoDuyet.nhan_cuoi.desc(), BanTinChoDuyet.id.desc())
        return [{"id": r.id, "ten": r.ten, "chat_id": r.chat_id, "nhan_cuoi": chu_gio_vn(r.nhan_cuoi)}
                for r in s.execute(q).scalars()]


def duyet(id_: int, ten: str, loai: str, phong: list[str] | None = None) -> tuple[bool, str]:
    """Biến một người chờ thành người nhận (bật) rồi xoá khỏi danh sách chờ. `phong` chỉ dùng cho loại trưởng phòng."""
    with session_scope() as s:
        r = s.get(BanTinChoDuyet, int(id_))
        chat_id = r.chat_id if r else None
        ten_san = r.ten if r else ""
    if not chat_id:
        return False, "Người này không còn trong danh sách chờ (có thể đã được duyệt hoặc bỏ qua)."
    if any(n["chat_id"] == chat_id for n in ban_tin.ds_nguoi_nhan()):
        bo_qua([id_], ghi=False)
        return False, "Người này đã là người nhận bản tin."
    ok, msg = ban_tin.luu_nguoi_nhan(None, (ten or "").strip() or ten_san, loai, chat_id, True, phong)
    if ok:
        bo_qua([id_], ghi=False)
        ghi_log("ban_tin_cho_duyet", f"Duyệt {ten or ten_san} (chat_id {chat_id}) làm người nhận loại {loai}")
    return ok, msg


def bo_qua(ids: list[int], ghi: bool = True) -> int:
    ids = [int(i) for i in ids]
    if not ids:
        return 0
    with session_scope() as s:
        n = int(s.execute(delete(BanTinChoDuyet).where(BanTinChoDuyet.id.in_(ids))).rowcount or 0)
    if n and ghi:
        ghi_log("ban_tin_cho_duyet", f"Bỏ qua {n} người chờ duyệt: {ids}")
    return n


# ------------------------------------------------------------------ kết nối webhook (setWebhook / deleteWebhook / getWebhookInfo)
def trang_thai_webhook() -> tuple[str, str]:
    """(mức ok|warn|bad, câu giải thích) từ getWebhookInfo so với địa chỉ app."""
    if not zalo_bot.da_cau_hinh():
        return "warn", "Máy chủ chưa cài biến ZALO_BOT_TOKEN nên chưa kết nối được."
    mong = url_webhook()
    try:
        url = zalo_bot.thong_tin_webhook()["url"]
    except zalo_bot.LoiZalo as e:
        return "bad", f"Không hỏi được trạng thái kết nối: {e}"
    if not url:
        return "warn", ("Chưa kết nối. Bấm “Kết nối webhook” để người nhắn bot tự hiện trong danh sách chờ."
                        if mong else "Chưa kết nối, và máy chủ chưa cài biến APP_URL (địa chỉ app) nên chưa kết nối được.")
    if mong and url == mong:
        return "ok", "Đã kết nối: người nhắn bot sẽ tự hiện trong danh sách chờ duyệt."
    return "warn", ("Bot đang trỏ tới một địa chỉ khác, không phải app này. Bấm “Kết nối webhook” để trỏ về app."
                    if mong else "Bot đang đặt webhook ở một địa chỉ khác, và máy chủ chưa cài biến APP_URL.")


def ket_noi() -> tuple[str, str]:
    """(mức, câu báo). Không có APP_URL thì KHÔNG gọi Zalo: không đoán địa chỉ."""
    if not zalo_bot.da_cau_hinh():
        return "bad", "Máy chủ chưa cài biến ZALO_BOT_TOKEN."
    url = url_webhook()
    if not url:
        return "bad", "Cần cài biến APP_URL (địa chỉ app, vd https://ten-app.vercel.app) trên máy chủ trước khi kết nối."
    if not url.startswith("https://"):
        return "bad", "APP_URL phải bắt đầu bằng https:// thì Zalo mới nhận."
    try:
        kq = zalo_bot.dat_webhook(url, khoa_webhook())
    except zalo_bot.LoiZalo as e:
        return "bad", f"Kết nối thất bại: {e}"
    ghi_log("ban_tin_webhook", "Kết nối webhook Zalo")
    if not kq["kiem_tra_ok"]:
        return "warn", (f"Đã lưu địa chỉ nhưng Zalo gọi thử chưa được ({kq['ket_qua_kiem_tra'] or 'không rõ lý do'}). "
                        "Kiểm tra app đã triển khai bản mới chưa rồi bấm lại.")
    return "ok", "Đã kết nối webhook. Từ giờ người nhắn bot sẽ hiện trong danh sách chờ duyệt."


def ngat_ket_noi() -> tuple[str, str]:
    try:
        zalo_bot.go_webhook()
    except zalo_bot.LoiZalo as e:
        return "bad", f"Ngắt kết nối thất bại: {e}"
    ghi_log("ban_tin_webhook", "Ngắt webhook Zalo")
    return "ok", "Đã ngắt kết nối. Người nhắn bot sẽ không tự hiện trong danh sách chờ nữa."
