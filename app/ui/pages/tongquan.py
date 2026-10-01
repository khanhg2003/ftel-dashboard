"""Trang Báo cáo Tổng - bảng tổng hợp theo phòng, dùng để họp giao ban và chụp gửi nhóm.

Bố cục theo thứ tự người xem cần:
1. Thanh lọc (ngày + chi nhánh) nằm chung một hàng, dính trên đầu khi cuộn.
2. Trạng thái số liệu: ngày đang cập nhật hay đã chốt - tránh chụp số tạm tính mà tưởng số chốt.
3. Năm chỉ số chính.
4. Bảng theo phòng: mặc định vừa khít màn hình, chỉnh cỡ bằng nút − / +, có chú thích màu.

Bảng rộng hơn màn hình laptop nên chế độ "Vừa màn hình" đo bề rộng cửa sổ ở trình duyệt
(store `ui-vw`) rồi tính tỷ lệ thu nhỏ. Trên điện thoại không thu nhỏ quá tay mà cho kéo ngang,
cột Phòng ghim bên trái, và mặc định dùng bảng "Gọn" chỉ gồm các cột chính.
"""
from __future__ import annotations

from datetime import date, timedelta

import dash_ag_grid as dag
from dash import Input, Output, State, ctx, dcc, html, no_update
from flask_login import current_user

from app.config import rules_config
from app.export_excel import xuat_tong_quan
from app.export_png import anh_tong_quan
from app.metrics import cac_ngay_co_du_lieu
from app import tro_ly_du_lieu as dl
from app.du_bao import du_bao_thang
from app.org import loc_chi_nhanh
from app.overview import TEN_PHAM_VI, bang_tong_quan, lui_mot_thang, trang_thai_ngay
from app.ui.components import chi_nhanh_control, field, kpi, seg_control
from app.ui.luoi import PCT, SO
from app.ui import ky_chung as kc
from app.ui import lien_ket as lk
from app.ui import tro_ly as tl
from app.ui.icons import icon

# thang màu giống bảng tính: đỏ nhạt -> cam -> vàng -> xanh nhạt -> xanh
MAU_HEAT = [("#F7BDBD", "#7F1D1D"), ("#FBD9AE", "#7C3A06"), ("#FCEBB4", "#6B5104"),
            ("#D3EBD4", "#14532D"), ("#A5DCAF", "#0F3D22")]
ZOOM_STEPS = [50, 60, 70, 80, 90, 100, 110, 125, 150]
BE_NGANG_CHUA_BANG = 124       # lề trang + padding thẻ + thanh cuộn, trừ khi tính cỡ vừa màn hình
MAN_HINH_NHO = 768             # dưới mức này coi là điện thoại
TY_LE_TOI_THIEU_DT = 0.8       # điện thoại: không thu nhỏ hơn mức này, thừa thì kéo ngang



# PTTB CNQL kèm số MTTN trong ngoặc (chốt với chủ app 01/10/2026) - chỉ hiện ở dòng có cột `mttn_hien`
# bật (IBB7 và dòng tổng bầy chứa IBB7, xem app/overview.py). Định dạng ở đây (không ở Python) vì giá
# trị gốc "cnql"/"cnql_ty_le" phải giữ số thuần cho Excel export và trợ lý AI đọc.
SO_CNQL_MTTN = {"function": (
    "params.value == null ? '' : Number(params.value).toLocaleString('vi-VN') + "
    "(params.data && params.data.mttn_hien && params.data.mttn != null "
    "? ' (' + Number(params.data.mttn).toLocaleString('vi-VN') + ')' : '')")}
PCT_CNQL_MTTN = {"function": (
    "params.value == null ? '' : Math.round(params.value) + '%' + "
    "(params.data && params.data.mttn_hien && params.data.mttn_ty_le != null "
    "? ' (' + Math.round(params.data.mttn_ty_le) + '%)' : '')")}


def _heat(kind: str, gia_tri: str = "params.value") -> dict:
    """Sinh điều kiện tô màu theo ngưỡng trong config/rules.yml.

    `gia_tri`: biểu thức JS lấy số để so ngưỡng, mặc định là chính giá trị ô."""
    t = rules_config()["heatmap"][kind]
    moc = [t["rat_kem"], t["kem"], t["trung_binh"], t["kha"]]
    dk = []
    for i, (bg, fg) in enumerate(MAU_HEAT):
        cond = (f"{gia_tri} != null && {gia_tri} < {moc[i]}" if i < len(moc)
                else f"{gia_tri} != null")
        dk.append({"condition": cond,
                   "style": {"backgroundColor": bg, "color": fg, "fontWeight": "600"}})
    return {"styleConditions": dk}


