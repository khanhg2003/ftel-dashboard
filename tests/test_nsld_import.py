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


def test_nsld_phong_bang_tong_itn_nguoi_duoc_xet_chia_so_nguoi_duoc_xet():
    nsld, den, df = _nsld()
    bang = nsld.nsld_theo_phong(df, den)
    thang = df[(df.so_thang == den) & ~df.dieu_kien.fillna("").isin(["Không xét"])]
    du = bang[bang.loai_dong == "data"]
    for r in du.itertuples():
        d = thang[thang.phong_code == r.phong_code]
        assert getattr(r, f"t{den}") == round(d.diem_itn.sum() / len(d), 2)
    tong = bang[bang.loai_dong == "total"].iloc[0]
    assert tong[f"t{den}"] == round(du[f"t{den}"].mean(), 2)          # Total = TB cộng các phòng
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


def test_file_bo_sung_chi_cap_nhat_acc_trong_file():
    from openpyxl import Workbook

    from app.mau_nhap import COT_NHAN_SU, SHEET_BO_SUNG, xem_truoc_nhan_su
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_BO_SUNG
    ws.append(COT_NHAN_SU + ["Vấn đề app phát hiện"])
    ws.append(["DNG.KiemThuBoSung", "IBB1", None, None, None, None, "Chưa có trong danh mục"])
    buf = io.BytesIO()
    wb.save(buf)
    kq = xem_truoc_nhan_su(buf.getvalue())
    assert list(kq.loai) == ["Thêm mới"]           # không đánh dấu nghỉ ai khác


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


# ------------------------------------------------------ đối chiếu số liệu giữa các trang
def test_bao_cao_phong_tong_khop_bao_cao_tong_moi_phong():
    """Người chỉ bán V.VIP/Camera (không có online) vẫn phải được cộng vào TỔNG PHÒNG."""
    from app import bao_cao_phong as bp
    from app.org import phong_order
    from app.overview import bang_tong_quan
    tq, _ = bang_tong_quan("2026-09", 11)
    tq = tq[tq.loai_dong == "data"].set_index("phong_code")
    for p in phong_order("2026-09"):
        nv = bp.bang_nhan_su("2026-09", 11, p["code"])
        t = nv[nv.loai_dong == "total"].iloc[0]
        for k, kq in (("online", "online"), ("vvip", "vvip"), ("camera", "camera"), ("ton", "so_ton")):
            assert int(t[k]) == int(tq.loc[p["code"], kq]), (p["code"], k)


def test_so_sanh_acc_khong_nhan_doi_nguoi_ban_nhieu_phong():
    from app.metrics import so_sanh_acc
    ss = so_sanh_acc(("2026-09-01", "2026-09-11"), ("2026-09-01", "2026-09-11"))
    assert not ss.acc.duplicated().any() and ss.ky2.sum() == 1394


def test_hieu_suat_nhan_su_gan_phong_cho_acc_ngoai_danh_muc():
    from app.hr_metrics import hieu_suat_nhan_su
    df = hieu_suat_nhan_su("2026-09", ngay=11)
    assert df.phong_code.notna().sum() >= (df.online > 0).sum() - 1
    assert df[df.phong_code.str.startswith("KT_", na=False)].online.sum() > 0


GOC = Path(__file__).resolve().parent.parent
SHEET = GOC / "Báo cáo T9-2026 - T9.2026.csv"


