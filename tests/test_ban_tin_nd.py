"""Kiểm thử chuỗi Bản tin 8h mới: ảnh báo cáo + tin chữ "NHẬN ĐỊNH & HÀNH ĐỘNG" cho Ban Giám đốc và trưởng phòng.
Chặn mạng hoàn toàn (giả lập `zalo_bot.gui_tin` / `gui_anh`), dùng database thử, ngày số 11/09/2026."""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import ban_tin as bt                                           # noqa: E402
from app import ban_tin_anh as ba                                        # noqa: E402
from app import ban_tin_nd as nd                                         # noqa: E402
from app import ban_tin_phong as tp                                      # noqa: E402
from app import ban_tin_phong_nd as pn                                   # noqa: E402
from app import bao_cao_phong as bcp                                     # noqa: E402
from app import canh_bao, config, du_bao, metrics, overview, zalo_bot   # noqa: E402
from app import phan_tich as pt                                          # noqa: E402
from app.config import DATA_DIR                                          # noqa: E402

pytestmark = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(),
                                reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")
NGAY = "2026-09-11"
SANG_8H = datetime(2026, 9, 12, 8, 5)
CHOT = (False, datetime(2026, 9, 12, 7, 0))
APP = "https://app.example.vn"


class Gia:
    """Bản giả của `gui_tin` / `gui_anh`: ghi đúng thứ tự gửi. `hong_anh`: loại ảnh luôn lỗi ("phong" | "tong");
    `hong_chu`: chat_id luôn lỗi khi gửi chữ; `hong_lan_chu`: lần gửi chữ thứ n (từ 1) lỗi."""

    def __init__(self):
        self.tin: list[tuple[str, str]] = []
        self.anh: list[tuple[str, str, str]] = []
        self.log: list[tuple[str, str]] = []
        self.hong_anh: set[str] = set()
        self.hong_chu: set[str] = set()
        self.hong_lan_chu: set[int] = set()
        self.so_chu = 0

    def gui_tin(self, chat_id, noi_dung, parse_mode=None, han=8, text_styles=None):
        self.so_chu += 1
        if chat_id in self.hong_chu or self.so_chu in self.hong_lan_chu:
            raise zalo_bot.LoiZalo("Zalo từ chối (mã 400): chữ giả lập.")
        self.tin.append((chat_id, noi_dung))
        self.log.append(("tin", chat_id))

    def gui_anh(self, chat_id, url_anh, caption="", han=20):
        loai = "phong" if (phong_cua_url(url_anh)[1]) else "tong"
        if loai in self.hong_anh:
            raise zalo_bot.LoiZalo("Zalo từ chối (mã 400): ảnh giả lập.")
        self.anh.append((chat_id, url_anh, caption))
        self.log.append(("anh", chat_id))

    def cho(self, chat_id):
        return [t for c, t in self.tin if c == chat_id]

    def anh_cho(self, chat_id):
        return [(phong_cua_url(u), cap) for c, u, cap in self.anh if c == chat_id]


def phong_cua_url(url: str):
    """(ngày số, mã phòng hoặc None) giải từ đường dẫn ảnh."""
    m = re.search(r"/api/ban-tin/anh/([^/]+)\.png$", url)
    return ba.doc_ma(m.group(1)) if m else None


@pytest.fixture()
def gia(monkeypatch):
    g = Gia()
    monkeypatch.setattr(zalo_bot, "gui_tin", g.gui_tin)
    monkeypatch.setattr(zalo_bot, "gui_anh", g.gui_anh)
    return g


@pytest.fixture(autouse=True)
def moi_truong(monkeypatch):
    from sqlalchemy import delete

    from app.db import session_scope
    from app.models import BanTinNguoiNhan, BanTinNguoiNhanPhong, BanTinNhatKy

    def don():
        with session_scope() as s:
            for b in (BanTinNhatKy, BanTinNguoiNhanPhong, BanTinNguoiNhan):
                s.execute(delete(b))
    bt.dam_bao_bang()
    don()
    monkeypatch.setattr(metrics, "ngay_moi_nhat", lambda: NGAY)
    monkeypatch.setattr(overview, "trang_thai_ngay", lambda iso: CHOT)
    monkeypatch.setenv("APP_URL", APP)
    yield
    don()


