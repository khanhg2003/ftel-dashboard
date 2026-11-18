"""Trang Điều hành liên khối (nhánh thi-lien-khoi): sự kiện của các khối theo mã hợp đồng -> luật -> việc giao đúng người -> Zalo -> theo dõi.

Bốn tab: Việc cần làm (kết quả các luật), Theo dõi & Zalo (giao việc, nhắc, báo quản lý, trạng thái từng việc: `lienkhoi_td.py`),
Hồ sơ hợp đồng (mọi thứ ba khối biết về một hợp đồng: `lienkhoi_hs.py`), Nguồn dữ liệu (khối nào đã nối, khớp nhau tới đâu).
Chỉ Quản trị xem (bản thử). Mọi callback kiểm quyền ở máy chủ; không có tên khách hàng ở bất kỳ đâu trên trang.
"""
from __future__ import annotations

import pandas as pd

from dash import ALL, Input, Output, ctx, dcc, html
from dash.exceptions import PreventUpdate
from flask_login import current_user

from app.lien_khoi import ho_so as hs
from app.lien_khoi import luat, nguon, su_kien as sk
from app.ui.components import alert, callback_can_quyen, card, ghi_chu, kpi, seg_control
from app.ui.icons import icon
from app.ui.luoi import bang
from app.ui.pages import lienkhoi_hq, lienkhoi_hs, lienkhoi_td, lienkhoi_tl, lienkhoi_tq, phanloai

QUYEN = "duoc_cau_hinh"
TAB = [("tongquan", "Dashboard"), ("pl", "Phân loại khách hàng"), ("viec", "Việc cần làm"), ("td", "Theo dõi & Zalo"), ("hq", "Hiệu quả"), ("tl", "Trợ lý điều hành"), ("hd", "Hồ sơ hợp đồng"), ("nguon", "Nguồn dữ liệu")]
MUC_MAU = {"styleConditions": [{"condition": "params.value == 'Cao'", "style": {"color": "#b42318", "fontWeight": 600}},
                               {"condition": "params.value == 'Trung bình'", "style": {"color": "#b54708", "fontWeight": 600}}]}
COT_VIEC = [
    {"headerName": "Mã HĐ", "field": "so_hd", "width": 120, "pinned": "left", "cellClass": "o-bam"},
    {"headerName": "Luật", "field": "ten_luat", "width": 150},
    {"headerName": "Mức", "field": "muc", "width": 100, "cellStyle": MUC_MAU},
    {"headerName": "Giao sale", "field": "giao_sale", "width": 180},
    {"headerName": "Giao DVKH", "field": "giao_dvkh", "width": 190},
    {"headerName": "Giao Kỹ thuật", "field": "giao_kt", "width": 220},
    {"headerName": "Phát sinh", "field": "phat_sinh", "width": 110},
    {"headerName": "Hạn", "field": "han", "width": 120},
    {"headerName": "Lý do (dẫn chứng)", "field": "ly_do", "minWidth": 340, "flex": 2, "wrapText": True, "autoHeight": True},
    {"headerName": "Đề xuất hành động", "field": "de_xuat", "minWidth": 260, "flex": 1, "wrapText": True, "autoHeight": True},
]
GHI_CHU_THU = ("Bản thử của hướng điều hành liên khối. Ba khối lấy từ các chi nhánh khác nhau nên số hợp đồng trùng nhau giữa các khối còn ít.",
               "Khi cùng dùng một mã hợp đồng thì các luật chạy luôn, không phải viết lại.",
               "Khối Kỹ thuật chưa có nguồn nên việc cần Kỹ thuật tạm vào hàng chờ.")
GHI_CHU_DEMO = ("Dữ liệu MINH HOẠ đã ghép mã: mã hợp đồng, tên nhân sự và ngày tháng là giả định để minh hoạ ba khối cùng một mã.",
                "Phần khối Kỹ thuật dựng từ file báo cáo Kỹ thuật thật nhưng đã đổi hết mã và tên. Không có tên khách hàng. Tin Zalo chỉ được GIẢ LẬP, không gửi ra ngoài.")


def _duoc_xem() -> bool:
    return bool(getattr(current_user, "is_authenticated", False)) and bool(getattr(current_user, QUYEN, False))


def thanh_du_lieu() -> list:
    """Dòng tình trạng dữ liệu trên thanh tiêu đề của trang liên khối (không dùng dòng của khối Kinh doanh: dữ liệu minh hoạ không nằm trong database)."""
    if nguon.la_demo():
        ngay = nguon.ngay_tham_chieu()
        return [html.Span([icon("database", 13), html.Span(f"Minh hoạ · tới {ngay:%d/%m}" if ngay is not None else "Minh hoạ")], className="badge muted thanh-dl",
                          title="Bộ dữ liệu minh hoạ đã ghép mã: mã hợp đồng, tên người và ngày tháng là giả định")]
    return [html.Span([icon("database", 13), html.Span("Dữ liệu thật · chỉ đọc")], className="badge muted thanh-dl")]


