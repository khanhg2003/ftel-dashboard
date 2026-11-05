"""Bot Zalo Tra cứu giá (app/zalo_gia.py, zalo_gia_nd.py, api_zalo_gia.py). Chặn mạng hoàn toàn: fpt.vn và Zalo đều là hàm giả."""
from __future__ import annotations

import json
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import gia_fpt as gf                      # noqa: E402
from app import gia_fpt_nhom as gn                 # noqa: E402
from app import zalo_bot, zalo_gia as zg           # noqa: E402
from app import zalo_gia_anh as za                 # noqa: E402
from app import zalo_gia_nd as nd                  # noqa: E402
from app.config import DATA_DIR                    # noqa: E402
from app.thoi_gian import utc_bay_gio              # noqa: E402

pytestmark = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(),
                                reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")
TOKEN = "999:GIA-BI-MAT"
GUI_TIN_THAT = zalo_bot.gui_tin                 # trước khi fixture thay bằng hàm giả

TINH = [{"id": 511, "ten": "Đà Nẵng"}, {"id": 56, "ten": "Khánh Hòa"}, {"id": 79, "ten": "Hồ Chí Minh"}]
PHUONG = {511: [{"id": 1, "ten": "Phường Hải Châu"}, {"id": 2, "ten": "Phường An Hải"}, {"id": 3, "ten": "Xã Quế Sơn"}],
          56: [{"id": 10, "ten": "Phường Nam Nha Trang"}, {"id": 11, "ten": "Phường Bắc Nha Trang"}, {"id": 12, "ten": "Phường An Hải"}],
          79: [{"id": 20, "ten": "Phường Bến Nghé"}]}


def _g(id_, code, ten, gia):
    return {"id": id_, "code": code, "ten": ten, "khach": "ca_nhan", "gia": gia, "toc_do": "1 Gbps / 300 Mbps", "thiet_bi": None,
            "uu_dai": "", "nhan": "", "mo_ta": []}


GOI = [_g(1, "goi-giga", "Internet Giga", 245000), _g(2, "goi-sky", "Internet Sky", 270000), _g(3, "goi-sky-f1", "Internet Sky F1", 330000),
       _g(4, "goi-meta-f1", "Internet Meta F1", 340000), _g(5, "goi-meta-f2", "Internet Meta F2", 390000),
       _g(6, "super-300-biz", "Super300 Biz", 450000), _g(7, "combo-lux800", "Combo Internet Lux800 V.VIP", 800000),
       _g(10, "combo-internet-giga-vvip-lite", "Combo Giga - V.VIP", 285000), _g(11, "combo-internet-sky-vvip-lite", "Combo Sky - V.VIP", 310000),
       _g(12, "combo-internet-meta-vvip-lite", "Combo Meta - V.VIP", 400000),
       _g(8, "goi-f-game", "Internet F-Game", 300000), _g(9, "goi-giga-eyes", "Internet Giga Eyes3", 400000)]
GOI[0]["toc_do"] = "300 Mbps / 300 Mbps"
# như website: Sky F1 nằm cả "cá nhân" lẫn "gia đình", Lux800 nằm cả V.VIP lẫn doanh nghiệp; ba nhóm game thủ / doanh nghiệp / camera bot không hiện
CH = {"nhom": [("Internet cá nhân", ["goi-giga", "goi-sky", "goi-sky-f1"]), ("Internet gia đình", ["goi-sky-f1", "goi-meta-f1", "goi-meta-f2"]),
               ("Combo Internet + V.VIP", ["combo-internet-giga-vvip-lite", "combo-internet-sky-vvip-lite", "combo-internet-meta-vvip-lite", "combo-lux800"]), ("Internet doanh nghiệp", ["super-300-biz", "combo-lux800"]),
               ("Internet game thủ", ["goi-f-game"]), ("Combo Internet Camera", ["goi-giga-eyes"])], "nguon": "website"}


def _lc(hinh_thuc, thang, tong, phi, tang=0, thang_dong=None, den="31/12/2026"):
    return {"hinh_thuc": hinh_thuc, "thang": thang, "tong": tong, "phi_lap": phi, "thiet_bi": None, "thang_dong": thang_dong or thang,
            "tang": tang, "binh_quan": None, "qua": "", "chinh_sach": "CS", "ma": "", "den": den}


def _ct(phi):
    """phi: số (cả ba cách cùng mức), 0 = dịch vụ ghi rõ miễn phí, None = mất dòng phí."""
    lc = [_lc("Trả sau", 1, 245000, phi), _lc("Trả trước", 6, 1470000, phi), _lc("Trả trước", 13, 2940000, phi, tang=1, thang_dong=12)]
    return {"ten": "x", "gia": 245000, "phi_nhom": [] if phi is None else [["Trả theo tháng · trả trước 6 / 13 tháng", phi]],
            "thiet_bi": None, "mo_ta": [], "lua_chon": lc, "luc": utc_bay_gio()}


class Ghi(list):
    """Các tin bot gửi (chat, chữ, token); `.kieu` là text_styles đi kèm từng tin."""

    def __init__(self):
        super().__init__()
        self.kieu, self.anh, self.su_kien = [], [], []


PHI = {"goi-giga": 300000, "goi-sky": None, "goi-meta-f1": 0}


@pytest.fixture(autouse=True)
def moi_truong(monkeypatch):
    from sqlalchemy import delete

    from app.db import session_scope
    from app.models import AuditLog, ZaloGiaHoiLai, ZaloGiaTin

    def don():
        with session_scope() as s:
            s.execute(delete(ZaloGiaTin))
            s.execute(delete(ZaloGiaHoiLai))
            s.execute(delete(AuditLog).where(AuditLog.action.in_(["zalo_gia", "zalo_gia_la"])))
    zg.dam_bao_bang()
    don()
    monkeypatch.setenv("ZALO_GIA_TOKEN", TOKEN)
    monkeypatch.setenv("ZALO_GIA_CHO_PHEP", "g1, u1")
    monkeypatch.delenv("ZALO_GIA_GHI_LOG", raising=False)
    monkeypatch.delenv("ZALO_GIA_TEN_BOT", raising=False)
    monkeypatch.setattr(gf, "danh_sach_tinh", lambda: TINH)
    monkeypatch.setattr(gf, "danh_sach_phuong", lambda t: PHUONG[t])
    monkeypatch.setattr(gf, "goi_theo_phuong", lambda t, p: {"goi": GOI, "luc": utc_bay_gio(), "cu": False})
    monkeypatch.setattr(gf, "chi_tiet_nhieu", lambda t, p, goi: {g["code"]: _ct(PHI.get(g["code"], 500000)) for g in goi})
    monkeypatch.setattr(gn, "cau_hinh", lambda: CH)
    gui = Ghi()

    def ghi(c, n, *a, **k):
        gui.append((c, n, k.get("token")))
        gui.kieu.append(k.get("text_styles"))
        gui.su_kien.append("tin")
    monkeypatch.setattr(zalo_bot, "gui_tin", ghi)

    def ghi_anh(c, url, caption="", han=0, token=None):
        gui.anh.append((c, url, caption, han, token))
        gui.su_kien.append("anh")
    monkeypatch.setattr(zalo_bot, "gui_anh", ghi_anh)
    monkeypatch.delenv("APP_URL", raising=False)
    monkeypatch.delenv("ZALO_GIA_ANH", raising=False)
    monkeypatch.setattr(gf, "chi_tiet_goi", lambda code, t, p, gia: _ct(PHI.get(code, 500000)))
    za._cache.clear()
    yield gui
    don()


