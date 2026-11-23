"""Trang "Thuyết trình AI" (`/thuyettrinh`, chỉ Ban Giám đốc - `duoc_cau_hinh`), khối Kinh doanh (chủ app chốt 23/11/2026, bản đầu).

Bấm "Tạo bài thuyết trình" (hoặc nói "thuyết trình"): máy chủ dựng các slide từ số liệu của app (`app/thuyet_trinh.py`) rồi nhờ AI viết lời nói (`app/thuyet_trinh_ai.py`).
Trình duyệt đọc to từng slide bằng giọng sẵn có (`assets/thuyet_trinh.js`, miễn phí), tự chuyển slide, nghe giọng nói để ra lệnh (tiếp, lùi, dừng, nói lại, slide N) hoặc đặt câu hỏi
về slide đang xem; câu hỏi gửi lên máy chủ, AI trả lời bằng chính bộ công cụ số liệu của Fox rồi trình duyệt đọc câu trả lời. Mọi callback kiểm quyền ở máy chủ.
"""
from __future__ import annotations

from dash import ClientsideFunction, Input, Output, State, clientside_callback, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate
from flask_login import current_user

from app import thuyet_trinh as tt, thuyet_trinh_ai as ai, tro_ly
from app.ui.components import alert, callback_can_quyen, card
from app.ui.icons import icon

QUYEN = "duoc_cau_hinh"
TOC_DO = (("Chậm", "0.85"), ("Vừa", "1"), ("Nhanh", "1.15"), ("Rất nhanh", "1.3"))
TOI_DA_LICH_SU = 12


def topbar():
    return [html.Div([html.H1("Thuyết trình AI"), html.Div("AI dựng slide từ số liệu khối Kinh doanh và thuyết trình bằng giọng nói; bấm lùi hoặc hỏi để nghe giải thích sâu hơn", className="sub")])]


def _cho_phep() -> bool:
    return bool(getattr(current_user, QUYEN, False))


def _nut(id_: str, chu, lop: str = "btn", **kw):
    return html.Button(chu, id=id_, n_clicks=0, className=lop, **kw)


# ------------------------------------------------------------------ slide
def _kpi(k: dict) -> html.Div:
    return html.Div([html.Div(k["nhan"], className="tt-kpi-nhan"), html.Div(k["gia_tri"], className="tt-kpi-so"), html.Div(k["phu"], className="tt-kpi-phu")], className=f"tt-kpi {k.get('mau') or ''}".strip())


def _bang(b: dict) -> html.Table:
    return html.Table([html.Thead(html.Tr([html.Th(c) for c in b["cot"]])), html.Tbody([html.Tr([html.Td(str(x)) for x in d]) for d in b["dong"]])], className="tt-bang")


def ve_slide(s: dict, i: int, n: int, bai: dict) -> html.Div:
    """Một slide: tiêu đề, hàng chỉ số (nếu có), biểu đồ hoặc bảng, các ý chính; chân slide ghi lời nói do AI hay do lời mẫu."""
    diem = html.Ul([html.Li(d) for d in s["diem"]], className="tt-diem")
    if s["kpi"]:
        than = [html.Div([_kpi(k) for k in s["kpi"]], className="tt-kpi-hang"), diem]
    elif s["hinh"]:
        than = [html.Div([dcc.Graph(figure=s["hinh"], config={"displayModeBar": False}, className="tt-do-thi"), diem], className="tt-hai-cot")]
    elif s["bang"]:
        than = [_bang(s["bang"]), diem]
    else:
        than = [diem]
    chan = "Lời nói do AI viết, số liệu do hệ thống tính." if s["nguon_loi"] == "ai" else "Lời nói mẫu do hệ thống viết (số liệu do hệ thống tính)."
    tam = html.Div("Số của ngày cuối còn tạm tính.", className="tt-tam") if bai.get("tam_tinh") and i == 0 else None
    return html.Div([html.Div([html.Span(f"{i + 1}/{n}", className="tt-so"), html.H2(s["tieu_de"])], className="tt-dau"), *than, tam, html.Div(chan, className="tt-chan")], className="tt-slide")


def _bong(lich_su: list[dict]) -> list:
    if not lich_su:
        return [html.Div("Chưa có câu hỏi. Bấm mic và nói, hoặc gõ câu hỏi về slide đang xem.", className="desc")]
    return [html.Div([html.Div(("Bạn" if m["role"] == "user" else "AI") + (f" · {m['slide']}" if m.get("slide") else ""), className="tt-bong-ai"), html.Div(m["content"])],
                     className=f"tt-bong {'hoi' if m['role'] == 'user' else 'dap'}") for m in lich_su[-TOI_DA_LICH_SU:]]


