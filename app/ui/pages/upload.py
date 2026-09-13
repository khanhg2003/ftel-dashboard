"""Trang nạp dữ liệu: chọn nhiều file -> nhận diện loại -> xem trước -> lưu một lần.

Gộp một lần lưu vì mỗi ngày đều nạp 3 file bán hàng (đầu tháng thêm NSLĐ): một lượt chọn,
một bảng kết quả, thay cho bốn lượt thao tác giống hệt nhau.
"""
from __future__ import annotations

import base64
from datetime import date, datetime
from pathlib import Path

import dash_ag_grid as dag
from dash import Input, Output, State, dcc, html, no_update
from flask_login import current_user

from app.auth import ghi_log
from app.config import GIOI_HAN_NAP_MB, UPLOAD_DIR
from app.db import session_scope
from app.ingest.commit import commit_result, file_hash, thang_tu_ten_file
from app.ingest.loader import load_file
from app.metrics import cac_thang_co_du_lieu
from app.ui.components import alert, badge, card
from app.ui.icons import icon

MAX_PREVIEW = 20
TEN_DE_HIEU = {"internet": "Internet", "fptplay": "Truyền hình / FPT Play",
               "camera": "Camera", "nhan_su": "Nhân sự (NSLĐ)",
               "danh_muc_nv": "Danh mục nhân viên"}


def topbar():
    return [html.Div([html.H1("Nạp dữ liệu"),
                      html.Div("Internet · Truyền hình · Camera · NSLĐ",
                               className="sub")]),
            html.Div(className="spacer"),
            html.Div(id="up-badge")]


def layout():
    return html.Div([
        # Nội dung file giữ ở trình duyệt và gửi kèm cả lúc xem trước lẫn lúc lưu: trên Vercel
        # hai thao tác có thể chạy ở hai máy chủ khác nhau nên không dựa vào file tạm.
        dcc.Store(id="up-hang-doi"),
        dcc.Store(id="up-gioi-han", data=GIOI_HAN_NAP_MB),
        card([
            dcc.Upload(id="up-file", multiple=True, className="upload-zone", children=html.Div([
                html.Div("⬆", style={"fontSize": "26px", "marginBottom": "6px"}),
                html.Div([html.B("Chọn file"), " hoặc kéo thả · chọn nhiều file cùng lúc"]),
                html.Div("Định dạng .xlsx hoặc .csv",
                         style={"fontSize": "12px", "marginTop": "4px"})])),
            html.Div(id="up-dung-luong", className="desc", style={"marginTop": "8px"}),
            html.Div(style={"height": "6px"}),
            html.Div([
                html.Div([html.Label("Tháng của file nhân sự"),
                          dcc.Dropdown(id="up-thang", options=_thang_options(), value=None,
                                       placeholder="Chọn tháng", clearable=True,
                                       style={"width": "190px"})],
                         className="field"),
                html.Div("Ba file bán hàng tự lấy ngày trong file, không cần chọn tháng.",
                         className="desc", style={"margin": 0, "alignSelf": "center",
                                                  "maxWidth": "42ch"}),
                html.Div(className="grow"),
                html.Button([icon("save", 14), html.Span("Lưu tất cả vào hệ thống")],
                            id="up-commit", className="btn primary", disabled=True),
            ], className="toolbar"),
        ], title="Bước 1 · Chọn file",
            desc="Loại dữ liệu được nhận diện theo tên cột, nên đổi thứ tự hay thêm bớt cột "
                 "vẫn đọc đúng."),
        dcc.Loading(html.Div(id="up-ketqua")),
        html.Div(id="up-commit-ketqua"),
    ])


def _thang_options() -> list[dict]:
    """Danh sách tháng để chọn: 12 tháng gần đây + các tháng đã có dữ liệu."""
    hom_nay = date.today()
    ds = []
    for i in range(12):
        y, m = divmod(hom_nay.year * 12 + hom_nay.month - 1 - i, 12)
        ds.append(f"{y}-{m + 1:02d}")
    for t in cac_thang_co_du_lieu():
        if t not in ds:
            ds.append(t)
    ds = sorted(set(ds), reverse=True)
    return [{"label": f"Tháng {t[5:7]}/{t[:4]}", "value": t} for t in ds]


