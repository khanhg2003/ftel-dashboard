"""Trang Lead Online (chốt 16/11/2026): một kho lead duy nhất thay cho nhiều tab Google Sheet theo tỉnh.

Bảng sửa ngay trong ô như Google Sheet (cùng kiểu với Nhập tồn - app/ui/pages/nhapton.py), tự lưu từng ô.
Quyền xem/sửa lead: tài khoản vai trò "online" (5 bạn trong nhóm) và admin (`current_user.duoc_xem_phong_online`,
giống trang Phòng Online). Mục Cấu hình (danh mục page, người nhận cảnh báo Zalo, kết nối Messenger) chỉ
admin (`duoc_cau_hinh`).

**Sale 1/2/3** (chốt 20/11/2026, thay cột "Sale tư vấn" cũ - xem `app/leads.py`): ba cột hiện lịch sử ai đã
từng nhận lead này. Mỗi ô chỉ sửa được khi nó là Ô TRỐNG KẾ TIẾP (sale_1 trống -> sửa sale_1; sale_1 có mà
sale_2 trống -> sửa sale_2...), ô đã có người ở sale_1/sale_2 thì KHOÁ (chỉ xem) - riêng sale_3 luôn sửa
được một khi sale_2 đã có người, vì lead bị dội quá 3 lần thì ghi đè sale_3. Sửa bất kỳ ô nào trong 3 ô này
đều gọi `leads.nhan_cheo`, hàm tự tìm đúng ô cần điền.

Hộp "Thêm lead mới" (rút gọn 19-20/11/2026, chủ app thấy nhiều ô quá): còn 6 ô (Tỉnh/Page, Ngày, Sale 1,
Tên KH, SĐT, Trạng thái) + một ô "Ghi chú" tự do (gộp Địa chỉ/Nhu cầu/KH dùng mạng/Mô hình/Tư vấn cũ - sale
ít khi điền đủ 5 ô riêng). KHTN của Báo cáo ngày (`app/bao_cao_ngay.dong_bo_khtn`) đếm theo người ĐANG phụ
trách (`leads.nguoi_phu_trach`) nên gán Sale 1 ngay lúc thêm vẫn có ý nghĩa, dù chưa bắt buộc.

**Xoá lead** (thêm 20/11/2026): tích ô # đầu dòng (checkbox, chọn nhiều dòng được) rồi bấm "Xoá lead đã
chọn" - có hộp xác nhận trước khi xoá thật (`leads.xoa_lead`, đã ghi `AuditLog`). Không giới hạn riêng ai
được xoá (ai xem/sửa được trang này thì xoá được), giống quyền sửa các ô khác trên bảng.
"""
from __future__ import annotations

from datetime import date
from urllib.parse import quote

from dash import Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate
from flask_login import current_user

from app import canh_bao_lead as cb
from app import leads
from app.auth import ghi_log
from app.thoi_gian import chu_gio_vn, gio_viet_nam
from app.ui.components import alert, field, modal
from app.ui.icons import icon
from app.ui.luoi import SO, bang

AN = {"display": "none"}
TAT_CA = "Tất cả"
QUA_HAN_LOP = "params.data.qua_han"
GIO_TRE_MAU = {"styleConditions": [{"condition": QUA_HAN_LOP, "style": {"color": "#B42318", "fontWeight": "700"}}]}
# "2026-11-20" -> "20/11/2026": chỉ đổi CÁCH HIỂN THỊ (valueFormatter), giữ nguyên giá trị ISO trong ô để
# sắp xếp theo ngày vẫn đúng (chuỗi "dd/mm/yyyy" sắp xếp kiểu chữ sẽ sai thứ tự). Chủ app báo bảng khó nhìn
# 20/11/2026 - ISO dài hơn nên hay bị ag-grid cắt chữ ở cột hẹp, và không đúng kiểu Việt Nam.
VN_NGAY = {"function": "params.value ? params.value.slice(8,10)+'/'+params.value.slice(5,7)+'/'+"
                       "params.value.slice(0,4) : ''"}


def topbar():
    return [html.Div([html.H1("Lead Online"),
                      html.Div("Mọi lead của Phòng Online ở một chỗ - bấm vào ô để sửa, sửa xong tự lưu",
                               className="sub")])]


def _duoc_xem() -> bool:
    return bool(getattr(current_user, "is_authenticated", False)) and current_user.duoc_xem_phong_online


#  Sale 1/2/3 (chốt 20/11/2026): mỗi ô chỉ sửa được khi nó là Ô TRỐNG KẾ TIẾP; sale_3 luôn sửa được một khi
#  sale_2 đã có người (cho phép ghi đè khi lead bị dội quá 3 lần, xem app/leads.nhan_cheo).
DK_SALE1 = "!params.data.sale_1"
DK_SALE2 = "params.data.sale_1 && !params.data.sale_2"
DK_SALE3 = "!!params.data.sale_2"


