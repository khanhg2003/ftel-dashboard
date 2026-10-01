"""Trang Quản trị (chỉ Quản trị BGĐ): Tài khoản · Danh mục nhân sự · Cơ cấu tổ chức · Chỉ tiêu · Nhật ký.

Ba tab sau do settings.py dựng (trước là trang Cấu hình riêng). Lịch sử nạp nằm ở trang Nạp dữ liệu.

Tài khoản và danh mục nhân sự không sửa trực tiếp trong ô nữa: bấm "Sửa" ở cuối dòng (hoặc bấm đúp
vào dòng) mở hộp thoại điền sẵn thông tin, kiểm tra hợp lệ rồi mới lưu. Thêm mới dùng chung hộp thoại
đó. Thao tác xoá đều hỏi lại. Đổi phòng của một acc thì app tự tính lại việc gán phòng.
"""
from __future__ import annotations

import dash_ag_grid as dag
from dash import Input, Output, Patch, State, ctx, dcc, html, no_update
from flask_login import current_user

from app.admin_service import (ROLE_CO_PHONG, ROLES, danh_sach_staff, danh_sach_user, dat_lai_mat_khau, lay_staff,
                               lay_user, luu_mot_staff, pham_vi_options, sua_user, them_user,
                               xoa_staff, xoa_user, xoa_truong_phong_khong_dang_nhap)
from app.db import session_scope
from app.ingest.commit import recompute_phong
from app.mau_nhap import ap_dung_nhan_su, mau_nhan_su, xem_truoc_nhan_su
from app.ui.components import (COT_SUA, MA_NV, MAU_LOAI_THAY_DOI, alert, callback_can_quyen, card,
                               dong_can_sua, gan_import, modal, nut_import, ghi_chu)
from app.ui.icons import icon

CHON = {"field": "_chon", "headerName": "", "width": 44, "maxWidth": 44, "pinned": "left",
        "checkboxSelection": True, "headerCheckboxSelection": True, "sortable": False,
        "resizable": False}
GRID = {"rowSelection": "multiple", "suppressRowClickSelection": True, "suppressCellFocus": True,
        "tooltipShowDelay": 300}
TRANG_THAI_TK = ["Đang dùng", "Ngừng dùng"]

TAB = [("user", "Tài khoản"), ("staff", "Danh mục nhân sự"), ("cocau", "Cơ cấu tổ chức"),
       ("chitieu", "Chỉ tiêu"), ("nhatky", "Nhật ký"), ("ai", "Trợ lý AI")]


def topbar():
    return [html.Div([html.H1("Quản trị"),
                      html.Div("Tài khoản · danh mục nhân sự · cơ cấu tổ chức · chỉ tiêu · nhật ký · trợ lý AI",
                               className="sub")])]


AN = {"display": "none"}


def _o(label, control, id_=None, an=False):
    """Ô nhập có nhãn. Ẩn bằng style (lớp .field đặt display nên thuộc tính hidden không có tác dụng)."""
    kw = {"id": id_, "style": AN if an else {}} if id_ else {}
    return html.Div([html.Label(label), control], className="field rong", **kw)


