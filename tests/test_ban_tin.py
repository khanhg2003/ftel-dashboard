"""Kiểm thử Bản tin 8h sáng qua Zalo Bot (giai đoạn 1: Ban Giám đốc + nhắc Admin). Chặn mạng: giả lập `zalo_bot.gui_tin`."""
from __future__ import annotations

import io
import json
import sys
import urllib.error
from datetime import date, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import ban_tin as bt                                           # noqa: E402
from app import metrics, overview, zalo_bot                             # noqa: E402
from app.config import DATA_DIR                                          # noqa: E402

pytestmark = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(),
                                reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")
NGAY = "2026-09-11"                       # ngày cuối của kỳ dữ liệu gốc
SANG_8H = datetime(2026, 9, 12, 8, 5)
CHOT = (False, datetime(2026, 9, 12, 7, 0))         # đã nạp lại từ 07:00 sáng hôm sau
KHOA = "khoa-bi-mat-thu"


class Gia:
    """Bản giả của `zalo_bot.gui_tin`: ghi lại từng tin, báo lỗi cho chat_id nằm trong `hong`."""

    def __init__(self):
        self.tin: list[tuple[str, str]] = []
        self.hong: set[str] = set()

    def __call__(self, chat_id, noi_dung, parse_mode=None, han=8, text_styles=None):
        if chat_id in self.hong:
            raise zalo_bot.LoiZalo("Zalo từ chối (mã 400): giả lập.")
        self.tin.append((chat_id, noi_dung))
        self.kieu = text_styles


@pytest.fixture()
def gia(monkeypatch):
    g = Gia()
    monkeypatch.setattr(zalo_bot, "gui_tin", g)
    return g


@pytest.fixture(autouse=True)
def moi_truong(monkeypatch):
    """Ngày số cố định, mặc định đã chốt; xoá người nhận + nhật ký trước / sau mỗi phép thử."""
    from sqlalchemy import delete

    from app.db import session_scope
    from app.models import BanTinNguoiNhan, BanTinNhatKy

    def don():
        with session_scope() as s:
            s.execute(delete(BanTinNhatKy))
            s.execute(delete(BanTinNguoiNhan))
    bt.dam_bao_bang()
    don()
    monkeypatch.setattr(metrics, "ngay_moi_nhat", lambda: NGAY)
    monkeypatch.setattr(overview, "trang_thai_ngay", lambda iso: CHOT)
    monkeypatch.delenv("APP_URL", raising=False)
    yield
    don()


def _them(ten, loai="bgd", chat="c1", bat=True):
    ok, _ = bt.luu_nguoi_nhan(None, ten, loai, chat, bat)
    assert ok


def _nhat_ky():
    from sqlalchemy import select

    from app.db import session_scope
    from app.models import BanTinNhatKy
    with session_scope() as s:
        return [(r.nguoi_nhan_id, r.loai, r.ket_qua, r.so_lan) for r in s.execute(select(BanTinNhatKy)).scalars()]


# ------------------------------------------------------------------ có gửi hay không
def test_chua_chot_khong_gui(gia, monkeypatch):
    _them("Anh A")
    monkeypatch.setattr(overview, "trang_thai_ngay", lambda iso: (True, datetime(2026, 9, 11, 14, 30)))
    kq = bt.chay(gio_vn=SANG_8H)
    assert gia.tin == [] and kq["da_gui"] == [] and "đang cập nhật" in kq["ly_do"]
    assert _nhat_ky() == []


def test_nap_truoc_6h_sang_hom_sau_van_chua_chot(gia, monkeypatch):
    _them("Anh A")
    monkeypatch.setattr(overview, "trang_thai_ngay", lambda iso: (False, datetime(2026, 9, 12, 5, 59)))
    assert bt.chay(gio_vn=SANG_8H)["da_gui"] == [] and gia.tin == []
    monkeypatch.setattr(overview, "trang_thai_ngay", lambda iso: (False, datetime(2026, 9, 12, 6, 0)))
    assert bt.chay(gio_vn=SANG_8H)["da_gui"] == ["Anh A"]


def test_da_chot_nhung_truoc_8h_khong_gui(gia):
    _them("Anh A")
    kq = bt.chay(gio_vn=datetime(2026, 9, 12, 7, 59))
    assert gia.tin == [] and "08:00" in kq["ly_do"]


def test_gui_dung_nguoi_bgd_dang_bat(gia):
    _them("Anh A", chat="a")
    _them("Chị B", chat="b", bat=False)
    _them("Admin", loai="admin", chat="ad")
    kq = bt.chay(gio_vn=SANG_8H)
    assert kq["da_gui"] == ["Anh A"] and [c for c, _ in gia.tin] == ["a"]
    assert "Số chốt ngày 11/09" in gia.tin[0][1]


