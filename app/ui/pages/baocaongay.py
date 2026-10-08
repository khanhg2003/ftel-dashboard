"""Trang Báo cáo ngày - sale nhập 6 ô đầu ngày, cả phòng nhìn một bảng (quy tắc: app/bao_cao_ngay.py).

Laptop: sửa ngay trong ô như Google Sheet, tự lưu từng ô. Điện thoại (< 768 px): mỗi người một thẻ,
bấm thẻ mở form. Nút "Tạo ảnh báo cáo" vẽ PNG gửi nhóm. Mọi callback kiểm lại phòng được xem ở máy chủ.
"""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
from dash import ALL, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate
from flask_login import current_user

from app import bao_cao_ngay as bc
from app.auth import ghi_log
from app.org import phong_order
from app.thoi_gian import gio_viet_nam
from app.ui import ngan_nhan_su as nn
from app.ui.components import alert, field, modal, tip
from app.ui.icons import icon
from app.ui.luoi import SO, bang

AN = {"display": "none"}
TOI_LA = "Chọn tên mình (để ghi tên)"
GHI_TEN = "Chọn tên mình ở ô \"Tôi là\" để phần \"cập nhật bởi\" ghi đúng tên."
SUA = "params.data.sua_duoc"
NHIP_MS = 15_000                   # nhịp hỏi lại xem có ai vừa sửa không (chốt 26/09/2026)
# Vá lại dòng mình vừa sửa sau khi ngừng gõ CHO_VA giây. Phải hoãn chứ không vá ngay lúc lưu:
# ag-grid XOÁ SẠCH undo stack mỗi lần nhận transaction, vá ngay là Ctrl+Z mất tác dụng.
NHIP_VA_MS = 2_000
CHO_VA = 5
# tô cam theo NGƯỜI chưa nhập báo cáo hôm nay, không theo ô bằng 0: KHTN 0 hay ONL sáng 0 là số thật
THIEU = {"o-thieu": "!params.data.da_nhap && !params.data.la_tong"}
# chưa nhập thì để ô trống chứ không hiện 0, nhìn là biết ngay ai còn thiếu
SO_NHAP = {"function": "params.data.da_nhap ? " + SO["function"] + " : ''"}
GOI_Y = ("Mục tiêu bán của riêng hôm nay.\nKHTN là khách đang theo, chưa lên hợp đồng.\n"
         "Dự kiến online sáng / chiều là số ca chắc chắn lên trong buổi đó.")
MAU_CON = {"styleConditions": [{"condition": "params.value > 0",
                                "style": {"color": "#8A5A00", "fontWeight": "650"}},
                               {"condition": "params.value < 0",        # đã online vượt dự kiến
                                "style": {"color": "#1B7A4B", "fontWeight": "650"}}]}
# Hai cột này là cộng trừ thuần tuý nên để trình duyệt tự tính: gõ ONL sáng / chiều là đổi NGAY,
# không phải chờ máy chủ trả về (chủ app chốt 27/09/2026). Công thức phải giống hệt `bao_cao_ngay.bang`
# và `tom_tat` - sửa một bên thì sửa cả ba, có test đối chiếu.
# "Còn phải ONL" KHÔNG kẹp ở 0: online vượt dự kiến thì để số âm, nhờ vậy cộng dọc cột mới ra dòng TỔNG.
# Phải bọc Number(): ô vừa gõ trả về CHUỖI, để nguyên thì "5" + 0 ra "50" chứ không phải 5.
_SO_O = "Number(params.data.%s || 0)"
DK_ONL = {"function": f"{_SO_O % 'onl_sang'} + {_SO_O % 'onl_chieu'}"}
CON_PHAI_ONL = {"function": f"{_SO_O % 'onl_sang'} + {_SO_O % 'onl_chieu'} - {_SO_O % 'thuc_hien'}"}


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
    # cho chọn cả ngày tương lai (sale điền trước), nhưng không quá bc.TRUOC_TOI_DA ngày
    return min(d, bc.ngay_xa_nhat())


def _dau_khoi(c: dict) -> dict:
    """Cột mở đầu một khối: thêm lớp kẻ dọc đậm cho cả ô header và ô dữ liệu."""
    c = dict(c)
    c["headerClass"] = (c.get("headerClass", "") + " khoi-dau").strip()
    c["cellClass"] = (c.get("cellClass", "") + " khoi-dau").strip()
    return c


