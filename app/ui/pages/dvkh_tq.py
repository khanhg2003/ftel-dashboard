"""Trang Tổng quan KPI của khối DVKH: bốn nhóm KPI theo phòng (DNG1, DNG2, tổng Đà Nẵng), so cùng kỳ tháng trước, điểm cần chú ý."""
from __future__ import annotations

from datetime import date

import plotly.graph_objects as go
from dash import Input, Output, dcc, html

from app.dvkh import insight, so_lieu as sl, tong_quan as tq
from app.ui.components import card, seg_control
from app.ui.pages import dvkh_chung as ch

CHE_DO = [("luy_ke", "Luỹ kế tháng"), ("ngay", "Trong ngày")]
COT = ["DNG1", "DNG2", "Tổng DNG", "QNM", "Cùng kỳ tháng trước", "Chênh"]
GHI_CHU_DU_LIEU = ("Số SR lấy từ file mới nhất, mỗi mã SR tính một lần (không cộng các lần nạp). Rời mạng và công nợ là số chốt sẵn trong file. "
                   "“–” là chưa có dữ liệu, không phải kết quả tốt hay xấu. QNM chưa có nguồn dữ liệu.")


def topbar():
    return [html.Div([html.H1("Tổng quan KPI"), html.Div("Rời mạng · Công nợ · SR bị động · SR chủ động, theo ngày và theo phòng", className="sub")])]


def layout():
    nd = sl.ngay_du_lieu()
    ngay = nd["nap"] or date.today()                    # ngày chốt của lần nạp mới nhất; số SR có thể cũ hơn (xem các chip ngày bên dưới)
    return html.Div([
        html.Div([html.Div([html.Label("Ngày xem"), dcc.DatePickerSingle(id="dvtq-ngay", date=ngay, display_format="DD/MM/YYYY",
                                                                         max_date_allowed=date.today(), className="dv-ngay")], className="field"),
                  html.Div([html.Label("Cách xem"), seg_control("dvtq-che-do", CHE_DO, "luy_ke")], className="field"),
                  html.Div(className="grow")], className="toolbar loc-trang"),
        dcc.Loading(html.Div(id="dvtq-noi-dung"), type="dot"),
    ])


def _tg(ten: str):
    return None if ten is None else ten


def _chenh(hien, truoc, fmt, tot_khi):
    if hien is None or truoc is None:
        return html.Span("–", className="dv-chua-co")
    d = hien - truoc
    if abs(d) < 1e-9:
        return html.Span("0", className="dv-chua-co")
    tot = (d > 0) == (tot_khi == "tang") if tot_khi else None
    chu = ("+" if d > 0 else "−") + (ch.so(abs(d), 2) + " điểm %" if fmt in (_p1, _p2) else fmt(abs(d)))
    return html.Span(chu, className="" if tot is None else ("dv-tot" if tot else "dv-xau"))


def _p1(v):
    return ch.pct(v, 1)


def _p2(v):
    return ch.pct(v, 2)


def _n(v):
    return ch.so(v, 0)


def _dong(ten, hien, truoc, lay, fmt, tot_khi=None, ghi=None):
    """Một dòng KPI: lay(du_lieu_phong) lấy số; hien / truoc là {phòng: dữ liệu}."""
    def v(nguon, p):
        x = (nguon or {}).get(p)
        try:
            return None if x is None else lay(x)
        except (KeyError, TypeError):
            return None
    cac = [fmt(v(hien, p)) if v(hien, p) is not None else None for p in ("DNG1", "DNG2", "DNG")]
    cung_ky = v(truoc, "DNG")
    return (ten, cac + [html.Span("chưa có nguồn", className="dv-chua-co"), fmt(cung_ky) if cung_ky is not None else None,
                        _chenh(v(hien, "DNG"), cung_ky, fmt, tot_khi)], ghi)


