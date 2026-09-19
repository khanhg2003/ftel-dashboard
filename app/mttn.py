"""MTTN (Miền Trung - Tây Nguyên): phần số bán của một số phòng (hiện là IBB7) có khách ở các tỉnh MTTN.

Hợp đồng tính MTTN = hợp đồng của phòng áp dụng có CN Quản lý (tỉnh của khách) thuộc danh sách mã tỉnh
trong config/rules.yml (mục `mttn`). CN Bán của các phòng này luôn là DNG nên không dùng để phân biệt.
Mục tiêu MTTN là TỶ LỆ % số online MTTN / số online của phòng, nhập mỗi tháng ở Quản trị → Chỉ tiêu
(chỉ tiêu `mttn`).
"""
from __future__ import annotations

import math

import pandas as pd
from sqlalchemy import bindparam, text

from app.config import rules_config
from app.db import engine
from app.phan_tich import cung_ky_thang_truoc

CHI_TIEU = "mttn"


def cau_hinh() -> dict:
    c = rules_config().get("mttn") or {}
    return {"ten": c.get("ten", "MTTN"), "ten_day_du": c.get("ten_day_du", "Miền Trung - Tây Nguyên"),
            "phong": list(c.get("phong") or []),
            "cn_quan_ly": [str(x).strip().upper() for x in c.get("cn_quan_ly") or []]}


def ap_dung(code: str | None) -> bool:
    return bool(code) and code in cau_hinh()["phong"]


def la_mttn(cn_quan_ly: pd.Series) -> pd.Series:
    return cn_quan_ly.fillna("").astype(str).str.strip().str.upper().isin(cau_hinh()["cn_quan_ly"])


def _dem(bang: str, code: str, tu: str, den: str, them: str = "") -> tuple[int, int]:
    """(số MTTN, tổng) của phòng trong [tu, den] theo ngày online."""
    sql = text(f"""SELECT COUNT(*) AS tong,
                          SUM(CASE WHEN UPPER(TRIM(COALESCE(cn_quan_ly, ''))) IN :ds THEN 1 ELSE 0 END) AS mttn
                   FROM {bang} WHERE phong_code = :c AND ngay_online >= :tu AND ngay_online <= :den{them}"""
               ).bindparams(bindparam("ds", expanding=True))
    r = pd.read_sql_query(sql, engine, params={"ds": cau_hinh()["cn_quan_ly"] or [""], "c": code, "tu": tu,
                                         "den": den}).iloc[0]
    return int(r.mttn or 0), int(r.tong or 0)


def muc_tieu(thang: str, code: str) -> float | None:
    """Mục tiêu tỷ lệ MTTN (%) của phòng trong tháng, None nếu chưa nhập."""
    r = pd.read_sql_query(text("""SELECT gia_tri FROM target_monthly WHERE thang = :t AND doi_tuong = 'PHONG'
                            AND ma_doi_tuong = :c AND chi_tieu = :k"""), engine,
                    params={"t": thang, "c": code, "k": CHI_TIEU})
    return float(r.gia_tri.iloc[0]) if len(r) and pd.notna(r.gia_tri.iloc[0]) else None


def tong_hop(thang: str, ngay: int, code: str) -> dict:
    """Số MTTN của phòng luỹ kế 01 -> ngày, cùng kỳ tháng trước và mức cần thêm để đạt mục tiêu %."""
    tu, den = f"{thang}-01", f"{thang}-{ngay:02d}"
    mttn, tong = _dem("fact_internet", code, tu, den)
    ck_mttn, ck_tong = _dem("fact_internet", code, *cung_ky_thang_truoc(thang, ngay))
    cam, _ = _dem("fact_camera", code, tu, den)
    vvip, _ = _dem("fact_fptplay", code, tu, den, " AND la_vvip = TRUE")
    ty_le = round(mttn / tong * 100, 1) if tong else None
    mt = muc_tieu(thang, code)
    # số online MTTN phải bán thêm để tỷ lệ đạt mục tiêu - mỗi số MTTN thêm cũng làm tăng tổng của phòng:
    # (mttn + x) / (tong + x) >= p  <=>  x >= (p * tong - mttn) / (1 - p)
    p = None if mt is None else mt / 100
    can_them = (max(math.ceil((p * tong - mttn) / (1 - p) - 1e-9), 0)
                if p is not None and tong and p < 1 else None)
    return {"ten": cau_hinh()["ten"], "mttn": mttn, "tong": tong, "ty_le": ty_le,
            "ck_mttn": ck_mttn, "ck_ty_le": round(ck_mttn / ck_tong * 100, 1) if ck_tong else None,
            "tang_truong": round((mttn / ck_mttn - 1) * 100) if ck_mttn else None,
            "camera": cam, "vvip": vvip, "muc_tieu": mt, "can_them": can_them,
            "dat": None if mt is None or ty_le is None else ty_le >= mt}
