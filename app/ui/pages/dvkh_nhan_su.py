"""Trang Hiệu suất CSKH: một dòng mỗi người, gộp SR bị động và SR chủ động. Trả lời bốn câu: ai gánh bao nhiêu, ai đang nghẹt, ai làm tốt, ai giữ được khách.

Tải việc so trên số khách mỗi người phụ trách (bảng "Count of Acc NVVP" của file) để so công bằng: người phụ trách nhiều khách thì nhiều SR là bình thường.
"""
from __future__ import annotations

import plotly.graph_objects as go
from dash import Input, Output, dcc, html

from app.dvkh import khai_thac as kt, so_lieu as sl
from app.ui.components import card, chu_giai, seg_control
from app.ui.pages import dvkh_chung as ch, dvkh_ve as ve

SAP_XEP = [("tai", "Tải việc"), ("han", "% quá hạn"), ("ton", "Số SR tồn")]


def topbar():
    return [html.Div([html.H1("Hiệu suất CSKH"), html.Div("Ai gánh bao nhiêu việc, ai đang nghẹt, ai làm tốt (SR bị động + SR chủ động)", className="sub")])]


def layout():
    return html.Div([ch.thanh_loc("dvns", them=[html.Div([html.Label("Sắp xếp biểu đồ thanh"), seg_control("dvns-sx", SAP_XEP, "tai")], className="field")]),
                     dcc.Loading(html.Div(id="dvns-noi-dung"), type="dot")])


def _chuan_bi(phong):
    bd, cd = sl.loc(sl.sr_bi_dong(), ch.phong_ma(phong)), sl.loc(sl.sr_chu_dong(), ch.phong_ma(phong), cot_ngay="ngay_do")
    hs = sl.hieu_suat_nhan_su(bd, cd)
    if hs.empty:
        return bd, cd, hs
    hs = kt.cho_nao_tot_xau(kt.gan_so_khach(hs[hs["tong_tai"] > 0].copy(), sl.so_kh_au()))
    return bd, cd, hs


def _the_chi_so(hs, cd):
    tb = hs["tong_tai"].median()
    ro = hs[hs["tong_tai"] >= 30]
    cao, thap = ro.sort_values("tong_tai").iloc[-1], ro.sort_values("tong_tai").iloc[0]
    td = cd[cd["tu_dong"]]
    return ch.hang_kpi([
        ("Số CSKH có việc", ch.so(len(hs)), f"Không tính tài khoản máy gọi tự động ({ch.so(len(td))} SR)", ""),
        ("Tải trung vị", f"{ch.so(tb)} SR", f"Cao nhất {ch.so(cao['tong_tai'])} ({cao['nhan_su']}) · thấp nhất {ch.so(thap['tong_tai'])} ({thap['nhan_su']})", ""),
        ("% quá hạn trung vị", ch.pct(hs["ty_le_qua_han"].median()), "Trên tổng SR được giao cho mỗi người", ch.muc_theo_nguong(hs["ty_le_qua_han"].median(), 15, 30)),
        ("Cần hỗ trợ", ch.so((hs["nhan"] == "Cần hỗ trợ").sum()), "Nhiều việc hơn mức giữa và % quá hạn thuộc nhóm cao nhất", "bad" if (hs["nhan"] == "Cần hỗ trợ").any() else "ok"),
        ("Làm tốt", ch.so((hs["nhan"] == "Làm tốt").sum()), "Nhiều việc hơn mức giữa mà % quá hạn thuộc nhóm thấp nhất", "ok")])


def _sap_xep(hs, kieu):
    cot = {"tai": "tong_tai", "han": "ty_le_qua_han", "ton": "tong_ton"}[kieu]
    return hs.sort_values(cot, ascending=True)


def _tai_va_cong_bang(hs):
    """Cột SR trên 1.000 khách phụ trách (so công bằng) và hộp phân bố % quá hạn theo phòng."""
    co = hs.dropna(subset=["sr_1000kh"])
    trai = card([html.Div("Chưa có số khách mỗi CSKH phụ trách: nạp lại file Excel mới nhất (sheet BC SR bị động có bảng Count of Acc NVVP).", className="desc")],
                title="Tải việc trên số khách phụ trách")
    if len(co) >= 8:
        d = co.sort_values("sr_1000kh", ascending=False)
        f = go.Figure(go.Bar(x=d["nhan_su"], y=d["sr_1000kh"], marker_color=[ve.MAU_NHAN[n] if n else ch.XANH for n in d["nhan"]],
                             customdata=d[["so_kh", "tong_tai"]], hovertemplate="%{x}: %{y:.0f} SR/1.000 khách<br>%{customdata[1]:.0f} SR trên %{customdata[0]:,.0f} khách<extra></extra>"))
        f.add_hline(y=float(d["sr_1000kh"].median()), line_dash="dot", line_color=ch.XAM, annotation_text="trung vị", annotation_position="top right")
        f.update_xaxes(tickangle=-60)
        trai = card([ch.khung(f, 360, legend=False)], title="Tải việc trên số khách phụ trách",
                    desc=f"SR được giao trên mỗi 1.000 khách của người đó. Cao hơn nhiều so với trung vị ({ch.so(d['sr_1000kh'].median())}) là người đang gánh nặng so với quy mô của mình.")
    d = hs[hs["tong_tai"] >= 30]
    phai = card([_ket_luan_hop(d), ve.hop_theo_phong(d), _cach_doc_hop()], title="Mức đều tay giữa các CSKH",
                desc="So % quá hạn của từng người trong mỗi phòng. Chỉ tính người từ 30 SR trở lên (người ít SR thì tỷ lệ dễ lệch).")
    return html.Div([trai, phai], className="dv-hai-cot")


