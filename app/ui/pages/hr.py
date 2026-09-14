"""Trang Nhân sự & NSLĐ - năng suất theo người và theo phòng, đối chiếu thâm niên và NSLĐ.

Thanh lọc chung: Ngày (luỹ kế tháng như Báo cáo Tổng) · Chi nhánh · Phòng.
Hai tab tách theo nguồn số để không lẫn kỳ:
1. Bán hàng trong kỳ (số online hằng ngày): 5 chỉ số → Cần trao đổi sớm (có lý do) →
   năng suất theo thâm niên + xếp hạng → bảng chi tiết (tìm, lọc, Excel).
2. Năng suất lao động (file NSLĐ hằng tháng): 5 chỉ số → NSLĐ ITN theo tháng → NSLĐ tân binh
   theo tháng làm việc. Mỗi bảng xem theo phòng hoặc từng nhân sự của phòng đang chọn.

Quyền: Quản trị xem mọi phòng, Trưởng phòng chỉ phòng mình phụ trách, Nhập liệu không vào được.
"""
from __future__ import annotations

from datetime import date

import dash_ag_grid as dag
import plotly.graph_objects as go
from dash import Input, Output, Patch, State, dcc, html, no_update
from flask_login import current_user

from app import canh_bao, nsld
from app.auth import ghi_log
from app.export_phan_tich import xuat_phan_tich
from app.hr_metrics import (LOAI_KINH_DOANH, MOC_THAM_NIEN, TEN_NHOM,
                            canh_bao_nhan_su, hieu_suat_nhan_su, tong_hop_tham_nien)
from app.metrics import cac_ngay_co_du_lieu
from app.org import phong_order
from app.ui.components import (LOCALE_VI, alert, chi_nhanh_control, chon_ngay, chu_giai, field,
                               gan_chon_ngay, kpi, seg_control)
from app.ui.icons import icon

MAU_NHOM = {"MOI": "#F37021", "DANG_LEN": "#37A5E6", "ON_DINH": "#0072BC", "LAU_NAM": "#00A650"}
SO = {"function": "params.value == null ? '' : Number(params.value).toLocaleString('vi-VN')"}
PCT = {"function": "params.value == null ? '–' : Math.round(params.value) + '%'"}
CHENH = {"function": "params.value == null ? '–' : (params.value > 0 ? '+' : '') + Math.round(params.value) + '%'"}
MAU_CHENH = {"styleConditions": [
    {"condition": "params.value != null && params.value <= -50",
     "style": {"backgroundColor": "#FBE3E1", "color": "#93241C", "fontWeight": "600"}},
    {"condition": "params.value != null && params.value >= 50",
     "style": {"backgroundColor": "#DCF5E6", "color": "#0A5B31", "fontWeight": "600"}}]}
MAU_NSLD = {"styleConditions": [
    {"condition": "params.value == 'Chưa đạt'", "style": {"color": "#B42318", "fontWeight": "650"}},
    {"condition": "params.value == 'Đạt'", "style": {"color": "#0A7A3E"}}]}
MAU_KHONG = {"styleConditions": [
    {"condition": "params.value === 0", "style": {"color": "#B42318", "fontWeight": "700"}}]}

DINH_NGHIA = [
    ("Online", "Hợp đồng Internet online từ ngày 01 đến ngày chọn, theo acc người bán. Acc ngoài danh "
               "mục (KT, CUS, ECOM) lấy phòng có nhiều số nhất; người bán cho nhiều phòng nên tổng theo "
               "người có thể lệch vài số với Báo cáo Tổng (tính theo hợp đồng)."),
    ("Nhân sự kinh doanh", "Người đang làm ở phòng IBB và phòng địa bàn, theo danh mục acc → phòng. "
                           "Không tính người đã nghỉ, và acc 60 ngày không có số mà không có trong NSLĐ "
                           "(trưởng phòng, acc cũ)."),
    ("Thâm niên · NSLĐ", "Lấy từ file NSLĐ gần nhất (thường là tháng trước). Người chưa có trong "
                         "NSLĐ để trống."),
    ("So với cùng thâm niên", "Online của người đó so với trung vị những người cùng mốc thâm niên "
                              "ở phòng kinh doanh. +50% là bán hơn một nửa so với người cùng mốc."),
    ("VVIP/PTTB", "Số V.VIP online chia số online, cùng cách tính với Báo cáo Tổng."),
    ("Trao đổi ngay", canh_bao.MO_TA_TRAO_DOI_NGAY + " Cùng quy tắc với Báo cáo phòng."),
    ("Theo dõi", canh_bao.MO_TA_THEO_DOI),
]


def topbar():
    return [html.Div([html.H1("Nhân sự & NSLĐ"),
                      html.Div("Năng suất từng người, theo thâm niên và NSLĐ", className="sub")]),
            html.Div(className="spacer"),
            html.Div(id="hr-nguon-hr")]


def _grid(id, cao=None, **kw):
    opts = {"suppressCellFocus": True, "localeText": LOCALE_VI, "tooltipShowDelay": 300,
            "includeHiddenColumnsInQuickFilter": True,
            "domLayout": "autoHeight" if cao is None else "normal"}
    opts.update(kw.pop("dashGridOptions", {}))
    style = {"width": "100%"} | ({"height": f"{cao}px"} if cao else {})
    return dag.AgGrid(id=id, className="ag-theme-quartz ag-theme-ftel", columnDefs=[], rowData=[],
                      defaultColDef={"resizable": True, "sortable": True, "suppressMovable": True,
                                     "wrapHeaderText": True, "autoHeaderHeight": True},
                      dashGridOptions=opts, style=style, **kw)


def khung_cuon(so_dong: int, co_dong_ghim: bool = False) -> dict:
    """Bảng không chia trang: cao vừa đủ số dòng, tối đa bằng khung hình (trừ thanh lọc + tiêu đề thẻ),
    dài hơn thì cuộn trong bảng - tiêu đề cột luôn thấy."""
    can = 34 * (so_dong + (1 if co_dong_ghim else 0)) + 64
    return {"width": "100%", "height": f"min({max(can, 140)}px, calc(100vh - 230px))",
            "minHeight": "140px"}


