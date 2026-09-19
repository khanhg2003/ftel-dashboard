"""Ads IBB7 - tab Cấu hình: kết nối n8n / bot, nạp file sheet cũ, người chạy page, danh mục page, sale và acc,
nhập tay, nhật ký lead. Tách khỏi app/ui/pages/ads.py cho gọn; chỉ Quản trị (callback kiểm quyền qua `cb`)."""
from __future__ import annotations

import base64
import json
from datetime import date

from dash import Input, Output, State, ctx, dcc, html, no_update
from flask_login import current_user

from app import ads
from app.auth import ghi_log
from app.thoi_gian import gio_viet_nam
from app.ui.components import alert, field
from app.ui.icons import icon
from app.ui.luoi import PCT
from app.ui.pages.ads import SO, _ban_ghi, _grid, _ky, _so, _the


def layout():
    return [
        _the("Kết nối n8n và bot Telegram", "n8n gửi thẳng vào app thay cho Google Sheet. Gửi lại cùng page + camp "
             "+ ngày thì ghi đè, không nhân đôi. Page mới tự xuất hiện ở danh mục bên dưới.",
             html.Div(id="ads-token-tt"),
             html.Details([html.Summary("Xem mẫu gửi dữ liệu (cho người cài n8n)", className="cg-tieu-de"),
                           html.Pre(id="ads-mau-json", className="khoi-ma")], className="chu-giai"),
             nut=html.Button([icon("refresh", 14), html.Span("Tạo mã kết nối mới")], id="ads-tao-ma",
                             className="btn")),
        _the("Nạp file Google Sheet cũ", "Tải file 'BÁO CÁO CHI TIÊU ADS' (File → Download → .xlsx, một file gồm mọi "
             "tab) rồi thả vào đây: chi tiêu, lead / PTTB, người chạy từng page, tỷ lệ chia riêng. Chỉ dùng cho tháng "
             "chưa nối n8n - nạp lại tháng đã có bot gửi lead sẽ cộng trùng lead.",
             dcc.Upload(id="ads-file", className="upload-zone", children=html.Div(
                 [icon("upload", 18), html.Span(" Kéo thả hoặc bấm chọn file .xlsx")])),
             dcc.Loading(html.Div(id="ads-msg-file"), type="dot")),
        _the("Người chạy page (PIC)", "Khai ai chạy page từ ngày nào. Đổi người giữa tháng: chọn page, chọn nhóm sale "
             "mới và ngày bắt đầu - khai báo cũ tự kết thúc ở ngày trước đó. Tối đa 3 sale; để trống tỷ lệ = chia đều.",
             html.Div([
                 field("Page", dcc.Dropdown(id="ads-pic-page", style={"minWidth": "220px"})),
                 field("Sale (tối đa 3)", dcc.Dropdown(id="ads-pic-sale", multi=True, style={"minWidth": "240px"})),
                 field("Sale mới (chưa có trong danh sách)", dcc.Input(id="ads-pic-moi", className="inp",
                                                                        placeholder="VD: C. Lan")),
                 field("Tỷ lệ % (theo thứ tự sale)", dcc.Input(id="ads-pic-tl", className="inp",
                                                              placeholder="trống = chia đều · VD 70, 30")),
                 field("Từ ngày", dcc.DatePickerSingle(id="ads-pic-tu", display_format="DD/MM/YYYY",
                                                       first_day_of_week=1)),
                 field("Đến ngày (trống = đến nay)", dcc.DatePickerSingle(id="ads-pic-den", display_format="DD/MM/YYYY",
                                                                          first_day_of_week=1, clearable=True)),
                 field(" ", html.Button([icon("plus", 14), html.Span("Lưu phân công")], id="ads-pic-luu",
                                        className="btn primary")),
             ], className="toolbar", style={"flexWrap": "wrap"}),
             html.Div(id="ads-msg-pic"),
             _grid("ads-g-pic", [
                 {"field": "page", "headerName": "Page", "minWidth": 190, "flex": 2, "checkboxSelection": True},
                 {"field": "sale", "headerName": "Sale", "minWidth": 120, "flex": 1},
                 {"field": "tu", "headerName": "Từ ngày", "minWidth": 110},
                 {"field": "den", "headerName": "Đến ngày", "minWidth": 110},
                 _so("Tỷ lệ", "ty_le", PCT, 80)], cao=320, getRowId="params.data.id",
                 opts={"rowSelection": "multiple"}),
             nut=html.Button([icon("trash", 14), html.Span("Xoá dòng đã chọn")], id="ads-pic-xoa",
                             className="btn nguy-hiem")),
        _the("Danh mục page", "Bấm đúp ô có dấu ✎ để sửa rồi Lưu. Loại 'Công ty' = chạy tài khoản công ty, không chia "
             "chi phí cho sale. Tên chuẩn là tên n8n / bot gửi lên - không sửa được.",
             _grid("ads-g-dm", [
                 {"field": "ma", "headerName": "Tên chuẩn (n8n gửi)", "minWidth": 180, "flex": 1.3},
                 {"field": "ten", "headerName": "Tên hiển thị ✎", "editable": True, "minWidth": 190, "flex": 1.6},
                 {"field": "link", "headerName": "Link fanpage ✎", "editable": True, "minWidth": 200, "flex": 1.6},
                 {"field": "loai", "headerName": "Loại ✎", "editable": True, "minWidth": 100,
                  "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": ["Sale", "Công ty"]}},
                 {"field": "tinh_trang", "headerName": "Tình trạng ✎", "editable": True, "minWidth": 115,
                  "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": ads.TINH_TRANG_PAGE}},
                 {"field": "ghi_chu", "headerName": "Ghi chú ✎", "editable": True, "minWidth": 180, "flex": 1.6},
             ], cao=380, getRowId="params.data.id"),
             html.Details([
                 html.Summary("+ Thêm page mới", className="cg-tieu-de"),
                 html.Div([
                     field("Tên chuẩn (n8n / bot gửi)", dcc.Input(id="ads-pm-ma", className="inp",
                                                                   placeholder="VD: BÌNH PHƯỚC")),
                     field("Tên hiển thị", dcc.Input(id="ads-pm-ten", className="inp", placeholder="trống = như tên chuẩn")),
                     field("Loại", dcc.Dropdown(id="ads-pm-loai", value="sale", clearable=False, searchable=False,
                                                options=[{"label": "Sale", "value": "sale"},
                                                         {"label": "Công ty (Trung lập)", "value": "cong_ty"}],
                                                style={"minWidth": "170px"})),
                     field("Tình trạng", dcc.Dropdown(id="ads-pm-tt", value="Đang chạy", clearable=False,
                                                      searchable=False, style={"minWidth": "130px"},
                                                      options=[{"label": x, "value": x} for x in ads.TINH_TRANG_PAGE])),
                     field("Link fanpage", dcc.Input(id="ads-pm-link", className="inp",
                                                     placeholder="https://www.facebook.com/…")),
                     field(" ", html.Button([icon("plus", 14), html.Span("Thêm page")], id="ads-pm-them",
                                            className="btn primary")),
                 ], className="toolbar", style={"flexWrap": "wrap", "marginTop": "8px"}),
                 html.Div("Tên chuẩn phải đúng tên n8n / bot Telegram sẽ gửi (không phân biệt hoa thường, khoảng trắng)"
                          " để số tự vào đúng page. Thêm xong nhớ khai người chạy page ở mục trên.",
                          className="ghi-chu-nhan"),
             ], className="chu-giai", style={"marginTop": "10px"}),
             html.Div(id="ads-msg-pm"),
             html.Div(id="ads-trung-ten"),
             html.Div(id="ads-msg-dm"),
             nut=html.Button([icon("save", 14), html.Span("Lưu danh mục")], id="ads-dm-luu", className="btn primary")),
        _the("Sale và acc", "Danh sách sale dùng khi khai người chạy page. Thêm sale mới ở dưới bảng; sửa cột Acc "
             "(bấm đúp) rồi Lưu.",
             _grid("ads-g-sale-acc", [
                 {"field": "ten", "headerName": "Tên gọi", "minWidth": 140, "flex": 1},
                 {"field": "acc", "headerName": "Acc inside ✎", "editable": True, "minWidth": 180, "flex": 1.4}],
                 cao=320, getRowId="params.data.ten"),
             html.Div([
                 field("Tên gọi sale mới", dcc.Input(id="ads-sm-ten", className="inp", placeholder="VD: C. Lan")),
                 field("Acc inside", dcc.Input(id="ads-sm-acc", className="inp", placeholder="VD: DNG.LanNT5")),
                 field(" ", html.Button([icon("plus", 14), html.Span("Thêm sale")], id="ads-sm-them",
                                        className="btn primary")),
             ], className="toolbar", style={"flexWrap": "wrap", "marginTop": "10px"}),
             html.Div(id="ads-msg-acc"),
             nut=html.Button([icon("save", 14), html.Span("Lưu acc")], id="ads-acc-luu", className="btn primary")),
        _the("Nhập tay", "Cho page không có số từ n8n (VD chạy tài khoản khác) hoặc bổ sung lead / PTTB khi bot "
             "Telegram lỗi. Chi tiêu nhập tay cùng page + ngày sẽ ghi đè lần nhập trước.",
             html.Div([
                 field("Page", dcc.Dropdown(id="ads-tay-page", style={"minWidth": "220px"})),
                 field("Ngày", dcc.DatePickerSingle(id="ads-tay-ngay", display_format="DD/MM/YYYY",
                                                    first_day_of_week=1)),
                 field("Chi tiêu (USD)", dcc.Input(id="ads-tay-chi", type="number", min=0, step="any",
                                                   className="inp", style={"width": "110px"})),
                 field("Số ĐT", dcc.Input(id="ads-tay-lead", type="number", step=1, className="inp",
                                          style={"width": "80px"})),
                 field("PTTB", dcc.Input(id="ads-tay-pttb", type="number", step=1, className="inp",
                                         style={"width": "80px"})),
                 field(" ", html.Button([icon("plus", 14), html.Span("Ghi")], id="ads-tay-ghi",
                                        className="btn primary")),
             ], className="toolbar", style={"flexWrap": "wrap"}),
             html.Div(id="ads-msg-tay")),
        _the("Nhật ký lead / PTTB", "Mỗi lần bot Telegram hoặc nhập tay báo có số là một dòng (kèm người nhắn và nội "
             "dung tin). Nhập nhầm thì tick dòng rồi Xoá.",
             _grid("ads-g-lead", [
                 {"field": "ngay", "headerName": "Ngày", "minWidth": 100, "checkboxSelection": True},
                 {"field": "page", "headerName": "Page", "minWidth": 180, "flex": 1.6},
                 _so("Số ĐT", "lead", SO, 70), _so("PTTB", "pttb", SO, 70),
                 {"field": "nguon", "headerName": "Nguồn", "minWidth": 90},
                 {"field": "nguoi", "headerName": "Người nhập", "minWidth": 120},
                 {"field": "ghi_chu", "headerName": "Tin nhắn / ghi chú", "minWidth": 180, "flex": 1.6,
                  "tooltipField": "ghi_chu"},
                 {"field": "luc", "headerName": "Lúc", "minWidth": 140}], cao=380, getRowId="params.data.id",
                 opts={"rowSelection": "multiple"}),
             nut=html.Button([icon("trash", 14), html.Span("Xoá dòng đã chọn")], id="ads-lead-xoa",
                             className="btn nguy-hiem")),
    ]


