"""Khối DVKH, phần phân tích sâu: xu hướng, dự báo, dòng chảy giữ chân, phí / miễn giảm, tuổi tồn, nhãn nhân sự. Chỉ dùng DataFrame dựng tay, không đụng database."""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from app.dvkh import doc_file, khai_thac as kt, xu_huong as xh


# ------------------------------------------------------------------ xu hướng và dự báo
def test_huong_tang_giam_di_ngang_va_thieu_ngay():
    assert xh.huong(pd.Series([10, 10, 10, 10, 10, 14, 14, 14]))["huong"] == "tang"
    assert xh.huong(pd.Series([20, 20, 20, 20, 20, 10, 10, 10]))["huong"] == "giam"
    assert xh.huong(pd.Series([10, 10, 10, 10, 10, 10, 10.2, 10]))["huong"] == "di_ngang"
    assert xh.huong(pd.Series([1, 2, 3])) is None                                   # quá ít ngày thì không kết luận


def test_danh_gia_huong_theo_chieu_tot():
    tang = xh.huong(pd.Series([10, 10, 10, 10, 10, 14, 14, 14]))
    assert xh.danh_gia_huong(tang, tang_la_tot=False) == "xau"                      # tồn tăng là xấu
    assert xh.danh_gia_huong(tang, tang_la_tot=True) == "tot"
    assert xh.danh_gia_huong(None, tang_la_tot=True) == "trung_tinh"


def test_du_bao_thang_theo_nhip_trung_binh():
    db = xh.du_bao_thang(pd.Series([100, 100, 100, 100, 100]), 30)
    assert db["du_bao"] == 3000 and db["da_co"] == 500 and db["con_lai"] == 25 and db["tin_cay"] == "thấp"
    assert xh.du_bao_thang(pd.Series([100, 100]), 30) is None                       # chưa đủ 3 ngày


def test_luong_theo_ngay_vao_ra_ton():
    d = pd.DataFrame({"ngay_yc": pd.to_datetime(["2026-10-01", "2026-10-01", "2026-10-02"]), "tinh_trang": ["Đã hoàn tất", "Đang xử lý", "Đã hoàn tất"],
                      "tg_cn_cuoi": pd.to_datetime(["2026-10-02 09:00", None, "2026-10-02 10:00"])})
    l = xh.luong_theo_ngay(d, "ngay_yc")
    assert l["vao"].tolist() == [2, 1] and l["ra"].tolist() == [0, 2]
    assert l["ton_cuoi_ngay"].tolist() == [2, 1]                                    # còn 1 SR đang xử lý


def _cn(ky: str, ngay: list[int], gia_tri: list[float], ten: str = "To tal DNG CN 30", cap: str = "phong") -> pd.DataFrame:
    return pd.DataFrame({"ky_no": ky, "cap": cap, "ten": ten, "so_ngay": ngay, "ty_le_bill": gia_tri, "ty_le_dt": gia_tri})


def test_du_bao_cong_no_theo_hinh_dang_ky_truoc():
    cu = _cn("2026-08", list(range(1, 11)), [round(.1 * i, 2) for i in range(1, 11)])
    moi = _cn("2026-09", [1, 3, 5], [.1, .3, .4])
    r = xh.du_bao_cong_no(pd.concat([cu, moi]), "To tal DNG CN 30")
    assert r["so_ngay"] == 5 and r["hien_tai"] == .4 and r["cung_ngay_ky_cu"] == .5
    assert abs(r["duong_du_bao"][0] - 0.52) < 1e-9                                  # ngày 6: 1 - 0,6 × (1 - 0,6) / (1 - 0,5)
    assert r["du_bao_cuoi_ky"] == 1.0 and list(r["ngay_du_bao"]) == [6, 7, 8, 9, 10]


def test_du_bao_cong_no_can_ky_truoc_da_chay_het():
    cu = _cn("2026-08", [1, 2, 3], [.1, .2, .3])
    moi = _cn("2026-09", [1, 2, 3, 4], [.1, .2, .3, .4])
    assert xh.du_bao_cong_no(pd.concat([cu, moi]), "To tal DNG CN 30") is None     # kỳ trước chưa có số sau ngày hiện tại


def test_chenh_dich_chuyen_bo_dong_tong_va_so_theo_ngay_lich():
    cu = _cn("2026-08", [3, 4, 5], [.3, .4, .5], ten="Q.Hai Chau", cap="quan")
    moi = _cn("2026-09", [3, 4, 5], [.25, .4, .55], ten="Q.Hai Chau", cap="quan")
    tong = _cn("2026-09", [3, 4, 5], [.5, .5, .5], ten="DNG 1", cap="quan")
    m = xh.chenh_dich_chuyen(pd.concat([cu, moi, tong]))
    assert list(m.index) == ["Q.Hai Chau"]
    assert m.loc["Q.Hai Chau"].round(1).tolist() == [-5.0, 0.0, 5.0]


# ------------------------------------------------------------------ giữ chân khách
def _thanh_ly(tu_van: str, so: int, chet: int) -> pd.DataFrame:
    return pd.DataFrame({"ma_sr": [f"{tu_van}-{i}" for i in range(so)], "loai_yc": "Thanh lý", "ket_qua_tu_van": tu_van,
                         "roi_mang_sau": [i < chet for i in range(so)], "o_lai": tu_van.startswith("Khách hàng đồng ý")})


def test_khong_dong_y_khong_bi_tinh_la_o_lai():
    d = pd.DataFrame({"ket_qua_tu_van": ["Khách hàng không đồng ý sử dụng tiếp", "Khách hàng đồng ý sử dụng tiếp và không cần hỗ trợ", "Khách hàng đang suy nghĩ", None]})
    assert kt.ket_qua_tu_van_nhom(d).tolist() == ["Không đồng ý", "Đồng ý ở lại", "Đang suy nghĩ", "Chưa có kết quả tư vấn"]


