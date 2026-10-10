"""Trang Soạn email (logic và khuôn mail: app/soan_mail.py; danh bạ: app/danh_ba.py). Dùng cho admin + nhân viên KD IBB7.

Ba bước trên một màn hình: (1) chọn loại và điền ô, (2) chọn người nhận (app chỉ GỢI Ý từ danh bạ, sale tự chọn),
(3) xem trước rồi bấm Copy. App không gửi mail và không lưu nội dung mail: dán vào Outlook rồi tự bấm Gửi.
"""
from __future__ import annotations

import re

import pandas as pd
from dash import ALL, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate
from flask_login import current_user

from app import danh_ba as db
from app import soan_mail as sm
from app import tro_ly as ai
from app.auth import ghi_log
from app.ui.components import alert, field, modal, seg_control
from app.ui.icons import icon
from app.ui.pages.danhba import the_nguoi

F, FT = "sm-f", "sm-ft"                                   # kiểu id của ô một dòng / ô nhiều dòng (tình huống)
TU_NHAN = ""                                              # ô chi nhánh nơi lắp: để trống = tự nhận từ địa chỉ
VT = {"den": "Đến", "cc": "CC"}
NHAC_AI = "Đừng gõ tên khách, địa chỉ hay số điện thoại ở ô này: Fox chỉ nên thấy ý chính, các chi tiết đó điền ở ô riêng."


def topbar():
    return [html.Div([html.H1("Soạn email"), html.Div("Điền ô, Fox viết giúp, copy dán vào Outlook", className="sub")])]


def _vao() -> None:
    if not (current_user.is_authenticated and current_user.duoc_soan_mail):
        raise PreventUpdate


def _gia_tri(ids: list, vals: list) -> dict:
    return {i["k"]: v for i, v in zip(ids, vals)}


