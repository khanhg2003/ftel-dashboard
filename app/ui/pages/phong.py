"""Trang Báo cáo phòng - Trưởng phòng theo dõi phòng mình và từng nhân sự, gửi ảnh nhóm Zalo phòng.

Quyền: Quản trị (BGĐ) chọn được mọi phòng. Trưởng phòng chỉ chọn được phòng mình phụ trách
(kiêm nhiệm thì có nhiều phòng). Nhập liệu không vào được trang này. Mọi callback đều kiểm tra lại
quyền ở máy chủ - không tin giá trị phòng gửi lên từ trình duyệt.

Bố cục theo thứ tự Trưởng phòng cần trong buổi sáng:
1. Ngày + phòng, trạng thái số (đang cập nhật / đã chốt), nút Chụp ảnh và Excel.
2. Sáu chỉ số của phòng, có hạng so với các phòng cùng nhóm.
3. Bảng nhân sự (hạng trong phòng) - bấm một người để xem chi tiết ngay bên dưới.
4. Phòng đứng ở đâu so với chi nhánh theo từng chỉ số + diễn biến online từng ngày.
"""
from __future__ import annotations

from datetime import date

import dash_ag_grid as dag
import plotly.graph_objects as go
from dash import Input, Output, State, ctx, dcc, html, no_update
from flask_login import current_user

from app import bao_cao_phong as bp
from app.auth import ghi_log
from app.export_phong import anh_bao_cao_phong, xuat_bao_cao_phong
from app.metrics import cac_ngay_co_du_lieu
from app.org import phong_order
from app.overview import trang_thai_ngay
from app.ui.components import alert, card, field, kpi
from app.ui.icons import icon

SO = {"function": "params.value == null ? '' : Number(params.value).toLocaleString('vi-VN')"}
PCT = {"function": "params.value == null ? '–' : Math.round(params.value) + '%'"}
ROW_STYLE = {"styleConditions": [
    {"condition": "params.data.loai_dong == 'total'",
     "style": {"backgroundColor": "#DCE8F4", "fontWeight": "700", "color": "#003057"}}]}
DO, VANG, XANH = ({"backgroundColor": "#F7BDBD", "color": "#7F1D1D", "fontWeight": "600"},
                  {"backgroundColor": "#FCEBB4", "color": "#6B5104"},
                  {"backgroundColor": "#D3EBD4", "color": "#14532D", "fontWeight": "600"})


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
    moi_nhat = ngays[-1] if ngays else None
    return html.Div([
        html.Div([
            field("Ngày báo cáo", html.Div([
                html.Button("‹", id="bp-lui", className="nut-ky", title="Ngày trước đó"),
                dcc.DatePickerSingle(id="bp-date", date=moi_nhat, display_format="DD/MM/YYYY",
                                     min_date_allowed=ngays[0] if ngays else None,
                                     max_date_allowed=moi_nhat, initial_visible_month=moi_nhat,
                                     first_day_of_week=1, clearable=False, className="date-pick"),
                html.Button("›", id="bp-toi", className="nut-ky", title="Ngày sau đó"),
                html.Button("Mới nhất", id="bp-moinhat", className="btn nho"),
            ], className="chon-ngay")),
            field("Phòng", dcc.Dropdown(id="bp-phong", options=lua_chon, value=lua_chon[0]["value"],
                                        clearable=False, searchable=len(lua_chon) > 6,
                                        disabled=len(lua_chon) == 1, style={"width": "220px"})),
            html.Div(className="grow"),
            field(" ", html.Div([
                html.Button([icon("camera", 14), html.Span("Chụp ảnh")], id="bp-png",
                            className="btn primary", title="Ảnh PNG gửi nhóm Zalo của phòng"),
                html.Button([icon("download", 14), html.Span("Excel")], id="bp-xls", className="btn",
                            title="File Excel đủ mọi chỉ số của từng nhân sự"),
            ], style={"display": "flex", "gap": "8px"})),
        ], className="toolbar loc-trang"),
        dcc.Download(id="bp-tai-xuong"),
        dcc.Store(id="bp-chon-nv"),

        html.Div(id="bp-canh-bao"),
        html.Div(id="bp-kpi", className="kpi-row kpi-6"),

        card([
            html.Div([
                html.Div(id="bp-mo-ta-nv", className="desc", style={"margin": 0}),
                html.Div(className="grow"),
                dcc.Dropdown(id="bp-loc", clearable=False, value="all", searchable=False,
                             style={"width": "210px"},
                             options=[{"label": "Tất cả nhân sự", "value": "all"},
                                      {"label": "Chỉ người cần chú ý", "value": "chu_y"}]),
            ], className="toolbar", style={"marginBottom": "10px"}),
            dcc.Loading(dag.AgGrid(
                id="bp-nv", className="ag-theme-quartz ag-theme-ftel", columnDefs=[], rowData=[],
                defaultColDef={"resizable": True, "sortable": True, "suppressMovable": True,
                               "wrapHeaderText": True, "autoHeaderHeight": True},
                dashGridOptions={"suppressCellFocus": True, "domLayout": "autoHeight",
                                 "rowSelection": "single", "tooltipShowDelay": 300},
                getRowStyle=ROW_STYLE, style={"width": "100%"})),
            html.Div("Bấm vào một nhân sự để xem chi tiết. Màu VVIP/PTTB, Camera/PTTB so với mức chung "
                     "của phòng: xanh cao hơn từ 5 điểm, đỏ thấp hơn từ 10 điểm.",
                     className="desc", style={"margin": "10px 0 0"}),
        ], title="Nhân sự của phòng"),

        html.Div(id="bp-chi-tiet"),

        html.Div([
            html.Div(card([dcc.Loading(dag.AgGrid(
                id="bp-so-sanh", className="ag-theme-quartz ag-theme-ftel", columnDefs=[],
                rowData=[], defaultColDef={"resizable": True, "sortable": False,
                                           "suppressMovable": True},
                dashGridOptions={"suppressCellFocus": True, "domLayout": "autoHeight"},
                style={"width": "100%"}))],
                title="Phòng đứng ở đâu so với chi nhánh",
                desc="Hạng so với các phòng cùng nhóm. Mức chung là tỷ lệ của toàn chi nhánh; "
                     "với số lượng là bình quân một phòng."), className="chart-col"),
            html.Div(card([dcc.Loading(dcc.Graph(id="bp-ngay", config={"displayModeBar": False,
                                                                       "responsive": True},
                                                 style={"width": "100%"}))],
                          title="Online từng ngày của phòng",
                          desc="Đường cam là mục tiêu ngày"), className="chart-col"),
        ], className="chart-row"),
    ])