def _hop_thoai_user():
    return modal("qt-modal-user", html.Span("Thêm tài khoản", id="qt-user-tieu-de"), [
        dcc.Store(id="qt-user-dang-sua"),
        html.Div([
            _o("Tên đăng nhập *", dcc.Input(id="qt-f-username", type="text",
                                            placeholder="vd: truongphong.ibb2", className="inp")),
            _o("Họ tên", dcc.Input(id="qt-f-hoten", type="text", className="inp")),
            _o("Vai trò *", dcc.Dropdown(id="qt-f-role", clearable=False, value="phong",
                                         options=[{"label": t, "value": v} for v, t in ROLES])),
            _o("Phòng phụ trách", dcc.Dropdown(id="qt-f-phamvi", multi=True,
                                               placeholder="Chọn phòng", options=pham_vi_options())),
            _o("Mã NV", dcc.Input(id="qt-f-manv", type="text", className="inp")),
            _o("Email", dcc.Input(id="qt-f-email", type="email", className="inp")),
            _o("Mật khẩu khởi tạo *", dcc.Input(id="qt-f-matkhau", type="text", value="Ftel@2026",
                                                className="inp"), id_="qt-f-matkhau-o"),
            _o("Trạng thái", dcc.Dropdown(id="qt-f-trangthai", clearable=False, value="Đang dùng",
                                          searchable=False, options=TRANG_THAI_TK),
               id_="qt-f-trangthai-o", an=True),
        ], className="form-grid"),
        dcc.Checklist(id="qt-f-mokhoa", options=[{"label": " Mở khoá (tài khoản đang bị khoá do nhập sai "
                                                            "mật khẩu nhiều lần)", "value": "mo"}],
                      value=[], style={"display": "none"}),
        html.Div(id="qt-user-goi-y", className="desc", style={"marginTop": "12px"}),
        html.Div(id="qt-modal-user-msg"),
    ], nut_chinh="Tạo tài khoản")


def _hop_thoai_staff():
    return modal("qt-modal-staff", html.Span("Thêm nhân sự vào danh mục", id="qt-staff-tieu-de"), [
        dcc.Store(id="qt-staff-dang-sua"),
        html.Div([
            _o("Acc inside *", dcc.Input(id="qt-s-acc", type="text", placeholder="vd: DNG.AnhNV1",
                                         className="inp")),
            _o("Phòng *", dcc.Dropdown(id="qt-s-phong", clearable=False, searchable=True,
                                       placeholder="Chọn phòng", options=pham_vi_options())),
            _o("Mã NV", dcc.Input(id="qt-s-manv", type="text", className="inp")),
            _o("Tình trạng", dcc.Dropdown(id="qt-s-nghi", clearable=False, searchable=False, value="lam",
                                          options=[{"label": "Đang làm", "value": "lam"},
                                                   {"label": "Đã nghỉ", "value": "nghi"}])),
            _o("Hiệu lực từ", dcc.DatePickerSingle(id="qt-s-tu", display_format="DD/MM/YYYY",
                                                   placeholder="Không giới hạn", clearable=True,
                                                   first_day_of_week=1, className="date-pick")),
            _o("Hiệu lực đến", dcc.DatePickerSingle(id="qt-s-den", display_format="DD/MM/YYYY",
                                                    placeholder="Không giới hạn", clearable=True,
                                                    first_day_of_week=1, className="date-pick")),
        ], className="form-grid"),
        html.Div(_o("Ghi chú", dcc.Input(id="qt-s-ghichu", type="text", className="inp")),
                 style={"marginTop": "14px"}),
        html.Div(_o("Tên hiển thị", dcc.Input(id="qt-s-ten", type="text", className="inp",
                                              placeholder="vd: Anh Tú")),
                 style={"marginTop": "14px"}),
        ghi_chu("Acc inside quyết định hợp đồng thuộc phòng nào - gõ đúng như trên hệ thống. Ngày hiệu lực "
                "chỉ cần khi nhân sự chuyển phòng giữa kỳ (mỗi phòng một dòng). Lưu xong app tự tính lại "
                "việc gán phòng cho dữ liệu đã nạp. Tên hiển thị chỉ cần khi chưa có trong NSLĐ (vd acc "
                "tạm chưa cấp acc inside chính thức) - có NSLĐ rồi thì bỏ trống, app tự lấy tên chính thức.",
                style={"marginTop": "12px"}),
        html.Div(id="qt-modal-staff-msg"),
    ], nut_chinh="Thêm vào danh mục")


