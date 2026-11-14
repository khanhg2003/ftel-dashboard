"""Trang Triển khai đúng hẹn: KPI theo block (lần 1, chung, bảo trì 24 giờ, thời gian xử lý) và hợp đồng phải hẹn nhiều lần."""
from __future__ import annotations

import plotly.graph_objects as go
from dash import html

from app.kt import so_lieu as sl
from app.ui.components import card
from app.ui.pages import dvkh_chung as ch, kt_chung as kc


def topbar():
    return [html.Div([html.H1("Triển khai đúng hẹn"), html.Div("Đúng hẹn lần 1, đúng hẹn chung, bảo trì quá 24 giờ, theo từng block", className="sub")])]


def layout():
    blk = sl.theo_block(sl.kpi_block())
    if blk.empty:
        return card([html.Div("Chưa có file KPI theo block (file “Báo cáo KPI”: Block, Lô, Đúng hẹn lần 1, Bảo trì quá 24H).", className="desc")], title="Chưa có KPI theo block")
    r = blk[blk["tong_l1"] >= sl.TOI_THIEU_BLOCK]
    f = go.Figure([go.Bar(name="Đúng hẹn lần 1 (%)", x=r["block"], y=r["dung_hen_l1_pct"], marker_color=ch.CAM),
                   go.Bar(name="Đúng hẹn chung (%)", x=r["block"], y=r["dung_hen_pct"], marker_color=ch.XANH)])
    f.update_layout(barmode="group", yaxis_range=[0, 105])
    cot = [ch.cot_chu("block", "Block", 140), ch.cot_so("tong", "Số lần hẹn", 110), ch.cot_pct("dung_hen_l1_pct", "Đúng hẹn lần 1", 130), ch.cot_pct("dung_hen_pct", "Đúng hẹn chung", 130),
           ch.cot_so("qua_hen", "Quá hẹn", 100), ch.cot_pct("bao_tri_pct", "Bảo trì quá 24 giờ", 140), ch.cot_so1("tgxl_tb", "TGXL TB (giờ)", 120), ch.cot_pct("tin_pnc_pct", "Tích hẹn TIN/PNC", 140)]
    nhieu = sl.trien_khai(sl.su_kien())
    nhieu = nhieu[nhieu["so_lan"] >= 3].assign(dung_hen=lambda d: d["dung_hen"].map({True: "Đúng", False: "Không"}))
    cot2 = [ch.cot_chu("so_hd", "Mã hợp đồng", 130), ch.cot_chu("nguoi", "KTV", 120), ch.cot_so("so_lan", "Số lần hẹn", 110), ch.cot_chu("dung_hen", "Đúng hẹn", 100)]
    return html.Div([
        kc.ghi_chu_nguon(),
        card([ch.khung(f, 340)], title=f"Đúng hẹn theo block (block từ {sl.TOI_THIEU_BLOCK} lần hẹn)", desc="Block nào lần 1 thấp hơn hẳn chung là hẹn lần đầu hay bị lệch."),
        html.Div(style={"height": "16px"}),
        card([ch.bang_df("kt-blk-bang", blk, cot, 380)], title="Chi tiết theo block", desc="Tỷ lệ tính lại từ số đếm của các lô trong block. Thấp nhất (lần 1) trước."),
        html.Div("Hợp đồng hẹn nhiều lần", className="dv-tieu-nhom"),
        card([ch.bang_df("kt-nhieu-bang", nhieu, cot2, 300)], desc="Hợp đồng trong file triển khai đúng hạn có từ 3 lần hẹn trở lên.") if len(nhieu) else html.Div("Không có hợp đồng nào hẹn từ 3 lần.", className="desc"),
        kc.cach_hieu(),
    ])


def register(app):
    return None
