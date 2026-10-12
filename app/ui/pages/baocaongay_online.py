"""Mục "Theo dõi Online" nằm dưới bảng của trang Báo cáo ngày (quy tắc: app/online_ca.py; giao diện vẽ ở assets/online.js).

Máy chủ chỉ làm ba việc: nạp gói dữ liệu của ngày (`onl-du-lieu`), nhận sự kiện từ trình duyệt qua `onl-sk` (đổi trạng thái, dời
khung, dời mai, huỷ) và nhận form thêm ca / sửa ca. Phòng và ngày lấy từ chính bộ lọc của trang Báo cáo ngày
(`bn-phong`, `bn-ngay`); ai được xem / sửa thì theo đúng quyền của Báo cáo ngày (`bn._phong_hop_le`). Mỗi lần ca đổi, số ONL sáng /
ONL chiều / Đã online trong bảng phía trên được tính lại từ phiếu (`online_ca.dong_bo_bang`) và dòng đó tự cập nhật.
"""
from __future__ import annotations

from dash import ClientsideFunction, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate
from flask_login import current_user

from app import online_ca as oc
from app.auth import ghi_log
from app.thoi_gian import gio_viet_nam
from app.ui.components import alert, modal
from app.ui.icons import icon


def khung() -> list:
    """Thẻ Theo dõi Online + hộp sửa ca, đặt ngay dưới bảng Báo cáo ngày."""
    oc.dam_bao_bang()
    khungs = oc.khung()
    return [
        dcc.Store(id="onl-du-lieu"), dcc.Store(id="onl-sk"), dcc.Store(id="onl-lam-moi"), dcc.Store(id="onl-ve"),
        dcc.Store(id="onl-thong-bao"), dcc.Store(id="onl-bao-xong"),
        html.Div([
            html.Div(id="onl-hero"),
            html.Div(id="onl-nguoi"),
            html.Div([
                dcc.Input(id="onl-f-hd", type="text", className="inp onl-f-hd", maxLength=24, autoComplete="off",
                          placeholder="Mã hợp đồng, VD: DAAAP6381"),
                html.Div(dcc.Dropdown(id="onl-f-nv", options=[], placeholder="Nhân viên phụ trách", clearable=False), className="onl-f-nv"),
                html.Div(dcc.Dropdown(id="onl-f-khung", options=[{"label": k["nhan"], "value": k["ma"]} for k in khungs],
                                      value=khungs[0]["ma"], clearable=False, searchable=False), className="onl-f-khung"),
                html.Button([icon("plus", 14), html.Span("Thêm ca")], id="onl-f-them", className="btn primary", n_clicks=0),
            ], className="onl-them-bar"),
            html.Div(id="onl-msg"),
            html.Div(id="onl-canh-bao"),
            html.Div(id="onl-bang"),
        ], className="card onl", id="onl-goc"),
        modal("onl-md", html.Span(id="onl-md-tieu-de"), [
            dcc.Store(id="onl-md-id"),
            html.Div([html.Label("Người phụ trách"),
                      dcc.Dropdown(id="onl-md-nv", options=[], clearable=False)], className="field rong"),
            html.Div([html.Label("Ghi chú"),
                      dcc.Textarea(id="onl-md-gc", className="inp", maxLength=oc.GHI_CHU_TOI_DA,
                                   placeholder="VD: khách chỉ rảnh sau 15h, đã gọi xác nhận",
                                   style={"width": "100%", "minHeight": "72px"})], className="field rong", style={"marginTop": "12px"}),
            html.Div(id="onl-md-ls", className="onl-md-ls"),
            html.Div(id="onl-md-msg"),
        ]),
    ]


def _ngu_canh(code, ngay, toi_la):
    """(phòng, ngày, tên người ghi) sau khi kiểm quyền ở máy chủ."""
    from app.ui.pages import baocaongay as bn
    phong, d = bn._phong_hop_le(code), bn._ngay_hop_le(ngay)
    ten = bn.nt_ten(toi_la) if bn._dung_chung() else None
    return phong, d, (ten or current_user.username)


