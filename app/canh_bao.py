"""Quy tắc "cần chú ý" dùng chung cho Báo cáo phòng và Nhân sự & NSLĐ (BGĐ chốt 14/09/2026).

Hai mức, xét theo nhịp có số online của từng người tại ngày chọn:
- Trao đổi ngay: từ 7 ngày không có số online nào (hoặc chưa có số trong cả khoảng xét).
- Theo dõi: từ 3 ngày liền chưa có số, hoặc tuần này (7 ngày gần nhất) giảm từ một nửa so với
  tuần trước (tuần trước từ 3 số), hoặc NSLĐ tháng gần nhất chưa đạt.
"""
from __future__ import annotations

import pandas as pd

TRAO_DOI_NGAY, THEO_DOI = "Trao đổi ngay", "Theo dõi"
THU_TU_MUC = {TRAO_DOI_NGAY: 0, THEO_DOI: 1, "": 2}
NGAY_TRAO_DOI_NGAY = 7       # từ 7 ngày không có số online nào
NGAY_THEO_DOI = 3            # từ 3 ngày liền chưa có số
SUT_TUAN = 0.5               # tuần này còn không quá một nửa tuần trước
TUAN_TRUOC_TOI_THIEU = 3     # chỉ xét sụt khi tuần trước có từ 3 số

MO_TA_TRAO_DOI_NGAY = f"Từ {NGAY_TRAO_DOI_NGAY} ngày không có số online nào."
MO_TA_THEO_DOI = (f"Từ {NGAY_THEO_DOI} ngày liền chưa có số, tuần này giảm từ một nửa so với tuần trước "
                  f"(tuần trước từ {TUAN_TRUOC_TOI_THIEU} số), hoặc NSLĐ chưa đạt.")


def _trong(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v))


def xet(so_ngay_khong_so, tuan_nay: int, tuan_truoc: int, nsld_chua_dat: bool = False,
        thang_nsld: str = "", khong_co_so: str = "Chưa có số trong 4 tuần") -> tuple[str, list[str]]:
    """(mức, các lý do). so_ngay_khong_so = số ngày từ lần có số gần nhất đến ngày xét (None: chưa có)."""
    muc, ly_do = "", []
    if _trong(so_ngay_khong_so):
        muc = TRAO_DOI_NGAY
        ly_do.append(khong_co_so)
    elif so_ngay_khong_so >= NGAY_TRAO_DOI_NGAY:
        muc = TRAO_DOI_NGAY
        ly_do.append(f"{int(so_ngay_khong_so)} ngày chưa có số")
    elif so_ngay_khong_so >= NGAY_THEO_DOI:
        muc = THEO_DOI
        ly_do.append(f"{int(so_ngay_khong_so)} ngày liền chưa có số")
    if (tuan_truoc or 0) >= TUAN_TRUOC_TOI_THIEU and (tuan_nay or 0) <= tuan_truoc * SUT_TUAN \
            and muc != TRAO_DOI_NGAY:
        muc = muc or THEO_DOI
        ly_do.append(f"Tuần này {int(tuan_nay or 0)}, tuần trước {int(tuan_truoc)} "
                     f"(−{round((1 - (tuan_nay or 0) / tuan_truoc) * 100)}%)")
    if nsld_chua_dat:
        muc = muc or THEO_DOI
        ly_do.append(f"NSLĐ T{thang_nsld} chưa đạt" if thang_nsld else "NSLĐ chưa đạt")
    return muc, ly_do
