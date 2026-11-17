"""Trang Báo cáo tồn (SỐ LIỆU THẬT, bản chốt): tồn triển khai / bảo trì, năng suất KTV đang trực, mất tín, công nợ của TIN Huế.

Số liệu lấy từ trang "Báo cáo tồn" của web NKN Huế, chốt một lần bằng `scripts/trich_bao_cao_ton.py` ra
`demo/lien_khoi/kt_bao_cao_ton.json`; trang chỉ ĐỌC file đó, không tự cập nhật, không đụng database.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, html

from app.ui.components import card
from app.ui.pages import dvkh_chung as ch

FILE = Path(__file__).resolve().parents[3] / "demo" / "lien_khoi" / "kt_bao_cao_ton.json"
GOC = {"do": "#e5392b", "vang": "#e8b923", "xanh": "#2fa84f", "cam": "#f36f21", "lam": "#1f86d6", "brand": "#004B87"}      # bảng màu của web gốc
TEN_TAB = {"tonNs0": "Chưa có NS", "tonCao": "Tồn cao · NS thấp", "tonBt": "Chưa có ca 9h", "tonTk": "Chưa BT 9h · TK 10h",
           "tonQh72": "TK >72h", "tonOnl": "Online chưa đóng", "tonCi": "Check in", "tonMt": "Mất tín", "tonCn": "Công nợ"}
BI_CAT = {"tonMt": "Ở đây chỉ hiện 15 hợp đồng đầu, xem đủ ở mục Mất tín.", "tonCn": "Trang gốc chỉ hiện 15 nhân viên đầu."}
MUC = [("tong", "Tổng quan"), ("block", "Tổng hợp"), ("staff", "Nhân sự"), ("detail", "Chi tiết tồn"), ("mt", "Mất tín")]


@lru_cache(maxsize=1)
def du_lieu() -> dict:
    return json.loads(FILE.read_text(encoding="utf-8")) if FILE.exists() else {}


def topbar():
    return [html.Div([html.H1("Báo cáo tồn"),
                      html.Div("Số liệu thật (tên và mã đã ẩn danh) của đội Kỹ thuật: tồn, năng suất KTV đang trực, mất tín, công nợ", className="sub")])]


def _nhan_dinh(dong: str) -> dict:
    """Một dòng nhận định của trang gốc → thẻ nhận định (mức theo biểu tượng đầu dòng)."""
    muc = "Nghiêm trọng" if dong[:1] in "🛑📵⏰" else ("Thông tin" if dong.startswith("🧩") else "Cần chú ý")
    chu = dong.split(" ", 1)[1] if " " in dong else dong
    tieu_de, _, noi_dung = chu.partition(":")
    return {"muc": muc, "chu_de": "Báo cáo tồn", "tieu_de": tieu_de.strip(), "noi_dung": noi_dung.strip()}


def _bieu_do_vong(bd: dict):
    """Vòng tròn "Năng suất NV đang trực" như web gốc: đã có / chưa có năng suất."""
    ns = next((x for x in bd.get("prog", []) if "năng suất" in x.get("l", "")), None)
    if ns is None:
        return html.Div("Không có số liệu.", className="desc")
    f = go.Figure(go.Pie(labels=["Đã có năng suất", "Chưa có năng suất"], values=[ns["v"], ns["d"] - ns["v"]], hole=0.72, sort=False,
                         marker={"colors": [GOC["xanh"], GOC["do"]], "line": {"color": "#fff", "width": 2}}, textinfo="none"))
    f.add_annotation(text=f"<b>{ns['v']}/{ns['d']}</b><br><span style='font-size:12px'>đã có năng suất</span>", showarrow=False,
                     font={"size": 26, "color": GOC["brand"]})
    f.update_layout(legend={"orientation": "h", "y": -0.05, "x": 0.5, "xanchor": "center"})
    return ch.khung(f, 280)


def _bieu_do_tien_do(bd: dict):
    p = pd.DataFrame(bd.get("prog", []))
    if p.empty:
        return html.Div("Không có số liệu.", className="desc")
    p["pct"] = p["v"] / p["d"] * 100
    p = p.iloc[::-1]
    f = go.Figure(go.Bar(y=p["l"], x=p["v"], orientation="h", marker_color=[GOC["xanh"] if v >= 90 else (GOC["vang"] if v >= 60 else GOC["do"]) for v in p["pct"]],
                         text=[f"<b>{v}/{d}</b>" for v, d in zip(p["v"], p["d"])], textposition="outside", cliponaxis=False,
                         hovertemplate="%{y}: %{x}<extra></extra>"))
    f.update_xaxes(range=[0, int(p["d"].max()) * 1.12], showgrid=True, gridcolor="#EDF1F6")
    f.update_yaxes(automargin=True)
    return ch.khung(f, 280, legend=False)


def _bieu_do_dieu_hanh(bd: dict):
    dh = bd.get("dh") or {}
    if not dh.get("labels"):
        return html.Div("Không có số liệu.", className="desc")
    f = go.Figure([go.Bar(name=ten, x=dh["labels"], y=dh.get(k, []), marker_color=mau)
                   for k, ten, mau in (("bt", "Chưa có ca đầu ngày", GOC["vang"]), ("ns0", "Chưa có năng suất", GOC["do"]), ("cao", "Tồn cao · NS thấp", GOC["cam"]))])
    f.update_layout(barmode="group", bargap=0.35)
    f.update_yaxes(dtick=1)
    return ch.khung(f, 280)


def _bieu_do_ns0(bd: dict):
    """Tồn của các NV chưa có năng suất: TK xanh, BT cam, như web gốc."""
    p = pd.DataFrame(bd.get("ns0", []))
    if p.empty:
        return html.Div("Không có NV nào chưa có năng suất.", className="desc")
    p = p.iloc[::-1]
    f = go.Figure([go.Bar(name=ten, y=p["n"], x=p[c], orientation="h", marker_color=mau) for c, ten, mau in (("tk", "Tồn TK", GOC["lam"]), ("bt", "Tồn BT", GOC["cam"]))])
    f.update_layout(barmode="stack")
    f.update_yaxes(automargin=True)
    return ch.khung(f, 280)


def _bieu_do_phan_tan(bd: dict):
    """Mỗi chấm một NV đang trực: trục ngang năng suất, trục dọc tồn; vùng đỏ = tồn ≥ ngưỡng và NS < ngưỡng."""
    p = pd.DataFrame(bd.get("pts", []))
    if p.empty:
        return html.Div("Không có số liệu.", className="desc")
    th, mau = bd.get("th", {}), bd.get("dhc", {})
    f = go.Figure()
    for dh, nhom in p.groupby("d"):
        f.add_trace(go.Scatter(x=nhom["x"], y=nhom["y"], mode="markers", name=dh, text=nhom["n"],
                               marker={"size": 10, "color": mau.get(dh), "line": {"width": [2.5 if t == "cao" else 0.5 for t in nhom["t"]],
                                                                                    "color": [ch.DO if t == "cao" else "#fff" for t in nhom["t"]]}},
                               hovertemplate="%{text}<br>NS %{x} · tồn %{y}<extra>" + dh + "</extra>"))
    if th:
        f.add_shape(type="rect", x0=0, x1=th.get("ns", 2), y0=th.get("cao", 4), y1=max(p["y"].max(), th.get("cao", 4)) + 1,
                    fillcolor="rgba(217,45,32,0.08)", line={"width": 0}, layer="below")
    f.update_xaxes(title="Năng suất (NS T)", showgrid=True, gridcolor="#EDF1F6")
    f.update_yaxes(title="Tồn nhân sự")
    return ch.khung(f, 280)


def _so(v: str, tien: bool):
    """Chữ trên web → số (web ghi số lẻ bằng dấu chấm, tiền ghi dấu chấm ngăn nghìn); không phải số thì None."""
    v = v.replace(".", "") if tien else v
    return float(v) if re.fullmatch(r"-?\d+(\.\d+)?", v or "") else None


def _kieu_css(k: str) -> dict:
    """"background:#fde2df;color:#b71c1c" → {"backgroundColor": ..., "color": ...} cho ô ag-grid."""
    ten = {"background": "backgroundColor", "color": "color"}
    kq = {ten[a]: b for a, _, b in (x.partition(":") for x in k.split(";")) if a in ten}
    return {**kq, "fontWeight": 600} if "color" in kq else kq


def bang_chi_tiet(b: dict, muc: str = "tong"):
    """Bảng giữ nguyên cột như trang gốc; cột toàn số thì căn phải để xếp theo số."""
    cot, dong = b["cot"], b["dong"]
    mau = b.get("mau") or [[""] * len(cot) for _ in dong]
    df = pd.DataFrame(dong, columns=[f"c{i}" for i in range(len(cot))])
    dinh_nghia = []
    for i, ten in enumerate(cot):
        tien = "đ" in ten or (any("." in v for v in df[f"c{i}"]) and all(re.fullmatch(r"\d{1,3}(\.\d{3})*", v or "") for v in df[f"c{i}"]))   # 300.000 = tiền
        so = [_so(v, tien) for v in df[f"c{i}"]]
        if dong and all(s is not None for s in so):
            df[f"c{i}"] = so
            c = ch.cot_so(f"c{i}", ten, 120) if tien else ch.cot_so1(f"c{i}", ten, 100)
        else:
            c = ch.cot_chu(f"c{i}", ten, 150 if i == 0 else None)
        df[f"m{i}"] = [m[i] for m in mau]
        kieu = sorted({m[i] for m in mau if m[i]})
        if kieu:          # tô y hệt web gốc: mỗi màu đang có trong cột là một điều kiện
            c["cellStyle"] = {"styleConditions": [{"condition": f"params.data.m{i} == '{k}'", "style": _kieu_css(k)} for k in kieu]}
        dinh_nghia.append(c)
    return ch.bang_df(f"kt-bct-bang-{muc}-{b['ma']}", df, dinh_nghia, 420 if len(dong) > 8 else 60 + 42 * len(dong))


def _muc(ma: str) -> dict:
    return du_lieu().get("muc", {}).get(ma) or {}


def _the(ds: list[dict]) -> html.Div:
    """Thẻ số đúng kiểu web gốc (lớp ton-card + red / amber / k-ton / k-done / k-lap / k-hen, CSS ở assets/style.css)."""
    return html.Div([html.Div([html.Span(x["nhan"], className="l"), html.Span(x["so"], className="n")]
                              + ([html.Span(x["ghi_chu"], className="s")] if x.get("ghi_chu") else []),
                              className=f"ton-card {x.get('lop', '')}".strip()) for x in ds], className="ton-cards")


def _the_theo_nhom(ds: list[dict]) -> list:
    """Thẻ số chia nhóm như trang gốc (Quá giờ, Bảo trì, Triển khai, CSAT); không có nhóm thì một hàng."""
    nhom = list(dict.fromkeys(x.get("nhom", "") for x in ds))
    if nhom == [""]:
        return [_the(ds)]
    return [x for n in nhom for x in (html.P(n, className="ton-sec"), _the([t for t in ds if t.get("nhom", "") == n]))]


def _ve_tong(m: dict) -> html.Div:
    bd, bang = m.get("bieu_do", {}), m.get("bang", [])
    return html.Div([
        _the(m.get("the", [])),
        html.Div([card([_bieu_do_vong(bd)], title="🎯 Năng suất NV đang trực", desc="NV có lịch trực, trừ KTV Pro."),
                  card([_bieu_do_tien_do(bd)], title="🕘 Tiến độ đầu ngày", desc="Số NV trực đã đạt mốc."),
                  card([_bieu_do_dieu_hanh(bd)], title="🧑‍💼 Theo Điều hành", desc="Số NV cần nhắc.")],
                 className="ba-cot"),
        html.Div([card([_bieu_do_ns0(bd)], title="🛑 Tồn của các NV chưa có năng suất", desc="TK + BT."),
                  card([_bieu_do_phan_tan(bd)], title="Tồn và năng suất từng NV", desc="Vùng đỏ là tồn cao, năng suất thấp. Viền đỏ là NV cần xử lý.")],
                 className="dv-hai-cot"),
        html.Div("Nhận định", className="dv-tieu-nhom"),
        ch.danh_sach_nhan_dinh([_nhan_dinh(x) for x in m.get("nhan_dinh", [])]),
        html.Div("Chi tiết", className="dv-tieu-nhom"),
        ch.tab_nho("kt-bct-tab", [(b["ma"], TEN_TAB.get(b["ma"], b["tieu_de"])) for b in bang], bang[0]["ma"] if bang else ""),
        html.Div(id="kt-bct-chi-tiet"),
    ])


def _bieu_do_tong_hop(bd: dict) -> html.Div | None:
    """Ba biểu đồ của mục Tổng hợp: cơ cấu quá giờ, tồn so với đã hoàn tất, tồn theo block."""
    goc = {k: float(v) for k, v in (bd.get("base") or {}).items() if re.fullmatch(r"-?\d+(\.\d+)?", str(v))}
    khoi = pd.DataFrame(bd.get("blocks", []))
    if not goc and khoi.empty:
        return None
    qua = [("BT 18-23h", "BT 18h – 24h", GOC["vang"]), ("BT quá 24h", "BT quá 24h", GOC["do"]), ("TK 48-70h", "TK 48h – 72h", GOC["vang"]), ("TK quá 72h", "TK quá 72h", GOC["do"])]
    f1 = go.Figure(go.Bar(x=[n for _, n, _ in qua], y=[goc.get(k, 0) for k, _, _ in qua], marker_color=[m for *_, m in qua],
                          text=[ch.so(goc.get(k, 0)) for k, _, _ in qua], textposition="outside", cliponaxis=False))
    f1.update_yaxes(visible=False)
    cap = [("Bảo trì", "Tồn Bảo Trì", "Hoàn Tất BT"), ("Triển khai", "Tồn Triển Khai", "Hoàn Tất TK"), ("TK mới", "Triển Khai Mới", "HT Triển Khai mới"),
           ("Mất tín", "Không tín", "Hoàn Tất Mất Tín"), ("Swap wifi 6", "Swap wifi 6", "HT WIFI 6")]
    f2 = go.Figure([go.Bar(name=ten, x=[c[0] for c in cap], y=[goc.get(c[i], 0) for c in cap], marker_color=mau, text=[ch.so(goc.get(c[i], 0)) for c in cap],
                           textposition="outside", cliponaxis=False) for i, ten, mau in ((1, "Tồn", GOC["do"]), (2, "Đã hoàn tất", GOC["xanh"]))])
    f2.update_yaxes(visible=False)
    o = [card([ch.khung(f1, 280, legend=False)], title="Cơ cấu quá giờ", desc="BT / TK sắp quá hạn và đã quá hạn."),
         card([ch.khung(f2, 280)], title="Tồn so với đã hoàn tất", desc="Theo từng loại phiếu.")]
    if not khoi.empty:
        k = khoi.assign(tong=khoi["tk"] + khoi["bt"]).sort_values("tong", ascending=False)
        f3 = go.Figure([go.Bar(name=ten, x=k["b"], y=k[c], marker_color=mau) for c, ten, mau in (("tk", "Tồn triển khai", GOC["lam"]), ("bt", "Tồn bảo trì", GOC["cam"]))])
        f3.update_layout(barmode="stack")
        f3.update_xaxes(tickangle=-40)
        o.append(card([ch.khung(f3, 280)], title="Tồn theo Block", desc="Tồn triển khai + bảo trì, xếp giảm dần."))
    return html.Div(o, className="ba-cot")


def _ve_muc(ma: str, m: dict) -> html.Div:
    """Tổng hợp / Nhân sự / Chi tiết tồn / Mất tín: thẻ số, biểu đồ (nếu có), rồi từng bảng như trang gốc."""
    bd = _bieu_do_tong_hop(m.get("bieu_do", {})) if ma == "block" else None
    bang = [card([bang_chi_tiet(b, ma) if b["dong"] else html.Div("Không có dòng nào.", className="desc")],
                 title=f"{b['tieu_de']} · {b['so']}" if b.get("so") else b["tieu_de"],
                 desc=" ".join(x for x in (b.get("tom_tat"), b.get("mo_ta")) if x) or None) for b in m.get("bang", [])]
    return html.Div(_the_theo_nhom(m.get("the", [])) + ([bd] if bd is not None else []) + bang)


def layout():
    d = du_lieu()
    if not d.get("muc"):
        return card([html.Div("Chưa có file số liệu. Chạy: python scripts/trich_bao_cao_ton.py \"Tổng quan.html\" \"Tổng hợp.html\" ...", className="desc")],
                    title="Chưa có số liệu Báo cáo tồn")
    return html.Div([
        html.Div([html.Span(f"Số liệu thật · tên NV, mã HĐ đã ẩn danh · chốt lúc {d.get('chot_luc', '')}", className="badge ok"),
                  html.Span(f"{_muc('tong').get('bieu_do', {}).get('duty', '–')} NV đang trực", className="badge muted")], className="toolbar loc-trang"),
        ch.tab_nho("kt-bct-muc", MUC, "tong"),
        html.Div(id="kt-bct-noi-dung"),
    ], className="kt-bct")


def register(app):
    @app.callback(Output("kt-bct-noi-dung", "children"), Input("kt-bct-muc", "value"))
    def _ve_noi_dung(ma):
        m = _muc(ma or "tong")
        if not m:
            return card([html.Div("Chưa lưu trang này từ web gốc nên chưa có số liệu.", className="desc")], title="Chưa có số liệu mục này")
        return _ve_tong(m) if ma in (None, "tong") else _ve_muc(ma, m)

    @app.callback(Output("kt-bct-chi-tiet", "children"), Input("kt-bct-tab", "value"))
    def _ve(ma):
        b = next((x for x in _muc("tong").get("bang", []) if x["ma"] == ma), None)
        if b is None:
            return html.Div("Chọn một mục ở trên.", className="desc")
        mo_ta = " ".join(x for x in (b.get("tom_tat"), b.get("mo_ta"), BI_CAT.get(ma)) if x)
        tieu_de = f"{b['tieu_de']} · {b['so']}" if b.get("so") else b["tieu_de"]
        return card([bang_chi_tiet(b)], title=tieu_de, desc=mo_ta or None)
