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
       _g(6, "super-300-biz", "Super300 Biz", 450000)]
CH = {"nhom": [("Internet cá nhân", ["goi-giga", "goi-sky"]), ("Internet gia đình", ["goi-sky-f1", "goi-meta-f1", "goi-meta-f2"]),
               ("Internet doanh nghiệp", ["super-300-biz"])], "nguon": "website"}


def _lc(hinh_thuc, thang, tong, phi, tang=0, thang_dong=None, den="31/12/2026"):
    return {"hinh_thuc": hinh_thuc, "thang": thang, "tong": tong, "phi_lap": phi, "thiet_bi": None, "thang_dong": thang_dong or thang,
            "tang": tang, "binh_quan": None, "qua": "", "chinh_sach": "CS", "ma": "", "den": den}


def _ct(phi):
    """phi: số (cả ba cách cùng mức), 0 = dịch vụ ghi rõ miễn phí, None = mất dòng phí."""
    lc = [_lc("Trả sau", 1, 245000, phi), _lc("Trả trước", 6, 1470000, phi), _lc("Trả trước", 13, 2940000, phi, tang=1, thang_dong=12)]
    return {"ten": "x", "gia": 245000, "phi_nhom": [] if phi is None else [["Trả theo tháng · trả trước 6 / 13 tháng", phi]],
            "thiet_bi": None, "mo_ta": [], "lua_chon": lc, "luc": utc_bay_gio()}


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
    gui = []
    monkeypatch.setattr(zalo_bot, "gui_tin", lambda c, n, *a, **k: gui.append((c, n, k.get("token"))))
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
    assert "Trả theo tháng: 245.000đ/tháng" in chu
    assert "Trả trước 13 tháng: 2.940.000đ (đóng 12 tháng, tặng 1 tháng)" in chu
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
def test_chi_hoi_gia_phuong_thi_liet_ke_theo_nhom_va_nhac_go_ten_goi():
    chu = _chu(zg.tra_loi("giá cước phường hải châu", None))
    assert "Internet cá nhân" in chu and "• Internet Giga: 245.000đ/tháng - 1 Gbps / 300 Mbps" in chu
    assert "Internet doanh nghiệp" in chu and "Gõ thêm tên gói để xem chi tiết" in chu


def test_hoi_nhom_doanh_nghiep_chi_liet_ke_nhom_do():
    chu = _chu(zg.tra_loi("giá gói doanh nghiệp phường hải châu", None))
    assert "Super300 Biz" in chu and "Internet Giga" not in chu


def test_lenh_help_va_huong_dan_co_ba_vi_du():
    for cau in ("/help", "hướng dẫn", "@Bot /help"):
        chu = _chu(zg.tra_loi(cau, None))
        assert chu.count("Giá ") >= 3 and "/id" in chu


# ------------------------------------------------------------------ tin dài
def test_chia_tin_dai_dung_gioi_han_va_danh_so():
    khoi = [("• dòng " + "x" * 80 + "\n") * 12 for _ in range(6)] + ["y" * 3000]
    tin = nd.chia_tin(khoi)
    assert len(tin) > 2 and all(len(t) <= 2000 for t in tin)
    assert tin[0].startswith(f"(1/{len(tin)})") and tin[-1].startswith(f"({len(tin)}/{len(tin)})")
    assert nd.chia_tin(["ngắn"]) == ["ngắn"]


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
