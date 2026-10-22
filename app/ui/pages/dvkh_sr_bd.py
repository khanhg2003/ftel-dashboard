"""Trang SR bị động (khách chủ động yêu cầu, khiếu nại, thanh lý...): tổng quan, loại yêu cầu và nguyên nhân, kênh và thời gian, SR tồn, hợp đồng gọi lặp."""
from __future__ import annotations

from datetime import date

import plotly.graph_objects as go
from dash import Input, Output, dcc, html

from app.dvkh import so_lieu as sl
from app.dvkh.doc_file import bo_dau
from app.ui.components import card
from app.ui.pages import dvkh_chung as ch, dvkh_sr_bd_sau as sau

TAB = [("tq", "Tổng quan"), ("gc", "Giữ chân khách"), ("nn", "Loại yêu cầu & nguyên nhân"), ("kd", "Khách & dịch vụ"), ("kenh", "Kênh & thời gian"),
       ("ton", "SR tồn"), ("lap", "Hợp đồng gọi lặp")]
THU = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]


def topbar():
    return [html.Div([html.H1("SR bị động"), html.Div("Khách chủ động yêu cầu, khiếu nại, thanh lý: ai xử lý, bao lâu, vì sao", className="sub")])]


def layout():
    df = sl.sr_bi_dong()
    tu, den = (df["ngay_yc"].min().date(), df["ngay_yc"].max().date()) if len(df) else (date.today(), date.today())
    loai = [{"label": "Tất cả loại yêu cầu", "value": "all"}] + [{"label": x, "value": x} for x in sorted(df["loai_yc"].dropna().unique())]
    return html.Div([
        ch.thanh_loc("dvbd", ngay_min=tu, ngay_max=den, ngay=None, khoang=True,
                     them=[html.Div([html.Label("Loại yêu cầu"), dcc.Dropdown(id="dvbd-loai", options=loai, value="all", clearable=False,
                                                                              style={"minWidth": "240px"})], className="field")]),
        ch.tab_nho("dvbd-tab", TAB, "tq"),
        html.Div(style={"height": "14px"}),
        dcc.Loading(html.Div(id="dvbd-noi-dung"), type="dot"),
    ])


def _khoang(df, tu, den):
    return sl.loc(df, None, tu, den, "ngay_yc")


# ------------------------------------------------------------------ các tab
def _tq(df):
    k = sl.kpi_bd(df)
    kpi_ = ch.hang_kpi([
        ("SR phát sinh", ch.so(k["so_sr"]), f"{ch.so(k['so_hd'])} hợp đồng · {ch.so(k['phan_cong'])} đã phân công", ""),
        ("Đã xử lý xong", ch.pct(k["ty_le_xu_ly"]), f"{ch.so(k['da_xu_ly'])} SR · không thành công {ch.so(k['that_bai'])}",
         ch.muc_theo_nguong(k["ty_le_xu_ly"], 85, 60, cao_xau=False)),
        ("SR tồn", ch.so(k["ton"]), f"{ch.so(k['chua_xu_ly'])} chưa xử lý · {ch.so(k['dang_xu_ly'])} đang xử lý", ""),
        ("Quá hạn", ch.pct(k["ty_le_qua_han"]), f"{ch.so(k['qua_han'])} SR", ch.muc_theo_nguong(k["ty_le_qua_han"], 10, 30)),
        ("Phản hồi trong 60 phút", ch.pct(k["trong_60p"], 0), f"Trung vị {ch.so(k['phan_hoi_p50'])} phút · chậm nhất 10%: trên {ch.so(k['phan_hoi_p90'])} phút",
         ch.muc_theo_nguong(k["trong_60p"], 90, 70, cao_xau=False)),
        ("Đóng SR (trung vị)", f"{ch.so(k['xu_ly_p50_gio'], 1)} giờ", f"Gọi lặp: {ch.pct(k['ty_le_lap'], 0)} SR", "")])
    ngay = sl.theo_ngay_bd(df)
    f = go.Figure()
    if not ngay.empty:
        khac = ngay["so_sr"] - ngay["da_xu_ly"] - ngay["ton"]
        f.add_bar(x=ngay["ngay_yc"], y=ngay["da_xu_ly"], name="Đã xử lý xong", marker_color=ch.LUC)
        f.add_bar(x=ngay["ngay_yc"], y=ngay["ton"], name="Còn tồn", marker_color=ch.CAM)
        f.add_bar(x=ngay["ngay_yc"], y=khac, name="Không thành công / chuyển", marker_color=ch.XAM)
        f.update_layout(barmode="stack")
        f.update_xaxes(tickformat="%d/%m")
    tt = sl.dem_theo(df, "tinh_trang")
    d = go.Figure(go.Pie(labels=tt["tinh_trang"], values=tt["so"], hole=.55, text=[f"{v:.0f}%" if v >= 4 else "" for v in tt["ty_trong"]], textinfo="text", sort=False,
                         marker={"colors": [ch.LUC, ch.XANH, ch.XAM, ch.CAM, DO_NHAT, TIM_NHAT, XAM_NHAT][:len(tt)]}))
    return html.Div([kpi_, html.Div([card([ch.khung(f, 300)], title="SR theo ngày", desc="Xếp chồng theo kết quả xử lý hiện tại"),
                                     card([ch.khung(d, 300)], title="Tình trạng xử lý", desc="Tỷ trọng theo trạng thái")], className="dv-hai-cot"),
                     html.Div(style={"height": "16px"}),
                     html.Div("Xu hướng", className="dv-tieu-nhom"), sau.xu_huong(df),
                     html.Div("Theo phường / xã", className="dv-tieu-nhom"),
                     sau.theo_phuong(_theo_phuong(df))])


