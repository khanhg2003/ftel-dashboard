"""Kiểm thử trang Phân tích bán hàng và cách xử lý file export cuộn 3 tháng."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import phan_tich as pt                                        # noqa: E402
from app.config import DATA_DIR                                        # noqa: E402

THANG = "2026-09"
pytestmark = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(),
                                reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")


def test_so_online_khop_bao_cao_tong():
    from app.overview import bang_tong_quan
    tu, den, ngay = pt.ky_phan_tich(THANG)
    df = pt.hop_dong_online(tu, den)
    bang, ngay_bc = bang_tong_quan(THANG)
    assert ngay == ngay_bc == 11
    assert len(df) == int(bang[bang.loai_dong == "total"].online.iloc[0]) == 1394
    assert df.hop_dong.is_unique


def test_ty_le_ban_kem_hop_le():
    tu, den, _ = pt.ky_phan_tich(THANG)
    df = pt.hop_dong_online(tu, den)
    c = pt.chi_so_chung(df)
    for k in ("kem_vvip", "kem_camera", "du_3", "tra_truoc", "onl_1_ngay", "ngoai_tinh"):
        assert 0 <= c[k] <= 100
    assert c["du_3"] <= min(c["kem_vvip"], c["kem_camera"])
    # tỷ lệ đọc ngược lại phải ra đúng số hợp đồng có cờ kèm V.VIP
    assert df.co_vvip.sum() == round(c["kem_vvip"] * len(df) / 100)


def test_bang_theo_phong_dong_tong_bang_tong_cac_phong():
    tu, den, _ = pt.ky_phan_tich(THANG)
    df, ton = pt.hop_dong_online(tu, den), pt.hop_dong_ton()
    bang = pt.bang_theo_phong(df, ton, THANG)
    data = bang[bang.loai_dong == "data"]
    tong = bang[bang.loai_dong == "total"].iloc[0]
    assert data.online.sum() == tong.online == len(df)
    assert data.ton.sum() == tong.ton == len(ton)


def test_chi_nhanh_chi_lay_phong_cua_chi_nhanh():
    from app.org import loc_chi_nhanh
    tu, den, _ = pt.ky_phan_tich(THANG)
    qnm = loc_chi_nhanh(None, "QNM", THANG)
    df = pt.hop_dong_online(tu, den, qnm)
    assert len(df) and set(df.phong_code) <= set(qnm)


def test_nhom_goi():
    assert pt.nhom_goi("Giga F1") == "Giga" and pt.nhom_goi("sky") == "Sky"
    assert pt.nhom_goi("Super300-Biz") == "Khác" and pt.nhom_goi(None) == "Khác"


def test_ton_theo_tuoi_cong_du():
    ton = pt.hop_dong_ton()
    g = pt.ton_theo_tuoi(ton, THANG)
    tong = g[g.loai_dong == "total"].iloc[0]
    assert tong.tong == len(ton) == sum(tong[f"m{i}"] for i in range(len(pt.MOC_TON)))


def test_ban_ngoai_tinh_la_phan_bu_cua_pttb_cnql():
    from app.overview import bang_tong_quan
    tu, den, _ = pt.ky_phan_tich(THANG)
    df = pt.hop_dong_online(tu, den)
    bang, _ = bang_tong_quan(THANG)
    cnql = int(bang[bang.loai_dong == "total"].cnql.iloc[0])
    assert df.ngoai_tinh.sum() == len(df) - cnql


# ---------------------------------------------------------- file cuộn 3 tháng
def test_so_ton_chi_tinh_hop_dong_con_trong_file_moi_nhat(monkeypatch):
    import app.metrics as m
    lan_nap = pd.DataFrame({"id": [9, 8, 7], "rows_valid": [10500, 10200, 9900]})
    monkeypatch.setattr(m.pd, "read_sql", lambda *a, **k: lan_nap)
    dk, p = m.dieu_kien_ton("f.")
    assert "f.batch_id = :lo_moi_nhat" in dk and p == {"lo_moi_nhat": 9}


def test_file_le_khong_dung_de_loc_so_ton(monkeypatch):
    import app.metrics as m
    lan_nap = pd.DataFrame({"id": [9, 8], "rows_valid": [300, 10200]})   # lần mới chỉ là file lẻ
    monkeypatch.setattr(m.pd, "read_sql", lambda *a, **k: lan_nap)
    dk, p = m.dieu_kien_ton()
    assert dk == "ngay_online IS NULL" and p == {}


def test_nap_lai_camera_khong_dem_trung_khi_hop_dong_doi_thong_tin():
    from sqlalchemy import func, select

    from app.db import SessionLocal
    from app.ingest.commit import _bo_dong_camera_cu, _upsert
    from app.models import FactCamera

    s = SessionLocal()
    try:
        cu = s.execute(select(FactCamera).where(FactCamera.ngay_online.is_(None)).limit(1)).scalar_one()
        dem = lambda: s.execute(select(func.count()).select_from(FactCamera)       # noqa: E731
                                .where(FactCamera.hop_dong == cu.hop_dong)).scalar()
        truoc = dem()
        # file mới: đúng hợp đồng đó nhưng đã online -> mã băm dòng khác
        moi = {c.name: getattr(cu, c.name) for c in FactCamera.__table__.columns
               if c.name != "updated_at"}
        moi.update(row_hash="hash-moi-sau-khi-online", ngay_online=cu.ngay_tao_hd)
        cac_dong_khac = [{c.name: getattr(o, c.name) for c in FactCamera.__table__.columns
                          if c.name != "updated_at"}
                         for o in s.execute(select(FactCamera).where(
                             FactCamera.hop_dong == cu.hop_dong,
                             FactCamera.row_hash != cu.row_hash)).scalars()]
        rows = [moi] + cac_dong_khac
        _bo_dong_camera_cu(s, rows)
        _upsert(s, FactCamera, rows, "row_hash")
        assert dem() == truoc
        assert s.get(FactCamera, cu.row_hash) is None
    finally:
        s.rollback()
        s.close()


def test_trang_phan_tich_dung_duoc():
    from app.ui.pages import phantich
    phantich.layout()
    assert phantich.topbar()


def test_khong_con_chu_dau_noi():
    goc = Path(__file__).resolve().parent.parent
    for f in list((goc / "app").rglob("*.py")) + list((goc / "docs").glob("*.md")):
        assert "đấu nối" not in f.read_text(encoding="utf-8").lower(), f
