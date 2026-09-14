"""Trang Cấu hình: cơ cấu tổ chức, chỉ tiêu, danh mục nhân sự, tài khoản, nhật ký.

Toàn bộ cơ cấu (Bầy, Phòng, cơ cấu theo tháng) sửa được trên giao diện -
không cần sửa file cấu hình hay code.
"""
from __future__ import annotations

import dash_ag_grid as dag
import pandas as pd
from dash import Input, Output, State, ctx, dcc, html, no_update
from flask_login import current_user
from sqlalchemy import select, text

from app.auth import doi_mat_khau, ghi_log
from app.db import engine, session_scope
from app.ingest.commit import recompute_phong
from app.metrics import cac_thang_co_du_lieu, prev_month
from app.models import Target
from app.org import (LOAI_PHONG, bay_info, bay_options, co_cau_rieng, luu_bay, luu_co_cau_thang,
                     luu_phong, phong_order, xoa_bay, xoa_cache_org, xoa_co_cau_thang, xoa_phong)
from app.thoi_gian import chu_gio_vn
from app.mau_nhap import ap_dung_co_cau, mau_co_cau, xem_truoc_co_cau
from app.ui.components import (MAU_LOAI_THAY_DOI, alert, card, chon_ky, field, gan_dieu_huong_ky,
                               gan_import, modal, nhac_chua_luu, nut_import)
from app.ui.icons import icon

CHON = {"field": "_chon", "headerName": "", "width": 44, "maxWidth": 44, "pinned": "left",
        "checkboxSelection": True, "headerCheckboxSelection": True, "sortable": False,
        "editable": False, "resizable": False}

CHI_TIEU = [("internet", "Chỉ tiêu Internet"), ("camera", "Chỉ tiêu Camera"),
            ("ngay", "Chỉ tiêu mỗi ngày")]
CO_KHONG = ["Có", "Không"]
CHI_NHANH = ["DNG", "QNM"]
NHOM_KHAC = ["", "DNG", "QNM"]
GRID_OPTS = {"domLayout": "autoHeight", "stopEditingWhenCellsLoseFocus": True,
             "singleClickEdit": True, "rowSelection": "multiple",
             "suppressRowClickSelection": True}


def topbar():
    return [html.Div([html.H1("Cấu hình"),
                      html.Div("Cơ cấu tổ chức · chỉ tiêu tháng · danh mục hệ thống",
                               className="sub")])]


def _grid(gid, cao: int | None = None, **kw):
    """cao=None -> bảng ngắn, để tự giãn. Có cao -> cuộn trong khung, tiêu đề cột luôn thấy."""
    kw.setdefault("defaultColDef", {"resizable": True, "sortable": False})
    opts = dict(GRID_OPTS)
    style = {"width": "100%"}
    if cao:
        opts["domLayout"] = "normal"
        style["height"] = f"{cao}px"
    return dag.AgGrid(id=gid, className="ag-theme-quartz ag-theme-ftel", columnDefs=[], rowData=[],
                      dashGridOptions=opts, style=style, **kw)


def _o(label, control):
    return html.Div([html.Label(label), control], className="field rong")


def _hop_thoai_bay():
    return modal("st-modal-bay", "Thêm bầy mới", [
        html.Div([
            _o("Tên bầy *", dcc.Input(id="st-b-ten", type="text", placeholder="vd: BẦY 4",
                                      className="inp")),
            _o("Tên dòng tổng", dcc.Input(id="st-b-tentong", type="text",
                                          placeholder="vd: TỔNG BẦY 4", className="inp")),
            _o("Thứ tự hiển thị", dcc.Input(id="st-b-thutu", type="number", value=99,
                                            className="inp")),
        ], className="form-grid"),
        html.Div("Bầy là nhóm nhiều phòng kinh doanh. Tạo xong, chuyển phòng vào bầy mới ở "
                 "bảng bên dưới.", className="desc"),
        html.Div(id="st-modal-bay-msg"),
    ], nut_chinh="Tạo bầy")


