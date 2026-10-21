"""Trang Công nợ: tiến độ thu nợ theo ngày (so tháng trước cùng ngày thu), theo phòng và theo phường / xã, tiền còn nợ."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, dcc, html

from app.dvkh import so_lieu as sl
from app.ui.components import card, seg_control
from app.ui.pages import dvkh_chung as ch

DON_VI = [("tong", "Cả Đà Nẵng"), ("DNG1", "DNG1"), ("DNG2", "DNG2")]
TEN_PHONG = {"tong": "To tal DNG CN 30", "DNG1": "DNG1", "DNG2": "DNG2"}
QUAN_THEO_PHONG = {"tong": "DNG", "DNG1": "DNG 1", "DNG2": "DNG 2"}


def topbar():
    return [html.Div([html.H1("Công nợ"), html.Div("Tỷ lệ thu nợ theo ngày, so với tháng trước, theo phòng và phường / xã", className="sub")])]


def layout():
    cn = sl.cong_no_ngay()
    ky = sorted(cn["ky_no"].unique(), reverse=True) if len(cn) else []
    return html.Div([
        html.Div([html.Div([html.Label("Đơn vị"), seg_control("dvcn-don-vi", DON_VI, "tong")], className="field"),
                  html.Div([html.Label("Kỳ hoá đơn"), dcc.Dropdown(id="dvcn-ky", options=[{"label": f"Hoá đơn tháng {k[-2:]}/{k[:4]}", "value": k} for k in ky],
                                                                    value=ky[0] if ky else None, clearable=False, style={"minWidth": "220px"})], className="field"),
                  html.Div(className="grow")], className="toolbar loc-trang"),
        dcc.Loading(html.Div(id="dvcn-noi-dung"), type="dot"),
    ])


def _duong(cn, don_vi, ky, kieu):
    """Đường tỷ lệ thu của kỳ đang xem và kỳ liền trước theo ngày thu thứ."""
    ten = TEN_PHONG[don_vi]
    s = cn[(cn["cap"] == "phong") & (cn["ten"] == ten)]
    cac_ky = sorted(s["ky_no"].unique())
    chon = [k for k in cac_ky if k <= ky][-2:]
    f = go.Figure()
    for i, k in enumerate(chon):
        x = s[s["ky_no"] == k]
        moi = k == chon[-1]
        f.add_scatter(x=x["so_ngay"], y=x[kieu] * 100, mode="lines+markers", name=f"Hoá đơn tháng {k[-2:]}",
                      line={"color": ch.XANH if moi else ch.XAM, "dash": "solid" if moi else "dot", "width": 2.6 if moi else 2})
    f.update_xaxes(title="Ngày thu thứ")
    f.update_yaxes(ticksuffix="%", range=[0, 102])
    return f, chon


def _tang_moi_ngay(cn, don_vi, ky):
    s = cn[(cn["cap"] == "phong") & (cn["ten"] == TEN_PHONG[don_vi]) & (cn["ky_no"] == ky)].sort_values("so_ngay")
    if len(s) < 2:
        return None
    d = s["ty_le_bill"].diff() * 100 / s["so_ngay"].diff()
    f = go.Figure(go.Bar(x=s["so_ngay"], y=d, marker_color=ch.CAM, hovertemplate="Ngày thu %{x}: +%{y:.1f} điểm %/ngày<extra></extra>"))
    f.update_xaxes(title="Ngày thu thứ")
    f.update_yaxes(ticksuffix=" đ")
    return f


def register(app):
    @app.callback(Output("dvcn-noi-dung", "children"), Input("dvcn-don-vi", "value"), Input("dvcn-ky", "value"))
    def _ve(don_vi, ky):
        cn = sl.cong_no_ngay()
        if cn.empty or not ky:
            return html.Div("Chưa có số liệu công nợ.", className="desc")
        don_vi = don_vi or "tong"
        s = cn[(cn["cap"] == "phong") & (cn["ten"] == TEN_PHONG[don_vi]) & (cn["ky_no"] == ky)].sort_values("so_ngay")
        if s.empty:
            return html.Div("Kỳ này chưa có số liệu.", className="desc")
        moi = s.iloc[-1]
        cac_ky = sorted(cn["ky_no"].unique())
        kt = cac_ky[cac_ky.index(ky) - 1] if cac_ky.index(ky) > 0 else None
        cu = None
        if kt:
            x = cn[(cn["cap"] == "phong") & (cn["ten"] == TEN_PHONG[don_vi]) & (cn["ky_no"] == kt) & (cn["so_ngay"] <= moi["so_ngay"])].sort_values("so_ngay")
            cu = x.iloc[-1] if len(x) else None
        chenh_b = (moi["ty_le_bill"] - cu["ty_le_bill"]) * 100 if cu is not None else None
        chenh_d = (moi["ty_le_dt"] - cu["ty_le_dt"]) * 100 if cu is not None else None
        ct = sl.cong_no_chot()
        ct = ct[ct["ngay_chot"] == ct["ngay_chot"].max()] if len(ct) else ct
        p = ct[(ct["cap"] == "phong") & (ct["chi_nhanh"] == {"tong": "", "DNG1": "DNG_1", "DNG2": "DNG_2"}[don_vi])] if len(ct) else ct
        con_no = p.iloc[0] if len(p) else None
        kpi_ = ch.hang_kpi([
            ("Thu theo hoá đơn (bill)", ch.pct(moi["ty_le_bill"] * 100), f"Ngày thu thứ {int(moi['so_ngay'])} ({moi['ngay']:%d/%m})", ""),
            ("Thu theo doanh thu", ch.pct(moi["ty_le_dt"] * 100), "", ""),
            ("So với tháng trước (bill)", f"{'+' if (chenh_b or 0) > 0 else '−'}{ch.so(abs(chenh_b), 1)} điểm %" if chenh_b is not None else "–",
             f"Cùng ngày thu thứ {int(moi['so_ngay'])}: {ch.pct(cu['ty_le_bill'] * 100)}" if cu is not None else "Chưa có kỳ trước", "ok" if (chenh_b or 0) >= 0 else "bad"),
            ("So với tháng trước (doanh thu)", f"{'+' if (chenh_d or 0) > 0 else '−'}{ch.so(abs(chenh_d), 1)} điểm %" if chenh_d is not None else "–",
             f"Kỳ trước: {ch.pct(cu['ty_le_dt'] * 100)}" if cu is not None else "", "ok" if (chenh_d or 0) >= 0 else "bad"),
            ("Tiền còn nợ", f"{ch.so(con_no['tt_con_no'] / 1e6, 0)} triệu" if con_no is not None else "–",
             f"{ch.so(con_no['hd_con_no'])} hoá đơn chưa thu" if con_no is not None else "", "warn" if con_no is not None else "")])
        f1, _ = _duong(cn, don_vi, ky, "ty_le_bill")
        f2, _ = _duong(cn, don_vi, ky, "ty_le_dt")
        tang = _tang_moi_ngay(cn, don_vi, ky)
        # theo phường / xã (ảnh chụp hệ thống đổ hằng ngày)
        q = ct[ct["cap"] == "quan"].copy() if len(ct) else pd.DataFrame()
        phan_q = []
        if len(q):
            if don_vi != "tong":
                q = q[q["chi_nhanh"] == {"DNG1": "DNG_1", "DNG2": "DNG_2"}[don_vi]]
            q = q.assign(ten=q["ten"].map(sl.ten_phuong)).groupby("ten").agg(so_hd=("so_hd", "sum"), tong_tien=("tong_tien", "sum"), hd_con_no=("hd_con_no", "sum"), tt_con_no=("tt_con_no", "sum")).reset_index()
            q["ty_le_bill"] = (1 - q["hd_con_no"] / q["so_hd"].replace(0, float("nan"))) * 100
            q["ty_le_dt"] = (1 - q["tt_con_no"] / q["tong_tien"].replace(0, float("nan"))) * 100
            q["tt_con_no_tr"] = q["tt_con_no"] / 1e6
            q = q[q["so_hd"] >= 50].sort_values("tt_con_no", ascending=False)
            cot = [ch.cot_chu("ten", "Phường / xã", None, pinned="left"), ch.cot_so("so_hd", "Số hoá đơn", 110), ch.cot_so("hd_con_no", "Còn nợ (HĐ)", 120),
                   ch.cot_so1("tt_con_no_tr", "Còn nợ (triệu đ)", 140), ch.cot_pct("ty_le_bill", "Thu theo bill", 110), ch.cot_pct("ty_le_dt", "Thu theo DT", 110)]
            top = q.head(10).assign(ten=lambda x: x["ten"].str.replace("Phường ", "P. "))
            phan_q = [html.Div(style={"height": "16px"}),
                      html.Div([card([ch.cot_ngang(top, "ten", "tt_con_no_tr", 340, mau=ch.CAM, chu="{:.0f} tr")], title="Phường / xã còn nợ nhiều nhất", desc="Triệu đồng, theo ảnh chụp công nợ mới nhất"),
                                card([ch.bang_df("dvcn-quan", q, cot, 340)], title="Theo phường / xã", desc="Chỉ phường có từ 50 hoá đơn")], className="dv-hai-cot")]
        return html.Div([kpi_, html.Div([card([ch.khung(f1, 320)], title="Tiến độ thu theo hoá đơn (bill)", desc="Đường liền là kỳ đang xem, đường chấm là kỳ trước"),
                                         card([ch.khung(f2, 320)], title="Tiến độ thu theo doanh thu", desc="Tỷ lệ doanh thu đã thu")], className="dv-hai-cot"),
                         *([html.Div(style={"height": "16px"}), card([ch.khung(tang, 240, legend=False)], title="Mỗi ngày thu thêm bao nhiêu",
                                                                      desc="Điểm % tăng thêm mỗi ngày thu; thấp dần là thu chậm lại, cần dồn lực gọi nhắc")] if tang is not None else []),
                         *phan_q])
