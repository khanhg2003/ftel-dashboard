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


# ------------------------------------------------------- đợt 4: đi xuống chi tiết, tình trạng dữ liệu
def test_trang_mo_dau_theo_vai_tro(tai_khoan):
    r = _dang_nhap_tra_ve("zz_ht_admin")
    assert r.headers["Location"].endswith("/") and not r.headers["Location"].endswith("/phong")
    assert _dang_nhap_tra_ve("zz_ht_phong").headers["Location"].endswith("/phong")


def _dang_nhap_tra_ve(username):
    from app.ui.app import server
    return server.test_client().post("/login", data={"username": username, "password": MK})


def _callback_theo_output_input(out: str, id_):
    from app.ui.app import app
    for k, v in app.callback_map.items():
        if out in k and any(i["id"] == id_ for i in v["inputs"]):
            return getattr(v["callback"], "__wrapped__", v["callback"])
    raise KeyError(id_)


@pytest.mark.parametrize("grid", ["tq-grid", "tk-grid", "pt-phong"])
def test_bam_ten_phong_mo_bao_cao_phong(tai_khoan, grid):
    from dash import no_update
    from flask_login import login_user

    from app.ui.app import server
    ham = _callback_theo_output_input("url.pathname", grid)
    ky = {"tu": "2026-09-01", "den": "2026-09-08"}
    with server.test_request_context("/"):
        login_user(_user("zz_ht_admin"))
        assert ham({"colId": "phong", "rowId": "data|IBB6"}, ky) == ("/phong", {**ky, "phong": "IBB6"})
        assert ham({"colId": "phong", "rowId": "subtotal|SUB_BAY1"}, ky) == (no_update, no_update)
        assert ham({"colId": "online", "rowId": "data|IBB6"}, ky) == (no_update, no_update)
    with server.test_request_context("/"):
        login_user(_user("zz_ht_phong"))                 # trưởng phòng IBB2 không mở được phòng khác
        assert ham({"colId": "phong", "rowId": "data|IBB6"}, ky) == (no_update, no_update)
        assert ham({"colId": "phong", "rowId": "data|IBB2"}, ky)[0] == "/phong"


def test_giai_thich_tu_viet_tat():
    from app.ui.lien_ket import giai_thich, them_giai_thich
    assert "hoàn thành kế hoạch" in giai_thich("Tỷ lệ HTKH")
    gt = giai_thich("Tỷ lệ VVIP/PTTB")
    assert "V.VIP" in gt and "phát triển thuê bao" in gt
    cols = them_giai_thich([{"headerName": "PTTB CNQL", "children": [{"headerName": "Số online"}]},
                            {"headerName": "Cùng kỳ", "headerTooltip": "giữ nguyên"}])
    assert "CNQL" in cols[0]["headerTooltip"] and "headerTooltip" not in cols[0]["children"][0]
    assert cols[1]["headerTooltip"] == "giữ nguyên"


def test_dong_tinh_trang_du_lieu(tai_khoan, monkeypatch):
    from flask_login import login_user

    from app import admin_service
    from app.ui import lien_ket
    from app.ui.app import server
    with server.test_request_context("/"):
        login_user(_user("zz_ht_admin"))
        monkeypatch.setattr(admin_service, "do_moi_du_lieu", lambda: [
            {"loai": "Internet", "ngay": "2026-09-12"}, {"loai": "Truyền hình", "ngay": "2026-09-12"},
            {"loai": "Camera", "ngay": "2026-09-11"}])
        chu = str(lien_ket.thanh_du_lieu())
        assert "Số đến 12/09" in chu and "Camera mới đến 11/09" in chu and "/chatluong" in chu
        monkeypatch.setattr(admin_service, "do_moi_du_lieu", lambda: [
            {"loai": "Internet", "ngay": "2026-09-12"}, {"loai": "Truyền hình", "ngay": "2026-09-12"},
            {"loai": "Camera", "ngay": "2026-09-12"}])
        assert "Kiểm tra" not in str(lien_ket.thanh_du_lieu())


def test_chua_co_du_lieu_thi_huong_dan_nap(tai_khoan, monkeypatch):
    from flask_login import login_user

    import app.metrics
    from app.ui.app import _router, server
    monkeypatch.setattr(app.metrics, "ngay_moi_nhat", lambda: None)
    with server.test_request_context("/"):
        login_user(_user("zz_ht_admin"))
        noi_dung, _ = _router("/", "", None)
        assert "Nạp dữ liệu ngay" in str(noi_dung)
        noi_dung, _ = _router("/quantri", "", None)          # trang quản trị vẫn mở bình thường
        assert "qt-tab" in str(noi_dung)


