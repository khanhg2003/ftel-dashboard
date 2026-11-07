"""Phòng Online: nhóm nhân sự của IBB2 được gom vào một bảng riêng để BGĐ theo dõi (chốt 07/11/2026).

Nhóm và phòng gốc khai ở `config/rules.yml` → `phong_online`. Số liệu tính đúng như Báo cáo phòng của IBB2
(cùng hàm `bao_cao_phong.bang_nhan_su`), chỉ giữ người trong nhóm - IBB2 vẫn hiện đủ mọi người, số của nhóm
không bị trừ khỏi IBB2.
"""
from __future__ import annotations

import pandas as pd

from app import bao_cao_phong as bp
from app.config import rules_config
from app.metrics import bang_ngay_theo_acc

TEN = "Phòng Online"


def _cfg() -> dict:
    return rules_config().get("phong_online") or {}


def phong_goc() -> str:
    return _cfg().get("phong_goc") or "IBB2"


def acc_nhom() -> list[str]:
    """acc_norm của những người thuộc Phòng Online."""
    return [str(a).strip().lower() for a in (_cfg().get("acc") or [])]


def la_nguoi_online(acc_norm: str | None) -> bool:
    return (acc_norm or "").strip().lower() in set(acc_nhom())


def bang_nhan_su(thang: str, ngay: int) -> pd.DataFrame:
    """Bảng nhân sự của nhóm: cùng cột với Báo cáo phòng, hạng và TỔNG tính trong riêng nhóm."""
    kq = bp.bang_nhan_su(thang, ngay, phong_goc(), acc=acc_nhom())
    kq.loc[kq.loai_dong == "total", "ho_ten"] = f"TỔNG {TEN.upper()}"
    return kq


def so_theo_ngay(thang: str, ngay: int, khoi: str, cong_don: bool = False) -> pd.DataFrame:
    """Số từng ngày của từng người trong nhóm (cùng bảng với khối "Số bán theo ngày" của Báo cáo phòng)."""
    df = bang_ngay_theo_acc(thang, khoi, chi_phong=[phong_goc()], den_ngay=ngay, cong_don=cong_don)
    cot_ngay = [c for c in df.columns if c.isdigit()]
    giu = set(acc_nhom())
    nguoi = df[(df.loai_dong == "data") & df.acc_norm.isin(giu)].copy()
    if not nguoi.empty:
        tong = {c: int(nguoi[c].sum()) for c in cot_ngay}
        tong["Tổng"] = int(nguoi["Tổng"].sum())      # cột Tổng của mỗi người là tổng thật kể cả khi xem cộng dồn
    else:
        tong = {c: 0 for c in cot_ngay} | {"Tổng": 0}
    dong_tong = {"loai_dong": "subtotal", "phong_code": "ONLINE", "phong": TEN, "acc": f"TỔNG {TEN.upper()}",
                 "acc_norm": "", "ten": "", **tong}
    return pd.concat([nguoi, pd.DataFrame([dong_tong])], ignore_index=True)
