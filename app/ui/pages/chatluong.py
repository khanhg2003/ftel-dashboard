"""Trang Chất lượng dữ liệu: nơi phát hiện mọi điểm bất thường của file raw trước khi chốt số.

Bố cục (BGĐ chốt 17/09/2026):
1. Bốn ô đếm: số mục Nghiêm trọng / Cần soát / Thông tin / Ổn.
2. Danh sách mục kiểm tra xếp theo mức độ, mỗi dòng có số lượng và cách xử lý. Mặc định chỉ hiện mục có vấn đề.
3. Bấm một mục -> bảng chi tiết bên dưới (tìm nhanh, copy được).
4. Nút Excel: mỗi mục có vấn đề một sheet + sheet Tổng hợp để gửi Trưởng phòng / Inside.
Danh sách mục và cách kiểm tra nằm ở app/chat_luong.py.
"""
from __future__ import annotations

import dash_ag_grid as dag
import pandas as pd
from dash import Input, Output, Patch, State, ctx, dcc, html, no_update

from app import chat_luong as cl
from app.auth import ghi_log
from app.export_phan_tich import xuat_phan_tich
from app.metrics import cac_ngay_co_du_lieu as _cac_ngay
from app.metrics import cac_thang_co_du_lieu
from app.overview import TEN_PHAM_VI
from app.ui import ky_chung as kc
from app.ui.components import LOCALE_VI, MA_NV, chi_nhanh_control, chon_ky, field, gan_dieu_huong_ky, kpi, seg_control
from app.ui.icons import icon

MAU_MUC_DO = {"styleConditions": [
    {"condition": f"params.value == '{cl.NGHIEM_TRONG}'", "style": {"color": "#B42318", "fontWeight": "700"}},
    {"condition": f"params.value == '{cl.CAN_SOAT}'", "style": {"color": "#8A5709", "fontWeight": "650"}},
    {"condition": f"params.value == '{cl.THONG_TIN}'", "style": {"color": "#0C4B7E"}},
    {"condition": "params.value == 'Ổn'", "style": {"color": "#0A5B31"}}]}
COT_TONG = [
    {"field": "muc_do", "headerName": "Mức độ", "width": 130, "pinned": "left", "cellStyle": MAU_MUC_DO},
    {"field": "nhom", "headerName": "Nhóm", "width": 170},
    {"field": "ten", "headerName": "Mục kiểm tra", "flex": 2, "minWidth": 260},
    {"field": "so", "headerName": "Số lượng", "width": 120},
    {"field": "xu_ly", "headerName": "Cách xử lý", "flex": 3, "minWidth": 320, "tooltipField": "xu_ly"},
]


def topbar():
    return [html.Div([html.H1("Chất lượng dữ liệu"),
                      html.Div("Mọi điểm bất thường của file raw - soát trước khi chốt số", className="sub")]),
            html.Div(className="spacer"),
            html.Div(id="cl-badge")]


