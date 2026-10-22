"""Trang Công nợ: tiến độ thu nợ theo ngày (so tháng trước cùng ngày thu), theo phòng và theo phường / xã, tiền còn nợ."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, dcc, html

from app.dvkh import so_lieu as sl, xu_huong as xh
from app.ui.components import card, seg_control
from app.ui.pages import dvkh_chung as ch, dvkh_ve as ve

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


def _tang_moi_ngay(cn, don_vi, ky):
    s = cn[(cn["cap"] == "phong") & (cn["ten"] == TEN_PHONG[don_vi]) & (cn["ky_no"] == ky)].sort_values("so_ngay")
    if len(s) < 2:
        return None
    d = s["ty_le_bill"].diff() * 100 / s["so_ngay"].diff()
    f = go.Figure(go.Bar(x=s["so_ngay"], y=d, marker_color=ch.CAM, hovertemplate="Ngày %{x}: +%{y:.1f} điểm %/ngày<extra></extra>"))
    f.update_xaxes(title="Ngày trong tháng")
    f.update_yaxes(ticksuffix=" đ")
    return f


def _kpi(moi, cu, con_no, db_b):
    chenh_b = (moi["ty_le_bill"] - cu["ty_le_bill"]) * 100 if cu is not None else None
    chenh_d = (moi["ty_le_dt"] - cu["ty_le_dt"]) * 100 if cu is not None else None
    cac = [("Thu theo hoá đơn (bill)", ch.pct(moi["ty_le_bill"] * 100), f"Đến ngày {int(moi['so_ngay'])} ({moi['ngay']:%d/%m})", ""),
           ("Thu theo doanh thu", ch.pct(moi["ty_le_dt"] * 100), "", ""),
           ("So với tháng trước (bill)", f"{'+' if (chenh_b or 0) > 0 else '−'}{ch.so(abs(chenh_b), 1)} điểm %" if chenh_b is not None else "–",
            f"Tháng trước cùng ngày {int(moi['so_ngay'])}: {ch.pct(cu['ty_le_bill'] * 100)}" if cu is not None else "Chưa có kỳ trước", "ok" if (chenh_b or 0) >= -0.5 else "bad"),
           ("So với tháng trước (doanh thu)", f"{'+' if (chenh_d or 0) > 0 else '−'}{ch.so(abs(chenh_d), 1)} điểm %" if chenh_d is not None else "–",
            f"Kỳ trước: {ch.pct(cu['ty_le_dt'] * 100)}" if cu is not None else "", "ok" if (chenh_d or 0) >= -0.5 else "bad"),
           ("Tiền còn nợ", f"{ch.so(con_no['tt_con_no'] / 1e6, 0)} triệu" if con_no is not None else "–",
            f"{ch.so(con_no['hd_con_no'])} hoá đơn chưa thu" if con_no is not None else "", "warn" if con_no is not None else "")]
    if db_b:
        cuoi = db_b["cuoi_ky_cu"] * 100
        cac.append(("Dự báo cuối kỳ (bill)", ch.pct(db_b["du_bao_cuoi_ky"] * 100), f"Kỳ trước đạt {ch.pct(cuoi)}", ch.muc_theo_nguong(db_b["du_bao_cuoi_ky"] * 100, cuoi - .3, cuoi - 1.5, cao_xau=False)))
    return ch.hang_kpi(cac)


def _phan_phuong(ct, don_vi):
    q = ct[ct["cap"] == "quan"].copy() if len(ct) else pd.DataFrame()
    if q.empty:
        return []
    if don_vi != "tong":
        q = q[q["chi_nhanh"] == {"DNG1": "DNG_1", "DNG2": "DNG_2"}[don_vi]]
    q = q.assign(ten=q["ten"].map(sl.ten_phuong)).groupby("ten").agg(so_hd=("so_hd", "sum"), tong_tien=("tong_tien", "sum"), hd_con_no=("hd_con_no", "sum"),
                                                                       tt_con_no=("tt_con_no", "sum")).reset_index()
    q["ty_le_bill"] = (1 - q["hd_con_no"] / q["so_hd"].replace(0, float("nan"))) * 100
    q["ty_le_dt"] = (1 - q["tt_con_no"] / q["tong_tien"].replace(0, float("nan"))) * 100
    q["tt_con_no_tr"] = q["tt_con_no"] / 1e6
    q = q[q["so_hd"] >= 50].sort_values("tt_con_no", ascending=False)
    cot = [ch.cot_chu("ten", "Phường / xã", None, pinned="left"), ch.cot_so("so_hd", "Số hoá đơn", 110), ch.cot_so("hd_con_no", "Còn nợ (HĐ)", 120),
           ch.cot_so1("tt_con_no_tr", "Còn nợ (triệu đ)", 140), ch.cot_pct("ty_le_bill", "Thu theo bill", 110), ch.cot_pct("ty_le_dt", "Thu theo DT", 110)]
    top = q.head(10).assign(ten=lambda x: x["ten"].str.replace("Phường ", "P. "))
    return [html.Div(style={"height": "16px"}),
            html.Div([card([ch.cot_ngang(top, "ten", "tt_con_no_tr", 340, mau=ch.CAM, chu="{:.0f} tr")], title="Phường / xã còn nợ nhiều nhất", desc="Triệu đồng, theo ảnh chụp công nợ mới nhất"),
                      card([ch.bang_df("dvcn-quan", q, cot, 340)], title="Theo phường / xã", desc="Chỉ phường có từ 50 hoá đơn")], className="dv-hai-cot")]


def _phan_quan(cn):
    """Bản đồ nhiệt quận × ngày và xếp hạng quận thu chậm nhất so với tháng trước (cùng ngày trong tháng)."""
    m = xh.chenh_dich_chuyen(cn)
    if m.empty:
        return []
    cuoi = m.iloc[:, -1].dropna().sort_values()
    ngay_cuoi = int(m.columns[-1])
    mau = [ch.DO if v < -0.5 else (ch.LUC if v > 0.5 else ch.XAM) for v in cuoi]
    f = go.Figure(go.Bar(y=cuoi.index.map(ve.ten_quan), x=cuoi.values, orientation="h", marker_color=mau, text=[f"{v:+.1f}" for v in cuoi.values], textposition="outside", cliponaxis=False))
    f.update_xaxes(zeroline=True, zerolinecolor="#9AA7B8", title="điểm %")
    f.update_yaxes(automargin=True)
    return [html.Div("Theo quận / huyện", className="dv-tieu-nhom"),
            html.Div([card([ve.nhiet_chenh(m)], title="Quận nào thu chậm hơn tháng trước, vào ngày nào",
                           desc="Mỗi ô là chênh tỷ lệ thu theo hoá đơn giữa tháng này và tháng trước, cùng ngày trong tháng. Ô đỏ là thu chậm hơn, ô xanh là nhanh hơn."),
                      card([ch.khung(f, max(260, 34 * len(cuoi) + 80), legend=False)], title=f"Chênh so với tháng trước, đến ngày {ngay_cuoi}",
                           desc="Thanh đỏ là quận đang thu chậm hơn tháng trước; ưu tiên dồn lực gọi nhắc.")], className="dv-hai-cot")]


def register(app):
    @app.callback(Output("dvcn-noi-dung", "children"), Input("dvcn-don-vi", "value"), Input("dvcn-ky", "value"))
    def _ve(don_vi, ky):
        cn = sl.cong_no_ngay()
        if cn.empty or not ky:
            return html.Div("Chưa có số liệu công nợ.", className="desc")
        don_vi = don_vi or "tong"
        ten = TEN_PHONG[don_vi]
        s = cn[(cn["cap"] == "phong") & (cn["ten"] == ten) & (cn["ky_no"] == ky)].sort_values("so_ngay")
        if s.empty:
            return html.Div("Kỳ này chưa có số liệu.", className="desc")
        moi = s.iloc[-1]
        cac_ky = sorted(cn["ky_no"].unique())
        kt = cac_ky[cac_ky.index(ky) - 1] if cac_ky.index(ky) > 0 else None
        cu = None
        if kt:
            x = cn[(cn["cap"] == "phong") & (cn["ten"] == ten) & (cn["ky_no"] == kt) & (cn["so_ngay"] <= moi["so_ngay"])].sort_values("so_ngay")
            cu = x.iloc[-1] if len(x) else None
        ct = sl.cong_no_chot()
        ct = ct[ct["ngay_chot"] == ct["ngay_chot"].max()] if len(ct) else ct
        p = ct[(ct["cap"] == "phong") & (ct["chi_nhanh"] == {"tong": "", "DNG1": "DNG_1", "DNG2": "DNG_2"}[don_vi])] if len(ct) else ct
        la_moi = ky == cac_ky[-1]
        db_b, db_d = (xh.du_bao_cong_no(cn, ten), xh.du_bao_cong_no(cn, ten, "ty_le_dt")) if la_moi else (None, None)
        tang = _tang_moi_ngay(cn, don_vi, ky)
        return html.Div([_kpi(moi, cu, p.iloc[0] if len(p) else None, db_b),
                         html.Div([card([ve.duong_cong_no(cn, ten, db_b, "ty_le_bill", ky_den=ky)], title="Tiến độ thu theo hoá đơn (bill)",
                                        desc="Đường liền là kỳ đang xem, đường chấm là kỳ trước, đường đứt là dự báo theo nhịp kỳ trước"),
                                   card([ve.duong_cong_no(cn, ten, db_d, "ty_le_dt", ky_den=ky)], title="Tiến độ thu theo doanh thu", desc="Tỷ lệ doanh thu đã thu, cùng cách vẽ dự báo")],
                                  className="dv-hai-cot"),
                         *([html.Div(style={"height": "16px"}), card([ch.khung(tang, 240, legend=False)], title="Mỗi ngày thu thêm bao nhiêu",
                                                                      desc="Điểm % tăng thêm mỗi ngày; thấp dần là thu chậm lại, cần dồn lực gọi nhắc")] if tang is not None else []),
                         *_phan_quan(cn), *_phan_phuong(ct, don_vi)])