def _luu_tam(filename: str, content: str) -> Path:
    head, b64 = content.split(",", 1)
    path = UPLOAD_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{Path(filename).name}"
    path.write_bytes(base64.b64decode(b64))
    return path


def _khoi_ui(res, ten_file: str) -> html.Div:
    ten = TEN_DE_HIEU.get(res.dataset, res.ten_hien_thi)
    if res.thieu_cot:
        return card([
            alert([html.B(f"Thiếu {len(res.thieu_cot)} cột bắt buộc: "),
                   ", ".join(res.thieu_cot),
                   html.Div("Kiểm tra lại loại báo cáo đã tải. Nếu hệ thống vừa đổi tên cột, "
                            "báo quản trị bổ sung tên cột mới.",
                            style={"marginTop": "6px"})], "bad")],
            title=f"{ten} · {ten_file}")
    if res.canh_bao and res.df is None:
        return card([alert(" ".join(res.canh_bao), "warn")], title=f"{ten} · {ten_file}")

    df = res.df.drop(columns=[c for c in ("_row_hash", "_dong_file", "_ly_do")
                             if c in res.df.columns])
    preview = df.head(MAX_PREVIEW)
    cols = [{"field": c, "headerName": c, "minWidth": 120, "flex": 1} for c in preview.columns]
    body = [
        html.Div([
            badge(f"{res.rows_valid:,} dòng hợp lệ".replace(",", "."), "ok"),
            badge(f"{res.rows_invalid} dòng bị loại", "bad" if res.rows_invalid else "muted"),
            badge(f"{len(res.cols)} cột được dùng"),
        ], style={"display": "flex", "gap": "8px", "marginBottom": "12px"}),
        dag.AgGrid(className="ag-theme-quartz ag-theme-ftel", columnDefs=cols,
                   rowData=preview.astype(str).to_dict("records"),
                   defaultColDef={"resizable": True, "sortable": True},
                   dashGridOptions={"suppressCellFocus": True, "domLayout": "autoHeight"},
                   style={"width": "100%"}),
    ]
    if res.rows_invalid:
        loi = res.loi[["_dong_file", "_ly_do"]].head(MAX_PREVIEW)
        body += [
            html.Div(style={"height": "14px"}),
            alert([html.B(f"{res.rows_invalid} dòng bị loại "),
                   "- phần còn lại vẫn được lưu bình thường:"], "warn"),
            dag.AgGrid(className="ag-theme-quartz ag-theme-ftel",
                       columnDefs=[{"field": "_dong_file", "headerName": "Dòng số", "width": 110},
                                   {"field": "_ly_do", "headerName": "Lý do", "flex": 1}],
                       rowData=loi.astype(str).to_dict("records"),
                       dashGridOptions={"suppressCellFocus": True, "domLayout": "autoHeight"},
                       style={"width": "100%"}),
        ]
    return card(body, title=f"{ten} · {ten_file}",
                desc="20 dòng đầu sau khi map cột - kiểm nhanh trước khi lưu")


