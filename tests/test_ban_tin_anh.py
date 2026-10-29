"""Kiểm thử Bản tin 8h gửi ẢNH Báo cáo Tổng cho Ban Giám đốc (Zalo sendPhoto + đường ảnh tạm có ký). Chặn mạng hoàn toàn."""
from __future__ import annotations

import io
import json
import re
import sys
import time
import urllib.error
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import ban_tin as bt                                           # noqa: E402
from app import ban_tin_anh as ba                                        # noqa: E402
from app import config, metrics, overview, zalo_bot                      # noqa: E402
from app.config import DATA_DIR                                          # noqa: E402

pytestmark = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(),
                                reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")
NGAY = "2026-09-11"
SANG_8H = datetime(2026, 9, 12, 8, 5)
CHOT = (False, datetime(2026, 9, 12, 7, 0))
APP = "https://app.example.vn"
TOKEN = "123456:SecretTokenAbc"


class Gia:
    """Bản giả của `gui_tin` và `gui_anh`: ghi lại từng lần gọi; chat_id trong `hong_anh` / `hong_chu` báo lỗi."""

    def __init__(self):
        self.tin: list[tuple[str, str]] = []
        self.anh: list[tuple[str, str, str]] = []
        self.hong_anh: set[str] = set()
        self.hong_chu: set[str] = set()
        self.log: list[tuple[str, str]] = []              # ("anh" | "tin", chat_id) theo đúng thứ tự gửi

    def gui_tin(self, chat_id, noi_dung, parse_mode=None, han=8, text_styles=None):
        if chat_id in self.hong_chu:
            raise zalo_bot.LoiZalo("Zalo từ chối (mã 400): chữ giả lập.")
        self.tin.append((chat_id, noi_dung))
        self.log.append(("tin", chat_id))

    def gui_anh(self, chat_id, url_anh, caption="", han=20):
        if chat_id in self.hong_anh:
            raise zalo_bot.LoiZalo("Zalo từ chối (mã 400): ảnh giả lập.")
        self.anh.append((chat_id, url_anh, caption))
        self.log.append(("anh", chat_id))


@pytest.fixture()
def gia(monkeypatch):
    g = Gia()
    monkeypatch.setattr(zalo_bot, "gui_tin", g.gui_tin)
    monkeypatch.setattr(zalo_bot, "gui_anh", g.gui_anh)
    return g


@pytest.fixture(autouse=True)
def moi_truong(monkeypatch):
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
    monkeypatch.setenv("APP_URL", APP + "/")
    monkeypatch.setenv("BAN_TIN_KHOA", "khoa")
    yield
    don()


@pytest.fixture()
def may_khach():
    from app.ui.app import server
    return server.test_client()                       # không đăng nhập


def _them(ten, loai="bgd", chat="c1", bat=True):
    assert bt.luu_nguoi_nhan(None, ten, loai, chat, bat)[0]


def _nhat_ky():
    from sqlalchemy import select

    from app.db import session_scope
    from app.models import BanTinNhatKy
    with session_scope() as s:
        return [(r.loai, r.ket_qua, r.so_lan, r.ly_do) for r in s.execute(select(BanTinNhatKy)).scalars()]


# ------------------------------------------------------------------ đường ảnh tạm
def test_ma_hop_le_tra_png_khong_can_dang_nhap(may_khach):
    r = may_khach.get(f"/api/ban-tin/anh/{ba.tao_ma(NGAY)}.png")
    assert r.status_code == 200 and r.mimetype == "image/png"
    assert "no-store" in r.headers["Cache-Control"] and "private" in r.headers["Cache-Control"]
    from PIL import Image
    img = Image.open(io.BytesIO(r.data))
    assert img.format == "PNG" and img.width > 800 and img.height > 200


def test_ma_phong_tra_anh_phong_khong_can_dang_nhap(may_khach):
    from PIL import Image
    r = may_khach.get(f"/api/ban-tin/anh/{ba.tao_ma(NGAY, phong='IBB7')}.png")
    assert r.status_code == 200 and r.mimetype == "image/png" and "no-store" in r.headers["Cache-Control"]
    img = Image.open(io.BytesIO(r.data))
    assert img.format == "PNG" and img.width > 800 and img.height > 200