# ------------------------------------------------------------------ cột
def _mau_ty_le(chung) -> dict:
    if chung is None:
        return {}
    goc = "params.data.loai_dong == 'data' && params.value != null && "
    return {"styleConditions": [
        {"condition": goc + f"params.value <= {chung - 10}", "style": DO},
        {"condition": goc + f"params.value < {chung - 5}", "style": VANG},
        {"condition": goc + f"params.value >= {chung + 5}", "style": XANH}]}


def _cot_nv(thang: str, ngay: int, tong: dict) -> list:
    m = int(thang[5:7])

    def so(field_, ten, w=76, **kw):
        return {"field": field_, "headerName": ten, "minWidth": w, "flex": 1,
                "type": "numericColumn", "valueFormatter": SO, **kw}

    def pct(field_, ten, tip, **kw):
        return {"field": field_, "headerName": ten, "headerTooltip": tip, "minWidth": 84, "flex": 1,
                "type": "numericColumn", "valueFormatter": PCT, **kw}

    goc = "params.data.loai_dong == 'data' && params.value != null && "
    return [
        {"field": "hang", "headerName": "Hạng", "pinned": "left", "width": 70,
         "type": "numericColumn", "sort": "asc"},
        {"field": "ho_ten", "headerName": "Nhân sự", "pinned": "left", "minWidth": 180,
         "tooltipField": "acc", "cellStyle": {"fontWeight": "600"}},
        {"field": "tham_nien_bucket", "headerName": "Thâm niên", "minWidth": 84, "flex": .8},
        {"headerName": f"LUỸ KẾ THÁNG {m}", "children": [
            so("online", "Online", cellStyle={"fontWeight": "700"}),
            so("ck_online", f"Cùng kỳ {bp.thang_truoc_nhan(thang)}", 84),
            so("vvip", "V.VIP"),
            pct("kem_vvip", "VVIP/PTTB", "Số V.VIP / số online", cellStyle=_mau_ty_le(tong.get("kem_vvip"))),
            so("camera", "Camera"),
            pct("kem_camera", "Camera/PTTB", "Số camera / số online",
                cellStyle=_mau_ty_le(tong.get("kem_camera"))),
            pct("du_3", "Đủ 3 DV", "Hợp đồng online có cả V.VIP và Camera"),
            pct("tra_truoc", "Trả trước", "Hợp đồng có trả trước 3, 6 hoặc 12 tháng"),
        ]},
        {"headerName": f"NGÀY {ngay:02d}/{m:02d}", "children": [
            so("ban_moi_ngay", "Bán mới"), so("online_ngay", "Online")]},
        {"headerName": "SỐ TỒN", "children": [
            so("ton", "Chưa online", 84),
            so("ton_qua_7", "Chờ từ 7 ngày", 90, cellStyle={"styleConditions": [
                {"condition": goc + "params.value >= 3", "style": DO},
                {"condition": goc + "params.value > 0", "style": VANG}]})]},
        {"headerName": "THEO DÕI", "children": [
            so("ngay_lien_chua_co_so", "Ngày liền chưa có số", 96, cellStyle={"styleConditions": [
                {"condition": goc + "params.value >= 7", "style": DO},
                {"condition": goc + f"params.value >= {bp.NGAY_LIEN_CANH_BAO}", "style": VANG}]}),
            so("tuan_nay", "Tuần này"), so("tuan_truoc", "Tuần trước"),
            {"field": "ket_luan", "headerName": "NSLĐ kỳ trước", "minWidth": 90, "flex": .9,
             "cellStyle": {"styleConditions": [
                 {"condition": "params.value == 'NOT OK'", "style": DO}]}},
        ]},
        {"field": "chu_y", "headerName": "Cần chú ý", "minWidth": 260, "flex": 2.4,
         "tooltipField": "chu_y", "cellStyle": {"color": "#93241C"}},
    ]


