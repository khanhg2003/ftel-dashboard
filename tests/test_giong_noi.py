"""Nhập Báo cáo ngày bằng giọng nói (chốt 08/10/2026): khớp tên, kiểm số, quyền, lưu từng phần, gửi ghi âm."""
from __future__ import annotations

import base64
import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import bao_cao_ngay as bc                                      # noqa: E402
from app import giong_noi as gn                                         # noqa: E402
from app import tro_ly as ai                                            # noqa: E402
from app.auth import ADMIN_USERNAME                                    # noqa: E402
from app.config import DATA_DIR                                          # noqa: E402

pytestmark = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(),
                                reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")
NGAY = date(2026, 9, 10)
PHONG = ["IBB7"]
CH = {"bat": True, "key": "sk-thu", "model_chat": "gpt-5-mini", "model_giong": "gpt-4o-mini-transcribe",
      "giong": "trinh_duyet", "tran_usd": 20.0, "vai_tro": [], "tai_khoan": [], "luot_ngay": 20}

DS = [{"acc_norm": "dng.camtien", "ho_ten": "Võ Thị Cẩm Tiên", "acc": "DNG.CamTien"},
      {"acc_norm": "dng.kimchi", "ho_ten": "Lê Thị Kim Chi", "acc": "DNG.KimChi"},
      {"acc_norm": "dng.mychi", "ho_ten": "Hồ Thị Mỹ Chi", "acc": "DNG.MyChi"},
      {"acc_norm": "dng.khai", "ho_ten": "Phan Ngọc Khái", "acc": "DNG.KhaiPN10"},
      {"acc_norm": "dng.anhtu", "ho_ten": "DNG.AnhTu", "acc": "DNG.AnhTu"}]


def _tk(role: str, scope: list[str], ten: str = "kiemthu.gn"):
    from app.auth import SessionUser
    return SessionUser(SimpleNamespace(id=2, username=ten, ho_ten="Kiểm thử", role=role, ma_nv=None,
                                       session_version=0, scope=json.dumps(scope)))


@pytest.fixture(autouse=True)
def _sach():
    from sqlalchemy import delete
    from app.db import session_scope
    from app.models import AiSuDung, BaoCaoNgay

    def don():
        with session_scope() as s:
            s.execute(delete(BaoCaoNgay).where(BaoCaoNgay.ngay == NGAY))
            s.execute(delete(AiSuDung).where(AiSuDung.username == "kiemthu.gn"))
    don()
    yield
    don()


# ------------------------------------------------------------------ khớp tên
@pytest.mark.parametrize("noi,ket_qua", [
    ("Cẩm Tiên", ["dng.camtien"]), ("cam tien", ["dng.camtien"]), ("Tiên", ["dng.camtien"]),
    ("Tiến", ["dng.camtien"]),                       # nghe sai thanh điệu vẫn khớp
    ("chị Cẩm Tiên", ["dng.camtien"]), ("anh Khải", ["dng.khai"]),
    ("Kim Chi", ["dng.kimchi"]), ("Mỹ Chi", ["dng.mychi"]),
    ("Anh Tú", ["dng.anhtu"]),                       # tên trong danh mục chỉ là acc
    ("Võ Thị Cẩm Tiên", ["dng.camtien"]),
    ("Nam", []), ("", []),
])
def test_khop_ten(noi, ket_qua):
    assert gn.khop_ten(noi, DS) == ket_qua


def test_khop_ten_trung_ten_goi_thi_bao_mo_ho():
    assert sorted(gn.khop_ten("Chi", DS)) == ["dng.kimchi", "dng.mychi"]        # không tự chọn thay người dùng
    assert gn.khop_ten("Chị", DS) != []                                          # "Chị" một mình có thể là tên Chi


# ------------------------------------------------------------------ phân tích
def _roster():
    df = bc.bang(PHONG, NGAY)
    return [r for r in df.itertuples()]


