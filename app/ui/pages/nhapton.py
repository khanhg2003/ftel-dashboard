"""Trang Nhập tồn - sale ghi tình trạng hợp đồng chưa online, Trưởng phòng theo dõi (quy tắc: app/nhap_ton.py).

Laptop: bảng sửa ngay trong ô như Google Sheet, tự lưu từng ô. Điện thoại (< 768 px): mỗi ca một thẻ, bấm thẻ mở
form 3 mục bắt buộc. Danh sách xếp theo từng cụm nhân viên. Mọi callback kiểm lại phòng được xem ở máy chủ.
"""
from __future__ import annotations

import base64

import pandas as pd
from dash import ALL, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate
from flask_login import current_user

from app import nhap_ton as nt
from app.auth import ghi_log
from app.org import phong_order
from app.thoi_gian import gio_viet_nam
from app.ui.components import alert, field, kpi, modal, seg_control, tip
from app.ui.icons import icon
from app.ui.luoi import SO, bang

NHANH = [("all", "Tất cả"), ("gap", "Cần xử lý gấp"), ("den_han", "Đến hạn hôm nay"), ("thieu", "Chưa cập nhật")]
AN = {"display": "none"}
NHOM = "params.data.loai_dong == 'nhom'"
LA_CA = "params.data.loai_dong != 'nhom'"
SUA = f"{LA_CA} && params.data.sua_duoc"
NGAY_DM = {"function": "params.value ? params.value.slice(8, 10) + '/' + params.value.slice(5, 7) : ''"}
NGAY_DMY = {"function": "params.value ? params.value.slice(8, 10) + '/' + params.value.slice(5, 7) + '/' "
                        "+ params.value.slice(0, 4) : ''"}
THIEU = {"o-thieu": f"{LA_CA} && params.data.muc != 'huy' && !params.value"}
MAU_CANH_BAO = {"styleConditions": [
    {"condition": "params.data.muc == 'do'", "style": {"color": "#B42318", "fontWeight": "650"}},
    {"condition": "params.data.muc == 'vang'", "style": {"color": "#8A5A00", "fontWeight": "650"}}]}
MAU_PA = {"pa-cho": "params.value == 'Đang chờ triển khai'", "pa-huy": "params.value == 'Huỷ'",
          "pa-suy-nghi": "params.value == 'KH đang suy nghĩ - Chốt lại'", "pa-xong": "params.value == 'Đã triển khai'"}
GOI_Y_GHI_CHU = "Nguyên nhân tồn + thời gian hẹn thực tế. Treo, CPTC... cũng ghi ở đây."
CHON_TEN = "Chọn tên mình ở ô Nhân viên để bắt đầu cập nhật."
GOI_Y_MOC = ("Mốc đang hiển thị trên PTC.\nHẹn thi công: quá ngày mà chưa online thì báo đỏ, đúng hôm nay báo vàng.\n"
             "Trả về: điền ngày bị trả về. Quá {han} ngày không xử lý thì HĐ tự huỷ nên luôn báo đỏ.")


def topbar():
    return [html.Div([html.H1("Nhập tồn"),
                      html.Div("Tình trạng từng hợp đồng chưa online, sale cập nhật mỗi ngày", className="sub")])]


def _dung_chung() -> bool:
    """Tài khoản dùng chung của phòng: phải chọn tên mình mới sửa được (chốt 21/09/2026)."""
    return current_user.role == "nvkd"


def _nguoi_ghi(acc) -> tuple[str | None, str | None]:
    """(chỉ được sửa ca của acc nào, tên ghi vào "cập nhật bởi"). Tài khoản riêng thì (None, None)."""
    if not _dung_chung():
        return None, None
    if not acc or acc == "all":
        raise nt.LoiNhapTon(CHON_TEN)
    return acc, nt.ten_cua(acc) or acc


def _phong_hop_le(code) -> list[str]:
    ds = current_user.phong_nhap_ton() if current_user.is_authenticated else []
    if code not in ds:
        raise PreventUpdate
    return [code]


