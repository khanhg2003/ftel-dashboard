"""Năng suất lao động (NSLĐ) theo tháng, lấy từ các file NSLĐ đã nạp.

Hai bảng giống báo cáo phòng Nhân sự đang gửi:
1. NSLĐ ITN theo tháng: mỗi phòng mỗi tháng = tổng ITN của người được xét / số người được xét
   (NVKD + CTV, bỏ "Không xét"). Dòng Total = trung bình cộng các phòng.
2. NSLĐ tân binh: tân binh = người có Ngày tính lương trong năm đang xem (cả NVKD và CTV).
   "Tháng k" = ITN bình quân của các tân binh ở tháng làm việc thứ k (tháng vào làm là tháng 1).
   Tỷ lệ out = số đã nghỉ / số tân binh.
Cả hai đều có bản cho từng nhân sự trong phòng.
"""
from __future__ import annotations

import re
from collections import Counter

import numpy as np
import pandas as pd
from sqlalchemy import text

from app.config import rules_config
from app.db import engine
from app.org import phong_order


def _q(sql: str, **params) -> pd.DataFrame:
    return pd.read_sql(text(sql), engine, params=params)


def _cau_hinh() -> dict:
    return rules_config().get("nsld", {}) or {}


def ban_do_phong_ps() -> dict[str, str]:
    """Mã phòng PS -> mã phòng trên app."""
    khai = {str(k).upper(): v for k, v in (_cau_hinh().get("phong_ps") or {}).items()}
    doan = _q("""SELECT h.phong_ps, s.phong_code FROM hr_monthly h
                 JOIN staff_map s ON s.acc_norm = LOWER(TRIM(h.acc))
                 WHERE h.phong_ps IS NOT NULL""")
    ket_qua: dict[str, str] = {}
    for ps, nhom in doan.groupby("phong_ps"):
        ket_qua[str(ps).upper()] = Counter(nhom.phong_code).most_common(1)[0][0]
    ket_qua.update(khai)
    return ket_qua


def cac_thang_nsld() -> list[str]:
    return sorted(_q("SELECT DISTINCT thang FROM hr_monthly").thang.dropna().tolist())


def thang_nsld_den(nam: int, thang: int) -> int | None:
    """Tháng NSLĐ mới nhất đã nạp trong năm, không vượt quá tháng đang xem."""
    co = [int(t[5:7]) for t in cac_thang_nsld() if t[:4] == str(nam) and int(t[5:7]) <= thang]
    return max(co) if co else None


def du_lieu(nam: int, den_thang: int) -> pd.DataFrame:
    """Mọi dòng NSLĐ từ tháng 01 đến `den_thang` của năm, kèm phòng trên app và tháng thâm niên."""
    df = _q("""SELECT h.thang, h.ma_nv, h.acc, h.ho_ten, h.vi_tri, h.phong_ps, h.trang_thai,
                      h.dieu_kien, h.diem_itn, h.diem_tong, h.ket_luan, h.tham_nien_bucket,
                      e.ngay_tinh_luong
               FROM hr_monthly h LEFT JOIN dim_employee e ON e.ma_nv = h.ma_nv
               WHERE h.thang >= :tu AND h.thang <= :den""",
            tu=f"{nam}-01", den=f"{nam}-{den_thang:02d}")
    if df.empty:
        return df
    bd = ban_do_phong_ps()
    ten = {p["code"]: p["ten"] for p in phong_order()}
    df["phong_ps"] = df.phong_ps.fillna("").str.upper()
    df["phong_code"] = df.phong_ps.map(bd).fillna(df.phong_ps)
    df["phong"] = [ten.get(c, c) or "Chưa rõ phòng" for c in df.phong_code]
    df["so_thang"] = df.thang.str[5:7].astype(int)
    vao = pd.to_datetime(df.ngay_tinh_luong, errors="coerce")
    df["ngay_vao"] = vao
    df["thang_lam_viec"] = ((nam * 12 + df.so_thang) - (vao.dt.year * 12 + vao.dt.month) + 1)
    df["tan_binh"] = vao.dt.year == nam
    df["nvkd"] = df.vi_tri.fillna("").str.upper().eq(
        str(_cau_hinh().get("vi_tri_tinh_binh_quan", "NVKD")).upper())
    df["nghi_viec"] = df.trang_thai.fillna("").str.contains("Nghỉ việc")
    return df


def _loc(df: pd.DataFrame, chi_phong: list[str] | None) -> pd.DataFrame:
    return df if chi_phong is None else df[df.phong_code.isin(set(chi_phong))]


def _thu_tu_phong(codes) -> list[str]:
    """Xếp như báo cáo NSLĐ: theo tên phòng, số đứng sau so theo giá trị (IBB2 trước IBB10)."""
    ten = {p["code"]: p["ten"] for p in phong_order()}
    return sorted(codes, key=lambda c: [int(x) if x.isdigit() else x
                                        for x in re.split(r"(\d+)", str(ten.get(c, c)))])


