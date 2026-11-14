"""Tab Hiệu quả của hướng liên khối (nhánh thi-lien-khoi): số đo cho quản lý, lịch sử mô phỏng của bản minh hoạ, mốc so sánh.
Số đo là hàm thuần nên kiểm bằng bảng dựng tay; phần ghi dùng file trạng thái tạm (tmp_path), không đụng gì khác."""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest

from app.lien_khoi import hieu_qua as hq
from app.lien_khoi import mo_phong as mp
from app.lien_khoi import theo_doi as td
from app.ui.pages import lienkhoi_hq

T0 = datetime(2026, 11, 14, 12, 0, 0)


def _h(gio: float) -> datetime:
    return T0 + timedelta(hours=gio)


def _d(*dong) -> pd.DataFrame:
    mac = dict(id=1, so_hd="MHAAA0001", luat="su_co_lap", ten_luat="Sự cố lặp", vai_tro="kt", nguoi="ktv_01", trang_thai="moi", tao_luc=_h(-2), han_luc=_h(22),
               cap_nhat_luc=pd.NaT, phan_hoi_luc=pd.NaT, bao_quan_ly_luc=pd.NaT, ghi_chu=None, mo_phong=0)
    return pd.DataFrame([{**mac, "id": i + 1, **d} for i, d in enumerate(dong)])


def _mau() -> pd.DataFrame:
    return _d(dict(trang_thai="da_xong", tao_luc=_h(-30), han_luc=_h(-6), cap_nhat_luc=_h(-20), phan_hoi_luc=_h(-29)),            # xong đúng hạn (10 giờ)
              dict(trang_thai="da_xong", tao_luc=_h(-60), han_luc=_h(-36), cap_nhat_luc=_h(-10), phan_hoi_luc=_h(-52)),            # xong trễ (50 giờ)
              dict(trang_thai="khong_lam_duoc", tao_luc=_h(-30), han_luc=_h(-6), cap_nhat_luc=_h(-25), ghi_chu="Khách hẹn tuần sau"),
              dict(trang_thai="moi", tao_luc=_h(-30), han_luc=_h(-6), bao_quan_ly_luc=_h(-1)),                                      # mở, quá hạn, chưa ai phản hồi
              dict(trang_thai="moi", tao_luc=_h(-2), han_luc=_h(22)),                                                              # còn trong hạn: chưa tính
              dict(trang_thai="tu_het"))


# ------------------------------------------------------------------ cách tính
def test_so_do_dem_dung_tinh_theo_viec_da_toi_han_va_bo_viec_het_dau_hieu():
    s = hq.so_do(hq.chuan_bi(_mau(), T0))
    assert s["giao"] == 5 and s["xong"] == 2 and s["dung_han"] == 1 and s["khong"] == 1 and s["qua_han_mo"] == 1
    assert s["den_han"] == 4 and s["ty_le"] == 25.0                                       # việc còn trong hạn và việc hết dấu hiệu không vào mẫu số
    assert s["gio_xu_ly"] == 30.0 and s["gio_xu_ly_tb"] == 30.0                           # (10 + 50) / 2
    assert s["phan_hoi"] == 4.5 and s["phan_hoi_nhanh"] == 50.0                            # 1 giờ và 8 giờ: một nửa trong 4 giờ
    assert s["da_bao_ql"] == 1 and s["chua_phan_hoi"] == 1


def test_khong_co_du_lieu_thi_so_do_rong_va_nhan_dinh_noi_chua_co():
    s = hq.so_do(hq.chuan_bi(_d().iloc[0:0], T0))
    assert s["giao"] == 0 and s["ty_le"] is None
    assert hq.nhan_dinh(_d().iloc[0:0]) == ["Chưa có phần việc nào trong kỳ này."]


def test_tong_hop_theo_khoi_doi_ten_vai_tro_va_nhom_it_du_lieu_khong_co_ty_le():
    d = hq.chuan_bi(_mau(), T0)
    t = hq.tong_hop(d, "vai_tro")
    assert list(t["nhom"]) == ["Kỹ thuật"] and t["giao"].iloc[0] == 5
    assert t["ty_le"].iloc[0] == 25.0                                                      # 4 việc đã tới hạn = đúng ngưỡng tối thiểu
    nhieu = hq.chuan_bi(_d(*[dict(trang_thai="da_xong", tao_luc=_h(-30), han_luc=_h(-6), cap_nhat_luc=_h(-20), nguoi="ktv_09")] * 3, dict(nguoi="ktv_01", trang_thai="da_xong",
                                                                                                                                     tao_luc=_h(-30), han_luc=_h(-6), cap_nhat_luc=_h(-20))), T0)
    ng = hq.tong_hop(nhieu, "nguoi").set_index("nhom")
    assert pd.isna(ng.loc["ktv_01", "ty_le"]) and pd.isna(ng.loc["ktv_09", "ty_le"])        # dưới 4 việc đã tới hạn: ít dữ liệu


