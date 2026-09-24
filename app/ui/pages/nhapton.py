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
from app.ui.components import alert, field, modal, seg_control, tip
from app.ui.icons import icon
from app.ui.luoi import PCT, SO, bang

TAT_CA = "Tất cả nhân viên"
TEN_LOC = {"all": "", "gap": "Cần xử lý gấp", "den_han": "Đến hạn hôm nay", "thieu": "Chưa cập nhật"}
AN = {"display": "none"}
NHOM = "params.data.loai_dong == 'nhom'"
LA_CA = "params.data.loai_dong != 'nhom'"
SUA = f"{LA_CA} && params.data.sua_duoc"
NGAY_DM = {"function": "params.value ? params.value.slice(8, 10) + '/' + params.value.slice(5, 7) : ''"}
THIEU = {"o-thieu": f"{LA_CA} && params.data.muc != 'huy' && !params.value"}
MAU_CANH_BAO = {"styleConditions": [
    {"condition": "params.data.muc == 'do'", "style": {"color": "#B42318", "fontWeight": "650"}},
    {"condition": "params.data.muc == 'vang'", "style": {"color": "#8A5A00", "fontWeight": "650"}}]}
MAU_NV = {"styleConditions": [{"condition": "params.value > 0", "style": {"color": "#B42318",
                                                                             "fontWeight": "700"}}]}
MAU_VANG = {"styleConditions": [{"condition": "params.value > 0", "style": {"color": "#8A5A00",
                                                                           "fontWeight": "700"}}]}
MAU_XONG = {"styleConditions": [{"condition": "params.value >= 100", "style": {"color": "#0A7A3E",
                                                                              "fontWeight": "700"}}]}
OPTS_NV = {"rowSelection": {"mode": "singleRow", "checkboxes": False, "enableClickSelection": True},
           "suppressCellFocus": True}
MAU_PA = {"pa-cho": "params.value == 'Đang chờ triển khai'", "pa-huy": "params.value == 'Huỷ'",
          "pa-suy-nghi": "params.value == 'KH đang suy nghĩ - Chốt lại'", "pa-xong": "params.value == 'Đã triển khai'"}
GOI_Y_GHI_CHU = "Nguyên nhân tồn + thời gian hẹn thực tế. Treo, CPTC... cũng ghi ở đây."
GHI_TEN = "Tick tên mình ở ô Nhân viên để phần \"cập nhật bởi\" ghi đúng tên."
NHAN_O_NV = {"select_all": "Chọn tất cả", "deselect_all": "Bỏ chọn tất cả", "search": "Tìm tên...",
             "selected_count": "{num_selected} người", "clear_search": "Xoá tìm", "clear_selection": "Bỏ chọn",
             "no_options_found": "Không có tên nào khớp"}
GOI_Y_MOC = ("Mốc đang hiển thị trên PTC.\nHẹn thi công: quá ngày mà chưa online thì báo đỏ, đúng hôm nay báo vàng.\n"
             "Trả về: điền ngày bị trả về. Quá {han} ngày không xử lý thì HĐ tự huỷ nên luôn báo đỏ.")


def topbar():
    return [html.Div([html.H1("Nhập tồn"),
                      html.Div("Tình trạng từng hợp đồng chưa online, sale cập nhật mỗi ngày", className="sub")])]


def _dung_chung() -> bool:
    """Tài khoản dùng chung của phòng: phải chọn tên mình mới sửa được (chốt 21/09/2026)."""
    return current_user.role == "nvkd"


def _nguoi_ghi(acc) -> tuple[str | None, str | None]:
    """(chỉ được sửa ca của acc nào, tên ghi vào "cập nhật bởi").

    Tài khoản sale dùng chung được sửa mọi ca (chủ app chốt 24/09/2026) nên không chặn ai; chỉ khi đang
    tick đúng một tên thì ghi tên người đó vào "cập nhật bởi" cho Trưởng phòng biết ai vừa sửa."""
    ds = _ds_acc(acc)
    if not _dung_chung() or len(ds) != 1:
        return None, None
    return None, nt.ten_cua(ds[0]) or ds[0]


