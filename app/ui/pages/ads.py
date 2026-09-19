"""Trang Ads IBB7 (chỉ Quản trị): chi tiêu quảng cáo Facebook, lead / PTTB, chia chi phí cho sale.

Năm tab, đi từ tổng thể tới chi tiết: Tổng quan (lọc khoảng ngày / sale / đánh giá, số chính, dữ liệu cần kiểm tra,
điểm cần chú ý, bảng page, biểu đồ theo ngày) · Nhận định (nhóm hiệu quả, xu hướng 7 ngày, phễu tin nhắn → số → PTTB)
· Theo sale (bấm đúp xem page từng sale) · Theo ngày (Tracking page × ngày, bấm đúp xem chi tiết page) · Cấu hình.
Số liệu và quy tắc ở app/ads.py.
"""
from __future__ import annotations

import base64
import json
import time
from datetime import date, timedelta

import dash_ag_grid as dag
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate
from flask_login import current_user

from app import ads
from app.auth import ghi_log
from app.metrics import month_range
from app.thoi_gian import gio_viet_nam
from app.ui.components import (LOCALE_VI, alert, callback_can_quyen, chon_ky, field, gan_dieu_huong_ky, kpi,
                               modal, seg_control, so_vn, tieu_de, tip)
from app.ui.icons import icon

AN = {"display": "none"}
TAB = [("tong", "Tổng quan"), ("nhan_dinh", "Nhận định"), ("sale", "Theo sale"), ("ngay", "Theo ngày"),
       ("cauhinh", "Cấu hình")]
HUONG_DAN_TAB = [
    ("Tổng quan", "số chính, điểm cần chú ý và hiệu quả từng page; lọc theo khoảng ngày (cả tháng / 7 ngày / ngày "
                  "gần nhất), theo sale, theo đánh giá. Bấm đúp một page để xem chi tiết."),
    ("Nhận định", "page nào hiệu quả / đốt tiền, đang tốt lên hay xấu đi, kẹt ở khâu nào (tin nhắn → số → PTTB)."),
    ("Theo sale", "mỗi sale chạy bao nhiêu page, đã chi bao nhiêu ($ và VNĐ), dự kiến chi tới hết tháng. Bấm đúp "
                  "một sale để xem từng page."),
    ("Theo ngày", "Tracking ngày: page × ngày. Bấm đúp một page để xem từng camp từng ngày (như trang tính cũ)."),
    ("Cấu hình", "kết nối n8n, người chạy page, tên page, tên sale ↔ acc, nhập tay, nhật ký lead."),
]
USD = {"function": "params.value == null ? '' : Number(params.value).toLocaleString('vi-VN', "
                   "{minimumFractionDigits: 2, maximumFractionDigits: 2})"}
SO = {"function": "params.value == null ? '' : Number(params.value).toLocaleString('vi-VN', "
                  "{maximumFractionDigits: 1})"}
VND = {"function": "params.value == null ? '' : Math.round(params.value).toLocaleString('vi-VN')"}
USD_D = {"function": "params.value == null ? '' : Number(params.value).toLocaleString('vi-VN', "
                     "{minimumFractionDigits: 2, maximumFractionDigits: 2}) + ' $'"}
PCT = {"function": "params.value == null ? '' : Math.round(params.value) + '%'"}
PCT_DAU = {"function": "params.value == null ? '' : (params.value > 0 ? '+' : '') + Math.round(params.value) + '%'"}
# 3 màu: xanh tốt · vàng trung bình · đỏ cần xử lý
XANH, VANG, DO = ("#DDF1E3", "#14532D"), ("#FFF3D1", "#6B5104"), ("#FCE1DD", "#93241C")
LAM = ("#EAF3FC", "#D0E4F7", "#A8CBEE")          # chi tiêu: nhiều / ít, không tốt không xấu


def _o(nen, chu=None, dam=False):
    s = {"backgroundColor": nen}
    if chu:
        s["color"] = chu
    if dam:
        s["fontWeight"] = "700"
    return s


MAU_CP = {"styleConditions": [
    {"condition": "params.value == null", "style": {}},
    {"condition": f"params.value <= {ads.NGUONG_TOT}", "style": _o(*XANH)},
    {"condition": f"params.value <= {ads.NGUONG_BINH_THUONG}", "style": _o(*VANG)},
    {"condition": "true", "style": _o(*DO, dam=True)}]}
MAU_DANH_GIA = {"styleConditions": [
    {"condition": "params.value == 'Tốt'", "style": _o(*XANH, dam=True)},
    {"condition": "params.value == 'Trung bình'", "style": _o(*VANG)},
    {"condition": "params.value == 'Kém'", "style": _o(*DO, dam=True)}]}
DANH_GIA_LOC = ["Tốt", "Trung bình", "Kém", "Chưa đủ số"]
KHOANG = [("thang", "Cả tháng"), ("7", "7 ngày gần nhất"), ("1", "Ngày gần nhất")]
BIEU_DO = [("chi", "Chi tiêu & PTTB"), ("cp", "Chi phí / PTTB"), ("pheu", "Tin nhắn · Số ĐT · PTTB")]
THU = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]
MAU_NHOM = {"styleConditions": [
    {"condition": "params.value == 'Hiệu quả cao'", "style": _o(*XANH, dam=True)},
    {"condition": "params.value == 'Trung bình'", "style": _o(*VANG)},
    {"condition": "params.value == 'Kém'", "style": _o(*DO, dam=True)}]}
MAU_DOI = {"styleConditions": [                       # % đổi chi phí/PTTB: giảm là tốt
    {"condition": "params.value == null", "style": {}},
    {"condition": "params.value <= -15", "style": _o(*XANH)},
    {"condition": "params.value < 15", "style": {}},
    {"condition": "params.value < 50", "style": _o(*VANG)},
    {"condition": "true", "style": _o(*DO, dam=True)}]}
MAU_TT = {"styleConditions": [
    {"condition": "params.value == 'HOẠT ĐỘNG'", "style": {"color": "#04843F", "fontWeight": "700"}},
    {"condition": "params.value == 'TẮT'", "style": {"color": "#B42318"}}]}
MAU_VAN_DE = {"styleConditions": [{"condition": "params.value", "style": _o(*VANG)}]}
HUONG_CHI_SO = {"chi_tieu": "trung_tinh", "tin_nhan": "cao_tot", "lead": "cao_tot", "pttb": "cao_tot",
                "cp_pttb": "thap_tot"}
CHU_MAU = {
    "cao_tot": [(DO[0], "thấp"), (VANG[0], "trung bình"), (XANH[0], "cao")],
    "trung_tinh": [(LAM[0], "ít"), (LAM[1], "vừa"), (LAM[2], "nhiều")],
    "thap_tot": [(XANH[0], f"≤ {ads.NGUONG_TOT:.0f}$ tốt"), (VANG[0], f"≤ {ads.NGUONG_BINH_THUONG:.0f}$"),
                 (DO[0], f"> {ads.NGUONG_BINH_THUONG:.0f}$ cao")],
}


def _mau_nhiet(gia_tri, huong: str) -> dict:
    """Tô 3 mức cho bảng page × ngày. Ngưỡng = 1/3 và 2/3 các ô có số (bỏ ô trống / 0)."""
    if huong == "thap_tot":
        return MAU_CP
    v = np.array([x for x in gia_tri if x is not None and x == x and x > 0], dtype=float)
    if len(v) < 3:
        return {}
    a, b = np.quantile(v, [1 / 3, 2 / 3])
    if huong == "trung_tinh":
        m1, m2, m3 = _o(LAM[0]), _o(LAM[1]), _o(LAM[2], "#0C3B66", True)
    else:
        m1, m2, m3 = _o(*DO), _o(*VANG), _o(*XANH, dam=True)
    return {"styleConditions": [
        {"condition": "!params.value", "style": {}},
        {"condition": f"params.value <= {a}", "style": m1},
        {"condition": f"params.value <= {b}", "style": m2},
        {"condition": "true", "style": m3}]}


def _chu_mau(huong: str):
    return html.Div([html.Span("Màu:")] + [html.Span([html.I(style={"background": m}), t])
                                           for m, t in CHU_MAU[huong]], className="chu-mau")


def _grid(id_, cot, cao=440, **kw):
    """Bảng cao cố định, nhiều dòng thì cuộn trong khung (không kéo dài trang)."""
    opts = {"localeText": LOCALE_VI, "suppressCellFocus": False, "enableCellTextSelection": True,
            "ensureDomOrder": True, "tooltipShowDelay": 300, **kw.pop("opts", {})}
    return dag.AgGrid(id=id_, className="ag-theme-quartz ag-theme-ftel luoi-ke", columnDefs=cot, rowData=[],
                      defaultColDef={"resizable": True, "sortable": True, "filter": True},
                      dashGridOptions=opts, style={"height": f"{cao}px"}, **kw)


def _so(label, field_, fmt=SO, w=100, **kw):
    return {"field": field_, "headerName": label, "type": "numericColumn", "minWidth": w, "flex": 1,
            "valueFormatter": fmt, **kw}


CHON_1_DONG = {"rowSelection": {"mode": "singleRow", "checkboxes": False, "enableClickSelection": True}}
COT_PAGE = {"field": "ten", "headerName": "Page", "pinned": "left", "minWidth": 200, "flex": 2,
            "tooltipField": "ten"}
COT_LINK = {"field": "link_md", "headerName": "", "width": 60, "cellRenderer": "markdown", "linkTarget": "_blank",
            "sortable": False, "filter": False, "headerTooltip": "Mở fanpage (khai link ở Theo ngày → Sửa page)"}


def _thang_co() -> list[str]:
    try:
        df = ads._q("SELECT DISTINCT substr(CAST(ngay AS TEXT), 1, 7) AS t FROM ads_ngay "
                    "UNION SELECT DISTINCT substr(CAST(ngay AS TEXT), 1, 7) FROM ads_lead")
        ds = set(df.t.dropna())
    except Exception:
        ds = set()
    ds.add(gio_viet_nam().strftime("%Y-%m"))
    return sorted(ds, reverse=True)


def topbar():
    return [html.Div([html.H1("Ads IBB7"),
                      html.Div("Chi tiêu quảng cáo Facebook, lead / PTTB từng page và chi phí từng sale",
                               className="sub")]),
            html.Div(className="spacer"), html.Div(id="ads-badge")]


def _the(tieu, mo_ta, *con, nut=None, **kw):
    return html.Div([html.Div([html.Div([tieu_de(tieu, mo_ta)], className="the-ten"),
                               html.Div(nut, className="the-nut") if nut is not None else None], className="the-dau"),
                     *con], className="card", **kw)


def _huong_dan_tab():
    return tip(html.Div([html.Div([html.B(t + ": "), m]) for t, m in HUONG_DAN_TAB]
                        + [html.Div(["Đánh giá page theo ", html.B("chi phí / PTTB"), f" (USD): ≤ {ads.NGUONG_TOT:.0f} "
                                     f"tốt · ≤ {ads.NGUONG_BINH_THUONG:.0f} bình thường · còn lại cao. Chi tiêu về "
                                     "app lúc 7h sáng hôm sau; lead / PTTB về ngay khi báo qua bot Telegram."],
                                    style={"marginTop": "6px"})]))


