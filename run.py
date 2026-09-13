"""Khởi động ứng dụng:  python run.py   ->  http://127.0.0.1:8050"""
from __future__ import annotations

import sys

from app.db import init_db
from app.ui.app import app, server  # noqa: F401  (server dùng cho waitress/gunicorn)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

if __name__ == "__main__":
    init_db()
    print("FTEL Dashboard: http://127.0.0.1:8050")
    app.run(host="127.0.0.1", port=8050, debug=False)
