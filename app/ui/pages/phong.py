"""Trang Báo cáo phòng - Trưởng phòng theo dõi phòng mình và từng nhân sự, gửi ảnh nhóm Zalo phòng.

Quyền: Quản trị (BGĐ) chọn được mọi phòng. Trưởng phòng chỉ chọn được phòng mình phụ trách
(kiêm nhiệm thì có nhiều phòng). Nhập liệu không vào được trang này. Mọi callback đều kiểm tra lại
quyền ở máy chủ - không tin giá trị phòng gửi lên từ trình duyệt.

Bố cục theo thứ tự Trưởng phòng cần trong buổi sáng:
1. Ngày + phòng, trạng thái số (đang cập nhật / đã chốt), nút Chụp ảnh và Excel.
2. Sáu chỉ số của phòng, có hạng so với các phòng kinh doanh khác.
3. Bảng nhân sự xếp hạng trong phòng, chia hai góc nhìn vừa khít màn hình laptop:
   "Bán hàng" và "Theo dõi" (tồn, nhịp có số, NSLĐ). Dòng TỔNG PHÒNG luôn ghim ở đáy.
   Bấm một người -> ngăn chi tiết trượt ra bên phải, không phải cuộn tìm.
4. Phòng đứng ở đâu so với chi nhánh + online / bán mới từng ngày, xếp đôi trên laptop.
"""
from __future__ import annotations

from datetime import date

import dash_ag_grid as dag
import plotly.graph_objects as go
from dash import Input, Output, Patch, State, ctx, dcc, html, no_update
from flask_login import current_user

from app import bao_cao_phong as bp
from app.auth import ghi_log
from app.export_phong import anh_bao_cao_phong, xuat_bao_cao_phong
from app.metrics import cac_ngay_co_du_lieu
from app.org import phong_order
from app.overview import trang_thai_ngay
from app.ui.components import (LOCALE_VI, alert, card, chon_ngay, chu_giai, field, gan_chon_ngay,
                               kpi, seg_control)
from app.ui.icons import icon

SO = {"function": "params.value == null ? '' : Number(params.value).toLocaleString('vi-VN')"}
PCT = {"function": "params.value == null ? '–' : Math.round(params.value) + '%'"}
CHENH = {"function": "params.value == null ? '' : (params.value > 0 ? '+' : '') + params.value"}
DO, VANG, XANH = ({"backgroundColor": "#F7BDBD", "color": "#7F1D1D", "fontWeight": "600"},
                  {"backgroundColor": "#FCEBB4", "color": "#6B5104"},
                  {"backgroundColor": "#D3EBD4", "color": "#14532D", "fontWeight": "600"})
ROW_STYLE = {"styleConditions": [
    {"condition": "params.node.rowPinned", "style": {"backgroundColor": "#DCE8F4", "fontWeight": "700",
                                                     "color": "#003057"}}]}

DINH_NGHIA = [
    ("Online", "Hợp đồng Internet có ngày online trong kỳ (01 đến ngày chọn), theo acc người bán."),
    ("Cùng kỳ", "Online của chính người đó cùng số ngày tháng trước."),
    ("VVIP/PTTB · Camera/PTTB", "Số V.VIP (Camera) online trong kỳ chia số online - cùng cách tính "
                                "với Báo cáo Tổng. Một hợp đồng lắp nhiều camera nên có thể trên 100%."),
    ("Đủ 3 DV", "Hợp đồng online có cả V.VIP và Camera."),
    ("Trả trước", "Hợp đồng có trả trước 3, 6 hoặc 12 tháng."),
    ("Online trong 1 ngày", "Online ngay trong ngày tạo hợp đồng hoặc hôm sau."),
    ("Chưa online · Chờ từ 7 ngày", "Hợp đồng đã tạo, chưa online, còn trong file mới nhất; "
                                    "số ngày tính từ ngày tạo."),
    ("Ngày liền chưa có số", "Số ngày tính từ lần có số online gần nhất đến ngày chọn."),
    ("Hạng", "Xếp theo số online trong phòng; bằng số thì đồng hạng."),
    ("Cần chú ý", f"Từ {bp.NGAY_LIEN_CANH_BAO} ngày liền chưa có số, tuần này giảm từ một nửa, "
                  f"từ {bp.TON_LAU_CANH_BAO} hợp đồng chờ online từ 7 ngày, có số mà chưa bán kèm."),
]


