"""Tự bắt lead từ Messenger (Giai đoạn B): nhận webhook (app/api_lead.py), tạo/cập nhật `Lead` theo (page, PSID);
gọi Graph API để lấy tên khách và để đăng ký webhook cho từng page.

**Chỉ tạo lead MỚI khi tin nhắn có số điện thoại** (chốt với người dùng 17/11/2026, `leads.tim_sdt`): khách nhắn
mà chưa cho số thì chưa tạo gì cả, tới khi có tin nào của đúng khách đó chứa số mới tạo lead (các tin trước đó
không có số bị bỏ qua, không lưu lại). Lead ĐÃ tồn tại (khách nhắn lại) thì mọi tin sau vẫn được nối vào, không
lọc lại. "Quét số" từ trang cá nhân khách là việc sale tự làm bằng tay (Facebook không cho app đọc SĐT người lạ
qua API) - gõ thẳng vào nút "+ Thêm lead" của trang /leads, không qua webhook này.

Việc người dùng phải tự làm trên Meta (không thao tác thay được): tạo Meta App, bật Messenger, lấy App Secret
(`FB_APP_SECRET`), khai báo URL callback + verify token (`FB_WEBHOOK_VERIFY_TOKEN`), lấy Page Access Token của
từng page rồi dán vào trang /leads (mục Cấu hình) - `app/leads.luu_fb_cau_hinh`. Đăng ký webhook cho page
(`dang_ky_webhook`) thì app tự gọi được, không cần vào Meta Business Suite.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime

from sqlalchemy import select

from app import leads
from app.db import session_scope
from app.models import CrmPage, Lead

GRAPH = "https://graph.facebook.com/v19.0"
HAN_GIAY = 8


class LoiMessenger(Exception):
    """Lỗi gọi Graph API - câu tiếng Việt trả thẳng cho người dùng."""


def _goi_graph(duong_dan: str, method: str = "GET", **tham_so) -> dict:
    url = f"{GRAPH}/{duong_dan}"
    data = urllib.parse.urlencode(tham_so).encode()
    if method == "GET":
        url, data = f"{url}?{data.decode()}", None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, method=method), timeout=HAN_GIAY) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            loi = json.loads(e.read()).get("error", {}).get("message", "")
        except Exception:
            loi = ""
        raise LoiMessenger(f"Facebook từ chối (mã {e.code}){': ' + loi if loi else ''}.") from None
    except Exception as e:
        raise LoiMessenger(f"Không gọi được Facebook ({type(e).__name__}).") from None


def ten_khach(psid: str, token: str) -> str | None:
    """Tên khách từ PSID (không chặn nếu lỗi - để trống cho sale tự điền)."""
    try:
        kq = _goi_graph(psid, fields="first_name,last_name", access_token=token)
    except LoiMessenger:
        return None
    ten = " ".join(x for x in (kq.get("first_name"), kq.get("last_name")) if x)
    return ten.strip() or None


def dang_ky_webhook(fb_page_id: str, token: str) -> str:
    """POST /{page-id}/subscribed_apps - đăng ký page nhận sự kiện 'messages' qua webhook của Meta App."""
    _goi_graph(f"{fb_page_id}/subscribed_apps", method="POST", subscribed_fields="messages", access_token=token)
    return "Đã đăng ký webhook cho page này."


# ------------------------------------------------------------------ nhận webhook
def _trang(fb_page_id: str) -> tuple[int, str] | None:
    with session_scope() as s:
        p = s.execute(select(CrmPage).where(CrmPage.fb_page_id == fb_page_id,
                                            CrmPage.active.is_(True))).scalars().first()
        return (p.id, p.page_access_token or "") if p else None


def _xu_ly_tin(fb_page_id: str, msg: dict) -> None:
    tin = msg.get("message") or {}
    if tin.get("is_echo"):
        return
    noi_dung = (tin.get("text") or "").strip()
    psid = str((msg.get("sender") or {}).get("id") or "")
    if not psid:
        return
    trang = _trang(fb_page_id)
    if not trang:
        return
    page_id, token = trang
    now = datetime.utcnow()
    with session_scope() as s:
        r = s.execute(select(Lead).where(Lead.page_id == page_id, Lead.fb_psid == psid)).scalars().first()
        if r is None:
            sdt = leads.tim_sdt(noi_dung)
            if not sdt:
                return      # chưa cho số -> chưa tạo lead, chờ tin sau có số
            s.add(Lead(page_id=page_id, ngay=date.today(), fb_psid=psid,
                       ten_kh=ten_khach(psid, token) if token else None, sdt=sdt,
                       tinh_trang_xu_ly="Mới", nguon="messenger", ghi_chu=noi_dung or None,
                       tao_luc=now, tao_boi="messenger", cap_nhat_luc=now, cap_nhat_boi="messenger"))
        else:
            if noi_dung:
                r.ghi_chu = f"{r.ghi_chu}\n{noi_dung}" if r.ghi_chu else noi_dung
            if not r.sdt:
                r.sdt = leads.tim_sdt(noi_dung)
            r.cap_nhat_luc, r.cap_nhat_boi, r.canh_bao_luc = now, "messenger", None


def xu_ly_su_kien(payload: dict) -> None:
    """Một lượt webhook (nhiều `entry`, mỗi entry nhiều `messaging`) - một tin lỗi không chặn các tin khác."""
    leads.dam_bao_bang()
    for entry in payload.get("entry") or []:
        fb_page_id = str(entry.get("id") or "")
        if not fb_page_id:
            continue
        for msg in entry.get("messaging") or []:
            try:
                _xu_ly_tin(fb_page_id, msg)
            except Exception:
                continue
