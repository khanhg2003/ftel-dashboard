"""Nạp dữ liệu mẫu từ file Google Sheet đang dùng (file ghép nhiều khối).

Chạy:  python scripts/seed_from_sheet.py
Khi có file export gốc (.xlsx) thì không cần script này nữa - upload thẳng trên giao diện.
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml
from argon2 import PasswordHasher
from sqlalchemy import select

from app.config import BASE_DIR, CONFIG_DIR
from app.db import init_db, session_scope
from app.ingest.commit import commit_result, file_hash, thang_tu_ten_file
from app.ingest.loader import load_file, read_raw
from app.ingest.normalize import norm_acc, norm_text, parse_number
from app.models import StaffMap, Target, User
from app.org import phong_by_name, sync_org_to_db

SHEET = BASE_DIR / "Báo cáo T9-2026 - T9.2026.csv"
HR = BASE_DIR / "NSLĐ T8.2026.xlsx - DNG.csv"
THANG_SHEET = "2026-09"
UU_TIEN = {"danh_muc_nv": 0, "internet": 1, "fptplay": 2, "camera": 3, "nhan_su": 4}


def apply_overrides(session) -> int:
    f = CONFIG_DIR / "staff_overrides.yml"
    if not f.exists():
        return 0
    data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    n = 0
    for o in data.get("overrides", []) or []:
        acc_norm = norm_acc(o["acc"])
        code = phong_by_name().get(norm_text(o["phong"]).lower(), o["phong"])
        row = session.execute(select(StaffMap).where(StaffMap.acc_norm == acc_norm)).scalars().first()
        if row is None:
            row = StaffMap(acc=o["acc"], acc_norm=acc_norm, phong_code=code, nguon="override")
            session.add(row)
        row.phong_code = code
        row.ghi_chu = o.get("ghi_chu")
        n += 1
    return n


def seed_targets(session) -> int:
    """Lấy chỉ tiêu tháng từ bảng tổng hợp trong sheet (cột A..V). Sửa lại trong app sau."""
    raw = read_raw(SHEET)
    name2code = phong_by_name()
    n = 0
    for i in range(2, 40):
        ten = norm_text(raw.iat[i, 0])
        code = name2code.get(ten.lower())
        if not code:
            continue
        for col, chi_tieu in ((2, "internet"), (14, "camera"), (17, "ngay")):
            val = parse_number(raw.iat[i, col])
            if val is None:
                continue
            row = session.execute(select(Target).where(
                Target.thang == THANG_SHEET, Target.doi_tuong == "PHONG",
                Target.ma_doi_tuong == code, Target.chi_tieu == chi_tieu)).scalars().first()
            if row is None:
                row = Target(thang=THANG_SHEET, doi_tuong="PHONG", ma_doi_tuong=code,
                             chi_tieu=chi_tieu)
                session.add(row)
            row.gia_tri = val
            row.ghi_chu = "Nạp tạm từ sheet cũ - cần xác nhận lại"
            n += 1
    return n


def seed_admin(session) -> str | None:
    if session.execute(select(User).where(User.username == "admin")).scalars().first():
        return None
    pwd = "Ftel@2026"
    session.add(User(username="admin", ho_ten="Quản trị hệ thống", role="admin",
                     password_hash=PasswordHasher().hash(pwd), scope=None, active=True))
    return pwd


def main() -> None:
    init_db()
    with session_scope() as s:
        nb, np_ = sync_org_to_db(s)
        print(f"Đồng bộ cơ cấu tổ chức: {nb} bầy, {np_} phòng được tạo mới")

        print(f"\nĐọc {SHEET.name} ...")
        results = sorted(load_file(SHEET), key=lambda r: UU_TIEN.get(r.dataset, 9))
        h = file_hash(SHEET)
        for res in results:
            if not res.ok:
                print(f"  - bỏ qua {res.dataset:12s} {res.nguon}: {'; '.join(res.canh_bao)}")
                continue
            stats = commit_result(s, res, nguon_file=SHEET.name, hash_file=h, user="seed",
                                  thang=THANG_SHEET)
            print(f"  + {res.dataset:12s} {res.nguon}: {stats}")
            if res.dataset == "danh_muc_nv":
                s.flush()
                print("    ghi đè thủ công:", apply_overrides(s), "acc")
                s.flush()

        print(f"\nĐọc {HR.name} ...")
        thang_hr = thang_tu_ten_file(HR.name) or "2026-08"
        for res in load_file(HR):
            if not res.ok:
                print(f"  - bỏ qua {res.dataset}: {'; '.join(res.canh_bao)} {res.thieu_cot}")
                continue
            stats = commit_result(s, res, nguon_file=HR.name, hash_file=file_hash(HR),
                                  user="seed", thang=thang_hr)
            print(f"  + {res.dataset:12s} (tháng {thang_hr}): {stats}")

        print("\nChỉ tiêu nạp tạm:", seed_targets(s), "dòng")
        pwd = seed_admin(s)
        if pwd:
            print(f"\nTài khoản quản trị: admin / {pwd}  (đổi mật khẩu ngay sau khi đăng nhập)")


if __name__ == "__main__":
    main()