@pytest.mark.skipif(not SHEET.exists(), reason="Không có file Google Sheet gốc để đối chiếu")
def test_bao_cao_tong_khop_google_sheet_goc_ngay_11():
    """Đối chiếu từng ô với bảng tổng trong Google Sheet (chốt 11/09/2026).

    Ngoại lệ đã biết, không phải lỗi app:
    - IBB6 / Phòng CUS DNG2: BGĐ chốt TIN.MinhLH1 chỉ tính cho CUS DNG2 (sheet tính cả hai nơi).
    - Nhân sự, Camera, Tăng trưởng/Kết luận của KT/CUS/ECOM: sheet đếm khác (xem báo cáo đối chiếu).
    """
    import re
    import unicodedata

    import pandas as pd

    from app.overview import bang_tong_quan
    d = pd.read_csv(SHEET, header=None, low_memory=False, dtype=str)
    cot = ["phong", "nhan_su", "mt_internet", "so_ton", "online", "htkh_internet", "ck_online",
           "tang_truong", "fpl_combo", "fpl_ty_le", "cnql", "cnql_ty_le", "vvip", "vvip_ty_le",
           "mt_camera", "camera", "htkh_camera", "mt_ngay", "ngay_ban_moi", "ngay_online", "ngay_vvip"]
    sheet = d.iloc[3:27, :21].copy()
    sheet.columns = cot
    app, _ = bang_tong_quan("2026-09", 11)
    app["_k"] = [unicodedata.normalize("NFC", str(x)).upper() for x in app.phong]

    def so(v):
        s = str(v).replace("%", "").strip()
        if re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):
            s = s.replace(".", "")
        return float(s.replace(",", "."))

    # `mt_ngay` CỐ TÌNH không đối chiếu với sheet: sheet dùng một con số cố định nhập tay, app tính
    # ngược từ phần còn thiếu của mục tiêu tháng (chủ app chốt 28/09/2026 - xem `_mt_ngay_can`).
    # Ví dụ IBB4 ngày 11: sheet ghi 9, app ra 10 vì còn thiếu 183 chia 20 ngày là 9,15.
    kiem = ["mt_internet", "so_ton", "online", "ck_online", "fpl_combo", "cnql", "vvip", "mt_camera",
            "ngay_ban_moi", "ngay_online"]
    for _, r in sheet.iterrows():
        ten = unicodedata.normalize("NFC", str(r.phong)).strip()
        if ten in ("IBB6", "Phòng CUS DNG2", "ANCS") or ten.startswith("BẦY DNG_1"):
            continue
        dong = app[app._k == ten.upper()]
        assert len(dong), ten
        for c in kiem:
            assert so(r[c]) == float(dong.iloc[0][c]), (ten, c, r[c], dong.iloc[0][c])


def test_tong_chi_nhanh_khong_cong_nhan_su_muc_tieu_ancs_nhu_sheet():
    from app.overview import bang_tong_quan
    df, _ = bang_tong_quan("2026-09", 11)
    data = df[df.loai_dong == "data"].set_index("phong_code")
    tong = df[df.loai_dong == "total"].iloc[0]
    assert tong.mt_internet == 4530 == data.mt_internet.sum() - data.loc["ANCS", "mt_internet"]
    assert tong.nhan_su == data.nhan_su.sum() - data.loc["ANCS", "nhan_su"]
    assert tong.online == data.online.sum() == 1394          # số thực hiện vẫn tính đủ
    assert tong.so_ton == data.so_ton.sum()


def test_ket_luan_dat_khi_online_bang_muc_tieu_ngay():
    from app.overview import bang_tong_quan
    df, _ = bang_tong_quan("2026-09", 11)
    d = df[df.loai_dong == "data"]
    assert (d[d.ngay_online >= d.mt_ngay].ket_luan == "Đạt").all()
    assert (d[d.ngay_online < d.mt_ngay].ket_luan == "Không đạt").all()


# ------------------------------------------------------ Báo cáo Tổng theo khoảng ngày
def test_khoang_ngay_luy_ke_giong_cach_cu_va_khoang_tu_chon_cong_dung():
    from app.metrics import tong_theo_phong
    from app.overview import bang_tong_quan
    a, _ = bang_tong_quan("2026-09", 11)
    b, _ = bang_tong_quan("2026-09", 11, tu="2026-09-01")
    ta, tb = a[a.loai_dong == "total"].iloc[0], b[b.loai_dong == "total"].iloc[0]
    assert ta.online == tb.online == 1394 and ta.ck_online == tb.ck_online == 1381
    c, _ = bang_tong_quan("2026-09", 11, tu="2026-09-05")
    tc = c[c.loai_dong == "total"].iloc[0]
    assert tc.online == int(tong_theo_phong("2026-09-05", "2026-09-11").n.sum())
    assert tc.ck_online == int(tong_theo_phong("2026-08-05", "2026-08-11").n.sum())
    assert tc.ngay_online == ta.ngay_online and tc.mt_internet == ta.mt_internet   # ngày cuối, mục tiêu tháng


def test_nut_chon_ky_bao_cao_tong():
    from app.ui.pages.tongquan import doi_ky
    ngays = [f"2026-09-{i:02d}" for i in range(1, 15)]
    assert doi_ky("tq-lui", None, "2026-09-01", "2026-09-14", ngays) == ("2026-09-01", "2026-09-13")
    assert doi_ky("tq-lui", None, "2026-09-08", "2026-09-14", ngays) == ("2026-09-07", "2026-09-13")
    assert doi_ky("tq-nhanh", "7ngay", None, None, ngays) == ("2026-09-08", "2026-09-14")
    assert doi_ky("tq-nhanh", "tuan", None, None, ngays) == ("2026-09-14", "2026-09-14")   # 14/09/2026 là thứ 2
    assert doi_ky("tq-nhanh", "cungky", "2026-09-01", "2026-09-14", ngays) == ("2026-08-01", "2026-08-14")
    assert doi_ky("tq-nhanh", "thangtruoc", "2026-09-01", "2026-09-14", ngays) == ("2026-08-01", "2026-08-31")
    assert doi_ky("tq-p-moinhat", None, "2026-09-05", "2026-09-06", ngays) == ("2026-09-01", "2026-09-14")


