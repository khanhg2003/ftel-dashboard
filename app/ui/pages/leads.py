"""Trang Lead Online (chốt 16/11/2026): một kho lead duy nhất thay cho nhiều tab Google Sheet theo tỉnh.

Bảng sửa ngay trong ô như Google Sheet (cùng kiểu với Nhập tồn - app/ui/pages/nhapton.py), tự lưu từng ô.
Đổi ô "Sale tư vấn" của một lead đang quá hạn = chính là thao tác "nhận chéo". Quyền xem/sửa lead: tài khoản
vai trò "online" (5 bạn trong nhóm) và admin (`current_user.duoc_xem_phong_online`, giống trang Phòng Online).
Mục Cấu hình (danh mục page, người nhận cảnh báo Zalo, kết nối Messenger) chỉ admin (`duoc_cau_hinh`).
"""
from __future__ import annotations

from datetime import date

from dash import Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate
from flask_login import current_user

from app import canh_bao_lead as cb
from app import leads
from app.auth import ghi_log
from app.thoi_gian import gio_viet_nam
from app.ui.components import alert, field, modal
from app.ui.icons import icon
from app.ui.luoi import SO, bang

AN = {"display": "none"}
TAT_CA = "Tất cả"
QUA_HAN_LOP = "params.data.qua_han"
GIO_TRE_MAU = {"styleConditions": [{"condition": QUA_HAN_LOP, "style": {"color": "#B42318", "fontWeight": "700"}}]}


def topbar():
    return [html.Div([html.H1("Lead Online"),
                      html.Div("Mọi lead của Phòng Online ở một chỗ - bấm vào ô để sửa, sửa xong tự lưu",
                               className="sub")])]


def _duoc_xem() -> bool:
    return bool(getattr(current_user, "is_authenticated", False)) and current_user.duoc_xem_phong_online


def _cot() -> list[dict]:
    sua = {"editable": True, "cellClass": "o-sale"}
    return [
        {"field": "id", "headerName": "#", "width": 56, "maxWidth": 64, "pinned": "left", "cellClass": "o-dam"},
        {"field": "ngay", "headerName": "Ngày", "width": 92, "maxWidth": 100},
        {"field": "tinh", "headerName": "Tỉnh / Page", "minWidth": 110, "flex": 1},
        {"field": "ten_kh", "headerName": "Tên KH", "minWidth": 130, "flex": 1.3, **sua},
        {"field": "sdt", "headerName": "SĐT", "minWidth": 100, "width": 110, **sua},
        {"field": "dia_chi", "headerName": "Địa chỉ", "minWidth": 140, "flex": 1.4, **sua},
        {"field": "nhu_cau", "headerName": "Nhu cầu", "minWidth": 100, "width": 110, **sua},
        {"field": "tinh_trang_xu_ly", "headerName": "Tình trạng xử lý", "minWidth": 130, "width": 140,
         "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": leads.TRANG_THAI}, **sua},
        {"field": "sale_ten", "headerName": "Sale tư vấn", "minWidth": 110, "width": 120,
         "cellEditor": "agSelectCellEditor",
         "cellEditorParams": {"values": [a["ten"] for a in leads.nguoi_online()]}, **sua},
        {"field": "kh_dung_mang", "headerName": "KH dùng mạng", "minWidth": 100, "width": 120, **sua},
        {"field": "sale_len", "headerName": "Sale lên", "minWidth": 100, "width": 110, **sua},
        {"field": "mo_hinh", "headerName": "Mô hình", "minWidth": 100, "width": 120, **sua},
        {"field": "tu_van_1", "headerName": "Tư vấn", "minWidth": 160, "flex": 1.6, "wrapText": True,
         "autoHeight": True, "cellEditor": "agLargeTextCellEditor", "cellEditorPopup": True, **sua},
        {"field": "gio_tre", "headerName": "Trễ (giờ)", "width": 86, "maxWidth": 96, "type": "numericColumn",
         "valueFormatter": SO, "cellStyle": GIO_TRE_MAU,
         "headerTooltip": f"Số giờ từ lần chăm sóc gần nhất. Quá {leads.HAN_SLA_GIO}h chưa đổi trạng thái -> đỏ, "
                          "hệ thống tự báo Zalo để nhờ người khác nhận chéo."},
    ]


