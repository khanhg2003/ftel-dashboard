"""Phân tích bán hàng - thẻ "Bán theo tỉnh": số online theo tỉnh + đi sâu một tỉnh, ai bán ở tỉnh nào (theo phòng / theo nhân viên +
đi sâu một nhân viên), gói cước theo tỉnh, một ngày bán & online.

Quản trị xem đủ ba cách xem. Nhân viên KD của phòng bật ở rules.yml (`ban_tinh`, hiện IBB7) chỉ thấy hai phần "Bán theo tỉnh" và
"Ai bán ở tỉnh nào" (cách xem "Số online theo tỉnh"); số theo tỉnh / theo phòng là số chung, chi tiết nhân viên mọi phòng (22/10/2026). Chặn cả ở máy chủ, không chỉ ẩn trên giao diện.
Tách khỏi app/ui/pages/phantich.py cho gọn; dùng chung kỳ, bảng, biểu đồ của trang đó."""
from __future__ import annotations

from datetime import date

import plotly.graph_objects as go
from dash import Input, Output, Patch, State, dcc, html, no_update
from dash.exceptions import PreventUpdate
from flask_login import current_user

from app import phan_tich as pt
from app.auth import loc_nhan_su
from app.org import loc_chi_nhanh, phong_order
from app.overview import TEN_PHAM_VI
from app.ui.components import cua_so, field, ghi_chu, seg_control
from app.ui.icons import icon
from app.ui.pages.phantich import MAU_GOI, PCT, SO, _dau_the, _fig, _graph, _grid, _ky, _ten_nhan_vien, _trong


def _pham_vi_nv() -> list[str] | None:
    """Phạm vi nhân viên của hai phần theo tỉnh. Ai đã được xem phần này (Quản trị, nvkd phòng bật ở rules.yml) thì thấy nhân viên MỌI phòng
    (chủ app chốt 22/10/2026, thay quy tắc "chỉ phòng mình" của lần đầu); vai trò khác giữ phạm vi nhân sự thường."""
    return None if current_user.duoc_xem_ban_tinh else current_user.phong_nhan_su()


def _phong_nv_duoc_xem() -> list[dict]:
    """Phòng hiện trong ô chọn ở bảng theo nhân viên."""
    pham_vi = _pham_vi_nv()
    return [p for p in phong_order() if pham_vi is None or p["code"] in set(pham_vi)]


def _acc_duoc_xem(acc_key: str, tu: str, den: str, scope) -> bool:
    """Người dùng giới hạn theo phòng chỉ được mở chi tiết nhân viên có số trong phòng mình (kiểm ở máy chủ, không tin dòng trình duyệt gửi lên)."""
    pham_vi = _pham_vi_nv()
    if pham_vi is None:
        return True
    df = pt.online_theo_tinh(tu, den, loc_nhan_su(scope, pham_vi))
    return bool((df.acc_norm.fillna(df.acc_nhan_vien.str.lower()) == acc_key).any())


