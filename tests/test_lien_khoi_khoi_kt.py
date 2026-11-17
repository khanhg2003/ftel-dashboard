"""Khối Kỹ thuật (nhánh thi-lien-khoi): số liệu từ file báo cáo Kỹ thuật, nhận định bằng luật, các trang /kt và nguồn dữ liệu thật / minh hoạ."""
from __future__ import annotations

import json
import re

import pandas as pd
import pytest

from app.kt import so_lieu as sl
from app.lien_khoi import doc_kt, nguon

T = pd.Timestamp
NOW = T("2026-11-14 12:00")


def _ev(*dong) -> pd.DataFrame:
    mac = dict(so_hd="DAAAA0001", loai="ton_kt", thoi_diem=T("2026-11-10 10:00"), chi_tiet="", nguoi="ktv_01", so_lan=None, thuoc_tinh="{}")
    return pd.DataFrame([{**mac, **d} for d in dong], columns=nguon.COT_KT)


def _tt(**kw) -> str:
    return json.dumps(kw, ensure_ascii=False)


def _kpi(*dong) -> pd.DataFrame:
    mac = dict(vung="V", block="B1", lo="B1.L1", dung_hen_l1=0, dung_hen=0, qua_hen=0, tich_tin_pnc=0, bao_tri_24h=0, tong_l1=0, tong=0, kh_co_cl=0, tong_tgxl=0)
    return pd.DataFrame([{**mac, **d} for d in dong], columns=doc_kt.KPI_COT)


# ------------------------------------------------------------------ tồn và lịch hẹn
def test_ton_tinh_tuoi_va_qua_moc_hen():
    ev = _ev(dict(so_hd="A", thuoc_tinh=_tt(hen_xanh="2026-11-13 10:00", hen_do="2026-11-14 09:00")),            # qua cả xanh và đỏ
             dict(so_hd="B", thoi_diem=T("2026-11-01 12:00"), thuoc_tinh=_tt(hen_xanh="2026-11-20 10:00")),     # tồn 13 ngày, chưa tới hẹn
             dict(so_hd="C", nguoi=None, thuoc_tinh=_tt(hen_xanh="2026-11-13 10:00")))                           # quá xanh, chưa phân công
    t = sl.ton(ev, NOW).set_index("so_hd")
    assert t.loc["B", "ngay_ton"] == 13.0 and t.loc["B", "tuoi"] == "7 - 14 ngày" and not t.loc["B", "qua_xanh"]
    assert t.loc["A", "qua_xanh"] and t.loc["A", "qua_do"] and t.loc["C", "qua_xanh"] and not t.loc["C", "qua_do"]
    assert t.loc["C", "nguoi"] == "Chưa phân công" and list(sl.ton(ev, NOW)["so_hd"])[0] == "B"                   # tồn lâu nhất trước
    assert sl.ton_theo_tuoi(sl.ton(ev, NOW)).set_index("nhom").loc["7 - 14 ngày", "so"] == 1


def test_ton_khong_nhan_su_kien_loai_khac():
    ev = _ev(dict(so_hd="A"), dict(so_hd="B", loai="checklist", so_lan=2))
    assert list(sl.ton(ev, NOW)["so_hd"]) == ["A"]
    assert sl.ton(ev[ev["loai"] != "ton_kt"], NOW).empty


# ------------------------------------------------------------------ KPI theo block: tỷ lệ tính lại từ số đếm
def test_theo_block_cong_cac_lo_roi_moi_tinh_ty_le():
    k = _kpi(dict(block="B1", lo="B1.L1", dung_hen_l1=1, tong_l1=2, dung_hen=3, tong=4, bao_tri_24h=1, tong_tgxl=40),
             dict(block="B1", lo="B1.L2", dung_hen_l1=3, tong_l1=8, dung_hen=5, tong=6, bao_tri_24h=1, tong_tgxl=60),
             dict(block="B2", dung_hen_l1=9, tong_l1=10, dung_hen=10, tong=10))
    b = sl.theo_block(k).set_index("block")
    assert b.loc["B1", "dung_hen_l1_pct"] == 40.0 and b.loc["B1", "dung_hen_pct"] == 80.0 and b.loc["B1", "bao_tri_pct"] == 20.0 and b.loc["B1", "tgxl_tb"] == 10.0
    assert list(sl.theo_block(k)["block"]) == ["B1", "B2"]                                                          # thấp nhất (lần 1) trước


