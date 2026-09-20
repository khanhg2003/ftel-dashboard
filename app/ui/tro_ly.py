"""Giao diện trợ lý AI: thẻ Dự báo & nhận xét trên các trang, khung chat nổi, tab cấu hình ở Quản trị."""
from __future__ import annotations

import time
from types import SimpleNamespace

import dash_ag_grid as dag
from dash import Input, Output, State, ctx, dcc, html, no_update
from flask_login import current_user

from app import tro_ly as ai
from app import tro_ly_du_lieu as dl
from app.admin_service import ROLES, danh_sach_user
from app.auth import ghi_log
from app.du_bao import AN_TOAN, RUI_RO, TANG_TOC
from app.thoi_gian import chu_gio_vn, gio_viet_nam
from app.ui.components import alert, callback_can_quyen, card, kpi, tip, ghi_chu
from app.ui.icons import icon

AN = {"display": "none"}
MAU_DANH_GIA = {AN_TOAN: "ok", TANG_TOC: "warn", RUI_RO: "bad"}
MODEL_GOI_Y = ["gpt-5-mini", "gpt-5", "gpt-5-nano", "gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini"]


# Con cáo cam - hình đại diện của trợ lý. Con ngươi (.cao-nguoi) nhìn theo chuột: assets/cao_nhin_theo.js
SVG_CAO = """<svg class="cao" viewBox="0 0 80 80" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
<g class="cao-duoi"><path d="M47 62C60 66 76 58 76 40C76 31 71 25 66 23C68 33 64 44 54 50C50 53 47 56 45 58Z" fill="#D9480F"/>
<path d="M66 23C71 25 76 31 76 40C76 43 75 46 74 48C72 40 68 34 63 31C65 28 66 25 66 23Z" fill="#FFF4E6"/></g>
<path d="M27 48C22 58 24 72 29 75H47C52 72 54 58 49 48C42 43 34 43 27 48Z" fill="#E8590C"/>
<path d="M32 48C33 58 36 64 38 66C40 64 43 58 44 48C40 46 36 46 32 48Z" fill="#FFF4E6"/>
<rect x="29" y="68" width="7" height="10" rx="3.5" fill="#3B2418"/><rect x="40" y="68" width="7" height="10" rx="3.5" fill="#3B2418"/>
<g class="cao-dau"><g transform="translate(14 0) scale(.75)">
<path d="M9 5 27 19 13 31Z" fill="#D9480F"/><path d="M55 5 37 19 51 31Z" fill="#D9480F"/>
<path d="M13 12 22 20 15 26Z" fill="#3B2418"/><path d="M51 12 42 20 49 26Z" fill="#3B2418"/>
<path d="M7 31Q9 15 32 15Q55 15 57 31Q57 45 32 59Q7 45 7 31Z" fill="#E8590C"/>
<path d="M7 33Q19 36 32 59Q13 49 7 33Z" fill="#FFF4E6"/><path d="M57 33Q45 36 32 59Q51 49 57 33Z" fill="#FFF4E6"/>
<path d="M23 43Q32 36 41 43Q37 54 32 59Q27 54 23 43Z" fill="#FFF4E6"/>
<g class="cao-mat"><ellipse cx="22.5" cy="33" rx="5.2" ry="5.6" fill="#fff"/><ellipse cx="41.5" cy="33" rx="5.2" ry="5.6" fill="#fff"/>
<g class="cao-nguoi" data-cx="30.9" data-cy="24.8"><circle cx="22.5" cy="33" r="3" fill="#2B1B14"/><circle cx="23.6" cy="31.9" r="1" fill="#fff"/></g>
<g class="cao-nguoi" data-cx="45.1" data-cy="24.8"><circle cx="41.5" cy="33" r="3" fill="#2B1B14"/><circle cx="42.6" cy="31.9" r="1" fill="#fff"/></g></g>
<ellipse cx="32" cy="50" rx="3.2" ry="2.3" fill="#2B1B14"/>
<path d="M29 54Q32 56.5 35 54" stroke="#2B1B14" stroke-width="1.2" fill="none" stroke-linecap="round"/></g></g>
</svg>"""


def con_cao(co: str = "nho"):
    return dcc.Markdown(SVG_CAO, dangerously_allow_html=True, className=f"cao-boc {co}")


def _cau_hinh_an_toan() -> dict:
    try:
        return ai.cau_hinh()
    except Exception:                   # database lỗi thì coi như tắt AI, không làm hỏng trang
        return dict(ai.MAC_DINH)


def _dung_duoc(ch: dict) -> bool:
    """Người đang đăng nhập có thấy / dùng được AI không (bật + được mở quyền)."""
    try:
        return current_user.is_authenticated and ai.duoc_dung(current_user, ch)
    except Exception:
        return False