def _them(ten, phong, chat="c1", loai="truong_phong"):
    ok, msg = bt.luu_nguoi_nhan(None, ten, loai, chat, True, phong)
    assert ok, msg


def _nhat_ky():
    from sqlalchemy import select

    from app.db import session_scope
    from app.models import BanTinNhatKy
    with session_scope() as s:
        return {(r.nguoi_nhan_id, r.loai): (r.ket_qua, r.ly_do) for r in s.execute(select(BanTinNhatKy)).scalars()}


def _loai_ok(ten_nguoi):
    from sqlalchemy import select

    from app.db import session_scope
    from app.models import BanTinNhatKy
    with session_scope() as s:
        return {r.loai for r in s.execute(select(BanTinNhatKy).where(
            BanTinNhatKy.ten_nguoi == ten_nguoi, BanTinNhatKy.ket_qua == "ok")).scalars()}


def _doan_kieu(chu, kieu):
    u16 = chu.encode("utf-16-le")
    return [(u16[k["start"] * 2:(k["start"] + k["len"]) * 2].decode("utf-16-le"), k["st"]) for k in kieu]


# ------------------------------------------------------------------ nhận định Ban Giám đốc
def test_nhan_dinh_bgd_co_muc_tieu_phong_can_bu_chat_luong_ton_va_hanh_dong():
    t = nd.dung_nhan_dinh_bgd(NGAY)
    for cum in ("NHẬN ĐỊNH & HÀNH ĐỘNG · 11/09", "1) MỤC TIÊU CẦN ĐẠT", "2) PHÒNG CẦN BÙ SỐ", "3) CHẤT LƯỢNG BÁN",
                "4) HỢP ĐỒNG TỒN", "5) HÀNH ĐỘNG ĐỀ XUẤT", "Chi nhánh: cần", "Đà Nẵng: cần", "Quảng Nam: cần",
                "Họp nhanh với", "trước 13/09", "online/ngày"):
        assert cum in t, cum
    assert len(t) <= bt.TOI_DA_KY_TU and "đấu nối" not in t.lower()
    db = du_bao.du_bao_thang("2026-09", 11)
    tong = db[db.phong_code == "TOTAL"].iloc[0]
    assert f"Chi nhánh: cần {bt._so(tong['can_moi_ngay'])}/ngày (hiện {bt._so(tong['tb_ngay'], 1)})" in t
    assert f"· hụt {bt._so(tong['mt'] - tong['du_bao'])}" in t
    assert len(t) <= 1400                                                         # gọn: một màn hình điện thoại rưỡi


def test_nhan_dinh_bgd_phong_can_bu_dung_quy_tac_va_xep_hut_nhieu_truoc():
    sl = bt._so_lieu_bgd(NGAY)
    ban_hang = bt._phong_ban_hang(sl)
    tq = sl["tq"].set_index("phong_code")
    mong = []
    for g in ban_hang.values():
        for _, r in g.iterrows():
            if r["danh_gia"] == du_bao.RUI_RO or tq.loc[r["phong_code"], "online"] < tq.loc[r["phong_code"], "ck_online"]:
                mong.append((max(r["mt"] - r["du_bao"], 0), r["phong"]))
    mong.sort(key=lambda x: -x[0])
    khong = [r["phong"] for g in ban_hang.values() for _, r in g.iterrows()
             if r["danh_gia"] != du_bao.RUI_RO and tq.loc[r["phong_code"], "online"] >= tq.loc[r["phong_code"], "ck_online"]]
    t = str(nd.dung_nhan_dinh_bgd(NGAY))
    muc2 = t[t.index("2) PHÒNG CẦN BÙ SỐ"):t.index("3) CHẤT LƯỢNG BÁN")]
    dong = [d[2:].split(":")[0] for d in muc2.split("\n") if d.startswith("• ")]
    assert len(dong) >= 3 and dong == [ten for _, ten in mong[:len(dong)]]
    assert all(f"• {k}:" not in muc2 for k in khong)                       # phòng An toàn / Cần tăng tốc mà không giảm cùng kỳ thì không nêu
    for ten in ("KT_DNG1", "CUS_DNG1", "ECOM_DNG", "ANCS"):                # phòng không bán hàng không xếp
        assert ten not in muc2