COT_SO_SANH = [
    {"field": "chi_so", "headerName": "Chỉ số", "minWidth": 200, "flex": 2},
    {"field": "gia_tri_chu", "headerName": "Phòng", "minWidth": 80, "flex": 1,
     "type": "numericColumn", "cellStyle": {"fontWeight": "700"}},
    {"field": "muc_chung_chu", "headerName": "Mức chung", "minWidth": 90, "flex": 1,
     "type": "numericColumn"},
    {"field": "chenh_chu", "headerName": "Chênh", "minWidth": 80, "flex": 1, "type": "numericColumn",
     "cellStyle": {"styleConditions": [
         {"condition": "params.data.tot === true", "style": XANH},
         {"condition": "params.data.tot === false", "style": DO}]}},
    {"field": "hang_chu", "headerName": "Hạng", "minWidth": 80, "flex": .9, "type": "numericColumn",
     "cellStyle": {"fontWeight": "700"}},
]


def _dong_so_sanh(ss) -> list[dict]:
    def chu(v, kieu, dau=False):
        if v is None:
            return "–"
        if kieu == "pct":
            return f"{v:+.0f} điểm" if dau else f"{v:.0f}%"
        if kieu == "so1":
            return f"{v:+.1f}" if dau else f"{v:.1f}"
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
            "Theo tỷ lệ HTKH, trong các phòng cùng nhóm" if h is h_htkh
            else "Theo số online, trong các phòng cùng nhóm",
            "" if not h.hang else ("ok" if h.hang <= h.so_phong / 3 else
                                   ("bad" if h.hang > h.so_phong * 2 / 3 else "warn"))),
    ]


def _bieu_do_ngay(thang: str, ngay: int, code: str, mt_ngay) -> go.Figure:
    d = bp.dien_bien_ngay(thang, ngay, code)
    fig = go.Figure()
    if len(d):
        fig.add_trace(go.Bar(x=d.ngay, y=d.online, marker_color="#0072BC", name="Online",
                             text=d.online, textposition="outside", cliponaxis=False,
                             hovertemplate="Ngày %{x}: %{y} online<extra></extra>"))
        if mt_ngay:
            fig.add_hline(y=float(mt_ngay), line_dash="dot", line_color="#F37021",
                          annotation_text=f"Mục tiêu ngày {mt_ngay:.0f}",
                          annotation_position="top left")
        fig.update_yaxes(range=[0, max(d.online.max(), float(mt_ngay or 0)) * 1.25 + 1])
    return _fig(fig)


