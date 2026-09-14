"""Tính các chỉ số của báo cáo Tracking từ database.

Công thức lấy đúng theo Khối E của file báo cáo hiện tại:
- Sum kỳ [a->b] = Cộng dồn[b] - Cộng dồn[a-1]
- TB/ngày      = Sum kỳ / số ngày
- %VVIP        = Sum VVIP kỳ / Sum Online kỳ
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import text

from app.db import engine
from app.org import bay_info, phong_order, ten_bay

# metric -> (bảng, cột ngày, điều kiện thêm)
METRICS = {
    "online":  ("fact_internet", "ngay_online", ""),
    "ban_moi": ("fact_internet", "ngay_tao_hd", ""),
    "vvip":    ("fact_fptplay", "ngay_online", " AND la_vvip = TRUE"),
    "fptplay": ("fact_fptplay", "ngay_online", ""),
    "camera":  ("fact_camera", "ngay_online", ""),
}
METRIC_LABEL = {"online": "Số Online", "vvip": "Số V.VIP", "camera": "Camera",
                "ban_moi": "Bán mới", "fptplay": "FPT Play"}


def month_range(thang: str) -> tuple[date, date, int]:
    y, m = (int(x) for x in thang.split("-"))
    days = monthrange(y, m)[1]
    return date(y, m, 1), date(y, m, days), days


def prev_month(thang: str) -> str:
    y, m = (int(x) for x in thang.split("-"))
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def daily_counts(thang: str, metric: str = "online") -> pd.DataFrame:
    """Bảng số theo ngày: dòng = mã phòng, cột = ngày 1..n."""
    table, col, extra = METRICS[metric]
    start, end, days = month_range(thang)
    sql = text(f"""SELECT phong_code, {col} AS ngay, COUNT(*) AS n
                   FROM {table}
                   WHERE {col} >= :start AND {col} <= :end{extra}
                   GROUP BY phong_code, {col}""")
    df = pd.read_sql(sql, engine, params={"start": start.isoformat(), "end": end.isoformat()})
    codes = [p["code"] for p in phong_order(thang)]
    out = pd.DataFrame(0, index=codes, columns=range(1, days + 1), dtype=int)
    if not df.empty:
        df["ngay"] = pd.to_datetime(df["ngay"]).dt.day
        pv = df.pivot_table(index="phong_code", columns="ngay", values="n",
                            aggfunc="sum", fill_value=0)
        for c in pv.columns:
            for i in pv.index:
                if i in out.index and c in out.columns:
                    out.at[i, c] = int(pv.at[i, c])
    return out


def tracking_table(thang: str, metric: str = "online", cong_don: bool = False,
                   den_ngay: int | None = None, chi_phong: list[str] | None = None) -> pd.DataFrame:
    """Bảng giống Khối A/B/C: Bầy -> Phòng -> ngày, có dòng tổng của từng bầy.

    chi_phong: giới hạn theo quyền người dùng (None = xem tất cả).
    """
    daily = daily_counts(thang, metric)
    if chi_phong is not None:
        daily = daily.loc[[c for c in daily.index if c in set(chi_phong)]]
    if cong_don:
        daily = daily.cumsum(axis=1)
    if den_ngay:
        daily = daily.loc[:, [c for c in daily.columns if c <= den_ngay]]

    bays = bay_info()
    rows = []
    for bcode, binfo in sorted(bays.items(), key=lambda kv: kv[1]["thu_tu"]):
        phongs = [p for p in phong_order(thang) if p["bay"] == bcode and p["code"] in daily.index]
        if not phongs:
            continue
        for i, p in enumerate(phongs):
            vals = daily.loc[p["code"]]
            rows.append({"bay": binfo["ten"] if i == 0 else "", "phong": p["ten"],
                         "loai_dong": "data", "phong_code": p["code"],
                         **{str(c): int(vals[c]) for c in daily.columns}})
        sub = daily.loc[[p["code"] for p in phongs]].sum()
        rows.append({"bay": f"TỔNG {binfo['ten'].upper()}", "phong": "", "loai_dong": "subtotal",
                     "phong_code": f"SUB_{bcode}", **{str(c): int(sub[c]) for c in daily.columns}})
    # Khối D1: gộp các phòng KT/CUS/ECOM thành DNG Khác / QNM Khác
    meta_all = {p["code"]: p for p in phong_order(thang)}
    for nhom, ten in (("DNG", "DNG Khác"), ("QNM", "QNM Khác")):
        codes = [c for c in daily.index if meta_all.get(c, {}).get("nhom_khac") == nhom]
        if not codes:
            continue
        vals = daily.loc[codes].sum()
        rows.append({"bay": ten, "phong": "", "loai_dong": "nhomkhac",
                     "phong_code": f"KHAC_{nhom}",
                     **{str(c): int(vals[c]) for c in daily.columns}})

    tot = daily.sum()
    rows.append({"bay": "TỔNG TOÀN CHI NHÁNH", "phong": "", "loai_dong": "total",
                 "phong_code": "TOTAL", **{str(c): int(tot[c]) for c in daily.columns}})

    df = pd.DataFrame(rows)
    day_cols = [str(c) for c in daily.columns]
    df["Tổng"] = df[day_cols].sum(axis=1) if not cong_don else df[day_cols[-1]]
    return df


def lan_nap_day_du(dataset: str = "internet") -> int | None:
    """Mã lần nạp gần nhất nếu đó là một file đầy đủ (bản chụp 3 tháng), ngược lại None.

    File export là bản chụp cuộn khoảng 3 tháng: hợp đồng bị huỷ/rớt sẽ biến mất khỏi file mới.
    Hợp đồng chưa online mà không còn trong file mới nhất thì không còn là "tồn" nữa.
    Lần nạp chỉ bằng dưới một nửa lần nạp đầy đủ trước đó thì coi là file lẻ (không phải bản chụp),
    khi đó không dùng để lọc.
    """
    df = pd.read_sql(text("""SELECT id, rows_valid FROM upload_batch WHERE dataset = :d
                             ORDER BY id DESC"""), engine, params={"d": dataset})
    if df.empty:
        return None
    moi = df.iloc[0]
    lon_nhat_truoc = df.iloc[1:6].rows_valid.max() if len(df) > 1 else 0
    if lon_nhat_truoc and moi.rows_valid < 0.5 * lon_nhat_truoc:
        return None
    return int(moi.id)


def dieu_kien_ton(alias: str = "") -> tuple[str, dict]:
    """Điều kiện SQL cho "Số tồn": chưa online VÀ còn nằm trong file Internet mới nhất."""
    lo = lan_nap_day_du("internet")
    if lo is None:
        return f"{alias}ngay_online IS NULL", {}
    return f"{alias}ngay_online IS NULL AND {alias}batch_id = :lo_moi_nhat", {"lo_moi_nhat": lo}


def tong_thang(thang: str, metric: str = "online") -> int:
    return int(daily_counts(thang, metric).to_numpy().sum())


def summary_phong(thang: str, den_ngay: int | None = None,
                  chi_phong: list[str] | None = None) -> pd.DataFrame:
    """Bảng tổng hợp theo phòng: online, vvip, camera, tồn, chỉ tiêu, tăng trưởng."""
    start, end, days = month_range(thang)
    den_ngay = den_ngay or days

    def _sum(metric):
        d = daily_counts(thang, metric)
        if chi_phong is not None:
            d = d.loc[[c for c in d.index if c in set(chi_phong)]]
        return d.loc[:, [c for c in d.columns if c <= den_ngay]].sum(axis=1)

    online, vvip, camera, ban_moi = (_sum(m) for m in ("online", "vvip", "camera", "ban_moi"))

    # cùng kỳ tháng trước (cùng số ngày)
    pm = prev_month(thang)
    d_prev = daily_counts(pm, "online")
    prev = d_prev.loc[:, [c for c in d_prev.columns if c <= den_ngay]].sum(axis=1)

    dk_ton, p_ton = dieu_kien_ton()
    ton = pd.read_sql(text(f"""SELECT phong_code, COUNT(*) n FROM fact_internet
                               WHERE {dk_ton} GROUP BY phong_code"""), engine, params=p_ton)
    ton = ton.set_index("phong_code")["n"] if not ton.empty else pd.Series(dtype=int)

    tgt = pd.read_sql(text("""SELECT ma_doi_tuong, chi_tieu, gia_tri FROM target_monthly
                              WHERE thang = :t AND doi_tuong = 'PHONG'"""),
                      engine, params={"t": thang})
    tgt_pv = (tgt.pivot_table(index="ma_doi_tuong", columns="chi_tieu", values="gia_tri")
              if not tgt.empty else pd.DataFrame())

    out = pd.DataFrame(index=online.index)
    meta = {p["code"]: p for p in phong_order(thang)}
    out["phong"] = [meta[c]["ten"] for c in out.index]
    out["bay"] = [ten_bay(meta[c]["bay"]) for c in out.index]
    out["online"] = online
    out["vvip"] = vvip
    out["camera"] = camera
    out["ban_moi"] = ban_moi
    out["ton"] = [int(ton.get(c, 0)) for c in out.index]
    out["ty_le_vvip"] = (out.vvip / out.online.replace(0, np.nan) * 100).round(1)
    out["cung_ky_thang_truoc"] = prev.reindex(out.index).fillna(0).astype(int)
    out["tang_truong"] = ((out.online - out.cung_ky_thang_truoc) /
                          out.cung_ky_thang_truoc.replace(0, np.nan) * 100).round(1)
    for ct, colname in (("internet", "muc_tieu_internet"), ("camera", "muc_tieu_camera"),
                        ("ngay", "muc_tieu_ngay")):
        out[colname] = (tgt_pv[ct].reindex(out.index) if ct in getattr(tgt_pv, "columns", [])
                        else np.nan)
    out["htkh"] = (out.online / out.muc_tieu_internet.replace(0, np.nan) * 100).round(1)
    return out.reset_index(names="phong_code")


def tien_do_thang(thang: str, den_ngay: int | None = None) -> dict:
    """Tiến độ tháng: đã chạy bao nhiêu ngày, cần bao nhiêu số/ngày cho phần còn lại."""
    _, _, days = month_range(thang)
    den_ngay = den_ngay or days
    hien_tai = int(daily_counts(thang, "online").loc[:, :den_ngay].to_numpy().sum())
    tgt = pd.read_sql(text("""SELECT SUM(gia_tri) g FROM target_monthly
                              WHERE thang = :t AND doi_tuong = 'PHONG' AND chi_tieu = 'internet'"""),
                      engine, params={"t": thang})
    muc_tieu = float(tgt.iloc[0, 0] or 0)
    con_lai_ngay = max(days - den_ngay, 0)
    return {
        "ngay_da_chay": den_ngay,
        "so_ngay_trong_thang": days,          # dùng đúng số ngày thật của tháng
        "ty_le_thoi_gian": round(den_ngay / days * 100, 2),
        "hien_tai": hien_tai,
        "muc_tieu": muc_tieu,
        "ty_le_hoan_thanh": round(hien_tai / muc_tieu * 100, 2) if muc_tieu else None,
        "con_thieu": max(muc_tieu - hien_tai, 0) if muc_tieu else None,
        "con_lai_ngay": con_lai_ngay,
        "can_moi_ngay": (round((muc_tieu - hien_tai) / con_lai_ngay)
                         if muc_tieu and con_lai_ngay else None),
        "tb_ngay_hien_tai": round(hien_tai / den_ngay, 1) if den_ngay else 0,
    }


def ngay_co_du_lieu(thang: str) -> int:
    """Ngày cuối cùng có dữ liệu online trong tháng."""
    d = daily_counts(thang, "online").sum()
    nz = [c for c in d.index if d[c] > 0]
    return max(nz) if nz else 0


def cac_ngay_co_du_lieu() -> list[str]:
    """Danh sách ngày (YYYY-MM-DD) đã có số Online - dùng cho bộ chọn ngày."""
    df = pd.read_sql(text("""SELECT DISTINCT ngay_online AS d FROM fact_internet
                             WHERE ngay_online IS NOT NULL ORDER BY d"""), engine)
    return [str(x)[:10] for x in df["d"].dropna().tolist()]


def ngay_moi_nhat() -> str | None:
    ds = cac_ngay_co_du_lieu()
    return ds[-1] if ds else None


def cac_thang_co_du_lieu() -> list[str]:
    from app.sql_dialect import thang_cua
    df = pd.read_sql(text(f"""SELECT DISTINCT {thang_cua('ngay_online')} AS thang
                             FROM fact_internet WHERE ngay_online IS NOT NULL
                             ORDER BY thang DESC"""), engine)
    return df["thang"].dropna().tolist()

# ------------------------------------------------------------ theo khoảng ngày
def tong_theo_phong(tu: str, den: str, metric: str = "online") -> pd.DataFrame:
    """Tổng số trong khoảng [tu, den] theo từng phòng."""
    table, col, extra = METRICS[metric]
    sql = text(f"""SELECT phong_code, COUNT(*) AS n FROM {table}
                   WHERE {col} >= :tu AND {col} <= :den{extra}
                   GROUP BY phong_code""")
    return pd.read_sql(sql, engine, params={"tu": tu, "den": den})


def tong_theo_acc(tu: str, den: str, metric: str = "online") -> pd.DataFrame:
    """Tổng số trong khoảng [tu, den] theo từng acc nhân viên."""
    table, col, extra = METRICS[metric]
    sql = text(f"""SELECT f.acc_nhan_vien AS acc, f.acc_norm, f.phong_code, COUNT(*) AS n
                   FROM {table} f
                   WHERE f.{col} >= :tu AND f.{col} <= :den{extra}
                   GROUP BY f.acc_nhan_vien, f.acc_norm, f.phong_code""")
    return pd.read_sql(sql, engine, params={"tu": tu, "den": den})


def so_sanh_ky(ky1: tuple[str, str], ky2: tuple[str, str], metric: str = "online",
               chi_phong: list[str] | None = None) -> pd.DataFrame:
    """Bảng so sánh 2 kỳ theo phòng: kỳ 1, kỳ 2, chênh lệch, %."""
    meta = {p["code"]: p for p in phong_order()}
    a = tong_theo_phong(*ky1, metric).set_index("phong_code")["n"]
    b = tong_theo_phong(*ky2, metric).set_index("phong_code")["n"]
    codes = [c for c in meta if chi_phong is None or c in set(chi_phong)]
    out = pd.DataFrame({"phong_code": codes})
    out["phong"] = [meta[c]["ten"] for c in codes]
    out["bay"] = [ten_bay(meta[c]["bay"]) for c in codes]
    out["ky1"] = [int(a.get(c, 0)) for c in codes]
    out["ky2"] = [int(b.get(c, 0)) for c in codes]
    out["chenh"] = out.ky2 - out.ky1
    out["ty_le"] = (out.chenh / out.ky1.replace(0, np.nan) * 100).round(0)
    return out.sort_values("chenh")


def so_sanh_acc(ky1: tuple[str, str], ky2: tuple[str, str], metric: str = "online",
                chi_phong: list[str] | None = None) -> pd.DataFrame:
    """Khối D2: từng acc nhân viên, kỳ 1 vs kỳ 2, sắp theo mức hụt."""
    meta = {p["code"]: p for p in phong_order()}
    def _gop(df: pd.DataFrame) -> pd.DataFrame:
        # một acc có số ở nhiều phòng -> gộp một dòng, phòng = nơi có nhiều số nhất
        if df.empty:
            return df
        chinh = df.sort_values("n", ascending=False).drop_duplicates("acc_norm")
        return chinh.drop(columns="n").merge(df.groupby("acc_norm", as_index=False).n.sum(), on="acc_norm")
    a = _gop(tong_theo_acc(*ky1, metric))
    b = _gop(tong_theo_acc(*ky2, metric))
    m = a.merge(b, on=["acc_norm"], how="outer", suffixes=("_1", "_2"))
    m["acc"] = m.acc_1.fillna(m.acc_2)
    m["phong_code"] = m.phong_code_2.fillna(m.phong_code_1)
    m["ky1"] = m.n_1.fillna(0).astype(int)
    m["ky2"] = m.n_2.fillna(0).astype(int)
    m["chenh"] = m.ky2 - m.ky1
    m["phong"] = [meta.get(c, {}).get("ten", "Chưa gán phòng") for c in m.phong_code]
    if chi_phong is not None:
        m = m[m.phong_code.isin(set(chi_phong))]
    return m[["acc", "phong", "phong_code", "ky1", "ky2", "chenh"]].sort_values("chenh")


def nhom_khac_theo_ngay(thang: str, metric: str = "online") -> pd.DataFrame:
    """Khối D1: gộp các phòng KT/CUS/ECOM thành DNG Khác và QNM Khác."""
    daily = daily_counts(thang, metric)
    meta = {p["code"]: p for p in phong_order(thang)}
    rows = []
    for nhom, ten in (("DNG", "DNG Khác"), ("QNM", "QNM Khác")):
        codes = [c for c in daily.index if meta.get(c, {}).get("nhom_khac") == nhom]
        if not codes:
            continue
        vals = daily.loc[codes].sum()
        rows.append({"nhom": ten, **{str(c): int(vals[c]) for c in daily.columns},
                     "Tổng": int(vals.sum())})
    return pd.DataFrame(rows)
