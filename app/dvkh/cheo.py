"""Phân tích chéo giữa các nguồn DVKH: cùng một hợp đồng xuất hiện ở nhiều nơi nói lên điều gì."""
from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from app.bo_nho import nho
from app.db import engine
from app.dvkh import nap


@nho("dvkh", 30)
def tap_hop_dong(loai: str) -> set[str]:
    """Danh sách hợp đồng ych (yêu cầu huỷ) hoặc no_cuoc (nợ cước) đã nạp."""
    nap.dam_bao_bang()
    with engine.connect() as c:
        return {r[0] for r in c.execute(text("SELECT so_hd FROM dv_danh_sach WHERE loai = :l"), {"l": loai})}


def _noi_chuoi(df: pd.DataFrame, khoa: str, cot: str, ten: str, toi_da: int = 70) -> pd.Series:
    """Nối các giá trị khác nhau của một cột theo từng hợp đồng bằng một lần gộp (nhanh hơn groupby + lambda trên hàng nghìn nhóm)."""
    d = df[[khoa, cot]].dropna().drop_duplicates()
    d[cot] = d[cot].astype(str).str.strip()
    return d.groupby(khoa)[cot].agg(" · ".join).str.slice(0, toi_da).rename(ten)


def hop_dong_hai_nguon(bd: pd.DataFrame, cd: pd.DataFrame) -> pd.DataFrame:
    """Hợp đồng vừa khách gọi (SR bị động) vừa được DVKH chủ động chăm: nếu gọi hai lần cho cùng một việc thì nên gộp."""
    if bd.empty or cd.empty:
        return pd.DataFrame()
    a = bd.groupby("so_hd").agg(sr_bd=("ma_sr", "size"), ton_bd=("ton", "sum"), muon_di=("muon_di", "sum"), phong=("phong", "first"), quan=("quan", "first"))
    a = a.join(_noi_chuoi(bd, "so_hd", "loai_yc", "loai_bd"))
    b = cd.groupby("so_hd").agg(sr_cd=("ma_sr", "size"), ton_cd=("ton", "sum"), muon_thanh_ly=("muon_thanh_ly", "sum"), no_cuoc=("no_cuoc", "max"))
    b = b.join(_noi_chuoi(cd, "so_hd", "chuong_trinh", "ct_cd"))
    m = a.join(b, how="inner").reset_index()
    m["tong_sr"] = m["sr_bd"] + m["sr_cd"]
    m["con_ton"] = m["ton_bd"] + m["ton_cd"]
    return m.sort_values(["con_ton", "tong_sr"], ascending=False)


def thanh_ly_ton(bd: pd.DataFrame, cd: pd.DataFrame) -> pd.DataFrame:
    """Khách đang đòi thanh lý mà SR chưa xong: gọi ngay còn giữ được."""
    a = bd[(bd["loai_yc"] == "Thanh lý") & bd["ton"]][["ma_sr", "so_hd", "phong", "quan", "nguoi_xu_ly", "tinh_trang", "tg_yc"]].rename(columns={"tg_yc": "thoi_gian"})
    a["nguon"] = "SR bị động: thanh lý"
    b = cd[cd["muon_thanh_ly"] & cd["ton"]][["ma_sr", "so_hd", "phong", "quan", "nguoi_xu_ly", "tinh_trang", "tg_do"]].rename(columns={"tg_do": "thoi_gian"})
    b["nguon"] = "SR chủ động: khách đòi thanh lý"
    return pd.concat([a, b], ignore_index=True).sort_values("thoi_gian") if len(a) + len(b) else pd.DataFrame()


def thanh_ly_va_no_cuoc(bd: pd.DataFrame) -> dict:
    """Trong các hợp đồng yêu cầu thanh lý, bao nhiêu hợp đồng đang nợ cước (thanh lý để tránh nợ?)."""
    no = tap_hop_dong("no_cuoc")
    tl = bd[bd["loai_yc"] == "Thanh lý"]["so_hd"].dropna().unique()
    tat_ca = bd["so_hd"].dropna().unique()
    n_tl = sum(1 for h in tl if h in no)
    n_all = sum(1 for h in tat_ca if h in no)
    return {"hd_thanh_ly": len(tl), "thanh_ly_no_cuoc": n_tl, "ty_le_thanh_ly": n_tl * 100 / max(len(tl), 1),
            "hd_tat_ca": len(tat_ca), "tat_ca_no_cuoc": n_all, "ty_le_tat_ca": n_all * 100 / max(len(tat_ca), 1)}
