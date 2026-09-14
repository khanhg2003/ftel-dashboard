"""Chỉ số nhân sự: nối số bán (luỹ kế đến ngày chọn) với hồ sơ NSLĐ gần nhất.

Quy ước chung với Báo cáo phòng:
- Người thuộc phòng nào lấy theo danh mục acc -> phòng của app.
- "Đang làm" = không ghi Nghỉ việc trong NSLĐ, không ghi "Nghỉ" trong danh mục, và còn hoạt động
  (có NSLĐ, hoặc có số trong 60 ngày, hoặc mới khai vào danh mục).
  Người đã nghỉ mà không còn số trong kỳ thì bỏ khỏi danh sách.
- Mặc định chỉ tính phòng kinh doanh (IBB, địa bàn) - phòng KT/CUS/ECOM không bán hằng ngày
  nên đưa vào sẽ làm sai số bình quân và số "chưa có số".
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sqlalchemy import text

from app import canh_bao
from app.db import engine
from app.metrics import month_range
from app.org import phong_order

LOAI_KINH_DOANH = {"IBB", "DIABAN"}
# thâm niên trong file NSLĐ: 1-6 tháng ghi từng tháng, sau đó gộp 7-12 và 13+
MOC_THAM_NIEN = ["1", "2", "3", "4", "5", "6", "7-12", "13+"]
TEN_NHOM = {"MOI": "Mới", "DANG_LEN": "Đang lên", "ON_DINH": "Ổn định", "LAU_NAM": "Lâu năm"}
TEN_NSLD = {"OK": "Đạt", "NOT OK": "Chưa đạt", "KHONG XET": "Không xét", "KHÔNG XÉT": "Không xét"}
NGAY_KHONG_SO_CAO = 7          # giữ tên cũ; quy tắc cần chú ý dùng chung ở app/canh_bao.py
NGAY_HOAT_DONG = 60            # acc không có số, không có NSLĐ quá chừng này ngày -> không tính
SUT_TUAN = 0.5                 # tuần này giảm từ một nửa so với tuần trước (tuần trước từ 3 số)


def _q(sql: str, **params) -> pd.DataFrame:
    return pd.read_sql(text(sql), engine, params=params)


def hr_thang_gan_nhat(thang: str) -> str | None:
    df = _q("SELECT MAX(thang) t FROM hr_monthly WHERE thang <= :t", t=thang)
    return df.iloc[0, 0]


def ten_tham_nien(bucket) -> str:
    b = "" if bucket is None or pd.isna(bucket) else str(bucket).strip()
    return f"{b} tháng" if b else ""


def _dem(bang: str, cot: str, tu: str, den: str, them: str = "") -> pd.DataFrame:
    return _q(f"""SELECT acc_norm, COUNT(*) AS n, COUNT(DISTINCT {cot}) AS so_ngay FROM {bang}
                  WHERE {cot} >= :tu AND {cot} <= :den{them} GROUP BY acc_norm""",
              tu=tu, den=den).set_index("acc_norm")


def ky_nhan_su(thang: str, ngay: int | None = None) -> tuple[str, str]:
    start, end, _ = month_range(thang)
    den = f"{thang}-{ngay:02d}" if ngay else end.isoformat()
    return start.isoformat(), den


def hieu_suat_nhan_su(thang: str, chi_phong: list[str] | None = None,
                      ngay: int | None = None) -> pd.DataFrame:
    """Một dòng = một nhân sự: số bán luỹ kế 01 -> ngày chọn + hồ sơ NSLĐ gần nhất."""
    tu, den = ky_nhan_su(thang, ngay)
    online = _dem("fact_internet", "ngay_online", tu, den)
    vvip = _dem("fact_fptplay", "ngay_online", tu, den, " AND la_vvip = TRUE")
    cam = _dem("fact_camera", "ngay_online", tu, den)
    ban_moi = _dem("fact_internet", "ngay_tao_hd", tu, den)

    staff = _q("SELECT acc, acc_norm, phong_code, ghi_chu, hieu_luc_tu, hieu_luc_den FROM staff_map")
    hr_thang = hr_thang_gan_nhat(thang)
    hr = pd.DataFrame()
    if hr_thang:
        hr = _q("""SELECT acc, ho_ten, vi_tri, tham_nien_bucket, tham_nien_thang, nhom_tham_nien,
                          trang_thai, dieu_kien, diem_tong, ket_luan
                   FROM hr_monthly WHERE thang = :t""", t=hr_thang)
        hr["acc_norm"] = hr["acc"].fillna("").str.strip().str.lower()
        hr = hr[hr.acc_norm != ""].drop_duplicates("acc_norm").set_index("acc_norm")

    # acc chuyển phòng có nhiều dòng: ưu tiên dòng còn hiệu lực (chưa có ngày kết thúc)
    base = (staff.assign(_het=staff.hieu_luc_den.notna()) if "hieu_luc_den" in staff else staff.assign(_het=False))
    base = base.sort_values("_het")[["acc", "acc_norm", "phong_code", "ghi_chu", "hieu_luc_tu"]].drop_duplicates("acc_norm")
    them = []
    if not hr.empty:                                   # có trong NSLĐ, chưa có trong danh mục
        them.append(pd.DataFrame({"acc": hr.loc[~hr.index.isin(base.acc_norm), "acc"]})
                    .rename_axis("acc_norm").reset_index())
    co_so = set(online.index) | set(vvip.index) | set(cam.index)
    thieu = sorted(co_so - set(base.acc_norm) - (set(hr.index) if not hr.empty else set()))
    if thieu:                                          # có số bán nhưng chưa khai ở đâu cả
        them.append(pd.DataFrame({"acc_norm": thieu, "acc": thieu}))
    base = pd.concat([base, *them], ignore_index=True).set_index("acc_norm")
    # acc không có trong danh mục (hợp đồng gán phòng theo quy tắc: KT, CUS, ECOM...) -> lấy phòng
    # xuất hiện nhiều nhất trong số bán của kỳ, để tổng từng phòng khớp Báo cáo Tổng
    theo_so = _q("""SELECT acc_norm, phong_code, COUNT(*) n FROM (
                        SELECT acc_norm, phong_code FROM fact_internet WHERE ngay_online >= :tu AND ngay_online <= :den
                        UNION ALL SELECT acc_norm, phong_code FROM fact_fptplay
                                  WHERE ngay_online >= :tu AND ngay_online <= :den AND la_vvip = TRUE
                        UNION ALL SELECT acc_norm, phong_code FROM fact_camera WHERE ngay_online >= :tu AND ngay_online <= :den
                    ) x GROUP BY acc_norm, phong_code""", tu=tu, den=den)
    if len(theo_so):
        chinh = theo_so.sort_values("n", ascending=False).drop_duplicates("acc_norm").set_index("acc_norm").phong_code
        base["phong_code"] = base.phong_code.where(base.phong_code.notna(), chinh.reindex(base.index))

    base["online"] = online["n"].reindex(base.index).fillna(0).astype(int)
    base["so_ngay_co_so"] = online["so_ngay"].reindex(base.index).fillna(0).astype(int)
    base["vvip"] = vvip["n"].reindex(base.index).fillna(0).astype(int)
    base["camera"] = cam["n"].reindex(base.index).fillna(0).astype(int)
    base["ban_moi"] = ban_moi["n"].reindex(base.index).fillna(0).astype(int)
    base["ty_le_vvip"] = (base.vvip / base.online.replace(0, np.nan) * 100).round(0)
    base["ty_le_camera"] = (base.camera / base.online.replace(0, np.nan) * 100).round(0)

    cot_hr = ("ho_ten", "vi_tri", "tham_nien_bucket", "tham_nien_thang", "nhom_tham_nien",
              "trang_thai", "dieu_kien", "diem_tong", "ket_luan")
    for c in cot_hr:
        base[c] = hr[c].reindex(base.index) if not hr.empty else None
    base["co_nsld"] = base.ho_ten.notna()
    ten_emp = _q("SELECT acc_norm, ho_ten FROM dim_employee")
    if not ten_emp.empty:
        ten_emp = ten_emp.drop_duplicates("acc_norm").set_index("acc_norm").ho_ten
        base["ho_ten"] = base.ho_ten.fillna(ten_emp.reindex(base.index))
    base["ho_ten"] = base.ho_ten.fillna(base.acc)

    meta = {p["code"]: p for p in phong_order(thang)}
    base["phong"] = [meta[c]["ten"] if c in meta else "Chưa gán phòng" for c in base.phong_code]
    base["kd"] = [meta.get(c, {}).get("loai") in LOAI_KINH_DOANH for c in base.phong_code]
    ten_cn = {"DNG": "Đà Nẵng", "QNM": "Quảng Nam"}

    def _cn(code, acc) -> str:
        ma = meta.get(code, {}).get("chi_nhanh")
        if not ma:                                     # chưa gán phòng: đoán theo tiền tố acc
            ma = str(acc).upper()[:3] if str(acc).upper()[:4] in ("DNG.", "QNM.") else None
        return ten_cn.get(ma, "")

    base["chi_nhanh"] = [_cn(c, a) for c, a in zip(base.phong_code, base.acc)]
    base["tham_nien"] = [ten_tham_nien(b) for b in base.tham_nien_bucket]
    base["nhom"] = base.nhom_tham_nien.map(TEN_NHOM)
    base["nsld"] = [TEN_NSLD.get(str(k).strip().upper(), str(k)) if isinstance(k, str) else None
                    for k in base.ket_luan]
    # acc trong danh mục mà 60 ngày không có số, không có NSLĐ, không phải người mới khai
    # (trưởng phòng, acc cũ, acc phụ) thì không tính là nhân sự bán hàng
    tu_60 = (pd.Timestamp(den) - pd.Timedelta(days=NGAY_HOAT_DONG)).date().isoformat()
    gan_day = set(_q("""SELECT DISTINCT acc_norm FROM fact_internet
                        WHERE ngay_online >= :tu AND ngay_online <= :den""", tu=tu_60, den=den).acc_norm)
    moi_khai = pd.to_datetime(base.hieu_luc_tu, errors="coerce") >= pd.Timestamp(tu_60)
    hoat_dong = base.co_nsld | base.index.isin(gan_day) | moi_khai
    nghi = (base.trang_thai.fillna("").str.contains("Nghỉ việc")
            | base.ghi_chu.fillna("").str.contains("Nghỉ") | ~hoat_dong)
    base["dang_lam"] = ~nghi
    base = base[~nghi | (base.online > 0)]
    base["hr_thang"] = hr_thang

    # so với người cùng mốc thâm niên (trung vị, chỉ tính người đang làm ở phòng kinh doanh)
    so_sanh = base[base.dang_lam & base.kd & base.tham_nien_bucket.notna()]
    trung_vi = so_sanh.groupby("tham_nien_bucket").online.median()
    tv = base.tham_nien_bucket.map(trung_vi)
    base["trung_vi_tham_nien"] = tv
    base["so_voi_tham_nien"] = np.where(base.kd & (tv > 0),
                                        ((base.online / tv - 1) * 100).round(0), np.nan)

    if chi_phong is not None:
        base = base[base.phong_code.isin(set(chi_phong))]
    out = base.drop(columns=["ghi_chu", "hieu_luc_tu"]).reset_index()
    return out.sort_values(["online", "vvip", "camera"], ascending=False).reset_index(drop=True)


def tong_hop_tham_nien(df: pd.DataFrame) -> pd.DataFrame:
    """Online bình quân mỗi người theo mốc thâm niên (người đang làm, có hồ sơ NSLĐ)."""
    d = df[df.dang_lam & df.tham_nien_bucket.notna()]
    if d.empty:
        return pd.DataFrame()
    g = d.groupby("tham_nien_bucket").agg(
        so_nv=("acc", "count"), online=("online", "sum"), trung_vi=("online", "median"),
        chua_co_so=("online", lambda s: int((s == 0).sum())),
        nhom_tham_nien=("nhom_tham_nien", "first"))
    g["tb_online"] = (g.online / g.so_nv).round(1)
    g = g.reindex([m for m in MOC_THAM_NIEN if m in g.index]
                  + [m for m in g.index if m not in MOC_THAM_NIEN])
    return g.rename_axis("tham_nien_bucket").reset_index()


def canh_bao_nhan_su(thang: str, chi_phong=None, ngay: int | None = None,
                     df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Người cần trao đổi sớm, tính tại ngày chọn: lâu không có số, sụt mạnh, NSLĐ chưa đạt."""
    _, den = ky_nhan_su(thang, ngay)
    moc_du_lieu = _q("SELECT MAX(ngay_online) d FROM fact_internet").iloc[0, 0]
    if not moc_du_lieu:
        return pd.DataFrame()
    moc = min(pd.Timestamp(den), pd.Timestamp(str(moc_du_lieu)[:10]))
    t7, t14 = moc - pd.Timedelta(days=6), moc - pd.Timedelta(days=13)
    ban = _q("""SELECT acc_norm, ngay_online FROM fact_internet
                WHERE ngay_online >= :tu AND ngay_online <= :den""",
             tu=(moc - pd.Timedelta(days=27)).date().isoformat(), den=moc.date().isoformat())
    ban["ngay_online"] = pd.to_datetime(ban["ngay_online"])

    nv = df if df is not None else hieu_suat_nhan_su(thang, chi_phong=chi_phong, ngay=ngay)
    # chỉ xét người bán thật: đang làm ở phòng kinh doanh, có hồ sơ NSLĐ hoặc có số trong 4 tuần
    nv = nv[nv.dang_lam & nv.kd & (nv.co_nsld | nv.acc_norm.isin(set(ban.acc_norm)))]
    if nv.empty:
        return pd.DataFrame()
    g7 = ban[ban.ngay_online >= t7].groupby("acc_norm").size()
    g14 = ban[(ban.ngay_online >= t14) & (ban.ngay_online < t7)].groupby("acc_norm").size()
    cuoi = ban.groupby("acc_norm").ngay_online.max()

    out = nv[["acc", "acc_norm", "ho_ten", "phong", "phong_code", "tham_nien", "online",
              "nsld"]].copy()
    out["tuan_nay"] = [int(g7.get(a, 0)) for a in out.acc_norm]
    out["tuan_truoc"] = [int(g14.get(a, 0)) for a in out.acc_norm]
    out["so_ngay_khong_so"] = [int((moc - cuoi[a]).days) if a in cuoi.index else None
                               for a in out.acc_norm]
    thang_nsld = nv.hr_thang.dropna().iloc[0][5:7] if nv.hr_thang.notna().any() else ""

    def _xet(r) -> tuple[str, str]:
        muc, ly_do = canh_bao.xet(r.so_ngay_khong_so, r.tuan_nay, r.tuan_truoc,
                                  nsld_chua_dat=r.nsld == "Chưa đạt", thang_nsld=thang_nsld)
        return muc, " · ".join(ly_do)

    xet = [_xet(r) for r in out.itertuples()]
    out["muc_rui_ro"] = [m for m, _ in xet]
    out["ly_do"] = [l for _, l in xet]
    out = out[out.muc_rui_ro != ""]
    return (out.assign(_o=out.muc_rui_ro.map(canh_bao.THU_TU_MUC),
                       _n=out.so_ngay_khong_so.fillna(99))
            .sort_values(["_o", "_n", "tuan_truoc"], ascending=[True, False, False])
            .drop(columns=["_o", "_n"]).reset_index(drop=True))


def thoi_gian_trien_khai(thang: str) -> pd.DataFrame:
    """Số ngày từ lúc tạo hợp đồng đến lúc online, theo phòng (dùng cho script đối chiếu)."""
    from app.sql_dialect import so_ngay_giua, thang_cua
    df = _q(f"""SELECT p.ten AS phong, {so_ngay_giua("f.ngay_online", "f.ngay_tao_hd")} AS so_ngay
                FROM fact_internet f LEFT JOIN dim_phong p ON p.code = f.phong_code
                WHERE {thang_cua("f.ngay_online")} = :t AND f.ngay_tao_hd IS NOT NULL""", t=thang)
    if df.empty:
        return df
    g = df.groupby("phong").so_ngay.agg(["count", "mean", "median"]).reset_index()
    g.columns = ["phong", "so_hd", "tb_ngay", "trung_vi"]
    g["tb_ngay"] = g.tb_ngay.round(1)
    return g.sort_values("tb_ngay", ascending=False)

