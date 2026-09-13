"""Trang Báo cáo Tổng - giữ nguyên bố cục bảng tổng hợp quen thuộc + heatmap + cỡ bảng.

Bảng rộng hơn màn hình laptop nên mặc định chạy chế độ "Vừa màn hình": bề rộng cửa sổ
được đo ở trình duyệt (store `ui-vw`), ở đây tính ra tỷ lệ thu nhỏ vừa đủ để không phải
kéo ngang. Tiêu đề cột tự xuống dòng nên không bị cắt chữ.
"""
from __future__ import annotations

from datetime import date, timedelta

import dash_ag_grid as dag
from dash import Input, Output, State, ctx, dcc, html, no_update
from flask_login import current_user

from app.config import rules_config
from app.export_excel import xuat_tong_quan
from app.export_png import anh_tong_quan
from app.metrics import cac_ngay_co_du_lieu, ngay_moi_nhat
from app.org import loc_chi_nhanh
from app.overview import bang_tong_quan
from app.ui.components import card, chi_nhanh_control, field, kpi
from app.ui.icons import icon

# thang màu giống bảng tính: đỏ nhạt -> cam -> vàng -> xanh nhạt -> xanh
MAU_HEAT = [("#F7BDBD", "#7F1D1D"), ("#FBD9AE", "#7C3A06"), ("#FCEBB4", "#6B5104"),
            ("#D3EBD4", "#14532D"), ("#A5DCAF", "#0F3D22")]
ZOOM_STEPS = [50, 75, 90, 100, 125, 150, 200]
ZOOM_OPTIONS = ([{"label": "Vừa màn hình", "value": "fit"}]
                + [{"label": f"{z}%", "value": z} for z in ZOOM_STEPS])
BE_NGANG_CHUA_BANG = 124       # lề trang + padding thẻ + thanh cuộn, trừ khi tính cỡ vừa màn hình

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
]}

ROW_STYLE = {"styleConditions": [
    {"condition": "params.data.loai_dong == 'subtotal'",
     "style": {"backgroundColor": "#EDF3F9", "fontWeight": "700", "color": "#C8372D"}},
    {"condition": "params.data.loai_dong == 'total'",
     "style": {"backgroundColor": "#DCE8F4", "fontWeight": "700", "color": "#003057"}},
]}


def topbar():
    return [html.Div([html.H1("Báo cáo Tổng"),
                      html.Div("Toàn bộ chỉ số của kỳ, theo từng phòng kinh doanh",
                               className="sub")]),
            html.Div(className="spacer"),
            html.Div(id="tq-badge")]


def layout():
    ngays = cac_ngay_co_du_lieu()
    moi_nhat = ngays[-1] if ngays else None
    thieu = [d for d in _khoang_ngay(ngays) if d not in set(ngays)]
    return html.Div([
        html.Div([
            field("Ngày báo cáo", dcc.DatePickerSingle(
                id="tq-date", date=moi_nhat, display_format="DD/MM/YYYY",
                min_date_allowed=ngays[0] if ngays else None,
                max_date_allowed=ngays[-1] if ngays else None,
                initial_visible_month=moi_nhat, disabled_days=thieu,
                first_day_of_week=1, clearable=False, className="date-pick")),
            field("Xem nhanh", html.Div([
                html.Button("Ngày mới nhất", id="tq-p-moinhat", className="chip"),
                html.Button("Hôm trước", id="tq-p-truoc", className="chip"),
                html.Button("Cùng ngày tháng trước", id="tq-p-cungky", className="chip"),
                html.Button("Ngày cuối tháng trước", id="tq-p-cuoithang", className="chip"),
            ], className="chips")),
            html.Div(className="grow"),
            field("Chi nhánh", chi_nhanh_control("tq-cn")),
        ], className="toolbar loc-trang"),
        dcc.Download(id="tq-tai-xuong"),

        html.Div(id="tq-kpi", className="kpi-row"),

        card([
            html.Div([
                html.Div(id="tq-ghi-chu", className="desc", style={"margin": 0}),
                html.Div(className="grow"),
                field("Cỡ bảng", dcc.Dropdown(
                    id="tq-zoom", clearable=False, value="fit", options=ZOOM_OPTIONS,
                    style={"width": "150px"})),
                field(" ", html.Div([
                    html.Button([icon("camera", 14), html.Span("Chụp ảnh (PNG)")], id="tq-png",
                                className="btn primary",
                                title="Ảnh đầy đủ toàn bộ bảng, dùng để gửi nhóm"),
                    html.Button([icon("download", 14), html.Span("Excel")], id="tq-xls",
                                className="btn"),
                    html.Button([icon("download", 14), html.Span("CSV")], id="tq-export",
                                className="btn"),
                ], style={"display": "flex", "gap": "8px"})),
            ], className="toolbar", style={"marginBottom": "12px"}),
            html.Div(dcc.Loading(dag.AgGrid(
                id="tq-grid", className="ag-theme-quartz ag-theme-ftel", columnDefs=[], rowData=[],
                defaultColDef={"resizable": True, "sortable": False, "suppressMovable": True,
                               "wrapHeaderText": True, "autoHeaderHeight": True,
                               "cellStyle": {"textAlign": "center"}},
                dashGridOptions={"suppressCellFocus": True, "headerHeight": 42,
                                 "groupHeaderHeight": 30, "rowHeight": 32,
                                 "domLayout": "autoHeight", "suppressColumnVirtualisation": True},
                getRowStyle=ROW_STYLE, style={"width": "100%"})),
                id="tq-zoom-wrap", className="zoom-wrap")],
            title="Số liệu theo phòng",
            desc="Cộng dồn từ ngày 01 đến ngày đang chọn. Nhóm cột cuối là số riêng của ngày đó. "
                 "Màu ô: xanh đạt, vàng sát ngưỡng, đỏ cần xử lý."),
    ])