def test_anh_phong_la_bao_cao_phong_che_do_ban_hang_khong_dung_anh_tong(monkeypatch):
    goi = []
    import app.export_phong as ep
    import app.export_png as epng

    def gia_phong(thang, ngay, code, **kw):
        goi.append((thang, ngay, code, kw))
        return b"png-" + code.encode(), "x.png"
    monkeypatch.setattr(ep, "anh_bao_cao_phong", gia_phong)
    monkeypatch.setattr(epng, "anh_tong_quan", lambda *a, **k: (b"tong", "t.png"))
    ba._cache.clear()
    assert ba.dung_anh(NGAY, "IBB7") == b"png-IBB7" and ba.dung_anh(NGAY, "IBB3") == b"png-IBB3"
    assert ba.dung_anh(NGAY) == b"tong"                       # mỗi (loại, phòng) có chỗ nhớ riêng, không lẫn nhau
    assert ba.dung_anh(NGAY, "IBB7") == b"png-IBB7" and len(goi) == 2
    thang, ngay, code, kw = goi[0]
    assert (thang, ngay, code) == ("2026-09", 11, "IBB7") and kw["che_do"] == "ban_hang"
    assert kw["tam_tinh"] is False and kw["luc"] == CHOT[1] and "chi_chu_y" not in kw


def test_link_phong_a_khong_xem_duoc_phong_b(may_khach, monkeypatch):
    import app.export_phong as ep
    monkeypatch.setattr(ep, "anh_bao_cao_phong", lambda thang, ngay, code, **kw: (b"png-" + code.encode(), "x.png"))
    ba._cache.clear()
    ma = ba.tao_ma(NGAY, phong="IBB7")
    assert may_khach.get(f"/api/ban-tin/anh/{ma}.png").data == b"png-IBB7"
    ma_b = ma.replace("IBB7", "IBB3")
    r = may_khach.get(f"/api/ban-tin/anh/{ma_b}.png?phong=IBB3&code=IBB3")
    assert r.status_code == 404 and r.mimetype != "image/png"
    assert may_khach.get(f"/api/ban-tin/anh/{ba.tao_ma(NGAY)}.png?phong=IBB3").data != b"png-IBB3"     # tham số ngoài mã không chọn được phòng


def _ma_xau():
    tot = ba.tao_ma(NGAY)
    ngay, han, ky = tot.split(".")
    return [
        f"{ngay}.{han}.{'0' * len(ky)}",                          # sai chữ ký
        f"{ngay}.{int(han) + 5}.{ky}",                            # sửa hạn
        f"2026-09-10.{han}.{ky}",                                 # sửa ngày
        ba.tao_ma(NGAY, bay_gio=time.time() - 2 * ba.HAN_ANH_GIAY),   # đã hết hạn
        ba.tao_ma("2026-09-12"),                                  # ký đúng nhưng ngày xa hơn ngày số mới nhất
        ba.tao_ma("2026-13-45"),                                  # ký đúng nhưng không phải ngày
        ba.tao_ma("rac-rac-ra"),
        "rac", "a.b", "a.b.c.d", "..", f"{ngay}.{han}", f"{ngay}.chu.{ky}",
        f"{ngay}.{han}.IBB7.{ky}",                                # chữ ký loại tổng gắn thêm mã phòng
        ba.tao_ma(NGAY, phong="IBB7").replace("IBB7", "IBB3"),    # đổi mã phòng trong mã đã ký
        ba.tao_ma(NGAY, phong="IBB7", bay_gio=time.time() - 2 * ba.HAN_ANH_GIAY),
        ba.tao_ma(NGAY, phong="KT_DNG1"),                         # ký đúng nhưng không phải phòng bán hàng
        ba.tao_ma(NGAY, phong="IBB7;x"), ba.tao_ma(NGAY, phong=""),
    ]


def test_ma_sai_het_han_hay_rac_deu_cung_mot_phan_hoi(may_khach):
    kq = []
    for ma in _ma_xau():
        r = may_khach.get(f"/api/ban-tin/anh/{ma}.png")
        kq.append((r.status_code, r.mimetype, r.data))
    assert len(set(kq)) == 1 and kq[0][0] == 404 and kq[0][1] != "image/png"
    for ma in _ma_xau():
        assert ba.doc_ma(ma) is None
    assert ba.doc_ma(ba.tao_ma(NGAY, phong="../etc")) is None
    assert ba.doc_ma(ba.tao_ma(NGAY)) == (NGAY, None)
    assert ba.doc_ma(ba.tao_ma(NGAY, phong="IBB7")) == (NGAY, "IBB7")


