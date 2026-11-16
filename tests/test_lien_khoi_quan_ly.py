"""Giao việc liên khối theo CẤP QUẢN LÝ (nhánh thi-lien-khoi): quản lý nhận MỘT tin tổng hợp việc của team, giao cho nhân viên trên app, quá hạn nhắc quản lý,
quá 48 giờ báo giám đốc chi nhánh. Trạng thái ở file sqlite tạm; người nhận dựng tay; không tin nào gửi ra ngoài."""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest

from app import zalo_bot
from app.lien_khoi import luat, nguon, theo_doi as td, zalo_viec as zv

T0 = datetime(2026, 11, 14, 8, 0, 0)
NGUOI = pd.DataFrame([
    dict(ma="sale_01", ten="Sale 01", khoi="KD", vai_tro="nhan_vien", quan_ly="tpkd_01", chat_id="c:s1"),
    dict(ma="sale_02", ten="Sale 02", khoi="KD", vai_tro="nhan_vien", quan_ly="tpkd_02", chat_id="c:s2"),
    dict(ma="cskh_01", ten="CSKH 01", khoi="DVKH", vai_tro="nhan_vien", quan_ly="tn_dvkh_01", chat_id="c:c1"),
    dict(ma="ktv_01", ten="KTV 01", khoi="KT", vai_tro="nhan_vien", quan_ly="dh_kt_01", chat_id="c:k1"),
    dict(ma="tpkd_01", ten="TPKD team 1", khoi="KD", vai_tro="truong_phong", quan_ly="gd_01", chat_id="c:tpkd1"),
    dict(ma="tpkd_02", ten="TPKD team 2", khoi="KD", vai_tro="truong_phong", quan_ly="gd_01", chat_id="c:tpkd2"),
    dict(ma="tn_dvkh_01", ten="Trưởng nhóm DVKH 1", khoi="DVKH", vai_tro="truong_nhom", quan_ly="tp_dvkh_01", chat_id="c:tn1"),
    dict(ma="dh_kt_01", ten="Điều hành KT 1", khoi="KT", vai_tro="dieu_hanh", quan_ly="tp_kt_01", chat_id="c:dh1"),
    dict(ma="tp_dvkh_01", ten="TP DVKH", khoi="DVKH", vai_tro="tp_khoi", quan_ly="gd_01", chat_id="c:tpd"),
    dict(ma="tp_kt_01", ten="TP Kỹ thuật", khoi="KT", vai_tro="tp_khoi", quan_ly="gd_01", chat_id="c:tpk"),
    dict(ma="gd_01", ten="Giám đốc chi nhánh", khoi="BGD", vai_tro="giam_doc", quan_ly="", chat_id="c:gd"),
])


def _viec(*dong) -> pd.DataFrame:
    mac = dict(so_hd="MHAAA0001", luat="su_co_lap", ten_luat="Sự cố lặp", muc="Cao", giao_sale="sale_01", giao_dvkh="cskh_01", giao_kt="ktv_01", han="Trong 24 giờ",
               phat_sinh=T0, ly_do="Kỹ thuật ghi checklist lặp 2 lần", de_xuat="DVKH gọi hỏi thăm từ xa trước")
    return pd.DataFrame([{**mac, **d} for d in dong], columns=luat.COT_VIEC)


@pytest.fixture
def ql(tmp_path, monkeypatch):
    monkeypatch.setenv("LIEN_KHOI_DB", str(tmp_path / "td.db"))
    monkeypatch.setenv("LIEN_KHOI_NGUON", "demo")
    monkeypatch.delenv("LIEN_KHOI_TIN_CHO", raising=False)
    monkeypatch.delenv("LIEN_KHOI_ZALO_TOKEN", raising=False)
    monkeypatch.delenv("LIEN_KHOI_ZALO_GUI", raising=False)
    monkeypatch.setattr(td, "nguoi_nhan", lambda: NGUOI)

    def khong_duoc_gui(*a, **k):
        raise AssertionError("Chế độ minh hoạ không được gửi tin thật")
    monkeypatch.setattr(zalo_bot, "gui_tin", khong_duoc_gui)
    return tmp_path


