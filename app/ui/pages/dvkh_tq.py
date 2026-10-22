"""Trang Tổng quan KPI của khối DVKH: bốn nhóm KPI theo phòng (DNG1, DNG2, tổng Đà Nẵng), so cùng kỳ tháng trước, điểm cần chú ý."""
from __future__ import annotations

from datetime import date

import plotly.graph_objects as go
from dash import Input, Output, dcc, html

from app.dvkh import insight, so_lieu as sl, tong_quan as tq, xu_huong as xh
from app.ui.components import card, seg_control
from app.ui.pages import dvkh_chung as ch, dvkh_ve as ve

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
    return ch.bang_kpi("Công nợ", f"Tỷ lệ đã thu {ky}, tại ngày {d['so_ngay_thu']}; kỳ trước tính cùng ngày trong tháng", COT, [
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


def _chu_du_bao(db: dict | None, ten: str) -> str:
    if not db:
        return f"Chưa đủ ngày để ước tính cả tháng cho {ten}."
    tin = "Độ tin cậy còn thấp vì mới có " + ch.so(db["so_ngay_co"]) + " ngày dữ liệu." if db["tin_cay"] == "thấp" else ""
    return (f"Nếu giữ nhịp {ch.so(db['trung_binh_ngay'])} SR mỗi ngày như {ch.so(db['so_ngay_co'])} ngày qua, cả tháng khoảng {ch.so(round(db['du_bao'], -1))} SR "
            f"(trong khoảng {ch.so(round(db['thap'], -1))} đến {ch.so(round(db['cao'], -1))}). {tin}")


def _the_cong_no(sk: dict, d: dict) -> html.Div:
    """Thẻ công nợ: so với tháng trước cùng ngày lịch (xanh nếu bằng hoặc hơn) và dự báo cuối kỳ."""
    db = sk["du_bao_no"]
    cn = (d.get("cong_no") or {}).get("DNG")
    so = ch.pct(cn["bill"]) if cn and cn.get("bill") is not None else "–"
    if not db:
        return ve.the_xu_huong("Thu công nợ (theo hoá đơn)", so, ghi="Cần số kỳ trước đã thu hết để so sánh và dự báo")
    chenh = (db["hien_tai"] - db["cung_ngay_ky_cu"]) * 100
    muc = "ok" if chenh >= -0.5 else ("warn" if chenh >= -2 else "bad")
    xu_huong = html.Div([html.Span(f"{'▲ cao hơn' if chenh >= 0 else '▼ thấp hơn'} tháng trước {ch.so(abs(chenh), 1)} điểm",
                                   className="dv-xh " + ("dv-tot" if chenh >= 0 else "dv-xau")),
                         html.Span(f"cùng ngày {db['so_ngay']} hằng tháng", className="dv-xh-ghi")], className="dv-xh-dong")
    return ve.the_xu_huong("Thu công nợ (theo hoá đơn)", so, muc=muc, xu_huong_html=xu_huong,
                           ghi=f"Dự báo cuối kỳ {ch.pct(db['du_bao_cuoi_ky'] * 100)} (kỳ trước đạt {ch.pct(db['cuoi_ky_cu'] * 100)})",
                           giai_thich="Tỷ lệ hoá đơn đã thu của kỳ nợ đang thu. So với tháng trước cùng ngày lịch, không so theo số dòng có dữ liệu.")


def _the_roi_mang(sk: dict) -> html.Div:
    ls = sk["roi_mang_lich_su"]
    if ls is None or ls.empty:
        return ve.the_xu_huong("Rời mạng / KH Active", "–", ghi="Chưa có số rời mạng")
    r = ls.iloc[-1]
    muc = ch.muc_theo_nguong(r["ty_le_roi_active"], 0.3, 0.6)
    ghi = f"{ch.so(r['kh_roi_mang'])} khách · chốt {r['ngay_chot']:%d/%m}"
    if len(ls) >= 2:
        return ve.the_xu_huong("Rời mạng / KH Active", ch.pct(r["ty_le_roi_active"], 2), muc=muc, ghi=ghi, h=xh.huong(ls["ty_le_roi_active"], k=1),
                               chuoi=ls["ty_le_roi_active"], cua_so="so với các lần chốt trước")
    return ve.the_xu_huong("Rời mạng / KH Active", ch.pct(r["ty_le_roi_active"], 2), muc=muc, ghi=ghi,
                           xu_huong_html=html.Div("Mới có một lần chốt nên chưa thấy hướng tăng giảm", className="dv-xh dv-chua-co"),
                           giai_thich="Số chốt trong file. Nạp thêm file ở các ngày sau thì mũi tên xu hướng sẽ hiện.")


def _dai_suc_khoe(sk: dict, d: dict) -> html.Div:
    kb, kc = sk["kpi_bd"], sk["kpi_cd"]
    lb, lc = sk["luong_bd"], sk["luong_cd"]
    cac = []
    if kb:
        cac.append(ve.the_xu_huong("SR bị động phát sinh", ch.so(kb["so_sr"]), h=sk["huong_vao_bd"], tang_la_tot=False, chuoi=lb["vao"],
                                   ghi=f"{ch.so(kb['so_hd'])} hợp đồng · trung bình {ch.so(kb['so_sr'] / max(len(lb), 1))} SR/ngày",
                                   giai_thich="Số yêu cầu khách gọi vào từ đầu tháng. Tăng nghĩa là việc nhiều hơn."))
        cac.append(ve.the_xu_huong("SR bị động còn tồn", ch.so(kb["ton"]), muc=ch.muc_theo_nguong(kb["ty_le_qua_han"], 10, 30), h=sk["huong_ton_bd"], tang_la_tot=False,
                                   chuoi=lb["ton_cuoi_ngay"], ghi=f"{ch.pct(kb['ty_le_qua_han'])} quá hạn · {ch.pct(kb['ty_le_xu_ly'], 0)} đã xử lý xong",
                                   giai_thich="Chưa xử lý + đang xử lý. Mũi tên so tồn cuối ngày của 3 ngày gần nhất với các ngày trước."))
    if kc:
        cac.append(ve.the_xu_huong("SR chủ động còn tồn", ch.so(kc["ton"]), muc=ch.muc_theo_nguong(kc["ty_le_ton"], 25, 40), h=sk["huong_ton_cd"], tang_la_tot=False,
                                   chuoi=lc["ton_cuoi_ngay"], ghi=f"{ch.pct(kc['ty_le_ton'], 0)} tổng SR đổ về · {ch.pct(kc['ty_le_khong_lien_lac'], 0)} không liên lạc được",
                                   giai_thich="SR DVKH chủ động chăm sóc mà chưa xong, gồm cả SR chưa có người nhận."))
    cac += [_the_cong_no(sk, d), _the_roi_mang(sk)]
    tl, cu = sk["so_thanh_ly_cho"], sk["thanh_ly_cu_nhat"]
    cac.append(ve.the_xu_huong("Khách đòi thanh lý chưa xử lý", ch.so(tl), muc="bad" if tl >= 100 else ("warn" if tl else "ok"),
                               ghi=f"Cũ nhất từ {cu:%d/%m %H:%M}" if cu is not None else "Không còn SR nào", xu_huong_html=html.Div(className="dv-xh-dong"),
                               giai_thich="SR thanh lý (bị động) và SR chủ động có khách đòi thanh lý mà chưa xong. Gọi ngay còn giữ được khách."))
    return ve.hang_the(cac)


def _hai_bieu_do_luong(sk: dict) -> html.Div:
    lb, lc = sk["luong_bd"], sk["luong_cd"]
    cot = []
    if len(lb):
        cot.append(card([html.Div(_chu_du_bao(sk["du_bao_bd"], "SR bị động"), className="dv-ket-luan"), ve.vao_ra_ton(lb, "SR bị động phát sinh")],
                        title="SR bị động: vào, ra và tồn",
                        desc="Cột xanh là khách gọi vào, cột lá là SR đã rời hàng chờ. Đường cam là tồn cuối ngày: đi xuống là đang dọn nhanh hơn việc đổ về."))
    if len(lc):
        cot.append(card([html.Div(_chu_du_bao(sk["du_bao_cd"], "SR chủ động"), className="dv-ket-luan"), ve.vao_ra_ton(lc, "SR chủ động đổ về")],
                        title="SR chủ động: vào, ra và tồn", desc="Ngày đổ nhiều thì tồn nhảy lên; xem sau đó mấy ngày mới dọn xong."))
    return html.Div(cot, className="dv-hai-cot")


def _so_sanh_phong(d: dict) -> html.Div | None:
    """Hai phòng cạnh nhau trên các tỷ lệ chính; thanh ngắn hơn là tốt hơn."""
    sr = d["sr"]
    cn = d.get("cong_no") or {}

    def lay(p, nhom, khoa):
        x = (sr.get(p) or {}).get(nhom)
        return None if not x else x.get(khoa)

    dong = [("SR bị động quá hạn", lambda p: lay(p, "bd", "ty_le_qua_han")),
            ("SR bị động chưa xử lý xong", lambda p: None if lay(p, "bd", "ty_le_xu_ly") is None else 100 - lay(p, "bd", "ty_le_xu_ly")),
            ("SR chủ động tồn", lambda p: lay(p, "cd", "ty_le_ton")),
            ("SR chủ động không liên lạc được", lambda p: lay(p, "cd", "ty_le_khong_lien_lac")),
            ("Hoá đơn chưa thu", lambda p: (100 - cn[p]["bill"]) if p in cn and cn[p].get("bill") is not None else None)]
    f = go.Figure()
    for p, mau in (("DNG1", ch.XANH), ("DNG2", ch.CAM)):
        v = [x(p) for _, x in dong]
        f.add_bar(y=[t for t, _ in dong], x=v, name=p, orientation="h", marker_color=mau, text=[ch.pct(y, 1) if y is not None else "" for y in v],
                  textposition="outside", cliponaxis=False)
    f.update_layout(barmode="group")
    f.update_yaxes(autorange="reversed", automargin=True)
    cao_nhat = max([y for p in ("DNG1", "DNG2") for _, x in dong if (y := x(p)) is not None] or [10])
    f.update_xaxes(ticksuffix="%", showgrid=True, gridcolor="#EDF1F6", range=[0, cao_nhat * 1.2])
    return card([ch.khung(f, 330)], title="DNG1 so với DNG2", desc="Cùng một tỷ lệ cho hai phòng; thanh ngắn hơn là tốt hơn. Hoá đơn chưa thu = 100% trừ tỷ lệ đã thu.")


def _cong_no_du_bao(sk: dict, d: dict) -> html.Div:
    db, dt = sk["du_bao_no"], sk["du_bao_no_dt"]
    ket = ""
    if db and dt:
        ket = (f"Đến ngày {db['so_ngay']}, đã thu {ch.pct(db['hien_tai'] * 100)} số hoá đơn (tháng trước cùng ngày: {ch.pct(db['cung_ngay_ky_cu'] * 100)}). "
               f"Theo hình dạng đường thu tháng trước, cuối kỳ dự kiến {ch.pct(db['du_bao_cuoi_ky'] * 100)} số hoá đơn và {ch.pct(dt['du_bao_cuoi_ky'] * 100)} doanh thu.")
    thanh = [card([html.Div(ket, className="dv-ket-luan") if ket else None, ve.duong_cong_no(sl.cong_no_ngay(), "To tal DNG CN 30", db)],
                  title="Tiến độ thu công nợ và dự báo cuối kỳ",
                  desc="Đường liền là kỳ đang thu, đường chấm là kỳ trước, đường đứt là phần còn lại dự báo theo nhịp thu của kỳ trước.")]
    so_sanh = _so_sanh_phong(d)
    if so_sanh is not None:
        thanh.append(so_sanh)
    return html.Div(thanh, className="dv-hai-cot")


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
        sk = tq.suc_khoe(ngay_d)
        return html.Div([
            ch.thanh_cap_nhat(),
            html.Div([html.B("Quy tắc dữ liệu: "), GHI_CHU_DU_LIEU], className="dv-ghi-chu-du-lieu"),
            html.Div([html.B("Chưa có SR trong ngày này: "), f"SR mới nhất trong file là ngày {sr_moi:%d/%m/%Y}. Chọn “Luỹ kế tháng” hoặc đổi ngày xem."],
                     className="dv-ghi-chu-du-lieu") if trong_ngay_rong else None,
            html.Div("Sức khoẻ khối DVKH", className="dv-tieu-nhom"),
            _dai_suc_khoe(sk, d),
            html.Div("Xu hướng và dự báo", className="dv-tieu-nhom"),
            _hai_bieu_do_luong(sk),
            html.Div(style={"height": "16px"}),
            _cong_no_du_bao(sk, d),
            html.Div("Điểm cần chú ý", className="dv-tieu-nhom"),
            card([ch.danh_sach_nhan_dinh(chu_y), html.Div(html.A("Xem tất cả nhận định và phân tích sâu →", href="/dvkh/insight", className="btn"),
                                                          style={"marginTop": "12px"})],
                 title="Điểm cần chú ý", desc="Do luật cố định đọc từ số liệu, mỗi nhận định kèm gợi ý hành động"),
            html.Div("Bảng chỉ số theo phòng", className="dv-tieu-nhom"),
            html.Div([_nhom_roi_mang(d), _nhom_cong_no(d), _nhom_sr_bd(d, che_do), _nhom_sr_cd(d, che_do)], className="dv-luoi-kpi"),
        ])
