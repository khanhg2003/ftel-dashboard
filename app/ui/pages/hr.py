"""Trang hiệu suất nhân sự: nối số bán với hồ sơ NSLĐ."""
from __future__ import annotations

import dash_ag_grid as dag
import plotly.graph_objects as go
from dash import Input, Output, dcc, html
from flask_login import current_user

from app.config import rules_config
from app.hr_metrics import (canh_bao_nhan_su, duong_cong_nang_suat,
                            hieu_suat_nhan_su, thoi_gian_trien_khai,
                            tong_hop_tham_nien)
from app.metrics import cac_thang_co_du_lieu
from app.org import loc_chi_nhanh
from app.ui.components import (card, chi_nhanh_control, chon_ky, field, gan_dieu_huong_ky,
                               kpi, seg_control)
from app.ui.icons import icon

NHOM_TEN = {g["code"]: g["ten"] for g in rules_config()["tham_nien"]}
MAU_NHOM = {"MOI": "#F37021", "DANG_LEN": "#37A5E6", "ON_DINH": "#0072BC", "LAU_NAM": "#00A650"}


def topbar():
    return [html.Div([html.H1("Hiệu suất nhân sự"),
                      html.Div("Số bán theo từng nhân sự, đối chiếu thâm niên và NSLĐ",
                               className="sub")]),
            html.Div(className="spacer"),
            html.Div(id="hr-nguon-hr")]


def layout():
    thangs = cac_thang_co_du_lieu() or ["2026-09"]
    return html.Div([
        html.Div([
            field("Kỳ báo cáo", chon_ky("hr-thang", thangs)),
            field("Nhóm thâm niên",
                  dcc.Dropdown(id="hr-nhom", multi=True, placeholder="Tất cả",
                               options=[{"label": v, "value": k} for k, v in NHOM_TEN.items()],
                               style={"width": "320px"})),
            field("Chỉ hiện", dcc.Dropdown(
                id="hr-loc", clearable=False, value="all", style={"width": "220px"},
                options=[{"label": "Tất cả nhân sự", "value": "all"},
                         {"label": "Chưa có số trong kỳ", "value": "zero"},
                         {"label": "NSLĐ chưa đạt", "value": "notok"}])),
            html.Div(className="grow"),
            field("Chi nhánh", chi_nhanh_control("hr-cn")),
        ], className="toolbar loc-trang"),

        html.Div(id="hr-kpi", className="kpi-row"),

        html.Div([
            html.Div(card([dcc.Graph(id="hr-bar-nhom",
                                     config={"displayModeBar": False, "responsive": True},
                                     style={"width": "100%"})],
                          title="Năng suất theo thâm niên",
                          desc="Số bán bình quân mỗi nhân sự trong kỳ, theo nhóm thâm niên"),
                     className="chart-col"),
            html.Div(card([
                html.Div([html.Div(className="grow"),
                          field("Xếp hạng", seg_control("hr-xep", [("cao", "Bán nhiều nhất"),
                                                                   ("thap", "Bán ít nhất")],
                                                        "cao"))],
                         className="toolbar", style={"marginBottom": "10px"}),
                dcc.Graph(id="hr-scatter", config={"displayModeBar": False, "responsive": True},
                          style={"width": "100%"})],
                title="Xếp hạng nhân sự",
                desc="15 người đứng đầu hoặc cuối bảng trong kỳ, màu theo nhóm thâm niên"),
                     className="chart-col"),
        ], className="chart-row"),

        html.Div([
            html.Div(card([dcc.Loading(dcc.Graph(
                id="hr-rampup", config={"displayModeBar": False, "responsive": True},
                style={"width": "100%"}))],
                title="Tốc độ lên tay của người mới",
                desc="Năng suất bình quân theo số tháng làm việc. Đường cam là mức của nhóm "
                     "trên 12 tháng"),
                className="chart-col"),
            html.Div(card([dcc.Loading(dcc.Graph(
                id="hr-leadtime", config={"displayModeBar": False, "responsive": True},
                style={"width": "100%"}))],
                title="Thời gian đấu nối",
                desc="Số ngày bình quân từ lúc ký đến khi khách online, theo phòng"),
                className="chart-col"),
        ], className="chart-row"),

        card([html.Div(id="hr-canhbao-tomtat"),
              dcc.Loading(dag.AgGrid(
                  id="hr-canhbao", className="ag-theme-quartz ag-theme-ftel", columnDefs=[],
                  rowData=[], defaultColDef={"resizable": True, "sortable": True},
                  dashGridOptions={"suppressCellFocus": True, "domLayout": "normal"},
                  style={"width": "100%", "height": "360px"}))],
             title="Nhân sự cần trao đổi sớm",
             desc="Nhiều ngày liền không có số hoặc tuần này sụt mạnh so với tuần trước"),

        card([
            html.Div([html.Div(id="hr-tom-tat", className="desc", style={"margin": 0}),
                      html.Div(className="grow"),
                      html.Button([icon("download", 14), html.Span("Xuất CSV")], id="hr-export",
                                  className="btn")],
                     className="toolbar", style={"marginBottom": "12px"}),
            dcc.Loading(dag.AgGrid(
            id="hr-grid", className="ag-theme-quartz ag-theme-ftel", columnDefs=[], rowData=[],
            defaultColDef={"resizable": True, "sortable": True, "filter": True},
            dashGridOptions={"suppressCellFocus": True, "rowHeight": 32, "pagination": True,
                             "paginationPageSize": 12, "paginationPageSizeSelector": False},
            style={"width": "100%", "height": "480px"}))],
            title="Chi tiết theo nhân sự",
            desc="Bấm tiêu đề cột để sắp xếp, gõ vào ô lọc dưới tiêu đề để tìm nhanh"),
    ])


