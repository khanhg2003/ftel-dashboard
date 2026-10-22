"""Trang SR chủ động (DVKH chủ động chăm sóc khách có nguy cơ rời mạng / chất lượng kém): chương trình, hiệu quả liên hệ, điểm nguy cơ, SR tồn."""
from __future__ import annotations

from datetime import date

import plotly.graph_objects as go
from dash import Input, Output, dcc, html

from app.dvkh import khai_thac as kt, so_lieu as sl, xu_huong as xh
from app.ui.components import card
from app.ui.pages import dvkh_chung as ch, dvkh_ve as ve

TAB = [("tq", "Tổng quan"), ("ct", "Theo chương trình"), ("lh", "Hiệu quả liên hệ"), ("rm", "Điểm nguy cơ & lý do"), ("ton", "SR tồn")]
MAU_TT = {"Đã hoàn tất": ch.LUC, "Đã xử lý": "#5CC58B", "Đóng tự động bởi hệ thống": ch.XAM, "Đang xử lý": ch.XANH, "Chưa xử lý": ch.CAM,
          "Chưa phân công": ch.DO, "Xử lý không thành công": ch.TIM}


def topbar():
    return [html.Div([html.H1("SR chủ động"), html.Div("Chăm sóc khách có nguy cơ rời mạng: chương trình nào tồn, gọi có gặp khách không, điểm nguy cơ có đúng không", className="sub")])]


def layout():
    df = sl.sr_chu_dong()
    tu, den = (df["ngay_do"].min().date(), df["ngay_do"].max().date()) if len(df) else (date.today(), date.today())
    ct = [{"label": "Tất cả nhóm chương trình", "value": "all"}] + [{"label": x, "value": x} for x in
                                                                    ["Nguy cơ rời mạng (SOS)", "KSRM T", "KSRM T-1", "CLL (Checklist lặp)", "Chương trình khác"]]
    return html.Div([
        ch.thanh_loc("dvcd", ngay_min=tu, ngay_max=den, ngay=None, khoang=True,
                     them=[html.Div([html.Label("Nhóm chương trình"), dcc.Dropdown(id="dvcd-nhom", options=ct, value="all", clearable=False,
                                                                                   style={"minWidth": "240px"})], className="field")]),
        ch.tab_nho("dvcd-tab", TAB, "tq"),
        html.Div(style={"height": "14px"}),
        dcc.Loading(html.Div(id="dvcd-noi-dung"), type="dot"),
    ])


def _tq(df):
    k = sl.kpi_cd(df)
    kpi_ = ch.hang_kpi([
        ("SR đổ về", ch.so(k["so_sr"]), f"{ch.so(k['so_hd'])} hợp đồng · {ch.so(k['phan_cong'])} đã phân công", ""),
        ("SR tồn", ch.pct(k["ty_le_ton"], 0), f"{ch.so(k['chua_xu_ly'])} chưa xử lý · {ch.so(k['chua_phan_cong'])} chưa phân công · {ch.so(k['dang_xu_ly'])} đang xử lý",
         ch.muc_theo_nguong(k["ty_le_ton"], 15, 35)),
        ("Quá hạn", ch.pct(k["ty_le_qua_han"], 0), f"{ch.so(k['qua_han'])} SR", ch.muc_theo_nguong(k["ty_le_qua_han"], 10, 25)),
        ("Gặp được khách", ch.pct(k["ty_le_gap"], 0), f"Trên {ch.so(k['da_thu_lien_he'])} SR đã thử liên hệ", ch.muc_theo_nguong(k["ty_le_gap"], 80, 60, cao_xau=False)),
        ("Không liên lạc được", ch.pct(k["ty_le_khong_lien_lac"], 0), f"{ch.so(k['khong_lien_lac'])} SR", ch.muc_theo_nguong(k["ty_le_khong_lien_lac"], 15, 30)),
        ("Không cần liên hệ / tự đóng", ch.pct(k["ty_le_khong_can_lh"] + k["ty_le_dong_tu_dong"], 0),
         f"{ch.so(k['khong_can_lh'])} không cần · {ch.so(k['dong_tu_dong'])} tự đóng", "")])
    ngay = df.groupby(["ngay_do", "nhom_bc"]).size().unstack(fill_value=0)
    f = go.Figure()
    for i, c in enumerate(ngay.columns):
        f.add_bar(x=ngay.index, y=ngay[c], name=c, marker_color=ch.DAY_MAU[i % len(ch.DAY_MAU)])
    f.update_layout(barmode="stack")
    f.update_xaxes(tickformat="%d/%m")
    tt = sl.dem_theo(df, "tinh_trang")
    d = go.Figure(go.Pie(labels=tt["tinh_trang"], values=tt["so"], hole=.55, text=[f"{v:.0f}%" if v >= 4 else "" for v in tt["ty_trong"]], textinfo="text", sort=False,
                         marker={"colors": [MAU_TT.get(x, ch.XAM) for x in tt["tinh_trang"]]}))
    return html.Div([kpi_, html.Div([card([ch.khung(f, 300)], title="SR đổ về theo ngày", desc="Xếp chồng theo nhóm chương trình"),
                                     card([ch.khung(d, 300)], title="Tình trạng xử lý", desc="Tỷ trọng theo trạng thái")], className="dv-hai-cot"),
                     html.Div(style={"height": "16px"}),
                     html.Div("Xu hướng", className="dv-tieu-nhom"), _xu_huong(df),
                     html.Div("Theo nhóm chương trình", className="dv-tieu-nhom"),
                     _nhiet_ct(sl.theo_chuong_trinh(df, "nhom_bc"), "nhom_bc", "Theo nhóm chương trình (như bảng BC)",
                               "SOS = Ngưng kết nối + Dự đoán RM + nợ cước; KSRM T / T-1 = CSKH không PSLL vết T / T-1. Mỗi cột tô từ xanh (tốt nhất) đến đỏ (xấu nhất).")])


