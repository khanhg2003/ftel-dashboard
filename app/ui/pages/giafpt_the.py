"""Tab "Tra giá" của Tra cứu giá: chọn MỘT nhóm bằng các nút tròn (như trang gói cước của fpt.vn), nhóm đó hiện thành THẺ, bấm cả thẻ để xem
chi tiết (chủ app chốt 22/10/2026: mỗi lần chỉ một nhóm cho đỡ rối). Riêng "Internet · cá nhân" có thêm hàng nút nhỏ lọc tiếp theo nhu cầu
(Wifi 7, gia đình, game thủ, combo Internet + Camera) - cách chia lấy từ các trang /internet/... của fpt.vn, xem `gia_fpt.PHAN_LOAI_CON`.

Điều kiện giống hệt nhau ở mọi gói của nhóm (cách thanh toán, số tháng tặng, phí hòa mạng dùng chung, hạn chính sách...) nằm ở dải "Chính sách
chung" dưới tiêu đề; trên thẻ và trong chi tiết chỉ ghi chỗ KHÁC (`gia_fpt.phan_chung` / `khac_biet`), riêng phí hòa mạng luôn ghi trên thẻ.
Ba bước để trang hiện nhanh: `_tra` lấy danh sách gói (một lần gọi) và dựng nút nhóm; `_chi_tiet` nạp chi tiết CẢ phường song song (lần đầu ~5 giây,
sau đó đã nhớ tạm) vào Store `gf-ctd`; `_ds` vẽ nhóm đang chọn từ hai thứ trên, vẽ lại khi chi tiết về hoặc khi đổi nút.
Store `gf-ctd` mang khoá phường (`pha`) để kết quả của phường cũ về muộn không đè lên phường mới.
"""
from __future__ import annotations

from dash import Input, Output, State, ctx, dcc, html
from dash.exceptions import PreventUpdate

from app import gia_fpt as gf
from app.bo_nho import xoa
from app.thoi_gian import chu_gio_vn
from app.ui.components import alert, ghi_chu
from app.ui.icons import icon

KHOA_MAC_DINH = "Internet|ca_nhan"
KHOA_CAMERA = "Internet + Camera An Tâm|ca_nhan"       # không có nút riêng: nằm trong nút nhỏ "Combo Internet + Camera" của Internet · cá nhân


def pane():
    from app.ui.pages.giafpt import chon_khu_vuc
    return html.Div([
        html.Div([*chon_khu_vuc("gf"), html.Div(className="grow"), html.Span(id="gf-luc", className="gf-luc"),
                  html.Button([icon("refresh", 14), html.Span("Làm mới giá")], id="gf-moi", className="btn nt-nut",
                              title="Bỏ giá đang nhớ tạm và hỏi lại fpt.vn")], className="toolbar"),
        html.Div(id="gf-tb"),
        dcc.RadioItems(id="gf-muc", options=[], value=None, className="gf-pills", labelClassName="gf-pill", inputClassName="gf-pill-in"),
        dcc.RadioItems(id="gf-con", options=[], value="all", className="gf-pills gf-pills-con", labelClassName="gf-pill", inputClassName="gf-pill-in",
                       style={"display": "none"}),
        html.Div(id="gf-ds", className="gf-ds"),
        ghi_chu("Giá là giá niêm yết trên website fpt.vn cho đúng phường đang chọn, đã gồm VAT. Chọn khác phường thì giá và danh sách gói có thể khác.",
                style={"margin": "8px 0 0"}),
        dcc.Store(id="gf-pha"), dcc.Store(id="gf-ctd"),
    ], id="gf-pane-tra")


# ------------------------------------------------------------------ dựng thẻ
def _toc_do(chu: str | None):
    if not chu:
        return "–"
    xuong, _, len_ = chu.partition(" / ")
    return html.Span([html.Span([html.Span("↓", className="gf-mui"), xuong]), html.Span([html.Span("↑", className="gf-mui"), len_])] if len_ else [xuong],
                     className="gf-toc-do", title="Tốc độ tải xuống / tải lên")


def _dong(nhan: str, gia_tri, lop: str = ""):
    return [html.Span(nhan, className="gf-fk"), html.Span(gia_tri, className=f"gf-fv {lop}".strip())]