# ------------------------------------------------------------------ thẻ dự báo & nhận xét
def the_ai(prefix: str, tieu_de: str, mo_ta: str, truoc=None):
    """Thẻ dùng chung: phần dự báo (luôn hiện) + nút nhận xét của trợ lý (ẩn khi AI tắt)."""
    ch = _cau_hinh_an_toan()
    return html.Div([
        html.Div([
            html.Div([html.H3([con_cao(), tieu_de, tip(mo_ta)], className="tieu-de-tip")],
                     className="the-ten"),
            html.Button([html.Span("✨"), html.Span(f"{ch['ten']} nhận xét", id=f"{prefix}-ai-nhan")],
                        id=f"{prefix}-ai-tao", className="btn primary",
                        style={} if _dung_duoc(ch) else AN,
                        title="Trợ lý AI đọc số của trang đang xem rồi nhận xét"),
        ], className="the-dau"),
        *([truoc] if truoc is not None else []),
        dcc.Loading(html.Div(id=f"{prefix}-ai-kq", className="ai-kq"), type="dot"),
    ], className="card the-ai")


def noi_dung_nhan_xet(ban: dict, ten: str):
    return html.Div([
        dcc.Markdown(ban["noi_dung"], className="ai-md"),
        html.Div(f"{ten} nhận xét lúc {chu_gio_vn(ban['luc'], '%H:%M %d/%m')}"
                 + (f" · {ban['username']} bấm tạo" if ban.get("username") else "")
                 + " · số do app tính, AI chỉ diễn giải - đối chiếu bảng số khi cần.", className="ai-meta"),
    ])


def gan_nhan_xet(app, prefix: str, loai: str, inputs: list[tuple[str, str]], ngu_canh, yeu_cau: str):
    """Mở trang / đổi bộ lọc: hiện nhận xét đã lưu (nếu có). Bấm nút: gọi AI tạo mới rồi lưu."""
    # Bấm là hiện ngay "đang viết" + khoá nút (AI mất 10-40 giây); máy chủ trả kết quả thì mở lại nút.
    app.clientside_callback(
        """function(n) {
            if (!n) { return [window.dash_clientside.no_update, window.dash_clientside.no_update]; }
            const div = function (p) { return {type: 'Div', namespace: 'dash_html_components', props: p}; };
            return [div({className: 'ai-dang-viet', children: [
                div({className: 'ai-cham', children: [0, 1, 2].map(function () {
                    return {type: 'I', namespace: 'dash_html_components', props: {}}; })}),
                'Đang đọc số của kỳ đang xem và viết nhận xét… thường mất 10-40 giây.']}), true];
        }""",
        Output(f"{prefix}-ai-kq", "children", allow_duplicate=True), Output(f"{prefix}-ai-tao", "disabled"),
        Input(f"{prefix}-ai-tao", "n_clicks"), prevent_initial_call=True)

    @app.callback(Output(f"{prefix}-ai-kq", "children"), Output(f"{prefix}-ai-nhan", "children"),
                  Output(f"{prefix}-ai-tao", "disabled", allow_duplicate=True),
                  Input(f"{prefix}-ai-tao", "n_clicks"), *[Input(i, p) for i, p in inputs],
                  prevent_initial_call="initial_duplicate")
    def _nhan_xet(_n, *gia_tri):
        ch = _cau_hinh_an_toan()
        if not _dung_duoc(ch):
            return "", no_update, False
        try:
            khoa, du_lieu = ngu_canh(current_user, *gia_tri)
            ban = ai.nhan_xet_da_luu(loai, khoa)
            if ctx.triggered_id == f"{prefix}-ai-tao":
                ban = ai.tao_nhan_xet(current_user, loai, khoa, du_lieu(), yeu_cau)
            if not ban:
                return (html.Div(f"Bấm “{ch['ten']} nhận xét” để trợ lý đọc số của kỳ đang xem: nhận định, "
                                 "vì sao và việc cần làm.", className="ai-goi-y"),
                        f"{ch['ten']} nhận xét", False)
            return noi_dung_nhan_xet(ban, ch["ten"]), "Tạo lại nhận xét", False
        except ai.LoiAI as e:
            return alert(str(e), "warn"), no_update, False


def nhan_xet_anh(tu: str | None, den: str | None, chi_nhanh: str | None) -> tuple[str, str] | None:
    """(tiêu đề, nội dung) nhận xét ngắn in dưới ảnh Báo cáo Tổng. AI tắt / lỗi thì ảnh vẫn xuất bình thường."""
    ch = _cau_hinh_an_toan()
    if not _dung_duoc(ch):
        return None
    try:
        khoa, du_lieu = dl.ngu_canh_tong(current_user, tu, den, chi_nhanh)
        ban = ai.nhan_xet_da_luu("tong_anh", khoa) or ai.tao_nhan_xet(current_user, "tong_anh", khoa, du_lieu(),
                                                                      dl.YEU_CAU_ANH)
        return f"{ch['ten']} nhận xét", ban["noi_dung"]
    except ai.LoiAI:
        return None


