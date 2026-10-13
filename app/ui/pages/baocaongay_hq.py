"""Cửa sổ "Hiệu quả & xu hướng" của trang Báo cáo ngày (chốt 12/10/2026, thiết kế lại 13/10/2026): ngoài là TỔNG QUAN CẢ PHÒNG (bốn năm ô chỉ số so với khoảng
trước, thanh kết quả các ca, nhận định, biểu đồ, bảng nhân viên); bấm vào một người thì xem CHI TIẾT người đó (`baocaongay_hq_nv.py`). Quy tắc tính và nhận định ở
`app/online_ca_phan_tich.py`; trang này chỉ dựng giao diện (thành phần dùng chung ở `baocaongay_hq_ve.py`)."""
from __future__ import annotations

from dash import ALL, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

from app import online_ca_phan_tich as pa
from app.ui.components import cua_so, seg_control
from app.ui.pages import baocaongay_hq_ve as ve


def khung() -> html.Div:
    return html.Div([dcc.Store(id="onl-hq-nv"), cua_so("onl-hq", None, nut=seg_control("onl-hq-ky", list(pa.KY.items()), "7"))])


def cac_the_chung(t: dict, t0: dict, xh: dict, xh0: dict, so: dict | None = None) -> html.Div:
    """Năm ô chỉ số + so với khoảng trước. `so` = số của cả phòng để đặt cạnh khi xem một người."""
    so = so or {}
    ty_chot, ty_chot0 = ve.pc(xh["tong"]["onl"], xh["tong"]["dk"]), ve.pc(xh0["tong"]["onl"], xh0["tong"]["dk"])
    ty_ban, ty_ban0 = ve.pc(xh["tong"]["ban"], xh["tong"]["mt"]), ve.pc(xh0["tong"]["ban"], xh0["tong"]["mt"])
    pt = so.get("ty_le")
    muc, _ = pa.danh_gia(t["ty_le"], t["xet"])
    return ve.luoi_the([
        ve.the("Đúng hẹn", "–" if t["ty_le"] is None else f"{t['ty_le']}%", f"{t['dung']}/{t['xet']} ca đã xét" + (f" · cả phòng {pt}%" if pt is not None else ""),
               ve.chenh(t["ty_le"], t0["ty_le"]), muc, "Ca lên online khi còn trong hạn khung giờ sale hẹn lúc tạo ca."),
        ve.the("Online / dự kiến", "–" if ty_chot is None else f"{ty_chot}%", f"{xh['tong']['onl']}/{xh['tong']['dk']} ca", ve.chenh(ty_chot, ty_chot0), "",
               "Số 'Đã online' chia số dự kiến sale gõ ở bảng Báo cáo ngày."),
        ve.the("Ca bị dời ngày", str(t["doi"]), "–" if t["ty_doi"] is None else f"{t['ty_doi']}% số ca" + (f" · cả phòng {so['ty_doi']}%" if so.get("ty_doi") is not None else ""),
               ve.chenh(t["ty_doi"], t0["ty_doi"], tot_khi_giam=True), "", "Ca đã dời sang ngày khác. Càng ít càng tốt."),
        ve.the("Bán / mục tiêu", "–" if ty_ban is None else f"{ty_ban}%", f"{xh['tong']['ban']}/{xh['tong']['mt']} HĐ", ve.chenh(ty_ban, ty_ban0), "",
               "Số bán sale tự nhập chia mục tiêu ngày."),
        ve.the("Số ca theo dõi", str(t["ca"]), f"chưa tới hạn {t['cho']} · không hẹn giờ {t['khong_hen']}", None, "",
               "Mỗi ca dời tính ở cả ngày cũ và ngày mới."),
    ])


def _bang_nv(hq: dict, xh: dict) -> html.Div:
    nv_xh = {r["acc"]: r for r in xh["nv"]}
    dong = []
    for h in hq["nv"]:
        x = nv_xh.get(h["acc"], {})
        muc, nhan = pa.danh_gia(h["ty_le"], h["xet"])
        ty = h["ty_le"]
        dong.append(html.Tr([
            html.Td(h["ten"], className="ten"),
            html.Td(h["ca"]),
            html.Td([html.Span(html.I(style={"width": f"{ty or 0}%"}), className=f"hq-mini {muc}"), html.B("–" if ty is None else f"{ty}%")], className="hq-td-tl"),
            html.Td(h["tre"]), html.Td(h["chua_len"]), html.Td(h["doi"]),
            html.Td("–" if not x or not x["dk"] else f"{x['onl']}/{x['dk']}"),
            html.Td("–" if not x or not x["mt"] else f"{x['ban']}/{x['mt']}"),
            html.Td(ve.huy_hieu(muc, nhan)),
        ], id={"type": "hq-nv", "acc": h["acc"]}, n_clicks=0, className="hq-hang"))
    cot = ["Nhân viên", "Ca", "Đúng hẹn", "Trễ", "Chưa lên", "Dời", "Online / dự kiến", "Bán / mục tiêu", "Đánh giá"]
    return html.Div([html.Div(["Theo nhân viên ", html.Span("· bấm vào một người để xem chi tiết", className="hq-ghi-nho")], className="hq-tde"),
                     html.Table([html.Thead(html.Tr([html.Th(c) for c in cot])), html.Tbody(dong)], className="hq-bang")], className="hq-khoi")