def test_tom_tat_khong_chia_cho_khong_khi_chua_co_file_kpi():
    s = sl.tom_tat(_ev(dict(so_hd="A")), _kpi(), NOW)
    assert s["so_ton"] == 1 and s["dung_hen_pct"] is None and s["tgxl_tb"] is None and s["bao_tri_pct"] is None
    assert sl.theo_block(_kpi()).empty


# ------------------------------------------------------------------ checklist, cáp LAN, KTV
def test_checklist_lap_lay_so_lan_tu_file_va_nhom_theo_phan_tu_loi():
    ev = _ev(dict(so_hd="A", loai="checklist", so_lan=3, thuoc_tinh=_tt(phan_tu_loi="Modem", nguyen_nhan_loi="Treo")),
             dict(so_hd="B", loai="checklist", so_lan=2, thuoc_tinh=_tt(phan_tu_loi="Modem")),
             dict(so_hd="C", loai="checklist", so_lan=2, thuoc_tinh=_tt()))
    assert list(sl.hop_dong_lap(ev)["so_hd"]) == ["A", "B", "C"] and list(sl.hop_dong_lap(ev, 3)["so_hd"]) == ["A"]
    n = sl.nhom_loi(ev, "phan_tu_loi").set_index("nhom")
    assert n.loc["Modem", "so"] == 2 and n.loc["Không ghi", "so"] == 1 and n.loc["Modem", "pct"] == 66.7


def test_cap_lan_dem_lan_wifi_va_ly_do():
    ev = _ev(dict(so_hd="A", loai="cap_lan", thuoc_tinh=_tt(active_by="LAN")),
             dict(so_hd="B", loai="cap_lan", thuoc_tinh=_tt(active_by="WIFI", nguyen_nhan="Khách thích wifi")),
             dict(so_hd="C", loai="cap_lan", thuoc_tinh=_tt(active_by="WIFI")))
    c = sl.cap_lan(ev)
    assert (c["tong"], c["lan"], c["wifi"], c["pct_lan"]) == (3, 1, 2, 33.3) and set(c["ly_do"]["nhom"]) == {"Khách thích wifi", "Không ghi"}
    assert sl.cap_lan(_ev(dict(loai="ton_kt")))["pct_lan"] is None


def test_theo_ktv_gom_ton_checklist_va_trien_khai_khong_dung_hen():
    ev = _ev(dict(so_hd="A", nguoi="k1", thuoc_tinh=_tt(hen_do="2026-11-14 08:00")), dict(so_hd="B", nguoi="k1"),
             dict(so_hd="C", loai="checklist", nguoi="k2", so_lan=2),
             dict(so_hd="D", loai="trien_khai", nguoi="k2", so_lan=3, chi_tiet="Triển khai: hẹn 3 lần, không đúng hẹn"))
    k = sl.theo_ktv(ev, NOW).set_index("ktv")
    assert k.loc["k1", "ton"] == 2 and k.loc["k1", "qua_do"] == 1 and k.loc["k2", "checklist"] == 1 and k.loc["k2", "khong_dung_hen"] == 1
    assert sl.theo_ktv(_ev(), NOW).empty


# ------------------------------------------------------------------ nhận định bằng luật
def test_nhan_dinh_dua_tren_nguong_va_xep_nghiem_trong_truoc():
    ev = _ev(dict(so_hd="A", thuoc_tinh=_tt(hen_do="2026-11-13 08:00")))
    nd = sl.nhan_dinh(ev, _kpi(dict(dung_hen_l1=3, tong_l1=10, dung_hen=9, tong=10)), NOW)
    muc = [x["muc"] for x in nd]
    assert muc[0] == "Nghiêm trọng" and any("quá mốc hẹn đỏ" in x["tieu_de"] for x in nd) and any("Đúng hẹn lần 1 chỉ 30" in x["tieu_de"] for x in nd)
    assert muc == sorted(muc, key=["Nghiêm trọng", "Cần chú ý", "Thông tin", "Tốt"].index)