def _the(g: dict, kb: dict, ct: dict | None, re_nhat: bool):
    """Thẻ có cấu trúc CỐ ĐỊNH để các thẻ cùng nhóm nhìn so được: tên, giá, rồi các dòng Tốc độ / Phí hòa mạng / Kết nối / Thiết bị, ưu đãi cuối."""
    fact = _dong("Tốc độ", _toc_do(g["toc_do"]))
    if g["nhom"] != "Camera":
        phi = gf.chu_phi_hoa_mang(ct)
        fact += _dong("Phí hòa mạng", phi or "…", "gf-fv-xanh" if phi == "Miễn phí" else ("gf-fv-cho" if not phi else "gf-fv-phi"))
    if g["thiet_bi"]:
        fact += _dong("Kết nối", f"{g['thiet_bi']} thiết bị")
    if ct and ct["thiet_bi"] and g["nhom"] != "Camera":
        fact += _dong("Thiết bị đi kèm", gf.chu_khoang(ct["thiet_bi"]))
    uu_dai = kb.get("uu_dai", "") if kb else g["uu_dai"]
    gia = f"{g['gia']:,.0f}".replace(",", ".") if g["gia"] else "–"
    return html.Button([
        html.Div([html.Div(g["ten"], className="gf-the-ten"),
                  html.Span("Rẻ nhất", className="gf-nhan gf-nhan-re") if re_nhat else (html.Span(g["nhan"], className="gf-nhan") if g["nhan"] else None)],
                 className="gf-the-dau"),
        html.Div([html.Span(gia, className="gf-gia"), html.Span("đ", className="gf-dong"),
                  html.Span(gf.DON_VI_GIA.get(g["nhom"], "/ tháng"), className="gf-dv")], className="gf-the-gia"),
        html.Div(fact, className="gf-facts"),
        html.Div(uu_dai, className="gf-uu-dai") if uu_dai else None,
        html.Div([html.Span("Xem chi tiết"), html.Span("›", className="gf-mui-xem")], className="gf-the-xem"),
    ], id={"type": "gf-the", "code": g["code"], "gia": g["gia"] or 0, "khoa": gf.khoa_nhom(g)}, n_clicks=0, className="gf-the")


def _muc(khoa: str, goi: list[dict], chung: dict | None, ct: dict | None, tieu: str | None = None):
    """Nhóm đang xem: tiêu đề + dải chính sách chung + lưới thẻ. chung / ct là None khi chi tiết chưa nạp xong."""
    re = min((g["gia"] for g in goi if g["gia"]), default=None) if len(goi) >= 3 else None
    the = []
    for g in goi:
        c = (ct or {}).get(g["code"])
        the.append(_the(g, gf.khac_biet(g, c, chung or {}), c, re is not None and g["gia"] == re and sum(1 for x in goi if x["gia"] == re) == 1))
    if chung is None:
        dai = html.Div("Đang nạp chính sách chung của nhóm (phí hòa mạng, cách thanh toán, hạn chính sách)…", className="gf-chung gf-cho")
    else:
        dong = gf.dong_chung(chung)
        dai = html.Div([html.Span("Chính sách chung", className="gf-chung-nhan"),
                        html.Ul([html.Li(d) for d in dong])], className="gf-chung") if dong else None
    return html.Div([html.Div(html.H3(tieu or gf.tieu_de_nhom(khoa)), className="gf-muc-dau"), dai, html.Div(the, className="gf-luoi-the")], className="gf-muc")


def _nhom(goi: list[dict]) -> dict[str, list[dict]]:
    ra: dict = {}
    for g in goi:
        ra.setdefault(gf.khoa_nhom(g), []).append(g)
    return ra


def _nut_nhom(goi: list[dict]) -> list[dict]:
    return [{"label": f"{gf.tieu_de_nhom(k)} ({len(v)})", "value": k} for k, v in _nhom(goi).items() if k != KHOA_CAMERA]


def _nut_con(goi: list[dict]) -> list[dict]:
    """Nút nhỏ của Internet · cá nhân: Tất cả + các nhu cầu có ít nhất một gói."""
    ca_nhan = [g for g in goi if gf.khoa_nhom(g) == KHOA_MAC_DINH]
    ra = [{"label": f"Tất cả ({len(ca_nhan)})", "value": "all"}]
    for ma, nhan in gf.PHAN_LOAI_CON:
        n = len(_goi_con(goi, ma))
        if n:
            ra.append({"label": f"{nhan} ({n})", "value": ma})
    return ra


def _goi_con(goi: list[dict], ma: str) -> list[dict]:
    """Gói của một nút nhỏ. "Combo Internet + Camera" lấy nhóm An Tâm; các nút khác lọc trong Internet · cá nhân theo `gia_fpt.thuoc_con`."""
    if ma == "camera":
        return [g for g in goi if gf.khoa_nhom(g) == KHOA_CAMERA]
    return [g for g in goi if gf.khoa_nhom(g) == KHOA_MAC_DINH and gf.thuoc_con(g, ma)]


