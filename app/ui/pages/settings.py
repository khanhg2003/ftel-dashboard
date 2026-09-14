"""Các tab Cơ cấu tổ chức, Chỉ tiêu, Nhật ký của trang Quản trị (trước là trang Cấu hình riêng).

Toàn bộ cơ cấu (Bầy, Phòng, cơ cấu theo tháng) và chỉ tiêu sửa được trên giao diện - không cần sửa file
cấu hình hay code. Trang Quản trị (quantri.py) ghép các phần này vào.

Như tab Tài khoản: không gõ thẳng vào ô. Bấm "✎ Sửa" cuối dòng (hoặc bấm đúp) mở hộp thoại điền sẵn,
kiểm tra hợp lệ rồi mới lưu từng dòng.
"""
from __future__ import annotations

import dash_ag_grid as dag
import pandas as pd
from dash import Input, Output, State, ctx, dcc, html, no_update
from flask_login import current_user
from sqlalchemy import delete, select, text

from app.auth import ghi_log
from app.db import engine, session_scope
from app.ingest.normalize import norm_text
from app.mau_nhap import ap_dung_co_cau, mau_co_cau, xem_truoc_co_cau
from app.metrics import cac_thang_co_du_lieu, prev_month
from app.models import Target
from app.org import (LOAI_PHONG, bay_info, bay_options, co_cau_rieng, luu_bay, luu_co_cau_thang,
                     luu_phong, phong_order, xoa_bay, xoa_cache_org, xoa_co_cau_thang, xoa_phong)
from app.thoi_gian import chu_gio_vn
from app.ui.components import (COT_SUA, MAU_LOAI_THAY_DOI, alert, callback_can_quyen, card, chon_ky,
                               dong_can_sua, field, gan_dieu_huong_ky, gan_import, modal, nut_import)
from app.ui.icons import icon

CHON = {"field": "_chon", "headerName": "", "width": 44, "maxWidth": 44, "pinned": "left",
        "checkboxSelection": True, "headerCheckboxSelection": True, "sortable": False,
        "resizable": False}

SO_DONG_NHAT_KY = 200
CHI_TIEU = [("internet", "Chỉ tiêu Internet"), ("camera", "Chỉ tiêu Camera"),
            ("ngay", "Chỉ tiêu mỗi ngày")]
TRANG_THAI = [{"label": "Đang dùng", "value": "Có"}, {"label": "Ngừng dùng", "value": "Không"}]
NHOM_KHAC = [{"label": "Không gộp", "value": ""}, {"label": "DNG Khác", "value": "DNG"},
             {"label": "QNM Khác", "value": "QNM"}]
AN = {"display": "none"}
SO = {"function": "params.value == null ? '' : Number(params.value).toLocaleString('vi-VN')"}
GRID_OPTS = {"rowSelection": "multiple", "suppressRowClickSelection": True, "suppressCellFocus": True,
             "tooltipShowDelay": 300}


def _grid(gid, cao: int | None = None, **kw):
    """cao=None -> bảng ngắn, để tự giãn. Có cao -> cuộn trong khung, tiêu đề cột luôn thấy."""
    kw.setdefault("defaultColDef", {"resizable": True, "sortable": True})
    opts = {**GRID_OPTS, "domLayout": "normal" if cao else "autoHeight"}
    style = {"width": "100%", **({"height": f"{cao}px"} if cao else {})}
    return dag.AgGrid(id=gid, className="ag-theme-quartz ag-theme-ftel", columnDefs=[], rowData=[],
                      dashGridOptions=opts, style=style, **kw)


def _o(label, control, id_=None, an=False):
    kw = {"id": id_, "style": AN if an else {}} if id_ else {}
    return html.Div([html.Label(label), control], className="field rong", **kw)


def _so_nhap(id_, **kw):
    return dcc.Input(id=id_, type="number", min=0, className="inp", **kw)


def _hop_thoai_bay():
    return modal("st-modal-bay", html.Span("Thêm bầy mới", id="st-bay-tieu-de"), [
        dcc.Store(id="st-bay-dang-sua"),
        html.Div([
            _o("Tên bầy *", dcc.Input(id="st-b-ten", type="text", placeholder="vd: BẦY 4", className="inp")),
            _o("Tên dòng tổng", dcc.Input(id="st-b-tentong", type="text", placeholder="vd: TỔNG BẦY 4",
                                          className="inp")),
            _o("Thứ tự hiển thị", _so_nhap("st-b-thutu", value=99, step=1)),
            _o("Trạng thái", dcc.Dropdown(id="st-b-active", clearable=False, searchable=False, value="Có",
                                          options=TRANG_THAI), id_="st-b-active-o", an=True),
        ], className="form-grid"),
        html.Div("Bầy là nhóm nhiều phòng kinh doanh, có dòng tổng riêng trên Báo cáo Tổng. Tạo xong, "
                 "chuyển phòng vào bầy ở bảng Phòng.", className="desc", style={"marginTop": "12px"}),
        html.Div(id="st-modal-bay-msg"),
    ], nut_chinh="Tạo bầy")


