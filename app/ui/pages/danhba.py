"""Trang Danh bạ - tra cứu người liên hệ nội bộ (logic: app/danh_ba.py). Dùng được cho admin + nhân viên KD IBB7.

Một ô tìm (tên, chức danh, email, chi nhánh, số điện thoại; bỏ dấu), lọc theo chi nhánh và nhóm chức danh, kết quả là
thẻ có nút copy email / số. Người không có trong file thì sale tự thêm; file PNC / TIN do Quản trị nạp lại hằng tháng.
`the_nguoi` được Soạn email dùng lại ở hộp tra danh bạ.
"""
from __future__ import annotations

import base64

import pandas as pd
from dash import ALL, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate
from flask_login import current_user

from app import danh_ba as db
from app.ui.components import alert, field, modal, seg_control
from app.ui.icons import icon
from app.thoi_gian import chu_gio_vn

TAT_CA_DV = ""
NHOM_NUT = [("all", "Tất cả"), ("giam_doc", "Giám đốc"), ("pho_giam_doc", "Phó GĐ"), ("truong_phong_kt", "TP kỹ thuật"),
            ("ha_tang", "Hạ tầng"), ("doi_truong", "Đội trưởng"), ("ke_toan", "Kế toán"), ("khac", "Khác")]
CHU_GIAI = ("Dữ liệu lấy từ file danh bạ PNC (Đà Nẵng vào Nam) và TIN (Đà Nẵng ra Bắc). "
            "Người không có trong file thì bấm Thêm người. Hai file lệch email thì thẻ hiện cả hai.")


def topbar():
    return [html.Div([html.H1("Danh bạ"), html.Div("Tra cứu người liên hệ: tên, chức danh, email, số điện thoại",
                                                   className="sub")])]


def _vao() -> None:
    """Mọi callback kiểm lại quyền ở máy chủ (ẩn menu là chưa đủ)."""
    if not (current_user.is_authenticated and current_user.duoc_soan_mail):
        raise PreventUpdate


def _chu(v) -> str:
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)


def nut_chep(noi_dung: str, nhan: str = "Copy", **kw) -> html.Button:
    """Nút copy một đoạn chữ; `assets/sao_chep.js` làm phần còn lại (có chữ "Đã copy" thoáng qua)."""
    return html.Button(icon("copy", 13), className="nut-chep", title=nhan, **{"data-chep": noi_dung}, **kw)


def _vien_tu(ten: str) -> str:
    t = _chu(ten).split()
    return (t[-2][0] + t[-1][0] if len(t) >= 2 else ten[:2]).upper()


def the_nguoi(r, hanh_dong: list | None = None) -> html.Div:
    """Một người = một thẻ. `hanh_dong`: nút thêm ở chân thẻ (Soạn email dùng cho Đến / CC)."""
    email, khac, sdt, ext, ghi = (_chu(r.email), _chu(r.email_khac), _chu(r.di_dong), _chu(r.ext), _chu(r.ghi_chu))
    dong = []
    if email:
        dong.append(html.Div([icon("mail", 14), html.Span(email, className="db-gia-tri"), nut_chep(email, "Copy email")],
                             className="db-dong"))
    if khac:
        dong.append(html.Div([html.Span("Email khác", className="db-nhan"), html.Span(khac, className="db-gia-tri"),
                              nut_chep(khac, "Copy email khác")], className="db-dong phu"))
    if sdt or ext:
        dong.append(html.Div([icon("phone", 14),
                              (html.A(sdt, href="tel:" + "".join(c for c in sdt if c.isdigit()), className="db-gia-tri")
                               if sdt else None),
                              html.Span(f"máy lẻ {ext}" if ext else "", className="db-nhan"),
                              nut_chep("".join(c for c in sdt if c.isdigit()), "Copy số") if sdt else None],
                             className="db-dong"))
    nguon = r.nguon_ds.replace("TAY", "Thêm tay")
    ngay = chu_gio_vn(r.cap_nhat_luc, "%d/%m") if pd.notna(r.cap_nhat_luc) else ""
    chan = [html.Span(f"{nguon} · {ngay}" if ngay else nguon, className="db-nguon", title="Nguồn dữ liệu và ngày cập nhật")]
    if pd.notna(r.id_tay):
        chan.append(html.Button("Sửa", id={"type": "db-sua", "id": int(r.id_tay)}, className="btn nho", n_clicks=0))
    return html.Div([
        html.Div([html.Div(_vien_tu(r.ho_ten), className="db-vien"),
                  html.Div([html.Div([html.B(r.ho_ten), html.Span(db.NHOM[r.nhom], className=f"db-nhom-n {r.nhom}")],
                                     className="db-ten"),
                            html.Div(" · ".join(x for x in (_chu(r.chuc_vu), _chu(r.don_vi)) if x), className="desc")])],
                 className="db-dau"),
        *dong,
        html.Div(ghi, className="db-ghi-chu") if ghi else None,
        html.Div([*chan, html.Div(className="grow"), *(hanh_dong or [])], className="db-chan"),
    ], className="db-the")


