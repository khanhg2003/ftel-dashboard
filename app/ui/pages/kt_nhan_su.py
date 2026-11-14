"""Trang Hiệu suất KTV: một dòng mỗi kỹ thuật viên, tồn, quá mốc hẹn, checklist lặp, triển khai không đúng hẹn."""
from __future__ import annotations

import plotly.graph_objects as go
from dash import html

from app.kt import so_lieu as sl
from app.ui.components import card
from app.ui.pages import dvkh_chung as ch, kt_chung as kc


def topbar():
    return [html.Div([html.H1("Hiệu suất KTV"), html.Div("Ai đang giữ nhiều hợp đồng tồn, ai bị quá mốc hẹn, ai có nhiều checklist lặp", className="sub")])]


def layout():
    ev = sl.su_kien()
    if ev.empty:
        return kc.chua_co_du_lieu()
    k = sl.theo_ktv(ev, sl.bay_gio(ev))
    if k.empty:
        return html.Div("Chưa có sự kiện nào ghi tên kỹ thuật viên.", className="desc")
    d = k.head(15).iloc[::-1]
    f = go.Figure([go.Bar(name="Tồn dưới 7 ngày", y=d["ktv"], x=d["ton"] - d["ton_lau"], orientation="h", marker_color=ch.XANH),
                   go.Bar(name=f"Tồn từ {sl.TON_LAU_NGAY} ngày", y=d["ktv"], x=d["ton_lau"], orientation="h", marker_color=ch.CAM)])
    f.update_layout(barmode="stack")
    cot = [ch.cot_chu("ktv", "KTV", 120), ch.cot_so("ton", "Hợp đồng tồn", 120), ch.cot_so("ton_lau", f"Tồn từ {sl.TON_LAU_NGAY} ngày", 130),
           ch.cot_so("qua_xanh", "Quá mốc xanh", 120), ch.cot_so("qua_do", "Quá mốc đỏ", 110), ch.cot_so1("tuoi_tb", "Tuổi tồn TB (ngày)", 140),
           ch.cot_so("checklist", "Checklist lặp", 120), ch.cot_so("hd_lap", "Hợp đồng lặp", 120), ch.cot_so("sau_tk", "Lỗi sau triển khai", 140),
           ch.cot_so("khong_dung_hen", "Triển khai không đúng hẹn", 190)]
    return html.Div([
        kc.ghi_chu_nguon(),
        card([ch.khung(f, max(260, 28 * len(d) + 80))], title="Ai đang giữ nhiều hợp đồng tồn", desc="Mỗi thanh là một KTV, cam là phần tồn đã từ 7 ngày."),
        html.Div(style={"height": "16px"}),
        card([ch.bang_df("kt-ktv-bang", k, cot, 420)], title="Bảng chi tiết",
             desc="Số hợp đồng không chia theo số khách phụ trách vì file Kỹ thuật chưa có cột đó, nên đây là số đếm thô, chưa so sánh công bằng giữa các KTV."),
        kc.cach_hieu(),
    ])


def register(app):
    return None