def _dau_the(tieu_de, mo_ta_id=None, mo_ta=None, nut=None):
    return html.Div([
        html.Div([html.H3(tieu_de),
                  html.Div(mo_ta, id=mo_ta_id, className="desc") if mo_ta_id
                  else html.Div(mo_ta, className="desc")], className="the-ten"),
        html.Div(nut or [], className="the-nut"),
    ], className="the-dau")


DINH_NGHIA_NSLD = [
    ("NSLĐ ITN của phòng", "Tổng điểm ITN của người được xét NSLĐ trong phòng / số người được xét "
                           "(NVKD + CTV, bỏ người “Không xét”). Cách tính của bảng Tình hình NSLĐ."),
    ("Total · TB", "Total = trung bình cộng các phòng trong tháng. TB = trung bình các tháng đã có file."),
    ("Phòng", "Theo cột Phòng (theo PS) trong file NSLĐ, đổi sang tên phòng trên app (DNGB1 = IBB1…)."),
    ("Tân binh", "Người có Ngày tính lương trong năm đang xem (vào làm từ 01/01), cả NVKD và CTV, "
                 "có trong ít nhất một file NSLĐ đã nạp."),
    ("Tháng thứ 1, 2, 3…", "Tháng làm việc thứ mấy của người đó: tháng vào làm là tháng thứ 1 (vào ngày "
                           "15 cũng tính tháng đó). Ô = ITN bình quân các tân binh ở tháng làm việc đó."),
    ("Đã nghỉ · Tỷ lệ out", "Đã nghỉ khi file gần nhất ghi Nghỉ việc, hoặc không còn trong file "
                            "NSLĐ tháng mới nhất. Tỷ lệ out = đã nghỉ / số tân binh."),
]
TAT_CA_KD, TAT_CA = "__kd", "__all"


def layout():
    ngays = cac_ngay_co_du_lieu()
    return html.Div([
        html.Div([
            field("Ngày báo cáo", chon_ngay("hr", ngays)),
            field("Chi nhánh", chi_nhanh_control("hr-cn")),
            field("Phòng", dcc.Dropdown(id="hr-phong", clearable=False, searchable=True,
                                        placeholder="Tất cả phòng kinh doanh",
                                        style={"width": "240px"})),
        ], className="toolbar loc-trang"),
        dcc.Download(id="hr-tai-xuong"),
        html.Div(seg_control("hr-tab", [("ban", "1 · Bán hàng trong kỳ"),
                                        ("nsld", "2 · Năng suất lao động (NSLĐ)")], "ban"),
                 className="tab-lon"),
        html.Div(style={"height": "14px"}),

        # ------------------------------------------------------ tab bán hàng
        html.Div(id="hr-pane-ban", children=[
            html.Div(id="hr-thong-bao"),
            dcc.Loading(html.Div(id="hr-kpi", className="kpi-row"), type="dot"),

            html.Div([
                _dau_the("Cần trao đổi sớm", "hr-cb-mo-ta"),
                html.Div(id="hr-cb-tom-tat"),
                _grid("hr-canhbao", cao=360),
            ], className="card"),

            html.Div([
                html.Div(html.Div([
                    _dau_the("Năng suất theo thâm niên", "hr-tn-mo-ta"),
                    dcc.Graph(id="hr-bar-nhom", config={"displayModeBar": False, "responsive": True},
                              style={"width": "100%", "height": "360px"}),
                ], className="card"), className="chart-col"),
                html.Div(html.Div([
                    _dau_the("Xếp hạng online", mo_ta="15 người đang làm, theo số online trong kỳ",
                             nut=seg_control("hr-xep", [("cao", "Cao nhất"), ("thap", "Thấp nhất")],
                                             "cao")),
                    _chu_mau(),
                    dcc.Graph(id="hr-scatter", config={"displayModeBar": False, "responsive": True},
                              style={"width": "100%", "height": "420px"}),
                ], className="card"), className="chart-col"),
            ], className="chart-row doi"),

            html.Div([
                _dau_the("Chi tiết theo nhân sự", "hr-tom-tat",
                         nut=html.Button([icon("download", 14), html.Span("Excel")], id="hr-export",
                                         className="btn", title="Tải đủ cột của các dòng đang lọc")),
                html.Div([
                    dcc.Input(id="hr-tim", type="search", placeholder="Tìm tên hoặc acc…",
                              className="o-tim", debounce=False),
                    dcc.Dropdown(id="hr-nhom", multi=True, placeholder="Mọi thâm niên",
                                 options=[{"label": v, "value": k} for k, v in TEN_NHOM.items()],
                                 style={"minWidth": "180px"}),
                    dcc.Dropdown(id="hr-loc", clearable=False, value="all", searchable=False,
                                 style={"width": "170px"},
                                 options=[{"label": "Mọi tình trạng", "value": "all"},
                                          {"label": "Chưa có số", "value": "zero"},
                                          {"label": "NSLĐ chưa đạt", "value": "notok"},
                                          {"label": "Chưa có NSLĐ", "value": "chua_nsld"}]),
                    html.Div(className="grow"),
                    seg_control("hr-xem", [("ban", "Bán hàng"), ("nsld", "Hồ sơ NSLĐ")], "ban"),
                ], className="the-thanh"),
                _grid("hr-grid", cao=520, getRowId="params.data.acc_norm",
                      dashGridOptions={"rowHeight": 34}),
                chu_giai("Cách tính", DINH_NGHIA),
            ], className="card"),
        ]),

        # ----------------------------------------------------------- tab NSLĐ
        html.Div(id="hr-pane-nsld", hidden=True, children=[
            html.Div(id="hr-ns-thong-bao"),
            dcc.Loading(html.Div(id="hr-ns-kpi", className="kpi-row"), type="dot"),
            html.Div([
                _dau_the("NSLĐ ITN theo tháng", "hr-ns-mo-ta", nut=[
                    seg_control("hr-ns-xem", [("phong", "Các phòng"), ("nhan_su", "Từng nhân sự")],
                                "phong"),
                    html.Button([icon("download", 14), html.Span("Excel")], id="hr-ns-export",
                                className="btn", title="Hai bảng NSLĐ, mỗi bảng một sheet"),
                ]),
                html.Div(id="hr-ns-chu"),
                _grid("hr-ns-grid", cao=300, getRowStyle=DONG_TONG, dashGridOptions={"rowHeight": 34}),
            ], className="card"),
            html.Div([
                _dau_the("NSLĐ tân binh theo tháng làm việc", "hr-tb-mo-ta", nut=[
                    seg_control("hr-tb-xem", [("phong", "Các phòng"), ("nhan_su", "Từng tân binh")],
                                "phong")]),
                html.Div(id="hr-tb-chu"),
                _grid("hr-tb-grid", cao=300, getRowStyle=DONG_TONG, dashGridOptions={"rowHeight": 34}),
                chu_giai("Cách tính", DINH_NGHIA_NSLD),
            ], className="card"),
        ]),
    ])


