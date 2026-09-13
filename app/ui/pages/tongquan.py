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
from app.org import loc_chi_nhanh
from app.overview import TEN_PHAM_VI, bang_tong_quan, trang_thai_ngay
from app.ui.components import chi_nhanh_control, field, kpi, seg_control
from app.ui.icons import icon

# thang màu giống bảng tính: đỏ nhạt -> cam -> vàng -> xanh nhạt -> xanh
MAU_HEAT = [("#F7BDBD", "#7F1D1D"), ("#FBD9AE", "#7C3A06"), ("#FCEBB4", "#6B5104"),
            ("#D3EBD4", "#14532D"), ("#A5DCAF", "#0F3D22")]
ZOOM_STEPS = [50, 60, 70, 80, 90, 100, 110, 125, 150]
BE_NGANG_CHUA_BANG = 124       # lề trang + padding thẻ + thanh cuộn, trừ khi tính cỡ vừa màn hình
MAN_HINH_NHO = 768             # dưới mức này coi là điện thoại
TY_LE_TOI_THIEU_DT = 0.8       # điện thoại: không thu nhỏ hơn mức này, thừa thì kéo ngang

SO = {"function": "params.value == null ? '' : Number(params.value).toLocaleString('vi-VN')"}
PCT = {"function": "params.value == null ? '' : Math.round(params.value) + '%'"}


def _heat(kind: str) -> dict:
    """Sinh điều kiện tô màu theo ngưỡng trong config/rules.yml."""
    t = rules_config()["heatmap"][kind]
    moc = [t["rat_kem"], t["kem"], t["trung_binh"], t["kha"]]
    dk = []
    for i, (bg, fg) in enumerate(MAU_HEAT):
        cond = (f"params.value != null && params.value < {moc[i]}" if i < len(moc)
                else "params.value != null")
        dk.append({"condition": cond,
                   "style": {"backgroundColor": bg, "color": fg, "fontWeight": "600"}})
    return {"styleConditions": dk}


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
     "style": {"backgroundColor": "#EDF3F9", "fontWeight": "700", "color": "#C8372D"}},
    {"condition": "params.data.loai_dong == 'total'",
     "style": {"backgroundColor": "#DCE8F4", "fontWeight": "700", "color": "#003057"}},
]}


def topbar():
    return [html.Div([html.H1("Báo cáo Tổng"),
                      html.Div("Kết quả kinh doanh luỹ kế tháng, theo phòng", className="sub")]),
            html.Div(className="spacer"),
            html.Div(id="tq-badge")]


def layout():
    ngays = cac_ngay_co_du_lieu()
    moi_nhat = ngays[-1] if ngays else None
    thieu = [d for d in _khoang_ngay(ngays) if d not in set(ngays)]
    return html.Div([
        html.Div([
            field("Ngày báo cáo", html.Div([
                html.Button("‹", id="tq-lui", className="nut-ky", title="Ngày trước đó"),
                dcc.DatePickerSingle(
                    id="tq-date", date=moi_nhat, display_format="DD/MM/YYYY",
                    min_date_allowed=ngays[0] if ngays else None,
                    max_date_allowed=ngays[-1] if ngays else None,
                    initial_visible_month=moi_nhat, disabled_days=thieu,
                    first_day_of_week=1, clearable=False, className="date-pick"),
                html.Button("›", id="tq-toi", className="nut-ky", title="Ngày sau đó"),
                html.Button("Mới nhất", id="tq-p-moinhat", className="btn nho"),
                dcc.Dropdown(id="tq-nhanh", placeholder="Chọn nhanh", searchable=False,
                             clearable=False, className="chon-nhanh", options=[
                                 {"label": "Cùng ngày tháng trước", "value": "cungky"},
                                 {"label": "Cuối tháng trước", "value": "cuoithang"}]),
            ], className="chon-ngay")),
            field("Chi nhánh", chi_nhanh_control("tq-cn")),
        ], className="toolbar loc-trang"),
        dcc.Download(id="tq-tai-xuong"),
        dcc.Store(id="tq-zoom", data="fit"),
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
                        html.Button(id="tq-zoom-nhan", className="btn zoom-nhan",
                                    title="Về cỡ vừa màn hình"),
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
                defaultColDef={"resizable": True, "sortable": False, "suppressMovable": True,
                               "wrapHeaderText": True, "autoHeaderHeight": True,
                               "cellStyle": {"textAlign": "center"}},
                dashGridOptions={"suppressCellFocus": True, "headerHeight": 42,
                                 "groupHeaderHeight": 30, "rowHeight": 32,
                                 "domLayout": "autoHeight", "suppressColumnVirtualisation": True,
                                 "tooltipShowDelay": 300},
                getRowStyle=ROW_STYLE, style={"width": "100%"})),
                id="tq-zoom-wrap", className="zoom-wrap"),
        ], className="card"),
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


