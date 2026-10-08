"""Nhập Báo cáo ngày bằng giọng nói - phần giao diện (logic ở `app/giong_noi.py`, ghi âm ở `assets/ghi_am.js`).

Tách khỏi `baocaongay.py` cho gọn (mẫu `phantich_tinh.py`): module mẹ nạp file này trong `layout()` / `register()`.
Nút micro nổi ở góc dưới màn hình (dùng nhiều nhất trên điện thoại). Nói xong hiện hộp "Kiểm tra trước khi lưu":
câu nghe được (sửa được), mỗi người một thẻ điền sẵn; ô trống = không đổi. Chỉ khi bấm Lưu mới ghi vào dữ liệu.
"""
from __future__ import annotations

from dash import ALL, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate
from flask_login import current_user

from app import giong_noi as gn
from app import tro_ly as ai
from app.ui.components import alert, modal
from app.ui.icons import icon
from app.ui.pages.baocaongay import _dung_chung, _ngay_hop_le, _phong_hop_le, nt_ten

SO = {"min": 0, "max": 999, "step": 1}


def duoc_dung() -> bool:
    """Có hiện nút micro không (đúng người + đúng phòng; chưa tính AI đã mở quyền hay chưa - bấm vào sẽ báo rõ)."""
    return current_user.is_authenticated and bool(gn.phong_duoc_dung(current_user))


def khung():
    ch = ai.cau_hinh()
    return html.Div([
        dcc.Store(id="bn-gn-kq"), dcc.Store(id="bn-gn-goc"),
        html.Div([
            html.Button([icon("edit", 16), html.Span("Gõ")], id="bn-gn-go", className="bn-gn-go",
                        title="Gõ hoặc đọc bằng micro của bàn phím, rồi để AI tự điền"),
            html.Button([icon("mic", 24), html.Span("Nói để nhập", className="gn-chu")], id="bn-gn-mic",
                        className="bn-gn-mic", title="Đọc báo cáo, AI tự điền các ô để bạn kiểm tra",
                        **{"data-engine": ch.get("giong") or "trinh_duyet", "data-openai": "1" if ch.get("key") else "0"}),
        ], className="bn-gn-nut"),
        modal("bn-gn", "Nhập báo cáo bằng giọng nói", [
            html.Div(id="bn-gn-msg"),
            html.Div([html.Label("Câu nghe được (sửa được, rồi bấm Phân tích lại)"),
                      dcc.Textarea(id="bn-gn-chu", maxLength=gn.TOI_DA_CHU, className="inp bn-gn-chu",
                                   placeholder="VD: Cẩm Tiên mục tiêu 3, đã thực hiện bán 2, dự kiến online sáng 2, "
                                               "chiều 1")], className="field rong"),
            html.Button([icon("refresh", 14), html.Span("Phân tích lại")], id="bn-gn-lai", className="btn nho"),
            html.Div(id="bn-gn-the", className="bn-gn-the"),
            html.Div("Ô để trống là không đổi. Đừng đọc tên khách hàng trong ghi chú.", className="desc"),
        ], nut_chinh="Lưu"),
    ], className="bn-gn-khung")


def _the(i: int, m: dict, ds: list[dict], dang_co: dict):
    """Một người = một thẻ: ô chọn người + sáu ô số + ghi chú, điền sẵn theo đề xuất."""
    acc = m.get("acc_norm")
    chua_chac = acc is None
    cu = dang_co.get(acc) or {}
    ghi = (", ".join(f"{gn.NHAN[c]} {cu[c]}" for c in gn.NHAN if c in cu) if cu else "chưa nhập gì hôm nay")
    return html.Div([
        html.Div(f"Nghe được: “{m['ten_noi']}”" + (" · hơn một người khớp, hãy chọn lại" if m.get("mo_ho") else
                                                   " · chưa tìm thấy người này, hãy chọn" if chua_chac else ""),
                 className="bn-gn-nghe"),
        dcc.Dropdown(id={"type": "bn-gn-ten", "i": i}, options=ds, value=acc, clearable=False,
                     placeholder="Chọn nhân sự", className="bn-gn-chon"),
        html.Div([html.Div([html.Label(gn.NHAN[c]),
                            dcc.Input(id={"type": "bn-gn-o", "i": i, "f": c}, type="number", className="inp",
                                      value=m["truong"].get(c), placeholder="–", **SO)], className="field")
                  for c in gn.NHAN], className="bn-gn-luoi"),
        dcc.Input(id={"type": "bn-gn-gc", "i": i}, type="text", className="inp", value=m.get("ghi_chu") or "",
                  placeholder="Ghi chú (để trống = giữ nguyên)", maxLength=400),
        html.Div(f"Đang có: {ghi}", className="desc bn-gn-co"),
    ], className="bn-gn-nguoi" + (" thieu" if chua_chac else ""))