def phong_duoc_chon() -> list[dict]:
    """Các phòng tài khoản hiện tại được xem chi tiết nhân sự."""
    pham_vi = current_user.phong_nhan_su()
    ds = phong_order()
    if pham_vi is not None:
        ds = [p for p in ds if p["code"] in set(pham_vi)]
    return [{"label": p["ten"], "value": p["code"]} for p in ds]


def duoc_xem_phong(code: str | None) -> bool:
    return bool(code) and code in {o["value"] for o in phong_duoc_chon()}


def topbar():
    return [html.Div([html.H1("Báo cáo phòng"),
                      html.Div("Kết quả của phòng và từng nhân sự, luỹ kế tháng", className="sub")]),
            html.Div(className="spacer"),
            html.Div(id="bp-badge")]


def layout():
    if not current_user.duoc_xem_nhan_su:
        return alert("Tài khoản này không có quyền xem chi tiết nhân sự.", "bad")
    lua_chon = phong_duoc_chon()
    if not lua_chon:
        return alert("Tài khoản chưa được gán phòng phụ trách. Liên hệ quản trị để được gán phòng.",
                     "warn")
    ngays = cac_ngay_co_du_lieu()
    return html.Div([
        html.Div([
            field("Ngày báo cáo", chon_ngay("bp", ngays)),
            field("Phòng", dcc.Dropdown(id="bp-phong", options=lua_chon, value=lua_chon[0]["value"],
                                        clearable=False, searchable=len(lua_chon) > 6,
                                        disabled=len(lua_chon) == 1, style={"width": "210px"})),
            html.Div(className="grow"),
            field(" ", html.Div([
                html.Button([icon("camera", 14), html.Span("Chụp ảnh")], id="bp-png",
                            className="btn primary", title="Ảnh PNG gửi nhóm Zalo của phòng"),
                html.Button([icon("download", 14), html.Span("Excel")], id="bp-xls", className="btn",
                            title="File Excel đủ mọi chỉ số của từng nhân sự"),
            ], style={"display": "flex", "gap": "8px"})),
        ], className="toolbar loc-trang"),
        dcc.Download(id="bp-tai-xuong"),

        html.Div(id="bp-canh-bao"),
        dcc.Loading(html.Div(id="bp-kpi", className="kpi-row kpi-6"), type="dot"),

        html.Div([
            html.Div([
                html.Div([html.H3("Nhân sự của phòng", style={"margin": 0}),
                          html.Div(id="bp-mo-ta-nv", className="desc", style={"margin": "2px 0 0"})]),
                html.Div(className="grow"),
                dcc.Input(id="bp-tim", type="search", placeholder="Tìm tên hoặc acc…",
                          className="o-tim"),
                seg_control("bp-xem", [("ban", "Bán hàng"), ("theo_doi", "Nhịp có số & tồn"),
                                       ("tat_ca", "Tất cả cột")], "ban"),
                dcc.Dropdown(id="bp-loc", clearable=False, value="all", searchable=False,
                             style={"width": "190px"},
                             options=[{"label": "Tất cả nhân sự", "value": "all"},
                                      {"label": "Chỉ người cần chú ý", "value": "chu_y"}]),
            ], className="the-thanh"),
            dcc.Loading(dag.AgGrid(
                id="bp-nv", className="ag-theme-quartz ag-theme-ftel", columnDefs=[], rowData=[],
                defaultColDef={"resizable": True, "sortable": True, "suppressMovable": True,
                               "wrapHeaderText": True, "autoHeaderHeight": True},
                dashGridOptions={"suppressCellFocus": True, "domLayout": "autoHeight",
                                 "tooltipShowDelay": 300, "localeText": LOCALE_VI,
                                 "rowStyle": {"cursor": "pointer"}},
                getRowId="params.data.acc_norm",
                getRowStyle=ROW_STYLE, style={"width": "100%"})),
            html.Div("Bấm vào một nhân sự để mở chi tiết. Màu VVIP/PTTB, Camera/PTTB so với mức "
                     "chung của phòng: xanh cao hơn từ 5 điểm, vàng thấp hơn 5-10 điểm, đỏ thấp hơn "
                     "từ 10 điểm.", className="desc", style={"margin": "10px 0 4px"}),
            chu_giai("Cách tính các cột", DINH_NGHIA),
        ], className="card"),

        html.Div([
            html.Div(html.Div([
                html.H3("Phòng đứng ở đâu so với chi nhánh"),
                html.Div(id="bp-mo-ta-ss", className="desc"),
                dcc.Loading(dag.AgGrid(
                    id="bp-so-sanh", className="ag-theme-quartz ag-theme-ftel", columnDefs=[],
                    rowData=[], defaultColDef={"resizable": True, "sortable": False,
                                               "suppressMovable": True},
                    dashGridOptions={"suppressCellFocus": True, "domLayout": "autoHeight",
                                     "localeText": LOCALE_VI},
                    style={"width": "100%"}))], className="card"), className="chart-col"),
            html.Div(card([dcc.Loading(dcc.Graph(id="bp-ngay", config={"displayModeBar": False,
                                                                       "responsive": True},
                                                 style={"width": "100%"}))],
                          title="Online và bán mới từng ngày",
                          desc="Cột xanh là online, cột cam là hợp đồng tạo mới; đường chấm là "
                               "mục tiêu ngày"), className="chart-col"),
        ], className="chart-row doi"),

        # ngăn chi tiết nhân sự
        html.Div([
            html.Div(id="bp-ngan-nen", className="ngan-nen"),
            html.Div([
                html.Div([html.Div(id="bp-ngan-tieu-de", className="grow"),
                          html.Button("×", id="bp-ngan-dong", className="modal-x", title="Đóng")],
                         className="ngan-dau"),
                dcc.Loading(html.Div(id="bp-ngan-than", className="ngan-than")),
            ], className="ngan-hop"),
        ], id="bp-ngan", className="ngan"),
    ])