def test_ma_ky_bang_khoa_rieng_khac_khoa_webhook():
    from app import ban_tin_cho_duyet as cd
    assert ba._ky(NGAY, 1) != cd.khoa_webhook()[:32]
    assert ba.tao_ma(NGAY).split(".")[2] != cd.khoa_webhook()[:32]


def test_duong_anh_khong_nhan_tham_so_phong_hay_chi_nhanh(may_khach):
    ma = ba.tao_ma(NGAY)
    r0 = may_khach.get(f"/api/ban-tin/anh/{ma}.png")
    r1 = may_khach.get(f"/api/ban-tin/anh/{ma}.png?phong=IBB7&chi_nhanh=DNG&thang=2026-08&ngay=3&nhan_xet=1")
    assert r0.status_code == r1.status_code == 200 and r0.data == r1.data


def test_khong_ghi_ma_ra_log_ung_dung(may_khach, caplog):
    ma = ba.tao_ma(NGAY)
    with caplog.at_level("DEBUG"):
        may_khach.get(f"/api/ban-tin/anh/{ma}.png")
        may_khach.get("/api/ban-tin/anh/rac.png")
    assert ma not in caplog.text


def test_anh_la_bao_cao_tong_toan_chi_nhanh_khong_nhan_xet(monkeypatch):
    goi = {}
    import app.export_png as ep

    def gia_anh(thang, ngay=None, **kw):
        goi.update(thang=thang, ngay=ngay, **kw)
        return b"png", "x.png"
    monkeypatch.setattr(ep, "anh_tong_quan", gia_anh)
    ba._cache.clear()
    assert ba.dung_anh(NGAY) == b"png"
    assert (goi["thang"], goi["ngay"], goi["chi_nhanh"], goi["chi_phong"]) == ("2026-09", 11, "all", None)
    assert goi["tam_tinh"] is False and goi["luc"] == CHOT[1] and "nhan_xet" not in goi


# ------------------------------------------------------------------ zalo_bot.gui_anh
class _Tra:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return b'{"ok": true, "result": {"message_id": "m1", "date": 1}}'


def test_gui_anh_gui_dung_json(monkeypatch):
    monkeypatch.setenv("ZALO_BOT_TOKEN", TOKEN)
    thu = {}

    def mo(req, timeout):
        thu.update(url=req.full_url, goi=json.loads(req.data), han=timeout)
        return _Tra()
    monkeypatch.setattr(zalo_bot.urllib.request, "urlopen", mo)
    zalo_bot.gui_anh("c1", f"{APP}/api/ban-tin/anh/ma.png", "Chú thích " + "x" * 3000)
    assert thu["url"].endswith("/sendPhoto")
    assert thu["goi"]["chat_id"] == "c1" and thu["goi"]["photo"] == f"{APP}/api/ban-tin/anh/ma.png"
    assert thu["goi"]["caption"].startswith("Chú thích") and len(thu["goi"]["caption"]) == 2000
    zalo_bot.gui_anh("c1", f"{APP}/x.png")
    assert "caption" not in thu["goi"]


@pytest.mark.parametrize("loi", [
    urllib.error.HTTPError(f"https://bot-api.zaloplatforms.com/bot{TOKEN}/sendPhoto", 400, "x", {},
                           io.BytesIO(json.dumps({"description": f"không tải được {APP}/api/ban-tin/anh/BIMAT123.png token {TOKEN}"}).encode())),
    urllib.error.URLError(f"không nối được bot{TOKEN}"),
    TimeoutError(f"quá giờ bot{TOKEN}"),
    ValueError(f"lạ bot{TOKEN} {APP}/api/ban-tin/anh/BIMAT123.png"),
])
def test_gui_anh_loi_khong_lo_token_hay_ma(monkeypatch, loi):
    monkeypatch.setenv("ZALO_BOT_TOKEN", TOKEN)

    def hong(*a, **k):
        raise loi
    monkeypatch.setattr(zalo_bot.urllib.request, "urlopen", hong)
    with pytest.raises(zalo_bot.LoiZalo) as e:
        zalo_bot.gui_anh("c1", f"{APP}/api/ban-tin/anh/BIMAT123.png", "x")
    m = str(e.value)
    assert TOKEN not in m and "SecretToken" not in m and "bot-api" not in m and "BIMAT123" not in m


