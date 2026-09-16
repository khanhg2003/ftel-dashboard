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

from app.admin_service import go_bo_lan_nap, lich_su_nap
from app.auth import ghi_log
from app.config import GIOI_HAN_NAP_MB, UPLOAD_DIR
from app.db import session_scope
from app.ingest.commit import commit_result, file_hash, thang_nsld_tu_noi_dung, thang_tu_ten_file
from app.ingest.loader import load_file
from app.metrics import cac_thang_co_du_lieu
from app.ui.components import LOCALE_VI, alert, badge, card
from app.ui.icons import icon

MAX_PREVIEW = 20
TEN_DE_HIEU = {"internet": "Internet", "fptplay": "Truyền hình / FPT Play",
               "camera": "Camera", "nhan_su": "Nhân sự (NSLĐ)",
               "danh_muc_nv": "Danh mục nhân viên"}
TEN_NGAN = {"internet": "Internet", "fptplay": "Truyền hình", "camera": "Camera",
            "nhan_su": "NSLĐ", "danh_muc_nv": "Danh mục NV"}


def _duoc_nap(dataset: str) -> bool:
    """Quyền nạp theo loại file. Ngoài ngữ cảnh đăng nhập (dựng layout trong kiểm thử) coi như đủ
    quyền - mọi callback lưu và gỡ đều kiểm tra lại ở máy chủ."""
    ham = getattr(current_user, "duoc_nap", None)
    return bool(ham(dataset)) if callable(ham) else True


def _ten_loai_duoc_nap() -> str:
    return " · ".join(TEN_NGAN[d] for d in ("internet", "fptplay", "camera", "nhan_su",
                                            "danh_muc_nv") if _duoc_nap(d))


def topbar():
    return [html.Div([html.H1("Nạp dữ liệu"),
                      html.Div(_ten_loai_duoc_nap(), className="sub")]),
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
                html.Div([html.Label("Tháng NSLĐ (chỉ khi app không tự nhận được)"),
                          dcc.Dropdown(id="up-thang", options=_thang_options(), value=None,
                                       placeholder="Chọn tháng", clearable=True,
                                       style={"width": "190px"})],
                         className="field",
                         style={} if _duoc_nap("nhan_su") else {"display": "none"}),
                html.Div("File bán hàng tự lấy ngày trong file. File NSLĐ tự nhận tháng từ dữ liệu "
                         "(Ngày tính lương + Tháng NSLĐ) hoặc tên file - nạp nhiều tháng một lượt được."
                         if _duoc_nap("nhan_su") else
                         "Tài khoản của bạn nạp được 3 file bán hàng (Internet, Truyền hình, Camera); "
                         "file NSLĐ và Danh mục nhân viên do Quản trị nạp.",
                         className="desc", style={"margin": 0, "alignSelf": "center",
                                                  "maxWidth": "42ch"}),
                html.Div(className="grow"),
                html.Button([icon("save", 14), html.Span("Lưu tất cả vào hệ thống")],
                            id="up-commit", className="btn primary", disabled=True),
            ], className="toolbar"),
        ], title="Bước 1 · Chọn file",
            desc="Loại dữ liệu được nhận diện theo tên cột, nên đổi thứ tự hay thêm bớt cột "
                 "vẫn đọc đúng."),
        # kết quả lưu đặt ngay dưới nút Lưu (trước các bảng xem trước) để bấm là thấy
        dcc.Loading(html.Div(id="up-commit-ketqua"), type="default"),
        dcc.Loading(html.Div(id="up-ketqua")),
        _the_lich_su(),
    ])


