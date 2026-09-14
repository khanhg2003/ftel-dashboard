"""Trang Hiệu suất nhân sự - nhìn năng suất theo người, đối chiếu thâm niên và NSLĐ.

Khác Báo cáo phòng (một phòng, dùng buổi sáng), trang này nhìn ngang nhiều phòng:
1. Ngày (luỹ kế tháng như Báo cáo Tổng) + chi nhánh + phạm vi phòng.
2. Năm chỉ số: quân số, bình quân, chưa có số, cần trao đổi, NSLĐ chưa đạt.
3. "Cần trao đổi sớm" đặt trước tiên vì là việc cần làm ngay, mỗi người có sẵn lý do.
4. Năng suất theo thâm niên + xếp hạng, xếp đôi trên laptop.
5. Bảng chi tiết: tìm, lọc phòng / thâm niên / tình trạng, hai góc nhìn vừa màn hình, xuất Excel.

Quyền: Quản trị xem mọi phòng, Trưởng phòng chỉ phòng mình phụ trách, Nhập liệu không vào được.
"""
from __future__ import annotations

from datetime import date

import dash_ag_grid as dag
import plotly.graph_objects as go
from dash import Input, Output, Patch, State, dcc, html, no_update
from flask_login import current_user

from app.auth import ghi_log, loc_nhan_su
from app.export_phan_tich import xuat_phan_tich
from app.hr_metrics import (MOC_THAM_NIEN, NGAY_KHONG_SO_CAO, TEN_NHOM, canh_bao_nhan_su,
                            hieu_suat_nhan_su, tong_hop_tham_nien)
from app.metrics import cac_ngay_co_du_lieu
from app.org import loc_chi_nhanh
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
    ("Online", "Hợp đồng Internet online từ ngày 01 đến ngày chọn, theo acc người bán."),
    ("Nhân sự kinh doanh", "Người đang làm ở phòng IBB và phòng địa bàn, theo danh mục acc → phòng. "
                           "Không tính người đã nghỉ, và acc 60 ngày không có số mà không có trong NSLĐ "
                           "(trưởng phòng, acc cũ)."),
    ("Thâm niên · NSLĐ", "Lấy từ file NSLĐ gần nhất (thường là tháng trước). Người chưa có trong "
                         "NSLĐ để trống."),
    ("So với cùng thâm niên", "Online của người đó so với trung vị những người cùng mốc thâm niên "
                              "ở phòng kinh doanh. +50% là bán hơn một nửa so với người cùng mốc."),
    ("VVIP/PTTB", "Số V.VIP online chia số online, cùng cách tính với Báo cáo Tổng."),
    ("Cần trao đổi ngay", f"{NGAY_KHONG_SO_CAO} ngày gần nhất không có số online nào."),
    ("Cần theo dõi", "Tuần này giảm từ một nửa so với tuần trước (tuần trước từ 3 số), "
                     "hoặc NSLĐ chưa đạt."),
]


def topbar():
    return [html.Div([html.H1("Hiệu suất nhân sự"),
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


def _dau_the(tieu_de, mo_ta_id=None, mo_ta=None, nut=None):
    return html.Div([
        html.Div([html.H3(tieu_de),
                  html.Div(mo_ta, id=mo_ta_id, className="desc") if mo_ta_id
                  else html.Div(mo_ta, className="desc")], className="the-ten"),
        html.Div(nut or [], className="the-nut"),
    ], className="the-dau")


def layout():
    ngays = cac_ngay_co_du_lieu()
    return html.Div([
        html.Div([
            field("Ngày báo cáo", chon_ngay("hr", ngays)),
            field("Chi nhánh", chi_nhanh_control("hr-cn")),
            field("Phạm vi", seg_control("hr-pham-vi", [("kd", "Phòng kinh doanh"),
                                                        ("tat_ca", "Tất cả phòng")], "kd")),
        ], className="toolbar loc-trang"),
        dcc.Download(id="hr-tai-xuong"),

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
                dcc.Dropdown(id="hr-phong", multi=True, placeholder="Mọi phòng",
                             style={"minWidth": "190px"}),
                dcc.Dropdown(id="hr-nhom", multi=True, placeholder="Mọi thâm niên",
                             options=[{"label": v, "value": k} for k, v in TEN_NHOM.items()],
                             style={"minWidth": "170px"}),
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
                  dashGridOptions={"pagination": True, "paginationPageSize": 12,
                                   "paginationPageSizeSelector": False, "rowHeight": 34}),
            chu_giai("Cách tính", DINH_NGHIA),
        ], className="card"),
    ])


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
        text=[f"{v:.1f}" for v in g.tb_online], textposition="outside", cliponaxis=False,
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


def _du_lieu(ngay_iso, chi_nhanh, pham_vi):
    """(ngày, tháng, bảng nhân sự trong phạm vi quyền + bộ lọc trang)."""
    d, thang, ngay = _ky(ngay_iso)
    if d is None:
        return None, None, None
    scope = loc_nhan_su(loc_chi_nhanh(current_user.phong_duoc_xem(), chi_nhanh, thang),
                        current_user.phong_nhan_su())
    df = hieu_suat_nhan_su(thang, chi_phong=scope, ngay=ngay)
    if pham_vi != "tat_ca":
        df = df[df.kd]
    return d, thang, df


def _loc_bang(df, phong, nhom, loc):
    if phong:
        df = df[df.phong.isin(phong)]
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