def _hop_thoai_phong():
    return modal("st-modal-phong", "Thêm phòng kinh doanh", [
        html.Div([
            _o("Tên phòng *", dcc.Input(id="st-p-ten", type="text", placeholder="vd: IBB8",
                                        className="inp")),
            _o("Bầy mặc định *", dcc.Dropdown(id="st-p-bay", clearable=False,
                                              options=bay_options(),
                                              value=bay_options()[0]["value"] if bay_options()
                                              else None)),
            _o("Loại phòng *", dcc.Dropdown(id="st-p-loai", clearable=False, value="IBB",
                                            options=[{"label": x, "value": x}
                                                     for x in LOAI_PHONG])),
            _o("Chi nhánh *", dcc.Dropdown(id="st-p-cn", clearable=False, value="DNG",
                                           options=[{"label": "Đà Nẵng", "value": "DNG"},
                                                    {"label": "Quảng Nam", "value": "QNM"}])),
            _o("Gộp vào nhóm Khác", dcc.Dropdown(
                id="st-p-nhomkhac", value="", clearable=False,
                options=[{"label": "Không gộp", "value": ""},
                         {"label": "DNG Khác", "value": "DNG"},
                         {"label": "QNM Khác", "value": "QNM"}])),
            _o("Thứ tự trong bầy", dcc.Input(id="st-p-thutu", type="number", value=99,
                                             className="inp")),
        ], className="form-grid"),
        html.Div("IBB / DIABAN là phòng bán hàng trực tiếp. Phòng kỹ thuật, CUS, ECOM "
                 "thường gộp vào dòng “Khác” - chọn ở ô “Gộp vào nhóm Khác”.", className="desc"),
        html.Div(id="st-modal-phong-msg"),
    ], nut_chinh="Tạo phòng")


