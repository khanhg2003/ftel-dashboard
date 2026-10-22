"""Tab "Giá cả tỉnh" của Tra cứu giá: quét giá mọi gói ở mọi phường / xã của một tỉnh rồi cho thấy vùng giá.

Mỗi phường là một lần gọi fpt.vn nên chỉ quét khi người dùng bấm (khoảng 20-40 giây, quá 45 giây thì trả phần đã quét được).
Kết quả giữ ở trình duyệt (`dcc.Store` kiểu session) để máy chủ nào của Vercel cũng dùng tiếp được và không phải quét lại khi đổi trang.
"""
from __future__ import annotations

from datetime import datetime

import plotly.graph_objects as go
from dash import Input, Output, State, dcc, html, no_update
from dash.exceptions import PreventUpdate

from app import gia_fpt as gf
from app.thoi_gian import chu_gio_vn
from app.ui.components import alert, card, field, ghi_chu, kpi
from app.ui.icons import icon
from app.ui.luoi import bang

XANH, CAM = "#0072BC", "#F37021"
DONG = {"function": "params.value == null ? '–' : Math.round(params.value).toLocaleString('vi-VN') + 'đ'"}
COT = [
    {"field": "ten", "headerName": "Gói", "minWidth": 240, "flex": 2},
    {"field": "khach", "headerName": "Khách hàng", "width": 130,
     "valueFormatter": {"function": "params.value == 'doanh_nghiep' ? 'Doanh nghiệp' : 'Cá nhân'"}},
    {"field": "thap", "headerName": "Giá thấp nhất", "width": 130, "type": "numericColumn", "valueFormatter": DONG},
    {"field": "cao", "headerName": "Giá cao nhất", "width": 130, "type": "numericColumn", "valueFormatter": DONG},
    {"field": "chenh", "headerName": "Chênh lệch", "width": 120, "type": "numericColumn", "valueFormatter": DONG,
     "cellStyle": {"styleConditions": [{"condition": "params.value > 0", "style": {"color": "#C8372D", "fontWeight": "600"}}]}},
    {"field": "so_muc", "headerName": "Số mức giá", "width": 100, "type": "numericColumn"},
    {"field": "ban", "headerName": "Phường có bán", "width": 120, "type": "numericColumn"},
    {"field": "khong_ban", "headerName": "Phường không bán", "width": 130, "type": "numericColumn",
     "headerTooltip": "Số phường / xã mà fpt.vn không bán gói này."},
]


def pane():
    from app.ui.pages.giafpt import _dd, opt_tinh
    return html.Div([
        dcc.Store(id="gf3-du-lieu", storage_type="session"),
        html.Div([field("Tỉnh / thành", _dd("gf3-tinh", value=gf.TINH_MAC_DINH, clearable=False, options=opt_tinh(), placeholder="Đang tải…")),
                  html.Div(className="grow"),
                  html.Button([icon("search", 14), html.Span("Quét giá các phường", id="gf3-quet-chu")], id="gf3-quet", className="btn primary")],
                 className="toolbar"),
        html.Div(id="gf3-tb"),
        html.Div(id="gf3-kq", children=card(html.Div("Bấm \"Quét giá các phường\" để xem phường nào giá cao, phường nào giá thấp và gói nào "
                                                      "giá khác nhau giữa các phường. Quét mất khoảng 20 - 40 giây vì phải hỏi fpt.vn từng phường.",
                                                      className="desc"), title="Giá cả tỉnh")),
    ], id="gf-pane-vung", style={"display": "none"})


def _the(du: dict, bd: list[dict]) -> html.Div:
    khac = [r for r in bd if r["so_muc"] > 1]
    lon = max(bd, key=lambda r: r["chenh"]) if bd else None
    cac = [kpi("Phường / xã đã quét", f"{len(du['gia'])}", f"Trên tổng {len(du['phuong'])} phường / xã của tỉnh"),
           kpi("Gói giá khác nhau giữa các phường", f"{len(khac)}", f"Trên {len(bd)} gói đang bán"),
           kpi("Chênh lệch lớn nhất", gf.chu_tien(lon["chenh"]) if lon else "–", lon["ten"] if lon else "")]
    if du["loi"]:
        cac.append(kpi("Chưa quét được", f"{len(du['loi'])}", "Phường fpt.vn chưa kịp trả lời: quét lại để bổ sung", "warn"))
    return html.Div(cac, className="kpi-row")


def _goi_mac_dinh(bd: list[dict]) -> str | None:
    """Gói đầu tiên là Internet cá nhân có giá khác nhau giữa các phường (thường là gói sale hay báo nhất)."""
    uu_tien = [r for r in bd if r["so_muc"] > 1 and r["khach"] == "ca_nhan" and r["id"]]
    return (uu_tien or bd or [{"id": None}])[0]["id"]


