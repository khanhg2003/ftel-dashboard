"""Thuyết trình AI khối Kinh doanh (chốt 23/11/2026): slide do code dựng từ số liệu có sẵn, AI chỉ viết lời nói (kiểm số), hỏi đáp theo slide, chỉ Ban Giám đốc dùng."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import DATA_DIR  # noqa: E402

pytestmark = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(), reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")
GOC = Path(__file__).resolve().parent.parent


def _tk(role: str, scope: list[str] | None = None):
    from app.auth import SessionUser
    return SessionUser(SimpleNamespace(id=1, username=f"kiemthu.{role}", ho_ten="Kiểm thử", role=role, ma_nv=None, session_version=0, scope=json.dumps(scope or [])))


@pytest.fixture(scope="module")
def bai():
    from app import thuyet_trinh as tt
    return tt.dung_bai(_tk("admin"))


# ------------------------------------------------------------------ chữ cho giọng đọc
def test_cho_giong_doc_duoc_so_phan_tram_ngay_thang_va_ma_phong():
    from app.thuyet_trinh import cho_giong
    assert cho_giong("Có 1.438 online, bằng 32% mục tiêu 4.530.") == "Có 1438 online, bằng 32 phần trăm mục tiêu 4530."
    assert cho_giong("Tăng +12 so với 12/09, còn 3/30.") == "Tăng tăng 12 so với ngày 12 tháng 9, còn 3 trên 30."
    assert "IBB 7" in cho_giong("IBB7 hụt") and "V VIP" in cho_giong("V.VIP thấp") and "DNG Longph" in cho_giong("DNG.Longph") and "âm 20" in cho_giong("bằng -20 online")
    assert "(" not in cho_giong("Tam Kỳ (hụt 115)") and cho_giong("**Kết luận:** xong").startswith("Kết luận: xong")
    assert cho_giong("tuần 08-14/11 là -23 online") == "tuần từ ngày 8 đến ngày 14 tháng 11 là âm 23 online."
    assert cho_giong("bán mới tăng +27 hợp đồng; kỹ thuật/triển khai xử lý — ngay") == "bán mới tăng 27 hợp đồng; kỹ thuật, triển khai xử lý, ngay."


# ------------------------------------------------------------------ bài do code dựng
def test_bai_co_du_slide_va_moi_slide_co_loi_noi_va_so_lieu(bai):
    ids = [s["id"] for s in bai["slides"]]
    assert ids[0] == "tong_quan" and ids[-1] == "ket_luan"
    assert {"phong", "cung_ky", "nhip", "chat_luong", "ton", "tinh", "nhan_su"} <= set(ids)
    for s in bai["slides"]:
        assert s["tieu_de"] and s["diem"] and len(s["loi_noi"]) > 60 and s["su_that"] and s["nguon_loi"] == "luat"
        assert s["kpi"] or s["hinh"] or s["bang"] or s["id"] in ("nguyen_nhan", "ket_luan")
    assert bai["dung_ai"] is False and bai["ngay"] and bai["slides"][0]["kpi"]


def test_so_tren_slide_khop_ham_co_san_va_loi_mau_qua_kiem_so(bai):
    from app import ban_tin as bt, thuyet_trinh as tt
    from app.tro_ly_dieu_hanh_nd import kiem_so
    sl = bt._so_lieu_bgd(bai["ngay"])
    s = bai["slides"][0]
    assert s["su_that"]["luy_ke"] == int(sl["du_bao"]["luy_ke"]) and s["su_that"]["muc_tieu"] == int(sl["du_bao"]["mt"]) and s["su_that"]["du_bao"] == int(sl["du_bao"]["du_bao"])
    for sl_ in bai["slides"]:
        if sl_["id"] != "nguyen_nhan":                                    # slide chẩn đoán lấy nguyên văn công cụ nên số nằm trong văn bản, đã được kiểm ở test riêng
            assert kiem_so(sl_["loi_noi"], tt.bang_kiem_so(sl_["su_that"])), (sl_["id"], sl_["loi_noi"])


def test_khong_dau_noi_khong_ten_khach_va_hinh_la_figure(bai):
    chu = json.dumps(bai, ensure_ascii=False, default=str).lower()
    assert "đấu nối" not in chu and "ten_kh" not in chu
    for s in bai["slides"]:
        if s["hinh"]:
            assert s["hinh"]["data"] and "layout" in s["hinh"]


# ------------------------------------------------------------------ AI viết lời nói (kiểm số)
def _bai_nho() -> dict:
    return {"ngay": "2026-09-11", "ngay_hien": "11/09/2026", "tam_tinh": False, "dung_ai": False, "ly_do_luat": "", "slides": [
        {"id": "a", "tieu_de": "A", "kpi": [], "hinh": None, "bang": None, "diem": ["x"], "su_that": {"luy_ke": 1394, "ngay": 11}, "loi_noi": "Lời mẫu A có 1394 online.", "nguon_loi": "luat"},
        {"id": "b", "tieu_de": "B", "kpi": [], "hinh": None, "bang": None, "diem": ["y"], "su_that": {"ton": 279}, "loi_noi": "Lời mẫu B có 279 hợp đồng tồn.", "nguon_loi": "luat"}]}


def _chay_ai(monkeypatch, tra_ve: dict | str | Exception, ch_ok: bool = True) -> dict:
    from app import thuyet_trinh_ai as ai, tro_ly
    if ch_ok:
        monkeypatch.setattr(tro_ly, "kiem_tra", lambda u: {"model_chat": "m", "key": "k"})
    else:
        monkeypatch.setattr(tro_ly, "kiem_tra", lambda u: (_ for _ in ()).throw(tro_ly.LoiAI("Trợ lý AI đang tắt.")))

    def hoi(*a, **k):
        if isinstance(tra_ve, Exception):
            raise tra_ve
        return {"content": tra_ve if isinstance(tra_ve, str) else json.dumps(tra_ve, ensure_ascii=False)}
    monkeypatch.setattr(tro_ly, "hoi", hoi)
    return ai.viet_loi(_tk("admin"), _bai_nho())


def test_viet_loi_chi_nhan_loi_dung_so_con_lai_giu_loi_mau(monkeypatch):
    b = _chay_ai(monkeypatch, {"loi_noi": {"a": "Tính đến ngày 11, toàn chi nhánh có 1394 online, đây là con số cần theo dõi sát.",
                                           "b": "Có tới 999 hợp đồng tồn, rất nhiều so với mọi khi và cần xử lý ngay trong tuần này."}})
    a, bb = b["slides"]
    assert a["nguon_loi"] == "ai" and "1394" in a["loi_noi"]
    assert bb["nguon_loi"] == "luat" and bb["loi_noi"] == "Lời mẫu B có 279 hợp đồng tồn.", "số 999 không có trong bảng số liệu nên bị loại"
    assert b["dung_ai"] is True and "lời mẫu" in b["ly_do_luat"]


def test_viet_loi_loi_cam_json_hong_ai_tat_thi_dung_loi_mau(monkeypatch):
    from app import tro_ly
    b = _chay_ai(monkeypatch, {"loi_noi": {"a": "Toàn chi nhánh đấu nối được 1394 online trong tháng này nhé các anh chị.", "b": "Ton 279 hợp đồng, cần xử lý dứt điểm trong tuần này để kịp kế hoạch tháng."}})
    assert [s["nguon_loi"] for s in b["slides"]] == ["luat", "ai"], "chữ cấm 'đấu nối' bị loại"
    assert all(s["nguon_loi"] == "luat" for s in _chay_ai(monkeypatch, "không phải json")["slides"])
    assert all(s["nguon_loi"] == "luat" for s in _chay_ai(monkeypatch, tro_ly.LoiAI("hết giờ"))["slides"])
    tat = _chay_ai(monkeypatch, {}, ch_ok=False)
    assert tat["dung_ai"] is False and "đang tắt" in tat["ly_do_luat"] and all(s["nguon_loi"] == "luat" for s in tat["slides"])


# ------------------------------------------------------------------ hỏi đáp
def test_hoi_gui_ngu_canh_slide_va_lam_sach_markdown(monkeypatch):
    from app import thuyet_trinh_ai as ai, tro_ly
    thu = {}

    def chat(user, lich_su, cau, ngu_canh, cong_cu, chay):
        thu.update(cau=cau, ngu_canh=ngu_canh, cong_cu={c["function"]["name"] for c in cong_cu}, lich_su=lich_su)
        return "**Kết luận:** phòng này hụt.\n\n- Do hai người giảm.\n- Cần kèm cặp."
    monkeypatch.setattr(tro_ly, "chat", chat)
    kq = ai.hoi(_tk("admin"), _bai_nho(), 1, "  vì sao con số này thấp?  ", [{"role": "user", "content": "câu trước"}])
    assert thu["cau"] == "vì sao con số này thấp?" and "SLIDE 2/2: B" in thu["ngu_canh"][1] and '"ton": 279' in thu["ngu_canh"][1] and "ĐANG THUYẾT TRÌNH BẰNG GIỌNG NÓI" in thu["ngu_canh"][1]
    assert "phan_tich_nguyen_nhan" in thu["cong_cu"] and thu["lich_su"][0]["content"] == "câu trước"
    assert "**" not in kq and "\n" not in kq and "- " not in kq and kq.startswith("Kết luận:")
    monkeypatch.setattr(tro_ly, "chat", lambda *a, **k: "Phòng này hụt vì hai người giảm. Fox")
    assert ai.hoi(_tk("admin"), _bai_nho(), 0, "câu hỏi", []) == "Phòng này hụt vì hai người giảm."


def test_cau_hoi_vi_sao_duoc_tra_san_nguyen_nhan_dung_phong(monkeypatch):
    from app import fox_nguyen_nhan, thuyet_trinh_ai as ai, tro_ly
    goi, thu = [], {}
    monkeypatch.setattr(fox_nguyen_nhan, "nguyen_nhan", lambda user, den, code: goi.append((den, code)) or "CHẨN ĐOÁN GIẢ: người A giảm 5")
    monkeypatch.setattr(tro_ly, "chat", lambda user, ls, cau, nc, cc, chay: thu.update(nc=nc) or "ok")
    b = _bai_nho()
    b["slides"][1]["phong_chinh"] = {"ma": "IBB2", "ten": "IBB2"}
    ai.hoi(_tk("admin"), b, 1, "Vì sao phòng hụt nhiều nhất lại thấp như vậy?", [])
    assert goi == [("2026-09-11", "IBB2")] and "CHẨN ĐOÁN GIẢ" in thu["nc"][1] and "ĐÃ TRA SẴN cho phòng IBB2" in thu["nc"][1], "phòng lấy từ slide"
    goi.clear()
    ai.hoi(_tk("admin"), b, 1, "tại sao IBB6 giảm", [])
    assert goi == [("2026-09-11", "IBB6")], "phòng nêu trong câu hỏi được ưu tiên hơn phòng của slide"
    goi.clear()
    ai.hoi(_tk("admin"), b, 1, "con số này nghĩa là gì", [])
    assert goi == [], "câu không hỏi nguyên nhân thì không tra thêm"
    assert ai._phong_trong_cau("vì sao B5 thấp") == "IBB5" and ai._phong_trong_cau("xin chào") is None


# ------------------------------------------------------------------ quyền và menu
def test_chi_ban_giam_doc_goi_duoc_callback_va_thay_menu():
    from dash.exceptions import PreventUpdate
    from flask_login import login_user
    from app.ui import app as ung_dung
    from app.ui.app import server
    from app.ui.pages import thuyettrinh
    for role in ("phong", "operator", "nvkd", "online", "dvkh"):
        with server.test_request_context("/"):
            login_user(_tk(role, ["IBB7"]))
            for ham, tham in ((thuyettrinh.cb_tao, (1, 0, "")), (thuyettrinh.cb_hoi, (1, 0, "hỏi", {"slides": [{}]}, 0, [])), (thuyettrinh.cb_ve, ({"slides": [{}]}, 0))):
                with pytest.raises(PreventUpdate):
                    ham(*tham)
            assert ung_dung.MUC_THUYET_TRINH not in ung_dung._muc_he_thong([], "KD"), role
            ket = repr(ung_dung._router("/thuyettrinh", "", None)[0]).lower()
            assert "chỉ dành cho ban giám đốc" in ket or "không mở được trang này" in ket, role        # vai trò bị chặn ngay ở bộ định tuyến, hoặc ở chính trang
    with server.test_request_context("/"):
        login_user(_tk("admin"))
        assert ung_dung.MUC_THUYET_TRINH in ung_dung._muc_he_thong([], "KD") and ung_dung.MUC_THUYET_TRINH not in ung_dung._muc_he_thong([], "DVKH")
        assert "tt-slide" in repr(ung_dung._router("/thuyettrinh", "", None)[0])


def test_trang_dung_slide_va_bong_hoi_thoai(bai):
    from app.ui.pages import thuyettrinh
    bong = thuyettrinh._bong([{"role": "user", "content": "câu hỏi", "slide": "A"}, {"role": "assistant", "content": "trả lời", "slide": "A"}])
    assert len(bong) == 2 and "chưa có câu hỏi" in repr(thuyettrinh._bong([])).lower()
    for i, s in enumerate(bai["slides"]):
        assert "tt-slide" in repr(thuyettrinh.ve_slide(s, i, len(bai["slides"]), bai))


# ------------------------------------------------------------------ JS: hiểu lệnh bằng giọng nói
@pytest.mark.skipif(shutil.which("node") is None, reason="Không có Node để chạy đoạn JS")
def test_js_phan_tich_lenh_giong_noi():
    ma = ('global.window = {}; global.document = { addEventListener() {}, getElementById() { return null; }, querySelector() { return null; } };'
          f'require({json.dumps(str(GOC / "assets" / "thuyet_trinh.js"))}); const p = window.dash_clientside.tt.phanTich;'
          'const v = JSON.parse(require("fs").readFileSync(0, "utf8")); console.log(JSON.stringify(v.map(x => p(x[0], x[1]))));')
    vao = [["phân tích phòng IBB7", False], ["thuyết trình cho tôi", False], ["báo cáo toàn bộ chi nhánh tới 22/11", True], ["tiếp", True], ["Slide ba", True], ["slide số 5", True], ["lùi lại", True], ["dừng", True], ["đọc tiếp", True], ["nói lại", True],
           ["vì sao IBB5 hụt nhiều nhất", True], ["tại sao quay lại slide trước đó lại thấp như vậy", True]]
    kq = json.loads(subprocess.run([shutil.which("node"), "-e", ma], input=json.dumps(vao), capture_output=True, text=True, encoding="utf-8", check=True).stdout)
    assert [k["lenh"] for k in kq] == ["tao", "tao", "tao", "tiep", "slide", "slide", "lui", "dung", "phat", "lai", "hoi", "hoi"]
    assert kq[0]["chu"] == "phân tích phòng IBB7" and kq[4]["so"] == 3 and kq[5]["so"] == 5 and kq[10]["chu"] == "vì sao IBB5 hụt nhiều nhất"


# ------------------------------------------------------------------ hiểu yêu cầu bằng chữ
PHONGS = [{"code": "IBB7", "ten": "IBB7"}, {"code": "IBB6", "ten": "IBB6"}, {"code": "TAMKY", "ten": "Tam Kỳ"}, {"code": "HOIAN", "ten": "Hội An"}]
NGAYS = [f"2026-11-{d:02d}" for d in range(1, 23)] + ["2026-10-30", "2026-10-31"]


def test_yeu_cau_toan_chi_nhanh_va_khoang_ngay():
    from app import thuyet_trinh_yeu_cau as yc
    ngays = sorted(NGAYS)
    y = yc.phan_tich("báo cáo toàn bộ chi nhánh từ đầu tháng 11 - 22/11", ngays, PHONGS)
    assert y["phong"] is None and y["ngay"] == "2026-11-22" and y["tu"] == "2026-11-01" and "toàn chi nhánh" in y["ghi_chu"] and "01/11/2026 đến 22/11/2026" in y["ghi_chu"]
    assert "chỉ có số luỹ kế" not in y["ghi_chu"], "bắt đầu từ ngày 01 thì không cần nhắc"
    y2 = yc.phan_tich("báo cáo từ ngày 5 tháng 11 đến ngày 20 tháng 11", ngays, PHONGS)
    assert y2["ngay"] == "2026-11-20" and "chỉ có số luỹ kế từ ngày 01" in y2["ghi_chu"]
    assert yc.phan_tich("", ngays, PHONGS)["ngay"] == "2026-11-22" and yc.phan_tich("hôm qua", ngays, PHONGS)["ngay"] == "2026-11-21"
    y3 = yc.phan_tich("tổng kết tháng 10", ngays, PHONGS)
    assert y3["ngay"] == "2026-10-31"
    assert "chưa có số nên dùng ngày 22/11" in yc.phan_tich("tới 25/11", ngays, PHONGS)["ghi_chu"]
    with pytest.raises(ValueError):
        yc.phan_tich("báo cáo tới 15/09", ngays, PHONGS)
    with pytest.raises(ValueError):
        yc.phan_tich("tháng 8", ngays, PHONGS)


def test_yeu_cau_tim_phong_theo_ma_ten_va_cach_noi():
    from app import thuyet_trinh_yeu_cau as yc
    tim = lambda c: yc.tim_phong(c, PHONGS)
    assert tim("phân tích phòng IBB7") == "IBB7" and tim("phân tích phòng ibb 7 nhé") == "IBB7" and tim("báo cáo B6") == "IBB6" and tim("phân tích phòng ibb bảy") == "IBB7"
    assert tim("phòng Tam Kỳ thế nào") == "TAMKY" and tim("phan tich phong hoi an") == "HOIAN" and tim("toàn bộ chi nhánh") is None
    y = yc.phan_tich("phân tích phòng IBB7", sorted(NGAYS), PHONGS)
    assert y["phong"] == "IBB7" and "phòng IBB7" in y["ghi_chu"]


# ------------------------------------------------------------------ bài cho một phòng
def test_bai_mot_phong_co_slide_dung_phong_va_so_khop(bai):
    from app import ban_tin as bt, thuyet_trinh as tt
    from app.tro_ly_dieu_hanh_nd import kiem_so
    b = tt.dung_bai(_tk("admin"), bai["ngay"], "IBB7")
    ids = [s["id"] for s in b["slides"]]
    assert b["phong"] == "IBB7" and ids[0] == "tong_quan_phong" and ids[-1] == "ket_luan" and {"nhip_phong", "nhan_su_phong", "chat_luong_phong", "ton_phong"} <= set(ids)
    sl = bt._so_lieu_bgd(b["ngay"])
    hang = sl["phong"][sl["phong"]["phong_code"] == "IBB7"].iloc[0]
    s0 = b["slides"][0]
    assert s0["su_that"]["luy_ke"] == int(hang["luy_ke"]) and s0["su_that"]["muc_tieu"] == int(hang["mt"]) and "IBB7" in s0["tieu_de"] and s0["phong_chinh"]["ma"] == "IBB7"
    ns = next(s for s in b["slides"] if s["id"] == "nhan_su_phong")
    assert ns["hinh"] and ns["su_that"]["so_nguoi"] > 0
    for s in b["slides"]:
        assert s["diem"] and len(s["loi_noi"]) > 60 and s["nguon_loi"] == "luat", s["id"]
        if s["id"] != "nguyen_nhan":
            assert kiem_so(s["loi_noi"], tt.bang_kiem_so(s["su_that"])), (s["id"], s["loi_noi"])
    with pytest.raises(ValueError):
        tt.dung_bai(_tk("admin"), bai["ngay"], "KHONGCO")


def test_loc_duoc_nem_ten_khong_vo_khi_khong_con_ai_de_nem():
    import pandas as pd
    from app.fox_nguyen_nhan import loc_duoc_nem_ten
    nv = pd.DataFrame({"ck": [5, 3], "chenh": [-5, -3]}, index=["a", "b"])
    phong = pd.Series({"a": "IBB1", "b": "IBB2"})
    assert list(loc_duoc_nem_ten(nv, phong, lambda p: p == "IBB2").index) == ["b"]
    rong = loc_duoc_nem_ten(nv, phong, lambda p: False)
    assert rong.empty and list(rong.columns) == ["ck", "chenh"], "không còn ai thì vẫn giữ nguyên các cột"
    assert loc_duoc_nem_ten(nv.iloc[0:0], phong, lambda p: True).empty


# ------------------------------------------------------------------ giọng đọc Gemini (bộ giọng chọn được)
@pytest.fixture
def giong_gia(monkeypatch):
    from app import thuyet_trinh_giong as g, tro_ly
    g._nho.clear()
    dem = {"goi": [], "chi": []}

    def tao(chu, giong, key):
        dem["goi"].append((chu, giong))
        return g._wav(b"\x00\x01" * 400)
    monkeypatch.setattr(g, "_tao_am", tao)
    monkeypatch.setattr(g, "khoa_gemini", lambda: "AIza-khoa-thu")
    monkeypatch.setattr(tro_ly, "chi_phi_thang", lambda: 0.0)
    monkeypatch.setattr(tro_ly, "_ghi_su_dung", lambda *a, **k: dem["chi"].append(a) or 0.0)
    yield dem
    g._nho.clear()


def test_giong_doc_nho_tam_theo_giong_va_cau_ghi_chi_phi_tung_lan_goi_that(giong_gia):
    from app import thuyet_trinh_giong as g
    u = _tk("admin")
    a = g.doc(u, "Chi nhánh  đang  bằng 32 phần trăm mục tiêu.", "Kore")
    assert a[:4] == b"RIFF" and g.doc(u, "Chi nhánh đang bằng 32 phần trăm mục tiêu.", "Kore") == a        # khoảng trắng thừa không tạo bản mới
    assert len(giong_gia["goi"]) == 1 and len(giong_gia["chi"]) == 1 and giong_gia["chi"][0][3] == len("Chi nhánh đang bằng 32 phần trăm mục tiêu.")
    g.doc(u, "Chi nhánh đang bằng 32 phần trăm mục tiêu.", "Aoede")            # giọng khác là bản khác
    g.doc(u, "Giọng lạ bị đổi về giọng mặc định.", "KhongCoGiongNay")
    assert [x[1] for x in giong_gia["goi"]] == ["Kore", "Aoede", g.MAC_DINH]


def test_giong_doc_tu_choi_chu_rong_qua_dai_chua_co_ma_va_het_ngan_sach(giong_gia, monkeypatch):
    from app import thuyet_trinh_giong as g, tro_ly
    for chu in ("", "   ", None, "a" * (g.TOI_DA_KY_TU + 1)):
        with pytest.raises(tro_ly.LoiAI):
            g.doc(_tk("admin"), chu)
    monkeypatch.setattr(g, "khoa_gemini", lambda: "")
    with pytest.raises(tro_ly.LoiAI, match="Chưa có mã Gemini"):
        g.doc(_tk("admin"), "Xin chào.")
    monkeypatch.setattr(g, "khoa_gemini", lambda: "AIza-khoa-thu")
    monkeypatch.setattr(tro_ly, "chi_phi_thang", lambda: 10 ** 6)
    with pytest.raises(tro_ly.LoiAI, match="ngân sách"):
        g.doc(_tk("admin"), "Xin chào.")
    assert giong_gia["goi"] == []


def test_giong_30_giong_co_mo_ta_va_khong_trung():
    from app import thuyet_trinh_giong as g
    assert len(g.GIONG) == 30 and len(g.TEN_GIONG) == 30 and g.MAC_DINH in g.TEN_GIONG
    assert all(m and nhom in ("nu", "nam") for _, m, nhom in g.GIONG)


def test_gemini_tim_am_va_boc_wav_dung_ca_hai_kieu_tra_loi():
    import base64
    from app import thuyet_trinh_giong as g
    pcm = b"\x01\x02" * 50
    b64 = base64.b64encode(pcm).decode()
    assert g._tim_am({"steps": [{"type": "model_output", "content": [{"type": "text", "text": "x"}, {"type": "audio", "data": b64}]}]}) == b64
    assert g._tim_am({"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "audio/L16;rate=24000", "data": b64}}]}}]}) == b64
    assert g._tim_am({"steps": [{"content": [{"type": "text", "data": "khong phai am thanh"}]}]}) is None
    w = g._wav(pcm)
    assert w[:4] == b"RIFF" and w[8:12] == b"WAVE" and w[-len(pcm):] == pcm and len(w) == 44 + len(pcm)


def test_gemini_goi_that_loi_400_thi_thu_generate_content(monkeypatch):
    import base64
    from app import thuyet_trinh_giong as g, tro_ly
    cac = []

    def http(duong, body, key, han):
        cac.append(duong)
        if duong == "interactions":
            e = tro_ly.LoiAI("sai")
            e.ma = 404
            raise e
        return {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "audio/L16;rate=24000", "data": base64.b64encode(b"\x01\x02" * 20).decode()}}]}}]}
    monkeypatch.setattr(g, "_http", http)
    assert g._tao_am("Xin chào.", "Kore", "k")[:4] == b"RIFF" and cac == ["interactions", f"models/{g.MODEL_DU_PHONG}:generateContent"]
    monkeypatch.setattr(g, "_http", lambda *a: (_ for _ in ()).throw(tro_ly.LoiAI("429")))      # lỗi không phải 400 / 404 thì không thử lại
    with pytest.raises(tro_ly.LoiAI):
        g._tao_am("Xin chào.", "Kore", "k")


def test_duong_giong_doc_chi_ban_giam_doc_va_tra_wav_hoac_loi_tieng_viet(giong_gia, monkeypatch):
    from flask_login import login_user
    from app import api_thuyet_trinh as api, thuyet_trinh_giong as g, tro_ly
    from app.ui.app import server
    for role in ("phong", "operator", "nvkd", "online", "dvkh"):
        with server.test_request_context("/api/thuyet-trinh/doc", method="POST", json={"chu": "Xin chào."}):
            login_user(_tk(role, ["IBB7"]))
            assert api.doc()[1] == 403, role
    with server.test_request_context("/api/thuyet-trinh/doc", method="POST", json={"chu": "Xin chào.", "giong": "Leda"}):
        login_user(_tk("admin"))
        r = api.doc()
        assert r.status_code == 200 and r.mimetype == "audio/wav" and r.data[:4] == b"RIFF" and giong_gia["goi"][-1][1] == "Leda"
    with server.test_request_context("/api/thuyet-trinh/doc", method="POST", json={"chu": "Xin chào hai."}):
        login_user(_tk("admin"))
        monkeypatch.setattr(g, "_tao_am", lambda *a: (_ for _ in ()).throw(tro_ly.LoiAI("Gemini báo quá nhiều yêu cầu.")))
        r, ma = api.doc()
        assert ma == 400 and "quá nhiều" in r.get_json()["loi"]
    with server.test_request_context("/api/thuyet-trinh/doc", method="POST", json={"chu": "Xin chào ba."}):
        login_user(_tk("admin"))
        monkeypatch.setattr(g, "_tao_am", lambda *a: (_ for _ in ()).throw(KeyError("chi tiết kỹ thuật")))
        r, ma = api.doc()
        assert ma == 502 and "KeyError" not in r.get_json()["loi"]


def test_trang_co_bang_chon_giong_khong_con_giong_trinh_duyet_va_luu_ma_chi_bgd(monkeypatch):
    from dash.exceptions import PreventUpdate
    from flask_login import login_user
    from app import thuyet_trinh_giong as g
    from app.ui.app import server
    from app.ui.pages import thuyettrinh
    with server.test_request_context("/"):
        login_user(_tk("admin"))
        ds = repr(thuyettrinh.layout()["tt-giong-ds"])
        assert ds.count("tt-gv-nghe") == 30 and "Sulafat" in ds and "Nghe thử" in ds and "Giọng nữ" in ds and "Giọng nam" in ds
    for role in ("phong", "nvkd", "online"):
        with server.test_request_context("/"):
            login_user(_tk(role, ["IBB7"]))
            with pytest.raises(PreventUpdate):
                thuyettrinh.cb_khoa(1, 0, "AIza" + "x" * 40)
    luu = []
    monkeypatch.setattr(g, "luu_khoa", lambda k, n: luu.append(k))
    monkeypatch.setattr(g, "doc", lambda *a: b"RIFF")
    monkeypatch.setattr(thuyettrinh, "ctx", SimpleNamespace(triggered=[{"value": 1}], triggered_id="tt-gm-luu"))
    with server.test_request_context("/"):
        login_user(_tk("admin"))
        thuyettrinh.cb_khoa(1, 0, "ngắn")
        assert luu == []                                  # mã quá ngắn: không lưu
        thuyettrinh.cb_khoa(1, 0, "AIza" + "x" * 40)
        assert luu == ["AIza" + "x" * 40]
    goc_js = GOC / "assets" / "thuyet_trinh.js"
    js = goc_js.read_text(encoding="utf-8")
    assert "speechSynthesis" not in js and "SpeechSynthesisUtterance" not in js          # đã bỏ hẳn giọng của trình duyệt
    if shutil.which("node"):
        assert subprocess.run(["node", "--check", str(goc_js)], capture_output=True).returncode == 0


# ------------------------------------------------------------------ nút Bắt đầu thuyết trình, đọc theo đoạn
@pytest.mark.skipif(shutil.which("node") is None, reason="Không có Node để chạy đoạn JS")
def test_js_lenh_bat_dau_va_nut_bat_dau_o_trang(bai):
    ma = ('global.window = {}; global.document = { addEventListener() {}, getElementById() { return null; }, querySelector() { return null; } };'
          f'require({json.dumps(str(GOC / "assets" / "thuyet_trinh.js"))}); const p = window.dash_clientside.tt.phanTich;'
          'const v = JSON.parse(require("fs").readFileSync(0, "utf8")); console.log(JSON.stringify(v.map(x => p(x[0], x[1]))));')
    vao = [["bắt đầu thuyết trình", True], ["bắt đầu", True], ["tiếp tục", True], ["thuyết trình lại phòng IBB7 đến 22/11", True]]
    kq = json.loads(subprocess.run([shutil.which("node"), "-e", ma], input=json.dumps(vao), capture_output=True, text=True, encoding="utf-8", check=True).stdout)
    assert [k["lenh"] for k in kq] == ["phat", "phat", "phat", "tao"]
    from flask_login import login_user
    from app.ui.app import server
    from app.ui.pages import thuyettrinh
    with server.test_request_context("/"):
        login_user(_tk("admin"))
        ly = thuyettrinh.layout()
        assert ly["tt-phat"].children == "▶ Bắt đầu thuyết trình" and ly["tt-phat2"] is not None and ly["tt-loi-sau"] is not None
        ket = thuyettrinh.cb_ve(bai, 0)
        assert len(ket) == 6 and ket[3] and ket[4] is True and ket[5] is False                      # có lời của slide kế tiếp để xin sẵn giọng
        assert thuyettrinh.cb_ve(bai, len(bai["slides"]) - 1)[3] == ""


# ------------------------------------------------------------------ tài khoản kỹ thuật không dùng được
def test_tai_khoan_ky_thuat_admin_khong_thay_va_khong_goi_duoc_thuyet_trinh():
    from dash.exceptions import PreventUpdate
    from flask_login import login_user
    from app import api_thuyet_trinh as api
    from app.auth import ADMIN_USERNAME, SessionUser
    from app.ui import app as ung_dung
    from app.ui.app import server
    from app.ui.pages import thuyettrinh
    ky_thuat = SessionUser(SimpleNamespace(id=1, username=ADMIN_USERNAME, ho_ten="Kỹ thuật", role="admin", ma_nv=None, session_version=0, scope="[]"))
    assert ky_thuat.la_superadmin and not ky_thuat.duoc_thuyet_trinh and _tk("admin").duoc_thuyet_trinh
    with server.test_request_context("/api/thuyet-trinh/doc", method="POST", json={"chu": "Xin chào."}):
        login_user(ky_thuat)
        assert api.doc()[1] == 403
        assert ung_dung.MUC_THUYET_TRINH not in ung_dung._muc_he_thong([], "KD")
        assert "chỉ dành cho ban giám đốc" in repr(ung_dung._router("/thuyettrinh", "", None)[0]).lower()
        with pytest.raises(PreventUpdate):
            thuyettrinh.cb_tao(1, 0, "")


def test_viet_loi_slide_bi_loai_duoc_nho_viet_lai_mot_lan_kem_ly_do(monkeypatch):
    from app import thuyet_trinh_ai as ai, tro_ly
    monkeypatch.setattr(tro_ly, "kiem_tra", lambda u: {"model_chat": "m", "key": "k"})
    cac_lan = []

    def hoi(messages, *a, **k):
        nd = json.loads(messages[1]["content"])
        cac_lan.append(nd)
        if "can_viet_lai" not in nd:
            return {"content": json.dumps({"loi_noi": {"a": "Tính đến ngày 11, toàn chi nhánh có 1394 online, đây là con số cần theo dõi sát.",
                                                       "b": "Có tới 999 hợp đồng tồn, rất nhiều so với mọi khi và cần xử lý ngay trong tuần này."}}, ensure_ascii=False)}
        return {"content": json.dumps({"loi_noi": {"b": "Hiện còn 279 hợp đồng tồn, đây là phần dư địa em thấy dễ chuyển thành online nhất trong ngắn hạn."}}, ensure_ascii=False)}
    monkeypatch.setattr(tro_ly, "hoi", hoi)
    b = ai.viet_loi(_tk("admin"), _bai_nho())
    assert [s["nguon_loi"] for s in b["slides"]] == ["ai", "ai"] and b["ly_do_luat"] == "" and len(cac_lan) == 2
    assert [s["id"] for s in cac_lan[1]["slides"]] == ["b"] and "999" in cac_lan[1]["can_viet_lai"]["b"]       # chỉ gửi lại slide bị loại, nói rõ số nào sai
    assert "279" in b["slides"][1]["loi_noi"]
    assert ai._so_sai("Có 48 giờ và 279 hợp đồng.", b["slides"][1]["su_that"]) == ["48"]