def test_nhan_dinh_bgd_ton_khop_bao_cao_phong_va_nhac_3_phong_nhieu_nhat():
    ton = pt.bang_theo_phong(pt.hop_dong_online("2026-09-01", NGAY), pt.hop_dong_ton(), "2026-09")
    tong = int(ton[ton.loai_dong == "total"].iloc[0]["ton_qua_7"])
    t = str(nd.dung_nhan_dinh_bgd(NGAY))
    assert f"{bt._so(tong)} HĐ chờ online từ 7 ngày" in t
    muc4 = t[t.index("4) HỢP ĐỒNG TỒN"):t.index("5) HÀNH ĐỘNG")]
    assert muc4.count(",") == 2 and "Nhiều nhất:" in muc4


def test_nhan_dinh_bgd_khong_ten_nhan_su_khong_ten_khach_hang():
    from sqlalchemy import text

    from app.db import engine
    bi_mat = "KHACH_BI_MAT_XYZ"
    ten = set()
    for ma in ("IBB7", "IBB2", "DIENBAN", "IBB1"):
        bn = bcp.bang_nhan_su("2026-09", 11, ma)
        ten |= {str(x) for x in bn[bn.loai_dong == "data"].ho_ten} | {str(x) for x in bn[bn.loai_dong == "data"].acc if x}
    with engine.begin() as c:
        c.execute(text("UPDATE fact_internet SET ten_khach_hang = :t WHERE ten_khach_hang IS NULL"), {"t": bi_mat})
    try:
        t = str(nd.dung_nhan_dinh_bgd(NGAY))
    finally:
        with engine.begin() as c:
            c.execute(text("UPDATE fact_internet SET ten_khach_hang = NULL WHERE ten_khach_hang = :t"), {"t": bi_mat})
    assert bi_mat not in t and not [n for n in ten if len(n) > 5 and n in t]


def test_nhan_dinh_bgd_dai_thi_bot_phong_roi_cat_va_kieu_chu_dung_vi_tri(monkeypatch):
    day_du = nd.dung_nhan_dinh_bgd(NGAY)
    monkeypatch.setattr(bt, "TOI_DA_KY_TU", len(day_du) - 250)
    ngan = nd.dung_nhan_dinh_bgd(NGAY)
    assert len(ngan) <= len(day_du) - 250 and "1) MỤC TIÊU CẦN ĐẠT" in ngan and "phòng khác (xem ảnh)" in ngan
    monkeypatch.setattr(bt, "TOI_DA_KY_TU", 400)
    assert len(nd.dung_nhan_dinh_bgd(NGAY)) <= 400
    tong = len(day_du.encode("utf-16-le")) // 2
    assert day_du.kieu and all(k["start"] >= 0 and k["len"] > 0 and k["start"] + k["len"] <= tong for k in day_du.kieu)
    doan = _doan_kieu(day_du, day_du.kieu)
    assert any(c.startswith("NHẬN ĐỊNH & HÀNH ĐỘNG") and "b" in st for c, st in doan)
    assert len(day_du.kieu) <= bt.KIEU_TOI_DA
    assert any(c == "1) MỤC TIÊU CẦN ĐẠT" and "b" in st for c, st in doan)
    assert any(any(s.startswith("c_") for s in st) for _, st in doan)


def test_nhan_dinh_bgd_khi_da_dat_muc_tieu_khong_co_phong_can_bu(monkeypatch):
    sl = bt._so_lieu_bgd(NGAY)
    sl["phong"] = sl["phong"].assign(danh_gia=du_bao.AN_TOAN, du_bao=lambda d: d["mt"] + 5)
    sl["tq"] = sl["tq"].assign(ck_online=0)
    monkeypatch.setattr(bt, "_so_lieu_bgd", lambda iso: sl)
    t = str(nd.dung_nhan_dinh_bgd(NGAY))
    assert "2) PHÒNG CẦN BÙ SỐ" not in t and "Họp nhanh" not in t and "xử lý dứt điểm" in t