DO_NHAT, TIM_NHAT, XAM_NHAT = "#E8A33D", "#8C6FD1", "#C9D2DE"


def _theo_phuong(df):
    g = df.groupby("quan").agg(so_sr=("ma_sr", "size"), ton=("ton", "sum"), qua_han=("qua_han_cd", "sum"), phan_hoi_p50=("phan_hoi_phut", "median"),
                               khieu_nai=("loai_yc", lambda s: int((s == "Khiếu nại, phàn nàn").sum())),
                               thanh_ly=("loai_yc", lambda s: int((s == "Thanh lý").sum()))).reset_index().rename(columns={"quan": "phuong"})
    g["ty_le_qua_han"] = g["qua_han"] * 100 / g["so_sr"]
    rm = sl.roi_mang_moi_nhat()
    if not rm.empty:
        rm = rm[rm["cap"] == "quan"].copy()
        rm["khoa"] = rm["ten"].map(bo_dau)
        g["khoa"] = g["phuong"].map(bo_dau)
        g = g.merge(rm[["khoa", "kh_active"]], on="khoa", how="left")
        g["sr_1000"] = g["so_sr"] * 1000 / g["kh_active"]
    else:
        g["sr_1000"] = None
    return g.sort_values("so_sr", ascending=False)


def _nn(df, loai):
    theo = sl.theo_loai_yc(df)
    sub = df if loai in (None, "all") else df[df["loai_yc"] == loai]
    pl = sl.dem_theo(sub[sub["phan_loai"].notna()], "phan_loai", 10)
    n1 = sl.dem_theo(sub[sub["nguyen_nhan_1"].notna()], "nguyen_nhan_1", 10)
    n2 = sl.dem_theo(sub[sub["nguyen_nhan_2"].notna()], "nguyen_nhan_2", 10)
    gc = "Mỗi SR có thể có nhiều cấp nguyên nhân; nhóm nào không ghi thì không đếm."
    return html.Div([
        html.Div([sau.loai_yeu_cau_nhiet(theo), sau.loai_va_phan_loai(df)], className="dv-hai-cot"),
        html.Div(style={"height": "16px"}),
        html.Div([card([ch.cot_ngang(pl, "phan_loai", "so", 330)], title="Phân loại khiếu nại / thay đổi / giải đáp", desc=gc),
                  card([ch.cot_ngang(n1, "nguyen_nhan_1", "so", 330, mau=ch.CAM)], title="Nguyên nhân cấp 1", desc="10 nguyên nhân nhiều nhất")], className="dv-hai-cot"),
        html.Div(style={"height": "16px"}),
        card([ch.cot_ngang(n2, "nguyen_nhan_2", "so", 330, mau=ch.TIM)], title="Nguyên nhân cấp 2 (chi tiết)",
             desc=f"{ch.so(len(sub[sub['nguyen_nhan_2'].notna()]))} SR có ghi nguyên nhân cấp 2")])


