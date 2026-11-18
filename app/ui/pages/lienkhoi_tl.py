"""Tab "Trợ lý điều hành" của trang Điều hành liên khối (nhánh thi-lien-khoi): sổ quyết định của trợ lý (quan sát -> nhận định -> đề xuất -> người quyết -> kiểm chứng).
Số liệu và vòng chạy ở `app/lien_khoi/tro_ly_dieu_hanh.py`, lưu ở `quyet_dinh.py`; ở đây chỉ dựng giao diện. Chỉ Quản trị; mọi callback kiểm quyền ở máy chủ.
Trợ lý chỉ ĐỀ XUẤT: người có quyền chọn phương án (trên Zalo hoặc nhắn bot), trợ lý không tự giao việc."""
from __future__ import annotations

from dash import Input, Output, State, ctx, dcc, html
from dash.exceptions import PreventUpdate

from app.lien_khoi import luat, quyet_dinh as qd, theo_doi as td, tro_ly_dieu_hanh as tdh
from app.ui.components import alert, callback_can_quyen, card, kpi
from app.ui.luoi import bang

QUYEN = "duoc_cau_hinh"
NHAN_MUC = {"cao": "Cao", "trung_binh": "Trung bình", "thap": "Thấp"}
NHAN_CHI_SO = {"qua_han": "Việc quá hạn", "dang_mo": "Việc đang mở", "ty_le_qua_han": "Tỷ lệ quá hạn (%)", "chua_giao": "Chưa giao cho ai", "muc_cao": "Việc mức Cao", "hang_cho": "Việc hàng chờ chưa giao",
               "qua_han_muc_cao": "Mức Cao đã quá hạn", "chua_giao_muc_cao": "Mức Cao chưa giao", "so_muc": "Số mục phát hiện", "so_cao": "Mục mức cao", "so_trung_binh": "Mục mức trung bình",
               "so_thap": "Mục mức thấp", "gio_im_lang": "Giờ im lặng (nặng nhất)", "ngay_ton": "Ngày tồn (nặng nhất)", "nguong_gio": "Ngưỡng im lặng (giờ)"}
LY_DO_LUAT = {"chua_bat_ai": "AI chưa dùng được lúc đề xuất", "het_tran": "đã hết lượt gọi AI trong ngày", "loi_ai": "AI báo lỗi", "sai_dinh_dang_hoac_so": "câu AI viết sai khuôn hoặc có số không có trong bảng sự thật"}
NHAN_HANH_DONG = {"de_xuat": "Trợ lý đề xuất", "da_quyet": "Đã quyết", "bac": "Bác đề xuất", "qua_han": "Quá hạn quyết, đã báo cấp trên", "kiem_chung": "Kiểm chứng kết quả"}
MAU_TT = {"styleConditions": [{"condition": "params.value == 'Đã kiểm chứng'", "style": {"color": "#0a5b31", "fontWeight": 600}},
                              {"condition": "params.value == 'Đã quyết'", "style": {"color": "#0072bc", "fontWeight": 600}},
                              {"condition": "params.value == 'Quá hạn quyết'", "style": {"color": "#b42318", "fontWeight": 600}},
                              {"condition": "params.value == 'Chờ quyết'", "style": {"color": "#b54708", "fontWeight": 600}},
                              {"condition": "params.value == 'Đã bác'", "style": {"color": "#667789"}}]}