def bang_du_bao(gid: str):
    so = {"function": "params.value == null ? '–' : Number(params.value).toLocaleString('vi-VN')"}
    return dag.AgGrid(
        id=gid, className="ag-theme-quartz ag-theme-ftel", rowData=[],
        columnDefs=[
            {"field": "phong", "headerName": "Phòng", "pinned": "left", "minWidth": 130, "flex": 1.3},
            {"field": "mt", "headerName": "MT tháng", "valueFormatter": so},
            {"field": "luy_ke", "headerName": "Luỹ kế", "valueFormatter": so},
            {"field": "tb_ngay", "headerName": "TB/ngày"},
            {"field": "du_bao", "headerName": "Dự báo cuối tháng", "valueFormatter": so,
             "cellStyle": {"fontWeight": "650"},
             "headerTooltip": "Luỹ kế + phần còn lại theo đúng nhịp tháng trước"},
            {"field": "du_bao_tuan", "headerName": "Giữ nhịp 7 ngày", "valueFormatter": so,
             "headerTooltip": "Kịch bản thận trọng: từ giờ tới cuối tháng chỉ bán đều như 7 ngày gần nhất "
                              "đã chốt số, không bứt tốc cuối tháng"},
            {"field": "pct_mt", "headerName": "% MT", "valueFormatter":
                {"function": "params.value == null ? '–' : params.value + '%'"}},
            {"field": "can_moi_ngay", "headerName": "Cần mỗi ngày", "valueFormatter": so,
             "headerTooltip": "Số online mỗi ngày còn lại cần đạt để đủ mục tiêu tháng"},
            {"field": "danh_gia", "headerName": "Đánh giá", "minWidth": 130, "cellStyle": {"styleConditions": [
                {"condition": f"params.value == '{AN_TOAN}'", "style": {"color": "#0A5B31", "fontWeight": "650"}},
                {"condition": f"params.value == '{TANG_TOC}'", "style": {"color": "#8A5709", "fontWeight": "650"}},
                {"condition": f"params.value == '{RUI_RO}'", "style": {"color": "#B42318", "fontWeight": "650"}}]}},
        ],
        defaultColDef={"flex": 1, "minWidth": 96, "sortable": True, "resizable": True,
                       "cellClass": "o-giua", "headerClass": "tieu-de-giua"},
        dashGridOptions={"suppressCellFocus": True, "rowHeight": 32, "headerHeight": 38},
        getRowStyle={"styleConditions": [{"condition": "params.data.phong_code == 'TOTAL'",
                                          "style": {"backgroundColor": "#B9D3EB", "fontWeight": "700"}}]},
        style={"width": "100%", "height": "380px"})


def _so1(v) -> str:
    return f"{v:,.1f}".replace(",", "@").replace(".", ",").replace("@", ".")


def giai_thich_du_bao(r: dict, nhip: dict | None, tuan: dict | None) -> list:
    """Hai dòng nhỏ dưới ô số: số chính dựa vào nhịp tháng trước, và kịch bản không bứt tốc.

    Nói bằng chính số của tháng trước và của tuần vừa rồi, không dùng chữ "hệ số".
    """
    dong = []
    if nhip and nhip.get("dau") and nhip.get("cuoi"):
        t, k, n = nhip["thang_truoc"][5:7], nhip["cat"], nhip["so_ngay"]
        huong = "nhanh hơn" if nhip["he_so"] >= 1 else "chậm hơn"
        dong.append(f"Số chính giả định tháng này giữ đúng nhịp tháng trước: tháng {t} các ngày "
                    f"{k + 1:02d}-{n}/{t} bán {_so1(nhip['cuoi'])} online mỗi ngày, {huong} "
                    f"{str(nhip['he_so']).replace('.', ',')} lần mức {_so1(nhip['dau'])} của các ngày "
                    f"01-{k:02d}/{t}.")
    if tuan and r.get("du_bao_tuan") is not None and tuan.get("so_ngay"):
        th = tuan["thang"][5:7]
        so = f"{int(r['du_bao_tuan']):,}".replace(",", ".")
        dong.append(f"Nếu từ giờ tới cuối tháng chỉ bán đều như {tuan['so_ngay']} ngày gần nhất "
                    f"({tuan['tu']:02d}-{tuan['den']:02d}/{th}, {_so1(tuan['tb'])} online mỗi ngày) thì cuối "
                    f"tháng khoảng {so}"
                    + (f" = {round(r['pct_tuan'])}% mục tiêu." if r.get("pct_tuan") else " online."))
    return [html.Div(c, className="desc") for c in dong]


def dong_du_bao(r: dict | None, ten: str = "Phòng", nhip: dict | None = None, tuan: dict | None = None):
    """Một dòng tóm tắt dự báo (Báo cáo phòng, Phân tích)."""
    if not r:
        return html.Div()
    if not r.get("mt"):
        return html.Div(f"{ten} chưa có mục tiêu tháng nên chưa dự báo được % hoàn thành.", className="desc")
    hang = html.Div([
        kpi("Dự báo cuối tháng", f"{r['du_bao']:,}".replace(",", "."), f"mục tiêu {r['mt']:,}".replace(",", "."),
            MAU_DANH_GIA.get(r["danh_gia"], "")),
        kpi("% mục tiêu dự báo", f"{r['pct_mt']}%", r["danh_gia"], MAU_DANH_GIA.get(r["danh_gia"], "")),
        kpi("Bình quân mỗi ngày", str(r["tb_ngay"]).replace(".", ","), f"luỹ kế {r['luy_ke']:,}".replace(",", ".")),
        kpi("Cần mỗi ngày còn lại", f"{r['can_moi_ngay'] or 0:,}".replace(",", "."), "để đủ mục tiêu tháng"),
    ], className="kpi-row", style={"marginBottom": "6px"})
    loi = giai_thich_du_bao(r, nhip, tuan)
    return html.Div([hang, *loi]) if loi else hang