def _kenh(df):
    g = df.groupby(["kenh", "nhom_kenh"]).agg(so_sr=("ma_sr", "size"), ton=("ton", "sum"), qua_han=("qua_han_cd", "sum"),
                                              phan_hoi_p50=("phan_hoi_phut", "median"),
                                              trong_60=("phan_hoi_phut", lambda s: float((s.dropna() <= 60).mean() * 100) if s.notna().any() else None)).reset_index()
    g["ty_trong"] = g["so_sr"] * 100 / g["so_sr"].sum()
    g["ty_le_qua_han"] = g["qua_han"] * 100 / g["so_sr"]
    g = g.sort_values("so_sr", ascending=False)
    nhom = df["nhom_kenh"].value_counts()
    hm = df.groupby(["thu", "gio"]).size().unstack(fill_value=0).reindex(index=range(7), columns=range(24), fill_value=0)
    f = go.Figure(go.Heatmap(z=hm.values, x=[f"{h}h" for h in hm.columns], y=THU, colorscale=[[0, "#F2F6FB"], [1, ch.XANH]], hovertemplate="%{y} %{x}: %{z} SR<extra></extra>",
                             showscale=False))
    f.update_yaxes(autorange="reversed")
    gio = df.groupby("gio").agg(so_sr=("ma_sr", "size"), qua_han=("qua_han_cd", "sum")).reset_index()
    gio["ty_le"] = gio["qua_han"] * 100 / gio["so_sr"]
    g2 = go.Figure()
    g2.add_bar(x=gio["gio"], y=gio["so_sr"], name="SR", marker_color=ch.XANH)
    g2.add_scatter(x=gio["gio"], y=gio["ty_le"], name="% quá hạn", yaxis="y2", mode="lines+markers", line={"color": ch.CAM})
    g2.update_layout(yaxis2={"overlaying": "y", "side": "right", "ticksuffix": "%", "showgrid": False})
    g2.update_xaxes(dtick=2, title="Giờ tạo SR")
    return html.Div([
        ch.hang_kpi([("Kênh số (Zalo, Hi FPT, MobiX...)", ch.pct(nhom.get("Kênh số", 0) * 100 / max(len(df), 1), 0), f"{ch.so(nhom.get('Kênh số', 0))} SR", ""),
                     ("Thoại / quầy", ch.pct(nhom.get("Thoại / quầy", 0) * 100 / max(len(df), 1), 0), f"{ch.so(nhom.get('Thoại / quầy', 0))} SR", ""),
                     ("Giờ cao điểm", f"{int(gio.sort_values('so_sr').iloc[-1]['gio'])}h", f"{ch.so(gio['so_sr'].max())} SR trong khung giờ này", "")]),
        sau.kenh_nhiet(g),
        html.Div(style={"height": "16px"}),
        html.Div([card([ch.khung(f, 300, legend=False)], title="Khi nào khách liên hệ", desc="Số SR theo thứ và giờ tạo"),
                  card([ch.khung(g2, 300)], title="Tải theo giờ và tỷ lệ quá hạn", desc="Giờ nào đông nhưng xử lý chậm")], className="dv-hai-cot")])