def _cot_sale(field: str, ten: str, dieu_kien: str, opt_ten: list[str]) -> dict:
    return {"field": field, "headerName": ten, "minWidth": 140, "width": 150,
            "editable": {"function": dieu_kien}, "cellEditor": "agSelectCellEditor",
            "cellEditorParams": {"values": opt_ten}, "tooltipValueGetter": {"function": "params.value || ''"},
            "cellClassRules": {"o-sale": dieu_kien, "o-tu-ca": f"!({dieu_kien})"}}


def _cot() -> list[dict]:
    # Rà soát 20/11/2026 (chủ app báo bảng khó nhìn vì chữ bị cắt): cột nào hay có chữ dài thì nới rộng
    # hẳn (minWidth, bỏ "width" chặn hẹp) thay vì để ag-grid cắt bớt bằng dấu "...", thêm tooltipField tự
    # thân cho chắc (rê chuột vẫn đọc được đủ dù màn hẹp làm cột co lại). Bảng dài hơn, phải cuộn ngang
    # nhiều hơn - chấp nhận đổi lấy không còn mất chữ, đúng tinh thần "còn ngắn hơn là cắt chữ" ở Nhập tồn.
    sua = {"editable": True, "cellClass": "o-sale"}
    tu_than = {"tooltipValueGetter": {"function": "params.value || ''"}}
    opt_ten = [a["ten"] for a in leads.nguoi_online()]
    return [
        {"field": "id", "headerName": "#", "width": 56, "maxWidth": 64, "pinned": "left", "cellClass": "o-dam",
         "checkboxSelection": True, "headerCheckboxSelection": True},
        {"field": "ngay", "headerName": "Ngày", "width": 104, "maxWidth": 112, "valueFormatter": VN_NGAY},
        {"field": "tinh", "headerName": "Tỉnh / Page", "minWidth": 120, "flex": 1},
        {"field": "ten_kh", "headerName": "Tên KH", "minWidth": 170, "flex": 1.4, **tu_than, **sua},
        {"field": "sdt", "headerName": "SĐT", "minWidth": 110, "width": 120, **sua},
        {"field": "tinh_trang_xu_ly", "headerName": "Tình trạng xử lý", "minWidth": 150, "width": 160,
         "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": leads.TRANG_THAI}, **sua},
        _cot_sale("sale_1_ten", "Sale 1", DK_SALE1, opt_ten),
        _cot_sale("sale_2_ten", "Sale 2", DK_SALE2, opt_ten),
        _cot_sale("sale_3_ten", "Sale 3", DK_SALE3, opt_ten),
        {"field": "sale_len", "headerName": "Sale lên", "minWidth": 120, "width": 130, **tu_than, **sua},
        {"field": "ghi_chu", "headerName": "Ghi chú", "minWidth": 200, "flex": 2, "wrapText": True,
         "autoHeight": True, "cellEditor": "agLargeTextCellEditor", "cellEditorPopup": True, **sua},
        {"field": "gio_tre", "headerName": "Trễ (giờ)", "width": 92, "maxWidth": 100, "type": "numericColumn",
         "valueFormatter": SO, "cellStyle": GIO_TRE_MAU,
         "headerTooltip": f"Số giờ từ lần chăm sóc gần nhất. Quá {leads.han_sla_gio():g}h chưa đổi trạng thái -> đỏ, "
                          "hệ thống tự báo Zalo để nhờ người khác nhận chéo."},
    ]


