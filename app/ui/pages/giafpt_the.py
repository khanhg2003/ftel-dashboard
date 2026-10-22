"""Tab "Tra giá" của Tra cứu giá: các gói hiện thành THẺ gom theo nhóm, bấm cả thẻ để xem chi tiết (chủ app chốt 22/10/2026).

Điều kiện giống hệt nhau ở mọi gói của một nhóm (cách thanh toán, số tháng tặng, phí lắp đặt, hạn chính sách...) được lôi ra thành một dải
"Chung cho cả nhóm" ngay dưới tiêu đề nhóm; trên thẻ và trong chi tiết chỉ ghi chỗ KHÁC (`gia_fpt.phan_chung` / `khac_biet`).
Dựng hai lượt để trang hiện nhanh: lượt một chỉ cần danh sách gói (một lần gọi), lượt hai nạp chi tiết song song cho cả phường rồi vẽ lại
kèm phần chung (lần đầu ~5 giây, sau đó đã nhớ tạm).
"""
from __future__ import annotations

from datetime import datetime

from dash import Input, Output, ctx, dcc, html
from dash.exceptions import PreventUpdate

from app import gia_fpt as gf
from app.bo_nho import xoa
from app.thoi_gian import chu_gio_vn
from app.ui.components import alert, field, ghi_chu, kpi
from app.ui.icons import icon


def pane():
    from app.ui.pages.giafpt import NHIEU_KHACH, NHIEU_NHOM, chon_khu_vuc
    return html.Div([
        html.Div([*chon_khu_vuc("gf"),
                  field("Khách hàng", dcc.Dropdown(id="gf-khach", options=NHIEU_KHACH, value=["ca_nhan"], multi=True, searchable=False,
                                                   placeholder="Tất cả", persistence=True, persistence_type="local", className="gf-dd gf-dd-nho")),
                  field("Nhóm sản phẩm", dcc.Dropdown(id="gf-nhom", options=NHIEU_NHOM, value=["Internet"], multi=True, searchable=False,
                                                      placeholder="Tất cả", closeOnSelect=False, persistence=True, persistence_type="local",
                                                      className="gf-dd gf-dd-nho gf-dd-nhieu")),
                  html.Div(className="grow"),
                  html.Button([icon("refresh", 14), html.Span("Làm mới giá")], id="gf-moi", className="btn nt-nut",
                              title="Bỏ giá đang nhớ tạm và hỏi lại fpt.vn")], className="toolbar"),
        html.Div(id="gf-tb"),
        html.Div(id="gf-the", className="kpi-row"),
        html.Div([html.Div([icon("zoom_in", 14), html.Span("Bấm vào một gói để xem chi tiết: giá theo cách thanh toán, phí hòa mạng và điểm riêng của gói")],
                           className="goi-y-bam"),
                  html.Div(className="grow"),
                  html.Span(id="gf-chep-ghi", className="desc", style={"margin": 0}),
                  html.Button([icon("copy", 14), html.Span("Copy bảng giá gửi khách")], id="gf-chep", n_clicks=0, className="btn nut-chep lon")],
                 className="gf-hang-chep"),
        html.Div(id="gf-ds", className="gf-ds"),
        ghi_chu("Giá là giá niêm yết trên website fpt.vn cho đúng phường đang chọn, đã gồm VAT. Chọn khác phường thì giá và danh sách gói có thể khác. "
                "Nút Copy lấy đúng các gói đang hiện (lọc theo khách hàng / nhóm sản phẩm rồi copy nếu chỉ cần một phần).", style={"margin": "8px 0 0"}),
        dcc.Store(id="gf-pha"), dcc.Store(id="gf-chung"),
    ], id="gf-pane-tra")


# ------------------------------------------------------------------ dựng thẻ
def _kpi(goi: list[dict], dang_hien: int, luc) -> list:
    def re_nhat(khach):
        ds = [g for g in goi if g["nhom"] == "Internet" and g["khach"] == khach and g["gia"]]
        g = min(ds, key=lambda x: x["gia"]) if ds else None
        return (gf.chu_tien(g["gia"]), g["ten"]) if g else ("–", "Khu vực này chưa có gói")
    cn, dn = re_nhat("ca_nhan"), re_nhat("doanh_nghiep")
    return [kpi("Gói đang bán ở phường này", f"{len(goi)}", f"Đang hiện {dang_hien} gói theo bộ lọc"),
            kpi("Internet cá nhân rẻ nhất", cn[0], cn[1]), kpi("Internet doanh nghiệp rẻ nhất", dn[0], dn[1]),
            kpi("Giá lấy lúc", chu_gio_vn(luc, "%H:%M"), "Từ fpt.vn, nhớ tạm 15 phút")]


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