# ------------------------------------------------------------------ cột
def _mau_ty_le(chung) -> dict:
    if chung is None:
        return {}
    goc = "params.value != null && !params.node.rowPinned && "
    return {"styleConditions": [
        {"condition": goc + f"params.value <= {chung - 10}", "style": DO},
        {"condition": goc + f"params.value < {chung - 5}", "style": VANG},
        {"condition": goc + f"params.value >= {chung + 5}", "style": XANH}]}


def _cot_nv(thang: str, ngay: int, tong: dict, xem: str) -> list:
    m = int(thang[5:7])
    goc = "params.value != null && !params.node.rowPinned && "

    def so(field_, ten, w=74, **kw):
        return {"field": field_, "headerName": ten, "minWidth": w, "flex": 1,
                "type": "numericColumn", "valueFormatter": SO, **kw}

    def pct(field_, ten, tip, w=78, **kw):
        return {"field": field_, "headerName": ten, "headerTooltip": tip, "minWidth": w, "flex": 1,
                "type": "numericColumn", "valueFormatter": PCT, **kw}

    hang = {"field": "hang", "headerName": "Hạng", "pinned": "left", "width": 68,
            "type": "numericColumn", "sort": "asc"}
    ten = {"field": "ho_ten", "headerName": "Nhân sự", "pinned": "left", "minWidth": 150,
           "flex": 1.6, "tooltipField": "acc", "cellStyle": {"fontWeight": "600"}}
    chu_y = {"field": "chu_y", "headerName": "Cần chú ý", "minWidth": 160, "flex": 3,
             "tooltipField": "chu_y", "cellStyle": {"color": "#93241C"}}
    c = {
        "tham_nien": {"field": "tham_nien_bucket", "headerName": "Thâm niên", "minWidth": 80,
                      "flex": .8},
        "online": so("online", "Online", cellStyle={"fontWeight": "700"}),
        "ck": so("ck_online", f"Cùng kỳ {bp.thang_truoc_nhan(thang)}", 72),
        "chenh": so("chenh_ck", "+/−", 58, valueFormatter=CHENH, headerTooltip="Online so với cùng kỳ",
                    cellStyle={"styleConditions": [
                        {"condition": goc + "params.value > 0", "style": {"color": "#0A7A3D",
                                                                          "fontWeight": "600"}},
                        {"condition": goc + "params.value < 0", "style": {"color": "#B42318",
                                                                          "fontWeight": "600"}}]}),
        "vvip": so("vvip", "V.VIP"),
        "kem_vvip": pct("kem_vvip", "VVIP/PTTB", "Số V.VIP / số online",
                        cellStyle=_mau_ty_le(tong.get("kem_vvip"))),
        "camera": so("camera", "Camera"),
        "kem_camera": pct("kem_camera", "Camera/PTTB", "Số camera / số online",
                          cellStyle=_mau_ty_le(tong.get("kem_camera"))),
        "ban_moi_ngay": so("ban_moi_ngay", "Bán mới"),
        "online_ngay": so("online_ngay", "Online"),
        "ban_moi": so("ban_moi", "Bán mới tháng", 84),
        "so_ngay": so("so_ngay_co_so", "Số ngày có số", 70),
        "ngay_lien": so("ngay_lien_chua_co_so", "Ngày liền chưa có số", 84,
                        cellStyle={"styleConditions": [
                            {"condition": goc + "params.value >= 7", "style": DO},
                            {"condition": goc + f"params.value >= {bp.NGAY_LIEN_CANH_BAO}",
                             "style": VANG}]}),
        "tuan_nay": so("tuan_nay", "Tuần này"),
        "tuan_truoc": so("tuan_truoc", "Tuần trước"),
        "ton": so("ton", "Chưa online", 72),
        "ton7": so("ton_qua_7", "Chờ từ 7 ngày", 78, cellStyle={"styleConditions": [
            {"condition": goc + f"params.value >= {bp.TON_LAU_CANH_BAO}", "style": DO},
            {"condition": goc + "params.value > 0", "style": VANG}]}),
        "onl1": pct("onl_1_ngay", "Online trong 1 ngày", "Online trong ngày tạo hoặc hôm sau", 80),
        "du3": pct("du_3", "Đủ 3 DV", "Hợp đồng online có cả V.VIP và Camera"),
        "tra_truoc": pct("tra_truoc", "Trả trước", "Có trả trước 3, 6 hoặc 12 tháng"),
        "nsld": {"field": "ket_luan", "headerName": "NSLĐ kỳ trước", "minWidth": 86, "flex": .9,
                 "cellStyle": {"styleConditions": [
                     {"condition": "params.value == 'NOT OK'", "style": DO}]}},
    }
    nhom_thang = {"headerName": f"LUỸ KẾ THÁNG {m}", "children": []}
    nhom_ngay = {"headerName": f"NGÀY {ngay:02d}/{m:02d}", "children": [c["ban_moi_ngay"],
                                                                        c["online_ngay"]]}
    if xem == "ban":
        nhom_thang["children"] = [c[k] for k in ("online", "ck", "chenh", "vvip", "kem_vvip",
                                                 "camera", "kem_camera")]
        return [hang, ten, nhom_thang, nhom_ngay, chu_y]
    if xem == "theo_doi":
        return [hang, ten, c["tham_nien"],
                {"headerName": "NHỊP CÓ SỐ", "children": [c["so_ngay"], c["ngay_lien"],
                                                          c["tuan_nay"], c["tuan_truoc"]]},
                {"headerName": "SỐ TỒN", "children": [c["ton"], c["ton7"]]},
                c["nsld"], chu_y]
    nhom_thang["children"] = [c[k] for k in ("online", "ck", "chenh", "ban_moi", "vvip", "kem_vvip",
                                             "camera", "kem_camera", "du3", "tra_truoc", "onl1")]
    return [hang, ten, c["tham_nien"], nhom_thang, nhom_ngay,
            {"headerName": "SỐ TỒN", "children": [c["ton"], c["ton7"]]},
            {"headerName": "NHỊP CÓ SỐ", "children": [c["so_ngay"], c["ngay_lien"], c["tuan_nay"],
                                                      c["tuan_truoc"]]},
            c["nsld"], chu_y]


