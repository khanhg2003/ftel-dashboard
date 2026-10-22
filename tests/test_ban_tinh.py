"""Phân tích bán hàng: hai phần "Bán theo tỉnh" và "Ai bán ở tỉnh nào" cho nhân viên KD IBB7 (chủ app chốt 22/10/2026).

Quy tắc: nvkd IBB7 chỉ thấy hai phần đó (các phần còn lại của trang ẩn VÀ không nhận số), số theo tỉnh / theo phòng là số chung,
chi tiết từng nhân viên chỉ trong phòng mình. Phòng khác, vai trò khác giữ nguyên như trước."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import DATA_DIR  # noqa: E402

pytestmark = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(), reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")
TU, DEN = "2026-09-01", "2026-09-11"


def _tk(role: str, scope: list[str]):
    from app.auth import SessionUser
    return SessionUser(SimpleNamespace(id=1, username=f"kiemthu.{role}", ho_ten="Kiểm thử", role=role, ma_nv=None, session_version=0, scope=json.dumps(scope)))


def _goi(dau_ra: str, tai_khoan, *args):
    """Gọi thẳng hàm callback có Output chứa `dau_ra`, như thể `tai_khoan` đang đăng nhập."""
    from dash import ctx  # noqa: F401
    from dash._callback_context import context_value
    from dash._utils import AttributeDict
    from flask_login import login_user
    from app.ui.app import app, server
    ham = next(getattr(v["callback"], "__wrapped__", v["callback"]) for k, v in app.callback_map.items() if "callback" in v and dau_ra in k)
    with server.test_request_context("/"):
        login_user(tai_khoan)
        context_value.set(AttributeDict(triggered_inputs=[], inputs_list=[], states_list=[], outputs_list=[]))
        return ham(*args)


def test_quyen_xem_ban_tinh_theo_phong_va_vai_tro():
    assert _tk("nvkd", ["IBB7"]).duoc_xem_ban_tinh and _tk("nvkd", ["IBB7"]).vao_duoc("/phantich")
    assert not _tk("nvkd", ["IBB6"]).duoc_xem_ban_tinh and not _tk("nvkd", ["IBB6"]).vao_duoc("/phantich")
    assert not _tk("nvkd", ["IBB7", "IBB6"]).duoc_xem_ban_tinh                    # tài khoản xem nhiều phòng không phải người vận hành IBB7
    assert _tk("admin", []).duoc_xem_ban_tinh
    tp = _tk("phong", ["IBB7"])
    assert not tp.duoc_xem_ban_tinh and tp.vao_duoc("/phantich")                  # vai trò khác: quyền cũ giữ nguyên (thẻ vẫn ẩn)
    assert not _tk("nvkd", ["IBB7"]).vao_duoc("/hr") and not _tk("nvkd", ["IBB7"]).vao_duoc("/")   # không mở thêm trang nào khác


def _khoi_hien(tai_khoan) -> dict:
    from flask_login import login_user
    from app.ui.app import server
    from app.ui.pages import phantich
    with server.test_request_context("/"):
        login_user(tai_khoan)
        con = phantich.layout().children
    ten = {}
    for c in con:
        chu = json.dumps(c, default=lambda o: o.to_plotly_json() if hasattr(o, "to_plotly_json") else str(o))
        ten[c] = ('"pt-kpi"' in chu, '"pt-tinh-bang"' in chu, '"pt-nv"' in chu, (getattr(c, "style", None) or {}).get("display") == "none")
    return ten


def test_layout_nvkd_ibb7_chi_hien_the_ban_tinh():
    ten = _khoi_hien(_tk("nvkd", ["IBB7"]))
    kpi = [v for v in ten.values() if v[0]]
    tinh = [v for v in ten.values() if v[1]]
    nv = [v for v in ten.values() if v[2]]
    assert kpi and kpi[0][3] and nv and nv[0][3]                  # khối KPI / chất lượng bán theo phòng và khối theo nhân viên bị ẩn
    assert tinh and not tinh[0][3]                                # thẻ Bán theo tỉnh hiện


def test_layout_vai_tro_khac_giu_nguyen():
    adm = _khoi_hien(_tk("admin", []))
    assert all(not v[3] for v in adm.values() if v[0] or v[1] or v[2])        # Quản trị: mọi khối hiện
    tp = _khoi_hien(_tk("phong", ["IBB7"]))
    assert any(v[1] for v in tp.values())                                    # khối chứa thẻ tỉnh vẫn có trong trang của Trưởng phòng


def test_callback_cac_phan_an_khong_nhan_so_cho_nvkd():
    from dash.exceptions import PreventUpdate
    sale = _tk("nvkd", ["IBB7"])
    with pytest.raises(PreventUpdate):
        _goi("pt-kpi.children", sale, TU, DEN, "all", "tat_ca")                      # KPI + chất lượng bán theo phòng + tồn + biểu đồ
    assert _goi("pt-du-bao.children", sale, DEN, "all") == ""                        # dự báo cả chi nhánh: để trống
    assert _goi("pt-nv.rowData", sale, TU, DEN, "all", "all", "all")[1] == []          # bảng chất lượng theo nhân viên: rỗng


def test_nvkd_ibb7_nhan_so_bang_tinh_nhung_chi_nhan_vien_trong_phong_minh():
    from app.org import phong_order
    sale = _tk("nvkd", ["IBB7"])
    tinh = _goi("pt-tinh-bang.rowData", sale, TU, DEN, "all", "all", "tat_ca", "tong")
    assert tinh[5] and tinh[7]                                                         # bảng tỉnh và ma trận phòng có số (số chung)
    cot, dong = _goi("pt-tinh-nv.rowData", sale, "nv", "tong", TU, DEN, "all", "all", "tat_ca", "all")
    ten_ibb7 = next(p["ten"] for p in phong_order("2026-09") if p["code"] == "IBB7")
    assert dong and {d["phong"] for d in dong} == {ten_ibb7}
    admin = _goi("pt-tinh-nv.rowData", _tk("admin", []), "nv", "tong", TU, DEN, "all", "all", "tat_ca", "all")[1]
    assert len({d["phong"] for d in admin}) > 1                                       # Quản trị vẫn thấy mọi phòng


def test_nvkd_khong_mo_duoc_chi_tiet_nhan_vien_phong_khac():
    from app import phan_tich as pt
    df = pt.online_theo_tinh(TU, DEN, None)
    khac = df[(df.phong_code != "IBB7") & df.acc_norm.notna()].acc_norm.iloc[0]
    kq = _goi("pt-md-nv-tieu-de.children", _tk("nvkd", ["IBB7"]), [{"acc_key": khac, "ho_ten": "x", "phong": "x"}], TU, DEN, "all")
    assert kq == ("modal", "", [])                                                     # người phòng khác: không mở cửa sổ chi tiết
    cua_minh = df[(df.phong_code == "IBB7") & df.acc_norm.notna()].acc_norm.iloc[0]
    kq = _goi("pt-md-nv-tieu-de.children", _tk("nvkd", ["IBB7"]), [{"acc_key": cua_minh, "ho_ten": "x", "phong": "x"}], TU, DEN, "all")
    assert kq[0] == "modal mo"


def test_nvkd_chi_tiet_tinh_chi_liet_ke_nhan_vien_phong_minh():
    sale = _tk("nvkd", ["IBB7"])
    tinh = _goi("pt-tinh-bang.rowData", sale, TU, DEN, "all", "all", "tat_ca", "tong")[5]
    ma = next(r["ma_tinh"] for r in tinh)
    _cls, _tieu, than = _goi("pt-md-tinh-tieu-de.children", sale, [{"ma_tinh": ma, "tinh": "x"}], TU, DEN, "all", "all")
    chu = json.dumps(than, default=lambda o: o.to_plotly_json() if hasattr(o, "to_plotly_json") else str(o))
    assert "pt-tinh-ct-nv" in chu
