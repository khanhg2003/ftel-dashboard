"""Kiểm thử trợ lý AI và dự báo cuối tháng. Không gọi OpenAI thật: thay `_goi_api` bằng hàm giả."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import tro_ly as ai                                             # noqa: E402
from app import tro_ly_du_lieu as dl                                     # noqa: E402
from app.config import DATA_DIR                                          # noqa: E402

pytestmark = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(),
                                reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")


def _nguoi(role="admin", ten="kiemthu.ai", phong=None):
    return SimpleNamespace(username=ten, ho_ten=ten, role=role, duoc_xem_nhan_su=role in ("admin", "phong"),
                           phong_duoc_xem=lambda: None,
                           phong_nhan_su=lambda: None if role == "admin" else (phong or []))


@pytest.fixture
def ai_bat(monkeypatch):
    """Bật AI với mã giả; dọn cấu hình + lượt dùng của tài khoản kiểm thử sau khi chạy."""
    from sqlalchemy import delete

    from app.db import session_scope
    from app.models import AiNhanXet, AiSuDung, CaiDat
    ai.luu_cau_hinh({"bat": True, "key": "sk-test-1234567890", "tran_usd": 20.0, "luot_ngay": 2}, "pytest")
    goi = []

    def gia(duong_dan, key, body=None, han=50):
        goi.append(body)
        tin = body["messages"]
        if body.get("tools") and not any(m["role"] == "tool" for m in tin):
            return {"model": body["model"], "usage": {"prompt_tokens": 1000, "completion_tokens": 50},
                    "choices": [{"message": {"content": None, "tool_calls": [{
                        "id": "c1", "type": "function", "function": {
                            "name": "du_bao_cuoi_thang", "arguments": json.dumps({"den": "2026-09-11"})}}]}}]}
        return {"model": body["model"], "usage": {"prompt_tokens": 2000, "completion_tokens": 300},
                "choices": [{"message": {"content": "- IBB7 dẫn đầu\n**Việc nên làm**: đôn tồn"}}]}
    monkeypatch.setattr(ai, "_goi_api", gia)
    yield goi
    with session_scope() as s:
        s.execute(delete(AiSuDung).where(AiSuDung.username.like("kiemthu%")))
        s.execute(delete(AiNhanXet))
        s.execute(delete(CaiDat).where(CaiDat.khoa.like("ai.%")))


def test_ma_hoa_key_giai_ma_duoc_va_khong_lo_ma():
    ma = ai.ma_hoa("sk-bi-mat-123456")
    assert "sk-bi-mat" not in ma and ai.giai_ma(ma) == "sk-bi-mat-123456"
    hong = ma[:-4] + ("AAAA" if not ma.endswith("AAAA") else "BBBB")
    assert ai.giai_ma(hong) is None
    assert ai.key_an("sk-proj-abcdefgh1234") == "sk-…1234"


def test_du_bao_dung_cong_thuc_va_cong_du():
    from app.du_bao import du_bao_thang
    db = du_bao_thang("2026-09", 11)
    he_so, phong = db.attrs["he_so"], db[db.phong_code != "TOTAL"]
    tong = db[db.phong_code == "TOTAL"].iloc[0]
    assert 0.7 <= he_so <= 1.5
    assert tong.luy_ke == phong.luy_ke.sum() == 1394
    r = db[db.phong_code == "IBB7"].iloc[0]
    assert r.du_bao == round(r.luy_ke + r.luy_ke / 11 * 19 * he_so)
    assert r.pct_mt == round(r.du_bao / r.mt * 100)


def test_nhan_xet_luu_lai_khong_goi_ai_lan_hai(ai_bat):
    u = _nguoi()
    khoa, du_lieu = dl.ngu_canh_tong(u, None, "2026-09-11", "all")
    assert ai.nhan_xet_da_luu("tong", khoa) is None
    ban = ai.tao_nhan_xet(u, "tong", khoa, du_lieu(), dl.YEU_CAU_TONG)
    assert "IBB7" in ban["noi_dung"] and len(ai_bat) == 1
    assert ai.nhan_xet_da_luu("tong", khoa)["noi_dung"] == ban["noi_dung"]      # người sau xem lại, không gọi AI
    assert len(ai_bat) == 1
    # số liệu gửi đi không có tên khách hàng, có dự báo
    noi_dung = ai_bat[0]["messages"][1]["content"]
    assert "DỰ BÁO CUỐI THÁNG" in noi_dung and "ten_khach_hang" not in noi_dung


def test_chat_goi_cong_cu_roi_tra_loi(ai_bat):
    u = _nguoi()
    tra_loi = ai.chat(u, [], "Phòng nào rủi ro?", dl.ngu_canh_chat(u, "/", {}), dl.cong_cu(u),
                      lambda ten, ts: dl.chay_cong_cu(u, ten, ts))
    assert "IBB7" in tra_loi and len(ai_bat) == 2
    ket_qua_cong_cu = [m for m in ai_bat[1]["messages"] if m["role"] == "tool"][0]["content"]
    assert "Dự báo cuối tháng" in ket_qua_cong_cu


def test_chat_cau_hoi_trung_dung_ban_da_luu_khong_goi_ai(ai_bat):
    u = _nguoi()
    hoi = lambda cau: ai.chat(u, [], cau, dl.ngu_canh_chat(u, "/", {}), dl.cong_cu(u),   # noqa: E731
                              lambda ten, ts: dl.chay_cong_cu(u, ten, ts), khoa_luu="/|admin")
    dau = hoi("Phòng nào rủi ro?")
    assert len(ai_bat) == 2
    assert hoi("  phòng nào RỦI RO? ") == dau and len(ai_bat) == 2          # không gọi thêm
    hoi("Phòng nào rủi ro?")
    assert len(ai_bat) == 2


def test_cung_cau_dang_tra_loi_thi_khong_goi_ai_them(ai_bat, monkeypatch):
    u = _nguoi()
    ngu_canh, cc = dl.ngu_canh_chat(u, "/", {}), dl.cong_cu(u)
    ket_qua = []

    def chay(ten, ts):          # trong lúc câu đầu còn đang lấy số, người dùng bấm gửi lại đúng câu đó
        with pytest.raises(ai.LoiAI, match="đang được trả lời"):
            ai.chat(u, [], "Phòng nào rủi ro?", ngu_canh, cc, chay)
        ket_qua.append("chan")
        return dl.chay_cong_cu(u, ten, ts)
    ai.chat(u, [], "Phòng nào rủi ro?", ngu_canh, cc, chay)
    assert ket_qua == ["chan"] and len(ai_bat) == 2                          # chỉ 2 lượt của câu đầu
    ai.chat(u, [], "Phòng nào rủi ro?", ngu_canh, cc, lambda t, s: dl.chay_cong_cu(u, t, s))   # xong thì hỏi lại được
    assert len(ai_bat) == 4


def test_phong_chon_o_bao_cao_phong_khong_dinh_sang_trang_khac():
    u, ky = _nguoi(), {"tu": "2026-09-01", "den": "2026-09-16", "cn": "all", "phong": "IBB7"}
    assert "IBB7" not in dl.ngu_canh_chat(u, "/", ky)[1]
    assert "phòng đang chọn IBB7" in dl.ngu_canh_chat(u, "/phong", ky)[1]
    assert dl.bo_loc_trang("/", ky) == {"tu": "2026-09-01", "den": "2026-09-16", "cn": "all"}
    assert "MỌI phòng/bầy" in dl.ngu_canh_chat(u, "/phong", ky)[0]


def test_chat_tra_loi_ngan_nhan_xet_moi_day_du():
    u = _nguoi()
    chat = ai.loi_dan("Fox", chat=True) + dl.ngu_canh_chat(u, "/", {})[0]
    assert "Việc nên làm" not in ai.loi_dan("Fox", chat=True) and "Việc nên làm" in ai.loi_dan("Fox")
    assert "NGẮN, ĐÚNG TRỌNG TÂM" in chat and "| IBB |" in chat and "| DIABAN |" in chat


def test_loi_dan_co_dinh_dung_dau_de_openai_luu_dem(ai_bat):
    a, b = _nguoi(), _nguoi("phong", "kiemthu.tp", ["IBB2"])
    ca, cb = dl.ngu_canh_chat(a, "/", {}), dl.ngu_canh_chat(b, "/phong", {"phong": "IBB2"})
    assert ca[0] == cb[0] and ca[1] != cb[1]                                # phần đầu giống hệt -> dùng lại đệm
    assert ai._ghi_su_dung("kiemthu.gia", "thu", "gpt-5-mini", 10_000, 0, dem=10_000) == \
        pytest.approx(10_000 * 0.25 * 0.1 / 1e6)


def test_bao_cao_tong_hoi_vai_phong_chi_tra_vai_dong():
    u = _nguoi()
    ca = dl.chay_cong_cu(u, "bao_cao_tong", {"den": "2026-09-11"})
    gon = dl.chay_cong_cu(u, "bao_cao_tong", {"den": "2026-09-11", "phong": "IBB7, IBB2"})
    dong = gon.splitlines()
    assert len(dong) < len(ca.splitlines()) and any(x.startswith("IBB7,") for x in dong)
    assert dong[-1].startswith("TỔNG TOÀN CHI NHÁNH")


def test_goi_y_cau_hoi_theo_trang():
    from app.ui.tro_ly import goi_y_cho_trang
    admin, nhap_lieu = _nguoi(), _nguoi("operator")
    assert goi_y_cho_trang("/phong", admin) != goi_y_cho_trang("/", admin) != goi_y_cho_trang("/phantich", admin)
    assert goi_y_cho_trang("/sosanh", admin) == goi_y_cho_trang("/tracking", admin)
    assert goi_y_cho_trang("/hr", nhap_lieu) == goi_y_cho_trang("/", nhap_lieu)


def test_gioi_han_luot_moi_ngay_va_admin_khong_gioi_han(ai_bat):
    tp = _nguoi("phong", "kiemthu.tp", ["IBB2"])
    for _ in range(2):
        ai.tao_nhan_xet(tp, "x", "k", "so", "nhận xét")
    with pytest.raises(ai.LoiAI, match="hết 2 lượt"):
        ai.kiem_tra(tp)
    ai.kiem_tra(_nguoi("admin", "kiemthu.admin"))


def test_cham_tran_chi_phi_thi_dung(ai_bat, monkeypatch):
    monkeypatch.setattr(ai, "chi_phi_thang", lambda: 20.0)
    with pytest.raises(ai.LoiAI, match="ngân sách"):
        ai.kiem_tra(_nguoi())


def test_ai_tat_thi_bao_ro():
    with pytest.raises(ai.LoiAI, match="đang tắt"):
        ai.kiem_tra(_nguoi(), {**ai.MAC_DINH, "key": "sk-x"})


def test_phan_quyen_cong_cu():
    nhap_lieu = _nguoi("operator")
    assert {c["function"]["name"] for c in dl.cong_cu(nhap_lieu)} == {"bao_cao_tong", "so_theo_ngay",
                                                                     "du_bao_cuoi_thang", "chat_luong_ban"}
    with pytest.raises(ai.LoiAI):
        dl.chay_cong_cu(nhap_lieu, "nhan_su_phong", {"phong": "IBB2", "den": "2026-09-11"})
    tp = _nguoi("phong", "kiemthu.tp", ["IBB2"])
    with pytest.raises(ai.LoiAI, match="phòng mình"):
        dl.chay_cong_cu(tp, "nhan_su_phong", {"phong": "IBB7", "den": "2026-09-11"})
    assert "Họ tên" in dl.chay_cong_cu(tp, "nhan_su_phong", {"phong": "IBB2", "den": "2026-09-11"})


def test_anh_bao_cao_tong_kem_nhan_xet_cao_hon():
    import io

    from PIL import Image

    from app.export_png import anh_tong_quan
    goc, _ = anh_tong_quan("2026-09", 11)
    co_nx, _ = anh_tong_quan("2026-09", 11, nhan_xet=("Mây nhận xét", "- **IBB7** vượt 105% mục tiêu\n- Tam Kỳ rủi ro"))
    h = lambda b: Image.open(io.BytesIO(b)).height                          # noqa: E731
    assert h(co_nx) > h(goc)


def test_cac_trang_dung_duoc_voi_the_ai():
    from flask_login import login_user
    from sqlalchemy import select

    from app.auth import SessionUser
    from app.db import session_scope
    from app.models import User
    from app.ui.app import server, serve_layout
    from app.ui.pages import phantich, phong, quantri, tongquan
    with session_scope() as s:
        admin = SessionUser(s.execute(select(User).where(User.role == "admin")).scalars().first())
    with server.test_request_context("/"):
        login_user(admin)
        for trang in (tongquan.layout(), phong.layout(), phantich.layout(), quantri.layout("ai"), serve_layout()):
            assert trang is not None
