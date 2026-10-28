"""Phản hồi hệ thống: hộp góp ý ghim cố định (lọc mục theo quyền tài khoản) và tab tổng hợp ở Quản trị."""
from __future__ import annotations

import time
from dash import Input, Output, Patch, State, ctx, dcc, html, no_update
from flask_login import current_user
from sqlalchemy import delete, func, select

from app.auth import ROLE_LABEL, ghi_log
from app.db import engine, session_scope
from app.models import PhanHoi
from app.thoi_gian import chu_gio_vn, utc_bay_gio
from app.ui import khoi as kh
from app.ui.components import COT_SUA, alert, callback_can_quyen, card, dong_can_sua, field, kpi, modal
from app.ui.icons import icon
from app.ui.luoi import bang

LOAI_PHAN_HOI = ["Cải thiện tính năng", "Bổ sung tính năng", "Khác"]
TRANG_THAI_MAP = {"moi": "Mới", "dang_xu_ly": "Đang xử lý", "da_xu_ly": "Đã xử lý"}
AN = {"display": "none"}

# Danh sách toàn bộ mục chức năng trong hệ thống kèm điều kiện quyền tương ứng
MUC_KD = [
    ("/", "Báo cáo Tổng", None),
    ("/tracking", "Tracking ngày & So sánh", None),
    ("/baocaongay", "Báo cáo ngày", "baocaongay"),
    ("/nhapton", "Nhập tồn", "nhapton"),
    ("/soanmail", "Soạn email", "soanmail"),
    ("/danhba", "Danh bạ", "soanmail"),
    ("/giafpt", "Tra cứu giá", None),
    ("/phong", "Báo cáo phòng", "nhansu"),
    ("/hr", "Nhân sự & NSLĐ", "nhansu"),
    ("/phantich", "Phân tích bán hàng", None),
    ("/ads", "Ads IBB7", "ads"),
    ("/upload", "Nạp dữ liệu", "upload"),
    ("/chatluong", "Chất lượng dữ liệu", None),
    ("/quantri", "Quản trị hệ thống", "settings"),
]

MUC_DVKH = [
    ("/dvkh", "Tổng quan KPI (DVKH)", None),
    ("/dvkh/nhan-su", "Hiệu suất CSKH (DVKH)", None),
    ("/dvkh/sr-bi-dong", "SR bị động (DVKH)", None),
    ("/dvkh/sr-chu-dong", "SR chủ động (DVKH)", None),
    ("/dvkh/roi-mang", "Rời mạng (DVKH)", None),
    ("/dvkh/cong-no", "Công nợ (DVKH)", None),
    ("/dvkh/insight", "Nhận định & phân tích sâu (DVKH)", None),
    ("/dvkh/nap", "Cập nhật Excel (DVKH)", "duoc_nap_dvkh"),
]

SVG_BONG_SAO = """<svg viewBox="0 0 28 28" width="24" height="24" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M4 6.5C4 4.84315 5.34315 3.5 7 3.5H21C22.6569 3.5 24 4.84315 24 6.5V17.5C24 19.1569 22.6569 20.5 21 20.5H11.5L6.2 24.4C5.54 24.89 4.6 24.42 4.6 23.6V20.5C4.26 20.5 4 20.24 4 19.9V6.5Z" fill="#155EEF"/>
<path d="M9.5 9.6L10.1 11.1L11.7 11.2L10.5 12.2L10.9 13.8L9.5 12.9L8.1 13.8L8.5 12.2L7.3 11.2L8.9 11.1L9.5 9.6Z" fill="#FFFFFF"/>
<path d="M14 9.1L14.7 10.8L16.5 11L15.1 12.1L15.5 13.9L14 12.9L12.5 13.9L12.9 12.1L11.5 11L13.3 10.8L14 9.1Z" fill="#FFFFFF"/>
<path d="M18.5 9.6L19.1 11.1L20.7 11.2L19.5 12.2L19.9 13.8L18.5 12.9L17.1 13.8L17.5 12.2L16.3 11.2L17.9 11.1L18.5 9.6Z" fill="#FFFFFF"/>
</svg>"""


def dam_bao_bang_phan_hoi():
    """Đảm bảo bảng phan_hoi_he_thong tồn tại trong database."""
    try:
        PhanHoi.__table__.create(bind=engine, checkfirst=True)
    except Exception:
        pass