def test_nhan_dinh_tot_khi_dung_hen_cao_va_khong_qua_moc_do():
    nd = sl.nhan_dinh(_ev(dict(so_hd="A")), _kpi(dict(dung_hen_l1=9, tong_l1=10, dung_hen=10, tong=10)), NOW)
    assert [x["muc"] for x in nd] == ["Tốt"]


# ------------------------------------------------------------------ đọc file KPI theo block
def test_doc_kpi_block_nhan_dien_bang_ten_cot_va_doc_cot_phan_tram_trung_ten():
    cot = ["Vùng", "Đối tác", "Block", "Lô", "Đúng hẹn lần 1", "%", "Đúng hẹn", "%", "Quá hẹn", "%", "TIN/PNC Tích hẹn", "%", "Khác TIN/PNC Tích hẹn", "%",
           "Tổng SLg lần 1", "Bảo trì quá 24H", "%", "Tổng SLg", "KH có CL", "Tổng TGXL(h)", "TGXL trung bình"]
    d = pd.DataFrame([["V", "DT", "Block A", "A.L1", "14", "63.64", "27", "93.1", "2", "6.9", "11", "37.9", "22", "75.8", "22", "6", "20.69", "29", "28", "433", "14.93"]], columns=cot)
    assert doc_kt.la_file_kpi(cot) and doc_kt.loai_file(cot) is None                                                  # không lẫn với 5 loại file theo mã hợp đồng
    k = doc_kt.kpi_block(d).iloc[0]
    assert (k["block"], k["lo"], k["dung_hen_l1"], k["dung_hen"], k["bao_tri_24h"], k["tong_l1"], k["tong"], k["tong_tgxl"]) == ("Block A", "A.L1", 14, 27, 6, 22, 29, 433)
    assert doc_kt.kpi_block(pd.DataFrame({"x": [1]})).empty


def test_doc_thu_muc_rong_hoac_khong_co_file_hop_le(tmp_path):
    (tmp_path / "hong.xlsx").write_bytes(b"khong phai xlsx")
    ev, kpi = doc_kt.doc_thu_muc(tmp_path)
    assert ev.empty and kpi.empty and list(ev.columns) == doc_kt.KT_COT


# ------------------------------------------------------------------ nguồn: thật (thư mục file) và minh hoạ
def test_du_lieu_that_chi_co_khi_dat_thu_muc_va_khong_co_thi_rong(monkeypatch, tmp_path):
    monkeypatch.delenv("LIEN_KHOI_NGUON", raising=False)
    monkeypatch.delenv("LIEN_KHOI_KT_THU_MUC", raising=False)
    assert nguon.thu_muc_kt() is None and nguon.kt().empty and nguon.kt_block().empty and not sl.co_du_lieu()
    monkeypatch.setenv("LIEN_KHOI_KT_THU_MUC", str(tmp_path / "khong_ton_tai"))
    assert nguon.thu_muc_kt() is None
    monkeypatch.setenv("LIEN_KHOI_KT_THU_MUC", str(tmp_path))
    assert nguon.thu_muc_kt() == tmp_path and nguon.kt().empty and list(nguon.kt().columns) == nguon.COT_KT


def test_bo_minh_hoa_co_kpi_block_va_cac_trang_kt_dung_duoc(monkeypatch):
    monkeypatch.setenv("LIEN_KHOI_NGUON", "demo")
    kpi = nguon.kt_block()
    assert len(kpi) > 10 and kpi["block"].str.fullmatch(r"Block \d{2}").all() and (kpi["vung"] == "Vùng minh hoạ").all()
    assert sl.co_du_lieu() and sl.bay_gio() == T("2026-11-14 12:00")
    s = sl.tom_tat(sl.su_kien(), kpi, sl.bay_gio())
    assert s["so_ton"] > 0 and 0 < s["dung_hen_pct"] <= 100 and s["hd_lap"] > 0
    from app.ui.pages import kt as trang_kt
    for duong_dan in trang_kt.TRANG:
        noi_dung, thanh = trang_kt.trang(duong_dan)
        assert noi_dung is not None and thanh
    assert "không tìm thấy" in trang_kt.trang("/kt/khong-co")[1][0].children[0].children.lower()


