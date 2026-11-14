"""Xem thử trang Điều hành liên khối bằng bộ dữ liệu MINH HOẠ, chạy hoàn toàn trên máy (nhánh thi-lien-khoi).

    python scripts/xem_demo_lien_khoi.py [cổng, mặc định 8060]    ->  http://127.0.0.1:8060/lienkhoi

- Dùng database riêng data/demo_lien_khoi.db (tự tạo, rỗng) và dữ liệu demo/lien_khoi/*.csv: không chạm database của app đang chạy.
- Tự đăng nhập quyền Quản trị cho phiên này và CHỈ nghe địa chỉ 127.0.0.1. Đây là công cụ xem thử trên máy: không đưa lên máy chủ, không dùng cho người khác.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

try:
    sys.stdout.reconfigure(encoding="utf-8")           # màn hình Windows mặc định không in được tiếng Việt
except Exception:
    pass
GOC = Path(__file__).resolve().parents[1]
os.chdir(GOC)
sys.path.insert(0, str(GOC))
os.environ["LIEN_KHOI_NGUON"] = "demo"
os.environ["DATABASE_URL"] = "sqlite:///" + (GOC / "data" / "demo_lien_khoi.db").as_posix()

from flask import session            # noqa: E402

from app.auth import SessionUser, login_manager            # noqa: E402
from app.db import init_db            # noqa: E402
from app.ui.app import app, server            # noqa: E402

cong = int(sys.argv[1]) if len(sys.argv) > 1 else 8060
(GOC / "data").mkdir(exist_ok=True)
init_db()
nguoi = SessionUser(SimpleNamespace(id=1, username="xemthu", ho_ten="Xem thử (dữ liệu minh hoạ)", role="admin", ma_nv=None, session_version=0,
                                    scope=json.dumps([])))
login_manager.user_loader(lambda uid: nguoi)


def _vao():
    session["_user_id"] = "1"
    session["_fresh"] = True


server.before_request_funcs.setdefault(None, []).insert(0, _vao)
print(f"Bản xem thử dữ liệu minh hoạ: http://127.0.0.1:{cong}/lienkhoi")
app.run(host="127.0.0.1", port=cong, debug=False)