def _dung_the(kq: dict) -> tuple[list, list]:
    if not kq["nguoi"]:
        return [html.Div("Chưa tách được người nào. Thử nói rõ tên và từng chỉ số, hoặc sửa câu ở trên rồi bấm "
                         "Phân tích lại.", className="desc")], []
    the = [_the(i, m, kq["ds"], kq["dang_co"]) for i, m in enumerate(kq["nguoi"])]
    goc = [{"ten_noi": m["ten_noi"], "acc_norm": m["acc_norm"], "truong": m["truong"], "ghi_chu": m["ghi_chu"]}
           for m in kq["nguoi"]]
    return the, goc


def register(app):
    @app.callback(Output("bn-gn", "className"), Output("bn-gn-chu", "value"), Output("bn-gn-the", "children"),
                  Output("bn-gn-goc", "data"), Output("bn-gn-msg", "children"),
                  Input("bn-gn-kq", "data"), Input("bn-gn-lai", "n_clicks"), Input("bn-gn-go", "n_clicks"),
                  Input("bn-gn-dong", "n_clicks"), Input("bn-gn-huy", "n_clicks"),
                  State("bn-gn-chu", "value"), State("bn-phong", "value"), State("bn-ngay", "date"),
                  prevent_initial_call=True)
    def _nghe(kq, _lai, go, _d, _h, chu, code, ngay):
        trig = ctx.triggered_id
        if trig in ("bn-gn-dong", "bn-gn-huy"):
            return "modal", no_update, no_update, no_update, ""
        if trig == "bn-gn-go":
            if not go:                      # nút được dựng lại cùng trang: không phải bấm thật
                raise PreventUpdate
            return "modal mo", "", [], [], ""
        phong, d = _phong_hop_le(code), _ngay_hop_le(ngay)
        if trig == "bn-gn-kq":
            if not isinstance(kq, dict):
                raise PreventUpdate
            try:
                chu = (kq.get("van_ban") or "") if kq.get("loai") == "chu" else \
                    gn.van_ban_tu_am(kq.get("b64") or "", kq.get("mime"), phong, d, current_user)
            except ai.LoiAI as e:
                return "modal mo", "", [], [], alert(str(e), "bad")
        elif not (chu or "").strip():
            return no_update, no_update, [], [], alert("Chưa có câu nào để phân tích.", "warn")
        try:
            the, goc = _dung_the(gn.phan_tich(chu, phong, d, current_user))
        except ai.LoiAI as e:
            return "modal mo", chu, [], [], alert(str(e), "bad")
        return "modal mo", chu, the, goc, ""

    @app.callback(Output("bn-gn", "className", allow_duplicate=True), Output("bn-gn-msg", "children", allow_duplicate=True),
                  Output("bn-msg", "children", allow_duplicate=True), Output("bn-da-luu", "data", allow_duplicate=True),
                  Input("bn-gn-ok", "n_clicks"), State("bn-gn-goc", "data"),
                  State({"type": "bn-gn-ten", "i": ALL}, "value"), State({"type": "bn-gn-ten", "i": ALL}, "id"),
                  State({"type": "bn-gn-o", "i": ALL, "f": ALL}, "value"),
                  State({"type": "bn-gn-o", "i": ALL, "f": ALL}, "id"),
                  State({"type": "bn-gn-gc", "i": ALL}, "value"), State({"type": "bn-gn-gc", "i": ALL}, "id"),
                  State("bn-phong", "value"), State("bn-ngay", "date"), State("bn-toi-la", "value"),
                  prevent_initial_call=True)
    def _luu(n, goc, ten, ten_id, so, so_id, gc, gc_id, code, ngay, toi_la):
        if not n:
            raise PreventUpdate
        phong, d = _phong_hop_le(code), _ngay_hop_le(ngay)
        muc = []
        for t, ti in zip(ten, ten_id):
            i = ti["i"]
            truong = {si["f"]: int(v) for v, si in zip(so, so_id) if si["i"] == i and v not in (None, "")}
            ghi = next((v for v, gi in zip(gc, gc_id) if gi["i"] == i), "") or ""
            muc.append({"acc_norm": t, "truong": truong, "ghi_chu": ghi.strip(),
                        "ten_noi": (goc[i]["ten_noi"] if goc and i < len(goc) else "")})
        try:
            kq = gn.luu_nhieu(muc, phong, d, current_user, ghi_ten=nt_ten(toi_la) if _dung_chung() else None, goc=goc)
        except ai.LoiAI as e:
            return no_update, alert(str(e), "bad"), no_update, no_update
        if kq["loi"]:
            da = f"Đã lưu {len(kq['da'])} người. " if kq["da"] else ""
            return "modal mo", alert(da + " ".join(kq["loi"]), "bad"), no_update, (_luc() if kq["da"] else no_update)
        if not kq["da"]:
            return no_update, alert("Chưa có ô nào để lưu.", "warn"), no_update, no_update
        return "modal", "", alert(f"Đã lưu {len(kq['da'])} người, {kq['n_o']} ô.", "ok"), _luc()


def _luc() -> str:
    from app.thoi_gian import gio_viet_nam
    return gio_viet_nam().isoformat()
