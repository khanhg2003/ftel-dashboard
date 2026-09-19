"""Trang Ads IBB7 (chỉ Quản trị): chi tiêu quảng cáo Facebook, lead / PTTB, chia chi phí cho sale.

Năm tab: Tổng quan (theo page như DASHBOARD của sheet) · Theo sale (chi phí được chia + số bán thật trên app) ·
Tracking ngày · Hoạch định (KPI PTTB từng page) · Cấu hình (kết nối n8n, nạp file sheet cũ, page, phân công,
tên sale ↔ acc, nhập tay, nhật ký lead). Số liệu và quy tắc ở app/ads.py.
"""
from __future__ import annotations

import base64
import json
from datetime import date

import dash_ag_grid as dag
import plotly.graph_objects as go
from dash import Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate
from flask_login import current_user

from app import ads
from app.auth import ghi_log
from app.metrics import month_range
from app.thoi_gian import gio_viet_nam
from app.ui.components import (LOCALE_VI, alert, callback_can_quyen, chon_ky, field, gan_dieu_huong_ky, kpi,
                               seg_control, so_vn)
from app.ui.icons import icon

AN = {"display": "none"}
TAB = [("tong", "Tổng quan"), ("sale", "Theo sale"), ("ngay", "Tracking ngày"), ("hoach", "Hoạch định"),
       ("cauhinh", "Cấu hình")]
USD = {"function": "params.value == null ? '' : Number(params.value).toLocaleString('vi-VN', "
                   "{minimumFractionDigits: 2, maximumFractionDigits: 2})"}
SO = {"function": "params.value == null ? '' : Number(params.value).toLocaleString('vi-VN', "
                  "{maximumFractionDigits: 1})"}
VND = {"function": "params.value == null ? '' : Math.round(params.value).toLocaleString('vi-VN')"}
PCT = {"function": "params.value == null ? '' : Math.round(params.value) + '%'"}
MAU_DANH_GIA = {"styleConditions": [
    {"condition": "params.value == 'Tốt'", "style": {"color": "#0A7A3D", "fontWeight": "700"}},
    {"condition": "params.value == 'Bình thường'", "style": {"color": "#8A5709", "fontWeight": "650"}},
    {"condition": "params.value == 'Cao'", "style": {"color": "#B42318", "fontWeight": "700"}}]}
MAU_CP = {"styleConditions": [
    {"condition": f"params.value != null && params.value <= {ads.NGUONG_TOT}", "style": {"color": "#0A7A3D"}},
    {"condition": f"params.value != null && params.value > {ads.NGUONG_BINH_THUONG}",
     "style": {"color": "#B42318", "fontWeight": "700"}}]}


def _grid(id_, cot, cao=None, **kw):
    opts = {"localeText": LOCALE_VI, "suppressCellFocus": False, "enableCellTextSelection": True,
            "ensureDomOrder": True, **kw.pop("opts", {})}
    if cao is None:
        opts["domLayout"] = "autoHeight"
    return dag.AgGrid(id=id_, className="ag-theme-quartz ag-theme-ftel", columnDefs=cot, rowData=[],
                      defaultColDef={"resizable": True, "sortable": True, "filter": True},
                      dashGridOptions=opts, style={"height": f"{cao}px"} if cao else {"height": None}, **kw)


def _so(label, field_, fmt=SO, w=100, **kw):
    return {"field": field_, "headerName": label, "type": "numericColumn", "minWidth": w, "flex": 1,
            "valueFormatter": fmt, **kw}


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