dam_bao_bang_phan_hoi()


def _duoc_xem_muc(user, href: str, quyen: str | None) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not user.vao_duoc(href):
        return False
    if quyen == "duoc_nap_dvkh" and not user.duoc_nap_dvkh:
        return False
    if quyen == "nhapton" and not user.duoc_nhap_ton:
        return False
    if quyen == "baocaongay" and not user.duoc_bao_cao_ngay:
        return False
    if quyen == "soanmail" and not user.duoc_soan_mail:
        return False
    if quyen == "ads" and not user.duoc_xem_ads:
        return False
    if quyen == "upload" and not user.duoc_upload:
        return False
    if quyen == "settings" and not user.duoc_cau_hinh:
        return False
    if quyen == "nhansu" and not user.duoc_xem_nhan_su:
        return False
    return True


def muc_theo_quyen(user, path: str | None = None) -> tuple[list[dict], str]:
    """Trả về (danh sách options mục tính năng theo quyền của user, giá trị chọn mặc định)."""
    if not user or not getattr(user, "is_authenticated", False):
        return [{"label": "Khác", "value": "Khác"}], "Khác"
    khoi_duoc = user.khoi_duoc_xem()
    chi_dvkh = khoi_duoc == [kh.DVKH]
    ds_muc: list[tuple[str, str]] = []
    if kh.KD in khoi_duoc:
        for href, ten, quyen in MUC_KD:
            if _duoc_xem_muc(user, href, quyen):
                ds_muc.append((href, ten))
    if kh.DVKH in khoi_duoc:
        for href, ten, quyen in MUC_DVKH:
            if _duoc_xem_muc(user, href, quyen):
                nhan = ten.replace(" (DVKH)", "") if chi_dvkh else ten
                ds_muc.append((href, nhan))
    ds_muc.append(("/khac", "Khác"))
    opts = [{"label": ten, "value": ten} for _, ten in ds_muc]
    duong_dan = {"/sosanh": "/tracking", "/settings": "/quantri"}.get(path or "/", path or "/")
    mac_dinh = next((ten for href, ten in ds_muc if href == duong_dan), ds_muc[0][1])
    return opts, mac_dinh


def luu_phan_hoi(user, loai: str, muc: str, noi_dung: str) -> tuple[bool, str]:
    """Lưu phản hồi mới của người dùng vào bảng phan_hoi_he_thong."""
    nd = (noi_dung or "").strip()
    if not nd:
        return False, "Anh/chị vui lòng nhập nội dung phản hồi trước khi gửi."
    loai_chuan = loai if loai in LOAI_PHAN_HOI else LOAI_PHAN_HOI[0]
    muc_chuan = (muc or "Khác").strip() or "Khác"
    phong_str = ", ".join(user.scope) if getattr(user, "scope", None) else "Toàn chi nhánh"
    vai_tro_str = ROLE_LABEL.get(getattr(user, "role", ""), getattr(user, "role", ""))
    with session_scope() as s:
        row = PhanHoi(
            username=user.username,
            ho_ten=user.ho_ten or user.username,
            vai_tro=vai_tro_str,
            phong=phong_str,
            loai=loai_chuan,
            muc=muc_chuan,
            noi_dung=nd[:3000],
            trang_thai="moi",
            tao_luc=utc_bay_gio(),
        )
        s.add(row)
    ghi_log("gui_phan_hoi", f"[{loai_chuan} · {muc_chuan}] {nd[:120]}")
    return True, "Đã ghi nhận phản hồi của anh/chị. Quản trị viên sẽ kiểm tra và cập nhật sớm nhất."


def dem_phan_hoi_moi() -> int:
    """Số lượng phản hồi ở trạng thái Mới (chưa xử lý)."""
    try:
        with session_scope() as s:
            n = s.execute(select(func.count(PhanHoi.id)).where(PhanHoi.trang_thai == "moi")).scalar()
            return int(n or 0)
    except Exception:
        return 0