# Dòng có hiện MTTN trong ngoặc thì màu cột Tỷ lệ PTTB CNQL cũng phải tô theo đúng số MTTN đó, không
# phải số CNQL đứng trước - chốt với chủ app 01/10/2026 (nhìn đỏ theo CNQL dễ hiểu lầm trong khi MTTN
# đang ổn hơn hẳn). Các dòng không có MTTN thì vẫn tô theo params.value (= cnql_ty_le) như cũ.
_GIA_TRI_HEAT_CNQL = ("(params.data && params.data.mttn_hien && params.data.mttn_ty_le != null "
                     "? params.data.mttn_ty_le : params.value)")


KET_LUAN_STYLE = {"styleConditions": [
    {"condition": "params.value == 'Đạt'",
     "style": {"backgroundColor": "#DCF5E6", "color": "#0A5B31", "fontWeight": "700"}},
    {"condition": "params.value == 'Không đạt'",
     "style": {"backgroundColor": "#FBE3E1", "color": "#93241C", "fontWeight": "600"}},
    {"condition": "params.value == 'Chưa đạt'",
     "style": {"backgroundColor": "#FDF1D8", "color": "#8A5709", "fontWeight": "600"}},
]}

ROW_STYLE = {"styleConditions": [
    {"condition": "params.data.loai_dong == 'subtotal'",
     "style": {"backgroundColor": "#D5E3F1", "fontWeight": "700", "color": "#B01E14"}},
    {"condition": "params.data.loai_dong == 'chinhanh'",
     "style": {"backgroundColor": "#C3D8EC", "fontWeight": "700", "color": "#002B4E"}},
    {"condition": "params.data.loai_dong == 'total'",
     "style": {"backgroundColor": "#A9C6E3", "fontWeight": "800", "color": "#002B4E"}},
]}


def topbar():
    return [html.Div([html.H1("Báo cáo Tổng"),
                      html.Div("Kết quả kinh doanh theo phòng, trong kỳ đã chọn", className="sub")]),
            html.Div(className="spacer"),
            html.Div(id="tq-badge")]


