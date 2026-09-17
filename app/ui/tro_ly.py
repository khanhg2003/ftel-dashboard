"""Giao diện trợ lý AI: thẻ Dự báo & nhận xét trên các trang, khung chat nổi, tab cấu hình ở Quản trị."""
from __future__ import annotations

import time

import dash_ag_grid as dag
from dash import Input, Output, State, ctx, dcc, html, no_update
from flask_login import current_user

from app import tro_ly as ai
from app import tro_ly_du_lieu as dl
from app.auth import ghi_log
from app.du_bao import AN_TOAN, RUI_RO, TANG_TOC
from app.thoi_gian import chu_gio_vn, gio_viet_nam
from app.ui.components import alert, callback_can_quyen, card, kpi
from app.ui.icons import icon

AN = {"display": "none"}
MAU_DANH_GIA = {AN_TOAN: "ok", TANG_TOC: "warn", RUI_RO: "bad"}
MODEL_GOI_Y = ["gpt-5-mini", "gpt-5", "gpt-5-nano", "gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini"]


# Con cáo cam - hình đại diện của trợ lý. Con ngươi (.cao-nguoi) nhìn theo chuột: assets/cao_nhin_theo.js
SVG_CAO = """<svg class="cao" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
<path d="M9 5 27 19 13 31Z" fill="#E8621A"/><path d="M55 5 37 19 51 31Z" fill="#E8621A"/>
<path d="M13 12 22 20 15 26Z" fill="#4A2A1C"/><path d="M51 12 42 20 49 26Z" fill="#4A2A1C"/>
<path d="M7 31Q9 15 32 15Q55 15 57 31Q57 45 32 59Q7 45 7 31Z" fill="#F7892F"/>
<path d="M7 33Q19 36 32 59Q13 49 7 33Z" fill="#FFF3E6"/><path d="M57 33Q45 36 32 59Q51 49 57 33Z" fill="#FFF3E6"/>
<path d="M23 43Q32 36 41 43Q37 54 32 59Q27 54 23 43Z" fill="#FFF3E6"/>
<g class="cao-mat"><ellipse cx="22.5" cy="33" rx="5.2" ry="5.6" fill="#fff"/><ellipse cx="41.5" cy="33" rx="5.2" ry="5.6" fill="#fff"/>
<g class="cao-nguoi" data-cx="22.5" data-cy="33"><circle cx="22.5" cy="33" r="3" fill="#2B1B14"/><circle cx="23.6" cy="31.9" r="1" fill="#fff"/></g>
<g class="cao-nguoi" data-cx="41.5" data-cy="33"><circle cx="41.5" cy="33" r="3" fill="#2B1B14"/><circle cx="42.6" cy="31.9" r="1" fill="#fff"/></g></g>
<ellipse cx="32" cy="50" rx="3.2" ry="2.3" fill="#2B1B14"/>
<path d="M29 54Q32 56.5 35 54" stroke="#2B1B14" stroke-width="1.2" fill="none" stroke-linecap="round"/>
</svg>"""


def con_cao(co: str = "nho"):
    return dcc.Markdown(SVG_CAO, dangerously_allow_html=True, className=f"cao-boc {co}")


def _cau_hinh_an_toan() -> dict:
    try:
        return ai.cau_hinh()
    except Exception:                   # database lỗi thì coi như tắt AI, không làm hỏng trang
        return dict(ai.MAC_DINH)