def _mau_json(host: str) -> str:
    return (f"# 1) n8n - chi tiêu hôm qua (node HTTP Request, method POST)\n"
            f"URL: {host}/api/ads/chi-tieu\nHeader: X-Ads-Token: <mã kết nối>\nBody (JSON):\n"
            + json.dumps({"page": "KON TUM", "rows": [{"camp": "TCDT_KONTUM_4", "tinh_trang": "HOẠT ĐỘNG",
                                                        "ngay": "2026-09-18", "chi_tieu": 4.56, "tin_nhan": 3}]},
                         ensure_ascii=False, indent=2)
            + f"\n\n# 2) bot Telegram - mỗi lần có số điện thoại / PTTB\nURL: {host}/api/ads/lead\n"
              "Header: X-Ads-Token: <mã kết nối>\nBody (JSON):\n"
            + json.dumps({"page": "QUẢNG NGÃI", "lead": 1, "pttb": 1, "ngay": "2026-09-19",
                          "nguoi": "Kiều", "ghi_chu": ""}, ensure_ascii=False, indent=2)
            + f"\n\n# 3) bot Telegram - hỏi báo cáo (GET)\nURL: {host}/api/ads/bao-cao?date=19/09/2026 "
              "(hoặc start_date=..&end_date=..)\nHeader: X-Ads-Token: <mã kết nối>"
            + "\n\n'page' = tên chuẩn của page (cột Tên chuẩn ở Danh mục page). 'ngay' bỏ trống ở lead = hôm nay.")