# ------------------------------------------------------------------ cấu trúc quản lý
def test_mac_dinh_tin_cho_quan_ly_va_doi_duoc(monkeypatch):
    monkeypatch.delenv("LIEN_KHOI_TIN_CHO", raising=False)
    assert zv.tin_cho() == "quan_ly"
    monkeypatch.setenv("LIEN_KHOI_TIN_CHO", "nhan_vien")
    assert zv.tin_cho() == "nhan_vien"
    monkeypatch.setenv("LIEN_KHOI_TIN_CHO", "bat_ky")
    assert zv.tin_cho() == "quan_ly"                                    # giá trị lạ thì về mặc định


def test_quan_ly_cua_pham_vi_va_giam_doc():
    assert td.quan_ly_cua("sale_01", NGUOI) == "tpkd_01" and td.quan_ly_cua("tp_dvkh_01", NGUOI) == "tp_dvkh_01"      # người nhận là quản lý (việc hàng chờ) thì chính họ
    assert td.quan_ly_cua("khong_co", NGUOI) == "" and td.giam_doc(NGUOI) == "gd_01"
    assert td.pham_vi("tp_dvkh_01", NGUOI) == {"tp_dvkh_01", "tn_dvkh_01"} and td.pham_vi("tpkd_01", NGUOI) == {"tpkd_01"}
    assert td.pham_vi("gd_01", NGUOI) >= {"tpkd_01", "tpkd_02", "tp_dvkh_01", "tn_dvkh_01", "tp_kt_01", "dh_kt_01"}
    assert td.doi_truong("DVKH", NGUOI) == "tp_dvkh_01" and td.doi_truong("KT", NGUOI) == "tp_kt_01"                     # hàng chờ về trưởng phòng khối
    chi_doi_truong = NGUOI.assign(vai_tro=NGUOI["vai_tro"].replace("tp_khoi", "doi_truong"))
    assert td.doi_truong("DVKH", chi_doi_truong) == "tp_dvkh_01"        # danh sách cũ chỉ có đội trưởng vẫn chạy


def test_danh_sach_viec_co_cot_quan_ly_hang_cho_ve_truong_phong_khoi(ql):
    td.dong_bo(_viec(dict(so_hd="MHAAA0001"), dict(so_hd="MHAAA0002", giao_dvkh=luat.GIAO_DVKH, giao_kt=luat.GIAO_KT)), T0)
    d = td.danh_sach(T0).set_index(["so_hd", "vai_tro"])
    assert d.loc[("MHAAA0001", "sale"), "quan_ly"] == "tpkd_01" and d.loc[("MHAAA0001", "dvkh"), "quan_ly"] == "tn_dvkh_01" and d.loc[("MHAAA0001", "kt"), "quan_ly"] == "dh_kt_01"
    assert d.loc[("MHAAA0002", "dvkh"), "quan_ly"] == "tp_dvkh_01" and d.loc[("MHAAA0002", "dvkh"), "nguoi_goc"] == luat.GIAO_DVKH
    assert d.loc[("MHAAA0002", "kt"), "quan_ly"] == "tp_kt_01"


# ------------------------------------------------------------------ tin tổng hợp cho quản lý
def test_moi_quan_ly_nhan_mot_tin_tong_hop_nhan_vien_khong_nhan_tin(ql):
    td.dong_bo(_viec(dict(so_hd="MHAAA0001"), dict(so_hd="MHAAA0002", giao_sale="sale_02")), T0)
    r = zv.gui_viec_moi(T0)
    assert r == {"nguoi": 4, "viec": 6, "tin": 4}                        # tpkd_01, tpkd_02, tn_dvkh_01, dh_kt_01
    h = td.hop_thu()
    assert set(h["den_nguoi"]) == {"tpkd_01", "tpkd_02", "tn_dvkh_01", "dh_kt_01"} and set(h["loai"]) == {"giao"} and set(h["kenh"]) == {"gia_lap"}
    tin = h.set_index("den_nguoi")["noi_dung"]
    assert "Chào TPKD team 1" in tin["tpkd_01"] and "2 việc" in tin["tn_dvkh_01"] and "MHAAA0001" in tin["tn_dvkh_01"] and "MHAAA0002" in tin["tn_dvkh_01"]
    assert "Sự cố lặp (2)" in tin["tn_dvkh_01"] and "mức Cao" in tin["tn_dvkh_01"] and zv.GHI_CHU_APP in tin["tn_dvkh_01"]
    assert "xong MÃ" not in " ".join(tin) and "nhận MÃ" not in " ".join(tin)             # quản lý không phải trả lời từng mã trên Zalo
    assert all(len(t) <= zv.TOI_DA_KY_TU for t in tin)
    assert zv.gui_viec_moi(T0) == {"nguoi": 0, "viec": 0, "tin": 0}                      # đã gửi thì không gửi lại
    assert td.danh_sach(T0)["da_gui_luc"].notna().all()