def _xu_huong(df):
    luong = xh.luong_theo_ngay(df, "ngay_do")
    if len(luong) < 2:
        return html.Div("Cần ít nhất 2 ngày dữ liệu để vẽ xu hướng.", className="desc")
    h = xh.huong(luong["ton_cuoi_ngay"])
    cau = {"giam": "Tồn đang giảm: dọn nhanh hơn việc đổ về.", "tang": "Tồn đang tăng: việc đổ về nhiều hơn khả năng xử lý.", "di_ngang": "Tồn đi ngang.", None: ""}[h["huong"] if h else None]
    coh = kt.theo_ngay_do_va_tinh_trang(df)
    cu = coh.iloc[:-1]
    bo = cu["Chưa xử lý / chưa phân công"].sum() if len(cu) else 0
    ket = f"{cau} Trong các ngày đổ về trước ngày mới nhất, còn {ch.so(bo)} SR chưa ai xử lý." if len(cu) else cau
    return html.Div([card([html.Div([html.B("Xu hướng: "), ket], className="dv-ket-luan"), ve.vao_ra_ton(luong, "SR chủ động đổ về")], title="SR vào, ra và tồn theo ngày",
                          desc="Ngày đổ nhiều thì tồn nhảy lên; xem sau đó mấy ngày mới dọn xong. Cột lá là SR đã xử lý xong hoặc hệ thống tự đóng."),
                     card([ve.xep_chong(coh, ve.MAU_TT_CD, ngang=False, cao=320)], title="SR đổ về mỗi ngày giờ ra sao",
                          desc="Mỗi cột là một ngày đổ về, chia theo tình trạng hiện nay. Ngày cũ mà vẫn còn cam là việc bị bỏ rơi.")], className="dv-hai-cot")


def _nhiet_ct(g, cot_ten, tieu_de, mo_ta):
    """Bản đồ nhiệt các chỉ số của từng chương trình / nhóm chương trình (thay cho bảng nhiều cột)."""
    chi_so = [("so_sr", "SR", "{:,.0f}", None), ("ty_le_ton", "% tồn", "{:.0f}%", False), ("ty_le_qua_han", "% quá hạn", "{:.0f}%", False),
              ("ty_le_khong_lien_lac", "% không<br>liên lạc", "{:.0f}%", False), ("ty_le_khong_can_lh", "% không<br>cần LH", "{:.0f}%", False),
              ("ty_le_dong_tu_dong", "% tự đóng", "{:.0f}%", False), ("muon_thanh_ly", "Đòi<br>thanh lý", "{:,.0f}", False)]
    return card([ve.nhiet_bang(g, cot_ten, chi_so)], title=tieu_de, desc=mo_ta)


