"""Thành phần giao diện dùng chung của các trang khối DVKH: thanh lọc, hàng KPI, biểu đồ, bảng, thẻ nhận định.

Giao diện giữ đúng kiểu khối Kinh doanh (thẻ, KPI, bảng ag-grid, màu FPT); chỉ thêm vài lớp CSS `dv-*` ở cuối assets/style.css.
"""
from __future__ import annotations

import math
from datetime import date

import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html

from app.dvkh import so_lieu as sl
from app.ui.components import card, kpi, seg_control, so_vn, tip
from app.ui.icons import icon
from app.ui.luoi import SO, bang

XANH, CAM, LUC, XAM, DO, TIM, XANH_NHAT = "#0072BC", "#F37021", "#00A650", "#9AA7B8", "#D92D20", "#8C6FD1", "#37A5E6"
DAY_MAU = [XANH, CAM, LUC, TIM, XANH_NHAT, XAM]
PHONG = [("all", "Cả Đà Nẵng"), ("DNG1", "DNG1"), ("DNG2", "DNG2")]
MUC_CSS = {"Nghiêm trọng": "bad", "Cần chú ý": "warn", "Thông tin": "info", "Tốt": "ok"}


def phong_ma(v) -> str | None:
    return None if v in (None, "all") else v


def thanh_loc(prefix: str, *, ngay: date | None = None, ngay_min: date | None = None, ngay_max: date | None = None, phong: str = "all",
              khoang: bool = False, them=None):
    """Thanh lọc dính đầu trang: phạm vi phòng và (tuỳ chọn) một ngày hoặc khoảng ngày."""
    cac = [html.Div([html.Label("Phạm vi"), seg_control(f"{prefix}-phong", PHONG, phong)], className="field")]
    if khoang:
        cac.append(html.Div([html.Label("Khoảng ngày"), dcc.DatePickerRange(
            id=f"{prefix}-ngay", display_format="DD/MM/YYYY", start_date=ngay_min, end_date=ngay_max, min_date_allowed=ngay_min,
            max_date_allowed=ngay_max, minimum_nights=0, className="dv-ngay")], className="field"))
    elif ngay is not None:
        cac.append(html.Div([html.Label("Ngày xem"), dcc.DatePickerSingle(
            id=f"{prefix}-ngay", date=ngay, display_format="DD/MM/YYYY", min_date_allowed=ngay_min, max_date_allowed=ngay_max,
            className="dv-ngay")], className="field"))
    cac.append(html.Div(className="grow"))
    if them is not None:
        cac.extend(them if isinstance(them, list) else [them])
    return html.Div(cac, className="toolbar loc-trang")


def thanh_cap_nhat() -> html.Div:
    """Mỗi nguồn dữ liệu tới ngày nào - người xem biết số có cũ không."""
    nd = sl.ngay_du_lieu()

    def mot(ten, d):
        return html.Span([html.Span(ten, className="dv-nguon"), html.Span(d.strftime("%d/%m") if d else "chưa có", className="dv-ngay-nguon")],
                         className="dv-chip")
    return html.Div([mot("SR bị động tới", nd["sr_bd"]), mot("SR chủ động tới", nd["sr_cd"]), mot("Rời mạng chốt", nd["roi_mang"]),
                     mot("Công nợ tới", nd["cong_no"])], className="dv-cap-nhat")


def thanh_du_lieu() -> list:
    """Dòng tình trạng dữ liệu trên thanh tiêu đề khi đang ở khối DVKH."""
    nd = sl.ngay_du_lieu()
    if not nd["nap"]:
        return [html.Span("Chưa có dữ liệu DVKH", className="badge warn thanh-dl")]
    sr = [d for d in (nd["sr_bd"], nd["sr_cd"]) if d]
    chi_tiet = f"SR bị động tới {nd['sr_bd']:%d/%m}, SR chủ động tới {nd['sr_cd']:%d/%m}, rời mạng chốt {nd['roi_mang']:%d/%m}, công nợ tới {nd['cong_no']:%d/%m}"
    return [html.Span([icon("database", 13), html.Span(f"Cập nhật {nd['nap']:%d/%m} · SR tới {max(sr):%d/%m}" if sr else f"Cập nhật {nd['nap']:%d/%m}")],
                      className="badge muted thanh-dl", title=chi_tiet)]


def chua_co_du_lieu(duoc_nap: bool) -> html.Div:
    nut = (html.A([icon("upload", 14), html.Span("Cập nhật file Excel")], href="/dvkh/nap", className="btn primary") if duoc_nap
           else html.Div("Liên hệ người phụ trách khối DVKH để cập nhật file.", className="desc"))
    return card([html.Div("Khối DVKH chưa có số liệu. Cập nhật file Excel báo cáo DVKH để xem các bảng và nhận định.", className="desc"), nut],
                title="Chưa có số liệu DVKH")


def hang_kpi(ds: list[tuple]) -> html.Div:
    """ds: (nhãn, giá trị, ghi chú, mức) với mức '' / ok / warn / bad."""
    return html.Div([kpi(*d) for d in ds], className="kpi-row")


def so(v, nd: int = 0) -> str:
    return so_vn(v, nd)


def pct(v, nd: int = 1) -> str:
    return "–" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{so_vn(v, nd)}%"


def vnd(v) -> str:
    """Tiền đầy đủ, dễ đọc: 2.845.123.456 đ (không rút gọn thành triệu)."""
    return "–" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{so_vn(v, 0)} đ"


