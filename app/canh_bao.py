"""Quy tắc "cần chú ý" dùng chung cho Báo cáo phòng và Nhân sự & NSLĐ (BGĐ chốt 14/09/2026).

Hai mức, xét theo nhịp có số online của từng người tại ngày chọn:
- Trao đổi ngay: từ 7 ngày không có số online nào (hoặc chưa có số trong cả khoảng xét).
- Theo dõi: từ 3 ngày liền chưa có số, hoặc tuần này (7 ngày gần nhất) giảm từ một nửa so với
  tuần trước (tuần trước từ 3 số), hoặc NSLĐ tháng gần nhất chưa đạt.
Không xét (chốt 18/09/2026): người đã ghi "Nghỉ" trong danh mục nhân sự và trưởng phòng (acc khớp tài
khoản Trưởng phòng trên app theo tên đăng nhập = phần sau dấu chấm của acc, hoặc theo mã NV).
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
                  f"(tuần trước từ {TUAN_TRUOC_TOI_THIEU} số), hoặc NSLĐ chưa đạt. Không xét người đã ghi "
                  "Nghỉ và trưởng phòng.")


def la_acc_tam(ghi_chu) -> bool:
    """Ghi chú đánh dấu "Acc tạm" = người chỉ để nhập liệu ở Báo cáo ngày và Nhập tồn (vd chưa cấp acc inside):
    KHÔNG tính vào số nhân sự, xếp hạng, cảnh báo (chủ app chốt 03/10/2026). Không phân biệt hoa thường và dấu."""
    from app.ingest.commit import _bo_dau
    return "acc tam" in _bo_dau(str(ghi_chu or "")).lower()


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


def _tp_va_danh_muc():
    from sqlalchemy import text

    from app.db import engine
    from app.ingest.normalize import norm_manv
    with engine.connect() as c:
        staff = c.execute(text("SELECT acc_norm, ma_nv, ghi_chu FROM staff_map")).all()
        tp = c.execute(text("SELECT username, ma_nv FROM users WHERE role = 'phong' AND active = TRUE")).all()
    ten_tp = {str(u).strip().lower() for u, _ in tp if u}
    ma_tp = {norm_manv(m) for _, m in tp if m} - {""}
    la_tp = {a for a, ma, _ in staff if a and (a.split(".")[-1] in ten_tp or (ma and norm_manv(ma) in ma_tp))}
    # TP dùng acc admin (không có role='phong'): nhận diện qua ghi_chu chứa 'truong' (không dấu, lower)
    la_tp |= {a for a, _, gc in staff if a and "truong" in (gc or "").lower()}
    return staff, ten_tp, la_tp


def acc_truong_phong(them_acc=()) -> set[str]:
    """acc_norm của trưởng phòng (khớp tài khoản Trưởng phòng trên app theo tên đăng nhập = phần sau dấu
    chấm của acc, hoặc theo mã NV). Trưởng phòng không tính vào mọi chỉ số hiệu suất cá nhân (chốt
    18/09/2026) - số bán của họ vẫn cộng cho phòng."""
    _, ten_tp, la_tp = _tp_va_danh_muc()
    return la_tp | {a for a in them_acc if a and str(a).split(".")[-1] in ten_tp}


def acc_khong_xet(them_acc=()) -> dict[str, str]:
    """acc_norm -> lý do không đưa vào cảnh báo ("Đã nghỉ" / "Trưởng phòng")."""
    staff, ten_tp, la_tp = _tp_va_danh_muc()
    out = {a: "Trưởng phòng" for a in la_tp}
    for a, _, ghi_chu in staff:
        if a and a not in out and "nghỉ" in (ghi_chu or "").lower():
            out[a] = "Đã nghỉ"
        elif a and a not in out and la_acc_tam(ghi_chu):
            out[a] = "Acc tạm"
    for a in them_acc:
        if a and a not in out and str(a).split(".")[-1] in ten_tp:
            out[a] = "Trưởng phòng"
    return out
