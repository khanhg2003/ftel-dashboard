"""Bảng sự kiện theo mã hợp đồng: nền của hướng điều hành liên khối (nhánh thi-lien-khoi, 14/11/2026).

Mỗi khối đổ sự kiện của mình vào MỘT dạng bảng chung (`COT`), khoá nối là mã hợp đồng. Số liệu lấy qua `nguon.py` (dữ liệu thật hoặc bộ minh hoạ).
Khối Kỹ thuật: `su_kien_kt()` đọc `nguon.kt()`; khi có nguồn thật chỉ cần `nguon.kt()` trả đúng các cột - luật và giao diện không đổi.
Bảng này KHÔNG có tên khách hàng, địa chỉ hay số điện thoại.
"""
from __future__ import annotations

import pandas as pd

from app.bo_nho import nho
from app.lien_khoi import nguon
from app.lien_khoi.doc_kt import TEN_LOAI_KT

KD, DVKH, KT = "KD", "DVKH", "KT"
TEN_KHOI = {KD: "Kinh doanh", DVKH: "Dịch vụ khách hàng", KT: "Kỹ thuật"}
COT = ["so_hd", "nguon", "loai", "thoi_diem", "chi_tiet", "nguoi"]
TEN_LOAI = {"tao_hd": "Tạo hợp đồng", "online": "Online", "huy": "Huỷ hợp đồng", "sr_bi_dong": "SR bị động (khách gọi)",
            "sr_chu_dong": "SR chủ động (DVKH chăm)", "no_cuoc": "Nợ cước", "ych": "Trong danh sách YCH", **TEN_LOAI_KT}


def chuan_hd(s: pd.Series) -> pd.Series:
    """Mã hợp đồng ba khối có thể gõ khác hoa / thường hoặc thừa khoảng trắng: so khớp bằng dạng chuẩn này."""
    return s.fillna("").astype(str).str.strip().str.upper()


def _rong() -> pd.DataFrame:
    return pd.DataFrame(columns=COT)


def hop_dong_kd() -> pd.DataFrame:
    return nguon.kd()


def danh_sach_dvkh() -> pd.DataFrame:
    return nguon.danh_sach_dvkh()


def su_kien_kd() -> pd.DataFrame:
    kd = hop_dong_kd()
    if kd.empty:
        return _rong()
    phan = []
    for loai, cot, chu in (("tao_hd", "ngay_tao", "Tạo hợp đồng, gói "), ("online", "ngay_online", "Online"), ("huy", "ngay_huy", "Huỷ hợp đồng")):
        d = kd[kd[cot].notna()]
        ct = (chu + d["goi"].fillna("")) if loai == "tao_hd" else chu
        phan.append(pd.DataFrame({"so_hd": d["so_hd"], "nguon": KD, "loai": loai, "thoi_diem": d[cot], "chi_tiet": ct, "nguoi": d["sale"]}))
    return pd.concat(phan, ignore_index=True)


def _ghep(*cot) -> pd.Series:
    """Nối các cột chữ bằng " · ", bỏ ô trống."""
    out = pd.DataFrame({i: c.fillna("").astype(str) for i, c in enumerate(cot)})
    return out.apply(lambda r: " · ".join(x for x in r if x), axis=1) if len(out) else pd.Series([], dtype=str)


