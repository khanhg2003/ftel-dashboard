"""Tab "Theo dõi & Zalo" của trang Điều hành liên khối (nhánh thi-lien-khoi): đồng bộ việc từ các luật, gửi qua Zalo, nhắc quá hạn,
báo quản lý, cập nhật trạng thái từng phần việc, hộp thư Zalo. Chạy minh hoạ thì mọi tin chỉ được GIẢ LẬP (không gửi ra ngoài).
Logic ở `app/lien_khoi/theo_doi.py` và `zalo_viec.py`; ở đây chỉ dựng giao diện và gọi hàm. Chỉ Quản trị; mọi callback kiểm quyền ở máy chủ."""
from __future__ import annotations

import pandas as pd

from dash import Input, Output, State, ctx, dcc, html
from dash.exceptions import PreventUpdate

from app.lien_khoi import dieu_phoi as dp, luat, mo_phong as mp, nguon, theo_doi as td, zalo_viec as zv
from app.ui.components import alert, callback_can_quyen, card, kpi
from app.ui.luoi import bang

QUYEN = "duoc_cau_hinh"
NHAN_KENH = {"gia_lap": "GIẢ LẬP: tin chỉ ghi vào hộp thư bên dưới, không gửi ra ngoài.",
             "zalo_thu": "THỬ ZALO: dữ liệu MINH HOẠ nhưng tin của 4 quản lý đại diện (KD, DVKH, Kỹ thuật, Ban giám đốc) được gửi THẬT tới người thử đã đăng ký; tin của các quản lý khác chỉ ghi vào hộp thư.", "zalo": "ĐANG GỬI THẬT qua bot Zalo riêng của hướng liên khối.",
             "chua_cau_hinh": "Chưa cấu hình bot Zalo (LIEN_KHOI_ZALO_TOKEN và LIEN_KHOI_ZALO_GUI=1): tin chỉ được ghi vào hộp thư, chưa gửi."}
MAU_TT = {"styleConditions": [{"condition": "params.value == 'Đã xong'", "style": {"color": "#0a5b31", "fontWeight": 600}},
                              {"condition": "params.value == 'Không làm được'", "style": {"color": "#b42318", "fontWeight": 600}},
                              {"condition": "params.value == 'Đã nhận'", "style": {"color": "#b54708", "fontWeight": 600}},
                              {"condition": "params.value == 'Hết dấu hiệu'", "style": {"color": "#667789"}}]}
COT_TD = [
    {"headerName": "Mã HĐ", "field": "so_hd", "width": 115, "pinned": "left"},
    {"headerName": "Luật", "field": "ten_luat", "width": 140},
    {"headerName": "Mức", "field": "muc", "width": 95, "cellStyle": {"styleConditions": [{"condition": "params.value == 'Cao'", "style": {"color": "#b42318", "fontWeight": 600}}]}},
    {"headerName": "Vai trò", "field": "vai_tro_ten", "width": 100},
    {"headerName": "Nhân viên / hàng chờ", "field": "nguoi", "width": 150},
    {"headerName": "Quản lý nhận tin", "field": "quan_ly", "width": 140},
    {"headerName": "Đã giao cho", "field": "giao_cho", "width": 130},
    {"headerName": "Trạng thái", "field": "trang_thai_ten", "width": 130, "cellStyle": MAU_TT},
    {"headerName": "Giao lúc", "field": "tao_luc", "width": 120},
    {"headerName": "Hạn", "field": "han", "width": 120},
    {"headerName": "Còn lại", "field": "con_lai", "width": 120, "cellStyle": {"styleConditions": [{"condition": "String(params.value).indexOf('Quá') === 0",
                                                                                                    "style": {"color": "#b42318", "fontWeight": 600}}]}},
    {"headerName": "Đã gửi", "field": "da_gui", "width": 105},
    {"headerName": "Nhắc", "field": "nhac", "width": 105},
    {"headerName": "Báo QL", "field": "bao_ql", "width": 105},
    {"headerName": "Nguồn", "field": "nguon", "width": 100},
    {"headerName": "Ghi chú", "field": "ghi_chu", "minWidth": 200, "flex": 1, "wrapText": True, "autoHeight": True},
]
COT_THU = [
    {"headerName": "Lúc", "field": "luc", "width": 115}, {"headerName": "Người", "field": "den_nguoi", "width": 150},
    {"headerName": "Loại", "field": "loai_ten", "width": 140}, {"headerName": "Kết quả", "field": "ket_qua", "width": 120},
    {"headerName": "Nội dung tin", "field": "noi_dung", "minWidth": 420, "flex": 1, "wrapText": True, "autoHeight": True},
]
TEN_LOAI_TIN = {"giao": "Giao việc", "nhac": "Nhắc quá hạn", "quan_ly": "Báo quản lý", "phan_hoi": "Phản hồi của bot", "nhan_tu_nguoi": "Người trả lời", "tong_ket": "Tổng kết",
                 "quyet_dinh": "Đề xuất cần quyết", "nhac_quyet": "Nhắc quyết định", "leo_thang": "Báo cấp trên (quá hạn quyết)", "kiem_chung": "Kết quả sau quyết định"}