def test_han_xu_ly_khong_vuot_cuoi_thang():
    assert str(nd.han_xu_ly("2026-09-11")) == "2026-09-13" and str(nd.han_xu_ly("2026-09-29")) == "2026-09-30"
    assert nd.ngay_vn(nd.cuoi_thang("2026-02-10")) == "28/02"


# ------------------------------------------------------------------ nhận định trưởng phòng
def _nd_phong(ma):
    chung = tp.nap_chung(NGAY)
    ns = tp._nhan_su(chung, ma)
    can = tp.can_trao_doi(ns[1], ma)
    return chung, ns, can, pn.dung_nhan_dinh_phong(chung, ma, bcp.ten_phong(ma), ns, can)


def test_nhan_dinh_phong_co_muc_tieu_vi_tri_trao_doi_ban_kem_ton_va_hanh_dong():
    chung, ns, can, tin = _nd_phong("IBB7")
    t = "\n".join(map(str, tin))
    for cum in ("NHẬN ĐỊNH & HÀNH ĐỘNG - IBB7", "1) MỤC TIÊU CẦN ĐẠT", "Cả phòng cần", "Chia bình quân", "mục tiêu ngày",
                "2) VỊ TRÍ", "Hạng 1/", "3) CẦN TRAO ĐỔI", "5) BÁN KÈM", "6) HỢP ĐỒNG TỒN", "7) HÀNH ĐỘNG ĐỀ XUẤT", "trước 13/09"):
        assert cum in t, cum
    d = chung["db"][chung["db"].phong_code == "IBB7"].iloc[0]
    assert f"Cả phòng cần {bt._so(d['can_moi_ngay'])} online/ngày trong {int(d['con_lai'])} ngày còn lại" in t
    so_nguoi = len(ns[1])
    assert f"Chia bình quân {so_nguoi} nhân sự được xét" in t
    assert all(len(x) <= bt.TOI_DA_KY_TU for x in tin) and "đấu nối" not in t.lower()
    q = chung["tq"][chung["tq"].phong_code == "IBB7"].iloc[0]
    assert f"Online ngày 11/09: {bt._so(q['ngay_online'])}/{bt._so(q['mt_ngay'])} mục tiêu ngày" in t


def test_nhan_dinh_phong_neu_dung_het_nguoi_can_trao_doi_khong_gioi_han():
    chung, ns, can, tin = _nd_phong("DIENBAN")
    t = "\n".join(map(str, tin))
    assert len(can) >= 5
    assert all(str(r["ho_ten"]) in t for _, r in can.iterrows())
    muc3 = t[t.index("3) CẦN TRAO ĐỔI"):t.index("4) NHỊP BÁN") if "4) NHỊP BÁN" in t else t.index("5) BÁN KÈM")]
    assert muc3.count("• ") == len(can)
    doan = _doan_kieu(tin[0], tin[0].kieu)
    assert any(c in (canh_bao.TRAO_DOI_NGAY, canh_bao.THEO_DOI, tp.GIAM_CUNG_KY) and "c_db342e" in st for c, st in doan)    # nhãn đỏ


def test_nhan_dinh_phong_khong_nhac_truong_phong_nguoi_nghi_nhung_so_phong_van_du(monkeypatch):
    bn = bcp.bang_nhan_su("2026-09", 11, "IBB7")
    data = bn[bn.loai_dong == "data"]
    top, nghi = data.iloc[0], data.iloc[1]
    monkeypatch.setattr(canh_bao, "acc_khong_xet", lambda them=(): {top.acc_norm: "Trưởng phòng", nghi.acc_norm: "Đã nghỉ"})
    chung, ns, can, tin = _nd_phong("IBB7")
    t = "\n".join(map(str, tin))
    assert str(top.ho_ten) not in t and str(nghi.ho_ten) not in t
    q = chung["tq"][chung["tq"].phong_code == "IBB7"].iloc[0]
    assert int(q["online"]) == sum(int(x) for x in data.online)                  # số phòng vẫn gồm hai người đó
    assert f"Chia bình quân {len(ns[1])} nhân sự" in t and len(ns[1]) == len(data) - 2