def _sau_khi_ghi(accs):
    """Đầu ra chung sau mỗi lần ghi: nạp lại gói dữ liệu + báo bảng phía trên vá lại dòng của các nhân viên vừa đổi."""
    return (gio_viet_nam().isoformat(), {"luc": gio_viet_nam().isoformat(), "acc": sorted({a for a in accs if a})},
            not accs)


def register(app):
    app.clientside_callback(ClientsideFunction(namespace="ftel", function_name="ve_online"),
                            Output("onl-ve", "data"), Input("onl-du-lieu", "data"))
    app.clientside_callback(ClientsideFunction(namespace="ftel", function_name="onl_bao"),
                            Output("onl-bao-xong", "data"), Input("onl-thong-bao", "data"), prevent_initial_call=True)

    @app.callback(Output("onl-f-nv", "options"), Output("onl-md-nv", "options"), Input("bn-toi-la", "options"))
    def _chon_nv(opts):
        return opts or [], opts or []

    @app.callback(Output("onl-f-nv", "value"), Input("bn-toi-la", "value"), prevent_initial_call=True)
    def _nv_mac_dinh(toi_la):
        return toi_la if toi_la else no_update                 # tài khoản dùng chung: chọn "Tôi là" thì ô nhân viên tự điền theo

    @app.callback(Output("onl-du-lieu", "data"),
                  Input("bn-phong", "value"), Input("bn-ngay", "date"), Input("bn-nhip", "n_intervals"),
                  Input("onl-lam-moi", "data"), Input("bn-da-luu", "data"), State("onl-du-lieu", "data"))
    def _nap(code, ngay, _nhip, _moi, _luu, cu):
        phong, d, _ = _ngu_canh(code, ngay, None)
        if ctx.triggered_id == "bn-nhip" and cu and cu.get("moc") == oc.moc(phong, d) and cu.get("ngay") == d.isoformat():
            raise PreventUpdate                                # nhịp tự động: chỉ nạp lại khi có người vừa sửa
        return oc.du_lieu(phong, d)

    @app.callback(Output("onl-f-hd", "value"), Output("onl-msg", "children"), Output("onl-lam-moi", "data"),
                  Output("onl-thong-bao", "data"), Output("bn-da-luu", "data", allow_duplicate=True),
                  Output("bn-nhip-va", "disabled", allow_duplicate=True),
                  Input("onl-f-them", "n_clicks"), Input("onl-f-hd", "n_submit"),
                  State("onl-f-hd", "value"), State("onl-f-nv", "value"), State("onl-f-khung", "value"),
                  State("bn-phong", "value"), State("bn-ngay", "date"), State("bn-toi-la", "value"),
                  prevent_initial_call=True)
    def _them(n, sub, hd, nv, khung_ma, code, ngay, toi_la):
        if not (n or sub):
            raise PreventUpdate
        phong, d, ai = _ngu_canh(code, ngay, toi_la)
        try:
            oc.them(hd, nv, khung_ma, phong, ai, d)
        except oc.LoiOnline as e:
            return no_update, alert(str(e), "bad"), no_update, no_update, no_update, no_update
        ma = oc.chuan_ma(hd)
        ghi_log("online_them", f"{ma} {d:%d/%m/%Y} {code} khung {khung_ma}")
        moi, luu, tat = _sau_khi_ghi([nv])
        return "", None, moi, {"msg": f"✓ Đã thêm {ma} vào {oc._nhan_khung(khung_ma)}", "t": moi}, luu, tat

    @app.callback(Output("onl-lam-moi", "data", allow_duplicate=True), Output("onl-msg", "children", allow_duplicate=True),
                  Output("bn-da-luu", "data", allow_duplicate=True), Output("bn-nhip-va", "disabled", allow_duplicate=True),
                  Input("onl-sk", "data"), State("bn-phong", "value"), State("bn-ngay", "date"), State("bn-toi-la", "value"),
                  prevent_initial_call=True)
    def _su_kien(sk, code, ngay, toi_la):
        if not sk or sk.get("act") in (None, "sua"):
            raise PreventUpdate
        phong, d, ai = _ngu_canh(code, ngay, toi_la)
        acc = {c["id"]: c["acc"] for c in oc.ds_ca(phong, d)}.get(sk.get("id"))
        act, accs = sk["act"], [acc]
        try:
            if act == "tt":
                oc.doi_trang_thai(sk["id"], sk.get("val"), phong, ai)
            elif act == "khung":
                oc.doi_khung(sk["id"], sk.get("val"), phong, ai)
            elif act == "mai":
                oc.doi_ngay_mai(sk["id"], phong, ai)
            elif act == "xoa":
                t = oc.xoa(sk["id"], phong, ai)
                ghi_log("online_xoa", f"{t['ma_hd']} {t['ngay']:%d/%m/%Y} {code}")
            else:
                raise PreventUpdate
        except oc.LoiOnline as e:                              # trình duyệt đã đổi tạm trên màn hình: nạp lại số thật + báo lỗi
            moi, _, _ = _sau_khi_ghi([])
            return moi, alert(str(e), "bad"), no_update, no_update
        moi, luu, tat = _sau_khi_ghi(accs)
        return moi, None, (luu if accs else no_update), (tat if accs else no_update)

    @app.callback(Output("onl-md", "className"), Output("onl-md-tieu-de", "children"), Output("onl-md-id", "data"),
                  Output("onl-md-nv", "value"), Output("onl-md-gc", "value"), Output("onl-md-ls", "children"),
                  Output("onl-md-msg", "children"),
                  Input("onl-sk", "data"), Input("onl-md-dong", "n_clicks"), Input("onl-md-huy", "n_clicks"),
                  State("bn-phong", "value"), State("bn-ngay", "date"), prevent_initial_call=True)
    def _mo_sua(sk, _d, _h, code, ngay):
        if ctx.triggered_id != "onl-sk":
            return "modal", no_update, no_update, no_update, no_update, no_update, ""
        if not sk or sk.get("act") != "sua":
            raise PreventUpdate
        phong, d, _ = _ngu_canh(code, ngay, None)
        c = next((x for x in oc.ds_ca(phong, d) if x["id"] == sk.get("id")), None)
        if c is None:
            raise PreventUpdate
        ls = [html.Div("Lịch sử", className="onl-md-nhan"),
              *[html.Div([html.Span(x["luc"][11:16], className="onl-md-gio"), f"{x['ai']}: {x['viec']}"]) for x in reversed(c["ls"])]]
        return "modal mo", f"Ca {c['ma']}", c["id"], c["acc"], c["gc"], ls, ""

    @app.callback(Output("onl-md", "className", allow_duplicate=True), Output("onl-md-msg", "children", allow_duplicate=True),
                  Output("onl-lam-moi", "data", allow_duplicate=True), Output("bn-da-luu", "data", allow_duplicate=True),
                  Output("bn-nhip-va", "disabled", allow_duplicate=True),
                  Input("onl-md-ok", "n_clicks"), State("onl-md-id", "data"), State("onl-md-nv", "value"), State("onl-md-gc", "value"),
                  State("bn-phong", "value"), State("bn-ngay", "date"), State("bn-toi-la", "value"), prevent_initial_call=True)
    def _luu_sua(n, id_, nv, gc, code, ngay, toi_la):
        if not n or not id_:
            raise PreventUpdate
        phong, d, ai = _ngu_canh(code, ngay, toi_la)
        cu = {c["id"]: c["acc"] for c in oc.ds_ca(phong, d)}.get(id_)
        try:
            oc.sua(id_, nv, gc, phong, ai)
        except oc.LoiOnline as e:
            return no_update, alert(str(e), "bad"), no_update, no_update, no_update
        moi, luu, tat = _sau_khi_ghi([cu, nv])
        return "modal", "", moi, luu, tat
