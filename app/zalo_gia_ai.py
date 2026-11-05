"""Bot Zalo trả lời SỐ LIỆU dashboard bằng trợ lý AI (chốt 05/11/2026): "IBB7 hôm qua online bao nhiêu", "dự báo cuối tháng toàn chi nhánh",
"DNG.Anhtu hôm nay bán mấy", "IBB7 tồn bao nhiêu HĐ quá 7 ngày".

Dùng lại nguyên `app/tro_ly.py` (chat, kiểm tra, key đã lưu ở Quản trị → Trợ lý AI, ghi `ai_chat`) và `app/tro_ly_du_lieu.py` (công cụ lấy số,
quyền): mọi truy vấn đi qua `chay_cong_cu(user, ...)` nên quyền nằm ở đúng một chỗ, ở đây không tự viết truy vấn nào.

QUYẾT ĐỊNH CỦA CEO: cả nhóm Zalo = MỘT tài khoản admin có sẵn (biến `ZALO_GIA_TAI_KHOAN`): xem hết mọi phòng, mọi số, cả số từng nhân sự, dù nhóm có ~17
sale. Không có tên khách hàng ở bất kỳ đâu (công cụ của trợ lý không trả tên khách). Chỉ chat có trong `ZALO_GIA_CHO_PHEP` mới tới được đây (kiểm ở zalo_gia).
Hạn mức: CEO chọn "không giới hạn", chỉ có MỘT trần an toàn rất cao `ZALO_GIA_AI_TOI_DA_NGAY` (mặc định 300 câu / ngày / chat, 0 = tắt trần).
`ZALO_GIA_AI=0` tắt hẳn đường này (bot chỉ còn trả giá). Câu GIÁ gói cước giữ đường quy tắc cũ (nhanh, không tốn tiền): `huong()` chỉ chuyển
sang AI khi câu có từ khoá số liệu mà không có địa chỉ (phường / xã), hoặc khi giá không tìm ra gì.
"""
from __future__ import annotations

import json
import re
import os
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import tro_ly as ai
from app import tro_ly_du_lieu as dl
from app import zalo_gia_nd as nd
from app.auth import SessionUser, ghi_log
from app.db import engine, session_scope
from app.models import AuditLog, User, ZaloGiaHoiThoai
from app.thoi_gian import gio_viet_nam, utc_bay_gio

HAN_HOI_THOAI = timedelta(minutes=10)
SO_TIN_NHO = 6                        # số tin (hỏi + đáp) giữ lại làm ngữ cảnh hỏi tiếp
TOI_DA_NGAY_MAC_DINH = 300
GHI_LOG_TOI_DA = 200

CHUA_BAT = "Chưa bật trả lời số liệu."
QUA_NHIEU = "Câu này cần tra nhiều số, anh/chị hỏi hẹp lại (một phòng hoặc một kỳ) nhé."
LOI_CHUNG = "Mình chưa tra được số lúc này, anh/chị thử lại sau ít phút nhé."

# Từ khoá (đã bỏ dấu) cho biết đây là câu hỏi SỐ LIỆU. "ban" = bán, "ton" = tồn, "phong" = phòng (khác "phuong" = phường).
_TU_SO = {"online", "ban", "ton", "vvip", "camera", "htkh", "pttb", "nsld", "itn", "dng", "qnm", "ibb", "mttn", "phong"}
_CUM_SO = ("v vip", "du bao", "muc tieu", "hom qua", "hom nay", "hom kia", "thang nay", "thang truoc", "tuan nay", "tuan truoc", "cung ky",
           "hop dong", "bao nhieu", "bao cao", "tang truong", "xep hang", "nhan su", "tan binh", "chi nhanh", "so lieu", "fpt play", "bao nhieu hd")
_TU_DIA_CHI = ("phuong", "xa", "thi tran", "dac khu")
_TU_GOI = {"giga", "sky", "meta", "speedx1", "speedx2", "lux", "lux500", "lux800", "super"}


def bat() -> bool:
    return (os.environ.get("ZALO_GIA_AI") or "1").strip() != "0"


def tran_ngay() -> int:
    try:
        return max(0, int((os.environ.get("ZALO_GIA_AI_TOI_DA_NGAY") or "").strip() or TOI_DA_NGAY_MAC_DINH))
    except ValueError:
        return TOI_DA_NGAY_MAC_DINH


def dam_bao_bang() -> None:
    try:
        ZaloGiaHoiThoai.__table__.create(bind=engine, checkfirst=True)
    except Exception:
        pass


dam_bao_bang()


# ------------------------------------------------------------------ tài khoản đại diện
def tai_khoan() -> SessionUser | None:
    """Tài khoản admin có sẵn mà nhóm dùng chung; không đặt biến, không có tài khoản, đã khoá hoặc KHÔNG phải admin thì None
    (chỉ ĐỌC bảng users, không tạo / sửa / xoá gì)."""
    ten = (os.environ.get("ZALO_GIA_TAI_KHOAN") or "").strip()
    if not ten:
        return None
    try:
        with session_scope() as s:
            row = s.execute(select(User).where(User.username == ten)).scalar_one_or_none()
            return SessionUser(row) if row is not None and row.role == "admin" and row.active else None
    except Exception:
        return None


