"""Trang Quản trị: tài khoản, danh mục nhân sự (lịch sử nạp nằm ở trang Nạp dữ liệu).

Mọi thao tác thêm đều qua hộp thoại (điền đủ thông tin rồi mới tạo), thao tác xoá
đều hỏi lại, và dòng chưa lưu được tô vàng để không ai bấm nhầm rồi quên lưu.
"""
from __future__ import annotations

import dash_ag_grid as dag
from dash import Input, Output, State, ctx, dcc, html, no_update
from flask_login import current_user

from app.admin_service import (ROLES, danh_sach_staff, danh_sach_user, dat_lai_mat_khau,
                               luu_staff, luu_user, pham_vi_options,
                               them_user, xoa_staff, xoa_user)
from app.db import session_scope
from app.ingest.commit import recompute_phong
from app.org import phong_order
from app.ui.components import alert, card, field, modal, nhac_chua_luu
from app.ui.icons import icon

TRANG_THAI = ["Đang dùng", "Ngừng dùng", "Đang khoá"]
CHON = {"field": "_chon", "headerName": "", "width": 44, "maxWidth": 44, "pinned": "left",
        "checkboxSelection": True, "headerCheckboxSelection": True, "sortable": False,
        "editable": False, "resizable": False}
GRID = {"domLayout": "autoHeight", "stopEditingWhenCellsLoseFocus": True, "singleClickEdit": True,
        "rowSelection": "multiple", "suppressRowClickSelection": True}
# dòng mới thêm hoặc vừa sửa mà chưa bấm Lưu -> nền vàng nhạt
ROW_STYLE = {"styleConditions": [
    {"condition": "params.data._moi === true",
     "style": {"backgroundColor": "#FFF7E0", "fontWeight": "600"}}]}


def topbar():
    return [html.Div([html.H1("Quản trị"),
                      html.Div("Tài khoản · danh mục nhân sự",
                               className="sub")])]


def _o(label, control):
    return html.Div([html.Label(label), control], className="field rong")


def _hop_thoai_user():
    return modal("qt-modal-user", "Thêm tài khoản", [
        html.Div([
            _o("Tên đăng nhập *", dcc.Input(id="qt-f-username", type="text",
                                            placeholder="vd: truongphong.ibb2", className="inp")),
            _o("Họ tên", dcc.Input(id="qt-f-hoten", type="text", className="inp")),
            _o("Vai trò *", dcc.Dropdown(id="qt-f-role", clearable=False, value="phong",
                                         options=[{"label": t, "value": v} for v, t in ROLES])),
            _o("Phòng phụ trách", dcc.Dropdown(id="qt-f-phamvi", multi=True,
                                               placeholder="Chỉ chọn cho Trưởng phòng",
                                               options=pham_vi_options())),
            _o("Mã NV", dcc.Input(id="qt-f-manv", type="text", className="inp")),
            _o("Email", dcc.Input(id="qt-f-email", type="text", className="inp")),
            _o("Mật khẩu khởi tạo *", dcc.Input(id="qt-f-matkhau", type="text", value="Ftel@2026",
                                                className="inp")),
        ], className="form-grid"),
        html.Div("Quản trị và Nhập liệu không cần chọn phòng. Trưởng phòng chọn phòng mình "
                 "phụ trách (kiêm nhiệm thì chọn nhiều phòng).", className="desc"),
        html.Div(id="qt-modal-user-msg"),
    ], nut_chinh="Tạo tài khoản")