def test_tin_tong_hop_ghi_viec_hang_cho_la_chua_co_nguoi_phu_trach_va_gioi_han_viec_cao(ql):
    dong = [dict(so_hd=f"MHAAA{i:04d}", giao_dvkh=luat.GIAO_DVKH) for i in range(1, 9)]
    td.dong_bo(_viec(*dong, dict(so_hd="MHAAA0099")), T0)
    zv.gui_viec_moi(T0)
    tin = td.hop_thu().set_index("den_nguoi").loc["tp_dvkh_01", "noi_dung"]
    assert "Chưa có người phụ trách (8)" in tin and "... và 3 việc mức Cao nữa" in tin and tin.count("MHAAA") == zv.TOI_DA_VIEC_CAO
    assert "8 việc" in tin and "nan" not in tin and "None" not in tin


def test_nhan_vien_chua_co_quan_ly_thi_viec_ve_giam_doc(ql, monkeypatch):
    mo_coi = pd.concat([NGUOI, pd.DataFrame([dict(ma="sale_09", ten="Sale 09", khoi="KD", vai_tro="nhan_vien", quan_ly="", chat_id="c:s9")])], ignore_index=True)
    monkeypatch.setattr(td, "nguoi_nhan", lambda: mo_coi)
    td.dong_bo(_viec(dict(so_hd="MHAAA0001", giao_sale="sale_09", giao_dvkh="", giao_kt="")), T0)
    assert zv.gui_viec_moi(T0)["nguoi"] == 1
    assert list(td.hop_thu()["den_nguoi"]) == ["gd_01"]


# ------------------------------------------------------------------ nhắc quản lý, báo giám đốc chi nhánh
def test_qua_24_gio_nhac_quan_ly_qua_48_gio_bao_giam_doc_mot_tin_mot_lan(ql):
    td.dong_bo(_viec(dict(so_hd="MHAAA0001"), dict(so_hd="MHAAA0002", giao_sale="sale_02")), T0)
    zv.gui_viec_moi(T0)
    assert zv.chay_nhac(T0 + timedelta(hours=10)) == {"nhac": 0, "bao_quan_ly": 0, "viec_bao": 0}
    r = zv.chay_nhac(T0 + timedelta(hours=25))
    assert r["nhac"] == 6 and r["bao_quan_ly"] == 0
    h = td.hop_thu()
    nhac = h[h["loai"] == "nhac"]
    assert set(nhac["den_nguoi"]) == {"tpkd_01", "tpkd_02", "tn_dvkh_01", "dh_kt_01"}            # nhắc QUẢN LÝ, không nhắc nhân viên
    assert nhac["noi_dung"].str.contains("quá 24 giờ").all() and nhac["noi_dung"].str.contains("chưa giao cho ai").all()
    assert zv.chay_nhac(T0 + timedelta(hours=26))["nhac"] == 0                                    # mỗi việc chỉ nhắc một lần
    r = zv.chay_nhac(T0 + timedelta(hours=49))
    assert r == {"nhac": 0, "bao_quan_ly": 1, "viec_bao": 6}
    ql_tin = td.hop_thu()
    ql_tin = ql_tin[ql_tin["loai"] == "quan_ly"]
    assert list(ql_tin["den_nguoi"]) == ["gd_01"] and ql_tin["noi_dung"].iloc[0].startswith("Báo giám đốc chi nhánh: có 6 việc quá 48 giờ")
    assert all(t in ql_tin["noi_dung"].iloc[0] for t in ("TPKD team 1", "TPKD team 2", "Trưởng nhóm DVKH 1", "Điều hành KT 1"))
    assert zv.chay_nhac(T0 + timedelta(hours=60))["bao_quan_ly"] == 0


def test_viec_da_xong_khong_bi_nhac_va_khong_bao_giam_doc(ql):
    td.dong_bo(_viec(dict(so_hd="MHAAA0001", giao_dvkh="", giao_kt="")), T0)
    zv.gui_viec_moi(T0)
    td.cap_nhat(int(td.danh_sach(T0).iloc[0]["id"]), "da_xong", "tpkd_01", "", T0 + timedelta(hours=5))
    assert zv.chay_nhac(T0 + timedelta(hours=50)) == {"nhac": 0, "bao_quan_ly": 0, "viec_bao": 0}


