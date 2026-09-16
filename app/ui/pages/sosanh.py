"""Tab 2 "So sánh" của trang Tracking ngày & So sánh (dienbien.py): khoảng ngày tự chọn + Top hụt số."""
from __future__ import annotations

from datetime import date, timedelta

import dash_ag_grid as dag
import plotly.graph_objects as go
from dash import Input, Output, State, ctx, dcc, html, no_update
from flask_login import current_user

from app.auth import ghi_log, loc_nhan_su
from app.export_phan_tich import xuat_phan_tich
from app.metrics import METRIC_LABEL, cac_ngay_co_du_lieu, so_sanh_acc, so_sanh_ky
from app.org import loc_chi_nhanh, phong_order
from app.ui.components import card, chi_nhanh_control, field, kpi, pct_vn, seg_control, so_vn
from app.ui import ky_chung as kc
from app.ui.icons import icon

TOP_N = 15
SO1 = {"function": "params.value == null ? '' : Number(params.value).toLocaleString('vi-VN', "
                   "{minimumFractionDigits: 1, maximumFractionDigits: 1})"}


def _dp(gid, ngays, mac_dinh):
    return dcc.DatePickerSingle(id=gid, date=mac_dinh, display_format="DD/MM/YYYY",
                                min_date_allowed=ngays[0] if ngays else None,
                                max_date_allowed=ngays[-1] if ngays else None,
                                first_day_of_week=1, clearable=False, className="date-pick")


