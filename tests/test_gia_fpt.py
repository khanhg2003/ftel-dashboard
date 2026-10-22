"""Tra cứu giá gói cước theo khu vực (app/gia_fpt.py + trang /giafpt), chủ app chốt 22/10/2026.

Không gọi mạng: dịch vụ của fpt.vn được thay bằng dữ liệu giả cùng dạng với dữ liệu thật đã đo (giá khác nhau theo phường,
gói Internet có lựa chọn trả trước 3 / 6 / 13 tháng, 13 tháng chỉ đóng 12)."""
from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import gia_fpt as gf  # noqa: E402
from app.bo_nho import xoa  # noqa: E402
from app.config import DATA_DIR  # noqa: E402
from app.thoi_gian import utc_bay_gio  # noqa: E402

TINH, AN_HAI, QUANG_PHU, QUE_SON = 511, 1000009603, 1000009633, 1000009700
GIA_THEO_PHUONG = {AN_HAI: {"1": 205000, "18": 340000, "109": 450000}, QUANG_PHU: {"1": 200000, "18": 330000, "109": 450000},
                    QUE_SON: {"1": 200000, "18": 330000}}              # Quế Sơn không bán Super300 Biz


def _goi(id_, code, ten, loai="internet", gia=0, tagline=""):
    return {"id": id_, "code": code, "slug": code, "name": ten, "type": loai, "type_name": loai, "tagline": tagline,
            "card_description": "Tốc độ Download/Upload 1 Gbps/300 Mbps", "price": {"price": gia, "min_price": None},
            "product_spec_characteristics": [{"name": "Tốc độ download (done)", "value": "1 Gbps"},
                                             {"name": "Tốc độ upload (done)", "value": "300 Mbps"},
                                             {"name": "Thiết bị kết nối", "value": "15"}]}


MAU = {"1": ("sky", "Internet Sky"), "18": ("meta-f1", "Internet Meta F1"), "109": ("super300", "Super300 Biz")}


def _dich_vu(duong, noi_dung, han=15):
    if duong.endswith("provinces/list"):
        return [{"id": 8, "text": "Hồ Chí Minh"}, {"id": TINH, "text": "Đà Nẵng"}]
    if duong.endswith("wards/list"):
        return [{"id": QUE_SON, "text": "Xã Quế Sơn"}, {"id": AN_HAI, "text": "Phường An Hải"}, {"id": QUANG_PHU, "text": "Phường Quảng Phú"}]
    if duong.endswith("packages/list"):
        bang = GIA_THEO_PHUONG[noi_dung["location"]["ward_id"]]
        return [_goi(int(i), MAU[i][0], MAU[i][1], gia=g) for i, g in bang.items()] + [_goi(24, "goi-vvip1", "Gói V.VIP 1", "fpt-play", 130000),
                                                                                                                           _goi(128, "casper", "Casper Smart TV", "smart-tivi", 3378531)]
    if duong.endswith("packages/get"):
        tu, den = utc_bay_gio() - timedelta(days=30), utc_bay_gio() + timedelta(days=30)
        het = utc_bay_gio() - timedelta(days=1)

        def chinh_sach(thang, tong, tinh_trang="active", hieu_luc_den=den):
            return {"name": "CS INT Cá nhân", "status": tinh_trang, "billing_type_name": "Trả trước", "contract_length_months": thang,
                    "sale_platform_code": "INT.1", "effective_from": tu.strftime("%Y-%m-%d %H:%M:%S"),
                    "effective_to": hieu_luc_den.strftime("%Y-%m-%d %H:%M:%S"),
                    "summary": {"service_price": {"price": tong}, "fee_price": {"price": 500000}, "device_price": None}}
        gia_an_hai = {m[0]: GIA_THEO_PHUONG[AN_HAI].get(i) for i, m in MAU.items()}.get(noi_dung["code"], 340000)
        return {"name": "Internet Meta F1", "price": {"price": 1020000, "contract_length_months": 3},     # giá theo thời hạn ngắn nhất, không phải giá tháng
                "card_description": "Modem Wi-Fi 6\nKết nối 25 thiết bị",
                "display_contents": {"promotion_contents": [{"contract_length_months": 13, "charge_type": "tra-truoc", "tag_line": "Tặng Camera"}]},
                "product_offering_price": [chinh_sach(3, 3 * gia_an_hai), chinh_sach(13, 12 * gia_an_hai), chinh_sach(6, 6 * gia_an_hai, hieu_luc_den=het)]}
    raise AssertionError(duong)


@pytest.fixture
def mang_gia(monkeypatch):
    xoa("gia_fpt")
    gf._GAN_NHAT.clear()
    monkeypatch.setattr(gf, "_goi_dich_vu", _dich_vu)
    yield
    xoa("gia_fpt")
    gf._GAN_NHAT.clear()