def _fig(fig: go.Figure, height: int = 330) -> go.Figure:
    fig.update_layout(height=height, autosize=True, margin=dict(l=8, r=8, t=10, b=8),
                      font=dict(family="Inter, Segoe UI, sans-serif", size=12, color="#1B2733"),
                      plot_bgcolor="white", paper_bgcolor="white", showlegend=False)
    fig.update_xaxes(showgrid=False, linecolor="#E4E9F0", dtick=1)
    fig.update_yaxes(gridcolor="#F1F5F9", zeroline=False)
    return fig


def _chi_tiet(thang: str, ngay: int, code: str, r: dict) -> html.Div:
    ds = bp.dien_bien_nhan_su(thang, ngay, r["acc_norm"])
    fig = go.Figure(go.Bar(x=ds.ngay, y=ds.online, marker_color="#37A5E6", text=ds.online,
                           textposition="outside", cliponaxis=False,
                           hovertemplate="Ngày %{x}: %{y} online<extra></extra>"))
    fig.update_yaxes(range=[0, (ds.online.max() or 1) * 1.3 + 1])
    cho = bp.hop_dong_cho_cua_nhan_su(r["acc_norm"], code)
    ghi_log("xem_nhan_su", f"{code}: {r.get('acc')}")

    def dong(nhan, gia_tri):
        return html.Div([html.Span(nhan, className="cg-ten"), html.B(gia_tri)], className="ct-dong")

    thong_tin = html.Div([
        dong("Acc", r.get("acc") or ""),
        dong("Thâm niên", f"{r.get('tham_nien_bucket') or '–'} tháng · {r.get('vi_tri') or ''}"),
        dong("Online tháng", f"{_so(r.get('online'))} (cùng kỳ {_so(r.get('ck_online'))})"),
        dong("Bán mới tháng", _so(r.get("ban_moi"))),
        dong("V.VIP · Camera", f"{_so(r.get('vvip'))} ({_pct(r.get('kem_vvip'))}) · "
                               f"{_so(r.get('camera'))} ({_pct(r.get('kem_camera'))})"),
        dong("Đủ 3 DV · Trả trước", f"{_pct(r.get('du_3'))} · {_pct(r.get('tra_truoc'))}"),
        dong("Online trong 1 ngày", _pct(r.get("onl_1_ngay"))),
        dong("Số ngày có số", f"{r.get('so_ngay_co_so') or 0}/{ngay} ngày"),
        dong("NSLĐ kỳ trước", f"{r.get('ket_luan') or '–'} · điểm {r.get('diem_tong') or '–'}"),
        html.Div(r.get("chu_y") or "Không có điểm cần chú ý.", className="desc",
                 style={"marginTop": "10px", "color": "#93241C" if r.get("chu_y") else None}),
    ])
    bang_cho = dag.AgGrid(
        className="ag-theme-quartz ag-theme-ftel", rowData=cho.to_dict("records"),
        columnDefs=[{"field": "hop_dong", "headerName": "Hợp đồng", "flex": 1, "minWidth": 110},
                    {"field": "goi_dich_vu", "headerName": "Gói", "flex": .8, "minWidth": 80},
                    {"field": "nguon_ban", "headerName": "Nguồn", "flex": .8, "minWidth": 80},
                    {"field": "ngay_tao", "headerName": "Ngày tạo", "flex": 1, "minWidth": 100},
                    {"field": "so_ngay_cho", "headerName": "Số ngày chờ", "flex": .8,
                     "minWidth": 90, "type": "numericColumn"}],
        dashGridOptions={"suppressCellFocus": True, "domLayout": "autoHeight", "pagination": True,
                         "paginationPageSize": 8, "paginationPageSizeSelector": False},
        style={"width": "100%"})
    return card([
        html.Div([
            html.Div(thong_tin, className="chart-col", style={"flex": "1 1 260px"}),
            html.Div(dcc.Graph(figure=_fig(fig, 260), config={"displayModeBar": False,
                                                              "responsive": True}),
                     className="chart-col", style={"flex": "2 1 420px"}),
        ], className="chart-row"),
        html.H3(f"Hợp đồng chưa online ({len(cho)})", style={"marginTop": "14px"}),
        bang_cho if len(cho) else html.Div("Không có hợp đồng nào đang chờ.", className="desc"),
    ], title=f"Chi tiết · {r.get('ho_ten')}", desc="Online từng ngày trong tháng")


