"""Phòng Online: nhóm 5 người của IBB2 gom vào một bảng riêng cho BGĐ (chốt 07/11/2026)."""
from __future__ import annotations

import json
from datetime import date
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
    for trang in ("/taikhoan", "/huongdan", "/baocaongay", "/soanmail", "/danhba", "/giafpt"):    # báo cáo ngày + 3 công cụ (10/11/2026)
        assert online.vao_duoc(trang), trang
    for trang in ("/", "/phong", "/hr", "/phantich", "/tracking", "/upload", "/quantri", "/ads", "/nhapton", "/dvkh"):
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


# ------------------------------------------------------------------ Báo cáo ngày riêng + KHTN (10/11/2026)
def test_bao_cao_ngay_cua_nhom_rieng_voi_ibb7():
    from app import bao_cao_ngay as bc
    ds = bc.bang([bc.PHONG_ONLINE], date(2026, 9, 10))
    assert set(ds.acc_norm) <= set(po.acc_nhom()) and len(ds) >= 1 and set(ds.phong_code) == {bc.PHONG_ONLINE}
    ibb2 = bp.bang_nhan_su(THANG, 10, "IBB2")
    ibb2 = ibb2[(ibb2.loai_dong == "data") & ibb2.acc_norm.isin(po.acc_nhom())].set_index("acc_norm")
    for r in ds.itertuples():                  # PTTB luỹ kế y hệt Báo cáo phòng IBB2
        assert r.pttb_thang == ibb2.loc[r.acc_norm, "online"], r.acc_norm
    assert not set(bc.bang(["IBB7"], date(2026, 9, 10)).acc_norm) & set(po.acc_nhom())      # IBB7 không lẫn người của nhóm
    t = bc.tom_tat([bc.PHONG_ONLINE], date(2026, 9, 10))
    assert t["luy_ke"] == int(ds.pttb_thang.sum()) and t["so_nguoi"] == len(ds)


def test_khtn_luu_rieng_va_bao_cao_theo_nguoi():
    from sqlalchemy import delete, select

    from app import bao_cao_ngay as bc
    from app.db import session_scope
    from app.models import BaoCaoNgay
    ngay, acc = date(2026, 9, 10), po.acc_nhom()[0]
    bc.dam_bao_bang()
    with session_scope() as sess:
        sess.execute(delete(BaoCaoNgay).where(BaoCaoNgay.acc_norm.in_(po.acc_nhom())))
    try:
        # KHTN của nhóm giờ tự đếm từ Lead Online (`dong_bo_khtn`), không còn ghi được qua `bc.luu` (xem
        # test_khtn_tu_lead_khoa_sale_khong_go_tay_duoc) - ghi thẳng vào bảng để mô phỏng đúng cách số được
        # lưu (cron ghi đè mỗi ngày, số cuối cùng trong ngày trở thành lịch sử của ngày đó).
        with session_scope() as sess:
            sess.add(BaoCaoNgay(ngay=date(2026, 9, 9), acc_norm=acc, phong_code=bc.PHONG_ONLINE, khtn=6))
            sess.add(BaoCaoNgay(ngay=ngay, acc_norm=acc, phong_code=bc.PHONG_ONLINE, khtn=9))
        bc.luu(po.acc_nhom()[1], {"ghi_chu": "chỉ ghi chú"}, [bc.PHONG_ONLINE], "kiemthu", ngay)      # đã có báo cáo trong ngày (dù chỉ ghi chú) thì KHTN là số 0 đã nhập, như bảng Báo cáo ngày
        k = po.khtn_theo_ngay(THANG, 10).set_index("acc_norm")
        assert k.loc[acc, "hom_nay"] == 9 and k.loc[acc, "hom_qua"] == 6 and k.loc[acc, "tb"] == 7.5 and k.loc[acc, "so_ngay_nhap"] == 2
        assert k.loc[acc, "cao_nhat"] == 9 and k.loc[acc, "d09"] == 6
        assert k.loc[po.acc_nhom()[1], "so_ngay_nhap"] == 1 and k.loc[po.acc_nhom()[1], "hom_nay"] == 0
        chua = k[~k.index.isin(po.acc_nhom()[:2])]
        assert len(chua) and chua.so_ngay_nhap.eq(0).all() and chua.hom_nay.isna().all()      # người chưa có báo cáo nào: vẫn có dòng, ô trống (không ghi 0)
        with session_scope() as sess:                                           # số lưu với mã ảo, không dính IBB7
            ma = {r[0] for r in sess.execute(select(BaoCaoNgay.phong_code).where(BaoCaoNgay.acc_norm == acc))}
        assert ma == {bc.PHONG_ONLINE}
    finally:
        with session_scope() as sess:
            sess.execute(delete(BaoCaoNgay).where(BaoCaoNgay.acc_norm.in_(po.acc_nhom())))


