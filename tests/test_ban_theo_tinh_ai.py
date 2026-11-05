"""Công cụ `ban_theo_tinh` của trợ lý AI (app/tro_ly_du_lieu.py): số hợp đồng theo tỉnh, dùng đúng hàm của thẻ "Bán theo tỉnh" (phan_tich.hd_theo_tinh /
bang_tinh). Dữ liệu: database kiểm thử. Không gọi AI."""
from __future__ import annotations

import csv
import io
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import phan_tich as pt                                          # noqa: E402
from app import tro_ly as ai                                             # noqa: E402
from app import tro_ly_du_lieu as dl                                     # noqa: E402
from app.config import DATA_DIR                                          # noqa: E402

pytestmark = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(),
                                reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")
NGAY = "2026-09-10"


def _nguoi(role="admin", phong=None):
    return SimpleNamespace(username=f"kiemthu.{role}", ho_ten="K", role=role, duoc_xem_nhan_su=True,
                           phong_duoc_xem=lambda: phong, phong_nhan_su=lambda: phong)


def _bang(kq: str) -> tuple[str, list[list[str]]]:
    dau, _, thanh = kq.partition("\nTỉnh,")
    dong = list(csv.reader(io.StringIO("Tỉnh," + thanh)))
    return dau, dong[1:]


def _so_pct(o: str) -> float:
    return float(o.rstrip("%").replace(",", "."))


def test_cong_cu_co_trong_bo_cong_cu_va_noi_ro_ban_khac_online():
    ct = {c["function"]["name"]: c["function"] for c in dl.cong_cu(_nguoi())}
    f = ct["ban_theo_tinh"]
    assert set(f["parameters"]["properties"]) == {"tu", "den", "chi_so", "phong"} and f["parameters"]["required"] == ["tu", "den"]
    assert f["parameters"]["properties"]["chi_so"]["enum"] == ["online", "ban"]
    assert "HAI CHỈ SỐ KHÁC NHAU" in f["description"] and "tu = den" in f["description"]


def test_mot_ngay_tong_va_phan_tram_dung_tu_hd_theo_tinh():
    kq = dl.chay_cong_cu(_nguoi(), "ban_theo_tinh", {"tu": NGAY, "den": NGAY, "chi_so": "ban"})
    dau, dong = _bang(kq)
    assert "TẠO MỚI (bán)" in dau and "10/09/2026" in dau and "Cùng kỳ' = 09/09" in dau
    tong = int(dong[-1][1])
    assert dong[-1][0] == "TỔNG" and tong == len(pt.hd_theo_tinh(NGAY, NGAY, None, "ban")) > 0
    tinh = dong[:-1]
    assert sum(int(r[1]) for r in tinh) == tong                                        # các dòng cộng đúng bằng TỔNG
    assert abs(sum(_so_pct(r[2]) for r in tinh) - 100) <= 0.1 * len(tinh) and dong[-1][2] == "100,0%"
    so = [int(r[1]) for r in tinh if r[0] != "Khác"]
    assert so == sorted(so, reverse=True) and len(so) <= dl.TOI_DA_TINH                 # giảm dần, tối đa 12 tỉnh
    assert tinh[-1][0] == "Khác" if len(pt.hd_theo_tinh(NGAY, NGAY, None, "ban").tinh.unique()) > dl.TOI_DA_TINH else True
    top = tinh[0]
    assert _so_pct(top[2]) == round(int(top[1]) / tong * 100, 1)
    assert int(dong[-1][3]) == len(pt.hd_theo_tinh("2026-09-09", "2026-09-09", None, "ban"))   # cùng kỳ = ngày liền trước


def test_online_va_ban_la_hai_chi_so_khac_nhau():
    onl = _bang(dl.chay_cong_cu(_nguoi(), "ban_theo_tinh", {"tu": NGAY, "den": NGAY}))
    ban = _bang(dl.chay_cong_cu(_nguoi(), "ban_theo_tinh", {"tu": NGAY, "den": NGAY, "chi_so": "ban"}))
    assert "ONLINE" in onl[0] and int(onl[1][-1][1]) == len(pt.hd_theo_tinh(NGAY, NGAY, None, "online"))
    assert int(onl[1][-1][1]) != int(ban[1][-1][1])


