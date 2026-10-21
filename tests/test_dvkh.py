"""Khối DVKH: đọc file Excel, nạp database, các chỉ số, nhận định và quyền theo khối."""
from __future__ import annotations

from datetime import date, datetime
from io import BytesIO

import pandas as pd
import pytest
from openpyxl import Workbook
from sqlalchemy import text

from app.auth import SessionUser
from app.db import engine
from app.dvkh import cheo, doc_file, insight, nap, so_lieu as sl, tong_quan
from app.models import User
from app.ui import khoi

COT_SR_BD = ["Chi nhánh", "Quận huyện", "Mã SR", "Số hợp đồng", "Loại yêu cầu", "Kết quả tư vấn", "Thời gian yêu cầu", "Thời gian cập nhật lần đầu",
             "Tình trạng xử lý", "Người xử lý", "Đơn vị xử lý", "Quá hạn", "Tình trạng NET hiện tại", "Cột lạ không cần"]
COT_SR_CD = ["Mã chi nhánh", "Quận huyện", "Mã SR", "Số hợp đồng", "Nhóm chương trình", "Chương trình", "Thời gian đổ dữ liệu", "Kết quả liên hệ",
             "Kết quả tư vấn", "Tình trạng xử lý", "Người xử lý", "Quá hạn", "Thời gian phân công nhân sự xử lý", "Thời gian cập nhật lần đầu", "Điểm nguy cơ RM"]
TIEU_DE_RM = ["", "KH hiện hành", "KH đầu kỳ", "Gross PTTB", "Hủy SSD", "CTBDV", "CTBDV khôi phục DV", "HSSD khôi phục", "CTBDV chuyển HSSD", "Chờ thanh lý",
              "Chờ thanh lý KPDV", "Chờ thanh lý HSSD", "CTBDV dự kiến", "KH rời mạng", "Tỷ lệ rời mạng so với KH Active hiện hành",
              "Tỷ lệ rời mạng so với Gross PTTB", "Net PTTB", "Tỷ lệ giữ lại", "Tỷ lệ tăng trưởng"]
TIEU_DE_RM_QUAN = ["Name", "KH Active hiện hành", "KH Active đầu kỳ", "Gross PTTB", "Hủy TSD", "Hủy SSD", "Chờ thanh lý", "Chờ thanh lý KPDV", "Chờ thanh lý HSSD",
                   "CTBDV", "CTBDV khôi phục DV", "HSSD khôi phục", "CTBDV chuyễn HSSD", "CTBDV dự kiến", "KH rời mạng", "Tỷ lệ % rời mạng so với KH Active hiện hành",
                   "Tỷ lệ % rời mạng so với Gross PTTB", "Net PTTB", "Tỷ lệ % giữ lại", "Tỷ lệ % tăng trưởng"]


def _sr_bd(n: int = 40, thanh_ly: int = 10, khong_dong_y: int = 6):
    """n SR bị động: `thanh_ly` SR thanh lý (`khong_dong_y` khách không đồng ý, còn lại đồng ý ở lại), còn lại thắc mắc; 1/4 đang xử lý (quá hạn)."""
    rows = []
    for i in range(n):
        tl = i < thanh_ly
        tv = ("Khách hàng không đồng ý sử dụng tiếp" if i < khong_dong_y else "Khách hàng đồng ý sử dụng tiếp và không cần hỗ trợ") if tl else "Khách hàng đồng ý"
        dang = i % 4 == 0
        rows.append(["DNG_01" if i % 2 == 0 else "DNG_02", "Phường Thanh Khê", f"SR-{i}", f"DA{i % 30:03d}", "Thanh lý" if tl else "Thắc mắc", tv,
                     datetime(2026, 10, 1 + i % 5, 9, 0), datetime(2026, 10, 1 + i % 5, 9, 20), "Đang xử lý" if dang else "Đã hoàn tất",
                     "NhanVienA" if i % 2 else "nhanvienb", "Phòng dịch vụ khách hàng 1", "Quá hạn đang xử lý " if dang else "Hoàn tất trong hạn",
                     "Đã chấm dứt hợp đồng" if i < 3 else "Bình thường", "x"])
    return rows