def test_anh_va_excel_theo_khoang_ngay():
    from app.export_excel import xuat_tong_quan
    from app.export_png import anh_tong_quan
    _, ten = anh_tong_quan("2026-09", 11, tu="2026-09-05")
    assert ten == "BaoCaoTong_ToanCN_20260905_den20260911.png"
    _, ten2 = xuat_tong_quan("2026-09", 11)
    assert ten2 == "BaoCaoTong_ToanCN_202609_ngay11.xlsx"


# ------------------------------------------------------ nạp file NSLĐ: nhận tháng
def test_nhan_thang_tu_ten_file_nsld():
    from datetime import datetime

    from app.ingest.commit import thang_tu_ten_file
    nay = datetime(2026, 9, 14)
    assert thang_tu_ten_file("T5.xlsx", nay) == "2026-05"
    assert thang_tu_ten_file("NSLĐ tháng 5.xlsx", nay) == "2026-05"
    assert thang_tu_ten_file("NSLĐ Tháng 7.2026.xlsx", nay) == "2026-07"
    assert thang_tu_ten_file("NSLĐ T8.2026.xlsx", nay) == "2026-08"
    assert thang_tu_ten_file("NSLĐ T12.xlsx", nay) == "2025-12"          # tháng sau hiện tại -> năm trước
    assert thang_tu_ten_file("Chi tiết báo cáo PTTB NET(47).xlsx", nay) is None


@pytest.mark.skipif(not (Path(__file__).resolve().parent.parent / "NSLĐ T8.2026.xlsx - DNG.csv").exists(),
                    reason="Không có file NSLĐ mẫu")
def test_nhan_thang_nsld_tu_noi_dung_file_uu_tien_hon_ten_file():
    from app.ingest.loader import load_file
    from app.ui.pages.upload import thang_nsld
    goc = Path(__file__).resolve().parent.parent
    res = [r for r in load_file(goc / "NSLĐ T8.2026.xlsx - DNG.csv") if r.dataset == "nhan_su"][0]
    thang, cach = thang_nsld(res, "T5.xlsx")          # tên file ghi nhầm T5
    assert thang == "2026-08" and "dữ liệu" in cach


# ------------------------------------------------------ chất lượng dữ liệu
def test_chat_luong_du_lieu_cac_muc_kiem_tra():
    from app.admin_service import (acc_la, acc_trung_danh_muc, chua_gan_phong, do_moi_du_lieu,
                                   hd_bat_thuong, nv_thieu_ho_so)
    moi = do_moi_du_lieu()
    assert [m["loai"] for m in moi] == ["Internet", "Truyền hình", "Camera"] and moi[0]["ngay"]
    cg = chua_gan_phong("2026-09")
    assert set(cg.columns) >= {"loai", "acc", "so_hd"}
    al = acc_la("2026-09")
    assert set(al.nhom) <= {"Cần xem", "Kỹ thuật / CUS"}
    assert not al[al.nhom == "Kỹ thuật / CUS"].dang_tinh_cho.str.startswith("IBB").any()
    th = nv_thieu_ho_so("2026-09")
    assert set(th.chi_nhanh) <= {"DNG", "QNM"}
    trung = acc_trung_danh_muc()
    # acc chốt trong staff_overrides.yml (TIN.MinhLH1 -> IBB3) chỉ bị báo khi danh mục khai khác phòng đã chốt
    from sqlalchemy import text

    from app.db import engine
    with engine.connect() as c:
        khai = {r[0] for r in c.execute(text("SELECT phong_code FROM staff_map WHERE acc_norm = 'tin.minhlh1'"))}
    assert ("tin.minhlh1" in set(trung.acc.str.lower())) == bool(khai and "IBB3" not in khai)
    assert "phong" in hd_bat_thuong("2026-09").columns


def test_trang_chat_luong_dung_duoc():
    from app.ui.pages import chatluong
    goc = chatluong.layout()
    assert goc is not None and chatluong.topbar()
