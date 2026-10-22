"""Trang Tra cứu giá (khối Kinh doanh, mọi tài khoản): giá gói cước FPT theo phường / xã, lấy trực tiếp từ dịch vụ của fpt.vn
(logic: app/gia_fpt.py). Ba tab: Tra giá một phường (giafpt_the.py), So giá hai phường, Giá cả tỉnh (giafpt_vung.py).

Danh sách tỉnh / phường nạp bằng callback (không làm chậm `layout()`), giá nhớ tạm 15 phút; nút "Làm mới giá" bỏ nhớ tạm.
Nút copy dùng chung `assets/sao_chep.js` (lớp nut-chep + data-chep) để dán thẳng vào Zalo / email gửi khách.
"""
from __future__ import annotations

from dash import Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate
from flask_login import current_user

from app import gia_fpt as gf
from app.bo_nho import xoa
from app.thoi_gian import chu_gio_vn
from app.ui.components import alert, cua_so, field, ghi_chu, kpi, seg_control
from app.ui.icons import icon
from app.ui.luoi import bang

TAB = [("tra", "Tra giá"), ("sosanh", "So giá hai phường"), ("vung", "Giá cả tỉnh")]
LOC_KHACH = [{"label": "Cá nhân và doanh nghiệp", "value": "all"}, {"label": "Cá nhân", "value": "ca_nhan"},
             {"label": "Doanh nghiệp", "value": "doanh_nghiep"}]
AN = {"display": "none"}
DONG = "params.value == null ? '–' : Math.round(params.value).toLocaleString('vi-VN') + 'đ'"
CHENH = ("params.value == null ? '–' : (params.value > 0 ? '+' : '') + Math.round(params.value).toLocaleString('vi-VN') + 'đ'")
KHACH_CHU = {"function": "params.value == 'doanh_nghiep' ? 'Doanh nghiệp' : 'Cá nhân'"}


def topbar():
    return [html.Div([html.H1("Tra cứu giá"), html.Div("Giá gói cước FPT theo phường / xã, lấy trực tiếp từ fpt.vn", className="sub")])]


def _vao() -> None:
    """Mọi callback kiểm lại quyền ở máy chủ (ẩn menu là chưa đủ)."""
    if not (current_user.is_authenticated and current_user.vao_duoc("/giafpt")):
        raise PreventUpdate


def _dd(id_: str, **kw) -> dcc.Dropdown:
    return dcc.Dropdown(id=id_, className="gf-dd", persistence=True, persistence_type="local", **kw)


def opt_tinh() -> list[dict]:
    try:
        return [{"label": t["ten"], "value": t["id"]} for t in gf.danh_sach_tinh()]
    except gf.LoiGia:
        return []                       # callback `_nap_tinh` nạp lại khi fpt.vn trả lời được


def opt_phuong(tinh: int) -> list[dict]:
    try:
        return [{"label": p["ten"], "value": p["id"]} for p in gf.danh_sach_phuong(tinh)]
    except gf.LoiGia:
        return []


def chon_khu_vuc(goc: str, nhan: str = "") -> list:
    """Hai ô chọn Tỉnh / thành và Phường / xã. Danh sách có sẵn từ lúc dựng trang (đã nhớ tạm một ngày): ô có `persistence` mà
    lúc đầu không có danh sách thì Dash coi giá trị nhớ là sai và xoá mất, nên không điền bằng callback sau."""
    return [field(f"Tỉnh / thành{nhan}", _dd(f"{goc}-tinh", value=gf.TINH_MAC_DINH, clearable=False, options=opt_tinh(), placeholder="Đang tải…")),
            field(f"Phường / xã{nhan}", _dd(f"{goc}-phuong", options=opt_phuong(gf.TINH_MAC_DINH), clearable=False,
                                            placeholder="Chọn phường / xã (gõ để tìm)"))]


def _luoi(gid: str, cot: list, cao: int = 560):
    return bang(gid, cot, cao, tuy_chon={"rowSelection": "multiple", "suppressRowClickSelection": True, "suppressCellFocus": True,
                                         "tooltipShowDelay": 300},
                cot_mac_dinh={"resizable": True, "sortable": True, "suppressMovable": True, "wrapHeaderText": True, "autoHeaderHeight": True})


