"""Kiểm thử: NSLĐ theo phòng / tân binh, file mẫu + import Excel, Việt hoá ô chọn và bảng."""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import DATA_DIR                                        # noqa: E402

pytestmark = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(),
                                reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")


# ------------------------------------------------------------------- NSLĐ
def _nsld():
    from app import nsld
    den = nsld.thang_nsld_den(2026, 9)
    if not den:
        pytest.skip("Database kiểm thử chưa có NSLĐ")
    return nsld, den, nsld.du_lieu(2026, den)


def test_thang_lam_viec_khop_cot_thang_nsld_trong_file():
    _, _, df = _nsld()
    so = df[df.tham_nien_bucket.astype(str).str.fullmatch(r"\d+")]
    assert len(so) and (so.thang_lam_viec == so.tham_nien_bucket.astype(int)).all()
    assert (df[df.tham_nien_bucket == "13+"].thang_lam_viec >= 13).all()


def test_nsld_phong_bang_tong_itn_chia_so_nvkd():
    nsld, den, df = _nsld()
    bang = nsld.nsld_theo_phong(df, den)
    thang = df[df.so_thang == den]
    for r in bang[bang.loai_dong == "data"].itertuples():
        d = thang[thang.phong_code == r.phong_code]
        assert getattr(r, f"t{den}") == round(d.diem_itn.sum() / d.nvkd.sum(), 2)
    tong = bang[bang.loai_dong == "total"].iloc[0]
    assert tong[f"t{den}"] == round(thang.diem_itn.sum() / thang.nvkd.sum(), 2)   # không phải TB các phòng
    assert list(bang.phong.iloc[:3]) == sorted(bang.phong.iloc[:3], key=lambda x: int(x[3:]))


def test_tan_binh_dem_dung_va_ty_le_out():
    nsld, den, df = _nsld()
    bang = nsld.tan_binh_theo_phong(df, 2026, den)
    tong = bang[bang.loai_dong == "total"].iloc[0]
    tb = df[df.ngay_vao.dt.year == 2026]
    assert tong.so_moi == tb.ma_nv.nunique() == bang[bang.loai_dong == "data"].so_moi.sum()
    assert tong.con_lai == tong.so_moi - tong.da_nghi
    assert tong.ty_le_out == round(tong.da_nghi / tong.so_moi * 100)
    k1 = tb[tb.thang_lam_viec == 1].diem_itn
    if len(k1):
        assert tong.k1 == round(k1.mean(), 1)


def test_nsld_tung_nhan_su_va_tan_binh_tung_nguoi():
    nsld, den, df = _nsld()
    ns = nsld.nsld_nhan_su(df, den)
    assert len(ns) == df.ma_nv.nunique() and ns.ho_ten.notna().all()
    tb = nsld.tan_binh_nhan_su(df, 2026, den)
    assert set(tb.tinh_trang) <= {"Đang làm", "Đã nghỉ"}


# ------------------------------------------------------------ file mẫu + import
def test_file_mau_nhan_su_nhap_lai_khong_doi_gi():
    from app.mau_nhap import mau_nhan_su, xem_truoc_nhan_su
    kq = xem_truoc_nhan_su(mau_nhan_su())
    assert len(kq) and set(kq.loai) == {"Không đổi"}


def test_xem_truoc_nhan_su_nhan_dien_thay_doi_va_loi():
    from openpyxl import load_workbook

    from app.mau_nhap import mau_nhan_su, xem_truoc_nhan_su
    wb = load_workbook(io.BytesIO(mau_nhan_su()))
    ws = wb["Nhân sự"]
    acc_doi, phong_cu = ws["A2"].value, ws["B2"].value
    moi = "IBB3" if phong_cu != "IBB3" else "IBB1"
    ws["B2"] = moi
    acc_bo = ws["A3"].value
    ws.delete_rows(3)
    ws.append(["DNG.KiemThuMoi", "IBB1", None, "01/09/2026", None, None])
    ws.append(["DNG.KiemThuLoi", "Phòng không có", None, "31/02/2026", None, None])
    ws.append(["", "IBB1", None, None, None, None])
    buf = io.BytesIO()
    wb.save(buf)
    kq = xem_truoc_nhan_su(buf.getvalue()).set_index("acc")
    assert kq.loc[acc_doi].loai == "Đổi phòng" and kq.loc[acc_doi].phong_moi == moi
    assert kq.loc["DNG.KiemThuMoi"].loai == "Thêm mới"
    assert kq.loc["DNG.KiemThuLoi"].loai == "Lỗi" and "không có trên app" in kq.loc["DNG.KiemThuLoi"].chi_tiet
    if acc_bo not in kq.index or kq.loc[acc_bo].loai != "Không đổi":
        assert kq.loc[acc_bo].loai in ("Đánh dấu nghỉ",)
    assert (kq.loai == "Lỗi").sum() == 2