# ------------------------------------------------------------------ thẻ dự báo & nhận xét
def the_ai(prefix: str, tieu_de: str, mo_ta: str, truoc=None):
    """Thẻ dùng chung: phần dự báo (luôn hiện) + nút nhận xét của trợ lý (ẩn khi AI tắt)."""
    ch = _cau_hinh_an_toan()
    return html.Div([
        html.Div([
            html.Div([html.H3([con_cao(), tieu_de]),
                      html.Div(mo_ta, className="desc")], className="the-ten"),
            html.Button([html.Span("✨"), html.Span(f"{ch['ten']} nhận xét", id=f"{prefix}-ai-nhan")],
                        id=f"{prefix}-ai-tao", className="btn primary",
                        style={} if ch["bat"] else AN,
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
    @app.callback(Output(f"{prefix}-ai-kq", "children"), Output(f"{prefix}-ai-nhan", "children"),
                  Input(f"{prefix}-ai-tao", "n_clicks"), *[Input(i, p) for i, p in inputs])
    def _nhan_xet(_n, *gia_tri):
        ch = _cau_hinh_an_toan()
        if not ch["bat"]:
            return "", no_update
        try:
            khoa, du_lieu = ngu_canh(current_user, *gia_tri)
            ban = ai.nhan_xet_da_luu(loai, khoa)
            if ctx.triggered_id == f"{prefix}-ai-tao":
                ban = ai.tao_nhan_xet(current_user, loai, khoa, du_lieu(), yeu_cau)
            if not ban:
                return (html.Div(f"Bấm “{ch['ten']} nhận xét” để trợ lý đọc số của kỳ đang xem, chỉ ra điểm "
                                 "nổi bật, rủi ro và việc nên làm.", className="ai-goi-y"),
                        f"{ch['ten']} nhận xét")
            return noi_dung_nhan_xet(ban, ch["ten"]), "Tạo lại nhận xét"
        except ai.LoiAI as e:
            return alert(str(e), "warn"), no_update


def nhan_xet_anh(tu: str | None, den: str | None, chi_nhanh: str | None) -> tuple[str, str] | None:
    """(tiêu đề, nội dung) nhận xét ngắn in dưới ảnh Báo cáo Tổng. AI tắt / lỗi thì ảnh vẫn xuất bình thường."""
    ch = _cau_hinh_an_toan()
    if not ch["bat"]:
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
             "cellStyle": {"fontWeight": "650"}},
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


def dong_du_bao(r: dict | None, ten: str = "Phòng"):
    """Một dòng tóm tắt dự báo (Báo cáo phòng, Phân tích)."""
    if not r:
        return html.Div()
    if not r.get("mt"):
        return html.Div(f"{ten} chưa có mục tiêu tháng nên chưa dự báo được % hoàn thành.", className="desc")
    return html.Div([
        kpi("Dự báo cuối tháng", f"{r['du_bao']:,}".replace(",", "."), f"mục tiêu {r['mt']:,}".replace(",", "."),
            MAU_DANH_GIA.get(r["danh_gia"], "")),
        kpi("% mục tiêu dự báo", f"{r['pct_mt']}%", r["danh_gia"], MAU_DANH_GIA.get(r["danh_gia"], "")),
        kpi("Bình quân mỗi ngày", str(r["tb_ngay"]).replace(".", ","), f"luỹ kế {r['luy_ke']:,}".replace(",", ".")),
        kpi("Cần mỗi ngày còn lại", f"{r['can_moi_ngay'] or 0:,}".replace(",", "."), "để đủ mục tiêu tháng"),
    ], className="kpi-row", style={"marginBottom": "6px"})


MO_TA_DU_BAO = ("Dự báo = luỹ kế + bình quân mỗi ngày × số ngày còn lại × hệ số cuối tháng (nhịp phần cuối "
                "tháng trước so với đầu tháng). An toàn ≥ 100% mục tiêu · Cần tăng tốc 90-99% · Rủi ro dưới 90%.")


# ------------------------------------------------------------------ khung chat nổi
def khung_chat():
    try:
        if not current_user.is_authenticated:
            return html.Div()
        ch = ai.cau_hinh()
    except Exception:
        return html.Div()
    if not ch["bat"]:
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
            html.Div(id="ai-chat-log", className="ai-log"),
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


GOI_Y_CAU_HOI = ["Tóm tắt kết quả tháng này so với mục tiêu", "Phòng nào có nguy cơ không đạt mục tiêu?",
                 "Nhân sự nào cần chú ý nhất?"]


# ------------------------------------------------------------------ tab Quản trị → Trợ lý AI
def pane_cau_hinh(tab: str):
    o = lambda label, ctl: html.Div([html.Label(label), ctl], className="field rong")   # noqa: E731
    return html.Div(id="ai-pane", style={} if tab == "ai" else AN, children=[
        dcc.Store(id="ai-da-luu"),
        html.Datalist(id="ai-ds-model", children=[html.Option(value=m) for m in MODEL_GOI_Y]),
        card([
            dcc.Checklist(id="ai-bat", options=[{"label": " Bật trợ lý AI cho mọi tài khoản", "value": "bat"}],
                          value=[], className="ai-bat"),
            html.Div([
                o("Tên trợ lý", dcc.Input(id="ai-ten", type="text", className="inp", maxLength=20)),
                o("Mã API ChatGPT (OpenAI)", dcc.Input(id="ai-key", type="password", className="inp",
                                                       autoComplete="off", placeholder="sk-...")),
                o("Model cho chat", dcc.Input(id="ai-model-chat", type="text", className="inp", list="ai-ds-model")),
                o("Model cho nhận xét", dcc.Input(id="ai-model-nx", type="text", className="inp", list="ai-ds-model")),
                o("Trần chi phí mỗi tháng (USD)", dcc.Input(id="ai-tran", type="number", min=0.5, step=0.5,
                                                            className="inp")),
                o("Số câu mỗi người / ngày", dcc.Input(id="ai-luot", type="number", min=1, step=1, className="inp")),
            ], className="form-grid"),
            html.Div(id="ai-key-hien", className="desc", style={"marginTop": "10px"}),
            html.Div([
                html.Button([icon("check", 14), html.Span("Lưu cấu hình")], id="ai-luu", className="btn primary"),
                html.Button([icon("refresh", 14), html.Span("Thử kết nối")], id="ai-thu", className="btn"),
                html.Div(className="grow"),
                html.Button([icon("trash", 14), html.Span("Xoá mã API")], id="ai-xoa-key", className="btn nguy-hiem"),
            ], className="toolbar", style={"marginTop": "14px", "marginBottom": 0}),
            html.Div(id="ai-msg", style={"marginTop": "12px"}),
            html.Div("Dán mã lấy ở platform.openai.com → API keys rồi bấm Lưu. Mã được mã hoá trước khi lưu, sau đó "
                     "chỉ hiện 4 ký tự cuối. Quản trị (BGĐ) không giới hạn số câu; hết trần chi phí tháng thì AI tự "
                     "tạm dừng tới đầu tháng sau (hoặc nâng trần). Chi phí là ước tính theo bảng giá OpenAI, "
                     "số chính xác xem ở trang Usage của OpenAI.", className="desc", style={"marginTop": "8px"}),
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

    # gửi: hiện ngay câu hỏi (máy khách), máy chủ trả lời sau
    app.clientside_callback(
        """function(_n, _goi_y, chu, ls) {
            const trig = (window.dash_clientside.callback_context.triggered[0] || {}).prop_id || '';
            const nu = window.dash_clientside.no_update;
            if (trig.startsWith('{')) {
                const t = window.dash_clientside.callback_context.triggered[0];
                if (!t || !t.value) { return [nu, nu]; }
                const i = JSON.parse(trig.split('.')[0]).i;
                chu = document.querySelectorAll('.ai-goi-y-cau')[i].innerText;
            }
            chu = (chu || '').trim();
            if (!chu) { return [nu, nu]; }
            return [{id: Date.now(), q: chu}, ''];
        }""",
        Output("ai-chat-cho", "data"), Output("ai-chat-o", "value"),
        Input("ai-chat-gui", "n_clicks"), Input({"loai": "ai-goi-y", "i": "ALL"}, "n_clicks"),
        State("ai-chat-o", "value"), State("ai-chat-ls", "data"), prevent_initial_call=True)

    # Enter để gửi, Shift+Enter xuống dòng
    app.clientside_callback(
        """function(id) {
            const o = document.getElementById('ai-chat-o');
            if (o && !o.__ftel) {
                o.__ftel = true;
                o.addEventListener('keydown', function (e) {
                    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); document.getElementById('ai-chat-gui').click(); }
                });
            }
            return window.dash_clientside.no_update;
        }""",
        Output("ai-chat-cuon", "data", allow_duplicate=True), Input("ai-chat-o", "id"), prevent_initial_call="initial_duplicate")

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
            tra_loi = ai.chat(current_user, [m for m in ls if not m.get("loi")], hoi["content"],
                              dl.ngu_canh_chat(current_user, duong_dan, ky), dl.cong_cu(current_user),
                              lambda ten, ts: dl.chay_cong_cu(current_user, ten, ts))
            dap = {"role": "assistant", "content": tra_loi}
        except ai.LoiAI as e:
            dap = {"role": "assistant", "content": str(e), "loi": True}
        except Exception as e:                                 # pragma: no cover - lỗi lạ vẫn báo gọn
            ghi_log("ai_loi", f"{type(e).__name__}: {str(e)[:200]}")
            dap = {"role": "assistant", "content": "Có lỗi khi lấy số, bạn thử lại hoặc hỏi cách khác.", "loi": True}
        return (ls + [hoi, dap])[-30:]

    @app.callback(Output("ai-chat-log", "children"), Input("ai-chat-ls", "data"), Input("ai-chat-cho", "data"))
    def _ve(ls, cho):
        ten = _cau_hinh_an_toan()["ten"]
        ls = ls or []
        tin = [_tin(m, ten) for m in ls]
        if cho and not any(m.get("id") == cho["id"] for m in ls):
            tin += [_tin({"role": "user", "content": cho["q"]}, ten),
                    html.Div([html.I(), html.I(), html.I()], className="ai-tin ai-ban ai-dang-go")]
        if not tin:
            tin = [html.Div([html.Div(ten, className="ai-ten"),
                             html.Div(f"Chào {current_user.ho_ten}! Mình là {ten}, tra số bán và NSLĐ theo đúng quyền "
                                      "của bạn. Thử hỏi:")], className="ai-tin ai-ban"),
                   *[html.Button(c, id={"loai": "ai-goi-y", "i": i}, className="ai-goi-y-cau")
                     for i, c in enumerate(GOI_Y_CAU_HOI)]]
        return tin

    app.clientside_callback(
        """function(_) {
            setTimeout(function () { const l = document.getElementById('ai-chat-log'); if (l) l.scrollTop = l.scrollHeight; }, 50);
            return window.dash_clientside.no_update;
        }""",
        Output("ai-chat-cuon", "data"), Input("ai-chat-log", "children"), prevent_initial_call=True)

    # ---------------- Quản trị → Trợ lý AI
    cb = callback_can_quyen(app, "duoc_cau_hinh")

    @cb(Output("ai-pane", "style"), Input("qt-tab", "value"), prevent_initial_call=True)
    def _tab(tab):
        return {} if tab == "ai" else AN

    @cb(Output("ai-bat", "value"), Output("ai-ten", "value"), Output("ai-model-chat", "value"),
        Output("ai-model-nx", "value"), Output("ai-tran", "value"), Output("ai-luot", "value"),
        Output("ai-key-hien", "children"), Output("ai-dung-kpi", "children"), Output("ai-dung-grid", "rowData"),
        Input("qt-tab", "value"), Input("ai-da-luu", "data"))
    def _nap(tab, _luu):
        if tab != "ai":
            return (no_update,) * 9
        ch = ai.cau_hinh()
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
        kpis = [kpi("Chi phí tháng này", f"${chi_phi:.2f}", f"trần ${ch['tran_usd']:g} · {pct:.0f}%",
                    "bad" if pct >= 100 else "warn" if pct >= 80 else "ok"),
                kpi("Câu hỏi hôm nay", sum(r["hom_nay"] for r in dung)),
                kpi("Câu hỏi tháng này", sum(r["thang"] for r in dung)),
                kpi("Trạng thái", "Đang bật" if ch["bat"] and ch["key"] else "Đang tắt")]
        for r in dung:
            r["chi_phi"] = round(r["chi_phi"], 4)
        return (["bat"] if ch["bat"] else [], ch["ten"], ch["model_chat"], ch["model_nhan_xet"], ch["tran_usd"],
                ch["luot_ngay"], key, kpis, dung)

    @cb(Output("ai-msg", "children"), Output("ai-key", "value"), Output("ai-da-luu", "data"),
        Input("ai-luu", "n_clicks"), Input("ai-thu", "n_clicks"), Input("ai-xoa-key", "n_clicks"),
        State("ai-bat", "value"), State("ai-ten", "value"), State("ai-key", "value"),
        State("ai-model-chat", "value"), State("ai-model-nx", "value"), State("ai-tran", "value"),
        State("ai-luot", "value"), prevent_initial_call=True)
    def _thao_tac(_l, _t, _x, bat, ten, key, m_chat, m_nx, tran, luot):
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
        if key and not key.startswith("sk-"):
            return alert("Mã API OpenAI bắt đầu bằng “sk-”. Kiểm tra lại mã vừa dán.", "warn"), no_update, no_update
        ai.luu_cau_hinh({"bat": "bat" in (bat or []), "ten": ten.strip(), "key": key, "model_chat": m_chat,
                         "model_nhan_xet": m_nx, "tran_usd": float(tran), "luot_ngay": int(luot)},
                        current_user.username)
        ch = ai.cau_hinh()
        nhac = " Chưa có mã API nên AI chưa chạy." if ch["bat"] and not ch["key"] else ""
        return alert(f"Đã lưu cấu hình ({gio_viet_nam():%H:%M:%S}). Tải lại trang (F5) để thấy nút chat "
                     f"và nút nhận xét.{nhac}", "warn" if nhac else "ok"), "", time.time()