def _khoang_ngay(ngays):
    """Mọi ngày trong khoảng dữ liệu - dùng để chặn ngày chưa có số trên lịch."""
    if not ngays:
        return []
    d0, d1 = date.fromisoformat(ngays[0]), date.fromisoformat(ngays[-1])
    return [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def _cols(thang: str, ngay: int):
    thang_so = int(thang[5:7])
    w = 72
    return [
        {"headerName": "PKD", "field": "phong", "pinned": "left", "width": 158,
         "cellStyle": {"textAlign": "left", "fontWeight": "600"}},
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
            {"headerName": "Số online", "field": "ck_online", "width": 78, "valueFormatter": SO,
             "headerTooltip": "Cùng kỳ tháng trước"},
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
        {"headerName": f"KẾT QUẢ THỰC HIỆN NGÀY {ngay:02d}", "children": [
            {"headerName": "Mục tiêu", "field": "mt_ngay", "width": w, "valueFormatter": SO},
            {"headerName": "Bán mới", "field": "ngay_ban_moi", "width": w, "valueFormatter": SO},
            {"headerName": "Online", "field": "ngay_online", "width": w, "valueFormatter": SO,
             "cellStyle": {"textAlign": "center", "fontWeight": "700"}},
            {"headerName": "VVIP", "field": "ngay_vvip", "width": 66, "valueFormatter": SO},
            {"headerName": "Kết luận", "field": "ket_luan", "width": 96,
             "cellStyle": KET_LUAN_STYLE},
        ]},
    ]


def _rong_bang(cols) -> int:
    tong = 0
    for c in cols:
        tong += sum(x["width"] for x in c["children"]) if "children" in c else c["width"]
    return tong + 2


def ty_le_vua_man_hinh(cols, vw: dict | None, sidebar_thu_gon: bool = False) -> float:
    """Tỷ lệ thu nhỏ vừa đủ để cả bảng lọt trong một khung hình, không cần kéo ngang."""
    rong_cua_so = (vw or {}).get("w") or 1440
    sidebar = 66 if sidebar_thu_gon else 212
    con_lai = max(420, rong_cua_so - sidebar - BE_NGANG_CHUA_BANG)
    return min(1.0, round(con_lai / (_rong_bang(cols) + 12), 3))


def register(app):
    @app.callback(Output("tq-date", "date"),
                  Input("tq-p-moinhat", "n_clicks"), Input("tq-p-truoc", "n_clicks"),
                  Input("tq-p-cungky", "n_clicks"), Input("tq-p-cuoithang", "n_clicks"),
                  State("tq-date", "date"), prevent_initial_call=True)
    def _chon_nhanh(_a, _b, _c, _d, hien_tai):
        ngays = cac_ngay_co_du_lieu()
        if not ngays:
            return no_update
        d = date.fromisoformat(hien_tai) if hien_tai else date.fromisoformat(ngays[-1])
        trig = ctx.triggered_id
        if trig == "tq-p-moinhat":
            return ngays[-1]
        if trig == "tq-p-truoc":
            truoc = [x for x in ngays if x < d.isoformat()]
            return truoc[-1] if truoc else no_update
        if trig == "tq-p-cungky":
            cuoi_thang_truoc = d.replace(day=1) - timedelta(days=1)
            ngay = min(d.day, cuoi_thang_truoc.day)
            muc_tieu = date(cuoi_thang_truoc.year, cuoi_thang_truoc.month, ngay).isoformat()
            hop_le = [x for x in ngays if x <= muc_tieu]
            return hop_le[-1] if hop_le else ngays[0]
        if trig == "tq-p-cuoithang":
            cuoi_truoc = (d.replace(day=1) - timedelta(days=1)).isoformat()
            hop_le = [x for x in ngays if x <= cuoi_truoc]
            return hop_le[-1] if hop_le else ngays[0]
        return no_update

    @app.callback(Output("tq-grid", "columnDefs"), Output("tq-grid", "rowData"),
                  Output("tq-kpi", "children"), Output("tq-badge", "children"),
                  Output("tq-zoom-wrap", "style"), Output("tq-ghi-chu", "children"),
                  Input("tq-date", "date"), Input("tq-zoom", "value"), Input("tq-cn", "value"),
                  Input("ui-vw", "data"), State("ui-sidebar", "data"))
    def _cap_nhat(ngay_iso, zoom, chi_nhanh, vw, sidebar):
        ngays = cac_ngay_co_du_lieu()
        ngay_iso = ngay_iso or (ngays[-1] if ngays else None)
        if not ngay_iso:
            return [], [], [], "", {}, ""
        d = date.fromisoformat(ngay_iso)
        thang = f"{d.year}-{d.month:02d}"
        scope = loc_chi_nhanh(current_user.phong_duoc_xem(), chi_nhanh, thang)

        df, ngay = bang_tong_quan(thang, d.day, chi_phong=scope)
        cols = _cols(thang, ngay)
        tong = df[df.loai_dong == "total"].iloc[0]

        if zoom == "fit":
            ty_le = ty_le_vua_man_hinh(cols, vw, (sidebar or {}).get("thu_gon", False))
            ghi_chu = f"Đang hiển thị {ty_le * 100:.0f}% để vừa toàn bộ cột trong màn hình."
        else:
            ty_le = (zoom or 100) / 100
            ghi_chu = "Cỡ tự chọn. Chuyển về “Vừa màn hình” để thấy toàn bộ cột."

        def fmt(v):
            return f"{int(v or 0):,}".replace(",", ".")

        kpis = [
            kpi("Số online tháng", fmt(tong.online),
                f"Chỉ tiêu {fmt(tong.mt_internet)}" if tong.mt_internet else "Chưa nhập chỉ tiêu"),
            kpi("Tỷ lệ HTKH", f"{tong.htkh_internet:.0f}%" if tong.htkh_internet else "-",
                f"Tồn {fmt(tong.so_ton)} hợp đồng"),
            kpi("Tỷ lệ V.VIP", f"{tong.vvip_ty_le:.0f}%" if tong.vvip_ty_le else "-",
                f"{fmt(tong.vvip)} V.VIP"),
            kpi(f"Online ngày {ngay:02d}", fmt(tong.ngay_online),
                f"Bán mới {fmt(tong.ngay_ban_moi)} · V.VIP {fmt(tong.ngay_vvip)}"),
            kpi("PTTB CNQL", f"{tong.cnql_ty_le:.0f}%" if tong.cnql_ty_le else "-",
                f"{fmt(tong.cnql)} hợp đồng thuộc chi nhánh"),
        ]
        la_moi_nhat = ngay_moi_nhat() == ngay_iso
        badge = html.Span([
            html.Span("Số liệu ngày ", style={"color": "var(--text-muted)"}),
            html.B(f"{d.day:02d}/{d.month:02d}/{d.year}"),
            html.Span(" · mới nhất" if la_moi_nhat else "", style={"color": "var(--fpt-green)"})],
            className="badge muted")
        style = {"zoom": ty_le} if ty_le != 1 else {}
        return cols, df.to_dict("records"), kpis, badge, style, ghi_chu

    @app.callback(Output("tq-grid", "exportDataAsCsv"), Input("tq-export", "n_clicks"),
                  prevent_initial_call=True)
    def _export(n):
        return bool(n)

    @app.callback(Output("tq-tai-xuong", "data"),
                  Input("tq-xls", "n_clicks"), Input("tq-png", "n_clicks"),
                  State("tq-date", "date"), State("tq-cn", "value"), prevent_initial_call=True)
    def _tai_ve(_a, _b, ngay_iso, chi_nhanh):
        d = date.fromisoformat(ngay_iso) if ngay_iso else None
        thang = f"{d.year}-{d.month:02d}" if d else None
        scope = loc_chi_nhanh(current_user.phong_duoc_xem(), chi_nhanh, thang)
        ham = anh_tong_quan if ctx.triggered_id == "tq-png" else xuat_tong_quan
        noi_dung, ten = ham(thang, d.day if d else None, chi_phong=scope)
        return dcc.send_bytes(noi_dung, ten)