@pytest.fixture()
def gui(moi_truong):
    return moi_truong


@pytest.fixture()
def may_khach():
    from app.ui.app import server
    return server.test_client()


def _chu(kq):
    return "\n".join(kq["tin"])


# ------------------------------------------------------------------ tách câu
def test_cau_hoi_anh_mau_ra_chi_tiet_goi_giga():
    kq = zg.tra_loi("Giá cước GiGa ở phường Nam Nha Trang, Khánh Hoà @Bot", None)
    chu = _chu(kq)
    assert kq["hoi"] is None and kq["nhat_ky"] == ("Internet Giga", "Phường Nam Nha Trang, Khánh Hòa")
    assert "Internet Giga - Phường Nam Nha Trang, Khánh Hòa" in chu and "245.000đ/tháng" in chu
    assert "Trả theo tháng · 245.000đ/tháng" in chu and "Trả trước 6 tháng · 1.470.000đ" in chu
    assert "Trả trước 13 tháng · 2.940.000đ (đóng 12, tặng 1)" in chu and "Tốc độ: 300 Mbps\n" in chu
    assert "Phí hòa mạng: 300.000đ" in chu and "Chính sách áp dụng đến hết 31/12/2026" in chu
    assert "đã gồm VAT" in chu and "Super300" not in chu


def test_go_khong_dau_va_khong_phan_biet_hoa_thuong():
    kq = zg.tra_loi("GIA giga phuong hai chau da nang", None)
    assert kq["nhat_ky"][1] == "Phường Hải Châu, Đà Nẵng"


def test_bo_mention_co_ten_bot_nhieu_chu(monkeypatch):
    monkeypatch.setenv("ZALO_GIA_TEN_BOT", "Tra Gia FPT")
    assert zg.bo_mention("@Tra Gia FPT giá giga phường hải châu") == "giá giga phường hải châu"
    assert zg.bo_mention("giá giga @bot") == "giá giga"


def test_phi_thieu_thi_ghi_chua_ro_khong_ghi_mien_phi():
    chu = _chu(zg.tra_loi("giá sky phường hải châu", None))
    assert "Phí hòa mạng: Chưa rõ, xem trên fpt.vn" in chu and "Miễn phí" not in chu


def test_phi_0_dich_vu_ghi_ro_thi_moi_la_mien_phi():
    assert "Phí hòa mạng: Miễn phí" in _chu(zg.tra_loi("giá meta f1 phường hải châu", None))


def test_goi_nhieu_chu_chon_ten_dai_nhat():
    kq = zg.tra_loi("giá sky f1 phường hải châu", None)
    assert kq["nhat_ky"][0] == "Internet Sky F1"
    kq = zg.tra_loi("giá giga và sky phường hải châu", None)
    assert kq["nhat_ky"][0] == "Internet Giga, Internet Sky"


# ------------------------------------------------------------------ hỏi lại
def test_trung_ten_phuong_o_nhieu_tinh_thi_hoi_lai_roi_chon_so():
    kq = zg.tra_loi("giá giga phường An Hải", None)
    assert kq["hoi"]["buoc"] == "chon_phuong" and len(kq["hoi"]["ds"]) == 2
    assert "1. Phường An Hải, Đà Nẵng" in _chu(kq) and "2. Phường An Hải, Khánh Hòa" in _chu(kq)
    ra = zg.tra_loi("2", kq["hoi"])
    assert ra["hoi"] is None and ra["nhat_ky"] == ("Internet Giga", "Phường An Hải, Khánh Hòa")


def test_co_tinh_thi_het_mo_ho():
    kq = zg.tra_loi("giá giga phường An Hải Đà Nẵng", None)
    assert kq["hoi"] is None and kq["nhat_ky"][1] == "Phường An Hải, Đà Nẵng"


def test_nhieu_goi_khop_mot_phan_thi_hoi_lai_goi():
    kq = zg.tra_loi("giá meta phường hải châu", None)
    assert kq["hoi"]["buoc"] == "chon_goi"
    assert "1. Internet Meta F1 - 340.000đ/tháng" in _chu(kq) and "2. Internet Meta F2" in _chu(kq)
    ra = zg.tra_loi("2", kq["hoi"])
    assert ra["nhat_ky"] == ("Internet Meta F2", "Phường Hải Châu, Đà Nẵng")


def test_so_ngoai_danh_sach_va_so_khi_khong_co_cau_hoi():
    kq = zg.tra_loi("giá meta phường hải châu", None)
    sai = zg.tra_loi("9", kq["hoi"])
    assert "từ 1 đến 2" in _chu(sai) and sai["hoi"] == kq["hoi"]
    assert "chưa có câu hỏi nào đang chờ" in _chu(zg.tra_loi("3", None))


def test_thieu_phuong_thi_hoi_phuong_roi_ghep_cau_tra_loi():
    kq = zg.tra_loi("Giá cước giga ở Đà Nẵng", None)
    assert kq["hoi"]["buoc"] == "cho_phuong" and "phường/xã nào ở Đà Nẵng" in _chu(kq)
    ra = zg.tra_loi("hải châu", kq["hoi"])
    assert ra["nhat_ky"] == ("Internet Giga", "Phường Hải Châu, Đà Nẵng")
    moi = zg.tra_loi("giá sky phường hải châu", kq["hoi"])           # câu mới đầy đủ thì không ghép với câu cũ
    assert moi["nhat_ky"][0] == "Internet Sky"


def test_khong_tim_thay_phuong_noi_ro():
    kq = zg.tra_loi("giá giga phường Xyzabc Đà Nẵng", None)
    assert kq["hoi"] is None and "chưa tìm thấy phường/xã “xyzabc” ở Đà Nẵng" in _chu(kq)


def test_go_sai_chinh_ta_thi_hoi_lai_khong_tu_chon():
    kq = zg.tra_loi("giá giga phường nam nha trag Khánh Hòa", None)
    assert kq["hoi"]["buoc"] == "chon_phuong" and "Nam Nha Trang" in _chu(kq)