def the(den, ngays, xem_tinh: bool, admin: bool):
    """Thẻ 'Bán theo tỉnh' + hai cửa sổ chi tiết một tỉnh / một nhân viên. `xem_tinh`: được thấy thẻ; `admin`: được đổi sang gói cước / một ngày."""
    return html.Div([
        html.Div([
            _dau_the("Bán theo tỉnh", "pt-mo-ta-tinh",
                     dcc.Dropdown(id="pt-tinh-pv", value="all", clearable=False, style={"width": "240px"},
                                  options=[{"label": "Toàn bộ phạm vi", "value": "all"}]),
                     seg_control("pt-tinh-loai", [("tat_ca", "Tất cả tỉnh"), ("ngoai", "Chỉ ngoại tỉnh")], "tat_ca")),
            html.Div(seg_control("pt-tinh-xem", [("tong", "Số online theo tỉnh"), ("goi", "Gói cước theo tỉnh"),
                                                 ("ngay", "Một ngày: bán & online")], "tong"),
                     style={"margin": "2px 0 12px"} if admin else {"display": "none"}),
            html.Div([
                html.Div(id="pt-tinh-tom-tat", className="chips", style={"margin": "4px 0 10px"}),
                html.Div([
                    html.Div(dcc.Loading(_graph("pt-tinh-bd")), className="chart-col"),
                    html.Div([_grid("pt-tinh-bang", cao=420, className="ag-theme-quartz ag-theme-ftel luoi-ke", dashGridOptions={
                                  "rowSelection": {"mode": "singleRow", "checkboxes": False,
                                                   "enableClickSelection": True}}),
                              html.Div([icon("zoom_in", 14), html.Span("Bấm vào tên tỉnh để xem chi tiết: phường/xã, "
                                                                      "nhân viên bán, gói cước")],
                                       className="goi-y-bam", style={"marginTop": "6px"})],
                             className="chart-col"),
                ], className="chart-row doi"),
                html.Div([html.H3("Ai bán ở tỉnh nào", style={"margin": 0, "fontSize": "14px"}),
                          html.Div(className="grow"),
                          seg_control("pt-tinh-mt-xem", [("phong", "Theo phòng"), ("nv", "Theo nhân viên")], "phong")],
                         className="the-thanh", style={"margin": "18px 0 6px"}),
                html.Div([
                    ghi_chu("Mỗi cột là một phòng, mỗi dòng một tỉnh; số là hợp đồng online. Màu theo tỷ trọng trong "
                            "chính phòng đó: xanh đậm = tỉnh chiếm từ 20% số của phòng, xanh nhạt 5-20%.",
                            nhan="Cách đọc bảng", style={"margin": "0 0 8px"}),
                    _grid("pt-tinh-ma-tran", cao=440, className="ag-theme-quartz ag-theme-ftel luoi-ke"),
                ], id="pt-tinh-mt-phong"),
                html.Div([
                    ghi_chu("Mỗi dòng một nhân viên (xếp theo phòng), mỗi cột một tỉnh có số (nhiều trước, kéo ngang "
                            "để xem hết). Bấm một nhân viên để mở cửa sổ số bán + số online từng tỉnh, từng phường / xã. Chọn "
                            "phòng ở ô bên dưới để xem riêng nhân viên một phòng. Màu "
                            "theo tỷ trọng trong số của chính người đó: xanh đậm từ 20%, xanh nhạt 5-20%. Trưởng phòng "
                            "không đưa vào (số của họ vẫn tính cho phòng).", nhan="Cách đọc bảng",
                            style={"margin": "0 0 8px"}),
                    html.Div([
                        dcc.Dropdown(id="pt-tinh-nv-phong", value="all", clearable=False, style={"width": "220px"},
                                     options=[{"label": "Tất cả phòng" if admin or current_user.duoc_xem_ban_tinh else "Phòng của bạn", "value": "all"}] + [
                                         {"label": p["ten"], "value": p["code"]} for p in _phong_nv_duoc_xem()]),
                        dcc.Input(id="pt-tinh-nv-tim", type="search", placeholder="Tìm tên hoặc acc…",
                                  className="o-tim"),
                        html.Div([icon("zoom_in", 14), html.Span("Bấm vào tên nhân viên để xem chi tiết bán + online "
                                                                "từng tỉnh, từng phường/xã")], className="goi-y-bam"),
                    ], className="the-thanh", style={"margin": "0 0 8px", "gap": "8px", "flexWrap": "wrap"}),
                    _grid("pt-tinh-nv", cao=480, className="ag-theme-quartz ag-theme-ftel luoi-ke",
                          dashGridOptions={"rowSelection": {"mode": "singleRow", "checkboxes": False,
                                                            "enableClickSelection": True}}),
                ], id="pt-tinh-mt-nv", hidden=True),
            ], id="pt-tinh-v-tong"),
            html.Div([
                html.Div(id="pt-tinh-goi-mo-ta", className="desc", style={"margin": "0 0 8px"}),
                html.Div([
                    html.Div(dcc.Loading(_graph("pt-tinh-goi-bd")), className="chart-col"),
                    html.Div(_grid("pt-tinh-goi", cao=440, className="ag-theme-quartz ag-theme-ftel luoi-ke"), className="chart-col"),
                ], className="chart-row doi"),
            ], id="pt-tinh-v-goi", hidden=True),
            html.Div([
                html.Div([
                    field("Ngày", dcc.DatePickerSingle(id="pt-tinh-ngay", date=den, display_format="DD/MM/YYYY",
                                                       min_date_allowed=ngays[0] if ngays else None,
                                                       max_date_allowed=ngays[-1] if ngays else None,
                                                       first_day_of_week=1, clearable=False, className="date-pick")),
                    field("Phòng", seg_control("pt-tinh-ngay-pv", [("ibb", "IBB1 - IBB7"), ("all", "Tất cả phòng")],
                                               "ibb")),
                ], className="toolbar", style={"flexWrap": "wrap", "margin": "0 0 8px"}),
                html.Div(id="pt-tinh-ngay-tom-tat", className="chips", style={"margin": "0 0 10px"}),
                dcc.Loading(_grid("pt-tinh-ngay-bang", cao=460, className="ag-theme-quartz ag-theme-ftel luoi-ke")),
                ghi_chu("Bán = hợp đồng tạo trong ngày (gồm cả hợp đồng chưa online). Online = hợp đồng online trong "
                        "ngày (có thể tạo từ hôm trước). Tỉnh theo CN quản lý của hợp đồng (nơi khách ở). Ngày đang "
                        "cập nhật thì số còn tăng.", style={"margin": "8px 0 0"}),
            ], id="pt-tinh-v-ngay", hidden=True),
        ], className="card", style={} if xem_tinh else {"display": "none"}),
        cua_so("pt-md-tinh"),
        cua_so("pt-md-nv"),
    ])


