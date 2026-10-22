"""Biểu đồ và thẻ chỉ số dùng chung của các trang DVKH: thẻ có xu hướng, vào - ra - tồn, Sankey, bản đồ nhiệt, đường dự báo, góc phần tư.

Quy ước màu (như khối Kinh doanh): xanh lá = tốt, cam = cần chú ý, đỏ = xấu, xanh dương = số lượng không tốt không xấu.
Mỗi hàm trả `dcc.Graph` (qua `ch.khung`) hoặc một thẻ HTML; không đọc database, chỉ vẽ cái được đưa vào.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import html

from app.dvkh import xu_huong as xh
from app.ui.components import tip
from app.ui.pages import dvkh_chung as ch

XANH_LA_NHAT, DO_NHAT, VANG = "#5CC58B", "#F1A3A3", "#E8A33D"
MAU_NHAN = {"Cần hỗ trợ": ch.DO, "Cần nhắc": ch.CAM, "Làm tốt": ch.LUC, "": "#B8C4D3"}
MAU_TT_CD = {"Đã xử lý xong": ch.LUC, "Hệ thống tự đóng": "#B8C4D3", "Đang xử lý": ch.XANH_NHAT, "Chưa xử lý / chưa phân công": ch.CAM,
             "Không thành công": ch.TIM}
THANG_NHIET = [[0, "#E3F4EA"], [.5, "#FFF1D6"], [1, "#F6B8B0"]]
THU_NGAN = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]


# ----------------------------------------------------------------------------- thẻ chỉ số có xu hướng
def _nhan_xu_huong(h: dict | None, tang_la_tot: bool, don_vi: str = "", cua_so: str = "3 ngày gần nhất so với các ngày trước") -> html.Div:
    if h is None:
        return html.Div("Chưa đủ ngày để thấy xu hướng", className="dv-xh dv-chua-co")
    mui = {"tang": "▲", "giam": "▼", "di_ngang": "▬"}[h["huong"]]
    chu = {"tang": "tăng", "giam": "giảm", "di_ngang": "đi ngang"}[h["huong"]]
    mau = {"tot": "dv-tot", "xau": "dv-xau", "trung_tinh": "dv-chua-co"}[xh.danh_gia_huong(h, tang_la_tot)]
    pc = "" if h["chenh_pct"] is None or h["huong"] == "di_ngang" else f" {ch.so(abs(h['chenh_pct']), 0)}%"
    return html.Div([html.Span(f"{mui} {chu}{pc}", className=f"dv-xh {mau}"), html.Span(cua_so, className="dv-xh-ghi")], className="dv-xh-dong")


def spark(chuoi, mau: str = "") -> html.Div:
    """Dải cột nhỏ (không cần thư viện biểu đồ) cho thấy chuỗi theo ngày; cột cuối đậm."""
    v = [float(x) for x in chuoi if x is not None and not (isinstance(x, float) and math.isnan(x))][-14:]
    if len(v) < 2:
        return html.Div(className="dv-spark")
    hi = max(v) or 1
    return html.Div([html.I(style={"height": f"{max(8, x * 100 / hi):.0f}%"}, className="cuoi" if i == len(v) - 1 else "") for i, x in enumerate(v)],
                    className=f"dv-spark {mau}".strip())


def the_xu_huong(nhan: str, so: str, *, muc: str = "", h: dict | None = None, tang_la_tot: bool = False, ghi: str = "", chuoi=None,
                 giai_thich: str | None = None, cua_so: str = "3 ngày gần nhất so với các ngày trước", xu_huong_html=None) -> html.Div:
    """Thẻ KPI có: số lớn, màu thanh trên theo mức (ok / warn / bad), mũi tên xu hướng tăng / giảm kèm tốt / xấu, dải cột nhỏ theo ngày."""
    return html.Div([html.Div([nhan, tip(giai_thich) if giai_thich else None], className="label"), html.Div(so, className="value"),
                     xu_huong_html if xu_huong_html is not None else _nhan_xu_huong(h, tang_la_tot, cua_so=cua_so), html.Div(ghi, className="hint") if ghi else None,
                     spark(chuoi) if chuoi is not None else None], className=f"kpi dv-the {muc}".strip())


def hang_the(cac: list) -> html.Div:
    return html.Div(cac, className="dv-the-luoi")


# ----------------------------------------------------------------------------- vào - ra - tồn
def vao_ra_ton(luong: pd.DataFrame, ten_vao: str = "SR vào", cao: int = 320):
    """Cột xanh = SR vào, cột xanh lá = SR đã rời hàng chờ; đường cam (trục phải) = tồn cuối ngày. Tồn đi xuống nghĩa là xử lý nhanh hơn việc đổ về."""
    f = go.Figure()
    f.add_bar(x=luong["ngay"], y=luong["vao"], name=ten_vao, marker_color=ch.XANH)
    f.add_bar(x=luong["ngay"], y=luong["ra"], name="Đã rời hàng chờ", marker_color=ch.LUC,
              hovertemplate="%{y} SR đã xử lý xong / tự đóng / chuyển<extra></extra>")
    f.add_scatter(x=luong["ngay"], y=luong["ton_cuoi_ngay"], name="Tồn cuối ngày (trục phải)", yaxis="y2", mode="lines+markers",
                  line={"color": ch.CAM, "width": 2.6}, marker={"size": 6})
    f.update_layout(barmode="group", bargap=.25, yaxis2={"overlaying": "y", "side": "right", "showgrid": False, "rangemode": "tozero"},
                    hovermode="x unified")
    f.update_xaxes(tickformat="%d/%m", dtick=86400000)
    return ch.khung(f, cao)


def theo_thu(tt: pd.DataFrame, cao: int = 240):
    """SR vào trung bình mỗi ngày theo thứ trong tuần; ghi số ngày mẫu để không đọc quá mức khi mới có vài tuần."""
    if tt.empty:
        return None
    tt = tt.set_index("thu").reindex(range(7))
    mau = [ch.XANH if (v == v and v >= np.nanmean(tt["tb"])) else "#9CC9EA" for v in tt["tb"]]
    f = go.Figure(go.Bar(x=THU_NGAN, y=tt["tb"], marker_color=mau, text=[ch.so(v) if v == v else "" for v in tt["tb"]], textposition="outside", cliponaxis=False,
                         customdata=tt["so_ngay"], hovertemplate="%{x}: trung bình %{y:.0f} SR/ngày (%{customdata} ngày mẫu)<extra></extra>"))
    f.update_yaxes(rangemode="tozero")
    return ch.khung(f, cao, legend=False)


# ----------------------------------------------------------------------------- xếp chồng, Sankey, bản đồ nhiệt
def xep_chong(ct: pd.DataFrame, mau: dict | None = None, ngang: bool = True, phan_tram: bool = False, cao: int = 340, hau_to: str = ""):
    """Cột xếp chồng theo từng dòng của bảng chéo (cột = nhóm màu). Dòng đưa vào theo thứ tự muốn thấy từ trên xuống."""
    f = go.Figure()
    d = ct.iloc[::-1] if ngang else ct
    nhan = d.index.strftime("%d/%m") if isinstance(d.index, pd.DatetimeIndex) else d.index.astype(str)       # ngày hiện dd/mm, không để plotly tự hiện tên tháng tiếng Anh
    nguong = 8 if phan_tram else .07 * float(d.sum(axis=1).max() or 1)           # chỉ ghi số lên khúc đủ rộng, khúc nhỏ xem khi rê chuột
    for i, c in enumerate(d.columns):
        mc = (mau or {}).get(c, ch.DAY_MAU[i % len(ch.DAY_MAU)])
        kw = {"y": nhan, "x": d[c], "orientation": "h"} if ngang else {"x": nhan, "y": d[c]}
        f.add_bar(name=str(c), marker_color=mc, text=[(f"{v:.0f}{hau_to}" if v >= nguong else "") for v in d[c]], textposition="inside",
                  hovertemplate="%{y}: %{x:,.0f}" + hau_to + "<extra>" + str(c) + "</extra>" if ngang else "%{x}: %{y:,.0f}" + hau_to + "<extra>" + str(c) + "</extra>", **kw)
    f.update_layout(barmode="stack")
    if ngang:
        f.update_yaxes(automargin=True)
        f.update_xaxes(range=[0, 100] if phan_tram else None, ticksuffix=hau_to)
    return ch.khung(f, cao)


def sankey(g: dict, cao: int = 340):
    """Sankey từ `khai_thac.dong_giu_chan`: nhóm cuối cùng màu đỏ (đã chấm dứt), xanh lá (còn dùng)."""
    mau_nut = [ch.XANH, ch.LUC, VANG, ch.DO, "#B8C4D3", ch.DO, ch.LUC]
    mau_noi = [mau_nut[d] + "55" for d in g["dich"]]
    f = go.Figure(go.Sankey(arrangement="snap", node={"label": g["nhan"], "color": mau_nut, "pad": 18, "thickness": 18, "line": {"width": 0}},
                            link={"source": g["nguon"], "target": g["dich"], "value": g["gia_tri"], "color": mau_noi}))
    return ch.khung(f, cao, legend=False)


def ban_do_nhiet(ten: list[str], cot: list[str], chuan: np.ndarray, raw: np.ndarray, cao: int | None = None, dinh_dang: str = "{:,.1f}"):
    """Hàng = phường / xã, cột = chỉ số. Màu: xanh nhạt (tốt nhất trong cột) tới đỏ nhạt (xấu nhất); chữ là số thật."""
    chu = [[("–" if np.isnan(v) else dinh_dang.format(v)) for v in r] for r in raw]
    f = go.Figure(go.Heatmap(z=chuan, x=cot, y=ten, colorscale=THANG_NHIET, zmin=0, zmax=1, showscale=False, text=chu, texttemplate="%{text}",
                             hovertemplate="%{y} · %{x}: %{text}<extra></extra>", xgap=3, ygap=3))
    f.update_yaxes(autorange="reversed", automargin=True)
    f.update_xaxes(side="top", tickangle=0)
    return ch.khung(f, cao or max(260, 30 * len(ten) + 100), legend=False)


def nhiet_chenh(m: pd.DataFrame, cao: int | None = None):
    """Chênh tỷ lệ thu (điểm %) kỳ này so với kỳ trước, cùng ngày trong tháng. Đỏ = thu chậm hơn, xanh = nhanh hơn."""
    lim = float(np.nanmax(np.abs(m.to_numpy()))) or 1
    f = go.Figure(go.Heatmap(z=m.to_numpy(), x=[f"{int(c)}" for c in m.columns], y=m.index.map(ten_quan), zmid=0, zmin=-lim, zmax=lim,
                             colorscale=[[0, "#E5645A"], [.5, "#FFFFFF"], [1, "#2E9E6B"]], showscale=True, xgap=2, ygap=2,
                             colorbar={"title": "điểm %", "thickness": 10, "len": .8},
                             hovertemplate="%{y}, ngày %{x}: %{z:+.1f} điểm %<extra></extra>"))
    f.update_xaxes(title="Ngày trong tháng")
    f.update_yaxes(autorange="reversed", automargin=True)
    return ch.khung(f, cao or max(260, 28 * len(m) + 90), legend=False)


def ten_quan(t: str) -> str:
    return (str(t).replace("Q.", "Quận ").replace("Huyen ", "Huyện ")).replace("Quận Cam Le", "Quận Cẩm Lệ").replace("Quận Lien Chieu", "Quận Liên Chiểu") \
        .replace("Quận Hai Chau", "Quận Hải Châu").replace("Quận Thanh Khe", "Quận Thanh Khê").replace("Quận Ngu Hanh Son", "Quận Ngũ Hành Sơn") \
        .replace("Quận Son Tra", "Quận Sơn Trà").replace("Huyện Hoa Vang", "Huyện Hòa Vang")


# ----------------------------------------------------------------------------- công nợ có dự báo
def duong_cong_no(cn: pd.DataFrame, ten: str, du_bao: dict | None, cot: str = "ty_le_bill", cao: int = 330, ky_den: str | None = None):
    """Đường thu của kỳ trước (xám, nét chấm), kỳ này (xanh, nét liền) và dự báo phần còn lại (xanh, nét đứt) theo hình dạng kỳ trước."""
    d = cn[(cn["cap"] == "phong") & (cn["ten"] == ten)].dropna(subset=[cot])
    ky = [k for k in sorted(d["ky_no"].unique()) if ky_den is None or k <= ky_den][-2:]
    f = go.Figure()
    for i, k in enumerate(ky):
        x = d[d["ky_no"] == k].sort_values("so_ngay")
        moi = i == len(ky) - 1
        f.add_scatter(x=x["so_ngay"], y=x[cot] * 100, mode="lines+markers", name=f"Hoá đơn tháng {k[-2:]}" + (" (đang thu)" if moi else ""),
                      line={"color": ch.XANH if moi else ch.XAM, "dash": "solid" if moi else "dot", "width": 2.8 if moi else 2}, marker={"size": 5})
    if du_bao:
        x = np.concatenate([[du_bao["so_ngay"]], du_bao["ngay_du_bao"]])
        y = np.concatenate([[du_bao["hien_tai"]], du_bao["duong_du_bao"]]) * 100
        f.add_scatter(x=x, y=y, mode="lines", name="Dự báo theo nhịp tháng trước", line={"color": ch.XANH, "dash": "dash", "width": 2.2})
        f.add_annotation(x=x[-1], y=y[-1], text=f"{ch.pct(y[-1])} dự kiến", showarrow=True, ax=-10, ay=26, font={"size": 11, "color": ch.XANH})
    f.update_xaxes(title="Ngày trong tháng", dtick=2)
    f.update_yaxes(ticksuffix="%", range=[0, 102])
    f.update_layout(hovermode="x unified")
    return ch.khung(f, cao)


# ----------------------------------------------------------------------------- nhân sự
def tai_viec_xep_chong(hs: pd.DataFrame, cao: int | None = None):
    """Mỗi CSKH một thanh: SR xong đúng hạn / xong nhưng quá hạn / chưa xử lý / đang xử lý và đã quá hạn. Nhìn một lần thấy cả tải lẫn chỗ nghẽn."""
    d = hs.sort_values("tong_tai")
    f = go.Figure()
    for cot, ten, mau in (("xong_dung_han", "Xong đúng hạn", ch.LUC), ("xong_qua_han", "Xong nhưng quá hạn", VANG), ("chua_xu_ly", "Chưa xử lý", ch.CAM),
                          ("dang_qua_han", "Đang xử lý, đã quá hạn", ch.DO)):
        f.add_bar(y=d["nhan_su"], x=d[cot], name=ten, orientation="h", marker_color=mau, hovertemplate="%{y}: %{x} SR<extra>" + ten + "</extra>")
    f.update_layout(barmode="stack")
    f.update_yaxes(automargin=True)
    return ch.khung(f, cao or max(320, 21 * len(d) + 90))


def goc_phan_tu(hs: pd.DataFrame, cot_x: str, ten_x: str, cao: int = 420):
    """Chấm là từng CSKH: ngang = mức tải, dọc = % quá hạn. Chỉ ghi tên người cần hỗ trợ và người làm tốt; người còn lại xem khi rê chuột."""
    d = hs.dropna(subset=[cot_x, "ty_le_qua_han"])
    mx, my = float(d[cot_x].median()), float(d["ty_le_qua_han"].median())
    xmax, ymax = float(d[cot_x].max()) * 1.08, float(d["ty_le_qua_han"].max()) * 1.12
    f = go.Figure()
    f.add_shape(type="rect", x0=mx, x1=xmax, y0=my, y1=ymax, fillcolor="rgba(217,45,32,.06)", line={"width": 0}, layer="below")
    f.add_shape(type="rect", x0=mx, x1=xmax, y0=0, y1=my, fillcolor="rgba(0,166,80,.06)", line={"width": 0}, layer="below")
    for nhan, g in d.groupby("nhan"):
        ghi = g["nhan_su"].where(g["nhan"].isin(["Cần hỗ trợ", "Làm tốt"]), "")
        f.add_scatter(x=g[cot_x], y=g["ty_le_qua_han"], mode="markers+text", name=nhan or "Bình thường", text=ghi, textposition="top center", textfont={"size": 11},
                      marker={"size": 11, "color": MAU_NHAN[nhan], "line": {"width": 1, "color": "#fff"}, "opacity": .92},
                      customdata=g[["nhan_su", "tong_tai"]], hovertemplate="%{customdata[0]}<br>" + ten_x + ": %{x:,.0f}<br>Quá hạn: %{y:.1f}% · %{customdata[1]:.0f} SR<extra></extra>")
    f.add_vline(x=mx, line_dash="dot", line_color=ch.XAM)
    f.add_hline(y=my, line_dash="dot", line_color=ch.XAM)
    f.add_annotation(x=xmax, y=ymax, text="Nhiều việc và chậm: cần hỗ trợ", showarrow=False, xanchor="right", yanchor="top", font={"size": 11, "color": ch.DO})
    f.add_annotation(x=xmax, y=0, text="Nhiều việc mà vẫn đúng hạn", showarrow=False, xanchor="right", yanchor="bottom", font={"size": 11, "color": "#04843F"})
    f.update_xaxes(title=ten_x, range=[max(0, float(d[cot_x].min()) * .9), xmax], gridcolor="#EDF1F6")
    f.update_yaxes(title="% SR quá hạn", ticksuffix="%", range=[0, ymax])
    return ch.khung(f, cao)


def hop_theo_phong(hs: pd.DataFrame, cot: str = "ty_le_qua_han", ten: str = "% quá hạn", cao: int = 320):
    """Hộp phân bố của một chỉ số theo phòng: khoảng cách giữa người tốt nhất và kém nhất, và phòng nào đồng đều hơn."""
    f = go.Figure()
    for i, (p, g) in enumerate(hs.dropna(subset=[cot]).groupby("phong")):
        f.add_box(y=g[cot], x=[p] * len(g), name=p, boxpoints="all", jitter=.4, pointpos=0, marker={"color": ch.DAY_MAU[i % 6], "size": 6}, line={"color": ch.DAY_MAU[i % 6]},
                  text=g["nhan_su"], hovertemplate="%{text}: %{y:.1f}%<extra></extra>", boxmean=True)
    f.update_yaxes(title=ten, ticksuffix="%")
    return ch.khung(f, cao, legend=False)
