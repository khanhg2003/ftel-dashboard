"""Cửa sổ chi tiết một gói ở Tra cứu giá: bấm cả thẻ để mở. CHỈ ghi những điểm KHÁC phần chung của nhóm (chủ app chốt 22/10/2026);
phần chung (cách thanh toán, số tháng tặng, phí lắp đặt dùng chung, hạn chính sách...) đã nằm ngoài danh sách, ở dải "Chung cho cả nhóm".

Nội dung dựng khi mở: chi tiết một gói đã nhớ tạm từ lúc nạp danh sách nên thường mở ngay.
"""
from __future__ import annotations

from dash import ALL, Input, Output, State, ctx, html
from dash.exceptions import PreventUpdate

from app import gia_fpt as gf
from app.ui.components import alert, ghi_chu
from app.ui.luoi import bang

DONG = {"function": "params.value == null ? '–' : Math.round(params.value).toLocaleString('vi-VN') + 'đ'"}


def _hang_gia(ct: dict) -> list[dict]:
    """Mỗi cách thanh toán một dòng (một hình thức + thời hạn có thể có nhiều chính sách: lấy chính sách đầu)."""
    thay = {}
    for z in ct["lua_chon"]:
        thay.setdefault((z["hinh_thuc"], z["thang"]), z)
    return [{"thoi_han": gf.nhan_thoi_han(z["hinh_thuc"], z["thang"]), "tong": z["tong"], "binh_quan": z["binh_quan"], "tang": z["tang"] or None,
             "phi_lap": z["phi_lap"], "thiet_bi": z["thiet_bi"], "qua": z["qua"]} for z in thay.values() if z["tong"]]


def _cot(hang: list[dict]) -> list[dict]:
    """Cột nào giống nhau ở mọi dòng thì bỏ (đã nói ở phần khác biệt), chỉ giữ cột có khác nhau giữa các cách thanh toán.
    Cột hẹp (minWidth) và bảng tự co theo khung (`columnSize`) để ở màn 800 px không phải cuộn ngang; cột Ưu đãi xuống dòng."""
    def doi(k):
        return len({h[k] for h in hang}) > 1
    cot = [{"field": "thoi_han", "headerName": "Cách thanh toán", "minWidth": 120},
           {"field": "tong", "headerName": "Tổng tiền dịch vụ", "minWidth": 130, "type": "numericColumn", "valueFormatter": DONG,
            "headerTooltip": "Số tiền dịch vụ khách đóng một lần cho cả thời hạn (chưa gồm phí lắp đặt)."},
           {"field": "binh_quan", "headerName": "Bình quân / tháng", "minWidth": 120, "type": "numericColumn", "valueFormatter": DONG,
            "headerTooltip": "Tổng tiền dịch vụ chia cho cả thời hạn."}]
    if any(h["tang"] for h in hang):
        cot.append({"field": "tang", "headerName": "Tặng thêm (tháng)", "minWidth": 100, "type": "numericColumn",
                    "valueFormatter": {"function": "params.value == null ? '–' : '+' + params.value.toLocaleString('vi-VN')"},
                    "cellStyle": {"styleConditions": [{"condition": "params.value > 0", "style": {"color": "#00844A", "fontWeight": "600"}}]}})
    if doi("phi_lap"):
        cot.append({"field": "phi_lap", "headerName": "Phí hòa mạng", "minWidth": 105, "type": "numericColumn", "valueFormatter": DONG})
    if doi("thiet_bi"):
        cot.append({"field": "thiet_bi", "headerName": "Thiết bị", "minWidth": 95, "type": "numericColumn", "valueFormatter": DONG})
    if doi("qua"):
        cot.append({"field": "qua", "headerName": "Ưu đãi", "minWidth": 140, "wrapText": True, "autoHeight": True})
    return cot


def _nhan_xet(ct: dict) -> str | None:
    """Cách trả trước có bình quân thấp nhất so với trả theo giá tháng."""
    gia = ct["gia"]
    tot = [z for z in ct["lua_chon"] if z["hinh_thuc"] == "Trả trước" and z["binh_quan"] and gia]
    if not tot:
        return None
    z = min(tot, key=lambda x: x["binh_quan"])
    if z["binh_quan"] >= gia:
        return None
    re = str(round((1 - z["binh_quan"] / gia) * 100, 1)).replace(".", ",")
    tang = f", tặng thêm {z['tang']:g} tháng" if z["tang"] else ""
    return f"Rẻ nhất khi trả trước {z['thang']} tháng: bình quân {gf.chu_tien(z['binh_quan'])}/tháng, thấp hơn giá tháng khoảng {re}%{tang}."


