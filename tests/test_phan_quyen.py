"""Kiểm thử phân quyền + chặn truy cập + các trang có dựng được không.

Chạy:  python -m pytest -q
Tự tạo 3 tài khoản thử (tiền tố `zz_test_`) rồi xoá sạch khi chạy xong.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from argon2 import PasswordHasher                                     # noqa: E402
from sqlalchemy import delete, select                                 # noqa: E402

from app.config import DATA_DIR                                       # noqa: E402
from app.db import session_scope                                      # noqa: E402
from app.models import AuditLog, User                                 # noqa: E402
from app.org import bay_info, phong_order                             # noqa: E402
from app.overview import bang_tong_quan                               # noqa: E402

THANG = "2026-09"
MK = "Kiemthu@2026"
pytestmark = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(),
                                reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")


def _tao(username: str, role: str, scope: list[str] | None) -> None:
    with session_scope() as s:
        s.execute(delete(User).where(User.username == username))
        s.add(User(username=username, ho_ten="Tài khoản kiểm thử", role=role,
                   password_hash=PasswordHasher().hash(MK),
                   scope=json.dumps(scope) if scope else None, active=True))


@pytest.fixture(scope="module")
def tai_khoan():
    ma_bay = next(iter(bay_info()))
    _tao("zz_test_admin", "admin", None)
    _tao("zz_test_bay", "bay", [ma_bay])              # tài khoản cũ của vai trò đã bỏ
    _tao("zz_test_phong", "phong", ["IBB2"])
    _tao("zz_test_kiem", "phong", ["IBB2", "IBB6"])
    _tao("zz_test_nhaplieu", "operator", None)
    yield {"bay": ma_bay}
    with session_scope() as s:
        s.execute(delete(User).where(User.username.like("zz_test_%")))
        s.execute(delete(AuditLog).where(AuditLog.username.like("zz_test_%")))


def _user(username: str):
    from app.auth import SessionUser
    with session_scope() as s:
        return SessionUser(s.execute(select(User).where(User.username == username)).scalars().one())


# --------------------------------------------------------------- phạm vi xem
def test_admin_xem_toan_bo(tai_khoan):
    u = _user("zz_test_admin")
    assert u.phong_duoc_xem() is None and u.phong_nhan_su() is None
    assert u.duoc_upload and u.duoc_cau_hinh and u.duoc_xem_nhan_su
    assert u.loai_duoc_nap() == {"internet", "fptplay", "camera", "nhan_su", "danh_muc_nv"}


def test_tai_khoan_giam_doc_bay_cu_quy_ve_truong_phong_cac_phong_trong_bay(tai_khoan):
    u = _user("zz_test_bay")
    mong_doi = {p["code"] for p in phong_order() if p["bay"] == tai_khoan["bay"]}
    assert u.role == "phong" and set(u.phong_nhan_su()) == mong_doi and mong_doi
    assert not u.duoc_cau_hinh


def test_truong_phong_xem_so_chung_toan_chi_nhanh_nhung_nhan_su_chi_phong_minh(tai_khoan):
    u = _user("zz_test_phong")
    assert u.phong_duoc_xem() is None                  # Báo cáo Tổng, Tracking, Phân tích: đủ phòng
    assert u.phong_nhan_su() == ["IBB2"]               # chi tiết nhân sự: chỉ phòng mình
    assert u.duoc_xem_nhan_su
    assert not u.duoc_cau_hinh and not u.duoc_chat


def test_truong_phong_nap_duoc_3_file_ban_hang_nhung_khong_nap_duoc_nsld(tai_khoan):
    u = _user("zz_test_phong")
    assert u.duoc_upload and u.loai_duoc_nap() == {"internet", "fptplay", "camera"}
    assert u.duoc_nap("internet") and u.duoc_nap("fptplay") and u.duoc_nap("camera")
    assert not u.duoc_nap("nhan_su") and not u.duoc_nap("danh_muc_nv")


def test_nhap_lieu_cung_chi_nap_file_ban_hang(tai_khoan):
    assert _user("zz_test_nhaplieu").loai_duoc_nap() == {"internet", "fptplay", "camera"}


def test_khong_go_duoc_lan_nap_ngoai_quyen(tai_khoan):
    from sqlalchemy import select as _select

    from app.admin_service import go_bo_lan_nap
    from app.models import UploadBatch
    with session_scope() as s:
        lo = s.execute(_select(UploadBatch).where(UploadBatch.dataset == "nhan_su")).scalars().first()
        ma, nguoi = (lo.id, lo.uploaded_by) if lo else (None, None)
    if ma is None:
        pytest.skip("Database kiểm thử chưa có lần nạp NSLĐ")
    quyen_phong = _user("zz_test_phong").loai_duoc_nap()
    kq = go_bo_lan_nap(ma, "zz_test_phong", loai_cho_phep=quyen_phong, chi_cua_minh=True)
    assert not kq["ok"] and "quyền" in kq["msg"]
    # đúng loại nhưng của người khác nạp cũng không gỡ được
    with session_scope() as s:
        lo2 = s.execute(_select(UploadBatch).where(UploadBatch.dataset == "internet")).scalars().first()
    kq2 = go_bo_lan_nap(lo2.id, "zz_test_phong", loai_cho_phep=quyen_phong, chi_cua_minh=True)
    assert not kq2["ok"] and lo2.uploaded_by != "zz_test_phong"


def test_truong_phong_kiem_nhiem_hai_phong(tai_khoan):
    assert set(_user("zz_test_kiem").phong_nhan_su()) == {"IBB2", "IBB6"}


def test_nhap_lieu_xem_so_chung_nhung_khong_xem_nhan_su(tai_khoan):
    u = _user("zz_test_nhaplieu")
    assert u.phong_duoc_xem() is None and u.phong_nhan_su() == []
    assert u.duoc_upload and not u.duoc_xem_nhan_su and not u.duoc_nap("nhan_su")


def test_loc_nhan_su_giao_dung_pham_vi():
    from app.auth import loc_nhan_su
    assert loc_nhan_su(None, None) is None
    assert loc_nhan_su(None, ["IBB2"]) == ["IBB2"]
    assert loc_nhan_su(["IBB2", "IBB6"], ["IBB2"]) == ["IBB2"]
    assert loc_nhan_su(["IBB6"], ["IBB2"]) == []
    assert loc_nhan_su(None, []) == []


def test_truong_phong_chi_chon_duoc_phong_minh_o_bao_cao_phong(tai_khoan):
    from flask_login import login_user

    from app.ui.app import server
    from app.ui.pages import phong
    with server.test_request_context("/"):
        login_user(_user("zz_test_phong"))
        assert [o["value"] for o in phong.phong_duoc_chon()] == ["IBB2"]
        assert phong.duoc_xem_phong("IBB2") and not phong.duoc_xem_phong("IBB6")
        login_user(_user("zz_test_admin"))
        assert phong.duoc_xem_phong("IBB6")
        login_user(_user("zz_test_nhaplieu"))
        assert not phong.duoc_xem_phong("IBB2")


def test_bao_cao_bi_cat_dung_theo_pham_vi(tai_khoan):
    """Trưởng phòng IBB2 chỉ thấy đúng dòng của mình, tổng bằng số của phòng."""
    full, _ = bang_tong_quan(THANG)
    rieng, _ = bang_tong_quan(THANG, chi_phong=["IBB2"])
    assert set(rieng[rieng.loai_dong == "data"].phong) == {"IBB2"}
    tong_rieng = int(rieng[rieng.loai_dong == "total"].iloc[0].online)
    ibb2 = int(full[full.phong == "IBB2"].iloc[0].online)
    assert tong_rieng == ibb2 == 167
    assert tong_rieng < int(full[full.loai_dong == "total"].iloc[0].online)


# --------------------------------------------------------------- đăng nhập
def test_chua_dang_nhap_thi_bi_day_ve_trang_login():
    from app.ui.app import server
    c = server.test_client()
    r = c.get("/")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    assert c.post("/_dash-update-component", json={}).status_code == 401
    assert c.get("/login").status_code == 200


def test_dang_nhap_sai_va_dung(tai_khoan):
    from app.ui.app import server
    c = server.test_client()
    r = c.post("/login", data={"username": "zz_test_phong", "password": "sai-mat-khau"})
    assert r.status_code == 200 and "Sai tài khoản" in r.get_data(as_text=True)
    r = c.post("/login", data={"username": "zz_test_phong", "password": MK})
    # trưởng phòng vào thẳng Báo cáo phòng của mình
    assert r.status_code == 302 and r.headers["Location"].endswith("/phong")
    assert c.get("/").status_code == 200          # đã vào được app


def test_khoa_tai_khoan_sau_5_lan_sai(tai_khoan):
    from app.auth import KHOA_SAU, xac_thuc
    _tao("zz_test_khoa", "phong", ["IBB2"])
    for _ in range(KHOA_SAU):
        assert xac_thuc("zz_test_khoa", "sai")[0] is None
    u, loi = xac_thuc("zz_test_khoa", MK)          # mật khẩu đúng nhưng đang bị khoá
    assert u is None and "khoá" in loi


# --------------------------------------------------------------- vận hành
def test_healthz_khong_can_dang_nhap_va_khong_lo_so_lieu():
    from app.ui.app import server
    r = server.test_client().get("/healthz")
    assert r.status_code == 200
    d = r.get_json()
    assert d["status"] == "ok" and len(d["du_lieu_moi_nhat"]) == 10
    assert set(d) == {"status", "du_lieu_moi_nhat", "tai_khoan_dang_dung"}


def test_sao_luu_database_tao_ra_file_doc_duoc():
    import sqlite3
    from contextlib import closing

    from scripts.backup_db import sao_luu
    f = sao_luu()
    try:
        assert f and f.exists() and f.stat().st_size > 0
        with closing(sqlite3.connect(f)) as c:   # bản sao phải mở được và có dữ liệu
            assert c.execute("SELECT COUNT(*) FROM fact_internet").fetchone()[0] > 0
    finally:
        if f and f.exists():
            f.unlink()


def test_canh_bao_mat_khau_mac_dinh_khi_khoi_dong():
    from serve import kiem_tra_truoc_khi_chay
    assert isinstance(kiem_tra_truoc_khi_chay(), list)


# --------------------------------------------------------------- dựng trang
@pytest.mark.parametrize("duong_dan", ["/", "/phong", "/phantich", "/tracking", "/sosanh", "/hr",
                                       "/chatluong", "/upload", "/quantri", "/settings"])
def test_cac_trang_dung_duoc_voi_quyen_admin(tai_khoan, duong_dan):
    from flask_login import login_user

    from app.ui.app import _router, server
    with server.test_request_context("/"):
        login_user(_user("zz_test_admin"))
        noi_dung, thanh_tren = _router(duong_dan)
    assert noi_dung is not None and thanh_tren is not None


def test_truong_phong_vao_duoc_trang_nap_du_lieu(tai_khoan):
    from flask_login import login_user

    from app.ui.app import _router, server
    with server.test_request_context("/"):
        login_user(_user("zz_test_phong"))
        noi_dung, _ = _router("/upload")
    assert "không có quyền" not in str(noi_dung.children)


@pytest.mark.parametrize("duong_dan", ["/quantri", "/settings"])
def test_trang_han_che_bi_chan_voi_truong_phong(tai_khoan, duong_dan):
    from flask_login import login_user

    from app.ui.app import _router, server
    with server.test_request_context("/"):
        login_user(_user("zz_test_phong"))
        noi_dung, _ = _router(duong_dan)
    assert "không có quyền" in str(noi_dung.children)


@pytest.mark.parametrize("duong_dan", ["/phong", "/hr"])
def test_nhap_lieu_khong_vao_duoc_trang_nhan_su(tai_khoan, duong_dan):
    from flask_login import login_user

    from app.ui.app import _router, server
    with server.test_request_context("/"):
        login_user(_user("zz_test_nhaplieu"))
        noi_dung, _ = _router(duong_dan)
    assert "không có quyền" in str(noi_dung.children)


def test_truong_phong_vao_duoc_bao_cao_phong(tai_khoan):
    from flask_login import login_user

    from app.ui.app import _router, server
    with server.test_request_context("/"):
        login_user(_user("zz_test_phong"))
        noi_dung, _ = _router("/phong")
    assert "không có quyền" not in str(noi_dung)


def test_phan_hoi_he_thong_theo_quyen_va_xu_ly(tai_khoan):
    from app.phan_hoi import (cap_nhat_phan_hoi, danh_sach_phan_hoi, dem_phan_hoi_moi,
                              luu_phan_hoi, muc_theo_quyen, xoa_phan_hoi)

    u_admin = _user("zz_test_admin")
    u_phong = _user("zz_test_phong")
    u_nhap = _user("zz_test_nhaplieu")

    opts_admin, mac_dinh_admin = muc_theo_quyen(u_admin, "/quantri")
    ten_admin = {o["value"] for o in opts_admin}
    assert "Quản trị hệ thống" in ten_admin
    assert "Tổng quan KPI (DVKH)" in ten_admin
    assert mac_dinh_admin == "Quản trị hệ thống"

    opts_phong, mac_dinh_phong = muc_theo_quyen(u_phong, "/phong")
    ten_phong = {o["value"] for o in opts_phong}
    assert "Báo cáo phòng" in ten_phong
    assert "Quản trị hệ thống" not in ten_phong
    assert "Tổng quan KPI (DVKH)" not in ten_phong
    assert mac_dinh_phong == "Báo cáo phòng"

    opts_nhap, _ = muc_theo_quyen(u_nhap, "/upload")
    ten_nhap = {o["value"] for o in opts_nhap}
    assert "Nạp dữ liệu" in ten_nhap
    assert "Báo cáo phòng" not in ten_nhap
    assert "Nhân sự & NSLĐ" not in ten_nhap

    truoc = dem_phan_hoi_moi()
    ok, msg = luu_phan_hoi(u_phong, "Cải thiện tính năng", "Báo cáo phòng", "Đề xuất thêm cột so sánh nhanh")
    assert ok and "anh/chị" in msg
    assert dem_phan_hoi_moi() == truoc + 1

    ds = [r for r in danh_sach_phan_hoi() if r["username"] == "zz_test_phong"]
    assert ds and ds[0]["muc"] == "Báo cáo phòng"
    ph_id = ds[0]["id"]

    ok_xl, _ = cap_nhat_phan_hoi(ph_id, "da_xu_ly", "Đã bổ sung theo đề xuất", "zz_test_admin")
    assert ok_xl
    assert dem_phan_hoi_moi() == truoc
    assert xoa_phan_hoi([ph_id], "zz_test_admin") == 1