def test_xu_huong_theo_ngay_gio_viet_nam():
    d = hq.chuan_bi(_d(*[dict(trang_thai="da_xong", tao_luc=datetime(2026, 11, 10, 18, 0), han_luc=datetime(2026, 11, 11, 18, 0), cap_nhat_luc=datetime(2026, 11, 10, 20, 0))] * 4,
                       dict(trang_thai="da_xong", tao_luc=datetime(2026, 11, 11, 2, 0), han_luc=datetime(2026, 11, 12, 2, 0), cap_nhat_luc=datetime(2026, 11, 11, 5, 0))), T0)
    x = hq.xu_huong(d)
    assert x["ngay"].dt.strftime("%d/%m").tolist() == ["11/11", "11/11"] or x["ngay"].dt.strftime("%d/%m").tolist() == ["11/11"]
    assert x["giao"].sum() == 5 and x["xong"].sum() == 5


def test_nhan_dinh_noi_khoi_chenh_nhau_nguoi_cham_va_viec_chua_phan_hoi():
    xong = dict(trang_thai="da_xong", tao_luc=_h(-30), han_luc=_h(-6), cap_nhat_luc=_h(-20))
    tre = dict(trang_thai="moi", tao_luc=_h(-30), han_luc=_h(-6))
    d = hq.chuan_bi(_d(*[{**xong, "vai_tro": "sale", "nguoi": "sale_01"}] * 8, *[{**tre, "vai_tro": "dvkh", "nguoi": "cskh_01"}] * 5, *[{**xong, "vai_tro": "dvkh", "nguoi": "cskh_02"}] * 3), T0)
    nd = " ".join(hq.nhan_dinh(d))
    assert "Khối thấp nhất là DVKH" in nd and "cao nhất là Sale" in nd
    assert "cskh_01 (5 việc)" in nd and "chưa phản hồi lần nào" in nd


def test_so_voi_moc_chi_noi_khi_co_moc_va_dung_huong_tang_giam():
    s = {"gio_xu_ly": 12.0, "ty_le": 70.0}
    assert hq.so_voi_moc(s, {}) == []
    kq = hq.so_voi_moc(s, {"gio_xu_ly": 40.0, "ty_le_dung_han": 35.0})
    assert "giảm 70%" in kq[0] and "tăng 35 điểm" in kq[1]
    assert "tăng" in hq.so_voi_moc({"gio_xu_ly": 50.0, "ty_le": None}, {"gio_xu_ly": 40.0})[0]


# ------------------------------------------------------------------ lịch sử mô phỏng
@pytest.fixture
def trang_thai(tmp_path, monkeypatch):
    monkeypatch.setenv("LIEN_KHOI_DB", str(tmp_path / "td.db"))
    monkeypatch.setenv("LIEN_KHOI_NGUON", "demo")
    return tmp_path


def test_lich_su_mo_phong_co_dinh_hat_giong_va_dung_quy_tac_thoi_gian(trang_thai):
    ds = td.nguoi_nhan()
    a, b = mp.dung_lich_su(ds, T0), mp.dung_lich_su(ds, T0)
    assert a == b and len(a) > 500                                                          # chạy lại ra đúng cùng kết quả
    assert all(r["so_hd"].startswith("MHLS") for r in a)                                    # mã mô phỏng không trùng bộ minh hoạ MHAAA
    for r in a:
        tao, han = datetime.fromisoformat(r["tao_luc"]), datetime.fromisoformat(r["han_luc"])
        assert han - tao == timedelta(hours=24) and tao < T0
        if r["cap_nhat_luc"]:
            assert datetime.fromisoformat(r["cap_nhat_luc"]) <= T0 and r["trang_thai"] in ("da_xong", "khong_lam_duoc", "da_nhan")
        if r["trang_thai"] == "khong_lam_duoc":
            assert r["ghi_chu"]
        if r["bao_quan_ly_luc"]:
            assert r["trang_thai"] in td.MO                                                  # chỉ việc còn mở mới bị báo quản lý