def _sr_cd(n: int = 40):
    rows = []
    for i in range(n):
        rows.append(["DNG_01" if i % 2 == 0 else "DNG_02", "Phường Hải Châu", f"CD-{i}", f"DA{i % 30:03d}", "Nguy cơ rời mạng (SOS)", "Ngưng kết nối",
                     datetime(2026, 10, 1 + i % 6, 7, 0), "Không liên lạc được" if i % 4 == 0 else "Gặp trực tiếp người sử dụng",
                     "KH đồng ý sử dụng tiếp và không cần hỗ trợ" if i % 4 else None, "Chưa xử lý" if i % 5 == 0 else "Đã hoàn tất",
                     "autocall" if i % 10 == 0 else "cskhA", "Hoàn tất trong hạn", datetime(2026, 10, 1 + i % 6, 7, 5), datetime(2026, 10, 1 + i % 6, 8, 0),
                     850 if i % 3 == 0 else -1])
    return rows


def tao_file(sr_bd=None, sr_cd=None, dao_cot: bool = False) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "SR bị động"
    h = list(COT_SR_BD)
    data = sr_bd if sr_bd is not None else _sr_bd()
    if dao_cot:                                   # cột đổi chỗ nhưng vẫn nhận đúng theo tên
        h, data = h[::-1], [r[::-1] for r in data]
    ws.append(h)
    for r in data:
        ws.append(r)
    ws = wb.create_sheet("SR chủ động")
    ws.append(COT_SR_CD)
    for r in (sr_cd if sr_cd is not None else _sr_cd()):
        ws.append(r)
    ws = wb.create_sheet("rời mạng")
    for r in (["bảng rời mạng theo phòng theo ngày T"], [], ["Chi nhánh", "Số khách hàng Active"], TIEU_DE_RM,
              ["05.Da Nang", 1000, 990, 10, 3, 0, 1, 2, 0, 0, 0, 0, 5, 5, 0.5, 50, 5, 99.5, 0.4],
              ["DNG-01", 500, 495, 4, 1, 0, 0, 1, 0, 0, 0, 0, 2, 2, 0.4, 50, 2, 99.6, 0.3],
              ["Tổng", "1,000", "990", "10"], [], ["bảng rời mạng theo quận theo ngày T"], [], TIEU_DE_RM_QUAN,
              ["05.Da Nang", 1000, 990, 10, 0, 3, 0, 0, 0, 0, 1, 2, 0, 5, 5, 0.5, 50, 5, 99.5, 0.4],
              ["Phuong Hai Chau", 800, 790, 8, 0, 2, 0, 0, 0, 0, 1, 1, 0, 4, 4, 0.5, 50, 4, 99.5, 0.4],
              ["Tổng cộng", 1000, 990, 10, 0, 3, 0, 0, 0, 0, 1, 2, 0, 5, 5, 0.5, 50, 5, 99.5, 0.4]):
        ws.append(r)
    ws = wb.create_sheet("công nợ")
    for r in (["Tỷ lệ công nợ hằng ngày theo phòng"], ["Công nợ T9.26", datetime(2026, 10, 1), None, datetime(2026, 10, 2)],
              ["", "Ty le DT", "Tỉ lệ bill", "Ty le DT", "Tỉ lệ bill"], ["To tal DNG CN 30", 0.2, 0.1, 0.4, 0.3], ["DNG1", 0.25, 0.12, 0.45, 0.35], [],
              ["Dữ liệu hệ thống đổ hằng ngày"], [], ["Tháng", "Số HĐ", "Tổng tiền", "HĐ Đã TT", "TT Đã TT", "HĐ còn nợ", "TT còn nợ", "Tỷ lệ theo DT", "Tỷ lệ theo bill"],
              ["2026.09", 100, 1_000_000, 90, 900_000, 10, 100_000, 90.0, 90.0], ["+Tổng DNG_1", 100, 1_000_000, 90, 900_000, 10, 100_000, 90.0, 90.0],
              ["++Tổng 05.Da Nang", 200, 2_000_000, 180, 1_800_000, 20, 200_000, 90.0, 90.0]):
        ws.append(r)
    ws = wb.create_sheet("data")
    ws.append(["YCH", None, "Nợ cước"])
    for y, c in (("da001", "DA002"), ("DA003", "DA004")):
        ws.append([y, None, c])
    b = BytesIO()
    wb.save(b)
    return b.getvalue()