def muc_theo_nguong(v, tot, xau, cao_xau: bool = True) -> str:
    """Màu KPI: xanh khi đạt ngưỡng tốt, đỏ khi vượt ngưỡng xấu, giữa là vàng. cao_xau=False: số càng thấp càng xấu."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    if cao_xau:
        return "ok" if v <= tot else ("bad" if v >= xau else "warn")
    return "ok" if v >= tot else ("bad" if v <= xau else "warn")


# ----------------------------------------------------------------------------- biểu đồ
def khung(fig: go.Figure, cao: int = 320, legend: bool = True, ten_truc_y: str | None = None) -> dcc.Graph:
    fig.update_layout(height=cao, margin={"l": 44, "r": 16, "t": 16, "b": 36}, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      font={"family": "Inter, sans-serif", "size": 12, "color": "#44546A"}, colorway=DAY_MAU, showlegend=legend,
                      legend={"orientation": "h", "y": -0.18, "x": 0, "font": {"size": 11}}, hoverlabel={"font_size": 12},
                      yaxis_title=ten_truc_y)
    fig.update_xaxes(showgrid=False, linecolor="#D8DFE8")
    fig.update_yaxes(gridcolor="#EDF1F6", zeroline=False)
    return dcc.Graph(figure=fig, config={"displayModeBar": False}, style={"width": "100%"})


def cot_ngang(df: pd.DataFrame, nhan: str, gia_tri: str, cao: int = 300, mau: str = XANH, hau_to: str = "", top: int = 12,
              mau_cot: list | None = None, chu: str | None = None) -> dcc.Graph:
    d = df.head(top).iloc[::-1]
    f = go.Figure(go.Bar(y=d[nhan].astype(str).str.slice(0, 46), x=d[gia_tri], orientation="h", marker_color=mau_cot or mau,
                         text=[so_vn(v, 0) + hau_to if chu is None else chu.format(v) for v in d[gia_tri]], textposition="outside",
                         cliponaxis=False, hovertemplate="%{y}: %{x:,.0f}<extra></extra>"))
    f.update_xaxes(showgrid=True, gridcolor="#EDF1F6", visible=False)
    f.update_yaxes(showgrid=False)
    return khung(f, cao, legend=False)


def bang_df(gid: str, df: pd.DataFrame, cot: list[dict], cao: int | None = None, **kw):
    g = bang(gid, cot, cao, **kw)
    g.rowData = [{k: (None if (isinstance(v, float) and math.isnan(v)) else (v.isoformat() if isinstance(v, (pd.Timestamp, date)) else v))
                  for k, v in r.items()} for r in df.to_dict("records")]
    return g


def cot_so(field: str, ten: str, rong: int = 100, **kw) -> dict:
    return {"field": field, "headerName": ten, "width": rong, "type": "numericColumn", "valueFormatter": SO, **kw}


PCT_MOT = {"function": "params.value == null ? '–' : Number(params.value).toLocaleString('vi-VN', {maximumFractionDigits: 1}) + '%'"}


def cot_pct(field: str, ten: str, rong: int = 100, **kw) -> dict:
    return {"field": field, "headerName": ten, "width": rong, "type": "numericColumn", "valueFormatter": PCT_MOT, **kw}


SO_1 = {"function": "params.value == null ? '–' : Number(params.value).toLocaleString('vi-VN', {maximumFractionDigits: 1})"}


def cot_so1(field: str, ten: str, rong: int = 100, **kw) -> dict:
    return {"field": field, "headerName": ten, "width": rong, "type": "numericColumn", "valueFormatter": SO_1, **kw}


def cot_chu(field: str, ten: str, rong: int | None = None, **kw) -> dict:
    return {"field": field, "headerName": ten, **({"width": rong} if rong else {"flex": 1, "minWidth": 140}), **kw}


# ----------------------------------------------------------------------------- bảng KPI nhỏ và thẻ nhận định
def bang_kpi(tieu_de: str, mo_ta: str, cot: list[str], dong: list[tuple]) -> html.Div:
    """Một nhóm KPI dạng bảng nhỏ: mỗi dòng (tên chỉ số, [giá trị theo cột], ghi chú). Ô None hiện '–'."""
    head = html.Tr([html.Th("Chỉ số")] + [html.Th(c) for c in cot] + [html.Th("")])
    rows = []
    for ten, vals, ghi in dong:
        rows.append(html.Tr([html.Td(ten, className="dv-ten")] + [html.Td(v if v not in (None, "") else "–") for v in vals] +
                            [html.Td(tip(ghi) if ghi else "")]))
    return card([html.Table([html.Thead(head), html.Tbody(rows)], className="dv-kpi-bang")], title=tieu_de, desc=mo_ta)


def the_nhan_dinh(x: dict) -> html.Div:
    return html.Div([
        html.Div([html.Span(x["muc"], className="dv-muc"), html.Span(x["chu_de"], className="dv-chu-de")], className="dv-nd-dau"),
        html.Div(x["tieu_de"], className="dv-nd-tieu-de"),
        html.Div(x["noi_dung"], className="dv-nd-noi-dung"),
        html.Div([html.B("Gợi ý: "), x["goi_y"]], className="dv-nd-goi-y") if x.get("goi_y") else None,
    ], className=f"dv-nd {MUC_CSS.get(x['muc'], 'info')}")


def danh_sach_nhan_dinh(ds: list[dict], toi_da: int | None = None) -> html.Div:
    ds = ds[:toi_da] if toi_da else ds
    return html.Div([the_nhan_dinh(x) for x in ds] or [html.Div("Chưa có nhận định nào cho phạm vi này.", className="desc")], className="dv-nd-luoi")


def tab_nho(id_: str, tabs: list[tuple[str, str]], value: str):
    return html.Div(seg_control(id_, tabs, value), className="tab-lon")


def toi_da(v, gioi_han: float):
    return min(v, gioi_han) if v == v else v