def _cot(han: int, pa: list[str]) -> list[dict]:
    sua = {"editable": {"function": SUA}, "cellClassRules": THIEU}
    return [
        {"field": "hop_dong", "headerName": "Hợp đồng", "pinned": "left", "minWidth": 118, "maxWidth": 130,
         "colSpan": {"function": f"{NHOM} ? 20 : 1"}, "cellClass": "o-dam"},
        {"field": "ten_khach_hang", "headerName": "Tên khách hàng", "minWidth": 150, "flex": 1.1,
         "tooltipField": "ten_khach_hang"},
        {"field": "ngay_tao_hd", "headerName": "Ngày tạo HĐ", "minWidth": 100, "maxWidth": 110,
         "valueFormatter": NGAY_DMY},
        {"field": "so_ngay_cho", "headerName": "Chờ", "minWidth": 62, "maxWidth": 70, "type": "numericColumn",
         "valueFormatter": SO, "headerTooltip": "Số ngày từ ngày tạo HĐ đến ngày có số mới nhất."},
        {"field": "ghi_chu", "headerName": "Ghi chú tình trạng * ⓘ", "headerClass": "co-chu-thich",
         "headerTooltip": GOI_Y_GHI_CHU, "minWidth": 240, "flex": 2.4, "wrapText": True, "autoHeight": True,
         "cellEditor": "agLargeTextCellEditor", "cellEditorPopup": True,
         "cellEditorParams": {"maxLength": nt.GHI_CHU_TOI_DA, "rows": 5, "cols": 50}, **sua},
        {"field": "loai_moc", "headerName": "Mốc tick hẹn (PTC) * ⓘ", "headerClass": "co-chu-thich",
         "headerTooltip": GOI_Y_MOC.format(han=han), "minWidth": 118, "maxWidth": 130,
         "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": list(nt.LOAI_MOC.values())}, **sua},
        {"field": "ngay_moc", "headerName": "Ngày mốc *", "minWidth": 96, "maxWidth": 110,
         "cellEditor": "agDateStringCellEditor", "valueFormatter": NGAY_DM, **sua},
        {"field": "canh_bao", "headerName": "Cảnh báo", "minWidth": 170, "flex": 1.3, "wrapText": True,
         "autoHeight": True, "cellStyle": MAU_CANH_BAO},
        {"field": "phuong_an", "headerName": "Phương án *", "minWidth": 170, "maxWidth": 200,
         "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": pa},
         "editable": {"function": SUA}, "cellClassRules": {**THIEU, **MAU_PA}},
        {"field": "cap_nhat", "headerName": "Cập nhật", "minWidth": 110, "maxWidth": 150,
         "tooltipField": "cap_nhat_boi",
         "headerTooltip": "Lần sửa gần nhất và người sửa.\nGiờ hôm nay, hoặc ngày giờ nếu sửa hôm khác."},
    ]


