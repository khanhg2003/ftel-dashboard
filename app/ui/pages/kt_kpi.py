"""Trang KPI kỹ thuật (SỐ LIỆU THẬT, bản chốt, đã ẩn danh): phần KPIs của web TAIHD, giữ nguyên giao diện và màu gốc.

`scripts/trich_bao_cao_ton.py` cắt nội dung chính của từng mục KPI (đã bỏ cột thông tin khách, đổi tên NV / mã HĐ sang mã giả
cùng bảng mã với Báo cáo tồn) ra `demo/lien_khoi/kt_kpi/`. Trang chỉ ĐỌC các file đó và hiển thị trong khung riêng với CSS
của web gốc, nên màu y hệt và CSS gốc không lẫn sang phần còn lại của app. Không tự cập nhật, không đụng database.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from dash import Input, Output, html

from app.ui.components import card
from app.ui.pages import dvkh_chung as ch

THU_MUC = Path(__file__).resolve().parents[3] / "demo" / "lien_khoi" / "kt_kpi"
MUC = [("tong", "Tổng quan"), ("nhan_su", "KPI nhân sự"), ("huy", "Hủy dịch vụ"), ("hifpt", "HiFPT"), ("csat", "CSAT"),
       ("lap", "Lặp"), ("thu_hoi", "Thu hồi thiết bị"), ("suy_hao", "Suy hao TK-BT"), ("swap", "SWAP WiFi4")]
# Khung tự giãn theo chiều cao nội dung (srcdoc cùng nguồn với trang nên đọc được frameElement), tránh hai thanh cuộn lồng nhau.
# Biểu đồ Plotly lúc lưu là SVG cố định kích thước: co giãn cho vừa khung (giữ nguyên hình và màu) rồi mới đo chiều cao.
GIAN = ("<script>function v(){document.querySelectorAll('.svg-container').forEach(function(c){var s=c.querySelector('svg.main-svg');"
        "if(!s)return;var w=+s.getAttribute('width'),h=+s.getAttribute('height'),o=c.parentElement.parentElement,k=o.clientWidth/w;"
        "if(!w||!k)return;c.style.width=w+'px';c.style.height=h+'px';c.style.transformOrigin='0 0';c.style.transform='scale('+k+')';"
        "o.style.height=(h*k)+'px';o.style.overflow='hidden'})}"
        "function g(){v();var f=window.frameElement;if(f){f.style.height=(document.documentElement.scrollHeight+8)+'px'}}"
        "window.addEventListener('load',g);setTimeout(g,150);setTimeout(g,800);window.addEventListener('resize',g)</script>")
# CSS Plotly tự chèn bằng JS lúc chạy (không được lưu khi Ctrl+S): ẩn thanh công cụ, xếp chồng các lớp SVG.
THEM_CSS = ("body{background:transparent!important}main.container-fluid{padding-top:4px!important}"
            ".modebar-container,.modebar{display:none!important}.svg-container{position:relative}"
            ".svg-container>.main-svg{position:absolute;top:0;left:0}.svg-container>.main-svg:first-child{position:relative}"
            ".js-plotly-plot .main-svg .draglayer,.js-plotly-plot .hoverlayer{pointer-events:none}")


@lru_cache(maxsize=1)
def meta() -> dict:
    f = THU_MUC / "meta.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


@lru_cache(maxsize=1)
def css() -> str:
    f = THU_MUC / "kpi.css"
    return f.read_text(encoding="utf-8") if f.exists() else ""


@lru_cache(maxsize=16)
def trang_html(ma: str) -> str:
    """Tài liệu HTML đầy đủ của một mục (CSS gốc + nội dung đã ẩn danh); rỗng nếu chưa có file."""
    f = THU_MUC / f"{ma}.html"
    if not f.exists():
        return ""
    return ('<!doctype html><html lang="vi" data-theme="light" data-bs-theme="light"><head><meta charset="utf-8">'
            f"<style>{css()}</style><style>{THEM_CSS}</style></head><body>{f.read_text(encoding='utf-8')}{GIAN}</body></html>")


def topbar():
    return [html.Div([html.H1("KPI kỹ thuật"),
                      html.Div("Số liệu thật (tên và mã đã ẩn danh) từ hệ thống KPI của đội: NSLĐ, CSAT, lặp, HiFPT, hủy dịch vụ, thu hồi thiết bị, suy hao",
                               className="sub")])]


def layout():
    m = meta()
    if not m:
        return card([html.Div("Chưa có số liệu KPI. Chạy: python scripts/trich_bao_cao_ton.py <file Báo cáo tồn...> <file KPI...>", className="desc")],
                    title="Chưa có số liệu KPI")
    return html.Div([
        html.Div([html.Span(f"Số liệu thật · tên NV, mã HĐ đã ẩn danh · số liệu KPI lúc {m.get('chot_luc', '')}", className="badge ok")],
                 className="toolbar loc-trang"),
        ch.tab_nho("kt-kpi-muc", MUC, "tong"),
        html.Div(id="kt-kpi-noi-dung"),
    ])


def register(app):
    @app.callback(Output("kt-kpi-noi-dung", "children"), Input("kt-kpi-muc", "value"))
    def _ve(ma):
        h = trang_html(ma or "tong")
        if not h:
            return card([html.Div("Chưa lưu trang này từ web gốc nên chưa có số liệu.", className="desc")], title="Chưa có số liệu mục này")
        return html.Iframe(srcDoc=h, style={"width": "100%", "height": "1400px", "border": "0", "display": "block"}, title=dict(MUC).get(ma, "KPI"))
