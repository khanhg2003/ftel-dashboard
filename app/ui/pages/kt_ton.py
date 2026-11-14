"""Trang Tồn và lịch hẹn: danh sách hợp đồng tồn Kỹ thuật, lọc theo mốc hẹn và tuổi tồn."""
from __future__ import annotations

import plotly.graph_objects as go
from dash import Input, Output, dcc, html

from app.kt import so_lieu as sl
from app.ui.components import card, seg_control
from app.ui.pages import dvkh_chung as ch, kt_chung as kc

LOC = [("tat_ca", "Tất cả"), ("do", "Quá mốc đỏ"), ("xanh", "Quá mốc xanh"), ("lau", f"Tồn từ {sl.TON_LAU_NGAY} ngày")]


def topbar():
    return [html.Div([html.H1("Tồn và lịch hẹn"), html.Div("Hợp đồng chưa triển khai xong, hẹn tới đâu, tồn bao lâu", className="sub")])]


def layout():
    if not sl.co_du_lieu():
        return kc.chua_co_du_lieu()
    return html.Div([html.Div([html.Div([html.Label("Hiện"), seg_control("kt-ton-loc", LOC, "tat_ca")], className="field"), html.Div(className="grow")], className="toolbar loc-trang"),
                     dcc.Loading(html.Div(id="kt-ton-noi-dung"), type="dot")])


def loc(t, cach: str):
    if cach == "do":
        return t[t["qua_do"]]
    if cach == "xanh":
        return t[t["qua_xanh"]]
    return t[t["ngay_ton"] >= sl.TON_LAU_NGAY] if cach == "lau" else t


def _cot_tuoi(d):
    tuoi = sl.ton_theo_tuoi(d)
    f = go.Figure(go.Bar(x=tuoi["nhom"], y=tuoi["so"], marker_color=ch.XANH, text=tuoi["so"], textposition="outside", cliponaxis=False))
    f.update_yaxes(visible=False)
    return f


def register(app):
    @app.callback(Output("kt-ton-noi-dung", "children"), Input("kt-ton-loc", "value"))
    def _ve(cach):
        t = sl.ton(sl.su_kien(), sl.bay_gio())
        if t.empty:
            return html.Div("Chưa có hợp đồng tồn.", className="desc")
        d = loc(t, cach or "tat_ca")
        theo = d["nguoi"].value_counts().rename_axis("nhom").reset_index(name="so")
        return html.Div([
            ch.hang_kpi([("Đang hiện", ch.so(len(d)), f"Trên tổng {ch.so(len(t))} hợp đồng tồn", ""), ("Quá mốc đỏ", ch.so(int(d["qua_do"].sum())), "", "bad" if d["qua_do"].any() else "ok"),
                         ("Quá mốc xanh", ch.so(int(d["qua_xanh"].sum())), "", "warn" if d["qua_xanh"].any() else "ok"),
                         ("Tuổi tồn TB", f"{ch.so(d['ngay_ton'].mean(), 1)} ngày" if len(d) else "–", "", "")]),
            html.Div([card([ch.khung(_cot_tuoi(d), 260, legend=False)], title="Theo tuổi tồn"),
                      card([ch.cot_ngang(theo, "nhom", "so", 260, top=10) if len(theo) else html.Div("Không có hợp đồng nào.", className="desc")], title="Theo KTV")], className="dv-hai-cot"),
            html.Div("Danh sách hợp đồng", className="dv-tieu-nhom"),
            card([kc.bang_ton(d, "kt-ton-bang")], desc="Tồn lâu nhất trước. Mốc hẹn lấy từ file, không tự suy diễn.") if len(d) else html.Div("Không có hợp đồng nào ở mức này.", className="desc"),
        ])
