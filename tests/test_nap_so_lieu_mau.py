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


KIEM_TRA_NHAP = """
from datetime import date
from app import ads, bao_cao_ngay as bc, danh_ba, nhap_ton as nt, online_ca_phan_tich as hq, phong_online as po
b = bc.bang(["IBB7"], date(2026, 11, 14))
ton = nt.danh_sach(["IBB7"])
on = po.bang_nhan_su("2026-11", 14)
kh = po.khtn_theo_ngay("2026-11", 14)
pg = ads.theo_page(date(2026, 11, 1), date(2026, 11, 14))
h = hq.hieu_qua(["IBB7"], date(2026, 11, 8), date(2026, 11, 14), now=18 * 60)
print(len(b), int(b.pttb_thang.sum()), int(b.khtn.sum()), len(ton), int((ton.ghi_chu != "").sum()), len(on[on.loai_dong == "data"]), len(kh), int(kh.so_ngay_nhap.min()),
      len(pg), h["tong"]["ca"] > 20, len(danh_ba.tat_ca()), danh_ba.chi_nhanh_mac_dinh())
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
                 "dv_nap", "dv_sr_bi_dong", "dv_sr_chu_dong", "dv_sr_bd_them", "dv_au_kh", "dv_roi_mang", "dv_cong_no", "dv_cong_no_chot", "dv_danh_sach",
                 "bao_cao_ngay", "bao_cao_ngay_chu", "ton_theo_doi", "online_ca", "danh_ba", "ads_page", "ads_sale", "ads_pic", "ads_ngay", "ads_lead", "ads_thang", "phan_hoi_he_thong"):
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


def _acc_online() -> list[str]:
    import yaml
    return [str(a).lower() for a in yaml.safe_load((GOC / "config" / "rules.yml").read_text(encoding="utf-8"))["phong_online"]["acc"]]


def test_nhan_su_va_ma_hop_dong_deu_la_bia(db_mau):
    db, _ = db_mau
    online = ", ".join(f"'{a}'" for a in _acc_online())
    assert _dem(db, "staff_map", f"acc NOT LIKE '%.demo%' AND lower(acc) NOT IN ({online})") == 0       # trừ 5 acc Phòng Online khai ở rules.yml (tên người vẫn bịa)
    assert _dem(db, "fact_internet", f"acc_nhan_vien NOT LIKE '%demo%' AND acc_nhan_vien NOT LIKE 'HNI.%' AND lower(acc_nhan_vien) NOT IN ({online})") == 0
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


def test_phong_online_co_du_nam_nguoi_va_so(db_mau):
    db, _ = db_mau
    for a in _acc_online():
        assert _dem(db, "staff_map", f"lower(acc) = '{a}' AND phong_code = 'IBB2'") == 1, a
        assert _dem(db, "fact_internet", f"lower(acc_nhan_vien) = '{a}' AND ngay_online >= '2026-11-01'") > 0, a
        assert _dem(db, "bao_cao_ngay", f"acc_norm = '{a}' AND phong_code = 'ONLINE' AND khtn > 0") >= 10, a      # bảng KHTN từng bạn có số nhiều ngày
    assert _dem(db, "online_ca", "phong_code = 'ONLINE'") > 0


def test_nhap_lieu_ibb7_bao_cao_ngay_nhap_ton_ads_danh_ba(db_mau):
    db, kq = db_mau
    assert _dem(db, "bao_cao_ngay", "phong_code = 'IBB7' AND ngay = '2026-11-14' AND khtn > 0") == 10      # mọi dòng của bảng Báo cáo ngày đều có báo cáo ở ngày tham chiếu
    assert _dem(db, "bao_cao_ngay", "phong_code = 'IBB7' AND ngay >= '2026-10-25' AND ngay <= '2026-11-14'") > 150
    assert _dem(db, "bao_cao_ngay_chu", "phong_code = 'IBB7'") >= 4
    assert _dem(db, "target_monthly", "doi_tuong = 'NHAN_VIEN' AND thang = '2026-11'") >= 14
    assert kq["nhap_lieu"]["nhap_ton"] >= 10 and _dem(db, "ton_theo_doi", "ngay_moc IS NOT NULL AND phuong_an IS NOT NULL AND ghi_chu IS NOT NULL") >= 10
    assert _dem(db, "online_ca", "phong_code = 'IBB7' AND trang_thai = 'da_online' AND online_luc IS NOT NULL") > 20
    assert _dem(db, "ads_page") == 10 and _dem(db, "ads_ngay", "ngay >= '2026-11-01'") > 100 and _dem(db, "ads_lead", "pttb > 0") > 50
    assert _dem(db, "ads_pic", "den_ngay IS NOT NULL") > 0                                           # cần một phân công đã kết thúc, xem `nap_ads`
    assert _dem(db, "danh_ba", "nguon = 'PNC'") > 50 and _dem(db, "danh_ba", "nguon = 'TIN'") > 10 and _dem(db, "danh_ba", "nguon = 'TAY'") == 2
    assert _dem(db, "danh_ba", "email NOT LIKE '%@example.com'") == 0                                  # email giả, không có email thật
    assert _dem(db, "hr_monthly", "thang = '2026-01'") > 50 and _dem(db, "hr_monthly", "nhom_tham_nien = 'MOI' AND thang = '2026-11'") > 0   # đủ 11 tháng NSLĐ và có tân binh
    assert _dem(db, "target_monthly", "chi_tieu = 'ngay' AND thang = '2026-11'") >= 20


def test_cac_trang_nhap_lieu_doc_ra_so(db_mau):
    db, _ = db_mau
    kq = _chay("-c", KIEM_TRA_NHAP, db=db, LIEN_KHOI_NGUON="demo")
    assert kq.returncode == 0, kq.stderr[-2000:]
    ib7, pttb, khtn, ton, co_ghi_chu, online, kh, ngay_nhap, page, co_ca, ba, mac_dinh = kq.stdout.strip().splitlines()[-1].split(maxsplit=11)
    assert int(ib7) == 10 and int(pttb) > 50 and int(khtn) > 50
    assert int(ton) >= 10 and int(co_ghi_chu) >= 10
    assert int(online) == 5 and int(kh) == 5 and int(ngay_nhap) >= 8                     # Phòng Online: đủ 5 người, mỗi người báo KHTN nhiều ngày
    assert int(page) == 10 and co_ca == "True" and int(ba) > 100 and mac_dinh == "Đà Nẵng"


def test_chay_lai_khong_nap_trung(db_mau):
    db, _ = db_mau
    truoc = (_dem(db, "fact_internet"), _dem(db, "dv_sr_bi_dong"), _dem(db, "dv_nap"), _dem(db, "bao_cao_ngay"), _dem(db, "danh_ba"))
    kq = _chay("scripts/nap_so_lieu_mau.py", db=db)
    assert kq.returncode == 0, kq.stderr[-1000:]
    assert list(json.loads(kq.stdout)) == ["ngay_tc"]                               # không nạp gì thêm
    assert (_dem(db, "fact_internet"), _dem(db, "dv_sr_bi_dong"), _dem(db, "dv_nap"), _dem(db, "bao_cao_ngay"), _dem(db, "danh_ba")) == truoc


def test_tu_choi_database_khong_phai_sqlite(tmp_path):
    kq = subprocess.run([sys.executable, "scripts/nap_so_lieu_mau.py"], cwd=str(GOC), capture_output=True, text=True, encoding="utf-8",
                        env={**os.environ, "PYTHONUTF8": "1", "DATABASE_URL": "postgresql://nguoi:mat@localhost:5432/khong_co"}, timeout=120)
    assert kq.returncode == 1 and "SQLite" in kq.stdout


def test_ruff_sach():
    kq = subprocess.run([sys.executable, "-m", "ruff", "check", "app", "scripts", "--select", "F,E9"], cwd=str(GOC), capture_output=True, text=True, timeout=300)
    if "No module named ruff" in kq.stderr:
        pytest.skip("Chưa cài ruff")
    assert kq.returncode == 0, kq.stdout[-1500:]
