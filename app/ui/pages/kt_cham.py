"""Trang Chậm do ai: ca tồn Kỹ thuật đang chờ phía nào (khách, kỹ thuật, hạ tầng, kinh doanh, hệ thống) và ca nào đang "im lặng".

Nhãn lấy từ ghi chú KTV bằng luật từ khoá (`doc_kt.phan_loai_ghi_chu`), không dùng AI và không lưu nguyên văn ghi chú. Đây là gợi ý để trao đổi, không phải kết luận trách nhiệm."""
from __future__ import annotations

import plotly.graph_objects as go
from dash import Input, Output, dcc, html

from app.kt import so_lieu as sl
from app.lien_khoi import doc_kt
from app.ui.components import card, seg_control
from app.ui.pages import dvkh_chung as ch, kt_chung as kc

MAU = {"khach": ch.TIM, "ky_thuat": ch.CAM, "ha_tang": ch.DO, "kinh_doanh": ch.XANH, "he_thong": ch.XANH_NHAT, "chua_ghi": ch.XAM}
LOC = [("all", "Tất cả")] + [(m, doc_kt.NHOM_GHI_CHU[m]) for m in sl.THU_TU_NHOM]


def topbar():
    return [html.Div([html.H1("Chậm do ai"), html.Div("Ca tồn đang chờ phía nào, ca nào không ai cập nhật", className="sub")])]


def layout():
    if sl.su_kien().empty:
        return kc.chua_co_du_lieu()
    return html.Div([html.Div([html.Div([html.Label("Phía đang chờ"), seg_control("kt-cham-loc", LOC, "all")], className="field"), html.Div(className="grow")], className="toolbar loc-trang"),
                     dcc.Loading(html.Div(id="kt-cham-noi-dung"), type="dot")])


def _chong(t):
    g = t.groupby(["ly_do_ma", "tinh_trang"]).size().unstack(fill_value=0)
    f = go.Figure()
    for tt in sl.GIAI_DOAN_TON:
        if tt in g.columns:
            f.add_bar(name=tt, y=[doc_kt.NHOM_GHI_CHU[m] for m in g.index], x=g[tt], orientation="h")
    f.update_layout(barmode="stack")
    f.update_yaxes(autorange="reversed")
    return f


def _bang(d):
    d = d.assign(tao_luc=d["tao_luc"].dt.strftime("%d/%m %H:%M"), ghi_chu_luc=d["ghi_chu_luc"].dt.strftime("%d/%m %H:%M").fillna("Chưa từng ghi"))
    cot = [ch.cot_chu("so_hd", "Mã hợp đồng", 130), ch.cot_chu("nguoi", "KTV", 110), ch.cot_chu("ly_do", "Đang chờ", 130), ch.cot_chu("tinh_trang", "Tình trạng", 170),
           ch.cot_so1("ngay_ton", "Ngày tồn", 90), ch.cot_chu("ghi_chu_luc", "Ghi chú cuối", 120), ch.cot_so1("gio_im_lang", "Im lặng (giờ)", 120), ch.cot_so("phan_tuyen", "Lần phân tuyến", 130)]
    return ch.bang_df("kt-cham-bang", d, cot, 420)


def register(app):
    @app.callback(Output("kt-cham-noi-dung", "children"), Input("kt-cham-loc", "value"))
    def _ve(loc):
        ev = sl.su_kien()
        t = sl.ton(ev, sl.bay_gio(ev))
        if t.empty:
            return html.Div("Chưa có hợp đồng tồn.", className="desc")
        cd = sl.cham_do_ai(t)
        il = sl.im_lang(t)
        d = t if loc in (None, "all") else t[t["ly_do_ma"] == loc]
        d = d.assign(gio_im_lang=d["gio_im_lang"].fillna(d["ngay_ton"] * 24)).sort_values("gio_im_lang", ascending=False)
        so = {r["ma"]: int(r["so"]) for r in cd.to_dict("records")}
        pct = lambda m: ch.pct(100.0 * so.get(m, 0) / len(t))                            # noqa: E731
        ph = cd[cd["so"] > 0]
        f2 = go.Figure(go.Bar(x=ph["tuoi_tb"], y=ph["nhom"], orientation="h", marker_color=[MAU[m] for m in ph["ma"]], text=[f"{ch.so(v, 1)} ngày" for v in ph["tuoi_tb"]], textposition="outside", cliponaxis=False))
        f2.update_yaxes(autorange="reversed")
        f2.update_xaxes(visible=False)
        return html.Div([
            ch.hang_kpi([("Chờ khách hàng", pct("khach"), f"{so.get('khach', 0)} ca: khách hẹn lại, nhà chưa xong, không nghe máy", ""),
                         ("Chờ Kỹ thuật / hạ tầng", ch.pct(100.0 * (so.get("ky_thuat", 0) + so.get("ha_tang", 0) + so.get("he_thong", 0)) / len(t)), "Thiếu trụ, tuyến xa, thời tiết, hệ thống lỗi", ""),
                         ("Chờ Kinh doanh", pct("kinh_doanh"), "Hoá đơn, thanh toán, liên hệ khách", "warn" if so.get("kinh_doanh") else "ok"),
                         ("Chưa ghi lý do", pct("chua_ghi"), f"{so.get('chua_ghi', 0)} ca không biết chờ ai", "bad" if so.get("chua_ghi", 0) >= 0.4 * len(t) else "warn"),
                         (f"Im lặng quá {sl.GIO_IM_LANG} giờ", ch.so(len(il)), "Ghi chú cuối đã cũ hoặc chưa từng có", "warn" if len(il) else "ok")]),
            html.Div([card([ch.khung(_chong(t), 300)], title="Phía đang chờ, chia theo giai đoạn", desc="Mỗi thanh là một phía; màu là giai đoạn của ca."),
                      card([ch.khung(f2, 300, legend=False)], title="Tuổi tồn trung bình theo phía", desc="Phía nào có ca tồn lâu nhất.")], className="dv-hai-cot"),
            html.Div("Danh sách ca", className="dv-tieu-nhom"),
            card([_bang(d)], desc="Im lặng lâu nhất trước. Cột “Đang chờ” là nhãn từ ghi chú của KTV, chưa phải kết luận trách nhiệm.") if len(d) else html.Div("Không có ca nào ở nhóm này.", className="desc"),
            kc.cach_hieu(),
        ])