def layout(ky: dict | None = None):
    ky = ky or {}
    ngays = cac_ngay_co_du_lieu()
    cuoi = date.fromisoformat(ngays[-1]) if ngays else date.today()
    k2_tu, k2_den = cuoi - timedelta(days=6), cuoi
    k1_tu, k1_den = k2_tu - timedelta(days=7), k2_tu - timedelta(days=1)
    chon = kc.hai_ky(ky, ngays)          # đã chọn kỳ ở trang khác: kỳ 2 = kỳ đó
    if chon:
        k1_tu, k1_den, k2_tu, k2_den = (date.fromisoformat(x) for x in chon)
    return html.Div([
        card([
            # Hàng 1: Preset shortcuts + Chỉ số + Chi nhánh (tự hiểu, không cần label)
            html.Div([
                html.Button("7 ngày gần nhất", id="ss-p-7ngay", className="chip",
                            title="So 7 ngày gần nhất vs 7 ngày trước"),
                html.Button("Tuần này", id="ss-p-tuan", className="chip",
                            title="Tuần này vs tuần trước"),
                html.Button("Tháng này", id="ss-p-thang", className="chip",
                            title="Tháng này vs cùng kỳ tháng trước"),
                html.Div(className="grow"),
                seg_control("ss-metric", [("online", "Số Online"), ("vvip", "Số V.VIP"),
                                          ("camera", "Camera")], "online"),
                html.Div(style={"width": "1px", "background": "#E4E9F0",
                                "alignSelf": "stretch", "margin": "0 10px"}),
                chi_nhanh_control("ss-cn", ky.get("cn", "all")),
                html.Button([icon("download", 14), html.Span("Excel")], id="ss-export", className="btn",
                            title="Tải bảng theo phòng, Top giảm và Top tăng (mỗi bảng một sheet)",
                            style={"marginLeft": "10px"}),
            ], className="toolbar", style={"marginBottom": "10px"}),
            dcc.Download(id="ss-tai-xuong"),
            # Hàng 2: Khoảng thời gian compact (2 pickers/kỳ gộp chung) + Nhóm phòng
            html.Div([
                html.Div([
                    html.Label("Kỳ 1"),
                    html.Div([
                        _dp("ss-k1-tu", ngays, k1_tu.isoformat()),
                        html.Span("→", style={"color": "#94A3B8", "padding": "0 5px",
                                               "alignSelf": "center", "flexShrink": "0",
                                               "lineHeight": "1"}),
                        _dp("ss-k1-den", ngays, k1_den.isoformat()),
                    ], style={"display": "flex", "alignItems": "center"}),
                ], className="field"),
                html.Div(style={"width": "1px", "background": "#E4E9F0",
                                "alignSelf": "stretch", "margin": "4px 14px"}),
                html.Div([
                    html.Label("Kỳ 2"),
                    html.Div([
                        _dp("ss-k2-tu", ngays, k2_tu.isoformat()),
                        html.Span("→", style={"color": "#94A3B8", "padding": "0 5px",
                                               "alignSelf": "center", "flexShrink": "0",
                                               "lineHeight": "1"}),
                        _dp("ss-k2-den", ngays, k2_den.isoformat()),
                    ], style={"display": "flex", "alignItems": "center"}),
                ], className="field"),
                html.Div(className="grow"),
                field("Nhóm phòng", dcc.Dropdown(
                    id="ss-nhom", clearable=False, value="kd", style={"width": "165px"},
                    options=[{"label": "Chỉ phòng kinh doanh", "value": "kd"},
                             {"label": "Tất cả phòng", "value": "all"}])),
            ], className="toolbar"),
        ], title="Khoảng so sánh",
            desc="Kỳ 1 là mốc cũ, Kỳ 2 là mốc mới. Dùng nút gợi ý hoặc tự chọn ngày."),

        html.Div(id="ss-kpi", className="kpi-row kpi-6"),

        html.Div([
            html.Div(card([dcc.Loading(dcc.Graph(
                id="ss-chart", config={"displayModeBar": False, "responsive": True},
                style={"width": "100%"}))], title="Chênh lệch theo phòng",
                desc="Xanh là tăng so với kỳ 1, đỏ là giảm"),
                className="chart-col"),
            html.Div(card([dcc.Loading(dag.AgGrid(
                id="ss-phong", className="ag-theme-quartz ag-theme-ftel", columnDefs=[], rowData=[],
                defaultColDef={"resizable": True, "sortable": True},
                dashGridOptions={"suppressCellFocus": True, "domLayout": "normal"},
                style={"width": "100%", "height": "420px"}))],
                title="Chi tiết theo phòng"),
                className="chart-col"),
        ], className="chart-row"),

        html.Div([
            html.Div(card([
                dcc.Loading(dag.AgGrid(
                    id="ss-hut", className="ag-theme-quartz ag-theme-ftel", columnDefs=[],
                    rowData=[], defaultColDef={"resizable": True, "sortable": True},
                    dashGridOptions={"suppressCellFocus": True, "domLayout": "normal"},
                    style={"width": "100%", "height": "420px"}))],
                title=f"Top {TOP_N} giảm sâu nhất",
                desc="Giảm nhiều nhất so với kỳ 1 - ưu tiên trao đổi trước"),
                className="chart-col"),
            html.Div(card([
                dcc.Loading(dag.AgGrid(
                    id="ss-tang", className="ag-theme-quartz ag-theme-ftel", columnDefs=[],
                    rowData=[], defaultColDef={"resizable": True, "sortable": True},
                    dashGridOptions={"suppressCellFocus": True, "domLayout": "normal"},
                    style={"width": "100%", "height": "420px"}))],
                title=f"Top {TOP_N} tăng mạnh nhất",
                desc="Tăng nhiều nhất so với kỳ 1 - nên ghi nhận kịp thời"),
                className="chart-col"),
        ], className="chart-row"),
    ])


def _cols_phong():
    return [
        {"field": "phong", "headerName": "Phòng", "flex": 2, "minWidth": 150, "pinned": "left"},
        {"field": "bay", "headerName": "Bầy", "flex": 1.4, "minWidth": 110},
        {"field": "ky1", "headerName": "Kỳ 1", "flex": 1, "minWidth": 76, "type": "numericColumn"},
        {"field": "ky2", "headerName": "Kỳ 2", "flex": 1, "minWidth": 76, "type": "numericColumn"},
        {"field": "chenh", "headerName": "Chênh", "flex": 1.2, "minWidth": 92,
         "type": "numericColumn",
         "cellStyle": {"styleConditions": [
             {"condition": "params.value < 0",
              "style": {"color": "#C8372D", "fontWeight": "700"}},
             {"condition": "params.value > 0",
              "style": {"color": "#04843F", "fontWeight": "700"}}]}},
        {"field": "ty_le", "headerName": "%", "flex": 1, "minWidth": 72, "type": "numericColumn",
         "valueFormatter": {"function": "params.value == null ? '' : (params.value > 0 ? '+' : '') + "
                                        "Math.round(params.value) + '%'"}},
        {"field": "tb1", "headerName": "TB/ngày kỳ 1", "flex": 1, "minWidth": 80,
         "type": "numericColumn", "valueFormatter": SO1,
         "headerTooltip": "Trung bình số/ngày của Kỳ 1"},
        {"field": "tb2", "headerName": "TB/ngày kỳ 2", "flex": 1, "minWidth": 80,
         "type": "numericColumn", "valueFormatter": SO1,
         "headerTooltip": "Trung bình số/ngày của Kỳ 2"},
    ]