def test_goi_khong_co_ten_thi_bao_roi_liet_ke():
    chu = _chu(zg.tra_loi("giá ultra phường hải châu", None))
    assert "chưa thấy gói “ultra”" in chu and "Internet Giga: 245.000đ/tháng" in chu


# ------------------------------------------------------------------ liệt kê, nhóm, lệnh
def test_chi_hoi_gia_phuong_thi_liet_ke_moi_goi_mot_dong_va_nhac_go_ten_goi():
    chu = _chu(zg.tra_loi("giá cước phường hải châu", None))
    assert "• Internet Giga: 245.000đ/tháng · 300 Mbps" in chu and "• Internet Sky: 270.000đ/tháng · 1 Gbps / 300 Mbps" in chu
    assert "Gõ tên gói để xem chi tiết, ví dụ: giá Giga phường Hải Châu." in chu


def test_bo_ba_nhom_game_doanh_nghiep_camera():
    chu = _chu(zg.tra_loi("giá cước phường hải châu", None))
    for nhom in zg.NHOM_AN:
        assert nhom not in chu
    for goi in ("Super300", "F-Game", "Eyes3"):
        assert goi not in chu
    kq = zg.tra_loi("giá super300 phường hải châu", None)             # hỏi thẳng gói của nhóm bị ẩn: không khớp
    assert "chưa thấy gói" in _chu(kq) and "Super300 Biz:" not in _chu(kq)
    kq = zg.tra_loi("giá gói doanh nghiệp phường hải châu", None)
    assert kq["hoi"] is None and "Super300" not in _chu(kq)


def test_moi_goi_chi_hien_mot_lan_va_giu_thu_tu_nhom():
    chu = _chu(zg.tra_loi("giá cước phường hải châu", None))
    for goi in ("Internet Sky F1", "Combo Giga - V.VIP", "Internet Giga:"):
        assert chu.count(goi) == 1, goi
    assert chu.index("Internet cá nhân") < chu.index("Internet gia đình") < chu.index("Combo Internet + V.VIP")
    ca_nhan = chu.split("Internet gia đình")[0]
    assert ca_nhan.index("Giga") < ca_nhan.index("Sky:") < ca_nhan.index("Sky F1")                      # giá thấp -> cao
    gia_dinh = chu.split("Internet gia đình")[1].split("Combo Internet + V.VIP")[0]
    assert "Sky F1" not in gia_dinh and "Meta F1" in gia_dinh
    hien = zg.nhom_hien(GOI, CH)
    assert list(hien) == ["Internet cá nhân", "Internet gia đình", "Combo Internet + V.VIP"]
    assert [g["code"] for g in hien["Internet gia đình"]] == ["goi-meta-f1", "goi-meta-f2"]


def test_nhom_het_goi_sau_khi_loai_trung_thi_bo_ca_tieu_de():
    ch = {"nhom": [("Internet cá nhân", ["goi-giga"]), ("Internet gia đình", ["goi-giga"])], "nguon": "website"}
    assert list(zg.nhom_hien(GOI, ch)) == ["Internet cá nhân"]


def test_goi_tuong_tu_toi_da_4_dong_va_khong_trung():
    goi = GOI + [_g(20 + i, f"goi-sky-x{i}", f"Internet Sky X{i}", 500000 + i) for i in range(6)]
    ch = {"nhom": [("Internet cá nhân", ["goi-sky"] + [f"goi-sky-x{i}" for i in range(6)] + ["goi-sky-f1"]),
                   ("Internet gia đình", ["goi-sky-f1", "goi-sky-x0"])], "nguon": "website"}
    hien = [g for gs in zg.nhom_hien(goi, ch).values() for g in gs]
    kq = zg._chi_tiet([goi[1]], hien, 511, 1, "Hải Châu, Đà Nẵng", nd.chan_trang(utc_bay_gio()))
    chu = "\n".join(kq["tin"])
    tuong_tu = chu.split("Gói tương tự (gõ tên đầy đủ để xem):")[1].split("\n\n")[0].strip().splitlines()
    assert len(tuong_tu) == 4 and len(set(tuong_tu)) == 4


# ------------------------------------------------------------------ kiểu chữ
def _doan_co_kieu(tin, kieu):
    """Các đoạn chữ mang kiểu `kieu` (đổi vị trí UTF-16 của Zalo về chữ để so)."""
    b = str(tin).encode("utf-16-le")
    return [b[k["start"] * 2:(k["start"] + k["len"]) * 2].decode("utf-16-le") for k in tin.kieu if kieu in k["st"]]


def test_danh_sach_gia_noi_bat_va_so_kieu_duoi_tran():
    tin = zg.tra_loi("giá cước phường hải châu", None)["tin"][0]
    assert "245.000đ" in _doan_co_kieu(tin, "c_f27806") and "340.000đ" in _doan_co_kieu(tin, "c_f27806")
    assert any({"b", "c_f27806"} <= set(k["st"]) and "f_18" not in k["st"] for k in tin.kieu)   # giá: đậm + cam, cỡ thường
    assert "Internet Giga" in _doan_co_kieu(tin, "b") and "Internet cá nhân" in _doan_co_kieu(tin, "b")
    assert 0 < len(tin.kieu) <= nd.TRAN_KIEU


def test_chi_tiet_gia_thang_phi_va_so_tien_deu_dam():
    tin = zg.tra_loi("giá giga phường hải châu", None)["tin"][0]
    dam = _doan_co_kieu(tin, "b")
    assert "245.000đ" in _doan_co_kieu(tin, "c_f27806")
    assert "300.000đ" in dam and "2.940.000đ" in dam and "1.470.000đ" in dam and "245.000đ/tháng" in dam
    assert any(d.startswith("Internet Giga - Phường Hải Châu") for d in dam)
    assert not any("Chính sách" in d for d in dam)                                           # hạn chính sách là chữ thường


def test_nhieu_kieu_qua_thi_giu_gia_bo_kieu_phu():
    goi = [_g(100 + i, f"g{i}", f"Internet G{i}", 200000 + i) for i in range(30)]
    tin = nd.chia_tin(nd.danh_sach({"Internet cá nhân": goi}, "Hải Châu, Đà Nẵng"))
    assert all(len(t.kieu) <= nd.TRAN_KIEU for t in tin)
    assert sum(1 for t in tin for k in t.kieu if "c_f27806" in k["st"]) >= 30                 # đủ 30 giá còn nguyên màu


