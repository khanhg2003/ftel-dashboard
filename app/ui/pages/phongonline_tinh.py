"""Phòng Online - thẻ "Bán / online theo tỉnh" (CEO yêu cầu 20/11/2026): khách của nhóm ở tỉnh nào, so cùng kỳ tháng trước, từng bạn bán ở tỉnh nào.

Số liệu đúng như thẻ "Bán theo tỉnh" của Phân tích bán hàng (`phan_tich.hd_theo_tinh` / `bang_tinh` / `ma_tran_nv_tinh`, biểu đồ và cột dùng chung ở
`phantich_tinh`), chỉ giữ người của nhóm (`phong_online.hd_theo_tinh`). Luỹ kế từ ngày 01 tới ngày chọn ở đầu trang, so cùng kỳ tháng trước.
Quyền như trang Phòng Online (BGĐ và vai trò "online"); callback kiểm lại ở máy chủ."""
from __future__ import annotations

from datetime import date

from dash import Input, Output, html
from dash.exceptions import PreventUpdate
from flask_login import current_user

from app import phan_tich as pt
from app import phong_online as po
from app.tinh import NOI_TINH
from app.ui import ngan_nhan_su as nn
from app.ui.components import ghi_chu, seg_control
from app.ui.pages.phantich import _dau_the, _graph, _grid
from app.ui.pages.phantich_tinh import cot_bang_tinh, cot_nv_tinh, hinh_tinh

CHI_SO = {"online": ("Online", "online", "online trong kỳ"), "ban": ("Bán mới", "bán mới", "hợp đồng tạo mới trong kỳ, gồm cả hợp đồng chưa online")}


def _duoc_xem() -> bool:
    return current_user.is_authenticated and current_user.duoc_xem_phong_online


def the() -> html.Div:
    return html.Div([
        _dau_the("Bán / online theo tỉnh", "po-tinh-mo-ta",
                 seg_control("po-tinh-chi-so", [("online", "Số online"), ("ban", "Số bán mới")], "online"),
                 seg_control("po-tinh-loai", [("tat_ca", "Tất cả tỉnh"), ("ngoai", "Chỉ ngoại tỉnh")], "tat_ca")),
        html.Div(id="po-tinh-tom-tat", className="chips", style={"margin": "4px 0 10px"}),
        html.Div([
            html.Div(_graph("po-tinh-bd"), className="chart-col"),
            html.Div(_grid("po-tinh-bang", cao=420, className="ag-theme-quartz ag-theme-ftel luoi-ke"), className="chart-col"),
        ], className="chart-row doi"),
        html.Div([html.H3("Từng bạn bán ở tỉnh nào", style={"margin": 0, "fontSize": "14px"})], className="the-thanh", style={"margin": "18px 0 6px"}),
        nn.goi_y("Bấm vào tên một bạn để xem chi tiết đầy đủ.", style={"marginBottom": "8px"}),
        ghi_chu("Mỗi dòng một bạn trong nhóm, mỗi cột một tỉnh có số (nhiều trước, kéo ngang để xem hết). Màu theo tỷ trọng trong số của chính người đó: "
                "xanh đậm từ 20%, xanh nhạt 5-20%. Tỉnh theo CN quản lý của hợp đồng (nơi khách ở).", nhan="Cách đọc bảng", style={"margin": "0 0 8px"}),
        _grid("po-tinh-nv", cao=300, className=f"ag-theme-quartz ag-theme-ftel luoi-ke {nn.lop('mot')}"),
    ], className="card")


def _ky(ngay_iso: str) -> dict:
    """Luỹ kế 01 -> ngày chọn và khoảng cùng kỳ tháng trước (cùng quy tắc `phan_tich.khoang_so_sanh` của trang Phân tích)."""
    d = date.fromisoformat(ngay_iso)
    tu, den = d.replace(day=1).isoformat(), d.isoformat()
    (ck_tu, ck_den), _ = pt.khoang_so_sanh(tu, den)
    return {"tu": tu, "den": den, "ck": (ck_tu, ck_den), "ten_ck": f"cùng kỳ t{int(ck_tu[5:7]):02d}",
            "ten_ck_day": f"{ck_tu[8:10]}/{ck_tu[5:7]} - {ck_den[8:10]}/{ck_den[5:7]}", "nhan": f"01 - {d:%d/%m}"}


def register(app):
    @app.callback(Output("po-tinh-mo-ta", "children"), Output("po-tinh-tom-tat", "children"), Output("po-tinh-bd", "figure"),
                  Output("po-tinh-bang", "columnDefs"), Output("po-tinh-bang", "rowData"),
                  Output("po-tinh-nv", "columnDefs"), Output("po-tinh-nv", "rowData"),
                  Input("po-date", "date"), Input("po-tinh-chi-so", "value"), Input("po-tinh-loai", "value"))
    def _tinh(ngay_iso, chi_so, loai):
        if not _duoc_xem() or not ngay_iso:
            raise PreventUpdate
        theo = chi_so if chi_so in CHI_SO else "online"
        nhan_cot, nhan_ngan, nhan_dai = CHI_SO[theo]
        ky = _ky(ngay_iso)
        df, df_ck = po.hd_theo_tinh(ky["tu"], ky["den"], theo), po.hd_theo_tinh(*ky["ck"], theo)
        bang = pt.bang_tinh(df, df_ck)
        tong = int(bang.online.sum()) if len(bang) else 0
        noi = int(bang[bang.noi_tinh].online.sum()) if len(bang) else 0
        ngoai = bang[~bang.noi_tinh & (bang.online > 0)] if len(bang) else bang
        chips = []
        if tong:
            chips = [html.Span(f"{tong:,} hợp đồng {nhan_ngan}".replace(",", "."), className="chip"),
                     html.Span(f"Nội tỉnh (Đà Nẵng + Quảng Nam): {noi / tong * 100:.0f}%", className="chip"),
                     html.Span(f"Ngoại tỉnh: {(tong - noi) / tong * 100:.0f}% · {len(ngoai)} tỉnh", className="chip")]
            if len(ngoai):
                r = ngoai.iloc[0]
                chips.append(html.Span(f"Ngoại tỉnh nhiều nhất: {r.tinh} ({int(r.online)})", className="chip"))
        x = bang[~bang.noi_tinh] if loai == "ngoai" and len(bang) else bang
        x = x[x.online > 0].head(15)
        mo_ta = f"{po.TEN} · {nhan_dai} {ky['nhan']}, so {ky['ten_ck_day']} · tỉnh theo CN quản lý của hợp đồng (nơi khách ở)"
        d_nv = df if loai != "ngoai" else df[~df.ma_tinh.isin(NOI_TINH)]
        mt, tinh = pt.ma_tran_nv_tinh(d_nv, pt.ten_nhan_vien(), {po.phong_goc(): po.TEN})
        mt = mt.drop(columns=["khac"], errors="ignore")
        rows_nv = [{**r, "acc_norm": r["acc_key"]} for r in mt.to_dict("records")] if len(mt) else []
        return (mo_ta, chips, hinh_tinh(x, ky["ten_ck"]), cot_bang_tinh(ky["ten_ck"], ky["ten_ck_day"], nhan_cot, bam_duoc=False),
                bang.to_dict("records") if len(bang) else [], [c for c in cot_nv_tinh(tinh, bam_duoc=False) if c["field"] != "phong"], rows_nv)   # cột Phòng thừa: cả nhóm cùng một phòng