def _muc(khoa: str, goi: list[dict], chung: dict | None, ct: dict | None):
    """Một nhóm: tiêu đề + dải điều kiện chung + lưới thẻ. chung / ct là None khi chi tiết chưa nạp xong (lượt một)."""
    re = min((g["gia"] for g in goi if g["gia"]), default=None) if len(goi) >= 3 else None
    the = []
    for g in goi:
        c = ct.get(g["code"]) if ct else None
        the.append(_the(g, gf.khac_biet(g, c, chung or {}), c, re is not None and g["gia"] == re and sum(1 for x in goi if x["gia"] == re) == 1))
    if chung is None:
        dai = html.Div("Đang nạp điều kiện chung của nhóm (phí hòa mạng, cách thanh toán, hạn chính sách)…", className="gf-chung gf-cho")
    else:
        dong = gf.dong_chung(chung)
        dai = html.Div([html.Span("Chung cho cả nhóm", className="gf-chung-nhan"),
                        html.Ul([html.Li(d) for d in dong])], className="gf-chung") if dong else None
    tu = min((g["gia"] for g in goi if g["gia"]), default=None)
    return html.Div([html.Div([html.H3(gf.tieu_de_nhom(khoa)), html.Span(f"{len(goi)} gói" + (f" · từ {gf.chu_tien(tu)}" if tu else ""), className="gf-muc-dem")],
                              className="gf-muc-dau"),
                     dai, html.Div(the, className="gf-luoi-the")], className="gf-muc")


def _nhom(goi: list[dict]) -> dict[str, list[dict]]:
    ra: dict = {}
    for g in goi:
        ra.setdefault(gf.khoa_nhom(g), []).append(g)
    return ra


def _ve(goi: list[dict], ct: dict | None):
    """(các nhóm đã dựng, phần chung của từng nhóm). ct=None: lượt một, chưa có chi tiết."""
    nhom = _nhom(goi)
    chung = {k: gf.phan_chung(v, ct) for k, v in nhom.items()} if ct is not None else None
    if not nhom:
        return html.Div("Không có gói nào theo bộ lọc này.", className="desc"), {}
    return [_muc(k, v, chung[k] if chung is not None else None, ct) for k, v in nhom.items()], (chung or {})


def _chep(khu_vuc: str, hien: list[dict], luc, chung: dict, ct: dict | None = None) -> tuple[str, str]:
    return gf.van_ban_bao_gia(khu_vuc, hien, luc, chung, ct), f"Sẽ copy {len(hien)} gói đang hiện"


# ------------------------------------------------------------------ callbacks
def register(app):
    from app.ui.pages.giafpt import _canh_bao, _loi, _vao, ten_khu_vuc

    @app.callback(Output("gf-tb", "children"), Output("gf-the", "children"), Output("gf-ds", "children"), Output("gf-chung", "data"),
                  Output("gf-chep", "data-chep"), Output("gf-chep-ghi", "children"), Output("gf-pha", "data"),
                  Input("gf-tab", "value"), Input("gf-tinh", "value"), Input("gf-phuong", "value"), Input("gf-khach", "value"),
                  Input("gf-nhom", "value"), Input("gf-moi", "n_clicks"))
    def _tra(tab, tinh, phuong, khach, nhom, _moi):
        _vao()
        if tab != "tra":
            raise PreventUpdate
        if not tinh or not phuong:
            return alert("Chọn tỉnh / thành và phường / xã ở trên để xem giá.", "info"), [], [], {}, "", "", None
        if ctx.triggered_id == "gf-moi":
            xoa("gia_fpt")
        try:
            kq = gf.goi_theo_phuong(tinh, phuong)
        except gf.LoiGia as e:
            return _loi(e), [], [], {}, "", "", None
        hien = gf.loc_goi(kq["goi"], khach, nhom)
        ds, _ = _ve(hien, None)
        chu, ghi = _chep(ten_khu_vuc(tinh, phuong), hien, kq["luc"], {})
        return (_canh_bao(kq), _kpi(kq["goi"], len(hien), kq["luc"]), ds, {}, chu, ghi,
                {"tinh": tinh, "phuong": phuong, "khach": khach, "nhom": nhom, "luc": kq["luc"].isoformat()})

    @app.callback(Output("gf-ds", "children", allow_duplicate=True), Output("gf-chung", "data", allow_duplicate=True),
                  Output("gf-chep", "data-chep", allow_duplicate=True), Input("gf-pha", "data"), prevent_initial_call=True)
    def _chi_tiet(pha):
        """Lượt hai: nạp chi tiết cả phường (một lần, song song) rồi vẽ lại kèm điều kiện chung."""
        _vao()
        if not pha:
            raise PreventUpdate
        try:
            kq = gf.goi_theo_phuong(pha["tinh"], pha["phuong"])
        except gf.LoiGia:
            raise PreventUpdate
        ct = gf.chi_tiet_nhieu(pha["tinh"], pha["phuong"], kq["goi"])
        hien = gf.loc_goi(kq["goi"], pha["khach"], pha["nhom"])
        ds, chung = _ve(hien, ct)
        return ds, chung, _chep(ten_khu_vuc(pha["tinh"], pha["phuong"]), hien, datetime.fromisoformat(pha["luc"]), chung, ct)[0]
