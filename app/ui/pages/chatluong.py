"""Trang Chất lượng dữ liệu: soát các điểm làm số báo cáo sai hoặc thiếu trước khi chốt số.

Mỗi mục kiểm tra trả lời một câu hỏi và có sẵn cách xử lý:
1. Đã nạp đủ file chưa?          -> Ngày có số mới nhất của Internet / Truyền hình / Camera có lệch nhau không.
2. Có ngày nào thiếu file?        -> Ngày không có hợp đồng online nào trong khoảng đã có số.
3. Số đã về đúng phòng chưa?      -> Hợp đồng chưa gán phòng (cả 3 loại file), acc khai trùng trong danh mục.
4. Danh mục có sót người bán?     -> Acc ngoài danh mục, tách riêng nhóm "cần xem" khỏi nhân viên KT/CUS.
5. Hồ sơ NSLĐ có đủ?              -> Nhân sự phòng kinh doanh không có trong file NSLĐ gần nhất.
6. Có hợp đồng đáng soát?         -> Tồn đọng triển khai, hợp đồng đã ngưng / chấm dứt nhưng vẫn tính.
Không dùng "điểm chất lượng" cộng trừ tuỳ ý - chỉ đếm số mục ổn / cần xử lý.
"""
from __future__ import annotations

import numbers

import dash_ag_grid as dag
import pandas as pd
from dash import Input, Output, dcc, html

from app.admin_service import (acc_la, acc_trung_danh_muc, chua_gan_phong, do_moi_du_lieu,
                               hd_bat_thuong, ngay_thieu_du_lieu, nv_thieu_ho_so, ton_dong_lau)
from app.metrics import cac_thang_co_du_lieu
from app.org import phong_order
from app.ui.components import LOCALE_VI, alert, chi_nhanh_control, chon_ky, field, gan_dieu_huong_ky, kpi, seg_control
from app.ui.icons import icon


def topbar():
    return [html.Div([html.H1("Chất lượng dữ liệu"),
                      html.Div("Soát các điểm làm số sai hoặc thiếu trước khi chốt số", className="sub")]),
            html.Div(className="spacer"),
            html.Div(id="cl-badge")]


def _the(tieu_de, id_mo_ta, noi_dung, nut=None):
    return html.Div([
        html.Div([html.Div([html.H3(tieu_de), html.Div(id=id_mo_ta, className="desc")], className="the-ten"),
                  html.Div(nut or [], className="the-nut")], className="the-dau"),
        *noi_dung,
    ], className="card")