# ------------------------------------------------------- sửa tài khoản, danh mục bằng hộp thoại
def test_sua_tai_khoan_va_cac_chot_chan(tai_khoan):
    from app.admin_service import lay_user, sua_user
    ok, msg = sua_user("zz_ht_phong", {"ho_ten": "Trưởng phòng mới", "role": "phong", "pham_vi": ["IBB2", "IBB6"],
                                        "ma_nv": "123", "email": "tp@fpt.vn", "trang_thai": "Đang dùng"},
                       "zz_ht_admin")
    assert ok, msg
    u = lay_user("zz_ht_phong")
    assert u["ho_ten"] == "Trưởng phòng mới" and u["pham_vi"] == ["IBB2", "IBB6"] and u["email"] == "tp@fpt.vn"
    assert not sua_user("zz_ht_phong", {"role": "phong", "pham_vi": []}, "zz_ht_admin")[0]      # thiếu phòng
    assert not sua_user("zz_ht_phong", {"role": "phong", "pham_vi": ["IBB2"], "email": "sai"}, "x")[0]
    assert not sua_user("zz_ht_admin", {"role": "operator"}, "zz_ht_admin")[0]           # tự hạ quyền
    ok, _ = sua_user("zz_ht_phong", {"role": "operator", "pham_vi": ["IBB2"]}, "zz_ht_admin")
    assert ok and lay_user("zz_ht_phong")["pham_vi"] == []                                # nhập liệu: bỏ phòng
    _tao("zz_ht_phong", "phong", ["IBB2"])


def test_dat_lai_mat_khau_ngau_nhien(tai_khoan):
    from app.admin_service import dat_lai_mat_khau
    a, b = dat_lai_mat_khau("zz_ht_phong", "zz_ht_admin"), dat_lai_mat_khau("zz_ht_phong", "zz_ht_admin")
    assert a.startswith("Ftel@") and len(a) == 11 and a != b
    _tao("zz_ht_phong", "phong", ["IBB2"])


def test_luu_mot_dong_danh_muc_chan_khai_trung():
    from sqlalchemy import delete

    from app.admin_service import lay_staff, luu_mot_staff
    from app.db import session_scope
    from app.models import StaffMap
    acc = "ZZ.KiemThuDanhMuc"
    try:
        ok, msg, tinh = luu_mot_staff(None, {"acc": acc, "phong_code": "IBB2"}, "zz_ht_admin")
        assert ok and tinh, msg
        with session_scope() as s:
            id_ = s.query(StaffMap).filter(StaffMap.acc == acc).one().id
        ok, msg, _ = luu_mot_staff(None, {"acc": acc, "phong_code": "IBB6"}, "zz_ht_admin")
        assert not ok and "đã có trong danh mục" in msg                              # trùng thời gian hiệu lực
        ok, msg, _ = luu_mot_staff(None, {"acc": acc, "phong_code": "IBB6", "hieu_luc_tu": "2026-09-10",
                                          "hieu_luc_den": "2026-09-05"}, "zz_ht_admin")
        assert not ok and "trước" in msg
        ok, _, tinh = luu_mot_staff(id_, {"acc": acc, "phong_code": "IBB2", "ma_nv": "999", "da_nghi": True,
                                         "ghi_chu": "chuyển công tác"}, "zz_ht_admin")
        r = lay_staff(id_)
        assert ok and not tinh and r["da_nghi"] and "chuyển công tác" in r["ghi_chu"]   # không đổi phòng: không tính lại
        ok, _, tinh = luu_mot_staff(id_, {"acc": acc, "phong_code": "IBB6", "ghi_chu": "chuyển công tác"},
                                    "zz_ht_admin")
        assert ok and tinh and not lay_staff(id_)["da_nghi"]
    finally:
        with session_scope() as s:
            s.execute(delete(StaffMap).where(StaffMap.acc == acc))


