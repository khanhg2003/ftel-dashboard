"""Đo hiệu quả giao việc liên khối cho người quản lý (nhánh thi-lien-khoi): hàm thuần trên bảng phần việc của `theo_doi.danh_sach_day_du()`.

Cách tính (ghi rõ trên giao diện):
- Bỏ phần việc "hết dấu hiệu" (luật tự đóng, không phải lỗi của người nhận).
- "Đã tới hạn" = đã xong, không làm được, hoặc còn mở mà quá hạn. Việc còn trong hạn chưa tính vì chưa biết kết quả.
- "Xong đúng hạn" = đã xong và giờ cập nhật không muộn hơn hạn. Tỷ lệ xong đúng hạn = xong đúng hạn / đã tới hạn. Không làm được tính là CHƯA đạt.
- Thời gian xử lý = từ lúc giao tới lúc báo xong (chỉ việc đã xong). Phản hồi = từ lúc giao tới lần đầu người nhận làm gì đó với phần việc.
Nhận định do LUẬT cố định sinh ra (không dùng AI). Không có tên khách hàng.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from app.lien_khoi.theo_doi import MO, VAI_TRO

PHAN_HOI_GIO = 4                    # coi là "phản hồi nhanh" nếu người nhận làm gì đó trong N giờ đầu
TOI_THIEU_VIEC = 4                  # dưới ngần này việc đã tới hạn thì không xếp hạng người (ít dữ liệu)
CHENH_KHOI = 10                     # chênh từ N điểm % giữa hai khối mới nêu trong nhận định
LECH_GIO_VN = pd.Timedelta(hours=7)
COT_TONG_HOP = ["nhom", "giao", "xong", "dung_han", "den_han", "ty_le", "gio_xu_ly", "qua_han_mo", "khong", "da_bao_ql"]


def chuan_bi(d: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """Thêm các cột đo (xong, đúng hạn, quá hạn đang mở, giờ xử lý, giờ phản hồi) và bỏ việc hết dấu hiệu."""
    if d.empty:
        return d
    d = d[d["trang_thai"] != "tu_het"].copy()
    for c in ("tao_luc", "han_luc", "cap_nhat_luc", "phan_hoi_luc", "bao_quan_ly_luc"):
        d[c] = pd.to_datetime(d[c]) if c in d.columns else pd.NaT
    n = pd.Timestamp(now)
    d["xong"] = d["trang_thai"] == "da_xong"
    d["khong"] = d["trang_thai"] == "khong_lam_duoc"
    d["qua_han_mo"] = d["trang_thai"].isin(MO) & (d["han_luc"] < n)
    d["den_han"] = d["xong"] | d["khong"] | d["qua_han_mo"]
    d["dung_han"] = d["xong"] & (d["cap_nhat_luc"] <= d["han_luc"])
    d["gio_xu_ly"] = ((d["cap_nhat_luc"] - d["tao_luc"]).dt.total_seconds() / 3600).where(d["xong"])
    d["gio_phan_hoi"] = (d["phan_hoi_luc"] - d["tao_luc"]).dt.total_seconds() / 3600
    return d


def _v(x: float, n: int = 1) -> str:
    """Số kiểu Việt Nam: dấu chấm hàng nghìn, dấu phẩy thập phân (1.238; 12,5)."""
    return f"{x:,.{n}f}".replace(",", "\0").replace(".", ",").replace("\0", ".")


def _ty_le(dung, den) -> float | None:
    return round(100 * dung / den, 1) if den else None


def so_do(d: pd.DataFrame) -> dict:
    """Các số đầu trang của `chuan_bi(...)`."""
    if d.empty:
        return {"giao": 0, "xong": 0, "dung_han": 0, "den_han": 0, "ty_le": None, "gio_xu_ly": None, "gio_xu_ly_tb": None, "phan_hoi": None,
                "phan_hoi_nhanh": None, "qua_han_mo": 0, "khong": 0, "da_bao_ql": 0, "chua_phan_hoi": 0, "mo_phong": 0}
    ph = d["gio_phan_hoi"].dropna()
    mo = d["trang_thai"].isin(MO)
    return {"giao": int(len(d)), "xong": int(d["xong"].sum()), "dung_han": int(d["dung_han"].sum()), "den_han": int(d["den_han"].sum()),
            "ty_le": _ty_le(int(d["dung_han"].sum()), int(d["den_han"].sum())),
            "gio_xu_ly": round(float(d["gio_xu_ly"].median()), 1) if d["gio_xu_ly"].notna().any() else None,
            "gio_xu_ly_tb": round(float(d["gio_xu_ly"].mean()), 1) if d["gio_xu_ly"].notna().any() else None,
            "phan_hoi": round(float(ph.median()), 1) if len(ph) else None,
            "phan_hoi_nhanh": round(100 * float((ph <= PHAN_HOI_GIO).mean()), 1) if len(ph) else None,
            "qua_han_mo": int(d["qua_han_mo"].sum()), "khong": int(d["khong"].sum()), "da_bao_ql": int(d["bao_quan_ly_luc"].notna().sum()),
            "chua_phan_hoi": int((mo & d["phan_hoi_luc"].isna() & d["qua_han_mo"]).sum()),
            "mo_phong": int(d["mo_phong"].fillna(0).astype(int).sum()) if "mo_phong" in d.columns else 0}


def tong_hop(d: pd.DataFrame, theo: str) -> pd.DataFrame:
    """Bảng theo `theo` ("vai_tro", "ten_luat" hoặc "nguoi"): số việc, xong, đúng hạn, tỷ lệ, giờ xử lý trung vị, quá hạn đang mở, không làm được, đã báo quản lý.
    Nhóm có dưới `TOI_THIEU_VIEC` việc đã tới hạn thì không có tỷ lệ (ít dữ liệu). Xếp tỷ lệ thấp nhất lên đầu."""
    if d.empty:
        return pd.DataFrame(columns=COT_TONG_HOP)
    g = d.groupby(theo)
    out = pd.DataFrame({"giao": g.size(), "xong": g["xong"].sum(), "dung_han": g["dung_han"].sum(), "den_han": g["den_han"].sum(),
                        "gio_xu_ly": g["gio_xu_ly"].median().round(1), "qua_han_mo": g["qua_han_mo"].sum(), "khong": g["khong"].sum(),
                        "da_bao_ql": g["bao_quan_ly_luc"].apply(lambda s: int(s.notna().sum()))}).reset_index().rename(columns={theo: "nhom"})
    out["ty_le"] = [_ty_le(a, b) if b >= TOI_THIEU_VIEC else None for a, b in zip(out["dung_han"], out["den_han"])]
    if theo == "vai_tro":
        out["nhom"] = out["nhom"].map(lambda x: VAI_TRO.get(x, x))
    out = out.astype({c: int for c in ("xong", "dung_han", "den_han", "qua_han_mo", "khong")})
    return out.sort_values(["ty_le", "qua_han_mo"], ascending=[True, False], na_position="last").reset_index(drop=True)[COT_TONG_HOP]


def xu_huong(d: pd.DataFrame) -> pd.DataFrame:
    """Theo ngày (giờ Việt Nam): việc mới giao, việc hoàn tất trong ngày, tỷ lệ xong đúng hạn của các việc giao ngày đó."""
    if d.empty:
        return pd.DataFrame(columns=["ngay", "giao", "xong", "ty_le"])
    ngay_giao = (d["tao_luc"] + LECH_GIO_VN).dt.normalize()
    ngay_xong = (d.loc[d["xong"], "cap_nhat_luc"] + LECH_GIO_VN).dt.normalize()
    cohort = d.assign(ngay=ngay_giao).groupby("ngay").agg(giao=("xong", "size"), dung=("dung_han", "sum"), den=("den_han", "sum"))
    out = cohort.join(ngay_xong.value_counts().rename("xong")).fillna({"xong": 0}).reset_index()
    out["ty_le"] = [_ty_le(a, b) if b >= TOI_THIEU_VIEC else None for a, b in zip(out["dung"], out["den"])]
    out["xong"] = out["xong"].astype(int)
    return out[["ngay", "giao", "xong", "ty_le"]].sort_values("ngay").reset_index(drop=True)


def nhan_dinh(d: pd.DataFrame) -> list[str]:
    """Vài câu nhận định bằng luật cố định: tổng quan, khối chênh nhau, người nhiều việc quá hạn, luật hay "không làm được", xu hướng, phản hồi chậm."""
    s = so_do(d)
    if not s["giao"]:
        return ["Chưa có phần việc nào trong kỳ này."]
    kq = [f"Trong kỳ có {_v(s['giao'], 0)} phần việc: {_v(s['xong'], 0)} đã xong (trong đó {_v(s['dung_han'], 0)} đúng hạn), {_v(s['khong'], 0)} không làm được, "
          f"{_v(s['qua_han_mo'], 0)} đang quá hạn."]
    if s["ty_le"] is not None:
        kq[0] += f" Tỷ lệ xong đúng hạn {s['ty_le']:.0f}% trên số việc đã tới hạn."
    k = tong_hop(d, "vai_tro").dropna(subset=["ty_le"])
    if len(k) >= 2 and k["ty_le"].max() - k["ty_le"].min() >= CHENH_KHOI:
        kq.append(f"Khối thấp nhất là {k['nhom'].iloc[0]} ({k['ty_le'].iloc[0]:.0f}%), cao nhất là {k['nhom'].iloc[-1]} ({k['ty_le'].iloc[-1]:.0f}%): nên xem lại cách giao việc cho khối thấp.")
    n = tong_hop(d, "nguoi")
    cham = n[n["qua_han_mo"] >= TOI_THIEU_VIEC].sort_values("qua_han_mo", ascending=False).head(3)
    if len(cham):
        kq.append("Nhiều việc quá hạn nhất: " + ", ".join(f"{r['nhom']} ({r['qua_han_mo']} việc)" for _, r in cham.iterrows()) + ". Đội trưởng nên hỏi thăm trước.")
    lu = d.groupby("ten_luat").agg(den=("den_han", "sum"), khong=("khong", "sum"))
    lu = lu[lu["den"] >= 5].assign(ty=lambda x: x["khong"] / x["den"]).sort_values("ty", ascending=False)
    if len(lu) and lu["ty"].iloc[0] >= 0.1:
        ly = d.loc[(d["ten_luat"] == lu.index[0]) & d["khong"] & d["ghi_chu"].notna(), "ghi_chu"].value_counts()
        kq.append(f"Luật \"{lu.index[0]}\" hay không làm được nhất ({lu['ty'].iloc[0] * 100:.0f}% số việc đã tới hạn)" + (f", lý do thường gặp: {ly.index[0].lower()}." if len(ly) else "."))
    xh = xu_huong(d).dropna(subset=["ty_le"])
    if len(xh) >= 6:
        nua = len(xh) // 2
        dau, sau = xh["ty_le"].iloc[:nua].mean(), xh["ty_le"].iloc[nua:].mean()
        if abs(sau - dau) >= 5:
            kq.append(f"Nửa sau của kỳ {'tốt hơn' if sau > dau else 'kém hơn'} nửa đầu {abs(sau - dau):.0f} điểm % về tỷ lệ xong đúng hạn.")
    if s["chua_phan_hoi"]:
        kq.append(f"{s['chua_phan_hoi']} phần việc quá hạn mà người nhận chưa phản hồi lần nào: nên gọi trực tiếp.")
    return kq


def so_voi_moc(s: dict, moc: dict) -> list[str]:
    """So số đo hiện tại với mốc người dùng đã nhập (đo được trước khi dùng hệ thống). Chưa nhập mốc thì trả rỗng."""
    kq = []
    if moc.get("gio_xu_ly") and s.get("gio_xu_ly") is not None:
        d = 100 * (moc["gio_xu_ly"] - s["gio_xu_ly"]) / moc["gio_xu_ly"]
        kq.append(f"Thời gian xử lý trung vị {_v(s['gio_xu_ly'])} giờ so với mốc {_v(moc['gio_xu_ly'])} giờ: {'giảm' if d >= 0 else 'tăng'} {abs(d):.0f}%.")
    if moc.get("ty_le_dung_han") is not None and s.get("ty_le") is not None:
        d = s["ty_le"] - moc["ty_le_dung_han"]
        kq.append(f"Tỷ lệ xong đúng hạn {s['ty_le']:.0f}% so với mốc {moc['ty_le_dung_han']:.0f}%: {'tăng' if d >= 0 else 'giảm'} {abs(d):.0f} điểm %.")
    return kq
