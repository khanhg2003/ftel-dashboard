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

from app.bo_nho import nho
from sqlalchemy import text

from app.db import engine
from app.metrics import dieu_kien_ton, month_range, prev_month
from app.org import bay_info, phong_order

CN_NOI_BO = ("DNG_01", "DNG_02", "QNM")
NHOM_GOI = ("Giga", "Sky", "Meta")
MOC_TON = [(0, 2, "0-2 ngày"), (3, 6, "3-6 ngày"), (7, 14, "7-14 ngày"), (15, 30, "15-30 ngày"),
           (31, 10 ** 6, "Trên 30 ngày")]
LOAI_KINH_DOANH = {"IBB", "DIABAN"}
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
@nho("so_lieu")
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


@nho("so_lieu")
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
                         "nhom_kd": meta[c].get("loai") in LOAI_KINH_DOANH,
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
    out["_lau"] = out.m3 + out.m4
    out = out.sort_values(["_lau", "m2", "tong"], ascending=False).drop(columns="_lau")
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
    from app.canh_bao import acc_truong_phong
    g = g[~g.index.isin(acc_truong_phong(g.index))]          # trưởng phòng không xếp hạng nhân viên
    return g.reset_index().sort_values("online", ascending=False).replace({np.nan: None})


def muc_chung_kinh_doanh(df: pd.DataFrame, thang: str) -> dict:
    """Tỷ lệ chung của các phòng kinh doanh (IBB và địa bàn) - mốc tô màu công bằng hơn so với
    dòng tổng chi nhánh vốn gồm cả phòng Kỹ thuật, CUS, ECOM có đặc thù bán kèm thấp."""
    kd = {p["code"] for p in phong_order(thang) if p.get("loai") in LOAI_KINH_DOANH}
    return chi_so_chung(df[df.phong_code.isin(kd)])


# ------------------------------------------------------------------ bán theo tỉnh (CN quản lý của hợp đồng)
@nho("so_lieu")
def hd_theo_tinh(tu: str, den: str, chi_phong: list[str] | None = None, theo: str = "online") -> pd.DataFrame:
    """Một dòng = một hợp đồng Internet: phòng bán, tỉnh của khách (CN quản lý), gói, phường/xã, nhân viên.
    theo = 'online' (ngày online trong kỳ) hoặc 'ban' (ngày tạo hợp đồng trong kỳ - số bán mới, gồm cả hợp đồng
    chưa online)."""
    from app.tinh import ma_tinh, ten_tinh
    cot = "ngay_tao_hd" if theo == "ban" else "ngay_online"
    df = pd.read_sql(text(f"""SELECT phong_code, cn_quan_ly, goi_dich_vu, quan_huyen, acc_norm, acc_nhan_vien, ngay_online
                              FROM fact_internet WHERE {cot} >= :tu AND {cot} <= :den"""), engine,
                     params={"tu": tu, "den": den})
    if chi_phong is not None:
        df = df[df.phong_code.isin(set(chi_phong))]
    df = df.copy()
    df["ma_tinh"] = [ma_tinh(x) for x in df.cn_quan_ly]
    df["tinh"] = [ten_tinh(m) for m in df.ma_tinh]
    df["nhom_goi"] = [nhom_goi(g) for g in df.goi_dich_vu]
    df["xa"] = [ten_xa(x) for x in df.quan_huyen]
    return df


def online_theo_tinh(tu: str, den: str, chi_phong: list[str] | None = None) -> pd.DataFrame:
    """Hợp đồng online trong kỳ kèm tỉnh (xem hd_theo_tinh)."""
    return hd_theo_tinh(tu, den, chi_phong, "online")


def ten_xa(v) -> str:
    """Phường / xã trong file (cột Quận huyện - sau sáp nhập 07/2025 chỉ còn xã/phường, tên không dấu)."""
    s = " ".join(str(v or "").split())
    if not s or s.lower().startswith("không"):
        return "Không rõ"
    for a, b in (("Phuong ", "Phường "), ("Xa ", "Xã "), ("Thi tran ", "Thị trấn "), ("Dac khu ", "Đặc khu ")):
        if s.startswith(a):
            return b + s[len(a):]
    return s