def test_trang_kt_bao_chua_co_du_lieu_khi_nguon_that_rong(monkeypatch):
    monkeypatch.delenv("LIEN_KHOI_NGUON", raising=False)
    monkeypatch.delenv("LIEN_KHOI_KT_THU_MUC", raising=False)
    from app.ui.pages import kt as trang_kt
    noi_dung, _ = trang_kt.trang("/kt")
    assert "chưa có số liệu" in str(noi_dung).lower()


def test_menu_kt_va_khoi_san_sang():
    from app.ui import khoi
    assert khoi.KHOI[khoi.KT]["san_sang"]
    duong_dan = {m[0] for _, ds in khoi.NAV_KT for m in ds}
    assert {"/kt", "/kt/su-co", "/kt/nhan-su"} <= duong_dan
    assert not {"/kt/ton", "/kt/phau", "/kt/trien-khai"} & duong_dan          # ẩn khỏi menu (trùng Báo cáo tồn / KPI), trang vẫn còn
    from app.ui.pages import kt as trang_kt
    assert {"/kt", "/kt/ton", "/kt/trien-khai", "/kt/su-co", "/kt/nhan-su", "/kt/phau", "/kt/cham-do-ai", "/kt/bao-cao-ton", "/kt/kpi"} == set(trang_kt.TRANG)
    assert {"/kt/cham-do-ai", "/kt/bao-cao-ton", "/kt/kpi"} <= duong_dan
    assert all(khoi.khoi_cua_duong_dan(p) == khoi.KT for p in trang_kt.TRANG)


@pytest.mark.parametrize("cach, mong_doi", [("do", {"A"}), ("xanh", {"A", "B"}), ("lau", {"C"}), ("tat_ca", {"A", "B", "C"})])
def test_loc_trang_ton(cach, mong_doi):
    from app.ui.pages import kt_ton
    ev = _ev(dict(so_hd="A", thuoc_tinh=_tt(hen_xanh="2026-11-13 10:00", hen_do="2026-11-13 12:00")), dict(so_hd="B", thuoc_tinh=_tt(hen_xanh="2026-11-14 08:00")),
             dict(so_hd="C", thoi_diem=T("2026-11-01 10:00")))
    assert set(kt_ton.loc(sl.ton(ev, NOW), cach)["so_hd"]) == mong_doi


# ------------------------------------------------------------------ Phễu triển khai và Chậm do ai
@pytest.mark.parametrize("ghi_chu, mong_doi", [
    ("nhà khách chưa có điện. hẹn tuần sau(KTMPN.A 09/11/2026 09:05:03 AM)", "khach"),
    ("kh đi hái cà hẹn lại", "khach"),
    ("khu vực nhà kh ko có trụ đảm bảo, đang chờ sale care kh trồng trụ", "ha_tang"),          # nguyên nhân gốc là hạ tầng, đứng trước chữ "chờ sale"
    ("kh vưc vươt cáp. sale đanng xin td", "ha_tang"),
    ("trời mưa ktv k xử lý kịp đã liên hệ hẹn lại kh", "ky_thuat"),                              # kỹ thuật đứng trước "hẹn lại" (hệ quả)
    ("đã tk cho khách..đang chờ xuất hoá đơn để khách báo lên cấp trên", "kinh_doanh"),
    ("hệ thống lỗi trùng sđt fpl", "he_thong"),
    ("Phân tuyến trên Inside KTMPN.A>>(KTMPN.A 09/11/2026 09:05:03 AM)", "chua_ghi"),             # chỉ có dòng phân tuyến: chưa có lý do
    ("Phân tuyến trên Inside KTMPN.A>>(x)\nkh nhà xây chưa xong", "khach"),                       # bỏ dòng phân tuyến, lấy dòng có nghĩa
    ("Micro-PTC-NOT-OK(A) - 10/11/2026 09:27:59;  -> ; Chuyển thi công-b-SaleClub: KH nhà xây;", "khach"),
    ("", "chua_ghi"), (None, "chua_ghi"), ("14.0123456, 108.0123456 - vị trí", "chua_ghi"),
])
def test_phan_loai_ghi_chu_theo_nguyen_nhan_goc(ghi_chu, mong_doi):
    assert doc_kt.phan_loai_ghi_chu(ghi_chu) == mong_doi