def layout():
    thangs = cac_thang_co_du_lieu() or ["2026-09"]
    return html.Div([
        _hop_thoai_bay(),
        _hop_thoai_phong(),
        dcc.ConfirmDialog(id="st-bay-xacnhan", message="Xoá các bầy đã chọn?"),
        dcc.ConfirmDialog(id="st-phong-xacnhan", message="Xoá các phòng đã chọn?"),
        html.Div([
            dcc.Tabs(id="st-tab", value="cocau", className="seg", children=[
                dcc.Tab(label="Cơ cấu tổ chức", value="cocau", className="seg-item",
                        selected_className="seg-item active"),
                dcc.Tab(label="Chỉ tiêu", value="chitieu", className="seg-item",
                        selected_className="seg-item active"),
                dcc.Tab(label="Nhân sự & hệ thống", value="khac", className="seg-item",
                        selected_className="seg-item active"),
            ]),
            html.Div(className="grow"),
            field("Kỳ áp dụng", chon_ky("st-thang", thangs)),
        ], className="toolbar loc-trang"),

        # ------------------------------------------------ tab Cơ cấu tổ chức
        html.Div(id="st-pane-cocau", children=[
            html.Div([
                html.Div([html.H3("Nhập nhanh bằng Excel"),
                          html.Div("Tải file mẫu (điền sẵn bầy, phòng hiện có) → sửa hoặc thêm dòng → "
                                   "Import Excel. App cho xem trước từng thay đổi rồi mới ghi. Bầy, "
                                   "phòng không có trong file giữ nguyên.", className="desc")],
                         className="the-ten"),
                html.Div(nut_import("st-cc", "Tải file mẫu"), className="the-nut"),
            ], className="card the-dau"),
            card([
                html.Div([
                    html.Div("Đổi tên, thêm bầy mới hoặc ngừng dùng một bầy.",
                             style={"color": "var(--text-muted)", "fontSize": "12.5px"}),
                    html.Div(id="st-bay-nhac", style={"marginLeft": "10px"}),
                    html.Div(className="grow"),
                    html.Button([icon("trash", 14), html.Span("Xoá")], id="st-bay-xoa",
                                className="btn nguy-hiem"),
                    html.Button([icon("plus", 14), html.Span("Thêm bầy")], id="st-bay-them",
                                className="btn"),
                    html.Button([icon("save", 14), html.Span("Lưu danh mục bầy")], id="st-bay-luu",
                                className="btn primary"),
                ], className="toolbar"),
                html.Div(id="st-bay-msg"),
                _grid("st-bay-grid"),
            ], title="Danh mục Bầy"),

            card([
                html.Div([
                    html.Div("Mỗi phòng thuộc một bầy mặc định. Thêm phòng mới ngay tại đây.",
                             style={"color": "var(--text-muted)", "fontSize": "12.5px"}),
                    html.Div(id="st-phong-nhac", style={"marginLeft": "10px"}),
                    html.Div(className="grow"),
                    html.Button([icon("trash", 14), html.Span("Xoá")], id="st-phong-xoa",
                                className="btn nguy-hiem"),
                    html.Button([icon("plus", 14), html.Span("Thêm phòng")], id="st-phong-them",
                                className="btn"),
                    html.Button([icon("save", 14), html.Span("Lưu danh mục phòng")],
                                id="st-phong-luu", className="btn primary"),
                ], className="toolbar"),
                html.Div(id="st-phong-msg"),
                _grid("st-phong-grid", cao=380),
            ], title="Phòng kinh doanh"),

            card([
                html.Div([
                    html.Div(id="st-cocau-trangthai"),
                    html.Div(className="grow"),
                    html.Button([icon("refresh", 14), html.Span("Dùng cơ cấu mặc định")],
                                id="st-cocau-xoa", className="btn"),
                    html.Button([icon("copy", 14), html.Span("Sao chép kỳ trước")],
                                id="st-cocau-copy", className="btn"),
                    html.Button([icon("save", 14), html.Span("Lưu cơ cấu kỳ này")],
                                id="st-cocau-luu", className="btn primary"),
                ], className="toolbar"),
                html.Div(id="st-cocau-msg"),
                _grid("st-cocau-grid", cao=380),
            ], title="Cơ cấu Bầy của kỳ đang chọn",
                desc="Xếp lại phòng vào bầy cho riêng kỳ này, không ảnh hưởng các kỳ trước"),
        ]),

        # ------------------------------------------------ tab Chỉ tiêu
        html.Div(id="st-pane-chitieu", children=[
            card([
                html.Div([
                    html.Div("Chỉ tiêu tháng của từng phòng - dùng để tính tỷ lệ hoàn thành "
                             "kế hoạch.", style={"color": "var(--text-muted)",
                                                 "fontSize": "12.5px"}),
                    html.Div(id="st-target-nhac", style={"marginLeft": "10px"}),
                    html.Div(className="grow"),
                    html.Button([icon("copy", 14), html.Span("Sao chép kỳ trước")],
                                id="st-target-copy", className="btn"),
                    html.Button([icon("save", 14), html.Span("Lưu chỉ tiêu")], id="st-luu-target",
                                className="btn primary"),
                ], className="toolbar"),
                html.Div(id="st-target-msg"),
                _grid("st-target-grid", cao=420,
                      defaultColDef={"resizable": True, "editable": True, "sortable": False}),
            ], title="Chỉ tiêu tháng"),
        ]),

        # ------------------------------------------------ tab Nhân sự & hệ thống
        html.Div(id="st-pane-khac", children=[
            card([
                html.Div([
                    html.Button([icon("refresh", 14), html.Span("Tính lại việc gán phòng")],
                                id="st-recompute", className="btn"),
                    html.Div("Chạy sau khi cập nhật danh mục nhân sự hoặc thêm phòng mới.",
                             style={"color": "var(--text-muted)", "fontSize": "12.5px",
                                    "alignSelf": "center"}),
                    html.Div(className="grow"),
                    html.Div(id="st-recompute-msg"),
                ], className="toolbar"),
                html.Div(id="st-danhmuc"),
            ], title="Danh mục nhân sự → Phòng kinh doanh",
                desc="Sửa ở Quản trị → Danh mục nhân sự, hoặc nạp file danh mục"),

            html.Div([
                html.Div(card([
                    html.Div([
                        field("Mật khẩu hiện tại", dcc.Input(id="st-mk-cu", type="password",
                                                             style=_inp())),
                        field("Mật khẩu mới", dcc.Input(id="st-mk-moi", type="password",
                                                        style=_inp())),
                    ], style={"display": "flex", "gap": "14px", "flexWrap": "wrap"}),
                    html.Div(style={"height": "10px"}),
                    html.Button("Đổi mật khẩu", id="st-doi-mk", className="btn primary"),
                    html.Div(id="st-mk-msg", style={"marginTop": "10px"}),
                ], title="Tài khoản", desc=f"Đang đăng nhập: {current_user.username}"),
                    style={"flex": "1 1 360px"}),
                html.Div(card([html.Div(id="st-log")], title="Nhật ký hệ thống",
                              desc="20 thao tác gần nhất"),
                     style={"flex": "1 1 460px"}),
            ], style={"display": "flex", "gap": "20px", "flexWrap": "wrap"}),
        ]),
    ])


