"""Gửi tin nhắn qua Zalo Bot chính thức (POST bot-api.zaloplatforms.com/bot<TOKEN>/sendMessage).

Token mặc định đọc từ biến môi trường `ZALO_BOT_TOKEN` (bot Bản tin); bot Tra cứu giá là bot RIÊNG (`ZALO_GIA_TOKEN`, vì một bot
chỉ gắn được một webhook) nên mọi hàm nhận thêm tham số `token`. Token nằm ngay trong địa chỉ gọi nên mọi thông báo lỗi ở đây
được viết sẵn bằng tiếng Việt và KHÔNG bao giờ chứa token hay địa chỉ gọi (log, nhật ký, giao diện đều
chỉ nhìn thấy câu đã làm sạch). Zalo có thể từ chối bot gửi chủ động cho người lâu không nhắn: đó là
`LoiZalo` bình thường, người gọi ghi lại rồi thử lượt sau.
"""
from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request

GOC = "https://bot-api.zaloplatforms.com"
HAN_GIAY = 8
HAN_ANH = 20                  # Zalo tải ảnh về ngay trong lúc gọi sendPhoto: chờ lâu hơn tin chữ
TOI_DA_KY_TU = 2000


class LoiZalo(Exception):
    """Không gửi được tin Zalo; thông điệp tiếng Việt, an toàn để hiện và ghi nhật ký."""


def _token(token: str | None = None) -> str:
    """`token` None = bot Bản tin (ZALO_BOT_TOKEN); truyền chuỗi (kể cả rỗng) = bot khác."""
    if token is None:
        token = os.environ.get("ZALO_BOT_TOKEN")
    return (token or "").strip()


def token_gia() -> str:
    return (os.environ.get("ZALO_GIA_TOKEN") or "").strip()


def da_cau_hinh() -> bool:
    return bool(_token())


def _thieu_token(token: str | None) -> str:
    return "Chưa cài biến ZALO_BOT_TOKEN trên máy chủ." if token is None else "Chưa cài token cho bot Zalo này trên máy chủ."


def _sach(chu: str, token: str) -> str:
    """Bỏ token (nếu Zalo lỡ nhắc lại) và cắt ngắn trước khi đưa vào thông báo."""
    chu = " ".join(str(chu or "").split())
    return (chu.replace(token, "***") if token else chu)[:150]


def _mo_ta_loi_http(e: urllib.error.HTTPError, token: str) -> str:
    mo_ta = ""
    try:
        du_lieu = json.loads(e.read() or b"{}")
        if isinstance(du_lieu, dict):
            mo_ta = du_lieu.get("description") or du_lieu.get("message") or ""
    except Exception:
        pass
    ma = e.code
    goi_y = " Kiểm tra token bot." if ma in (401, 404) else ""
    return f"Zalo từ chối (mã {ma}){': ' + _sach(mo_ta, token) if mo_ta else ''}.{goi_y}"


def gui_tin(chat_id: str, noi_dung: str, parse_mode: str | None = None, han: float = HAN_GIAY,
            text_styles: list | None = None, token: str | None = None) -> None:
    """Gửi một tin chữ tới `chat_id`. `text_styles` = kiểu chữ theo vị trí UTF-16 của Zalo (đậm, màu, cỡ).
    Lỗi gì cũng đổi thành `LoiZalo`."""
    if not _token(token):
        raise LoiZalo(_thieu_token(token))
    chat_id = str(chat_id or "").strip()
    chu = (noi_dung or "") if text_styles else (noi_dung or "").strip()      # có kiểu thì giữ nguyên để vị trí không lệch
    chu = chu[:TOI_DA_KY_TU]
    if not chat_id or not chu.strip():
        raise LoiZalo("Thiếu chat_id hoặc nội dung tin nhắn.")
    goi = {"chat_id": chat_id, "text": chu}
    if parse_mode in ("markdown", "html"):
        goi["parse_mode"] = parse_mode
    elif text_styles:
        goi["text_styles"] = list(text_styles)
    _goi_api("sendMessage", goi, han, token)


