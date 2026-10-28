"""Số liệu và giao diện Phễu bán hàng trên Báo cáo Tổng (chốt 28/10/2026).

Đọc từ bảng `fact_pheu_ban_hang` theo đúng tháng đang xem trên Báo cáo Tổng (nạp từ file Excel
"Danh sách khách hàng chưa chuyển đổi theo từng đơn vị" ở trang Nạp dữ liệu). Mỗi tầng của phễu =
Chuyển đổi + Chưa chuyển đổi của giai đoạn đó; tỷ lệ % ở mỗi tầng từ tầng 2 trở đi = số tầng hiện tại
chia số tầng ngay phía trên × 100%.
"""
from __future__ import annotations

import pandas as pd
from dash import dcc, html
from sqlalchemy import inspect, text

from app.bo_nho import nho
from app.config import rules_config
from app.db import engine, session_scope
from app.models import FactPheu
from app.org import phong_order
from app.ui.components import seg_control, tip

THANG_MAU = "2026-10"

COT_SO_PHEU = (
    "thu_thap_cd", "thu_thap_ccd", "lien_he_cd", "lien_he_ccd",
    "tu_van_cd", "tu_van_ccd", "len_don_cd", "len_don_ccd",
    "hoan_tat_cd", "hoan_tat_ccd", "kh_cham_soc",
)

# Dữ liệu khởi tạo của kỳ 10/2026 từ file mẫu
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
    ("DNGBT2", 479, 21, 367, 112, 367, 0, 316, 51, 0, 142 * 0 + 316, 0),
    ("DNGCS1", 130, 0, 130, 0, 130, 0, 98, 32, 0, 98, 0),
    ("DNGCS2", 194, 3730, 182, 12, 182, 0, 139, 43, 0, 139, 0),
    ("DNGDA", 2, 0, 2, 0, 2, 0, 1, 1, 0, 1, 0),
)

CAC_TANG = (
    ("thu_thap", "THU THẬP", "PROSPECT", "#0052B4", "polygon(0% 0%, 100% 0%, 91.5% 100%, 8.5% 100%)",
     "Tổng lượng khách hàng tiềm năng thô vừa ghi nhận vào hệ thống. Khách đến từ nhắn tin hoặc bạn tự tạo"),
    ("lien_he", "LIÊN HỆ", "", "#0D6EFD", "polygon(8.5% 0%, 91.5% 0%, 83% 100%, 17% 100%)",
     "Số lượng khách hàng có SĐT xác thực đang chờ được liên hệ"),
    ("tu_van", "TƯ VẤN", "LEAD", "#1D8CF8", "polygon(17% 0%, 83% 0%, 75% 100%, 25% 100%)",
     "Số lượng khách hàng thực sự phát sinh tương tác, tìm hiểu chi tiết về sản phẩm/dịch vụ và đã được sale tư vấn"),
    ("len_don", "LÊN ĐƠN", "", "#3BA1FF", "polygon(25% 0%, 75% 0%, 67.5% 100%, 32.5% 100%)",
     "Số lượng khách hàng đã được xác nhận nhu cầu mua hàng và tiến tới giai đoạn tạo đơn hàng"),
    ("hoan_tat", "HOÀN TẤT", "CUSTOMER", "#63B8FF", "polygon(32.5% 0%, 67.5% 0%, 67.5% 100%, 32.5% 100%)",
     "Số lượng khách hàng đã hoàn tất đơn hàng và kích hoạt sử dụng dịch vụ thành công"),
)

MAU_PHEU_CON = (
    ("#1E00B8", "#351AE6", "#503AF7", "#6B5BFF", "#8477FF"),
    ("#1E7E00", "#2F9E0F", "#44B820", "#64CF42", "#8BE06E"),
    ("#9C3D00", "#C95B0C", "#F27A1A", "#F79640", "#FCBA77"),
    ("#0052B4", "#0D6EFD", "#1D8CF8", "#3BA1FF", "#63B8FF"),
    ("#065F73", "#087F99", "#0CA0BF", "#32B9D6", "#67D0E8"),
    ("#9E1C40", "#BF2652", "#DE3B6A", "#EB638B", "#F58FAD"),
    ("#1E3A5F", "#2B5282", "#3B6EA5", "#568BC2", "#7BA9D9"),
)

TEN_TANG_NGAN = {"thu_thap": "Thu thập", "lien_he": "Liên hệ", "tu_van": "Tư vấn",
                 "len_don": "Lên đơn", "hoan_tat": "Hoàn tất"}