def layout():
    if not _duoc_xem():
        return alert("Tài khoản này không xem được mục Lead Online.", "bad")
    leads.dam_bao_bang()
    pages = leads.ds_page()
    nguoi = leads.nguoi_online()
    opt_page = [{"label": t, "value": i} for i, t in zip(pages.id, pages.ten)] if len(pages) else []
    opt_sale = [{"label": a["ten"], "value": a["acc_norm"]} for a in nguoi]
    return html.Div([
        dcc.Store(id="ld-da-luu"),
        dcc.ConfirmDialog(id="ld-xoa-xacnhan", message=""),
        html.Div(id="ld-msg"),
        html.Div(id="ld-kpi", className="kpi-row kpi-3"),
        html.Div(id="ld-trang-thai"),
        html.Div([
            html.Div([
                field("Tỉnh / Page", dcc.Dropdown(id="ld-loc-page", options=opt_page, placeholder=TAT_CA,
                                                  style={"minWidth": "160px"})),
                field("Sale", dcc.Dropdown(id="ld-loc-sale", options=opt_sale, placeholder=TAT_CA,
                                           style={"minWidth": "140px"})),
                field("Trạng thái", dcc.Dropdown(id="ld-loc-tt", options=leads.TRANG_THAI, placeholder=TAT_CA,
                                                 style={"minWidth": "150px"})),
                dcc.Input(id="ld-tim", type="search", placeholder="Tìm tên hoặc SĐT…", className="o-tim"),
                html.Div(className="grow"),
                html.Button([icon("trash", 14), html.Span("Xoá lead đã chọn")], id="ld-xoa-mo",
                            className="btn nguy-hiem"),
                html.Button([icon("plus", 14), html.Span("Thêm lead")], id="ld-them-mo", className="btn primary"),
            ], className="toolbar", style={"flexWrap": "wrap"}),
            dcc.Loading(bang("ld-luoi", _cot(), cao=560, lop="ag-theme-quartz ag-theme-ftel luoi-ke",
                             getRowId="params.data.id",
                             tuy_chon={"singleClickEdit": True, "stopEditingWhenCellsLoseFocus": True,
                                       "rowSelection": "multiple", "suppressRowClickSelection": True,
                                       "rowClassRules": {"dong-do": QUA_HAN_LOP}})),
            html.Div("Bấm vào ô để sửa, sửa xong tự lưu. Sửa ô Sale 1/2/3 trống kế tiếp của một lead đang "
                     "trễ (đỏ) chính là thao tác nhận lead. Tích ô # đầu dòng rồi bấm \"Xoá lead đã chọn\" "
                     "để xoá.", className="goi-y-bam"),
        ], className="card"),
        modal("ld-md", "Thêm lead mới", [
            # Rút gọn 19-20/11/2026 (chủ app thấy nhiều ô quá): còn 6 ô + một ô Ghi chú tự do gộp 5 ô ít
            # dùng cũ (địa chỉ, nhu cầu, KH dùng mạng, mô hình, tư vấn).
            html.Div([
                field("Tỉnh / Page *", dcc.Dropdown(id="ld-f-page", options=opt_page, placeholder="Chọn page")),
                field("Ngày *", dcc.Input(id="ld-f-ngay", type="date", className="inp", value=date.today().isoformat())),
                field("Sale 1", dcc.Dropdown(id="ld-f-sale", options=opt_sale, placeholder="Chưa gán")),
                field("Tên KH", dcc.Input(id="ld-f-ten", className="inp")),
                field("SĐT", dcc.Input(id="ld-f-sdt", className="inp")),
                field("Trạng thái", dcc.Dropdown(id="ld-f-tt", options=leads.TRANG_THAI, value="Mới",
                                                 clearable=False)),
            ], className="form-grid"),
            field("Ghi chú", dcc.Textarea(id="ld-f-ghichu", className="inp", style={"width": "100%", "minHeight": "70px"},
                                          placeholder="Khách nhắn gì, cần gì, địa chỉ, nhu cầu...")),
            html.Div(id="ld-md-msg"),
        ], nut_chinh="Thêm"),
        # Luôn render (ẩn bằng CSS, không bỏ khỏi cây) để callback của mục Cấu hình không lỗi
        # "nonexistent object" khi tài khoản không phải admin xem trang - callback vẫn tự kiểm
        # quyền `duoc_cau_hinh` ở máy chủ trước khi trả dữ liệu (như `callback_can_quyen` đang làm).
        html.Div(_cau_hinh(), style={} if current_user.duoc_cau_hinh else AN),
    ])


def _sla_hien_thi(gio: float) -> tuple[float, str]:
    """Chọn đơn vị dễ đọc để hiện lại ngưỡng SLA đang lưu (bằng giờ): chia hết cho 24 thì hiện theo
    ngày, không thì hiện theo giờ."""
    return (gio / 24, "ngay") if gio and gio % 24 == 0 else (gio, "gio")


