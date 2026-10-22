"""Các tab sâu của trang SR bị động: giữ chân khách, khách và dịch vụ, xu hướng, tuổi SR tồn, vòng tròn nguyên nhân.

Tách khỏi `dvkh_sr_bd.py` cho gọn file; trang mẹ import module này trong hàm để tránh vòng lặp import.
"""
from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
from dash import html

from app.dvkh import khai_thac as kt, so_lieu as sl, xu_huong as xh
from app.ui.components import card
from app.ui.pages import dvkh_chung as ch, dvkh_ve as ve

MAU_TU_VAN = {"Đồng ý ở lại": ch.LUC, "Đang suy nghĩ": ve.VANG, "Không đồng ý": ch.DO, "Chưa có kết quả tư vấn": "#B8C4D3"}
CHUA_NAP_LAI = "Chưa có phần này vì file chưa được nạp lại sau khi thêm tính năng. Nạp lại file Excel mới nhất (python scripts/nap_dvkh.py) để hiện."


def _khoang(): return html.Div(style={"height": "16px"})


def _thieu(ten: str):
    return card([html.Div(CHUA_NAP_LAI, className="desc")], title=ten)


# ------------------------------------------------------------------ xu hướng (nằm trong tab Tổng quan)
def xu_huong(df):
    luong = xh.luong_theo_ngay(df, "ngay_yc")
    if len(luong) < 2:
        return html.Div("Cần ít nhất 2 ngày dữ liệu để vẽ xu hướng.", className="desc")
    h = xh.huong(luong["vao"])
    db = xh.du_bao_thang(luong["vao"], int(df["ngay_yc"].max().days_in_month))
    chu = ""
    if db:
        chu = (f"Trung bình {ch.so(db['trung_binh_ngay'])} SR mỗi ngày trong {ch.so(db['so_ngay_co'])} ngày. Nếu giữ nhịp này, cả tháng khoảng {ch.so(round(db['du_bao'], -1))} SR "
               f"(trong khoảng {ch.so(round(db['thap'], -1))} đến {ch.so(round(db['cao'], -1))})." + (" Độ tin cậy còn thấp vì chưa đủ hai tuần dữ liệu." if db["tin_cay"] == "thấp" else ""))
    huong = {"tang": "đang tăng", "giam": "đang giảm", "di_ngang": "đi ngang", None: "chưa rõ"}[h["huong"] if h else None]
    thu = ve.theo_thu(xh.theo_thu(luong))
    return html.Div([card([html.Div([html.B("Xu hướng: "), f"SR vào {huong}. ", chu], className="dv-ket-luan"), ve.vao_ra_ton(luong, "SR bị động phát sinh")],
                          title="SR vào, ra và tồn theo ngày",
                          desc="Cột xanh là khách gọi vào, cột lá là SR đã rời hàng chờ (xử lý xong, tự đóng, chuyển). Đường cam là tồn cuối ngày: đi xuống nghĩa là xử lý nhanh hơn việc đổ về."),
                     card([thu] if thu is not None else [html.Div("Chưa đủ ngày", className="desc")], title="Thứ nào khách gọi nhiều",
                          desc="Trung bình SR vào mỗi ngày theo thứ trong tuần. Thanh đậm là thứ cao hơn mức trung bình chung.")], className="dv-hai-cot")


