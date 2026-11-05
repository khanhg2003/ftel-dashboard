"""Bot Zalo trả lời số liệu bằng trợ lý AI (app/zalo_gia_ai.py + đường định tuyến ở app/zalo_gia.py). Không gọi OpenAI / Zalo / fpt.vn thật:
`tro_ly.chat` và các hàm giá được thay bằng hàm giả."""
from __future__ import annotations

import itertools
import json
import sys
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import gia_fpt as gf                      # noqa: E402
from app import gia_fpt_nhom as gn                 # noqa: E402
from app import tro_ly as ai                       # noqa: E402
from app import zalo_bot, zalo_gia as zg           # noqa: E402
from app import zalo_gia_ai as za                  # noqa: E402
from app.config import DATA_DIR                    # noqa: E402
from app.thoi_gian import utc_bay_gio              # noqa: E402

pytestmark = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(),
                                reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")
TOKEN = "999:GIA-BI-MAT"
_MA = itertools.count(1)

TINH = [{"id": 511, "ten": "Đà Nẵng"}]
PHUONG = {511: [{"id": 1, "ten": "Phường Hải Châu"}]}
GOI = [{"id": 1, "code": "goi-giga", "ten": "Internet Giga", "khach": "ca_nhan", "gia": 245000, "toc_do": "1 Gbps / 300 Mbps",
        "thiet_bi": None, "uu_dai": "", "nhan": "", "mo_ta": []},
       {"id": 2, "code": "goi-meta-f1", "ten": "Internet Meta F1", "khach": "ca_nhan", "gia": 340000, "toc_do": "1 Gbps / 300 Mbps",
        "thiet_bi": None, "uu_dai": "", "nhan": "", "mo_ta": []},
       {"id": 3, "code": "goi-meta-f2", "ten": "Internet Meta F2", "khach": "ca_nhan", "gia": 390000, "toc_do": "1 Gbps / 300 Mbps",
        "thiet_bi": None, "uu_dai": "", "nhan": "", "mo_ta": []}]
CH = {"nhom": [("Internet cá nhân", ["goi-giga"]), ("Internet gia đình", ["goi-meta-f1", "goi-meta-f2"])], "nguon": "website"}
CT = {"ten": "x", "gia": 245000, "phi_nhom": [["Trả theo tháng", 300000]], "thiet_bi": None, "mo_ta": [], "luc": utc_bay_gio(),
      "lua_chon": [{"hinh_thuc": "Trả sau", "thang": 1, "tong": 245000, "phi_lap": 300000, "thiet_bi": None, "thang_dong": 1, "tang": 0,
                    "binh_quan": None, "qua": "", "chinh_sach": "CS", "ma": "", "den": "31/12/2026"}]}


class Ghi(list):
    """Các tin bot gửi (chat, chữ, token); `.kieu` là text_styles; `.ai` là các lần gọi trợ lý (tên tài khoản, lịch sử, câu hỏi)."""

    def __init__(self):
        super().__init__()
        self.kieu, self.ai = [], []


