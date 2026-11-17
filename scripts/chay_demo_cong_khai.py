"""Chạy bản DEMO liên khối CÔNG KHAI (nhánh thi-lien-khoi) trên một máy chủ: phải ĐĂNG NHẬP bằng tài khoản demo (`DEMO_USER` / `DEMO_MAT_KHAU` đặt trong .env của máy chủ). Dữ liệu toàn là MINH HOẠ.

    python scripts/chay_demo_cong_khai.py [--host 0.0.0.0] [--port 8060]

- Database riêng (SQLite `data/demo_lien_khoi.db`) và dữ liệu `demo/lien_khoi/*.csv`: không chạm database của app đang chạy thật.
- Lần đầu (file trạng thái còn trống) tự nạp 14 ngày lịch sử mô phỏng và việc hôm nay, để mở ra là có số liệu.
- Khối Kinh doanh / DVKH đọc thẳng database nên lần đầu cũng được nạp số liệu mẫu tổng hợp (`scripts/nap_so_lieu_mau.py`; `--nap-lai-so-lieu-mau` để nạp lại). Biến `DEMO_DB` đổi file database.
- TỪ CHỐI chạy nếu có `LIEN_KHOI_ZALO_TOKEN`: bản công khai ai cũng bấm được nên tuyệt đối không được gửi tin Zalo thật (chỉ ghi hộp thư giả lập).
- Chạy bằng waitress (như `serve.py`). KHÔNG đặt chung thư mục với app chạy thật, KHÔNG dùng file .env của app thật.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
GOC = Path(__file__).resolve().parents[1]
os.chdir(GOC)
sys.path.insert(0, str(GOC))
os.environ["LIEN_KHOI_NGUON"] = "demo"
(GOC / "data").mkdir(exist_ok=True)
os.environ["DATABASE_URL"] = "sqlite:///" + Path(os.environ.get("DEMO_DB") or GOC / "data" / "demo_lien_khoi.db").resolve().as_posix()      # DEMO_DB: đổi file database (vd để thử trên bản sao)


def tao_tai_khoan_demo(user: str, mat_khau: str) -> None:
    """Tài khoản duy nhất của bản công khai (quyền Quản trị trong database demo, không phải của app thật); mỗi lần chạy đặt lại mật khẩu theo biến môi trường.
    Đăng nhập bằng form của app: sai 5 lần thì khoá 15 phút."""
    from argon2 import PasswordHasher
    from sqlalchemy import select

    from app.db import session_scope
    from app.models import User

    with session_scope() as s:
        row = s.execute(select(User).where(User.username == user)).scalars().first()
        if row is None:
            row = User(username=user, ho_ten="Demo (dữ liệu minh hoạ)", role="admin", scope="[]", active=True, password_hash="")
            s.add(row)
        row.password_hash = PasswordHasher().hash(mat_khau)
        row.active, row.failed_logins, row.locked_until = True, 0, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8060)
    ap.add_argument("--threads", type=int, default=6)
    ap.add_argument("--nap-lai-so-lieu-mau", action="store_true", help="xoá số liệu mẫu của khối Kinh doanh / DVKH rồi nạp lại (mặc định chỉ nạp khi còn trống)")
    a = ap.parse_args()
    user, mat_khau = os.environ.get("DEMO_USER", "").strip(), os.environ.get("DEMO_MAT_KHAU", "")
    if not user or not mat_khau:
        print("Từ chối chạy: bản công khai phải có tài khoản đăng nhập. Đặt DEMO_USER và DEMO_MAT_KHAU (trong file .env của máy chủ, không đưa vào git).")
        return 1
    if os.environ.get("LIEN_KHOI_ZALO_TOKEN") or os.environ.get("LIEN_KHOI_ZALO_GUI"):
        print("Từ chối chạy: bản công khai không được có LIEN_KHOI_ZALO_TOKEN / LIEN_KHOI_ZALO_GUI (ai bấm cũng gửi được tin Zalo thật).")
        return 1
    from waitress import serve

    from app.db import init_db
    from app.lien_khoi import mo_phong as mp, theo_doi as td
    from app.ui.app import server

    init_db()
    from scripts.nap_so_lieu_mau import nap_mau
    kq = nap_mau(nap_lai=a.nap_lai_so_lieu_mau)
    if len(kq) > 1:
        print("Nạp số liệu mẫu Kinh doanh / DVKH:", {k: v for k, v in kq.items() if k != "ngay_tc"})
    if td.danh_sach().empty:
        print("Nạp dữ liệu minh hoạ lần đầu:", mp.chuan_bi_demo())
    tao_tai_khoan_demo(user, mat_khau)
    print(f"Demo công khai: http://{a.host}:{a.port}/lienkhoi")
    serve(server, host=a.host, port=a.port, threads=a.threads)
    return 0


if __name__ == "__main__":
    sys.exit(main())
