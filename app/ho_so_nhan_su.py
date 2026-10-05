"""Hồ sơ chi tiết MỘT nhân sự (ngăn chi tiết ở Báo cáo phòng): mọi thứ app phân tích được từ số bán của người đó.

Gồm: vị trí trong phòng, xu hướng 3 tháng, bán theo tỉnh / phường xã, cơ cấu gói, chất lượng bán so với phòng và
cùng kỳ tháng trước, tốc độ triển khai và hợp đồng chưa online, chuyển hoá bán mới -> online, nhịp theo thứ trong
tuần, NSLĐ gần đây. Không có tên khách hàng (xem AGENTS.md mục 5).

Kỳ luôn là luỹ kế từ ngày 01 đến ngày chọn, so với cùng số ngày tháng trước (cùng quy ước Báo cáo phòng).
"""
from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import text

from app import fox_insight as fi
from app import phan_tich as pt
from app.db import engine
from app.metrics import month_range, prev_month

THU = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]
TOI_DA_XA = 8


def _q(sql: str, **params) -> pd.DataFrame:
    return pd.read_sql_query(text(sql), engine, params=params)


def _ty_le(df: pd.DataFrame, cot: str) -> float | None:
    return round(float(df[cot].mean()) * 100) if len(df) else None


def _cua(df: pd.DataFrame, acc_norm: str) -> pd.DataFrame:
    return df[df.acc_norm == acc_norm]


def chat_luong(nguoi: pd.DataFrame, phong: pd.DataFrame, nguoi_ck: pd.DataFrame) -> list[dict]:
    """Mỗi tỷ lệ chất lượng: của người, của phòng, chênh (điểm), của chính người đó cùng kỳ tháng trước."""
    out = []
    for _, (co, ten) in pt.TY_LE.items():
        a, b, c = _ty_le(nguoi, co), _ty_le(phong, co), _ty_le(nguoi_ck, co)
        out.append({"chi_so": ten, "nguoi": a, "phong": b, "chenh": None if a is None or b is None else a - b,
                    "cung_ky": c})
    return out


def co_cau_goi(nguoi: pd.DataFrame, phong: pd.DataFrame) -> list[dict]:
    """Từng nhóm gói: số online, tỷ trọng của người so với tỷ trọng của phòng, tỷ lệ kèm V.VIP / Camera."""
    out = []
    for g, x in nguoi.groupby("nhom_goi"):
        out.append({"goi": g, "so": len(x), "ty_trong": round(len(x) / len(nguoi) * 100),
                    "ty_trong_phong": round((phong.nhom_goi == g).mean() * 100) if len(phong) else None,
                    "vvip": round(float(x.co_vvip.mean()) * 100), "camera": round(float(x.co_camera.mean()) * 100)})
    return sorted(out, key=lambda r: -r["so"])


def theo_thu(nguoi: pd.DataFrame, thang: str, ngay: int) -> list[dict]:
    """Online theo thứ trong tuần: tổng và bình quân mỗi ngày thuộc thứ đó trong kỳ."""
    so_ngay = pd.Series([date(int(thang[:4]), int(thang[5:7]), n).weekday() for n in range(1, ngay + 1)]).value_counts()
    dem = nguoi.ngay_online.dt.dayofweek.value_counts()
    return [{"thu": THU[i], "so": int(dem.get(i, 0)), "so_ngay": int(so_ngay.get(i, 0)),
             "tb": round(float(dem.get(i, 0)) / int(so_ngay.get(i, 1)), 1) if int(so_ngay.get(i, 0)) else 0.0}
            for i in range(7)]


def chuoi_khong_so(nguoi: pd.DataFrame, ngay: int) -> tuple[int, int]:
    """(số ngày có số, chuỗi ngày liền không có số dài nhất) trong kỳ."""
    co = set(nguoi.ngay_online.dt.day)
    dai, hien = 0, 0
    for n in range(1, ngay + 1):
        hien = 0 if n in co else hien + 1
        dai = max(dai, hien)
    return len(co), dai


def xu_huong(acc_norm: str, thang: str, ngay: int) -> list[dict]:
    """Online và bán mới 3 tháng gần nhất (hai tháng trước đủ tháng, tháng này tới ngày chọn kèm cùng kỳ)."""
    m1 = prev_month(thang)
    m2 = prev_month(m1)
    tu = f"{m2}-01"
    den = f"{thang}-{ngay:02d}"
    ban = _q("SELECT ngay_tao_hd AS d FROM fact_internet WHERE acc_norm = :a AND ngay_tao_hd >= :tu AND ngay_tao_hd <= :den",
             a=acc_norm, tu=tu, den=den)
    onl = _q("SELECT ngay_online AS d FROM fact_internet WHERE acc_norm = :a AND ngay_online >= :tu AND ngay_online <= :den",
             a=acc_norm, tu=tu, den=den)

    def dem(df: pd.DataFrame, m: str, toi_ngay: int | None = None) -> int:
        d = pd.to_datetime(df.d)
        x = d[d.dt.strftime("%Y-%m") == m]
        return int((x.dt.day <= toi_ngay).sum()) if toi_ngay else int(len(x))
    ngay_ck = min(ngay, month_range(m1)[2])
    return [{"ten": f"T{int(m2[5:7])}", "online": dem(onl, m2), "ban_moi": dem(ban, m2)},
            {"ten": f"T{int(m1[5:7])}", "online": dem(onl, m1), "ban_moi": dem(ban, m1),
             "online_ck": dem(onl, m1, ngay_ck), "ban_moi_ck": dem(ban, m1, ngay_ck)},
            {"ten": f"T{int(thang[5:7])} (đến {ngay:02d})", "online": dem(onl, thang), "ban_moi": dem(ban, thang),
             "online_ck": dem(onl, m1, ngay_ck), "ban_moi_ck": dem(ban, m1, ngay_ck)}]


