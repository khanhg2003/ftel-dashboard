"""Trang Diễn biến & So sánh: gộp Tracking ngày (tab 1) và So sánh kỳ (tab 2).

Hai tab cùng trả lời "số đang đi thế nào theo thời gian". Mỗi tab giữ nguyên bộ lọc, chỉ số và
callback của trang cũ (tracking.py, sosanh.py); tab đang ẩn không tính để trang mở nhanh.
Đường dẫn cũ /sosanh mở thẳng tab 2.
"""
from __future__ import annotations

from dash import Input, Output, html

from app.ui.components import seg_control
from app.ui.pages import sosanh, tracking

TAB = [("ngay", "1 · Theo từng ngày"), ("sosanh", "2 · So sánh hai kỳ")]
MO_TA = {"ngay": "Số bán của từng phòng theo từng ngày trong tháng",
         "sosanh": "Đối chiếu hai khoảng thời gian: phòng nào, ai tăng hay giảm"}


def topbar(tab: str = "ngay"):
    return [html.Div([html.H1("Diễn biến & So sánh"),
                      html.Div(MO_TA.get(tab, MO_TA["ngay"]), id="db-mo-ta", className="sub")]),
            html.Div(className="spacer"),
            html.Div(id="tracking-cap-nhat", hidden=tab != "ngay"),
            html.Div(id="ss-badge", hidden=tab != "sosanh")]


def layout(tab: str = "ngay", ky: dict | None = None):
    tab = tab if tab in dict(TAB) else "ngay"
    return html.Div([
        html.Div(seg_control("db-tab", TAB, tab), className="tab-lon"),
        html.Div(style={"height": "14px"}),
        html.Div(tracking.layout(ky), id="db-pane-ngay", hidden=tab != "ngay"),
        html.Div(sosanh.layout(ky), id="db-pane-sosanh", hidden=tab != "sosanh"),
    ])


def register(app):
    @app.callback(Output("db-pane-ngay", "hidden"), Output("db-pane-sosanh", "hidden"),
                  Output("tracking-cap-nhat", "hidden"), Output("ss-badge", "hidden"),
                  Output("db-mo-ta", "children"),
                  Input("db-tab", "value"), prevent_initial_call=True)
    def _doi_tab(tab):
        ngay = tab != "sosanh"
        return not ngay, ngay, not ngay, ngay, MO_TA["ngay" if ngay else "sosanh"]