@pytest.fixture
def sach_dvkh():
    """Mỗi phép kiểm bắt đầu và kết thúc với các bảng dv_* trống (database kiểm thử dùng chung)."""
    def don():
        nap.dam_bao_bang()
        with engine.begin() as c:
            for t in ("dv_nap", "dv_sr_bi_dong", "dv_sr_chu_dong", "dv_roi_mang", "dv_cong_no", "dv_cong_no_chot", "dv_danh_sach"):
                c.execute(text(f"DELETE FROM {t}"))
    don()
    yield
    don()


# ------------------------------------------------------------------ đọc file
def test_doc_file_nhan_cot_theo_ten_va_chuan_hoa():
    kq = doc_file.doc_file(tao_file())
    bd, cd = kq["sr_bd"], kq["sr_cd"]
    assert len(bd) == 40 and len(cd) == 40 and kq["canh_bao"] == []
    assert "cot_la" not in bd.columns and "Cột lạ không cần" not in bd.columns
    assert set(bd["nguoi_xu_ly"]) == {"nhanviena", "nhanvienb"}                      # tài khoản không phân biệt hoa thường
    assert "Quá hạn đang xử lý" in set(bd["qua_han"])                               # bỏ khoảng trắng thừa ở cuối
    assert bd["tg_yc"].dtype.kind == "M" and bd["so_hd"].iloc[0] == "DA000"
    assert kq["ych"] == ["DA001", "DA003"] and kq["no_cuoc"] == ["DA002", "DA004"]   # chuẩn hoá chữ hoa


def test_doc_file_cot_doi_cho_van_dung():
    a = doc_file.doc_file(tao_file())["sr_bd"].sort_values("ma_sr").reset_index(drop=True)
    b = doc_file.doc_file(tao_file(dao_cot=True))["sr_bd"].sort_values("ma_sr").reset_index(drop=True)
    pd.testing.assert_frame_equal(a[sorted(a.columns)], b[sorted(b.columns)])


def test_doc_roi_mang_va_cong_no():
    kq = doc_file.doc_file(tao_file())
    rm = {(r["cap"], r["ten"]): r for r in kq["roi_mang"]}
    assert rm[("phong", "05.Da Nang")]["kh_roi_mang"] == 5 and rm[("phong", "DNG-01")]["kh_active"] == 500
    assert ("phong", "Tổng") not in rm and ("quan", "Tổng cộng") not in rm            # dòng tổng của bảng không phải đơn vị
    assert rm[("quan", "Phuong Hai Chau")]["huy_ssd"] == 2 and rm[("quan", "Phuong Hai Chau")]["ctbdv_khoi_phuc"] == 1
    ngay = {(r["ten"], r["ngay"]): r for r in kq["chuoi_cong_no"]}
    assert ngay[("To tal DNG CN 30", date(2026, 10, 2))]["ty_le_bill"] == 0.3 and kq["chuoi_cong_no"][0]["ky_no"] == "2026-09"
    chot = {r["ten"]: r for r in kq["chot_cong_no"]}
    assert chot["DNG_1"]["so_hd"] == 100 and chot["Đà Nẵng"]["hd_con_no"] == 20