def _nhom_roi_mang(d):
    h, t = d["roi_mang"], d["roi_mang_truoc"]
    if not h:
        return ch.bang_kpi("Rời mạng", "Chưa có số liệu rời mạng.", COT, [])
    return ch.bang_kpi("Rời mạng", "Số chốt của file, theo phòng", COT, [
        _dong("KH rời mạng", h, t, lambda x: x["kh_roi_mang"], _n, "giam", "Hủy SSD + CTBDV + chờ thanh lý + CTBDV dự kiến, trừ số khôi phục."),
        _dong("Tỷ lệ rời mạng / KH Active", h, t, lambda x: x["ty_le_roi_active"], _p2, "giam"),
        _dong("Rời mạng / Gross PTTB", h, t, lambda x: x["ty_le_roi_gross"], _p1, "giam", "Cứ 100 khách mới thì mất bao nhiêu khách cũ."),
        _dong("Net PTTB", h, t, lambda x: x["net_pttb"], _n, "tang", "Khách mới trừ khách rời mạng."),
        _dong("Tỷ lệ giữ lại", h, t, lambda x: x["ty_le_giu"], _p2, "tang")])


def _nhom_cong_no(d):
    h, t = d["cong_no"], d["cong_no_truoc"]
    if not h:
        return ch.bang_kpi("Công nợ", "Chưa có số liệu công nợ.", COT, [])
    ky = f"hoá đơn tháng {d['ky_no'][-2:]}" if d["ky_no"] else ""
    return ch.bang_kpi("Công nợ", f"Tỷ lệ đã thu {ky}, tại ngày thu thứ {d['so_ngay_thu']}; kỳ trước tính cùng ngày thu", COT, [
        _dong("Tỷ lệ thu theo hoá đơn (bill)", h, t, lambda x: x["bill"], _p1, "tang"),
        _dong("Tỷ lệ thu theo doanh thu", h, t, lambda x: x["dt"], _p1, "tang")])


def _nhom_sr_bd(d, che_do):
    h = {p: v["bd"] for p, v in d["sr"].items()}
    t = {p: v["bd"] for p, v in d["sr_truoc"].items()}
    kho = "trong ngày" if che_do == "ngay" else "luỹ kế tháng"
    return ch.bang_kpi("SR bị động", f"Yêu cầu của khách, {kho}", COT, [
        _dong("SR phát sinh", h, t, lambda x: x["so_sr"], _n, None),
        _dong("Đã phân công", h, t, lambda x: x["phan_cong"], _n, None),
        _dong("Tồn (chưa + đang xử lý)", h, t, lambda x: x["ton"], _n, "giam"),
        _dong("Tỷ lệ xử lý xong", h, t, lambda x: x["ty_le_xu_ly"], _p1, "tang"),
        _dong("Tỷ lệ quá hạn", h, t, lambda x: x["ty_le_qua_han"], _p1, "giam", "Quá hạn trên số SR đã có hạn xử lý."),
        _dong("Phản hồi trong 60 phút", h, t, lambda x: x["trong_60p"], _p1, "tang"),
        _dong("Hợp đồng gọi lặp (SR)", h, t, lambda x: x["ty_le_lap"], _p1, "giam", "SR thuộc hợp đồng có từ 2 SR trở lên trong kỳ.")])


def _nhom_sr_cd(d, che_do):
    h = {p: v["cd"] for p, v in d["sr"].items()}
    t = {p: v["cd"] for p, v in d["sr_truoc"].items()}
    kho = "trong ngày" if che_do == "ngay" else "luỹ kế tháng"
    return ch.bang_kpi("SR chủ động", f"DVKH chủ động chăm sóc, {kho}", COT, [
        _dong("SR đổ về", h, t, lambda x: x["so_sr"], _n, None),
        _dong("Đã phân công", h, t, lambda x: x["phan_cong"], _n, None),
        _dong("Tồn", h, t, lambda x: x["ton"], _n, "giam", "Chưa xử lý + chưa phân công + đang xử lý."),
        _dong("Tỷ lệ tồn", h, t, lambda x: x["ty_le_ton"], _p1, "giam"),
        _dong("Tỷ lệ quá hạn", h, t, lambda x: x["ty_le_qua_han"], _p1, "giam"),
        _dong("Không liên lạc được", h, t, lambda x: x["ty_le_khong_lien_lac"], _p1, "giam", "Trên SR đã thử liên hệ."),
        _dong("Khách muốn thanh lý", h, t, lambda x: x["muon_thanh_ly"], _n, "giam")])


