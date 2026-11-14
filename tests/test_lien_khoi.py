"""Điều hành liên khối (nhánh thi-lien-khoi): bảng sự kiện và ba luật đầu. Luật là hàm thuần nên kiểm bằng bảng dựng tay, không cần database."""
from __future__ import annotations

import pandas as pd
import pytest

from app.lien_khoi import luat, su_kien as sk
from app.models import User

T = pd.Timestamp
NGAY_TC = T("2026-09-12")


def _kd(*dong) -> pd.DataFrame:
    """Mỗi dòng: dict ghi đè mặc định (hợp đồng chưa online, đang tồn, tạo cách ngày tham chiếu 5 ngày)."""
    mac = dict(so_hd="DAAAA0001", ngay_tao=T("2026-09-07"), ngay_online=pd.NaT, ngay_huy=pd.NaT, sale="DNG.A", phong="IBB7",
               goi="Sky", tinh_trang="Bình thường", ton=True)
    return pd.DataFrame([{**mac, **d} for d in dong])


def _bd(*dong) -> pd.DataFrame:
    mac = dict(so_hd="DAAAA0001", tg_yc=T("2026-10-07 09:00"), loai_yc="Thắc mắc", tinh_trang="Đang xử lý", ket_qua_tu_van=None,
               nhan_su_au="cskh1", net_hien="Đang hoạt động")
    return pd.DataFrame([{**mac, **d} for d in dong])


def _cd(*dong) -> pd.DataFrame:
    mac = dict(so_hd="DAAAA0001", tg_do=T("2026-10-07 07:00"), nhom_ct="Nhóm chất lượng dịch vụ", ket_qua_tu_van=None, diem_rm=-1.0,
               tinh_trang="Đang xử lý", nhan_su_au="cskh2")
    return pd.DataFrame([{**mac, **d} for d in dong])


def _rong_bd() -> pd.DataFrame:
    return _bd().iloc[0:0]


def _rong_cd() -> pd.DataFrame:
    return _cd().iloc[0:0]


# ------------------------------------------------------------------ chờ online lâu
def test_cho_online_chi_tinh_hop_dong_ton_du_so_ngay_va_con_hieu_luc():
    kd = _kd(dict(so_hd="DAAAA0001"),                                              # 5 ngày: tính
             dict(so_hd="DAAAA0002", ngay_tao=T("2026-09-11")),                    # 1 ngày: chưa tới
             dict(so_hd="DAAAA0003", ngay_huy=T("2026-09-10")),                    # đã huỷ
             dict(so_hd="DAAAA0004", phong="NGOAI_CN"),                            # chi nhánh khác bán hộ
             dict(so_hd="DAAAA0005", ton=False),                                   # không còn trong tồn
             dict(so_hd="DAAAA0006", tinh_trang="Đã chấm dứt hợp đồng"))
    v = luat.luat_cho_online(kd, NGAY_TC, so_ngay=2, cao_tu=7)
    assert list(v["so_hd"]) == ["DAAAA0001"]
    assert v["giao_kt"].iloc[0] == luat.GIAO_KT                                    # khối Kỹ thuật chưa có nguồn: vào hàng chờ
    assert "5 ngày chưa online" in v["ly_do"].iloc[0]


def test_cho_online_muc_cao_tu_moc_va_sale_trong_thi_ghi_khong_co_trong_file():
    kd = _kd(dict(so_hd="DAAAA0001", ngay_tao=T("2026-09-01"), sale=""), dict(so_hd="DAAAA0002", ngay_tao=T("2026-09-08")))
    v = luat.luat_cho_online(kd, NGAY_TC, so_ngay=2, cao_tu=7).set_index("so_hd")
    assert v.loc["DAAAA0001", "muc"] == luat.CAO and v.loc["DAAAA0002", "muc"] == luat.TB
    assert v.loc["DAAAA0001", "giao_sale"] == luat.KHONG_CO_SALE


# ------------------------------------------------------------------ lỗi sớm sau lắp
def test_loi_som_chi_tinh_sr_khieu_nai_sau_khi_online_trong_han():
    kd = _kd(dict(so_hd="DAAAA0001", ngay_online=T("2026-09-20")),
             dict(so_hd="DAAAA0002", ngay_online=T("2026-07-01")),                 # SR quá 30 ngày sau online
             dict(so_hd="DAAAA0003", ngay_online=T("2026-10-20")),                 # SR (07/10) có trước ngày online
             dict(so_hd="DAAAA0004", ngay_online=T("2026-09-20")))                 # SR không phải khiếu nại
    kn = "Khiếu nại, phàn nàn"
    bd = _bd(dict(so_hd="DAAAA0001", loai_yc=kn), dict(so_hd="DAAAA0002", loai_yc=kn), dict(so_hd="DAAAA0003", loai_yc=kn),
             dict(so_hd="DAAAA0004", loai_yc="Thắc mắc"))
    v = luat.luat_loi_som(kd, bd, so_ngay=30, loai_yc=(kn,))
    assert list(v["so_hd"]) == ["DAAAA0001"]
    assert v["giao_sale"].iloc[0] == "DNG.A" and v["giao_kt"].iloc[0] == luat.GIAO_KT


