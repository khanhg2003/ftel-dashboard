"""Trang Phòng Online - nhóm người của IBB2 gom vào một bảng riêng để BGĐ theo dõi (chốt 07/11/2026).

Số liệu y hệt Báo cáo phòng của IBB2 (`app/phong_online.py` gọi lại cùng hàm), chỉ giữ người trong nhóm; IBB2 vẫn
hiện đủ mọi người ở Báo cáo phòng. Quyền: BGĐ (role admin, không phải tài khoản kỹ thuật) và tài khoản vai trò "online".
Mọi callback kiểm lại quyền ở máy chủ.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

import dash_ag_grid as dag
from dash import Input, Output, Patch, State, dcc, html
from dash.exceptions import PreventUpdate
from flask_login import current_user

from app import cot_phong as cp
from app import canh_bao as quy_tac
from app import phong_online as po
from app.auth import ghi_log
from app.metrics import cac_ngay_co_du_lieu
from app.overview import trang_thai_ngay
from app.ui import ky_chung as kc
from app.ui import lien_ket as lk
from app.ui import ngan_nhan_su as nn
from app.ui.components import (DONG_TONG_NGAY, HEAT_NGAY, LOCALE_VI, LOP_DONG_NGAY, alert, chon_ngay, chu_giai,
                               field, gan_chon_ngay, ghi_chu, kpi, lop_cot_ngay, seg_control)
from app.ui.icons import icon
from app.ui.luoi import bang
from app.ui.pages.phong import DINH_NGHIA, ROW_STYLE, TEN_KHOI, _cot_nv


SO_TRONG = {"function": "params.value == null || isNaN(params.value) ? '–' : Number(params.value).toLocaleString('vi-VN')"}
CHENH_TRONG = {"function": "params.value == null || isNaN(params.value) ? '–' : (params.value > 0 ? '+' : '') + params.value"}


def _tong(serie) -> int | None:
    """Tổng một cột, bỏ ô chưa nhập; cả cột chưa nhập thì để trống (không ghi 0 cho người chưa báo)."""
    v = pd.to_numeric(serie, errors="coerce")
    return int(v.sum()) if v.notna().any() else None


def _duoc_xem() -> bool:
    return bool(getattr(current_user, "is_authenticated", False)) and current_user.duoc_xem_phong_online


def topbar():
    return [html.Div([html.H1(po.TEN), html.Div("Nhóm online của IBB2: đủ chỉ số từng người, luỹ kế tháng", className="sub")]),
            html.Div(className="spacer"), html.Div(id="po-badge")]


def layout(ky: dict | None = None):
    from app.ui.pages import phongonline_tinh
    ky = ky or {}
    if not _duoc_xem():
        return alert("Tài khoản này không xem được Phòng Online.", "bad")
    ngays = cac_ngay_co_du_lieu()
    return html.Div([
        html.Div([field("Kỳ báo cáo · luỹ kế đến ngày", chon_ngay("po", ngays, kc.ngay_co_so(ky.get("den"), ngays)))],
                 className="toolbar loc-trang"),
        html.Div(id="po-canh-bao"),
        dcc.Loading(html.Div(id="po-kpi", className="kpi-row kpi-5"), type="dot"),

        # Báo cáo KHTN từng bạn (để báo cáo sếp): lấy từ ô KHTN ở Báo cáo ngày của nhóm
        html.Div([
            html.Div([
                html.Div([html.H3("Báo cáo KHTN từng bạn", style={"margin": 0}),
                          html.Div(id="po-khtn-mo-ta", className="desc", style={"margin": "2px 0 0"})]),
                html.Div(className="grow"),
                seg_control("po-khtn-xem", [("tt", "Tóm tắt"), ("ngay", "Từng ngày")], "tt"),
                html.Button([icon("download", 14), html.Span("Excel")], id="po-khtn-xls", className="btn",
                            title="File Excel KHTN từng ngày của từng bạn, gửi sếp"),
            ], className="the-thanh"),
            dcc.Download(id="po-khtn-tai"),
            dcc.Loading(bang("po-khtn", [], lop="ag-theme-quartz ag-theme-ftel luoi-ke")),
            ghi_chu("KHTN là số khách đang theo, chưa lên hợp đồng, do từng bạn tự nhập ở Báo cáo ngày. "
                    "Ô trống (–) là ngày đó bạn chưa nhập, không phải số 0. Trung bình chỉ tính các ngày đã nhập.",
                    nhan="Cách đọc", style={"margin": "10px 0 4px"}),
        ], className="card"),

        html.Div([
            html.Div([
                html.Div([html.H3("Nhân sự Phòng Online", style={"margin": 0}),
                          html.Div(id="po-mo-ta", className="desc", style={"margin": "2px 0 0"})]),
                html.Div(className="grow"),
                dcc.Input(id="po-tim", type="search", placeholder="Tìm tên hoặc acc…", className="o-tim"),
                seg_control("po-xem", [("ban", "Bán hàng"), ("theo_doi", "Nhịp có số & tồn"), ("tat_ca", "Tất cả cột")], "ban"),
            ], className="the-thanh"),
            nn.goi_y("Bấm vào một nhân sự để xem chi tiết đầy đủ.", style={"marginBottom": "8px"}),
            dcc.Loading(dag.AgGrid(
                id="po-nv", className=f"ag-theme-quartz ag-theme-ftel {nn.lop('mot')}", columnDefs=[], rowData=[],
                defaultColDef={"resizable": True, "sortable": True, "suppressMovable": True,
                               "wrapHeaderText": True, "autoHeaderHeight": True},
                dashGridOptions={"suppressCellFocus": True, "domLayout": "autoHeight", "tooltipShowDelay": 300,
                                 "localeText": LOCALE_VI, "rowStyle": {"cursor": "pointer"}},
                getRowId="params.data.acc_norm", getRowStyle=ROW_STYLE, style={"width": "100%"})),
            ghi_chu("Màu VVIP/PTTB, Camera/PTTB so với mức chung của nhóm: xanh cao hơn từ 5 điểm, vàng thấp hơn 5-10 điểm, "
                    "đỏ thấp hơn từ 10 điểm. Hạng xếp trong riêng nhóm.", nhan="Cách đọc màu", style={"margin": "10px 0 4px"}),
            chu_giai("Cách tính các cột", DINH_NGHIA),
        ], className="card"),

        phongonline_tinh.the(),

        html.Div([
            html.Div([
                html.Div([html.H3("Số bán theo ngày của từng nhân viên", style={"margin": 0}),
                          html.Div(id="po-ngay-mo-ta", className="desc", style={"margin": "2px 0 0"})]),
                html.Div(className="grow"),
                seg_control("po-khoi", [("online", "Số Online"), ("fptplay", "Số Combo"), ("vvip", "Số V.VIP"),
                                        ("camera", "Số Camera")], "online"),
                seg_control("po-khoi-xem", [("ngay", "Từng ngày"), ("congdon", "Cộng dồn")], "ngay"),
            ], className="the-thanh"),
            nn.goi_y(style={"marginBottom": "8px"}),
            dcc.Loading(dag.AgGrid(
                id="po-nv-ngay", className=f"ag-theme-quartz ag-theme-ftel {nn.lop()}", columnDefs=[], rowData=[],
                defaultColDef={"resizable": True, "sortable": False, "suppressMovable": True},
                dashGridOptions={"suppressCellFocus": True, "domLayout": "autoHeight", "rowHeight": 32, "headerHeight": 38,
                                 "localeText": LOCALE_VI, "rowClassRules": LOP_DONG_NGAY},
                getRowStyle=DONG_TONG_NGAY, style={"width": "100%"})),
        ], className="card"),
    ])


def _the(tong: dict) -> list:
    """Năm thẻ tóm tắt lấy từ dòng TỔNG của nhóm."""
    chenh = int(tong.get("chenh_ck") or 0)
    pct = lambda v: "–" if v is None else f"{v:.0f}%"            # noqa: E731
    return [
        kpi("Online luỹ kế", f"{int(tong.get('online') or 0)}", f"{chenh:+d} so với cùng kỳ tháng trước", "ok" if chenh >= 0 else "bad"),
        kpi("VVIP/PTTB", pct(tong.get("kem_vvip")), f"{int(tong.get('vvip') or 0)} V.VIP trên {int(tong.get('online') or 0)} online"),
        kpi("Camera/PTTB", pct(tong.get("kem_camera")), f"{int(tong.get('camera') or 0)} camera trên {int(tong.get('online') or 0)} online"),
        kpi("Bán mới luỹ kế", f"{int(tong.get('ban_moi') or 0)}", f"{int(tong.get('ban_moi_ngay') or 0)} trong ngày chọn"),
        kpi("HĐ chờ từ 7 ngày", f"{int(tong.get('ton_qua_7') or 0)}", f"trên {int(tong.get('ton') or 0)} hợp đồng chưa online",
            "warn" if tong.get("ton_qua_7") else "ok"),
    ]


def register(app):
    from app.ui.pages import phongonline_tinh
    gan_chon_ngay(app, "po")
    phongonline_tinh.register(app)

    @app.callback(
        Output("po-kpi", "children"), Output("po-badge", "children"), Output("po-canh-bao", "children"),
        Output("po-mo-ta", "children"), Output("po-nv", "columnDefs"), Output("po-nv", "rowData"),
        Output("po-nv", "pinnedBottomRowData"),
        Input("po-date", "date"), Input("po-xem", "value"))
    def _cap_nhat(ngay_iso, xem):
        if not _duoc_xem() or not ngay_iso:
            raise PreventUpdate
        d = date.fromisoformat(ngay_iso)
        thang, ngay = f"{d.year}-{d.month:02d}", d.day
        tam_tinh, luc = trang_thai_ngay(ngay_iso)
        nv = po.bang_nhan_su(thang, ngay)
        rows, tong = cp.dong_nhan_su(nv)
        du_lieu = nv[nv.loai_dong == "data"]
        can_chu_y = du_lieu[du_lieu.muc_chu_y.fillna("") != ""]
        so_ngay_ngay = int((can_chu_y.muc_chu_y == quy_tac.TRAO_DOI_NGAY).sum())
        badge = ""
        if luc:
            badge = (html.Span([html.I(className="cham nhap-nhay"), f"Đang cập nhật · số lúc {luc:%H:%M}"], className="badge warn")
                     if tam_tinh else html.Span([html.I(className="cham"), "Đã chốt số"], className="badge ok"))
        canh_bao = alert([html.B(f"Ngày {ngay:02d}/{d.month:02d} đang cập nhật. "), f"Số tính đến {luc:%H:%M}."],
                         "warn") if tam_tinh and luc else ""
        mo_ta = (f"{int((du_lieu.khong_xet != 'Trưởng phòng').sum())} nhân sự · {so_ngay_ngay} trao đổi ngay · "
                 f"{len(can_chu_y) - so_ngay_ngay} theo dõi · luỹ kế 01 - {ngay:02d}/{d.month:02d}")
        return (_the(tong), badge, canh_bao, mo_ta, lk.them_giai_thich(_cot_nv(thang, ngay, tong, xem or "ban")), rows, [tong])

    @app.callback(Output("po-khtn", "columnDefs"), Output("po-khtn", "rowData"), Output("po-khtn", "pinnedBottomRowData"),
                  Output("po-khtn-mo-ta", "children"), Input("po-date", "date"), Input("po-khtn-xem", "value"))
    def _khtn(ngay_iso, xem):
        if not _duoc_xem() or not ngay_iso:
            raise PreventUpdate
        d = date.fromisoformat(ngay_iso)
        df = po.khtn_theo_ngay(f"{d.year}-{d.month:02d}", d.day)
        if df.empty:
            return [], [], [], "Chưa có nhân sự để báo cáo."
        so = {"type": "numericColumn", "valueFormatter": SO_TRONG, "minWidth": 70, "flex": 1}
        ten = {"field": "ho_ten", "headerName": "Nhân sự", "pinned": "left", "width": 190, "tooltipField": "acc",
               "cellClass": "o-dam"}
        mo_ta = f"{int(df.so_ngay_nhap.gt(0).sum())}/{len(df)} bạn đã báo KHTN trong tháng · tính đến {d:%d/%m/%Y}"
        if xem == "ngay":
            cot = [ten] + [{"field": c, "headerName": c[1:], "width": 52, "minWidth": 46, "type": "numericColumn",
                            "valueFormatter": SO_TRONG, "cellClass": "o-giua " + lop_cot_ngay(f"{d.year}-{d.month:02d}", c[1:]),
                            "headerClass": "tieu-de-giua"} for c in df.columns if c.startswith("d") and c[1:].isdigit()]
            cot += [{"field": "tb", "headerName": "TB", "pinned": "right", "width": 70, **so, "cellStyle": {"fontWeight": "700"}}]
            tong = {"ho_ten": "TỔNG", **{c: _tong(df[c]) for c in df.columns if c.startswith("d") and c[1:].isdigit()},
                    "tb": _tong(df["tb"])}
            return cot, df.to_dict("records"), [tong], mo_ta
        cot = [ten,
               {"field": "hom_nay", "headerName": f"Hôm nay {d:%d/%m}", **so, "cellStyle": {"fontWeight": "700"}},
               {"field": "hom_qua", "headerName": "Hôm qua", **so},
               {"field": "chenh", "headerName": "+/−", **so, "valueFormatter": CHENH_TRONG,
                "cellStyle": {"styleConditions": [{"condition": "params.value > 0", "style": {"color": "#1B7A4B", "fontWeight": "600"}},
                                                  {"condition": "params.value < 0", "style": {"color": "#B3261E", "fontWeight": "600"}}]}},
               {"field": "tb", "headerName": "TB tháng", **so}, {"field": "cao_nhat", "headerName": "Cao nhất", **so},
               {"field": "so_ngay_nhap", "headerName": "Số ngày đã nhập", **so}]
        df["chenh"] = df.hom_nay - df.hom_qua
        tong = {"ho_ten": "TỔNG", "hom_nay": _tong(df.hom_nay), "hom_qua": _tong(df.hom_qua), "chenh": _tong(df.chenh),
                "tb": _tong(df.tb), "cao_nhat": _tong(df.cao_nhat)}
        return cot, df.to_dict("records"), [tong], mo_ta

    @app.callback(Output("po-khtn-tai", "data"), Input("po-khtn-xls", "n_clicks"), State("po-date", "date"),
                  prevent_initial_call=True)
    def _khtn_excel(_n, ngay_iso):
        if not _duoc_xem() or not ngay_iso:
            raise PreventUpdate
        d = date.fromisoformat(ngay_iso)
        df = po.khtn_theo_ngay(f"{d.year}-{d.month:02d}", d.day)
        if df.empty:
            raise PreventUpdate
        ngay_cot = [c for c in df.columns if c.startswith("d") and c[1:].isdigit()]
        out = df[["ho_ten", "acc"]].rename(columns={"ho_ten": "Nhân sự", "acc": "Acc"})
        for c in ngay_cot:
            out[c[1:]] = df[c]
        out["Trung bình"], out["Cao nhất"], out["Số ngày đã nhập"] = df.tb, df.cao_nhat, df.so_ngay_nhap
        ghi_log("xuat_khtn_phong_online", f"{d:%d/%m/%Y}")
        return dcc.send_data_frame(out.to_excel, f"KHTN_PhongOnline_{d:%Y%m%d}.xlsx", sheet_name="KHTN", index=False)

    @app.callback(Output("po-nv-ngay", "columnDefs"), Output("po-nv-ngay", "rowData"), Output("po-ngay-mo-ta", "children"),
                  Input("po-date", "date"), Input("po-khoi", "value"), Input("po-khoi-xem", "value"))
    def _ngay_theo_nhan_su(ngay_iso, khoi, xem):
        if not _duoc_xem() or not ngay_iso:
            raise PreventUpdate
        d = date.fromisoformat(ngay_iso)
        thang = f"{d.year}-{d.month:02d}"
        df = po.so_theo_ngay(thang, d.day, khoi or "online", cong_don=xem == "congdon")
        ngay_cols = [c for c in df.columns if c.isdigit()]
        cols = [{"field": "acc", "headerName": "Acc nhân viên", "pinned": "left", "width": 170, "cellStyle": {"fontWeight": "600"}},
                {"field": "ten", "headerName": "Họ tên", "pinned": "left", "width": 170}]
        cols += [{"field": c, "headerName": c.zfill(2), "width": 48, "flex": 1, "minWidth": 44, "type": "numericColumn",
                  "cellStyle": HEAT_NGAY, "cellClass": f"o-giua {lop_cot_ngay(thang, c)}".strip(),
                  "headerClass": f"tieu-de-giua {lop_cot_ngay(thang, c)}".strip()} for c in ngay_cols]
        cols.append({"field": "Tổng", "headerName": "TỔNG", "pinned": "right", "width": 84, "type": "numericColumn",
                     "cellClass": "o-giua", "headerClass": "tieu-de-giua", "cellStyle": {"fontWeight": "700"}})
        cach = "cộng dồn từ ngày 01" if xem == "congdon" else "số của riêng từng ngày"
        mo_ta = (f"{TEN_KHOI.get(khoi or 'online')} · {int((df.loai_dong == 'data').sum())} nhân sự · 01-{d:%d/%m/%Y} · {cach}. "
                 "Tổng các nhân viên bằng số của Phòng Online.")
        return cols, df.to_dict("records"), mo_ta

    @app.callback(Output("po-nv", "dashGridOptions"), Input("po-tim", "value"), prevent_initial_call=True)
    def _tim(chu):
        if not _duoc_xem():
            raise PreventUpdate
        p = Patch()
        p["quickFilterText"] = chu or ""
        return p
