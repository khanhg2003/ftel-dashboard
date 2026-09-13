"""Trang Phân tích bán hàng - trả lời "bán TỐT không" và "đang tắc ở đâu", bổ sung cho Báo cáo Tổng.

Bố cục theo câu hỏi người xem đặt ra trong giao ban:
1. Sáu chỉ số chất lượng, mỗi chỉ số so với cùng kỳ tháng trước.
2. Bảng theo phòng: phòng nào bán kèm kém, online chậm, tồn nhiều - màu so với mức chung chi nhánh.
3. Số tồn theo thời gian chờ + danh sách hợp đồng chờ lâu để đôn đốc.
4. Gói nào dễ bán kèm, khách online nhanh hay chậm, cơ cấu gói, nhịp theo thứ trong tuần.
5. Bảng theo nhân viên.
"""
from __future__ import annotations

import dash_ag_grid as dag
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, dcc, html
from flask_login import current_user

from app import phan_tich as pt
from app.config import rules_config
from app.metrics import cac_thang_co_du_lieu
from app.org import loc_chi_nhanh
from app.overview import TEN_DONG_TONG, TEN_PHAM_VI
from app.ui.components import card, chi_nhanh_control, chon_ky, field, gan_dieu_huong_ky, kpi, seg_control
from app.ui.icons import icon

MAU_TOT, MAU_VUA, MAU_KEM = ("#D3EBD4", "#14532D"), ("#FCEBB4", "#6B5104"), ("#F7BDBD", "#7F1D1D")
MAU_GOI = {"Giga": "#0072BC", "Sky": "#37A5E6", "Meta": "#F37021", "Khác": "#B9C5D3"}
MAU_TON = ["#D3EBD4", "#FCEBB4", "#FBD9AE", "#F7BDBD"]

SO = {"function": "params.value == null ? '' : Number(params.value).toLocaleString('vi-VN')"}
PCT = {"function": "params.value == null ? '–' : Math.round(params.value) + '%'"}
ROW_STYLE = {"styleConditions": [
    {"condition": "params.data.loai_dong == 'subtotal'",
     "style": {"backgroundColor": "#EDF3F9", "fontWeight": "700", "color": "#C8372D"}},
    {"condition": "params.data.loai_dong == 'total'",
     "style": {"backgroundColor": "#DCE8F4", "fontWeight": "700", "color": "#003057"}},
]}


def _nguong() -> dict:
    return {"tot": 5, "kem": 10,
            **(rules_config().get("phan_tich") or {})}


def topbar():
    return [html.Div([html.H1("Phân tích bán hàng"),
                      html.Div("Bán kèm, tốc độ online, số tồn và cơ cấu gói theo phòng",
                               className="sub")]),
            html.Div(className="spacer"),
            html.Div(id="pt-badge")]


def _grid(gid: str, cao: int | None = None, **kw):
    opts = {"suppressCellFocus": True, "domLayout": "autoHeight" if cao is None else "normal"}
    opts.update(kw.pop("dashGridOptions", {}))
    return dag.AgGrid(id=gid, className="ag-theme-quartz ag-theme-ftel", columnDefs=[],
                      rowData=[], dashGridOptions=opts,
                      defaultColDef={"resizable": True, "sortable": True, "suppressMovable": True,
                                     "wrapHeaderText": True, "autoHeaderHeight": True},
                      style={"width": "100%", **({"height": f"{cao}px"} if cao else {})}, **kw)


def _graph(gid: str):
    return dcc.Loading(dcc.Graph(id=gid, config={"displayModeBar": False, "responsive": True},
                                 style={"width": "100%"}))