def register(app):
    gan_chon_ngay(app, "hr")

    @app.callback(Output("hr-kpi", "children"), Output("hr-nguon-hr", "children"),
                  Output("hr-thong-bao", "children"),
                  Output("hr-canhbao", "columnDefs"), Output("hr-canhbao", "rowData"),
                  Output("hr-cb-tom-tat", "children"), Output("hr-cb-mo-ta", "children"),
                  Output("hr-bar-nhom", "figure"), Output("hr-tn-mo-ta", "children"),
                  Output("hr-phong", "options"),
                  Input("hr-date", "date"), Input("hr-cn", "value"), Input("hr-pham-vi", "value"))
    def _cap_nhat(ngay_iso, chi_nhanh, pham_vi):
        d, thang, df = _du_lieu(ngay_iso, chi_nhanh, pham_vi)
        if d is None:
            trong = _fig(_trong(go.Figure(), "Chưa có số liệu"))
            return ([], "", alert("Chưa có số liệu. Nạp file Internet để bắt đầu.", "info"),
                    _cols_canh_bao(), [], "", "", trong, "", [])

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
        cao = int((cb.muc_rui_ro == "Cao").sum()) if len(cb) else 0
        theo_doi = len(cb) - cao
        moi = int(dang_lam.nhom_tham_nien.eq("MOI").sum())
        ten_nv = "Nhân sự kinh doanh" if pham_vi != "tat_ca" else "Nhân sự"
        kpis = [
            kpi(ten_nv, f"{n}", f"{moi} người mới, 1-3 tháng" if hr_thang else "Đang làm"),
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
            cb = cb.assign(muc=cb.muc_rui_ro.map({"Cao": "Trao đổi ngay", "Trung bình": "Theo dõi"}))
        tom_tat = html.Div([
            html.Span(f"{cao} trao đổi ngay", className="badge bad" if cao else "badge ok"),
            html.Span(f"{theo_doi} theo dõi", className="badge warn" if theo_doi else "badge muted"),
        ], style={"display": "flex", "gap": "8px", "marginBottom": "10px"}) if len(cb) else html.Div(
            "Không có ai cần trao đổi trong phạm vi này.", className="desc")
        mo_ta_cb = (f"Tính đến {d:%d/%m}: {NGAY_KHONG_SO_CAO} ngày chưa có số, tuần này giảm từ "
                    "một nửa, hoặc NSLĐ chưa đạt")
        mo_ta_tn = (f"Online bình quân mỗi người, luỹ kế 01-{d:%d/%m} · thâm niên theo "
                    f"{nsld_nhan}" if hr_thang else "Cần file NSLĐ để chia theo thâm niên")
        phong_opts = [{"label": p, "value": p} for p in sorted(df.phong.dropna().unique())]
        return (kpis, nguon, thong_bao, _cols_canh_bao(), _ban_ghi(cb) if len(cb) else [],
                tom_tat, mo_ta_cb, _bieu_do_tham_nien(df[df.kd] if pham_vi != "tat_ca" else df),
                mo_ta_tn, phong_opts)

    @app.callback(Output("hr-scatter", "figure"),
                  Input("hr-date", "date"), Input("hr-cn", "value"), Input("hr-pham-vi", "value"),
                  Input("hr-xep", "value"))
    def _xep_hang(ngay_iso, chi_nhanh, pham_vi, xep):
        d, _, df = _du_lieu(ngay_iso, chi_nhanh, pham_vi)
        if d is None:
            return _fig(_trong(go.Figure(), "Chưa có số liệu"), 420)
        return _bieu_do_xep_hang(df, xep)

    @app.callback(Output("hr-grid", "columnDefs"), Output("hr-grid", "rowData"),
                  Output("hr-tom-tat", "children"),
                  Input("hr-date", "date"), Input("hr-cn", "value"), Input("hr-pham-vi", "value"),
                  Input("hr-phong", "value"), Input("hr-nhom", "value"), Input("hr-loc", "value"),
                  Input("hr-xem", "value"))
    def _bang(ngay_iso, chi_nhanh, pham_vi, phong, nhom, loc, xem):
        d, _, df = _du_lieu(ngay_iso, chi_nhanh, pham_vi)
        if d is None:
            return _cols(xem), [], ""
        df = _loc_bang(df, phong, nhom, loc)
        return _cols(xem), _ban_ghi(df), f"{len(df)} người · luỹ kế 01-{d:%d/%m/%Y}"

    @app.callback(Output("hr-grid", "dashGridOptions"), Input("hr-tim", "value"),
                  prevent_initial_call=True)
    def _tim(chu):
        p = Patch()
        p["quickFilterText"] = chu or ""
        return p

    @app.callback(Output("hr-tai-xuong", "data"), Input("hr-export", "n_clicks"),
                  State("hr-date", "date"), State("hr-cn", "value"), State("hr-pham-vi", "value"),
                  State("hr-phong", "value"), State("hr-nhom", "value"), State("hr-loc", "value"),
                  prevent_initial_call=True)
    def _excel(n, ngay_iso, chi_nhanh, pham_vi, phong, nhom, loc):
        if not n or not current_user.duoc_xem_nhan_su:
            return no_update
        d, thang, df = _du_lieu(ngay_iso, chi_nhanh, pham_vi)
        if d is None:
            return no_update
        df = _loc_bang(df, phong, nhom, loc)
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
