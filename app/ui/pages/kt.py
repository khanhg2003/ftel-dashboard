"""Khối Kỹ thuật: định tuyến các trang /kt/... và đăng ký callback của từng trang."""
from __future__ import annotations

import importlib

from dash import html

TRANG = {"/kt": "kt_tq", "/kt/ton": "kt_ton", "/kt/trien-khai": "kt_tk", "/kt/su-co": "kt_su_co", "/kt/nhan-su": "kt_nhan_su"}


def _module(ten: str):
    return importlib.import_module(f"app.ui.pages.{ten}")


def trang(path: str):
    """(nội dung, thanh tiêu đề) của một trang Kỹ thuật."""
    ten = TRANG.get((path or "").rstrip("/") or "/kt")
    if ten is None:
        return html.Div("Không có trang này trong khối Kỹ thuật.", className="card"), [html.Div([html.H1("Không tìm thấy trang")])]
    m = _module(ten)
    return m.layout(), m.topbar()


def register(app):
    for ten in dict.fromkeys(TRANG.values()):
        _module(ten).register(app)