def test_chi_nap_lich_su_o_che_do_minh_hoa_va_danh_dau_mo_phong(trang_thai, monkeypatch):
    td.xoa_het_minh_hoa()
    n = mp.nap_lich_su(T0)
    d = td.danh_sach_day_du(T0)
    assert n == len(d) and (d["mo_phong"] == 1).all() and d["phan_hoi_luc"].notna().any()
    monkeypatch.setenv("LIEN_KHOI_NGUON", "that")
    with pytest.raises(RuntimeError):
        mp.nap_lich_su(T0)
    with pytest.raises(RuntimeError):
        td.chen_lich_su([])


def test_chuan_bi_demo_nap_lich_su_va_viec_hom_nay_va_luat_khong_dong_viec_mo_phong(trang_thai):
    r = mp.chuan_bi_demo()
    assert r["mo_phong"] > 500 and r["moi"] > 100
    d = td.danh_sach_day_du()
    assert (d["mo_phong"] == 1).sum() == r["mo_phong"] and (d["mo_phong"] == 0).sum() == r["moi"]
    mo_phong_mo = ((d["mo_phong"] == 1) & d["dang_mo"]).sum()
    assert mo_phong_mo > 0
    from app.lien_khoi import luat
    assert td.dong_bo(luat.danh_sach_viec())["het"] == 0                                     # đồng bộ lại không đóng nhầm việc mô phỏng đang mở
    assert ((td.danh_sach_day_du()["mo_phong"] == 1) & (td.danh_sach_day_du()["trang_thai"] == "tu_het")).sum() == 0
    s = hq.so_do(hq.chuan_bi(td.danh_sach_day_du(), td.bay_gio()))
    assert s["mo_phong"] == r["mo_phong"] and s["ty_le"] is not None and 40 <= s["ty_le"] <= 95 and s["gio_xu_ly"] is not None


def test_moc_truoc_khi_dung_luu_doc_va_xoa(trang_thai):
    assert td.doc_moc() == {}
    td.ghi_moc(40, 35)
    assert td.doc_moc() == {"gio_xu_ly": 40.0, "ty_le_dung_han": 35.0}
    td.ghi_moc(None, 35)
    assert td.doc_moc() == {"ty_le_dung_han": 35.0}
    td.xoa_het_minh_hoa()
    assert td.doc_moc() == {}


def test_file_trang_thai_cu_chua_co_cot_mo_phong_van_mo_duoc(trang_thai):
    import sqlite3
    p = trang_thai / "td.db"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE giao (id INTEGER PRIMARY KEY AUTOINCREMENT, so_hd TEXT NOT NULL, luat TEXT NOT NULL, vai_tro TEXT NOT NULL, nguoi TEXT NOT NULL, nguoi_goc TEXT, "
              "ten_luat TEXT, muc TEXT, ly_do TEXT, de_xuat TEXT, trang_thai TEXT NOT NULL, tao_luc TEXT NOT NULL, han_luc TEXT NOT NULL, da_gui_luc TEXT, nhac_luc TEXT, "
              "bao_quan_ly_luc TEXT, cap_nhat_luc TEXT, cap_nhat_boi TEXT, ghi_chu TEXT, UNIQUE (so_hd, luat, vai_tro))")
    c.commit()
    c.close()
    assert td.danh_sach(T0).empty and td.hop_thu().empty                                    # mở lại file bản cũ: tự thêm cột, không lỗi
    assert td.chen_lich_su([]) == 0


# ------------------------------------------------------------------ giao diện
def test_hinh_ve_khong_loi_khi_co_va_khi_khong_co_du_lieu():
    d = hq.chuan_bi(_mau(), T0)
    f = lienkhoi_hq.hinh_xu_huong(hq.xu_huong(d))
    assert len(f.data) == 3                                                                  # cột giao, cột hoàn tất, đường tỷ lệ
    assert len(lienkhoi_hq.hinh_xu_huong(pd.DataFrame()).data) == 0 and len(lienkhoi_hq.hinh_theo_khoi(pd.DataFrame()).data) == 0
    assert len(lienkhoi_hq.hinh_theo_khoi(hq.tong_hop(d, "vai_tro")).data) == 1


def test_layout_tab_hieu_qua_dung_duoc():
    assert lienkhoi_hq.layout() is not None
    assert lienkhoi_hq._so(None) == "–" and lienkhoi_hq._so(12.34) == "12,3"