def _cau_hinh():
    pages = leads.ds_page()
    opt_page = [{"label": t, "value": i} for i, t in zip(pages.id, pages.ten)] if len(pages) else []
    opt_sale = [{"label": a["ten"], "value": a["acc_norm"]} for a in leads.nguoi_online()]
    _sla_so_luon, _sla_don_vi = _sla_hien_thi(leads.han_sla_gio())
    return html.Details([
        html.Summary("Cấu hình (chỉ Quản trị)", className="cg-tieu-de"),
        html.Div([
            html.H3("Danh mục page / tỉnh", style={"margin": "4px 0"}),
            html.Div([
                field("Tên page / tỉnh", dcc.Input(id="ld-pg-ten", className="inp", placeholder="VD: Hải Phòng")),
                field("Ghi chú", dcc.Input(id="ld-pg-ghichu", className="inp")),
                field(" ", html.Button([icon("plus", 14), html.Span("Thêm page")], id="ld-pg-them",
                                       className="btn primary")),
            ], className="toolbar", style={"flexWrap": "wrap"}),
            html.Div(id="ld-pg-msg"),
            bang("ld-g-page", [
                {"field": "id", "headerName": "#", "width": 56},
                {"field": "ten", "headerName": "Tên ✎", "editable": True, "minWidth": 160, "flex": 1},
                {"field": "ghi_chu", "headerName": "Ghi chú ✎", "editable": True, "minWidth": 160, "flex": 1},
                {"field": "fb_page_id", "headerName": "Facebook Page ID", "minWidth": 140},
                {"field": "active", "headerName": "Đang dùng ✎", "editable": True, "width": 100,
                 "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": [True, False]}},
            ], cao=240, getRowId="params.data.id"),
            html.Button([icon("save", 14), html.Span("Lưu danh mục")], id="ld-pg-luu", className="btn primary",
                        style={"marginTop": "8px"}),

            html.H3("Ngưỡng cảnh báo SLA", style={"margin": "18px 0 4px"}),
            html.Div("Lead chưa chăm sóc (chưa đổi trạng thái/ghi chú/người phụ trách) quá khoảng này thì "
                     "tính là quá hạn và hệ thống tự nhắc qua Zalo.", className="desc"),
            html.Div([
                field("Số lượng", dcc.Input(id="ld-sla-so", type="number", min=1, step=0.5,
                                            value=_sla_so_luon, className="inp", style={"width": "90px"})),
                field("Đơn vị", dcc.Dropdown(id="ld-sla-dv", options=[{"label": "Giờ", "value": "gio"},
                                                                      {"label": "Ngày", "value": "ngay"}],
                                             value=_sla_don_vi, clearable=False, style={"minWidth": "110px"})),
                field(" ", html.Button([icon("save", 14), html.Span("Lưu ngưỡng")], id="ld-sla-luu",
                                       className="btn primary")),
            ], className="toolbar", style={"flexWrap": "wrap"}),
            html.Div(id="ld-sla-msg"),

            html.H3("Người nhận cảnh báo SLA (Zalo)", style={"margin": "18px 0 4px"}),
            html.Div("Sale: gắn acc để tính tải việc khi gợi ý nhận chéo. Leader: chỉ nhận tin, không tính tải việc.",
                     className="desc"),
            html.Div([
                field("Vai trò", dcc.Dropdown(id="ld-nn-vt", options=[{"label": "Sale (5 bạn Online)", "value": "sale"},
                                                                      {"label": "Leader", "value": "leader"}],
                                              value="leader", clearable=False, style={"minWidth": "160px"})),
                field("Tên", dcc.Input(id="ld-nn-ten", className="inp")),
                field("Acc (chỉ khi là Sale)", dcc.Dropdown(id="ld-nn-acc", options=opt_sale)),
                field("Chat ID Zalo", dcc.Input(id="ld-nn-chatid", className="inp")),
                field(" ", html.Button([icon("plus", 14), html.Span("Thêm người nhận")], id="ld-nn-them",
                                       className="btn primary")),
            ], className="toolbar", style={"flexWrap": "wrap"}),
            html.Div(id="ld-nn-msg"),
            bang("ld-g-nn", [
                {"field": "vai_tro", "headerName": "Vai trò", "width": 90, "checkboxSelection": True},
                {"field": "ten", "headerName": "Tên", "minWidth": 130, "flex": 1},
                {"field": "acc_norm", "headerName": "Acc", "minWidth": 110, "flex": 1},
                {"field": "chat_id", "headerName": "Chat ID", "minWidth": 120, "flex": 1},
                {"field": "bat", "headerName": "Đang bật", "width": 90},
            ], cao=220, getRowId="params.data.id", tuy_chon={"rowSelection": "multiple"}),
            html.Button([icon("trash", 14), html.Span("Xoá người nhận đã chọn")], id="ld-nn-xoa",
                        className="btn nguy-hiem", style={"marginTop": "8px"}),

            html.H3("Kết nối Messenger (tự bắt lead)", style={"margin": "18px 0 4px"}),
            html.Div("Tạo Meta App + lấy Page Access Token trên Meta for Developers (ngoài app). Dán vào đây rồi "
                     "bấm Đăng ký webhook - app tự gọi Facebook, không cần vào Business Suite.", className="desc"),
            html.Div([
                field("Page", dcc.Dropdown(id="ld-fb-page", options=opt_page, style={"minWidth": "180px"})),
                field("Facebook Page ID", dcc.Input(id="ld-fb-id", className="inp")),
                field("Page Access Token", dcc.Input(id="ld-fb-token", className="inp", type="password")),
                field(" ", html.Button([icon("save", 14), html.Span("Lưu kết nối")], id="ld-fb-luu",
                                       className="btn primary")),
                field(" ", html.Button([icon("refresh", 14), html.Span("Đăng ký webhook")], id="ld-fb-dangky",
                                       className="btn")),
            ], className="toolbar", style={"flexWrap": "wrap"}),
            html.Div(id="ld-fb-msg"),
        ], className="chu-giai", style={"marginTop": "10px"}),
    ], className="card")