def _hop_thoai_staff():
    ten_phong = [{"label": p["ten"], "value": p["ten"]} for p in phong_order()]
    return modal("qt-modal-staff", "Thêm nhân sự vào danh mục", [
        html.Div([
            _o("Acc inside *", dcc.Input(id="qt-s-acc", type="text", placeholder="vd: DNG.AnhNV1",
                                         className="inp")),
            _o("Phòng kinh doanh *", dcc.Dropdown(id="qt-s-phong", options=ten_phong,
                                                  value=ten_phong[0]["value"] if ten_phong else None,
                                                  clearable=False)),
            _o("Mã NV", dcc.Input(id="qt-s-manv", type="text", className="inp")),
            _o("Hiệu lực từ", dcc.Input(id="qt-s-tu", type="text", placeholder="2026-09-01",
                                        className="inp")),
            _o("Hiệu lực đến", dcc.Input(id="qt-s-den", type="text", className="inp")),
            _o("Ghi chú", dcc.Input(id="qt-s-ghichu", type="text", className="inp")),
        ], className="form-grid"),
        html.Div("Acc inside quyết định hợp đồng thuộc phòng nào - gõ đúng như trên hệ thống. "
                 "Ngày hiệu lực chỉ cần khi nhân sự chuyển phòng giữa kỳ.", className="desc"),
        html.Div(id="qt-modal-staff-msg"),
    ], nut_chinh="Thêm vào danh mục")


def layout():
    return html.Div([
        dcc.Tabs(id="qt-tab", value="user", className="seg", children=[
            dcc.Tab(label="Tài khoản", value="user", className="seg-item",
                    selected_className="seg-item active"),
            dcc.Tab(label="Danh mục nhân sự", value="staff", className="seg-item",
                    selected_className="seg-item active"),
        ]),
        html.Div(style={"height": "16px"}),
        _hop_thoai_user(),
        _hop_thoai_staff(),
        dcc.ConfirmDialog(id="qt-user-xacnhan", message="Xoá các tài khoản đã chọn?"),
        dcc.ConfirmDialog(id="qt-staff-xacnhan", message="Xoá các dòng đã chọn khỏi danh mục?"),

        html.Div(id="qt-pane-user", children=[
            card([
                html.Div([
                    html.Div("Sửa trực tiếp trong ô rồi bấm Lưu thay đổi. Chọn dòng bằng ô "
                             "tích trước khi xoá hoặc đặt lại mật khẩu.",
                             className="desc", style={"margin": 0}),
                    html.Div(id="qt-user-nhac", style={"marginLeft": "10px"}),
                    html.Div(className="grow"),
                    html.Button([icon("trash", 14), html.Span("Xoá")], id="qt-user-xoa",
                                className="btn nguy-hiem"),
                    html.Button([icon("refresh", 14), html.Span("Đặt lại mật khẩu")],
                                id="qt-user-reset", className="btn"),
                    html.Button([icon("plus", 14), html.Span("Thêm tài khoản")], id="qt-user-them",
                                className="btn"),
                    html.Button([icon("save", 14), html.Span("Lưu thay đổi")], id="qt-user-luu",
                                className="btn primary"),
                ], className="toolbar"),
                html.Div(id="qt-user-msg"),
                dag.AgGrid(id="qt-user-grid", className="ag-theme-quartz ag-theme-ftel",
                           columnDefs=[], rowData=[],
                           defaultColDef={"resizable": True, "sortable": True},
                           dashGridOptions={**GRID, "domLayout": "normal"},
                           getRowStyle=ROW_STYLE, style={"width": "100%", "height": "340px"}),
                html.Div("Quản trị (BGĐ): toàn quyền, xem chi tiết nhân sự mọi phòng · Nhập liệu: "
                         "nạp dữ liệu và xem số chung, không xem nhân sự · Trưởng phòng: xem số "
                         "chung toàn chi nhánh, chi tiết nhân sự chỉ của phòng phụ trách.",
                         className="desc", style={"marginTop": "12px"}),
            ], title="Tài khoản người dùng"),
        ]),

        html.Div(id="qt-pane-staff", children=[
            card([
                html.Div([
                    html.Div("Bảng ghép acc người bán với phòng. Sửa xong bấm “Tính lại việc "
                             "gán phòng” để áp cho dữ liệu đã nạp.",
                             className="desc", style={"margin": 0}),
                    html.Div(id="qt-staff-nhac", style={"marginLeft": "10px"}),
                    html.Div(className="grow"),
                    html.Button([icon("trash", 14), html.Span("Xoá")], id="qt-staff-xoa",
                                className="btn nguy-hiem"),
                    html.Button([icon("refresh", 14), html.Span("Tính lại việc gán phòng")],
                                id="qt-staff-tinhlai", className="btn"),
                    html.Button([icon("plus", 14), html.Span("Thêm nhân sự")], id="qt-staff-them",
                                className="btn"),
                    html.Button([icon("save", 14), html.Span("Lưu thay đổi")], id="qt-staff-luu",
                                className="btn primary"),
                ], className="toolbar"),
                html.Div(id="qt-staff-msg"),
                dag.AgGrid(id="qt-staff-grid", className="ag-theme-quartz ag-theme-ftel",
                           columnDefs=[], rowData=[],
                           defaultColDef={"resizable": True, "sortable": True, "filter": True},
                           dashGridOptions={**GRID, "domLayout": "normal", "pagination": True,
                                            "paginationPageSize": 20,
                                            "paginationPageSizeSelector": False},
                           getRowStyle=ROW_STYLE, style={"width": "100%", "height": "460px"}),
            ], title="Danh mục nhân sự theo phòng"),
        ]),

    ])


