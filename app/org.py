"""Cơ cấu tổ chức: Bầy, Phòng kinh doanh và quy tắc gán phòng cho từng hợp đồng.

Nguồn dữ liệu:
- `dim_bay`, `dim_phong` trong database là NGUỒN CHÍNH, quản lý ở Quản trị → Cơ cấu tổ chức.
- `config/org.yml` chỉ dùng để khởi tạo lần đầu (seed) và làm quy tắc gán phòng dự phòng.
- `phong_bay_thang` ghi đè cơ cấu Bầy cho từng tháng (mỗi tháng phòng có thể đổi bầy).

Quy tắc gán phòng (đã kiểm chứng khớp báo cáo Tracking):
1. Hợp đồng bán qua ECOM (CN Bán = *_ECOM) -> ECOM DNG / ECOM QNM theo CN Quản lý.
2. Còn lại: tra acc nhân viên trong danh mục -> phòng kinh doanh.
3. Không có trong danh mục + Phòng (hệ thống) là "Phòng kỹ thuật"/"Phòng CUS"
   -> Phòng KT/CUS theo CN Bán (DNG_01/DNG_02/QNM).
4. Còn lại -> "Chưa gán phòng" (vẫn cộng vào tổng chi nhánh - BGD chốt 11/09/2026).
"""
from __future__ import annotations

import re
import time
import unicodedata
from datetime import date, datetime

from sqlalchemy import select, text

from app.config import LA_SERVERLESS, org_config
from app.db import engine
from app.ingest.normalize import norm_acc, norm_text
from app.models import Bay, Phong, PhongBayThang, StaffMap

_cache: dict = {"bay": None, "phong": None, "ten": None, "bay_thang": {}, "luc": 0.0}
LOAI_PHONG = ["IBB", "DIABAN", "KT", "CUS", "ECOM", "KHAC"]

# Khi chạy nhiều máy chủ cùng lúc (Vercel), sửa cơ cấu ở máy này thì máy khác không biết để
# xoá bộ nhớ đệm -> cho bộ nhớ đệm tự hết hạn sau ít giây, số liệu mới nhất tự được đọc lại.
HAN_CACHE_GIAY = 30 if LA_SERVERLESS else 600


# --------------------------------------------------------------------- cache
def xoa_cache_org(thang: str | None = None) -> None:
    from app.bo_nho import xoa
    xoa("so_lieu")                        # phòng của hợp đồng có thể đổi theo cơ cấu mới
    _cache["bay"] = _cache["phong"] = _cache["ten"] = None
    if thang:
        _cache["bay_thang"].pop(thang, None)
    else:
        _cache["bay_thang"] = {}


def _kiem_han_cache() -> None:
    bay_gio = time.monotonic()
    if bay_gio - _cache["luc"] > HAN_CACHE_GIAY:
        xoa_cache_org()
        _cache["luc"] = bay_gio


def _rows(sql: str, params: dict | None = None) -> list[dict]:
    try:
        with engine.connect() as con:
            res = con.execute(text(sql), params or {})
            return [dict(r._mapping) for r in res]
    except Exception:            # bảng chưa tạo ở lần chạy đầu
        return []


# --------------------------------------------------------------------- seed
def sync_org_to_db(session) -> tuple[int, int]:
    """Nạp cơ cấu mặc định từ org.yml - chỉ thêm cái còn thiếu, KHÔNG ghi đè chỉnh sửa của user."""
    cfg = org_config()
    nb = np = 0
    for b in cfg["bay"]:
        if session.get(Bay, b["code"]) is None:
            session.add(Bay(code=b["code"], ten=b["ten"], ten_tong=b.get("ten_tong"),
                            thu_tu=b["thu_tu"], active=True))
            nb += 1
    for p in cfg["phong"]:
        if session.get(Phong, p["code"]) is None:
            session.add(Phong(code=p["code"], ten=p["ten"], bay=p["bay"], loai=p["loai"],
                              chi_nhanh=p["chi_nhanh"], nhom_khac=p.get("nhom_khac"),
                              thu_tu=p["thu_tu"], active=True))
            np += 1
    session.flush()
    xoa_cache_org()
    return nb, np


