"""Chạy bản DEMO liên khối CÔNG KHAI (nhánh thi-lien-khoi) trên một máy chủ: ai mở link cũng xem được, tự vào quyền Quản trị. Dữ liệu toàn là MINH HOẠ.

    python scripts/chay_demo_cong_khai.py [--host 0.0.0.0] [--port 8060]

- Database riêng (SQLite `data/demo_lien_khoi.db`) và dữ liệu `demo/lien_khoi/*.csv`: không chạm database của app đang chạy thật.
- Lần đầu (file trạng thái còn trống) tự nạp 14 ngày lịch sử mô phỏng và việc hôm nay, để mở ra là có số liệu.
- Khối Kinh doanh / DVKH đọc thẳng database nên lần đầu cũng được nạp số liệu mẫu tổng hợp (`scripts/nap_so_lieu_mau.py`; `--nap-lai-so-lieu-mau` để nạp lại). Biến `DEMO_DB` đổi file database.
- TỪ CHỐI chạy nếu có `LIEN_KHOI_ZALO_TOKEN`: bản công khai ai cũng bấm được nên tuyệt đối không được gửi tin Zalo thật (chỉ ghi hộp thư giả lập).
- Chạy bằng waitress (như `serve.py`). KHÔNG đặt chung thư mục với app chạy thật, KHÔNG dùng file .env của app thật.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8060)
    ap.add_argument("--threads", type=int, default=6)
    ap.add_argument("--nap-lai-so-lieu-mau", action="store_true", help="xoá số liệu mẫu của khối Kinh doanh / DVKH rồi nạp lại (mặc định chỉ nạp khi còn trống)")
    a = ap.parse_args()
    if os.environ.get("LIEN_KHOI_ZALO_TOKEN") or os.environ.get("LIEN_KHOI_ZALO_GUI"):
        print("Từ chối chạy: bản công khai không được có LIEN_KHOI_ZALO_TOKEN / LIEN_KHOI_ZALO_GUI (ai bấm cũng gửi được tin Zalo thật).")
        return 1
    from flask import session
    from waitress import serve

    from app.auth import SessionUser, login_manager
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
    nguoi = SessionUser(SimpleNamespace(id=1, username="demo", ho_ten="Demo (dữ liệu minh hoạ)", role="admin", ma_nv=None, session_version=0, scope=json.dumps([])))
    login_manager.user_loader(lambda uid: nguoi)

    def _vao():
        session["_user_id"] = "1"
        session["_fresh"] = True

    server.before_request_funcs.setdefault(None, []).insert(0, _vao)
    print(f"Demo công khai: http://{a.host}:{a.port}/lienkhoi")
    serve(server, host=a.host, port=a.port, threads=a.threads)
    return 0


if __name__ == "__main__":
    sys.exit(main())