def test_phan_tich_khop_nguoi_va_bo_so_sai(monkeypatch):
    a, b = _roster()[0], _roster()[1]
    monkeypatch.setattr(gn, "kiem_tra", lambda user, code: CH)
    monkeypatch.setattr(gn, "_tach", lambda *x: [
        {"ten": a.ho_ten, "mt": 3, "khtn": None, "thuc_hien": 2, "dk_sang": 2, "dk_chieu": 1, "da_online": None,
         "ghi_chu": None},
        {"ten": b.ho_ten, "mt": -1, "khtn": 99999, "thuc_hien": True, "dk_sang": 4, "dk_chieu": None,
         "da_online": 0, "ghi_chu": "chờ thi công"},
        {"ten": a.ho_ten, "mt": None, "khtn": 5, "thuc_hien": None, "dk_sang": None, "dk_chieu": None,
         "da_online": None, "ghi_chu": None},                       # nhắc lại cùng người -> gộp
        {"ten": "Người lạ hoắc", "mt": 1, "khtn": None, "thuc_hien": None, "dk_sang": None, "dk_chieu": None,
         "da_online": None, "ghi_chu": None},
        {"ten": "Trống", "mt": None, "khtn": None, "thuc_hien": None, "dk_sang": None, "dk_chieu": None,
         "da_online": None, "ghi_chu": None},                       # không có gì để điền -> bỏ
    ])
    kq = gn.phan_tich("câu nói thử", PHONG, NGAY, _tk("admin", [], ADMIN_USERNAME))
    n = {m["ten_noi"]: m for m in kq["nguoi"]}
    assert len(kq["nguoi"]) == 3 and "Trống" not in n
    assert n[a.ho_ten]["acc_norm"] == a.acc_norm
    assert n[a.ho_ten]["truong"] == {"muc_tieu": 3, "da_ban": 2, "onl_sang": 2, "onl_chieu": 1, "khtn": 5}
    assert n[b.ho_ten]["truong"] == {"onl_sang": 4, "da_online": 0}      # số âm / quá lớn / True bị bỏ
    assert n[b.ho_ten]["ghi_chu"] == "chờ thi công"
    assert n["Người lạ hoắc"]["acc_norm"] is None and n["Người lạ hoắc"]["mo_ho"] == []
    assert {x["value"] for x in kq["ds"]} >= {a.acc_norm, b.acc_norm}


def test_phan_tich_cau_noi_trong_hoac_qua_dai(monkeypatch):
    monkeypatch.setattr(gn, "kiem_tra", lambda user, code: CH)
    for chu in ("", "   ", "a" * (gn.TOI_DA_CHU + 1)):
        with pytest.raises(ai.LoiAI):
            gn.phan_tich(chu, PHONG, NGAY, _tk("admin", [], ADMIN_USERNAME))


def test_tach_gui_ai_dung_khuon_va_doc_duoc_json(monkeypatch):
    thay = {}

    def gia_hoi(messages, model, key, username, loai, **kw):
        thay.update(messages=messages, loai=loai, kw=kw)
        return {"content": json.dumps({"nguoi": [{"ten": "Tiên", "mt": 3}]})}
    monkeypatch.setattr(ai, "hoi", gia_hoi)
    kq = gn._tach("Tiên mục tiêu 3", ["Võ Thị Cẩm Tiên"], CH, "kiemthu.gn")
    assert kq == [{"ten": "Tiên", "mt": 3}] and thay["loai"] == gn.LOAI
    assert thay["kw"]["dinh_dang"]["json_schema"]["strict"] is True
    assert "Võ Thị Cẩm Tiên" in thay["messages"][1]["content"]             # chỉ gửi tên nhân sự + câu nói
    monkeypatch.setattr(ai, "hoi", lambda *a, **k: {"content": "không phải json"})
    with pytest.raises(ai.LoiAI):
        gn._tach("x", [], CH, "u")


