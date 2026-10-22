"""Trang Phân tích bán hàng - trả lời "bán TỐT không" và "đang tắc ở đâu", bổ sung cho Báo cáo Tổng.

Bố cục theo câu hỏi người xem đặt ra trong giao ban:
1. Chọn KỲ như Báo cáo Tổng: mặc định luỹ kế 01 -> ngày có số mới nhất, hoặc khoảng ngày tự chọn / chọn nhanh
   (7 ngày, tuần này, tháng trước...) + chi nhánh; một nút Excel cho cả trang.
2. Sáu chỉ số chất lượng, so với cùng kỳ tháng trước (xem luỹ kế) hoặc khoảng liền trước cùng số ngày (khoảng tự
   chọn); khối "Cách tính" gập được. Số tồn luôn là số hiện tại, không theo kỳ.
3. Bảng theo phòng: chỉ tô màu các phòng kinh doanh, mốc so sánh là mức chung của phòng kinh doanh
   (phòng KT/CUS/ECOM đặc thù bán kèm thấp nên để chữ nhạt, không tô).
4. Số tồn theo thời gian chờ + danh sách hợp đồng chờ từ 7 ngày (lọc phòng, tìm kiếm).
5. Bốn biểu đồ xếp đôi trên laptop: bán kèm theo gói, tốc độ online, cơ cấu gói, nhịp theo thứ.
6. Bảng theo nhân viên (theo quyền xem nhân sự): tìm kiếm, lọc phòng, lọc người cần chú ý.
"""
from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, Patch, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate
from flask_login import current_user

from app import phan_tich as pt
from app import tro_ly as ai
from app import tro_ly_du_lieu as dl
from app.du_bao import du_bao_thang
from app.auth import ghi_log, loc_nhan_su
from app.config import rules_config
from app.export_phan_tich import xuat_phan_tich
from app.metrics import cac_ngay_co_du_lieu
from app.org import loc_chi_nhanh, phong_order
from app.overview import TEN_DONG_TONG, TEN_PHAM_VI
from app.ui.components import (alert, card, chi_nhanh_control, chu_giai, field, kpi, seg_control,
                               ghi_chu)
from app.ui.luoi import LOP, SO, PCT_GACH as PCT, bang as _bang
from app.ui import ky_chung as kc
from app.ui import lien_ket as lk
from app.ui import ngan_nhan_su as nn
from app.ui import tro_ly as tl
from app.ui.icons import icon

MAU_TOT, MAU_VUA, MAU_KEM = ("#D3EBD4", "#14532D"), ("#FCEBB4", "#6B5104"), ("#F7BDBD", "#7F1D1D")
MAU_GOI = {"Giga": "#0072BC", "Sky": "#37A5E6", "Meta": "#F37021", "Khác": "#B9C5D3"}
MAU_TON = [None, None, "#FCEBB4", "#FBD0A6", "#F7BDBD"]      # 0-2, 3-6 không tô; càng lâu càng đỏ

ROW_STYLE = {"styleConditions": [
    {"condition": "params.data.loai_dong == 'subtotal'",
     "style": {"backgroundColor": "#EDF3F9", "fontWeight": "700", "color": "#C8372D"}},
    {"condition": "params.data.loai_dong == 'total' || params.node.rowPinned",
     "style": {"backgroundColor": "#DCE8F4", "fontWeight": "700", "color": "#003057"}},
]}

DINH_NGHIA = [
    ("HĐ kèm V.VIP", "Hợp đồng Internet online trong thời gian đang xem có dòng V.VIP trong file Truyền hình (ghép "
                     "theo số hợp đồng), chia tổng online. Khác cột VVIP/PTTB của Báo cáo Tổng - cột "
                     "đó đếm V.VIP theo ngày online của chính V.VIP."),
    ("HĐ kèm Camera", "Hợp đồng online trong thời gian đang xem có trong file Camera, chia tổng online."),
    ("Đủ 3 dịch vụ", "Hợp đồng online có cả V.VIP và Camera."),
    ("Trả trước", "Hợp đồng có trả trước 3, 6 hoặc 12 tháng."),
    ("Online trong 1 ngày", "Online ngay trong ngày tạo hợp đồng hoặc hôm sau (file chỉ có ngày tạo, "
                            "không có giờ)."),
    ("Bán ngoại tỉnh", "CN Quản lý khác DNG_01/DNG_02/QNM: khách tỉnh khác do mình bán online, số "
                       "tính cho tỉnh khác. Càng cao càng cần chú ý."),
    ("Số tồn · Chờ từ 7 ngày", "Hợp đồng đã tạo, chưa online, còn nằm trong file Internet mới nhất. "
                               "Số ngày chờ tính từ ngày tạo đến ngày có số mới nhất."),
    ("Màu so sánh", "Chỉ tô cho phòng kinh doanh (IBB, địa bàn). Mốc là mức chung của các phòng kinh "
                    "doanh trong phạm vi đang xem: xanh cao hơn từ 5 điểm, vàng thấp hơn 5-10 điểm, "
                    "đỏ thấp hơn từ 10 điểm."),
]


def _nguong() -> dict:
    return {"tot": 5, "kem": 10, **(rules_config().get("phan_tich") or {})}


def topbar():
    return [html.Div([html.H1("Phân tích bán hàng"),
                      html.Div("Bán kèm, tốc độ online, số tồn và cơ cấu gói theo phòng",
                               className="sub")]),
            html.Div(className="spacer"),
            html.Div(id="pt-badge")]


def _grid(gid: str, cao: int | None = None, **kw):
    return _bang(gid, cao=cao, lop=kw.pop("className", LOP), tuy_chon=kw.pop("dashGridOptions", {}), **kw)


def _graph(gid: str):
    return dcc.Loading(dcc.Graph(id=gid, config={"displayModeBar": False, "responsive": True},
                                 style={"width": "100%"}))


