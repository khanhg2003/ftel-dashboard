"""Gửi tin nhắn qua Zalo Bot chính thức (POST bot-api.zaloplatforms.com/bot<TOKEN>/sendMessage).

Token đọc từ biến môi trường `ZALO_BOT_TOKEN`, nằm ngay trong địa chỉ gọi nên mọi thông báo lỗi ở đây
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
TOI_DA_KY_TU = 2000


class LoiZalo(Exception):
    """Không gửi được tin Zalo; thông điệp tiếng Việt, an toàn để hiện và ghi nhật ký."""


def _token() -> str:
    return (os.environ.get("ZALO_BOT_TOKEN") or "").strip()


def da_cau_hinh() -> bool:
    return bool(_token())


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


def gui_tin(chat_id: str, noi_dung: str, parse_mode: str | None = None, han: float = HAN_GIAY) -> None:
    """Gửi một tin chữ tới `chat_id`. Lỗi gì cũng đổi thành `LoiZalo`."""
    token = _token()
    if not token:
        raise LoiZalo("Chưa cài biến ZALO_BOT_TOKEN trên máy chủ.")
    chat_id = str(chat_id or "").strip()
    chu = (noi_dung or "").strip()[:TOI_DA_KY_TU]
    if not chat_id or not chu:
        raise LoiZalo("Thiếu chat_id hoặc nội dung tin nhắn.")
    goi = {"chat_id": chat_id, "text": chu}
    if parse_mode in ("markdown", "html"):
        goi["parse_mode"] = parse_mode
    req = urllib.request.Request(
        f"{GOC}/bot{token}/sendMessage", data=json.dumps(goi).encode(), method="POST",
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
