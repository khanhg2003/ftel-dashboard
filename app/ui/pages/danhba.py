"""Trang Danh bạ - tra cứu người liên hệ nội bộ (logic: app/danh_ba.py). Dùng được cho admin + nhân viên KD IBB7.

Máy chủ chỉ gửi MỘT LẦN toàn bộ danh bạ dạng gọn (`db-du-lieu`); việc tìm, lọc chi nhánh, đổi nhóm chức danh và vẽ thẻ
do `assets/danh_ba.js` làm ngay trên trình duyệt nên không còn trễ. Người không có trong file thì sale tự thêm; file
PNC / TIN do Quản trị nạp lại hằng tháng. Bấm Sửa trên thẻ -> JS ghi `db-sk-sua`, máy chủ mở hộp sửa và kiểm quyền.
"""
from __future__ import annotations

import base64

import pandas as pd
from dash import ClientsideFunction, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate
from flask_login import current_user

from app import danh_ba as db
from app.thoi_gian import chu_gio_vn
from app.ui.components import alert, card, field, modal
from app.ui.icons import icon

NHOM_NUT = [("all", "Tất cả"), ("giam_doc", "Giám đốc"), ("pho_giam_doc", "Phó GĐ"), ("truong_phong_kt", "TP kỹ thuật"),
            ("ha_tang", "Hạ tầng"), ("doi_truong", "Đội trưởng"), ("ke_toan", "Kế toán"), ("khac", "Khác")]
O_NGUOI = ("ho_ten", "chuc_vu", "email", "di_dong", "ext", "don_vi", "ghi_chu")


def topbar():
    return [html.Div([html.H1("Danh bạ"), html.Div("Tra cứu người liên hệ: tên, chức danh, email, số điện thoại",
                                                   className="sub")])]


def _vao() -> None:
    """Mọi callback kiểm lại quyền ở máy chủ (ẩn menu là chưa đủ)."""
    if not (current_user.is_authenticated and current_user.duoc_soan_mail):
        raise PreventUpdate


def _chu(v) -> str:
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)


