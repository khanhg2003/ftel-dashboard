"""Chi tiết MỘT nhân viên trong cửa sổ "Hiệu quả & xu hướng" (mở bằng cách bấm vào dòng của người đó ở bảng tổng quan, `baocaongay_hq.py`):
năm ô chỉ số đặt cạnh số cả phòng, thanh kết quả, nhận định riêng, biểu đồ riêng và danh sách ca cần chú ý."""
from __future__ import annotations

from dash import html

from app import online_ca_phan_tich as pa
from app.thoi_gian import sang_gio_vn
from app.ui.pages import baocaongay_hq_ve as ve
from app.ui.pages.baocaongay_hq import cac_the_chung

THU_TU_XAU = {"chua_len": 0, "doi": 1, "tre": 2}


def _ca_chu_y(ca: list[dict]) -> html.Div:
    """Ca trễ / chưa lên / đã dời của người này (nặng nhất lên trước), tối đa 12 dòng."""
    xau = sorted([c for c in ca if c["kq"] in THU_TU_XAU], key=lambda c: (THU_TU_XAU[c["kq"]], -c["so_doi"], c["ngay"]))
    if not xau:
        return html.Div([html.Div("Ca cần chú ý", className="hq-tde"), html.Div("Không có ca nào trễ, chưa lên hay phải dời trong khoảng này.", className="hq-ghi")], className="hq-khoi")
    khung = {k["ma"]: k["nhan"] for k in pa.oc.khung()}
    dong = []
    for c in xau[:12]:
        luc = sang_gio_vn(c.get("online_luc"))
        chi_tiet = f"muộn {c['tre_phut']} phút" if c["kq"] == "tre" and c.get("tre_phut") else f"online {luc:%H:%M %d/%m}" if c["kq"] == "tre" and luc else ""
        dong.append(html.Tr([html.Td(c["ma"], className="ten"), html.Td(f"{c['ngay']:%d/%m}"), html.Td(khung.get(c["khung_dau"] or c["khung"], "")),
                             html.Td(html.Span(ve.NHAN[c["kq"]], className=f"hq-hh kq-{c['kq']}")), html.Td(f"{c['so_doi']} lần" if c["so_doi"] else "–"), html.Td(chi_tiet)]))
    them = [html.Div(f"và {len(xau) - 12} ca nữa.", className="hq-ghi")] if len(xau) > 12 else []
    return html.Div([html.Div(f"Ca cần chú ý · {len(xau)} ca", className="hq-tde"),
                     html.Table([html.Thead(html.Tr([html.Th(c) for c in ("Mã HĐ", "Ngày", "Khung hẹn", "Kết quả", "Đã dời", "Ghi chú")])), html.Tbody(dong)], className="hq-bang"),
                     *them], className="hq-khoi")


def chi_tiet(phong: list[str], ky: str, acc: str) -> list:
    tu, den = pa.khoang(ky)
    tu0, den0 = pa.ky_truoc(tu, den)
    hq, hq0 = pa.hieu_qua(phong, tu, den, acc=acc), pa.hieu_qua(phong, tu0, den0, acc=acc)
    hq_phong = pa.hieu_qua(phong, tu, den)
    xh, xh0 = pa.xu_huong(phong, tu, den, acc), pa.xu_huong(phong, tu0, den0, acc)
    ten = next((n["ten"] for n in hq_phong["nv"] if n["acc"] == acc), None) or next((n["ten"] for n in xh["nv"] if n["acc"] == acc), acc)
    t = hq["tong"]
    muc, nhan = pa.danh_gia(t["ty_le"], t["xet"])
    dau = html.Div([html.Button("← Cả phòng", id={"type": "hq-ve", "i": 0}, n_clicks=0, className="btn hq-ve"), html.Span(ten, className="hq-nv-ten"), ve.huy_hieu(muc, nhan),
                    html.Span(ve.khoang_chu(tu, den) + f" · so với {ve.khoang_chu(tu0, den0)}", className="hq-ghi-nho")], className="hq-nv-dau")
    if not t["ca"] and not xh["ngay"]:
        return [dau, html.Div("Người này chưa có ca hay báo cáo nào trong khoảng này.", className="hq-ghi")]
    hinh = ve.cac_hinh(ve.hinh_dung_hen(hq["ngay"]) if len(hq["ngay"]) >= 2 else None, ve.hinh_khung(hq["khung"]) if hq["khung"] else None,
                       ve.hinh_online(xh["ngay"]) if len(xh["ngay"]) >= 2 else None, ve.hinh_ban(xh["ngay"]) if len(xh["ngay"]) >= 2 else None)
    nv_dong = {**t, "ten": ten}
    return [dau, cac_the_chung(t, hq0["tong"], xh, xh0, hq_phong["tong"]), ve.thanh_ket_qua(t, f"Kết quả ca của {ten}"),
            ve.nhan_dinh(pa.nhan_dinh_nv(nv_dong, hq, hq_phong["tong"], xh)), hinh, _ca_chu_y(hq["ca"]), ve.ghi_cuoi()]