def _khoang_ngay(ngays):
    """Mọi ngày trong khoảng dữ liệu - dùng để chặn ngày chưa có số trên lịch."""
    if not ngays:
        return []
    d0, d1 = date.fromisoformat(ngays[0]), date.fromisoformat(ngays[-1])
    return [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def _cols(thang: str, ngay: int, gon: bool = False):
    thang_so = int(thang[5:7])
    thang_truoc = 12 if thang_so == 1 else thang_so - 1
    w = 72
    phong = {"headerName": "PKD", "field": "phong", "pinned": "left", "width": 172,
             "cellStyle": {"textAlign": "left", "fontWeight": "600"}}
    ket_luan = {"headerName": "Kết luận", "field": "ket_luan", "width": 96,
                "cellStyle": KET_LUAN_STYLE,
                "headerTooltip": "Online trong ngày so với mục tiêu ngày"}
    if gon:
        return [
            {**phong, "width": 124},
            {"headerName": f"INTERNET T{thang_so}", "children": [
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
        {"headerName": f"INTERNET THÁNG {thang_so}", "children": [
            {"headerName": "Mục tiêu", "field": "mt_internet", "width": w, "valueFormatter": SO},
            {"headerName": "Số tồn", "field": "so_ton", "width": w, "valueFormatter": SO},
            {"headerName": "Số online", "field": "online", "width": 78, "valueFormatter": SO,
             "cellStyle": {"textAlign": "center", "fontWeight": "700"}},
            {"headerName": "Tỷ lệ HTKH", "field": "htkh_internet", "width": 76,
             "valueFormatter": PCT, "cellStyle": _heat("htkh")},
        ]},
        {"headerName": "TĂNG TRƯỞNG", "children": [
            {"headerName": f"Cùng kỳ T{thang_truoc}", "field": "ck_online", "width": 78,
             "valueFormatter": SO,
             "headerTooltip": f"Số online từ 01 đến ngày {ngay:02d} của tháng {thang_truoc}"},
            {"headerName": "Tỷ lệ", "field": "tang_truong", "width": w, "valueFormatter": PCT,
             "cellStyle": _heat("tang_truong")},
        ]},
        {"headerName": "FPT PLAY", "children": [
            {"headerName": "Combo", "field": "fpl_combo", "width": w, "valueFormatter": SO},
            {"headerName": "Tỷ lệ FPL/NET", "field": "fpl_ty_le", "width": 82,
             "valueFormatter": PCT, "cellStyle": _heat("ty_le")},
        ]},
        {"headerName": "PTTB CNQL", "children": [
            {"headerName": "Số online", "field": "cnql", "width": 78, "valueFormatter": SO},
            {"headerName": "Tỷ lệ", "field": "cnql_ty_le", "width": w, "valueFormatter": PCT,
             "cellStyle": _heat("ty_le")},
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
            {"headerName": "Mục tiêu", "field": "mt_ngay", "width": w, "valueFormatter": SO},
            {"headerName": "Bán mới", "field": "ngay_ban_moi", "width": w, "valueFormatter": SO},
            {"headerName": "Online", "field": "ngay_online", "width": w, "valueFormatter": SO,
             "cellStyle": {"textAlign": "center", "fontWeight": "700"}},
            {"headerName": "VVIP", "field": "ngay_vvip", "width": 66, "valueFormatter": SO},
            ket_luan,
        ]},
    ]


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


def _kpis(tong, ngay: int, thang: str, tam_tinh: bool) -> list:
    thang_so = int(thang[5:7])
    thang_truoc = 12 if thang_so == 1 else thang_so - 1
    tt = tong.tang_truong
    dat_ngay = tong.mt_ngay and tong.ngay_online >= tong.mt_ngay
    return [
        kpi("Online tháng", _so(tong.online),
            f"Chỉ tiêu {_so(tong.mt_internet)} · HTKH {_pct(tong.htkh_internet)}"
            if tong.mt_internet else "Chưa nhập chỉ tiêu tháng"),
        kpi("Tăng trưởng", "–" if tt is None else f"{tt:+.0f}%",
            f"Cùng kỳ T{thang_truoc}: {_so(tong.ck_online)} online",
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
    # Điện thoại: mở trang là dùng bảng Gọn luôn
    app.clientside_callback(
        """function(_) { return window.innerWidth < %d ? 'gon' : window.dash_clientside.no_update; }"""
        % MAN_HINH_NHO,
        Output("tq-cot", "value"), Input("tq-cot", "id"))

    @app.callback(Output("tq-date", "date"), Output("tq-nhanh", "value"),
                  Input("tq-lui", "n_clicks"), Input("tq-toi", "n_clicks"),
                  Input("tq-p-moinhat", "n_clicks"), Input("tq-nhanh", "value"),
                  Input("tq-xem-chot", "n_clicks"),
                  State("tq-date", "date"), prevent_initial_call=True)
    def _chon_ngay(_a, _b, _c, nhanh, _d, hien_tai):
        ngays = cac_ngay_co_du_lieu()
        if not ngays:
            return no_update, None
        d = hien_tai or ngays[-1]
        trig = ctx.triggered_id
        if trig == "tq-lui":
            truoc = [x for x in ngays if x < d]
            return (truoc[-1] if truoc else no_update), None
        if trig == "tq-toi":
            sau = [x for x in ngays if x > d]
            return (sau[0] if sau else no_update), None
        if trig == "tq-p-moinhat":
            return ngays[-1], None
        if trig == "tq-xem-chot":
            truoc = [x for x in ngays if x < ngays[-1]]
            return (truoc[-1] if truoc else no_update), None
        if trig == "tq-nhanh" and nhanh:
            dd = date.fromisoformat(d)
            cuoi_thang_truoc = dd.replace(day=1) - timedelta(days=1)
            if nhanh == "cungky":
                ngay = min(dd.day, cuoi_thang_truoc.day)
                muc_tieu = cuoi_thang_truoc.replace(day=ngay).isoformat()
            else:
                muc_tieu = cuoi_thang_truoc.isoformat()
            hop_le = [x for x in ngays if x <= muc_tieu]
            return (hop_le[-1] if hop_le else ngays[0]), None
        return no_update, no_update

    @app.callback(Output("tq-zoom", "data"),
                  Input("tq-nho", "n_clicks"), Input("tq-to", "n_clicks"),
                  Input("tq-zoom-nhan", "n_clicks"),
                  State("tq-zoom", "data"), State("tq-ty-le", "data"), prevent_initial_call=True)
    def _doi_co(_a, _b, _c, zoom, ty_le):
        if ctx.triggered_id == "tq-zoom-nhan":
            return "fit"
        hien = round((ty_le or 1) * 100)
        if ctx.triggered_id == "tq-nho":
            nho_hon = [z for z in ZOOM_STEPS if z < hien]
            return nho_hon[-1] if nho_hon else ZOOM_STEPS[0]
        lon_hon = [z for z in ZOOM_STEPS if z > hien]
        return lon_hon[0] if lon_hon else ZOOM_STEPS[-1]

    @app.callback(Output("tq-grid", "columnDefs"), Output("tq-grid", "rowData"),
                  Output("tq-kpi", "children"), Output("tq-badge", "children"),
                  Output("tq-zoom-wrap", "style"), Output("tq-zoom-nhan", "children"),
                  Output("tq-ty-le", "data"),
                  Output("tq-tieu-de", "children"), Output("tq-mo-ta", "children"),
                  Output("tq-canh-bao", "hidden"), Output("tq-canh-bao-chu", "children"),
                  Output("tq-xem-chot", "hidden"), Output("tq-xem-chot", "children"),
                  Input("tq-date", "date"), Input("tq-zoom", "data"), Input("tq-cn", "value"),
                  Input("tq-cot", "value"), Input("ui-vw", "data"), State("ui-sidebar", "data"))
    def _cap_nhat(ngay_iso, zoom, chi_nhanh, kieu_cot, vw, sidebar):
        ngays = cac_ngay_co_du_lieu()
        ngay_iso = ngay_iso or (ngays[-1] if ngays else None)
        if not ngay_iso:
            return ([], [], [], "", {}, "Vừa màn hình", 1, "Chưa có số liệu",
                    "Nạp file Internet để bắt đầu.", True, "", True, "")
        d = date.fromisoformat(ngay_iso)
        thang = f"{d.year}-{d.month:02d}"
        chi_nhanh = chi_nhanh or "all"
        scope = loc_chi_nhanh(current_user.phong_duoc_xem(), chi_nhanh, thang)
        tam_tinh, luc = trang_thai_ngay(ngay_iso)

        df, ngay = bang_tong_quan(thang, d.day, chi_phong=scope, chi_nhanh=chi_nhanh,
                                  tam_tinh=tam_tinh)
        cols = _cols(thang, ngay, gon=kieu_cot == "gon")
        tong = df[df.loai_dong == "total"].iloc[0]

        if zoom == "fit":
            ty_le = ty_le_vua_man_hinh(cols, vw, (sidebar or {}).get("thu_gon", False))
            nhan_zoom = "Vừa màn hình"
        else:
            ty_le = (zoom or 100) / 100
            nhan_zoom = f"{zoom}%"

        tieu_de = f"Kết quả theo phòng · {TEN_PHAM_VI.get(chi_nhanh, TEN_PHAM_VI['all'])}"
        mo_ta = f"Luỹ kế từ 01/{d.month:02d} đến {ngay:02d}/{d.month:02d}/{d.year}"

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
        return (cols, df.to_dict("records"), _kpis(tong, ngay, thang, tam_tinh),
                _huy_hieu(tam_tinh, luc), style, nhan_zoom, ty_le, tieu_de, mo_ta, *canh_bao)

    @app.callback(Output("tq-tai-xuong", "data"),
                  Input("tq-xls", "n_clicks"), Input("tq-png", "n_clicks"),
                  State("tq-date", "date"), State("tq-cn", "value"), prevent_initial_call=True)
    def _tai_ve(_a, _b, ngay_iso, chi_nhanh):
        d = date.fromisoformat(ngay_iso) if ngay_iso else None
        thang = f"{d.year}-{d.month:02d}" if d else None
        chi_nhanh = chi_nhanh or "all"
        scope = loc_chi_nhanh(current_user.phong_duoc_xem(), chi_nhanh, thang)
        tam_tinh, luc = trang_thai_ngay(ngay_iso) if ngay_iso else (False, None)
        ham = anh_tong_quan if ctx.triggered_id == "tq-png" else xuat_tong_quan
        noi_dung, ten = ham(thang, d.day if d else None, chi_phong=scope, chi_nhanh=chi_nhanh,
                            tam_tinh=tam_tinh, luc=luc)
        return dcc.send_bytes(noi_dung, ten)
