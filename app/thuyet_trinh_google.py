"""Giọng đọc tiếng Việt của Google Cloud Text-to-Speech cho "Thuyết trình AI" (CEO chốt 23/11/2026, thay Gemini làm nguồn chính vì Gemini gói miễn phí chỉ 3 lượt / phút và mỗi lần tạo cho âm sắc hơi khác nhau).

Dịch vụ chính thức `texttospeech.googleapis.com` (khác Gemini TTS, khoá lấy ở Google Cloud, không phải AI Studio): giọng CỐ ĐỊNH nên mọi lần gọi cùng một giọng, tạo nhanh (1-2 giây), không có giới hạn vài lượt mỗi phút.
Miễn phí theo tháng (trang giá Google, 23/11/2026): Chirp 3 HD và Neural2 mỗi loại 1 triệu ký tự, WaveNet và Standard mỗi loại 4 triệu; vượt thì Google TÍNH TIỀN, nên app tự đếm ký tự mỗi tháng theo từng loại giọng
(bảng `ai_su_dung`, cột `token_vao` = số ký tự) và DỪNG ở 95% hạn mức miễn phí. Khoá lưu mã hoá ở `cai_dat` (khoá `tt.google_tts_key`, nhập ngay trên trang) hoặc biến môi trường `GOOGLE_TTS_API_KEY`; không bao giờ trả ra trình duyệt.
Danh sách giọng lấy từ chính Google (`voices.list`, lọc `vi-VN`), nhớ trong tiến trình 24 giờ.
"""
from __future__ import annotations

import base64
import json
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

from sqlalchemy import func, select

from app import tro_ly
from app.db import session_scope
from app.models import AiSuDung, AuditLog, CaiDat
from app.thoi_gian import LECH_GIO_VN, gio_viet_nam

API = "https://texttospeech.googleapis.com/v1"
KHOA_LUU = "tt.google_tts_key"
TAN_SO = 24000
AN_TOAN = 0.95                       # dừng khi đã dùng chừng này phần của hạn mức miễn phí
# (mảnh trong tên giọng, nhãn tiếng Việt, hạn mức miễn phí mỗi tháng (ký tự), tên ghi ở ai_su_dung): đứng trước = tự nhiên hơn
LOAI = (("Chirp3-HD", "Chirp 3 HD (mới, tự nhiên nhất)", 1_000_000, "google-chirp3"),
        ("Neural2", "Neural2 (tự nhiên)", 1_000_000, "google-neural2"),
        ("Wavenet", "WaveNet", 4_000_000, "google-wavenet"),
        ("Standard", "Standard (cơ bản)", 4_000_000, "google-standard"))
GIONG_MAC_DINH = ("vi-VN-Chirp3-HD-Sulafat", "vi-VN-Chirp3-HD-Kore", "vi-VN-Neural2-A")
_TEN = re.compile(r"vi-VN-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*")
_nho_ds: dict = {"luc": 0.0, "khoa": "", "ds": []}
_khoa_nho = threading.Lock()


# ------------------------------------------------------------------ khoá
def khoa() -> str:
    """Khoá đã lưu (giải mã) hoặc biến môi trường `GOOGLE_TTS_API_KEY`; rỗng nếu chưa có."""
    tro_ly._dam_bao_bang()
    with session_scope() as s:
        row = s.get(CaiDat, KHOA_LUU)
        ma = row.gia_tri if row else None
    return (tro_ly.giai_ma(ma) if ma else None) or ("" if ma else os.environ.get("GOOGLE_TTS_API_KEY", "").strip())


def luu_khoa(moi: str | None, nguoi: str) -> None:
    """`moi` = None thì xoá mã đã lưu. Ghi nhật ký (không ghi mã)."""
    tro_ly._dam_bao_bang()
    with session_scope() as s:
        row = s.get(CaiDat, KHOA_LUU)
        if moi is None:
            if row:
                s.delete(row)
        elif row is None:
            s.add(CaiDat(khoa=KHOA_LUU, gia_tri=tro_ly.ma_hoa(moi.strip()), updated_by=nguoi))
        else:
            row.gia_tri, row.updated_by, row.updated_at = tro_ly.ma_hoa(moi.strip()), nguoi, datetime.utcnow()
        s.add(AuditLog(username=nguoi, action="thuyet_trinh_khoa_google", detail="xoá mã" if moi is None else "đã đổi mã"))
    with _khoa_nho:
        _nho_ds.update(luc=0.0, ds=[])


def trang_thai() -> str:
    k = khoa()
    return f"Đã có mã Google Cloud {tro_ly.key_an(k)}." if k else "Chưa có mã Google Cloud."