def _user_cols():
    return [
        CHON,
        {"field": "username", "headerName": "Tài khoản", "editable": False, "minWidth": 140,
         "flex": 1.3, "pinned": "left"},
        {"field": "ho_ten", "headerName": "Họ tên", "editable": True, "minWidth": 150, "flex": 1.6},
        {"field": "vai_tro", "headerName": "Vai trò", "editable": True, "minWidth": 140,
         "flex": 1.3, "cellEditor": "agSelectCellEditor",
         "cellEditorParams": {"values": [t for _, t in ROLES]}},
        {"field": "pham_vi", "headerName": "Phòng phụ trách", "editable": True, "minWidth": 180,
         "flex": 2, "tooltipField": "pham_vi",
         "headerTooltip": "Chỉ dùng cho Trưởng phòng. Nhiều phòng thì cách nhau dấu phẩy"},
        {"field": "ma_nv", "headerName": "Mã NV", "editable": True, "minWidth": 90, "flex": .8},
        {"field": "email", "headerName": "Email", "editable": True, "minWidth": 150, "flex": 1.4},
        {"field": "trang_thai", "headerName": "Trạng thái", "editable": True, "minWidth": 120,
         "flex": 1, "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": TRANG_THAI}},
        {"field": "lan_cuoi", "headerName": "Đăng nhập gần nhất", "editable": False,
         "minWidth": 150, "flex": 1.2},
    ]


def _staff_cols():
    ten_phong = [p["ten"] for p in phong_order()]
    return [
        CHON,
        {"field": "acc", "headerName": "Acc inside", "editable": True, "minWidth": 150,
         "flex": 1.4, "pinned": "left"},
        {"field": "phong", "headerName": "Phòng kinh doanh", "editable": True, "minWidth": 160,
         "flex": 1.6, "cellEditor": "agSelectCellEditor",
         "cellEditorParams": {"values": ten_phong}},
        {"field": "ma_nv", "headerName": "Mã NV", "editable": True, "minWidth": 100, "flex": .9},
        {"field": "hieu_luc_tu", "headerName": "Hiệu lực từ", "editable": True, "minWidth": 120,
         "flex": 1, "headerTooltip": "yyyy-mm-dd, để trống nếu áp dụng mọi thời điểm"},
        {"field": "hieu_luc_den", "headerName": "Hiệu lực đến", "editable": True, "minWidth": 120,
         "flex": 1},
        {"field": "ghi_chu", "headerName": "Ghi chú", "editable": True, "minWidth": 140,
         "flex": 1.6},
        {"field": "id", "headerName": "ID", "editable": False, "width": 80, "maxWidth": 80},
    ]


