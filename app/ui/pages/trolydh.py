"""Trang "Trợ lý điều hành" (`/trolydieuhanh`, chỉ BGĐ): sổ quyết định của trợ lý (rà soát -> nhận định -> đề xuất -> người quyết -> nhắc -> kiểm chứng).
Số liệu và vòng chạy ở `app/tro_ly_dieu_hanh*.py`; ở đây chỉ dựng giao diện. Toàn trang nằm sau công tắc `rules.yml` → `tro_ly_dieu_hanh.bat` (tắt thì không có menu, không mở được,
mọi callback trả rỗng). Mọi callback kiểm quyền ở máy chủ. Trợ lý chỉ ĐỀ XUẤT và ghi sổ; gửi Zalo chỉ khi quản trị tick ô "Gửi cho người quyết"."""
from __future__ import annotations

from dash import Input, Output, State, ctx, dcc, html
from dash.exceptions import PreventUpdate
from flask_login import current_user

from app import tro_ly_dieu_hanh as td, tro_ly_dieu_hanh_nd as nd, tro_ly_dieu_hanh_quet as q, tro_ly_dieu_hanh_so as so, tro_ly_dieu_hanh_zalo as tz
from app.thoi_gian import chu_gio_vn
from app.ui.components import alert, callback_can_quyen, card, kpi, tip
from app.ui.luoi import bang

QUYEN = "duoc_cau_hinh"
NHAN_CHI_SO = {"so_muc": "Số phát hiện", "so_cao": "Phát hiện mức cao", "so_trung_binh": "Phát hiện mức trung bình", "so_thap": "Phát hiện mức thấp", "so_nguoi": "Số người / đơn vị cần chú ý",
               "so_cao_nguoi": "Trong đó mức cao", "online": "Online luỹ kế", "cung_ky": "Cùng kỳ tháng trước", "muc_tieu": "Mục tiêu tháng", "luy_ke": "Luỹ kế", "du_bao": "Dự báo cuối tháng",
               "du_bao_nhip": "Dự báo (theo nhịp)", "hut": "Hụt so mục tiêu", "can_moi_ngay": "Cần mỗi ngày", "tb_ngay": "Bình quân mỗi ngày", "con_lai": "Số ngày còn lại", "danh_gia": "Đánh giá",
               "ton_qua_7": "HĐ chờ online từ 7 ngày", "ngay_tre": "Số ngày chậm", "qua_han": "Quá hạn", "ty_le_qua_han": "Tỷ lệ quá hạn (%)", "ton": "Tồn", "tai": "Tải việc",
               "roi_mang": "Khách rời mạng", "thang_truoc": "Tháng trước", "tang_pct": "Tăng (%)", "thu_bill": "Thu nợ theo hoá đơn (%)", "ky_truoc": "Kỳ trước (%)", "chenh_diem": "Chênh (điểm %)",
               "dat_pct": "Dự báo đạt mục tiêu (%)", "cung_ky_pct": "Cùng kỳ tháng trước (%)", "giam_pct": "Thấp hơn cùng kỳ (%)", "ngay_chua_co_so": "Số ngày chưa có số", "tuan_nay": "Tuần này", "tuan_truoc": "Tuần trước",
               "canh_bao": "Mức cảnh báo chung", "ky_no": "Kỳ nợ", "phong": "Phòng", "trung_vi_phong": "Trung vị phòng", "do_lech": "Độ lệch so đồng nghiệp"}
LY_DO_LUAT = {"chua_bat_ai": "AI chưa dùng được lúc đề xuất", "het_tran": "đã hết lượt gọi AI trong ngày", "loi_ai": "AI báo lỗi",
              "sai_dinh_dang_hoac_so": "câu AI viết sai khuôn hoặc có số không có trong bảng sự thật"}