# ------------------------------------------------------------------ gọi dịch vụ
def _goi(duong_dan: str, body: dict | None, key: str, han: float = 30) -> dict:
    req = urllib.request.Request(f"{API}/{duong_dan}", method="POST" if body is not None else "GET", data=json.dumps(body).encode() if body is not None else None,
                                 headers={"X-Goog-Api-Key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=han) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            chi_tiet = (json.loads(e.read()).get("error") or {}).get("message", "")
        except Exception:
            chi_tiet = ""
        chung = chi_tiet.lower()
        if e.code in (400, 401) and ("api key" in chung or "api_key" in chung):
            thong_bao = "Mã Google Cloud không hợp lệ."
        elif e.code == 403 and ("billing" in chung or "not been used" in chung or "disabled" in chung or "not enabled" in chung):
            thong_bao = "Mã Google Cloud chưa bật dịch vụ Cloud Text-to-Speech hoặc chưa bật thanh toán cho dự án."
        elif e.code == 403:
            thong_bao = "Mã Google Cloud không có quyền dùng Text-to-Speech (kiểm tra phần giới hạn của mã)."
        elif e.code == 429:
            thong_bao = "Google báo quá nhiều yêu cầu, thử lại sau ít giây."
        else:
            thong_bao = f"Google báo lỗi {e.code} khi tạo giọng đọc." + (f" ({chi_tiet[:140]})" if chi_tiet else "")
        loi = tro_ly.LoiAI(thong_bao)
        loi.ma = e.code
        raise loi from None
    except (socket.timeout, TimeoutError):
        raise tro_ly.LoiAI("Giọng đọc trả lời quá lâu, thử lại.") from None
    except urllib.error.URLError:
        raise tro_ly.LoiAI("Không kết nối được tới Google.") from None


def la_giong(ten: str) -> bool:
    return bool(ten) and _TEN.fullmatch(ten) is not None


def loai_cua(ten: str) -> tuple:
    """(mảnh, nhãn, hạn mức miễn phí / tháng, tên ghi lượt dùng) của loại giọng chứa trong `ten`; giọng lạ tính như loại có hạn mức thấp nhất."""
    for m in LOAI:
        if f"-{m[0]}" in ten or ten.endswith(m[0]):
            return m
    return LOAI[0]


def danh_sach_giong(key: str) -> list[dict]:
    """Giọng vi-VN của Google: [{ten, loai, gioi: "nu" | "nam" | ""}] xếp theo loại tự nhiên trước. Lỗi / chưa có khoá thì rỗng; nhớ 24 giờ."""
    if not key:
        return []
    with _khoa_nho:
        if _nho_ds["ds"] and _nho_ds["khoa"] == key and time.time() - _nho_ds["luc"] < 86400:
            return list(_nho_ds["ds"])
    try:
        kq = _goi("voices?languageCode=vi-VN", None, key, 20)
    except tro_ly.LoiAI:
        return []
    ds = []
    for v in kq.get("voices") or []:
        ten = v.get("name") or ""
        if la_giong(ten):
            ds.append({"ten": ten, "loai": loai_cua(ten)[0], "gioi": {"FEMALE": "nu", "MALE": "nam"}.get(v.get("ssmlGender"), "")})
    thu_tu = {m[0]: i for i, m in enumerate(LOAI)}
    ds.sort(key=lambda g: (thu_tu.get(g["loai"], 9), g["gioi"] != "nu", g["ten"]))
    with _khoa_nho:
        _nho_ds.update(luc=time.time(), khoa=key, ds=ds)
    return list(ds)


def mac_dinh(ds: list[dict]) -> str:
    """Giọng chọn sẵn: ưu tiên giọng ấm áp của Chirp 3 HD, không có thì giọng đầu danh sách."""
    ten = {g["ten"] for g in ds}
    return next((g for g in GIONG_MAC_DINH if g in ten), ds[0]["ten"] if ds else "")


# ------------------------------------------------------------------ hạn mức miễn phí
def ky_tu_thang(model: str) -> int:
    """Số ký tự đã gửi trong tháng này (giờ Việt Nam) cho loại giọng `model` (đếm từ bảng lượt dùng AI)."""
    tro_ly._dam_bao_bang()
    dau = gio_viet_nam().replace(day=1, hour=0, minute=0, second=0, microsecond=0) - LECH_GIO_VN
    with session_scope() as s:
        return int(s.execute(select(func.coalesce(func.sum(AiSuDung.token_vao), 0)).where(AiSuDung.model == model, AiSuDung.ts >= dau)).scalar() or 0)


def kiem_han_muc(ten: str, so_ky_tu: int) -> str:
    """Tên ghi lượt dùng của loại giọng; ném `LoiAI` nếu gửi thêm `so_ky_tu` sẽ vượt 95% hạn mức miễn phí tháng này của loại đó (vượt là Google tính tiền)."""
    _, nhan, han, model = loai_cua(ten)
    da_dung = ky_tu_thang(model)
    if da_dung + so_ky_tu > han * AN_TOAN:
        dung, tong = f"{da_dung:,}".replace(",", "."), f"{han:,}".replace(",", ".")
        raise tro_ly.LoiAI(f"Giọng loại {nhan} đã dùng {dung} / {tong} ký tự miễn phí tháng này nên app dừng để không bị Google tính tiền. Chọn giọng loại khác hoặc đợi sang tháng.")
    return model


def tao_am(chu: str, ten: str, key: str) -> bytes:
    """WAV 24 kHz của `chu` bằng giọng `ten`; gặp 429 thì chờ vài giây thử lại một lần."""
    body = {"input": {"text": chu}, "voice": {"languageCode": "vi-VN", "name": ten}, "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": TAN_SO}}
    try:
        kq = _goi("text:synthesize", body, key, 60)
    except tro_ly.LoiAI as e:
        if getattr(e, "ma", None) != 429:
            raise
        time.sleep(4)
        kq = _goi("text:synthesize", body, key, 60)
    b64 = kq.get("audioContent")
    if not b64:
        raise tro_ly.LoiAI("Google không trả về âm thanh.")
    return base64.b64decode(b64)