# ------------------------------------------------------------------ giao diện
def layout():
    db.dam_bao_bang()
    ds_dv = db.ds_don_vi()
    return html.Div([
        dcc.Store(id="sm-nguoi", data={"den": [], "cc": []}), dcc.Store(id="sm-goiy"), dcc.Store(id="sm-y-goc"),
        dcc.Store(id="sm-log"),
        seg_control("sm-loai", [(k, v["ten"]) for k, v in sm.LOAI.items()], "ca_hot"),
        html.Div([
            html.Div([
                html.H3("1 · Điền thông tin", style={"margin": "0 0 12px"}),
                html.Div(id="sm-form", className="sm-form"),
                html.Div([
                    field("Chi nhánh nơi lắp", dcc.Dropdown(
                        id="sm-dv", options=[{"label": "Tự nhận từ địa chỉ", "value": TU_NHAN},
                                             *[{"label": d, "value": d} for d in ds_dv]],
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
        _khung_tra_danh_ba(ds_dv),
    ])


def _khung_tra_danh_ba(ds_dv: list[str]):
    return modal("sm-db", "Tra danh bạ", [
        html.Div([dcc.Input(id="sm-db-tim", type="search", debounce=0.35, className="inp o-tim",
                            placeholder="Tên, chức danh, email, chi nhánh"),
                  dcc.Dropdown(id="sm-db-dv", options=[{"label": "Mọi chi nhánh", "value": ""},
                                                       *[{"label": d, "value": d} for d in ds_dv]],
                               value="", clearable=False, style={"width": "180px"})], className="toolbar"),
        html.Div(id="sm-db-kq", className="sm-db-kq"),
    ], nut_chinh="Xong")


def _o_form(loai: str) -> list:
    L = sm.LOAI[loai]
    o = [html.Div([html.Label(t["nhan"] + (" *" if t["bat_buoc"] else "")),
                   dcc.Input(id={"type": F, "k": t["khoa"]}, type="text", className="inp", debounce=True,
                             placeholder=t["goi_y"], maxLength=300)], className="field rong") for t in L["truong"]]
    o.append(html.Div([
        html.Label(L["y_chinh"]),
        dcc.Textarea(id={"type": FT, "k": "tinh_huong"}, className="inp sm-ta", rows=4, maxLength=sm.TOI_DA_DOAN,
                     placeholder="VD: " + L["y_mau"]),
        html.Div([html.Button([icon("sparkle", 14), html.Span("Fox viết giúp")], id="sm-fox", className="btn nho sm-fox"),
                  html.Button("Hoàn tác", id="sm-hoan", className="btn nho"),
                  html.Span(NHAC_AI, className="desc")], className="sm-fox-dong"),
        html.Div(id="sm-fox-msg")], className="field rong"))
    return o


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
    _dang_ky_form(app)
    _dang_ky_nguoi(app)
    _dang_ky_xem(app)
    _dang_ky_fox(app)
    _dang_ky_tra_danh_ba(app)


def _dang_ky_form(app):
    @app.callback(Output("sm-form", "children"), Output("sm-y-goc", "data"), Input("sm-loai", "value"))
    def _form(loai):
        _vao()
        if loai not in sm.LOAI:
            raise PreventUpdate
        return _o_form(loai), None

    @app.callback(Output("sm-goiy", "data"), Output("sm-goiy-khung", "children"),
                  Input("sm-loai", "value"), Input("sm-dv", "value"), Input({"type": F, "k": ALL}, "value"),
                  State({"type": F, "k": ALL}, "id"))
    def _goi_y(loai, dv, vals, ids):
        _vao()
        if loai not in sm.LOAI:
            raise PreventUpdate
        g = sm.goi_y(loai, dv or None, _gia_tri(ids, vals).get("dia_chi") or "")
        return g, _goi_y_khung(g)


def _dang_ky_nguoi(app):
    @app.callback(Output("sm-nguoi", "data"), Output("sm-email-tay", "value"),
                  Input({"type": "sm-ap", "vt": ALL, "i": ALL}, "n_clicks"), Input("sm-ap-het", "n_clicks"),
                  Input({"type": "sm-go", "vt": ALL, "i": ALL}, "n_clicks"),
                  Input({"type": "sm-chon", "vt": ALL, "id": ALL}, "n_clicks"),
                  Input("sm-tay-den", "n_clicks"), Input("sm-tay-cc", "n_clicks"),
                  State("sm-nguoi", "data"), State("sm-goiy", "data"), State("sm-email-tay", "value"),
                  prevent_initial_call=True)
    def _nguoi(_ap, _het, _go, _chon, _den, _cc, nguoi, goi_y, tay):
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
            p = ds[-1 - i if doi else i]
            moi = [(({"den": "cc", "cc": "den"})[t["vt"]] if doi else t["vt"], p)]
        elif isinstance(t, dict) and t["type"] == "sm-go":
            if t["i"] < len(nguoi[t["vt"]]):
                nguoi[t["vt"]].pop(t["i"])
        elif isinstance(t, dict) and t["type"] == "sm-chon":
            r = db.tat_ca()
            r = r[r.id == t["id"]]
            moi = [(t["vt"], sm.nguoi_dict(next(r.itertuples())))] if not r.empty else []
        elif t in ("sm-tay-den", "sm-tay-cc"):
            vt = "den" if t == "sm-tay-den" else "cc"
            moi = [(vt, {"id": 0, "ten": e.split("@")[0], "email": e, "chuc_vu": "", "don_vi": ""})
                   for e in re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", tay or "")]
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
                  Input("sm-loai", "value"), Input({"type": F, "k": ALL}, "value"),
                  Input({"type": FT, "k": ALL}, "n_blur"), Input("sm-nguoi", "data"), Input("sm-xung", "value"),
                  Input("sm-gui", "value"), Input("sm-chao", "value"),
                  State({"type": F, "k": ALL}, "id"), State({"type": FT, "k": ALL}, "value"),
                  State({"type": FT, "k": ALL}, "id"))
    def _xem_truoc(loai, vals, _blur, nguoi, xung, gui, chao, ids, vals_t, ids_t):
        _vao()
        if loai not in sm.LOAI:
            raise PreventUpdate
        nguoi = nguoi or {"den": [], "cc": []}
        v = {**_gia_tri(ids, vals), **_gia_tri(ids_t, vals_t), "xung": xung or "anh", "nguoi_gui": gui or "",
             "chao": (chao or "").strip() or sm.loi_chao(nguoi["den"], xung or "anh")}
        kq = sm.dung(loai, v)
        return _xem(kq), _hanh_dong(loai, kq, nguoi)

    @app.callback(Output("sm-log", "data"), Input("sm-copy-ma", "n_clicks"), State("sm-loai", "value"),
                  State({"type": F, "k": ALL}, "value"), State({"type": F, "k": ALL}, "id"), prevent_initial_call=True)
    def _ghi_nhat_ky(n, loai, vals, ids):
        _vao()
        if not n:
            raise PreventUpdate
        ghi_log("soan_mail", f"{loai} {str(_gia_tri(ids, vals).get('hop_dong') or '')[:30]}")     # không ghi nội dung mail
        return pd.Timestamp.now().isoformat()


def _dang_ky_fox(app):
    @app.callback(Output({"type": FT, "k": "tinh_huong"}, "value"), Output("sm-fox-msg", "children"),
                  Output("sm-y-goc", "data", allow_duplicate=True),
                  Input("sm-fox", "n_clicks"), State("sm-loai", "value"), State({"type": FT, "k": "tinh_huong"}, "value"),
                  State({"type": F, "k": ALL}, "value"), State({"type": F, "k": ALL}, "id"),
                  running=[(Output("sm-fox", "disabled"), True, False)], prevent_initial_call=True)
    def _fox(n, loai, y_chinh, vals, ids):
        _vao()
        if not n:
            raise PreventUpdate
        v = _gia_tri(ids, vals)
        try:
            doan = sm.viet_tinh_huong(loai, y_chinh, {"Hạn cần lắp": v.get("han_lap"),
                                                       "Thời gian khách có thể đợi": v.get("thoi_gian_cho")}, current_user)
        except ai.LoiAI as e:
            return no_update, alert(str(e), "bad"), no_update
        return doan, alert("Fox đã viết xong. Đọc lại và sửa nếu cần, rồi bấm Copy.", "ok"), y_chinh or ""

    @app.callback(Output({"type": FT, "k": "tinh_huong"}, "value", allow_duplicate=True),
                  Input("sm-hoan", "n_clicks"), State("sm-y-goc", "data"), prevent_initial_call=True)
    def _hoan_tac(n, goc):
        _vao()
        if not n or goc is None:
            raise PreventUpdate
        return goc


def _dang_ky_tra_danh_ba(app):
    @app.callback(Output("sm-db", "className"),
                  Input("sm-db-mo", "n_clicks"), Input("sm-db-dong", "n_clicks"), Input("sm-db-huy", "n_clicks"),
                  Input("sm-db-ok", "n_clicks"), prevent_initial_call=True)
    def _mo_db(mo, *_):
        _vao()
        if ctx.triggered_id != "sm-db-mo":
            return "modal"
        if not mo:
            raise PreventUpdate
        return "modal mo"

    @app.callback(Output("sm-db-kq", "children"), Input("sm-db-tim", "value"), Input("sm-db-dv", "value"),
                  Input("sm-db", "className"))
    def _tra(q, dv, lop):
        _vao()
        if "mo" not in (lop or "").split():
            raise PreventUpdate
        ds, tong = db.tim(q or "", dv or None, None, 30)
        if ds.empty:
            return [html.Div("Không có ai khớp.", className="desc")]
        o = [html.Div(f"{len(ds)} / {tong} người", className="desc")]
        for r in ds.itertuples():
            nut = ([html.Button(VT[vt], id={"type": "sm-chon", "vt": vt, "id": int(r.id)}, className="btn nho", n_clicks=0)
                    for vt in ("den", "cc")] if isinstance(r.email, str) and r.email else
                   [html.Span("Chưa có email", className="desc")])
            o.append(the_nguoi(r, nut))
        return o