# ------------------------------------------------------------------ định tuyến giá / AI
def co_tu_so_lieu(q: str) -> bool:
    tu = set(q.split())
    return bool(tu & _TU_SO) or any(f" {c} " in f" {q} " for c in _CUM_SO) or bool(re.search(r"\b(ibb|dng|qnm)\s?\d*\b", q))


def co_dia_chi(q: str) -> bool:
    return any(f" {t} " in f" {q} " for t in _TU_DIA_CHI)


def huong(q: str, hoi_lai: dict | None, dang_hoi_ai: bool) -> str:
    """"gia" (đường quy tắc cũ) | "ai" | "gia_roi_ai" (thử giá, không ra gì thì AI) | "ai_mem" (không giống câu giá lẫn câu
    số liệu: AI nếu đã cài tài khoản đại diện, chưa cài thì giữ đường giá như trước). `q` đã bỏ dấu / @mention; `hoi_lai` là câu giá đang hỏi dở;
    `dang_hoi_ai` là người này vừa hỏi số liệu trong 10 phút (để "còn hôm kia?" đi tiếp bằng AI). Mơ hồ thì ưu tiên giá."""
    if not bat():
        return "gia"
    if not q or q in ("help", "start", "tro giup", "huong dan", "gioi thieu", "id") or q.startswith(("help ", "huong dan ")) \
            or (hoi_lai and (q.isdigit() or hoi_lai.get("buoc") == "cho_phuong")):
        return "gia"
    so, dia = co_tu_so_lieu(q), co_dia_chi(q)
    if so:
        return "gia_roi_ai" if dia else "ai"
    if dia or (set(q.split()) & _TU_GOI):
        return "gia"
    if dang_hoi_ai:
        return "ai"
    if {"gia", "cuoc", "goi"} & set(q.split()):
        return "gia"
    return "ai_mem"


def gia_khong_ra_gi(kq: dict) -> bool:
    """Đường giá không trả lời được gì (không có gói / danh sách, không hỏi lại phường / gói): lúc đó mới đáng chuyển sang AI."""
    hoi = kq.get("hoi") or {}
    return not kq.get("nhat_ky") and hoi.get("buoc") not in ("chon_phuong", "chon_goi")


# ------------------------------------------------------------------ hội thoại nhiều lượt (database, hết hạn 10 phút)
def doc_hoi_thoai(khoa: str) -> list[dict]:
    with session_scope() as s:
        r = s.execute(select(ZaloGiaHoiThoai).where(ZaloGiaHoiThoai.khoa == khoa)).scalar_one_or_none()
        if not r or r.het_han < utc_bay_gio():
            return []
        try:
            ds = json.loads(r.du_lieu)
        except ValueError:
            return []
    return [m for m in ds if isinstance(m, dict) and m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)]


def luu_hoi_thoai(khoa: str, ds: list[dict] | None) -> None:
    """Lưu `SO_TIN_NHO` tin cuối (None = xoá). Hai tin tới cùng lúc: bên nào ghi sau thắng."""
    for _ in range(2):
        try:
            with session_scope() as s:
                r = s.execute(select(ZaloGiaHoiThoai).where(ZaloGiaHoiThoai.khoa == khoa)).scalar_one_or_none()
                if ds is None:
                    if r:
                        s.delete(r)
                    return
                du_lieu = json.dumps([{"role": m["role"], "content": m["content"][:1200]} for m in ds[-SO_TIN_NHO:]], ensure_ascii=False)
                het = utc_bay_gio() + HAN_HOI_THOAI
                if r:
                    r.du_lieu, r.het_han = du_lieu, het
                else:
                    s.add(ZaloGiaHoiThoai(khoa=khoa, du_lieu=du_lieu, het_han=het))
            return
        except IntegrityError:
            continue


def dang_hoi(khoa: str) -> bool:
    return bool(doc_hoi_thoai(khoa))


# ------------------------------------------------------------------ trần ngày + nhật ký
def so_cau_hom_nay(chat_id: str) -> int:
    with session_scope() as s:
        return int(s.execute(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "zalo_gia_ai", AuditLog.detail.like(f"chat {chat_id}:%"), AuditLog.ts >= ai._dau_ngay_utc())).scalar() or 0)


def _ghi(chat_id: str, cau: str) -> None:
    """Chỉ mã chat + 200 ký tự đầu của câu hỏi (đã bỏ @mention); KHÔNG ghi câu trả lời."""
    ghi_log("zalo_gia_ai", f"chat {chat_id}: {' '.join(cau.split())[:GHI_LOG_TOI_DA]}")


