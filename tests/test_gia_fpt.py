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
from app import gia_fpt_nhom as gn  # noqa: E402
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
KICH_BAN: dict = {}        # code gói -> {"phi": số / None (không ghi dòng phí), "tra_sau": phí trả sau, "thieu_lan_dau": "rong" | "ca_nhan_combo", "thieu_mai": True}
LAN_GOI: dict = {}         # code gói -> số lần đã gọi packages/get


def _chinh_sach(thang, tong, phi, tinh_trang="active", hieu_luc_den=None, hinh_thuc="Trả trước"):
    tu, den = utc_bay_gio() - timedelta(days=30), hieu_luc_den or utc_bay_gio() + timedelta(days=30)
    return {"name": "CS INT Cá nhân", "status": tinh_trang, "billing_type_name": hinh_thuc, "contract_length_months": thang,
            "sale_platform_code": "INT.1", "effective_from": tu.strftime("%Y-%m-%d %H:%M:%S"),
            "effective_to": den.strftime("%Y-%m-%d %H:%M:%S"),
            "summary": {"service_price": {"price": tong}, "fee_price": None if phi is None else {"price": phi}, "device_price": None}}


def _chi_tiet_goi_gia(noi_dung):
    code = noi_dung["code"]
    kb = KICH_BAN.get(code, {})
    LAN_GOI[code] = LAN_GOI.get(code, 0) + 1
    gia_an_hai = {**{m[0]: GIA_THEO_PHUONG[AN_HAI].get(i) for i, m in MAU.items()}, "sky-an-tam": 395000, "meta-an-tam": 405000}.get(code, 340000)
    het = utc_bay_gio() - timedelta(days=1)
    phi = None if (kb.get("thieu_phi_lan_dau") and LAN_GOI[code] == 1) else kb.get("phi", 500000)       # lượt đầu mất dòng "Phí lắp đặt Internet"
    cs =[_chinh_sach(3, 3 * gia_an_hai, phi), _chinh_sach(13, 12 * gia_an_hai, phi), _chinh_sach(6, 6 * gia_an_hai, phi, hieu_luc_den=het)]
    if "tra_sau" in kb:
        cs.insert(0, _chinh_sach(1, gia_an_hai, kb["tra_sau"], hinh_thuc="Trả sau"))
    thieu = kb.get("thieu_mai") or (kb.get("thieu_lan_dau") and LAN_GOI[code] == 1)
    if thieu:
        cs = [] if kb.get("thieu") != "combo" else [{**_chinh_sach(1, None, 840000), "billing_type_name": None, "contract_length_months": None}]
    return {"name": "Internet Meta F1", "price": {"price": 1020000, "contract_length_months": 3},     # giá theo thời hạn ngắn nhất, không phải giá tháng
            "card_description": "Modem Wi-Fi 6\nKết nối 25 thiết bị",
            "display_contents": {"promotion_contents": [{"contract_length_months": 13, "charge_type": "tra-truoc", "tag_line": "Tặng Camera"}]},
            "product_offering_price": cs}


def _dich_vu(duong, noi_dung, han=15):
    if duong.endswith("provinces/list"):
        return [{"id": 8, "text": "Hồ Chí Minh"}, {"id": TINH, "text": "Đà Nẵng"}]
    if duong.endswith("wards/list"):
        return [{"id": QUE_SON, "text": "Xã Quế Sơn"}, {"id": AN_HAI, "text": "Phường An Hải"}, {"id": QUANG_PHU, "text": "Phường Quảng Phú"}]
    if duong.endswith("packages/list"):
        bang = GIA_THEO_PHUONG[noi_dung["location"]["ward_id"]]
        bay = [_goi(24, "goi-vvip1", "Gói V.VIP 1", "fpt-play", 130000), _goi(128, "casper", "Casper Smart TV", "smart-tivi", 3378531),
               _goi(129, "cam-iq4s", "Camera IQ4S", "fpt-camera", 1200000)]                    # Camera / FPT Play / Smart TV lẻ: không lấy (chủ app 22/10/2026)
        return [_goi(int(i), MAU[i][0], MAU[i][1], gia=g) for i, g in bang.items()] + bay
    if duong.endswith("packages/get"):
        return _chi_tiet_goi_gia(noi_dung)
    raise AssertionError(duong)