def danh_sach_phan_hoi() -> list[dict]:
    """Đọc toàn bộ phản hồi cho trang Quản trị, mới nhất xếp trên."""
    with session_scope() as s:
        rows = s.execute(select(PhanHoi).order_by(PhanHoi.id.desc())).scalars().all()
        kq = []
        for r in rows:
            kq.append({
                "id": r.id,
                "tao_luc": chu_gio_vn(r.tao_luc),
                "username": r.username,
                "ho_ten": r.ho_ten or r.username,
                "nguoi_gui": f"{r.ho_ten or r.username} ({r.username})",
                "vai_tro": r.vai_tro or "",
                "phong": r.phong or "",
                "vai_tro_phong": f"{r.vai_tro or ''} · {r.phong or ''}".strip(" ·"),
                "loai": r.loai,
                "muc": r.muc,
                "noi_dung": r.noi_dung,
                "trang_thai": r.trang_thai,
                "trang_thai_nhan": TRANG_THAI_MAP.get(r.trang_thai, r.trang_thai),
                "ghi_chu_admin": r.ghi_chu_admin or "",
                "xu_ly_luc": chu_gio_vn(r.xu_ly_luc) if r.xu_ly_luc else "",
                "xu_ly_boi": r.xu_ly_boi or "",
            })
        return kq


def lay_phan_hoi(id_: int) -> dict | None:
    with session_scope() as s:
        r = s.get(PhanHoi, int(id_))
        if not r:
            return None
        return {
            "id": r.id,
            "tao_luc": chu_gio_vn(r.tao_luc),
            "nguoi_gui": f"{r.ho_ten or r.username} ({r.username})",
            "vai_tro_phong": f"{r.vai_tro or ''} · {r.phong or ''}".strip(" ·"),
            "loai": r.loai,
            "muc": r.muc,
            "noi_dung": r.noi_dung,
            "trang_thai": r.trang_thai,
            "ghi_chu_admin": r.ghi_chu_admin or "",
            "xu_ly_boi": r.xu_ly_boi or "",
            "xu_ly_luc": chu_gio_vn(r.xu_ly_luc) if r.xu_ly_luc else "",
        }


def cap_nhat_phan_hoi(id_: int, trang_thai: str, ghi_chu: str, nguoi_xu_ly: str) -> tuple[bool, str]:
    tt = trang_thai if trang_thai in TRANG_THAI_MAP else "da_xu_ly"
    with session_scope() as s:
        r = s.get(PhanHoi, int(id_))
        if not r:
            return False, "Không tìm thấy phản hồi này."
        r.trang_thai = tt
        r.ghi_chu_admin = (ghi_chu or "").strip() or None
        r.xu_ly_luc = utc_bay_gio()
        r.xu_ly_boi = nguoi_xu_ly
    ghi_log("xu_ly_phan_hoi", f"ID #{id_} -> {TRANG_THAI_MAP[tt]}")
    return True, f"Đã cập nhật phản hồi #{id_} sang trạng thái “{TRANG_THAI_MAP[tt]}”."


def danh_dau_da_xu_ly(ids: list[int], nguoi_xu_ly: str) -> int:
    if not ids:
        return 0
    dem = 0
    with session_scope() as s:
        for id_ in ids:
            r = s.get(PhanHoi, int(id_))
            if r and r.trang_thai != "da_xu_ly":
                r.trang_thai = "da_xu_ly"
                r.xu_ly_luc = utc_bay_gio()
                r.xu_ly_boi = nguoi_xu_ly
                dem += 1
    if dem:
        ghi_log("xu_ly_phan_hoi", f"Đánh dấu hoàn tất {dem} phản hồi: {ids}")
    return dem


def xoa_phan_hoi(ids: list[int], nguoi_xu_ly: str) -> int:
    if not ids:
        return 0
    with session_scope() as s:
        res = s.execute(delete(PhanHoi).where(PhanHoi.id.in_([int(x) for x in ids])))
        dem = int(res.rowcount or 0)
    if dem:
        ghi_log("xoa_phan_hoi", f"{nguoi_xu_ly} xoá {dem} phản hồi: {ids}")
    return dem


# ------------------------------------------------------------------ Giao diện nút ghim & popup Phản hồi hệ thống
def nut_menu_trai():
    """Nút Phản hồi hệ thống ghim cố định ở chân menu trái (ngay trên nút Thu gọn)."""
    return html.Button(
        [icon("phan_hoi", 17), html.Span("Phản hồi hệ thống")],
        id="ph-nut-mo",
        className="ph-nut-menu",
        title="Gửi góp ý, đề xuất cải thiện hoặc báo lỗi về Quản trị",
    )


