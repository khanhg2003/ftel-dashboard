"""Kiểm thử đợt hệ thống hoá giao diện: quy tắc cần chú ý chung, chỉ tiêu Tracking, định dạng số,
chặn quyền ở máy chủ, trang Tài khoản của tôi."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import DATA_DIR                                        # noqa: E402

THANG = "2026-09"
MK = "Kiemthu@2026"
pytestmark = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(),
                                reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")


def _tao(username: str, role: str, scope=None) -> None:
    from argon2 import PasswordHasher
    from sqlalchemy import delete

    from app.db import session_scope
    from app.models import User
    with session_scope() as s:
        s.execute(delete(User).where(User.username == username))
        s.add(User(username=username, ho_ten="Kiểm thử", role=role, password_hash=PasswordHasher().hash(MK),
                   scope=json.dumps(scope) if scope else None, active=True))


@pytest.fixture(scope="module")
def tai_khoan():
    _tao("zz_ht_admin", "admin")
    _tao("zz_ht_phong", "phong", ["IBB2"])
    yield
    from sqlalchemy import delete

    from app.db import session_scope
    from app.models import AuditLog, User
    with session_scope() as s:
        s.execute(delete(User).where(User.username.like("zz_ht_%")))
        s.execute(delete(AuditLog).where(AuditLog.username.like("zz_ht_%")))


def _user(username: str):
    from sqlalchemy import select

    from app.auth import SessionUser
    from app.db import session_scope
    from app.models import User
    with session_scope() as s:
        return SessionUser(s.execute(select(User).where(User.username == username)).scalars().one())


def _dang_nhap(username: str):
    from app.ui.app import server
    c = server.test_client()
    assert c.post("/login", data={"username": username, "password": MK}).status_code == 302
    return c


# ------------------------------------------------------- quy tắc cần chú ý
def test_quy_tac_can_chu_y_hai_muc():
    from app import canh_bao as cb
    assert cb.xet(None, 0, 0)[0] == cb.TRAO_DOI_NGAY
    assert cb.xet(7, 0, 5)[0] == cb.TRAO_DOI_NGAY
    assert cb.xet(6, 1, 1)[0] == cb.THEO_DOI                     # 6 ngày liền chưa có số
    assert cb.xet(3, 2, 2)[0] == cb.THEO_DOI
    assert cb.xet(2, 2, 2)[0] == ""
    assert cb.xet(0, 3, 6)[0] == cb.THEO_DOI                     # tuần này giảm đúng một nửa
    assert cb.xet(0, 4, 6)[0] == ""
    assert cb.xet(0, 1, 2)[0] == ""                              # tuần trước dưới 3 số: không xét sụt
    muc, ly_do = cb.xet(0, 5, 5, nsld_chua_dat=True, thang_nsld="08")
    assert muc == cb.THEO_DOI and ly_do == ["NSLĐ T08 chưa đạt"]
    muc, ly_do = cb.xet(9, 0, 6, nsld_chua_dat=True)
    assert muc == cb.TRAO_DOI_NGAY and len(ly_do) == 2           # không ghi thêm "tuần này giảm"


def test_bao_cao_phong_va_nhan_su_cung_muc_can_chu_y():
    """Cùng một người, cùng ngày: hai trang phải cho cùng mức."""
    from app import bao_cao_phong as bp
    from app.hr_metrics import canh_bao_nhan_su, hieu_suat_nhan_su
    ngay = 11
    nv = bp.bang_nhan_su(THANG, ngay, "IBB2")
    nv = nv[nv.loai_dong == "data"].set_index("acc_norm")
    df = hieu_suat_nhan_su(THANG, chi_phong=["IBB2"], ngay=ngay)
    cb = canh_bao_nhan_su(THANG, ngay=ngay, df=df).set_index("acc_norm")
    xet = df[df.dang_lam & df.kd].acc_norm
    chung = [a for a in xet if a in nv.index]
    assert chung
    for a in chung:
        muc_hr = cb.muc_rui_ro.get(a, "") if len(cb) else ""
        assert nv.at[a, "muc_chu_y"] == muc_hr, a
    assert set(nv.muc_chu_y) <= {"", "Trao đổi ngay", "Theo dõi"}


# ------------------------------------------------------- số liệu các trang khớp nhau
def test_tracking_chi_tieu_khop_bao_cao_tong_ca_khi_loc_chi_nhanh():
    from app.metrics import tien_do_thang
    from app.org import loc_chi_nhanh
    from app.overview import bang_tong_quan
    for cn in ("all", "DNG", "QNM"):
        scope = loc_chi_nhanh(None, cn, THANG)
        df, _ = bang_tong_quan(THANG, 11, chi_phong=scope, chi_nhanh=cn)
        tong = df[df.loai_dong == "total"].iloc[0]
        td = tien_do_thang(THANG, den_ngay=11, chi_phong=scope)
        assert td["muc_tieu"] == pytest.approx(float(tong.mt_internet)), cn
        assert td["hien_tai"] == int(tong.online), cn


def test_dinh_dang_so_kieu_viet_nam():
    from app.ui.components import pct_vn, so_vn
    assert so_vn(1438) == "1.438" and so_vn(8.63, 1) == "8,6"
    assert so_vn(12, dau=True) == "+12" and so_vn(-51, dau=True) == "-51"
    assert pct_vn(70.2) == "70%" and pct_vn(-4.8, dau=True) == "-5%" and pct_vn(None) == "–"
    import plotly.io as pio

    import app.ui.app  # noqa: F401  - khởi động app để gắn mẫu biểu đồ
    assert pio.templates[pio.templates.default].layout.separators == ",."


# ------------------------------------------------------- quyền ở máy chủ
def _goi_callback(c, output: str, inputs: list[dict], state=None):
    return c.post("/_dash-update-component", json={
        "output": output, "outputs": [{"id": o.split(".")[0], "property": o.split(".")[1]}
                                      for o in output.strip(".").split("...")],
        "inputs": inputs, "state": state or [], "changedPropIds": [inputs[0]["id"] + "." + inputs[0]["property"]]})


def test_truong_phong_khong_goi_duoc_callback_quan_tri(tai_khoan):
    out = "..qt-user-grid.columnDefs...qt-user-grid.rowData...qt-staff-grid.columnDefs...qt-staff-grid.rowData.."
    vao = [{"id": "qt-user-msg", "property": "children", "value": "x"},
           {"id": "qt-staff-msg", "property": "children", "value": None}]
    r = _goi_callback(_dang_nhap("zz_ht_phong"), out, vao)
    assert r.status_code == 204 and "zz_ht_admin" not in r.get_data(as_text=True)
    r = _goi_callback(_dang_nhap("zz_ht_admin"), out, vao)
    assert r.status_code == 200 and "zz_ht_admin" in r.get_data(as_text=True)


# ------------------------------------------------------- tài khoản của tôi
def test_moi_vai_tro_vao_duoc_trang_tai_khoan(tai_khoan):
    from flask_login import login_user

    from app.ui.app import _router, server
    with server.test_request_context("/"):
        login_user(_user("zz_ht_phong"))
        noi_dung, _ = _router("/taikhoan")
    chu = str(noi_dung)
    assert "tk-doi-mk" in chu and "không có quyền" not in chu and "IBB2" in chu


def test_doi_mat_khau_kiem_tra_nhap_lai(tai_khoan):
    from flask_login import login_user

    from app.auth import xac_thuc
    from app.ui.app import app, server
    ham = app.callback_map["..tk-mk-msg.children...tk-mk-cu.value...tk-mk-moi.value...tk-mk-lai.value.."]["callback"]
    goc = getattr(ham, "__wrapped__", ham)
    with server.test_request_context("/"):
        login_user(_user("zz_ht_phong"))
        msg = goc(1, 0, MK, "MatKhauMoi@1", "khac")
        assert "không khớp" in str(msg[0])
        msg = goc(1, 0, MK, "MatKhauMoi@1", "MatKhauMoi@1")
        assert "Đã đổi mật khẩu" in str(msg[0])
    assert xac_thuc("zz_ht_phong", "MatKhauMoi@1")[0] is not None
    _tao("zz_ht_phong", "phong", ["IBB2"])                      # trả lại mật khẩu cho các test khác


def _callback(chua: str):
    from app.ui.app import app
    khoa = next(k for k in app.callback_map if chua in k)
    ham = app.callback_map[khoa]["callback"]
    return getattr(ham, "__wrapped__", ham)


def test_callback_bao_cao_phong_va_nhan_su_chay_duoc(tai_khoan):
    """Chạy thật callback chính của hai trang có cột cảnh báo (bắt lỗi trùng tên biến, thiếu cột)."""
    from flask_login import login_user

    from app.ui.app import server
    with server.test_request_context("/"):
        login_user(_user("zz_ht_admin"))
        kq = _callback("bp-kpi.children")("2026-09-11", "IBB2", "chu_y", "ban")
        assert "trao đổi ngay" in kq[3] and all(r["muc_chu_y"] for r in kq[5])
        kq = _callback("hr-kpi.children")("2026-09-11", "all", "__kd")
        assert kq[4] is not None and all(r["muc"] in ("Trao đổi ngay", "Theo dõi") for r in kq[4])


# ------------------------------------------------------- đợt 2: menu, gộp trang
def _cac_id(node, out=None):
    out = [] if out is None else out
    if getattr(node, "id", None) is not None:
        out.append(node.id)
    con = getattr(node, "children", None)
    if con is not None and not isinstance(con, str):
        for c in con if isinstance(con, (list, tuple)) else [con]:
            _cac_id(c, out)
    return out


def test_menu_con_8_muc_theo_nhom():
    from app.ui.app import NAV
    muc = [href for _, ds in NAV for href, *_ in ds]
    assert len(muc) == 8 and len(set(muc)) == 8
    assert "/settings" not in muc and "/sosanh" not in muc
    assert [n for n, _ in NAV] == ["Hằng ngày", "Phân tích", "Phòng & nhân sự", "Dữ liệu", "Hệ thống"]


@pytest.mark.parametrize("duong_dan, tim_thay", [
    ("/tracking", "db-pane-ngay"), ("/sosanh", "db-pane-sosanh"), ("/settings", "st-pane-cocau"),
    ("/quantri", "qt-pane-user")])
def test_trang_gop_khong_trung_id_va_mo_dung_tab(tai_khoan, duong_dan, tim_thay):
    from flask_login import login_user

    from app.ui.app import _router, server
    with server.test_request_context("/"):
        login_user(_user("zz_ht_admin"))
        noi_dung, thanh_tren = _router(duong_dan)
    ids = _cac_id(noi_dung) + _cac_id(html_div(thanh_tren))
    trung = {i for i in ids if ids.count(i) > 1}
    assert not trung, trung
    hien = [n for n in _cac_node(noi_dung) if getattr(n, "id", None) == tim_thay][0]
    assert not getattr(hien, "hidden", False) and (getattr(hien, "style", None) or {}).get("display") != "none"


def test_quantri_mo_tab_theo_duong_dan(tai_khoan):
    from flask_login import login_user

    from app.ui.app import _router, server
    with server.test_request_context("/"):
        login_user(_user("zz_ht_admin"))
        noi_dung, _ = _router("/quantri", "?tab=nhatky")
    tab = [n for n in _cac_node(noi_dung) if getattr(n, "id", None) == "qt-tab"][0]
    assert tab.value == "nhatky"


def test_tab_an_khong_tinh(tai_khoan):
    from dash import no_update
    from flask_login import login_user

    from app.ui.app import server
    with server.test_request_context("/"):
        login_user(_user("zz_ht_admin"))
        kq = _callback("tk-kpi.children")(THANG, "online", "ngay", "fit", "all", "bay", {}, "sosanh", {})
        assert all(x is no_update for x in kq)
        kq = _callback("ss-kpi.children")("2026-09-01", "2026-09-05", "2026-09-06", "2026-09-11",
                                          "online", "kd", "all", "ngay")
        assert all(x is no_update for x in kq)
        kq = _callback("ss-kpi.children")("2026-09-01", "2026-09-05", "2026-09-06", "2026-09-11",
                                          "online", "kd", "all", "sosanh")
        assert len(kq[0]) == 6


def html_div(children):
    from dash import html
    return html.Div(children)


def _cac_node(node, out=None):
    out = [] if out is None else out
    out.append(node)
    con = getattr(node, "children", None)
    if con is not None and not isinstance(con, str):
        for c in con if isinstance(con, (list, tuple)) else [con]:
            _cac_node(c, out)
    return out


# ------------------------------------------------------- đợt 3: bộ lọc chung
def test_bo_loc_chung_lam_sach_va_uu_tien_duong_dan():
    from app.ui import ky_chung as kc
    assert kc.lam_sach({"tu": "2026-09-05", "den": "2026-09-01", "cn": "HN", "phong": "<script>"}) == \
        {"den": "2026-09-01"}
    assert kc.doc({"den": "2026-09-10", "cn": "DNG"}, "?den=2026-09-11&tab=sosanh") == \
        {"den": "2026-09-11", "cn": "DNG"}
    assert kc.doc(None, "?tu=2026-13-01&den=abc") == {}
    ngays = ["2026-08-30", "2026-09-01", "2026-09-02", "2026-09-05"]
    assert kc.ngay_co_so("2026-09-04", ngays) == "2026-09-02"
    assert kc.ca_thang("2026-09", ngays) == {"tu": "2026-09-01", "den": "2026-09-05"}
    # luỹ kế tháng -> kỳ 1 là cùng kỳ tháng trước; khoảng tự chọn -> khoảng liền trước cùng số ngày
    assert kc.hai_ky({"tu": "2026-09-01", "den": "2026-09-05"}, ngays) == \
        ("2026-08-01", "2026-08-05", "2026-09-01", "2026-09-05")
    assert kc.hai_ky({"tu": "2026-09-02", "den": "2026-09-05"}, ngays) == \
        ("2026-08-29", "2026-09-01", "2026-09-02", "2026-09-05")
    assert kc.hai_ky({}, ngays) is None


def _gia_tri(node, id_, prop):
    n = [x for x in _cac_node(node) if getattr(x, "id", None) == id_]
    return getattr(n[0], prop) if n else None


def test_cac_trang_mo_voi_bo_loc_da_chon(tai_khoan):
    from flask_login import login_user

    from app.ui.app import _router, server
    ky = {"tu": "2026-09-03", "den": "2026-09-08", "cn": "QNM", "phong": "IBB2"}
    with server.test_request_context("/"):
        login_user(_user("zz_ht_admin"))
        tq, _ = _router("/", "", ky)
        assert _gia_tri(tq, "tq-khoang", "start_date") == "2026-09-03"
        assert _gia_tri(tq, "tq-khoang", "end_date") == "2026-09-08"
        assert _gia_tri(tq, "tq-cn", "value") == "QNM"
        bp, _ = _router("/phong", "", ky)
        assert _gia_tri(bp, "bp-date", "date") == "2026-09-08" and _gia_tri(bp, "bp-phong", "value") == "IBB2"
        hr, _ = _router("/hr", "", ky)
        assert _gia_tri(hr, "hr-date", "date") == "2026-09-08" and _gia_tri(hr, "hr-phong", "value") == "IBB2"
        db, _ = _router("/sosanh", "", ky)
        assert _gia_tri(db, "ss-k2-tu", "date") == "2026-09-03"
        assert _gia_tri(db, "ss-k1-den", "date") == "2026-09-02"
        assert _gia_tri(db, "tk-thang", "value") == "2026-09"
        cl, _ = _router("/chatluong", "?den=2026-09-11&cn=DNG", ky)     # đường dẫn thắng
        assert _gia_tri(cl, "cl-cn", "value") == "DNG"


def test_truong_phong_khong_mo_duoc_phong_khac_qua_duong_dan(tai_khoan):
    from flask_login import login_user

    from app.ui.app import _router, server
    with server.test_request_context("/"):
        login_user(_user("zz_ht_phong"))
        bp, _ = _router("/phong", "?phong=IBB7", None)
    assert _gia_tri(bp, "bp-phong", "value") == "IBB2"


def test_doi_bo_loc_thi_ghi_vao_bo_loc_chung(tai_khoan):
    from dash import no_update
    from flask_login import login_user

    from app.ui.app import app, server
    ghi = [v["callback"] for k, v in app.callback_map.items()
           if k.startswith("..ky-chung.data") or k.startswith("ky-chung.data")]
    assert len(ghi) >= 8                             # 7 trang + đọc từ đường dẫn
    ham = _callback_theo_input("bp-date")
    with server.test_request_context("/"):
        login_user(_user("zz_ht_admin"))
        assert ham("2026-09-08", "IBB6", {"cn": "DNG"}) == \
            {"tu": "2026-09-01", "den": "2026-09-08", "cn": "DNG", "phong": "IBB6"}
        assert ham("2026-09-08", "IBB6", {"tu": "2026-09-01", "den": "2026-09-08", "phong": "IBB6"}) is no_update
        hr = _callback_theo_input("hr-date")
        assert hr("2026-09-08", "all", "__kd", {"phong": "IBB6"})["phong"] == "IBB6"   # "tất cả" không xoá phòng


def _callback_theo_input(id_):
    from app.ui.app import app
    for k, v in app.callback_map.items():
        if "ky-chung.data" in k and any(i["id"] == id_ for i in v["inputs"]):
            return getattr(v["callback"], "__wrapped__", v["callback"])
    raise KeyError(id_)
