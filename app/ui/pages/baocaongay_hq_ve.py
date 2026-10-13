"""Thành phần dựng chung cho cửa sổ "Hiệu quả & xu hướng" (tổng quan cả phòng: `baocaongay_hq.py`, chi tiết từng người: `baocaongay_hq_nv.py`).
Chỉ dựng giao diện; mọi con số và nhận định do `app/online_ca_phan_tich.py` tính."""
from __future__ import annotations

from dash import dcc, html
from plotly import graph_objects as go

from app import online_ca_phan_tich as pa

# Bảng màu: kết quả đứng theo thứ tự tốt → xấu, mỗi màu kèm nhãn chữ nên không chỉ dựa vào màu
MAU = {"dung": "#067647", "tre": "#F79009", "chua_len": "#D92D20", "doi": "#667085", "cho": "#B8C4D2", "khong_hen": "#E4E7EC"}
NHAN = {"dung": "Đúng hẹn", "tre": "Trễ", "chua_len": "Chưa lên", "doi": "Dời ngày", "cho": "Chưa tới hạn", "khong_hen": "Không hẹn giờ"}
XANH, XAM, LA, CAM = "#0072BC", "#B8C4D2", "#067647", "#F79009"
CAU = {"displayModeBar": False}


def khoang_chu(tu, den) -> str:
    return f"{tu:%d/%m/%Y}" if tu == den else f"{tu:%d/%m} – {den:%d/%m/%Y}"


def chenh(ty, ty0, tot_khi_giam: bool = False):
    """Chip so sánh điểm phần trăm với khoảng trước (▲ xanh khi tốt lên, ▼ đỏ khi xấu đi); không có số trước thì thôi."""
    if ty is None or ty0 is None or ty == ty0:
        return html.Span("= khoảng trước", className="hq-cl") if ty is not None and ty0 is not None else None
    d = ty - ty0
    tot = d < 0 if tot_khi_giam else d > 0
    return html.Span(f"{'▲' if d > 0 else '▼'} {abs(d)} điểm so với khoảng trước", className="hq-cl " + ("tot" if tot else "xau"))


def the(nhan: str, gia_tri: str, phu: str, cl=None, muc: str = "", tip: str = "") -> html.Div:
    return html.Div([html.Span(nhan, className="hq-the-nhan", title=tip), html.Div(gia_tri, className="hq-the-so"),
                     html.Div(phu, className="hq-the-phu"), cl], className=f"hq-the {muc}".strip())


def luoi_the(cac_the: list) -> html.Div:
    return html.Div(cac_the, className="hq-luoi-the")


def pc(a, b):
    return round(a * 100 / b) if b else None


def thanh_ket_qua(t: dict, tieu: str = "Kết quả các ca theo kế hoạch từng ngày") -> html.Div:
    """Một thanh ngang chia theo kết quả + chú thích số ca từng nhóm."""
    if not t["ca"]:
        return html.Div("Chưa có ca nào trong khoảng này.", className="hq-ghi")
    seg = [html.Div(className="hq-seg", style={"width": f"{t[k] * 100 / t['ca']:.2f}%", "background": MAU[k]}, title=f"{NHAN[k]}: {t[k]} ca")
           for k in pa.KET_QUA if t[k]]
    chu = [html.Span([html.I(style={"background": MAU[k]}), f"{NHAN[k]} ", html.B(t[k])], className="hq-chu-thich") for k in pa.KET_QUA if t[k]]
    return html.Div([html.Div(f"{tieu} · {t['ca']} ca", className="hq-tde"), html.Div(seg, className="hq-thanh"), html.Div(chu, className="hq-chu-ds")], className="hq-khoi")


def nhan_dinh(ds: list[tuple[str, str]]) -> html.Div:
    if not ds:
        return html.Div()
    return html.Div([html.Div("Nhận định", className="hq-tde"),
                     html.Ul([html.Li([html.I(className=f"hq-cham {m}"), html.Span(c)]) for m, c in ds], className="hq-nd")], className="hq-khoi hq-nd-khoi")