# ------------------------------------------------------------------ lưu
def test_luu_nhieu_chi_ghi_o_co_gia_tri_va_chi_nguoi_trong_phong(monkeypatch):
    monkeypatch.setattr(gn, "kiem_tra", lambda user, code: CH)
    a, b = _roster()[0], _roster()[1]
    bc.luu(a.acc_norm, {"khtn": 7, "ghi_chu": "ghi chú cũ"}, PHONG, "kiemthu.gn", NGAY)
    goc = [{"acc_norm": a.acc_norm, "truong": {"muc_tieu": 3, "da_ban": 2}, "ghi_chu": ""}]
    kq = gn.luu_nhieu(
        [{"acc_norm": a.acc_norm, "truong": {"muc_tieu": 4, "da_ban": 2, "onl_sang": None}, "ghi_chu": ""},
         {"acc_norm": "nguoi.khong.co", "truong": {"muc_tieu": 9}, "ten_noi": "Ai đó"},
         {"acc_norm": b.acc_norm, "truong": {}, "ghi_chu": ""},
         {"acc_norm": b.acc_norm, "truong": {"onl_chieu": 2000}, "ghi_chu": ""}],      # vượt trần -> báo lỗi
        PHONG, NGAY, _tk("admin", [], ADMIN_USERNAME), goc=goc)
    r = bc.bang(PHONG, NGAY).set_index("acc_norm").loc[a.acc_norm]
    assert (int(r.muc_tieu), int(r.da_ban)) == (4, 2)
    assert int(r.khtn) == 7 and r.ghi_chu == "ghi chú cũ"                     # ô không nhắc tới giữ nguyên
    assert kq["da"] == [a.acc_norm] and len(kq["loi"]) == 2
    assert "Chưa chọn người" in kq["loi"][0]


def test_dem_sua():
    goc = [{"acc_norm": "a", "truong": {"muc_tieu": 3, "da_ban": 2}, "ghi_chu": ""}]
    assert gn.dem_sua(goc, [{"acc_norm": "a", "truong": {"muc_tieu": 3, "da_ban": 2}, "ghi_chu": ""}]) == 0
    assert gn.dem_sua(goc, [{"acc_norm": "a", "truong": {"muc_tieu": 4, "da_ban": 2}, "ghi_chu": ""}]) == 1
    assert gn.dem_sua(goc, [{"acc_norm": "b", "truong": {"muc_tieu": 3, "da_ban": 2}, "ghi_chu": ""}]) == 2


# ------------------------------------------------------------------ quyền
def test_quyen_chi_phong_bat_va_dung_tai_khoan(monkeypatch):
    monkeypatch.setattr(ai, "kiem_tra", lambda user: CH)
    assert gn.phong_duoc_dung(_tk("nvkd", ["IBB7"])) == ["IBB7"]
    assert gn.phong_duoc_dung(_tk("admin", [], ADMIN_USERNAME)) != []                       # tài khoản hệ thống dùng thử được
    assert gn.phong_duoc_dung(_tk("admin", [], "bgd.thu")) == []                             # BGĐ không vào Báo cáo ngày
    for tk in (_tk("nvkd", ["IBB2"]), _tk("phong", ["IBB7", "IBB2"]), _tk("nhanvien", ["IBB7"])):
        assert gn.phong_duoc_dung(tk) == [], tk.role
        with pytest.raises(ai.LoiAI):
            gn.kiem_tra(tk, "IBB7")
    assert gn.kiem_tra(_tk("nvkd", ["IBB7"]), "IBB7") is CH
    with pytest.raises(ai.LoiAI):                                              # phòng không được bật
        gn.kiem_tra(_tk("nvkd", ["IBB7"]), "IBB2")


def test_het_luot_ngay_thi_chan_nhung_admin_khong_bi_gioi_han(monkeypatch):
    monkeypatch.setattr(ai, "kiem_tra", lambda user: CH)
    monkeypatch.setattr(ai, "luot_hom_nay", lambda u, loai=(): gn.TOI_DA_NGAY)
    with pytest.raises(ai.LoiAI, match="hết"):
        gn.kiem_tra(_tk("nvkd", ["IBB7"]), "IBB7")
    assert gn.kiem_tra(_tk("admin", [], ADMIN_USERNAME), "IBB7") is CH


def test_ai_tat_thi_bao_ro(monkeypatch):
    monkeypatch.setattr(ai, "cau_hinh", lambda: {**CH, "bat": False})
    with pytest.raises(ai.LoiAI, match="tắt"):
        gn.kiem_tra(_tk("nvkd", ["IBB7"]), "IBB7")


