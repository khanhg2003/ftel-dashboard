"""Cảnh báo SLA lead quá 24h chưa được care, báo qua Zalo. Dùng BOT RIÊNG cho Lead Online (`ZALO_LEAD_TOKEN`,
chốt với người dùng 17/11/2026 - ban đầu định dùng lại bot Bản tin nhưng người dùng muốn gửi thẳng vào 1 nhóm
Zalo chung, nên tạo bot mới: một bot chỉ gắn được một webhook, bot Bản tin đang dùng webhook của nó).

Người nhận một lần cảnh báo: sale đang phụ trách + người được đề xuất nhận chéo (ít lead đang xử lý nhất trong
nhóm, xem `app/leads.py` `de_xuat_nhan_cheo`) + mọi người vai trò "leader" đang bật (`LeadNguoiNhanCanhBao` -
thường là chat_id của MỘT nhóm Zalo chung, khai vai trò `leader`, không phải từng người riêng).
Không nhắc lại cho cùng 1 lead trước `CHU_KY_NHAC_LAI_GIO` giờ kể từ lần cảnh báo trước (`Lead.canh_bao_luc`).
Gọi `quet_va_canh_bao()` từ `app/api_lead.py` (cron bên ngoài gọi mỗi 15-30 phút).
"""
from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy import select

from app import leads, zalo_bot
from app.db import engine, session_scope
from app.models import AuditLog, CrmPage, Lead, LeadNguoiNhanCanhBao

CHU_KY_NHAC_LAI_GIO = 12
BANG = (LeadNguoiNhanCanhBao,)
_da_tao = False


def _token() -> str | None:
    return os.environ.get("ZALO_LEAD_TOKEN")


def dam_bao_bang() -> None:
    global _da_tao
    if not _da_tao:
        for b in BANG:
            b.__table__.create(engine, checkfirst=True)
        _da_tao = True


# ------------------------------------------------------------------ người nhận cảnh báo
def ds_nguoi_nhan() -> list[dict]:
    dam_bao_bang()
    with session_scope() as s:
        rows = s.execute(select(LeadNguoiNhanCanhBao)
                         .order_by(LeadNguoiNhanCanhBao.vai_tro.desc(), LeadNguoiNhanCanhBao.id)).scalars()
        return [{"id": r.id, "vai_tro": r.vai_tro, "acc_norm": r.acc_norm, "ten": r.ten,
                 "chat_id": r.chat_id, "bat": bool(r.bat)} for r in rows]


def luu_nguoi_nhan(id_: int | None, vai_tro: str, ten: str, chat_id: str, acc_norm: str | None, bat: bool,
                   nguoi: str) -> tuple[bool, str]:
    dam_bao_bang()
    ten, chat_id = (ten or "").strip(), (chat_id or "").strip()
    if vai_tro not in ("sale", "leader"):
        return False, "Vai trò không hợp lệ."
    if not ten or not chat_id:
        return False, "Cần nhập tên và chat_id."
    with session_scope() as s:
        r = s.get(LeadNguoiNhanCanhBao, int(id_)) if id_ else None
        if id_ and not r:
            return False, "Không tìm thấy người nhận này."
        if not r:
            r = LeadNguoiNhanCanhBao(tao_luc=datetime.utcnow())
            s.add(r)
        r.vai_tro, r.ten, r.chat_id, r.bat = vai_tro, ten[:120], chat_id[:80], bool(bat)
        r.acc_norm = ((acc_norm or "").strip().lower()[:80] or None) if vai_tro == "sale" else None
        s.add(AuditLog(username=nguoi, action="lead_nguoi_nhan",
                       detail=f"{'Sửa' if id_ else 'Thêm'} {ten} ({vai_tro})"))
    return True, f"Đã lưu người nhận “{ten}”."


def xoa_nguoi_nhan(ids: list[int], nguoi: str) -> int:
    dam_bao_bang()
    with session_scope() as s:
        n = 0
        for i in ids:
            r = s.get(LeadNguoiNhanCanhBao, int(i))
            if r:
                s.delete(r)
                n += 1
        s.add(AuditLog(username=nguoi, action="lead_xoa_nguoi_nhan", detail=f"{n} dòng"))
    return n


