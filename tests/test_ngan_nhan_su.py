"""Ngăn chi tiết nhân sự dùng chung: mở từ mọi bảng nhân sự, quyền kiểm ở máy chủ, báo "đang tải" toàn app."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from dash import no_update
from flask_login import login_user

from app import bao_cao_phong as bp
from app.auth import SessionUser
from app.ui import ngan_nhan_su as nn
from app.ui.app import app, server

ASSETS = Path(__file__).resolve().parent.parent / "assets"
THANG, NGAY, PHONG = "2026-09", 11, "IBB2"


def _user(role: str, scope: list[str] | None = None) -> SessionUser:
    return SessionUser(SimpleNamespace(id=99901, username=f"zz_ns_{role}", ho_ten="Thử", role=role, ma_nv=None,
                                       session_version=0, scope=json.dumps(scope or [])))


def _nguoi_ibb2():
    nv = bp.bang_nhan_su(THANG, NGAY, PHONG)
    r = nv[(nv.loai_dong == "data") & (nv.online > 0)].iloc[0]
    return r.acc_norm, r.ho_ten


def _chu(node) -> str:
    return json.dumps(node, default=lambda o: o.to_plotly_json() if hasattr(o, "to_plotly_json") else str(o),
                      ensure_ascii=False)


def test_admin_mo_duoc_ho_so_tu_bang_bat_ky():
    acc, ten = _nguoi_ibb2()
    with server.test_request_context("/"):
        login_user(_user("admin"))
        tieu_de, than = nn.noi_dung(acc, [None], "2026-09-11")      # không gợi ý phòng: máy chủ tự tìm phòng của người này
    chu_tieu_de, chu_than = _chu(tieu_de), _chu(than)
    assert ten in chu_tieu_de and "11/09/2026" in chu_tieu_de
    assert "Bán theo tỉnh và phường / xã" in chu_than and "Chất lượng bán so với phòng" in chu_than


def test_truong_phong_chi_mo_duoc_nguoi_trong_phong_minh():
    acc, _ = _nguoi_ibb2()
    with server.test_request_context("/"):
        login_user(_user("phong", ["IBB3"]))
        tieu_de, than = nn.noi_dung(acc, [PHONG], "2026-09-11")     # trình duyệt gợi ý IBB2 cũng không lách được
    assert "Chưa có chi tiết" in _chu(tieu_de) and "Chất lượng bán" not in _chu(than)


def test_vai_tro_khong_duoc_xem_nhan_su_bi_chan():
    acc, _ = _nguoi_ibb2()
    with server.test_request_context("/"):
        login_user(_user("nhanvien", [PHONG]))
        tieu_de, _than = nn.noi_dung(acc, [PHONG], "2026-09-11")
    assert "Không có quyền" in _chu(tieu_de)


def test_callback_dung_ngan_da_dang_ky_va_bo_qua_luc_chua_chon():
    ham = next(v["callback"] for k, v in app.callback_map.items()
               if "ns-ngan-tieu-de.children" in k and "ns-ngan-than.children" in k and "callback" in v)
    ham = getattr(ham, "__wrapped__", ham)
    with server.test_request_context("/"):
        login_user(_user("admin"))
        kq = ham({"acc": "", "t": 1}, {})
    assert kq[0] is no_update and kq[1] is no_update


def test_khung_ngan_co_dung_ma_va_ma_trong_js_khop():
    ids = _chu(nn.khung())
    for ma in (nn.STORE, "ns-ngan", "ns-ngan-than", "ns-ngan-tieu-de", "ns-ngan-dong", "ns-ngan-nen"):
        assert f'"{ma}"' in ids
    js = (ASSETS / "nhan_su_bam.js").read_text(encoding="utf-8")
    assert f"'{nn.STORE}'" in js and "'ns-ngan-dong'" in js          # JS ghi đúng Store mà máy chủ đang nghe


def test_bang_nhan_su_deu_gan_lop_bam_duoc():
    """Các bảng liệt kê nhân sự phải có lớp `nhan-su-bam`, nếu không bấm đúp không có tác dụng."""
    import re

    goc = Path(__file__).resolve().parent.parent / "app" / "ui" / "pages"
    dung = {"phong.py": 2, "phantich.py": 2, "hr.py": 4, "tracking.py": 1, "sosanh.py": 2, "nhapton.py": 2,
            "baocaongay.py": 1}
    for ten, so in dung.items():
        n = len(re.findall(r"nn\.lop\(", (goc / ten).read_text(encoding="utf-8")))
        assert n == so, f"{ten}: {n} bảng gắn lớp bấm được, cần {so}"


def test_bao_dang_tai_toan_app():
    js = (ASSETS / "dang_tai.js").read_text(encoding="utf-8")
    css = (ASSETS / "style.css").read_text(encoding="utf-8")
    assert "_dash-update-component" in js and "data-dang-tai" in js and "n_intervals" in js
    assert "html.dang-tai #thanh-tai" in css and "[data-dang-tai]" in css