def test_khong_co_giam_doc_thi_ghi_hop_thu_va_van_danh_dau(ql, monkeypatch):
    monkeypatch.setattr(td, "nguoi_nhan", lambda: NGUOI[NGUOI["vai_tro"] != "giam_doc"].reset_index(drop=True))
    td.dong_bo(_viec(dict(so_hd="MHAAA0001", giao_dvkh="", giao_kt="")), T0)
    zv.gui_viec_moi(T0)
    zv.chay_nhac(T0 + timedelta(hours=49))
    h = td.hop_thu()
    assert "(chưa có giám đốc)" in set(h["den_nguoi"]) and td.danh_sach(T0)["bao_quan_ly_luc"].notna().all()


# ------------------------------------------------------------------ quản lý giao việc trên app
def test_giao_viec_nhieu_cong_mot_lan_ghi_nguoi_duoc_giao_va_nhat_ky(ql):
    td.dong_bo(_viec(dict(so_hd="MHAAA0001"), dict(so_hd="MHAAA0002")), T0)
    d = td.danh_sach(T0)
    ids = [int(i) for i in d.loc[d["vai_tro"] == "sale", "id"]]
    td.cap_nhat(ids[1], "da_xong", "tpkd_01", "", T0)
    n = td.giao_viec(ids, "sale_01", "tpkd_01", T0 + timedelta(hours=2))
    assert n == 1                                                                           # việc đã xong không bị giao lại
    d = td.danh_sach_day_du(T0 + timedelta(hours=3)).set_index("id")
    assert d.loc[ids[0], "giao_cho"] == "sale_01" and d.loc[ids[0], "trang_thai"] == "da_nhan" and d.loc[ids[0], "cap_nhat_boi"] == "tpkd_01"
    assert d.loc[ids[1], "trang_thai"] == "da_xong" and pd.isna(d.loc[ids[1], "giao_cho"])
    assert pd.Timestamp(d.loc[ids[0], "phan_hoi_luc"]) == pd.Timestamp(T0 + timedelta(hours=2))      # giao việc tính là phản hồi của quản lý
    nk = td.nhat_ky(ids[0])
    assert "giao_cho" in list(nk["hanh_dong"]) and list(nk["hanh_dong"]).count("giao") == 1


def test_trang_theo_doi_giao_hang_loat_va_loc_theo_pham_vi_quan_ly(ql):
    from app.ui.pages import lienkhoi_td as ui
    td.dong_bo(_viec(dict(so_hd="MHAAA0001"), dict(so_hd="MHAAA0002", giao_dvkh=luat.GIAO_DVKH)), T0)
    d = td.danh_sach(T0)
    assert set(ui._pham_vi_quan_ly(d, "all")["quan_ly"]) == set(d["quan_ly"])
    tp = ui._pham_vi_quan_ly(d, "tp_dvkh_01")
    assert set(tp["quan_ly"]) == {"tp_dvkh_01", "tn_dvkh_01"} and set(ui._pham_vi_quan_ly(d, "tn_dvkh_01")["quan_ly"]) == {"tn_dvkh_01"}
    chon = [{"id": int(i)} for i in d.loc[d["quan_ly"] == "tn_dvkh_01", "id"]] + [{"id": int(i)} for i in d.loc[d["quan_ly"] == "tpkd_01", "id"]]
    assert "Chọn người" in ui._hanh_dong("lk-td-giao", chon, "", "", "", None, "tpkd_01")
    assert "Chọn ít nhất" in ui._hanh_dong("lk-td-giao", [], "", "", "", "sale_01", "tpkd_01")
    assert ui._hanh_dong("lk-td-giao", chon, "", "", "", "cskh_01", "tn_dvkh_01").startswith("Đã giao 3 phần việc cho cskh_01")
    assert ui._hanh_dong("lk-td-khong", chon, "", "", "", None, "tn_dvkh_01").startswith("Ghi lý do")
    assert ui._hanh_dong("lk-td-xong", chon, "", "", "", None, "tn_dvkh_01").startswith("Đã ghi 3 phần việc")
    kq = td.danh_sach(T0).set_index("id")
    assert (kq.loc[[c["id"] for c in chon], "trang_thai"] == "da_xong").all() and (kq.loc[[c["id"] for c in chon], "cap_nhat_boi"] == "tn_dvkh_01").all()