def khung_phan_hoi():
    """Hộp popup Phản hồi hệ thống nổi cố định trên màn hình."""
    if not current_user.is_authenticated:
        return html.Div()
    opts, mac_dinh = muc_theo_quyen(current_user)
    return html.Div([
        dcc.Store(id="ph-cap-nhat"),
        html.Div([
            html.Div([
                html.Div([
                    dcc.Markdown(SVG_BONG_SAO, dangerously_allow_html=True, className="ph-ico-sao"),
                    html.Span("Phản hồi hệ thống", className="ph-tieu-de"),
                ], className="ph-dau-trai"),
                html.Button("×", id="ph-dong", className="ph-dong", title="Đóng"),
            ], className="ph-dau"),
            html.Div(
                "Trong quá trình sử dụng, nếu anh/chị có đề xuất cải thiện, bổ sung tính năng hoặc cần "
                "điều chỉnh số liệu, vui lòng gửi phản hồi tại đây để hệ thống được cập nhật sát nhất "
                "với thực tế công việc tại đơn vị.",
                className="ph-mo-ta",
            ),
            html.Div([
                dcc.Dropdown(
                    id="ph-loai",
                    options=[{"label": x, "value": x} for x in LOAI_PHAN_HOI],
                    value=LOAI_PHAN_HOI[0],
                    clearable=False,
                    searchable=False,
                    className="ph-chon",
                ),
                dcc.Dropdown(
                    id="ph-muc",
                    options=opts,
                    value=mac_dinh,
                    clearable=False,
                    searchable=False,
                    className="ph-chon",
                ),
                dcc.Textarea(
                    id="ph-noi-dung",
                    placeholder="Bắt buộc nhập",
                    className="ph-o-nhap",
                    maxLength=3000,
                ),
            ], className="ph-than"),
            html.Div(id="ph-msg", className="ph-msg"),
            html.Div([
                html.Button("Gửi phản hồi", id="ph-gui", className="ph-nut-gui", disabled=True),
            ], className="ph-chan"),
        ], id="ph-hop", className="ph-hop"),
    ], id="ph-khung", className="ph-khung")


# ------------------------------------------------------------------ Giao diện Quản trị (Admin)
CHON = {"field": "_chon", "headerName": "", "width": 44, "maxWidth": 44, "pinned": "left",
        "checkboxSelection": True, "headerCheckboxSelection": True, "sortable": False,
        "resizable": False}


def _cot_phan_hoi():
    return [
        CHON,
        {"field": "tao_luc", "headerName": "Thời điểm", "width": 145, "pinned": "left"},
        {"field": "nguoi_gui", "headerName": "Người gửi", "minWidth": 165, "flex": 1.1, "pinned": "left"},
        {"field": "vai_tro_phong", "headerName": "Vai trò · Phòng", "minWidth": 165, "flex": 1.1,
         "tooltipField": "vai_tro_phong"},
        {"field": "loai", "headerName": "Loại phản hồi", "width": 155},
        {"field": "muc", "headerName": "Mục tính năng", "minWidth": 155, "flex": 1},
        {"field": "noi_dung", "headerName": "Nội dung góp ý của anh/chị", "minWidth": 260, "flex": 2.2,
         "tooltipField": "noi_dung", "wrapText": True, "autoHeight": True},
        {"field": "trang_thai_nhan", "headerName": "Trạng thái", "width": 125,
         "cellStyle": {"styleConditions": [
             {"condition": "params.value == 'Mới'",
              "style": {"color": "#B42318", "fontWeight": "700", "backgroundColor": "#FEF3F2"}},
             {"condition": "params.value == 'Đang xử lý'",
              "style": {"color": "#005A96", "fontWeight": "650", "backgroundColor": "#EFF8FF"}},
             {"condition": "params.value == 'Đã xử lý'",
              "style": {"color": "#067647", "fontWeight": "650", "backgroundColor": "#ECFDF3"}},
         ]}},
        {"field": "ghi_chu_admin", "headerName": "Ghi chú xử lý", "minWidth": 180, "flex": 1.3,
         "tooltipField": "ghi_chu_admin"},
        COT_SUA,
    ]