def _thong_tin(g: dict, ct: dict, kb: dict, co_chung: bool):
    """Thông tin chính của gói. Phí hòa mạng luôn ghi (sale dựa vào đó để tư vấn); ưu đãi / thiết bị đi kèm chỉ ghi khi khác phần chung của nhóm."""
    dong = [html.Li([html.B("Phí hòa mạng: "), gf.chu_phi_hoa_mang(ct)])]
    if g["toc_do"]:
        dong.append(html.Li([html.B("Tốc độ: "), g["toc_do"].replace(" / ", " tải xuống · ") + " tải lên"]))
    if g["thiet_bi"]:
        dong.append(html.Li([html.B("Kết nối đồng thời: "), f"{g['thiet_bi']} thiết bị"]))
    if kb.get("thiet_bi"):
        dong.append(html.Li([html.B("Thiết bị đi kèm: "), gf.chu_khoang(kb["thiet_bi"])]))
    if kb.get("uu_dai"):
        dong.append(html.Li([html.B("Ưu đãi: "), kb["uu_dai"]]))
    tieu = "Thông tin chính" if not co_chung else "Thông tin chính (điều kiện chung của nhóm xem ngay trên danh sách)"
    return html.Div([html.Div(tieu, className="gf-ct-tieu"), html.Ul(dong, className="gf-mo-ta")])


def than(g: dict, ct: dict, chung: dict, khu_vuc: str):
    kb = gf.khac_biet(g, ct, chung)
    chips = html.Div([html.Span(f"Khu vực: {khu_vuc}", className="chip"), html.Span(gf.tieu_de_nhom(gf.khoa_nhom(g)), className="chip"),
                      html.Span(f"Giá niêm yết: {gf.chu_tien(ct['gia'])}", className="chip")], className="chips", style={"margin": "0 0 12px"})
    hang = _hang_gia(ct)
    cac = [chips, _thong_tin(g, ct, kb, bool(chung))]
    if hang:
        nx = _nhan_xet(ct)
        cac.append(nx and alert(nx, "ok"))
        luoi = bang("gf-ct-bang", _cot(hang), None, tuy_chon={"suppressCellFocus": True, "tooltipShowDelay": 300}, columnSize="responsiveSizeToFit")
        luoi.rowData = hang
        cac += [html.Div("Giá theo cách thanh toán", className="gf-ct-tieu"), luoi]
    cs = {(z["ma"], z["den"]) for z in ct["lua_chon"] if z["ma"]}
    if cs:
        cac.append(ghi_chu("Chính sách đang áp dụng: " + "; ".join(f"{ma} (đến hết {den})" for ma, den in sorted(cs)) + ". Giá đã gồm VAT. Số tháng tặng "
                                                                                                                      "chỉ có khi trả trước.", style={"margin": "8px 0 0"}))
    return cac


def register(app):
    @app.callback(Output("gf-ct", "className"), Output("gf-ct-tieu-de", "children"), Output("gf-ct-than", "children"),
                  Input({"type": "gf-the", "code": ALL}, "n_clicks"), State("gf-tinh", "value"),
                  State("gf-phuong", "value"), State("gf-ctd", "data"), prevent_initial_call=True)
    def _mo(clicks, tinh, phuong, ctd):
        from app.ui.pages.giafpt import _vao, ten_khu_vuc
        _vao()
        bam = ctx.triggered_id
        if not isinstance(bam, dict) or not (ctx.triggered and ctx.triggered[0].get("value")) or not (tinh and phuong):
            raise PreventUpdate                                   # thẻ vừa được dựng lại (n_clicks = 0), không phải người dùng bấm
        try:
            g = next((x for x in gf.goi_theo_phuong(tinh, phuong)["goi"] if x["code"] == bam["code"]), None)
            if g is None:
                raise PreventUpdate
            ct = gf.chi_tiet_goi(g["code"], tinh, phuong, g["gia"])
        except gf.LoiGia as e:
            return "modal mo", bam["code"], alert(f"{e} Thử lại sau ít phút.", "warn")
        return "modal mo", g["ten"], than(g, ct, ((ctd or {}).get("chung") or {}).get(gf.khoa_nhom(g), {}), ten_khu_vuc(tinh, phuong))

    @app.callback(Output("gf-ct", "className", allow_duplicate=True), Input("gf-ct-dong", "n_clicks"), Input("gf-ct-nen", "n_clicks"),
                  prevent_initial_call=True)
    def _dong(_x, _nen):
        return "modal"