def _ton(df):
    tuoi = sau.tuoi_ton(df)
    t = df[df["ton"]].copy()
    moc = df["tg_yc"].max()
    t["tuoi_gio"] = ((moc - t["tg_yc"]).dt.total_seconds() / 3600).round(1)
    t = t.sort_values("tuoi_gio", ascending=False)
    t["tg_yc_chu"] = t["tg_yc"].dt.strftime("%d/%m %H:%M")
    cot = [ch.cot_chu("ma_sr", "Mã SR", 250), ch.cot_chu("so_hd", "Hợp đồng", 110), ch.cot_chu("loai_yc", "Loại yêu cầu", None), ch.cot_chu("quan", "Phường / xã", 150),
           ch.cot_chu("nguoi_xu_ly", "Người xử lý", 130), ch.cot_chu("tinh_trang", "Tình trạng", 120), ch.cot_chu("qua_han", "Hạn xử lý", 150),
           ch.cot_chu("tg_yc_chu", "Tạo lúc", 110), ch.cot_so("tuoi_gio", "Tuổi (giờ)", 100)]
    for c in cot:
        c["filter"] = True
    return html.Div([ch.hang_kpi([("SR tồn", ch.so(len(t)), f"Tính tới SR mới nhất trong file: {moc:%d/%m %H:%M}", ""),
                                  ("Tồn quá 24 giờ", ch.so((t["tuoi_gio"] > 24).sum()), "", "warn" if (t["tuoi_gio"] > 24).sum() else "ok"),
                                  ("Chưa phân công", ch.so(t["nguoi_xu_ly"].isna().sum()), "Không có người xử lý", "")]),
                     *([tuoi, html.Div(style={"height": "16px"})] if tuoi is not None else []),
                     card([ch.bang_df("dvbd-ton", t, cot, 520)], title="Danh sách SR tồn", desc="Cũ nhất lên đầu. Lọc được theo từng cột.")])


def _lap(df):
    k = sl.kpi_bd(df)
    pt = df.groupby("so_hd").size()
    hd = sl.hop_dong_lap(df, 200)
    cot = [ch.cot_chu("so_hd", "Hợp đồng", 120), ch.cot_so("so_sr", "Số SR", 80), ch.cot_chu("loai", "Các loại yêu cầu", None), ch.cot_chu("phong", "Phòng", 80),
           ch.cot_chu("quan", "Phường / xã", 150), ch.cot_so("ton", "Còn tồn", 90), ch.cot_chu("lan_cuoi_chu", "Lần gần nhất", 130)]
    if not hd.empty:
        hd["lan_cuoi_chu"] = hd["lan_cuoi"].dt.strftime("%d/%m %H:%M")
    return html.Div([ch.hang_kpi([("Hợp đồng gọi lặp", ch.so(k["hd_lap"]), "Từ 2 SR trở lên trong kỳ", "warn"),
                                  ("SR thuộc hợp đồng lặp", ch.pct(k["ty_le_lap"], 0), f"{ch.so(k['sr_lap'])} SR", ""),
                                  ("Hợp đồng gọi từ 4 lần", ch.so((pt >= 4).sum()), "Cần một người phụ trách đến khi ổn", "bad" if (pt >= 4).sum() else "ok")]),
                     sau.phan_bo_lap(pt), html.Div(style={"height": "16px"}),
                     card([ch.bang_df("dvbd-lap", hd, cot, 520)], title="Hợp đồng gọi lặp nhiều nhất",
                          desc="Gọi lặp thường là lần xử lý trước chưa dứt điểm. 200 hợp đồng nhiều SR nhất.")])


def register(app):
    @app.callback(Output("dvbd-noi-dung", "children"), Input("dvbd-tab", "value"), Input("dvbd-phong", "value"), Input("dvbd-ngay", "start_date"),
                  Input("dvbd-ngay", "end_date"), Input("dvbd-loai", "value"))
    def _ve(tab, phong, tu, den, loai):
        df = sl.sr_bi_dong()
        if df.empty:
            return html.Div("Chưa có SR bị động.", className="desc")
        df = _khoang(sl.loc(df, ch.phong_ma(phong)), tu, den)
        if tab in ("tq", "kenh", "ton", "lap", "kd") and loai not in (None, "all"):
            df = df[df["loai_yc"] == loai]
        if df.empty:
            return html.Div("Không có SR nào trong phạm vi đã chọn.", className="desc")
        if tab == "nn":
            return _nn(df, loai)
        return {"tq": _tq, "gc": sau.giu_chan, "kd": sau.khach_dich_vu, "kenh": _kenh, "ton": _ton, "lap": _lap}.get(tab, _tq)(df)