def _ct(df):
    ct = sl.theo_chuong_trinh(df)
    ct = ct.assign(chuong_trinh=ct["chuong_trinh"].str.strip())
    mau = [ch.DO if v >= 80 else (ch.CAM if v >= 40 else ch.XANH) for v in ct.head(12).iloc[::-1]["ty_le_ton"]]
    kll = ct[ct["thu"] >= 30].sort_values("ty_le_khong_lien_lac", ascending=False)
    return html.Div([
        _nhiet_ct(ct, "chuong_trinh", "Theo chương trình",
                  "Mỗi cột tô từ xanh (tốt nhất) đến đỏ (xấu nhất). Chương trình tồn gần hết là chương trình chưa có người nhận; % không liên lạc tính trên SR đã thử liên hệ."),
        html.Div(style={"height": "16px"}),
        card([ve.xep_chong(kt.theo_chuong_trinh_va_tinh_trang(df), ve.MAU_TT_CD, phan_tram=False, cao=420)], title="Mỗi chương trình đang ở đâu",
             desc="Số SR của 10 chương trình đông nhất, chia theo tình trạng. Phần cam là chưa ai xử lý: chương trình nào cam gần hết là chưa có người nhận."),
        html.Div(style={"height": "16px"}),
        html.Div([card([ch.cot_ngang(ct, "chuong_trinh", "ty_le_ton", 360, hau_to="%", mau_cot=mau, chu="{:.0f}%")],
                       title="Tỷ lệ tồn theo chương trình", desc="Đỏ từ 80%, cam từ 40%"),
                  card([ch.cot_ngang(kll, "chuong_trinh", "ty_le_khong_lien_lac", 360, mau=ch.CAM, chu="{:.0f}%")], title="Tỷ lệ không liên lạc được",
                       desc="Chương trình có từ 30 SR đã thử liên hệ trở lên")], className="dv-hai-cot")])


def _lh(df):
    k = sl.kpi_cd(df)
    pc = k["phan_cong"]
    thu = k["da_thu_lien_he"]
    gap = k["gap_khach"]
    f = go.Figure(go.Funnel(y=["SR đổ về", "Đã phân công", "Đã thử liên hệ", "Gặp được khách", "Khách đồng ý dùng tiếp"],
                            x=[k["so_sr"], pc, thu, gap, k["o_lai"]], textinfo="value+percent initial",
                            marker={"color": [ch.XANH, "#2F8BCB", ch.XANH_NHAT, ch.LUC, "#5CC58B"]}))
    cc = df[df["cong_cu"].notna()].groupby("cong_cu").agg(so_sr=("ma_sr", "size"), thu=("da_thu_lien_he", "sum"), gap=("gap_khach", "sum"),
                                                          khong_lien_lac=("khong_lien_lac", "sum")).reset_index()
    cc["ty_le_gap"] = cc["gap"] * 100 / cc["thu"].replace(0, float("nan"))
    cc["ty_le_khong_lien_lac"] = cc["khong_lien_lac"] * 100 / cc["thu"].replace(0, float("nan"))
    cc = cc.sort_values("so_sr", ascending=False)
    nhan_cc = [f"{ch.xuong_dong(c)}<br>({ch.so(n)} SR)" for c, n in zip(cc["cong_cu"], cc["so_sr"])]
    fcc = go.Figure()
    fcc.add_bar(x=nhan_cc, y=cc["ty_le_gap"], name="% gặp được khách", marker_color=ch.LUC, text=[ch.pct(v, 0) for v in cc["ty_le_gap"]], textposition="outside", cliponaxis=False)
    fcc.add_bar(x=nhan_cc, y=cc["ty_le_khong_lien_lac"], name="% không liên lạc được", marker_color=ch.CAM, text=[ch.pct(v, 0) for v in cc["ty_le_khong_lien_lac"]],
                textposition="outside", cliponaxis=False)
    fcc.update_layout(barmode="group")
    fcc.update_xaxes(tickangle=0)
    fcc.update_yaxes(ticksuffix="%", rangemode="tozero")
    tv = sl.dem_theo(df[df["ket_qua_tu_van"].notna()], "ket_qua_tu_van", 10)
    lh = sl.dem_theo(df[df["ly_do_khong_lh"].notna()], "ly_do_khong_lh", 8)
    sl_cs = sl.dem_theo(df[df["so_lan_cs"].notna()].assign(so_lan_cs=lambda x: x["so_lan_cs"].astype(int).astype(str) + " lần"), "so_lan_cs")
    return html.Div([
        html.Div([card([ch.khung(f, 330, legend=False)], title="Từ SR đổ về đến khách ở lại", desc="Phần trăm so với SR đổ về"),
                  card([ch.khung(fcc, 330)], title="Hiệu quả theo công cụ liên hệ", desc="Trên SR đã thử liên hệ. Gọi tay, máy gọi tự động, CSKH mở rộng, tại quầy...")], className="dv-hai-cot"),
        html.Div(style={"height": "16px"}),
        html.Div([card([ch.cot_ngang(tv, "ket_qua_tu_van", "so", 360)], title="Kết quả tư vấn", desc="10 kết quả nhiều nhất"),
                  card([ch.cot_ngang(lh, "ly_do_khong_lh", "so", 360, mau=ch.XAM)], title="Vì sao không cần liên hệ",
                       desc="Công sức phân công không tạo giá trị: lọc từ nguồn đổ SR")], className="dv-hai-cot"),
        html.Div(style={"height": "16px"}),
        card([ch.cot_ngang(sl_cs, "so_lan_cs", "so", 260, mau=ch.XANH_NHAT)], title="Số lần chăm sóc mỗi SR", desc="Chăm sóc nhiều lần mà chưa xong là dấu hiệu khó")])


