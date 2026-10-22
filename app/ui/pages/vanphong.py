"""Trang Văn phòng AI (chỉ Quản trị / CEO): các nhân viên AI của dự án đang làm gì, việc vừa xong, lệnh gần đây và hàng đợi việc.
Logic và nơi lưu dữ liệu: app/van_phong.py. Trang tự làm mới vài giây một lần khi chạy trên máy (có nhật ký hook); trên Vercel không có nhật ký nên
chỉ hiện danh sách nhân viên và tắt nhịp để không tốn CPU.
"""
from __future__ import annotations

from dash import ALL, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

from app import van_phong as vp
from app.config import LA_SERVERLESS
from app.ui.components import alert, callback_can_quyen, card
from app.ui.icons import icon

NHIP_MS = 5000
GAN_DAY = 15 * 60


def topbar():
    return [html.Div([html.H1("Văn phòng AI"), html.Div("Các nhân viên AI của dự án đang làm gì", className="sub")])]


def layout():
    return html.Div([
        html.Div(id="vp-tom-tat", className="vp-tom-tat"),
        html.Div(id="vp-ban", className="vp-ban"),
        html.Div([card(html.Div(id="vp-xong"), title="Việc vừa xong", desc="Báo cáo cuối cùng của từng nhân viên sau mỗi lần được giao việc."),
                  card(html.Div(id="vp-lenh"), title="Lệnh gần đây của CEO", desc="Những gì CEO đã nhắn cho trợ lý điều phối (đã che mật khẩu / token).")],
                 className="vp-hai-cot"),
        card([html.Div([dcc.Input(id="vp-viec-moi", type="text", className="inp", maxLength=vp.TOI_DA_CHU, debounce=False,
                                  placeholder="Việc cần làm, ví dụ: Thêm cột tỷ lệ vào bảng Tra cứu giá", autoComplete="off"),
                        html.Button([icon("plus", 14), html.Span("Thêm việc")], id="vp-them", className="btn primary", n_clicks=0)], className="vp-them"),
              html.Div(id="vp-hang-doi")],
             title="Hàng đợi việc của CEO",
             desc="Việc thêm ở đây sẽ được báo cho trợ lý điều phối ở đầu mỗi phiên làm việc. Bấm nhãn trạng thái để đổi Chờ, Đang làm, Xong."),
        dcc.Interval(id="vp-nhip", interval=NHIP_MS, disabled=LA_SERVERLESS),
    ], className="vp")


# ------------------------------------------------------------------ dựng giao diện
def _ban(nv: dict, t: dict):
    lam = t["dang_lam"]
    dong = [html.Span("Đang làm" if lam else "Rảnh", className="vp-tt vp-tt-lam" if lam else "vp-tt"),
            html.Span(nv["model"], className="vp-chip", title="Model AI nhân viên này dùng")]
    chi_tiet = []
    if lam:
        chi_tiet.append(html.Div(t["viec"] or "Đang xử lý…", className="vp-viec"))
        if t["cong_cu"]:
            chi_tiet.append(html.Div([html.Span("Vừa dùng: ", className="vp-nhan"), t["cong_cu"]], className="vp-cong-cu"))
    elif t["gan_nhat"]:
        chi_tiet.append(html.Div([html.Span(f"Xong lúc {vp.gio(t['luc_xong'])}: ", className="vp-nhan"), t["gan_nhat"]], className="vp-xong-gn"))
    else:
        chi_tiet.append(html.Div("Chưa có việc nào được ghi nhận.", className="vp-trong"))
    return html.Div([
        html.Div([html.Div("".join(w[0] for w in nv["ten"].split()[:2]).upper(), className="vp-avatar" + (" vp-avatar-lam" if lam else "")),
                  html.Div([html.Div(nv["ten"], className="vp-ten"), html.Div(nv["vai_tro"], className="vp-vai-tro")])], className="vp-ban-dau"),
        html.Div(dong, className="vp-ban-dong"), *chi_tiet,
        html.Div(f"Hôm nay xong {t['hom_nay']} việc", className="vp-hom-nay") if nv["id"] != "main" else None,
    ], className="vp-the" + (" vp-the-lam" if lam else ""), title=nv["mo_ta"])


