"""Tab "Bản tin Zalo" của trang Quản trị: người nhận, gửi thử, 10 lần gửi gần nhất (số liệu ở app/ban_tin.py)."""
from __future__ import annotations

from dash import Input, Output, State, ctx, dcc, html, no_update

from app import ban_tin, zalo_bot
from app.ui.components import (COT_SUA, alert, callback_can_quyen, card, dong_can_sua, field, ghi_chu, modal)
from app.ui.icons import icon
from app.ui.luoi import bang

AN = {"display": "none"}
CHON = {"field": "_chon", "headerName": "", "width": 44, "maxWidth": 44, "pinned": "left",
        "checkboxSelection": True, "headerCheckboxSelection": True, "sortable": False, "resizable": False}
COT_NGUOI = [
    CHON,
    {"field": "ten", "headerName": "Tên", "minWidth": 150, "flex": 1.3},
    {"field": "loai_nhan", "headerName": "Loại", "minWidth": 150, "flex": 1.1},
    {"field": "chat_id", "headerName": "chat_id", "minWidth": 170, "flex": 1.3},
    {"field": "bat_nhan", "headerName": "Trạng thái", "width": 110},
    COT_SUA,
]
COT_NHAT_KY = [
    {"field": "ngay_so", "headerName": "Ngày số", "width": 110},
    {"field": "ten_nguoi", "headerName": "Người nhận", "minWidth": 140, "flex": 1.2},
    {"field": "loai", "headerName": "Tin", "width": 120},
    {"field": "gio_gui", "headerName": "Giờ gửi", "width": 115},
    {"field": "ket_qua", "headerName": "Kết quả", "width": 100,
     "cellStyle": {"styleConditions": [
         {"condition": "params.value == 'Lỗi'", "style": {"color": "#B42318", "fontWeight": "650"}},
         {"condition": "params.value == 'Đã gửi'", "style": {"color": "#067647", "fontWeight": "650"}}]}},
    {"field": "ly_do", "headerName": "Lý do (nếu lỗi)", "minWidth": 220, "flex": 2, "tooltipField": "ly_do"},
]


def _hop_thoai():
    return modal("bt-modal", html.Span("Thêm người nhận", id="bt-tieu-de"), [
        dcc.Store(id="bt-dang-sua"),
        html.Div([
            field("Tên *", dcc.Input(id="bt-f-ten", type="text", className="inp", placeholder="vd: Anh Nam")),
            field("Loại *", dcc.Dropdown(id="bt-f-loai", clearable=False, searchable=False, value="bgd",
                                         options=[{"label": t, "value": v} for v, t in ban_tin.LOAI_NHAN.items()])),
            field("chat_id Zalo *", dcc.Input(id="bt-f-chat", type="text", className="inp")),
            field("Trạng thái", dcc.Dropdown(id="bt-f-bat", clearable=False, searchable=False, value="bat",
                                             options=[{"label": "Bật", "value": "bat"},
                                                      {"label": "Tắt", "value": "tat"}])),
        ], className="form-grid"),
        html.Div(id="bt-modal-msg"),
    ], nut_chinh="Lưu")


def pane(tab: str):
    return html.Div(id="bt-pane", style={} if tab == "bantin" else AN, children=[
        dcc.Store(id="bt-lam-moi"),
        dcc.ConfirmDialog(id="bt-xacnhan-xoa", message="Xoá các người nhận đã chọn?"),
        _hop_thoai(),
        card([
            html.Div(id="bt-tinh-trang"),
            html.Div([
                html.Div(className="grow"),
                html.Button([icon("trash", 14), html.Span("Xoá")], id="bt-xoa", className="btn nguy-hiem"),
                html.Button([icon("mail", 14), html.Span("Gửi thử", id="bt-thu-chu")], id="bt-thu", className="btn"),
                html.Button([icon("plus", 14), html.Span("Thêm người nhận")], id="bt-them",
                            className="btn primary"),
            ], className="toolbar"),
            html.Div(id="bt-msg"),
            bang("bt-grid", cao=300, cot=COT_NGUOI, getRowId="params.data.id + ''",
                 tuy_chon={"rowSelection": "multiple", "suppressRowClickSelection": True}),
            ghi_chu("Mỗi sáng sau khi số ngày hôm trước đã chốt, app gửi bản tin cho người nhận loại Ban Giám đốc. "
                    "Quá 10:30 mà chưa có số chốt thì nhắc người nhận loại Admin nạp file. Mỗi người chỉ nhận "
                    "một lần mỗi ngày số. “Gửi thử” gửi một tin ngắn cho người đang tích chọn để kiểm tra chat_id.",
                    nhan="Cách hoạt động", style={"marginTop": "12px"}),
        ], title="Người nhận bản tin Zalo"),
        card([bang("bt-nk", cao=None, cot=COT_NHAT_KY)], title="10 lần gửi gần nhất"),
    ])