CH_TEST = {"nhom": [("Internet cá nhân", ["sky"]), ("Internet gia đình", ["meta-f1"]), ("Internet game thủ", ["meta-f1"]),
                    ("Combo Internet Camera", ["sky-an-tam", "meta-an-tam"]), ("Internet doanh nghiệp", ["super300"])], "nguon": "website"}


@pytest.fixture(autouse=True)
def chan_mang_nhom(monkeypatch):
    """Cấu hình nhóm cố định khớp mã giả của file này: test không bao giờ gọi fpt.vn thật (Meta F1 nằm ở hai nhóm như website)."""
    monkeypatch.setattr(gn, "cau_hinh", lambda: {"nhom": [(n, list(m)) for n, m in CH_TEST["nhom"]], "nguon": CH_TEST["nguon"]})


@pytest.fixture
def mang_gia(monkeypatch):
    xoa("gia_fpt")
    gf._GAN_NHAT.clear()
    KICH_BAN.clear()
    LAN_GOI.clear()
    monkeypatch.setattr(gf, "_goi_dich_vu", _dich_vu)
    yield
    xoa("gia_fpt")
    gf._GAN_NHAT.clear()
    KICH_BAN.clear()
    LAN_GOI.clear()


def test_bo_dong_qua_tang_camera_nhung_giu_uu_dai_khac():
    assert gf._chuan_goi(_goi(1, "a", "Internet Sky", tagline="Nhận Camera AI + Cloud 12T miễn phí"))["uu_dai"] == ""
    assert gf._chuan_goi(_goi(2, "b", "Internet Sky", tagline="Tặng 12T FPT Play"))["uu_dai"] == "Tặng 12 tháng FPT Play"


def test_phan_loai_goi_theo_ten():
    c = gf._chuan_goi(_goi(1, "a", "Super500 Biz Plus", gia=1))
    assert c["khach"] == "doanh_nghiep" and "nhom" not in c                          # nhóm không còn đoán theo tên: lấy từ website (gia_fpt_nhom)
    assert gf._chuan_goi(_goi(2, "b", "Combo Lux 800 - V.VIP"))["khach"] == "doanh_nghiep"
    meta = gf._chuan_goi(_goi(4, "d", "Internet Meta F1", gia=330000))
    assert (meta["khach"], meta["gia"], meta["toc_do"], meta["thiet_bi"]) == ("ca_nhan", 330000, "1 Gbps / 300 Mbps", 15)
    assert gf._chuan_goi(_goi(9, "lux500", "Internet Lux500", gia=800000))["khach"] == "doanh_nghiep"                  # Lux500 là gói doanh nghiệp


def test_gia_khac_nhau_theo_phuong_va_loc(mang_gia):
    a, b = gf.goi_theo_phuong(TINH, AN_HAI), gf.goi_theo_phuong(TINH, QUANG_PHU)
    assert {g["ten"]: g["gia"] for g in a["goi"]}["Internet Meta F1"] == 340000
    assert {g["ten"]: g["gia"] for g in b["goi"]}["Internet Meta F1"] == 330000
    assert [g["ten"] for g in gf.loc_goi(a["goi"], "doanh_nghiep")] == ["Super300 Biz"]
    assert {g["ten"] for g in gf.loc_goi(a["goi"], ["ca_nhan"])} == {"Internet Sky", "Internet Meta F1"}                  # chọn nhiều / một giá trị
    assert len(gf.loc_goi(a["goi"], [])) == len(a["goi"]) == len(gf.loc_goi(a["goi"], ["all"]))                           # để trống = tất cả
    nhom = gf.theo_nhom(a["goi"])
    assert list(nhom) == ["Internet cá nhân", "Internet gia đình", "Internet game thủ", "Internet doanh nghiệp"]          # theo thứ tự của website, nhóm trống bỏ
    assert nhom["Internet gia đình"] == nhom["Internet game thủ"]                                                         # một gói ở hai nhóm thì hiện ở cả hai
    ten = {g["ten"] for g in a["goi"]}
    assert not ten & {"Casper Smart TV", "Gói V.VIP 1", "Camera IQ4S"}      # Smart TV, FPT Play lẻ, Camera lẻ và các loại khác không lấy (chủ app 22/10/2026)
    assert all(g["code"] not in ("goi-vvip1", "casper", "cam-iq4s") for g in a["goi"])


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


