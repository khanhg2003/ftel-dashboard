"""Trang Chất lượng dữ liệu: soi các điểm nghi ngờ trước khi báo cáo lên BGD."""
from __future__ import annotations

import dash_ag_grid as dag
from dash import Input, Output, dcc, html

from app.admin_service import (acc_la, chua_gan_phong, hd_bat_thuong, ngay_thieu_du_lieu,
                               nv_thieu_ho_so, ton_dong_lau)
from app.metrics import cac_thang_co_du_lieu
from app.org import phong_order
from app.ui.components import (alert, card, chi_nhanh_control, chon_ky, field,
                               gan_dieu_huong_ky, kpi, seg_control)
from app.ui.icons import icon


def topbar():
    return [html.Div([html.H1("Chất lượng dữ liệu"),
                      html.Div("Soát các điểm bất thường trước khi chốt số",
                               className="sub")]),
            html.Div(className="spacer"),
            html.Div(id="cl-badge")]


def layout():
    thangs = cac_thang_co_du_lieu() or ["2026-09"]
    return html.Div([
        html.Div([
            field("Kỳ kiểm tra", chon_ky("cl-thang", thangs)),
            html.Div(className="grow"),
            field("Chi nhánh", chi_nhanh_control("cl-cn")),
            field(" ", dcc.Link([icon("users", 14), html.Span("Sửa danh mục nhân sự")],
                                href="/quantri", className="btn")),
        ], className="toolbar loc-trang"),

        html.Div(id="cl-kpi", className="kpi-row"),
        html.Div(id="cl-canh-bao"),

        card([dcc.Loading(_grid("cl-chuagan"))], title="Hợp đồng chưa gán phòng",
             desc="Acc người bán chưa có trong danh mục nên số chưa về phòng nào (vẫn nằm "
                  "trong tổng chi nhánh). Xử lý: Quản trị → Danh mục nhân sự → thêm acc → "
                  "Tính lại việc gán phòng."),

        html.Div([
            html.Div(card([dcc.Loading(_grid("cl-accla"))], title="Acc lạ",
                          desc="Có phát sinh số nhưng không có trong danh mục lẫn NSLĐ - "
                               "thường là người mới hoặc sai chính tả acc"),
                     className="chart-col"),
            html.Div(card([dcc.Loading(_grid("cl-thieuhoso"))], title="Thiếu hồ sơ NSLĐ",
                          desc="Có trong danh mục nhưng chưa có hồ sơ NSLĐ nên thiếu "
                               "thâm niên, chức danh"),
                     className="chart-col"),
        ], className="chart-row"),

        html.Div([
            html.Div(card([dcc.Loading(_grid("cl-tondong"))], title="Tồn đọng triển khai",
                          desc="Đã ký trên 7 ngày nhưng chưa online - nguy cơ mất khách"),
                     className="chart-col"),
            html.Div(card([dcc.Loading(_grid("cl-batthuong"))], title="Hợp đồng bất thường",
                          desc="Đã huỷ hoặc tạm ngưng nhưng vẫn tính vào số tháng"),
                     className="chart-col"),
        ], className="chart-row"),
    ])


def _grid(gid):
    return dag.AgGrid(id=gid, className="ag-theme-quartz ag-theme-ftel", columnDefs=[], rowData=[],
                      defaultColDef={"resizable": True, "sortable": True, "filter": True},
                      dashGridOptions={"suppressCellFocus": True, "domLayout": "autoHeight",
                                       "pagination": True, "paginationPageSize": 10,
                                       "paginationPageSizeSelector": False},
                      style={"width": "100%"})


def _loc_cn(df, chi_nhanh: str | None, cot_phong: str | None = None,
            cot_acc: str | None = None, cot_cn: str | None = None):
    """Lọc một bảng theo chi nhánh.

    Tuỳ bảng mà nhận ra chi nhánh theo cách khác nhau: tên phòng (qua danh mục),
    tiền tố của acc (DNG./QNM.) hoặc cột CN Bán.
    """
    if not chi_nhanh or chi_nhanh == "all" or df is None or df.empty:
        return df
    if cot_cn and cot_cn in df.columns:
        return df[df[cot_cn].astype(str).str.upper().str.startswith(chi_nhanh)]
    if cot_phong and cot_phong in df.columns:
        thuoc = {p["ten"] for p in phong_order() if p.get("chi_nhanh") == chi_nhanh}
        return df[df[cot_phong].isin(thuoc)]
    if cot_acc and cot_acc in df.columns:
        return df[df[cot_acc].astype(str).str.upper().str.startswith(chi_nhanh + ".")]
    return df


def _cols(df, ten: dict[str, str] | None = None, rong: dict[str, int] | None = None):
    """Cột co giãn theo bề rộng thật của màn hình - không đặt width cứng để khỏi kéo ngang."""
    ten, rong = ten or {}, rong or {}
    out = []
    for c in df.columns:
        col = {"field": c, "headerName": ten.get(c, c.replace("_", " ").title()),
               "minWidth": rong.get(c, 110), "flex": 1, "tooltipField": c}
        out.append(col)
    return out