def topbar():
    return [html.Div([html.H1("Điều hành liên khối"), html.Div("Sự kiện ba khối theo mã hợp đồng, luật, giao việc qua Zalo và theo dõi kết quả", className="sub")])]


def _ngay(t, gio: bool = False) -> str:
    return "" if pd.isna(t) else pd.Timestamp(t).strftime("%d/%m/%Y %H:%M" if gio else "%d/%m/%Y")


def layout(tab: str | None = None, ql: str | None = None):
    """`tab` và `ql` lấy từ đường dẫn (?tab=td&ql=tpkd_01): mở thẳng tab và chọn sẵn quản lý (đường dẫn trong tin Zalo)."""
    if not _duoc_xem():
        return alert("Chỉ tài khoản Quản trị xem được trang này.", "bad")
    luat_opt = [{"label": "Tất cả luật", "value": "all"}] + [{"label": v, "value": k} for k, v in luat.TEN_LUAT.items()]
    an = {"display": "none"}
    return html.Div([
        alert(" ".join(GHI_CHU_DEMO), "warn") if nguon.la_demo() else ghi_chu(" ".join(GHI_CHU_THU), "Bản thử"),
        html.Div(seg_control("lk-tab", TAB, tab if tab in {k for k, _ in TAB} else "tongquan"), style={"margin": "10px 0 14px"}),
        html.Div(lienkhoi_tq.layout(), id="lk-tongquan"),
        html.Div(phanloai.layout(), id="lk-pl", style=an),
        html.Div([
            html.Div(id="lk-kpi", className="kpi-row kpi-6"),
            card([
                html.Div([html.Label("Luật", style={"marginRight": "8px"}),
                          dcc.Dropdown(id="lk-luat", options=luat_opt, value="all", clearable=False, style={"width": "240px"})],
                         style={"display": "flex", "alignItems": "center", "marginBottom": "10px"}),
                bang("lk-luoi-viec", COT_VIEC, cao=560),
            ], title="Việc cần làm", desc="Mỗi dòng là một việc: ai nhận, vì sao. Người nhận chưa biết thì ghi tên hàng chờ. Mức Cao xếp trước."),
        ], id="lk-viec", style=an),
        html.Div(lienkhoi_td.layout(ql), id="lk-td", style=an),
        html.Div(lienkhoi_hq.layout(), id="lk-hq", style=an),
        html.Div(lienkhoi_tl.layout(), id="lk-tl", style=an),
        html.Div([
            html.Div([dcc.Input(id="lk-hd-ma", type="text", debounce=True, className="inp", style={"width": "260px"}, placeholder="Gõ mã hợp đồng rồi Enter")],
                     style={"marginBottom": "12px"}),
            html.Div(id="lk-hd-noi-dung"),
        ], id="lk-hd", style=an),
        html.Div(id="lk-nguon", style=an),
    ])


def _viec_dong(v: pd.DataFrame) -> list[dict]:
    d = v.copy()
    d["phat_sinh"] = d["phat_sinh"].map(_ngay)
    return d.to_dict("records")


def _nguon_noi_dung():
    tt, kh = sk.trang_thai_nguon(), sk.khop_giua_khoi()
    the = []
    for s in tt:
        if s["co_nguon"]:
            dong = [html.Div(f"{s['so_hd']:,} hợp đồng · {s['so_su_kien']:,} sự kiện".replace(",", "."), className="desc"),
                    html.Div(f"Từ {_ngay(s['tu'])} đến {_ngay(s['den'])}", className="desc")]
        else:
            dong = [html.Div("Chưa có nguồn. Khi có file Kỹ thuật theo mã hợp đồng thì cho `nguon.kt()` đọc file đó là cắm được, luật và giao diện không đổi.",
                             className="desc")]
        the.append(card(dong, title=s["ten"] + (" · đã nối" if s["co_nguon"] else " · chưa có nguồn")))
    khop = [("Kinh doanh và DVKH cùng có", kh["kd_dvkh"]), ("Kinh doanh và Kỹ thuật cùng có", kh["kd_kt"]),
            ("DVKH và Kỹ thuật cùng có", kh["dvkh_kt"]), ("Cả ba khối cùng có", kh["ca_ba"])]
    che_do = (alert("Đang dùng bộ dữ liệu MINH HOẠ đã ghép mã (biến LIEN_KHOI_NGUON=demo).", "warn") if nguon.la_demo()
              else alert("Đang dùng dữ liệu thật có trong máy (chỉ đọc, không ghi).", "info"))
    return html.Div([che_do, html.Div(the, style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(260px, 1fr))", "gap": "14px"}),
                     card([html.Div([html.B(f"{n:,}".replace(",", ".")), f"  hợp đồng · {ten}"], style={"marginBottom": "4px"}) for ten, n in khop],
                          title="Số hợp đồng khớp giữa các khối",
                          desc="Khớp bằng mã hợp đồng. Số nhỏ vì mỗi khối đang lấy từ chi nhánh hoặc khoảng ngày khác nhau, không phải do lệch mã.")])


