"""Trang SR chủ động (DVKH chủ động chăm sóc khách có nguy cơ rời mạng / chất lượng kém): chương trình, hiệu quả liên hệ, điểm nguy cơ, SR tồn."""
from __future__ import annotations

from datetime import date

import plotly.graph_objects as go
from dash import Input, Output, dcc, html

from app.dvkh import so_lieu as sl
from app.ui.components import card
from app.ui.pages import dvkh_chung as ch

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
                     card([ch.bang_df("dvcd-nhom-bang", sl.theo_chuong_trinh(df, "nhom_bc"), _cot_ct("nhom_bc", "Nhóm chương trình"))],
                          title="Theo nhóm chương trình (như bảng BC)", desc="SOS = Ngưng kết nối + Dự đoán RM + nợ cước; KSRM T / T-1 = CSKH không PSLL vết T / T-1")])


def _cot_ct(ten_cot, tieu_de):
    return [ch.cot_chu(ten_cot, tieu_de, None), ch.cot_so("so_sr", "SR", 80), ch.cot_pct("ty_trong", "Tỷ trọng", 90), ch.cot_so("ton", "Tồn", 80),
            ch.cot_pct("ty_le_ton", "% tồn", 80), ch.cot_so("chua_phan_cong", "Chưa PC", 90), ch.cot_pct("ty_le_qua_han", "% quá hạn", 100),
            ch.cot_pct("ty_le_khong_lien_lac", "% không LL", 100), ch.cot_pct("ty_le_khong_can_lh", "% không cần LH", 120),
            ch.cot_pct("ty_le_dong_tu_dong", "% tự đóng", 100), ch.cot_so("muon_thanh_ly", "Muốn thanh lý", 120)]


def _ct(df):
    ct = sl.theo_chuong_trinh(df)
    ct = ct.assign(chuong_trinh=ct["chuong_trinh"].str.strip())
    mau = [ch.DO if v >= 80 else (ch.CAM if v >= 40 else ch.XANH) for v in ct.head(12).iloc[::-1]["ty_le_ton"]]
    kll = ct[ct["thu"] >= 30].sort_values("ty_le_khong_lien_lac", ascending=False)
    return html.Div([
        card([ch.bang_df("dvcd-ct", ct, _cot_ct("chuong_trinh", "Chương trình"), 420)], title="Theo chương trình",
             desc="Chương trình tồn gần hết là chương trình chưa có người nhận. % không LL tính trên SR đã thử liên hệ."),
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
    cot = [ch.cot_chu("cong_cu", "Công cụ liên hệ", None), ch.cot_so("so_sr", "SR", 80), ch.cot_so("thu", "Đã thử LH", 100), ch.cot_pct("ty_le_gap", "% gặp khách", 110),
           ch.cot_pct("ty_le_khong_lien_lac", "% không LL", 110)]
    tv = sl.dem_theo(df[df["ket_qua_tu_van"].notna()], "ket_qua_tu_van", 10)
    lh = sl.dem_theo(df[df["ly_do_khong_lh"].notna()], "ly_do_khong_lh", 8)
    sl_cs = sl.dem_theo(df[df["so_lan_cs"].notna()].assign(so_lan_cs=lambda x: x["so_lan_cs"].astype(int).astype(str) + " lần"), "so_lan_cs")
    return html.Div([
        html.Div([card([ch.khung(f, 330, legend=False)], title="Từ SR đổ về đến khách ở lại", desc="Phần trăm so với SR đổ về"),
                  card([ch.bang_df("dvcd-cc", cc, cot)], title="Hiệu quả theo công cụ liên hệ", desc="Gọi tay, máy gọi tự động, CSKH mở rộng, tại quầy...")], className="dv-hai-cot"),
        html.Div(style={"height": "16px"}),
        html.Div([card([ch.cot_ngang(tv, "ket_qua_tu_van", "so", 360)], title="Kết quả tư vấn", desc="10 kết quả nhiều nhất"),
                  card([ch.cot_ngang(lh, "ly_do_khong_lh", "so", 360, mau=ch.XAM)], title="Vì sao không cần liên hệ",
                       desc="Công sức phân công không tạo giá trị: lọc từ nguồn đổ SR")], className="dv-hai-cot"),
        html.Div(style={"height": "16px"}),
        card([ch.cot_ngang(sl_cs, "so_lan_cs", "so", 260, mau=ch.XANH_NHAT)], title="Số lần chăm sóc mỗi SR", desc="Chăm sóc nhiều lần mà chưa xong là dấu hiệu khó")])


def _rm(df):
    bac = sl.theo_bac_diem(df)
    cot = [ch.cot_chu("bac_diem", "Bậc điểm nguy cơ", None), ch.cot_so("so_sr", "SR đã có kết quả", 140), ch.cot_so("muon_thanh_ly", "Đòi thanh lý", 110),
           ch.cot_pct("ty_le_thanh_ly", "% đòi thanh lý", 120), ch.cot_pct("ty_le_o_lai", "% đồng ý dùng tiếp", 150)]
    mk = sl.dem_theo(df[df["ly_do_mat_kn"].notna()], "ly_do_mat_kn")
    nguon = sl.dem_theo(df, "nguon_pp", 6)
    nc = df.groupby("nhom_bc").agg(so_sr=("ma_sr", "size"), no_cuoc=("no_cuoc", "sum"), ych=("ych", "sum")).reset_index()
    nc["ty_no"] = nc["no_cuoc"] * 100 / nc["so_sr"]
    nc["ty_ych"] = nc["ych"] * 100 / nc["so_sr"]
    cot_nc = [ch.cot_chu("nhom_bc", "Nhóm chương trình", None), ch.cot_so("so_sr", "SR", 80), ch.cot_so("no_cuoc", "Hợp đồng nợ cước", 130), ch.cot_pct("ty_no", "% nợ cước", 100),
              ch.cot_so("ych", "Trong danh sách YCH", 150), ch.cot_pct("ty_ych", "% YCH", 90)]
    return html.Div([
        card([ch.bang_df("dvcd-diem", bac, cot)], title="Điểm nguy cơ rời mạng có đáng tin không?",
             desc="Điểm càng cao mà tỷ lệ khách đòi thanh lý không cao hơn thì điểm chưa giúp xếp ưu tiên. Chỉ SR đã có kết quả tư vấn mới xét."),
        html.Div(style={"height": "16px"}),
        html.Div([card([ch.cot_ngang(mk, "ly_do_mat_kn", "so", 220, mau=ch.CAM)], title="Lý do mất kết nối", desc="Cúp điện không cần CSKH gọi"),
                  card([ch.cot_ngang(nguon, "nguon_pp", "so", 220, mau=ch.XANH)], title="Nguồn phân phối SR", desc="SR do đơn vị nào đổ về")], className="dv-hai-cot"),
        html.Div(style={"height": "16px"}),
        card([ch.bang_df("dvcd-nc", nc, cot_nc)], title="Nợ cước và yêu cầu huỷ trên SR chủ động",
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
    return html.Div([ch.hang_kpi([("SR tồn", ch.so(len(t)), f"Tính tới SR mới nhất: {moc:%d/%m %H:%M}", ""),
                                  ("Ưu tiên rất cao còn tồn", ch.so(cao), "Xử lý trước", "bad" if cao else "ok"),
                                  ("Chưa phân công", ch.so(t["nguoi_xu_ly"].isna().sum()), "Chưa có người nhận", "warn")]),
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
