"""Nơi DUY NHẤT quyết định số liệu của hướng liên khối lấy từ đâu (nhánh thi-lien-khoi).

- Mặc định ("that"): đọc dữ liệu thật của app (chỉ ĐỌC, không ghi); khối Kỹ thuật chưa có bảng nên rỗng.
- Đặt biến môi trường `LIEN_KHOI_NGUON=demo`: đọc bộ dữ liệu MINH HOẠ đã ghép mã trong `demo/lien_khoi/*.csv` (không chạm database).
  Bộ này do `scripts/dung_demo_lien_khoi.py` dựng: mã hợp đồng, tên người, ngày tháng đều là giả định, không có tên khách hàng.
Các module khác của hướng liên khối chỉ gọi hàm ở đây, không tự đọc database hay file.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from app.bo_nho import nho
from app.config import BASE_DIR
from app.db import engine
from app.dvkh import nap, so_lieu
from app.metrics import dieu_kien_ton

THU_MUC_DEMO = Path(BASE_DIR) / "demo" / "lien_khoi"
COT_KD = ["so_hd", "ngay_tao", "ngay_online", "ngay_huy", "sale", "phong", "goi", "tinh_trang", "ton"]
COT_KT = ["so_hd", "loai", "thoi_diem", "chi_tiet", "nguoi", "so_lan", "thuoc_tinh"]
COT_KD_THEM = ["cuoc_thang", "hinh_thuc_tt", "so_thang_tra_truoc", "so_tien_tra_truoc", "tien_hoa_mang", "chinh_sach", "doi_tuong", "nguon_ban", "cn_quan_ly"]
COT_DICH_VU = ["so_hd", "nhom", "ten", "so_luong", "don_gia", "vvip"]


def che_do() -> str:
    return "demo" if os.getenv("LIEN_KHOI_NGUON", "").strip().lower() == "demo" else "that"


def la_demo() -> bool:
    return che_do() == "demo"


def _csv(ten: str, ngay: list[str] | None = None) -> pd.DataFrame:
    p = THU_MUC_DEMO / f"{ten}.csv"
    if not p.exists():
        raise FileNotFoundError(f"Chưa có bộ dữ liệu minh hoạ ({p.name}). Chạy: python scripts/dung_demo_lien_khoi.py")
    return pd.read_csv(p, dtype=str, keep_default_na=False, parse_dates=ngay or [])


def meta() -> dict:
    p = THU_MUC_DEMO / "meta.json"
    return json.loads(p.read_text(encoding="utf-8")) if la_demo() and p.exists() else {}


def ngay_tham_chieu() -> pd.Timestamp | None:
    """Ngày "hôm nay" của bộ minh hoạ (dữ liệu thật thì để các luật tự suy từ ngày có số)."""
    d = meta().get("ngay_tc")
    return pd.Timestamp(d) if d else None


# ------------------------------------------------------------------ Kinh doanh
@nho("so_lieu", 60)
def _kd_that() -> pd.DataFrame:
    """Hợp đồng Internet của khối Kinh doanh (không lấy tên khách). `ton` = đúng định nghĩa "Số tồn" của app: chưa online và còn trong file mới nhất."""
    df = pd.read_sql_query(text("""SELECT hop_dong, ngay_tao_hd, ngay_online, ngay_huy, acc_nhan_vien, phong_code, goi_dich_vu, tinh_trang,
                                   arpu_tra_sau, arpu_tra_truoc, hinh_thuc_tt, so_thang_tra_truoc, so_tien_tra_truoc, tien_hoa_mang,
                                   chinh_sach_ban, doi_tuong_kh, nguon_ban, cn_quan_ly FROM fact_internet"""), engine,
                           parse_dates=["ngay_tao_hd", "ngay_online", "ngay_huy"])
    df["cuoc_thang"] = pd.to_numeric(df["arpu_tra_sau"], errors="coerce").where(lambda x: x > 0, pd.to_numeric(df["arpu_tra_truoc"], errors="coerce"))
    df = df.rename(columns={"chinh_sach_ban": "chinh_sach", "doi_tuong_kh": "doi_tuong"}).drop(columns=["arpu_tra_sau", "arpu_tra_truoc"])
    dk, tham_so = dieu_kien_ton()
    ton = pd.read_sql_query(text(f"SELECT hop_dong FROM fact_internet WHERE {dk}"), engine, params=tham_so)
    df = df.rename(columns={"ngay_tao_hd": "ngay_tao", "acc_nhan_vien": "sale", "phong_code": "phong", "goi_dich_vu": "goi"})
    df["so_hd"] = _chuan(df.pop("hop_dong"))
    df["sale"] = df["sale"].fillna("")
    df["ton"] = df["so_hd"].isin(set(_chuan(ton["hop_dong"])))
    return df


def _chuan(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str).str.strip().str.upper()


def kd() -> pd.DataFrame:
    if not la_demo():
        return _kd_that()
    d = _csv("kd", ["ngay_tao", "ngay_online", "ngay_huy"])
    d["ton"] = d["ton"].eq("1")
    return d[COT_KD + [c for c in COT_KD_THEM if c in d.columns]]


# ------------------------------------------------------------------ DVKH
def sr_bi_dong() -> pd.DataFrame:
    if not la_demo():
        return so_lieu.sr_bi_dong()
    return _csv("sr_bi_dong", ["tg_yc"])


def sr_chu_dong() -> pd.DataFrame:
    if not la_demo():
        return so_lieu.sr_chu_dong()
    d = _csv("sr_chu_dong", ["tg_do"])
    d["diem_rm"] = pd.to_numeric(d["diem_rm"], errors="coerce")
    d["no_cuoc"] = pd.to_numeric(d["no_cuoc"], errors="coerce").fillna(0).astype(int)
    return d


@nho("dvkh", 60)
def _danh_sach_that() -> pd.DataFrame:
    if not nap.co_bang("dv_danh_sach"):
        return pd.DataFrame(columns=["loai", "so_hd", "ngay_chot"])
    return pd.read_sql_query(text("SELECT loai, so_hd, ngay_chot FROM dv_danh_sach"), engine)


def danh_sach_dvkh() -> pd.DataFrame:
    """Hợp đồng nợ cước / YCH trong file DVKH (chỉ có mã hợp đồng và ngày chốt, không có tên người phụ trách)."""
    return _csv("no_cuoc") if la_demo() else _danh_sach_that()


@nho("so_lieu", 60)
def _dich_vu_that() -> pd.DataFrame:
    """Dịch vụ kèm theo hợp đồng: FPT Play (có cờ V.VIP) và Camera. Chỉ lấy tên gói và giá, không có tên khách."""
    fpl = pd.read_sql_query(text("SELECT hop_dong, goi_fpt_play, la_vvip, loai_box, gia_box FROM fact_fptplay"), engine)
    cam = pd.read_sql_query(text("SELECT hop_dong, ten_goi_cloud, so_luong_cloud, gia_cuoc_cloud FROM fact_camera"), engine)
    a = pd.DataFrame({"so_hd": _chuan(fpl["hop_dong"]), "nhom": "FPT Play", "ten": fpl["goi_fpt_play"].fillna("").astype(str).str.cat(fpl["loai_box"].fillna("").astype(str), sep=" ").str.strip(),
                      "so_luong": "1", "don_gia": pd.to_numeric(fpl["gia_box"], errors="coerce"), "vvip": fpl["la_vvip"].fillna(0).astype(int).astype(str)})
    b = pd.DataFrame({"so_hd": _chuan(cam["hop_dong"]), "nhom": "Camera", "ten": cam["ten_goi_cloud"].fillna("").astype(str),
                      "so_luong": pd.to_numeric(cam["so_luong_cloud"], errors="coerce").fillna(1).astype(int).astype(str),
                      "don_gia": pd.to_numeric(cam["gia_cuoc_cloud"], errors="coerce"), "vvip": "0"})
    return pd.concat([a, b], ignore_index=True)


def dich_vu_kem() -> pd.DataFrame:
    if not la_demo():
        return _dich_vu_that()
    d = _csv("dich_vu")
    d["don_gia"] = pd.to_numeric(d["don_gia"], errors="coerce")
    return d[COT_DICH_VU]


def nguoi_nhan() -> pd.DataFrame:
    """Danh sách người nhận việc của bộ minh hoạ (mã, tên, khối, vai trò, quản lý, mã chat giả). Dữ liệu thật: bảng `nguoi_nhan` ở file trạng thái (`theo_doi.py`)."""
    if not la_demo():
        from app.lien_khoi import theo_doi
        return theo_doi.nguoi_nhan_that()
    return _csv("nguoi_nhan")


# ------------------------------------------------------------------ Kỹ thuật
def kt() -> pd.DataFrame:
    """Sự kiện của khối Kỹ thuật (`COT_KT`). Dữ liệu thật: chưa có bảng nên rỗng. Khi có, đọc ở đây (bộ đọc file nằm ở `doc_kt.py`)."""
    if not la_demo():
        return pd.DataFrame(columns=COT_KT)
    d = _csv("kt", ["thoi_diem"])
    d["so_lan"] = pd.to_numeric(d["so_lan"], errors="coerce")
    return d[COT_KT]