NHAN_HANH_DONG = {"de_xuat": "Trợ lý đề xuất", "da_quyet": "Đã quyết", "bac": "Bác đề xuất", "qua_han": "Quá hạn quyết, đã báo cấp trên", "kiem_chung": "Kiểm chứng kết quả"}
NHAN_KHOI = {"kd": "Kinh doanh", "dvkh": "DVKH", "chung": "Chung"}
MAU_TT = {"styleConditions": [{"condition": "params.value == 'Đã kiểm chứng'", "style": {"color": "#0a5b31", "fontWeight": 600}},
                              {"condition": "params.value == 'Đã quyết'", "style": {"color": "#0072bc", "fontWeight": 600}},
                              {"condition": "params.value == 'Quá hạn quyết'", "style": {"color": "#b42318", "fontWeight": 600}},
                              {"condition": "params.value == 'Chờ quyết'", "style": {"color": "#b54708", "fontWeight": 600}},
                              {"condition": "params.value == 'Đã bác'", "style": {"color": "#667789"}}]}
COT = [
    {"headerName": "#", "field": "id", "width": 70, "pinned": "left"},
    {"headerName": "Vấn đề", "field": "tieu_de", "minWidth": 280, "flex": 2, "wrapText": True, "autoHeight": True},
    {"headerName": "Khối", "field": "khoi", "width": 110},
    {"headerName": "Người quyết", "field": "nguoi", "width": 170},
    {"headerName": "Mức", "field": "muc", "width": 100},
    {"headerName": "Trạng thái", "field": "trang_thai_ten", "width": 140, "cellStyle": MAU_TT},
    {"headerName": "Lựa chọn", "field": "lua_chon_ten", "minWidth": 200, "flex": 1, "wrapText": True, "autoHeight": True},
    {"headerName": "Hạn quyết", "field": "han_quyet", "width": 125},
    {"headerName": "Hạn kiểm chứng", "field": "han_kiem_chung", "width": 135},
    {"headerName": "Kết quả", "field": "ket_qua", "minWidth": 240, "flex": 2, "wrapText": True, "autoHeight": True},
    {"headerName": "Nội dung do", "field": "nguon", "width": 120},
]
COT_PHU = [{"headerName": "Nguồn quét", "field": "ten", "minWidth": 230, "flex": 1.3}, {"headerName": "Khối", "field": "khoi_ten", "width": 110},
           {"headerName": "Đơn vị", "field": "don_vi", "minWidth": 160, "flex": 1}, {"headerName": "Đã quét", "field": "da_quet", "width": 100, "type": "numericColumn"},
           {"headerName": "Tổng", "field": "tong", "width": 90, "type": "numericColumn"}, {"headerName": "Dữ liệu tới", "field": "du_lieu_luc", "minWidth": 170, "flex": 1},
           {"headerName": "Ghi chú", "field": "ghi_chu", "minWidth": 260, "flex": 2, "tooltipField": "ghi_chu"}, {"headerName": "Nguồn", "field": "co_nguon_ten", "width": 130}]


def topbar():
    return [html.Div([html.H1("Trợ lý điều hành"), html.Div("Rà soát toàn bộ số liệu, đề xuất phương án, chờ người quyết, nhắc và kiểm chứng kết quả", className="sub")])]


def _cho_phep() -> bool:
    return bool(getattr(current_user, QUYEN, False)) and so.bat()


def _lua_chon(r: dict) -> str:
    return tz.lua_chon_chu(r)


def dong_so(rows: list[dict], nguoi: dict) -> list[dict]:
    """Dòng của bảng sổ quyết định (mới nhất trước); `nguoi` = khoá người quyết -> tên hiển thị."""
    return [{"id": r["id"], "tieu_de": r["tieu_de"], "khoi": NHAN_KHOI.get(r["khoi"], r["khoi"]), "nguoi": nguoi.get(r["nguoi_quyet"], r["nguoi_quyet"]),
             "muc": {"cao": "Cao", "trung_binh": "Trung bình", "thap": "Thấp"}.get(r["su_that"].get("muc", ""), ""), "trang_thai_ten": so.TRANG_THAI.get(r["trang_thai"], r["trang_thai"]),
             "lua_chon_ten": _lua_chon(r), "han_quyet": chu_gio_vn(r["han_quyet"], "%d/%m %H:%M"), "han_kiem_chung": chu_gio_vn(r["han_kiem_chung"], "%d/%m %H:%M"),
             "ket_qua": r["ket_qua"] or "", "nguon": "AI viết" if r["nguon_noi_dung"] == "llm" else "Luật"} for r in rows]


