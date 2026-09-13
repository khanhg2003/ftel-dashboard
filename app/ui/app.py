"""Ứng dụng web: đăng nhập + khung giao diện + điều hướng."""
from __future__ import annotations

from dash import Dash, Input, Output, State, dcc, html, no_update
from flask import Flask, redirect, render_template_string, request
from flask_login import current_user, login_user, logout_user

from app.auth import ROLE_LABEL, login_manager, xac_thuc
from app.config import BASE_DIR, SECRET_KEY
from app.ui.icons import icon

server = Flask(__name__)
server.secret_key = SECRET_KEY
server.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
login_manager.init_app(server)

LOGIN_PAGE = """<!doctype html>
<html lang="vi"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Đăng nhập · FTEL Dashboard</title>
<link rel="stylesheet" href="/assets/style.css">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
</head><body><div class="login-wrap"><form class="login-card" method="post">
<div class="brand-dots"><i></i><i></i><i></i></div>
<h1>Sales &amp; HR Dashboard</h1>
<p class="sub">FPT Telecom · Chi nhánh Đà Nẵng &amp; Quảng Nam</p>
{% if err %}<div class="login-err">{{ err }}</div>{% endif %}
<label for="username">Tài khoản</label>
<input id="username" name="username" autocomplete="username" autofocus required>
<label for="password">Mật khẩu</label>
<input id="password" name="password" type="password" autocomplete="current-password" required>
<button type="submit">Đăng nhập</button>
<div class="login-foot">Hệ thống nội bộ · Truy cập được ghi nhật ký</div>
</form></div></body></html>"""


@server.route("/login", methods=["GET", "POST"])
def login():
    err = ""
    if request.method == "POST":
        user, err = xac_thuc(request.form.get("username", "").strip(),
                             request.form.get("password", ""))
        if user:
            login_user(user)
            return redirect("/")
    return render_template_string(LOGIN_PAGE, err=err)


@server.route("/logout")
def logout():
    logout_user()
    return redirect("/login")


@server.route("/healthz")
def healthz():
    """Kiểm tra sức khoẻ cho dịch vụ nền / công cụ giám sát (không cần đăng nhập).

    Trả về 200 nếu database đọc được, 503 nếu hỏng. Không lộ số liệu kinh doanh.
    """
    from sqlalchemy import text as _text

    from app.db import engine
    try:
        with engine.connect() as c:
            ngay = c.execute(_text("SELECT MAX(ngay_online) FROM fact_internet")).scalar()
            n_user = c.execute(_text("SELECT COUNT(*) FROM users WHERE active = TRUE")).scalar()
        return {"status": "ok", "du_lieu_moi_nhat": str(ngay or "")[:10],
                "tai_khoan_dang_dung": int(n_user or 0)}, 200
    except Exception as e:                                   # pragma: no cover
        return {"status": "loi", "chi_tiet": type(e).__name__}, 503


@server.before_request
def _bat_buoc_dang_nhap():
    path = request.path
    if path.startswith("/assets/") or path in ("/login", "/logout", "/favicon.ico", "/healthz"):
        return None
    if not current_user.is_authenticated:
        if path.startswith("/_dash"):
            return "Phiên đăng nhập đã hết hạn. Tải lại trang.", 401
        return redirect("/login")
    return None


app = Dash(__name__, server=server, suppress_callback_exceptions=True,
           assets_folder=str(BASE_DIR / "assets"),
           external_stylesheets=[
               "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"],
           title="FTEL · Sales & HR Dashboard")

NAV = [
    ("Báo cáo", [
        ("/", "Báo cáo Tổng", "dashboard", None),
        ("/tracking", "Tracking ngày", "calendar", None),
        ("/sosanh", "So sánh kỳ", "compare", None),
        ("/hr", "Hiệu suất nhân sự", "users", None),
    ]),
    ("Vận hành", [
        ("/chatluong", "Chất lượng dữ liệu", "shield", None),
        ("/upload", "Nạp dữ liệu", "upload", "upload"),
        ("/quantri", "Quản trị", "shield", "settings"),
        ("/settings", "Cấu hình", "settings", "settings"),
    ]),
    ("Trợ giúp", [
        ("/huongdan", "Hướng dẫn sử dụng", "book", None),
    ]),
]