MO_TA_PHEU = [
    html.Div("Phễu phản ánh hành trình chuyển đổi từ lúc thu thập dữ liệu thô đến khi chốt đơn thành công.",
             style={"marginBottom": "6px"}),
    html.Div("◦ Số tuyệt đối: số lượng khách hàng tại mỗi bước.", style={"paddingLeft": "8px", "marginBottom": "3px"}),
    html.Div("◦ Tỷ lệ %: Hiệu suất chuyển đổi so với bước ngay trước đó", style={"paddingLeft": "8px", "marginBottom": "8px"}),
    html.Div("Nếu tỉ lệ chuyển đổi tại bước nào đang thấp đột biến, hãy chú ý vì đó có thể là điểm nghẽn khiến "
             "bạn mất doanh thu tiềm năng. Bạn có thể so sánh con số này với các nguồn khách hàng khác hoặc với "
             "cùng kỳ tháng trước để tìm ra nguyên nhân gốc rễ (do chất lượng data hay do kỹ năng tư vấn). Tập "
             "trung tối ưu khâu vận hành tại đó để tránh lãng phí nguồn lực."),
]


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


def _df_mau(thang: str = THANG_MAU) -> pd.DataFrame:
    rows = []
    for dv, *so in _DU_LIEU_MAU:
        phong_code, chi_nhanh = gan_don_vi(dv)
        rows.append({"khoa": f"{thang}|{dv}", "thang": thang, "don_vi": dv,
                     "phong_code": phong_code, "chi_nhanh": chi_nhanh,
                     **dict(zip(COT_SO_PHEU, so))})
    return pd.DataFrame(rows)


def dam_bao_bang_pheu() -> None:
    """Tạo bảng (hoặc nâng cấp bảng cũ chưa có cột `thang`) và khởi tạo dữ liệu mẫu T10/2026."""
    from app.ingest.commit import _upsert
    try:
        insp = inspect(engine)
        if "fact_pheu_ban_hang" in insp.get_table_names():
            cot = {c["name"] for c in insp.get_columns("fact_pheu_ban_hang")}
            if "thang" not in cot or "khoa" not in cot:
                with engine.begin() as c:
                    c.execute(text("DROP TABLE fact_pheu_ban_hang"))
        FactPheu.__table__.create(engine, checkfirst=True)
        with session_scope() as s:
            n = s.execute(text("SELECT COUNT(*) FROM fact_pheu_ban_hang WHERE thang = :t"),
                          {"t": THANG_MAU}).scalar() or 0
            if n == 0:
                _upsert(s, FactPheu, _df_mau(THANG_MAU).to_dict("records"), "khoa")
    except Exception:
        pass


@nho("so_lieu")
def bang_pheu() -> pd.DataFrame:
    """Đọc toàn bộ bảng phễu bán hàng (đã nhớ tạm theo nhóm `so_lieu`)."""
    try:
        dam_bao_bang_pheu()
        df = pd.read_sql_query(text("SELECT * FROM fact_pheu_ban_hang ORDER BY thang DESC, don_vi"), engine)
        return df if not df.empty else _df_mau(THANG_MAU)
    except Exception:
        return _df_mau(THANG_MAU)


def loc_pheu(chi_phong: list[str] | None = None, chi_nhanh: str = "all",
             don_vi: str | None = None, thang: str | None = None) -> pd.DataFrame:
    """Lọc bảng phễu theo tháng của bảng tổng, phạm vi phòng, chi nhánh và đơn vị."""
    df = bang_pheu()
    if df.empty:
        return df
    if thang and "thang" in df.columns:
        df = df[df["thang"] == thang]
    if chi_nhanh in ("DNG", "QNM"):
        df = df[df["chi_nhanh"] == chi_nhanh]
    if chi_phong is not None:
        cho_phep = set(chi_phong)
        df = df[df["phong_code"].isin(cho_phep) | df["phong_code"].isna()]
    if don_vi and don_vi != "all":
        df = df[df["don_vi"] == don_vi]
    return df


def loc_nhom_don_vi(df: pd.DataFrame, nhom: str = "ibb") -> pd.DataFrame:
    """Lọc các dòng đơn vị theo nhóm so sánh: IBB1->IBB7, KT & CSKH, hoặc Tất cả."""
    if df.empty or nhom == "all":
        return df
    p = df["phong_code"].fillna("")
    dv = df["don_vi"].fillna("").str.upper()
    if nhom == "ibb":
        return df[p.str.startswith("IBB") | dv.str.match(r"^(DNG|QNM)B\d+$")]
    if nhom == "bt_cs":
        return df[p.str.startswith(("KT_", "CUS_")) | dv.str.contains("BT|CS")]
    return df


