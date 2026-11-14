"""Giao việc liên khối qua Zalo (nhánh thi-lien-khoi): soạn tin, gửi, nhắc quá hạn, báo quản lý, đọc trả lời của người nhận.

Gửi đi đâu do `kenh()` quyết định, mặc định KHÔNG gửi gì ra ngoài:
- chạy minh hoạ (`LIEN_KHOI_NGUON=demo`): chỉ ghi vào hộp thư giả lập (`theo_doi.hop_thu`), không có tin nào rời máy;
- dữ liệu thật: chỉ gửi thật khi có đủ `LIEN_KHOI_ZALO_TOKEN` (bot RIÊNG, không dùng chung bot Bản tin / Tra giá) và `LIEN_KHOI_ZALO_GUI=1`; thiếu thì ghi "chưa cấu hình".
Tin không có tên khách hàng (chỉ mã hợp đồng, luật, lý do, đề xuất). Người nhận trả lời bằng chữ: "nhận MÃ", "xong MÃ", "không được MÃ lý do".
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import unicodedata
from datetime import datetime

import pandas as pd

from app import zalo_bot
from app.lien_khoi import nguon, theo_doi as td

TOI_DA_KY_TU = 1700                                  # dưới giới hạn tin của Zalo (có chừa chỗ cho phần mở đầu / hướng dẫn)
HUONG_DAN = 'Trả lời: "nhận MÃ", "xong MÃ" hoặc "không được MÃ lý do". Nhiều mã cách nhau bằng dấu cách.'
MA_HD = re.compile(r"\b([A-Za-z]{5}\d{4})\b")
LENH = [("khong_lam_duoc", re.compile(r"\b(khong lam duoc|khong duoc|chua duoc|ket)\b")),
        ("da_xong", re.compile(r"\b(da xong|xong|hoan tat|done)\b")),
        ("da_nhan", re.compile(r"\b(da nhan|nhan|ok)\b"))]
TEN_TT = {"da_nhan": "Đã nhận", "da_xong": "Đã xong", "khong_lam_duoc": "Không làm được"}


def kenh() -> str:
    """"gia_lap" (minh hoạ), "zalo" (gửi thật) hoặc "chua_cau_hinh"."""
    if nguon.la_demo():
        return "gia_lap"
    return "zalo" if os.getenv("LIEN_KHOI_ZALO_TOKEN") and os.getenv("LIEN_KHOI_ZALO_GUI") == "1" else "chua_cau_hinh"


def _gui(ma: str, chat_id: str, loai: str, chu: str, now: datetime) -> str:
    """Gửi (hoặc giả lập) MỘT tin và ghi hộp thư. Trả về kết quả: ok | gia_lap | chua_cau_hinh | thieu_chat_id | loi: ..."""
    k = kenh()
    if k == "zalo" and not chat_id:
        kq = "thieu_chat_id"
    elif k == "zalo":
        try:
            zalo_bot.gui_tin(chat_id, chu, token=os.environ["LIEN_KHOI_ZALO_TOKEN"])
            kq = "ok"
        except zalo_bot.LoiZalo as e:
            kq = f"loi: {e}"
    else:
        kq = k
    td.ghi_hop_thu(ma, chat_id, loai, chu, k, kq, now)
    return kq


def _da_giao(kq: str) -> bool:
    """Tin coi là đã tới tay (hoặc đã giả lập) thì mới đánh dấu "đã gửi"; chưa cấu hình / lỗi thì lượt sau gửi lại."""
    return kq in ("ok", "gia_lap")


def thuc(d: pd.DataFrame) -> pd.Series:
    """Phần việc THẬT (không phải lịch sử mô phỏng của bản minh hoạ): chỉ những phần này được gửi, nhắc, báo quản lý hoặc nhận trả lời."""
    return d["mo_phong"].fillna(0) == 0 if "mo_phong" in d.columns else pd.Series(True, index=d.index)


def _ngay(t) -> str:
    return pd.Timestamp(t).strftime("%d/%m %H:%M")


def _dong(i: int, r) -> str:
    goc = f" (việc của hàng chờ {td.VAI_TRO[r['vai_tro']]}: anh/chị phân cho người phù hợp)" if r["nguoi_goc"] else ""
    return f"{i}) {r['so_hd']} · {r['ten_luat']} ({r['muc']})\n   {r['ly_do']}\n   Cần làm ({td.VAI_TRO[r['vai_tro']]}): {r['de_xuat']}{goc}"


def soan_giao(ten: str, rows: list, han_gio: int) -> list[str]:
    """Tin giao việc cho MỘT người; nhiều việc thì tách thành nhiều tin dưới giới hạn của Zalo."""
    dau = f"Chào {ten}. Có {len(rows)} việc cần xử lý trong {han_gio} giờ:"
    khoi, cur = [], dau
    for i, r in enumerate(rows, 1):
        d = _dong(i, r)
        if len(cur) + len(d) + 2 > TOI_DA_KY_TU and cur != dau:
            khoi.append(cur)
            cur = f"(tiếp) {d}"
        else:
            cur += "\n\n" + d
    khoi.append(cur)
    khoi[-1] += "\n\n" + HUONG_DAN
    return khoi


def _theo_nguoi(d: pd.DataFrame) -> dict:
    return {ma: g.to_dict("records") for ma, g in d.groupby("nguoi", sort=False)}


def _chu_nguoi(ds: pd.DataFrame) -> dict:
    return {r["ma"]: r for r in ds.fillna("").to_dict("records")}


def gui_viec_moi(now: datetime | None = None) -> dict:
    """Gửi cho từng người các phần việc còn mở mà chưa gửi lần nào."""
    now = now or td.bay_gio()
    d = td.danh_sach(now)
    if d.empty:
        return {"nguoi": 0, "viec": 0, "tin": 0}
    han, _ = td.cau_hinh_gio()
    ds = _chu_nguoi(td.nguoi_nhan())
    d = d[d["dang_mo"] & d["da_gui_luc"].isna() & thuc(d)]
    n_nguoi = n_viec = n_tin = 0
    for ma, rows in _theo_nguoi(d).items():
        p = ds.get(ma, {"ten": ma, "chat_id": ""})
        kq = [_gui(ma, p.get("chat_id", ""), "giao", chu, now) for chu in soan_giao(p.get("ten") or ma, rows, han)]
        n_tin += len(kq)
        if all(_da_giao(x) for x in kq):
            td.danh_dau([r["id"] for r in rows], "da_gui_luc", now)
            n_nguoi, n_viec = n_nguoi + 1, n_viec + len(rows)
    return {"nguoi": n_nguoi, "viec": n_viec, "tin": n_tin}


def _tom_tat_viec(rows: list, toi_da: int = 8) -> str:
    dong = [f"- {r['so_hd']} · {r['ten_luat']} ({r['muc']}), giao {_ngay(r['tao_luc'])}" for r in rows[:toi_da]]
    return "\n".join(dong) + (f"\n- ... và {len(rows) - toi_da} việc nữa" if len(rows) > toi_da else "")


def chay_nhac(now: datetime | None = None) -> dict:
    """Quá hạn thì nhắc người nhận (một lần), quá mốc báo quản lý thì báo quản lý của họ (một lần)."""
    now = now or td.bay_gio()
    han, ql = td.cau_hinh_gio()
    d = td.danh_sach(now)
    if d.empty:
        return {"nhac": 0, "bao_quan_ly": 0}
    ds = _chu_nguoi(td.nguoi_nhan())
    mo = d[d["dang_mo"] & thuc(d)]
    a = mo[(mo["tao_luc"] + pd.Timedelta(hours=han) <= pd.Timestamp(now)) & mo["nhac_luc"].isna()]
    for ma, rows in _theo_nguoi(a).items():
        p = ds.get(ma, {"chat_id": ""})
        chu = f"Nhắc: anh/chị còn {len(rows)} việc quá {han} giờ chưa xong:\n{_tom_tat_viec(rows)}\n\n{HUONG_DAN}"
        if _da_giao(_gui(ma, p.get("chat_id", ""), "nhac", chu, now)):
            td.danh_dau([r["id"] for r in rows], "nhac_luc", now)
    b = mo[(mo["tao_luc"] + pd.Timedelta(hours=ql) <= pd.Timestamp(now)) & mo["bao_quan_ly_luc"].isna()]
    n_ql = 0
    quan_ly: dict[str, list] = {}
    for ma, rows in _theo_nguoi(b).items():
        quan_ly.setdefault(ds.get(ma, {}).get("quan_ly", "") or "", []).extend([{**r, "ten_nguoi": ds.get(ma, {}).get("ten") or ma} for r in rows])
    for ma_ql, rows in quan_ly.items():
        theo_ten: dict[str, list] = {}
        for r in rows:
            theo_ten.setdefault(r["ten_nguoi"], []).append(r)
        chu = f"Báo quản lý: có {len(rows)} việc quá {ql} giờ chưa xong:\n" + "\n".join(f"* {t}: {len(v)} việc ({', '.join(x['so_hd'] for x in v[:4])}{'...' if len(v) > 4 else ''})"
                                                                                for t, v in theo_ten.items())
        p = ds.get(ma_ql, {"chat_id": ""})
        kq = _gui(ma_ql or "(chưa có quản lý)", p.get("chat_id", ""), "quan_ly", chu, now) if ma_ql else "khong_co_quan_ly"
        if not ma_ql:
            td.ghi_hop_thu("(chưa có quản lý)", "", "quan_ly", chu, kenh(), kq, now)
        if _da_giao(kq) or kq == "khong_co_quan_ly":
            td.danh_dau([r["id"] for r in rows], "bao_quan_ly_luc", now)
            n_ql += 1
    return {"nhac": len(a), "bao_quan_ly": n_ql}


# ------------------------------------------------------------------ đọc trả lời
def _bo_dau(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def doc_lenh(chu: str) -> tuple[str | None, list[str], str]:
    """Câu trả lời -> (trạng thái mới hoặc None, các mã hợp đồng, ghi chú / lý do)."""
    ma = [m.upper() for m in MA_HD.findall(chu or "")]
    goc = _bo_dau(MA_HD.sub(" ", chu or ""))
    for tt, mau in LENH:
        m = mau.search(goc)
        if m:
            return tt, list(dict.fromkeys(ma)), re.sub(r"\s+", " ", (goc[:m.start()] + " " + goc[m.end():])).strip() if tt == "khong_lam_duoc" else ""
    return None, list(dict.fromkeys(ma)), ""


def xu_ly_tra_loi(nguoi: str, chu: str, now: datetime | None = None) -> str:
    """Người nhận (mã hoặc mã chat Zalo) trả lời bằng chữ; cập nhật trạng thái và trả về câu phản hồi (cũng được gửi / ghi hộp thư)."""
    now = now or td.bay_gio()
    ds = td.nguoi_nhan().fillna("")
    kt = ds[(ds["ma"] == nguoi) | ((ds["chat_id"] == nguoi) & (ds["chat_id"] != ""))]
    ma = str(kt["ma"].iloc[0]) if len(kt) else ""
    chat_id = str(kt["chat_id"].iloc[0]) if len(kt) else ""
    td.ghi_hop_thu(ma or nguoi, chat_id, "nhan_tu_nguoi", chu or "", kenh(), "da_nhan", now)
    if not ma:
        phan_hoi = "Em chưa biết anh/chị là ai trong danh sách người nhận việc. Anh/chị nhờ quản trị thêm mã chat này vào danh sách."
    else:
        phan_hoi = _ap_dung(ma, chu, now)
    _gui(ma or nguoi, chat_id, "phan_hoi", phan_hoi, now)
    return phan_hoi


# ------------------------------------------------------------------ webhook Zalo (tin trả lời thật)
DUONG_DAN_WEBHOOK = "/api/lien-khoi/zalo-webhook"


def khoa_webhook() -> str:
    """HMAC-SHA256(APP_SECRET_KEY, "lien-khoi-webhook") dạng hex: khác khoá của bot Bản tin / Tra giá, không phải lưu thêm gì."""
    from app.config import SECRET_KEY
    return hmac.new(SECRET_KEY.encode(), b"lien-khoi-webhook", hashlib.sha256).hexdigest()


def khoa_dung(khoa: str | None) -> bool:
    """Đường webhook chỉ mở khi đang cấu hình gửi thật; chưa cấu hình (hoặc chạy minh hoạ) thì luôn từ chối dù đúng khoá."""
    return kenh() == "zalo" and hmac.compare_digest((khoa or "").encode(), khoa_webhook().encode())


def url_webhook() -> str | None:
    goc = (os.environ.get("APP_URL") or "").strip().rstrip("/")
    return f"{goc}{DUONG_DAN_WEBHOOK}" if goc else None


def xu_ly_su_kien(payload) -> None:
    """Zalo gọi vào: chỉ nhận tin CHỮ của người thật trong chat riêng; không bao giờ ném lỗi (webhook phải trả 200 để Zalo khỏi gửi lại)."""
    try:
        from app.zalo_gia import doc_tin
        t = doc_tin(payload)
        if t and not t["la_bot"] and t["loai_chat"] in ("", "PRIVATE"):
            xu_ly_tra_loi(t["chat_id"], t["text"])
    except Exception:
        pass


def _ap_dung(ma: str, chu: str, now: datetime) -> str:
    tt, codes, ghi_chu = doc_lenh(chu)
    if tt is None:
        return "Em chưa hiểu. " + HUONG_DAN
    d = td.danh_sach(now)
    mo = d[(d["nguoi"] == ma) & d["dang_mo"] & thuc(d)] if len(d) else d
    if not codes:
        hd = list(dict.fromkeys(mo["so_hd"])) if len(mo) else []
        if len(hd) != 1:
            if not hd:
                return "Hiện anh/chị không có việc nào đang mở. Cảm ơn anh/chị."
            return f"Anh/chị đang có {len(hd)} việc mở. Nhớ ghi mã hợp đồng, ví dụ: xong {hd[0]}. " + HUONG_DAN
        codes = hd
    if tt == "khong_lam_duoc" and not ghi_chu:
        return "Anh/chị ghi thêm lý do giúp em, ví dụ: không được " + codes[0] + " khách hẹn tuần sau."
    ket = []
    for c in codes:
        x = mo[mo["so_hd"] == c] if len(mo) else mo
        for gid in (x["id"].tolist() if len(x) else []):
            td.cap_nhat(int(gid), tt, ma, ghi_chu, now)
        ket.append(f"{c}: {TEN_TT[tt]}" + (f" ({len(x)} phần việc)" if len(x) > 1 else "") if len(x) else f"{c}: không thấy việc đang mở của anh/chị")
    return "Đã ghi nhận.\n" + "\n".join(ket)