def layout():
    if not _duoc_xem():
        return alert("Tài khoản này không xem được mục Lead Online.", "bad")
    leads.dam_bao_bang()
    pages = leads.ds_page()
    nguoi = leads.nguoi_online()
    opt_page = [{"label": t, "value": i} for i, t in zip(pages.id, pages.ten)] if len(pages) else []
    opt_sale = [{"label": a["ten"], "value": a["acc_norm"]} for a in nguoi]
    return html.Div([
        dcc.Store(id="ld-da-luu"),
        html.Div(id="ld-msg"),
        html.Div(id="ld-kpi", className="kpi-row kpi-3"),
        html.Div([
            html.Div([
                field("Tỉnh / Page", dcc.Dropdown(id="ld-loc-page", options=opt_page, placeholder=TAT_CA,
                                                  style={"minWidth": "160px"})),
                field("Sale", dcc.Dropdown(id="ld-loc-sale", options=opt_sale, placeholder=TAT_CA,
                                           style={"minWidth": "140px"})),
                field("Trạng thái", dcc.Dropdown(id="ld-loc-tt", options=leads.TRANG_THAI, placeholder=TAT_CA,
                                                 style={"minWidth": "150px"})),
                dcc.Input(id="ld-tim", type="search", placeholder="Tìm tên hoặc SĐT…", className="o-tim"),
                html.Div(className="grow"),
                html.Button([icon("plus", 14), html.Span("Thêm lead")], id="ld-them-mo", className="btn primary"),
            ], className="toolbar", style={"flexWrap": "wrap"}),
            dcc.Loading(bang("ld-luoi", _cot(), cao=560, lop="ag-theme-quartz ag-theme-ftel luoi-ke",
                             getRowId="params.data.id",
                             tuy_chon={"singleClickEdit": True, "stopEditingWhenCellsLoseFocus": True,
                                       "rowClassRules": {"dong-do": QUA_HAN_LOP}})),
            html.Div("Bấm vào ô để sửa, sửa xong tự lưu. Đổi ô \"Sale tư vấn\" của một lead đang trễ (đỏ) "
                     "chính là thao tác nhận chéo.", className="goi-y-bam"),
        ], className="card"),
        modal("ld-md", "Thêm lead mới", [
            html.Div([
                field("Tỉnh / Page *", dcc.Dropdown(id="ld-f-page", options=opt_page, placeholder="Chọn page")),
                field("Ngày", dcc.Input(id="ld-f-ngay", type="date", className="inp", value=date.today().isoformat())),
                field("Tên KH", dcc.Input(id="ld-f-ten", className="inp")),
                field("SĐT", dcc.Input(id="ld-f-sdt", className="inp")),
                field("Địa chỉ", dcc.Input(id="ld-f-diachi", className="inp")),
                field("Nhu cầu", dcc.Input(id="ld-f-nhucau", className="inp")),
                field("Trạng thái", dcc.Dropdown(id="ld-f-tt", options=leads.TRANG_THAI, value="Mới",
                                                 clearable=False)),
                field("Sale tư vấn", dcc.Dropdown(id="ld-f-sale", options=opt_sale, placeholder="Chưa gán")),
                field("KH dùng mạng", dcc.Input(id="ld-f-mang", className="inp")),
                field("Mô hình", dcc.Input(id="ld-f-mohinh", className="inp")),
            ], className="form-grid"),
            field("Tư vấn", dcc.Textarea(id="ld-f-tuvan", className="inp", style={"width": "100%", "minHeight": "70px"})),
            html.Div(id="ld-md-msg"),
        ], nut_chinh="Thêm"),
        # Luôn render (ẩn bằng CSS, không bỏ khỏi cây) để callback của mục Cấu hình không lỗi
        # "nonexistent object" khi tài khoản không phải admin xem trang - callback vẫn tự kiểm
        # quyền `duoc_cau_hinh` ở máy chủ trước khi trả dữ liệu (như `callback_can_quyen` đang làm).
        html.Div(_cau_hinh(), style={} if current_user.duoc_cau_hinh else AN),
    ])


