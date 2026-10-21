"""Khối DVKH: định tuyến các trang /dvkh/... và đăng ký callback của từng trang."""
from __future__ import annotations

from dash import html

from app.ui.pages import dvkh_chung as ch

# đường dẫn -> tên module (nạp khi cần để trang mở nhanh)
TRANG = {"/dvkh": "dvkh_tq", "/dvkh/sr-bi-dong": "dvkh_sr_bd", "/dvkh/sr-chu-dong": "dvkh_sr_cd", "/dvkh/roi-mang": "dvkh_roi_mang",
         "/dvkh/cong-no": "dvkh_cong_no", "/dvkh/nhan-su": "dvkh_nhan_su", "/dvkh/insight": "dvkh_insight", "/dvkh/nap": "dvkh_nap"}
CAN_SO_LIEU = {p for p in TRANG if p != "/dvkh/nap"}


def _module(ten: str):
    import importlib
    return importlib.import_module(f"app.ui.pages.{ten}")


def trang(path: str, tab: str | None = None):
    """(nội dung, thanh tiêu đề) của một trang DVKH. Chưa có số liệu thì hướng dẫn nạp file thay vì bảng trống."""
    from flask_login import current_user

    from app.dvkh import so_lieu as sl
    ten = TRANG.get((path or "").rstrip("/") or "/dvkh")
    if ten is None:
        return html.Div("Không có trang này trong khối DVKH.", className="card"), [html.Div([html.H1("Không tìm thấy trang")])]
    m = _module(ten)
    if path in CAN_SO_LIEU and not sl.co_du_lieu():
        return ch.chua_co_du_lieu(current_user.duoc_nap_dvkh), m.topbar()
    lay = m.layout
    return (lay(tab) if "tab" in lay.__code__.co_varnames[:lay.__code__.co_argcount] else lay()), m.topbar()


def register(app):
    for ten in dict.fromkeys(TRANG.values()):
        _module(ten).register(app)