def layout():
    ds = current_user.phong_nhap_ton()
    if not ds:
        return alert("Tài khoản này không dùng mục Nhập tồn.", "bad")
    nt.dam_bao_bang()
    ch = nt.cau_hinh()
    ten = {p["code"]: p["ten"] for p in phong_order()}
    xem_tong = current_user.role != "nvkd"
    return html.Div([
        html.Div([
            html.Div(field("Phòng", dcc.Dropdown(id="nt-phong", options=[{"label": ten.get(c, c), "value": c}
                                                                          for c in ds],
                                                 value=ds[0], clearable=False, style={"width": "150px"})),
                     style={} if len(ds) > 1 else AN),
            field("Nhân viên", dcc.Dropdown(id="nt-nv", value="all", clearable=False, persistence=True,
                                            persistence_type="local", style={"minWidth": "260px"})),
            field("Xem", seg_control("nt-nhanh", NHANH, "all")),
            field("Tìm", dcc.Input(id="nt-tim", type="search", placeholder="Mã HĐ hoặc tên KH", className="o-tim",
                                   debounce=True)),
            html.Div(className="grow"),
            field(" ", html.Button([icon("download", 14), html.Span("Excel")], id="nt-xls", className="btn",
                                   title="Xuất đúng danh sách đang lọc", style={} if xem_tong else AN)),
        ], className="toolbar loc-trang"),
        dcc.Download(id="nt-tai"),
        dcc.Store(id="nt-da-luu"),
        html.Div(id="nt-msg"),
        html.Div(id="nt-kpi", className="kpi-row kpi-4"),

        html.Div([
            html.Div([html.H3("Theo nhân viên", style={"margin": 0}),
                      tip("Bấm một người để xem riêng ca của người đó. Không tính ca đã chọn Huỷ vào các cột cảnh báo.")],
                     className="the-thanh"),
            bang("nt-tong", [
                {"field": "ho_ten", "headerName": "Nhân viên", "minWidth": 170, "flex": 1.6, "cellClass": "o-bam"},
                {"field": "acc", "headerName": "Acc", "minWidth": 120, "flex": 1},
                *[{"field": f, "headerName": t, "type": "numericColumn", "minWidth": 90, "flex": 0.8,
                   "valueFormatter": SO, **({"cellStyle": _nen(mau)} if mau else {})}
                  for f, t, mau in (("ton", "Tồn", ""), ("chua_cap_nhat", "Chưa cập nhật", "#FDF3E3"),
                                    ("tra_ve", "Trả về", "#FCEDEC"), ("qua_hen", "Quá hẹn", "#FCEDEC"),
                                    ("den_han", "Đến hạn hôm nay", "#FDF3E3"), ("huy", "Huỷ", ""))],
            ], cao=300, tuy_chon={"rowSelection": {"mode": "singleRow", "checkboxes": False,
                                                   "enableClickSelection": True}}),
            html.Div("Bấm một dòng để lọc theo nhân viên đó.", className="goi-y-bam"),
        ], className="card"),

        html.Div([
            html.Div([html.H3("Danh sách hợp đồng tồn", style={"margin": 0}),
                      html.Div(id="nt-mo-ta", className="desc", style={"margin": "2px 0 0"})], className="the-thanh"),
            html.Div(bang("nt-luoi", _cot(ch["han_tra_ve"], ch["phuong_an"]), cao=640,
                          lop="ag-theme-quartz ag-theme-ftel luoi-ke",
                          cot_mac_dinh={"resizable": True, "sortable": False, "suppressMovable": True,
                                        "wrapHeaderText": True},
                          getRowId="params.data.id",
                          tuy_chon={"suppressCellFocus": False, "singleClickEdit": True,
                                    "stopEditingWhenCellsLoseFocus": True, "enableCellTextSelection": True,
                                    "rowClassRules": {"dong-nhom": NHOM, "dong-huy": "params.data.muc == 'huy'"}}),
                     className="nt-laptop"),
            html.Div(id="nt-the", className="nt-dien-thoai"),
            html.Div("Bấm vào ô để sửa, sửa xong tự lưu. Ô có viền cam là mục bắt buộc chưa điền.",
                     className="goi-y-bam nt-laptop"),
        ], className="card"),

        _nap_sheet() if xem_tong else None,
        modal("nt-md", html.Span(id="nt-md-tieu-de"), [
            dcc.Store(id="nt-md-hd"),
            html.Div(id="nt-md-dau", className="desc"),
            html.Div([
                html.Div([html.Label("Ghi chú tình trạng *"),
                          dcc.Textarea(id="nt-f-ghi-chu", className="inp", maxLength=nt.GHI_CHU_TOI_DA,
                                       placeholder=GOI_Y_GHI_CHU, style={"width": "100%", "minHeight": "90px"})],
                         className="field rong"),
                html.Div([html.Label("Mốc tick hẹn (PTC) *"),
                          seg_control("nt-f-loai", list(nt.LOAI_MOC.items()), "hen")], className="field rong"),
                html.Div([html.Label("Ngày mốc *"), dcc.Input(id="nt-f-ngay", type="date", className="inp")],
                         className="field rong"),
                html.Div([html.Label("Phương án *"),
                          dcc.Dropdown(id="nt-f-pa", options=ch["phuong_an"], searchable=False,
                                       placeholder="Chọn phương án")], className="field rong"),
            ], className="form-grid"),
            html.Div(GOI_Y_MOC.format(han=ch["han_tra_ve"]), className="desc", style={"whiteSpace": "pre-line"}),
            html.Div(id="nt-md-msg"),
        ]),
    ])


def _nen(mau: str) -> dict:
    return {"styleConditions": [{"condition": "params.value > 0", "style": {"backgroundColor": mau,
                                                                            "fontWeight": "650"}}]}