# ------------------------------------------------------------ chọn phòng
def _phong_trong_quyen(chi_nhanh: str | None) -> list[dict]:
    pham_vi = current_user.phong_nhan_su()
    ds = [p for p in phong_order() if not chi_nhanh or chi_nhanh == "all"
          or p.get("chi_nhanh") == chi_nhanh]
    if pham_vi is not None:
        ds = [p for p in ds if p["code"] in set(pham_vi)]
    return ds


def _phong_opts(chi_nhanh: str | None) -> list[dict]:
    ds = _phong_trong_quyen(chi_nhanh)
    kd = [p for p in ds if p["loai"] in LOAI_KINH_DOANH]
    khac = [p for p in ds if p["loai"] not in LOAI_KINH_DOANH]
    if current_user.phong_nhan_su() is not None and len(ds) <= 1:
        return [{"label": p["ten"], "value": p["code"]} for p in ds]
    dau = [{"label": "Tất cả phòng kinh doanh", "value": TAT_CA_KD}]
    if khac:
        dau.append({"label": "Tất cả phòng", "value": TAT_CA})
    return (dau + [{"label": p["ten"], "value": p["code"]} for p in kd]
            + [{"label": f"{p['ten']} (không phải KD)", "value": p["code"]} for p in khac])


def _phong_mac_dinh(chi_nhanh: str | None) -> str | None:
    opts = _phong_opts(chi_nhanh)
    return opts[0]["value"] if opts else None


def _ma_phong(chon: str | None, chi_nhanh: str | None) -> list[str]:
    """Giá trị ô Phòng -> danh sách mã phòng (đã giới hạn theo quyền)."""
    ds = _phong_trong_quyen(chi_nhanh)
    if chon == TAT_CA:
        return [p["code"] for p in ds]
    if chon in (None, TAT_CA_KD):
        return [p["code"] for p in ds if p["loai"] in LOAI_KINH_DOANH]
    return [p["code"] for p in ds if p["code"] == chon]


def _ten_pham_vi(chon: str | None) -> str:
    if chon == TAT_CA:
        return "tất cả phòng"
    if chon in (None, TAT_CA_KD):
        return "các phòng kinh doanh"
    return next((p["ten"] for p in phong_order() if p["code"] == chon), chon)


def _chu_mau():
    """Chú thích màu thâm niên dùng chung cho hai biểu đồ."""
    return html.Div([html.Span([html.I(style={"background": MAU_NHOM[k]}), TEN_NHOM[k]],
                               className="mau-chip") for k in MAU_NHOM]
                    + [html.Span([html.I(style={"background": "#94A3B8"}), "Chưa có NSLĐ"],
                                 className="mau-chip")], className="chu-mau")


# ------------------------------------------------------------------ cột bảng
def _cot_nhan_su(hien_acc: bool = True):
    return [
        {"field": "ho_ten", "headerName": "Nhân sự", "pinned": "left", "minWidth": 160, "flex": 1.4,
         "tooltipField": "acc", "cellStyle": {"fontWeight": "600"}},
        {"field": "acc", "headerName": "Acc", "minWidth": 124, "flex": .9, "hide": not hien_acc,
         "tooltipField": "acc"},
        {"field": "phong", "headerName": "Phòng", "minWidth": 104, "flex": .8},
    ]


def _cols(xem: str):
    so = {"type": "numericColumn", "valueFormatter": SO, "minWidth": 70, "flex": .6}
    if xem == "nsld":
        return _cot_nhan_su() + [
            {"field": "vi_tri", "headerName": "Vị trí", "minWidth": 64, "flex": .4},
            {"field": "tham_nien", "headerName": "Thâm niên", "minWidth": 96, "flex": .7},
            {"field": "nhom", "headerName": "Nhóm", "minWidth": 78, "flex": .5},
            {**so, "field": "online", "headerName": "Online", "minWidth": 64},
            {**so, "field": "diem_tong", "headerName": "Điểm NSLĐ", "minWidth": 80},
            {"field": "nsld", "headerName": "NSLĐ", "minWidth": 86, "flex": .6, "cellStyle": MAU_NSLD},
            {"field": "dieu_kien", "headerName": "Điều kiện", "minWidth": 84, "flex": .6},
            {"field": "trang_thai", "headerName": "Tình trạng", "minWidth": 100, "flex": .7},
        ]
    return _cot_nhan_su(hien_acc=False) + [
        {"field": "tham_nien", "headerName": "Thâm niên", "minWidth": 96, "flex": .6},
        {**so, "field": "online", "headerName": "Online", "cellStyle": MAU_KHONG},
        {"field": "so_voi_tham_nien", "headerName": "So với cùng thâm niên", "minWidth": 104,
         "flex": .7, "type": "numericColumn", "valueFormatter": CHENH, "cellStyle": MAU_CHENH,
         "headerTooltip": "So với trung vị những người cùng mốc thâm niên ở phòng kinh doanh"},
        {**so, "field": "so_ngay_co_so", "headerName": "Ngày có số", "minWidth": 80},
        {**so, "field": "ban_moi", "headerName": "Bán mới", "minWidth": 76,
         "headerTooltip": "Hợp đồng tạo trong kỳ (chưa chắc đã online)"},
        {**so, "field": "vvip", "headerName": "V.VIP", "minWidth": 64},
        {"field": "ty_le_vvip", "headerName": "VVIP/PTTB", "minWidth": 86, "flex": .6,
         "type": "numericColumn", "valueFormatter": PCT},
        {**so, "field": "camera", "headerName": "Camera", "minWidth": 72},
        {"field": "nsld", "headerName": "NSLĐ", "minWidth": 80, "flex": .5, "cellStyle": MAU_NSLD},
    ]


