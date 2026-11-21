"""Kiểm thử app/canh_bao_lead.py: quét SLA, chọn người nhận, gửi Zalo. Chặn mạng: giả lập
`zalo_bot.gui_tin_du_phong` (không gọi Zalo thật)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import delete

from app import canh_bao_lead as cb
from app import leads, zalo_bot
from app.bo_nho import xoa as xoa_nho
from app.db import session_scope
from app.models import CrmPage, Lead, LeadNguoiNhanCanhBao

NGUOI = "kiemthu"


@pytest.fixture(autouse=True)
def don_dep():
    leads.dam_bao_bang()
    cb.dam_bao_bang()

    def xoa():
        with session_scope() as s:
            s.execute(delete(Lead))
            s.execute(delete(LeadNguoiNhanCanhBao))
            s.execute(delete(CrmPage))
        xoa_nho()
    xoa()
    yield
    xoa()


@pytest.fixture
def gui_gia(monkeypatch):
    """(danh sách tin đã gửi, tập chat_id sẽ gây lỗi khi gửi)."""
    goi: list[tuple[str, str]] = []
    hong: set[str] = set()

    def gia(chat_id, noi_dung, han=8, token=None):
        if chat_id in hong:
            raise zalo_bot.LoiZalo("Zalo từ chối (mã 400): giả lập.")
        goi.append((chat_id, noi_dung))
        return False
    monkeypatch.setattr(zalo_bot, "gui_tin_du_phong", gia)
    return goi, hong


def _page() -> int:
    leads.them_page("Hải Phòng", None, NGUOI)
    return int(leads.ds_page().iloc[0].id)


def _qua_han(lead_id: int) -> None:
    with session_scope() as s:
        s.get(Lead, lead_id).cap_nhat_luc = datetime.utcnow() - timedelta(hours=30)
    xoa_nho("leads")


def test_them_sua_xoa_nguoi_nhan():
    ok, msg = cb.luu_nguoi_nhan(None, "leader", "Sếp A", "chat:1", None, True, NGUOI)
    assert ok, msg
    ds = cb.ds_nguoi_nhan()
    assert len(ds) == 1 and ds[0]["vai_tro"] == "leader" and ds[0]["acc_norm"] is None
    n = cb.xoa_nguoi_nhan([ds[0]["id"]], NGUOI)
    assert n == 1 and not cb.ds_nguoi_nhan()


def test_luu_nguoi_nhan_thieu_ten_hoac_chat_id_bao_loi():
    ok, _msg = cb.luu_nguoi_nhan(None, "leader", "", "chat:1", None, True, NGUOI)
    assert not ok


def test_quet_bo_qua_lead_chua_qua_han(gui_gia):
    goi, _ = gui_gia
    pid = _page()
    leads.tao_lead({"page_id": pid, "ten_kh": "Mới tinh"}, NGUOI)
    kq = cb.quet_va_canh_bao()
    assert kq["qua_han"] == 0 and not goi


def test_quet_bao_dung_sale_phu_trach(gui_gia):
    goi, _ = gui_gia
    nguoi = leads.nguoi_online()
    if not nguoi:
        pytest.skip("Chưa cấu hình config/rules.yml phong_online.acc.")
    a = nguoi[0]["acc_norm"]
    pid = _page()
    lid = leads.tao_lead({"page_id": pid, "ten_kh": "Khách trễ", "sale_1": a}, NGUOI)
    cb.luu_nguoi_nhan(None, "sale", "A", "chat:a", a, True, NGUOI)
    _qua_han(lid)
    kq = cb.quet_va_canh_bao()
    assert kq["qua_han"] == 1 and kq["da_bao"] == 1
    assert "chat:a" in {c for c, _ in goi}


def test_khong_nhac_lai_trong_chu_ky(gui_gia):
    goi, _ = gui_gia
    nguoi = leads.nguoi_online()
    if not nguoi:
        pytest.skip("Chưa cấu hình config/rules.yml phong_online.acc.")
    a = nguoi[0]["acc_norm"]
    pid = _page()
    lid = leads.tao_lead({"page_id": pid, "sale_1": a}, NGUOI)
    cb.luu_nguoi_nhan(None, "sale", "A", "chat:a", a, True, NGUOI)
    _qua_han(lid)
    cb.quet_va_canh_bao()
    assert goi
    goi.clear()
    cb.quet_va_canh_bao()            # vừa báo xong, chưa đủ CHU_KY_NHAC_LAI_GIO -> không gửi lại
    assert not goi


def test_lan_quet_gan_nhat_tach_dung_so_tu_chi_tiet(gui_gia):
    """Thêm 21/11/2026: sơ đồ quy trình trên trang /leads cần số "đã báo" của lần quét gần nhất, tách ra
    từ chuỗi `chi_tiet` đã ghi trong AuditLog (không thêm cột mới)."""
    nguoi = leads.nguoi_online()
    if not nguoi:
        pytest.skip("Chưa cấu hình config/rules.yml phong_online.acc.")
    a = nguoi[0]["acc_norm"]
    pid = _page()
    lid = leads.tao_lead({"page_id": pid, "sale_1": a}, NGUOI)
    cb.luu_nguoi_nhan(None, "sale", "A", "chat:a", a, True, NGUOI)
    _qua_han(lid)
    cb.quet_va_canh_bao()
    lan = cb.lan_quet_gan_nhat()
    assert lan["qua_han"] == 1 and lan["da_bao"] == 1 and lan["loi"] == 0


def test_loi_gui_cho_mot_nguoi_khong_chan_nguoi_khac(gui_gia):
    goi, hong = gui_gia
    nguoi = leads.nguoi_online()
    if not nguoi:
        pytest.skip("Chưa cấu hình config/rules.yml phong_online.acc.")
    a = nguoi[0]["acc_norm"]
    pid = _page()
    lid = leads.tao_lead({"page_id": pid, "sale_1": a}, NGUOI)
    cb.luu_nguoi_nhan(None, "sale", "A", "chat:a", a, True, NGUOI)
    cb.luu_nguoi_nhan(None, "leader", "Sếp", "chat:sep", None, True, NGUOI)
    hong.add("chat:a")
    _qua_han(lid)
    kq = cb.quet_va_canh_bao()
    assert kq["da_bao"] == 1
    assert "chat:sep" in {c for c, _ in goi}
    assert kq["loi"]