COT = [
    {"headerName": "#", "field": "id", "width": 70, "pinned": "left"},
    {"headerName": "Vấn đề", "field": "tieu_de", "minWidth": 280, "flex": 2, "wrapText": True, "autoHeight": True},
    {"headerName": "Khối", "field": "khoi", "width": 90},
    {"headerName": "Người quyết", "field": "nguoi", "width": 160},
    {"headerName": "Mức", "field": "muc", "width": 100},
    {"headerName": "Trạng thái", "field": "trang_thai_ten", "width": 140, "cellStyle": MAU_TT},
    {"headerName": "Lựa chọn", "field": "lua_chon_ten", "minWidth": 200, "flex": 1, "wrapText": True, "autoHeight": True},
    {"headerName": "Hạn quyết", "field": "han_quyet", "width": 120},
    {"headerName": "Hạn kiểm chứng", "field": "han_kiem_chung", "width": 130},
    {"headerName": "Kết quả", "field": "ket_qua", "minWidth": 240, "flex": 2, "wrapText": True, "autoHeight": True},
    {"headerName": "Nội dung do", "field": "nguon", "width": 120},
]
COT_PHU = [{"headerName": "Nguồn quét", "field": "ten", "minWidth": 220, "flex": 1}, {"headerName": "Đơn vị", "field": "don_vi", "width": 180},
           {"headerName": "Đã quét", "field": "da_quet", "width": 110, "type": "numericColumn"}, {"headerName": "Tổng", "field": "tong", "width": 100, "type": "numericColumn"},
           {"headerName": "Nguồn dữ liệu", "field": "co_nguon_ten", "width": 150}]


def _ten_nguoi(ma: str, ten: dict) -> str:
    return ten.get(ma, ma)


def _lua_chon(r: dict) -> str:
    if r["lua_chon"] == qd.LUA_CHON_SUA:
        return "Sửa ý: " + (r["ghi_chu"] or "")
    pa = {p["ma"]: p for p in r["phuong_an"]}
    if r["lua_chon"] in pa:
        return f"{r['lua_chon']} - {pa[r['lua_chon']]['tieu_de']}"
    return ("Bác: " + (r["ghi_chu"] or "")) if r["trang_thai"] == "bac" else ""


def dong_so(rows: list[dict], ten: dict) -> list[dict]:
    """Dòng của bảng sổ quyết định (mới nhất trước)."""
    return [{"id": r["id"], "tieu_de": r["tieu_de"], "khoi": r["khoi"], "nguoi": _ten_nguoi(r["nguoi_quyet"], ten), "muc": NHAN_MUC.get(r["su_that"].get("muc", ""), ""),
             "trang_thai_ten": qd.TRANG_THAI.get(r["trang_thai"], r["trang_thai"]), "lua_chon_ten": _lua_chon(r), "han_quyet": tdh._vn(r["han_quyet"]),
             "han_kiem_chung": tdh._vn(r["han_kiem_chung"]), "ket_qua": r["ket_qua"] or "", "nguon": "AI viết" if r["nguon_noi_dung"] == "llm" else "Luật"} for r in rows]


def trang_thai_ai_hien():
    st = tdh.trang_thai_ai()
    if st["dung_ai"]:
        return alert(f"AI đang BẬT: trợ lý nhờ AI viết nhận định và phương án, mọi số được kiểm với bảng sự thật, sai thì tự dùng bản luật. Hôm nay đã dùng {st['luot_hom_nay']} / {st['tran_ngay']} lượt gọi.", "ok")
    return alert(f"Đang dùng BẢN LUẬT (khuôn cố định, vẫn đầy đủ nhận định và phương án). Lý do: {st['ly_do']} Hôm nay đã dùng {st['luot_hom_nay']} / {st['tran_ngay']} lượt gọi AI.", "warn")


def _kpi(rows: list[dict]) -> list:
    t = qd.tom_tat()
    return [kpi("Chờ quyết", t["cho_quyet"], f"{t['qua_han']} đề xuất quá hạn quyết", trang_thai="bad" if t["qua_han"] else ""), kpi("Đã quyết", t["da_quyet"], "Đang chờ tới hạn đo lại"),
            kpi("Quá hạn quyết", t["qua_han"], "Đã báo cấp trên", trang_thai="bad" if t["qua_han"] else ""), kpi("Đã kiểm chứng", t["da_kiem_chung"], f"{t['bac']} đề xuất bị bác")]