def test_dieu_kien_chung_cua_nhom_va_diem_rieng_cua_goi(mang_gia_an_tam):
    goi = gf.theo_nhom(gf.goi_theo_phuong(TINH, AN_HAI)["goi"])["Combo Internet Camera"]
    ct = gf.chi_tiet_nhieu(TINH, AN_HAI, goi)
    chung = gf.phan_chung(goi, ct)
    assert chung["tra_truoc"] == [3, 13] and chung["tra_sau"] is False and chung["tang"] == {"13": 1.0}
    assert chung["phi"] == 500000 and chung["den"] and chung["so_goi"] == 2
    dong = gf.dong_chung(chung)
    assert "Thanh toán: trả trước 3 / 13 tháng" in dong and "Trả trước 13 tháng: tặng thêm 1 tháng" in dong and "Phí hòa mạng: 500.000đ" in dong
    assert gf.phan_chung(goi[:1], ct) == {}                                             # một gói thì không có gì để gọi là chung
    assert gf.chu_phi_hoa_mang(ct[goi[0]["code"]]) == "500.000đ" and gf.chu_phi_hoa_mang(None) == ""
    assert "phi" not in gf.khac_biet(goi[0], ct[goi[0]["code"]], {})                     # phí luôn ghi riêng ở thẻ, không nằm trong phần "khác biệt"
    ct[goi[1]["code"]]["phi_nhom"] = [["Trả trước 3 / 13 tháng", 700000]]
    assert gf.phan_chung(goi, ct)["phi"] is None                                         # hai gói khác phí thì dải chung không ghi phí
    assert not any(d.startswith("Phí hòa mạng") for d in gf.dong_chung(gf.phan_chung(goi, ct)))


# ------------------------------------------------------------------ phí hòa mạng: không suy ra "miễn phí" từ chỗ trống (22/10/2026)
def _lc(hinh_thuc, thang, phi):
    return {"hinh_thuc": hinh_thuc, "thang": thang, "phi_lap": phi}


def test_phi_hoa_mang_chi_ghi_mien_phi_khi_dich_vu_ghi_ro_la_0(mang_gia):
    KICH_BAN["goi-sky"] = {"phi": 0}
    ct = gf.chi_tiet_goi("goi-sky", TINH, AN_HAI, 205000)
    assert ct["phi_nhom"] == [["Trả trước 3 / 13 tháng", 0]] and gf.chu_phi_hoa_mang(ct) == "Miễn phí"
    KICH_BAN["goi-meta-f1"] = {"phi": None}
    ct = gf.chi_tiet_goi("goi-meta-f1", TINH, AN_HAI, 340000)                        # dịch vụ KHÔNG ghi dòng phí: chưa rõ, không phải miễn phí
    assert ct["phi_nhom"] == [] and gf.chu_phi_hoa_mang(ct) == "Chưa rõ"
    assert "fpt.vn" in gf.chu_phi_hoa_mang(ct, chi_tiet=True)
    assert LAN_GOI["goi-meta-f1"] == gf.LAN_THU                                       # đã gọi lại hết lượt mới chịu "chưa rõ"


def test_dich_vu_tra_thieu_thi_goi_lai_cho_toi_khi_du(mang_gia):
    KICH_BAN["goi-sky"] = {"thieu_lan_dau": True}                                    # lượt đầu: danh sách chính sách rỗng
    ct = gf.chi_tiet_goi("goi-sky", TINH, AN_HAI, 205000)
    assert LAN_GOI["goi-sky"] == 2 and ct["phi_nhom"] == [["Trả trước 3 / 13 tháng", 500000]]
    KICH_BAN["goi-meta-f1"] = {"thieu_lan_dau": True, "thieu": "combo"}              # lượt đầu: chỉ có chính sách "Combo" không có hình thức thanh toán
    ct = gf.chi_tiet_goi("goi-meta-f1", TINH, AN_HAI, 340000)
    assert LAN_GOI["goi-meta-f1"] == 2 and [z["thang"] for z in ct["lua_chon"]] == [3, 13]
    KICH_BAN["goi-super300"] = {"thieu_mai": True}                                   # lượt nào cũng rỗng: báo lỗi, không hiện số
    with pytest.raises(gf.LoiGia):
        gf.chi_tiet_goi("goi-super300", TINH, AN_HAI, 450000)
    assert gf.chi_tiet_nhieu(TINH, AN_HAI, [{"code": "goi-super300", "gia": 450000}]) == {"goi-super300": None}


