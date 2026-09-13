"""Bảng tổng quan theo ngày - dựng lại đúng khối tổng hợp trong file Google Sheet.

Cột: PKD | Nhân sự | INTERNET (Mục tiêu, Số tồn, Số online, Tỷ lệ HTKH)
     | TĂNG TRƯỞNG (Số online cùng kỳ tháng trước, Tỷ lệ)
     | FPT PLAY (Combo, Tỷ lệ FPL/NET) | PTTB CNQL (Số online, Tỷ lệ)
     | COMBO VVIP (Số VVIP, Tỷ lệ VVIP/PTTB) | CAMERA (Mục tiêu, Thực hiện, Tỷ lệ HTKH)
     | KẾT QUẢ THỰC HIỆN NGÀY (Mục tiêu, Bán mới, Online, VVIP, Kết luận)

PTTB CNQL = hợp đồng có CN Quản lý thuộc chi nhánh (DNG_01/DNG_02/QNM),
đã đối chiếu khớp 20/20 phòng với file hiện tại.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sqlalchemy import text

from app.db import engine
from app.metrics import daily_counts, month_range, ngay_co_du_lieu, prev_month
from app.org import bay_info, phong_order

CN_NOI_BO = ("DNG_01", "DNG_02", "QNM")


def _sum_den_ngay(thang: str, metric: str, ngay: int) -> pd.Series:
    d = daily_counts(thang, metric)
    return d.loc[:, [c for c in d.columns if c <= ngay]].sum(axis=1)


def _ngay_don(thang: str, metric: str, ngay: int) -> pd.Series:
    d = daily_counts(thang, metric)
    return d[ngay] if ngay in d.columns else pd.Series(0, index=d.index)


def _sql_series(sql: str, params: dict) -> pd.Series:
    df = pd.read_sql(text(sql), engine, params=params)
    if df.empty:
        return pd.Series(dtype=int)
    return df.set_index("phong_code")["n"]


def _nhan_su() -> pd.Series:
    sql = """SELECT phong_code, COUNT(*) n FROM staff_map
             WHERE COALESCE(ghi_chu, '') NOT LIKE '%Nghỉ%' GROUP BY phong_code"""
    return _sql_series(sql, {})


def _pttb_cnql(thang: str, ngay: int) -> pd.Series:
    start, _, _ = month_range(thang)
    den = f"{thang}-{ngay:02d}"
    sql = f"""SELECT phong_code, COUNT(*) n FROM fact_internet
              WHERE ngay_online >= :start AND ngay_online <= :den
                AND cn_quan_ly IN ({','.join(repr(c) for c in CN_NOI_BO)})
              GROUP BY phong_code"""
    return _sql_series(sql, {"start": start.isoformat(), "den": den})


def _so_ton() -> pd.Series:
    return _sql_series("""SELECT phong_code, COUNT(*) n FROM fact_internet
                          WHERE ngay_online IS NULL GROUP BY phong_code""", {})


def _targets(thang: str) -> pd.DataFrame:
    df = pd.read_sql(text("""SELECT ma_doi_tuong, chi_tieu, gia_tri FROM target_monthly
                             WHERE thang = :t AND doi_tuong = 'PHONG'"""),
                     engine, params={"t": thang})
    if df.empty:
        return pd.DataFrame()
    return df.pivot_table(index="ma_doi_tuong", columns="chi_tieu", values="gia_tri")


def bang_tong_quan(thang: str, ngay: int | None = None,
                   chi_phong: list[str] | None = None) -> tuple[pd.DataFrame, int]:
    """Trả về (bảng đã có dòng tổng bầy + tổng chi nhánh, ngày dữ liệu được dùng)."""
    ngay = ngay or ngay_co_du_lieu(thang) or month_range(thang)[2]
    codes = [p["code"] for p in phong_order(thang)]
    if chi_phong is not None:
        codes = [c for c in codes if c in set(chi_phong)]

    def s(series: pd.Series) -> pd.Series:
        return series.reindex(codes).fillna(0).astype(int)

    online = s(_sum_den_ngay(thang, "online", ngay))
    vvip = s(_sum_den_ngay(thang, "vvip", ngay))
    fpl = s(_sum_den_ngay(thang, "fptplay", ngay))
    camera = s(_sum_den_ngay(thang, "camera", ngay))
    ck = s(_sum_den_ngay(prev_month(thang), "online", ngay))
    cnql = s(_pttb_cnql(thang, ngay))
    ton = s(_so_ton())
    nhan_su = s(_nhan_su())
    ngay_ban_moi = s(_ngay_don(thang, "ban_moi", ngay))
    ngay_online = s(_ngay_don(thang, "online", ngay))
    ngay_vvip_tao = _vvip_tao_trong_ngay(thang, ngay).reindex(codes).fillna(0).astype(int)

    tgt = _targets(thang)

    def target(col: str) -> pd.Series:
        if tgt.empty or col not in tgt.columns:
            return pd.Series(0, index=codes)
        return tgt[col].reindex(codes).fillna(0)

    meta = {p["code"]: p for p in phong_order(thang)}
    df = pd.DataFrame({
        "phong": [meta[c]["ten"] for c in codes],
        "bay": [meta[c]["bay"] for c in codes],
        "nhan_su": nhan_su,
        "mt_internet": target("internet"),
        "so_ton": ton,
        "online": online,
        "ck_online": ck,
        "fpl_combo": fpl,
        "cnql": cnql,
        "vvip": vvip,
        "mt_camera": target("camera"),
        "camera": camera,
        "mt_ngay": target("ngay"),
        "ngay_ban_moi": ngay_ban_moi,
        "ngay_online": ngay_online,
        "ngay_vvip": ngay_vvip_tao,
    }, index=codes)

    rows = []
    bays = bay_info()
    for bcode, binfo in sorted(bays.items(), key=lambda kv: kv[1]["thu_tu"]):
        sub = df[df.bay == bcode]
        if sub.empty:
            continue
        for code, r in sub.iterrows():
            rows.append({"phong_code": code, "loai_dong": "data", **r.drop("bay").to_dict()})
        tong = sub.drop(columns=["phong", "bay"]).sum()
        rows.append({"phong_code": f"SUB_{bcode}", "loai_dong": "subtotal",
                     "phong": binfo.get("ten_tong", f"TỔNG {binfo['ten']}"), **tong.to_dict()})
    tong_all = df.drop(columns=["phong", "bay"]).sum()
    rows.append({"phong_code": "TOTAL", "loai_dong": "total",
                 "phong": "TỔNG TOÀN CHI NHÁNH", **tong_all.to_dict()})

    out = pd.DataFrame(rows)
    out = _them_ty_le(out)
    return out, ngay


def _vvip_tao_trong_ngay(thang: str, ngay: int) -> pd.Series:
    """Cột VVIP trong khối 'Kết quả thực hiện ngày' đếm theo NGÀY TẠO hợp đồng."""
    d = f"{thang}-{ngay:02d}"
    return _sql_series("""SELECT phong_code, COUNT(*) n FROM fact_fptplay
                          WHERE ngay_tao_hd = :d AND la_vvip = TRUE GROUP BY phong_code""",
                       {"d": d})


def _ty_le(tu: pd.Series, mau: pd.Series) -> pd.Series:
    return (tu / mau.replace(0, np.nan) * 100).round(0)


def _them_ty_le(out: pd.DataFrame) -> pd.DataFrame:
    out["htkh_internet"] = _ty_le(out.online, out.mt_internet)
    out["tang_truong"] = ((out.online - out.ck_online) /
                          out.ck_online.replace(0, np.nan) * 100).round(0)
    out["fpl_ty_le"] = _ty_le(out.fpl_combo, out.online)
    out["cnql_ty_le"] = _ty_le(out.cnql, out.online)
    out["vvip_ty_le"] = _ty_le(out.vvip, out.online)
    out["htkh_camera"] = _ty_le(out.camera, out.mt_camera)
    out["ket_luan"] = np.where(out.ngay_online >= out.mt_ngay.replace(0, np.nan).fillna(10 ** 9),
                               "Đạt", "Không đạt")
    out.loc[out.mt_ngay == 0, "ket_luan"] = "—"
    return out.replace({np.nan: None})