def layout(tab: str | None = None):
    if not current_user.duoc_cau_hinh:
        return alert("Chỉ tài khoản Quản trị được xem mục Ads IBB7.", "bad")
    ads.dam_bao_bang()
    thangs = _thang_co()
    tab = tab if tab in dict(TAB) else "tong"
    return html.Div([
        html.Div([
            field("Tháng", chon_ky("ads-thang", thangs, thangs[0])),
            field("Xem", seg_control("ads-tab", TAB, tab)),
            html.Div([_huong_dan_tab(), html.Span("Mỗi mục xem gì?", className="ghi-chu-nhan")],
                     className="ghi-chu ads-tab-tip"),
        ], className="toolbar loc-trang"),
        dcc.Store(id="ads-sua"),                    # tín hiệu: vừa lưu cấu hình -> nạp lại số
        dcc.Store(id="ads-ct-page"),
        _modal_ct(),
        _modal_page(),
        _modal_sale(),

        # ---------------- Tổng quan
        html.Div(id="ads-p-tong", children=[
            html.Div([
                field("Khoảng ngày", seg_control("ads-khoang", KHOANG, "thang")),
                field("Loại page", seg_control("ads-loc-loai", [("all", "Tất cả"), ("sale", "Page sale"),
                                                         ("cong_ty", "Trung lập")], "all")),
                field("Sale", dcc.Dropdown(id="ads-loc-sale", placeholder="Tất cả sale", style={"minWidth": "170px"})),
                field("Đánh giá", dcc.Dropdown(id="ads-loc-dg", multi=True, placeholder="Tất cả",
                                               options=[{"label": x, "value": x} for x in DANH_GIA_LOC],
                                               style={"minWidth": "200px"})),
                html.Div([tip("Khoảng ngày tính tới ngày đã có chi tiêu (chi tiêu về lúc 7h sáng hôm sau), so với "
                              "khoảng liền trước cùng độ dài; Cả tháng so với cùng kỳ tháng trước. Lọc theo sale = "
                              "các page sale đó chạy trong khoảng, số là của cả page (không chia). Trung lập = page chạy tài khoản công ty "
                              "(không chia cho sale). Tab Nhận định, Theo "
                              "sale, Theo ngày luôn xem cả tháng."),
                          html.Span(id="ads-ky-chu", className="ghi-chu-nhan")], className="ghi-chu ads-tab-tip"),
            ], className="toolbar loc-trang", style={"flexWrap": "wrap"}),
            dcc.Loading(html.Div(id="ads-kpi", className="kpi-row kpi-7"), type="dot"),
            html.Div(id="ads-kiem-tra"),
            _the("Điểm cần chú ý", "Tự rút ra từ số liệu tháng đang chọn (tính tới ngày đã có chi tiêu). Xem đầy đủ "
                 "ở tab Nhận định.", html.Div(id="ads-tq-the", className="nd-luoi"),
                 nut=html.Button("Xem tất cả nhận định →", id="ads-sang-nd", className="btn")),
            _the("Hiệu quả từng page", f"Bấm đúp vào một page để xem chi tiết từng ngày. Chi phí / PTTB: xanh ≤ "
                 f"{ads.NGUONG_TOT:.0f}$, vàng ≤ {ads.NGUONG_BINH_THUONG:.0f}$, đỏ cao hơn. Cùng kỳ = cùng khoảng "
                 "ngày tháng trước.",
                 _grid("ads-g-page", [
                     COT_PAGE, COT_LINK,
                     {"field": "pic", "headerName": "Sale chạy", "minWidth": 150, "flex": 1.4, "tooltipField": "pic"},
                     _so("Chi tiêu ($)", "chi_tieu", USD, 105),
                     _so("Ngày chạy", "so_ngay", SO, 85, headerTooltip="Số ngày có chi tiêu trong khoảng"),
                     _so("TB/ngày ($)", "tb_ngay", USD, 95, headerTooltip="Chi tiêu / số ngày chạy"),
                     _so("Tin nhắn", "tin_nhan", SO, 85),
                     _so("Số ĐT", "lead", SO, 75, headerTooltip="Lead = số điện thoại xin được"),
                     _so("PTTB", "pttb", SO, 70),
                     _so("CP/số ĐT", "cpl", USD, 90, headerTooltip="Chi tiêu / số điện thoại (USD), tính tới ngày "
                                                                  "đã có chi tiêu"),
                     _so("CP/PTTB", "cp_pttb", USD, 90, headerTooltip="Chi tiêu / PTTB (USD) - chỉ số chính, tính tới "
                                                                      "ngày đã có chi tiêu", cellStyle=MAU_CP),
                     _so("Tỷ lệ chốt", "ty_le_chot", PCT, 90, headerTooltip="PTTB / số điện thoại"),
                     {"field": "danh_gia", "headerName": "Đánh giá", "minWidth": 115, "cellStyle": MAU_DANH_GIA},
                     _so("PTTB kỳ trước", "ck_pttb", SO, 100, headerTooltip="Khoảng so sánh ghi ở thanh lọc"),
                     _so("CP/PTTB kỳ trước", "ck_cp", USD, 115, cellStyle=MAU_CP),
                 ], cao=460, opts=CHON_1_DONG)),
            _the("Diễn biến từng ngày", "Chi tiêu & PTTB: cột xanh là tiền (trục trái), đường cam là PTTB (trục phải). "
                 "Chi phí / PTTB: cột màu từng ngày, đường đen là trung bình 7 ngày gần nhất (đỡ nhiễu hơn từng ngày). "
                 "Vẽ tới ngày đã có chi tiêu.",
                 html.Div(id="ads-bd-chu", className="ghi-chu-nhan"),
                 dcc.Graph(id="ads-bieu-do", config={"displayModeBar": False}),
                 nut=seg_control("ads-bd-kieu", BIEU_DO, "chi")),
        ]),

        # ---------------- Nhận định
        html.Div(id="ads-p-nhan_dinh", style=AN, children=[
            _the("Nhận định", "Rút ra tự động từ số liệu: đỏ = cần xử lý ngay, vàng = theo dõi, xanh dương = gợi ý, "
                 "xanh lá = đang tốt. Tính tới ngày đã có chi tiêu để tiền và PTTB cùng khoảng.",
                 html.Div(id="ads-nd-the", className="nd-luoi"), nut=html.Div(id="ads-nd-den")),
            html.Div([
                _the("Chi phí / PTTB từng page", f"Thanh càng dài càng đắt. Xanh ≤ {ads.NGUONG_TOT:.0f}$, vàng ≤ "
                     f"{ads.NGUONG_BINH_THUONG:.0f}$, đỏ cao hơn; xám = chưa có PTTB (độ dài = số tiền đã tiêu). Chữ "
                     "bên phải là số tiền page đã tiêu trong tháng.",
                     dcc.Graph(id="ads-nd-ma-tran", config={"displayModeBar": False})),
                html.Div([
                    _the("Tiền bỏ ra và PTTB thu về", "Chia các page thành 4 nhóm theo chi phí/PTTB (xanh ≤ 6$, "
                         "vàng 6-10$, đỏ > 10$ hoặc tiêu từ 10$ mà chưa có PTTB, xám = mới chạy, chưa đủ số). Thanh "
                         "trên: mỗi nhóm tiêu bao nhiêu % tổng tiền. Thanh dưới: mỗi nhóm mang về bao nhiêu % tổng "
                         "PTTB. Nhóm đỏ chiếm phần tiền lớn hơn phần PTTB là đang tốn tiền kém hiệu quả.",
                         html.Div(id="ads-nd-nhom-chu", className="nd-viec"),
                         dcc.Graph(id="ads-nd-nhom", config={"displayModeBar": False})),
                    _the("Phễu tin nhắn → số điện thoại → PTTB", "Bao nhiêu tin nhắn thành số điện thoại, bao nhiêu "
                         "số thành PTTB. Chọn page để so với mức chung.",
                         dcc.Graph(id="ads-nd-pheu-bd", config={"displayModeBar": False}),
                         nut=dcc.Dropdown(id="ads-pheu-page", placeholder="Tất cả page", style={"minWidth": "200px"})),
                ], style={"display": "flex", "flexDirection": "column", "gap": "16px", "minWidth": 0}),
            ], className="hai-cot"),
            _the("Xu hướng 7 ngày", "Chi phí/PTTB 7 ngày gần nhất so với 7 ngày trước đó. Tăng mạnh thường là quảng "
                 "cáo đã mỏi (chạy lâu, tệp khách bão hoà) - nên đổi nội dung. Chỉ tính page tiêu từ 5$.",
                 _grid("ads-nd-xu", [
                     COT_PAGE,
                     _so("CP/PTTB 7 ngày trước", "cp_truoc", USD, 120, cellStyle=MAU_CP),
                     _so("CP/PTTB 7 ngày gần nhất", "cp_nay", USD, 130, cellStyle=MAU_CP),
                     _so("Thay đổi", "doi_cp", PCT_DAU, 95, cellStyle=MAU_DOI,
                         headerTooltip="Âm là tốt lên (rẻ hơn)"),
                     _so("PTTB trước", "pttb_truoc", SO, 90), _so("PTTB gần nhất", "pttb_nay", SO, 100),
                     _so("Chi 7 ngày gần nhất ($)", "chi_tieu_nay", USD, 130),
                 ], cao=380)),
            _the("Phễu từng page", "Tìm page kẹt ở khâu nào: nhiều tin nhắn mà ít xin được số "
                 "(xem lại kịch bản chat, tốc độ trả lời) hay có số mà chốt ít (sale gọi lại chậm, tư vấn chưa tới). "
                 "Đánh dấu khi thấp hơn một nửa mức chung.",
                 _grid("ads-nd-pheu", [
                     COT_PAGE, _so("Tin nhắn", "tin_nhan", SO, 85), _so("Số ĐT", "lead", SO, 75),
                     _so("% ra số", "tl_so", PCT, 85, headerTooltip="Số điện thoại / tin nhắn"),
                     _so("PTTB", "pttb", SO, 70),
                     _so("% chốt", "tl_chot", PCT, 85, headerTooltip="PTTB / số điện thoại"),
                     {"field": "van_de", "headerName": "Điểm nghẽn", "minWidth": 210, "flex": 1.6,
                      "cellStyle": MAU_VAN_DE},
                 ], cao=380), nut=html.Div(id="ads-nd-muc-chung", className="ghi-chu-nhan")),
        ]),

        # ---------------- Theo sale
        html.Div(id="ads-p-sale", style=AN, children=[
            _the("Chi phí từng sale", "Bấm đúp một sale để xem từng page sale đó được chia bao nhiêu. Chi tiêu mỗi "
                 "page mỗi ngày chia cho các sale chạy page ngày đó (đều nhau, hoặc theo tỷ lệ đã khai). Dự kiến hết tháng = đã chi + trung bình mỗi ngày của 5 ngày gần nhất có "
                 "số chi tiêu × số ngày còn lại của tháng. VNĐ đổi theo tỷ giá tháng ở ô bên phải.",
                 html.Div(id="ads-sale-mo-ta", className="ghi-chu-nhan", style={"margin": "0 0 8px"}),
                 _grid("ads-g-sale", [
                     {"field": "sale", "headerName": "Sale", "pinned": "left", "minWidth": 150, "flex": 1.4},
                     _so("Số page", "so_page", SO, 85),
                     _so("Đã chi ($)", "chi_tieu", USD_D, 115), _so("Đã chi ≈ VNĐ", "vnd", VND, 130),
                     _so("TB/ngày 5 ngày gần nhất", "tb_5_ngay", USD_D, 150,
                         headerTooltip="Trung bình tiền chạy mỗi ngày trong 5 ngày gần nhất có số chi tiêu"),
                     _so("Dự kiến hết tháng ($)", "du_kien", USD_D, 150, cellStyle={"fontWeight": "700"}),
                     _so("Dự kiến ≈ VNĐ", "du_kien_vnd", VND, 140, cellStyle={"fontWeight": "700"}),
                     {"field": "ghi_chu", "headerName": "Ghi chú", "minWidth": 160, "flex": 1.2,
                      "tooltipField": "ghi_chu"},
                 ], cao=460, opts={"pinnedBottomRowData": [], **CHON_1_DONG}),
                 html.Div(id="ads-msg-ty-gia"),
                 nut=html.Div([
                     html.Span("Tỷ giá USD → VNĐ", className="ghi-chu-nhan", style={"marginRight": "6px"}),
                     dcc.Input(id="ads-ty-gia", type="number", min=1000, step=1, className="inp",
                               style={"width": "110px"}),
                     html.Button([icon("save", 14), html.Span("Lưu tỷ giá")], id="ads-luu-ty-gia", className="btn")],
                     style={"display": "flex", "alignItems": "center", "gap": "8px"})),
        ]),

        # ---------------- Theo ngày
        html.Div(id="ads-p-ngay", style=AN, children=[
            _the("Tracking ngày", "Mỗi dòng một page, mỗi cột một ngày; màu cho thấy ngày nào nhiều / ít. Tổng VNĐ "
                 "đổi theo tỷ giá tháng (tab Theo sale). Bấm đúp vào một page để xem từng camp từng ngày.",
                 _grid("ads-g-ngay", [], cao=400, opts=CHON_1_DONG),
                 html.Div(id="ads-chu-mau"),
                 nut=seg_control("ads-chi-so", [("chi_tieu", "Chi tiêu"), ("tin_nhan", "Tin nhắn"),
                                                ("lead", "Số ĐT"), ("pttb", "PTTB"), ("cp_pttb", "CP/PTTB")],
                                 "chi_tieu")),
        ]),

        html.Div(id="ads-p-cauhinh", style=AN, children=_cau_hinh()),
    ])