def test_bam_sua_mo_hop_thoai_dien_san(tai_khoan):
    from flask_login import login_user

    from app.ui.app import server
    ham = _callback_theo_output_input("qt-modal-user.className", "qt-user-grid")
    from unittest import mock
    with server.test_request_context("/"):
        login_user(_user("zz_ht_admin"))
        with mock.patch("app.ui.pages.quantri.ctx") as c, mock.patch("dash.ctx", c):
            c.triggered_id = "qt-user-grid"
            c.triggered = [{"prop_id": "qt-user-grid.cellClicked"}]
            kq = ham(None, {"colId": "_sua", "rowId": "zz_ht_phong"}, None, None, None, None)
            assert kq[0] == "modal mo" and kq[4] == "zz_ht_phong" and kq[5] is True and kq[8] == ["IBB2"]
            kq = ham(None, {"colId": "ho_ten", "rowId": "zz_ht_phong"}, None, None, None, None)
            assert kq[0] != "modal mo"                                           # bấm ô thường: không mở
            c.triggered = [{"prop_id": "qt-user-grid.cellDoubleClicked"}]
            kq = ham(None, None, {"colId": "ho_ten", "rowId": "zz_ht_phong"}, None, None, None)
            assert kq[0] == "modal mo"                                           # bấm đúp: mở


# ------------------------------------------------------- cơ cấu tổ chức, chỉ tiêu: sửa bằng hộp thoại
def test_hop_thoai_bay_phong_kiem_tra_hop_le():
    from app.org import bay_info, phong_order
    from app.ui.pages.settings import luu_bay_hop_thoai, luu_phong_hop_thoai
    b = next(iter(bay_info().values()))
    khac = [x for x in bay_info().values() if x["code"] != b["code"]][0]
    assert not luu_bay_hop_thoai(None, "", "", 1, "Có")[0]
    assert "Đã có bầy" in luu_bay_hop_thoai(None, khac["ten"], "", 1, "Có")[1]
    assert not luu_bay_hop_thoai(b["code"], b["ten"], "", -1, "Có")[0]
    assert "còn phòng" in luu_bay_hop_thoai(b["code"], b["ten"], "", 1, "Không")[1]
    p, q = phong_order()[:2]
    d = {"ten": q["ten"], "bay": p["bay"], "loai": p["loai"], "chi_nhanh": p["chi_nhanh"], "thu_tu": 1}
    assert "Đã có phòng" in luu_phong_hop_thoai(p["code"], d)[1]
    assert not luu_phong_hop_thoai(p["code"], {**d, "ten": p["ten"], "bay": "KHONG_CO"})[0]


def test_luu_chi_tieu_mot_phong_va_xoa_o_trong():
    from sqlalchemy import delete

    from app.db import session_scope
    from app.models import Target
    from app.ui.pages.settings import _luu_target_rows, _target_rows
    thang = "2030-01"
    try:
        _luu_target_rows(thang, [{"phong_code": "IBB2", "internet": 500, "camera": 120, "ngay": 20}], "test")
        r = next(x for x in _target_rows(thang)[1] if x["phong_code"] == "IBB2")
        assert (r["internet"], r["camera"], r["ngay"]) == (500, 120, 20)
        _luu_target_rows(thang, [{"phong_code": "IBB2", "internet": 550, "camera": None, "ngay": ""}], "test",
                         xoa_o_trong=True)
        r = next(x for x in _target_rows(thang)[1] if x["phong_code"] == "IBB2")
        assert (r["internet"], r["camera"], r["ngay"]) == (550, None, None)
    finally:
        with session_scope() as s:
            s.execute(delete(Target).where(Target.thang == thang))


@pytest.mark.parametrize("grid, out, rowid", [("st-bay-grid", "st-modal-bay.className", None),
                                              ("st-phong-grid", "st-modal-phong.className", "IBB2"),
                                              ("st-cocau-grid", "st-modal-cocau.className", "IBB2"),
                                              ("st-target-grid", "st-modal-target.className", "IBB2")])
def test_bam_sua_mo_hop_thoai_co_cau_chi_tieu(tai_khoan, grid, out, rowid):
    from unittest import mock

    from flask_login import login_user

    from app.org import bay_info
    from app.ui.app import server
    rowid = rowid or next(iter(bay_info()))
    ham = _callback_theo_output_input(out, grid)
    with server.test_request_context("/"):
        login_user(_user("zz_ht_admin"))
        with mock.patch("app.ui.pages.settings.ctx") as c, mock.patch("dash.ctx", c):
            c.triggered_id = grid
            c.triggered = [{"prop_id": f"{grid}.cellClicked"}]
            o = {"colId": "_sua", "rowId": rowid}
            kq = (ham(o, None, None, None, None, THANG) if grid in ("st-cocau-grid", "st-target-grid")
                  else ham(None, o, None, None, None, None))
            assert kq[0] == "modal mo"