def _cau_hinh():
    pages = leads.ds_page()
    opt_page = [{"label": t, "value": i} for i, t in zip(pages.id, pages.ten)] if len(pages) else []
    opt_sale = [{"label": a["ten"], "value": a["acc_norm"]} for a in leads.nguoi_online()]
    return html.Details([
        html.Summary("Cấu hình (chỉ Quản trị)", className="cg-tieu-de"),
        html.Div([
            html.H3("Danh mục page / tỉnh", style={"margin": "4px 0"}),
            html.Div([
                field("Tên page / tỉnh", dcc.Input(id="ld-pg-ten", className="inp", placeholder="VD: Hải Phòng")),
                field("Ghi chú", dcc.Input(id="ld-pg-ghichu", className="inp")),
                field(" ", html.Button([icon("plus", 14), html.Span("Thêm page")], id="ld-pg-them",
                                       className="btn primary")),
            ], className="toolbar", style={"flexWrap": "wrap"}),
            html.Div(id="ld-pg-msg"),
            bang("ld-g-page", [
                {"field": "id", "headerName": "#", "width": 56},
                {"field": "ten", "headerName": "Tên ✎", "editable": True, "minWidth": 160, "flex": 1},
                {"field": "ghi_chu", "headerName": "Ghi chú ✎", "editable": True, "minWidth": 160, "flex": 1},
                {"field": "fb_page_id", "headerName": "Facebook Page ID", "minWidth": 140},
                {"field": "active", "headerName": "Đang dùng ✎", "editable": True, "width": 100,
                 "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": [True, False]}},
            ], cao=240, getRowId="params.data.id"),
            html.Button([icon("save", 14), html.Span("Lưu danh mục")], id="ld-pg-luu", className="btn primary",
                        style={"marginTop": "8px"}),

            html.H3("Người nhận cảnh báo SLA (Zalo)", style={"margin": "18px 0 4px"}),
            html.Div("Sale: gắn acc để tính tải việc khi gợi ý nhận chéo. Leader: chỉ nhận tin, không tính tải việc.",
                     className="desc"),
            html.Div([
                field("Vai trò", dcc.Dropdown(id="ld-nn-vt", options=[{"label": "Sale (5 bạn Online)", "value": "sale"},
                                                                      {"label": "Leader", "value": "leader"}],
                                              value="leader", clearable=False, style={"minWidth": "160px"})),
                field("Tên", dcc.Input(id="ld-nn-ten", className="inp")),
                field("Acc (chỉ khi là Sale)", dcc.Dropdown(id="ld-nn-acc", options=opt_sale)),
                field("Chat ID Zalo", dcc.Input(id="ld-nn-chatid", className="inp")),
                field(" ", html.Button([icon("plus", 14), html.Span("Thêm người nhận")], id="ld-nn-them",
                                       className="btn primary")),
            ], className="toolbar", style={"flexWrap": "wrap"}),
            html.Div(id="ld-nn-msg"),
            bang("ld-g-nn", [
                {"field": "vai_tro", "headerName": "Vai trò", "width": 90, "checkboxSelection": True},
                {"field": "ten", "headerName": "Tên", "minWidth": 130, "flex": 1},
                {"field": "acc_norm", "headerName": "Acc", "minWidth": 110, "flex": 1},
                {"field": "chat_id", "headerName": "Chat ID", "minWidth": 120, "flex": 1},
                {"field": "bat", "headerName": "Đang bật", "width": 90},
            ], cao=220, getRowId="params.data.id", tuy_chon={"rowSelection": "multiple"}),
            html.Button([icon("trash", 14), html.Span("Xoá người nhận đã chọn")], id="ld-nn-xoa",
                        className="btn nguy-hiem", style={"marginTop": "8px"}),

            html.H3("Kết nối Messenger (tự bắt lead)", style={"margin": "18px 0 4px"}),
            html.Div("Tạo Meta App + lấy Page Access Token trên Meta for Developers (ngoài app). Dán vào đây rồi "
                     "bấm Đăng ký webhook - app tự gọi Facebook, không cần vào Business Suite.", className="desc"),
            html.Div([
                field("Page", dcc.Dropdown(id="ld-fb-page", options=opt_page, style={"minWidth": "180px"})),
                field("Facebook Page ID", dcc.Input(id="ld-fb-id", className="inp")),
                field("Page Access Token", dcc.Input(id="ld-fb-token", className="inp", type="password")),
                field(" ", html.Button([icon("save", 14), html.Span("Lưu kết nối")], id="ld-fb-luu",
                                       className="btn primary")),
                field(" ", html.Button([icon("refresh", 14), html.Span("Đăng ký webhook")], id="ld-fb-dangky",
                                       className="btn")),
            ], className="toolbar", style={"flexWrap": "wrap"}),
            html.Div(id="ld-fb-msg"),
        ], className="chu-giai", style={"marginTop": "10px"}),
    ], className="card")