COT_SS = [
    {"field": "ten", "headerName": "Gói", "minWidth": 240, "flex": 2, "checkboxSelection": True, "headerCheckboxSelection": True},
    {"field": "nhom", "headerName": "Nhóm", "width": 190},
    {"field": "khach", "headerName": "Khách hàng", "width": 130, "valueFormatter": KHACH_CHU},
    {"field": "gia_a", "headerName": "Giá bên trái", "width": 150, "type": "numericColumn", "valueFormatter": {"function": DONG}},
    {"field": "gia_b", "headerName": "Giá bên phải", "width": 150, "type": "numericColumn", "valueFormatter": {"function": DONG}},
    {"field": "chenh", "headerName": "Chênh (phải − trái)", "width": 160, "type": "numericColumn", "valueFormatter": {"function": CHENH},
     "cellStyle": {"styleConditions": [{"condition": "params.value < 0", "style": {"color": "#00844A", "fontWeight": "600"}},
                                       {"condition": "params.value > 0", "style": {"color": "#C8372D", "fontWeight": "600"}}]}},
    {"field": "pct", "headerName": "%", "width": 90, "type": "numericColumn",
     "valueFormatter": {"function": "params.value == null ? '–' : (params.value > 0 ? '+' : '') + params.value.toLocaleString('vi-VN') + '%'"}},
    {"field": "ghi_chu", "headerName": "Nhận xét", "minWidth": 200, "flex": 1},
]


def _pane_so_sanh():
    return html.Div([
        html.Div([html.Div([html.Div("Bên trái", className="gf-ben"), html.Div(chon_khu_vuc("gf2a"), className="gf-ben-o")], className="gf-ben-khoi"),
                  html.Div([html.Div("Bên phải", className="gf-ben"), html.Div(chon_khu_vuc("gf2b"), className="gf-ben-o")], className="gf-ben-khoi")],
                 className="gf-hai-ben"),
        html.Div([field("Khách hàng", dcc.Dropdown(id="gf2-khach", options=LOC_KHACH, value="all", clearable=False, searchable=False,
                                                   className="gf-dd gf-dd-nho")),
                  dcc.Checklist(id="gf2-khac", options=[{"label": " Chỉ hiện gói có giá khác nhau", "value": "khac"}], value=[],
                                className="gf-tick"),
                  html.Div(className="grow"),
                  html.Button([icon("copy", 14), html.Span("Copy bảng so giá")], id="gf2-chep", n_clicks=0, className="btn nut-chep lon")],
                 className="toolbar"),
        html.Div(id="gf2-tb"), html.Div(id="gf2-the", className="kpi-row"),
        _luoi("gf2-luoi", COT_SS),
        ghi_chu("Chênh = giá bên phải trừ giá bên trái: số âm (xanh) là bên phải rẻ hơn, số dương (đỏ) là bên phải đắt hơn. Gói chỉ có ở một bên "
                "nghĩa là phường kia không bán gói đó. Tick ô đầu dòng để chỉ copy các gói đã chọn.", style={"margin": "8px 0 0"}),
        dcc.Store(id="gf2-ctx"),
    ], id="gf-pane-sosanh", style=AN)


def layout():
    from app.ui.pages import giafpt_the, giafpt_vung
    return html.Div([
        html.Div(seg_control("gf-tab", TAB, "tra"), className="gf-tab"),
        giafpt_the.pane(), _pane_so_sanh(), giafpt_vung.pane(),
        cua_so("gf-ct", ghi_chu="Chỉ ghi những điểm khác với điều kiện chung của nhóm; phần chung nằm ngay dưới tiêu đề nhóm ở danh sách."),
    ])


# ------------------------------------------------------------------ chữ hiển thị
def ten_khu_vuc(tinh: int, phuong: int, gon: bool = False) -> str:
    """"Phường An Hải, Đà Nẵng"; gon=True chỉ ghi tên phường (khi hai bên cùng tỉnh thì nhãn ngắn dễ đọc hơn)."""
    ten_p = next((p["ten"] for p in gf.danh_sach_phuong(tinh) if p["id"] == phuong), "")
    if gon:
        return ten_p
    ten_t = next((t["ten"] for t in gf.danh_sach_tinh() if t["id"] == tinh), "")
    return f"{ten_p}, {ten_t}".strip(", ")


def _canh_bao(kq: dict):
    return alert(f"Chưa lấy được giá mới từ fpt.vn nên đang hiện giá lần trước (lúc {chu_gio_vn(kq['luc'], '%H:%M %d/%m')}). "
                 "Giá có thể đã đổi: thử bấm Làm mới giá sau ít phút.", "warn") if kq.get("cu") else None


def _loi(e: Exception):
    return alert(f"{e} Thử lại sau ít phút, hoặc xem giá trực tiếp ở fpt.vn.", "warn")


def _nhan_xet(r: dict, ten_a: str, ten_b: str) -> str:
    tt = r["tinh_trang"]
    if tt == "chi_a":
        return f"Chỉ {ten_a} bán"
    if tt == "chi_b":
        return f"Chỉ {ten_b} bán"
    if tt == "bang":
        return "Như nhau"
    return f"{ten_b} {'rẻ' if tt == 'b_re' else 'đắt'} hơn {gf.chu_tien(abs(r['chenh']))}"


