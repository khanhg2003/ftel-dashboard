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
            for bang in ("ads_ngay", "ads_lead", "ads_pic", "ads_kpi"):
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
    assert (tp.lead, tp.pttb, tp.cp_pttb, tp.danh_gia) == (2, 1, 7, "Bình thường")
    assert ads.danh_gia(5, 3) == "Tốt" and ads.danh_gia(12, 1) == "Cao" and ads.danh_gia(None, 0) == "Chưa có PTTB"


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


def test_hoach_dinh_va_ky_tu_so():
    assert ads.doc_so("1.234,5") == 1234.5 and ads.doc_so("4,93") == 4.93 and ads.doc_so(None) == 0
    assert ads.chuan_ma("  Kon   tum ") == "KON TUM" and ads.khoa_sale("C.HỒNG") == ads.khoa_sale("C. Hồng")
    ads.luu_thang("2026-08", 26000, {_pid("ZZ KT MỘT"): 5}, "kt")
    hd = ads.hoach_dinh("2026-08", date(2026, 8, 31)).set_index("ma").loc["ZZ KT MỘT"]
    assert hd.kpi == 5 and hd.ngan_sach_can == 35 and hd.khuyen_nghi == "Tối ưu camp"
    assert ads.ty_gia("2026-08") == 26000


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