def tong_quan(phong: list[str], ky: str) -> list:
    tu, den = pa.khoang(ky)
    tu0, den0 = pa.ky_truoc(tu, den)
    hq, hq0 = pa.hieu_qua(phong, tu, den), pa.hieu_qua(phong, tu0, den0)
    xh, xh0 = pa.xu_huong(phong, tu, den), pa.xu_huong(phong, tu0, den0)
    t = hq["tong"]
    if not t["ca"] and not xh["ngay"]:
        return [html.Div(f"{ve.khoang_chu(tu, den)}: chưa có ca hoặc báo cáo nào.", className="hq-ghi")]
    dau = html.Div([html.B(ve.khoang_chu(tu, den)), f" · so với {ve.khoang_chu(tu0, den0)}"], className="hq-dau")
    ghi = [html.Div(f"Số liệu Báo cáo ngày chỉ có từ {xh['tu_ngay_co']:%d/%m/%Y} (trước đó báo cáo ngày đã qua bị xoá).", className="hq-ghi")
           ] if xh["tu_ngay_co"] and xh["tu_ngay_co"] > tu else []
    nhieu_ngay = len(hq["ngay"]) >= 2 or len(xh["ngay"]) >= 2
    hinh = ve.cac_hinh(ve.hinh_dung_hen(hq["ngay"]) if len(hq["ngay"]) >= 2 else None, ve.hinh_khung(hq["khung"]) if hq["khung"] else None,
                       ve.hinh_online(xh["ngay"]) if len(xh["ngay"]) >= 2 else None, ve.hinh_ban(xh["ngay"]) if len(xh["ngay"]) >= 2 else None)
    return [dau, *ghi, cac_the_chung(t, hq0["tong"], xh, xh0), ve.thanh_ket_qua(t), ve.nhan_dinh(pa.nhan_dinh_phong(hq, hq0, xh)),
            hinh if nhieu_ngay or hq["khung"] else None, _bang_nv(hq, xh), ve.ghi_cuoi()]


def noi_dung(phong: list[str], ky: str, acc: str | None = None) -> list:
    if acc:
        from app.ui.pages import baocaongay_hq_nv
        return baocaongay_hq_nv.chi_tiet(phong, ky, acc)
    return tong_quan(phong, ky)


def register(app):
    @app.callback(Output("onl-hq", "className"), Output("onl-hq-tieu-de", "children"), Output("onl-hq-than", "children"), Output("onl-hq-nv", "data"),
                  Input("onl-hq-mo", "n_clicks"), Input("onl-hq-dong", "n_clicks"), Input("onl-hq-nen", "n_clicks"), Input("onl-hq-ky", "value"),
                  Input({"type": "hq-nv", "acc": ALL}, "n_clicks"), Input({"type": "hq-ve", "i": ALL}, "n_clicks"),
                  State("bn-phong", "value"), State("onl-hq", "className"), State("onl-hq-nv", "data"), prevent_initial_call=True)
    def _hq(mo, _dong, _nen, ky, _nv, _ve, code, lop, nv_cu):
        from app.ui.pages import baocaongay as bn
        t = ctx.triggered_id
        nv = nv_cu
        if t in ("onl-hq-dong", "onl-hq-nen"):
            return "modal", no_update, no_update, None
        if isinstance(t, dict):                              # bấm một dòng nhân viên / nút "Cả phòng"; thành phần mới dựng ra cũng bắn một lần với giá trị rỗng
            if not ctx.triggered[0]["value"]:
                raise PreventUpdate
            nv = t["acc"] if t["type"] == "hq-nv" else None
        elif t == "onl-hq-mo":
            if not mo:
                raise PreventUpdate
            nv = None
        elif t == "onl-hq-ky" and "mo" not in (lop or ""):
            raise PreventUpdate                              # đổi kỳ khi cửa sổ đang đóng: không dựng gì
        phong = bn._phong_hop_le(code)
        than = noi_dung(phong, ky or "7", nv)
        return "modal mo", f"Hiệu quả & xu hướng · {code}", than, nv
