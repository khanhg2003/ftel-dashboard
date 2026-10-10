"""Trang Soạn email (logic và khuôn mail: app/soan_mail.py; danh bạ: app/danh_ba.py). Dùng cho admin + nhân viên KD IBB7.

Ba bước trên một màn hình: (1) chọn loại và điền ô, (2) chọn người nhận (app chỉ GỢI Ý từ danh bạ, sale tự chọn),
(3) xem trước rồi bấm Copy. App không gửi mail và không lưu nội dung mail: dán vào Outlook rồi tự bấm Gửi.

Cả ba biểu mẫu dựng sẵn một lần và chỉ ẩn / hiện bằng CSS khi đổi loại (không hỏi máy chủ): đổi loại tức thì và ô đã gõ
của loại khác không mất. Vì vậy id mọi ô mang cả tên loại (`l`). Hộp Tra danh bạ lọc ngay trên trình duyệt (assets/danh_ba.js).
"""
from __future__ import annotations

import re

import pandas as pd
from dash import ALL, MATCH, ClientsideFunction, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate
from flask_login import current_user

from app import danh_ba as db
from app import soan_mail as sm
from app import tro_ly as ai
from app.auth import ghi_log
from app.ui.components import alert, field, modal, seg_control
from app.ui.icons import icon
from app.ui.pages.danhba import chon_chi_nhanh

F, FT = "sm-f", "sm-ft"                                   # kiểu id của ô một dòng / ô nhiều dòng (tình huống)
TU_NHAN = ""                                              # ô chi nhánh nơi lắp: để trống = tự nhận từ địa chỉ
VT = {"den": "Đến", "cc": "CC"}
NHAC_AI = "Đừng gõ tên khách, địa chỉ hay số điện thoại ở ô này: Fox chỉ nên thấy ý chính, các chi tiết đó điền ở ô riêng."
MAU_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def topbar():
    return [html.Div([html.H1("Soạn email"), html.Div("Điền ô, Fox viết giúp, copy dán vào Outlook", className="sub")])]


def _vao() -> None:
    if not (current_user.is_authenticated and current_user.duoc_soan_mail):
        raise PreventUpdate


def _cua_loai(loai: str, vals: list, ids: list) -> dict:
    """Giá trị các ô của MỘT loại từ danh sách ô của cả ba loại."""
    return {i["k"]: v for i, v in zip(ids, vals) if i["l"] == loai}


# ------------------------------------------------------------------ giao diện
def layout():
    db.dam_bao_bang()
    return html.Div([
        dcc.Store(id="sm-nguoi", data={"den": [], "cc": []}), dcc.Store(id="sm-goiy"), dcc.Store(id="sm-log"),
        dcc.Store(id="sm-du-lieu"), dcc.Store(id="sm-ve"), dcc.Store(id="sm-sk-chon"),
        seg_control("sm-loai", [(k, v["ten"]) for k, v in sm.LOAI.items()], "ca_hot"),
        html.Div([
            html.Div([
                html.H3("1 · Điền thông tin", style={"margin": "0 0 12px"}),
                html.Div([_o_form(loai) for loai in sm.LOAI], id="sm-form", className="sm-khung loai-ca_hot"),
                html.Div([
                    field("Chi nhánh nơi lắp", dcc.Dropdown(id="sm-dv", options=[{"label": "Tự nhận từ địa chỉ",
                                                                                  "value": TU_NHAN}],
                                                            value=TU_NHAN, clearable=False)),
                    field("Xưng hô", dcc.Dropdown(id="sm-xung", options=["anh", "chị"], value="anh", clearable=False,
                                                  searchable=False)),
                    field("Lời chào (tự theo người nhận)", dcc.Input(id="sm-chao", type="text", className="inp",
                                                                      debounce=True, placeholder="VD: anh Bình")),
                    field("Người gửi (ký tên cuối mail)", dcc.Input(id="sm-gui", type="text", className="inp",
                                                                    debounce=True, placeholder="VD: Rin",
                                                                    persistence=True, persistence_type="local")),
                ], className="form-grid sm-chung"),
            ], className="card sm-trai"),
            html.Div([
                html.Div([html.H3("2 · Người nhận", style={"margin": "0 0 4px"}),
                          html.Div("App chỉ gợi ý theo danh bạ. Bạn chọn ai là Đến, ai là CC.", className="desc"),
                          html.Div(id="sm-chips", className="sm-chips"),
                          html.Div(id="sm-goiy-khung", className="sm-goiy"),
                          html.Div([dcc.Input(id="sm-email-tay", type="text", className="inp", debounce=False,
                                              placeholder="Thêm email chưa có trong danh bạ (cách nhau dấu ;)"),
                                    html.Button("Đến", id="sm-tay-den", className="btn nho"),
                                    html.Button("CC", id="sm-tay-cc", className="btn nho"),
                                    html.Button([icon("search", 14), html.Span("Tra danh bạ")], id="sm-db-mo",
                                                className="btn nho")], className="sm-tay")], className="card"),
                html.Div([html.H3("3 · Xem trước", style={"margin": "0 0 8px"}),
                          html.Div(id="sm-xem"), html.Div(id="sm-hanh-dong", className="sm-hanh-dong")], className="card"),
            ], className="sm-phai"),
        ], className="sm-luoi"),
        _khung_tra_danh_ba(),
    ])


