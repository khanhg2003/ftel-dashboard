"""Phần "thêm người nhận bằng cách nhắn bot" của tab Bản tin Zalo: thẻ Kết nối Zalo (webhook) và thẻ người chờ duyệt.
Số liệu + quy tắc ở app/ban_tin_cho_duyet.py; id Dash tiền tố `btd-` để không đụng `bt-` của tab mẹ."""
from __future__ import annotations

import time

from dash import Input, Output, State, ctx, dcc, html, no_update

from app import ban_tin, ban_tin_cho_duyet as cd
from app.ui.components import alert, callback_can_quyen, card, field, ghi_chu, modal
from app.ui.icons import icon
from app.ui.luoi import bang
from app.ui.pages.quantri_ban_tin import CHON, hien_o_phong, o_phong

COT_CHO = [
    CHON,
    {"field": "ten", "headerName": "Tên hiển thị trên Zalo", "minWidth": 170, "flex": 1.4},
    {"field": "chat_id", "headerName": "chat_id", "minWidth": 170, "flex": 1.3},
    {"field": "nhan_cuoi", "headerName": "Nhắn lần cuối (giờ VN)", "minWidth": 160, "flex": 1},
]
HUONG_DAN_TRONG = "Nhờ người cần nhận bản tin mở Zalo, tìm Bot AI FTEL - DNG và nhắn một câu bất kỳ."
MUC = {"ok": "ok", "warn": "warn", "bad": "bad"}


def cac_the():
    return [
        dcc.Store(id="btd-lm-ds"),
        dcc.Store(id="btd-lm-tt"),
        dcc.ConfirmDialog(id="btd-xn-ngat", message=(
            "Ngắt kết nối webhook? Sau khi ngắt, người nhắn bot sẽ không tự hiện trong danh sách chờ duyệt nữa. "
            "Người đã là người nhận vẫn nhận bản tin bình thường.")),
        modal("btd-modal", "Thêm làm người nhận", [
            dcc.Store(id="btd-id"),
            html.Div([
                field("Tên *", dcc.Input(id="btd-f-ten", type="text", className="inp")),
                field("Loại *", dcc.Dropdown(id="btd-f-loai", clearable=False, searchable=False, value="bgd",
                                             options=[{"label": t, "value": v}
                                                      for v, t in ban_tin.LOAI_NHAN.items()])),
            ], className="form-grid"),
            o_phong("btd-f-phong"),
            html.Div(id="btd-modal-msg"),
        ], nut_chinh="Lưu"),
        card([
            html.Div(id="btd-tt"),
            html.Div([
                html.Div(className="grow"),
                html.Button([icon("trash", 14), html.Span("Ngắt kết nối")], id="btd-ngat", className="btn nguy-hiem"),
                html.Button([icon("plus", 14), html.Span("Kết nối webhook", id="btd-kn-chu")], id="btd-ket-noi",
                            className="btn primary"),
            ], className="toolbar"),
            html.Div(id="btd-msg-kn"),
            ghi_chu("Kết nối xong, ai nhắn bot sẽ tự hiện ở bảng “Người vừa nhắn bot” bên dưới, không phải lấy chat_id bằng tay. "
                    "Khi webhook đang bật, lệnh getUpdates cũ không chạy được nữa: Zalo chỉ cho dùng một trong hai. "
                    "Cần biến APP_URL (địa chỉ app) trên máy chủ.", nhan="Cách hoạt động"),
        ], title="Kết nối Zalo"),
        card([
            html.Div([
                html.Div(className="grow"),
                html.Button([icon("trash", 14), html.Span("Bỏ qua")], id="btd-bo", className="btn"),
                html.Button([icon("plus", 14), html.Span("Thêm làm người nhận")], id="btd-them",
                            className="btn primary"),
            ], className="toolbar"),
            html.Div(id="btd-msg"),
            bang("btd-grid", cao=240, cot=COT_CHO, getRowId="params.data.id + ''",
                 tuy_chon={"rowSelection": "multiple", "suppressRowClickSelection": True}),
            html.Div(id="btd-trong"),
        ], title="Người vừa nhắn bot (chờ duyệt)"),
    ]