def register(app):
    # Kiểm dung lượng ngay trên trình duyệt, quá giới hạn thì không gửi lên máy chủ
    app.clientside_callback(
        """
        function(contents, names, gioiHanMb) {
            if (!contents) { return [window.dash_clientside.no_update, ""]; }
            if (!Array.isArray(contents)) { contents = [contents]; names = [names]; }
            let tong = 0;
            contents.forEach(function (c) { tong += Math.round(c.length * 0.75); });
            const mb = tong / 1048576;
            if (mb > gioiHanMb) {
                return [null, "Tổng dung lượng " + mb.toFixed(1) + " MB vượt giới hạn "
                    + gioiHanMb + " MB mỗi lượt. Chia thành nhiều lượt nạp nhỏ hơn."];
            }
            const ds = contents.map(function (c, i) { return {name: names[i], content: c}; });
            return [ds, contents.length + " file · " + mb.toFixed(2) + " MB"];
        }
        """,
        Output("up-hang-doi", "data"), Output("up-dung-luong", "children"),
        Input("up-file", "contents"), State("up-file", "filename"),
        State("up-gioi-han", "data"))

    @app.callback(Output("up-ketqua", "children"),
                  Output("up-commit", "disabled"), Output("up-thang", "value"),
                  Output("up-badge", "children"),
                  Input("up-hang-doi", "data"), prevent_initial_call=True)
    def _doc_file(hang_doi):
        if not hang_doi:
            return [], True, no_update, ""

        ui, kho, thang_nhan_su, so_ok = [], [], None, 0
        for muc_file in hang_doi:
            noi_dung, ten_file = muc_file["content"], muc_file["name"]
            try:
                path = _luu_tam(ten_file, noi_dung)
                results = load_file(path)
            except Exception as e:  # noqa: BLE001
                ui.append(card([alert([html.B("Không đọc được file: "), str(e)], "bad")],
                               title=ten_file))
                continue
            if not results:
                ui.append(card([alert([html.B("Không nhận diện được loại dữ liệu. "),
                                       "File cần có các cột đặc trưng như Hợp đồng, "
                                       "Acc nhân viên bán, Ngày Online."], "bad")],
                               title=ten_file))
                continue
            for r in results:
                ui.append(_khoi_ui(r, ten_file))
                if r.ok:
                    so_ok += 1
                if r.dataset == "nhan_su":
                    thang_nhan_su = thang_tu_ten_file(ten_file) or thang_nhan_su
            kho.append(ten_file)

        tom_tat = html.Div([badge(f"{len(kho)} file đã đọc"),
                            badge(f"{so_ok} bảng sẵn sàng lưu", "ok" if so_ok else "muted")],
                           style={"display": "flex", "gap": "8px", "marginBottom": "14px"})
        badge_top = html.Span(f"{so_ok} bảng chờ lưu", className="badge muted")
        return [tom_tat] + ui, not so_ok, thang_nhan_su or no_update, badge_top

    @app.callback(Output("up-commit-ketqua", "children"),
                  Input("up-commit", "n_clicks"), State("up-hang-doi", "data"),
                  State("up-thang", "value"), prevent_initial_call=True)
    def _luu(n, hang_doi, thang):
        if not n or not hang_doi:
            return no_update
        if not current_user.duoc_upload:
            return alert("Tài khoản này không có quyền nạp dữ liệu.", "bad")

        dong, loi_chung = [], []
        for muc_file in hang_doi:
            muc = {"filename": muc_file["name"]}
            try:
                path = _luu_tam(muc_file["name"], muc_file["content"])
                results = load_file(path)
                h = file_hash(path)
                with session_scope() as s:
                    for res in results:
                        if not res.ok:
                            continue
                        ten = TEN_DE_HIEU.get(res.dataset, res.ten_hien_thi)
                        if res.dataset == "nhan_su" and not thang:
                            dong.append(html.Li([html.B(ten), ": bỏ qua vì chưa chọn tháng - "
                                                              "chọn tháng rồi lưu lại."]))
                            continue
                        st = commit_result(s, res, nguon_file=muc["filename"], hash_file=h,
                                           user=current_user.username, thang=thang or None)
                        dong.append(html.Li([
                            html.B(ten), ": thêm mới ", html.B(f"{st.get('them_moi', 0):,}"
                                                              .replace(",", ".")),
                            ", cập nhật ", f"{st.get('cap_nhat', 0):,}".replace(",", "."),
                            f", trùng trong file {st.get('trung_trong_file', 0)}"
                            f", bỏ vì lỗi {st.get('loi', 0)}"]))
                ghi_log("upload", muc["filename"])
            except Exception as e:  # noqa: BLE001
                loi_chung.append(f"{muc['filename']}: {e}")

        noi_dung = [html.B("Đã lưu vào hệ thống."), html.Ul(dong)]
        if loi_chung:
            noi_dung.append(alert([html.B("Có file lỗi: "), "; ".join(loi_chung)], "bad"))
        noi_dung.append(html.Div([
            dcc.Link([icon("dashboard", 14), html.Span("Xem Báo cáo Tổng")], href="/",
                     className="btn primary"),
            dcc.Link([icon("shield", 14), html.Span("Kiểm tra chất lượng dữ liệu")],
                     href="/chatluong", className="btn"),
        ], style={"display": "flex", "gap": "8px", "marginTop": "12px"}))
        return alert(noi_dung, "warn" if loi_chung else "ok")