def test_zalo_tu_choi_kieu_chu_thi_gui_lai_ban_tron(may_khach, gui, monkeypatch):
    def ghi(c, n, *a, **k):
        if k.get("text_styles"):
            raise zalo_bot.LoiZalo("Zalo từ chối (mã 403).")
        gui.append((c, n, k.get("token")))
    monkeypatch.setattr(zalo_bot, "gui_tin", ghi)
    _gui(may_khach, _su_kien("giá giga phường hải châu"))
    assert len(gui) == 1 and "Internet Giga" in gui[0][1] and gui[0][2] == TOKEN


def test_toc_do_gon():
    assert nd.toc_do_gon("300 Mbps / 300 Mbps") == "300 Mbps"
    assert nd.toc_do_gon("1 Gbps / 300 Mbps") == "1 Gbps / 300 Mbps"
    assert nd.toc_do_gon(None) == ""


def test_lenh_help_va_huong_dan_co_ba_vi_du():
    for cau in ("/help", "hướng dẫn", "@Bot /help"):
        chu = _chu(zg.tra_loi(cau, None))
        assert chu.count("Giá ") >= 3 and "/id" in chu


# ------------------------------------------------------------------ tin dài
def test_chia_tin_dai_dung_gioi_han_va_danh_so():
    khoi = [[nd.dong_chu(f"• dòng {k}.{i} " + "x" * 80) for i in range(12)] for k in range(6)] + [[nd.dong_chu("y" * 100) for _ in range(40)]]
    tin = nd.chia_tin(khoi)
    assert len(tin) > 2 and all(len(t) <= 2000 for t in tin)
    assert tin[0].startswith(f"(1/{len(tin)})") and tin[-1].startswith(f"({len(tin)}/{len(tin)})")
    assert [str(t) for t in nd.chia_tin([[nd.dong_chu("ngắn")]])] == ["ngắn"]


# ------------------------------------------------------------------ webhook
def _su_kien(text, chat="g1", ma="m1", loai="GROUP", nguoi="u9", bot=False, ev="message.text.received"):
    return {"event_name": ev, "message": {"message_id": ma, "date": 1, "text": text, "from": {"id": nguoi, "display_name": "Chị Lan", "is_bot": bot},
                                          "chat": {"id": chat, "chat_type": loai}}}


def _gui(c, payload, khoa="dung"):
    h = {} if khoa is None else {"X-Bot-Api-Secret-Token": zg.khoa_webhook() if khoa == "dung" else khoa}
    return c.post("/api/zalo-gia/webhook", data=json.dumps(payload) if payload is not None else "", content_type="application/json", headers=h)


def test_khoa_sai_hoac_thieu_thi_403_dung_khoa_thi_luon_200(may_khach, gui):
    assert _gui(may_khach, _su_kien("x"), khoa=None).status_code == 403
    assert _gui(may_khach, _su_kien("x"), khoa="sai").status_code == 403
    assert not gui
    assert _gui(may_khach, None).status_code == 200                       # không có nội dung
    assert _gui(may_khach, {"linh": "tinh"}).status_code == 200
    assert _gui(may_khach, _su_kien("giá giga phường hải châu")).status_code == 200


def test_khoa_webhook_khac_khoa_ban_tin():
    from app import ban_tin_cho_duyet as cd
    assert len(zg.khoa_webhook()) == 64 and zg.khoa_webhook() != cd.khoa_webhook()
    assert zg.khoa_dung(zg.khoa_webhook()) and not zg.khoa_dung("") and not zg.khoa_dung(None)


def test_nhom_hoi_gia_bot_tra_loi_bang_token_bot_gia(may_khach, gui):
    _gui(may_khach, _su_kien("@Bot Giá cước GiGa ở phường Nam Nha Trang, Khánh Hoà"))
    assert len(gui) == 1 and gui[0][0] == "g1" and gui[0][2] == TOKEN and "Internet Giga" in gui[0][1]


def test_chat_rieng_cung_chay(may_khach, gui):
    _gui(may_khach, _su_kien("giá giga phường hải châu", chat="u1", loai="PRIVATE"))
    assert gui and "Internet Giga" in gui[0][1]


def test_dang_boc_trong_result_cung_doc_duoc(may_khach, gui):
    _gui(may_khach, {"ok": True, "result": _su_kien("giá giga phường hải châu")})
    assert gui and "Internet Giga" in gui[0][1]


def test_chat_chua_cap_quyen_chi_nhan_ma_chat_khong_lo_gia(may_khach, gui):
    _gui(may_khach, _su_kien("giá giga phường hải châu", chat="lạ-99"))
    assert len(gui) == 1 and gui[0][1] == "Chat này chưa được cấp quyền. Mã chat: lạ-99. Gửi mã này cho Admin để được mở."
    assert "245" not in gui[0][1]


def test_lenh_id_luon_tra_ma_chat_ke_ca_chua_cap_quyen(may_khach, gui):
    _gui(may_khach, _su_kien("@Bot /id", chat="lạ-99", ma="m2"))
    assert gui == [("lạ-99", "Mã chat này: lạ-99", TOKEN)]


def test_cung_message_id_chi_tra_loi_mot_lan(may_khach, gui):
    for _ in range(3):
        _gui(may_khach, _su_kien("giá giga phường hải châu", ma="trung"))
    assert len(gui) == 1


def test_gioi_han_toc_do_moi_chat(may_khach, gui):
    for i in range(zg.TOI_DA_CAU_PHUT + 4):
        _gui(may_khach, _su_kien("/help", ma=f"t{i}"))
    chu = [g[1] for g in gui]
    assert len(chu) == zg.TOI_DA_CAU_PHUT + 1 and "hỏi nhanh quá" in chu[-1]
    _gui(may_khach, _su_kien("/help", chat="u1", ma="khac"))              # chat khác không bị ảnh hưởng
    assert gui[-1][0] == "u1"


def test_tin_cua_bot_va_nguoi_la_khong_tra_loi(may_khach, gui):
    _gui(may_khach, _su_kien("giá giga phường hải châu", bot=True))
    _gui(may_khach, _su_kien("giá giga phường hải châu", ev="message.image.received", ma="a"))
    assert not gui


def test_hoi_lai_qua_hai_tin_webhook_tung_nguoi_rieng(may_khach, gui):
    _gui(may_khach, _su_kien("giá meta phường hải châu", ma="a", nguoi="n1"))
    _gui(may_khach, _su_kien("giá sky phường hải châu", ma="b", nguoi="n2"))     # người khác hỏi xen giữa
    _gui(may_khach, _su_kien("2", ma="c", nguoi="n1"))
    assert "1. Internet Meta F1" in gui[0][1] and "Internet Sky - Phường" in gui[1][1] and "Internet Meta F2 - Phường" in gui[2][1]