def trang_thai_ai_hien():
    st = nd.trang_thai_ai()
    if st["dung_ai"]:
        return alert(f"AI đang BẬT: trợ lý nhờ AI viết nhận định và phương án, mọi số được kiểm với bảng sự thật, sai thì tự dùng bản luật. Hôm nay đã dùng {st['luot_hom_nay']} / {st['tran_ngay']} lượt gọi.", "ok")
    return alert(f"Đang dùng BẢN LUẬT (khuôn cố định, vẫn đầy đủ nhận định và phương án). Lý do: {st['ly_do']} Hôm nay đã dùng {st['luot_hom_nay']} / {st['tran_ngay']} lượt gọi AI.", "warn")


def _kpi() -> list:
    t = so.tom_tat()
    bad = "bad" if t["qua_han"] else ""
    return [kpi("Chờ quyết", t["cho_quyet"], f"{t['qua_han']} đề xuất quá hạn quyết", trang_thai=bad), kpi("Đã quyết", t["da_quyet"], "Đang chờ tới hạn đo lại"),
            kpi("Quá hạn quyết", t["qua_han"], "Đã báo cấp trên", trang_thai=bad), kpi("Đã kiểm chứng", t["da_kiem_chung"], f"{t['bac']} đề xuất bị bác")]


def chi_tiet(r: dict, nguoi: str) -> html.Div:
    """Nhận định, phương án, bằng chứng, chỉ số trước / sau, nhật ký và đường dẫn xem chi tiết của MỘT đề xuất."""
    s = r["su_that"]
    pa = [html.Li([html.B(f"{p['ma']}. {p['tieu_de']}"), html.B(" (khuyến nghị)", style={"color": "#0072bc"}) if p["ma"] == r["khuyen_nghi"] else "",
                   html.B(" (đã chọn)", style={"color": "#0a5b31"}) if p["ma"] == r["lua_chon"] else "", html.Div(p["mo_ta"], className="desc")]) for p in r["phuong_an"]]
    bc = html.Ul([html.Li(f"{NHAN_CHI_SO.get(k, k)}: {v}") for k, v in s.get("bang_chung", {}).items() if v is not None])
    cs, sau = r["chi_so_truoc"] or {}, r["chi_so_sau"] or {}
    do = html.Div(f"Chỉ số theo dõi: {cs.get('nhan', '')}. Lúc đề xuất {cs.get('gia_tri', '–')} {cs.get('don_vi', '')}" + (f"; đo lại {sau['gia_tri']} {cs.get('don_vi', '')}." if sau else "; chưa tới hạn đo lại."), className="desc")
    nk = html.Ul([html.Li(f"{chu_gio_vn(x['luc'], '%d/%m %H:%M')} · {'Trợ lý' if x['boi'] == 'tro_ly' else 'Hệ thống' if x['boi'] == 'he_thong' else x['boi']} · "
                          f"{NHAN_HANH_DONG.get(x['hanh_dong'], x['hanh_dong'])}" + (f" · {x['ghi_chu']}" if x["ghi_chu"] else "")) for x in so.nhat_ky(r["id"])])
    ly_do = [html.Div(f"Nội dung do bản luật viết vì: {LY_DO_LUAT.get(s['soan_luat_vi'], s['soan_luat_vi'])}.", className="desc")] if r["nguon_noi_dung"] == "luat" and s.get("soan_luat_vi") else []
    link = html.Div(["Xem chi tiết ở trang: ", dcc.Link(s["duong_dan"], href=s["duong_dan"])], className="desc") if s.get("duong_dan") else ""
    return card([html.Div(r["nhan_dinh"], style={"marginBottom": "10px"}), html.Div(f"Người quyết: {nguoi}", className="desc"), html.H4("Phương án"), html.Ul(pa),
                 html.H4("Bằng chứng (số do code lấy, không phải AI)"), bc, do, link, html.H4("Nhật ký"), nk, *ly_do], title=f"#{r['id']} · {r['tieu_de']}", desc="Chi tiết đề xuất đang chọn trong sổ.")


def _ds_nhan() -> list[dict]:
    """Người nhận Bản tin đang bật, để chọn "chỉ gửi thử cho". Lỗi đọc thì danh sách rỗng (trang vẫn mở)."""
    try:
        from app import ban_tin
        return [{"label": f"{n['ten']} ({'Ban Giám đốc' if n['loai'] == 'bgd' else 'Trưởng phòng' if n['loai'] == ban_tin.LOAI_TRUONG_PHONG else 'Admin'})", "value": n["chat_id"]}
                for n in ban_tin.ds_nguoi_nhan(chi_bat=True)]
    except Exception:
        return []


