"""Kiểm thử Ads IBB7: nhận dữ liệu n8n / bot Telegram, chia chi phí theo người chạy page, đánh giá page."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import ads                                                    # noqa: E402
from app.config import DATA_DIR                                        # noqa: E402

pytestmark = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(),
                                reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")
T = date(2026, 8, 1), date(2026, 8, 31)          # tháng riêng cho kiểm thử, không đụng dữ liệu tháng 9


@pytest.fixture(scope="module", autouse=True)
def sach():
    ads.dam_bao_bang()
    from sqlalchemy import text

    from app.db import engine

    def xoa():
        with engine.begin() as c:
            ids = [r[0] for r in c.execute(text("SELECT id FROM ads_page WHERE ma LIKE 'ZZ KT%'"))]
            for bang in ("ads_ngay", "ads_lead", "ads_pic"):
                for i in ids:
                    c.execute(text(f"DELETE FROM {bang} WHERE page_id = :i"), {"i": i})
            c.execute(text("DELETE FROM ads_page WHERE ma LIKE 'ZZ KT%'"))
            c.execute(text("DELETE FROM ads_sale WHERE ten LIKE 'ZZ %'"))
    xoa()
    yield
    xoa()


def _pid(ma):
    return int(ads.ds_page().set_index("ma").id[ma])


def test_nhan_chi_tieu_ghi_de_khong_nhan_doi_va_tu_tao_page():
    kq = ads.nhan_chi_tieu({"page": "zz kt  một", "rows": [
        {"camp": "C1", "ngay": "2026-08-01", "chi_tieu": "4,50", "tin_nhan": 3, "tinh_trang": "HOẠT ĐỘNG"},
        {"camp": "C2", "ngay": "02/08/2026", "chi_tieu": 2, "tin_nhan": 1},
        {"camp": "", "ngay": "2026-08-03", "chi_tieu": 1}]})
    assert kq["moi"] == 2 and kq["page_moi"] == ["ZZ KT MỘT"] and len(kq["loi"]) == 1
    kq = ads.nhan_chi_tieu([{"page": "ZZ KT MỘT", "camp": "C1", "ngay": "2026-08-01", "chi_tieu": 5, "tin_nhan": 4}])
    assert kq["moi"] == 0 and kq["cap_nhat"] == 1
    tp = ads.theo_page(*T).set_index("ma").loc["ZZ KT MỘT"]
    assert tp.chi_tieu == 7 and tp.tin_nhan == 5 and tp.pic == ads.CHUA_PHAN_CONG


def test_lead_pttb_va_danh_gia():
    ads.nhan_lead({"page": "ZZ KT MỘT", "ngay": "2026-08-01", "lead": 1, "pttb": 1, "nguoi": "zz"})
    ads.nhan_lead([{"page": "ZZ KT MỘT", "ngay": "2026-08-02", "lead": 1}])
    assert ads.nhan_lead({"page": "ZZ KT MỘT", "lead": 0, "pttb": 0})["loi"]
    tp = ads.theo_page(*T).set_index("ma").loc["ZZ KT MỘT"]
    assert (tp.lead, tp.pttb, tp.cp_pttb, tp.danh_gia) == (2, 1, 7, "Trung bình")
    assert ads.danh_gia(15, 3) == "Tốt" and ads.danh_gia(12, 1) == "Kém" and ads.danh_gia(12, 0) == "Kém"
    assert ads.danh_gia(5, 0) == "Chưa đủ số" and ads.danh_gia(0, 2) == "Chưa có chi tiêu"


def test_cp_pttb_chi_tinh_toi_ngay_da_co_chi_tieu():
    # chi tiêu về trễ 1 ngày: PTTB báo ngày chưa có chi tiêu không làm chi phí / PTTB rẻ đi
    ads.nhan_chi_tieu({"page": "ZZ KT BỐN", "camp": "Q", "ngay": "2026-08-20", "chi_tieu": 12})
    ads.nhan_lead([{"page": "ZZ KT BỐN", "ngay": "2026-08-20", "lead": 2, "pttb": 2},
                   {"page": "ZZ KT BỐN", "ngay": "2026-08-21", "lead": 2, "pttb": 2}])
    d = date(2026, 8, 20), date(2026, 8, 21)
    tp = ads.theo_page(*d).set_index("ma").loc["ZZ KT BỐN"]
    assert tp.pttb == 4 and tp.cp_pttb == 6 and tp.ty_le_chot == 100
    t = ads.tong_quan(*d)
    assert t["den_cp"] == date(2026, 8, 20) and t["pttb_chua_khop"] >= 2


def test_doi_nguoi_chay_giua_thang_va_ty_le_rieng():
    ads.nhan_chi_tieu([{"page": "ZZ KT HAI", "camp": "X", "ngay": f"2026-08-{d:02d}", "chi_tieu": 10}
                       for d in (5, 15, 25)])
    pid = _pid("ZZ KT HAI")
    ads.them_pic(pid, ["ZZ A", "ZZ B"], date(2026, 8, 1), None, "kt")
    ads.them_pic(pid, ["ZZ A", "ZZ C"], date(2026, 8, 11), date(2026, 8, 20), "kt")
    ads.them_pic(pid, ["ZZ A", "ZZ C"], date(2026, 8, 21), None, "kt", [70, 30])
    pb = ads.phan_bo(*T)
    pb = pb[pb.page_id == pid].groupby("sale").chi_tieu.sum().round(2).to_dict()
    # 05/08: A,B 5-5 · 15/08: A,C 5-5 · 25/08: A 7, C 3
    assert pb == {"ZZ A": 17.0, "ZZ B": 5.0, "ZZ C": 8.0}
    with pytest.raises(ads.LoiAds):
        ads.them_pic(pid, ["ZZ A", "ZZ B", "ZZ C", "ZZ D"], date(2026, 8, 1), None, "kt")
    with pytest.raises(ads.LoiAds, match="100%"):
        ads.them_pic(pid, ["ZZ A", "ZZ C"], date(2026, 8, 1), None, "kt", [70, 20])


def test_page_cong_ty_khong_chia_cho_sale():
    ads.nhan_chi_tieu({"page": "ZZ KT TRUNG LẬP", "camp": "TL", "ngay": "2026-08-09", "chi_tieu": 9})
    pb = ads.phan_bo(*T)
    assert set(pb[pb.page_id == _pid("ZZ KT TRUNG LẬP")].sale) == {ads.CONG_TY}


def test_ty_gia_va_ky_tu_so():
    assert ads.doc_so("1.234,5") == 1234.5 and ads.doc_so("4,93") == 4.93 and ads.doc_so(None) == 0
    assert ads.chuan_ma("  Kon   tum ") == "KON TUM" and ads.khoa_sale("C.HỒNG") == ads.khoa_sale("C. Hồng")
    ads.luu_thang("2026-08", 26000, "kt")
    assert ads.ty_gia("2026-08") == 26000


def test_chi_tiet_sale_tracking_tong_va_kiem_tra():
    ct = ads.chi_tiet_sale("ZZ A", *T)
    r = ct.set_index("ten").iloc[0]
    assert r.chi_tieu == 17 and r.so_ngay == 3 and r.cung == "ZZ B, ZZ C" and r.phan == 57
    pv, _ = ads.tracking("2026-08", "chi_tieu")
    assert pv.attrs["tong"]["5"] >= 10 and pv.attrs["tong"]["tong"] == round(float(pv.tong.sum()), 2)
    loi = ads.kiem_tra(*T, date(2026, 9, 19))
    assert all(m in ("bad", "warn", "info") for m, _ in loi)
    assert any("chưa chia cho sale" in c for _, c in loi)                     # ZZ KT MỘT chưa khai người chạy


def test_api_can_ma_ket_noi_va_trang_can_dang_nhap():
    from app.ui.app import server
    c = server.test_client()
    assert c.get("/").status_code == 302                                        # trang thường vẫn phải đăng nhập
    assert c.post("/api/ads/chi-tieu", json={"page": "ZZ KT BA"}).status_code == 401
    tok = ads.tao_token("kt")
    r = c.post("/api/ads/chi-tieu", headers={"X-Ads-Token": tok},
               json={"page": "ZZ KT BA", "rows": [{"camp": "Z", "ngay": "2026-08-10", "chi_tieu": 1.5}]})
    assert r.status_code == 200 and r.get_json()["moi"] == 1
    r = c.post("/api/ads/lead", headers={"X-Ads-Token": tok}, json={"page": "ZZ KT BA", "lead": 1})
    assert r.status_code == 200 and r.get_json()["ghi"] == 1
    assert c.post("/api/ads/lead", headers={"X-Ads-Token": "ads_sai"}, json={"page": "ZZ KT BA"}).status_code == 401


def test_bao_cao_bot_telegram():
    from app.ui.app import server
    c = server.test_client()
    assert c.get("/api/ads/bao-cao?date=01/08/2026").status_code == 401
    tok = ads.tao_token("kt")
    r = c.get("/api/ads/bao-cao?type=month&start_date=01/08/2026&end_date=31/08/2026",
              headers={"X-Ads-Token": tok}).get_json()
    assert r["ok"] and r["date"] == "01/08/2026 - 31/08/2026" and "ZZ KT MỘT: 2 leads | 1 PTTB" in r["details_text"]
    assert r["total_pttb"] >= 1 and "ineffective_pages_text" in r


def test_chi_tiet_page_nhu_trang_tinh_va_sua_page():
    pid = _pid("ZZ KT HAI")
    ct = ads.chi_tiet_page(pid, *T)
    assert [r["ngay"] for r in ct["rows"]] == ["05/08/2026", "15/08/2026", "25/08/2026"]      # ngày tăng dần
    assert ct["rows"][0]["pic1"] == "ZZ A" and ct["rows"][0]["tien_nguoi"] == "5,00"
    assert ct["rows"][2]["tien_nguoi"] == "ZZ A 7,00 · ZZ C 3,00" and ct["so_pic"] == 2
    assert dict(ct["tong_sale"]) == {"ZZ A": 17.0, "ZZ B": 5.0, "ZZ C": 8.0}
    ads.sua_page(pid, "  ZZ KT Hai  mới ", "facebook.com/zzkt", "Đang nuôi", "kt")
    p = ads.ds_page().set_index("id").loc[pid]
    assert (p.ten, p.link, p.tinh_trang) == ("ZZ KT Hai mới", "https://facebook.com/zzkt", "Đang nuôi")
    with pytest.raises(ads.LoiAds):
        ads.sua_page(pid, "", None, None, "kt")


def test_nhan_dinh_chay_duoc_va_nhom_hieu_qua():
    assert ads.nhom_hieu_qua(30, 10) == "Hiệu quả cao" and ads.nhom_hieu_qua(80, 10) == "Trung bình"
    assert ads.nhom_hieu_qua(12, 0) == "Kém" and ads.nhom_hieu_qua(5, 0) == "Chưa đủ dữ liệu"
    nd = ads.nhan_dinh(*T)
    assert {"the", "page", "xu_huong", "pheu", "chuoi"} <= set(nd)
    assert all(t["muc"] in ("bad", "warn", "info", "ok") for t in nd["the"])


def test_khong_cho_hai_page_trung_ten():
    with pytest.raises(ads.LoiAds, match="đang dùng cho page"):
        ads.sua_page(_pid("ZZ KT MỘT"), "zz kt  hai mới", None, None, "kt")        # trùng tên (khác hoa thường)
    with pytest.raises(ads.LoiAds):
        ads.luu_page([{"id": _pid("ZZ KT BA"), "ten": "ZZ KT Hai mới"}], "kt")


def test_them_page_va_sale():
    msg = ads.them_page("zz kt  năm", "ZZ KT Năm hiển thị", "sale", "facebook.com/zz5", None, "kt")
    assert "ZZ KT NĂM" in msg
    p = ads.ds_page().set_index("ma").loc["ZZ KT NĂM"]
    assert (p.ten, p.loai, p.tinh_trang, p.link) == ("ZZ KT Năm hiển thị", "sale", "Đang chạy", "https://facebook.com/zz5")
    with pytest.raises(ads.LoiAds, match="Đã có page"):
        ads.them_page("ZZ KT NĂM", None, "sale", None, None, "kt")
    with pytest.raises(ads.LoiAds, match="đang dùng cho page"):
        ads.them_page("ZZ KT SÁU", "zz kt năm hiển thị", "sale", None, None, "kt")          # trùng tên hiển thị
    assert ads.ds_page().ma.eq("ZZ KT SÁU").sum() == 0                                     # không tạo dở
    ads.them_page("ZZ KT TRUNG LẬP 9", None, "sale", None, None, "kt")
    pg = ads.ds_page()
    assert pg[pg.ma == ads.chuan_ma("ZZ KT TRUNG LẬP 9")].loai.tolist() == ["cong_ty"]
    ads.them_sale("ZZ Lan", "DNG.ZzLan", "kt")
    assert ads.ds_sale().set_index("ten").acc["ZZ Lan"] == "DNG.ZzLan"
    with pytest.raises(ads.LoiAds, match="Đã có sale"):
        ads.them_sale("zz  lan", None, "kt")