def _inp():
    return {"padding": "9px 12px", "borderRadius": "8px", "border": "1px solid var(--border)",
            "width": "190px"}


# ----------------------------------------------------------------- dữ liệu bảng
def _bay_rows():
    rows = [{"code": b["code"], "ten": b["ten"],
             "ten_tong": b.get("ten_tong") or f"TỔNG {b['ten'].upper()}",
             "thu_tu": b["thu_tu"], "active": "Có"}
            for b in sorted(bay_info().values(), key=lambda x: x["thu_tu"])]
    cols = [
        CHON,
        {"field": "ten", "headerName": "Tên bầy", "editable": True, "width": 180},
        {"field": "ten_tong", "headerName": "Tên dòng tổng", "editable": True, "width": 200},
        {"field": "thu_tu", "headerName": "Thứ tự", "editable": True, "width": 110,
         "type": "numericColumn"},
        {"field": "active", "headerName": "Đang dùng", "editable": True, "width": 130,
         "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": CO_KHONG}},
        {"field": "code", "headerName": "Mã", "editable": False, "width": 120},
    ]
    return cols, rows


def _phong_rows():
    ten_b = {c: b["ten"] for c, b in bay_info().items()}
    rows = [{"code": p["code"], "ten": p["ten"], "bay": ten_b.get(p["bay"], p["bay"]),
             "loai": p["loai"], "chi_nhanh": p["chi_nhanh"], "nhom_khac": p.get("nhom_khac") or "",
             "thu_tu": p["thu_tu"], "active": "Có"}
            for p in phong_order()]
    cols = [
        CHON,
        {"field": "ten", "headerName": "Tên phòng", "editable": True, "width": 190,
         "pinned": "left"},
        {"field": "bay", "headerName": "Bầy mặc định", "editable": True, "width": 150,
         "cellEditor": "agSelectCellEditor",
         "cellEditorParams": {"values": [b["label"] for b in bay_options()]}},
        {"field": "loai", "headerName": "Loại", "editable": True, "width": 120,
         "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": LOAI_PHONG},
         "headerTooltip": "IBB / DIABAN (địa bàn) / KT / CUS / ECOM / KHAC"},
        {"field": "chi_nhanh", "headerName": "Chi nhánh", "editable": True, "width": 120,
         "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": CHI_NHANH}},
        {"field": "nhom_khac", "headerName": "Gộp vào nhóm Khác", "editable": True, "width": 180,
         "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": NHOM_KHAC}},
        {"field": "thu_tu", "headerName": "Thứ tự", "editable": True, "width": 100,
         "type": "numericColumn"},
        {"field": "active", "headerName": "Đang dùng", "editable": True, "width": 120,
         "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": CO_KHONG}},
        {"field": "code", "headerName": "Mã", "editable": False, "width": 130},
    ]
    return cols, rows


def _cocau_rows(thang: str):
    ten_b = {c: b["ten"] for c, b in bay_info().items()}
    rows = [{"phong_code": p["code"], "phong": p["ten"], "bay": ten_b.get(p["bay"], p["bay"]),
             "thu_tu": p["thu_tu"]} for p in phong_order(thang)]
    cols = [
        {"field": "phong", "headerName": "Phòng kinh doanh", "editable": False, "width": 200,
         "pinned": "left"},
        {"field": "bay", "headerName": "Thuộc bầy", "editable": True, "width": 170,
         "cellEditor": "agSelectCellEditor",
         "cellEditorParams": {"values": [b["label"] for b in bay_options()]},
         "cellStyle": {"fontWeight": "600"}},
        {"field": "thu_tu", "headerName": "Thứ tự trong bầy", "editable": True, "width": 160,
         "type": "numericColumn"},
    ]
    return cols, rows


