"""Cửa sổ "Hiệu quả & xu hướng" của trang Báo cáo ngày (chốt 12/10/2026): tỷ lệ ca lên ĐÚNG dự kiến theo nhân viên / khung giờ và
xu hướng theo ngày (mục tiêu - bán, dự kiến - đã online). Quy tắc tính ở `app/online_ca_phan_tich.py`; trang này chỉ dựng giao diện."""
from __future__ import annotations

from dash import Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate
from plotly import graph_objects as go

from app import online_ca_phan_tich as pa
from app.ui.components import cua_so, seg_control

XANH, XAM, LA = "#0072BC", "#B8C4D2", "#067647"


def khung() -> html.Div:
    return cua_so("onl-hq", None, nut=seg_control("onl-hq-ky", list(pa.KY.items()), "7"))


def _lop(ty_le) -> str:
    return "" if ty_le is None else ("tot" if ty_le >= 80 else "tb" if ty_le >= 50 else "xau")


def _bang(cot: list[str], dong: list[list]) -> html.Table:
    return html.Table([html.Thead(html.Tr([html.Th(c) for c in cot])),
                       html.Tbody([html.Tr([html.Td(v[0] if isinstance(v, tuple) else v, className=(v[1] if isinstance(v, tuple) else ""))
                                            for v in r]) for r in dong])], className="onl-hq-bang")


def _pc(a: int, b: int) -> str:
    return f"{a} / {b} ({round(a * 100 / b)}%)" if b else f"{a}"


def _hinh(ngay: list[dict]):
    x = [r["ngay"].strftime("%d/%m") for r in ngay]
    kieu = dict(margin=dict(l=34, r=10, t=34, b=28), height=250, plot_bgcolor="#fff", paper_bgcolor="#fff", font=dict(size=12, color="#475467"),
                legend=dict(orientation="h", y=1.18, x=0), xaxis=dict(type="category", showgrid=False), yaxis=dict(gridcolor="#EEF0F3", rangemode="tozero"))
    ban = go.Figure([go.Bar(x=x, y=[r["mt"] for r in ngay], name="Mục tiêu ngày", marker_color=XAM),
                     go.Bar(x=x, y=[r["ban"] for r in ngay], name="Thực hiện", marker_color=XANH)], layout=dict(barmode="group", **kieu))
    onl = go.Figure([go.Scatter(x=x, y=[r["dk"] for r in ngay], name="Dự kiến online", mode="lines+markers", line=dict(color=XAM, dash="dot")),
                     go.Scatter(x=x, y=[r["onl"] for r in ngay], name="Đã online", mode="lines+markers", line=dict(color=LA))], layout=kieu)
    cau = {"displayModeBar": False}
    return html.Div([html.Div([html.Div("Bán so với mục tiêu ngày", className="onl-hq-tde"), dcc.Graph(figure=ban, config=cau)]),
                     html.Div([html.Div("Online: dự kiến và thực tế", className="onl-hq-tde"), dcc.Graph(figure=onl, config=cau)])], className="onl-hq-do")