def test_hoi_lai_het_han_sau_10_phut(may_khach, gui):
    from datetime import timedelta

    from sqlalchemy import update

    from app.db import session_scope
    from app.models import ZaloGiaHoiLai
    _gui(may_khach, _su_kien("giá meta phường hải châu", ma="a"))
    with session_scope() as s:
        s.execute(update(ZaloGiaHoiLai).values(het_han=utc_bay_gio() - timedelta(minutes=1)))
    _gui(may_khach, _su_kien("2", ma="b"))
    assert "chưa có câu hỏi nào đang chờ" in gui[-1][1]


def test_payload_la_duoc_ghi_nhat_ky_toi_da_500_ky_tu_va_khong_lo_token(may_khach, gui):
    from sqlalchemy import select

    from app.db import session_scope
    from app.models import AuditLog
    _gui(may_khach, {"event_name": "message.text.received", "message": {"noi": "dung-la", "token": TOKEN, "dai": "x" * 2000}})
    with session_scope() as s:
        ds = [r.detail for r in s.execute(select(AuditLog).where(AuditLog.action == "zalo_gia_la")).scalars()]
    assert len(ds) == 1 and len(ds[0]) <= 500 and "dung-la" in ds[0] and TOKEN not in ds[0]


def test_nhat_ky_chi_ghi_chat_goi_phuong_khong_ghi_noi_dung_tin(may_khach, gui):
    from sqlalchemy import select

    from app.db import session_scope
    from app.models import AuditLog, ZaloGiaTin
    _gui(may_khach, _su_kien("giá giga phường hải châu xin chào bí mật"))
    with session_scope() as s:
        ds = [r.detail for r in s.execute(select(AuditLog).where(AuditLog.action == "zalo_gia")).scalars()]
        cot = {c.name for c in ZaloGiaTin.__table__.columns}
    assert ds == ["chat g1: gói=Internet Giga; phường=Phường Hải Châu, Đà Nẵng"] and "bí mật" not in ds[0] and "text" not in cot


def test_fpt_loi_thi_noi_de_hieu_va_khong_treo(may_khach, gui, monkeypatch):
    def hong(t, p):
        raise gf.LoiGia("x")
    monkeypatch.setattr(gf, "goi_theo_phuong", hong)
    _gui(may_khach, _su_kien("giá giga phường hải châu"))
    assert "Chưa lấy được giá từ fpt.vn lúc này" in gui[0][1]


def test_qua_han_thi_bao_thu_lai_sau(may_khach, gui, monkeypatch):
    import time
    monkeypatch.setattr(zg, "HAN_TRA_LOI", 0.05)
    monkeypatch.setattr(gf, "goi_theo_phuong", lambda t, p: time.sleep(0.5))
    _gui(may_khach, _su_kien("giá giga phường hải châu"))
    assert "gõ lại câu hỏi sau ít giây" in gui[0][1]


# ------------------------------------------------------------------ zalo_bot nhận token riêng
def test_gui_tin_dung_token_rieng_va_khong_lo_token_khi_loi(monkeypatch):
    monkeypatch.setenv("ZALO_BOT_TOKEN", "111:BAN-TIN")
    monkeypatch.setattr(zalo_bot, "gui_tin", GUI_TIN_THAT)
    thay = []

    def gia(req, timeout=None):
        thay.append(req.full_url)
        raise urllib.error.URLError("hỏng")
    monkeypatch.setattr(zalo_bot.urllib.request, "urlopen", gia)
    with pytest.raises(zalo_bot.LoiZalo) as e:
        zalo_bot.gui_tin("c", "xin chào", token=TOKEN)
    assert thay == [f"{zalo_bot.GOC}/bot{TOKEN}/sendMessage"] and TOKEN not in str(e.value)
    with pytest.raises(zalo_bot.LoiZalo):
        zalo_bot.gui_tin("c", "xin chào")
    assert thay[1].endswith("/bot111:BAN-TIN/sendMessage")                # mặc định vẫn là bot Bản tin
    with pytest.raises(zalo_bot.LoiZalo, match="token cho bot Zalo này"):
        zalo_bot.gui_tin("c", "xin chào", token="")


# ------------------------------------------------------------------ ảnh banner
def _png_hop_le(b):
    import io

    from PIL import Image
    anh = Image.open(io.BytesIO(b))
    anh.load()
    return anh.format == "PNG" and anh.size == (za.W, za.W)


def _ct_day_du():
    ct = _ct(300000)
    ct["mo_ta"] = ["Modem Wi-Fi 6", "Kết nối 25 thiết bị"]
    ct["lua_chon"][2]["qua"] = "Tặng 1 Camera trong nhà"
    return ct


def test_ve_banner_ra_png_dung_kich_thuoc_voi_va_khong_co_qua_phi_thieu():
    g = {**GOI[0], "gia": 195000}
    assert _png_hop_le(za.ve_banner(g, _ct_day_du(), "Phường Nam Nha Trang, Khánh Hòa", utc_bay_gio()))       # đủ quà + modem
    assert _png_hop_le(za.ve_banner(g, _ct(300000), "Phường Hải Châu, Đà Nẵng"))                              # không có quà
    assert _png_hop_le(za.ve_banner(g, _ct(None), "Phường Hải Châu, Đà Nẵng"))                                # phí thiếu
    assert _png_hop_le(za.ve_banner({**g, "toc_do": None, "gia": None}, None, "Xã Quế Sơn, Đà Nẵng"))        # gần như không có dữ liệu
    assert _png_hop_le(za.ve_banner({**g, "ten": "Combo Internet Giga Eyes3 Play4 V.VIP Lite " * 2}, _ct_day_du(), "x" * 200))   # tên / địa chỉ rất dài


def test_du_lieu_banner_chi_lay_cai_co_that():
    g = {**GOI[0], "gia": 195000}
    dl = za.du_lieu(g, _ct_day_du())
    assert dl["ten_goi"] == "Giga" and dl["toc"] == ["300 Mbps", "300 Mbps"] and dl["phi"] == "300.000đ"
    assert dl["pills"] == ["Tặng 1 Camera trong nhà", "Modem Wi-Fi 6"] and dl["han"] == "Chính sách áp dụng đến hết 31/12/2026"
    assert dl["tra_truoc"]["thang"] == 13 and dl["tra_truoc"]["tang"] == 1                                    # cách tặng nhiều nhất
    trong = za.du_lieu({**g, "toc_do": None}, None)
    assert trong["pills"] == [] and trong["toc"] == [] and trong["tra_truoc"] is None and trong["han"] == ""
    assert "Mbps" not in str(za.du_lieu({**g, "toc_do": None}, _ct(300000))["toc"])