def register(app):
    gan_dieu_huong_ky(app, "cl-thang")

    @app.callback(
        Output("cl-kpi", "children"), Output("cl-canh-bao", "children"),
        Output("cl-chuagan", "columnDefs"), Output("cl-chuagan", "rowData"),
        Output("cl-accla", "columnDefs"), Output("cl-accla", "rowData"),
        Output("cl-thieuhoso", "columnDefs"), Output("cl-thieuhoso", "rowData"),
        Output("cl-tondong", "columnDefs"), Output("cl-tondong", "rowData"),
        Output("cl-batthuong", "columnDefs"), Output("cl-batthuong", "rowData"),
        Output("cl-badge", "children"),
        Input("cl-thang", "value"), Input("cl-cn", "value"))
    def _cap_nhat(thang, chi_nhanh):
        cg = _loc_cn(chua_gan_phong(thang), chi_nhanh, cot_cn="cn_ban", cot_acc="acc")
        al = _loc_cn(acc_la(thang), chi_nhanh, cot_acc="acc")
        th = _loc_cn(nv_thieu_ho_so(thang), chi_nhanh, cot_phong="phong", cot_acc="acc")
        td = _loc_cn(ton_dong_lau(7), chi_nhanh, cot_phong="phong")
        bt = _loc_cn(hd_bat_thuong(thang), chi_nhanh, cot_acc="acc")
        ngay_thieu = ngay_thieu_du_lieu(thang)

        so_cg = int(cg.so_hd.sum()) if not cg.empty else 0
        diem = 100 - min(100, so_cg * 2 + len(al) * 3 + len(ngay_thieu) * 10 + len(bt))
        kpis = [
            kpi("Điểm chất lượng", f"{max(diem, 0)}/100", "100 là không còn lỗi nào",
                "ok" if diem >= 90 else ("warn" if diem >= 70 else "bad")),
            kpi("HĐ chưa gán phòng", f"{so_cg}", f"Thuộc {len(cg)} acc",
                "bad" if so_cg else "ok"),
            kpi("Acc ngoài danh mục", f"{len(al)}", "Bổ sung để số về đúng phòng",
                "warn" if len(al) else "ok"),
            kpi("Ngày thiếu dữ liệu", f"{len(ngay_thieu)}",
                ", ".join(d[8:10] + "/" + d[5:7] for d in ngay_thieu[:6])
                or "Không thiếu ngày nào",
                "bad" if ngay_thieu else "ok"),
            kpi("Thiếu hồ sơ NSLĐ", f"{len(th)}", "Chưa có thâm niên, chức danh",
                "warn" if len(th) else "ok"),
        ]

        canh_bao = []
        if ngay_thieu:
            canh_bao.append(alert(
                [html.B("Các ngày này không có hợp đồng nào: "),
                 ", ".join(f"{d[8:10]}/{d[5:7]}" for d in ngay_thieu),
                 ". Nhiều khả năng chưa nạp file của ngày đó."], "bad"))
        if so_cg:
            canh_bao.append(alert(
                [html.B(f"{so_cg} hợp đồng chưa gán phòng. "),
                 "Bổ sung acc ở Quản trị → Danh mục nhân sự, rồi bấm “Tính lại việc gán phòng”."],
                "warn"))
        if not canh_bao:
            canh_bao.append(alert("Không phát hiện bất thường trong kỳ này.", "ok"))

        badge = html.Span(f"{len(cg) + len(al) + len(ngay_thieu)} điểm cần xử lý",
                          className="badge bad" if (so_cg or ngay_thieu) else "badge ok")

        return (
            kpis, canh_bao,
            _cols(cg, {"acc": "Acc nhân viên", "ma_nv": "Mã NV", "phong_he_thong": "Phòng hệ thống",
                       "cn_ban": "CN Bán", "so_hd": "Số HĐ", "tu_ngay": "Từ ngày",
                       "den_ngay": "Đến ngày"}, {"acc": 180, "phong_he_thong": 190}),
            cg.to_dict("records"),
            _cols(al, {"acc": "Acc", "so_hd": "Số HĐ", "gan_nhat": "Gần nhất"}, {"acc": 200}),
            al.to_dict("records"),
            _cols(th, {"acc": "Acc", "phong": "Phòng", "ma_nv": "Mã NV"}, {"acc": 190}),
            th.to_dict("records"),
            _cols(td, {"phong": "Phòng", "so_hd": "Số HĐ tồn", "tuoi_tb": "Tuổi TB (ngày)"},
                  {"phong": 190}),
            td.to_dict("records"),
            _cols(bt, {"hop_dong": "Hợp đồng", "acc": "Acc", "tinh_trang": "Tình trạng",
                       "ngay_online": "Ngày online", "ngay_huy": "Ngày hủy"},
                  {"hop_dong": 140, "tinh_trang": 200}),
            bt.to_dict("records"),
            badge,
        )