def test_phan_loai_goi_theo_ten():
    c = gf._chuan_goi(_goi(1, "a", "Super500 Biz Plus", gia=1))
    assert c["khach"] == "doanh_nghiep" and c["nhom"] == "Internet"
    assert gf._chuan_goi(_goi(2, "b", "Combo Lux 800 - V.VIP"))["khach"] == "doanh_nghiep"
    assert gf._chuan_goi(_goi(2, "b", "Combo Lux 800 - V.VIP"))["nhom"] == "Combo Internet + V.VIP"
    assert gf._chuan_goi(_goi(3, "c", "Sky An Tâm 7 - IQ4S"))["nhom"] == "Internet + Camera An Tâm"
    meta = gf._chuan_goi(_goi(4, "d", "Internet Meta F1", gia=330000))
    assert (meta["khach"], meta["gia"], meta["toc_do"], meta["thiet_bi"]) == ("ca_nhan", 330000, "1 Gbps / 300 Mbps", 15)
    assert gf._chuan_goi(_goi(5, "e", "Camera", "fpt-camera"))["nhom"] == "Camera"


def test_gia_khac_nhau_theo_phuong_va_loc(mang_gia):
    a, b = gf.goi_theo_phuong(TINH, AN_HAI), gf.goi_theo_phuong(TINH, QUANG_PHU)
    assert {g["ten"]: g["gia"] for g in a["goi"]}["Internet Meta F1"] == 340000
    assert {g["ten"]: g["gia"] for g in b["goi"]}["Internet Meta F1"] == 330000
    assert [g["ten"] for g in gf.loc_goi(a["goi"], "doanh_nghiep")] == ["Super300 Biz"]
    assert {g["ten"] for g in gf.loc_goi(a["goi"], "all", "FPT Play")} == {"Gói V.VIP 1"}
    assert {g["ten"] for g in gf.loc_goi(a["goi"], ["ca_nhan"], ["Internet", "FPT Play"])} == {"Internet Sky", "Internet Meta F1", "Gói V.VIP 1"}   # chọn nhiều
    assert len(gf.loc_goi(a["goi"], [], [])) == len(a["goi"]) == len(gf.loc_goi(a["goi"], ["all"], None))                              # để trống = tất cả
    assert gf.cac_nhom(a["goi"]) == ["Internet", "FPT Play"]
    assert all(g["ten"] != "Casper Smart TV" for g in a["goi"])            # Smart TV, Tăng tốc, Smart Home, thiết bị mạng không lấy (chủ app 22/10/2026)


def test_dich_vu_loi_thi_dung_ban_cu_hoac_bao_loi(mang_gia, monkeypatch):
    gf.goi_theo_phuong(TINH, AN_HAI)
    xoa("gia_fpt")                                                   # hết hạn nhớ tạm

    def hong(*a, **k):
        raise gf.LoiGia("x")
    monkeypatch.setattr(gf, "_goi_dich_vu", hong)
    kq = gf.goi_theo_phuong(TINH, AN_HAI)
    assert kq["cu"] is True and kq["goi"]                              # có bản lần trước: dùng tạm và báo là cũ
    with pytest.raises(gf.LoiGia):
        gf.goi_theo_phuong(TINH, QUANG_PHU)                            # chưa từng lấy được: báo lỗi để trang nói rõ


def test_chi_tiet_goi_tang_thang_va_bo_chinh_sach_het_han(mang_gia):
    ct = gf.chi_tiet_goi("goi-meta-f1", TINH, AN_HAI, 340000)
    assert [z["thang"] for z in ct["lua_chon"]] == [3, 13]               # chính sách 6 tháng đã hết hạn nên không hiện
    ba, muoi_ba = ct["lua_chon"]
    assert (ba["thang_dong"], ba["tang"]) == (3, 0) and ba["binh_quan"] == 340000
    assert (muoi_ba["thang_dong"], muoi_ba["tang"]) == (12, 1) and muoi_ba["binh_quan"] == 313846   # 13 tháng chỉ đóng 12
    assert muoi_ba["qua"] == "Tặng Camera" and muoi_ba["phi_lap"] == 500000
    assert ct["gia"] == 340000                                           # giá tháng lấy từ danh sách, không lấy giá theo thời hạn của dịch vụ chi tiết