def layout():
    db.dam_bao_bang()
    ds = db.ds_don_vi()
    return html.Div([
        dcc.Store(id="db-da-luu"),
        html.Div([
            field("Tìm", dcc.Input(id="db-tim", type="search", debounce=0.35, className="o-tim db-o-tim",
                                   placeholder="Tên, chức danh, email, chi nhánh hoặc số điện thoại")),
            field("Chi nhánh", dcc.Dropdown(id="db-dv", options=[{"label": "Mọi chi nhánh", "value": TAT_CA_DV},
                                                                 *[{"label": d, "value": d} for d in ds]],
                                            value=TAT_CA_DV, clearable=False, style={"width": "190px"})),
            html.Button([icon("plus", 14), html.Span("Thêm người")], id="db-them-mo", className="btn nt-nut"),
        ], className="toolbar"),
        seg_control("db-nhom", NHOM_NUT, "all"),
        html.Div(id="db-dem", className="desc db-dem"),
        html.Div(id="db-kq", className="db-luoi"),
        html.Div(id="db-msg"),
        _khung_nguoi(),
        _khung_nap() if current_user.duoc_cau_hinh else None,
    ])


def _khung_nguoi():
    ds = [("ho_ten", "Họ tên *", "Nguyễn Văn A"), ("chuc_vu", "Chức vụ", "Trưởng phòng Kỹ thuật"),
          ("email", "Email", "VanA@fpt.com"), ("di_dong", "Di động", "0903 123 456"),
          ("ext", "Máy lẻ", "51234"), ("don_vi", "Chi nhánh / đơn vị", "Khánh Hòa")]
    return modal("db-md", html.Span("Thêm người", id="db-md-tieu-de"), [
        dcc.Store(id="db-md-id"),
        html.Div("Cần ít nhất email hoặc số điện thoại. Người từ file PNC / TIN không sửa ở đây: nạp lại file.",
                 className="desc", style={"margin": "0 0 12px"}),
        html.Div([html.Div([html.Label(nhan), dcc.Input(id=f"db-f-{k}", type="text", className="inp", placeholder=vd,
                                                         maxLength=db.GIOI_HAN.get(k, 200))], className="field rong")
                  for k, nhan, vd in ds]
                 + [html.Div([html.Label("Ghi chú (khu vực phụ trách...)"),
                              dcc.Input(id="db-f-ghi_chu", type="text", className="inp", maxLength=300)],
                             className="field rong")], className="form-grid"),
        html.Button([icon("trash", 14), html.Span("Xoá người này")], id="db-md-xoa", className="btn nho",
                    style={"marginTop": "10px", "display": "none"}),
        html.Div(id="db-md-msg"),
    ], nut_chinh="Lưu")


def _khung_nap():
    def o(nguon, nhan):
        lan = db.lan_nap_cuoi().get(nguon)
        return html.Div([html.B(nhan), html.Div(f"Đang dùng bản nạp ngày {chu_gio_vn(lan, '%d/%m/%Y')}" if lan
                                                else "Chưa nạp", className="desc"),
                         dcc.Upload(id=f"db-file-{nguon}", className="upload-zone", accept=".xlsx",
                                    children=html.Div([icon("upload", 18), html.Span(" Kéo thả hoặc bấm chọn file .xlsx")]))],
                        className="db-nap-o")
    return html.Details([
        html.Summary("Nạp danh bạ từ file Excel (Quản trị, mỗi tháng một lần)", className="cg-tieu-de"),
        html.Div("Mỗi file là bản chụp mới nhất: nạp lại thì thay toàn bộ người của nguồn đó. "
                 "Người sale tự thêm không bị đụng.", className="desc"),
        html.Div([o("PNC", db.NGUON_FILE["PNC"]), o("TIN", db.NGUON_FILE["TIN"])], className="db-nap"),
        dcc.Loading(html.Div(id="db-nap-msg"), type="dot"),
    ], className="chu-giai card")