def _cols_canh_bao():
    return [
        {"field": "muc", "headerName": "Mức", "width": 118, "pinned": "left",
         "cellStyle": {"styleConditions": [
             {"condition": "params.value == 'Trao đổi ngay'",
              "style": {"backgroundColor": "#FBE3E1", "color": "#93241C", "fontWeight": "700"}},
             {"condition": "params.value == 'Theo dõi'",
              "style": {"backgroundColor": "#FDF3E3", "color": "#8A5709", "fontWeight": "600"}}]}},
        {"field": "ho_ten", "headerName": "Nhân sự", "minWidth": 160, "flex": 1.1,
         "tooltipField": "acc", "cellStyle": {"fontWeight": "600"}},
        {"field": "phong", "headerName": "Phòng", "minWidth": 100, "flex": .6},
        {"field": "tham_nien", "headerName": "Thâm niên", "minWidth": 96, "flex": .6},
        {"field": "ly_do", "headerName": "Lý do", "minWidth": 240, "flex": 2, "tooltipField": "ly_do"},
        {"field": "tuan_truoc", "headerName": "Tuần trước", "minWidth": 86, "flex": .5,
         "type": "numericColumn", "headerTooltip": "Online từ 13 đến 7 ngày trước ngày chọn"},
        {"field": "tuan_nay", "headerName": "Tuần này", "minWidth": 80, "flex": .5,
         "type": "numericColumn", "headerTooltip": "Online 7 ngày gần nhất tính đến ngày chọn"},
        {"field": "online", "headerName": "Online kỳ", "minWidth": 82, "flex": .5,
         "type": "numericColumn"},
    ]


# ------------------------------------------------------------------ biểu đồ
def _fig(fig, height=340):
    fig.update_layout(height=height, autosize=True, margin=dict(l=8, r=12, t=8, b=8),
                      font=dict(family="Inter, Segoe UI, sans-serif", size=12, color="#1B2733"),
                      plot_bgcolor="white", paper_bgcolor="white", showlegend=False)
    fig.update_xaxes(showgrid=False, linecolor="#E3E8EF")
    fig.update_yaxes(gridcolor="#F1F5F9", zeroline=False)
    return fig


def _trong(fig, chu: str):
    fig.add_annotation(text=chu, x=.5, y=.5, xref="paper", yref="paper", showarrow=False,
                       font=dict(size=13, color="#64748B"))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def _bieu_do_tham_nien(df):
    g = tong_hop_tham_nien(df)
    fig = go.Figure()
    if g.empty:
        return _fig(_trong(fig, "Chưa có hồ sơ NSLĐ để chia theo thâm niên"))
    nhan = [f"{m} th" if m in MOC_THAM_NIEN[:6] else f"{m}" for m in g.tham_nien_bucket]
    fig.add_trace(go.Bar(
        x=nhan, y=g.tb_online, marker_color=[MAU_NHOM.get(c, "#0072BC") for c in g.nhom_tham_nien],
        text=[f"{v:.1f}".replace(".", ",") for v in g.tb_online], textposition="outside", cliponaxis=False,
        customdata=list(zip(g.so_nv, g.trung_vi, g.chua_co_so)),
        hovertemplate="Thâm niên %{x}<br>Bình quân %{y:.1f} online/người<br>"
                      "%{customdata[0]} người · trung vị %{customdata[1]}<br>"
                      "%{customdata[2]} người chưa có số<extra></extra>"))
    # số người mỗi mốc ghi dưới trục để biết cột nào chỉ vài người
    fig.update_xaxes(tickvals=nhan, ticktext=[f"{n}<br><span style='font-size:11px;color:#64748B'>"
                                              f"{k} người</span>" for n, k in zip(nhan, g.so_nv)])
    moc = g[g.tham_nien_bucket == "13+"]
    if len(moc):
        fig.add_hline(y=float(moc.tb_online.iloc[0]), line_dash="dot", line_color="#F37021",
                      annotation_text="Mức nhóm 13+ tháng", annotation_position="bottom left",
                      annotation_font_color="#B45309")
    fig.update_yaxes(title=None, rangemode="tozero")
    return _fig(fig)


def _bieu_do_xep_hang(df, xep):
    fig = go.Figure()
    d = df[df.dang_lam]
    if d.empty:
        return _fig(_trong(fig, "Không có nhân sự trong phạm vi"), 420)
    top = d.sort_values("online", ascending=(xep == "thap")).head(15).iloc[::-1]
    fig.add_trace(go.Bar(
        x=top.online, y=[f"{t} · {p}" for t, p in zip(top.ho_ten, top.phong)], orientation="h",
        marker_color=[MAU_NHOM.get(c, "#94A3B8") for c in top.nhom_tham_nien],
        text=top.online, textposition="outside", cliponaxis=False,
        customdata=list(zip(top.acc, top.tham_nien.replace("", "chưa có NSLĐ"), top.vvip)),
        hovertemplate="%{y}<br>%{customdata[0]} · thâm niên %{customdata[1]}"
                      "<br>Online %{x} · V.VIP %{customdata[2]}<extra></extra>"))
    fig.update_xaxes(title=None, rangemode="tozero")
    fig.update_yaxes(automargin=True, gridcolor="rgba(0,0,0,0)")
    return _fig(fig, 420)


# ------------------------------------------------------------------ callbacks
def _ky(ngay_iso):
    ngays = cac_ngay_co_du_lieu()
    ngay_iso = ngay_iso or (ngays[-1] if ngays else None)
    if not ngay_iso:
        return None, None, None
    d = date.fromisoformat(ngay_iso)
    return d, f"{d.year}-{d.month:02d}", d.day


def _du_lieu(ngay_iso, chi_nhanh, chon_phong):
    """(ngày, tháng, bảng nhân sự trong phạm vi quyền + phòng đang chọn)."""
    d, thang, ngay = _ky(ngay_iso)
    if d is None:
        return None, None, None
    df = hieu_suat_nhan_su(thang, chi_phong=_ma_phong(chon_phong, chi_nhanh), ngay=ngay)
    return d, thang, df


def _loc_bang(df, nhom, loc):
    if nhom:
        df = df[df.nhom_tham_nien.isin(nhom)]
    if loc == "zero":
        df = df[(df.online == 0) & df.dang_lam]
    elif loc == "notok":
        df = df[df.nsld == "Chưa đạt"]
    elif loc == "chua_nsld":
        df = df[~df.co_nsld]
    return df


def _ban_ghi(df):
    return df.astype(object).where(df.notna(), None).to_dict("records")