def _hop_thoai_phong():
    return modal("st-modal-phong", html.Span("Thêm phòng", id="st-phong-tieu-de"), [
        dcc.Store(id="st-phong-dang-sua"),
        html.Div([
            _o("Tên phòng *", dcc.Input(id="st-p-ten", type="text", placeholder="vd: IBB8", className="inp")),
            _o("Bầy mặc định *", dcc.Dropdown(id="st-p-bay", clearable=False, options=bay_options())),
            _o("Loại phòng *", dcc.Dropdown(id="st-p-loai", clearable=False, value="IBB", searchable=False,
                                            options=[{"label": x, "value": x} for x in LOAI_PHONG])),
            _o("Chi nhánh *", dcc.Dropdown(id="st-p-cn", clearable=False, value="DNG", searchable=False,
                                           options=[{"label": "Đà Nẵng", "value": "DNG"},
                                                    {"label": "Quảng Nam", "value": "QNM"}])),
            _o("Gộp vào nhóm Khác", dcc.Dropdown(id="st-p-nhomkhac", value="", clearable=False,
                                                 searchable=False, options=NHOM_KHAC)),
            _o("Thứ tự trong bầy", _so_nhap("st-p-thutu", value=99, step=1)),
            _o("Trạng thái", dcc.Dropdown(id="st-p-active", clearable=False, searchable=False, value="Có",
                                          options=TRANG_THAI), id_="st-p-active-o", an=True),
        ], className="form-grid"),
        html.Div("IBB / DIABAN là phòng bán hàng trực tiếp. Phòng kỹ thuật, CUS, ECOM thường gộp vào dòng "
                 "“Khác”. Phòng đã có số liệu thì chuyển Ngừng dùng thay vì xoá.", className="desc",
                 style={"marginTop": "12px"}),
        html.Div(id="st-modal-phong-msg"),
    ], nut_chinh="Tạo phòng")


def _hop_thoai_cocau():
    return modal("st-modal-cocau", html.Span("Cơ cấu kỳ", id="st-cocau-tieu-de"), [
        dcc.Store(id="st-cocau-dang-sua"),
        html.Div([
            _o("Thuộc bầy *", dcc.Dropdown(id="st-c-bay", clearable=False, options=bay_options())),
            _o("Thứ tự trong bầy", _so_nhap("st-c-thutu", step=1)),
        ], className="form-grid"),
        html.Div("Chỉ áp dụng cho kỳ đang chọn, không đổi các kỳ trước và bầy mặc định của phòng.",
                 className="desc", style={"marginTop": "12px"}),
        html.Div(id="st-modal-cocau-msg"),
    ], nut_chinh="Lưu thay đổi")


def _hop_thoai_chitieu():
    return modal("st-modal-target", html.Span("Chỉ tiêu", id="st-target-tieu-de"), [
        dcc.Store(id="st-target-dang-sua"),
        html.Div([_o(ten, _so_nhap(f"st-t-{ma}", step="any", placeholder="Chưa có"))
                  for ma, ten in CHI_TIEU], className="form-grid"),
        html.Div("Để trống ô nào là xoá chỉ tiêu đó của phòng trong kỳ này.", className="desc",
                 style={"marginTop": "12px"}),
        html.Div(id="st-modal-target-msg"),
    ], nut_chinh="Lưu chỉ tiêu")


TAB_CUA_TRANG = ("cocau", "chitieu", "nhatky")      # các tab của trang Quản trị do module này dựng


def hop_thoai() -> list:
    return [_hop_thoai_bay(), _hop_thoai_phong(), _hop_thoai_cocau(), _hop_thoai_chitieu(),
            dcc.ConfirmDialog(id="st-bay-xacnhan", message="Xoá các bầy đã chọn?"),
            dcc.ConfirmDialog(id="st-phong-xacnhan", message="Xoá các phòng đã chọn?")]


def chon_ky_ap_dung(tab: str):
    """Ô Kỳ áp dụng - chỉ hiện ở tab Cơ cấu tổ chức và Chỉ tiêu."""
    thangs = cac_thang_co_du_lieu() or ["2026-09"]
    return html.Div(field("Kỳ áp dụng", chon_ky("st-thang", thangs)), id="st-ky-wrap",
                    style={} if tab in ("cocau", "chitieu") else AN)


def _thanh(*nut, trai=None):
    return html.Div([*(trai or []), html.Div(className="grow"), *nut], className="toolbar")