COT_SO_SANH = [
    {"field": "chi_so", "headerName": "Chỉ số", "minWidth": 190, "flex": 2.2},
    {"field": "gia_tri_chu", "headerName": "Phòng", "minWidth": 76, "flex": 1,
     "type": "numericColumn", "cellStyle": {"fontWeight": "700"}},
    {"field": "muc_chung_chu", "headerName": "Mức chung", "minWidth": 86, "flex": 1,
     "type": "numericColumn"},
    {"field": "chenh_chu", "headerName": "Chênh", "minWidth": 84, "flex": 1, "type": "numericColumn",
     "cellStyle": {"styleConditions": [
         {"condition": "params.data.tot === true", "style": XANH},
         {"condition": "params.data.tot === false", "style": DO}]}},
    {"field": "hang_chu", "headerName": "Hạng", "minWidth": 70, "flex": .8, "type": "numericColumn",
     "cellStyle": {"fontWeight": "700"}},
]


def _dong_so_sanh(ss) -> list[dict]:
    def chu(v, kieu, dau=False):
        if v is None:
            return "–"
        if kieu == "pct":
            return f"{v:+.0f} điểm" if dau else f"{v:.0f}%"
        if kieu == "so1":
            return f"{v:+.1f}".replace(".", ",") if dau else f"{v:.1f}".replace(".", ",")
        return f"{v:+,.0f}".replace(",", ".") if dau else f"{v:,.0f}".replace(",", ".")

    rows = []
    for r in ss.to_dict("records"):
        tot = None
        if r["chenh"] is not None and abs(r["chenh"]) >= (5 if r["kieu"] == "pct" else 0.01):
            tot = (r["chenh"] > 0) == r["cao_la_tot"]
        rows.append({"chi_so": r["chi_so"], "gia_tri_chu": chu(r["gia_tri"], r["kieu"]),
                     "muc_chung_chu": chu(r["muc_chung"], r["kieu"]),
                     "chenh_chu": chu(r["chenh"], r["kieu"], dau=True), "tot": tot,
                     "hang_chu": f"{r['hang']}/{r['so_phong']}" if r["hang"] else "–"})
    return rows