def test_nhan_dinh_phong_nguoi_trong_khong_trao_doi_ibb7_khong_bi_nhac():
    _, _, can, tin = _nd_phong("IBB7")
    t = "\n".join(map(str, tin))
    for acc in tp.rules_config()["ban_tin"]["khong_trao_doi"]["IBB7"]:
        assert acc not in set(can["acc_norm"])


def test_nhan_dinh_phong_tach_nhieu_tin_con_khi_dai_va_khong_mat_nguoi(monkeypatch):
    chung, ns, can, tin = _nd_phong("DIENBAN")
    monkeypatch.setattr(bt, "TOI_DA_KY_TU", 700)
    chung, ns, can, nhieu = _nd_phong("DIENBAN")
    assert len(nhieu) >= 2 and all(len(x) <= 700 for x in nhieu)
    assert all(f"({i}/{len(nhieu)})" in x for i, x in enumerate(nhieu, 1))
    t = "\n".join(map(str, nhieu))
    assert all(str(r["ho_ten"]) in t for _, r in can.iterrows())
    assert not any(str(x).startswith("\n") for x in nhieu)


def test_nhan_dinh_phong_khong_ten_khach_hang():
    from sqlalchemy import text

    from app.db import engine
    bi_mat = "KHACH_BI_MAT_XYZ"
    with engine.begin() as c:
        c.execute(text("UPDATE fact_internet SET ten_khach_hang = :t WHERE ten_khach_hang IS NULL"), {"t": bi_mat})
    try:
        t = "\n".join(map(str, _nd_phong("IBB7")[3]))
    finally:
        with engine.begin() as c:
            c.execute(text("UPDATE fact_internet SET ten_khach_hang = NULL WHERE ten_khach_hang = :t"), {"t": bi_mat})
    assert bi_mat not in t


# ------------------------------------------------------------------ gửi cho trưởng phòng
def test_truong_phong_nhan_anh_phong_anh_tong_roi_nhan_dinh_dung_thu_tu(gia):
    _them("TP A", ["IBB7"], chat="a")
    kq = bt.chay(gio_vn=SANG_8H)
    assert not kq["loi"] and kq["da_gui"] == ["TP A (phòng IBB7)"]
    assert [x[0] for x in gia.log[:2]] == ["anh", "anh"] and all(x[0] == "tin" for x in gia.log[2:]) and len(gia.log) >= 3
    (phong, tong) = gia.anh_cho("a")
    assert phong[0] == (NGAY, "IBB7") and tong[0] == (NGAY, None)
    assert phong[1] == f"Báo cáo phòng IBB7 - số chốt ngày 11/09\nXem chi tiết: {APP}"
    assert tong[1] == f"Báo cáo Tổng - số chốt ngày 11/09\nXem chi tiết: {APP}"
    assert gia.cho("a")[0].startswith("NHẬN ĐỊNH & HÀNH ĐỘNG - IBB7")
    assert not any("Tổng quan phòng" in t for t in gia.cho("a"))
    loai = _loai_ok("TP A")
    assert {"tp:IBB7:ap", "tp:IBB7:at", "tp:IBB7:nd1", "tp:IBB7:ht"} <= loai and not any(":ns" in x or x.endswith(":tq") for x in loai)
    assert all(len(x) <= 20 for x in loai)


def test_nguoi_phong_a_khong_nhan_so_phong_b(gia):
    _them("TP A", ["IBB7"], chat="a")
    _them("TP B", ["IBB3"], chat="b")
    bt.chay(gio_vn=SANG_8H)
    assert [p[0][1] for p in gia.anh_cho("a")] == ["IBB7", None] and [p[0][1] for p in gia.anh_cho("b")] == ["IBB3", None]
    assert all("IBB7" in t and "IBB3" not in t for t in gia.cho("a"))
    assert all("IBB3" in t and "- IBB7" not in t for t in gia.cho("b"))         # phòng khác chỉ xuất hiện ở dòng so hạng
    ten_a = {str(x) for x in bcp.bang_nhan_su("2026-09", 11, "IBB7").ho_ten if x}
    assert not [n for n in ten_a if len(n) > 5 and any(n in t for t in gia.cho("b"))]       # không lộ nhân sự phòng khác