def test_luy_ke_so_cung_ky_thang_truoc_va_khoang_so_sanh():
    dau, dong = _bang(dl.chay_cong_cu(_nguoi(), "ban_theo_tinh", {"tu": "2026-09-01", "den": "2026-09-11"}))
    assert "01/09 - 11/09/2026" in dau and "Cùng kỳ' = 01/08 - 11/08" in dau
    assert pt.khoang_so_sanh("2026-09-01", "2026-09-11") == (("2026-08-01", "2026-08-11"), True)
    assert pt.khoang_so_sanh("2026-09-10", "2026-09-10") == (("2026-09-09", "2026-09-09"), False)
    assert pt.khoang_so_sanh("2026-09-08", "2026-09-10") == (("2026-09-05", "2026-09-07"), False)
    bang = pt.bang_tinh(pt.hd_theo_tinh("2026-09-01", "2026-09-11", None, "online"), pt.hd_theo_tinh("2026-08-01", "2026-08-11", None, "online"))
    assert int(dong[-1][1]) == int(bang.online.sum()) and int(dong[-1][3]) == int(bang.ck.sum())     # đúng số của thẻ Bán theo tỉnh


def test_mot_phong_chi_tinh_hop_dong_cua_phong_do():
    dau, dong = _bang(dl.chay_cong_cu(_nguoi(), "ban_theo_tinh", {"tu": "2026-09-01", "den": "2026-09-11", "phong": "IBB5"}))
    assert "phòng: IBB5" in dau and int(dong[-1][1]) == len(pt.hd_theo_tinh("2026-09-01", "2026-09-11", ["IBB5"], "online"))


def test_phong_ngoai_quyen_bi_chan_con_trong_quyen_thi_xem_duoc():
    tp = _nguoi("phong", ["IBB2"])
    with pytest.raises(ai.LoiAI, match="không có quyền xem số của phòng này"):
        dl.chay_cong_cu(tp, "ban_theo_tinh", {"tu": NGAY, "den": NGAY, "phong": "IBB7"})
    dau, dong = _bang(dl.chay_cong_cu(tp, "ban_theo_tinh", {"tu": "2026-09-01", "den": "2026-09-11"}))     # không chọn phòng: chỉ gộp phòng được xem
    assert int(dong[-1][1]) == len(pt.hd_theo_tinh("2026-09-01", "2026-09-11", ["IBB2"], "online"))
    assert int(_bang(dl.chay_cong_cu(tp, "ban_theo_tinh", {"tu": NGAY, "den": NGAY, "phong": "IBB2"}))[1][-1][1]) >= 0
    with pytest.raises(ai.LoiAI, match="không phải mã phòng"):
        dl.chay_cong_cu(tp, "ban_theo_tinh", {"tu": NGAY, "den": NGAY, "phong": "DNG.Anhtu"})


def test_khong_co_ten_nhan_su_hay_ten_khach_trong_ket_qua():
    kq = dl.chay_cong_cu(_nguoi(), "ban_theo_tinh", {"tu": "2026-09-01", "den": "2026-09-11"})
    cot = _bang(kq)[1]
    assert all(len(r) == 4 for r in cot) and "DNG." not in kq and "ten_khach" not in kq.lower()


def test_khoang_khong_co_hop_dong_thi_bao_gon():
    kq = dl.chay_cong_cu(_nguoi(), "ban_theo_tinh", {"tu": "2026-01-01", "den": "2026-01-02"})
    assert "không có hợp đồng nào" in kq


def test_ma_phong_hieu_cach_goi_B5_phong_5_la_IBB5():
    """Chủ app 05/11/2026 hỏi "b5 hôm qua bán ở tỉnh nào": AI truyền "b5", bị báo lỗi rồi bỏ trống phòng nên ra số cả chi nhánh."""
    from app import tro_ly_du_lieu as dl
    assert [dl._ma_phong(q) for q in ("b5", "B5", "phòng 5", "ibb 5", "IBB7", "Phong 7")] == ["IBB5", "IBB5", "IBB5", "IBB5", "IBB7", "IBB7"]