def _rm(df):
    bac = sl.theo_bac_diem(df)
    nhan_bac = [f"{b}<br>({ch.so(n)} SR)" for b, n in zip(bac["bac_diem"], bac["so_sr"])]
    fb = go.Figure()
    fb.add_bar(x=nhan_bac, y=bac["ty_le_thanh_ly"], name="% đòi thanh lý", marker_color=ch.DO, text=[ch.pct(v, 1) for v in bac["ty_le_thanh_ly"]], textposition="outside", cliponaxis=False)
    fb.add_bar(x=nhan_bac, y=bac["ty_le_o_lai"], name="% đồng ý dùng tiếp", marker_color=ch.LUC, text=[ch.pct(v, 0) for v in bac["ty_le_o_lai"]], textposition="outside", cliponaxis=False)
    fb.update_layout(barmode="group")
    fb.update_xaxes(tickangle=0)
    fb.update_yaxes(ticksuffix="%", rangemode="tozero")
    mk = sl.dem_theo(df[df["ly_do_mat_kn"].notna()], "ly_do_mat_kn")
    nguon = sl.dem_theo(df, "nguon_pp", 6)
    nc = df.groupby("nhom_bc").agg(so_sr=("ma_sr", "size"), no_cuoc=("no_cuoc", "sum"), ych=("ych", "sum")).reset_index()
    nc["ty_no"] = nc["no_cuoc"] * 100 / nc["so_sr"]
    nc["ty_ych"] = nc["ych"] * 100 / nc["so_sr"]
    fn = go.Figure()
    fn.add_bar(x=nc["nhom_bc"].map(ch.xuong_dong), y=nc["ty_no"], name="% hợp đồng đang nợ cước", marker_color=ch.CAM, text=[ch.pct(v, 0) for v in nc["ty_no"]], textposition="outside", cliponaxis=False)
    fn.add_bar(x=nc["nhom_bc"].map(ch.xuong_dong), y=nc["ty_ych"], name="% trong danh sách yêu cầu huỷ", marker_color=ch.DO, text=[ch.pct(v, 0) for v in nc["ty_ych"]], textposition="outside", cliponaxis=False)
    fn.update_layout(barmode="group")
    fn.update_xaxes(tickangle=0)
    fn.update_yaxes(ticksuffix="%", rangemode="tozero")
    return html.Div([
        card([ch.khung(fb, 320)], title="Điểm nguy cơ rời mạng có đáng tin không?",
             desc="Điểm càng cao mà tỷ lệ khách đòi thanh lý không cao hơn thì điểm chưa giúp xếp ưu tiên. Chỉ SR đã có kết quả tư vấn mới xét."),
        html.Div(style={"height": "16px"}),
        html.Div([card([ch.cot_ngang(mk, "ly_do_mat_kn", "so", 220, mau=ch.CAM)], title="Lý do mất kết nối", desc="Cúp điện không cần CSKH gọi"),
                  card([ch.cot_ngang(nguon, "nguon_pp", "so", 220, mau=ch.XANH)], title="Nguồn phân phối SR", desc="SR do đơn vị nào đổ về")], className="dv-hai-cot"),
        html.Div(style={"height": "16px"}),
        card([ch.khung(fn, 320)], title="Nợ cước và yêu cầu huỷ trên SR chủ động",
             desc="Hợp đồng vừa bị chăm sóc vừa nợ cước nên gộp một lần gọi")])