def layout():
    thangs = cac_thang_co_du_lieu() or ["2026-09"]
    return html.Div([
        html.Div([
            field("Kỳ báo cáo", chon_ky("pt-thang", thangs)),
            html.Div(className="grow"),
            field("Chi nhánh", chi_nhanh_control("pt-cn")),
        ], className="toolbar loc-trang"),

        html.Div(id="pt-kpi", className="kpi-row kpi-6"),

        card([
            html.Div([html.Div(id="pt-mo-ta-phong", className="desc", style={"margin": 0}),
                      html.Div(className="grow"),
                      html.Button([icon("download", 14), html.Span("Xuất CSV")],
                                  id="pt-phong-csv", className="btn")],
                     className="toolbar", style={"marginBottom": "10px"}),
            dcc.Loading(_grid("pt-phong", getRowStyle=ROW_STYLE,
                              csvExportParams={"fileName": "PhanTich_TheoPhong.csv"})),
            html.Div(id="pt-chu-giai", className="desc", style={"margin": "10px 0 0"}),
        ], title="Chất lượng bán theo phòng"),

        card([
            html.Div([
                seg_control("pt-ton-xem", [("phong", "Theo phòng"), ("ds", "Hợp đồng chờ từ 7 ngày")],
                            "phong"),
                html.Div(className="grow"),
                html.Button([icon("download", 14), html.Span("Xuất CSV")], id="pt-ton-csv",
                            className="btn"),
            ], className="toolbar", style={"marginBottom": "10px"}),
            dcc.Loading(html.Div([
                html.Div(_grid("pt-ton-phong", getRowStyle=ROW_STYLE), id="pt-ton-phong-hop"),
                html.Div(_grid("pt-ton-ds", cao=420,
                               dashGridOptions={"pagination": True, "paginationPageSize": 12,
                                                "paginationPageSizeSelector": False},
                               csvExportParams={"fileName": "HopDong_ChoOnline.csv"}),
                         id="pt-ton-ds-hop", hidden=True),
            ])),
        ], title="Số tồn theo thời gian chờ",
            desc="Hợp đồng đã ký nhưng chưa online, còn nằm trong file mới nhất. "
                 "Tính số ngày từ ngày tạo hợp đồng đến ngày có số mới nhất."),

        html.Div([
            html.Div(card([_graph("pt-kem-goi")], title="Tỷ lệ bán kèm theo gói",
                          desc="Gói nào khách dễ lấy thêm V.VIP, Camera"), className="chart-col"),
            html.Div(card([_graph("pt-toc-do")], title="Tốc độ online",
                          desc="Số ngày từ lúc tạo hợp đồng đến khi online"),
                     className="chart-col"),
        ], className="chart-row"),

        html.Div([
            html.Div(card([_graph("pt-co-cau")], title="Cơ cấu gói theo phòng",
                          desc="Tỷ trọng Giga / Sky / Meta trong số online của từng phòng"),
                     className="chart-col"),
            html.Div(card([_graph("pt-nhip")], title="Nhịp online theo thứ trong tuần",
                          desc="Online bình quân mỗi thứ, tính trên 4 tuần gần nhất"),
                     className="chart-col"),
        ], className="chart-row"),

        card([
            html.Div([
                field("Chỉ hiện", dcc.Dropdown(
                    id="pt-nv-loc", clearable=False, value="all", style={"width": "260px"},
                    options=[{"label": "Tất cả nhân viên có số", "value": "all"},
                             {"label": "Chưa bán kèm V.VIP / Camera", "value": "khong_kem"},
                             {"label": "Có hợp đồng chờ từ 7 ngày", "value": "ton"}])),
                html.Div(className="grow"),
                field(" ", html.Button([icon("download", 14), html.Span("Xuất CSV")],
                                       id="pt-nv-csv", className="btn")),
            ], className="toolbar", style={"marginBottom": "10px"}),
            dcc.Loading(_grid("pt-nv", cao=480,
                              dashGridOptions={"pagination": True, "paginationPageSize": 12,
                                               "paginationPageSizeSelector": False},
                              csvExportParams={"fileName": "PhanTich_TheoNhanVien.csv"})),
        ], title="Chất lượng bán theo nhân viên",
            desc="Bấm tiêu đề cột để sắp xếp. Tỷ lệ tính trên số online của chính nhân viên đó."),
    ])