def test_nguoi_hai_phong_nhan_du_hai_bo_va_goi_hai_lan_khong_trung(gia):
    _them("TP", ["IBB7", "IBB3"], chat="a")
    bt.chay(gio_vn=SANG_8H)
    assert [p[0][1] for p in gia.anh_cho("a")] == ["IBB7", None, "IBB3", None]
    so_tin, so_anh = len(gia.cho("a")), len(gia.anh)
    kq = bt.chay(gio_vn=SANG_8H)
    assert len(gia.cho("a")) == so_tin and len(gia.anh) == so_anh and kq["da_gui"] == []


def test_goi_lan_hai_khong_dung_lai_noi_dung_cho_phong_da_xong(gia, monkeypatch):
    _them("TP", ["IBB7"], chat="a")
    bt.chay(gio_vn=SANG_8H)
    monkeypatch.setattr(tp, "dung_goi_phong", lambda *a, **k: (_ for _ in ()).throw(AssertionError("không dựng lại phòng đã xong")))
    kq = bt.chay(gio_vn=SANG_8H)
    assert not kq["loi"]


def test_mat_anh_phong_thi_thay_bang_tin_tung_nhan_su_van_co_anh_tong_va_nhan_dinh(gia):
    _them("TP", ["IBB7"], chat="a")
    gia.hong_anh.add("phong")
    kq = bt.chay(gio_vn=SANG_8H)
    assert not kq["loi"] and kq["dung_ban_chu"] == ["TP (phòng IBB7)"]
    assert [p[0][1] for p in gia.anh_cho("a")] == [None]                              # chỉ còn ảnh Tổng
    chu = gia.cho("a")
    assert chu[0].startswith("Số chốt ngày 11/09 - IBB7") and "TĂNG hoặc bằng cùng kỳ" in chu[0]     # Từng nhân sự thay ảnh phòng
    assert chu[-1].startswith("NHẬN ĐỊNH & HÀNH ĐỘNG - IBB7")
    assert gia.log[0][0] == "tin" and ("anh", "a") in gia.log
    loai = _loai_ok("TP")
    assert {"tp:IBB7:ap", "tp:IBB7:ns1", "tp:IBB7:at", "tp:IBB7:nd1", "tp:IBB7:ht"} <= loai
    ap = next(v for (i, l), v in _nhat_ky().items() if l == "tp:IBB7:ap")
    assert ap[0] == "ok" and "ảnh giả lập" in ap[1]
    bt.chay(gio_vn=SANG_8H)
    assert len(gia.cho("a")) == len(chu)


def test_mat_anh_tong_thi_bo_qua_khong_thay(gia):
    _them("TP", ["IBB7"], chat="a")
    gia.hong_anh.add("tong")
    kq = bt.chay(gio_vn=SANG_8H)
    assert not kq["loi"] and kq["bo_anh"] == ["TP (phòng IBB7) · tong"] and "dung_ban_chu" not in kq
    assert [p[0][1] for p in gia.anh_cho("a")] == ["IBB7"]
    assert not any(t.startswith("Số chốt ngày") for t in gia.cho("a"))
    assert gia.cho("a")[0].startswith("NHẬN ĐỊNH & HÀNH ĐỘNG")
    at = next(v for (i, l), v in _nhat_ky().items() if l == "tp:IBB7:at")
    assert at[0] == "ok" and "Bỏ qua ảnh" in at[1]


