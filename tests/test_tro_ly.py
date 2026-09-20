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


def test_cot_insight_tinh_san_dung():
    import pandas as pd

    from app.overview import bang_tong_quan
    from datetime import date
    df, _ = bang_tong_quan("2026-09", 11)
    df = dl._them_insight(df, date(2026, 9, 11), "2026-09-01")
    phong = df[df.loai_dong == "data"]
    tong = df[df.loai_dong == "total"].iloc[0]
    assert (df.chenh_ck == df.online - df.ck_online).all()
    assert tong.tuan_nay == phong.tuan_nay.sum() and tong.tuan_truoc == phong.tuan_truoc.sum()
    assert tong.chenh_tien_do == round(tong.htkh_internet - round(11 / 30 * 100))
    tang = pd.to_numeric(phong.dong_gop[phong.chenh_ck > 0])
    assert 98 <= tang.sum() <= 102                                           # các phòng tăng cộng lại ~100%
    assert set(phong[phong.ck_online < 30].mau_nho) == {"có"} and "có" not in set(phong[phong.ck_online >= 30].mau_nho)


def test_chan_doan_theo_quyen():
    admin, nhap_lieu = _nguoi(), _nguoi("operator")
    co = dl.chay_cong_cu(admin, "chan_doan_phong", {"den": "2026-09-11", "phong": "IBB5"})
    khong = dl.chay_cong_cu(nhap_lieu, "chan_doan_phong", {"den": "2026-09-11", "phong": "IBB5"})
    assert "giảm nhiều nhất" in co and "Online từng ngày" in khong and "Họ tên" not in khong


def test_chat_tra_loi_ngan_nhan_xet_moi_day_du():
    u = _nguoi()
    chat = ai.loi_dan("Fox", chat=True) + dl.ngu_canh_chat(u, "/", {})[0]
    assert "Việc cần làm" not in ai.loi_dan("Fox", chat=True) and "Việc cần làm" in ai.loi_dan("Fox")
    ld = ai.loi_dan("Fox")
    assert "KHÔNG chép lại bảng" in ld and "170 từ" in ld and "**Nhận định:**" in ld and "kéo giảm" in ld
    assert "NHÂN VẬT" in ai.loi_dan("Fox", chat=True) and "VÍ DỤ VIẾT ĐẠT" not in ai.loi_dan("Fox", chat=True)
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


def test_quyen_dung_ai_theo_vai_tro_hoac_tung_tai_khoan(ai_bat):
    # giai đoạn thử: không mở vai trò nào, chỉ riêng tài khoản kiemthu.admin
    ai.luu_cau_hinh({"vai_tro": [], "tai_khoan": ["kiemthu.admin"]}, "pytest")
    ch = ai.cau_hinh()
    assert ch["vai_tro"] == [] and ch["tai_khoan"] == ["kiemthu.admin"]
    ai.kiem_tra(_nguoi("admin", "kiemthu.admin"))
    for nguoi in (_nguoi("admin", "kiemthu.bgd"), _nguoi("phong", "kiemthu.tp", ["IBB2"])):
        with pytest.raises(ai.LoiAI, match="chưa được mở quyền"):
            ai.kiem_tra(nguoi)
    # câu trả lời đã lưu cũng không trả cho người chưa có quyền
    with pytest.raises(ai.LoiAI, match="chưa được mở quyền"):
        ai.chat(_nguoi("admin", "kiemthu.bgd"), [], "x", ("", ""), [], None, khoa_luu="k")
    # mở rộng: thêm vai trò Trưởng phòng
    ai.luu_cau_hinh({"vai_tro": ["phong"], "tai_khoan": ["kiemthu.admin", "kiemthu.bgd"]}, "pytest")
    ai.kiem_tra(_nguoi("phong", "kiemthu.tp", ["IBB2"]))
    ai.kiem_tra(_nguoi("admin", "kiemthu.bgd"))
    with pytest.raises(ai.LoiAI, match="chưa được mở quyền"):
        ai.kiem_tra(_nguoi("operator", "kiemthu.nl"))


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
                                                                     "du_bao_cuoi_thang", "chat_luong_ban",
                                                                     "chan_doan_phong"}
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