def _fig(fig, height=320):
    fig.update_layout(height=height, autosize=True, margin=dict(l=8, r=8, t=10, b=8),
                      font=dict(family="Inter, Segoe UI, sans-serif", size=12, color="#1B2733"),
                      plot_bgcolor="white", paper_bgcolor="white",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
    fig.update_xaxes(showgrid=False, linecolor="#E3E8EF")
    fig.update_yaxes(gridcolor="#F1F5F9", zeroline=False)
    return fig


def register(app):
    gan_dieu_huong_ky(app, "hr-thang")

    @app.callback(Output("hr-kpi", "children"), Output("hr-grid", "columnDefs"),
                  Output("hr-grid", "rowData"), Output("hr-bar-nhom", "figure"),
                  Output("hr-scatter", "figure"), Output("hr-nguon-hr", "children"),
                  Output("hr-rampup", "figure"), Output("hr-leadtime", "figure"),
                  Output("hr-canhbao", "columnDefs"), Output("hr-canhbao", "rowData"),
                  Output("hr-canhbao-tomtat", "children"), Output("hr-tom-tat", "children"),
                  Input("hr-thang", "value"), Input("hr-nhom", "value"), Input("hr-loc", "value"),
                  Input("hr-cn", "value"), Input("hr-xep", "value"))
    def _cap_nhat(thang, nhom, loc, chi_nhanh, xep_hang):
        scope = loc_chi_nhanh(current_user.phong_duoc_xem(), chi_nhanh, thang)
        df = hieu_suat_nhan_su(thang, chi_phong=scope)
        hr_thang = df.hr_thang.iloc[0] if len(df) and df.hr_thang.notna().any() else None

        if nhom:
            df = df[df.nhom_tham_nien.isin(nhom)]
        if loc == "zero":
            df = df[(df.online == 0) & (df.trang_thai.fillna("") != "Nghỉ việc")]
        elif loc == "notok":
            df = df[df.ket_luan == "NOT OK"]

        dang_lam = df[df.trang_thai.fillna("Bình thường") != "Nghỉ việc"]
        so_nv = len(dang_lam)
        tong_online = int(df.online.sum())
        zero = int((dang_lam.online == 0).sum())
        notok = int((df.ket_luan == "NOT OK").sum())
        kpis = [
            kpi("Nhân sự", f"{so_nv}", "Đang làm việc trong phạm vi xem"),
            kpi("Tổng số bán", f"{tong_online:,}".replace(",", "."),
                f"Bình quân {tong_online / so_nv:.1f} số/người" if so_nv else ""),
            kpi("Chưa có số trong kỳ", f"{zero}",
                f"Chiếm {zero / so_nv * 100:.0f}% quân số" if so_nv else "",
                "bad" if zero else "ok"),
            kpi("NSLĐ chưa đạt", f"{notok}",
                f"Theo kỳ NSLĐ {hr_thang[5:7]}/{hr_thang[:4]}" if hr_thang
                else "Chưa có dữ liệu NSLĐ", "warn" if notok else "ok"),
        ]

        cols = [
            {"field": "acc", "headerName": "Acc", "minWidth": 140, "flex": 1.3,
             "pinned": "left"},
            {"field": "ho_ten", "headerName": "Họ tên", "minWidth": 150, "flex": 1.5,
             "pinned": "left"},
            {"field": "phong", "headerName": "Phòng", "minWidth": 120, "flex": 1.2},
            {"field": "chi_nhanh", "headerName": "Chi nhánh", "minWidth": 100, "flex": 1},
            {"field": "vi_tri", "headerName": "Vị trí", "minWidth": 80, "flex": .8},
            {"field": "tham_nien_bucket", "headerName": "Thâm niên", "minWidth": 100,
             "flex": 1},
            {"field": "nhom_tham_nien", "headerName": "Nhóm", "minWidth": 100, "flex": 1,
             "valueFormatter": {"function": "params.value ? params.value : ''"}},
            {"field": "online", "headerName": "Số bán", "minWidth": 90, "flex": .9,
             "type": "numericColumn"},
            {"field": "vvip", "headerName": "V.VIP", "minWidth": 85, "flex": .8,
             "type": "numericColumn"},
            {"field": "ty_le_vvip", "headerName": "% V.VIP", "minWidth": 90, "flex": .9,
             "type": "numericColumn"},
            {"field": "camera", "headerName": "Camera", "minWidth": 90, "flex": .9,
             "type": "numericColumn"},
            {"field": "so_ngay_co_so", "headerName": "Số ngày có số", "minWidth": 100,
             "flex": 1, "type": "numericColumn"},
            {"field": "diem_tong", "headerName": "Điểm NSLĐ", "minWidth": 95, "flex": .9,
             "type": "numericColumn"},
            {"field": "ket_luan", "headerName": "Đánh giá", "minWidth": 100, "flex": 1},
            {"field": "trang_thai", "headerName": "Tình trạng", "minWidth": 110, "flex": 1},
        ]

        g = tong_hop_tham_nien(df)
        bar = go.Figure()
        if not g.empty:
            bar.add_trace(go.Bar(x=[NHOM_TEN.get(c, c) for c in g.nhom_tham_nien], y=g.tb_online,
                                 marker_color=[MAU_NHOM.get(c, "#0072BC") for c in g.nhom_tham_nien],
                                 text=[f"{v:.1f}" for v in g.tb_online], textposition="auto",
                                 customdata=g.so_nv,
                                 hovertemplate="%{x}<br>TB %{y:.1f} số/người<br>%{customdata} nhân sự<extra></extra>"))
        bar.update_layout(showlegend=False)

        # bảng xếp hạng: đọc được ngay tên người, không phải rê chuột từng chấm
        dang_lam = df[df.trang_thai.fillna("Bình thường") != "Nghỉ việc"]
        top = (dang_lam.sort_values("online", ascending=(xep_hang == "thap")).head(15)
               .sort_values("online"))
        sc = go.Figure()
        if not top.empty:
            nhan = [f"{(r.ho_ten if isinstance(r.ho_ten, str) else r.acc)}" for r in
                    top.itertuples()]
            sc.add_trace(go.Bar(
                x=top.online, y=nhan, orientation="h",
                marker_color=[MAU_NHOM.get(c, "#94A3B8") for c in top.nhom_tham_nien],
                text=top.online, textposition="auto",
                customdata=list(zip(top.phong, top.vvip, top.acc)),
                hovertemplate="%{y}<br>%{customdata[2]} · %{customdata[0]}"
                              "<br>Số bán %{x} · V.VIP %{customdata[1]}<extra></extra>"))
        sc.update_xaxes(title="Số bán trong kỳ")
        sc.update_layout(showlegend=False)

        nguon = html.Span(f"Hồ sơ NSLĐ kỳ {hr_thang}" if hr_thang else "Chưa có dữ liệu NSLĐ",
                          className="badge muted")

        # đường cong lên tay nghề
        rc = duong_cong_nang_suat(thang, chi_phong=scope)
        ru = go.Figure()
        if not rc.empty:
            ru.add_trace(go.Scatter(x=rc.tham_nien_thang, y=rc.tb_online, mode="lines+markers",
                                    name="TB số/người", line=dict(color="#0072BC", width=2.5),
                                    marker=dict(size=7), customdata=rc.so_nv,
                                    hovertemplate="Thâm niên %{x} tháng<br>TB %{y} số<br>"
                                                  "%{customdata} nhân sự<extra></extra>"))
            if rc.muc_chuan.notna().any():
                muc = float(rc.muc_chuan.iloc[0])
                ru.add_hline(y=muc, line_dash="dot", line_color="#F37021",
                             annotation_text=f"Mức chuẩn nhóm 13+ tháng: {muc}",
                             annotation_position="top left")
        ru.update_xaxes(title="Số tháng thâm niên")
        ru.update_yaxes(title="Số Online trung bình")

        # thời gian triển khai
        lt = thoi_gian_trien_khai(thang)
        lf = go.Figure()
        if not lt.empty:
            lf.add_trace(go.Bar(x=lt.tb_ngay, y=lt.phong, orientation="h",
                                marker_color="#37A5E6", text=lt.tb_ngay, textposition="auto"))
        lf.update_xaxes(title="Ngày")
        lf.update_layout(showlegend=False)

        # cảnh báo
        cb = canh_bao_nhan_su(thang, chi_phong=scope)
        cb_cols = [
            {"field": "muc_rui_ro", "headerName": "Mức độ", "minWidth": 100, "flex": .9,
             "cellStyle": {"styleConditions": [
                 {"condition": "params.value == 'Cao'",
                  "style": {"backgroundColor": "#FBE3E1", "color": "#93241C",
                            "fontWeight": "700"}},
                 {"condition": "params.value == 'Trung bình'",
                  "style": {"backgroundColor": "#FDF3E3", "color": "#8A5709"}}]}},
            {"field": "acc", "headerName": "Acc", "minWidth": 140, "flex": 1.4},
            {"field": "ho_ten", "headerName": "Họ tên", "minWidth": 150, "flex": 1.6},
            {"field": "phong", "headerName": "Phòng", "minWidth": 120, "flex": 1.2},
            {"field": "nhom_tham_nien", "headerName": "Nhóm thâm niên", "minWidth": 110,
             "flex": 1},
            {"field": "so_ngay_khong_so", "headerName": "Số ngày chưa có số",
             "minWidth": 120, "flex": 1.1, "type": "numericColumn"},
            {"field": "tuan_truoc", "headerName": "Tuần trước", "minWidth": 100, "flex": 1,
             "type": "numericColumn"},
            {"field": "tuan_nay", "headerName": "Tuần này", "minWidth": 100, "flex": 1,
             "type": "numericColumn"},
            {"field": "online", "headerName": "Cả tháng", "minWidth": 90, "flex": .9,
             "type": "numericColumn"},
            {"field": "ket_luan", "headerName": "NSLĐ kỳ trước", "minWidth": 115, "flex": 1.1},
        ]
        cao = int((cb.muc_rui_ro == "Cao").sum()) if not cb.empty else 0
        ten_cn_cb = {"DNG": "Đà Nẵng", "QNM": "Quảng Nam"}.get(chi_nhanh, "cả hai chi nhánh")
        tom_tat = html.Div([
            html.Span(f"{cao} cần xử lý ngay", className="badge bad" if cao else "badge ok"),
            html.Span(f"{len(cb) - cao} cần theo dõi", className="badge warn",
                      style={"marginLeft": "8px"}),
            html.Span(f"Phạm vi: {ten_cn_cb}", className="badge muted",
                      style={"marginLeft": "8px"}),
        ], style={"marginBottom": "12px"})

        ten_cn = {"DNG": "Đà Nẵng", "QNM": "Quảng Nam"}.get(chi_nhanh, "cả hai chi nhánh")
        tom_tat_bang = f"{len(df)} nhân sự · phạm vi {ten_cn}" + (
            f" · nhóm {', '.join(NHOM_TEN.get(n, n) for n in nhom)}" if nhom else "")

        return (kpis, cols, df.to_dict("records"), _fig(bar), _fig(sc, 430), nguon,
                _fig(ru, 330), _fig(lf, max(300, 24 * len(lt) + 80)), cb_cols,
                [] if cb.empty else cb.to_dict("records"), tom_tat, tom_tat_bang)

    @app.callback(Output("hr-grid", "exportDataAsCsv"), Input("hr-export", "n_clicks"),
                  prevent_initial_call=True)
    def _xuat_csv(n):
        return bool(n)