def _the_lich_su():
    return html.Div([
        dcc.ConfirmDialog(id="up-ls-xacnhan"),
        html.Div([
            html.Div([html.H3("Lịch sử nạp"),
                      html.Div("50 lần nạp gần nhất. Nạp nhầm file: tick dòng đó rồi bấm Gỡ bỏ.",
                               className="desc")], className="the-ten"),
            html.Div([html.Button([icon("trash", 14), html.Span("Gỡ bỏ lần nạp")],
                                  id="up-ls-go", className="btn nguy-hiem", disabled=True)],
                     className="the-nut"),
        ], className="the-dau"),
        html.Div(id="up-ls-msg"),
        dag.AgGrid(id="up-ls-grid", className="ag-theme-quartz ag-theme-ftel",
                   columnDefs=_cot_lich_su(), rowData=[], getRowId="params.data.id",
                   defaultColDef={"resizable": True, "sortable": True},
                   dashGridOptions={"rowSelection": "single", "suppressCellFocus": True,
                                    "pagination": True, "paginationPageSize": 10,
                                    "paginationPageSizeSelector": False, "tooltipShowDelay": 300,
                                    "localeText": LOCALE_VI, "domLayout": "autoHeight"},
                   style={"width": "100%"}),
    ], className="card")


SO = {"function": "params.value == null ? '' : Number(params.value).toLocaleString('vi-VN')"}


def _cot_lich_su():
    return [
        {"field": "_chon", "headerName": "", "width": 44, "maxWidth": 44, "pinned": "left",
         "checkboxSelection": True, "sortable": False, "resizable": False},
        {"field": "thoi_diem", "headerName": "Thời điểm", "width": 136,
         "comparator": {"function": "(a, b, na, nb) => na.data.thoi_diem_sx < nb.data.thoi_diem_sx ? -1 : 1"}},
        {"field": "loai", "headerName": "Loại", "width": 120},
        {"field": "file_name", "headerName": "File", "minWidth": 180, "flex": 1,
         "tooltipField": "file_name"},
        {"field": "rows_valid", "headerName": "Dòng hợp lệ", "width": 104,
         "valueFormatter": SO, "type": "numericColumn"},
        {"field": "rows_new", "headerName": "Thêm mới", "width": 94, "valueFormatter": SO,
         "type": "numericColumn"},
        {"field": "rows_updated", "headerName": "Cập nhật", "width": 94, "valueFormatter": SO,
         "type": "numericColumn"},
        {"field": "con_lai", "headerName": "Đang dùng", "width": 96, "valueFormatter": SO,
         "type": "numericColumn",
         "headerTooltip": "Số dòng báo cáo đang lấy từ lần nạp này. Về 0 khi lần nạp sau đã "
                          "cập nhật lại toàn bộ các dòng đó - bình thường."},
        {"field": "uploaded_by", "headerName": "Người nạp", "width": 100},
        {"field": "note", "headerName": "Ghi chú", "minWidth": 110, "flex": .5,
         "tooltipField": "note"},
    ]


def _du_lieu_lich_su() -> list[dict]:
    b = lich_su_nap()
    if b.empty:
        return []
    b["loai"] = b["dataset"].map(TEN_NGAN).fillna(b["dataset"])
    b = b.drop(columns=["uploaded_at"])
    return b.astype(object).where(b.notna(), None).to_dict("records")


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


def thang_nsld(res, ten_file: str, thang_chon: str | None = None) -> tuple[str | None, str]:
    """(tháng của file NSLĐ, cách nhận ra). Ưu tiên dữ liệu trong file, rồi tên file, rồi ô chọn tháng."""
    theo_dl, ty_le = thang_nsld_tu_noi_dung(res.df)
    theo_ten = thang_tu_ten_file(ten_file)
    if theo_dl and ty_le >= 0.8:
        ghi = "tự nhận từ Ngày tính lương + Tháng NSLĐ"
        if theo_ten and theo_ten != theo_dl:
            ghi += f" (tên file ghi {theo_ten[5:7]}/{theo_ten[:4]} - đang dùng tháng theo dữ liệu)"
        return theo_dl, ghi
    if theo_ten:
        return theo_ten, "lấy theo tên file"
    if thang_chon:
        return thang_chon, "lấy theo ô Tháng NSLĐ bạn chọn"
    return None, ""