def test_dong_giu_chan_va_tom_tat():
    bd = pd.concat([_thanh_ly("Khách hàng không đồng ý sử dụng tiếp", 20, 15), _thanh_ly("Khách hàng đang suy nghĩ", 10, 1),
                    _thanh_ly("Khách hàng đồng ý sử dụng tiếp và không cần hỗ trợ", 10, 0)], ignore_index=True)
    g = kt.dong_giu_chan(bd)
    t = kt.tom_tat_giu_chan(g)
    assert g["tong"] == 40 and t["khong_dong_y"] == 20 and t["chet_trong_khong_dong_y"] == 15
    assert t["dang_nghi"] == 10 and t["con_cuu_duoc"] == 9 and t["o_lai"] == 10 and t["chet"] == 16
    assert sum(v for s, v in zip(g["nguon"], g["gia_tri"]) if s == 0) == 40          # mọi yêu cầu đều chảy ra một nhóm tư vấn


def test_dong_giu_chan_can_du_mau():
    assert kt.dong_giu_chan(_thanh_ly("Khách hàng đang suy nghĩ", 5, 0)) is None


# ------------------------------------------------------------------ phí, tuổi tồn, nhãn nhân sự
def test_phi_mien_giam_vuot_phi():
    d = pd.DataFrame({"ma_sr": list("abcd"), "loai_yc": ["Chuyển địa điểm", "Chuyển địa điểm", "Khôi phục dịch vụ", "Thắc mắc"],
                      "phi": [100, 100, 50, 0], "mien_giam_phi": [40, 0, 60, 0]})
    g = kt.phi_mien_giam(d).set_index("loai_yc")
    assert "Thắc mắc" not in g.index
    assert g.loc["Chuyển địa điểm", "ty_le_mien_giam"] == 20 and g.loc["Khôi phục dịch vụ", "ty_le_mien_giam"] == 120
    assert g.loc["Khôi phục dịch vụ", "thu_thuc"] == -10


def test_tuoi_ton_chia_bac():
    moc = datetime(2026, 10, 10, 12, 0)
    d = pd.DataFrame({"ton": [True, True, True, True, False], "tg_yc": [moc - pd.Timedelta(hours=h) for h in (2, 30, 100, 200, 5)], "loai_yc": "A"})
    t = kt.tuoi_ton(d.assign(tg_yc=pd.to_datetime(d["tg_yc"])), "tg_yc").set_index("tuoi")["so"]
    assert t.to_dict() == {"Dưới 1 ngày": 1, "1 đến 3 ngày": 1, "3 đến 7 ngày": 1, "Trên 7 ngày": 1}    # mốc tuổi là SR mới nhất trong bảng


def test_nhan_nhan_su_theo_tai_va_qua_han():
    ten = [f"n{i}" for i in range(12)]
    hs = pd.DataFrame({"nhan_su": ten, "tong_tai": [200, 200, 200, 200, 200, 200, 60, 60, 60, 60, 60, 20],
                       "ty_le_qua_han": [60, 5, 10, 30, 28, 32, 60, 5, 20, 20, 20, 90]})
    nhan = kt.cho_nao_tot_xau(hs).set_index("nhan_su")["nhan"]
    assert nhan["n0"] == "Cần hỗ trợ"                 # nhiều việc và quá hạn cao nhất
    assert nhan["n1"] == "Làm tốt"                    # nhiều việc, quá hạn thấp
    assert nhan["n6"] == "Cần nhắc"                   # ít việc mà vẫn chậm
    assert nhan["n11"] == ""                          # dưới 30 SR không gắn nhãn dù quá hạn rất cao


def test_gan_so_khach_khop_ten_khong_phan_biet_hoa_thuong():
    hs = pd.DataFrame({"nhan_su": ["haonth2", "khac"], "tong_tai": [100, 50]})
    so_kh = pd.DataFrame({"acc": ["HaoNTH2"], "so_kh": [5000]})
    kq = kt.gan_so_khach(hs, so_kh)
    assert kq.loc[0, "sr_1000kh"] == 20 and np.isnan(kq.loc[1, "sr_1000kh"])
    assert kt.gan_so_khach(hs, pd.DataFrame(columns=["acc", "so_kh"]))["sr_1000kh"].isna().all()


def test_doc_so_kh_au_tu_bang_pivot():
    dong = [["SR", "Account IS"], [], ["Row Labels", "Count of Acc NVVP "], ["DaoNTH5", 4611], ["Hoadtt19", 5404], ["Grand Total", 10015], [], ["Khác", 1]]
    assert doc_file.doc_so_kh_au(dong) == [{"acc": "daonth5", "so_kh": 4611}, {"acc": "hoadtt19", "so_kh": 5404}]
    assert doc_file.doc_so_kh_au([["không có pivot"]]) == []


def test_theo_goi_bo_nhom_it_mau():
    d = pd.DataFrame({"ma_sr": range(70), "goi_net_nhom": ["Sky"] * 40 + ["Giga"] * 30 + [None] * 0, "loai_yc": ["Thanh lý"] * 10 + ["Thắc mắc"] * 60})
    g = kt.theo_goi(d).set_index("goi_net_nhom")
    assert g.loc["Sky", "ty_le_thanh_ly"] == 25 and g.loc["Giga", "ty_le_thanh_ly"] == 0
    assert kt.theo_goi(d.head(20)).empty                                           # dưới 30 SR mỗi gói thì bỏ qua