def _ds_acc(acc) -> list[str]:
    """Giá trị ô Nhân viên (chọn nhiều) -> danh sách acc; rỗng = mọi người."""
    return [a for a in ([acc] if isinstance(acc, str) else acc or []) if a and a != "all"]


def _phong_hop_le(code) -> list[str]:
    ds = current_user.phong_nhap_ton() if current_user.is_authenticated else []
    if code not in ds:
        raise PreventUpdate
    return [code]


def _cot(han: int, pa: list[str]) -> list[dict]:
    """4 cột sale phải điền mang lớp `o-sale` (nền kem, có vạch ngăn với phần hệ thống tự lấy)."""
    sua = {"editable": {"function": SUA}, "cellClass": "o-sale", "cellClassRules": THIEU}
    return [
        {"field": "hop_dong", "headerName": "Hợp đồng", "pinned": "left", "width": 114, "minWidth": 114,
         "maxWidth": 126, "cellClass": "o-dam"},
        {"field": "ten_khach_hang", "headerName": "Tên khách hàng", "minWidth": 130, "flex": 1.5,
         "tooltipField": "ten_khach_hang", "colSpan": {"function": f"{NHOM} ? 20 : 1"}},
        {"field": "ngay_tao_hd", "headerName": "Ngày tạo", "width": 74, "minWidth": 74, "maxWidth": 82,
         "valueFormatter": NGAY_DM, "headerTooltip": "Ngày tạo hợp đồng."},
        {"field": "so_ngay_cho", "headerName": "Chờ", "width": 54, "minWidth": 54, "maxWidth": 62,
         "type": "numericColumn", "valueFormatter": SO,
         "headerTooltip": "Số ngày từ ngày tạo HĐ đến ngày có số mới nhất."},
        {"field": "canh_bao", "headerName": "Cảnh báo", "minWidth": 96, "flex": .7, "wrapText": True,
         "autoHeight": True, "cellStyle": MAU_CANH_BAO},
        {"field": "ghi_chu", "headerName": "Ghi chú tình trạng * ⓘ", "headerClass": "co-chu-thich vung-sale",
         "headerTooltip": GOI_Y_GHI_CHU, "minWidth": 170, "flex": 2.2, "wrapText": True, "autoHeight": True,
         "cellEditor": "agLargeTextCellEditor", "cellEditorPopup": True,
         "cellEditorParams": {"maxLength": nt.GHI_CHU_TOI_DA, "rows": 5, "cols": 50}, **sua},
        {"field": "loai_moc", "headerName": "Mốc tick (PTC) * ⓘ", "headerClass": "co-chu-thich",
         "headerTooltip": GOI_Y_MOC.format(han=han), "width": 106, "minWidth": 106, "maxWidth": 126,
         "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": list(nt.LOAI_MOC.values())}, **sua},
        {"field": "ngay_moc", "headerName": "Ngày mốc *", "width": 84, "minWidth": 84, "maxWidth": 100,
         "cellEditor": "agDateStringCellEditor", "valueFormatter": NGAY_DM, **sua},
        {"field": "phuong_an", "headerName": "Phương án *", "width": 140, "minWidth": 140, "maxWidth": 180,
         "wrapText": True, "autoHeight": True,
         "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": pa},
         "editable": {"function": SUA}, "cellClass": "o-sale",
         "cellClassRules": {**THIEU, **MAU_PA}},
        {"field": "cap_nhat", "headerName": "Cập nhật", "width": 86, "minWidth": 86, "maxWidth": 130,
         "wrapText": True, "autoHeight": True, "tooltipField": "cap_nhat_boi",
         "headerTooltip": "Lần sửa gần nhất và người sửa.\nGiờ hôm nay, hoặc ngày giờ nếu sửa hôm khác."},
    ]


