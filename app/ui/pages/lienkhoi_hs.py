"""Giao diện hồ sơ MỘT hợp đồng của trang Điều hành liên khối (nhánh thi-lien-khoi): thẻ đầu trang, ô chỉ số, ba thẻ theo khối,
việc đang giao và dòng thời gian. Số liệu từ `app/lien_khoi/ho_so.py`; không có tên khách hàng."""
from __future__ import annotations

import pandas as pd

from dash import html

from app.lien_khoi import luat, su_kien as sk
from app.lien_khoi.doc_kt import TEN_LOAI_KT
from app.lien_khoi.ho_so import _chu, _dong, _so

NHAN_KT = {"so_lan_lap": "Số lần lặp (30 ngày)", "so_lan_hen": "Số lần hẹn", "trieu_chung": "Triệu chứng khách báo", "phan_tu_loi": "Phần tử lỗi",
           "nguyen_nhan_loi": "Nguyên nhân", "huong_xu_ly": "Hướng xử lý", "tinh_trang": "Tình trạng", "loai_trien_khai": "Loại triển khai",
           "hen_xanh": "Mốc hẹn xanh", "hen_do": "Mốc hẹn đỏ", "loai_dich_vu": "Dịch vụ triển khai", "loai_giao_dich": "Loại giao dịch",
           "tgxl_72h": "Thời gian xử lý 72h (giờ)", "cap_indoor": "Cáp indoor (m)", "cap_outdoor": "Cáp outdoor (m)", "loai_ket_noi": "Loại kết nối",
           "active_by": "Kích hoạt bằng", "tong_cap": "Tổng số cấp", "nguyen_nhan": "Ghi nhận"}
LOP_KHOI = {sk.KD: "kd", sk.KT: "kt", sk.DVKH: "dvkh"}
LOP_MUC = {luat.CAO: "cao", luat.TB: "tb", "Ổn": "on"}


def _ngay(t, gio: bool = False) -> str:
    return "" if t is None or pd.isna(t) else pd.Timestamp(t).strftime("%d/%m/%Y %H:%M" if gio else "%d/%m/%Y")


def _tien(x) -> str:
    return "" if not x else f"{x:,.0f}".replace(",", ".") + " đ"


def _badge(chu: str, muc: str = "muted"):
    return html.Span(chu, className=f"badge {muc}")


def _kv(cap: list[tuple]) -> html.Div:
    """Các dòng "nhãn - giá trị", bỏ dòng không có giá trị."""
    return html.Div([html.Div([html.Div(k, className="lk-k"), html.Div(v, className="lk-v")], className="lk-kv") for k, v in cap if v not in (None, "", [])])


def _the(tieu_de: str, than, so=None):
    dau = [html.Span(tieu_de, className="lk-the-td")] + ([html.Span(str(so), className="badge muted")] if so is not None else [])
    return html.Div([html.Div(dau, className="lk-the-dau"), html.Div(than, className="lk-the-than")], className="lk-the")


def _trong(chu: str):
    return html.Div(chu, className="lk-trong")


def _dau(h: dict):
    kd, co, n = h["kd"], h["co"], h["nguoi"]
    b = []
    if co["da_online"] is True:
        b.append(_badge(f"Đã online · {co['tham_nien_thang']} tháng" if co["tham_nien_thang"] is not None else "Đã online", "ok"))
    elif co["da_online"] is False:
        b.append(_badge(f"Chưa online · chờ {co['cho_ngay']} ngày" if co["cho_ngay"] is not None else "Chưa online", "bad" if (co["cho_ngay"] or 0) >= 7 else "warn"))
    if kd.get("goi"):
        b.append(_badge(f"Gói {kd['goi']}"))
    if any(x["vvip"] for x in kd.get("dich_vu", [])):
        b.append(_badge("V.VIP", "ok"))
    if co["no_cuoc"]:
        b.append(_badge("Nằm trong danh sách nợ cước", "warn"))
    if co["co_y_roi"]:
        b.append(_badge("Có ý rời", "bad"))
    chip = lambda nhan, ten, thieu: html.Div([html.Div(nhan, className="lk-nhan"), html.B(ten or thieu)], className="lk-chip")
    return html.Div([html.Div([html.Div("Hợp đồng", className="lk-nhan"), html.Div(h["ma"], className="lk-ma"), html.Div(b, className="lk-badges")]),
                     html.Div([chip("Sale bán", n["sale"], "Không có trong file bán hàng"), chip("CSKH phụ trách", n["dvkh"], "Chưa có (vào hàng chờ)"),
                               chip("KTV", n["ktv"], "Chưa có (vào hàng chờ)")], className="lk-nguoi")], className="lk-dau")