def test_khong_co_app_url_thi_ca_hai_anh_roi_ve_ban_chu(gia, monkeypatch):
    monkeypatch.delenv("APP_URL")
    _them("TP", ["IBB7"], chat="a")
    kq = bt.chay(gio_vn=SANG_8H)
    assert not kq["loi"] and gia.anh == [] and kq["dung_ban_chu"] == ["TP (phòng IBB7)"] and kq["bo_anh"]
    assert gia.cho("a")[0].startswith("Số chốt ngày 11/09 - IBB7") and gia.cho("a")[-1].startswith("NHẬN ĐỊNH")
    assert "APP_URL" in next(v for (i, l), v in _nhat_ky().items() if l == "tp:IBB7:ap")[1]


def test_nhan_dinh_loi_giua_chung_luot_sau_chi_gui_phan_con_thieu(gia):
    _them("TP", ["IBB7"], chat="a")
    gia.hong_chu.add("a")
    kq = bt.chay(gio_vn=SANG_8H)
    assert len(gia.anh) == 2 and gia.tin == [] and kq["loi"][0]["nguoi"] == "TP (phòng IBB7)" and kq["da_gui"] == []
    gia.hong_chu.clear()
    kq = bt.chay(gio_vn=SANG_8H)
    assert len(gia.anh) == 2 and kq["da_gui"] == ["TP (phòng IBB7)"] and len(gia.tin) >= 1        # ảnh không gửi lại
    assert "tp:IBB7:ht" in _loai_ok("TP")
    n = len(gia.tin)
    bt.chay(gio_vn=SANG_8H)
    assert len(gia.tin) == n and len(gia.anh) == 2


def test_tp_dang_chu_giu_nguyen_hanh_vi_cu(gia, monkeypatch):
    monkeypatch.setattr(config, "rules_config", lambda: {"ban_tin": {"tp_dang": "chu", "bgd_dang": "chu"}})
    _them("TP", ["IBB7"], chat="a")
    kq = bt.chay(gio_vn=SANG_8H)
    assert not kq["loi"] and gia.anh == [] and "dung_ban_chu" not in kq
    chu = gia.cho("a")
    assert chu[0].startswith("Số chốt ngày 11/09 - IBB7") and "Tổng quan phòng IBB7" in chu[0]
    assert not any(t.startswith("NHẬN ĐỊNH") for t in chu)
    assert {"tp:IBB7:tq", "tp:IBB7:ns1", "tp:IBB7:ht"} <= _loai_ok("TP") and not any(":ap" in x or ":nd" in x for x in _loai_ok("TP"))


def test_mot_phong_dung_loi_khong_chan_phong_khac_va_bgd(gia, monkeypatch):
    _them("TP A", ["IBB7"], chat="a")
    _them("TP B", ["IBB3"], chat="b")
    _them("Anh BGĐ", None, chat="g", loai="bgd")
    goc = tp.dung_goi_phong

    def hong(ngay, ma, chung=None, anh=True):
        if ma == "IBB3":
            raise RuntimeError("https://x/botSECRET")
        return goc(ngay, ma, chung, anh)
    monkeypatch.setattr(tp, "dung_goi_phong", hong)
    kq = bt.chay(gio_vn=SANG_8H)
    assert gia.cho("b") == [] and gia.anh_cho("b") == [] and gia.anh_cho("a") and gia.cho("a")
    assert gia.anh_cho("g") and gia.cho("g") and any("IBB3" in e["nguoi"] for e in kq["loi"]) and "SECRET" not in str(kq)


def test_het_thoi_gian_thi_de_lai_luot_sau(gia):
    _them("TP", ["IBB7"], chat="a")
    kq = bt.chay(gio_vn=SANG_8H, han_giay=-1)
    assert gia.tin == [] and gia.anh == [] and "thời gian" in kq["ly_do"]
    assert bt.chay(gio_vn=SANG_8H)["da_gui"] == ["TP (phòng IBB7)"]


def test_nhat_ky_gan_day_nhan_ten_anh_va_nhan_dinh(gia):
    _them("TP", ["IBB7"], chat="a")
    _them("Anh BGĐ", None, chat="g", loai="bgd")
    bt.chay(gio_vn=SANG_8H)
    nhan = {r["loai"] for r in bt.nhat_ky_gan_day(30)}
    assert {"TP IBB7 · ảnh Báo cáo phòng", "TP IBB7 · ảnh Báo cáo Tổng", "TP IBB7 · nhận định 1", "Bản tin",
            "Nhận định & hành động"} <= nhan
    assert not any(r["loai"].endswith("ht") for r in bt.nhat_ky_gan_day(30))