def _target_rows(thang: str):
    df = pd.read_sql(text("""SELECT ma_doi_tuong, chi_tieu, gia_tri FROM target_monthly
                             WHERE thang = :t AND doi_tuong = 'PHONG'"""),
                     engine, params={"t": thang})
    pv = (df.pivot_table(index="ma_doi_tuong", columns="chi_tieu", values="gia_tri")
          if not df.empty else pd.DataFrame())
    rows = []
    for p in phong_order(thang):
        row = {"phong_code": p["code"], "phong": p["ten"], "bay": p["bay"]}
        for key, _ in CHI_TIEU:
            row[key] = (float(pv.at[p["code"], key])
                        if (not pv.empty and p["code"] in pv.index and key in pv.columns
                            and pd.notna(pv.at[p["code"], key])) else None)
        rows.append(row)
    cols = [{"field": "phong", "headerName": "Phòng", "editable": False, "pinned": "left",
             "width": 190},
            {"field": "bay", "headerName": "Bầy", "editable": False, "width": 110}]
    cols += [{"field": k, "headerName": t, "type": "numericColumn", "width": 170}
             for k, t in CHI_TIEU]
    return cols, rows


def _luu_target_rows(thang: str, rows: list[dict], ghi_chu: str) -> int:
    n = 0
    with session_scope() as s:
        for r in rows or []:
            for key, _ in CHI_TIEU:
                val = r.get(key)
                if val in (None, ""):
                    continue
                try:
                    val = float(val)
                except (TypeError, ValueError):
                    continue
                row = s.execute(select(Target).where(
                    Target.thang == thang, Target.doi_tuong == "PHONG",
                    Target.ma_doi_tuong == r["phong_code"],
                    Target.chi_tieu == key)).scalars().first()
                if row is None:
                    row = Target(thang=thang, doi_tuong="PHONG", ma_doi_tuong=r["phong_code"],
                                 chi_tieu=key)
                    s.add(row)
                row.gia_tri = val
                row.ghi_chu = ghi_chu
                n += 1
    return n