def test_quan_ly_tra_loi_tren_zalo_cap_nhat_viec_cua_ca_team_tuy_chon(ql):
    td.dong_bo(_viec(dict(so_hd="MHAAA0001")), T0)
    assert "Đã ghi nhận" in zv.xu_ly_tra_loi("tpkd_01", "xong MHAAA0001", T0 + timedelta(hours=3))
    d = td.danh_sach(T0).set_index("vai_tro")
    assert d.loc["sale", "trang_thai"] == "da_xong" and d.loc["dvkh", "trang_thai"] == "moi"             # chỉ việc của team mình
    assert "không có việc nào" in zv.xu_ly_tra_loi("tpkd_02", "xong", T0)


# ------------------------------------------------------------------ bộ minh hoạ + mô phỏng
def test_mo_phong_quan_ly_giao_viec_va_so_do_theo_team(tmp_path, monkeypatch):
    from app.bo_nho import xoa
    from app.lien_khoi import hieu_qua as hq, mo_phong as mp
    monkeypatch.setenv("LIEN_KHOI_NGUON", "demo")
    monkeypatch.setenv("LIEN_KHOI_DB", str(tmp_path / "td.db"))
    monkeypatch.delenv("LIEN_KHOI_TIN_CHO", raising=False)
    xoa()
    mp.chuan_bi_demo()
    d = td.danh_sach_day_du()
    ls = d[d["mo_phong"] == 1]
    giao = ls[ls["giao_cho"].notna()]
    assert len(giao) > 100 and (giao["giao_cho"] == giao["nguoi"]).all() and ls["quan_ly"].ne("").all()
    t = hq.tong_hop(hq.chuan_bi(d, td.bay_gio()), "quan_ly")
    assert len(t) >= 8 and t["giao"].sum() == len(d[d["trang_thai"] != "tu_het"])                   # mọi phần việc thuộc một quản lý
    r = zv.gui_viec_moi()
    assert 0 < r["nguoi"] <= 13 and r["viec"] == int(((d["mo_phong"] == 0) & d["dang_mo"]).sum())    # chỉ việc thật, và chỉ quản lý (tối đa 13 người) nhận tin
    assert {"truong_phong", "truong_nhom", "dieu_hanh", "tp_khoi"} >= set(nguon.nguoi_nhan().set_index("ma").loc[list(td.hop_thu()["den_nguoi"]), "vai_tro"])
    td.them_gio_gia_lap(25)
    mp.tien_thoi_gian()
    r = zv.chay_nhac()
    assert r["nhac"] > 0
    td.them_gio_gia_lap(24)
    mp.tien_thoi_gian()
    assert zv.chay_nhac()["bao_quan_ly"] == 1 and list(td.hop_thu(1)["den_nguoi"]) == ["gd_01"]
    xoa()


# ------------------------------------------------------------------ chế độ THỬ ZALO: dữ liệu minh hoạ, gửi thật chỉ tới người thử đã đăng ký
@pytest.fixture
def thu_zalo(ql, tmp_path, monkeypatch):
    f = tmp_path / "zalo_thu.json"
    monkeypatch.setenv("LIEN_KHOI_ZALO_THU", str(f))
    gui = []
    monkeypatch.setattr(zalo_bot, "gui_tin", lambda chat_id, noi_dung, *a, **k: gui.append((chat_id, noi_dung, k.get("token"))))
    return f, gui


def _dat(monkeypatch, token="tok-gia", gui="1"):
    monkeypatch.setenv("LIEN_KHOI_ZALO_TOKEN", token) if token else monkeypatch.delenv("LIEN_KHOI_ZALO_TOKEN", raising=False)
    monkeypatch.setenv("LIEN_KHOI_ZALO_GUI", gui) if gui else monkeypatch.delenv("LIEN_KHOI_ZALO_GUI", raising=False)


def test_thu_zalo_chi_bat_khi_du_ba_dieu_kien(thu_zalo, monkeypatch):
    f, _ = thu_zalo
    _dat(monkeypatch)
    assert zv.kenh() == "gia_lap"                                          # chưa có file đăng ký
    f.write_text('{"KD": "chat-kd", "KHAC": "x", "DVKH": ""}', encoding="utf-8")
    assert zv.dai_dien_thu() == {"KD": "chat-kd"}                          # bỏ khoá lạ và giá trị rỗng
    assert zv.kenh() == "zalo_thu"
    _dat(monkeypatch, token=None)
    assert zv.kenh() == "gia_lap"                                          # thiếu token
    _dat(monkeypatch, gui=None)
    assert zv.kenh() == "gia_lap"                                          # thiếu LIEN_KHOI_ZALO_GUI=1
    _dat(monkeypatch)
    f.write_text("không phải json", encoding="utf-8")
    assert zv.dai_dien_thu() == {} and zv.kenh() == "gia_lap"              # file hỏng thì coi như chưa đăng ký