def _cols_acc():
    return [
        {"field": "stt", "headerName": "#", "width": 52, "maxWidth": 52},
        {"field": "acc", "headerName": "Acc nhân viên", "flex": 2, "minWidth": 140},
        {"field": "phong", "headerName": "Phòng", "flex": 1.6, "minWidth": 110},
        {"field": "ky1", "headerName": "Kỳ 1", "flex": 1, "minWidth": 66, "type": "numericColumn"},
        {"field": "ky2", "headerName": "Kỳ 2", "flex": 1, "minWidth": 66, "type": "numericColumn"},
        {"field": "chenh_txt", "headerName": "Chênh", "flex": 1, "minWidth": 84,
         "cellStyle": {"styleConditions": [
             {"condition": "params.value.indexOf('▼') >= 0",
              "style": {"color": "#C8372D", "fontWeight": "700"}},
             {"condition": "params.value.indexOf('▲') >= 0",
              "style": {"color": "#04843F", "fontWeight": "700"}}]}},
        {"field": "pct", "headerName": "%", "flex": 0.9, "minWidth": 70,
         "cellStyle": {"styleConditions": [
             {"condition": "params.value && params.value.indexOf('-') >= 0",
              "style": {"color": "#C8372D"}},
             {"condition": "params.value && params.value.indexOf('+') >= 0",
              "style": {"color": "#04843F"}}]}},
    ]


