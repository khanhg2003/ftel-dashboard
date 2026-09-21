"""Dự báo số online cuối tháng theo phòng - tính bằng công thức, AI chỉ diễn giải.

Giao diện hiện SONG SONG hai số: `du_bao` và trong ngoặc là `du_bao_nhip`.

1. `du_bao` (số chính) = luỹ kế + (luỹ kế / số ngày đã qua) × số ngày còn lại. Giữ nguyên đà từ đầu
   tháng tới nay, không cộng thêm gì. Dễ kiểm tra bằng tay.
2. `du_bao_nhip` (số trong ngoặc) = như trên nhưng × hệ số nhịp cuối tháng trước: tháng trước tốc độ
   bình quân/ngày của phần cuối tháng chia tốc độ của cùng số ngày đầu tháng (chi nhánh tháng nào
   cũng dồn về cuối tháng). Giới hạn 0,7 - 1,5 để một tháng bất thường không kéo lệch.
3. `du_bao_tuan` (cột "Giữ nhịp 7 ngày") = luỹ kế + bình quân 7 ngày gần nhất đã chốt × số ngày còn
   lại. Cao hơn `du_bao` nghĩa là tuần vừa rồi chạy nhanh hơn đà cả tháng.

Thử lại trên tháng 8/2026 (thật 4.322 online), đứng ở từng ngày 7-30: `du_bao` sai trung bình 6,5%
(giữa tháng thấp hơn thật 8-10%, khít dần về cuối tháng), `du_bao_nhip` sai 1,9% (từ ngày 15 là
1,3%). Hai số đứng cạnh nhau cho người đọc thấy khoảng dao động; đánh giá An toàn / Cần tăng tốc /
Rủi ro vẫn bám số chính (chủ app chốt 21/09/2026).
"""
from __future__ import annotations

import math

import pandas as pd

from datetime import date

from app.metrics import daily_counts, month_range, prev_month
from app.org import phong_order
from app.overview import _targets, phong_khong_cong_tong

HE_SO_MIN, HE_SO_MAX = 0.7, 1.5
AN_TOAN, TANG_TOC, RUI_RO, CHUA_MT = "An toàn", "Cần tăng tốc", "Rủi ro", "Chưa có mục tiêu"


def nhip_cuoi_thang(thang: str, ngay: int, chi_phong: list[str] | None = None) -> dict:
    """Nhịp tháng trước, nói được bằng số thật: bình quân mỗi ngày của phần đầu tháng (tới ngày `ngay`)
    và của phần còn lại, cùng hệ số = cuối / đầu."""
    pm = prev_month(thang)
    days = month_range(pm)[2]
    k = min(ngay, days)
    goc = {"thang_truoc": pm, "cat": k, "so_ngay": days, "dau": None, "cuoi": None, "he_so": 1.0}
    if k >= days:
        return goc
    d = daily_counts(pm, "online")
    if chi_phong is not None:
        d = d.loc[[c for c in d.index if c in set(chi_phong)]]
    dau, cuoi = d.loc[:, :k].to_numpy().sum() / k, d.loc[:, k + 1:].to_numpy().sum() / (days - k)
    if not dau or not cuoi:
        return goc
    return {**goc, "dau": round(float(dau), 1), "cuoi": round(float(cuoi), 1),
            "he_so": round(float(min(HE_SO_MAX, max(HE_SO_MIN, cuoi / dau))), 2)}


