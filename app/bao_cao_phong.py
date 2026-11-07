"""Báo cáo phòng: kết quả của một phòng, vị trí so với các phòng khác, và từng nhân sự trong phòng.

Kỳ giống Báo cáo Tổng: luỹ kế từ ngày 01 đến ngày được chọn, cột "ngày" là riêng ngày đó.
Nhân sự thuộc phòng theo danh mục acc -> phòng của app (cùng nguồn với Báo cáo Tổng) nên
tổng số của các nhân sự luôn bằng số của phòng trên Báo cáo Tổng.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import text

from app import canh_bao as cb
from app import mttn
from app import phan_tich as pt
from app.db import engine
from app.metrics import daily_counts, prev_month
from app.org import phong_order
from app.overview import bang_tong_quan

NHOM_KINH_DOANH = {"IBB", "DIABAN"}      # các phòng bán hàng trực tiếp được xếp hạng với nhau
NGAY_LIEN_CANH_BAO = cb.NGAY_THEO_DOI    # quy tắc cần chú ý dùng chung: app/canh_bao.py
TON_LAU_CANH_BAO = 3                    # từ 3 hợp đồng chờ online từ 7 ngày thì nhắc


def _q(sql: str, **params) -> pd.DataFrame:
    return pd.read_sql_query(text(sql), engine, params=params)


def _dem_theo_acc(bang: str, cot: str, tu: str, den: str, code: str, them: str = "") -> pd.Series:
    df = _q(f"""SELECT acc_norm, COUNT(*) AS n FROM {bang}
                WHERE phong_code = :code AND {cot} >= :tu AND {cot} <= :den{them}
                GROUP BY acc_norm""", code=code, tu=tu, den=den)
    return df.set_index("acc_norm")["n"] if not df.empty else pd.Series(dtype=int)


def phong_cung_nhom(code: str, thang: str) -> list[str]:
    """Các phòng dùng để so sánh, xếp hạng: phòng kinh doanh so với phòng kinh doanh (IBB và địa bàn),
    phòng KT/CUS/ECOM so với phòng cùng loại."""
    ds = phong_order(thang)
    loai = next((p["loai"] for p in ds if p["code"] == code), None)
    nhom = NHOM_KINH_DOANH if loai in NHOM_KINH_DOANH else {loai}
    return [p["code"] for p in ds if p["loai"] in nhom]


# ------------------------------------------------------------------ nhân sự
def bang_nhan_su(thang: str, ngay: int, code: str, acc: list[str] | None = None) -> pd.DataFrame:
    """Một dòng = một nhân sự của phòng, kèm dòng TỔNG PHÒNG ở cuối.

    `acc` (danh sách acc_norm) chỉ giữ một nhóm nhân sự của phòng đó (Phòng Online gom 5 người của IBB2):
    hạng, TỔNG và mọi tỷ lệ tính lại trong riêng nhóm, các cột còn lại tính y hệt phòng thường.
    """
    tu, den = f"{thang}-01", f"{thang}-{ngay:02d}"
    d_den = date.fromisoformat(den)

    hd = pt.hop_dong_online(tu, den, [code])
    ton = pt.hop_dong_ton([code])
    if acc is not None:
        giu = set(acc)
        hd, ton = hd[hd.acc_norm.isin(giu)], ton[ton.acc_norm.isin(giu)]

    # chỉ dòng danh mục có hiệu lực trong kỳ (người đã chuyển phòng không còn hiện ở phòng cũ)
    staff = _q("""SELECT acc, acc_norm, ghi_chu, ten_hien_thi, hieu_luc_den FROM staff_map WHERE phong_code = :c
                  AND (hieu_luc_den IS NULL OR hieu_luc_den >= :tu) AND (hieu_luc_tu IS NULL OR hieu_luc_tu <= :den)""",
               c=code, tu=tu, den=den)
    vvip = _dem_theo_acc("fact_fptplay", "ngay_online", tu, den, code, " AND la_vvip = TRUE")
    camera = _dem_theo_acc("fact_camera", "ngay_online", tu, den, code)
    ban_moi = _dem_theo_acc("fact_internet", "ngay_tao_hd", tu, den, code)
    if acc is not None:
        staff = staff[staff.acc_norm.isin(giu)]
        vvip, camera, ban_moi = (s[s.index.isin(giu)] for s in (vvip, camera, ban_moi))
    # người chỉ bán V.VIP / Camera / hợp đồng mới (chưa có online) cũng phải có dòng,
    # nếu không dòng TỔNG PHÒNG sẽ thiếu so với Báo cáo Tổng
    ban_ra = set(hd.acc_norm) | set(ton.acc_norm) | set(vvip.index) | set(camera.index) | set(ban_moi.index)
    ds_acc = pd.DataFrame({"acc_norm": sorted(set(staff.acc_norm) | ban_ra)})
    phu = _q("""SELECT DISTINCT acc_norm, acc_nhan_vien FROM fact_camera WHERE phong_code = :c
                  AND ngay_online >= :tu AND ngay_online <= :den
                  UNION SELECT DISTINCT acc_norm, acc_nhan_vien FROM fact_fptplay WHERE phong_code = :c
                  AND ngay_online >= :tu AND ngay_online <= :den""", c=code, tu=tu, den=den)
    ten_acc = {**dict(zip(phu.acc_norm, phu.acc_nhan_vien)),
               **dict(zip(hd.acc_norm, hd.acc_nhan_vien)), **dict(zip(ton.acc_norm, ton.acc_nhan_vien)),
               **dict(zip(staff.acc_norm, staff.acc))}
    ds_acc["acc"] = ds_acc.acc_norm.map(ten_acc)
    ds_acc = ds_acc.set_index("acc_norm")

    # --- số bán trong kỳ
    g = hd.groupby("acc_norm")
    out = ds_acc.copy()
    out["online"] = g.size().reindex(out.index).fillna(0).astype(int)
    for cot, co in (("du_3", "du_3"), ("tra_truoc", "co_tra_truoc"), ("onl_1_ngay", "onl_nhanh")):
        out[cot] = (g[co].mean() * 100).round(0).reindex(out.index)
    out["online_ngay"] = (hd[hd.ngay_online.dt.date == d_den].groupby("acc_norm").size()
                          .reindex(out.index).fillna(0).astype(int))
    out["so_ngay_co_so"] = g.ngay_online.nunique().reindex(out.index).fillna(0).astype(int)
    out["vvip"] = vvip.reindex(out.index).fillna(0).astype(int)
    out["camera"] = camera.reindex(out.index).fillna(0).astype(int)
    # cùng cách tính với cột "Tỷ lệ VVIP/PTTB" của Báo cáo Tổng: số V.VIP (Camera) / số online
    out["kem_vvip"] = (out.vvip / out.online.replace(0, np.nan) * 100).round(0)
    out["kem_camera"] = (out.camera / out.online.replace(0, np.nan) * 100).round(0)
    out["ban_moi"] = ban_moi.reindex(out.index).fillna(0).astype(int)
    out["ban_moi_ngay"] = _dem_theo_acc("fact_internet", "ngay_tao_hd", den, den, code
                                        ).reindex(out.index).fillna(0).astype(int)
    if mttn.ap_dung(code):                    # số online có khách ở tỉnh MTTN (chỉ phòng áp dụng)
        out["mttn"] = (hd[mttn.la_mttn(hd.cn_quan_ly)].groupby("acc_norm").size()
                       .reindex(out.index).fillna(0).astype(int))
        out["ty_le_mttn"] = (out.mttn / out.online.replace(0, np.nan) * 100).round(0)

    # --- cùng kỳ tháng trước (theo acc, dù khi đó ở phòng nào)
    tu_t, den_t = pt.cung_ky_thang_truoc(thang, ngay)
    acc_list = list(out.index)
    lich_su = _q("""SELECT acc_norm, ngay_online FROM fact_internet
                    WHERE ngay_online >= :tu AND ngay_online <= :den""",
                 tu=(d_den - timedelta(days=62)).isoformat(), den=den)
    lich_su = lich_su[lich_su.acc_norm.isin(acc_list)].copy()
    lich_su["ngay_online"] = pd.to_datetime(lich_su.ngay_online)
    ck = lich_su[(lich_su.ngay_online >= tu_t) & (lich_su.ngay_online <= den_t)]
    out["ck_online"] = ck.groupby("acc_norm").size().reindex(out.index).fillna(0).astype(int)
    t0 = pd.Timestamp(d_den - timedelta(days=6))
    t1 = pd.Timestamp(d_den - timedelta(days=13))
    out["tuan_nay"] = (lich_su[lich_su.ngay_online >= t0].groupby("acc_norm").size()
                       .reindex(out.index).fillna(0).astype(int))
    out["tuan_truoc"] = (lich_su[(lich_su.ngay_online >= t1) & (lich_su.ngay_online < t0)]
                         .groupby("acc_norm").size().reindex(out.index).fillna(0).astype(int))
    cuoi = lich_su.groupby("acc_norm").ngay_online.max()
    out["ngay_lien_chua_co_so"] = [
        int((pd.Timestamp(d_den) - cuoi[a]).days) if a in cuoi.index else None for a in out.index]

    # --- số tồn
    if len(ton):
        gt = ton.groupby("acc_norm")
        out["ton"] = gt.size().reindex(out.index).fillna(0).astype(int)
        out["ton_qua_7"] = (ton[ton.so_ngay_cho >= 7].groupby("acc_norm").size()
                            .reindex(out.index).fillna(0).astype(int))
    else:
        out["ton"] = out["ton_qua_7"] = 0

    # --- hồ sơ NSLĐ gần nhất
    hr = _q("""SELECT h.acc, h.ho_ten, h.vi_tri, h.tham_nien_bucket, h.nhom_tham_nien,
                      h.trang_thai, h.diem_tong, h.ket_luan, h.thang
               FROM hr_monthly h
               WHERE h.thang = (SELECT MAX(thang) FROM hr_monthly WHERE thang <= :t)""", t=thang)
    if not hr.empty:
        hr["acc_norm"] = hr.acc.fillna("").str.strip().str.lower()
        hr = hr.drop_duplicates("acc_norm").set_index("acc_norm")
    for c in ("ho_ten", "vi_tri", "tham_nien_bucket", "nhom_tham_nien", "trang_thai", "diem_tong",
              "ket_luan"):
        out[c] = hr[c].reindex(out.index) if not hr.empty else None
    out["thang_nsld"] = hr.thang.reindex(out.index) if not hr.empty else None
    ten_emp = _q("SELECT acc_norm, ho_ten FROM dim_employee")
    if not ten_emp.empty:
        ten_emp = ten_emp.drop_duplicates("acc_norm").set_index("acc_norm").ho_ten
        out["ho_ten"] = out.ho_ten.fillna(ten_emp.reindex(out.index))
    # chưa có trong NSLĐ thì dùng tên hiển thị tạm đặt trong danh mục, cuối cùng mới acc
    ten_tam = staff.set_index("acc_norm").ten_hien_thi.replace("", None)
    out["ho_ten"] = out.ho_ten.fillna(ten_tam.reindex(out.index))
    out["ho_ten"] = out.ho_ten.fillna(out.acc)

    # người đã nghỉ HẲN (không có hiệu_lực_đến - không rõ ngày quay lại) và không còn số, không còn tồn
    # thì bỏ khỏi danh sách. Nghỉ TẠM có ngày dự kiến quay lại (vd thai sản, hieu_luc_den có giá trị) vẫn
    # tính là nhân sự của phòng, chỉ không vào Báo cáo ngày trong lúc nghỉ (chủ app chốt 02/10/2026).
    nghi_han = staff[(staff.ghi_chu.fillna("").str.contains("Nghỉ") & staff.hieu_luc_den.isna())
                     | staff.ghi_chu.map(cb.la_acc_tam)].acc_norm      # "Acc tạm" cũng không phải nhân sự phòng
    nghi = (out.trang_thai.fillna("").str.contains("Nghỉ việc") | out.index.isin(nghi_han))
    out = out[~nghi | (out.online + out.ton + out.vvip + out.camera + out.ban_moi > 0)].copy()

    out["chenh_ck"] = out.online - out.ck_online
    out = out.sort_values(["online", "vvip", "camera"], ascending=False)
    out["khong_xet"] = out.index.map(cb.acc_khong_xet(out.index)).fillna("")    # đã nghỉ / trưởng phòng: không cảnh báo
    la_tp = out.khong_xet == "Trưởng phòng"               # trưởng phòng: số vẫn cộng cho phòng, không xếp hạng
    out["hang"] = out.online.where(~la_tp).rank(method="min", ascending=False)
    out = pd.concat([out[~la_tp], out[la_tp]])                # trưởng phòng xuống cuối bảng
    xet = [_chu_y(r) for r in out.itertuples()]
    out["muc_chu_y"] = [("" if kx else m) for (m, _), kx in zip(xet, out.khong_xet)]
    out["chu_y"] = [("" if kx else y) for (_, y), kx in zip(xet, out.khong_xet)]
    out["loai_dong"] = "data"
    out = out.reset_index()

    tong = _dong_tong(out, hd, ton)
    kq = pd.concat([out, pd.DataFrame([tong])], ignore_index=True).astype(object)
    for c in ("hang", "ngay_lien_chua_co_so"):
        kq[c] = [None if v is None or pd.isna(v) else int(v) for v in kq[c]]
    return kq.replace({np.nan: None})


def _chu_y(r) -> tuple[str, str]:
    """(mức theo quy tắc chung, lý do). Tồn lâu / chưa bán kèm chỉ là lưu ý, không nâng mức."""
    muc, y = cb.xet(r.ngay_lien_chua_co_so, r.tuan_nay, r.tuan_truoc,
                    nsld_chua_dat=r.ket_luan == "NOT OK", thang_nsld=_thang_nsld(r.thang_nsld),
                    khong_co_so="Chưa có số online trong 2 tháng")
    if r.ton_qua_7 >= TON_LAU_CANH_BAO:
        y.append(f"{r.ton_qua_7} HĐ chờ online từ 7 ngày")
    if r.online >= 3 and r.vvip == 0:
        y.append("Chưa bán kèm V.VIP")
    if r.online >= 3 and r.camera == 0:
        y.append("Chưa bán kèm Camera")
    return muc, " · ".join(y)


def _thang_nsld(t) -> str:
    return str(t)[5:7] if isinstance(t, str) and len(t) >= 7 else ""


def _dong_tong(out: pd.DataFrame, hd: pd.DataFrame, ton: pd.DataFrame) -> dict:
    c = pt.chi_so_chung(hd)
    nv = out[out.khong_xet != "Trưởng phòng"]            # bình quân / người không tính trưởng phòng
    so_cot = ["online", "online_ngay", "vvip", "camera", "ban_moi", "ban_moi_ngay", "ck_online",
              "tuan_nay", "tuan_truoc", "ton", "ton_qua_7", "chenh_ck"]
    so_cot += ["mttn"] if "mttn" in out.columns else []
    tong = {k: int(out[k].sum()) for k in so_cot}
    ty_le = (lambda a: round(a / tong["online"] * 100, 0) if tong["online"] else None)
    if "mttn" in out.columns:
        tong["ty_le_mttn"] = ty_le(tong["mttn"])
    tong.update(acc_norm="TOTAL", acc="", ho_ten="TỔNG PHÒNG", loai_dong="total", hang=None, muc_chu_y="",
                khong_xet="",
                kem_vvip=ty_le(tong["vvip"]), kem_camera=ty_le(tong["camera"]), du_3=c["du_3"],
                tra_truoc=c["tra_truoc"], onl_1_ngay=c["onl_1_ngay"],
                so_ngay_co_so=int(hd.ngay_online.nunique()) if len(hd) else 0,
                chu_y=f"{len(nv)} nhân sự · bình quân {nv.online.sum() / len(nv):.1f} online/người"
                if len(nv) else "")
    return tong


# ------------------------------------------------------------------ phòng
CHI_SO_PHONG = [
    # (khoá, nhãn, nguồn, cao là tốt, kiểu, cách tính mức chung)
    ("online", "Số online tháng", "tq", True, "so", "tb_phong"),
    ("htkh_internet", "Tỷ lệ HTKH Internet", "tq", True, "pct", "tong"),
    ("tang_truong", "Tăng trưởng so cùng kỳ", "tq", True, "pct", "tong"),
    ("online_nguoi", "Online bình quân / nhân sự", "tq", True, "so1", "tong"),
    ("vvip_ty_le", "Tỷ lệ VVIP/PTTB", "tq", True, "pct", "tong"),
    ("htkh_camera", "Tỷ lệ HTKH Camera", "tq", True, "pct", "tong"),
    ("kem_camera", "Hợp đồng có kèm Camera", "pt", True, "pct", "tong"),
    ("du_3", "Đủ 3 dịch vụ", "pt", True, "pct", "tong"),
    ("tra_truoc", "Trả trước", "pt", True, "pct", "tong"),
    ("onl_1_ngay", "Online trong 1 ngày", "pt", True, "pct", "tong"),
    ("ton_qua_7", "Hợp đồng chờ online từ 7 ngày", "pt", False, "so", "tb_phong"),
]


def so_sanh_phong(thang: str, ngay: int, code: str,
                  tam_tinh: bool = False) -> tuple[pd.DataFrame, dict]:
    """(bảng vị trí của phòng theo từng chỉ số, dòng Báo cáo Tổng của phòng)."""
    tq, _ = bang_tong_quan(thang, ngay, tam_tinh=tam_tinh)
    tq = tq.copy()
    tq["online_nguoi"] = (tq.online / tq.nhan_su.replace(0, np.nan)).round(1)
    du_lieu = tq[tq.loai_dong == "data"].set_index("phong_code")
    tong_tq = tq[tq.loai_dong == "total"].iloc[0]

    tu, den = f"{thang}-01", f"{thang}-{ngay:02d}"
    ptb = pt.bang_theo_phong(pt.hop_dong_online(tu, den), pt.hop_dong_ton(), thang)
    du_lieu_pt = ptb[ptb.loai_dong == "data"].set_index("phong_code")
    tong_pt = ptb[ptb.loai_dong == "total"].iloc[0]

    nhom = [c for c in phong_cung_nhom(code, thang) if c in du_lieu.index]
    rows = []
    for khoa, nhan, nguon, cao_tot, kieu, cach in CHI_SO_PHONG:
        bang, tong = (du_lieu, tong_tq) if nguon == "tq" else (du_lieu_pt, tong_pt)
        cot = bang[khoa].reindex(nhom).astype(float) if khoa in bang.columns else pd.Series(dtype=float)
        v = cot.get(code) if code in cot.index else None
        v = None if v is None or pd.isna(v) else float(v)
        if khoa == "online_nguoi":
            nv_nhom = du_lieu.nhan_su.reindex(nhom).sum()
            chung = round(du_lieu.online.reindex(nhom).sum() / nv_nhom, 1) if nv_nhom else None
        elif cach == "tb_phong":
            chung = round(float(cot.mean()), 1) if cot.notna().any() else None
        else:
            chung = tong.get(khoa)
            chung = None if chung is None or pd.isna(chung) else float(chung)
        hop_le = cot.dropna()
        hang = (int((hop_le > v).sum() + 1) if cao_tot else int((hop_le < v).sum() + 1)) \
            if v is not None and len(hop_le) else None
        rows.append({"khoa": khoa, "chi_so": nhan, "gia_tri": v, "muc_chung": chung,
                     "chenh": None if v is None or chung is None else round(v - chung, 1),
                     "hang": hang, "so_phong": len(hop_le), "cao_la_tot": cao_tot, "kieu": kieu,
                     "cach": cach})
    dong = du_lieu.loc[code].to_dict() if code in du_lieu.index else {}
    dong["phong_code"] = code
    return pd.DataFrame(rows), dong


def dien_bien_ngay(thang: str, ngay: int, code: str) -> pd.DataFrame:
    """Online và bán mới (hợp đồng tạo mới) từng ngày của phòng."""
    ngays = list(range(1, ngay + 1))
    out = pd.DataFrame({"ngay": ngays})
    for metric in ("online", "ban_moi"):
        d = daily_counts(thang, metric)
        out[metric] = [int(d.at[code, c]) if code in d.index and c in d.columns else 0 for c in ngays]
    return out


def dien_bien_nhan_su(thang: str, ngay: int, acc_norm: str) -> pd.DataFrame:
    """Online và bán mới từng ngày của một nhân sự trong tháng."""
    tu, den = f"{thang}-01", f"{thang}-{ngay:02d}"
    out = pd.DataFrame({"ngay": list(range(1, ngay + 1))})
    for ten, cot in (("online", "ngay_online"), ("ban_moi", "ngay_tao_hd")):
        df = _q(f"""SELECT {cot} AS d, COUNT(*) AS n FROM fact_internet
                    WHERE acc_norm = :a AND {cot} >= :tu AND {cot} <= :den
                    GROUP BY {cot}""", a=acc_norm, tu=tu, den=den)
        dem = {pd.Timestamp(str(x)[:10]).day: int(n) for x, n in zip(df.d, df.n)}
        out[ten] = [dem.get(i, 0) for i in out.ngay]
    return out


def hop_dong_cho_cua_nhan_su(acc_norm: str, code: str) -> pd.DataFrame:
    ton = pt.hop_dong_ton([code])
    ton = ton[ton.acc_norm == acc_norm].sort_values("so_ngay_cho", ascending=False).copy()
    ton["ngay_tao"] = ton.ngay_tao_hd.dt.strftime("%d/%m/%Y")
    return ton[["hop_dong", "goi_dich_vu", "nguon_ban", "ngay_tao", "so_ngay_cho"]]


def ten_phong(code: str) -> str:
    return next((p["ten"] for p in phong_order() if p["code"] == code), code)


def thang_truoc_nhan(thang: str) -> str:
    return f"T{int(prev_month(thang)[5:7])}"
