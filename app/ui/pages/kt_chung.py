"""Thành phần dùng chung của các trang khối Kỹ thuật (nhánh thi-lien-khoi). Biểu đồ, bảng, thẻ KPI dùng lại của khối DVKH (`dvkh_chung.py`)."""
from __future__ import annotations

import pandas as pd
from dash import html

from app.kt import so_lieu as sl
from app.lien_khoi import nguon
from app.ui.components import card, chu_giai
from app.ui.icons import icon
from app.ui.pages import dvkh_chung as ch

STYLE_CANH_BAO = {"styleConditions": [{"condition": "params.value == 'Quá mốc đỏ'", "style": {"color": "#D92D20", "fontWeight": 600}},
                                      {"condition": "params.value == 'Quá mốc xanh'", "style": {"color": "#B54708", "fontWeight": 600}}]}


def thanh_du_lieu() -> list:
    """Dòng tình trạng dữ liệu trên thanh tiêu đề khi đang ở khối Kỹ thuật."""
    if not sl.co_du_lieu():
        return [html.Span("Chưa có dữ liệu Kỹ thuật", className="badge warn thanh-dl")]
    ten = "Minh hoạ" if nguon.la_demo() else "Dữ liệu thật"
    return [html.Span([icon("database", 13), html.Span(f"{ten} · tới {sl.bay_gio():%d/%m}")], className="badge muted thanh-dl", title=sl.nguon_ghi_chu())]


def chua_co_du_lieu() -> html.Div:
    return card([html.Div("Đặt biến môi trường LIEN_KHOI_KT_THU_MUC trỏ tới thư mục chứa các file báo cáo Kỹ thuật (.xlsx: tồn, triển khai đúng hạn, checklist lặp "
                          "30 ngày, checklist sau triển khai, cáp LAN, KPI theo block), rồi tải lại trang. Hoặc chạy bản minh hoạ: LIEN_KHOI_NGUON=demo.", className="desc")],
                title="Khối Kỹ thuật chưa có số liệu")


def ghi_chu_nguon() -> html.Div:
    return html.Div(sl.nguon_ghi_chu(), className="desc")


def cach_hieu() -> html.Div:
    """Giải thích các từ của file Kỹ thuật (gập, mặc định đóng)."""
    return chu_giai("Cách hiểu các số", [
        ("Tồn Kỹ thuật", "Hợp đồng đã tạo phiếu thi công nhưng chưa triển khai xong (file báo cáo chi tiết tồn). Tuổi tồn tính từ lúc tạo phiếu tới ngày dữ liệu."),
        ("Mốc hẹn xanh / đỏ", "Hai mốc giờ hẹn ghi trong file. “Quá mốc” nghĩa là mốc đã qua so với ngày dữ liệu mà hợp đồng vẫn còn tồn."),
        ("Đúng hẹn lần 1 / đúng hẹn", "Lấy từ file KPI theo block: số lần hẹn đúng chia tổng số lần hẹn. Lần 1 là lần hẹn đầu tiên, đúng hẹn chung tính cả hẹn lại."),
        ("Bảo trì quá 24 giờ", "Hợp đồng phải bảo trì sau hơn 24 giờ kể từ lúc lắp xong, trên tổng số lần hẹn."),
        ("Chậm do ai", "Nhãn lấy từ ghi chú của KTV bằng luật từ khoá (khách hẹn lại, nhà chưa xây, thiếu trụ, chờ sale...). Chỉ là gợi ý để trao đổi, không phải kết luận trách nhiệm; ca không ghi chú thì ghi \"Chưa ghi lý do\"."),
        ("Ca im lặng", "Ca tồn mà ghi chú cuối đã quá 24 giờ, hoặc chưa từng có ghi chú dù đã tồn trên 1 ngày."),
        ("Checklist lặp", "Hợp đồng bị lập checklist sự cố từ 2 lần trở lên trong 30 ngày. Số lần lặp lấy từ file, app không tự đếm lại."),
    ])


def bang_ton(t: pd.DataFrame, gid: str, cao: int | None = 420):
    d = t.assign(tao_luc=t["tao_luc"].dt.strftime("%d/%m %H:%M"), hen_xanh=t["hen_xanh"].dt.strftime("%d/%m %H:%M").fillna(""),
                 hen_do=t["hen_do"].dt.strftime("%d/%m %H:%M").fillna(""),
                 canh_bao=["Quá mốc đỏ" if a else ("Quá mốc xanh" if b else "") for a, b in zip(t["qua_do"], t["qua_xanh"])])
    cot = [ch.cot_chu("so_hd", "Mã hợp đồng", 130), ch.cot_chu("nguoi", "KTV", 120), ch.cot_chu("tinh_trang", "Tình trạng", 170),
           ch.cot_chu("loai_trien_khai", "Loại triển khai", 190), ch.cot_chu("tao_luc", "Tạo phiếu", 110), ch.cot_so1("ngay_ton", "Ngày tồn", 90),
           ch.cot_chu("hen_xanh", "Hẹn xanh", 110), ch.cot_chu("hen_do", "Hẹn đỏ", 110),
           {**ch.cot_chu("canh_bao", "Cảnh báo", 120), "cellStyle": STYLE_CANH_BAO}]
    return ch.bang_df(gid, d, cot, cao)