def layout(ky: dict | None = None):
    ky = ky or {}
    ngays = cac_ngay_co_du_lieu()
    moi_nhat = ngays[-1] if ngays else None
    den = kc.ngay_co_so(ky.get("den"), ngays) if ky.get("den") else moi_nhat
    tu = ky.get("tu") if ky.get("tu") and den and ky["tu"] <= den else ((den[:8] + "01") if den else None)
    if tu and ngays and tu < ngays[0][:8] + "01":
        tu = ngays[0][:8] + "01"
    return html.Div([
        html.Div([
            field("Kỳ báo cáo · từ ngày - đến ngày", html.Div([
                html.Button("‹", id="tq-lui", className="nut-ky", title="Lùi một ngày"),
                dcc.DatePickerRange(
                    id="tq-khoang", start_date=tu,
                    end_date=den, display_format="DD/MM/YYYY",
                    min_date_allowed=(ngays[0][:8] + "01") if ngays else None,
                    max_date_allowed=ngays[-1] if ngays else None,
                    initial_visible_month=den, first_day_of_week=1, clearable=False,
                    minimum_nights=0, start_date_placeholder_text="Từ ngày",
                    end_date_placeholder_text="Đến ngày", className="date-pick khoang"),
                html.Button("›", id="tq-toi", className="nut-ky", title="Tới một ngày"),
                html.Button("Mới nhất", id="tq-p-moinhat", className="btn nho",
                            title="Luỹ kế từ ngày 01 đến ngày có số mới nhất"),
                dcc.Dropdown(id="tq-nhanh", placeholder="Chọn nhanh", searchable=False,
                             clearable=False, className="chon-nhanh", options=[
                                 {"label": "Luỹ kế tháng này", "value": "luyke"},
                                 {"label": "Riêng ngày mới nhất", "value": "motngay"},
                                 {"label": "7 ngày gần nhất", "value": "7ngay"},
                                 {"label": "Tuần này (từ thứ 2)", "value": "tuan"},
                                 {"label": "Cùng kỳ tháng trước", "value": "cungky"},
                                 {"label": "Cả tháng trước", "value": "thangtruoc"}]),
            ], className="chon-ngay")),
            field("Chi nhánh", chi_nhanh_control("tq-cn", ky.get("cn", "all"))),
        ], className="toolbar loc-trang"),
        dcc.Download(id="tq-tai-xuong"),
        dcc.Store(id="tq-ty-le", data=1),

        html.Div([
            html.Div(id="tq-canh-bao-chu", className="grow"),
            html.Button(id="tq-xem-chot", className="btn nho", hidden=True),
        ], id="tq-canh-bao", className="alert warn thanh-canh-bao", hidden=True),

        html.Div(id="tq-kpi", className="kpi-row"),

        html.Div([
            html.Div([
                html.Div([html.H3(id="tq-tieu-de"), html.Div(id="tq-mo-ta", className="desc")],
                         className="the-ten"),
                html.Div([
                    html.Div(seg_control("tq-cot", [("day", "Đủ cột"), ("gon", "Gọn")], "day"),
                             title="Gọn: chỉ giữ các cột chính, hợp xem trên điện thoại"),
                    html.Div([
                        html.Button("−", id="tq-nho", className="btn", title="Thu nhỏ bảng"),
                        dcc.Dropdown(id="tq-zoom-chon", value="fit", clearable=False,
                                     searchable=False, className="zoom-chon",
                                     options=[{"label": "Vừa màn hình", "value": "fit"}]
                                     + [{"label": f"{z}%", "value": z} for z in ZOOM_STEPS]),
                        html.Button("+", id="tq-to", className="btn", title="Phóng to bảng"),
                    ], className="zoom-box"),
                    html.Button([icon("camera", 14), html.Span("Chụp ảnh")], id="tq-png",
                                className="btn primary",
                                title="Tải ảnh PNG đủ toàn bộ bảng để gửi nhóm Zalo"),
                    html.Button([icon("download", 14), html.Span("Excel")], id="tq-xls",
                                className="btn", title="Tải file Excel giữ nguyên định dạng"),
                ], className="the-nut"),
            ], className="the-dau"),
            _chu_giai(),
            html.Div(dcc.Loading(dag.AgGrid(
                id="tq-grid", className="ag-theme-quartz ag-theme-ftel", columnDefs=[], rowData=[],
                getRowId=lk.ROW_ID,
                defaultColDef={"resizable": True, "sortable": False, "suppressMovable": True,
                               "wrapHeaderText": True, "autoHeaderHeight": True,
                               "cellClass": "o-giua", "headerClass": "tieu-de-giua"},
                dashGridOptions={"suppressCellFocus": True, "headerHeight": 42,
                                 "groupHeaderHeight": 30, "rowHeight": 32,
                                 "domLayout": "autoHeight", "suppressColumnVirtualisation": True,
                                 "tooltipShowDelay": 300,
                                 # kẻ đậm dưới dòng tổng mỗi bầy để các bầy tách bạch
                                 "rowClassRules": {
                                     "dong-tong-bay": "params.data.loai_dong == 'subtotal'",
                                     "dong-tong-cn": "params.data.loai_dong == 'chinhanh'",
                                     "dong-tong": "params.data.loai_dong == 'total'"}},
                getRowStyle=ROW_STYLE, style={"width": "100%"})),
                id="tq-zoom-wrap", className="zoom-wrap"),
        ], className="card"),
        tl.the_ai("tq", "Dự báo cuối tháng & nhận xét", tl.MO_TA_DU_BAO,
                  html.Div([tl.bang_du_bao("tq-du-bao"),
                            html.Div(id="tq-du-bao-loi", style={"marginTop": "8px"})])),
    ])


def _chu_giai():
    """Chú thích màu - lấy đúng ngưỡng trong config/rules.yml để luôn khớp với bảng."""
    t = rules_config()["heatmap"]

    def dong(ten: str, kind: str):
        m = t[kind]
        moc = [m["rat_kem"], m["kem"], m["trung_binh"], m["kha"]]
        def so(x):
            return f"−{abs(x)}" if x < 0 else str(x)
        nhan = ([f"Dưới {so(moc[0])}%"]
                + [f"{so(moc[i])} đến {so(moc[i + 1] - 1)}%" for i in range(3)]
                + [f"Từ {so(moc[3])}%"])
        return html.Div([html.Span(ten, className="cg-ten")] + [
            html.Span(n, className="cg-o", style={"background": bg, "color": fg})
            for n, (bg, fg) in zip(nhan, MAU_HEAT)], className="cg-dong")

    return html.Details([
        html.Summary("Cách đọc màu và kết luận"),
        html.Div([
            dong("Tỷ lệ HTKH", "htkh"),
            dong("Tăng trưởng", "tang_truong"),
            dong("FPL/NET · CNQL · VVIP", "ty_le"),
            html.Div([html.Span("Kết luận", className="cg-ten"),
                      html.Span("Online trong ngày so với mục tiêu ngày. "
                                "“Chưa đạt” là ngày còn đang cập nhật số.", className="cg-ghi")],
                     className="cg-dong"),
        ], className="cg-than"),
    ], className="chu-giai")