def _brand_dots():
    return html.Div([html.I(), html.I(), html.I()], className="brand-dots")


def _sidebar(path: str):
    items = []
    for nhom, muc in NAV:
        muc_hien = []
        for href, label, ico, quyen in muc:
            if quyen == "upload" and not current_user.duoc_upload:
                continue
            if quyen == "settings" and not current_user.duoc_cau_hinh:
                continue
            cls = "nav-item active" if path == href else "nav-item"
            muc_hien.append(dcc.Link([icon(ico), html.Span(label)], href=href, className=cls))
        if muc_hien:
            items.append(html.Div(nhom, className="nav-group"))
            items.extend(muc_hien)
    return html.Div([
        html.Div([
            html.Div([html.Img(src="/assets/fpt_logo.png", className="logo-img",
                               alt="FPT Telecom"),
                      html.Div([html.Div("FPT Telecom", className="logo"),
                                html.Div("Sales & HR Performance", className="sub")],
                               className="brand-text")],
                     className="brand-mark"),
        ], className="brand"),
        html.Div(items, className="nav"),
        html.Div([html.Div(current_user.ho_ten, className="who"),
                  html.Div(ROLE_LABEL.get(current_user.role, current_user.role)),
                  html.A([icon("logout", 14), html.Span("Đăng xuất")], href="/logout")],
                 className="foot"),
        html.Button([icon("thu_gon", 17), html.Span("Thu gọn")], id="btn-thu-gon",
                    className="side-toggle", title="Thu gọn / mở rộng menu"),
    ], className="sidebar")


def serve_layout():
    return html.Div([
        dcc.Location(id="url", refresh=False),
        dcc.Store(id="ui-sidebar", storage_type="local", data={"thu_gon": False}),
        dcc.Store(id="ui-vw", data={"w": 1440, "h": 900}),
        dcc.Store(id="ui-menu"),
        html.Div(id="sidebar-container"),
        html.Div(id="menu-nen", className="menu-nen"),
        html.Div([
            html.Div([
                html.Button(icon("menu", 20), id="btn-menu", className="nut-menu",
                            title="Mở menu"),
                html.Div(id="topbar", className="topbar-noi"),
            ], className="topbar"),
            html.Div(id="page-content", className="page"),
        ], className="main"),
    ], id="app-shell", className="app-shell")


app.layout = serve_layout


# Điện thoại: menu là ngăn kéo trượt ra. Bấm nút ☰ để mở, bấm nền mờ hoặc chọn trang để đóng.
app.clientside_callback(
    """
    function(_mo, _nen, path) {
        const trig = (window.dash_clientside.callback_context.triggered[0] || {}).prop_id || '';
        if (trig.startsWith('btn-menu')) { document.body.classList.toggle('menu-mo'); }
        else { document.body.classList.remove('menu-mo'); }
        return null;
    }
    """,
    Output("ui-menu", "data"), Input("btn-menu", "n_clicks"), Input("menu-nen", "n_clicks"),
    Input("url", "pathname"))


# Đo bề rộng cửa sổ để bảng tự co cho vừa màn hình (chế độ "Vừa màn hình").
# Đồng thời đo chiều cao thanh tiêu đề để thanh lọc dính ngay bên dưới, không bị che.
app.clientside_callback(
    """
    function(path, thu_gon) {
        const doCao = function () {
            const tb = document.querySelector('.topbar');
            if (tb) { document.documentElement.style.setProperty('--topbar-h', tb.offsetHeight + 'px'); }
        };
        setTimeout(doCao, 60); setTimeout(doCao, 600);
        if (!window.__ftel_resize) {          // gắn một lần, sau đó tự cập nhật khi kéo cửa sổ
            window.__ftel_resize = true;
            let cho = null;
            window.addEventListener('resize', function () {
                clearTimeout(cho);
                cho = setTimeout(function () {
                    doCao();
                    window.dash_clientside.set_props('ui-vw',
                        {data: {w: window.innerWidth, h: window.innerHeight}});
                }, 150);
            });
        }
        return {w: window.innerWidth, h: window.innerHeight};
    }
    """,
    Output("ui-vw", "data"), Input("url", "pathname"), Input("ui-sidebar", "data"))


