"""Trang Cập nhật Excel của khối DVKH: tải file báo cáo DVKH lên, xem trước, lưu; lịch sử các lần nạp.

File thật nặng 15 MB. Trên Vercel mỗi yêu cầu chỉ nhận được vài MB nên ở đó chỉ nạp bằng lệnh `python scripts/nap_dvkh.py` (cùng hàm
`app.dvkh.nap.nap_file`); chạy app trên máy chủ riêng thì tải thẳng ở trang này.
"""
from __future__ import annotations

import base64
import hashlib
from datetime import date

from dash import Input, Output, State, dcc, html

from app.config import GIOI_HAN_NAP_MB
from app.dvkh import doc_file, nap
from app.thoi_gian import chu_gio_vn, gio_viet_nam
from app.ui.components import alert, callback_can_quyen, card
from app.ui.icons import icon
from app.ui.pages import dvkh_chung as ch

_NHO: dict[str, dict] = {}            # kết quả đọc file giữ tạm theo mã băm nội dung; luôn có đường đọc lại nếu máy chủ khác nhận bấm Lưu


def topbar():
    return [html.Div([html.H1("Cập nhật Excel"), html.Div("Nạp file báo cáo DVKH, xem lịch sử các lần nạp", className="sub")])]


def layout():
    mb = int(GIOI_HAN_NAP_MB)
    return html.Div([
        card([
            dcc.Upload(id="dvnap-file", multiple=False, className="upload-zone", children=html.Div([
                html.Div([icon("upload", 26)], style={"marginBottom": "6px"}),
                html.Div([html.B("Chọn file Excel báo cáo DVKH"), " hoặc kéo thả vào đây"]),
                html.Div(f"Định dạng .xlsx, tối đa {mb} MB mỗi lần tải. File lớn hơn nạp bằng lệnh (xem hướng dẫn bên dưới).",
                         style={"fontSize": "12px", "marginTop": "4px"})])),
            html.Div([html.Div([html.Label("Ngày chốt báo cáo"), dcc.DatePickerSingle(id="dvnap-ngay", date=gio_viet_nam().date(), display_format="DD/MM/YYYY",
                                                                                       className="dv-ngay")], className="field"),
                      html.Div(className="grow"),
                      html.Button([icon("save", 14), html.Span("Lưu vào hệ thống")], id="dvnap-luu", className="btn primary", disabled=True, n_clicks=0,
                                  style={"alignSelf": "flex-end"})], className="toolbar", style={"marginTop": "14px", "marginBottom": "0"}),
            html.Div(id="dvnap-xem-truoc", style={"marginTop": "12px"}),
            html.Div(id="dvnap-ket-qua", style={"marginTop": "12px"}),
        ], title="Tải file lên", desc="File có đủ các sheet: SR bị động, SR chủ động, rời mạng, công nợ, data. App đọc theo tên cột nên thứ tự cột đổi được."),
        html.Div(style={"height": "16px"}),
        card([html.Ul([
            html.Li("Mỗi mã SR chỉ tính một lần: nạp lại file mới hơn thì SR đã có được cập nhật theo trạng thái mới nhất, không bị cộng dồn."),
            html.Li("Rời mạng và công nợ lưu theo ngày chốt. Nạp lại cùng ngày chốt thì ghi đè, khác ngày thì giữ cả hai để vẽ xu hướng."),
            html.Li("Hai danh sách trong sheet data (YCH, nợ cước) được thay mới mỗi lần nạp."),
            html.Li(["Nạp bằng lệnh khi file nặng hoặc app chạy trên Vercel: ", html.Code("python scripts/nap_dvkh.py \"đường dẫn file.xlsx\" --ngay 2026-10-21")])],
                       className="dv-huong-dan")], title="Hướng dẫn"),
        html.Div(style={"height": "16px"}),
        card([html.Div(id="dvnap-lich-su")], title="Lịch sử cập nhật", desc="30 lần nạp gần nhất"),
    ])


def _doc(noi_dung: str) -> tuple[dict, str]:
    """(kết quả đọc, mã băm); dùng bộ nhớ tạm nếu đã đọc đúng nội dung này."""
    b = base64.b64decode(noi_dung.split(",", 1)[1])
    ma = hashlib.sha1(b).hexdigest()
    if ma not in _NHO:
        if len(_NHO) >= 2:
            _NHO.clear()
        _NHO[ma] = doc_file.doc_file(b)
    return _NHO[ma], ma