def _the(tieu_de, mo_ta, *con, nut=None):
    return html.Div([html.Div([html.Div([html.H3(tieu_de), html.Div(mo_ta, className="desc")], className="the-ten"),
                               html.Div(nut, className="the-nut") if nut is not None else None], className="the-dau"),
                     *con], className="card")


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
        ], className="toolbar loc-trang"),
        dcc.Store(id="ads-sua"),                    # tín hiệu: vừa lưu cấu hình -> nạp lại số
        dcc.Loading(html.Div(id="ads-kpi", className="kpi-row kpi-7"), type="dot"),

        html.Div(id="ads-p-tong", children=[
            _the("Hiệu quả từng page", "Đánh giá theo chi phí / PTTB: ≤ 6 USD Tốt, ≤ 10 USD Bình thường, còn lại "
                 "Cao. Cùng kỳ = cùng khoảng ngày tháng trước.",
                 _grid("ads-g-page", [
                     {"field": "ten", "headerName": "Page", "pinned": "left", "minWidth": 190, "flex": 2},
                     {"field": "pic", "headerName": "Sale chạy", "minWidth": 150, "flex": 1.4},
                     _so("Chi tiêu (USD)", "chi_tieu", USD, 110),
                     _so("Tin nhắn", "tin_nhan", SO, 90), _so("Lead", "lead", SO, 80), _so("PTTB", "pttb", SO, 80),
                     _so("CPL", "cpl", USD, 80, headerTooltip="Chi tiêu / lead (USD)"),
                     _so("CP/PTTB", "cp_pttb", USD, 90, headerTooltip="Chi tiêu / PTTB (USD)", cellStyle=MAU_CP),
                     _so("Tỷ lệ chốt", "ty_le_chot", PCT, 90, headerTooltip="PTTB / lead"),
                     {"field": "danh_gia", "headerName": "Đánh giá", "minWidth": 120, "cellStyle": MAU_DANH_GIA},
                     _so("PTTB cùng kỳ", "ck_pttb", SO, 100),
                 ])),
            _the("Chi tiêu từng ngày", "Cột: chi tiêu (USD) · đường: số PTTB", dcc.Graph(id="ads-bieu-do",
                                                                                     config={"displayModeBar": False})),
        ]),
        html.Div(id="ads-p-sale", style=AN, children=[
            _the("Chi phí từng sale", "Chi tiêu mỗi page mỗi ngày chia cho sale chạy page ngày đó (đều nhau, hoặc "
                 "theo tỷ lệ đã khai); lead / PTTB chia cùng cách. Online thật lấy từ số bán trên app theo acc đã khai "
                 "ở Cấu hình → Tên sale ↔ acc.",
                 _grid("ads-g-sale", [
                     {"field": "sale", "headerName": "Sale", "pinned": "left", "minWidth": 130, "flex": 1.2},
                     {"field": "acc", "headerName": "Acc", "minWidth": 130, "flex": 1.2},
                     _so("Số page", "so_page", SO, 80),
                     _so("Chi phí (USD)", "chi_tieu", USD, 110), _so("≈ VNĐ", "vnd", VND, 120),
                     _so("Lead", "lead", SO, 80), _so("PTTB", "pttb", SO, 80),
                     _so("CP/PTTB", "cp_pttb", USD, 90, cellStyle=MAU_CP),
                     _so("Online thật", "online", SO, 100, headerTooltip="Số online của acc trên app trong kỳ"),
                     _so("Online MTTN", "online_mttn", SO, 100),
                     _so("CP / online thật", "cp_online", USD, 110,
                         headerTooltip="Chi phí ads được chia / số online thật của sale (USD)"),
                 ])),
        ]),
        html.Div(id="ads-p-ngay", style=AN, children=[
            _the("Chi tiết một page", "Chọn page (hoặc bấm vào một dòng ở bảng Tracking bên dưới) để xem từng ngày: "
                 "chạy bao nhiêu tiền, bao nhiêu lead / PTTB, ai chạy, camp nào.",
                 _grid("ads-g-ct", [
                     {"field": "ngay", "headerName": "Ngày", "pinned": "left", "width": 80},
                     _so("Chi tiêu", "chi_tieu", USD, 95), _so("Tin nhắn", "tin_nhan", SO, 90),
                     _so("Lead", "lead", SO, 70), _so("PTTB", "pttb", SO, 70),
                     _so("CPL", "cpl", USD, 80), _so("CP/PTTB", "cp_pttb", USD, 90, cellStyle=MAU_CP),
                     {"field": "sale", "headerName": "Sale chạy", "minWidth": 150, "flex": 1.3},
                     {"field": "camp", "headerName": "Camp", "minWidth": 220, "flex": 2, "tooltipField": "camp"}],
                     cao=420, opts={"pinnedBottomRowData": []}),
                 nut=dcc.Dropdown(id="ads-ct-page", placeholder="Chọn page…", style={"minWidth": "260px"})),
            _the("Tracking ngày", "Mỗi dòng một page, mỗi cột một ngày. Bấm vào một dòng để xem chi tiết page đó ở trên.",
                 _grid("ads-g-ngay", [], cao=620, opts={"rowSelection": {"mode": "singleRow", "checkboxes": False, "enableClickSelection": True}}),
                 nut=seg_control("ads-chi-so", [("chi_tieu", "Chi tiêu"), ("tin_nhan", "Tin nhắn"), ("lead", "Lead"),
                                                ("pttb", "PTTB")], "chi_tieu")),
        ]),
        html.Div(id="ads-p-hoach", style=AN, children=[
            _the("Hoạch định PTTB", "Dự kiến cả tháng theo nhịp hiện tại. Nhập KPI PTTB vào cột KPI (bấm đúp ô) rồi "
                 "Lưu. Khuyến nghị: CP/PTTB từ 4 USD → tối ưu camp; đạt hoặc dự kiến đạt KPI → giữ vững; còn lại → "
                 "tăng nhẹ ngân sách.",
                 _grid("ads-g-hoach", [
                     {"field": "ten", "headerName": "Page", "pinned": "left", "minWidth": 190, "flex": 2},
                     _so("Chi tiêu", "chi_tieu", USD, 95), _so("PTTB", "pttb", SO, 70),
                     _so("CP/PTTB", "cp_pttb", USD, 85, cellStyle=MAU_CP), _so("TB/ngày", "tb_ngay", USD, 85),
                     _so("Dự kiến chi", "du_kien_chi", USD, 100), _so("Dự kiến PTTB", "du_kien_pttb", SO, 100),
                     _so("KPI PTTB ✎", "kpi", SO, 95, editable=True,
                         cellStyle={"backgroundColor": "#FFF8E6", "fontWeight": "700"}),
                     _so("Ngân sách cần", "ngan_sach_can", USD, 110),
                     _so("Cần thêm/ngày", "can_them_ngay", USD, 110), _so("Tiến độ KPI", "tien_do", PCT, 95),
                     {"field": "khuyen_nghi", "headerName": "Khuyến nghị", "minWidth": 150, "flex": 1.2},
                 ], getRowId="params.data.page_id"),
                 nut=html.Div([
                     html.Span("Tỷ giá USD → VNĐ", className="desc", style={"margin": "0 6px 0 0"}),
                     dcc.Input(id="ads-ty-gia", type="number", min=1000, step=1, className="inp",
                               style={"width": "110px"}),
                     html.Button([icon("save", 14), html.Span("Lưu KPI & tỷ giá")], id="ads-luu-hoach",
                                 className="btn primary")], style={"display": "flex", "alignItems": "center",
                                                                   "gap": "8px"})),
            html.Div(id="ads-msg-hoach"),
        ]),
        html.Div(id="ads-p-cauhinh", style=AN, children=_cau_hinh()),
    ])