def _dau_the(tieu_de: str, mo_ta_id: str | None, *dieu_khien):
    return html.Div([
        html.Div([html.H3(tieu_de, style={"margin": 0}),
                  html.Div(id=mo_ta_id, className="desc", style={"margin": "2px 0 0"})
                  if mo_ta_id else None]),
        html.Div(className="grow"), *dieu_khien], className="the-thanh")


def layout(ky: dict | None = None):
    from app.ui.pages import phantich_tinh
    ky = ky or {}
    ngays = cac_ngay_co_du_lieu()
    den = kc.ngay_co_so(ky.get("den"), ngays)
    tu = ky.get("tu") if ky.get("tu") and den and ky["tu"] <= den else ((den[:8] + "01") if den else None)
    xem_nv = current_user.duoc_xem_nhan_su
    admin = current_user.role == "admin"
    an = {"display": "none"} if current_user.role == "nvkd" else {}       # nvkd IBB7 chỉ thấy hai phần Bán theo tỉnh / Ai bán ở tỉnh nào (22/10/2026)
    lua_chon_phong = [{"label": "Mọi phòng được xem", "value": "all"}] + [
        {"label": p["ten"], "value": p["code"]} for p in phong_order()
        if current_user.phong_nhan_su() is None or p["code"] in set(current_user.phong_nhan_su())]
    return html.Div([
        html.Div([
            field("Kỳ báo cáo · từ ngày - đến ngày", html.Div([
                html.Button("‹", id="pt-lui", className="nut-ky", title="Lùi một ngày"),
                dcc.DatePickerRange(
                    id="pt-khoang", start_date=tu, end_date=den, display_format="DD/MM/YYYY",
                    min_date_allowed=(ngays[0][:8] + "01") if ngays else None,
                    max_date_allowed=ngays[-1] if ngays else None, initial_visible_month=den,
                    first_day_of_week=1, clearable=False, minimum_nights=0,
                    start_date_placeholder_text="Từ ngày", end_date_placeholder_text="Đến ngày",
                    className="date-pick khoang"),
                html.Button("›", id="pt-toi", className="nut-ky", title="Tới một ngày"),
                html.Button("Mới nhất", id="pt-p-moinhat", className="btn nho",
                            title="Luỹ kế từ ngày 01 đến ngày có số mới nhất"),
                dcc.Dropdown(id="pt-nhanh", placeholder="Chọn nhanh", searchable=False, clearable=False,
                             className="chon-nhanh", options=[
                                 {"label": "Luỹ kế tháng này", "value": "luyke"},
                                 {"label": "Riêng ngày mới nhất", "value": "motngay"},
                                 {"label": "7 ngày gần nhất", "value": "7ngay"},
                                 {"label": "Tuần này (từ thứ 2)", "value": "tuan"},
                                 {"label": "Cả tháng trước", "value": "thangtruoc"}]),
            ], className="chon-ngay")),
            field("Chi nhánh", chi_nhanh_control("pt-cn", ky.get("cn", "all"))),
            html.Div(className="grow"),
            html.Div(field(" ", html.Button([icon("download", 14), html.Span("Excel")], id="pt-xls",
                                            className="btn", title="Tải toàn bộ bảng của trang, mỗi bảng "
                                                                   "một sheet")), style=an),
        ], className="toolbar loc-trang"),
        dcc.Download(id="pt-tai-xuong"),

        html.Div([
            dcc.Loading(html.Div(id="pt-kpi", className="kpi-row kpi-6"), type="dot"),
            tl.the_ai("pt", "Dự báo cuối tháng & nhận định chất lượng bán", tl.MO_TA_DU_BAO, html.Div(id="pt-du-bao")),
            chu_giai("Cách tính các chỉ số", DINH_NGHIA),

            html.Div([
                _dau_the("Chất lượng bán theo phòng", "pt-mo-ta-phong",
                         seg_control("pt-nhom", [("tat_ca", "Tất cả phòng"), ("kd", "Phòng kinh doanh")],
                                     "tat_ca")),
                dcc.Loading(_grid("pt-phong", getRowStyle=ROW_STYLE, getRowId=lk.ROW_ID, dashGridOptions={
                    "rowClassRules": {"dong-phu": "params.data.loai_dong == 'data' && "
                                                  "!params.data.nhom_kd"}})),
                html.Div(id="pt-chu-giai", className="desc", style={"margin": "10px 0 0"}),
            ], className="card"),
        ], style=an),

        phantich_tinh.the(den, ngays, current_user.duoc_xem_ban_tinh, admin),

        html.Div([
        html.Div([
            _dau_the("Số tồn theo thời gian chờ", "pt-mo-ta-ton",
                     seg_control("pt-ton-xem", [("phong", "Theo phòng"),
                                                ("ds", "Hợp đồng chờ từ 7 ngày")], "phong")),
            html.Div(_grid("pt-ton-phong", getRowStyle=ROW_STYLE), id="pt-ton-phong-hop"),
            html.Div([
                html.Div([
                    dcc.Input(id="pt-ton-tim", type="search", placeholder="Tìm hợp đồng, acc, tên…",
                              className="o-tim"),
                    dcc.Dropdown(id="pt-ton-phong-loc", options=lua_chon_phong, value="all",
                                 clearable=False, style={"width": "220px"}),
                ], className="the-thanh"),
                nn.goi_y("Bấm đúp vào một dòng để xem chi tiết đầy đủ của nhân viên đó.",
                         style={"marginBottom": "8px"}),
                _grid("pt-ton-ds", cao=520, className=f"{LOP} {nn.lop()}"),
            ], id="pt-ton-ds-hop", hidden=True) if xem_nv else html.Div(
                alert("Danh sách hợp đồng có tên nhân viên chỉ dành cho Quản trị và Trưởng phòng.",
                      "info"), id="pt-ton-ds-hop", hidden=True),
        ], className="card"),

        html.Div([
            html.Div(card([_graph("pt-kem-goi")], title="Tỷ lệ bán kèm theo gói",
                          desc="Gói nào khách dễ lấy thêm V.VIP, Camera"), className="chart-col"),
            html.Div(card([_graph("pt-toc-do")], title="Tốc độ online",
                          desc="Số ngày từ lúc tạo hợp đồng đến khi online"), className="chart-col"),
        ], className="chart-row doi"),
        html.Div([
            html.Div(card([_graph("pt-co-cau")], title="Cơ cấu gói theo phòng kinh doanh",
                          desc="Tỷ trọng Giga / Sky / Meta trong số online của từng phòng"),
                     className="chart-col"),
            html.Div(card([_graph("pt-nhip")], title="Nhịp online theo thứ trong tuần",
                          desc="Online bình quân mỗi thứ, 4 tuần gần nhất tính đến ngày chọn. Cột đỏ "
                               "thấp hơn bình quân từ 20%"), className="chart-col"),
        ], className="chart-row doi"),

        html.Div([
            _dau_the("Chất lượng bán theo nhân viên", "pt-mo-ta-nv",
                     dcc.Input(id="pt-nv-tim", type="search", placeholder="Tìm tên hoặc acc…",
                               className="o-tim"),
                     dcc.Dropdown(id="pt-nv-phong", options=lua_chon_phong, value="all",
                                  clearable=False, style={"width": "210px"}),
                     dcc.Dropdown(
                         id="pt-nv-loc", clearable=False, value="all", searchable=False,
                         style={"width": "250px"},
                         options=[{"label": "Tất cả nhân viên có số", "value": "all"},
                                  {"label": "Chưa bán kèm V.VIP hoặc Camera", "value": "khong_kem"},
                                  {"label": "Có hợp đồng chờ từ 7 ngày", "value": "ton"}])),
            nn.goi_y(style={"marginBottom": "8px"}),
            dcc.Loading(_grid("pt-nv", cao=560, className=f"{LOP} {nn.lop()}")),
            ghi_chu("Tỷ lệ tính trên số online của chính nhân viên. Màu so với mức chung các phòng "
                    "kinh doanh; nhân viên dưới 5 hợp đồng online không tô vì mẫu quá nhỏ.", nhan="Cách đọc màu",
                    style={"margin": "10px 0 0"}),
        ], className="card", style={} if xem_nv else {"display": "none"}),
        ], style=an),
    ])


