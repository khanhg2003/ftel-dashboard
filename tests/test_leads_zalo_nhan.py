"""Kiểm thử app/leads_zalo_nhan.py + đường POST /api/lead/zalo-webhook: nhận lead bằng cách trả lời kèm
mã trong nhóm Zalo. Chặn mạng hoàn toàn: gui_tin bị monkeypatch, không gọi Zalo thật."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import delete

from app import canh_bao_lead as cb
from app import leads, leads_zalo_nhan as lzn, zalo_bot
from app.bo_nho import xoa as xoa_nho
from app.db import session_scope
from app.models import CrmPage, Lead, LeadNguoiNhanCanhBao, LeadZaloTin

NGUOI = "kiemthu"
NHOM = "g-lead-1"
HIEU, HAO = "dng.hieunt310", "dng.haoctp2"


@pytest.fixture(autouse=True)
def don_dep(monkeypatch):
    leads.dam_bao_bang()
    cb.dam_bao_bang()
    lzn.dam_bao_bang()
    monkeypatch.setattr(leads, "nguoi_online", lambda: [
        {"acc_norm": HIEU, "ten": "Ngô Trung Hiếu"}, {"acc_norm": HAO, "ten": "Cao Trần Phong Hào"}])

    def xoa():
        with session_scope() as s:
            s.execute(delete(Lead))
            s.execute(delete(CrmPage))
            s.execute(delete(LeadNguoiNhanCanhBao))
            s.execute(delete(LeadZaloTin))
        xoa_nho()
    xoa()
    cb.luu_nguoi_nhan(None, "leader", "Nhóm Lead", NHOM, None, True, NGUOI)
    yield
    xoa()


def _page() -> int:
    leads.them_page("Hải Phòng", None, NGUOI)
    df = leads.ds_page()
    return int(df.iloc[0].id)


def _lead(sale: str | None = None) -> int:
    return leads.tao_lead({"page_id": _page(), "sale_1": sale}, NGUOI)


@pytest.fixture
def gui(monkeypatch):
    goi = []
    monkeypatch.setattr(zalo_bot, "gui_tin", lambda c, n, *a, **k: goi.append((c, n)))
    return goi


@pytest.fixture
def may():
    from app.ui.app import server
    return server.test_client()


def _su_kien(text, chat=NHOM, ma="m1", bot=False):
    return {"message": {"message_id": ma, "date": 1, "text": text,
                        "from": {"id": "u1", "is_bot": bot}, "chat": {"id": chat, "chat_type": "GROUP"}}}


def _gui_webhook(may, payload, khoa="dung"):
    h = {} if khoa is None else {"X-Bot-Api-Secret-Token": lzn.khoa_webhook() if khoa == "dung" else khoa}
    return may.post("/api/lead/zalo-webhook", data=json.dumps(payload), content_type="application/json", headers=h)


def test_khoa_sai_hoac_thieu_thi_403(may, gui):
    assert _gui_webhook(may, _su_kien("x"), khoa=None).status_code == 403
    assert _gui_webhook(may, _su_kien("x"), khoa="sai").status_code == 403
    assert not gui


def test_nhan_dung_ma_dung_ten_thi_dien_sale_1(may, gui):
    """Lead chưa gán (sale_1 trống) - "Hiếu nhận #id" điền thẳng vào sale_1 (chưa phải dội nên chưa qua sale_2)."""
    lid = _lead()
    r = _gui_webhook(may, _su_kien(f"Hiếu nhận #{lid}"))
    assert r.status_code == 200
    df = leads.danh_sach()
    row = df[df.id == lid].iloc[0]
    assert row.sale_1 == HIEU and row.sale_2 is None
    assert len(gui) == 1
    assert str(lid) in gui[0][1] and "Hiếu" in gui[0][1]


def test_nhan_lead_da_co_sale_1_thi_dien_sale_2(may, gui):
    """Lead đã gán cho Hào (sale_1 = Hào) - "Hiếu nhận #id" là dội lần 1, điền vào sale_2."""
    lid = _lead(sale=HAO)
    _gui_webhook(may, _su_kien(f"Hiếu nhận #{lid}"))
    row = leads.danh_sach().set_index("id").loc[lid]
    assert row.sale_1 == HAO and row.sale_2 == HIEU


def test_khong_co_ma_thi_bo_qua_khong_tra_loi(may, gui):
    assert _gui_webhook(may, _su_kien("chào cả nhà, hôm nay mệt quá")).status_code == 200
    assert not gui


def test_tu_nhom_khac_thi_bo_qua(may, gui):
    lid = _lead()
    assert _gui_webhook(may, _su_kien(f"Hiếu nhận #{lid}", chat="nhom-la")).status_code == 200
    assert not gui
    df = leads.danh_sach()
    assert df[df.id == lid].iloc[0].sale_1 is None


def test_lead_da_dong_thi_bao_da_xong_khong_gan_lai(may, gui):
    lid = _lead(sale=HAO)
    leads.cap_nhat_lead(lid, {"tinh_trang_xu_ly": "Đã chốt"}, NGUOI)
    _gui_webhook(may, _su_kien(f"Hiếu nhận #{lid}"))
    assert len(gui) == 1 and "đã xong" in gui[0][1]
    df = leads.danh_sach()
    assert df[df.id == lid].iloc[0].sale_1 == HAO     # không bị đổi sang Hiếu


def test_khong_ro_ten_thi_hoi_lai(may, gui):
    lid = _lead()
    _gui_webhook(may, _su_kien(f"ai nhận hộ #{lid} với"))
    assert len(gui) == 1 and "tên" in gui[0][1].lower()
    df = leads.danh_sach()
    assert df[df.id == lid].iloc[0].sale_1 is None


def test_lead_khong_ton_tai_thi_bao_khong_tim_thay(may, gui):
    _gui_webhook(may, _su_kien("Hiếu nhận #999999"))
    assert len(gui) == 1 and "Không tìm thấy" in gui[0][1]


def test_cung_message_id_chi_xu_ly_mot_lan(may, gui):
    lid = _lead()
    su = _su_kien(f"Hiếu nhận #{lid}", ma="m-trung")
    _gui_webhook(may, su)
    _gui_webhook(may, su)                                  # Zalo gửi lại sự kiện
    assert len(gui) == 1


def test_tin_cua_chinh_bot_khong_xu_ly(may, gui):
    lid = _lead()
    _gui_webhook(may, _su_kien(f"Hiếu nhận #{lid}", bot=True))
    assert not gui