def hop_thoai_quan_tri():
    return modal("qt-modal-ph", html.Span("Xử lý phản hồi", id="qt-ph-tieu-de"), [
        dcc.Store(id="qt-ph-dang-sua"),
        html.Div(id="qt-ph-chi-tiet", className="ph-ct-hop"),
        html.Div([
            html.Div([
                html.Label("Trạng thái xử lý"),
                dcc.Dropdown(
                    id="qt-ph-trangthai",
                    clearable=False,
                    searchable=False,
                    value="da_xu_ly",
                    options=[{"label": ten, "value": ma} for ma, ten in TRANG_THAI_MAP.items()],
                ),
            ], className="field rong"),
            html.Div([
                html.Label("Ghi chú xử lý / phản hồi của Admin"),
                dcc.Textarea(
                    id="qt-ph-ghichu",
                    placeholder="Ghi chú nguyên nhân, hướng xử lý hoặc bản cập nhật đã fix...",
                    className="inp",
                    style={"height": "88px", "resize": "vertical"},
                ),
            ], className="field rong", style={"gridColumn": "1 / -1"}),
        ], className="form-grid", style={"marginTop": "14px"}),
        html.Div(id="qt-modal-ph-msg"),
    ], nut_chinh="Lưu xử lý")


def pane_quan_tri(tab: str):
    return html.Div(id="qt-pane-phanhoi", style={} if tab == "phanhoi" else AN, children=[
        dcc.Store(id="qt-ph-loc-tt", data="ALL"),
        dcc.ConfirmDialog(id="qt-ph-xacnhan-xoa", message="Xoá các phản hồi đã chọn?"),
        hop_thoai_quan_tri(),
        html.Div(id="qt-ph-kpi", className="kpi-row kpi-4"),
        card([
            html.Div([
                field("Loại phản hồi", dcc.Dropdown(
                    id="qt-ph-loc-loai",
                    value="ALL",
                    clearable=False,
                    searchable=False,
                    options=[{"label": "Tất cả loại", "value": "ALL"}]
                            + [{"label": x, "value": x} for x in LOAI_PHAN_HOI],
                    style={"minWidth": "190px"},
                )),
                field("Tìm nhanh", dcc.Input(
                    id="qt-ph-tim",
                    type="search",
                    className="o-tim",
                    placeholder="Tìm người gửi, phòng, mục, nội dung…",
                )),
                html.Div(className="grow"),
                html.Button([icon("check", 14), html.Span("Đánh dấu Đã xử lý")],
                            id="qt-ph-btn-xong", className="btn"),
                html.Button([icon("trash", 14), html.Span("Xoá")],
                            id="qt-ph-btn-xoa", className="btn nguy-hiem"),
            ], className="toolbar"),
            html.Div(id="qt-ph-msg"),
            bang("qt-ph-grid", cao=480, cot=_cot_phan_hoi(), getRowId="params.data.id + ''",
                 cot_mac_dinh={"resizable": True, "sortable": True, "filter": True},
                 tuy_chon={"rowSelection": "multiple", "suppressRowClickSelection": True,
                           "suppressCellFocus": True, "tooltipShowDelay": 250}),
        ], title="Danh sách phản hồi từ các tài khoản",
           desc="Bấm vào từng thẻ chỉ số phía trên để lọc theo trạng thái · bấm ✎ Sửa (hoặc bấm đúp vào dòng) để xem chi tiết và ghi chú xử lý"),
    ])