def _kpi(df) -> list:
    tong = len(df)
    mo = int((~df.tinh_trang_xu_ly.isin(leads.TRANG_THAI_DONG)).sum()) if tong else 0
    qua_han = int(df.qua_han.sum()) if tong else 0
    from app.ui.components import kpi
    return [kpi("Tổng lead", f"{tong}"), kpi("Đang xử lý", f"{mo}"),
            kpi("Quá hạn care", f"{qua_han}", f"Trên {leads.HAN_SLA_GIO}h chưa chăm sóc", "bad" if qua_han else "ok")]


def register(app):
    @app.callback(Output("ld-kpi", "children"), Output("ld-luoi", "rowData"),
                  Input("ld-loc-page", "value"), Input("ld-loc-sale", "value"), Input("ld-loc-tt", "value"),
                  Input("ld-da-luu", "data"))
    def _nap(page_id, sale, tt, _luu):
        if not _duoc_xem():
            raise PreventUpdate
        df = leads.danh_sach(page_id=page_id, sale=sale, tinh_trang=tt)
        if df.empty:
            return _kpi(df), []
        out = df.assign(ngay=[str(x)[:10] for x in df.ngay])
        return _kpi(df), out.to_dict("records")

    @app.callback(Output("ld-luoi", "dashGridOptions"), Input("ld-tim", "value"), prevent_initial_call=True)
    def _tim(chu):
        from dash import Patch
        p = Patch()
        p["quickFilterText"] = chu or ""
        return p

    @app.callback(Output("ld-md", "className", allow_duplicate=True),
                  Output("ld-md-msg", "children", allow_duplicate=True),
                  Input("ld-them-mo", "n_clicks"), Input("ld-md-dong", "n_clicks"), Input("ld-md-huy", "n_clicks"),
                  Input("ld-da-luu", "data"), prevent_initial_call=True)
    def _mo_dong(_a, _b, _c, _d):
        return ("modal mo" if ctx.triggered_id == "ld-them-mo" else "modal"), ""

    @app.callback(Output("ld-md-msg", "children", allow_duplicate=True),
                  Output("ld-da-luu", "data", allow_duplicate=True), Output("ld-md", "className", allow_duplicate=True),
                  Input("ld-md-ok", "n_clicks"),
                  State("ld-f-page", "value"), State("ld-f-ngay", "value"), State("ld-f-ten", "value"),
                  State("ld-f-sdt", "value"), State("ld-f-diachi", "value"), State("ld-f-nhucau", "value"),
                  State("ld-f-tt", "value"), State("ld-f-sale", "value"), State("ld-f-mang", "value"),
                  State("ld-f-mohinh", "value"), State("ld-f-tuvan", "value"), prevent_initial_call=True)
    def _them(_n, page_id, ngay, ten, sdt, diachi, nhucau, tt, sale, mang, mohinh, tuvan):
        if not _duoc_xem():
            raise PreventUpdate
        try:
            leads.tao_lead({"page_id": page_id, "ngay": ngay, "ten_kh": ten, "sdt": sdt, "dia_chi": diachi,
                            "nhu_cau": nhucau, "tinh_trang_xu_ly": tt, "sale_tu_van": sale,
                            "kh_dung_mang": mang, "mo_hinh": mohinh, "tu_van_1": tuvan}, current_user.username)
        except leads.LoiLead as e:
            return alert(str(e), "bad"), no_update, no_update
        return "", gio_viet_nam().isoformat(), "modal"

    @app.callback(Output("ld-msg", "children"), Output("ld-da-luu", "data", allow_duplicate=True),
                  Input("ld-luoi", "cellValueChanged"), prevent_initial_call=True)
    def _luu_o(doi):
        if not _duoc_xem():
            raise PreventUpdate
        doi = doi if isinstance(doi, list) else [doi] if doi else []
        ten_acc = {a["ten"]: a["acc_norm"] for a in leads.nguoi_online()}
        loi = []
        for d in doi:
            r, cot, moi = d.get("data") or {}, d.get("colId"), d.get("value")
            lead_id = r.get("id")
            if not lead_id or not cot:
                continue
            try:
                if cot == "sale_ten":
                    acc = ten_acc.get(moi)
                    if r.get("qua_han"):
                        leads.nhan_cheo(lead_id, acc, current_user.username)
                    else:
                        leads.cap_nhat_lead(lead_id, {"sale_tu_van": acc}, current_user.username)
                else:
                    leads.cap_nhat_lead(lead_id, {cot: moi}, current_user.username)
            except leads.LoiLead as e:
                loi.append(str(e))
        return (alert(" ".join(loi), "bad") if loi else None), gio_viet_nam().isoformat()

    # ------------------------------------------------ cấu hình (admin)
    @app.callback(Output("ld-g-page", "rowData"), Output("ld-fb-page", "options"), Output("ld-f-page", "options"),
                  Output("ld-loc-page", "options"), Output("ld-g-nn", "rowData"),
                  Input("ld-da-luu", "data"), Input("ld-pg-msg", "children"), Input("ld-nn-msg", "children"),
                  Input("ld-fb-msg", "children"))
    def _nap_cau_hinh(*_a):
        if not current_user.duoc_cau_hinh:
            raise PreventUpdate
        pages = leads.ds_page()
        opt = [{"label": t, "value": i} for i, t in zip(pages.id, pages.ten)] if len(pages) else []
        return (pages.to_dict("records") if len(pages) else [], opt, opt, opt, cb.ds_nguoi_nhan())

    @app.callback(Output("ld-pg-msg", "children", allow_duplicate=True), Output("ld-pg-ten", "value"),
                  Output("ld-pg-ghichu", "value"),
                  Input("ld-pg-them", "n_clicks"), State("ld-pg-ten", "value"), State("ld-pg-ghichu", "value"),
                  prevent_initial_call=True)
    def _them_page(_n, ten, ghi_chu):
        if not current_user.duoc_cau_hinh:
            raise PreventUpdate
        try:
            msg = leads.them_page(ten, ghi_chu, current_user.username)
        except leads.LoiLead as e:
            return alert(str(e), "bad"), no_update, no_update
        return alert(msg, "ok"), "", ""

    @app.callback(Output("ld-pg-msg", "children", allow_duplicate=True),
                  Input("ld-pg-luu", "n_clicks"), State("ld-g-page", "rowData"), prevent_initial_call=True)
    def _luu_page(_n, rows):
        if not current_user.duoc_cau_hinh:
            raise PreventUpdate
        n = 0
        for r in rows or []:
            try:
                leads.sua_page(r["id"], r.get("ten"), r.get("ghi_chu"), bool(r.get("active", True)),
                               current_user.username)
                n += 1
            except leads.LoiLead as e:
                return alert(str(e), "bad")
        return alert(f"Đã lưu {n} page.", "ok")

    @app.callback(Output("ld-nn-msg", "children", allow_duplicate=True), Output("ld-nn-ten", "value"),
                  Output("ld-nn-chatid", "value"),
                  Input("ld-nn-them", "n_clicks"), State("ld-nn-vt", "value"), State("ld-nn-ten", "value"),
                  State("ld-nn-chatid", "value"), State("ld-nn-acc", "value"), prevent_initial_call=True)
    def _them_nguoi_nhan(_n, vt, ten, chat_id, acc):
        if not current_user.duoc_cau_hinh:
            raise PreventUpdate
        ok, msg = cb.luu_nguoi_nhan(None, vt, ten, chat_id, acc, True, current_user.username)
        if not ok:
            return alert(msg, "bad"), no_update, no_update
        return alert(msg, "ok"), "", ""

    @app.callback(Output("ld-nn-msg", "children", allow_duplicate=True),
                  Input("ld-nn-xoa", "n_clicks"), State("ld-g-nn", "selectedRows"), prevent_initial_call=True)
    def _xoa_nguoi_nhan(_n, chon):
        if not current_user.duoc_cau_hinh:
            raise PreventUpdate
        if not chon:
            return alert("Chọn người nhận cần xoá.", "warn")
        n = cb.xoa_nguoi_nhan([r["id"] for r in chon], current_user.username)
        return alert(f"Đã xoá {n} người nhận.", "ok")

    @app.callback(Output("ld-fb-msg", "children", allow_duplicate=True), Input("ld-fb-luu", "n_clicks"),
                  State("ld-fb-page", "value"), State("ld-fb-id", "value"), State("ld-fb-token", "value"),
                  prevent_initial_call=True)
    def _luu_fb(_n, page_id, fb_id, token):
        if not current_user.duoc_cau_hinh:
            raise PreventUpdate
        if not page_id:
            return alert("Chọn page trước.", "warn")
        try:
            msg = leads.luu_fb_cau_hinh(page_id, fb_id, token, current_user.username)
        except leads.LoiLead as e:
            return alert(str(e), "bad")
        ghi_log("lead_fb_cau_hinh", f"page {page_id}")
        return alert(msg, "ok")

    @app.callback(Output("ld-fb-msg", "children", allow_duplicate=True), Input("ld-fb-dangky", "n_clicks"),
                  State("ld-fb-page", "value"), prevent_initial_call=True)
    def _dang_ky(_n, page_id):
        if not current_user.duoc_cau_hinh:
            raise PreventUpdate
        if not page_id:
            return alert("Chọn page trước.", "warn")
        from app.db import session_scope
        from app.models import CrmPage
        with session_scope() as s:
            p = s.get(CrmPage, int(page_id))
            fb_page_id, token = (p.fb_page_id, p.page_access_token) if p else (None, None)
        if not fb_page_id or not token:
            return alert("Page này chưa lưu Facebook Page ID / Page Access Token.", "warn")
        from app import leads_messenger as lm
        try:
            msg = lm.dang_ky_webhook(fb_page_id, token)
        except lm.LoiMessenger as e:
            return alert(str(e), "bad")
        ghi_log("lead_fb_dang_ky", f"page {page_id}")
        return alert(msg, "ok")
