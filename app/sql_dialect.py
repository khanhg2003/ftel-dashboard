"""Đoạn SQL khác nhau giữa SQLite (chạy trên máy) và PostgreSQL (Supabase).

Mọi câu truy vấn viết tay trong app dùng các hàm dưới đây thay vì viết cứng cú pháp
của một loại database, nhờ vậy cùng một code chạy được ở cả hai nơi.
"""
from __future__ import annotations

from app.db import engine

LA_POSTGRES = engine.dialect.name == "postgresql"


def thang_cua(cot: str) -> str:
    """'YYYY-MM' của một cột ngày."""
    return f"to_char({cot}, 'YYYY-MM')" if LA_POSTGRES else f"substr({cot}, 1, 7)"


def so_ngay_giua(sau: str, truoc: str) -> str:
    """Số ngày từ `truoc` đến `sau` (hai cột kiểu ngày)."""
    return f"({sau} - {truoc})" if LA_POSTGRES else f"(julianday({sau}) - julianday({truoc}))"


def so_ngay_den_hom_nay(cot: str) -> str:
    """Số ngày từ một cột ngày đến hôm nay."""
    return f"(CURRENT_DATE - {cot})" if LA_POSTGRES else f"(julianday('now') - julianday({cot}))"
