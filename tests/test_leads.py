"""Kiểm thử app/leads.py: CRUD lead, danh mục page riêng của Phòng Online, tính SLA và đề xuất nhận chéo."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import delete

from app import leads
from app.bo_nho import xoa as xoa_nho
from app.db import session_scope
from app.models import CrmPage, Lead

NGUOI = "kiemthu"


@pytest.fixture(autouse=True)
def don_dep():
    leads.dam_bao_bang()

    def xoa():
        with session_scope() as s:
            s.execute(delete(Lead))
            s.execute(delete(CrmPage))
        xoa_nho()
    xoa()
    yield
    xoa()


def _page(ten: str = "Hải Phòng") -> int:
    leads.them_page(ten, None, NGUOI)
    df = leads.ds_page()
    return int(df[df.ten == ten].id.iloc[0])


def test_them_page_trung_ten_bi_tu_choi_du_khac_hoa_thuong_khoang_trang():
    _page("Hải Phòng")
    with pytest.raises(leads.LoiLead):
        leads.them_page("hải   phòng", None, NGUOI)


def test_tao_lead_thieu_page_bi_tu_choi():
    with pytest.raises(leads.LoiLead):
        leads.tao_lead({"ten_kh": "A"}, NGUOI)


def test_tim_sdt_bat_duoc_so_trong_tin_nhan_tho():
    assert leads.tim_sdt("em 0912.345.678 cho chị nhé") == "0912345678"
    assert leads.tim_sdt("không có số nào ở đây") is None


def test_tao_lead_voi_ngay_dang_chuoi_iso_nhu_dcc_input_gui_len():
    """`dcc.Input(type="date")` gửi lên chuỗi ISO "YYYY-MM-DD", không phải đối tượng date."""
    pid = _page()
    lid = leads.tao_lead({"page_id": pid, "ten_kh": "Anh Tú", "ngay": "2026-11-10"}, NGUOI)
    df = leads.danh_sach()
    assert str(df[df.id == lid].iloc[0].ngay) == "2026-11-10"


def test_tao_va_sua_lead_ghi_moc_cham_soc():
    pid = _page()
    lid = leads.tao_lead({"page_id": pid, "ten_kh": "Chị Lan", "sdt": "0912345678"}, NGUOI)
    df = leads.danh_sach()
    r = df[df.id == lid].iloc[0]
    assert r.tinh_trang_xu_ly == "Mới" and r.cap_nhat_luc is not None and not bool(r.qua_han)

    leads.cap_nhat_lead(lid, {"tinh_trang_xu_ly": "Đang tư vấn"}, NGUOI)
    df2 = leads.danh_sach()
    r2 = df2[df2.id == lid].iloc[0]
    assert r2.tinh_trang_xu_ly == "Đang tư vấn" and r2.cap_nhat_luc >= r.cap_nhat_luc


def test_lead_qua_24h_duoc_danh_dau_qua_han():
    pid = _page()
    lid = leads.tao_lead({"page_id": pid, "ten_kh": "Anh Nam"}, NGUOI)
    with session_scope() as s:
        s.get(Lead, lid).cap_nhat_luc = datetime.utcnow() - timedelta(hours=25)
    xoa_nho("leads")
    df = leads.danh_sach()
    assert bool(df[df.id == lid].iloc[0].qua_han)


def test_lead_da_chot_khong_tinh_qua_han_du_lau_ngay():
    pid = _page()
    lid = leads.tao_lead({"page_id": pid, "ten_kh": "Chị Hoa", "tinh_trang_xu_ly": "Đã chốt"}, NGUOI)
    with session_scope() as s:
        s.get(Lead, lid).cap_nhat_luc = datetime.utcnow() - timedelta(days=5)
    xoa_nho("leads")
    df = leads.danh_sach()
    assert not bool(df[df.id == lid].iloc[0].qua_han)


def test_de_xuat_nhan_cheo_chon_dung_nguoi_it_viec_nhat_khac_chinh_minh():
    nguoi = leads.nguoi_online()
    if len(nguoi) < 2:
        pytest.skip("Cần ít nhất 2 người ở config/rules.yml phong_online.acc để kiểm thử.")
    pid = _page()
    a, b = nguoi[0]["acc_norm"], nguoi[1]["acc_norm"]
    for _ in range(3):
        leads.tao_lead({"page_id": pid, "sale_tu_van": a}, NGUOI)
    leads.tao_lead({"page_id": pid, "sale_tu_van": b}, NGUOI)
    de_xuat = leads.de_xuat_nhan_cheo(a)
    tai = leads.tai_dang_xu_ly()
    assert de_xuat != a
    assert tai[de_xuat] == min(v for k, v in tai.items() if k != a)


def test_nhan_cheo_doi_sale_va_ghi_nguoi_da_nhan():
    nguoi = leads.nguoi_online()
    if len(nguoi) < 2:
        pytest.skip("Cần ít nhất 2 người ở config/rules.yml phong_online.acc để kiểm thử.")
    pid = _page()
    a, b = nguoi[0]["acc_norm"], nguoi[1]["acc_norm"]
    lid = leads.tao_lead({"page_id": pid, "sale_tu_van": a}, NGUOI)
    leads.nhan_cheo(lid, b, NGUOI)
    df = leads.danh_sach()
    r = df[df.id == lid].iloc[0]
    assert r.sale_tu_van == b and r.care_cheo_boi == b
    ten_b = {a["acc_norm"]: a["ten"] for a in nguoi}[b]
    assert r.care_cheo_tooltip == f"Đã nhận chéo bởi {ten_b}"
    lid2 = leads.tao_lead({"page_id": pid, "sale_tu_van": a}, NGUOI)       # lead chưa từng nhận chéo: không có tooltip
    assert leads.danh_sach()[leads.danh_sach().id == lid2].iloc[0].care_cheo_tooltip == ""


def test_luu_fb_cau_hinh_can_du_fb_page_id_va_token():
    pid = _page()
    with pytest.raises(leads.LoiLead):
        leads.luu_fb_cau_hinh(pid, "", "tok", NGUOI)
    leads.luu_fb_cau_hinh(pid, "1234567890", "tok-bi-mat", NGUOI)
    pages = leads.ds_page()
    assert pages[pages.id == pid].iloc[0].fb_page_id == "1234567890"
