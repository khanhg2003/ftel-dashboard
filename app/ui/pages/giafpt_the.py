"""Tab "Tra giá" của Tra cứu giá: chọn MỘT nhóm bằng một hàng nút tròn (như trang gói cước của fpt.vn), nhóm đó hiện thành THẺ,
bấm cả thẻ để xem chi tiết (chủ app chốt 22/10/2026: mỗi lần chỉ một nhóm cho đỡ rối). Nhóm chia đúng như website (`gia_fpt_nhom`): một gói có
thể nằm ở nhiều nhóm nên số trên các nút không cần cộng ra tổng số gói. Mỗi lượt callback lấy cấu hình nhóm MỘT lần (`gia_fpt_nhom.cau_hinh`).

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
from app import gia_fpt_nhom as gn
from app.bo_nho import xoa
from app.thoi_gian import chu_gio_vn
from app.ui.components import alert, ghi_chu
from app.ui.icons import icon


def pane():
    from app.ui.pages.giafpt import chon_khu_vuc
    return html.Div([
        html.Div([*chon_khu_vuc("gf"), html.Div(className="grow"),
                  html.Div([html.Span(id="gf-luc", className="gf-luc"),
                            html.Button([icon("refresh", 14), html.Span("Làm mới giá")], id="gf-moi", className="btn nt-nut",
                                        title="Bỏ giá đang nhớ tạm và hỏi lại fpt.vn")], className="gf-moi-hang")], className="toolbar"),
        html.Div(id="gf-tb"),
        alert([icon("alert", 20),
               html.Div([html.Div("Lưu ý khi báo giá gói Internet tặng camera", className="gf-luu-y-dau"),
                         html.Div("Trong bảng giá không có giá gói Internet tặng camera. Hãy tính theo Combo Internet + V.VIP, cộng thêm 10.000đ - 20.000đ tùy khu vực.")])],
              "warn gf-luu-y"),
        dcc.RadioItems(id="gf-muc", options=[], value=None, className="gf-pills", labelClassName="gf-pill", inputClassName="gf-pill-in"),
        html.Div(id="gf-ds", className="gf-ds"),
        ghi_chu("Giá là giá niêm yết trên website fpt.vn cho đúng phường đang chọn, đã gồm VAT. Chọn khác phường thì giá và danh sách gói có thể khác.",
                style={"margin": "8px 0 0"}),
        dcc.Store(id="gf-pha"), dcc.Store(id="gf-ctd"),
    ], id="gf-pane-tra")


# ------------------------------------------------------------------ dựng thẻ
def _toc_do(chu: str):
    """Hai chiều chồng nhau (↓ trên, ↑ dưới); gói chỉ ghi một chiều thì một dòng."""
    xuong, _, len_ = chu.partition(" / ")
    return html.Span([html.Span([html.Span("↓", className="gf-mui"), xuong]), html.Span([html.Span("↑", className="gf-mui"), len_])] if len_ else [xuong],
                     className="gf-toc-do", title="Tốc độ tải xuống / tải lên")


def _dong(nhan: str, gia_tri, lop: str = ""):
    return [html.Span(nhan, className="gf-fk"), html.Div(gia_tri, className=f"gf-fv {lop}".strip())]


def _the(g: dict, kb: dict, ct: dict | None, re_nhat: bool, dang_nap: bool = False):
    """Thẻ có cấu trúc CỐ ĐỊNH để các thẻ cùng nhóm nhìn so được: tên, giá, rồi các dòng Tốc độ / Phí hòa mạng / Kết nối / Thiết bị, ưu đãi cuối.
    Id thẻ chỉ mang mã gói (ASCII): tên nhóm có chữ "â" bị Dash thoát ký tự khác với chữ trình duyệt gửi lên, callback mở chi tiết sẽ không nhận ra thẻ.
    Phí hòa mạng: `dang_nap` = chi tiết cả phường chưa về ("…"); đã về mà gói này không có chi tiết thì "Chưa rõ", không bao giờ suy ra miễn phí."""
    fact = _dong("Tốc độ", _toc_do(g["toc_do"])) if g["toc_do"] else []
    phi = gf.dong_phi(ct) if ct else ([] if dang_nap else ["Chưa rõ"])
    lop = "gf-fv-xanh" if phi == ["Miễn phí"] else ("gf-fv-cho" if phi in ([], ["Chưa rõ"]) else "gf-fv-phi")
    fact += _dong("Phí hòa mạng", [html.Div(d) for d in phi] if phi else "…", lop)
    if g["thiet_bi"]:
        fact += _dong("Kết nối", f"{g['thiet_bi']} thiết bị")
    if ct and ct["thiet_bi"]:
        fact += _dong("Thiết bị đi kèm", gf.chu_khoang(ct["thiet_bi"]))
    uu_dai = kb.get("uu_dai", "") if kb else g["uu_dai"]
    gia = f"{g['gia']:,.0f}".replace(",", ".") if g["gia"] else "–"
    return html.Button([
        html.Div([html.Div(g["ten"], className="gf-the-ten", title=g["ten"]),
                  html.Span("Rẻ nhất", className="gf-nhan gf-nhan-re") if re_nhat else (html.Span(g["nhan"], className="gf-nhan") if g["nhan"] else None)],
                 className="gf-the-dau"),
        html.Div([html.Span(gia, className="gf-gia"), html.Span("đ", className="gf-dong"),
                  html.Span("/ tháng", className="gf-dv")], className="gf-the-gia"),
        html.Div(fact, className="gf-facts"),
        html.Div(uu_dai, className="gf-uu-dai") if uu_dai else None,
        html.Div([html.Span("Xem chi tiết"), html.Span("›", className="gf-mui-xem")], className="gf-the-xem"),
    ], id={"type": "gf-the", "code": g["code"]}, n_clicks=0, className="gf-the")


def _muc(nhom: str, goi: list[dict], chung: dict | None, ct: dict | None):
    """Nhóm đang xem: tiêu đề + dải chính sách chung + lưới thẻ. chung / ct là None khi chi tiết chưa nạp xong."""
    re = min((g["gia"] for g in goi if g["gia"]), default=None) if len(goi) >= 3 else None
    the = []
    for g in goi:
        c = (ct or {}).get(g["code"])
        the.append(_the(g, gf.khac_biet(g, c, chung or {}), c, re is not None and g["gia"] == re and sum(1 for x in goi if x["gia"] == re) == 1,
                        ct is None))
    if chung is None:
        dai = html.Div("Đang nạp chính sách chung của nhóm (phí hòa mạng, cách thanh toán, hạn chính sách)…", className="gf-chung gf-cho")
    else:
        dong = gf.dong_chung(chung)
        dai = html.Div([html.Span("Chính sách chung", className="gf-chung-nhan"),
                        html.Ul([html.Li(d) for d in dong])], className="gf-chung") if dong else None
    return html.Div([html.Div(html.H3(nhom), className="gf-muc-dau"), dai, html.Div(the, className="gf-luoi-the")], className="gf-muc")


def _nut_nhom(goi: list[dict], ch: dict) -> list[dict]:
    """Một nút cho mỗi nhóm CÓ gói, theo thứ tự của website, nhãn "Tên (số gói)"."""
    return [{"label": f"{n} ({len(v)})", "value": n} for n, v in gf.theo_nhom(goi, ch).items()]


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
        ch = gn.cau_hinh()
        nut = _nut_nhom(kq["goi"], ch)
        co = {n["value"] for n in nut}
        chon = muc if muc in co else (gf.NHOM_MAC_DINH if gf.NHOM_MAC_DINH in co else (nut[0]["value"] if nut else None))
        return (_canh_bao(kq), f"Giá lấy lúc {chu_gio_vn(kq['luc'], '%H:%M')}" + (" · nhóm theo danh sách lưu sẵn" if ch["nguon"] == "luu_san" else ""), nut, chon, None,
                {"tinh": tinh, "phuong": phuong, "luc": kq["luc"].isoformat(), "khoa": f"{tinh}-{phuong}"})

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
        chung = {k: gf.phan_chung(v, ct) for k, v in gf.theo_nhom(kq["goi"], gn.cau_hinh()).items()}
        gon = {code: {"phi_nhom": c["phi_nhom"], "thiet_bi": c["thiet_bi"]} for code, c in ct.items() if c}
        return {"pha": pha["khoa"], "ct": gon, "chung": chung}

    @app.callback(Output("gf-ds", "children"), Input("gf-muc", "value"), Input("gf-pha", "data"), Input("gf-ctd", "data"))
    def _ds(nhom, pha, ctd):
        _vao()
        if not nhom or not pha:
            return []
        try:
            tat_ca = gf.goi_theo_phuong(pha["tinh"], pha["phuong"])["goi"]
        except gf.LoiGia:
            raise PreventUpdate
        co_ct = bool(ctd) and ctd.get("pha") == pha["khoa"]
        return _muc(nhom, gf.theo_nhom(tat_ca, gn.cau_hinh()).get(nhom, []), (ctd["chung"].get(nhom) or {}) if co_ct else None, ctd["ct"] if co_ct else None)