def _goi_api(ten_ham: str, goi: dict, han: float = HAN_GIAY, token: str | None = None) -> dict:
    """POST một hàm của Bot API, trả về JSON phản hồi. Lỗi gì cũng đổi thành `LoiZalo` đã làm sạch."""
    thieu, token = _thieu_token(token), _token(token)
    if not token:
        raise LoiZalo(thieu)
    req = urllib.request.Request(
        f"{GOC}/bot{token}/{ten_ham}", data=json.dumps(goi).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=han) as r:
            kq = json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise LoiZalo(_mo_ta_loi_http(e, token)) from None
    except (socket.timeout, TimeoutError):
        raise LoiZalo("Zalo không trả lời kịp (quá thời gian chờ).") from None
    except urllib.error.URLError as e:
        qua_gio = isinstance(getattr(e, "reason", None), (socket.timeout, TimeoutError))
        raise LoiZalo("Zalo không trả lời kịp (quá thời gian chờ)." if qua_gio
                      else "Không kết nối được tới Zalo.") from None
    except Exception:
        raise LoiZalo("Phản hồi của Zalo không đọc được.") from None
    if not isinstance(kq, dict):
        raise LoiZalo("Phản hồi của Zalo không đúng dạng mong đợi.")
    if kq.get("ok") is False or kq.get("error_code"):
        raise LoiZalo(f"Zalo từ chối (mã {kq.get('error_code', '?')}): "
                      f"{_sach(kq.get('description') or kq.get('message'), token)}")
    return kq


def gui_tin_du_phong(chat_id: str, noi_dung: str, han: float = HAN_GIAY, token: str | None = None) -> bool:
    """Gửi tin kèm kiểu chữ (`noi_dung.kieu`); Zalo từ chối thì gửi lại bản CHỮ TRƠN để người nhận vẫn có tin.
    True = đã phải dùng chữ trơn. Không có kiểu chữ mà lỗi thì ném `LoiZalo` như `gui_tin`."""
    kieu = getattr(noi_dung, "kieu", None)
    them = {} if token is None else {"token": token}          # bot Bản tin (mặc định) gọi y như cũ
    try:
        gui_tin(chat_id, noi_dung, han=han, text_styles=kieu, **them)
        return False
    except LoiZalo:
        if not kieu:
            raise
    gui_tin(chat_id, str(noi_dung), han=han, **them)
    return True


def gui_anh(chat_id: str, url_anh: str, caption: str = "", han: float = HAN_ANH, token: str | None = None) -> None:
    """sendPhoto: `url_anh` là ĐƯỜNG DẪN công khai để Zalo tự tải ảnh (tài liệu Zalo chỉ ghi "đường dẫn hình ảnh sẽ được
    gửi", không nói rõ giới hạn dung lượng hay định dạng). Thông báo lỗi không bao giờ chứa token, địa chỉ gọi hay mã trong đường dẫn ảnh."""
    chat_id, url_anh = str(chat_id or "").strip(), str(url_anh or "").strip()
    if not chat_id or not url_anh:
        raise LoiZalo("Thiếu chat_id hoặc đường dẫn ảnh.")
    goi = {"chat_id": chat_id, "photo": url_anh}
    if (caption or "").strip():
        goi["caption"] = caption.strip()[:TOI_DA_KY_TU]
    try:
        _goi_api("sendPhoto", goi, han, token)
    except LoiZalo as e:
        ma = url_anh.rsplit("/", 1)[-1].removesuffix(".png")
        raise LoiZalo(str(e).replace(url_anh, "***").replace(ma, "***") if ma else str(e)) from None


def dat_webhook(url: str, secret_token: str, token: str | None = None) -> dict:
    """setWebhook. Zalo tự gọi thử địa chỉ và báo kết quả ở `verification` (địa chỉ vẫn được lưu dù thử hỏng)."""
    kq = _goi_api("setWebhook", {"url": url, "secret_token": secret_token}, token=token)
    res = kq.get("result") if isinstance(kq.get("result"), dict) else {}
    ktra = res.get("verification") if isinstance(res.get("verification"), dict) else {}
    return {"url": str(res.get("url") or url), "kiem_tra_ok": ktra.get("ok") is not False,
            "ket_qua_kiem_tra": _sach(ktra.get("outcome") or "", _token(token))}


def go_webhook(token: str | None = None) -> None:
    _goi_api("deleteWebhook", {}, token=token)


def thong_tin_webhook(token: str | None = None) -> dict:
    """getWebhookInfo -> {"url": địa chỉ đang đặt ("" nếu chưa)}."""
    kq = _goi_api("getWebhookInfo", {}, token=token)
    res = kq.get("result") if isinstance(kq.get("result"), dict) else {}
    return {"url": str(res.get("url") or "")}