# ------------------------------------------------------------------ cột + màu
def _mau_so_voi_chung(chung: float | None, nguong: dict, cao_la_tot: bool = True) -> dict:
    """Tô màu một ô tỷ lệ so với mức chung của phạm vi đang xem (dòng tổng)."""
    if chung is None:
        return {}
    tot, kem = nguong["tot"], nguong["kem"]
    if cao_la_tot:
        dk_tot, dk_kem, dk_vua = (f"params.value >= {chung + tot}", f"params.value <= {chung - kem}",
                                  f"params.value < {chung - tot}")
    else:
        dk_tot, dk_kem, dk_vua = (f"params.value <= {chung - tot}", f"params.value >= {chung + kem}",
                                  f"params.value > {chung + tot}")
    goc = "params.data.loai_dong == 'data' && params.value != null && "
    return {"styleConditions": [
        {"condition": goc + dk_kem, "style": {"backgroundColor": MAU_KEM[0], "color": MAU_KEM[1],
                                               "fontWeight": "600"}},
        {"condition": goc + dk_vua, "style": {"backgroundColor": MAU_VUA[0], "color": MAU_VUA[1]}},
        {"condition": goc + dk_tot, "style": {"backgroundColor": MAU_TOT[0], "color": MAU_TOT[1],
                                               "fontWeight": "600"}},
    ]}


def _mau_ton(gia_tri: pd.Series) -> dict:
    """Số hợp đồng chờ lâu phụ thuộc quy mô phòng nên không đặt ngưỡng cứng: tô theo thứ hạng
    trong chính bảng đang xem - nhóm 1/4 phòng tồn nhiều nhất màu đỏ, nhóm trên trung vị màu vàng."""
    v = gia_tri[gia_tri > 0]
    if v.empty:
        return {}
    do, vang = float(v.quantile(.75)), float(v.median())
    goc = "params.data.loai_dong == 'data' && params.value > 0 && "
    return {"styleConditions": [
        {"condition": goc + f"params.value >= {do}",
         "style": {"backgroundColor": MAU_KEM[0], "color": MAU_KEM[1], "fontWeight": "700"}},
        {"condition": goc + f"params.value >= {vang}",
         "style": {"backgroundColor": MAU_VUA[0], "color": MAU_VUA[1]}},
    ]}


def _cot_phong(tong: dict, nguong: dict, ton_qua_7: pd.Series) -> list:
    def ty_le(field_, ten, tip, cao_la_tot=True):
        return {"field": field_, "headerName": ten, "headerTooltip": tip, "minWidth": 96, "flex": 1,
                "type": "numericColumn", "valueFormatter": PCT,
                "cellStyle": _mau_so_voi_chung(tong.get(field_), nguong, cao_la_tot)}

    return [
        {"field": "phong", "headerName": "Phòng", "pinned": "left", "minWidth": 160, "flex": 1.6},
        {"field": "online", "headerName": "Online", "minWidth": 80, "flex": .8,
         "type": "numericColumn", "valueFormatter": SO},
        {"headerName": "BÁN KÈM", "children": [
            ty_le("kem_vvip", "V.VIP", "Hợp đồng online có kèm V.VIP / tổng online"),
            ty_le("kem_camera", "Camera", "Hợp đồng online có kèm Camera / tổng online"),
            ty_le("du_3", "Đủ 3 DV", "Có cả Internet, V.VIP và Camera"),
        ]},
        {"headerName": "CHẤT LƯỢNG", "children": [
            ty_le("tra_truoc", "Trả trước", "Hợp đồng có trả trước (3, 6 hoặc 12 tháng)"),
            ty_le("onl_1_ngay", "Online trong 1 ngày",
                  "Online ngay trong ngày ký hoặc ngày hôm sau"),
            ty_le("ngoai_tinh", "Ngoại tỉnh",
                  "Khách thuộc tỉnh khác (CN Quản lý ngoài DNG/QNM), số tính cho tỉnh khác",
                  cao_la_tot=False),
        ]},
        {"headerName": "SỐ TỒN", "children": [
            {"field": "ton", "headerName": "Chưa online", "minWidth": 90, "flex": .9,
             "type": "numericColumn", "valueFormatter": SO},
            {"field": "ton_qua_7", "headerName": "Chờ từ 7 ngày", "minWidth": 96, "flex": .9,
             "type": "numericColumn", "valueFormatter": SO, "cellStyle": _mau_ton(ton_qua_7)},
        ]},
    ]


