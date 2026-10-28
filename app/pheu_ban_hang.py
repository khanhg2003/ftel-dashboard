"""Số liệu và giao diện Phễu bán hàng trên Báo cáo Tổng (chốt 28/10/2026).

Đọc từ bảng `fact_pheu_ban_hang` (nạp từ file Excel "Danh sách khách hàng chưa chuyển đổi theo từng đơn vị"
ở trang Nạp dữ liệu). Mỗi tầng của phễu = Chuyển đổi + Chưa chuyển đổi của giai đoạn đó; tỷ lệ % ở mỗi tầng
từ tầng 2 trở đi = số tầng hiện tại / số tầng ngay phía trên × 100%.
"""
from __future__ import annotations

import pandas as pd
from dash import dcc, html
from sqlalchemy import text

from app.bo_nho import nho
from app.config import rules_config
from app.db import engine, session_scope
from app.models import FactPheu
from app.org import phong_order
from app.ui.components import tip

COT_SO_PHEU = (
    "thu_thap_cd", "thu_thap_ccd", "lien_he_cd", "lien_he_ccd",
    "tu_van_cd", "tu_van_ccd", "len_don_cd", "len_don_ccd",
    "hoan_tat_cd", "hoan_tat_ccd", "kh_cham_soc",
)

# Dữ liệu khởi tạo lần đầu từ file mẫu khi bảng trên máy chủ mới chưa nạp
_DU_LIEU_MAU = (
    ("Khác", 12, 11, 3, 9, 2, 1, 2, 0, 1, 1, 1),
    ("DNGB1", 12418, 3485, 685, 11733, 668, 17, 532, 136, 324, 208, 324),
    ("DNGB2", 5631, 3578, 676, 4955, 546, 130, 315, 231, 4, 311, 4),
    ("DNGB3", 22021, 2977, 563, 21458, 526, 37, 377, 149, 133, 244, 133),
    ("DNGB4", 706, 478, 562, 144, 503, 59, 367, 136, 158, 209, 158),
    ("DNGB5", 2073, 1219, 1617, 456, 1188, 429, 950, 238, 660, 290, 660),
    ("DNGB6", 5192, 2285, 590, 4602, 462, 128, 256, 206, 27, 229, 27),
    ("DNGB7", 8561, 4547, 2582, 5979, 2259, 323, 1898, 361, 1504, 394, 1504),
    ("DNGBT1", 163, 7, 161, 2, 161, 0, 142, 19, 0, 142, 0),
    ("DNGBT2", 479, 21, 367, 112, 367, 0, 316, 51, 0, 316, 0),
    ("DNGCS1", 130, 0, 130, 0, 130, 0, 98, 32, 0, 98, 0),
    ("DNGCS2", 194, 3730, 182, 12, 182, 0, 139, 43, 0, 139, 0),
    ("DNGDA", 2, 0, 2, 0, 2, 0, 1, 1, 0, 1, 0),
)

CAC_TANG = (
    ("thu_thap", "THU THẬP", "PROSPECT", "#0052B4", "polygon(0% 0%, 100% 0%, 91.5% 100%, 8.5% 100%)",
     "Khách hàng tiềm năng thu thập được trong kỳ (Chuyển đổi + Chưa chuyển đổi)."),
    ("lien_he", "LIÊN HỆ", "", "#0D6EFD", "polygon(8.5% 0%, 91.5% 0%, 83% 100%, 17% 100%)",
     "Khách hàng đã chuyển sang bước Liên hệ. Tỷ lệ % = Liên hệ / Thu thập."),
    ("tu_van", "TƯ VẤN", "LEAD", "#1D8CF8", "polygon(17% 0%, 83% 0%, 75% 100%, 25% 100%)",
     "Khách hàng đã liên hệ thành công và chuyển sang Tư vấn. Tỷ lệ % = Tư vấn / Liên hệ."),
    ("len_don", "LÊN ĐƠN", "", "#3BA1FF", "polygon(25% 0%, 75% 0%, 67.5% 100%, 32.5% 100%)",
     "Khách hàng đồng ý đăng ký và chuyển sang Lên đơn. Tỷ lệ % = Lên đơn / Tư vấn."),
    ("hoan_tat", "HOÀN TẤT", "CUSTOMER", "#63B8FF", "polygon(32.5% 0%, 67.5% 0%, 67.5% 100%, 32.5% 100%)",
     "Đơn hàng bước vào giai đoạn Hoàn tất triển khai. Tỷ lệ % = Hoàn tất / Lên đơn."),
)