def co_cau_goi_tinh(df: pd.DataFrame, toi_da: int = 15) -> pd.DataFrame:
    """Dòng = tỉnh (nhiều hợp đồng nhất trước): số hợp đồng từng nhóm gói + tỷ trọng %, gói chi tiết hay bán nhất."""
    nhom = list(NHOM_GOI + ("Khác",))
    if df.empty:
        return pd.DataFrame(columns=["ma_tinh", "tinh", "so_hd", *nhom, *[f"{g}_pct" for g in nhom], "goi_nhieu"])
    pv = pd.crosstab([df.ma_tinh, df.tinh], df.nhom_goi).reindex(columns=nhom, fill_value=0)
    pv["so_hd"] = pv.sum(axis=1)
    for g in nhom:
        pv[f"{g}_pct"] = (pv[g] / pv.so_hd * 100).round(1)
    top = df.groupby(["ma_tinh", "tinh"]).goi_dich_vu.agg(lambda x: x.fillna("?").value_counts().index[0])
    pv["goi_nhieu"] = top.reindex(pv.index)
    return pv.sort_values("so_hd", ascending=False).head(toi_da).reset_index()


def chi_tiet_tinh(df: pd.DataFrame, ma: str, ten_nv: dict | None = None, ten_phong: dict | None = None) -> dict:
    """Đi sâu một tỉnh: phường/xã, nhân viên (trừ trưởng phòng), gói cước, phòng bán (số hợp đồng, tỷ trọng trong
    tỉnh)."""
    x = df[df.ma_tinh == ma]
    tong = len(x)

    def dem(cot, ten):
        if not tong:
            return pd.DataFrame(columns=[ten, "so", "ty_trong"])
        g = x.groupby(cot, dropna=False).size().rename("so").reset_index().rename(columns={cot: ten})
        g["ty_trong"] = (g.so / tong * 100).round(1)
        return g.sort_values("so", ascending=False).reset_index(drop=True)

    nv = x.assign(_a=x.acc_norm.fillna(x.acc_nhan_vien)).groupby(["_a", "phong_code"]).agg(
        so=("_a", "size"), acc=("acc_nhan_vien", "first")).reset_index() if tong else pd.DataFrame()
    if len(nv):
        from app.canh_bao import acc_truong_phong
        nv = nv[~nv._a.isin(acc_truong_phong(set(nv._a.dropna())))].copy()   # trưởng phòng không xếp hạng cá nhân
    if len(nv):
        nv["ho_ten"] = [(ten_nv or {}).get(a) or c for a, c in zip(nv._a, nv.acc)]
        nv["phong"] = [(ten_phong or {}).get(c, "Chưa gán phòng") for c in nv.phong_code]
        nv["ty_trong"] = (nv.so / tong * 100).round(1)
        nv = nv.sort_values("so", ascending=False).reset_index(drop=True)
    ph = dem("phong_code", "phong_code")
    if len(ph):
        ph["phong"] = [(ten_phong or {}).get(c, "Chưa gán phòng") for c in ph.phong_code]
    return {"tong": tong, "xa": dem("xa", "xa"), "goi": dem("goi_dich_vu", "goi"), "nv": nv, "phong": ph}