def _ket_qua(du: dict):
    bd = gf.bien_dong(du)
    if not bd:
        return alert("Chưa quét được gói nào. Thử quét lại sau ít phút.", "warn")
    g = bang("gf3-bd", COT, 420, tuy_chon={"suppressCellFocus": True, "tooltipShowDelay": 300})
    g.rowData = bd
    ten_tinh = next((t["ten"] for t in gf.danh_sach_tinh() if t["id"] == du["tinh"]), "")
    return html.Div([
        _the(du, bd),
        card([g, ghi_chu("Mỗi dòng là một gói. Chênh lệch = giá cao nhất trừ giá thấp nhất giữa các phường. Gói xếp trên là gói giá khác nhau nhiều "
                         "nhất: sale cần báo đúng giá của phường khách ở.", style={"margin": "8px 0 0"})],
             title=f"Gói nào giá khác nhau giữa các phường · {ten_tinh}",
             desc=f"Quét lúc {chu_gio_vn(datetime.fromisoformat(du['luc']), '%H:%M %d/%m/%Y')}. Giá đã gồm VAT."),
        card([field("Chọn gói", dcc.Dropdown(id="gf3-goi", className="gf-dd", clearable=False, value=_goi_mac_dinh(bd),
                                             options=[{"label": f"{r['ten']} ({'DN' if r['khach'] == 'doanh_nghiep' else 'cá nhân'})", "value": r["id"]}
                                                      for r in bd])),
              html.Div(id="gf3-vung")], title="Nhóm giá theo phường / xã", desc="Phường nào cùng một mức giá thì gom lại; bấm một mức để xem tên phường."),
    ])


def _hinh_vung(nhom: list[dict]) -> go.Figure:
    nhan = [gf.chu_tien(n["gia"]) if n["gia"] is not None else "Không bán" for n in nhom]
    fig = go.Figure(go.Bar(x=nhan, y=[len(n["phuong"]) for n in nhom], marker_color=[XANH if n["gia"] is not None else "#9AA7B8" for n in nhom],
                           text=[len(n["phuong"]) for n in nhom], textposition="outside", hovertemplate="%{x}: %{y} phường / xã<extra></extra>"))
    fig.update_layout(height=260, margin={"l": 8, "r": 8, "t": 16, "b": 8}, plot_bgcolor="white", paper_bgcolor="white",
                      font={"family": "Inter, Segoe UI, sans-serif", "size": 12, "color": "#1B2733"}, showlegend=False,
                      xaxis={"type": "category", "title": "Giá / tháng"}, yaxis={"title": "Số phường / xã", "gridcolor": "#F1F5F9", "zeroline": False})
    return fig


def _nhom_gia(nhom: list[dict]) -> list:
    out = []
    for i, n in enumerate(nhom):
        tieu = f"{gf.chu_tien(n['gia'])} · {len(n['phuong'])} phường / xã" if n["gia"] is not None else f"Không bán · {len(n['phuong'])} phường / xã"
        out.append(html.Details([html.Summary(tieu), html.Div([html.Span(p, className="chip") for p in n["phuong"]], className="chips")],
                                className="gf-nhom-gia", open=i == 0 and len(n["phuong"]) <= 30))
    return out


def register(app):
    @app.callback(Output("gf3-du-lieu", "data"), Output("gf3-tb", "children"), Input("gf3-quet", "n_clicks"), State("gf3-tinh", "value"),
                  prevent_initial_call=True,
                  running=[(Output("gf3-quet", "disabled"), True, False), (Output("gf3-quet-chu", "children"), "Đang quét, chờ khoảng 30 giây…", "Quét giá các phường")])
    def _quet(n, tinh):
        from app.ui.pages.giafpt import _loi, _vao
        _vao()
        if not n or not tinh:
            raise PreventUpdate
        try:
            return gf.quet_tinh(int(tinh)), None
        except gf.LoiGia as e:
            return no_update, _loi(e)

    @app.callback(Output("gf3-kq", "children"), Input("gf3-du-lieu", "data"), Input("gf-tab", "value"))
    def _hien(du, tab):
        from app.ui.pages.giafpt import _vao
        _vao()
        if tab != "vung" or not du:
            raise PreventUpdate
        return _ket_qua(du)

    @app.callback(Output("gf3-vung", "children"), Input("gf3-goi", "value"), State("gf3-du-lieu", "data"))
    def _vung(goi, du):
        from app.ui.pages.giafpt import _vao
        _vao()
        if not goi or not du:
            raise PreventUpdate
        nhom = gf.vung_gia(du, goi)
        return [dcc.Graph(figure=_hinh_vung(nhom), config={"displayModeBar": False, "responsive": True}, style={"width": "100%"}),
                *_nhom_gia(nhom)]
