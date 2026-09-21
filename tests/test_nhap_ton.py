"""Kiểm thử Nhập tồn + tài khoản Nhân viên KD (chốt với chủ app 21/09/2026)."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import nhap_ton as nt                                          # noqa: E402
from app.config import DATA_DIR                                          # noqa: E402

pytestmark = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(),
                                reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")


def _tk(role: str, scope: list[str]):
    from app.auth import SessionUser
    return SessionUser(SimpleNamespace(id=1, username=f"kiemthu.{role}", ho_ten="Kiểm thử", role=role, ma_nv=None,
                                       session_version=0, scope=json.dumps(scope)))


# ------------------------------------------------------------------ cảnh báo
def test_tra_ve_han_chot_la_het_ngay_d_cong_3():
    """Chủ app: trả về ngày 19/9 thì hạn chót là hết ngày 22/9, quá hạn HĐ tự huỷ - luôn báo đỏ cho TP."""
    d = date(2026, 9, 19)
    muc, chu, _ = nt.trang_thai("tra_ve", d, None, date(2026, 9, 21))
    assert muc == "do" and "còn 1 ngày" in chu and "22/09" in chu
    muc, chu, _ = nt.trang_thai("tra_ve", d, None, date(2026, 9, 22))
    assert muc == "do" and "hạn chót hôm nay" in chu
    muc, chu, thu_tu = nt.trang_thai("tra_ve", d, None, date(2026, 9, 23))
    assert muc == "do" and "Quá hạn xử lý 1 ngày" in chu and thu_tu == 0      # quá hạn đứng đầu cụm


def test_hen_thi_cong_qua_ngay_bao_do_dung_hom_nay_bao_vang():
    hom = date(2026, 9, 21)
    assert nt.trang_thai("hen", date(2026, 9, 19), None, hom)[:2] == ("do", "Quá hẹn 2 ngày")
    assert nt.trang_thai("hen", hom, None, hom)[0] == "vang"
    assert nt.trang_thai("hen", date(2026, 9, 25), None, hom)[0] == ""


def test_phuong_an_huy_va_da_trien_khai_khong_bao_do():
    hom = date(2026, 9, 21)
    assert nt.trang_thai("hen", date(2026, 9, 1), nt.PA_HUY, hom)[0] == "huy"
    assert nt.trang_thai("tra_ve", date(2026, 9, 1), nt.PA_DA_TRIEN_KHAI, hom)[0] == ""


# ------------------------------------------------------------------ đọc sheet cũ
@pytest.mark.parametrize("chu, loai, ngay", [
    ("29/9", "hen", date(2026, 9, 29)),
    ("Trả về 19/9", "tra_ve", date(2026, 9, 19)),
    ("trả về 20/9", "tra_ve", date(2026, 9, 20)),
    ("trả vè 18/9", "tra_ve", date(2026, 9, 18)),          # gõ sai dấu trên sheet thật
    ("treo 13/9", None, None),                            # Treo, CPTC: chủ app chốt ghi vào ghi chú
    ("cptc 22/9", None, None),
    ("đang hoàn tiền", None, None),
])
def test_doc_moc_viet_tay_tren_sheet(chu, loai, ngay):
    assert nt.doc_moc(chu, date(2026, 9, 21)) == (loai, ngay)


def test_chi_nhan_dung_phuong_an_trong_danh_sach():
    assert nt._chuan({"phuong_an": "Huỷ"}) == {"phuong_an": "Huỷ"}
    with pytest.raises(nt.LoiNhapTon):
        nt._chuan({"phuong_an": "Treo"})
    with pytest.raises(nt.LoiNhapTon):
        nt._chuan({"ghi_chu": "x" * (nt.GHI_CHU_TOI_DA + 1)})
    assert nt.cau_hinh()["phuong_an"] == ["Đang chờ triển khai", "Huỷ", "KH đang suy nghĩ - Chốt lại",
                                           "Đã triển khai"]


# ------------------------------------------------------------------ quyền
def test_quyen_nhan_vien_kd_ibb7():
    tk = _tk("nvkd", ["IBB7"])
    assert tk.duoc_xem_nhan_su and tk.phong_nhan_su() == ["IBB7"]
    assert tk.phong_nhap_ton() == ["IBB7"] and tk.duoc_nhap_ton
    assert tk.duoc_xem_ads and not tk.duoc_cau_hinh                # Ads chỉ xem, không sửa
    for trang in ("/nhapton", "/phong", "/ads"):
        assert tk.vao_duoc(trang)
    for trang in ("/", "/hr", "/phantich", "/upload", "/quantri", "/tracking"):
        assert not tk.vao_duoc(trang), trang
    assert not tk.duoc_upload


def test_nhan_vien_kd_mo_app_la_vao_thang_nhap_ton():
    """(test_trang_mo_dau_theo_vai_tro trong test_he_thong_hoa đang hỏng sẵn vì môi trường, nên kiểm riêng ở đây.)"""
    from app.ui.app import trang_mo_dau
    assert trang_mo_dau(_tk("nvkd", ["IBB7"])) == "/nhapton"
    assert trang_mo_dau(_tk("phong", ["IBB7"])) == "/phong"


def test_nhan_vien_kd_phong_khac_khong_thay_ads_va_nhap_ton():
    tk = _tk("nvkd", ["IBB2"])
    assert not tk.duoc_xem_ads and tk.phong_nhap_ton() == []


def test_truong_phong_ibb7_theo_doi_duoc_nhap_ton():
    assert _tk("phong", ["IBB7"]).phong_nhap_ton() == ["IBB7"]
    assert _tk("phong", ["IBB2"]).phong_nhap_ton() == []
    assert _tk("phong", ["IBB7"]).vao_duoc("/hr")                  # vai trò khác không bị giới hạn trang


# ------------------------------------------------------------------ danh sách + ghi
def test_danh_sach_xep_theo_tung_cum_nhan_vien():
    df = nt.danh_sach(["IBB7"])
    if df.empty:
        pytest.skip("database kiểm thử không có HĐ tồn IBB7")
    doi = (df.acc_norm != df.acc_norm.shift()).sum()
    assert doi == df.acc_norm.nunique()                            # mỗi người một cụm liền nhau
    assert {"hop_dong", "ten_khach_hang", "ngay_tao_hd", "acc", "ho_ten"} <= set(df.columns)


@pytest.fixture
def mot_ca():
    from sqlalchemy import delete

    from app.db import session_scope
    from app.models import AuditLog, TonTheoDoi
    df = nt.danh_sach(["IBB7"])
    if df.empty:
        pytest.skip("database kiểm thử không có HĐ tồn IBB7")
    r = df.iloc[0]
    yield r
    with session_scope() as s:
        s.execute(delete(TonTheoDoi).where(TonTheoDoi.hop_dong == r.hop_dong))
        s.execute(delete(AuditLog).where(AuditLog.username.like("kiemthu%")))


def test_tai_khoan_dung_chung_ghi_duoi_ten_nguoi_dang_chon(mot_ca):
    r = mot_ca
    nt.luu(r.hop_dong, {"ghi_chu": "KH hẹn cuối tuần", "loai_moc": "hen", "ngay_moc": "2026-09-27",
                        "phuong_an": "Đang chờ triển khai"}, ["IBB7"], "kiemthu.nvkd", r.acc_norm, "Nguyễn Văn Kiểm")
    moi = nt.danh_sach(["IBB7"]).set_index("hop_dong").loc[r.hop_dong]
    assert moi.cap_nhat_boi == "Nguyễn Văn Kiểm" and moi.cap_nhat.endswith("· Kiểm")
    assert moi.ghi_chu == "KH hẹn cuối tuần" and not moi.thieu


def test_tai_khoan_dung_chung_khong_sua_ca_nguoi_khac(mot_ca):
    with pytest.raises(nt.LoiNhapTon, match="không phải ca của người đang chọn"):
        nt.luu(mot_ca.hop_dong, {"ghi_chu": "x"}, ["IBB7"], "kiemthu.nvkd", "acc.nguoi.khac", "Ai Đó")


def test_khong_ghi_duoc_hop_dong_ngoai_danh_sach_ton():
    with pytest.raises(nt.LoiNhapTon, match="không còn trong danh sách tồn"):
        nt.luu("KHONGCO999", {"ghi_chu": "x"}, ["IBB7"], "kiemthu.tp")


# ------------------------------------------------------------------ tên khách hàng (dữ liệu cá nhân)
def test_chi_luu_ten_khach_hang_cua_phong_bat_nhap_ton(monkeypatch):
    """Chốt 21/09/2026: tên KH chỉ lưu cho phòng bật Nhập tồn (IBB7) và chỉ file Internet; phòng khác vẫn bỏ."""
    import pandas as pd

    from app.ingest import commit as cm
    assert cm.phong_luu_ten_kh() == {"IBB7"}
    monkeypatch.setattr(cm, "LUU_TEN_KHACH_HANG", False)
    monkeypatch.setattr(cm, "assign_phong", lambda acc, *a: ({"sale.ibb7": "IBB7"}.get(acc, "IBB2"), False))
    df = pd.DataFrame([{"hop_dong": "HD1", "acc_nhan_vien": "sale.ibb7", "ten_khach_hang": "Nguyen Van A"},
                       {"hop_dong": "HD2", "acc_nhan_vien": "sale.ibb2", "ten_khach_hang": "Tran Thi B"}])
    net = cm._fact_rows(SimpleNamespace(df=df, dataset="internet"), {}, 1)
    assert [r["ten_khach_hang"] for r in net] == ["Nguyen Van A", None]
    fpl = cm._fact_rows(SimpleNamespace(df=df, dataset="fptplay"), {}, 1)
    assert [r["ten_khach_hang"] for r in fpl] == [None, None]


# ------------------------------------------------------------------ giao diện (chủ app 21/09: bấm tên phải thấy đổi ngay)
def test_ten_tren_chip_ngan_gon_va_khong_trung():
    import pandas as pd

    from app.ui.pages.nhapton import _ten_chip
    tong = pd.DataFrame({"acc_norm": ["a", "b", "c"],
                         "ho_ten": ["Bùi Ngô Anh Thắng", "Trần Văn Anh Thắng", "Hồ Thị Mỹ Chi"]})
    assert _ten_chip(tong) == {"a": "Bùi Ngô Anh Thắng", "b": "Trần Văn Anh Thắng", "c": "Mỹ Chi"}


def test_o_so_cung_la_nut_loc_va_danh_dau_o_dang_chon():
    from app.ui.pages.nhapton import _kpi
    d = {"ton": 32, "chua_cap_nhat": 5, "gap": 2, "den_han": 1, "tra_ve": 1, "qua_hen": 1, "huy": 0}
    o = _kpi(d, "gap")
    assert [x.id["v"] for x in o] == ["all", "gap", "den_han", "thieu"]      # gấp đứng ngay sau tổng
    assert ["dang-chon" in x.className for x in o] == [False, True, False, False]
    assert "bad" in o[1].className                                          # còn ca gấp thì đỏ