def _cot_nv() -> list[dict]:
    """Bảng tổng quan: mỗi nhân viên một dòng, dòng ghim cuối là cả phòng."""
    so = {"type": "numericColumn", "valueFormatter": SO, "width": 104, "minWidth": 88, "maxWidth": 130}
    return [
        {"field": "ho_ten", "headerName": "Nhân viên", "minWidth": 160, "flex": 1.2, "cellClass": "o-dam o-bam"},
        {"field": "acc", "headerName": "Acc", "minWidth": 128, "flex": 1},
        {"field": "ton", "headerName": "Tổng tồn", **so, "cellStyle": {"fontWeight": "700"}},
        {"field": "gap", "headerName": "Cần xử lý gấp", **so, "cellStyle": MAU_NV,
         "headerTooltip": "Hợp đồng bị trả về, hoặc đã quá ngày hẹn thi công."},
        {"field": "den_han", "headerName": "Đến hạn hôm nay", **so, "cellStyle": MAU_VANG,
         "headerTooltip": "Hẹn thi công đúng hôm nay."},
        {"field": "chua_cap_nhat", "headerName": "Chưa cập nhật", **so, "cellStyle": MAU_VANG,
         "headerTooltip": "Còn thiếu ghi chú, mốc hoặc phương án."},
        {"field": "pct", "headerName": "Đã cập nhật", **so, "valueFormatter": PCT, "cellStyle": MAU_XONG,
         "headerTooltip": "Phần trăm ca đã điền đủ 3 mục bắt buộc.\nCa đã chọn Huỷ tính là xong."},
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
        ], className="toolbar loc-trang", style={} if len(ds) > 1 else AN),
        dcc.Download(id="nt-tai"),
        dcc.Store(id="nt-da-luu"),
        dcc.Store(id="nt-nhanh", data="all"),
        html.Div(id="nt-msg"),
        html.Div(id="nt-pham-vi", className="nt-pham-vi"),
        html.Div(id="nt-kpi", className="kpi-row kpi-4"),

        html.Div([
            html.Div([html.H3("Theo nhân viên", style={"margin": 0}),
                      html.Div("Người còn nhiều việc xếp lên đầu. Dòng cuối là cả phòng. "
                               "Bấm tiêu đề cột để xếp lại.",
                               className="desc", style={"margin": "2px 0 0"})],
                     className="the-thanh"),
            bang("nt-nv-luoi", _cot_nv(), cao=356, lop="ag-theme-quartz ag-theme-ftel luoi-ke",
                 cot_mac_dinh={"resizable": True, "sortable": True, "suppressMovable": True,
                               "wrapHeaderText": True, "autoHeaderHeight": True},
                 tuy_chon=dict(OPTS_NV)),
            html.Div("Bấm một dòng để xem riêng ca của người đó ở danh sách bên dưới.", className="goi-y-bam"),
        ], className="card nt-laptop"),           # điện thoại: mỗi cụm thẻ đã có dòng tóm tắt của nhân viên

        html.Div([
            html.Div([
                # tick nhiều người; rỗng = tất cả. Chỉ gửi lọc khi đóng ô (tick xong mới tải lại một lần).
                # Ô nhớ lựa chọn trên máy: sale tick tên mình một lần, lần sau mở là đúng tên.
                field("Nhân viên", dcc.Dropdown(
                    id="nt-nv", value=[], multi=True, closeOnSelect=False, debounce=True, search_order="original",
                    maxHeight=380, placeholder=TAT_CA, labels=NHAN_O_NV, persistence=True,
                    persistence_type="local", className="nt-o-nv")),
                field("Tìm", dcc.Input(id="nt-tim", type="search", placeholder="Mã HĐ hoặc tên KH",
                                       className="o-tim", debounce=True)),
                html.Button([icon("download", 14), html.Span("Excel")], id="nt-xls", className="btn nt-nut",
                            title="Xuất đúng danh sách đang lọc", style={} if xem_tong else AN),
            ], className="toolbar nt-loc"),
            html.Div([html.H3(id="nt-tieu-de-ds", style={"margin": 0}),
                      html.Div(id="nt-mo-ta", className="desc", style={"margin": "2px 0 0"})], className="the-thanh"),
            html.Div(bang("nt-luoi", _cot(ch["han_tra_ve"], ch["phuong_an"]), cao=640,
                          lop="ag-theme-quartz ag-theme-ftel luoi-ke",
                          cot_mac_dinh={"resizable": True, "sortable": False, "suppressMovable": True,
                                        "wrapHeaderText": True},
                          getRowId="params.data.id",
                          tuy_chon={"suppressCellFocus": False, "singleClickEdit": True,
                                    "stopEditingWhenCellsLoseFocus": True, "enableCellTextSelection": True,
                                    "rowClassRules": {"dong-nhom": NHOM, "dong-huy": "params.data.muc == 'huy'",
                                                      "dong-do": f"{LA_CA} && params.data.muc == 'do'",
                                                      "dong-vang": f"{LA_CA} && params.data.muc == 'vang'"}}),
                     className="nt-laptop"),
            html.Div(id="nt-the", className="nt-dien-thoai"),
            html.Div("Bấm vào ô để sửa, sửa xong tự lưu. Nhấn Tab để nhảy sang ô kế tiếp: "
                     "ghi chú → mốc → ngày → phương án, không cần dùng chuột. "
                     "Ô viền cam là mục bắt buộc chưa điền.",
                     className="goi-y-bam nt-laptop"),
        ], className="card"),

        _nap_sheet() if xem_tong else None,
        modal("nt-md", html.Span(id="nt-md-tieu-de"), [
            dcc.Store(id="nt-md-hd"),
            html.Div(id="nt-md-dau", className="desc", style={"margin": "0 0 14px"}),
            html.Div([
                html.Div([html.Label("Ghi chú tình trạng *"),
                          dcc.Textarea(id="nt-f-ghi-chu", className="inp", maxLength=nt.GHI_CHU_TOI_DA,
                                       placeholder=GOI_Y_GHI_CHU, style={"width": "100%", "minHeight": "90px"})],
                         className="field rong"),
                html.Div([html.Label(["Mốc tick hẹn (PTC) *", tip(GOI_Y_MOC.format(han=ch["han_tra_ve"]))]),
                          seg_control("nt-f-loai", list(nt.LOAI_MOC.items()), "hen")], className="field rong"),
                html.Div([html.Label("Ngày mốc *"), dcc.Input(id="nt-f-ngay", type="date", className="inp")],
                         className="field rong"),
                html.Div([html.Label("Phương án *"),
                          dcc.Dropdown(id="nt-f-pa", options=ch["phuong_an"], searchable=False,
                                       placeholder="Chọn phương án")], className="field rong"),
            ], className="form-grid"),
            html.Div(id="nt-md-msg"),
        ]),
    ])


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
def _dong_luoi(df: pd.DataFrame, nhom: bool = True) -> list[dict]:
    """Chèn một dòng tiêu đề trước mỗi cụm nhân viên (bảng không nhóm được dòng). Đang xem đúng một người
    thì bỏ dòng tiêu đề - tên và số ca đã nằm ở tiêu đề thẻ."""
    if df.empty:
        return []
    if not nhom:
        return df.assign(loai_moc=df.loai_moc.map(nt.LOAI_MOC).fillna(""),
                         so_ngay_cho=df.so_ngay_cho.astype(int)).drop(columns=["thieu"]).to_dict("records")
    ds = df.assign(loai_moc=df.loai_moc.map(nt.LOAI_MOC).fillna(""), so_ngay_cho=df.so_ngay_cho.astype(int))
    tong = nt.tong_hop_nv(ds).set_index("acc_norm")
    out = []
    for acc, g in ds.groupby("acc_norm", sort=False):
        t = tong.loc[acc]
        out.append({"id": f"nhom-{acc}", "loai_dong": "nhom", "hop_dong": f"{int(t.ton)} ca",
                    "ten_khach_hang": f"{t.ho_ten} · {t.acc} · {_tom_tat(t, ton=False)}"})
        out.extend(g.drop(columns=["thieu"]).to_dict("records"))
    return out


