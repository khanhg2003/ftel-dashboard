"""Bảng (dash-ag-grid) dùng chung: định dạng số kiểu Việt Nam và hàm dựng bảng.

Định dạng là chuỗi JavaScript chạy trong trình duyệt - giữ đơn giản (không dùng typeof / === / isNaN, dash-ag-grid
không nhận). Chữ phức tạp thì định dạng sẵn bằng Python.
"""
from __future__ import annotations

import dash_ag_grid as dag

from app.ui.components import LOCALE_VI


def _f(js: str) -> dict:
    return {"function": js}


SO = _f("params.value == null ? '' : Number(params.value).toLocaleString('vi-VN')")                 # 1.234
SO_1 = _f("params.value == null ? '' : Number(params.value).toLocaleString('vi-VN', "
          "{maximumFractionDigits: 1})")                                                             # 1.234,5
PCT = _f("params.value == null ? '' : Math.round(params.value) + '%'")                              # 45%
PCT_GACH = _f("params.value == null ? '–' : Math.round(params.value) + '%'")                        # trống -> –
PCT_DAU = _f("params.value == null ? '' : (params.value > 0 ? '+' : '') + Math.round(params.value) + '%'")
CHENH_PCT = _f("params.value == null ? '–' : (params.value > 0 ? '+' : '') + Math.round(params.value) + '%'")
CHENH = _f("params.value == null ? '' : (params.value > 0 ? '+' : '') + params.value")              # +3
USD = _f("params.value == null ? '' : Number(params.value).toLocaleString('vi-VN', "
         "{minimumFractionDigits: 2, maximumFractionDigits: 2})")                                    # 1.234,50
USD_D = _f("params.value == null ? '' : Number(params.value).toLocaleString('vi-VN', "
           "{minimumFractionDigits: 2, maximumFractionDigits: 2}) + ' $'")                           # 1.234,50 $
VND = _f("params.value == null ? '' : Math.round(params.value).toLocaleString('vi-VN')")

LOP = "ag-theme-quartz ag-theme-ftel"
COT_MAC_DINH = {"resizable": True, "sortable": True, "suppressMovable": True, "wrapHeaderText": True,
                "autoHeaderHeight": True}


def bang(gid: str, cot: list | None = None, cao: int | None = None, *, lop: str = LOP,
         tuy_chon: dict | None = None, cot_mac_dinh: dict | None = None, **kw) -> dag.AgGrid:
    """Bảng chuẩn của app. cao=None: tự giãn theo số dòng (bảng ngắn); có cao: cao cố định, nhiều dòng thì cuộn
    trong khung, tiêu đề cột đứng yên. `tuy_chon` ghi đè dashGridOptions, `cot_mac_dinh` ghi đè defaultColDef."""
    opts = {"localeText": LOCALE_VI, "tooltipShowDelay": 300, "suppressCellFocus": True,
            "domLayout": "autoHeight" if cao is None else "normal", **(tuy_chon or {})}
    return dag.AgGrid(id=gid, className=lop, columnDefs=cot or [], rowData=[], dashGridOptions=opts,
                      defaultColDef=cot_mac_dinh or COT_MAC_DINH,
                      style={"width": "100%", **({"height": f"{cao}px"} if cao else {})}, **kw)