def _pct(v) -> str:
    return "–" if v is None else f"{float(v):.0f}%"


def _so(v) -> str:
    return f"{int(v or 0):,}".replace(",", ".")


def _kpis(thang: str, ngay: int, dong: dict, ss, tam_tinh: bool) -> list:
    hang = ss.set_index("khoa")
    h_htkh = hang.loc["htkh_internet"]
    h = h_htkh if h_htkh.hang else hang.loc["online"]
    tt = dong.get("tang_truong")
    kl = dong.get("ket_luan")
    return [
        kpi("Online tháng", _so(dong.get("online")),
            f"Mục tiêu {_so(dong.get('mt_internet'))} · HTKH {_pct(dong.get('htkh_internet'))}"
            if dong.get("mt_internet") else "Chưa nhập chỉ tiêu tháng"),
        kpi("Tăng trưởng", "–" if tt is None else f"{tt:+.0f}%",
            f"Cùng kỳ {bp.thang_truoc_nhan(thang)}: {_so(dong.get('ck_online'))} online",
            "" if tt is None else ("ok" if tt >= 0 else "bad")),
        kpi("VVIP/PTTB", _pct(dong.get("vvip_ty_le")), f"{_so(dong.get('vvip'))} V.VIP"),
        kpi("Camera", _so(dong.get("camera")),
            f"Mục tiêu {_so(dong.get('mt_camera'))} · HTKH {_pct(dong.get('htkh_camera'))}"
            if dong.get("mt_camera") else "Chưa nhập chỉ tiêu camera"),
        kpi(f"Online ngày {ngay:02d}/{thang[5:7]}", _so(dong.get("ngay_online")),
            f"Mục tiêu {_so(dong.get('mt_ngay'))} · {kl}" if dong.get("mt_ngay")
            else f"Bán mới {_so(dong.get('ngay_ban_moi'))}",
            "" if not dong.get("mt_ngay") else
            ("ok" if kl == "Đạt" else ("warn" if tam_tinh else "bad"))),
        kpi("Hạng phòng", f"{h.hang}/{h.so_phong}" if h.hang else "–",
            ("Theo tỷ lệ HTKH" if h is h_htkh else "Theo số online") + " · phòng kinh doanh",
            "" if not h.hang else ("ok" if h.hang <= h.so_phong / 3 else
                                   ("bad" if h.hang > h.so_phong * 2 / 3 else "warn"))),
    ]


