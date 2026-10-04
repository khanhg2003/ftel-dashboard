"""Ảnh Báo cáo Tổng (PNG) phải giống bảng trên web ở cột PTTB CNQL: dòng có MTTN hiện số trong ngoặc."""
from __future__ import annotations

import io

from PIL import Image

from app import export_png as ep
from app import mttn
from app.org import phong_order
from app.overview import bang_tong_quan

THANG, NGAY = "2026-09", 11


def test_anh_cnql_kem_mttn_trong_ngoac_giong_web():
    """Chủ app báo 04/10/2026: ảnh gửi nhóm thiếu "17 (24)" và "33% (47%)" ở IBB7 và bầy DNG_2 dù web có."""
    df, _ = bang_tong_quan(THANG, NGAY)
    meta = {p["code"]: p for p in phong_order(THANG)}
    phong_bat = mttn.cau_hinh()["phong"]
    assert phong_bat
    bay = meta[phong_bat[0]]["bay"]
    for ma in (phong_bat[0], f"SUB_{bay}"):
        r = df[df.phong_code == ma].iloc[0].to_dict()
        assert ep._chu_o("so", "cnql", r) == f"{ep._so(r['cnql'])} ({ep._so(r['mttn'])})"
        assert ep._chu_o("pct:ty_le", "cnql_ty_le", r) == f"{round(r['cnql_ty_le'])}% ({round(r['mttn_ty_le'])}%)"
        # tô màu theo số MTTN trong ngoặc, giống web
        assert ep._gia_tri_mau("cnql_ty_le", r) == r["mttn_ty_le"]
    khac = df[(df.loai_dong == "data") & ~df.phong_code.isin(phong_bat) & (df.cnql > 0)].iloc[0].to_dict()
    assert "(" not in ep._chu_o("so", "cnql", khac) and "(" not in ep._chu_o("pct:ty_le", "cnql_ty_le", khac)
    tong = df[df.phong_code == "TOTAL"].iloc[0].to_dict()
    assert "(" not in ep._chu_o("so", "cnql", tong)


def test_anh_tong_quan_ve_duoc():
    png, _ = ep.anh_tong_quan(THANG, NGAY)
    assert Image.open(io.BytesIO(png)).width > 1000
