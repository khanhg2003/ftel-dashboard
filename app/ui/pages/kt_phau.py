"""Trang Phễu triển khai: hợp đồng tồn đang nằm ở giai đoạn nào, và mỗi khâu của hợp đồng đã triển khai xong mất bao lâu (khâu nào chậm nhất)."""
from __future__ import annotations

import plotly.graph_objects as go
from dash import html

from app.kt import so_lieu as sl
from app.ui.components import card
from app.ui.pages import dvkh_chung as ch, kt_chung as kc


def topbar():
    return [html.Div([html.H1("Phễu triển khai"), html.Div("Ca tồn đang kẹt ở giai đoạn nào, mỗi khâu mất bao lâu", className="sub")])]


def _giai_doan(g):
    f = go.Figure(go.Bar(x=g["so"], y=g["giai_doan"], orientation="h", marker_color=[ch.XANH_NHAT, ch.XANH, ch.CAM, ch.TIM][:len(g)],
                         text=[f"{int(s)} ca · tuổi TB {ch.so(t, 1)} ngày" if t is not None else f"{int(s)} ca" for s, t in zip(g["so"], g["tuoi_tb"])],
                         textposition="outside", cliponaxis=False))
    f.update_yaxes(autorange="reversed")
    f.update_xaxes(visible=False)
    return f


def _khau(tom):
    r = tom[tom["trung_vi"].notna()]
    nho = r["so_mau"] < sl.TOI_THIEU_KHAU
    lon = r[~r["khau"].str.startswith("Tổng")]["trung_vi"].max() if (~r["khau"].str.startswith("Tổng")).any() else None
    mau = [ch.XAM if str(k).startswith("Tổng") else (ch.DO if v == lon else ch.XANH) for k, v in zip(r["khau"], r["trung_vi"])]
    f = go.Figure(go.Bar(x=r["trung_vi"], y=r["khau"], orientation="h", marker_color=mau,
                         text=[f"{ch.so(v, 1)} giờ" + (" (mẫu nhỏ)" if n else "") for v, n in zip(r["trung_vi"], nho)], textposition="outside", cliponaxis=False))
    f.update_yaxes(autorange="reversed")
    f.update_xaxes(visible=False)
    return f


def layout():
    ev = sl.su_kien()
    if ev.empty:
        return kc.chua_co_du_lieu()
    now = sl.bay_gio(ev)
    t = sl.ton(ev, now)
    g = sl.theo_giai_doan(t)
    ct, tom = sl.khau_trien_khai(ev)
    chua_nhan = int(g.loc[g["giai_doan"] == "Đã phân công", "so"].sum())
    cot_g = [ch.cot_chu("giai_doan", "Giai đoạn", 200), ch.cot_so("so", "Số ca", 90), ch.cot_so1("tuoi_tb", "Tuổi tồn TB (ngày)", 150), ch.cot_so("tu_7_ngay", f"Từ {sl.TON_LAU_NGAY} ngày", 110),
             ch.cot_so("qua_do", "Quá mốc đỏ", 110)]
    cot_k = [ch.cot_chu("khau", "Khâu", 300), ch.cot_so("so_mau", "Số hợp đồng", 120), ch.cot_so1("trung_vi", "Trung vị (giờ)", 130), ch.cot_so1("tb", "Trung bình (giờ)", 140),
             ch.cot_so1("lon_nhat", "Lâu nhất (giờ)", 130)]
    hl = sl.ly_do_hen_lai(ev)
    return html.Div([
        kc.ghi_chu_nguon(),
        ch.hang_kpi([("Hợp đồng tồn", ch.so(len(t)), "Đang chờ triển khai", ""),
                     ("Chưa ai nhận ca", ch.so(chua_nhan), "Đã phân công nhưng KTV chưa nhận", "warn" if chua_nhan else "ok"),
                     ("Đang xử lý", ch.so(int(g.loc[g["giai_doan"] == "Đang xử lý", "so"].sum())), "KTV đang thi công", ""),
                     ("Chờ theo dõi", ch.so(int(g.loc[g["giai_doan"] == "Đã xử lý đang theo dõi", "so"].sum())), "Đã làm, chờ khách hoặc hệ thống", "")]),
        html.Div("Hiện tại: ca tồn đang ở đâu", className="dv-tieu-nhom"),
        card([ch.khung(_giai_doan(g), 260, legend=False), ch.bang_df("kt-phau-gd", g, cot_g, None)], title="Hợp đồng tồn theo giai đoạn",
             desc="Giai đoạn lấy từ cột Tình trạng của file tồn. Ca đứng lâu ở giai đoạn đầu là ca chưa ai bắt tay vào làm."),
        html.Div("Đã làm xong: khâu nào chậm nhất", className="dv-tieu-nhom"),
        card([ch.khung(_khau(tom), 280, legend=False) if tom["trung_vi"].notna().any() else html.Div("Chưa có hợp đồng nào đủ các mốc thời gian.", className="desc"),
              ch.bang_df("kt-phau-khau", tom, cot_k, None)], title="Thời gian từng khâu (trung vị)",
             desc=f"Tính trên {int(tom['so_mau'].max()) if len(tom) else 0} hợp đồng trong file triển khai đúng hạn. File này chỉ liệt kê hợp đồng KHÔNG đúng hẹn nên số lệch về phía chậm; "
                  "khâu đỏ là khâu có trung vị lớn nhất."),
        html.Div("Vì sao phải hẹn lại", className="dv-tieu-nhom"),
        card([ch.cot_ngang(hl, "nhom", "so", 220, top=6) if len(hl) else html.Div("Chưa có hợp đồng nào hẹn từ 2 lần.", className="desc")], title="Nguyên nhân của lần hẹn lại sau cùng",
             desc="Lấy từ cột Nguyên nhân tích L2. “Từ phía KH” là khách đổi lịch, ô trống là KTV chưa ghi."),
        kc.cach_hieu(),
    ])


def register(app):
    return None
