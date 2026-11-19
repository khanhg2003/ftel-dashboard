"""Nhận lead bằng cách trả lời tin cảnh báo trong nhóm Zalo (chốt với người dùng 19/11/2026).

Tin cảnh báo SLA (`app/canh_bao_lead.py`) có dòng "Mã: #<id>". Sale trả lời trong đúng nhóm đang cấu hình
nhận cảnh báo, nêu cả MÃ LEAD lẫn TÊN MÌNH, ví dụ "Hiếu nhận #42" - bot gọi thẳng `leads.nhan_cheo` (hàm
đã dùng cho nút "Nhận chéo" trong app) rồi trả lời xác nhận. **Bắt buộc có mã lead**: Zalo Bot ở app này
chỉ gửi được chữ trơn, không có nút bấm / reply-threading đáng tin cậy (`app/zalo_bot.py` không trả về
`message_id` của tin đã gửi), nên không biết "đang trả lời tin nào" nếu không có mã trong câu - nhóm có
thể có nhiều lead quá hạn cùng lúc. Không có mã trong câu thì BỎ QUA HẲN (không trả lời) để khỏi làm ồn
nhóm với những tin trò chuyện bình thường khác.

Khung copy từ `app/zalo_gia.py` (webhook nhận tin, so khớp theo quy tắc không AI, dedup theo message_id).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re

from sqlalchemy.exc import IntegrityError

from app import leads, zalo_bot
from app.config import SECRET_KEY
from app.db import engine, session_scope
from app.models import Lead, LeadZaloTin
from app.zalo_gia import bo_dau, bo_mention, doc_tin

_da_tao = False
_RE_MA = re.compile(r"#\s*(\d+)")
DUONG_DAN = "/api/lead/zalo-webhook"


def url_webhook() -> str | None:
    goc = (os.environ.get("APP_URL") or "").strip().rstrip("/")
    return f"{goc}{DUONG_DAN}" if goc else None


def dam_bao_bang() -> None:
    global _da_tao
    if not _da_tao:
        LeadZaloTin.__table__.create(engine, checkfirst=True)
        _da_tao = True


def khoa_webhook() -> str:
    """HMAC-SHA256(APP_SECRET_KEY, "zalo-lead-webhook") dạng hex - khác khoá webhook bot Tra giá / Bản tin."""
    return hmac.new(SECRET_KEY.encode(), b"zalo-lead-webhook", hashlib.sha256).hexdigest()


def khoa_dung(khoa: str | None) -> bool:
    return hmac.compare_digest((khoa or "").encode(), khoa_webhook().encode())


def _nhom_cho_phep() -> set[str]:
    """Chat_id các nhóm đang nhận cảnh báo SLA (vai trò leader) - chỉ nhận lệnh "nhận lead" từ đúng nhóm này."""
    from app import canh_bao_lead as cb
    return {n["chat_id"] for n in cb.ds_nguoi_nhan() if n["vai_tro"] == "leader" and n["bat"]}


def _khop_nguoi(chuoi: str) -> str | None:
    """Tên trong câu (bỏ dấu, không phân biệt hoa thường) khớp đúng 1 trong 5 người Phòng Online - so theo
    cả họ tên đầy đủ lẫn tên gọi (từ cuối của họ tên, cách gọi phổ biến, vd "Hiếu" trong "Ngô Trung Hiếu")."""
    sach = f" {bo_dau(chuoi)} "
    for a in leads.nguoi_online():
        ten = bo_dau(a["ten"] or "")
        cum = {ten, ten.split()[-1]} if ten else set()
        cum.add(bo_dau(a["acc_norm"] or ""))
        if any(c and f" {c} " in sach for c in cum):
            return a["acc_norm"]
    return None


def _da_nhan(ma_tin: str, chat_id: str) -> bool:
    """Ghi tin vào sổ; True nếu tin này đã xử lý rồi (Zalo gửi lại sự kiện) - IntegrityError chỉ ném ra lúc
    commit (cuối `with session_scope()`), nên phải bọc try quanh CẢ khối, không phải quanh mỗi `s.add`."""
    dam_bao_bang()
    try:
        with session_scope() as s:
            s.add(LeadZaloTin(ma_tin=ma_tin, chat_id=chat_id))
    except IntegrityError:
        return True
    return False


def _tra_loi(chat_id: str, noi_dung: str) -> None:
    try:
        zalo_bot.gui_tin_du_phong(chat_id, noi_dung, token=os.environ.get("ZALO_LEAD_TOKEN"))
    except zalo_bot.LoiZalo:
        pass


def _ghi_debug(nhan: str, payload) -> None:
    """Ghi vắn tắt những lượt KHÔNG xử lý được (không đọc được sự kiện / không có mã) vào app.log, để dò khi
    tính năng còn mới - vd xem Zalo có gửi kiểu sự kiện khác cho tin TRẢ LỜI (reply) hay không. Nội dung là
    tin nội bộ của nhóm sale (không phải dữ liệu khách hàng), nhưng vẫn cắt ngắn cho gọn log."""
    try:
        chu = json.dumps(payload, ensure_ascii=False)
    except TypeError:
        chu = str(payload)
    logging.getLogger(__name__).info("Lead Zalo (%s): %s", nhan, chu[:500])


def _xu_ly(payload) -> None:
    tin = doc_tin(payload)
    if not tin:
        _ghi_debug("khong_doc_duoc", payload)
        return
    if tin["la_bot"]:
        return
    chat_id = tin["chat_id"]
    if chat_id not in _nhom_cho_phep():
        return
    ma = _RE_MA.search(tin["text"])
    if not ma:
        _ghi_debug("khong_co_ma", payload)
        return                                      # không có mã lead -> không phải lệnh nhận, im lặng
    if _da_nhan(tin["ma_tin"], chat_id):
        return
    lead_id = int(ma.group(1))
    chu = bo_mention(tin["text"])
    acc = _khop_nguoi(chu)
    with session_scope() as s:
        r = s.get(Lead, lead_id)
        ten_lead = None if r is None else (r.ten_kh or f"#{lead_id}")
        da_dong = r is not None and r.tinh_trang_xu_ly in leads.TRANG_THAI_DONG
    if r is None:
        _tra_loi(chat_id, f"Không tìm thấy lead #{lead_id}.")
        return
    if da_dong:
        _tra_loi(chat_id, f"Lead #{lead_id} ({ten_lead}) đã xong ({r.tinh_trang_xu_ly}), không cần nhận nữa.")
        return
    if not acc:
        _tra_loi(chat_id, f"Chưa rõ ai nhận lead #{lead_id} - trả lời kèm tên (vd \"Hiếu nhận #{lead_id}\").")
        return
    try:
        leads.nhan_cheo(lead_id, acc, "zalo")
    except leads.LoiLead as e:
        _tra_loi(chat_id, str(e))
        return
    ten_nguoi = next((a["ten"] for a in leads.nguoi_online() if a["acc_norm"] == acc), acc)
    _tra_loi(chat_id, f"Đã gán lead #{lead_id} ({ten_lead}) cho {ten_nguoi}.")


def xu_ly_su_kien(payload) -> None:
    """Không bao giờ ném lỗi: webhook phải trả 200 để Zalo khỏi gửi lại."""
    try:
        _xu_ly(payload)
    except Exception:
        logging.getLogger(__name__).exception("Lead Zalo: lỗi khi xử lý sự kiện")


def ghi_debug_request(dung_khoa: bool) -> None:
    """[TẠM, dò lượt nhận lead qua Zalo 19/11/2026] mọi lượt POST tới /api/lead/zalo-webhook, kể cả sai khoá -
    để biết chắc Zalo có gọi webhook này hay không. Xoá khi đã rõ nguyên nhân tin trả lời/trích dẫn không nhận được."""
    logging.getLogger(__name__).info("Lead Zalo: có lượt gọi webhook, khoá %s", "đúng" if dung_khoa else "SAI")