def layout():
    nut = lambda id_, chu, lop="btn primary": html.Button(chu, id=id_, n_clicks=0, className=lop)
    return html.Div([
        dcc.Store(id="tdh-tick", data=0),
        html.Div(id="tdh-ai", style={"marginBottom": "10px"}),
        card([dcc.Checklist(id="tdh-gui", options=[{"label": " Gửi cho người quyết qua Zalo (không tick thì chỉ ghi vào sổ, không gửi gì)", "value": "gui"}], value=[], className="zalo-tick"),
              html.Div([html.Div("Hoặc chỉ gửi thử cho một người (chọn tên mình):", className="desc"),
                        dcc.Dropdown(id="tdh-thu", options=_ds_nhan(), placeholder="Không chọn = theo ô tick ở trên", clearable=True, style={"maxWidth": "380px"}),
                        html.Div("Chọn người ở đây thì CHỈ người đó nhận tin (có nhãn GỬI THỬ), người quyết thật không nhận gì, và ô tick ở trên được bỏ qua.", className="desc")], style={"marginTop": "6px"}),
              html.Div([nut("tdh-sang", "Chạy trợ lý"), nut("tdh-kc", "Chạy kiểm chứng và nhắc", "btn")], style={"display": "flex", "gap": "10px", "margin": "10px 0", "flexWrap": "wrap"}),
              dcc.Loading(html.Div(id="tdh-thongbao"), type="dot")],
             title="Chạy trợ lý", desc="Chạy trợ lý: rà soát mọi nhân sự, phòng, khối rồi tạo đề xuất cho người quyết (không tạo trùng trong ngày). Chạy kiểm chứng và nhắc: nhắc người chưa quyết, báo cấp trên khi quá hạn, đo lại các quyết định tới hạn."),
        html.Div(id="tdh-kpi", className="kpi-row kpi-4"),
        card([bang("tdh-luoi", COT, cao=380, tuy_chon={"rowSelection": {"mode": "singleRow", "checkboxes": False, "enableClickSelection": True}})], title="Sổ quyết định",
             desc="Mỗi dòng là một đề xuất của trợ lý. Bấm một dòng để xem nhận định, phương án và bằng chứng. Người quyết trả lời qua Zalo: dong y SỐ A, sua SỐ ý kiến hoặc bac SỐ lý do."),
        html.Div(id="tdh-chi-tiet"),
        card([dcc.Loading(bang("tdh-phu", COT_PHU, cao=None), type="dot")], title="Sổ độ phủ", desc="Trợ lý đã quét bao nhiêu thực thể trên tổng của từng nguồn, và dữ liệu mới nhất tới ngày nào. Nguồn nào chưa có số cũng được nêu thành một phát hiện."),
        html.Div(["Công tắc ", html.Code("rules.yml → tro_ly_dieu_hanh.bat"), " đang BẬT. ", tip("Tắt công tắc này thì menu biến mất, trợ lý không chạy, không gửi Zalo, không nhận lệnh.")], className="desc"),
    ])


def _ghi(hanh_dong: str, chi_tiet_: str) -> None:
    try:
        from app.auth import ghi_log
        ghi_log(hanh_dong, chi_tiet_)
    except Exception:                                                     # nhật ký lỗi không được làm hỏng nút bấm
        pass


