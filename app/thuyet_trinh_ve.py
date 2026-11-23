"""Biểu đồ cho các slide của "Thuyết trình AI" (`app/thuyet_trinh.py`). Mỗi hàm trả về figure Plotly dạng dict (JSON) để lưu trong Store của trình duyệt.

Màu theo quy ước của app: xanh dương = số của kỳ này, cam = cùng kỳ / mốc so sánh, xanh lá tốt, vàng trung bình, đỏ cần xử lý.
Biểu đồ theo tỉnh dùng lại `phantich_tinh.hinh_tinh`, không dựng lại.
"""
from __future__ import annotations

import json

import plotly.graph_objects as go

XANH, CAM, LA, VANG, DO, XAM = "#0072BC", "#F37021", "#04843F", "#E0A100", "#C8372D", "#8A97A8"
MAU_DANH_GIA = {"An toàn": LA, "Cần tăng tốc": VANG, "Rủi ro": DO}


def _dict(fig: go.Figure, cao: int = 420) -> dict:
    fig.update_layout(template="plotly_white", height=cao, margin={"l": 10, "r": 30, "t": 30, "b": 20}, font={"size": 14},
                      legend={"orientation": "h", "y": 1.1}, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return json.loads(fig.to_json())


def _cao(n: int, moi: int = 34, toi_thieu: int = 300) -> int:
    return max(toi_thieu, 80 + moi * n)


def du_bao_theo_phong(ten: list[str], pct: list[float], danh_gia: list[str]) -> dict:
    """Cột ngang: dự báo cuối tháng đạt bao nhiêu % mục tiêu của từng phòng (xếp thấp -> cao), màu theo đánh giá, vạch 100%."""
    fig = go.Figure(go.Bar(y=ten, x=pct, orientation="h", marker_color=[MAU_DANH_GIA.get(d, XAM) for d in danh_gia],
                           text=[f"{p:.0f}%" for p in pct], textposition="outside", cliponaxis=False,
                           hovertemplate="%{y}: dự báo đạt %{x:.0f}% mục tiêu<extra></extra>"))
    fig.add_vline(x=100, line_dash="dash", line_color=XAM)
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(range=[0, max(pct + [100]) * 1.2], ticksuffix="%")
    return _dict(fig, _cao(len(ten)))


def chenh_cung_ky(ten: list[str], chenh: list[int]) -> dict:
    """Cột ngang: online kỳ này hơn / kém cùng kỳ tháng trước bao nhiêu, theo phòng (xanh lá tăng, đỏ giảm)."""
    fig = go.Figure(go.Bar(y=ten, x=chenh, orientation="h", marker_color=[LA if c >= 0 else DO for c in chenh],
                           text=[f"{c:+d}" for c in chenh], textposition="outside", cliponaxis=False,
                           hovertemplate="%{y}: %{x:+d} online so với cùng kỳ<extra></extra>"))
    fig.update_yaxes(autorange="reversed")
    return _dict(fig, _cao(len(ten)))


def nhip_theo_ngay(ngay: list[int], nay: list[int], truoc: list[int], can_moi_ngay: float | None, nhan_truoc: str) -> dict:
    """Online từng ngày của tháng này (cột) so với cùng ngày tháng trước (đường cam) và mức cần mỗi ngày để kịp mục tiêu (đường đứt)."""
    fig = go.Figure()
    fig.add_bar(x=ngay, y=nay, name="Tháng này", marker_color=XANH, hovertemplate="Ngày %{x}: %{y} online<extra></extra>")
    fig.add_scatter(x=ngay, y=truoc, name=nhan_truoc, mode="lines+markers", line={"color": CAM, "width": 2},
                    hovertemplate="Ngày %{x}: %{y} online (cùng kỳ)<extra></extra>")
    if can_moi_ngay:
        fig.add_hline(y=can_moi_ngay, line_dash="dash", line_color=DO, annotation_text=f"Cần {can_moi_ngay:.0f}/ngày", annotation_position="top left")
    fig.update_xaxes(dtick=1, title="Ngày trong tháng")
    return _dict(fig)


def chat_luong(ten: list[str], vvip: list[float], camera: list[float], chung_vvip: float | None, chung_camera: float | None) -> dict:
    """Cột đôi: tỷ lệ V.VIP và Camera trên online của từng phòng, kèm vạch mức chung của chi nhánh."""
    fig = go.Figure()
    fig.add_bar(x=ten, y=vvip, name="V.VIP", marker_color=XANH, hovertemplate="%{x}: V.VIP %{y:.0f}%<extra></extra>")
    fig.add_bar(x=ten, y=camera, name="Camera", marker_color=CAM, hovertemplate="%{x}: Camera %{y:.0f}%<extra></extra>")
    if chung_vvip is not None:
        fig.add_hline(y=chung_vvip, line_dash="dot", line_color=XANH, annotation_text=f"V.VIP chung {chung_vvip:.0f}%", annotation_position="top left")
    if chung_camera is not None:
        fig.add_hline(y=chung_camera, line_dash="dot", line_color=CAM, annotation_text=f"Camera chung {chung_camera:.0f}%", annotation_position="top right")
    fig.update_layout(barmode="group")
    fig.update_yaxes(ticksuffix="%")
    return _dict(fig)


def ton_lau(ten: list[str], so: list[int]) -> dict:
    """Cột ngang: hợp đồng chờ online từ 7 ngày của từng phòng."""
    fig = go.Figure(go.Bar(y=ten, x=so, orientation="h", marker_color=DO, text=so, textposition="outside", cliponaxis=False,
                           hovertemplate="%{y}: %{x} hợp đồng chờ từ 7 ngày<extra></extra>"))
    fig.update_yaxes(autorange="reversed")
    return _dict(fig, _cao(len(ten)))


def nhan_su_online(ten: list[str], nay: list[int], truoc: list[int]) -> dict:
    """Cột ngang đôi: online luỹ kế của từng nhân sự (xanh) so với cùng kỳ tháng trước (cam), người nhiều online đứng trên."""
    fig = go.Figure()
    fig.add_bar(y=ten, x=nay, name="Kỳ này", orientation="h", marker_color=XANH, text=nay, textposition="outside", cliponaxis=False, hovertemplate="%{y}: %{x} online<extra></extra>")
    fig.add_bar(y=ten, x=truoc, name="Cùng kỳ tháng trước", orientation="h", marker_color=CAM, hovertemplate="%{y}: cùng kỳ %{x} online<extra></extra>")
    fig.update_layout(barmode="group")
    fig.update_yaxes(autorange="reversed")
    return _dict(fig, _cao(len(ten), 44))
