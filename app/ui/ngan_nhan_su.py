"""Ngăn chi tiết MỘT nhân sự, mở được từ mọi bảng có danh sách nhân sự.

Cách dùng ở một trang: gắn lớp `nhan-su-bam` cho bảng (xem `lop()`), trong dữ liệu mỗi dòng có `acc_norm` hoặc `acc`,
rồi đặt `goi_y()` gần bảng. `assets/nhan_su_bam.js` bắt thao tác bấm đúp, ghi người được chọn vào `dcc.Store` `ns-mo`;
ngăn trượt ra ngay (không chờ máy chủ), vòng xoay hiện trong lúc máy chủ dựng nội dung.

Quyền kiểm ở máy chủ, không tin gì từ trình duyệt gửi lên: tài khoản phải được xem chi tiết nhân sự và phòng của
người đó phải nằm trong phạm vi `phong_nhan_su()` (AGENTS.md mục 5). Kỳ lấy từ bộ lọc chung `ky-chung` (ngày đang
xem ở trang), luỹ kế từ ngày 01 của tháng.
"""
from __future__ import annotations

from datetime import date

import dash_ag_grid as dag
from dash import Input, Output, State, dcc, html, no_update
from flask_login import current_user
from sqlalchemy import text

from app import bao_cao_phong as bp
from app import canh_bao as quy_tac
from app import ho_so_nhan_su
from app.auth import ghi_log
from app.db import engine
from app.metrics import cac_ngay_co_du_lieu, month_range
from app.ui import ky_chung as kc
from app.ui.components import LOCALE_VI
from app.ui.icons import icon
from app.ui.pages import phong_ho_so as hs_ui
from app.ui.pages.phong_ho_so import DO, _o, _pct, _so

STORE = "ns-mo"
LOP_BAM = "nhan-su-bam"
LOP_BAM_TEN = "nhan-su-bam nhan-su-bam-ten"      # bảng có ô sửa được: chỉ ô tên mở ngăn, ô khác vẫn sửa như thường
LOP_BAM_1 = "nhan-su-bam nhan-su-bam-1"          # bảng chỉ để xem: bấm một lần là mở
GOI_Y = "Bấm đúp vào một nhân sự để xem chi tiết đầy đủ."


def lop(kieu: str = "xem") -> str:
    """Lớp CSS cho bảng nhân sự: 'xem' bấm đúp, 'mot' bấm một lần, 'ten' chỉ bấm đúp ở ô tên (bảng nhập liệu)."""
    return {"xem": LOP_BAM, "mot": LOP_BAM_1, "ten": LOP_BAM_TEN}[kieu]


def goi_y(chu: str = GOI_Y, **kw) -> html.Div:
    """Dòng nhắc người xem rằng dòng nhân sự bấm được - đặt ngay trên hoặc dưới bảng."""
    return html.Div([icon("users", 13), html.Span(chu)], className="goi-y-bam", **kw)


def khung() -> html.Div:
    """Ngăn trượt + kho lưu người được chọn. Đặt MỘT lần ở khung app (app/ui/app.py)."""
    return html.Div([
        dcc.Store(id=STORE),
        html.Div(id="ns-ngan-nen", className="ngan-nen"),
        html.Div([
            html.Div([html.Div(id="ns-ngan-tieu-de", className="grow"),
                      html.Button("×", id="ns-ngan-dong", className="modal-x", title="Đóng (Esc)")],
                     className="ngan-dau"),
            dcc.Loading(html.Div(id="ns-ngan-than", className="ngan-than"), type="circle",
                        className="ngan-tai"),
        ], className="ngan-hop"),
    ], id="ns-ngan", className="ngan")


# ------------------------------------------------------------------ chọn phòng + dựng nội dung
def _phong_duoc_xem() -> set[str]:
    from app.ui.pages.phong import phong_duoc_chon
    return {o["value"] for o in phong_duoc_chon()} if current_user.duoc_xem_nhan_su else set()


def _ung_vien(acc: str, thang: str, goi_y_phong: list[str | None]) -> list[str]:
    """Các phòng có thể là phòng của người này trong tháng, theo thứ tự thử: gợi ý của trình duyệt, danh mục nhân sự,
    rồi phòng ghi trên hợp đồng. Chỉ giữ phòng tài khoản được xem."""
    duoc = _phong_duoc_xem()
    tu_d, den_d, _ = month_range(thang)
    tu, den = tu_d.isoformat(), den_d.isoformat()
    with engine.connect() as c:
        dm = [r[0] for r in c.execute(text(
            """SELECT phong_code FROM staff_map WHERE acc_norm = :a AND (hieu_luc_den IS NULL OR hieu_luc_den >= :tu)
               AND (hieu_luc_tu IS NULL OR hieu_luc_tu <= :den) ORDER BY hieu_luc_tu DESC"""),
            {"a": acc, "tu": tu, "den": den})]
        hd = [r[0] for r in c.execute(text(
            """SELECT phong_code FROM fact_internet WHERE acc_norm = :a AND ((ngay_online >= :tu AND ngay_online <= :den)
               OR (ngay_tao_hd >= :tu AND ngay_tao_hd <= :den)) GROUP BY phong_code ORDER BY COUNT(*) DESC"""),
            {"a": acc, "tu": tu, "den": den})]
    ra: list[str] = []
    for code in [*goi_y_phong, *dm, *hd]:
        if code and code in duoc and code not in ra:
            ra.append(code)
    return ra