def _modal_ct():
    """Cửa sổ chi tiết một page (mở bằng bấm đúp ở Tổng quan / Tracking ngày) - như trang tính từng page của sheet."""
    return html.Div([
        html.Div(className="modal-nen", id="ads-md-ct-nen"),
        html.Div([
            html.Div([html.H3(id="ads-md-ct-tieu-de"), tip("Mỗi dòng một camp một ngày, ngày tăng dần. Số điện thoại / "
                                                           "PTTB báo qua bot ghi ở dòng đầu của ngày. Tiền/người = chi "
                                                           "tiêu chia cho người chạy (theo tỷ lệ nếu có)."),
                      html.Div(className="grow"),
                      html.Button([icon("settings", 14), html.Span("Sửa tên / link")], id="ads-ct-sua", className="btn"),
                      html.Button("×", id="ads-md-ct-dong", className="modal-x", title="Đóng")], className="modal-dau"),
            html.Div([html.Div(id="ads-ct-dau", className="ct-dau"),
                      _grid("ads-g-ct", [], cao=520, opts={"pinnedBottomRowData": []})], className="modal-than",
                     style={"paddingBottom": "16px"}),
        ], className="modal-hop modal-rong"),
    ], id="ads-md-ct", className="modal")


def _modal_sale():
    """Cửa sổ các page của một sale (bấm đúp ở tab Theo sale)."""
    return html.Div([
        html.Div(className="modal-nen", id="ads-md-sale-nen"),
        html.Div([
            html.Div([html.H3(id="ads-md-sale-tieu-de"),
                      tip("Tiền được chia = phần chi tiêu của sale ở page đó (chia đều cho người chạy cùng ngày, hoặc "
                          "theo tỷ lệ đã khai). Phần của sale = tiền được chia / tổng tiền page trong tháng."),
                      html.Div(className="grow"),
                      html.Button("×", id="ads-md-sale-dong", className="modal-x", title="Đóng")], className="modal-dau"),
            html.Div(_grid("ads-g-ct-sale", [
                COT_PAGE,
                _so("Ngày chạy", "so_ngay", SO, 85), {"field": "khoang", "headerName": "Từ - đến", "width": 110},
                _so("Tiền được chia ($)", "chi_tieu", USD_D, 130), _so("≈ VNĐ", "vnd", VND, 120),
                _so("Phần của sale", "phan", PCT, 105),
                {"field": "cung", "headerName": "Chạy cùng", "minWidth": 160, "flex": 1.2, "tooltipField": "cung"},
            ], cao=380, opts={"pinnedBottomRowData": []}), className="modal-than", style={"paddingBottom": "16px"}),
        ], className="modal-hop modal-rong"),
    ], id="ads-md-sale", className="modal")


def _modal_page():
    return modal("ads-md-page", html.Span("Sửa page", id="ads-md-tieu-de"), [
        dcc.Store(id="ads-md-id"),
        html.Div([
            field("Tên hiển thị", dcc.Input(id="ads-md-ten", className="inp", style={"width": "100%"})),
            field("Link fanpage", dcc.Input(id="ads-md-link", className="inp", style={"width": "100%"},
                                            placeholder="https://www.facebook.com/…")),
            field("Tình trạng", dcc.Dropdown(id="ads-md-tt", clearable=False,
                                             options=[{"label": x, "value": x} for x in ads.TINH_TRANG_PAGE])),
        ], className="form-grid"),
        html.Div(id="ads-md-ma", className="ghi-chu-nhan", style={"marginTop": "10px"}),
        html.Div(id="ads-md-msg"),
    ], nut_chinh="Lưu")


def _cau_hinh():
    return [
        _the("Kết nối n8n và bot Telegram", "n8n gửi thẳng vào app thay cho Google Sheet. Gửi lại cùng page + camp "
             "+ ngày thì ghi đè, không nhân đôi. Page mới tự xuất hiện ở danh mục bên dưới.",
             html.Div(id="ads-token-tt"),
             html.Details([html.Summary("Xem mẫu gửi dữ liệu (cho người cài n8n)", className="cg-tieu-de"),
                           html.Pre(id="ads-mau-json", className="khoi-ma")], className="chu-giai"),
             nut=html.Button([icon("refresh", 14), html.Span("Tạo mã kết nối mới")], id="ads-tao-ma",
                             className="btn")),
        _the("Nạp file Google Sheet cũ", "Tải file 'BÁO CÁO CHI TIÊU ADS' (File → Download → .xlsx, một file gồm mọi "
             "tab) rồi thả vào đây: chi tiêu, lead / PTTB, người chạy từng page, tỷ lệ chia riêng. Chỉ dùng cho tháng "
             "chưa nối n8n - nạp lại tháng đã có bot gửi lead sẽ cộng trùng lead.",
             dcc.Upload(id="ads-file", className="upload-zone", children=html.Div(
                 [icon("upload", 18), html.Span(" Kéo thả hoặc bấm chọn file .xlsx")])),
             dcc.Loading(html.Div(id="ads-msg-file"), type="dot")),
        _the("Người chạy page (PIC)", "Khai ai chạy page từ ngày nào. Đổi người giữa tháng: chọn page, chọn nhóm sale "
             "mới và ngày bắt đầu - khai báo cũ tự kết thúc ở ngày trước đó. Tối đa 3 sale; để trống tỷ lệ = chia đều.",
             html.Div([
                 field("Page", dcc.Dropdown(id="ads-pic-page", style={"minWidth": "220px"})),
                 field("Sale (tối đa 3)", dcc.Dropdown(id="ads-pic-sale", multi=True, style={"minWidth": "240px"})),
                 field("Sale mới (chưa có trong danh sách)", dcc.Input(id="ads-pic-moi", className="inp",
                                                                        placeholder="VD: C. Lan")),
                 field("Tỷ lệ % (theo thứ tự sale)", dcc.Input(id="ads-pic-tl", className="inp",
                                                              placeholder="trống = chia đều · VD 70, 30")),
                 field("Từ ngày", dcc.DatePickerSingle(id="ads-pic-tu", display_format="DD/MM/YYYY",
                                                       first_day_of_week=1)),
                 field("Đến ngày (trống = đến nay)", dcc.DatePickerSingle(id="ads-pic-den", display_format="DD/MM/YYYY",
                                                                          first_day_of_week=1, clearable=True)),
                 field(" ", html.Button([icon("plus", 14), html.Span("Lưu phân công")], id="ads-pic-luu",
                                        className="btn primary")),
             ], className="toolbar", style={"flexWrap": "wrap"}),
             html.Div(id="ads-msg-pic"),
             _grid("ads-g-pic", [
                 {"field": "page", "headerName": "Page", "minWidth": 190, "flex": 2, "checkboxSelection": True},
                 {"field": "sale", "headerName": "Sale", "minWidth": 120, "flex": 1},
                 {"field": "tu", "headerName": "Từ ngày", "minWidth": 110},
                 {"field": "den", "headerName": "Đến ngày", "minWidth": 110},
                 _so("Tỷ lệ", "ty_le", PCT, 80)], cao=320, getRowId="params.data.id",
                 opts={"rowSelection": "multiple"}),
             nut=html.Button([icon("trash", 14), html.Span("Xoá dòng đã chọn")], id="ads-pic-xoa",
                             className="btn nguy-hiem")),
        _the("Danh mục page", "Bấm đúp ô có dấu ✎ để sửa rồi Lưu. Loại 'Công ty' = chạy tài khoản công ty, không chia "
             "chi phí cho sale. Tên chuẩn là tên n8n / bot gửi lên - không sửa được.",
             _grid("ads-g-dm", [
                 {"field": "ma", "headerName": "Tên chuẩn (n8n gửi)", "minWidth": 180, "flex": 1.3},
                 {"field": "ten", "headerName": "Tên hiển thị ✎", "editable": True, "minWidth": 190, "flex": 1.6},
                 {"field": "link", "headerName": "Link fanpage ✎", "editable": True, "minWidth": 200, "flex": 1.6},
                 {"field": "loai", "headerName": "Loại ✎", "editable": True, "minWidth": 100,
                  "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": ["Sale", "Công ty"]}},
                 {"field": "tinh_trang", "headerName": "Tình trạng ✎", "editable": True, "minWidth": 115,
                  "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": ads.TINH_TRANG_PAGE}},
                 {"field": "ghi_chu", "headerName": "Ghi chú ✎", "editable": True, "minWidth": 180, "flex": 1.6},
             ], cao=380, getRowId="params.data.id"),
             html.Details([
                 html.Summary("+ Thêm page mới", className="cg-tieu-de"),
                 html.Div([
                     field("Tên chuẩn (n8n / bot gửi)", dcc.Input(id="ads-pm-ma", className="inp",
                                                                   placeholder="VD: BÌNH PHƯỚC")),
                     field("Tên hiển thị", dcc.Input(id="ads-pm-ten", className="inp", placeholder="trống = như tên chuẩn")),
                     field("Loại", dcc.Dropdown(id="ads-pm-loai", value="sale", clearable=False, searchable=False,
                                                options=[{"label": "Sale", "value": "sale"},
                                                         {"label": "Công ty (Trung lập)", "value": "cong_ty"}],
                                                style={"minWidth": "170px"})),
                     field("Tình trạng", dcc.Dropdown(id="ads-pm-tt", value="Đang chạy", clearable=False,
                                                      searchable=False, style={"minWidth": "130px"},
                                                      options=[{"label": x, "value": x} for x in ads.TINH_TRANG_PAGE])),
                     field("Link fanpage", dcc.Input(id="ads-pm-link", className="inp",
                                                     placeholder="https://www.facebook.com/…")),
                     field(" ", html.Button([icon("plus", 14), html.Span("Thêm page")], id="ads-pm-them",
                                            className="btn primary")),
                 ], className="toolbar", style={"flexWrap": "wrap", "marginTop": "8px"}),
                 html.Div("Tên chuẩn phải đúng tên n8n / bot Telegram sẽ gửi (không phân biệt hoa thường, khoảng trắng)"
                          " để số tự vào đúng page. Thêm xong nhớ khai người chạy page ở mục trên.",
                          className="ghi-chu-nhan"),
             ], className="chu-giai", style={"marginTop": "10px"}),
             html.Div(id="ads-msg-pm"),
             html.Div(id="ads-trung-ten"),
             html.Div(id="ads-msg-dm"),
             nut=html.Button([icon("save", 14), html.Span("Lưu danh mục")], id="ads-dm-luu", className="btn primary")),
        _the("Sale và acc", "Danh sách sale dùng khi khai người chạy page. Thêm sale mới ở dưới bảng; sửa cột Acc "
             "(bấm đúp) rồi Lưu.",
             _grid("ads-g-sale-acc", [
                 {"field": "ten", "headerName": "Tên gọi", "minWidth": 140, "flex": 1},
                 {"field": "acc", "headerName": "Acc inside ✎", "editable": True, "minWidth": 180, "flex": 1.4}],
                 cao=320, getRowId="params.data.ten"),
             html.Div([
                 field("Tên gọi sale mới", dcc.Input(id="ads-sm-ten", className="inp", placeholder="VD: C. Lan")),
                 field("Acc inside", dcc.Input(id="ads-sm-acc", className="inp", placeholder="VD: DNG.LanNT5")),
                 field(" ", html.Button([icon("plus", 14), html.Span("Thêm sale")], id="ads-sm-them",
                                        className="btn primary")),
             ], className="toolbar", style={"flexWrap": "wrap", "marginTop": "10px"}),
             html.Div(id="ads-msg-acc"),
             nut=html.Button([icon("save", 14), html.Span("Lưu acc")], id="ads-acc-luu", className="btn primary")),
        _the("Nhập tay", "Cho page không có số từ n8n (VD chạy tài khoản khác) hoặc bổ sung lead / PTTB khi bot "
             "Telegram lỗi. Chi tiêu nhập tay cùng page + ngày sẽ ghi đè lần nhập trước.",
             html.Div([
                 field("Page", dcc.Dropdown(id="ads-tay-page", style={"minWidth": "220px"})),
                 field("Ngày", dcc.DatePickerSingle(id="ads-tay-ngay", display_format="DD/MM/YYYY",
                                                    first_day_of_week=1)),
                 field("Chi tiêu (USD)", dcc.Input(id="ads-tay-chi", type="number", min=0, step="any",
                                                   className="inp", style={"width": "110px"})),
                 field("Số ĐT", dcc.Input(id="ads-tay-lead", type="number", step=1, className="inp",
                                          style={"width": "80px"})),
                 field("PTTB", dcc.Input(id="ads-tay-pttb", type="number", step=1, className="inp",
                                         style={"width": "80px"})),
                 field(" ", html.Button([icon("plus", 14), html.Span("Ghi")], id="ads-tay-ghi",
                                        className="btn primary")),
             ], className="toolbar", style={"flexWrap": "wrap"}),
             html.Div(id="ads-msg-tay")),
        _the("Nhật ký lead / PTTB", "Mỗi lần bot Telegram hoặc nhập tay báo có số là một dòng (kèm người nhắn và nội "
             "dung tin). Nhập nhầm thì tick dòng rồi Xoá.",
             _grid("ads-g-lead", [
                 {"field": "ngay", "headerName": "Ngày", "minWidth": 100, "checkboxSelection": True},
                 {"field": "page", "headerName": "Page", "minWidth": 180, "flex": 1.6},
                 _so("Số ĐT", "lead", SO, 70), _so("PTTB", "pttb", SO, 70),
                 {"field": "nguon", "headerName": "Nguồn", "minWidth": 90},
                 {"field": "nguoi", "headerName": "Người nhập", "minWidth": 120},
                 {"field": "ghi_chu", "headerName": "Tin nhắn / ghi chú", "minWidth": 180, "flex": 1.6,
                  "tooltipField": "ghi_chu"},
                 {"field": "luc", "headerName": "Lúc", "minWidth": 140}], cao=380, getRowId="params.data.id",
                 opts={"rowSelection": "multiple"}),
             nut=html.Button([icon("trash", 14), html.Span("Xoá dòng đã chọn")], id="ads-lead-xoa",
                             className="btn nguy-hiem")),
    ]


