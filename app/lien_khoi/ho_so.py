"""Hồ sơ MỘT hợp đồng: gom mọi thứ ba khối biết về nó (nhánh thi-lien-khoi). Không có tên khách hàng.

`ho_so(so_hd)` trả về từ điển thuần (không có thành phần giao diện) để trang dựng và để kiểm thử:
kd (thuộc tính thương mại + dịch vụ kèm), kt (sự kiện Kỹ thuật kèm thuộc tính), sr_bd / sr_cd (SR của DVKH), viec (việc các luật đang giao cho hợp đồng này),
nguoi (sale / DVKH / KTV phụ trách), co (cờ trạng thái) và dong_thoi_gian.
"""
from __future__ import annotations

import json

import pandas as pd

from app.lien_khoi import luat, nguon
from app.lien_khoi import su_kien as sk
from app.lien_khoi.su_kien import chuan_hd


def _loc(df: pd.DataFrame, ma: str) -> pd.DataFrame:
    return df[chuan_hd(df["so_hd"]) == ma] if len(df) else df


def _so(v) -> float | None:
    x = pd.to_numeric(pd.Series([v]), errors="coerce").iloc[0]
    return None if pd.isna(x) else float(x)


def _dong(v) -> float | None:
    """Số tiền trong file bán hàng lúc ghi bằng nghìn đồng (145), lúc bằng đồng (109091): dưới 5.000 thì coi là nghìn đồng."""
    x = _so(v)
    return None if not x else (x * 1000 if x < 5000 else x)


def _chu(v) -> str:
    return "" if v is None or (isinstance(v, float) and v != v) or v is pd.NaT else str(v).strip()


def thuoc_tinh(v) -> dict:
    """Cột `thuoc_tinh` của sự kiện Kỹ thuật (JSON) -> từ điển; rỗng hoặc hỏng thì {}."""
    try:
        d = json.loads(v) if isinstance(v, str) and v.strip() else {}
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def _kd(ma: str) -> dict:
    k = _loc(nguon.kd(), ma)
    if k.empty:
        return {}
    r = k.iloc[0]
    d = {c: r[c] for c in k.columns if c != "so_hd"}
    d.update(cuoc_thang=_dong(d.get("cuoc_thang")), tien_hoa_mang=_dong(d.get("tien_hoa_mang")), so_tien_tra_truoc=_dong(d.get("so_tien_tra_truoc")))
    d["dich_vu"] = [{"nhom": x["nhom"], "ten": _chu(x["ten"]), "so_luong": _chu(x["so_luong"]), "don_gia": _dong(x["don_gia"]),
                     "vvip": _chu(x["vvip"]) == "1"} for _, x in _loc(nguon.dich_vu_kem(), ma).iterrows()]
    return d


def _nguoi(ma: str, kd: dict, bd: pd.DataFrame, cd: pd.DataFrame, kt: pd.DataFrame) -> dict:
    return {"sale": _chu(kd.get("sale")), "dvkh": luat.nguoi_dvkh(bd, cd).get(ma, ""), "ktv": luat.nguoi_kt(kt).get(ma, "")}


def ho_so(so_hd: str) -> dict | None:
    """None nếu không khối nào có hợp đồng này."""
    ma = str(so_hd or "").strip().upper()
    if not ma:
        return None
    kd = _kd(ma)
    bd, cd, kt = _loc(nguon.sr_bi_dong(), ma), _loc(nguon.sr_chu_dong(), ma), _loc(nguon.kt(), ma)
    if not kd and bd.empty and cd.empty and kt.empty:
        return None
    viec = luat.danh_sach_viec()
    viec = viec[viec["so_hd"] == ma].reset_index(drop=True)
    kt = kt.sort_values("thoi_diem", ascending=False).reset_index(drop=True)
    kt["tt"] = kt["thuoc_tinh"].map(thuoc_tinh) if len(kt) else pd.Series(dtype=object)
    ds = sk.danh_sach_dvkh()
    online, tao = kd.get("ngay_online"), kd.get("ngay_tao")
    ngay_tc = nguon.ngay_tham_chieu() or pd.Timestamp.today().normalize()
    co = {"da_online": bool(pd.notna(online)) if online is not None else None,
          "no_cuoc": bool(len(ds) and ((chuan_hd(ds["so_hd"]) == ma) & (ds["loai"] == "no_cuoc")).any()),
          "co_y_roi": bool((viec["luat"] == "co_y_roi").any()) if len(viec) else False,
          "cho_ngay": int((ngay_tc - pd.Timestamp(tao).normalize()).days) if (online is not None and pd.isna(online) and pd.notna(tao)) else None,
          "tham_nien_thang": int((ngay_tc - pd.Timestamp(online).normalize()).days // 30) if (online is not None and pd.notna(online)) else None}
    muc = "Cao" if (len(viec) and (viec["muc"] == luat.CAO).any()) else ("Trung bình" if len(viec) else "Ổn")
    return {"ma": ma, "kd": kd, "kt": kt, "sr_bd": bd.sort_values("tg_yc", ascending=False).reset_index(drop=True) if len(bd) else bd,
            "sr_cd": cd.sort_values("tg_do", ascending=False).reset_index(drop=True) if len(cd) else cd, "viec": viec,
            "nguoi": _nguoi(ma, kd, bd, cd, kt), "co": co, "muc": muc, "dong_thoi_gian": sk.dong_thoi_gian(ma)}


def hop_dong_goi_y(n: int = 8) -> list[str]:
    """Vài hợp đồng đáng xem (việc mức Cao trước, mỗi hợp đồng một lần) để bấm thử khi chưa gõ mã."""
    v = luat.danh_sach_viec()
    if v.empty:
        return []
    moi_luat = [v[(v["luat"] == k) & (v["muc"] == luat.CAO)].head(2)["so_hd"].tolist() for k in luat.TEN_LUAT]          # mỗi luật vài hợp đồng tiêu biểu
    return list(dict.fromkeys(x for nhom in zip(*[m + [None] * (2 - len(m)) for m in moi_luat]) for x in nhom if x))[:n]