def _tom_tat(t, ton: bool = True) -> str:
    phan = [f"{int(t.ton)} ca"] if ton else []
    if t.gap:
        phan.append(f"{int(t.gap)} cần xử lý gấp")
    if t.den_han:
        phan.append(f"{int(t.den_han)} đến hạn hôm nay")
    if t.chua_cap_nhat:
        phan.append(f"{int(t.chua_cap_nhat)} chưa cập nhật")
    return " · ".join(phan) if phan else "đã cập nhật đủ"


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


def _kpi(d: dict, nhanh: str, ai: str = "cả phòng") -> list:
    """4 ô số cũng là 4 nút lọc: bấm ô nào thì danh sách chỉ còn các ca đó, bấm lại ô Tổng tồn để xem hết.

    `ai`: 4 ô đếm theo ô Nhân viên đang tick, nên phải ghi rõ đang là cả phòng hay của ai."""
    goi_y = " · ".join(x for x in (f"Tất cả ca của {ai}", f"{d['huy']} đã chọn Huỷ" if d["huy"] else "") if x)
    o = [("all", "Tổng tồn", d["ton"], goi_y, ""),
         ("gap", "Cần xử lý gấp", d["gap"], f"Trả về {d['tra_ve']} · Quá hẹn {d['qua_hen']}",
          "bad" if d["gap"] else "ok"),
         ("den_han", "Đến hạn hôm nay", d["den_han"], "Hẹn thi công đúng hôm nay", "warn" if d["den_han"] else ""),
         ("thieu", "Chưa cập nhật", d["chua_cap_nhat"], "Thiếu ghi chú, mốc hoặc phương án",
          "warn" if d["chua_cap_nhat"] else "ok")]
    return [html.Button([html.Div(nhan, className="label"), html.Div(f"{so:,}".replace(",", "."), className="value"),
                         html.Div(goi_y, className="hint")],
                        id={"type": "nt-loc", "v": v}, n_clicks=0, title="Bấm để lọc danh sách",
                        className=f"kpi kpi-bam {mau}" + (" dang-chon" if v == nhanh else ""))
            for v, nhan, so, goi_y, mau in o]