# ------------------------------------------------------------------ cột + màu
def _mau_so_voi_chung(chung: float | None, nguong: dict, cao_la_tot: bool = True,
                      dk_them: str = "params.data.nhom_kd === true") -> dict:
    if chung is None:
        return {}
    tot, kem = nguong["tot"], nguong["kem"]
    if cao_la_tot:
        dk_tot, dk_kem, dk_vua = (f"params.value >= {chung + tot}", f"params.value <= {chung - kem}",
                                  f"params.value < {chung - tot}")
    else:
        dk_tot, dk_kem, dk_vua = (f"params.value <= {chung - tot}", f"params.value >= {chung + kem}",
                                  f"params.value > {chung + tot}")
    goc = f"params.data.loai_dong != 'total' && params.value != null && {dk_them} && "
    return {"styleConditions": [
        {"condition": goc + dk_kem, "style": {"backgroundColor": MAU_KEM[0], "color": MAU_KEM[1],
                                               "fontWeight": "600"}},
        {"condition": goc + dk_vua, "style": {"backgroundColor": MAU_VUA[0], "color": MAU_VUA[1]}},
        {"condition": goc + dk_tot, "style": {"backgroundColor": MAU_TOT[0], "color": MAU_TOT[1],
                                               "fontWeight": "600"}},
    ]}


def _mau_ton(gia_tri: pd.Series) -> dict:
    """Số hợp đồng chờ lâu phụ thuộc quy mô phòng nên tô theo thứ hạng trong bảng đang xem:
    nhóm 1/4 phòng kinh doanh tồn nhiều nhất màu đỏ, trên trung vị màu vàng."""
    v = gia_tri[gia_tri > 0]
    if v.empty:
        return {}
    do, vang = float(v.quantile(.75)), float(v.median())
    goc = "params.data.loai_dong == 'data' && params.data.nhom_kd === true && params.value > 0 && "
    return {"styleConditions": [
        {"condition": goc + f"params.value >= {do}",
         "style": {"backgroundColor": MAU_KEM[0], "color": MAU_KEM[1], "fontWeight": "700"}},
        {"condition": goc + f"params.value >= {vang}",
         "style": {"backgroundColor": MAU_VUA[0], "color": MAU_VUA[1]}},
    ]}


def _cot_phong(chung: dict, nguong: dict, ton_qua_7: pd.Series) -> list:
    def ty_le(field_, ten, tip, cao_la_tot=True):
        return {"field": field_, "headerName": ten, "headerTooltip": tip, "minWidth": 92, "flex": 1,
                "type": "numericColumn", "valueFormatter": PCT,
                "cellStyle": _mau_so_voi_chung(chung.get(field_), nguong, cao_la_tot)}

    return lk.them_giai_thich([
        lk.cot_phong_bam_duoc({"field": "phong", "headerName": "Phòng", "pinned": "left", "minWidth": 160,
                               "flex": 1.6}),
        {"field": "online", "headerName": "Online", "minWidth": 78, "flex": .8,
         "type": "numericColumn", "valueFormatter": SO},
        {"headerName": "BÁN KÈM", "children": [
            ty_le("kem_vvip", "HĐ kèm V.VIP", "Hợp đồng online có kèm V.VIP / tổng online"),
            ty_le("kem_camera", "HĐ kèm Camera", "Hợp đồng online có kèm Camera / tổng online"),
            ty_le("du_3", "Đủ 3 DV", "Có cả Internet, V.VIP và Camera"),
        ]},
        {"headerName": "CHẤT LƯỢNG", "children": [
            ty_le("tra_truoc", "Trả trước", "Hợp đồng có trả trước 3, 6 hoặc 12 tháng"),
            ty_le("onl_1_ngay", "Online trong 1 ngày", "Online trong ngày tạo hoặc hôm sau"),
            ty_le("ngoai_tinh", "Ngoại tỉnh", "Khách thuộc tỉnh khác, số tính cho tỉnh khác",
                  cao_la_tot=False),
        ]},
        {"headerName": "SỐ TỒN", "children": [
            {"field": "ton", "headerName": "Chưa online", "minWidth": 88, "flex": .9,
             "type": "numericColumn", "valueFormatter": SO},
            {"field": "ton_qua_7", "headerName": "Chờ từ 7 ngày", "minWidth": 92, "flex": .9,
             "type": "numericColumn", "valueFormatter": SO, "cellStyle": _mau_ton(ton_qua_7)},
        ]},
    ])