def ban_online_ngay(ngay: str, chi_phong: list[str] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Một ngày: (hợp đồng tạo trong ngày = số bán, hợp đồng online trong ngày), kèm tỉnh."""
    return hd_theo_tinh(ngay, ngay, chi_phong, "ban"), hd_theo_tinh(ngay, ngay, chi_phong, "online")


def bang_ngay_tinh(ban: pd.DataFrame, onl: pd.DataFrame, phong: list[str]) -> pd.DataFrame:
    """Dòng = tỉnh; cột: tong_ban, tong_onl và <phòng>_ban, <phòng>_onl cho từng phòng trong `phong`."""
    from app.tinh import NOI_TINH
    k = ["ma_tinh", "tinh"]
    if ban.empty and onl.empty:
        return pd.DataFrame(columns=[*k, "tong_ban", "tong_onl", "noi_tinh"])
    b = ban.pivot_table(index=k, columns="phong_code", aggfunc="size", fill_value=0) if len(ban) else pd.DataFrame()
    o = onl.pivot_table(index=k, columns="phong_code", aggfunc="size", fill_value=0) if len(onl) else pd.DataFrame()
    idx = b.index.union(o.index)
    b, o = b.reindex(idx, fill_value=0), o.reindex(idx, fill_value=0)
    out = pd.DataFrame(index=idx)
    out["tong_ban"], out["tong_onl"] = b.sum(axis=1), o.sum(axis=1)
    for c in phong:
        out[f"{c}_ban"] = b[c] if c in b else 0
        out[f"{c}_onl"] = o[c] if c in o else 0
    out = out.reset_index()
    out["noi_tinh"] = out.ma_tinh.isin(NOI_TINH)
    return out.sort_values(["tong_ban", "tong_onl"], ascending=False).reset_index(drop=True)


def bang_tinh(df: pd.DataFrame, df_ck: pd.DataFrame) -> pd.DataFrame:
    """Dòng = tỉnh: online kỳ này, tỷ trọng, cùng kỳ tháng trước, chênh lệch. Xếp nhiều -> ít."""
    from app.tinh import NOI_TINH
    if df.empty and df_ck.empty:
        return pd.DataFrame(columns=["ma_tinh", "tinh", "online", "ty_trong", "ck", "chenh", "noi_tinh"])
    nay = df.groupby(["ma_tinh", "tinh"]).size().rename("online")
    ck = df_ck.groupby(["ma_tinh", "tinh"]).size().rename("ck")
    out = pd.concat([nay, ck], axis=1).fillna(0).astype(int).reset_index()
    tong = out.online.sum()
    out["ty_trong"] = (out.online / tong * 100).round(1) if tong else 0.0
    out["chenh"] = out.online - out.ck
    out["noi_tinh"] = out.ma_tinh.isin(NOI_TINH)
    return out[out.online + out.ck > 0].sort_values(["online", "ck"], ascending=False).reset_index(drop=True)


def ma_tran_tinh_phong(df: pd.DataFrame, thang: str) -> tuple[pd.DataFrame, list[dict]]:
    """Tỉnh × phòng: số online mỗi phòng bán ở mỗi tỉnh. Trả (bảng, danh sách phòng theo thứ tự báo cáo)."""
    if df.empty:
        return pd.DataFrame(), []
    thu_tu = [p for p in phong_order(thang) if p["code"] in set(df.phong_code)]
    pv = df.pivot_table(index=["ma_tinh", "tinh"], columns="phong_code", aggfunc="size", fill_value=0)
    pv = pv.reindex(columns=[p["code"] for p in thu_tu], fill_value=0)
    pv["tong"] = pv.sum(axis=1)
    return pv.sort_values("tong", ascending=False).reset_index(), thu_tu


def ma_tran_nv_tinh(df: pd.DataFrame, ten_nv: dict, ten_phong: dict, toi_da: int | None = None) \
        -> tuple[pd.DataFrame, list[tuple[str, str]]]:
    """Nhân viên × tỉnh: số online mỗi người bán ở mỗi tỉnh. Cột = mọi tỉnh có số (nhiều trước), hoặc `toi_da` tỉnh
    nhiều nhất + 'Tỉnh khác'.
    Trưởng phòng không đưa vào (không tính chỉ số cá nhân - số của họ vẫn ở bảng theo phòng)."""
    from app.canh_bao import acc_truong_phong
    from app.tinh import NOI_TINH
    if df.empty:
        return pd.DataFrame(), []
    x = df.assign(acc=df.acc_norm.fillna(df.acc_nhan_vien.str.lower()))
    x = x[x.acc.notna() & ~x.acc.isin(acc_truong_phong(set(x.acc)))]
    if x.empty:
        return pd.DataFrame(), []
    top = x.groupby(["ma_tinh", "tinh"]).size().sort_values(ascending=False)
    if toi_da:
        top = top.head(toi_da)
    cot = [ma for ma, _ in top.index]
    pv = x.pivot_table(index="acc", columns="ma_tinh", aggfunc="size", fill_value=0)
    out = pd.DataFrame(index=pv.index)
    out["tong"] = pv.sum(axis=1)
    ngoai = [c for c in pv.columns if c not in NOI_TINH]
    out["ngoai"] = pv[ngoai].sum(axis=1) if ngoai else 0
    out["ngoai_pct"] = (out.ngoai / out.tong * 100).round(0)
    for c in cot:
        out[c] = pv[c] if c in pv else 0
    khac = [c for c in pv.columns if c not in cot]
    out["khac"] = pv[khac].sum(axis=1) if khac else 0
    phong = x.groupby("acc").phong_code.agg(lambda v: v.value_counts().index[0])
    acc_goc = x.groupby("acc").acc_nhan_vien.first()
    out["phong"] = [ten_phong.get(phong[a], "Chưa gán phòng") for a in out.index]
    out["ho_ten"] = [ten_nv.get(a) or acc_goc.get(a) or a for a in out.index]
    out["acc"] = [acc_goc.get(a) or a for a in out.index]
    out["acc_key"] = list(out.index)
    thu_tu = {v: i for i, v in enumerate(ten_phong.values())}
    out["_o"] = [thu_tu.get(p_, 999) for p_ in out.phong]
    out = out.sort_values(["_o", "tong"], ascending=[True, False]).drop(columns="_o")
    return out.reset_index(drop=True), list(top.index)


def chi_tiet_nv_tinh(acc_key: str, tu: str, den: str, chi_phong: list[str] | None = None) -> dict:
    """Một nhân viên trong kỳ: số bán (hợp đồng tạo trong kỳ, trong đó đã online bao nhiêu) và số online (online trong
    kỳ) theo từng tỉnh và từng phường / xã."""
    from app.tinh import NOI_TINH

    def cua(d):
        return d[d.acc_norm.fillna(d.acc_nhan_vien.str.lower()) == acc_key]
    ban, onl = cua(hd_theo_tinh(tu, den, chi_phong, "ban")), cua(hd_theo_tinh(tu, den, chi_phong, "online"))
    ban = ban.assign(da_onl=ban.ngay_online.notna().astype(int))
    k = ["ma_tinh", "tinh"]

    def gop(keys):
        a = ban.groupby(keys).agg(ban=("da_onl", "size"), ban_da_onl=("da_onl", "sum"))
        b = onl.groupby(keys).size().rename("onl")
        g = pd.concat([a, b], axis=1).fillna(0).astype(int).reset_index()
        return g.sort_values(["onl", "ban"], ascending=False).reset_index(drop=True)
    tinh = gop(k) if len(ban) or len(onl) else pd.DataFrame(columns=[*k, "ban", "ban_da_onl", "onl"])
    if len(tinh):
        tinh["ty_trong"] = (tinh.onl / max(int(tinh.onl.sum()), 1) * 100).round(1)
        tinh["noi_tinh"] = tinh.ma_tinh.isin(NOI_TINH)
    xa = gop([*k, "xa"]) if len(ban) or len(onl) else pd.DataFrame(columns=[*k, "xa", "ban", "ban_da_onl", "onl"])
    goi = onl.goi_dich_vu.fillna("?").value_counts()
    ngay_onl = pd.to_datetime(ban.ngay_online)
    onl_tu_ban = int(((ngay_onl >= pd.Timestamp(tu)) & (ngay_onl <= pd.Timestamp(den))).sum())
    return {"ban": len(ban), "ban_da_onl": int(ban.da_onl.sum()), "onl": len(onl),
            "onl_ban_truoc": max(len(onl) - onl_tu_ban, 0),
            "ngoai_onl": int((~onl.ma_tinh.isin(NOI_TINH)).sum()), "tinh": tinh, "xa": xa,
            "goi": ", ".join(f"{g} {n}" for g, n in goi.head(4).items())}