TEN_HANH_DONG = {"giao": "Hệ thống tạo việc", "giao_cho": "Quản lý giao cho nhân viên", "mo_lai": "Dấu hiệu quay lại", "tu_het": "Hết dấu hiệu"}
LOC = [("mo", "Đang mở"), ("qua_han", "Quá hạn"), ("da_xong", "Đã xong"), ("khong_lam_duoc", "Không làm được"), ("tu_het", "Hết dấu hiệu"), ("all", "Tất cả")]


def _vn(t) -> str:
    return "" if t is None or pd.isna(t) else (pd.Timestamp(t) + pd.Timedelta(hours=7)).strftime("%d/%m %H:%M")


def _con_lai(r) -> str:
    if not r["dang_mo"]:
        return ""
    g = abs(r["con_lai_gio"])
    return f"Quá {g:.0f} giờ" if r["con_lai_gio"] < 0 else f"Còn {g:.0f} giờ"


def _dong(d: pd.DataFrame) -> list[dict]:
    out = d.copy()
    out["vai_tro_ten"] = out["vai_tro"].map(td.VAI_TRO)
    out["trang_thai_ten"] = out["trang_thai"].map(td.TRANG_THAI)
    out["con_lai"] = out.apply(_con_lai, axis=1)
    for c, moi in (("tao_luc", "tao_luc"), ("han_luc", "han")):
        out[moi] = out[c].map(_vn)
    for c, moi in (("da_gui_luc", "da_gui"), ("nhac_luc", "nhac"), ("bao_quan_ly_luc", "bao_ql")):
        out[moi] = out[c].map(_vn)
    out["ghi_chu"] = out["ghi_chu"].fillna("")
    out["giao_cho"] = out["giao_cho"].fillna("") if "giao_cho" in out.columns else ""
    out["nguon"] = out["mo_phong"].fillna(0).astype(int).map({1: "Mô phỏng", 0: "Thật"})
    return out.drop(columns=["han_luc", "da_gui_luc", "nhac_luc", "bao_quan_ly_luc"]).to_dict("records")


def _ds_quan_ly() -> list[dict]:
    ds = td.nguoi_nhan().fillna("")
    ql = ds[ds["vai_tro"].isin(td.VAI_TRO_QUAN_LY) & (ds["vai_tro"] != "giam_doc")]
    return [{"label": "Tất cả (giám đốc chi nhánh xem)", "value": "all"}] + [{"label": f"{r['ten']} ({r['ma']})", "value": r["ma"]} for r in ql.to_dict("records")]


