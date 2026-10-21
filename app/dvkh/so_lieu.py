"""Số liệu khối DVKH: đọc database, thêm cột suy ra, tính các chỉ số theo phòng / quận / chương trình / nhân sự.

Quy tắc đã đối chiếu với các sheet báo cáo của file (T10/2026, nguồn là Người xử lý chứ không phải "Nhân sự AU"):
- *Nhân sự* (Account IS) của SR bị động và SR chủ động = cột **Người xử lý** (khớp bảng "BC SR bị động" / "BC SR chủ động").
- *Phân công* = SR đã có người xử lý. *Tồn* = Chưa xử lý + Đang xử lý (+ Chưa phân công với SR chủ động).
- *Quá hạn* = "Hoàn tất quá hạn" + "Quá hạn đang xử lý" (cột Quá hạn của file, đã tính theo hạn xử lý của từng loại SR).
- SR chủ động chia theo chương trình như bảng BC: Nguy cơ rời mạng (SOS) = Ngưng kết nối + Dự đoán RM + Nguy cơ sang rời mạng
  nợ cước; KSRM T = "CSKH không PSLL vết T"; KSRM T-1 = "CSKH không PSLL vết T-"; CLL = "CSKH có Checklist lặp".
- *Không liên lạc được* (Ko lldc) chỉ tính trên SR đã thử liên hệ: Gặp + Không liên lạc được + Gặp KH từ chối + Không gặp.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import text

from app.bo_nho import nho
from app.db import engine
from app.dvkh import nap
from app.dvkh.doc_file import QUAN_CU, bo_dau

PHONG = {"DNG_01": "DNG1", "DNG_02": "DNG2"}
DA_XU_LY = ("Đã xử lý", "Đã hoàn tất")
TON_BD = ("Chưa xử lý", "Đang xử lý", "Chưa phân công")
QUA_HAN = ("Hoàn tất quá hạn", "Quá hạn đang xử lý")
TAI_KHOAN_TU_DONG = ("autocall",)               # tài khoản máy gọi tự động, không phải CSKH: tách khỏi bảng nhân sự
KENH_SO = ("Zalo", "Hi FPT", "Hi FPT Chat", "Hi FPT YC", "MobiX", "Fpt.vn", "Email", "Online khác")
KENH_THOAI = ("Điện thoại", "AnsCall", "Quầy giao dịch", "CSKH mở rộng", "KBN", "KTC")
DA_THU_LIEN_HE = ("Gặp trực tiếp người sử dụng", "Gặp trực tiếp khách hàng", "Không liên lạc được", "Gặp KH, KH từ chối",
                  "Không gặp trực tiếp KH", "Không gặp trực tiếp khách hàng")
GAP_KHACH = ("Gặp trực tiếp người sử dụng", "Gặp trực tiếp khách hàng")
NHOM_CT = {"Ngưng kết nối": "Nguy cơ rời mạng (SOS)", "Dự đoán RM": "Nguy cơ rời mạng (SOS)",
           "Nguy cơ sang rời mạng nợ cước (CTBDV)": "Nguy cơ rời mạng (SOS)", "CSKH không PSLL vết T": "KSRM T",
           "CSKH không PSLL vết T-": "KSRM T-1", "CSKH có Checklist lặp": "CLL (Checklist lặp)"}
DIEM_RM_BAC = [(-1.5, 0, "Không có điểm"), (0, 300, "Dưới 300"), (300, 600, "300 đến 599"), (600, 800, "600 đến 799"),
               (800, 10_000, "Từ 800")]


_TEN_PHUONG = {bo_dau(k): k for k in QUAN_CU}


def ten_phuong(ten) -> str:
    """"Phuong Hoa Xuan" (file rời mạng, công nợ không dấu) -> "Phường Hòa Xuân" (tên có dấu như file SR)."""
    return _TEN_PHUONG.get(bo_dau(ten), str(ten))


def co_du_lieu() -> bool:
    nap.dam_bao_bang()
    with engine.connect() as c:
        return bool(c.execute(text("SELECT COUNT(*) FROM dv_nap")).scalar())


def _them_chung(df: pd.DataFrame) -> pd.DataFrame:
    df["phong"] = df["chi_nhanh"].map(PHONG).fillna(df["chi_nhanh"])
    df["quan_cu"] = df["quan"].map(QUAN_CU).fillna(df["quan"])
    return df


@nho("dvkh", 30)
def sr_bi_dong() -> pd.DataFrame:
    """SR bị động kèm các cột suy ra (giờ phản hồi, thời gian đóng, cờ tồn / quá hạn / khách rời mạng sau SR, SR lặp)."""
    nap.dam_bao_bang()
    df = pd.read_sql_query(text("SELECT * FROM dv_sr_bi_dong"), engine, parse_dates=["tg_yc", "tg_cn_dau", "tg_cn_cuoi"])
    if df.empty:
        return df
    df = _them_chung(df)
    df["ngay_yc"] = pd.to_datetime(df["tg_yc"]).dt.normalize()
    p = (df["tg_cn_dau"] - df["tg_yc"]).dt.total_seconds() / 60
    df["phan_hoi_phut"] = p.where(p >= 0)
    d = (df["tg_cn_cuoi"] - df["tg_yc"]).dt.total_seconds() / 3600
    df["xu_ly_gio"] = d.where((d >= 0) & df["tinh_trang"].isin(DA_XU_LY))
    df["da_xu_ly"] = df["tinh_trang"].isin(DA_XU_LY)
    df["ton"] = df["tinh_trang"].isin(TON_BD)
    df["that_bai"] = df["tinh_trang"].eq("Xử lý không thành công")
    df["qua_han_cd"] = df["qua_han"].isin(QUA_HAN)
    df["roi_mang_sau"] = df["net_hien"].eq("Đã chấm dứt hợp đồng")
    tv = df["ket_qua_tu_van"].fillna("")
    df["o_lai"] = tv.str.startswith("Khách hàng đồng ý")                        # "không đồng ý" cũng chứa chữ "đồng ý": chỉ lấy câu bắt đầu bằng đồng ý
    df["muon_di"] = tv.str.contains("không đồng ý")
    df["la_dvkh"] = df["don_vi_xu_ly"].fillna("").str.lower().str.contains("dịch vụ khách hàng")   # còn lại: kỹ thuật, hỗ trợ khách hàng...
    n = df.groupby("so_hd")["ma_sr"].transform("size")
    df["so_sr_cung_hd"] = n
    df["lap"] = n >= 2
    df["gio"] = pd.to_datetime(df["tg_yc"]).dt.hour
    df["thu"] = pd.to_datetime(df["tg_yc"]).dt.dayofweek
    df["nhom_kenh"] = np.where(df["kenh"].isin(KENH_SO), "Kênh số", np.where(df["kenh"].isin(KENH_THOAI), "Thoại / quầy", "Khác"))
    return df


@nho("dvkh", 30)
def sr_chu_dong() -> pd.DataFrame:
    """SR chủ động kèm nhóm chương trình theo bảng BC, bậc điểm nguy cơ, cờ liên hệ / tồn / quá hạn."""
    nap.dam_bao_bang()
    df = pd.read_sql_query(text("SELECT * FROM dv_sr_chu_dong"), engine,
                           parse_dates=["tg_do", "tg_phan_cong", "tg_cn_dau", "tg_cn_cuoi"])
    if df.empty:
        return df
    df = _them_chung(df)
    df["ngay_do"] = pd.to_datetime(df["tg_do"]).dt.normalize()
    df["nhom_bc"] = df["chuong_trinh"].str.strip().map(NHOM_CT).fillna("Chương trình khác")
    df["ton"] = df["tinh_trang"].isin(("Chưa xử lý", "Đang xử lý", "Chưa phân công"))
    df["tu_dong"] = df["nguoi_xu_ly"].fillna("").str.lower().isin(TAI_KHOAN_TU_DONG)
    df["chua_phan_cong"] = df["tinh_trang"].eq("Chưa phân công") | df["nguoi_xu_ly"].isna()
    df["da_thu_lien_he"] = df["ket_qua_lien_he"].isin(DA_THU_LIEN_HE)
    df["gap_khach"] = df["ket_qua_lien_he"].isin(GAP_KHACH)
    df["khong_lien_lac"] = df["ket_qua_lien_he"].eq("Không liên lạc được")
    df["khong_can_lh"] = df["ket_qua_lien_he"].eq("Không cần liên hệ")
    df["dong_tu_dong"] = df["tinh_trang"].eq("Đóng tự động bởi hệ thống")
    df["qua_han_cd"] = df["qua_han"].isin(QUA_HAN)
    df["muon_thanh_ly"] = df["ket_qua_tu_van"].fillna("").str.contains("yêu cầu thanh lý", case=False)
    df["o_lai"] = df["ket_qua_tu_van"].fillna("").str.contains("đồng ý sử dụng tiếp", case=False)
    d = (df["tg_cn_dau"] - df["tg_phan_cong"]).dt.total_seconds() / 3600
    df["phan_hoi_gio"] = d.where(d >= 0)
    diem = df["diem_rm"].fillna(-1)
    df["bac_diem"] = pd.cut(diem, [b[0] for b in DIEM_RM_BAC] + [10_000], right=False,
                            labels=[b[2] for b in DIEM_RM_BAC]).astype(str)
    return df


@nho("dvkh", 30)
def roi_mang() -> pd.DataFrame:
    nap.dam_bao_bang()
    return pd.read_sql_query(text("SELECT * FROM dv_roi_mang ORDER BY ngay_chot, id"), engine, parse_dates=["ngay_chot"])


@nho("dvkh", 30)
def cong_no_ngay() -> pd.DataFrame:
    nap.dam_bao_bang()
    df = pd.read_sql_query(text("SELECT * FROM dv_cong_no ORDER BY ky_no, ngay"), engine, parse_dates=["ngay"])
    if not df.empty:
        df["ngay_thu"] = df.groupby(["ky_no", "cap", "ten"]).cumcount() + 1
        df["so_ngay"] = (df["ngay"] - df.groupby("ky_no")["ngay"].transform("min")).dt.days + 1
    return df


@nho("dvkh", 30)
def cong_no_chot() -> pd.DataFrame:
    nap.dam_bao_bang()
    return pd.read_sql_query(text("SELECT * FROM dv_cong_no_chot ORDER BY ngay_chot, id"), engine, parse_dates=["ngay_chot"])


@nho("dvkh", 30)
def ngay_du_lieu() -> dict[str, date | None]:
    """Ngày mới nhất của từng nguồn (để báo "số tới ngày nào" ngay trên trang)."""
    nap.dam_bao_bang()

    def mot(sql):
        with engine.connect() as c:
            v = c.execute(text(sql)).scalar()
        return pd.to_datetime(v).date() if v is not None else None
    return {"sr_bd": mot("SELECT MAX(ngay_yc) FROM dv_sr_bi_dong"), "sr_cd": mot("SELECT MAX(ngay_do) FROM dv_sr_chu_dong"),
            "roi_mang": mot("SELECT MAX(ngay_chot) FROM dv_roi_mang"), "cong_no": mot("SELECT MAX(ngay) FROM dv_cong_no"),
            "nap": mot("SELECT MAX(ngay_chot) FROM dv_nap")}


# ----------------------------------------------------------------------- tiện ích dùng chung
def chia(a, b, nhan: int = 100) -> float | None:
    """a / b theo %, None nếu mẫu số 0 (để bảng ghi "–" thay vì 0%)."""
    return None if not b else float(a) * nhan / float(b)


def loc(df: pd.DataFrame, phong: str | None = None, tu=None, den=None, cot_ngay: str = "ngay_yc") -> pd.DataFrame:
    if df.empty:
        return df
    if phong and phong != "all":
        df = df[df["phong"] == phong]
    if tu is not None:
        df = df[df[cot_ngay] >= pd.Timestamp(tu)]
    if den is not None:
        df = df[df[cot_ngay] <= pd.Timestamp(den)]
    return df


def dem_theo(df: pd.DataFrame, cot: str, top: int | None = None, trong: str = "(Chưa ghi)") -> pd.DataFrame:
    """Bảng số lượng và tỷ trọng theo một cột chữ, giảm dần."""
    if df.empty or cot not in df:
        return pd.DataFrame(columns=[cot, "so", "ty_trong"])
    s = df[cot].fillna(trong).value_counts()
    out = s.rename_axis(cot).reset_index(name="so")
    out["ty_trong"] = out["so"] * 100 / max(int(s.sum()), 1)
    return out.head(top) if top else out


# ----------------------------------------------------------------------- SR bị động
def kpi_bd(df: pd.DataFrame) -> dict:
    n = len(df)
    qh = df[df["qua_han"].notna()]
    ph = df["phan_hoi_phut"].dropna()
    xl = df["xu_ly_gio"].dropna()
    hd = df["so_hd"].nunique()
    return {
        "so_sr": n, "so_hd": hd, "phan_cong": int(df["nguoi_xu_ly"].notna().sum()),
        "da_xu_ly": int(df["da_xu_ly"].sum()), "ton": int(df["ton"].sum()), "that_bai": int(df["that_bai"].sum()),
        "chua_xu_ly": int(df["tinh_trang"].eq("Chưa xử lý").sum()), "dang_xu_ly": int(df["tinh_trang"].eq("Đang xử lý").sum()),
        "ty_le_xu_ly": chia(df["da_xu_ly"].sum(), n), "ty_le_ton": chia(df["ton"].sum(), n),
        "qua_han": int(df["qua_han_cd"].sum()), "ty_le_qua_han": chia(df["qua_han_cd"].sum(), len(qh)),
        "phan_hoi_p50": float(ph.median()) if len(ph) else None, "phan_hoi_p90": float(ph.quantile(.9)) if len(ph) else None,
        "trong_60p": chia((ph <= 60).sum(), len(ph)), "xu_ly_p50_gio": float(xl.median()) if len(xl) else None,
        "sr_lap": int(df["lap"].sum()), "ty_le_lap": chia(df["lap"].sum(), n), "hd_lap": int((df.groupby("so_hd").size() >= 2).sum()),
        "khieu_nai": int(df["loai_yc"].eq("Khiếu nại, phàn nàn").sum()), "thanh_ly": int(df["loai_yc"].eq("Thanh lý").sum()),
        "roi_mang_sau": int(df["roi_mang_sau"].sum()), "ty_le_roi_mang_sau": chia(df["roi_mang_sau"].sum(), n),
        "phi": float(df["phi"].fillna(0).sum()), "mien_giam": float(df["mien_giam_phi"].fillna(0).sum()),
    }


def theo_nhan_su_bd(df: pd.DataFrame) -> pd.DataFrame:
    """Chỉ CSKH của các phòng dịch vụ khách hàng (người của đơn vị khác chỉ có vài SR chuyển sang)."""
    g = df[df["nguoi_xu_ly"].notna() & df["la_dvkh"]].groupby("nguoi_xu_ly")
    if g.ngroups == 0:
        return pd.DataFrame()
    out = g.agg(phan_cong=("ma_sr", "size"), da_xu_ly=("da_xu_ly", "sum"), ton=("ton", "sum"), qua_han=("qua_han_cd", "sum"),
                that_bai=("that_bai", "sum"), phan_hoi_p50=("phan_hoi_phut", "median"), xu_ly_p50=("xu_ly_gio", "median"),
                khieu_nai=("loai_yc", lambda s: int((s == "Khiếu nại, phàn nàn").sum())),
                thanh_ly=("loai_yc", lambda s: int((s == "Thanh lý").sum())), phong=("phong", lambda s: s.mode().iat[0] if len(s.mode()) else ""))
    out["ty_le_xu_ly"] = out["da_xu_ly"] * 100 / out["phan_cong"]
    out["ty_le_qua_han"] = out["qua_han"] * 100 / out["phan_cong"]
    return out.reset_index().rename(columns={"nguoi_xu_ly": "nhan_su"}).sort_values("phan_cong", ascending=False)


def theo_ngay_bd(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    g = df.groupby("ngay_yc")
    return g.agg(so_sr=("ma_sr", "size"), da_xu_ly=("da_xu_ly", "sum"), ton=("ton", "sum"), qua_han=("qua_han_cd", "sum"),
                 khieu_nai=("loai_yc", lambda s: int((s == "Khiếu nại, phàn nàn").sum())),
                 thanh_ly=("loai_yc", lambda s: int((s == "Thanh lý").sum()))).reset_index()


def theo_loai_yc(df: pd.DataFrame) -> pd.DataFrame:
    """Mỗi loại yêu cầu: số SR, % tồn, % quá hạn, thời gian đóng trung vị, % khách đã chấm dứt hợp đồng sau SR."""
    if df.empty:
        return pd.DataFrame()
    g = df.groupby("loai_yc")
    out = g.agg(so_sr=("ma_sr", "size"), ton=("ton", "sum"), qua_han=("qua_han_cd", "sum"), xu_ly_p50=("xu_ly_gio", "median"),
                roi_mang_sau=("roi_mang_sau", "sum")).reset_index()
    out["ty_trong"] = out["so_sr"] * 100 / len(df)
    out["ty_le_ton"] = out["ton"] * 100 / out["so_sr"]
    out["ty_le_qua_han"] = out["qua_han"] * 100 / out["so_sr"]
    out["ty_le_roi_mang_sau"] = out["roi_mang_sau"] * 100 / out["so_sr"]
    return out.sort_values("so_sr", ascending=False)


def hop_dong_lap(df: pd.DataFrame, top: int = 30) -> pd.DataFrame:
    """Hợp đồng có từ 2 SR trở lên: gọi lại nhiều lần là dấu hiệu lần xử lý trước chưa dứt điểm."""
    if df.empty:
        return pd.DataFrame()
    g = df.groupby("so_hd").agg(so_sr=("ma_sr", "size"), lan_cuoi=("tg_yc", "max"), ton=("ton", "sum"), phong=("phong", "first"), quan=("quan", "first"))
    g = g[g["so_sr"] >= 2].sort_values(["so_sr", "lan_cuoi"], ascending=False).head(top)
    d = df[df["so_hd"].isin(g.index)][["so_hd", "loai_yc"]].dropna().drop_duplicates()
    g["loai"] = d.groupby("so_hd")["loai_yc"].agg(" · ".join).str.slice(0, 80)
    return g.reset_index()


# ----------------------------------------------------------------------- SR chủ động
def kpi_cd(df: pd.DataFrame) -> dict:
    n = len(df)
    thu = int(df["da_thu_lien_he"].sum())
    qh = df[df["qua_han"].notna()]
    ph = df["phan_hoi_gio"].dropna()
    return {
        "so_sr": n, "so_hd": df["so_hd"].nunique(), "phan_cong": int(df["nguoi_xu_ly"].notna().sum()),
        "chua_xu_ly": int(df["tinh_trang"].eq("Chưa xử lý").sum()), "chua_phan_cong": int(df["tinh_trang"].eq("Chưa phân công").sum()),
        "dang_xu_ly": int(df["tinh_trang"].eq("Đang xử lý").sum()), "ton": int(df["ton"].sum()), "ty_le_ton": chia(df["ton"].sum(), n),
        "dong_tu_dong": int(df["dong_tu_dong"].sum()), "ty_le_dong_tu_dong": chia(df["dong_tu_dong"].sum(), n),
        "khong_can_lh": int(df["khong_can_lh"].sum()), "ty_le_khong_can_lh": chia(df["khong_can_lh"].sum(), n),
        "da_thu_lien_he": thu, "gap_khach": int(df["gap_khach"].sum()), "khong_lien_lac": int(df["khong_lien_lac"].sum()),
        "ty_le_khong_lien_lac": chia(df["khong_lien_lac"].sum(), thu), "ty_le_gap": chia(df["gap_khach"].sum(), thu),
        "qua_han": int(df["qua_han_cd"].sum()), "ty_le_qua_han": chia(df["qua_han_cd"].sum(), len(qh)),
        "phan_hoi_p50_gio": float(ph.median()) if len(ph) else None,
        "muon_thanh_ly": int(df["muon_thanh_ly"].sum()), "o_lai": int(df["o_lai"].sum()),
        "no_cuoc": int(df["no_cuoc"].sum()), "ych": int(df["ych"].sum()), "tu_dong": int(df["tu_dong"].sum()),
    }


def theo_chuong_trinh(df: pd.DataFrame, cot: str = "chuong_trinh") -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    g = df.groupby(cot)
    out = g.agg(so_sr=("ma_sr", "size"), ton=("ton", "sum"), chua_phan_cong=("chua_phan_cong", "sum"), qua_han=("qua_han_cd", "sum"),
                thu=("da_thu_lien_he", "sum"), khong_lien_lac=("khong_lien_lac", "sum"), khong_can_lh=("khong_can_lh", "sum"),
                dong_tu_dong=("dong_tu_dong", "sum"), muon_thanh_ly=("muon_thanh_ly", "sum"), o_lai=("o_lai", "sum")).reset_index()
    out["ty_trong"] = out["so_sr"] * 100 / len(df)
    out["ty_le_ton"] = out["ton"] * 100 / out["so_sr"]
    out["ty_le_qua_han"] = out["qua_han"] * 100 / out["so_sr"]
    out["ty_le_khong_lien_lac"] = np.where(out["thu"] > 0, out["khong_lien_lac"] * 100 / out["thu"].replace(0, np.nan), np.nan)
    out["ty_le_khong_can_lh"] = out["khong_can_lh"] * 100 / out["so_sr"]
    out["ty_le_dong_tu_dong"] = out["dong_tu_dong"] * 100 / out["so_sr"]
    return out.sort_values("so_sr", ascending=False)


def theo_nhan_su_cd(df: pd.DataFrame) -> pd.DataFrame:
    g = df[df["nguoi_xu_ly"].notna() & ~df["tu_dong"]].groupby("nguoi_xu_ly")
    if g.ngroups == 0:
        return pd.DataFrame()
    out = g.agg(phan_cong=("ma_sr", "size"), ton=("ton", "sum"), qua_han=("qua_han_cd", "sum"), thu=("da_thu_lien_he", "sum"),
                khong_lien_lac=("khong_lien_lac", "sum"), dong_tu_dong=("dong_tu_dong", "sum"), o_lai=("o_lai", "sum"),
                muon_thanh_ly=("muon_thanh_ly", "sum"), phan_hoi_p50=("phan_hoi_gio", "median"),
                phong=("phong", lambda s: s.mode().iat[0] if len(s.mode()) else "")).reset_index()
    out = out.rename(columns={"nguoi_xu_ly": "nhan_su"})
    out["ty_le_ton"] = out["ton"] * 100 / out["phan_cong"]
    out["ty_le_qua_han"] = out["qua_han"] * 100 / out["phan_cong"]
    out["ty_le_khong_lien_lac"] = np.where(out["thu"] > 0, out["khong_lien_lac"] * 100 / out["thu"].replace(0, np.nan), np.nan)
    return out.sort_values("phan_cong", ascending=False)


def theo_ngay_cd(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    return df.groupby("ngay_do").agg(so_sr=("ma_sr", "size"), ton=("ton", "sum"), qua_han=("qua_han_cd", "sum"),
                                     khong_lien_lac=("khong_lien_lac", "sum")).reset_index()


def theo_bac_diem(df: pd.DataFrame) -> pd.DataFrame:
    """Điểm nguy cơ rời mạng càng cao thì khách có thực sự đòi thanh lý nhiều hơn không? (kiểm tra độ tin cậy của điểm)."""
    if df.empty:
        return pd.DataFrame()
    d = df[df["tinh_trang"].isin(DA_XU_LY + ("Đóng tự động bởi hệ thống",)) | df["ket_qua_tu_van"].notna()]
    out = d.groupby("bac_diem").agg(so_sr=("ma_sr", "size"), muon_thanh_ly=("muon_thanh_ly", "sum"), o_lai=("o_lai", "sum"),
                                    khong_lien_lac=("khong_lien_lac", "sum"), thu=("da_thu_lien_he", "sum")).reset_index()
    tt = [b[2] for b in DIEM_RM_BAC]
    out["thu_tu"] = out["bac_diem"].map({t: i for i, t in enumerate(tt)})
    out["ty_le_thanh_ly"] = out["muon_thanh_ly"] * 100 / out["so_sr"]
    out["ty_le_o_lai"] = out["o_lai"] * 100 / out["so_sr"]
    return out.sort_values("thu_tu")


# ----------------------------------------------------------------------- hiệu suất nhân sự (cả hai loại SR)
def hieu_suat_nhan_su(bd: pd.DataFrame, cd: pd.DataFrame) -> pd.DataFrame:
    """Một dòng mỗi CSKH: tải việc (SR bị động + chủ động), tồn, quá hạn, phản hồi, không liên lạc được."""
    a = theo_nhan_su_bd(bd).rename(columns=lambda c: c if c in ("nhan_su", "phong") else "bd_" + c)
    b = theo_nhan_su_cd(cd).rename(columns=lambda c: c if c in ("nhan_su", "phong") else "cd_" + c)
    if a.empty and b.empty:
        return pd.DataFrame()
    m = pd.merge(a, b, on="nhan_su", how="outer", suffixes=("", "_cd"))
    m["phong"] = m["phong"].fillna(m.get("phong_cd"))
    for c in ("bd_phan_cong", "bd_ton", "bd_qua_han", "cd_phan_cong", "cd_ton", "cd_qua_han"):
        m[c] = m[c].fillna(0)
    m["tong_tai"] = m["bd_phan_cong"] + m["cd_phan_cong"]
    m["tong_ton"] = m["bd_ton"] + m["cd_ton"]
    m["tong_qua_han"] = m["bd_qua_han"] + m["cd_qua_han"]
    m["ty_le_qua_han"] = m["tong_qua_han"] * 100 / m["tong_tai"].replace(0, np.nan)
    m["ty_le_ton"] = m["tong_ton"] * 100 / m["tong_tai"].replace(0, np.nan)
    return m.drop(columns=[c for c in m.columns if c.endswith("_cd") and c.startswith("phong")]).sort_values("tong_tai", ascending=False)


# ----------------------------------------------------------------------- rời mạng, công nợ
def roi_mang_moi_nhat(ngay: date | None = None) -> pd.DataFrame:
    df = roi_mang()
    if df.empty:
        return df
    if ngay is not None:
        df = df[df["ngay_chot"] <= pd.Timestamp(ngay)]
    if df.empty:
        return df
    return df[df["ngay_chot"] == df["ngay_chot"].max()].copy()


def cong_no_tai_ngay(ky_no: str, so_ngay: int, ten: str = "DNG", cap: str = "quan") -> tuple[float | None, float | None]:
    """(tỷ lệ theo DT, theo bill) của một đơn vị tại ngày thu thứ `so_ngay` của kỳ nợ (cùng ngày thứ mấy để so với kỳ trước)."""
    df = cong_no_ngay()
    if df.empty:
        return None, None
    d = df[(df["ky_no"] == ky_no) & (df["cap"] == cap) & (df["ten"] == ten) & (df["so_ngay"] <= so_ngay)]
    if d.empty:
        return None, None
    r = d.sort_values("so_ngay").iloc[-1]
    return float(r["ty_le_dt"]) if pd.notna(r["ty_le_dt"]) else None, float(r["ty_le_bill"]) if pd.notna(r["ty_le_bill"]) else None


# ----------------------------------------------------------------------- điểm nóng theo phường / xã
def diem_nong_phuong(bd: pd.DataFrame, cd: pd.DataFrame) -> pd.DataFrame:
    """Ghép ba nguồn theo phường / xã: SR bị động (trên 1.000 KH), tỷ lệ rời mạng, tỷ lệ chưa thu công nợ, SR chủ động tồn.

    Tên phường ở file rời mạng / công nợ không dấu ("Phuong Thanh Khe"), ở file SR có dấu ("Phường Thanh Khê") nên ghép theo tên bỏ dấu.
    """
    rm = roi_mang_moi_nhat()
    rm = rm[rm["cap"] == "quan"] if not rm.empty else rm
    if rm.empty:
        return pd.DataFrame()
    rm = rm[rm["ten"].str.lower().str.startswith(("phuong", "xa"))].copy()
    rm["khoa"] = rm["ten"].map(bo_dau)
    ct = cong_no_chot()
    cn = pd.DataFrame()
    if not ct.empty:
        ct = ct[(ct["cap"] == "quan") & (ct["ngay_chot"] == ct["ngay_chot"].max())].copy()
        ct["khoa"] = ct["ten"].map(bo_dau)
        cn = ct.groupby("khoa").agg(so_hd=("so_hd", "sum"), tt_con_no=("tt_con_no", "sum"), tong_tien=("tong_tien", "sum"),
                                    hd_con_no=("hd_con_no", "sum")).reset_index()
        cn["ty_le_chua_thu"] = cn["tt_con_no"] * 100 / cn["tong_tien"].replace(0, np.nan)
        cn["ty_le_chua_thu_bill"] = cn["hd_con_no"] * 100 / cn["so_hd"].replace(0, np.nan)
    a = bd.assign(khoa=bd["quan"].map(bo_dau)).groupby("khoa").agg(sr_bd=("ma_sr", "size"), bd_ton=("ton", "sum"), bd_qua_han=("qua_han_cd", "sum"),
                                                                    khieu_nai=("loai_yc", lambda s: int((s == "Khiếu nại, phàn nàn").sum()))).reset_index() if not bd.empty else pd.DataFrame(columns=["khoa"])
    b = cd.assign(khoa=cd["quan"].map(bo_dau)).groupby("khoa").agg(sr_cd=("ma_sr", "size"), cd_ton=("ton", "sum")).reset_index() if not cd.empty else pd.DataFrame(columns=["khoa"])
    m = rm[["khoa", "ten", "kh_active", "gross_pttb", "kh_roi_mang", "ty_le_roi_active", "ty_le_roi_gross", "net_pttb"]]
    for t in (a, b, cn):
        if not t.empty:
            m = m.merge(t, on="khoa", how="left")
    m = m[m["kh_active"].fillna(0) >= 500].copy()                                      # bỏ xã / phường quá nhỏ làm nhiễu tỷ lệ
    if "sr_bd" in m:
        m["sr_bd_1000"] = m["sr_bd"].fillna(0) * 1000 / m["kh_active"]
    if "sr_cd" in m:
        m["sr_cd_1000"] = m["sr_cd"].fillna(0) * 1000 / m["kh_active"]
    chi = [c for c in ("sr_bd_1000", "ty_le_roi_active", "ty_le_chua_thu") if c in m]
    for c in chi:
        m["hang_" + c] = m[c].rank(ascending=False, method="min")
    m["so_chi_so_top3"] = sum((m["hang_" + c] <= 3).astype(int) for c in chi) if chi else 0
    return m.sort_values(["so_chi_so_top3", "ty_le_roi_active"], ascending=False)
