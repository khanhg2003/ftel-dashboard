"""Giờ giấc: database và máy chủ Vercel đều chạy giờ UTC, người dùng xem giờ Việt Nam.

Quy ước: mọi mốc thời gian GHI xuống database là giờ UTC (không kèm múi giờ),
chỉ đổi sang giờ Việt Nam lúc HIỂN THỊ.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

LECH_GIO_VN = timedelta(hours=7)


def utc_bay_gio() -> datetime:
    return datetime.utcnow()


def gio_viet_nam() -> datetime:
    return datetime.utcnow() + LECH_GIO_VN


def sang_gio_vn(v) -> datetime | None:
    """Mốc UTC đọc từ database -> giờ Việt Nam (None nếu trống)."""
    if v is None or (not isinstance(v, datetime) and pd.isna(v)):
        return None
    t = pd.Timestamp(v)
    if pd.isna(t):
        return None
    return t.to_pydatetime().replace(tzinfo=None) + LECH_GIO_VN


def chu_gio_vn(v, dang: str = "%d/%m/%Y %H:%M") -> str:
    t = sang_gio_vn(v)
    return f"{t:{dang}}" if t else ""