def cac_tab(tab: str) -> list:
    return [
        # ------------------------------------------------ tab Cơ cấu tổ chức
        html.Div(id="st-pane-cocau", style={} if tab == "cocau" else AN, children=[
            html.Div([
                html.Div([html.H3("Nhập nhanh bằng Excel"),
                          html.Div("Tải file mẫu (điền sẵn bầy, phòng hiện có) → sửa hoặc thêm dòng → "
                                   "Import Excel. App cho xem trước từng thay đổi rồi mới ghi. Bầy, "
                                   "phòng không có trong file giữ nguyên.", className="desc")],
                         className="the-ten"),
                html.Div(nut_import("st-cc", "Tải file mẫu"), className="the-nut"),
            ], className="card the-dau"),
            card([
                _thanh(html.Button([icon("trash", 14), html.Span("Xoá")], id="st-bay-xoa", className="btn nguy-hiem"),
                       html.Button([icon("plus", 14), html.Span("Thêm bầy")], id="st-bay-them",
                                   className="btn primary")),
                html.Div(id="st-bay-msg"),
                _grid("st-bay-grid", getRowId="params.data.code"),
            ], title="Danh mục Bầy"),

            card([
                _thanh(html.Button([icon("trash", 14), html.Span("Xoá")], id="st-phong-xoa",
                                   className="btn nguy-hiem"),
                       html.Button([icon("plus", 14), html.Span("Thêm phòng")], id="st-phong-them",
                                   className="btn primary")),
                html.Div(id="st-phong-msg"),
                _grid("st-phong-grid", cao=400, getRowId="params.data.code"),
            ], title="Phòng", desc="Mỗi phòng thuộc một bầy mặc định"),

            card([
                _thanh(html.Button([icon("refresh", 14), html.Span("Dùng cơ cấu mặc định")],
                                   id="st-cocau-xoa", className="btn"),
                       html.Button([icon("copy", 14), html.Span("Sao chép kỳ trước")],
                                   id="st-cocau-copy", className="btn"),
                       trai=[html.Div(id="st-cocau-trangthai")]),
                html.Div(id="st-cocau-msg"),
                _grid("st-cocau-grid", cao=400, getRowId="params.data.phong_code"),
            ], title="Cơ cấu Bầy của kỳ đang chọn",
                desc="Xếp lại phòng vào bầy cho riêng kỳ này, không ảnh hưởng các kỳ trước"),
        ]),

        # ------------------------------------------------ tab Chỉ tiêu
        html.Div(id="st-pane-chitieu", style={} if tab == "chitieu" else AN, children=[
            card([
                _thanh(html.Button([icon("copy", 14), html.Span("Sao chép kỳ trước")],
                                   id="st-target-copy", className="btn"),
                       trai=[html.Div(id="st-target-tong", className="desc", style={"margin": 0})]),
                html.Div(id="st-target-msg"),
                _grid("st-target-grid", cao=460, getRowId="params.data.phong_code"),
            ], title="Chỉ tiêu tháng", desc="Chỉ tiêu của từng phòng - dùng để tính tỷ lệ hoàn thành kế hoạch"),
        ]),

        # ------------------------------------------------ tab Nhật ký
        html.Div(id="st-pane-nhatky", style={} if tab == "nhatky" else AN, children=[
            card([dag.AgGrid(id="st-log", className="ag-theme-quartz ag-theme-ftel", rowData=[],
                             columnDefs=[{"field": "luc", "headerName": "Thời điểm", "width": 160},
                                         {"field": "username", "headerName": "Người dùng", "width": 150},
                                         {"field": "action", "headerName": "Thao tác", "width": 190},
                                         {"field": "detail", "headerName": "Chi tiết", "flex": 1,
                                          "minWidth": 240, "tooltipField": "detail"}],
                             defaultColDef={"resizable": True, "sortable": True, "filter": True},
                             dashGridOptions={"suppressCellFocus": True, "domLayout": "normal"},
                             style={"width": "100%", "height": "560px"})],
                 title="Nhật ký hệ thống",
                 desc=f"{SO_DONG_NHAT_KY} thao tác gần nhất: đăng nhập, nạp, sửa, xoá, xuất file"),
        ]),
    ]


# ----------------------------------------------------------------- dữ liệu bảng
def _bay_rows():
    rows = [{"code": b["code"], "ten": b["ten"], "ten_tong": b.get("ten_tong") or f"TỔNG {b['ten'].upper()}",
             "thu_tu": b["thu_tu"], "so_phong": sum(1 for p in phong_order() if p["bay"] == b["code"])}
            for b in sorted(bay_info().values(), key=lambda x: x["thu_tu"])]
    cols = [
        CHON,
        {"field": "ten", "headerName": "Tên bầy", "minWidth": 160, "flex": 1.3},
        {"field": "ten_tong", "headerName": "Tên dòng tổng", "minWidth": 180, "flex": 1.5},
        {"field": "so_phong", "headerName": "Số phòng", "width": 100, "type": "numericColumn"},
        {"field": "thu_tu", "headerName": "Thứ tự", "width": 90, "type": "numericColumn"},
        {"field": "code", "headerName": "Mã", "width": 120},
        COT_SUA,
    ]
    return cols, rows


TEN_CN = {"DNG": "Đà Nẵng", "QNM": "Quảng Nam"}


def _phong_rows():
    ten_b = {c: b["ten"] for c, b in bay_info().items()}
    rows = [{"code": p["code"], "ten": p["ten"], "bay": ten_b.get(p["bay"], p["bay"]), "loai": p["loai"],
             "chi_nhanh": TEN_CN.get(p["chi_nhanh"], p["chi_nhanh"]),
             "nhom_khac": f"{p['nhom_khac']} Khác" if p.get("nhom_khac") else "", "thu_tu": p["thu_tu"]}
            for p in phong_order()]
    cols = [
        CHON,
        {"field": "ten", "headerName": "Tên phòng", "minWidth": 170, "flex": 1.4, "pinned": "left"},
        {"field": "bay", "headerName": "Bầy mặc định", "minWidth": 130, "flex": 1},
        {"field": "loai", "headerName": "Loại", "width": 100,
         "headerTooltip": "IBB / DIABAN (địa bàn) / KT / CUS / ECOM / KHAC"},
        {"field": "chi_nhanh", "headerName": "Chi nhánh", "width": 120},
        {"field": "nhom_khac", "headerName": "Gộp vào nhóm Khác", "minWidth": 150, "flex": 1},
        {"field": "thu_tu", "headerName": "Thứ tự", "width": 90, "type": "numericColumn"},
        {"field": "code", "headerName": "Mã", "width": 120},
        COT_SUA,
    ]
    return cols, rows