def test_model_suy_luan_het_do_dai_thi_goi_lai_voi_gioi_han_lon_hon(monkeypatch):
    goi = []

    def gia(duong_dan, key, body=None, han=50):
        goi.append(dict(body))
        if body["max_completion_tokens"] < 10000:            # lần đầu: nghĩ hết chỗ, chưa viết chữ nào
            return {"model": "gpt-5", "usage": {"prompt_tokens": 3000, "completion_tokens": body["max_completion_tokens"]},
                    "choices": [{"finish_reason": "length", "message": {"content": ""}}]}
        return {"model": "gpt-5", "usage": {"prompt_tokens": 3000, "completion_tokens": 900},
                "choices": [{"finish_reason": "stop", "message": {"content": "- Nhận xét"}}]}
    monkeypatch.setattr(ai, "_goi_api", gia)
    monkeypatch.setattr(ai, "_ghi_su_dung", lambda *a, **k: 0)
    msg = ai.hoi([{"role": "user", "content": "x"}], "gpt-5", "sk-x", "kiemthu.ai", "nhan_xet")
    assert msg["content"] == "- Nhận xét" and [g["max_completion_tokens"] for g in goi] == [6000, 12000]
    assert goi[0]["reasoning_effort"] == "minimal"


def test_model_khong_nhan_muc_minimal_thi_dung_low(monkeypatch):
    goi = []

    def gia(duong_dan, key, body=None, han=50):
        goi.append(body.get("reasoning_effort"))
        if body.get("reasoning_effort") == "minimal":
            loi = ai.LoiAI("OpenAI báo lỗi 400.")
            loi.ma, loi.chi_tiet = 400, "Unsupported value: 'minimal' for reasoning_effort"
            raise loi
        return {"model": "gpt-5.1", "usage": {}, "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}]}
    monkeypatch.setattr(ai, "_goi_api", gia)
    monkeypatch.setattr(ai, "_ghi_su_dung", lambda *a, **k: 0)
    assert ai.hoi([], "gpt-5.1", "sk-x", "kiemthu.ai", "chat")["content"] == "ok" and goi == ["minimal", "low"]


def test_het_do_dai_ca_hai_lan_thi_bao_ro(monkeypatch):
    monkeypatch.setattr(ai, "_goi_api", lambda *a, **k: {
        "model": "gpt-5", "usage": {}, "choices": [{"finish_reason": "length", "message": {"content": None}}]})
    monkeypatch.setattr(ai, "_ghi_su_dung", lambda *a, **k: 0)
    with pytest.raises(ai.LoiAI, match="giới hạn độ dài"):
        ai.hoi([], "gpt-5", "sk-x", "kiemthu.ai", "nhan_xet")


def test_tin_hieu_chinh_tinh_san_cho_nhan_xet(monkeypatch):
    from datetime import date

    import app.overview as ov
    monkeypatch.setattr(ov, "trang_thai_ngay", lambda d: (False, None))
    t = dl.tin_hieu_tong(date(2026, 9, 11), "2026-09", "all", "2026-09-01", None)
    assert "THIẾU 319 online" in t and "Hụt nhiều nhất so với mục tiêu tháng" in t and "Tam Kỳ hụt" in t
    assert "đóng góp" not in t.lower()          # phần thiếu phải nói là "chiếm", không phải "đóng góp"
    assert "Hợp đồng chờ lâu" in t and "kéo" not in t.lower() and "Năng suất" in t and "7 ngày đã chốt" in t
    assert "TÍN HIỆU CHÍNH" in dl.ngu_canh_tong(_nguoi(), None, "2026-09-11", "all")[1]()


def test_ngay_dang_tam_tinh_khong_tinh_vao_7_ngay_gan(monkeypatch):
    from datetime import date

    import app.overview as ov
    monkeypatch.setattr(ov, "trang_thai_ngay", lambda d: (True, None))
    assert dl.ngay_chot_7(date(2026, 9, 18)) == date(2026, 9, 17)
    monkeypatch.setattr(ov, "trang_thai_ngay", lambda d: (False, None))
    assert dl.ngay_chot_7(date(2026, 9, 18)) == date(2026, 9, 18)


def test_tin_hieu_phong_va_so_thang_truoc(monkeypatch):
    from datetime import date

    import app.overview as ov
    monkeypatch.setattr(ov, "trang_thai_ngay", lambda d: (False, None))
    t = dl.tin_hieu_phong(date(2026, 9, 11), "IBB5")
    assert "IBB5: dự báo" in t and "nhân sự, bình quân" in t and "Mức phụ thuộc" in t and "7 ngày đã chốt" in t
    ss = dl.so_voi_thang_truoc("2026-09", 11, None)
    assert "tới ngày 11/08" in ss and "% số của cả tháng 08" in ss
    assert "TÍN HIỆU CHÍNH" in dl.ngu_canh_phong(_nguoi(), "2026-09-11", "IBB5")[1]()


def test_fox_boi_canh_chung_va_tin_hieu_phan_tich():
    """Bối cảnh tháng dùng chung + tín hiệu chất lượng & vận hành; không có quyền nhân sự thì không nêu tên ai."""
    from datetime import date

    from app import fox_insight as fi

    class U:
        duoc_xem_nhan_su = False

        def phong_nhan_su(self):
            return []

    d = date(2026, 9, 11)
    bc = fi.boi_canh_chung(U(), d, None)
    assert "BỐI CẢNH THÁNG" in bc and "Chất lượng bán" in bc and "Nhân sự:" not in bc
    th = fi.tin_hieu_phan_tich(U(), d, None)
    assert "Tỷ lệ chung" in th and "Sale có số" not in th
    for x in (bc, th):
        assert "kéo" not in x.lower() and "đòn bẩy" not in x.lower()


def test_lam_sach_cau_tra_loi():
    from app.tro_ly import lam_sach
    assert lam_sach("làm 129.8/ngày, chờ >7 ngày, thêm ~39, 4.211 số") == "làm 129,8/ngày, chờ quá 7 ngày, thêm khoảng 39, 4.211 số"
    assert lam_sach("sale kéo giảm tỷ lệ, kéo tụt tiến độ") == "sale làm giảm tỷ lệ, làm tụt tiến độ"
    assert lam_sach("đạt 93% (số này do hệ thống tính, tôi chỉ báo cáo).") == "đạt 93%."


def test_tra_mot_nhan_su_theo_acc_hoac_ten():
    """Hỏi về một người cụ thể phải ra số của người đó, không báo 'không tìm thấy' (lỗi chủ app gặp 19/09)."""
    admin = _nguoi()
    kq = dl.chay_cong_cu(admin, "nhan_su_ca_nhan", {"nguoi": "DNG.ChiPTL4", "den": "2026-09-11"})
    assert "Phạm Thị Lan Chi" in kq and "IBB6" in kq and "Vị trí trong phòng" in kq
    assert dl.chay_cong_cu(admin, "nhan_su_ca_nhan", {"nguoi": "Phạm Thị Lan Chi", "den": "2026-09-11"}) == kq
    with pytest.raises(ai.LoiAI, match="Không có nhân sự"):
        dl.chay_cong_cu(admin, "nhan_su_ca_nhan", {"nguoi": "Nguyễn Không Có Thật", "den": "2026-09-11"})
    # trưởng phòng chỉ tra được người của phòng mình
    tp = _nguoi("phong", "kiemthu.tp", ["IBB2"])
    with pytest.raises(ai.LoiAI):
        dl.chay_cong_cu(tp, "nhan_su_ca_nhan", {"nguoi": "DNG.ChiPTL4", "den": "2026-09-11"})


def test_truyen_acc_vao_o_ma_phong_thi_chi_duong_sang_cong_cu_dung():
    with pytest.raises(ai.LoiAI, match="nhan_su_ca_nhan"):
        dl.chay_cong_cu(_nguoi(), "nhan_su_phong", {"phong": "DNG.ChiPTL4", "den": "2026-09-11"})


def test_khong_dung_tu_dong_gop_cho_phan_thieu():
    """'Đóng góp' chỉ dành cho việc tốt; phần thiếu phải nói là 'chiếm' và không dán phép tính."""
    from app.tro_ly import lam_sach
    assert lam_sach("Tam Kỳ, IBB2 đóng góp 51% phần thiếu (87+64+63 = 214/323) của chi nhánh") == (
        "Tam Kỳ, IBB2 chiếm 51% phần thiếu của chi nhánh")
    assert lam_sach("cần 183/ngày vs đang 129,8/ngày") == "cần 183/ngày so với đang 129,8/ngày"
    assert lam_sach("IBB7 đóng góp 40% phần tăng") == "IBB7 đóng góp 40% phần tăng"


def test_loi_dan_giu_dung_nhan_vat_fox():
    d = ai.loi_dan("Fox")
    assert "bạn là Fox" in d and "anh/chị" in d
    assert "không viết 'đóng góp phần thiếu'" in d
    assert ai.loi_dan("Mây").count("Mây") >= 3          # đổi tên trợ lý thì nhân vật đổi theo


def test_nhip_cuoi_thang_do_bang_so_thang_truoc():
    """Hệ số = tốc độ phần cuối tháng trước / tốc độ phần đầu, để giao diện nói được bằng số thật."""
    from app.du_bao import nhip_cuoi_thang
    n = nhip_cuoi_thang("2026-09", 11)
    assert n["dau"] and n["cuoi"] and abs(n["he_so"] - round(n["cuoi"] / n["dau"], 2)) < 0.01
    assert n["thang_truoc"] == "2026-08" and n["cat"] == 11


def test_du_bao_kich_ban_giu_nhip_7_ngay():
    """Cột thứ hai của dự báo: luỹ kế + bình quân 7 ngày gần nhất ĐÃ CHỐT × số ngày còn lại."""
    from app.du_bao import du_bao_thang, nhip_tuan
    from app.metrics import daily_counts, month_range
    db = du_bao_thang("2026-09", 11)
    t = db.attrs["tuan"]
    assert t["den"] - t["tu"] + 1 == t["so_ngay"] <= 7 and t["den"] <= 11
    bang = daily_counts("2026-09", "online")
    assert round(float(bang.loc[:, t["tu"]:t["den"]].to_numpy().sum() / t["so_ngay"]), 1) == t["tb"]
    r = db[db.phong_code == "TOTAL"].iloc[0]
    con_lai = month_range("2026-09")[2] - 11
    assert abs(r.du_bao_tuan - (r.luy_ke + t["tb"] * con_lai)) <= 2   # tb làm tròn 1 chữ số
    assert r.pct_tuan == round(r.du_bao_tuan / r.mt * 100)
    # lọc phòng thì nhịp tuần chỉ tính phòng đó
    assert nhip_tuan("2026-09", 11, ["IBB2"])["tb"] < t["tb"]


def test_giai_thich_du_bao_noi_bang_loi_thuong():
    import re

    from app.du_bao import du_bao_thang
    from app.ui.tro_ly import giai_thich_du_bao
    db = du_bao_thang("2026-09", 11)
    chu = " ".join(d.children for d in giai_thich_du_bao(
        db[db.phong_code == "TOTAL"].iloc[0].to_dict(), db.attrs.get("nhip"), db.attrs.get("tuan")))
    assert "giữ đúng nhịp tháng trước" in chu and "7 ngày gần nhất" in chu
    assert "hệ số" not in chu.lower()                 # chủ app không hiểu chữ này
    assert "bán" not in chu.lower()                  # dự báo tính trên số ONLINE, không phải số bán
    assert not re.search(r"\d\.\d", chu)          # số thập phân kiểu Việt Nam: 135,7

