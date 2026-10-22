"""Trang Rời mạng: khách rời mạng, tỷ lệ so với khách đang hoạt động và so với khách mới, theo phòng và theo phường / xã."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, dcc, html

from app.dvkh import khai_thac as kt, so_lieu as sl
from app.ui.components import card
from app.ui.pages import dvkh_chung as ch, dvkh_ve as ve

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


def _ten_ngan(t):
    return str(t).replace("Phường ", "P. ").replace("Xã ", "Xã ")


def _gross_va_roi(q):
    """Hai thanh mỗi phường: khách mới (Gross PTTB) và khách rời mạng. Thanh cam dài gần bằng thanh xanh là mất gần bằng khách mới."""
    d = q[q["gross_pttb"].fillna(0) >= 10].sort_values("kh_roi_mang")
    f = go.Figure()
    f.add_bar(y=d["ten"].map(_ten_ngan), x=d["gross_pttb"], name="Khách mới (Gross PTTB)", orientation="h", marker_color=ch.XANH)
    f.add_bar(y=d["ten"].map(_ten_ngan), x=d["kh_roi_mang"], name="Khách rời mạng", orientation="h", marker_color=ch.CAM)
    f.update_layout(barmode="group")
    f.update_yaxes(automargin=True)
    return card([ch.khung(f, max(360, 34 * len(d) + 90))], title="Khách mới và khách rời mạng theo phường",
                desc="Phường có từ 10 khách mới trở lên. Thanh cam dài sát thanh xanh nghĩa là mất gần bằng số khách mới.")


def _net_theo_phuong(q):
    """Net PTTB (khách mới trừ khách rời): xanh lá là tăng, đỏ là giảm ròng."""
    d = q[q["gross_pttb"].fillna(0) >= 10].sort_values("net_pttb")
    f = go.Figure(go.Bar(y=d["ten"].map(_ten_ngan), x=d["net_pttb"], orientation="h", marker_color=[ch.LUC if v >= 0 else ch.DO for v in d["net_pttb"]],
                         text=[ch.so(v) for v in d["net_pttb"]], textposition="outside", cliponaxis=False))
    f.update_xaxes(zeroline=True, zerolinecolor="#9AA7B8")
    f.update_yaxes(automargin=True)
    return card([ch.khung(f, max(360, 34 * len(d) + 90), legend=False)], title="Net PTTB theo phường",
                desc="Khách mới trừ khách rời mạng. Thanh đỏ là phường đang mất khách ròng, cần ưu tiên chăm sóc.")


def _goc_phan_tu(q):
    """Mỗi chấm một phường: ngang = tỷ lệ rời / khách đang hoạt động, dọc = rời so với khách mới. Chỉ ghi tên phường ở góc xấu."""
    d = q.dropna(subset=["ty_le_roi_active", "ty_le_roi_gross"])
    d = d[d["gross_pttb"].fillna(0) >= 10]
    mx, my = float(d["ty_le_roi_active"].median()), float(d["ty_le_roi_gross"].median())
    xau = (d["ty_le_roi_active"] >= mx) & (d["ty_le_roi_gross"] >= my)
    ghi = xau & d["ty_le_roi_gross"].rank(ascending=False, method="first").le(6)          # chỉ ghi tên 6 phường xấu nhất, còn lại rê chuột để xem
    f = go.Figure()
    f.add_shape(type="rect", x0=mx, x1=float(d["ty_le_roi_active"].max()) * 1.1, y0=my, y1=float(d["ty_le_roi_gross"].max()) * 1.1, fillcolor="rgba(217,45,32,.06)", line={"width": 0}, layer="below")
    f.add_scatter(x=d["ty_le_roi_active"], y=d["ty_le_roi_gross"], mode="markers",
                  marker={"size": 12, "color": [ch.DO if v else ch.XANH for v in xau], "opacity": .85, "line": {"width": 1, "color": "#fff"}},
                  customdata=d["ten"].map(_ten_ngan), hovertemplate="%{customdata}<br>Rời / Active: %{x:.2f}%<br>Rời / khách mới: %{y:.0f}%<extra></extra>")
    chu = d[ghi]
    ve.ghi_ten(f, chu["ty_le_roi_active"], chu["ty_le_roi_gross"], chu["ten"].map(_ten_ngan))
    f.add_vline(x=mx, line_dash="dot", line_color=ch.XAM)
    f.add_hline(y=my, line_dash="dot", line_color=ch.XAM)
    f.update_xaxes(title="% rời mạng / KH đang hoạt động", ticksuffix="%", gridcolor="#EDF1F6")
    f.update_yaxes(title="Rời mạng so với khách mới", ticksuffix="%")
    return card([ch.khung(f, 400, legend=False)], title="Phường nào đáng lo",
                desc="Vùng đỏ nhạt (phải, trên) là phường vừa mất nhiều khách trên quy mô vừa mất gần bằng khách mới. Vạch nét đứt là mức giữa các phường.")


def _nhiet_phuong():
    ten, cot, chuan, raw = kt.ma_tran_phuong(sl.diem_nong_phuong(sl.sr_bi_dong(), sl.sr_chu_dong()))
    if not ten:
        return None
    return card([ve.ban_do_nhiet(ten, cot, chuan, raw)], title="Bản đồ nhiệt các phường",
                desc="Ghép SR bị động, SR chủ động, rời mạng và công nợ. Mỗi cột tô từ xanh (tốt nhất) đến đỏ (xấu nhất) trong chính cột đó; phường đỏ ở nhiều cột là điểm nóng.")


def _cau_thanh_phong(phong):
    """Cấu thành khách rời mạng của DNG1 và DNG2 cạnh nhau (số khách theo từng nguyên nhân)."""
    p = phong[phong["ten"].isin(["DNG-01", "DNG-02"])].copy()
    if p.empty:
        return None
    cot = {"huy_ssd": "Hủy SSD", "ctbdv_du_kien": "CTBDV dự kiến", "cho_thanh_ly": "Chờ thanh lý", "ctbdv": "CTBDV"}
    ct = p.set_index(p["ten"].map(TEN_PHONG))[[c for c in cot if c in p]].rename(columns=cot).fillna(0)
    ct = ct.loc[:, ct.sum() > 0]
    return card([ve.xep_chong(ct, {"Hủy SSD": ch.CAM, "CTBDV dự kiến": ve.VANG, "Chờ thanh lý": ch.DO, "CTBDV": ch.TIM}, cao=220)], title="Khách rời mạng do đâu, DNG1 và DNG2",
                desc="Số khách theo từng nhóm: hủy sau sử dụng, chờ thanh lý, CTBDV (chấm dứt bất đắc dĩ vì nợ cước) dự kiến.")


def _kpi_roi_mang(r, t):
    gh = (lambda c: f"Ngày chốt trước ({t['ngay_chot']:%d/%m}): {ch.so(t[c])}") if t is not None else (lambda c: "")
    return ch.hang_kpi([
        ("KH rời mạng", ch.so(r["kh_roi_mang"]), gh("kh_roi_mang") or f"Hủy SSD {ch.so(r['huy_ssd'])} · CTBDV dự kiến {ch.so(r['ctbdv_du_kien'])}", ""),
        ("Rời mạng / KH Active", ch.pct(r["ty_le_roi_active"], 2), f"Trên {ch.so(r['kh_active'])} khách đang hoạt động", ch.muc_theo_nguong(r["ty_le_roi_active"], 0.3, 0.6)),
        ("Rời mạng / Gross PTTB", ch.pct(r["ty_le_roi_gross"], 1), f"Cứ 100 khách mới mất {ch.so(r['ty_le_roi_gross'])} khách cũ", ch.muc_theo_nguong(r["ty_le_roi_gross"], 30, 50)),
        ("Net PTTB", ch.so(r["net_pttb"]), f"Gross PTTB {ch.so(r['gross_pttb'])}", ""),
        ("Tỷ lệ giữ lại", ch.pct(r["ty_le_giu"], 2), "", ""),
        ("Tăng trưởng khách", ch.pct(r["ty_le_tang"], 2), f"KH đầu kỳ {ch.so(r['kh_dau_ky'])}", "")])


def _xu_huong_roi_mang(rm_all):
    ls = rm_all[(rm_all["cap"] == "phong") & (rm_all["ten"] == "05.Da Nang")].sort_values("ngay_chot")
    if len(ls) < 2:
        return card([html.Div("Mới có một lần chốt rời mạng nên chưa vẽ được xu hướng. Mỗi lần nạp file ở một ngày chốt khác, đường này dài thêm một điểm.", className="desc")],
                    title="Xu hướng qua các ngày chốt")
    f = go.Figure(go.Scatter(x=ls["ngay_chot"], y=ls["ty_le_roi_active"], mode="lines+markers", line={"color": ch.XANH}))
    f.update_yaxes(ticksuffix="%")
    return card([ch.khung(f, 260, legend=False)], title="Xu hướng qua các ngày chốt", desc="Tỷ lệ rời mạng / KH Active, cả Đà Nẵng")


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
        truoc = rm_all[(rm_all["ngay_chot"] < pd.Timestamp(ngay)) & (rm_all["cap"] == "phong") & (rm_all["ten"] == "05.Da Nang")].sort_values("ngay_chot")
        phong["ten_hien"] = phong["ten"].map(TEN_PHONG).fillna(phong["ten"])
        q = _quan(rm)
        khoang = html.Div(style={"height": "16px"})
        phan_phuong = []
        if len(q):
            nhiet = _nhiet_phuong()
            phan_phuong = [html.Div("Theo phường / xã", className="dv-tieu-nhom"),
                           html.Div([_gross_va_roi(q), _net_theo_phuong(q)], className="dv-hai-cot"), khoang,
                           html.Div([_goc_phan_tu(q), *([nhiet] if nhiet is not None else [])], className="dv-hai-cot"), khoang,
                           card([ch.bang_df("dvrm-quan", q, _cot("ten", "Phường / xã"), 460)], title="Bảng theo phường / xã", desc="Sắp xếp được theo từng cột")]
        cau = _cau_thanh_phong(phong)
        return html.Div([_kpi_roi_mang(tong.iloc[0], truoc.iloc[-1] if len(truoc) else None),
                         html.Div([card([_bieu_do_dong(tong.iloc[0])], title="Cấu thành khách rời mạng", desc="Hủy SSD + CTBDV + chờ thanh lý, trừ khách khôi phục"),
                                   *([cau] if cau is not None else []), ], className="dv-hai-cot"), khoang,
                         card([ch.bang_df("dvrm-phong", phong, _cot("ten_hien", "Phòng"))], title="Theo phòng", desc="DNG1 và DNG2 (DNG-01, DNG-02 trong file)"),
                         *phan_phuong, html.Div("Xu hướng", className="dv-tieu-nhom"), _xu_huong_roi_mang(rm_all)])