def _cot_ton() -> list:
    cols = [{"field": "phong", "headerName": "Phòng", "pinned": "left", "minWidth": 160, "flex": 1.6},
            {"field": "tong", "headerName": "Tổng tồn", "minWidth": 86, "flex": .9,
             "type": "numericColumn", "valueFormatter": SO, "cellStyle": {"fontWeight": "700"}}]
    for i, (_, _, nhan) in enumerate(pt.MOC_TON):
        col = {"field": f"m{i}", "headerName": nhan, "minWidth": 86, "flex": .9,
               "type": "numericColumn", "valueFormatter": SO}
        if MAU_TON[i]:
            col["cellStyle"] = {"styleConditions": [
                {"condition": "!params.node.rowPinned && params.value > 0",
                 "style": {"backgroundColor": MAU_TON[i], "fontWeight": "600"}}]}
        cols.append(col)
    cols.append({"field": "tb_ngay", "headerName": "Chờ bình quân (ngày)", "minWidth": 110,
                 "flex": 1, "type": "numericColumn"})
    return cols


COT_DS_TON = [
    {"field": "hop_dong", "headerName": "Hợp đồng", "minWidth": 110, "flex": 1},
    {"field": "ho_ten", "headerName": "Nhân viên", "minWidth": 150, "flex": 1.4,
     "tooltipField": "acc_nhan_vien"},
    {"field": "phong", "headerName": "Phòng", "minWidth": 120, "flex": 1.1},
    {"field": "goi_dich_vu", "headerName": "Gói", "minWidth": 80, "flex": .7},
    {"field": "nguon_ban", "headerName": "Nguồn bán", "minWidth": 90, "flex": .8},
    {"field": "ngay_tao", "headerName": "Ngày tạo HĐ", "minWidth": 100, "flex": .9},
    {"field": "so_ngay_cho", "headerName": "Số ngày chờ", "minWidth": 90, "flex": .8,
     "type": "numericColumn", "sort": "desc", "cellStyle": {"styleConditions": [
         {"condition": "params.value > 30", "style": {"backgroundColor": MAU_KEM[0],
                                                      "fontWeight": "700"}},
         {"condition": "params.value > 14", "style": {"backgroundColor": "#FBD0A6"}}]}},
]


def _cot_nv(chung: dict, nguong: dict) -> list:
    dk = "params.data.online >= 5"

    def pct(field_, ten, cao_la_tot=True, **kw):
        return {"field": field_, "headerName": ten, "type": "numericColumn", "valueFormatter": PCT,
                "minWidth": 88, "flex": .8,
                "cellStyle": _mau_so_voi_chung(chung.get(field_), nguong, cao_la_tot, dk), **kw}

    return [
        {"field": "ho_ten", "headerName": "Nhân viên", "pinned": "left", "minWidth": 170, "flex": 1.5,
         "tooltipField": "acc", "cellStyle": {"fontWeight": "600"}},
        {"field": "acc", "headerName": "Acc", "minWidth": 130, "flex": 1.1},
        {"field": "phong", "headerName": "Phòng", "minWidth": 110, "flex": 1},
        {"field": "online", "headerName": "Online", "minWidth": 76, "flex": .7,
         "type": "numericColumn", "sort": "desc", "cellStyle": {"fontWeight": "700"}},
        pct("kem_vvip", "HĐ kèm V.VIP"), pct("kem_camera", "HĐ kèm Camera"), pct("du_3_tl", "Đủ 3 DV"),
        pct("tra_truoc_tl", "Trả trước"), pct("onl_1_ngay", "Online trong 1 ngày"),
        {"field": "ton", "headerName": "Chưa online", "minWidth": 84, "flex": .7,
         "type": "numericColumn"},
        {"field": "ton_qua_7", "headerName": "Chờ từ 7 ngày", "minWidth": 90, "flex": .7,
         "type": "numericColumn", "cellStyle": {"styleConditions": [
             {"condition": "params.value >= 3", "style": {"backgroundColor": MAU_KEM[0],
                                                          "color": MAU_KEM[1], "fontWeight": "600"}},
             {"condition": "params.value > 0", "style": {"backgroundColor": MAU_VUA[0]}}]}},
    ]