# ------------------------------------------------------------------ Ban Giám đốc cùng lượt + gửi thử + chạy thử
def test_bgd_va_truong_phong_cung_luot_moi_nguoi_dung_chuoi_cua_minh(gia):
    _them("Anh BGĐ", None, chat="g", loai="bgd")
    _them("TP", ["IBB7"], chat="a")
    kq = bt.chay(gio_vn=SANG_8H)
    assert set(kq["da_gui"]) == {"Anh BGĐ", "TP (phòng IBB7)"}
    assert [p[0][1] for p in gia.anh_cho("g")] == [None] and len(gia.cho("g")) == 1
    assert gia.cho("g")[0].startswith("NHẬN ĐỊNH & HÀNH ĐỘNG ·")


def test_gui_thu_truong_phong_gui_dung_chuoi_moi_co_nhan_ban_thu(gia):
    _them("TP", ["IBB7"], chat="a")
    ok, msg = bt.gui_thu(bt.ds_nguoi_nhan()[0]["id"])
    assert ok and "2 ảnh" in msg and "bản chữ" not in msg
    assert [x[0] for x in gia.log[:2]] == ["anh", "anh"] and gia.log[2][0] == "tin"
    caps = [c for _, _, c in gia.anh]
    assert caps[0].startswith("[BẢN THỬ]\nBáo cáo phòng IBB7") and caps[1].startswith("[BẢN THỬ]\nBáo cáo Tổng")
    assert all(t.startswith("[BẢN THỬ]\n") for t in gia.cho("a")) and "NHẬN ĐỊNH & HÀNH ĐỘNG" in gia.cho("a")[0]
    assert _nhat_ky() == {}


def test_gui_thu_truong_phong_mat_anh_noi_ro_dung_ban_chu(gia):
    _them("TP", ["IBB7"], chat="a")
    gia.hong_anh.add("phong")
    ok, msg = bt.gui_thu(bt.ds_nguoi_nhan()[0]["id"])
    assert ok and "bản chữ thay" in msg and "ảnh giả lập" in msg and "1 ảnh" in msg
    assert gia.cho("a")[0].startswith("[BẢN THỬ]\nSố chốt ngày 11/09 - IBB7")
    gia.hong_chu.add("a")
    assert not bt.gui_thu(bt.ds_nguoi_nhan()[0]["id"])[0]


def test_gui_thu_truong_phong_tp_dang_chu_la_ban_cu(gia, monkeypatch):
    monkeypatch.setattr(config, "rules_config", lambda: {"ban_tin": {"tp_dang": "chu"}})
    _them("TP", ["IBB7"], chat="a")
    ok, msg = bt.gui_thu(bt.ds_nguoi_nhan()[0]["id"])
    assert ok and gia.anh == [] and "0 ảnh" in msg and "Tổng quan phòng IBB7" in gia.cho("a")[0]


def test_kho_voi_phong_tra_nhan_dinh_phong_khong_gui_khong_ghi(gia, monkeypatch):
    _them("TP A", ["IBB7"], chat="a")
    monkeypatch.setattr(ba, "tao_ma", lambda *a, **k: (_ for _ in ()).throw(AssertionError("không tạo mã khi chạy thử")))
    kq = bt.chay(gio_vn=SANG_8H, kho=True, phong="IBB7")
    assert kq["tp_dang"] == "anh" and kq["nhan_dinh_phong"][0].startswith("NHẬN ĐỊNH & HÀNH ĐỘNG - IBB7")
    assert kq["kich_thuoc_nhan_dinh"][0]["so_kieu"] > 0 and kq["noi_dung_phong"][0].startswith("Số chốt ngày 11/09 - IBB7")
    assert gia.tin == [] and gia.anh == [] and _nhat_ky() == {}
    assert "nhan_dinh_phong" not in bt.chay(gio_vn=SANG_8H, kho=True)