def nsld_gan_day(acc_norm: str) -> list[dict]:
    df = _q("""SELECT thang, diem_tong, ket_luan FROM hr_monthly
               WHERE LOWER(TRIM(acc)) = :a ORDER BY thang DESC""", a=acc_norm).head(3)
    return [{"thang": r.thang, "diem": None if pd.isna(r.diem_tong) else float(r.diem_tong),
             "ket_luan": r.ket_luan or ""} for r in df.itertuples()][::-1]


def ho_so(thang: str, ngay: int, code: str, acc_norm: str) -> dict:
    tu, den = f"{thang}-01", f"{thang}-{ngay:02d}"
    tu_ck, den_ck = pt.cung_ky_thang_truoc(thang, ngay)
    phong_nay, phong_ck = pt.hop_dong_online(tu, den, [code]), pt.hop_dong_online(tu_ck, den_ck, [code])
    nguoi, nguoi_ck = _cua(phong_nay, acc_norm), _cua(phong_ck, acc_norm)
    ton = pt.hop_dong_ton([code])
    ton = ton[ton.acc_norm == acc_norm]

    # bán theo tỉnh / phường xã (cùng nguồn với trang Phân tích bán hàng -> Bán theo tỉnh)
    ct = pt.chi_tiet_nv_tinh(acc_norm, tu, den, [code])
    tinh, xa = ct["tinh"], ct["xa"].head(TOI_DA_XA)
    ngoai_phong = round(float(phong_nay.ngoai_tinh.mean()) * 100) if len(phong_nay) else None

    # chuyển hoá bán mới -> online và nguồn bán
    nguon = _q("""SELECT nguon_ban, COUNT(*) AS n FROM fact_internet
                  WHERE acc_norm = :a AND ngay_tao_hd >= :tu AND ngay_tao_hd <= :den GROUP BY nguon_ban""",
               a=acc_norm, tu=tu, den=den)
    nguon = nguon.assign(nguon_ban=nguon.nguon_ban.fillna("Không rõ")).sort_values("n", ascending=False)

    ngay_co_so, dai_nhat = chuoi_khong_so(nguoi, ngay)
    hs = fi._hieu_suat(thang, [code], ngay)
    vi_tri = hs[hs.acc_norm == acc_norm]
    vi_tri = vi_tri.iloc[0].to_dict() if len(vi_tri) else {}
    online = len(nguoi)
    tuoi = pd.cut(ton.so_ngay_cho, bins=[-1, 2, 6, 14, 30, 10 ** 6],
                  labels=[m[2] for m in pt.MOC_TON]).value_counts().reindex([m[2] for m in pt.MOC_TON]).fillna(0).astype(int) \
        if len(ton) else pd.Series(0, index=[m[2] for m in pt.MOC_TON])
    return {
        "online": online, "online_phong": len(phong_nay),
        "dong_gop": round(online / len(phong_nay) * 100) if len(phong_nay) else None,
        "trung_vi_phong": float(hs[hs.dang_lam & hs.kd].online.median()) if len(hs) else None,
        "trung_vi_tham_nien": vi_tri.get("trung_vi_tham_nien"), "so_voi_tham_nien": vi_tri.get("so_voi_tham_nien"),
        "tinh": tinh, "xa": xa, "ban": ct["ban"], "ban_da_onl": ct["ban_da_onl"], "onl_ban_truoc": ct["onl_ban_truoc"],
        "ngoai_onl": ct["ngoai_onl"], "ngoai_phong": ngoai_phong,
        "goi": co_cau_goi(nguoi, phong_nay), "chat_luong": chat_luong(nguoi, phong_nay, nguoi_ck),
        "cho_trung_vi": float(nguoi.so_ngay_cho.median()) if online else None,
        "cho_trung_vi_phong": float(phong_nay.so_ngay_cho.median()) if len(phong_nay) else None,
        "ton": len(ton), "ton_tuoi": tuoi, "nguon_ban": nguon,
        "thu": theo_thu(nguoi, thang, ngay), "ngay_co_so": ngay_co_so, "chuoi_dai_nhat": dai_nhat,
        "tb_moi_ngay_co_so": round(online / ngay_co_so, 1) if ngay_co_so else None,
        "xu_huong": xu_huong(acc_norm, thang, ngay), "nsld": nsld_gan_day(acc_norm),
    }