# ------------------------------------------------------------------ Callbacks
def register(app):
    # Mở / đóng hộp Phản hồi hệ thống ở góc trái dưới
    @app.callback(
        Output("ph-khung", "className"),
        Output("ph-muc", "options"),
        Output("ph-muc", "value"),
        Output("ph-msg", "children", allow_duplicate=True),
        Input("ph-nut-mo", "n_clicks"),
        Input("ph-dong", "n_clicks"),
        State("ph-khung", "className"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def _bat_tat_popup(_mo, _dong, cls_hien, path):
        trig = ctx.triggered_id
        dang_mo = "mo" in (cls_hien or "")
        if trig == "ph-dong" or (trig == "ph-nut-mo" and dang_mo):
            return "ph-khung", no_update, no_update, ""
        opts, mac_dinh = muc_theo_quyen(current_user, path)
        return "ph-khung mo", opts, mac_dinh, ""

    # Bật / khoá nút "Gửi phản hồi" ngay trên trình duyệt khi người dùng gõ chữ
    app.clientside_callback(
        """function(val) {
            return !val || !String(val).trim();
        }""",
        Output("ph-gui", "disabled"),
        Input("ph-noi-dung", "value"),
    )

    # Gửi phản hồi
    @app.callback(
        Output("ph-msg", "children"),
        Output("ph-noi-dung", "value"),
        Output("ph-cap-nhat", "data"),
        Input("ph-gui", "n_clicks"),
        State("ph-loai", "value"),
        State("ph-muc", "value"),
        State("ph-noi-dung", "value"),
        prevent_initial_call=True,
    )
    def _gui_phan_hoi(n, loai, muc, noi_dung):
        if not n or not current_user.is_authenticated:
            return no_update, no_update, no_update
        ok, msg = luu_phan_hoi(current_user, loai, muc, noi_dung)
        if not ok:
            return alert(msg, "warn"), no_update, no_update
        return alert(msg, "ok"), "", time.time()

    # ---------------- Callbacks Quản trị (chỉ dành cho Admin)
    cb = callback_can_quyen(app, "duoc_cau_hinh")

    @cb(Output("qt-pane-phanhoi", "style"), Input("qt-tab", "value"), prevent_initial_call=True)
    def _hien_tab_ph(tab):
        return {} if tab == "phanhoi" else AN

    @cb(Output("qt-ph-loc-tt", "data"),
        Input("qt-ph-k-all", "n_clicks"), Input("qt-ph-k-moi", "n_clicks"),
        Input("qt-ph-k-dang", "n_clicks"), Input("qt-ph-k-xong", "n_clicks"),
        prevent_initial_call=True)
    def _chon_kpi_tt(*_):
        m = {"qt-ph-k-all": "ALL", "qt-ph-k-moi": "moi",
             "qt-ph-k-dang": "dang_xu_ly", "qt-ph-k-xong": "da_xu_ly"}
        return m.get(ctx.triggered_id, "ALL")

    @cb(Output("qt-ph-grid", "dashGridOptions"), Input("qt-ph-tim", "value"), prevent_initial_call=True)
    def _tim_ph(chu):
        p = Patch()
        p["quickFilterText"] = chu or ""
        return p

    @cb(Output("qt-ph-kpi", "children"), Output("qt-ph-grid", "rowData"),
        Input("qt-tab", "value"), Input("qt-ph-loc-tt", "data"),
        Input("qt-ph-loc-loai", "value"), Input("qt-ph-msg", "children"),
        Input("ph-cap-nhat", "data"))
    def _nap_ds_ph(tab, loc_tt, loc_loai, *_):
        if tab != "phanhoi":
            return no_update, no_update
        rows = danh_sach_phan_hoi()
        n_all = len(rows)
        n_moi = sum(1 for r in rows if r["trang_thai"] == "moi")
        n_dang = sum(1 for r in rows if r["trang_thai"] == "dang_xu_ly")
        n_xong = sum(1 for r in rows if r["trang_thai"] == "da_xu_ly")
        tt = loc_tt or "ALL"
        the_kpi = [
            html.Button(kpi("Tổng phản hồi", f"{n_all}", "Toàn bộ góp ý đã gửi"),
                        id="qt-ph-k-all", className="kpi-bam" + (" dang-chon" if tt == "ALL" else "")),
            html.Button(kpi("Mới chờ xử lý", f"{n_moi}", "Cần kiểm tra & phản hồi", "bad" if n_moi else "ok"),
                        id="qt-ph-k-moi", className="kpi-bam" + (" dang-chon" if tt == "moi" else "")),
            html.Button(kpi("Đang xử lý", f"{n_dang}", "Đang kiểm tra / khắc phục", "warn" if n_dang else ""),
                        id="qt-ph-k-dang", className="kpi-bam" + (" dang-chon" if tt == "dang_xu_ly" else "")),
            html.Button(kpi("Đã xử lý", f"{n_xong}", "Đã hoàn tất cập nhật", "ok"),
                        id="qt-ph-k-xong", className="kpi-bam" + (" dang-chon" if tt == "da_xu_ly" else "")),
        ]
        if tt != "ALL":
            rows = [r for r in rows if r["trang_thai"] == tt]
        if loc_loai and loc_loai != "ALL":
            rows = [r for r in rows if r["loai"] == loc_loai]
        return the_kpi, rows

    @cb(Output("qt-modal-ph", "className"), Output("qt-ph-tieu-de", "children"),
        Output("qt-ph-dang-sua", "data"), Output("qt-ph-chi-tiet", "children"),
        Output("qt-ph-trangthai", "value"), Output("qt-ph-ghichu", "value"),
        Output("qt-modal-ph-msg", "children", allow_duplicate=True),
        Input("qt-ph-grid", "cellClicked"), Input("qt-ph-grid", "cellDoubleClicked"),
        Input("qt-modal-ph-dong", "n_clicks"), Input("qt-modal-ph-huy", "n_clicks"),
        Input("qt-ph-msg", "children"), prevent_initial_call=True)
    def _mo_modal_ph(bam, bam_dup, *_):
        giu = (no_update,) * 6
        if ctx.triggered_id == "qt-ph-grid":
            id_ = dong_can_sua(bam, bam_dup)
            r = lay_phan_hoi(int(id_)) if str(id_ or "").isdigit() else None
            if not r:
                return (no_update,) + giu
            ct = html.Div([
                html.Div([html.B("Người gửi: "), r["nguoi_gui"], " · ", r["vai_tro_phong"]]),
                html.Div([html.B("Thời điểm gửi: "), r["tao_luc"], " · ",
                          html.B("Phân loại: "), f"{r['loai']} → {r['muc']}"]),
                html.Div(r["noi_dung"], className="ph-ct-noidung"),
            ], className="ph-ct-khung")
            return ("modal mo", f"Phản hồi #{r['id']} · {r['muc']}", r["id"],
                    ct, r["trang_thai"], r["ghi_chu_admin"], "")
        return ("modal",) + giu

    @cb(Output("qt-ph-xacnhan-xoa", "displayed"), Output("qt-ph-xacnhan-xoa", "message"),
        Input("qt-ph-btn-xoa", "n_clicks"), State("qt-ph-grid", "selectedRows"),
        prevent_initial_call=True)
    def _hoi_xoa_ph(_n, chon):
        if not chon:
            return False, ""
        return True, f"Xoá {len(chon)} phản hồi đã chọn? Thao tác này không hoàn tác được."

    @cb(Output("qt-ph-msg", "children"), Output("qt-modal-ph-msg", "children"),
        Input("qt-modal-ph-ok", "n_clicks"), Input("qt-ph-btn-xong", "n_clicks"),
        Input("qt-ph-xacnhan-xoa", "submit_n_clicks"),
        State("qt-ph-dang-sua", "data"), State("qt-ph-trangthai", "value"),
        State("qt-ph-ghichu", "value"), State("qt-ph-grid", "selectedRows"),
        prevent_initial_call=True)
    def _thao_tac_ph(_ok, _xong, _xoa, id_sua, tt, ghichu, chon):
        trig = ctx.triggered_id
        if trig == "qt-modal-ph-ok" and id_sua:
            ok, msg = cap_nhat_phan_hoi(int(id_sua), tt, ghichu, current_user.username)
            return (alert(msg, "ok"), "") if ok else (no_update, alert(msg, "bad"))
        ids = [int(r["id"]) for r in (chon or []) if str(r.get("id") or "").isdigit()]
        if trig == "qt-ph-btn-xong":
            if not ids:
                return alert("Tích chọn ít nhất một dòng phản hồi trong bảng trước.", "warn"), no_update
            n = danh_dau_da_xu_ly(ids, current_user.username)
            return alert(f"Đã đánh dấu hoàn tất {n} phản hồi.", "ok"), no_update
        if trig == "qt-ph-xacnhan-xoa" and ids:
            n = xoa_phan_hoi(ids, current_user.username)
            return alert(f"Đã xoá {n} phản hồi.", "ok"), no_update
        return no_update, no_update
