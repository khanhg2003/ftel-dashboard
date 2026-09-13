"""Trang Tracking ngày - thay thế báo cáo Google Sheet đang dùng."""
from __future__ import annotations

import dash_ag_grid as dag
import plotly.graph_objects as go
from dash import Input, Output, State, ctx, dcc, html, no_update
from flask_login import current_user

from app.metrics import (METRIC_LABEL, cac_thang_co_du_lieu, daily_counts, month_range,
                         ngay_co_du_lieu, summary_phong, tien_do_thang, tracking_table)
from app.org import bay_info, loc_chi_nhanh, phong_order
from app.ui.components import (GRID_STYLE_CONDITIONS, card, chi_nhanh_control, chon_ky, field,
                               gan_dieu_huong_ky, kpi, seg_control)
from app.ui.icons import icon

ZOOM_STEPS = [50, 75, 90, 100, 125, 150, 200]
ZOOM_OPTIONS = ([{"label": "Vừa màn hình", "value": "fit"}]
                + [{"label": f"{z}%", "value": z} for z in ZOOM_STEPS])
RONG_CO_DINH = 165 * 2 + 88          # cột Bầy + Phòng + Tổng (luôn ghim)
RONG_NGAY = 48

# Ô ngày tô đậm dần theo mức so với ngày thường của chính phòng đó, nhìn một cái
# là thấy phòng nào ngày nào hụt hoặc bứt tốc.
HEAT_NGAY = {"styleConditions": [
    {"condition": "params.data.loai_dong != 'data'", "style": {}},
    {"condition": "params.value === 0",
     "style": {"backgroundColor": "#FBE3E1", "color": "#93241C"}},
    {"condition": "params.value < params.data._tb * 0.6",
     "style": {"backgroundColor": "#FDEDE9", "color": "#9A3412"}},
    {"condition": "params.value < params.data._tb * 0.95",
     "style": {"backgroundColor": "#FFF8E6", "color": "#6B5104"}},
    {"condition": "params.value < params.data._tb * 1.4",
     "style": {"backgroundColor": "#E8F5EC", "color": "#14532D"}},
    {"condition": "true",
     "style": {"backgroundColor": "#BFE6C8", "color": "#0F3D22", "fontWeight": "700"}},
]}

MAU = ["#0072BC", "#F37021", "#00A650", "#37A5E6", "#8C6FD1", "#0E7490"]
MAU_PHONG = ["#0072BC", "#F37021", "#00A650", "#37A5E6", "#8C6FD1", "#0E7490", "#D946A0",
             "#B45309"]


def _thang_mac_dinh() -> str:
    ds = cac_thang_co_du_lieu()
    return ds[0] if ds else "2026-09"


def topbar():
    return [html.Div([html.H1("Tracking ngày"),
                      html.Div("Số bán của từng phòng theo từng ngày trong tháng",
                               className="sub")]),
            html.Div(className="spacer"),
            html.Div(id="tracking-cap-nhat")]


