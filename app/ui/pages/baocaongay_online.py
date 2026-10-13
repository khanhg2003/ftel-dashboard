"""Mục "Theo dõi Online" nằm dưới bảng của trang Báo cáo ngày (quy tắc: app/online_ca.py; giao diện vẽ ở assets/online.js).

Máy chủ chỉ làm ba việc: nạp gói dữ liệu của ngày (`onl-du-lieu`), nhận sự kiện từ trình duyệt qua `onl-sk` (đổi trạng thái, dời
khung, dời mai, huỷ, thêm ca) và nhận form sửa ca. Phòng và ngày lấy từ chính bộ lọc của trang Báo cáo ngày
(`bn-phong`, `bn-ngay`); ai được xem / sửa thì theo đúng quyền của Báo cáo ngày (`bn._phong_hop_le`).
Liên kết một chiều với bảng phía trên (chủ app chốt 13/10/2026, phương án A): từ HÔM NAY trở về trước, ONL sáng / ONL chiều / Đã online của bảng tự đếm từ
các ca ở đây (`bc.che_do_onl`, `oc.dem_theo_nguoi`), nên mỗi lần ca đổi trang báo bảng vá lại dòng + dòng TỔNG; ngày chưa tới thì bảng gõ tay, mục này không ghi gì vào bảng.
"""
from __future__ import annotations

from datetime import date

from dash import ClientsideFunction, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate
from flask_login import current_user

from app import bao_cao_ngay as bc
from app import online_ca as oc
from app.auth import ghi_log
from app.thoi_gian import gio_viet_nam
from app.ui.components import alert, modal


def khung() -> list:
    """Thẻ Theo dõi Online + hộp sửa ca, đặt ngay dưới bảng Báo cáo ngày."""
    oc.dam_bao_bang()
    return [
        dcc.Store(id="onl-du-lieu"), dcc.Store(id="onl-sk"), dcc.Store(id="onl-lam-moi"), dcc.Store(id="onl-ve"),
        dcc.Store(id="onl-thong-bao"), dcc.Store(id="onl-bao-xong"), dcc.Store(id="onl-toi-la-xong"), dcc.Store(id="onl-hoi"), dcc.Store(id="onl-hoi-xong"),
        html.Div([
            html.Div(id="onl-hero"),
            html.Div(id="onl-msg"),
            html.Div(id="onl-hen"),
            html.Div(id="onl-doi"),
            html.Div(id="onl-xuly"),
            html.Div(id="onl-bang"),
        ], className="card onl", id="onl-goc"),
        modal("onl-tm", "Thêm ca phát sinh", [html.Div(id="onl-them")], nut_chinh="Thêm ca"),
        modal("onl-md", html.Span(id="onl-md-tieu-de"), [
            dcc.Store(id="onl-md-id"),
            html.Div([html.Label("Ghi chú"),
                      dcc.Textarea(id="onl-md-gc", className="inp", maxLength=oc.GHI_CHU_TOI_DA,
                                   placeholder="VD: khách chỉ rảnh sau 15h. Enter để lưu, Shift+Enter xuống dòng",
                                   style={"width": "100%", "minHeight": "56px"})], className="field rong"),
            html.Div(id="onl-md-ls", className="onl-md-ls"),
            html.Div(id="onl-md-msg"),
        ]),
    ]


def _bao_bang(d: date, truoc: set, phong: list[str], sk: dict | None = None) -> tuple:
    """Hai đầu ra `bn-da-luu` + `bn-nhip-va`: báo bảng phía trên nạp lại dòng của những người vừa có ca đổi (cả người cũ và người mới khi chuyển ca).
    Ngày chưa tới thì bảng gõ tay, không có gì phải báo."""
    if not bc.che_do_onl(d):
        return no_update, no_update
    accs = truoc | {c["acc"] for c in oc.ds_ca(phong, d)} | {(sk or {}).get("acc")}
    accs.discard(None)
    accs.discard("")
    if not accs:
        return no_update, no_update
    return {"luc": gio_viet_nam().isoformat(), "acc": sorted(accs), "xong": []}, False


def _ngu_canh(code, ngay, toi_la):
    """(phòng, ngày, tên người ghi) sau khi kiểm quyền ở máy chủ."""
    from app.ui.pages import baocaongay as bn
    phong, d = bn._phong_hop_le(code), bn._ngay_hop_le(ngay)
    ten = bn.nt_ten(toi_la) if bn._dung_chung() else None
    return phong, d, (ten or current_user.username)