def nhip_tuan(thang: str, ngay: int, chi_phong: list[str] | None = None) -> dict:
    """Bình quân online/ngày của 7 ngày gần nhất ĐÃ CHỐT (bỏ ngày còn đang cập nhật), theo phòng.

    Dùng cho kịch bản "không bứt tốc": từ giờ tới cuối tháng mỗi ngày vẫn có số online như tuần vừa rồi.
    """
    from app.overview import trang_thai_ngay
    days = month_range(thang)[2]
    ngay = max(1, min(ngay, days))
    chot = ngay
    if ngay > 1 and trang_thai_ngay(date(int(thang[:4]), int(thang[5:7]), ngay).isoformat())[0]:
        chot = ngay - 1                     # ngày cuối đang nạp số: chưa tính vào nhịp tuần
    tu = max(1, chot - 6)
    d = daily_counts(thang, "online")
    if chi_phong is not None:
        d = d.loc[[c for c in d.index if c in set(chi_phong)]]
    so_ngay = chot - tu + 1
    return {"thang": thang, "tu": tu, "den": chot, "so_ngay": so_ngay,
            "theo_phong": d.loc[:, tu:chot].sum(axis=1) / so_ngay,
            "tb": round(float(d.loc[:, tu:chot].to_numpy().sum() / so_ngay), 1)}


def danh_gia(pct: float | None) -> str:
    if pct is None:
        return CHUA_MT
    return AN_TOAN if pct >= 100 else TANG_TOC if pct >= 90 else RUI_RO


def du_bao_thang(thang: str, ngay: int, chi_phong: list[str] | None = None) -> pd.DataFrame:
    """Dòng = phòng (+ dòng TỔNG): mt, luy_ke, du_bao (giữ nhịp cả tháng tới nay), du_bao_tuan (giữ
    nhịp 7 ngày gần nhất), pct_mt, can_moi_ngay, danh_gia."""
    days = month_range(thang)[2]
    ngay = max(1, min(ngay, days))
    con_lai = days - ngay
    codes = [p["code"] for p in phong_order(thang)]
    if chi_phong is not None:
        codes = [c for c in codes if c in set(chi_phong)]
    ten = {p["code"]: p["ten"] for p in phong_order(thang)}
    luy_ke = daily_counts(thang, "online").loc[:, :ngay].sum(axis=1).reindex(codes).fillna(0)
    tgt = _targets(thang)
    mt = (tgt["internet"] if "internet" in tgt.columns else pd.Series(dtype=float)).reindex(codes).fillna(0)
    tuan = nhip_tuan(thang, ngay, chi_phong)
    nhip = nhip_cuoi_thang(thang, ngay, chi_phong)
    he_so = nhip["he_so"]
    tb_tuan = tuan["theo_phong"].reindex(codes).fillna(0)

    def dong(code, ten_dong, lk, muc_tieu, tb7):
        du_bao = round(lk + lk / ngay * con_lai)
        theo_nhip = round(lk + lk / ngay * con_lai * he_so)
        theo_tuan = round(lk + tb7 * con_lai)
        pct = round(du_bao / muc_tieu * 100) if muc_tieu else None
        can = math.ceil((muc_tieu - lk) / con_lai) if muc_tieu > lk and con_lai else 0
        return {"phong_code": code, "phong": ten_dong, "mt": int(muc_tieu), "luy_ke": int(lk),
                "du_bao": int(du_bao), "du_bao_nhip": int(theo_nhip), "du_bao_tuan": int(theo_tuan),
                "pct_mt": pct, "pct_nhip": round(theo_nhip / muc_tieu * 100) if muc_tieu else None,
                "nhip": he_so,
                "ngay": ngay, "con_lai": con_lai,

                "pct_tuan": round(theo_tuan / muc_tieu * 100) if muc_tieu else None,
                "can_moi_ngay": can if muc_tieu else None,
                "tb_ngay": round(lk / ngay, 1), "danh_gia": danh_gia(pct)}

    rows = [dong(c, ten[c], float(luy_ke[c]), float(mt[c]), float(tb_tuan[c])) for c in codes]
    bo = phong_khong_cong_tong()
    rows.append(dong("TOTAL", "TỔNG", float(luy_ke.sum()),
                     float(mt[[c for c in codes if c not in bo]].sum()), float(tb_tuan.sum())))
    out = pd.DataFrame(rows).astype(object).where(lambda d: d.notna(), None)
    out.attrs.update(ngay=ngay, so_ngay=days, tuan=tuan, nhip=nhip, he_so=he_so)
    return out