# --------------------------------------------------------------------- đọc
def bay_info() -> dict[str, dict]:
    """{mã bầy: {code, ten, ten_tong, thu_tu}} - theo thứ tự hiển thị."""
    _kiem_han_cache()
    if _cache["bay"] is None:
        rows = _rows("SELECT code, ten, ten_tong, thu_tu FROM dim_bay WHERE active = TRUE "
                     "ORDER BY thu_tu, code")
        if not rows:
            rows = [{"code": b["code"], "ten": b["ten"], "ten_tong": b.get("ten_tong"),
                     "thu_tu": b["thu_tu"]} for b in org_config()["bay"]]
        _cache["bay"] = {r["code"]: r for r in rows}
    return _cache["bay"]


def ten_bay(code: str) -> str:
    return bay_info().get(code, {}).get("ten", code or "KHÁC")


def bay_options() -> list[dict]:
    return [{"value": b["code"], "label": b["ten"]}
            for b in sorted(bay_info().values(), key=lambda x: x["thu_tu"])]


def phong_all() -> list[dict]:
    _kiem_han_cache()
    if _cache["phong"] is None:
        rows = _rows("SELECT code, ten, bay, loai, chi_nhanh, nhom_khac, thu_tu, active "
                     "FROM dim_phong WHERE active = TRUE")
        if not rows:
            rows = [dict(p) for p in org_config()["phong"]]
        _cache["phong"] = rows
    return [dict(r) for r in _cache["phong"]]


def phong_by_name() -> dict[str, str]:
    """Tên phòng (như trong danh mục / báo cáo) -> mã phòng."""
    _kiem_han_cache()
    if _cache["ten"] is None:
        out = {}
        for p in phong_all():
            out[norm_text(p["ten"]).lower()] = p["code"]
            out[p["code"].lower()] = p["code"]
        _cache["ten"] = out
    return _cache["ten"]


def _bay_thang(thang: str | None) -> dict[str, tuple[str, int]]:
    if not thang:
        return {}
    _kiem_han_cache()
    if thang not in _cache["bay_thang"]:
        rows = _rows("SELECT phong_code, bay, thu_tu FROM phong_bay_thang WHERE thang = :t",
                     {"t": thang})
        _cache["bay_thang"][thang] = {r["phong_code"]: (r["bay"], r["thu_tu"] or 0) for r in rows}
    return _cache["bay_thang"][thang]


def co_cau_rieng(thang: str) -> bool:
    return bool(_bay_thang(thang))


def phong_order(thang: str | None = None) -> list[dict]:
    """Danh sách phòng theo thứ tự hiển thị, áp cơ cấu Bầy của tháng nếu tháng đó có cấu hình riêng."""
    ghi_de = _bay_thang(thang)
    bays = bay_info()
    ps = []
    for p in phong_all():
        if p["code"] in ghi_de:
            p["bay"], p["thu_tu"] = ghi_de[p["code"]]
        ps.append(p)
    return sorted(ps, key=lambda p: (bays.get(p["bay"], {"thu_tu": 99})["thu_tu"], p["thu_tu"],
                                     p["ten"]))


def loc_chi_nhanh(chi_phong: list[str] | None, chi_nhanh: str | None,
                  thang: str | None = None) -> list[str] | None:
    """Giao phạm vi được xem (theo quyền) với bộ lọc chi nhánh trên giao diện.

    `chi_phong=None` nghĩa là xem toàn bộ; `chi_nhanh` nhận "DNG" / "QNM" / None.
    """
    if not chi_nhanh or chi_nhanh == "all":
        return chi_phong
    codes = [p["code"] for p in phong_order(thang) if p.get("chi_nhanh") == chi_nhanh]
    if chi_phong is None:
        return codes
    return [c for c in chi_phong if c in set(codes)]


# --------------------------------------------------------------------- ghi
def _ma_moi(ten: str, dang_co: set[str], tien_to: str = "") -> str:
    s = unicodedata.normalize("NFD", norm_text(ten))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").upper()[:16] or "MOI"
    code = f"{tien_to}{s}"
    i = 2
    while code in dang_co:
        code = f"{tien_to}{s}_{i}"
        i += 1
    return code


