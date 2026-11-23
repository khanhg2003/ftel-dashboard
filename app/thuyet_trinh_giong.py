"""Giọng đọc tiếng Việt cho "Thuyết trình AI": bộ giọng Gemini TTS (Aoede, Kore, Sulafat...), người nghe tự chọn giọng ở trang (CEO chốt 23/11/2026).

Đã bỏ hẳn giọng của trình duyệt (máy hay không có giọng Việt nên đọc bằng giọng nước ngoài) và giọng OpenAI. Trình duyệt gửi từng CÂU lên `POST /api/thuyet-trinh/doc`
{chu, giong}, máy chủ nhờ Gemini đọc thành WAV rồi trình duyệt phát. Chỉ chữ lời nói đã qua kiểm số được gửi; không có tên khách.
Khoá Gemini (Google AI Studio) lưu mã hoá ở bảng `cai_dat` (khoá `tt.gemini_key`, nhập ngay trên trang) hoặc lấy từ biến môi trường `GEMINI_API_KEY`; không bao giờ trả ra trình duyệt.
Gọi theo API "interactions" hiện hành, lỗi 400 / 404 thì thử lại bằng `generateContent` của model 2.5 để không hỏng khi Google đổi tên model. Nhớ tạm theo (giọng, câu) nên nghe lại không tốn thêm.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import socket
import struct
import threading
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from datetime import datetime

from app import tro_ly
from app.db import session_scope
from app.models import AuditLog, CaiDat

API = "https://generativelanguage.googleapis.com/v1beta"
MODEL = "gemini-3.8-flash-tts"                  # API interactions
MODEL_DU_PHONG = "gemini-2.5-flash-preview-tts"  # API generateContent
PHONG_THUYET_TRINH = "đọc bằng tiếng Việt, giọng thuyết trình chuyên nghiệp, rõ ràng, tự nhiên, nhịp vừa phải, không quá nhanh"
MAC_DINH = "Sulafat"
KHOA_LUU = "tt.gemini_key"
TOI_DA_KY_TU = 1200                # một lần xin đọc (vài câu gộp lại) dài tối đa; quá thì từ chối để không bị lợi dụng đọc văn bản tuỳ ý
TOI_DA_CHO = 30                    # Gemini báo quá giới hạn: chờ tối đa chừng này giây rồi thử lại MỘT lần
TOI_DA_NHO = 100                   # số câu nhớ tạm trong tiến trình (mỗi câu vài trăm KB WAV)

# (tên giọng, mô tả tiếng Việt, "nu" / "nam") - 30 giọng có sẵn của Gemini; thứ tự như trang chọn giọng của Navi
GIONG = [
    ("Aoede", "nhẹ nhàng, thoáng", "nu"), ("Kore", "chắc, rõ ràng", "nu"), ("Leda", "trẻ trung", "nu"), ("Zephyr", "tươi sáng", "nu"),
    ("Autonoe", "sáng, rõ", "nu"), ("Callirrhoe", "thoải mái", "nu"), ("Despina", "mượt mà", "nu"), ("Erinome", "trong trẻo", "nu"),
    ("Laomedeia", "vui tươi", "nu"), ("Achernar", "mềm mại", "nu"), ("Gacrux", "chín chắn", "nu"), ("Pulcherrima", "tự tin, thẳng thắn", "nu"),
    ("Vindemiatrix", "dịu dàng", "nu"), ("Sulafat", "ấm áp", "nu"),
    ("Puck", "sôi nổi", "nam"), ("Charon", "chuyên nghiệp", "nam"), ("Fenrir", "hào hứng", "nam"), ("Orus", "chắc chắn", "nam"),
    ("Enceladus", "trầm, nhẹ hơi", "nam"), ("Iapetus", "rõ ràng", "nam"), ("Umbriel", "thoải mái", "nam"), ("Algieba", "mượt mà", "nam"),
    ("Algenib", "khàn, trầm", "nam"), ("Rasalgethi", "thông tin, mạch lạc", "nam"), ("Alnilam", "chắc, mạnh", "nam"), ("Schedar", "đều đặn", "nam"),
    ("Achird", "thân thiện", "nam"), ("Zubenelgenubi", "tự nhiên", "nam"), ("Sadachbia", "lanh lợi", "nam"), ("Sadaltager", "hiểu biết", "nam"),
]
TEN_GIONG = {g[0] for g in GIONG}

_nho: OrderedDict[str, bytes] = OrderedDict()
_khoa = threading.Lock()
_luot = threading.Lock()           # Gemini chỉ cho vài yêu cầu mỗi phút (gói miễn phí: 3): tạo giọng lần lượt từng yêu cầu, không dồn cùng lúc


# ------------------------------------------------------------------ khoá Gemini
def khoa_gemini() -> str:
    """Khoá đã lưu (giải mã) hoặc biến môi trường `GEMINI_API_KEY`; rỗng nếu chưa có."""
    tro_ly._dam_bao_bang()
    with session_scope() as s:
        row = s.get(CaiDat, KHOA_LUU)
        ma = row.gia_tri if row else None
    return (tro_ly.giai_ma(ma) if ma else None) or ("" if ma else os.environ.get("GEMINI_API_KEY", "").strip())


def luu_khoa(khoa: str | None, nguoi: str) -> None:
    """`khoa` = None thì xoá mã đã lưu. Ghi nhật ký (không ghi mã)."""
    tro_ly._dam_bao_bang()
    with session_scope() as s:
        row = s.get(CaiDat, KHOA_LUU)
        if khoa is None:
            if row:
                s.delete(row)
        elif row is None:
            s.add(CaiDat(khoa=KHOA_LUU, gia_tri=tro_ly.ma_hoa(khoa.strip()), updated_by=nguoi))
        else:
            row.gia_tri, row.updated_by, row.updated_at = tro_ly.ma_hoa(khoa.strip()), nguoi, datetime.utcnow()
        s.add(AuditLog(username=nguoi, action="thuyet_trinh_khoa_giong", detail="xoá mã" if khoa is None else "đã đổi mã"))
    with _khoa:
        _nho.clear()


def trang_thai_khoa() -> str:
    k = khoa_gemini()
    return f"Đã có mã Gemini {tro_ly.key_an(k)}." if k else "Chưa có mã Gemini nên chưa có giọng đọc."


# ------------------------------------------------------------------ gọi Gemini
def _http(duong_dan: str, body: dict, key: str, han: float) -> dict:
    req = urllib.request.Request(f"{API}/{duong_dan}", method="POST", data=json.dumps(body).encode(),
                                 headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=han) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            chi_tiet = (json.loads(e.read()).get("error") or {}).get("message", "")
        except Exception:
            chi_tiet = ""
        thong_bao = {401: "Mã Gemini không hợp lệ.", 403: "Mã Gemini không có quyền dùng giọng đọc.",
                     429: ("Mã Gemini đang ở gói miễn phí nên chỉ được vài yêu cầu mỗi phút. Bật thanh toán cho mã ở aistudio.google.com để đọc liền mạch." if "free" in chi_tiet.lower()
                           else "Gemini báo quá nhiều yêu cầu hoặc hết hạn mức giọng đọc, thử lại sau ít phút.")}
        loi = tro_ly.LoiAI(thong_bao.get(e.code, f"Gemini báo lỗi {e.code} khi tạo giọng đọc.") + (f" ({chi_tiet[:140]})" if chi_tiet and e.code not in (401, 403, 429) else ""))
        loi.ma = e.code
        m = re.search(r"retry in (\d+)", chi_tiet, re.I)
        loi.cho = int(m.group(1)) if m else int(e.headers.get("Retry-After") or 0)
        raise loi from None
    except (socket.timeout, TimeoutError):
        raise tro_ly.LoiAI("Giọng đọc trả lời quá lâu, thử lại.") from None
    except urllib.error.URLError:
        raise tro_ly.LoiAI("Không kết nối được tới Gemini.") from None


def _tim_am(x) -> str | None:
    """Tìm chuỗi base64 âm thanh trong kết quả (đúng cho cả hai kiểu trả lời của Gemini)."""
    if isinstance(x, dict):
        if isinstance(x.get("data"), str) and (x.get("type") == "audio" or "mimeType" in x or "mime_type" in x):
            return x["data"]
        for v in x.values():
            if (r := _tim_am(v)):
                return r
    elif isinstance(x, list):
        for v in x:
            if (r := _tim_am(v)):
                return r
    return None


def _wav(pcm: bytes, tan_so: int = 24000) -> bytes:
    """Gemini trả PCM 16-bit mono thô; bọc thêm phần đầu WAV để trình duyệt phát được."""
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, tan_so, tan_so * 2, 2, 16)
            + b"data" + struct.pack("<I", len(pcm)) + pcm)


def _tao_am(chu: str, giong: str, key: str) -> bytes:
    """Tạo lần lượt (khoá `_luot`); Gemini báo quá giới hạn mà chỉ cần chờ ngắn thì chờ rồi thử lại một lần."""
    if not _luot.acquire(timeout=50):
        raise tro_ly.LoiAI("Đang tạo giọng cho phần trước, thử lại sau ít giây.")
    try:
        try:
            return _tao_am_mot_lan(chu, giong, key)
        except tro_ly.LoiAI as e:
            cho = getattr(e, "cho", 0)
            if getattr(e, "ma", None) != 429 or not 0 < cho <= TOI_DA_CHO:
                raise
            time.sleep(cho + 1)
            return _tao_am_mot_lan(chu, giong, key)
    finally:
        _luot.release()


def _tao_am_mot_lan(chu: str, giong: str, key: str) -> bytes:
    loi_dau = None
    try:
        kq = _http("interactions", {"model": MODEL, "response_format": {"type": "audio"}, "generation_config": {"speech_config": [{"voice": giong}]},
                                    "input": [{"type": "user_input", "content": [{"type": "text", "text": chu, "annotations": [{"type": "speech_metadata", "style": PHONG_THUYET_TRINH}]}]}]}, key, 40)
    except tro_ly.LoiAI as e:
        if getattr(e, "ma", None) not in (400, 404):
            raise
        loi_dau, kq = e, None
    if kq is None:
        try:
            kq = _http(f"models/{MODEL_DU_PHONG}:generateContent",
                       {"contents": [{"parts": [{"text": f"{PHONG_THUYET_TRINH.capitalize()}: {chu}"}]}],
                        "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": giong}}}}}, key, 40)
        except tro_ly.LoiAI:
            raise loi_dau from None
    b64 = _tim_am(kq)
    if not b64:
        raise tro_ly.LoiAI("Gemini không trả về âm thanh.")
    am = base64.b64decode(b64)
    return am if am[:4] == b"RIFF" else _wav(am)


def doc(user, chu: str, giong: str = MAC_DINH) -> bytes:
    """WAV của một câu lời nói. Ném `LoiAI` (câu tiếng Việt đã làm sạch) nếu không đọc được."""
    chu = " ".join((chu or "").split())
    if not chu:
        raise tro_ly.LoiAI("Không có chữ để đọc.")
    if len(chu) > TOI_DA_KY_TU:
        raise tro_ly.LoiAI("Câu quá dài để đọc.")
    if giong not in TEN_GIONG:
        giong = MAC_DINH
    ma = hashlib.sha256(f"{MODEL}|{giong}|{chu}".encode()).hexdigest()
    with _khoa:
        if ma in _nho:
            _nho.move_to_end(ma)
            return _nho[ma]
    key = khoa_gemini()
    if not key:
        raise tro_ly.LoiAI("Chưa có mã Gemini nên chưa có giọng đọc. Dán mã ở mục “Mã Gemini” bên dưới trang.")
    if tro_ly.chi_phi_thang() >= tro_ly.cau_hinh()["tran_usd"]:
        raise tro_ly.LoiAI("Đã dùng hết ngân sách AI tháng này, giọng đọc tạm dừng.")
    am = _tao_am(chu, giong, key)
    tro_ly._ghi_su_dung(user.username, "giong_doc", MODEL, len(chu), 0)      # giá tính theo ký tự (xem tro_ly.GIA)
    with _khoa:
        _nho[ma] = am
        while len(_nho) > TOI_DA_NHO:
            _nho.popitem(last=False)
    return am