# ------------------------------------------------------------------ callbacks
def register(app):
    from app.ui.pages import giafpt_ct, giafpt_the, giafpt_vung

    app.clientside_callback(
        "function(t){return [t=='tra'?{}:{display:'none'}, t=='sosanh'?{}:{display:'none'}, t=='vung'?{}:{display:'none'}];}",
        Output("gf-pane-tra", "style"), Output("gf-pane-sosanh", "style"), Output("gf-pane-vung", "style"), Input("gf-tab", "value"))

    @app.callback(*[Output(f"{g}-tinh", "options") for g in ("gf", "gf2a", "gf2b", "gf3")], Input("gf-tab", "value"))
    def _nap_tinh(_tab):
        _vao()
        op = opt_tinh()
        if not op:
            raise PreventUpdate
        return op, op, op, op

    for goc in ("gf", "gf2a", "gf2b"):
        app.callback(Output(f"{goc}-phuong", "options"), Output(f"{goc}-phuong", "value"),
                     Input(f"{goc}-tinh", "value"), State(f"{goc}-phuong", "value"))(_nap_phuong)

    @app.callback(Output("gf2-tb", "children"), Output("gf2-the", "children"), Output("gf2-luoi", "columnDefs"),
                  Output("gf2-luoi", "rowData"), Output("gf2-ctx", "data"),
                  Input("gf-tab", "value"), Input("gf2a-tinh", "value"), Input("gf2a-phuong", "value"), Input("gf2b-tinh", "value"),
                  Input("gf2b-phuong", "value"), Input("gf2-khach", "value"), Input("gf2-khac", "value"), Input("gf-moi", "n_clicks"))
    def _so_sanh(tab, ta, pa, tb, pb, khach, khac, _moi):
        _vao()
        if tab != "sosanh":
            raise PreventUpdate
        if not (ta and pa and tb and pb):
            return alert("Chọn phường / xã cho cả hai bên để so giá.", "info"), [], no_update, [], None
        if ctx.triggered_id == "gf-moi":
            xoa("gia_fpt")
        try:
            a, b = gf.goi_theo_phuong(ta, pa), gf.goi_theo_phuong(tb, pb)
        except gf.LoiGia as e:
            return _loi(e), [], no_update, [], None
        gon = ta == tb
        ten_a, ten_b = ten_khu_vuc(ta, pa, gon), ten_khu_vuc(tb, pb, gon)
        dong = gf.so_sanh(gf.loc_goi(a["goi"], khach), gf.loc_goi(b["goi"], khach))
        dem = gf.dem_so_sanh(dong)
        if khac:
            dong = [r for r in dong if r["tinh_trang"] != "bang"]
        for r in dong:
            r["ghi_chu"] = _nhan_xet(r, ten_a, ten_b)
        cot = [{**c, "headerName": f"Giá ở {ten_a}" if c["field"] == "gia_a" else f"Giá ở {ten_b}" if c["field"] == "gia_b" else c["headerName"]}
               for c in COT_SS]
        luc = min(a["luc"], b["luc"])
        return (_canh_bao(a if a.get("cu") else b), _the_so_sanh(dem, ten_a, ten_b), cot, dong,
                {"ten_a": ten_a, "ten_b": ten_b, "luc": luc.isoformat()})

    @app.callback(Output("gf2-chep", "data-chep"), Input("gf2-luoi", "rowData"), Input("gf2-luoi", "selectedRows"), State("gf2-ctx", "data"))
    def _chep_so_sanh(dong, chon, c):
        _vao()
        if not dong or not c:
            return ""
        from datetime import datetime
        return gf.van_ban_so_sanh(c["ten_a"], c["ten_b"], chon or dong, datetime.fromisoformat(c["luc"]))

    giafpt_the.register(app)
    giafpt_ct.register(app)
    giafpt_vung.register(app)


def _the_so_sanh(dem: dict, ten_a: str, ten_b: str) -> list:
    return [kpi(f"{ten_b} rẻ hơn", dem["b_re"], "gói", "ok" if dem["b_re"] else ""),
            kpi(f"{ten_b} đắt hơn", dem["b_dat"], "gói", "warn" if dem["b_dat"] else ""),
            kpi("Giá như nhau", dem["bang"], "gói"),
            kpi(f"Chỉ {ten_a} bán", dem["chi_a"], "gói"), kpi(f"Chỉ {ten_b} bán", dem["chi_b"], "gói")]


def _nap_phuong(tinh, hien_tai):
    """Đổi tỉnh thì nạp lại danh sách phường; phường đã chọn (kể cả giá trị nhớ trên máy) không thuộc tỉnh mới thì bỏ chọn."""
    _vao()
    if not tinh:
        return [], None
    op = opt_phuong(tinh)
    if not op:
        raise PreventUpdate
    return op, (hien_tai if hien_tai in {o["value"] for o in op} else None)