def test_muc_tieu_thang_nhom_la_tong_muc_tieu_tung_nguoi():
    from app import bao_cao_ngay as bc
    acc = po.acc_nhom()
    bc.dat_muc_tieu(THANG, "NHAN_VIEN", acc[0], "internet", 20, "kiemthu")
    bc.dat_muc_tieu(THANG, "NHAN_VIEN", acc[1], "internet", 15, "kiemthu")
    try:
        assert bc.muc_tieu_thang(THANG, [bc.PHONG_ONLINE]) >= 35
    finally:
        from sqlalchemy import delete

        from app.db import session_scope
        from app.models import Target
        with session_scope() as sess:
            sess.execute(delete(Target).where(Target.thang == THANG, Target.doi_tuong == "NHAN_VIEN", Target.ma_doi_tuong.in_(acc[:2])))


def test_quyen_bao_cao_ngay_va_cong_cu_cua_nhom():
    online, bgd, ky_thuat, nvkd = _tk("online"), _tk("admin"), _tk("admin", username=ADMIN_USERNAME), _tk("nvkd", scope=["IBB7"])
    assert online.phong_bao_cao_ngay() == ["ONLINE"] and online.duoc_bao_cao_ngay and online.duoc_soan_mail
    assert "ONLINE" not in ky_thuat.phong_bao_cao_ngay() and "ONLINE" not in nvkd.phong_bao_cao_ngay() and "ONLINE" not in bgd.phong_bao_cao_ngay()
    assert nvkd.phong_bao_cao_ngay() == ["IBB7"]                                   # IBB7 giữ nguyên
    from app.ui.app import trang_mo_dau
    assert trang_mo_dau(online) == "/baocaongay"


# ------------------------------------------------------------------ Theo dõi Online của nhóm: cập nhật khung giờ, KHÔNG nối Nhập tồn (10/11/2026)
def test_theo_doi_online_cua_nhom_khong_noi_nhap_ton():
    from sqlalchemy import delete, func, select

    from app import bao_cao_ngay as bc
    from app import online_ca as oc
    from app import online_ton as ot
    from app.db import session_scope
    from app.models import OnlineCa, TonTheoDoi
    ngay, acc = date(2026, 9, 10), po.acc_nhom()[0]
    ph = [bc.PHONG_ONLINE]
    assert {x["a"] for x in oc.nhan_vien(tuple(ph), ngay.isoformat())} <= set(po.acc_nhom())         # chỉ người của nhóm
    assert not ot.noi_ton(ph) and ot.noi_ton(["IBB7"]) and ot._ton(ph).empty
    oc.dam_bao_bang()
    with session_scope() as sess:
        sess.execute(delete(OnlineCa).where(OnlineCa.phong_code == bc.PHONG_ONLINE))
        truoc = sess.execute(select(func.count()).select_from(TonTheoDoi)).scalar()
    try:
        ket = oc.them_nhieu("DAAAP6381 DAAAP6382", acc, oc.khung()[0]["ma"], ph, "kiemthu", ngay, ghi_chu="khách hẹn sáng")
        assert ket["them"] == ["DAAAP6381", "DAAAP6382"] and not ket["hoi"]                          # không hỏi xác nhận ngày với Nhập tồn
        ca = oc.ds_ca(ph, ngay)
        assert len(ca) == 2 and all(c["acc"] == acc and c["gc"] == "khách hẹn sáng" for c in ca)
        oc.doi_trang_thai(ca[0]["id"], "da_online", ph, "kiemthu")
        oc.doi_khung(ca[1]["id"], "chua", ph, "kiemthu")
        gd = oc.du_lieu(ph, ngay)
        assert gd["tu_ca"] is True and gd["hen"] == {} and gd["lech"] == {} and gd["ton"] == {}
        with session_scope() as sess:
            assert sess.execute(select(func.count()).select_from(TonTheoDoi)).scalar() == truoc    # không ghi gì sang Nhập tồn
        d = bc.bang(ph, ngay).set_index("acc_norm").loc[acc]                                       # ngày đã qua: người có ca thì tự đếm
        assert d.tu_ca and d.thuc_hien == 1 and d.onl_sang == 1 and d.chua_xep == 1
        assert bc.khoa_onl(acc, ph, ngay) and not bc.che_do_onl(ngay, ["IBB7"])                    # IBB7 vẫn tạm dừng, không bị ảnh hưởng
    finally:
        with session_scope() as sess:
            sess.execute(delete(OnlineCa).where(OnlineCa.phong_code == bc.PHONG_ONLINE))