def luu_bay(session, rows: list[dict]) -> int:
    """Thêm mới / cập nhật danh mục Bầy từ bảng trên giao diện."""
    dang_co = {b.code for b in session.execute(select(Bay)).scalars()}
    n = 0
    for r in rows:
        ten = norm_text(r.get("ten"))
        if not ten:
            continue
        code = norm_text(r.get("code")) or _ma_moi(ten, dang_co)
        dang_co.add(code)
        row = session.get(Bay, code) or Bay(code=code)
        row.ten = ten
        row.ten_tong = norm_text(r.get("ten_tong")) or f"TỔNG {ten.upper()}"
        row.thu_tu = int(r.get("thu_tu") or 0)
        row.active = str(r.get("active", "Có")).strip().lower() in ("có", "co", "true", "1", "x")
        session.add(row)
        n += 1
    session.flush()
    xoa_cache_org()
    return n


def luu_phong(session, rows: list[dict], ten2code_bay: dict[str, str]) -> int:
    dang_co = {p.code for p in session.execute(select(Phong)).scalars()}
    n = 0
    for r in rows:
        ten = norm_text(r.get("ten"))
        if not ten:
            continue
        code = norm_text(r.get("code")) or _ma_moi(ten, dang_co)
        dang_co.add(code)
        row = session.get(Phong, code) or Phong(code=code)
        row.ten = ten
        row.bay = ten2code_bay.get(norm_text(r.get("bay")), r.get("bay") or "KHAC")
        row.loai = (norm_text(r.get("loai")) or "IBB").upper()
        row.chi_nhanh = (norm_text(r.get("chi_nhanh")) or "DNG").upper()
        nk = norm_text(r.get("nhom_khac")).upper()
        row.nhom_khac = nk if nk in ("DNG", "QNM") else None
        row.thu_tu = int(r.get("thu_tu") or 0)
        row.active = str(r.get("active", "Có")).strip().lower() in ("có", "co", "true", "1", "x")
        session.add(row)
        n += 1
    session.flush()
    xoa_cache_org()
    return n


def xoa_bay(session, codes: list[str]) -> tuple[int, list[str]]:
    """Xoá bầy. Bầy còn phòng thì không xoá - phải chuyển phòng sang bầy khác trước."""
    bo_qua, n = [], 0
    for code in codes or []:
        con = session.execute(select(Phong).where(Phong.bay == code,
                                                  Phong.active.is_(True))).scalars().all()
        if con:
            bo_qua.append(f"{code}: còn {len(con)} phòng đang thuộc bầy này")
            continue
        row = session.get(Bay, code)
        if row is None:
            continue
        session.delete(row)
        n += 1
    session.flush()
    xoa_cache_org()
    return n, bo_qua


def xoa_phong(session, codes: list[str]) -> tuple[int, list[str]]:
    """Xoá phòng. Phòng đã có nhân sự hoặc đã có số liệu thì chỉ nên chuyển sang Ngừng dùng."""
    bo_qua, n = [], 0
    for code in codes or []:
        dung = session.execute(
            text("SELECT (SELECT COUNT(*) FROM staff_map WHERE phong_code = :c) "
                 "+ (SELECT COUNT(*) FROM fact_internet WHERE phong_code = :c) AS n"),
            {"c": code}).scalar() or 0
        if dung:
            bo_qua.append(f"{code}: đang gắn với {dung} bản ghi - hãy đổi sang “Ngừng dùng”")
            continue
        row = session.get(Phong, code)
        if row is None:
            continue
        session.delete(row)
        n += 1
    session.flush()
    xoa_cache_org()
    return n, bo_qua


def luu_co_cau_thang(session, thang: str, rows: list[dict]) -> int:
    """rows: [{'phong_code':..., 'bay':..., 'thu_tu':...}] - cơ cấu Bầy riêng của 1 tháng."""
    hien_co = {r.phong_code: r for r in session.execute(
        select(PhongBayThang).where(PhongBayThang.thang == thang)).scalars()}
    n = 0
    for r in rows:
        code, bay = r.get("phong_code"), r.get("bay")
        if not code or not bay:
            continue
        row = hien_co.get(code)
        if row is None:
            row = PhongBayThang(thang=thang, phong_code=code)
            session.add(row)
        row.bay = bay
        row.thu_tu = int(r.get("thu_tu") or 0)
        n += 1
    session.flush()
    xoa_cache_org(thang)
    return n


def xoa_co_cau_thang(session, thang: str) -> int:
    rows = session.execute(select(PhongBayThang).where(PhongBayThang.thang == thang)).scalars().all()
    for r in rows:
        session.delete(r)
    session.flush()
    xoa_cache_org(thang)
    return len(rows)