def test_phi_banner_thieu_la_chua_ro_khong_mien_phi_tru_khi_dich_vu_ghi_0():
    g = GOI[0]
    assert za.du_lieu(g, _ct(None))["phi"] == "Chưa rõ" and za.du_lieu(g, None)["phi"] == "Chưa rõ"
    assert za.du_lieu(g, _ct(0))["phi"] == "Miễn phí"
    khac = _ct(500000)
    khac["phi_nhom"] = [["Trả theo tháng", 1000000], ["Trả trước", 600000]]
    assert za.du_lieu(g, khac)["phi"] == "600.000đ - 1.000.000đ"


def test_ma_ky_dung_sai_het_han_hong():
    import time
    ma = za.tao_ma(511, 1, "goi-giga")
    assert za.doc_ma(ma) == (511, 1, "goi-giga")
    tinh, phuong, code, han, ky = ma.split(".")
    for xau in (f"511.2.{code}.{han}.{ky}", f"511.1.goi-sky.{han}.{ky}", f"511.1.{code}.{int(han) + 99}.{ky}", f"511.1.{code}.{han}.{'0' * 32}",
                "", "abc", "511.1.goi-giga", "511.1.goi giga.1.2", f"511.1.{code}.{han}.{ky}.x"):
        assert za.doc_ma(xau) is None, xau
    assert za.doc_ma(ma, bay_gio=time.time() + za.HAN_ANH_GIAY + 60) is None                  # hết hạn
    assert za.tao_ma(511, 1, "goi-giga", bay_gio=time.time() - 3600).startswith("511.1.goi-giga.")
    assert za.doc_ma(za.tao_ma(511, 1, "goi-giga", bay_gio=time.time() - 3600)) is None
    assert za.url_anh("https://x.vn", 511, 1, "co dau cach") is None


def test_khoa_anh_khac_khoa_webhook_va_khoa_anh_ban_tin():
    from app import ban_tin_anh as bta
    assert za._ky(511, 1, "goi-giga", 5) != bta._ky("2026-09-01", 5) and za._NHAN_KHOA == b"zalo-gia-anh"


def test_duong_anh_200_png_va_moi_loi_deu_404_giong_nhau(may_khach):
    import time
    ma = za.tao_ma(511, 1, "goi-giga")
    r = may_khach.get(f"/api/zalo-gia/anh/{ma}.png")
    assert r.status_code == 200 and r.mimetype == "image/png" and r.data[:8] == b"\x89PNG\r\n\x1a\n" and _png_hop_le(r.data)
    assert "Cache-Control" in r.headers and "no-store" in r.headers["Cache-Control"]
    hong = [f"{ma[:-3]}abc", "rac", za.tao_ma(511, 1, "goi-giga", bay_gio=time.time() - 9999), za.tao_ma(511, 1, "khong-co-goi"),
            za.tao_ma(511, 999999, "goi-giga")]
    kq = [may_khach.get(f"/api/zalo-gia/anh/{m}.png") for m in hong]
    assert {(x.status_code, x.data) for x in kq} == {(404, "Không tìm thấy.".encode())}
    assert may_khach.get(f"/api/zalo-gia/anh/{ma}.png?tinh=8&phuong=2&goi=goi-sky").data == r.data   # không nhận tham số nào khác


def test_duong_anh_khong_can_dang_nhap_va_dung_lai_trong_vai_phut(may_khach, monkeypatch):
    ma = za.tao_ma(511, 1, "goi-giga")
    dem = []
    goc = za.ve_banner
    monkeypatch.setattr(za, "ve_banner", lambda *a, **k: dem.append(1) or goc(*a, **k))
    for _ in range(3):
        assert may_khach.get(f"/api/zalo-gia/anh/{ma}.png").status_code == 200
    assert len(dem) == 1


def test_gui_chi_tiet_mot_goi_gui_anh_truoc_roi_tin_chu(may_khach, gui, monkeypatch):
    monkeypatch.setenv("APP_URL", "https://app.example.vn/")
    _gui(may_khach, _su_kien("@Bot giá giga phường nam nha trang khánh hòa"))
    assert gui.su_kien == ["anh", "tin"] and len(gui.anh) == 1
    c, url, caption, han, token = gui.anh[0]
    assert c == "g1" and token == TOKEN and han <= zg.HAN_ANH_GIAY
    assert caption == "Gói Giga · Phường Nam Nha Trang · 245.000đ/tháng"
    assert url.startswith("https://app.example.vn/api/zalo-gia/anh/") and url.endswith(".png")
    assert za.doc_ma(url.rsplit("/", 1)[1][:-4]) == (56, 10, "goi-giga")             # mã trong link khớp đúng gói + phường vừa hỏi
    assert "Internet Giga" in gui[0][1]


def test_banner_loi_thi_van_gui_tin_chu_khong_bao_loi_cho_nguoi_dung(may_khach, gui, monkeypatch):
    from sqlalchemy import select

    from app.db import session_scope
    from app.models import AuditLog
    monkeypatch.setenv("APP_URL", "https://app.example.vn")

    def hong(*a, **k):
        raise zalo_bot.LoiZalo("Zalo từ chối (mã 400).")
    monkeypatch.setattr(zalo_bot, "gui_anh", hong)
    _gui(may_khach, _su_kien("giá giga phường hải châu"))
    assert len(gui) == 1 and "Internet Giga" in gui[0][1] and "lỗi" not in gui[0][1].lower()
    with session_scope() as s:
        ds = [r.detail for r in s.execute(select(AuditLog).where(AuditLog.action == "zalo_gia_la")).scalars()]
    assert ds == [f"banner không gửi được sau {zg.SO_LAN_GUI_ANH} lần: Zalo từ chối (mã 400)."] and "/anh/" not in ds[0]
    monkeypatch.setattr(zalo_bot, "gui_anh", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("https://x/anh/BI-MAT.png")))
    _gui(may_khach, _su_kien("giá sky phường hải châu", ma="m2"))
    assert len(gui) == 2


def test_khong_co_app_url_https_hoac_tat_bang_bien_thi_khong_gui_anh(may_khach, gui, monkeypatch):
    _gui(may_khach, _su_kien("giá giga phường hải châu", ma="a"))                               # chưa cài APP_URL
    monkeypatch.setenv("APP_URL", "http://app.example.vn")
    _gui(may_khach, _su_kien("giá giga phường hải châu", ma="b"))                               # http
    monkeypatch.setenv("APP_URL", "https://app.example.vn")
    monkeypatch.setenv("ZALO_GIA_ANH", "0")
    _gui(may_khach, _su_kien("giá giga phường hải châu", ma="c"))                               # tắt
    assert not gui.anh and len(gui) == 3
    monkeypatch.setenv("ZALO_GIA_ANH", "1")
    _gui(may_khach, _su_kien("giá giga phường hải châu", ma="d"))
    assert len(gui.anh) == 1


