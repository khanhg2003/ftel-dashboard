"""Cửa sổ "Xem chi tiết" của một gói ở Tra cứu giá: các lựa chọn thời hạn / trả trước, phí lắp đặt, chính sách đang áp dụng.

Nội dung dựng khi mở (gọi dịch vụ chi tiết của fpt.vn cho đúng phường đang chọn), không dựng sẵn.
"""
from __future__ import annotations

from dash import Input, Output, State, html
from dash.exceptions import PreventUpdate

from app import gia_fpt as gf
from app.ui.components import alert, ghi_chu
from app.ui.luoi import bang

DONG = {"function": "params.value == null ? '–' : Math.round(params.value).toLocaleString('vi-VN') + 'đ'"}
SO_1 = {"function": "params.value == null ? '–' : params.value.toLocaleString('vi-VN')"}
COT = [
    {"field": "hinh_thuc", "headerName": "Hình thức", "width": 110},
    {"field": "thang", "headerName": "Thời hạn (tháng)", "width": 100, "type": "numericColumn"},
    {"field": "tong", "headerName": "Tổng tiền dịch vụ", "width": 140, "type": "numericColumn", "valueFormatter": DONG,
     "headerTooltip": "Số tiền dịch vụ khách đóng một lần cho cả thời hạn (chưa gồm phí lắp đặt)."},
    {"field": "thang_dong", "headerName": "Số tháng phải đóng", "width": 110, "type": "numericColumn", "valueFormatter": SO_1},
    {"field": "tang", "headerName": "Tặng thêm (tháng)", "width": 110, "type": "numericColumn",
     "valueFormatter": {"function": "params.value == null || params.value == 0 ? '–' : '+' + params.value.toLocaleString('vi-VN')"},
     "cellStyle": {"styleConditions": [{"condition": "params.value > 0", "style": {"color": "#00844A", "fontWeight": "600"}}]},
     "headerTooltip": "Số tháng được dùng thêm mà không phải đóng tiền: thời hạn trừ số tháng phải đóng."},
    {"field": "binh_quan", "headerName": "Bình quân / tháng", "width": 130, "type": "numericColumn", "valueFormatter": DONG,
     "headerTooltip": "Tổng tiền dịch vụ chia cho cả thời hạn."},
    {"field": "phi_lap", "headerName": "Phí lắp đặt", "width": 110, "type": "numericColumn", "valueFormatter": DONG},
    {"field": "thiet_bi", "headerName": "Thiết bị", "width": 100, "type": "numericColumn", "valueFormatter": DONG},
    {"field": "qua", "headerName": "Ưu đãi", "minWidth": 200, "flex": 2},
    {"field": "den", "headerName": "Chính sách đến hết", "width": 120},
    {"field": "chinh_sach", "headerName": "Chính sách", "minWidth": 220, "flex": 2, "tooltipField": "chinh_sach"},
]


def _nhan_xet(ct: dict) -> str | None:
    """Lựa chọn trả trước có bình quân thấp nhất so với trả theo tháng."""
    gia = ct["gia"]
    tot = [z for z in ct["lua_chon"] if z["hinh_thuc"] == "Trả trước" and z["binh_quan"] and gia]
    if not tot:
        return None
    z = min(tot, key=lambda x: x["binh_quan"])
    if z["binh_quan"] >= gia:
        return None
    re = round((1 - z["binh_quan"] / gia) * 100, 1)
    tang = f", tặng thêm {z['tang']:g} tháng" if z["tang"] else ""
    return (f"Trả trước {z['thang']} tháng: bình quân {gf.chu_tien(z['binh_quan'])}/tháng, rẻ hơn giá tháng {gf.chu_tien(gia)} "
            f"khoảng {str(re).replace('.', ',')}%{tang}.")


def than(ct: dict, khu_vuc: str):
    ds = []
    if ct["mo_ta"]:
        ds.append(html.Ul([html.Li(d) for d in ct["mo_ta"]], className="gf-mo-ta"))
    chips = html.Div([html.Span(f"Khu vực: {khu_vuc}", className="chip"), html.Span(f"Giá tháng: {gf.chu_tien(ct['gia'])}", className="chip")],
                     className="chips", style={"margin": "0 0 12px"})
    if not ct["lua_chon"]:
        return [chips, *ds, alert("Gói này không có lựa chọn thời hạn riêng ở phường này: giá tính theo tháng như bảng giá.", "info")]
    g = bang("gf-ct-bang", COT, None, tuy_chon={"suppressCellFocus": True, "tooltipShowDelay": 300})
    g.rowData = ct["lua_chon"]
    nx = _nhan_xet(ct)
    return [chips, nx and alert(nx, "ok"), *ds, g,
            ghi_chu("Tiền lấy từ chính sách bán đang áp dụng cho phường này trên fpt.vn, đã gồm VAT. Chính sách hết hạn thì tự biến mất khỏi bảng. "
                    "Phí lắp đặt và thiết bị là số khách phải trả thêm khi ký hợp đồng.", style={"margin": "8px 0 0"})]


def register(app):
    @app.callback(Output("gf-ct", "className"), Output("gf-ct-tieu-de", "children"), Output("gf-ct-than", "children"),
                  Input("gf-luoi", "cellClicked"), State("gf-tinh", "value"), State("gf-phuong", "value"), prevent_initial_call=True)
    def _mo(bam, tinh, phuong):
        from app.ui.pages.giafpt import _vao, ten_khu_vuc
        _vao()
        if not bam or bam.get("colId") != "ct" or not bam.get("value") or not (tinh and phuong):
            raise PreventUpdate
        code, gia, ten = str(bam["value"]).split("|", 2)
        try:
            ct = gf.chi_tiet_goi(code, tinh, phuong, float(gia) if gia else None)
        except gf.LoiGia as e:
            return "modal mo", ten, alert(f"{e} Thử lại sau ít phút.", "warn")
        return "modal mo", ten, than(ct, ten_khu_vuc(tinh, phuong))

    @app.callback(Output("gf-ct", "className", allow_duplicate=True), Input("gf-ct-dong", "n_clicks"), Input("gf-ct-nen", "n_clicks"),
                  prevent_initial_call=True)
    def _dong(_x, _nen):
        return "modal"
