"""Hồ sơ chi tiết một nhân sự (ngăn chi tiết Báo cáo phòng): số liệu cộng khớp và giao diện dựng được."""
from __future__ import annotations

from app import bao_cao_phong as bp
from app import ho_so_nhan_su as hs
from app.ui.pages import phong_ho_so

THANG, NGAY, PHONG = "2026-09", 11, "IBB2"


def _nguoi(co_so: bool):
    nv = bp.bang_nhan_su(THANG, NGAY, PHONG)
    nv = nv[(nv.loai_dong == "data") & (nv.khong_xet.fillna("") == "")]
    nv = nv[(nv.online > 0) if co_so else (nv.online == 0)]
    return nv.iloc[0]


def test_ho_so_cong_khop_voi_bang_nhan_su():
    r = _nguoi(True)
    h = hs.ho_so(THANG, NGAY, PHONG, r.acc_norm)
    assert h["online"] == r.online                                         # cùng số với dòng trong bảng nhân sự
    assert int(h["tinh"].onl.sum()) == h["online"]                          # tỉnh cộng lại = online
    assert sum(g["so"] for g in h["goi"]) == h["online"]                    # gói cộng lại = online
    assert sum(t["so"] for t in h["thu"]) == h["online"]                    # thứ trong tuần cộng lại = online
    assert h["ban"] == r.ban_moi and h["ton"] == r.ton
    assert [c["chi_so"] for c in h["chat_luong"]][:2] == ["Kèm V.VIP", "Kèm Camera"] and len(h["chat_luong"]) == 6
    assert len(h["xu_huong"]) == 3 and h["xu_huong"][2]["online"] == h["online"]
    assert 0 < h["dong_gop"] <= 100 and h["ngay_co_so"] == r.so_ngay_co_so


def test_ho_so_nguoi_chua_co_so_van_dung_duoc():
    r = _nguoi(False)
    h = hs.ho_so(THANG, NGAY, PHONG, r.acc_norm)
    assert h["online"] == 0 and h["goi"] == [] and int(h["tinh"].onl.sum()) == 0
    assert h["chuoi_dai_nhat"] == NGAY                                      # cả kỳ không có số
    assert phong_ho_so.phan_ho_so(h)                                        # giao diện vẫn dựng được


def test_ho_so_dung_giao_dien():
    r = _nguoi(True)
    ui = phong_ho_so.phan_ho_so(hs.ho_so(THANG, NGAY, PHONG, r.acc_norm))
    tieu_de = [x.children for x in ui if getattr(x, "children", None) and type(x).__name__ == "H4"]
    assert {"Vị trí trong phòng", "Xu hướng 3 tháng", "Chất lượng bán so với phòng"} <= set(tieu_de)
