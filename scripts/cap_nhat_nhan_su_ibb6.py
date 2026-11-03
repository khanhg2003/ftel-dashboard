"""Cập nhật thông tin nhân sự IBB6 theo yêu cầu Trưởng phòng:
1. Nguyễn Thị Thu Vân (DNG.VanNTT107): chuyển trạng thái từ 'Nghỉ tạm thời' thành 'Bình thường'.
2. ThuNA54 (DNG.ThuNA54): thêm vào staff_map (phòng IBB6) và hr_monthly với thâm niên 2 tháng, trạng thái 'Bình thường'.
Áp dụng cho cả database local và Supabase production.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from app.config import chuan_hoa_url_postgres

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()


def update_db(url_str: str, name: str) -> None:
    if url_str.startswith("postgres"):
        url_str = chuan_hoa_url_postgres(url_str)
    print(f"=== Đang cập nhật {name} ===")
    try:
        eng = create_engine(url_str)
        with eng.connect() as conn:
            with conn.begin():
                # 1. Thu Vân (DNG.VanNTT107) -> Bình thường
                res1 = conn.execute(text(
                    "UPDATE hr_monthly SET trang_thai = 'Bình thường' WHERE LOWER(TRIM(acc)) = 'dng.vanntt107'"
                ))
                print(f"  [hr_monthly] Đã sửa trạng thái Thu Vân: {res1.rowcount} dòng")

                try:
                    res1_emp = conn.execute(text(
                        "UPDATE dim_employee SET trang_thai = 'Đang làm việc' WHERE acc_norm = 'dng.vanntt107'"
                    ))
                    print(f"  [dim_employee] Đã sửa Thu Vân: {res1_emp.rowcount} dòng")
                except Exception as e:
                    print(f"  [dim_employee] Bỏ qua ({e})")

                # 2. ThuNA54 -> staff_map
                check_sm = conn.execute(text(
                    "SELECT COUNT(*) FROM staff_map WHERE acc_norm = 'dng.thuna54'"
                )).scalar()
                if check_sm == 0:
                    conn.execute(text(
                        "INSERT INTO staff_map (acc, acc_norm, phong_code, ten_hien_thi, nguon, updated_at) "
                        "VALUES ('DNG.ThuNA54', 'dng.thuna54', 'IBB6', 'ThuNA54', 'manual', CURRENT_TIMESTAMP)"
                    ))
                    print("  [staff_map] Đã thêm ThuNA54 vào phòng IBB6")
                else:
                    conn.execute(text(
                        "UPDATE staff_map SET phong_code = 'IBB6', ten_hien_thi = 'ThuNA54' "
                        "WHERE acc_norm = 'dng.thuna54'"
                    ))
                    print("  [staff_map] Đã cập nhật ThuNA54 thuộc phòng IBB6")

                # 3. ThuNA54 -> hr_monthly (thâm niên 2 tháng, trạng thái Bình thường)
                check_hr = conn.execute(text(
                    "SELECT COUNT(*) FROM hr_monthly WHERE LOWER(TRIM(acc)) = 'dng.thuna54'"
                )).scalar()
                if check_hr == 0:
                    conn.execute(text(
                        "INSERT INTO hr_monthly (ma_nv, thang, acc, ho_ten, vi_tri, phong_ps, tham_nien_bucket, "
                        "tham_nien_thang, nhom_tham_nien, trang_thai, dieu_kien) "
                        "VALUES ('THUNA54', '2026-08', 'DNG.ThuNA54', 'ThuNA54', 'NVKD', 'DNGB6', '2', 2, 'MOI', 'Bình thường', 'Đủ ĐK xét')"
                    ))
                    print("  [hr_monthly] Đã thêm ThuNA54 với thâm niên 2 tháng")
                else:
                    conn.execute(text(
                        "UPDATE hr_monthly SET tham_nien_bucket = '2', tham_nien_thang = 2, "
                        "nhom_tham_nien = 'MOI', trang_thai = 'Bình thường' "
                        "WHERE LOWER(TRIM(acc)) = 'dng.thuna54'"
                    ))
                    print("  [hr_monthly] Đã cập nhật thâm niên 2 tháng cho ThuNA54")

        print(f"==> Thành công trên {name}!\n")
    except Exception as e:
        print(f"Lỗi khi cập nhật {name}: {e}\n")


if __name__ == "__main__":
    # 1. Local database
    local_db = "sqlite:///data/ftel.db"
    update_db(local_db, "Local SQLite (data/ftel.db)")

    # 2. Supabase Production database
    supabase_url = os.getenv("SUPABASE_DB_URL", "").strip()
    if supabase_url:
        update_db(supabase_url, "Supabase Production")
    else:
        print("CẢNH BÁO: Chưa tìm thấy SUPABASE_DB_URL trong file .env")