def test_goi_hai_lan_khong_gui_trung(gia):
    _them("Anh A")
    bt.chay(gio_vn=SANG_8H)
    kq = bt.chay(gio_vn=SANG_8H)
    assert len(gia.tin) == 1 and kq["da_gui"] == []


def test_da_ok_khong_gui_lai_ke_ca_khi_so_doi(gia, monkeypatch):
    _them("Anh A")
    bt.chay(gio_vn=SANG_8H)
    monkeypatch.setattr(overview, "trang_thai_ngay", lambda iso: (False, datetime(2026, 9, 12, 9, 30)))  # nạp lại
    bt.chay(gio_vn=datetime(2026, 9, 12, 9, 45))
    assert len(gia.tin) == 1


def test_loi_thi_thu_lai_roi_ok_thi_thoi(gia):
    _them("Anh A", chat="a")
    gia.hong.add("a")
    kq = bt.chay(gio_vn=SANG_8H)
    assert kq["loi"][0]["nguoi"] == "Anh A" and "giả lập" in kq["loi"][0]["ly_do"]
    assert _nhat_ky()[0][2:] == ("loi", 1)
    gia.hong.clear()
    assert bt.chay(gio_vn=SANG_8H)["da_gui"] == ["Anh A"]
    assert _nhat_ky()[0][2:] == ("ok", 2)
    bt.chay(gio_vn=SANG_8H)
    assert len(gia.tin) == 1


def test_loi_mai_chi_thu_toi_da_vai_lan(gia):
    _them("Anh A", chat="a")
    gia.hong.add("a")
    for _ in range(bt.TOI_DA_LAN + 3):
        bt.chay(gio_vn=SANG_8H)
    assert _nhat_ky()[0][3] == bt.TOI_DA_LAN


def test_mot_nguoi_loi_khong_chan_nguoi_khac(gia):
    _them("Anh A", chat="a")
    _them("Anh B", chat="b")
    gia.hong.add("a")
    kq = bt.chay(gio_vn=SANG_8H)
    assert kq["da_gui"] == ["Anh B"] and len(kq["loi"]) == 1


def test_loi_bat_ngo_khong_lam_sap_luot(gia, monkeypatch):
    _them("Anh A")
    monkeypatch.setattr(zalo_bot, "gui_tin", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("https://x/botSECRET")))
    kq = bt.chay(gio_vn=SANG_8H)
    assert "SECRET" not in json.dumps(kq, ensure_ascii=False) and kq["loi"]
    assert "SECRET" not in str(_nhat_ky())


def test_giu_cho_chi_mot_nguoi_thang():
    _them("Anh A")
    nguoi = bt.ds_nguoi_nhan()[0]
    ngay = date.fromisoformat(NGAY)
    assert bt._giu_cho(ngay, nguoi, "bgd") is not None
    assert bt._giu_cho(ngay, nguoi, "bgd") is None          # đang gửi, chưa quá hạn


# ------------------------------------------------------------------ nhắc admin
def test_nhac_admin_sau_1030_dung_mot_lan(gia, monkeypatch):
    _them("Anh A", chat="a")
    _them("Admin", loai="admin", chat="ad")
    monkeypatch.setattr(overview, "trang_thai_ngay", lambda iso: (True, datetime(2026, 9, 11, 14, 30)))
    assert bt.chay(gio_vn=datetime(2026, 9, 12, 10, 29))["da_gui"] == []
    kq = bt.chay(gio_vn=datetime(2026, 9, 12, 10, 30))
    assert kq["da_gui"] == ["Admin"] and gia.tin == [("ad", "Chưa có số chốt của ngày 11/09, hãy nạp file.")]
    bt.chay(gio_vn=datetime(2026, 9, 12, 10, 45))
    assert len(gia.tin) == 1


def test_da_chot_thi_khong_nhac_admin(gia):
    _them("Admin", loai="admin", chat="ad")
    bt.chay(gio_vn=datetime(2026, 9, 12, 10, 45))
    assert gia.tin == []


# ------------------------------------------------------------------ chạy thử
def test_kho_khong_gui_khong_ghi(gia):
    _them("Anh A")
    kq = bt.chay(gio_vn=SANG_8H, kho=True)
    assert gia.tin == [] and _nhat_ky() == []
    assert kq["se_gui"] is True and kq["nguoi_nhan"] == ["Anh A"] and "Số chốt ngày 11/09" in kq["noi_dung"]