def _ket_luan_hop(d):
    """Mỗi phòng một câu: một nửa số người nằm trong khoảng nào, ai thấp nhất, ai cao nhất."""
    dong = []
    for p, g in d.dropna(subset=["ty_le_qua_han"]).groupby("phong"):
        q1, md, q3 = g["ty_le_qua_han"].quantile([.25, .5, .75])
        cao, thap = g.loc[g["ty_le_qua_han"].idxmax()], g.loc[g["ty_le_qua_han"].idxmin()]
        dong.append(html.Div([html.B(f"{p}: "), f"một nửa số CSKH có % quá hạn từ {q1:.0f}% đến {q3:.0f}% (người ở giữa {md:.0f}%). "
                                                 f"Thấp nhất {thap['nhan_su']} {thap['ty_le_qua_han']:.0f}%, cao nhất {cao['nhan_su']} {cao['ty_le_qua_han']:.0f}%."]))
    return html.Div(dong, className="dv-ket-luan")


def _cach_doc_hop():
    return chu_giai("Cách đọc biểu đồ này", [
        ("Mỗi chấm", "Một CSKH. Rê chuột lên chấm để xem tên và % quá hạn của người đó."),
        ("Hộp màu", "Chứa một nửa số CSKH ở giữa (từ phân vị 25 đến 75). Hộp càng thấp là cả phòng ít quá hạn; hộp càng hẹp là mọi người làm đều tay."),
        ("Vạch ngang trong hộp", "Người ở giữa phòng (trung vị): một nửa số người cao hơn, một nửa thấp hơn."),
        ("Vạch nét đứt", "Trung bình của phòng. Nếu nét đứt cao hơn vạch giữa thì có vài người quá hạn rất cao kéo trung bình lên."),
        ("Râu (đường thẳng nối ra ngoài)", "Người thấp nhất và cao nhất trong phạm vi bình thường. Chấm nằm ngoài râu là trường hợp bất thường, nên hỏi riêng."),
        ("So hai phòng", "Phòng nào có hộp thấp hơn thì ít quá hạn hơn; phòng nào hộp cao và dài thì có người làm tốt xen lẫn người rất chậm, cần cân lại việc.")])


def _nhom_nguoi(hs):
    def nhom(nhan, mau, mo_ta):
        d = hs[hs["nhan"] == nhan].sort_values("ty_le_qua_han", ascending=(nhan == "Làm tốt"))
        dong = [html.Div([html.B(r.nhan_su), html.Span(f"{ch.so(r.tong_tai)} SR · {ch.pct(r.ty_le_qua_han, 0)} quá hạn", className="dv-xh-ghi")], className="dv-nguoi")
                for r in d.itertuples()] or [html.Div("Không có ai", className="desc")]
        return html.Div([html.Div(nhan, className="dv-nhom-ten", style={"color": mau}), html.Div(mo_ta, className="desc"), *dong], className="dv-nhom")
    return html.Div([nhom("Cần hỗ trợ", ch.DO, "Nhiều việc và chậm: chia bớt việc hoặc kèm cặp"), nhom("Cần nhắc", ch.CAM, "Ít việc mà vẫn chậm: hỏi nguyên nhân"),
                     nhom("Làm tốt", ch.LUC, "Nhiều việc mà vẫn đúng hạn: học cách làm")], className="dv-ba-cot dv-nhom-luoi")


def _giu_chan(bd):
    g = kt.giu_chan_theo_nguoi(bd)
    if len(g) < 3:
        return None
    f = go.Figure(go.Bar(y=g["nhan_su"].iloc[::-1], x=g["ty_le_o_lai"].iloc[::-1], orientation="h", marker_color=ch.LUC,
                         text=[f"{v:.0f}% ({o}/{n})" for v, o, n in zip(g["ty_le_o_lai"].iloc[::-1], g["o_lai"].iloc[::-1], g["so_sr"].iloc[::-1])],
                         textposition="outside", cliponaxis=False, hovertemplate="%{y}: %{x:.0f}% khách đồng ý ở lại<extra></extra>"))
    f.update_xaxes(visible=False, range=[0, max(60, float(g["ty_le_o_lai"].max()) * 1.35)])
    return card([ch.khung(f, max(240, 30 * len(g) + 60), legend=False)], title="Giữ chân khách thanh lý",
                desc=f"Tỷ lệ khách đồng ý ở lại trên SR thanh lý đã tư vấn. Chỉ xếp người có từ {kt.MAU_NHAN_SU_TOI_THIEU} SR thanh lý; số trong ngoặc là ở lại / tổng SR.")


