"""Điểm vào của app khi chạy trên Vercel.

Vercel tìm biến `app` (ứng dụng WSGI) trong file này. Mọi đường dẫn đều được chuyển về đây
(xem vercel.json), Flask + Dash tự điều hướng tiếp như khi chạy trên máy.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ui.app import server as app  # noqa: E402,F401