def _cocau_rows(thang: str):
    ten_b = {c: b["ten"] for c, b in bay_info().items()}
    mac_dinh = {p["code"]: p["bay"] for p in phong_order()}
    rows = [{"phong_code": p["code"], "phong": p["ten"], "bay": ten_b.get(p["bay"], p["bay"]),
             "thu_tu": p["thu_tu"],
             "khac_mac_dinh": "Khác mặc định" if mac_dinh.get(p["code"]) != p["bay"] else ""}
            for p in phong_order(thang)]
    cols = [
        {"field": "phong", "headerName": "Phòng", "minWidth": 180, "flex": 1.4, "pinned": "left"},
        {"field": "bay", "headerName": "Thuộc bầy", "minWidth": 150, "flex": 1.2, "cellStyle": {"fontWeight": "600"}},
        {"field": "thu_tu", "headerName": "Thứ tự trong bầy", "width": 150, "type": "numericColumn"},
        {"field": "khac_mac_dinh", "headerName": "Ghi chú", "minWidth": 130, "flex": 1,
         "cellStyle": {"color": "#B45309"}},
        COT_SUA,
    ]
    return cols, rows


def _target_rows(thang: str):
    df = pd.read_sql(text("""SELECT ma_doi_tuong, chi_tieu, gia_tri FROM target_monthly
                             WHERE thang = :t AND doi_tuong = 'PHONG'"""),
                     engine, params={"t": thang})
    pv = (df.pivot_table(index="ma_doi_tuong", columns="chi_tieu", values="gia_tri")
          if not df.empty else pd.DataFrame())
    ten_b = {c: b["ten"] for c, b in bay_info().items()}
    rows = []
    for p in phong_order(thang):
        row = {"phong_code": p["code"], "phong": p["ten"], "bay": ten_b.get(p["bay"], p["bay"])}
        for key, _ in CHI_TIEU:
            row[key] = (float(pv.at[p["code"], key])
                        if (not pv.empty and p["code"] in pv.index and key in pv.columns
                            and pd.notna(pv.at[p["code"], key])) else None)
        rows.append(row)
    cols = [{"field": "phong", "headerName": "Phòng", "pinned": "left", "minWidth": 180, "flex": 1.4},
            {"field": "bay", "headerName": "Bầy", "minWidth": 110, "flex": .9}]
    cols += [{"field": k, "headerName": t, "type": "numericColumn", "minWidth": 150, "flex": 1,
              "valueFormatter": SO} for k, t in CHI_TIEU]
    cols.append(COT_SUA)
    return cols, rows


def _luu_target_rows(thang: str, rows: list[dict], ghi_chu: str, xoa_o_trong: bool = False) -> int:
    n = 0
    with session_scope() as s:
        for r in rows or []:
            for key, _ in CHI_TIEU:
                val = r.get(key)
                dieu_kien = (Target.thang == thang, Target.doi_tuong == "PHONG",
                             Target.ma_doi_tuong == r["phong_code"], Target.chi_tieu == key)
                if val in (None, ""):
                    if xoa_o_trong:
                        s.execute(delete(Target).where(*dieu_kien))
                    continue
                try:
                    val = float(val)
                except (TypeError, ValueError):
                    continue
                row = s.execute(select(Target).where(*dieu_kien)).scalars().first()
                if row is None:
                    row = Target(thang=thang, doi_tuong="PHONG", ma_doi_tuong=r["phong_code"], chi_tieu=key)
                    s.add(row)
                row.gia_tri = val
                row.ghi_chu = ghi_chu
                n += 1
    return n


def _so_nguyen(v, mac_dinh=None):
    try:
        return int(v) if v not in (None, "") else mac_dinh
    except (TypeError, ValueError):
        return mac_dinh


def _ten_ky(thang: str | None) -> str:
    return f"{thang[5:7]}/{thang[:4]}" if thang else ""


