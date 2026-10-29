"""Kiểm thử thêm người nhận Bản tin bằng cách nhắn bot (webhook Zalo + danh sách chờ duyệt). Chặn mạng hoàn toàn."""
from __future__ import annotations

import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import ban_tin as bt                                           # noqa: E402
from app import ban_tin_cho_duyet as cd                                  # noqa: E402
from app import zalo_bot                                                 # noqa: E402
from app.config import DATA_DIR                                          # noqa: E402

pytestmark = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(),
                                reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")
TOKEN = "123456:TOKEN-BI-MAT"


def _su_kien(chat_id="u1", ten="Chị Lan", loai="PRIVATE", bot=False, ev="message.text.received", text="xin chào"):
    return {"event_name": ev, "message": {"message_id": "m", "date": 1, "message_type": "TEXT", "text": text,
                                          "from": {"id": chat_id, "display_name": ten, "is_bot": bot},
                                          "chat": {"id": chat_id, "chat_type": loai}}}


@pytest.fixture(autouse=True)
def moi_truong(monkeypatch):
    from sqlalchemy import delete

    from app.db import session_scope
    from app.models import BanTinChoDuyet, BanTinNguoiNhan

    def don():
        with session_scope() as s:
            s.execute(delete(BanTinChoDuyet))
            s.execute(delete(BanTinNguoiNhan))
    bt.dam_bao_bang()
    cd.dam_bao_bang()
    don()
    monkeypatch.setenv("ZALO_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("APP_URL", "https://app.example.vn/")
    tin = []
    monkeypatch.setattr(zalo_bot, "gui_tin", lambda c, n, *a, **k: tin.append((c, n)))
    yield tin
    don()


@pytest.fixture()
def tin(moi_truong):
    return moi_truong


@pytest.fixture()
def may_khach():
    from app.ui.app import server
    return server.test_client()


def _gui(c, payload, khoa="dung"):
    h = {} if khoa is None else {"X-Bot-Api-Secret-Token": cd.khoa_webhook() if khoa == "dung" else khoa}
    return c.post("/api/ban-tin/zalo-webhook", data=json.dumps(payload) if payload is not None else "",
                  content_type="application/json", headers=h)


# ------------------------------------------------------------------ khoá
def test_khoa_dan_xuat_dai_vua_phai_va_on_dinh():
    k = cd.khoa_webhook()
    assert 8 <= len(k) <= 256 and k == cd.khoa_webhook()
    from app.config import SECRET_KEY
    assert SECRET_KEY not in k


def test_sai_hoac_thieu_khoa_403_giong_nhau(may_khach, tin):
    a, b, c = _gui(may_khach, _su_kien(), None), _gui(may_khach, _su_kien(), "sai"), _gui(may_khach, _su_kien(), "")
    assert a.status_code == b.status_code == c.status_code == 403
    assert a.get_data() == b.get_data() == c.get_data()
    assert cd.ds_cho_duyet() == [] and tin == []


# ------------------------------------------------------------------ nhận tin
def test_tin_rieng_vao_cho_va_chao_dung_mot_lan(may_khach, tin):
    r = _gui(may_khach, _su_kien("u1", "Chị Lan"))
    assert r.status_code == 200
    ds = cd.ds_cho_duyet()
    assert len(ds) == 1 and ds[0]["chat_id"] == "u1" and ds[0]["ten"] == "Chị Lan" and ds[0]["nhan_cuoi"]
    assert tin == [("u1", cd.LOI_CHAO)]
    assert _gui(may_khach, _su_kien("u1", "Chị Lan Mới", text="hi lần hai")).status_code == 200
    ds = cd.ds_cho_duyet()
    assert len(ds) == 1 and ds[0]["ten"] == "Chị Lan Mới" and len(tin) == 1


def test_khong_luu_noi_dung_tin_nhan(may_khach):
    _gui(may_khach, _su_kien(text="NOI-DUNG-RIENG-TU-123"))
    from sqlalchemy import select

    from app.db import session_scope
    from app.models import BanTinChoDuyet
    with session_scope() as s:
        r = s.execute(select(BanTinChoDuyet)).scalar_one()
        gia_tri = json.dumps({c.name: str(getattr(r, c.name)) for c in r.__table__.columns})
    assert "NOI-DUNG-RIENG-TU-123" not in gia_tri


@pytest.mark.parametrize("payload", [
    _su_kien(bot=True), _su_kien(loai="GROUP"), _su_kien(ev="user.joined"), _su_kien(chat_id=""),
    {"event_name": "message.text.received"}, {"event_name": "message.text.received", "message": "x"}, [1, 2], {},
])
def test_su_kien_khong_dung_duoc_bi_bo_qua_nhung_tra_200(may_khach, tin, payload):
    assert _gui(may_khach, payload).status_code == 200
    assert cd.ds_cho_duyet() == [] and tin == []


def test_khong_phai_json_van_200(may_khach):
    r = may_khach.post("/api/ban-tin/zalo-webhook", data="khong phai json", content_type="text/plain",
                       headers={"X-Bot-Api-Secret-Token": cd.khoa_webhook()})
    assert r.status_code == 200 and cd.ds_cho_duyet() == []


def test_da_la_nguoi_nhan_khong_vao_cho(may_khach, tin):
    bt.luu_nguoi_nhan(None, "Anh Nam", "bgd", "u9", True)
    assert _gui(may_khach, _su_kien("u9")).status_code == 200
    assert cd.ds_cho_duyet() == [] and tin == []


def test_loi_gui_loi_chao_khong_lam_hong_viec_ghi(may_khach, monkeypatch):
    def hong(*a, **k):
        raise zalo_bot.LoiZalo("Zalo từ chối (mã 400): giả lập.")
    monkeypatch.setattr(zalo_bot, "gui_tin", hong)
    assert _gui(may_khach, _su_kien("u2")).status_code == 200
    assert len(cd.ds_cho_duyet()) == 1


# ------------------------------------------------------------------ duyệt / bỏ qua
def test_duyet_tao_nguoi_nhan_va_xoa_khoi_cho(may_khach, tin):
    _gui(may_khach, _su_kien("u1", "Chị Lan"))
    id_ = cd.ds_cho_duyet()[0]["id"]
    ok, _ = cd.duyet(id_, "Chị Lan (Kế toán)", "admin")
    assert ok and cd.ds_cho_duyet() == []
    n = bt.ds_nguoi_nhan()
    assert len(n) == 1 and (n[0]["ten"], n[0]["loai"], n[0]["chat_id"], n[0]["bat"]) == (
        "Chị Lan (Kế toán)", "admin", "u1", True)
    assert not cd.duyet(id_, "x", "bgd")[0]           # duyệt lần hai: dòng đã mất


def test_duyet_loai_sai_giu_nguyen_dong_cho(may_khach):
    _gui(may_khach, _su_kien("u1"))
    assert not cd.duyet(cd.ds_cho_duyet()[0]["id"], "A", "la")[0]
    assert len(cd.ds_cho_duyet()) == 1 and bt.ds_nguoi_nhan() == []


def test_bo_qua_xoa_khoi_cho_va_nhan_lai_hien_lai(may_khach, tin):
    _gui(may_khach, _su_kien("u1"))
    assert cd.bo_qua([cd.ds_cho_duyet()[0]["id"]]) == 1 and cd.ds_cho_duyet() == []
    _gui(may_khach, _su_kien("u1"))
    assert len(cd.ds_cho_duyet()) == 1 and bt.ds_nguoi_nhan() == []


# ------------------------------------------------------------------ setWebhook / deleteWebhook / getWebhookInfo
class _Tra:
    def __init__(self, noi_dung):
        self.noi_dung = noi_dung

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self.noi_dung).encode()