def don_vi_options(chi_phong: list[str] | None = None, chi_nhanh: str = "all",
                   thang: str | None = None) -> list[dict]:
    """Danh sách đơn vị cho ô lọc góc phải của thẻ Phễu bán hàng."""
    df = loc_pheu(chi_phong=chi_phong, chi_nhanh=chi_nhanh, don_vi="all", thang=thang)
    ten_phong = {p["code"]: p["ten"] for p in phong_order(thang)}
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


def ten_thang_pheu(thang: str | None) -> str:
    return f"Tháng {thang[5:7]}/{thang[:4]}" if thang and len(thang) >= 7 else ""


def _ten_hien_thi_dv(r: pd.Series, ten_phong: dict[str, str]) -> tuple[str, str]:
    dv = str(r.get("don_vi") or "")
    p = ten_phong.get(r.get("phong_code"), "")
    if p and p.upper() != dv.upper():
        return p, dv
    return dv, ""


def the_pheu(chi_nhanh: str = "all", thang: str | None = THANG_MAU) -> html.Div:
    """Thẻ Phễu bán hàng + khối so sánh giữa các phòng đặt dưới phần Dự báo ở Báo cáo Tổng."""
    thang = thang or THANG_MAU
    df_all = loc_pheu(chi_nhanh=chi_nhanh, thang=thang)
    return html.Div([
        html.Div([
            html.Div([
                html.H3(["Phân tích cơ hội và giá trị theo giai đoạn", tip(MO_TA_PHEU)],
                        className="tieu-de-tip"),
            ], className="the-ten"),
            html.Div([
                html.Span(ten_thang_pheu(thang), id="tq-pheu-ky", className="badge muted"),
                dcc.Dropdown(id="tq-pheu-dv", value="all", clearable=False, searchable=False,
                             options=don_vi_options(chi_nhanh=chi_nhanh, thang=thang),
                             className="pheu-chon-dv"),
            ], className="the-nut"),
        ], className="the-dau"),
        html.Div(ve_pheu(df_all, thang=thang), id="tq-pheu-than"),
        html.Div([
            html.Div([
                html.Div([
                    html.H4("So sánh phễu chuyển đổi giữa các phòng", className="pheu-ss-tieu-de"),
                    html.Span("So sánh trực diện khối lượng và hiệu suất chuyển đổi từng bước giữa IBB1 → IBB7",
                              className="desc"),
                ], className="the-ten"),
                html.Div([
                    seg_control("tq-pheu-nhom", [
                        ("ibb", "IBB1 → IBB7"),
                        ("bt_cs", "KT & CSKH"),
                        ("all", "Tất cả đơn vị"),
                    ], "ibb"),
                    seg_control("tq-pheu-kieu", [
                        ("luoi", "Lưới phễu"),
                        ("bang", "Bảng so sánh"),
                    ], "luoi"),
                ], className="the-nut"),
            ], className="the-dau pheu-ss-dau"),
            html.Div(ve_so_sanh_phong(df_all, "ibb", "luoi", thang=thang), id="tq-pheu-ss-than"),
        ], className="pheu-ss-khung"),
    ], className="card the-pheu")


def ve_pheu(df: pd.DataFrame, thang: str | None = None) -> html.Div:
    """Dựng 5 tầng của phễu lớn giống 100% mẫu thiết kế."""
    if df.empty:
        nhan_ky = ten_thang_pheu(thang) or "kỳ đang chọn"
        return html.Div([
            html.Div(f"Chưa có dữ liệu phễu bán hàng của {nhan_ky}. "
                     f"Vào mục Nạp dữ liệu để tải lên file Excel Phễu bán hàng của {nhan_ky.lower()}.",
                     className="ai-goi-y"),
        ])
    tang = tinh_pheu(df)
    dong = []
    for i, t in enumerate(tang):
        chi_tiet = (f"{t['nhan']}: {_so(t['tong'])} khách hàng\n"
                    f"• Đã chuyển đổi sang bước sau: {_so(t['cd'])}\n"
                    f"• Chưa chuyển đổi: {_so(t['ccd'])}")
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
                         title=chi_tiet),
                className="pheu-giua",
            ),
            html.Div([html.Span(t["nhan"], className="pheu-ten-tang"), tip([html.Span(t["mo_ta"])], trai=True)],
                     className="pheu-phai"),
        ], className=lop_dong))
    return html.Div(dong, className="pheu-khung")