# ------------------------------------------------------------------ callbacks
def register(app):
    @app.callback(Output("db-kq", "children"), Output("db-dem", "children"),
                  Input("db-tim", "value"), Input("db-dv", "value"), Input("db-nhom", "value"),
                  Input("db-da-luu", "data"))
    def _ket_qua(q, dv, nhom, _luu):
        _vao()
        ds, tong = db.tim(q or "", dv or None, nhom)
        lan = db.lan_nap_cuoi()
        moi = " · ".join(f"{n} cập nhật {chu_gio_vn(t, '%d/%m/%Y')}" for n, t in sorted(lan.items()) if n != "TAY" and t)
        if ds.empty:
            return ([html.Div([html.Div("Không có ai khớp." if lan else "Chưa có danh bạ.", className="desc"),
                               html.Div(CHU_GIAI if lan else "Quản trị nạp file PNC và TIN ở cuối trang này.",
                                        className="desc")], className="card")], "")
        dem = f"{len(ds)} / {tong} người" + (" · gõ thêm để thu hẹp" if tong > len(ds) else "") + (f" · {moi}" if moi else "")
        return [the_nguoi(r) for r in ds.itertuples()], dem

    @app.callback(Output("db-md", "className"), Output("db-md-tieu-de", "children"), Output("db-md-id", "data"),
                  Output("db-md-xoa", "style"), Output("db-md-msg", "children"),
                  *[Output(f"db-f-{k}", "value") for k in ("ho_ten", "chuc_vu", "email", "di_dong", "ext", "don_vi", "ghi_chu")],
                  Input("db-them-mo", "n_clicks"), Input({"type": "db-sua", "id": ALL}, "n_clicks"),
                  Input("db-md-dong", "n_clicks"), Input("db-md-huy", "n_clicks"), State("db-dv", "value"),
                  prevent_initial_call=True)
    def _mo(_them, sua, _d, _h, dv):
        _vao()
        t = ctx.triggered_id
        rong = [no_update] * 7
        if t in ("db-md-dong", "db-md-huy"):
            return ("modal", no_update, no_update, no_update, "", *rong)
        if t == "db-them-mo":
            return ("modal mo", "Thêm người", None, {"display": "none", "marginTop": "10px"}, "",
                    "", "", "", "", "", dv or "", "")
        if not isinstance(t, dict) or not any(sua or []):
            raise PreventUpdate
        df = db.tat_ca()
        r = df[df.id_tay == t["id"]]
        if r.empty:
            raise PreventUpdate
        r = r.iloc[0]
        return ("modal mo", "Sửa người", int(t["id"]), {"display": "inline-flex", "marginTop": "10px"}, "",
                *[_chu(r[k]) for k in ("ho_ten", "chuc_vu", "email", "di_dong", "ext", "don_vi", "ghi_chu")])

    @app.callback(Output("db-md", "className", allow_duplicate=True), Output("db-md-msg", "children", allow_duplicate=True),
                  Output("db-da-luu", "data"), Output("db-msg", "children"),
                  Input("db-md-ok", "n_clicks"), Input("db-md-xoa", "n_clicks"), State("db-md-id", "data"),
                  *[State(f"db-f-{k}", "value") for k in ("ho_ten", "chuc_vu", "email", "di_dong", "ext", "don_vi", "ghi_chu")],
                  prevent_initial_call=True)
    def _luu(ok, xoa, id_, *gia_tri):
        _vao()
        if not (ok or xoa):
            raise PreventUpdate
        truong = dict(zip(("ho_ten", "chuc_vu", "email", "di_dong", "ext", "don_vi", "ghi_chu"), gia_tri))
        try:
            if ctx.triggered_id == "db-md-xoa":
                db.xoa_tay(int(id_), current_user.username)
                chu = "Đã xoá người này khỏi danh bạ."
            else:
                db.luu_tay(truong, current_user.username, int(id_) if id_ else None)
                chu = f"Đã lưu {truong['ho_ten']}."
        except (db.LoiDanhBa, TypeError, ValueError) as e:
            return no_update, alert(str(e), "bad"), no_update, no_update
        return "modal", "", pd.Timestamp.now().isoformat(), alert(chu, "ok")

    @app.callback(Output("db-nap-msg", "children"), Output("db-da-luu", "data", allow_duplicate=True),
                  Input("db-file-PNC", "contents"), Input("db-file-TIN", "contents"),
                  State("db-file-PNC", "filename"), State("db-file-TIN", "filename"), prevent_initial_call=True)
    def _nap(pnc, tin, ten_pnc, ten_tin):
        if not current_user.is_authenticated or not current_user.duoc_cau_hinh:
            raise PreventUpdate
        nguon = {"db-file-PNC": ("PNC", pnc, ten_pnc), "db-file-TIN": ("TIN", tin, ten_tin)}.get(ctx.triggered_id)
        if not nguon or not nguon[1]:
            raise PreventUpdate
        ma, noi_dung, ten = nguon
        try:
            kq = db.nap(base64.b64decode(noi_dung.split(",", 1)[1]), ten or "", ma, current_user.username)
        except (db.LoiDanhBa, ValueError, IndexError) as e:
            return alert(str(e), "bad"), no_update
        chu = (f"Đã nạp {kq['so_nguoi']} người cho {ma} ({kq['co_email']} có email), thay {kq['so_cu']} người cũ."
               + (f" Bỏ qua sheet không phải danh bạ: {', '.join(kq['bo_qua'])}." if kq["bo_qua"] else ""))
        return alert(chu, "ok"), pd.Timestamp.now().isoformat()