# ----------------------------------------------------------------- lưu từ hộp thoại
def luu_bay_hop_thoai(code: str | None, ten, ten_tong, thu_tu, active) -> tuple[bool, str]:
    ten = norm_text(ten)
    if not ten:
        return False, "Chưa nhập tên bầy."
    thu_tu = _so_nguyen(thu_tu)
    if thu_tu is None or thu_tu < 0:
        return False, "Thứ tự phải là số nguyên từ 0."
    if any(b["ten"].lower() == ten.lower() and b["code"] != code for b in bay_info().values()):
        return False, f"Đã có bầy tên “{ten}”."
    ngung = active == "Không"
    if code and ngung and any(p["bay"] == code for p in phong_order()):
        return False, "Bầy còn phòng: chuyển các phòng sang bầy khác trước khi ngừng dùng."
    with session_scope() as s:
        luu_bay(s, [{"code": code or "", "ten": ten, "ten_tong": ten_tong, "thu_tu": thu_tu,
                     "active": "Không" if ngung else "Có"}])
    ghi_log("sua_bay" if code else "them_bay", f"{code or ''} {ten}".strip())
    return True, (f"Đã lưu bầy “{ten}”." + (" Bầy đã ngừng dùng, không còn hiện trên báo cáo." if ngung else "")
                  if code else f"Đã tạo bầy “{ten}”. Chuyển phòng vào bầy này ở bảng Phòng.")


def luu_phong_hop_thoai(code: str | None, d: dict) -> tuple[bool, str]:
    ten = norm_text(d.get("ten"))
    if not ten:
        return False, "Chưa nhập tên phòng."
    if d.get("bay") not in bay_info():
        return False, "Chưa chọn bầy."
    if d.get("loai") not in LOAI_PHONG or d.get("chi_nhanh") not in TEN_CN:
        return False, "Loại phòng hoặc chi nhánh không hợp lệ."
    thu_tu = _so_nguyen(d.get("thu_tu"))
    if thu_tu is None or thu_tu < 0:
        return False, "Thứ tự phải là số nguyên từ 0."
    if any(p["ten"].lower() == ten.lower() and p["code"] != code for p in phong_order()):
        return False, f"Đã có phòng tên “{ten}”."
    ngung = d.get("active") == "Không"
    with session_scope() as s:
        luu_phong(s, [{"code": code or "", "ten": ten, "bay": d["bay"], "loai": d["loai"],
                       "chi_nhanh": d["chi_nhanh"], "nhom_khac": d.get("nhom_khac") or "", "thu_tu": thu_tu,
                       "active": "Không" if ngung else "Có"}], {})
    ghi_log("sua_phong" if code else "them_phong", f"{code or ''} {ten}".strip())
    if not code:
        return True, f"Đã tạo phòng “{ten}”. Gán nhân sự cho phòng ở tab Danh mục nhân sự."
    return True, f"Đã lưu phòng “{ten}”." + (" Phòng đã ngừng dùng, không còn hiện trên báo cáo." if ngung else "")


