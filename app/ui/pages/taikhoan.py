"""Trang Tài khoản của tôi: mọi vai trò xem thông tin quyền của mình và tự đổi mật khẩu."""
from __future__ import annotations

from dash import Input, Output, State, dcc, html
from flask_login import current_user

from app.auth import ROLE_LABEL, doi_mat_khau
from app.org import phong_order
from app.ui.components import alert, card, field

MO_TA_QUYEN = {
    "admin": "Toàn quyền: xem số chung và chi tiết nhân sự mọi phòng, nạp dữ liệu, quản trị hệ thống.",
    "operator": "Nạp dữ liệu và xem số chung toàn chi nhánh. Không xem chi tiết từng nhân sự.",
    "phong": "Xem số chung toàn chi nhánh; chi tiết nhân sự chỉ của phòng phụ trách.",
    "nhanvien": "Xem số của phòng mình.",
}


def topbar():
    return [html.Div([html.H1("Tài khoản của tôi"),
                      html.Div("Thông tin đăng nhập, quyền xem và đổi mật khẩu", className="sub")])]


def _o_nhap(id_: str, goi_y: str) -> dcc.Input:
    return dcc.Input(id=id_, type="password", placeholder=goi_y, className="inp",
                     style={"width": "240px"}, n_submit=0)


def layout():
    pham_vi = current_user.phong_nhan_su()
    ten = {p["code"]: p["ten"] for p in phong_order()}
    phong = ("Mọi phòng" if pham_vi is None else
             ", ".join(ten.get(c, c) for c in pham_vi) if pham_vi else "Không xem chi tiết nhân sự")
    return html.Div([
        html.Div([
            html.Div(card([
                html.Table(html.Tbody([
                    html.Tr([html.Th("Tên đăng nhập"), html.Td(current_user.username)]),
                    html.Tr([html.Th("Họ tên"), html.Td(current_user.ho_ten)]),
                    html.Tr([html.Th("Vai trò"), html.Td(ROLE_LABEL.get(current_user.role,
                                                                       current_user.role))]),
                    html.Tr([html.Th("Chi tiết nhân sự"), html.Td(phong)]),
                ]), className="simple bang-thong-tin"),
                html.Div(MO_TA_QUYEN.get(current_user.role, ""), className="desc",
                         style={"marginTop": "10px"}),
            ], title="Thông tin tài khoản"), style={"flex": "1 1 340px"}),
            html.Div(card([
                html.Div([
                    field("Mật khẩu hiện tại", _o_nhap("tk-mk-cu", "")),
                    field("Mật khẩu mới", _o_nhap("tk-mk-moi", "Từ 8 ký tự")),
                    field("Nhập lại mật khẩu mới", _o_nhap("tk-mk-lai", "")),
                ], style={"display": "flex", "flexDirection": "column", "gap": "12px"}),
                html.Button("Đổi mật khẩu", id="tk-doi-mk", className="btn primary",
                            style={"marginTop": "14px"}),
                html.Div(id="tk-mk-msg", style={"marginTop": "12px"}),
            ], title="Đổi mật khẩu",
                desc="Nên đổi ngay mật khẩu được cấp lần đầu hoặc sau khi quản trị đặt lại."),
                style={"flex": "1 1 340px"}),
        ], style={"display": "flex", "gap": "20px", "flexWrap": "wrap", "alignItems": "flex-start"}),
    ])


def register(app):
    @app.callback(Output("tk-mk-msg", "children"), Output("tk-mk-cu", "value"),
                  Output("tk-mk-moi", "value"), Output("tk-mk-lai", "value"),
                  Input("tk-doi-mk", "n_clicks"), Input("tk-mk-lai", "n_submit"),
                  State("tk-mk-cu", "value"), State("tk-mk-moi", "value"), State("tk-mk-lai", "value"),
                  prevent_initial_call=True)
    def _doi_mk(_n, _enter, cu, moi, lai):
        if not getattr(current_user, "is_authenticated", False):
            return alert("Phiên đăng nhập đã hết hạn.", "bad"), None, None, None
        if not cu or not moi:
            return alert("Nhập đủ mật khẩu hiện tại và mật khẩu mới.", "warn"), cu, moi, lai
        if moi != (lai or ""):
            return alert("Hai lần nhập mật khẩu mới không khớp.", "bad"), cu, moi, None
        if moi == cu:
            return alert("Mật khẩu mới phải khác mật khẩu hiện tại.", "warn"), cu, None, None
        err = doi_mat_khau(current_user.username, cu, moi)
        if err:
            return alert(err, "bad"), None, None, None
        return alert("Đã đổi mật khẩu. Lần đăng nhập sau dùng mật khẩu mới.", "ok"), None, None, None