# ------------------------------------------------------------------ giữ chân khách
def giu_chan(df):
    g = kt.dong_giu_chan(df)
    if g is None:
        return card([html.Div(f"Cần ít nhất {kt.MAU_TOI_THIEU} SR thanh lý trong phạm vi đã chọn.", className="desc")], title="Giữ chân khách")
    t = kt.tom_tat_giu_chan(g)
    ton_tl = int(df[(df["loai_yc"] == "Thanh lý") & df["ton"]].shape[0])
    ty_o_lai = t["o_lai"] * 100 / max(t["co_tu_van"], 1)
    kpi_ = ch.hang_kpi([("SR thanh lý", ch.so(g["tong"]), f"{ch.pct(g['tong'] * 100 / len(df), 0)} tổng SR bị động", ""),
                        ("Khách đồng ý ở lại", ch.pct(ty_o_lai, 0), f"{ch.so(t['o_lai'])} trên {ch.so(t['co_tu_van'])} SR đã tư vấn", ch.muc_theo_nguong(ty_o_lai, 50, 30, cao_xau=False)),
                        ("Hợp đồng đã chấm dứt thật", ch.so(t["chet"]), f"{ch.pct(t['chet'] * 100 / g['tong'], 0)} SR thanh lý", "warn" if t["chet"] else "ok"),
                        ("Còn cứu được", ch.so(t["con_cuu_duoc"]), "Khách đang suy nghĩ mà hợp đồng vẫn còn dùng", "warn" if t["con_cuu_duoc"] else "ok"),
                        ("Thanh lý còn tồn", ch.so(ton_tl), "SR chưa xử lý xong, gọi ngay còn giữ được", "bad" if ton_tl >= 50 else ("warn" if ton_tl else "ok"))])
    ket = [html.B("Đọc biểu đồ: "), f"{ch.so(t['khong_dong_y'])} khách nói không đồng ý ở lại thì {ch.so(t['chet_trong_khong_dong_y'])} "
           f"({ch.pct(t['chet_trong_khong_dong_y'] * 100 / max(t['khong_dong_y'], 1), 0)}) đã chấm dứt hợp đồng thật. Ngược lại {ch.so(t['dang_nghi'])} khách còn đang suy nghĩ "
           f"thì chỉ {ch.so(t['dang_nghi'] - t['con_cuu_duoc'])} đã chấm dứt, {ch.so(t['con_cuu_duoc'])} vẫn dùng: đây là nhóm còn cứu được nếu gọi lại sớm."]
    theo_ngay = (df[df["loai_yc"] == "Thanh lý"].assign(nhom=lambda d: kt.ket_qua_tu_van_nhom(d)).groupby(["ngay_yc", "nhom"]).size().unstack(fill_value=0)
                 .reindex(columns=list(MAU_TU_VAN), fill_value=0))
    ly_do = sl.dem_theo(df[(df["loai_yc"] == "Thanh lý") & df["nguyen_nhan_1"].notna()], "nguyen_nhan_1", 8)
    return html.Div([kpi_, card([html.Div(ket, className="dv-ket-luan"), ve.sankey(g, 360)], title="Dòng chảy của khách yêu cầu thanh lý",
                                desc="Từ yêu cầu thanh lý, qua kết quả tư vấn, đến tình trạng hợp đồng hiện nay (cột hợp đồng lấy theo tình trạng NET hiện tại của file)."),
                     _khoang(),
                     html.Div([card([ve.xep_chong(theo_ngay, MAU_TU_VAN, ngang=False, cao=320)], title="SR thanh lý mỗi ngày, theo kết quả tư vấn",
                                    desc="Ngày nào nhiều khách không đồng ý thì cần xem lại chính sách giữ khách."),
                               card([ch.cot_ngang(ly_do, "nguyen_nhan_1", "so", 320, mau=ch.CAM)], title="Vì sao khách thanh lý", desc="Nguyên nhân cấp 1 ghi trên SR thanh lý")],
                              className="dv-hai-cot")])


# ------------------------------------------------------------------ khách và dịch vụ
def _theo_goi_ve(df, cot, tieu_de):
    g = kt.theo_goi(df, cot)
    if g.empty:
        return _thieu(tieu_de)
    f = go.Figure()
    f.add_bar(x=g[cot], y=g["ty_le_thanh_ly"], name="% SR thanh lý", marker_color=ch.DO, text=[ch.pct(v, 0) for v in g["ty_le_thanh_ly"]], textposition="outside")
    f.add_bar(x=g[cot], y=g["ty_le_khieu_nai"], name="% SR khiếu nại", marker_color=ch.CAM, text=[ch.pct(v, 0) for v in g["ty_le_khieu_nai"]], textposition="outside")
    f.update_layout(barmode="group")
    f.update_yaxes(ticksuffix="%", rangemode="tozero")
    return card([ch.khung(f, 300), html.Div("SR mỗi gói: " + " · ".join(f"{r[cot]} {ch.so(r['so_sr'])}" for _, r in g.iterrows()), className="desc")], title=tieu_de,
                desc="Tỷ lệ tính trên số SR của gói đó (không phải trên số khách). Gói có từ 30 SR trở lên mới hiện.")


def _nguon_tao_ve(df):
    g = kt.theo_nguon_tao(df)
    if g.empty:
        return _thieu("Ai tạo SR")
    cao = g[g["so_sr"] >= kt.MAU_TOI_THIEU].assign(ty_kn=lambda x: x["khieu_nai"] * 100 / x["so_sr"]).sort_values("ty_kn", ascending=False).iloc[0]
    nhan = g.sort_values("so_sr")
    f = go.Figure(go.Bar(y=nhan["nguon_tao_nhom"], x=nhan["so_sr"], orientation="h", marker_color=ch.XANH,
                         text=[f"{ch.so(r.so_sr)} ({ch.pct(r.ty_trong, 0)})" for r in nhan.itertuples()], textposition="outside", cliponaxis=False))
    f.update_xaxes(visible=False, range=[0, float(nhan["so_sr"].max()) * 1.3])
    f.update_yaxes(automargin=True)
    ket = f"{cao['nguon_tao_nhom']} tạo {ch.so(cao['so_sr'])} SR, trong đó {ch.pct(cao['ty_kn'], 0)} là khiếu nại, phàn nàn. Đây là phản ánh từ khách mới hoặc khách sau bán nên cần chuyển về khối Kinh doanh xem lại chất lượng bán." if cao["ty_kn"] >= 50 else ""
    return card([html.Div(ket, className="dv-ket-luan") if ket else None, ch.khung(f, 300, legend=False)], title="Ai tạo SR",
                desc="Khách tự tạo qua app hoặc tổng đài, nhân viên DVKH, phòng kinh doanh, triển khai bảo trì, hỗ trợ khách hàng, hệ thống / bot.")