def chi_tiet(r: dict, ten: dict) -> html.Div:
    """Nhận định, phương án, bằng chứng, chỉ số trước / sau và nhật ký của MỘT đề xuất."""
    s = r["su_that"]
    pa = [html.Li([html.B(f"{p['ma']}. {p['tieu_de']}"), (html.B(" (khuyến nghị)", style={"color": "#0072bc"}) if p["ma"] == r["khuyen_nghi"] else ""),
                   (html.B(" (đã chọn)", style={"color": "#0a5b31"}) if p["ma"] == r["lua_chon"] else ""), html.Div(p["mo_ta"], className="lk-ghi-chu")]) for p in r["phuong_an"]]
    bc = html.Ul([html.Li(f"{NHAN_CHI_SO.get(k, k)}: {v}") for k, v in s.get("bang_chung", {}).items()], className="lk-nhan-dinh")
    cs, sau = r["chi_so_truoc"] or {}, r["chi_so_sau"] or {}
    do = [html.Div(f"Chỉ số theo dõi: {tdh._hien(cs.get('nhan', ''), ten)}. Lúc đề xuất {cs.get('gia_tri', '–')} {cs.get('don_vi', '')}"
                   + (f"; đo lại {sau['gia_tri']} {cs.get('don_vi', '')}." if sau else "; chưa tới hạn đo lại."), className="lk-ghi-chu")]
    nk = qd.nhat_ky(r["id"])
    nhat_ky = html.Ul([html.Li(f"{tdh._vn(x['luc'])} · {'Trợ lý' if x['boi'] == 'tro_ly' else 'Hệ thống' if x['boi'] == 'he_thong' else _ten_nguoi(x['boi'], ten)} · {NHAN_HANH_DONG.get(x['hanh_dong'], x['hanh_dong'])}" + (f" · {x['ghi_chu']}" if x["ghi_chu"] else "")) for x in nk.to_dict("records")], className="lk-nhan-dinh")
    return card([
        html.Div(r["nhan_dinh"], style={"marginBottom": "10px"}), html.Div("Phương án", className="lk-nhan"), html.Ul(pa, className="lk-nhan-dinh"),
        html.Div("Bằng chứng (số do code lấy, không phải AI)", className="lk-nhan", style={"marginTop": "10px"}), bc, *do,
        html.Div(["Xem chi tiết: ", html.A(s.get("duong_dan", ""), href=s.get("duong_dan", ""), target="_blank")], className="lk-ghi-chu", style={"marginTop": "6px"}) if s.get("duong_dan") else "",
        html.Div("Nhật ký", className="lk-nhan", style={"marginTop": "10px"}), nhat_ky,
        *([html.Div(f"Nội dung do bản luật viết vì: {LY_DO_LUAT.get(s['soan_luat_vi'], s['soan_luat_vi'])}.", className="lk-ghi-chu")] if r["nguon_noi_dung"] == "luat" and s.get("soan_luat_vi") else []),
    ], title=f"#{r['id']} · {r['tieu_de']}", desc="Chi tiết đề xuất đang chọn trong sổ.")


def layout():
    nut = lambda id_, chu, lop="btn primary": html.Button(chu, id=id_, n_clicks=0, className=lop)
    return html.Div([
        dcc.Store(id="lk-tl-tick", data=0),
        html.Div(id="lk-tl-ai", style={"marginBottom": "10px"}),
        card([html.Div([nut("lk-tl-sang", "Chạy trợ lý buổi sáng"), nut("lk-tl-kc", "Chạy kiểm chứng")], className="lk-badges"), html.Div(id="lk-tl-thongbao", style={"marginTop": "10px"})],
             title="Chạy trợ lý", desc="Buổi sáng: quét số liệu, đề xuất cho người quyết rồi gửi qua Zalo (không tạo trùng trong ngày). Kiểm chứng: nhắc người chưa quyết, báo cấp trên khi quá hạn, đo lại các quyết định tới hạn. Ở bản minh hoạ, lùi đồng hồ ở tab Theo dõi & Zalo để thử."),
        html.Div(id="lk-tl-kpi", className="kpi-row kpi-6"),
        card([bang("lk-tl-luoi", COT, cao=380, tuy_chon={"rowSelection": {"mode": "singleRow", "checkboxes": False, "enableClickSelection": True}})],
             title="Sổ quyết định", desc="Mỗi dòng là một đề xuất của trợ lý. Bấm một dòng để xem nhận định, phương án và bằng chứng. Người quyết trả lời qua Zalo: dong y SỐ A, sua SỐ ý kiến hoặc bac SỐ lý do."),
        html.Div(id="lk-tl-chi-tiet"),
        card([bang("lk-tl-phu", COT_PHU, cao=None)], title="Phạm vi quét", desc="Trợ lý đã nhìn được bao nhiêu thực thể trên tổng của từng nguồn. Thêm nguồn mới (Kinh doanh, DVKH, Kỹ thuật) không phải sửa lõi."),
    ])