def layout():
    db.dam_bao_bang()
    return html.Div([
        dcc.Store(id="db-da-luu"), dcc.Store(id="db-du-lieu"), dcc.Store(id="db-ve"), dcc.Store(id="db-sk-sua"),
        html.Div([
            field("Tìm", dcc.Input(id="db-tim", type="search", className="o-tim db-o-tim", autoComplete="off",
                                    placeholder="Tên, chức danh, email, chi nhánh hoặc số điện thoại")),
            field("Chi nhánh", html.Select([html.Option("Mọi chi nhánh", value="")], id="db-dv", className="inp db-chon")),
            html.Button([icon("plus", 14), html.Span("Thêm người")], id="db-them-mo", className="btn nt-nut"),
        ], className="toolbar"),
        html.Div([html.Button(ten, className="db-cd" + (" active" if v == "the" else ""), **{"data-cd": v})
                  for v, ten in (("the", "Thẻ"), ("so_do", "Sơ đồ"))], id="db-cd", className="db-nhom db-cd-nhom"),
        html.Div([html.Button(ten, className="db-chip" + (" active" if v == "all" else ""), **{"data-nhom": v})
                  for v, ten in NHOM_NUT], id="db-nhom", className="db-nhom"),
        html.Div(id="db-dem", className="desc db-dem"),
        html.Div(html.Div("Đang tải danh bạ…", className="desc"), id="db-kq", className="db-luoi"),
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


def _chu_lan(nguon: str) -> str:
    lan = db.lan_nap_cuoi().get(nguon)
    return f"Đang dùng bản nạp ngày {chu_gio_vn(lan, '%d/%m/%Y')}" if lan else "Chưa nạp"


def _khung_nap():
    """Thẻ nạp file giống trang Nạp dữ liệu (ô kéo thả nét đứt, chữ giữa); hai ô cạnh nhau, mỗi ô một nguồn."""
    def o(nguon, nhan):
        return html.Div([
            html.Div([html.B(nhan), html.Div(_chu_lan(nguon), id=f"db-lan-{nguon}", className="desc")], className="db-nap-tieu"),
            dcc.Upload(id=f"db-file-{nguon}", className="upload-zone", accept=".xlsx", children=html.Div([
                html.Div("⬆", style={"fontSize": "26px", "marginBottom": "6px"}),
                html.Div([html.B("Chọn file"), " hoặc kéo thả vào đây"]),
                html.Div("Định dạng .xlsx", style={"fontSize": "12px", "marginTop": "4px"})]))], className="db-nap-o")
    return html.Div(card([
        html.Div([o("PNC", db.NGUON_FILE["PNC"]), o("TIN", db.NGUON_FILE["TIN"])], className="db-nap"),
        dcc.Loading(html.Div(id="db-nap-msg"), type="dot"),
    ], title="Nạp danh bạ từ file Excel",
        desc="Quản trị nạp mỗi tháng một lần. Mỗi file là bản chụp mới nhất: nạp lại thì thay toàn bộ người của nguồn đó, "
             "người sale tự thêm không bị đụng."), className="db-khung-nap")


# ------------------------------------------------------------------ callbacks
def register(app):
    app.clientside_callback(ClientsideFunction(namespace="ftel", function_name="nap_db"),
                            Output("db-ve", "data"), Input("db-du-lieu", "data"))

    @app.callback(Output("db-du-lieu", "data"), Input("db-da-luu", "data"))
    def _du_lieu(_luu):
        _vao()
        return db.cho_trinh_duyet()

    @app.callback(Output("db-md", "className"), Output("db-md-tieu-de", "children"), Output("db-md-id", "data"),
                  Output("db-md-xoa", "style"), Output("db-md-msg", "children"),
                  *[Output(f"db-f-{k}", "value") for k in O_NGUOI],
                  Input("db-them-mo", "n_clicks"), Input("db-sk-sua", "data"),
                  Input("db-md-dong", "n_clicks"), Input("db-md-huy", "n_clicks"), prevent_initial_call=True)
    def _mo(_them, sua, _d, _h):
        _vao()
        t = ctx.triggered_id
        if t in ("db-md-dong", "db-md-huy"):
            return ("modal", no_update, no_update, no_update, "", *[no_update] * len(O_NGUOI))
        if t == "db-them-mo":
            return ("modal mo", "Thêm người", None, {"display": "none", "marginTop": "10px"}, "", *[""] * len(O_NGUOI))
        df = db.tat_ca()
        r = df[df.id_tay == (sua or {}).get("id")] if t == "db-sk-sua" and sua else df.iloc[0:0]
        if r.empty:
            raise PreventUpdate
        r = r.iloc[0]
        return ("modal mo", "Sửa người", int(r.id_tay), {"display": "inline-flex", "marginTop": "10px"}, "",
                *[_chu(r[k]) for k in O_NGUOI])

    @app.callback(Output("db-md", "className", allow_duplicate=True), Output("db-md-msg", "children", allow_duplicate=True),
                  Output("db-da-luu", "data"), Output("db-msg", "children"),
                  Input("db-md-ok", "n_clicks"), Input("db-md-xoa", "n_clicks"), State("db-md-id", "data"),
                  *[State(f"db-f-{k}", "value") for k in O_NGUOI], prevent_initial_call=True)
    def _luu(ok, xoa, id_, *gia_tri):
        _vao()
        if not (ok or xoa):
            raise PreventUpdate
        truong = dict(zip(O_NGUOI, gia_tri))
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
                  Output("db-lan-PNC", "children"), Output("db-lan-TIN", "children"),
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
            return alert(str(e), "bad"), no_update, no_update, no_update
        chu = (f"Đã nạp {kq['so_nguoi']} người cho {ma} ({kq['co_email']} có email), thay {kq['so_cu']} người cũ."
               + (f" Bỏ qua sheet không phải danh bạ: {', '.join(kq['bo_qua'])}." if kq["bo_qua"] else ""))
        return alert(chu, "ok"), pd.Timestamp.now().isoformat(), _chu_lan("PNC"), _chu_lan("TIN")
