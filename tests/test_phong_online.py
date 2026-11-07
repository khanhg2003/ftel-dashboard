"""Phòng Online: nhóm 5 người của IBB2 gom vào một bảng riêng cho BGĐ (chốt 07/11/2026)."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app import bao_cao_phong as bp
from app import phong_online as po
from app.auth import ADMIN_USERNAME, SessionUser

THANG, NGAY = "2026-09", 11


def _tk(role: str, username: str | None = None, scope=()) -> SessionUser:
    return SessionUser(SimpleNamespace(id=1, username=username or f"kiemthu.{role}", ho_ten="K", role=role, ma_nv=None,
                                       session_version=0, scope=json.dumps(list(scope))))


def test_nhom_gom_dung_5_nguoi_cua_ibb2():
    assert po.phong_goc() == "IBB2"
    assert sorted(po.acc_nhom()) == ["dng.haoctp2", "dng.hieunt310", "dng.mottm", "dng.thutu", "dng.vannhk"]
    assert po.la_nguoi_online("DNG.MoTTM") and not po.la_nguoi_online("dng.longph") and not po.la_nguoi_online(None)


def test_bang_chi_giu_nguoi_trong_nhom_va_khop_ibb2():
    nhom = po.bang_nhan_su(THANG, NGAY)
    nguoi = nhom[nhom.loai_dong == "data"]
    assert set(nguoi.acc_norm) <= set(po.acc_nhom())
    ibb2 = bp.bang_nhan_su(THANG, NGAY, "IBB2")
    ibb2 = ibb2[(ibb2.loai_dong == "data") & ibb2.acc_norm.isin(po.acc_nhom())].set_index("acc_norm")
    for r in nguoi.itertuples():         # số từng người y hệt Báo cáo phòng IBB2
        for cot in ("online", "ck_online", "vvip", "camera", "ban_moi", "ton"):
            assert getattr(r, cot) == ibb2.loc[r.acc_norm, cot], (r.acc_norm, cot)
    tong = nhom[nhom.loai_dong == "total"].iloc[0]
    assert tong.ho_ten == "TỔNG PHÒNG ONLINE" and tong.online == nguoi.online.sum() and tong.vvip == nguoi.vvip.sum()
    assert sorted(nguoi.hang.dropna()) == sorted(nguoi.online.rank(method="min", ascending=False).astype(int))   # hạng trong riêng nhóm


def test_ibb2_khong_bi_doi():
    day_du = bp.bang_nhan_su(THANG, NGAY, "IBB2")
    assert len(day_du[day_du.loai_dong == "data"]) > len(po.acc_nhom())          # vẫn còn đủ người ngoài nhóm
    assert bp.bang_nhan_su(THANG, NGAY, "IBB2", acc=None).equals(day_du)


def test_so_theo_ngay_cong_dung_tong():
    for cong_don in (False, True):
        df = po.so_theo_ngay(THANG, NGAY, "online", cong_don=cong_don)
        nguoi, tong = df[df.loai_dong == "data"], df[df.loai_dong == "subtotal"].iloc[0]
        assert set(nguoi.acc_norm) <= set(po.acc_nhom())
        assert tong["Tổng"] == nguoi["Tổng"].sum() and tong[str(NGAY)] == nguoi[str(NGAY)].sum()


def test_quyen_xem_trang():
    bgd = _tk("admin")                                    # BGĐ
    ky_thuat = _tk("admin", username=ADMIN_USERNAME)      # tài khoản kỹ thuật: KHÔNG xem
    online = _tk("online")
    assert bgd.duoc_xem_phong_online and bgd.vao_duoc("/phongonline")
    assert not ky_thuat.duoc_xem_phong_online and not ky_thuat.vao_duoc("/phongonline")
    assert online.duoc_xem_phong_online and online.vao_duoc("/phongonline")
    for vai in ("operator", "phong", "nvkd", "dvkh"):
        assert not _tk(vai, scope=["IBB2"]).vao_duoc("/phongonline"), vai


def test_tai_khoan_online_chi_vao_dung_trang():
    online = _tk("online")
    assert online.vao_duoc("/taikhoan") and online.vao_duoc("/huongdan")
    for trang in ("/", "/phong", "/hr", "/phantich", "/tracking", "/upload", "/quantri", "/ads", "/baocaongay", "/dvkh"):
        assert not online.vao_duoc(trang), trang
    assert online.phong_duoc_xem() == [] and online.phong_nhan_su() == []     # không có số chung / nhân sự nào khác
    assert not online.duoc_cau_hinh and not online.duoc_upload and not online.duoc_xem_nhan_su


def test_tao_duoc_tai_khoan_vai_tro_online():
    from app.admin_service import ROLE_TEN, ROLES
    assert ("online", "Phòng Online") in ROLES and ROLE_TEN["online"] == "Phòng Online"


@pytest.mark.parametrize("acc,duoc", [("dng.mottm", True), ("dng.longph", False)])
def test_ngan_nhan_su_chi_mo_nguoi_trong_nhom(monkeypatch, acc, duoc):
    from app.ui import ngan_nhan_su as ns
    monkeypatch.setattr(ns, "current_user", _tk("online"))
    monkeypatch.setattr(ns, "_ngan_noi_dung", lambda thang, ngay, code, r: ("mo", code))   # chỉ kiểm cổng quyền, không dựng ngăn thật
    tieu_de, _ = ns.noi_dung(acc, [None], f"{THANG}-{NGAY:02d}")
    assert (tieu_de == "mo") == duoc if isinstance(tieu_de, str) else not duoc