def layout(tab: str | None = None):
    from app.ui import tro_ly
    from app.ui.pages import settings as st
    tab = tab if tab in dict(TAB) else "user"
    an = {"display": "none"}
    return html.Div([
        html.Div([
            dcc.Tabs(id="qt-tab", value=tab, className="seg", children=[
                dcc.Tab(label=ten, value=ma, className="seg-item", selected_className="seg-item active")
                for ma, ten in TAB]),
            html.Div(className="grow"),
            st.chon_ky_ap_dung(tab),
        ], className="toolbar loc-trang"),
        *st.hop_thoai(),
        _hop_thoai_user(),
        _hop_thoai_staff(),
        dcc.ConfirmDialog(id="qt-user-xacnhan", message="Xoá các tài khoản đã chọn?"),
        dcc.ConfirmDialog(id="qt-reset-xacnhan", message="Đặt lại mật khẩu?"),
        dcc.ConfirmDialog(id="qt-staff-xacnhan", message="Xoá các dòng đã chọn khỏi danh mục?"),

        html.Div(id="qt-pane-user", style={} if tab == "user" else an, children=[
            card([
                html.Div([
                    html.Div(className="grow"),
                    html.Button([icon("trash", 14), html.Span("Xoá")], id="qt-user-xoa",
                                className="btn nguy-hiem"),
                    html.Button([icon("refresh", 14), html.Span("Đặt lại mật khẩu")],
                                id="qt-user-reset", className="btn"),
                    html.Button([icon("plus", 14), html.Span("Thêm tài khoản")], id="qt-user-them",
                                className="btn primary"),
                ], className="toolbar"),
                html.Div(id="qt-user-auto-msg"),
                html.Div(id="qt-user-msg"),
                dag.AgGrid(id="qt-user-grid", className="ag-theme-quartz ag-theme-ftel",
                           columnDefs=[], rowData=[], getRowId="params.data.username",
                           defaultColDef={"resizable": True, "sortable": True},
                           dashGridOptions=GRID, style={"width": "100%", "height": "340px"}),
                ghi_chu("Quản trị (BGĐ): toàn quyền, nạp được cả NSLĐ và danh mục nhân viên, xem "
                        "chi tiết nhân sự mọi phòng · Nhập liệu: nạp 3 file bán hàng và xem số "
                        "chung, không xem nhân sự · Trưởng phòng: nạp 3 file bán hàng, xem số chung "
                        "toàn chi nhánh, chi tiết nhân sự chỉ của phòng phụ trách.", nhan="Quyền của từng vai trò",
                        style={"marginTop": "12px"}),
            ], title="Tài khoản người dùng"),
        ]),

        html.Div(id="qt-pane-staff", style={} if tab == "staff" else an, children=[
            card([
                html.Div([
                    dcc.Input(id="qt-staff-tim", type="search", className="o-tim",
                              placeholder="Tìm acc, mã NV, phòng…"),
                    html.Div(id="qt-staff-dem", className="desc", style={"margin": 0}),
                    html.Div(className="grow"),
                    nut_import("qt-ns"),
                    html.Button([icon("trash", 14), html.Span("Xoá")], id="qt-staff-xoa",
                                className="btn nguy-hiem"),
                    html.Button([icon("refresh", 14), html.Span("Tính lại việc gán phòng")],
                                id="qt-staff-tinhlai", className="btn",
                                title="Thường không cần: lưu hoặc import là app tự tính lại"),
                    html.Button([icon("plus", 14), html.Span("Thêm nhân sự")], id="qt-staff-them",
                                className="btn primary"),
                ], className="toolbar"),
                html.Div(id="qt-staff-msg"),
                dag.AgGrid(id="qt-staff-grid", className="ag-theme-quartz ag-theme-ftel",
                           columnDefs=[], rowData=[], getRowId="params.data.id + ''",
                           defaultColDef={"resizable": True, "sortable": True, "filter": True},
                           dashGridOptions={**GRID, "pagination": True, "paginationPageSize": 20,
                                            "paginationPageSizeSelector": False},
                           style={"width": "100%", "height": "480px"}),
                ghi_chu("Thay đổi nhiều: Tải file mẫu (điền sẵn danh mục hiện tại) → sửa → Import Excel. "
                        "Acc không có trong file sẽ được ghi chú “Nghỉ”.", nhan="Sửa hàng loạt",
                        style={"marginTop": "10px"}),
            ], title="Danh mục nhân sự theo phòng"),
        ]),
        *st.cac_tab(tab),
        tro_ly.pane_cau_hinh(tab),
    ])