def test_kho_van_dung_noi_dung_khi_chua_chot(gia, monkeypatch):
    monkeypatch.setattr(overview, "trang_thai_ngay", lambda iso: (True, datetime(2026, 9, 11, 14, 30)))
    kq = bt.chay(gio_vn=SANG_8H, kho=True)
    assert kq["se_gui"] is False and kq["noi_dung"]


# ------------------------------------------------------------------ nội dung
def test_noi_dung_dung_khuon_va_gioi_han():
    chu = bt.dung_noi_dung_bgd(NGAY)
    assert len(chu) <= 2000
    for cum in ("Số chốt ngày 11/09", "1) TỔNG QUAN", "Online luỹ kế", "Dự báo cuối tháng", "2) PHÒNG CẦN CHÚ Ý"):
        assert cum in chu
    assert "đấu nối" not in chu.lower() and "Xem chi tiết" not in chu
    import re
    assert re.search(r"Dự báo cuối tháng: [\d.]+ \([\d.]+\)", chu)       # hai số song song "3.892 (4.134)"


def test_noi_dung_co_link_khi_dat_app_url(monkeypatch):
    monkeypatch.setenv("APP_URL", "https://bao-cao.example")
    assert bt.dung_noi_dung_bgd(NGAY).endswith("Xem chi tiết: https://bao-cao.example")


def test_noi_dung_dai_thi_bo_muc_3_truoc(monkeypatch):
    day_du = bt.dung_noi_dung_bgd(NGAY)
    assert "3) CHẤT LƯỢNG BÁN" in day_du
    monkeypatch.setattr(bt, "TOI_DA_KY_TU", len(day_du) - 5)
    ngan = bt.dung_noi_dung_bgd(NGAY)
    assert len(ngan) <= len(day_du) - 5 and "3) CHẤT LƯỢNG BÁN" not in ngan and "1) TỔNG QUAN" in ngan


def _doan_kieu(chu: str, kieu: list[dict]) -> list[tuple[str, list[str]]]:
    """Cắt chữ theo vị trí UTF-16 như Zalo đọc, để kiểm kiểu rơi đúng chữ."""
    u16 = chu.encode("utf-16-le")
    return [(u16[k["start"] * 2:(k["start"] + k["len"]) * 2].decode("utf-16-le"), k["st"]) for k in kieu]


def test_noi_dung_co_kieu_chu_dung_vi_tri():
    tin = bt.dung_noi_dung_bgd(NGAY)
    tong = len(tin.encode("utf-16-le")) // 2
    assert tin.kieu and all(k["start"] >= 0 and k["len"] > 0 and k["start"] + k["len"] <= tong for k in tin.kieu)
    doan = _doan_kieu(tin, tin.kieu)
    assert any(c.startswith("Số chốt ngày") and "b" in st for c, st in doan)
    for tieu_de in ("1) TỔNG QUAN", "2) PHÒNG CẦN CHÚ Ý"):
        assert any(c == tieu_de and "b" in st for c, st in doan)
    assert any(c in ("An toàn", "Cần tăng tốc", "Rủi ro") and any(s.startswith("c_") for s in st) for c, st in doan)


def test_gui_thu_gui_ban_tin_co_nhan_ban_thu_va_giu_dung_kieu(gia):
    _them("Anh A", chat="a")
    assert bt.gui_thu(bt.ds_nguoi_nhan()[0]["id"])[0]
    chu, kieu = gia.tin[0][1], gia.kieu
    assert chu.startswith("[BẢN THỬ") and kieu
    assert any(c.startswith("Số chốt ngày") and "b" in st for c, st in _doan_kieu(chu, kieu))


# ------------------------------------------------------------------ Zalo: lỗi không lộ token
TOKEN = "123456:SecretTokenAbc"


def _http_loi(ma, than):
    return urllib.error.HTTPError(f"https://bot-api.zaloplatforms.com/bot{TOKEN}/sendMessage", ma, "x", {},
                                  io.BytesIO(json.dumps(than).encode()))


@pytest.mark.parametrize("loi", [
    _http_loi(401, {"description": f"token {TOKEN} sai"}),
    urllib.error.URLError(f"không nối được bot{TOKEN}"),
    TimeoutError(f"quá giờ bot{TOKEN}"),
    ValueError(f"lạ bot{TOKEN}"),
])
def test_loi_zalo_khong_chua_token(monkeypatch, loi):
    monkeypatch.setenv("ZALO_BOT_TOKEN", TOKEN)

    def hong(*a, **k):
        raise loi
    monkeypatch.setattr(zalo_bot.urllib.request, "urlopen", hong)
    with pytest.raises(zalo_bot.LoiZalo) as e:
        zalo_bot.gui_tin("c1", "xin chào")
    assert TOKEN not in str(e.value) and "SecretToken" not in str(e.value) and "bot-api" not in str(e.value)