def _ky(thang: str) -> tuple[date, date]:
    dau, cuoi, _ = month_range(thang)
    homnay = gio_viet_nam().date()
    return dau, min(cuoi, homnay) if dau <= homnay else cuoi


def _usd(v) -> str:
    return "–" if v is None else f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _ban_ghi(df, cot=None):
    if df is None or len(df) == 0:
        return []
    d = df[cot] if cot else df
    return json.loads(d.to_json(orient="records", date_format="iso", force_ascii=False))


def _link_md(link) -> str:
    return f"[↗]({link})" if isinstance(link, str) and link.startswith("http") else ""


def _bd_the(bd) -> go.Figure:
    """Biểu đồ nhỏ trong thẻ nhận định."""
    f = go.Figure()
    if bd["kieu"] == "bar":
        n = len(bd["nhan"])
        f.add_bar(y=bd["nhan"], x=bd["gia_tri"], orientation="h", marker_color=bd.get("mau") or "#0072BC",
                  text=bd["chu"], textposition="auto", insidetextanchor="start", cliponaxis=False,
                  textfont={"size": 11}, hoverinfo="skip")
        if bd.get("vach") is not None:
            f.add_vline(x=bd["vach"], line={"color": "#51606F", "dash": "dot", "width": 1},
                        annotation_text=bd.get("ten_vach"), annotation_position="top",
                        annotation_font={"size": 10, "color": "#51606F"})
        cao = 44 + 28 * n
        f.update_yaxes(autorange="reversed", tickfont={"size": 11})
        f.update_xaxes(visible=False)
    elif bd["kieu"] == "doi":
        mau_sau = "#D64534" if bd["xau"] else "#1E9E5A"
        for t, a, b in zip(bd["nhan"], bd["truoc"], bd["sau"]):
            f.add_scatter(x=[a, b], y=[t, t], mode="lines", line={"color": "#C9D3DE", "width": 3},
                          hoverinfo="skip", showlegend=False)
        f.add_scatter(x=bd["truoc"], y=bd["nhan"], mode="markers+text", marker={"size": 10, "color": "#9AA9BA"},
                      text=[ads._tien(v) + "$" for v in bd["truoc"]], textposition="middle left",
                      textfont={"size": 10, "color": "#51606F"}, name="7 ngày trước", hoverinfo="skip")
        f.add_scatter(x=bd["sau"], y=bd["nhan"], mode="markers+text", marker={"size": 11, "color": mau_sau},
                      text=[ads._tien(v) + "$" for v in bd["sau"]], textposition="middle right",
                      textfont={"size": 10, "color": mau_sau}, name="7 ngày gần nhất", hoverinfo="skip")
        cao = 64 + 30 * len(bd["nhan"])
        f.update_yaxes(autorange="reversed", tickfont={"size": 11})
        lon = max(bd["truoc"] + bd["sau"])
        f.update_xaxes(visible=False, range=[-lon * .25, lon * 1.3])
        f.update_layout(showlegend=True, legend={"orientation": "h", "y": -0.05, "font": {"size": 10}})
    else:                                                          # cot: so sánh 2 cột
        f.add_bar(x=bd["nhan"], y=bd["gia_tri"], text=bd["chu"], textposition="outside",
                  marker_color=["#9AA9BA", "#0072BC"], hoverinfo="skip", cliponaxis=False)
        cao = 170
        f.update_yaxes(visible=False, range=[0, max(bd["gia_tri"]) * 1.25])
    f.update_layout(height=cao, margin={"l": 8, "r": 8, "t": 18, "b": 8}, plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)", font={"size": 11}, bargap=.35,
                    showlegend=f.layout.showlegend or False)
    return f


def _the_nd(ds, toi_da=None):
    if not ds:
        return [html.Div("Chưa đủ số liệu để nhận định.", className="ghi-chu-nhan")]
    thu_tu = {"bad": 0, "warn": 1, "info": 2, "ok": 3}
    ds = sorted(ds, key=lambda x: thu_tu[x["muc"]])[:toi_da]
    return [html.Div([html.Div(t["tieu_de"], className="nd-ten"), html.Div(t.get("so", ""), className="nd-so"),
                      dcc.Graph(figure=_bd_the(t["bd"]), config={"displayModeBar": False, "staticPlot": True}),
                      html.Div(["→ ", t["noi_dung"]], className="nd-viec")], className=f"nd-the {t['muc']}")
            for t in ds]


def _mau_json(host: str) -> str:
    return (f"# 1) n8n - chi tiêu hôm qua (node HTTP Request, method POST)\n"
            f"URL: {host}/api/ads/chi-tieu\nHeader: X-Ads-Token: <mã kết nối>\nBody (JSON):\n"
            + json.dumps({"page": "KON TUM", "rows": [{"camp": "TCDT_KONTUM_4", "tinh_trang": "HOẠT ĐỘNG",
                                                        "ngay": "2026-09-18", "chi_tieu": 4.56, "tin_nhan": 3}]},
                         ensure_ascii=False, indent=2)
            + f"\n\n# 2) bot Telegram - mỗi lần có số điện thoại / PTTB\nURL: {host}/api/ads/lead\n"
              "Header: X-Ads-Token: <mã kết nối>\nBody (JSON):\n"
            + json.dumps({"page": "QUẢNG NGÃI", "lead": 1, "pttb": 1, "ngay": "2026-09-19",
                          "nguoi": "Kiều", "ghi_chu": ""}, ensure_ascii=False, indent=2)
            + f"\n\n# 3) bot Telegram - hỏi báo cáo (GET)\nURL: {host}/api/ads/bao-cao?date=19/09/2026 "
              "(hoặc start_date=..&end_date=..)\nHeader: X-Ads-Token: <mã kết nối>"
            + "\n\n'page' = tên chuẩn của page (cột Tên chuẩn ở Danh mục page). 'ngay' bỏ trống ở lead = hôm nay.")


def _khoang(dau: date, den: date, cuoi: date | None, khoang: str | None):
    """(từ, đến, kỳ so sánh, tên kỳ so sánh). 7 ngày / ngày gần nhất tính lùi từ ngày đã có chi tiêu."""
    if khoang in ("7", "1") and cuoi:
        n = int(khoang)
        a = cuoi - timedelta(days=n - 1)
        return a, cuoi, (a - timedelta(days=n), cuoi - timedelta(days=n)), "7 ngày trước" if n == 7 else "ngày trước"
    return dau, den, (ads.lui_thang(dau), ads.lui_thang(den)), "cùng kỳ"


_ND = {}


def _nd(tu, den, s):
    """nhan_dinh dùng cho 2 callback cùng lúc - giữ kết quả 60 giây để không tính 2 lần."""
    k = (tu, den, s)
    v = _ND.get(k)
    if v is None or time.time() - v[0] > 60:
        _ND.clear() if len(_ND) > 8 else None
        v = _ND[k] = (time.time(), ads.nhan_dinh(tu, den))
    return v[1]


