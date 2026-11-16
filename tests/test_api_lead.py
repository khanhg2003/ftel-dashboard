"""Kiểm thử app/api_lead.py: đường cron cảnh báo SLA + webhook Messenger (xác thực, không gọi Facebook/Zalo thật)."""
from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from sqlalchemy import delete

from app import leads, leads_messenger
from app.bo_nho import xoa as xoa_nho
from app.db import session_scope
from app.models import CrmPage, Lead

NGUOI = "kiemthu"
SECRET = "secret-thu"


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


@pytest.fixture
def may(monkeypatch):
    from app.ui.app import server
    monkeypatch.setenv("LEAD_CANH_BAO_KHOA", "khoa-thu")
    monkeypatch.setenv("FB_WEBHOOK_VERIFY_TOKEN", "verify-thu")
    monkeypatch.setenv("FB_APP_SECRET", SECRET)
    monkeypatch.setattr(leads_messenger, "ten_khach", lambda psid, token: None)      # chặn gọi Graph API thật
    return server.test_client()


def _ky(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def test_canh_bao_sai_hoac_thieu_khoa_la_403(may):
    assert may.post("/api/lead/canh-bao").status_code == 403
    assert may.post("/api/lead/canh-bao", headers={"X-Lead-Khoa": "sai"}).status_code == 403


def test_canh_bao_dung_khoa_goi_quet_va_tra_ket_qua(may, monkeypatch):
    goi = {}

    def gia():
        goi["chay"] = True
        return {"quet": 0, "qua_han": 0, "da_bao": 0, "loi": []}
    from app import canh_bao_lead
    monkeypatch.setattr(canh_bao_lead, "quet_va_canh_bao", gia)
    r = may.post("/api/lead/canh-bao", headers={"X-Lead-Khoa": "khoa-thu"})
    assert r.status_code == 200 and r.get_json()["ok"] is True and goi.get("chay")


def test_fb_verify_dung_token_tra_challenge(may):
    r = may.get("/api/lead/fb-webhook?hub.mode=subscribe&hub.verify_token=verify-thu&hub.challenge=abc123")
    assert r.status_code == 200 and r.get_data(as_text=True) == "abc123"


def test_fb_verify_sai_token_bi_tu_choi(may):
    r = may.get("/api/lead/fb-webhook?hub.mode=subscribe&hub.verify_token=sai&hub.challenge=abc123")
    assert r.status_code == 403


def test_fb_webhook_sai_chu_ky_bi_tu_choi_403(may):
    body = json.dumps({"entry": []}).encode()
    r = may.post("/api/lead/fb-webhook", data=body,
                 headers={"X-Hub-Signature-256": "sha256=sai", "Content-Type": "application/json"})
    assert r.status_code == 403


def test_fb_webhook_dung_chu_ky_tao_lead_moi(may):
    leads.them_page("Hải Phòng", None, NGUOI)
    pid = int(leads.ds_page().iloc[0].id)
    leads.luu_fb_cau_hinh(pid, "fb-page-1", "token-gia", NGUOI)
    payload = {"entry": [{"id": "fb-page-1", "messaging": [
        {"sender": {"id": "psid-1"}, "message": {"text": "em muốn lắp mạng, sđt 0912345678"}}]}]}
    body = json.dumps(payload).encode()
    r = may.post("/api/lead/fb-webhook", data=body,
                 headers={"X-Hub-Signature-256": _ky(body), "Content-Type": "application/json"})
    assert r.status_code == 200
    xoa_nho("leads")
    df = leads.danh_sach()
    assert len(df) == 1
    r0 = df.iloc[0]
    assert r0.sdt == "0912345678" and r0.nguon == "messenger" and r0.tinh_trang_xu_ly == "Mới"


def test_fb_webhook_tin_nhan_tiep_theo_cap_nhat_cung_mot_lead(may):
    leads.them_page("Hải Phòng", None, NGUOI)
    pid = int(leads.ds_page().iloc[0].id)
    leads.luu_fb_cau_hinh(pid, "fb-page-1", "token-gia", NGUOI)
    for text in ("chào shop", "em ở quận Hồng Bàng"):
        payload = {"entry": [{"id": "fb-page-1", "messaging": [
            {"sender": {"id": "psid-1"}, "message": {"text": text}}]}]}
        body = json.dumps(payload).encode()
        may.post("/api/lead/fb-webhook", data=body,
                headers={"X-Hub-Signature-256": _ky(body), "Content-Type": "application/json"})
    xoa_nho("leads")
    df = leads.danh_sach()
    assert len(df) == 1 and "Hồng Bàng" in (df.iloc[0].tu_van_1 or "")


def test_fb_webhook_page_chua_cau_hinh_bi_bo_qua_nhung_van_tra_200(may):
    payload = {"entry": [{"id": "fb-page-la", "messaging": [
        {"sender": {"id": "psid-1"}, "message": {"text": "xin chào"}}]}]}
    body = json.dumps(payload).encode()
    r = may.post("/api/lead/fb-webhook", data=body,
                 headers={"X-Hub-Signature-256": _ky(body), "Content-Type": "application/json"})
    assert r.status_code == 200
    xoa_nho("leads")
    assert leads.danh_sach().empty