def _cot() -> list[dict]:
    # cellClass phải kèm "ag-right-aligned-cell": đặt cellClass cho cột numericColumn thì mất lớp
    # căn phải của kiểu cột, số trong ô sale nhập sẽ lệch hàng với các cột số còn lại
    sua = {"editable": {"function": SUA}, "cellClass": "ag-right-aligned-cell o-sale", "cellClassRules": THIEU,
           "type": "numericColumn", "valueFormatter": SO_NHAP, "width": 84, "minWidth": 74, "maxWidth": 104}
    doc = {"type": "numericColumn", "valueFormatter": SO, "width": 84, "minWidth": 72, "maxWidth": 104}
    sua_doc = {**doc, "editable": {"function": SUA}, "cellClass": "ag-right-aligned-cell o-sale"}

    ban = [
        {"field": "muc_tieu", "headerName": "MT ngày *", "headerClass": "vung-sale",
         "headerTooltip": "Mục tiêu bán của riêng hôm nay.", **sua},
        {"field": "khtn", "headerName": "KHTN *", "headerTooltip": "Khách đang theo, chưa lên hợp đồng.",
         **sua},
        # ô khai báo của sale, đối chiếu thẳng với ô "MT ngày" bên trái - không lấy gì từ file
        {"field": "da_ban", "headerName": "Thực hiện *", "headerClass": "vung-sale", **sua,
         "cellStyle": {"fontWeight": "700"},
         "headerTooltip": "Số bán thực hiện hôm nay, so với ô MT ngày ngay bên trái.\nSale tự nhập."},
    ]
    onl = [
        {"field": "dk_onl", "headerName": "DK ONL", **doc, "cellStyle": {"fontWeight": "700"},
         "valueGetter": DK_ONL,
         "headerTooltip": "Dự kiến online cả ngày = sáng + chiều. App tự cộng."},
        {"field": "onl_sang", "headerName": "ONL sáng *", "headerTooltip": "Dự kiến online buổi sáng.", **sua},
        {"field": "onl_chieu", "headerName": "ONL chiều *", "headerTooltip": "Dự kiến online buổi chiều.",
         **sua},
        # ô sale tự gõ như Google Sheet, không liên quan tới file Internet (chốt 06/10/2026)
        {"field": "thuc_hien", "headerName": "Đã online *", "headerClass": "vung-sale", **sua_doc,
         "headerTooltip": "Số đã online hôm nay của người này.\nSale tự gõ, không lấy từ file Internet."},
        {"field": "con_phai_onl", "headerName": "Còn phải ONL", **doc, "cellStyle": MAU_CON,
         "valueGetter": CON_PHAI_ONL,
         "headerTooltip": "Dự kiến ONL trừ đã online.\nSố âm màu xanh nghĩa là người đó đã online "
                          "vượt dự kiến; nhờ để số âm nên cộng dọc cột ra đúng dòng TỔNG."},
    ]
    net = [
        {"field": "pttb_thang", "headerName": "PTTB tháng", **doc, "cellStyle": {"fontWeight": "700"},
         "headerTooltip": "Luỹ kế online từ đầu tháng. App tự lấy."},
        {"field": "mt_thang", "headerName": "MT tháng *", "headerClass": "vung-sale",
         "headerTooltip": "Mục tiêu cả tháng của người này.\nNhập một lần đầu tháng, app nhớ cho các ngày sau.",
         **{**sua, "valueFormatter": SO,
            "cellClassRules": {"o-thieu": "!params.value && !params.data.la_tong"}}},
        {"field": "vvip_thang", "headerName": "V.VIP", **doc,
         "headerTooltip": "Số V.VIP luỹ kế tháng (cột \"Pay\" trong ảnh báo cáo). App tự lấy."},
    ]
    khoi = [("Báo cáo số bán", ban), ("Dự kiến online", onl), ("Số Net / Pay", net)]
    return [
        {"field": "ho_ten", "headerName": "Nhân sự", "pinned": "left", "width": 146, "minWidth": 146,
         "maxWidth": 190, "cellClass": "o-dam", "tooltipField": "acc"},
        # gom thành ba khối để đọc theo cụm: số bán trong ngày · dự kiến online · luỹ kế tháng
        *[{"headerName": ten, "headerClass": "nhom-khoi", "marryChildren": True,
           "children": [_dau_khoi(c[0]), *c[1:]]} for ten, c in khoi],
        # ghi chú để MỘT dòng, xem đủ bằng rê chuột: cột hẹp mà xuống dòng thì 17 người thành bảng dài
        # gấp bốn, sáng ra không ai đọc hết. Bấm vào ô vẫn mở ô soạn to.
        _dau_khoi({"field": "ghi_chu", "headerName": "Ghi chú *", "headerClass": "vung-sale",
                   "minWidth": 150, "flex": 1, "tooltipField": "ghi_chu",
                   "editable": {"function": SUA}, "cellClass": "o-sale",
                   "cellEditor": "agLargeTextCellEditor", "cellEditorPopup": True,
                   "cellEditorParams": {"maxLength": bc.GHI_CHU_TOI_DA, "rows": 5, "cols": 50}}),
    ]


