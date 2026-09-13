"""Các khối giao diện dùng lại nhiều nơi."""
from __future__ import annotations

from dash import dcc, html


def card(children, title: str | None = None, desc: str | None = None, **kw):
    head = []
    if title:
        head.append(html.H3(title))
    if desc:
        head.append(html.Div(desc, className="desc"))
    return html.Div(head + (children if isinstance(children, list) else [children]),
                    className="card", **kw)


def kpi(label: str, value, hint=None, trang_thai: str = "", id: str | None = None):
    body = [html.Div(label, className="label"), html.Div(value, className="value")]
    if hint is not None:
        body.append(html.Div(hint, className="hint"))
    kw = {"id": id} if id else {}
    return html.Div(body, className=f"kpi {trang_thai}".strip(), **kw)


def field(label: str, control):
    return html.Div([html.Label(label), control], className="field")


def alert(children, muc: str = "info"):
    return html.Div(children, className=f"alert {muc}")


def badge(text: str, muc: str = ""):
    return html.Span(text, className=f"badge {muc}".strip())


def seg_control(id: str, options: list[tuple[str, str]], value: str):
    """Nhóm nút dạng segmented control."""
    return dcc.Tabs(
        id=id, value=value, className="seg", mobile_breakpoint=0,   # không tự xếp dọc trên điện thoại
        children=[dcc.Tab(label=lb, value=v, className="seg-item",
                          selected_className="seg-item active") for v, lb in options],
    )


def nhac_chua_luu(app, grid_id: str, out_id: str, reset_id: str):
    """Hiện nhắc nhở khi người dùng sửa ô trong bảng mà chưa bấm Lưu.

    `reset_id` là ô thông báo của thẻ đó - khi lưu xong thông báo đổi thì lời nhắc tắt.
    """
    from dash import Input, Output, ctx

    @app.callback(Output(out_id, "children"),
                  Input(grid_id, "cellValueChanged"), Input(reset_id, "children"),
                  prevent_initial_call=True)
    def _nhac(thay_doi, _da_luu):
        if ctx.triggered_id == reset_id or not thay_doi:
            return ""
        return html.Span("● Có thay đổi chưa lưu", className="chip canh-bao")


def modal(id: str, tieu_de: str, noi_dung: list, nut_chinh: str = "Lưu"):
    """Hộp thoại dùng chung. Mở/đóng bằng cách đổi className thành "modal mo".

    Sinh sẵn các id: `<id>-dong`, `<id>-huy`, `<id>-ok` để trang tự nối callback.
    """
    return html.Div([
        html.Div(className="modal-nen"),
        html.Div([
            html.Div([html.H3(tieu_de), html.Div(className="grow"),
                      html.Button("×", id=f"{id}-dong", className="modal-x",
                                  title="Đóng")], className="modal-dau"),
            html.Div(noi_dung, className="modal-than"),
            html.Div([html.Div(className="grow"),
                      html.Button("Huỷ", id=f"{id}-huy", className="btn"),
                      html.Button(nut_chinh, id=f"{id}-ok", className="btn primary")],
                     className="modal-chan"),
        ], className="modal-hop"),
    ], id=id, className="modal")


def ten_ky(thang: str) -> str:
    return f"Tháng {thang[5:7]}/{thang[:4]}" if thang else ""


def chon_ky(id: str, thangs: list[str] | None = None, value: str | None = None):
    """Bộ chọn kỳ báo cáo: nút lùi/tới + danh sách mọi tháng đã có số liệu.

    Dùng danh sách thay vì các tab cố định để tháng nào mới có dữ liệu là tự xuất hiện,
    không phải sửa code lại mỗi đầu tháng.
    """
    thangs = thangs or []
    value = value or (thangs[0] if thangs else None)
    return html.Div([
        html.Button("‹", id=f"{id}-lui", className="nut-ky", title="Kỳ trước"),
        dcc.Dropdown(id=id, clearable=False, value=value,
                     options=[{"label": ten_ky(t), "value": t} for t in thangs],
                     style={"width": "158px"}),
        html.Button("›", id=f"{id}-toi", className="nut-ky", title="Kỳ sau"),
    ], className="chon-ky")


def gan_dieu_huong_ky(app, id: str):
    """Nối hai nút lùi/tới của bộ chọn kỳ (danh sách tháng xếp mới nhất trước)."""
    from dash import Input, Output, State, ctx, no_update

    @app.callback(Output(id, "value"), Input(f"{id}-lui", "n_clicks"),
                  Input(f"{id}-toi", "n_clicks"),
                  State(id, "value"), State(id, "options"), prevent_initial_call=True)
    def _doi_ky(_a, _b, hien_tai, options):
        ds = [o["value"] if isinstance(o, dict) else o for o in (options or [])]
        if hien_tai not in ds:
            return no_update
        i = ds.index(hien_tai) + (1 if ctx.triggered_id == f"{id}-lui" else -1)
        return ds[i] if 0 <= i < len(ds) else no_update