def test_mat_dong_phi_lan_dau_thi_goi_lai_va_lay_phi_that(mang_gia):
    KICH_BAN["goi-sky"] = {"thieu_phi_lan_dau": True}                                # lượt đầu có chính sách nhưng không có dòng phí; lượt sau đủ
    ct = gf.chi_tiet_goi("goi-sky", TINH, AN_HAI, 205000)
    assert LAN_GOI["goi-sky"] == 2                                                   # phải gọi lại, không dừng ở lượt thiếu
    assert ct["phi_nhom"] == [["Trả trước 3 / 13 tháng", 500000]] and gf.chu_phi_hoa_mang(ct) == "500.000đ"
    assert "Chưa rõ" not in gf.chu_phi_hoa_mang(ct) and "Miễn phí" not in gf.chu_phi_hoa_mang(ct)


def test_diem_day_du_xep_dung_thu_tu():
    def cs(phi, hinh_thuc="Trả trước", dich_vu=300000):
        return {"billing_type_name": hinh_thuc,
                "summary": {"service_price": {"price": dich_vu}, "fee_price": None if phi is None else {"price": phi}}}
    assert gf._diem_day_du({}, 300000) == 0
    assert gf._diem_day_du({"product_offering_price": [{"billing_type_name": None, "summary": {}}]}, 300000) == 0     # chỉ có dòng "Combo" không hình thức thanh toán
    assert gf._diem_day_du({"product_offering_price": [cs(None)]}, 300000) == 2                                         # thiếu phí
    assert gf._diem_day_du({"product_offering_price": [cs(0)]}, 300000) == 3                                            # phí 0 là có phí
    assert gf._diem_day_du({"product_offering_price": [cs(0, "Trả sau", 250000)]}, 300000) == 2                         # trả sau lệch giá tháng của danh sách
    assert gf._diem_day_du({"product_offering_price": [cs(0), cs(None)]}, 300000) == 2                                  # chỉ cần một cách thiếu phí là chưa đủ


def test_phi_cung_muc_gom_mot_dong_va_phi_0_chung_cua_nhom():
    nhom = gf._nhom_phi([_lc("Trả sau", 1, 500000), _lc("Trả trước", 6, 500000), _lc("Trả trước", 13, 500000)])
    assert nhom == [["Trả theo tháng · trả trước 6 / 13 tháng", 500000]]            # cùng mức phí thì một dòng, không lặp
    assert gf.dong_phi({"phi_nhom": nhom}) == ["500.000đ"]
    mien = {"phi_nhom": [["Trả trước 3 / 13 tháng", 0]], "thiet_bi": None}
    chung = gf.phan_chung([{"code": "a", "uu_dai": ""}, {"code": "b", "uu_dai": ""}],
                          {"a": {**mien, "lua_chon": [{"hinh_thuc": "Trả trước", "thang": 3, "tang": 0, "den": ""}]},
                           "b": {**mien, "lua_chon": [{"hinh_thuc": "Trả trước", "thang": 3, "tang": 0, "den": ""}]}})
    assert chung["phi"] == 0 and "Phí hòa mạng: Miễn phí" in gf.dong_chung(chung)   # số 0 chung của cả nhóm không bị coi là "không có"
    chua_ro = {"phi_nhom": [], "thiet_bi": None, "lua_chon": [{"hinh_thuc": "Trả trước", "thang": 3, "tang": 0, "den": ""}]}
    chung = gf.phan_chung([{"code": "a", "uu_dai": ""}, {"code": "b", "uu_dai": ""}], {"a": chua_ro, "b": chua_ro})
    assert chung["phi"] is None and not any(d.startswith("Phí hòa mạng") for d in gf.dong_chung(chung))   # cả nhóm chưa rõ: dải chung không ghi phí