def _kiem_tra(tu, den):
    ds = ads.kiem_tra(tu, den, gio_viet_nam().date())
    if not ds:
        return None
    muc = "bad" if any(m == "bad" for m, _ in ds) else "warn" if any(m == "warn" for m, _ in ds) else "info"
    return html.Details([
        html.Summary(f"{len(ds)} điểm dữ liệu cần kiểm tra (bấm để xem)"),
        html.Ul([html.Li(c, className=f"kt-{m}") for m, c in ds])], className=f"kiem-tra {muc}")


def _ve_bieu_do(df, tu, den, cuoi, kieu):
    """Biểu đồ theo ngày (tới ngày đã có chi tiêu), bỏ tiền nhập tay tổng tháng ghi ở ngày 01."""
    fig, chu = go.Figure(), []
    if df.empty or cuoi is None:
        return _bo_cuc(fig, 320), "Chưa có chi tiêu trong khoảng này."
    d = df[df.ngay <= cuoi]
    g = d.groupby("ngay")[["chi_tieu", "tin_nhan", "lead", "pttb"]].sum()
    g = g.reindex(pd.date_range(tu, cuoi).date, fill_value=0)
    tay = ads.tien_tong_thang(tu, cuoi)
    tay = tay[tay.page_id.isin(set(df.page_id))]
    if len(tay):
        bot = tay.groupby("ngay").chi_tieu.sum()
        g["chi_tieu"] = (g.chi_tieu - bot.reindex(g.index).fillna(0)).clip(lower=0)
        chu.append(f"Không vẽ {_usd(float(tay.chi_tieu.sum()))} $ nhập tay tổng tháng ({', '.join(tay.ten)}) vì không "
                   "có số từng ngày.")
    sau = df[df.ngay > cuoi]
    if len(sau) and (sau.pttb.sum() or sau.chi_tieu.sum()):
        chu.append(f"Sau {cuoi:%d/%m} chưa đủ chi tiêu các page nên chưa vẽ ({int(sau.pttb.sum())} PTTB, "
                   f"{_usd(float(sau.chi_tieu.sum()))} $ đã báo).")
    x = list(g.index)
    if kieu == "cp":
        cp = (g.chi_tieu / g.pttb.where(g.pttb > 0)).round(2)
        c7, p7 = g.chi_tieu.rolling(7, min_periods=1).sum(), g.pttb.rolling(7, min_periods=1).sum()
        tb7 = (c7 / p7.where(p7 > 0)).round(2)
        mau = ["#B7C2CE" if v != v else "#1E9E5A" if v <= ads.NGUONG_TOT else "#E3A008"
               if v <= ads.NGUONG_BINH_THUONG else "#D64534" for v in cp]
        fig.add_bar(x=x, y=cp, name="Từng ngày", marker_color=mau,
                    customdata=np.stack([g.chi_tieu, g.pttb], axis=-1),
                    hovertemplate="%{x|%d/%m}: %{y:.2f} $/PTTB<br>tiêu %{customdata[0]:,.2f} $ · "
                                  "%{customdata[1]:.0f} PTTB<extra></extra>")
        fig.add_scatter(x=x, y=tb7, name="Trung bình 7 ngày", mode="lines", line={"color": "#1F2937", "width": 2},
                        hovertemplate="%{x|%d/%m}: TB 7 ngày %{y:.2f} $/PTTB<extra></extra>")
        for v, m in ((ads.NGUONG_TOT, "#1E9E5A"), (ads.NGUONG_BINH_THUONG, "#D64534")):
            fig.add_hline(y=v, line={"color": m, "dash": "dot", "width": 1})
        _bo_cuc(fig, 320, yaxis={"title": None, "gridcolor": "#EEF2F6", "rangemode": "tozero", "ticksuffix": " $"})
    elif kieu == "pheu":
        for cot, ten, mau in (("tin_nhan", "Tin nhắn", "#8DB8E3"), ("lead", "Số ĐT", "#0072BC"),
                              ("pttb", "PTTB", "#F37021")):
            fig.add_scatter(x=x, y=g[cot], name=ten, mode="lines+markers", line={"color": mau, "width": 2},
                            hovertemplate="%{x|%d/%m}: %{y:.0f} " + ten + "<extra></extra>")
        _bo_cuc(fig, 320, yaxis={"title": None, "gridcolor": "#EEF2F6", "rangemode": "tozero"})
    else:
        fig.add_bar(x=x, y=g.chi_tieu, name="Chi tiêu (USD)", marker_color="#0072BC",
                    hovertemplate="%{x|%d/%m}: %{y:,.2f} $<extra></extra>")
        fig.add_scatter(x=x, y=g.pttb, name="PTTB", yaxis="y2", mode="lines+markers",
                        line={"color": "#F37021", "width": 2}, hovertemplate="%{x|%d/%m}: %{y:.0f} PTTB<extra></extra>")
        _bo_cuc(fig, 320, yaxis={"title": None, "gridcolor": "#EEF2F6", "rangemode": "tozero", "ticksuffix": " $"},
                yaxis2={"overlaying": "y", "side": "right", "showgrid": False, "rangemode": "tozero",
                        "tickmode": "auto", "title": None})
    fig.update_xaxes(tickformat="%d/%m", range=[pd.Timestamp(tu) - pd.Timedelta(hours=14),
                                                pd.Timestamp(cuoi) + pd.Timedelta(hours=14)])
    fig.update_layout(margin={"l": 50, "r": 40, "t": 10, "b": 36}, hovermode="x unified" if kieu != "cp" else None)
    return fig, " ".join(chu)


def _bo_cuc(fig, cao=300, **kw):
    fig.update_layout(**{"height": cao, "margin": {"l": 44, "r": 20, "t": 10, "b": 36}, "plot_bgcolor": "white",
                         "paper_bgcolor": "white", "legend": {"orientation": "h", "y": 1.12}, "font": {"size": 12},
                         "hoverlabel": {"bgcolor": "white"}, **kw})
    return fig


