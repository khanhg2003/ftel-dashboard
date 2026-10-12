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


@pytest.fixture(autouse=True)
def _don():
    """Xoá phiếu và báo cáo của ngày kiểm thử trước / sau mỗi phép thử (database kiểm thử dùng lại qua nhiều lần chạy)."""
    from sqlalchemy import delete

    from app.db import session_scope
    from app.models import BaoCaoNgay, OnlineCa

    def don():
        with session_scope() as s:
            for ngay in (NGAY, NGAY + timedelta(days=1)):
                s.execute(delete(OnlineCa).where(OnlineCa.ngay == ngay))
            s.execute(delete(BaoCaoNgay).where(BaoCaoNgay.ngay.in_([NGAY, NGAY + timedelta(days=1)])))
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


def test_ca_noi_voi_bang_bao_cao_ngay_sang_chieu_va_da_online(hai_nguoi):
    """Mỗi lần phiếu đổi, ba ô ONL sáng / ONL chiều / Đã online của đúng người đó được tính lại từ phiếu."""
    a, b = hai_nguoi
    ids = [oc.them("DAAAP0001", a, "08-10", PHONG, "k", NGAY), oc.them("DAAAP0002", a, "10-12", PHONG, "k", NGAY),
           oc.them("DAAAP0003", a, "1530-1730", PHONG, "k", NGAY), oc.them("DAAAP0004", a, "sau", PHONG, "k", NGAY),
           oc.them("DAAAP0005", a, "chua", PHONG, "k", NGAY)]
    oc.them("DAAAP0006", b, "08-10", PHONG, "k", NGAY)

    def dong(acc):
        return bc.bang(PHONG, NGAY).set_index("acc_norm").loc[acc]
    r = dong(a)
    assert (r.onl_sang, r.onl_chieu, r.thuc_hien, r.dk_onl) == (2, 2, 0, 4)       # ca "Chưa hẹn giờ" chưa tính vào ô nào
    assert dong(b).onl_sang == 1
    oc.doi_trang_thai(ids[0], "da_online", PHONG, "k")
    assert dong(a).thuc_hien == 1 and dong(a).con_phai_onl == 3
    oc.doi_khung(ids[4], "1330-1530", PHONG, "k")                                # chọn khung cho ca chưa hẹn giờ
    assert dong(a).onl_chieu == 3
    oc.xoa(ids[1], PHONG, "k")
    assert dong(a).onl_sang == 1 and dong(a).dk_onl == 4
    assert dong(b).onl_sang == 1                                                    # người khác không bị đụng


def test_doi_nguoi_phu_trach_tinh_lai_ca_hai_nguoi(hai_nguoi):
    a, b = hai_nguoi
    i = oc.them("DAAAP0001", a, "08-10", PHONG, "k", NGAY)
    oc.sua(i, b, "  khách quen ", PHONG, "k")
    c = oc.ds_ca(PHONG, NGAY)[0]
    assert c["acc"] == b and c["gc"] == "khách quen"
    t = bc.bang(PHONG, NGAY).set_index("acc_norm")
    assert t.loc[a].onl_sang == 0 and t.loc[b].onl_sang == 1


def test_doi_sang_ngay_mai_ve_du_kien_chua_hen_gio_va_tinh_lai_hai_ngay(hai_nguoi):
    a, _ = hai_nguoi
    i = oc.them("DAAAP0001", a, "08-10", PHONG, "k", NGAY)
    oc.doi_trang_thai(i, "dang_lam", PHONG, "k")
    mai = oc.doi_ngay_mai(i, PHONG, "k")
    assert mai == NGAY + timedelta(days=1) and oc.ds_ca(PHONG, NGAY) == []
    c = oc.ds_ca(PHONG, mai)[0]
    assert (c["khung"], c["tt"]) == ("chua", "du_kien") and "Dời sang ngày 11/09" in c["ls"][-1]["viec"]
    assert bc.bang(PHONG, NGAY).set_index("acc_norm").loc[a].onl_sang == 0
    j = oc.them("DAAAP0001", a, "08-10", PHONG, "k", NGAY)                         # mã này đã nằm ở ngày mai
    with pytest.raises(oc.LoiOnline, match="đã có"):
        oc.doi_ngay_mai(j, PHONG, "k")


