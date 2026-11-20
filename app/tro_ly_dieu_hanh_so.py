"""Sổ quyết định của TRỢ LÝ ĐIỀU HÀNH: mỗi vấn đề trợ lý đề xuất là một dòng, người có quyền chọn phương án, trợ lý nhắc và kiểm chứng.

Chỉ dùng ba bảng MỚI (`td_quyet_dinh`, `td_quyet_dinh_nk`, `td_phu`); không đọc hay sửa bảng số liệu nào của app.
Trạng thái: `cho_quyet` -> `da_quyet` (hoặc `bac`) -> `da_kiem_chung`. Quá hạn quyết mà chưa quyết: nhắc, quá nữa thì báo cấp trên và đổi sang
`qua_han` (vẫn quyết được). Mọi đổi trạng thái chỉ thành công khi đang ở trạng thái hợp lệ (hai người cùng quyết một lúc thì chỉ một lượt được ghi)
và đều ghi nhật ký. Mốc giờ lưu UTC không kèm múi giờ như phần còn lại của app. Hàm ở đây chỉ lưu và đọc.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.config import rules_config
from app.db import engine, session_scope
from app.models import TdPhu, TdQuyetDinh, TdQuyetDinhNk
from app.thoi_gian import utc_bay_gio

TRANG_THAI = {"cho_quyet": "Chờ quyết", "da_quyet": "Đã quyết", "bac": "Đã bác", "qua_han": "Quá hạn quyết", "da_kiem_chung": "Đã kiểm chứng"}
CHO = ("cho_quyet", "qua_han")                       # còn quyết được
MO = ("cho_quyet", "qua_han", "da_quyet")            # còn đang theo dõi: chưa tạo vấn đề mới cùng nhóm
LUA_CHON_SUA = "sua"
COT_JSON = ("su_that", "phuong_an", "chi_so_truoc", "chi_so_sau")
MAC_DINH = {"bat": False, "tu_dong": False, "han_quyet_gio": 8, "leo_thang_gio": 16, "kiem_chung_gio": 48, "tran_llm_ngay": 30, "toi_da_van_de": 8}
_da_tao_bang = False


def cau_hinh() -> dict:
    """Cấu hình ở `rules.yml` → `tro_ly_dieu_hanh` (thiếu khoá nào lấy mặc định; mặc định TẮT)."""
    c = (rules_config().get("tro_ly_dieu_hanh")) or {}
    return {k: (bool(c.get(k, v)) if isinstance(v, bool) else type(v)(c.get(k, v))) for k, v in MAC_DINH.items()}


def bat() -> bool:
    return bool(cau_hinh()["bat"])


def dam_bao_bang() -> None:
    """Tạo ba bảng của trợ lý nếu chưa có (Supabase / máy chủ cũ không chạy create_all lúc khởi động). Chỉ gọi khi tính năng được dùng."""
    global _da_tao_bang
    if not _da_tao_bang:
        for b in (TdQuyetDinh, TdQuyetDinhNk, TdPhu):
            b.__table__.create(bind=engine, checkfirst=True)
        _da_tao_bang = True


def sach(v):
    """Đổi về kiểu JSON thuần: số numpy -> số Python, NaN -> None, ngày giờ -> chuỗi ISO (bảng số liệu của app trả về kiểu numpy / pandas)."""
    if isinstance(v, dict):
        return {str(k): sach(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [sach(x) for x in v]
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        try:
            v = v.item()
        except (ValueError, TypeError):
            return str(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return None if isinstance(v, float) and v != v else v


def _json(v) -> dict | list:
    try:
        return json.loads(v) if isinstance(v, str) and v else {}
    except ValueError:
        return {}


def _dong(r: TdQuyetDinh) -> dict:
    d = {c.name: getattr(r, c.name) for c in TdQuyetDinh.__table__.columns}
    for c in COT_JSON:
        d[c] = _json(d.get(c))
    d["phuong_an"] = d["phuong_an"] or []
    return d


def _nk(s, qid: int, luc: datetime, boi: str, hanh_dong: str, ghi_chu: str = "") -> None:
    s.add(TdQuyetDinhNk(quyet_dinh_id=qid, luc=luc, boi=(boi or "")[:120], hanh_dong=hanh_dong, ghi_chu=ghi_chu or None))


# ------------------------------------------------------------------ tạo và đọc
def tao(van_de: dict, now: datetime | None = None) -> int | None:
    """Thêm một đề xuất mới. Trả None khi cùng `ma_van_de` đã có (không tạo trùng trong ngày) hoặc cùng nhóm vẫn đang theo dõi
    (chờ quyết / quá hạn / đã quyết chưa kiểm chứng): tránh một vấn đề kéo dài thành mỗi ngày một đề xuất."""
    dam_bao_bang()
    now = now or utc_bay_gio()
    gia_tri = {k: (json.dumps(sach(v), ensure_ascii=False) if k in COT_JSON and v is not None else v) for k, v in van_de.items()}
    with session_scope() as s:
        if s.execute(select(TdQuyetDinh.id).where(TdQuyetDinh.nhom == van_de["nhom"], TdQuyetDinh.trang_thai.in_(MO)).limit(1)).first():
            return None
    try:
        with session_scope() as s:
            r = TdQuyetDinh(**gia_tri, trang_thai="cho_quyet", tao_luc=now, cap_nhat_luc=now)
            s.add(r)
            s.flush()
            _nk(s, r.id, now, "tro_ly", "de_xuat", van_de.get("tieu_de", ""))
            return r.id
    except IntegrityError:
        return None


def doc(qid: int) -> dict | None:
    dam_bao_bang()
    with session_scope() as s:
        r = s.get(TdQuyetDinh, int(qid))
        return _dong(r) if r else None


def doc_theo_ma(ma_van_de: str) -> dict | None:
    dam_bao_bang()
    with session_scope() as s:
        r = s.execute(select(TdQuyetDinh).where(TdQuyetDinh.ma_van_de == ma_van_de)).scalar_one_or_none()
        return _dong(r) if r else None


def liet_ke(trang_thai: str | tuple | None = None) -> list[dict]:
    """Toàn bộ sổ, mới nhất trước (có thể lọc theo một hoặc nhiều trạng thái)."""
    dam_bao_bang()
    q = select(TdQuyetDinh).order_by(TdQuyetDinh.id.desc())
    if trang_thai:
        q = q.where(TdQuyetDinh.trang_thai.in_([trang_thai] if isinstance(trang_thai, str) else list(trang_thai)))
    with session_scope() as s:
        return [_dong(r) for r in s.execute(q).scalars()]


def qua_han(now: datetime | None = None) -> list[dict]:
    """Đề xuất còn chờ mà đã quá `han_quyet`."""
    now = now or utc_bay_gio()
    return [r for r in sorted(liet_ke(CHO), key=lambda r: r["id"]) if r["han_quyet"] and r["han_quyet"] <= now]


def can_kiem_chung(now: datetime | None = None) -> list[dict]:
    """Quyết định đã quyết, tới hạn đo lại mà chưa kiểm chứng."""
    now = now or utc_bay_gio()
    return [r for r in sorted(liet_ke("da_quyet"), key=lambda r: r["id"]) if r["han_kiem_chung"] and r["han_kiem_chung"] <= now]


def nhat_ky(qid: int) -> list[dict]:
    dam_bao_bang()
    with session_scope() as s:
        return [{"luc": r.luc, "boi": r.boi, "hanh_dong": r.hanh_dong, "ghi_chu": r.ghi_chu or ""}
                for r in s.execute(select(TdQuyetDinhNk).where(TdQuyetDinhNk.quyet_dinh_id == int(qid)).order_by(TdQuyetDinhNk.id)).scalars()]


def tom_tat() -> dict:
    dam_bao_bang()
    with session_scope() as s:
        dem = dict(s.execute(select(TdQuyetDinh.trang_thai, func.count()).group_by(TdQuyetDinh.trang_thai)).all())
    return {"tong": int(sum(dem.values())), "cho_quyet": int(dem.get("cho_quyet", 0) + dem.get("qua_han", 0)), "da_quyet": int(dem.get("da_quyet", 0)),
            "bac": int(dem.get("bac", 0)), "qua_han": int(dem.get("qua_han", 0)), "da_kiem_chung": int(dem.get("da_kiem_chung", 0))}


# ------------------------------------------------------------------ đổi trạng thái
def _doi(qid: int, tu: tuple, cot: dict, boi: str, hanh_dong: str, ghi_chu: str, now: datetime) -> bool:
    """Chỉ đổi khi đang ở một trong các trạng thái `tu`; trả False nếu lượt khác đã đổi trước."""
    dam_bao_bang()
    with session_scope() as s:
        n = s.execute(update(TdQuyetDinh).where(TdQuyetDinh.id == int(qid), TdQuyetDinh.trang_thai.in_(tu))
                      .values(**cot, cap_nhat_luc=now)).rowcount
        if n:
            _nk(s, int(qid), now, boi, hanh_dong, ghi_chu)
    return bool(n)


def quyet(qid: int, boi: str, lua_chon: str, ghi_chu: str = "", now: datetime | None = None) -> bool:
    """Ghi quyết định: `lua_chon` là mã phương án (A, B, C) hoặc "sua" (người quyết sửa ý, `ghi_chu` là ý kiến). Đặt luôn hạn kiểm chứng.
    Mặc định chỉ ghi sổ, không tự thực thi gì khác. False nếu không còn ở trạng thái chờ."""
    now = now or utc_bay_gio()
    han = now + timedelta(hours=cau_hinh()["kiem_chung_gio"])
    return _doi(qid, CHO, {"trang_thai": "da_quyet", "lua_chon": lua_chon, "ghi_chu": ghi_chu or None, "quyet_boi": boi[:120], "quyet_luc": now, "han_kiem_chung": han},
                boi, "da_quyet", f"{lua_chon}: {ghi_chu}" if ghi_chu else lua_chon, now)


def bac(qid: int, boi: str, ly_do: str, now: datetime | None = None) -> bool:
    now = now or utc_bay_gio()
    return _doi(qid, CHO, {"trang_thai": "bac", "ghi_chu": ly_do or None, "quyet_boi": boi[:120], "quyet_luc": now}, boi, "bac", ly_do, now)


def het_han(qid: int, now: datetime | None = None) -> bool:
    """Quá hạn quyết đã báo cấp trên: đổi sang `qua_han` (vẫn quyết được)."""
    now = now or utc_bay_gio()
    return _doi(qid, ("cho_quyet",), {"trang_thai": "qua_han"}, "he_thong", "qua_han", "Quá hạn quyết, đã báo cấp trên", now)


def danh_dau(qid: int, cot: str, now: datetime | None = None) -> None:
    """Ghi giờ đã gửi tin đề xuất / nhắc / báo cấp trên / báo kiểm chứng (mỗi loại chỉ một lần)."""
    if cot not in ("da_gui_luc", "nhac_luc", "leo_thang_luc", "bao_kiem_chung_luc"):
        return
    dam_bao_bang()
    with session_scope() as s:
        s.execute(update(TdQuyetDinh).where(TdQuyetDinh.id == int(qid)).values(**{cot: now or utc_bay_gio()}))


def ghi_kiem_chung(qid: int, chi_so_sau: dict, ket_qua: str, nguon_noi_dung: str, now: datetime | None = None) -> bool:
    now = now or utc_bay_gio()
    return _doi(qid, ("da_quyet",), {"trang_thai": "da_kiem_chung", "chi_so_sau": json.dumps(sach(chi_so_sau), ensure_ascii=False), "ket_qua": ket_qua},
                "tro_ly", "kiem_chung", f"{ket_qua} ({nguon_noi_dung})", now)


# ------------------------------------------------------------------ khoá - giá trị phụ (lượt gọi AI, câu AI đã viết, buổi sáng đã chạy)
def doc_phu(khoa: str, mac_dinh: str | None = None) -> str | None:
    dam_bao_bang()
    with session_scope() as s:
        r = s.get(TdPhu, khoa)
        return r.gia_tri if r else mac_dinh


def ghi_phu(khoa: str, gia_tri: str) -> None:
    dam_bao_bang()
    with session_scope() as s:
        r = s.get(TdPhu, khoa)
        if r is None:
            s.add(TdPhu(khoa=khoa, gia_tri=gia_tri, cap_nhat_luc=utc_bay_gio()))
        else:
            r.gia_tri, r.cap_nhat_luc = gia_tri, utc_bay_gio()
