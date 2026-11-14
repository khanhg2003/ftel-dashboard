"""Ứng dụng web: đăng nhập + khung giao diện + điều hướng."""
from __future__ import annotations

from dash import Dash, Input, Output, State, dcc, html, no_update
from flask import Flask, redirect, render_template_string, request
from flask_login import current_user, login_user, logout_user

from app.auth import ROLE_LABEL, login_manager, xac_thuc
from app.config import BASE_DIR, SECRET_KEY
from app.ui import khoi as kh
from app.ui import ky_chung
from app.ui.icons import icon
from app.ui.viet_hoa import viet_hoa

viet_hoa()          # nhãn tiếng Việt cho ô chọn và bảng - phải chạy trước khi dựng các trang

# Logo nhúng trực tiếp dạng base64 để tránh vấn đề phục vụ file tĩnh trên Vercel
FPT_LOGO_SRC = "data:image/png;base64,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"

server = Flask(__name__)
server.secret_key = SECRET_KEY
server.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

# Đảm bảo cột session_version tồn tại (migration nhẹ, cần trước login_manager). staff_map.ten_hien_thi
# tự vá ngay lúc nạp app.db (app.db._migrate_staff_map), không cần gọi lại ở đây.
from app.db import _migrate_session_version
_migrate_session_version()

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


def trang_mo_dau(user) -> str:
    """Nhân viên KD vào Báo cáo ngày (việc đầu tiên trong ngày), Trưởng phòng vào Báo cáo phòng của mình,
    các vai trò khác vào Báo cáo Tổng."""
    if user.role == "dvkh":
        return "/dvkh"
    if user.role == "nvkd":
        return "/baocaongay" if user.duoc_bao_cao_ngay else "/nhapton"
    if user.role == "online":
        return "/baocaongay" if user.duoc_bao_cao_ngay else "/phongonline"
    return "/phong" if user.role == "phong" and user.phong_nhan_su() else "/"


@server.route("/login", methods=["GET", "POST"])
def login():
    err = ""
    if request.method == "POST":
        user, err = xac_thuc(request.form.get("username", "").strip(),
                             request.form.get("password", ""))
        if user:
            login_user(user)
            return redirect(trang_mo_dau(user))
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


from app.api_ads import bp as _api_ads  # noqa: E402
from app.api_ban_tin import bp as _api_ban_tin  # noqa: E402
from app.api_zalo_gia import bp as _api_zalo_gia  # noqa: E402

server.register_blueprint(_api_ads)
server.register_blueprint(_api_ban_tin)
server.register_blueprint(_api_zalo_gia)


@server.before_request
def _bat_buoc_dang_nhap():
    path = request.path
    if path.startswith("/assets/") or path in ("/login", "/logout", "/favicon.ico", "/healthz"):
        return None
    if path.startswith("/api/ads/"):          # n8n / bot Telegram: xác thực bằng mã kết nối (app/api_ads.py)
        return None
    if path.startswith("/api/ban-tin/"):      # n8n làm đồng hồ Bản tin 8h: xác thực bằng khoá (app/api_ban_tin.py)
        return None
    if path.startswith("/api/zalo-gia/"):     # bot Zalo Tra cứu giá: xác thực bằng khoá webhook (app/api_zalo_gia.py)
        return None
    if not current_user.is_authenticated:
        if path.startswith("/_dash"):
            return "Phiên đăng nhập đã hết hạn. Tải lại trang.", 401
        return redirect("/login")
    if path == "/" and not current_user.vao_duoc("/"):      # Nhân viên KD mở địa chỉ app -> vào trang đầu của họ
        return redirect(trang_mo_dau(current_user))
    return None


app = Dash(__name__, server=server, suppress_callback_exceptions=True,
           assets_folder=str(BASE_DIR / "assets"),
           external_stylesheets=[
               "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"],
           # lịch chọn ngày đọc ngôn ngữ từ window.dateFns.locale -> nạp bản tiếng Việt
           external_scripts=["https://cdn.jsdelivr.net/npm/date-fns@4.1.0/locale/vi/cdn.min.js"],
           title="FTEL · Sales & HR Dashboard")