def _goi_y():
    chip = [html.Button(m, id={"type": "lk-hd-chon", "index": m}, n_clicks=0, className="btn") for m in hs.hop_dong_goi_y()]
    return html.Div([html.Div("Gõ một mã hợp đồng ở ô trên, hoặc bấm một hợp đồng tiêu biểu (mỗi luật vài hợp đồng):", className="lk-ghi-chu"),
                     html.Div(chip, className="lk-badges", style={"marginTop": "8px"})], className="lk-trong")


def register(app):
    cb = callback_can_quyen(app, QUYEN)
    lienkhoi_td.register(app)
    lienkhoi_hq.register(app)
    lienkhoi_tl.register(app)
    lienkhoi_tq.register(app)
    phanloai.register(app)

    @cb(Output("lk-tab", "value"), Output("lk-hd-ma", "value", allow_duplicate=True), Input("lk-luoi-viec", "cellClicked"), prevent_initial_call=True)
    def _mo_ho_so(cell):
        if not cell or cell.get("colId") != "so_hd":
            raise PreventUpdate
        return "hd", cell["value"]

    @cb(Output("lk-tongquan", "style"), Output("lk-pl", "style"), Output("lk-viec", "style"), Output("lk-td", "style"), Output("lk-hq", "style"), Output("lk-tl", "style"), Output("lk-hd", "style"), Output("lk-nguon", "style"), Input("lk-tab", "value"))
    def _hien(tab):
        an, hien = {"display": "none"}, {"display": "block"}
        return tuple(hien if tab == k else an for k in ("tongquan", "pl", "viec", "td", "hq", "tl", "hd", "nguon"))

    @cb(Output("lk-kpi", "children"), Output("lk-luoi-viec", "rowData"), Input("lk-tab", "value"), Input("lk-luat", "value"))
    def _viec(tab, ma_luat):
        if tab != "viec":
            raise PreventUpdate
        v = luat.danh_sach_viec()
        tt = luat.tom_tat(v)
        n = tt["theo_luat"]
        ks = [kpi("Tổng việc", f"{tt['tong']:,}".replace(",", "."), f"{tt['hang_cho_dvkh']} việc chưa biết người DVKH (vào hàng chờ)"),
              kpi("Mức Cao", f"{tt['cao']:,}".replace(",", "."), "Nên xử lý trước", trang_thai="bad" if tt["cao"] else ""),
              kpi(luat.TEN_LUAT["cho_online"], n.get("cho_online", 0), "Chưa online sau 2 ngày kể từ ngày tạo"),
              kpi(luat.TEN_LUAT["loi_som"], n.get("loi_som", 0), "Online xong 30 ngày đã có SR khiếu nại hoặc checklist"),
              kpi(luat.TEN_LUAT["su_co_lap"], n.get("su_co_lap", 0), "Kỹ thuật ghi checklist lặp từ 2 lần"),
              kpi(luat.TEN_LUAT["co_y_roi"], n.get("co_y_roi", 0), "Nói không ở lại, đang suy nghĩ hoặc điểm nguy cơ cao")]
        if ma_luat and ma_luat != "all":
            v = v[v["luat"] == ma_luat]
        return ks, _viec_dong(v)

    @cb(Output("lk-hd-noi-dung", "children"), Input("lk-tab", "value"), Input("lk-hd-ma", "value"))
    def _hop_dong(tab, ma):
        if tab != "hd":
            raise PreventUpdate
        if not (ma or "").strip():
            return _goi_y()
        h = hs.ho_so(ma)
        if h is None:
            return alert(f"Không có sự kiện nào cho mã {ma.strip().upper()} ở các khối đã nối.", "warn")
        return lienkhoi_hs.noi_dung(h)

    @cb(Output("lk-hd-ma", "value"), Input({"type": "lk-hd-chon", "index": ALL}, "n_clicks"), prevent_initial_call=True)
    def _chon(clicks):
        if not any(clicks or []) or not isinstance(ctx.triggered_id, dict):
            raise PreventUpdate
        return ctx.triggered_id["index"]

    @cb(Output("lk-nguon", "children"), Input("lk-tab", "value"))
    def _nguon(tab):
        if tab != "nguon":
            raise PreventUpdate
        return _nguon_noi_dung()
