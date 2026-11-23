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
            for ham, tham in ((thuyettrinh.cb_tao, (1,)), (thuyettrinh.cb_hoi, (1, 0, "hỏi", {"slides": [{}]}, 0, [])), (thuyettrinh.cb_ve, ({"slides": [{}]}, 0))):
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
    vao = [["Thuyết trình cho tôi", False], ["xin chào", False], ["tiếp", True], ["Slide ba", True], ["slide số 5", True], ["lùi lại", True], ["dừng", True], ["đọc tiếp", True], ["nói lại", True],
           ["vì sao IBB5 hụt nhiều nhất", True], ["tại sao quay lại slide trước đó lại thấp như vậy", True]]
    kq = json.loads(subprocess.run([shutil.which("node"), "-e", ma], input=json.dumps(vao), capture_output=True, text=True, encoding="utf-8", check=True).stdout)
    assert [k["lenh"] for k in kq] == ["tao", "chua_co_bai", "tiep", "slide", "slide", "lui", "dung", "phat", "lai", "hoi", "hoi"]
    assert kq[3]["so"] == 3 and kq[4]["so"] == 5 and kq[9]["chu"] == "vì sao IBB5 hụt nhiều nhất"