def _cot_ton() -> list:
    cols = [{"field": "phong", "headerName": "Phòng", "pinned": "left", "minWidth": 160,
             "flex": 1.6},
            {"field": "tong", "headerName": "Tổng tồn", "minWidth": 90, "flex": .9,
             "type": "numericColumn", "valueFormatter": SO}]
    for i, (_, _, nhan) in enumerate(pt.MOC_TON):
        cols.append({"field": f"m{i}", "headerName": nhan, "minWidth": 90, "flex": .9,
                     "type": "numericColumn", "valueFormatter": SO,
                     "cellStyle": {"styleConditions": [
                         {"condition": "params.data.loai_dong == 'data' && params.value > 0",
                          "style": {"backgroundColor": pt_mau(i)}}]}})
    cols.append({"field": "tb_ngay", "headerName": "Chờ bình quân (ngày)", "minWidth": 110,
                 "flex": 1, "type": "numericColumn"})
    return cols


def pt_mau(i: int) -> str:
    return MAU_TON[min(i, len(MAU_TON) - 1)]


COT_DS_TON = [
    {"field": "hop_dong", "headerName": "Hợp đồng", "minWidth": 120, "flex": 1},
    {"field": "acc_nhan_vien", "headerName": "Acc nhân viên", "minWidth": 150, "flex": 1.3},
    {"field": "phong", "headerName": "Phòng", "minWidth": 130, "flex": 1.1},
    {"field": "goi_dich_vu", "headerName": "Gói", "minWidth": 90, "flex": .8},
    {"field": "nguon_ban", "headerName": "Nguồn bán", "minWidth": 100, "flex": .8},
    {"field": "ngay_tao", "headerName": "Ngày tạo HĐ", "minWidth": 110, "flex": .9},
    {"field": "so_ngay_cho", "headerName": "Số ngày chờ", "minWidth": 100, "flex": .8,
     "type": "numericColumn", "sort": "desc"},
]


def _cot_nv(nguong: dict) -> list:
    pct = {"type": "numericColumn", "valueFormatter": PCT, "minWidth": 90, "flex": .8}
    return [
        {"field": "acc", "headerName": "Acc", "pinned": "left", "minWidth": 140, "flex": 1.3},
        {"field": "ho_ten", "headerName": "Họ tên", "minWidth": 150, "flex": 1.4},
        {"field": "phong", "headerName": "Phòng", "minWidth": 120, "flex": 1.1},
        {"field": "online", "headerName": "Online", "minWidth": 80, "flex": .7,
         "type": "numericColumn", "sort": "desc"},
        {"field": "kem_vvip", "headerName": "Kèm V.VIP", **pct},
        {"field": "kem_camera", "headerName": "Kèm Camera", **pct},
        {"field": "du_3_tl", "headerName": "Đủ 3 DV", **pct},
        {"field": "tra_truoc_tl", "headerName": "Trả trước", **pct},
        {"field": "onl_1_ngay", "headerName": "Online trong 1 ngày", **pct},
        {"field": "ton", "headerName": "Chưa online", "minWidth": 90, "flex": .8,
         "type": "numericColumn"},
        {"field": "ton_qua_7", "headerName": "Chờ từ 7 ngày", "minWidth": 96, "flex": .8,
         "type": "numericColumn", "cellStyle": {"styleConditions": [
             {"condition": "params.value >= 3",
              "style": {"backgroundColor": MAU_KEM[0], "color": MAU_KEM[1],
                        "fontWeight": "600"}}]}},
    ]