def chi_nhanh_control(id: str, value: str = "all"):
    """Bộ lọc chi nhánh dùng chung cho mọi trang báo cáo."""
    return seg_control(id, [("all", "Tất cả"), ("DNG", "Đà Nẵng"), ("QNM", "Quảng Nam")], value)


def chon_ngay(prefix: str, ngays: list[str]):
    """Bộ chọn ngày báo cáo dùng chung: ‹ lịch › + nút Mới nhất. Chỉ cho chọn ngày đã có số."""
    from datetime import date, timedelta
    moi_nhat = ngays[-1] if ngays else None
    co = set(ngays)
    thieu = []
    if ngays:
        d0, d1 = date.fromisoformat(ngays[0]), date.fromisoformat(ngays[-1])
        thieu = [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)
                 if (d0 + timedelta(days=i)).isoformat() not in co]
    return html.Div([
        html.Button("‹", id=f"{prefix}-lui", className="nut-ky", title="Ngày trước đó"),
        dcc.DatePickerSingle(id=f"{prefix}-date", date=moi_nhat, display_format="DD/MM/YYYY",
                             min_date_allowed=ngays[0] if ngays else None,
                             max_date_allowed=moi_nhat, initial_visible_month=moi_nhat,
                             disabled_days=thieu, first_day_of_week=1, clearable=False,
                             className="date-pick"),
        html.Button("›", id=f"{prefix}-toi", className="nut-ky", title="Ngày sau đó"),
        html.Button("Mới nhất", id=f"{prefix}-moinhat", className="btn nho"),
    ], className="chon-ngay")


def gan_chon_ngay(app, prefix: str):
    """Nối nút ‹ › Mới nhất của bộ chọn ngày."""
    from dash import Input, Output, State, ctx, no_update

    from app.metrics import cac_ngay_co_du_lieu

    @app.callback(Output(f"{prefix}-date", "date"), Input(f"{prefix}-lui", "n_clicks"),
                  Input(f"{prefix}-toi", "n_clicks"), Input(f"{prefix}-moinhat", "n_clicks"),
                  State(f"{prefix}-date", "date"), prevent_initial_call=True)
    def _chon(_a, _b, _c, hien_tai):
        ngays = cac_ngay_co_du_lieu()
        if not ngays:
            return no_update
        d = hien_tai or ngays[-1]
        if ctx.triggered_id == f"{prefix}-lui":
            truoc = [x for x in ngays if x < d]
            return truoc[-1] if truoc else no_update
        if ctx.triggered_id == f"{prefix}-toi":
            sau = [x for x in ngays if x > d]
            return sau[0] if sau else no_update
        return ngays[-1]


def chu_giai(tieu_de: str, muc: list[tuple[str, str]]):
    """Khối "Cách tính" gập được: (tên chỉ số, định nghĩa)."""
    return html.Details([
        html.Summary(tieu_de, className="cg-tieu-de"),
        html.Div([html.Div([html.B(ten), html.Span(dn)], className="dn-dong") for ten, dn in muc],
                 className="dn-luoi"),
    ], className="chu-giai dinh-nghia")


# Chữ tiếng Việt cho bảng (phân trang, không có dữ liệu, bộ lọc)
LOCALE_VI = {
    "page": "Trang", "of": "/", "to": "đến", "more": "thêm", "next": "Sau", "last": "Cuối",
    "first": "Đầu", "previous": "Trước", "noRowsToShow": "Không có dữ liệu",
    "loadingOoo": "Đang tải...", "filterOoo": "Lọc...", "contains": "Có chứa",
    "equals": "Bằng", "notEqual": "Khác", "lessThan": "Nhỏ hơn", "greaterThan": "Lớn hơn",
    "andCondition": "Và", "orCondition": "Hoặc", "pageSizeSelectorLabel": "Số dòng:",
    "ariaPageSizeSelectorLabel": "Số dòng",
}


def empty_state(text: str):
    return html.Div(text, style={"padding": "40px", "textAlign": "center",
                                 "color": "var(--text-muted)"})


GRID_STYLE_CONDITIONS = {
    "styleConditions": [
        {"condition": "params.data.loai_dong == 'subtotal'",
         "style": {"backgroundColor": "var(--row-sub)", "fontWeight": "650"}},
        {"condition": "params.data.loai_dong == 'nhomkhac'",
         "style": {"backgroundColor": "#FFF6EC", "fontWeight": "650", "color": "#8A4B08"}},
        {"condition": "params.data.loai_dong == 'total'",
         "style": {"backgroundColor": "var(--row-total)", "fontWeight": "700"}},
    ]
}
