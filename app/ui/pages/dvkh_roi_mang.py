"""Trang Rời mạng: khách rời mạng, tỷ lệ so với khách đang hoạt động và so với khách mới, theo phòng và theo phường / xã."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, dcc, html

from app.dvkh import so_lieu as sl
from app.ui.components import card
from app.ui.pages import dvkh_chung as ch

TEN_PHONG = {"05.Da Nang": "Cả Đà Nẵng", "DNG-01": "DNG1", "DNG-02": "DNG2"}


def topbar():
    return [html.Div([html.H1("Rời mạng"), html.Div("Khách rời mạng so với khách đang hoạt động và khách mới, theo phòng và phường / xã", className="sub")])]


def layout():
    rm = sl.roi_mang()
    ngay = sorted(rm["ngay_chot"].dt.date.unique(), reverse=True) if len(rm) else []
    return html.Div([
        html.Div([html.Div([html.Label("Ngày chốt"), dcc.Dropdown(id="dvrm-ngay", options=[{"label": d.strftime("%d/%m/%Y"), "value": d.isoformat()} for d in ngay],
                                                                  value=ngay[0].isoformat() if ngay else None, clearable=False, style={"minWidth": "180px"})], className="field"),
                  html.Div(className="grow")], className="toolbar loc-trang"),
        dcc.Loading(html.Div(id="dvrm-noi-dung"), type="dot"),
    ])


COT_BANG = [("kh_active", "KH Active", 100, ch.cot_so), ("kh_dau_ky", "KH đầu kỳ", 100, ch.cot_so), ("gross_pttb", "Gross PTTB", 100, ch.cot_so),
            ("huy_ssd", "Hủy SSD", 90, ch.cot_so), ("ctbdv_du_kien", "CTBDV dự kiến", 120, ch.cot_so), ("kh_roi_mang", "KH rời mạng", 110, ch.cot_so),
            ("ty_le_roi_active", "% rời / Active", 110, "p2"), ("ty_le_roi_gross", "% rời / Gross", 110, "p1"), ("net_pttb", "Net PTTB", 90, ch.cot_so),
            ("ty_le_giu", "% giữ lại", 90, "p2")]
PCT_2 = {"function": "params.value == null ? '–' : Number(params.value).toLocaleString('vi-VN', {minimumFractionDigits: 2, maximumFractionDigits: 2}) + '%'"}


def _cot(ten_cot, tieu_de):
    out = [ch.cot_chu(ten_cot, tieu_de, None, pinned="left")]
    for f, t, w, kieu in COT_BANG:
        if kieu == "p2":
            out.append({"field": f, "headerName": t, "width": w, "type": "numericColumn", "valueFormatter": PCT_2})
        elif kieu == "p1":
            out.append(ch.cot_pct(f, t, w))
        else:
            out.append(kieu(f, t, w))
    return out


def _bieu_do_dong(r):
    """Cấu thành số khách rời mạng: Hủy SSD + CTBDV + chờ thanh lý + dự kiến, trừ số khôi phục."""
    buoc = [("Hủy SSD", r["huy_ssd"]), ("CTBDV", r["ctbdv"]), ("Chờ thanh lý", r["cho_thanh_ly"]), ("CTBDV dự kiến", r["ctbdv_du_kien"]),
            ("Khôi phục dịch vụ (CTBDV)", -(r["ctbdv_khoi_phuc"] or 0)), ("Khôi phục (HSSD)", -(r["hssd_khoi_phuc"] or 0))]
    buoc = [(t, v) for t, v in buoc if v]
    f = go.Figure(go.Waterfall(x=[t for t, _ in buoc] + ["KH rời mạng"], y=[v for _, v in buoc] + [0], measure=["relative"] * len(buoc) + ["total"],
                               text=[ch.so(v) for _, v in buoc] + [ch.so(r["kh_roi_mang"])], textposition="outside",
                               increasing={"marker": {"color": ch.CAM}}, decreasing={"marker": {"color": ch.LUC}}, totals={"marker": {"color": ch.XANH}}))
    return ch.khung(f, 320, legend=False)


def _quan(rm):
    q = rm[(rm["cap"] == "quan") & rm["ten"].str.lower().str.startswith(("phuong", "xa"))].copy()
    q["ten"] = q["ten"].map(sl.ten_phuong)
    return q.sort_values("kh_roi_mang", ascending=False)


def register(app):
    @app.callback(Output("dvrm-noi-dung", "children"), Input("dvrm-ngay", "value"))
    def _ve(ngay):
        rm_all = sl.roi_mang()
        if rm_all.empty or not ngay:
            return html.Div("Chưa có số liệu rời mạng.", className="desc")
        rm = rm_all[rm_all["ngay_chot"] == pd.Timestamp(ngay)]
        phong = rm[rm["cap"] == "phong"].copy()
        tong = phong[phong["ten"] == "05.Da Nang"]
        if tong.empty:
            return html.Div("Ngày chốt này không có dòng tổng Đà Nẵng.", className="desc")
        r = tong.iloc[0]
        truoc = rm_all[(rm_all["ngay_chot"] < pd.Timestamp(ngay)) & (rm_all["cap"] == "phong") & (rm_all["ten"] == "05.Da Nang")].sort_values("ngay_chot")
        t = truoc.iloc[-1] if len(truoc) else None
        gh = (lambda c: f"Ngày chốt trước ({t['ngay_chot']:%d/%m}): {ch.so(t[c])}") if t is not None else (lambda c: "")
        kpi_ = ch.hang_kpi([
            ("KH rời mạng", ch.so(r["kh_roi_mang"]), gh("kh_roi_mang") or f"Hủy SSD {ch.so(r['huy_ssd'])} · CTBDV dự kiến {ch.so(r['ctbdv_du_kien'])}", ""),
            ("Rời mạng / KH Active", ch.pct(r["ty_le_roi_active"], 2), f"Trên {ch.so(r['kh_active'])} khách đang hoạt động",
             ch.muc_theo_nguong(r["ty_le_roi_active"], 0.3, 0.6)),
            ("Rời mạng / Gross PTTB", ch.pct(r["ty_le_roi_gross"], 1), f"Cứ 100 khách mới mất {ch.so(r['ty_le_roi_gross'])} khách cũ", ch.muc_theo_nguong(r["ty_le_roi_gross"], 30, 50)),
            ("Net PTTB", ch.so(r["net_pttb"]), f"Gross PTTB {ch.so(r['gross_pttb'])}", ""),
            ("Tỷ lệ giữ lại", ch.pct(r["ty_le_giu"], 2), "", ""),
            ("Tăng trưởng khách", ch.pct(r["ty_le_tang"], 2), f"KH đầu kỳ {ch.so(r['kh_dau_ky'])}", "")])
        q = _quan(rm)
        phong["ten_hien"] = phong["ten"].map(TEN_PHONG).fillna(phong["ten"])
        ve = []
        if len(q):
            top = q.head(10)
            lon = q[q["gross_pttb"] >= 20].sort_values("ty_le_roi_gross", ascending=False)
            sc = go.Figure(go.Scatter(x=q["kh_active"], y=q["ty_le_roi_active"], mode="markers+text", text=q["ten"].str.replace("Phường ", "").str.replace("Xã ", ""),
                                      textposition="top center", marker={"size": (q["kh_roi_mang"].clip(lower=3) ** .6) * 3, "color": ch.XANH, "opacity": .7},
                                      hovertemplate="%{text}: %{x:,.0f} KH, %{y:.2f}% rời mạng<extra></extra>"))
            sc.update_xaxes(title="KH Active", showgrid=True, gridcolor="#EDF1F6")
            sc.update_yaxes(title="% rời mạng / Active", ticksuffix="%")
            ve = [html.Div(style={"height": "16px"}),
                  html.Div([card([ch.cot_ngang(top.assign(ten=top["ten"].str.replace("Phường ", "P. ")), "ten", "kh_roi_mang", 340, mau=ch.CAM)],
                                 title="Phường / xã có nhiều khách rời mạng nhất", desc="Số khách rời mạng"),
                            card([ch.cot_ngang(lon.assign(ten=lon["ten"].str.replace("Phường ", "P. ")), "ten", "ty_le_roi_gross", 340, mau=ch.DO, chu="{:.0f}%")],
                                 title="Rời mạng so với khách mới (Gross PTTB)", desc="Phường có từ 20 khách mới trở lên; cao nghĩa là mất gần bằng khách mới")], className="dv-hai-cot"),
                  html.Div(style={"height": "16px"}),
                  card([ch.khung(sc, 360, legend=False)], title="Quy mô và tỷ lệ rời mạng", desc="Chấm càng lớn khách rời mạng càng nhiều; chấm cao là tỷ lệ rời mạng cao"),
                  html.Div(style={"height": "16px"}),
                  card([ch.bang_df("dvrm-quan", q, _cot("ten", "Phường / xã"), 460)], title="Theo phường / xã", desc="Sắp xếp được theo từng cột")]
        lich_su = rm_all[(rm_all["cap"] == "phong") & (rm_all["ten"] == "05.Da Nang")].sort_values("ngay_chot")
        xu_huong = []
        if len(lich_su) >= 2:
            f = go.Figure(go.Scatter(x=lich_su["ngay_chot"], y=lich_su["ty_le_roi_active"], mode="lines+markers", line={"color": ch.XANH}))
            f.update_yaxes(ticksuffix="%")
            xu_huong = [html.Div(style={"height": "16px"}), card([ch.khung(f, 260, legend=False)], title="Xu hướng qua các ngày chốt", desc="Tỷ lệ rời mạng / KH Active, cả Đà Nẵng")]
        return html.Div([kpi_, html.Div([card([_bieu_do_dong(r)], title="Cấu thành khách rời mạng", desc="Hủy SSD + CTBDV + chờ thanh lý, trừ khách khôi phục"),
                                         card([ch.bang_df("dvrm-phong", phong, _cot("ten_hien", "Phòng"))], title="Theo phòng", desc="DNG1 và DNG2 (DNG-01, DNG-02 trong file)")],
                                        className="dv-hai-cot"), *ve, *xu_huong])