def _khung_tra_danh_ba():
    return modal("sm-db", "Tra danh bạ", [
        html.Div([dcc.Input(id="sm-db-tim", type="search", className="inp o-tim", autoComplete="off",
                             placeholder="Tên, chức danh, email, chi nhánh"),
                  chon_chi_nhanh("sm-db-dv")],
                 className="toolbar"),
        html.Div(id="sm-db-dem", className="desc db-dem"),
        html.Div(id="sm-db-kq", className="sm-db-kq"),
    ], nut_chinh="Xong")


def _o_form(loai: str) -> html.Div:
    L = sm.LOAI[loai]
    o = [html.Div([html.Label(t["nhan"] + (" *" if t["bat_buoc"] else "")),
                   dcc.Input(id={"type": F, "l": loai, "k": t["khoa"]}, type="text", className="inp", debounce=True,
                             placeholder=t["goi_y"], maxLength=300)], className="field rong") for t in L["truong"]]
    o.append(html.Div([
        html.Label(L["y_chinh"]),
        dcc.Textarea(id={"type": FT, "l": loai, "k": "tinh_huong"}, className="inp sm-ta", rows=4,
                     maxLength=sm.TOI_DA_DOAN, placeholder="VD: " + L["y_mau"]),
        html.Div([html.Button([icon("sparkle", 14), html.Span("Fox viết giúp")], id={"type": "sm-fox", "l": loai},
                              className="btn nho sm-fox", n_clicks=0),
                  html.Button("Hoàn tác", id={"type": "sm-hoan", "l": loai}, className="btn nho", n_clicks=0),
                  html.Span(NHAC_AI, className="desc")], className="sm-fox-dong"),
        dcc.Store(id={"type": "sm-y-goc", "l": loai}),
        html.Div(id={"type": "sm-fox-msg", "l": loai})], className="field rong"))
    return html.Div(o, id=f"sm-form-{loai}", className=f"sm-form f-{loai}")


def _chip(vt: str, i: int, p: dict) -> html.Span:
    return html.Span([html.Span(p["ten"], className="sm-ten"),
                      html.Span(p["chuc_vu"], className="sm-cv") if p["chuc_vu"] else None,
                      html.Button("×", id={"type": "sm-go", "vt": vt, "i": i}, className="sm-x", n_clicks=0,
                                  title="Bỏ người này")], className="sm-chip", title=p["email"])


def _dong_chip(vt: str, ds: list[dict]) -> html.Div:
    return html.Div([html.Span(VT[vt], className="sm-vt"),
                     *([_chip(vt, i, p) for i, p in enumerate(ds)] or [html.Span("Chưa chọn", className="desc")])],
                    className="sm-dong-chip")


