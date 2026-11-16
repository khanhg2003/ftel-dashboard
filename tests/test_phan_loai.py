"""Phân loại khách hàng (chăm sóc chủ động / nhắc cước / bán thêm) trên bộ minh hoạ, nguồn cước tuỳ chọn, nạp file cước và giao diện tab.
Mọi file trạng thái nằm ở tmp_path."""
from __future__ import annotations

import json

import pandas as pd
import pytest

from app.bo_nho import xoa
from app.lien_khoi import ho_so, nguon, phan_loai as pl


@pytest.fixture
def demo(tmp_path, monkeypatch):
    monkeypatch.setenv("LIEN_KHOI_DB", str(tmp_path / "state.db"))
    monkeypatch.setenv("LIEN_KHOI_NGUON", "demo")
    xoa()
    yield tmp_path
    xoa()


def test_ba_nhom_tren_bo_minh_hoa(demo):
    t = pl.tong_hop()
    s = pl.tom_tat(t)
    b, rm, nc, bt = t["dac_diem"], t["roi_mang"], t["nhac_cuoc"], t["ban_them"]
    assert t["hom_nay"] == pd.Timestamp("2026-11-14") and t["tong"] == 227 and t["co_nguon_cuoc"]
    assert s["rm"] == len(rm) > 0 and s["cuoc"] == len(nc) > 0 and s["ban"] == len(bt) >= 30
    # nhóm 1: chỉ hợp đồng đang hoạt động, điểm đúng ngưỡng, xếp giảm dần, luôn có lý do và việc nên làm
    assert b.loc[rm["so_hd"], "hoat_dong"].all() and rm["diem"].between(30, 100).all() and rm["diem"].is_monotonic_decreasing
    assert ((rm["muc"] == pl.CAO) == (rm["diem"] >= 60)).all() and rm["ly_do"].ne("").all() and rm["de_xuat"].ne("").all()
    assert not rm["ly_do"].str.contains("nan|None").any()
    # nhóm 2: mỗi hợp đồng một dòng; quá hạn thì hạn trước ngày tham chiếu; hợp đồng trong danh sách nợ đều có mặt
    assert nc["so_hd"].is_unique and set(nc["nhom"]) <= set(pl.NHOM_CUOC)
    qh = nc[nc["nhom"] == pl.NHOM_CUOC[0]]
    assert len(qh) and (qh["con_ngay"] < 0).all() and (qh["han_tt"] < t["hom_nay"]).all() and (qh["so_tien"] > 0).all()
    sap = nc[nc["nhom"].isin(pl.NHOM_CUOC[1:4])]
    assert len(sap) and sap["con_ngay"].between(0, 30).all()
    assert set(b.index[b["trong_ds_no"]]) <= set(nc["so_hd"])
    assert t["lich_cuoc"]["so_tien"].sum() == pytest.approx(sap["so_tien"].sum())
    # nhóm 3: khách ổn định, không trùng nhóm 1, không nợ; gợi ý không mời thứ khách đã có
    assert not set(bt["so_hd"]) & set(rm["so_hd"]) and not b.loc[bt["so_hd"], "dang_no"].any() and b.loc[bt["so_hd"], "hoat_dong"].all()
    for r in bt.to_dict("records"):
        assert r["goi_y"] and set(r["goi_y"].split(" · ")) <= set(pl.GOI_Y)
        assert ("FPT Play" in r["goi_y"]) == (not b.at[r["so_hd"], "co_play"]) and ("Camera" in r["goi_y"].split(" · ")) == (not b.at[r["so_hd"], "co_camera"])
    assert sum(s["ban_theo_dv"].values()) == int(bt["so_goi_y"].sum())


def test_ho_so_co_phan_loai_va_lich_su_cuoc(demo):
    t = pl.tong_hop()
    ma = t["nhac_cuoc"].loc[t["nhac_cuoc"]["nhom"] == pl.NHOM_CUOC[0], "so_hd"].iloc[0]
    h = ho_so.ho_so(ma)
    p = h["pl"]
    assert "nhac_cuoc" in {n["ma"] for n in p["nhom"]} and p["tom_tat"]["qua_han"] >= 1 and p["tom_tat"]["tien_chua_tt"] > 0
    assert len(p["ky"]) == p["tom_tat"]["so_ky"] and p["ky"]["ky_tu"].is_monotonic_decreasing
    from app.ui.pages import lienkhoi_hs
    chu = json.dumps(lienkhoi_hs.noi_dung(h).to_plotly_json(), default=lambda o: o.to_plotly_json(), ensure_ascii=False)
    assert "Lịch sử thanh toán cước" in chu and "Quá hạn" in chu and "Phân loại khách hàng" in chu
    ma_on = t["ban_them"]["so_hd"].iloc[0]
    assert [n["ma"] for n in pl.cua_hop_dong(ma_on)["nhom"] if n["ma"] != "nhac_cuoc"] == ["ban_them"]
    khong = pl.cua_hop_dong("KHONGCO0001")
    assert khong["nhom"] == [] and khong["ky"].empty and khong["tom_tat"] == {"so_ky": 0, "chua_tt": 0, "qua_han": 0, "tre": 0, "tien_chua_tt": 0.0}


def test_thieu_nguon_cuoc_van_chay(demo, monkeypatch):
    """Không có nguồn lịch sử kỳ cước: không lỗi, báo chưa có nguồn cước, nhóm nhắc cước chỉ còn danh sách nợ."""
    goc = nguon._csv

    def _csv_thieu_cuoc(ten, ngay=None):                       # như thư mục nguồn không có file cuoc.csv
        if ten == "cuoc":
            raise FileNotFoundError(ten)
        return goc(ten, ngay)
    monkeypatch.setattr(nguon, "_csv", _csv_thieu_cuoc)
    xoa()
    t = pl.tong_hop()
    assert not t["co_nguon_cuoc"] and len(t["roi_mang"]) > 0
    assert set(t["nhac_cuoc"]["nhom"]) == {pl.NHOM_CUOC[4]} and t["lich_cuoc"].empty
    assert not t["ban_them"]["goi_y"].str.contains("trả trước").any()            # không có lịch sử thanh toán thì không gợi ý chuyển trả trước


def test_du_lieu_that_chua_co_nguon_cuoc_thi_rong(monkeypatch):
    monkeypatch.setenv("LIEN_KHOI_NGUON", "that")
    d = nguon.cuoc()
    assert d.empty and list(d.columns) == nguon.COT_CUOC


def test_tab_phan_loai_va_dashboard_dung_duoc_tren_bo_minh_hoa(demo):
    from app.ui.pages import lienkhoi, lienkhoi_tq, phanloai
    assert phanloai.layout() is not None and lienkhoi_tq.layout() is not None
    assert [t[0] for t in lienkhoi.TAB][:2] == ["tongquan", "pl"]
