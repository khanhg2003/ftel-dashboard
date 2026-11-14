"""Trang Sự cố và checklist: checklist lặp 30 ngày (phần tử lỗi, nguyên nhân, hướng xử lý), checklist sau triển khai, cáp LAN."""
from __future__ import annotations

from dash import html

from app.kt import so_lieu as sl
from app.ui.components import card
from app.ui.pages import dvkh_chung as ch, kt_chung as kc


def topbar():
    return [html.Div([html.H1("Sự cố và checklist"), html.Div("Checklist lặp trong 30 ngày, lỗi sau triển khai, cáp LAN", className="sub")])]


def _nhom(ev, khoa: str, tieu_de: str, desc: str = "", loai: str = "checklist"):
    d = sl.nhom_loi(ev, khoa, loai)
    return card([ch.cot_ngang(d, "nhom", "pct", 280, hau_to="%", top=8, chu="{:.1f}%") if len(d) else html.Div("Chưa có dữ liệu.", className="desc")], title=tieu_de, desc=desc or None)


def layout():
    ev = sl.su_kien()
    if ev.empty:
        return kc.chua_co_du_lieu()
    lap, cl = sl.hop_dong_lap(ev), sl.cap_lan(ev)
    cot = [ch.cot_chu("so_hd", "Mã hợp đồng", 130), ch.cot_chu("nguoi", "KTV", 110), ch.cot_so("so_lan", "Số lần lặp", 100), ch.cot_chu("phan_tu_loi", "Phần tử lỗi", 160),
           ch.cot_chu("nguyen_nhan", "Nguyên nhân (cấp 1)"), ch.cot_chu("gan_nhat", "Checklist gần nhất", 150)]
    ds = lap.assign(gan_nhat=lap["gan_nhat"].dt.strftime("%d/%m %H:%M")) if len(lap) else lap
    return html.Div([
        kc.ghi_chu_nguon(),
        ch.hang_kpi([("Hợp đồng có checklist", ch.so(sl.tom_tat(ev, sl.kpi_block(), sl.bay_gio(ev))["hd_checklist"]), "Trong 30 ngày", ""),
                     ("Lặp từ 3 lần", ch.so(len(sl.hop_dong_lap(ev, 3))), "Lỗi chưa dứt điểm", "bad" if len(sl.hop_dong_lap(ev, 3)) else "ok"),
                     ("Checklist sau triển khai", ch.so(int((ev["loai"] == "checklist_sau_tk").sum())), "Lỗi ngay sau khi lắp xong", ""),
                     ("Cáp LAN", ch.pct(cl["pct_lan"]), f"{ch.so(cl['lan'])} LAN · {ch.so(cl['wifi'])} WIFI", "")]),
        html.Div("Sự cố lặp: lỗi ở đâu, vì sao, xử lý thế nào", className="dv-tieu-nhom"),
        html.Div([_nhom(ev, "phan_tu_loi", "Phần tử lỗi", "Tỷ lệ trên số checklist lặp."), _nhom(ev, "trieu_chung", "Triệu chứng đầu vào"),
                  _nhom(ev, "nguyen_nhan_loi", "Nguyên nhân (cấp 1)"), _nhom(ev, "huong_xu_ly", "Hướng xử lý")], className="dv-hai-cot"),
        html.Div("Hợp đồng lặp nhiều lần", className="dv-tieu-nhom"),
        card([ch.bang_df("kt-lap-bang", ds, cot, 360)], desc="Từ 3 lần lặp trước. Các hợp đồng này đã tự vào việc của Điều hành liên khối.") if len(lap) else html.Div("Không có hợp đồng nào lặp.", className="desc"),
        html.Div("Sau triển khai và cáp LAN", className="dv-tieu-nhom"),
        html.Div([_nhom(ev, "phan_tu_loi", "Phần tử lỗi sau triển khai", "Checklist lập ngay sau khi lắp xong.", "checklist_sau_tk"),
                  card([ch.cot_ngang(cl["ly_do"], "nhom", "so", 280, top=6) if len(cl["ly_do"]) else html.Div("Không có hợp đồng kích hoạt bằng WIFI.", className="desc")],
                       title="Vì sao không dùng cáp LAN", desc="Hợp đồng kích hoạt bằng WIFI, theo lý do kỹ thuật viên chọn.")], className="dv-hai-cot"),
        kc.cach_hieu(),
    ])


def register(app):
    return None