# ----------------------------------------------------------------- callbacks
def register(app):
    cb = callback_can_quyen(app, "duoc_cau_hinh")   # mọi thao tác ở trang này chỉ dành cho Quản trị
    gan_dieu_huong_ky(app, "st-thang")
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

    @cb(Output("st-pane-cocau", "style"), Output("st-pane-chitieu", "style"),
        Output("st-pane-nhatky", "style"), Output("st-ky-wrap", "style"), Input("qt-tab", "value"),
        prevent_initial_call=True)
    def _tab(tab):
        return ({} if tab == "cocau" else AN, {} if tab == "chitieu" else AN,
                {} if tab == "nhatky" else AN, {} if tab in ("cocau", "chitieu") else AN)

    @cb(Output("st-log", "rowData"), Input("qt-tab", "value"))
    def _nhat_ky(tab):
        if tab != "nhatky":
            return no_update
        log = pd.read_sql(text(f"""SELECT ts, username, action, detail FROM audit_log
                                   ORDER BY id DESC LIMIT {SO_DONG_NHAT_KY}"""), engine)
        return [{"luc": chu_gio_vn(r.ts, "%H:%M:%S %d/%m/%Y"), "username": r.username or "",
                 "action": r.action, "detail": r.detail or ""} for r in log.itertuples()]

    @cb(Output("st-bay-grid", "columnDefs"), Output("st-bay-grid", "rowData"),
        Output("st-phong-grid", "columnDefs"), Output("st-phong-grid", "rowData"),
        Output("st-cocau-grid", "columnDefs"), Output("st-cocau-grid", "rowData"),
        Output("st-cocau-trangthai", "children"),
        Output("st-target-grid", "columnDefs"), Output("st-target-grid", "rowData"),
        Output("st-target-tong", "children"),
        Output("st-p-bay", "options"), Output("st-c-bay", "options"),
        Input("st-thang", "value"), Input("st-bay-msg", "children"),
        Input("st-phong-msg", "children"), Input("st-cocau-msg", "children"),
        Input("st-target-msg", "children"))
    def _nap(thang, *_):
        b_cols, b_rows = _bay_rows()
        p_cols, p_rows = _phong_rows()
        c_cols, c_rows = _cocau_rows(thang)
        t_cols, t_rows = _target_rows(thang)
        cc_badge = (html.Span(f"Kỳ {_ten_ky(thang)} đang dùng cơ cấu riêng", className="badge ok")
                    if co_cau_rieng(thang) else
                    html.Span(f"Kỳ {_ten_ky(thang)} đang dùng cơ cấu mặc định", className="badge muted"))
        from app.overview import phong_khong_cong_tong
        bo = phong_khong_cong_tong()
        co = sum(1 for r in t_rows if r.get("internet") is not None)
        tong = sum(r.get("internet") or 0 for r in t_rows if r["phong_code"] not in bo)
        t_tong = (f"Kỳ {_ten_ky(thang)} · {co}/{len(t_rows)} phòng có chỉ tiêu Internet · tổng chi nhánh "
                  f"{tong:,.0f}".replace(",", ".") + (" (không cộng ANCS, như Báo cáo Tổng)" if bo else ""))
        opts = bay_options()
        return (b_cols, b_rows, p_cols, p_rows, c_cols, c_rows, cc_badge, t_cols, t_rows, t_tong, opts, opts)

    # ------------------------------------------------ bầy
    @cb(Output("st-modal-bay", "className"), Output("st-bay-tieu-de", "children"),
        Output("st-modal-bay-ok", "children"), Output("st-bay-dang-sua", "data"),
        Output("st-b-ten", "value"), Output("st-b-tentong", "value"), Output("st-b-thutu", "value"),
        Output("st-b-active", "value"), Output("st-b-active-o", "style"),
        Output("st-modal-bay-msg", "children", allow_duplicate=True),
        Input("st-bay-them", "n_clicks"), Input("st-bay-grid", "cellClicked"),
        Input("st-bay-grid", "cellDoubleClicked"), Input("st-modal-bay-dong", "n_clicks"),
        Input("st-modal-bay-huy", "n_clicks"), Input("st-bay-msg", "children"), prevent_initial_call=True)
    def _mo_dong_bay(_them, bam, bam_dup, *_):
        giu = (no_update,) * 9
        if ctx.triggered_id == "st-bay-them":
            return "modal mo", "Thêm bầy mới", "Tạo bầy", None, "", "", 99, "Có", AN, ""
        if ctx.triggered_id == "st-bay-grid":
            b = bay_info().get(dong_can_sua(bam, bam_dup) or "")
            if not b:
                return (no_update,) + giu
            return ("modal mo", f"Sửa bầy · {b['ten']}", "Lưu thay đổi", b["code"], b["ten"],
                    b.get("ten_tong") or "", b["thu_tu"], "Có", {}, "")
        return ("modal",) + giu

    @cb(Output("st-bay-xacnhan", "displayed"), Output("st-bay-xacnhan", "message"),
        Input("st-bay-xoa", "n_clicks"), State("st-bay-grid", "selectedRows"), prevent_initial_call=True)
    def _hoi_xoa_bay(n, chon):
        if not chon:
            return False, ""
        return True, (f"Xoá {len(chon)} bầy ({', '.join(r['ten'] for r in chon[:5])})? "
                      "Bầy còn phòng sẽ không xoá được.")

    @cb(Output("st-bay-msg", "children"), Output("st-modal-bay-msg", "children"),
        Input("st-modal-bay-ok", "n_clicks"), Input("st-bay-xoa", "n_clicks"),
        Input("st-bay-xacnhan", "submit_n_clicks"),
        State("st-bay-grid", "selectedRows"), State("st-bay-dang-sua", "data"),
        State("st-b-ten", "value"), State("st-b-tentong", "value"),
        State("st-b-thutu", "value"), State("st-b-active", "value"), prevent_initial_call=True)
    def _bay_cb(_ok, _xoa, _xn, chon, code, ten, ten_tong, thu_tu, active):
        trig = ctx.triggered_id
        if trig == "st-modal-bay-ok":
            ok, msg = luu_bay_hop_thoai(code, ten, ten_tong, thu_tu, active)
            return (alert(msg, "ok"), "") if ok else (no_update, alert(msg, "bad"))
        if trig == "st-bay-xoa":
            return (alert("Tích chọn bầy cần xoá trước đã.", "warn"), no_update) if not chon \
                else (no_update, no_update)
        if trig == "st-bay-xacnhan":
            with session_scope() as s:
                k, bo_qua = xoa_bay(s, [r["code"] for r in (chon or []) if r.get("code")])
            ghi_log("xoa_bay", f"{k} bầy")
            noi_dung = [html.B(f"Đã xoá {k} bầy. ")]
            if bo_qua:
                noi_dung.append("Bỏ qua: " + "; ".join(bo_qua))
            return alert(noi_dung, "warn" if bo_qua else "ok"), no_update
        return no_update, no_update

    # ------------------------------------------------ phòng
    @cb(Output("st-modal-phong", "className"), Output("st-phong-tieu-de", "children"),
        Output("st-modal-phong-ok", "children"), Output("st-phong-dang-sua", "data"),
        Output("st-p-ten", "value"), Output("st-p-bay", "value"), Output("st-p-loai", "value"),
        Output("st-p-cn", "value"), Output("st-p-nhomkhac", "value"), Output("st-p-thutu", "value"),
        Output("st-p-active", "value"), Output("st-p-active-o", "style"),
        Output("st-modal-phong-msg", "children", allow_duplicate=True),
        Input("st-phong-them", "n_clicks"), Input("st-phong-grid", "cellClicked"),
        Input("st-phong-grid", "cellDoubleClicked"), Input("st-modal-phong-dong", "n_clicks"),
        Input("st-modal-phong-huy", "n_clicks"), Input("st-phong-msg", "children"), prevent_initial_call=True)
    def _mo_dong_phong(_them, bam, bam_dup, *_):
        giu = (no_update,) * 12
        if ctx.triggered_id == "st-phong-them":
            bays = bay_options()
            return ("modal mo", "Thêm phòng", "Tạo phòng", None, "", bays[0]["value"] if bays else None, "IBB",
                    "DNG", "", 99, "Có", AN, "")
        if ctx.triggered_id == "st-phong-grid":
            code = dong_can_sua(bam, bam_dup)
            p = next((x for x in phong_order() if x["code"] == code), None)
            if not p:
                return (no_update,) + giu
            return ("modal mo", f"Sửa phòng · {p['ten']}", "Lưu thay đổi", p["code"], p["ten"], p["bay"],
                    p["loai"], p["chi_nhanh"], p.get("nhom_khac") or "", p["thu_tu"], "Có", {}, "")
        return ("modal",) + giu

    @cb(Output("st-phong-xacnhan", "displayed"), Output("st-phong-xacnhan", "message"),
        Input("st-phong-xoa", "n_clicks"), State("st-phong-grid", "selectedRows"), prevent_initial_call=True)
    def _hoi_xoa_phong(n, chon):
        if not chon:
            return False, ""
        return True, (f"Xoá {len(chon)} phòng ({', '.join(r['ten'] for r in chon[:5])})? "
                      "Phòng đã có nhân sự hoặc số liệu thì nên chuyển sang Ngừng dùng.")

    @cb(Output("st-phong-msg", "children"), Output("st-modal-phong-msg", "children"),
        Input("st-modal-phong-ok", "n_clicks"), Input("st-phong-xoa", "n_clicks"),
        Input("st-phong-xacnhan", "submit_n_clicks"),
        State("st-phong-grid", "selectedRows"), State("st-phong-dang-sua", "data"),
        State("st-p-ten", "value"), State("st-p-bay", "value"), State("st-p-loai", "value"),
        State("st-p-cn", "value"), State("st-p-nhomkhac", "value"), State("st-p-thutu", "value"),
        State("st-p-active", "value"), prevent_initial_call=True)
    def _phong_cb(_ok, _xoa, _xn, chon, code, ten, bay, loai, cn, nhom_khac, thu_tu, active):
        trig = ctx.triggered_id
        if trig == "st-modal-phong-ok":
            ok, msg = luu_phong_hop_thoai(code, {"ten": ten, "bay": bay, "loai": loai, "chi_nhanh": cn,
                                                 "nhom_khac": nhom_khac, "thu_tu": thu_tu, "active": active})
            return (alert(msg, "ok"), "") if ok else (no_update, alert(msg, "bad"))
        if trig == "st-phong-xoa":
            return (alert("Tích chọn phòng cần xoá trước đã.", "warn"), no_update) if not chon \
                else (no_update, no_update)
        if trig == "st-phong-xacnhan":
            with session_scope() as s:
                k, bo_qua = xoa_phong(s, [r["code"] for r in (chon or []) if r.get("code")])
            ghi_log("xoa_phong", f"{k} phòng")
            noi_dung = [html.B(f"Đã xoá {k} phòng. ")]
            if bo_qua:
                noi_dung.append("Bỏ qua: " + "; ".join(bo_qua))
            return alert(noi_dung, "warn" if bo_qua else "ok"), no_update
        return no_update, no_update

    # ------------------------------------------------ cơ cấu theo kỳ
    @cb(Output("st-modal-cocau", "className"), Output("st-cocau-tieu-de", "children"),
        Output("st-cocau-dang-sua", "data"), Output("st-c-bay", "value"), Output("st-c-thutu", "value"),
        Output("st-modal-cocau-msg", "children", allow_duplicate=True),
        Input("st-cocau-grid", "cellClicked"), Input("st-cocau-grid", "cellDoubleClicked"),
        Input("st-modal-cocau-dong", "n_clicks"), Input("st-modal-cocau-huy", "n_clicks"),
        Input("st-cocau-msg", "children"), State("st-thang", "value"), prevent_initial_call=True)
    def _mo_dong_cocau(bam, bam_dup, _d, _h, _m, thang):
        giu = (no_update,) * 5
        if ctx.triggered_id == "st-cocau-grid":
            code = dong_can_sua(bam, bam_dup)
            p = next((x for x in phong_order(thang) if x["code"] == code), None)
            if not p:
                return (no_update,) + giu
            return "modal mo", f"Cơ cấu kỳ {_ten_ky(thang)} · {p['ten']}", p["code"], p["bay"], p["thu_tu"], ""
        return ("modal",) + giu

    @cb(Output("st-cocau-msg", "children"), Output("st-modal-cocau-msg", "children"),
        Input("st-modal-cocau-ok", "n_clicks"), Input("st-cocau-copy", "n_clicks"),
        Input("st-cocau-xoa", "n_clicks"),
        State("st-cocau-dang-sua", "data"), State("st-c-bay", "value"), State("st-c-thutu", "value"),
        State("st-thang", "value"), prevent_initial_call=True)
    def _luu_cocau(_ok, _copy, _xoa, code, bay, thu_tu, thang):
        trig = ctx.triggered_id
        if trig == "st-cocau-xoa":
            with session_scope() as s:
                k = xoa_co_cau_thang(s, thang)
            ghi_log("xoa_co_cau_bay", f"{thang}: {k}")
            return alert(f"Kỳ {_ten_ky(thang)} quay lại dùng cơ cấu mặc định.", "info"), no_update
        if trig == "st-cocau-copy":
            rows = [{"phong_code": p["code"], "bay": p["bay"], "thu_tu": p["thu_tu"]}
                    for p in phong_order(prev_month(thang))]
            with session_scope() as s:
                k = luu_co_cau_thang(s, thang, rows)
            xoa_cache_org(thang)
            ghi_log("luu_co_cau_bay", f"{thang}: {k} phòng (sao chép từ kỳ {prev_month(thang)})")
            return alert(f"Đã sao chép cơ cấu kỳ {_ten_ky(prev_month(thang))} sang kỳ {_ten_ky(thang)}.",
                         "ok"), no_update
        if trig == "st-modal-cocau-ok":
            if bay not in bay_info():
                return no_update, alert("Chưa chọn bầy.", "bad")
            thu_tu = _so_nguyen(thu_tu)
            if thu_tu is None or thu_tu < 0:
                return no_update, alert("Thứ tự phải là số nguyên từ 0.", "bad")
            p = next((x for x in phong_order(thang) if x["code"] == code), None)
            if not p:
                return no_update, alert("Phòng này không còn trong danh mục.", "bad")
            with session_scope() as s:
                luu_co_cau_thang(s, thang, [{"phong_code": code, "bay": bay, "thu_tu": thu_tu}])
            xoa_cache_org(thang)
            ghi_log("luu_co_cau_bay", f"{thang}: {p['ten']} → {bay_info()[bay]['ten']}")
            return alert(f"Kỳ {_ten_ky(thang)}: {p['ten']} thuộc {bay_info()[bay]['ten']}.", "ok"), ""
        return no_update, no_update

    # ------------------------------------------------ chỉ tiêu
    @cb(Output("st-modal-target", "className"), Output("st-target-tieu-de", "children"),
        Output("st-target-dang-sua", "data"),
        *[Output(f"st-t-{ma}", "value") for ma, _ in CHI_TIEU],
        Output("st-modal-target-msg", "children", allow_duplicate=True),
        Input("st-target-grid", "cellClicked"), Input("st-target-grid", "cellDoubleClicked"),
        Input("st-modal-target-dong", "n_clicks"), Input("st-modal-target-huy", "n_clicks"),
        Input("st-target-msg", "children"), State("st-thang", "value"), prevent_initial_call=True)
    def _mo_dong_target(bam, bam_dup, _d, _h, _m, thang):
        giu = (no_update,) * (3 + len(CHI_TIEU))
        if ctx.triggered_id == "st-target-grid":
            code = dong_can_sua(bam, bam_dup)
            _, rows = _target_rows(thang)
            r = next((x for x in rows if x["phong_code"] == code), None)
            if not r:
                return (no_update,) + giu
            return ("modal mo", f"Chỉ tiêu tháng {_ten_ky(thang)} · {r['phong']}", code,
                    *[r.get(ma) for ma, _ in CHI_TIEU], "")
        return ("modal",) + giu

    @cb(Output("st-target-msg", "children"), Output("st-modal-target-msg", "children"),
        Input("st-modal-target-ok", "n_clicks"), Input("st-target-copy", "n_clicks"),
        State("st-target-dang-sua", "data"), *[State(f"st-t-{ma}", "value") for ma, _ in CHI_TIEU],
        State("st-thang", "value"), prevent_initial_call=True)
    def _luu_target(_ok, _copy, code, *gia_tri):
        *gia_tri, thang = gia_tri
        if ctx.triggered_id == "st-target-copy":
            truoc = prev_month(thang)
            _, rows_truoc = _target_rows(truoc)
            n = _luu_target_rows(thang, rows_truoc, f"Sao chép từ kỳ {truoc}")
            ghi_log("sao_chep_chi_tieu", f"{thang} <- {truoc}: {n}")
            return alert(f"Đã sao chép {n} giá trị chỉ tiêu từ kỳ {_ten_ky(truoc)}.", "ok"), no_update
        if ctx.triggered_id == "st-modal-target-ok":
            if code not in {p["code"] for p in phong_order(thang)}:
                return no_update, alert("Phòng này không còn trong danh mục.", "bad")
            d = {"phong_code": code}
            for (ma, ten), v in zip(CHI_TIEU, gia_tri):
                if v not in (None, "") and (not isinstance(v, (int, float)) or v < 0):
                    return no_update, alert(f"{ten} phải là số từ 0.", "bad")
                d[ma] = v
            _luu_target_rows(thang, [d], f"Cập nhật bởi {current_user.username}", xoa_o_trong=True)
            ten_p = next(p["ten"] for p in phong_order(thang) if p["code"] == code)
            ghi_log("luu_chi_tieu", f"{thang} {ten_p}: " + ", ".join(f"{ma}={d[ma]}" for ma, _ in CHI_TIEU))
            return alert(f"Đã lưu chỉ tiêu tháng {_ten_ky(thang)} của {ten_p}.", "ok"), ""
        return no_update, no_update
