"""Bảng tổng quan theo ngày - dựng lại đúng khối tổng hợp trong file Google Sheet.

Cột: PKD | Nhân sự | INTERNET (Mục tiêu, Số tồn, Số online, Tỷ lệ HTKH)
     | TĂNG TRƯỞNG (Số online cùng kỳ tháng trước, Tỷ lệ)
     | FPT PLAY (Combo, Tỷ lệ FPL/NET) | PTTB CNQL (Số online, Tỷ lệ)
     | COMBO VVIP (Số VVIP, Tỷ lệ VVIP/PTTB) | CAMERA (Mục tiêu, Thực hiện, Tỷ lệ HTKH)
     | KẾT QUẢ THỰC HIỆN NGÀY (Mục tiêu, Bán mới, Online, VVIP, Kết luận)

PTTB CNQL = hợp đồng có CN Quản lý thuộc chi nhánh (DNG_01/DNG_02/QNM),
đã đối chiếu khớp 20/20 phòng với file hiện tại.

MTTN (chốt với chủ app 01/10/2026): hiện thêm trong ngoặc cạnh "Số online" và "Tỷ lệ" của PTTB
CNQL, ví dụ "210 (65)" và "31% (62%)" - CHỈ ở đúng phòng có bật MTTN (`app.mttn`, hiện là IBB7) và
dòng tổng bầy chứa phòng đó, không hiện ở phòng/bầy khác hay dòng tổng chi nhánh/toàn phòng. Cùng
khoảng ngày với PTTB CNQL để so trực tiếp được. Công thức tỷ lệ giống hệt MTTN ở Báo cáo phòng:
mttn / tổng online của phòng (không phải so với số CNQL).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import text

from app import mttn
from app.db import engine
from app.metrics import month_range, ngay_co_du_lieu
from app.org import bay_info, phong_order

CN_NOI_BO = ("DNG_01", "DNG_02", "QNM")

TEN_PHAM_VI = {"all": "Toàn chi nhánh", "DNG": "Đà Nẵng", "QNM": "Quảng Nam"}
TEN_DONG_TONG = {"all": "TỔNG TOÀN CHI NHÁNH", "DNG": "TỔNG ĐÀ NẴNG", "QNM": "TỔNG QUẢNG NAM"}
COT_KHONG_CONG = ["nhan_su", "mt_internet", "mt_camera", "mt_ngay"]
LECH_GIO_VN = timedelta(hours=7)          # database lưu giờ UTC


def _sql_bang(sql: str, params: dict) -> pd.DataFrame:
    df = pd.read_sql_query(text(sql), engine, params=params)
    return df.set_index("phong_code") if not df.empty else pd.DataFrame()


def _dem(dk: str) -> str:
    return f"SUM(CASE WHEN {dk} THEN 1 ELSE 0 END)"


def _mt_ngay_can(mt_thang: pd.Series, luy_ke_den_hom_qua: pd.Series, d: date) -> pd.Series:
    """Bình quân online mỗi ngày còn lại (tính cả hôm nay) để về mục tiêu tháng.

    `luy_ke_den_hom_qua` là online từ đầu tháng đến TRƯỚC ngày `d` (chưa bao gồm ngày `d`).
    Số ngày còn lại = số ngày trong tháng trừ ngày `d` + 1 (tính cả ngày `d`).
    Ngày cuối tháng = 1 ngày.
    Làm tròn LÊN: thiếu 101 chia 3 ngày là 33,67 nên phải online 34 mỗi ngày mới đủ.
    Đã đủ mục tiêu tháng thì mục tiêu ngày = 0.
    """
    con_thieu = (mt_thang - luy_ke_den_hom_qua).clip(lower=0)
    so_ngay_con = month_range(f"{d:%Y-%m}")[2] - d.day + 1
    if so_ngay_con <= 0:
        return pd.Series(0, index=mt_thang.index)
    return np.ceil(con_thieu / so_ngay_con).astype(int)


def _so_lieu_phong(d_tu: date, d_den: date) -> pd.DataFrame:
    """Mọi cột đếm của Báo cáo Tổng theo phòng, trong 3 câu hỏi database (trước đây ~14 câu lẻ):
    - Internet: online trong kỳ, cùng kỳ tháng trước, PTTB CNQL, số tồn, online / bán mới trong ngày cuối;
    - FPT Play: combo, V.VIP trong kỳ, V.VIP tạo trong ngày cuối (Kết quả ngày đếm V.VIP theo NGÀY TẠO);
    - Camera trong kỳ.
    Cách đếm giữ nguyên như từng hàm cũ (đã đối chiếu khớp sheet)."""
    from app.metrics import dieu_kien_ton
    ck_tu, ck_den = lui_mot_thang(d_tu), lui_mot_thang(d_den)
    dau_thang = d_den.replace(day=1)          # để tính mục tiêu ngày: luỹ kế tháng, không theo kỳ đang xem
    dk_ton, p = dieu_kien_ton()
    mttn_cfg = mttn.cau_hinh()
    mttn_phong, mttn_cn = mttn_cfg["phong"], mttn_cfg["cn_quan_ly"]
    p.update({"tu": d_tu.isoformat(), "den": d_den.isoformat(), "ck_tu": ck_tu.isoformat(),
              "ck_den": ck_den.isoformat(), "d": d_den.isoformat(), "thang_tu": dau_thang.isoformat(),
              "lo": min(d_tu, ck_tu, dau_thang).isoformat(),
              "hi": max(d_den, ck_den).isoformat(), **{f"cnql_{i}": c for i, c in enumerate(CN_NOI_BO)},
              **{f"mttnph_{i}": c for i, c in enumerate(mttn_phong)},
              **{f"mttncn_{i}": c for i, c in enumerate(mttn_cn)}})
    trong_ky = "ngay_online >= :tu AND ngay_online <= :den"
    cnql = ", ".join(f":cnql_{i}" for i in range(len(CN_NOI_BO)))
    # PTTB CNQL = CN Quản lý thuộc chi nhánh nội bộ; MTTN = CN Quản lý thuộc tỉnh Miền Trung - Tây
    # Nguyên, VÀ chỉ tính cho phòng có bật MTTN (config/rules.yml -> mttn.phong, hiện chỉ IBB7) -
    # chốt với chủ app 01/10/2026: hiện cạnh PTTB CNQL để so trực tiếp, không tính cho phòng khác.
    dk_mttn = ("0=1" if not (mttn_phong and mttn_cn) else
              f"{trong_ky} AND phong_code IN ({', '.join(f':mttnph_{i}' for i in range(len(mttn_phong)))}) "
              f"AND cn_quan_ly IN ({', '.join(f':mttncn_{i}' for i in range(len(mttn_cn)))})")
    net = _sql_bang(f"""
        SELECT phong_code, {_dem(trong_ky)} AS online,
               {_dem("ngay_online >= :ck_tu AND ngay_online <= :ck_den")} AS ck_online,
               {_dem("ngay_online >= :thang_tu AND ngay_online <= :den")} AS luy_ke_thang,
               {_dem(f"{trong_ky} AND cn_quan_ly IN ({cnql})")} AS cnql,
               {_dem(dk_mttn)} AS mttn,
               {_dem(dk_ton)} AS so_ton,
               {_dem("ngay_online = :d")} AS ngay_online,
               {_dem("ngay_tao_hd = :d")} AS ngay_ban_moi
        FROM fact_internet
        WHERE (ngay_online >= :lo AND ngay_online <= :hi) OR ngay_tao_hd = :d OR ({dk_ton})
        GROUP BY phong_code""", p)
    ky = {"tu": p["tu"], "den": p["den"], "d": p["d"]}
    fpl = _sql_bang(f"""
        SELECT phong_code, {_dem(trong_ky)} AS fpl_combo, {_dem(f"{trong_ky} AND la_vvip = TRUE")} AS vvip,
               {_dem("ngay_tao_hd = :d AND la_vvip = TRUE")} AS ngay_vvip
        FROM fact_fptplay WHERE ({trong_ky}) OR ngay_tao_hd = :d
        GROUP BY phong_code""", ky)
    cam = _sql_bang(f"""SELECT phong_code, COUNT(*) AS camera FROM fact_camera WHERE {trong_ky}
                        GROUP BY phong_code""", ky)
    return pd.concat([x for x in (net, fpl, cam) if not x.empty], axis=1) if any(
        not x.empty for x in (net, fpl, cam)) else pd.DataFrame()


def _nhan_su() -> pd.Series:
    """Số nhân sự đang làm của phòng: không ghi Nghỉ hoặc Trưởng, dòng danh mục còn hiệu lực, không đếm trưởng phòng.

    Nhận diện trưởng phòng qua hai lớp:
    1. SQL: ghi_chu chứa 'truong' (không phân biệt hoa thường, không dấu) — dùng cho TP không có role='phong'.
    2. Python: acc_truong_phong() — dùng cho TP có tài khoản riêng role='phong'.
    """
    from app.canh_bao import acc_truong_phong
    df = pd.read_sql_query(text("""SELECT acc_norm, phong_code FROM staff_map
                             WHERE COALESCE(ghi_chu, '') NOT LIKE '%Ngh%'
                               AND COALESCE(ghi_chu, '') NOT LIKE '%Truong%'
                               AND (hieu_luc_den IS NULL OR hieu_luc_den >= CURRENT_DATE)"""), engine)
    df = df[~df.acc_norm.isin(acc_truong_phong())]
    return df.groupby("phong_code").size().astype(int)


def _targets(thang: str) -> pd.DataFrame:
    """Bảng mục tiêu phòng × chỉ tiêu của một tháng."""
    return _targets_thang([thang]).get(thang, pd.DataFrame())


def _targets_thang(cac_thang: list[str]) -> dict[str, pd.DataFrame]:
    """{tháng: bảng mục tiêu phòng × chỉ tiêu} của các tháng, đọc trong một câu hỏi."""
    ten = ", ".join(f":t{i}" for i in range(len(cac_thang)))
    df = pd.read_sql_query(text(f"""SELECT thang, ma_doi_tuong, chi_tieu, gia_tri FROM target_monthly
                                   WHERE thang IN ({ten}) AND doi_tuong = 'PHONG'"""),
                           engine, params={f"t{i}": t for i, t in enumerate(cac_thang)})
    return {t: g.pivot_table(index="ma_doi_tuong", columns="chi_tieu", values="gia_tri")
            for t, g in df.groupby("thang")}


def lui_mot_thang(d: date) -> date:
    """Cùng ngày tháng trước (31/10 -> 30/09)."""
    dau = d.replace(day=1) - timedelta(days=1)
    return dau.replace(day=min(d.day, dau.day))


def ten_khoang(tu: date, den: date) -> str:
    """Nhãn kỳ ngắn: "tháng 9" khi luỹ kế từ ngày 01, còn lại "08/09-14/09"."""
    if tu == den.replace(day=1):
        return f"THÁNG {den.month}"
    if tu.year != den.year:
        return f"{tu:%d/%m/%Y}-{den:%d/%m/%Y}"
    return f"{tu:%d/%m}-{den:%d/%m}"


def bang_tong_quan(thang: str, ngay: int | None = None,
                   chi_phong: list[str] | None = None, chi_nhanh: str = "all",
                   tam_tinh: bool = False, tu: str | None = None) -> tuple[pd.DataFrame, int]:
    """Trả về (bảng đã có dòng tổng bầy + dòng tổng, ngày dữ liệu được dùng).

    Kỳ xem: từ `tu` (mặc định ngày 01 của tháng) đến ngày `ngay` của `thang`. Khoảng có thể
    vắt qua nhiều tháng. Cùng kỳ = cùng khoảng ngày lùi một tháng. Khối "Kết quả ngày" là ngày cuối.
    Mục tiêu: tháng của ngày cuối; khoảng vắt nhiều tháng thì cộng mục tiêu các tháng đó.
    `chi_nhanh` chỉ đổi tên dòng tổng (TỔNG ĐÀ NẴNG...). `tam_tinh` = ngày còn đang nạp số:
    phòng chưa đủ mục tiêu ghi "Chưa đạt" thay vì "Không đạt".
    """
    ngay = ngay or ngay_co_du_lieu(thang) or month_range(thang)[2]
    d_den = date.fromisoformat(f"{thang}-{ngay:02d}")
    d_tu = date.fromisoformat(tu) if tu else d_den.replace(day=1)
    d_tu = min(d_tu, d_den)
    codes = [p["code"] for p in phong_order(thang)]
    if chi_phong is not None:
        codes = [c for c in codes if c in set(chi_phong)]

    def s(series: pd.Series) -> pd.Series:
        return series.reindex(codes).fillna(0).astype(int)

    so = _so_lieu_phong(d_tu, d_den)

    def cot(ten: str) -> pd.Series:
        return s(so[ten]) if ten in so.columns else pd.Series(0, index=codes)

    nhan_su = s(_nhan_su())

    so_thang = (d_den.year - d_tu.year) * 12 + d_den.month - d_tu.month
    cac_thang = [f"{(d_tu.year * 12 + d_tu.month - 1 + i) // 12}-{(d_tu.month - 1 + i) % 12 + 1:02d}"
                 for i in range(so_thang + 1)]
    moi_thang = _targets_thang(sorted(set(cac_thang) | {thang}))
    ds_tgt = [moi_thang[m] for m in cac_thang if m in moi_thang]
    tgt = pd.concat(ds_tgt).groupby(level=0).sum() if len(ds_tgt) > 1 else (ds_tgt[0] if ds_tgt else pd.DataFrame())
    tgt_thang = moi_thang.get(thang, pd.DataFrame())     # mục tiêu ngày luôn lấy của tháng ngày cuối

    def target(col: str, bang: pd.DataFrame | None = None) -> pd.Series:
        bang = tgt if bang is None else bang
        if bang.empty or col not in bang.columns:
            return pd.Series(0, index=codes)
        return bang[col].reindex(codes).fillna(0)

    meta = {p["code"]: p for p in phong_order(thang)}
    df = pd.DataFrame({
        "phong": [meta[c]["ten"] for c in codes],
        "bay": [meta[c]["bay"] for c in codes],
        "nhan_su": nhan_su,
        "mt_internet": target("internet"),
        "so_ton": cot("so_ton"),
        "online": cot("online"),
        "ck_online": cot("ck_online"),
        "fpl_combo": cot("fpl_combo"),
        "cnql": cot("cnql"),
        "mttn": cot("mttn"),
        "vvip": cot("vvip"),
        "mt_camera": target("camera"),
        "camera": cot("camera"),
        "mt_ngay": _mt_ngay_can(target("internet", tgt_thang),
                                cot("luy_ke_thang") - cot("ngay_online"), d_den),
        "ngay_ban_moi": cot("ngay_ban_moi"),
        "ngay_online": cot("ngay_online"),
        "ngay_vvip": cot("ngay_vvip"),
    }, index=codes)

    # MTTN chỉ hiện (số) cạnh PTTB CNQL ở đúng phòng có bật MTTN và dòng tổng bầy chứa phòng đó -
    # chốt với chủ app 01/10/2026, không hiện ở bầy khác (dù cộng ra 0) hay dòng tổng chi nhánh/toàn phòng.
    mttn_phong_bat = set(mttn.cau_hinh()["phong"])
    mttn_bay_bat = {meta[c]["bay"] for c in mttn_phong_bat if c in meta}

    rows = []
    bays = bay_info()
    for bcode, binfo in sorted(bays.items(), key=lambda kv: kv[1]["thu_tu"]):
        sub = df[df.bay == bcode]
        if sub.empty:
            continue
        for code, r in sub.iterrows():
            rows.append({"phong_code": code, "loai_dong": "data", "mttn_hien": code in mttn_phong_bat,
                        **r.drop("bay").to_dict()})
        tong = sub.drop(columns=["phong", "bay"]).sum()
        rows.append({"phong_code": f"SUB_{bcode}", "loai_dong": "subtotal", "mttn_hien": bcode in mttn_bay_bat,
                     "phong": binfo.get("ten_tong", f"TỔNG {binfo['ten']}"), **tong.to_dict()})
    # Xem toàn chi nhánh: thêm dòng tổng riêng Đà Nẵng / Quảng Nam ngay trên dòng tổng
    # (bầy trộn phòng của cả hai tỉnh nên không đọc được từ các dòng tổng bầy)
    # Như Google Sheet: phòng trong `tong_chi_nhanh.khong_cong` (ANCS) không cộng NHÂN SỰ và MỤC TIÊU
    # vào dòng tổng; số thực hiện (online, tồn, V.VIP...) vẫn tính đủ toàn chi nhánh.
    df_tong = df.copy()
    df_tong.loc[df_tong.index.isin(phong_khong_cong_tong()), COT_KHONG_CONG] = 0
    if chi_nhanh == "all":
        cn_cua = pd.Series({c: meta[c].get("chi_nhanh") for c in codes})
        if cn_cua.nunique() > 1:
            for cn in ("DNG", "QNM"):
                sub = df_tong[cn_cua.reindex(df_tong.index) == cn]
                if len(sub):
                    rows.append({"phong_code": f"CN_{cn}", "loai_dong": "chinhanh", "mttn_hien": False,
                                 "phong": f"TỔNG {cn}",
                                 **sub.drop(columns=["phong", "bay"]).sum().to_dict()})
    tong_all = df_tong.drop(columns=["phong", "bay"]).sum()
    rows.append({"phong_code": "TOTAL", "loai_dong": "total", "mttn_hien": False,
                 "phong": TEN_DONG_TONG.get(chi_nhanh, TEN_DONG_TONG["all"]),
                 **tong_all.to_dict()})

    out = pd.DataFrame(rows)
    out = _them_ty_le(out, tam_tinh)
    return out, ngay


def phong_khong_cong_tong() -> set[str]:
    """Phòng hiện dòng riêng nhưng không cộng vào dòng tổng chi nhánh (config/rules.yml)."""
    from app.config import rules_config
    return set((rules_config().get("tong_chi_nhanh") or {}).get("khong_cong") or [])


def _ty_le(tu: pd.Series, mau: pd.Series) -> pd.Series:
    return (tu / mau.replace(0, np.nan) * 100).round(0)


def _them_ty_le(out: pd.DataFrame, tam_tinh: bool = False) -> pd.DataFrame:
    out["htkh_internet"] = _ty_le(out.online, out.mt_internet)
    out["tang_truong"] = ((out.online - out.ck_online) /
                          out.ck_online.replace(0, np.nan) * 100).round(0)
    out["fpl_ty_le"] = _ty_le(out.fpl_combo, out.online)
    out["cnql_ty_le"] = _ty_le(out.cnql, out.online)
    out["mttn_ty_le"] = _ty_le(out.mttn, out.online)
    out["vvip_ty_le"] = _ty_le(out.vvip, out.online)
    out["htkh_camera"] = _ty_le(out.camera, out.mt_camera)
    # Đạt khi online trong ngày >= mục tiêu ngày (BGĐ chốt 14/09/2026). Phòng đã đủ mục tiêu tháng
    # thì mục tiêu ngày = 0 nên luôn Đạt. Chỉ ghi "—" khi CHƯA NHẬP MỤC TIÊU THÁNG cho phòng nào -
    # bám mt_internet chứ không bám mt_ngay: cuối tháng cả chi nhánh đủ chỉ tiêu thì mt_ngay về 0
    # hết, bám mt_ngay là cột Kết luận biến thành "—" đúng lúc đang làm tốt nhất.
    out["ket_luan"] = np.where(out.ngay_online >= out.mt_ngay, "Đạt",
                               "Chưa đạt" if tam_tinh else "Không đạt")
    if not (out[out.loai_dong == "data"].mt_internet > 0).any():
        out["ket_luan"] = "—"
    return out.replace({np.nan: None})


def lan_nap_so_cuoi() -> datetime | None:
    """Giờ Việt Nam của lần nạp file Internet gần nhất (file quyết định số online)."""
    df = pd.read_sql_query(text("SELECT MAX(uploaded_at) AS t FROM upload_batch "
                          "WHERE dataset = 'internet'"), engine)
    v = df["t"].iloc[0] if not df.empty else None
    if v is None or pd.isna(v):
        return None
    return pd.Timestamp(v).to_pydatetime().replace(tzinfo=None) + LECH_GIO_VN


def trang_thai_ngay(ngay_iso: str) -> tuple[bool, datetime | None]:
    """(ngày này còn đang cập nhật?, giờ nạp số gần nhất).

    File được xuất nhiều lần trong ngày. Ngày mới nhất coi là "đang cập nhật" khi lần nạp
    cuối vẫn diễn ra trong chính ngày đó - tức chưa có lượt nạp nào sau khi ngày kết thúc.
    """
    from app.metrics import ngay_moi_nhat
    luc = lan_nap_so_cuoi()
    dang = bool(luc) and ngay_iso == ngay_moi_nhat() and luc.date().isoformat() <= ngay_iso
    return dang, luc