def test_loi_som_hai_sr_la_muc_cao_va_nguoi_dvkh_lay_tu_tu_dien_hoac_hang_cho():
    kd = _kd(dict(so_hd="DAAAA0001", ngay_online=T("2026-09-20")), dict(so_hd="DAAAA0002", ngay_online=T("2026-09-20")))
    kn = "Khiếu nại, phàn nàn"
    bd = _bd(dict(so_hd="DAAAA0001", loai_yc=kn), dict(so_hd="DAAAA0001", loai_yc=kn, tg_yc=T("2026-10-08 09:00")),
             dict(so_hd="DAAAA0002", loai_yc=kn))
    v = luat.luat_loi_som(kd, bd, 30, (kn,), dvkh={"DAAAA0001": "cskh9"}).set_index("so_hd")
    assert v.loc["DAAAA0001", "muc"] == luat.CAO and v.loc["DAAAA0002", "muc"] == luat.TB
    assert v.loc["DAAAA0001", "giao_dvkh"] == "cskh9" and v.loc["DAAAA0002", "giao_dvkh"] == luat.GIAO_DVKH


# ------------------------------------------------------------------ khách có ý rời
def test_co_y_roi_sr_bi_dong_manh_la_cao_dang_suy_nghi_la_trung_binh_da_giu_duoc_thi_bo():
    bd = _bd(dict(so_hd="DAAAA0001", ket_qua_tu_van="Khách hàng không đồng ý sử dụng tiếp"),
             dict(so_hd="DAAAA0002", ket_qua_tu_van="Khách hàng đang suy nghĩ"),
             dict(so_hd="DAAAA0003", loai_yc="Thanh lý", ket_qua_tu_van="Khách hàng đồng ý"),     # đã giữ được
             dict(so_hd="DAAAA0004", loai_yc="Thanh lý", ket_qua_tu_van=None),                     # xin thanh lý, chưa tư vấn
             dict(so_hd="DAAAA0005", ket_qua_tu_van="Khách hàng không đồng ý", net_hien="Đã chấm dứt hợp đồng"),
             dict(so_hd="DAAAA0006", ket_qua_tu_van="Khách hàng không đồng ý", tg_yc=T("2026-09-01")))   # ngoài cửa sổ
    v = luat.luat_co_y_roi(bd, _rong_cd(), _kd(), set(), so_ngay_gan=3).set_index("so_hd")
    assert set(v.index) == {"DAAAA0001", "DAAAA0002", "DAAAA0004"}
    assert v.loc["DAAAA0001", "muc"] == luat.CAO and v.loc["DAAAA0004", "muc"] == luat.CAO
    assert v.loc["DAAAA0002", "muc"] == luat.TB


def test_co_y_roi_sr_chu_dong_yeu_cau_thanh_ly_cao_va_diem_cao_chi_tinh_khi_sr_con_mo():
    cd = _cd(dict(so_hd="DAAAA0001", ket_qua_tu_van="Khách hàng yêu cầu thanh lý"),
             dict(so_hd="DAAAA0002", nhom_ct="Nguy cơ rời mạng (SOS)", diem_rm=900.0),
             dict(so_hd="DAAAA0003", nhom_ct="Nguy cơ rời mạng (SOS)", diem_rm=900.0, tinh_trang="Đã hoàn tất"),
             dict(so_hd="DAAAA0004", nhom_ct="Nguy cơ rời mạng (SOS)", diem_rm=500.0))
    v = luat.luat_co_y_roi(_rong_bd(), cd, _kd(), set(), so_ngay_gan=3, diem_cao=800).set_index("so_hd")
    assert set(v.index) == {"DAAAA0001", "DAAAA0002"}
    assert v.loc["DAAAA0001", "muc"] == luat.CAO and v.loc["DAAAA0002", "muc"] == luat.TB


def test_co_y_roi_no_cuoc_chi_ghi_vao_ly_do_khong_nang_muc():
    bd = _bd(dict(so_hd="DAAAA0001", ket_qua_tu_van="Khách hàng đang suy nghĩ"))
    v = luat.luat_co_y_roi(bd, _rong_cd(), _kd(), {"DAAAA0001"}, so_ngay_gan=3)
    assert v["muc"].iloc[0] == luat.TB and "nợ cước" in v["ly_do"].iloc[0]


