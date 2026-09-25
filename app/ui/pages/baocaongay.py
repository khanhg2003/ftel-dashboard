"""Trang Báo cáo ngày - sale nhập 6 ô đầu ngày, cả phòng nhìn một bảng (quy tắc: app/bao_cao_ngay.py).

Laptop: sửa ngay trong ô như Google Sheet, tự lưu từng ô. Điện thoại (< 768 px): mỗi người một thẻ,
bấm thẻ mở form. Nút "Tạo ảnh báo cáo" vẽ PNG gửi nhóm. Mọi callback kiểm lại phòng được xem ở máy chủ.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
from dash import ALL, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate
from flask_login import current_user

from app import bao_cao_ngay as bc
from app.auth import ghi_log
from app.org import phong_order
from app.thoi_gian import gio_viet_nam
from app.ui.components import alert, field, modal, tip
from app.ui.icons import icon
from app.ui.luoi import SO, bang

AN = {"display": "none"}
TOI_LA = "Chọn tên mình (để ghi tên)"
GHI_TEN = "Chọn tên mình ở ô \"Tôi là\" để phần \"cập nhật bởi\" ghi đúng tên."
SUA = "params.data.sua_duoc"
# tô cam theo NGƯỜI chưa nhập báo cáo hôm nay, không theo ô bằng 0: KHTN 0 hay ONL sáng 0 là số thật
THIEU = {"o-thieu": "!params.data.da_nhap && !params.data.la_tong"}
# chưa nhập thì để ô trống chứ không hiện 0, nhìn là biết ngay ai còn thiếu
SO_NHAP = {"function": "params.data.da_nhap ? " + SO["function"] + " : ''"}
GOI_Y = ("Mục tiêu bán của riêng hôm nay.\nKHTN là khách đang theo, chưa lên hợp đồng.\n"
         "Dự kiến online sáng / chiều là số ca chắc chắn lên trong buổi đó.")
MAU_CON = {"styleConditions": [{"condition": "params.value > 0",
                                "style": {"color": "#8A5A00", "fontWeight": "650"}}]}


def topbar():
    return [html.Div([html.H1("Báo cáo ngày"),
                      html.Div("Mục tiêu và dự kiến online đầu ngày, cả phòng nhìn chung một bảng",
                               className="sub")])]


def _dung_chung() -> bool:
    return current_user.role == "nvkd"


def nt_ten(acc_norm) -> str | None:
    """Họ tên của acc đang chọn ở ô "Tôi là" - máy chủ tự tra, không tin tên trình duyệt gửi lên."""
    from app.nhap_ton import ten_cua
    return (ten_cua(acc_norm) or acc_norm) if acc_norm else None


def _phong_hop_le(code) -> list[str]:
    ds = current_user.phong_bao_cao_ngay() if current_user.is_authenticated else []
    if code not in ds:
        raise PreventUpdate
    return [code]


def _ngay_hop_le(v) -> date:
    try:
        d = date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return bc.hom_nay()
    return d if d <= bc.hom_nay() else bc.hom_nay()


def _cot() -> list[dict]:
    # cellClass phải kèm "ag-right-aligned-cell": đặt cellClass cho cột numericColumn thì mất lớp
    # căn phải của kiểu cột, số trong ô sale nhập sẽ lệch hàng với các cột số còn lại
    sua = {"editable": {"function": SUA}, "cellClass": "ag-right-aligned-cell o-sale", "cellClassRules": THIEU,
           "type": "numericColumn", "valueFormatter": SO_NHAP, "width": 84, "minWidth": 74, "maxWidth": 104}
    doc = {"type": "numericColumn", "valueFormatter": SO, "width": 84, "minWidth": 72, "maxWidth": 104}
    return [
        {"field": "ho_ten", "headerName": "Nhân sự", "pinned": "left", "width": 146, "minWidth": 146,
         "maxWidth": 190, "cellClass": "o-dam", "tooltipField": "acc"},
        {"field": "muc_tieu", "headerName": "MT ngày *", "headerClass": "vung-sale",
         "headerTooltip": "Mục tiêu bán của riêng hôm nay.", **sua},
        {"field": "khtn", "headerName": "KHTN *", "headerTooltip": "Khách đang theo, chưa lên hợp đồng.",
         **sua},
        {"field": "onl_sang", "headerName": "ONL sáng *", "headerTooltip": "Dự kiến online buổi sáng.", **sua},
        {"field": "onl_chieu", "headerName": "ONL chiều *", "headerTooltip": "Dự kiến online buổi chiều.",
         **sua},
        {"field": "dk_onl", "headerName": "DK ONL", **doc, "cellStyle": {"fontWeight": "700"},
         "headerTooltip": "Dự kiến online cả ngày = sáng + chiều. App tự cộng."},
        # sale gõ tay được: file Internet chỉ về vào hôm sau nên buổi sáng số từ file luôn là 0,
        # không gõ được thì "Còn phải ONL" vô nghĩa. Hiện số lớn hơn giữa số gõ tay và số từ file.
        {"field": "thuc_hien", "headerName": "Đã online *", "headerClass": "vung-sale", **doc,
         "editable": {"function": SUA}, "cellClass": "ag-right-aligned-cell o-sale",
         "headerTooltip": "Số đã online hôm nay của người này.\nSale gõ tay trong ngày; khi file Internet "
                          "về thì app lấy số lớn hơn giữa hai bên."},
        {"field": "con_phai_onl", "headerName": "Còn phải ONL", **doc, "cellStyle": MAU_CON},
        {"field": "pttb_thang", "headerName": "PTTB tháng", **doc, "cellStyle": {"fontWeight": "700"},
         "headerTooltip": "Luỹ kế online từ đầu tháng. App tự lấy."},
        {"field": "mt_thang", "headerName": "MT tháng *", "headerClass": "vung-sale",
         "headerTooltip": "Mục tiêu cả tháng của người này.\nNhập một lần đầu tháng, app nhớ cho các ngày sau.",
         **{**sua, "valueFormatter": SO,
            "cellClassRules": {"o-thieu": "!params.value && !params.data.la_tong"}}},
        {"field": "vvip_thang", "headerName": "V.VIP", **doc,
         "headerTooltip": "Số V.VIP luỹ kế tháng (cột \"Pay\" trong ảnh báo cáo). App tự lấy."},
        # ghi chú để MỘT dòng, xem đủ bằng rê chuột: cột hẹp mà xuống dòng thì 17 người thành bảng dài
        # gấp bốn, sáng ra không ai đọc hết. Bấm vào ô vẫn mở ô soạn to.
        {"field": "ghi_chu", "headerName": "Ghi chú *", "headerClass": "vung-sale", "minWidth": 150,
         "flex": 1, "tooltipField": "ghi_chu", "editable": {"function": SUA},
         "cellClass": "o-sale", "cellEditor": "agLargeTextCellEditor", "cellEditorPopup": True,
         "cellEditorParams": {"maxLength": bc.GHI_CHU_TOI_DA, "rows": 5, "cols": 50}},
    ]


# ------------------------------------------------------------------ giao diện
def layout():
    ds = current_user.phong_bao_cao_ngay()
    if not ds:
        return alert("Tài khoản này không dùng mục Báo cáo ngày.", "bad")
    bc.dam_bao_bang()
    ten = {p["code"]: p["ten"] for p in phong_order()}
    hom = bc.hom_nay()
    return html.Div([
        html.Div([
            html.Div(field("Phòng", dcc.Dropdown(id="bn-phong", options=[{"label": ten.get(c, c), "value": c}
                                                                         for c in ds],
                                                 value=ds[0], clearable=False, style={"width": "150px"})),
                     style={} if len(ds) > 1 else AN),
            field("Ngày", dcc.DatePickerSingle(id="bn-ngay", date=hom.isoformat(), max_date_allowed=hom,
                                               display_format="DD/MM/YYYY", first_day_of_week=1)),
            html.Div(field("Tôi là", dcc.Dropdown(id="bn-toi-la", options=[], placeholder=TOI_LA,
                                                  persistence=True, persistence_type="local",
                                                  style={"minWidth": "220px"})),
                     style={} if _dung_chung() else AN),
            html.Div(className="grow"),
            html.Button([icon("camera", 14), html.Span("Tạo ảnh báo cáo", id="bn-png-chu")], id="bn-png",
                        className="btn primary", n_clicks=0, title="Vẽ ảnh PNG để gửi nhóm Zalo"),
        ], className="toolbar loc-trang"),
        dcc.Download(id="bn-tai"),
        dcc.Store(id="bn-da-luu"),
        html.Div(id="bn-msg"),
        html.Div(id="bn-tom-tat", className="kpi-row kpi-3"),

        html.Div([
            html.Div([html.H3(id="bn-tieu-de", style={"margin": 0}),
                      html.Div(id="bn-mo-ta", className="desc", style={"margin": "2px 0 0"})],
                     className="the-thanh"),
            html.Div(bang("bn-luoi", _cot(), cao=560, lop="ag-theme-quartz ag-theme-ftel luoi-ke",
                          cot_mac_dinh={"resizable": True, "sortable": False, "suppressMovable": True,
                                        "wrapHeaderText": True, "autoHeaderHeight": True},
                          getRowId="params.data.id",
                          tuy_chon={"suppressCellFocus": False, "singleClickEdit": True,
                                    "stopEditingWhenCellsLoseFocus": True, "enableCellTextSelection": True,
                                    "pinnedBottomRowData": []}),
                     className="bn-laptop"),
            html.Div(id="bn-the", className="bn-dien-thoai"),
            html.Div(["Bấm vào ô để sửa, sửa xong tự lưu. Nhấn Tab để nhảy sang ô kế tiếp. ",
                      "Ô viền cam là mục chưa điền.", tip(GOI_Y)], className="goi-y-bam bn-laptop"),
        ], className="card"),

        _khoi_chu(),
        modal("bn-md", html.Span(id="bn-md-tieu-de"), [
            dcc.Store(id="bn-md-acc"),
            html.Div(id="bn-md-dau", className="desc", style={"margin": "0 0 14px"}),
            html.Div([
                _o_so("bn-f-mt", "Mục tiêu ngày *"), _o_so("bn-f-khtn", "KHTN đang có *"),
                _o_so("bn-f-sang", "Dự kiến ONL sáng *"), _o_so("bn-f-chieu", "Dự kiến ONL chiều *"),
                _o_so("bn-f-onl", "Đã online *"),
            ], className="form-grid"),
            html.Div([html.Label("Ghi chú *"),
                      dcc.Textarea(id="bn-f-ghi-chu", className="inp", maxLength=bc.GHI_CHU_TOI_DA,
                                   placeholder="Công việc hôm nay, khó khăn đang gặp...",
                                   style={"width": "100%", "minHeight": "84px"})], className="field rong"),
            html.Div(id="bn-md-msg"),
        ]),
    ])


def _o_so(id_: str, nhan: str):
    return html.Div([html.Label(nhan),
                     dcc.Input(id=id_, type="number", min=0, max=bc.TOI_DA, step=1, className="inp")],
                    className="field")


def _khoi_chu():
    """Ba khối chữ của ảnh báo cáo: Fox viết từ số liệu, Trưởng phòng sửa lại rồi lưu."""
    if current_user.role == "nvkd":
        return None
    o = [("bn-c-trong-tam", "Trọng tâm hôm nay", "Việc cả team phải bám trong ngày."),
         ("bn-c-nhan-dinh", "Đánh giá & nhận định", "Đọc số hôm qua, sáng nay và luỹ kế tháng."),
         ("bn-c-thong-diep", "Thông điệp ngày mới", "Một đoạn ngắn động viên cả team.")]
    return html.Div([
        html.Div([html.H3("Chữ trong ảnh báo cáo", style={"margin": 0}),
                  html.Div("Fox viết sẵn từ số liệu, anh/chị sửa lại rồi bấm Lưu. Ảnh lấy đúng phần này.",
                           className="desc", style={"margin": "2px 0 0"}),
                  html.Div(className="grow"),
                  html.Button([icon("refresh", 14), html.Span("Fox viết giúp", id="bn-fox-chu")],
                              id="bn-fox", className="btn", n_clicks=0),
                  html.Button("Lưu", id="bn-luu-chu", className="btn primary", n_clicks=0)],
                 className="the-thanh"),
        html.Div([html.Div([html.Label([nhan, tip(mo_ta)]),
                            dcc.Textarea(id=i, className="inp", style={"width": "100%", "minHeight": "150px"})],
                           className="field rong") for i, nhan, mo_ta in o], className="form-grid bn-chu"),
        dcc.Loading(html.Div(id="bn-chu-msg"), type="dot"),
    ], className="card")


# ------------------------------------------------------------------ dựng nội dung
def _the_so(nhan: str, so, goi_y: str, mau: str = "") -> html.Div:
    return html.Div([html.Div(nhan, className="label"), html.Div(so, className="value"),
                     html.Div(goi_y, className="hint")], className=f"kpi {mau}")


def _tom_tat(t: dict) -> list:
    hq, ty = t["hq_thuc_te"], t["hq_ty_le"]
    return [
        _the_so(f"Kết quả ngày {t['hom_qua']:%d/%m}", f"{hq} / {t['hq_muc_tieu']}",
                f"Thiếu {t['hq_thieu']} PTTB · đạt {ty}%",
                "ok" if ty >= 100 else "warn" if ty >= 80 else "bad"),
        _the_so(f"Tình hình sáng {t['ngay']:%d/%m}", f"{t['dk_onl']}",
                f"KHTN {t['khtn']} · sáng {t['onl_sang']} · chiều {t['onl_chieu']} · "
                f"đã online {t['da_online']}",
                "ok" if t["mt_ngay"] and t["dk_onl"] >= t["mt_ngay"] else "warn"),
        _the_so("Luỹ kế tháng", f"{t['luy_ke']} / {t['mt_thang']}",
                f"Còn thiếu {t['con_thieu']} PTTB · đạt {t['ty_le_thang']:g}%",
                "ok" if t["ty_le_thang"] >= 90 else "warn" if t["ty_le_thang"] >= 70 else "bad"),
    ]


def _ghim(df: pd.DataFrame) -> list[dict]:
    """Dòng TỔNG ghim cuối bảng. `da_nhap` / `la_tong` để dòng này không dính hai quy tắc của dòng
    người: "chưa nhập thì để ô trống" (nếu không cả dòng tổng sẽ trắng) và tô cam ô còn thiếu."""
    if df.empty:
        return []
    c = ["muc_tieu", "khtn", "onl_sang", "onl_chieu", "dk_onl", "thuc_hien", "con_phai_onl",
         "pttb_thang", "mt_thang", "vvip_thang"]
    return [{"ho_ten": "TỔNG", "da_nhap": True, "la_tong": True, **{k: int(df[k].sum()) for k in c}}]


def _the(df: pd.DataFrame) -> list:
    """Dạng thẻ cho điện thoại."""
    if df.empty:
        return [html.Div("Phòng chưa có số liệu.", className="desc")]
    out = []
    for r in df.itertuples():
        the = html.Button if r.sua_duoc else html.Div
        out.append(the([
            html.Div([html.B(r.ho_ten), html.Div(className="grow"),
                      html.Span(f"{int(r.pttb_thang)}/{int(r.mt_thang)}", className="bn-lk")],
                     className="bn-the-dau"),
            html.Div([html.Span(f"MT {int(r.muc_tieu)}"), html.Span(f"KHTN {int(r.khtn)}"),
                      html.Span(f"Sáng {int(r.onl_sang)}"), html.Span(f"Chiều {int(r.onl_chieu)}"),
                      html.Span(f"Đã ONL {int(r.thuc_hien)}")], className="bn-the-so"),
            html.Div(r.ghi_chu or "Chưa ghi chú", className="bn-the-gc" + ("" if r.ghi_chu else " thieu")),
        ], **({"id": {"type": "bn-the", "acc": r.acc_norm}, "n_clicks": 0} if r.sua_duoc else {}),
            className="bn-the" + ("" if r.da_nhap else " thieu") + ("" if r.sua_duoc else " chi-xem")))
    return out


# ------------------------------------------------------------------ callbacks
def register(app):
    @app.callback(Output("bn-toi-la", "options"), Output("bn-tom-tat", "children"),
                  Output("bn-luoi", "rowData"), Output("bn-luoi", "dashGridOptions"),
                  Output("bn-the", "children"), Output("bn-tieu-de", "children"), Output("bn-mo-ta", "children"),
                  Input("bn-phong", "value"), Input("bn-ngay", "date"), Input("bn-toi-la", "value"),
                  Input("bn-da-luu", "data"), State("ui-vw", "data"), State("bn-luoi", "dashGridOptions"))
    def _nap(code, ngay, toi_la, _luu, vw, opts):
        phong = _phong_hop_le(code)
        d = _ngay_hop_le(ngay)
        df = bc.bang(phong, d)
        t = bc.tom_tat(phong, d)
        if df.empty:
            return [], _tom_tat(t), [], no_update, [], "Bảng chỉ số toàn bộ nhân sự", \
                "Phòng chưa có số liệu (chưa nạp file Internet của tháng này)."
        chon = [{"label": r.ho_ten, "value": r.acc_norm} for r in df.itertuples()]
        df = df.assign(sua_duoc=True)             # sale sửa được mọi dòng (chốt 24/09/2026)
        dien_thoai = (vw or {}).get("w", 1440) < 768
        tieu_de = f"Bảng chỉ số toàn bộ nhân sự · {d:%d/%m/%Y}"
        mo_ta = (f"{t['so_nguoi']} nhân sự · {t['chua_nhap']} người chưa nhập. "
                 "Ô có dấu * là sale nhập, còn lại app tự lấy từ file Internet.")
        if _dung_chung() and not toi_la:
            mo_ta = html.Span([mo_ta, " ", html.I(GHI_TEN)])
        return (chon, _tom_tat(t), [] if dien_thoai else df.to_dict("records"),
                {**(opts or {}), "pinnedBottomRowData": _ghim(df)},
                _the(df) if dien_thoai else [], tieu_de, mo_ta)

    @app.callback(Output("bn-da-luu", "data"), Output("bn-msg", "children"),
                  Input("bn-luoi", "cellValueChanged"), State("bn-phong", "value"), State("bn-ngay", "date"),
                  State("bn-toi-la", "value"), prevent_initial_call=True)
    def _luu_o(doi, code, ngay, toi_la):
        phong, d = _phong_hop_le(code), _ngay_hop_le(ngay)
        ten = nt_ten(toi_la) if _dung_chung() else None
        loi = []
        for x in (doi if isinstance(doi, list) else [doi] if doi else []):
            r, cot = x.get("data") or {}, x.get("colId")
            try:
                if cot == "mt_thang":
                    bc.dat_muc_tieu(f"{d:%Y-%m}", "NHAN_VIEN", r.get("acc_norm"), "internet",
                                    float(x.get("value") or 0), current_user.username)
                elif cot in bc.O_NHAP or cot == "thuc_hien":
                    # cột "Đã online" hiện số đã gộp với file, nhưng gõ vào thì lưu vào ô nhập tay
                    o = "da_online" if cot == "thuc_hien" else cot
                    bc.luu(r.get("acc_norm"), {o: x.get("value")}, phong, current_user.username, d,
                           ghi_ten=ten)
            except bc.LoiBaoCao as e:
                loi.append(str(e))
        return gio_viet_nam().isoformat(), alert(" ".join(loi), "bad") if loi else None

    @app.callback(Output("bn-md", "className"), Output("bn-md-tieu-de", "children"),
                  Output("bn-md-acc", "data"), Output("bn-md-dau", "children"), Output("bn-f-mt", "value"),
                  Output("bn-f-khtn", "value"), Output("bn-f-sang", "value"), Output("bn-f-chieu", "value"),
                  Output("bn-f-onl", "value"), Output("bn-f-ghi-chu", "value"), Output("bn-md-msg", "children"),
                  Input({"type": "bn-the", "acc": ALL}, "n_clicks"), Input("bn-md-dong", "n_clicks"),
                  Input("bn-md-huy", "n_clicks"), Input("bn-da-luu", "data"), State("bn-phong", "value"),
                  State("bn-ngay", "date"), prevent_initial_call=True)
    def _mo_form(bam, _d, _h, _l, code, ngay):
        if not isinstance(ctx.triggered_id, dict):
            return ("modal",) + (no_update,) * 10
        if not any(bam or []):
            raise PreventUpdate
        d = _ngay_hop_le(ngay)
        df = bc.bang(_phong_hop_le(code), d)
        r = df[df.acc_norm == ctx.triggered_id["acc"]]
        if r.empty:
            raise PreventUpdate
        r = r.iloc[0]
        dau = f"{r.acc} · PTTB tháng {int(r.pttb_thang)}/{int(r.mt_thang)} · V.VIP {int(r.vvip_thang)}"
        return ("modal mo", f"{r.ho_ten} · {d:%d/%m}", r.acc_norm, dau, int(r.muc_tieu), int(r.khtn),
                int(r.onl_sang), int(r.onl_chieu), int(r.thuc_hien), r.ghi_chu, "")

    @app.callback(Output("bn-md-msg", "children", allow_duplicate=True),
                  Output("bn-da-luu", "data", allow_duplicate=True),
                  Input("bn-md-ok", "n_clicks"), State("bn-md-acc", "data"), State("bn-f-mt", "value"),
                  State("bn-f-khtn", "value"), State("bn-f-sang", "value"), State("bn-f-chieu", "value"),
                  State("bn-f-onl", "value"), State("bn-f-ghi-chu", "value"), State("bn-phong", "value"),
                  State("bn-ngay", "date"), State("bn-toi-la", "value"), prevent_initial_call=True)
    def _luu_form(_n, acc, mt, khtn, sang, chieu, onl, gc, code, ngay, toi_la):
        phong, d = _phong_hop_le(code), _ngay_hop_le(ngay)
        if not (gc or "").strip():
            return alert("Chưa điền Ghi chú.", "bad"), no_update
        try:
            bc.luu(acc, {"muc_tieu": mt, "khtn": khtn, "onl_sang": sang, "onl_chieu": chieu,
                         "da_online": onl, "ghi_chu": gc},
                   phong, current_user.username, d, ghi_ten=nt_ten(toi_la) if _dung_chung() else None)
        except bc.LoiBaoCao as e:
            return alert(str(e), "bad"), no_update
        return "", gio_viet_nam().isoformat()

    _dang_ky_chu(app)

    @app.callback(Output("bn-tai", "data"), Input("bn-png", "n_clicks"), State("bn-phong", "value"),
                  State("bn-ngay", "date"),
                  running=[(Output("bn-png", "disabled"), True, False),
                           (Output("bn-png", "className"), "btn primary dang-chay", "btn primary"),
                           (Output("bn-png-chu", "children"), "Đang vẽ ảnh...", "Tạo ảnh báo cáo")],
                  prevent_initial_call=True)
    def _anh(_n, code, ngay):
        from app.export_png_ngay import anh_bao_cao_ngay
        phong, d = _phong_hop_le(code), _ngay_hop_le(ngay)
        ghi_log("tao_anh_bao_cao_ngay", f"{code} {d:%d/%m/%Y}")
        png = anh_bao_cao_ngay(phong[0], d)
        return dcc.send_bytes(lambda f: f.write(png), f"BaoCaoDauNgay_{code}_{d:%Y%m%d}.png")


def _dang_ky_chu(app):
    """Ba khối chữ: nạp khi đổi ngày, Fox viết giúp, Trưởng phòng sửa rồi lưu."""
    o = ("bn-c-trong-tam", "bn-c-nhan-dinh", "bn-c-thong-diep")

    @app.callback([Output(i, "value") for i in o],
                  Input("bn-phong", "value"), Input("bn-ngay", "date"))
    def _nap_chu(code, ngay):
        if current_user.role == "nvkd":
            raise PreventUpdate
        c = bc.chu(_phong_hop_le(code)[0], _ngay_hop_le(ngay))
        return c["trong_tam"], c["nhan_dinh"], c["thong_diep"]

    # `running`: khoá nút và đổi chữ trong lúc AI viết - không thì người dùng bấm lại nhiều lần,
    # mỗi lần là một lượt gọi AI tốn tiền
    @app.callback([Output(i, "value", allow_duplicate=True) for i in o], Output("bn-chu-msg", "children"),
                  Input("bn-fox", "n_clicks"), State("bn-phong", "value"), State("bn-ngay", "date"),
                  running=[(Output("bn-fox", "disabled"), True, False),
                           (Output("bn-fox", "className"), "btn dang-chay", "btn"),
                           (Output("bn-fox-chu", "children"), "Fox đang viết...", "Fox viết giúp"),
                           (Output("bn-luu-chu", "disabled"), True, False)],
                  prevent_initial_call=True)
    def _fox(_n, code, ngay):
        from app.bao_cao_ngay_ai import fox_viet
        phong, d = _phong_hop_le(code), _ngay_hop_le(ngay)
        try:
            c = fox_viet(current_user, phong, d)
        except Exception as e:                     # lỗi AI đã viết sẵn bằng tiếng Việt
            return no_update, no_update, no_update, alert(str(e), "bad")
        return c["trong_tam"], c["nhan_dinh"], c["thong_diep"], alert(
            "Fox đã viết xong - anh/chị đọc lại, sửa nếu cần rồi bấm Lưu.", "ok")

    @app.callback(Output("bn-chu-msg", "children", allow_duplicate=True), Input("bn-luu-chu", "n_clicks"),
                  [State(i, "value") for i in o], State("bn-phong", "value"), State("bn-ngay", "date"),
                  prevent_initial_call=True)
    def _luu_chu(_n, tt, nd, td, code, ngay):
        phong, d = _phong_hop_le(code), _ngay_hop_le(ngay)
        bc.luu_chu(phong[0], {"trong_tam": tt, "nhan_dinh": nd, "thong_diep": td},
                   current_user.username, d)
        return alert("Đã lưu phần chữ cho ảnh báo cáo.", "ok")