# Mascot AI nhỏ (chốt 20/11/2026, chủ app muốn nhìn "có con AI đang hoạt động" ở riêng chỗ này): tự vẽ
# bằng SVG gốc (không chép ảnh mẫu chủ app đưa - ảnh đó có bản quyền của bên khác), có gradient + glow -
# PHÁ LỆ chỉ riêng icon này, phần chữ còn lại của dải vẫn phẳng như cả app (`app/ui/icons.py` vẫn chỉ 1 màu
# cho mọi icon khác, đừng thêm icon nhiều màu vào đó).
_AI_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
           '<defs>'
           '<linearGradient id="g1" x1="0" y1="0" x2="1" y2="1">'
           '<stop offset="0" stop-color="#8B5CF6"/><stop offset="1" stop-color="#2563EB"/>'
           '</linearGradient>'
           '<radialGradient id="g2" cx="0.5" cy="0.35" r="0.65">'
           '<stop offset="0" stop-color="#A5F3FC"/><stop offset="1" stop-color="#0EA5E9"/>'
           '</radialGradient>'
           '</defs>'
           '<circle cx="32" cy="32" r="30" fill="url(#g1)"/>'
           '<circle cx="13" cy="31" r="4.2" fill="#C4B5FD"/>'
           '<circle cx="51" cy="31" r="4.2" fill="#C4B5FD"/>'
           '<rect x="17" y="19" width="30" height="25" rx="11" fill="#111827" opacity="0.92"/>'
           '<circle cx="26" cy="31.5" r="4.4" fill="url(#g2)"/>'
           '<circle cx="38" cy="31.5" r="4.4" fill="url(#g2)"/>'
           '<path d="M24 40q8 5.5 16 0" stroke="#7DD3FC" stroke-width="2.2" fill="none" stroke-linecap="round"/>'
           '<line x1="32" y1="11" x2="32" y2="17" stroke="#C4B5FD" stroke-width="2.4" stroke-linecap="round"/>'
           '<circle cx="32" cy="9" r="3" fill="#7DD3FC"/>'
           '</svg>')
_AI_AVATAR_URI = f'url("data:image/svg+xml,{quote(_AI_SVG)}")'


def _ai_avatar(cham: str) -> html.Div:
    return html.Div(html.Span(className=f"ld-dot {cham}"), className="ld-ai-avatar",
                     style={"backgroundImage": _AI_AVATAR_URI})


def _nut_pipeline(ten_icon: str, nhan: str, so, mau: str = "") -> html.Div:
    return html.Div([html.Div(icon(ten_icon, 18), className="ld-node-ico"),
                      html.Div(f"{so}", className="ld-node-so"), html.Div(nhan, className="ld-node-nhan")],
                     className=f"ld-node {mau}".strip())


def _pipeline(tong: int, mo: int, qua_han: int, da_bao) -> html.Div:
    """Sơ đồ 4 bước AI đang chạy thật (chốt 21/11/2026, chủ app muốn trông "máy móc" hơn): Quét lead (tổng
    đang có) -> Phát hiện quá hạn (số thật đang hiện) -> Báo Zalo (số của lần quét cron gần nhất, không
    phải lần này) -> Đang xử lý (sale chưa đóng). Mọi số lấy từ cùng nguồn với KPI/dải chữ bên trên, không
    có số nào vẽ thêm cho đẹp."""
    return html.Div([
        _nut_pipeline("search", "Quét lead", tong),
        html.Div(className="ld-link"),
        _nut_pipeline("alert", "Quá hạn", qua_han, "canh-bao" if qua_han else ""),
        html.Div(className="ld-link"),
        _nut_pipeline("zap", "Đã báo Zalo", da_bao if da_bao is not None else "–"),
        html.Div(className="ld-link"),
        _nut_pipeline("user", "Đang xử lý", mo),
    ], className="ld-pipeline")