def test_zalo_thieu_token(monkeypatch):
    monkeypatch.delenv("ZALO_BOT_TOKEN", raising=False)
    with pytest.raises(zalo_bot.LoiZalo, match="ZALO_BOT_TOKEN"):
        zalo_bot.gui_tin("c1", "x")


def test_zalo_gui_dung_dinh_dang_va_cat_2000(monkeypatch):
    monkeypatch.setenv("ZALO_BOT_TOKEN", TOKEN)
    thu = {}

    class Tra:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"ok": true, "result": {}}'

    def mo(req, timeout):
        thu.update(url=req.full_url, goi=json.loads(req.data), han=timeout)
        return Tra()
    monkeypatch.setattr(zalo_bot.urllib.request, "urlopen", mo)
    zalo_bot.gui_tin("c1", "x" * 3000)
    assert thu["url"].endswith("/sendMessage") and len(thu["goi"]["text"]) == 2000
    assert thu["goi"]["chat_id"] == "c1" and "parse_mode" not in thu["goi"] and thu["han"] <= 10


# ------------------------------------------------------------------ đường API
@pytest.fixture()
def may_khach(monkeypatch):
    from app.ui.app import server
    monkeypatch.setenv("BAN_TIN_KHOA", KHOA)
    return server.test_client()


def test_api_sai_hoac_thieu_khoa_403(may_khach, monkeypatch):
    goi = []
    monkeypatch.setattr(bt, "chay", lambda **k: goi.append(k) or {"loi": [], "da_gui": []})
    assert may_khach.post("/api/ban-tin/chay").status_code == 403
    assert may_khach.post("/api/ban-tin/chay", headers={"X-Ban-Tin-Khoa": "sai"}).status_code == 403
    monkeypatch.delenv("BAN_TIN_KHOA")
    assert may_khach.post("/api/ban-tin/chay", headers={"X-Ban-Tin-Khoa": ""}).status_code == 403
    assert may_khach.post("/api/ban-tin/chay", headers={"X-Ban-Tin-Khoa": KHOA}).status_code == 403
    assert goi == []


def test_api_dung_khoa_chay_va_chi_tra_noi_dung_khi_chay_thu(may_khach, gia):
    _them("Anh A")
    h = {"X-Ban-Tin-Khoa": KHOA}
    r = may_khach.post("/api/ban-tin/chay?kho=1", headers=h).get_json()
    assert r["ok"] and r["kho"] and "Số chốt ngày" in r["noi_dung"] and gia.tin == []
    thuc = bt.chay
    import app.ban_tin as m
    m.chay = lambda **k: thuc(gio_vn=SANG_8H, **k)
    try:
        r = may_khach.post("/api/ban-tin/chay", headers=h).get_json()
    finally:
        m.chay = thuc
    assert r["ok"] and r["da_gui"] == ["Anh A"] and "noi_dung" not in r
    assert KHOA not in json.dumps(r)


# ------------------------------------------------------------------ người nhận
def test_luu_sua_xoa_nguoi_nhan_va_kiem_tra():
    assert not bt.luu_nguoi_nhan(None, "", "bgd", "c", True)[0]
    assert not bt.luu_nguoi_nhan(None, "A", "la", "c", True)[0]
    _them("Anh A", chat="c1")
    id_ = bt.ds_nguoi_nhan()[0]["id"]
    assert bt.luu_nguoi_nhan(id_, "Anh A2", "admin", "c9", False)[0]
    n = bt.lay_nguoi_nhan(id_)
    assert (n["ten"], n["loai"], n["chat_id"], n["bat"]) == ("Anh A2", "admin", "c9", False)
    assert bt.xoa_nguoi_nhan([id_]) == 1 and bt.ds_nguoi_nhan() == []


def test_gui_thu_bao_loi_de_hieu_va_nhat_ky_gan_day(gia):
    _them("Anh A", chat="a")
    id_ = bt.ds_nguoi_nhan()[0]["id"]
    assert bt.gui_thu(id_)[0] and gia.tin[0][0] == "a"
    gia.hong.add("a")
    ok, msg = bt.gui_thu(id_)
    assert not ok and "Anh A" in msg
    bt.chay(gio_vn=SANG_8H)
    nk = bt.nhat_ky_gan_day(10)
    assert nk[0]["ngay_so"] == "11/09/2026" and nk[0]["ket_qua"] == "Lỗi" and nk[0]["ly_do"]
