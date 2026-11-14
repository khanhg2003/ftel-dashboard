"""Mô phỏng người nhận làm việc trong bản minh hoạ (nhánh thi-lien-khoi): việc mô phỏng không bị gửi / nhắc / nhận trả lời, đồng hồ chạy tới thì
người nhận xử lý việc thật theo tốc độ riêng, số đo không tụt vô lý. File trạng thái tạm (tmp_path), không gửi tin nào ra ngoài."""
from __future__ import annotations

import pytest

from app import zalo_bot
from app.lien_khoi import hieu_qua as hq
from app.lien_khoi import mo_phong as mp
from app.lien_khoi import theo_doi as td
from app.lien_khoi import zalo_viec as zv


@pytest.fixture
def demo(tmp_path, monkeypatch):
    monkeypatch.setenv("LIEN_KHOI_DB", str(tmp_path / "td.db"))
    monkeypatch.setenv("LIEN_KHOI_NGUON", "demo")
    monkeypatch.delenv("LIEN_KHOI_ZALO_TOKEN", raising=False)

    def khong_gui(*a, **k):
        raise AssertionError("Chế độ minh hoạ không được gửi tin thật")
    monkeypatch.setattr(zalo_bot, "gui_tin", khong_gui)
    return tmp_path


def _so_do():
    now = td.bay_gio()
    return hq.so_do(hq.chuan_bi(td.danh_sach_day_du(now), now))


def test_viec_mo_phong_khong_bi_gui_nhac_bao_quan_ly_hay_nhan_tra_loi(demo):
    mp.chuan_bi_demo()
    r = zv.gui_viec_moi()
    d = td.danh_sach()
    assert r["viec"] == int((d["mo_phong"] == 0).sum())                                       # chỉ việc hôm nay (thật) được gửi
    td.them_gio_gia_lap(60)
    zv.chay_nhac()
    h = td.hop_thu()
    assert not h["noi_dung"].str.contains("MHLS").any()                                      # không tin nào nhắc tới việc mô phỏng
    mo_phong_mo = d[(d["mo_phong"] == 1) & d["dang_mo"]]
    assert len(mo_phong_mo) > 0
    nguoi = mo_phong_mo["nguoi"].iloc[0]
    assert "MHLS" not in zv.xu_ly_tra_loi(nguoi, "xong")                                      # trả lời chỉ nói tới việc thật, không bao giờ nhắc việc mô phỏng
    d2 = td.danh_sach()
    assert (d2[d2["mo_phong"] == 1]["trang_thai"].isin(["da_xong"]).sum()) == (d[d["mo_phong"] == 1]["trang_thai"].isin(["da_xong"]).sum())   # và không đổi việc mô phỏng


def test_nguoi_chi_co_mot_viec_that_tra_loi_xong_khong_can_ma_va_lan_hai_noi_het_viec(demo):
    mp.chuan_bi_demo()
    zv.gui_viec_moi()
    d = td.danh_sach()
    that = d[d["mo_phong"] == 0]
    dem = that.groupby("nguoi")["so_hd"].nunique()
    nguoi = dem[dem == 1].index[0]                                                            # người có đúng một việc thật (trong khi còn nhiều việc mô phỏng cũ)
    so_hd = that[that["nguoi"] == nguoi]["so_hd"].iloc[0]
    assert f"{so_hd}: Đã xong" in zv.xu_ly_tra_loi(nguoi, "xong")
    assert "không có việc nào đang mở" in zv.xu_ly_tra_loi(nguoi, "xong")


def test_tien_thoi_gian_nguoi_nhan_xu_ly_viec_that_va_chay_lai_khong_doi_gi(demo):
    mp.chuan_bi_demo()
    zv.gui_viec_moi()
    truoc = _so_do()
    assert mp.tien_thoi_gian() == {"xong": 0, "khong_lam_duoc": 0, "da_nhan": 0}              # chưa chạy đồng hồ thì chưa ai làm kịp
    td.them_gio_gia_lap(25)
    r = mp.tien_thoi_gian()
    assert r["xong"] > 100 and r["khong_lam_duoc"] > 0 and r["da_nhan"] > 0
    assert mp.tien_thoi_gian() == {"xong": 0, "khong_lam_duoc": 0, "da_nhan": 0}              # gọi lại không đổi gì
    sau = _so_do()
    assert sau["xong"] >= truoc["xong"] + r["xong"] and 45 <= sau["ty_le"] <= 90              # lùi đồng hồ không làm tỷ lệ tụt vô lý
    d = td.danh_sach()
    assert d.loc[d["mo_phong"] == 1, "cap_nhat_boi"].notna().any() and (d["trang_thai"] == "tu_het").sum() == 0


def test_chay_den_48_gio_van_con_viec_bi_bo_ngo_de_nhac_va_bao_quan_ly(demo):
    mp.chuan_bi_demo()
    zv.gui_viec_moi()
    td.them_gio_gia_lap(25)
    mp.tien_thoi_gian()
    n1 = zv.chay_nhac()
    assert n1["nhac"] > 0                                                                     # người chưa làm xong bị nhắc
    td.them_gio_gia_lap(25)
    mp.tien_thoi_gian()
    n2 = zv.chay_nhac()
    assert n2["bao_quan_ly"] > 0
    d = td.danh_sach()
    that = d[d["mo_phong"] == 0]
    assert that["bao_quan_ly_luc"].notna().sum() > 0 and (that["trang_thai"] == "da_xong").sum() > 100


def test_toc_do_nguoi_co_dinh_theo_ma_va_co_nguoi_nhanh_nguoi_cham():
    assert mp.toc_do_nguoi("ktv_01") == mp.toc_do_nguoi("ktv_01")
    toc = {mp.toc_do_nguoi(f"sale_{i:02d}") for i in range(40)}
    assert min(toc) < 1 < max(toc)


def test_chi_chay_o_che_do_minh_hoa(demo, monkeypatch):
    monkeypatch.setenv("LIEN_KHOI_NGUON", "that")
    with pytest.raises(RuntimeError):
        mp.tien_thoi_gian()
