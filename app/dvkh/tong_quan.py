"""KPI tổng quan khối DVKH theo ngày xem: bốn nhóm (rời mạng, công nợ, SR bị động, SR chủ động) cho DNG1, DNG2 và cả Đà Nẵng.

- "Luỹ kế" = từ đầu tháng của ngày xem đến ngày xem; "Trong ngày" = đúng ngày xem.
- Cùng kỳ tháng trước = cùng khoảng ngày của tháng liền trước, chỉ có khi file đã nạp tháng đó (không có thì để trống, không đoán).
- Rời mạng và công nợ là số chốt sẵn trong file: lấy ngày chốt / ngày thu gần nhất không sau ngày xem.
"""
from __future__ import annotations

import calendar
from datetime import date

import pandas as pd

from app.bo_nho import nho
from app.dvkh import cheo, so_lieu as sl, xu_huong as xh

PHONG_XEM = ("DNG1", "DNG2", "DNG")                      # DNG = tổng Đà Nẵng
TEN_ROI_MANG = {"DNG-01": "DNG1", "DNG-02": "DNG2", "05.Da Nang": "DNG"}
TEN_CONG_NO = {"DNG1": "DNG1", "DNG2": "DNG2", "DNG": "To tal DNG CN 30"}


def _cua_so(ngay: date, che_do: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    d = pd.Timestamp(ngay)
    return (d, d) if che_do == "ngay" else (d.replace(day=1), d)


def _lui_thang(tu: pd.Timestamp, den: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    return tu - pd.DateOffset(months=1), den - pd.DateOffset(months=1)


def _sr(ngay: date, che_do: str, truoc: bool = False) -> dict[str, dict]:
    bd, cd = sl.sr_bi_dong(), sl.sr_chu_dong()
    tu, den = _cua_so(ngay, che_do)
    if truoc:
        tu, den = _lui_thang(tu, den)
    out = {}
    for p in PHONG_XEM:
        ma = None if p == "DNG" else p
        b = sl.loc(bd, ma, tu, den, "ngay_yc")
        c = sl.loc(cd, ma, tu, den, "ngay_do")
        out[p] = {"bd": sl.kpi_bd(b) if len(b) else None, "cd": sl.kpi_cd(c) if len(c) else None}
    return out


def _roi_mang(ngay: date, truoc: bool = False) -> dict[str, dict]:
    d = pd.Timestamp(ngay) - (pd.DateOffset(months=1) if truoc else pd.Timedelta(0))
    rm = sl.roi_mang_moi_nhat(d.date())
    if rm.empty or (truoc and (pd.Timestamp(ngay) - rm["ngay_chot"].max()).days < 20):
        return {}
    rm = rm[rm["cap"] == "phong"]
    return {TEN_ROI_MANG[r["ten"]]: r.to_dict() for _, r in rm.iterrows() if r["ten"] in TEN_ROI_MANG}


def _cong_no(ngay: date) -> tuple[dict, dict, str | None, int | None]:
    """({phòng: {dt, bill}}, kỳ trước cùng ngày lịch, kỳ nợ, ngày trong tháng). Kỳ nợ = tháng của ngày xem nếu đã có số."""
    cn = sl.cong_no_ngay()
    if cn.empty:
        return {}, {}, None, None
    cn = cn[cn["cap"] == "phong"]
    ky = sorted(cn["ky_no"].unique())
    d0 = pd.Timestamp(ngay)
    khoang = cn.groupby("ky_no")["ngay"].agg(["min", "max"])       # kỳ nợ T9 được thu trong tháng 10: chọn kỳ có khoảng thu chứa ngày xem
    trong = [k for k in ky if khoang.loc[k, "min"] <= d0 <= khoang.loc[k, "max"] + pd.Timedelta(days=1)]
    da_bat_dau = [k for k in ky if khoang.loc[k, "min"] <= d0]
    hien = trong[-1] if trong else (da_bat_dau[-1] if da_bat_dau else ky[0])
    d = cn[(cn["ky_no"] == hien) & (cn["ngay"] <= d0)]
    if d.empty:
        d = cn[cn["ky_no"] == hien]
    so_ngay = int(d["so_ngay"].max())
    kt = ky[ky.index(hien) - 1] if ky.index(hien) > 0 else None

    def lay(k, n):
        out = {}
        for p, ten in TEN_CONG_NO.items():
            x = cn[(cn["ky_no"] == k) & (cn["ten"] == ten) & (cn["so_ngay"] <= n)].sort_values("so_ngay")
            if len(x):
                r = x.iloc[-1]
                out[p] = {"dt": None if pd.isna(r["ty_le_dt"]) else r["ty_le_dt"] * 100,
                          "bill": None if pd.isna(r["ty_le_bill"]) else r["ty_le_bill"] * 100, "ngay": r["ngay"]}
        return out
    return lay(hien, so_ngay), (lay(kt, so_ngay) if kt else {}), hien, so_ngay


@nho("dvkh", sl.TTL)
def tinh(ngay: date, che_do: str = "luy_ke") -> dict:
    cong_no, cong_no_truoc, ky_no, so_ngay = _cong_no(ngay)
    return {"sr": _sr(ngay, che_do), "sr_truoc": _sr(ngay, che_do, truoc=True), "roi_mang": _roi_mang(ngay),
            "roi_mang_truoc": _roi_mang(ngay, truoc=True), "cong_no": cong_no, "cong_no_truoc": cong_no_truoc,
            "ky_no": ky_no, "so_ngay_thu": so_ngay}


@nho("dvkh", sl.TTL)
def suc_khoe(ngay: date) -> dict:
    """Số liệu cho dải thẻ "sức khoẻ" ở đầu trang tổng quan: vào - ra - tồn theo ngày, hướng đi, dự báo tháng, dự báo thu nợ, rời mạng, thanh lý chờ.

    Chỉ lấy SR của tháng chứa ngày xem tới hết ngày xem. Mọi dự báo kèm số ngày dữ liệu để người đọc biết độ tin cậy."""
    d0 = pd.Timestamp(ngay)
    dau = d0.replace(day=1)
    bd = sl.loc(sl.sr_bi_dong(), None, dau, d0, "ngay_yc")
    cd = sl.loc(sl.sr_chu_dong(), None, dau, d0, "ngay_do")
    l_bd, l_cd = xh.luong_theo_ngay(bd, "ngay_yc"), xh.luong_theo_ngay(cd, "ngay_do")
    so_ngay_thang = calendar.monthrange(d0.year, d0.month)[1]
    cn = sl.cong_no_ngay()
    rm = sl.roi_mang()
    rm = rm[(rm["cap"] == "phong") & (rm["ten"] == "05.Da Nang")].sort_values("ngay_chot") if not rm.empty else rm
    tl = cheo.thanh_ly_ton(sl.sr_bi_dong(), sl.sr_chu_dong())
    return {"bd": bd, "cd": cd, "luong_bd": l_bd, "luong_cd": l_cd, "kpi_bd": sl.kpi_bd(bd) if len(bd) else None, "kpi_cd": sl.kpi_cd(cd) if len(cd) else None,
            "huong_vao_bd": xh.huong(l_bd["vao"]), "huong_ton_bd": xh.huong(l_bd["ton_cuoi_ngay"]),
            "huong_vao_cd": xh.huong(l_cd["vao"]), "huong_ton_cd": xh.huong(l_cd["ton_cuoi_ngay"]),
            "du_bao_bd": xh.du_bao_thang(l_bd["vao"], so_ngay_thang), "du_bao_cd": xh.du_bao_thang(l_cd["vao"], so_ngay_thang),
            "du_bao_no": xh.du_bao_cong_no(cn, "To tal DNG CN 30"), "du_bao_no_dt": xh.du_bao_cong_no(cn, "To tal DNG CN 30", "ty_le_dt"),
            "roi_mang_lich_su": rm, "so_thanh_ly_cho": len(tl), "thanh_ly_cu_nhat": tl["thoi_gian"].min() if len(tl) else None,
            "theo_thu_bd": xh.theo_thu(l_bd)}