def _dai_trang_thai(df) -> html.Div:
    """Dải "đang theo dõi" phía trên bảng (chủ app muốn 20/11/2026 cảm giác có AI điều phối lead, cảnh báo
    lead bị bỏ sót; 21/11/2026 thêm sơ đồ quy trình cho "ra dáng AI Agent"). Số liệu THẬT tính từ chính
    `df` đang hiện và `AuditLog` của `canh_bao_lead.quet_va_canh_bao` (cron 15-30 phút/lần) - không phải
    số dựng cho đẹp. Chấm góc dưới của avatar mới là tín hiệu thật (xanh/đỏ theo `qua_han`), mascot chỉ để
    gợi cảm giác "đang hoạt động"."""
    tong = len(df)
    mo = int((~df.tinh_trang_xu_ly.isin(leads.TRANG_THAI_DONG)).sum()) if tong else 0
    qua_han = int(df.qua_han.sum()) if tong else 0
    lan = cb.lan_quet_gan_nhat()
    if qua_han:
        dong1 = (f"{qua_han} lead đang quá {leads.han_sla_gio():g}h chưa chăm sóc - hệ thống tự nhắc qua Zalo "
                 f"mỗi {cb.CHU_KY_NHAC_LAI_GIO}h cho người phụ trách")
        cham = "canh-bao"
    else:
        dong1 = "Đang theo dõi, chưa có lead nào quá hạn care"
        cham = "on"
    dong2 = (f"Quét SLA lần gần nhất lúc {chu_gio_vn(lan['luc'])} · {lan['chi_tiet']}" if lan
             else "Chưa có lượt quét SLA nào.")
    return html.Div([
        html.Div([
            _ai_avatar(cham),
            html.Div([html.Div(dong1, className="ld-dong-1"), html.Div(dong2, className="ld-dong-2")]),
        ], className="ld-trang-thai-hang"),
        _pipeline(tong, mo, qua_han, lan.get("da_bao") if lan else None),
    ], className="ld-trang-thai")


def _kpi(df) -> list:
    tong = len(df)
    mo = int((~df.tinh_trang_xu_ly.isin(leads.TRANG_THAI_DONG)).sum()) if tong else 0
    qua_han = int(df.qua_han.sum()) if tong else 0
    from app.ui.components import kpi
    return [kpi("Tổng lead", f"{tong}"), kpi("Đang xử lý", f"{mo}"),
            kpi("Quá hạn care", f"{qua_han}", f"Trên {leads.han_sla_gio():g}h chưa chăm sóc", "bad" if qua_han else "ok")]