def _fig(fig: go.Figure, height: int = 330) -> go.Figure:
    fig.update_layout(height=height, autosize=True, margin=dict(l=8, r=8, t=30, b=8),
                      font=dict(family="Inter, Segoe UI, sans-serif", size=12, color="#1B2733"),
                      plot_bgcolor="white", paper_bgcolor="white", bargap=.25,
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                      hovermode="x unified")
    fig.update_xaxes(showgrid=False, linecolor="#E4E9F0", dtick=1)
    fig.update_yaxes(gridcolor="#F1F5F9", zeroline=False, rangemode="tozero")
    return fig


def _bieu_do(d, mt_ngay=None, height: int = 330) -> go.Figure:
    fig = go.Figure()
    if len(d):
        fig.add_trace(go.Bar(x=d.ngay, y=d.online, name="Online", marker_color="#0072BC",
                             hovertemplate="%{y} online<extra></extra>"))
        fig.add_trace(go.Bar(x=d.ngay, y=d.ban_moi, name="Bán mới", marker_color="#F5A25D",
                             hovertemplate="%{y} bán mới<extra></extra>"))
        if mt_ngay:
            fig.add_hline(y=float(mt_ngay), line_dash="dot", line_color="#C8372D",
                          annotation_text=f"Mục tiêu ngày {mt_ngay:.0f}",
                          annotation_position="top left")
        fig.update_layout(barmode="group")
    return _fig(fig, height)


def _o(nhan: str, so: str, phu: str = "") -> html.Div:
    return html.Div([html.Div(nhan, className="nhan"), html.Div(so, className="so"),
                     html.Div(phu, className="phu")], className="ct-o")


