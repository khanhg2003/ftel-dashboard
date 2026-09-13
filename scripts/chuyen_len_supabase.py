"""Chuyển toàn bộ dữ liệu từ database trên máy (SQLite) lên Supabase (PostgreSQL).

Chạy:
    python scripts/chuyen_len_supabase.py            # chép lần đầu (Supabase phải còn trống)
    python scripts/chuyen_len_supabase.py --lam-lai  # xoá sạch dữ liệu trên Supabase rồi chép lại

Cần có SUPABASE_DB_URL trong file .env (chuỗi "Session pooler" - cổng 5432).
Script KHÔNG in mật khẩu ra màn hình và không sửa gì database trên máy.

Việc script làm:
1. Tạo đủ bảng trên Supabase theo đúng cấu trúc app đang dùng.
2. Chép từng bảng theo thứ tự (bảng danh mục trước, bảng số liệu sau).
3. Không chép tên khách hàng (báo cáo không dùng) - trừ khi LUU_TEN_KHACH_HANG=true.
4. Đặt lại bộ đếm mã tự tăng để lần thêm mới sau không bị trùng mã.
5. Khoá bảng khỏi cổng truy cập công khai của Supabase (bật RLS, thu quyền anon).
6. So số dòng từng bảng giữa hai nơi.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(GOC / ".env")

from sqlalchemy import create_engine, func, inspect, select, text  # noqa: E402
from sqlalchemy.pool import NullPool                               # noqa: E402

KHOI = 2000


def _url_postgres(url: str) -> str:
    if url.startswith(("postgres://", "postgresql://")):
        return "postgresql+psycopg://" + url.split("://", 1)[1]
    return url


def _kieu_python(col):
    try:
        return col.type.python_type
    except NotImplementedError:
        return None


def _an_mat_khau(url: str) -> str:
    u = urlsplit(url)
    return f"{u.scheme}://{u.username}:***@{u.hostname}:{u.port}{u.path}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lam-lai", action="store_true",
                    help="Xoá dữ liệu đang có trên Supabase rồi chép lại từ đầu")
    a = ap.parse_args()

    dich_url = os.getenv("SUPABASE_DB_URL", "").strip()
    if not dich_url:
        sys.exit("Chưa có SUPABASE_DB_URL trong file .env - xem docs/TRIEN_KHAI.md bước 3.")
    dich_url = _url_postgres(dich_url)

    nguon_url = f"sqlite:///{(GOC / 'data' / 'ftel.db').as_posix()}"
    if not (GOC / "data" / "ftel.db").exists():
        sys.exit("Không thấy data/ftel.db trên máy.")

    # models dùng chung Base cho mọi database; engine của app không bị dùng ở đây
    os.environ.setdefault("DATABASE_URL", nguon_url)
    from app.db import Base
    from app import models  # noqa: F401

    nguon = create_engine(nguon_url)
    dich = create_engine(dich_url, poolclass=NullPool,
                         connect_args={"prepare_threshold": None, "connect_timeout": 15})

    print("Nguồn :", nguon_url)
    print("Đích  :", _an_mat_khau(dich_url))
    with dich.connect() as c:
        print("Kết nối Supabase OK ·", c.execute(text("select version()")).scalar().split(",")[0])

    Base.metadata.create_all(dich)
    bang = Base.metadata.sorted_tables                    # cha trước, con sau

    with dich.begin() as c:
        co_du_lieu = {t.name: c.execute(select(func.count()).select_from(t)).scalar()
                      for t in bang}
    if any(co_du_lieu.values()) and not a.lam_lai:
        dang_co = ", ".join(f"{k}={v}" for k, v in co_du_lieu.items() if v)
        sys.exit(f"Supabase đã có dữ liệu ({dang_co}).\n"
                 "Muốn chép lại từ đầu thì chạy thêm --lam-lai.")

    luu_ten_kh = os.getenv("LUU_TEN_KHACH_HANG", "false").lower() == "true"

    with dich.begin() as c:
        if a.lam_lai:
            ten = ", ".join(f'"{t.name}"' for t in bang)
            c.execute(text(f"TRUNCATE {ten} RESTART IDENTITY CASCADE"))
            print("Đã xoá dữ liệu cũ trên Supabase.")

        for t in bang:
            cot_nguon = {col["name"] for col in inspect(nguon).get_columns(t.name)} \
                if inspect(nguon).has_table(t.name) else set()
            if not cot_nguon:
                print(f"  {t.name:<18} (không có trên máy, bỏ qua)")
                continue
            cot = [col for col in t.columns if col.name in cot_nguon]
            cot_bool = [col.name for col in cot if _kieu_python(col) is bool]
            n = 0
            with nguon.connect() as cn:
                kq = cn.execution_options(stream_results=True).execute(
                    select(*[t.c[col.name] for col in cot]))
                while True:
                    lo = kq.fetchmany(KHOI)
                    if not lo:
                        break
                    dong = [dict(r._mapping) for r in lo]
                    if "ten_khach_hang" in t.c and not luu_ten_kh:
                        for d in dong:
                            d["ten_khach_hang"] = None
                    for d in dong:                         # SQLite lưu boolean dạng 0/1
                        for col in cot_bool:
                            if d.get(col) is not None:
                                d[col] = bool(d[col])
                    c.execute(t.insert(), dong)
                    n += len(dong)
            print(f"  {t.name:<18} {n:>7} dòng")

        # bộ đếm mã tự tăng
        for t in bang:
            pk = list(t.primary_key.columns)
            if len(pk) == 1 and pk[0].autoincrement is not False and _kieu_python(pk[0]) is int:
                c.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('\"{t.name}\"', '{pk[0].name}'), "
                    f"COALESCE((SELECT MAX(\"{pk[0].name}\") FROM \"{t.name}\"), 0) + 1, false)"))

        # Khoá bảng khỏi Data API công khai: bật RLS, không tạo chính sách nào -> vai trò
        # anon/authenticated không đọc được gì; app kết nối bằng tài khoản postgres nên không ảnh hưởng.
        for t in bang:
            c.execute(text(f'ALTER TABLE "{t.name}" ENABLE ROW LEVEL SECURITY'))
            c.execute(text(f'REVOKE ALL ON TABLE "{t.name}" FROM anon, authenticated'))
        print("Đã bật RLS và thu quyền anon/authenticated trên mọi bảng.")

    print("\nĐối chiếu số dòng:")
    lech = 0
    with nguon.connect() as cn, dich.connect() as cd:
        for t in bang:
            if not inspect(nguon).has_table(t.name):
                continue
            a1 = cn.execute(select(func.count()).select_from(t)).scalar()
            a2 = cd.execute(select(func.count()).select_from(t)).scalar()
            dau = "OK " if a1 == a2 else "LỆCH"
            lech += a1 != a2
            print(f"  [{dau}] {t.name:<18} máy {a1:>7} · Supabase {a2:>7}")
    print("\nHOÀN TẤT - dữ liệu đã lên Supabase." if not lech else
          f"\nCÓ {lech} BẢNG LỆCH - không dùng Supabase cho tới khi xử lý xong.")


if __name__ == "__main__":
    main()