@pytest.fixture()
def mang(monkeypatch):
    """Giả `urlopen`: ghi lại từng lệnh gọi; `mang.tra` quyết định phản hồi."""
    class M:
        lan: list = []
        tra = {"ok": True, "result": {"url": "https://app.example.vn/api/ban-tin/zalo-webhook",
                                      "verification": {"ok": True, "outcome": "webhook.ok"}}}
        loi = None

    m = M()
    m.lan = []

    def mo(req, timeout):
        m.lan.append((req.full_url, json.loads(req.data)))
        if m.loi:
            raise m.loi
        return _Tra(m.tra)
    monkeypatch.setattr(zalo_bot.urllib.request, "urlopen", mo)
    return m


def test_ket_noi_gui_dung_url_va_khoa_dan_xuat(mang):
    muc, chu = cd.ket_noi()
    assert muc == "ok" and "Đã kết nối" in chu
    url, goi = mang.lan[0]
    assert url.endswith("/setWebhook")
    assert goi == {"url": "https://app.example.vn/api/ban-tin/zalo-webhook", "secret_token": cd.khoa_webhook()}


def test_ket_noi_khong_co_app_url_thi_khong_goi_zalo(mang, monkeypatch):
    monkeypatch.delenv("APP_URL")
    muc, chu = cd.ket_noi()
    assert muc == "bad" and "APP_URL" in chu and mang.lan == []


def test_ket_noi_chua_cai_token_thi_khong_goi_zalo(mang, monkeypatch):
    monkeypatch.delenv("ZALO_BOT_TOKEN")
    assert cd.ket_noi()[0] == "bad" and mang.lan == []


def test_ket_noi_zalo_thu_hong_bao_canh_bao(mang):
    mang.tra = {"ok": True, "result": {"url": "u", "verification": {"ok": False, "outcome": "webhook.http.404"}}}
    muc, chu = cd.ket_noi()
    assert muc == "warn" and "webhook.http.404" in chu


def test_loi_khong_lo_token(mang):
    e = urllib.error.HTTPError("https://x", 400, "x", {}, io.BytesIO(
        json.dumps({"description": f"bad url {TOKEN} nhe"}).encode()))
    mang.loi = e
    for ham in (cd.ket_noi, cd.ngat_ket_noi, cd.trang_thai_webhook):
        muc, chu = ham()
        assert muc in ("bad", "warn") and TOKEN not in chu and "TOKEN-BI-MAT" not in chu
    mang.loi = None
    mang.tra = {"ok": False, "error_code": 400, "description": f"loi {TOKEN}"}
    muc, chu = cd.ket_noi()
    assert muc == "bad" and TOKEN not in chu


def test_ngat_ket_noi_goi_deletewebhook(mang):
    mang.tra = {"ok": True, "result": {"url": ""}}
    muc, chu = cd.ngat_ket_noi()
    assert muc == "ok" and mang.lan[0][0].endswith("/deleteWebhook") and "không tự hiện" in chu


@pytest.mark.parametrize("url_dang_dat,muc", [
    ("https://app.example.vn/api/ban-tin/zalo-webhook", "ok"),
    ("", "warn"),
    ("https://noi-khac.vn/hook", "warn"),
])
def test_trang_thai_webhook(mang, url_dang_dat, muc):
    mang.tra = {"ok": True, "result": {"url": url_dang_dat, "updated_at": 1}}
    m, chu = cd.trang_thai_webhook()
    assert m == muc and mang.lan[0][0].endswith("/getWebhookInfo")
    if url_dang_dat and muc == "warn":
        assert "địa chỉ khác" in chu