# ------------------------------------------------------------------ ghi âm gửi OpenAI (đường dự phòng)
def test_phien_am_gui_dung_tep_va_ghi_chi_phi(monkeypatch):
    thay = {}

    def gia_api(duong_dan, key, body=None, han=0, tep=None):
        thay.update(duong_dan=duong_dan, key=key, tep=tep)
        return {"text": " Cẩm Tiên mục tiêu 3 ", "usage": {"input_tokens": 100, "output_tokens": 20}}
    ghi = []
    monkeypatch.setattr(ai, "_goi_api", gia_api)
    monkeypatch.setattr(ai, "_ghi_su_dung", lambda *a: ghi.append(a) or 0)
    chu = ai.phien_am(b"AUDIO-GIA", "audio/mp4", CH, "kiemthu.gn", "Nhân sự: Cẩm Tiên")
    assert chu == "Cẩm Tiên mục tiêu 3" and thay["duong_dan"] == "audio/transcriptions"
    data, kieu = thay["tep"]
    ranh = kieu.split("boundary=")[1].encode()
    assert ranh in data and b"AUDIO-GIA" in data and b'name="language"\r\n\r\nvi' in data
    assert b"gpt-4o-mini-transcribe" in data and b"filename=\"giong.mp4\"" in data and "Cẩm Tiên".encode() in data
    assert ghi[0][1] == "giong_noi_am" and ghi[0][3:5] == (100, 20)


def test_van_ban_tu_am_chan_file_trong_va_qua_lon(monkeypatch):
    monkeypatch.setattr(gn, "kiem_tra", lambda user, code: CH)
    monkeypatch.setattr(ai, "phien_am", lambda tho, kieu, ch, u, goi_y: f"{len(tho)}|{kieu}")
    tk = _tk("admin", [], ADMIN_USERNAME)
    ok = base64.b64encode(b"xyz").decode()
    assert gn.van_ban_tu_am("data:audio/webm;base64," + ok, "audio/webm", PHONG, NGAY, tk) == "3|audio/webm"
    for xau in ("", base64.b64encode(b"x" * (gn.TOI_DA_AM + 1)).decode()):
        with pytest.raises(ai.LoiAI):
            gn.van_ban_tu_am(xau, "audio/webm", PHONG, NGAY, tk)


