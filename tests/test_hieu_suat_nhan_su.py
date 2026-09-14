"""Kiểm thử đợt: dòng Tổng DNG/QNM, giờ Việt Nam, lịch sử nạp ở trang Nạp dữ liệu, Hiệu suất nhân sự."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import DATA_DIR                                        # noqa: E402

THANG = "2026-09"
pytestmark = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(),
                                reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")


def _tim(node, id_):
    if getattr(node, "id", None) == id_:
        return node
    con = getattr(node, "children", None)
    if con is None or isinstance(con, str):
        return None
    for c in con if isinstance(con, (list, tuple)) else [con]:
        kq = _tim(c, id_)
        if kq is not None:
            return kq
    return None


# ------------------------------------------------------------ Báo cáo Tổng
def test_bao_cao_tong_co_dong_tong_dng_qnm_ngay_tren_dong_tong():
    from app.org import loc_chi_nhanh
    from app.overview import bang_tong_quan
    df, _ = bang_tong_quan(THANG)
    assert list(df.phong.iloc[-3:]) == ["TỔNG DNG", "TỔNG QNM", "TỔNG TOÀN CHI NHÁNH"]
    cn = df[df.loai_dong == "chinhanh"].set_index("phong")
    tong = df[df.loai_dong == "total"].iloc[0]
    assert cn.online.sum() == tong.online and cn.so_ton.sum() == tong.so_ton
    for ma in ("DNG", "QNM"):
        rieng, _ = bang_tong_quan(THANG, chi_phong=loc_chi_nhanh(None, ma, THANG), chi_nhanh=ma)
        assert cn.loc[f"TỔNG {ma}"].online == rieng[rieng.loai_dong == "total"].iloc[0].online
        assert "chinhanh" not in set(rieng.loai_dong)       # xem riêng một tỉnh thì không lặp dòng


def test_anh_va_excel_bao_cao_tong_van_xuat_duoc():
    from app.export_excel import xuat_tong_quan
    from app.export_png import anh_tong_quan
    assert anh_tong_quan(THANG)[0] and xuat_tong_quan(THANG)[0]


# --------------------------------------------------------------- giờ giấc
def test_gio_luu_utc_hien_thi_gio_viet_nam():
    from app.thoi_gian import chu_gio_vn
    assert chu_gio_vn(datetime(2026, 9, 13, 14, 54)) == "13/09/2026 21:54"
    assert chu_gio_vn("2026-09-13 20:30:00", "%H:%M %d/%m") == "03:30 14/09"
    assert chu_gio_vn(None) == "" and chu_gio_vn(float("nan")) == ""


def test_lich_su_nap_dung_gio_viet_nam():
    import pandas as pd
    from sqlalchemy import text

    from app.admin_service import lich_su_nap
    from app.db import engine
    b = lich_su_nap(1)
    if b.empty:
        pytest.skip("Database kiểm thử chưa có lần nạp")
    goc = pd.read_sql(text("SELECT uploaded_at FROM upload_batch ORDER BY id DESC LIMIT 1"), engine)
    gio = pd.Timestamp(goc.iloc[0, 0]) + pd.Timedelta(hours=7)
    assert b.thoi_diem.iloc[0] == f"{gio:%H:%M %d/%m/%Y}"


def test_lich_su_nap_chuyen_sang_trang_nap_du_lieu():
    from app.ui.pages import quantri, upload
    assert _tim(upload.layout(), "up-ls-grid") is not None
    assert _tim(upload.layout(), "up-ls-go") is not None
    assert _tim(quantri.layout(), "qt-batch-grid") is None


# ------------------------------------------------------ Hiệu suất nhân sự
def test_nhan_su_luy_ke_den_ngay_chon_khop_so_online():
    from app.hr_metrics import hieu_suat_nhan_su
    from app.overview import bang_tong_quan
    df = hieu_suat_nhan_su(THANG, ngay=11)
    bang, _ = bang_tong_quan(THANG, 11)
    assert df.online.sum() == bang[bang.loai_dong == "total"].iloc[0].online
    assert hieu_suat_nhan_su(THANG, ngay=5).online.sum() < df.online.sum()


def test_nhan_su_khong_con_nan_va_nhan_de_doc():
    from app.hr_metrics import hieu_suat_nhan_su
    df = hieu_suat_nhan_su(THANG, ngay=11)
    assert not df.tham_nien.str.contains("nan").any()
    assert set(df.nsld.dropna()) <= {"Đạt", "Chưa đạt", "Không xét"}
    assert set(df.nhom.dropna()) <= {"Mới", "Đang lên", "Ổn định", "Lâu năm"}
    assert df.ho_ten.notna().all()


def test_nguoi_da_nghi_khong_con_so_bi_bo():
    from app.hr_metrics import hieu_suat_nhan_su
    df = hieu_suat_nhan_su(THANG, ngay=11)
    assert (df[~df.dang_lam].online > 0).all()


def test_so_voi_cung_tham_nien_lay_trung_vi_phong_kinh_doanh():
    from app.hr_metrics import hieu_suat_nhan_su
    df = hieu_suat_nhan_su(THANG, ngay=11)
    d = df[df.kd & df.dang_lam & df.tham_nien_bucket.notna()]
    if d.empty:
        pytest.skip("Không có hồ sơ NSLĐ")
    moc = d.tham_nien_bucket.value_counts().index[0]
    nhom = d[d.tham_nien_bucket == moc]
    tv = nhom.online.median()
    r = nhom.iloc[0]
    assert r.so_voi_tham_nien == round((r.online / tv - 1) * 100)
    assert df[~df.kd].so_voi_tham_nien.isna().all()


def test_canh_bao_co_ly_do_va_chi_xet_phong_kinh_doanh():
    from app.hr_metrics import canh_bao_nhan_su, hieu_suat_nhan_su
    df = hieu_suat_nhan_su(THANG, ngay=11)
    cb = canh_bao_nhan_su(THANG, ngay=11, df=df)
    assert len(cb) and (cb.ly_do.str.len() > 0).all()
    assert set(cb.muc_rui_ro) <= {"Trao đổi ngay", "Theo dõi"}
    kd = set(df[df.kd].acc_norm)
    assert set(cb.acc_norm) <= kd
    assert (cb[cb.muc_rui_ro == "Trao đổi ngay"].tuan_nay == 0).all()


def test_trang_hieu_suat_dung_duoc():
    from app.ui.pages import hr
    goc = hr.layout()
    for id_ in ("hr-date", "hr-cn", "hr-phong", "hr-tab", "hr-canhbao", "hr-grid", "hr-tim",
                "hr-export", "hr-ns-grid", "hr-tb-grid", "hr-ns-export"):
        assert _tim(goc, id_) is not None, id_
    assert hr._cols("ban") and hr._cols("nsld")