def test_danh_sach_hoi_lai_va_nhieu_goi_khong_gui_anh(may_khach, gui, monkeypatch):
    monkeypatch.setenv("APP_URL", "https://app.example.vn")
    _gui(may_khach, _su_kien("giá cước phường hải châu", ma="a"))                              # danh sách
    _gui(may_khach, _su_kien("giá meta phường hải châu", ma="b"))                              # hỏi lại
    _gui(may_khach, _su_kien("giá giga và sky phường hải châu", ma="c"))                       # hai gói
    assert not gui.anh and len(gui) == 3
    _gui(may_khach, _su_kien("giá meta phường hải châu", ma="d"))
    _gui(may_khach, _su_kien("2", ma="e"))                                                     # chọn số -> một gói -> có ảnh
    assert len(gui.anh) == 1 and gui.anh[0][2].startswith("Gói Meta F2")


# ------------------------------------------------------------------ nhóm V.VIP chỉ giữ Giga và Sky
def test_nhom_vvip_chi_giu_combo_giga_va_sky():
    chu = _chu(zg.tra_loi("giá cước phường hải châu", None))
    assert "Combo Giga - V.VIP" in chu and "Combo Sky - V.VIP" in chu
    assert "Meta - V.VIP" not in chu and "Lux800" not in chu
    hien = zg.nhom_hien(GOI, CH)
    assert [g["code"] for g in hien["Combo Internet + V.VIP"]] == ["combo-internet-giga-vvip-lite", "combo-internet-sky-vvip-lite"]
    assert zg.COMBO_VVIP_GIU == {"combo-internet-giga-vvip-lite", "combo-internet-sky-vvip-lite"}


def test_combo_vvip_bi_bo_khong_khop_ten_va_khong_la_goi_tuong_tu():
    kq = zg.tra_loi("giá lux800 phường hải châu", None)
    assert "chưa thấy gói" in _chu(kq) and "Lux800" not in _chu(kq).split("Các gói đang bán:", 1)[1]
    kq = zg.tra_loi("giá combo meta phường hải châu", None)
    assert kq["hoi"]["buoc"] == "chon_goi" and "Combo Meta" not in _chu(kq) and "Meta F1" in _chu(kq)
    chu = _chu(zg.tra_loi("giá giga phường hải châu", None))
    tuong_tu = chu.split("Gói tương tự", 1)[1]
    assert "Combo Giga - V.VIP" in tuong_tu and "Meta - V.VIP" not in tuong_tu and "Lux800" not in tuong_tu


def test_hoi_combo_ra_combo_con_hoi_ten_tran_ra_goi_thuong():
    """"combo giga" / "giga v.vip" -> Combo Giga - V.VIP; "giga" -> Internet Giga (lỗi thật 05/11/2026: hỏi combo giga chỉ ra Giga)."""
    for q, mong in (("combo giga phường hải châu", "Combo Giga - V.VIP"), ("giá giga v.vip phường hải châu", "Combo Giga - V.VIP"),
                    ("giá giga vvip phường hải châu", "Combo Giga - V.VIP"), ("combo sky phường hải châu", "Combo Sky - V.VIP"),
                    ("giá giga phường hải châu", "Internet Giga - Phường")):
        kq = zg.tra_loi(q, None)
        assert kq["hoi"] is None and mong in _chu(kq).splitlines()[0], q


def test_banner_lan_dau_loi_thi_thu_lai_mot_lan_va_gui_duoc(may_khach, gui, monkeypatch):
    """Zalo tải banner chậm lần đầu (máy nguội) thì thử lại; lần hai được thì không ghi nhật ký lỗi và không gửi trùng."""
    from sqlalchemy import select

    from app.db import session_scope
    from app.models import AuditLog
    monkeypatch.setenv("APP_URL", "https://app.example.vn")
    lan = []

    def cham(*a, **k):
        lan.append(1)
        if len(lan) == 1:
            raise zalo_bot.LoiZalo("Zalo từ chối (mã 400).")
    monkeypatch.setattr(zalo_bot, "gui_anh", cham)
    _gui(may_khach, _su_kien("giá giga phường hải châu"))
    assert len(lan) == 2 and len(gui) == 1
    with session_scope() as s:
        assert not list(s.execute(select(AuditLog).where(AuditLog.action == "zalo_gia_la")).scalars())


def test_dong_tra_truoc_khong_co_duoi_qua_camera_cloud():
    """Chủ app 05/11/2026: tin chữ bỏ "Nhận thêm Camera + Cloud 12T miễn phí" ở từng cách thanh toán."""
    z = {"hinh_thuc": "Trả trước", "thang": 13, "tong": 2340000, "thang_dong": 12, "tang": 1, "qua": "Nhận thêm Camera + Cloud 12T miễn phí"}
    chu = nd._chu(nd._dong_thanh_toan(z))
    assert "2.340.000đ" in chu and "tặng 1" in chu and "Camera" not in chu and "Cloud" not in chu


# ------------------------------------------------------------------ ảnh gói lấy từ fpt.vn
URL_ANH = "https://s3-api.fpt.vn/fptvn-storage/uploads/internet-giga-3.jpg"


def _anh_gia(rong=500, cao=361, dinh_dang="JPEG"):
    import io

    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (rong, cao), (30, 120, 240)).save(b, dinh_dang)
    return b.getvalue()


@pytest.fixture()
def tai_anh(monkeypatch):
    """Chặn mạng: `za._tai_byte` trả ảnh Pillow tạo tại chỗ (ghi lại địa chỉ được tải)."""
    ds = []
    kq = {"byte": _anh_gia()}

    def gia(url):
        ds.append(url)
        if isinstance(kq["byte"], Exception):
            raise kq["byte"]
        return kq["byte"]
    za._anh_cache.clear()
    monkeypatch.setattr(za, "_tai_byte", gia)
    yield kq, ds
    za._anh_cache.clear()


def _kich_thuoc(b):
    import io

    from PIL import Image
    return Image.open(io.BytesIO(b)).size


def test_co_anh_fpt_thi_ra_png_doc_rong_1080_cao_co_dinh(tai_anh):
    g = {**GOI[0], "gia": 195000, "anh": URL_ANH}
    r1, r2 = (za.ve_banner(g, _ct_day_du(), "Phường Hải Châu, Đà Nẵng", utc_bay_gio()),
              za.ve_banner(g, _ct(None), "Phường Hải Châu, Đà Nẵng", utc_bay_gio()))
    (w1, h1), (w2, h2) = _kich_thuoc(r1), _kich_thuoc(r2)
    assert w1 == w2 == za.W and h1 > w1 and h2 > w2                         # khổ dọc
    assert round(za.W / za.ANH_TY_LE) < h1 < 2000
    kq_khac = za.ve_banner({**g, "anh": URL_ANH}, None, "x", None)
    assert _kich_thuoc(kq_khac)[0] == za.W