MO_TA_DU_BAO = ("Dự báo cuối tháng lấy luỹ kế hiện tại rồi cộng phần còn lại theo đúng nhịp tháng trước "
                "(tháng trước, những ngày cuối tháng bán nhanh hơn đầu tháng bao nhiêu lần thì tháng này tính "
                "như vậy). "
                "Cột 'Giữ nhịp 7 ngày' là kịch bản thận trọng: từ giờ tới cuối tháng chỉ bán đều như 7 ngày "
                "gần nhất, không bứt tốc. "
                "Thử lại trên tháng 8 đã biết kết quả: cách tính chính sai khoảng 1-2%, kịch bản 7 ngày thấp "
                "hơn thực tế khoảng 4-6%. "
                "Đánh giá theo số chính: An toàn từ 100% mục tiêu trở lên · Cần tăng tốc 90-99% · Rủi ro dưới "
                "90%.")


# ------------------------------------------------------------------ khung chat nổi
def khung_chat():
    try:
        if not current_user.is_authenticated:
            return html.Div()
        ch = ai.cau_hinh()
    except Exception:
        return html.Div()
    if not _dung_duoc(ch):
        return html.Div()
    ten = ch["ten"]
    return html.Div([
        dcc.Store(id="ai-chat-ls", storage_type="session", data=[]),
        dcc.Store(id="ai-chat-cho"),
        dcc.Store(id="ai-chat-cuon"),
        html.Button([con_cao("vua"), html.Span(f"Hỏi {ten}")], id="ai-chat-nut",
                    className="ai-nut-noi", title=f"Hỏi {ten} về số bán, NSLĐ"),
        html.Div([
            html.Div([con_cao("vua"),
                      html.Div([html.B(ten), html.Div("Trợ lý số liệu · trả lời theo quyền của bạn",
                                                      className="ai-phu")], className="grow"),
                      html.Button(icon("trash", 14), id="ai-chat-xoa", className="modal-x",
                                  title="Xoá hội thoại"),
                      html.Button("×", id="ai-chat-dong", className="modal-x", title="Đóng")],
                     className="ai-dau"),
            # lịch sử do máy chủ vẽ; câu vừa gửi + "đang trả lời" vẽ ngay ở trình duyệt (không chờ máy chủ)
            html.Div([html.Div(id="ai-chat-lich", className="ai-lich"), html.Div(id="ai-chat-dang", className="ai-lich")],
                     id="ai-chat-log", className="ai-log"),
            html.Div([dcc.Textarea(id="ai-chat-o", placeholder="VD: IBB5 tháng này so cùng kỳ thế nào?",
                                   className="ai-o", maxLength=600),
                      html.Button("Gửi", id="ai-chat-gui", className="btn primary")], className="ai-go"),
        ], id="ai-chat-khung", className="ai-khung"),
    ], className="ai-chat")


def _tin(m: dict, ten: str):
    if m["role"] == "user":
        return html.Div(m["content"], className="ai-tin ai-toi")
    return html.Div([html.Div(ten, className="ai-ten"), dcc.Markdown(m["content"], className="ai-md")],
                    className="ai-tin ai-ban" + (" ai-loi" if m.get("loi") else ""))


# Câu hỏi gợi ý theo trang đang xem
GOI_Y_CAU_HOI = {
    "/": ["Tóm tắt kết quả kỳ đang xem so với mục tiêu và cùng kỳ", "Phòng nào có nguy cơ không đạt mục tiêu tháng?",
          "Bầy nào dẫn đầu, bầy nào đang tụt?"],
    "/tracking": ["So sánh online 7 ngày gần nhất với 7 ngày trước đó", "Ngày nào tháng này online thấp bất thường?",
                  "Phòng nào tăng, giảm mạnh nhất so với cùng kỳ?"],
    "/phantich": ["Tỷ lệ bán kèm V.VIP, Camera thay đổi thế nào so với cùng kỳ?",
                  "Phòng nào có nhiều hợp đồng chờ online lâu nhất?", "Nhóm gói nào dễ bán kèm nhất?"],
    "/phong": ["Phòng đang xem có đạt mục tiêu tháng không?", "Nhân sự nào cần trao đổi ngay và vì sao?",
               "Ai đang có nhiều hợp đồng tồn lâu?"],
    "/hr": ["NSLĐ phòng nào cao nhất, thấp nhất tháng gần nhất?", "Tỷ lệ tân binh nghỉ việc ra sao?",
            "NSLĐ tháng gần nhất so với bình quân năm thế nào?"],
}