def _tu_hop_le(tu_iso: str | None, den: date) -> str:
    """Ngày bắt đầu hợp lệ: trống hoặc sau ngày cuối thì lấy ngày 01 của tháng ngày cuối."""
    tu = (tu_iso or "")[:10]
    if not tu or tu > den.isoformat():
        return den.replace(day=1).isoformat()
    return tu


def doi_ky(nut: str | None, nhanh: str | None, tu: str | None, den: str | None,
           ngays: list[str]) -> tuple[str, str] | None:
    """(từ ngày, đến ngày) mới khi bấm ‹ ›, Mới nhất, Xem ngày đã chốt hoặc Chọn nhanh.

    ‹ ›: dời ngày cuối sang ngày có số liền trước/sau. Đang xem luỹ kế (từ ngày 01) thì giữ luỹ kế
    của tháng mới; đang xem khoảng tự chọn thì dời cả khoảng, giữ nguyên số ngày.
    """
    moi = ngays[-1]
    den = (den or moi)[:10]
    d_den = date.fromisoformat(den)
    tu = _tu_hop_le(tu, d_den)
    d_tu = date.fromisoformat(tu)
    luy_ke = d_tu == d_den.replace(day=1)

    def _luy_ke(ngay_cuoi: str) -> tuple[str, str]:
        return ngay_cuoi[:8] + "01", ngay_cuoi

    if nut in ("tq-lui", "tq-toi"):
        ds = [x for x in ngays if x < den] if nut == "tq-lui" else [x for x in ngays if x > den]
        if not ds:
            return None
        moi_den = ds[-1] if nut == "tq-lui" else ds[0]
        if luy_ke:
            return _luy_ke(moi_den)
        return (d_tu + (date.fromisoformat(moi_den) - d_den)).isoformat(), moi_den
    if nut == "tq-p-moinhat":
        return _luy_ke(moi)
    if nut == "tq-xem-chot":
        truoc = [x for x in ngays if x < moi]
        return _luy_ke(truoc[-1]) if truoc else None
    if nut == "tq-nhanh" and nhanh:
        d_moi = date.fromisoformat(moi)
        if nhanh == "luyke":
            return _luy_ke(moi)
        if nhanh == "motngay":
            return moi, moi
        if nhanh == "7ngay":
            return (d_moi - timedelta(days=6)).isoformat(), moi
        if nhanh == "tuan":
            return (d_moi - timedelta(days=d_moi.weekday())).isoformat(), moi
        if nhanh == "cungky":
            return lui_mot_thang(d_tu).isoformat(), lui_mot_thang(d_den).isoformat()
        if nhanh == "thangtruoc":
            cuoi = d_den.replace(day=1) - timedelta(days=1)
            return cuoi.replace(day=1).isoformat(), cuoi.isoformat()
    return None