def test_anh_fpt_moi_ti_le_deu_cat_ve_cung_chieu_cao(tai_anh):
    from PIL import Image
    for rong, cao in ((500, 361), (1250, 902), (900, 900), (2000, 600), (400, 800)):
        out = za._bia_anh(Image.open(__import__("io").BytesIO(_anh_gia(rong, cao))))
        assert out.size == (za.W, round(za.W / za.ANH_TY_LE)), (rong, cao)


def test_khong_co_anh_hoac_anh_loi_thi_dung_banner_tu_ve_vuong(tai_anh):
    kq, ds = tai_anh
    g = {**GOI[0], "gia": 195000}
    assert _png_hop_le(za.ve_banner({**g, "anh": ""}, _ct(300000), "Phường Hải Châu, Đà Nẵng"))        # gói không có ảnh
    assert not ds                                                                                       # không có ảnh thì không tải gì
    kq["byte"] = OSError("mạng hỏng")
    assert _png_hop_le(za.ve_banner({**g, "anh": URL_ANH}, _ct(300000), "x"))                           # tải lỗi
    kq["byte"] = b"day khong phai anh"
    za._anh_cache.clear()
    assert _png_hop_le(za.ve_banner({**g, "anh": URL_ANH}, _ct(300000), "x"))                           # không phải ảnh


def test_chong_ssrf_chi_tai_https_s3_api_fpt_vn(tai_anh):
    _, ds = tai_anh
    g = {**GOI[0], "gia": 195000}
    for url in ("http://s3-api.fpt.vn/a.jpg", "https://evil.example.com/a.jpg", "https://s3-api.fpt.vn.evil.com/a.jpg",
                "https://evil.com/s3-api.fpt.vn/a.jpg", "https://user@s3-api.fpt.vn/a.jpg", "https://s3-api.fpt.vn:8443/a.jpg",
                "https://127.0.0.1/a.jpg", "file:///etc/passwd", "ftp://s3-api.fpt.vn/a.jpg", "//s3-api.fpt.vn/a.jpg", "s3-api.fpt.vn/a.jpg"):
        assert not za.url_anh_hop_le(url), url
        assert za.tai_anh_goc(url) is None
        assert _png_hop_le(za.ve_banner({**g, "anh": url}, None, "x"))
    assert not ds                                                                                       # không địa chỉ lạ nào được tải
    assert za.url_anh_hop_le(URL_ANH) and za.url_anh_hop_le("https://s3-api.fpt.vn:443/a.jpg")


def test_anh_qua_lon_thi_bo(monkeypatch):
    za._anh_cache.clear()

    class Tra:
        def __init__(self, dai, noi_dung):
            self.headers, self._b = {"Content-Length": str(dai)} if dai else {}, noi_dung

        def read(self, n=-1):
            return self._b[:n] if n >= 0 else self._b

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    to = _anh_gia()
    monkeypatch.setattr(za._opener, "open", lambda req, timeout=None: Tra(za.TOI_DA_BYTE_ANH + 1, to))          # khai báo quá lớn
    with pytest.raises(ValueError):
        za._tai_byte(URL_ANH)
    monkeypatch.setattr(za._opener, "open", lambda req, timeout=None: Tra(0, b"x" * (za.TOI_DA_BYTE_ANH + 5)))   # không khai báo nhưng thực tế quá lớn
    with pytest.raises(ValueError):
        za._tai_byte(URL_ANH)
    assert za.tai_anh_goc(URL_ANH) is None
    za._anh_cache.clear()
    monkeypatch.setattr(za._opener, "open", lambda req, timeout=None: Tra(len(to), to))
    assert za._tai_byte(URL_ANH) == to
    assert za.tai_anh_goc(URL_ANH) is not None


def test_tai_anh_khong_di_theo_chuyen_huong_va_gui_user_agent_trinh_duyet(monkeypatch):
    import urllib.request
    req = urllib.request.Request(URL_ANH, headers={"User-Agent": za._UA})
    assert za._KhongChuyenHuong().redirect_request(req, None, 302, "Found", {}, "http://127.0.0.1/x") is None
    thay = []

    class R:
        headers = {}

        def read(self, n=-1):
            return _anh_gia()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(za._opener, "open", lambda req, timeout=None: thay.append((req, timeout)) or R())
    za._tai_byte(URL_ANH)
    req2, han = thay[0]
    assert req2.get_header("User-agent").startswith("Mozilla/5.0") and han == za.HAN_TAI_ANH <= 6


def test_anh_tai_roi_nho_tam_va_tai_hong_nho_ngan(tai_anh):
    kq, ds = tai_anh
    assert za.tai_anh_goc(URL_ANH) is not None and za.tai_anh_goc(URL_ANH) is not None
    assert ds == [URL_ANH]
    za._anh_cache.clear()
    kq["byte"] = OSError("hỏng")
    assert za.tai_anh_goc(URL_ANH) is None and za.tai_anh_goc(URL_ANH) is None
    assert len(ds) == 2                                                                                 # tải hỏng chỉ thử một lần trong vài phút


def test_chuan_goi_lay_anh_images_dau_tien():
    x = {"id": 1, "code": "goi-giga", "name": "Internet Giga", "type": "internet", "price": {"price": 1}, "card_description": ""}
    assert gf._chuan_goi({**x, "images": [{"url": URL_ANH}, {"url": "https://s3-api.fpt.vn/b.jpg"}]})["anh"] == URL_ANH
    assert gf._chuan_goi(x)["anh"] == "" and gf._chuan_goi({**x, "images": []})["anh"] == "" and gf._chuan_goi({**x, "images": [{}]})["anh"] == ""


def test_duong_anh_dung_anh_fpt_khi_goi_co_anh(may_khach, tai_anh, monkeypatch):
    goi = [{**g, "anh": URL_ANH if g["code"] == "goi-giga" else ""} for g in GOI]
    monkeypatch.setattr(gf, "goi_theo_phuong", lambda t, p: {"goi": goi, "luc": utc_bay_gio(), "cu": False})
    za._cache.clear()
    r = may_khach.get(f"/api/zalo-gia/anh/{za.tao_ma(511, 1, 'goi-giga')}.png")
    assert r.status_code == 200 and _kich_thuoc(r.data)[1] > za.W                                       # khổ dọc
    r = may_khach.get(f"/api/zalo-gia/anh/{za.tao_ma(511, 1, 'goi-sky')}.png")
    assert r.status_code == 200 and _png_hop_le(r.data)                                                 # gói không có ảnh: bản tự vẽ vuông