# Menu nhóm theo câu hỏi người xem đặt ra. Hướng dẫn và Tài khoản nằm ở chân menu.
NAV = [
    ("Hằng ngày", [
        ("/", "Báo cáo Tổng", "dashboard", None),
        ("/tracking", "Tracking ngày & So sánh", "trend", None),
    ]),
    # Thứ tự theo ngày làm việc của sale: nhập liệu đầu ngày -> công cụ làm việc -> xem số (chủ app yêu cầu 10/10/2026)
    ("Nhập liệu", [
        ("/baocaongay", "Báo cáo ngày", "calendar", "baocaongay"),
        ("/nhapton", "Nhập tồn", "edit", "nhapton"),
    ]),
    ("Công cụ", [
        ("/soanmail", "Soạn email", "mail", "soanmail"),
        ("/danhba", "Danh bạ", "book", "soanmail"),
        ("/giafpt", "Tra cứu giá", "tag", None),
    ]),
    ("Phòng & nhân sự", [
        ("/phong", "Báo cáo phòng", "table", "nhansu"),
        ("/phongonline", "Phòng Online", "table", None),
        ("/hr", "Nhân sự & NSLĐ", "users", "nhansu"),
    ]),
    ("Phân tích", [
        ("/phantich", "Phân tích bán hàng", "pie", None),
        ("/ads", "Ads IBB7", "trend", "ads"),
    ]),
    ("Liên khối", [("/lienkhoi", "Điều hành liên khối", "trend", "settings")]),
    ("Dữ liệu", [
        ("/upload", "Nạp dữ liệu", "upload", "upload"),
        ("/chatluong", "Chất lượng dữ liệu", "database", None),
    ]),
    ("Hệ thống", [
        ("/quantri", "Quản trị", "settings", "settings"),
        ("/phanhoi", "Phản hồi", "phan_hoi", "settings"),
    ]),
]
# đường dẫn cũ vẫn mở được, menu sáng đúng mục mới
DUONG_DAN_CU = {"/sosanh": "/tracking", "/settings": "/quantri"}


def _brand_dots():
    return html.Div([html.I(), html.I(), html.I()], className="brand-dots")


NAV_THEO_KHOI = {kh.KD: NAV, kh.DVKH: kh.NAV_DVKH, kh.KT: kh.NAV_KT}


def _chon_khoi(path: str, khoi_cu: str | None) -> str:
    """Khối đang xem: theo đường dẫn; trang dùng chung giữ khối cũ (nếu tài khoản còn được vào khối đó)."""
    duoc = current_user.khoi_duoc_xem()
    k = kh.khoi_cua_duong_dan(path) or (khoi_cu if khoi_cu in duoc else None) or duoc[0]
    return k if k in duoc else duoc[0]


def _chon_khoi_ui(khoi_dang_xem: str):
    """Nút chuyển khối nằm cạnh "Thoát" ở chân menu: hiện khối đang xem, bấm thì xổ danh sách lên trên.
    Chỉ hiện với tài khoản được vào từ hai khối trở lên. Dùng thẻ details nên không cần callback."""
    duoc = current_user.khoi_duoc_xem()
    if len(duoc) < 2:
        return None
    muc = []
    for k in kh.THU_TU:
        if k not in duoc:
            continue
        tt = kh.KHOI[k]
        dang_xem = k == khoi_dang_xem
        duoi = icon("check", 14) if dang_xem else (None if tt["san_sang"] else html.Small("Sắp có"))
        muc.append(dcc.Link([html.Span(tt["ten_day_du"]), duoi], href=tt["trang_chu"], className="khoi-muc active" if dang_xem else "khoi-muc"))
    return html.Details([
        html.Summary([icon("doi_khoi", 14), html.Span(kh.KHOI[khoi_dang_xem]["ten_ngan"])], className="khoi-hien", title="Chuyển khối làm việc"),
        html.Div(muc, className="khoi-ds"),
    ], className="khoi-doi")