def _user_cols():
    return [
        CHON,
        {"field": "username", "headerName": "Tài khoản", "minWidth": 140, "flex": 1.2, "pinned": "left"},
        {"field": "ho_ten", "headerName": "Họ tên", "minWidth": 150, "flex": 1.5},
        {"field": "vai_tro", "headerName": "Vai trò", "minWidth": 130, "flex": 1.1},
        {"field": "pham_vi", "headerName": "Phòng phụ trách", "minWidth": 160, "flex": 1.8,
         "tooltipField": "pham_vi"},
        {"field": "ma_nv", "headerName": "Mã NV", "minWidth": 100, "flex": .7, "valueFormatter": MA_NV},
        {"field": "email", "headerName": "Email", "minWidth": 150, "flex": 1.3},
        {"field": "trang_thai", "headerName": "Trạng thái", "minWidth": 110, "flex": .9,
         "cellStyle": {"styleConditions": [
             {"condition": "params.value == 'Đang khoá'", "style": {"color": "#B42318", "fontWeight": "650"}},
             {"condition": "params.value == 'Ngừng dùng'", "style": {"color": "#8A94A6"}}]}},
        {"field": "lan_cuoi", "headerName": "Đăng nhập gần nhất", "minWidth": 140, "flex": 1.1},
        COT_SUA,
    ]


def _staff_cols():
    return [
        CHON,
        {"field": "acc", "headerName": "Acc inside", "minWidth": 150, "flex": 1.4, "pinned": "left"},
        {"field": "phong", "headerName": "Phòng", "minWidth": 150, "flex": 1.4},
        {"field": "ma_nv", "headerName": "Mã NV", "minWidth": 110, "flex": .9, "valueFormatter": MA_NV},
        {"field": "ten_hien_thi", "headerName": "Tên hiển thị ⓘ", "minWidth": 140, "flex": 1.2,
         "headerClass": "co-chu-thich",
         "headerTooltip": "Chỉ dùng khi acc chưa có trong NSLĐ.\nCó NSLĐ rồi thì app tự lấy tên chính thức, "
                          "bỏ qua cột này."},
        {"field": "hieu_luc_tu", "headerName": "Hiệu lực từ", "minWidth": 110, "flex": .9},
        {"field": "hieu_luc_den", "headerName": "Hiệu lực đến", "minWidth": 110, "flex": .9},
        {"field": "ghi_chu", "headerName": "Ghi chú", "minWidth": 160, "flex": 1.8, "tooltipField": "ghi_chu",
         "cellStyle": {"styleConditions": [
             {"condition": "params.value && params.value.toLowerCase().indexOf('nghỉ') >= 0",
              "style": {"color": "#8A94A6"}}]}},
        COT_SUA,
    ]


def _ngay_vn(v) -> str:
    v = str(v or "")[:10]
    return f"{v[8:10]}/{v[5:7]}/{v[:4]}" if len(v) == 10 else ""