def _bang_lich_su() -> html.Div:
    ds = nap.lich_su(30)
    if not ds:
        return html.Div("Chưa có lần nạp nào.", className="desc")
    cot = [ch.cot_chu("ngay_chot_chu", "Ngày chốt", 110), ch.cot_chu("nap_luc_chu", "Nạp lúc", 140), ch.cot_chu("nap_boi", "Người nạp", 120),
           ch.cot_chu("ten_file", "File", None), ch.cot_so("so_sr_bd", "SR bị động", 110), ch.cot_so("so_sr_cd", "SR chủ động", 120),
           ch.cot_chu("tg_sr_bd_chu", "SR BĐ tới", 110), ch.cot_chu("tg_sr_cd_chu", "SR CĐ tới", 110)]
    import pandas as pd
    df = pd.DataFrame(ds)
    df["ngay_chot_chu"] = pd.to_datetime(df["ngay_chot"]).dt.strftime("%d/%m/%Y")
    df["nap_luc_chu"] = [chu_gio_vn(v, "%H:%M %d/%m/%Y") for v in df["nap_luc"]]
    df["tg_sr_bd_chu"] = pd.to_datetime(df["tg_sr_bd"]).dt.strftime("%d/%m %H:%M")
    df["tg_sr_cd_chu"] = pd.to_datetime(df["tg_sr_cd"]).dt.strftime("%d/%m %H:%M")
    return ch.bang_df("dvnap-bang", df, cot, 320)


def register(app):
    @app.callback(Output("dvnap-lich-su", "children"), Input("dvnap-ket-qua", "children"), Input("dvnap-file", "id"))
    def _lich_su(_a, _b):
        return _bang_lich_su()

    @callback_can_quyen(app, "duoc_nap_dvkh")(Output("dvnap-xem-truoc", "children"), Output("dvnap-luu", "disabled"), Input("dvnap-file", "contents"),
                                                State("dvnap-file", "filename"), prevent_initial_call=True)
    def _xem_truoc(noi_dung, ten):
        if not noi_dung:
            return None, True
        if len(noi_dung) * 3 / 4 > GIOI_HAN_NAP_MB * 1024 * 1024:
            return alert(f"File “{ten}” lớn hơn {int(GIOI_HAN_NAP_MB)} MB. Nạp bằng lệnh: python scripts/nap_dvkh.py \"đường dẫn file\".", "warn"), True
        try:
            kq, _ = _doc(noi_dung)
        except Exception as e:                                                 # file sai định dạng
            return alert(f"Không đọc được file: {type(e).__name__}. Kiểm tra lại file Excel.", "bad"), True
        bd, cd = kq["sr_bd"], kq["sr_cd"]
        dong = [html.Li(f"SR bị động: {len(bd):,} dòng".replace(",", ".") + (f", từ {bd['tg_yc'].min():%d/%m} đến {bd['tg_yc'].max():%d/%m/%Y}" if len(bd) else "")),
                html.Li(f"SR chủ động: {len(cd):,} dòng".replace(",", ".") + (f", từ {cd['tg_do'].min():%d/%m} đến {cd['tg_do'].max():%d/%m/%Y}" if len(cd) else "")),
                html.Li(f"Rời mạng: {len(kq['roi_mang'])} dòng · Công nợ theo ngày: {len(kq['chuoi_cong_no'])} dòng · Ảnh chụp công nợ: {len(kq['chot_cong_no'])} dòng"),
                html.Li(f"Danh sách YCH: {len(kq['ych']):,} hợp đồng · nợ cước: {len(kq['no_cuoc']):,} hợp đồng".replace(",", "."))]
        loi = [html.Li(c) for c in kq["canh_bao"]]
        hop_le = not (bd.empty and cd.empty)
        return html.Div([alert([html.B(f"Đã đọc file “{ten}”"), html.Ul(dong)], "ok" if hop_le else "warn"),
                         alert(html.Ul(loi), "warn") if loi else None]), not hop_le

    @callback_can_quyen(app, "duoc_nap_dvkh")(Output("dvnap-ket-qua", "children"), Input("dvnap-luu", "n_clicks"), State("dvnap-file", "contents"),
                                                State("dvnap-file", "filename"), State("dvnap-ngay", "date"), running=[(Output("dvnap-luu", "disabled"), True, False)],
                                                prevent_initial_call=True)
    def _luu(n, noi_dung, ten, ngay):
        from flask_login import current_user
        if not n or not noi_dung:
            return None
        try:
            kq, _ = _doc(noi_dung)
            r = nap.nap(kq, date.fromisoformat(str(ngay)[:10]), ten or "file DVKH", current_user.username)
        except Exception as e:                                                 # không để lỗi lạ làm treo nút
            return alert(f"Chưa lưu được: {type(e).__name__}. Thử lại hoặc nạp bằng lệnh.", "bad")
        return alert([html.B("Đã lưu. "), f"SR bị động {r['sr_bd']:,} · SR chủ động {r['sr_cd']:,} · rời mạng {r['roi_mang']} · công nợ {r['cong_no']}".replace(",", ".")], "ok")