def layout(ql: str | None = None):
    nut = lambda id_, chu, lop="btn": html.Button(chu, id=id_, n_clicks=0, className=lop)
    gia_lap = nguon.la_demo()
    return html.Div([
        dcc.Store(id="lk-td-tick", data=0),
        html.Div(id="lk-td-kenh"),
        card([
            html.Div([nut("lk-td-dongbo", "1. Lấy việc từ các luật", "btn primary"), nut("lk-td-gui", "2. Gửi việc mới qua Zalo", "btn primary"),
                      nut("lk-td-nhac", "3. Chạy nhắc & báo quản lý", "btn primary"),
                      *([nut("lk-td-lui1", "Lùi đồng hồ +25 giờ"), nut("lk-td-lui2", "Lùi đồng hồ +49 giờ"), nut("lk-td-reset", "Làm lại từ đầu"),
                         nut("lk-td-chuan-bi", "Chuẩn bị demo (nạp 14 ngày mô phỏng)")] if gia_lap else [])],
                     className="lk-badges"),
            html.Div(id="lk-td-dong-ho", className="lk-ghi-chu", style={"marginTop": "8px"}),
            html.Div(id="lk-td-thongbao", style={"marginTop": "10px"}),
        ], title="Giao việc", desc="Bước 1 đưa việc từ các luật vào bảng theo dõi (việc cũ giữ nguyên trạng thái). Bước 2 gửi cho từng QUẢN LÝ một tin tổng hợp việc của team (nhân viên không nhận tin). Bước 3 nhắc việc quá 24 giờ và báo quản lý khi quá 48 giờ."),
        html.Div(id="lk-td-kpi", className="kpi-row kpi-6"),
        card([
            html.Div([html.Label("Tôi là", style={"marginRight": "8px"}), dcc.Dropdown(id="lk-td-ql", options=_ds_quan_ly(), value=ql if ql in {o["value"] for o in _ds_quan_ly()} else "all", clearable=False, style={"width": "340px"}),
                      html.Label("Xem", style={"margin": "0 8px 0 18px"}), dcc.Dropdown(id="lk-td-loc", options=[{"label": t, "value": k} for k, t in LOC], value="mo",
                                                                                         clearable=False, style={"width": "200px"})],
                     style={"display": "flex", "alignItems": "center", "marginBottom": "10px"}),
            bang("lk-td-luoi", COT_TD, cao=420, tuy_chon={"rowSelection": {"mode": "multiRow", "checkboxes": False, "headerCheckbox": False, "enableClickSelection": True}}),
            html.Div([html.A("Xuất Excel", id="lk-td-xlsx", href="/lien-khoi/xuat.xlsx", className="btn primary", style={"textDecoration": "none"}),
                      html.Span("Cả danh sách đang xem (theo ô Tôi là và ô Xem), gồm một sheet riêng cho từng nhân viên để gửi thẳng cho họ.", className="lk-ghi-chu")],
                     className="lk-badges", style={"marginBottom": "10px"}),
            html.Div([dcc.Dropdown(id="lk-td-giao-cho", placeholder="Giao cho (chọn người của team)", style={"width": "300px"}), nut("lk-td-giao", "Giao các việc đã chọn", "btn primary"), nut("lk-td-chia-deu", "Chia đều việc hàng chờ"),
                      nut("lk-td-xong", "Đã xong"), nut("lk-td-khong", "Không làm được"),
                      dcc.Input(id="lk-td-lydo", type="text", className="inp", placeholder="Lý do (bắt buộc khi không làm được)", style={"width": "280px"})],
                     className="lk-badges", style={"marginTop": "10px"}),
            html.Div(id="lk-td-chon", className="lk-ghi-chu", style={"marginTop": "6px"}),
            html.Div("Chọn nhiều dòng (giữ Ctrl hoặc Shift, hoặc bấm từng dòng), chọn người rồi bấm Giao một lần. Quản lý làm việc này trên app, không phải trả lời từng mã trên Zalo. Nút Chia đều việc hàng chờ tự giao các việc chưa có người phụ trách cho nhân viên đúng khối, ai đang ít việc nhất nhận trước.",
                     className="lk-ghi-chu", style={"marginTop": "6px"}),
            html.Div(id="lk-td-nhat-ky", style={"marginTop": "10px"}),
        ], title="Trạng thái từng phần việc", desc="Mỗi dòng là phần việc của MỘT nhân viên (sale, DVKH hoặc Kỹ thuật) với một hợp đồng, do quản lý team đó nhận tin và giao. Quá hạn xếp trước. Chọn tên quản lý ở ô Tôi là để xem đúng phần việc của team."),
        card([
            html.Div([dcc.Dropdown(id="lk-td-tl-nguoi", placeholder="Chọn người nhận", style={"width": "220px"}),
                      dcc.Input(id="lk-td-tl-chu", type="text", className="inp", placeholder='Ví dụ: xong MHAAA0007', style={"width": "340px"}),
                      nut("lk-td-tl-gui", "Gửi trả lời")], className="lk-badges"),
            html.Div("Tuỳ chọn: giả lập quản lý nhắn lại cho bot. Cách nhắn: nhận MÃ, xong MÃ, không được MÃ lý do. Cách chính là chọn nhiều việc và giao trên bảng phía trên.",
                     className="lk-ghi-chu", style={"marginTop": "6px"}),
        ], title="Giả lập trả lời Zalo (tuỳ chọn)"),
        card([bang("lk-td-thu", COT_THU, cao=360)], title="Hộp thư Zalo", desc="Mọi tin bot gửi và tin người nhận trả lời (mới nhất ở trên)."),
    ])


