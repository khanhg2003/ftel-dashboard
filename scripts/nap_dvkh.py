"""Nạp file Excel báo cáo DVKH vào database từ dòng lệnh (dùng khi file quá nặng để tải qua web, hoặc chạy hằng ngày bằng lịch).

    python scripts/nap_dvkh.py "E:\Bao cao DVKH T10.2026.xlsx" --ngay 2026-10-21

Database là DATABASE_URL trong .env (Supabase) hoặc data/ftel.db trên máy. Ngày chốt mặc định là hôm nay.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", help="đường dẫn file Excel DVKH")
    ap.add_argument("--ngay", help="ngày chốt YYYY-MM-DD (mặc định hôm nay)")
    ap.add_argument("--nguoi", default="script", help="tên ghi vào lịch sử nạp")
    a = ap.parse_args()
    from app.dvkh import nap
    r = nap.nap_file(a.file, date.fromisoformat(a.ngay) if a.ngay else None, Path(a.file).name, a.nguoi)
    print({k: v for k, v in r.items() if k != "canh_bao"})
    for c in r.get("canh_bao", []):
        print("Cảnh báo:", c)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