def _bang(hs):
    mau_han = {"styleConditions": [{"condition": "params.value >= 35", "style": {"color": "#B42318", "fontWeight": "650"}},
                                   {"condition": "params.value >= 20", "style": {"color": "#8A5709", "fontWeight": "650"}}]}
    nhan = {"styleConditions": [{"condition": "params.value == 'Cần hỗ trợ'", "style": {"color": "#B42318", "fontWeight": "650"}},
                                {"condition": "params.value == 'Cần nhắc'", "style": {"color": "#8A5709", "fontWeight": "650"}},
                                {"condition": "params.value == 'Làm tốt'", "style": {"color": "#0A5B31", "fontWeight": "650"}}]}
    cot = [ch.cot_chu("nhan_su", "CSKH", 140, pinned="left"), ch.cot_chu("phong", "Phòng", 80), ch.cot_so("so_kh", "Khách phụ trách", 130),
           ch.cot_so("tong_tai", "Tổng SR", 90), ch.cot_so1("sr_1000kh", "SR / 1.000 KH", 120), ch.cot_so("tong_ton", "Tồn", 80),
           ch.cot_pct("ty_le_qua_han", "% quá hạn", 100, cellStyle=mau_han), ch.cot_so("bd_phan_cong", "Bị động", 90), ch.cot_pct("bd_ty_le_xu_ly", "BĐ xử lý xong", 120),
           ch.cot_so1("bd_phan_hoi_p50", "BĐ phản hồi (phút)", 140), ch.cot_so("cd_phan_cong", "Chủ động", 100), ch.cot_pct("cd_ty_le_khong_lien_lac", "CĐ không LL", 110),
           ch.cot_so("cd_ton", "CĐ tồn", 80), ch.cot_chu("nhan", "Tín hiệu", 130, cellStyle=nhan)]
    return card([ch.bang_df("dvns-bang", hs.sort_values("tong_tai", ascending=False), cot, 520)], title="Bảng hiệu suất từng CSKH",
                desc="BĐ = SR bị động, CĐ = SR chủ động. SR tính cho Người xử lý như bảng BC của file. Khách phụ trách lấy từ bảng Count of Acc NVVP.")


def _cach_doc():
    return chu_giai("Cách đọc các nhãn", [
        ("Cần hỗ trợ", "Số SR từ mức trung vị trở lên và % quá hạn thuộc nhóm cao nhất (phân vị 75). Việc nhiều mà chậm: nên chia bớt hoặc kèm cặp."),
        ("Cần nhắc", "Ít việc hơn trung vị mà % quá hạn vẫn cao: hỏi nguyên nhân (nghỉ phép, kỹ năng, bỏ sót việc)."),
        ("Làm tốt", "Nhiều việc hơn trung vị mà % quá hạn thuộc nhóm thấp nhất (phân vị 25)."),
        ("Chưa gắn nhãn", "Người có dưới 30 SR hoặc nằm giữa các nhóm trên; tỷ lệ của mẫu nhỏ dễ lệch nên không gắn nhãn.")])


def register(app):
    @app.callback(Output("dvns-noi-dung", "children"), Input("dvns-phong", "value"), Input("dvns-sx", "value"))
    def _ve(phong, sx):
        bd, cd, hs = _chuan_bi(phong)
        if hs.empty:
            return html.Div("Chưa có số liệu nhân sự.", className="desc")
        dung_kh = hs["sr_1000kh"].notna().sum() >= 0.6 * len(hs)
        cot_x, ten_x = ("sr_1000kh", "SR được giao trên 1.000 khách phụ trách") if dung_kh else ("tong_tai", "Tổng SR được giao")
        gc = _giu_chan(bd)
        return html.Div([
            _the_chi_so(hs, cd),
            card([ve.tai_viec_xep_chong(_sap_xep(hs, sx or "tai"))], title="Ai đang gánh bao nhiêu việc",
                 desc="Mỗi thanh là một CSKH, chia theo tình trạng hạn xử lý. Xanh lá và vàng là đã xong; cam là chưa ai xử lý; đỏ là đang xử lý mà đã quá hạn. Đổi cách sắp xếp ở thanh trên."),
            html.Div(style={"height": "16px"}),
            _tai_va_cong_bang(hs),
            html.Div("Ai cần hỗ trợ, ai làm tốt", className="dv-tieu-nhom"),
            card([ve.goc_phan_tu(hs, cot_x, ten_x), _cach_doc()], title="Tải việc và quá hạn",
                 desc="Mỗi chấm là một người. Vùng đỏ nhạt (phải, trên) là việc nhiều và chậm; vùng xanh nhạt (phải, dưới) là việc nhiều mà vẫn đúng hạn. Chỉ ghi tên người cần chú ý và người làm tốt, còn lại rê chuột để xem."),
            html.Div(style={"height": "16px"}),
            _nhom_nguoi(hs),
            *([html.Div(style={"height": "16px"}), gc] if gc else []),
            html.Div("Bảng chi tiết", className="dv-tieu-nhom"),
            _bang(hs),
        ])