def register(app):
    cb = callback_can_quyen(app, "duoc_cau_hinh")

    @cb(Output("btd-grid", "rowData"), Output("btd-trong", "children"),
        Input("qt-tab", "value"), Input("btd-lm-ds", "data"))
    def _nap_ds(tab, _):
        if tab != "bantin":
            return no_update, no_update
        ds = cd.ds_cho_duyet()
        return ds, ("" if ds else ghi_chu(HUONG_DAN_TRONG, nhan="Chưa có ai nhắn bot", style={"marginTop": "12px"}))

    @cb(Output("btd-tt", "children"), Input("qt-tab", "value"), Input("btd-lm-tt", "data"))
    def _nap_tt(tab, _):
        if tab != "bantin":
            return no_update
        muc, chu = cd.trang_thai_webhook()
        return alert(chu, MUC[muc])

    @cb(Output("btd-modal", "className"), Output("btd-id", "data"), Output("btd-f-ten", "value"),
        Output("btd-f-loai", "value"), Output("btd-modal-msg", "children", allow_duplicate=True),
        Output("btd-msg", "children", allow_duplicate=True), Output("btd-f-phong", "value"),
        Input("btd-them", "n_clicks"), Input("btd-modal-dong", "n_clicks"), Input("btd-modal-huy", "n_clicks"),
        Input("btd-lm-ds", "data"), State("btd-grid", "selectedRows"), prevent_initial_call=True)
    def _mo_hop(_them, _d, _h, _lm, chon):
        giu = (no_update,) * 6
        if ctx.triggered_id == "btd-them":
            if len(chon or []) != 1:
                return (no_update,) * 5 + (alert("Tích chọn đúng một người để thêm làm người nhận.", "warn"), no_update)
            r = chon[0]
            return "modal mo", r["id"], r.get("ten") or "", "bgd", "", "", []
        return ("modal",) + giu

    @cb(Output("btd-msg", "children"), Output("btd-modal-msg", "children"), Output("btd-lm-ds", "data"),
        Input("btd-modal-ok", "n_clicks"), Input("btd-bo", "n_clicks"),
        State("btd-id", "data"), State("btd-f-ten", "value"), State("btd-f-loai", "value"),
        State("btd-grid", "selectedRows"), State("btd-f-phong", "value"),
        running=[(Output("btd-modal-ok", "disabled"), True, False)], prevent_initial_call=True)
    def _thao_tac(_ok, _bo, id_, ten, loai, chon, phong):
        if ctx.triggered_id == "btd-modal-ok":
            if id_ is None:
                return no_update, no_update, no_update
            ok, msg = cd.duyet(id_, ten, loai, phong)
            return (alert(msg, "ok"), "", time.time()) if ok else (no_update, alert(msg, "bad"), no_update)
        ids = [int(r["id"]) for r in (chon or []) if str(r.get("id") or "").isdigit()]
        if not ids:
            return alert("Tích chọn người cần bỏ qua.", "warn"), no_update, no_update
        return alert(f"Đã bỏ qua {cd.bo_qua(ids)} người. Họ nhắn lại bot thì sẽ hiện lại.", "ok"), "", time.time()

    @cb(Output("btd-f-phong-ho", "style"), Input("btd-f-loai", "value"))
    def _hien_phong(loai):
        return hien_o_phong(loai)

    @cb(Output("btd-xn-ngat", "displayed"), Input("btd-ngat", "n_clicks"), prevent_initial_call=True)
    def _hoi_ngat(_n):
        return True

    @cb(Output("btd-msg-kn", "children"), Output("btd-lm-tt", "data"),
        Input("btd-ket-noi", "n_clicks"), Input("btd-xn-ngat", "submit_n_clicks"),
        running=[(Output("btd-ket-noi", "disabled"), True, False), (Output("btd-ngat", "disabled"), True, False),
                 (Output("btd-kn-chu", "children"), "Đang kết nối…", "Kết nối webhook")],
        prevent_initial_call=True)
    def _ket_noi(_kn, _ngat):
        muc, chu = cd.ket_noi() if ctx.triggered_id == "btd-ket-noi" else cd.ngat_ket_noi()
        return alert(chu, MUC[muc]), time.time()