def _tom_tat(nv_ds: list[dict], tt: dict, co_nhat_ky: bool):
    dang = sum(t["dang_lam"] for t in tt.values())
    xong = sum(t["hom_nay"] for t in tt.values())
    chip = [html.Span(f"{len(nv_ds) - 1} nhân viên + 1 điều phối", className="vp-chip-to"), html.Span(f"Đang làm: {dang}", className="vp-chip-to"),
            html.Span(f"Hôm nay xong: {xong} việc", className="vp-chip-to")]
    if not co_nhat_ky:
        return html.Div([html.Div(chip, className="vp-chips"),
                         alert("Chưa có hoạt động nào được ghi. Nhật ký chỉ ghi khi Claude Code chạy ở chính máy này (hook trong .claude/settings.json), "
                               "nên trên bản chạy thật (Vercel) trang chỉ hiện danh sách nhân viên.", "info")])
    return html.Div(chip, className="vp-chips")


def _xong(ds: list[dict]):
    if not ds:
        return html.Div("Chưa có việc nào xong.", className="vp-trong")
    return html.Div([html.Div([html.Div([html.B(e.get("agent") or "?"), html.Span(vp.gio(e.get("ts"), "%d/%m %H:%M"), className="vp-gio")], className="vp-dong-dau"),
                               html.Div(e["ket_qua"], className="vp-ket-qua")], className="vp-dong") for e in ds])


def _lenh(ds: list[dict]):
    if not ds:
        return html.Div("Chưa có lệnh nào được ghi.", className="vp-trong")
    return html.Div([html.Div([html.Span(vp.gio(e.get("ts"), "%d/%m %H:%M"), className="vp-gio"), html.Span(e["lenh"], className="vp-lenh")], className="vp-dong")
                     for e in ds])


def _hang_doi(ds: list[dict]):
    if not ds:
        return html.Div("Chưa có việc nào trong hàng đợi.", className="vp-trong")
    return html.Div([html.Div([
        html.Button(vp.NHAN_VIEC.get(v.get("trang_thai"), "Chờ"), id={"type": "vp-doi-tt", "id": v["id"]}, n_clicks=0, title="Bấm để đổi trạng thái",
                    className=f"vp-nhan-viec vp-nv-{v.get('trang_thai', 'cho')}"),
        html.Span(v.get("noi_dung") or "", className="vp-noi-dung" + (" vp-da-xong" if v.get("trang_thai") == "xong" else "")),
        html.Button("×", id={"type": "vp-xoa", "id": v["id"]}, n_clicks=0, className="vp-xoa", title="Xoá việc này")], className="vp-viec-dong") for v in ds])


# ------------------------------------------------------------------ callbacks
def register(app):
    def quyen():
        return callback_can_quyen(app, "duoc_cau_hinh")

    @quyen()(Output("vp-tom-tat", "children"), Output("vp-ban", "children"), Output("vp-xong", "children"), Output("vp-lenh", "children"),
             Input("vp-nhip", "n_intervals"))
    def _ve(_n):
        nv = vp.doc_nhan_vien()
        sk = vp.doc_su_kien()
        tt = vp.trang_thai(nv, sk)
        co = list(nv) + [{"id": i, "ten": i.replace("-", " ").title(), "vai_tro": "Agent khác", "mo_ta": "", "model": "?", "cong_cu": []}
                         for i in tt if i not in {x["id"] for x in nv}]
        return (_tom_tat(nv, tt, bool(sk)), [_ban(x, tt[x["id"]]) for x in co], _xong(vp.viec_vua_xong(sk)), _lenh(vp.lenh_ceo(sk)))

    @quyen()(Output("vp-hang-doi", "children"), Output("vp-viec-moi", "value"),
             Input("vp-them", "n_clicks"), Input({"type": "vp-doi-tt", "id": ALL}, "n_clicks"), Input({"type": "vp-xoa", "id": ALL}, "n_clicks"),
             State("vp-viec-moi", "value"))
    def _viec(_them, _doi, _xoa, noi_dung):
        bam = ctx.triggered_id
        if bam is not None and ctx.triggered and not ctx.triggered[0].get("value"):
            raise PreventUpdate                                       # nút vừa được dựng lại (n_clicks = 0), không phải người dùng bấm
        o_trong = no_update
        if bam == "vp-them":
            if vp.them_viec(noi_dung or ""):
                o_trong = ""
        elif isinstance(bam, dict) and bam.get("type") == "vp-doi-tt":
            vp.doi_trang_thai(bam["id"])
        elif isinstance(bam, dict) and bam.get("type") == "vp-xoa":
            vp.xoa_viec(bam["id"])
        return _hang_doi(vp.doc_hang_doi()), o_trong
