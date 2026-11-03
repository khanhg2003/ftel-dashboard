"""Kết nối database."""
from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import DATABASE_URL, LA_SERVERLESS


class Base(DeclarativeBase):
    pass


def cong_giao_dich(url: str) -> bool:
    """Chuỗi kết nối đi qua Transaction pooler của Supabase (cổng 6543)."""
    from sqlalchemy.engine import make_url
    try:
        return make_url(url).port == 6543
    except Exception:
        return False


def _tao_engine():
    if DATABASE_URL.startswith("sqlite"):
        return create_engine(DATABASE_URL, future=True)
    kw = {
        "future": True,
        "pool_pre_ping": True,
        # Cổng "Transaction pooler" của Supabase (6543) không hỗ trợ prepared statement
        "connect_args": {"prepare_threshold": None, "connect_timeout": 10},
    }
    if LA_SERVERLESS and cong_giao_dich(DATABASE_URL):
        # Transaction pooler (cổng 6543): Supabase ghép nhiều kết nối của app vào ít kết nối thật, nên mỗi máy
        # Vercel giữ sẵn 1-3 kết nối được - không phải bắt tay (TLS + đăng nhập) lại cho từng câu hỏi.
        kw.update(pool_size=1, max_overflow=2, pool_recycle=120, pool_timeout=10)
    elif LA_SERVERLESS:
        # Session pooler (cổng 5432): mỗi kết nối giữ một chỗ thật trong pool có hạn của Supabase -> không giữ
        # lại (tránh cạn kết nối khi nhiều máy chạy song song), mở mới cho mỗi lần dùng.
        kw["poolclass"] = NullPool
    else:
        kw.update(pool_size=5, max_overflow=5, pool_recycle=1800)
    return create_engine(DATABASE_URL, **kw)


engine = _tao_engine()

if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")      # cho phép đọc trong lúc ghi
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def session_scope():
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def init_db() -> None:
    from app import models  # noqa: F401  (đăng ký bảng)

    Base.metadata.create_all(engine)
    _migrate_session_version()


def _migrate_session_version() -> None:
    """Thêm cột session_version vào bảng users nếu chưa tồn tại (migration nhẹ)."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    if "users" not in insp.get_table_names():
        return
    cot = {c["name"] for c in insp.get_columns("users")}
    if "session_version" not in cot:
        with engine.begin() as c:
            c.execute(text("ALTER TABLE users ADD COLUMN session_version INTEGER DEFAULT 0"))


def _migrate_staff_map() -> None:
    """Thêm cột ten_hien_thi vào staff_map nếu chưa tồn tại (migration nhẹ)."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    if "staff_map" not in insp.get_table_names():
        return
    cot = {c["name"] for c in insp.get_columns("staff_map")}
    if "ten_hien_thi" not in cot:
        with engine.begin() as c:
            c.execute(text("ALTER TABLE staff_map ADD COLUMN ten_hien_thi VARCHAR(120)"))


# Chạy ngay lúc nạp module: staff_map đã tồn tại từ trước (không qua init_db() khi chạy script /
# kiểm thử riêng lẻ), nên không thể chỉ trông chờ init_db() hay app/ui/app.py gọi.
_migrate_staff_map()


def _cap_nhat_nhan_su_ibb6() -> None:
    """Cập nhật trạng thái và thâm niên nhân sự IBB6 theo yêu cầu Trưởng phòng:
    - Thu Vân (DNG.VanNTT107): chuyển trạng thái 'Nghỉ tạm thời' -> 'Bình thường'.
    - ThuNA54 (DNG.ThuNA54): thêm vào staff_map (phòng IBB6) và hr_monthly (thâm niên 2 tháng, 'Bình thường').
    """
    from sqlalchemy import inspect, text
    try:
        insp = inspect(engine)
        tables = set(insp.get_table_names())
        if "hr_monthly" not in tables:
            return
        with engine.begin() as c:
            c.execute(text(
                "UPDATE hr_monthly SET trang_thai = 'Bình thường' "
                "WHERE LOWER(TRIM(acc)) = 'dng.vanntt107' AND trang_thai != 'Bình thường'"
            ))
            if "dim_employee" in tables:
                c.execute(text(
                    "UPDATE dim_employee SET trang_thai = 'Đang làm việc' "
                    "WHERE acc_norm = 'dng.vanntt107' AND trang_thai != 'Đang làm việc'"
                ))
            if "staff_map" in tables:
                sm_exists = c.execute(text(
                    "SELECT COUNT(*) FROM staff_map WHERE acc_norm = 'dng.thuna54'"
                )).scalar()
                if not sm_exists:
                    c.execute(text(
                        "INSERT INTO staff_map (acc, acc_norm, phong_code, ten_hien_thi, nguon, updated_at) "
                        "VALUES ('DNG.ThuNA54', 'dng.thuna54', 'IBB6', 'ThuNA54', 'manual', CURRENT_TIMESTAMP)"
                    ))
                else:
                    c.execute(text(
                        "UPDATE staff_map SET phong_code = 'IBB6', ten_hien_thi = 'ThuNA54' "
                        "WHERE acc_norm = 'dng.thuna54' AND phong_code != 'IBB6'"
                    ))
            hr_exists = c.execute(text(
                "SELECT COUNT(*) FROM hr_monthly WHERE LOWER(TRIM(acc)) = 'dng.thuna54'"
            )).scalar()
            if not hr_exists:
                c.execute(text(
                    "INSERT INTO hr_monthly (ma_nv, thang, acc, ho_ten, vi_tri, phong_ps, tham_nien_bucket, "
                    "tham_nien_thang, nhom_tham_nien, trang_thai, dieu_kien) "
                    "VALUES ('THUNA54', '2026-08', 'DNG.ThuNA54', 'ThuNA54', 'NVKD', 'DNGB6', '2', 2, 'MOI', 'Bình thường', 'Đủ ĐK xét')"
                ))
            else:
                c.execute(text(
                    "UPDATE hr_monthly SET tham_nien_bucket = '2', tham_nien_thang = 2, "
                    "nhom_tham_nien = 'MOI', trang_thai = 'Bình thường' "
                    "WHERE LOWER(TRIM(acc)) = 'dng.thuna54' AND (tham_nien_bucket != '2' OR trang_thai != 'Bình thường')"
                ))
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Lỗi cập nhật nhân sự IBB6: %s", e)


_cap_nhat_nhan_su_ibb6()
