"""Trang Hiệu suất CSKH: một dòng mỗi người, gộp SR bị động và SR chủ động; tìm người quá tải, người chậm, người làm tốt."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from dash import Input, Output, dcc, html

from app.dvkh import so_lieu as sl
from app.ui.components import card
from app.ui.pages import dvkh_chung as ch

MIN_TAI = 30                       # dưới mức này tỷ lệ chưa đủ tin cậy nên không gắn nhãn


def topbar():
    return [html.Div([html.H1("Hiệu suất CSKH"), html.Div("Tải việc, tồn, quá hạn, tốc độ phản hồi của từng người (SR bị động + SR chủ động)", className="sub")])]


def layout():
    return html.Div([ch.thanh_loc("dvns"), dcc.Loading(html.Div(id="dvns-noi-dung"), type="dot")])


def gan_nhan(m):
    """Quá tải: tải ≥ P75 và quá hạn ≥ P75. Chậm dù ít việc: tải < trung vị và quá hạn ≥ P75. Làm tốt: tải ≥ trung vị và quá hạn ≤ P25."""
    ok = m["tong_tai"] >= MIN_TAI
    tai, qh = m.loc[ok, "tong_tai"], m.loc[ok, "ty_le_qua_han"]
    if len(tai) < 8:
        m["tin_hieu"] = ""
        return m
    t50, t75, q25, q75 = tai.median(), tai.quantile(.75), qh.quantile(.25), qh.quantile(.75)
    m["tin_hieu"] = np.select([ok & (m["tong_tai"] >= t75) & (m["ty_le_qua_han"] >= q75), ok & (m["tong_tai"] < t50) & (m["ty_le_qua_han"] >= q75),
                               ok & (m["tong_tai"] >= t50) & (m["ty_le_qua_han"] <= q25)], ["Quá tải", "Chậm dù ít việc", "Làm tốt"], "")
    return m


def register(app):
    @app.callback(Output("dvns-noi-dung", "children"), Input("dvns-phong", "value"))
    def _ve(phong):
        bd, cd = sl.loc(sl.sr_bi_dong(), ch.phong_ma(phong)), sl.loc(sl.sr_chu_dong(), ch.phong_ma(phong), cot_ngay="ngay_do")
        m = sl.hieu_suat_nhan_su(bd, cd)
        if m.empty:
            return html.Div("Chưa có số liệu nhân sự.", className="desc")
        m = gan_nhan(m[m["tong_tai"] > 0].copy())
        tb = m["tong_tai"].median()
        td = cd[cd["tu_dong"]]
        kpi_ = ch.hang_kpi([("Số CSKH có việc", ch.so(len(m)), f"Không tính tài khoản máy gọi tự động ({ch.so(len(td))} SR)", ""),
                            ("Tải trung vị", f"{ch.so(tb)} SR", f"Cao nhất {ch.so(m['tong_tai'].max())} ({m.iloc[0]['nhan_su']})", ""),
                            ("Quá hạn trung vị", ch.pct(m["ty_le_qua_han"].median()), "Trên tổng SR được giao", ""),
                            ("Quá tải", ch.so((m["tin_hieu"] == "Quá tải").sum()), "Tải và quá hạn cùng thuộc nhóm cao nhất", "warn" if (m["tin_hieu"] == "Quá tải").any() else "ok"),
                            ("Chậm dù ít việc", ch.so((m["tin_hieu"] == "Chậm dù ít việc").sum()), "Cần hỏi nguyên nhân", "warn" if (m["tin_hieu"] == "Chậm dù ít việc").any() else "ok")])
        d = m[m["tong_tai"] >= MIN_TAI]
        mau = {"Quá tải": ch.DO, "Chậm dù ít việc": ch.CAM, "Làm tốt": ch.LUC, "": ch.XANH_NHAT}
        sc = go.Figure()
        for nhan, g in d.groupby("tin_hieu"):
            sc.add_scatter(x=g["tong_tai"], y=g["ty_le_qua_han"], mode="markers+text", name=nhan or "Bình thường", text=g["nhan_su"], textposition="top center",
                           marker={"size": 10 + g["cd_ton"].clip(0, 200) ** .5 * 2, "color": mau[nhan], "opacity": .8},
                           hovertemplate="%{text}<br>Tải %{x} SR · quá hạn %{y:.1f}%<extra></extra>")
        sc.update_xaxes(title="Tổng SR được giao", showgrid=True, gridcolor="#EDF1F6")
        sc.update_yaxes(title="% quá hạn", ticksuffix="%")
        if len(d):
            sc.add_vline(x=d["tong_tai"].median(), line_dash="dot", line_color=ch.XAM)
            sc.add_hline(y=d["ty_le_qua_han"].median(), line_dash="dot", line_color=ch.XAM)
        cot = [ch.cot_chu("nhan_su", "CSKH", 140, pinned="left"), ch.cot_chu("phong", "Phòng", 80), ch.cot_so("tong_tai", "Tổng SR", 90), ch.cot_so("tong_ton", "Tồn", 80),
               ch.cot_pct("ty_le_qua_han", "% quá hạn", 100), ch.cot_so("bd_phan_cong", "Bị động", 90), ch.cot_pct("bd_ty_le_xu_ly", "BĐ xử lý xong", 120),
               ch.cot_so1("bd_phan_hoi_p50", "BĐ phản hồi (phút)", 140), ch.cot_so("cd_phan_cong", "Chủ động", 100), ch.cot_pct("cd_ty_le_khong_lien_lac", "CĐ không LL", 110),
               ch.cot_so("cd_ton", "CĐ tồn", 80), ch.cot_chu("tin_hieu", "Tín hiệu", 140,
                                                              cellStyle={"styleConditions": [{"condition": "params.value == 'Quá tải'", "style": {"color": "#B42318", "fontWeight": "650"}},
                                                                                             {"condition": "params.value == 'Chậm dù ít việc'", "style": {"color": "#8A5709", "fontWeight": "650"}},
                                                                                             {"condition": "params.value == 'Làm tốt'", "style": {"color": "#0A5B31", "fontWeight": "650"}}]})]
        top = m.sort_values("tong_ton", ascending=False).head(10)
        return html.Div([kpi_,
                         card([ch.khung(sc, 400)], title="Tải việc và quá hạn", desc=f"Chấm lớn là nhiều SR chủ động tồn. Chỉ xét người có từ {MIN_TAI} SR trở lên."),
                         html.Div(style={"height": "16px"}),
                         html.Div([card([ch.cot_ngang(top, "nhan_su", "tong_ton", 340, mau=ch.CAM)], title="Nhiều SR tồn nhất", desc="Bị động + chủ động"),
                                   card([ch.cot_ngang(m.head(10), "nhan_su", "tong_tai", 340)], title="Tải việc cao nhất", desc="Tổng SR được giao")], className="dv-hai-cot"),
                         html.Div(style={"height": "16px"}),
                         card([ch.bang_df("dvns-bang", m, cot, 520)], title="Bảng hiệu suất từng CSKH",
                              desc="BĐ = SR bị động, CĐ = SR chủ động. SR được tính cho Người xử lý, như bảng BC của file.")])