def layout():
    thangs = cac_thang_co_du_lieu() or ["2026-09"]
    return html.Div([
        html.Div([
            field("Kỳ kiểm tra", chon_ky("cl-thang", thangs)),
            field("Chi nhánh", chi_nhanh_control("cl-cn")),
            html.Div(className="grow"),
            field(" ", html.Div([
                dcc.Link([icon("upload", 14), html.Span("Nạp dữ liệu")], href="/upload", className="btn"),
                dcc.Link([icon("users", 14), html.Span("Sửa danh mục nhân sự")], href="/quantri",
                         className="btn"),
            ], style={"display": "flex", "gap": "8px"})),
        ], className="toolbar loc-trang"),

        dcc.Loading(html.Div(id="cl-kpi", className="kpi-row kpi-6"), type="dot"),
        html.Div(id="cl-canh-bao"),

        _the("1 · Hợp đồng chưa gán phòng", "cl-mo-chuagan", [
            html.Div("Acc người bán không có trong danh mục và không thuộc quy tắc KT/CUS/ECOM nên số "
                     "chưa về phòng nào (vẫn cộng vào tổng chi nhánh). Xử lý: Quản trị → Danh mục nhân sự → "
                     "thêm acc → Tính lại việc gán phòng.", className="desc", style={"marginBottom": "10px"}),
            _grid("cl-chuagan")]),

        html.Div([
            html.Div(_the("2 · Acc ngoài danh mục", "cl-mo-accla", [
                html.Div("Nhân viên kỹ thuật / CUS không cần khai danh mục - app tự tính cho Phòng KT/CUS. "
                         "Chỉ cần soát nhóm “Cần xem”: acc đang tính cho phòng kinh doanh, chưa gán phòng, "
                         "hoặc có trong NSLĐ (nhiều khả năng là nhân viên kinh doanh bị sót).",
                         className="desc", style={"marginBottom": "10px"}),
                _grid("cl-accla")],
                nut=seg_control("cl-accla-xem", [("can_xem", "Cần xem"), ("tat_ca", "Tất cả")], "can_xem")),
                className="chart-col"),
            html.Div(_the("3 · Nhân sự kinh doanh thiếu NSLĐ", "cl-mo-thieuhoso", [
                html.Div("Có trong danh mục phòng kinh doanh, đang làm, nhưng không có trong file NSLĐ gần "
                         "nhất nên thiếu thâm niên, điểm NSLĐ. Chi nhánh chưa nạp file NSLĐ thì cả chi nhánh "
                         "sẽ hiện ở đây.", className="desc", style={"marginBottom": "10px"}),
                _grid("cl-thieuhoso")]), className="chart-col"),
        ], className="chart-row doi"),

        html.Div([
            html.Div(_the("4 · Tồn đọng triển khai", "cl-mo-tondong", [
                html.Div("Hợp đồng đã tạo từ 7 ngày, chưa online, còn trong file mới nhất - tính đến ngày có "
                         "số mới nhất. Chi tiết từng hợp đồng ở Phân tích bán hàng → Số tồn.",
                         className="desc", style={"marginBottom": "10px"}),
                _grid("cl-tondong")],
                nut=dcc.Link("Xem chi tiết", href="/phantich", className="btn nho")), className="chart-col"),
            html.Div(_the("5 · Hợp đồng đã ngưng / chấm dứt", "cl-mo-batthuong", [
                html.Div("Online trong kỳ nhưng tình trạng hiện tại không còn “Bình thường” (ngưng vì thanh "
                         "toán, chấm dứt, đi vắng). Các hợp đồng này vẫn đang được tính vào số online.",
                         className="desc", style={"marginBottom": "10px"}),
                html.Div(id="cl-batthuong-tt"),
                _grid("cl-batthuong")]), className="chart-col"),
        ], className="chart-row doi"),

        _the("6 · Danh mục khai sai hoặc trùng", "cl-mo-trung", [
            html.Div("Acc khai nhiều dòng mà không ghi ngày hiệu lực, hoặc đang khai khác phòng đã được BGĐ chốt "
                     "- số của acc đó đang về sai phòng. Xử lý ở Quản trị → Danh mục nhân sự rồi bấm "
                     "“Tính lại việc gán phòng”.",
                     className="desc", style={"marginBottom": "10px"}),
            _grid("cl-trung")]),
    ])


def _grid(gid):
    return dag.AgGrid(id=gid, className="ag-theme-quartz ag-theme-ftel", columnDefs=[], rowData=[],
                      defaultColDef={"resizable": True, "sortable": True, "filter": True},
                      dashGridOptions={"suppressCellFocus": True, "domLayout": "autoHeight",
                                       "pagination": True, "paginationPageSize": 10,
                                       "paginationPageSizeSelector": False,
                                       "localeText": {**LOCALE_VI, "noRowsToShow": "Không có - mục này ổn"}},
                      style={"width": "100%"})


def _loc_cn(df, chi_nhanh: str | None, cot_phong: str | None = None,
            cot_acc: str | None = None, cot_cn: str | None = None):
    """Lọc một bảng theo chi nhánh: theo cột CN Bán, cột chi nhánh, tên phòng hoặc tiền tố acc."""
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


def _la_cot_so(cot: pd.Series) -> bool:
    """Cột toàn số - kể cả kiểu Decimal mà PostgreSQL trả về cho phép ROUND."""
    if pd.api.types.is_numeric_dtype(cot):
        return True
    gia_tri = cot.dropna()
    return not gia_tri.empty and all(isinstance(v, numbers.Number) and not isinstance(v, bool)
                                     for v in gia_tri)


def _cols(df, ten: dict[str, str] | None = None, rong: dict[str, int] | None = None, bo: tuple = ()):
    """Cột co giãn theo bề rộng thật của màn hình - không đặt width cứng để khỏi kéo ngang."""
    ten, rong = ten or {}, rong or {}
    out = []
    for c in df.columns:
        if c in bo:
            continue
        col = {"field": c, "headerName": ten.get(c, c.replace("_", " ").title()),
               "minWidth": rong.get(c, 100), "flex": 1, "tooltipField": c}
        if _la_cot_so(df[c]) and c not in ("ma_nv", "acc", "hop_dong"):
            col["type"] = "numericColumn"
        out.append(col)
    return out


def _ban_ghi(df):
    if df is None or df.empty:
        return []
    d = df.astype(object).where(df.notna(), None)
    for c in d.columns:
        d[c] = [str(v)[:10] if hasattr(v, "isoformat") else v for v in d[c]]
    return d.to_dict("records")