def _phi_ve(df):
    g = kt.phi_mien_giam(df)
    if g.empty:
        return card([html.Div("Không có SR thu phí trong phạm vi này.", className="desc")], title="Phí và miễn giảm")
    f = go.Figure()
    f.add_bar(x=g["loai_yc"], y=g["phi"] / 1e6, name="Phí phát sinh", marker_color=ch.XANH, text=[f"{v / 1e6:.1f} tr" for v in g["phi"]], textposition="outside")
    f.add_bar(x=g["loai_yc"], y=g["mien_giam"] / 1e6, name="Đã miễn giảm", marker_color=ch.CAM, text=[f"{v / 1e6:.1f} tr" for v in g["mien_giam"]], textposition="outside")
    f.update_layout(barmode="group")
    f.update_yaxes(title="Triệu đồng", rangemode="tozero")
    phi, mg = float(g["phi"].sum()), float(g["mien_giam"].sum())
    vuot = g[g["mien_giam"] > g["phi"]]
    ket = f"Phí phát sinh {phi / 1e6:.1f} triệu, đã miễn giảm {mg / 1e6:.1f} triệu ({ch.pct(mg * 100 / phi, 0)}). " + \
          ("".join(f"{r.loai_yc}: miễn giảm {ch.pct(r.ty_le_mien_giam, 0)} so với phí của chính loại này. " for r in vuot.itertuples()))
    return card([html.Div(ket, className="dv-ket-luan"), ch.khung(f, 300)], title="Phí và miễn giảm",
                desc="Chỉ các loại yêu cầu có thu phí. Miễn giảm vượt phí nghĩa là doanh thu ròng của loại việc đó âm.")


def _duyet_ve(df):
    ct = kt.duyet_de_xuat(df)
    if ct.empty:
        return _thieu("Đề xuất cần duyệt")
    mau = {"Đã xử lý": ch.LUC, "Chưa xử lý": ch.CAM, "Đã hủy": "#B8C4D3"}
    return card([ve.xep_chong(ct, mau, cao=260)], title="Đề xuất cần duyệt", desc="Miễn giảm, đổi câu lệnh giá, khoá rời mạng, theo trạng thái duyệt. Phần cam là còn chờ duyệt.")


def khach_dich_vu(df):
    return html.Div([html.Div([_theo_goi_ve(df, "goi_net_nhom", "Thanh lý và khiếu nại theo gói Internet"), _theo_goi_ve(df, "goi_pay_nhom", "Thanh lý và khiếu nại theo gói FPT Play")], className="dv-hai-cot"),
                     _khoang(), html.Div([_nguon_tao_ve(df), _phi_ve(df)], className="dv-hai-cot"), _khoang(), _duyet_ve(df)])


# ------------------------------------------------------------------ vòng tròn nguyên nhân, tuổi tồn
def vong_nguyen_nhan(df):
    d = df.assign(p=df["phan_loai"].fillna("Không ghi phân loại"))
    g = d.groupby(["loai_yc", "p"]).size().reset_index(name="so")
    g.loc[g["so"] < 12, "p"] = "Khác"
    g = g.groupby(["loai_yc", "p"], as_index=False)["so"].sum()
    f = px.sunburst(g, path=["loai_yc", "p"], values="so", color_discrete_sequence=ch.DAY_MAU + ["#C9D2DE", "#5CC58B", "#E8A33D"])
    f.update_traces(hovertemplate="%{label}: %{value} SR<extra></extra>", insidetextorientation="radial")
    return ch.khung(f, 520, legend=False)


def tuoi_ton(df):
    ct = kt.tuoi_ton(df, "tg_yc", "loai_yc")
    if ct.empty:
        return None
    return card([ve.xep_chong(ct.loc[ct.sum(axis=1).sort_values(ascending=False).index], {"Dưới 1 ngày": ch.LUC, "1 đến 3 ngày": ve.VANG, "3 đến 7 ngày": ch.CAM, "Trên 7 ngày": ch.DO}, cao=320)],
                title="SR tồn đã chờ bao lâu", desc="Mỗi loại yêu cầu, chia theo tuổi tính từ lúc tạo tới SR mới nhất trong file. Phần cam và đỏ là SR bị bỏ quên.")