def huy_hieu(muc: str, nhan: str) -> html.Span:
    return html.Span(nhan, className=f"hq-hh {muc}")


def _kieu(cao: int = 250) -> dict:
    return dict(margin=dict(l=34, r=10, t=30, b=28), height=cao, plot_bgcolor="#fff", paper_bgcolor="#fff", font=dict(size=12, color="#475467"),
                legend=dict(orientation="h", y=1.2, x=0), xaxis=dict(type="category", showgrid=False), yaxis=dict(gridcolor="#EEF0F3", rangemode="tozero"),
                hoverlabel=dict(font_size=12))


def _do(tieu: str, fig, ghi: str = "") -> html.Div:
    return html.Div([html.Div(tieu, className="hq-tde"), dcc.Graph(figure=fig, config=CAU), html.Div(ghi, className="hq-ghi") if ghi else None], className="hq-khoi")


def _x(ngay: list[dict]) -> list[str]:
    return [r["ngay"].strftime("%d/%m") for r in ngay]


def hinh_online(ngay: list[dict]):
    x = _x(ngay)
    f = go.Figure([go.Bar(x=x, y=[r["dk"] for r in ngay], name="Dự kiến online", marker_color=XAM),
                   go.Bar(x=x, y=[r["onl"] for r in ngay], name="Đã online", marker_color=LA)], layout=dict(barmode="group", **_kieu()))
    return _do("Online: dự kiến và thực tế theo ngày", f)


def hinh_ban(ngay: list[dict]):
    x = _x(ngay)
    f = go.Figure([go.Bar(x=x, y=[r["mt"] for r in ngay], name="Mục tiêu ngày", marker_color=XAM),
                   go.Bar(x=x, y=[r["ban"] for r in ngay], name="Thực hiện", marker_color=XANH)], layout=dict(barmode="group", **_kieu()))
    return _do("Bán so với mục tiêu ngày", f)


def hinh_dung_hen(ngay: list[dict]):
    """Tỷ lệ đúng hẹn theo ngày (đường) và số ca (cột mờ); ngày chưa có ca đến hạn thì để trống đường."""
    x = _x(ngay)
    kieu = _kieu()
    kieu["yaxis2"] = dict(overlaying="y", side="right", range=[0, 100], tickvals=[0, 25, 50, 75, 100], ticksuffix="%", showgrid=False)
    f = go.Figure([go.Bar(x=x, y=[r["ca"] for r in ngay], name="Số ca", marker_color="#E4E7EC"),
                   go.Scatter(x=x, y=[r["ty_le"] for r in ngay], name="Đúng hẹn (%)", yaxis="y2", mode="lines+markers", connectgaps=False,
                              line=dict(color=LA, width=2.5), marker=dict(size=7))], layout=kieu)
    return _do("Tỷ lệ ca lên đúng hẹn theo ngày", f)


def hinh_khung(kh: list[dict]):
    """Mỗi khung giờ HẸN một cột chồng theo kết quả: nhìn là biết khung nào hay lỡ."""
    x = [k["nhan"] for k in kh]
    cot = [go.Bar(x=x, y=[k[m] for k in kh], name=NHAN[m], marker_color=MAU[m]) for m in pa.KET_QUA if any(k[m] for k in kh)]
    f = go.Figure(cot, layout=dict(barmode="stack", **_kieu()))
    return _do("Kết quả theo khung giờ HẸN (khung sale khai lúc tạo ca)", f)


def cac_hinh(*hinh) -> html.Div:
    return html.Div([h for h in hinh if h is not None], className="hq-do")


def ghi_cuoi() -> html.Div:
    return html.Div(["Đúng hẹn: ca đã online khi còn trong hạn khung giờ hẹn. Trễ: online muộn hơn hạn. Chưa lên: quá hạn mà chưa online. Dời ngày: ca đã dời sang ngày khác (một ca dời "
                     "tạo phiếu ở cả hai ngày). Giờ online là giờ sale bấm nút nên có thể muộn hơn giờ thật."], className="hq-ghi")
