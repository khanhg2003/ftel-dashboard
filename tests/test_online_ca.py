"""Kiểm thử Theo dõi Online trong ngày (chốt với chủ app 12/10/2026): phiếu theo mã HĐ, khung giờ, nối với bảng Báo cáo ngày."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import bao_cao_ngay as bc                                      # noqa: E402
from app import online_ca as oc                                         # noqa: E402
from app.config import DATA_DIR                                          # noqa: E402

pytestmark = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(),
                                reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")
NGAY = date(2026, 9, 10)          # nằm trong kỳ dữ liệu gốc 01-11/09/2026
PHONG = ["IBB7"]


_HEN_THAT = None


@pytest.fixture(autouse=True)
def _khong_hen_tu_nhap_ton(monkeypatch):
    """Database kiểm thử có sẵn mốc hẹn thật ở Nhập tồn; các phép thử cũ không muốn bị nhắc thêm ca hẹn nên tắt đi, riêng phép thử liên kết bật lại bằng `hen_that`."""
    from app import online_ton as ot
    global _HEN_THAT
    _HEN_THAT = _HEN_THAT or ot.hen_cho_ngay
    monkeypatch.setattr(ot, "hen_cho_ngay", lambda *a, **k: {})


@pytest.fixture()
def hen_that(monkeypatch):
    from app import online_ton as ot
    monkeypatch.setattr(ot, "hen_cho_ngay", _HEN_THAT)


@pytest.fixture(autouse=True)
def _don():
    """Xoá phiếu và báo cáo của ngày kiểm thử trước / sau mỗi phép thử (database kiểm thử dùng lại qua nhiều lần chạy)."""
    from sqlalchemy import delete

    from app.db import session_scope
    from app.models import BaoCaoNgay, OnlineCa

    def don():
        with session_scope() as s:
            ngay_don = [NGAY + timedelta(days=i) for i in range(4)]            # ca dời sang +2 / +3 ngày cũng phải sạch
            s.execute(delete(OnlineCa).where(OnlineCa.ngay.in_(ngay_don)))
            s.execute(delete(BaoCaoNgay).where(BaoCaoNgay.ngay.in_(ngay_don)))
    bc.dam_bao_bang()
    oc.dam_bao_bang()
    don()
    yield
    don()


@pytest.fixture()
def hai_nguoi():
    nv = oc.nhan_vien(tuple(PHONG), NGAY.isoformat())
    assert len(nv) >= 2, "phòng IBB7 phải có ít nhất hai nhân sự trong kỳ kiểm thử"
    return nv[0]["a"], nv[1]["a"]


def test_them_ca_chuan_hoa_ma_va_chan_trung(hai_nguoi):
    a, _ = hai_nguoi
    oc.them(" daaap-6381 ", a, "08-10", PHONG, "kiemthu", NGAY)
    ca = oc.ds_ca(PHONG, NGAY)
    assert [(c["ma"], c["khung"], c["tt"], c["acc"]) for c in ca] == [("DAAAP6381", "08-10", "du_kien", a)]
    assert ca[0]["ls"][0]["viec"].startswith("Tạo ca")
    with pytest.raises(oc.LoiOnline, match="đã có"):
        oc.them("DAAAP6381", a, "10-12", PHONG, "kiemthu", NGAY)
    with pytest.raises(oc.LoiOnline, match="Mã hợp đồng"):
        oc.them("ab", a, "10-12", PHONG, "kiemthu", NGAY)
    with pytest.raises(oc.LoiOnline, match="khung giờ"):
        oc.them("DAAAP0001", a, "khong-co", PHONG, "kiemthu", NGAY)
    with pytest.raises(oc.LoiOnline, match="nhân viên"):
        oc.them("DAAAP0002", "khong.co.nguoi", "08-10", PHONG, "kiemthu", NGAY)


def test_ca_sap_theo_khung_gio_va_thong_ke(hai_nguoi):
    a, b = hai_nguoi
    oc.them("DAAAP0001", a, "1330-1530", PHONG, "k", NGAY)
    oc.them("DAAAP0002", a, "08-10", PHONG, "k", NGAY)
    oc.them("DAAAP0003", b, "08-10", PHONG, "k", NGAY)
    ca = oc.ds_ca(PHONG, NGAY)
    assert [c["ma"] for c in ca] == ["DAAAP0002", "DAAAP0003", "DAAAP0001"]          # theo khung giờ rồi theo thứ tự tạo
    oc.doi_trang_thai(ca[0]["id"], "da_online", PHONG, "k")
    oc.doi_trang_thai(ca[1]["id"], "dang_lam", PHONG, "k")
    tk = oc.thong_ke(oc.ds_ca(PHONG, NGAY))
    assert (tk["tong"], tk["cho"], tk["dang"], tk["online"]) == (3, 1, 1, 1)
    assert tk["khung"]["08-10"] == {"tong": 2, "cho": 0, "dang": 1, "online": 1}
    assert tk["khung"]["10-12"]["tong"] == 0 and tk["nv"][a]["tong"] == 2 and tk["nv"][b]["dang"] == 1


def test_doi_trang_thai_va_doi_khung_ghi_lich_su(hai_nguoi):
    a, _ = hai_nguoi
    i = oc.them("DAAAP0001", a, "08-10", PHONG, "k", NGAY)
    oc.doi_khung(i, "10-12", PHONG, "Rin")
    oc.doi_trang_thai(i, "dang_lam", PHONG, "Rin")
    oc.doi_trang_thai(i, "dang_lam", PHONG, "Rin")                                  # không đổi: không ghi thêm
    c = oc.ds_ca(PHONG, NGAY)[0]
    assert (c["khung"], c["tt"]) == ("10-12", "dang_lam")
    assert [x["viec"] for x in c["ls"][1:]] == ["Dời khung 08h–10h → 10h–12h", "Dự kiến → Đang triển khai"]
    assert all(x["ai"] == "Rin" for x in c["ls"][1:])
    with pytest.raises(oc.LoiOnline):
        oc.doi_trang_thai(i, "bay_mau", PHONG, "k")


def test_sua_ghi_chu_khong_co_doi_nguoi_phu_trach(hai_nguoi):
    """Chủ app (12/10/2026): mỗi HĐ gắn đúng người bán, không có chuyện chuyển HĐ nên chỉ sửa được ghi chú."""
    a, _ = hai_nguoi
    i = oc.them("DAAAP0001", a, "08-10", PHONG, "k", NGAY)
    oc.sua_ghi_chu(i, "  khách quen ", PHONG, "k")
    c = oc.ds_ca(PHONG, NGAY)[0]
    assert c["acc"] == a and c["gc"] == "khách quen" and not hasattr(oc, "sua")
    oc.sua_ghi_chu(i, "   ", PHONG, "k")
    assert oc.ds_ca(PHONG, NGAY)[0]["gc"] == ""
    with pytest.raises(oc.LoiOnline, match="Không tìm thấy"):
        oc.sua_ghi_chu(i, "x", ["IBB2"], "k")


def test_doi_ngay_chon_khung_gio_cho_ngay_moi_va_giu_ghi_chu(hai_nguoi):
    """Dời sang ngày khác thì chọn luôn khung giờ của ngày đó (chủ app 13/10/2026); bỏ trống thì "Chưa hẹn giờ". Ghi chú luôn giữ nguyên."""
    a, _ = hai_nguoi
    i = oc.them("DAAAP0001", a, "08-10", PHONG, "k", NGAY, ghi_chu="gọi trước")
    j = oc.them("DAAAP0002", a, "08-10", PHONG, "k", NGAY)
    moi = oc.doi_ngay(i, PHONG, "k", NGAY + timedelta(days=2), "1330-1530")
    c = oc.ds_ca(PHONG, moi)[0]
    assert (c["khung"], c["gc"]) == ("1330-1530", "gọi trước")
    moi2 = oc.doi_ngay(j, PHONG, "k", NGAY + timedelta(days=1))
    assert oc.ds_ca(PHONG, moi2)[0]["khung"] == "chua"
    with pytest.raises(oc.LoiOnline):
        oc.doi_ngay(oc.them("DAAAP0004", a, "08-10", PHONG, "k", NGAY), PHONG, "k", NGAY + timedelta(days=1), "khong-co")


def test_doi_sang_ngay_mai_ve_du_kien_chua_hen_gio_va_tinh_lai_hai_ngay(hai_nguoi):
    a, _ = hai_nguoi
    i = oc.them("DAAAP0001", a, "08-10", PHONG, "k", NGAY)
    oc.doi_trang_thai(i, "dang_lam", PHONG, "k")
    mai = oc.doi_ngay(i, PHONG, "k")
    assert mai == NGAY + timedelta(days=1) and oc.ds_ca(PHONG, NGAY) == []
    c = oc.ds_ca(PHONG, mai)[0]
    assert (c["khung"], c["tt"]) == ("chua", "du_kien") and "Dời sang ngày 11/09" in c["ls"][-1]["viec"]
    assert bc.bang(PHONG, NGAY).set_index("acc_norm").loc[a].onl_sang == 0
    with pytest.raises(oc.LoiOnline, match="dời sang ngày mai"):                   # mã đã dời đi thì không thêm lại ở hôm nay
        oc.them("DAAAP0001", a, "08-10", PHONG, "k", NGAY)
    oc.them("DAAAP0002", a, "08-10", PHONG, "k", mai)                              # mã trùng sẵn ở ngày mai thì không dời được
    j = oc.them("DAAAP0002", a, "08-10", PHONG, "k", NGAY)
    with pytest.raises(oc.LoiOnline, match="đã có"):
        oc.doi_ngay(j, PHONG, "k")


def test_dan_nhieu_ma_mot_lan_bo_qua_ma_trung_va_ma_sai(hai_nguoi):
    a, _ = hai_nguoi
    assert oc.tach_ma("daaap1001, DAAAP1002;daaap-1001  xx\nDAAAP1003") == (["DAAAP1001", "DAAAP1002", "DAAAP1003"], ["xx"])
    oc.them("DAAAP1002", a, "08-10", PHONG, "k", NGAY)
    kq = oc.them_nhieu("DAAAP1001 DAAAP1002 DAAAP1003 xx", a, "10-12", PHONG, "k", NGAY)
    assert kq["them"] == ["DAAAP1001", "DAAAP1003"]
    assert ("DAAAP1002", "đã có trong ngày") in kq["bo_qua"] and ("xx", "mã không hợp lệ") in kq["bo_qua"]
    assert [c["khung"] for c in oc.ds_ca(PHONG, NGAY)] == ["08-10", "10-12", "10-12"]
    with pytest.raises(oc.LoiOnline):                                               # toàn mã đã có: báo lỗi chứ không im lặng
        oc.them_nhieu("DAAAP1001", a, "10-12", PHONG, "k", NGAY)


def test_doi_nhieu_ca_mot_lan_sang_khung_khac_hoac_sang_mai(hai_nguoi):
    a, _ = hai_nguoi
    ids = [oc.them(f"DAAAP200{i}", a, "08-10", PHONG, "k", NGAY) for i in range(3)]
    kq = oc.doi_nhieu(ids[:2], "khung", "1530-1730", PHONG, "k")
    assert kq == {"xong": 2, "loi": []} and [c["khung"] for c in oc.ds_ca(PHONG, NGAY)] == ["08-10", "1530-1730", "1530-1730"]
    kq = oc.doi_nhieu(ids[1:], "mai", "", PHONG, "k")
    assert kq["xong"] == 2 and len(oc.ds_ca(PHONG, NGAY)) == 1 and len(oc.ds_ca(PHONG, NGAY + timedelta(days=1))) == 2
    assert [c["doi"] for c in oc.ds_ca(PHONG, NGAY + timedelta(days=1))] == [2, 1]      # ca dời khung rồi dời mai: 2 lần; ca chỉ dời mai: 1


def test_online_luc_va_khung_dau_de_tinh_dung_hen(hai_nguoi):
    from sqlalchemy import select

    from app.db import session_scope
    from app.models import OnlineCa
    a, _ = hai_nguoi
    i = oc.them("DAAAP0001", a, "08-10", PHONG, "k", NGAY)
    oc.doi_khung(i, "10-12", PHONG, "k")
    oc.doi_trang_thai(i, "da_online", PHONG, "k")
    with session_scope() as s:
        r = s.get(OnlineCa, i)
        assert (r.khung, r.khung_dau) == ("10-12", "08-10") and r.online_luc is not None
    oc.doi_trang_thai(i, "dang_lam", PHONG, "k")
    with session_scope() as s:
        assert s.get(OnlineCa, i).online_luc is None


def test_ton_cua_chi_goi_y_hd_chua_co_ca_trong_ngay(hai_nguoi):
    a, b = hai_nguoi
    from app import phan_tich as pt
    ton = pt.hop_dong_ton(PHONG)
    acc = ton.acc_norm.value_counts().index[0]
    ds = oc.ton_cua(acc, PHONG, NGAY)
    assert ds and all(set(x) == {"ma", "ton", "goi"} for x in ds) and ds == sorted(ds, key=lambda x: -x["ton"])
    nv = {x["a"] for x in oc.nhan_vien(tuple(PHONG), NGAY.isoformat())}
    if acc in nv:
        oc.them(ds[0]["ma"], acc, "08-10", PHONG, "k", NGAY)
        assert ds[0]["ma"] not in {x["ma"] for x in oc.ton_cua(acc, PHONG, NGAY)}
    assert oc.ton_cua("", PHONG, NGAY) == [] and oc.ton_cua(a, ["IBB2"], NGAY) is not None
    tat = oc.ton_tat_ca(PHONG, NGAY)                                                # gói cả phòng gửi cùng dữ liệu để chọn mã ngay trong cột
    assert acc in tat and oc.du_lieu(PHONG, NGAY)["ton"].keys() == tat.keys()


def test_huy_ca_chua_hen_gio_khong_dung_toi_o_onl(hai_nguoi):
    a, _ = hai_nguoi
    bc.luu(a, {"onl_sang": 1, "onl_chieu": 1}, PHONG, "k", NGAY)
    i = oc.them("DAAAP0001", a, "chua", PHONG, "k", NGAY)
    oc.xoa(i, PHONG, "k")
    r = bc.bang(PHONG, NGAY).set_index("acc_norm").loc[a]
    assert (r.onl_sang, r.onl_chieu) == (1, 1)


def test_moc_doi_khi_co_nguoi_sua(hai_nguoi):
    a, _ = hai_nguoi
    m0 = oc.moc(PHONG, NGAY)
    i = oc.them("DAAAP0001", a, "08-10", PHONG, "k", NGAY)
    m1 = oc.moc(PHONG, NGAY)
    oc.xoa(i, PHONG, "k")
    assert m0 != m1 != oc.moc(PHONG, NGAY)                                          # thêm rồi xoá đều làm dấu vết đổi


def test_khong_sua_duoc_ca_cua_phong_khac(hai_nguoi):
    a, _ = hai_nguoi
    i = oc.them("DAAAP0001", a, "08-10", PHONG, "k", NGAY)
    with pytest.raises(oc.LoiOnline, match="Không tìm thấy"):
        oc.doi_trang_thai(i, "da_online", ["IBB2"], "k")
    with pytest.raises(oc.LoiOnline, match="Không tìm thấy"):
        oc.xoa(i, ["IBB2"], "k")


def test_khung_phu_chi_hien_khi_co_ca():
    phu = {k["ma"] for k in oc.khung() if k["phu"]}
    assert phu == {"sau", "chua"}


def test_khung_doc_tu_cau_hinh_co_sau_khung_va_chua_hen():
    ma = [k["ma"] for k in oc.khung()]
    assert ma == ["08-10", "10-12", "1330-1530", "1530-1730", "sau", "chua"]
    assert {k["ma"]: k["buoi"] for k in oc.khung()} == {"08-10": "sang", "10-12": "sang", "1330-1530": "chieu",
                                                         "1530-1730": "chieu", "sau": "chieu", "chua": ""}


# ------------------------------------------------------------------ phần vẽ trên trình duyệt (assets/online.js)
DK = {"x": 4, "z": 2, "k": 0}
HEN = {"w": 2, "x": 1}


def test_ban_tinh_thong_ke_tren_trinh_duyet_khop_ban_python():
    node = shutil.which("node")
    if not node:
        pytest.skip("Máy không có Node")
    ca = [{"id": 1, "ma": "A", "acc": "x", "khung": "08-10", "tt": "da_online"}, {"id": 2, "ma": "B", "acc": "x", "khung": "08-10", "tt": "dang_lam"},
          {"id": 3, "ma": "C", "acc": "y", "khung": "chua", "tt": "du_kien"}, {"id": 4, "ma": "D", "acc": "y", "khung": "sau", "tt": "du_kien"}]
    code = ("const m=require(process.argv[1]);let d='';process.stdin.on('data',c=>d+=c).on('end',()=>{"
            "const j=JSON.parse(d);console.log(JSON.stringify({tk:m.thongKe(j.ca,j.khung)}));});")
    js = Path(__file__).resolve().parent.parent / "assets" / "online.js"
    kq = json.loads(subprocess.run([node, "-e", code, str(js)], input=json.dumps({"ca": ca, "khung": oc.khung()}), capture_output=True,
                                   text=True, encoding="utf-8", check=True).stdout)
    assert kq["tk"] == oc.thong_ke(ca)


def test_trang_bao_cao_ngay_co_muc_theo_doi_online_va_khong_trung_id():
    from flask_login import login_user

    from app.auth import SessionUser
    from app.ui.app import server
    from app.ui.pages import baocaongay
    from types import SimpleNamespace
    ad = SessionUser(SimpleNamespace(id=1, username="kiemthu.nvkd", ho_ten="K", role="nvkd", ma_nv=None, session_version=0,
                                     scope='["IBB7"]'))
    with server.test_request_context("/"):
        login_user(ad)

        def ids(n):
            kq, dung = [], [n]
            while dung:
                x = dung.pop()
                if isinstance(x, (list, tuple)):
                    dung.extend(x)
                    continue
                i = getattr(x, "id", None)
                if i is not None:
                    kq.append(str(sorted(i.items())) if isinstance(i, dict) else i)
                dung.extend([c for c in [getattr(x, "children", None)] if c is not None])
            return kq
        tat = ids(baocaongay.layout())
        assert not {i for i in tat if tat.count(i) > 1}
        assert {"onl-du-lieu", "onl-sk", "onl-hero", "onl-xuly", "onl-bang", "onl-md", "onl-hq", "bn-tien-do"} <= set(tat)


# ------------------------------------------------------------------ tỷ lệ đúng hẹn + xu hướng
def _ca_gia(tt, khung_dau, luc_vn=None, ngay=NGAY, khung=None):
    """Ca giả để thử `ket_qua`: luc_vn là giờ Việt Nam lúc bấm Đã online (đổi sang UTC như database)."""
    from datetime import datetime
    return {"ngay": ngay, "tt": tt, "khung": khung or khung_dau, "khung_dau": khung_dau,
            "online_luc": (luc_vn - timedelta(hours=7)) if luc_vn else None}


def test_ket_qua_dung_hen_tre_chua_len_cho_va_khong_hen():
    from datetime import datetime

    from app import online_ca_phan_tich as pa
    hn = date(2026, 10, 12)
    at = lambda h, m, d=hn: datetime(d.year, d.month, d.day, h, m)           # noqa: E731
    assert pa.ket_qua(_ca_gia("da_online", "08-10", at(9, 59), hn), hn, 600) == "dung"          # còn trong hạn 10h
    assert pa.ket_qua(_ca_gia("da_online", "08-10", at(10, 5), hn), hn, 700) == "tre"           # muộn hơn hạn
    assert pa.ket_qua(_ca_gia("da_online", "08-10", at(9, 0, date(2026, 10, 13)), hn), hn, 700) == "tre"   # online sang ngày khác
    assert pa.ket_qua(_ca_gia("da_online", "08-10", at(11, 0), hn, khung="10-12"), hn, 700) == "tre"        # dời khung rồi mới online: xét hẹn ban đầu
    assert pa.ket_qua(_ca_gia("dang_lam", "08-10", ngay=hn), hn, 601) == "chua_len"             # hôm nay quá hạn mà chưa online
    assert pa.ket_qua(_ca_gia("dang_lam", "1330-1530", ngay=hn), hn, 600) == "cho"            # chưa tới hạn: chưa tính
    assert pa.ket_qua(_ca_gia("du_kien", "08-10", ngay=hn - timedelta(days=1)), hn, 0) == "chua_len"        # ngày đã qua
    assert pa.ket_qua(_ca_gia("doi_mai", "08-10", ngay=hn), hn, 0) == "doi"                    # đã dời ngày: tách riêng, vẫn không tính là đúng hẹn
    assert pa.ket_qua(_ca_gia("da_online", "chua", at(9, 0), hn), hn, 700) == "khong_hen"       # chưa hẹn giờ: không có hẹn để so


def test_hieu_qua_theo_nhan_vien_va_khung_hen(hai_nguoi):
    from datetime import datetime

    from sqlalchemy import update

    from app import online_ca_phan_tich as pa
    from app.db import session_scope
    from app.models import OnlineCa
    a, b = hai_nguoi
    ids = [oc.them("DAAAP3001", a, "08-10", PHONG, "k", NGAY), oc.them("DAAAP3002", a, "08-10", PHONG, "k", NGAY),
           oc.them("DAAAP3003", b, "10-12", PHONG, "k", NGAY), oc.them("DAAAP3004", b, "chua", PHONG, "k", NGAY)]
    for i in ids[:3]:
        oc.doi_trang_thai(i, "da_online", PHONG, "k")
    with session_scope() as s:                                                     # giờ bấm: ca 1 đúng hạn, ca 3 muộn
        s.execute(update(OnlineCa).where(OnlineCa.id == ids[0]).values(online_luc=datetime(2026, 9, 10, 2, 30)))     # 09:30 VN
        s.execute(update(OnlineCa).where(OnlineCa.id == ids[2]).values(online_luc=datetime(2026, 9, 10, 6, 0)))      # 13:00 VN, hẹn 10-12
    r = pa.hieu_qua(PHONG, NGAY, NGAY, now=0)
    nv = {x["acc"]: x for x in r["nv"]}
    assert nv[a]["ca"] == 2
    assert nv[a]["dung"] == 1 and nv[a]["tre"] == 1                                # ca 2 online lúc thật (khác ngày): muộn
    assert nv[b]["tre"] == 1 and nv[b]["khong_hen"] == 1 and nv[b]["ty_le"] == 0
    kh = {k["ma"]: k for k in r["khung"]}
    assert kh["08-10"]["ca"] == 2 and kh["10-12"]["ca"] == 1 and kh["chua"]["ca"] == 1 and "1330-1530" not in kh
    assert r["tong"]["ca"] == 4 and r["tong"]["ty_le"] == 33
    assert pa.khoang("7", date(2026, 10, 12)) == (date(2026, 10, 6), date(2026, 10, 12))
    assert pa.khoang("thang", date(2026, 10, 12)) == (date(2026, 10, 1), date(2026, 10, 12))


def test_phan_tich_hieu_qua_tach_ca_doi_so_sanh_ky_truoc_va_nhan_dinh(hai_nguoi):
    """Chủ app 13/10/2026: phân tích hiệu quả chi tiết cả phòng và từng người (đúng hẹn, dời ngày, trễ, so với khoảng trước, nhận định)."""
    from datetime import datetime

    from sqlalchemy import update

    from app import online_ca_phan_tich as pa
    from app.db import session_scope
    from app.models import OnlineCa
    a, b = hai_nguoi
    ids = [oc.them(f"DAAAP80{i}", a, "08-10", PHONG, "k", NGAY) for i in range(1, 5)] + [oc.them("DAAAP8099", b, "08-10", PHONG, "k", NGAY)]
    for i in ids[:2]:
        oc.doi_trang_thai(i, "da_online", PHONG, "k")
    with session_scope() as s:
        s.execute(update(OnlineCa).where(OnlineCa.id == ids[0]).values(online_luc=datetime(2026, 9, 10, 2, 30)))     # 09:30 VN: đúng hạn 10h
        s.execute(update(OnlineCa).where(OnlineCa.id == ids[1]).values(online_luc=datetime(2026, 9, 10, 3, 30)))     # 10:30 VN: muộn 30 phút
    oc.doi_ngay(ids[2], PHONG, "k", NGAY + timedelta(days=1))
    oc.doi_ngay(oc.ds_ca(PHONG, NGAY + timedelta(days=1))[0]["id"], PHONG, "k", NGAY + timedelta(days=2))
    r = pa.hieu_qua(PHONG, NGAY, NGAY, now=0)
    t = r["tong"]
    assert (t["dung"], t["tre"], t["doi"], t["chua_len"]) == (1, 1, 1, 2) and t["xet"] == 5 and t["ty_le"] == 20
    assert t["tre_tb"] == 30 and t["ty_doi"] == 20
    na = next(x for x in r["nv"] if x["acc"] == a)
    assert (na["ca"], na["doi"], na["chua_len"]) == (4, 1, 1) and pa.danh_gia(na["ty_le"], na["xet"]) == ("xau", "Cần hỗ trợ")
    assert pa.danh_gia(80, 2)[0] == "it" and pa.danh_gia(85, 4)[0] == "tot" and pa.danh_gia(60, 4)[0] == "luu_y"
    rieng = pa.hieu_qua(PHONG, NGAY, NGAY, now=0, acc=b)                           # lọc một người
    assert rieng["tong"]["ca"] == 1 and [x["acc"] for x in rieng["nv"]] == [b]
    assert [d["ngay"] for d in r["ngay"]] == [NGAY]
    ca_dung = next(c for c in r["ca"] if c["ma"] == "DAAAP8099")
    assert ca_dung["kq"] == "chua_len" and ca_dung["so_doi"] == 0
    chuoi_doi = next(c for c in pa.hieu_qua(PHONG, NGAY + timedelta(days=2), NGAY + timedelta(days=2), now=0)["ca"] if c["ma"] == "DAAAP803")
    assert chuoi_doi["so_doi"] == 2                                                # dời hai lần liên tiếp
    assert pa.ky_truoc(date(2026, 10, 8), date(2026, 10, 14)) == (date(2026, 10, 1), date(2026, 10, 7))
    xh = pa.xu_huong(PHONG, NGAY, NGAY)
    nd = pa.nhan_dinh_phong(r, pa.hieu_qua(PHONG, NGAY - timedelta(days=1), NGAY - timedelta(days=1), now=0), xh)
    assert nd and nd[0][0] == "xau" and "1/5" in nd[0][1] and any("bị dời" in c for _, c in nd)
    nd_nv = pa.nhan_dinh_nv({**na, "ten": "A"}, pa.hieu_qua(PHONG, NGAY, NGAY, now=0, acc=a), t, pa.xu_huong(PHONG, NGAY, NGAY, a))
    assert nd_nv[0][0] == "xau" and any("quá hạn mà chưa online" in c for _, c in nd_nv)


def test_xu_huong_gom_so_bao_cao_ngay_theo_ngay_va_theo_nguoi(hai_nguoi):
    from app import online_ca_phan_tich as pa
    a, b = hai_nguoi
    bc.luu(a, {"muc_tieu": 3, "da_ban": 2, "onl_sang": 2, "onl_chieu": 1, "da_online": 2}, PHONG, "k", NGAY)
    bc.luu(b, {"muc_tieu": 1, "da_ban": 1, "onl_sang": 1, "da_online": 1}, PHONG, "k", NGAY)
    x = pa.xu_huong(PHONG, NGAY, NGAY)
    assert x["ngay"] == [{"ngay": NGAY, "mt": 4, "ban": 3, "dk": 4, "onl": 3, "nguoi": 2}] and x["tu_ngay_co"] == NGAY
    nv = {r["acc"]: r for r in x["nv"]}
    assert (nv[a]["mt"], nv[a]["ban"], nv[a]["dk"], nv[a]["onl"], nv[a]["so_ngay"]) == (3, 2, 3, 2, 1)
    assert pa.xu_huong(PHONG, NGAY + timedelta(days=30), NGAY + timedelta(days=31)) == {"ngay": [], "nv": [], "tong": dict(mt=0, ban=0, dk=0, onl=0), "tu_ngay_co": None}
    assert pa.xu_huong(PHONG, NGAY, NGAY, acc=a)["tong"] == dict(mt=3, ban=2, dk=3, onl=2)                   # lọc riêng một người


def test_cua_so_hieu_qua_va_thanh_tien_do_nhap_dung_duoc(hai_nguoi, monkeypatch):
    from app import online_ca_phan_tich as pa
    from app.ui.pages import baocaongay, baocaongay_hq
    monkeypatch.setattr(pa, "khoang", lambda ky, hom=None: (NGAY, NGAY))                  # dữ liệu thử nằm ở ngày kiểm thử, không phải hôm nay
    a, b = hai_nguoi
    oc.them("DAAAP5001", a, "08-10", PHONG, "k", NGAY)
    bc.luu(a, {"onl_sang": 1, "muc_tieu": 2}, PHONG, "k", NGAY)
    ndung = baocaongay_hq.noi_dung(PHONG, "hn")
    assert ndung and ndung[0].className == "hq-dau"
    assert baocaongay_hq.noi_dung(PHONG, "hn", a)[0].className == "hq-nv-dau"                  # bấm một người: xem chi tiết
    df = bc.bang(PHONG, NGAY)
    td = baocaongay._tien_do(df, bc.hom_nay())                                    # hôm nay: có thanh, bấm tên nhảy tới dòng
    assert td is not None and td.className in ("bn-td", "bn-td xong")
    assert baocaongay._tien_do(df, bc.hom_nay() - timedelta(days=1)) is None      # ngày đã qua: không nhắc
    assert baocaongay._tien_do(df.iloc[0:0], bc.hom_nay()) is None


def test_doi_sang_ngay_tuy_chon_trong_gioi_han_nhap_truoc(hai_nguoi):
    """Chủ app (12/10/2026): không chỉ dời sang ngày mai mà chọn được ngày khác (ngày mốt, tuần sau), tối đa tới ngày xa nhất Báo cáo ngày cho nhập trước."""
    a, _ = hai_nguoi
    i = oc.them("DAAAP6001", a, "08-10", PHONG, "k", NGAY)
    xa = bc.ngay_xa_nhat()
    with pytest.raises(oc.LoiOnline, match="khác ngày hiện tại"):
        oc.doi_ngay(i, PHONG, "k", NGAY)                                          # không dời về chính ngày đó
    with pytest.raises(oc.LoiOnline, match="Ngày không hợp lệ"):
        oc.doi_ngay(i, PHONG, "k", "abc")
    with pytest.raises(oc.LoiOnline, match="xa nhất"):
        oc.doi_ngay(i, PHONG, "k", (xa + timedelta(days=1)).isoformat())          # quá giới hạn nhập trước
    moi = oc.doi_ngay(i, PHONG, "k", xa.isoformat())                              # dời tới ngày xa nhất (chuỗi YYYY-MM-DD)
    assert moi == xa and oc.ds_ca(PHONG, NGAY) == []
    try:
        c = oc.ds_ca(PHONG, xa)[0]
        assert c["ma"] == "DAAAP6001" and c["khung"] == "chua" and f"Dời sang ngày {xa:%d/%m}" in c["ls"][-1]["viec"]
        assert oc.du_lieu(PHONG, NGAY)["xa_nhat"] == xa.isoformat()
    finally:
        from sqlalchemy import delete

        from app.db import session_scope
        from app.models import BaoCaoNgay, OnlineCa
        with session_scope() as s:
            s.execute(delete(OnlineCa).where(OnlineCa.ngay == xa))
            s.execute(delete(BaoCaoNgay).where(BaoCaoNgay.ngay == xa))


# ------------------------------------------------------------------ liên kết với Nhập tồn và với bảng Báo cáo ngày (12/10/2026)
AI = "kiemthu.lienket"


@pytest.fixture()
def ma_ton():
    """Ba mã HĐ tồn THẬT của database kiểm thử, chưa có ghi chú nào ở Nhập tồn; dọn mốc và nhật ký sau khi thử."""
    from sqlalchemy import delete, select

    from app import nhap_ton as nt
    from app import phan_tich as pt
    from app.db import session_scope
    from app.models import AuditLog, TonTheoDoi
    nt.dam_bao_bang()
    with session_scope() as s:
        co = set(s.execute(select(TonTheoDoi.hop_dong)).scalars())
    ds = [m for m in pt.hop_dong_ton(PHONG).hop_dong if m not in co][:3]
    assert len(ds) == 3, "database kiểm thử phải có ít nhất 3 HĐ tồn chưa ghi chú"

    def don():
        with session_scope() as s:
            s.execute(delete(TonTheoDoi).where(TonTheoDoi.hop_dong.in_(ds)))
            s.execute(delete(AuditLog).where(AuditLog.username == AI))
    don()
    yield ds
    don()


def _moc_tt(ma):
    from sqlalchemy import select

    from app.db import session_scope
    from app.models import TonTheoDoi
    with session_scope() as s:
        r = s.get(TonTheoDoi, ma)
        return (r.loai_moc, r.ngay_moc, r.phuong_an) if r else (None, None, None)


def test_them_ca_chua_co_moc_o_nhap_ton_thi_tu_dien_hen_thi_cong(hai_nguoi, ma_ton):
    a, _ = hai_nguoi
    kq = oc.them_nhieu(ma_ton[0], a, "08-10", PHONG, AI, NGAY)
    assert kq["them"] == [ma_ton[0]] and kq["hoi"] == []
    assert _moc_tt(ma_ton[0])[:2] == ("hen", NGAY)                                   # Nhập tồn tự có "Hẹn thi công" đúng ngày của ca


def test_nhap_ton_dang_hen_ngay_khac_thi_hoi_lai_dong_y_moi_them_va_doi_ngay_hen(hai_nguoi, ma_ton):
    from datetime import timedelta

    from app import nhap_ton as nt
    a, _ = hai_nguoi
    ngay_khac = NGAY + timedelta(days=5)
    nt.luu(ma_ton[1], {"loai_moc": "hen", "ngay_moc": ngay_khac.isoformat()}, PHONG, AI)
    kq = oc.them_nhieu(f"{ma_ton[1]} {ma_ton[2]}", a, "10-12", PHONG, AI, NGAY)
    assert kq["them"] == [ma_ton[2]] and kq["hoi"] == [{"ma": ma_ton[1], "loai": "hen", "ngay": ngay_khac.isoformat()}]    # ca xung đột chưa được thêm
    assert [c["ma"] for c in oc.ds_ca(PHONG, NGAY)] == [ma_ton[2]] and _moc_tt(ma_ton[1])[1] == ngay_khac
    kq = oc.them_nhieu(ma_ton[1], a, "10-12", PHONG, AI, NGAY, xac_nhan=True)         # sale đồng ý chuyển sang hôm nay
    assert kq["them"] == [ma_ton[1]] and _moc_tt(ma_ton[1])[:2] == ("hen", NGAY)       # Nhập tồn tự đổi ngày hẹn


def test_doi_nham_roi_doi_ve_lai_ngay_cu_phieu_hoi_sinh_va_nhap_ton_khop_lai(hai_nguoi, ma_ton):
    """Chủ app 13/10/2026: dời ca nhầm sang ngày khác rồi dời VỀ LẠI thì không tạo phiếu thứ hai, phiếu cũ sống lại và ngày hẹn Nhập tồn về đúng ngày cũ."""
    from sqlalchemy import func, select

    from app.db import session_scope
    from app.models import OnlineCa
    a, _ = hai_nguoi
    bc.luu(a, {"onl_sang": 1}, PHONG, "k", NGAY)
    i = oc.them(ma_ton[0], a, "08-10", PHONG, AI, NGAY)
    moi = oc.doi_ngay(i, PHONG, AI, NGAY + timedelta(days=1), "10-12")
    assert _moc_tt(ma_ton[0])[:2] == ("hen", moi)                                  # sang ngày mới: Nhập tồn theo
    ca_moi = oc.ds_ca(PHONG, moi)[0]
    assert ca_moi["khung"] == "10-12"
    ve = oc.doi_ngay(ca_moi["id"], PHONG, AI, NGAY)                                # dời về lại ngày cũ (đã qua hôm nay, nhưng là hồi sinh)
    assert ve == NGAY and oc.ds_ca(PHONG, moi) == []
    c = oc.ds_ca(PHONG, NGAY)
    assert len(c) == 1 and (c[0]["khung"], c[0]["tt"]) == ("08-10", "du_kien") and "Dời về lại" in c[0]["ls"][-1]["viec"]
    assert _moc_tt(ma_ton[0])[:2] == ("hen", NGAY)                                 # Nhập tồn về đúng ngày cũ
    with session_scope() as s:
        assert s.execute(select(func.count()).select_from(OnlineCa).where(OnlineCa.ma_hd == ma_ton[0], OnlineCa.ngay == NGAY)).scalar() == 1
    assert bc.bang(PHONG, NGAY).set_index("acc_norm").loc[a].onl_sang == 1         # ONL sáng đã gõ không mất qua một vòng dời đi dời về


def test_doi_ve_lai_ngay_cu_giu_dung_trang_thai_cu(hai_nguoi):
    """Hoàn tác một lần dời ngày: ca đang "Đang lắp" / "Đã online" trước khi dời thì về lại đúng trạng thái đó."""
    a, _ = hai_nguoi
    i = oc.them("DAAAP7101", a, "08-10", PHONG, "k", NGAY)
    j = oc.them("DAAAP7102", a, "10-12", PHONG, "k", NGAY)
    k = oc.them("DAAAP7103", a, "10-12", PHONG, "k", NGAY)
    oc.doi_trang_thai(i, "dang_lam", PHONG, "k")
    oc.doi_trang_thai(j, "da_online", PHONG, "k")
    moi = NGAY + timedelta(days=1)
    for x in (i, j, k):
        oc.doi_ngay(x, PHONG, "k", moi)
    for c in oc.ds_ca(PHONG, moi):
        assert c["tt"] == "du_kien"                                                 # sang ngày mới thì bắt đầu lại từ Dự kiến
        oc.doi_ngay(c["id"], PHONG, "k", NGAY)
    ca = {c["ma"]: c for c in oc.ds_ca(PHONG, NGAY)}
    assert (ca["DAAAP7101"]["tt"], ca["DAAAP7102"]["tt"], ca["DAAAP7103"]["tt"]) == ("dang_lam", "da_online", "du_kien")


def test_thong_ke_ca_doi_di_va_den_theo_ngay(hai_nguoi):
    """Chủ app 13/10/2026: xem được hôm nay có bao nhiêu ca dời đi (sang ngày nào) và ca từ ngày khác dời đến."""
    a, b = hai_nguoi
    d1, d2 = NGAY + timedelta(days=1), NGAY + timedelta(days=2)
    i = oc.them("DAAAP7201", a, "08-10", PHONG, "k", NGAY)
    j = oc.them("DAAAP7202", a, "08-10", PHONG, "k", NGAY)
    k = oc.them("DAAAP7203", b, "08-10", PHONG, "k", NGAY)
    oc.doi_ngay(i, PHONG, "k", d1)
    oc.doi_ngay(j, PHONG, "k", d2)
    oc.doi_ngay(k, PHONG, "k", d1)
    x = oc.ca_doi(PHONG, NGAY)
    assert [(r["ma"], r["den"]) for r in x["di"]] == [("DAAAP7201", d1.isoformat()), ("DAAAP7203", d1.isoformat()), ("DAAAP7202", d2.isoformat())] and x["den"] == []
    y = oc.ca_doi(PHONG, d1)
    assert [(r["ma"], r["tu"]) for r in y["den"]] == [("DAAAP7201", NGAY.isoformat()), ("DAAAP7203", NGAY.isoformat())] and y["di"] == []
    assert oc.du_lieu(PHONG, NGAY)["doi"] == x
    ca = oc.ds_ca(PHONG, d1)
    oc.doi_ngay(next(c["id"] for c in ca if c["ma"] == "DAAAP7201"), PHONG, "k", NGAY)    # dời về lại: không còn tính là dời đi / đến
    assert "DAAAP7201" not in [r["ma"] for r in oc.ca_doi(PHONG, NGAY)["di"]]


def test_khong_lui_ve_ngay_da_qua_neu_day_khong_phai_ngay_cu_cua_ca(hai_nguoi):
    a, _ = hai_nguoi
    i = oc.them("DAAAP7001", a, "08-10", PHONG, "k", NGAY + timedelta(days=1))
    with pytest.raises(oc.LoiOnline, match="hôm nay trở đi"):
        oc.doi_ngay(i, PHONG, "k", NGAY)


def test_trang_thai_ca_dong_bo_phuong_an_va_doi_ngay_dong_bo_ngay_hen(hai_nguoi, ma_ton):
    from datetime import timedelta
    a, _ = hai_nguoi
    i = oc.them(ma_ton[0], a, "08-10", PHONG, AI, NGAY)
    oc.doi_trang_thai(i, "da_online", PHONG, AI)
    assert _moc_tt(ma_ton[0])[2] == "Đã triển khai"                                   # sale báo online: Nhập tồn chuyển "Đã triển khai"
    oc.doi_trang_thai(i, "dang_lam", PHONG, AI)
    assert _moc_tt(ma_ton[0])[2] == "Đang chờ triển khai"                              # bỏ Đã online: về lại chờ triển khai
    moi = oc.doi_ngay(i, PHONG, AI)
    assert moi == NGAY + timedelta(days=1) and _moc_tt(ma_ton[0])[:2] == ("hen", moi)  # dời ngày: Nhập tồn đổi ngày hẹn theo


def test_ca_hen_hom_nay_theo_nhap_ton_nhac_xep_khung_gio(hai_nguoi, ma_ton, hen_that):
    from app import nhap_ton as nt
    from app import online_ton as ot
    a, _ = hai_nguoi
    nt.luu(ma_ton[0], {"loai_moc": "hen", "ngay_moc": NGAY.isoformat()}, PHONG, AI)
    nt.luu(ma_ton[1], {"loai_moc": "hen", "ngay_moc": NGAY.isoformat(), "phuong_an": "Huỷ"}, PHONG, AI)      # đã chọn Huỷ: không nhắc
    hen = ot.hen_cho_ngay(PHONG, NGAY)
    ds = {x["ma"] for v in hen.values() for x in v}
    assert ma_ton[0] in ds and ma_ton[1] not in ds
    acc = next(k for k, v in hen.items() if any(x["ma"] == ma_ton[0] for x in v))
    nv = {x["a"] for x in oc.nhan_vien(tuple(PHONG), NGAY.isoformat())}
    oc.them(ma_ton[0], a if acc not in nv else acc, "08-10", PHONG, AI, NGAY)
    assert ma_ton[0] not in {x["ma"] for v in ot.hen_cho_ngay(PHONG, NGAY).values() for x in v}   # đã xếp khung giờ: hết nhắc


def test_the_lech_ngay_voi_nhap_ton_va_nut_cap_nhat_ngay_hen(hai_nguoi, ma_ton):
    from datetime import timedelta

    from app import nhap_ton as nt
    from app import online_ton as ot
    a, _ = hai_nguoi
    i = oc.them(ma_ton[0], a, "08-10", PHONG, AI, NGAY)
    assert ot.lech_ngay(oc.ds_ca(PHONG, NGAY), NGAY, PHONG) == {}
    ngay_khac = NGAY + timedelta(days=4)
    nt.luu(ma_ton[0], {"loai_moc": "hen", "ngay_moc": ngay_khac.isoformat()}, PHONG, AI)             # ai đó sửa ngày hẹn ở trang Nhập tồn
    assert ot.lech_ngay(oc.ds_ca(PHONG, NGAY), NGAY, PHONG) == {ma_ton[0]: {"loai": "hen", "ngay": ngay_khac.isoformat()}}
    assert oc.dong_bo_ngay_hen(i, PHONG, AI) == 1 and _moc_tt(ma_ton[0])[1] == NGAY
    assert oc.dong_bo_ngay_hen(i, PHONG, AI) == 0                                       # đã khớp: không ghi lại


def test_ma_khong_con_ton_thi_bo_qua_khong_bao_loi_o_nhap_ton(hai_nguoi):
    a, _ = hai_nguoi
    kq = oc.them_nhieu("ZZZZZ9999", a, "08-10", PHONG, AI, NGAY)                          # mã lạ / đã online theo file: vẫn thêm ca bình thường
    assert kq["them"] == ["ZZZZZ9999"] and kq["hoi"] == []


def test_dua_ve_tim_noi_ca_dang_o_va_thong_ke_doi_di_theo_dung_noi(hai_nguoi):
    """Chủ app báo 13/10/2026: bấm "Đưa về hôm nay" mà báo "ca không còn ở ngày đã dời tới". Ca có thể đã dời tiếp (A -> B -> C), đã huỷ, hoặc đã về rồi."""
    a, _ = hai_nguoi
    d1, d2, d3 = NGAY + timedelta(days=1), NGAY + timedelta(days=2), NGAY + timedelta(days=3)
    i = oc.them("DAAAP7401", a, "08-10", PHONG, "k", NGAY)
    j = oc.them("DAAAP7402", a, "08-10", PHONG, "k", NGAY)
    oc.doi_ngay(i, PHONG, "k", d1)
    oc.doi_ngay(oc.ds_ca(PHONG, d1)[0]["id"], PHONG, "k", d3)                      # A (NGAY) -> B (d1) -> C (d3)
    oc.doi_ngay(j, PHONG, "k", d2)
    oc.xoa(oc.ds_ca(PHONG, d2)[0]["id"], PHONG, "k")                               # ca thứ hai bị huỷ ở ngày đích
    di = oc.ca_doi(PHONG, NGAY)["di"]
    assert [(x["ma"], x["den"]) for x in di] == [("DAAAP7401", d3.isoformat())]    # chỉ ca còn sống, ghi đúng nơi nó đang ở
    ca = oc.ca_dang_o(PHONG, "DAAAP7401", NGAY)
    assert ca["ngay"] == d3 and ca["acc"] == a
    assert oc.ca_dang_o(PHONG, "DAAAP7402", NGAY) is None                          # đã huỷ
    oc.doi_ngay(ca["id"], PHONG, "k", NGAY)                                        # đưa về: từ nơi nó đang ở, không cần biết ngày đích cũ
    assert [c["ma"] for c in oc.ds_ca(PHONG, NGAY)] == ["DAAAP7401"] and oc.ca_dang_o(PHONG, "DAAAP7401", NGAY)["ngay"] == NGAY
    assert oc.ca_doi(PHONG, NGAY)["di"] == []


def test_ghi_chu_lien_ket_hai_chieu_giua_ca_va_nhap_ton(hai_nguoi, ma_ton):
    """Chủ app 13/10/2026: ghi chú của ca (Theo dõi Online) và "Ghi chú tình trạng" (Nhập tồn) là cùng một chữ, sửa bên nào thì bên kia theo."""
    from sqlalchemy import delete

    from app.db import session_scope
    from app.models import BaoCaoNgay, OnlineCa
    try:
        from app import nhap_ton as nt
        from app import online_ton as ot
        a, _ = hai_nguoi
        hom_nay = bc.hom_nay()
        gc_ton = lambda ma: ot.ghi_chu_ton([ma]).get(ma, "")                         # noqa: E731
        # 1) Nhập tồn đã có chữ, thêm ca mới không gõ gì -> ca lấy sẵn chữ Nhập tồn
        nt.luu(ma_ton[0], {"ghi_chu": "KH hẹn 7/10, trời mưa"}, PHONG, AI)
        i = oc.them(ma_ton[0], a, "08-10", PHONG, AI, hom_nay)
        assert next(c for c in oc.ds_ca(PHONG, hom_nay) if c["id"] == i)["gc"] == "KH hẹn 7/10, trời mưa"
        # 2) sửa ở ca -> Nhập tồn đổi theo
        oc.sua_ghi_chu(i, "KH hẹn lại 11/10", PHONG, AI)
        assert gc_ton(ma_ton[0]) == "KH hẹn lại 11/10"
        # 3) sửa ở Nhập tồn -> ca đổi theo (và chỉ các ca còn sống từ hôm nay)
        nt.luu(ma_ton[0], {"ghi_chu": "KH hẹn 12/10 sau 15h"}, PHONG, AI)
        assert oc.ghi_chu_tu_ton(ma_ton[0], "KH hẹn 12/10 sau 15h", PHONG, AI) == 1
        assert next(c for c in oc.ds_ca(PHONG, hom_nay) if c["id"] == i)["gc"] == "KH hẹn 12/10 sau 15h"
        # 4) ca mới có gõ ghi chú riêng mà Nhập tồn đã có chữ -> NỐI, không xoá lịch sử; hai bên giống nhau
        oc.them(ma_ton[1], a, "10-12", PHONG, AI, hom_nay, ghi_chu="KH rảnh sau 15h")
        nt.luu(ma_ton[2], {"ghi_chu": "đã gọi 2 lần"}, PHONG, AI)
        k = oc.them(ma_ton[2], a, "10-12", PHONG, AI, hom_nay, ghi_chu="KH rảnh sau 15h")
        gc = next(c for c in oc.ds_ca(PHONG, hom_nay) if c["id"] == k)["gc"]
        assert gc == "đã gọi 2 lần · KH rảnh sau 15h" and gc_ton(ma_ton[2]) == gc
        assert gc_ton(ma_ton[1]) == "KH rảnh sau 15h"                                   # Nhập tồn chưa có chữ: lấy chữ của ca
        # 5) HĐ không có trong tồn: bỏ qua, không lỗi
        j = oc.them("DAAAP7501", a, "08-10", PHONG, AI, hom_nay, ghi_chu="ca phát sinh")
        oc.sua_ghi_chu(j, "đổi chữ", PHONG, AI)
        assert ot.ghi_chu_ton(["DAAAP7501"]) == {}

    finally:                                                                     # ca thử nằm ở HÔM NAY thật, không thuộc ngày kiểm thử mà fixture tự dọn
        with session_scope() as s:
            s.execute(delete(OnlineCa).where(OnlineCa.ma_hd.in_([*ma_ton, "DAAAP7501"])))
            s.execute(delete(BaoCaoNgay).where(BaoCaoNgay.ngay == bc.hom_nay(), BaoCaoNgay.acc_norm == a))


def test_trang_nhap_ton_chep_ghi_chu_sang_ca_theo_doi_online(hai_nguoi, ma_ton):
    """Đường THẬT của trang Nhập tồn (`_ghi_chu_sang_online`, gọi sau mỗi lần sale sửa "Ghi chú tình trạng") đổi ghi chú các ca đang còn của HĐ đó."""
    import json
    from types import SimpleNamespace

    from flask_login import login_user
    from sqlalchemy import delete

    from app import online_ton as ot
    from app.auth import SessionUser
    from app.db import session_scope
    from app.models import BaoCaoNgay, OnlineCa
    from app.ui.app import server
    from app.ui.pages import nhapton
    a, _ = hai_nguoi
    hom_nay = bc.hom_nay()
    try:
        i = oc.them(ma_ton[0], a, "08-10", PHONG, AI, hom_nay, ghi_chu="chữ cũ")
        with server.test_request_context("/"):
            login_user(SessionUser(SimpleNamespace(id=1, username="kiemthu.nvkd", ho_ten="Kiểm thử", role="nvkd", ma_nv=None, session_version=0,
                                                   scope=json.dumps(PHONG))))
            nhapton._ghi_chu_sang_online(ma_ton[0], "chữ mới từ Nhập tồn", PHONG, a)
        assert next(c for c in oc.ds_ca(PHONG, hom_nay) if c["id"] == i)["gc"] == "chữ mới từ Nhập tồn"
        assert ot.ghi_chu_ton([ma_ton[0]]).get(ma_ton[0], "") != "chữ mới từ Nhập tồn"        # hàm này chỉ chép MỘT chiều (Nhập tồn đã tự lưu ở bước trước)
    finally:
        with session_scope() as s:
            s.execute(delete(OnlineCa).where(OnlineCa.ma_hd == ma_ton[0]))
            s.execute(delete(BaoCaoNgay).where(BaoCaoNgay.ngay == hom_nay, BaoCaoNgay.acc_norm == a))


def test_nap_muc_online_keo_ghi_chu_ca_cu_ve_khop_nhap_ton(hai_nguoi, ma_ton):
    """Ca tạo TRƯỚC khi có liên kết ghi chú: nạp mục Theo dõi Online là tự khớp - Nhập tồn có chữ thì ca lấy chữ đó; Nhập tồn trống mà ca có chữ thì chép sang Nhập tồn."""
    from sqlalchemy import delete, update

    from app import nhap_ton as nt
    from app import online_ton as ot
    from app.db import session_scope
    from app.models import BaoCaoNgay, OnlineCa
    a, _ = hai_nguoi
    hom_nay = bc.hom_nay()
    try:
        i, j = oc.them(ma_ton[0], a, "08-10", PHONG, AI, hom_nay), oc.them(ma_ton[1], a, "08-10", PHONG, AI, hom_nay)
        with session_scope() as s:                                                    # giả lập ca cũ: ghi chú riêng, chưa liên kết
            s.execute(update(OnlineCa).where(OnlineCa.id == i).values(ghi_chu="chữ riêng của ca"))
            s.execute(update(OnlineCa).where(OnlineCa.id == j).values(ghi_chu="chỉ ca có chữ"))
        nt.luu(ma_ton[0], {"ghi_chu": "Tình trạng đang có ở Nhập tồn"}, PHONG, AI)
        du = oc.du_lieu(PHONG, hom_nay)
        gc = {c["ma"]: c["gc"] for c in du["ca"]}
        assert gc[ma_ton[0]] == "Tình trạng đang có ở Nhập tồn"                        # Nhập tồn thắng
        assert gc[ma_ton[1]] == "chỉ ca có chữ" and ot.ghi_chu_ton([ma_ton[1]])[ma_ton[1]] == "chỉ ca có chữ"   # Nhập tồn trống: lấy chữ của ca
        assert oc.dong_bo_ghi_chu_ngay(PHONG, hom_nay) == 0                            # lần sau không còn gì lệch, không ghi lại
    finally:
        with session_scope() as s:
            s.execute(delete(OnlineCa).where(OnlineCa.ma_hd.in_(ma_ton)))
            s.execute(delete(BaoCaoNgay).where(BaoCaoNgay.ngay == hom_nay, BaoCaoNgay.acc_norm == a))


def test_o_bi_tu_choi_vi_gia_tri_sai_quay_ve_ngay_kem_ten_nguoi(hai_nguoi):
    """Chủ app báo 13/10/2026: gõ giá trị bị từ chối thì vài giây sau số tự nhảy về mà không hiểu vì sao. Nay máy chủ trả NGAY dòng đã lưu cho ô bị từ chối
    (`bo_cho`) và câu báo ghi rõ tên người."""
    import json
    from types import SimpleNamespace

    from flask_login import login_user

    from app.auth import SessionUser
    from app.ui.app import app, server
    a, _ = hai_nguoi
    bc.luu(a, {"onl_sang": 2}, PHONG, "k", NGAY)
    luu_o = next(getattr(v["callback"], "__wrapped__", v["callback"]) for k, v in app.callback_map.items()
                 if "callback" in v and "bn-da-luu.data" in k and "bn-msg.children" in k and "bn-cap-nhat.data" in k)
    ev = {"colId": "onl_sang", "value": "abc", "data": {"acc_norm": a, "ho_ten": "Người Thử"}}
    with server.test_request_context("/"):
        login_user(SessionUser(SimpleNamespace(id=1, username="kiemthu.nvkd", ho_ten="Kiểm thử", role="nvkd", ma_nv=None, session_version=0, scope=json.dumps(PHONG))))
        da_luu, msg, _tat, ve = luu_o([ev], "IBB7", NGAY.isoformat(), None)
    assert da_luu["xong"] == [[a, "onl_sang", "abc"]]                                  # đã xử lý (từ chối theo luật) nên trình duyệt không gửi lại
    assert ve["bo_cho"] == [[a, "onl_sang", "abc"]] and next(r for r in ve["rows"] if r["acc_norm"] == a)["onl_sang"] == 2
    assert "Người Thử: Chỉ được nhập số" in json.dumps(msg, default=lambda o: o.to_plotly_json(), ensure_ascii=False)