# ------------------------------------------------------------------ callbacks
def register(app):
    from app.ui.pages.giafpt import _canh_bao, _loi, _vao

    @app.callback(Output("gf-tb", "children"), Output("gf-luc", "children"), Output("gf-muc", "options"), Output("gf-muc", "value"),
                  Output("gf-ctd", "data"), Output("gf-pha", "data"),
                  Input("gf-tab", "value"), Input("gf-tinh", "value"), Input("gf-phuong", "value"), Input("gf-moi", "n_clicks"),
                  State("gf-muc", "value"))
    def _tra(tab, tinh, phuong, _moi, muc):
        _vao()
        if tab != "tra":
            raise PreventUpdate
        if not tinh or not phuong:
            return alert("Chọn tỉnh / thành và phường / xã ở trên để xem giá.", "info"), "", [], None, None, None
        if ctx.triggered_id == "gf-moi":
            xoa("gia_fpt")
        try:
            kq = gf.goi_theo_phuong(tinh, phuong)
        except gf.LoiGia as e:
            return _loi(e), "", [], None, None, None
        nut = _nut_nhom(kq["goi"])
        co = {n["value"] for n in nut}
        chon = muc if muc in co else (KHOA_MAC_DINH if KHOA_MAC_DINH in co else (nut[0]["value"] if nut else None))
        return (_canh_bao(kq), f"Giá lấy lúc {chu_gio_vn(kq['luc'], '%H:%M')}", nut, chon, None,
                {"tinh": tinh, "phuong": phuong, "luc": kq["luc"].isoformat(), "khoa": f"{tinh}-{phuong}"})

    @app.callback(Output("gf-con", "options"), Output("gf-con", "value"), Output("gf-con", "style"),
                  Input("gf-muc", "value"), Input("gf-pha", "data"), State("gf-con", "value"))
    def _con(khoa, pha, con):
        """Hàng nút nhỏ chỉ hiện khi đang xem Internet · cá nhân."""
        _vao()
        if khoa != KHOA_MAC_DINH or not pha:
            return [], "all", {"display": "none"}
        try:
            nut = _nut_con(gf.goi_theo_phuong(pha["tinh"], pha["phuong"])["goi"])
        except gf.LoiGia:
            raise PreventUpdate
        return nut, (con if con in {n["value"] for n in nut} else "all"), {}

    @app.callback(Output("gf-ctd", "data", allow_duplicate=True), Input("gf-pha", "data"), prevent_initial_call=True)
    def _chi_tiet(pha):
        """Nạp chi tiết cả phường (một lần, song song) rồi tính điều kiện chung từng nhóm; chỉ giữ phần thẻ cần để nhẹ."""
        _vao()
        if not pha:
            raise PreventUpdate
        try:
            kq = gf.goi_theo_phuong(pha["tinh"], pha["phuong"])
        except gf.LoiGia:
            raise PreventUpdate
        ct = gf.chi_tiet_nhieu(pha["tinh"], pha["phuong"], kq["goi"])
        chung = {k: gf.phan_chung(v, ct) for k, v in _nhom(kq["goi"]).items()}
        gon = {code: {"phi_lap": c["phi_lap"], "thiet_bi": c["thiet_bi"]} for code, c in ct.items() if c}
        return {"pha": pha["khoa"], "ct": gon, "chung": chung}

    @app.callback(Output("gf-ds", "children"), Input("gf-muc", "value"), Input("gf-con", "value"), Input("gf-pha", "data"), Input("gf-ctd", "data"))
    def _ds(khoa, con, pha, ctd):
        _vao()
        if not khoa or not pha:
            return []
        try:
            tat_ca = gf.goi_theo_phuong(pha["tinh"], pha["phuong"])["goi"]
        except gf.LoiGia:
            raise PreventUpdate
        tieu = None
        if khoa == KHOA_MAC_DINH and con and con != "all":
            goi = _goi_con(tat_ca, con)
            tieu = f"Internet · cá nhân · {dict(gf.PHAN_LOAI_CON)[con]}"
            khoa = KHOA_CAMERA if con == "camera" else khoa
        else:
            goi = _nhom(tat_ca).get(khoa, [])
        co_ct = bool(ctd) and ctd.get("pha") == pha["khoa"]
        ct, chung = (ctd["ct"], ctd["chung"]) if co_ct else (None, None)
        return _muc(khoa, goi, (chung or {}).get(khoa, {}) if co_ct else None, ct, tieu)