def noi_dung(phong: list[str], ky: str) -> list:
    tu, den = pa.khoang(ky)
    hq, xh = pa.hieu_qua(phong, tu, den), pa.xu_huong(phong, tu, den)
    t = hq["tong"]
    khoang = f"{tu:%d/%m/%Y}" if tu == den else f"{tu:%d/%m} – {den:%d/%m/%Y}"
    ghi = [html.Div(f"Số liệu Báo cáo ngày chỉ có từ {xh['tu_ngay_co']:%d/%m/%Y} (trước đó báo cáo ngày đã qua bị xoá).", className="onl-hq-ghi")
           ] if xh["tu_ngay_co"] and xh["tu_ngay_co"] > tu else []
    tom = html.Div([html.Span(khoang, className="onl-hq-ky"),
                    html.Span([html.B(_pc(t["dung"], t["dung"] + t["tre"] + t["chua_len"])), " ca lên đúng hẹn"]) if t["ty_le"] is not None
                    else html.Span("Chưa có ca nào đến hạn để tính"),
                    html.Span(f"trễ {t['tre']}"), html.Span(f"chưa lên {t['chua_len']}"), html.Span(f"chưa tới hạn {t['cho']}"),
                    html.Span(f"không hẹn giờ {t['khong_hen']}")], className="onl-hq-tom")
    nv_xh = {r["acc"]: r for r in xh["nv"]}
    acc = list(dict.fromkeys([r["acc"] for r in hq["nv"]] + [r["acc"] for r in xh["nv"]]))
    nv_hq = {r["acc"]: r for r in hq["nv"]}
    dong = []
    for a in acc:
        h, x = nv_hq.get(a), nv_xh.get(a)
        if not ((h and h["ca"]) or (x and (x["dk"] or x["ban"] or x["mt"]))):
            continue                                         # người không có ca và không có số nào: ẩn, đỡ rối
        dong.append([(h or x)["ten"], h["ca"] if h else 0, h["dung"] if h else 0, h["tre"] if h else 0, h["chua_len"] if h else 0,
                     ("–" if not h or h["ty_le"] is None else f"{h['ty_le']}%", _lop(h["ty_le"] if h else None)),
                     x["so_ngay"] if x else 0, _pc(x["ban"], x["mt"]) if x else "–", _pc(x["onl"], x["dk"]) if x else "–"])
    dong.sort(key=lambda r: (r[5][0] == "–", -int(r[5][0].rstrip("%")) if r[5][0] != "–" else 0, r[0]))
    if not dong:
        return [tom, html.Div("Chưa có ca hoặc báo cáo nào trong khoảng này.", className="onl-hq-ghi")]
    kh = [[k["nhan"], k["ca"], k["dung"], k["tre"], k["chua_len"], ("–" if k["ty_le"] is None else f"{k['ty_le']}%", _lop(k["ty_le"]))] for k in hq["khung"]]
    out = [tom, *ghi,
           html.Div("Theo nhân viên", className="onl-hq-tde"),
           _bang(["Nhân viên", "Ca", "Đúng hẹn", "Trễ", "Chưa lên", "Tỷ lệ đúng hẹn", "Ngày có báo cáo", "Bán / mục tiêu", "Online / dự kiến"], dong)]
    if kh:
        out += [html.Div("Theo khung giờ HẸN (khung giờ sale khai lúc tạo ca)", className="onl-hq-tde"),
                _bang(["Khung giờ", "Ca", "Đúng hẹn", "Trễ", "Chưa lên", "Tỷ lệ đúng hẹn"], kh)]
    if len(xh["ngay"]) >= 2:
        out += [html.Div("Xu hướng theo ngày", className="onl-hq-tde"), _hinh(xh["ngay"])]
    out.append(html.Div(["Đúng hẹn: ca đã online khi còn trong hạn khung giờ hẹn. Trễ: online muộn hơn hạn. Chưa lên: quá hạn mà chưa online hoặc đã dời sang mai. ",
                         "Giờ online là giờ sale bấm nút nên có thể muộn hơn giờ thật."], className="onl-hq-ghi"))
    return out


def register(app):
    @app.callback(Output("onl-hq", "className"), Output("onl-hq-tieu-de", "children"), Output("onl-hq-than", "children"),
                  Input("onl-hq-mo", "n_clicks"), Input("onl-hq-dong", "n_clicks"), Input("onl-hq-nen", "n_clicks"), Input("onl-hq-ky", "value"),
                  State("bn-phong", "value"), State("onl-hq", "className"), prevent_initial_call=True)
    def _hq(mo, _dong, _nen, ky, code, lop):
        from app.ui.pages import baocaongay as bn
        t = ctx.triggered_id
        if t in ("onl-hq-dong", "onl-hq-nen"):
            return "modal", no_update, no_update
        if t == "onl-hq-mo" and not mo:
            raise PreventUpdate
        if t == "onl-hq-ky" and "mo" not in (lop or ""):
            raise PreventUpdate                                # đổi kỳ khi cửa sổ đang đóng: không dựng gì
        phong = bn._phong_hop_le(code)
        return "modal mo", f"Hiệu quả & xu hướng · {code}", noi_dung(phong, ky or "7")