def register(app):
    kc.ghi(app, ("ss-k2-tu", "date"), ("ss-k2-den", "date"), ("ss-cn", "value"),
           chuyen=lambda tu, den, cn: {"tu": tu, "den": den, "cn": cn})
    @app.callback(Output("ss-k1-tu", "date"), Output("ss-k1-den", "date"),
                  Output("ss-k2-tu", "date"), Output("ss-k2-den", "date"),
                  Input("ss-p-7ngay", "n_clicks"), Input("ss-p-tuan", "n_clicks"),
                  Input("ss-p-thang", "n_clicks"), prevent_initial_call=True)
    def _chon_nhanh(_a, _b, _c):
        ngays = cac_ngay_co_du_lieu()
        cuoi = date.fromisoformat(ngays[-1]) if ngays else date.today()
        trig = ctx.triggered_id
        if trig == "ss-p-tuan":
            dau_tuan = cuoi - timedelta(days=cuoi.weekday())
            k1_tu, k1_den = dau_tuan - timedelta(days=7), dau_tuan - timedelta(days=1)
            k2_tu, k2_den = dau_tuan, cuoi
        elif trig == "ss-p-thang":
            k2_tu, k2_den = cuoi.replace(day=1), cuoi
            cuoi_truoc = k2_tu - timedelta(days=1)
            k1_tu = cuoi_truoc.replace(day=1)
            k1_den = date(cuoi_truoc.year, cuoi_truoc.month, min(cuoi.day, cuoi_truoc.day))
        else:
            k2_tu, k2_den = cuoi - timedelta(days=6), cuoi
            k1_tu, k1_den = k2_tu - timedelta(days=7), k2_tu - timedelta(days=1)
        return k1_tu.isoformat(), k1_den.isoformat(), k2_tu.isoformat(), k2_den.isoformat()

    @app.callback(Output("ss-kpi", "children"), Output("ss-phong", "columnDefs"),
                  Output("ss-phong", "rowData"), Output("ss-hut", "columnDefs"),
                  Output("ss-hut", "rowData"), Output("ss-tang", "columnDefs"),
                  Output("ss-tang", "rowData"), Output("ss-chart", "figure"),
                  Output("ss-badge", "children"),
                  Input("ss-k1-tu", "date"), Input("ss-k1-den", "date"),
                  Input("ss-k2-tu", "date"), Input("ss-k2-den", "date"),
                  Input("ss-metric", "value"), Input("ss-nhom", "value"),
                  Input("ss-cn", "value"), Input("db-tab", "value"))
    def _cap_nhat(k1_tu, k1_den, k2_tu, k2_den, metric, nhom, chi_nhanh, tab):
        if tab != "sosanh":                  # đang xem tab Tracking ngày: không tính phần này
            return (no_update,) * 9
        dfp, dfa, hut, tang, so_ngay1, so_ngay2 = _tinh(k1_tu, k1_den, k2_tu, k2_den, metric, nhom,
                                                        chi_nhanh)
        t1, t2 = int(dfp.ky1.sum()), int(dfp.ky2.sum())
        chenh = t2 - t1
        pct = (chenh / t1 * 100) if t1 else None
        giam = dfp[dfp.chenh < 0]
        tang_phong = dfp[dfp.chenh > 0]
        kpis = [
            kpi(f"Kỳ 1 ({so_ngay1} ngày)", so_vn(t1),
                f"{k1_tu[8:10]}/{k1_tu[5:7]} → {k1_den[8:10]}/{k1_den[5:7]} · TB "
                f"{so_vn(t1 / so_ngay1, 1)}/ngày"),
            kpi(f"Kỳ 2 ({so_ngay2} ngày)", so_vn(t2),
                f"{k2_tu[8:10]}/{k2_tu[5:7]} → {k2_den[8:10]}/{k2_den[5:7]} · TB "
                f"{so_vn(t2 / so_ngay2, 1)}/ngày"),
            kpi("Chênh lệch", so_vn(chenh, dau=True),
                pct_vn(pct, dau=True, trong=""), "ok" if chenh >= 0 else "bad"),
            kpi("Phòng tăng", f"{len(tang_phong)}/{len(dfp)}",
                ", ".join(tang_phong.phong.head(3)) if len(tang_phong) else "Không có phòng nào tăng",
                "ok" if len(tang_phong) else ""),
            kpi("Phòng giảm", f"{len(giam)}/{len(dfp)}",
                ", ".join(giam.phong.head(3)) if len(giam) else "Không có phòng nào giảm",
                "warn" if len(giam) else "ok"),
            kpi("Nhân sự hụt số", f"{int((dfa.chenh < 0).sum())}",
                f"Tăng: {int((dfa.chenh > 0).sum())} người"),
        ]


        d = dfp[dfp.chenh != 0].sort_values("chenh")
        fig = go.Figure(go.Bar(
            x=d.chenh, y=d.phong, orientation="h",
            marker_color=["#C8372D" if v < 0 else "#00A650" for v in d.chenh],
            text=[f"{v:+d}" for v in d.chenh], textposition="outside"))
        fig.update_layout(height=max(320, 26 * len(d) + 80),
                          margin=dict(l=8, r=30, t=10, b=8), plot_bgcolor="white",
                          paper_bgcolor="white", showlegend=False,
                          font=dict(family="Inter, Segoe UI, sans-serif", size=12))
        fig.update_xaxes(zeroline=True, zerolinecolor="#CBD5E1", gridcolor="#F1F5F9",
                         title=f"Chênh lệch {METRIC_LABEL[metric]}")
        fig.update_yaxes(showgrid=False)

        badge = html.Span(f"{METRIC_LABEL[metric]} · {so_ngay1} ngày vs {so_ngay2} ngày",
                          className="badge muted")
        return (kpis, _cols_phong(), dfp.to_dict("records"), _cols_acc(),
                hut.to_dict("records"), _cols_acc(), tang.to_dict("records"), fig, badge)

    @app.callback(Output("ss-tai-xuong", "data"), Input("ss-export", "n_clicks"),
                  State("ss-k1-tu", "date"), State("ss-k1-den", "date"),
                  State("ss-k2-tu", "date"), State("ss-k2-den", "date"),
                  State("ss-metric", "value"), State("ss-nhom", "value"), State("ss-cn", "value"),
                  prevent_initial_call=True)
    def _export(n, k1_tu, k1_den, k2_tu, k2_den, metric, nhom, chi_nhanh):
        if not n or not all((k1_tu, k1_den, k2_tu, k2_den)):
            return no_update
        dfp, _, hut, tang, _, _ = _tinh(k1_tu, k1_den, k2_tu, k2_den, metric, nhom, chi_nhanh)
        ky = f"{_dd(k1_tu)}-{_dd(k1_den)} so với {_dd(k2_tu)}-{_dd(k2_den)}"
        cot_phong = [("phong", "Phòng", "text"), ("bay", "Bầy", "text"), ("ky1", "Kỳ 1", "so"),
                     ("ky2", "Kỳ 2", "so"), ("chenh", "Chênh", "so"), ("ty_le", "Chênh %", "pct"),
                     ("tb1", "TB/ngày kỳ 1", "so"), ("tb2", "TB/ngày kỳ 2", "so")]
        cot_acc = [("stt", "#", "so"), ("acc", "Acc nhân viên", "text"), ("phong", "Phòng", "text"),
                   ("ky1", "Kỳ 1", "so"), ("ky2", "Kỳ 2", "so"), ("chenh", "Chênh", "so"),
                   ("pct", "Chênh %", "text")]
        bang = [("Theo phòng", dfp, cot_phong)]
        if current_user.duoc_xem_nhan_su:
            bang += [(f"Top {TOP_N} giảm", hut, cot_acc), (f"Top {TOP_N} tăng", tang, cot_acc)]
        noi_dung = xuat_phan_tich("", f"SO SÁNH KỲ · {METRIC_LABEL[metric].upper()} · {ky}", bang)
        ghi_log("xuat_so_sanh_ky", f"{metric} {ky} {chi_nhanh}")
        return dcc.send_bytes(noi_dung, f"SoSanhKy_{metric}_{k2_den.replace('-', '')}.xlsx")