# --------------------------------------------------------------- gán phòng
def load_staff_map(session) -> dict[str, list[tuple]]:
    """acc_norm -> [(hiệu lực từ, hiệu lực đến, mã phòng)] - một acc có thể có nhiều dòng khi chuyển phòng."""
    rows = session.execute(select(StaffMap.acc_norm, StaffMap.phong_code, StaffMap.hieu_luc_tu,
                                  StaffMap.hieu_luc_den)).all()
    out: dict[str, list[tuple]] = {}
    for acc_norm, code, tu, den in rows:
        out.setdefault(acc_norm, []).append((tu, den, code))
    return out


def _thanh_ngay(v) -> date | None:
    if v is None or v == "" or (isinstance(v, float) and v != v):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def phong_theo_danh_muc(dong, ngay=None) -> str | None:
    """Phòng của acc tại ngày hợp đồng: dòng có hiệu lực bao trùm ngày đó; không dòng nào bao trùm
    (hoặc không có ngày) thì lấy dòng đang hiệu lực (không có ngày kết thúc), rồi dòng kết thúc muộn nhất."""
    if not dong:
        return None
    if isinstance(dong, str):
        return dong
    d = _thanh_ngay(ngay)
    if d is not None:
        for tu, den, code in dong:
            if (tu is None or tu <= d) and (den is None or d <= den):
                return code
    mo = [x for x in dong if x[1] is None]
    if mo:
        return max(mo, key=lambda x: x[0] or date.min)[2]
    return max(dong, key=lambda x: x[1])[2]


def ma_ngoai_chi_nhanh() -> str:
    """Mã gán cho HĐ do sale chi nhánh khác bán hộ (không tính vào số Đà Nẵng + Quảng Nam)."""
    return (org_config()["fallback"].get("ngoai_chi_nhanh") or {}).get("ma", "")


def assign_phong(acc, phong_he_thong, cn_ban, cn_quan_ly, staff_map: dict, ngay=None, doi_tuong_kh=None):
    """Trả về (mã phòng, có phải hợp đồng ECOM không). `ngay` = ngày online (hoặc ngày tạo) của hợp đồng,
    dùng để chọn đúng phòng khi nhân sự chuyển phòng (cột Hiệu lực từ / đến của danh mục).

    `doi_tuong_kh` đặc biệt (config/org.yml -> fallback.doi_tuong_kh_dac_biet, vd VIP 7 -> ANCS) được
    xét TRƯỚC TIÊN, vượt trên cả luật ECOM và danh mục nhân sự - nhóm khách này công ty quản lý
    riêng, không phụ thuộc ai đứng tên bán (chốt với chủ app 01/10/2026)."""
    fb = org_config()["fallback"]
    dac_biet = {k.upper(): v for k, v in (fb.get("doi_tuong_kh_dac_biet") or {}).items()}
    phong_dac_biet = dac_biet.get(norm_text(doi_tuong_kh).upper())
    cn_ban = norm_text(cn_ban).upper()
    cn_quan_ly = norm_text(cn_quan_ly).upper()
    if phong_dac_biet:
        theo_tinh = (fb.get("dac_biet_theo_cn_quan_ly") or {}).get(phong_dac_biet) or {}
        return next((v for k, v in theo_tinh.items() if cn_quan_ly.startswith(k)), phong_dac_biet), False

    if cn_ban.endswith(fb["ecom_cn_ban_suffix"]):
        rule = fb["ecom_theo_cn_quan_ly"]
        for k, v in rule.items():
            if k != "_default" and cn_quan_ly.startswith(k):
                return v, True
        return rule["_default"], True

    code = phong_theo_danh_muc(staff_map.get(norm_acc(acc)), ngay)
    if code:
        return code, False

    theo_phong = fb["theo_phong_he_thong"].get(norm_text(phong_he_thong))
    if theo_phong:
        code = theo_phong.get(cn_ban)
        if code:
            return code, False
    ngoai = fb.get("ngoai_chi_nhanh")
    if ngoai and cn_ban and not cn_ban.startswith(tuple(ngoai["tien_to_noi_bo"])):
        return ngoai["ma"], False
    return fb["mac_dinh"], False