def register(app):
    cb = callback_can_quyen(app, "duoc_cau_hinh")

    @cb(Output("bt-pane", "style"), Input("qt-tab", "value"), prevent_initial_call=True)
    def _hien_tab(tab):
        return {} if tab == "bantin" else AN

    @cb(Output("bt-grid", "rowData"), Output("bt-nk", "rowData"), Output("bt-tinh-trang", "children"),
        Input("qt-tab", "value"), Input("bt-lam-moi", "data"))
    def _nap(tab, _):
        if tab != "bantin":
            return no_update, no_update, no_update
        ok = zalo_bot.da_cau_hinh()
        tt = alert("Máy chủ đã cài token Zalo Bot." if ok else
                   "Máy chủ chưa cài biến ZALO_BOT_TOKEN nên chưa gửi được tin nào.", "ok" if ok else "warn")
        return ban_tin.ds_nguoi_nhan(), ban_tin.nhat_ky_gan_day(10), tt

    @cb(Output("bt-modal", "className"), Output("bt-tieu-de", "children"), Output("bt-dang-sua", "data"),
        Output("bt-f-ten", "value"), Output("bt-f-loai", "value"), Output("bt-f-chat", "value"),
        Output("bt-f-bat", "value"), Output("bt-modal-msg", "children", allow_duplicate=True),
        Input("bt-them", "n_clicks"), Input("bt-grid", "cellClicked"), Input("bt-grid", "cellDoubleClicked"),
        Input("bt-modal-dong", "n_clicks"), Input("bt-modal-huy", "n_clicks"), Input("bt-lam-moi", "data"),
        prevent_initial_call=True)
    def _mo_hop(_them, bam, bam_dup, *_):
        giu = (no_update,) * 7
        if ctx.triggered_id == "bt-them":
            return ("modal mo", "Thêm người nhận", None, "", "bgd", "", "bat", "")
        if ctx.triggered_id == "bt-grid":
            id_ = dong_can_sua(bam, bam_dup)
            r = ban_tin.lay_nguoi_nhan(int(id_)) if str(id_ or "").isdigit() else None
            if not r:
                return (no_update,) + giu
            return ("modal mo", f"Sửa người nhận: {r['ten']}", r["id"], r["ten"], r["loai"], r["chat_id"],
                    "bat" if r["bat"] else "tat", "")
        return ("modal",) + giu

    @cb(Output("bt-msg", "children"), Output("bt-modal-msg", "children"), Output("bt-lam-moi", "data"),
        Input("bt-modal-ok", "n_clicks"), Input("bt-xacnhan-xoa", "submit_n_clicks"), Input("bt-thu", "n_clicks"),
        State("bt-dang-sua", "data"), State("bt-f-ten", "value"), State("bt-f-loai", "value"),
        State("bt-f-chat", "value"), State("bt-f-bat", "value"), State("bt-grid", "selectedRows"),
        running=[(Output("bt-thu", "disabled"), True, False),
                 (Output("bt-thu-chu", "children"), "Đang gửi…", "Gửi thử")],
        prevent_initial_call=True)
    def _thao_tac(_ok, _xoa, _thu, id_sua, ten, loai, chat, bat, chon):
        import time
        trig = ctx.triggered_id
        ids = [int(r["id"]) for r in (chon or []) if str(r.get("id") or "").isdigit()]
        if trig == "bt-modal-ok":
            ok, msg = ban_tin.luu_nguoi_nhan(id_sua, ten, loai, chat, bat == "bat")
            return (alert(msg, "ok"), "", time.time()) if ok else (no_update, alert(msg, "bad"), no_update)
        if trig == "bt-xacnhan-xoa" and ids:
            return alert(f"Đã xoá {ban_tin.xoa_nguoi_nhan(ids)} người nhận.", "ok"), "", time.time()
        if trig == "bt-thu":
            if len(ids) != 1:
                return alert("Tích chọn đúng một người nhận để gửi thử.", "warn"), no_update, no_update
            ok, msg = ban_tin.gui_thu(ids[0])
            return alert(msg, "ok" if ok else "bad"), no_update, no_update
        return no_update, no_update, no_update

    @cb(Output("bt-xacnhan-xoa", "displayed"), Input("bt-xoa", "n_clicks"), State("bt-grid", "selectedRows"),
        prevent_initial_call=True)
    def _hoi_xoa(_n, chon):
        return bool(chon)