def layout():
    thangs = cac_thang_co_du_lieu() or [_thang_mac_dinh()]
    return html.Div([
        html.Div([
            field("Kỳ báo cáo", chon_ky("tk-thang", thangs)),
            field("Chi nhánh", chi_nhanh_control("tk-cn")),
            html.Div(className="grow"),
            field("Chỉ số", seg_control("tk-metric",
                                        [("online", "Số Online"), ("vvip", "Số V.VIP"),
                                         ("camera", "Camera"), ("ban_moi", "Bán mới")], "online")),
            field("Cách xem", seg_control("tk-view", [("ngay", "Từng ngày"),
                                                      ("congdon", "Cộng dồn")], "ngay")),
        ], className="toolbar loc-trang"),

        html.Div(id="tk-kpi", className="kpi-row"),

        card([
            html.Div([
                html.Div("Màu ô so với mức trung bình của chính phòng đó: xanh là ngày tốt, "
                         "đỏ là ngày hụt.", className="desc", style={"margin": 0}),
                html.Div(className="grow"),
                field("Cỡ bảng", dcc.Dropdown(
                    id="tk-zoom", clearable=False, value="fit", options=ZOOM_OPTIONS,
                    style={"width": "150px"})),
                field(" ", html.Button([icon("download", 14), html.Span("Xuất CSV")],
                                       id="tk-export", className="btn")),
            ], className="toolbar", style={"marginBottom": "12px"}),
            html.Div(dcc.Loading(dag.AgGrid(
                id="tk-grid", className="ag-theme-quartz ag-theme-ftel",
                columnDefs=[], rowData=[],
                defaultColDef={"resizable": True, "sortable": False, "suppressMovable": True},
                dashGridOptions={"suppressCellFocus": True, "headerHeight": 38, "rowHeight": 32,
                                 "domLayout": "normal"},
                getRowStyle=GRID_STYLE_CONDITIONS,
                style={"width": "100%", "height": "560px"})),
                id="tk-zoom-wrap", className="zoom-wrap")],
            title="Số bán theo ngày"),

        html.Div([
            html.Div(card([
                html.Div([field("Nhóm biểu đồ theo", seg_control("tk-nhom", [("bay", "Bầy"),
                                                                             ("phong", "Phòng")], "bay"))],
                         className="toolbar", style={"marginBottom": "10px"}),
                dcc.Loading(dcc.Graph(id="tk-line",
                                      config={"displayModeBar": False, "responsive": True},
                                      style={"width": "100%"}))],
                title="Diễn biến theo ngày",
                desc="Đường chấm xám là toàn chi nhánh"),
                     className="chart-col"),
            html.Div(card([dcc.Loading(dcc.Graph(id="tk-bar", config={"displayModeBar": False, "responsive": True},
                                                 style={"width": "100%"}))],
                          title="Xếp hạng phòng",
                          desc="Vạch cam là chỉ tiêu tháng của phòng"),
                     className="chart-col"),
        ], className="chart-row"),
    ])


def _fig(fig: go.Figure, height: int = 320) -> go.Figure:
    fig.update_layout(height=height, autosize=True, margin=dict(l=8, r=8, t=10, b=8),
                      font=dict(family="Inter, Segoe UI, sans-serif", size=12, color="#1B2733"),
                      plot_bgcolor="white", paper_bgcolor="white",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                      hovermode="x unified")
    fig.update_xaxes(showgrid=False, linecolor="#E4E9F0", ticks="outside", tickcolor="#E4E9F0")
    fig.update_yaxes(gridcolor="#F1F5F9", zeroline=False)
    return fig


