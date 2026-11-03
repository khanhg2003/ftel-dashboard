"""Phần "hồ sơ" trong ngăn chi tiết một nhân sự (Báo cáo phòng): dựng giao diện từ `app.ho_so_nhan_su.ho_so`.

Tách khỏi `phong.py` cho gọn (mẫu `phantich_tinh.py`). Không import `phong.py` để tránh vòng lặp import.
"""
from __future__ import annotations

import dash_ag_grid as dag
import plotly.graph_objects as go
from dash import dcc, html

from app.ui.components import LOCALE_VI, ghi_chu, tip

XANH_DUONG, CAM = "#0072BC", "#F5A25D"
DO = {"backgroundColor": "#F7BDBD", "color": "#7F1D1D", "fontWeight": "600"}
XANH = {"backgroundColor": "#D3EBD4", "color": "#14532D", "fontWeight": "600"}
SO0 = {"function": "params.value ? params.value : ''"}
PCT = {"function": "params.value == null ? '–' : Math.round(params.value) + '%'"}
CHENH = {"function": "params.value == null ? '–' : (params.value > 0 ? '+' : '') + Math.round(params.value) + ' điểm'"}


def _so(v) -> str:
    return f"{int(v or 0):,}".replace(",", ".")


def _pct(v) -> str:
    return "–" if v is None else f"{float(v):.0f}%"


def _dau(v) -> str:
    return f"{v:+.0f}"


def _o(nhan: str, so: str, phu: str = "") -> html.Div:
    return html.Div([html.Div(nhan, className="nhan"), html.Div(so, className="so"), html.Div(phu, className="phu")],
                    className="ct-o")


def _bang(cot: list[dict], dong: list[dict]) -> dag.AgGrid:
    return dag.AgGrid(className="ag-theme-quartz ag-theme-ftel luoi-ke", rowData=dong, columnDefs=cot,
                      dashGridOptions={"suppressCellFocus": True, "domLayout": "autoHeight", "localeText": LOCALE_VI,
                                       "tooltipShowDelay": 300}, style={"width": "100%"})


def _so_cot(field: str, ten: str, w: int = 78, **kw) -> dict:
    return {"field": field, "headerName": ten, "type": "numericColumn", "width": w, "valueFormatter": SO0, **kw}


def _bieu_do(fig: go.Figure, cao: int = 220) -> dcc.Graph:
    fig.update_layout(height=cao, autosize=True, margin=dict(l=8, r=8, t=24, b=8), plot_bgcolor="white",
                      paper_bgcolor="white", bargap=.3, barmode="group", hovermode="x unified",
                      font=dict(family="Inter, Segoe UI, sans-serif", size=12, color="#1B2733"),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
    fig.update_xaxes(showgrid=False, linecolor="#E4E9F0")
    fig.update_yaxes(gridcolor="#F1F5F9", zeroline=False, rangemode="tozero")
    return dcc.Graph(figure=fig, config={"displayModeBar": False, "responsive": True})


def vi_tri(hs: dict) -> list:
    tv, tn = hs.get("trung_vi_phong"), hs.get("so_voi_tham_nien")
    o = [_o("Đóng góp cho phòng", _pct(hs.get("dong_gop")), f"{_so(hs['online'])}/{_so(hs['online_phong'])} online của phòng")]
    o.append(_o("So với trung vị phòng", "–" if tv is None else _dau(hs["online"] - tv),
                "Trung vị phòng kinh doanh: " + ("–" if tv is None else f"{tv:.0f} online")))
    o.append(_o("So với cùng thâm niên", "–" if tn is None or tn != tn else f"{tn:+.0f}%",
                "Trung vị nhóm thâm niên: " + (f"{hs['trung_vi_tham_nien']:.0f}" if hs.get("trung_vi_tham_nien") == hs.get("trung_vi_tham_nien")
                                              and hs.get("trung_vi_tham_nien") is not None else "–")))
    return [html.H4("Vị trí trong phòng"), html.Div(o, className="ct-luoi")]


def xu_huong(hs: dict) -> list:
    d = hs["xu_huong"]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=[r["ten"] for r in d], y=[r["online"] for r in d], name="Online", marker_color=XANH_DUONG))
    fig.add_trace(go.Bar(x=[r["ten"] for r in d], y=[r["ban_moi"] for r in d], name="Bán mới", marker_color=CAM))
    ck = d[-1]
    return [html.H4("Xu hướng 3 tháng"), _bieu_do(fig),
            html.Div(f"Cùng kỳ {d[1]['ten']}: online {_so(ck['online_ck'])}, bán mới {_so(ck['ban_moi_ck'])}. "
                     f"Hai tháng trước là cả tháng, tháng này tính tới ngày chọn.", className="desc")]