def test_chi_nhac_nguoi_da_nhap_du_kien_ma_chua_khai_du_gio_nguoi_du_kien_0_an_han(hai_nguoi):
    """Chủ app (12/10/2026): người dự kiến online 0 không hiện; chỉ người đã gõ dự kiến mà chưa khai đủ giờ mới bị nhắc."""
    a, b = hai_nguoi
    d = oc.du_lieu(PHONG, NGAY)
    assert d["thieu"] == {} and d["dk"] == {}                                       # đầu ngày chưa ai gõ gì: không ai bị nhắc
    bc.luu(a, {"onl_sang": 2, "onl_chieu": 1}, PHONG, "k", NGAY)                    # a gõ dự kiến 3 ca, chưa khai ca nào
    bc.luu(b, {"onl_sang": 0, "onl_chieu": 0}, PHONG, "k", NGAY)                    # b gõ 0
    d = oc.du_lieu(PHONG, NGAY)
    assert d["thieu"] == {a: {"can": 3, "khai": 0, "chua": 0, "thieu": 3}} and b not in d["thieu"]
    oc.them("DAAAP0001", a, "08-10", PHONG, "k", NGAY)
    oc.them("DAAAP0002", a, "chua", PHONG, "k", NGAY)                               # "Chưa hẹn giờ" vẫn là chưa khai giờ
    assert oc.du_lieu(PHONG, NGAY)["thieu"][a] == {"can": 3, "khai": 1, "chua": 1, "thieu": 2}
    oc.them("DAAAP0003", a, "10-12", PHONG, "k", NGAY)
    i = oc.ds_ca(PHONG, NGAY)
    oc.doi_khung(next(c["id"] for c in i if c["khung"] == "chua"), "1330-1530", PHONG, "k")
    assert oc.du_lieu(PHONG, NGAY)["thieu"][a]["thieu"] == 0                        # khai đủ 3 ca có giờ: hết nhắc
    oc.them("DAAAP0004", b, "08-10", PHONG, "k", NGAY)                              # b có phiếu thì có mặt, không thiếu
    assert oc.du_lieu(PHONG, NGAY)["thieu"][b] == {"can": 1, "khai": 1, "chua": 0, "thieu": 0}


def test_chua_khai_du_thi_khong_ghi_de_so_da_go_nhung_huy_ca_thi_ghi_dung(hai_nguoi):
    a, _ = hai_nguoi
    bc.luu(a, {"onl_sang": 3, "onl_chieu": 2}, PHONG, "k", NGAY)                    # gõ dự kiến 5
    ids = [oc.them("DAAAP0001", a, "08-10", PHONG, "k", NGAY), oc.them("DAAAP0002", a, "1530-1730", PHONG, "k", NGAY)]
    r = bc.bang(PHONG, NGAY).set_index("acc_norm").loc[a]
    assert (r.onl_sang, r.onl_chieu) == (3, 2)                                      # mới khai 2/5 ca: số gõ còn nguyên
    oc.doi_trang_thai(ids[0], "da_online", PHONG, "k")
    assert bc.bang(PHONG, NGAY).set_index("acc_norm").loc[a].thuc_hien == 1         # "Đã online" luôn đúng số phiếu
    oc.xoa(ids[1], PHONG, "k")                                                      # huỷ ca là chủ ý bớt ca: ghi đúng số phiếu
    r = bc.bang(PHONG, NGAY).set_index("acc_norm").loc[a]
    assert (r.onl_sang, r.onl_chieu) == (1, 0)


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


def test_ban_tinh_thong_ke_tren_trinh_duyet_khop_ban_python():
    node = shutil.which("node")
    if not node:
        pytest.skip("Máy không có Node")
    ca = [{"id": 1, "ma": "A", "acc": "x", "khung": "08-10", "tt": "da_online"}, {"id": 2, "ma": "B", "acc": "x", "khung": "08-10", "tt": "dang_lam"},
          {"id": 3, "ma": "C", "acc": "y", "khung": "chua", "tt": "du_kien"}, {"id": 4, "ma": "D", "acc": "y", "khung": "sau", "tt": "du_kien"}]
    code = ("const m=require(process.argv[1]);let d='';process.stdin.on('data',c=>d+=c).on('end',()=>{"
            "const j=JSON.parse(d);console.log(JSON.stringify({tk:m.thongKe(j.ca,j.khung),th:m.thieuGio(j.ca,j.dk)}));});")
    js = Path(__file__).resolve().parent.parent / "assets" / "online.js"
    kq = json.loads(subprocess.run([node, "-e", code, str(js)], input=json.dumps({"ca": ca, "khung": oc.khung(), "dk": DK}), capture_output=True,
                                   text=True, encoding="utf-8", check=True).stdout)
    assert kq["tk"] == oc.thong_ke(ca)
    assert kq["th"] == oc.thieu_gio(ca, DK) and kq["th"]["x"] == {"can": 4, "khai": 2, "chua": 0, "thieu": 2}


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
        assert {"onl-du-lieu", "onl-sk", "onl-hero", "onl-nguoi", "onl-bang", "onl-f-hd", "onl-f-nv", "onl-f-khung", "onl-md"} <= set(tat)