# ----------------------------------------------------------------- callbacks
def register(app):
    gan_dieu_huong_ky(app, "st-thang")
    nhac_chua_luu(app, "st-bay-grid", "st-bay-nhac", "st-bay-msg")
    nhac_chua_luu(app, "st-phong-grid", "st-phong-nhac", "st-phong-msg")
    nhac_chua_luu(app, "st-target-grid", "st-target-nhac", "st-target-msg")
    gan_import(app, "st-cc", ham_mau=mau_co_cau, ten_file_mau="Mau_CoCau_Bay_Phong.xlsx",
               ham_xem=xem_truoc_co_cau, ham_ap=ap_dung_co_cau, out_msg="st-phong-msg",
               cot=[{"field": "loai", "headerName": "Thay đổi", "width": 120, "pinned": "left",
                     "cellStyle": MAU_LOAI_THAY_DOI},
                    {"field": "doi_tuong", "headerName": "Loại", "width": 86},
                    {"field": "ten", "headerName": "Tên", "width": 170},
                    {"field": "ma", "headerName": "Mã", "width": 120},
                    {"field": "chi_tiet", "headerName": "Chi tiết", "flex": 1, "minWidth": 240,
                     "tooltipField": "chi_tiet"},
                    {"field": "dong", "headerName": "Dòng", "width": 76}],
               mo_ta_ket_qua=lambda d: [
                   html.B("Đã import cơ cấu. "),
                   f"Thêm mới {d.get('Thêm mới', 0)}, cập nhật {d.get('Cập nhật', 0)}, bỏ qua "
                   f"{d.get('Lỗi', 0)} dòng lỗi. Phòng mới cần gán nhân sự ở Quản trị → Danh mục nhân sự."])

    @app.callback(Output("st-pane-cocau", "style"), Output("st-pane-chitieu", "style"),
                  Output("st-pane-khac", "style"), Input("st-tab", "value"))
    def _tab(tab):
        an = {"display": "none"}
        return ({} if tab == "cocau" else an, {} if tab == "chitieu" else an,
                {} if tab == "khac" else an)

    @app.callback(Output("st-bay-grid", "columnDefs"), Output("st-bay-grid", "rowData"),
                  Output("st-phong-grid", "columnDefs"), Output("st-phong-grid", "rowData"),
                  Output("st-cocau-grid", "columnDefs"), Output("st-cocau-grid", "rowData"),
                  Output("st-cocau-trangthai", "children"),
                  Output("st-target-grid", "columnDefs"), Output("st-target-grid", "rowData"),
                  Output("st-danhmuc", "children"), Output("st-log", "children"),
                  Input("st-thang", "value"), Input("st-bay-msg", "children"),
                  Input("st-phong-msg", "children"), Input("st-cocau-msg", "children"),
                  Input("st-target-msg", "children"))
    def _nap(thang, *_):
        b_cols, b_rows = _bay_rows()
        p_cols, p_rows = _phong_rows()
        c_cols, c_rows = _cocau_rows(thang)
        t_cols, t_rows = _target_rows(thang)
        cc_badge = (html.Span("Kỳ này đang dùng cơ cấu riêng", className="badge ok")
                    if co_cau_rieng(thang) else
                    html.Span("Kỳ này đang dùng cơ cấu mặc định", className="badge muted"))

        dm = pd.read_sql(text("""SELECT s.acc, p.ten AS phong, s.ma_nv, s.ghi_chu
                                 FROM staff_map s LEFT JOIN dim_phong p ON p.code = s.phong_code
                                 ORDER BY p.ten, s.acc"""), engine)
        dm_ui = [html.Div(f"{len(dm)} tài khoản trong danh mục", className="badge",
                          style={"marginBottom": "10px"}),
                 dag.AgGrid(className="ag-theme-quartz ag-theme-ftel",
                            columnDefs=[{"field": "acc", "headerName": "Acc inside", "width": 180},
                                        {"field": "phong", "headerName": "Phòng", "width": 180},
                                        {"field": "ma_nv", "headerName": "Mã NV", "width": 120},
                                        {"field": "ghi_chu", "headerName": "Ghi chú", "flex": 1}],
                            rowData=dm.astype(object).where(dm.notna(), "").to_dict("records"),
                            defaultColDef={"resizable": True, "sortable": True, "filter": True},
                            dashGridOptions={"suppressCellFocus": True, "pagination": True,
                                             "paginationPageSize": 10,
                                             "paginationPageSizeSelector": False},
                            style={"width": "100%", "height": "420px"})]
        log = pd.read_sql(text("""SELECT ts, username, action FROM audit_log
                                  ORDER BY id DESC LIMIT 20"""), engine)
        log_ui = html.Table([
            html.Thead(html.Tr([html.Th("Thời điểm"), html.Th("Người dùng"), html.Th("Thao tác")])),
            html.Tbody([html.Tr([html.Td(chu_gio_vn(r.ts, "%H:%M:%S %d/%m/%Y")), html.Td(r.username or ""),
                                 html.Td(r.action)]) for r in log.itertuples()])
        ], className="simple")
        return (b_cols, b_rows, p_cols, p_rows, c_cols, c_rows, cc_badge, t_cols, t_rows,
                dm_ui, log_ui)

    # --- thêm bầy / phòng bằng hộp thoại
    @app.callback(Output("st-modal-bay", "className"),
                  Input("st-bay-them", "n_clicks"), Input("st-modal-bay-dong", "n_clicks"),
                  Input("st-modal-bay-huy", "n_clicks"), Input("st-bay-msg", "children"),
                  prevent_initial_call=True)
    def _mo_dong_bay(*_):
        return "modal mo" if ctx.triggered_id == "st-bay-them" else "modal"

    @app.callback(Output("st-modal-phong", "className"),
                  Input("st-phong-them", "n_clicks"), Input("st-modal-phong-dong", "n_clicks"),
                  Input("st-modal-phong-huy", "n_clicks"), Input("st-phong-msg", "children"),
                  prevent_initial_call=True)
    def _mo_dong_phong(*_):
        return "modal mo" if ctx.triggered_id == "st-phong-them" else "modal"

    @app.callback(Output("st-bay-xacnhan", "displayed"), Output("st-bay-xacnhan", "message"),
                  Input("st-bay-xoa", "n_clicks"), State("st-bay-grid", "selectedRows"),
                  prevent_initial_call=True)
    def _hoi_xoa_bay(n, chon):
        if not chon:
            return False, ""
        return True, (f"Xoá {len(chon)} bầy ({', '.join(r['ten'] for r in chon[:5])})? "
                      "Bầy còn phòng sẽ không xoá được.")

    @app.callback(Output("st-phong-xacnhan", "displayed"), Output("st-phong-xacnhan", "message"),
                  Input("st-phong-xoa", "n_clicks"), State("st-phong-grid", "selectedRows"),
                  prevent_initial_call=True)
    def _hoi_xoa_phong(n, chon):
        if not chon:
            return False, ""
        return True, (f"Xoá {len(chon)} phòng ({', '.join(r['ten'] for r in chon[:5])})? "
                      "Phòng đã có nhân sự hoặc số liệu thì nên đổi sang “Ngừng dùng”.")

    # --- lưu / thêm / xoá danh mục bầy
    @app.callback(Output("st-bay-msg", "children"), Output("st-modal-bay-msg", "children"),
                  Input("st-bay-luu", "n_clicks"), Input("st-modal-bay-ok", "n_clicks"),
                  Input("st-bay-xacnhan", "submit_n_clicks"),
                  State("st-bay-grid", "rowData"), State("st-bay-grid", "selectedRows"),
                  State("st-b-ten", "value"), State("st-b-tentong", "value"),
                  State("st-b-thutu", "value"), prevent_initial_call=True)
    def _bay_cb(_a, _b, _c, rows, chon, ten, ten_tong, thu_tu):
        trig = ctx.triggered_id
        if trig == "st-modal-bay-ok":
            if not (ten or "").strip():
                return no_update, alert("Chưa nhập tên bầy.", "bad")
            with session_scope() as s:
                luu_bay(s, [{"code": "", "ten": ten, "ten_tong": ten_tong,
                             "thu_tu": thu_tu or 99, "active": "Có"}])
            ghi_log("them_bay", ten)
            return alert([html.B(f"Đã tạo bầy “{ten}”. "),
                          "Chuyển phòng vào bầy này ở bảng bên dưới."], "ok"), ""
        if trig == "st-bay-xacnhan":
            with session_scope() as s:
                k, bo_qua = xoa_bay(s, [r["code"] for r in (chon or []) if r.get("code")])
            ghi_log("xoa_bay", f"{k} bầy")
            noi_dung = [html.B(f"Đã xoá {k} bầy. ")]
            if bo_qua:
                noi_dung.append("Bỏ qua: " + "; ".join(bo_qua))
            return alert(noi_dung, "warn" if bo_qua else "ok"), ""
        with session_scope() as s:
            k = luu_bay(s, rows or [])
        ghi_log("luu_danh_muc_bay", f"{k} bầy")
        return alert(f"Đã lưu danh mục Bầy: {k} bản ghi.", "ok"), ""

    # --- lưu / thêm / xoá danh mục phòng
    @app.callback(Output("st-phong-msg", "children"), Output("st-modal-phong-msg", "children"),
                  Input("st-phong-luu", "n_clicks"), Input("st-modal-phong-ok", "n_clicks"),
                  Input("st-phong-xacnhan", "submit_n_clicks"),
                  State("st-phong-grid", "rowData"), State("st-phong-grid", "selectedRows"),
                  State("st-p-ten", "value"), State("st-p-bay", "value"),
                  State("st-p-loai", "value"), State("st-p-cn", "value"),
                  State("st-p-nhomkhac", "value"), State("st-p-thutu", "value"),
                  prevent_initial_call=True)
    def _phong_cb(_a, _b, _c, rows, chon, ten, bay, loai, cn, nhom_khac, thu_tu):
        trig = ctx.triggered_id
        ten2code = {b["label"]: b["value"] for b in bay_options()}
        if trig == "st-modal-phong-ok":
            if not (ten or "").strip():
                return no_update, alert("Chưa nhập tên phòng.", "bad")
            with session_scope() as s:
                luu_phong(s, [{"code": "", "ten": ten, "bay": bay, "loai": loai, "chi_nhanh": cn,
                               "nhom_khac": nhom_khac or "", "thu_tu": thu_tu or 99,
                               "active": "Có"}], {**ten2code, bay: bay})
            ghi_log("them_phong", ten)
            return alert([html.B(f"Đã tạo phòng “{ten}”. "),
                          "Gán nhân sự cho phòng ở Quản trị → Danh mục nhân sự, rồi bấm "
                          "“Tính lại việc gán phòng”."], "ok"), ""
        if trig == "st-phong-xacnhan":
            with session_scope() as s:
                k, bo_qua = xoa_phong(s, [r["code"] for r in (chon or []) if r.get("code")])
            ghi_log("xoa_phong", f"{k} phòng")
            noi_dung = [html.B(f"Đã xoá {k} phòng. ")]
            if bo_qua:
                noi_dung.append("Bỏ qua: " + "; ".join(bo_qua))
            return alert(noi_dung, "warn" if bo_qua else "ok"), ""
        with session_scope() as s:
            k = luu_phong(s, rows or [], ten2code)
        ghi_log("luu_danh_muc_phong", f"{k} phòng")
        return alert([html.B(f"Đã lưu {k} phòng. "),
                      "Nếu vừa thêm phòng mới, nhớ gán nhân sự cho phòng đó rồi bấm "
                      "“Tính lại việc gán phòng”."], "ok"), ""

    # --- cơ cấu theo tháng
    @app.callback(Output("st-cocau-msg", "children"),
                  Input("st-cocau-luu", "n_clicks"), Input("st-cocau-copy", "n_clicks"),
                  Input("st-cocau-xoa", "n_clicks"),
                  State("st-cocau-grid", "rowData"), State("st-thang", "value"),
                  prevent_initial_call=True)
    def _luu_cocau(_a, _b, _c, rows, thang):
        ten2code = {b["label"]: b["value"] for b in bay_options()}
        if ctx.triggered_id == "st-cocau-xoa":
            with session_scope() as s:
                k = xoa_co_cau_thang(s, thang)
            ghi_log("xoa_co_cau_bay", f"{thang}: {k}")
            return alert(f"Kỳ {thang} quay lại dùng cơ cấu mặc định.", "info")
        if ctx.triggered_id == "st-cocau-copy":
            rows = [{"phong_code": p["code"], "bay": p["bay"], "thu_tu": p["thu_tu"]}
                    for p in phong_order(prev_month(thang))]
            nguon = f"sao chép từ kỳ {prev_month(thang)}"
        else:
            rows = [{"phong_code": r.get("phong_code"),
                     "bay": ten2code.get(r.get("bay"), r.get("bay")), "thu_tu": r.get("thu_tu")}
                    for r in (rows or [])]
            nguon = "cập nhật thủ công"
        with session_scope() as s:
            k = luu_co_cau_thang(s, thang, rows)
        xoa_cache_org(thang)
        ghi_log("luu_co_cau_bay", f"{thang}: {k} phòng ({nguon})")
        return alert(f"Đã lưu cơ cấu Bầy kỳ {thang}: {k} phòng ({nguon}).", "ok")

    # --- chỉ tiêu
    @app.callback(Output("st-target-msg", "children"),
                  Input("st-luu-target", "n_clicks"), Input("st-target-copy", "n_clicks"),
                  State("st-target-grid", "rowData"), State("st-thang", "value"),
                  prevent_initial_call=True)
    def _luu_target(_a, _b, rows, thang):
        if ctx.triggered_id == "st-target-copy":
            truoc = prev_month(thang)
            _, rows_truoc = _target_rows(truoc)
            n = _luu_target_rows(thang, rows_truoc, f"Sao chép từ kỳ {truoc}")
            ghi_log("sao_chep_chi_tieu", f"{thang} <- {truoc}: {n}")
            return alert(f"Đã sao chép {n} giá trị chỉ tiêu từ kỳ {truoc}.", "ok")
        n = _luu_target_rows(thang, rows, f"Cập nhật bởi {current_user.username}")
        ghi_log("luu_chi_tieu", f"{thang}: {n} giá trị")
        return alert(f"Đã lưu {n} giá trị chỉ tiêu cho kỳ {thang}.", "ok")

    # --- khác
    @app.callback(Output("st-recompute-msg", "children"), Input("st-recompute", "n_clicks"),
                  prevent_initial_call=True)
    def _recompute(n):
        with session_scope() as s:
            changed = recompute_phong(s)
        ghi_log("tinh_lai_phong", str(changed))
        return html.Span(f"Đã cập nhật {changed} hợp đồng.", className="badge ok")

    @app.callback(Output("st-mk-msg", "children"), Input("st-doi-mk", "n_clicks"),
                  State("st-mk-cu", "value"), State("st-mk-moi", "value"),
                  prevent_initial_call=True)
    def _doi_mk(n, cu, moi):
        err = doi_mat_khau(current_user.username, cu or "", moi or "")
        return alert(err, "bad") if err else alert("Đã đổi mật khẩu.", "ok")