def layout(ky: dict | None = None):
    ky = ky or {}
    thangs = cac_thang_co_du_lieu() or ["2026-09"]
    return html.Div([
        html.Div([
            field("Kỳ báo cáo · theo tháng", chon_ky("cl-thang", thangs, kc.thang_cua(ky, thangs))),
            field("Chi nhánh", chi_nhanh_control("cl-cn", ky.get("cn", "all"))),
            html.Div(className="grow"),
            field(" ", html.Div([
                html.Button([icon("download", 14), html.Span("Excel")], id="cl-xls", className="btn primary",
                            title="Mỗi mục có vấn đề một sheet, gửi Trưởng phòng / Inside xử lý"),
                dcc.Link([icon("upload", 14), html.Span("Nạp dữ liệu")], href="/upload", className="btn"),
                dcc.Link([icon("users", 14), html.Span("Danh mục nhân sự")], href="/quantri?tab=staff",
                         className="btn"),
            ], style={"display": "flex", "gap": "8px", "flexWrap": "wrap"})),
        ], className="toolbar loc-trang"),
        dcc.Store(id="cl-kq"),
        dcc.Download(id="cl-tai-xuong"),

        dcc.Loading(html.Div(id="cl-kpi", className="kpi-row"), type="dot"),

        html.Div([
            html.Div([
                html.Div([html.H3("Danh sách kiểm tra"), html.Div(id="cl-mo-ta", className="desc")],
                         className="the-ten"),
                html.Div(seg_control("cl-xem", [("loi", "Chỉ mục có vấn đề"), ("tat_ca", "Tất cả mục")], "loi"),
                         className="the-nut"),
            ], className="the-dau"),
            dag.AgGrid(id="cl-tong", className="ag-theme-quartz ag-theme-ftel", columnDefs=COT_TONG, rowData=[],
                       getRowId="params.data.ma",
                       defaultColDef={"resizable": True, "sortable": True, "wrapText": True, "autoHeight": True},
                       dashGridOptions={"suppressCellFocus": True, "domLayout": "autoHeight",
                                        "rowSelection": "single", "rowStyle": {"cursor": "pointer"},
                                        "localeText": {**LOCALE_VI, "noRowsToShow": "Không có mục nào cần xử lý"}},
                       style={"width": "100%"}),
            html.Div("Bấm một dòng để xem chi tiết bên dưới.", className="desc", style={"marginTop": "8px"}),
        ], className="card"),

        html.Div([
            html.Div([
                html.Div([html.H3(id="cl-ct-tieu-de"), html.Div(id="cl-ct-mo-ta", className="desc")],
                         className="the-ten"),
                html.Div(dcc.Input(id="cl-ct-tim", type="search", placeholder="Tìm hợp đồng, acc, phòng…",
                                   className="o-tim", autoComplete="off"), className="the-nut"),
            ], className="the-dau"),
            dag.AgGrid(id="cl-ct", className="ag-theme-quartz ag-theme-ftel", columnDefs=[], rowData=[],
                       defaultColDef={"resizable": True, "sortable": True, "filter": True},
                       dashGridOptions={"suppressCellFocus": True, "domLayout": "autoHeight", "pagination": True,
                                        "paginationPageSize": 15, "paginationPageSizeSelector": False,
                                        "localeText": {**LOCALE_VI, "noRowsToShow": "Không có - mục này ổn"}},
                       style={"width": "100%"}),
        ], className="card", id="cl-the-ct"),
    ])


def _so(r: dict) -> str:
    if r["loi"]:
        return "Lỗi khi kiểm tra"
    return f"{r['so_luong']:,} {r['don_vi']}".replace(",", ".") if r["so_luong"] else "0"


def _cot_ct(r: dict) -> list[dict]:
    out = []
    for k, ten in r["cot"].items():
        c = {"field": k, "headerName": ten, "flex": 1, "minWidth": 110, "tooltipField": k}
        if k == "ma_nv":
            c["valueFormatter"] = MA_NV
        if k in ("van_de", "xu_ly", "file_name", "thieu"):
            c.update(flex=2, minWidth=220)
        out.append(c)
    return out