def test_moc_ghi_chu_doc_ca_gio_12_va_24():
    assert doc_kt._moc_ghi_chu("a(X 09/11/2026 09:05:03 AM)\nb(X 10/11/2026 11:47:25 PM)") == "2026-11-10 23:47"
    assert doc_kt._moc_ghi_chu("Chuyển thi công-x-13/11/2026 08:03:22-SaleClub") == "2026-11-13 08:03"
    assert doc_kt._moc_ghi_chu("12/11/2026 12:05:00 AM") == "2026-11-12 00:05" and doc_kt._moc_ghi_chu("không có giờ") == ""


def test_file_ton_chi_giu_nhan_khong_giu_nguyen_van_ghi_chu():
    d = pd.DataFrame([{"Số HĐ": "KTAAA0001", "TG tạo PTC": "07-11-2026 10:13:51", "Nhân sự": "K1", "Gói dịch vụ": "Giga", "Sale HĐ": "S1", "Tình trạng": "Đã nhận ca",
                       "Loại triển khai": "Triển khai mới", "TG Hẹn xanh": "16-11-2026 10:00:00", "TG Hẹn đỏ": " ",
                       "Ghi chú triển khai TIN/PNC": "kh hẹn lại, gọi 0912345678 không nghe máy(K1 09/11/2026 09:05:03 AM)\nPhân tuyến trên Inside K1>>(K1 08/11/2026 08:00:00 AM)"}])
    e = doc_kt.su_kien_tu_bang(d)
    tt = json.loads(e["thuoc_tinh"].iloc[0])
    assert tt["ly_do"] == "khach" and tt["ghi_chu_luc"] == "2026-11-09 09:05" and tt["so_lan_phan_tuyen"] == 1
    assert "0912345678" not in e["thuoc_tinh"].iloc[0] and "nghe máy" not in e["thuoc_tinh"].iloc[0]


def test_ton_gan_nhan_ly_do_va_do_im_lang():
    ev = _ev(dict(so_hd="A", thuoc_tinh=_tt(ly_do="khach", ghi_chu_luc="2026-11-14 08:00")),             # vừa ghi 4 giờ trước: không im lặng
             dict(so_hd="B", thuoc_tinh=_tt(ly_do="ha_tang", ghi_chu_luc="2026-11-12 12:00")),            # 48 giờ: im lặng
             dict(so_hd="C", thoi_diem=T("2026-11-14 06:00"), thuoc_tinh=_tt()),                          # chưa ghi, mới tồn 6 giờ: chưa tính
             dict(so_hd="D", thoi_diem=T("2026-11-10 06:00"), thuoc_tinh=_tt(so_lan_phan_tuyen=3)))       # chưa từng ghi, tồn 4 ngày: im lặng
    t = sl.ton(ev, NOW).set_index("so_hd")
    assert t.loc["A", "ly_do"] == "Khách hàng" and t.loc["C", "ly_do_ma"] == "chua_ghi" and t.loc["D", "phan_tuyen"] == 3 and t.loc["B", "gio_im_lang"] == 48.0
    il = sl.im_lang(sl.ton(ev, NOW))
    assert list(il["so_hd"]) == ["D", "B"] and il.set_index("so_hd").loc["D", "gio_im_lang"] > 48


def test_cham_do_ai_va_theo_giai_doan():
    ev = _ev(dict(so_hd="A", thuoc_tinh=_tt(tinh_trang="Đã phân công", ly_do="khach")), dict(so_hd="B", thuoc_tinh=_tt(tinh_trang="Đã nhận ca", ly_do="khach")),
             dict(so_hd="C", thuoc_tinh=_tt(tinh_trang="Đã nhận ca")), dict(so_hd="D", thuoc_tinh=_tt(tinh_trang="Đang xử lý", ly_do="kinh_doanh")))
    t = sl.ton(ev, NOW)
    cd = sl.cham_do_ai(t).set_index("ma")
    assert (cd.loc["khach", "so"], cd.loc["khach", "ty_le"], cd.loc["chua_ghi", "so"], cd.loc["kinh_doanh", "so"]) == (2, 50.0, 1, 1) and cd["so"].sum() == 4
    g = sl.theo_giai_doan(t).set_index("giai_doan")
    assert (g.loc["Đã phân công", "so"], g.loc["Đã nhận ca", "so"], g.loc["Đang xử lý", "so"], g.loc["Đã xử lý đang theo dõi", "so"]) == (1, 2, 1, 0)
    assert sl.cham_do_ai(sl.ton(_ev(), NOW)).empty