# ------------------------------------------------------------------ KHTN tự đếm từ Lead Online (chốt 19/11/2026)
def test_khtn_tu_lead_khoa_sale_khong_go_tay_duoc():
    from app import bao_cao_ngay as bc
    assert bc.khtn_tu_lead_bat([bc.PHONG_ONLINE]) and not bc.khtn_tu_lead_bat(["IBB7"])
    with pytest.raises(bc.LoiBaoCao):
        bc.luu(po.acc_nhom()[0], {"khtn": 5}, [bc.PHONG_ONLINE], "kiemthu", date(2026, 9, 10))
    bc.luu("kiemthu.tp", {"khtn": 5}, ["IBB7"], "kiemthu", date(2026, 9, 10))     # IBB7 không bị khoá


def test_bang_danh_dau_khtn_tu_dong_dung_phong():
    from app import bao_cao_ngay as bc
    nhom = bc.bang([bc.PHONG_ONLINE], date(2026, 9, 10))
    ibb7 = bc.bang(["IBB7"], date(2026, 9, 10))
    assert not nhom.empty and nhom.khtn_tu_dong.all()
    assert not ibb7.empty and not ibb7.khtn_tu_dong.any()


def test_dong_bo_khtn_ghi_dung_so_lead_dang_mo():
    from sqlalchemy import delete

    from app import bao_cao_ngay as bc
    from app import leads
    from app.bo_nho import xoa as xoa_nho
    from app.db import session_scope
    from app.models import BaoCaoNgay, CrmPage, Lead
    xoa_nho()
    hom, acc = bc.hom_nay(), po.acc_nhom()
    with session_scope() as sess:
        sess.execute(delete(Lead))
        sess.execute(delete(CrmPage))
        sess.execute(delete(BaoCaoNgay).where(BaoCaoNgay.ngay == hom, BaoCaoNgay.acc_norm.in_(acc)))
    try:
        leads.them_page("Hải Phòng", None, "kiemthu")
        pid = int(leads.ds_page().iloc[0].id)
        for _ in range(2):
            leads.tao_lead({"page_id": pid, "sale_tu_van": acc[0]}, "kiemthu")
        lid = leads.tao_lead({"page_id": pid, "sale_tu_van": acc[0]}, "kiemthu")
        leads.cap_nhat_lead(lid, {"tinh_trang_xu_ly": "Đã chốt"}, "kiemthu")       # đã đóng: không tính vào KHTN
        leads.tao_lead({"page_id": pid, "sale_tu_van": acc[1]}, "kiemthu")
        n = bc.dong_bo_khtn()
        assert n == len(acc)
        with session_scope() as sess:
            rows = {r.acc_norm: r.khtn for r in sess.query(BaoCaoNgay)
                   .filter(BaoCaoNgay.ngay == hom, BaoCaoNgay.acc_norm.in_(acc)).all()}
        assert rows[acc[0]] == 2 and rows[acc[1]] == 1 and rows[acc[2]] == 0
    finally:
        with session_scope() as sess:
            sess.execute(delete(Lead))
            sess.execute(delete(CrmPage))
            sess.execute(delete(BaoCaoNgay).where(BaoCaoNgay.ngay == hom, BaoCaoNgay.acc_norm.in_(acc)))


def test_dong_bo_khtn_tat_cong_tac_thi_khong_ghi_gi(monkeypatch):
    from app import bao_cao_ngay as bc
    monkeypatch.setattr(po, "khtn_tu_lead", lambda: False)
    assert bc.dong_bo_khtn() == 0