def register(app):
    kc.ghi(app, ("cl-thang", "value"), ("cl-cn", "value"),
           chuyen=lambda thang, cn: {**kc.ca_thang(thang, _cac_ngay()), "cn": cn})
    gan_dieu_huong_ky(app, "cl-thang")

    @app.callback(Output("cl-kq", "data"), Output("cl-kpi", "children"), Output("cl-badge", "children"),
                  Output("cl-mo-ta", "children"),
                  Input("cl-thang", "value"), Input("cl-cn", "value"))
    def _chay(thang, cn):
        kq = cl.chay(thang, cn or "all")
        dem = {m: sum(1 for r in kq if r["muc_do"] == m) for m in (cl.NGHIEM_TRONG, cl.CAN_SOAT, cl.THONG_TIN, "Ổn")}
        kpis = [kpi("Nghiêm trọng", dem[cl.NGHIEM_TRONG], "mục làm số báo cáo sai / thiếu",
                    "bad" if dem[cl.NGHIEM_TRONG] else "ok"),
                kpi("Cần soát", dem[cl.CAN_SOAT], "mục nên kiểm tra lại với Inside", "warn" if dem[cl.CAN_SOAT] else "ok"),
                kpi("Thông tin", dem[cl.THONG_TIN], "mục theo dõi, không làm sai số"),
                kpi("Mục ổn", dem["Ổn"], f"trên {len(kq)} mục kiểm tra", "ok")]
        van_de = dem[cl.NGHIEM_TRONG] + dem[cl.CAN_SOAT]
        badge = html.Span(f"{dem[cl.NGHIEM_TRONG]} nghiêm trọng · {dem[cl.CAN_SOAT]} cần soát" if van_de
                          else "Dữ liệu ổn", className="badge bad" if dem[cl.NGHIEM_TRONG] else
                          "badge warn" if van_de else "badge ok")
        mo_ta = (f"{len(kq)} mục · tháng {thang[5:7]}/{thang[:4]} · {TEN_PHAM_VI.get(cn or 'all', 'Toàn chi nhánh')}"
                 " · xếp theo mức độ")
        return kq, kpis, badge, mo_ta

    @app.callback(Output("cl-tong", "rowData"), Input("cl-kq", "data"), Input("cl-xem", "value"))
    def _tong(kq, xem):
        return [{"ma": r["ma"], "muc_do": r["muc_do"], "nhom": r["nhom"], "ten": r["ten"], "so": _so(r),
                 "xu_ly": r["loi"] or r["xu_ly"]}
                for r in (kq or []) if xem == "tat_ca" or r["muc_do"] != "Ổn"]

    @app.callback(Output("cl-ct-tieu-de", "children"), Output("cl-ct-mo-ta", "children"),
                  Output("cl-ct", "columnDefs"), Output("cl-ct", "rowData"), Output("cl-ct-tim", "value"),
                  Input("cl-tong", "cellClicked"), Input("cl-kq", "data"), State("cl-tong", "rowData"))
    def _chi_tiet(bam, kq, dong_tong):
        kq = kq or []
        if not kq:
            return "Chi tiết", "", [], [], ""
        ma = (bam or {}).get("rowId") if ctx.triggered_id == "cl-tong" else None
        if not ma:                                    # mặc định: mục có vấn đề nặng nhất
            ma = (dong_tong or [{}])[0].get("ma") if dong_tong else None
            ma = ma or next((r["ma"] for r in kq if r["muc_do"] != "Ổn"), kq[0]["ma"])
        r = next((x for x in kq if x["ma"] == ma), kq[0])
        tieu_de = [html.Span(r["muc_do"], className="badge " + {cl.NGHIEM_TRONG: "bad", cl.CAN_SOAT: "warn",
                                                                  "Ổn": "ok"}.get(r["muc_do"], "muted"),
                             style={"marginRight": "8px"}), f"{r['ten']} · {_so(r)}"]
        mo_ta = r["loi"] or r["xu_ly"]
        if r["tong_dong"] > len(r["dong"]):
            mo_ta += f" (đang hiện {len(r['dong'])}/{r['tong_dong']} dòng - xem đủ trong file Excel)"
        return tieu_de, mo_ta, _cot_ct(r), r["dong"], ""

    @app.callback(Output("cl-ct", "dashGridOptions"), Input("cl-ct-tim", "value"), prevent_initial_call=True)
    def _tim(chu):
        p = Patch()
        p["quickFilterText"] = chu or ""
        return p

    @app.callback(Output("cl-tai-xuong", "data"), Input("cl-xls", "n_clicks"),
                  State("cl-thang", "value"), State("cl-cn", "value"), prevent_initial_call=True)
    def _excel(_n, thang, cn):
        if not _n:
            return no_update
        cn = cn or "all"
        kq = cl.chay(thang, cn)
        tong = pd.DataFrame([{"muc_do": r["muc_do"], "nhom": r["nhom"], "ten": r["ten"], "so": _so(r),
                              "xu_ly": r["loi"] or r["xu_ly"]} for r in kq])
        bang = [("Tổng hợp", tong, [("muc_do", "Mức độ", "text"), ("nhom", "Nhóm", "text"),
                                    ("ten", "Mục kiểm tra", "text"), ("so", "Số lượng", "text"),
                                    ("xu_ly", "Cách xử lý", "text")])]
        for i, r in enumerate([x for x in kq if x["muc_do"] != "Ổn" and not x["loi"]], start=1):
            # Excel lấy đủ dòng, không giới hạn như trên trang
            df = cl.MUC_THEO_MA[r["ma"]].ham(thang, cn)
            ten_sheet = "".join(" " if ch in "/\\?*[]:" else ch for ch in f"{i:02d} {r['ten']}")[:31]
            bang.append((ten_sheet, cl._ban_ghi_df(df),
                         [(k, ten, "text") for k, ten in r["cot"].items()]))
        ghi_log("xuat_chat_luong", f"{thang} {cn}")
        noi_dung = xuat_phan_tich("", f"CHẤT LƯỢNG DỮ LIỆU THÁNG {thang[5:7]}/{thang[:4]} · "
                                      f"{TEN_PHAM_VI.get(cn, 'Toàn chi nhánh').upper()}", bang)
        return dcc.send_bytes(noi_dung, f"ChatLuongDuLieu_{thang}_{cn}.xlsx")