def register(app):
    cb = callback_can_quyen(app, "duoc_cau_hinh")   # mọi thao tác ở trang này chỉ dành cho Quản trị
    gan_import(app, "qt-ns", ham_mau=mau_nhan_su, ten_file_mau="Mau_DanhMucNhanSu.xlsx",
               ham_xem=xem_truoc_nhan_su, ham_ap=ap_dung_nhan_su, out_msg="qt-staff-msg",
               cot=[{"field": "loai", "headerName": "Thay đổi", "width": 130, "pinned": "left",
                     "cellStyle": MAU_LOAI_THAY_DOI},
                    {"field": "acc", "headerName": "Acc inside", "width": 170},
                    {"field": "phong_cu", "headerName": "Phòng hiện tại", "width": 130},
                    {"field": "phong_moi", "headerName": "Phòng trong file", "width": 130},
                    {"field": "chi_tiet", "headerName": "Chi tiết", "flex": 1, "minWidth": 220,
                     "tooltipField": "chi_tiet"},
                    {"field": "dong", "headerName": "Dòng", "width": 76}],
               mo_ta_ket_qua=lambda d: [
                   html.B("Đã import danh mục nhân sự. "),
                   f"Thêm mới {d.get('Thêm mới', 0)}, đổi phòng {d.get('Đổi phòng', 0)}, cập nhật "
                   f"{d.get('Cập nhật', 0)}, đánh dấu nghỉ {d.get('Đánh dấu nghỉ', 0)}, bỏ qua "
                   f"{d.get('Lỗi', 0)} dòng lỗi. Đã tính lại phòng cho "
                   f"{d.get('gan_lai_hop_dong', 0)} hợp đồng."])

    @cb(Output("qt-staff-grid", "dashGridOptions"), Input("qt-staff-tim", "value"),
        prevent_initial_call=True)
    def _tim_staff(chu):
        p = Patch()
        p["quickFilterText"] = chu or ""
        return p

    @cb(Output("qt-staff-dem", "children"), Input("qt-staff-grid", "rowData"))
    def _dem_staff(rows):
        rows = rows or []
        nghi = sum(1 for r in rows if "nghỉ" in str(r.get("ghi_chu") or "").lower())
        return f"{len(rows)} acc · {nghi} đã nghỉ"

    @cb(Output("qt-pane-user", "style"), Output("qt-pane-staff", "style"),
        Input("qt-tab", "value"), prevent_initial_call=True)
    def _tab(tab):
        an = {"display": "none"}
        return {} if tab == "user" else an, {} if tab == "staff" else an

    @cb(Output("qt-user-grid", "columnDefs"), Output("qt-user-grid", "rowData"),
        Output("qt-staff-grid", "columnDefs"), Output("qt-staff-grid", "rowData"),
        Output("qt-user-auto-msg", "children"),
        Input("qt-user-msg", "children"), Input("qt-staff-msg", "children"))
    def _nap(*_):
        # Tự động xoá Trưởng phòng không đăng nhập >= 5 ngày
        da_xoa = xoa_truong_phong_khong_dang_nhap()
        msg_xoa = ""
        if da_xoa:
            msg_xoa = alert(
                [html.B(f"Đã tự động xoá {len(da_xoa)} tài khoản Trưởng phòng "
                        f"không đăng nhập quá 5 ngày: "),
                 ", ".join(da_xoa) + "."],
                "warn")
        u = danh_sach_user()
        s = danh_sach_staff()
        if not s.empty:
            s = s.assign(hieu_luc_tu=[_ngay_vn(v) for v in s.hieu_luc_tu],
                         hieu_luc_den=[_ngay_vn(v) for v in s.hieu_luc_den])
        cot_u = ["username", "ho_ten", "vai_tro", "pham_vi", "ma_nv", "email", "trang_thai", "lan_cuoi"]
        return (_user_cols(), [] if u.empty else u[cot_u].astype(object).where(u[cot_u].notna(), "")
                .to_dict("records"),
                _staff_cols(), [] if s.empty else s.to_dict("records"),
                msg_xoa)

    # ------------------------------------------------------------ tài khoản
    @cb(Output("qt-modal-user", "className"), Output("qt-user-tieu-de", "children"),
        Output("qt-modal-user-ok", "children"), Output("qt-user-dang-sua", "data"),
        Output("qt-f-username", "value"), Output("qt-f-username", "disabled"),
        Output("qt-f-hoten", "value"), Output("qt-f-role", "value"), Output("qt-f-phamvi", "value"),
        Output("qt-f-manv", "value"), Output("qt-f-email", "value"), Output("qt-f-trangthai", "value"),
        Output("qt-f-matkhau-o", "style"), Output("qt-f-trangthai-o", "style"),
        Output("qt-f-mokhoa", "value"), Output("qt-f-mokhoa", "style"), Output("qt-user-goi-y", "children"),
        Output("qt-modal-user-msg", "children", allow_duplicate=True),
        Input("qt-user-them", "n_clicks"), Input("qt-user-grid", "cellClicked"),
        Input("qt-user-grid", "cellDoubleClicked"), Input("qt-modal-user-dong", "n_clicks"),
        Input("qt-modal-user-huy", "n_clicks"), Input("qt-user-msg", "children"),
        prevent_initial_call=True)
    def _mo_dong_user(_them, bam, bam_dup, *_):
        giu = (no_update,) * 17
        trig = ctx.triggered_id
        if trig == "qt-user-them":
            return ("modal mo", "Thêm tài khoản", "Tạo tài khoản", None, "", False, "", "phong", [], "", "",
                    "Đang dùng", {}, AN, [], AN, "", "")
        if trig == "qt-user-grid":
            username = dong_can_sua(bam, bam_dup)
            u = lay_user(username) if username else None
            if not u:
                return (no_update,) + giu
            ban_than = u["username"] == current_user.username
            goi_y = f"Đăng nhập gần nhất: {u['lan_cuoi'] or 'chưa đăng nhập'}."
            if ban_than:
                goi_y += " Đây là tài khoản bạn đang dùng: không đổi được vai trò và trạng thái."
            return ("modal mo", f"Sửa tài khoản · {u['username']}", "Lưu thay đổi", u["username"],
                    u["username"], True, u["ho_ten"], u["role"], u["pham_vi"], u["ma_nv"], u["email"],
                    "Đang dùng" if u["active"] else "Ngừng dùng", AN, {}, [],
                    {"marginTop": "10px"} if u["dang_khoa"] else AN, goi_y, "")
        return ("modal",) + giu

    @cb(Output("qt-f-phamvi", "disabled"), Output("qt-f-phamvi", "placeholder"),
        Output("qt-f-role", "disabled"), Output("qt-f-trangthai", "disabled"),
        Input("qt-f-role", "value"), Input("qt-user-dang-sua", "data"))
    def _theo_vai_tro(role, dang_sua):
        ban_than = bool(dang_sua) and dang_sua == current_user.username
        la_tp = role in ROLE_CO_PHONG
        return (not la_tp, "Chọn phòng (kiêm nhiệm chọn nhiều)" if la_tp else "Toàn chi nhánh - không cần chọn",
                ban_than, ban_than)

    @cb(Output("qt-user-msg", "children"), Output("qt-modal-user-msg", "children"),
        Input("qt-modal-user-ok", "n_clicks"), Input("qt-user-reset", "n_clicks"),
        Input("qt-user-xacnhan", "submit_n_clicks"), Input("qt-reset-xacnhan", "submit_n_clicks"),
        State("qt-user-grid", "selectedRows"), State("qt-user-dang-sua", "data"),
        State("qt-f-username", "value"), State("qt-f-hoten", "value"),
        State("qt-f-role", "value"), State("qt-f-phamvi", "value"),
        State("qt-f-manv", "value"), State("qt-f-email", "value"),
        State("qt-f-matkhau", "value"), State("qt-f-trangthai", "value"), State("qt-f-mokhoa", "value"),
        prevent_initial_call=True)
    def _thao_tac_user(_ok, _reset, _xoa, _xn_reset, chon, dang_sua, username, hoten, role, phamvi, manv,
                       email, matkhau, trang_thai, mo_khoa):
        trig = ctx.triggered_id
        if trig == "qt-modal-user-ok":
            d = {"username": username, "ho_ten": hoten, "role": role, "pham_vi": phamvi, "ma_nv": manv,
                 "email": email}
            if dang_sua:
                ok, msg = sua_user(dang_sua, {**d, "trang_thai": trang_thai, "mo_khoa": bool(mo_khoa)},
                                   current_user.username)
            else:
                ok, msg = them_user({**d, "mat_khau": matkhau}, current_user.username)
            return (alert(msg, "ok"), "") if ok else (no_update, alert(msg, "bad"))

        if trig == "qt-user-xacnhan":
            n, bo_qua = xoa_user([r["username"] for r in (chon or [])], current_user.username)
            noi_dung = [html.B(f"Đã xoá {n} tài khoản. ")]
            if bo_qua:
                noi_dung.append("Bỏ qua: " + "; ".join(bo_qua))
            return alert(noi_dung, "warn" if bo_qua else "ok"), no_update

        if trig == "qt-user-reset":                       # bấm nút: chỉ nhắc khi chưa chọn, hỏi lại ở hộp xác nhận
            return (alert("Tích chọn một tài khoản trong bảng trước đã.", "warn"), no_update) if not chon \
                else (no_update, no_update)

        if trig == "qt-reset-xacnhan" and chon:
            mk = dat_lai_mat_khau(chon[0]["username"], current_user.username)
            return alert([html.B(f"Mật khẩu tạm của {chon[0]['username']}: {mk} "),
                          "- báo người dùng đăng nhập rồi đổi ngay ở mục Tài khoản."], "ok"), no_update
        return no_update, no_update

    @cb(Output("qt-reset-xacnhan", "displayed"), Output("qt-reset-xacnhan", "message"),
        Input("qt-user-reset", "n_clicks"), State("qt-user-grid", "selectedRows"), prevent_initial_call=True)
    def _hoi_reset(n, chon):
        if not chon:
            return False, ""
        return True, f"Đặt lại mật khẩu cho {chon[0]['username']}? Mật khẩu cũ sẽ không dùng được nữa."

    @cb(Output("qt-user-xacnhan", "displayed"), Output("qt-user-xacnhan", "message"),
        Input("qt-user-xoa", "n_clicks"), State("qt-user-grid", "selectedRows"),
        prevent_initial_call=True)
    def _hoi_xoa_user(n, chon):
        if not chon:
            return False, ""
        ten = ", ".join(r["username"] for r in chon[:5])
        return True, f"Xoá {len(chon)} tài khoản ({ten})? Thao tác này không hoàn tác được."

    # ------------------------------------------------------ danh mục nhân sự
    @cb(Output("qt-modal-staff", "className"), Output("qt-staff-tieu-de", "children"),
        Output("qt-modal-staff-ok", "children"), Output("qt-staff-dang-sua", "data"),
        Output("qt-s-acc", "value"), Output("qt-s-phong", "value"), Output("qt-s-manv", "value"),
        Output("qt-s-nghi", "value"), Output("qt-s-tu", "date"), Output("qt-s-den", "date"),
        Output("qt-s-ghichu", "value"), Output("qt-s-ten", "value"),
        Output("qt-modal-staff-msg", "children", allow_duplicate=True),
        Input("qt-staff-them", "n_clicks"), Input("qt-staff-grid", "cellClicked"),
        Input("qt-staff-grid", "cellDoubleClicked"), Input("qt-modal-staff-dong", "n_clicks"),
        Input("qt-modal-staff-huy", "n_clicks"), Input("qt-staff-msg", "children"),
        prevent_initial_call=True)
    def _mo_dong_staff(_them, bam, bam_dup, *_):
        giu = (no_update,) * 12
        trig = ctx.triggered_id
        if trig == "qt-staff-them":
            return ("modal mo", "Thêm nhân sự vào danh mục", "Thêm vào danh mục", None, "", None, "", "lam",
                    None, None, "", "", "")
        if trig == "qt-staff-grid":
            id_ = dong_can_sua(bam, bam_dup)
            r = lay_staff(int(id_)) if str(id_ or "").isdigit() else None
            if not r:
                return (no_update,) + giu
            ghi_chu = " · ".join(x.strip() for x in r["ghi_chu"].split("·")
                                 if x.strip() and "nghỉ" not in x.lower())
            return ("modal mo", f"Sửa danh mục · {r['acc']}", "Lưu thay đổi", r["id"], r["acc"], r["phong_code"],
                    r["ma_nv"], "nghi" if r["da_nghi"] else "lam", r["hieu_luc_tu"], r["hieu_luc_den"],
                    ghi_chu, r["ten_hien_thi"], "")
        return ("modal",) + giu

    @cb(Output("qt-staff-xacnhan", "displayed"), Output("qt-staff-xacnhan", "message"),
        Input("qt-staff-xoa", "n_clicks"), State("qt-staff-grid", "selectedRows"),
        prevent_initial_call=True)
    def _hoi_xoa_staff(n, chon):
        if not chon:
            return False, ""
        return True, (f"Xoá {len(chon)} dòng khỏi danh mục nhân sự? "
                      "Hợp đồng của các acc này sẽ về “Chưa gán phòng”.")

    @cb(Output("qt-staff-msg", "children"), Output("qt-modal-staff-msg", "children"),
        Input("qt-modal-staff-ok", "n_clicks"), Input("qt-staff-xacnhan", "submit_n_clicks"),
        Input("qt-staff-tinhlai", "n_clicks"),
        State("qt-staff-grid", "selectedRows"), State("qt-staff-dang-sua", "data"),
        State("qt-s-acc", "value"), State("qt-s-phong", "value"), State("qt-s-manv", "value"),
        State("qt-s-nghi", "value"), State("qt-s-tu", "date"), State("qt-s-den", "date"),
        State("qt-s-ghichu", "value"), State("qt-s-ten", "value"), prevent_initial_call=True)
    def _thao_tac_staff(_ok, _xoa, _tinh, chon, dang_sua, acc, phong, manv, nghi, tu, den, ghi_chu, ten):
        trig = ctx.triggered_id
        if trig == "qt-modal-staff-ok":
            ok, msg, tinh_lai = luu_mot_staff(dang_sua, {"acc": acc, "phong_code": phong, "ma_nv": manv,
                                                         "hieu_luc_tu": tu, "hieu_luc_den": den,
                                                         "ghi_chu": ghi_chu, "da_nghi": nghi == "nghi",
                                                         "ten_hien_thi": ten},
                                              current_user.username)
            if not ok:
                return no_update, alert(msg, "bad")
            noi_dung = [html.B(msg + " ")]
            if tinh_lai:
                with session_scope() as s:
                    doi = recompute_phong(s)
                noi_dung.append(f"Đã tính lại việc gán phòng: {doi} hợp đồng đổi phòng.")
            return alert(noi_dung, "ok"), ""

        if trig == "qt-staff-xacnhan":
            ids = [int(r["id"]) for r in (chon or []) if str(r.get("id") or "").isdigit()]
            if not ids:
                return alert("Không có dòng hợp lệ để xoá.", "warn"), no_update
            xoa_staff(ids, current_user.username)
            with session_scope() as s:
                doi = recompute_phong(s)
            return alert(f"Đã xoá {len(ids)} dòng khỏi danh mục và tính lại gán phòng ({doi} hợp đồng).",
                         "ok"), no_update

        if trig == "qt-staff-tinhlai":
            with session_scope() as s:
                doi = recompute_phong(s)
            return alert([html.B("Đã tính lại việc gán phòng. "),
                          f"{doi} hợp đồng được gán lại."], "ok"), no_update
        return no_update, no_update