def test_hoi_gui_response_format(monkeypatch):
    thay = {}

    def gia_api(duong_dan, key, body=None, han=0, tep=None):
        thay.update(body)
        return {"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}], "usage": {}}
    monkeypatch.setattr(ai, "_goi_api", gia_api)
    monkeypatch.setattr(ai, "_ghi_su_dung", lambda *a: 0)
    ai.hoi([{"role": "user", "content": "x"}], "gpt-5-mini", "k", "u", "giong_noi", dinh_dang={"type": "json_object"})
    assert thay["response_format"] == {"type": "json_object"}


# ------------------------------------------------------------------ giao diện + nối callback
ASSETS = Path(__file__).resolve().parent.parent / "assets"


def _callback_co_input(ma: str):
    from app.ui.app import app
    for v in app.callback_map.values():
        if "callback" in v and any(i["id"] == ma for i in v["inputs"]):
            return getattr(v["callback"], "__wrapped__", v["callback"])
    raise AssertionError(f"không có callback nhận {ma}")


def _chu(node) -> str:
    return json.dumps(node, default=lambda o: o.to_plotly_json() if hasattr(o, "to_plotly_json") else str(o),
                      ensure_ascii=False)


def _kich_hoat(ma: str, prop: str = "n_clicks"):
    """Giả lập Dash đang chạy một callback do `ma` kích hoạt (để dùng được `ctx.triggered_id`)."""
    from dash._callback_context import context_value
    from dash._utils import AttributeDict
    return context_value.set(AttributeDict(triggered_inputs=[{"prop_id": f"{ma}.{prop}", "value": 1}],
                                           inputs_list=[], states_list=[], outputs_list=[]))


def test_ma_id_trong_js_khop_voi_giao_dien():
    from app.ui.pages import baocaongay_giong as ui
    chu = _chu(ui.khung())
    js = (ASSETS / "ghi_am.js").read_text(encoding="utf-8")
    for ma in ("bn-gn-kq", "bn-gn-mic", "bn-gn", "bn-gn-go", "bn-gn-chu", "bn-gn-the"):
        assert f'"{ma}"' in chu, ma
    for ma in ("bn-gn-kq", "#bn-gn-mic", "'bn-gn'", "'bn-gn-tt'"):
        assert ma in js, ma
    assert "vi-VN" in js and "trinh_duyet" in js and "openai" in js and "TOI_DA_GIAY = 60" in js
    assert all(k in js for k in ("audio/webm", "audio/mp4"))               # iPhone ghi mp4, Android ghi webm
    assert '"data-engine"' not in chu or "trinh_duyet" in chu               # engine mặc định = miễn phí
    assert "bn-gn-tt" not in chu                                            # dòng báo do JS tự dựng, tránh React ghi đè


def test_khung_chi_hien_voi_dung_nguoi_dung_phong(monkeypatch):
    from flask_login import login_user
    from app.ui.app import server
    from app.ui.pages import baocaongay as bn
    with server.test_request_context("/"):
        login_user(_tk("nvkd", ["IBB7"]))
        assert "bn-gn-mic" in _chu(bn.layout())
        monkeypatch.setattr(bc, "cau_hinh", lambda: {"phong": ["IBB7"], "giong_noi": []})   # phòng chưa bật
        assert "bn-gn-mic" not in _chu(bn.layout())


def test_nghe_va_luu_qua_callback(monkeypatch):
    from flask_login import login_user
    from app.ui.app import server
    from app.ui.pages import baocaongay_giong as ui
    a = _roster()[0]
    monkeypatch.setattr(gn, "kiem_tra", lambda user, code: CH)
    monkeypatch.setattr(gn, "_tach", lambda *x: [{"ten": a.ho_ten, "mt": 3, "khtn": None, "thuc_hien": 2,
                                                  "dk_sang": 2, "dk_chieu": 1, "da_online": None, "ghi_chu": None}])
    nghe, luu = _callback_co_input("bn-gn-kq"), _callback_co_input("bn-gn-ok")
    with server.test_request_context("/"):
        login_user(_tk("nvkd", ["IBB7"]))
        _kich_hoat("bn-gn-kq", "data")
        lop, chu, the, goc, msg = nghe({"loai": "chu", "van_ban": "Tiên mục tiêu 3"}, None, None, None, None,
                                       "", "IBB7", NGAY.isoformat())
        assert lop == "modal mo" and chu == "Tiên mục tiêu 3" and msg == ""
        assert len(the) == 1 and goc[0]["acc_norm"] == a.acc_norm
        assert '"bn-gn-ten"' in _chu(the) and '"bn-gn-o"' in _chu(the)
        ids = [{"type": "bn-gn-o", "i": 0, "f": c} for c in ui.gn.NHAN]
        kq = luu(1, goc, [a.acc_norm], [{"type": "bn-gn-ten", "i": 0}], [3, None, 2, 2, 1, None], ids,
                 [""], [{"type": "bn-gn-gc", "i": 0}], "IBB7", NGAY.isoformat(), None)
        assert kq[0] == "modal" and "Đã lưu 1 người" in _chu(kq[2])
        r = bc.bang(PHONG, NGAY).set_index("acc_norm").loc[a.acc_norm]
        assert (int(r.muc_tieu), int(r.da_ban), int(r.onl_sang), int(r.onl_chieu)) == (3, 2, 2, 1)


def test_nghe_bao_loi_ro_khi_ai_tat_hoac_khong_co_quyen(monkeypatch):
    from flask_login import login_user
    from app.ui.app import server
    nghe = _callback_co_input("bn-gn-kq")
    with server.test_request_context("/"):
        login_user(_tk("nvkd", ["IBB7"]))
        _kich_hoat("bn-gn-kq", "data")
        lop, _chu_, the, goc, msg = nghe({"loai": "chu", "van_ban": "x"}, None, None, None, None, "", "IBB7",
                                         NGAY.isoformat())
        assert lop == "modal mo" and the == [] and "Trợ lý AI" in _chu(msg)    # AI chưa bật -> nói rõ, không văng lỗi
        from dash.exceptions import PreventUpdate
        with pytest.raises(PreventUpdate):                                       # phòng khác: bị chặn ở máy chủ
            nghe({"loai": "chu", "van_ban": "x"}, None, None, None, None, "", "IBB2", NGAY.isoformat())


def test_cau_hinh_cach_nhan_dang_luu_va_doc_lai():
    cu = ai.cau_hinh()["giong"]
    try:
        ai.luu_cau_hinh({"giong": "openai"}, "kiemthu.gn")
        assert ai.cau_hinh()["giong"] == "openai"
    finally:
        ai.luu_cau_hinh({"giong": cu}, "kiemthu.gn")
    assert ai.cau_hinh()["giong"] == cu and ai.MAC_DINH["giong"] == "trinh_duyet"