# ------------------------------------------------------------------ chữ ra Zalo
def bo_markdown(chu: str) -> str:
    """Zalo không hiển thị Markdown: bỏ ** / # / `, gạch đầu dòng thành "•", dòng bảng thành các ô cách nhau " · "."""
    ra = []
    for dong in (chu or "").replace("\r", "").split("\n"):
        d = dong.rstrip()
        if re.fullmatch(r"\s*\|?[\s:|-]{3,}\|?\s*", d) and "-" in d:
            continue                                                       # dòng kẻ của bảng
        if d.strip().startswith("|") and d.count("|") >= 2:
            d = " · ".join(o.strip() for o in d.strip().strip("|").split("|") if o.strip())
        d = re.sub(r"^\s*#{1,6}\s*", "", d)
        d = re.sub(r"^\s*[-*]\s+", "• ", d)
        d = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), d)
        d = d.replace("`", "")
        d = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", d)
        ra.append(d)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(ra)).strip()


def chia_tin_chu(chu: str) -> list:
    """Tin chữ trơn ≤ 1.900 ký tự (như bot giá): mỗi đoạn một khối, dòng không bị cắt giữa chừng."""
    khoi = [[nd.dong_chu(dong) for dong in doan.split("\n")] for doan in re.split(r"\n\s*\n", chu) if doan.strip()]
    return nd.chia_tin(khoi)


_LOI_CHUA_SAN_SANG = ("đang tắt", "chưa được mở quyền", "mã API", "chưa có mã")


def _loi_de_hieu(e: ai.LoiAI) -> str:
    """Lỗi của trợ lý đã là câu tiếng Việt, nhưng vài câu nói về cài đặt Quản trị thì gói lại cho người dùng nhóm; không lộ chi tiết kỹ thuật."""
    m = str(e)
    if any(t in m for t in _LOI_CHUA_SAN_SANG):
        return "Trợ lý số liệu chưa sẵn sàng. Anh/chị nhờ Admin kiểm tra Quản trị → Trợ lý AI nhé."
    if "tra nhiều số" in m or "chưa tổng hợp xong" in m:
        return QUA_NHIEU
    return m[:300] or LOI_CHUNG


# ------------------------------------------------------------------ trả lời
PHIEN_DAN_ZALO = 2        # tăng khi đổi DAN_ZALO để câu trả lời đã nhớ theo lời dặn cũ hết hiệu lực
DAN_ZALO = """

CÁCH TRẢ LỜI TRÊN ZALO (ưu tiên hơn mọi lời dặn về độ dài ở trên):
- Trả lời NGẮN, 1-4 dòng, đi thẳng vào con số người hỏi cần. Không mở đầu bằng khoảng ngày trong ngoặc.
- Dòng đầu: "<phạm vi> online <dd/mm>: <số> hợp đồng". Rồi nếu có so sánh thì một dòng: "So với <dd/mm>: <số> (tăng/giảm <x>)".
- Ghi ngày cụ thể dd/mm, không viết "hôm qua" trơn. Số của ngày chưa chốt thì thêm đúng chữ "(tạm tính)" sau con số.
- KHÔNG nhận định, KHÔNG suy diễn nguyên nhân, KHÔNG khen chê. Chỉ nêu số và so sánh; người hỏi muốn phân tích thì sẽ hỏi.
- Hỏi nhiều phòng hoặc nhiều người thì mỗi dòng một phòng / người, kiểu "IBB7: 21", không viết thành đoạn văn.
- Chỉ dùng số lấy từ công cụ; không có số thì nói "chưa có số" kèm lý do ngắn."""


def tra_loi(chat_id: str, khoa: str, cau: str) -> list:
    """Hỏi trợ lý bằng quyền của tài khoản đại diện, trả các tin chữ trơn. Không bao giờ ném lỗi."""
    u = tai_khoan()
    if u is None:
        return [CHUA_BAT]
    tran = tran_ngay()
    if tran and so_cau_hom_nay(chat_id) >= tran:
        return [f"Chat này đã hỏi số liệu {tran} lần hôm nay, mai hỏi tiếp nhé."]
    _ghi(chat_id, cau)
    lich_su = doc_hoi_thoai(khoa)
    try:
        co_dinh, thay_doi = dl.ngu_canh_chat(u, "/", {})
        chu = ai.chat(u, lich_su, cau[:600], (co_dinh + DAN_ZALO, thay_doi), dl.cong_cu(u), lambda ten, ts: dl.chay_cong_cu(u, ten, ts),
                      khoa_luu=f"zalo-gia|{gio_viet_nam():%Y-%m-%d}|v{PHIEN_DAN_ZALO}")
    except ai.LoiAI as e:
        return [_loi_de_hieu(e)]
    except Exception:
        return [LOI_CHUNG]
    chu = bo_markdown(chu)
    if not chu:
        return [LOI_CHUNG]
    luu_hoi_thoai(khoa, lich_su + [{"role": "user", "content": cau[:600]}, {"role": "assistant", "content": chu}])
    return chia_tin_chu(chu)