def _nap_sheet():
    return html.Details([
        html.Summary("Nạp ghi chú từ Google Sheet cũ (một lần khi chuyển sang app)", className="cg-tieu-de"),
        html.Div("File .csv hoặc .xlsx có các cột Hợp đồng, Ghi chú tình trạng, Mốc tick hẹn, Chốt / Phương án. "
                 "Chỉ nạp hợp đồng còn tồn. Hợp đồng đã ghi trên app thì giữ bản trên app. Mốc không rõ kiểu "
                 "(treo, cptc...) được chép vào ghi chú để sale chọn lại.", className="desc"),
        dcc.Upload(id="nt-file", className="upload-zone", accept=".csv,.xlsx",
                   children=html.Div([icon("upload", 18), html.Span(" Kéo thả hoặc bấm chọn file")])),
        dcc.Loading(html.Div(id="nt-file-msg"), type="dot"),
    ], className="chu-giai card")


# ------------------------------------------------------------------ dựng nội dung
def _dong_luoi(df: pd.DataFrame) -> list[dict]:
    """Chèn một dòng tiêu đề trước mỗi cụm nhân viên (bảng không nhóm được dòng)."""
    if df.empty:
        return []
    ds = df.assign(loai_moc=df.loai_moc.map(nt.LOAI_MOC).fillna(""), so_ngay_cho=df.so_ngay_cho.astype(int))
    tong = nt.tong_hop_nv(ds).set_index("acc_norm")
    out = []
    for acc, g in ds.groupby("acc_norm", sort=False):
        t = tong.loc[acc]
        out.append({"id": f"nhom-{acc}", "loai_dong": "nhom", "hop_dong": f"{t.ho_ten} · {t.acc} · {_tom_tat(t)}"})
        out.extend(g.drop(columns=["thieu"]).to_dict("records"))
    return out


def _tom_tat(t) -> str:
    phan = [f"{int(t.ton)} ca"]
    if t.gap:
        phan.append(f"{int(t.gap)} cần xử lý gấp")
    if t.den_han:
        phan.append(f"{int(t.den_han)} đến hạn hôm nay")
    if t.chua_cap_nhat:
        phan.append(f"{int(t.chua_cap_nhat)} chưa cập nhật")
    return " · ".join(phan)


def _the(df: pd.DataFrame) -> list:
    """Dạng thẻ cho điện thoại."""
    if df.empty:
        return [html.Div("Không có hợp đồng nào khớp bộ lọc.", className="desc")]
    tong, out = nt.tong_hop_nv(df).set_index("acc_norm"), []
    for acc, g in df.groupby("acc_norm", sort=False):
        t = tong.loc[acc]
        out.append(html.Div([html.B(t.ho_ten), html.Span(f" · {_tom_tat(t)}")], className="nt-nhom"))
        for r in g.itertuples():
            the = html.Button if r.sua_duoc else html.Div
            out.append(the([
                html.Div([html.B(r.hop_dong), html.Span(r.ten_khach_hang), html.Div(className="grow"),
                          html.Span(r.phuong_an or "Chưa chọn phương án",
                                    className=f"pa {_lop_pa(r.phuong_an)}")], className="nt-the-dau"),
                html.Div(r.ghi_chu or "Chưa ghi chú tình trạng", className="nt-the-gc" + ("" if r.ghi_chu else " thieu")),
                html.Div([html.Span(f"Tạo {r.ngay_tao_hd[8:10]}/{r.ngay_tao_hd[5:7]} · chờ {int(r.so_ngay_cho)} ngày"),
                          html.Span(_moc_chu(r), className="nt-moc"),
                          html.Span(r.canh_bao, className=f"nt-cb {r.muc}") if r.canh_bao else None],
                         className="nt-the-chan"),
            ], **({"id": {"type": "nt-the", "hd": r.hop_dong}, "n_clicks": 0} if r.sua_duoc else {}),
                className=f"nt-the {r.muc}" + (" thieu" if r.thieu else "") + ("" if r.sua_duoc else " chi-xem")))
    return out


def _lop_pa(pa) -> str:
    return {"Đang chờ triển khai": "pa-cho", "Huỷ": "pa-huy", "KH đang suy nghĩ - Chốt lại": "pa-suy-nghi",
            "Đã triển khai": "pa-xong"}.get(pa or "", "pa-trong")


def _moc_chu(r) -> str:
    if not r.loai_moc or not r.ngay_moc:
        return "Chưa có mốc"
    return f"{nt.LOAI_MOC.get(r.loai_moc, r.loai_moc)} {r.ngay_moc[8:10]}/{r.ngay_moc[5:7]}"


