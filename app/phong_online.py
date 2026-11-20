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
MA = "ONLINE"            # mã "phòng" ảo của nhóm: Báo cáo ngày của nhóm lưu với mã này, tách hẳn IBB7 (xem `bao_cao_ngay.PHONG_ONLINE`)


def _cfg() -> dict:
    return rules_config().get("phong_online") or {}


def phong_goc() -> str:
    return _cfg().get("phong_goc") or "IBB2"


def acc_nhom() -> list[str]:
    """acc_norm của những người thuộc Phòng Online."""
    return [str(a).strip().lower() for a in (_cfg().get("acc") or [])]


def bao_cao_ngay_bat() -> bool:
    """Tài khoản vai trò "online" có mục Báo cáo ngày riêng (`rules.yml` → `phong_online.bao_cao_ngay`)."""
    return bool(_cfg().get("bao_cao_ngay"))


def onl_tu_ca() -> bool:
    """ONL sáng / chiều / Đã online của Báo cáo ngày nhóm tự đếm từ ca ở Theo dõi Online (`rules.yml` → `phong_online.onl_tu_ca`)."""
    return bool(_cfg().get("onl_tu_ca"))


def khtn_tu_lead() -> bool:
    """KHTN của Báo cáo ngày nhóm tự đếm từ Lead Online thay vì sale gõ tay (`rules.yml` → `phong_online.khtn_tu_lead`)."""
    return bool(_cfg().get("khtn_tu_lead"))


def la_nguoi_online(acc_norm: str | None) -> bool:
    return (acc_norm or "").strip().lower() in set(acc_nhom())


def hd_theo_tinh(tu: str, den: str, theo: str = "online") -> pd.DataFrame:
    """Hợp đồng của nhóm trong kỳ kèm tỉnh của khách: đúng hàm của Phân tích → Bán theo tỉnh (`phan_tich.hd_theo_tinh`) trên phòng gốc, chỉ giữ người trong nhóm.
    `theo`: "online" (ngày online trong kỳ) hoặc "ban" (ngày tạo hợp đồng trong kỳ, gồm cả hợp đồng chưa online)."""
    from app import phan_tich as pt
    df = pt.hd_theo_tinh(tu, den, [phong_goc()], theo)
    acc = df.acc_norm.fillna(df.acc_nhan_vien.str.lower())
    return df[acc.isin(set(acc_nhom()))]


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


def khtn_theo_ngay(thang: str, ngay: int) -> pd.DataFrame:
    """Báo cáo KHTN của từng người trong nhóm, lấy từ ô KHTN ở Báo cáo ngày của nhóm (khách đang theo, chưa lên hợp đồng).

    Mỗi dòng một người; cột `d01`... là số KHTN người đó báo từng ngày (None = ngày đó người đó chưa có báo cáo nào, khác hẳn số 0 đã nhập).
    Cột `hom_nay` / `hom_qua` là hai ngày cuối kỳ, `tb` bình quân các ngày ĐÃ nhập, `cao_nhat`, `so_ngay_nhap`."""
    from datetime import date

    from sqlalchemy import text

    from app import bao_cao_ngay as bc
    from app.db import engine
    d = date(int(thang[:4]), int(thang[5:7]), ngay)
    nguoi = bc.bang([bc.PHONG_ONLINE], d)
    if nguoi.empty:
        return pd.DataFrame()
    raw = pd.read_sql_query(text("SELECT ngay, acc_norm, khtn FROM bao_cao_ngay WHERE phong_code = :p AND ngay >= :tu AND ngay <= :den"),
                            engine, params={"p": bc.PHONG_ONLINE, "tu": f"{thang}-01", "den": d.isoformat()})
    raw = raw[raw.khtn.notna()]
    raw["ngay"] = pd.to_datetime(raw["ngay"]).dt.day
    pv = raw.pivot_table(index="acc_norm", columns="ngay", values="khtn", aggfunc="max")
    out = nguoi[["acc_norm", "acc", "ho_ten"]].copy()
    for n in range(1, ngay + 1):
        out[f"d{n:02d}"] = out.acc_norm.map(pv[n]) if n in pv.columns else None
    cot = [f"d{n:02d}" for n in range(1, ngay + 1)]
    so = out[cot].apply(pd.to_numeric, errors="coerce")
    out["hom_nay"] = so[cot[-1]]
    out["hom_qua"] = so[cot[-2]] if len(cot) > 1 else None
    out["tb"] = so.mean(axis=1).round(1)
    out["cao_nhat"] = so.max(axis=1)
    out["so_ngay_nhap"] = so.notna().sum(axis=1)
    return out.sort_values(["hom_nay", "ho_ten"], ascending=[False, True], na_position="last").reset_index(drop=True)
