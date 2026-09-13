"""Ứng dụng web: đăng nhập + khung giao diện + điều hướng."""
from __future__ import annotations

from dash import Dash, Input, Output, State, dcc, html, no_update
from flask import Flask, redirect, render_template_string, request
from flask_login import current_user, login_user, logout_user

from app.auth import ROLE_LABEL, login_manager, xac_thuc
from app.config import BASE_DIR, SECRET_KEY
from app.ui.icons import icon

# Logo nhúng trực tiếp dạng base64 để tránh vấn đề phục vụ file tĩnh trên Vercel
FPT_LOGO_SRC = (
    "data:image/png;base64,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"
)

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
            html.Div([html.Img(src=FPT_LOGO_SRC, className="logo-img",
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