def _the_pheu_nho(r: pd.Series, bang_mau: tuple[str, ...], ten_phong: dict[str, str]) -> html.Div:
    """Một thẻ phễu nhỏ của 1 phòng (bố cục giống 3 phễu nhỏ bên dưới trong ảnh mẫu)."""
    df_1 = pd.DataFrame([r])
    tang = tinh_pheu(df_1)
    ten_chinh, ma_phu = _ten_hien_thi_dv(r, ten_phong)
    tt_tong = tang[0]["tong"]
    ht_tong = tang[-1]["tong"]
    kh_cs = int(r.get("hoan_tat_cd") or 0)
    ty_le_chung = round(ht_tong / tt_tong * 100, 2) if tt_tong > 0 else 0.0

    dong_nho = []
    for j, t in enumerate(tang):
        noi_dung = [html.Div(_so(t["tong"]), className="pheu-nho-so")]
        if t["ty_le"] is not None:
            noi_dung.append(html.Div(_pct(t["ty_le"]), className="pheu-nho-pct"))
        chi_tiet = (f"{ten_chinh} · {t['nhan']}: {_so(t['tong'])}\n"
                    f"Chuyển đổi: {_so(t['cd'])} · Chưa chuyển đổi: {_so(t['ccd'])}")
        dong_nho.append(html.Div([
            html.Div(html.Span(TEN_TANG_NGAN[t["ma"]], className="pheu-nho-nhan-chu"),
                     className="pheu-nho-nhan"),
            html.Div(
                html.Div(noi_dung, className="pheu-khoi",
                         style={"background": bang_mau[j], "clipPath": t["clip"]},
                         title=chi_tiet),
                className="pheu-nho-thap",
            ),
        ], className="pheu-nho-dong"))

    mo_ta_phong = [
        html.Div(f"{ten_chinh}" + (f" (Mã đơn vị: {ma_phu})" if ma_phu else ""), style={"fontWeight": "700", "marginBottom": "4px"}),
        html.Div(f"◦ Tổng thu thập: {_so(tt_tong)} → Hoàn tất: {_so(ht_tong)} ({_pct(ty_le_chung)})"),
        html.Div(f"◦ Khách chăm sóc hiện có (Hoàn tất chuyển đổi): {_so(kh_cs)}"),
    ]
    return html.Div([
        html.Div([
            html.Div([
                html.Span(ten_chinh, className="pheu-nho-ten"),
                html.Span(f" · {ma_phu}", className="pheu-nho-phu") if ma_phu else None,
                tip(mo_ta_phong, trai=True),
            ], className="pheu-nho-dau-trai"),
            html.Span(f"HT/TT: {_pct(ty_le_chung)}", className="pheu-nho-huy-hieu",
                      title="Tỷ lệ Hoàn tất / Thu thập"),
        ], className="pheu-nho-dau"),
        html.Div(dong_nho, className="pheu-nho-than"),
    ], className="pheu-nho-the")


def _mau_pct_so_sanh(val: float | None, tb: float | None) -> dict:
    if val is None or tb is None:
        return {}
    chenh = val - tb
    if chenh >= 3:
        return {"backgroundColor": "#DCF5E6", "color": "#0A5B31", "fontWeight": "700"}
    if chenh <= -8:
        return {"backgroundColor": "#FBE3E1", "color": "#93241C", "fontWeight": "600"}
    if chenh <= -3:
        return {"backgroundColor": "#FDF1D8", "color": "#8A5709", "fontWeight": "600"}
    return {"fontWeight": "600", "color": "#1E293B"}


