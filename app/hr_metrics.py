"""Chỉ số nhân sự: nối dữ liệu bán hàng với hồ sơ nhân sự (NSLĐ)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sqlalchemy import text

from app.db import engine
from app.metrics import month_range
from app.org import phong_order, ten_bay
from app.sql_dialect import so_ngay_giua, thang_cua

_SQL_BAN = """
SELECT acc_norm, COUNT(*) AS n, COUNT(DISTINCT {col}) AS so_ngay
FROM {table} WHERE {col} >= :start AND {col} <= :end{extra}
GROUP BY acc_norm
"""


def _ban(table: str, col: str, start, end, extra: str = "") -> pd.DataFrame:
    sql = text(_SQL_BAN.format(table=table, col=col, extra=extra))
    return pd.read_sql(sql, engine, params={"start": start.isoformat(), "end": end.isoformat()})


def hr_thang_gan_nhat(thang: str) -> str | None:
    df = pd.read_sql(text("SELECT MAX(thang) t FROM hr_monthly WHERE thang <= :t"),
                     engine, params={"t": thang})
    return df.iloc[0, 0]


def hieu_suat_nhan_su(thang: str, chi_phong: list[str] | None = None) -> pd.DataFrame:
    """Một dòng = một nhân sự: số bán trong tháng + hồ sơ nhân sự gần nhất."""
    start, end, _ = month_range(thang)
    online = _ban("fact_internet", "ngay_online", start, end).set_index("acc_norm")
    vvip = _ban("fact_fptplay", "ngay_online", start, end, " AND la_vvip = TRUE").set_index("acc_norm")
    cam = _ban("fact_camera", "ngay_online", start, end).set_index("acc_norm")

    staff = pd.read_sql(text("SELECT acc, acc_norm, phong_code, ma_nv FROM staff_map"), engine)
    hr_thang = hr_thang_gan_nhat(thang)
    hr = pd.DataFrame()
    if hr_thang:
        hr = pd.read_sql(text("""SELECT ma_nv, acc, ho_ten, vi_tri, phong_ps, tham_nien_bucket,
                                        tham_nien_thang, nhom_tham_nien, trang_thai, ngay_nghi_viec,
                                        diem_itn, diem_fpt_play, diem_tong, ket_luan, dieu_kien
                                 FROM hr_monthly WHERE thang = :t"""),
                         engine, params={"t": hr_thang})
        hr["acc_norm"] = hr["acc"].str.strip().str.lower()

    base = staff[["acc", "acc_norm", "phong_code"]].copy()
    if not hr.empty:                       # nhân sự có trong HR nhưng chưa có trong danh mục
        extra = hr[~hr.acc_norm.isin(set(base.acc_norm))][["acc", "acc_norm"]].copy()
        extra["phong_code"] = None
        base = pd.concat([base, extra], ignore_index=True)
    # người có số bán nhưng không có ở cả hai nơi
    con_lai = set(online.index) | set(vvip.index) | set(cam.index)
    thieu = con_lai - set(base.acc_norm)
    if thieu:
        base = pd.concat([base, pd.DataFrame({"acc": sorted(thieu), "acc_norm": sorted(thieu),
                                              "phong_code": None})], ignore_index=True)

    base = base.drop_duplicates("acc_norm").set_index("acc_norm")
    base["online"] = online["n"].reindex(base.index).fillna(0).astype(int)
    base["so_ngay_co_so"] = online["so_ngay"].reindex(base.index).fillna(0).astype(int)
    base["vvip"] = vvip["n"].reindex(base.index).fillna(0).astype(int)
    base["camera"] = cam["n"].reindex(base.index).fillna(0).astype(int)
    base["ty_le_vvip"] = (base.vvip / base.online.replace(0, np.nan) * 100).round(1)

    if not hr.empty:
        hr_idx = hr.drop_duplicates("acc_norm").set_index("acc_norm")
        for c in ("ma_nv", "ho_ten", "vi_tri", "phong_ps", "tham_nien_bucket", "tham_nien_thang",
                  "nhom_tham_nien", "trang_thai", "diem_tong", "ket_luan", "dieu_kien"):
            base[c] = hr_idx[c].reindex(base.index)
    else:
        for c in ("ma_nv", "ho_ten", "vi_tri", "phong_ps", "tham_nien_bucket", "tham_nien_thang",
                  "nhom_tham_nien", "trang_thai", "diem_tong", "ket_luan", "dieu_kien"):
            base[c] = np.nan

    meta = {p["code"]: p for p in phong_order(thang)}
    base["phong"] = [meta[c]["ten"] if c in meta else "Chưa gán phòng" for c in base.phong_code]
    base["bay"] = [ten_bay(meta[c]["bay"]) if c in meta else "KHÁC" for c in base.phong_code]
    ten_cn = {"DNG": "Đà Nẵng", "QNM": "Quảng Nam"}

    def _cn(phong_code, acc: str) -> str:
        # chưa gán phòng thì đoán theo tiền tố acc (DNG.xxx / QNM.xxx)
        ma = meta.get(phong_code, {}).get("chi_nhanh")
        if not ma:
            ma = str(acc).upper()[:3] if str(acc).upper()[:4] in ("DNG.", "QNM.") else None
        return ten_cn.get(ma, "")

    base["chi_nhanh"] = [_cn(c, a) for c, a in zip(base.phong_code, base.acc)]
    base["hr_thang"] = hr_thang

    if chi_phong is not None:
        base = base[base.phong_code.isin(set(chi_phong))]
    out = base.reset_index().rename(columns={"index": "acc_norm"})
    return out.sort_values("online", ascending=False)


def tong_hop_tham_nien(df: pd.DataFrame) -> pd.DataFrame:
    """Năng suất bình quân theo nhóm thâm niên (chỉ tính người đang làm việc)."""
    d = df[df.nhom_tham_nien.notna()].copy()
    if d.empty:
        return pd.DataFrame()
    g = d.groupby("nhom_tham_nien").agg(so_nv=("acc", "count"), online=("online", "sum"),
                                        vvip=("vvip", "sum"), camera=("camera", "sum"))
    g["tb_online"] = (g.online / g.so_nv).round(1)
    g["ty_le_vvip"] = (g.vvip / g.online.replace(0, np.nan) * 100).round(1)
    thu_tu = {"MOI": 1, "DANG_LEN": 2, "ON_DINH": 3, "LAU_NAM": 4}
    return g.reset_index().assign(_o=lambda x: x.nhom_tham_nien.map(thu_tu)).sort_values("_o").drop(columns="_o")


def zero_sellers(df: pd.DataFrame) -> pd.DataFrame:
    """Nhân sự không có số Online nào trong tháng (đang làm việc)."""
    d = df[(df.online == 0) & (df.trang_thai.fillna("") != "Nghỉ việc")]
    return d[["acc", "ho_ten", "phong", "nhom_tham_nien", "vvip", "camera", "trang_thai"]]

def duong_cong_nang_suat(thang: str, chi_phong=None) -> pd.DataFrame:
    """Năng suất trung bình theo số tháng thâm niên - dùng để xem người mới lên tay nghề thế nào."""
    df = hieu_suat_nhan_su(thang, chi_phong=chi_phong)
    d = df[df.tham_nien_thang.notna() & (df.trang_thai.fillna("Bình thường") != "Nghỉ việc")]
    if d.empty:
        return pd.DataFrame()
    g = d.groupby("tham_nien_thang").agg(so_nv=("acc", "count"), tb_online=("online", "mean"),
                                         tb_vvip=("vvip", "mean"),
                                         max_online=("online", "max")).reset_index()
    g["tb_online"] = g.tb_online.round(1)
    g["tb_vvip"] = g.tb_vvip.round(1)
    chuan = d[d.tham_nien_thang >= 13].online.median()
    g["muc_chuan"] = round(float(chuan), 1) if pd.notna(chuan) else None
    g["dat_bao_nhieu"] = (g.tb_online / chuan * 100).round(0) if chuan else None
    return g.sort_values("tham_nien_thang")


def canh_bao_nhan_su(thang: str, chi_phong=None) -> pd.DataFrame:
    """Cảnh báo sớm: ai đang tụt dốc hoặc lâu không có số."""
    start, end, _ = month_range(thang)
    moc = pd.read_sql(text("SELECT MAX(ngay_online) d FROM fact_internet"), engine).iloc[0, 0]
    if not moc:
        return pd.DataFrame()
    moc = pd.Timestamp(str(moc)[:10])
    t7, t14 = moc - pd.Timedelta(days=6), moc - pd.Timedelta(days=13)

    sql = text("""SELECT acc_norm, ngay_online FROM fact_internet
                  WHERE ngay_online >= :tu AND ngay_online <= :den""")
    ban = pd.read_sql(sql, engine, params={"tu": (moc - pd.Timedelta(days=27)).date().isoformat(),
                                           "den": moc.date().isoformat()})
    ban["ngay_online"] = pd.to_datetime(ban["ngay_online"])

    nv = hieu_suat_nhan_su(thang, chi_phong=chi_phong)
    nv = nv[nv.trang_thai.fillna("Bình thường") != "Nghỉ việc"]
    # chỉ xét nhân sự kinh doanh thực sự: thuộc phòng KD/địa bàn và có hồ sơ hoặc có bán trong kỳ
    kd = {p["code"] for p in phong_order() if p["loai"] in ("IBB", "DIABAN")}
    nv = nv[nv.phong_code.isin(kd) & (nv.ho_ten.notna() | (nv.online > 0))]
    g7 = ban[ban.ngay_online >= t7].groupby("acc_norm").size()
    g14 = ban[(ban.ngay_online >= t14) & (ban.ngay_online < t7)].groupby("acc_norm").size()
    cuoi = ban.groupby("acc_norm").ngay_online.max()

    out = nv[["acc", "ho_ten", "phong", "phong_code", "nhom_tham_nien", "online",
              "ket_luan"]].copy()
    out["tuan_nay"] = [int(g7.get(a, 0)) for a in nv.index.map(lambda i: nv.loc[i, "acc_norm"])] \
        if "acc_norm" in nv.columns else 0
    out["tuan_nay"] = [int(g7.get(a, 0)) for a in nv.acc_norm]
    out["tuan_truoc"] = [int(g14.get(a, 0)) for a in nv.acc_norm]
    out["ngay_cuoi_co_so"] = [str(cuoi.get(a, ""))[:10] for a in nv.acc_norm]
    out["so_ngay_khong_so"] = [
        int((moc - cuoi[a]).days) if a in cuoi.index else 30 for a in nv.acc_norm]
    out["chenh"] = out.tuan_nay - out.tuan_truoc

    def _muc(r):
        if r.so_ngay_khong_so >= 14:
            return "Cao"
        if r.tuan_nay == 0:
            return "Cao"
        if r.tuan_truoc >= 3 and r.chenh <= -r.tuan_truoc * 0.5:
            return "Trung bình"
        if r.ket_luan == "NOT OK":
            return "Trung bình"
        return ""

    out["muc_rui_ro"] = out.apply(_muc, axis=1)
    out = out[out.muc_rui_ro != ""]
    thu_tu = {"Cao": 0, "Trung bình": 1}
    return out.assign(_o=out.muc_rui_ro.map(thu_tu)).sort_values(
        ["_o", "so_ngay_khong_so"], ascending=[True, False]).drop(columns="_o")


def thoi_gian_trien_khai(thang: str) -> pd.DataFrame:
    """Số ngày từ lúc tạo hợp đồng đến lúc online, theo phòng."""
    df = pd.read_sql(text(f"""SELECT p.ten AS phong,
                                    {so_ngay_giua("f.ngay_online", "f.ngay_tao_hd")} AS so_ngay
                             FROM fact_internet f LEFT JOIN dim_phong p ON p.code = f.phong_code
                             WHERE {thang_cua("f.ngay_online")} = :t
                               AND f.ngay_tao_hd IS NOT NULL"""),
                     engine, params={"t": thang})
    if df.empty:
        return df
    g = df.groupby("phong").so_ngay.agg(["count", "mean", "median"]).reset_index()
    g.columns = ["phong", "so_hd", "tb_ngay", "trung_vi"]
    g["tb_ngay"] = g.tb_ngay.round(1)
    return g.sort_values("tb_ngay", ascending=False)