def register(app):
    app.clientside_callback(ClientsideFunction(namespace="ftel", function_name="ve_online"),
                            Output("onl-ve", "data"), Input("onl-du-lieu", "data"))
    app.clientside_callback(ClientsideFunction(namespace="ftel", function_name="onl_bao"),
                            Output("onl-bao-xong", "data"), Input("onl-thong-bao", "data"), prevent_initial_call=True)
    app.clientside_callback(ClientsideFunction(namespace="ftel", function_name="onl_hoi"),
                            Output("onl-hoi-xong", "data"), Input("onl-hoi", "data"), prevent_initial_call=True)
    app.clientside_callback(ClientsideFunction(namespace="ftel", function_name="onl_toi_la"),
                            Output("onl-toi-la-xong", "data"), Input("bn-toi-la", "value"))

    @app.callback(Output("onl-du-lieu", "data"),
                  Input("bn-phong", "value"), Input("bn-ngay", "date"), Input("bn-nhip", "n_intervals"),
                  Input("onl-lam-moi", "data"), State("onl-du-lieu", "data"))
    def _nap(code, ngay, _nhip, _moi, cu):
        phong, d, _ = _ngu_canh(code, ngay, None)
        if ctx.triggered_id == "bn-nhip" and cu and cu.get("moc") == oc.moc(phong, d) and cu.get("ngay") == d.isoformat():
            raise PreventUpdate                                # nhịp tự động: chỉ nạp lại khi có người vừa sửa
        return oc.du_lieu(phong, d)

    @app.callback(Output("onl-lam-moi", "data"), Output("onl-msg", "children"), Output("onl-thong-bao", "data"),
                  Output("onl-hoi", "data"), Output("bn-da-luu", "data", allow_duplicate=True),
                  Output("bn-nhip-va", "disabled", allow_duplicate=True),
                  Input("onl-sk", "data"), State("bn-phong", "value"), State("bn-ngay", "date"), State("bn-toi-la", "value"),
                  prevent_initial_call=True)
    def _su_kien(sk, code, ngay, toi_la):
        if not sk or sk.get("act") in (None, "sua"):
            raise PreventUpdate
        phong, d, ai = _ngu_canh(code, ngay, toi_la)
        act, thong_bao, canh_bao, hoi = sk["act"], no_update, None, no_update
        truoc = {c["acc"] for c in oc.ds_ca(phong, d)} if bc.che_do_onl(d) else set()       # người có ca TRƯỚC khi đổi (ca xoá / dời đi không còn ở sau)
        try:
            if act == "them":
                kq = oc.them_nhieu(sk.get("text"), sk.get("acc"), sk.get("khung"), phong, ai, d, ghi_chu=sk.get("gc") or "", xac_nhan=bool(sk.get("xn")))
                if kq["them"]:
                    ghi_log("online_them", f"{', '.join(kq['them'])} {d:%d/%m/%Y} {code} khung {sk.get('khung')}")
                    ten = kq["them"][0] if len(kq["them"]) == 1 else f"{len(kq['them'])} ca"
                    thong_bao = {"msg": f"✓ Đã thêm {ten} vào {oc._nhan_khung(sk.get('khung'))}", "t": gio_viet_nam().isoformat()}
                if kq["hoi"]:                                   # Nhập tồn đang hẹn ngày khác: trình duyệt hỏi sale rồi gửi lại với xn=1
                    hoi = {"acc": sk.get("acc"), "khung": sk.get("khung"), "gc": sk.get("gc") or "", "ngay": d.isoformat(), "ds": kq["hoi"], "t": gio_viet_nam().isoformat()}
                if kq["bo_qua"]:
                    canh_bao = alert("Bỏ qua: " + "; ".join(f"{m} ({ly})" for m, ly in kq["bo_qua"]) + ".", "warn")
            elif act == "dong_bo_hen":
                n = oc.dong_bo_ngay_hen(sk["id"], phong, ai)
                thong_bao = {"msg": f"✓ Nhập tồn đã cập nhật ngày hẹn {d:%d/%m}" if n else "Nhập tồn đã khớp ngày hẹn", "t": gio_viet_nam().isoformat()}
            elif act == "tt":
                oc.doi_trang_thai(sk["id"], sk.get("val"), phong, ai)
            elif act == "khung":
                if sk.get("acc"):
                    oc.doi_nguoi(sk["id"], sk["acc"], phong, ai)
                    ghi_log("online_chuyen", f"{sk['id']} {d:%d/%m/%Y} {code} → {sk['acc']}")
                oc.doi_khung(sk["id"], sk.get("val"), phong, ai)
            elif act == "bulk":
                ids_hien = {c["id"] for c in oc.ds_ca(phong, d)}
                ids = [i for i in (sk.get("ids") or []) if i in ids_hien]
                kq = oc.doi_nhieu(ids, sk.get("loai"), sk.get("val") or "", phong, ai)
                if kq["loi"]:
                    return (gio_viet_nam().isoformat(), alert("; ".join(kq["loi"][:3]), "warn"), no_update, no_update, *_bao_bang(d, truoc, phong, sk))
            elif act == "mai":
                if sk.get("acc"):                              # đổi sale phụ trách TRƯỚC khi dời để phiếu mới ở ngày đích đã mang đúng người
                    oc.doi_nguoi(sk["id"], sk["acc"], phong, ai)
                    ghi_log("online_chuyen", f"{sk['id']} {d:%d/%m/%Y} {code} → {sk['acc']}")
                oc.doi_ngay(sk["id"], phong, ai, sk.get("ngay"), sk.get("khung") or None)
            elif act == "ve_ngay":                             # hoàn tác một lần dời ngày: đưa ca (đang ở ngày `tu`) về lại ngày cũ
                ve = date.fromisoformat(str(sk.get("ve"))[:10])
                mas = [m for m in (sk.get("mas") or [sk.get("ma")]) if m]
                xong, da_o, huy = [], [], []
                for m in mas:
                    # tìm nơi ca ĐANG Ở (có thể đã dời tiếp, hoặc đã về rồi do bấm hai lần) chứ không tin ngày trình duyệt gửi
                    ca = oc.ca_dang_o(phong, m, ve)
                    if ca is None:
                        huy.append(m)
                    elif ca["ngay"] == ve:
                        da_o.append(m)
                    else:
                        oc.doi_ngay(ca["id"], phong, ai, ve, sk.get("khung") or None)
                        if sk.get("acc"):                      # hoàn tác một lần dời kèm đổi người: trả luôn người cũ
                            oc.doi_nguoi(oc.ca_dang_o(phong, m, ve)["id"], sk["acc"], phong, ai)
                        xong.append(ca)
                if not xong and not da_o:
                    raise oc.LoiOnline("Không đưa về được: ca đã bị huỷ.")
                nhat = f"✓ Đã đưa {len(xong)} ca về lại {ve:%d/%m}" if xong else f"Ca đã ở ngày {ve:%d/%m} rồi"
                if huy:
                    canh_bao = alert(f"Bỏ qua {', '.join(huy)}: ca đã bị huỷ.", "warn")
                thong_bao = {"msg": nhat, "t": gio_viet_nam().isoformat()}
            elif act == "xoa":
                t = oc.xoa(sk["id"], phong, ai)
                ghi_log("online_xoa", f"{t['ma_hd']} {t['ngay']:%d/%m/%Y} {code}")
            else:
                raise PreventUpdate
        except oc.LoiOnline as e:                              # trình duyệt đã đổi tạm trên màn hình: nạp lại số thật + báo lỗi
            return gio_viet_nam().isoformat(), alert(str(e), "bad"), no_update, no_update, no_update, no_update
        return (gio_viet_nam().isoformat(), canh_bao, thong_bao, hoi, *_bao_bang(d, truoc, phong, sk))

    @app.callback(Output("onl-md", "className"), Output("onl-md-tieu-de", "children"), Output("onl-md-id", "data"),
                  Output("onl-md-gc", "value"), Output("onl-md-ls", "children"), Output("onl-md-msg", "children"),
                  Input("onl-sk", "data"), Input("onl-md-dong", "n_clicks"), Input("onl-md-huy", "n_clicks"),
                  State("bn-phong", "value"), State("bn-ngay", "date"), prevent_initial_call=True)
    def _mo_sua(sk, _d, _h, code, ngay):
        if ctx.triggered_id != "onl-sk":
            return "modal", no_update, no_update, no_update, no_update, ""
        if not sk or sk.get("act") != "sua":
            raise PreventUpdate
        phong, d, _ = _ngu_canh(code, ngay, None)
        c = next((x for x in oc.ds_ca(phong, d) if x["id"] == sk.get("id")), None)
        if c is None:
            raise PreventUpdate
        ls = [html.Div("Lịch sử", className="onl-md-nhan"),
              *[html.Div([html.Span(x["luc"][11:16], className="onl-md-gio"), f"{x['ai']}: {x['viec']}"]) for x in reversed(c["ls"])]] if len(c["ls"]) > 1 else []
        return "modal mo", f"Ca {c['ma']}", c["id"], c["gc"], ls, ""

    @app.callback(Output("onl-md", "className", allow_duplicate=True), Output("onl-md-msg", "children", allow_duplicate=True),
                  Output("onl-lam-moi", "data", allow_duplicate=True),
                  Input("onl-md-ok", "n_clicks"), State("onl-md-id", "data"), State("onl-md-gc", "value"),
                  State("bn-phong", "value"), State("bn-ngay", "date"), State("bn-toi-la", "value"), prevent_initial_call=True)
    def _luu_sua(n, id_, gc, code, ngay, toi_la):
        if not n or not id_:
            raise PreventUpdate
        phong, _, ai = _ngu_canh(code, ngay, toi_la)
        try:
            oc.sua_ghi_chu(id_, gc, phong, ai)
        except oc.LoiOnline as e:
            return no_update, alert(str(e), "bad"), no_update
        return "modal", "", gio_viet_nam().isoformat()
