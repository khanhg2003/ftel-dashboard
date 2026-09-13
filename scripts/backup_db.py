"""Sao lưu database (an toàn kể cả khi app đang chạy).

Chạy tay:      python scripts/backup_db.py
Chạy tự động:  đặt lịch Windows Task Scheduler gọi lệnh trên mỗi ngày (xem docs/VANHANH.md)
"""
from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.config import BASE_DIR, DATA_DIR  # noqa: E402

GIU_LAI = 30          # giữ 30 bản sao lưu gần nhất
THU_MUC = BASE_DIR / "backups"


def sao_luu() -> Path | None:
    nguon = DATA_DIR / "ftel.db"
    if not nguon.exists():
        print("Không tìm thấy database:", nguon)
        return None
    THU_MUC.mkdir(exist_ok=True)
    dich = THU_MUC / f"ftel_{datetime.now():%Y%m%d_%H%M}.db"

    # dùng API backup của SQLite -> bản sao nhất quán dù app đang ghi
    # (closing() để đóng hẳn kết nối - `with sqlite3.connect` chỉ commit, không đóng,
    #  trên Windows sẽ giữ file khiến không xoá/di chuyển được ngay sau đó)
    with closing(sqlite3.connect(nguon)) as src, closing(sqlite3.connect(dich)) as dst:
        src.backup(dst)
    print(f"Đã sao lưu: {dich.name} ({dich.stat().st_size / 1_048_576:.1f} MB)")
    return dich


def don_ban_cu() -> int:
    ds = sorted(THU_MUC.glob("ftel_*.db"), reverse=True)
    xoa = ds[GIU_LAI:]
    for f in xoa:
        f.unlink()
    if xoa:
        print(f"Đã xoá {len(xoa)} bản sao lưu cũ (giữ lại {GIU_LAI} bản gần nhất)")
    return len(xoa)


if __name__ == "__main__":
    if sao_luu():
        don_ban_cu()
