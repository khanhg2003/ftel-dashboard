"""Kiểm thử Báo cáo phòng: số từng nhân sự cộng lại phải khớp số của phòng trên Báo cáo Tổng."""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import bao_cao_phong as bp                                   # noqa: E402
from app.config import DATA_DIR                                       # noqa: E402
from app.overview import bang_tong_quan                               # noqa: E402

THANG, NGAY = "2026-09", 11
pytestmark = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(),
                                reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")


@pytest.fixture(scope="module")
def ibb2():
    return bp.bang_nhan_su(THANG, NGAY, "IBB2")


def test_tong_nhan_su_khop_so_cua_phong_tren_bao_cao_tong(ibb2):
    tq, _ = bang_tong_quan(THANG, NGAY)
    phong = tq[tq.phong_code == "IBB2"].iloc[0]
    du_lieu = ibb2[ibb2.loai_dong == "data"]
    tong = ibb2[ibb2.loai_dong == "total"].iloc[0]
    for cot_nv, cot_tq in (("online", "online"), ("vvip", "vvip"), ("camera", "camera"),
                           ("online_ngay", "ngay_online"), ("ban_moi_ngay", "ngay_ban_moi"),
                           ("ton", "so_ton")):
        assert sum(du_lieu[cot_nv]) == tong[cot_nv] == int(phong[cot_tq]), cot_nv


def test_ty_le_nhan_su_cung_cach_tinh_voi_bao_cao_tong(ibb2):
    tq, _ = bang_tong_quan(THANG, NGAY)
    phong = tq[tq.phong_code == "IBB2"].iloc[0]
    tong = ibb2[ibb2.loai_dong == "total"].iloc[0]
    assert round(tong.kem_vvip) == round(phong.vvip_ty_le)      # VVIP/PTTB


def test_hang_trong_phong_theo_so_online(ibb2):
    du_lieu = ibb2[ibb2.loai_dong == "data"]
    assert du_lieu.hang.iloc[0] == 1
    assert list(du_lieu.online) == sorted(du_lieu.online, reverse=True)
    # đồng hạng khi bằng số
    cung = du_lieu[du_lieu.online == du_lieu.online.iloc[1]]
    assert cung.hang.nunique() == 1


def test_chi_co_nhan_su_cua_dung_phong(ibb2):
    from sqlalchemy import text

    from app.db import engine
    with engine.connect() as c:
        khac = {r[0] for r in c.execute(text(
            "SELECT acc_norm FROM staff_map WHERE phong_code <> 'IBB2'"))}
        cua_phong = {r[0] for r in c.execute(text(
            "SELECT acc_norm FROM staff_map WHERE phong_code = 'IBB2'"))}
    accs = set(ibb2[ibb2.loai_dong == "data"].acc_norm)
    assert not (accs & (khac - cua_phong))


def test_so_sanh_phong_co_hang_trong_nhom():
    ss, dong = bp.so_sanh_phong(THANG, NGAY, "IBB2")
    assert dong["online"] > 0
    online = ss.set_index("khoa").loc["online"]
    assert 1 <= online.hang <= online.so_phong == len(bp.phong_cung_nhom("IBB2", THANG))
    # chỉ số "thấp là tốt": hạng 1 là phòng ít hợp đồng chờ nhất
    assert not ss.set_index("khoa").loc["ton_qua_7"].cao_la_tot


def test_chi_tiet_nhan_su(ibb2):
    nguoi = ibb2[ibb2.loai_dong == "data"].iloc[0]
    ds = bp.dien_bien_nhan_su(THANG, NGAY, nguoi.acc_norm)
    assert len(ds) == NGAY and ds.online.sum() == nguoi.online
    cho = bp.hop_dong_cho_cua_nhan_su(nguoi.acc_norm, "IBB2")
    assert len(cho) == nguoi.ton


def test_anh_va_excel_bao_cao_phong():
    from openpyxl import load_workbook
    from PIL import Image

    from app.export_phong import anh_bao_cao_phong, xuat_bao_cao_phong
    anh, ten = anh_bao_cao_phong(THANG, NGAY, "IBB2")
    assert ten == "BaoCaoPhong_IBB2_202609_ngay11.png"
    img = Image.open(io.BytesIO(anh))
    assert img.width > 1500 and img.height > 900
    xls, ten_x = xuat_bao_cao_phong(THANG, NGAY, "IBB2")
    ws = load_workbook(io.BytesIO(xls)).active
    assert ten_x.endswith(".xlsx") and "BÁO CÁO PHÒNG IBB2" in ws["A1"].value


def test_mttn_chi_ap_dung_ibb7_va_cong_khop(ibb2):
    import pandas as pd

    from app import mttn
    assert mttn.ap_dung("IBB7") and not mttn.ap_dung("IBB2")
    assert "mttn" not in ibb2.columns
    assert list(mttn.la_mttn(pd.Series(["dng_02", " GLI", "HCM_01", None]))) == [True, True, False, False]
    nv = bp.bang_nhan_su(THANG, NGAY, "IBB7")
    du_lieu, tong = nv[nv.loai_dong == "data"], nv[nv.loai_dong == "total"].iloc[0]
    m = mttn.tong_hop(THANG, NGAY, "IBB7")
    assert int(du_lieu.mttn.sum()) == tong.mttn == m["mttn"] and m["tong"] == tong.online
    assert all(0 <= v <= 100 for v in du_lieu.ty_le_mttn.dropna())


def test_khong_canh_bao_nguoi_nghi_va_truong_phong(monkeypatch):
    from app import canh_bao
    nv = bp.bang_nhan_su(THANG, NGAY, "IBB2")
    du_lieu = nv[nv.loai_dong == "data"]
    co_canh_bao = du_lieu[du_lieu.muc_chu_y != ""]
    assert len(co_canh_bao)
    a = co_canh_bao.acc_norm.iloc[0]
    monkeypatch.setattr(canh_bao, "acc_khong_xet", lambda them_acc=(): {a: "Trưởng phòng"})
    nv2 = bp.bang_nhan_su(THANG, NGAY, "IBB2").set_index("acc_norm")
    assert nv2.at[a, "muc_chu_y"] == "" and nv2.at[a, "chu_y"] == "" and nv2.at[a, "khong_xet"] == "Trưởng phòng"