def test_dieu_kien_chung_cua_nhom_va_diem_rieng_cua_goi(mang_gia):
    goi = [g for g in gf.goi_theo_phuong(TINH, AN_HAI)["goi"] if g["nhom"] == "Internet" and g["khach"] == "ca_nhan"]
    ct = gf.chi_tiet_nhieu(TINH, AN_HAI, goi)
    chung = gf.phan_chung(goi, ct)
    assert chung["tra_truoc"] == [3, 13] and chung["tra_sau"] is False and chung["tang"] == {"13": 1.0}
    assert chung["phi_lap"] == [500000, 500000] and chung["den"] and chung["so_goi"] == 2
    dong = gf.dong_chung(chung)
    assert "Thanh toán: trả trước 3 / 13 tháng" in dong and "Trả trước 13 tháng: tặng thêm 1 tháng" in dong and "Phí hòa mạng: 500.000đ" in dong
    assert gf.khac_biet(goi[0], ct[goi[0]["code"]], chung).get("phi_lap") is None      # phí giống phần chung thì không nhắc lại ở từng gói
    assert gf.phan_chung(goi[:1], ct) == {}                                             # một gói thì không có gì để gọi là chung
    assert gf.chu_phi_hoa_mang(ct[goi[0]["code"]]) == "500.000đ" and gf.chu_phi_hoa_mang(None) == ""
    assert gf.chu_phi_hoa_mang({"phi_lap": None}) == "Miễn phí"                          # dịch vụ không ghi khoản phí nào
    assert "phí hòa mạng 500.000đ" in gf.van_ban_bao_gia("An Hải", goi, utc_bay_gio(), chung, ct)   # chữ copy có phí hòa mạng từng gói
    rieng = gf.khac_biet(goi[0], ct[goi[0]["code"]], {})                                # nhóm không có phần chung: ghi đủ ở gói
    assert rieng["phi_lap"] == [500000, 500000]


def test_so_sanh_hai_phuong(mang_gia):
    a, b, c = (gf.goi_theo_phuong(TINH, p) for p in (AN_HAI, QUANG_PHU, QUE_SON))
    dong = {r["ten"]: r for r in gf.so_sanh(a["goi"], b["goi"])}
    meta = dong["Internet Meta F1"]
    assert (meta["gia_a"], meta["gia_b"], meta["chenh"], meta["pct"], meta["tinh_trang"]) == (340000, 330000, -10000, -2.9, "b_re")
    assert dong["Super300 Biz"]["tinh_trang"] == "bang" and dong["Super300 Biz"]["chenh"] == 0
    assert gf.dem_so_sanh(list(dong.values())) == {"b_re": 2, "b_dat": 0, "bang": 2, "chi_a": 0, "chi_b": 0}
    chi_a = {r["ten"]: r["tinh_trang"] for r in gf.so_sanh(a["goi"], c["goi"])}
    assert chi_a["Super300 Biz"] == "chi_a"                                # Quế Sơn không bán gói doanh nghiệp
    assert {r["tinh_trang"] for r in gf.so_sanh(c["goi"], a["goi"])} >= {"chi_b"}


def test_quet_tinh_vung_gia_va_bien_dong(mang_gia):
    du = gf.quet_tinh(TINH)
    assert len(du["gia"]) == 3 and not du["loi"]
    json.dumps(du)                                                        # giữ ở trình duyệt nên phải là JSON thuần
    nhom = gf.vung_gia(du, 18)
    assert [(n["gia"], n["phuong"]) for n in nhom] == [(330000, ["Phường Quảng Phú", "Xã Quế Sơn"]), (340000, ["Phường An Hải"])]
    biz = gf.vung_gia(du, 109)
    assert biz[-1] == {"gia": None, "phuong": ["Xã Quế Sơn"]}             # phường không bán đứng cuối
    bd = {r["ten"]: r for r in gf.bien_dong(du)}
    assert bd["Internet Meta F1"]["chenh"] == 10000 and bd["Internet Meta F1"]["so_muc"] == 2
    assert bd["Super300 Biz"]["khong_ban"] == 1 and bd["Super300 Biz"]["chenh"] == 0
    assert gf.bien_dong(du)[0]["chenh"] >= gf.bien_dong(du)[-1]["chenh"]


def test_quet_tinh_phuong_loi_thi_ghi_vao_loi(mang_gia, monkeypatch):
    def hong_mot_phuong(duong, noi_dung, han=15):
        if duong.endswith("packages/list") and noi_dung["location"]["ward_id"] == QUE_SON:
            raise gf.LoiGia("x")
        return _dich_vu(duong, noi_dung, han)
    monkeypatch.setattr(gf, "_goi_dich_vu", hong_mot_phuong)
    du = gf.quet_tinh(TINH)
    assert du["loi"] == [str(QUE_SON)] and len(du["gia"]) == 2


def test_chu_copy_gui_khach(mang_gia):
    a, b = gf.goi_theo_phuong(TINH, AN_HAI), gf.goi_theo_phuong(TINH, QUANG_PHU)
    chu = gf.van_ban_bao_gia("Phường An Hải, Đà Nẵng", a["goi"], a["luc"])
    assert "Internet Meta F1: 340.000đ/tháng" in chu and "tốc độ 1 Gbps / 300 Mbps" in chu and "VAT" in chu
    assert "INTERNET · DOANH NGHIỆP" in chu and "INTERNET · CÁ NHÂN" in chu          # mỗi nhóm một đề mục
    ss = gf.van_ban_so_sanh("An Hải", "Quảng Phú", gf.so_sanh(a["goi"], b["goi"]), a["luc"])
    assert "Internet Meta F1: An Hải 340.000đ · Quảng Phú 330.000đ" in ss
    assert gf.chu_tien(1234567) == "1.234.567đ" and gf.chu_tien(None) == "–"