def test_gui_anh_thieu_token_hoac_du_lieu(monkeypatch):
    monkeypatch.delenv("ZALO_BOT_TOKEN", raising=False)
    with pytest.raises(zalo_bot.LoiZalo, match="ZALO_BOT_TOKEN"):
        zalo_bot.gui_anh("c1", f"{APP}/a.png", "x")
    with pytest.raises(zalo_bot.LoiZalo):
        zalo_bot.gui_anh("", f"{APP}/a.png")


# ------------------------------------------------------------------ bản tin BGĐ
def test_bgd_nhan_anh_roi_tin_nhan_dinh_khi_co_app_url(gia):
    _them("Anh A", chat="a")
    kq = bt.chay(gio_vn=SANG_8H)
    assert kq["da_gui"] == ["Anh A"] and kq["gui_anh"] == ["Anh A"] and "dung_ban_chu" not in kq and not kq["loi"]
    assert len(gia.anh) == 1 and len(gia.tin) == 1 and gia.log == [("anh", "a"), ("tin", "a")]          # ảnh trước, nhận định sau
    chat, url, caption = gia.anh[0]
    m = re.fullmatch(re.escape(APP) + r"/api/ban-tin/anh/([^/]+)\.png", url)
    assert chat == "a" and m and ba.doc_ma(m.group(1)) == (NGAY, None)
    assert caption == f"Báo cáo Tổng - số chốt ngày 11/09\nXem chi tiết: {APP}"
    nd = gia.tin[0][1]
    assert nd.startswith("NHẬN ĐỊNH & HÀNH ĐỘNG - số chốt ngày 11/09") and len(nd) <= bt.TOI_DA_KY_TU
    assert {r[0]: r[1] for r in _nhat_ky()} == {"bgd": "ok", "bgd_nd": "ok"}


def test_goi_hai_lan_khong_gui_trung(gia):
    _them("Anh A", chat="a")
    bt.chay(gio_vn=SANG_8H)
    kq = bt.chay(gio_vn=SANG_8H)
    assert len(gia.anh) == 1 and len(gia.tin) == 1 and kq["da_gui"] == []


def test_khong_dung_chu_cu_khi_anh_di_duoc(gia, monkeypatch):
    _them("Anh A", chat="a")
    monkeypatch.setattr(bt, "dung_noi_dung_bgd", lambda iso: (_ for _ in ()).throw(AssertionError("không được dựng bản chữ cũ")))
    assert bt.chay(gio_vn=SANG_8H)["da_gui"] == ["Anh A"]


def test_khong_co_app_url_thi_gui_ban_chu_cu_roi_van_nhan_nhan_dinh(gia, monkeypatch):
    monkeypatch.delenv("APP_URL")
    _them("Anh A", chat="a")
    kq = bt.chay(gio_vn=SANG_8H)
    assert kq["da_gui"] == ["Anh A"] and kq["dung_ban_chu"] == ["Anh A"] and not kq["loi"]
    assert gia.anh == [] and len(gia.tin) == 2 and "Số chốt ngày 11/09" in gia.tin[0][1]
    assert gia.tin[1][1].startswith("NHẬN ĐỊNH & HÀNH ĐỘNG")
    ly = {r[0]: r[3] for r in _nhat_ky()}
    assert "APP_URL" in ly["bgd"]
    bt.chay(gio_vn=SANG_8H)
    assert len(gia.tin) == 2


def test_app_url_http_khong_dung_cho_anh(gia, monkeypatch):
    monkeypatch.setenv("APP_URL", "http://app.example.vn")
    assert ba.url_anh(NGAY) is None and ba.url_anh(NGAY, "IBB7") is None
    _them("Anh A", chat="a")
    assert bt.chay(gio_vn=SANG_8H)["dung_ban_chu"] == ["Anh A"]


def test_sendphoto_loi_thi_gui_ban_chu_roi_ghi_ok(gia):
    _them("Anh A", chat="a")
    _them("Anh B", chat="b")
    gia.hong_anh.add("a")
    kq = bt.chay(gio_vn=SANG_8H)
    assert sorted(kq["da_gui"]) == ["Anh A", "Anh B"] and kq["dung_ban_chu"] == ["Anh A"] and kq["gui_anh"] == ["Anh B"]
    assert sorted(c for c, _ in gia.tin) == ["a", "a", "b"] and [c for c, _, _ in gia.anh] == ["b"]      # A: bản chữ + nhận định; B: nhận định
    assert not kq["loi"] and all(r[1] == "ok" for r in _nhat_ky())
    assert any("ảnh giả lập" in (r[3] or "") for r in _nhat_ky())