def _goi_y_khung(g: dict) -> list:
    if not (g["den"] or g["cc"]):
        return [html.Div(f"Chưa có gợi ý cho {g['don_vi']}. Dùng Tra danh bạ hoặc gõ email.", className="desc")]
    ro = "" if g["khu_vuc_ro"] else " (chưa rõ khu vực: hiện cả các đội trưởng)"
    o = [html.Div([html.B("Gợi ý"), html.Span(f" · chi nhánh nơi lắp: {g['don_vi']}{ro}", className="desc")]),
         html.Button("Dùng hết gợi ý", id="sm-ap-het", className="btn nho", n_clicks=0)]
    for vt in ("den", "cc"):
        for i, p in enumerate(g[vt]):
            o.append(html.Div([html.Span(f"{p['ten']} · {p['chuc_vu']}".strip(" ·"), className="sm-gy-ten", title=p["email"]),
                               html.Button(VT[vt], id={"type": "sm-ap", "vt": vt, "i": i}, className="btn nho", n_clicks=0),
                               html.Button("CC" if vt == "den" else "Đến", id={"type": "sm-ap", "vt": vt, "i": -1 - i},
                                           className="btn nho", n_clicks=0)], className="sm-gy"))
    return o


def _xem(kq: dict) -> html.Div:
    def doan(d):
        out = []
        for chu, dam in d:
            for j, dong in enumerate(chu.split("\n")):
                if j:
                    out.append(html.Br())
                for c in re.split(r"(\[[^\]]+\])", dong):         # [Mã hợp đồng] còn trống: tô nổi để sale thấy
                    if c:
                        out.append(html.Span(c, className="sm-thieu") if re.fullmatch(r"\[[^\]]+\]", c)
                                   else (html.B(c) if dam else c))
        return html.P(out)
    return html.Div([html.Div([html.B("Tiêu đề: "), kq["tieu_de"]], className="sm-tieu-de"),
                     html.Div([doan(d) for d in kq["doan"]], id="sm-than", className="sm-than")])


def _hanh_dong(loai: str, kq: dict, nguoi: dict) -> list:
    emails = lambda vt: "; ".join(p["email"] for p in nguoi[vt])         # noqa: E731
    o = [html.Button([icon("copy", 14), html.Span("Copy cả mail")], id="sm-copy-ma", n_clicks=0,
                     className="btn primary nut-chep lon", **{"data-chep-nguon": "#sm-than", "data-chep-html": ""}),
         html.Button("Copy người nhận", className="btn nut-chep lon", **{"data-chep": emails("den")}),
         html.Button("Copy CC", className="btn nut-chep lon", **{"data-chep": emails("cc")}),
         html.Button("Copy tiêu đề", className="btn nut-chep lon", **{"data-chep": kq["tieu_de"]})]
    ghi = []
    if kq["thieu"]:
        ghi.append(alert("Còn trống: " + ", ".join(kq["thieu"]) + ".", "warn"))
    if not nguoi["den"]:
        ghi.append(html.Div("Chưa chọn người nhận (Đến).", className="desc"))
    if sm.LOAI[loai].get("nhac"):
        ghi.append(alert(sm.LOAI[loai]["nhac"], "info"))
    return [html.Div(o, className="sm-nut"), *ghi]


# ------------------------------------------------------------------ callbacks
def register(app):
    app.clientside_callback("function(l) { return 'sm-khung loai-' + l; }", Output("sm-form", "className"),
                            Input("sm-loai", "value"))
    app.clientside_callback(ClientsideFunction(namespace="ftel", function_name="nap_sm"),
                            Output("sm-ve", "data"), Input("sm-du-lieu", "data"))
    _dang_ky_goi_y(app)
    _dang_ky_nguoi(app)
    _dang_ky_xem(app)
    _dang_ky_fox(app)
    _dang_ky_tra_danh_ba(app)