def goi_y_cho_trang(duong_dan: str | None, user) -> list[str]:
    ds = GOI_Y_CAU_HOI.get({"/sosanh": "/tracking"}.get(duong_dan or "/", duong_dan or "/"), GOI_Y_CAU_HOI["/"])
    return ds if user.duoc_xem_nhan_su or duong_dan not in ("/phong", "/hr") else GOI_Y_CAU_HOI["/"]


# ------------------------------------------------------------------ tab Quản trị → Trợ lý AI
def pane_cau_hinh(tab: str):
    o = lambda label, ctl: html.Div([html.Label(label), ctl], className="field rong")   # noqa: E731
    return html.Div(id="ai-pane", style={} if tab == "ai" else AN, children=[
        dcc.Store(id="ai-da-luu"),
        html.Datalist(id="ai-ds-model", children=[html.Option(value=m) for m in MODEL_GOI_Y]),
        card([
            dcc.Checklist(id="ai-bat", options=[{"label": " Bật trợ lý AI", "value": "bat"}],
                          value=[], className="ai-bat"),
            html.Div([
                o("Tên trợ lý", dcc.Input(id="ai-ten", type="text", className="inp", maxLength=20)),
                # ô chữ thường che bằng CSS (không phải type=password) để trình duyệt KHÔNG tự điền mật khẩu
                # đăng nhập đã lưu vào đây - trước đây bị điền sẵn nên mỗi lần Lưu lại phải dán lại mã
                o("Mã API ChatGPT (OpenAI)", dcc.Input(id="ai-key", type="text", className="inp o-an",
                                                       autoComplete="off", spellCheck=False, name="ftel-ai-ma",
                                                       placeholder="sk-...")),
                o("Model cho chat", dcc.Input(id="ai-model-chat", type="text", className="inp", list="ai-ds-model")),
                o("Model cho nhận xét", dcc.Input(id="ai-model-nx", type="text", className="inp", list="ai-ds-model")),
                o("Trần chi phí mỗi tháng (USD)", dcc.Input(id="ai-tran", type="number", min=0.5, step=0.5,
                                                            className="inp")),
                o("Số câu mỗi người / ngày", dcc.Input(id="ai-luot", type="number", min=1, step=1, className="inp")),
                o("Vai trò được dùng AI", dcc.Dropdown(id="ai-vai-tro", multi=True, searchable=False,
                                                       placeholder="Chưa mở cho vai trò nào",
                                                       options=[{"label": t, "value": v} for v, t in ROLES])),
                o("Thêm từng tài khoản được dùng", dcc.Dropdown(id="ai-tai-khoan", multi=True,
                                                                placeholder="Chọn tài khoản (tuỳ chọn)")),
            ], className="form-grid"),
            ghi_chu("Tài khoản dùng được AI khi vai trò của họ được chọn HOẶC tài khoản đó được chọn "
                    "riêng. VD giai đoạn thử: bỏ trống vai trò, chỉ chọn tài khoản admin → sau mở thêm tài khoản "
                    "BGĐ → cuối cùng chọn vai trò Trưởng phòng. Người chưa được mở quyền không thấy nút chat, nút "
                    "nhận xét và nhận xét trên ảnh.", nhan="Cách mở quyền AI", style={"marginTop": "8px"}),
            html.Div(id="ai-quyen-hien", className="desc", style={"marginTop": "4px"}),
            html.Div(id="ai-key-hien", className="desc", style={"marginTop": "10px"}),
            html.Div([
                html.Button([icon("check", 14), html.Span("Lưu cấu hình")], id="ai-luu", className="btn primary"),
                html.Button([icon("refresh", 14), html.Span("Thử kết nối")], id="ai-thu", className="btn"),
                html.Div(className="grow"),
                html.Button([icon("trash", 14), html.Span("Xoá mã API")], id="ai-xoa-key", className="btn nguy-hiem"),
            ], className="toolbar", style={"marginTop": "14px", "marginBottom": 0}),
            html.Div(id="ai-msg", style={"marginTop": "12px"}),
            ghi_chu("Dán mã lấy ở platform.openai.com → API keys rồi bấm Lưu. Mã được mã hoá trước khi lưu, sau đó "
                    "chỉ hiện 4 ký tự cuối. Quản trị (BGĐ) không giới hạn số câu; hết trần chi phí tháng thì AI tự "
                    "tạm dừng tới đầu tháng sau (hoặc nâng trần). Chi phí là ước tính theo bảng giá OpenAI, "
                    "số chính xác xem ở trang Usage của OpenAI.", nhan="Về mã và chi phí", style={"marginTop": "8px"}),
        ], title="Cấu hình trợ lý AI"),
        card([
            html.Div(id="ai-dung-kpi", className="kpi-row"),
            dag.AgGrid(id="ai-dung-grid", className="ag-theme-quartz ag-theme-ftel", rowData=[],
                       columnDefs=[{"field": "username", "headerName": "Tài khoản", "flex": 1.4},
                                   {"field": "hom_nay", "headerName": "Câu hỏi hôm nay", "flex": 1},
                                   {"field": "thang", "headerName": "Câu hỏi tháng này", "flex": 1},
                                   {"field": "chi_phi", "headerName": "Chi phí tháng (USD)", "flex": 1,
                                    "valueFormatter": {"function": "'$' + Number(params.value).toFixed(3)"}}],
                       dashGridOptions={"suppressCellFocus": True, "domLayout": "autoHeight"},
                       style={"width": "100%"}),
        ], title="Mức sử dụng tháng này", desc="Câu hỏi = câu chat + lần bấm tạo nhận xét. Xem lại nhận xét "
                                              "đã lưu không tính."),
    ])