def _ngay(d: str | None) -> str:
    return f"{d[8:10]}/{d[5:7]}" if d else "–"


def register(app):
    gan_dieu_huong_ky(app, "cl-thang")

    @app.callback(
        Output("cl-kpi", "children"), Output("cl-canh-bao", "children"), Output("cl-badge", "children"),
        Output("cl-chuagan", "columnDefs"), Output("cl-chuagan", "rowData"), Output("cl-mo-chuagan", "children"),
        Output("cl-accla", "columnDefs"), Output("cl-accla", "rowData"), Output("cl-mo-accla", "children"),
        Output("cl-thieuhoso", "columnDefs"), Output("cl-thieuhoso", "rowData"),
        Output("cl-mo-thieuhoso", "children"),
        Output("cl-tondong", "columnDefs"), Output("cl-tondong", "rowData"), Output("cl-mo-tondong", "children"),
        Output("cl-batthuong", "columnDefs"), Output("cl-batthuong", "rowData"),
        Output("cl-mo-batthuong", "children"), Output("cl-batthuong-tt", "children"),
        Output("cl-trung", "columnDefs"), Output("cl-trung", "rowData"), Output("cl-mo-trung", "children"),
        Input("cl-thang", "value"), Input("cl-cn", "value"), Input("cl-accla-xem", "value"))
    def _cap_nhat(thang, chi_nhanh, xem_accla):
        moi = do_moi_du_lieu()
        cg = _loc_cn(chua_gan_phong(thang), chi_nhanh, cot_cn="cn_ban", cot_acc="acc")
        al_tat_ca = _loc_cn(acc_la(thang), chi_nhanh, cot_acc="acc")
        al_can_xem = al_tat_ca[al_tat_ca.nhom == "Cần xem"] if len(al_tat_ca) else al_tat_ca
        al = al_can_xem if xem_accla != "tat_ca" else al_tat_ca
        th = nv_thieu_ho_so(thang)
        if chi_nhanh and chi_nhanh != "all" and len(th):
            th = th[th.chi_nhanh == chi_nhanh]
        td = _loc_cn(ton_dong_lau(7), chi_nhanh, cot_phong="phong")
        bt = _loc_cn(hd_bat_thuong(thang), chi_nhanh, cot_phong="phong")
        trung = acc_trung_danh_muc()
        ngay_thieu = ngay_thieu_du_lieu(thang)

        # 1. độ mới: các file phải cùng tới một ngày
        ngay_moi = [m["ngay"] for m in moi if m["ngay"]]
        lech = [m for m in moi if m["ngay"] and ngay_moi and m["ngay"] < max(ngay_moi)]
        so_cg = int(cg.so_hd.sum()) if len(cg) else 0
        so_td = int(td.so_hd.sum()) if len(td) else 0
        muc = [
            ("Dữ liệu mới nhất", _ngay(max(ngay_moi) if ngay_moi else None),
             ("Chậm hơn: " + ", ".join(f"{m['loai']} {_ngay(m['ngay'])}" for m in lech)) if lech
             else "Internet, Truyền hình, Camera cùng ngày", not lech),
            ("HĐ chưa gán phòng", f"{so_cg}",
             " · ".join(f"{k} {int(v)}" for k, v in cg.groupby("loai").so_hd.sum().items()) if so_cg
             else "Mọi hợp đồng đã về phòng", so_cg == 0),
            ("Ngày thiếu dữ liệu", f"{len(ngay_thieu)}",
             ", ".join(_ngay(d) for d in ngay_thieu[:5]) or "Không thiếu ngày nào", not ngay_thieu),
            ("Acc cần xem", f"{len(al_can_xem)}",
             f"Ngoài danh mục · {len(al_tat_ca) - len(al_can_xem)} acc KT/CUS bỏ qua", len(al_can_xem) == 0),
            ("Thiếu hồ sơ NSLĐ", f"{len(th)}", "Nhân sự phòng kinh doanh đang làm", len(th) == 0),
            ("Danh mục sai / trùng", f"{len(trung)}", "Acc đang về sai phòng", len(trung) == 0),
        ]
        kpis = [kpi(ten, gia_tri, goi_y, "ok" if dat else "warn") for ten, gia_tri, goi_y, dat in muc]
        so_on = sum(1 for *_, dat in muc if dat)

        viec = []
        if lech:
            viec.append([html.B("Nạp bổ sung file: "),
                         ", ".join(f"{m['loai']} (mới tới {_ngay(m['ngay'])})" for m in lech),
                         f" - Internet đã tới {_ngay(max(ngay_moi))}, số V.VIP/Camera ngày đó đang thiếu."])
        if ngay_thieu:
            viec.append([html.B("Kiểm tra ngày không có hợp đồng: "), ", ".join(_ngay(d) for d in ngay_thieu),
                         " - nhiều khả năng chưa nạp file của ngày đó."])
        if so_cg:
            viec.append([html.B(f"{so_cg} hợp đồng chưa gán phòng: "),
                         "thêm acc vào danh mục rồi bấm “Tính lại việc gán phòng”."])
        if len(al_can_xem):
            viec.append([html.B(f"{len(al_can_xem)} acc cần xem: "),
                         "nếu là nhân viên kinh doanh thì khai vào danh mục để số về đúng phòng."])
        if len(trung):
            viec.append([html.B(f"{len(trung)} acc khai sai hoặc trùng trong danh mục: "),
                         "; ".join(f"{r.acc} - {r.van_de}, đang khai {r.dang_khai}" for r in trung.itertuples())])
        canh_bao = (alert([html.B(f"{so_on}/{len(muc)} mục ổn. Việc cần làm:"),
                           html.Ul([html.Li(v) for v in viec], style={"margin": "6px 0 0"})], "warn")
                    if viec else alert(html.B(f"{so_on}/{len(muc)} mục ổn - dữ liệu sẵn sàng để chốt số."), "ok"))
        badge = html.Span(f"{len(muc) - so_on} mục cần xử lý" if so_on < len(muc) else "Dữ liệu ổn",
                          className="badge warn" if so_on < len(muc) else "badge ok")

        ten_thang = f"tháng {thang[5:7]}/{thang[:4]}"
        th_mo = (f"{len(th)} người · so với file NSLĐ {th.thang_nsld.iloc[0][5:7]}/{th.thang_nsld.iloc[0][:4]}"
                 if len(th) and th.thang_nsld.iloc[0] else f"{len(th)} người · chưa có file NSLĐ")
        bt_tt = (html.Div([html.Span(f"{k}: {v}", className="badge warn") for k, v in bt.tinh_trang.value_counts().items()],
                          style={"display": "flex", "gap": "6px", "flexWrap": "wrap", "marginBottom": "10px"})
                 if len(bt) else "")
        return (
            kpis, canh_bao, badge,
            _cols(cg, {"loai": "Loại", "acc": "Acc nhân viên", "ma_nv": "Mã NV", "phong_he_thong": "Phòng hệ thống",
                       "cn_ban": "CN Bán", "so_hd": "Số HĐ", "tu_ngay": "Từ ngày", "den_ngay": "Đến ngày"},
                  {"acc": 170, "phong_he_thong": 150}),
            _ban_ghi(cg), f"{so_cg} hợp đồng · {len(cg)} acc · {ten_thang}",
            _cols(al_tat_ca, {"acc": "Acc", "dang_tinh_cho": "Đang tính cho", "so_hd": "Số HĐ",
                              "gan_nhat": "Gần nhất", "co_nsld": "Có NSLĐ", "nhom": "Nhóm"},
                  {"acc": 150, "dang_tinh_cho": 130}),
            _ban_ghi(al), f"{len(al_can_xem)} cần xem / {len(al_tat_ca)} acc · {ten_thang}",
            _cols(th, {"acc": "Acc", "phong": "Phòng", "ma_nv": "Mã NV", "chi_nhanh": "Chi nhánh"},
                  {"acc": 150}, bo=("thang_nsld",)),
            _ban_ghi(th), th_mo,
            _cols(td, {"phong": "Phòng", "so_hd": "HĐ chờ từ 7 ngày", "tuoi_tb": "Chờ TB (ngày)"}, {"phong": 150}),
            _ban_ghi(td), f"{so_td} hợp đồng · tính đến {_ngay(max(ngay_moi) if ngay_moi else None)}",
            _cols(bt, {"hop_dong": "Hợp đồng", "acc": "Acc", "tinh_trang": "Tình trạng", "ngay_online": "Ngày online",
                       "ngay_huy": "Ngày hủy", "phong": "Phòng"}, {"hop_dong": 120, "tinh_trang": 170}),
            _ban_ghi(bt), f"{len(bt)} hợp đồng · {ten_thang}", bt_tt,
            _cols(trung, {"acc": "Acc", "van_de": "Vấn đề", "dang_khai": "Đang khai ở"}, {"acc": 150, "van_de": 300}),
            _ban_ghi(trung), f"{len(trung)} acc",
        )