def theo_tinh(hs: dict) -> list:
    tinh, xa = hs["tinh"], hs["xa"]
    onl = hs["online"]
    chips = [html.Span(f"Bán {_so(hs['ban'])} · đã online {_so(hs['ban_da_onl'])} · chưa online "
                       f"{_so(hs['ban'] - hs['ban_da_onl'])}", className="chip"),
             html.Span(f"Ngoại tỉnh {_so(hs['ngoai_onl'])}/{_so(onl)} online ({_pct(hs['ngoai_onl'] / onl * 100 if onl else None)}"
                       f", phòng {_pct(hs['ngoai_phong'])})", className="chip"),
             html.Span(f"{len(tinh)} tỉnh", className="chip")]
    if hs["onl_ban_truoc"]:
        chips.append(html.Span(f"{hs['onl_ban_truoc']} online từ hợp đồng ký trước đầu tháng", className="chip"))
    cot_tinh = [{"field": "tinh", "headerName": "Tỉnh", "minWidth": 110, "flex": 1}, _so_cot("ban", "Bán", 64, headerTooltip="Hợp đồng ký mới trong tháng này"),
                _so_cot("ban_da_onl", "Đã online", 84, headerTooltip="Trong số HĐ vừa bán tháng này, đã có bao nhiêu HĐ nghiệm thu online"), _so_cot("onl", "Online", 74, cellStyle={"fontWeight": "700"}, headerTooltip="Tổng số hợp đồng nghiệm thu online trong tháng (gồm cả HĐ ký từ tháng trước)"),
                {"field": "ty_trong", "headerName": "% online", "type": "numericColumn", "width": 82, "headerTooltip": "Tỷ trọng online của tỉnh này trên tổng online của nhân sự",
                 "valueFormatter": PCT}]
    cot_xa = [{"field": "tinh", "headerName": "Tỉnh", "width": 100}, {"field": "xa", "headerName": "Phường / xã",
                                                                       "minWidth": 130, "flex": 1, "tooltipField": "xa"},
              _so_cot("ban", "Bán", 60, headerTooltip="Hợp đồng ký mới trong tháng này"), _so_cot("onl", "Online", 72, cellStyle={"fontWeight": "700"}, headerTooltip="Tổng số hợp đồng nghiệm thu online trong tháng")]
    return [html.H4("Bán theo tỉnh và phường / xã"), html.Div([*chips, tip("• Bán: Hợp đồng ký mới trong tháng này.\n• Đã online: Trong số HĐ vừa ký tháng này, đã có bao nhiêu HĐ nghiệm thu xong.\n• Online: Tổng HĐ thực tế online trong tháng (gồm cả HĐ ký từ tháng trước).")], className="chips", style={"margin": "0 0 8px", "alignItems": "center"}),
            _bang(cot_tinh, tinh.to_dict("records")),
            html.Div("Phường / xã nhiều nhất", className="ct-tinh-ten", style={"margin": "12px 0 6px"}),
            _bang(cot_xa, xa.to_dict("records")),
            ghi_chu("Bán = Hợp đồng ký mới trong tháng (trong đó 'Đã online' là ca đã lắp xong). Online = Tổng HĐ online trong tháng (gồm cả ca ký tháng trước chuyển sang). "
                    "Tỉnh theo chi nhánh quản lý của hợp đồng.", style={"margin": "8px 0 0"})]


def co_cau_goi(hs: dict) -> list:
    if not hs["goi"]:
        return []
    cot = [{"field": "goi", "headerName": "Nhóm gói", "minWidth": 90, "flex": 1}, _so_cot("so", "Online", 72),
           {"field": "ty_trong", "headerName": "% của người", "type": "numericColumn", "width": 96, "valueFormatter": PCT},
           {"field": "ty_trong_phong", "headerName": "% của phòng", "type": "numericColumn", "width": 96,
            "valueFormatter": PCT},
           {"field": "vvip", "headerName": "Kèm V.VIP", "type": "numericColumn", "width": 92, "valueFormatter": PCT},
           {"field": "camera", "headerName": "Kèm Camera", "type": "numericColumn", "width": 100, "valueFormatter": PCT}]
    return [html.H4("Cơ cấu gói cước"), _bang(cot, hs["goi"])]