@app.callback(Output("ui-sidebar", "data"), Input("btn-thu-gon", "n_clicks"),
              State("ui-sidebar", "data"), prevent_initial_call=True)
def _thu_gon(n, data):
    if not n:
        return no_update
    return {"thu_gon": not (data or {}).get("thu_gon", False)}


@app.callback(Output("app-shell", "className"), Input("ui-sidebar", "data"))
def _class_shell(data):
    return "app-shell thu-gon" if (data or {}).get("thu_gon") else "app-shell"


@app.callback(Output("btn-thu-gon", "children"), Input("ui-sidebar", "data"))
def _nhan_nut_thu_gon(data):
    if (data or {}).get("thu_gon"):
        return [icon("mo_rong", 17), html.Span("Mở rộng")]
    return [icon("thu_gon", 17), html.Span("Thu gọn")]


@app.callback(Output("sidebar-container", "children"), Input("url", "pathname"))
def _render_sidebar(path):
    return _sidebar(path or "/")


@app.callback(Output("page-content", "children"), Output("topbar", "children"),
              Input("url", "pathname"))
def _router(path):
    from app.ui.pages import chatluong, huongdan
    from app.ui.pages import hr as hr_page
    from app.ui.pages import quantri
    from app.ui.pages import settings as settings_page
    from app.ui.pages import sosanh, tongquan, tracking, upload

    path = path or "/"
    if path == "/huongdan":
        return huongdan.layout(), huongdan.topbar()
    if path == "/tracking":
        return tracking.layout(), tracking.topbar()
    if path == "/sosanh":
        return sosanh.layout(), sosanh.topbar()
    if path == "/chatluong":
        return chatluong.layout(), chatluong.topbar()
    if path == "/quantri":
        if not current_user.duoc_cau_hinh:
            return html.Div("Bạn không có quyền vào mục Quản trị."), _topbar_simple("Quản trị")
        return quantri.layout(), quantri.topbar()
    if path == "/hr":
        return hr_page.layout(), hr_page.topbar()
    if path == "/upload":
        if not current_user.duoc_upload:
            return html.Div("Bạn không có quyền nạp dữ liệu."), _topbar_simple("Nạp dữ liệu")
        return upload.layout(), upload.topbar()
    if path == "/settings":
        if not current_user.duoc_cau_hinh:
            return html.Div("Bạn không có quyền vào mục Cấu hình."), _topbar_simple("Cấu hình")
        return settings_page.layout(), settings_page.topbar()
    if path not in ("/", ""):
        return _trang_khong_co(path), _topbar_simple("Không tìm thấy trang")
    return tongquan.layout(), tongquan.topbar()


def _trang_khong_co(path: str):
    return html.Div([
        html.Div("404", style={"fontSize": "46px", "fontWeight": "700",
                               "color": "var(--fpt-blue)"}),
        html.H3(f"Không có trang “{path}”"),
        html.Div("Đường dẫn có thể đã cũ hoặc gõ nhầm.",
                 style={"color": "var(--text-muted)", "marginBottom": "16px"}),
        dcc.Link("← Về Báo cáo Tổng", href="/", className="btn primary"),
    ], className="card", style={"textAlign": "center", "padding": "48px"})


def _topbar_simple(title: str, sub: str = ""):
    return [html.Div([html.H1(title), html.Div(sub, className="sub")])]


def _register_pages():
    from app.ui.pages import chatluong, huongdan
    from app.ui.pages import hr as hr_page
    from app.ui.pages import quantri
    from app.ui.pages import settings as settings_page
    from app.ui.pages import sosanh, tongquan, tracking, upload

    for mod in (tongquan, tracking, sosanh, hr_page, chatluong, upload, quantri, settings_page,
                huongdan):
        mod.register(app)


_register_pages()

if __name__ == "__main__":
    app.run(debug=True, port=8050)
