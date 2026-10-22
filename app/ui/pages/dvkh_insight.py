"""Trang Nhận định & phân tích sâu: nhận định tự động từ số liệu và các bảng phân tích chéo giữa SR bị động, SR chủ động, rời mạng, công nợ."""
from __future__ import annotations

from dash import Input, Output, dcc, html

from app.dvkh import cheo, insight, khai_thac as kt, so_lieu as sl
from app.ui.components import card
from app.ui.pages import dvkh_chung as ch, dvkh_ve as ve


def topbar():
    return [html.Div([html.H1("Nhận định & phân tích sâu"), html.Div("Luật cố định đọc số rồi viết thành câu, kèm gợi ý hành động và các bảng phân tích chéo", className="sub")])]


def layout():
    chu_de = [{"label": "Tất cả chủ đề", "value": "all"}] + [{"label": x, "value": x} for x in insight.CHU_DE]
    return html.Div([ch.thanh_loc("dvin", them=[html.Div([html.Label("Chủ đề"), dcc.Dropdown(id="dvin-chu-de", options=chu_de, value="all", clearable=False,
                                                                                            style={"minWidth": "220px"})], className="field")]),
                     dcc.Loading(html.Div(id="dvin-noi-dung"), type="dot")])


def _diem_nong(bd, cd):
    h = sl.diem_nong_phuong(bd, cd)
    if h.empty:
        return card([html.Div("Chưa đủ dữ liệu rời mạng / công nợ theo phường để ghép.", className="desc")], title="Điểm nóng theo phường / xã")
    h = h.assign(ten=h["ten"].map(sl.ten_phuong))
    cot = [ch.cot_chu("ten", "Phường / xã", None, pinned="left"), ch.cot_so("kh_active", "KH Active", 100), ch.cot_so1("sr_bd_1000", "SR bị động / 1.000 KH", 150),
           {"field": "ty_le_roi_active", "headerName": "% rời mạng", "width": 110, "type": "numericColumn",
            "valueFormatter": {"function": "params.value == null ? '–' : Number(params.value).toLocaleString('vi-VN', {minimumFractionDigits: 2, maximumFractionDigits: 2}) + '%'"}},
           ch.cot_pct("ty_le_chua_thu", "% chưa thu nợ", 120), ch.cot_so1("sr_cd_1000", "SR chủ động / 1.000 KH", 160), ch.cot_so("so_chi_so_top3", "Số chỉ số trong top 3 xấu", 190)]
    ten, cot_nhiet, chuan, raw = kt.ma_tran_phuong(h)
    nhiet = card([ve.ban_do_nhiet(ten, cot_nhiet, chuan, raw)], title="Bản đồ nhiệt các phường",
                 desc="Mỗi cột tô từ xanh (tốt nhất) đến đỏ (xấu nhất) trong chính cột đó. Phường đỏ ở nhiều cột là điểm nóng.") if ten else None
    bang = card([ch.bang_df("dvin-nong", h, cot, 420)], title="Điểm nóng theo phường / xã",
                desc="Ghép ba nguồn: SR bị động, rời mạng, công nợ. Phường có từ 500 khách. Top 3 xấu ở nhiều chỉ số cùng lúc là nơi cần kế hoạch riêng.")
    return html.Div([nhiet, html.Div(style={"height": "16px"}), bang]) if nhiet is not None else bang


def _hai_nguon(bd, cd):
    h = cheo.hop_dong_hai_nguon(bd, cd).head(100)
    if h.empty:
        return card([html.Div("Không có hợp đồng nào xuất hiện ở cả hai nguồn.", className="desc")], title="Hợp đồng bị liên hệ từ hai phía")
    cot = [ch.cot_chu("so_hd", "Hợp đồng", 120), ch.cot_chu("phong", "Phòng", 80), ch.cot_chu("quan", "Phường / xã", 150), ch.cot_so("sr_bd", "SR bị động", 100),
           ch.cot_chu("loai_bd", "Loại yêu cầu", None), ch.cot_so("sr_cd", "SR chủ động", 100), ch.cot_chu("ct_cd", "Chương trình chủ động", None),
           ch.cot_so("con_ton", "Còn tồn", 90), ch.cot_so("no_cuoc", "Nợ cước", 90)]
    return card([ch.bang_df("dvin-hai", h, cot, 420)], title="Hợp đồng bị liên hệ từ hai phía",
                desc="Vừa khách gọi vào (SR bị động) vừa DVKH chủ động chăm sóc. Còn tồn nhiều lên đầu, hiện 100 hợp đồng.")


def _thanh_ly(bd, cd):
    t = cheo.thanh_ly_ton(bd, cd)
    if t.empty:
        return card([html.Div("Không còn SR thanh lý nào tồn.", className="desc")], title="Khách đòi thanh lý chưa xử lý xong")
    t["thoi_gian_chu"] = t["thoi_gian"].dt.strftime("%d/%m %H:%M")
    cot = [ch.cot_chu("ma_sr", "Mã SR", 250), ch.cot_chu("so_hd", "Hợp đồng", 110), ch.cot_chu("nguon", "Nguồn", 200), ch.cot_chu("phong", "Phòng", 80),
           ch.cot_chu("quan", "Phường / xã", 150), ch.cot_chu("nguoi_xu_ly", "Người xử lý", 130), ch.cot_chu("tinh_trang", "Tình trạng", 130), ch.cot_chu("thoi_gian_chu", "Lúc", 110)]
    return card([ch.bang_df("dvin-tl", t, cot, 420)], title="Khách đòi thanh lý chưa xử lý xong",
                desc="Cũ nhất lên đầu: gọi trong ngày còn có cơ hội giữ khách.")


def register(app):
    @app.callback(Output("dvin-noi-dung", "children"), Input("dvin-phong", "value"), Input("dvin-chu-de", "value"))
    def _ve(phong, chu_de):
        ma = ch.phong_ma(phong)
        ds = insight.tao_nhan_dinh(ma)
        if chu_de not in (None, "all"):
            ds = [x for x in ds if x["chu_de"] == chu_de]
        bd, cd = sl.loc(sl.sr_bi_dong(), ma), sl.loc(sl.sr_chu_dong(), ma, cot_ngay="ngay_do")
        dem = {m: sum(1 for x in ds if x["muc"] == m) for m in ("Nghiêm trọng", "Cần chú ý", "Thông tin", "Tốt")}
        kpi_ = ch.hang_kpi([("Nghiêm trọng", ch.so(dem["Nghiêm trọng"]), "Cần xử lý ngay", "bad" if dem["Nghiêm trọng"] else "ok"),
                            ("Cần chú ý", ch.so(dem["Cần chú ý"]), "Theo dõi và có kế hoạch", "warn" if dem["Cần chú ý"] else "ok"),
                            ("Thông tin", ch.so(dem["Thông tin"]), "Để hiểu rõ nguyên nhân", ""), ("Tốt", ch.so(dem["Tốt"]), "Đang làm đúng", "ok")])
        return html.Div([kpi_, ch.danh_sach_nhan_dinh(ds), html.Div(style={"height": "20px"}),
                         html.H3("Phân tích chéo", style={"margin": "0 0 10px", "fontSize": "15px"}),
                         _thanh_ly(bd, cd), html.Div(style={"height": "16px"}), _hai_nguon(bd, cd), html.Div(style={"height": "16px"}), _diem_nong(sl.sr_bi_dong(), sl.sr_chu_dong())])