def test_phi_khac_nhau_theo_cach_thanh_toan_ghi_tung_cach(mang_gia):
    KICH_BAN["goi-sky"] = {"phi": 600000, "tra_sau": 1000000}                        # kiểu gói Biz: trả sau 1.000.000, trả trước 600.000
    ct = gf.chi_tiet_goi("goi-sky", TINH, AN_HAI, 205000)
    assert ct["phi_nhom"] == [["Trả theo tháng", 1000000], ["Trả trước 3 / 13 tháng", 600000]]
    assert gf.chu_phi_hoa_mang(ct) == "Trả theo tháng: 1.000.000đ · Trả trước 3 / 13 tháng: 600.000đ"
    assert [z["phi_lap"] for z in ct["lua_chon"]] == [1000000, 600000, 600000]


def test_phi_giu_so_0_va_chi_can_mot_cach_thieu_la_chua_ro():
    nhom = gf._nhom_phi([_lc("Trả sau", 1, 0), _lc("Trả trước", 6, 300000), _lc("Trả trước", 13, 300000)])
    assert nhom == [["Trả theo tháng", 0], ["Trả trước 6 / 13 tháng", 300000]]       # số 0 không bị bỏ khỏi khoảng
    chu = gf.chu_phi_hoa_mang({"phi_nhom": nhom})
    assert "Miễn phí" in chu and "300.000đ" in chu
    assert gf._nhom_phi([_lc("Trả sau", 1, 0), _lc("Trả trước", 6, None)]) == []   # một cách không ghi phí: không kết luận miễn phí cho cả gói
    assert gf._nhom_phi([]) == []
    assert gf.chu_phi_hoa_mang({"phi_nhom": [["", 0]]}) == "Miễn phí"


def test_so_sanh_hai_phuong(mang_gia):
    a, b, c = (gf.goi_theo_phuong(TINH, p) for p in (AN_HAI, QUANG_PHU, QUE_SON))
    dong = {r["ten"]: r for r in gf.so_sanh(a["goi"], b["goi"])}
    meta = dong["Internet Meta F1"]
    assert (meta["gia_a"], meta["gia_b"], meta["chenh"], meta["pct"], meta["tinh_trang"]) == (340000, 330000, -10000, -2.9, "b_re")
    assert dong["Super300 Biz"]["tinh_trang"] == "bang" and dong["Super300 Biz"]["chenh"] == 0
    assert meta["nhom"] == "Internet gia đình · Internet game thủ" and dong["Super300 Biz"]["nhom"] == "Internet doanh nghiệp"     # cột Nhóm nối các nhóm
    assert gf.dem_so_sanh(list(dong.values())) == {"b_re": 2, "b_dat": 0, "bang": 1, "chi_a": 0, "chi_b": 0}
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
    assert all("code" not in tt and "gia" not in tt for tt in du["goi"].values()) and du["goi"]["18"]["nhom"] == "Internet gia đình · Internet game thủ"


def test_quet_tinh_phuong_loi_thi_ghi_vao_loi(mang_gia, monkeypatch):
    def hong_mot_phuong(duong, noi_dung, han=15):
        if duong.endswith("packages/list") and noi_dung["location"]["ward_id"] == QUE_SON:
            raise gf.LoiGia("x")
        return _dich_vu(duong, noi_dung, han)
    monkeypatch.setattr(gf, "_goi_dich_vu", hong_mot_phuong)
    du = gf.quet_tinh(TINH)
    assert du["loi"] == [str(QUE_SON)] and len(du["gia"]) == 2