# ---------------------------------------------------------------- bảng NSLĐ
MAU_THAP, MAU_GIUA, MAU_CAO = (244, 166, 166), (255, 255, 255), (150, 208, 160)


def _pha(a, b, t):
    return "#%02X%02X%02X" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _to_mau(rows: list[dict], cot: list[str]) -> None:
    """Thang màu từng cột như báo cáo gốc: thấp đỏ, giữa trắng, cao xanh (theo trung vị cột)."""
    for c in cot:
        gt = sorted(r[c] for r in rows if isinstance(r.get(c), (int, float)) and r[c] == r[c])
        if len(gt) < 2:
            continue
        thap, cao, giua = gt[0], gt[-1], gt[len(gt) // 2]
        for r in rows:
            v = r.get(c)
            if not isinstance(v, (int, float)) or v != v:
                continue
            if v <= giua:
                r[f"_m_{c}"] = _pha(MAU_THAP, MAU_GIUA, (v - thap) / (giua - thap) if giua > thap else 1)
            else:
                r[f"_m_{c}"] = _pha(MAU_GIUA, MAU_CAO, (v - giua) / (cao - giua) if cao > giua else 1)


O_MAU = {"function": "params.data && params.data['_m_' + params.colDef.field] ? "
                     "{backgroundColor: params.data['_m_' + params.colDef.field]} : null"}
SO2 = {"function": "params.value == null ? '' : Number(params.value).toLocaleString('vi-VN', "
                   "{minimumFractionDigits: 2, maximumFractionDigits: 2})"}
SO1 = {"function": "params.value == null ? '' : Number(params.value).toLocaleString('vi-VN', "
                   "{minimumFractionDigits: 1, maximumFractionDigits: 1})"}
DONG_TONG = {"styleConditions": [{"condition": "params.node.rowPinned",
                                  "style": {"backgroundColor": "#FDE9B8", "fontWeight": "700"}}]}


def _cot_thang(tien_to: str, den: int, nhan, fmt) -> list[dict]:
    return [{"field": f"{tien_to}{i}", "headerName": nhan(i), "minWidth": 62, "flex": .6,
             "type": "numericColumn", "valueFormatter": fmt, "cellStyle": O_MAU} for i in range(1, den + 1)]


def _cols_ns(xem: str, nam: int, den: int) -> list[dict]:
    thang = _cot_thang("t", den, lambda i: f"NSLĐ {i:02d}/{nam}", SO2)
    tb = {"field": "tb", "headerName": "TB NSLĐ ITN", "minWidth": 90, "flex": .7,
          "type": "numericColumn", "valueFormatter": SO2, "cellStyle": O_MAU}
    if xem == "nhan_su":
        return [{"field": "ho_ten", "headerName": "Nhân sự", "pinned": "left", "minWidth": 170,
                 "flex": 1.3, "tooltipField": "acc", "cellStyle": {"fontWeight": "600"}},
                {"field": "phong", "headerName": "Phòng", "minWidth": 64, "maxWidth": 84},
                {"field": "vi_tri", "headerName": "Vị trí", "minWidth": 70, "maxWidth": 80},
                {"field": "tham_nien_bucket", "headerName": "Thâm niên", "minWidth": 80, "flex": .5}
                ] + thang + [tb]
    return [{"field": "phong", "headerName": "Phòng", "pinned": "left", "minWidth": 110, "flex": .8,
             "cellStyle": {"fontWeight": "650"}},
            {"field": "so_nguoi", "headerName": "Số người xét", "minWidth": 84, "flex": .5,
             "type": "numericColumn",
             "headerTooltip": "NVKD + CTV được xét NSLĐ (bỏ Không xét) trong file tháng gần nhất"}
            ] + thang + [tb]


def _cols_tb(xem: str, den: int) -> list[dict]:
    thang = _cot_thang("k", den, lambda i: f"Tháng thứ {i}", SO1)
    tb = {"field": "tb", "headerName": "Trung bình", "minWidth": 86, "flex": .6,
          "type": "numericColumn", "valueFormatter": SO1, "cellStyle": O_MAU}
    if xem == "nhan_su":
        return [{"field": "ho_ten", "headerName": "Tân binh", "pinned": "left", "minWidth": 170,
                 "flex": 1.3, "tooltipField": "acc", "cellStyle": {"fontWeight": "600"}},
                {"field": "phong", "headerName": "Phòng", "minWidth": 64, "maxWidth": 80},
                {"field": "vi_tri", "headerName": "Vị trí", "minWidth": 70, "maxWidth": 80},
                {"field": "ngay_vao", "headerName": "Ngày vào", "minWidth": 104, "maxWidth": 110},
                {"field": "tinh_trang", "headerName": "Tình trạng", "minWidth": 92, "maxWidth": 100,
                 "cellStyle": {"styleConditions": [{"condition": "params.value == 'Đã nghỉ'",
                                                    "style": {"color": "#B42318", "fontWeight": "650"}}]}},
                ] + thang + [tb]
    return [{"field": "phong", "headerName": "Phòng", "pinned": "left", "minWidth": 96, "flex": .7,
             "cellStyle": {"fontWeight": "650"}},
            {"field": "so_moi", "headerName": "Tân binh", "minWidth": 76, "flex": .5,
             "type": "numericColumn"},
            {"field": "da_nghi", "headerName": "Đã nghỉ", "minWidth": 70, "flex": .5,
             "type": "numericColumn"},
            {"field": "con_lai", "headerName": "Còn lại", "minWidth": 70, "flex": .5,
             "type": "numericColumn"},
            {"field": "ty_le_out", "headerName": "Tỷ lệ out", "minWidth": 78, "flex": .5,
             "type": "numericColumn", "valueFormatter": PCT},
            ] + thang + [tb]


def _du_lieu_nsld(ngay_iso, chi_nhanh):
    """(năm, tháng NSLĐ cuối, dữ liệu mọi phòng trong chi nhánh) hoặc None nếu chưa có file."""
    d, _, _ = _ky(ngay_iso)
    d = d or date.today()
    den = nsld.thang_nsld_den(d.year, d.month)
    if not den:
        return d.year, None, None
    df = nsld.du_lieu(d.year, den)
    if chi_nhanh and chi_nhanh != "all":
        cn = {p["code"] for p in phong_order() if p.get("chi_nhanh") == chi_nhanh}
        df = df[df.phong_code.isin(cn)]
    return d.year, den, df


def register(app):
    gan_chon_ngay(app, "hr")

    @app.callback(Output("hr-phong", "options"), Output("hr-phong", "value"),
                  Input("hr-cn", "value"), State("hr-phong", "value"))
    def _ds_phong(chi_nhanh, dang_chon):
        opts = _phong_opts(chi_nhanh)
        giu = dang_chon if dang_chon in {o["value"] for o in opts} else _phong_mac_dinh(chi_nhanh)
        return opts, giu

    @app.callback(Output("hr-ns-xem", "value"), Output("hr-tb-xem", "value"),
                  Input("hr-phong", "value"), prevent_initial_call=True)
    def _xem_mac_dinh(chon_phong):
        """Xem nhiều phòng -> bảng theo phòng; chọn một phòng cụ thể -> từng nhân sự của phòng đó."""
        xem = "phong" if chon_phong in (None, TAT_CA_KD, TAT_CA) else "nhan_su"
        return xem, xem

    @app.callback(Output("hr-pane-ban", "hidden"), Output("hr-pane-nsld", "hidden"),
                  Input("hr-tab", "value"))
    def _doi_tab(tab):
        return tab == "nsld", tab != "nsld"

    @app.callback(Output("hr-kpi", "children"), Output("hr-nguon-hr", "children"),
                  Output("hr-thong-bao", "children"),
                  Output("hr-canhbao", "columnDefs"), Output("hr-canhbao", "rowData"),
                  Output("hr-cb-tom-tat", "children"), Output("hr-cb-mo-ta", "children"),
                  Output("hr-bar-nhom", "figure"), Output("hr-tn-mo-ta", "children"),
                  Input("hr-date", "date"), Input("hr-cn", "value"), Input("hr-phong", "value"))
    def _cap_nhat(ngay_iso, chi_nhanh, chon_phong):
        d, thang, df = _du_lieu(ngay_iso, chi_nhanh, chon_phong)
        if d is None:
            trong = _fig(_trong(go.Figure(), "Chưa có số liệu"))
            return ([], "", alert("Chưa có số liệu. Nạp file Internet để bắt đầu.", "info"),
                    _cols_canh_bao(), [], "", "", trong, "")

        hr_thang = df.hr_thang.dropna().iloc[0] if df.hr_thang.notna().any() else None
        nsld_nhan = f"NSLĐ T{hr_thang[5:7]}/{hr_thang[:4]}" if hr_thang else "Chưa có NSLĐ"
        nguon = html.Span(nsld_nhan, className="badge muted",
                          title="Thâm niên, điểm và kết luận NSLĐ lấy từ file này")
        thong_bao = ("" if hr_thang else
                     alert("Chưa nạp file NSLĐ nên chưa có thâm niên, điểm NSLĐ. Số bán vẫn xem được.",
                           "warn"))

        dang_lam = df[df.dang_lam]
        n = len(dang_lam)
        tong = int(dang_lam.online.sum())
        zero = int((dang_lam.online == 0).sum())
        notok = int((dang_lam.nsld == "Chưa đạt").sum())
        cb = canh_bao_nhan_su(thang, ngay=d.day, df=df)
        cao = int((cb.muc_rui_ro == canh_bao.TRAO_DOI_NGAY).sum()) if len(cb) else 0
        theo_doi = len(cb) - cao
        moi = int(dang_lam.nhom_tham_nien.eq("MOI").sum())
        kpis = [
            kpi("Nhân sự đang làm", f"{n}", f"{moi} người mới, 1-3 tháng" if hr_thang else "Đang làm"),
            kpi("Online bình quân", f"{tong / n:.1f}".replace(".", ",") if n else "–",
                f"mỗi người · tổng {tong:,} online".replace(",", ".")),
            kpi("Chưa có số", f"{zero}", f"{zero / n * 100:.0f}% nhân sự" if n else "",
                "bad" if zero else "ok"),
            kpi("Cần trao đổi ngay", f"{cao}", f"và {theo_doi} người cần theo dõi",
                "bad" if cao else ("warn" if theo_doi else "ok")),
            kpi("NSLĐ chưa đạt", f"{notok}" if hr_thang else "–", nsld_nhan,
                "warn" if notok else ""),
        ]

        if len(cb):
            cb = cb.assign(muc=cb.muc_rui_ro)
        tom_tat = html.Div([
            html.Span(f"{cao} trao đổi ngay", className="badge bad" if cao else "badge ok"),
            html.Span(f"{theo_doi} theo dõi", className="badge warn" if theo_doi else "badge muted"),
        ], style={"display": "flex", "gap": "8px", "marginBottom": "10px"}) if len(cb) else html.Div(
            "Không có ai cần trao đổi trong phạm vi này.", className="desc")
        mo_ta_cb = (f"{_ten_pham_vi(chon_phong).capitalize()} · tính đến {d:%d/%m} · trao đổi ngay: "
                    f"từ {canh_bao.NGAY_TRAO_DOI_NGAY} ngày không có số · theo dõi: từ "
                    f"{canh_bao.NGAY_THEO_DOI} ngày liền chưa có số, tuần này giảm từ một nửa, NSLĐ chưa đạt")
        mo_ta_tn = (f"Online bình quân mỗi người, luỹ kế 01-{d:%d/%m} · thâm niên theo "
                    f"{nsld_nhan}" if hr_thang else "Cần file NSLĐ để chia theo thâm niên")
        return (kpis, nguon, thong_bao, _cols_canh_bao(), _ban_ghi(cb) if len(cb) else [],
                tom_tat, mo_ta_cb, _bieu_do_tham_nien(df), mo_ta_tn)

    @app.callback(Output("hr-scatter", "figure"),
                  Input("hr-date", "date"), Input("hr-cn", "value"), Input("hr-phong", "value"),
                  Input("hr-xep", "value"))
    def _xep_hang(ngay_iso, chi_nhanh, chon_phong, xep):
        d, _, df = _du_lieu(ngay_iso, chi_nhanh, chon_phong)
        if d is None:
            return _fig(_trong(go.Figure(), "Chưa có số liệu"), 420)
        return _bieu_do_xep_hang(df, xep)

    @app.callback(Output("hr-grid", "columnDefs"), Output("hr-grid", "rowData"),
                  Output("hr-tom-tat", "children"), Output("hr-grid", "style"),
                  Input("hr-date", "date"), Input("hr-cn", "value"), Input("hr-phong", "value"),
                  Input("hr-nhom", "value"), Input("hr-loc", "value"), Input("hr-xem", "value"))
    def _bang(ngay_iso, chi_nhanh, chon_phong, nhom, loc, xem):
        d, _, df = _du_lieu(ngay_iso, chi_nhanh, chon_phong)
        if d is None:
            return _cols(xem), [], "", khung_cuon(0)
        df = _loc_bang(df, nhom, loc)
        nghi = int((~df.dang_lam).sum())
        so_nguoi = f"{len(df)} người" + (f" ({len(df) - nghi} đang làm, {nghi} đã nghỉ còn số trong kỳ)"
                                         if nghi else "")
        return (_cols(xem), _ban_ghi(df),
                f"{so_nguoi} · {_ten_pham_vi(chon_phong)} · luỹ kế 01-{d:%d/%m/%Y}",
                khung_cuon(len(df)))

    @app.callback(Output("hr-grid", "dashGridOptions"), Input("hr-tim", "value"),
                  prevent_initial_call=True)
    def _tim(chu):
        p = Patch()
        p["quickFilterText"] = chu or ""
        return p

    # ------------------------------------------------------------ tab NSLĐ
    @app.callback(Output("hr-ns-kpi", "children"), Output("hr-ns-thong-bao", "children"),
                  Output("hr-ns-grid", "columnDefs"), Output("hr-ns-grid", "rowData"),
                  Output("hr-ns-grid", "pinnedBottomRowData"), Output("hr-ns-mo-ta", "children"),
                  Output("hr-ns-chu", "children"),
                  Output("hr-tb-grid", "columnDefs"), Output("hr-tb-grid", "rowData"),
                  Output("hr-tb-grid", "pinnedBottomRowData"), Output("hr-tb-mo-ta", "children"),
                  Output("hr-tb-chu", "children"),
                  Output("hr-ns-grid", "style"), Output("hr-tb-grid", "style"),
                  Input("hr-tab", "value"), Input("hr-date", "date"), Input("hr-cn", "value"),
                  Input("hr-phong", "value"), Input("hr-ns-xem", "value"), Input("hr-tb-xem", "value"))
    def _nsld(tab, ngay_iso, chi_nhanh, chon_phong, xem_ns, xem_tb):
        if tab != "nsld":
            return (no_update,) * 14
        nam, den, df = _du_lieu_nsld(ngay_iso, chi_nhanh)
        if not den or df is None or df.empty:
            bao = alert([html.B(f"Chưa có file NSLĐ năm {nam}. "),
                         "Vào Nạp dữ liệu, chọn các file NSLĐ từng tháng (tên file có tháng, VD "
                         "“NSLĐ T8.2026”) rồi lưu một lần."], "warn")
            return [], bao, [], [], [], "", "", [], [], [], "", "", khung_cuon(0), khung_cuon(0)

        co_thang = sorted(df.so_thang.unique())
        thieu = [t for t in range(1, den + 1) if t not in co_thang]
        bao = (alert([html.B("Còn thiếu file NSLĐ "),
                      ", ".join(f"T{t}" for t in thieu),
                      f"/{nam} - các cột tháng đó để trống. Nạp bổ sung ở trang Nạp dữ liệu."], "warn")
               if thieu else "")

        ma = _ma_phong(chon_phong, chi_nhanh)
        pham_vi = df[df.phong_code.isin(ma)]
        tt = nsld.tom_tat(pham_vi, nam, den) if len(pham_vi) else {}
        ten_pv = _ten_pham_vi(chon_phong)
        if tt:
            tc = tt["thang_cuoi"]
            chenh = (tt["nsld"] - tt["nsld_truoc"]) if tt["nsld"] is not None and tt["nsld_truoc"] else None
            kpis = [
                kpi(f"NSLĐ ITN T{tc}", _so2(tt["nsld"]),
                    f"{'+' if chenh >= 0 else ''}{_so2(chenh)} so với T{tc - 1}" if chenh is not None
                    else ten_pv.capitalize(),
                    "" if chenh is None else ("ok" if chenh >= 0 else "bad")),
                kpi(f"Bình quân T1-T{den}", _so2(tt["nsld_tb"]), "Bình quân các tháng có file"),
                kpi("Số người xét NSLĐ", f"{tt['so_nguoi']}", f"{tt['so_nvkd']} NVKD · file T{tc}"),
                kpi("NSLĐ chưa đạt", f"{tt['chua_dat']}", f"Kết luận NOT OK · T{tc}",
                    "warn" if tt["chua_dat"] else "ok"),
                kpi(f"Tân binh {nam}", f"{tt['tan_binh']}",
                    f"{tt['tan_binh_nghi']} đã nghỉ · out "
                    f"{round(tt['tan_binh_nghi'] / tt['tan_binh'] * 100) if tt['tan_binh'] else 0}%",
                    "bad" if tt["tan_binh"] and tt["tan_binh_nghi"] / tt["tan_binh"] >= .3 else ""),
            ]
        else:
            kpis = []

        # --- bảng 1: NSLĐ ITN theo tháng
        xem_duoc = current_user.duoc_xem_nhan_su
        cot_t = [f"t{i}" for i in range(1, den + 1)] + ["tb"]
        if xem_ns == "nhan_su" and xem_duoc:
            bang = nsld.nsld_nhan_su(pham_vi, den)
            rows, pin = (_ban_ghi(bang) if len(bang) else []), []
            _to_mau(rows, cot_t)
            chu_ns = "" if rows else html.Div("Không có nhân sự trong phạm vi này.", className="desc")
            mo_ta_ns = f"ITN từng tháng của từng người · {ten_pv}"
        else:
            bang = nsld.nsld_theo_phong(df, den)
            du = bang[bang.loai_dong == "data"]
            rows = _ban_ghi(du)
            _to_mau(rows, cot_t)
            pin = _ban_ghi(bang[bang.loai_dong == "total"])
            chu_ns = ""
            mo_ta_ns = f"Tổng ITN / số người được xét (NVKD + CTV), năm {nam}"

        # --- bảng 2: tân binh
        cot_k = [f"k{i}" for i in range(1, den + 1)] + ["tb"]
        if xem_tb == "nhan_su" and xem_duoc:
            bang_tb = nsld.tan_binh_nhan_su(pham_vi, nam, den)
            rows_tb, pin_tb = (_ban_ghi(bang_tb) if len(bang_tb) else []), []
            _to_mau(rows_tb, cot_k)
            mo_ta_tb = f"ITN từng tháng làm việc của tân binh {nam} · {ten_pv}"
        else:
            bang_tb = nsld.tan_binh_theo_phong(df, nam, den)
            rows_tb = _ban_ghi(bang_tb[bang_tb.loai_dong == "data"]) if len(bang_tb) else []
            _to_mau(rows_tb, cot_k)
            pin_tb = _ban_ghi(bang_tb[bang_tb.loai_dong == "total"]) if len(bang_tb) else []
            mo_ta_tb = f"Tân binh vào làm năm {nam}: số lượng, tỷ lệ out, ITN bình quân theo tháng làm việc"
        chu_tb = "" if rows_tb else html.Div(f"Chưa có tân binh năm {nam} trong phạm vi này.",
                                             className="desc")

        return (kpis, bao, _cols_ns(xem_ns if xem_duoc else "phong", nam, den), rows, pin, mo_ta_ns,
                chu_ns, _cols_tb(xem_tb if xem_duoc else "phong", den), rows_tb, pin_tb, mo_ta_tb,
                chu_tb, khung_cuon(len(rows), bool(pin)), khung_cuon(len(rows_tb), bool(pin_tb)))

    @app.callback(Output("hr-tai-xuong", "data", allow_duplicate=True),
                  Input("hr-ns-export", "n_clicks"),
                  State("hr-date", "date"), State("hr-cn", "value"), State("hr-phong", "value"),
                  prevent_initial_call=True)
    def _excel_nsld(n, ngay_iso, chi_nhanh, chon_phong):
        if not n:
            return no_update
        nam, den, df = _du_lieu_nsld(ngay_iso, chi_nhanh)
        if not den or df is None or df.empty:
            return no_update
        pham_vi = df[df.phong_code.isin(_ma_phong(chon_phong, chi_nhanh))]
        thang = [(f"t{i}", f"NSLĐ {i:02d}/{nam}", "so") for i in range(1, den + 1)]
        thang_k = [(f"k{i}", f"Tháng thứ {i}", "so") for i in range(1, den + 1)]
        bang = [("NSLĐ theo phòng", nsld.nsld_theo_phong(df, den),
                 [("phong", "Phòng", "text"), ("so_nguoi", "Số người xét", "so")] + thang
                 + [("tb", "TB NSLĐ ITN", "so")]),
                ("Tân binh theo phòng", nsld.tan_binh_theo_phong(df, nam, den),
                 [("phong", "Phòng", "text"), ("so_moi", "Tân binh", "so"), ("da_nghi", "Đã nghỉ", "so"),
                  ("con_lai", "Còn lại", "so"), ("ty_le_out", "Tỷ lệ out", "pct")] + thang_k
                 + [("tb", "Trung bình", "so")])]
        if current_user.duoc_xem_nhan_su:
            bang += [("NSLĐ từng nhân sự", nsld.nsld_nhan_su(pham_vi, den),
                      [("ho_ten", "Nhân sự", "text"), ("acc", "Acc", "text"), ("phong", "Phòng", "text"),
                       ("vi_tri", "Vị trí", "text"), ("tham_nien_bucket", "Thâm niên", "text")]
                      + thang + [("tb", "TB NSLĐ ITN", "so")]),
                     ("Từng tân binh", nsld.tan_binh_nhan_su(pham_vi, nam, den),
                      [("ho_ten", "Tân binh", "text"), ("acc", "Acc", "text"), ("phong", "Phòng", "text"),
                       ("vi_tri", "Vị trí", "text"), ("ngay_vao", "Ngày vào", "text"),
                       ("tinh_trang", "Tình trạng", "text")] + thang_k + [("tb", "Trung bình", "so")])]
        noi_dung = xuat_phan_tich("", f"NĂNG SUẤT LAO ĐỘNG {nam} · đến T{den}", bang)
        ghi_log("xuat_nsld", f"{nam}-T{den} · {_ten_pham_vi(chon_phong)}")
        return dcc.send_bytes(noi_dung, f"NSLD_{nam}_T{den:02d}.xlsx")

    @app.callback(Output("hr-tai-xuong", "data"), Input("hr-export", "n_clicks"),
                  State("hr-date", "date"), State("hr-cn", "value"), State("hr-phong", "value"),
                  State("hr-nhom", "value"), State("hr-loc", "value"),
                  prevent_initial_call=True)
    def _excel(n, ngay_iso, chi_nhanh, chon_phong, nhom, loc):
        if not n or not current_user.duoc_xem_nhan_su:
            return no_update
        d, thang, df = _du_lieu(ngay_iso, chi_nhanh, chon_phong)
        if d is None:
            return no_update
        df = _loc_bang(df, nhom, loc)
        cot = [("ho_ten", "Nhân sự", "text"), ("acc", "Acc", "text"), ("phong", "Phòng", "text"),
               ("chi_nhanh", "Chi nhánh", "text"), ("vi_tri", "Vị trí", "text"),
               ("tham_nien", "Thâm niên", "text"), ("online", "Online", "so"),
               ("so_voi_tham_nien", "So với cùng thâm niên", "pct"),
               ("so_ngay_co_so", "Ngày có số", "so"), ("ban_moi", "Bán mới", "so"),
               ("vvip", "V.VIP", "so"), ("ty_le_vvip", "VVIP/PTTB", "pct"),
               ("camera", "Camera", "so"), ("diem_tong", "Điểm NSLĐ", "so"),
               ("nsld", "NSLĐ", "text"), ("dieu_kien", "Điều kiện", "text"),
               ("trang_thai", "Tình trạng", "text")]
        noi_dung = xuat_phan_tich("", f"HIỆU SUẤT NHÂN SỰ · luỹ kế 01-{d:%d/%m/%Y}",
                                  [("Nhân sự", df, cot)])
        ghi_log("xuat_hieu_suat_nhan_su", f"{d:%Y-%m-%d} · {len(df)} dòng")
        return dcc.send_bytes(noi_dung, f"HieuSuatNhanSu_{d:%Y%m%d}.xlsx")


def _so2(v) -> str:
    return "–" if v is None else f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