def _sidebar(path: str, khoi_dang_xem: str = kh.KD):
    items = []
    for nhom, muc in NAV_THEO_KHOI[khoi_dang_xem]:
        muc_hien = []
        for href, label, ico, quyen in muc:
            if not current_user.vao_duoc(href):
                continue
            if quyen == "duoc_nap_dvkh" and not current_user.duoc_nap_dvkh:
                continue
            if quyen == "nhapton" and not current_user.duoc_nhap_ton:
                continue
            if quyen == "baocaongay" and not current_user.duoc_bao_cao_ngay:
                continue
            if quyen == "soanmail" and not current_user.duoc_soan_mail:
                continue
            if quyen == "ads" and not current_user.duoc_xem_ads:
                continue
            if quyen == "upload" and not current_user.duoc_upload:
                continue
            if quyen == "settings" and not current_user.duoc_cau_hinh:
                continue
            if quyen == "nhansu" and not current_user.duoc_xem_nhan_su:
                continue
            cls = "nav-item active" if DUONG_DAN_CU.get(path, path) == href else "nav-item"
            nhan_con = [icon(ico), html.Span(label)]
            if href == "/phanhoi" and current_user.duoc_cau_hinh:
                from app.phan_hoi import dem_phan_hoi_moi
                so_ph = dem_phan_hoi_moi()
                if so_ph > 0:
                    nhan_con.append(html.Span(f"{so_ph}", className="ph-badge-menu", title=f"{so_ph} phản hồi mới chờ xử lý"))
            muc_hien.append(dcc.Link(nhan_con, href=href, className=cls))
        if muc_hien:
            items.append(html.Div(nhom, className="nav-group"))
            items.extend(muc_hien)
    return html.Div([
        html.Div([
            html.Div([html.Img(src=FPT_LOGO_SRC, className="logo-img",
                               alt="FPT Telecom"),
                      html.Div([html.Div("FPT Telecom", className="logo"),
                                html.Div(kh.KHOI[khoi_dang_xem]["mo_ta"], className="sub")],
                               className="brand-text")],
                     className="brand-mark"),
        ], className="brand"),
        html.Div(items, className="nav"),
        html.Div([html.Div(current_user.ho_ten, className="who"),
                  html.Div(ROLE_LABEL.get(current_user.role, current_user.role)),
                  html.Div([
                      dcc.Link([icon("user", 14), html.Span("Tài khoản")], href="/taikhoan",
                               className="active" if path == "/taikhoan" else "",
                               title="Tài khoản của tôi · đổi mật khẩu"),
                      dcc.Link([icon("help", 14), html.Span("Hướng dẫn")], href="/huongdan",
                               className="active" if path == "/huongdan" else "",
                               title="Hướng dẫn sử dụng"),
                      html.A([icon("logout", 14), html.Span("Thoát")], href="/logout", title="Đăng xuất"),
                      _chon_khoi_ui(khoi_dang_xem),
                  ], className="foot-links")],
                 className="foot"),
        html.Button([icon("thu_gon", 17), html.Span("Thu gọn")], id="btn-thu-gon",
                    className="side-toggle", title="Thu gọn / mở rộng menu"),
    ], className="sidebar")