@pytest.fixture(autouse=True)
def moi_truong(monkeypatch):
    from sqlalchemy import delete

    from app.db import session_scope
    from app.models import AuditLog, ZaloGiaHoiLai, ZaloGiaHoiThoai, ZaloGiaTin

    def don():
        with session_scope() as s:
            for b in (ZaloGiaTin, ZaloGiaHoiLai, ZaloGiaHoiThoai):
                s.execute(delete(b))
            s.execute(delete(AuditLog).where(AuditLog.action.in_(["zalo_gia", "zalo_gia_la", "zalo_gia_ai"])))
    zg.dam_bao_bang()
    za.dam_bao_bang()
    don()
    for k, v in {"ZALO_GIA_TOKEN": TOKEN, "ZALO_GIA_CHO_PHEP": "g1, u1", "ZALO_GIA_TAI_KHOAN": "admin"}.items():
        monkeypatch.setenv(k, v)
    for k in ("ZALO_GIA_AI", "ZALO_GIA_AI_TOI_DA_NGAY", "ZALO_GIA_GHI_LOG", "ZALO_GIA_TEN_BOT", "APP_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(gf, "danh_sach_tinh", lambda: TINH)
    monkeypatch.setattr(gf, "danh_sach_phuong", lambda t: PHUONG[t])
    monkeypatch.setattr(gf, "goi_theo_phuong", lambda t, p: {"goi": GOI, "luc": utc_bay_gio(), "cu": False})
    monkeypatch.setattr(gf, "chi_tiet_nhieu", lambda t, p, goi: {g["code"]: CT for g in goi})
    monkeypatch.setattr(gn, "cau_hinh", lambda: CH)
    gui = Ghi()
    monkeypatch.setattr(zalo_bot, "gui_tin", lambda c, n, *a, **k: (gui.append((c, n, k.get("token"))), gui.kieu.append(k.get("text_styles"))))
    tra = {"chu": "**IBB7** hôm qua có 12 online (cùng kỳ 9).", "loi": None}

    def chat_gia(user, lich_su, cau, ngu_canh, cong_cu, chay_cong_cu, khoa_luu=None):
        gui.ai.append((user.username, list(lich_su), cau, khoa_luu))
        if tra["loi"] is not None:
            raise tra["loi"]
        return tra["chu"]
    monkeypatch.setattr(ai, "chat", chat_gia)
    gui.tra = tra
    yield gui
    don()


@pytest.fixture()
def gui(moi_truong):
    return moi_truong


@pytest.fixture()
def may_khach():
    from app.ui.app import server
    return server.test_client()


def _hoi(c, text, chat="g1", nguoi="u9", ma=None):
    payload = {"event_name": "message.text.received",
               "message": {"message_id": ma or f"m{next(_MA)}", "date": 1, "text": text, "from": {"id": nguoi, "display_name": "Chị Lan", "is_bot": False},
                           "chat": {"id": chat, "chat_type": "GROUP"}}}
    h = {"X-Bot-Api-Secret-Token": zg.khoa_webhook()}
    return c.post("/api/zalo-gia/webhook", data=json.dumps(payload), content_type="application/json", headers=h)


# ------------------------------------------------------------------ định tuyến
CAU_SO_LIEU = ["@Bot Tra Cứu Giá IBB7 hôm qua IBB7 online bao nhiêu số", "dự báo cuối tháng toàn chi nhánh", "DNG.Anhtu hôm nay bán mấy",
               "IBB7 tồn bao nhiêu HĐ quá 7 ngày", "V.VIP tháng này so cùng kỳ", "mục tiêu tháng của phòng IBB5", "Camera hôm qua bao nhiêu"]
CAU_GIA = ["Giá cước GiGa ở phường Nam Nha Trang, Khánh Hoà", "giá meta phường hải châu", "giá giga phường hải châu", "bảng giá cước phường Hải Châu",
           "giá gói gia đình xã Quế Sơn"]


def test_huong_cau_gia_giu_duong_quy_tac_cau_so_lieu_di_ai():
    for c in CAU_GIA:
        assert za.huong(zg.chuan(zg.bo_mention(c)), None, False) == "gia", c
    for c in CAU_SO_LIEU:
        assert za.huong(zg.chuan(zg.bo_mention(c)), None, False) == "ai", c


def test_huong_mo_ho_uu_tien_gia():
    assert za.huong("online giga phuong hai chau", None, False) == "gia_roi_ai"      # có cả số liệu lẫn địa chỉ: thử giá trước
    assert za.huong("gia", None, False) == "gia" and za.huong("giga", None, False) == "gia"
    assert za.huong("xin chao", None, False) == "ai_mem"                               # không giống câu nào
    assert za.huong("2", {"buoc": "chon_goi"}, True) == "gia"                           # đang chọn số của câu giá
    assert za.huong("hai chau", {"buoc": "cho_phuong"}, False) == "gia"
    assert za.huong("con hom kia", None, True) == "ai"                                  # hỏi tiếp số liệu
    assert za.huong("help", None, True) == "gia" and za.huong("id", None, False) == "gia"


def test_cau_gia_van_ra_duong_gia_khong_goi_ai(may_khach, gui):
    for c in CAU_GIA[1:3]:
        _hoi(may_khach, c)
    assert not gui.ai and len(gui) == 2 and "Internet" in gui[1][1]


def test_cau_so_lieu_di_ai_tra_tin_chu_tron_dung_quyen_admin(may_khach, gui):
    for c in CAU_SO_LIEU[:4]:
        _hoi(may_khach, c)
    assert [g[0] for g in gui.ai] == ["admin"] * 4                                      # luôn bằng tài khoản đại diện
    assert gui.ai[0][2] == "Tra Cứu Giá IBB7 hôm qua IBB7 online bao nhiêu số"          # đã bỏ @mention
    assert len(gui) == 4 and all(g[2] == TOKEN for g in gui)
    assert gui[0][1] == "IBB7 hôm qua có 12 online (cùng kỳ 9)." and not any(gui.kieu)   # bỏ ** của Markdown, không text_styles


def test_giu_nguyen_giong_fox_va_khong_cache_qua_ngay(may_khach, gui):
    _hoi(may_khach, CAU_SO_LIEU[1])
    assert gui.ai[0][3].startswith("zalo-gia|20")                                       # khoá lưu có ngày hôm nay: "hôm qua" không dính bản cũ


def test_gia_khong_ra_gi_thi_chuyen_ai_con_gia_tra_loi_duoc_thi_khong(may_khach, gui):
    _hoi(may_khach, "online bao nhiêu ở phường Xyzabc")                                  # địa chỉ không có: giá không tìm ra gì -> AI
    assert len(gui.ai) == 1
    _hoi(may_khach, "online giga phường hải châu")                                       # giá trả lời được -> không AI
    assert len(gui.ai) == 1 and "Internet Giga" in gui[-1][1]


def test_dang_hoi_gia_do_thi_so_chon_van_la_cau_gia(may_khach, gui):
    _hoi(may_khach, "giá meta phường hải châu")
    _hoi(may_khach, "2")
    assert not gui.ai and "Internet Meta F2" in gui[-1][1]


def test_cau_la_di_ai_khi_da_cai_tai_khoan_con_chua_cai_thi_giu_duong_gia(may_khach, gui, monkeypatch):
    _hoi(may_khach, "xin chào")
    assert len(gui.ai) == 1
    monkeypatch.delenv("ZALO_GIA_TAI_KHOAN")
    _hoi(may_khach, "xin chào", nguoi="n2")
    assert len(gui.ai) == 1 and "phường/xã nào" in gui[-1][1]                              # đường giá cũ (hỏi phường)


# ------------------------------------------------------------------ quyền, bật / tắt
def test_chat_chua_cap_quyen_khong_dung_ai(may_khach, gui):
    _hoi(may_khach, CAU_SO_LIEU[0], chat="lạ-99")
    assert not gui.ai and gui[0][1].startswith("Chat này chưa được cấp quyền. Mã chat: lạ-99.")


def test_thieu_tai_khoan_hoac_khong_phai_admin_thi_mot_cau_thong_bao(may_khach, gui, monkeypatch):
    from app.db import session_scope
    from app.models import User
    monkeypatch.delenv("ZALO_GIA_TAI_KHOAN")
    _hoi(may_khach, CAU_SO_LIEU[2])
    monkeypatch.setenv("ZALO_GIA_TAI_KHOAN", "khong.co.nguoi.nay")
    _hoi(may_khach, CAU_SO_LIEU[2])
    with session_scope() as s:
        s.add(User(username="kiemthu.sale", ho_ten="K", password_hash="x", role="nvkd", scope="[]", active=True))
    try:
        monkeypatch.setenv("ZALO_GIA_TAI_KHOAN", "kiemthu.sale")
        assert za.tai_khoan() is None
        _hoi(may_khach, CAU_SO_LIEU[2])
    finally:
        with session_scope() as s:
            s.query(User).filter(User.username == "kiemthu.sale").delete()
    assert not gui.ai and [g[1] for g in gui] == [za.CHUA_BAT] * 3


def test_tai_khoan_chi_doc_dung_admin_dang_hoat_dong():
    u = za.tai_khoan()
    assert u is not None and u.username == "admin" and u.role == "admin" and u.phong_duoc_xem() is None


def test_za_ai_0_tat_han_chi_con_tra_gia(may_khach, gui, monkeypatch):
    monkeypatch.setenv("ZALO_GIA_AI", "0")
    _hoi(may_khach, CAU_SO_LIEU[0])
    assert not gui.ai and "phường/xã nào" in gui[0][1]
    _hoi(may_khach, "giá giga phường hải châu")
    assert "Internet Giga" in gui[1][1]


def test_tran_an_toan_moi_ngay_moi_chat(may_khach, gui, monkeypatch):
    monkeypatch.setenv("ZALO_GIA_AI_TOI_DA_NGAY", "2")
    for _ in range(3):
        _hoi(may_khach, CAU_SO_LIEU[3])
    assert len(gui.ai) == 2 and "đã hỏi số liệu 2 lần hôm nay" in gui[-1][1]
    _hoi(may_khach, CAU_SO_LIEU[3], chat="u1")                                            # chat khác không bị ảnh hưởng
    assert len(gui.ai) == 3


def test_tran_mac_dinh_rat_cao_va_0_la_tat_tran(monkeypatch):
    assert za.tran_ngay() == 300
    monkeypatch.setenv("ZALO_GIA_AI_TOI_DA_NGAY", "0")
    assert za.tran_ngay() == 0
    monkeypatch.setenv("ZALO_GIA_AI_TOI_DA_NGAY", "abc")
    assert za.tran_ngay() == 300


def test_khong_tran_thi_hoi_nhieu_van_tra_loi(may_khach, gui, monkeypatch):
    monkeypatch.setenv("ZALO_GIA_AI_TOI_DA_NGAY", "0")
    for _ in range(5):
        _hoi(may_khach, CAU_SO_LIEU[3])
    assert len(gui.ai) == 5


# ------------------------------------------------------------------ lỗi AI
def test_loi_ai_thanh_cau_de_hieu_khong_lo_chi_tiet_ky_thuat(may_khach, gui):
    gui.tra["loi"] = ai.LoiAI("Trợ lý AI đang tắt. Quản trị bật ở Quản trị → Trợ lý AI.")
    _hoi(may_khach, CAU_SO_LIEU[0])
    gui.tra["loi"] = ai.LoiAI("Câu hỏi cần tra nhiều số quá, hãy hỏi hẹp lại (một phòng hoặc một kỳ).")
    _hoi(may_khach, CAU_SO_LIEU[0])
    gui.tra["loi"] = RuntimeError("postgresql://user:matkhau@host/db  sk-BI-MAT-123")
    _hoi(may_khach, CAU_SO_LIEU[0])
    gui.tra["loi"] = ai.LoiAI("Đã dùng hết ngân sách AI tháng này (20 USD). Quản trị có thể nâng trần ở Quản trị → Trợ lý AI.")
    _hoi(may_khach, CAU_SO_LIEU[0])
    chu = [g[1] for g in gui]
    assert "chưa sẵn sàng" in chu[0] and "Quản trị bật ở" not in chu[0]
    assert chu[1] == za.QUA_NHIEU and chu[2] == za.LOI_CHUNG
    assert "matkhau" not in " ".join(chu) and "sk-" not in " ".join(chu) and "ngân sách AI" in chu[3]


def test_tra_loi_rong_thi_bao_chua_tra_duoc(may_khach, gui):
    gui.tra["chu"] = "   "
    _hoi(may_khach, CAU_SO_LIEU[0])
    assert gui[0][1] == za.LOI_CHUNG


# ------------------------------------------------------------------ chữ ra Zalo
def test_bo_markdown_bang_thanh_dong_ngan_va_gach_dau_dong():
    md = ("# Kết quả\n**Kết luận:** IBB7 đạt `12` online.\n\n- Phòng A: 5\n* Phòng B: 7\n\n| Phòng | Online |\n|---|---|\n| IBB7 | 12 |\n| IBB5 | 9 |\n"
          "__đậm__ và *nghiêng*")
    ra = za.bo_markdown(md)
    assert "**" not in ra and "#" not in ra and "`" not in ra and "|" not in ra and "---" not in ra
    assert "Kết luận: IBB7 đạt 12 online." in ra and "• Phòng A: 5" in ra and "• Phòng B: 7" in ra
    assert "Phòng · Online" in ra and "IBB7 · 12" in ra and "đậm và nghiêng" in ra


def test_cau_tra_loi_dai_duoc_tach_dung_gioi_han(may_khach, gui):
    gui.tra["chu"] = "\n\n".join(f"**Phòng {i}**\n" + "\n".join(f"- Nhân sự {j}: {j * 3 + i} online so với cùng kỳ {j}" for j in range(12)) for i in range(25))
    _hoi(may_khach, "liệt kê online từng nhân sự tất cả phòng")
    assert len(gui) > 2 and all(len(g[1]) <= 2000 for g in gui)
    assert gui[0][1].startswith(f"(1/{len(gui)})") and gui[-1][1].startswith(f"({len(gui)}/{len(gui)})")
    assert not any("**" in g[1] for g in gui) and not any(gui.kieu)


# ------------------------------------------------------------------ hội thoại nhiều lượt
def test_hoi_tiep_co_lich_su_het_han_sau_10_phut(may_khach, gui):
    from sqlalchemy import update

    from app.db import session_scope
    from app.models import ZaloGiaHoiThoai
    _hoi(may_khach, "IBB7 hôm qua online bao nhiêu")
    assert gui.ai[0][1] == []
    _hoi(may_khach, "còn hôm kia?")
    assert [m["role"] for m in gui.ai[1][1]] == ["user", "assistant"] and "IBB7 hôm qua online" in gui.ai[1][1][0]["content"]
    _hoi(may_khach, "còn hôm kia?", nguoi="n2")                                           # người khác trong nhóm: không dính lịch sử
    assert gui.ai[2][1] == []
    with session_scope() as s:
        s.execute(update(ZaloGiaHoiThoai).values(het_han=utc_bay_gio() - timedelta(minutes=1)))
    _hoi(may_khach, "còn hôm kia?")
    assert gui.ai[3][1] == []                                                              # đã hết hạn


def test_chi_nho_sau_tin_gan_nhat_va_khong_luu_khi_loi(may_khach, gui):
    for i in range(5):
        _hoi(may_khach, f"IBB{i} online hôm qua bao nhiêu")
    assert len(gui.ai[-1][1]) == za.SO_TIN_NHO
    assert za.doc_hoi_thoai("g1:u9")[-1]["role"] == "assistant" and len(za.doc_hoi_thoai("g1:u9")) == za.SO_TIN_NHO
    gui.tra["loi"] = ai.LoiAI("lỗi")
    _hoi(may_khach, "IBB9 online hôm qua")
    assert len(za.doc_hoi_thoai("g1:u9")) == za.SO_TIN_NHO and "IBB9" not in za.doc_hoi_thoai("g1:u9")[-2]["content"]


# ------------------------------------------------------------------ nhật ký + chống trùng
def test_nhat_ky_chi_ghi_chat_va_200_ky_tu_dau_cua_cau_hoi_khong_ghi_cau_tra_loi(may_khach, gui):
    from sqlalchemy import select

    from app.db import session_scope
    from app.models import AuditLog
    _hoi(may_khach, "@Bot IBB7 online hôm qua bao nhiêu " + "x" * 500)
    gui.tra["chu"] = "BI-MAT-TRONG-CAU-TRA-LOI online"
    _hoi(may_khach, "dự báo cuối tháng")
    with session_scope() as s:
        ds = [r.detail for r in s.execute(select(AuditLog).where(AuditLog.action == "zalo_gia_ai").order_by(AuditLog.id)).scalars()]
    assert len(ds) == 2 and ds[0].startswith("chat g1: IBB7 online hôm qua bao nhiêu x") and len(ds[0]) <= len("chat g1: ") + 200
    assert ds[1] == "chat g1: dự báo cuối tháng" and not any("BI-MAT" in d or "@Bot" in d or "12 online" in d for d in ds)


def test_cung_message_id_chi_hoi_ai_mot_lan(may_khach, gui):
    for _ in range(3):
        _hoi(may_khach, CAU_SO_LIEU[3], ma="trung")
    assert len(gui.ai) == 1 and len(gui) == 1


def test_tin_cua_bot_khong_hoi_ai(may_khach, gui):
    payload = {"event_name": "message.text.received",
               "message": {"message_id": "b1", "text": CAU_SO_LIEU[0], "from": {"id": "bot", "is_bot": True}, "chat": {"id": "g1", "chat_type": "GROUP"}}}
    may_khach.post("/api/zalo-gia/webhook", data=json.dumps(payload), content_type="application/json",
                   headers={"X-Bot-Api-Secret-Token": zg.khoa_webhook()})
    assert not gui.ai and not gui