# ------------------------------------------------------------------ biểu đồ
def _fig(fig: go.Figure, height: int = 320) -> go.Figure:
    fig.update_layout(height=height, autosize=True, margin=dict(l=8, r=8, t=10, b=8),
                      font=dict(family="Inter, Segoe UI, sans-serif", size=12, color="#1B2733"),
                      plot_bgcolor="white", paper_bgcolor="white",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
    fig.update_xaxes(showgrid=False, linecolor="#E4E9F0")
    fig.update_yaxes(gridcolor="#F1F5F9", zeroline=False)
    return fig


def _bd_kem_goi(g: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if not g.empty:
        nhan = [f"{r.nhom_goi} ({r.so_hd:,})".replace(",", ".") for r in g.itertuples()]
        for cot, ten, mau in (("vvip", "Kèm V.VIP", "#0072BC"), ("camera", "Kèm Camera", "#F37021"),
                              ("du_3", "Đủ 3 DV", "#00A650")):
            fig.add_trace(go.Bar(x=nhan, y=g[cot], name=ten, marker_color=mau,
                                 text=[f"{v:.0f}%" for v in g[cot]], textposition="outside",
                                 cliponaxis=False,
                                 hovertemplate="%{x}<br>" + ten + ": %{y:.1f}%<extra></extra>"))
    fig.update_yaxes(ticksuffix="%", range=[0, 112])        # chừa chỗ cho nhãn trên đầu cột
    fig.update_layout(barmode="group", bargap=.25)
    return _fig(fig)


def _bd_toc_do(g: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if not g.empty:
        mau = ["#00A650", "#5CBF7A", "#F5B942", "#F39C4A", "#E8743B", "#C8372D"]
        fig.add_trace(go.Bar(x=g.moc, y=g.so_hd, marker_color=mau[:len(g)],
                             text=[f"{v:.0f}%" if v is not None else "" for v in g.ty_le],
                             textposition="outside", cliponaxis=False,
                             hovertemplate="%{x}: %{y} hợp đồng<extra></extra>"))
    fig.update_layout(showlegend=False)
    fig.update_yaxes(title="Số hợp đồng", range=[0, (g.so_hd.max() or 1) * 1.18] if len(g) else None)
    return _fig(fig)


def _bd_co_cau(g: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if not g.empty:
        for goi in pt.NHOM_GOI + ("Khác",):
            fig.add_trace(go.Bar(y=g.phong, x=g[goi], name=goi, orientation="h",
                                 marker_color=MAU_GOI[goi],
                                 text=[f"{v:.0f}%" if v >= 8 else "" for v in g[goi]],
                                 textposition="inside", insidetextanchor="middle",
                                 hovertemplate="%{y}<br>" + goi + ": %{x:.1f}%<extra></extra>"))
    fig.update_layout(barmode="stack", bargap=.3, legend_traceorder="normal")
    fig.update_xaxes(ticksuffix="%", range=[0, 100])
    return _fig(fig, max(320, 24 * len(g) + 80))


def _bd_nhip(g: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if not g.empty:
        tb = g.tb_online.mean()
        fig.add_trace(go.Bar(x=g.thu, y=g.tb_online, text=g.tb_online, textposition="outside",
                             cliponaxis=False,
                             marker_color=["#C8372D" if v < tb * 0.8 else "#0072BC"
                                           for v in g.tb_online],
                             hovertemplate="%{x}: bình quân %{y} online<extra></extra>"))
        fig.add_hline(y=tb, line_dash="dot", line_color="#94A3B8",
                      annotation_text=f"Bình quân {tb:.0f}", annotation_position="top left")
    fig.update_layout(showlegend=False)
    if not g.empty:
        fig.update_yaxes(range=[0, (g.tb_online.max() or 1) * 1.18])
    return _fig(fig)


# ------------------------------------------------------------------ kpi
def _kpis(nay: dict, truoc: dict, ton: pd.DataFrame, ten_truoc: str) -> list:
    def the(ten, khoa, goi_y, cao_la_tot=True):
        v, c = nay.get(khoa), truoc.get(khoa)
        gia_tri = "–" if v is None else f"{v:.0f}%"
        if v is None or c is None:
            return kpi(ten, gia_tri, goi_y)
        chenh = v - c
        tot = chenh >= 0 if cao_la_tot else chenh <= 0
        return kpi(ten, gia_tri, html.Span([
            html.Span(f"{chenh:+.0f} điểm", className=f"delta {'up' if tot else 'down'}"),
            f" so với {ten_truoc} ({c:.0f}%)"]))

    qua_7 = int((ton.so_ngay_cho >= 7).sum()) if len(ton) else 0
    return [
        the("Kèm V.VIP", "kem_vvip", "Trên số online trong kỳ"),
        the("Kèm Camera", "kem_camera", "Trên số online trong kỳ"),
        the("Đủ 3 dịch vụ", "du_3", "Internet + V.VIP + Camera"),
        the("Online trong 1 ngày", "onl_1_ngay", "Trong ngày ký hoặc hôm sau"),
        the("Trả trước", "tra_truoc", "Có trả trước 3, 6 hoặc 12 tháng"),
        kpi("Chờ online từ 7 ngày", f"{qua_7:,}".replace(",", "."),
            f"Trên tổng {len(ton):,} hợp đồng chưa online".replace(",", "."),
            "bad" if qua_7 else "ok"),
    ]


# ------------------------------------------------------------------ callback
def register(app):
    gan_dieu_huong_ky(app, "pt-thang")

    for nut, bang in (("pt-phong-csv", "pt-phong"), ("pt-ton-csv", "pt-ton-ds"),
                      ("pt-nv-csv", "pt-nv")):
        app.callback(Output(bang, "exportDataAsCsv"), Input(nut, "n_clicks"),
                     prevent_initial_call=True)(lambda n: bool(n))

    @app.callback(Output("pt-ton-phong-hop", "hidden"), Output("pt-ton-ds-hop", "hidden"),
                  Output("pt-ton-csv", "style"), Input("pt-ton-xem", "value"))
    def _doi_xem_ton(xem):
        ds = xem == "ds"
        return ds, not ds, {} if ds else {"display": "none"}

    @app.callback(
        Output("pt-kpi", "children"), Output("pt-badge", "children"),
        Output("pt-mo-ta-phong", "children"), Output("pt-chu-giai", "children"),
        Output("pt-phong", "columnDefs"), Output("pt-phong", "rowData"),
        Output("pt-ton-phong", "columnDefs"), Output("pt-ton-phong", "rowData"),
        Output("pt-ton-ds", "columnDefs"), Output("pt-ton-ds", "rowData"),
        Output("pt-kem-goi", "figure"), Output("pt-toc-do", "figure"),
        Output("pt-co-cau", "figure"), Output("pt-nhip", "figure"),
        Output("pt-nv", "columnDefs"), Output("pt-nv", "rowData"),
        Input("pt-thang", "value"), Input("pt-cn", "value"), Input("pt-nv-loc", "value"))
    def _cap_nhat(thang, chi_nhanh, loc_nv):
        nguong = _nguong()
        scope = loc_chi_nhanh(current_user.phong_duoc_xem(), chi_nhanh, thang)
        tu, den, ngay = pt.ky_phan_tich(thang)
        df = pt.hop_dong_online(tu, den, scope)
        tu_t, den_t = pt.cung_ky_thang_truoc(thang, ngay)
        truoc = pt.chi_so_chung(pt.hop_dong_online(tu_t, den_t, scope))
        ton = pt.hop_dong_ton(scope)
        nay = pt.chi_so_chung(df)

        thang_truoc = f"T{int(tu_t[5:7])}"
        kpis = _kpis(nay, truoc, ton, f"cùng kỳ {thang_truoc}")
        pham_vi = TEN_PHAM_VI.get(chi_nhanh, TEN_PHAM_VI["all"])
        badge = html.Span(f"01 - {ngay:02d}/{thang[5:7]}/{thang[:4]} · {pham_vi}",
                          className="badge muted")

        bang = pt.bang_theo_phong(df, ton, thang, TEN_DONG_TONG.get(chi_nhanh, TEN_DONG_TONG["all"]))
        tong = bang[bang.loai_dong == "total"].iloc[0].to_dict()
        mo_ta = (f"{nay['online']:,} hợp đồng online từ 01 đến {ngay:02d}/{thang[5:7]} · "
                 f"{pham_vi}").replace(",", ".")
        chu_giai = html.Span([
            html.Span("■ ", style={"color": "#5CBF7A"}), f"Cao hơn mức chung từ {nguong['tot']} điểm   ",
            html.Span("■ ", style={"color": "#F5B942"}), f"Thấp hơn {nguong['tot']}-{nguong['kem']} điểm   ",
            html.Span("■ ", style={"color": "#E57373"}), f"Thấp hơn từ {nguong['kem']} điểm. ",
            "Mức chung là dòng tổng của phạm vi đang xem. Cột Ngoại tỉnh tô ngược lại (càng cao "
            "càng cần chú ý). Cột Chờ từ 7 ngày: đỏ là nhóm 1/4 phòng tồn lâu nhiều nhất."])

        ton_phong = pt.ton_theo_tuoi(ton, thang)
        meta_ten = dict(zip(ton_phong.phong_code, ton_phong.phong)) if len(ton_phong) else {}
        ds = ton[ton.so_ngay_cho >= 7].copy()
        ds["phong"] = [meta_ten.get(c, "Chưa gán phòng") for c in ds.phong_code]
        ds["ngay_tao"] = ds.ngay_tao_hd.dt.strftime("%d/%m/%Y")
        ds = ds.sort_values("so_ngay_cho", ascending=False)

        nv = pt.theo_nhan_vien(df, ton, thang)
        if not nv.empty and loc_nv == "khong_kem":
            nv = nv[(nv.vvip == 0) | (nv.camera == 0)]
        elif not nv.empty and loc_nv == "ton":
            nv = nv[nv.ton_qua_7 > 0].sort_values("ton_qua_7", ascending=False)

        tu_4t = (pd.Timestamp(den) - pd.Timedelta(days=27)).date().isoformat()
        nhip = pt.nhip_theo_thu(pt.hop_dong_online(tu_4t, den, scope), tu_4t, den)

        return (kpis, badge, mo_ta, chu_giai,
                _cot_phong(tong, nguong, bang[bang.loai_dong == "data"].ton_qua_7), bang.to_dict("records"),
                _cot_ton(), ton_phong.to_dict("records") if len(ton_phong) else [],
                COT_DS_TON, ds[["hop_dong", "acc_nhan_vien", "phong", "goi_dich_vu", "nguon_ban",
                                "ngay_tao", "so_ngay_cho"]].to_dict("records"),
                _bd_kem_goi(pt.kem_theo_goi(df)), _bd_toc_do(pt.toc_do_online(df)),
                _bd_co_cau(pt.co_cau_goi_theo_phong(df, thang)), _bd_nhip(nhip),
                _cot_nv(nguong), [] if nv.empty else nv.to_dict("records"))
