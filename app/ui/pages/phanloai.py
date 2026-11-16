"""Tab "Phân loại khách hàng": ba báo cáo theo nhóm cần hành động (chăm sóc chủ động, nhắc cước, bán thêm) dựng từ dữ liệu ghép ba khối.
Số liệu ở `app/lien_khoi/phan_loai.py`; ở đây chỉ dựng giao diện. Ai đăng nhập cũng xem được; không có tên khách hàng. Bấm mã hợp đồng để mở hồ sơ."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from dash import Input, Output, State, dcc, html
from dash.exceptions import PreventUpdate

from app.lien_khoi import phan_loai as pl
from app.ui.components import alert, callback_can_quyen, card, chu_giai, kpi, seg_control
from app.ui.luoi import SO, VND, bang
from app.ui.pages.lienkhoi_tq_chart import AMBER, BLUE, GREEN, GREY, RED, base

NHOM = [("rm", "Chăm sóc chủ động"), ("cuoc", "Nhắc cước"), ("ban", "Bán thêm")]
BANG = {"rm": "roi_mang", "cuoc": "nhac_cuoc", "ban": "ban_them"}
MAU_MUC = {"styleConditions": [{"condition": "params.value == 'Cao' || params.value == 'Quá hạn'", "style": {"color": "#b42318", "fontWeight": 600}},
                               {"condition": "params.value == 'Trung bình' || params.value == 'Đến hạn trong 7 ngày'", "style": {"color": "#b54708", "fontWeight": 600}}]}
MA = {"headerName": "Mã hợp đồng", "field": "so_hd", "width": 135, "pinned": "left", "cellClass": "o-bam"}
DAI = {"wrapText": True, "autoHeight": True, "cellStyle": {"lineHeight": "1.5", "padding": "6px 10px"}}
COT = {
    "rm": [MA, {"headerName": "Mức", "field": "muc", "width": 110, "cellStyle": MAU_MUC}, {"headerName": "Điểm ưu tiên", "field": "diem", "width": 105},
           {"headerName": "Điểm nguy cơ (DVKH)", "field": "diem_rm", "width": 120, "valueFormatter": SO},
           {"headerName": "Vì sao", "field": "ly_do", "minWidth": 320, "flex": 2, **DAI}, {"headerName": "Nên làm gì", "field": "de_xuat", "minWidth": 260, "flex": 1, **DAI},
           {"headerName": "DVKH phụ trách", "field": "phu_trach", "width": 150}, {"headerName": "Sale", "field": "sale", "width": 110},
           {"headerName": "Gói", "field": "goi", "width": 100}, {"headerName": "Cước / tháng", "field": "cuoc_thang", "width": 120, "valueFormatter": VND},
           {"headerName": "Số tháng dùng", "field": "tham_nien", "width": 105}, {"headerName": "Đang nợ", "field": "dang_no", "width": 95}],
    "cuoc": [MA, {"headerName": "Nhóm", "field": "nhom", "width": 210, "cellStyle": MAU_MUC}, {"headerName": "Hạn thanh toán", "field": "han_tt", "width": 125},
             {"headerName": "Còn / quá", "field": "con_lai", "width": 130}, {"headerName": "Số tiền", "field": "so_tien", "width": 125, "valueFormatter": VND},
             {"headerName": "Số kỳ chưa trả", "field": "so_ky", "width": 105}, {"headerName": "Kỳ trả trễ (12 tháng)", "field": "ky_tre", "width": 115},
             {"headerName": "Nên làm gì", "field": "de_xuat", "minWidth": 280, "flex": 1, **DAI}, {"headerName": "Hình thức thanh toán", "field": "hinh_thuc_tt", "width": 190},
             {"headerName": "DVKH phụ trách", "field": "phu_trach", "width": 150}, {"headerName": "Sale", "field": "sale", "width": 110}, {"headerName": "Gói", "field": "goi", "width": 100}],
    "ban": [MA, {"headerName": "Ưu tiên", "field": "muc", "width": 110, "cellStyle": MAU_MUC}, {"headerName": "Gợi ý bán thêm", "field": "goi_y", "minWidth": 260, "flex": 1, **DAI},
            {"headerName": "Vì sao phù hợp", "field": "ly_do", "minWidth": 300, "flex": 1, **DAI}, {"headerName": "Nên làm gì", "field": "de_xuat", "minWidth": 260, "flex": 1, **DAI},
            {"headerName": "Đang dùng", "field": "dich_vu", "width": 150}, {"headerName": "Gói", "field": "goi", "width": 100},
            {"headerName": "Cước / tháng", "field": "cuoc_thang", "width": 120, "valueFormatter": VND}, {"headerName": "Số tháng dùng", "field": "tham_nien", "width": 105},
            {"headerName": "Sale", "field": "sale", "width": 110}],
}
MO_TA = {
    "rm": "Hợp đồng đang hoạt động có tín hiệu rời mạng từ ít nhất một khối. Điểm ưu tiên cộng theo luật để xếp thứ tự gọi, không phải xác suất rời mạng.",
    "cuoc": "Kỳ cước chưa thanh toán xếp theo hạn, kỳ kế tiếp dự kiến trong 30 ngày và hợp đồng trong danh sách nợ của DVKH chưa có kỳ cước để đối chiếu.",
    "ban": "Khách đang ổn định: không nợ, không khiếu nại, không sự cố lặp, không thuộc nhóm chăm sóc chủ động. Gợi ý đúng dịch vụ còn thiếu.",
}
CACH_TINH = [
    ("Chăm sóc chủ động", f"Chỉ hợp đồng đang hoạt động. Cộng điểm: điểm nguy cơ DVKH từ 800 (+{pl.DIEM['rm_cao']}) hoặc từ 600 (+{pl.DIEM['rm_vua']}); có ý rời / yêu cầu thanh lý, tạm ngưng "
                          f"(+{pl.DIEM['y_roi']}); mỗi khiếu nại trong 90 ngày (+{pl.DIEM['khieu_nai']}, tối đa {pl.DIEM['khieu_nai_toi_da']}); sự cố kỹ thuật lặp từ 2 lần (+{pl.DIEM['su_co_lap']}); "
                          f"nợ cước (+{pl.DIEM['no_qua_han']}); trả trễ từ 2 kỳ trong 12 tháng (+{pl.DIEM['hay_tra_tre']}). Từ 30 điểm vào nhóm, từ 60 điểm là mức Cao."),
    ("Nhắc cước", "Hạn thanh toán lấy từ nguồn Lịch sử kỳ cước. Quá hạn: kỳ chưa trả có hạn trước ngày tham chiếu. Kỳ kế tiếp dự kiến: mọi kỳ đã trả, kỳ mới bắt đầu ngay sau kỳ cuối. "
                  "Số tiền là tổng các kỳ chưa trả của hợp đồng."),
    ("Bán thêm", "Gợi ý FPT Play / Camera khi hợp đồng chưa có; nâng gói khi đang dùng Giga; chuyển sang trả trước khi đang trả từng tháng và đúng hạn từ 3 kỳ, không kỳ nào trễ. "
                 "Ưu tiên theo số gợi ý, số tháng đã dùng và thói quen thanh toán."),
    ("Ngày tham chiếu", "Mọi phép tính ngày dùng ngày tham chiếu của nguồn dữ liệu, không dùng ngày của máy chủ."),
]


def _so(x) -> str:
    return "–" if x is None or pd.isna(x) else f"{x:,.0f}".replace(",", ".")


def _tien(x) -> str:
    return _so(x) + " đ"


def layout():
    return html.Div([
        dcc.Download(id="pl-tai"),
        html.Div([html.H2("Phân loại khách hàng"), html.P("Ghép Kinh doanh, DVKH và Kỹ thuật theo mã hợp đồng để biết khách nào cần giữ, khách nào tới kỳ cước, khách nào nên mời thêm dịch vụ.")],
                 className="data-intro"),
        html.Div(id="pl-canh-bao"),
        html.Div(id="pl-tong", className="pl-tong"),
        html.Div(seg_control("pl-nhom", NHOM, "rm"), style={"margin": "18px 0 10px"}),
        html.Div(id="pl-mo-ta", className="lk-ghi-chu", style={"marginBottom": "12px"}),
        html.Div(id="pl-kpi", className="kpi-row kpi-6"),
        html.Div([card([html.H3(id="pl-td1"), dcc.Graph(id="pl-hinh1", config={"displaylogo": False})]),
                  card([html.H3(id="pl-td2"), dcc.Graph(id="pl-hinh2", config={"displaylogo": False})])], className="pl-hinh"),
        card([bang("pl-luoi", [], cao=560, tuy_chon={"rowHeight": 52}),
              html.Div([html.Button("Tải báo cáo nhóm này (CSV)", id="pl-xuat", n_clicks=0, className="btn primary")], className="lk-badges", style={"marginTop": "10px"})],
             title="Báo cáo chi tiết", desc="Mỗi dòng một hợp đồng kèm lý do và việc nên làm. Bấm mã hợp đồng để mở hồ sơ ba khối. Bấm tiêu đề cột để sắp xếp."),
        chu_giai("Cách phân loại", CACH_TINH),
    ], className="pl-trang")


def _the_tong(t: dict, s: dict) -> list:
    the = lambda ten, so, phu, lop: html.Div([html.Div(ten, className="tq-kpi-label"), html.Div(so, className="tq-kpi-value"), html.Div(phu, className="tq-kpi-hint")],
                                              className=f"tq-kpi {lop}")
    return [the("CẦN CHĂM SÓC CHỦ ĐỘNG", _so(s["rm"]), f"{s['rm_cao']} mức Cao · trên {t['hoat_dong']} hợp đồng đang hoạt động", "red"),
            the("CẦN NHẮC CƯỚC", _so(s["cuoc"]), f"{s['cuoc_theo_nhom'][pl.NHOM_CUOC[0]]} quá hạn · {s['cuoc_theo_nhom'][pl.NHOM_CUOC[1]]} đến hạn trong 7 ngày", "amber"),
            the("CÓ THỂ BÁN THÊM", _so(s["ban"]), f"{s['ban_cao']} ưu tiên Cao · khách đang ổn định", "green")]


def _cot(nhan: list, gia_tri: list, mau, don_vi: str = "", ngang: bool = True, custom=None, cao: int = 320) -> go.Figure:
    f = go.Figure()
    if len(nhan) and sum(v or 0 for v in gia_tri):
        kw = dict(marker_color=mau, customdata=custom, text=[_so(v) for v in gia_tri], textposition="auto", hovertemplate="%{" + ("y" if ngang else "x") + "}<br>%{text}" + don_vi + "<extra></extra>")
        f.add_bar(x=gia_tri, y=nhan, orientation="h", **kw) if ngang else f.add_bar(x=nhan, y=gia_tri, **kw)
    base(f, cao)
    if ngang:
        f.update_yaxes(autorange="reversed", showgrid=False)
    return f


def _hinh(nhom: str, t: dict, s: dict):
    if nhom == "rm":
        d = t["roi_mang"]
        tin = [("Điểm nguy cơ cao (DVKH)", "Điểm nguy cơ rời mạng"), ("Có ý rời / thanh lý (DVKH)", "ý rời"), ("Khiếu nại (DVKH)", "khiếu nại"),
               ("Sự cố lặp (Kỹ thuật)", "Sự cố kỹ thuật"), ("Nợ cước", "ợ cước"), ("Hay trả trễ", "Trả trễ")]
        dem = [int(d["ly_do"].str.contains(k, regex=False).sum()) if len(d) else 0 for _, k in tin]
        dau = d.head(15)
        return ("Tín hiệu nào đang kéo khách vào nhóm", _cot([a for a, _ in tin], dem, [GREEN, RED, AMBER, BLUE, AMBER, GREY], " hợp đồng"),
                "15 hợp đồng điểm ưu tiên cao nhất", _cot(dau["so_hd"].tolist(), dau["diem"].tolist(), [RED if m == pl.CAO else AMBER for m in dau["muc"]], " điểm", cao=420))
    if nhom == "cuoc":
        lich = t["lich_cuoc"]
        f = _cot([x.strftime("%d/%m") for x in lich["han_tt"]], lich["so_tien"].tolist(), AMBER, " đ", ngang=False, custom=lich["so_hd"].tolist())
        f.update_traces(hovertemplate="%{x}<br>%{text} đ · %{customdata} hợp đồng<extra></extra>")
        return ("Số hợp đồng theo nhóm nhắc cước", _cot(pl.NHOM_CUOC, [s["cuoc_theo_nhom"][n] for n in pl.NHOM_CUOC], [RED, AMBER, GREEN, BLUE, GREY], " hợp đồng"),
                "Tiền cước đến hạn theo ngày, 30 ngày tới", f)
    d = t["ban_them"]
    sale = d["sale"].replace("", "Chưa rõ sale").value_counts().head(10) if len(d) else pd.Series(dtype=int)
    return ("Số hợp đồng theo dịch vụ gợi ý", _cot(pl.GOI_Y, [s["ban_theo_dv"][g] for g in pl.GOI_Y], [GREEN, BLUE, AMBER, GREY], " hợp đồng"),
            "Cơ hội theo sale phụ trách (10 người nhiều nhất)", _cot(sale.index.tolist(), sale.tolist(), GREEN, " hợp đồng", cao=380))


def _kpi(nhom: str, t: dict, s: dict) -> list:
    if nhom == "rm":
        d = t["roi_mang"]
        co = lambda k: int(d["ly_do"].str.contains(k, regex=False).sum()) if len(d) else 0
        return [kpi("Trong nhóm", s["rm"], f"{round(100 * s['rm'] / t['hoat_dong']) if t['hoat_dong'] else 0}% hợp đồng đang hoạt động"),
                kpi("Mức Cao", s["rm_cao"], "Gọi giữ chân trước", trang_thai="bad" if s["rm_cao"] else ""),
                kpi("Cước / tháng đang gặp rủi ro", _tien(s["rm_cuoc"]), "Tổng cước tháng của cả nhóm"),
                kpi("Có ý rời / thanh lý", co("ý rời"), "Tín hiệu từ DVKH"), kpi("Sự cố kỹ thuật lặp", co("Sự cố kỹ thuật"), "Tín hiệu từ Kỹ thuật"),
                kpi("Kèm nợ cước", int((d["dang_no"] == "Có").sum()) if len(d) else 0, "Vừa có tín hiệu rời vừa nợ")]
    if nhom == "cuoc":
        n = s["cuoc_theo_nhom"]
        return [kpi("Quá hạn", n[pl.NHOM_CUOC[0]], _tien(s["cuoc_qua_han_tien"]), trang_thai="bad" if n[pl.NHOM_CUOC[0]] else ""),
                kpi("Đến hạn trong 7 ngày", n[pl.NHOM_CUOC[1]], "Nhắn nhắc trước hạn"), kpi("Đến hạn trong 30 ngày", n[pl.NHOM_CUOC[2]], "Đưa vào lịch nhắc"),
                kpi("Kỳ kế tiếp dự kiến", n[pl.NHOM_CUOC[3]], "Mọi kỳ cũ đã thanh toán"), kpi("Tiền sắp tới hạn", _tien(s["cuoc_sap_toi_tien"]), "Chưa quá hạn, trong 30 ngày tới"),
                kpi("Trong danh sách nợ, chưa có kỳ cước", n[pl.NHOM_CUOC[4]], "Cần đối chiếu với DVKH")]
    v = s["ban_theo_dv"]
    return [kpi("Trong nhóm", s["ban"], "Khách ổn định còn thiếu dịch vụ"), kpi("Ưu tiên Cao", s["ban_cao"], "Nhiều gợi ý, dùng lâu, trả đúng hạn"),
            kpi("Mời FPT Play", v["FPT Play"], "Chưa có FPT Play"), kpi("Mời Camera", v["Camera"], "Chưa có Camera"),
            kpi("Mời nâng gói", v["Nâng gói lên Sky"], "Đang dùng gói Giga"), kpi("Mời trả trước", v["Chuyển sang trả trước"], "Trả từng tháng, luôn đúng hạn")]


def _dong(nhom: str, t: dict) -> list[dict]:
    d = t[BANG[nhom]].copy()
    if nhom == "cuoc" and len(d):
        d["con_lai"] = d["con_ngay"].map(lambda x: "" if x is None or pd.isna(x) else (f"Quá {-int(x)} ngày" if x < 0 else ("Hôm nay" if x == 0 else f"Còn {int(x)} ngày")))
        d["han_tt"] = d["han_tt"].map(lambda x: "" if pd.isna(x) else pd.Timestamp(x).strftime("%d/%m/%Y"))
        d = d.drop(columns="con_ngay")
    return d.astype(object).where(d.notna(), None).to_dict("records")


TEN_COT_XUAT = {"so_hd": "Mã hợp đồng", "muc": "Mức", "diem": "Điểm ưu tiên", "diem_rm": "Điểm nguy cơ DVKH", "ly_do": "Vì sao", "de_xuat": "Nên làm gì", "phu_trach": "DVKH phụ trách",
                "sale": "Sale", "goi": "Gói", "cuoc_thang": "Cước tháng", "tham_nien": "Số tháng dùng", "dang_no": "Đang nợ", "nhom": "Nhóm", "han_tt": "Hạn thanh toán",
                "con_lai": "Còn / quá", "so_tien": "Số tiền", "so_ky": "Số kỳ chưa trả", "ky_tre": "Kỳ trả trễ 12 tháng", "hinh_thuc_tt": "Hình thức thanh toán", "goi_y": "Gợi ý bán thêm",
                "so_goi_y": "Số gợi ý", "dich_vu": "Đang dùng"}


def register(app):
    cb = callback_can_quyen(app, "duoc_cau_hinh")

    @cb(Output("pl-canh-bao", "children"), Output("pl-tong", "children"), Output("pl-mo-ta", "children"), Output("pl-kpi", "children"), Output("pl-td1", "children"),
        Output("pl-hinh1", "figure"), Output("pl-td2", "children"), Output("pl-hinh2", "figure"), Output("pl-luoi", "columnDefs"), Output("pl-luoi", "rowData"),
        Input("lk-tab", "value"), Input("pl-nhom", "value"))
    def _ve(tab, nhom):
        if tab != "pl":
            raise PreventUpdate
        nhom = nhom if nhom in BANG else "rm"
        try:
            t = pl.tong_hop()
        except (FileNotFoundError, KeyError, ValueError):
            rong = _cot([], [], GREEN)
            return alert("Nguồn dữ liệu chưa đầy đủ hoặc sai cấu trúc. Kiểm tra tab Nguồn dữ liệu.", "bad"), [], "", [], "", rong, "", rong, COT[nhom], []
        s = pl.tom_tat(t)
        canh_bao = []
        if t["hom_nay"] is not None:
            canh_bao.append(html.Div(f"Ngày tham chiếu {t['hom_nay']:%d/%m/%Y} · {_so(t['tong'])} hợp đồng, {_so(t['hoat_dong'])} đang hoạt động" + (" · DỮ LIỆU MINH HOẠ" if t["demo"] else ""),
                                     className="lk-ghi-chu", style={"marginBottom": "10px"}))
        if not t["co_nguon_cuoc"]:
            canh_bao.append(alert("Chưa có nguồn Lịch sử kỳ cước: báo cáo Nhắc cước chỉ có danh sách nợ của DVKH, chưa có hạn thanh toán. Nạp nguồn này ở tab Nạp dữ liệu.", "warn"))
        td1, h1, td2, h2 = _hinh(nhom, t, s)
        return canh_bao, _the_tong(t, s), MO_TA[nhom], _kpi(nhom, t, s), td1, h1, td2, h2, COT[nhom], _dong(nhom, t)

    @cb(Output("lk-tab", "value", allow_duplicate=True), Output("lk-hd-ma", "value", allow_duplicate=True), Input("pl-luoi", "cellClicked"), prevent_initial_call=True)
    def _mo_ho_so(cell):
        if not cell or cell.get("colId") != "so_hd" or not cell.get("value"):
            raise PreventUpdate
        return "hd", cell["value"]

    @cb(Output("pl-tai", "data"), Input("pl-xuat", "n_clicks"), State("pl-nhom", "value"), prevent_initial_call=True)
    def _xuat(n, nhom):
        if not n or nhom not in BANG:
            raise PreventUpdate
        t = pl.tong_hop()
        d = pd.DataFrame(_dong(nhom, t))
        d = d.rename(columns=TEN_COT_XUAT) if len(d) else pd.DataFrame(columns=[TEN_COT_XUAT.get(c, c) for c in t[BANG[nhom]].columns])
        ngay = f"{t['hom_nay']:%Y%m%d}" if t["hom_nay"] is not None else "chua_co_ngay"
        return dict(content="﻿" + d.to_csv(index=False), filename=f"phan_loai_{BANG[nhom]}_{ngay}.csv", type="text/csv")