def su_kien_dvkh() -> pd.DataFrame:
    phan = []
    bd = nguon.sr_bi_dong()
    if not bd.empty:
        phan.append(pd.DataFrame({"so_hd": chuan_hd(bd["so_hd"]), "nguon": DVKH, "loai": "sr_bi_dong", "thoi_diem": bd["tg_yc"],
                                  "chi_tiet": _ghep(bd["loai_yc"], bd["tinh_trang"], bd["ket_qua_tu_van"]), "nguoi": bd["nhan_su_au"].fillna("")}))
    cd = nguon.sr_chu_dong()
    if not cd.empty:
        phan.append(pd.DataFrame({"so_hd": chuan_hd(cd["so_hd"]), "nguon": DVKH, "loai": "sr_chu_dong", "thoi_diem": cd["tg_do"],
                                  "chi_tiet": _ghep(cd["nhom_ct"], cd["chuong_trinh"], cd["tinh_trang"]), "nguoi": cd["nhan_su_au"].fillna("")}))
    ds = danh_sach_dvkh()
    if not ds.empty:
        phan.append(pd.DataFrame({"so_hd": chuan_hd(ds["so_hd"]), "nguon": DVKH, "loai": ds["loai"],
                                  "thoi_diem": pd.to_datetime(ds["ngay_chot"]), "chi_tiet": "Có trong danh sách của file DVKH", "nguoi": ""}))
    return pd.concat(phan, ignore_index=True) if phan else _rong()


def su_kien_kt() -> pd.DataFrame:
    """Sự kiện Kỹ thuật theo `COT`: lấy từ `nguon.kt()` (dữ liệu thật hiện chưa có nguồn nên trả bảng rỗng; bộ minh hoạ thì có)."""
    k = nguon.kt()
    if k.empty:
        return _rong()
    return pd.DataFrame({"so_hd": k["so_hd"], "nguon": KT, "loai": k["loai"], "thoi_diem": pd.to_datetime(k["thoi_diem"]),
                         "chi_tiet": k["chi_tiet"].fillna(""), "nguoi": k["nguoi"].fillna("")})


NGUON = {KD: su_kien_kd, DVKH: su_kien_dvkh, KT: su_kien_kt}


@nho("so_lieu", 60)
def bang_su_kien() -> pd.DataFrame:
    """Sự kiện của mọi khối, xếp theo hợp đồng rồi thời điểm."""
    phan = [f() for f in NGUON.values()]
    phan = [p for p in phan if not p.empty]
    if not phan:
        return _rong()
    ev = pd.concat(phan, ignore_index=True)
    ev["thoi_diem"] = pd.to_datetime(ev["thoi_diem"], errors="coerce")
    ev = ev[ev["so_hd"].ne("") & ev["thoi_diem"].notna()]
    return ev.sort_values(["so_hd", "thoi_diem"], kind="stable").reset_index(drop=True)


def dong_thoi_gian(so_hd: str) -> pd.DataFrame:
    """Toàn bộ sự kiện của một hợp đồng, từ cũ đến mới."""
    ma = str(so_hd or "").strip().upper()
    ev = bang_su_kien()
    return ev[ev["so_hd"] == ma].reset_index(drop=True) if ma and not ev.empty else _rong()


def trang_thai_nguon() -> list[dict]:
    """Mỗi khối: đã có nguồn chưa, bao nhiêu sự kiện / hợp đồng, từ ngày nào đến ngày nào."""
    ev = bang_su_kien()
    out = []
    for khoi, ten in TEN_KHOI.items():
        e = ev[ev["nguon"] == khoi] if not ev.empty else ev
        out.append({"khoi": khoi, "ten": ten, "co_nguon": not e.empty, "so_su_kien": int(len(e)),
                    "so_hd": int(e["so_hd"].nunique()) if not e.empty else 0,
                    "tu": e["thoi_diem"].min() if not e.empty else None, "den": e["thoi_diem"].max() if not e.empty else None})
    return out


def khop_giua_khoi() -> dict:
    """Số hợp đồng xuất hiện ở từng khối và ở cả hai khối: cho thấy dữ liệu đã nối với nhau được tới đâu."""
    ev = bang_su_kien()
    tap = {k: set(ev.loc[ev["nguon"] == k, "so_hd"]) if not ev.empty else set() for k in TEN_KHOI}
    return {"kd": len(tap[KD]), "dvkh": len(tap[DVKH]), "kt": len(tap[KT]), "kd_dvkh": len(tap[KD] & tap[DVKH]),
            "kd_kt": len(tap[KD] & tap[KT]), "dvkh_kt": len(tap[DVKH] & tap[KT]), "ca_ba": len(tap[KD] & tap[DVKH] & tap[KT])}
