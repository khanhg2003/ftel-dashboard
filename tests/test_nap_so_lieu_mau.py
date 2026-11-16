"""Số liệu mẫu của bản demo công khai (`scripts/nap_so_lieu_mau.py`): nạp vào SQLite TẠM bằng tiến trình riêng, không chạm data/kiemthu.db hay database thật."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

GOC = Path(__file__).resolve().parent.parent
KIEM_TRA_SO = """
from datetime import date
from app.overview import bang_tong_quan, trang_thai_ngay
from app.dvkh import insight, so_lieu as sl, tong_quan
df, ngay = bang_tong_quan("2026-11", 14)
tong = df[df.loai_dong == "total"].iloc[0]
tq = tong_quan.tinh(date(2026, 11, 14))
print(int(tong.online), int(tong.ck_online), int(tong.mt_internet), trang_thai_ngay("2026-11-14")[0], len(sl.sr_bi_dong()), len(sl.sr_chu_dong()),
      len(tq["roi_mang"]), len(tq["cong_no"]), len(insight.tao_nhan_dinh()))
"""


def _chay(*lenh: str, db: Path, **env) -> subprocess.CompletedProcess:
    e = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "DATABASE_URL": f"sqlite:///{db.as_posix()}", **env}
    return subprocess.run([sys.executable, *lenh], cwd=str(GOC), env=e, capture_output=True, text=True, encoding="utf-8", timeout=600)


@pytest.fixture(scope="module")
def db_mau(tmp_path_factory):
    db = tmp_path_factory.mktemp("mau") / "mau.db"
    kq = _chay("scripts/nap_so_lieu_mau.py", db=db)
    assert kq.returncode == 0, kq.stdout[-1500:] + kq.stderr[-1500:]
    return db, json.loads(kq.stdout)


def _dem(db: Path, bang: str, dieu_kien: str = "1=1") -> int:
    with sqlite3.connect(db) as c:
        return c.execute(f"SELECT COUNT(*) FROM {bang} WHERE {dieu_kien}").fetchone()[0]


def test_moi_bang_co_dong(db_mau):
    db, kq = db_mau
    for bang in ("dim_phong", "staff_map", "dim_employee", "hr_monthly", "target_monthly", "fact_pheu_ban_hang", "fact_internet", "fact_fptplay", "fact_camera", "upload_batch",
                 "dv_nap", "dv_sr_bi_dong", "dv_sr_chu_dong", "dv_sr_bd_them", "dv_au_kh", "dv_roi_mang", "dv_cong_no", "dv_cong_no_chot", "dv_danh_sach"):
        assert _dem(db, bang) > 0, bang
    assert kq["kinh_doanh"]["internet"] == _dem(db, "fact_internet") >= 500
    assert kq["dvkh"]["sr_bd"] == _dem(db, "dv_sr_bi_dong") >= 1000


def test_co_hai_thang_va_tinh_den_ngay_tham_chieu(db_mau):
    db, _ = db_mau
    assert _dem(db, "fact_internet", "ngay_online >= '2026-10-01' AND ngay_online <= '2026-10-31'") > 300
    assert _dem(db, "fact_internet", "ngay_online >= '2026-11-01' AND ngay_online <= '2026-11-14'") > 300
    assert _dem(db, "fact_internet", "ngay_online > '2026-11-14'") == 0
    assert _dem(db, "fact_internet", "ngay_online IS NULL") > 20                   # có hợp đồng tồn
    assert _dem(db, "fact_fptplay", "la_vvip = 1") > 0 and _dem(db, "fact_camera", "ngay_online >= '2026-11-01'") > 0
    assert _dem(db, "target_monthly", "thang = '2026-11'") > 0


def test_nhan_su_va_ma_hop_dong_deu_la_bia(db_mau):
    db, _ = db_mau
    assert _dem(db, "staff_map", "acc NOT LIKE '%.demo%'") == 0
    assert _dem(db, "fact_internet", "acc_nhan_vien NOT LIKE '%demo%' AND acc_nhan_vien NOT LIKE 'HNI.%'") == 0
    assert _dem(db, "fact_internet", "hop_dong NOT LIKE 'MHKD%'") == 0
    assert _dem(db, "dv_sr_bi_dong", "so_hd NOT LIKE 'MHDV%'") == 0
    assert _dem(db, "dv_sr_bi_dong", "nguoi_xu_ly IS NOT NULL AND nguoi_xu_ly NOT LIKE 'cskh_%' AND nguoi_xu_ly NOT LIKE 'ktv_%'") == 0
    assert _dem(db, "dim_employee", "ho_ten NOT LIKE '%IBB%' AND ho_ten NOT LIKE 'Nh%' AND ho_ten NOT LIKE 'Tr%'") == 0
    with sqlite3.connect(db) as c:                                                  # tên khách chỉ có dạng giả "Khách 00001"
        assert all(t[0].startswith("Khách ") for t in c.execute("SELECT ten_khach_hang FROM fact_internet WHERE ten_khach_hang IS NOT NULL").fetchall())


def test_cac_trang_doc_ra_so(db_mau):
    db, _ = db_mau
    kq = _chay("-c", KIEM_TRA_SO, db=db, LIEN_KHOI_NGUON="demo")
    assert kq.returncode == 0, kq.stderr[-2000:]
    onl, ck, mt, dang_cap_nhat, bd, cd, rm, cn, nd = kq.stdout.split()[-9:]
    assert int(onl) > 300 and int(ck) > 300 and int(mt) > 500
    assert dang_cap_nhat == "False"                                                 # ngày tham chiếu hiện là số đã chốt
    assert int(bd) > 1000 and int(cd) > 1000 and int(rm) == 3 and int(cn) == 3 and int(nd) >= 5


def test_chay_lai_khong_nap_trung(db_mau):
    db, _ = db_mau
    truoc = (_dem(db, "fact_internet"), _dem(db, "dv_sr_bi_dong"), _dem(db, "dv_nap"))
    kq = _chay("scripts/nap_so_lieu_mau.py", db=db)
    assert kq.returncode == 0, kq.stderr[-1000:]
    assert list(json.loads(kq.stdout)) == ["ngay_tc"]                               # không nạp gì thêm
    assert (_dem(db, "fact_internet"), _dem(db, "dv_sr_bi_dong"), _dem(db, "dv_nap")) == truoc


def test_tu_choi_database_khong_phai_sqlite(tmp_path):
    kq = subprocess.run([sys.executable, "scripts/nap_so_lieu_mau.py"], cwd=str(GOC), capture_output=True, text=True, encoding="utf-8",
                        env={**os.environ, "PYTHONUTF8": "1", "DATABASE_URL": "postgresql://nguoi:mat@localhost:5432/khong_co"}, timeout=120)
    assert kq.returncode == 1 and "SQLite" in kq.stdout


def test_ruff_sach():
    kq = subprocess.run([sys.executable, "-m", "ruff", "check", "app", "scripts", "--select", "F,E9"], cwd=str(GOC), capture_output=True, text=True, timeout=300)
    if "No module named ruff" in kq.stderr:
        pytest.skip("Chưa cài ruff")
    assert kq.returncode == 0, kq.stdout[-1500:]
