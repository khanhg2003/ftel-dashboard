"""Kiểm thử trang Phân tích bán hàng và cách xử lý file export cuộn 3 tháng."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import phan_tich as pt                                        # noqa: E402
from app.config import DATA_DIR                                        # noqa: E402

THANG = "2026-09"
pytestmark = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(),
                                reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")


def test_so_online_khop_bao_cao_tong():
    from app.overview import bang_tong_quan
    tu, den, ngay = pt.ky_phan_tich(THANG)
    df = pt.hop_dong_online(tu, den)
    bang, ngay_bc = bang_tong_quan(THANG)
    assert ngay == ngay_bc == 11
    assert len(df) == int(bang[bang.loai_dong == "total"].online.iloc[0]) == 1394
    assert df.hop_dong.is_unique


def test_ty_le_ban_kem_hop_le():
    tu, den, _ = pt.ky_phan_tich(THANG)
    df = pt.hop_dong_online(tu, den)
    c = pt.chi_so_chung(df)
    for k in ("kem_vvip", "kem_camera", "du_3", "tra_truoc", "onl_1_ngay", "ngoai_tinh"):
        assert 0 <= c[k] <= 100
    assert c["du_3"] <= min(c["kem_vvip"], c["kem_camera"])
    # tỷ lệ đọc ngược lại phải ra đúng số hợp đồng có cờ kèm V.VIP
    assert df.co_vvip.sum() == round(c["kem_vvip"] * len(df) / 100)


def test_bang_theo_phong_dong_tong_bang_tong_cac_phong():
    tu, den, _ = pt.ky_phan_tich(THANG)
    df, ton = pt.hop_dong_online(tu, den), pt.hop_dong_ton()
    bang = pt.bang_theo_phong(df, ton, THANG)
    data = bang[bang.loai_dong == "data"]
    tong = bang[bang.loai_dong == "total"].iloc[0]
    assert data.online.sum() == tong.online == len(df)
    assert data.ton.sum() == tong.ton == len(ton)


def test_chi_nhanh_chi_lay_phong_cua_chi_nhanh():
    from app.org import loc_chi_nhanh
    tu, den, _ = pt.ky_phan_tich(THANG)
    qnm = loc_chi_nhanh(None, "QNM", THANG)
    df = pt.hop_dong_online(tu, den, qnm)
    assert len(df) and set(df.phong_code) <= set(qnm)


def test_nhom_goi():
    assert pt.nhom_goi("Giga F1") == "Giga" and pt.nhom_goi("sky") == "Sky"
    assert pt.nhom_goi("Super300-Biz") == "Khác" and pt.nhom_goi(None) == "Khác"


def test_ton_theo_tuoi_cong_du():
    ton = pt.hop_dong_ton()
    g = pt.ton_theo_tuoi(ton, THANG)
    tong = g[g.loai_dong == "total"].iloc[0]
    assert tong.tong == len(ton) == sum(tong[f"m{i}"] for i in range(len(pt.MOC_TON)))


def test_ban_ngoai_tinh_la_phan_bu_cua_pttb_cnql():
    from app.overview import bang_tong_quan
    tu, den, _ = pt.ky_phan_tich(THANG)
    df = pt.hop_dong_online(tu, den)
    bang, _ = bang_tong_quan(THANG)
    cnql = int(bang[bang.loai_dong == "total"].cnql.iloc[0])
    assert df.ngoai_tinh.sum() == len(df) - cnql


# ---------------------------------------------------------- file cuộn 3 tháng
def _gia_lap_lan_nap(monkeypatch, dong):
    import app.metrics as m
    df = pd.DataFrame(dong, columns=["batch_id", "cn_ban", "n"])
    monkeypatch.setattr(m.pd, "read_sql", lambda *a, **k: df)
    return m


def test_so_ton_xet_file_moi_nhat_rieng_tung_chi_nhanh(monkeypatch):
    # file Đà Nẵng (lần 59) nạp sau file Quảng Nam (lần 58): tồn QNM vẫn lấy từ lần 58
    m = _gia_lap_lan_nap(monkeypatch, [(59, "DNG_01", 3394), (59, "DNG_02", 4771), (59, "HCM_ECOM", 281),
                                       (58, "QNM", 2063), (58, "HCM_ECOM", 64), (22, "DNG_01", 40)])
    assert m.lan_nap_moi_nhat_theo_chi_nhanh() == {"DNG": 59, "QNM": 58}
    dk, p = m.dieu_kien_ton("f.")
    assert dk.startswith("f.ngay_online IS NULL AND (")
    assert p["lo_0"] == 59 and p["lo_1"] == 58 and "f.batch_id IN (:lo_0, :lo_1)" in dk


def test_file_le_khong_dung_de_loc_so_ton(monkeypatch):
    # lần 60 chỉ vài chục dòng Đà Nẵng (file lẻ) -> vẫn dùng bản chụp đầy đủ lần 59
    m = _gia_lap_lan_nap(monkeypatch, [(60, "DNG_01", 30), (59, "DNG_01", 3394), (59, "DNG_02", 4771),
                                       (58, "QNM", 2063)])
    assert m.lan_nap_moi_nhat_theo_chi_nhanh() == {"DNG": 59, "QNM": 58}


def test_chua_nap_file_nao_thi_ton_la_moi_hop_dong_chua_online(monkeypatch):
    m = _gia_lap_lan_nap(monkeypatch, [])
    assert m.dieu_kien_ton() == ("ngay_online IS NULL", {})


def test_so_ton_chay_duoc_tren_database():
    from sqlalchemy import text

    from app.db import engine
    from app.metrics import dieu_kien_ton
    dk, p = dieu_kien_ton("f.")
    with engine.connect() as c:
        assert c.execute(text(f"SELECT COUNT(*) FROM fact_internet f WHERE {dk}"), p).scalar() >= 0


def test_nap_lai_camera_khong_dem_trung_khi_hop_dong_doi_thong_tin():
    from sqlalchemy import func, select

    from app.db import SessionLocal
    from app.ingest.commit import _bo_dong_camera_cu, _upsert
    from app.models import FactCamera

    s = SessionLocal()
    try:
        cu = s.execute(select(FactCamera).where(FactCamera.ngay_online.is_(None)).limit(1)).scalar_one()
        dem = lambda: s.execute(select(func.count()).select_from(FactCamera)       # noqa: E731
                                .where(FactCamera.hop_dong == cu.hop_dong)).scalar()
        truoc = dem()
        # file mới: đúng hợp đồng đó nhưng đã online -> mã băm dòng khác
        moi = {c.name: getattr(cu, c.name) for c in FactCamera.__table__.columns
               if c.name != "updated_at"}
        moi.update(row_hash="hash-moi-sau-khi-online", ngay_online=cu.ngay_tao_hd)
        cac_dong_khac = [{c.name: getattr(o, c.name) for c in FactCamera.__table__.columns
                          if c.name != "updated_at"}
                         for o in s.execute(select(FactCamera).where(
                             FactCamera.hop_dong == cu.hop_dong,
                             FactCamera.row_hash != cu.row_hash)).scalars()]
        rows = [moi] + cac_dong_khac
        _bo_dong_camera_cu(s, rows)
        _upsert(s, FactCamera, rows, "row_hash")
        assert dem() == truoc
        assert s.get(FactCamera, cu.row_hash) is None
    finally:
        s.rollback()
        s.close()


def test_camera_dong_giong_het_van_dem_tung_dong_va_nap_lai_khong_nhan_doi():
    from app.ingest.commit import _danh_so_dong_camera_giong_nhau

    def file():
        return [{"row_hash": "a"}, {"row_hash": "a"}, {"row_hash": "b"}, {"row_hash": "a"}]
    lan1, lan2 = file(), file()
    _danh_so_dong_camera_giong_nhau(lan1)
    _danh_so_dong_camera_giong_nhau(lan2)
    ma = [r["row_hash"] for r in lan1]
    assert ma == ["a", "a#2", "b", "a#3"] and len(set(ma)) == 4       # 4 dòng file = 4 camera
    assert ma == [r["row_hash"] for r in lan2]                          # nạp lại cùng file -> cùng mã


def test_trang_phan_tich_dung_duoc():
    from flask_login import login_user
    from sqlalchemy import select

    from app.auth import SessionUser
    from app.db import session_scope
    from app.models import User
    from app.ui.app import server
    from app.ui.pages import phantich
    with session_scope() as s:
        admin = SessionUser(s.execute(select(User).where(User.role == "admin")).scalars().first())
    with server.test_request_context("/"):
        login_user(admin)
        assert phantich.layout() is not None and phantich.topbar()


def test_khong_con_chu_dau_noi():
    goc = Path(__file__).resolve().parent.parent
    for f in list((goc / "app").rglob("*.py")) + list((goc / "docs").glob("*.md")):
        assert "đấu nối" not in f.read_text(encoding="utf-8").lower(), f


def test_excel_phan_tich_moi_bang_mot_sheet():
    import io

    from openpyxl import load_workbook

    from app.export_phan_tich import xuat_phan_tich
    tu, den, _ = pt.ky_phan_tich(THANG)
    df, ton = pt.hop_dong_online(tu, den), pt.hop_dong_ton()
    bang = pt.bang_theo_phong(df, ton, THANG)
    noi_dung = xuat_phan_tich("", "PHÂN TÍCH", [
        ("Theo phòng", bang, [("phong", "Phòng", "text"), ("online", "Online", "so"),
                              ("kem_vvip", "HĐ kèm V.VIP", "pct")]),
        ("Trống", bang.iloc[0:0], [("phong", "Phòng", "text")])])
    wb = load_workbook(io.BytesIO(noi_dung))
    assert wb.sheetnames == ["Theo phòng"]                 # bảng trống không tạo sheet
    ws = wb["Theo phòng"]
    assert ws["A3"].value == "Phòng" and ws.cell(row=4, column=3).number_format == "0%"


def test_muc_chung_kinh_doanh_chi_tinh_phong_kinh_doanh():
    from app.org import phong_order
    tu, den, _ = pt.ky_phan_tich(THANG)
    df = pt.hop_dong_online(tu, den)
    kd = {p["code"] for p in phong_order(THANG) if p["loai"] in pt.LOAI_KINH_DOANH}
    assert pt.muc_chung_kinh_doanh(df, THANG)["online"] == int(df.phong_code.isin(kd).sum())


def test_moc_ton_lien_mach_khong_trung():
    for (a1, b1, _), (a2, _, _) in zip(pt.MOC_TON, pt.MOC_TON[1:]):
        assert a2 == b1 + 1
    assert pt.MOC_TON[0][0] == 0 and pt.MOC_TON[2][0] == 7      # khớp mốc "chờ từ 7 ngày"


# ---------------------------------------------------------- chất lượng dữ liệu
def test_chat_luong_moi_muc_chay_duoc_va_xep_theo_muc_do():
    from app import chat_luong as cl
    kq = cl.chay(THANG, "all")
    assert len(kq) == len(cl.MUC) and not [r["ten"] for r in kq if r["loi"]]
    thu_tu = [(r["muc_do"] == "Ổn", cl.THU_TU_MUC_DO.get(r["muc_do_goc"])) for r in kq]
    assert thu_tu == sorted(thu_tu)
    qnm = {r["ma"]: r["so_luong"] for r in cl.chay(THANG, "QNM")}
    tat_ca = {r["ma"]: r["so_luong"] for r in kq}
    assert all(qnm[m] <= tat_ca[m] for m in ("khong_net", "nguon_kxd", "lech_phong"))


def test_chat_luong_bat_dung_bat_thuong():
    from app import chat_luong as cl
    nghi = cl.nghi_van_co_so(THANG, "all")
    assert "DNG.Thaidh5" in set(nghi.acc)                                     # ghi Nghỉ mà vẫn có số
    kn = cl.khong_co_internet(THANG, "all")
    assert len(kn) and kn.loai.isin(["Truyền hình", "Camera"]).all()


def test_ngay_thap_bat_thuong_so_voi_cung_thu(monkeypatch):
    from app import chat_luong as cl
    # 5 tuần, mỗi thứ Hai 100 hợp đồng; thứ Hai cuối chỉ 30 -> dưới 50% bình quân cùng thứ
    ngays = pd.date_range("2026-08-10", "2026-09-14")
    df = pd.DataFrame({"ngay": ngays, "cn_ban": "DNG_01",
                       "n": [30 if d == pd.Timestamp("2026-09-14") else 100 for d in ngays]})
    monkeypatch.setattr(cl, "_q", lambda *a, **k: df)
    monkeypatch.setattr(cl, "_ngay_tam_tinh", lambda d: False)
    out = cl.ngay_bat_thuong(THANG, "all")
    assert list(out.ngay) == ["2026-09-14"] and out.ty_le.iloc[0] == 30


def test_excel_chat_luong_moi_muc_mot_sheet():
    import io

    from openpyxl import load_workbook

    from app.ui.app import app, server
    from app.ui.pages import chatluong  # noqa: F401  (đăng ký callback)
    ham = app.callback_map["cl-tai-xuong.data"]["callback"]
    with server.test_request_context("/"):
        kq = ham.__wrapped__(1, THANG, "all")
    wb = load_workbook(io.BytesIO(__import__("base64").b64decode(kq["content"])))
    assert wb.sheetnames[0] == "Tổng hợp" and len(wb.sheetnames) > 3


def test_file_dang_dung_it_dong_hon_lan_truoc_thi_bao(monkeypatch):
    from app import chat_luong as cl
    bay_gio = pd.Timestamp.now("UTC").tz_localize(None)
    df = pd.DataFrame([  # file Đà Nẵng ~8.700 dòng và file Quảng Nam ~2.200 dòng nạp xen kẽ
        (1, "internet", "DN.xlsx", 8700, 0, 0), (2, "internet", "QN.xlsx", 2200, 0, 0),
        (3, "internet", "DN.xlsx", 7500, 0, 0), (4, "internet", "QN.xlsx", 2210, 0, 0),
        (5, "camera", "CAM.xlsx", 5000, 0, 400)],
        columns=["id", "dataset", "file_name", "rows_total", "rows_invalid", "rows_duplicate"])
    df["uploaded_at"], df["uploaded_by"] = bay_gio, "admin"
    monkeypatch.setattr(cl, "_q", lambda *a, **k: df)
    out = cl.lan_nap_bat_thuong(THANG, "all")
    assert list(out.lan_nap) == [3] and "14%" in out.van_de.iloc[0]      # QN không bị đem so với DN; camera trùng bỏ qua


def test_ban_theo_tinh_goi_di_sau_va_mot_ngay():
    tu, den, _ = pt.ky_phan_tich(THANG)
    df = pt.hd_theo_tinh(tu, den)
    assert len(df) == len(pt.hop_dong_online(tu, den)) and {"xa", "nhom_goi", "tinh"} <= set(df.columns)
    goi = pt.co_cau_goi_tinh(df, 50)
    assert goi.so_hd.sum() == len(df)
    assert all(abs(sum(r[f"{g}_pct"] for g in (*pt.NHOM_GOI, "Khác")) - 100) < 0.5 for _, r in goi.iterrows())
    ma = goi.ma_tinh.iloc[0]
    ct = pt.chi_tiet_tinh(df, ma)
    assert ct["tong"] == goi.so_hd.iloc[0] == ct["xa"].so.sum() == ct["goi"].so.sum() >= ct["nv"].so.sum()
    mt, tinh = pt.ma_tran_nv_tinh(df, {}, {})
    assert len(tinh) <= 12 and (mt[[m for m, _ in tinh]].sum(axis=1) + mt.khac == mt.tong).all()
    assert mt.tong.sum() <= len(df)
    ban, onl = pt.ban_online_ngay(den)
    phong = sorted(set(ban.phong_code) | set(onl.phong_code))
    b = pt.bang_ngay_tinh(ban, onl, phong)
    assert b.tong_ban.sum() == len(ban) and b.tong_onl.sum() == len(onl)
    assert sum(b[f"{p}_ban"].sum() for p in phong) == len(ban)
    assert pt.ten_xa("Phuong Hoa Khanh") == "Phường Hoa Khanh" and pt.ten_xa("Không xác định") == "Không rõ"


def test_ky_khoang_ngay_tu_chon():
    from app.ui.pages import phantich
    from app.metrics import cac_ngay_co_du_lieu
    den = cac_ngay_co_du_lieu()[-1]
    k = phantich._ky(None, den)
    assert k.luy_ke and k.tu == den[:8] + "01" and k.ten_ck.startswith("cùng kỳ")
    from datetime import date, timedelta
    d = date.fromisoformat(den)
    k = phantich._ky((d - timedelta(days=6)).isoformat(), den)
    assert not k.luy_ke and k.ten_ck == "kỳ trước"
    assert k.ck == ((d - timedelta(days=13)).isoformat(), (d - timedelta(days=7)).isoformat())