def _nhan_nv(r) -> str:
    """Một dòng trong ô Nhân viên: họ tên (tìm được theo tên) + số ca, số gấp, số chưa cập nhật."""
    phan = [f"{int(r.ton)} ca"]
    if r.gap:
        phan.append(f"{int(r.gap)} gấp")
    if r.chua_cap_nhat:
        phan.append(f"{int(r.chua_cap_nhat)} chưa cập nhật")
    return f"{r.ho_ten} · " + " · ".join(phan)


def _pham_vi(tong: pd.DataFrame, chon: list[str]) -> list:
    """Nói rõ 4 ô số đang đếm cho ai - nếu không, tick một người xong thì "Tổng tồn 16" đọc ra như cả phòng."""
    if not chon:
        return ["Bốn ô dưới đây là số của ", html.B("cả phòng"),
                f" · {len(tong)} nhân viên · {int(tong.ton.sum())} ca."]
    return ["Bốn ô dưới đây chỉ là số của ", html.B(_tieu_de(tong, chon)),
            ". Bỏ tick ở ô Nhân viên để xem lại cả phòng."]


def _dong_nv(tong: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """(mỗi nhân viên một dòng, dòng ghim "Cả phòng"). `pct` = % ca đã điền đủ 3 mục.
    Xếp người còn nhiều việc lên đầu: gấp -> chưa cập nhật -> tồn nhiều."""
    cot = ["acc_norm", "ho_ten", "acc", "ton", "gap", "den_han", "chua_cap_nhat"]
    if tong.empty:
        return [], []
    tong = tong.sort_values(["gap", "chua_cap_nhat", "ton"], ascending=False)
    ds = [{**{c: (r[c] if c in ("acc_norm", "ho_ten", "acc") else int(r[c])) for c in cot},
           "pct": round(100 * (r["ton"] - r["chua_cap_nhat"]) / r["ton"]) if r["ton"] else 100}
          for r in tong.to_dict("records")]
    t = {c: int(tong[c].sum()) for c in ("ton", "gap", "den_han", "chua_cap_nhat")}
    t["pct"] = round(100 * (t["ton"] - t["chua_cap_nhat"]) / t["ton"]) if t["ton"] else 100
    return ds, [{"ho_ten": "Cả phòng", "acc": f"{len(tong)} nhân viên", **t}]


def _tieu_de(tong: pd.DataFrame, chon: list[str]) -> str:
    if not chon:
        return TAT_CA
    ten = tong.set_index("acc_norm").ho_ten
    return ", ".join(ten[a] for a in chon) if len(chon) <= 3 else f"{len(chon)} nhân viên"


# ------------------------------------------------------------------ callbacks
def register(app):
    @app.callback(Output("nt-nv", "options"), Output("nt-pham-vi", "children"), Output("nt-kpi", "children"),
                  Output("nt-nv-luoi", "rowData"), Output("nt-nv-luoi", "dashGridOptions"),
                  Output("nt-luoi", "rowData"), Output("nt-the", "children"), Output("nt-tieu-de-ds", "children"),
                  Output("nt-mo-ta", "children"),
                  Input("nt-phong", "value"), Input("nt-nv", "value"), Input("nt-nhanh", "data"),
                  Input("nt-tim", "value"), Input("nt-da-luu", "data"), State("ui-vw", "data"),
                  State("nt-nv-luoi", "dashGridOptions"))
    def _nap(code, acc, nhanh, tim, _luu, vw, opts_nv):
        nhanh = nhanh if nhanh in TEN_LOC else "all"
        df = nt.danh_sach(_phong_hop_le(code))
        if df.empty:
            return [], [], _kpi(nt.dem(df), nhanh), [], no_update, [], [], "Danh sách hợp đồng tồn", \
                "Phòng chưa có hợp đồng tồn (hoặc chưa nạp file Internet)."
        tong = nt.tong_hop_nv(df)
        dong_nv, ghim_nv = _dong_nv(tong)
        ds_nv = [{"label": _nhan_nv(r), "value": r.acc_norm} for r in tong.itertuples()]
        chon = [a for a in _ds_acc(acc) if a in set(tong.acc_norm)]
        xem = nt.loc(df, chon, nhanh, tim)
        xem = xem.assign(sua_duoc=True)           # sale sửa được mọi ca
        dien_thoai = (vw or {}).get("w", 1440) < 768
        tieu_de = " · ".join(x for x in (_tieu_de(tong, chon), TEN_LOC[nhanh], f"{len(xem)} ca") if x)
        mo_ta = f"{len(xem)} / {len(df)} hợp đồng của phòng. Số tồn tính theo file Internet mới nhất đã nạp."
        if _dung_chung() and len(chon) != 1:
            mo_ta = html.Span([mo_ta, " ", html.I(GHI_TEN)])
        return (ds_nv, _pham_vi(tong, chon),
                _kpi(nt.dem(nt.loc(df, chon)), nhanh, _tieu_de(tong, chon) if chon else "cả phòng"),
                dong_nv, {**(opts_nv or {}), "pinnedBottomRowData": ghim_nv},
                [] if dien_thoai else _dong_luoi(xem, len(chon) != 1),
                _the(xem) if dien_thoai else [], tieu_de, mo_ta)

    @app.callback(Output("nt-nv", "value"), Input("nt-nv-luoi", "selectedRows"), prevent_initial_call=True)
    def _bam_dong_nv(rows):
        """Bấm một dòng ở bảng tổng quan = tick đúng người đó ở ô Nhân viên (danh sách dưới lọc theo)."""
        r = (rows or [None])[0]
        if not r or not r.get("acc_norm"):
            raise PreventUpdate
        return [r["acc_norm"]]

    @app.callback(Output("nt-nhanh", "data"), Input({"type": "nt-loc", "v": ALL}, "n_clicks"),
                  prevent_initial_call=True)
    def _bam_loc(bam):
        if not isinstance(ctx.triggered_id, dict) or not any(bam or []):
            raise PreventUpdate
        return ctx.triggered_id["v"]

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
        dau = [f"{r.ten_khach_hang or 'Khách hàng'} · {r.ho_ten} · tạo {r.ngay_tao_hd[8:10]}/"
               f"{r.ngay_tao_hd[5:7]} · chờ {int(r.so_ngay_cho)} ngày",
               html.Span(f" · {r.canh_bao}", className=f"nt-cb {r.muc}") if r.canh_bao else None]
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