def _bam(ma: str, gui: bool, thu: str | None = None) -> str:
    """`thu` = chat_id được chọn "chỉ gửi thử": chỉ người đó nhận, sổ không đánh dấu đã gửi."""
    if thu:
        with tz.chi_gui_cho(thu) as kq:
            chu = _bam(ma, True)
        return f"{chu} [GỬI THỬ: đã gửi {kq['so_tin']} tin chỉ cho người bạn chọn" + (f", {kq['loi']} tin lỗi" if kq["loi"] else "") + "; người quyết thật chưa nhận gì.]"
    if ma == "tdh-sang":
        r = td.chay_buoi_sang(gui=gui)
        _ghi("tro_ly_dieu_hanh_chay", f"moi={r['moi']} gui={r['gui']} ai={r['ai']} gui_zalo={gui}")
        con = f" Còn {r['bo_qua_trung_binh']} vấn đề mức trung bình chưa đề xuất (vượt trần mỗi lần)." if r["bo_qua_trung_binh"] else ""
        loi = f" Nguồn dữ liệu lỗi: {', '.join(sorted(r['loi_nguon']))}." if r["loi_nguon"] else ""
        return (f"Trợ lý đã đề xuất {r['moi']} vấn đề mới ({r['ai']} do AI viết, {r['luat']} bằng bản luật), {r['da_co']} vấn đề đã có từ trước, gửi {r['gui']} tin tới người quyết." + con + loi
                + (" Hôm nay không có vấn đề mới." if not r["moi"] else ""))
    n, k = td.nhac_quyet(gui=gui), td.kiem_chung(gui=gui)
    _ghi("tro_ly_dieu_hanh_kiem_chung", f"nhac={n['nhac']} leo={n['bao_cap_tren']} kc={k['kiem_chung']} gui_zalo={gui}")
    return f"Đã nhắc {n['nhac']} đề xuất chưa quyết, báo cấp trên {n['bao_cap_tren']} đề xuất quá hạn, kiểm chứng {k['kiem_chung']} quyết định (báo kết quả {k['da_bao']} lần)."


def cb_chay(_a, _b, gui, thu, tick):
    """Nút "Chạy trợ lý" / "Chạy kiểm chứng và nhắc". Gửi Zalo chỉ khi ô tick được chọn."""
    if not _cho_phep() or ctx.triggered_id not in ("tdh-sang", "tdh-kc") or not ctx.triggered[0]["value"]:
        raise PreventUpdate
    try:
        if thu and thu not in {n["value"] for n in _ds_nhan()}:
            return alert("Người nhận đã chọn không còn trong danh sách Bản tin Zalo (hoặc đã bị tắt). Chọn lại tên.", "bad"), tick or 0
        tb = alert(_bam(ctx.triggered_id, "gui" in (gui or []), thu or None), "info")
    except Exception as e:                                           # lỗi nguồn dữ liệu không được làm trang đứng
        tb = alert(f"Chưa chạy được ({type(e).__name__}). Xem lại dữ liệu rồi thử lại.", "bad")
    return tb, (tick or 0) + 1


def cb_ve(_tick):
    if not _cho_phep():
        raise PreventUpdate
    rows = so.liet_ke()
    nguoi = {k: td.ten_nguoi_quyet(k) for k in {r["nguoi_quyet"] for r in rows}}
    return trang_thai_ai_hien(), _kpi(), dong_so(rows, nguoi)


def cb_phu(_tick):
    if not _cho_phep():
        raise PreventUpdate
    return [{**x, "khoi_ten": NHAN_KHOI.get(x["khoi"], x["khoi"]), "co_nguon_ten": "Đã nối" if x["co_nguon"] else "Chưa đọc được"} for x in q.so_do_phu()]


def cb_chon(chon):
    if not chon or not _cho_phep():
        return ""
    r = so.doc(int(chon[0]["id"]))
    return "" if r is None else chi_tiet(r, td.ten_nguoi_quyet(r["nguoi_quyet"]))


def register(app):
    """Callback nào cũng kiểm `duoc_cau_hinh` ở máy chủ (`callback_can_quyen`) và công tắc `bat` (`_cho_phep`)."""
    cb = callback_can_quyen(app, QUYEN)
    cb(Output("tdh-thongbao", "children"), Output("tdh-tick", "data"), Input("tdh-sang", "n_clicks"), Input("tdh-kc", "n_clicks"), State("tdh-gui", "value"), State("tdh-thu", "value"), State("tdh-tick", "data"),
       prevent_initial_call=True, running=[(Output("tdh-sang", "disabled"), True, False), (Output("tdh-kc", "disabled"), True, False)])(cb_chay)
    cb(Output("tdh-ai", "children"), Output("tdh-kpi", "children"), Output("tdh-luoi", "rowData"), Input("tdh-tick", "data"))(cb_ve)
    cb(Output("tdh-phu", "rowData"), Input("tdh-tick", "data"))(cb_phu)
    cb(Output("tdh-chi-tiet", "children"), Input("tdh-luoi", "selectedRows"))(cb_chon)