def _kpi_hang(d: pd.DataFrame) -> list:
    t = td.tom_tat(d)
    return [kpi("Phần việc đã giao", t["tong"], "Mỗi nhân viên, mỗi hợp đồng, mỗi luật là một phần"), kpi("Mới giao", t["moi"], "Quản lý chưa giao cho ai"),
            kpi("Đã giao / đang làm", t["da_nhan"], "Quản lý đã giao cho nhân viên"), kpi("Đã xong", t["da_xong"], f"{t['ty_le_xong']}% số việc thật" if t["ty_le_xong"] is not None else "Chưa có"),
            kpi("Quá hạn", t["qua_han"], f"{t['da_bao_ql']} việc đã báo quản lý", trang_thai="bad" if t["qua_han"] else ""),
            kpi("Không làm được", t["khong_lam_duoc"], f"{t['tu_het']} việc tự hết dấu hiệu")]


def _hanh_dong(ma: str, chon, ly_do: str, nguoi: str, chu: str, giao_cho: str | None = None, ql: str | None = None) -> str:
    """Chạy một hành động bấm trên trang; trả về dòng thông báo."""
    if ma == "lk-td-dongbo":
        r = td.dong_bo(luat.danh_sach_viec())
        return f"Đã lấy việc từ các luật: thêm {r['moi']} phần việc mới, mở lại {r['mo_lai']}, đóng {r['het']} việc hết dấu hiệu."
    if ma == "lk-td-gui":
        td.dong_bo(luat.danh_sach_viec())
        r = zv.gui_viec_moi()
        doi_tuong = "quản lý" if zv.tin_cho() == "quan_ly" else "người"
        return f"Đã soạn {r['tin']} tin cho {r['nguoi']} {doi_tuong} ({r['viec']} phần việc). Kênh: {NHAN_KENH[zv.kenh()]}"
    if ma == "lk-td-nhac":
        r = zv.chay_nhac()
        if zv.tin_cho() == "quan_ly":
            return f"Đã nhắc quản lý {r['nhac']} phần việc quá hạn và báo giám đốc chi nhánh {r.get('viec_bao', 0)} việc quá {td.cau_hinh_gio()[1]} giờ chưa xong."
        return f"Đã nhắc {r['nhac']} phần việc quá hạn và báo {r['bao_quan_ly']} quản lý."
    if ma in ("lk-td-lui1", "lk-td-lui2"):
        gio = td.them_gio_gia_lap(25 if ma == "lk-td-lui1" else 49)
        r = mp.tien_thoi_gian()
        return (f"Đã lùi đồng hồ minh hoạ, tổng cộng {gio:.0f} giờ. Trong lúc đó người nhận (mô phỏng) đã làm xong {r['xong']} phần việc, "
                f"không làm được {r['khong_lam_duoc']}, mới nhận {r['da_nhan']}; phần còn lại chưa ai đụng tới.")
    if ma == "lk-td-reset":
        td.xoa_het_minh_hoa()
        return "Đã xoá giao việc, nhật ký, hộp thư và đồng hồ giả lập của bản minh hoạ."
    if ma == "lk-td-chuan-bi":
        r = mp.chuan_bi_demo()
        return (f"Đã chuẩn bị demo: nạp {r['mo_phong']} phần việc MÔ PHỎNG của 14 ngày qua và {r['moi']} phần việc mới hôm nay (chưa gửi). "
                "Sang tab Hiệu quả để xem số đo; ở đây bấm \"2. Gửi việc mới qua Zalo\" để chạy kịch bản.")
    if ma == "lk-td-chia-deu":
        boi = ql if ql and ql != "all" else td.giam_doc(td.nguoi_nhan().fillna(""))
        r = dp.chia_deu(boi)
        if not r["giao"] and not r["thieu_nguoi"]:
            return "Không còn việc hàng chờ nào chưa giao trong phạm vi này."
        return (f"Đã chia đều {r['giao']} phần việc hàng chờ: " + ", ".join(f"{t} {n}" for t, n in r["theo_nguoi"].items())
                + (f". {r['thieu_nguoi']} việc chưa chia được vì team không có nhân viên đúng khối." if r["thieu_nguoi"] else "."))
    if ma == "lk-td-tl-gui":
        if not nguoi or not (chu or "").strip():
            return "Chọn người nhận và gõ câu trả lời."
        return "Bot phản hồi: " + zv.xu_ly_tra_loi(nguoi, chu).replace("\n", " | ")
    if not chon:
        return "Chọn ít nhất một dòng trong bảng trước."
    boi = ql if ql and ql != "all" else "quản lý"
    if ma == "lk-td-giao":
        if not giao_cho:
            return "Chọn người nhận việc ở ô Giao cho."
        n = td.giao_viec([int(r["id"]) for r in chon], giao_cho, boi)
        return f"Đã giao {n} phần việc cho {giao_cho}" + (f" ({len(chon) - n} việc đã xong hoặc đã đóng nên không đổi)." if n < len(chon) else ".")
    tt = {"lk-td-xong": "da_xong", "lk-td-khong": "khong_lam_duoc"}[ma]
    if tt == "khong_lam_duoc" and not (ly_do or "").strip():
        return "Ghi lý do khi không làm được."
    n = sum(1 for r in chon if td.cap_nhat(int(r["id"]), tt, boi, (ly_do or "").strip()))
    return f"Đã ghi {n} phần việc → {td.TRANG_THAI[tt]}." if n else "Không cập nhật được."