def _so_o(nhan: str, gia_tri, ghi_chu: str, lop: str = ""):
    return html.Div([html.Div(nhan, className="lk-nhan"), html.Div(gia_tri, className="gt"), html.Div(ghi_chu, className="lk-ghi-chu")], className=f"lk-o {lop}".strip())


def _o_chi_so(h: dict):
    v, kt = h["viec"], h["kt"]
    su_co = int((kt["loai"] == "checklist").sum()) if len(kt) else 0
    return html.Div([
        _so_o("Mức ưu tiên xử lý", h["muc"], f"{len(v)} việc đang giao cho hợp đồng này" if len(v) else "Không có luật nào đang giao việc", LOP_MUC[h["muc"]]),
        _so_o("Kỹ thuật", len(kt), f"{su_co} lần checklist sự cố" if su_co else "Sự kiện Kỹ thuật ghi nhận"),
        _so_o("DVKH", len(h["sr_bd"]) + len(h["sr_cd"]), f"{len(h['sr_bd'])} SR khách gọi · {len(h['sr_cd'])} SR chủ động"),
        _so_o("Cước / tháng", _tien(h["kd"].get("cuoc_thang")) or "–", h["kd"].get("hinh_thuc_tt") or "Theo file bán hàng")], className="lk-so")


def _the_kd(h: dict):
    k = h["kd"]
    if not k:
        return _the("Kinh doanh", _trong("Hợp đồng này không có trong file bán hàng."))
    tra = f"{_so(k.get('so_thang_tra_truoc')):.0f}" if _so(k.get("so_thang_tra_truoc")) else ""
    dv = [html.Div([html.Div([html.B(x["ten"] or x["nhom"]), html.Span(f" · {x['nhom']}", className="lk-ghi-chu")]),
                    html.Div([_badge("V.VIP", "ok") if x["vvip"] else None, html.Span(_tien(x["don_gia"]), className="lk-ghi-chu")], className="lk-badges")], className="lk-dv")
          for x in k.get("dich_vu", [])]
    than = [_kv([("Gói cước", k.get("goi")), ("Cước / tháng", _tien(k.get("cuoc_thang"))),
                 ("Hình thức thanh toán", (k.get("hinh_thuc_tt") or "") + (f" · {tra} tháng" if tra and tra not in ("0", "0.0") else "")),
                 ("Số tiền trả trước", _tien(k.get("so_tien_tra_truoc"))), ("Phí hoà mạng", _tien(k.get("tien_hoa_mang"))),
                 ("Chính sách bán", k.get("chinh_sach")), ("Đối tượng", k.get("doi_tuong")), ("Nguồn bán", k.get("nguon_ban")),
                 ("Chi nhánh quản lý", k.get("cn_quan_ly")), ("Ngày tạo hợp đồng", _ngay(k.get("ngay_tao"))), ("Ngày online", _ngay(k.get("ngay_online"))),
                 ("Sale", k.get("sale"))]),
            html.Div("Dịch vụ kèm", className="lk-nhan", style={"marginTop": "12px"}), *(dv or [_trong("Không có FPT Play hay Camera.")])]
    return _the("Kinh doanh", than)


def _su_kien_kt(r) -> html.Div:
    tt = r["tt"] if isinstance(r["tt"], dict) else {}
    return html.Div([html.Div([html.B(TEN_LOAI_KT.get(r["loai"], r["loai"])), html.Span(f" · {_ngay(r['thoi_diem'], True)}", className="lk-ghi-chu"),
                               html.Span(f" · {r['nguoi']}" if _chu(r["nguoi"]) else "", className="lk-ghi-chu")]),
                     html.Div(_chu(r["chi_tiet"]), className="lk-ghi-chu"), _kv([(NHAN_KT.get(k, k), v) for k, v in tt.items()])], className="lk-sk")


def _the_kt(h: dict):
    kt = h["kt"]
    return _the("Kỹ thuật", [_su_kien_kt(r) for _, r in kt.iterrows()] if len(kt) else _trong("Khối Kỹ thuật chưa có sự kiện nào cho hợp đồng này."), len(kt) or None)