def _chua_co(tieu: str, nd: str):
    return html.Div(tieu), [html.Div(nd, className="desc")]


def noi_dung(acc: str, goi_y_phong: list[str | None], den_iso: str | None):
    """(tiêu đề, thân) của ngăn cho một nhân sự, hoặc thông báo vì sao chưa mở được."""
    from app import phong_online as po
    la_online = current_user.role == "online"      # tài khoản Phòng Online: chỉ 5 người của nhóm, không phải cả IBB2
    if la_online and not po.la_nguoi_online(acc):
        return _chua_co("Không có quyền", "Tài khoản này chỉ xem được nhân sự của Phòng Online.")
    if not (current_user.duoc_xem_nhan_su or la_online):
        return _chua_co("Không có quyền", "Tài khoản này không có quyền xem chi tiết nhân sự.")
    ngays = cac_ngay_co_du_lieu()
    den = kc.ngay_co_so(den_iso, ngays)
    if not den or not acc:
        return _chua_co("Chưa có số liệu", "Chưa có số liệu để xem chi tiết nhân sự này.")
    d = date.fromisoformat(den)
    thang = f"{d.year}-{d.month:02d}"
    for code in ([po.phong_goc()] if la_online else _ung_vien(acc, thang, goi_y_phong)):
        nv = bp.bang_nhan_su(thang, d.day, code)
        r = nv[(nv.acc_norm == acc) & (nv.loai_dong == "data")]
        if not r.empty:
            return _ngan_noi_dung(thang, d.day, code, r.iloc[0].to_dict())
    return _chua_co("Chưa có chi tiết", "Không có số liệu của nhân sự này trong các phòng tài khoản được xem "
                    f"(luỹ kế 01 - {d:%d/%m/%Y}).")


