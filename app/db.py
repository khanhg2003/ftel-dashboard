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