def _sr_bd(r) -> html.Div:
    phi, mg = _so(r.get("phi")), _so(r.get("mien_giam_phi"))
    dong = [("Kênh tiếp nhận", r.get("kenh")), ("Phân loại", r.get("phan_loai")), ("Hình thức", r.get("hinh_thuc_kn")), ("Nguyên nhân", r.get("nguyen_nhan_1")),
            ("Kết quả tư vấn", r.get("ket_qua_tu_van")), ("Đúng hạn", r.get("qua_han")), ("Phí / miễn giảm", f"{_tien(phi)} / {_tien(mg)}" if (phi or mg) else "")]
    return html.Div([html.Div([html.B(_chu(r.get("loai_yc")) or "SR"), html.Span(f" · {_ngay(r['tg_yc'], True)}", className="lk-ghi-chu"), _badge(_chu(r.get("tinh_trang")))],
                              className="lk-badges"), _kv([(k, _chu(v)) for k, v in dong])], className="lk-sk")


def _sr_cd(r) -> html.Div:
    diem = _so(r.get("diem_rm"))
    dong = [("Nhóm chương trình", r.get("nhom_ct")), ("Điểm nguy cơ rời mạng", f"{diem:.0f}" if diem is not None and diem >= 0 else ""), ("Độ ưu tiên", r.get("do_uu_tien")),
            ("Số lần chăm sóc", r.get("so_lan_cs")), ("Lý do mất kết nối", r.get("ly_do_mat_kn")), ("Kết quả tư vấn", r.get("ket_qua_tu_van")), ("Đúng hạn", r.get("qua_han"))]
    return html.Div([html.Div([html.B(_chu(r.get("chuong_trinh")) or "SR chủ động"), html.Span(f" · {_ngay(r['tg_do'], True)}", className="lk-ghi-chu"),
                               _badge(_chu(r.get("tinh_trang")))], className="lk-badges"), _kv([(k, _chu(v)) for k, v in dong])], className="lk-sk")


def _the_dvkh(h: dict):
    bd, cd = h["sr_bd"], h["sr_cd"]
    than = [*(_sr_bd(r) for _, r in bd.iterrows()), *(_sr_cd(r) for _, r in cd.iterrows())]
    return _the("Dịch vụ khách hàng", than or _trong("DVKH chưa có SR nào cho hợp đồng này."), (len(bd) + len(cd)) or None)


def _the_viec(h: dict):
    v = h["viec"]
    if v.empty:
        return _the("Việc cần làm của hợp đồng này", _trong("Không có luật nào đang giao việc cho hợp đồng này."))
    dong = [html.Div([html.Div([_badge(r["muc"], "bad" if r["muc"] == luat.CAO else "warn"), html.B(f"  {r['ten_luat']}"), html.Span(f" · {r['han']}", className="lk-ghi-chu")]),
                      html.Div(r["ly_do"]), html.Div(f"Đề xuất: {r['de_xuat']}", className="lk-ghi-chu"),
                      _kv([("Giao sale", r["giao_sale"]), ("Giao DVKH", r["giao_dvkh"]), ("Giao Kỹ thuật", r["giao_kt"])])], className="lk-sk") for _, r in v.iterrows()]
    return _the("Việc cần làm của hợp đồng này", dong, len(v))


def _the_thoi_gian(h: dict):
    ev = h["dong_thoi_gian"]
    muc = [html.Div([html.Div(className=f"lk-cham {LOP_KHOI.get(r['nguon'], '')}"),
                     html.Div([html.Div([html.B(sk.TEN_LOAI.get(r["loai"], r["loai"])), html.Span(f" · {sk.TEN_KHOI.get(r['nguon'], '')} · {_ngay(r['thoi_diem'], True)}", className="lk-ghi-chu")]),
                               html.Div(_chu(r["chi_tiet"]), className="lk-ghi-chu"), html.Div(_chu(r["nguoi"]), className="lk-ghi-chu")])], className="lk-moc")
           for _, r in ev.iloc[::-1].iterrows()]
    return _the("Dòng thời gian (mới nhất ở trên)", muc or _trong("Chưa có sự kiện."), len(ev) or None)


def noi_dung(h: dict):
    """Toàn bộ hồ sơ một hợp đồng."""
    return html.Div([_dau(h), _o_chi_so(h), _the_viec(h), html.Div([_the_kd(h), _the_kt(h), _the_dvkh(h)], className="lk-luoi"), _the_thoi_gian(h)])


__all__ = ["noi_dung", "_dong"]
