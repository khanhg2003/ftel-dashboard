"""Dự báo số online cuối tháng theo phòng - tính bằng công thức, AI chỉ diễn giải.

Dự báo = luỹ kế + (luỹ kế / số ngày đã qua) × số ngày còn lại × hệ số cuối tháng.
Hệ số cuối tháng lấy từ tháng trước của cả phạm vi đang xem: tốc độ bình quân/ngày của phần còn lại
tháng trước chia tốc độ của cùng số ngày đầu tháng (cuối tháng thường bán nhanh hơn). Giới hạn
0,7 - 1,5 để một tháng bất thường không kéo lệch dự báo.
"""
from __future__ import annotations

import math

import pandas as pd

from app.metrics import daily_counts, month_range, prev_month
from app.org import phong_order
from app.overview import _targets, phong_khong_cong_tong

HE_SO_MIN, HE_SO_MAX = 0.7, 1.5
AN_TOAN, TANG_TOC, RUI_RO, CHUA_MT = "An toàn", "Cần tăng tốc", "Rủi ro", "Chưa có mục tiêu"


def he_so_cuoi_thang(thang: str, ngay: int, chi_phong: list[str] | None = None) -> float:
    pm = prev_month(thang)
    days = month_range(pm)[2]
    k = min(ngay, days)
    if k >= days:
        return 1.0
    d = daily_counts(pm, "online")
    if chi_phong is not None:
        d = d.loc[[c for c in d.index if c in set(chi_phong)]]
    dau, cuoi = d.loc[:, :k].to_numpy().sum() / k, d.loc[:, k + 1:].to_numpy().sum() / (days - k)
    if not dau or not cuoi:
        return 1.0
    return round(float(min(HE_SO_MAX, max(HE_SO_MIN, cuoi / dau))), 2)


def danh_gia(pct: float | None) -> str:
    if pct is None:
        return CHUA_MT
    return AN_TOAN if pct >= 100 else TANG_TOC if pct >= 90 else RUI_RO


def du_bao_thang(thang: str, ngay: int, chi_phong: list[str] | None = None) -> pd.DataFrame:
    """Dòng = phòng (+ dòng TỔNG): mt, luy_ke, du_bao, pct_mt, can_moi_ngay, danh_gia."""
    days = month_range(thang)[2]
    ngay = max(1, min(ngay, days))
    con_lai = days - ngay
    codes = [p["code"] for p in phong_order(thang)]
    if chi_phong is not None:
        codes = [c for c in codes if c in set(chi_phong)]
    ten = {p["code"]: p["ten"] for p in phong_order(thang)}
    luy_ke = daily_counts(thang, "online").loc[:, :ngay].sum(axis=1).reindex(codes).fillna(0)
    tgt = _targets(thang)
    mt = (tgt["internet"] if "internet" in tgt.columns else pd.Series(dtype=float)).reindex(codes).fillna(0)
    he_so = he_so_cuoi_thang(thang, ngay, chi_phong)

    def dong(code, ten_dong, lk, muc_tieu):
        du_bao = round(lk + lk / ngay * con_lai * he_so)
        pct = round(du_bao / muc_tieu * 100) if muc_tieu else None
        can = math.ceil((muc_tieu - lk) / con_lai) if muc_tieu > lk and con_lai else 0
        return {"phong_code": code, "phong": ten_dong, "mt": int(muc_tieu), "luy_ke": int(lk),
                "du_bao": int(du_bao), "pct_mt": pct, "can_moi_ngay": can if muc_tieu else None,
                "tb_ngay": round(lk / ngay, 1), "danh_gia": danh_gia(pct)}

    rows = [dong(c, ten[c], float(luy_ke[c]), float(mt[c])) for c in codes]
    bo = phong_khong_cong_tong()
    rows.append(dong("TOTAL", "TỔNG", float(luy_ke.sum()), float(mt[[c for c in codes if c not in bo]].sum())))
    out = pd.DataFrame(rows).astype(object).where(lambda d: d.notna(), None)
    out.attrs.update(he_so=he_so, ngay=ngay, so_ngay=days)
    return out