def register(app):
    @app.callback(Output("pt-tinh-pv", "options"), Output("pt-mo-ta-tinh", "children"),
                  Output("pt-tinh-tom-tat", "children"), Output("pt-tinh-bd", "figure"),
                  Output("pt-tinh-bang", "columnDefs"), Output("pt-tinh-bang", "rowData"),
                  Output("pt-tinh-ma-tran", "columnDefs"), Output("pt-tinh-ma-tran", "rowData"),
                  Input("pt-khoang", "start_date"), Input("pt-khoang", "end_date"), Input("pt-cn", "value"),
                  Input("pt-tinh-pv", "value"), Input("pt-tinh-loai", "value"), Input("pt-tinh-xem", "value"))
    def _tinh(tu_iso, den_iso, chi_nhanh, pv, loai, xem):
        if not current_user.duoc_xem_ban_tinh or xem not in (None, "tong"):
            raise PreventUpdate
        ky = _ky(tu_iso, den_iso)
        if ky is None:
            return [], "", [], _fig(_trong(go.Figure())), [], [], [], []
        thang, tu, den = ky.thang, ky.tu, ky.den
        scope = loc_chi_nhanh(current_user.phong_duoc_xem(), chi_nhanh, thang)
        df = pt.online_theo_tinh(tu, den, scope)
        df_ck = pt.online_theo_tinh(*ky.ck, scope)
        mt, phong = pt.ma_tran_tinh_phong(df, thang)
        pham_vi = TEN_PHAM_VI.get(chi_nhanh, TEN_PHAM_VI["all"])
        opts = [{"label": f"Toàn bộ · {pham_vi}", "value": "all"}] + [
            {"label": p["ten"], "value": p["code"]} for p in phong]
        if pv not in {o["value"] for o in opts}:
            pv = "all"
        ten_pv = pham_vi if pv == "all" else next(p["ten"] for p in phong if p["code"] == pv)
        d, d_ck = (df, df_ck) if pv == "all" else (df[df.phong_code == pv], df_ck[df_ck.phong_code == pv])
        bang = pt.bang_tinh(d, d_ck)
        tong = int(bang.online.sum()) if len(bang) else 0
        noi = int(bang[bang.noi_tinh].online.sum()) if len(bang) else 0
        ngoai = bang[~bang.noi_tinh & (bang.online > 0)] if len(bang) else bang
        chips = []
        if tong:
            chips = [html.Span(f"{tong:,} hợp đồng online".replace(",", "."), className="chip"),
                     html.Span(f"Nội tỉnh (Đà Nẵng + Quảng Nam): {noi / tong * 100:.0f}%", className="chip"),
                     html.Span(f"Ngoại tỉnh: {(tong - noi) / tong * 100:.0f}% · {len(ngoai)} tỉnh", className="chip")]
            if len(ngoai):
                r = ngoai.iloc[0]
                chips.append(html.Span(f"Ngoại tỉnh nhiều nhất: {r.tinh} ({int(r.online)})", className="chip"))
        mo_ta = f"{ten_pv} · online {ky.nhan}, so {ky.ten_ck_day} · tỉnh theo CN quản lý của hợp đồng (nơi khách ở)"
        x = bang[~bang.noi_tinh] if loai == "ngoai" and len(bang) else bang
        x = x[x.online > 0].head(15)
        fig = go.Figure()
        if len(x):
            fig.add_bar(y=x.tinh, x=x.online, orientation="h", name="Kỳ này",
                        marker_color=["#0072BC" if n else "#37A5E6" for n in x.noi_tinh],
                        text=[f"{int(o)} · {t:.0f}%" for o, t in zip(x.online, x.ty_trong)], textposition="outside",
                        cliponaxis=False, hovertemplate="%{y}: %{x} hợp đồng<extra></extra>")
            fig.add_scatter(y=x.tinh, x=x.ck, mode="markers", name=ky.ten_ck.capitalize(),
                            marker={"symbol": "line-ns", "size": 16, "line": {"width": 3, "color": "#F37021"}},
                            hovertemplate="%{y}: cùng kỳ %{x}<extra></extra>")
            fig.update_yaxes(autorange="reversed")
            fig.update_xaxes(range=[0, max(x.online.max(), x.ck.max()) * 1.25])
        fig = _fig(fig, max(320, 60 + 30 * len(x)))
        fig.update_layout(legend={"orientation": "h", "y": 1.08}, margin={"l": 110, "r": 30, "t": 30, "b": 20})
        cot_bang = [{"field": "tinh", "headerName": "Tỉnh", "pinned": "left", "minWidth": 130, "flex": 1.3,
                     "cellClass": "o-bam", "headerTooltip": "Bấm vào tên tỉnh để xem chi tiết"},
                    {"field": "online", "headerName": "Online", "type": "numericColumn", "minWidth": 75, "flex": 1,
                     "valueFormatter": SO},
                    {"field": "ty_trong", "headerName": "Tỷ trọng", "type": "numericColumn", "minWidth": 80, "flex": 1,
                     "valueFormatter": {"function": "params.value == null ? '' : params.value.toFixed(1) + '%'"}},
                    {"field": "ck", "headerName": ky.ten_ck.capitalize(), "headerTooltip": ky.ten_ck_day,
                     "type": "numericColumn", "minWidth": 90, "flex": 1,
                     "valueFormatter": SO},
                    {"field": "chenh", "headerName": "+/-", "type": "numericColumn", "minWidth": 65, "flex": .8,
                     "valueFormatter": {"function": "params.value == null ? '' : (params.value > 0 ? '+' : '') + "
                                                    "params.value"},
                     "cellStyle": {"styleConditions": [
                         {"condition": "params.value > 0", "style": {"color": "#04843F", "fontWeight": "700"}},
                         {"condition": "params.value < 0", "style": {"color": "#C8372D", "fontWeight": "700"}}]}}]
        cot_mt = [{"field": "tinh", "headerName": "Tỉnh", "pinned": "left", "minWidth": 130},
                  {"field": "tong", "headerName": "Tổng", "pinned": "left", "width": 85, "type": "numericColumn",
                   "valueFormatter": SO, "cellStyle": {"fontWeight": "700"}}]
        for p in phong:
            t = int(mt[p["code"]].sum()) if len(mt) else 0
            cot_mt.append({"field": p["code"], "headerName": p["ten"], "width": 92, "type": "numericColumn",
                           "valueFormatter": {"function": "params.value ? params.value : ''"},
                           "headerTooltip": f"{p['ten']}: {t} hợp đồng online",
                           "cellStyle": {"styleConditions": [
                               {"condition": f"params.value >= {max(t * 0.2, 1)}",
                                "style": {"backgroundColor": "#BFE6C8", "fontWeight": "700", "color": "#0F3D22"}},
                               {"condition": f"params.value >= {max(t * 0.05, 1)}",
                                "style": {"backgroundColor": "#E8F5EC"}}]}})
        return (opts, mo_ta, chips, fig, cot_bang, bang.to_dict("records") if len(bang) else [], cot_mt,
                mt.to_dict("records") if len(mt) else [])


    # ------------------------------------------------ bán theo tỉnh: cách xem, đi sâu một tỉnh, gói, một ngày
    @app.callback(Output("pt-tinh-v-tong", "hidden"), Output("pt-tinh-v-goi", "hidden"),
                  Output("pt-tinh-v-ngay", "hidden"), Input("pt-tinh-xem", "value"))
    def _doi_xem_tinh(xem):
        return xem not in (None, "tong"), xem != "goi", xem != "ngay"

    @app.callback(Output("pt-tinh-mt-phong", "hidden"), Output("pt-tinh-mt-nv", "hidden"),
                  Input("pt-tinh-mt-xem", "value"))
    def _doi_mt(xem):
        return xem == "nv", xem != "nv"

    @app.callback(Output("pt-tinh-nv", "dashGridOptions"), Input("pt-tinh-nv-tim", "value"), prevent_initial_call=True)
    def _tim_nv_tinh(chu):
        p = Patch()
        p["quickFilterText"] = chu or ""
        return p

    @app.callback(Output("pt-tinh-nv", "columnDefs"), Output("pt-tinh-nv", "rowData"),
                  Input("pt-tinh-mt-xem", "value"), Input("pt-tinh-xem", "value"),
                  Input("pt-khoang", "start_date"), Input("pt-khoang", "end_date"), Input("pt-cn", "value"),
                  Input("pt-tinh-pv", "value"), Input("pt-tinh-loai", "value"), Input("pt-tinh-nv-phong", "value"))
    def _nv_tinh(xem, xem_tinh, tu_iso, den_iso, chi_nhanh, pv, loai, phong_nv):
        if xem != "nv" or xem_tinh not in (None, "tong") or not current_user.duoc_xem_ban_tinh:
            raise PreventUpdate
        ky = _ky(tu_iso, den_iso)
        if ky is None:
            return [], []
        from app.tinh import NOI_TINH
        scope = loc_chi_nhanh(current_user.phong_duoc_xem(), chi_nhanh, ky.thang)
        df = pt.online_theo_tinh(ky.tu, ky.den, scope)
        if pv and pv != "all":
            df = df[df.phong_code == pv]
        if phong_nv and phong_nv != "all":
            df = df[df.phong_code == phong_nv]
        pham_vi_nv = _pham_vi_nv()
        if pham_vi_nv is not None:
            df = df[df.phong_code.isin(set(pham_vi_nv))]
        if loai == "ngoai":
            df = df[~df.ma_tinh.isin(NOI_TINH)]
        ten_phong = {p["code"]: p["ten"] for p in phong_order(ky.thang)}
        mt, tinh = pt.ma_tran_nv_tinh(df, _ten_nhan_vien(), ten_phong)
        mt = mt.drop(columns=["khac"], errors="ignore")
        nhiet = {"styleConditions": [
            {"condition": "params.value && params.value >= params.data.tong * 0.2",
             "style": {"backgroundColor": "#BFE6C8", "fontWeight": "700", "color": "#0F3D22"}},
            {"condition": "params.value && params.value >= params.data.tong * 0.05",
             "style": {"backgroundColor": "#E8F5EC"}}]}
        so0 = {"function": "params.value ? params.value : ''"}
        cot = [{"field": "ho_ten", "headerName": "Nhân viên", "pinned": "left", "minWidth": 170,
                "cellClass": "o-bam", "headerTooltip": "Bấm vào tên để xem chi tiết"},
               {"field": "phong", "headerName": "Phòng", "pinned": "left", "width": 95},
               {"field": "tong", "headerName": "Tổng", "pinned": "left", "width": 72, "type": "numericColumn",
                "valueFormatter": SO, "cellStyle": {"fontWeight": "700"}},
               {"field": "ngoai_pct", "headerName": "% ngoại tỉnh", "width": 92, "type": "numericColumn",
                "valueFormatter": PCT, "headerTooltip": "Tỷ lệ hợp đồng khách ngoài Đà Nẵng + Quảng Nam"}]
        cot += [{"field": ma, "headerName": ten, "width": 90, "type": "numericColumn", "valueFormatter": so0,
                 "cellStyle": nhiet} for ma, ten in tinh]
        return cot, mt.to_dict("records") if len(mt) else []

    @app.callback(Output("pt-md-nv", "className"), Output("pt-md-nv-tieu-de", "children"),
                  Output("pt-md-nv-than", "children"),
                  Input("pt-tinh-nv", "selectedRows"), Input("pt-khoang", "start_date"),
                  Input("pt-khoang", "end_date"), Input("pt-cn", "value"))
    def _ct_nv_tinh(chon, tu_iso, den_iso, chi_nhanh):
        if not current_user.duoc_xem_ban_tinh:
            raise PreventUpdate
        r = (chon or [None])[0]
        ky = _ky(tu_iso, den_iso)
        if not r or not r.get("acc_key") or ky is None:
            return "modal", "", []
        scope = loc_chi_nhanh(current_user.phong_duoc_xem(), chi_nhanh, ky.thang)
        if not _acc_duoc_xem(r["acc_key"], ky.tu, ky.den, scope):
            return "modal", "", []
        ct = pt.chi_tiet_nv_tinh(r["acc_key"], ky.tu, ky.den, scope)
        luoi = "ag-theme-quartz ag-theme-ftel luoi-ke"
        so0 = {"function": "params.value ? params.value : ''"}

        def c(field_, ten, w=80, **kw):
            return {"field": field_, "headerName": ten, "type": "numericColumn", "width": w, "valueFormatter": so0,
                    **kw}
        dam = {"fontWeight": "700"}
        cot_tinh = [{"field": "tinh", "headerName": "Tỉnh", "pinned": "left", "minWidth": 130, "flex": 1},
                    c("ban", "Bán", 70, headerTooltip=f"Hợp đồng tạo trong {ky.ten}"),
                    c("ban_da_onl", "Trong đó đã online", 105, headerTooltip=f"Số hợp đồng bán {ky.ten} đã online"),
                    c("onl", "Online", 78, cellStyle=dam, headerTooltip=f"Hợp đồng online trong {ky.ten}"),
                    {"field": "ty_trong", "headerName": "% online", "type": "numericColumn", "width": 85,
                     "valueFormatter": PCT}]
        cot_xa = [{"field": "tinh", "headerName": "Tỉnh", "pinned": "left", "width": 120},
                  {"field": "xa", "headerName": "Phường / xã", "minWidth": 150, "flex": 1, "tooltipField": "xa"},
                  c("ban", "Bán", 66), c("onl", "Online", 74, cellStyle=dam)]

        def luoi_(gid, cot, d, cao):
            g = _grid(gid, cao=cao, className=luoi)
            g.columnDefs, g.rowData = cot, (d.to_dict("records") if len(d) else [])
            return g
        pct_ngoai = f"{ct['ngoai_onl'] / ct['onl'] * 100:.0f}%" if ct["onl"] else "–"
        chu_onl = f"Online {ky.ten}: {ct['onl']}"
        if ct["onl_ban_truoc"]:
            chu_onl += f" (có {ct['onl_ban_truoc']} HĐ bán từ {ky.truoc})"
        chips = [html.Span(f"Bán {ky.ten}: {ct['ban']} · đã online {ct['ban_da_onl']} · chưa online "
                           f"{ct['ban'] - ct['ban_da_onl']}", className="chip"),
                 html.Span(chu_onl, className="chip"),
                 html.Span(f"Ngoại tỉnh {ct['ngoai_onl']} ({pct_ngoai})", className="chip"),
                 html.Span(f"{len(ct['tinh'])} tỉnh", className="chip")]
        if ct["goi"]:
            chips.append(html.Span(f"Gói: {ct['goi']}", className="chip"))
        cao = min(max(160, 44 + 34 * len(ct["tinh"])), 360)
        return "modal mo", f"{r.get('ho_ten')} · {r.get('phong')} · {ky.nhan}", [
            html.Div(chips, className="chips", style={"margin": "0 0 12px"}),
            html.Div([
                html.Div([html.Div("Theo tỉnh", className="ct-tinh-ten"), luoi_("pt-tinh-nv-ct-tinh", cot_tinh,
                                                                               ct["tinh"], cao)]),
                html.Div([html.Div("Theo phường / xã", className="ct-tinh-ten"),
                          luoi_("pt-tinh-nv-ct-xa", cot_xa, ct["xa"], 360)]),
            ], className="hai-luoi"),
            ghi_chu(f"Bán = hợp đồng tạo trong {ky.ten}, gồm cả hợp đồng chưa online. Online = hợp đồng online "
                    f"trong {ky.ten}, có thể là hợp đồng bán từ {ky.truoc}. Vì vậy hai số không nhất thiết bằng nhau. "
                    "Tính mọi hợp đồng của người này "
                    "trong phạm vi chi nhánh đang chọn.", style={"margin": "8px 0 0"}),
        ]

    for md, bang in (("pt-md-tinh", "pt-tinh-bang"), ("pt-md-nv", "pt-tinh-nv")):
        def _dong(_a, _b):
            return "modal", []
        app.callback(Output(md, "className", allow_duplicate=True), Output(bang, "selectedRows", allow_duplicate=True),
                     Input(f"{md}-dong", "n_clicks"), Input(f"{md}-nen", "n_clicks"),
                     prevent_initial_call=True)(_dong)

    @app.callback(Output("pt-tinh-ngay", "date"), Input("pt-khoang", "end_date"), prevent_initial_call=True)
    def _ngay_theo_ky(den):
        return den[:10] if den else no_update

    @app.callback(Output("pt-md-tinh", "className"), Output("pt-md-tinh-tieu-de", "children"),
                  Output("pt-md-tinh-than", "children"),
                  Input("pt-tinh-bang", "selectedRows"), Input("pt-khoang", "start_date"),
                  Input("pt-khoang", "end_date"), Input("pt-cn", "value"), Input("pt-tinh-pv", "value"))
    def _ct_tinh(chon, tu_iso, den_iso, chi_nhanh, pv):
        if not current_user.duoc_xem_ban_tinh:
            raise PreventUpdate
        r = (chon or [None])[0]
        ky = _ky(tu_iso, den_iso)
        if not r or ky is None:
            return "modal", "", []
        scope = loc_chi_nhanh(current_user.phong_duoc_xem(), chi_nhanh, ky.thang)
        df = pt.online_theo_tinh(ky.tu, ky.den, scope)
        if pv and pv != "all":
            df = df[df.phong_code == pv]
        ten_phong = {p["code"]: p["ten"] for p in phong_order(ky.thang)}
        ct = pt.chi_tiet_tinh(df, r["ma_tinh"], _ten_nhan_vien(), ten_phong)
        pham_vi_nv = _pham_vi_nv()
        if pham_vi_nv is not None and len(ct["nv"]):                       # vai trò giới hạn: chỉ người trong phạm vi của mình
            ct["nv"] = ct["nv"][ct["nv"].phong_code.isin(set(pham_vi_nv))]
        tieu_de = f"{r['tinh']} · {ct['tong']:,} hợp đồng online {ky.nhan}".replace(",", ".")
        chips = [html.Span(f"{x.phong}: {int(x.so)} ({x.ty_trong:.0f}%)", className="chip")
                 for x in ct["phong"].head(8).itertuples()]
        tl_ = {"field": "ty_trong", "headerName": "%", "type": "numericColumn", "width": 70,
               "valueFormatter": {"function": "params.value == null ? '' : Math.round(params.value) + '%'"}}
        so_ = {"field": "so", "headerName": "HĐ", "type": "numericColumn", "width": 70, "valueFormatter": SO}
        cot_xa = [{"field": "xa", "headerName": "Phường / xã", "flex": 1, "minWidth": 150, "tooltipField": "xa"},
                  so_, tl_]
        cot_nv = [{"field": "ho_ten", "headerName": "Nhân viên", "flex": 1, "minWidth": 140, "tooltipField": "acc"},
                  {"field": "phong", "headerName": "Phòng", "width": 100}, so_]
        cot_goi = [{"field": "goi", "headerName": "Gói", "flex": 1, "minWidth": 110}, so_, tl_]
        luoi = "ag-theme-quartz ag-theme-ftel luoi-ke"

        def khoi(ten, gid, cot, d, c):
            g = _grid(gid, cao=320, className=luoi)
            g.columnDefs, g.rowData = cot, (d[c].to_dict("records") if len(d) else [])
            return html.Div([html.Div(ten, className="ct-tinh-ten"), g])
        return "modal mo", tieu_de, [
            html.Div(chips, className="chips", style={"margin": "0 0 12px"}),
            html.Div([khoi("Phường / xã", "pt-tinh-ct-xa", cot_xa, ct["xa"], ["xa", "so", "ty_trong"]),
                      khoi("Nhân viên bán", "pt-tinh-ct-nv", cot_nv, ct["nv"], ["ho_ten", "acc", "phong", "so"]),
                      khoi("Gói cước", "pt-tinh-ct-goi", cot_goi, ct["goi"], ["goi", "so", "ty_trong"])],
                     className="ba-cot"),
            ghi_chu("File Inside chỉ có phường / xã (từ 07/2025 không còn cấp quận / huyện), tên không dấu như file "
                    "gốc. Số là hợp đồng online trong thời gian đang xem, theo phạm vi đang chọn.", style={"margin": "8px 0 0"}),
        ]

    @app.callback(Output("pt-tinh-goi-bd", "figure"), Output("pt-tinh-goi", "columnDefs"),
                  Output("pt-tinh-goi", "rowData"), Output("pt-tinh-goi-mo-ta", "children"),
                  Input("pt-tinh-xem", "value"), Input("pt-khoang", "start_date"), Input("pt-khoang", "end_date"),
                  Input("pt-cn", "value"), Input("pt-tinh-pv", "value"), Input("pt-tinh-loai", "value"))
    def _goi_tinh(xem, tu_iso, den_iso, chi_nhanh, pv, loai):
        if xem != "goi" or current_user.role != "admin":
            raise PreventUpdate
        ky = _ky(tu_iso, den_iso)
        if ky is None:
            return _fig(_trong(go.Figure())), [], [], ""
        from app.tinh import NOI_TINH
        scope = loc_chi_nhanh(current_user.phong_duoc_xem(), chi_nhanh, ky.thang)
        df = pt.online_theo_tinh(ky.tu, ky.den, scope)
        if pv and pv != "all":
            df = df[df.phong_code == pv]
        if loai == "ngoai":
            df = df[~df.ma_tinh.isin(NOI_TINH)]
        bang = pt.co_cau_goi_tinh(df, 20)
        chung = pt.co_cau_goi_tinh(df.assign(ma_tinh="ALL", tinh="Chung"), 1)
        fig = go.Figure()
        nhom = list(pt.NHOM_GOI) + ["Khác"]
        if len(bang):
            x = bang.head(15)
            for g in nhom:
                fig.add_bar(y=x.tinh, x=x[f"{g}_pct"], name=g, orientation="h", marker_color=MAU_GOI.get(g, "#B9C5D3"),
                            text=[f"{v:.0f}%" if v >= 8 else "" for v in x[f"{g}_pct"]], textposition="inside",
                            customdata=x[g], hovertemplate="%{y} · " + g + ": %{x:.1f}% (%{customdata} HĐ)<extra></extra>")
            fig.update_yaxes(autorange="reversed")
            fig.update_xaxes(range=[0, 100], ticksuffix="%")
        fig = _fig(fig, max(320, 70 + 28 * min(len(bang), 15)))
        fig.update_layout(barmode="stack", legend={"orientation": "h", "y": 1.08},
                          margin={"l": 110, "r": 20, "t": 30, "b": 20})
        pct = {"function": "params.value == null ? '' : Math.round(params.value) + '%'"}
        cot = [{"field": "tinh", "headerName": "Tỉnh", "pinned": "left", "minWidth": 120, "flex": 1.2},
               {"field": "so_hd", "headerName": "HĐ", "type": "numericColumn", "width": 70, "valueFormatter": SO}]
        c0 = chung.iloc[0] if len(chung) else None
        for g in nhom:
            muc = float(c0[f"{g}_pct"]) if c0 is not None else 0
            cot.append({"field": f"{g}_pct", "headerName": f"% {g}", "type": "numericColumn", "width": 82,
                        "valueFormatter": pct, "headerTooltip": f"Mức chung {muc:.0f}%. Xanh: cao hơn mức chung "
                                                                 "từ 10 điểm, cam: thấp hơn từ 10 điểm",
                        "cellStyle": {"styleConditions": [
                            {"condition": f"params.value >= {muc + 10}", "style": {"backgroundColor": "#DDF1E3"}},
                            {"condition": f"params.value <= {muc - 10} && params.data.so_hd >= 5",
                             "style": {"backgroundColor": "#FDE7D6"}}]}})
        cot.append({"field": "goi_nhieu", "headerName": "Gói bán nhiều nhất", "minWidth": 120, "flex": 1})
        mo_ta = (f"Tỷ trọng nhóm gói trong số online {ky.nhan} của từng tỉnh (15 tỉnh nhiều hợp đồng nhất trên biểu "
                 "đồ, 20 tỉnh trong bảng)")
        if c0 is not None:
            mo_ta += " · mức chung: " + ", ".join(f"{g} {c0[f'{g}_pct']:.0f}%" for g in nhom)
        return fig, cot, bang.to_dict("records") if len(bang) else [], mo_ta

    @app.callback(Output("pt-tinh-ngay-bang", "columnDefs"), Output("pt-tinh-ngay-bang", "rowData"),
                  Output("pt-tinh-ngay-bang", "dashGridOptions"), Output("pt-tinh-ngay-tom-tat", "children"),
                  Input("pt-tinh-xem", "value"), Input("pt-tinh-ngay", "date"), Input("pt-cn", "value"),
                  Input("pt-tinh-pv", "value"), Input("pt-tinh-loai", "value"), Input("pt-tinh-ngay-pv", "value"),
                  State("pt-tinh-ngay-bang", "dashGridOptions"))
    def _ngay_tinh(xem, ngay, chi_nhanh, pv, loai, nhom, opts):
        if xem != "ngay" or current_user.role != "admin" or not ngay:
            raise PreventUpdate
        from app.tinh import NOI_TINH
        ngay = ngay[:10]
        thang = ngay[:7]
        scope = loc_chi_nhanh(current_user.phong_duoc_xem(), chi_nhanh, thang)
        ban, onl = pt.ban_online_ngay(ngay, scope)
        phong = [p for p in phong_order(thang) if nhom != "ibb" or p["code"].startswith("IBB")]
        if nhom == "ibb":                                           # IBB1 -> IBB7 theo số
            phong = sorted(phong, key=lambda p: (len(p["code"]), p["code"]))
        if pv and pv != "all":
            phong = [p for p in phong if p["code"] == pv]
        ma = {p["code"] for p in phong}
        ban, onl = ban[ban.phong_code.isin(ma)], onl[onl.phong_code.isin(ma)]
        if loai == "ngoai":
            ban, onl = ban[~ban.ma_tinh.isin(NOI_TINH)], onl[~onl.ma_tinh.isin(NOI_TINH)]
        co = set(ban.phong_code) | set(onl.phong_code)
        phong = [p for p in phong if p["code"] in co]
        bang = pt.bang_ngay_tinh(ban, onl, [p["code"] for p in phong])
        so0 = {"function": "params.value ? params.value : ''"}
        dam = {"styleConditions": [{"condition": "params.value > 0", "style": {"fontWeight": "700"}}]}

        def cap(field_, ten, w=62, **kw):
            return {"field": field_, "headerName": ten, "type": "numericColumn", "width": w, "valueFormatter": so0,
                    "cellStyle": dam, **kw}
        cot = [{"field": "tinh", "headerName": "Tỉnh", "pinned": "left", "minWidth": 130},
               {"headerName": "Tổng", "children": [cap("tong_ban", "Bán", 66, pinned="left"),
                                                   cap("tong_onl", "Online", 70, pinned="left")]}]
        cot += [{"headerName": p["ten"], "children": [cap(f"{p['code']}_ban", "Bán"),
                                                      cap(f"{p['code']}_onl", "Online", 68)]} for p in phong]
        opts = dict(opts or {})
        tong = {"tinh": "Tổng", "tong_ban": int(len(ban)), "tong_onl": int(len(onl))}
        for p in phong:
            tong[f"{p['code']}_ban"] = int((ban.phong_code == p["code"]).sum())
            tong[f"{p['code']}_onl"] = int((onl.phong_code == p["code"]).sum())
        opts["pinnedBottomRowData"] = [tong] if len(bang) else []
        d = date.fromisoformat(ngay)
        chips = [html.Span(f"Ngày {d:%d/%m/%Y}", className="chip"),
                 html.Span(f"Bán {len(ban)} · Online {len(onl)}", className="chip")]
        if len(ban):
            ngoai = ban[~ban.ma_tinh.isin(NOI_TINH)]
            chips.append(html.Span(f"Bán ngoại tỉnh {len(ngoai)} ({len(ngoai) / len(ban) * 100:.0f}%) · "
                                   f"{ngoai.ma_tinh.nunique()} tỉnh", className="chip"))
        if not len(bang):
            chips.append(html.Span("Ngày này chưa có số", className="chip"))
        return cot, bang.to_dict("records") if len(bang) else [], opts, chips