# ------------------------------------------------------------------ quét SLA + gửi cảnh báo
def _chat_id_sale(acc_norm: str | None, nguoi_nhan: list[dict]) -> str | None:
    return next((n["chat_id"] for n in nguoi_nhan
                if n["vai_tro"] == "sale" and n["acc_norm"] == acc_norm and n["bat"]), None)


def _noi_dung(r: Lead, ten_tinh: str, ten_sale: str, ten_de_xuat: str | None) -> str:
    gio = int((datetime.utcnow() - (r.cap_nhat_luc or r.tao_luc)).total_seconds() // 3600)
    dong = [f"⏰ LEAD QUÁ HẠN CARE ({gio} giờ chưa cập nhật)",
            f"Khách: {r.ten_kh or '(chưa có tên)'} · {ten_tinh}",
            f"SĐT: {r.sdt or '(chưa có)'}",
            f"Sale phụ trách: {ten_sale}"]
    if ten_de_xuat:
        dong.append(f"Đề xuất nhận chéo: {ten_de_xuat}")
    dong.append(f"Trạng thái hiện tại: {r.tinh_trang_xu_ly}")
    return "\n".join(dong)


def quet_va_canh_bao() -> dict:
    """Quét mọi lead quá hạn, gửi Zalo cho người liên quan, ghi lại `canh_bao_luc`. Lỗi gửi cho 1 người không
    chặn người khác / lead khác (cùng cách `app/ban_tin_phong.py` xử lý lỗi gửi Zalo)."""
    dam_bao_bang()
    leads.dam_bao_bang()
    now = datetime.utcnow()
    nguoi_nhan = ds_nguoi_nhan()
    ten_sale = {a["acc_norm"]: a["ten"] for a in leads.nguoi_online()}
    kq = {"quet": 0, "qua_han": 0, "da_bao": 0, "loi": []}
    with session_scope() as s:
        rows = s.execute(select(Lead)).scalars().all()
        kq["quet"] = len(rows)
        for r in rows:
            if r.tinh_trang_xu_ly in leads.TRANG_THAI_DONG:
                continue
            moc = r.cap_nhat_luc or r.tao_luc
            if not moc or (now - moc).total_seconds() < leads.HAN_SLA_GIO * 3600:
                continue
            kq["qua_han"] += 1
            if r.canh_bao_luc and (now - r.canh_bao_luc).total_seconds() < CHU_KY_NHAC_LAI_GIO * 3600:
                continue
            de_xuat = leads.de_xuat_nhan_cheo(r.sale_tu_van)
            trang = s.get(CrmPage, r.page_id)
            noi_dung = _noi_dung(r, trang.ten if trang else "",
                                 ten_sale.get(r.sale_tu_van, r.sale_tu_van or "(chưa gán)"),
                                 ten_sale.get(de_xuat) if de_xuat else None)
            nhan: list[str] = []
            for acc in (r.sale_tu_van, de_xuat):
                cid = _chat_id_sale(acc, nguoi_nhan)
                if cid and cid not in nhan:
                    nhan.append(cid)
            for n in nguoi_nhan:
                if n["vai_tro"] == "leader" and n["bat"] and n["chat_id"] not in nhan:
                    nhan.append(n["chat_id"])
            da_gui = False
            for chat_id in nhan:
                try:
                    zalo_bot.gui_tin_du_phong(chat_id, noi_dung, token=_token())
                    da_gui = True
                except zalo_bot.LoiZalo as e:
                    kq["loi"].append(f"Lead #{r.id} -> {chat_id}: {e}")
            if da_gui:
                r.canh_bao_luc = now
                kq["da_bao"] += 1
        s.add(AuditLog(username="he_thong", action="lead_canh_bao_sla",
                       detail=f"{kq['qua_han']} quá hạn, {kq['da_bao']} đã báo, {len(kq['loi'])} lỗi gửi"))
    return kq