def _ngan_noi_dung(thang: str, ngay: int, code: str, r: dict):
    from app.ui.pages.phong import _bieu_do
    ds = bp.dien_bien_nhan_su(thang, ngay, r["acc_norm"])
    cho = bp.hop_dong_cho_cua_nhan_su(r["acc_norm"], code)
    ghi_log("xem_nhan_su", f"{code}: {r.get('acc')}")
    chenh = r.get("chenh_ck") or 0
    ngay_lien = r.get("ngay_lien_chua_co_so")
    chu_y = [x for x in (r.get("chu_y") or "").split(" · ") if x]
    muc = r.get("muc_chu_y") or ""
    d = date(int(thang[:4]), int(thang[5:7]), ngay)

    hang = r.get("hang")
    tieu_de = html.Div([html.H3(f"{r.get('ho_ten')}" + (f" · hạng {int(hang)}" if hang else "")),
                        html.Div(f"{r.get('acc')} · {bp.ten_phong(code)} · thâm niên "
                                 f"{r.get('tham_nien_bucket') or '–'} tháng · "
                                 f"{r.get('vi_tri') or 'chưa có hồ sơ NSLĐ'}", className="sub"),
                        html.Div(f"Số liệu luỹ kế 01 - {d:%d/%m/%Y}. Đổi ngày ở bộ lọc của trang để xem kỳ khác.",
                                 className="sub")])
    than = [
        html.Div(([html.Span(muc, className="badge bad" if muc == quy_tac.TRAO_DOI_NGAY else "badge warn",
                             style={"marginRight": "6px"})] if muc else [])
                 + ([html.Span(x, className="ct-chip") for x in chu_y] if chu_y else
                    [html.Span("Không có điểm cần chú ý", className="ct-chip ok")]),
                 style={"marginBottom": "8px"}),
        html.Div([
            _o("Online tháng", _so(r.get("online")),
               f"Cùng kỳ {_so(r.get('ck_online'))} ({'+' if chenh > 0 else ''}{chenh})"),
            _o("Bán mới tháng", _so(r.get("ban_moi")),
               f"Ngày {ngay:02d}: bán mới {_so(r.get('ban_moi_ngay'))}, online "
               f"{_so(r.get('online_ngay'))}"),
            _o("Số ngày có số", f"{int(r.get('so_ngay_co_so') or 0)}/{ngay}",
               "Chưa có số trong 2 tháng" if ngay_lien is None else
               ("Có số ngày gần nhất" if ngay_lien == 0 else f"{int(ngay_lien)} ngày liền chưa có số")),
            _o("V.VIP", _so(r.get("vvip")), f"VVIP/PTTB {_pct(r.get('kem_vvip'))}"),
            _o("Camera", _so(r.get("camera")), f"Camera/PTTB {_pct(r.get('kem_camera'))}"),
            _o("Chưa online", _so(r.get("ton")), f"{_so(r.get('ton_qua_7'))} hợp đồng chờ từ 7 ngày"),
            _o("Online trong 1 ngày", _pct(r.get("onl_1_ngay")), "Trong ngày tạo hoặc hôm sau"),
            _o("Đủ 3 DV · Trả trước", f"{_pct(r.get('du_3'))} · {_pct(r.get('tra_truoc'))}"),
            _o("Tuần này", _so(r.get("tuan_nay")), f"Tuần trước {_so(r.get('tuan_truoc'))} · NSLĐ kỳ "
                                                   f"trước {r.get('ket_luan') or '–'}"),
        ], className="ct-luoi"),
        dcc.Link([icon("users", 14), html.Span("Xem NSLĐ và thâm niên của phòng")], href="/hr",
                 className="btn nho", style={"marginTop": "10px"}),
        html.H4("Online và bán mới từng ngày"),
        dcc.Graph(figure=_bieu_do(ds, height=250), config={"displayModeBar": False, "responsive": True}),
        *hs_ui.phan_ho_so(ho_so_nhan_su.ho_so(thang, ngay, code, r["acc_norm"])),
        html.H4(f"Hợp đồng chưa online ({len(cho)})"),
        dag.AgGrid(
            className="ag-theme-quartz ag-theme-ftel", rowData=cho.to_dict("records"),
            columnDefs=[{"field": "hop_dong", "headerName": "Hợp đồng", "flex": 1, "minWidth": 110},
                        {"field": "goi_dich_vu", "headerName": "Gói", "flex": .8, "minWidth": 80},
                        {"field": "nguon_ban", "headerName": "Nguồn", "flex": .8, "minWidth": 80},
                        {"field": "ngay_tao", "headerName": "Ngày tạo", "flex": 1, "minWidth": 100},
                        {"field": "so_ngay_cho", "headerName": "Số ngày chờ", "flex": .8,
                         "minWidth": 90, "type": "numericColumn",
                         "cellStyle": {"styleConditions": [
                             {"condition": "params.value >= 7", "style": DO}]}}],
            dashGridOptions={"suppressCellFocus": True, "domLayout": "autoHeight",
                             "pagination": True, "paginationPageSize": 10,
                             "paginationPageSizeSelector": False, "localeText": LOCALE_VI},
            style={"width": "100%"}) if len(cho) else
        html.Div("Không có hợp đồng nào đang chờ online.", className="desc"),
    ]
    return tieu_de, than


# ------------------------------------------------------------------ callback
JS_MO = """
function(mo, _dong, _nen) {
    const ctx = window.dash_clientside.callback_context;
    const trig = ((ctx.triggered[0] || {}).prop_id || '');
    return (trig.startsWith('%s') && mo && mo.acc) ? 'ngan mo' : 'ngan';
}
""" % STORE

def register(app):
    app.clientside_callback(JS_MO, Output("ns-ngan", "className"), Input(STORE, "data"),
                            Input("ns-ngan-dong", "n_clicks"), Input("ns-ngan-nen", "n_clicks"))
    # vừa chọn người mới: xoá nội dung người trước để vòng xoay hiện trên nền trống, không lẫn số hai người
    app.clientside_callback(
        """
        function(mo) {
            const khong = window.dash_clientside.no_update;
            return (mo && mo.acc) ? ['Đang tải thông tin nhân sự…', ''] : [khong, khong];
        }
        """,
        Output("ns-ngan-tieu-de", "children", allow_duplicate=True),
        Output("ns-ngan-than", "children", allow_duplicate=True),
        Input(STORE, "data"), prevent_initial_call=True)

    @app.callback(Output("ns-ngan-tieu-de", "children"), Output("ns-ngan-than", "children"),
                  Input(STORE, "data"), State("ky-chung", "data"), prevent_initial_call=True)
    def _dung(mo, ky):
        acc = str((mo or {}).get("acc") or "").strip().lower()
        if not acc:
            return no_update, no_update
        goi_y_phong = [(mo or {}).get("phong"), (kc.lam_sach(ky) or {}).get("phong")]
        try:
            return noi_dung(acc, goi_y_phong, (kc.lam_sach(ky) or {}).get("den"))
        except Exception as e:
            ghi_log("loi_xem_nhan_su", f"{acc}: {e}")
            return _chua_co("Không thể tải thông tin", f"Đã xảy ra lỗi khi tải hồ sơ nhân sự ({e}). Vui lòng thử lại sau.")