def test_file_mau_co_cau_nhap_lai_khong_doi_va_bao_loi_bay_sai():
    from openpyxl import load_workbook

    from app.mau_nhap import mau_co_cau, xem_truoc_co_cau
    assert set(xem_truoc_co_cau(mau_co_cau()).loai) == {"Không đổi"}
    wb = load_workbook(io.BytesIO(mau_co_cau()))
    wb["Bầy"].append([None, "BẦY KIỂM THỬ", None, 9, "Có"])
    wb["Phòng"].append([None, "IBB99", "BẦY KIỂM THỬ", "IBB", "DNG", None, 1, "Có"])
    wb["Phòng"].append([None, "IBB98", "BẦY KHÔNG CÓ", "IBB", "DNG", None, 1, "Có"])
    wb["Phòng"].append([None, "IBB97", "BẦY 1", "SAI", "HN", None, 1, "Có"])
    buf = io.BytesIO()
    wb.save(buf)
    kq = xem_truoc_co_cau(buf.getvalue()).set_index("ten")
    assert kq.loc["BẦY KIỂM THỬ"].loai == "Thêm mới" and kq.loc["IBB99"].loai == "Thêm mới"
    assert kq.loc["IBB98"].loai == "Lỗi" and kq.loc["IBB97"].loai == "Lỗi"
    assert "Chi nhánh" in kq.loc["IBB97"].chi_tiet


def test_file_khong_dung_mau_bao_loi_de_hieu():
    from openpyxl import Workbook

    from app.mau_nhap import xem_truoc_nhan_su
    wb = Workbook()
    wb.active.append(["Cột lạ", "Khác"])
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(ValueError, match="file mẫu"):
        xem_truoc_nhan_su(buf.getvalue())


# ----------------------------------------------------------------- Việt hoá
def test_o_chon_va_bang_mac_dinh_tieng_viet():
    import dash_ag_grid as dag
    from dash import dcc

    from app.ui.viet_hoa import viet_hoa
    viet_hoa()
    d = dcc.Dropdown(id="x", options=[], multi=True)
    assert d.labels["select_all"] == "Chọn tất cả" and d.labels["search"] == "Tìm…"
    assert dcc.Dropdown(id="y", placeholder="Riêng").placeholder == "Riêng"
    g = dag.AgGrid(id="g", dashGridOptions={"pagination": True})
    assert g.dashGridOptions["localeText"]["page"] == "Trang" and g.dashGridOptions["pagination"]


def test_trang_hr_co_hai_tab_va_loc_phong():
    from flask_login import login_user
    from sqlalchemy import select

    from app.auth import SessionUser
    from app.db import session_scope
    from app.models import User
    from app.ui.app import server
    from app.ui.pages import hr
    with session_scope() as s:
        admin = SessionUser(s.execute(select(User).where(User.role == "admin")).scalars().first())
    with server.test_request_context("/"):
        login_user(admin)
        opts = hr._phong_opts("all")
        assert opts[0]["value"] == hr.TAT_CA_KD
        kd = hr._ma_phong(hr.TAT_CA_KD, "all")
        assert kd and set(kd) < set(hr._ma_phong(hr.TAT_CA, "all"))
        assert hr._ma_phong("IBB2", "QNM") == []            # phòng không thuộc chi nhánh đang lọc
    cols = [c["field"] for c in hr._cols_ns("phong", 2026, 8)]
    assert cols[-1] == "tb" and "t8" in cols
    rows = [{"t1": 10.0}, {"t1": 20.0}, {"t1": 30.0}]
    hr._to_mau(rows, ["t1"])
    assert rows[0]["_m_t1"] != rows[2]["_m_t1"] and rows[1]["_m_t1"] == "#FFFFFF"