def _ngan_noi_dung(thang: str, ngay: int, code: str, r: dict):
    ds = bp.dien_bien_nhan_su(thang, ngay, r["acc_norm"])
    cho = bp.hop_dong_cho_cua_nhan_su(r["acc_norm"], code)
    ghi_log("xem_nhan_su", f"{code}: {r.get('acc')}")
    chenh = r.get("chenh_ck") or 0
    ngay_lien = r.get("ngay_lien_chua_co_so")
    chu_y = [x for x in (r.get("chu_y") or "").split(" · ") if x]

    hang = r.get("hang")
    tieu_de = html.Div([html.H3(f"{r.get('ho_ten')}" + (f" · hạng {int(hang)}" if hang else "")),
                        html.Div(f"{r.get('acc')} · {bp.ten_phong(code)} · thâm niên "
                                 f"{r.get('tham_nien_bucket') or '–'} tháng · "
                                 f"{r.get('vi_tri') or 'chưa có hồ sơ NSLĐ'}", className="sub")])
    than = [
        html.Div([html.Span(x, className="ct-chip") for x in chu_y] if chu_y else
                 [html.Span("Không có điểm cần chú ý", className="ct-chip ok")],
                 style={"marginBottom": "8px"}),
        html.Div([
            _o("Online tháng", _so(r.get("online")),
               f"Cùng kỳ {_so(r.get('ck_online'))} ({'+' if chenh > 0 else ''}{chenh})"),
            _o("Bán mới tháng", _so(r.get("ban_moi")),
               f"Ngày {ngay:02d}: bán mới {_so(r.get('ban_moi_ngay'))}, online "
               f"{_so(r.get('online_ngay'))}"),
            _o("Số ngày có số", f"{int(r.get('so_ngay_co_so') or 0)}/{ngay}",
               "Chưa có số trong 2 tháng" if ngay_lien is None else
               ("Có số ngày gần nhất" if ngay_lien == 0 else f"{ngay_lien} ngày liền chưa có số")),
            _o("V.VIP", _so(r.get("vvip")), f"VVIP/PTTB {_pct(r.get('kem_vvip'))}"),
            _o("Camera", _so(r.get("camera")), f"Camera/PTTB {_pct(r.get('kem_camera'))}"),
            _o("Chưa online", _so(r.get("ton")), f"{_so(r.get('ton_qua_7'))} hợp đồng chờ từ 7 ngày"),
            _o("Online trong 1 ngày", _pct(r.get("onl_1_ngay")), "Trong ngày tạo hoặc hôm sau"),
            _o("Đủ 3 DV · Trả trước", f"{_pct(r.get('du_3'))} · {_pct(r.get('tra_truoc'))}"),
            _o("Tuần này", _so(r.get("tuan_nay")), f"Tuần trước {_so(r.get('tuan_truoc'))} · NSLĐ kỳ "
                                                   f"trước {r.get('ket_luan') or '–'}"),
        ], className="ct-luoi"),
        html.H4("Online và bán mới từng ngày"),
        dcc.Graph(figure=_bieu_do(ds, height=250), config={"displayModeBar": False,
                                                           "responsive": True}),
        html.H4(f"Hợp đồng chưa online ({len(cho)})"),
        dag.AgGrid(
            className="ag-theme-quartz ag-theme-ftel", rowData=cho.to_dict("records"),
            columnDefs=[{"field": "hop_dong", "headerName": "Hợp đồng", "flex": 1, "minWidth": 110},
                        {"field": "goi_dich_vu", "headerName": "Gói", "flex": .8, "minWidth": 80},
                        {"field": "nguon_ban", "headerName": "Nguồn", "flex": .8, "minWidth": 80},
                        {"field": "ngay_tao", "headerName": "Ngày tạo", "flex": 1, "minWidth": 100},
                        {"field": "so_ngay_cho", "headerName": "Số ngày chờ", "flex": .8,
                         "minWidth": 90, "type": "numericColumn",
                         "cellStyle": {"styleConditions": [
                             {"condition": "params.value >= 7", "style": DO}]}}],
            dashGridOptions={"suppressCellFocus": True, "domLayout": "autoHeight",
                             "pagination": True, "paginationPageSize": 10,
                             "paginationPageSizeSelector": False, "localeText": LOCALE_VI},
            style={"width": "100%"}) if len(cho) else
        html.Div("Không có hợp đồng nào đang chờ online.", className="desc"),
    ]
    return tieu_de, than