def _ton(df):
    t = df[df["ton"]].copy()
    moc = df["tg_do"].max()
    t["tuoi_gio"] = ((moc - t["tg_do"]).dt.total_seconds() / 3600).round(1)
    thu_tu = {"Rất cao": 0, "Cao": 1, "Khá cao": 2, "Trung bình": 3, "Thấp": 4}
    t["_u"] = t["do_uu_tien"].map(thu_tu).fillna(9)
    t = t.sort_values(["_u", "tuoi_gio"], ascending=[True, False])
    t["tg_do_chu"] = t["tg_do"].dt.strftime("%d/%m %H:%M")
    t["chuong_trinh"] = t["chuong_trinh"].str.strip()
    cot = [ch.cot_chu("ma_sr", "Mã SR", 260), ch.cot_chu("so_hd", "Hợp đồng", 110), ch.cot_chu("chuong_trinh", "Chương trình", None), ch.cot_chu("quan", "Phường / xã", 150),
           ch.cot_chu("nguoi_xu_ly", "Người xử lý", 130), ch.cot_chu("tinh_trang", "Tình trạng", 130), ch.cot_chu("do_uu_tien", "Ưu tiên", 100),
           ch.cot_so("diem_rm", "Điểm RM", 90), ch.cot_chu("tg_do_chu", "Đổ về lúc", 110), ch.cot_so("tuoi_gio", "Tuổi (giờ)", 100)]
    for c in cot:
        c["filter"] = True
    cao = int(t["do_uu_tien"].eq("Rất cao").sum())
    tuoi = kt.tuoi_ton(df, "tg_do", "nhom_bc")
    bieu_do_tuoi = card([ve.xep_chong(tuoi.loc[tuoi.sum(axis=1).sort_values(ascending=False).index], {"Dưới 1 ngày": ch.LUC, "1 đến 3 ngày": ve.VANG, "3 đến 7 ngày": ch.CAM,
                                                                                                    "Trên 7 ngày": ch.DO}, cao=300)],
                        title="SR tồn đã chờ bao lâu", desc="Mỗi nhóm chương trình, chia theo tuổi tính từ lúc đổ về. Phần cam và đỏ là SR bị bỏ quên.") if len(tuoi) else None
    return html.Div([ch.hang_kpi([("SR tồn", ch.so(len(t)), f"Tính tới SR mới nhất: {moc:%d/%m %H:%M}", ""),
                                  ("Ưu tiên rất cao còn tồn", ch.so(cao), "Xử lý trước", "bad" if cao else "ok"),
                                  ("Chưa phân công", ch.so(t["nguoi_xu_ly"].isna().sum()), "Chưa có người nhận", "warn")]),
                     *([bieu_do_tuoi, html.Div(style={"height": "16px"})] if bieu_do_tuoi is not None else []),
                     card([ch.bang_df("dvcd-ton", t, cot, 520)], title="Danh sách SR tồn", desc="Ưu tiên rất cao lên đầu, cũ nhất trước. Lọc được theo từng cột.")])


def register(app):
    @app.callback(Output("dvcd-noi-dung", "children"), Input("dvcd-tab", "value"), Input("dvcd-phong", "value"), Input("dvcd-ngay", "start_date"),
                  Input("dvcd-ngay", "end_date"), Input("dvcd-nhom", "value"))
    def _ve(tab, phong, tu, den, nhom):
        df = sl.sr_chu_dong()
        if df.empty:
            return html.Div("Chưa có SR chủ động.", className="desc")
        df = sl.loc(df, ch.phong_ma(phong), tu, den, "ngay_do")
        if nhom not in (None, "all"):
            df = df[df["nhom_bc"] == nhom]
        if df.empty:
            return html.Div("Không có SR nào trong phạm vi đã chọn.", className="desc")
        return {"tq": _tq, "ct": _ct, "lh": _lh, "rm": _rm, "ton": _ton}.get(tab, _tq)(df)
