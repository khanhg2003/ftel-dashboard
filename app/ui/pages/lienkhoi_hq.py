"""Tab "Hiệu quả" của trang Điều hành liên khối (nhánh thi-lien-khoi): số đo cho người quản lý về việc đã giao qua Zalo.
Số đo và nhận định ở `app/lien_khoi/hieu_qua.py` (luật cố định, không AI). Phần lịch sử mô phỏng của bản minh hoạ luôn được ghi rõ là mô phỏng.
Chỉ Quản trị; mọi callback kiểm quyền ở máy chủ."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from dash import Input, Output, State, dcc, html
from dash.exceptions import PreventUpdate

from app.lien_khoi import hieu_qua as hq
from app.lien_khoi import theo_doi as td
from app.ui.components import alert, callback_can_quyen, card, chu_giai, kpi, seg_control
from app.ui.luoi import PCT_GACH, SO_1, bang

QUYEN = "duoc_cau_hinh"
KY = [("7", "7 ngày"), ("14", "14 ngày"), ("30", "30 ngày"), ("all", "Tất cả")]
XANH, CAM, XAM = "#0072BC", "#F37021", "#B8C4D2"
MAU_TY_LE = {"styleConditions": [{"condition": "params.value != null && params.value < 50", "style": {"color": "#b42318", "fontWeight": 600}},
                                 {"condition": "params.value != null && params.value < 70", "style": {"color": "#b54708", "fontWeight": 600}},
                                 {"condition": "params.value != null && params.value >= 85", "style": {"color": "#0a5b31", "fontWeight": 600}}]}
COT_TH = [
    {"headerName": "Nhóm", "field": "nhom", "minWidth": 150, "pinned": "left"},
    {"headerName": "Số việc", "field": "giao", "width": 95, "type": "numericColumn"},
    {"headerName": "Xong", "field": "xong", "width": 90, "type": "numericColumn"},
    {"headerName": "Xong đúng hạn", "field": "dung_han", "width": 130, "type": "numericColumn"},
    {"headerName": "Đã tới hạn", "field": "den_han", "width": 115, "type": "numericColumn"},
    {"headerName": "Tỷ lệ đúng hạn", "field": "ty_le", "width": 130, "type": "numericColumn", "valueFormatter": PCT_GACH,
     "cellClass": "ag-right-aligned-cell", "cellStyle": MAU_TY_LE},
    {"headerName": "Giờ xử lý (trung vị)", "field": "gio_xu_ly", "width": 150, "type": "numericColumn", "valueFormatter": SO_1},
    {"headerName": "Quá hạn đang mở", "field": "qua_han_mo", "width": 140, "type": "numericColumn"},
    {"headerName": "Không làm được", "field": "khong", "width": 135, "type": "numericColumn"},
    {"headerName": "Đã báo quản lý", "field": "da_bao_ql", "width": 130, "type": "numericColumn"},
]
CACH_TINH = [("Đã tới hạn", "Việc đã xong, không làm được, hoặc còn mở mà quá hạn. Việc còn trong hạn chưa tính vì chưa biết kết quả."),
             ("Xong đúng hạn", "Đã xong và báo xong không muộn hơn hạn (24 giờ kể từ lúc giao). Không làm được tính là chưa đạt."),
             ("Tỷ lệ đúng hạn", "Xong đúng hạn chia cho đã tới hạn. Nhóm dưới 4 việc đã tới hạn không có tỷ lệ (ít dữ liệu)."),
             ("Thời gian xử lý", "Từ lúc giao tới lúc báo xong, chỉ tính việc đã xong. Dùng trung vị để vài việc rất lâu không làm lệch số."),
             ("Phản hồi", "Từ lúc giao tới lần đầu người nhận làm gì đó với phần việc (nhận, xong hoặc không làm được)."),
             ("Việc hết dấu hiệu", "Luật tự đóng vì không còn thấy dấu hiệu: không tính vào số đo.")]


def _so(x, n: int = 1) -> str:
    return "–" if x is None else f"{x:.{n}f}".replace(".", ",")


def _nen(fig: go.Figure, cao: int = 320) -> go.Figure:
    fig.update_layout(height=cao, margin=dict(l=44, r=44, t=36, b=40), paper_bgcolor="white", plot_bgcolor="white",
                      font=dict(family="Inter, sans-serif", size=12, color="#33455A"), legend=dict(orientation="h", y=1.14, x=0), bargap=0.25)
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#E4E9F0")
    return fig


def hinh_xu_huong(xh: pd.DataFrame) -> go.Figure:
    """Cột việc mới giao và việc xong mỗi ngày; đường tỷ lệ xong đúng hạn của việc giao ngày đó (trục phải)."""
    f = go.Figure()
    if len(xh):
        ngay = xh["ngay"].dt.strftime("%d/%m")
        f.add_bar(x=ngay, y=xh["giao"], name="Việc mới giao", marker_color=XAM)
        f.add_bar(x=ngay, y=xh["xong"], name="Việc hoàn tất", marker_color=XANH)
        f.add_scatter(x=ngay, y=xh["ty_le"], name="Tỷ lệ xong đúng hạn (%)", mode="lines+markers", line=dict(color=CAM, width=2), yaxis="y2", connectgaps=True)
    _nen(f).update_layout(barmode="group", yaxis2=dict(overlaying="y", side="right", range=[0, 100], showgrid=False, ticksuffix="%"))
    return f


def hinh_theo_khoi(th: pd.DataFrame) -> go.Figure:
    f = go.Figure()
    t = th.dropna(subset=["ty_le"]) if len(th) else th
    if len(t):
        f.add_bar(y=t["nhom"], x=t["ty_le"], orientation="h", marker_color=XANH, text=[f"{v:.0f}%" for v in t["ty_le"]], textposition="outside", cliponaxis=False)
    _nen(f, 260).update_layout(xaxis=dict(range=[0, 100], ticksuffix="%"), showlegend=False)
    f.update_yaxes(autorange="reversed")
    return f


def layout():
    an = {"gridTemplateColumns": "repeat(auto-fit, minmax(380px, 1fr))", "display": "grid", "gap": "14px", "marginBottom": "14px"}
    return html.Div([
        dcc.Store(id="lk-hq-tick", data=0),
        html.Div(seg_control("lk-hq-ky", KY, "14"), style={"marginBottom": "12px"}),
        html.Div(id="lk-hq-banner"),
        html.Div(id="lk-hq-kpi", className="kpi-row kpi-6"),
        card([html.Div(id="lk-hq-nhan-dinh")], title="Nhận định", desc="Do luật cố định viết từ số đo bên dưới, không dùng AI."),
        html.Div([card([dcc.Graph(id="lk-hq-xh", config={"displayModeBar": False})], title="Việc giao và xong mỗi ngày", desc="Đường cam: tỷ lệ xong đúng hạn của các việc giao ngày đó."),
                  card([dcc.Graph(id="lk-hq-khoi", config={"displayModeBar": False})], title="Tỷ lệ xong đúng hạn theo khối")], style=an),
        card([bang("lk-hq-luat", COT_TH, cao=None)], title="Theo luật", desc="Luật nào việc hay bị trễ hoặc không làm được. Tỷ lệ thấp nhất xếp trước."),
        card([bang("lk-hq-nguoi", COT_TH, cao=380)], title="Theo người", desc="Để đội trưởng biết ai cần hỗ trợ. Người dưới 4 việc đã tới hạn chưa có tỷ lệ."),
        card([html.Div([dcc.Input(id="lk-hq-moc-gio", type="number", min=0, className="inp", placeholder="Giờ xử lý trước đây", style={"width": "210px"}),
                        dcc.Input(id="lk-hq-moc-ty", type="number", min=0, max=100, className="inp", placeholder="% xong đúng hạn trước đây", style={"width": "230px"}),
                        html.Button("Lưu mốc", id="lk-hq-moc-luu", n_clicks=0, className="btn primary")], className="lk-badges"),
              html.Div(id="lk-hq-moc-kq", style={"marginTop": "10px"})],
             title="So với mốc trước khi dùng hệ thống", desc="Nhập số đo được trước khi dùng (ví dụ lấy từ một tuần làm tay) để thấy mức cải thiện."),
        chu_giai("Cách tính các số đo", CACH_TINH),
    ])


def _du_lieu(ky: str):
    now = td.bay_gio()
    d = td.danh_sach_day_du(now)
    if len(d) and ky != "all":
        d = d[d["tao_luc"] >= pd.Timestamp(now) - pd.Timedelta(days=int(ky))]
    return hq.chuan_bi(d, now) if len(d) else d


def register(app):
    cb = callback_can_quyen(app, QUYEN)

    @cb(Output("lk-hq-banner", "children"), Output("lk-hq-kpi", "children"), Output("lk-hq-nhan-dinh", "children"), Output("lk-hq-xh", "figure"),
        Output("lk-hq-khoi", "figure"), Output("lk-hq-luat", "rowData"), Output("lk-hq-nguoi", "rowData"), Output("lk-hq-moc-kq", "children"),
        Input("lk-tab", "value"), Input("lk-hq-ky", "value"), Input("lk-td-tick", "data"), Input("lk-hq-tick", "data"))
    def _ve(tab, ky, _t1, _t2):
        if tab != "hq":
            raise PreventUpdate
        d = _du_lieu(ky or "14")
        s = hq.so_do(d)
        if not s["giao"]:
            vua = alert("Chưa có phần việc nào trong kỳ này. Ở tab Theo dõi & Zalo bấm \"Chuẩn bị demo\" (nạp 14 ngày mô phỏng) hoặc giao việc rồi quay lại.", "info")
            return vua, [], "", hinh_xu_huong(pd.DataFrame()), hinh_theo_khoi(pd.DataFrame()), [], [], ""
        banner = alert(f"{s['mo_phong']} trên {s['giao']} phần việc trong kỳ là MÔ PHỎNG (14 ngày dựng sẵn để minh hoạ). Số thật sẽ có khi dùng thật.", "warn") if s["mo_phong"] else ""
        ks = [kpi("Xong đúng hạn", "–" if s["ty_le"] is None else f"{_so(s['ty_le'], 0)}%", f"{s['dung_han']} trên {s['den_han']} việc đã tới hạn"),
              kpi("Thời gian xử lý", f"{_so(s['gio_xu_ly'])} giờ", f"Trung vị · trung bình {_so(s['gio_xu_ly_tb'])} giờ"),
              kpi(f"Phản hồi trong {hq.PHAN_HOI_GIO} giờ", "–" if s["phan_hoi_nhanh"] is None else f"{_so(s['phan_hoi_nhanh'], 0)}%", f"Trung vị {_so(s['phan_hoi'])} giờ"),
              kpi("Quá hạn đang mở", s["qua_han_mo"], f"{s['chua_phan_hoi']} việc chưa ai phản hồi", trang_thai="bad" if s["qua_han_mo"] else ""),
              kpi("Đã báo quản lý", s["da_bao_ql"], "Quá 48 giờ chưa xong"), kpi("Không làm được", s["khong"], "Người nhận có ghi lý do")]
        nd = html.Ul([html.Li(c) for c in hq.nhan_dinh(d)], className="lk-nhan-dinh")
        moc = hq.so_voi_moc(s, td.doc_moc())
        moc_kq = html.Ul([html.Li(c) for c in moc]) if moc else html.Div("Chưa nhập mốc.", className="lk-ghi-chu")
        return (banner, ks, nd, hinh_xu_huong(hq.xu_huong(d)), hinh_theo_khoi(hq.tong_hop(d, "vai_tro")),
                hq.tong_hop(d, "ten_luat").to_dict("records"), hq.tong_hop(d, "nguoi").to_dict("records"), moc_kq)

    @cb(Output("lk-hq-moc-gio", "value"), Output("lk-hq-moc-ty", "value"), Input("lk-tab", "value"))
    def _nap_moc(tab):
        if tab != "hq":
            raise PreventUpdate
        m = td.doc_moc()
        return m.get("gio_xu_ly"), m.get("ty_le_dung_han")

    @cb(Output("lk-hq-tick", "data"), Input("lk-hq-moc-luu", "n_clicks"), State("lk-hq-moc-gio", "value"), State("lk-hq-moc-ty", "value"), State("lk-hq-tick", "data"),
        prevent_initial_call=True)
    def _luu_moc(n, gio, ty, tick):
        if not n:
            raise PreventUpdate
        td.ghi_moc(gio if gio else None, ty if ty is not None else None)
        return (tick or 0) + 1