def test_thu_zalo_gui_that_chi_cho_dai_dien_con_quan_ly_khac_chi_ghi_hop_thu(thu_zalo, monkeypatch):
    f, gui = thu_zalo
    _dat(monkeypatch)
    f.write_text('{"KD": "chat-kd", "DVKH": "chat-dvkh", "KT": "chat-kt", "BGD": "chat-bgd"}', encoding="utf-8")
    td.dong_bo(_viec(dict(so_hd="MHAAA0001"), dict(so_hd="MHAAA0002", giao_sale="sale_02")), T0)
    zv.gui_viec_moi(T0)
    assert {c for c, _, _ in gui} == {"chat-kd", "chat-dvkh", "chat-kt"}                    # chỉ tpkd_01, tn_dvkh_01, dh_kt_01; tpkd_02 không được gửi thật
    assert len(gui) == 3 and all(t == "tok-gia" for _, _, t in gui)
    assert all(n.startswith("[THỬ NGHIỆM · dữ liệu minh hoạ") and "Tin gửi thay cho" in n for _, n, _ in gui)
    h = td.hop_thu().set_index("den_nguoi")
    assert h.loc["tpkd_01", "kenh"] == "zalo_thu" and h.loc["tpkd_01", "ket_qua"] == "ok" and h.loc["tpkd_01", "chat_id"] == "chat-kd"
    assert h.loc["tpkd_02", "kenh"] == "gia_lap" and h.loc["tpkd_02", "chat_id"] == ""
    assert td.danh_sach(T0)["da_gui_luc"].notna().all()                                      # tin giả lập cũng tính là đã gửi: không gửi lại
    gui.clear()
    zv.chay_nhac(T0 + timedelta(hours=49))
    assert [c for c, _, _ in gui if c == "chat-bgd"] and "Báo giám đốc chi nhánh" in [n for c, n, _ in gui if c == "chat-bgd"][0]


def test_thu_zalo_chua_dang_ky_khoi_nao_thi_khoi_do_chi_ghi_hop_thu_va_loi_gui_thi_gui_lai(thu_zalo, monkeypatch):
    f, gui = thu_zalo
    _dat(monkeypatch)
    f.write_text('{"KD": "chat-kd"}', encoding="utf-8")
    td.dong_bo(_viec(dict(so_hd="MHAAA0001")), T0)
    zv.gui_viec_moi(T0)
    assert [c for c, _, _ in gui] == ["chat-kd"]                                              # DVKH, KT chưa đăng ký: không gửi thật cho ai

    def loi(*a, **k):
        raise zalo_bot.LoiZalo("Zalo từ chối (thử)")
    monkeypatch.setattr(zalo_bot, "gui_tin", loi)
    td.dong_bo(_viec(dict(so_hd="MHAAA0002", giao_dvkh="", giao_kt="")), T0)
    r = zv.gui_viec_moi(T0)
    assert r["nguoi"] == 0                                                                    # gửi lỗi: không đánh dấu đã gửi để lượt sau gửi lại
    assert td.danh_sach(T0).set_index("so_hd").loc["MHAAA0002", "da_gui_luc"] is pd.NaT or pd.isna(td.danh_sach(T0).set_index("so_hd").loc["MHAAA0002", "da_gui_luc"])
    assert "loi" in " ".join(td.hop_thu()["ket_qua"])


def test_script_dang_ky_thu_zalo_doc_chu_khoi_khong_dau_va_ghi_file(thu_zalo, monkeypatch):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("lk_zalo_thu", Path(__file__).resolve().parents[1] / "scripts" / "lien_khoi_zalo_thu.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert [m._vai_tu_tin(x) for x in ("KD", " dvkh ", "kt", "BGĐ", "bgd xin chào", "hello", "")] == ["KD", "DVKH", "KT", "BGD", "BGD", "", ""]
    assert m._che("abcdefghij") == "abc…hij" and m._che("abc") == "abc"
    f, _ = thu_zalo
    m._ghi({"KD": "x1"})
    assert zv.dai_dien_thu() == {"KD": "x1"} and m.main("go") == 0 and not f.exists()