def test_nhom_mac_dinh_va_huong_dan_khong_con_noi_moi_goi_mot_nhom():
    assert gf.NHOM_MAC_DINH == "Internet cá nhân"
    assert not hasattr(gf, "NHOM") and not hasattr(gf, "phan_nhom")                           # nhóm do gia_fpt_nhom lo
    ma = Path(gf.__file__).read_text(encoding="utf-8")
    assert "fpt-camera" not in ma and "fpt-play" not in ma
    cs = (Path(__file__).resolve().parent.parent / "app" / "ui" / "pages" / "huongdan.py").read_text(encoding="utf-8")
    tra_gia = cs[cs.index('_muc("Tra cứu giá"'):cs.index('_muc("Ads IBB7')]
    assert "Copy bảng giá" not in tra_gia and "lắp đặt" not in tra_gia and "phí hòa mạng" in tra_gia
    assert "đúng một nhóm" not in tra_gia and "nhiều nhóm" in tra_gia


def test_chu_so_sanh_gui_khach(mang_gia):
    a, b = gf.goi_theo_phuong(TINH, AN_HAI), gf.goi_theo_phuong(TINH, QUANG_PHU)
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


def _goi_callback(dau_ra, tai_khoan, *args, bam=None):
    """Gọi thẳng callback có đầu ra `dau_ra` như một người dùng đã đăng nhập; `bam` là id (dict) của thẻ vừa được bấm."""
    from dash._callback_context import context_value
    from dash._utils import AttributeDict, stringify_id
    from flask_login import login_user

    from app.ui.app import app, server
    ham = next(getattr(v["callback"], "__wrapped__", v["callback"]) for k, v in app.callback_map.items() if "callback" in v and dau_ra in k)
    kich_hoat = [{"prop_id": f"{stringify_id(bam)}.n_clicks", "value": 1}] if bam else []
    with server.test_request_context("/"):
        login_user(tai_khoan)
        context_value.set(AttributeDict(triggered_inputs=kich_hoat, inputs_list=[], states_list=[], outputs_list=[]))
        return ham(*args)


@pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(), reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")
def test_trang_tra_gia_dung_duoc_va_callback_kiem_quyen(mang_gia_an_tam):
    from dash.exceptions import PreventUpdate
    from flask_login import login_user

    from app.ui.app import app, server
    from app.ui.pages import giafpt

    goi = _goi_callback

    with server.test_request_context("/"):
        login_user(_tk("nvkd", ["IBB7"]))
        giafpt.layout()
    sale = _tk("nvkd", ["IBB7"])
    tb, luc, nut, chon, ctd, pha = goi("gf-tb.children", sale, "tra", TINH, AN_HAI, None, None)
    assert tb is None and pha["phuong"] == AN_HAI and ctd is None and luc.startswith("Giá lấy lúc ")
    nhan = [n["label"] for n in nut]
    assert nhan == ["Internet cá nhân (1)", "Internet gia đình (1)", "Internet game thủ (1)", "Internet doanh nghiệp (1)", "Combo Internet Camera (2)"]   # thứ tự nút của CEO, nhóm trống bỏ
    assert "lưu sẵn" not in luc                                                                            # nhóm lấy từ website
    assert chon == "Internet cá nhân"                                                                      # mặc định Internet cá nhân
    assert goi("gf-tb.children", sale, "tra", TINH, AN_HAI, None, "Internet doanh nghiệp")[3] == "Internet doanh nghiệp"    # giữ nhóm đang xem khi đổi phường
    mo_ta = _chu(goi("gf-ds.children", sale, "Combo Internet Camera", pha, None))
    assert "gf-the" in mo_ta and "Sky An Tâm 7" in mo_ta and "Super300 Biz" not in mo_ta                  # chỉ nhóm đang chọn
    assert "Đang nạp chính sách chung" in mo_ta and "Chính sách chung" not in mo_ta                       # chi tiết chưa về: có chỗ chờ, phí hòa mạng chưa là "Chưa rõ"
    assert "Chưa rõ" not in mo_ta
    chi_tiet = goi("gf-ctd.data@", sale, pha)
    assert chi_tiet["pha"] == pha["khoa"] and chi_tiet["chung"] and chi_tiet["ct"]
    assert all("phi_nhom" in c for c in chi_tiet["ct"].values())
    mo_ta2 = _chu(goi("gf-ds.children", sale, "Combo Internet Camera", pha, chi_tiet))
    assert "Đang nạp chính sách chung" not in mo_ta2 and "Phí hòa mạng" in mo_ta2 and "Chính sách chung" in mo_ta2
    cu = dict(chi_tiet, pha="khac")                                                                        # kết quả của phường khác về muộn: bỏ qua
    assert "Đang nạp chính sách chung" in _chu(goi("gf-ds.children", sale, "Combo Internet Camera", pha, cu))
    with pytest.raises(PreventUpdate):
        goi("gf-tb.children", _tk("dvkh"), "tra", TINH, AN_HAI, None, None)                                # khối khác: máy chủ chặn
    with pytest.raises(PreventUpdate):
        goi("gf-tb.children", sale, "sosanh", TINH, AN_HAI, None, None)                                    # tab đang ẩn không tính
    assert not any("gf-con" in k for k in app.callback_map)   # hàng nút nhỏ đã bỏ hẳn


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
        tb, luc, nut, chon, ctd, pha = ham("tra", TINH, AN_HAI, None, None)
    chu = json.dumps(tb.to_plotly_json(), ensure_ascii=False)
    assert "Chưa lấy được giá từ fpt.vn" in chu and nut == [] and pha is None