def _dang_ky_goi_y(app):
    @app.callback(Output("sm-goiy", "data"), Output("sm-goiy-khung", "children"), Output("sm-dv", "options"),
                  Input("sm-loai", "value"), Input("sm-dv", "value"), Input({"type": F, "l": ALL, "k": "dia_chi"}, "value"),
                  State({"type": F, "l": ALL, "k": "dia_chi"}, "id"), State("sm-dv", "options"))
    def _goi_y(loai, dv, vals, ids, opts):
        _vao()
        if loai not in sm.LOAI:
            raise PreventUpdate
        g = sm.goi_y(loai, dv or None, _cua_loai(loai, vals, ids).get("dia_chi") or "")
        if len(opts or []) > 1:
            opts = no_update
        else:                                                 # danh sách chi nhánh nạp một lần, lần đầu vào trang
            opts = [{"label": "Tự nhận từ địa chỉ", "value": TU_NHAN},
                    *[{"label": f"{d} · {g['mien']}" if g["mien"] != "Chi nhánh của bạn" else d, "value": d}
                      for g in db.nhom_chi_nhanh() for d in g["ds"]]]
        return g, _goi_y_khung(g), opts


def _dang_ky_nguoi(app):
    @app.callback(Output("sm-nguoi", "data"), Output("sm-email-tay", "value"),
                  Input({"type": "sm-ap", "vt": ALL, "i": ALL}, "n_clicks"), Input("sm-ap-het", "n_clicks"),
                  Input({"type": "sm-go", "vt": ALL, "i": ALL}, "n_clicks"), Input("sm-sk-chon", "data"),
                  Input("sm-tay-den", "n_clicks"), Input("sm-tay-cc", "n_clicks"),
                  State("sm-nguoi", "data"), State("sm-goiy", "data"), State("sm-email-tay", "value"),
                  prevent_initial_call=True)
    def _nguoi(_ap, _het, _go, chon, _den, _cc, nguoi, goi_y, tay):
        _vao()
        t, gia_tri = ctx.triggered_id, ctx.triggered[0]["value"]
        if not gia_tri:
            raise PreventUpdate                              # nút vừa dựng lại, chưa ai bấm
        nguoi = {"den": list((nguoi or {}).get("den") or []), "cc": list((nguoi or {}).get("cc") or [])}
        moi = []                                             # [(vị trí, người)]
        if t == "sm-ap-het":
            moi = [(vt, p) for vt in ("den", "cc") for p in (goi_y or {}).get(vt, [])]
        elif isinstance(t, dict) and t["type"] == "sm-ap":
            i, ds = t["i"], (goi_y or {}).get(t["vt"], [])
            doi = i < 0                                      # nút thứ hai của dòng gợi ý: đổi sang vị trí còn lại
            moi = [(({"den": "cc", "cc": "den"})[t["vt"]] if doi else t["vt"], ds[-1 - i if doi else i])]
        elif isinstance(t, dict) and t["type"] == "sm-go":
            if t["i"] < len(nguoi[t["vt"]]):
                nguoi[t["vt"]].pop(t["i"])
        elif t == "sm-sk-chon" and (chon or {}).get("vt") in VT:
            r = db.tat_ca()
            r = r[r.id == chon.get("id")]
            moi = [(chon["vt"], sm.nguoi_dict(next(r.itertuples())))] if not r.empty else []
        elif t in ("sm-tay-den", "sm-tay-cc"):
            vt = "den" if t == "sm-tay-den" else "cc"
            moi = [(vt, {"id": 0, "ten": e.split("@")[0], "email": e, "chuc_vu": "", "don_vi": ""})
                   for e in MAU_EMAIL.findall(tay or "")]
        for vt, p in moi:
            if p["email"].lower() not in {x["email"].lower() for x in nguoi["den"] + nguoi["cc"]}:
                nguoi[vt].append(p)
        return nguoi, ("" if t in ("sm-tay-den", "sm-tay-cc") else no_update)

    @app.callback(Output("sm-chips", "children"), Input("sm-nguoi", "data"))
    def _chips(nguoi):
        _vao()
        return [_dong_chip(vt, (nguoi or {}).get(vt, [])) for vt in ("den", "cc")]


