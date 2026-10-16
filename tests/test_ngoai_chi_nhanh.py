"""HĐ do sale chi nhánh khác bán hộ không tính vào số Đà Nẵng + Quảng Nam (chủ app chốt 16/10/2026)."""
import pandas as pd

from app.org import assign_phong, ma_ngoai_chi_nhanh

DM = {"dng.abc": "IBB2"}


def test_cn_ban_ngoai_dng_qnm_ve_ma_ngoai_chi_nhanh():
    ma = ma_ngoai_chi_nhanh()
    assert ma == "NGOAI_CN"
    for cn in ("HUE", "HNI_01", "HCM_TCDT", "QNI", "HPG_02"):
        assert assign_phong("HUE.HuyTQ156", "Phòng kinh doanh 1", cn, "DNG_01", DM) == (ma, False), cn


def test_cn_ban_noi_bo_hoac_la_van_ve_chua_gan_de_soat():
    assert assign_phong("la.hoac", "Phòng nghiệp vụ", "DNG_02", "DNG_02", DM) == ("CHUA_GAN", False)
    assert assign_phong("la.hoac", "", "QNM", "QNM", DM) == ("CHUA_GAN", False)
    assert assign_phong("la.hoac", "", "DNG", "DNG_01", DM) == ("CHUA_GAN", False)         # CN Bán lạ "DNG": người quản trị soát
    assert assign_phong("la.hoac", "", "", "DNG_01", DM) == ("CHUA_GAN", False)            # CN Bán trống


def test_ecom_danh_muc_va_phong_he_thong_van_uu_tien_truoc():
    assert assign_phong("HCM.ECOM.x", "", "HCM_ECOM", "QNM", DM) == ("ECOM_QNM", True)
    assert assign_phong("DNG.ABC", "", "HNI_01", "DNG_01", DM) == ("IBB2", False)           # có trong danh mục thì về phòng của họ
    assert assign_phong("ai.do", "Phòng kỹ thuật", "DNG_02", "DNG_02", DM) == ("KT_DNG2", False)
    assert assign_phong("x", "", "HNI_06", "DNG_01", DM, doi_tuong_kh="VIP 7") == ("ANCS", False)


def test_bao_cao_tong_khong_con_dong_chua_gan_khi_het_so(monkeypatch):
    """Số của mã ngoại chi nhánh không thuộc dòng phòng nào nên không vào bảng, không vào dòng tổng;
    "Chưa gán phòng" hết số thì ẩn."""
    from app import overview as ov
    from app.org import phong_order

    ma_phong = [p["code"] for p in phong_order("2026-09")]
    assert "CHUA_GAN" in ma_phong and ma_ngoai_chi_nhanh() not in ma_phong
    so = pd.DataFrame({"online": [5, 7, 3]}, index=["IBB2", "CHUA_GAN", ma_ngoai_chi_nhanh()])
    monkeypatch.setattr(ov, "_so_lieu_phong", lambda tu, den: so)
    bang, _ = ov.bang_tong_quan("2026-09", 11)
    toan = bang[bang.phong_code == "TOTAL"].iloc[0]
    assert toan.online == 12                                                              # 5 + 7: mã ngoại chi nhánh bị bỏ
    so.loc["CHUA_GAN", "online"] = 0
    bang, _ = ov.bang_tong_quan("2026-09", 11)
    assert "CHUA_GAN" not in set(bang.phong_code) and bang[bang.phong_code == "TOTAL"].iloc[0].online == 5