# ------------------------------------------------------------------ giao diện
def layout():
    giong = html.Select([html.Option(ten, value=v, selected=v == "1") for ten, v in TOC_DO], id="tt-toc-do", className="tt-chon")
    dieu_khien = html.Div([
        _nut("tt-mic", [icon("mic", 15), html.Span("Nói yêu cầu")], "btn primary"),
        _nut("tt-tao", "Tạo bài thuyết trình"),
        html.Span(className="tt-ngan"),
        _nut("tt-lui", "‹ Lùi"), _nut("tt-phat", "▶ Phát"), _nut("tt-tiep", "Tiếp ›"),
        dcc.Checklist(id="tt-tu-chuyen", options=[{"label": " Tự chuyển slide", "value": "auto"}], value=["auto"], className="tt-tick"),
        html.Label(["Tốc độ đọc ", giong], className="tt-nhan"),
        _nut("tt-toan-man", "Toàn màn hình"),
    ], className="tt-dieu-khien")
    hoi = html.Div([dcc.Input(id="tt-cau-hoi", type="text", placeholder="Hỏi về slide đang xem, ví dụ: vì sao IBB5 hụt nhiều nhất?", debounce=False, n_submit=0, className="tt-o-hoi"),
                    _nut("tt-hoi", "Hỏi", "btn primary")], className="tt-hang-hoi")
    return html.Div([
        dcc.Store(id="tt-bai"), dcc.Store(id="tt-i", data=0), dcc.Store(id="tt-hoi-thoai", data=[]), dcc.Store(id="tt-tra-loi"), dcc.Store(id="tt-d1"), dcc.Store(id="tt-d2"),
        dcc.Input(id="tt-nhay", type="text", value="", style={"display": "none"}),
        card([dieu_khien, html.Div(id="tt-js-bao", className="desc"), dcc.Loading(html.Div(id="tt-thongbao"), type="dot")], title="Điều khiển",
             desc="Nói thử: “thuyết trình”, “tiếp”, “lùi”, “dừng”, “đọc tiếp”, “nói lại”, “slide ba”. Câu khác sẽ được hiểu là câu hỏi về slide đang xem. Giọng đọc và nghe là của trình duyệt (dùng Chrome hoặc Edge)."),
        html.Div([html.Div(html.Div("Chưa có bài thuyết trình. Bấm “Tạo bài thuyết trình” hoặc “Nói yêu cầu” rồi nói “thuyết trình”.", className="desc"), id="tt-slide", className="tt-man"),
                  html.Div([html.H3("Hỏi AI về slide này"), hoi, html.Div(_bong([]), id="tt-hoi-thoai-hien", className="tt-bong-ds")], className="tt-hoi-khung")], id="tt-khung", className="tt-khung"),
        html.Div(id="tt-loi", style={"display": "none"}),
    ], className="tt-trang")


# ------------------------------------------------------------------ callback
def cb_tao(_n):
    if not _cho_phep():
        raise PreventUpdate
    try:
        bai = tt.dung_bai(current_user)
    except ValueError as e:
        return no_update, no_update, no_update, alert(str(e), "bad")
    except Exception as e:                                   # lỗi nguồn dữ liệu không được làm trang đứng
        return no_update, no_update, no_update, alert(f"Chưa dựng được bài thuyết trình ({type(e).__name__}). Xem lại dữ liệu rồi thử lại.", "bad")
    ai.viet_loi(current_user, bai)
    _ghi("thuyet_trinh", f"ngay={bai['ngay']} slide={len(bai['slides'])} ai={bai['dung_ai']}")
    tin = f"Đã dựng {len(bai['slides'])} slide, số liệu tới ngày {bai['ngay_hien']}. " + ("Lời nói do AI viết." if bai["dung_ai"] and not bai["ly_do_luat"] else
                                                                                       f"Đang dùng lời nói mẫu một phần hoặc toàn bộ. Lý do: {bai['ly_do_luat']}")
    return bai, 0, [], alert(tin, "ok" if bai["dung_ai"] and not bai["ly_do_luat"] else "warn")


