"""Chuẩn bị database riêng cho kiểm thử.

Các phép kiểm chốt con số (1.394 số online, 980 V.VIP...) phải luôn cho ra cùng kết quả,
không phụ thuộc vào việc hôm nay ai vừa nạp thêm file gì vào database thật. Vì vậy bộ
kiểm thử dựng riêng một database từ đúng bộ dữ liệu gốc kỳ 01-11/09/2026 và dùng lại
cho các lần chạy sau (`data/kiemthu.db`).

Muốn dựng lại từ đầu: xoá file `data/kiemthu.db` rồi chạy lại pytest.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

GOC = Path(__file__).resolve().parent.parent
DB_KIEM_THU = GOC / "data" / "kiemthu.db"
NGUON = [GOC / "Báo cáo T9-2026 - T9.2026.csv", GOC / "NSLĐ T8.2026.xlsx - DNG.csv"]

# Phải đặt trước khi bất kỳ module nào của app được nạp, vì engine tạo lúc import.
os.environ["DATABASE_URL"] = f"sqlite:///{DB_KIEM_THU.as_posix()}"


def _dung_database() -> bool:
    if DB_KIEM_THU.exists():
        return True
    if not all(f.exists() for f in NGUON):
        return False
    print("\nĐang dựng database kiểm thử từ dữ liệu gốc kỳ 01-11/09/2026 (chỉ lần đầu)...")
    kq = subprocess.run([sys.executable, str(GOC / "scripts" / "seed_from_sheet.py")],
                        cwd=str(GOC), env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                        capture_output=True, text=True)
    if kq.returncode != 0:
        print(kq.stdout[-2000:], kq.stderr[-2000:])
        DB_KIEM_THU.unlink(missing_ok=True)
        return False
    return DB_KIEM_THU.exists()


SAN_SANG = _dung_database()


@pytest.fixture(autouse=True)
def database_kiem_thu(request):
    """Bỏ qua bài kiểm thử nếu không dựng được dữ liệu mẫu. NGOẠI LỆ: các bài `test_lien_khoi*` (nhánh thi-lien-khoi) chỉ dùng bộ dữ liệu minh hoạ
    trong `demo/lien_khoi` nên luôn chạy, để người không có file dữ liệu thật (đồng đội) vẫn có lưới an toàn."""
    if not SAN_SANG and not Path(str(request.node.fspath)).name.startswith("test_lien_khoi"):
        pytest.skip("Thiếu file dữ liệu gốc để dựng database kiểm thử")
    yield


@pytest.fixture(autouse=True)
def _xoa_bo_nho():
    """Mỗi phép kiểm bắt đầu với bộ nhớ tạm trống (nhiều phép ghi thẳng vào database bằng SQL)."""
    from app.bo_nho import xoa
    xoa()
    yield