def register(app):
    cb = callback_can_quyen(app, "duoc_cau_hinh")
    gan_dieu_huong_ky(app, "ads-thang")

    @app.callback(*[Output(f"ads-p-{k}", "style") for k, _ in TAB], Input("ads-tab", "value"))
    def _doi_tab(tab):
        return [{} if k == tab else AN for k, _ in TAB]

    @cb(Output("ads-tab", "value", allow_duplicate=True), Input("ads-sang-nd", "n_clicks"),
        prevent_initial_call=True)
    def _sang_nd(_n):
        return "nhan_dinh"

    # ------------------------------------------------ tổng quan + theo sale
    @cb(Output("ads-badge", "children"), Input("ads-thang", "value"), Input("ads-sua", "data"))
    def _nhan_ngay(thang, _s):
        dau, den_t = _ky(thang)
        cuoi_t = ads.ngay_cuoi_chi(dau, den_t)
        return (html.Span(f"Chi tiêu đến {cuoi_t:%d/%m}", className="badge muted",
                          title="Chi tiêu từ Facebook về lúc 7h sáng hôm sau")
                if cuoi_t else html.Span("Chưa có số tháng này", className="badge warn"))

    # mỗi tab chỉ tính khi người xem mở tab đó (mở lại tab thì lấy số đã nhớ tạm, xem app/bo_nho.py)
    @cb(Output("ads-kpi", "children"), Output("ads-g-page", "rowData"),
        Output("ads-bieu-do", "figure"), Output("ads-bd-chu", "children"), Output("ads-loc-sale", "options"),
        Output("ads-ky-chu", "children"), Output("ads-kiem-tra", "children"),
        Input("ads-tab", "value"), Input("ads-thang", "value"), Input("ads-khoang", "value"),
        Input("ads-loc-sale", "value"), Input("ads-loc-dg", "value"), Input("ads-bd-kieu", "value"),
        Input("ads-loc-loai", "value"), Input("ads-sua", "data"))
    def _nap(tab, thang, khoang, loc_sale, loc_dg, kieu, loai, _s):
        if tab != "tong":
            raise PreventUpdate
        dau, den_t = _ky(thang)
        cuoi_t = ads.ngay_cuoi_chi(dau, den_t)
        tu, den, ck, ten_ck = _khoang(dau, den_t, cuoi_t, khoang)
        df = ads.theo_ngay(tu, den)
        pb = ads.phan_bo(tu, den)
        sales = sorted(set(pb.sale) - {ads.CONG_TY, ads.CHUA_PHAN_CONG}) if len(pb) else []
        chon = None
        if loc_sale and len(pb):
            chon = set(pb[pb.sale == loc_sale].page_id)
        tp = ads.theo_page(tu, den, ck, df)
        if loc_dg:
            giu = set(tp[tp.danh_gia.isin(loc_dg)].page_id)
            chon = giu if chon is None else chon & giu
        if loai in ("sale", "cong_ty"):
            pg = ads.ds_page()
            giu = set(pg[(pg.loai == "cong_ty") == (loai == "cong_ty")].id)
            chon = giu if chon is None else chon & giu
        if chon is not None:
            df = df[df.page_id.isin(chon)]
            tp = tp[tp.page_id.isin(chon)]
        t = ads.tong_quan(tu, den, ck, df)
        c = t["ck"]
        if chon is not None:                                    # kỳ trước cũng chỉ tính các page đang lọc
            d_ck = ads.theo_ngay(*ck)
            d_ck = d_ck[d_ck.page_id.isin(chon)]
            c = {k: float(d_ck[k].sum()) if len(d_ck) else 0.0 for k in ("chi_tieu", "tin_nhan", "lead", "pttb")}
            t["ck_cp_pttb"] = c["chi_tieu"] / c["pttb"] if c["pttb"] and c["chi_tieu"] else None

        def ck_(v):
            return f"{ten_ck} {so_vn(v)}" if v else None
        the = [
            kpi("Chi tiêu", f"{_usd(t['chi_tieu'])} $", f"≈ {so_vn(t['vnd'] / 1e6, 1)} triệu đồng"
                + (f" · {ten_ck} {_usd(c['chi_tieu'])} $" if c["chi_tieu"] else "")),
            kpi("Tin nhắn", so_vn(t["tin_nhan"]), ck_(c["tin_nhan"])),
            kpi("Số điện thoại", so_vn(t["lead"]), f"{_usd(t['cpl'])} $ mỗi số"),
            kpi("PTTB", so_vn(t["pttb"]), ck_(c["pttb"])),
            kpi("Chi phí / PTTB", f"{_usd(t['cp_pttb'])} $",
                f"{ten_ck} {_usd(t['ck_cp_pttb'])} $" if t["ck_cp_pttb"] else
                (f"tính tới {t['den_cp']:%d/%m}" if t["den_cp"] else None),
                "" if t["cp_pttb"] is None else ("ok" if t["cp_pttb"] <= ads.NGUONG_TOT else
                                                  "warn" if t["cp_pttb"] <= ads.NGUONG_BINH_THUONG else "bad")),
            kpi("Tỷ lệ chốt", "–" if t["ty_le_chot"] is None else f"{t['ty_le_chot']:.0f}%", "PTTB / số điện thoại"),
            kpi("Page có chi tiêu", so_vn(t["so_page"]), f"tỷ giá {so_vn(t['ty_gia'])}"),
        ]
        if len(tp):
            tp = tp.copy()
            nd = df[df.chi_tieu > 0].groupby("page_id").ngay.nunique() if len(df) else {}
            tp["so_ngay"] = tp.page_id.map(nd).fillna(0).astype(int)
            tp["tb_ngay"] = (tp.chi_tieu / tp.so_ngay.where(tp.so_ngay > 0)).round(2)
            tp["ck_cp"] = (tp.ck_chi_tieu / tp.ck_pttb.where(tp.ck_pttb > 0)).where(tp.ck_chi_tieu > 0).round(2)
            tp["link_md"] = [_link_md(x) for x in tp.link]
        fig, chu = _ve_bieu_do(df, tu, den, t["den_cp"], kieu or "chi")
        ky = f"{tu:%d/%m} - {den:%d/%m}" if tu != den else f"{tu:%d/%m}"
        ky_chu = f"Đang xem {ky}, so với {ten_ck} ({ck[0]:%d/%m}" + (f" - {ck[1]:%d/%m})" if ck[0] != ck[1] else ")")
        if t["pttb_chua_khop"]:
            ky_chu += (f" · {int(t['pttb_chua_khop'])} PTTB báo sau {t['den_cp']:%d/%m} chưa có chi tiêu nên chưa tính "
                       "vào chi phí / PTTB")
        return (the, _ban_ghi(tp), fig, chu, [{"label": x, "value": x} for x in sales], ky_chu,
                _kiem_tra(dau, den_t))

    @cb(Output("ads-g-sale", "rowData"), Output("ads-g-sale", "dashGridOptions"), Output("ads-sale-mo-ta", "children"),
        Output("ads-ty-gia", "value"),
        Input("ads-tab", "value"), Input("ads-thang", "value"), Input("ads-sua", "data"),
        State("ads-g-sale", "dashGridOptions"))
    def _theo_sale(tab, thang, _s, opts):
        if tab != "sale":
            raise PreventUpdate
        tu, den = _ky(thang)
        opts = dict(opts or {})
        ts = ads.theo_sale(tu, den)
        rate = ads.ty_gia(thang)
        if ts.empty:
            opts["pinnedBottomRowData"] = []
            return [], opts, "", round(rate)
        ts["vnd"] = ts.chi_tieu * rate
        ts["du_kien_vnd"] = ts.du_kien * rate
        cuoi = ts.attrs.get("cuoi")
        opts["pinnedBottomRowData"] = [{"sale": "Tổng", "chi_tieu": float(ts.chi_tieu.sum()),
                                        "vnd": float(ts.vnd.sum()), "tb_5_ngay": float(ts.tb_5_ngay.fillna(0).sum()),
                                        "du_kien": float(ts.du_kien.sum()), "du_kien_vnd": float(ts.du_kien_vnd.sum())}]
        mo_ta = ""
        if cuoi:
            con = __import__("calendar").monthrange(cuoi.year, cuoi.month)[1] - cuoi.day
            a = max(tu, cuoi - timedelta(days=4))
            mo_ta = (f"Chi tiêu có đến {cuoi:%d/%m} · trung bình tính từ {a:%d/%m} đến {cuoi:%d/%m} · còn {con} ngày "
                     f"· tỷ giá {so_vn(rate)}")
        return _ban_ghi(ts.drop(columns=["acc"], errors="ignore")), opts, mo_ta, round(rate)

    @cb(Output("ads-md-sale", "className"), Output("ads-md-sale-tieu-de", "children"),
        Output("ads-g-ct-sale", "rowData"), Output("ads-g-ct-sale", "dashGridOptions"),
        Input("ads-g-sale", "cellDoubleClicked"), Input("ads-md-sale-dong", "n_clicks"),
        Input("ads-md-sale-nen", "n_clicks"), State("ads-g-sale", "selectedRows"), State("ads-g-sale", "rowData"),
        State("ads-thang", "value"), State("ads-g-ct-sale", "dashGridOptions"), prevent_initial_call=True)
    def _ct_sale(o, _a, _b, chon, rows, thang, opts):
        if ctx.triggered_id != "ads-g-sale":
            return "modal", no_update, no_update, no_update
        r = (chon or [None])[0]
        if r is None and o and rows and o.get("rowIndex") is not None and o["rowIndex"] < len(rows):
            r = rows[o["rowIndex"]]
        if not r or not r.get("sale") or r.get("sale") == "Tổng":
            raise PreventUpdate
        tu, den = _ky(thang)
        ct = ads.chi_tiet_sale(r["sale"], tu, den)
        opts = dict(opts or {})
        if ct.empty:
            opts["pinnedBottomRowData"] = []
            return "modal mo", f"{r['sale']} · chưa có chi tiêu", [], opts
        rate = ads.ty_gia(thang)
        ct["vnd"] = ct.chi_tieu * rate
        ct["khoang"] = [f"{a} - {b}" if a != b else a for a, b in zip(ct.tu, ct.den)]
        opts["pinnedBottomRowData"] = [{"ten": "Tổng", "chi_tieu": float(ct.chi_tieu.sum()),
                                        "vnd": float(ct.vnd.sum())}]
        return ("modal mo", f"{r['sale']} · {_usd(float(ct.chi_tieu.sum()))} $ · {len(ct)} page", _ban_ghi(ct),
                opts)

    @cb(Output("ads-msg-ty-gia", "children"), Output("ads-sua", "data", allow_duplicate=True),
        Input("ads-luu-ty-gia", "n_clicks"), State("ads-ty-gia", "value"), State("ads-thang", "value"),
        prevent_initial_call=True)
    def _luu_ty_gia(_n, rate, thang):
        try:
            rate = float(rate)
        except (TypeError, ValueError):
            return alert("Nhập tỷ giá là số, VD 26394.", "bad"), no_update
        if rate < 1000:
            return alert("Tỷ giá phải từ 1.000 trở lên.", "bad"), no_update
        ads.luu_thang(thang, rate, {}, current_user.username)
        return alert(f"Đã lưu tỷ giá tháng {thang[5:]}/{thang[:4]}: {so_vn(rate)}.", "ok"), gio_viet_nam().isoformat()

    # ------------------------------------------------ nhận định (tổng quan hiện 4 thẻ đầu)
    @cb(Output("ads-tq-the", "children"), Output("ads-nd-the", "children"), Output("ads-nd-den", "children"),
        Output("ads-nd-ma-tran", "figure"), Output("ads-nd-nhom", "figure"), Output("ads-nd-xu", "rowData"),
        Output("ads-nd-pheu", "rowData"), Output("ads-nd-muc-chung", "children"),
        Output("ads-nd-nhom-chu", "children"),
        Input("ads-tab", "value"), Input("ads-thang", "value"), Input("ads-sua", "data"))
    def _nhan_dinh(tab, thang, _s):
        if tab not in ("tong", "nhan_dinh"):
            raise PreventUpdate
        tu, den = _ky(thang)
        nd = _nd(tu, den, _s)
        tp = nd["page"]
        mau = {"Hiệu quả cao": "#1E9E5A", "Trung bình": "#E3A008", "Kém": "#D64534", "Chưa đủ dữ liệu": "#B7C2CE"}
        f1, f2 = go.Figure(), go.Figure()
        cao1, chu_nhom = 380, ""
        if len(tp):
            x = tp.assign(_v=tp.cp_pttb.where(tp.pttb > 0)).copy()
            x["_ve"] = x._v.fillna(x.chi_tieu.clip(upper=ads.NGUONG_BINH_THUONG * 1.6))
            x = x.sort_values(["_v"], ascending=False, na_position="first")
            x["_n"] = ads.ten_gon_ds(x.ten)
            trung = x._n.duplicated(keep=False)
            x.loc[trung, "_n"] = [f"{n} ({m.title()})" for n, m in zip(x._n[trung], x.ma[trung])]
            f1.add_bar(y=x._n, x=x._ve, orientation="h", marker_color=[mau[n] for n in x.nhom],
                       text=[(f"{ads._tien(v)}$/PTTB" if v == v else "chưa có PTTB") for v in x._v],
                       textposition="inside", insidetextanchor="end", textfont={"size": 10, "color": "white"},
                       customdata=np.stack([x.ten, x.chi_tieu, x.pttb], axis=-1),
                       hovertemplate="<b>%{customdata[0]}</b><br>Tiêu %{customdata[1]:,.2f} $ · "
                                     "%{customdata[2]:.0f} PTTB<extra></extra>")
            f1.add_scatter(y=x._n, x=[max(x._ve) * 1.02] * len(x), mode="text", hoverinfo="skip",
                           text=[f"{ads._tien(c)}$" for c in x.chi_tieu], textposition="middle right",
                           textfont={"size": 10, "color": "#51606F"}, showlegend=False)
            f1.add_vline(x=ads.NGUONG_TOT, line={"color": "#1E9E5A", "dash": "dot", "width": 1})
            f1.add_vline(x=ads.NGUONG_BINH_THUONG, line={"color": "#D64534", "dash": "dot", "width": 1})
            cao1 = 60 + 22 * len(x)
            f1.update_xaxes(range=[0, max(x._ve) * 1.22])
            g = tp.groupby("nhom")[["ty_trong_chi", "ty_trong_pttb"]].sum().reindex(ads.NHOM_HQ).fillna(0)
            so_page = tp.groupby("nhom").size().reindex(ads.NHOM_HQ).fillna(0).astype(int)
            ten_nhom = {"Hiệu quả cao": "Tốt", "Trung bình": "Trung bình", "Kém": "Kém", "Chưa đủ dữ liệu": "Mới"}
            for nhom in ads.NHOM_HQ:
                if not so_page[nhom]:
                    continue
                v = [g.ty_trong_chi[nhom], g.ty_trong_pttb[nhom]]
                f2.add_bar(y=["Tiền bỏ ra", "PTTB thu về"], x=v, orientation="h", name=f"{ten_nhom[nhom]} "
                           f"({so_page[nhom]} page)", marker_color=mau[nhom],
                           text=[f"{x:.0f}%" if x >= 4 else "" for x in v], textposition="inside",
                           insidetextanchor="middle", textfont={"color": "white", "size": 13},
                           hovertemplate=f"{ten_nhom[nhom]}: " + "%{x:.1f}%<extra></extra>")
            k = g.loc["Kém"] if "Kém" in g.index else None
            if k is not None and k.ty_trong_chi > 0:
                chu_nhom = (f"Nhóm Kém ({so_page['Kém']} page) tiêu {k.ty_trong_chi:.0f}% tổng tiền nhưng chỉ mang về "
                            f"{k.ty_trong_pttb:.0f}% PTTB. Nhóm Tốt ({so_page['Hiệu quả cao']} page) tiêu "
                            f"{g.ty_trong_chi['Hiệu quả cao']:.0f}% tiền, mang về {g.ty_trong_pttb['Hiệu quả cao']:.0f}% PTTB.")
            else:
                chu_nhom = "Không có page nào ở nhóm Kém."
        _bo_cuc(f1, cao1, showlegend=False, bargap=.25,
                xaxis={"title": "Chi phí / PTTB ($)", "gridcolor": "#EEF2F6", "side": "top"},
                yaxis={"autorange": "reversed", "tickfont": {"size": 11}}, margin={"l": 10, "r": 10, "t": 40, "b": 10})
        _bo_cuc(f2, 200, barmode="stack", bargap=.35, legend={"orientation": "h", "y": -0.25},
                xaxis={"visible": False, "range": [0, 100]}, yaxis={"autorange": "reversed", "tickfont": {"size": 12}},
                margin={"l": 90, "r": 10, "t": 6, "b": 10})
        den_ = html.Span(f"Tính đến {nd['den']:%d/%m}", className="badge muted") if nd["den"] else None
        muc = []
        if nd["tl_so"]:
            muc.append(f"Mức chung: {nd['tl_so']:.0f}% tin nhắn ra số")
        if nd["tl_chot"]:
            muc.append(f"{nd['tl_chot']:.0f}% số ra PTTB")
        xu = nd["xu_huong"]
        if len(xu):
            xu = xu.sort_values("doi_cp", ascending=False, na_position="last")
        ph = nd["pheu"]
        if len(ph):
            ph = ph.assign(_c=ph.van_de.eq("")).sort_values(["_c", "tin_nhan"], ascending=[True, False]) \
                   .drop(columns="_c")
        return (_the_nd(nd["the"], 4), _the_nd(nd["the"]), den_, f1, f2, _ban_ghi(xu), _ban_ghi(ph), " · ".join(muc),
                chu_nhom)

    @cb(Output("ads-pheu-page", "options"), Output("ads-nd-pheu-bd", "figure"),
        Input("ads-pheu-page", "value"), Input("ads-tab", "value"), Input("ads-thang", "value"),
        Input("ads-sua", "data"))
    def _pheu(pid, tab, thang, _s):
        if tab != "nhan_dinh":
            raise PreventUpdate
        tu, den = _ky(thang)
        nd = _nd(tu, den, _s)
        ph = nd["pheu"]
        opts = [] if ph.empty else [{"label": t, "value": int(i)} for i, t in
                                    zip(ph.sort_values("tin_nhan", ascending=False).page_id,
                                        ph.sort_values("tin_nhan", ascending=False).ten)]
        f = go.Figure()
        if len(ph):
            x = ph[ph.page_id == pid] if pid else ph
            v = [float(x.tin_nhan.sum()), float(x.lead.sum()), float(x.pttb.sum())]
            f.add_funnel(y=["Tin nhắn", "Số điện thoại", "PTTB"], x=v, textinfo="value+percent previous",
                         marker={"color": ["#8DB8E3", "#0072BC", "#F37021"]}, connector={"fillcolor": "#EEF2F6"},
                         hovertemplate="%{y}: %{x}<extra></extra>")
            if pid and nd["tl_so"] and nd["tl_chot"]:
                f.add_annotation(text=f"Mức chung: {nd['tl_so']:.0f}% tin nhắn ra số · {nd['tl_chot']:.0f}% số ra PTTB",
                                 xref="paper", yref="paper", x=0.5, y=-0.12, showarrow=False,
                                 font={"size": 11, "color": "#51606F"})
        _bo_cuc(f, 270, margin={"l": 100, "r": 20, "t": 10, "b": 36})
        return opts, f

    # ------------------------------------------------ tracking ngày (page × ngày)
    @cb(Output("ads-g-ngay", "columnDefs"), Output("ads-g-ngay", "rowData"), Output("ads-chu-mau", "children"),
        Output("ads-g-ngay", "dashGridOptions"),
        Input("ads-tab", "value"), Input("ads-thang", "value"), Input("ads-chi-so", "value"),
        Input("ads-sua", "data"), State("ads-g-ngay", "dashGridOptions"))
    def _tracking(tab, thang, chi_so, _s, opts):
        if tab != "ngay":
            raise PreventUpdate
        opts = dict(opts or {})
        chi_so = chi_so or "chi_tieu"
        pv, so_ngay = ads.tracking(thang, chi_so)
        tien = chi_so in ("chi_tieu", "cp_pttb")
        fmt = USD_D if tien else SO
        huong = HUONG_CHI_SO[chi_so]
        ngay = [str(i) for i in range(1, so_ngay + 1)]
        gia_tri = pv[[c for c in pv.columns if str(c).isdigit()]].values.ravel().tolist() if len(pv) else []
        nhiet = _mau_nhiet(gia_tri, huong)
        cot = [{"field": "ten", "headerName": "Page", "pinned": "left", "minWidth": 180, "tooltipField": "ten"}]
        if chi_so == "chi_tieu":
            cot += [{"field": "tong", "headerName": "Tổng ($)", "pinned": "left", "width": 100,
                     "type": "numericColumn", "valueFormatter": USD_D, "cellStyle": {"fontWeight": "700"}},
                    {"field": "vnd", "headerName": "≈ VNĐ", "pinned": "left", "width": 115, "type": "numericColumn",
                     "valueFormatter": VND, "headerTooltip": "Tổng USD × tỷ giá tháng"}]
        else:
            cot.append({"field": "tong", "headerName": "Cả tháng" if chi_so == "cp_pttb" else "Tổng",
                        "pinned": "left", "width": 95, "type": "numericColumn", "valueFormatter": fmt,
                        "cellStyle": MAU_CP if chi_so == "cp_pttb" else {"fontWeight": "700"}})
        dau = date.fromisoformat(f"{thang}-01")
        cot += [{"field": d, "headerName": f"{d} {THU[(dau + timedelta(days=int(d) - 1)).weekday()]}",
                 "width": 88 if tien else 58, "type": "numericColumn", "cellStyle": nhiet, "sortable": False,
                 "filter": False, "wrapHeaderText": True, "autoHeaderHeight": True,
                 "headerClass": "cot-cn" if (dau + timedelta(days=int(d) - 1)).weekday() == 6 else None,
                 "valueFormatter": {"function": "params.value ? " + fmt["function"] + " : ''"}} for d in ngay]
        opts["pinnedBottomRowData"] = []
        if pv.empty:
            return cot, [], _chu_mau(huong), opts
        tong = dict(pv.attrs.get("tong") or {})
        pv.columns = [str(c) for c in pv.columns]
        if chi_so == "chi_tieu":
            rate = ads.ty_gia(thang)
            pv["vnd"] = pv["tong"] * rate
            tong["vnd"] = (tong.get("tong") or 0) * rate
        opts["pinnedBottomRowData"] = [{"ten": "Tổng từng ngày" if chi_so != "cp_pttb" else "Chung từng ngày",
                                        **tong}]
        return cot, _ban_ghi(pv), _chu_mau(huong), opts

    # ------------------------------------------------ chi tiết một page
    @cb(Output("ads-ct-page", "data"), Input("ads-g-ngay", "cellDoubleClicked"),
        Input("ads-g-page", "cellDoubleClicked"), State("ads-g-ngay", "selectedRows"),
        State("ads-g-page", "selectedRows"), State("ads-g-ngay", "rowData"), State("ads-g-page", "rowData"),
        prevent_initial_call=True)
    def _bam_dup(o1, o2, chon1, chon2, rows1, rows2):
        o, chon, rows = (o1, chon1, rows1) if ctx.triggered_id == "ads-g-ngay" else (o2, chon2, rows2)
        if not o:
            raise PreventUpdate
        r = (chon or [None])[0]
        if r is None and rows and o.get("rowIndex") is not None and o["rowIndex"] < len(rows):
            r = rows[o["rowIndex"]]
        if not r or r.get("page_id") is None:
            raise PreventUpdate
        return {"id": int(r["page_id"]), "t": o.get("timestamp")}

    @cb(Output("ads-md-ct", "className", allow_duplicate=True), Input("ads-md-ct-dong", "n_clicks"),
        Input("ads-md-ct-nen", "n_clicks"), prevent_initial_call=True)
    def _dong_ct(_a, _b):
        return "modal"

    @cb(Output("ads-g-ct", "columnDefs"), Output("ads-g-ct", "rowData"), Output("ads-g-ct", "dashGridOptions"),
        Output("ads-ct-dau", "children"), Output("ads-md-ct-tieu-de", "children"),
        Output("ads-md-ct", "className"),
        Input("ads-ct-page", "data"), Input("ads-thang", "value"), Input("ads-sua", "data"),
        State("ads-g-ct", "dashGridOptions"), prevent_initial_call=True)
    def _ct(chon, thang, _s, opts):
        opts = dict(opts or {})
        opts["pinnedBottomRowData"] = []
        pid = (chon or {}).get("id")
        mo = "modal mo" if ctx.triggered_id == "ads-ct-page" else no_update
        if not pid:
            raise PreventUpdate
        tu, den = _ky(thang)
        ct = ads.chi_tiet_page(int(pid), tu, den)
        so_pic = max(ct["so_pic"], 1)
        cot = [{"field": "ngay", "headerName": "Ngày", "pinned": "left", "width": 105},
               {"field": "camp", "headerName": "Tên camp", "minWidth": 170, "flex": 1.6, "tooltipField": "camp"},
               {"field": "tinh_trang", "headerName": "Tình trạng", "width": 125, "cellStyle": MAU_TT},
               _so("Chi tiêu ($)", "chi_tieu", USD, 95), _so("Tin nhắn", "tin_nhan", SO, 85),
               _so("Số ĐT", "lead", SO, 75), _so("PTTB", "pttb", SO, 70)]
        cot += [{"field": f"pic{k}", "headerName": f"PIC {k}", "minWidth": 95, "flex": .8}
                for k in range(1, so_pic + 1)]
        cot.append({"field": "tien_nguoi", "headerName": "Tiền/người", "minWidth": 170, "flex": 1.4, "tooltipField": "tien_nguoi",
                    "type": "rightAligned", "headerTooltip": "Chi tiêu chia cho người chạy (USD)"})
        t = ct["tong"]
        opts["pinnedBottomRowData"] = [{"ngay": "Tổng", "camp": f"CP/PTTB {_usd(t['chi_tieu'] / t['pttb'])} $"
                                        if t["pttb"] else "", **t}]
        dau = []
        if ct["link"]:
            dau.append(html.A(["Mở fanpage ↗"], href=ct["link"], target="_blank", className="link-page"))
        dau += [html.Span(f"{s}: {_usd(v)} $", className="chip") for s, v in ct["tong_sale"]]
        if ct["tinh_trang"]:
            dau.append(html.Span(ct["tinh_trang"], className="badge muted"))
        return cot, ct["rows"], opts, dau, f"{ct['ten']} · {_usd(t['chi_tieu'])} $ · {int(t['pttb'])} PTTB", mo

    # ------------------------------------------------ sửa page (tên, link, tình trạng)
    @cb(Output("ads-md-page", "className"), Output("ads-md-id", "data"), Output("ads-md-tieu-de", "children"),
        Output("ads-md-ten", "value"), Output("ads-md-link", "value"), Output("ads-md-tt", "value"),
        Output("ads-md-ma", "children"), Output("ads-md-msg", "children"),
        Input("ads-ct-sua", "n_clicks"), Input("ads-md-page-dong", "n_clicks"), Input("ads-md-page-huy", "n_clicks"),
        Input("ads-md-msg", "title"), State("ads-ct-page", "data"), prevent_initial_call=True)
    def _mo_md(_a, _b, _c, xong, chon):
        pid = (chon or {}).get("id")
        if ctx.triggered_id == "ads-ct-sua" and pid:
            pg = ads.ds_page().set_index("id")
            if int(pid) not in pg.index:
                raise PreventUpdate
            p = pg.loc[int(pid)]
            return ("modal mo", int(pid), f"Sửa page · {p.ten}", p.ten, p.link if isinstance(p.link, str) else "",
                    p.tinh_trang, f"Tên chuẩn n8n / bot gửi lên: {p.ma} (không đổi)", "")
        if ctx.triggered_id == "ads-md-msg" and not xong:
            raise PreventUpdate
        return ("modal",) + (no_update,) * 6 + ("",)

    @cb(Output("ads-md-msg", "children", allow_duplicate=True), Output("ads-md-msg", "title"),
        Output("ads-sua", "data", allow_duplicate=True),
        Input("ads-md-page-ok", "n_clicks"), State("ads-md-id", "data"), State("ads-md-ten", "value"),
        State("ads-md-link", "value"), State("ads-md-tt", "value"), prevent_initial_call=True)
    def _luu_md(_n, pid, ten, link, tt):
        if not pid:
            raise PreventUpdate
        try:
            ads.sua_page(int(pid), ten, link, tt, current_user.username)
        except ads.LoiAds as e:
            return alert(str(e), "bad"), "", no_update
        return "", gio_viet_nam().isoformat(), gio_viet_nam().isoformat()

    # ------------------------------------------------ cấu hình
    @cb(Output("ads-g-pic", "rowData"), Output("ads-g-dm", "rowData"), Output("ads-g-sale-acc", "rowData"),
        Output("ads-g-lead", "rowData"), Output("ads-pic-page", "options"), Output("ads-pic-sale", "options"),
        Output("ads-tay-page", "options"), Output("ads-token-tt", "children"), Output("ads-mau-json", "children"),
        Output("ads-trung-ten", "children"),
        Input("ads-tab", "value"), Input("ads-sua", "data"), State("ads-thang", "value"))
    def _nap_cau_hinh(tab, _s, thang):
        if tab != "cauhinh":
            return (no_update,) * 10
        from flask import request
        pg = ads.ds_page()
        ten = dict(zip(pg.id, pg.ten))
        pic = ads.ds_pic()
        pic["page"] = pic.page_id.map(ten)
        pic["tu"] = [x.strftime("%d/%m/%Y") if x else "" for x in pic.tu_ngay]
        pic["den"] = [x.strftime("%d/%m/%Y") if x and x == x else "đến nay" for x in pic.den_ngay]
        pic = pic.sort_values(["page", "tu_ngay"], ascending=[True, False])
        dm = pg.assign(loai=pg.loai.map({"cong_ty": "Công ty"}).fillna("Sale"))
        tu, den = _ky(thang)
        lg = ads.nhat_ky_lead(tu, den)
        if len(lg):
            lg["ngay"] = [str(x)[:10] for x in lg.ngay]
            lg["luc"] = [str(x)[:16] for x in lg.created_at]
        opt_pg = [{"label": t, "value": int(i)} for i, t in zip(pg.id, pg.ten)]
        sale = ads.ds_sale()
        tt = (html.Span("Đã có mã kết nối. Mã chỉ hiện một lần lúc tạo; mất mã thì tạo mã mới rồi dán lại vào n8n.",
                        className="badge ok") if ads.co_token() else
              html.Span("Chưa có mã kết nối - bấm 'Tạo mã kết nối mới'.", className="badge warn"))
        return (_ban_ghi(pic, ["id", "page", "sale", "tu", "den", "ty_le"]), _ban_ghi(dm),
                _ban_ghi(sale), _ban_ghi(lg), opt_pg, [{"label": x, "value": x} for x in sale.ten], opt_pg, tt,
                _mau_json(request.host_url.rstrip("/")),
                [alert(f"Tên '{t}' đang dùng cho {len(m)} page ({', '.join(m)}) - sửa cho mỗi page một tên riêng.",
                       "warn") for t, m in ads.trung_ten()])

    @cb(Output("ads-token-tt", "children", allow_duplicate=True), Input("ads-tao-ma", "n_clicks"),
        prevent_initial_call=True)
    def _tao_ma(_n):
        tok = ads.tao_token(current_user.username)
        return alert([html.B("Mã kết nối mới (chỉ hiện lần này - dán vào header X-Ads-Token của 2 workflow n8n): "),
                      html.Code(tok, style={"userSelect": "all", "wordBreak": "break-all"})], "ok")

    @cb(Output("ads-msg-file", "children"), Output("ads-sua", "data", allow_duplicate=True),
        Input("ads-file", "contents"), State("ads-file", "filename"), prevent_initial_call=True)
    def _nap_file(noi_dung, ten):
        if not noi_dung:
            return no_update, no_update
        try:
            kq = ads.nap_file_sheet(base64.b64decode(noi_dung.split(",", 1)[1]), current_user.username)
        except ads.LoiAds as e:
            return alert(str(e), "bad"), no_update
        except Exception as e:                                    # file hỏng / không phải xlsx
            return alert(f"Không đọc được file {ten}: {type(e).__name__}", "bad"), no_update
        ghi_log("ads_nap_file", f"{ten}")
        return alert(f"Đã nạp {ten}: {kq['chi_tieu']} dòng chi tiêu ({kq['moi']} mới, {kq['cap_nhat']} cập nhật), "
                     f"{kq['lead']} ngày có lead / PTTB, {kq['pic']} dòng phân công, {kq['page']} page · tháng "
                     f"{', '.join(kq['thang'])}.", "ok"), gio_viet_nam().isoformat()

    @cb(Output("ads-msg-pic", "children"), Output("ads-sua", "data", allow_duplicate=True),
        Input("ads-pic-luu", "n_clicks"), Input("ads-pic-xoa", "n_clicks"),
        State("ads-pic-page", "value"), State("ads-pic-sale", "value"), State("ads-pic-moi", "value"),
        State("ads-pic-tl", "value"), State("ads-pic-tu", "date"), State("ads-pic-den", "date"),
        State("ads-g-pic", "selectedRows"), prevent_initial_call=True)
    def _pic(_a, _b, page, sales, moi, tl, tu, den, chon):
        try:
            if ctx.triggered_id == "ads-pic-xoa":
                if not chon:
                    return alert("Chọn dòng cần xoá (ô vuông đầu dòng).", "warn"), no_update
                n = ads.xoa_pic([r["id"] for r in chon], current_user.username)
                return alert(f"Đã xoá {n} dòng phân công.", "ok"), gio_viet_nam().isoformat()
            ds = list(sales or []) + [x.strip() for x in (moi or "").split(",") if x.strip()]
            if not page or not tu:
                return alert("Chọn page và ngày bắt đầu.", "warn"), no_update
            ty_le = [x.strip() for x in (tl or "").replace(";", ",").split(",") if x.strip()]
            msg = ads.them_pic(int(page), ds, date.fromisoformat(tu[:10]),
                               date.fromisoformat(den[:10]) if den else None, current_user.username,
                               [ads.doc_so(x) for x in ty_le] or None)
        except ads.LoiAds as e:
            return alert(str(e), "bad"), no_update
        return alert(msg, "ok"), gio_viet_nam().isoformat()

    @cb(Output("ads-msg-dm", "children"), Output("ads-sua", "data", allow_duplicate=True),
        Input("ads-dm-luu", "n_clicks"), State("ads-g-dm", "rowData"), prevent_initial_call=True)
    def _luu_dm(_n, rows):
        try:
            n = ads.luu_page([{**r, "loai": "cong_ty" if r.get("loai") == "Công ty" else "sale"}
                              for r in rows or []], current_user.username)
        except ads.LoiAds as e:
            return alert(str(e), "bad"), no_update
        return alert(f"Đã lưu {n} page thay đổi.", "ok"), gio_viet_nam().isoformat()

    @cb(Output("ads-msg-pm", "children"), Output("ads-sua", "data", allow_duplicate=True),
        Output("ads-pm-ma", "value"), Output("ads-pm-ten", "value"), Output("ads-pm-link", "value"),
        Input("ads-pm-them", "n_clicks"), State("ads-pm-ma", "value"), State("ads-pm-ten", "value"),
        State("ads-pm-loai", "value"), State("ads-pm-tt", "value"), State("ads-pm-link", "value"),
        prevent_initial_call=True)
    def _them_page(_n, ma, ten, loai, tt, link):
        try:
            msg = ads.them_page(ma, ten, loai, link, tt, current_user.username)
        except ads.LoiAds as e:
            return alert(str(e), "bad"), no_update, no_update, no_update, no_update
        return alert(msg, "ok"), gio_viet_nam().isoformat(), "", "", ""

    @cb(Output("ads-msg-acc", "children", allow_duplicate=True), Output("ads-sua", "data", allow_duplicate=True),
        Output("ads-sm-ten", "value"), Output("ads-sm-acc", "value"),
        Input("ads-sm-them", "n_clicks"), State("ads-sm-ten", "value"), State("ads-sm-acc", "value"),
        prevent_initial_call=True)
    def _them_sale(_n, ten, acc):
        try:
            msg = ads.them_sale(ten, acc, current_user.username)
        except ads.LoiAds as e:
            return alert(str(e), "bad"), no_update, no_update, no_update
        return alert(msg + " Giờ có thể chọn sale này ở Người chạy page.", "ok"), gio_viet_nam().isoformat(), "", ""

    @cb(Output("ads-msg-acc", "children"), Output("ads-sua", "data", allow_duplicate=True),
        Input("ads-acc-luu", "n_clicks"), State("ads-g-sale-acc", "rowData"), prevent_initial_call=True)
    def _luu_acc(_n, rows):
        n = ads.luu_sale(rows or [], current_user.username)
        return alert(f"Đã lưu {n} acc.", "ok"), gio_viet_nam().isoformat()

    @cb(Output("ads-msg-tay", "children"), Output("ads-sua", "data", allow_duplicate=True),
        Input("ads-tay-ghi", "n_clicks"), State("ads-tay-page", "value"), State("ads-tay-ngay", "date"),
        State("ads-tay-chi", "value"), State("ads-tay-lead", "value"), State("ads-tay-pttb", "value"),
        State("ads-tay-page", "options"), prevent_initial_call=True)
    def _nhap_tay(_n, page, ngay, chi, lead, pttb, opts):
        if not page or not ngay:
            return alert("Chọn page và ngày.", "warn"), no_update
        ten = next((o["label"] for o in opts or [] if o["value"] == page), None)
        ma = ads.ds_page().set_index("id").ma.get(page)
        viec = []
        if chi not in (None, ""):
            ads.nhan_chi_tieu({"page": ma, "camp": "Nhập tay", "ngay": ngay[:10], "chi_tieu": chi,
                               "tinh_trang": "NHẬP TAY"}, nguon="tay", nguoi=current_user.username)
            viec.append(f"chi tiêu {chi} $")
        if lead or pttb:
            kq = ads.nhan_lead({"page": ma, "ngay": ngay[:10], "lead": lead or 0, "pttb": pttb or 0,
                                "nguoi": current_user.username}, nguon="tay", nguoi=current_user.username)
            if kq["loi"]:
                return alert("; ".join(kq["loi"]), "bad"), no_update
            viec.append(f"{lead or 0} số điện thoại, {pttb or 0} PTTB")
        if not viec:
            return alert("Nhập chi tiêu hoặc số điện thoại / PTTB.", "warn"), no_update
        return alert(f"Đã ghi {ten} ngày {ngay[8:10]}/{ngay[5:7]}: {', '.join(viec)}.", "ok"), \
            gio_viet_nam().isoformat()

    @cb(Output("ads-sua", "data", allow_duplicate=True), Input("ads-lead-xoa", "n_clicks"),
        State("ads-g-lead", "selectedRows"), prevent_initial_call=True)
    def _xoa_lead(_n, chon):
        if not chon:
            return no_update
        ads.xoa_lead([r["id"] for r in chon], current_user.username)
        return gio_viet_nam().isoformat()