def _kpi(d: dict) -> list:
    return [kpi("Tổng tồn", f"{d['ton']:,}".replace(",", "."), f"{d['huy']} ca đã chọn Huỷ" if d["huy"] else None),
            kpi("Chưa cập nhật", d["chua_cap_nhat"], "Thiếu ghi chú, mốc hoặc phương án",
                "warn" if d["chua_cap_nhat"] else "ok"),
            kpi("Cần xử lý gấp", d["gap"], f"Trả về {d['tra_ve']} · Quá hẹn {d['qua_hen']}",
                "bad" if d["gap"] else "ok"),
            kpi("Đến hạn hôm nay", d["den_han"], "Hẹn thi công đúng hôm nay", "warn" if d["den_han"] else "")]


# ------------------------------------------------------------------ callbacks
def register(app):
    @app.callback(Output("nt-nv", "options"), Output("nt-kpi", "children"), Output("nt-tong", "rowData"),
                  Output("nt-luoi", "rowData"), Output("nt-the", "children"), Output("nt-mo-ta", "children"),
                  Input("nt-phong", "value"), Input("nt-nv", "value"), Input("nt-nhanh", "value"),
                  Input("nt-tim", "value"), Input("nt-da-luu", "data"), State("ui-vw", "data"))
    def _nap(code, acc, nhanh, tim, _luu, vw):
        df = nt.danh_sach(_phong_hop_le(code))
        if df.empty:
            return [{"label": "Tất cả nhân viên", "value": "all"}], _kpi(nt.dem(df)), [], [], [], \
                "Phòng chưa có hợp đồng tồn (hoặc chưa nạp file Internet)."
        tong = nt.tong_hop_nv(df)
        chon = [{"label": "Tất cả nhân viên", "value": "all"}] + [
            {"label": f"{r.ho_ten} ({r.acc}) · {int(r.ton)} ca", "value": r.acc_norm} for r in tong.itertuples()]
        acc = acc if acc in set(tong.acc_norm) else "all"
        xem = nt.loc(df, acc, nhanh, tim)
        xem = xem.assign(sua_duoc=not _dung_chung() or acc != "all")
        dien_thoai = (vw or {}).get("w", 1440) < 768
        mo_ta = f"{len(xem)} / {len(df)} hợp đồng. Số tồn tính theo file Internet mới nhất đã nạp."
        if _dung_chung() and acc == "all":
            mo_ta = html.Span([html.B(CHON_TEN, style={"color": "#B42318"}), " ", mo_ta])
        return (chon, _kpi(nt.dem(nt.loc(df, acc))), tong.to_dict("records"),
                [] if dien_thoai else _dong_luoi(xem), _the(xem) if dien_thoai else [], mo_ta)

    @app.callback(Output("nt-nv", "value"), Input("nt-tong", "selectedRows"), prevent_initial_call=True)
    def _chon_nv(chon):
        if not chon:
            raise PreventUpdate
        return chon[0]["acc_norm"]

    @app.callback(Output("nt-da-luu", "data"), Output("nt-msg", "children"),
                  Input("nt-luoi", "cellValueChanged"), State("nt-phong", "value"), State("nt-nv", "value"),
                  prevent_initial_call=True)
    def _luu_o(doi, code, acc):
        phong = _phong_hop_le(code)
        doi = doi if isinstance(doi, list) else [doi] if doi else []
        loi = []
        for d in doi:
            r, cot = d.get("data") or {}, d.get("colId")
            if r.get("loai_dong") == "nhom" or cot not in ("ghi_chu", "loai_moc", "ngay_moc", "phuong_an"):
                continue
            try:
                nt.luu(r.get("hop_dong"), {cot: d.get("value")}, phong, current_user.username, *_nguoi_ghi(acc))
            except nt.LoiNhapTon as e:
                loi.append(str(e))
        return gio_viet_nam().isoformat(), alert(" ".join(loi), "bad") if loi else None

    @app.callback(Output("nt-md", "className"), Output("nt-md-tieu-de", "children"), Output("nt-md-hd", "data"),
                  Output("nt-md-dau", "children"), Output("nt-f-ghi-chu", "value"), Output("nt-f-loai", "value"),
                  Output("nt-f-ngay", "value"), Output("nt-f-pa", "value"), Output("nt-md-msg", "children"),
                  Input({"type": "nt-the", "hd": ALL}, "n_clicks"), Input("nt-md-dong", "n_clicks"),
                  Input("nt-md-huy", "n_clicks"), Input("nt-da-luu", "data"), State("nt-phong", "value"),
                  prevent_initial_call=True)
    def _mo_form(bam, _d, _h, _l, code):
        t = ctx.triggered_id
        if not isinstance(t, dict):
            return ("modal",) + (no_update,) * 8
        if not any(bam or []):
            raise PreventUpdate
        df = nt.danh_sach(_phong_hop_le(code))
        r = df[df.hop_dong == t["hd"]]
        if r.empty:
            raise PreventUpdate
        r = r.iloc[0]
        dau = f"{r.ten_khach_hang or 'Khách hàng'} · {r.ho_ten} · tạo {r.ngay_tao_hd[8:10]}/{r.ngay_tao_hd[5:7]}"
        return ("modal mo", f"Cập nhật {r.hop_dong}", r.hop_dong, dau, r.ghi_chu, r.loai_moc or "hen",
                r.ngay_moc or None, r.phuong_an or None, "")

    @app.callback(Output("nt-md-msg", "children", allow_duplicate=True),
                  Output("nt-da-luu", "data", allow_duplicate=True),
                  Input("nt-md-ok", "n_clicks"), State("nt-md-hd", "data"), State("nt-f-ghi-chu", "value"),
                  State("nt-f-loai", "value"), State("nt-f-ngay", "value"), State("nt-f-pa", "value"),
                  State("nt-phong", "value"), State("nt-nv", "value"), prevent_initial_call=True)
    def _luu_form(_n, hd, ghi_chu, loai, ngay, pa, code, acc):
        phong = _phong_hop_le(code)
        thieu = [ten for ten, v in (("Ghi chú tình trạng", (ghi_chu or "").strip()), ("Mốc tick", loai),
                                    ("Ngày mốc", ngay), ("Phương án", pa)) if not v]
        if thieu:
            return alert("Chưa điền: " + ", ".join(thieu) + ".", "bad"), no_update
        try:
            nt.luu(hd, {"ghi_chu": ghi_chu, "loai_moc": loai, "ngay_moc": ngay, "phuong_an": pa}, phong,
                   current_user.username, *_nguoi_ghi(acc))
        except nt.LoiNhapTon as e:
            return alert(str(e), "bad"), no_update
        return "", gio_viet_nam().isoformat()

    @app.callback(Output("nt-tai", "data"), Input("nt-xls", "n_clicks"), State("nt-phong", "value"),
                  State("nt-nv", "value"), State("nt-nhanh", "value"), State("nt-tim", "value"),
                  prevent_initial_call=True)
    def _excel(_n, code, acc, nhanh, tim):
        if current_user.role == "nvkd":
            raise PreventUpdate
        xem = nt.loc(nt.danh_sach(_phong_hop_le(code)), acc, nhanh, tim)
        ghi_log("xuat_excel_nhap_ton", f"{code}: {len(xem)} dòng")
        ten = f"NhapTon_{code}_{gio_viet_nam():%Y%m%d_%H%M}.xlsx"
        return dcc.send_data_frame(nt.file_excel(xem).to_excel, ten, index=False, sheet_name="Nhap ton")

    @app.callback(Output("nt-file-msg", "children"), Output("nt-da-luu", "data", allow_duplicate=True),
                  Input("nt-file", "contents"), State("nt-file", "filename"), State("nt-phong", "value"),
                  prevent_initial_call=True)
    def _nap_file(noi_dung, ten, code):
        if not noi_dung or current_user.role == "nvkd":
            raise PreventUpdate
        try:
            kq = nt.nap_sheet(base64.b64decode(noi_dung.split(",", 1)[1]), ten or "", _phong_hop_le(code),
                              current_user.username)
        except (nt.LoiNhapTon, ValueError, UnicodeDecodeError) as e:
            return alert(f"Không đọc được file: {e}", "bad"), no_update
        chu = (f"Đã nạp {kq['da_nap']} hợp đồng. Giữ nguyên {kq['da_co']} hợp đồng đã ghi trên app. "
               f"Bỏ qua {kq['khong_ton']} hợp đồng không còn tồn. "
               f"{kq['moc_vao_ghi_chu']} mốc không rõ kiểu đã chép vào ghi chú, sale cần chọn lại mốc.")
        return alert(chu, "ok"), gio_viet_nam().isoformat()
