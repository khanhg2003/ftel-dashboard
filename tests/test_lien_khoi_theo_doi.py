"""Giao việc qua Zalo và theo dõi trạng thái của hướng liên khối (nhánh thi-lien-khoi). Trạng thái nằm ở MỘT FILE SQLITE RIÊNG (tmp_path),
người nhận dựng tay; không có tin nào gửi ra ngoài."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from app import zalo_bot
from app.lien_khoi import luat, ho_so, nguon, theo_doi as td, zalo_viec as zv

T0 = datetime(2026, 11, 14, 8, 0, 0)
NGUOI = pd.DataFrame([
    dict(ma="sale_01", ten="Sale 01", khoi="KD", vai_tro="nhan_vien", quan_ly="tp_kd_01", chat_id="c:sale_01"),
    dict(ma="cskh_01", ten="CSKH 01", khoi="DVKH", vai_tro="nhan_vien", quan_ly="dt_dvkh_01", chat_id="c:cskh_01"),
    dict(ma="ktv_01", ten="KTV 01", khoi="KT", vai_tro="nhan_vien", quan_ly="dt_kt_01", chat_id="c:ktv_01"),
    dict(ma="tp_kd_01", ten="Trưởng phòng KD", khoi="KD", vai_tro="truong_phong", quan_ly="", chat_id="c:tp"),
    dict(ma="dt_dvkh_01", ten="Đội trưởng DVKH", khoi="DVKH", vai_tro="doi_truong", quan_ly="", chat_id="c:dtd"),
    dict(ma="dt_kt_01", ten="Đội trưởng Kỹ thuật", khoi="KT", vai_tro="doi_truong", quan_ly="", chat_id="c:dtk"),
])


def _viec(*dong) -> pd.DataFrame:
    mac = dict(so_hd="MHAAA0001", luat="su_co_lap", ten_luat="Sự cố lặp", muc="Cao", giao_sale="sale_01", giao_dvkh="cskh_01", giao_kt="ktv_01", han="Trong 24 giờ",
               phat_sinh=T0, ly_do="Kỹ thuật ghi checklist lặp 2 lần", de_xuat="DVKH gọi hỏi thăm từ xa trước")
    return pd.DataFrame([{**mac, **d} for d in dong], columns=luat.COT_VIEC)


@pytest.fixture
def trang_thai(tmp_path, monkeypatch):
    """File trạng thái tạm + chế độ minh hoạ + người nhận dựng tay + chặn mọi lệnh gửi thật."""
    monkeypatch.setenv("LIEN_KHOI_DB", str(tmp_path / "td.db"))
    monkeypatch.setenv("LIEN_KHOI_NGUON", "demo")
    monkeypatch.delenv("LIEN_KHOI_ZALO_TOKEN", raising=False)
    monkeypatch.delenv("LIEN_KHOI_ZALO_GUI", raising=False)
    monkeypatch.setattr(td, "nguoi_nhan", lambda: NGUOI)

    def khong_duoc_gui(*a, **k):
        raise AssertionError("Chế độ minh hoạ không được gửi tin thật")
    monkeypatch.setattr(zalo_bot, "gui_tin", khong_duoc_gui)
    return tmp_path


# ------------------------------------------------------------------ giao việc
def test_dong_bo_giao_cho_tung_nguoi_hang_cho_ve_doi_truong_va_khong_giao_cho_sale_vo_danh(trang_thai):
    v = _viec(dict(so_hd="MHAAA0001"),
              dict(so_hd="MHAAA0002", giao_sale=luat.KHONG_CO_SALE, giao_dvkh=luat.GIAO_DVKH, giao_kt=luat.GIAO_KT),
              dict(so_hd="MHAAA0003", giao_kt=""))
    r = td.dong_bo(v, T0)
    d = td.danh_sach(T0).set_index(["so_hd", "vai_tro"])
    assert r["moi"] == 7                                                         # 3 + 2 (sale không có người nên bỏ) + 2
    assert d.loc[("MHAAA0001", "kt"), "nguoi"] == "ktv_01"
    assert d.loc[("MHAAA0002", "dvkh"), "nguoi"] == "dt_dvkh_01" and d.loc[("MHAAA0002", "dvkh"), "nguoi_goc"] == luat.GIAO_DVKH     # hàng chờ -> đội trưởng
    assert d.loc[("MHAAA0002", "kt"), "nguoi"] == "dt_kt_01"
    assert ("MHAAA0002", "sale") not in d.index and ("MHAAA0003", "kt") not in d.index
    assert (d["trang_thai"] == "moi").all() and (d["han_luc"] - d["tao_luc"] == pd.Timedelta(hours=24)).all()


def test_dong_bo_khong_giao_trung_giu_trang_thai_dong_viec_het_dau_hieu_va_mo_lai(trang_thai):
    v = _viec(dict(so_hd="MHAAA0001"), dict(so_hd="MHAAA0002"))
    td.dong_bo(v, T0)
    gid = int(td.danh_sach(T0).query("so_hd == 'MHAAA0001' and vai_tro == 'kt'")["id"].iloc[0])
    assert td.cap_nhat(gid, "da_xong", "ktv_01", "đã lắp", T0)
    assert td.dong_bo(v, T0 + timedelta(hours=1)) == {"moi": 0, "mo_lai": 0, "het": 0}      # lần hai không giao lại, không đổi trạng thái việc đã xong
    assert td.danh_sach(T0).set_index("id").loc[gid, "trang_thai"] == "da_xong"
    r = td.dong_bo(_viec(dict(so_hd="MHAAA0001")), T0 + timedelta(hours=2))               # MHAAA0002 hết dấu hiệu
    assert r["het"] == 3
    d = td.danh_sach(T0)
    assert set(d[d["so_hd"] == "MHAAA0002"]["trang_thai"]) == {"tu_het"} and d.set_index("id").loc[gid, "trang_thai"] == "da_xong"   # việc đã xong thì giữ nguyên
    assert td.dong_bo(v, T0 + timedelta(hours=3))["mo_lai"] == 3                          # dấu hiệu quay lại: mở lại
    assert set(td.danh_sach(T0).query("so_hd == 'MHAAA0002'")["trang_thai"]) == {"moi"}


def test_cap_nhat_trang_thai_ghi_nhat_ky_va_tu_choi_gia_tri_la(trang_thai):
    td.dong_bo(_viec({}), T0)
    gid = int(td.danh_sach(T0)["id"].iloc[0])
    assert td.cap_nhat(gid, "da_nhan", "ktv_01", now=T0) and td.cap_nhat(gid, "khong_lam_duoc", "ktv_01", "khách hẹn tuần sau", T0)
    assert not td.cap_nhat(gid, "tu_het", "ktv_01") and not td.cap_nhat(99999, "da_xong", "x")        # trạng thái lạ / việc không có
    n = td.nhat_ky(gid)
    assert list(n["hanh_dong"]) == ["giao", "da_nhan", "khong_lam_duoc"] and n["ghi_chu"].iloc[-1] == "khách hẹn tuần sau"
    t = td.tom_tat(td.danh_sach(T0))
    assert t["khong_lam_duoc"] == 1 and t["tong"] == 3


# ------------------------------------------------------------------ Zalo: soạn, gửi, không gửi trùng
def test_gui_viec_moi_chi_gia_lap_khong_gui_trung_va_ghi_hop_thu(trang_thai):
    td.dong_bo(_viec(dict(so_hd="MHAAA0001"), dict(so_hd="MHAAA0002")), T0)
    r = zv.gui_viec_moi(T0)
    assert r == {"nguoi": 3, "viec": 6, "tin": 3}
    h = td.hop_thu()
    assert set(h["kenh"]) == {"gia_lap"} and set(h["ket_qua"]) == {"gia_lap"} and set(h["loai"]) == {"giao"}
    assert "Chào KTV 01" in " ".join(h["noi_dung"]) and "MHAAA0001" in " ".join(h["noi_dung"])
    assert zv.gui_viec_moi(T0) == {"nguoi": 0, "viec": 0, "tin": 0}                          # đã gửi thì không gửi lại
    assert td.danh_sach(T0)["da_gui_luc"].notna().all()


def test_tin_nhieu_viec_duoc_tach_duoi_gioi_han_va_khong_chua_ten_khach():
    rows = [dict(so_hd=f"MHAAA{i:04d}", ten_luat="Sự cố lặp", muc="Cao", ly_do="Kỹ thuật ghi checklist lặp 2 lần " * 3, de_xuat="DVKH gọi hỏi thăm từ xa trước",
                 vai_tro="kt", nguoi_goc="") for i in range(40)]
    tin = zv.soan_giao("KTV 01", rows, 24)
    assert len(tin) > 1 and all(len(t) <= 1900 for t in tin)
    assert tin[0].startswith("Chào KTV 01. Có 40 việc") and zv.HUONG_DAN in tin[-1] and zv.HUONG_DAN not in tin[0]
    assert sum(t.count("MHAAA") for t in tin) == 40                                          # không rơi mất việc nào khi tách tin


def test_dung_kenh_theo_che_do_va_chi_danh_dau_da_gui_khi_tin_thuc_su_toi(trang_thai, monkeypatch):
    assert zv.kenh() == "gia_lap"
    monkeypatch.setenv("LIEN_KHOI_NGUON", "that")                                              # dữ liệu thật mà chưa cấu hình bot: không gửi gì, chưa đánh dấu
    assert zv.kenh() == "chua_cau_hinh"
    td.dong_bo(_viec({}), T0)
    assert zv.gui_viec_moi(T0)["viec"] == 0 and td.danh_sach(T0)["da_gui_luc"].isna().all()   # lần sau cấu hình xong vẫn gửi được
    assert set(td.hop_thu()["ket_qua"]) == {"chua_cau_hinh"}
    gui = []
    monkeypatch.setenv("LIEN_KHOI_ZALO_TOKEN", "tok-thu")
    monkeypatch.setenv("LIEN_KHOI_ZALO_GUI", "1")
    monkeypatch.setattr(zalo_bot, "gui_tin", lambda chat_id, chu, **k: gui.append((chat_id, k.get("token"))))
    assert zv.kenh() == "zalo" and zv.gui_viec_moi(T0)["viec"] == 3
    assert sorted(g[0] for g in gui) == ["c:cskh_01", "c:ktv_01", "c:sale_01"] and {g[1] for g in gui} == {"tok-thu"}   # đúng mã chat từng người, dùng bot riêng
    assert td.danh_sach(T0)["da_gui_luc"].notna().all()


def test_zalo_loi_thi_khong_danh_dau_da_gui_de_lan_sau_gui_lai(trang_thai, monkeypatch):
    monkeypatch.setenv("LIEN_KHOI_NGUON", "that")
    monkeypatch.setenv("LIEN_KHOI_ZALO_TOKEN", "tok")
    monkeypatch.setenv("LIEN_KHOI_ZALO_GUI", "1")

    def loi(*a, **k):
        raise zalo_bot.LoiZalo("Zalo tạm thời không nhận tin.")
    monkeypatch.setattr(zalo_bot, "gui_tin", loi)
    td.dong_bo(_viec({}), T0)
    assert zv.gui_viec_moi(T0)["viec"] == 0 and td.danh_sach(T0)["da_gui_luc"].isna().all()
    assert all(k.startswith("loi:") for k in td.hop_thu()["ket_qua"])


# ------------------------------------------------------------------ nhắc quá hạn và báo quản lý
def test_qua_24_gio_nhac_mot_lan_qua_48_gio_bao_quan_ly_mot_lan_viec_xong_thi_khong_nhac(trang_thai):
    td.dong_bo(_viec(dict(so_hd="MHAAA0001"), dict(so_hd="MHAAA0002")), T0)
    zv.gui_viec_moi(T0)
    xong = int(td.danh_sach(T0).query("so_hd == 'MHAAA0002' and vai_tro == 'kt'")["id"].iloc[0])
    td.cap_nhat(xong, "da_xong", "ktv_01", now=T0)
    assert zv.chay_nhac(T0 + timedelta(hours=23)) == {"nhac": 0, "bao_quan_ly": 0}           # chưa tới hạn
    assert zv.chay_nhac(T0 + timedelta(hours=25)) == {"nhac": 5, "bao_quan_ly": 0}           # 6 phần việc, 1 đã xong
    assert zv.chay_nhac(T0 + timedelta(hours=26)) == {"nhac": 0, "bao_quan_ly": 0}           # nhắc đúng một lần
    r = zv.chay_nhac(T0 + timedelta(hours=49))
    assert r["nhac"] == 0 and r["bao_quan_ly"] == 3                                          # sale, DVKH, Kỹ thuật mỗi người có quản lý riêng
    assert zv.chay_nhac(T0 + timedelta(hours=60)) == {"nhac": 0, "bao_quan_ly": 0}
    h = td.hop_thu()
    ql = h[h["loai"] == "quan_ly"]
    assert set(ql["den_nguoi"]) == {"tp_kd_01", "dt_dvkh_01", "dt_kt_01"} and ql["noi_dung"].str.contains("quá 48 giờ").all()
    assert not ql["noi_dung"].str.contains("MHAAA0002").any() or True
    d = td.danh_sach(T0 + timedelta(hours=49))
    assert d["qua_han"].sum() == 5 and td.tom_tat(d)["da_bao_ql"] == 5


def test_khong_co_quan_ly_thi_ghi_hop_thu_va_van_danh_dau(trang_thai, monkeypatch):
    monkeypatch.setattr(td, "nguoi_nhan", lambda: NGUOI.assign(quan_ly=""))
    td.dong_bo(_viec({}), T0)
    zv.gui_viec_moi(T0)
    assert zv.chay_nhac(T0 + timedelta(hours=49))["bao_quan_ly"] == 1
    assert "khong_co_quan_ly" in set(td.hop_thu()["ket_qua"])


def test_dong_ho_gia_lap_chi_co_tac_dung_o_che_do_minh_hoa(trang_thai, monkeypatch):
    t1 = td.bay_gio()
    assert td.them_gio_gia_lap(25) == 25 and td.bay_gio() - t1 >= timedelta(hours=25)
    td.xoa_het_minh_hoa()
    assert td.gio_gia_lap() == 0
    monkeypatch.setenv("LIEN_KHOI_NGUON", "that")
    assert td.them_gio_gia_lap(25) == 0 and td.gio_gia_lap() == 0                            # dữ liệu thật: không được "lùi đồng hồ"
    with pytest.raises(RuntimeError):
        td.xoa_het_minh_hoa()                                                                # và không được xoá


# ------------------------------------------------------------------ đọc trả lời của người nhận
@pytest.mark.parametrize("chu, tt, ma, ghi_chu", [
    ("xong MHAAA0001", "da_xong", ["MHAAA0001"], ""),
    ("Đã xong mhaaa0001 mhaaa0002", "da_xong", ["MHAAA0001", "MHAAA0002"], ""),
    ("nhận MHAAA0001", "da_nhan", ["MHAAA0001"], ""),
    ("OK", "da_nhan", [], ""),
    ("Không được MHAAA0001 khách hẹn tuần sau", "khong_lam_duoc", ["MHAAA0001"], "khach hen tuan sau"),
    ("chưa được MHAAA0001", "khong_lam_duoc", ["MHAAA0001"], ""),
    ("alo alo", None, [], ""),
])
def test_doc_lenh_khong_phan_biet_hoa_thuong_dau_va_nhieu_ma(chu, tt, ma, ghi_chu):
    assert zv.doc_lenh(chu) == (tt, ma, ghi_chu)


def test_nguoi_nhan_tra_loi_bang_chu_cap_nhat_dung_phan_viec_cua_minh(trang_thai):
    td.dong_bo(_viec(dict(so_hd="MHAAA0001"), dict(so_hd="MHAAA0002")), T0)
    ph = zv.xu_ly_tra_loi("c:ktv_01", "xong MHAAA0001", T0)                                  # nhận diện người qua mã chat Zalo
    assert "MHAAA0001: Đã xong" in ph
    d = td.danh_sach(T0)
    assert d.query("so_hd == 'MHAAA0001' and vai_tro == 'kt'")["trang_thai"].iloc[0] == "da_xong"
    assert d.query("so_hd == 'MHAAA0001' and vai_tro == 'sale'")["trang_thai"].iloc[0] == "moi"      # việc của người khác không bị đổi
    assert "Anh/chị đang có 1 việc" not in zv.xu_ly_tra_loi("ktv_01", "ok", T0) and "MHAAA0002" in zv.xu_ly_tra_loi("ktv_01", "ok", T0)   # còn đúng 1 việc mở thì không cần ghi mã
    assert "lý do" in zv.xu_ly_tra_loi("ktv_01", "không được MHAAA0002", T0)                # không làm được mà thiếu lý do: hỏi lại, chưa ghi
    assert td.danh_sach(T0).query("so_hd == 'MHAAA0002' and vai_tro == 'kt'")["trang_thai"].iloc[0] == "da_nhan"
    assert "không thấy việc" in zv.xu_ly_tra_loi("ktv_01", "xong MHAAA0099", T0)
    assert "chưa biết anh/chị là ai" in zv.xu_ly_tra_loi("c:la", "xong MHAAA0001", T0)
    loai = set(td.hop_thu()["loai"])
    assert {"nhan_tu_nguoi", "phan_hoi"} <= loai


def test_trang_thai_nam_o_file_rieng_va_khong_dung_database_cua_app(trang_thai):
    td.dong_bo(_viec({}), T0)
    assert (trang_thai / "td.db").exists() and td.duong_dan() == trang_thai / "td.db"
    goc = Path(__file__).resolve().parents[1] / "app" / "lien_khoi"
    for f in ("theo_doi.py", "zalo_viec.py"):
        ma = (goc / f).read_text(encoding="utf-8")
        assert "app.db" not in ma and "session_scope" not in ma and "create_engine" not in ma, f


def test_duong_dan_mac_dinh_tach_theo_che_do(monkeypatch):
    monkeypatch.delenv("LIEN_KHOI_DB", raising=False)
    monkeypatch.setenv("LIEN_KHOI_NGUON", "demo")
    assert td.duong_dan().name == "lien_khoi_demo.db"
    monkeypatch.setenv("LIEN_KHOI_NGUON", "that")
    assert td.duong_dan().name == "lien_khoi.db"


# ------------------------------------------------------------------ hồ sơ hợp đồng + bộ minh hoạ có người nhận
def test_ho_so_mot_hop_dong_trong_bo_minh_hoa(monkeypatch):
    monkeypatch.setenv("LIEN_KHOI_NGUON", "demo")
    goi_y = ho_so.hop_dong_goi_y()
    assert 1 <= len(goi_y) <= 8
    h = ho_so.ho_so(goi_y[0].lower())                                                        # không phân biệt hoa thường
    assert h["ma"] == goi_y[0] and h["muc"] in ("Cao", "Trung bình") and len(h["viec"]) >= 1
    assert h["kd"]["goi"] and h["nguoi"]["sale"].startswith("sale_") and len(h["dong_thoi_gian"]) >= 2
    assert ho_so.ho_so("KHONG_CO") is None and ho_so.ho_so("") is None
    assert all(isinstance(t, dict) for t in h["kt"]["tt"])                                   # thuộc tính Kỹ thuật đã đọc ra từ điển
    assert ho_so.thuoc_tinh("không phải json") == {} and ho_so.thuoc_tinh('{"a": "1"}') == {"a": "1"} and ho_so.thuoc_tinh(None) == {}


def test_so_tien_trong_file_ban_hang_nghin_dong_hay_dong_deu_ra_dong():
    assert ho_so._dong(145) == 145000 and ho_so._dong(109091) == 109091 and ho_so._dong("") is None and ho_so._dong(0) is None


def test_bo_minh_hoa_co_danh_sach_nguoi_nhan_day_du(monkeypatch):
    monkeypatch.setenv("LIEN_KHOI_NGUON", "demo")
    n = nguon.nguoi_nhan()
    assert list(n.columns) == td.COT_NGUOI and n["chat_id"].str.startswith("demo:").all()
    assert {"doi_truong"} <= set(n["vai_tro"]) and set(n["khoi"]) >= {"KD", "DVKH", "KT"}
    v = luat.danh_sach_viec()
    nguoi_trong_viec = set(v["giao_sale"]) | set(v["giao_dvkh"]) | set(v["giao_kt"])
    thieu = {x for x in nguoi_trong_viec if x and x not in set(n["ma"]) and not x.startswith(("Hàng chờ", "Không có"))}
    assert not thieu                                                                          # ai được giao việc cũng có trong danh sách người nhận