# ------------------------------------------------------------ NSLĐ ITN theo tháng
def _duoc_xet(d: pd.DataFrame) -> pd.Series:
    """Người được xét NSLĐ: cột Điều kiện khác "Không xét" (Xét NSLĐ, Xét 50%), cả NVKD và CTV."""
    dk = d.dieu_kien.fillna("").str.strip().str.lower()
    return ~dk.isin(["không xét", "khong xet"])


def nsld_theo_phong(df: pd.DataFrame, den_thang: int) -> pd.DataFrame:
    """Dòng = phòng, cột t1..tN, tb.

    Đã đối chiếu khớp tuyệt đối 20/21 ô T5-T7/2026 với bảng "Tình hình NSLĐ" phòng Nhân sự gửi:
    - Ô phòng = tổng ITN của người được xét / số người được xét (NVKD + CTV, bỏ "Không xét").
    - Dòng Total = trung bình cộng các phòng trong tháng.
    - TB = trung bình các tháng đã có file.
    """
    thang = list(range(1, den_thang + 1))
    if df.empty:
        return pd.DataFrame()

    def _gia_tri(nhom: pd.DataFrame) -> dict:
        r = {}
        xet = nhom[_duoc_xet(nhom)]
        for t in thang:
            d = xet[xet.so_thang == t]
            r[f"t{t}"] = round(float(d.diem_itn.sum()) / len(d), 2) if len(d) else None
        co = [v for v in r.values() if v is not None]
        r["tb"] = round(float(np.mean(co)), 2) if co else None
        cuoi = nhom[nhom.so_thang == nhom.so_thang.max()]
        r["so_nguoi"] = int(_duoc_xet(cuoi).sum())
        r["so_nvkd"] = int(cuoi.nvkd.sum())
        return r

    rows = [{"phong_code": c, "phong": df[df.phong_code == c].phong.iloc[0], "loai_dong": "data",
             **_gia_tri(df[df.phong_code == c])}
            for c in _thu_tu_phong(df.phong_code.unique())]
    tong = {"phong_code": "TOTAL", "phong": "Total", "loai_dong": "total"}
    for t in thang:
        co = [r[f"t{t}"] for r in rows if r[f"t{t}"] is not None]
        tong[f"t{t}"] = round(float(np.mean(co)), 2) if co else None
    co = [tong[f"t{t}"] for t in thang if tong[f"t{t}"] is not None]
    tong["tb"] = round(float(np.mean(co)), 2) if co else None
    tong["so_nguoi"] = sum(r["so_nguoi"] for r in rows)
    tong["so_nvkd"] = sum(r["so_nvkd"] for r in rows)
    rows.append(tong)
    return pd.DataFrame(rows)


def nsld_nhan_su(df: pd.DataFrame, den_thang: int) -> pd.DataFrame:
    """Dòng = nhân sự, cột t1..tN = ITN tháng đó, tb = bình quân các tháng có số."""
    if df.empty:
        return pd.DataFrame()
    pv = df.pivot_table(index="ma_nv", columns="so_thang", values="diem_itn", aggfunc="first")
    moi_nhat = df.sort_values("thang").groupby("ma_nv").tail(1).set_index("ma_nv")
    out = pd.DataFrame(index=pv.index)
    for t in range(1, den_thang + 1):
        out[f"t{t}"] = pv[t].round(2) if t in pv.columns else None
    out["tb"] = pv.mean(axis=1).round(2)
    for c in ("ho_ten", "acc", "phong", "phong_code", "vi_tri", "trang_thai", "tham_nien_bucket"):
        out[c] = moi_nhat[c].reindex(out.index)
    out["ngay_vao"] = moi_nhat.ngay_vao.reindex(out.index).dt.strftime("%d/%m/%Y")
    out["loai_dong"] = "data"
    thu_tu = {c: i for i, c in enumerate(_thu_tu_phong(out.phong_code.dropna().unique()))}
    out = (out.reset_index().assign(_p=lambda x: x.phong_code.map(thu_tu))
           .sort_values(["_p", "tb"], ascending=[True, False]).drop(columns="_p"))
    return out


# ------------------------------------------------------------------ tân binh
def _tan_binh(df: pd.DataFrame, nam: int) -> pd.DataFrame:
    return df[df.tan_binh & df.thang_lam_viec.between(1, 12)]


def _da_nghi(tb: pd.DataFrame, thang_cuoi: str) -> pd.Series:
    """Theo từng tân binh: đã nghỉ khi lần gần nhất ghi Nghỉ việc, hoặc không còn trong file
    tháng mới nhất đã nạp (người nghỉ thường bị bỏ khỏi file các tháng sau)."""
    cuoi = tb.sort_values("thang").groupby("ma_nv").tail(1).set_index("ma_nv")
    return cuoi.nghi_viec | (cuoi.thang < thang_cuoi)