def _dang_ky_xem(app):
    @app.callback(Output("sm-xem", "children"), Output("sm-hanh-dong", "children"),
                  Input("sm-loai", "value"), Input({"type": F, "l": ALL, "k": ALL}, "value"),
                  Input({"type": FT, "l": ALL, "k": ALL}, "n_blur"), Input("sm-nguoi", "data"), Input("sm-xung", "value"),
                  Input("sm-gui", "value"), Input("sm-chao", "value"),
                  State({"type": F, "l": ALL, "k": ALL}, "id"), State({"type": FT, "l": ALL, "k": ALL}, "value"),
                  State({"type": FT, "l": ALL, "k": ALL}, "id"))
    def _xem_truoc(loai, vals, _blur, nguoi, xung, gui, chao, ids, vals_t, ids_t):
        _vao()
        if loai not in sm.LOAI:
            raise PreventUpdate
        nguoi = nguoi or {"den": [], "cc": []}
        v = {**_cua_loai(loai, vals, ids), **_cua_loai(loai, vals_t, ids_t), "xung": xung or "anh", "nguoi_gui": gui or "",
             "chao": (chao or "").strip() or sm.loi_chao(nguoi["den"], xung or "anh")}
        kq = sm.dung(loai, v)
        return _xem(kq), _hanh_dong(loai, kq, nguoi)

    @app.callback(Output("sm-log", "data"), Input("sm-copy-ma", "n_clicks"), State("sm-loai", "value"),
                  State({"type": F, "l": ALL, "k": ALL}, "value"), State({"type": F, "l": ALL, "k": ALL}, "id"),
                  prevent_initial_call=True)
    def _ghi_nhat_ky(n, loai, vals, ids):
        _vao()
        if not n:
            raise PreventUpdate
        ghi_log("soan_mail", f"{loai} {str(_cua_loai(loai, vals, ids).get('hop_dong') or '')[:30]}")   # không ghi nội dung mail
        return pd.Timestamp.now().isoformat()


def _dang_ky_fox(app):
    @app.callback(Output({"type": FT, "l": MATCH, "k": "tinh_huong"}, "value"),
                  Output({"type": "sm-fox-msg", "l": MATCH}, "children"),
                  Output({"type": "sm-y-goc", "l": MATCH}, "data"),
                  Input({"type": "sm-fox", "l": MATCH}, "n_clicks"),
                  State({"type": FT, "l": MATCH, "k": "tinh_huong"}, "value"),
                  State({"type": F, "l": MATCH, "k": ALL}, "value"), State({"type": F, "l": MATCH, "k": ALL}, "id"),
                  running=[(Output({"type": "sm-fox", "l": MATCH}, "disabled"), True, False)], prevent_initial_call=True)
    def _fox(n, y_chinh, vals, ids):
        _vao()
        if not n:
            raise PreventUpdate
        loai = ctx.triggered_id["l"]
        v = {i["k"]: x for i, x in zip(ids, vals)}
        try:
            doan = sm.viet_tinh_huong(loai, y_chinh, {"Hạn cần lắp": v.get("han_lap"),
                                                       "Thời gian khách có thể đợi": v.get("thoi_gian_cho")}, current_user)
        except ai.LoiAI as e:
            return no_update, alert(str(e), "bad"), no_update
        return doan, alert("Fox đã viết xong. Đọc lại và sửa nếu cần, rồi bấm Copy.", "ok"), y_chinh or ""

    @app.callback(Output({"type": FT, "l": MATCH, "k": "tinh_huong"}, "value", allow_duplicate=True),
                  Input({"type": "sm-hoan", "l": MATCH}, "n_clicks"), State({"type": "sm-y-goc", "l": MATCH}, "data"),
                  prevent_initial_call=True)
    def _hoan_tac(n, goc):
        _vao()
        if not n or goc is None:
            raise PreventUpdate
        return goc


def _dang_ky_tra_danh_ba(app):
    @app.callback(Output("sm-db", "className"), Output("sm-du-lieu", "data"),
                  Input("sm-db-mo", "n_clicks"), Input("sm-db-dong", "n_clicks"), Input("sm-db-huy", "n_clicks"),
                  Input("sm-db-ok", "n_clicks"), State("sm-du-lieu", "data"), prevent_initial_call=True)
    def _mo_db(mo, _d, _h, _ok, da_co):
        _vao()
        if ctx.triggered_id != "sm-db-mo":
            return "modal", no_update
        if not mo:
            raise PreventUpdate
        return "modal mo", (no_update if da_co else db.cho_trinh_duyet())        # tải danh bạ lần đầu mở hộp