def test_anh_va_chu_deu_loi_thi_ghi_loi_va_thu_lai_khong_gui_nhan_dinh_truoc(gia):
    _them("Anh A", chat="a")
    gia.hong_anh.add("a")
    gia.hong_chu.add("a")
    kq = bt.chay(gio_vn=SANG_8H)
    assert kq["da_gui"] == [] and "ảnh cũng lỗi" in kq["loi"][0]["ly_do"] and gia.tin == []            # chưa có ảnh/bản chữ thì chưa gửi nhận định
    assert {r[0]: r[1] for r in _nhat_ky()} == {"bgd": "loi"}
    gia.hong_anh.clear()
    gia.hong_chu.clear()
    assert bt.chay(gio_vn=SANG_8H)["gui_anh"] == ["Anh A"]
    assert {r[0]: (r[1], r[2]) for r in _nhat_ky()} == {"bgd": ("ok", 2), "bgd_nd": ("ok", 1)}


def test_anh_ok_nhan_dinh_loi_thi_luot_sau_chi_gui_nhan_dinh(gia):
    _them("Anh A", chat="a")
    gia.hong_chu.add("a")
    kq = bt.chay(gio_vn=SANG_8H)
    assert len(gia.anh) == 1 and gia.tin == [] and kq["loi"] and kq["loi"][0]["nguoi"] == "Anh A"
    assert {r[0]: r[1] for r in _nhat_ky()} == {"bgd": "ok", "bgd_nd": "loi"}
    gia.hong_chu.clear()
    kq = bt.chay(gio_vn=SANG_8H)
    assert len(gia.anh) == 1 and len(gia.tin) == 1 and kq["da_gui"] == ["Anh A"] and not kq["loi"]       # ảnh không gửi lại
    assert {r[0]: r[1] for r in _nhat_ky()} == {"bgd": "ok", "bgd_nd": "ok"}
    bt.chay(gio_vn=SANG_8H)
    assert len(gia.anh) == 1 and len(gia.tin) == 1


def test_loi_bat_ngo_khi_gui_anh_van_gui_ban_chu(gia, monkeypatch):
    _them("Anh A", chat="a")
    monkeypatch.setattr(zalo_bot, "gui_anh", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("https://x/botSECRET")))
    kq = bt.chay(gio_vn=SANG_8H)
    assert kq["dung_ban_chu"] == ["Anh A"] and "SECRET" not in json.dumps(kq, ensure_ascii=False)
    assert "SECRET" not in str(_nhat_ky())


def test_cong_tac_chu_thi_chi_gui_chu_cu_khong_co_nhan_dinh(gia, monkeypatch):
    monkeypatch.setattr(config, "rules_config", lambda: {"ban_tin": {"bgd_dang": "chu"}})
    _them("Anh A", chat="a")
    kq = bt.chay(gio_vn=SANG_8H)
    assert kq["da_gui"] == ["Anh A"] and gia.anh == [] and "dung_ban_chu" not in kq and "gui_anh" not in kq
    assert len(gia.tin) == 1 and "Số chốt ngày 11/09" in gia.tin[0][1]
    assert [r[0] for r in _nhat_ky()] == ["bgd"]


def test_cong_tac_mac_dinh_la_anh_va_gia_tri_la_coi_nhu_anh(monkeypatch):
    assert ba.cong_tac() == "anh" and ba.cong_tac_tp() == "anh"
    monkeypatch.setattr(config, "rules_config", lambda: {"ban_tin": {"bgd_dang": "linh tinh", "tp_dang": "chu"}})
    assert ba.cong_tac() == "anh" and ba.cong_tac_tp() == "chu"
    monkeypatch.setattr(config, "rules_config", lambda: {})
    assert ba.cong_tac() == "anh" and ba.cong_tac_tp() == "anh"


