"""Đi từ tổng xuống chi tiết và các phần dùng chung ở khung app.

- Bấm tên phòng ở Báo cáo Tổng, Diễn biến, Phân tích -> mở Báo cáo phòng của phòng đó, giữ kỳ đang xem.
- Dòng tình trạng dữ liệu trên đầu mọi trang: số đến ngày nào, file nào đang nạp thiếu.
- Giải thích từ viết tắt khi rê chuột lên tiêu đề cột / ô chỉ số.
"""
from __future__ import annotations

from dash import Input, Output, State, dcc, html, no_update
from flask_login import current_user

from app.ui import ky_chung as kc
from app.ui.icons import icon

# Mã dòng trên bảng theo phòng: "<loại dòng>|<mã phòng>" (mã phòng lặp ở dòng tổng bầy nên ghép loại dòng)
ROW_ID = "params.data.loai_dong + '|' + params.data.phong_code"
O_PHONG = {"o-lien-ket": "params.data && params.data.loai_dong == 'data'"}


def cot_phong_bam_duoc(col: dict) -> dict:
    """Cột tên phòng: dòng phòng bấm được (gạch chân khi rê chuột) - chỉ với người được xem Báo cáo phòng."""
    if not current_user.duoc_xem_nhan_su:
        return col
    return {**col, "cellClassRules": {**col.get("cellClassRules", {}), **O_PHONG},
            "tooltipValueGetter": {"function": "params.data && params.data.loai_dong == 'data' ? "
                                               "'Bấm để mở Báo cáo phòng' : null"}}


def gan_mo_phong(app, grid_id: str, cot: str = "phong") -> None:
    @app.callback(Output("url", "pathname", allow_duplicate=True),
                  Output("ky-chung", "data", allow_duplicate=True),
                  Input(grid_id, "cellClicked"), State("ky-chung", "data"), prevent_initial_call=True)
    def _mo(o, ky):
        from app.ui.pages.phong import duoc_xem_phong
        o = o or {}
        loai, _, code = str(o.get("rowId") or "").partition("|")
        if o.get("colId") != cot or loai != "data" or not current_user.duoc_xem_nhan_su \
                or not duoc_xem_phong(code):
            return no_update, no_update
        return "/phong", {**kc.lam_sach(ky), "phong": code}


# ------------------------------------------------------------------ tình trạng dữ liệu
def thanh_du_lieu() -> list:
    """Nội dung dòng tình trạng dữ liệu (ngày có số mới nhất của 3 file)."""
    from app.admin_service import do_moi_du_lieu
    moi = do_moi_du_lieu()
    co = [m for m in moi if m["ngay"]]
    if not co:
        return [dcc.Link([icon("upload", 13), html.Span("Chưa có dữ liệu - nạp file để bắt đầu")],
                         href="/upload", className="badge warn thanh-dl")] if current_user.duoc_upload else \
               [html.Span("Chưa có dữ liệu", className="badge warn thanh-dl")]
    moi_nhat = max(m["ngay"] for m in co)
    tre = [m for m in moi if m["ngay"] != moi_nhat]
    chi_tiet = " · ".join(f"{m['loai']} đến {_dd(m['ngay'])}" for m in moi)
    out = [html.Span([icon("database", 13), html.Span(f"Số đến {_dd(moi_nhat)}")],
                     className="badge muted thanh-dl", title=chi_tiet)]
    if tre:
        chu = ", ".join(f"{m['loai']} {'chưa có' if not m['ngay'] else 'mới đến ' + _dd(m['ngay'])}"
                        for m in tre)
        out.append(dcc.Link([icon("alert", 13), html.Span(f"{chu} → Kiểm tra")], href="/chatluong",
                            className="badge warn thanh-dl",
                            title="Có file chưa nạp đủ ngày - số V.VIP / Camera ngày gần nhất có thể thiếu"))
    return out


def _dd(iso: str | None) -> str:
    return f"{iso[8:10]}/{iso[5:7]}" if iso else "–"


# ------------------------------------------------------------------ từ viết tắt
GIAI_THICH = {
    "HTKH": "HTKH: tỷ lệ hoàn thành kế hoạch = thực hiện / chỉ tiêu.",
    "PTTB": "PTTB: phát triển thuê bao - hợp đồng Internet online.",
    "VVIP": "V.VIP: gói truyền hình V.VIP, gồm cả V.VIP Plus.",
    "V.VIP": "V.VIP: gói truyền hình V.VIP, gồm cả V.VIP Plus.",
    "CNQL": "CNQL: hợp đồng do chi nhánh quản lý sau bán.",
    "FPL": "FPL: FPT Play - truyền hình.",
    "FPT PLAY": "FPT Play: truyền hình.",
    "NSLĐ": "NSLĐ: năng suất lao động theo file NSLĐ hằng tháng.",
    "ITN": "ITN: điểm Internet trong file NSLĐ.",
    "Số tồn": "Số tồn: đã ký hợp đồng nhưng chưa online, còn trong file mới nhất.",
    "Đủ 3 DV": "Đủ 3 DV: hợp đồng online có cả V.VIP và Camera.",
    "PKD": "PKD: phòng kinh doanh.",
}


def giai_thich(chu: str) -> str | None:
    chu = str(chu or "")
    tim = []
    for k, v in GIAI_THICH.items():
        if k.upper() in chu.upper() and v not in tim and not (k == "VVIP" and "V.VIP" in chu):
            tim.append(v)
    return " ".join(tim) or None


def them_giai_thich(cols: list[dict]) -> list[dict]:
    """Gắn chú thích từ viết tắt vào tiêu đề cột (giữ chú thích đã có)."""
    for c in cols:
        if "children" in c:
            them_giai_thich(c["children"])
        if not c.get("headerTooltip"):
            gt = giai_thich(c.get("headerName"))
            if gt:
                c["headerTooltip"] = gt
    return cols