def test_co_y_roi_giao_dung_nguoi_va_bo_hop_dong_da_cham_dut_o_file_ban_hang():
    kd = _kd(dict(so_hd="DAAAA0001", sale="DNG.Sale1"), dict(so_hd="DAAAA0002", tinh_trang="Đã chấm dứt hợp đồng"))
    bd = _bd(dict(so_hd="DAAAA0001", ket_qua_tu_van="Khách hàng đang suy nghĩ", nhan_su_au="cskh1"),
             dict(so_hd="DAAAA0002", ket_qua_tu_van="Khách hàng đang suy nghĩ"),
             dict(so_hd="DAAAA0003", ket_qua_tu_van="Khách hàng đang suy nghĩ", nhan_su_au=None))       # khách cũ, không có sale, chưa ai phụ trách
    v = luat.luat_co_y_roi(bd, _rong_cd(), kd, set(), so_ngay_gan=3).set_index("so_hd")
    assert set(v.index) == {"DAAAA0001", "DAAAA0003"}
    assert v.loc["DAAAA0001", "giao_sale"] == "DNG.Sale1" and v.loc["DAAAA0001", "giao_dvkh"] == "cskh1"
    assert v.loc["DAAAA0003", "giao_sale"] == luat.KHONG_CO_SALE and v.loc["DAAAA0003", "giao_dvkh"] == luat.GIAO_DVKH


def test_khong_co_du_lieu_thi_tra_bang_rong_dung_cot():
    for v in (luat.luat_cho_online(_kd().iloc[0:0], NGAY_TC), luat.luat_loi_som(_kd(), _rong_bd()),
              luat.luat_co_y_roi(_rong_bd(), _rong_cd(), _kd(), set())):
        assert v.empty and list(v.columns) == luat.COT_VIEC


def test_nguoi_dvkh_lay_nhan_su_au_cua_sr_gan_nhat():
    bd = _bd(dict(so_hd="DAAAA0001", tg_yc=T("2026-10-01"), nhan_su_au="cu"), dict(so_hd="DAAAA0002", nhan_su_au=None))
    cd = _cd(dict(so_hd="DAAAA0001", tg_do=T("2026-10-05"), nhan_su_au="moi"))
    m = luat.nguoi_dvkh(bd, cd)
    assert m == {"DAAAA0001": "moi"}                           # hợp đồng chưa có người phụ trách thì không có trong từ điển


def test_tom_tat_dem_theo_muc_va_luat():
    v = pd.DataFrame([dict(luat="cho_online", muc="Cao", giao_dvkh=""), dict(luat="co_y_roi", muc="Trung bình", giao_dvkh=luat.GIAO_DVKH)])
    t = luat.tom_tat(v)
    assert (t["tong"], t["cao"], t["hang_cho_dvkh"]) == (2, 1, 1) and t["theo_luat"]["co_y_roi"] == 1
    assert luat.tom_tat(v.iloc[0:0])["tong"] == 0


# ------------------------------------------------------------------ bảng sự kiện, chỗ cắm Kỹ thuật
def test_chuan_hd_bo_khoang_trang_va_viet_hoa():
    assert list(sk.chuan_hd(pd.Series([" daaaa0001 ", None]))) == ["DAAAA0001", ""]


def test_khoi_ky_thuat_chua_co_nguon_tra_bang_rong_dung_cot_va_da_dang_ky(monkeypatch):
    monkeypatch.delenv("LIEN_KHOI_NGUON", raising=False)        # chế độ mặc định = dữ liệu thật, khối Kỹ thuật chưa có bảng
    kt = sk.su_kien_kt()
    assert kt.empty and list(kt.columns) == sk.COT
    assert set(sk.NGUON) == {sk.KD, sk.DVKH, sk.KT}            # đã có chỗ cắm: viết thân hàm su_kien_kt là đủ


def test_dong_thoi_gian_va_khop_giua_khoi(monkeypatch):
    ev = pd.DataFrame([dict(so_hd="DAAAA0001", nguon="KD", loai="online", thoi_diem=T("2026-09-01"), chi_tiet="Online", nguoi="s"),
                       dict(so_hd="DAAAA0001", nguon="DVKH", loai="sr_bi_dong", thoi_diem=T("2026-10-01"), chi_tiet="x", nguoi="c"),
                       dict(so_hd="DAAAA0002", nguon="KD", loai="online", thoi_diem=T("2026-09-02"), chi_tiet="Online", nguoi="s")])
    monkeypatch.setattr(sk, "bang_su_kien", lambda: ev)
    assert list(sk.dong_thoi_gian(" daaaa0001 ")["nguon"]) == ["KD", "DVKH"]
    assert sk.dong_thoi_gian("KHONG_CO").empty and sk.dong_thoi_gian("").empty
    kh = sk.khop_giua_khoi()
    assert (kh["kd"], kh["dvkh"], kh["kt"], kh["kd_dvkh"], kh["ca_ba"]) == (2, 1, 0, 1, 0)


# ------------------------------------------------------------------ quyền
@pytest.mark.parametrize("role,duoc", [("admin", True), ("phong", False), ("nvkd", False), ("dvkh", False), ("online", False), ("operator", False)])
def test_chi_quan_tri_vao_duoc_trang_lien_khoi(role, duoc):
    from app.auth import SessionUser
    u = SessionUser(User(username="zz", ho_ten="x", role=role, password_hash="x", scope=None, active=True))
    assert u.vao_duoc("/lienkhoi") is duoc


def test_lien_khoi_la_trang_dung_chung_khong_thuoc_khoi_nao():
    from app.ui import khoi
    assert khoi.khoi_cua_duong_dan("/lienkhoi") is None