def register(app):
    cb = callback_can_quyen(app, QUYEN)
    nut = ["lk-td-dongbo", "lk-td-gui", "lk-td-nhac", "lk-td-lui1", "lk-td-lui2", "lk-td-reset", "lk-td-chuan-bi", "lk-td-giao", "lk-td-chia-deu", "lk-td-xong", "lk-td-khong", "lk-td-tl-gui"]

    @cb(Output("lk-td-thongbao", "children"), Output("lk-td-tick", "data"), *[Input(i, "n_clicks") for i in nut],
        State("lk-td-luoi", "selectedRows"), State("lk-td-lydo", "value"), State("lk-td-tl-nguoi", "value"), State("lk-td-tl-chu", "value"),
        State("lk-td-giao-cho", "value"), State("lk-td-ql", "value"), State("lk-td-tick", "data"), prevent_initial_call=True)
    def _bam(*a):
        ma = ctx.triggered_id
        if ma not in nut or not ctx.triggered[0]["value"]:
            raise PreventUpdate
        chon, ly_do, nguoi, chu, giao_cho, ql, tick = a[len(nut):]
        try:
            thong_bao = alert(_hanh_dong(ma, chon, ly_do, nguoi, chu, giao_cho, ql), "info")
        except RuntimeError as e:
            thong_bao = alert(str(e), "bad")
        return thong_bao, (tick or 0) + 1

    @cb(Output("lk-td-kenh", "children"), Output("lk-td-kpi", "children"), Output("lk-td-luoi", "rowData"), Output("lk-td-thu", "rowData"),
        Output("lk-td-dong-ho", "children"), Output("lk-td-tl-nguoi", "options"),
        Input("lk-tab", "value"), Input("lk-td-tick", "data"), Input("lk-td-loc", "value"), Input("lk-td-ql", "value"))
    def _ve(tab, _tick, loc, ql):
        if tab != "td":
            raise PreventUpdate
        d = td.loc_pham_vi(td.danh_sach(), ql)
        if len(d):                                                                  # việc THẬT hôm nay lên trước lịch sử mô phỏng (giữ nguyên thứ tự quá hạn / mức Cao bên trong mỗi nhóm)
            d = d.assign(_mp=d["mo_phong"].fillna(0)).sort_values("_mp", kind="stable").drop(columns="_mp")
        thu = td.hop_thu()
        thu["loai_ten"] = thu["loai"].map(lambda x: TEN_LOAI_TIN.get(x, x))
        thu["luc"] = thu["luc"].map(_vn)
        gio = td.gio_gia_lap()
        dong_ho = f"Giờ hệ thống: {_vn(td.bay_gio())}" + (f" (đã lùi {gio:.0f} giờ để xem nhắc / báo quản lý)" if gio else "")
        nguoi = [{"label": f"{r['ten']} ({r['ma']})", "value": r["ma"]} for r in td.nguoi_nhan().fillna("").to_dict("records")]
        kenh = alert(NHAN_KENH[zv.kenh()], "warn" if zv.kenh() != "zalo" else "ok")
        return kenh, _kpi_hang(d), _dong(td.loc_trang_thai(d, loc)) if len(d) else [], thu.to_dict("records"), dong_ho, nguoi

    @cb(Output("lk-td-xlsx", "href"), Input("lk-td-ql", "value"), Input("lk-td-loc", "value"))
    def _duong_xuat(ql, loc):
        return f"/lien-khoi/xuat.xlsx?ql={ql or 'all'}&loc={loc or 'mo'}"

    @cb(Output("lk-td-giao-cho", "options"), Output("lk-td-giao-cho", "value"), Input("lk-td-ql", "value"))
    def _giao_cho(ql):
        ds = td.nguoi_nhan().fillna("")
        cap = ds[ds["vai_tro"] == "nhan_vien"] if not ql or ql == "all" else ds[ds["quan_ly"].isin(td.pham_vi(ql, ds))]       # mọi người nằm dưới quản lý này (nhân viên và quản lý cấp dưới)
        return [{"label": f"{r['ten']} ({r['ma']})", "value": r["ma"]} for r in cap.to_dict("records")], None

    @cb(Output("lk-td-chon", "children"), Input("lk-td-luoi", "selectedRows"))
    def _chon(chon):
        return f"Đã chọn {len(chon)} phần việc ({len({r['so_hd'] for r in chon})} hợp đồng)." if chon else "Chưa chọn dòng nào."

    @cb(Output("lk-td-nhat-ky", "children"), Input("lk-td-luoi", "selectedRows"))
    def _nhat_ky(chon):
        if not chon or len(chon) != 1:
            return ""
        n = td.nhat_ky(int(chon[0]["id"]))
        return html.Div([html.Div(f"Nhật ký {chon[0]['so_hd']} · {chon[0]['nguoi']}:", className="lk-nhan")] +
                        [html.Div(f"{_vn(r['luc'])} · {r['boi']} · {TEN_HANH_DONG.get(r['hanh_dong'], td.TRANG_THAI.get(r['hanh_dong'], r['hanh_dong']))}" + (f" · {r['ghi_chu']}" if r["ghi_chu"] else ""),
                                  className="lk-ghi-chu") for r in n.to_dict("records")])