def register(app):
    nhac_chua_luu(app, "qt-user-grid", "qt-user-nhac", "qt-user-msg")
    nhac_chua_luu(app, "qt-staff-grid", "qt-staff-nhac", "qt-staff-msg")

    @app.callback(Output("qt-pane-user", "style"), Output("qt-pane-staff", "style"),
                  Input("qt-tab", "value"))
    def _tab(tab):
        an = {"display": "none"}
        return {} if tab == "user" else an, {} if tab == "staff" else an

    @app.callback(Output("qt-user-grid", "columnDefs"), Output("qt-user-grid", "rowData"),
                  Output("qt-staff-grid", "columnDefs"), Output("qt-staff-grid", "rowData"),
                  Input("qt-user-msg", "children"), Input("qt-staff-msg", "children"))
    def _nap(*_):
        u = danh_sach_user()
        s = danh_sach_staff()
        return (_user_cols(), [] if u.empty else u.to_dict("records"),
                _staff_cols(), [] if s.empty else s.to_dict("records"))

    # ------------------------------------------------------------ tài khoản
    @app.callback(Output("qt-modal-user", "className"),
                  Input("qt-user-them", "n_clicks"), Input("qt-modal-user-dong", "n_clicks"),
                  Input("qt-modal-user-huy", "n_clicks"), Input("qt-user-msg", "children"),
                  prevent_initial_call=True)
    def _mo_dong_user(_a, _b, _c, _d):
        return "modal mo" if ctx.triggered_id == "qt-user-them" else "modal"

    @app.callback(Output("qt-user-msg", "children"), Output("qt-modal-user-msg", "children"),
                  Input("qt-modal-user-ok", "n_clicks"), Input("qt-user-luu", "n_clicks"),
                  Input("qt-user-reset", "n_clicks"), Input("qt-user-xacnhan", "submit_n_clicks"),
                  State("qt-user-grid", "rowData"), State("qt-user-grid", "selectedRows"),
                  State("qt-f-username", "value"), State("qt-f-hoten", "value"),
                  State("qt-f-role", "value"), State("qt-f-phamvi", "value"),
                  State("qt-f-manv", "value"), State("qt-f-email", "value"),
                  State("qt-f-matkhau", "value"), prevent_initial_call=True)
    def _thao_tac_user(_a, _b, _c, _d, rows, chon, username, hoten, role, phamvi, manv, email,
                       matkhau):
        trig = ctx.triggered_id
        if trig == "qt-modal-user-ok":
            ok, msg = them_user({"username": username, "ho_ten": hoten, "role": role,
                                 "pham_vi": phamvi, "ma_nv": manv, "email": email,
                                 "mat_khau": matkhau}, current_user.username)
            return (alert(msg, "ok"), "") if ok else (no_update, alert(msg, "bad"))

        if trig == "qt-user-xacnhan":
            n, bo_qua = xoa_user([r["username"] for r in (chon or [])], current_user.username)
            noi_dung = [html.B(f"Đã xoá {n} tài khoản. ")]
            if bo_qua:
                noi_dung.append("Bỏ qua: " + "; ".join(bo_qua))
            return alert(noi_dung, "warn" if bo_qua else "ok"), ""

        if trig == "qt-user-reset":
            if not chon:
                return alert("Tick chọn một tài khoản trong bảng trước đã.", "warn"), ""
            mk = dat_lai_mat_khau(chon[0]["username"], current_user.username)
            return alert([html.B(f"Mật khẩu mới của {chon[0]['username']}: {mk} "),
                          "— báo người dùng đổi lại ngay sau khi đăng nhập."], "ok"), ""

        n, canh_bao = luu_user(rows, current_user.username)
        noi_dung = [html.B(f"Đã lưu {n} tài khoản. ")]
        if canh_bao:
            noi_dung.append("Tài khoản mới dùng mật khẩu khởi tạo Ftel@2026: "
                            + ", ".join(c.split(":")[0] for c in canh_bao))
        return alert(noi_dung, "ok"), ""

    @app.callback(Output("qt-user-xacnhan", "displayed"), Output("qt-user-xacnhan", "message"),
                  Input("qt-user-xoa", "n_clicks"), State("qt-user-grid", "selectedRows"),
                  prevent_initial_call=True)
    def _hoi_xoa_user(n, chon):
        if not chon:
            return False, ""
        ten = ", ".join(r["username"] for r in chon[:5])
        return True, f"Xoá {len(chon)} tài khoản ({ten})? Thao tác này không hoàn tác được."

    # ------------------------------------------------------ danh mục nhân sự
    @app.callback(Output("qt-modal-staff", "className"),
                  Input("qt-staff-them", "n_clicks"), Input("qt-modal-staff-dong", "n_clicks"),
                  Input("qt-modal-staff-huy", "n_clicks"), Input("qt-staff-msg", "children"),
                  prevent_initial_call=True)
    def _mo_dong_staff(_a, _b, _c, _d):
        return "modal mo" if ctx.triggered_id == "qt-staff-them" else "modal"

    @app.callback(Output("qt-staff-xacnhan", "displayed"), Output("qt-staff-xacnhan", "message"),
                  Input("qt-staff-xoa", "n_clicks"), State("qt-staff-grid", "selectedRows"),
                  prevent_initial_call=True)
    def _hoi_xoa_staff(n, chon):
        if not chon:
            return False, ""
        return True, (f"Xoá {len(chon)} dòng khỏi danh mục nhân sự? "
                      "Hợp đồng của các acc này sẽ về “Chưa gán phòng”.")

    @app.callback(Output("qt-staff-msg", "children"), Output("qt-modal-staff-msg", "children"),
                  Input("qt-modal-staff-ok", "n_clicks"), Input("qt-staff-luu", "n_clicks"),
                  Input("qt-staff-xacnhan", "submit_n_clicks"),
                  Input("qt-staff-tinhlai", "n_clicks"),
                  State("qt-staff-grid", "rowData"), State("qt-staff-grid", "selectedRows"),
                  State("qt-s-acc", "value"), State("qt-s-phong", "value"),
                  State("qt-s-manv", "value"), State("qt-s-tu", "value"),
                  State("qt-s-den", "value"), State("qt-s-ghichu", "value"),
                  prevent_initial_call=True)
    def _thao_tac_staff(_a, _b, _c, _d, rows, chon, acc, phong, manv, tu, den, ghi_chu):
        trig = ctx.triggered_id
        if trig == "qt-modal-staff-ok":
            if not (acc or "").strip():
                return no_update, alert("Chưa nhập acc inside.", "bad")
            n, loi = luu_staff([{"acc": acc, "phong": phong, "ma_nv": manv, "hieu_luc_tu": tu,
                                 "hieu_luc_den": den, "ghi_chu": ghi_chu}], current_user.username)
            if loi:
                return no_update, alert("; ".join(loi), "bad")
            return alert([html.B(f"Đã thêm {acc} vào {phong}. "),
                          "Bấm “Tính lại việc gán phòng” để áp cho dữ liệu đã nạp."], "ok"), ""

        if trig == "qt-staff-xacnhan":
            ids = [int(r["id"]) for r in (chon or []) if str(r.get("id") or "").isdigit()]
            if not ids:
                return alert("Không có dòng hợp lệ để xoá.", "warn"), ""
            xoa_staff(ids, current_user.username)
            return alert(f"Đã xoá {len(ids)} dòng khỏi danh mục.", "ok"), ""

        if trig == "qt-staff-tinhlai":
            with session_scope() as s:
                doi = recompute_phong(s)
            return alert([html.B("Đã tính lại việc gán phòng. "),
                          f"{doi} hợp đồng được gán lại."], "ok"), ""

        n, loi = luu_staff(rows, current_user.username)
        if loi:
            return alert([html.B(f"Đã lưu {n} dòng, {len(loi)} dòng bị bỏ qua: "),
                          "; ".join(loi[:5])], "warn"), ""
        return alert([html.B(f"Đã lưu {n} dòng. "),
                      "Bấm “Tính lại việc gán phòng” để áp cho dữ liệu đã nạp."], "ok"), ""