def _khoang_ngay(ngays):
    """Mọi ngày trong khoảng dữ liệu - dùng để chặn ngày chưa có số trên lịch."""
    if not ngays:
        return []
    d0, d1 = date.fromisoformat(ngays[0]), date.fromisoformat(ngays[-1])
    return [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def _cols(thang: str, ngay: int, gon: bool = False, tu: str | None = None):
    from app.overview import ten_khoang
    thang_so = int(thang[5:7])
    thang_truoc = 12 if thang_so == 1 else thang_so - 1
    d_den = date.fromisoformat(f"{thang}-{ngay:02d}")
    d_tu = date.fromisoformat(tu) if tu else d_den.replace(day=1)
    luy_ke = d_tu == d_den.replace(day=1)
    nhan_ky = ten_khoang(d_tu, d_den)
    nhan_gon = f"T{thang_so}" if luy_ke else nhan_ky
    w = 72
    phong = {"headerName": "PKD", "field": "phong", "pinned": "left", "width": 172,
             "cellClass": "", "headerClass": "",
             "cellStyle": {"textAlign": "left", "fontWeight": "600"}}
    ket_luan = {"headerName": "Kết luận", "field": "ket_luan", "width": 96,
                "cellStyle": KET_LUAN_STYLE,
                "headerTooltip": "Online trong ngày so với mục tiêu ngày"}
    if gon:
        return [
            {**phong, "width": 124},
            {"headerName": f"INTERNET {nhan_gon}", "children": [
                {"headerName": "Online", "field": "online", "width": 64, "valueFormatter": SO,
                 "cellStyle": {"textAlign": "center", "fontWeight": "700"}},
                {"headerName": "HTKH", "field": "htkh_internet", "width": 60,
                 "valueFormatter": PCT, "cellStyle": _heat("htkh")},
                {"headerName": "Tăng trưởng", "field": "tang_truong", "width": 84,
                 "valueFormatter": PCT, "cellStyle": _heat("tang_truong")},
            ]},
            {"headerName": f"NGÀY {ngay:02d}/{thang_so:02d}", "children": [
                {"headerName": "Online", "field": "ngay_online", "width": 62,
                 "valueFormatter": SO},
                {**ket_luan, "width": 88},
            ]},
        ]
    return [
        phong,
        {"headerName": "Nhân sự", "field": "nhan_su", "pinned": "left", "width": 70,
         "valueFormatter": SO},
        {"headerName": f"INTERNET {nhan_ky}", "children": [
            {"headerName": "Mục tiêu", "field": "mt_internet", "width": w, "valueFormatter": SO},
            {"headerName": "Số tồn", "field": "so_ton", "width": w, "valueFormatter": SO},
            {"headerName": "Số online", "field": "online", "width": 78, "valueFormatter": SO,
             "cellStyle": {"textAlign": "center", "fontWeight": "700"}},
            {"headerName": "Tỷ lệ HTKH", "field": "htkh_internet", "width": 76,
             "valueFormatter": PCT, "cellStyle": _heat("htkh")},
        ]},
        {"headerName": "TĂNG TRƯỞNG", "children": [
            {"headerName": f"Cùng kỳ T{thang_truoc}" if luy_ke else "Cùng kỳ th. trước",
             "field": "ck_online", "width": 78, "valueFormatter": SO,
             "headerTooltip": "Số online cùng khoảng ngày của tháng trước"},
            {"headerName": "Tỷ lệ", "field": "tang_truong", "width": w, "valueFormatter": PCT,
             "cellStyle": _heat("tang_truong")},
        ]},
        {"headerName": "FPT PLAY", "children": [
            {"headerName": "Combo", "field": "fpl_combo", "width": w, "valueFormatter": SO},
            {"headerName": "Tỷ lệ FPL/NET", "field": "fpl_ty_le", "width": 82,
             "valueFormatter": PCT, "cellStyle": _heat("ty_le")},
        ]},
        {"headerName": "PTTB CNQL", "children": [
            {"headerName": "Số online ⓘ", "field": "cnql", "width": 110, "valueFormatter": SO_CNQL_MTTN,
             "headerClass": "co-chu-thich",
             "headerTooltip": "Số trong ngoặc là số MTTN (Miền Trung - Tây Nguyên) của phòng/bầy có bật MTTN."},
            {"headerName": "Tỷ lệ ⓘ", "field": "cnql_ty_le", "width": 110, "valueFormatter": PCT_CNQL_MTTN,
             "cellStyle": _heat("ty_le", _GIA_TRI_HEAT_CNQL), "headerClass": "co-chu-thich",
             "headerTooltip": "Tỷ lệ trong ngoặc là tỷ lệ MTTN / tổng online của phòng/bầy có bật MTTN. "
                              "Màu ô tô theo số MTTN khi dòng có hiện số này."},
        ]},
        {"headerName": "COMBO VVIP", "children": [
            {"headerName": "Số VVIP", "field": "vvip", "width": w, "valueFormatter": SO},
            {"headerName": "Tỷ lệ VVIP/PTTB", "field": "vvip_ty_le", "width": 86,
             "valueFormatter": PCT, "cellStyle": _heat("ty_le")},
        ]},
        {"headerName": "CAMERA", "children": [
            {"headerName": "Mục tiêu", "field": "mt_camera", "width": w, "valueFormatter": SO},
            {"headerName": "Thực hiện", "field": "camera", "width": w, "valueFormatter": SO},
            {"headerName": "Tỷ lệ HTKH", "field": "htkh_camera", "width": 76,
             "valueFormatter": PCT, "cellStyle": _heat("htkh")},
        ]},
        {"headerName": f"KẾT QUẢ NGÀY {ngay:02d}/{thang_so:02d}", "children": [
            {"headerName": "Mục tiêu ⓘ", "field": "mt_ngay", "width": w, "valueFormatter": SO,
             "headerClass": "co-chu-thich",
             "headerTooltip": "Bình quân mỗi ngày còn lại (từ ngày mai) phải online bao nhiêu để về đích mục tiêu tháng.\n"
                              "= (mục tiêu tháng − đã online từ đầu tháng đến hết ngày này) "
                              "chia số ngày còn lại của tháng (không tính ngày này), làm tròn lên.\n"
                              "Hụt càng nhiều thì mục tiêu ngày mai càng nặng; đủ mục tiêu tháng rồi thì về 0."},
            {"headerName": "Bán mới", "field": "ngay_ban_moi", "width": w, "valueFormatter": SO},
            {"headerName": "Online", "field": "ngay_online", "width": w, "valueFormatter": SO,
             "cellStyle": {"textAlign": "center", "fontWeight": "700"}},
            {"headerName": "VVIP", "field": "ngay_vvip", "width": 66, "valueFormatter": SO},
            ket_luan,
        ]},
    ]


def _ke_khoi(cols: list[dict]) -> list[dict]:
    """Kẻ đường dọc đậm ở đầu mỗi khối cột (INTERNET, TĂNG TRƯỞNG, FPT PLAY...) cho dễ dò theo cột."""
    for c in cols:
        if "children" in c and c["children"]:
            c["headerClass"] = "khoi-dau"
            dau = c["children"][0]
            dau["cellClass"] = (dau.get("cellClass", "o-giua") + " khoi-dau").strip()
            dau["headerClass"] = (dau.get("headerClass", "tieu-de-giua") + " khoi-dau").strip()
    return cols


def _rong_bang(cols) -> int:
    tong = 0
    for c in cols:
        tong += sum(x["width"] for x in c["children"]) if "children" in c else c["width"]
    return tong + 2


def ty_le_vua_man_hinh(cols, vw: dict | None, sidebar_thu_gon: bool = False) -> float:
    """Tỷ lệ thu nhỏ vừa đủ để cả bảng lọt trong một khung hình, không cần kéo ngang.

    Điện thoại thì menu ẩn đi và không thu nhỏ dưới 80% cho chữ còn đọc được - phần thừa
    kéo ngang trong khung, cột Phòng ghim bên trái nên không bị lạc dòng.
    """
    rong_cua_so = (vw or {}).get("w") or 1440
    if rong_cua_so < MAN_HINH_NHO:
        con_lai = rong_cua_so - 2 * 14 - 2 * 14 - 4
        return max(TY_LE_TOI_THIEU_DT, min(1.0, round(con_lai / _rong_bang(cols), 3)))
    sidebar = 66 if sidebar_thu_gon else 212
    con_lai = max(420, rong_cua_so - sidebar - BE_NGANG_CHUA_BANG)
    return min(1.0, round(con_lai / (_rong_bang(cols) + 12), 3))


def _so(v) -> str:
    return f"{int(v or 0):,}".replace(",", ".")


def _pct(v) -> str:
    return "–" if v is None else f"{v:.0f}%"


def _kpis(tong, ngay: int, thang: str, tam_tinh: bool, luy_ke: bool = True) -> list:
    thang_so = int(thang[5:7])
    thang_truoc = 12 if thang_so == 1 else thang_so - 1
    tt = tong.tang_truong
    dat_ngay = tong.mt_ngay and tong.ngay_online >= tong.mt_ngay
    return [
        kpi("Online tháng" if luy_ke else "Online trong kỳ", _so(tong.online),
            f"Chỉ tiêu {_so(tong.mt_internet)} · HTKH {_pct(tong.htkh_internet)}"
            if tong.mt_internet else "Chưa nhập chỉ tiêu tháng"),
        kpi("Tăng trưởng", "–" if tt is None else f"{tt:+.0f}%",
            (f"Cùng kỳ T{thang_truoc}" if luy_ke else "Cùng kỳ tháng trước")
            + f": {_so(tong.ck_online)} online",
            trang_thai="" if tt is None else ("ok" if tt >= 0 else "bad")),
        kpi("Tỷ lệ VVIP/PTTB", _pct(tong.vvip_ty_le), f"{_so(tong.vvip)} hợp đồng VVIP"),
        kpi("Camera", _so(tong.camera),
            f"Chỉ tiêu {_so(tong.mt_camera)} · HTKH {_pct(tong.htkh_camera)}"
            if tong.mt_camera else "Chưa nhập chỉ tiêu camera"),
        kpi(f"Online ngày {ngay:02d}/{thang_so:02d}", _so(tong.ngay_online),
            f"Mục tiêu {_so(tong.mt_ngay)} · Bán mới {_so(tong.ngay_ban_moi)}"
            if tong.mt_ngay else f"Bán mới {_so(tong.ngay_ban_moi)}",
            trang_thai="" if not tong.mt_ngay else
            ("ok" if dat_ngay else ("warn" if tam_tinh else "bad"))),
    ]


def _huy_hieu(tam_tinh: bool, luc) -> html.Span:
    if luc is None:
        return html.Span()
    if tam_tinh:
        return html.Span([html.I(className="cham nhap-nhay"),
                          f"Đang cập nhật · số lúc {luc:%H:%M}"], className="badge warn")
    return html.Span([html.I(className="cham"), "Đã chốt số"], className="badge ok",
                     title=f"Lần nạp số gần nhất: {luc:%H:%M %d/%m/%Y}")


def register(app):
    lk.gan_mo_phong(app, "tq-grid")
    tl.gan_nhan_xet(app, "tq", "tong", [("tq-khoang", "start_date"), ("tq-khoang", "end_date"), ("tq-cn", "value")],
                    dl.ngu_canh_tong, dl.YEU_CAU_TONG)

    @app.callback(Output("tq-du-bao", "rowData"), Output("tq-du-bao-loi", "children"),
                  Input("tq-khoang", "end_date"), Input("tq-cn", "value"))
    def _du_bao(ngay_iso, chi_nhanh):
        ngays = cac_ngay_co_du_lieu()
        ngay_iso = (ngay_iso or (ngays[-1] if ngays else ""))[:10]
        if not ngay_iso:
            return [], ""
        d = date.fromisoformat(ngay_iso)
        thang = f"{d.year}-{d.month:02d}"
        db = du_bao_thang(thang, d.day, loc_chi_nhanh(current_user.phong_duoc_xem(), chi_nhanh, thang))
        rows = db[(db.phong_code == "TOTAL") | (db.mt > 0) | (db.luy_ke > 0)].to_dict("records")
        for x in rows:
            x["phep_tinh"] = tl.phep_tinh_du_bao(x, f"{x['phong']}\n")
        return (rows,
                tl.giai_thich_du_bao(db[db.phong_code == "TOTAL"].iloc[0].to_dict(), db.attrs.get("tuan"),
                                     db.attrs.get("nhip")))
    kc.ghi(app, ("tq-khoang", "start_date"), ("tq-khoang", "end_date"), ("tq-cn", "value"),
           chuyen=lambda tu, den, cn: {"tu": tu, "den": den, "cn": cn})
    # Điện thoại: mở trang là dùng bảng Gọn luôn
    app.clientside_callback(
        """function(_) { return window.innerWidth < %d ? 'gon' : window.dash_clientside.no_update; }"""
        % MAN_HINH_NHO,
        Output("tq-cot", "value"), Input("tq-cot", "id"))

    @app.callback(Output("tq-khoang", "start_date"), Output("tq-khoang", "end_date"),
                  Output("tq-nhanh", "value"),
                  Input("tq-lui", "n_clicks"), Input("tq-toi", "n_clicks"),
                  Input("tq-p-moinhat", "n_clicks"), Input("tq-nhanh", "value"),
                  Input("tq-xem-chot", "n_clicks"),
                  State("tq-khoang", "start_date"), State("tq-khoang", "end_date"),
                  prevent_initial_call=True)
    def _chon_ky(_a, _b, _c, nhanh, _d, tu, den):
        ngays = cac_ngay_co_du_lieu()
        if not ngays:
            return no_update, no_update, None
        kq = doi_ky(ctx.triggered_id, nhanh, tu, den, ngays)
        return (kq[0], kq[1], None) if kq else (no_update, no_update, None)

    @app.callback(Output("tq-zoom-chon", "value"),
                  Input("tq-nho", "n_clicks"), Input("tq-to", "n_clicks"),
                  State("tq-ty-le", "data"), prevent_initial_call=True)
    def _doi_co(_a, _b, ty_le):
        hien = round((ty_le or 1) * 100)
        if ctx.triggered_id == "tq-nho":
            nho_hon = [z for z in ZOOM_STEPS if z < hien]
            return nho_hon[-1] if nho_hon else ZOOM_STEPS[0]
        lon_hon = [z for z in ZOOM_STEPS if z > hien]
        return lon_hon[0] if lon_hon else ZOOM_STEPS[-1]

    @app.callback(Output("tq-grid", "columnDefs"), Output("tq-grid", "rowData"),
                  Output("tq-kpi", "children"), Output("tq-badge", "children"),
                  Output("tq-zoom-wrap", "style"), Output("tq-ty-le", "data"),
                  Output("tq-tieu-de", "children"), Output("tq-mo-ta", "children"),
                  Output("tq-canh-bao", "hidden"), Output("tq-canh-bao-chu", "children"),
                  Output("tq-xem-chot", "hidden"), Output("tq-xem-chot", "children"),
                  Input("tq-khoang", "start_date"), Input("tq-khoang", "end_date"),
                  Input("tq-zoom-chon", "value"), Input("tq-cn", "value"),
                  Input("tq-cot", "value"), Input("ui-vw", "data"), State("ui-sidebar", "data"))
    def _cap_nhat(tu_iso, ngay_iso, zoom, chi_nhanh, kieu_cot, vw, sidebar):
        ngays = cac_ngay_co_du_lieu()
        ngay_iso = (ngay_iso or (ngays[-1] if ngays else ""))[:10] or None
        if not ngay_iso:
            return ([], [], [], "", {}, 1, "Chưa có số liệu",
                    "Nạp file Internet để bắt đầu.", True, "", True, "")
        d = date.fromisoformat(ngay_iso)
        tu_iso = _tu_hop_le(tu_iso, d)
        luy_ke = tu_iso == d.replace(day=1).isoformat()
        thang = f"{d.year}-{d.month:02d}"
        chi_nhanh = chi_nhanh or "all"
        scope = loc_chi_nhanh(current_user.phong_duoc_xem(), chi_nhanh, thang)
        tam_tinh, luc = trang_thai_ngay(ngay_iso)

        df, ngay = bang_tong_quan(thang, d.day, chi_phong=scope, chi_nhanh=chi_nhanh,
                                  tam_tinh=tam_tinh, tu=tu_iso)
        cols = lk.them_giai_thich(_ke_khoi(_cols(thang, ngay, gon=kieu_cot == "gon", tu=tu_iso)))
        cols[0] = lk.cot_phong_bam_duoc(cols[0])
        tong = df[df.loai_dong == "total"].iloc[0]

        if zoom in (None, "fit"):
            ty_le = ty_le_vua_man_hinh(cols, vw, (sidebar or {}).get("thu_gon", False))
        else:
            ty_le = int(zoom) / 100

        tieu_de = f"Kết quả theo phòng · {TEN_PHAM_VI.get(chi_nhanh, TEN_PHAM_VI['all'])}"
        d_tu = date.fromisoformat(tu_iso)
        if luy_ke:
            mo_ta = f"Luỹ kế từ 01/{d.month:02d} đến {ngay:02d}/{d.month:02d}/{d.year}"
        else:
            cung_thang = (d_tu.year, d_tu.month) == (d.year, d.month)
            mo_ta = (f"Từ {d_tu:%d/%m/%Y} đến {d:%d/%m/%Y} ({(d - d_tu).days + 1} ngày) · cùng kỳ "
                     f"{lui_mot_thang(d_tu):%d/%m}-{lui_mot_thang(d):%d/%m} · mục tiêu "
                     + (f"tháng {d.month}" if cung_thang else "cộng các tháng trong kỳ"))

        truoc = [x for x in ngays if x < ngay_iso]
        if tam_tinh:
            chu = [html.B(f"Ngày {ngay:02d}/{d.month:02d} đang cập nhật. "),
                   f"Số tính đến {luc:%H:%M}, phòng chưa đủ mục tiêu ghi “Chưa đạt”."]
            nut = (f"Xem ngày {date.fromisoformat(truoc[-1]):%d/%m} (đã chốt)"
                   if truoc else "")
            canh_bao = (False, chu, not truoc, nut)
        else:
            canh_bao = (True, "", True, "")

        style = {"zoom": ty_le} if ty_le != 1 else {}
        return (cols, df.to_dict("records"), _kpis(tong, ngay, thang, tam_tinh, luy_ke),
                _huy_hieu(tam_tinh, luc), style, ty_le, tieu_de, mo_ta, *canh_bao)

    @app.callback(Output("tq-tai-xuong", "data"),
                  Input("tq-xls", "n_clicks"), Input("tq-png", "n_clicks"),
                  State("tq-khoang", "start_date"), State("tq-khoang", "end_date"),
                  State("tq-cn", "value"), prevent_initial_call=True)
    def _tai_ve(_a, _b, tu_iso, ngay_iso, chi_nhanh):
        ngay_iso = (ngay_iso or "")[:10] or None
        d = date.fromisoformat(ngay_iso) if ngay_iso else None
        tu_iso = _tu_hop_le(tu_iso, d) if d else None
        thang = f"{d.year}-{d.month:02d}" if d else None
        chi_nhanh = chi_nhanh or "all"
        scope = loc_chi_nhanh(current_user.phong_duoc_xem(), chi_nhanh, thang)
        tam_tinh, luc = trang_thai_ngay(ngay_iso) if ngay_iso else (False, None)
        kw = dict(chi_phong=scope, chi_nhanh=chi_nhanh, tam_tinh=tam_tinh, luc=luc, tu=tu_iso)
        if ctx.triggered_id == "tq-png":
            noi_dung, ten = anh_tong_quan(thang, d.day if d else None, nhan_xet=tl.nhan_xet_anh(tu_iso, ngay_iso,
                                                                                               chi_nhanh), **kw)
        else:
            noi_dung, ten = xuat_tong_quan(thang, d.day if d else None, **kw)
        return dcc.send_bytes(noi_dung, ten)