def test_nhac_admin_van_la_chu(gia, monkeypatch):
    _them("Anh A", chat="a")
    _them("Admin", loai="admin", chat="ad")
    monkeypatch.setattr(overview, "trang_thai_ngay", lambda iso: (True, datetime(2026, 9, 11, 14, 30)))
    kq = bt.chay(gio_vn=datetime(2026, 9, 12, 10, 30))
    assert kq["da_gui"] == ["Admin"] and gia.anh == []
    assert gia.tin == [("ad", "Chưa có số chốt của ngày 11/09, hãy nạp file.")]


def test_kho_khong_dung_anh_khong_tao_ma_nhung_dung_nhan_dinh(gia, monkeypatch):
    _them("Anh A", chat="a")
    monkeypatch.setattr(ba, "tao_ma", lambda *a, **k: (_ for _ in ()).throw(AssertionError("không tạo mã khi chạy thử")))
    monkeypatch.setattr(ba, "dung_anh", lambda *a, **k: (_ for _ in ()).throw(AssertionError("không dựng ảnh khi chạy thử")))
    kq = bt.chay(gio_vn=SANG_8H, kho=True)
    assert kq["bgd_dang"] == "anh" and kq["tp_dang"] == "anh" and kq["app_url_da_cai"] is True and kq["se_gui"]
    assert kq["nhan_dinh"].startswith("NHẬN ĐỊNH & HÀNH ĐỘNG") and "Số chốt ngày 11/09" in kq["noi_dung"]
    assert gia.anh == [] and gia.tin == [] and _nhat_ky() == []
    monkeypatch.delenv("APP_URL")
    assert bt.chay(gio_vn=SANG_8H, kho=True)["app_url_da_cai"] is False


def test_api_chay_thu_bao_cong_tac(may_khach, gia):
    r = may_khach.post("/api/ban-tin/chay?kho=1", headers={"X-Ban-Tin-Khoa": "khoa"}).get_json()
    assert r["ok"] and r["bgd_dang"] == "anh" and r["tp_dang"] == "anh" and r["app_url_da_cai"] is True
    assert r["nhan_dinh"].startswith("NHẬN ĐỊNH") and gia.tin == [] and _nhat_ky() == []


# ------------------------------------------------------------------ gửi thử
def test_gui_thu_bgd_gui_anh_roi_nhan_dinh_co_nhan_ban_thu_khong_ghi_nhat_ky(gia):
    _them("Anh A", chat="a")
    ok, msg = bt.gui_thu(bt.ds_nguoi_nhan()[0]["id"])
    assert ok and "ảnh" in msg and "nhận định" in msg and "CHỮ" not in msg
    assert gia.log == [("anh", "a"), ("tin", "a")]
    assert gia.anh[0][2].startswith("[BẢN THỬ]\nBáo cáo Tổng - số chốt ngày 11/09")
    assert gia.tin[0][1].startswith("[BẢN THỬ]\nNHẬN ĐỊNH & HÀNH ĐỘNG")
    assert _nhat_ky() == []


def test_gui_thu_bgd_anh_loi_thi_gui_chu_va_nhan_dinh_va_noi_ly_do(gia, monkeypatch):
    _them("Anh A", chat="a")
    gia.hong_anh.add("a")
    ok, msg = bt.gui_thu(bt.ds_nguoi_nhan()[0]["id"])
    assert ok and "BẢN CHỮ" in msg and "ảnh giả lập" in msg and "nhận định" in msg
    assert len(gia.tin) == 2 and gia.tin[0][1].startswith("[BẢN THỬ") and gia.tin[1][1].startswith("[BẢN THỬ]\nNHẬN ĐỊNH")
    monkeypatch.delenv("APP_URL")
    gia.hong_anh.clear()
    ok, msg = bt.gui_thu(bt.ds_nguoi_nhan()[0]["id"])
    assert ok and "BẢN CHỮ" in msg and "APP_URL" in msg


def test_gui_thu_admin_va_cong_tac_chu_van_la_chu(gia, monkeypatch):
    _them("Admin", loai="admin", chat="ad")
    ok, msg = bt.gui_thu(bt.ds_nguoi_nhan()[0]["id"])
    assert ok and gia.anh == [] and gia.tin[0][1].startswith("[BẢN THỬ")
    monkeypatch.setattr(config, "rules_config", lambda: {"ban_tin": {"bgd_dang": "chu"}})
    _them("Anh A", chat="a")
    assert bt.gui_thu(bt.ds_nguoi_nhan()[1]["id"])[0] and gia.anh == [] and len(gia.tin) == 2