def register(app, cb):
    # ------------------------------------------------ cấu hình
    @cb(Output("ads-g-pic", "rowData"), Output("ads-g-dm", "rowData"), Output("ads-g-sale-acc", "rowData"),
        Output("ads-g-lead", "rowData"), Output("ads-pic-page", "options"), Output("ads-pic-sale", "options"),
        Output("ads-tay-page", "options"), Output("ads-token-tt", "children"), Output("ads-mau-json", "children"),
        Output("ads-trung-ten", "children"),
        Input("ads-tab", "value"), Input("ads-sua", "data"), State("ads-thang", "value"))
    def _nap_cau_hinh(tab, _s, thang):
        if tab != "cauhinh":
            return (no_update,) * 10
        from flask import request
        pg = ads.ds_page()
        ten = dict(zip(pg.id, pg.ten))
        pic = ads.ds_pic()
        pic["page"] = pic.page_id.map(ten)
        pic["tu"] = [x.strftime("%d/%m/%Y") if x else "" for x in pic.tu_ngay]
        pic["den"] = [x.strftime("%d/%m/%Y") if x and x == x else "đến nay" for x in pic.den_ngay]
        pic = pic.sort_values(["page", "tu_ngay"], ascending=[True, False])
        dm = pg.assign(loai=pg.loai.map({"cong_ty": "Công ty"}).fillna("Sale"))
        tu, den = _ky(thang)
        lg = ads.nhat_ky_lead(tu, den)
        if len(lg):
            lg["ngay"] = [str(x)[:10] for x in lg.ngay]
            lg["luc"] = [str(x)[:16] for x in lg.created_at]
        opt_pg = [{"label": t, "value": int(i)} for i, t in zip(pg.id, pg.ten)]
        sale = ads.ds_sale()
        tt = (html.Span("Đã có mã kết nối. Mã chỉ hiện một lần lúc tạo; mất mã thì tạo mã mới rồi dán lại vào n8n.",
                        className="badge ok") if ads.co_token() else
              html.Span("Chưa có mã kết nối - bấm 'Tạo mã kết nối mới'.", className="badge warn"))
        return (_ban_ghi(pic, ["id", "page", "sale", "tu", "den", "ty_le"]), _ban_ghi(dm),
                _ban_ghi(sale), _ban_ghi(lg), opt_pg, [{"label": x, "value": x} for x in sale.ten], opt_pg, tt,
                _mau_json(request.host_url.rstrip("/")),
                [alert(f"Tên '{t}' đang dùng cho {len(m)} page ({', '.join(m)}) - sửa cho mỗi page một tên riêng.",
                       "warn") for t, m in ads.trung_ten()])

    @cb(Output("ads-token-tt", "children", allow_duplicate=True), Input("ads-tao-ma", "n_clicks"),
        prevent_initial_call=True)
    def _tao_ma(_n):
        tok = ads.tao_token(current_user.username)
        return alert([html.B("Mã kết nối mới (chỉ hiện lần này - dán vào header X-Ads-Token của 2 workflow n8n): "),
                      html.Code(tok, style={"userSelect": "all", "wordBreak": "break-all"})], "ok")

    @cb(Output("ads-msg-file", "children"), Output("ads-sua", "data", allow_duplicate=True),
        Input("ads-file", "contents"), State("ads-file", "filename"), prevent_initial_call=True)
    def _nap_file(noi_dung, ten):
        if not noi_dung:
            return no_update, no_update
        try:
            kq = ads.nap_file_sheet(base64.b64decode(noi_dung.split(",", 1)[1]), current_user.username)
        except ads.LoiAds as e:
            return alert(str(e), "bad"), no_update
        except Exception as e:                                    # file hỏng / không phải xlsx
            return alert(f"Không đọc được file {ten}: {type(e).__name__}", "bad"), no_update
        ghi_log("ads_nap_file", f"{ten}")
        return alert(f"Đã nạp {ten}: {kq['chi_tieu']} dòng chi tiêu ({kq['moi']} mới, {kq['cap_nhat']} cập nhật), "
                     f"{kq['lead']} ngày có lead / PTTB, {kq['pic']} dòng phân công, {kq['page']} page · tháng "
                     f"{', '.join(kq['thang'])}.", "ok"), gio_viet_nam().isoformat()

    @cb(Output("ads-msg-pic", "children"), Output("ads-sua", "data", allow_duplicate=True),
        Input("ads-pic-luu", "n_clicks"), Input("ads-pic-xoa", "n_clicks"),
        State("ads-pic-page", "value"), State("ads-pic-sale", "value"), State("ads-pic-moi", "value"),
        State("ads-pic-tl", "value"), State("ads-pic-tu", "date"), State("ads-pic-den", "date"),
        State("ads-g-pic", "selectedRows"), prevent_initial_call=True)
    def _pic(_a, _b, page, sales, moi, tl, tu, den, chon):
        try:
            if ctx.triggered_id == "ads-pic-xoa":
                if not chon:
                    return alert("Chọn dòng cần xoá (ô vuông đầu dòng).", "warn"), no_update
                n = ads.xoa_pic([r["id"] for r in chon], current_user.username)
                return alert(f"Đã xoá {n} dòng phân công.", "ok"), gio_viet_nam().isoformat()
            ds = list(sales or []) + [x.strip() for x in (moi or "").split(",") if x.strip()]
            if not page or not tu:
                return alert("Chọn page và ngày bắt đầu.", "warn"), no_update
            ty_le = [x.strip() for x in (tl or "").replace(";", ",").split(",") if x.strip()]
            msg = ads.them_pic(int(page), ds, date.fromisoformat(tu[:10]),
                               date.fromisoformat(den[:10]) if den else None, current_user.username,
                               [ads.doc_so(x) for x in ty_le] or None)
        except ads.LoiAds as e:
            return alert(str(e), "bad"), no_update
        return alert(msg, "ok"), gio_viet_nam().isoformat()

    @cb(Output("ads-msg-dm", "children"), Output("ads-sua", "data", allow_duplicate=True),
        Input("ads-dm-luu", "n_clicks"), State("ads-g-dm", "rowData"), prevent_initial_call=True)
    def _luu_dm(_n, rows):
        try:
            n = ads.luu_page([{**r, "loai": "cong_ty" if r.get("loai") == "Công ty" else "sale"}
                              for r in rows or []], current_user.username)
        except ads.LoiAds as e:
            return alert(str(e), "bad"), no_update
        return alert(f"Đã lưu {n} page thay đổi.", "ok"), gio_viet_nam().isoformat()

    @cb(Output("ads-msg-pm", "children"), Output("ads-sua", "data", allow_duplicate=True),
        Output("ads-pm-ma", "value"), Output("ads-pm-ten", "value"), Output("ads-pm-link", "value"),
        Input("ads-pm-them", "n_clicks"), State("ads-pm-ma", "value"), State("ads-pm-ten", "value"),
        State("ads-pm-loai", "value"), State("ads-pm-tt", "value"), State("ads-pm-link", "value"),
        prevent_initial_call=True)
    def _them_page(_n, ma, ten, loai, tt, link):
        try:
            msg = ads.them_page(ma, ten, loai, link, tt, current_user.username)
        except ads.LoiAds as e:
            return alert(str(e), "bad"), no_update, no_update, no_update, no_update
        return alert(msg, "ok"), gio_viet_nam().isoformat(), "", "", ""

    @cb(Output("ads-msg-acc", "children", allow_duplicate=True), Output("ads-sua", "data", allow_duplicate=True),
        Output("ads-sm-ten", "value"), Output("ads-sm-acc", "value"),
        Input("ads-sm-them", "n_clicks"), State("ads-sm-ten", "value"), State("ads-sm-acc", "value"),
        prevent_initial_call=True)
    def _them_sale(_n, ten, acc):
        try:
            msg = ads.them_sale(ten, acc, current_user.username)
        except ads.LoiAds as e:
            return alert(str(e), "bad"), no_update, no_update, no_update
        return alert(msg + " Giờ có thể chọn sale này ở Người chạy page.", "ok"), gio_viet_nam().isoformat(), "", ""

    @cb(Output("ads-msg-acc", "children"), Output("ads-sua", "data", allow_duplicate=True),
        Input("ads-acc-luu", "n_clicks"), State("ads-g-sale-acc", "rowData"), prevent_initial_call=True)
    def _luu_acc(_n, rows):
        n = ads.luu_sale(rows or [], current_user.username)
        return alert(f"Đã lưu {n} acc.", "ok"), gio_viet_nam().isoformat()

    @cb(Output("ads-msg-tay", "children"), Output("ads-sua", "data", allow_duplicate=True),
        Input("ads-tay-ghi", "n_clicks"), State("ads-tay-page", "value"), State("ads-tay-ngay", "date"),
        State("ads-tay-chi", "value"), State("ads-tay-lead", "value"), State("ads-tay-pttb", "value"),
        State("ads-tay-page", "options"), prevent_initial_call=True)
    def _nhap_tay(_n, page, ngay, chi, lead, pttb, opts):
        if not page or not ngay:
            return alert("Chọn page và ngày.", "warn"), no_update
        ten = next((o["label"] for o in opts or [] if o["value"] == page), None)
        ma = ads.ds_page().set_index("id").ma.get(page)
        viec = []
        if chi not in (None, ""):
            ads.nhan_chi_tieu({"page": ma, "camp": "Nhập tay", "ngay": ngay[:10], "chi_tieu": chi,
                               "tinh_trang": "NHẬP TAY"}, nguon="tay", nguoi=current_user.username)
            viec.append(f"chi tiêu {chi} $")
        if lead or pttb:
            kq = ads.nhan_lead({"page": ma, "ngay": ngay[:10], "lead": lead or 0, "pttb": pttb or 0,
                                "nguoi": current_user.username}, nguon="tay", nguoi=current_user.username)
            if kq["loi"]:
                return alert("; ".join(kq["loi"]), "bad"), no_update
            viec.append(f"{lead or 0} số điện thoại, {pttb or 0} PTTB")
        if not viec:
            return alert("Nhập chi tiêu hoặc số điện thoại / PTTB.", "warn"), no_update
        return alert(f"Đã ghi {ten} ngày {ngay[8:10]}/{ngay[5:7]}: {', '.join(viec)}.", "ok"), \
            gio_viet_nam().isoformat()

    @cb(Output("ads-sua", "data", allow_duplicate=True), Input("ads-lead-xoa", "n_clicks"),
        State("ads-g-lead", "selectedRows"), prevent_initial_call=True)
    def _xoa_lead(_n, chon):
        if not chon:
            return no_update
        ads.xoa_lead([r["id"] for r in chon], current_user.username)
        return gio_viet_nam().isoformat()
