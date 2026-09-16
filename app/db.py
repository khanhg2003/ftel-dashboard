"""Kết nối database."""
from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import DATABASE_URL, LA_SERVERLESS


class Base(DeclarativeBase):
    pass


def _tao_engine():
    if DATABASE_URL.startswith("sqlite"):
        return create_engine(DATABASE_URL, future=True)
    kw = {
        "future": True,
        "pool_pre_ping": True,
        # Cổng "Transaction pooler" của Supabase (6543) không hỗ trợ prepared statement
        "connect_args": {"prepare_threshold": None, "connect_timeout": 10},
    }
    if LA_SERVERLESS:
        # mỗi lần gọi hàm là một tiến trình ngắn - để pooler của Supabase giữ kết nối,
        # app không tự giữ pool (tránh cạn kết nối khi nhiều máy chạy song song)
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