def _bieu_do_ngay(ngay: date):
    bd, cd = sl.sr_bi_dong(), sl.sr_chu_dong()
    tu = date(ngay.year, ngay.month, 1)
    a = sl.theo_ngay_bd(sl.loc(bd, None, tu, ngay, "ngay_yc"))
    b = sl.theo_ngay_cd(sl.loc(cd, None, tu, ngay, "ngay_do"))
    f = go.Figure()
    if not a.empty:
        f.add_bar(x=a["ngay_yc"], y=a["so_sr"], name="SR bị động phát sinh", marker_color=ch.XANH)
    if not b.empty:
        f.add_bar(x=b["ngay_do"], y=b["so_sr"], name="SR chủ động đổ về", marker_color=ch.CAM)
    f.update_layout(barmode="group")
    f.update_xaxes(tickformat="%d/%m")
    return card([ch.khung(f, 300)], title="SR theo ngày", desc="Khối lượng việc mỗi ngày trong tháng")


def _bieu_do_cong_no():
    cn = sl.cong_no_ngay()
    cn = cn[(cn["cap"] == "phong") & (cn["ten"] == "To tal DNG CN 30")] if not cn.empty else cn
    if cn.empty:
        return card([html.Div("Chưa có số liệu công nợ.", className="desc")], title="Tiến độ thu công nợ")
    f = go.Figure()
    ky = sorted(cn["ky_no"].unique())[-2:]
    for i, k in enumerate(ky):
        x = cn[cn["ky_no"] == k]
        f.add_scatter(x=x["so_ngay"], y=x["ty_le_bill"] * 100, mode="lines+markers", name=f"Hoá đơn tháng {k[-2:]}",
                      line={"color": ch.XANH if i == len(ky) - 1 else ch.XAM, "dash": "solid" if i == len(ky) - 1 else "dot", "width": 2.5})
    f.update_xaxes(title="Ngày thu thứ")
    f.update_yaxes(ticksuffix="%", range=[0, 102])
    return card([ch.khung(f, 300)], title="Tiến độ thu công nợ", desc="Tỷ lệ thu theo hoá đơn, cả Đà Nẵng, so với tháng trước")


def register(app):
    @app.callback(Output("dvtq-noi-dung", "children"), Input("dvtq-ngay", "date"), Input("dvtq-che-do", "value"))
    def _ve(ngay, che_do):
        from flask_login import current_user
        if not sl.co_du_lieu():
            return ch.chua_co_du_lieu(current_user.duoc_nap_dvkh)
        ngay_d = date.fromisoformat(str(ngay)[:10])
        d = tq.tinh(ngay_d, che_do or "luy_ke")
        nd = sl.ngay_du_lieu()
        sr_moi = max([x for x in (nd["sr_bd"], nd["sr_cd"]) if x] or [None], default=None)
        trong_ngay_rong = (che_do == "ngay" and sr_moi is not None and ngay_d > sr_moi)
        chu_y = [x for x in insight.tao_nhan_dinh() if x["muc"] in ("Nghiêm trọng", "Cần chú ý")][:4]
        return html.Div([
            ch.thanh_cap_nhat(),
            html.Div([html.B("Quy tắc dữ liệu: "), GHI_CHU_DU_LIEU], className="dv-ghi-chu-du-lieu"),
            html.Div([html.B("Chưa có SR trong ngày này: "), f"SR mới nhất trong file là ngày {sr_moi:%d/%m/%Y}. Chọn “Luỹ kế tháng” hoặc đổi ngày xem."],
                     className="dv-ghi-chu-du-lieu") if trong_ngay_rong else None,
            html.Div([_nhom_roi_mang(d), _nhom_cong_no(d), _nhom_sr_bd(d, che_do), _nhom_sr_cd(d, che_do)], className="dv-luoi-kpi"),
            html.Div(style={"height": "16px"}),
            card([ch.danh_sach_nhan_dinh(chu_y), html.Div(html.A("Xem tất cả nhận định và phân tích sâu →", href="/dvkh/insight", className="btn"),
                                                          style={"marginTop": "12px"})],
                 title="Điểm cần chú ý", desc="Do luật cố định đọc từ số liệu, mỗi nhận định kèm gợi ý hành động"),
            html.Div([_bieu_do_ngay(ngay_d), _bieu_do_cong_no()], className="dv-hai-cot"),
        ])