def test_khau_trien_khai_tinh_gio_tung_khau_va_bo_moc_dao_nguoc():
    mo = dict(tao_hd="2026-11-01 08:00", tao_ptc="2026-11-01 09:00", phan_cong="2026-11-01 10:00", checkin="2026-11-02 10:00", hoan_tat="2026-11-02 12:00", online="2026-11-02 11:00")
    ev = _ev(dict(so_hd="A", loai="trien_khai", so_lan=1, thuoc_tinh=_tt(**mo)), dict(so_hd="B", loai="trien_khai", so_lan=3, thuoc_tinh=_tt(**{**mo, "hoan_tat": "2026-11-02 08:00"})))
    ct, tom = sl.khau_trien_khai(ev)
    tom = tom.set_index("khau")
    assert tom.loc["Sale chuyển phiếu thi công", "trung_vi"] == 1.0 and tom.loc["Chờ KTV tới nhà khách", "trung_vi"] == 24.0
    t = tom.loc["Thi công tại nhà khách"]
    assert t["so_mau"] == 1 and t["trung_vi"] == 2.0                                   # hợp đồng B: hoàn tất trước check-in là mốc đảo ngược, bị bỏ khỏi khâu này
    assert tom.loc["Tổng: từ tạo hợp đồng tới online", "so_mau"] == 2
    assert sl.khau_trien_khai(_ev(dict(loai="ton_kt")))[1].empty


def test_ly_do_hen_lai_chi_tinh_hop_dong_tu_hai_lan_hen():
    ev = _ev(dict(so_hd="A", loai="trien_khai", so_lan=1, thuoc_tinh=_tt()), dict(so_hd="B", loai="trien_khai", so_lan=2, thuoc_tinh=_tt(nguyen_nhan_l2="Từ phía KH")),
             dict(so_hd="C", loai="trien_khai", so_lan=4, thuoc_tinh=_tt()))
    h = sl.ly_do_hen_lai(ev).set_index("nhom")["so"]
    assert dict(h) == {"Từ phía KH": 1, "Chưa ghi nguyên nhân": 1}


def test_nhan_dinh_cham_do_ai_khi_nhieu_ca_cho_khach_va_chua_ghi_ly_do():
    ev = _ev(*[dict(so_hd=f"K{i}", thuoc_tinh=_tt(ly_do="khach", ghi_chu_luc="2026-11-14 08:00")) for i in range(4)],
             *[dict(so_hd=f"X{i}", thuoc_tinh=_tt()) for i in range(8)])
    nd = sl.nhan_dinh(ev, _kpi(), NOW)
    tieu_de = " | ".join(x["tieu_de"] for x in nd)
    assert "chưa ghi lý do" in tieu_de and "chờ phía khách hàng" in tieu_de


def test_trang_phau_va_cham_do_ai_dung_duoc_tren_bo_minh_hoa(monkeypatch):
    monkeypatch.setenv("LIEN_KHOI_NGUON", "demo")
    from app.ui.pages import kt as trang_kt
    from app.ui.pages import kt_cham
    for duong_dan in ("/kt/phau", "/kt/cham-do-ai"):
        noi_dung, thanh = trang_kt.trang(duong_dan)
        assert noi_dung is not None and thanh
    ev = sl.su_kien()
    t = sl.ton(ev, sl.bay_gio(ev))
    assert t["ly_do_ma"].nunique() >= 3 and len(sl.im_lang(t)) > 0 and kt_cham.LOC[0][0] == "all"
    assert sl.cham_do_ai(t)["so"].sum() == len(t)