def register(app):
    # ---------------- chat
    app.clientside_callback(
        """function(_a, _b) {
            const trig = (window.dash_clientside.callback_context.triggered[0] || {}).prop_id || '';
            const mo = trig.startsWith('ai-chat-nut');
            if (mo) { setTimeout(function () { const o = document.getElementById('ai-chat-o'); if (o) o.focus(); }, 80); }
            return mo ? 'ai-khung mo' : 'ai-khung';
        }""",
        Output("ai-chat-khung", "className"), Input("ai-chat-nut", "n_clicks"), Input("ai-chat-dong", "n_clicks"),
        prevent_initial_call=True)

    # gửi: hiện ngay câu hỏi (máy khách), máy chủ trả lời sau. Câu gợi ý và phím Enter: assets/tro_ly_ai.js
    app.clientside_callback(
        """function(_n, chu, cho, ls) {
            const nu = window.dash_clientside.no_update;
            const tu_goi_y = window.__aiCau; window.__aiCau = null;
            // đang chờ câu trả lời trước thì chưa nhận câu mới (tránh mất câu trả lời đang chạy)
            if (cho && Date.now() - cho.id < 90000 && !(ls || []).some(function (m) { return m.id === cho.id; })) {
                return [nu, nu];
            }
            chu = ((tu_goi_y || chu) || '').trim();
            if (!chu) { return [nu, nu]; }
            return [{id: Date.now(), q: chu}, tu_goi_y ? nu : ''];
        }""",
        Output("ai-chat-cho", "data"), Output("ai-chat-o", "value"),
        Input("ai-chat-gui", "n_clicks"), State("ai-chat-o", "value"), State("ai-chat-cho", "data"),
        State("ai-chat-ls", "data"), prevent_initial_call=True)

    # Hiện ngay câu vừa gửi + "đang trả lời". Chỉ được phụ thuộc ai-chat-cho: callback nào có Input là ai-chat-ls
    # (đầu ra của _tra_loi) đều bị Dash giữ lại tới khi câu trả lời xong -> người dùng không thấy gì lúc chờ.
    # Có câu trả lời thì _ve vẽ lịch sử và xoá khối này trong cùng một lần (không nháy trống).
    app.clientside_callback(
        """function(cho) {
            // quá 90 giây chưa có trả lời (mất mạng, máy chủ lỗi) thì thôi hiện "đang trả lời", cho gửi lại
            if (!cho || Date.now() - cho.id > 90000) { return []; }
            const div = function (props) { return {type: 'Div', namespace: 'dash_html_components', props: props}; };
            return [
                div({className: 'ai-tin ai-toi', children: cho.q}),
                div({className: 'ai-tin ai-ban ai-dang-go', children: [
                    div({className: 'ai-ten', children: 'Đang tra số và trả lời…'}),
                    div({className: 'ai-cham', children: [
                        {type: 'I', namespace: 'dash_html_components', props: {}},
                        {type: 'I', namespace: 'dash_html_components', props: {}},
                        {type: 'I', namespace: 'dash_html_components', props: {}}]})]})];
        }""",
        Output("ai-chat-dang", "children"), Input("ai-chat-cho", "data"), prevent_initial_call=True)

    @app.callback(Output("ai-chat-ls", "data"), Input("ai-chat-cho", "data"), Input("ai-chat-xoa", "n_clicks"),
                  State("ai-chat-ls", "data"), State("url", "pathname"), State("ky-chung", "data"),
                  prevent_initial_call=True)
    def _tra_loi(cho, _xoa, ls, duong_dan, ky):
        if ctx.triggered_id == "ai-chat-xoa":
            return []
        ls = ls or []
        if not cho or any(m.get("id") == cho["id"] for m in ls):
            return no_update
        hoi = {"role": "user", "content": cho["q"][:600], "id": cho["id"]}
        try:
            u = current_user
            ky_gon = dl.bo_loc_trang(duong_dan, ky)
            tra_loi = ai.chat(u, [m for m in ls if not m.get("loi")], hoi["content"],
                              dl.ngu_canh_chat(u, duong_dan, ky), dl.cong_cu(u),
                              lambda ten, ts: dl.chay_cong_cu(u, ten, ts),
                              khoa_luu=f"{duong_dan}|{ky_gon}|{u.role}|{u.phong_duoc_xem()}|{u.phong_nhan_su()}")
            dap = {"role": "assistant", "content": tra_loi}
        except ai.LoiAI as e:
            dap = {"role": "assistant", "content": str(e), "loi": True}
        except Exception as e:                                 # pragma: no cover - lỗi lạ vẫn báo gọn
            ghi_log("ai_loi", f"{type(e).__name__}: {str(e)[:200]}")
            dap = {"role": "assistant", "content": "Có lỗi khi lấy số, bạn thử lại hoặc hỏi cách khác.", "loi": True}
        return (ls + [hoi, dap])[-30:]

    @app.callback(Output("ai-chat-lich", "children"), Output("ai-chat-dang", "children", allow_duplicate=True),
                  Input("ai-chat-ls", "data"), Input("url", "pathname"), prevent_initial_call="initial_duplicate")
    def _ve(ls, duong_dan):
        """Hội thoại nối tiếp: câu hỏi của bạn -> câu trả lời -> ... Câu gợi ý (theo trang) nằm cuối dòng hội thoại,
        cuộn cùng tin nhắn; đang chờ trả lời thì ẩn (CSS)."""
        ten = _cau_hinh_an_toan()["ten"]
        ls = ls or []
        tin = [html.Div([html.Div(ten, className="ai-ten"),
                         html.Div(f"Chào {current_user.ho_ten}! Mình là {ten}, tra số bán và NSLĐ theo đúng quyền "
                                  "của bạn. Chọn một câu gợi ý hoặc gõ câu hỏi bên dưới.")], className="ai-tin ai-ban")]
        tin += [_tin(m, ten) for m in ls]
        da_hoi = {m["content"] for m in ls if m["role"] == "user"}
        goi_y = [c for c in goi_y_cho_trang(duong_dan, current_user) if c not in da_hoi]
        if goi_y:
            tin.append(html.Div([html.Div("Gợi ý cho trang này" if not ls else "Hỏi tiếp", className="ai-goi-y-nhan"),
                                 *[html.Button(c, className="ai-goi-y-cau", **{"data-cau": c}) for c in goi_y]],
                                className="ai-goi-y-hang"))
        return tin, no_update if ctx.triggered_id == "url" else []

    app.clientside_callback(
        """function(_) {
            setTimeout(function () {
                const l = document.getElementById('ai-chat-log');
                if (!l) { return; }
                const toi = l.querySelectorAll('.ai-toi'), cuoi = toi[toi.length - 1];
                // có câu trả lời mới: cuộn để câu hỏi vừa gửi nằm đầu khung, đọc câu trả lời từ đầu
                if (cuoi && !l.querySelector('.ai-dang-go')) { l.scrollTop = cuoi.offsetTop - 8; }
                else { l.scrollTop = l.scrollHeight; }
            }, 50);
            return window.dash_clientside.no_update;
        }""",
        Output("ai-chat-cuon", "data"), Input("ai-chat-lich", "children"), Input("ai-chat-dang", "children"),
        prevent_initial_call=True)

    # ---------------- Quản trị → Trợ lý AI
    cb = callback_can_quyen(app, "duoc_cau_hinh")

    @cb(Output("ai-pane", "style"), Input("qt-tab", "value"), prevent_initial_call=True)
    def _tab(tab):
        return {} if tab == "ai" else AN

    @cb(Output("ai-bat", "value"), Output("ai-ten", "value"), Output("ai-model-chat", "value"),
        Output("ai-model-nx", "value"), Output("ai-tran", "value"), Output("ai-luot", "value"),
        Output("ai-key-hien", "children"), Output("ai-dung-kpi", "children"), Output("ai-dung-grid", "rowData"),
        Output("ai-vai-tro", "value"), Output("ai-tai-khoan", "options"), Output("ai-tai-khoan", "value"),
        Output("ai-quyen-hien", "children"), Output("ai-key", "placeholder"),
        Input("qt-tab", "value"), Input("ai-da-luu", "data"))
    def _nap(tab, _luu):
        if tab != "ai":
            return (no_update,) * 14
        ch = ai.cau_hinh()
        users = danh_sach_user()
        tk = [] if users.empty else [{"label": f"{r.username} · {r.ho_ten or ''} ({r.vai_tro})", "value": r.username}
                                     for r in users.itertuples() if r.active]
        ten_vt = dict(ROLES)
        duoc = [] if users.empty else [
            r.username for r in users.itertuples()
            if r.active and ai.duoc_dung(SimpleNamespace(role=r.role, username=r.username), {**ch, "bat": True})]
        quyen = [html.B(f"Đang mở cho {len(duoc)} tài khoản: "),
                 ", ".join(duoc) if duoc else "chưa có ai",
                 f" · vai trò: {', '.join(ten_vt.get(v, v) for v in ch['vai_tro']) or 'không'}."]
        if ch["key_loi"]:
            key = alert("Mã API đã lưu không giải mã được (APP_SECRET_KEY đã đổi) - dán lại mã rồi Lưu.", "warn")
        elif ch["key"]:
            nguon = "lưu trong app" if ch["key_nguon"] == "app" else "lấy từ biến môi trường OPENAI_API_KEY"
            key = ["Đang dùng mã ", html.B(ai.key_an(ch["key"])), f" ({nguon}). Để trống ô mã khi lưu thì giữ mã cũ."]
        else:
            key = "Chưa có mã API - AI chưa chạy được."
        dung = ai.thong_ke_su_dung()
        chi_phi = sum(r["chi_phi"] for r in dung)
        pct = chi_phi / ch["tran_usd"] * 100 if ch["tran_usd"] else 0
        kpis = [kpi("Chi phí tháng này", f"${chi_phi:.3f}", f"trần ${ch['tran_usd']:g} · {pct:.0f}%",
                    "bad" if pct >= 100 else "warn" if pct >= 80 else "ok"),
                kpi("Câu hỏi hôm nay", sum(r["hom_nay"] for r in dung)),
                kpi("Câu hỏi tháng này", sum(r["thang"] for r in dung)),
                kpi("Trạng thái", "Đang bật" if ch["bat"] and ch["key"] else "Đang tắt")]
        for r in dung:
            r["chi_phi"] = round(r["chi_phi"], 4)
        return (["bat"] if ch["bat"] else [], ch["ten"], ch["model_chat"], ch["model_nhan_xet"], ch["tran_usd"],
                ch["luot_ngay"], key, kpis, dung, ch["vai_tro"], tk, ch["tai_khoan"], quyen,
                f"Đã lưu {ai.key_an(ch['key'])} · để trống là giữ mã này" if ch["key"] else "sk-...")

    @cb(Output("ai-msg", "children"), Output("ai-key", "value"), Output("ai-da-luu", "data"),
        Input("ai-luu", "n_clicks"), Input("ai-thu", "n_clicks"), Input("ai-xoa-key", "n_clicks"),
        State("ai-bat", "value"), State("ai-ten", "value"), State("ai-key", "value"),
        State("ai-model-chat", "value"), State("ai-model-nx", "value"), State("ai-tran", "value"),
        State("ai-luot", "value"), State("ai-vai-tro", "value"), State("ai-tai-khoan", "value"),
        prevent_initial_call=True)
    def _thao_tac(_l, _t, _x, bat, ten, key, m_chat, m_nx, tran, luot, vai_tro, tai_khoan):
        key, m_chat, m_nx = (key or "").strip(), (m_chat or "").strip(), (m_nx or "").strip()
        trig = ctx.triggered_id
        if trig == "ai-xoa-key":
            ai.luu_cau_hinh({"key": None}, current_user.username)
            return alert(f"Đã xoá mã API lưu trong app ({gio_viet_nam():%H:%M:%S}).", "ok"), "", time.time()
        if trig == "ai-thu":
            dung = key or ai.cau_hinh()["key"]
            if not dung:
                return alert("Dán mã API vào ô trước đã.", "warn"), no_update, no_update
            try:
                kq = [ai.thu_ket_noi(dung, m) for m in dict.fromkeys(x for x in (m_chat, m_nx) if x)]
                return alert(" ".join(kq) or "Mã hợp lệ.", "ok"), no_update, no_update
            except ai.LoiAI as e:
                return alert(str(e), "bad"), no_update, no_update
        if not (ten or "").strip() or not m_chat or not m_nx:
            return alert("Điền đủ tên trợ lý và hai model.", "warn"), no_update, no_update
        if not tran or float(tran) <= 0 or not luot or int(luot) < 1:
            return alert("Trần chi phí phải lớn hơn 0 và số câu mỗi ngày từ 1.", "warn"), no_update, no_update
        bo_qua_ma = bool(key) and not key.startswith("sk-")      # không phải mã OpenAI -> giữ mã cũ, vẫn lưu phần khác
        if bo_qua_ma:
            key = ""
        ai.luu_cau_hinh({"bat": "bat" in (bat or []), "ten": ten.strip(), "key": key, "model_chat": m_chat,
                         "model_nhan_xet": m_nx, "tran_usd": float(tran), "luot_ngay": int(luot),
                         "vai_tro": list(vai_tro or []), "tai_khoan": list(tai_khoan or [])},
                        current_user.username)
        ch = ai.cau_hinh()
        nhac = (" Ô mã API không phải mã OpenAI (phải bắt đầu bằng “sk-”) nên vẫn giữ mã đã lưu." if bo_qua_ma else
                " Chưa có mã API nên AI chưa chạy." if ch["bat"] and not ch["key"] else
                " Chưa mở quyền cho vai trò hay tài khoản nào nên chưa ai dùng được." if ch["bat"]
                and not (ch["vai_tro"] or ch["tai_khoan"]) else "")
        return alert(f"Đã lưu cấu hình ({gio_viet_nam():%H:%M:%S}). Tải lại trang (F5) để thấy nút chat "
                     f"và nút nhận xét.{nhac}", "warn" if nhac else "ok"), "", time.time()