def _cau_hinh():
    return [
        _the("Kết nối n8n và bot Telegram", "n8n gửi thẳng vào app thay cho Google Sheet. Gửi lại cùng page + camp "
             "+ ngày thì ghi đè, không nhân đôi. Page mới tự xuất hiện ở danh mục bên dưới.",
             html.Div(id="ads-token-tt"),
             html.Pre(id="ads-mau-json", className="khoi-ma"),
             nut=html.Button([icon("refresh", 14), html.Span("Tạo mã kết nối mới")], id="ads-tao-ma",
                             className="btn")),
        _the("Nạp file Google Sheet cũ", "Tải file 'BÁO CÁO CHI TIÊU ADS' (định dạng .xlsx) về rồi thả vào đây để đưa "
             "số các tháng đã chạy trên sheet lên app: chi tiêu, lead / PTTB, người chạy từng page, tỷ lệ chia riêng. "
             "Nạp lại không bị nhân đôi.",
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
        _the("Danh mục page", "Sửa trực tiếp trong ô (bấm đúp) rồi Lưu. Loại 'Công ty' = chạy tài khoản công ty, không "
             "chia chi phí cho sale.",
             _grid("ads-g-dm", [
                 {"field": "ma", "headerName": "Tên chuẩn (n8n gửi)", "minWidth": 190, "flex": 1.4},
                 {"field": "ten", "headerName": "Tên hiển thị ✎", "editable": True, "minWidth": 190, "flex": 1.6},
                 {"field": "loai", "headerName": "Loại ✎", "editable": True, "minWidth": 110,
                  "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": ["Sale", "Công ty"]}},
                 {"field": "tinh_trang", "headerName": "Tình trạng ✎", "editable": True, "minWidth": 120,
                  "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": ads.TINH_TRANG_PAGE}},
                 {"field": "ghi_chu", "headerName": "Ghi chú ✎", "editable": True, "minWidth": 200, "flex": 2},
             ], cao=360, getRowId="params.data.id"),
             html.Div(id="ads-msg-dm"),
             nut=html.Button([icon("save", 14), html.Span("Lưu danh mục")], id="ads-dm-luu", className="btn primary")),
        _the("Tên sale ↔ acc", "Nối tên gọi trong phân công (VD 'C. Chi') với acc inside để so chi phí ads với số "
             "online thật của sale. Sửa cột Acc (bấm đúp) rồi Lưu.",
             _grid("ads-g-sale-acc", [
                 {"field": "ten", "headerName": "Tên gọi", "minWidth": 140, "flex": 1},
                 {"field": "acc", "headerName": "Acc inside ✎", "editable": True, "minWidth": 180, "flex": 1.4}],
                 cao=320, getRowId="params.data.ten"),
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
                 field("Lead", dcc.Input(id="ads-tay-lead", type="number", step=1, className="inp",
                                         style={"width": "80px"})),
                 field("PTTB", dcc.Input(id="ads-tay-pttb", type="number", step=1, className="inp",
                                         style={"width": "80px"})),
                 field(" ", html.Button([icon("plus", 14), html.Span("Ghi")], id="ads-tay-ghi",
                                        className="btn primary")),
             ], className="toolbar", style={"flexWrap": "wrap"}),
             html.Div(id="ads-msg-tay")),
        _the("Nhật ký lead / PTTB", "Mỗi lần bot Telegram hoặc nhập tay báo có số là một dòng. Nhập nhầm thì chọn dòng "
             "rồi Xoá.",
             _grid("ads-g-lead", [
                 {"field": "ngay", "headerName": "Ngày", "minWidth": 100, "checkboxSelection": True},
                 {"field": "page", "headerName": "Page", "minWidth": 180, "flex": 1.6},
                 _so("Lead", "lead", SO, 70), _so("PTTB", "pttb", SO, 70),
                 {"field": "nguon", "headerName": "Nguồn", "minWidth": 90},
                 {"field": "nguoi", "headerName": "Người nhập", "minWidth": 120},
                 {"field": "ghi_chu", "headerName": "Ghi chú", "minWidth": 160, "flex": 1.4},
                 {"field": "luc", "headerName": "Lúc", "minWidth": 140}], cao=360, getRowId="params.data.id",
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


def _mau_json(host: str) -> str:
    return (f"# 1) n8n 7h30 - chi tiêu hôm qua (node HTTP Request, method POST)\n"
            f"URL: {host}/api/ads/chi-tieu\nHeader: X-Ads-Token: <mã kết nối>\nBody (JSON):\n"
            + json.dumps({"page": "KON TUM", "rows": [{"camp": "TCDT_KONTUM_4", "tinh_trang": "HOẠT ĐỘNG",
                                                        "ngay": "2026-09-18", "chi_tieu": 4.56, "tin_nhan": 3}]},
                         ensure_ascii=False, indent=2)
            + f"\n\n# 2) bot Telegram - mỗi lần có số điện thoại / PTTB\nURL: {host}/api/ads/lead\n"
              "Header: X-Ads-Token: <mã kết nối>\nBody (JSON):\n"
            + json.dumps({"page": "QUẢNG NGÃI", "lead": 1, "pttb": 1, "ngay": "2026-09-19",
                          "nguoi": "Kiều", "ghi_chu": ""}, ensure_ascii=False, indent=2)
            + "\n\n'page' = tên trang tính trên sheet cũ (tên chuẩn). 'ngay' bỏ trống ở lead = hôm nay.")


def register(app):
    cb = callback_can_quyen(app, "duoc_cau_hinh")
    gan_dieu_huong_ky(app, "ads-thang")

    @app.callback(*[Output(f"ads-p-{k}", "style") for k, _ in TAB], Input("ads-tab", "value"))
    def _doi_tab(tab):
        return [{} if k == tab else AN for k, _ in TAB]

    @cb(Output("ads-kpi", "children"), Output("ads-badge", "children"), Output("ads-g-page", "rowData"),
        Output("ads-bieu-do", "figure"), Output("ads-g-sale", "rowData"), Output("ads-ty-gia", "value"),
        Input("ads-thang", "value"), Input("ads-sua", "data"))
    def _nap(thang, _s):
        tu, den = _ky(thang)
        t = ads.tong_quan(tu, den)
        ck = t["ck"]

        def doi(a, b):
            return "" if not b else f" · cùng kỳ {so_vn(b)}"
        the = [
            kpi("Chi tiêu", f"{_usd(t['chi_tieu'])} $", f"≈ {so_vn(t['vnd'] / 1e6, 1)} triệu đồng" + doi(0, 0)),
            kpi("Tin nhắn", so_vn(t["tin_nhan"]), doi(0, ck["tin_nhan"]).lstrip(" ·") or None),
            kpi("Lead (số điện thoại)", so_vn(t["lead"]), f"CPL {_usd(t['cpl'])} $"),
            kpi("PTTB", so_vn(t["pttb"]), doi(0, ck["pttb"]).lstrip(" ·") or None),
            kpi("Chi phí / PTTB", f"{_usd(t['cp_pttb'])} $",
                f"cùng kỳ {_usd(t['ck_cp_pttb'])} $" if t["ck_cp_pttb"] else None,
                "" if t["cp_pttb"] is None else ("ok" if t["cp_pttb"] <= ads.NGUONG_TOT else
                                                  "warn" if t["cp_pttb"] <= ads.NGUONG_BINH_THUONG else "bad")),
            kpi("Tỷ lệ chốt", "–" if t["ty_le_chot"] is None else f"{t['ty_le_chot']:.0f}%", "PTTB / lead"),
            kpi("Page có chi tiêu", so_vn(t["so_page"]), f"tỷ giá {so_vn(t['ty_gia'])}"),
        ]
        badge = (html.Span(f"Ads đến {t['ngay_moi_nhat']:%d/%m}", className="badge muted")
                 if t["ngay_moi_nhat"] else html.Span("Chưa có số tháng này", className="badge warn"))
        tp = ads.theo_page(tu, den)
        df = ads.theo_ngay(tu, den)
        fig = go.Figure()
        if len(df):
            g = df.groupby("ngay")[["chi_tieu", "pttb"]].sum().reset_index()
            fig.add_bar(x=g.ngay, y=g.chi_tieu, name="Chi tiêu (USD)", marker_color="#0072BC",
                        hovertemplate="%{x|%d/%m}: %{y:,.2f} $<extra></extra>")
            fig.add_scatter(x=g.ngay, y=g.pttb, name="PTTB", yaxis="y2", mode="lines+markers",
                            line={"color": "#F37021", "width": 2},
                            hovertemplate="%{x|%d/%m}: %{y} PTTB<extra></extra>")
        fig.update_layout(height=300, margin={"l": 40, "r": 40, "t": 10, "b": 30}, plot_bgcolor="white",
                          legend={"orientation": "h", "y": 1.12}, xaxis={"tickformat": "%d/%m"},
                          yaxis={"title": None, "gridcolor": "#EEF2F6"},
                          yaxis2={"overlaying": "y", "side": "right", "showgrid": False})
        ts = ads.theo_sale(tu, den)
        if len(ts):
            ts["vnd"] = ts.chi_tieu * t["ty_gia"]
        return (the, badge, _ban_ghi(tp), fig, _ban_ghi(ts), round(ads.ty_gia(thang)))

    @cb(Output("ads-g-ngay", "columnDefs"), Output("ads-g-ngay", "rowData"),
        Input("ads-thang", "value"), Input("ads-chi-so", "value"), Input("ads-sua", "data"))
    def _tracking(thang, chi_so, _s):
        pv, so_ngay = ads.tracking(thang, chi_so or "chi_tieu")
        fmt = USD if chi_so == "chi_tieu" else SO
        cot = [{"field": "ten", "headerName": "Page", "pinned": "left", "minWidth": 180},
               {"field": "tong", "headerName": "Tổng", "pinned": "left", "width": 95, "type": "numericColumn",
                "valueFormatter": fmt, "cellStyle": {"fontWeight": "700"}}]
        cot += [{"field": str(i), "headerName": str(i), "width": 62, "type": "numericColumn",
                 "valueFormatter": {"function": "params.value ? " + fmt["function"] + " : ''"}}
                for i in range(1, so_ngay + 1)]
        if pv.empty:
            return cot, []
        pv.columns = [str(c) for c in pv.columns]
        return cot, _ban_ghi(pv)

    @cb(Output("ads-ct-page", "options"), Input("ads-thang", "value"), Input("ads-sua", "data"))
    def _ct_opts(thang, _s):
        tu, den = _ky(thang)
        tp = ads.theo_page(tu, den)
        return [{"label": f"{t} ({c:,.2f}$ · {int(p)} PTTB)", "value": int(i)}
                for i, t, c, p in zip(tp.page_id, tp.ten, tp.chi_tieu, tp.pttb)]

    @cb(Output("ads-ct-page", "value"), Input("ads-g-ngay", "selectedRows"), prevent_initial_call=True)
    def _ct_bam(rows):
        if not rows or rows[0].get("page_id") is None:
            raise PreventUpdate
        return int(rows[0]["page_id"])

    @cb(Output("ads-g-ct", "rowData"), Output("ads-g-ct", "dashGridOptions"),
        Input("ads-ct-page", "value"), Input("ads-thang", "value"), Input("ads-sua", "data"),
        State("ads-g-ct", "dashGridOptions"))
    def _ct(pid, thang, _s, opts):
        opts = dict(opts or {})
        if not pid:
            opts["pinnedBottomRowData"] = []
            return [], opts
        tu, den = _ky(thang)
        df = ads.chi_tiet_page(int(pid), tu, den)
        if df.empty:
            opts["pinnedBottomRowData"] = []
            return [], opts
        t = {c: float(df[c].sum()) for c in ("chi_tieu", "tin_nhan", "lead", "pttb")}
        opts["pinnedBottomRowData"] = [{"ngay": "Tổng", **t,
                                        "cpl": round(t["chi_tieu"] / t["lead"], 2) if t["lead"] else None,
                                        "cp_pttb": round(t["chi_tieu"] / t["pttb"], 2) if t["pttb"] else None}]
        return _ban_ghi(df), opts

    @cb(Output("ads-g-hoach", "rowData"), Input("ads-thang", "value"), Input("ads-sua", "data"))
    def _hoach(thang, _s):
        tu, den = _ky(thang)
        return _ban_ghi(ads.hoach_dinh(thang, den))

    @cb(Output("ads-msg-hoach", "children"), Output("ads-sua", "data", allow_duplicate=True),
        Input("ads-luu-hoach", "n_clicks"), State("ads-g-hoach", "rowData"), State("ads-ty-gia", "value"),
        State("ads-thang", "value"), prevent_initial_call=True)
    def _luu_hoach(_n, rows, rate, thang):
        kpi_ = {}
        for r in rows or []:
            v = r.get("kpi")
            try:
                kpi_[int(r["page_id"])] = int(float(v)) if v not in (None, "") else None
            except (TypeError, ValueError):
                return alert(f"KPI của {r.get('ten')} phải là số.", "bad"), no_update
        ads.luu_thang(thang, float(rate) if rate else None, kpi_, current_user.username)
        return alert("Đã lưu KPI PTTB và tỷ giá.", "ok"), gio_viet_nam().isoformat()

    # ------------------------------------------------ cấu hình
    @cb(Output("ads-g-pic", "rowData"), Output("ads-g-dm", "rowData"), Output("ads-g-sale-acc", "rowData"),
        Output("ads-g-lead", "rowData"), Output("ads-pic-page", "options"), Output("ads-pic-sale", "options"),
        Output("ads-tay-page", "options"), Output("ads-token-tt", "children"), Output("ads-mau-json", "children"),
        Input("ads-tab", "value"), Input("ads-sua", "data"), State("ads-thang", "value"))
    def _nap_cau_hinh(tab, _s, thang):
        if tab != "cauhinh":
            return (no_update,) * 9
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
                _mau_json(request.host_url.rstrip("/")))

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
        n = ads.luu_page([{**r, "loai": "cong_ty" if r.get("loai") == "Công ty" else "sale"} for r in rows or []],
                         current_user.username)
        return alert(f"Đã lưu {n} page thay đổi.", "ok"), gio_viet_nam().isoformat()

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
            viec.append(f"{lead or 0} lead, {pttb or 0} PTTB")
        if not viec:
            return alert("Nhập chi tiêu hoặc lead / PTTB.", "warn"), no_update
        return alert(f"Đã ghi {ten} ngày {ngay[8:10]}/{ngay[5:7]}: {', '.join(viec)}.", "ok"), \
            gio_viet_nam().isoformat()

    @cb(Output("ads-sua", "data", allow_duplicate=True), Input("ads-lead-xoa", "n_clicks"),
        State("ads-g-lead", "selectedRows"), prevent_initial_call=True)
    def _xoa_lead(_n, chon):
        if not chon:
            return no_update
        ads.xoa_lead([r["id"] for r in chon], current_user.username)
        return gio_viet_nam().isoformat()