def test_trang_bao_cao_ton_doc_ban_chot_va_dung_duoc_moi_bang():
    from app.ui.pages import kt_bao_cao_ton as bct
    d = bct.du_lieu()
    assert d["chot_luc"] and {"tong", "block", "staff", "mt"} <= set(d["muc"])
    tq = d["muc"]["tong"]
    assert len(tq["the"]) == 7 and tq["bang"] and tq["nhan_dinh"]
    assert bct.layout() is not None
    for ma, m in d["muc"].items():
        assert (bct._ve_tong(m) if ma == "tong" else bct._ve_muc(ma, m)) is not None          # mục nào cũng vẽ được
        for b in m["bang"]:
            assert all(len(dong) == len(b["cot"]) for dong in b["dong"])
            assert not any(re.search(r"ghi ch|ttscb", c, re.I) for c in b["cot"])              # không giữ cột ghi chú tự do
    assert [t["nhom"] for t in d["muc"]["block"]["the"]][:1] == ["⏱ Quá giờ"]
    assert bct._so("796.000", tien=True) == 796000 and bct._so("10.20", tien=False) == 10.2 and bct._so("chưa có", tien=False) is None


def test_ban_chot_bao_cao_ton_da_an_danh():
    """File số liệu Báo cáo tồn nằm trong git nên tên NV, Điều hành, mã hợp đồng, mã thiết bị phải là mã giả."""
    from app.ui.pages import kt_bao_cao_ton as bct
    s = bct.FILE.read_text(encoding="utf-8")
    assert not re.search(r"\b(?!MH)[A-Z]{5}\d{4}\b|\bHU(EP|D\d|FD)", s)                                  # không còn mã HĐ / OLT thật
    ma = set(re.findall(r"(?<![A-Za-z0-9])(?=[A-Za-z0-9]*[A-Z]{2})[A-Za-z][A-Za-z0-9]{2,}(?![A-Za-z0-9])", s))
    viet_tat = {"KTV", "OLT", "TIN", "CSAT", "CSATBT", "CSATTK", "HIFPT", "HTBT", "NEW", "NSLD", "SWAP", "TKM", "WIFI", "RPT"}      # chữ viết tắt nghiệp vụ
    assert all(re.fullmatch(r"KTV\d{2}|MHAAA\d{4}|MHHDC\d{4}|OLT\d{2}", x) or x.upper() in viet_tat for x in ma), ma        # mọi chữ dạng mã đều là mã giả
    assert bct.du_lieu()["muc"]["tong"]["bieu_do"]["dh"]["labels"][0].startswith("Đội ")
    assert "HUETI" not in s.upper() and not re.search(r"\d{9,}", s)                                  # không còn mã hoá đơn / số dài thật


def test_trang_kpi_du_9_muc_va_da_an_danh():
    """Phần KPIs (web TAIHD) nằm trong git nên: đủ 9 mục, không còn cột thông tin khách, tên NV / mã HĐ / số điện thoại thật."""
    from app.ui.pages import kt_kpi
    import sys
    sys.path.insert(0, str(kt_kpi.THU_MUC.parents[2] / "scripts"))
    import trich_kpi as tk
    assert kt_kpi.meta()["chot_luc"] and kt_kpi.layout() is not None
    for ma, _ in kt_kpi.MUC:
        h = (kt_kpi.THU_MUC / f"{ma}.html").read_text(encoding="utf-8")
        assert kt_kpi.trang_html(ma).startswith("<!doctype html>")
        chu = tk.chu_hien(h)
        assert not re.search(r"(?i)hueti\.|\bHU(EP|[A-Z]{1,3}\d{4})|(?<!\d)\d{9,}|t[aà]i\s*hd", chu), ma
        tieu_de = " | ".join(re.sub(r"<[^>]+>", " ", x) for x in re.findall(r"<th[^>]*>(.*?)</th>", h, re.S))
        assert not re.search(r"(?i)khách hàng|địa chỉ|\bMAC\b|ghi chú|ghi nhận", tieu_de), ma          # cột thông tin khách đã bỏ
        assert "<script" not in h.lower() and "<button" not in h.lower()