def serve_layout():
    from app.ui import ngan_nhan_su, tro_ly
    from app import phan_hoi
    return html.Div([
        dcc.Location(id="url", refresh=False),
        dcc.Store(id="ui-sidebar", storage_type="local", data={"thu_gon": False}),
        dcc.Store(id="ui-vw", data={"w": 1440, "h": 900}),
        dcc.Store(id="ui-menu"),
        dcc.Store(id="ui-khoi", storage_type="session"),
        # kỳ báo cáo, chi nhánh, phòng dùng chung giữa các trang (xem app/ui/ky_chung.py)
        dcc.Store(id="ky-chung", storage_type="session"),
        dcc.Store(id="ui-duong-dan"),
        html.Div(id="sidebar-container"),
        html.Div(id="menu-nen", className="menu-nen"),
        html.Div([
            html.Div([
                html.Button(icon("menu", 20), id="btn-menu", className="nut-menu",
                            title="Mở menu"),
                html.Div(id="topbar", className="topbar-noi"),
                html.Div(id="thanh-du-lieu", className="thanh-du-lieu"),
            ], className="topbar"),
            html.Div(id="page-content", className="page"),
        ], className="main"),
        tro_ly.khung_chat(),
        phan_hoi.khung_phan_hoi(),
        ngan_nhan_su.khung(),
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


@app.callback(Output("sidebar-container", "children"), Output("ui-khoi", "data"),
              Input("url", "pathname"), State("ui-khoi", "data"))
def _render_sidebar(path, khoi_cu):
    k = _chon_khoi(path or "/", khoi_cu)
    return _sidebar(path or "/", k), k


app.clientside_callback(ky_chung.JS_GHI_DUONG_DAN, Output("ui-duong-dan", "data"),
                        Input("ky-chung", "data"), Input("url", "pathname"))


@app.callback(Output("ky-chung", "data", allow_duplicate=True), Input("url", "pathname"),
              State("url", "search"), State("ky-chung", "data"), prevent_initial_call="initial_duplicate")
def _ky_tu_duong_dan(_path, search, store):
    """Mở link có ?tu=&den=&cn=&phong= thì lấy làm bộ lọc chung cho các trang sau."""
    tu_url = ky_chung.doc(None, search)
    if not tu_url:
        return no_update
    moi = ky_chung.doc(store, search)
    return moi if moi != ky_chung.lam_sach(store) else no_update


@app.callback(Output("thanh-du-lieu", "children"), Input("url", "pathname"))
def _thanh_du_lieu(path):
    duoc = current_user.khoi_duoc_xem()
    k = kh.khoi_cua_duong_dan(path or "/")
    if (k if k in duoc else duoc[0]) == kh.DVKH:
        from app.ui.pages.dvkh_chung import thanh_du_lieu as dvkh_thanh
        return dvkh_thanh()
    from app.ui.lien_ket import thanh_du_lieu
    return thanh_du_lieu()


TRANG_CAN_SO = {"/", "/phong", "/phongonline", "/phantich", "/tracking", "/sosanh", "/hr", "/chatluong"}


def _chua_co_du_lieu():
    """Chưa nạp file nào: hướng dẫn 3 bước thay cho các bảng trống."""
    buoc = [("1", "Nạp 3 file export", "Internet, Truyền hình, Camera - chọn cùng lúc rồi bấm Lưu."),
            ("2", "Kiểm tra dữ liệu", "Trang Chất lượng dữ liệu báo mục nào cần xử lý."),
            ("3", "Xem báo cáo", "Báo cáo Tổng, Báo cáo phòng... tự tính lại theo số vừa nạp.")]
    nut = (dcc.Link([icon("upload", 14), html.Span("Nạp dữ liệu ngay")], href="/upload",
                    className="btn primary") if current_user.duoc_upload else
           html.Div("Liên hệ người phụ trách nhập liệu để nạp file.", className="desc"))
    return html.Div([
        html.H3("Chưa có số liệu để báo cáo"),
        html.Div("App tính mọi chỉ số từ các file export. Làm theo 3 bước:", className="desc"),
        html.Div([html.Div([html.Div(so, className="buoc-so"),
                            html.Div([html.Div(ten, className="buoc-ten"),
                                      html.Div(mo_ta, className="buoc-noi-dung")])], className="buoc")
                  for so, ten, mo_ta in buoc], className="buoc-list", style={"margin": "16px 0"}),
        nut,
    ], className="card")


@app.callback(Output("page-content", "children"), Output("topbar", "children"),
              Input("url", "pathname"), State("url", "search"), State("ky-chung", "data"))
def _router(path, search=None, store=None):
    from urllib.parse import parse_qs

    from app.ui.pages import chatluong, dienbien, huongdan
    from app.ui.pages import hr as hr_page
    from app.ui.pages import quantri
    from app.ui.pages import phantich, phong, taikhoan, tongquan, upload

    path = path or "/"
    tab = (parse_qs((search or "").lstrip("?")).get("tab") or [None])[0]
    if not current_user.vao_duoc(path):
        return (html.Div([html.H3("Tài khoản này không mở được trang này"),
                          dcc.Link("← Về trang chính của bạn", href=trang_mo_dau(current_user), className="btn primary")], className="card"),
                _topbar_simple("Không có quyền"))
    if path == "/lienkhoi":
        from app.ui.pages import lienkhoi
        return lienkhoi.layout(), lienkhoi.topbar()
    if kh.khoi_cua_duong_dan(path) == kh.DVKH:
        from app.ui.pages import dvkh as dvkh_page
        return dvkh_page.trang(path, tab)
    if kh.khoi_cua_duong_dan(path) == kh.KT:
        return (html.Div([html.H3("Khối Kỹ thuật đang được xây dựng"),
                          html.Div("Trang này sẽ có khi khối Kỹ thuật có dữ liệu và chỉ số riêng.", className="desc")], className="card"),
                _topbar_simple("Khối Kỹ thuật", "Sắp có"))
    if path == "/baocaongay":
        from app.ui.pages import baocaongay
        return baocaongay.layout(), baocaongay.topbar()
    if path == "/nhapton":
        from app.ui.pages import nhapton
        return nhapton.layout(), nhapton.topbar()
    if path == "/giafpt":
        from app.ui.pages import giafpt
        return giafpt.layout(), giafpt.topbar()
    if path in ("/soanmail", "/danhba"):
        from app.ui.pages import danhba, soanmail
        if not current_user.duoc_soan_mail:
            return html.Div("Tài khoản này không dùng được Soạn email và Danh bạ."), _topbar_simple("Danh bạ")
        trang = soanmail if path == "/soanmail" else danhba
        return trang.layout(), trang.topbar()
    ky = ky_chung.doc(store, search)
    if path in TRANG_CAN_SO:
        from app.metrics import ngay_moi_nhat
        if not ngay_moi_nhat():
            return _chua_co_du_lieu(), _topbar_simple("Chưa có số liệu")
    if path == "/taikhoan":
        return taikhoan.layout(), taikhoan.topbar()
    if path == "/huongdan":
        return huongdan.layout(), huongdan.topbar()
    if path in ("/phong", "/hr") and not current_user.duoc_xem_nhan_su:
        return (html.Div("Bạn không có quyền xem chi tiết nhân sự."),
                _topbar_simple("Báo cáo phòng" if path == "/phong" else "Nhân sự & NSLĐ"))
    if path == "/phong":
        return phong.layout(ky), phong.topbar()
    if path == "/phongonline":
        from app.ui.pages import phongonline
        return phongonline.layout(ky), phongonline.topbar()
    if path == "/phantich":
        return phantich.layout(ky), phantich.topbar()
    if path in ("/tracking", "/sosanh"):
        tab = "sosanh" if path == "/sosanh" else (tab or "ngay")
        return dienbien.layout(tab, ky), dienbien.topbar(tab)
    if path == "/chatluong":
        return chatluong.layout(ky), chatluong.topbar()
    if path == "/ads":
        from app.ui.pages import ads as ads_page
        if not current_user.duoc_xem_ads:
            return html.Div("Tài khoản này không xem được mục Ads IBB7."), _topbar_simple("Ads IBB7")
        return ads_page.layout(tab), ads_page.topbar()
    if path in ("/quantri", "/settings", "/phanhoi"):
        if not current_user.duoc_cau_hinh:
            return html.Div("Bạn không có quyền vào mục Quản trị."), _topbar_simple("Quản trị")
        return quantri.layout("phanhoi" if path == "/phanhoi" else ("cocau" if path == "/settings" and not tab else tab)), quantri.topbar()
    if path == "/hr":
        return hr_page.layout(ky), hr_page.topbar()
    if path == "/upload":
        if not current_user.duoc_upload:
            return html.Div("Bạn không có quyền nạp dữ liệu."), _topbar_simple("Nạp dữ liệu")
        return upload.layout(), upload.topbar()
    if path not in ("/", ""):
        return _trang_khong_co(path), _topbar_simple("Không tìm thấy trang")
    return tongquan.layout(ky), tongquan.topbar()


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
    from app.ui.pages import chatluong, dienbien, huongdan
    from app.ui.pages import hr as hr_page
    from app.ui.pages import quantri
    from app.ui.pages import settings as settings_page
    from app.ui.pages import phantich, phong, sosanh, taikhoan, tongquan, tracking, upload

    from app.ui import ngan_nhan_su, tro_ly
    from app import phan_hoi

    from app.ui.pages import ads as ads_page
    from app.ui.pages import baocaongay, danhba, giafpt, nhapton, quantri_ban_tin, soanmail
    from app.ui.pages import dvkh as dvkh_page
    from app.ui.pages import lienkhoi, phongonline
    for mod in (dvkh_page, tongquan, phong, phongonline, lienkhoi, phantich, tracking, sosanh, dienbien, hr_page, chatluong, upload, quantri,
                settings_page, huongdan, taikhoan, tro_ly, ads_page, nhapton, baocaongay, ngan_nhan_su,
                danhba, soanmail, giafpt, phan_hoi, quantri_ban_tin):
        mod.register(app)


_register_pages()

if __name__ == "__main__":
    app.run(debug=True, port=8050)