def _dd(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}"


def _tinh(k1_tu, k1_den, k2_tu, k2_den, metric, nhom, chi_nhanh):
    """(bảng phòng, bảng acc, top giảm, top tăng, số ngày kỳ 1, số ngày kỳ 2) trong phạm vi quyền."""
    scope = loc_chi_nhanh(current_user.phong_duoc_xem(), chi_nhanh)
    if nhom == "kd":
        kd = [p["code"] for p in phong_order() if p["loai"] in ("IBB", "DIABAN")]
        scope = kd if scope is None else [c for c in scope if c in set(kd)]
    ky1, ky2 = (k1_tu, k1_den), (k2_tu, k2_den)
    dfp = so_sanh_ky(ky1, ky2, metric, chi_phong=scope)
    dfa = so_sanh_acc(ky1, ky2, metric, chi_phong=loc_nhan_su(scope, current_user.phong_nhan_su()))
    so_ngay1 = (date.fromisoformat(k1_den) - date.fromisoformat(k1_tu)).days + 1
    so_ngay2 = (date.fromisoformat(k2_den) - date.fromisoformat(k2_tu)).days + 1
    dfp["tb1"] = (dfp.ky1 / so_ngay1).round(1)
    dfp["tb2"] = (dfp.ky2 / so_ngay2).round(1)

    hut = dfa[dfa.chenh < 0].head(TOP_N).copy()
    hut.insert(0, "stt", range(1, len(hut) + 1))
    hut["chenh_txt"] = ["▼" + str(abs(int(c))) for c in hut.chenh]
    hut["pct"] = [f"{c/k*100:+.0f}%" if k else "" for c, k in zip(hut.chenh, hut.ky1)]
    tang = dfa[dfa.chenh > 0].sort_values("chenh", ascending=False).head(TOP_N).copy()
    tang.insert(0, "stt", range(1, len(tang) + 1))
    tang["chenh_txt"] = ["▲" + str(int(c)) for c in tang.chenh]
    tang["pct"] = [f"{c/k*100:+.0f}%" if k else "" for c, k in zip(tang.chenh, tang.ky1)]
    return dfp, dfa, hut, tang, so_ngay1, so_ngay2
