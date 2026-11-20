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
        leads.tao_lead({"page_id": pid, "sale_1": a}, NGUOI)
    leads.tao_lead({"page_id": pid, "sale_1": b}, NGUOI)
    de_xuat = leads.de_xuat_nhan_cheo(a)
    tai = leads.tai_dang_xu_ly()
    assert de_xuat != a
    assert tai[de_xuat] == min(v for k, v in tai.items() if k != a)


def test_nhan_lead_dien_dung_o_trong_ke_tiep_sale_1_2_3():
    """Chốt 20/11/2026: lead mới -> sale_1; dội lần 1 -> sale_2; dội lần 2 -> sale_3; dội quá 3 lần -> ghi
    đè sale_3. Người ĐANG phụ trách (để lọc/tính SLA) luôn là ô cuối cùng đã điền."""
    nguoi = leads.nguoi_online()
    if len(nguoi) < 3:
        pytest.skip("Cần ít nhất 3 người ở config/rules.yml phong_online.acc để kiểm thử.")
    pid = _page()
    a, b, c, d = nguoi[0]["acc_norm"], nguoi[1]["acc_norm"], nguoi[2]["acc_norm"], nguoi[1]["acc_norm"]
    lid = leads.tao_lead({"page_id": pid, "sale_1": a}, NGUOI)            # tạo lead: sale_1 = a
    r = leads.danh_sach().set_index("id").loc[lid]
    assert (r.sale_1, r.sale_2, r.sale_3, r.phu_trach) == (a, None, None, a)

    leads.nhan_cheo(lid, b, NGUOI)                                        # dội lần 1 -> sale_2
    r = leads.danh_sach().set_index("id").loc[lid]
    assert (r.sale_1, r.sale_2, r.sale_3, r.phu_trach) == (a, b, None, b)
    ten_b = {x["acc_norm"]: x["ten"] for x in nguoi}[b]
    assert r.sale_2_ten == ten_b and r.sale_1_ten == {x["acc_norm"]: x["ten"] for x in nguoi}[a]

    leads.nhan_cheo(lid, c, NGUOI)                                        # dội lần 2 -> sale_3
    r = leads.danh_sach().set_index("id").loc[lid]
    assert (r.sale_1, r.sale_2, r.sale_3, r.phu_trach) == (a, b, c, c)

    leads.nhan_cheo(lid, d, NGUOI)                                        # dội lần 3 (quá 3 người) -> GHI ĐÈ sale_3
    r = leads.danh_sach().set_index("id").loc[lid]
    assert (r.sale_1, r.sale_2, r.sale_3, r.phu_trach) == (a, b, d, d)

    # lọc theo "sale" của danh_sach() phải lọc theo NGƯỜI ĐANG PHỤ TRÁCH, không phải sale_1
    assert lid in set(leads.danh_sach(sale=d).id) and lid not in set(leads.danh_sach(sale=a).id)


def test_nhan_lead_nguoi_khong_hop_le_bi_tu_choi():
    pid = _page()
    lid = leads.tao_lead({"page_id": pid}, NGUOI)
    with pytest.raises(leads.LoiLead):
        leads.nhan_cheo(lid, "khong-phai-trong-nhom", NGUOI)


def test_ghi_chu_gom_chung_mot_o_tu_do():
    """Chốt 20/11/2026: Địa chỉ/Nhu cầu/KH dùng mạng/Mô hình/Tư vấn cũ gộp thành một ô `ghi_chu` tự do."""
    pid = _page()
    lid = leads.tao_lead({"page_id": pid, "ghi_chu": "123 Trần Phú, cần lắp gấp"}, NGUOI)
    r = leads.danh_sach().set_index("id").loc[lid]
    assert r.ghi_chu == "123 Trần Phú, cần lắp gấp"
    leads.cap_nhat_lead(lid, {"ghi_chu": "Đã gọi, hẹn chiều mai"}, NGUOI)
    assert leads.danh_sach().set_index("id").loc[lid].ghi_chu == "Đã gọi, hẹn chiều mai"


def test_xoa_lead_xoa_dung_dong_da_chon_con_lai_giu_nguyen():
    """Thêm 20/11/2026 (nối nút "Xoá lead đã chọn" trên bảng vào `leads.xoa_lead` có sẵn): chỉ xoá đúng
    id được chọn, id lạ bị bỏ qua, trả về đúng số dòng đã xoá."""
    pid = _page()
    lid1 = leads.tao_lead({"page_id": pid, "ten_kh": "A"}, NGUOI)
    lid2 = leads.tao_lead({"page_id": pid, "ten_kh": "B"}, NGUOI)
    n = leads.xoa_lead([lid1, 999999], NGUOI)
    assert n == 1
    con_lai = set(leads.danh_sach().id)
    assert con_lai == {lid2}


def test_luu_fb_cau_hinh_can_du_fb_page_id_va_token():
    pid = _page()
    with pytest.raises(leads.LoiLead):
        leads.luu_fb_cau_hinh(pid, "", "tok", NGUOI)
    leads.luu_fb_cau_hinh(pid, "1234567890", "tok-bi-mat", NGUOI)
    pages = leads.ds_page()
    assert pages[pages.id == pid].iloc[0].fb_page_id == "1234567890"