# ------------------------------------------------------------------ callback
def register(app):
    @app.callback(Output("bp-date", "date"), Input("bp-lui", "n_clicks"),
                  Input("bp-toi", "n_clicks"), Input("bp-moinhat", "n_clicks"),
                  State("bp-date", "date"), prevent_initial_call=True)
    def _chon_ngay(_a, _b, _c, hien_tai):
        ngays = cac_ngay_co_du_lieu()
        if not ngays:
            return no_update
        d = hien_tai or ngays[-1]
        if ctx.triggered_id == "bp-lui":
            truoc = [x for x in ngays if x < d]
            return truoc[-1] if truoc else no_update
        if ctx.triggered_id == "bp-toi":
            sau = [x for x in ngays if x > d]
            return sau[0] if sau else no_update
        return ngays[-1]

    @app.callback(
        Output("bp-kpi", "children"), Output("bp-badge", "children"),
        Output("bp-canh-bao", "children"), Output("bp-mo-ta-nv", "children"),
        Output("bp-nv", "columnDefs"), Output("bp-nv", "rowData"),
        Output("bp-so-sanh", "columnDefs"), Output("bp-so-sanh", "rowData"),
        Output("bp-ngay", "figure"), Output("bp-chi-tiet", "children", allow_duplicate=True),
        Input("bp-date", "date"), Input("bp-phong", "value"), Input("bp-loc", "value"),
        prevent_initial_call="initial_duplicate")
    def _cap_nhat(ngay_iso, code, loc):
        if not duoc_xem_phong(code) or not ngay_iso:
            chan = alert("Không có quyền xem phòng này." if ngay_iso else "Chưa có số liệu.", "bad")
            return [], "", chan, "", [], [], [], [], go.Figure(), ""
        d = date.fromisoformat(ngay_iso)
        thang, ngay = f"{d.year}-{d.month:02d}", d.day
        tam_tinh, luc = trang_thai_ngay(ngay_iso)

        nv = bp.bang_nhan_su(thang, ngay, code)
        ss, dong = bp.so_sanh_phong(thang, ngay, code, tam_tinh)
        tong = nv[nv.loai_dong == "total"].iloc[0].to_dict()
        du_lieu = nv[nv.loai_dong == "data"]
        can_chu_y = du_lieu[du_lieu.chu_y.fillna("") != ""]
        hien = can_chu_y if loc == "chu_y" else du_lieu
        rows = hien.to_dict("records") + [tong]

        badge = (html.Span([html.I(className="cham nhap-nhay"), f"Đang cập nhật · số lúc {luc:%H:%M}"],
                           className="badge warn") if tam_tinh else
                 html.Span([html.I(className="cham"), "Đã chốt số"], className="badge ok")) \
            if luc else ""
        canh_bao = []
        if tam_tinh:
            canh_bao.append(alert([html.B(f"Ngày {ngay:02d}/{d.month:02d} đang cập nhật. "),
                                   f"Số tính đến {luc:%H:%M}."], "warn"))
        mo_ta = (f"{len(du_lieu)} nhân sự · {len(can_chu_y)} người cần chú ý · luỹ kế 01 - "
                 f"{ngay:02d}/{d.month:02d}")
        return (_kpis(thang, ngay, dong, ss, tam_tinh), badge, canh_bao, mo_ta,
                _cot_nv(thang, ngay, tong), rows, COT_SO_SANH, _dong_so_sanh(ss),
                _bieu_do_ngay(thang, ngay, code, dong.get("mt_ngay")), "")

    @app.callback(Output("bp-chi-tiet", "children"), Input("bp-nv", "cellClicked"),
                  State("bp-nv", "rowData"), State("bp-date", "date"), State("bp-phong", "value"),
                  prevent_initial_call=True)
    def _xem_chi_tiet(o, rows, ngay_iso, code):
        if not o or not duoc_xem_phong(code) or not ngay_iso:
            return no_update
        i = o.get("rowIndex")
        acc = (o.get("data") or {}).get("acc_norm") if o.get("data") else (
            rows[i]["acc_norm"] if rows and i is not None and i < len(rows) else None)
        if not acc or acc == "TOTAL":
            return ""
        d = date.fromisoformat(ngay_iso)
        thang = f"{d.year}-{d.month:02d}"
        # tính lại ở máy chủ: chỉ hiện nếu người này đúng là nhân sự của phòng đang được phép xem
        nv = bp.bang_nhan_su(thang, d.day, code)
        r = nv[(nv.acc_norm == acc) & (nv.loai_dong == "data")]
        if r.empty:
            return ""
        return _chi_tiet(thang, d.day, code, r.iloc[0].to_dict())

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

