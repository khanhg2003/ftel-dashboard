"""Trang Tổng quan khối Kỹ thuật: tồn, lịch hẹn, đúng hẹn, bảo trì, sự cố lặp; nhận định bằng luật cố định; nối sang Điều hành liên khối."""
from __future__ import annotations

import plotly.graph_objects as go
from dash import dcc, html

from app.kt import so_lieu as sl
from app.ui.components import card
from app.ui.pages import dvkh_chung as ch, kt_chung as kc


def topbar():
    return [html.Div([html.H1("Tổng quan Kỹ thuật"), html.Div("Tồn · lịch hẹn · đúng hẹn · bảo trì · sự cố lặp", className="sub")])]


def _viec_lien_khoi() -> int | None:
    try:
        from app.lien_khoi import luat
        d = luat.danh_sach_viec()
        return int(d["giao_kt"].fillna("").ne("").sum()) if len(d) else 0
    except Exception:                      # noqa: BLE001 - phần nối liên khối không được làm hỏng trang Kỹ thuật
        return None


def _the_kpi(s: dict):
    pc = ch.pct
    return html.Div([
        ch.hang_kpi([("Hợp đồng tồn", ch.so(s["so_ton"]), f"Tuổi tồn trung bình {ch.so(s['tuoi_tb'], 1)} ngày", ""),
                     (f"Tồn từ {sl.TON_LAU_NGAY} ngày", ch.so(s["ton_lau"]), "Tồn lâu cần hỏi nguyên nhân", ch.muc_theo_nguong(s["ton_lau"], 0, max(3, 0.2 * s["so_ton"]))),
                     ("Quá mốc hẹn đỏ", ch.so(s["qua_do"]), f"{ch.so(s['qua_xanh'])} hợp đồng quá mốc xanh", "bad" if s["qua_do"] else "ok"),
                     ("Checklist lặp", ch.so(s["hd_lap"]), f"{ch.so(s['hd_lap3'])} hợp đồng từ 3 lần", "warn" if s["hd_lap"] else "ok")]),
        ch.hang_kpi([("Đúng hẹn lần 1", pc(s["dung_hen_l1_pct"]), "Theo file KPI các block", ch.muc_theo_nguong(s["dung_hen_l1_pct"], 80, sl.DUNG_HEN_L1_THAP, False)),
                     ("Đúng hẹn chung", pc(s["dung_hen_pct"]), f"Trên {ch.so(s['so_lan_hen'])} lần hẹn", ch.muc_theo_nguong(s["dung_hen_pct"], sl.DUNG_HEN_THAP, 75, False)),
                     ("Bảo trì quá 24 giờ", pc(s["bao_tri_pct"]), "Trên tổng số lần hẹn", ch.muc_theo_nguong(s["bao_tri_pct"], 15, sl.BAO_TRI_24H_CAO)),
                     ("Thời gian xử lý TB", f"{ch.so(s['tgxl_tb'], 1)} giờ", "TGXL trung bình mỗi lần hẹn", "")]),
    ])


def layout():
    if not sl.co_du_lieu():
        return kc.chua_co_du_lieu()
    ev, kpi = sl.su_kien(), sl.kpi_block()
    now = sl.bay_gio(ev)
    s, t = sl.tom_tat(ev, kpi, now), sl.ton(ev, now)
    tuoi = sl.ton_theo_tuoi(t)
    f = go.Figure(go.Bar(x=tuoi["nhom"], y=tuoi["so"], marker_color=[ch.XANH, ch.XANH, ch.XANH_NHAT, ch.CAM, ch.DO], text=tuoi["so"], textposition="outside", cliponaxis=False))
    f.update_yaxes(visible=False)
    loai = t["loai_trien_khai"].replace("", "Không ghi").value_counts().rename_axis("nhom").reset_index(name="so") if len(t) else None
    n_lk = _viec_lien_khoi()
    return html.Div([
        kc.ghi_chu_nguon(), _the_kpi(s),
        html.Div("Nhận định", className="dv-tieu-nhom"), ch.danh_sach_nhan_dinh(sl.nhan_dinh(ev, kpi, now)),
        html.Div("Tồn Kỹ thuật", className="dv-tieu-nhom"),
        html.Div([card([ch.khung(f, 280, legend=False)], title="Hợp đồng tồn theo tuổi", desc="Tuổi tính từ lúc tạo phiếu thi công tới ngày dữ liệu."),
                  card([ch.cot_ngang(loai, "nhom", "so", 280) if loai is not None else html.Div("Chưa có hợp đồng tồn.", className="desc")], title="Tồn theo loại triển khai")],
                 className="dv-hai-cot"),
        html.Div("Nối sang Điều hành liên khối", className="dv-tieu-nhom"),
        card([html.Div(f"Hiện có {n_lk} việc đang giao cho khối Kỹ thuật từ các luật liên khối (chờ online lâu, lỗi sớm sau lắp, sự cố lặp)." if n_lk is not None
                       else "Chưa đọc được việc từ Điều hành liên khối.", className="desc"),
              dcc.Link("Mở Điều hành liên khối", href="/lienkhoi", className="btn")], title="Việc giao cho Kỹ thuật"),
        kc.cach_hieu(),
    ])


def register(app):
    return None
