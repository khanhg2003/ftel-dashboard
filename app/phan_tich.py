"""Phân tích chất lượng bán: bán kèm, tốc độ online, số tồn theo thời gian chờ, cơ cấu gói.

Mọi tỷ lệ tính trên tập hợp đồng Internet ONLINE trong kỳ (01 -> ngày có số mới nhất),
khớp với cột "Số online" của Báo cáo Tổng:
- Kèm V.VIP  : hợp đồng đó có dòng V.VIP trong file Truyền hình (ghép theo số hợp đồng)
- Kèm Camera : hợp đồng đó có trong file Camera
- Đủ 3 DV    : có cả V.VIP lẫn Camera
- Trả trước  : số tháng trả trước > 0
- Online trong 1 ngày : ngày online - ngày tạo HĐ <= 1 (file chỉ có NGÀY tạo, không có giờ)
- Bán ngoại tỉnh : CN Quản lý không phải DNG_01/DNG_02/QNM (khách tỉnh khác, số tính cho tỉnh khác)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sqlalchemy import text

from app.db import engine
from app.metrics import dieu_kien_ton, month_range, prev_month
from app.org import bay_info, phong_order

CN_NOI_BO = ("DNG_01", "DNG_02", "QNM")
NHOM_GOI = ("Giga", "Sky", "Meta")
MOC_TON = [(0, 2, "0-2 ngày"), (3, 6, "3-6 ngày"), (7, 14, "7-14 ngày"), (15, 10 ** 6, "Trên 14 ngày")]
MOC_ONLINE = [(0, 0, "Trong ngày"), (1, 1, "1 ngày"), (2, 2, "2 ngày"), (3, 3, "3 ngày"),
              (4, 7, "4-7 ngày"), (8, 10 ** 6, "Trên 7 ngày")]
THU = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]

TY_LE = {  # tên cột -> (cột cờ, nhãn)
    "kem_vvip": ("co_vvip", "Kèm V.VIP"),
    "kem_camera": ("co_camera", "Kèm Camera"),
    "du_3": ("du_3", "Đủ 3 dịch vụ"),
    "tra_truoc": ("co_tra_truoc", "Trả trước"),
    "onl_1_ngay": ("onl_nhanh", "Online trong 1 ngày"),
    "ngoai_tinh": ("ngoai_tinh", "Bán ngoại tỉnh"),
}


def nhom_goi(goi) -> str:
    s = str(goi or "").strip().lower()
    for g in NHOM_GOI:
        if s.startswith(g.lower()):
            return g
    return "Khác"


# ------------------------------------------------------------------ dữ liệu gốc
def hop_dong_online(tu: str, den: str, chi_phong: list[str] | None = None) -> pd.DataFrame:
    """Một dòng = một hợp đồng Internet online trong [tu, den], kèm các cờ phân tích."""
    df = pd.read_sql(text("""
        SELECT f.hop_dong, f.phong_code, f.acc_nhan_vien, f.acc_norm, f.goi_dich_vu,
               f.ngay_tao_hd, f.ngay_online, f.so_thang_tra_truoc, f.cn_quan_ly,
               CASE WHEN EXISTS (SELECT 1 FROM fact_fptplay v
                                 WHERE v.hop_dong = f.hop_dong AND v.la_vvip = TRUE)
                    THEN 1 ELSE 0 END AS co_vvip,
               CASE WHEN EXISTS (SELECT 1 FROM fact_camera c WHERE c.hop_dong = f.hop_dong)
                    THEN 1 ELSE 0 END AS co_camera
        FROM fact_internet f
        WHERE f.ngay_online >= :tu AND f.ngay_online <= :den"""),
        engine, params={"tu": tu, "den": den})
    if chi_phong is not None:
        df = df[df.phong_code.isin(set(chi_phong))]
    df = df.copy()
    df["ngay_tao_hd"] = pd.to_datetime(df["ngay_tao_hd"])
    df["ngay_online"] = pd.to_datetime(df["ngay_online"])
    df["so_ngay_cho"] = (df.ngay_online - df.ngay_tao_hd).dt.days
    df["co_vvip"] = df.co_vvip.astype(int)
    df["co_camera"] = df.co_camera.astype(int)
    df["du_3"] = (df.co_vvip & df.co_camera).astype(int)
    df["co_tra_truoc"] = (pd.to_numeric(df.so_thang_tra_truoc, errors="coerce").fillna(0) > 0).astype(int)
    df["onl_nhanh"] = (df.so_ngay_cho.fillna(99) <= 1).astype(int)
    df["ngoai_tinh"] = (~df.cn_quan_ly.fillna("").isin(CN_NOI_BO)).astype(int)
    df["nhom_goi"] = [nhom_goi(g) for g in df.goi_dich_vu]
    return df


def ngay_du_lieu_moi_nhat() -> pd.Timestamp | None:
    v = pd.read_sql(text("SELECT MAX(ngay_tao_hd) d FROM fact_internet"), engine).iloc[0, 0]
    return pd.Timestamp(str(v)[:10]) if v else None


def hop_dong_ton(chi_phong: list[str] | None = None) -> pd.DataFrame:
    """Hợp đồng đã ký, chưa online, còn trong file mới nhất - kèm số ngày đã chờ."""
    dk, p = dieu_kien_ton("f.")
    df = pd.read_sql(text(f"""SELECT f.hop_dong, f.phong_code, f.acc_nhan_vien, f.acc_norm,
                                     f.goi_dich_vu, f.ngay_tao_hd, f.nguon_ban
                              FROM fact_internet f WHERE {dk}"""), engine, params=p)
    if chi_phong is not None:
        df = df[df.phong_code.isin(set(chi_phong))]
    df = df.copy()
    moc = ngay_du_lieu_moi_nhat()
    df["ngay_tao_hd"] = pd.to_datetime(df["ngay_tao_hd"])
    df["so_ngay_cho"] = ((moc - df.ngay_tao_hd).dt.days.clip(lower=0) if moc is not None
                         else 0)
    return df


# ------------------------------------------------------------------ tổng hợp
def _ty_le(so: float, mau: float) -> float | None:
    return round(so / mau * 100, 1) if mau else None


def chi_so_chung(df: pd.DataFrame) -> dict:
    n = len(df)
    out = {"online": n}
    for ten, (co, _) in TY_LE.items():
        out[ten] = _ty_le(df[co].sum(), n) if n else None
    out["so_ngay_cho_tv"] = float(df.so_ngay_cho.median()) if n else None
    return out


def ky_phan_tich(thang: str) -> tuple[str, str, int]:
    """(từ ngày, đến ngày, ngày) - từ đầu tháng đến ngày có số online mới nhất trong tháng."""
    from app.metrics import ngay_co_du_lieu
    start, _, days = month_range(thang)
    ngay = ngay_co_du_lieu(thang) or days
    return start.isoformat(), f"{thang}-{ngay:02d}", ngay


def cung_ky_thang_truoc(thang: str, ngay: int) -> tuple[str, str]:
    pm = prev_month(thang)
    _, _, days = month_range(pm)
    return f"{pm}-01", f"{pm}-{min(ngay, days):02d}"


def bang_theo_phong(df: pd.DataFrame, ton: pd.DataFrame, thang: str,
                    ten_tong: str = "TỔNG TOÀN CHI NHÁNH") -> pd.DataFrame:
    """Bầy -> Phòng -> dòng tổng bầy -> dòng tổng, cùng bố cục với Báo cáo Tổng."""
    codes = [p["code"] for p in phong_order(thang)]
    co_so = set(df.phong_code) | set(ton.phong_code)
    meta = {p["code"]: p for p in phong_order(thang)}

    def dong(sub: pd.DataFrame, sub_ton: pd.DataFrame) -> dict:
        r = chi_so_chung(sub)
        r["ton"] = len(sub_ton)
        r["ton_qua_7"] = int((sub_ton.so_ngay_cho >= 7).sum()) if len(sub_ton) else 0
        return r

    rows = []
    for bcode, binfo in sorted(bay_info().items(), key=lambda kv: kv[1]["thu_tu"]):
        ma = [c for c in codes if meta[c]["bay"] == bcode and c in co_so]
        if not ma:
            continue
        for c in ma:
            rows.append({"phong_code": c, "loai_dong": "data", "phong": meta[c]["ten"],
                         **dong(df[df.phong_code == c], ton[ton.phong_code == c])})
        rows.append({"phong_code": f"SUB_{bcode}", "loai_dong": "subtotal",
                     "phong": binfo.get("ten_tong", f"TỔNG {binfo['ten']}"),
                     **dong(df[df.phong_code.isin(ma)], ton[ton.phong_code.isin(ma)])})
    rows.append({"phong_code": "TOTAL", "loai_dong": "total", "phong": ten_tong,
                 **dong(df, ton)})
    return pd.DataFrame(rows).replace({np.nan: None})


def ton_theo_tuoi(ton: pd.DataFrame, thang: str) -> pd.DataFrame:
    """Số tồn của từng phòng chia theo thời gian đã chờ."""
    meta = {p["code"]: p for p in phong_order(thang)}
    rows = []
    for code, sub in ton.groupby("phong_code"):
        r = {"phong_code": code, "phong": meta.get(code, {}).get("ten", "Chưa gán phòng"),
             "thu_tu": meta.get(code, {}).get("thu_tu", 999), "tong": len(sub)}
        for i, (a, b, _) in enumerate(MOC_TON):
            r[f"m{i}"] = int(sub.so_ngay_cho.between(a, b).sum())
        r["tb_ngay"] = round(float(sub.so_ngay_cho.mean()), 1)
        rows.append(r)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out.sort_values(["m3", "m2", "tong"], ascending=False)
    tong = {"phong_code": "TOTAL", "phong": "TỔNG", "loai_dong": "total",
            "tong": int(out.tong.sum()), "tb_ngay": round(float(ton.so_ngay_cho.mean()), 1),
            **{f"m{i}": int(out[f"m{i}"].sum()) for i in range(len(MOC_TON))}}
    out["loai_dong"] = "data"
    return pd.concat([out, pd.DataFrame([tong])], ignore_index=True).drop(columns="thu_tu")


def kem_theo_goi(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    g = df.groupby("nhom_goi").agg(so_hd=("hop_dong", "size"), vvip=("co_vvip", "mean"),
                                   camera=("co_camera", "mean"), du_3=("du_3", "mean"))
    for c in ("vvip", "camera", "du_3"):
        g[c] = (g[c] * 100).round(1)
    thu_tu = {g_: i for i, g_ in enumerate(NHOM_GOI + ("Khác",))}
    return g.reset_index().sort_values("nhom_goi", key=lambda s: s.map(thu_tu))


def toc_do_online(df: pd.DataFrame) -> pd.DataFrame:
    n = len(df)
    rows = []
    for a, b, nhan in MOC_ONLINE:
        k = int(df.so_ngay_cho.between(a, b).sum()) if n else 0
        rows.append({"moc": nhan, "so_hd": k, "ty_le": _ty_le(k, n)})
    return pd.DataFrame(rows)


def co_cau_goi_theo_phong(df: pd.DataFrame, thang: str) -> pd.DataFrame:
    """Tỷ trọng từng nhóm gói trong số online của mỗi phòng (%)."""
    if df.empty:
        return pd.DataFrame()
    meta = {p["code"]: p for p in phong_order(thang)}
    pv = pd.crosstab(df.phong_code, df.nhom_goi)
    for g in NHOM_GOI + ("Khác",):
        if g not in pv.columns:
            pv[g] = 0
    pv = pv[list(NHOM_GOI + ("Khác",))]
    tong = pv.sum(axis=1)
    pct = (pv.div(tong, axis=0) * 100).round(1)
    pct["so_hd"] = tong
    pct["phong"] = [meta.get(c, {}).get("ten", "Chưa gán phòng") for c in pct.index]
    return pct[pct.so_hd >= 5].sort_values("Giga").reset_index()


def nhip_theo_thu(df: pd.DataFrame, tu: str, den: str) -> pd.DataFrame:
    """Online bình quân mỗi thứ trong tuần (chia cho số lần thứ đó xuất hiện trong kỳ)."""
    ngay = pd.date_range(tu, den)
    so_lan = pd.Series(ngay.dayofweek).value_counts()
    dem = df.ngay_online.dt.dayofweek.value_counts() if len(df) else pd.Series(dtype=int)
    rows = [{"thu": THU[i], "tb_online": round(float(dem.get(i, 0)) / so_lan[i], 1)
             if so_lan.get(i) else 0} for i in range(7)]
    return pd.DataFrame(rows)


def theo_nhan_vien(df: pd.DataFrame, ton: pd.DataFrame, thang: str) -> pd.DataFrame:
    meta = {p["code"]: p for p in phong_order(thang)}
    if df.empty and ton.empty:
        return pd.DataFrame()
    g = df.groupby("acc_norm").agg(
        acc=("acc_nhan_vien", "first"), phong_code=("phong_code", "first"),
        online=("hop_dong", "size"), vvip=("co_vvip", "sum"), camera=("co_camera", "sum"),
        du_3=("du_3", "sum"), tra_truoc=("co_tra_truoc", "sum"), nhanh=("onl_nhanh", "sum"))
    for c, moi in (("vvip", "kem_vvip"), ("camera", "kem_camera"), ("du_3", "du_3_tl"),
                   ("tra_truoc", "tra_truoc_tl"), ("nhanh", "onl_1_ngay")):
        g[moi] = (g[c] / g.online * 100).round(0)
    if len(ton):
        t = ton
        t_all = t.groupby("acc_norm").size()
        t7 = t[t.so_ngay_cho >= 7].groupby("acc_norm").size()
        g["ton"] = t_all.reindex(g.index).fillna(0).astype(int)
        g["ton_qua_7"] = t7.reindex(g.index).fillna(0).astype(int)
    else:
        g["ton"] = g["ton_qua_7"] = 0
    ten = pd.read_sql(text("SELECT acc_norm, ho_ten FROM dim_employee"), engine)
    g["ho_ten"] = ten.drop_duplicates("acc_norm").set_index("acc_norm").ho_ten.reindex(g.index)
    g["phong"] = [meta.get(c, {}).get("ten", "Chưa gán phòng") for c in g.phong_code]
    return g.reset_index().sort_values("online", ascending=False).replace({np.nan: None})