def _ten_thang(t: str) -> str:
    return f"{t[5:7]}/{t[:4]}"


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
    thang_ghi = []
    if res.dataset == "nhan_su":
        t, cach = thang_nsld(res, ten_file)
        ten = f"{ten} tháng {_ten_thang(t)}" if t else ten
        thang_ghi = [badge(f"Tháng {_ten_thang(t)} · {cach}", "ok") if t else
                     badge("Chưa nhận ra tháng - chọn ở ô Tháng NSLĐ trước khi lưu", "bad")]
    body = [
        html.Div(thang_ghi + [
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
    # ------------------------------------------------------------ lịch sử nạp
    @app.callback(Output("up-ls-grid", "rowData"),
                  Input("up-ls-grid", "id"), Input("up-commit-ketqua", "children"),
                  Input("up-ls-msg", "children"))
    def _nap_lich_su(*_):
        return _du_lieu_lich_su()

    @app.callback(Output("up-ls-go", "disabled"), Input("up-ls-grid", "selectedRows"))
    def _bat_nut_go(chon):
        return not chon

    @app.callback(Output("up-ls-xacnhan", "displayed"), Output("up-ls-xacnhan", "message"),
                  Input("up-ls-go", "n_clicks"), State("up-ls-grid", "selectedRows"),
                  prevent_initial_call=True)
    def _hoi_go(_n, chon):
        if not chon:
            return False, ""
        r = chon[0]
        return True, (f"Gỡ lần nạp {r.get('thoi_diem')} · {r.get('loai')} "
                      f"({r.get('file_name')})?\n\nCác dòng số đang lấy từ lần nạp này sẽ bị "
                      "xoá khỏi báo cáo. Không hoàn tác được - muốn lấy lại thì nạp lại file.")

    @app.callback(Output("up-ls-msg", "children"),
                  Input("up-ls-xacnhan", "submit_n_clicks"), State("up-ls-grid", "selectedRows"),
                  prevent_initial_call=True)
    def _go(n, chon):
        if not n or not chon:
            return no_update
        if not current_user.duoc_upload:
            return alert("Tài khoản này không có quyền gỡ dữ liệu.", "bad")
        kq = go_bo_lan_nap(int(chon[0]["id"]), current_user.username,
                           loai_cho_phep=current_user.loai_duoc_nap(),
                           chi_cua_minh=current_user.role != "admin")
        if not kq.get("ok"):
            return alert(kq.get("msg", "Không gỡ được."), "bad")
        return alert(f"Đã gỡ {kq['so_dong']:,} dòng {TEN_NGAN.get(kq['dataset'], kq['dataset'])} "
                     f"của lần nạp {chon[0].get('thoi_diem')}.".replace(",", "."), "ok")

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
        if not hang_doi:                     # vừa lưu xong (hàng đợi được xoá) - giữ kết quả đang hiện
            return no_update, True, no_update, no_update

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
                if not _duoc_nap(r.dataset):
                    ui.append(card([alert([html.B(f"{TEN_DE_HIEU.get(r.dataset, r.dataset)}: "),
                                           "tài khoản của bạn không được nạp loại file này. "
                                           "Nhờ Quản trị (BGĐ) nạp giúp."], "warn")],
                                   title=ten_file))
                    continue
                ui.append(_khoi_ui(r, ten_file))
                if r.ok:
                    so_ok += 1
            kho.append(ten_file)

        tom_tat = html.Div([badge(f"{len(kho)} file đã đọc"),
                            badge(f"{so_ok} bảng sẵn sàng lưu", "ok" if so_ok else "muted")],
                           style={"display": "flex", "gap": "8px", "marginBottom": "14px"})
        badge_top = html.Span(f"{so_ok} bảng chờ lưu", className="badge warn" if so_ok else "badge muted")
        huong_dan = alert([html.B(f"Đã đọc {len(kho)} file. "),
                           "Kiểm tra nhanh các bảng bên dưới rồi bấm ", html.B("Lưu tất cả vào hệ thống"),
                           " ở trên - dữ liệu chỉ vào báo cáo sau khi lưu."], "info") if so_ok else ""
        return [tom_tat, huong_dan] + ui, not so_ok, no_update, badge_top

    @app.callback(Output("up-commit-ketqua", "children"),
                  Output("up-hang-doi", "data", allow_duplicate=True),
                  Output("up-ketqua", "children", allow_duplicate=True),
                  Output("up-badge", "children", allow_duplicate=True),
                  Input("up-commit", "n_clicks"), State("up-hang-doi", "data"),
                  State("up-thang", "value"), prevent_initial_call=True,
                  running=[(Output("up-commit", "disabled"), True, False),
                           (Output("up-commit", "children"),
                            [html.Span(className="xoay"), html.Span("Đang lưu, vui lòng chờ…")],
                            [icon("save", 14), html.Span("Lưu tất cả vào hệ thống")])])
    def _luu(n, hang_doi, thang):
        if not n or not hang_doi:
            return no_update, no_update, no_update, no_update
        if not current_user.duoc_upload:
            return alert("Tài khoản này không có quyền nạp dữ liệu.", "bad"), no_update, no_update, no_update

        dong, so_luu, so_bo = [], 0, 0
        for muc_file in hang_doi:
            ten_file = muc_file["name"]
            try:
                path = _luu_tam(ten_file, muc_file["content"])
                results = load_file(path)
                h = file_hash(path)
                if not any(r.ok for r in results):
                    so_bo += 1
                    dong.append(("bad", ten_file, "Không đọc được dữ liệu hợp lệ - đã bỏ qua."))
                    continue
                with session_scope() as s:
                    for res in results:
                        if not res.ok:
                            continue
                        ten = TEN_DE_HIEU.get(res.dataset, res.ten_hien_thi)
                        if not _duoc_nap(res.dataset):
                            so_bo += 1
                            dong.append(("bad", f"{ten} · {ten_file}",
                                         "Chưa lưu: tài khoản của bạn không được nạp loại file này."))
                            continue
                        thang_file = thang
                        if res.dataset == "nhan_su":
                            thang_file, cach = thang_nsld(res, ten_file, thang)
                            if not thang_file:
                                so_bo += 1
                                dong.append(("bad", f"{ten} · {ten_file}",
                                             "Chưa lưu: không nhận ra tháng. Chọn ô Tháng NSLĐ rồi lưu lại."))
                                continue
                            ten = f"{ten} tháng {_ten_thang(thang_file)}"
                        st = commit_result(s, res, nguon_file=ten_file, hash_file=h,
                                           user=current_user.username, thang=thang_file or None)
                        so_luu += 1
                        chi_tiet = (f"thêm mới {st.get('them_moi', 0):,}, cập nhật {st.get('cap_nhat', 0):,}"
                                    .replace(",", "."))
                        if st.get("trung_trong_file"):
                            chi_tiet += f", bỏ {st['trung_trong_file']} dòng trùng trong file"
                        if st.get("loi"):
                            chi_tiet += f", bỏ {st['loi']} dòng lỗi"
                        dong.append(("ok", f"{ten} · {ten_file}", chi_tiet))
                ghi_log("upload", ten_file)
            except Exception as e:  # noqa: BLE001
                so_bo += 1
                dong.append(("bad", ten_file, f"Lỗi khi lưu: {e}"))

        muc = "ok" if so_luu and not so_bo else ("warn" if so_luu else "bad")
        tieu_de = (f"Đã lưu {so_luu} bảng vào hệ thống." if not so_bo else
                   f"Đã lưu {so_luu} bảng, {so_bo} bảng chưa lưu được - xem lý do bên dưới.")
        noi_dung = [
            html.B(tieu_de),
            html.Ul([html.Li([html.Span("✓ " if m == "ok" else "✗ ", className=f"dau-{m}"),
                              html.B(t), f": {c}"]) for m, t, c in dong], className="ds-ket-qua"),
            html.Div([
                dcc.Link([icon("dashboard", 14), html.Span("Xem Báo cáo Tổng")], href="/",
                         className="btn primary"),
                dcc.Link([icon("users", 14), html.Span("Xem NSLĐ")], href="/hr", className="btn"),
                dcc.Link([icon("shield", 14), html.Span("Kiểm tra chất lượng dữ liệu")],
                         href="/chatluong", className="btn"),
            ], style={"display": "flex", "gap": "8px", "marginTop": "12px", "flexWrap": "wrap"}),
        ]
        xong = html.Span(f"Đã lưu {so_luu} bảng", className="badge ok" if so_luu else "badge bad")
        if so_bo:                            # còn bảng chưa lưu: giữ nguyên file để chọn tháng rồi lưu lại
            return alert(noi_dung, muc), no_update, no_update, xong
        return alert(noi_dung, muc), None, [], xong
