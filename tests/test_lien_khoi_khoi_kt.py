"""Khối Kỹ thuật (nhánh thi-lien-khoi): số liệu từ file báo cáo Kỹ thuật, nhận định bằng luật, các trang /kt và nguồn dữ liệu thật / minh hoạ."""
from __future__ import annotations

import json

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
    assert {"/kt", "/kt/ton", "/kt/trien-khai", "/kt/su-co", "/kt/nhan-su"} <= duong_dan
    from app.ui.pages import kt as trang_kt
    assert {"/kt", "/kt/ton", "/kt/trien-khai", "/kt/su-co", "/kt/nhan-su"} == set(trang_kt.TRANG)
    assert all(khoi.khoi_cua_duong_dan(p) == khoi.KT for p in trang_kt.TRANG)


@pytest.mark.parametrize("cach, mong_doi", [("do", {"A"}), ("xanh", {"A", "B"}), ("lau", {"C"}), ("tat_ca", {"A", "B", "C"})])
def test_loc_trang_ton(cach, mong_doi):
    from app.ui.pages import kt_ton
    ev = _ev(dict(so_hd="A", thuoc_tinh=_tt(hen_xanh="2026-11-13 10:00", hen_do="2026-11-13 12:00")), dict(so_hd="B", thuoc_tinh=_tt(hen_xanh="2026-11-14 08:00")),
             dict(so_hd="C", thoi_diem=T("2026-11-01 10:00")))
    assert set(kt_ton.loc(sl.ton(ev, NOW), cach)["so_hd"]) == mong_doi