# ------------------------------------------------------------------ callback
def register(app):
    gan_chon_ngay(app, "bp")

    @app.callback(
        Output("bp-kpi", "children"), Output("bp-badge", "children"),
        Output("bp-canh-bao", "children"), Output("bp-mo-ta-nv", "children"),
        Output("bp-nv", "columnDefs"), Output("bp-nv", "rowData"),
        Output("bp-nv", "pinnedBottomRowData"),
        Output("bp-so-sanh", "columnDefs"), Output("bp-so-sanh", "rowData"),
        Output("bp-mo-ta-ss", "children"), Output("bp-ngay", "figure"),
        Input("bp-date", "date"), Input("bp-phong", "value"), Input("bp-loc", "value"),
        Input("bp-xem", "value"))
    def _cap_nhat(ngay_iso, code, loc, xem):
        if not duoc_xem_phong(code) or not ngay_iso:
            chan = alert("Không có quyền xem phòng này." if ngay_iso else "Chưa có số liệu.", "bad")
            return [], "", chan, "", [], [], [], [], [], "", go.Figure()
        d = date.fromisoformat(ngay_iso)
        thang, ngay = f"{d.year}-{d.month:02d}", d.day
        tam_tinh, luc = trang_thai_ngay(ngay_iso)

        nv = bp.bang_nhan_su(thang, ngay, code)
        ss, dong = bp.so_sanh_phong(thang, ngay, code, tam_tinh)
        tong = nv[nv.loai_dong == "total"].iloc[0].to_dict()
        du_lieu = nv[nv.loai_dong == "data"]
        can_chu_y = du_lieu[du_lieu.chu_y.fillna("") != ""]
        hien = can_chu_y if loc == "chu_y" else du_lieu

        badge = ""
        if luc:
            badge = (html.Span([html.I(className="cham nhap-nhay"),
                                f"Đang cập nhật · số lúc {luc:%H:%M}"], className="badge warn")
                     if tam_tinh else
                     html.Span([html.I(className="cham"), "Đã chốt số"], className="badge ok",
                               title=f"Lần nạp số gần nhất: {luc:%H:%M %d/%m/%Y}"))
        canh_bao = alert([html.B(f"Ngày {ngay:02d}/{d.month:02d} đang cập nhật. "),
                          f"Số tính đến {luc:%H:%M}, phòng chưa đủ mục tiêu ngày ghi “Chưa đạt”."],
                         "warn") if tam_tinh else ""
        mo_ta = (f"{len(du_lieu)} nhân sự · {len(can_chu_y)} người cần chú ý · luỹ kế 01 - "
                 f"{ngay:02d}/{d.month:02d}")
        so_phong = int(ss.so_phong.max() or 0)
        mo_ta_ss = (f"Hạng trong {so_phong} phòng kinh doanh (IBB và địa bàn). Mức chung với tỷ lệ "
                    "là của toàn chi nhánh, với số lượng là bình quân một phòng.")
        return (_kpis(thang, ngay, dong, ss, tam_tinh), badge, canh_bao, mo_ta,
                _cot_nv(thang, ngay, tong, xem or "ban"), hien.to_dict("records"), [tong],
                COT_SO_SANH, _dong_so_sanh(ss), mo_ta_ss,
                _bieu_do(bp.dien_bien_ngay(thang, ngay, code), dong.get("mt_ngay")))

    @app.callback(Output("bp-nv", "dashGridOptions"), Input("bp-tim", "value"),
                  prevent_initial_call=True)
    def _tim(chu):
        p = Patch()
        p["quickFilterText"] = chu or ""
        return p

    @app.callback(Output("bp-ngan", "className"), Output("bp-ngan-tieu-de", "children"),
                  Output("bp-ngan-than", "children"),
                  Input("bp-nv", "cellClicked"), Input("bp-ngan-dong", "n_clicks"),
                  Input("bp-ngan-nen", "n_clicks"), Input("bp-phong", "value"),
                  Input("bp-date", "date"), prevent_initial_call=True)
    def _ngan(o, _dong, _nen, code, ngay_iso):
        if ctx.triggered_id != "bp-nv":
            return "ngan", no_update, no_update
        acc = (o or {}).get("rowId")              # getRowId = acc_norm của nhân sự
        if not acc or acc == "TOTAL" or not duoc_xem_phong(code) or not ngay_iso:
            return no_update, no_update, no_update
        d = date.fromisoformat(ngay_iso)
        thang = f"{d.year}-{d.month:02d}"
        # tính lại ở máy chủ: chỉ mở nếu người này đúng là nhân sự của phòng được phép xem
        nv = bp.bang_nhan_su(thang, d.day, code)
        r = nv[(nv.acc_norm == acc) & (nv.loai_dong == "data")]
        if r.empty:
            return no_update, no_update, no_update
        tieu_de, than = _ngan_noi_dung(thang, d.day, code, r.iloc[0].to_dict())
        return "ngan mo", tieu_de, than

    @app.callback(Output("bp-tai-xuong", "data"), Input("bp-png", "n_clicks"),
                  Input("bp-xls", "n_clicks"), State("bp-date", "date"), State("bp-phong", "value"),
                  prevent_initial_call=True)
    def _tai_ve(_a, _b, ngay_iso, code):
        if not duoc_xem_phong(code) or not ngay_iso:
            return no_update
        d = date.fromisoformat(ngay_iso)
        thang = f"{d.year}-{d.month:02d}"
        tam_tinh, luc = trang_thai_ngay(ngay_iso)
        la_anh = ctx.triggered_id == "bp-png"
        ham = anh_bao_cao_phong if la_anh else xuat_bao_cao_phong
        noi_dung, ten = ham(thang, d.day, code, tam_tinh=tam_tinh, luc=luc)
        ghi_log("xuat_bao_cao_phong", f"{'png' if la_anh else 'xlsx'} {code} {ngay_iso}")
        return dcc.send_bytes(noi_dung, ten)
