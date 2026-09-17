"""Các mục kiểm tra Chất lượng dữ liệu - nơi phát hiện bất thường của file raw trước khi chốt số.

Mỗi mục: nhóm, tên, mức độ, cách xử lý và hàm trả về bảng chi tiết (mỗi dòng một điểm bất thường).
Trang /chatluong và file Excel đều đọc từ danh sách MUC này, thêm mục mới chỉ cần thêm một dòng.

Ngưỡng BGĐ chốt 17/09/2026:
- Ngày có số thấp bất thường: dưới 50% bình quân các ngày cùng thứ trong 4 tuần trước.
- File nạp nghi tải thiếu: ít dòng hơn lần nạp trước cùng loại từ 10%.
- Camera / FPT Play không có hợp đồng Internet: coi là bất thường cần soát.
- Hợp đồng ngưng / chấm dứt: vẫn tính như sheet, chỉ liệt kê để theo dõi.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from app import admin_service as sv
from app.metrics import month_range, prev_month
from app.org import phong_order

NGHIEM_TRONG, CAN_SOAT, THONG_TIN = "Nghiêm trọng", "Cần soát", "Thông tin"
THU_TU_MUC_DO = {NGHIEM_TRONG: 0, CAN_SOAT: 1, THONG_TIN: 2}
NGAY_THAP = 0.5            # dưới 50% bình quân cùng thứ
GIAM_DONG = 0.10           # file ít dòng hơn lần trước từ 10%
CN_HOP_LE = ("DNG_01", "DNG_02", "QNM")
NHOM_CN = {"DNG": ("DNG_01", "DNG_02"), "QNM": ("QNM",)}
THU = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]
TOI_DA_DONG = 3000         # mỗi mục giữ tối đa chừng này dòng chi tiết để trang nhẹ


@dataclass
class Muc:
    ma: str
    nhom: str
    ten: str
    muc_do: str
    xu_ly: str
    ham: Callable[[str, str], pd.DataFrame]
    cot: dict                               # khoá -> tên cột hiển thị
    dem: Callable[[pd.DataFrame], int] = len
    don_vi: str = "dòng"


def _q(sql: str, **p) -> pd.DataFrame:
    return sv._sql_df(sql, p)


def _ten_phong() -> dict:
    return {p["code"]: p["ten"] for p in phong_order()}


def _loc_cn(df: pd.DataFrame, cn: str, cot_cn: str = "cn_ban", cot_phong: str | None = None) -> pd.DataFrame:
    """Lọc theo chi nhánh bằng cột CN Bán (DNG_01/02, QNM) hoặc mã phòng."""
    if not cn or cn == "all" or df.empty:
        return df
    if cot_phong and cot_phong in df.columns:
        thuoc = {p["code"] for p in phong_order() if p.get("chi_nhanh") == cn}
        return df[df[cot_phong].isin(thuoc)]
    if cot_cn in df.columns:
        return df[df[cot_cn].fillna("").astype(str).str.upper().str.startswith(cn)]
    return df


# ------------------------------------------------------------------ nhóm: file nạp
def file_cham_ngay(thang: str, cn: str) -> pd.DataFrame:
    """Ngày có số mới nhất của từng file, tách riêng Đà Nẵng / Quảng Nam (mỗi chi nhánh xuất file riêng)."""
    moi = _q(" UNION ALL ".join(f"SELECT '{ten}' AS loai, cn_ban, MAX(ngay_online) AS d FROM {bang} GROUP BY cn_ban"
                                for ten, bang in sv.BANG_SO))
    rows = []
    for ten, _ in sv.BANG_SO:
        for nhom, cns in NHOM_CN.items():
            if cn not in (None, "", "all", nhom):
                continue
            v = moi[(moi.loai == ten) & moi.cn_ban.isin(cns)].d.dropna()
            rows.append({"loai": ten, "chi_nhanh": nhom, "ngay": str(v.max())[:10] if len(v) else None})
    df = pd.DataFrame(rows)
    co = df.ngay.dropna()
    if co.empty:
        return df.iloc[0:0]
    moi = max(co)
    df["moi_nhat_chung"] = moi
    df["cham_ngay"] = [(date.fromisoformat(moi) - date.fromisoformat(d)).days if d else None for d in df.ngay]
    return df[(df.cham_ngay.isna()) | (df.cham_ngay > 0)].reset_index(drop=True)


def ngay_bat_thuong(thang: str, cn: str) -> pd.DataFrame:
    """Ngày không có hợp đồng online hoặc thấp dưới 50% bình quân cùng thứ trong 4 tuần trước."""
    tu, den, _ = month_range(thang)
    df = _q("""SELECT ngay_online AS ngay, cn_ban, COUNT(*) AS n FROM fact_internet
               WHERE ngay_online >= :tu AND ngay_online <= :den GROUP BY ngay_online, cn_ban""",
            tu=(tu - timedelta(days=28)).isoformat(), den=den.isoformat())
    df = _loc_cn(df, cn)
    if df.empty:
        return pd.DataFrame(columns=["ngay", "thu", "online", "tb_cung_thu", "ty_le", "van_de"])
    s = df.assign(ngay=pd.to_datetime(df.ngay)).groupby("ngay").n.sum()
    moi_nhat = s.index.max()
    tam_tinh = _ngay_tam_tinh(moi_nhat.date().isoformat())
    s = s.reindex(pd.date_range(s.index.min(), moi_nhat), fill_value=0)
    out = []
    for d, n in s.items():
        if d.date() < tu or (d == moi_nhat and tam_tinh):
            continue
        truoc = [s.get(d - pd.Timedelta(days=7 * k)) for k in range(1, 5)]
        truoc = [int(x) for x in truoc if x is not None]
        tb = sum(truoc) / len(truoc) if truoc else None
        if n == 0 or (tb and n < NGAY_THAP * tb):
            out.append({"ngay": d.date().isoformat(), "thu": THU[d.weekday()], "online": int(n),
                        "tb_cung_thu": round(tb, 1) if tb else None,
                        "ty_le": round(n / tb * 100) if tb else None,
                        "van_de": "Không có hợp đồng nào" if n == 0 else "Thấp dưới 50% bình quân cùng thứ"})
    return pd.DataFrame(out, columns=["ngay", "thu", "online", "tb_cung_thu", "ty_le", "van_de"])


def _ngay_tam_tinh(ngay_iso: str) -> bool:
    from app.overview import trang_thai_ngay
    return trang_thai_ngay(ngay_iso)[0]


def lan_nap_bat_thuong(thang: str, cn: str) -> pd.DataFrame:
    """Lần nạp 30 ngày gần nhất, còn đang là file mới nhất của loại đó: ít dòng hơn lần trước cùng loại từ 10%,
    có dòng lỗi hoặc dòng trùng hợp đồng.

    Mỗi chi nhánh xuất file riêng nên "lần trước cùng loại" là lần gần nhất cùng loại file có số dòng cùng
    cỡ (chênh không quá một nửa) - không đem file Quảng Nam so với file Đà Nẵng.
    """
    df = _q("""SELECT id, dataset, file_name, rows_total, rows_invalid, rows_duplicate, uploaded_at, uploaded_by
               FROM upload_batch WHERE dataset IN ('internet', 'fptplay', 'camera') ORDER BY id""")
    if df.empty:
        return df
    ten = {"internet": "Internet", "fptplay": "Truyền hình", "camera": "Camera"}
    gan = pd.Timestamp.now('UTC').tz_localize(None) - pd.Timedelta(days=30)
    out = []
    for loai, g in df.groupby("dataset"):
        g = g.sort_values("id")
        for i, r in enumerate(g.itertuples()):
            if pd.Timestamp(r.uploaded_at) < gan:
                continue
            truoc = [x for x in g.iloc[:i].itertuples()
                     if x.rows_total and 0.5 <= r.rows_total / x.rows_total <= 2]
            tr = truoc[-1] if truoc else None
            van_de = []
            if tr and r.rows_total < tr.rows_total * (1 - GIAM_DONG) and r.rows_total >= 0.5 * tr.rows_total:
                van_de.append(f"Ít hơn lần trước {round((1 - r.rows_total / tr.rows_total) * 100)}% "
                              f"({tr.rows_total:,} → {r.rows_total:,} dòng)".replace(",", "."))
            if r.rows_invalid:
                van_de.append(f"{r.rows_invalid} dòng lỗi bị bỏ qua")
            # Camera có dòng giống hệt là bình thường (BGĐ chốt đếm từng dòng), Truyền hình luôn có ~10 cặp trùng
            # sẵn trong export -> chỉ báo dòng trùng với Internet (1 dòng = 1 hợp đồng)
            if r.rows_duplicate and loai == "internet":
                van_de.append(f"{r.rows_duplicate} dòng trùng hợp đồng trong file")
            # đã có lần nạp sau cùng loại, cùng cỡ file thì file này không còn quyết định số - bỏ qua
            sau = [x for x in g.iloc[i + 1:].itertuples() if x.rows_total and 0.5 <= x.rows_total / r.rows_total <= 2]
            if van_de and not sau:
                out.append({"lan_nap": r.id, "loai": ten.get(loai, loai), "file_name": r.file_name,
                            "luc": sv.chu_gio_vn(r.uploaded_at), "nguoi_nap": r.uploaded_by,
                            "so_dong": r.rows_total, "van_de": " · ".join(van_de)})
    return pd.DataFrame(out).sort_values("lan_nap", ascending=False) if out else pd.DataFrame()


# ------------------------------------------------------------------ nhóm: gán phòng & danh mục
def chua_gan(thang: str, cn: str) -> pd.DataFrame:
    return _loc_cn(sv.chua_gan_phong(thang), cn)


def acc_ngoai_danh_muc(thang: str, cn: str) -> pd.DataFrame:
    df = sv.acc_la(thang)
    df = df[df.nhom == "Cần xem"] if len(df) else df
    if cn and cn != "all" and len(df):
        df = df[df.acc.astype(str).str.upper().str.startswith(cn + ".")]
    return df.drop(columns="nhom", errors="ignore")


def danh_muc_trung(thang: str, cn: str) -> pd.DataFrame:
    return sv.acc_trung_danh_muc()


def nghi_van_co_so(thang: str, cn: str) -> pd.DataFrame:
    """Acc đã ghi chú Nghỉ trong danh mục nhưng vẫn có hợp đồng online trong tháng."""
    tu, den, _ = month_range(thang)
    df = _q("""SELECT s.acc, s.phong_code, s.ghi_chu, COUNT(*) AS so_hd, MAX(f.ngay_online) AS gan_nhat
               FROM staff_map s JOIN fact_internet f ON f.acc_norm = s.acc_norm
               WHERE COALESCE(s.ghi_chu, '') LIKE '%Nghỉ%' AND f.ngay_online >= :tu AND f.ngay_online <= :den
               GROUP BY s.acc, s.phong_code, s.ghi_chu ORDER BY so_hd DESC""",
            tu=tu.isoformat(), den=den.isoformat())
    df = _loc_cn(df, cn, cot_phong="phong_code")
    ten = _ten_phong()
    return df.assign(phong=[ten.get(c, c) for c in df.phong_code]).drop(columns="phong_code")


def lech_phong_giua_file(thang: str, cn: str) -> pd.DataFrame:
    """Cùng hợp đồng nhưng Truyền hình / Camera đang về phòng khác với Internet."""
    tu, den, _ = month_range(thang)
    phan = []
    for ten, bang in sv.BANG_SO[1:]:
        phan.append(f"""SELECT DISTINCT '{ten}' AS loai, f.hop_dong, i.acc_nhan_vien AS acc_internet,
                               f.acc_nhan_vien AS acc_file, i.phong_code AS phong_internet, f.phong_code AS phong_file,
                               f.cn_ban
                        FROM {bang} f JOIN fact_internet i ON i.hop_dong = f.hop_dong
                        WHERE f.ngay_online >= :tu AND f.ngay_online <= :den
                          AND COALESCE(f.phong_code, '') <> COALESCE(i.phong_code, '')""")
    df = _loc_cn(_q(" UNION ALL ".join(phan), tu=tu.isoformat(), den=den.isoformat()), cn)
    ten = _ten_phong()
    return df.assign(phong_internet=[ten.get(c, c) for c in df.phong_internet],
                     phong_file=[ten.get(c, c) for c in df.phong_file])


# ------------------------------------------------------------------ nhóm: dữ liệu thiếu / lạ
def truong_thieu_la(thang: str, cn: str) -> pd.DataFrame:
    """Dòng thiếu acc, thiếu / lạ CN Bán, gói FPT Play không xác định, ngày vô lý."""
    tu, den, _ = month_range(thang)
    p = {"tu": tu.isoformat(), "den": den.isoformat()}
    hop_le = ",".join(repr(c) for c in CN_HOP_LE)
    phan = []
    for ten, bang in sv.BANG_SO:
        dk_thang = "((ngay_online >= :tu AND ngay_online <= :den) OR (ngay_tao_hd >= :tu AND ngay_tao_hd <= :den))"
        van_de = [
            ("COALESCE(acc_nhan_vien, '') = ''", "Thiếu acc nhân viên bán"),
            ("COALESCE(cn_ban, '') = ''", "Thiếu CN Bán"),
            (f"COALESCE(cn_ban, '') <> '' AND cn_ban NOT IN ({hop_le}) AND cn_ban NOT LIKE '%ECOM%'",
             "CN Bán không thuộc DNG_01 / DNG_02 / QNM / ECOM"),
            ("ngay_online IS NOT NULL AND ngay_tao_hd IS NOT NULL AND ngay_online < ngay_tao_hd",
             "Ngày online trước ngày tạo hợp đồng"),
            ("ngay_online > CURRENT_DATE", "Ngày online ở tương lai"),
        ]
        if bang == "fact_fptplay":
            van_de.append(("UPPER(COALESCE(goi_fpt_play, '')) IN ('', 'KXD', 'KXĐ')",
                           "Gói FPT Play không xác định"))
        for dk, mo_ta in van_de:
            phan.append(f"""SELECT '{ten}' AS loai, hop_dong, acc_nhan_vien AS acc, cn_ban, ngay_tao_hd,
                                   ngay_online, '{mo_ta}' AS van_de
                            FROM {bang} WHERE {dk_thang} AND {dk}""")
    df = _q(" UNION ALL ".join(phan), **p)
    if cn and cn != "all":        # dòng thiếu CN Bán vẫn giữ khi lọc chi nhánh - không biết thuộc đâu
        df = df[df.cn_ban.fillna("").eq("") | df.cn_ban.fillna("").str.upper().str.startswith(cn)]
    return df.sort_values(["van_de", "loai"]).reset_index(drop=True)


def khong_co_internet(thang: str, cn: str) -> pd.DataFrame:
    """Truyền hình / Camera online trong tháng nhưng không có hợp đồng trong file Internet."""
    tu, den, _ = month_range(thang)
    phan = [f"""SELECT '{ten}' AS loai, f.hop_dong, f.acc_nhan_vien AS acc, f.cn_ban, f.phong_code,
                       f.ngay_tao_hd, f.ngay_online
                FROM {bang} f LEFT JOIN fact_internet i ON i.hop_dong = f.hop_dong
                WHERE f.ngay_online >= :tu AND f.ngay_online <= :den AND i.hop_dong IS NULL"""
            for ten, bang in sv.BANG_SO[1:]]
    df = _loc_cn(_q(" UNION ALL ".join(phan), tu=tu.isoformat(), den=den.isoformat()), cn)
    ten = _ten_phong()
    return (df.assign(phong=[ten.get(c, c) for c in df.phong_code]).drop(columns="phong_code")
            .drop_duplicates().sort_values(["loai", "ngay_online"]).reset_index(drop=True))


def nguon_kxd(thang: str, cn: str) -> pd.DataFrame:
    tu, den, _ = month_range(thang)
    df = _q("""SELECT hop_dong, acc_nhan_vien AS acc, cn_ban, phong_code, ngay_online, nguon_ban
               FROM fact_internet WHERE ngay_online >= :tu AND ngay_online <= :den
                 AND UPPER(COALESCE(nguon_ban, '')) IN ('', 'KXĐ', 'KXD')
               ORDER BY ngay_online DESC""", tu=tu.isoformat(), den=den.isoformat())
    df = _loc_cn(df, cn)
    ten = _ten_phong()
    return df.assign(phong=[ten.get(c, c) for c in df.phong_code]).drop(columns="phong_code")


# ------------------------------------------------------------------ nhóm: hợp đồng
def hd_ngung(thang: str, cn: str) -> pd.DataFrame:
    df = sv.hd_bat_thuong(thang)
    if cn and cn != "all" and len(df):
        thuoc = {p["ten"] for p in phong_order() if p.get("chi_nhanh") == cn}
        df = df[df.phong.isin(thuoc)]
    return df


def ton_lau(thang: str, cn: str) -> pd.DataFrame:
    df = sv.ton_dong_lau(7)
    if cn and cn != "all" and len(df):
        thuoc = {p["ten"] for p in phong_order() if p.get("chi_nhanh") == cn}
        df = df[df.phong.isin(thuoc)]
    return df


# ------------------------------------------------------------------ nhóm: cấu hình tháng
def thieu_muc_tieu(thang: str, cn: str) -> pd.DataFrame:
    tg = _q("""SELECT ma_doi_tuong, chi_tieu, gia_tri FROM target_monthly
               WHERE thang = :t AND doi_tuong = 'PHONG'""", t=thang)
    co = {(r.ma_doi_tuong, r.chi_tieu) for r in tg.itertuples() if r.gia_tri}
    ten_ct = {"internet": "Mục tiêu Internet", "camera": "Mục tiêu Camera", "ngay": "Mục tiêu ngày"}
    out = []
    for p in phong_order(thang):
        if p.get("loai") not in ("IBB", "DIABAN", "KT", "CUS", "ECOM") or (cn not in (None, "", "all")
                                                                           and p.get("chi_nhanh") != cn):
            continue
        thieu = [ten for ma, ten in ten_ct.items() if (p["code"], ma) not in co]
        if thieu:
            out.append({"phong": p["ten"], "loai_phong": p.get("loai"), "thieu": ", ".join(thieu)})
    return pd.DataFrame(out)


def thieu_file_nsld(thang: str, cn: str) -> pd.DataFrame:
    """Tháng trong năm (tới tháng trước kỳ đang xem) chưa nạp file NSLĐ."""
    co = set(_q("SELECT DISTINCT thang FROM hr_monthly").thang.dropna())
    nam, t = int(thang[:4]), int(thang[5:7])
    return pd.DataFrame([{"thang": f"{m:02d}/{nam}", "van_de": "Chưa nạp file NSLĐ"}
                         for m in range(1, t) if f"{nam}-{m:02d}" not in co])


def nv_thieu_nsld(thang: str, cn: str) -> pd.DataFrame:
    df = sv.nv_thieu_ho_so(thang)
    if cn and cn != "all" and len(df):
        df = df[df.chi_nhanh == cn]
    return df.drop(columns="thang_nsld", errors="ignore")


def tp_chua_gan_phong(thang: str, cn: str) -> pd.DataFrame:
    df = _q("SELECT username, ho_ten, scope FROM users WHERE role IN ('phong', 'bay') AND active = TRUE")
    df = df[df.scope.fillna("").isin(["", "[]", "null"])]
    return df.drop(columns="scope").assign(van_de="Tài khoản Trưởng phòng chưa chọn phòng phụ trách")


def co_cau_thang(thang: str, cn: str) -> pd.DataFrame:
    """Tháng trước có cơ cấu bầy riêng mà tháng này chưa khai - đang dùng cơ cấu mặc định."""
    n = lambda t: int(_q("SELECT COUNT(*) AS n FROM phong_bay_thang WHERE thang = :t", t=t).n.iloc[0])  # noqa: E731
    if n(thang) or not n(prev_month(thang)):
        return pd.DataFrame()
    return pd.DataFrame([{"thang": f"{thang[5:7]}/{thang[:4]}",
                          "van_de": f"Tháng {prev_month(thang)[5:7]} có cơ cấu bầy riêng, tháng này chưa khai"}])


# ------------------------------------------------------------------ danh sách mục
def _so_hd(df: pd.DataFrame) -> int:
    return int(df.so_hd.sum()) if len(df) and "so_hd" in df.columns else 0


MUC: list[Muc] = [
    Muc("file_cham", "File nạp", "File chưa nạp tới ngày mới nhất", NGHIEM_TRONG,
        "Nạp bổ sung file còn chậm (mỗi chi nhánh một file). Chưa nạp thì số V.VIP / Camera của những ngày "
        "đó đang thiếu.", file_cham_ngay,
        {"loai": "Loại file", "chi_nhanh": "Chi nhánh", "ngay": "Có số đến", "moi_nhat_chung": "File mới nhất tới",
         "cham_ngay": "Chậm (ngày)"}),
    Muc("ngay_bat_thuong", "File nạp", "Ngày không có số hoặc thấp bất thường", CAN_SOAT,
        "Online dưới 50% bình quân cùng thứ 4 tuần trước (hoặc bằng 0): kiểm tra file của ngày đó có bị thiếu "
        "dòng không. Ngày lễ thì bỏ qua.", ngay_bat_thuong,
        {"ngay": "Ngày", "thu": "Thứ", "online": "Online", "tb_cung_thu": "TB cùng thứ", "ty_le": "% so TB",
         "van_de": "Vấn đề"}, don_vi="ngày"),
    Muc("lan_nap", "File nạp", "File đang dùng bị nạp bất thường", CAN_SOAT,
        "File ít dòng hơn lần trước từ 10% có thể bị tải thiếu (lọc sai ngày, sai chi nhánh) - tải lại từ "
        "Inside rồi nạp lại. Dòng lỗi / dòng trùng xem chi tiết ở Nạp dữ liệu → Lịch sử.", lan_nap_bat_thuong,
        {"lan_nap": "Lần nạp", "loai": "Loại", "file_name": "File", "luc": "Lúc nạp", "nguoi_nap": "Người nạp",
         "so_dong": "Số dòng", "van_de": "Vấn đề"}, don_vi="lần nạp"),

    Muc("chua_gan", "Gán phòng & danh mục", "Hợp đồng chưa gán phòng", NGHIEM_TRONG,
        "Acc bán không có trong danh mục và không thuộc quy tắc KT/CUS/ECOM - số chưa về phòng nào (vẫn cộng "
        "tổng chi nhánh). Quản trị → Danh mục nhân sự → thêm acc → Tính lại việc gán phòng.", chua_gan,
        {"loai": "Loại", "acc": "Acc", "ma_nv": "Mã NV", "phong_he_thong": "Phòng hệ thống", "cn_ban": "CN Bán",
         "so_hd": "Số HĐ", "tu_ngay": "Từ ngày", "den_ngay": "Đến ngày"}, dem=_so_hd, don_vi="HĐ"),
    Muc("danh_muc_trung", "Gán phòng & danh mục", "Danh mục khai sai hoặc trùng", NGHIEM_TRONG,
        "Acc khai nhiều dòng không rõ ngày hiệu lực, hoặc khác phòng BGĐ đã chốt - số đang về sai phòng. Sửa ở "
        "Quản trị → Danh mục nhân sự.", danh_muc_trung,
        {"acc": "Acc", "van_de": "Vấn đề", "dang_khai": "Đang khai ở"}, don_vi="acc"),
    Muc("acc_ngoai", "Gán phòng & danh mục", "Acc ngoài danh mục cần xem", CAN_SOAT,
        "Acc đang tính cho phòng kinh doanh, chưa gán phòng hoặc có trong NSLĐ nhưng chưa khai danh mục - nhiều "
        "khả năng là nhân viên kinh doanh bị sót.", acc_ngoai_danh_muc,
        {"acc": "Acc", "dang_tinh_cho": "Đang tính cho", "so_hd": "Số HĐ", "gan_nhat": "Gần nhất",
         "co_nsld": "Có NSLĐ"}, don_vi="acc"),
    Muc("nghi_co_so", "Gán phòng & danh mục", "Nhân sự đã ghi Nghỉ vẫn có số", CAN_SOAT,
        "Danh mục ghi Nghỉ nhưng acc vẫn có hợp đồng online trong tháng: ghi chú sai, nghỉ giữa tháng, hoặc acc "
        "đang được người khác dùng. Kiểm tra và sửa danh mục.", nghi_van_co_so,
        {"acc": "Acc", "phong": "Phòng", "ghi_chu": "Ghi chú", "so_hd": "Số HĐ tháng", "gan_nhat": "Gần nhất"},
        don_vi="acc"),
    Muc("lech_phong", "Gán phòng & danh mục", "Cùng hợp đồng nhưng khác phòng giữa các file", CAN_SOAT,
        "Truyền hình / Camera của một hợp đồng đang về phòng khác với Internet (acc bán khác nhau giữa file). "
        "Soát lại acc trên Inside.", lech_phong_giua_file,
        {"loai": "File", "hop_dong": "Hợp đồng", "acc_internet": "Acc Internet", "acc_file": "Acc file này",
         "phong_internet": "Phòng Internet", "phong_file": "Phòng file này", "cn_ban": "CN Bán"}, don_vi="HĐ"),

    Muc("truong_thieu", "Dữ liệu thiếu / lạ", "Dòng thiếu thông tin hoặc giá trị lạ", CAN_SOAT,
        "Thiếu acc / CN Bán thì không gán được phòng; CN Bán lạ, gói không xác định, ngày vô lý thường do lỗi "
        "xuất file - đối chiếu hợp đồng trên Inside.", truong_thieu_la,
        {"van_de": "Vấn đề", "loai": "File", "hop_dong": "Hợp đồng", "acc": "Acc", "cn_ban": "CN Bán",
         "ngay_tao_hd": "Ngày tạo", "ngay_online": "Ngày online"}),
    Muc("khong_net", "Dữ liệu thiếu / lạ", "Truyền hình / Camera không có hợp đồng Internet", CAN_SOAT,
        "Online trong tháng nhưng không tìm thấy hợp đồng trong file Internet: kiểm tra file NET có thiếu dòng, "
        "hoặc hợp đồng Internet đã trôi khỏi file cuộn 3 tháng.", khong_co_internet,
        {"loai": "File", "hop_dong": "Hợp đồng", "acc": "Acc", "phong": "Phòng", "cn_ban": "CN Bán",
         "ngay_tao_hd": "Ngày tạo", "ngay_online": "Ngày online"}),
    Muc("nguon_kxd", "Dữ liệu thiếu / lạ", "Nguồn bán không xác định (KXĐ)", THONG_TIN,
        "Hợp đồng Internet có nguồn bán KXĐ hoặc trống - không ảnh hưởng số online, chỉ ảnh hưởng thống kê theo "
        "nguồn.", nguon_kxd,
        {"hop_dong": "Hợp đồng", "acc": "Acc", "phong": "Phòng", "cn_ban": "CN Bán", "ngay_online": "Ngày online",
         "nguon_ban": "Nguồn"}, don_vi="HĐ"),

    Muc("hd_ngung", "Hợp đồng", "Hợp đồng đã ngưng / chấm dứt vẫn tính online", THONG_TIN,
        "Tình trạng hiện tại không còn Bình thường. BGĐ chốt vẫn tính như sheet - liệt kê để theo dõi.", hd_ngung,
        {"hop_dong": "Hợp đồng", "acc": "Acc", "tinh_trang": "Tình trạng", "ngay_online": "Ngày online",
         "ngay_huy": "Ngày hủy", "phong": "Phòng"}, don_vi="HĐ"),
    Muc("ton_lau", "Hợp đồng", "Tồn đọng triển khai từ 7 ngày", THONG_TIN,
        "Hợp đồng tạo từ 7 ngày chưa online, còn trong file mới nhất. Chi tiết ở Phân tích bán hàng → Số tồn.",
        ton_lau, {"phong": "Phòng", "so_hd": "HĐ chờ từ 7 ngày", "tuoi_tb": "Chờ TB (ngày)"}, dem=_so_hd,
        don_vi="HĐ"),

    Muc("muc_tieu", "Cấu hình tháng", "Phòng chưa có mục tiêu tháng", CAN_SOAT,
        "Thiếu mục tiêu thì cột HTKH, dự báo % mục tiêu và kết luận ngày không tính được. Nhập ở Quản trị → "
        "Chỉ tiêu.", thieu_muc_tieu, {"phong": "Phòng", "loai_phong": "Loại", "thieu": "Còn thiếu"},
        don_vi="phòng"),
    Muc("co_cau", "Cấu hình tháng", "Cơ cấu bầy tháng chưa khai", THONG_TIN,
        "Tháng trước có cơ cấu bầy riêng mà tháng này chưa khai - app đang dùng cơ cấu mặc định. Khai ở Quản trị → "
        "Cơ cấu tổ chức (có nút sao chép tháng trước).", co_cau_thang, {"thang": "Tháng", "van_de": "Vấn đề"},
        don_vi="tháng"),
    Muc("file_nsld", "Cấu hình tháng", "Tháng chưa nạp file NSLĐ", CAN_SOAT,
        "Thiếu file thì NSLĐ theo tháng và tân binh bị trống tháng đó. Nạp ở Nạp dữ liệu (chỉ Quản trị).",
        thieu_file_nsld, {"thang": "Tháng", "van_de": "Vấn đề"}, don_vi="tháng"),
    Muc("nv_thieu_nsld", "Cấu hình tháng", "Nhân sự kinh doanh thiếu NSLĐ", CAN_SOAT,
        "Có trong danh mục phòng kinh doanh, đang làm, nhưng không có trong file NSLĐ gần nhất nên thiếu thâm "
        "niên, điểm NSLĐ.", nv_thieu_nsld, {"acc": "Acc", "phong": "Phòng", "ma_nv": "Mã NV",
                                             "chi_nhanh": "Chi nhánh"}, don_vi="người"),
    Muc("tp_chua_gan", "Cấu hình tháng", "Tài khoản Trưởng phòng chưa chọn phòng", CAN_SOAT,
        "Trưởng phòng chưa được chọn phòng phụ trách thì không xem được Báo cáo phòng. Sửa ở Quản trị → Tài khoản.",
        tp_chua_gan_phong, {"username": "Tài khoản", "ho_ten": "Họ tên", "van_de": "Vấn đề"}, don_vi="tài khoản"),
]
MUC_THEO_MA = {m.ma: m for m in MUC}


def chay(thang: str, cn: str | None = None) -> list[dict]:
    """Chạy mọi mục. Mỗi phần tử: thông tin mục + so_luong + bảng chi tiết (records, tối đa TOI_DA_DONG dòng).
    Mục nào lỗi khi chạy thì báo lỗi trong chính mục đó, không làm hỏng cả trang."""
    kq = []
    for m in MUC:
        try:
            df = m.ham(thang, cn or "all")
            df = df if df is not None else pd.DataFrame()
            so = int(m.dem(df)) if len(df) else 0
            loi = ""
        except Exception as e:                               # pragma: no cover - để trang vẫn mở được
            df, so, loi = pd.DataFrame(), 0, f"{type(e).__name__}: {str(e)[:160]}"
        kq.append({"ma": m.ma, "nhom": m.nhom, "ten": m.ten, "muc_do": m.muc_do if so or loi else "Ổn",
                   "muc_do_goc": m.muc_do, "so_luong": so, "don_vi": m.don_vi, "xu_ly": m.xu_ly, "loi": loi,
                   "cot": {k: v for k, v in m.cot.items() if k in df.columns},
                   "dong": _ban_ghi(df.head(TOI_DA_DONG)), "tong_dong": len(df)})
    return sorted(kq, key=lambda r: (r["muc_do"] == "Ổn", THU_TU_MUC_DO.get(r["muc_do_goc"], 9)))


def _ban_ghi_df(df: pd.DataFrame) -> pd.DataFrame:
    """Ngày -> chữ YYYY-MM-DD, số thực nguyên -> số nguyên, trống -> None (dùng cho trang và Excel)."""
    d = df.astype(object).where(df.notna(), None)
    for c in d.columns:
        d[c] = [str(v)[:10] if hasattr(v, "isoformat") and not isinstance(v, str) else
                (int(v) if isinstance(v, float) and v.is_integer() else v) for v in d[c]]
    return d


def _ban_ghi(df: pd.DataFrame) -> list[dict]:
    return [] if df.empty else _ban_ghi_df(df).to_dict("records")