# ------------------------------------------------------------------ nạp database
def test_nap_hai_lan_khong_cong_don_sr(sach_dvkh):
    kq = doc_file.doc_file(tao_file())
    r1 = nap.nap(kq, date(2026, 10, 8), "a.xlsx", "tester")
    r2 = nap.nap(doc_file.doc_file(tao_file()), date(2026, 10, 8), "a.xlsx", "tester")
    assert r1["sr_bd"] == r2["sr_bd"] == 40
    with engine.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM dv_sr_bi_dong")).scalar() == 40
        assert c.execute(text("SELECT COUNT(*) FROM dv_roi_mang")).scalar() == 4                       # cùng ngày chốt: ghi đè, không nhân đôi
        assert c.execute(text("SELECT COUNT(*) FROM dv_nap")).scalar() == 2
        assert c.execute(text("SELECT COUNT(*) FROM dv_sr_chu_dong WHERE no_cuoc = 1")).scalar() > 0     # đã gắn cờ nợ cước từ danh sách
        assert c.execute(text("SELECT COUNT(*) FROM dv_sr_bi_dong WHERE ych = 1")).scalar() > 0
    assert len(nap.lich_su()) == 2


def test_nap_ngay_chot_khac_giu_lich_su_va_sr_moi_thay_cu(sach_dvkh):
    nap.nap(doc_file.doc_file(tao_file()), date(2026, 10, 8), "a.xlsx")
    moi = _sr_bd()
    moi[0][8] = "Đã hoàn tất"                                                       # SR-0 trước đang xử lý, nay đã xong
    nap.nap(doc_file.doc_file(tao_file(sr_bd=moi)), date(2026, 10, 9), "b.xlsx")
    with engine.connect() as c:
        assert c.execute(text("SELECT tinh_trang FROM dv_sr_bi_dong WHERE ma_sr = 'SR-0'")).scalar() == "Đã hoàn tất"
        assert c.execute(text("SELECT COUNT(*) FROM dv_roi_mang")).scalar() == 8                       # hai ngày chốt
    assert sl.ngay_du_lieu()["nap"] == date(2026, 10, 9)


# ------------------------------------------------------------------ chỉ số
def test_chi_so_sr_bi_dong_va_giu_chan(sach_dvkh):
    nap.nap(doc_file.doc_file(tao_file()), date(2026, 10, 8), "a.xlsx")
    bd = sl.sr_bi_dong()
    k = sl.kpi_bd(bd)
    assert k["so_sr"] == 40 and k["ton"] == 10 and k["qua_han"] == 10 and k["thanh_ly"] == 10 and k["roi_mang_sau"] == 3
    tl = bd[bd["loai_yc"] == "Thanh lý"]
    assert int(tl["o_lai"].sum()) == 4 and int(tl["muon_di"].sum()) == 6                # "không đồng ý" không bị đếm là đồng ý
    ns = sl.theo_nhan_su_bd(bd)
    assert set(ns["nhan_su"]) == {"nhanviena", "nhanvienb"} and int(ns["phan_cong"].sum()) == 40


def test_chi_so_sr_chu_dong_tach_tai_khoan_may(sach_dvkh):
    nap.nap(doc_file.doc_file(tao_file()), date(2026, 10, 8), "a.xlsx")
    cd = sl.sr_chu_dong()
    k = sl.kpi_cd(cd)
    assert k["so_sr"] == 40 and k["tu_dong"] == 4 and k["khong_lien_lac"] == 10
    assert abs(k["ty_le_khong_lien_lac"] - 10 * 100 / k["da_thu_lien_he"]) < 1e-9       # chỉ tính trên SR đã thử liên hệ
    assert "autocall" not in set(sl.theo_nhan_su_cd(cd)["nhan_su"])
    assert set(cd["nhom_bc"]) == {"Nguy cơ rời mạng (SOS)"}