def register(app):
    gan_dieu_huong_ky(app, "tk-thang")

    @app.callback(Output("tk-grid", "exportDataAsCsv"), Input("tk-export", "n_clicks"),
                  prevent_initial_call=True)
    def _export(n):
        return bool(n)

    @app.callback(
        Output("tk-kpi", "children"), Output("tk-grid", "columnDefs"),
        Output("tk-grid", "rowData"), Output("tk-line", "figure"),
        Output("tk-bar", "figure"), Output("tracking-cap-nhat", "children"),
        Output("tk-zoom-wrap", "style"), Output("tk-grid", "style"),
        Input("tk-thang", "value"), Input("tk-metric", "value"), Input("tk-view", "value"),
        Input("tk-zoom", "value"), Input("tk-cn", "value"), Input("tk-nhom", "value"),
        Input("ui-vw", "data"), State("ui-sidebar", "data"))
    def _cap_nhat(thang, metric, view, zoom, chi_nhanh, nhom, vw, sidebar):
        scope = loc_chi_nhanh(current_user.phong_duoc_xem(), chi_nhanh, thang)
        cong_don = view == "congdon"
        den_ngay = ngay_co_du_lieu(thang) or month_range(thang)[2]

        # chỉ hiện tới ngày có dữ liệu - khỏi thừa 20 cột trống của những ngày chưa tới
        df = tracking_table(thang, metric, cong_don=cong_don, den_ngay=den_ngay,
                            chi_phong=scope)
        day_cols = [c for c in df.columns if c.isdigit()]
        # trung bình mỗi ngày của từng phòng -> mốc tô màu riêng cho chính dòng đó
        df["_tb"] = df[day_cols].mean(axis=1).round(2) if day_cols else 0

        cols = [{"field": "bay", "headerName": "Bầy", "pinned": "left", "width": 165,
                 "cellStyle": {"fontWeight": "600"}},
                {"field": "phong", "headerName": "Phòng kinh doanh", "pinned": "left", "width": 165}]
        # flex để các cột ngày giãn đều lấp hết bề ngang, không chừa khoảng trắng bên phải
        cols += [{"field": c, "headerName": c.zfill(2), "minWidth": RONG_NGAY, "flex": 1,
                  "type": "numericColumn", "cellStyle": HEAT_NGAY} for c in day_cols]
        cols.append({"field": "Tổng", "headerName": "TỔNG", "pinned": "right", "width": 88,
                     "type": "numericColumn", "cellStyle": {"fontWeight": "700"}})

        kpis = _kpi_cards(thang, den_ngay, scope)
        line = _line_chart(thang, metric, cong_don, scope, den_ngay, nhom or "bay")
        bar = _bar_chart(thang, metric, scope, den_ngay)
        cap_nhat = html.Span([
            html.Span("Dữ liệu đến ngày ", style={"color": "var(--text-muted)"}),
            html.B(f"{den_ngay:02d}/{thang[5:7]}/{thang[:4]}")],
            className="badge muted")

        rong_bang = RONG_CO_DINH + RONG_NGAY * len(day_cols)
        if zoom == "fit":
            rong_cua_so = (vw or {}).get("w") or 1440
            con_lai = max(420, rong_cua_so - (66 if (sidebar or {}).get("thu_gon") else 212) - 124)
            ty_le = min(1.0, round(con_lai / (rong_bang + 12), 3))
        else:
            ty_le = (zoom or 100) / 100
        cao_man_hinh = (vw or {}).get("h") or 900
        cao_bang = max(300, min(760, int((cao_man_hinh - 430) / ty_le)))
        return (kpis, cols, df.to_dict("records"), line, bar, cap_nhat,
                {"zoom": ty_le} if ty_le != 1 else {},
                {"width": "100%", "height": f"{cao_bang}px"})

    def _kpi_cards(thang, den_ngay, scope):
        s = summary_phong(thang, den_ngay=den_ngay, chi_phong=scope)
        online, vvip, camera = int(s.online.sum()), int(s.vvip.sum()), int(s.camera.sum())
        ton, ck = int(s.ton.sum()), int(s.cung_ky_thang_truoc.sum())
        tang = (online - ck) / ck * 100 if ck else None
        ty_vvip = vvip / online * 100 if online else 0
        td = tien_do_thang(thang, den_ngay=den_ngay)
        mt = td["muc_tieu"]
        htkh = (online / mt * 100) if mt else None
        trang_thai = "" if htkh is None else ("ok" if htkh >= td["ty_le_thoi_gian"] else "warn")

        delta = (html.Span(f"{tang:+.1f}% so cùng kỳ T{int(thang[5:7]) - 1}",
                           className=f"delta {'up' if tang >= 0 else 'down'}")
                 if tang is not None else "")
        return [
            kpi("Số Online", f"{online:,}".replace(",", "."), delta),
            kpi("Số V.VIP", f"{vvip:,}".replace(",", "."), f"Tỷ lệ V.VIP/Online {ty_vvip:.1f}%"),
            kpi("Camera", f"{camera:,}".replace(",", "."), "Đã loại các dòng trùng"),
            kpi("Số tồn", f"{ton:,}".replace(",", "."),
                "Đã ký nhưng chưa online",
                "warn" if ton else ""),
            kpi("Hoàn thành kế hoạch", f"{htkh:.1f}%" if htkh else "—",
                f"Chỉ tiêu tháng {mt:,.0f}".replace(",", ".") if mt
                else "Chưa nhập chỉ tiêu (mục Cấu hình)", trang_thai),
            kpi("Tiến độ tháng", f"{td['ngay_da_chay']}/{td['so_ngay_trong_thang']} ngày",
                (f"Cần {td['can_moi_ngay']} số/ngày trong {td['con_lai_ngay']} ngày còn lại"
                 if td["can_moi_ngay"] else f"Bình quân {td['tb_ngay_hien_tai']} số/ngày")),
        ]

    def _line_chart(thang, metric, cong_don, scope, den_ngay, nhom="bay"):
        daily = daily_counts(thang, metric)
        if scope is not None:
            daily = daily.loc[[c for c in daily.index if c in set(scope)]]
        daily = daily.loc[:, [c for c in daily.columns if c <= den_ngay]]
        if cong_don:
            daily = daily.cumsum(axis=1)
        fig = go.Figure()
        meta = {p["code"]: p for p in phong_order()}
        if nhom == "phong":
            # 8 phòng cao nhất vẽ riêng, phần còn lại gộp một đường cho đỡ rối
            tong = daily.sum(axis=1).sort_values(ascending=False)
            chinh = [c for c in tong.index[:8]]
            for i, code in enumerate(chinh):
                vals = daily.loc[code]
                fig.add_trace(go.Scatter(
                    x=list(vals.index), y=list(vals.values), mode="lines+markers",
                    name=meta.get(code, {}).get("ten", code),
                    line=dict(width=2, color=MAU_PHONG[i % len(MAU_PHONG)]),
                    marker=dict(size=5)))
            con_lai = [c for c in daily.index if c not in set(chinh)]
            if con_lai:
                vals = daily.loc[con_lai].sum()
                fig.add_trace(go.Scatter(x=list(vals.index), y=list(vals.values),
                                         mode="lines", name="Các phòng còn lại",
                                         line=dict(width=1.6, color="#B9C5D3")))
            tong_all = daily.sum()
            fig.add_trace(go.Scatter(x=list(tong_all.index), y=list(tong_all.values), mode="lines",
                                     name="Toàn chi nhánh",
                                     line=dict(width=2.5, color="#94A3B8", dash="dot")))
            fig.update_xaxes(title=None, dtick=1)
            return _fig(fig)

        bays = bay_info()
        for i, (bcode, binfo) in enumerate(sorted(bays.items(), key=lambda kv: kv[1]["thu_tu"])):
            codes = [c for c in daily.index if meta.get(c, {}).get("bay") == bcode]
            if not codes:
                continue
            vals = daily.loc[codes].sum()
            fig.add_trace(go.Scatter(x=list(vals.index), y=list(vals.values), mode="lines+markers",
                                     name=binfo["ten"], line=dict(width=2, color=MAU[i % len(MAU)]),
                                     marker=dict(size=5)))
        tong = daily.sum()
        fig.add_trace(go.Scatter(x=list(tong.index), y=list(tong.values), mode="lines",
                                 name="Toàn chi nhánh", line=dict(width=2.5, color="#94A3B8",
                                                                  dash="dot")))
        fig.update_xaxes(title=None, dtick=1)
        return _fig(fig)

    def _bar_chart(thang, metric, scope, den_ngay):
        s = summary_phong(thang, den_ngay=den_ngay, chi_phong=scope)
        col = {"online": "online", "vvip": "vvip", "camera": "camera",
               "ban_moi": "ban_moi"}[metric]
        s = s[s[col] > 0].sort_values(col)
        fig = go.Figure()
        fig.add_trace(go.Bar(x=s[col], y=s.phong, orientation="h", marker_color="#0072BC",
                             name=METRIC_LABEL[metric], text=s[col], textposition="auto"))
        if metric == "online" and s.muc_tieu_internet.notna().any():
            fig.add_trace(go.Scatter(x=s.muc_tieu_internet, y=s.phong, mode="markers",
                                     name="Chỉ tiêu tháng",
                                     marker=dict(symbol="line-ns", size=14, line=dict(width=2),
                                                 color="#F37021")))
        fig.update_layout(bargap=0.25, hovermode="closest")
        return _fig(fig, height=max(320, 22 * len(s) + 90))