def _bang_so_sanh(df: pd.DataFrame, ten_phong: dict[str, str]) -> html.Div:
    """Bảng so sánh trực diện 5 bước + tỷ lệ % chuyển đổi giữa các phòng."""
    tang_chung = tinh_pheu(df)
    tb_lh = tang_chung[1]["ty_le"]
    tb_tv = tang_chung[2]["ty_le"]
    tb_ld = tang_chung[3]["ty_le"]
    tb_ht = tang_chung[4]["ty_le"]
    tt_all = tang_chung[0]["tong"]
    tb_chot = round(tang_chung[4]["tong"] / tt_all * 100, 2) if tt_all > 0 else 0.0

    hang = []
    for _, r in df.iterrows():
        ten_chinh, ma_phu = _ten_hien_thi_dv(r, ten_phong)
        t = tinh_pheu(pd.DataFrame([r]))
        tt, lh, tv, ld, ht = [x["tong"] for x in t]
        kh_cs = int(r.get("hoan_tat_cd") or 0)
        chot = round(ht / tt * 100, 2) if tt > 0 else 0.0
        hang.append(html.Tr([
            html.Td([html.B(ten_chinh), html.Span(f" ({ma_phu})", className="pheu-nho-phu") if ma_phu else None],
                    className="o-trai"),
            html.Td(_so(tt), className="o-so"),
            html.Td(_so(lh), className="o-so khoi-dau"),
            html.Td(_pct(t[1]["ty_le"]), className="o-pct", style=_mau_pct_so_sanh(t[1]["ty_le"], tb_lh)),
            html.Td(_so(tv), className="o-so khoi-dau"),
            html.Td(_pct(t[2]["ty_le"]), className="o-pct", style=_mau_pct_so_sanh(t[2]["ty_le"], tb_tv)),
            html.Td(_so(ld), className="o-so khoi-dau"),
            html.Td(_pct(t[3]["ty_le"]), className="o-pct", style=_mau_pct_so_sanh(t[3]["ty_le"], tb_ld)),
            html.Td(_so(ht), className="o-so khoi-dau"),
            html.Td(_pct(t[4]["ty_le"]), className="o-pct", style=_mau_pct_so_sanh(t[4]["ty_le"], tb_ht)),
            html.Td(_so(kh_cs), className="o-so khoi-dau"),
            html.Td(_pct(chot), className="o-pct", style=_mau_pct_so_sanh(chot, tb_chot)),
        ]))

    kh_cs_all = int(df["hoan_tat_cd"].sum()) if not df.empty else 0
    hang.append(html.Tr([
        html.Td("TỔNG NHÓM ĐANG XEM", className="o-trai"),
        html.Td(_so(tang_chung[0]["tong"]), className="o-so"),
        html.Td(_so(tang_chung[1]["tong"]), className="o-so khoi-dau"),
        html.Td(_pct(tb_lh), className="o-pct"),
        html.Td(_so(tang_chung[2]["tong"]), className="o-so khoi-dau"),
        html.Td(_pct(tb_tv), className="o-pct"),
        html.Td(_so(tang_chung[3]["tong"]), className="o-so khoi-dau"),
        html.Td(_pct(tb_ld), className="o-pct"),
        html.Td(_so(tang_chung[4]["tong"]), className="o-so khoi-dau"),
        html.Td(_pct(tb_ht), className="o-pct"),
        html.Td(_so(kh_cs_all), className="o-so khoi-dau"),
        html.Td(_pct(tb_chot), className="o-pct"),
    ], className="pheu-ss-tong"))

    return html.Div([
        html.Table([
            html.Thead([
                html.Tr([
                    html.Th("Phòng / Đơn vị", rowSpan=2, className="o-trai"),
                    html.Th("Thu thập", rowSpan=2),
                    html.Th("Liên hệ", colSpan=2, className="khoi-dau"),
                    html.Th("Tư vấn", colSpan=2, className="khoi-dau"),
                    html.Th("Lên đơn", colSpan=2, className="khoi-dau"),
                    html.Th("Hoàn tất", colSpan=2, className="khoi-dau"),
                    html.Th("Tổng kết", colSpan=2, className="khoi-dau"),
                ]),
                html.Tr([
                    html.Th("Số lượng", className="khoi-dau"), html.Th("% LH/TT"),
                    html.Th("Số lượng", className="khoi-dau"), html.Th("% TV/LH"),
                    html.Th("Số lượng", className="khoi-dau"), html.Th("% LĐ/TV"),
                    html.Th("Số lượng", className="khoi-dau"), html.Th("% HT/LĐ"),
                    html.Th("KH chăm sóc", className="khoi-dau"), html.Th("% HT/TT"),
                ]),
            ]),
            html.Tbody(hang),
        ], className="pheu-ss-bang"),
    ], className="pheu-ss-bang-boc")


def ve_so_sanh_phong(df: pd.DataFrame, nhom: str = "ibb", kieu: str = "luoi",
                     thang: str | None = None) -> html.Div:
    """Dựng khối so sánh các phòng bên dưới phễu tổng (chế độ Lưới phễu hoặc Bảng so sánh)."""
    sub = loc_nhom_don_vi(df, nhom or "ibb")
    if sub.empty:
        nhan_ky = ten_thang_pheu(thang) or "kỳ đang chọn"
        return html.Div(f"Chưa có dữ liệu so sánh phòng của {nhan_ky}.", className="ai-goi-y")
    ten_phong = {p["code"]: p["ten"] for p in phong_order(thang)}
    if kieu == "bang":
        return _bang_so_sanh(sub, ten_phong)
    the = [_the_pheu_nho(r, MAU_PHEU_CON[idx % len(MAU_PHEU_CON)], ten_phong)
           for idx, (_, r) in enumerate(sub.iterrows())]
    return html.Div(the, className="pheu-nho-luoi")