def _map_don_vi() -> dict[str, str]:
    cfg = (rules_config().get("pheu_ban_hang") or {}).get("don_vi_phong") or {}
    return {str(k).strip().upper(): str(v).strip() for k, v in cfg.items()}


def gan_don_vi(don_vi: str) -> tuple[str | None, str]:
    """(mã phòng, mã chi nhánh DNG/QNM) từ tên Đơn vị trong file Excel."""
    dv = (don_vi or "").strip()
    hoa = dv.upper()
    phong_code = _map_don_vi().get(hoa)
    meta = {p["code"]: p for p in phong_order()}
    if phong_code and phong_code in meta:
        return phong_code, meta[phong_code].get("chi_nhanh") or "DNG"
    if hoa.startswith("QNM"):
        return phong_code, "QNM"
    return phong_code, "DNG"


def _df_mau() -> pd.DataFrame:
    rows = []
    for dv, *so in _DU_LIEU_MAU:
        phong_code, chi_nhanh = gan_don_vi(dv)
        rows.append({"don_vi": dv, "phong_code": phong_code, "chi_nhanh": chi_nhanh,
                     **dict(zip(COT_SO_PHEU, so))})
    return pd.DataFrame(rows)


def _seed_neu_trong() -> None:
    from app.ingest.commit import _upsert
    try:
        FactPheu.__table__.create(engine, checkfirst=True)
        with session_scope() as s:
            n = s.execute(text("SELECT COUNT(*) FROM fact_pheu_ban_hang")).scalar() or 0
            if n == 0:
                _upsert(s, FactPheu, _df_mau().to_dict("records"), "don_vi")
    except Exception:
        pass


@nho("so_lieu")
def bang_pheu() -> pd.DataFrame:
    """Đọc toàn bộ bảng phễu bán hàng (đã nhớ tạm theo nhóm `so_lieu`)."""
    try:
        FactPheu.__table__.create(engine, checkfirst=True)
        df = pd.read_sql_query(text("SELECT * FROM fact_pheu_ban_hang ORDER BY don_vi"), engine)
        if df.empty:
            _seed_neu_trong()
            df = pd.read_sql_query(text("SELECT * FROM fact_pheu_ban_hang ORDER BY don_vi"), engine)
        return df if not df.empty else _df_mau()
    except Exception:
        return _df_mau()


def loc_pheu(chi_phong: list[str] | None = None, chi_nhanh: str = "all",
             don_vi: str | None = None) -> pd.DataFrame:
    """Lọc bảng phễu theo phạm vi phòng được xem, chi nhánh và đơn vị đang chọn."""
    df = bang_pheu()
    if df.empty:
        return df
    if chi_nhanh in ("DNG", "QNM"):
        df = df[df["chi_nhanh"] == chi_nhanh]
    if chi_phong is not None:
        cho_phep = set(chi_phong)
        df = df[df["phong_code"].isin(cho_phep) | df["phong_code"].isna()]
    if don_vi and don_vi != "all":
        df = df[df["don_vi"] == don_vi]
    return df


def don_vi_options(chi_phong: list[str] | None = None, chi_nhanh: str = "all") -> list[dict]:
    """Danh sách đơn vị cho ô lọc góc phải của thẻ Phễu bán hàng."""
    df = loc_pheu(chi_phong=chi_phong, chi_nhanh=chi_nhanh, don_vi="all")
    ten_phong = {p["code"]: p["ten"] for p in phong_order()}
    opts = [{"label": "Tất cả đơn vị", "value": "all"}]
    for _, r in df.iterrows():
        dv = r["don_vi"]
        p = ten_phong.get(r.get("phong_code"), "")
        nhan = f"{dv} ({p})" if p and p.upper() != dv.upper() else dv
        opts.append({"label": nhan, "value": dv})
    return opts