def chat_luong(hs: dict) -> list:
    cot = [{"field": "chi_so", "headerName": "Chỉ số", "minWidth": 130, "flex": 1},
           {"field": "nguoi", "headerName": "Người này", "type": "numericColumn", "width": 92, "valueFormatter": PCT},
           {"field": "phong", "headerName": "Phòng", "type": "numericColumn", "width": 80, "valueFormatter": PCT},
           {"field": "chenh", "headerName": "Chênh", "type": "numericColumn", "width": 100, "valueFormatter": CHENH,
            "cellStyle": {"styleConditions": [{"condition": "params.value != null && params.value <= -10", "style": DO},
                                              {"condition": "params.value != null && params.value >= 10", "style": XANH}]}},
           {"field": "cung_ky", "headerName": "Cùng kỳ T-1", "type": "numericColumn", "width": 104, "valueFormatter": PCT,
            "headerTooltip": "Chính người này, cùng số ngày của tháng trước"}]
    return [html.H4("Chất lượng bán so với phòng"), _bang(cot, hs["chat_luong"]),
            ghi_chu("Tỷ lệ tính trên số online. Chênh = người này trừ phòng; tô đỏ khi thấp hơn từ 10 điểm, "
                    "xanh khi cao hơn từ 10 điểm.", style={"margin": "8px 0 0"})]


def trien_khai(hs: dict) -> list:
    tv, tvp = hs["cho_trung_vi"], hs["cho_trung_vi_phong"]
    tuoi = hs["ton_tuoi"]
    nguon = ", ".join(f"{r.nguon_ban} {int(r.n)}" for r in hs["nguon_ban"].itertuples()) or "–"
    ban, onl = hs["ban"], hs["ban_da_onl"]
    return [html.H4("Triển khai, hợp đồng chưa online và nguồn bán"), html.Div([
        _o("Chờ online (trung vị)", "–" if tv is None else f"{tv:.0f} ngày",
           "Phòng: " + ("–" if tvp is None else f"{tvp:.0f} ngày")),
        _o("Bán mới đã online", f"{onl}/{ban}", f"{_pct(onl / ban * 100 if ban else None)} số hợp đồng bán trong tháng"),
        _o("Chưa online", _so(hs["ton"]), ("Theo ngày chờ: " + " · ".join(f"{k.replace(' ngày', '')}: {int(v)}"
                                                                         for k, v in tuoi.items() if v)) if hs["ton"] else "Không có"),
        _o("Nguồn bán (hợp đồng mới)", nguon.split(",")[0] if nguon != "–" else "–",
           nguon if "," in nguon else "Tất cả hợp đồng bán trong tháng"),
    ], className="ct-luoi")]


def nhip_tuan(hs: dict) -> list:
    thu = hs["thu"]
    fig = go.Figure(go.Bar(x=[r["thu"] for r in thu], y=[r["tb"] for r in thu], marker_color=XANH_DUONG,
                           customdata=[[r["so"], r["so_ngay"]] for r in thu],
                           hovertemplate="%{y} online/ngày (%{customdata[0]} online trong %{customdata[1]} ngày)<extra></extra>"))
    tot = max(thu, key=lambda r: r["tb"])
    return [html.H4("Nhịp theo thứ trong tuần"), _bieu_do(fig, 200), html.Div([
        _o("Ngày có số", f"{hs['ngay_co_so']}", f"Bình quân {str(hs['tb_moi_ngay_co_so']).replace('.', ',')} online/ngày có số"
           if hs["tb_moi_ngay_co_so"] else ""),
        _o("Chuỗi không số dài nhất", f"{hs['chuoi_dai_nhat']} ngày", "Trong tháng đang xem"),
        _o("Ngày bán tốt nhất", tot["thu"] if tot["tb"] else "–", f"Bình quân {str(tot['tb']).replace('.', ',')} online/ngày"
           if tot["tb"] else ""),
    ], className="ct-luoi")]


def nsld(hs: dict) -> list:
    if not hs["nsld"]:
        return []
    return [html.H4("NSLĐ gần đây"), html.Div([html.Span(f"{r['thang']}: " + ("–" if r["diem"] is None else f"{r['diem']:.0f} điểm")
                                                         + (f" · {r['ket_luan']}" if r["ket_luan"] else ""), className="chip")
                                               for r in hs["nsld"]], className="chips")]


def phan_ho_so(hs: dict) -> list:
    """Các phần hồ sơ theo thứ tự đọc: vị trí -> xu hướng -> khách và gói -> chất lượng -> triển khai -> nhịp -> NSLĐ."""
    return [*vi_tri(hs), *xu_huong(hs), *theo_tinh(hs), *co_cau_goi(hs), *chat_luong(hs), *trien_khai(hs),
            *nhip_tuan(hs), *nsld(hs)]
