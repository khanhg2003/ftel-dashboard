"""Trợ lý AI: cấu hình, gọi OpenAI, giới hạn lượt dùng / trần chi phí, lưu nhận xét.

- Mã API do Quản trị dán ở Quản trị → Trợ lý AI, mã hoá bằng APP_SECRET_KEY trước khi lưu database
  (đổi APP_SECRET_KEY thì phải dán lại). Chưa dán thì dùng OPENAI_API_KEY trong .env nếu có.
- Gọi thẳng REST API bằng thư viện chuẩn - không thêm thư viện openai cho gọn gói cài trên Vercel.
- Số liệu do app tính và đưa vào; AI chỉ diễn giải. Không bao giờ gửi tên khách hàng.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import socket
import urllib.error
import urllib.request
from datetime import datetime

from sqlalchemy import func, select

from app.config import OPENAI_API_KEY, SECRET_KEY
from app.db import engine, session_scope
from app.models import AiNhanXet, AiSuDung, AuditLog, CaiDat
from app.thoi_gian import gio_viet_nam, LECH_GIO_VN

API = "https://api.openai.com/v1"
HAN_GIAY = 50                     # Vercel cắt yêu cầu ở 60 giây
MAC_DINH = {"bat": False, "ten": "Mây", "model_chat": "gpt-5-mini", "model_nhan_xet": "gpt-5",
            "tran_usd": 20.0, "luot_ngay": 20,
            # ai được dùng: theo vai trò HOẶC từng tài khoản (Quản trị → Trợ lý AI). Chưa lưu = mọi vai trò.
            "vai_tro": ["admin", "operator", "phong"], "tai_khoan": []}
DS_CAU_HINH = ("vai_tro", "tai_khoan")
# USD / 1 triệu token (vào, ra). Model lạ tính theo giá cao để không vượt trần.
GIA = {"gpt-5-nano": (0.05, 0.4), "gpt-5-mini": (0.25, 2.0), "gpt-5": (1.25, 10.0),
       "gpt-4.1-nano": (0.1, 0.4), "gpt-4.1-mini": (0.4, 1.6), "gpt-4.1": (2.0, 8.0),
       "gpt-4o-mini": (0.15, 0.6), "gpt-4o": (2.5, 10.0)}
GIA_LA = (5.0, 20.0)


class LoiAI(Exception):
    """Lỗi hiển thị thẳng cho người dùng (đã viết bằng tiếng Việt)."""


# ------------------------------------------------------------------ cấu hình
_da_tao_bang = False


def _dam_bao_bang() -> None:
    global _da_tao_bang
    if not _da_tao_bang:
        for bang in (CaiDat, AiSuDung, AiNhanXet):
            bang.__table__.create(engine, checkfirst=True)
        _da_tao_bang = True


def _khoa_ma_hoa() -> bytes:
    return hashlib.sha256(("ftel-ai|" + SECRET_KEY).encode()).digest()


def _dong_khoa(khoa: bytes, nonce: bytes, n: int) -> bytes:
    return b"".join(hashlib.sha256(khoa + nonce + i.to_bytes(4, "big")).digest()
                    for i in range(n // 32 + 1))[:n]


def ma_hoa(chu: str) -> str:
    khoa, nonce, du_lieu = _khoa_ma_hoa(), os.urandom(16), chu.encode()
    ma = bytes(a ^ b for a, b in zip(du_lieu, _dong_khoa(khoa, nonce, len(du_lieu))))
    the = hmac.new(khoa, nonce + ma, hashlib.sha256).digest()[:16]
    return base64.b64encode(nonce + the + ma).decode()


def giai_ma(chuoi: str) -> str | None:
    """None nếu chuỗi hỏng hoặc APP_SECRET_KEY đã đổi."""
    try:
        raw = base64.b64decode(chuoi)
        nonce, the, ma = raw[:16], raw[16:32], raw[32:]
        khoa = _khoa_ma_hoa()
        if not hmac.compare_digest(the, hmac.new(khoa, nonce + ma, hashlib.sha256).digest()[:16]):
            return None
        return bytes(a ^ b for a, b in zip(ma, _dong_khoa(khoa, nonce, len(ma)))).decode()
    except Exception:
        return None


def cau_hinh() -> dict:
    """Cấu hình hiện hành. `key` đã giải mã (chỉ dùng phía máy chủ), `key_loi` khi không giải mã được."""
    _dam_bao_bang()
    with session_scope() as s:
        luu = {r.khoa: r.gia_tri for r in s.execute(select(CaiDat).where(CaiDat.khoa.like("ai.%"))).scalars()}
    ch = dict(MAC_DINH)
    for k, v in luu.items():
        k = k[3:]
        if k in ("tran_usd",):
            ch[k] = float(v)
        elif k == "luot_ngay":
            ch[k] = int(v)
        elif k == "bat":
            ch[k] = v == "1"
        elif k in DS_CAU_HINH:
            ch[k] = [x for x in (v or "").split(",") if x]
        elif k != "key" and v:
            ch[k] = v
    ma = luu.get("ai.key")
    ch["key"] = (giai_ma(ma) if ma else None) or ("" if ma else OPENAI_API_KEY)
    ch["key_loi"] = bool(ma) and not ch["key"]
    ch["key_nguon"] = "app" if ma else ("env" if OPENAI_API_KEY else "")
    return ch


def key_an(key: str) -> str:
    return f"{key[:3]}…{key[-4:]}" if key and len(key) > 10 else ""


def luu_cau_hinh(moi: dict, nguoi: str) -> None:
    """moi: các trường cần đổi. key="" không đổi mã; key=None xoá mã đã lưu."""
    _dam_bao_bang()
    with session_scope() as s:
        for k, v in moi.items():
            if k == "key" and v == "":
                continue
            row = s.get(CaiDat, f"ai.{k}")
            if k == "key" and v is None:
                if row:
                    s.delete(row)
                continue
            gia_tri = (ma_hoa(v.strip()) if k == "key" else ",".join(v) if k in DS_CAU_HINH
                       else "1" if v is True else "0" if v is False else str(v))
            if row is None:
                s.add(CaiDat(khoa=f"ai.{k}", gia_tri=gia_tri, updated_by=nguoi))
            else:
                row.gia_tri, row.updated_by, row.updated_at = gia_tri, nguoi, datetime.utcnow()
        chi_tiet = ", ".join(f"{k}={'(đã đổi)' if k == 'key' else v}" for k, v in moi.items()
                             if not (k == "key" and v == ""))
        s.add(AuditLog(username=nguoi, action="ai_cau_hinh", detail=chi_tiet))


# ------------------------------------------------------------------ lượt dùng + chi phí
def _dau_ngay_utc() -> datetime:
    vn = gio_viet_nam()
    return vn.replace(hour=0, minute=0, second=0, microsecond=0) - LECH_GIO_VN


def chi_phi_thang() -> float:
    _dam_bao_bang()
    dau = (gio_viet_nam().replace(day=1, hour=0, minute=0, second=0, microsecond=0) - LECH_GIO_VN)
    with session_scope() as s:
        return float(s.execute(select(func.coalesce(func.sum(AiSuDung.chi_phi_usd), 0))
                               .where(AiSuDung.ts >= dau)).scalar() or 0)


def luot_hom_nay(username: str) -> int:
    _dam_bao_bang()
    with session_scope() as s:
        return int(s.execute(select(func.count()).select_from(AiSuDung).where(
            AiSuDung.username == username, AiSuDung.ts >= _dau_ngay_utc(),
            AiSuDung.loai.in_(["chat", "nhan_xet"]))).scalar() or 0)


def duoc_dung(user, ch: dict) -> bool:
    """AI đang bật và tài khoản này được mở quyền (theo vai trò hoặc chọn riêng từng tài khoản)."""
    return bool(ch["bat"]) and (getattr(user, "role", None) in ch["vai_tro"]
                                or getattr(user, "username", None) in ch["tai_khoan"])


def kiem_tra(user, ch: dict | None = None) -> dict:
    """Trả về cấu hình nếu người này được dùng AI ngay bây giờ, ngược lại ném LoiAI."""
    ch = ch or cau_hinh()
    if not ch["bat"]:
        raise LoiAI("Trợ lý AI đang tắt. Quản trị bật ở Quản trị → Trợ lý AI.")
    if not duoc_dung(user, ch):
        raise LoiAI("Tài khoản của bạn chưa được mở quyền dùng trợ lý AI.")
    if not ch["key"]:
        raise LoiAI("Chưa có mã API ChatGPT (hoặc mã đã lưu không còn dùng được). "
                    "Quản trị dán lại ở Quản trị → Trợ lý AI.")
    if chi_phi_thang() >= ch["tran_usd"]:
        raise LoiAI(f"Đã dùng hết ngân sách AI tháng này ({ch['tran_usd']:g} USD). "
                    "Quản trị có thể nâng trần ở Quản trị → Trợ lý AI.")
    if user.role != "admin" and luot_hom_nay(user.username) >= ch["luot_ngay"]:
        raise LoiAI(f"Bạn đã dùng hết {ch['luot_ngay']} lượt hỏi AI hôm nay. Mai dùng tiếp nhé.")
    return ch


def gia_model(model: str) -> tuple[float, float]:
    for ten in sorted(GIA, key=len, reverse=True):     # "gpt-5-mini-2025..." khớp "gpt-5-mini"
        if model.startswith(ten):
            return GIA[ten]
    return GIA_LA


def _ghi_su_dung(username, loai, model, vao, ra, dem: int = 0) -> float:
    """`dem`: số token vào đã được OpenAI lưu đệm (prompt caching) - tính 10% giá."""
    g_vao, g_ra = gia_model(model)
    chi_phi = ((vao - dem) * g_vao + dem * g_vao * 0.1 + ra * g_ra) / 1_000_000
    with session_scope() as s:
        s.add(AiSuDung(username=username, loai=loai, model=model, token_vao=vao, token_ra=ra,
                       chi_phi_usd=chi_phi))
    return chi_phi


def thong_ke_su_dung() -> list[dict]:
    """Theo người: lượt hôm nay, lượt tháng, chi phí tháng."""
    _dam_bao_bang()
    dau_thang = gio_viet_nam().replace(day=1, hour=0, minute=0, second=0, microsecond=0) - LECH_GIO_VN
    dau_ngay = _dau_ngay_utc()
    with session_scope() as s:
        rows = s.execute(select(AiSuDung.username, AiSuDung.ts, AiSuDung.chi_phi_usd, AiSuDung.loai)
                         .where(AiSuDung.ts >= dau_thang)).all()
    kq: dict[str, dict] = {}
    for u, ts, cp, loai in rows:
        r = kq.setdefault(u or "", {"username": u or "", "hom_nay": 0, "thang": 0, "chi_phi": 0.0})
        if loai in ("chat", "nhan_xet"):
            r["thang"] += 1
            r["hom_nay"] += ts >= dau_ngay
        r["chi_phi"] += cp or 0
    return sorted(kq.values(), key=lambda r: -r["chi_phi"])


# ------------------------------------------------------------------ gọi OpenAI
def _goi_api(duong_dan: str, key: str, body: dict | None = None, han: float = HAN_GIAY) -> dict:
    req = urllib.request.Request(f"{API}/{duong_dan}", method="POST" if body is not None else "GET",
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=max(5, han)) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            chi_tiet = json.loads(e.read()).get("error", {}).get("message", "")
        except Exception:
            chi_tiet = ""
        thong_bao = {401: "Mã API không hợp lệ hoặc đã bị thu hồi.",
                     403: "Mã API không có quyền dùng model này.",
                     404: "Không tìm thấy model - kiểm tra lại tên model trong cấu hình.",
                     429: "OpenAI báo hết hạn mức (quá nhiều yêu cầu hoặc tài khoản hết tiền)."}
        loi = LoiAI(thong_bao.get(e.code, f"OpenAI báo lỗi {e.code}.")
                    + (f" ({chi_tiet[:160]})" if chi_tiet and e.code not in (401,) else ""))
        loi.ma, loi.chi_tiet = e.code, chi_tiet
        raise loi from None
    except (socket.timeout, TimeoutError):
        raise LoiAI("AI trả lời quá lâu, thử lại sau ít phút.") from None
    except urllib.error.URLError:
        raise LoiAI("Không kết nối được tới OpenAI, thử lại sau.") from None


def thu_ket_noi(key: str, model: str) -> str:
    """Kiểm tra mã + tên model mà không tốn tiền. Trả về thông báo thành công, lỗi thì ném LoiAI."""
    _goi_api(f"models/{model}", key, han=15)
    return f"Kết nối tốt · mã hợp lệ · dùng được model {model}."


def _muc_suy_nghi(model: str) -> str | None:
    """Model suy luận (gpt-5, o3, o4) tính cả token "suy nghĩ" vào giới hạn độ dài. Diễn giải số liệu không cần
    suy nghĩ sâu -> để mức thấp nhất, vừa nhanh vừa không bị hết chỗ viết câu trả lời."""
    if model.startswith("gpt-5"):
        return "minimal"
    return "low" if model.startswith(("o3", "o4")) else None


def hoi(messages: list[dict], model: str, key: str, username: str, loai: str,
        tools: list | None = None, han: float = HAN_GIAY, toi_da: int = 6000, suy_nghi: str | None = None) -> dict:
    """Một lượt Chat Completions, ghi lượt dùng. Trả về message của AI.

    Tự xử lý 2 trường hợp hay gặp với model suy luận:
    - model không nhận mức 'minimal' (bản mới hơn gpt-5) -> gọi lại với 'low';
    - dùng hết giới hạn độ dài mà chưa viết được chữ nào (finish_reason = length) -> gọi lại một lần với gấp
      đôi giới hạn. Vẫn không được thì báo lỗi rõ ràng thay vì trả về rỗng.
    """
    muc = _muc_suy_nghi(model)
    if suy_nghi and muc:              # nhận xét trang: nghĩ kỹ hơn một chút để tuân thủ lời dặn về giọng văn
        muc = suy_nghi
    bat_dau = datetime.utcnow()
    for lan in range(3):
        body = {"model": model, "messages": messages, "max_completion_tokens": toi_da}
        if muc:
            body["reasoning_effort"] = muc
        if tools:
            body["tools"] = tools
        con = han - (datetime.utcnow() - bat_dau).total_seconds()
        try:
            kq = _goi_api("chat/completions", key, body, con)
        except LoiAI as e:
            if getattr(e, "ma", None) == 400 and muc == "minimal" and "reasoning" in (getattr(e, "chi_tiet", "") or ""):
                muc = "low"
                continue
            raise
        dung = kq.get("usage") or {}
        _ghi_su_dung(username, loai if lan == 0 else f"{loai}_lai", kq.get("model") or model, int(dung.get("prompt_tokens") or 0),
                     int(dung.get("completion_tokens") or 0),
                     int((dung.get("prompt_tokens_details") or {}).get("cached_tokens") or 0))
        chon = kq["choices"][0]
        msg = chon["message"]
        if msg.get("content") or msg.get("tool_calls") or chon.get("finish_reason") != "length":
            return msg
        if lan == 2 or con < 15:
            break
        toi_da *= 2
    raise LoiAI("AI dùng hết giới hạn độ dài mà chưa viết xong câu trả lời - bấm tạo lại, hoặc đổi model nhận xét "
                "sang gpt-5-mini ở Quản trị → Trợ lý AI.")


# ------------------------------------------------------------------ lời dặn chung
# Đổi khi sửa lời dặn: câu trả lời chat đã lưu theo lời dặn cũ tự hết hiệu lực
PHIEN_LOI_DAN = "8"


# Ngưỡng BGĐ chốt 17/09/2026
MAU_NHO_CUNG_KY = 30               # cùng kỳ dưới 30 số: không khen/chê theo %
DANG_KE_PCT, DANG_KE_SO = 10, 10   # "đáng kể" khi chênh từ 10% VÀ từ 10 số

QUY_TAC_INSIGHT = (
    "CÁCH RÚT RA INSIGHT (không chỉ đọc lại số):\n"
    "- Mỗi ý: con số chính -> ý nghĩa của nó (vậy thì sao). Ý nghĩa phải dựa trên số liệu được cung cấp.\n"
    "- Tiến độ: so %HTKH với '% thời gian đã qua' (cột 'Chênh tiến độ' = %HTKH - % thời gian; âm là chậm "
    "tiến độ). Kịp mục tiêu hay không: dựa dự báo cuối tháng và 'Cần mỗi ngày' so với 'TB/ngày'.\n"
    "- Xu hướng gần: so '7 ngày gần nhất' với '7 ngày trước đó' để nói đang tăng tốc hay chậm lại.\n"
    "- Quy mô thật: luôn nhìn 'Chênh cùng kỳ (số)' cạnh %; tăng % lớn trên nền nhỏ ít ý nghĩa hơn tăng nhiều "
    "số. Cột '% phần tăng/giảm của cả chi nhánh' = phần của phòng trong tổng mức tăng (hoặc giảm) của các phòng: "
    "dùng để nói phòng nào đóng góp / sụt nhiều nhất.\n"
    f"- Mẫu nhỏ: cùng kỳ dưới {MAU_NHO_CUNG_KY} số (cột 'Mẫu nhỏ' = có) thì KHÔNG khen/chê theo %, chỉ ghi "
    "'quy mô nhỏ'.\n"
    f"- Chỉ gọi là tăng/giảm 'đáng kể' khi chênh từ {DANG_KE_PCT}% VÀ từ {DANG_KE_SO} số trở lên; dưới "
    "ngưỡng thì nói 'tương đương'.\n"
    "- Vì sao: chỉ truy nguyên trong dữ liệu (nhân sự, ngày, gói, số tồn; trong chat dùng công cụ chan_doan_phong); tuyệt "
    "đối không đoán nguyên nhân bên ngoài (thời tiết, chính sách, đối thủ...).\n"
    "- Số tồn là dư địa: tồn chờ từ 7 ngày nhiều thì nêu là cơ hội chuyển thành online.\n"
    "- Ngày đang cập nhật (số tạm tính): không kết luận giảm dựa trên riêng ngày đó.\n")


# Giọng văn chung cho nhận xét và chat (chốt 18/09/2026: bớt "robot", nói như người quản lý)
GIONG_VAN = (
    "GIỌNG VĂN (bắt buộc):\n"
    "- Viết như một giám đốc kinh doanh đang báo cáo nhanh trong buổi giao ban với BGĐ: câu ngắn, tự nhiên, nói "
    "thẳng vấn đề, nói rõ ai cần làm gì. Nhận định trước, số làm bằng chứng sau.\n"
    "- KHÔNG dùng các cụm máy móc: 'kéo tăng', 'kéo giảm', 'kéo tụt', 'kéo lên', 'đòn bẩy', 'tác động ~X%', "
    "'lấp khoảng X/Y', 'chênh tiến độ', 'mẫu nhỏ', 'tồn ≥7', 'dư địa', ký hiệu '~', '→', và tên cột trong dữ liệu.\n"
    "- Thay bằng lời thường: 'đóng góp nhiều nhất', 'sụt so với tháng trước', 'hợp đồng đã chờ quá 7 ngày', 'gỡ "
    "được khoảng một phần ba phần còn thiếu', 'chậm hơn nhịp tháng trước', 'khoảng 40 số'.\n"
    "- Nêu tên người khi cần hành động, giọng xây dựng (cần kèm, cần hỗ trợ), không phán xét.\n"
    "- Không mở đầu bằng câu chung chung ('Nhìn chung...', 'Có thể thấy...'), không rào đón.\n")

VI_DU_NHAN_XET = (
    "VÍ DỤ VIẾT ĐẠT (chỉ để học giọng văn, KHÔNG dùng số trong ví dụ):\n"
    "**Nhận định:** Tháng này vẫn trong tầm với: đang đi đúng nhịp tháng trước và dự báo đạt 96% mục tiêu. Điều "
    "đáng lo không nằm ở số lượng mà ở chỗ khách phải chờ lắp đặt lâu hơn tháng trước.\n"
    "**Vì sao:**\n"
    "- Kỹ thuật Đà Nẵng 1 và Quảng Nam triển khai chậm đi rõ: tỷ lệ online trong ngày giảm 10 điểm, trong khi hai "
    "khu vực này chiếm hơn nửa số hợp đồng.\n"
    "- IBB2 có 4 sale đang dưới một nửa mặt bằng phòng; nếu họ lên được mức trung bình, phòng có thêm khoảng 40 "
    "số, đủ bù phần hụt.\n"
    "**Việc cần làm:**\n"
    "- Kỹ thuật Đà Nẵng 1, Quảng Nam: rà lịch lắp đặt, đưa tỷ lệ online trong ngày về lại 80% trong tuần này.\n"
    "- Trưởng phòng IBB2: kèm riêng 4 sale số thấp, theo dõi số online từng người mỗi ngày.\n"
    "VÍ DỤ CHƯA ĐẠT (tránh): 'Kéo giảm: Lê Văn A (16 online, giảm 7 so cùng kỳ), Trần B (25, giảm 6)... tác động "
    "~33%, lấp khoảng 120/366 phần thiếu' - chỉ liệt kê số, dùng từ máy móc, không nói vì sao và ai làm gì.\n")

# Nhận xét trên trang: người đọc ĐÃ thấy bảng số ngay bên trên -> chỉ cần nhận định, nguyên nhân và việc cần làm.
DINH_DANG_NHAN_XET = (
    "- Người đọc đang nhìn bảng số ngay phía trên: KHÔNG chép lại bảng, KHÔNG liệt kê số từng phòng / từng người. "
    "Cả bài dùng tối đa 4-5 con số then chốt làm bằng chứng; phần còn lại là nhận định.\n"
    "- Tối đa khoảng 140 từ, đúng 3 phần, tiêu đề in đậm:\n"
    "  **Nhận định:** 1-2 câu: tình hình và mức độ đáng lo, đặt trong BỐI CẢNH THÁNG (so nhịp tháng trước, rủi ro "
    "chung của chi nhánh) - không chỉ nhắc lại một con số.\n"
    "  **Vì sao:** 2-3 gạch đầu dòng, mỗi gạch MỘT nguyên nhân gắn với người / bộ phận cụ thể (phòng, sale, kỹ thuật "
    "khu vực) và nối ít nhất 2 tín hiệu (VD 'hụt không phải do thiếu người mà do 4 sale số thấp hẳn mặt bằng').\n"
    "  **Việc cần làm:** 2-3 gạch theo mẫu 'Ai: làm gì, theo dõi bằng chỉ số nào'. Giao đúng vai: "
    "sale và trưởng phòng (bán, bán kèm, kèm sale yếu, bám hợp đồng chờ), kỹ thuật khu vực (triển khai nhanh), BGĐ "
    "(điều phối, hỗ trợ phòng rủi ro). Xếp việc có tác động lớn nhất lên trước; nếu có số ước tính thì nói bằng "
    "lời (VD 'thêm khoảng 40 số').\n"
    "- Chỉ nói điều bảng không tự nói ra. Không nhắc chỉ số không phục vụ nhận định.\n"
    "- Dựa vào phần BỐI CẢNH THÁNG và TÍN HIỆU (app đã tính sẵn). Mỗi trang nhận xét theo LĂNG KÍNH của trang (nêu "
    "trong yêu cầu), chỉ mượn bối cảnh chung để giải thích.\n"
    "- Chỉ giao việc cho phòng / bầy / khu vực / người có trong dữ liệu; KHÔNG bịa bộ phận, KPI, chính sách; không "
    "diễn giải 'Cần mỗi ngày' thành chỉ tiêu tuần. Không nêu tên trưởng phòng hay người đã nghỉ như người cần kèm.\n"
    "- KHÔNG tự đặt con số mục tiêu mới (VD 'đưa về 80%', 'trên 75% trong tuần', 'giảm xuống 20 trong 10 ngày', "
    "'mỗi người thêm 2 số/tuần'); chỉ dùng số app đã tính (VD 'phòng thêm khoảng 39 số nếu họ đạt mặt bằng', mức "
    "cùng kỳ tháng trước). KHÔNG đề xuất nguồn lực, phương tiện, thời hạn không có trong dữ liệu (thêm người, thêm "
    "đội, tăng ca, xe, 'tối nay', 'họp gấp', 'phê duyệt').\n"
    "- Mỗi gạch đầu dòng tối đa khoảng 30 từ, 1 ý, không lặp tên người.\n"
    + VI_DU_NHAN_XET +
    "TRƯỚC KHI TRẢ LỜI, TỰ SOÁT: (1) không có chữ 'kéo', 'đòn bẩy', 'dư địa', ký hiệu '~', '→', '≥', '>'; (2) không "
    "tự đặt con số mục tiêu mới; (3) cả bài không quá 5 con số; (4) mỗi việc cần làm có đúng người làm; (5) viết "
    "lại câu nào còn giống liệt kê số.\n")


# Làm sạch sau khi AI trả lời: model nhỏ đôi khi vẫn lọt ký hiệu / cụm máy móc dù đã dặn -> sửa chắc chắn ở đây
_THAY = [
    (r"[>≥]\s*=?\s*(\d+)\s*ngày", r"quá \1 ngày"),            # ">7 ngày", "≥7 ngày" -> "quá 7 ngày"
    (r"(?<![\w])~\s*", "khoảng "),                               # "~39" -> "khoảng 39"
    (r"(?<=\d),(?=\d{3}(?!\d))", "."),                           # 4,211 (kiểu Anh) -> 4.211
    (r"(?<=\d)\.(?=\d(?!\d))", ","),                            # 129.8 -> 129,8 (1 chữ số thập phân)
    (r"(?<=\d)\.(?=\d{2}(?!\d))", ","),                          # 7.25 -> 7,25
    (r"\s*→\s*", " → "),
    (r"\bkéo (tụt|giảm|xuống)\b", r"làm \1"),
    (r"\bkéo (tăng|lên)\b", "đóng góp tăng"),
    (r"\bkéo tiến độ\b", "ảnh hưởng tiến độ"),
    (r"\bđòn bẩy\b", "cơ hội"),
    (r"\bdư địa\b", "cơ hội"),
    (r"\s*\((?:số này )?do hệ thống tính[^)]*\)", ""),
]


def lam_sach(chu: str) -> str:
    import re
    for mau, thay in _THAY:
        chu = re.sub(mau, thay, chu)
    return re.sub(r"làm (tụt|giảm) giảm", r"làm \1", chu).strip()


def loi_dan(ten: str, chat: bool = False) -> str:
    dinh_dang = ("" if chat else DINH_DANG_NHAN_XET)
    return (
        f"Bạn là {ten}, trợ lý phân tích số liệu kinh doanh của FPT Telecom chi nhánh Đà Nẵng & Quảng Nam. "
        "Người đọc là Ban giám đốc và trưởng phòng kinh doanh.\n"
        "Quy tắc bắt buộc:\n"
        "- CHỈ dùng số liệu được cung cấp (hoặc lấy qua công cụ). Không tự bịa, không ước đoán số. "
        "Thiếu dữ liệu thì nói rõ là chưa có.\n"
        "- Viết tiếng Việt.\n" + GIONG_VAN + dinh_dang + 
        "- Thuật ngữ: 'online' là hợp đồng Internet đã online; 'số tồn' là hợp đồng chưa online; "
        "'cùng kỳ' là cùng khoảng ngày tháng trước; HTKH là % hoàn thành kế hoạch (mục tiêu); "
        "PTTB là số online; V.VIP là gói FPT Play V.VIP. Luôn gọi là 'online', không dùng từ khác.\n"
        "- Số dự báo cuối tháng do hệ thống tính bằng công thức, chỉ diễn giải, không tự tính lại.\n"
        "- Định dạng số kiểu Việt Nam (1.394), phần trăm làm tròn.\n" + QUY_TAC_INSIGHT)


# ------------------------------------------------------------------ nhận xét có lưu lại
def phien_du_lieu() -> str:
    """Đổi mỗi khi nạp file hoặc sửa mục tiêu -> nhận xét cũ tự hết hiệu lực."""
    from sqlalchemy import text
    with engine.connect() as c:
        lo = c.execute(text("SELECT MAX(id) FROM upload_batch")).scalar()
        mt = c.execute(text("SELECT MAX(updated_at) FROM target_monthly")).scalar()
    return f"{lo}|{mt}"


def _khoa(loai: str, khoa: str) -> str:
    return hashlib.sha256(f"{loai}|{khoa}|{phien_du_lieu()}|v{PHIEN_LOI_DAN}".encode()).hexdigest()


def nhan_xet_da_luu(loai: str, khoa: str) -> dict | None:
    _dam_bao_bang()
    with session_scope() as s:
        r = s.get(AiNhanXet, _khoa(loai, khoa))
        return {"noi_dung": r.noi_dung, "username": r.username, "luc": r.created_at} if r else None


def tao_nhan_xet(user, loai: str, khoa: str, du_lieu: str, yeu_cau: str) -> dict:
    """Gọi AI tạo nhận xét cho `du_lieu` rồi lưu lại (ghi đè bản cũ cùng khoá)."""
    ch = kiem_tra(user)
    msg = hoi([{"role": "system", "content": loi_dan(ch["ten"])},
               {"role": "user", "content": f"{yeu_cau}\n\nSỐ LIỆU:\n{du_lieu}"}],
              ch["model_nhan_xet"], ch["key"], user.username, "nhan_xet", toi_da=8000, suy_nghi="low")
    noi_dung = lam_sach(msg.get("content") or "")
    if not noi_dung:
        raise LoiAI("AI chưa trả lời được, bấm tạo lại.")
    k = _khoa(loai, khoa)
    with session_scope() as s:
        r = s.get(AiNhanXet, k)
        if r:
            r.noi_dung, r.username, r.created_at = noi_dung, user.username, datetime.utcnow()
        else:
            s.add(AiNhanXet(khoa=k, loai=loai, noi_dung=noi_dung, username=user.username))
        s.add(AuditLog(username=user.username, action="ai_nhan_xet", detail=f"{loai} {khoa}"))
    return {"noi_dung": noi_dung, "username": user.username, "luc": datetime.utcnow()}


def chat(user, lich_su: list[dict], cau_hoi: str, ngu_canh: tuple[str, str], cong_cu: list, chay_cong_cu,
         khoa_luu: str | None = None) -> str:
    """Hỏi đáp có gọi công cụ lấy số. `chay_cong_cu(ten, tham_so) -> str`.

    Tiết kiệm token: câu hỏi đầu (chưa có hội thoại) trùng câu đã có người hỏi cùng trang, bộ lọc, quyền và
    phiên số liệu thì trả bản đã lưu, không gọi AI; lời dặn cố định đặt đầu để OpenAI lưu đệm; chỉ gửi 6 tin
    gần nhất, mỗi tin rút gọn.
    """
    k = (f"{' '.join(cau_hoi.lower().split())}|{khoa_luu}|v{PHIEN_LOI_DAN}"
         if khoa_luu and not lich_su else None)
    ch = cau_hinh()
    if k and duoc_dung(user, ch):
        ban = nhan_xet_da_luu("chat", k)
        if ban:
            return ban["noi_dung"]
    ch = kiem_tra(user, ch)
    # Chặn gửi trùng ở máy chủ: cùng người, cùng câu đang được trả lời (bấm nhiều lần, mở nhiều tab) thì không
    # gọi AI thêm lần nữa. Lưu trong database vì trên Vercel mỗi yêu cầu có thể chạy ở một máy khác.
    khoa_dang = hashlib.sha256(f"dang|{user.username}|{' '.join(cau_hoi.lower().split())}".encode()).hexdigest()
    with session_scope() as s:
        r = s.get(AiNhanXet, khoa_dang)
        if r and (datetime.utcnow() - r.created_at).total_seconds() < HAN_GIAY + 10:
            raise LoiAI("Câu này đang được trả lời, bạn chờ vài giây nhé.")
        s.merge(AiNhanXet(khoa=khoa_dang, loai="dang_hoi", noi_dung="", username=user.username,
                          created_at=datetime.utcnow()))
    try:
        return _chat(user, ch, lich_su, cau_hoi, ngu_canh, cong_cu, chay_cong_cu, k)
    finally:
        with session_scope() as s:
            r = s.get(AiNhanXet, khoa_dang)
            if r:
                s.delete(r)


def _chat(user, ch, lich_su, cau_hoi, ngu_canh, cong_cu, chay_cong_cu, k) -> str:
    co_dinh, thay_doi = ngu_canh
    messages = [{"role": "system", "content": loi_dan(ch["ten"], chat=True) + co_dinh},
                {"role": "system", "content": "NGỮ CẢNH HIỆN TẠI:\n" + thay_doi},
                *[{"role": m["role"], "content": m["content"][:1200]} for m in lich_su[-6:]],
                {"role": "user", "content": cau_hoi}]
    bat_dau = datetime.utcnow()
    tong_chi_phi_truoc = chi_phi_thang()
    for vong in range(5):
        con = HAN_GIAY - (datetime.utcnow() - bat_dau).total_seconds()
        if con < 8:
            raise LoiAI("Câu hỏi cần tra nhiều số quá, hãy hỏi hẹp lại (một phòng hoặc một kỳ).")
        msg = hoi(messages, ch["model_chat"], ch["key"], user.username, "chat" if vong == 0 else "chat_tiep",
                  tools=cong_cu if vong < 4 else None, han=con, toi_da=4000)
        goi = msg.get("tool_calls") or []
        if not goi:
            tra_loi = lam_sach(msg.get("content") or "")
            if not tra_loi:
                raise LoiAI("Mình chưa trả lời được câu này, bạn hỏi lại cụ thể hơn nhé.")
            with session_scope() as s:
                s.add(AuditLog(username=user.username, action="ai_chat",
                               detail=f"{cau_hoi[:300]} · ~{chi_phi_thang() - tong_chi_phi_truoc:.4f} USD"))
                if k and vong > 0:              # chỉ lưu câu trả lời đã dựa trên số lấy từ công cụ
                    s.merge(AiNhanXet(khoa=_khoa("chat", k), loai="chat", noi_dung=tra_loi, username=user.username))
            return tra_loi
        messages.append({"role": "assistant", "content": msg.get("content"), "tool_calls": goi})
        for g in goi:
            try:
                tham_so = json.loads(g["function"].get("arguments") or "{}")
                ket_qua = chay_cong_cu(g["function"]["name"], tham_so)
            except LoiAI as e:
                ket_qua = f"LỖI: {e}"
            except Exception as e:                       # tham số sai -> báo lại để AI tự sửa
                ket_qua = f"LỖI: {type(e).__name__}: {str(e)[:200]}"
            messages.append({"role": "tool", "tool_call_id": g["id"], "content": ket_qua[:30000]})
    raise LoiAI("Mình chưa tổng hợp xong, bạn hỏi cụ thể hơn nhé.")
