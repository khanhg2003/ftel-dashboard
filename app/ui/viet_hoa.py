"""Việt hoá chữ mặc định của các thành phần giao diện (ô chọn, bảng).

Dash và AG Grid mặc định hiện tiếng Anh ("Search", "Select All", "Page 1 of 3"...). Thay vì
truyền nhãn tiếng Việt ở từng chỗ dùng, gắn sẵn giá trị mặc định một lần khi khởi động app -
chỗ nào tự truyền nhãn riêng thì vẫn giữ nhãn đó.
"""
from __future__ import annotations

import dash_ag_grid as dag
from dash import dcc

from app.ui.components import LOCALE_VI

NHAN_DROPDOWN = {
    "select_all": "Chọn tất cả",
    "deselect_all": "Bỏ chọn tất cả",
    "selected_count": "Đã chọn {num_selected}",
    "search": "Tìm…",
    "clear_search": "Xoá chữ tìm",
    "clear_selection": "Bỏ chọn",
    "no_options_found": "Không có lựa chọn phù hợp",
}


def _gan_mac_dinh(cls, them) -> None:
    if getattr(cls, "_da_viet_hoa", False):
        return
    goc = cls.__init__

    def __init__(self, *args, **kwargs):
        them(kwargs)
        goc(self, *args, **kwargs)

    __init__.__wrapped__ = goc
    cls.__init__ = __init__
    cls._da_viet_hoa = True


def _dropdown(kw: dict) -> None:
    kw["labels"] = {**NHAN_DROPDOWN, **(kw.get("labels") or {})}
    kw.setdefault("placeholder", "Chọn…")


def _bang(kw: dict) -> None:
    opts = dict(kw.get("dashGridOptions") or {})
    opts["localeText"] = {**LOCALE_VI, **(opts.get("localeText") or {})}
    kw["dashGridOptions"] = opts


def _bieu_do() -> None:
    """Biểu đồ viết số kiểu Việt Nam: 1.438 và 8,6 (mặc định Plotly là 1,438 và 8.6)."""
    import plotly.graph_objects as go
    import plotly.io as pio
    if "ftel" not in pio.templates:
        mau = go.layout.Template(pio.templates["plotly"])
        mau.layout.separators = ",."
        pio.templates["ftel"] = mau
    pio.templates.default = "ftel"


def viet_hoa() -> None:
    _gan_mac_dinh(dcc.Dropdown, _dropdown)
    _gan_mac_dinh(dag.AgGrid, _bang)
    _bieu_do()