def tan_binh_theo_phong(df: pd.DataFrame, nam: int, den_thang: int) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    tb = _tan_binh(df, nam)
    if tb.empty:
        return pd.DataFrame()
    thang_cuoi = df.thang.max()
    nghi = _da_nghi(tb, thang_cuoi)
    phong_cua = tb.sort_values("thang").groupby("ma_nv").tail(1).set_index("ma_nv").phong_code

    def _dong(ma_nv: list[str], nhom: pd.DataFrame) -> dict:
        so = len(ma_nv)
        da_nghi = int(nghi.reindex(ma_nv).fillna(False).sum())
        r = {"so_moi": so, "da_nghi": da_nghi, "con_lai": so - da_nghi,
             "ty_le_out": round(da_nghi / so * 100) if so else None}
        co = []
        for k in range(1, den_thang + 1):
            v = nhom[nhom.thang_lam_viec == k].diem_itn.dropna()
            r[f"k{k}"] = round(float(v.mean()), 1) if len(v) else None
            if len(v):
                co.append(r[f"k{k}"])
        r["tb"] = round(float(np.mean(co)), 1) if co else None
        return r

    rows = []
    for c in _thu_tu_phong(phong_cua.unique()):
        ds = phong_cua[phong_cua == c].index.tolist()
        nhom = tb[tb.ma_nv.isin(ds)]
        rows.append({"phong_code": c, "phong": nhom.phong.iloc[-1], "loai_dong": "data",
                     **_dong(ds, nhom)})
    rows.append({"phong_code": "TOTAL", "phong": "Total", "loai_dong": "total",
                 **_dong(phong_cua.index.tolist(), tb)})
    return pd.DataFrame(rows)


def tan_binh_nhan_su(df: pd.DataFrame, nam: int, den_thang: int) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    tb = _tan_binh(df, nam)
    if tb.empty:
        return pd.DataFrame()
    nghi = _da_nghi(tb, df.thang.max())
    pv = tb.pivot_table(index="ma_nv", columns="thang_lam_viec", values="diem_itn", aggfunc="first")
    cuoi = tb.sort_values("thang").groupby("ma_nv").tail(1).set_index("ma_nv")
    out = pd.DataFrame(index=pv.index)
    for k in range(1, den_thang + 1):
        out[f"k{k}"] = pv[k].round(1) if k in pv.columns else None
    out["tb"] = pv.mean(axis=1).round(1)
    for c in ("ho_ten", "acc", "phong", "phong_code", "vi_tri"):
        out[c] = cuoi[c].reindex(out.index)
    out["ngay_vao"] = cuoi.ngay_vao.reindex(out.index).dt.strftime("%d/%m/%Y")
    out["thang_lam_viec"] = cuoi.thang_lam_viec.reindex(out.index)
    out["tinh_trang"] = np.where(nghi.reindex(out.index).fillna(False), "Đã nghỉ", "Đang làm")
    out["loai_dong"] = "data"
    thu_tu = {c: i for i, c in enumerate(_thu_tu_phong(out.phong_code.dropna().unique()))}
    return (out.reset_index().assign(_p=lambda x: x.phong_code.map(thu_tu))
            .sort_values(["_p", "tinh_trang", "tb"], ascending=[True, False, False])
            .drop(columns="_p"))


def tom_tat(df: pd.DataFrame, nam: int, den_thang: int) -> dict:
    """Số cho các ô chỉ số của tab NSLĐ (theo phạm vi đã lọc)."""
    if df.empty:
        return {}
    thang_cuoi = int(df.so_thang.max())
    phong = nsld_theo_phong(df, den_thang)
    tong = phong[phong.loai_dong == "total"].iloc[0]
    cuoi = df[df.so_thang == thang_cuoi]
    truoc = tong.get(f"t{thang_cuoi - 1}") if thang_cuoi > 1 else None
    tb = _tan_binh(df, nam)
    nghi = _da_nghi(tb, df.thang.max()) if len(tb) else pd.Series(dtype=bool)
    return {
        "thang_cuoi": thang_cuoi,
        "nsld": tong.get(f"t{thang_cuoi}"), "nsld_truoc": truoc, "nsld_tb": tong.get("tb"),
        "so_nvkd": int(cuoi.nvkd.sum()), "so_nguoi": int(_duoc_xet(cuoi).sum()),
        "chua_dat": int(cuoi.ket_luan.fillna("").str.upper().eq("NOT OK").sum()),
        "tan_binh": int(tb.ma_nv.nunique()), "tan_binh_nghi": int(nghi.sum()),
    }
