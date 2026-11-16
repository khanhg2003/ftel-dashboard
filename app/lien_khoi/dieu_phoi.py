"""Điều phối việc cho một quản lý (nhánh thi-lien-khoi): xem việc trong phạm vi, tìm người theo tên, giao theo mã hợp đồng, chia đều việc hàng chờ, tổng kết.
Dùng chung cho nút trên app (trang Theo dõi) và lệnh nhắn bot Zalo (`zalo_lenh.py`), để hai nơi luôn ra cùng một kết quả. Không có tên khách hàng.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime

import pandas as pd

from app.lien_khoi import theo_doi as td

KHOI_CUA_VAI_TRO = {"sale": "KD", "dvkh": "DVKH", "kt": "KT"}      # phần việc của vai nào thì giao cho người thuộc khối đó


def bo_dau(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").replace("đ", "d").replace("Đ", "D"))
    return re.sub(r"\s+", " ", "".join(c for c in s if unicodedata.category(c) != "Mn")).strip().lower()


def _thuc(d: pd.DataFrame) -> pd.Series:
    return d["mo_phong"].fillna(0) == 0 if "mo_phong" in d.columns else pd.Series(True, index=d.index)


def viec_cua(ma_ql: str, now: datetime | None = None, chi_mo: bool = True) -> pd.DataFrame:
    """Việc THẬT thuộc phạm vi một quản lý (team của họ và các team cấp dưới; giám đốc thấy cả việc chưa có quản lý). `chi_mo`: chỉ việc đang mở."""
    d = td.danh_sach(now)
    if d.empty:
        return d
    ds = td.nguoi_nhan().fillna("")
    pv = td.pham_vi(ma_ql, ds)
    gd = td.giam_doc(ds)
    trong = d["quan_ly"].isin(pv) | ((d["quan_ly"] == "") & (ma_ql == gd))
    d = d[trong & _thuc(d)]
    return d[d["dang_mo"]] if chi_mo else d


def tim_nguoi(chu: str, ma_ql: str) -> tuple[list[dict], str]:
    """Tìm người nhận việc theo mã hoặc tên (không dấu, gõ một phần cũng được) trong team của quản lý. Trả (danh sách khớp, ghi chú):
    đúng một người thì dùng; nhiều người thì hỏi lại; không ai thì báo."""
    ds = td.nguoi_nhan().fillna("")
    pv = td.pham_vi(ma_ql, ds)
    cap = ds[ds["quan_ly"].isin(pv) & (ds["ma"] != ma_ql)]
    q = bo_dau(chu)
    if not q:
        return [], "chua_nhap"
    tu = q.split()
    kq = []
    for r in cap.to_dict("records"):
        ten, ma = bo_dau(r["ten"]), bo_dau(r["ma"])
        if q in (ten, ma, ma.replace("_", " ")):
            return [r], "dung"
        if all(t in ten or t in ma or t in ma.replace("_", " ") for t in tu):
            kq.append(r)
    return kq, ("mot" if len(kq) == 1 else "nhieu" if kq else "khong")


def giao_theo_ma(ma_ql: str, codes: list[str], nguoi: dict, now: datetime | None = None) -> dict:
    """Giao các phần việc của các mã hợp đồng cho `nguoi` (đã chọn đúng một người). Chỉ giao phần việc thuộc đúng khối của người đó (việc Kỹ thuật không giao cho sale).
    Trả {"giao": số phần việc, "ma_giao": [...], "khong_thay": [...], "khac_khoi": [...]}."""
    d = viec_cua(ma_ql, now)
    ma_giao, khong_thay, khac_khoi, ids = [], [], [], []
    for c in codes:
        x = d[d["so_hd"] == c] if len(d) else d
        if x.empty:
            khong_thay.append(c)
            continue
        dung = x[x["vai_tro"].map(KHOI_CUA_VAI_TRO) == nguoi["khoi"]]
        if dung.empty:
            khac_khoi.append(c)
            continue
        ids += [int(i) for i in dung["id"]]
        ma_giao.append(c)
    n = td.giao_viec(ids, nguoi["ma"], ma_ql, now) if ids else 0
    return {"giao": n, "ma_giao": ma_giao, "khong_thay": khong_thay, "khac_khoi": khac_khoi}


def chia_deu(ma_ql: str, now: datetime | None = None) -> dict:
    """Chia đều các việc HÀNG CHỜ (chưa có người phụ trách, chưa giao) trong phạm vi cho nhân viên đúng khối, ưu tiên người đang ít việc nhất; việc mức Cao chia trước.
    Trả {"giao": số phần việc, "theo_nguoi": {tên: số}, "thieu_nguoi": số việc không có nhân viên phù hợp}."""
    d = viec_cua(ma_ql, now)
    if d.empty:
        return {"giao": 0, "theo_nguoi": {}, "thieu_nguoi": 0}
    ds = td.nguoi_nhan().fillna("")
    pv = td.pham_vi(ma_ql, ds)
    nv = ds[ds["quan_ly"].isin(pv) & (ds["vai_tro"] == "nhan_vien")]
    hang_cho = d[(d["trang_thai"] == "moi") & d["nguoi_goc"].fillna("").ne("") & d["giao_cho"].fillna("").eq("")]
    tai = {m: 0 for m in nv["ma"]}                                                 # số việc đang mở của từng nhân viên
    for m in (d["giao_cho"].fillna("").where(d["giao_cho"].fillna("") != "", d["nguoi"])).tolist():
        if m in tai:
            tai[m] += 1
    ten = dict(zip(ds["ma"], ds["ten"]))
    gan: dict[str, list[int]] = {}
    thieu = 0
    ths = hang_cho.assign(_c=(hang_cho["muc"] != "Cao").astype(int)).sort_values(["_c", "so_hd"])
    for r in ths.to_dict("records"):
        ung = [m for m in nv.loc[nv["khoi"] == KHOI_CUA_VAI_TRO.get(r["vai_tro"], ""), "ma"]]
        if not ung:
            thieu += 1
            continue
        m = min(ung, key=lambda x: (tai[x], x))
        tai[m] += 1
        gan.setdefault(m, []).append(int(r["id"]))
    n = 0
    for m, ids in gan.items():
        n += td.giao_viec(ids, m, ma_ql, now)
    return {"giao": n, "theo_nguoi": {ten.get(m, m): len(v) for m, v in sorted(gan.items(), key=lambda kv: -len(kv[1]))}, "thieu_nguoi": thieu}


def tong_ket(ma_ql: str, now: datetime | None = None) -> dict:
    """Số liệu tổng kết cho một quản lý: đang mở, mức Cao, quá hạn, chưa giao, đang làm, xong và không làm được trong 24 giờ qua, theo từng team."""
    now = pd.Timestamp(now or td.bay_gio())
    tat = viec_cua(ma_ql, now, chi_mo=False)
    if tat.empty:
        return {"mo": 0, "cao": 0, "qua_han": 0, "chua_giao": 0, "dang_lam": 0, "xong_24h": 0, "khong_24h": 0, "theo_team": []}
    mo = tat[tat["dang_mo"]]
    gan_day = pd.to_datetime(tat["cap_nhat_luc"], errors="coerce") >= now - pd.Timedelta(hours=24)
    ds = td.nguoi_nhan().fillna("")
    ten = dict(zip(ds["ma"], ds["ten"]))
    team = []
    for ql, x in mo.groupby("quan_ly"):
        team.append({"ten": ten.get(ql, ql or "(chưa có quản lý)"), "mo": len(x), "qua_han": int(x["qua_han"].sum()), "chua_giao": int((x["giao_cho"].fillna("") == "").sum())})
    team.sort(key=lambda t: (-t["qua_han"], -t["mo"]))
    return {"mo": len(mo), "cao": int((mo["muc"] == "Cao").sum()), "qua_han": int(mo["qua_han"].sum()), "chua_giao": int((mo["giao_cho"].fillna("") == "").sum()),
            "dang_lam": int((mo["trang_thai"] == "da_nhan").sum()), "xong_24h": int(((tat["trang_thai"] == "da_xong") & gan_day).sum()),
            "khong_24h": int(((tat["trang_thai"] == "khong_lam_duoc") & gan_day).sum()), "theo_team": team}