# ------------------------------------------------------------------ giao diện
def layout():
    ds = current_user.phong_bao_cao_ngay()
    if not ds:
        return alert("Tài khoản này không dùng mục Báo cáo ngày.", "bad")
    bc.dam_bao_bang()
    bc.don_ngay_cu()                          # xoá báo cáo của các ngày đã qua cho nhẹ bảng
    ten = {p["code"]: p["ten"] for p in phong_order()}
    hom = bc.hom_nay()
    return html.Div([
        html.Div([
            html.Div(field("Phòng", dcc.Dropdown(id="bn-phong", options=[{"label": ten.get(c, c), "value": c}
                                                                         for c in ds],
                                                 value=ds[0], clearable=False, style={"width": "150px"})),
                     style={} if len(ds) > 1 else AN),
            field("Ngày", dcc.DatePickerSingle(id="bn-ngay", date=hom.isoformat(),
                                               max_date_allowed=bc.ngay_xa_nhat(),
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
        # cả phòng cùng gõ một bảng nên phải tự nạp lại khi người khác vừa sửa
        dcc.Store(id="bn-moc"),
        dcc.Interval(id="bn-nhip", interval=NHIP_MS),
        dcc.Store(id="bn-da-va"),                 # lần sửa gần nhất đã được vá lại lên bảng
        # Dòng TỔNG đi đường riêng: máy chủ gửi số vào Store này, trình duyệt tự đặt vào bảng.
        # Gửi thẳng qua `dashGridOptions` thì Dash nạp lại trọn gói tuỳ chọn và ag-grid XOÁ undo
        # stack - đo 27/09/2026: đổi riêng dòng ghim bằng setGridOption thì undo còn nguyên.
        dcc.Store(id="bn-ghim"),
        dcc.Store(id="bn-ghim-xong"),
        # chỉ chạy vài giây sau khi mình vừa sửa, bình thường tắt hẳn để không bắn request rỗng
        dcc.Interval(id="bn-nhip-va", interval=NHIP_VA_MS, disabled=True),
        html.Div(id="bn-msg"),
        html.Div(id="bn-tom-tat", className="kpi-row kpi-3"),

        html.Div([
            html.Div([html.H3(id="bn-tieu-de", style={"margin": 0}),
                      html.Div(id="bn-mo-ta", className="desc", style={"margin": "2px 0 0"})],
                     className="the-thanh"),
            html.Div(bang("bn-luoi", _cot(), cao=560, lop=f"ag-theme-quartz ag-theme-ftel luoi-ke {nn.lop('ten')}",
                          cot_mac_dinh={"resizable": True, "sortable": False, "suppressMovable": True,
                                        "wrapHeaderText": True, "autoHeaderHeight": True},
                          getRowId="params.data.id",
                          tuy_chon={"suppressCellFocus": False, "singleClickEdit": True,
                                    "stopEditingWhenCellsLoseFocus": True, "enableCellTextSelection": True,
                                    # gõ nhầm số thì Ctrl+Z lùi lại, Ctrl+Shift+Z làm lại
                                    "undoRedoCellEditing": True, "undoRedoCellEditingLimit": 25,
                                    "pinnedBottomRowData": []}),
                     className="bn-laptop"),
            html.Div(id="bn-the", className="bn-dien-thoai"),
            html.Div(["Bấm vào ô để sửa, sửa xong tự lưu. Nhấn Tab để nhảy sang ô kế tiếp. ",
                      "Gõ nhầm thì Ctrl+Z lùi lại, Ctrl+Shift+Z làm lại. ",
                      "Ô viền cam là mục chưa điền. ",
                      "Bấm đúp vào tên nhân sự để xem hồ sơ bán hàng chi tiết.", tip(GOI_Y)], className="goi-y-bam bn-laptop"),
        ], className="card"),

        _khoi_chu(),
        modal("bn-md", html.Span(id="bn-md-tieu-de"), [
            dcc.Store(id="bn-md-acc"),
            html.Div(id="bn-md-dau", className="desc", style={"margin": "0 0 14px"}),
            html.Div([
                _o_so("bn-f-mt", "Mục tiêu ngày *"), _o_so("bn-f-khtn", "KHTN đang có *"),
                _o_so("bn-f-ban", "Thực hiện *"),
                _o_so("bn-f-sang", "Dự kiến ONL sáng *"), _o_so("bn-f-chieu", "Dự kiến ONL chiều *"),
                _o_so("bn-f-onl", "Đã online *"),
            ], className="form-grid"),
            html.Div([html.Label("Ghi chú *"),
                      dcc.Textarea(id="bn-f-ghi-chu", className="inp", maxLength=bc.GHI_CHU_TOI_DA,
                                   placeholder="Công việc hôm nay, khó khăn đang gặp...",
                                   style={"width": "100%", "minHeight": "84px"})], className="field rong"),
                html.Div(id="bn-md-msg"),
        ]),
        _modal_muc_tieu(),
        *_khung_giong(),
    ])


def _khung_giong() -> list:
    """Nút nhập bằng giọng nói - chỉ hiện với đúng người và đúng phòng (xem `app/giong_noi.py`)."""
    from app.ui.pages import baocaongay_giong
    return [baocaongay_giong.khung()] if baocaongay_giong.duoc_dung() else []


def _modal_muc_tieu():
    """Đặt mục tiêu PTTB tháng và (tuỳ chọn) mục tiêu mỗi ngày của phòng - chỉ dùng cho trang Báo cáo ngày.
    Ô mục tiêu ngày để trống thì tự chia đều mục tiêu tháng."""
    return modal("bn-mt", html.Span(id="bn-mt-tieu-de"), [
        html.Div([html.Label("Mục tiêu PTTB cả tháng"),
                  dcc.Input(id="bn-f-mt-thang", type="number", min=0, max=100000, step=1,
                            className="inp")], className="field rong"),
        html.Div([html.Label("Mục tiêu PTTB mỗi ngày (để trống = tự chia)"),
                  dcc.Input(id="bn-f-mt-ngay", type="number", min=0, max=1000, step=1,
                            className="inp")], className="field rong"),
        html.Div(id="bn-mt-chia", className="desc"),
        html.Div("Số này chỉ dùng cho trang Báo cáo ngày, không ảnh hưởng chỉ tiêu ở Báo cáo Tổng "
                 "hay Quản trị. Mỗi tháng đặt một lần, tháng sau nhập lại số mới.",
                 className="desc"),
        html.Div(id="bn-mt-msg"),
    ], nut_chinh="Lưu mục tiêu")


def _o_so(id_: str, nhan: str):
    return html.Div([html.Label(nhan),
                     dcc.Input(id=id_, type="number", min=0, max=bc.TOI_DA, step=1, className="inp")],
                    className="field")


def _khoi_chu():
    """Ba khối chữ của ảnh báo cáo: người dùng tự viết rồi lưu.

    Tài khoản Nhân viên KD cũng thấy khối này (chủ app chốt 25/09/2026): họ vốn đã bấm được
    "Tạo ảnh báo cáo", mà ảnh lấy đúng ba khối chữ này - không cho sửa thì ảnh ra trống chữ.
    Nút "Fox viết giúp" đã bỏ (chủ app chốt 28/09/2026): phần này sale tự nhập.
    """
    o = [("bn-c-trong-tam", "Trọng tâm hôm nay", "Việc cả team phải bám trong ngày."),
         ("bn-c-nhan-dinh", "Đánh giá & nhận định", "Đọc số hôm qua, sáng nay và luỹ kế tháng."),
         ("bn-c-thong-diep", "Thông điệp ngày mới", "Một đoạn ngắn động viên cả team.")]
    return html.Div([
        html.Div([html.H3("Chữ trong ảnh báo cáo", style={"margin": 0}),
                  html.Div("Anh/chị tự viết ba phần dưới đây rồi bấm Lưu. Ảnh lấy đúng phần này.",
                           className="desc", style={"margin": "2px 0 0"}),
                  html.Div(className="grow"),
                  html.Button("Lưu", id="bn-luu-chu", className="btn primary", n_clicks=0)],
                 className="the-thanh"),
        html.Div([html.Div([html.Label([nhan, tip(mo_ta)]),
                            dcc.Textarea(id=i, className="inp", style={"width": "100%", "minHeight": "150px"})],
                           className="field rong") for i, nhan, mo_ta in o], className="form-grid bn-chu"),
        dcc.Loading(html.Div(id="bn-chu-msg"), type="dot"),
    ], className="card")


# ------------------------------------------------------------------ dựng nội dung
def _the_so(nhan: str, so, goi_y: str, mau: str = "", id_: str | None = None) -> html.Div:
    """Thẻ chỉ số. Có `id_` thì thẻ là nút bấm được, kèm nhãn "Sửa" ở góc cho dễ thấy."""
    if not id_:
        return html.Div([html.Div(nhan, className="label"), html.Div(so, className="value"),
                         html.Div(goi_y, className="hint")], className=f"kpi {mau}")
    return html.Button([html.Div(nhan, className="label"), html.Div(so, className="value"),
                        html.Div(goi_y, className="hint"),
                        html.Span([icon("edit", 13), html.Span("Sửa mục tiêu")], className="kpi-sua")],
                       className=f"kpi {mau} kpi-bam", id=id_, n_clicks=0,
                       title="Bấm để đặt mục tiêu PTTB cả tháng")


def _sua_duoc_muc_tieu() -> bool:
    """Chỉ Quản trị (BGĐ) đặt mục tiêu tháng - chủ app chốt 02/10/2026."""
    return bool(getattr(current_user, "duoc_cau_hinh", False))


def _tom_tat(t: dict) -> list:
    hq, ty = t["hq_thuc_te"], t["hq_ty_le"]
    return [
        _the_so(f"Kết quả ngày {t['hom_qua']:%d/%m}", f"{hq} / {t['hq_muc_tieu']}",
                f"Thiếu {t['hq_thieu']} PTTB · đạt {ty}%",
                "ok" if ty >= 100 else "warn" if ty >= 80 else "bad"),
        _the_so(f"Tình hình sáng {t['ngay']:%d/%m}", f"{t['dk_onl']}",
                f"Bán {t['da_ban']} · KHTN {t['khtn']} · sáng {t['onl_sang']} · "
                f"chiều {t['onl_chieu']} · đã online {t['da_online']}",
                "ok" if t["mt_ngay"] and t["dk_onl"] >= t["mt_ngay"] else "warn"),
        _the_so("Luỹ kế tháng", f"{t['luy_ke']} / {t['mt_thang']}",
                f"Còn thiếu {t['con_thieu']} PTTB · đạt {t['ty_le_thang']:g}% · mục tiêu "
                f"{t['mt_ngay']}/ngày",
                "ok" if t["ty_le_thang"] >= 90 else "warn" if t["ty_le_thang"] >= 70 else "bad",
                id_="bn-mt-mo" if _sua_duoc_muc_tieu() else None),
    ]


def _dong_luoi(df: pd.DataFrame) -> list[dict]:
    """Dòng cho bảng. Người CHƯA nhập thì bốn ô sale để trống hẳn (None) chứ không phải số 0:
    ag-grid chỉ báo `cellValueChanged` khi giá trị thay đổi, nên nếu ô sẵn là 0 thì gõ 0 vào
    không được tính là sửa - số không lưu, người dùng phải gõ 1 rồi sửa lại 0 mới ăn."""
    ds = df.to_dict("records")
    for r in ds:
        if not r.get("da_nhap"):
            for k in ("muc_tieu", "khtn", "da_ban", "onl_sang", "onl_chieu"):
                r[k] = None
            r["thuc_hien"] = None
    return ds


def _ghim(df: pd.DataFrame) -> list[dict]:
    """Dòng TỔNG ghim cuối bảng. `da_nhap` / `la_tong` để dòng này không dính hai quy tắc của dòng
    người: "chưa nhập thì để ô trống" (nếu không cả dòng tổng sẽ trắng) và tô cam ô còn thiếu."""
    if df.empty:
        return []
    c = ["muc_tieu", "khtn", "da_ban", "onl_sang", "onl_chieu", "dk_onl", "thuc_hien",
         "pttb_thang", "mt_thang", "vvip_thang"]
    tong = {k: int(df[k].sum()) for k in c}
    # cộng thẳng cột: từng người không kẹp ở 0 nữa nên tổng dọc bằng đúng tổng dự kiến - tổng đã online
    tong["con_phai_onl"] = int(df["con_phai_onl"].sum())
    return [{"ho_ten": "TỔNG", "da_nhap": True, "la_tong": True, **tong}]


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
            html.Div([html.Span(f"MT {int(r.muc_tieu)}"), html.Span(f"Bán {int(r.da_ban)}"),
                      html.Span(f"KHTN {int(r.khtn)}"), html.Span(f"Sáng {int(r.onl_sang)}"),
                      html.Span(f"Chiều {int(r.onl_chieu)}"),
                      html.Span(f"Đã ONL {int(r.thuc_hien)}")], className="bn-the-so"),
            html.Div(r.ghi_chu or "Chưa ghi chú", className="bn-the-gc" + ("" if r.ghi_chu else " thieu")),
        ], **({"id": {"type": "bn-the", "acc": r.acc_norm}, "n_clicks": 0} if r.sua_duoc else {}),
            className="bn-the" + ("" if r.da_nhap else " thieu") + ("" if r.sua_duoc else " chi-xem")))
    return out


# ------------------------------------------------------------------ callbacks
def register(app):
    # Đặt dòng TỔNG vào bảng ngay tại trình duyệt, không qua `dashGridOptions` (xem ghi chú ở layout).
    app.clientside_callback(
        """function (ghim) {
            // Lúc mở trang, số về TRƯỚC khi ag-grid kịp dựng, mà getApi thì NÉM LỖI chứ không trả
            // rỗng - bỏ qua lần đó là dòng TỔNG mất hẳn (số chỉ gửi một lần). Nên phải thử lại.
            if (!ghim) { return window.dash_clientside.no_update; }
            let con = 40;                                  // thử lại tối đa ~4 giây rồi thôi
            const dat = function () {
                let api = null;
                try { api = window.dash_ag_grid.getApi('bn-luoi'); } catch (e) { api = null; }
                if (api) { api.setGridOption('pinnedBottomRowData', ghim); return; }
                if (con-- > 0) { setTimeout(dat, 100); }   // hết lượt = đã rời trang, bỏ qua
            };
            dat();
            return window.dash_clientside.no_update;
        }""",
        Output("bn-ghim-xong", "data"), Input("bn-ghim", "data"), prevent_initial_call=True)

    @app.callback(Output("bn-toi-la", "options"), Output("bn-tom-tat", "children"),
                  Output("bn-luoi", "rowData"), Output("bn-luoi", "rowTransaction"),
                  Output("bn-ghim", "data"),
                  Output("bn-the", "children"), Output("bn-tieu-de", "children"), Output("bn-mo-ta", "children"),
                  Output("bn-moc", "data"),
                  Input("bn-phong", "value"), Input("bn-ngay", "date"), Input("bn-toi-la", "value"),
                  Input("bn-da-luu", "data"), Input("bn-nhip", "n_intervals"),
                  State("ui-vw", "data"), State("bn-moc", "data"))
    def _nap(code, ngay, toi_la, luu, _nhip, vw, moc_cu):
        phong = _phong_hop_le(code)
        d = _ngay_hop_le(ngay)
        # nhịp tự động: chỉ dựng lại bảng khi có người khác vừa sửa, để không cắt ngang ô đang gõ
        moc = bc.moc_cap_nhat(phong, d)
        if ctx.triggered_id == "bn-nhip" and moc == moc_cu:
            raise PreventUpdate
        # Vừa tự sửa một ô: chỉ vá lại đúng dòng đó. Dựng lại cả bảng thì Ctrl+Z mất tác dụng
        # và ô đang gõ dở bị dựng lại giữa chừng - chủ app báo 27/09/2026.
        # chỉ tính khi chính lần lưu đó kích hoạt callback: giá trị cũ còn nằm trong Store nên nếu
        # không xét nguồn kích hoạt thì mọi lần đổi phòng / đổi ngày sau đó đều bị bỏ qua
        vua_sua = (luu or {}).get("acc") if ctx.triggered_id == "bn-da-luu" and isinstance(luu, dict) else None
        df = bc.bang(phong, d)
        t = bc.tom_tat(phong, d)
        if df.empty:
            return [], _tom_tat(t), [], no_update, no_update, [], "Bảng chỉ số toàn bộ nhân sự", \
                "Phòng chưa có số liệu (chưa nạp file Internet của tháng này).", moc
        chon = [{"label": r.ho_ten, "value": r.acc_norm} for r in df.itertuples()]
        df = df.assign(sua_duoc=True)             # sale sửa được mọi dòng (chốt 24/09/2026)
        if vua_sua:
            # Dòng TỔNG và khối tóm tắt cập nhật NGAY, cùng nhịp với DK ONL / Còn phải ONL mà trình
            # duyệt tự tính - nhờ vậy cộng dọc cột luôn ra đúng dòng TỔNG. Riêng dòng vừa sửa để
            # `_va_dong` vá sau: vá ngay là ag-grid xoá undo stack, Ctrl+Z hết tác dụng.
            return (chon, _tom_tat(t), no_update, no_update, _ghim(df),
                    no_update, no_update, no_update, moc)
        dien_thoai = (vw or {}).get("w", 1440) < 768
        tieu_de = [f"Bảng chỉ số toàn bộ nhân sự · {d:%d/%m/%Y}"]
        if d > bc.hom_nay():                      # điền trước cho hôm sau: phải nói rõ kẻo đọc nhầm
            tieu_de.append(html.Span("Nhập trước", className="bn-sau"))
        mo_ta = (f"{t['so_nguoi']} nhân sự · {t['chua_nhap']} người chưa nhập. "
                 "Ô có dấu * là sale nhập, còn lại app tự lấy từ file Internet.")
        if d > bc.hom_nay():
            mo_ta = (f"Ngày {d:%d/%m} chưa tới nên các cột app tự lấy từ file vẫn đang là số của hôm nay. "
                     + mo_ta)
        if _dung_chung() and not toi_la:
            mo_ta = html.Span([mo_ta, " ", html.I(GHI_TEN)])
        return (chon, _tom_tat(t), [] if dien_thoai else _dong_luoi(df), no_update, _ghim(df),
                _the(df) if dien_thoai else [], tieu_de, mo_ta, moc)

    @app.callback(Output("bn-luoi", "rowTransaction", allow_duplicate=True),
                  Output("bn-da-va", "data"), Output("bn-nhip-va", "disabled", allow_duplicate=True),
                  Input("bn-nhip-va", "n_intervals"), State("bn-da-luu", "data"), State("bn-da-va", "data"),
                  State("bn-phong", "value"), State("bn-ngay", "date"), prevent_initial_call=True)
    def _va_dong(_n, luu, da_va, code, ngay):
        """Làm mới dòng mình vừa sửa sau khi ngừng gõ CHO_VA giây.

        Chỉ còn phải hoãn mấy cột app tự lấy từ file (đã online theo file, PTTB tháng) và cờ
        "đã nhập": DK ONL với Còn phải ONL nay trình duyệt tự tính nên đổi ngay lúc gõ, còn dòng
        TỔNG đi đường riêng qua `bn-ghim` nên cũng không phải chờ."""
        acc = (luu or {}).get("acc") if isinstance(luu, dict) else None
        if not acc or luu.get("luc") == da_va:
            return no_update, no_update, True
        if (gio_viet_nam() - datetime.fromisoformat(luu["luc"])).total_seconds() < CHO_VA:
            raise PreventUpdate                    # còn đang gõ tiếp, để lượt sau
        df = bc.bang(_phong_hop_le(code), _ngay_hop_le(ngay))
        if df.empty:
            return no_update, luu["luc"], True
        dong = df[df.acc_norm.isin(acc)].assign(sua_duoc=True)
        return ({"update": _dong_luoi(dong)} if not dong.empty else no_update), luu["luc"], True

    @app.callback(Output("bn-da-luu", "data"), Output("bn-msg", "children"),
                  Output("bn-nhip-va", "disabled"),
                  Input("bn-luoi", "cellValueChanged"), State("bn-phong", "value"), State("bn-ngay", "date"),
                  State("bn-toi-la", "value"), prevent_initial_call=True)
    def _luu_o(doi, code, ngay, toi_la):
        phong, d = _phong_hop_le(code), _ngay_hop_le(ngay)
        ten = nt_ten(toi_la) if _dung_chung() else None
        loi, da_sua = [], []
        for x in (doi if isinstance(doi, list) else [doi] if doi else []):
            r, cot = x.get("data") or {}, x.get("colId")
            try:
                if cot == "mt_thang":
                    bc.dat_muc_tieu(f"{d:%Y-%m}", "NHAN_VIEN", r.get("acc_norm"), "internet",
                                    float(x.get("value") or 0), current_user.username)
                elif cot in bc.O_NHAP or cot == "thuc_hien":
                    # "Đã online" hiện số đã gộp với file, nhưng gõ vào thì lưu vào ô nhập tay
                    o = "da_online" if cot == "thuc_hien" else cot
                    bc.luu(r.get("acc_norm"), {o: x.get("value")}, phong, current_user.username, d,
                           ghi_ten=ten)
                else:
                    continue
                da_sua.append(r.get("acc_norm"))
            except bc.LoiBaoCao as e:
                loi.append(str(e))
        # kèm acc vừa sửa, và bật nhịp để `_va_dong` làm mới dòng đó khi sale ngừng gõ
        return ({"luc": gio_viet_nam().isoformat(), "acc": da_sua},
                alert(" ".join(loi), "bad") if loi else None, not da_sua)

    @app.callback(Output("bn-md", "className"), Output("bn-md-tieu-de", "children"),
                  Output("bn-md-acc", "data"), Output("bn-md-dau", "children"), Output("bn-f-mt", "value"),
                  Output("bn-f-khtn", "value"), Output("bn-f-ban", "value"), Output("bn-f-sang", "value"),
                  Output("bn-f-chieu", "value"),
                  Output("bn-f-onl", "value"), Output("bn-f-ghi-chu", "value"), Output("bn-md-msg", "children"),
                  Input({"type": "bn-the", "acc": ALL}, "n_clicks"), Input("bn-md-dong", "n_clicks"),
                  Input("bn-md-huy", "n_clicks"), Input("bn-da-luu", "data"), State("bn-phong", "value"),
                  State("bn-ngay", "date"), prevent_initial_call=True)
    def _mo_form(bam, _d, _h, _l, code, ngay):
        if not isinstance(ctx.triggered_id, dict):
            return ("modal",) + (no_update,) * 11
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
                int(r.da_ban), int(r.onl_sang), int(r.onl_chieu), int(r.thuc_hien), r.ghi_chu, "")

    @app.callback(Output("bn-md-msg", "children", allow_duplicate=True),
                  Output("bn-da-luu", "data", allow_duplicate=True),
                  Input("bn-md-ok", "n_clicks"), State("bn-md-acc", "data"), State("bn-f-mt", "value"),
                  State("bn-f-khtn", "value"), State("bn-f-ban", "value"), State("bn-f-sang", "value"),
                  State("bn-f-chieu", "value"),
                  State("bn-f-onl", "value"), State("bn-f-ghi-chu", "value"), State("bn-phong", "value"),
                  State("bn-ngay", "date"), State("bn-toi-la", "value"), prevent_initial_call=True)
    def _luu_form(_n, acc, mt, khtn, ban, sang, chieu, onl, gc, code, ngay, toi_la):
        phong, d = _phong_hop_le(code), _ngay_hop_le(ngay)
        if not (gc or "").strip():
            return alert("Chưa điền Ghi chú.", "bad"), no_update
        try:
            bc.luu(acc, {"muc_tieu": mt, "khtn": khtn, "da_ban": ban, "onl_sang": sang,
                         "onl_chieu": chieu, "da_online": onl, "ghi_chu": gc},
                   phong, current_user.username, d, ghi_ten=nt_ten(toi_la) if _dung_chung() else None)
        except bc.LoiBaoCao as e:
            return alert(str(e), "bad"), no_update
        return "", gio_viet_nam().isoformat()

    # ---------------------------------------------- mục tiêu tháng (chỉ Quản trị)
    @app.callback(Output("bn-mt", "className"), Output("bn-mt-tieu-de", "children"),
                  Output("bn-f-mt-thang", "value"), Output("bn-f-mt-ngay", "value"),
                  Output("bn-mt-msg", "children"),
                  Input("bn-mt-mo", "n_clicks"), Input("bn-mt-dong", "n_clicks"),
                  Input("bn-mt-huy", "n_clicks"), Input("bn-da-luu", "data"),
                  State("bn-phong", "value"), State("bn-ngay", "date"), prevent_initial_call=True)
    def _mo_muc_tieu(mo, _d, _h, _l, code, ngay):
        # `mo` phải khác 0: thẻ Luỹ kế tháng được dựng lại mỗi lần nạp số, Dash coi component mới
        # xuất hiện là một lần kích hoạt - không xét n_clicks thì hộp thoại tự bật khi mở trang.
        if ctx.triggered_id != "bn-mt-mo" or not mo or not _sua_duoc_muc_tieu():
            return "modal", no_update, no_update, no_update, ""
        phong, d = _phong_hop_le(code), _ngay_hop_le(ngay)
        thang = f"{d:%Y-%m}"
        return ("modal mo", f"Mục tiêu tháng {d:%m/%Y} · {code}",
                bc.muc_tieu_thang(thang, phong), bc.muc_tieu_ngay_rieng(thang, phong[0]), "")

    @app.callback(Output("bn-mt-chia", "children"), Input("bn-f-mt-thang", "value"),
                  Input("bn-f-mt-ngay", "value"), State("bn-ngay", "date"))
    def _xem_chia(mt, mt_ngay, ngay):
        d = _ngay_hop_le(ngay)
        thang = f"{d:%Y-%m}"
        so_ngay = bc.month_range(thang)[2]
        mt = int(mt or 0)
        tu_chia = f"{mt} ÷ {so_ngay} ngày = {bc.muc_tieu_ngay(mt, thang)} PTTB/ngày"
        if mt_ngay:
            return f"Mục tiêu mỗi ngày: {int(mt_ngay)} PTTB/ngày (đặt tay). Nếu để trống, app tự chia: {tu_chia}."
        return f"Mục tiêu mỗi ngày tự chia: {tu_chia}."

    @app.callback(Output("bn-mt-msg", "children", allow_duplicate=True),
                  Output("bn-da-luu", "data", allow_duplicate=True),
                  Input("bn-mt-ok", "n_clicks"), State("bn-f-mt-thang", "value"),
                  State("bn-f-mt-ngay", "value"), State("bn-phong", "value"), State("bn-ngay", "date"),
                  prevent_initial_call=True)
    def _luu_muc_tieu(_n, mt, mt_ngay, code, ngay):
        if not _sua_duoc_muc_tieu():
            raise PreventUpdate
        phong, d = _phong_hop_le(code), _ngay_hop_le(ngay)
        thang = f"{d:%Y-%m}"
        try:
            bc.dat_muc_tieu_thang(thang, phong[0], float(mt or 0), current_user.username)
            bc.dat_muc_tieu_ngay_phong(thang, phong[0], float(mt_ngay) if mt_ngay else None,
                                       current_user.username)
        except (bc.LoiBaoCao, TypeError, ValueError) as e:
            return alert(str(e) or "Mục tiêu không hợp lệ.", "bad"), no_update
        ghi_log("dat_muc_tieu_bao_cao_ngay", f"{thang} {phong[0]} = {int(mt or 0)}, ngày {mt_ngay or 'tự chia'}")
        return "", gio_viet_nam().isoformat()

    _dang_ky_chu(app)
    from app.ui.pages import baocaongay_giong
    baocaongay_giong.register(app)

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
    """Ba khối chữ: nạp khi đổi ngày, người dùng tự viết rồi lưu."""
    o = ("bn-c-trong-tam", "bn-c-nhan-dinh", "bn-c-thong-diep")

    @app.callback([Output(i, "value") for i in o],
                  Input("bn-phong", "value"), Input("bn-ngay", "date"))
    def _nap_chu(code, ngay):
        c = bc.chu(_phong_hop_le(code)[0], _ngay_hop_le(ngay))
        return c["trong_tam"], c["nhan_dinh"], c["thong_diep"]

    @app.callback(Output("bn-chu-msg", "children"), Input("bn-luu-chu", "n_clicks"),
                  [State(i, "value") for i in o], State("bn-phong", "value"), State("bn-ngay", "date"),
                  prevent_initial_call=True)
    def _luu_chu(_n, tt, nd, td, code, ngay):
        phong, d = _phong_hop_le(code), _ngay_hop_le(ngay)
        bc.luu_chu(phong[0], {"trong_tam": tt, "nhan_dinh": nd, "thong_diep": td},
                   current_user.username, d)
        return alert("Đã lưu phần chữ cho ảnh báo cáo.", "ok")
