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


def test_gan_phong_doi_tuong_kh_vip7_vuot_tren_ecom_va_danh_muc():
    """Chốt với chủ app 01/10/2026: HĐ "Đối tượng KH" = VIP 7 luôn tính cho ANCS, kể cả khi tài
    khoản bán là ECOM hoặc có trong danh mục nhân sự - nhóm khách công ty quản lý riêng, không phụ
    thuộc ai đứng tên bán."""
    dm = {"dng.abc": "IBB2"}
    # vượt trên cả ECOM (lẽ ra là ECOM_QNM / ECOM_DNG nếu không có VIP 7); khách Quảng Nam thì về ANCS_QNM (16/10/2026)
    assert assign_phong("HCM.ECOM.x", "", "HCM_ECOM", "DNG_02", dm, doi_tuong_kh="VIP 7") == ("ANCS", False)
    assert assign_phong("HCM.ECOM.x", "", "HCM_ECOM", "QNM", dm, doi_tuong_kh="VIP 7") == ("ANCS_QNM", False)
    # vượt trên cả danh mục nhân sự (lẽ ra là IBB2 nếu không có VIP 7)
    assert assign_phong("DNG.ABC", "Phòng kinh doanh 2", "DNG_01", "DNG_01", dm,
                        doi_tuong_kh="VIP 7") == ("ANCS", False)
    # không phân biệt hoa thường / khoảng trắng thừa
    assert assign_phong("DNG.ABC", "Phòng kinh doanh 2", "DNG_01", "DNG_01", dm,
                        doi_tuong_kh="  vip 7 ") == ("ANCS", False)
    # Đối tượng KH khác (hoặc không có) thì không ảnh hưởng gì
    assert assign_phong("DNG.ABC", "Phòng kinh doanh 2", "DNG_01", "DNG_01", dm,
                        doi_tuong_kh="Đối tượng khác") == ("IBB2", False)
    assert assign_phong("DNG.ABC", "Phòng kinh doanh 2", "DNG_01", "DNG_01", dm) == ("IBB2", False)


def test_gan_phong_theo_hieu_luc_khi_chuyen_phong():
    from datetime import date
    dm = {"qnm.x": [(None, date(2026, 8, 31), "TAMKY"), (date(2026, 9, 1), None, "DAILOC")],
          "qnm.y": [(date(2026, 9, 1), None, "HOIAN")]}
    g = lambda acc, ngay: assign_phong(acc, "Phòng kinh doanh 1", "QNM", "QNM", dm, ngay)[0]  # noqa: E731
    assert g("QNM.X", date(2026, 8, 20)) == "TAMKY"
    assert g("QNM.X", "2026-09-02") == "DAILOC"
    assert g("QNM.X", None) == "DAILOC"            # không có ngày -> dòng đang hiệu lực
    assert g("QNM.Y", date(2026, 8, 1)) == "HOIAN"  # chỉ một dòng -> vẫn dùng dòng đó


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


def test_mttn_hien_canh_cnql_chi_o_ibb7_va_bay_cua_ibb7():
    """Chốt với chủ app 01/10/2026: số/tỷ lệ MTTN hiện trong ngoặc cạnh PTTB CNQL - CHỈ ở phòng có
    bật MTTN (config/rules.yml -> mttn.phong, hiện là IBB7) và dòng tổng bầy chứa phòng đó, không ở
    phòng/bầy khác hay dòng tổng chi nhánh/toàn phòng. Tỷ lệ = mttn / tổng online (giống Báo cáo
    phòng), không phải so với số CNQL.

    Ở dòng tổng bầy: CN_NOI_BO (DNG_01/DNG_02/QNM, dùng cho cột CNQL) là TẬP CON của danh sách tỉnh
    MTTN, nên CNQL của các phòng KHÔNG tự bật MTTN trong cùng bầy vẫn chắc chắn nằm trong vùng MTTN -
    phải cộng thêm vào, không chỉ lấy đúng số MTTN của riêng phòng đã bật (chốt 01/10/2026, phản hồi
    sau khi thấy tỷ lệ bầy bị "pha loãng" xuống thấp hơn hẳn tỷ lệ của chính phòng)."""
    from app import mttn
    from app.org import bay_info, phong_order

    df, _ = bang_tong_quan(THANG)
    phong_mttn = mttn.cau_hinh()["phong"]
    assert phong_mttn, "cần ít nhất một phòng bật MTTN để phép thử này có ý nghĩa"
    meta = {p["code"]: p for p in phong_order(THANG)}
    bay_cua_mttn = {meta[c]["bay"] for c in phong_mttn if c in meta}

    for code in phong_mttn:
        r = df[df.phong_code == code].iloc[0]
        assert r.mttn_hien
        assert 0 <= r.mttn <= r.online
        if r.online:
            assert round(r.mttn / r.online * 100) == r.mttn_ty_le

    for bcode in bay_cua_mttn:
        sub = df[df.phong_code == f"SUB_{bcode}"].iloc[0]
        assert sub.mttn_hien
        ca_bay = df[(df.loai_dong == "data") & (df.phong_code.map(lambda c: meta.get(c, {}).get("bay")) == bcode)]
        mttn_rieng = ca_bay[ca_bay.phong_code.isin(phong_mttn)].mttn.sum()
        cnql_phong_khac = ca_bay[~ca_bay.phong_code.isin(phong_mttn)].cnql.sum()
        assert sub.mttn == mttn_rieng + cnql_phong_khac
        assert sub.mttn >= mttn_rieng       # không bao giờ nhỏ hơn số MTTN riêng của phòng đã bật

    # phòng/bầy không bật MTTN thì không hiện, dù cộng ra 0
    phong_khac = [p["code"] for p in phong_order(THANG) if p["code"] not in phong_mttn][0]
    assert not df[df.phong_code == phong_khac].iloc[0].mttn_hien
    bay_khac = next(b for b in bay_info() if b not in bay_cua_mttn
                    and not df[df.phong_code == f"SUB_{b}"].empty)
    assert not df[df.phong_code == f"SUB_{bay_khac}"].iloc[0].mttn_hien
    assert not df[df.loai_dong == "total"].iloc[0].mttn_hien


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