def _ghi_nhat_ky(hanh_dong: str, chi_tiet_: str) -> None:
    try:
        from app.auth import ghi_log
        ghi_log(hanh_dong, chi_tiet_)
    except Exception:                                                     # nhật ký của app lỗi không được làm hỏng nút bấm
        pass


def _bam(ma: str) -> str:
    if ma == "lk-tl-sang":
        td.dong_bo(luat.danh_sach_viec())
        r = tdh.chay_buoi_sang()
        _ghi_nhat_ky("tro_ly_dieu_hanh_sang", f"moi={r['moi']} gui={r['gui']} ai={r['ai']}")
        return (f"Trợ lý đã đề xuất {r['moi']} vấn đề mới ({r['ai']} do AI viết, {r['luat']} bằng bản luật) và gửi {r['gui']} tin tới người quyết."
                + (" Hôm nay không có vấn đề mới." if not r["moi"] else ""))
    n, k = tdh.nhac_quyet(), tdh.kiem_chung()
    _ghi_nhat_ky("tro_ly_dieu_hanh_kiem_chung", f"nhac={n['nhac']} leo={n['bao_cap_tren']} kc={k['kiem_chung']}")
    return (f"Đã nhắc {n['nhac']} đề xuất chưa quyết, báo cấp trên {n['bao_cap_tren']} đề xuất quá hạn, kiểm chứng {k['kiem_chung']} quyết định (báo kết quả {k['da_bao']} lần).")


def register(app):
    cb = callback_can_quyen(app, QUYEN)

    @cb(Output("lk-tl-thongbao", "children"), Output("lk-tl-tick", "data"), Input("lk-tl-sang", "n_clicks"), Input("lk-tl-kc", "n_clicks"), State("lk-tl-tick", "data"), prevent_initial_call=True)
    def _chay(_a, _b, tick):
        if ctx.triggered_id not in ("lk-tl-sang", "lk-tl-kc") or not ctx.triggered[0]["value"]:
            raise PreventUpdate
        try:
            tb = alert(_bam(ctx.triggered_id), "info")
        except RuntimeError as e:
            tb = alert(str(e), "bad")
        return tb, (tick or 0) + 1

    @cb(Output("lk-tl-ai", "children"), Output("lk-tl-kpi", "children"), Output("lk-tl-luoi", "rowData"), Output("lk-tl-phu", "rowData"),
        Input("lk-tab", "value"), Input("lk-tl-tick", "data"), Input("lk-td-tick", "data"))
    def _ve(tab, _t1, _t2):
        if tab != "tl":
            raise PreventUpdate
        rows = qd.liet_ke()
        ten = dict(zip(td.nguoi_nhan().fillna("")["ma"], td.nguoi_nhan().fillna("")["ten"]))
        phu = [{**x, "co_nguon_ten": "Đã nối" if x["co_nguon"] else "Chưa có nguồn"} for x in tdh.so_do_phu()]
        return trang_thai_ai_hien(), _kpi(rows), dong_so(rows, ten), phu

    @cb(Output("lk-tl-chi-tiet", "children"), Input("lk-tl-luoi", "selectedRows"))
    def _chon(chon):
        if not chon:
            return ""
        r = qd.doc(int(chon[0]["id"]))
        if r is None:
            return ""
        ds = td.nguoi_nhan().fillna("")
        return chi_tiet(r, dict(zip(ds["ma"], ds["ten"])))