def test_tong_quan_luy_ke_va_trong_ngay(sach_dvkh):
    nap.nap(doc_file.doc_file(tao_file()), date(2026, 10, 8), "a.xlsx")
    luy_ke = tong_quan.tinh(date(2026, 10, 3), "luy_ke")["sr"]["DNG"]["bd"]
    ngay = tong_quan.tinh(date(2026, 10, 3), "ngay")["sr"]["DNG"]["bd"]
    assert luy_ke["so_sr"] == 24 and ngay["so_sr"] == 8                                   # SR ngày 1-3/10 so với riêng ngày 3/10
    assert tong_quan.tinh(date(2026, 10, 3))["sr_truoc"]["DNG"]["bd"] is None             # chưa nạp tháng trước: để trống, không đoán
    assert tong_quan.tinh(date(2026, 10, 8))["roi_mang"]["DNG"]["kh_roi_mang"] == 5


# ------------------------------------------------------------------ nhận định
def test_nhan_dinh_rong_khi_chua_co_du_lieu(sach_dvkh):
    assert insight.tao_nhan_dinh() == []


def test_nhan_dinh_nghiem_trong_len_dau_va_co_goi_y(sach_dvkh):
    nap.nap(doc_file.doc_file(tao_file(sr_bd=_sr_bd(120, 40, 24))), date(2026, 10, 8), "a.xlsx")
    ds = insight.tao_nhan_dinh()
    assert ds and all({"muc", "chu_de", "tieu_de", "noi_dung", "goi_y"} <= set(x) for x in ds)
    thu_tu = [insight.THU_TU_MUC[x["muc"]] for x in ds]
    assert thu_tu == sorted(thu_tu)
    tl = next(x for x in ds if x["chu_de"] == "Giữ chân khách" and "thanh lý" in x["tieu_de"].lower() and "giữ lại" in x["tieu_de"])
    assert "40%" in tl["tieu_de"]                                                       # 16 trên 40 khách đã tư vấn đồng ý ở lại
    assert cheo.hop_dong_hai_nguon(sl.sr_bi_dong(), sl.sr_chu_dong()).shape[0] > 0


# ------------------------------------------------------------------ quyền theo khối
def _nguoi(role: str) -> SessionUser:
    return SessionUser(User(id=1, username="t", ho_ten="T", role=role, scope="[]", ma_nv=None, session_version=0))


def test_khoi_cua_duong_dan():
    assert khoi.khoi_cua_duong_dan("/dvkh") == khoi.DVKH and khoi.khoi_cua_duong_dan("/dvkh/cong-no") == khoi.DVKH
    assert khoi.khoi_cua_duong_dan("/kt") == khoi.KT and khoi.khoi_cua_duong_dan("/") == khoi.KD and khoi.khoi_cua_duong_dan("/phong") == khoi.KD
    assert khoi.khoi_cua_duong_dan("/taikhoan") is None and khoi.khoi_cua_duong_dan("/dvkhxx") == khoi.KD


def test_phan_quyen_theo_khoi():
    admin, dvkh, phong, nvkd = _nguoi("admin"), _nguoi("dvkh"), _nguoi("phong"), _nguoi("nvkd")
    assert admin.khoi_duoc_xem() == ["KD", "DVKH", "KT"] and all(admin.vao_duoc(p) for p in ("/", "/dvkh", "/dvkh/nap", "/kt"))
    assert dvkh.khoi_duoc_xem() == ["DVKH"] and dvkh.vao_duoc("/dvkh/sr-bi-dong") and dvkh.vao_duoc("/taikhoan")
    assert not dvkh.vao_duoc("/") and not dvkh.vao_duoc("/phong") and not dvkh.vao_duoc("/kt")
    assert phong.khoi_duoc_xem() == ["KD"] and phong.vao_duoc("/phong") and not phong.vao_duoc("/dvkh")
    assert not nvkd.vao_duoc("/dvkh") and nvkd.vao_duoc("/baocaongay")
    assert admin.duoc_nap_dvkh and dvkh.duoc_nap_dvkh and not phong.duoc_nap_dvkh and not nvkd.duoc_nap_dvkh
    assert dvkh.phong_duoc_xem() == [] and dvkh.phong_nhan_su() == []                  # không xem được số liệu bán hàng của khối KD