def register(app):
    @app.callback(Output("ld-kpi", "children"), Output("ld-trang-thai", "children"), Output("ld-luoi", "rowData"),
                  Input("ld-loc-page", "value"), Input("ld-loc-sale", "value"), Input("ld-loc-tt", "value"),
                  Input("ld-da-luu", "data"))
    def _nap(page_id, sale, tt, _luu):
        if not _duoc_xem():
            raise PreventUpdate
        df = leads.danh_sach(page_id=page_id, sale=sale, tinh_trang=tt)
        if df.empty:
            return _kpi(df), _dai_trang_thai(df), []
        out = df.assign(ngay=[str(x)[:10] for x in df.ngay])
        return _kpi(df), _dai_trang_thai(df), out.to_dict("records")

    @app.callback(Output("ld-luoi", "dashGridOptions"), Input("ld-tim", "value"), prevent_initial_call=True)
    def _tim(chu):
        from dash import Patch
        p = Patch()
        p["quickFilterText"] = chu or ""
        return p

    @app.callback(Output("ld-md", "className", allow_duplicate=True),
                  Output("ld-md-msg", "children", allow_duplicate=True),
                  Input("ld-them-mo", "n_clicks"), Input("ld-md-dong", "n_clicks"), Input("ld-md-huy", "n_clicks"),
                  Input("ld-da-luu", "data"), prevent_initial_call=True)
    def _mo_dong(_a, _b, _c, _d):
        return ("modal mo" if ctx.triggered_id == "ld-them-mo" else "modal"), ""

    @app.callback(Output("ld-md-msg", "children", allow_duplicate=True),
                  Output("ld-da-luu", "data", allow_duplicate=True), Output("ld-md", "className", allow_duplicate=True),
                  Input("ld-md-ok", "n_clicks"),
                  State("ld-f-page", "value"), State("ld-f-ngay", "value"), State("ld-f-ten", "value"),
                  State("ld-f-sdt", "value"), State("ld-f-tt", "value"), State("ld-f-sale", "value"),
                  State("ld-f-ghichu", "value"), prevent_initial_call=True)
    def _them(_n, page_id, ngay, ten, sdt, tt, sale, ghichu):
        if not _duoc_xem():
            raise PreventUpdate
        if not ngay:
            return alert("Chưa chọn ngày.", "warn"), no_update, no_update
        try:
            leads.tao_lead({"page_id": page_id, "ngay": ngay, "ten_kh": ten, "sdt": sdt,
                            "tinh_trang_xu_ly": tt, "sale_1": sale, "ghi_chu": ghichu}, current_user.username)
        except leads.LoiLead as e:
            return alert(str(e), "bad"), no_update, no_update
        return "", gio_viet_nam().isoformat(), "modal"

    @app.callback(Output("ld-msg", "children"), Output("ld-da-luu", "data", allow_duplicate=True),
                  Input("ld-luoi", "cellValueChanged"), prevent_initial_call=True)
    def _luu_o(doi):
        if not _duoc_xem():
            raise PreventUpdate
        doi = doi if isinstance(doi, list) else [doi] if doi else []
        ten_acc = {a["ten"]: a["acc_norm"] for a in leads.nguoi_online()}
        loi = []
        for d in doi:
            r, cot, moi = d.get("data") or {}, d.get("colId"), d.get("value")
            lead_id = r.get("id")
            if not lead_id or not cot:
                continue
            try:
                if cot in ("sale_1_ten", "sale_2_ten", "sale_3_ten"):
                    leads.nhan_cheo(lead_id, ten_acc.get(moi), current_user.username)
                else:
                    leads.cap_nhat_lead(lead_id, {cot: moi}, current_user.username)
            except leads.LoiLead as e:
                loi.append(str(e))
        return (alert(" ".join(loi), "bad") if loi else None), gio_viet_nam().isoformat()

    @app.callback(Output("ld-xoa-xacnhan", "displayed"), Output("ld-xoa-xacnhan", "message"),
                  Output("ld-msg", "children", allow_duplicate=True),
                  Input("ld-xoa-mo", "n_clicks"), State("ld-luoi", "selectedRows"), prevent_initial_call=True)
    def _hoi_xoa(_n, chon):
        if not _duoc_xem():
            raise PreventUpdate
        if not chon:
            return False, "", alert("Tích ô # của (các) lead cần xoá trước đã.", "warn")
        return True, f"Xoá {len(chon)} lead đã chọn? Thao tác này không hoàn tác được.", no_update

    @app.callback(Output("ld-msg", "children", allow_duplicate=True),
                  Output("ld-da-luu", "data", allow_duplicate=True),
                  Input("ld-xoa-xacnhan", "submit_n_clicks"), State("ld-luoi", "selectedRows"),
                  prevent_initial_call=True)
    def _xoa(_n, chon):
        if not _duoc_xem() or not chon:
            raise PreventUpdate
        n = leads.xoa_lead([r["id"] for r in chon], current_user.username)
        return alert(f"Đã xoá {n} lead.", "ok"), gio_viet_nam().isoformat()

    # ------------------------------------------------ cấu hình (admin)
    @app.callback(Output("ld-g-page", "rowData"), Output("ld-fb-page", "options"), Output("ld-f-page", "options"),
                  Output("ld-loc-page", "options"), Output("ld-g-nn", "rowData"),
                  Input("ld-da-luu", "data"), Input("ld-pg-msg", "children"), Input("ld-nn-msg", "children"),
                  Input("ld-fb-msg", "children"))
    def _nap_cau_hinh(*_a):
        if not current_user.duoc_cau_hinh:
            raise PreventUpdate
        pages = leads.ds_page()
        opt = [{"label": t, "value": i} for i, t in zip(pages.id, pages.ten)] if len(pages) else []
        return (pages.to_dict("records") if len(pages) else [], opt, opt, opt, cb.ds_nguoi_nhan())

    @app.callback(Output("ld-pg-msg", "children", allow_duplicate=True), Output("ld-pg-ten", "value"),
                  Output("ld-pg-ghichu", "value"),
                  Input("ld-pg-them", "n_clicks"), State("ld-pg-ten", "value"), State("ld-pg-ghichu", "value"),
                  prevent_initial_call=True)
    def _them_page(_n, ten, ghi_chu):
        if not current_user.duoc_cau_hinh:
            raise PreventUpdate
        try:
            msg = leads.them_page(ten, ghi_chu, current_user.username)
        except leads.LoiLead as e:
            return alert(str(e), "bad"), no_update, no_update
        return alert(msg, "ok"), "", ""

    @app.callback(Output("ld-pg-msg", "children", allow_duplicate=True),
                  Input("ld-pg-luu", "n_clicks"), State("ld-g-page", "rowData"), prevent_initial_call=True)
    def _luu_page(_n, rows):
        if not current_user.duoc_cau_hinh:
            raise PreventUpdate
        n = 0
        for r in rows or []:
            try:
                leads.sua_page(r["id"], r.get("ten"), r.get("ghi_chu"), bool(r.get("active", True)),
                               current_user.username)
                n += 1
            except leads.LoiLead as e:
                return alert(str(e), "bad")
        return alert(f"Đã lưu {n} page.", "ok")

    @app.callback(Output("ld-sla-msg", "children"), Output("ld-da-luu", "data", allow_duplicate=True),
                  Input("ld-sla-luu", "n_clicks"),
                  State("ld-sla-so", "value"), State("ld-sla-dv", "value"), prevent_initial_call=True)
    def _luu_sla(_n, so_luong, don_vi):
        if not current_user.duoc_cau_hinh:
            raise PreventUpdate
        if not so_luong or so_luong <= 0:
            return alert("Nhập số lượng lớn hơn 0.", "warn"), no_update
        gio = leads.luu_han_sla_gio(float(so_luong) * (24 if don_vi == "ngay" else 1), current_user.username)
        so, dv = _sla_hien_thi(gio)
        return (alert(f"Đã lưu: lead chưa chăm sóc quá {so:g} {'ngày' if dv == 'ngay' else 'giờ'} thì tính quá hạn.", "ok"),
                gio_viet_nam().isoformat())

    @app.callback(Output("ld-nn-msg", "children", allow_duplicate=True), Output("ld-nn-ten", "value"),
                  Output("ld-nn-chatid", "value"),
                  Input("ld-nn-them", "n_clicks"), State("ld-nn-vt", "value"), State("ld-nn-ten", "value"),
                  State("ld-nn-chatid", "value"), State("ld-nn-acc", "value"), prevent_initial_call=True)
    def _them_nguoi_nhan(_n, vt, ten, chat_id, acc):
        if not current_user.duoc_cau_hinh:
            raise PreventUpdate
        ok, msg = cb.luu_nguoi_nhan(None, vt, ten, chat_id, acc, True, current_user.username)
        if not ok:
            return alert(msg, "bad"), no_update, no_update
        return alert(msg, "ok"), "", ""

    @app.callback(Output("ld-nn-msg", "children", allow_duplicate=True),
                  Input("ld-nn-xoa", "n_clicks"), State("ld-g-nn", "selectedRows"), prevent_initial_call=True)
    def _xoa_nguoi_nhan(_n, chon):
        if not current_user.duoc_cau_hinh:
            raise PreventUpdate
        if not chon:
            return alert("Chọn người nhận cần xoá.", "warn")
        n = cb.xoa_nguoi_nhan([r["id"] for r in chon], current_user.username)
        return alert(f"Đã xoá {n} người nhận.", "ok")

    @app.callback(Output("ld-fb-msg", "children", allow_duplicate=True), Input("ld-fb-luu", "n_clicks"),
                  State("ld-fb-page", "value"), State("ld-fb-id", "value"), State("ld-fb-token", "value"),
                  prevent_initial_call=True)
    def _luu_fb(_n, page_id, fb_id, token):
        if not current_user.duoc_cau_hinh:
            raise PreventUpdate
        if not page_id:
            return alert("Chọn page trước.", "warn")
        try:
            msg = leads.luu_fb_cau_hinh(page_id, fb_id, token, current_user.username)
        except leads.LoiLead as e:
            return alert(str(e), "bad")
        ghi_log("lead_fb_cau_hinh", f"page {page_id}")
        return alert(msg, "ok")

    @app.callback(Output("ld-fb-msg", "children", allow_duplicate=True), Input("ld-fb-dangky", "n_clicks"),
                  State("ld-fb-page", "value"), prevent_initial_call=True)
    def _dang_ky(_n, page_id):
        if not current_user.duoc_cau_hinh:
            raise PreventUpdate
        if not page_id:
            return alert("Chọn page trước.", "warn")
        from app.db import session_scope
        from app.models import CrmPage
        with session_scope() as s:
            p = s.get(CrmPage, int(page_id))
            fb_page_id, token = (p.fb_page_id, p.page_access_token) if p else (None, None)
        if not fb_page_id or not token:
            return alert("Page này chưa lưu Facebook Page ID / Page Access Token.", "warn")
        from app import leads_messenger as lm
        try:
            msg = lm.dang_ky_webhook(fb_page_id, token)
        except lm.LoiMessenger as e:
            return alert(str(e), "bad")
        ghi_log("lead_fb_dang_ky", f"page {page_id}")
        return alert(msg, "ok")