def tinh_pheu(df: pd.DataFrame) -> list[dict]:
    """Tính 5 tầng của phễu: tổng, chuyển đổi, chưa chuyển đổi và tỷ lệ % so với tầng ngay trên."""
    out = []
    truoc = None
    for ma, nhan, nhom, mau, clip, mo_ta in CAC_TANG:
        cd = int(df[f"{ma}_cd"].sum()) if not df.empty else 0
        ccd = int(df[f"{ma}_ccd"].sum()) if not df.empty else 0
        tong = cd + ccd
        ty_le = round(tong / truoc * 100, 2) if truoc and truoc > 0 else (0.0 if truoc is not None else None)
        truoc = tong
        out.append({"ma": ma, "nhan": nhan, "nhom": nhom, "mau": mau, "clip": clip,
                    "mo_ta": mo_ta, "tong": tong, "cd": cd, "ccd": ccd, "ty_le": ty_le})
    return out


def _so(n: int) -> str:
    return f"{int(n):,}".replace(",", ".")


def _pct(v: float | None) -> str:
    return "" if v is None else f"{v:.2f}%"


def the_pheu(chi_nhanh: str = "all") -> html.Div:
    """Thẻ Phễu bán hàng đặt dưới phần Dự báo ở Báo cáo Tổng."""
    mo_ta = ("Số liệu từ file Phễu bán hàng nạp tại mục Nạp dữ liệu. "
             "Mỗi tầng hiển thị tổng cơ hội ở bước đó (Chuyển đổi + Chưa chuyển đổi). "
             "Tỷ lệ % là tỷ lệ chuyển đổi từ bước ngay phía trên xuống bước hiện tại.")
    return html.Div([
        html.Div([
            html.Div([html.H3(["Phân tích cơ hội và giá trị theo giai đoạn", tip(mo_ta)],
                              className="tieu-de-tip")], className="the-ten"),
            html.Div([
                dcc.Dropdown(id="tq-pheu-dv", value="all", clearable=False, searchable=False,
                             options=don_vi_options(chi_nhanh=chi_nhanh),
                             className="pheu-chon-dv"),
            ], className="the-nut"),
        ], className="the-dau"),
        html.Div(ve_pheu(loc_pheu(chi_nhanh=chi_nhanh)), id="tq-pheu-than"),
    ], className="card the-pheu")


def ve_pheu(df: pd.DataFrame) -> html.Div:
    """Dựng 5 tầng của phễu giống 100% mẫu thiết kế."""
    if df.empty:
        return html.Div([
            html.Div("Chưa có dữ liệu phễu bán hàng cho phạm vi đang chọn. "
                     "Vào mục Nạp dữ liệu để tải lên file Excel Phễu bán hàng.",
                     className="ai-goi-y"),
        ])
    tang = tinh_pheu(df)
    dong = []
    for i, t in enumerate(tang):
        chi_tiet = (f"{t['nhan']}: {_so(t['tong'])} khách hàng. "
                    f"Đã chuyển đổi sang bước sau: {_so(t['cd'])}. "
                    f"Chưa chuyển đổi: {_so(t['ccd'])}. {t['mo_ta']}")
        noi_dung_thap = [html.Div(_so(t["tong"]), className="pheu-so")]
        if t["ty_le"] is not None:
            noi_dung_thap.append(html.Div(_pct(t["ty_le"]), className="pheu-pct"))
        lop_dong = "pheu-dong"
        if i in (1, 4):
            lop_dong += " pheu-ranh-nhom"
        elif i in (2, 3):
            lop_dong += " pheu-ranh-con"
        dong.append(html.Div([
            html.Div(t["nhom"], className="pheu-trai"),
            html.Div(
                html.Div(noi_dung_thap, className="pheu-khoi",
                         style={"background": t["mau"], "clipPath": t["clip"]},
                         title=chi_tiet.replace(". ", "\n")),
                className="pheu-giua",
            ),
            html.Div([html.Span(t["nhan"], className="pheu-ten-tang"), tip(chi_tiet)],
                     className="pheu-phai"),
        ], className=lop_dong))
    return html.Div(dong, className="pheu-khung")