# ------------------------------------------------------------------ biểu đồ
def _fig(fig: go.Figure, height: int = 330) -> go.Figure:
    fig.update_layout(height=height, autosize=True, margin=dict(l=8, r=8, t=30, b=8),
                      font=dict(family="Inter, Segoe UI, sans-serif", size=12, color="#1B2733"),
                      plot_bgcolor="white", paper_bgcolor="white",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
    fig.update_xaxes(showgrid=False, linecolor="#E4E9F0")
    fig.update_yaxes(gridcolor="#F1F5F9", zeroline=False)
    return fig


def _trong(fig: go.Figure, chu: str = "Chưa có số liệu trong thời gian đang xem") -> go.Figure:
    fig.add_annotation(text=chu, showarrow=False, x=.5, y=.5, xref="paper", yref="paper",
                       font=dict(color="#94A3B8", size=13))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def _bd_kem_goi(g: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if g.empty:
        return _fig(_trong(fig))
    nhan = [f"{r.nhom_goi} ({r.so_hd:,})".replace(",", ".") for r in g.itertuples()]
    for cot, ten, mau in (("vvip", "Kèm V.VIP", "#0072BC"), ("camera", "Kèm Camera", "#F37021"),
                          ("du_3", "Đủ 3 DV", "#00A650")):
        fig.add_trace(go.Bar(x=nhan, y=g[cot], name=ten, marker_color=mau,
                             text=[f"{v:.0f}%" for v in g[cot]], textposition="outside",
                             cliponaxis=False,
                             hovertemplate="%{x}<br>" + ten + ": %{y:.1f}%<extra></extra>"))
    fig.update_yaxes(ticksuffix="%", range=[0, 115])
    fig.update_layout(barmode="group", bargap=.25)
    return _fig(fig)


def _bd_toc_do(g: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if g.empty or not g.so_hd.sum():
        return _fig(_trong(fig))
    mau = ["#00A650", "#5CBF7A", "#F5B942", "#F39C4A", "#E8743B", "#C8372D"]
    fig.add_trace(go.Bar(x=g.moc, y=g.so_hd, marker_color=mau[:len(g)],
                         text=[f"{v:.0f}%" if v is not None else "" for v in g.ty_le],
                         textposition="outside", cliponaxis=False,
                         hovertemplate="%{x}: %{y} hợp đồng<extra></extra>"))
    fig.update_layout(showlegend=False)
    fig.update_yaxes(title="Số hợp đồng", range=[0, g.so_hd.max() * 1.2])
    return _fig(fig)


def _bd_co_cau(g: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if g.empty:
        return _fig(_trong(fig))
    for goi in pt.NHOM_GOI + ("Khác",):
        fig.add_trace(go.Bar(y=g.phong, x=g[goi], name=goi, orientation="h",
                             marker_color=MAU_GOI[goi],
                             text=[f"{v:.0f}%" if v >= 8 else "" for v in g[goi]],
                             textposition="inside", insidetextanchor="middle",
                             hovertemplate="%{y}<br>" + goi + ": %{x:.1f}%<extra></extra>"))
    fig.update_layout(barmode="stack", bargap=.3, legend_traceorder="normal")
    fig.update_xaxes(ticksuffix="%", range=[0, 100])
    return _fig(fig, max(330, 26 * len(g) + 80))


def _bd_nhip(g: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if g.empty or not g.tb_online.sum():
        return _fig(_trong(fig))
    tb = g.tb_online.mean()
    fig.add_trace(go.Bar(x=g.thu, y=g.tb_online, text=g.tb_online, textposition="outside",
                         cliponaxis=False,
                         marker_color=["#C8372D" if v < tb * 0.8 else "#0072BC" for v in g.tb_online],
                         hovertemplate="%{x}: bình quân %{y} online<extra></extra>"))
    fig.add_hline(y=tb, line_dash="dot", line_color="#94A3B8",
                  annotation_text=f"Bình quân {tb:.0f}", annotation_position="top left")
    fig.update_layout(showlegend=False)
    fig.update_yaxes(range=[0, g.tb_online.max() * 1.2])
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
        the("HĐ kèm V.VIP", "kem_vvip", "Trên số online đang xem"),
        the("HĐ kèm Camera", "kem_camera", "Trên số online đang xem"),
        the("Đủ 3 dịch vụ", "du_3", "Internet + V.VIP + Camera"),
        the("Online trong 1 ngày", "onl_1_ngay", "Trong ngày tạo hoặc hôm sau"),
        the("Trả trước", "tra_truoc", "Có trả trước 3, 6 hoặc 12 tháng"),
        kpi("Chờ online từ 7 ngày", f"{qua_7:,}".replace(",", "."),
            f"Trên tổng {len(ton):,} hợp đồng chưa online".replace(",", "."),
            "bad" if qua_7 else "ok"),
    ]


# ------------------------------------------------------------------ dữ liệu theo bộ lọc
def _ky(tu_iso: str | None, den_iso: str | None):
    """Kỳ đang xem. Luỹ kế (từ ngày 01) so với cùng kỳ tháng trước; khoảng tự chọn so với khoảng liền trước cùng số
    ngày. `thang` = tháng của ngày cuối (dùng cho cơ cấu phòng, dự báo)."""
    ngays = cac_ngay_co_du_lieu()
    den = kc.ngay_co_so((den_iso or "")[:10] or None, ngays)
    if not den:
        return None
    d = date.fromisoformat(den)
    tu = (tu_iso or "")[:10]
    if not tu or tu > den:
        tu = den[:8] + "01"
    d_tu = date.fromisoformat(tu)
    thang = f"{d.year}-{d.month:02d}"
    luy_ke = d_tu == d.replace(day=1)
    if luy_ke:
        ck = pt.cung_ky_thang_truoc(thang, d.day)
        ten_ck = f"cùng kỳ T{int(ck[0][5:7])}"
        nhan = f"01 - {d:%d/%m/%Y}"
        ten, truoc = f"tháng {d.month}", "tháng trước"
    else:
        so = (d - d_tu).days + 1
        e = d_tu - timedelta(days=1)
        ck = ((e - timedelta(days=so - 1)).isoformat(), e.isoformat())
        ten_ck = "khoảng trước đó"
        nhan = f"{d:%d/%m/%Y}" if so == 1 else f"{d_tu:%d/%m} - {d:%d/%m/%Y}"
        ten = f"ngày {d:%d/%m}" if so == 1 else f"{d_tu:%d/%m}-{d:%d/%m}"
        truoc = f"trước {d_tu:%d/%m}"
    ten_ck_day = (f"{ten_ck} ({date.fromisoformat(ck[0]):%d/%m}" +
                  (f" - {date.fromisoformat(ck[1]):%d/%m})" if ck[0] != ck[1] else ")"))
    return SimpleNamespace(thang=thang, ngay=d.day, tu=tu, den=den, luy_ke=luy_ke, ck=ck, ten_ck=ten_ck,
                           ten_ck_day=ten_ck_day, nhan=nhan, ten=ten, truoc=truoc)


def _ten_nhan_vien() -> dict:
    from sqlalchemy import text

    from app.db import engine
    df = pd.read_sql_query(text("SELECT acc_norm, ho_ten FROM dim_employee"), engine)
    return dict(zip(df.acc_norm, df.ho_ten))


def _ds_ton(ton: pd.DataFrame, thang: str, pham_vi_nv, phong_loc: str | None) -> pd.DataFrame:
    ds = ton[ton.so_ngay_cho >= 7].copy()
    if pham_vi_nv is not None:
        ds = ds[ds.phong_code.isin(set(pham_vi_nv))]
    if phong_loc and phong_loc != "all":
        ds = ds[ds.phong_code == phong_loc]
    ten_phong = {p["code"]: p["ten"] for p in phong_order(thang)}
    ten_nv = _ten_nhan_vien()
    ds["phong"] = [ten_phong.get(c, "Chưa gán phòng") for c in ds.phong_code]
    ds["ho_ten"] = [ten_nv.get(a) or acc for a, acc in zip(ds.acc_norm, ds.acc_nhan_vien)]
    ds["ngay_tao"] = ds.ngay_tao_hd.dt.strftime("%d/%m/%Y")
    return ds.sort_values("so_ngay_cho", ascending=False)


def _nhan_vien(df, ton, thang, pham_vi_nv, phong_loc, loc) -> pd.DataFrame:
    nv = pt.theo_nhan_vien(df, ton, thang)
    if nv.empty:
        return nv
    if pham_vi_nv is not None:
        nv = nv[nv.phong_code.isin(set(pham_vi_nv))]
    if phong_loc and phong_loc != "all":
        nv = nv[nv.phong_code == phong_loc]
    if loc == "khong_kem":
        nv = nv[(nv.vvip == 0) | (nv.camera == 0)]
    elif loc == "ton":
        nv = nv[nv.ton_qua_7 > 0].sort_values("ton_qua_7", ascending=False)
    return nv


# ------------------------------------------------------------------ callback
def register(app):
    lk.gan_mo_phong(app, "pt-phong")
    kc.ghi(app, ("pt-khoang", "start_date"), ("pt-khoang", "end_date"), ("pt-cn", "value"),
           chuyen=lambda tu, den, cn: {"tu": tu, "den": den, "cn": cn})

    @app.callback(Output("pt-khoang", "start_date"), Output("pt-khoang", "end_date"), Output("pt-nhanh", "value"),
                  Input("pt-lui", "n_clicks"), Input("pt-toi", "n_clicks"), Input("pt-p-moinhat", "n_clicks"),
                  Input("pt-nhanh", "value"), State("pt-khoang", "start_date"), State("pt-khoang", "end_date"),
                  prevent_initial_call=True)
    def _chon_ky(_a, _b, _c, nhanh, tu, den):
        from app.ui.pages.tongquan import doi_ky
        ngays = cac_ngay_co_du_lieu()
        if not ngays:
            return no_update, no_update, None
        nut = {"pt-lui": "tq-lui", "pt-toi": "tq-toi", "pt-p-moinhat": "tq-p-moinhat",
               "pt-nhanh": "tq-nhanh"}.get(ctx.triggered_id)
        kq = doi_ky(nut, nhanh, tu, den, ngays)
        return (kq[0], kq[1], None) if kq else (no_update, no_update, None)

    @app.callback(Output("pt-ton-phong-hop", "hidden"), Output("pt-ton-ds-hop", "hidden"),
                  Input("pt-ton-xem", "value"))
    def _doi_xem_ton(xem):
        ds = xem == "ds"
        return ds, not ds

    for o_tim, bang in (("pt-ton-tim", "pt-ton-ds"), ("pt-nv-tim", "pt-nv")):
        def _tim(chu):
            p = Patch()
            p["quickFilterText"] = chu or ""
            return p
        app.callback(Output(bang, "dashGridOptions"), Input(o_tim, "value"),
                     prevent_initial_call=True)(_tim)

    @app.callback(
        Output("pt-kpi", "children"), Output("pt-badge", "children"),
        Output("pt-mo-ta-phong", "children"), Output("pt-chu-giai", "children"),
        Output("pt-phong", "columnDefs"), Output("pt-phong", "rowData"),
        Output("pt-mo-ta-ton", "children"),
        Output("pt-ton-phong", "columnDefs"), Output("pt-ton-phong", "rowData"),
        Output("pt-ton-phong", "pinnedBottomRowData"),
        Output("pt-kem-goi", "figure"), Output("pt-toc-do", "figure"),
        Output("pt-co-cau", "figure"), Output("pt-nhip", "figure"),
        Input("pt-khoang", "start_date"), Input("pt-khoang", "end_date"), Input("pt-cn", "value"),
        Input("pt-nhom", "value"))
    def _cap_nhat(tu_iso, den_iso, chi_nhanh, nhom):
        if current_user.role == "nvkd":                                     # trang này của nvkd chỉ có phần Bán theo tỉnh
            raise PreventUpdate
        k = _ky(tu_iso, den_iso)
        ky = k
        if ky is None:
            trong = _fig(_trong(go.Figure()))
            return ([], "", alert("Chưa có số liệu. Nạp file Internet để bắt đầu.", "warn"), "",
                    [], [], "", [], [], [], trong, trong, trong, trong)
        thang, tu, den = k.thang, k.tu, k.den
        nguong = _nguong()
        scope = loc_chi_nhanh(current_user.phong_duoc_xem(), chi_nhanh, thang)
        df = pt.hop_dong_online(tu, den, scope)
        truoc = pt.chi_so_chung(pt.hop_dong_online(*k.ck, scope))
        ton = pt.hop_dong_ton(scope)
        nay = pt.chi_so_chung(df)
        chung_kd = pt.muc_chung_kinh_doanh(df, thang)

        pham_vi = TEN_PHAM_VI.get(chi_nhanh, TEN_PHAM_VI["all"])
        badge = html.Span(f"{k.nhan} · {pham_vi}", className="badge muted", title=f"So với {k.ten_ck_day}")
        kpis = _kpis(nay, truoc, ton, k.ten_ck)

        bang = pt.bang_theo_phong(df, ton, thang, TEN_DONG_TONG.get(chi_nhanh, TEN_DONG_TONG["all"]))
        if nhom == "kd":
            bang = bang[(bang.loai_dong != "data") | (bang.nhom_kd == True)]  # noqa: E712
            bay_kd = {f"SUB_{p['bay']}" for p in phong_order(thang)
                      if p.get("loai") in pt.LOAI_KINH_DOANH}
            bang = bang[(bang.loai_dong != "subtotal") | bang.phong_code.isin(bay_kd)]
        mo_ta = f"{nay['online']:,} hợp đồng online {k.nhan} · {pham_vi}".replace(",", ".")
        chu_giai = html.Span([
            html.Span("■ ", style={"color": "#5CBF7A"}), f"Cao hơn mức chung từ {nguong['tot']} điểm   ",
            html.Span("■ ", style={"color": "#F5B942"}), f"Thấp hơn {nguong['tot']}-{nguong['kem']} điểm   ",
            html.Span("■ ", style={"color": "#E57373"}), f"Thấp hơn từ {nguong['kem']} điểm. ",
            html.Span(
                f"Mức chung các phòng kinh doanh: kèm V.VIP {chung_kd['kem_vvip'] or 0:.0f}%, kèm "
                f"Camera {chung_kd['kem_camera'] or 0:.0f}%, đủ 3 DV {chung_kd['du_3'] or 0:.0f}%, "
                f"online trong 1 ngày {chung_kd['onl_1_ngay'] or 0:.0f}%. Phòng KT, CUS, ECOM chữ nhạt, "
                "không tô màu.") if chung_kd["online"] else ""])

        ton_phong = pt.ton_theo_tuoi(ton, thang)
        tong_ton = ton_phong[ton_phong.loai_dong == "total"].to_dict("records") if len(ton_phong) else []
        ton_data = ton_phong[ton_phong.loai_dong == "data"] if len(ton_phong) else ton_phong
        lau = int((ton.so_ngay_cho > 30).sum()) if len(ton) else 0
        so = lambda n: f"{n:,}".replace(",", ".")                                   # noqa: E731
        mo_ta_ton = (f"{so(len(ton))} hợp đồng chưa online, còn trong file mới nhất · {so(lau)} hợp đồng "
                     "chờ trên 30 ngày (thường là khách đã bỏ, cần rà soát)")

        tu_4t = (pd.Timestamp(den) - pd.Timedelta(days=27)).date().isoformat()
        nhip = pt.nhip_theo_thu(pt.hop_dong_online(tu_4t, den, scope), tu_4t, den)
        kd = {p["code"] for p in phong_order(thang) if p.get("loai") in pt.LOAI_KINH_DOANH}

        return (kpis, badge, mo_ta, chu_giai,
                _cot_phong(chung_kd, nguong,
                           bang[(bang.loai_dong == "data") & (bang.nhom_kd == True)].ton_qua_7),  # noqa: E712
                bang.to_dict("records"), mo_ta_ton,
                _cot_ton(), ton_data.to_dict("records") if len(ton_data) else [], tong_ton,
                _bd_kem_goi(pt.kem_theo_goi(df)), _bd_toc_do(pt.toc_do_online(df)),
                _bd_co_cau(pt.co_cau_goi_theo_phong(df[df.phong_code.isin(kd)], thang)),
                _bd_nhip(nhip))

    @app.callback(Output("pt-ton-ds", "columnDefs"), Output("pt-ton-ds", "rowData"),
                  Input("pt-khoang", "end_date"), Input("pt-cn", "value"),
                  Input("pt-ton-phong-loc", "value"), Input("pt-ton-xem", "value"))
    def _ton_ds(den_iso, chi_nhanh, phong_loc, xem):
        ky = _ky(None, den_iso)
        if xem != "ds" or ky is None or not current_user.duoc_xem_nhan_su or current_user.role == "nvkd":
            return COT_DS_TON, []
        thang = ky.thang
        scope = loc_chi_nhanh(current_user.phong_duoc_xem(), chi_nhanh, thang)
        ds = _ds_ton(pt.hop_dong_ton(scope), thang, loc_nhan_su(scope, current_user.phong_nhan_su()),
                     phong_loc)
        return COT_DS_TON, ds[["hop_dong", "ho_ten", "acc_nhan_vien", "acc_norm", "phong_code", "phong",
                               "goi_dich_vu", "nguon_ban", "ngay_tao", "so_ngay_cho"]].to_dict("records")

    @app.callback(Output("pt-nv", "columnDefs"), Output("pt-nv", "rowData"),
                  Output("pt-mo-ta-nv", "children"),
                  Input("pt-khoang", "start_date"), Input("pt-khoang", "end_date"), Input("pt-cn", "value"),
                  Input("pt-nv-phong", "value"), Input("pt-nv-loc", "value"))
    def _nv(tu_iso, den_iso, chi_nhanh, phong_loc, loc):
        ky = _ky(tu_iso, den_iso)
        if ky is None or not current_user.duoc_xem_nhan_su or current_user.role == "nvkd":
            return [], [], ""
        thang, tu, den = ky.thang, ky.tu, ky.den
        scope = loc_chi_nhanh(current_user.phong_duoc_xem(), chi_nhanh, thang)
        df = pt.hop_dong_online(tu, den, scope)
        nv = _nhan_vien(df, pt.hop_dong_ton(scope), thang,
                        loc_nhan_su(scope, current_user.phong_nhan_su()), phong_loc, loc)
        mo_ta = f"{len(nv)} nhân viên" + ("" if current_user.phong_nhan_su() is None
                                         else " · trong phòng bạn phụ trách")
        return (_cot_nv(pt.muc_chung_kinh_doanh(df, thang), _nguong()),
                [] if nv.empty else nv.to_dict("records"), mo_ta)

    def _ngu_canh(nguoi, *gia_tri):
        if nguoi.role == "nvkd":
            raise ai.LoiAI("Trang này không có nhận xét.")
        return dl.ngu_canh_phan_tich(nguoi, *gia_tri)

    tl.gan_nhan_xet(app, "pt", "phan_tich", [("pt-khoang", "end_date"), ("pt-cn", "value"),
                                             ("pt-khoang", "start_date")], _ngu_canh,
                    dl.YEU_CAU_PHAN_TICH)

    @app.callback(Output("pt-du-bao", "children"), Input("pt-khoang", "end_date"), Input("pt-cn", "value"))
    def _du_bao(den_iso, chi_nhanh):
        ky = _ky(None, den_iso)
        if ky is None or current_user.role == "nvkd":
            return ""
        thang, ngay = ky.thang, ky.ngay
        db = du_bao_thang(thang, ngay, loc_chi_nhanh(current_user.phong_duoc_xem(), chi_nhanh, thang))
        return tl.dong_du_bao(db[db.phong_code == "TOTAL"].iloc[0].to_dict(), TEN_PHAM_VI.get(chi_nhanh or "all"),
                              db.attrs.get("tuan"), db.attrs.get("nhip"))

    @app.callback(Output("pt-tai-xuong", "data"), Input("pt-xls", "n_clicks"),
                  State("pt-khoang", "start_date"), State("pt-khoang", "end_date"), State("pt-cn", "value"),
                  prevent_initial_call=True)
    def _excel(_n, tu_iso, den_iso, chi_nhanh):
        ky = _ky(tu_iso, den_iso)
        if ky is None or current_user.role == "nvkd":
            return no_update
        thang, ngay, tu, den = ky.thang, ky.ngay, ky.tu, ky.den
        scope = loc_chi_nhanh(current_user.phong_duoc_xem(), chi_nhanh, thang)
        df = pt.hop_dong_online(tu, den, scope)
        ton = pt.hop_dong_ton(scope)
        pham_vi = TEN_PHAM_VI.get(chi_nhanh, TEN_PHAM_VI["all"])
        bang = pt.bang_theo_phong(df, ton, thang, TEN_DONG_TONG.get(chi_nhanh, TEN_DONG_TONG["all"]))
        cot_phong = [("phong", "Phòng", "text"), ("online", "Online", "so"),
                     ("kem_vvip", "HĐ kèm V.VIP", "pct"), ("kem_camera", "HĐ kèm Camera", "pct"),
                     ("du_3", "Đủ 3 DV", "pct"), ("tra_truoc", "Trả trước", "pct"),
                     ("onl_1_ngay", "Online trong 1 ngày", "pct"), ("ngoai_tinh", "Ngoại tỉnh", "pct"),
                     ("ton", "Chưa online", "so"), ("ton_qua_7", "Chờ từ 7 ngày", "so")]
        cot_ton = [("phong", "Phòng", "text"), ("tong", "Tổng tồn", "so")] + [
            (f"m{i}", nhan, "so") for i, (_, _, nhan) in enumerate(pt.MOC_TON)] + [
            ("tb_ngay", "Chờ bình quân (ngày)", "so")]
        bang_xuat = [("Theo phòng", bang, cot_phong),
                     ("Số tồn theo phòng", pt.ton_theo_tuoi(ton, thang), cot_ton)]
        if current_user.duoc_xem_nhan_su:
            pham_vi_nv = loc_nhan_su(scope, current_user.phong_nhan_su())
            ds = _ds_ton(ton, thang, pham_vi_nv, "all")
            nv = _nhan_vien(df, ton, thang, pham_vi_nv, "all", "all")
            bang_xuat += [
                ("HĐ chờ từ 7 ngày", ds, [("hop_dong", "Hợp đồng", "text"), ("ho_ten", "Nhân viên", "text"),
                                          ("acc_nhan_vien", "Acc", "text"), ("phong", "Phòng", "text"),
                                          ("goi_dich_vu", "Gói", "text"), ("nguon_ban", "Nguồn bán", "text"),
                                          ("ngay_tao", "Ngày tạo HĐ", "text"),
                                          ("so_ngay_cho", "Số ngày chờ", "so")]),
                ("Theo nhân viên", nv, [("ho_ten", "Nhân viên", "text"), ("acc", "Acc", "text"),
                                        ("phong", "Phòng", "text"), ("online", "Online", "so"),
                                        ("kem_vvip", "HĐ kèm V.VIP", "pct"),
                                        ("kem_camera", "HĐ kèm Camera", "pct"), ("du_3_tl", "Đủ 3 DV", "pct"),
                                        ("tra_truoc_tl", "Trả trước", "pct"),
                                        ("onl_1_ngay", "Online trong 1 ngày", "pct"),
                                        ("ton", "Chưa online", "so"), ("ton_qua_7", "Chờ từ 7 ngày", "so")]),
            ]
        tieu_de = f"PHÂN TÍCH BÁN HÀNG · {pham_vi.upper()} · {ky.nhan}"
        noi_dung = xuat_phan_tich("", tieu_de, bang_xuat)
        ghi_log("xuat_phan_tich", f"{chi_nhanh} {tu} - {den}")
        ten = (f"PhanTich_{thang.replace('-', '')}_ngay{ngay:02d}" if ky.luy_ke
               else f"PhanTich_{tu.replace('-', '')}-{den.replace('-', '')}")
        return dcc.send_bytes(noi_dung, f"{ten}.xlsx")

    from app.ui.pages import phantich_tinh
    phantich_tinh.register(app)