# ------------------------------------------------------------------ thẻ và cửa sổ chi tiết (sửa 22/10/2026)
AN_TAM = [("sky-an-tam", "Sky An Tâm 7 - IQ4S"), ("meta-an-tam", "Meta An Tâm 7 - IQ4S")]


@pytest.fixture
def mang_gia_an_tam(mang_gia, monkeypatch):
    """Dữ liệu giả có thêm hai gói An Tâm (tên có chữ "â"); không đưa vào `_dich_vu` chung để các test khác giữ nguyên số gói."""
    def co_an_tam(duong, noi_dung, han=15):
        kq = _dich_vu(duong, noi_dung, han)
        if duong.endswith("packages/list"):
            kq += [_goi(40 + i, ma, ten, gia=395000 + 10000 * i) for i, (ma, ten) in enumerate(AN_TAM)]
        return kq
    monkeypatch.setattr(gf, "_goi_dich_vu", co_an_tam)


def _id_the(node) -> list[dict]:
    ra = []
    if isinstance(getattr(node, "id", None), dict) and node.id.get("type") == "gf-the":
        ra.append(node.id)
    kids = getattr(node, "children", None)
    for k in kids if isinstance(kids, (list, tuple)) else [kids]:
        if k is not None and not isinstance(k, (str, int, float)):
            ra += _id_the(k)
    return ra


def _the_mau(**ghi_de):
    from app.ui.pages import giafpt_the
    g = {"code": "x", "ten": "Internet Sky", "khach": "ca_nhan", "gia": 200000, "toc_do": "1 Gbps / 300 Mbps", "thiet_bi": None,
         "nhan": "", "uu_dai": ""}
    return giafpt_the._the({**g, **ghi_de}, {}, None, False)


@pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(), reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")
def test_the_goi_an_tam_bam_mo_duoc_chi_tiet(mang_gia_an_tam):
    from dash._utils import stringify_id
    from dash.exceptions import PreventUpdate

    sale = _tk("nvkd", ["IBB7"])
    pha = {"tinh": TINH, "phuong": AN_HAI, "luc": "x", "khoa": f"{TINH}-{AN_HAI}"}
    chi_tiet = _goi_callback("gf-ctd.data@", sale, pha)
    assert chi_tiet["chung"]["Combo Internet Camera"]                                    # hai gói An Tâm nên có phần chung của nhóm
    cay = {"internet": _goi_callback("gf-ds.children", sale, "Internet cá nhân", pha, chi_tiet),
           "combo": _goi_callback("gf-ds.children", sale, "Combo Internet Camera", pha, chi_tiet),
           "doanh_nghiep": _goi_callback("gf-ds.children", sale, "Internet doanh nghiệp", pha, chi_tiet)}
    for ten, c in cay.items():
        ids = _id_the(c)
        assert ids, ten
        for i in ids:                                                                       # Dash thoát chữ "â" khác chữ trình duyệt gửi lên: id chỉ được mang chữ ASCII
            assert all(not isinstance(v, str) or v.isascii() for v in i.values()), i
            assert stringify_id(i).isascii()
    assert {i["code"] for i in _id_the(cay["combo"])} == {m for m, _ in AN_TAM}

    def mo(code, muc):
        return _goi_callback("gf-ct-than.children", sale, [1], TINH, AN_HAI, chi_tiet, muc, bam={"type": "gf-the", "code": code})
    lop, tieu, than = mo("sky-an-tam", "Combo Internet Camera")                              # thẻ trong nhóm Combo Internet Camera
    assert lop == "modal mo" and tieu == "Sky An Tâm 7 - IQ4S"
    assert "điều kiện chung của nhóm" in _chu(than) and "Combo Internet Camera" in _chu(than)   # phần chung của nhóm đang xem + chip tên nhóm
    lop, tieu, than = mo("meta-f1", "Internet game thủ")                                    # Meta F1 nằm ở hai nhóm: lấy nhóm đang xem
    assert lop == "modal mo" and tieu == "Internet Meta F1" and "Internet game thủ" in _chu(than)
    with pytest.raises(PreventUpdate):                                                      # thẻ vừa dựng lại (không có lượt bấm) thì không mở
        _goi_callback("gf-ct-than.children", sale, [0], TINH, AN_HAI, chi_tiet, "Internet cá nhân")