# ------------------------------------------------------------------ trang
def _chu(node) -> str:
    return json.dumps(node, ensure_ascii=False, default=lambda o: o.to_plotly_json() if hasattr(o, "to_plotly_json") else str(o))


def _tk(role: str, scope: list[str] | None = None):
    from app.auth import SessionUser
    return SessionUser(SimpleNamespace(id=1, username=f"kiemthu.{role}", ho_ten="Kiểm thử", role=role, ma_nv=None, session_version=0,
                                       scope=json.dumps(scope or [])))


def test_moi_tai_khoan_khoi_kinh_doanh_vao_duoc_nhung_khoi_khac_thi_khong():
    for role, scope in (("admin", []), ("nvkd", ["IBB7"]), ("nvkd", ["IBB6"]), ("phong", ["IBB7"]), ("nhanvien", ["IBB7"])):
        assert _tk(role, scope).vao_duoc("/giafpt"), role
    assert not _tk("dvkh").vao_duoc("/giafpt")                           # vai trò chỉ ở khối DVKH


@pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(), reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")
def test_trang_tra_gia_dung_duoc_va_callback_kiem_quyen(mang_gia):
    from dash._callback_context import context_value
    from dash._utils import AttributeDict
    from dash.exceptions import PreventUpdate
    from flask_login import login_user

    from app.ui.app import app, server
    from app.ui.pages import giafpt

    def goi(dau_ra, tai_khoan, *args):
        ham = next(getattr(v["callback"], "__wrapped__", v["callback"]) for k, v in app.callback_map.items() if "callback" in v and dau_ra in k)
        with server.test_request_context("/"):
            login_user(tai_khoan)
            context_value.set(AttributeDict(triggered_inputs=[], inputs_list=[], states_list=[], outputs_list=[]))
            return ham(*args)

    with server.test_request_context("/"):
        login_user(_tk("nvkd", ["IBB7"]))
        giafpt.layout()
    tb, the, ds, chung, chu, ghi, pha = goi("gf-tb.children", _tk("nvkd", ["IBB7"]), "tra", TINH, AN_HAI, "all", "all", None)
    assert tb is None and pha["phuong"] == AN_HAI and "Gói đang hiện" not in ghi and "4 gói" in ghi
    assert "Internet Meta F1: 340.000đ/tháng" in chu and "Phường An Hải, Đà Nẵng" in chu
    mo_ta = _chu(ds)
    assert "gf-the" in mo_ta and "Super300 Biz" in mo_ta and "Đang nạp điều kiện chung" in mo_ta     # lượt một: thẻ + chỗ chờ phần chung
    assert "1 gói" in _chu(goi("gf-tb.children", _tk("nvkd", ["IBB7"]), "tra", TINH, AN_HAI, "doanh_nghiep", "all", None)[2])
    with pytest.raises(PreventUpdate):
        goi("gf-tb.children", _tk("dvkh"), "tra", TINH, AN_HAI, "all", "all", None)           # khối khác: máy chủ chặn
    with pytest.raises(PreventUpdate):
        goi("gf-tb.children", _tk("nvkd", ["IBB7"]), "sosanh", TINH, AN_HAI, "all", "all", None)   # tab đang ẩn không tính


@pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(), reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")
def test_trang_bao_loi_de_hieu_khi_fpt_khong_tra_loi(mang_gia, monkeypatch):
    from dash._callback_context import context_value
    from dash._utils import AttributeDict
    from flask_login import login_user

    from app.ui.app import app, server

    def hong(*a, **k):
        raise gf.LoiGia("Chưa lấy được giá từ fpt.vn lúc này.")
    monkeypatch.setattr(gf, "_goi_dich_vu", hong)
    ham = next(getattr(v["callback"], "__wrapped__", v["callback"]) for k, v in app.callback_map.items() if "callback" in v and "gf-tb.children" in k)
    with server.test_request_context("/"):
        login_user(_tk("admin"))
        context_value.set(AttributeDict(triggered_inputs=[], inputs_list=[], states_list=[], outputs_list=[]))
        tb, the, ds, chung, chu_copy, ghi, pha = ham("tra", TINH, AN_HAI, "all", "all", None)
    chu = json.dumps(tb.to_plotly_json(), ensure_ascii=False)
    assert "Chưa lấy được giá từ fpt.vn" in chu and ds == [] and pha is None
