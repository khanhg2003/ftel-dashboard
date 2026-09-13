"""Chạy app ở chế độ vận hành thật (máy chủ WSGI waitress, không phải server dev).

    python serve.py                 -> http://0.0.0.0:8050
    python serve.py --port 9000     -> đổi cổng
    python serve.py --host 127.0.0.1

Muốn chạy nền như một dịch vụ Windows: xem docs/VANHANH.md
"""
from __future__ import annotations

import argparse
import logging
import socket
import sys
from logging.handlers import RotatingFileHandler

from waitress import serve

from app.config import BASE_DIR
from app.db import init_db
from app.ui.app import server

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MAT_KHAU_MAC_DINH = "Ftel@2026"


def bat_ghi_log() -> None:
    """Ghi log ra `logs/app.log`, xoay vòng 5 file × 2 MB."""
    thu_muc = BASE_DIR / "logs"
    thu_muc.mkdir(exist_ok=True)
    h = RotatingFileHandler(thu_muc / "app.log", maxBytes=2_000_000, backupCount=5,
                            encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    goc = logging.getLogger()
    goc.setLevel(logging.INFO)
    goc.addHandler(h)
    logging.getLogger("waitress").setLevel(logging.INFO)


def kiem_tra_truoc_khi_chay() -> list[str]:
    """Các cảnh báo cấu hình nên xử lý trước khi cho nhiều người dùng."""
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError
    from sqlalchemy import select

    from app.db import session_scope
    from app.models import User

    canh_bao: list[str] = []
    with session_scope() as s:
        users = s.execute(select(User).where(User.active.is_(True))).scalars().all()
        if not users:
            canh_bao.append("Chưa có tài khoản nào - chạy scripts/seed_from_sheet.py")
        for u in users:
            if u.role != "admin":
                continue
            try:
                PasswordHasher().verify(u.password_hash, MAT_KHAU_MAC_DINH)
                canh_bao.append(f"Tài khoản '{u.username}' vẫn dùng mật khẩu mặc định - "
                                "đổi ngay trong mục Quản trị")
            except VerifyMismatchError:
                pass
    return canh_bao


def dia_chi_lan() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8050)
    ap.add_argument("--threads", type=int, default=8)
    a = ap.parse_args()

    bat_ghi_log()
    init_db()

    for cb in kiem_tra_truoc_khi_chay():
        print(f"  ⚠  {cb}")
        logging.getLogger("ftel").warning(cb)

    dia_chi = f"http://{dia_chi_lan()}:{a.port}" if a.host == "0.0.0.0" else \
        f"http://{a.host}:{a.port}"
    print(f"FTEL Dashboard đang chạy: {dia_chi}  ({a.threads} luồng)")
    print(f"Kiểm tra tình trạng: {dia_chi}/healthz · Nhật ký: logs/app.log")
    print("Dừng bằng Ctrl+C")
    logging.getLogger("ftel").info("Khởi động tại %s", dia_chi)
    serve(server, host=a.host, port=a.port, threads=a.threads, ident="FTEL Dashboard")


if __name__ == "__main__":
    main()
