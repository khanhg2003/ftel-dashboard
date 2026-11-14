"""Đường webhook Zalo của bot giao việc liên khối (nhánh thi-lien-khoi): mặc định đóng, chỉ nhận tin chữ của người thật trong chat riêng,
xác thực bằng khoá riêng. Không có tin nào gửi ra ngoài (zalo_bot.gui_tin bị thay bằng hàm ghi lại)."""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from app import zalo_bot
from app.lien_khoi import luat, theo_doi as td, zalo_viec as zv

T0 = datetime(2026, 11, 14, 8, 0, 0)
NGUOI = pd.DataFrame([dict(ma="ktv_01", ten="KTV 01", khoi="KT", vai_tro="nhan_vien", quan_ly="", chat_id="c:ktv_01")])
DUONG_DAN = "/api/lien-khoi/zalo-webhook"


def _tin(chat_id="c:ktv_01", text="xong MHAAA0001", loai="PRIVATE", la_bot=False) -> dict:
    return {"event_name": "message.text.received", "message": {"message_id": "m1", "text": text, "chat": {"id": chat_id, "chat_type": loai},
                                                                "from": {"id": "u1", "is_bot": la_bot}}}


@pytest.fixture
def may(tmp_path, monkeypatch):
    from app.ui.app import server
    monkeypatch.setenv("LIEN_KHOI_DB", str(tmp_path / "td.db"))
    monkeypatch.setenv("LIEN_KHOI_NGUON", "that")
    monkeypatch.setenv("LIEN_KHOI_ZALO_TOKEN", "tok-thu")
    monkeypatch.setenv("LIEN_KHOI_ZALO_GUI", "1")
    monkeypatch.setattr(td, "nguoi_nhan", lambda: NGUOI)
    gui = []
    monkeypatch.setattr(zalo_bot, "gui_tin", lambda chat_id, chu, **k: gui.append((chat_id, chu)))
    v = pd.DataFrame([dict(so_hd="MHAAA0001", luat="su_co_lap", ten_luat="Sự cố lặp", muc="Cao", giao_sale="", giao_dvkh="", giao_kt="ktv_01", han="Trong 24 giờ",
                           phat_sinh=T0, ly_do="x", de_xuat="y")], columns=luat.COT_VIEC)
    td.dong_bo(v, T0)
    return server.test_client(), gui


def test_webhook_sai_hoac_thieu_khoa_la_403_va_khong_xu_ly_gi(may):
    client, gui = may
    assert client.post(DUONG_DAN, json=_tin()).status_code == 403
    assert client.post(DUONG_DAN, json=_tin(), headers={"X-Bot-Api-Secret-Token": "sai"}).status_code == 403
    assert not gui and td.danh_sach(T0)["trang_thai"].iloc[0] == "moi"


def test_webhook_dung_khoa_cap_nhat_viec_va_tra_loi_cho_nguoi_nhan(may):
    client, gui = may
    r = client.post(DUONG_DAN, json=_tin(), headers={"X-Bot-Api-Secret-Token": zv.khoa_webhook()})
    assert r.status_code == 200 and r.get_json() == {"ok": True}
    assert td.danh_sach(T0)["trang_thai"].iloc[0] == "da_xong"
    assert gui and gui[-1][0] == "c:ktv_01" and "MHAAA0001: Đã xong" in gui[-1][1]           # bot trả lời đúng người


def test_webhook_bo_qua_chat_nhom_tin_cua_bot_va_su_kien_la_nhung_van_tra_200(may):
    client, gui = may
    h = {"X-Bot-Api-Secret-Token": zv.khoa_webhook()}
    for goi in (_tin(loai="GROUP"), _tin(la_bot=True), {"event_name": "message.image.received", "message": {}}, {"linh": "tinh"}, None):
        assert client.post(DUONG_DAN, json=goi, headers=h).status_code == 200
    assert not gui and td.danh_sach(T0)["trang_thai"].iloc[0] == "moi"


def test_webhook_dong_khi_chua_cau_hinh_gui_that_hoac_dang_chay_minh_hoa(may, monkeypatch):
    client, gui = may
    h = {"X-Bot-Api-Secret-Token": zv.khoa_webhook()}
    monkeypatch.delenv("LIEN_KHOI_ZALO_GUI")
    assert client.post(DUONG_DAN, json=_tin(), headers=h).status_code == 403                 # chưa bật gửi thật
    monkeypatch.setenv("LIEN_KHOI_ZALO_GUI", "1")
    monkeypatch.setenv("LIEN_KHOI_NGUON", "demo")
    assert client.post(DUONG_DAN, json=_tin(), headers=h).status_code == 403                 # chạy minh hoạ: luôn đóng
    assert not gui


def test_khoa_webhook_khac_khoa_cua_cac_bot_khac_va_url_theo_app_url(monkeypatch):
    from app import zalo_gia
    assert zv.khoa_webhook() != zalo_gia.khoa_webhook() and len(zv.khoa_webhook()) == 64
    monkeypatch.setenv("APP_URL", "https://ten-app.example/")
    assert zv.url_webhook() == "https://ten-app.example" + DUONG_DAN
    monkeypatch.delenv("APP_URL")
    assert zv.url_webhook() is None
