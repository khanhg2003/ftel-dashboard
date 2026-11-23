"""Giọng đọc tiếng Việt cho "Thuyết trình AI" khi máy người xem KHÔNG có sẵn giọng Việt (chủ app báo 23/11/2026: Chrome trên Windows đọc bằng giọng nước ngoài).

Trình duyệt gửi từng CÂU lên `POST /api/thuyet-trinh/doc`, máy chủ nhờ OpenAI đọc thành mp3 (cùng khoá với Trợ lý AI, tính vào ngân sách AI tháng) rồi trình duyệt phát.
Chỉ chữ lời nói đã qua kiểm số được gửi; không có tên khách. Máy có giọng Việt sẵn (vd Edge) thì trình duyệt vẫn dùng giọng đó, miễn phí, không gọi đường này.
Nhớ tạm theo nội dung câu để nghe lại / lùi không tốn thêm tiền.
"""
from __future__ import annotations

import hashlib
import json
import socket
import threading
import urllib.error
import urllib.request
from collections import OrderedDict

from app import tro_ly

MODEL = "gpt-4o-mini-tts"
GIONG = "nova"
CHI_DAN = ("Đọc bằng tiếng Việt chuẩn giọng miền Bắc, giọng nữ trẻ, ấm, rõ ràng, nhịp thuyết trình chuyên nghiệp. "
           "Đọc đúng số và tên riêng, không quá nhanh, ngắt nghỉ tự nhiên giữa các ý.")
TOI_DA_KY_TU = 700                 # một câu lời nói dài tối đa; quá thì từ chối để không bị lợi dụng đọc văn bản tuỳ ý
TOI_DA_NHO = 300                   # số câu nhớ tạm trong tiến trình (mỗi câu vài chục KB)

_nho: OrderedDict[str, bytes] = OrderedDict()
_khoa = threading.Lock()


def san_sang(user) -> bool:
    """Có thể dùng giọng AI không: Trợ lý AI đang bật, có khoá và người này được mở quyền (không kiểm ngân sách, để trang chỉ cần hỏi nhanh)."""
    try:
        ch = tro_ly.cau_hinh()
    except Exception:                                        # lỗi đọc cấu hình không được làm sập trang
        return False
    return bool(ch["bat"] and ch["key"] and tro_ly.duoc_dung(user, ch))


def _goi(chu: str, key: str, han: float = 30) -> bytes:
    body = json.dumps({"model": MODEL, "voice": GIONG, "input": chu, "instructions": CHI_DAN, "response_format": "mp3"}).encode()
    req = urllib.request.Request(f"{tro_ly.API}/audio/speech", method="POST", data=body,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=han) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        thong_bao = {401: "Mã API không hợp lệ hoặc đã bị thu hồi.", 403: "Mã API không có quyền dùng giọng đọc.",
                     404: "Mã API chưa dùng được model giọng đọc.", 429: "OpenAI báo hết hạn mức giọng đọc."}
        raise tro_ly.LoiAI(thong_bao.get(e.code, f"OpenAI báo lỗi {e.code} khi tạo giọng đọc.")) from None
    except (socket.timeout, TimeoutError):
        raise tro_ly.LoiAI("Giọng đọc AI trả lời quá lâu.") from None
    except urllib.error.URLError:
        raise tro_ly.LoiAI("Không kết nối được tới OpenAI.") from None


def doc(user, chu: str) -> bytes:
    """mp3 của một câu lời nói. Ném `LoiAI` (câu tiếng Việt đã làm sạch) nếu không đọc được."""
    chu = " ".join((chu or "").split())
    if not chu:
        raise tro_ly.LoiAI("Không có chữ để đọc.")
    if len(chu) > TOI_DA_KY_TU:
        raise tro_ly.LoiAI("Câu quá dài để đọc.")
    ma = hashlib.sha256(f"{MODEL}|{GIONG}|{chu}".encode()).hexdigest()
    with _khoa:
        if ma in _nho:
            _nho.move_to_end(ma)
            return _nho[ma]
    ch = tro_ly.kiem_tra(user)                               # quyền, ngân sách tháng, trần lượt/ngày
    am = _goi(chu, ch["key"])
    if len(am) < 200:
        raise tro_ly.LoiAI("OpenAI không trả về âm thanh.")
    tro_ly._ghi_su_dung(user.username, "giong_doc", MODEL, len(chu), 0)      # giá tính theo ký tự (xem tro_ly.GIA)
    with _khoa:
        _nho[ma] = am
        while len(_nho) > TOI_DA_NHO:
            _nho.popitem(last=False)
    return am