def test_cot_bang_chi_tiet_cho_vua_man_800px():
    from app.ui.pages import giafpt_ct
    hang = [{"thoi_han": "Trả trước 3 tháng", "tong": 1, "binh_quan": 1, "tang": None, "phi_lap": 5, "thiet_bi": 0, "qua": None},
            {"thoi_han": "Trả trước 13 tháng", "tong": 2, "binh_quan": 2, "tang": 1, "phi_lap": 5, "thiet_bi": 0, "qua": "Tặng Camera"}]
    cot = {c["field"]: c for c in giafpt_ct._cot(hang)}
    assert cot["qua"]["wrapText"] and cot["qua"]["autoHeight"] and cot["qua"]["minWidth"] <= 150
    assert sum(c["minWidth"] for c in cot.values()) <= 700                                  # trường hợp thường gặp (phí, thiết bị giống nhau nên ẩn); hộp ở 800 px còn ~700 px cho bảng


def test_the_khong_toc_do_thi_bo_dong_toc_do():
    chu = _chu(_the_mau(toc_do=None))
    assert "Tốc độ" not in chu and "–" not in chu                                            # mất hẳn dòng, không để dấu gạch ngang thay chỗ
    assert "Phí hòa mạng" in chu
    day_du = _chu(_the_mau())
    assert "Tốc độ" in day_du and "gf-toc-do" in day_du
    mot_chieu = _chu(_the_mau(toc_do="1 Gbps"))
    assert "Tốc độ" in mot_chieu and "↑" not in mot_chieu


def test_the_ghi_phi_hoa_mang_dung_va_khong_suy_ra_mien_phi():
    from app.ui.pages import giafpt_the
    g = {"code": "x", "ten": "Internet Sky", "khach": "ca_nhan", "gia": 200000, "toc_do": None, "thiet_bi": None, "nhan": "", "uu_dai": ""}

    def the(ct, dang_nap=False):
        return _chu(giafpt_the._the(g, {}, ct, False, dang_nap))
    assert "Chưa rõ" in the(None) and "Miễn phí" not in the(None)                           # chi tiết cả phường đã về mà gói này không có: Chưa rõ
    dang = the(None, dang_nap=True)
    assert "…" in dang and "Chưa rõ" not in dang                                            # còn đang nạp: dấu chờ, không báo Chưa rõ vội
    assert "Chưa rõ" in the({"phi_nhom": [], "thiet_bi": None})                              # dịch vụ không ghi phí
    assert "Miễn phí" in the({"phi_nhom": [["", 0]], "thiet_bi": None})                     # chỉ khi ghi rõ 0
    assert "300.000đ" in the({"phi_nhom": [["", 300000]], "thiet_bi": None})
    nhieu = the({"phi_nhom": [["Trả theo tháng", 1000000], ["Trả trước 6 / 13 tháng", 600000]], "thiet_bi": None})
    assert "Trả theo tháng: 1.000.000đ" in nhieu and "Trả trước 6 / 13 tháng: 600.000đ" in nhieu
