"""Kiểm thử công thức báo cáo - chốt bộ số đã đối chiếu tay với file Google Sheet.

Chạy:  python -m pytest -q
Các mốc dưới đây đã được đối chiếu thủ công với báo cáo kỳ 01-11/09/2026
(sau khi áp 4 quyết định nghiệp vụ của BGD ngày 11/09/2026).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import DATA_DIR                                    # noqa: E402
from app.ingest.normalize import (norm_acc, norm_header, norm_manv,  # noqa: E402
                                  parse_date, parse_number)
from app.metrics import (daily_counts, so_sanh_acc, tracking_table,  # noqa: E402
                         tien_do_thang)
from app.org import assign_phong                                    # noqa: E402
from app.overview import bang_tong_quan                             # noqa: E402

THANG = "2026-09"
pytestmark = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(),
                                reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")


# --------------------------------------------------------------- chuẩn hoá
def test_chuan_hoa_unicode_ten_cot():
    """Tên cột trong file thật ở dạng Unicode tổ hợp - phải khớp sau khi chuẩn hoá."""
    to_hop = "CN Bán"          # dạng NFD như trong file export
    assert norm_header(to_hop) == norm_header("CN Bán") == "cn bán"
    assert norm_header("  Ngày   Online ") == "ngày online"


def test_chuan_hoa_ma_nv_va_acc():
    assert norm_manv("00036393") == norm_manv("36393") == "36393"
    assert norm_acc(" TIN.Minhlh1 ") == norm_acc("TIN.MinhLH1") == "tin.minhlh1"


@pytest.mark.parametrize("chuoi, mong_doi", [
    ("1,063,636", 1063636), ("158,01", 158.01), ("300.000", 300000),
    ("1.234,56", 1234.56), ("455", 455), ("", None), ("#N/A", None),
])
def test_doc_so_lan_dinh_dang(chuoi, mong_doi):
    assert parse_number(chuoi) == mong_doi


def test_doc_ngay():
    assert parse_date("2026-09-11").isoformat() == "2026-09-11"
    assert parse_date("11/09/2026").isoformat() == "2026-09-11"
    assert parse_date("1899-12-31") is not None      # ngày rác của Excel vẫn đọc được
    assert parse_date("#VALUE!") is None


# --------------------------------------------------------------- gán phòng
def test_gan_phong_theo_quy_tac():
    dm = {"dng.abc": "IBB2"}
    assert assign_phong("DNG.ABC", "Phòng kinh doanh 2", "DNG_01", "DNG_01", dm) == ("IBB2", False)
    # ECOM ưu tiên trước danh mục, tách theo CN Quản lý
    assert assign_phong("HCM.ECOM.x", "", "HCM_ECOM", "QNM", dm) == ("ECOM_QNM", True)
    assert assign_phong("HCM.ECOM.x", "", "HCM_ECOM", "DNG_02", dm) == ("ECOM_DNG", True)
    # không có trong danh mục -> theo phòng hệ thống + CN bán
    assert assign_phong("ai.do", "Phòng kỹ thuật", "DNG_02", "DNG_02", dm) == ("KT_DNG2", False)
    assert assign_phong("ai.do", "Phòng CUS", "QNM", "QNM", dm) == ("CUS_QNM", False)
    # còn lại -> chưa gán phòng (vẫn vào tổng chi nhánh)
    assert assign_phong("la.hoac", "Phòng nghiệp vụ", "DNG_01", "DNG_01", dm) == ("CHUA_GAN", False)


# --------------------------------------------------------------- số liệu
def test_tong_thang_khop_so_da_doi_chieu():
    df, ngay = bang_tong_quan(THANG)
    tong = df[df.loai_dong == "total"].iloc[0]
    assert ngay == 11
    assert int(tong.online) == 1394        # sheet cũ ghi 1.397 (đếm trùng 4, sót 1)
    assert int(tong.vvip) == 980           # sheet cũ ghi 983
    assert int(tong.camera) == 587         # = sheet: đếm từng dòng file Inside, kể cả dòng giống hệt (chốt 15/09)
    assert int(tong.cnql) == 1003
    assert int(tong.fpl_combo) == 983
    assert int(tong.so_ton) == 899


def test_ibb2_tung_ngay():
    d = daily_counts(THANG, "online").loc["IBB2"]
    assert [int(d[i]) for i in range(1, 12)] == [9, 15, 15, 22, 21, 14, 13, 20, 13, 16, 9]


def test_ibb2_dong_tong_hop():
    df, _ = bang_tong_quan(THANG)
    r = df[df.phong == "IBB2"].iloc[0]
    assert (int(r.mt_internet), int(r.so_ton), int(r.online)) == (550, 103, 167)
    assert (int(r.ck_online), int(r.fpl_combo), int(r.cnql), int(r.vvip)) == (149, 115, 127, 115)
    assert (int(r.mt_camera), int(r.camera)) == (140, 48)
    assert (int(r.ngay_ban_moi), int(r.ngay_online), int(r.ngay_vvip)) == (16, 9, 13)


def test_tin_minhlh1_chi_tinh_cho_cus_dng2():
    """BGD chốt: acc này chỉ thuộc Phòng CUS DNG2, không được tính thêm cho IBB6."""
    df, _ = bang_tong_quan(THANG)
    assert int(df[df.phong == "IBB6"].iloc[0].online) == 117
    assert int(df[df.phong == "Phòng CUS DNG2"].iloc[0].online) == 19


def test_dong_tong_bay_va_nhom_khac():
    df = tracking_table(THANG, "online")
    tong = {r["bay"]: int(r["Tổng"]) for _, r in df[df.loai_dong != "data"].iterrows()}
    assert tong["TỔNG BẦY 1"] == 479
    assert tong["TỔNG BẦY 2"] == 465
    assert tong["TỔNG BẦY 3"] == 396
    assert tong["DNG Khác"] == 155          # Khối D1 trong sheet
    assert tong["QNM Khác"] == 60
    assert tong["TỔNG TOÀN CHI NHÁNH"] == 1394


def test_tien_do_dung_so_ngay_cua_thang():
    """Sheet cũ chia 31 cho tháng 30 ngày - app phải chia đúng 30."""
    td = tien_do_thang(THANG, den_ngay=11)
    assert td["so_ngay_trong_thang"] == 30
    assert round(td["ty_le_thoi_gian"], 2) == 36.67


def test_top_hut_so_khop_khoi_d2():
    """Khối D2 của sheet: kỳ 16-22/08 so với 23-29/08."""
    d = so_sanh_acc(("2026-08-16", "2026-08-22"), ("2026-08-23", "2026-08-29"))
    d = d.set_index("acc")
    assert (int(d.loc["DNG.TraLT8"].ky1), int(d.loc["DNG.TraLT8"].ky2)) == (14, 7)
    assert (int(d.loc["DNG.Quyenlb4"].ky1), int(d.loc["DNG.Quyenlb4"].ky2)) == (8, 2)
    assert (int(d.loc["QNM.Vantn7"].ky1), int(d.loc["QNM.Vantn7"].ky2)) == (10, 2)