def cb_chuyen(_lui, _tiep, nhay, i, bai):
    if not _cho_phep() or not bai:
        raise PreventUpdate
    n = len(bai["slides"])
    if ctx.triggered_id == "tt-nhay":
        try:
            moi = int(str(nhay).split(":")[0]) - 1
        except ValueError:
            raise PreventUpdate
    elif ctx.triggered_id in ("tt-lui", "tt-tiep") and ctx.triggered[0]["value"]:
        moi = (i or 0) + (1 if ctx.triggered_id == "tt-tiep" else -1)
    else:
        raise PreventUpdate
    moi = max(0, min(n - 1, moi))
    if moi == (i or 0):
        raise PreventUpdate
    return moi


def cb_ve(bai, i):
    if not _cho_phep() or not bai:
        raise PreventUpdate
    n, i = len(bai["slides"]), max(0, min(int(i or 0), len(bai["slides"]) - 1))
    s = bai["slides"][i]
    return ve_slide(s, i, n, bai), tt.cho_giong(s["loi_noi"]), i == 0, i >= n - 1


def cb_hoi(_n, _enter, cau, bai, i, lich_su):
    if not _cho_phep() or not bai or not (cau or "").strip():
        raise PreventUpdate
    i = max(0, min(int(i or 0), len(bai["slides"]) - 1))
    lich_su = list(lich_su or [])
    nhan = bai["slides"][i]["tieu_de"]
    try:
        tra_loi = ai.hoi(current_user, bai, i, cau, [{"role": m["role"], "content": m["content"]} for m in lich_su])
        _ghi("thuyet_trinh_hoi", f"slide={bai['slides'][i]['id']} {cau.strip()[:150]}")
    except tro_ly.LoiAI as e:
        tra_loi = str(e)
    except Exception as e:
        tra_loi = f"Chưa trả lời được ({type(e).__name__}). Bạn hỏi lại giúp mình nhé."
    lich_su += [{"role": "user", "content": cau.strip()[:500], "slide": nhan}, {"role": "assistant", "content": tra_loi, "slide": nhan}]
    return lich_su[-2 * TOI_DA_LICH_SU:], "", {"n": len(lich_su), "text": tt.cho_giong(tra_loi)}


def _ghi(hanh_dong: str, chi_tiet: str) -> None:
    try:
        from app.auth import ghi_log
        ghi_log(hanh_dong, chi_tiet[:200])
    except Exception:                                         # nhật ký lỗi không được làm hỏng bài thuyết trình
        pass


def register(app):
    """Callback nào cũng kiểm `duoc_cau_hinh` ở máy chủ (`callback_can_quyen`). Phần đọc to và nghe giọng nói chạy ở trình duyệt (`assets/thuyet_trinh.js`)."""
    cb = callback_can_quyen(app, QUYEN)
    cb(Output("tt-bai", "data"), Output("tt-i", "data"), Output("tt-hoi-thoai", "data"), Output("tt-thongbao", "children"), Input("tt-tao", "n_clicks"), prevent_initial_call=True,
       running=[(Output("tt-tao", "disabled"), True, False), (Output("tt-phat", "disabled"), True, False)])(cb_tao)
    cb(Output("tt-i", "data", allow_duplicate=True), Input("tt-lui", "n_clicks"), Input("tt-tiep", "n_clicks"), Input("tt-nhay", "value"), State("tt-i", "data"), State("tt-bai", "data"),
       prevent_initial_call=True)(cb_chuyen)
    cb(Output("tt-slide", "children"), Output("tt-loi", "children"), Output("tt-lui", "disabled"), Output("tt-tiep", "disabled"), Input("tt-bai", "data"), Input("tt-i", "data"))(cb_ve)
    cb(Output("tt-hoi-thoai", "data", allow_duplicate=True), Output("tt-cau-hoi", "value"), Output("tt-tra-loi", "data"), Input("tt-hoi", "n_clicks"), Input("tt-cau-hoi", "n_submit"),
       State("tt-cau-hoi", "value"), State("tt-bai", "data"), State("tt-i", "data"), State("tt-hoi-thoai", "data"), prevent_initial_call=True,
       running=[(Output("tt-hoi", "disabled"), True, False)])(cb_hoi)
    cb(Output("tt-hoi-thoai-hien", "children"), Input("tt-hoi-thoai", "data"))(lambda ls: _bong(ls or []))
    clientside_callback(ClientsideFunction(namespace="tt", function_name="noiSlide"), Output("tt-d1", "data"), Input("tt-loi", "children"))
    clientside_callback(ClientsideFunction(namespace="tt", function_name="noiTraLoi"), Output("tt-d2", "data"), Input("tt-tra-loi", "data"))
