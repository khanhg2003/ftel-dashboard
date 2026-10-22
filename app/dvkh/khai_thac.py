"""Khai thác sâu dữ liệu DVKH: những góc nhìn mà bảng BC trong file chưa có (dòng chảy giữ chân khách, phí và miễn giảm, gói dịch vụ,
nguồn tạo SR, tuổi SR tồn, tải việc trên số khách phụ trách, nhóm theo ngày đổ về).

Mỗi hàm nhận DataFrame đã qua `so_lieu.sr_bi_dong()` / `sr_chu_dong()` và trả bảng nhỏ đã tính sẵn để trang chỉ việc vẽ.
Nhóm nào dưới `MAU_TOI_THIEU` SR thì bỏ qua thay vì hiện tỷ lệ dễ gây hiểu nhầm.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MAU_TOI_THIEU = 30
MAU_NHAN_SU_TOI_THIEU = 15                  # số SR thanh lý tối thiểu của một CSKH để xếp hạng tỷ lệ giữ chân
BAC_TUOI_TON = (0, 24, 72, 168, 10 ** 6)
NHAN_TUOI_TON = ("Dưới 1 ngày", "1 đến 3 ngày", "3 đến 7 ngày", "Trên 7 ngày")
BAC_XU_LY = (0, 1, 4, 24, 72, 10 ** 6)
NHAN_XU_LY = ("Dưới 1 giờ", "1 đến 4 giờ", "4 đến 24 giờ", "1 đến 3 ngày", "Trên 3 ngày")
NHOM_TT_CD = {"Đã hoàn tất": "Đã xử lý xong", "Đã xử lý": "Đã xử lý xong", "Đóng tự động bởi hệ thống": "Hệ thống tự đóng",
              "Đang xử lý": "Đang xử lý", "Chưa xử lý": "Chưa xử lý / chưa phân công", "Chưa phân công": "Chưa xử lý / chưa phân công",
              "Xử lý không thành công": "Không thành công"}
THU_TU_TT_CD = ("Đã xử lý xong", "Hệ thống tự đóng", "Đang xử lý", "Chưa xử lý / chưa phân công", "Không thành công")


# ------------------------------------------------------------------ giữ chân khách
def ket_qua_tu_van_nhom(bd: pd.DataFrame) -> pd.Series:
    """Quy kết quả tư vấn về bốn nhóm. "Không đồng ý" cũng chứa chữ "đồng ý" nên phải xét câu bắt đầu (đã có test chặn)."""
    tv = bd["ket_qua_tu_van"].fillna("")
    return pd.Series(np.select([tv.str.startswith("Khách hàng đồng ý"), tv.str.contains("đang suy nghĩ"), tv.str.contains("không đồng ý")],
                                ["Đồng ý ở lại", "Đang suy nghĩ", "Không đồng ý"], "Chưa có kết quả tư vấn"), index=bd.index)


def dong_giu_chan(bd: pd.DataFrame) -> dict | None:
    """Dòng chảy của khách yêu cầu thanh lý: yêu cầu → kết quả tư vấn → hợp đồng hiện nay còn dùng hay đã chấm dứt (cho biểu đồ Sankey)."""
    tl = bd[bd["loai_yc"] == "Thanh lý"]
    if len(tl) < MAU_TOI_THIEU:
        return None
    nhom = ket_qua_tu_van_nhom(tl)
    cuoi = np.where(tl["roi_mang_sau"], "Hợp đồng đã chấm dứt", "Vẫn đang dùng dịch vụ")
    nhan = ["Yêu cầu thanh lý", "Đồng ý ở lại", "Đang suy nghĩ", "Không đồng ý", "Chưa có kết quả tư vấn", "Hợp đồng đã chấm dứt", "Vẫn đang dùng dịch vụ"]
    chi_so = {t: i for i, t in enumerate(nhan)}
    nguon, dich, gia_tri = [], [], []
    for t, so in nhom.value_counts().items():
        nguon.append(0), dich.append(chi_so[t]), gia_tri.append(int(so))
    bang = pd.crosstab(nhom, pd.Series(cuoi, index=tl.index))
    for t in bang.index:
        for c in bang.columns:
            if bang.loc[t, c]:
                nguon.append(chi_so[t]), dich.append(chi_so[c]), gia_tri.append(int(bang.loc[t, c]))
    return {"nhan": nhan, "nguon": nguon, "dich": dich, "gia_tri": gia_tri, "tong": len(tl), "bang": bang}


def tom_tat_giu_chan(g: dict) -> dict:
    """Các con số rút từ `dong_giu_chan` để trang và nhận định dùng chung một cách tính."""
    b = g["bang"]

    def hang(nhom: str) -> int:
        return int(b.loc[nhom].sum()) if nhom in b.index else 0

    def o(nhom: str, cot: str) -> int:
        return int(b.loc[nhom, cot]) if nhom in b.index and cot in b.columns else 0

    chua_tv = hang("Chưa có kết quả tư vấn")
    return {"tong": g["tong"], "co_tu_van": g["tong"] - chua_tv, "o_lai": hang("Đồng ý ở lại"), "khong_dong_y": hang("Không đồng ý"),
            "chet_trong_khong_dong_y": o("Không đồng ý", "Hợp đồng đã chấm dứt"), "dang_nghi": hang("Đang suy nghĩ"),
            "con_cuu_duoc": o("Đang suy nghĩ", "Vẫn đang dùng dịch vụ"), "chet": int(b["Hợp đồng đã chấm dứt"].sum()) if "Hợp đồng đã chấm dứt" in b.columns else 0}


def giu_chan_theo_nguoi(bd: pd.DataFrame) -> pd.DataFrame:
    """Mỗi CSKH: số SR thanh lý đã tư vấn, bao nhiêu khách đồng ý ở lại. Chỉ xếp hạng người có đủ mẫu."""
    tl = bd[(bd["loai_yc"] == "Thanh lý") & bd["ket_qua_tu_van"].notna() & bd["nguoi_xu_ly"].notna() & bd["la_dvkh"]]
    if tl.empty:
        return pd.DataFrame(columns=["nhan_su", "so_sr", "o_lai", "ty_le_o_lai"])
    g = tl.groupby("nguoi_xu_ly").agg(so_sr=("ma_sr", "size"), o_lai=("o_lai", "sum")).reset_index().rename(columns={"nguoi_xu_ly": "nhan_su"})
    g = g[g["so_sr"] >= MAU_NHAN_SU_TOI_THIEU].copy()
    g["ty_le_o_lai"] = g["o_lai"] * 100 / g["so_sr"]
    return g.sort_values("ty_le_o_lai", ascending=False)


# ------------------------------------------------------------------ tiền: phí và miễn giảm
def phi_mien_giam(bd: pd.DataFrame) -> pd.DataFrame:
    """Mỗi loại yêu cầu có thu phí: số SR, tổng phí, tổng miễn giảm, tỷ lệ miễn giảm. Miễn giảm có thể vượt phí của chính nó (khôi phục dịch vụ)."""
    d = bd[(bd["phi"].fillna(0) > 0) | (bd["mien_giam_phi"].fillna(0) > 0)]
    if d.empty:
        return pd.DataFrame(columns=["loai_yc", "so_sr", "phi", "mien_giam", "thu_thuc", "ty_le_mien_giam"])
    g = d.groupby("loai_yc").agg(so_sr=("ma_sr", "size"), phi=("phi", "sum"), mien_giam=("mien_giam_phi", "sum")).reset_index()
    g["thu_thuc"] = g["phi"] - g["mien_giam"]
    g["ty_le_mien_giam"] = g["mien_giam"] * 100 / g["phi"].replace(0, np.nan)
    return g.sort_values("phi", ascending=False)


def duyet_de_xuat(bd: pd.DataFrame) -> pd.DataFrame:
    """Đề xuất cần duyệt (miễn giảm, đổi câu lệnh giá, khoá rời mạng) × trạng thái duyệt. Chuỗi gốc dạng "Miễn giảm - Đã xử lý"."""
    s = bd["duyet_de_xuat"].dropna() if "duyet_de_xuat" in bd else pd.Series(dtype=object)
    if s.empty:
        return pd.DataFrame()
    t = s.str.rsplit(" - ", n=1, expand=True)
    if t.shape[1] < 2:
        return pd.DataFrame()
    t.columns = ["loai", "trang_thai"]
    return pd.crosstab(t["loai"].str.strip(), t["trang_thai"].str.strip())


# ------------------------------------------------------------------ khách và dịch vụ
def theo_goi(bd: pd.DataFrame, cot: str = "goi_net_nhom") -> pd.DataFrame:
    """Tỷ lệ SR thanh lý và khiếu nại theo gói dịch vụ hiện tại của khách (trên tổng SR của gói đó)."""
    d = bd[bd[cot].notna()] if cot in bd else bd.iloc[0:0]
    if d.empty:
        return pd.DataFrame(columns=[cot, "so_sr", "thanh_ly", "khieu_nai", "ty_le_thanh_ly", "ty_le_khieu_nai"])
    g = d.groupby(cot).agg(so_sr=("ma_sr", "size"), thanh_ly=("loai_yc", lambda s: int((s == "Thanh lý").sum())),
                           khieu_nai=("loai_yc", lambda s: int((s == "Khiếu nại, phàn nàn").sum()))).reset_index()
    g = g[g["so_sr"] >= MAU_TOI_THIEU].copy()
    g["ty_le_thanh_ly"] = g["thanh_ly"] * 100 / g["so_sr"]
    g["ty_le_khieu_nai"] = g["khieu_nai"] * 100 / g["so_sr"]
    return g.sort_values("so_sr", ascending=False)


def theo_nguon_tao(bd: pd.DataFrame) -> pd.DataFrame:
    """Ai tạo SR bị động (khách tự tạo, DVKH, kinh doanh, triển khai, hỗ trợ khách hàng, bot) và loại việc họ tạo."""
    if "nguon_tao_nhom" not in bd or bd["nguon_tao_nhom"].eq("Chưa rõ").all():
        return pd.DataFrame()
    g = bd.groupby("nguon_tao_nhom").agg(so_sr=("ma_sr", "size"), thanh_ly=("loai_yc", lambda s: int((s == "Thanh lý").sum())),
                                         khieu_nai=("loai_yc", lambda s: int((s == "Khiếu nại, phàn nàn").sum())),
                                         ton=("ton", "sum")).reset_index()
    g["ty_trong"] = g["so_sr"] * 100 / g["so_sr"].sum()
    g["ty_le_ton"] = g["ton"] * 100 / g["so_sr"]
    return g.sort_values("so_sr", ascending=False)


# ------------------------------------------------------------------ tuổi tồn, thời gian xử lý
def tuoi_ton(df: pd.DataFrame, cot_tg: str, nhom: str | None = None) -> pd.DataFrame:
    """SR còn tồn chia theo tuổi tính từ lúc tạo / đổ về tới SR mới nhất trong file. `nhom` = cột để tách thành nhiều dòng."""
    t = df[df["ton"]]
    if t.empty:
        return pd.DataFrame()
    moc = df[cot_tg].max()
    tuoi = pd.cut((moc - t[cot_tg]).dt.total_seconds() / 3600, list(BAC_TUOI_TON), labels=list(NHAN_TUOI_TON), right=False)
    if nhom is None:
        return tuoi.value_counts().reindex(NHAN_TUOI_TON, fill_value=0).rename_axis("tuoi").reset_index(name="so")
    return pd.crosstab(t[nhom].fillna("(Chưa ghi)"), tuoi).reindex(columns=list(NHAN_TUOI_TON), fill_value=0)


def phan_bo_xu_ly(bd: pd.DataFrame, nhom: str = "loai_yc") -> pd.DataFrame:
    """Thời gian đóng SR (đã xử lý xong) chia theo bậc, mỗi dòng một loại yêu cầu, giá trị là % trong loại đó."""
    d = bd[bd["xu_ly_gio"].notna()]
    if d.empty:
        return pd.DataFrame()
    bac = pd.cut(d["xu_ly_gio"], list(BAC_XU_LY), labels=list(NHAN_XU_LY), right=False)
    ct = pd.crosstab(d[nhom], bac).reindex(columns=list(NHAN_XU_LY), fill_value=0)
    ct = ct[ct.sum(axis=1) >= MAU_TOI_THIEU]
    return ct.div(ct.sum(axis=1), axis=0) * 100


# ------------------------------------------------------------------ nhân sự
def gan_so_khach(hs: pd.DataFrame, so_kh: pd.DataFrame) -> pd.DataFrame:
    """Thêm số khách phụ trách và SR trên 1.000 khách vào bảng hiệu suất (khớp theo tên tài khoản viết thường)."""
    hs = hs.copy()
    if so_kh.empty or hs.empty:
        hs["so_kh"], hs["sr_1000kh"] = np.nan, np.nan
        return hs
    m = so_kh.assign(khoa=so_kh["acc"].str.lower()).drop_duplicates("khoa").set_index("khoa")["so_kh"]
    hs["so_kh"] = hs["nhan_su"].str.lower().map(m)
    hs["sr_1000kh"] = hs["tong_tai"] * 1000 / hs["so_kh"]
    return hs


def cho_nao_tot_xau(hs: pd.DataFrame, tai: str = "tong_tai", qua_han: str = "ty_le_qua_han", toi_thieu: int = 30) -> pd.DataFrame:
    """Gắn nhãn dễ hiểu: nhiều việc hơn trung vị và quá hạn cao = "Cần hỗ trợ"; ít việc mà quá hạn cao = "Cần nhắc"; nhiều việc mà quá hạn thấp = "Làm tốt".

    Ngưỡng theo trung vị tải và phân vị 75 / 25 của % quá hạn, chỉ xét người từ `toi_thieu` SR trở lên; còn lại để trống."""
    hs = hs.copy()
    hs["nhan"] = ""
    ok = hs[tai].fillna(0) >= toi_thieu
    if ok.sum() < 8:
        return hs
    t50, q25, q75 = hs.loc[ok, tai].median(), hs.loc[ok, qua_han].quantile(.25), hs.loc[ok, qua_han].quantile(.75)
    hs.loc[ok & (hs[tai] >= t50) & (hs[qua_han] >= q75), "nhan"] = "Cần hỗ trợ"
    hs.loc[ok & (hs[tai] < t50) & (hs[qua_han] >= q75), "nhan"] = "Cần nhắc"
    hs.loc[ok & (hs[tai] >= t50) & (hs[qua_han] <= q25), "nhan"] = "Làm tốt"
    return hs


# ------------------------------------------------------------------ SR chủ động theo ngày đổ về và chương trình
def tinh_trang_nhom(cd: pd.DataFrame) -> pd.Series:
    return cd["tinh_trang"].map(NHOM_TT_CD).fillna("Chưa xử lý / chưa phân công")


def theo_ngay_do_va_tinh_trang(cd: pd.DataFrame) -> pd.DataFrame:
    """Mỗi ngày đổ về: bao nhiêu SR đã xong, tự đóng, đang xử lý, chưa xử lý. Ngày càng cũ mà còn tồn nhiều là việc bị bỏ rơi."""
    if cd.empty:
        return pd.DataFrame()
    return pd.crosstab(cd["ngay_do"], tinh_trang_nhom(cd)).reindex(columns=list(THU_TU_TT_CD), fill_value=0)


def theo_chuong_trinh_va_tinh_trang(cd: pd.DataFrame, top: int = 10) -> pd.DataFrame:
    if cd.empty:
        return pd.DataFrame()
    ct = pd.crosstab(cd["chuong_trinh"].str.strip(), tinh_trang_nhom(cd)).reindex(columns=list(THU_TU_TT_CD), fill_value=0)
    return ct.loc[ct.sum(axis=1).sort_values(ascending=False).head(top).index]


# ------------------------------------------------------------------ phường / xã
CHI_SO_PHUONG = (("sr_bd_1000", "SR bị động<br>/ 1.000 KH"), ("sr_cd_1000", "SR chủ động<br>/ 1.000 KH"),
                 ("ty_le_roi_active", "% rời mạng"), ("ty_le_chua_thu", "% chưa<br>thu nợ"))


def ma_tran_phuong(hot: pd.DataFrame) -> tuple[list[str], list[str], np.ndarray, np.ndarray]:
    """Ma trận phường × chỉ số cho bản đồ nhiệt: màu theo vị trí 0 (tốt nhất) đến 1 (xấu nhất) trong từng chỉ số, chữ là số thật."""
    cot = [(c, t) for c, t in CHI_SO_PHUONG if c in hot and hot[c].notna().any()]
    if hot.empty or not cot:
        return [], [], np.empty((0, 0)), np.empty((0, 0))
    raw = hot[[c for c, _ in cot]].to_numpy(dtype=float)
    lo, hi = np.nanmin(raw, axis=0), np.nanmax(raw, axis=0)
    chuan = (raw - lo) / np.where(hi - lo == 0, 1, hi - lo)
    from app.dvkh.so_lieu import ten_phuong
    return hot["ten"].map(ten_phuong).tolist(), [t for _, t in cot], chuan, raw
