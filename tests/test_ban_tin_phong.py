"""Kiểm thử Bản tin 8h cho trưởng phòng. Chặn mạng bằng giả lập `zalo_bot.gui_tin`, dùng database thử (ngày số 11/09)."""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import ban_tin as bt                                           # noqa: E402
from app import ban_tin_phong as tp                                     # noqa: E402
from app import bao_cao_phong as bcp                                    # noqa: E402
from app import canh_bao, metrics, overview, zalo_bot                   # noqa: E402
from app.config import DATA_DIR                                          # noqa: E402

pytestmark = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(),
                                reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")
NGAY = "2026-09-11"
SANG_8H = datetime(2026, 9, 12, 8, 5)
CHOT = (False, datetime(2026, 9, 12, 7, 0))


class Gia:
    """Bản giả của `zalo_bot.gui_tin`: ghi từng tin; `hong` = chat_id luôn lỗi; `hong_lan` = lần gọi thứ n (từ 1) bị lỗi."""

    def __init__(self):
        self.tin: list[tuple[str, str]] = []
        self.kieu: list = []
        self.hong: set[str] = set()
        self.hong_lan: set[int] = set()
        self.so_goi = 0

    def __call__(self, chat_id, noi_dung, parse_mode=None, han=8, text_styles=None):
        self.so_goi += 1
        if chat_id in self.hong or self.so_goi in self.hong_lan:
            raise zalo_bot.LoiZalo("Zalo từ chối (mã 400): giả lập.")
        self.tin.append((chat_id, noi_dung))
        self.kieu.append(text_styles)

    def cho(self, chat_id):
        return [t for c, t in self.tin if c == chat_id]


@pytest.fixture()
def gia(monkeypatch):
    g = Gia()
    monkeypatch.setattr(zalo_bot, "gui_tin", g)
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
    monkeypatch.delenv("APP_URL", raising=False)
    yield
    don()


def _them(ten, phong, chat="c1", loai="truong_phong", bat=True):
    ok, msg = bt.luu_nguoi_nhan(None, ten, loai, chat, bat, phong)
    assert ok, msg


def _nhat_ky():
    from sqlalchemy import select

    from app.db import session_scope
    from app.models import BanTinNhatKy
    with session_scope() as s:
        return [(r.nguoi_nhan_id, r.loai, r.ket_qua) for r in s.execute(select(BanTinNhatKy)).scalars()]


def _doan_kieu(chu, kieu):
    u16 = chu.encode("utf-16-le")
    return [(u16[k["start"] * 2:(k["start"] + k["len"]) * 2].decode("utf-16-le"), k["st"]) for k in kieu]


# ------------------------------------------------------------------ người nhận + phòng
def test_truong_phong_bat_buoc_co_phong():
    assert not bt.luu_nguoi_nhan(None, "TP", "truong_phong", "c", True)[0]
    assert not bt.luu_nguoi_nhan(None, "TP", "truong_phong", "c", True, [])[0]
    assert bt.ds_nguoi_nhan() == []


def test_loai_khac_khong_luu_phong():
    _them("Anh A", ["IBB7"], loai="bgd")
    n = bt.ds_nguoi_nhan()[0]
    assert n["phong"] == [] and n["phong_ten"] == "" and tp.phong_theo_nguoi() == {}


def test_chi_phong_ban_hang_chon_duoc():
    for sai in ("KT_DNG1", "CUS_DNG1", "ECOM_DNG", "ANCS", "KHONG_CO"):
        assert not bt.luu_nguoi_nhan(None, "TP", "truong_phong", "c", True, [sai])[0], sai
    assert not bt.luu_nguoi_nhan(None, "TP", "truong_phong", "c", True, ["IBB7", "KT_DNG1"])[0]
    ma = {p["code"] for p in tp.phong_chon_duoc()}
    assert {"IBB1", "IBB7", "HOIAN"} <= ma and not ma & {"KT_DNG1", "ECOM_DNG", "ANCS"}


def test_mot_nguoi_nhieu_phong_sua_va_doi_loai():
    _them("TP", ["IBB7", "IBB3", "IBB7"])
    n = bt.ds_nguoi_nhan()[0]
    assert n["phong"] == ["IBB7", "IBB3"] and "IBB3" in n["phong_ten"]
    assert bt.luu_nguoi_nhan(n["id"], "TP", "truong_phong", "c1", True, ["IBB3", "HOIAN"])[0]
    assert sorted(bt.lay_nguoi_nhan(n["id"])["phong"]) == ["HOIAN", "IBB3"]
    assert bt.luu_nguoi_nhan(n["id"], "TP", "bgd", "c1", True, ["IBB3"])[0]           # đổi loại: bỏ hết phòng
    assert bt.lay_nguoi_nhan(n["id"])["phong"] == [] and tp.phong_theo_nguoi() == {}


def test_xoa_nguoi_nhan_xoa_ca_phong():
    _them("TP", ["IBB7", "IBB3"])
    _them("TP2", ["IBB1"], chat="c2")
    a = bt.ds_nguoi_nhan()[0]["id"]
    assert bt.xoa_nguoi_nhan([a]) == 1
    assert list(tp.phong_theo_nguoi().values()) == [["IBB1"]]


def test_duyet_tu_danh_sach_cho_voi_phong():
    from sqlalchemy import select

    from app import ban_tin_cho_duyet as cd
    from app.db import session_scope
    from app.models import BanTinChoDuyet
    cd.dam_bao_bang()
    with session_scope() as s:
        s.add(BanTinChoDuyet(chat_id="moi1", ten="Chị M"))
    with session_scope() as s:
        id_ = s.execute(select(BanTinChoDuyet.id).where(BanTinChoDuyet.chat_id == "moi1")).scalar()
    assert not cd.duyet(id_, "Chị M", "truong_phong", [])[0]
    ok, _ = cd.duyet(id_, "Chị M", "truong_phong", ["IBB7"])
    assert ok and bt.ds_nguoi_nhan()[0]["phong"] == ["IBB7"]


def test_ma_loai_tin_vua_cot_loai_20_ky_tu():
    for p in tp.phong_chon_duoc():
        assert len(tp.ma_loai(p["code"], "ns99")) <= 20, p["code"]


# ------------------------------------------------------------------ tin 1: tổng quan
def test_tin_tong_quan_co_tien_do_hang_du_bao_nhan_dinh_va_dung_so():
    chung = tp.nap_chung(NGAY)
    phan, tin = tp.dung_tin_phong(NGAY, "IBB7", chung)[0]
    assert phan == "tq"
    for cum in ("Số chốt ngày 11/09 - IBB7", "NHẬN ĐỊNH NHANH", "1) TIẾN ĐỘ", "Online luỹ kế", "mục tiêu tháng", "hạng ",
                "phòng bán hàng", "Cùng kỳ tháng 8", "Dự báo cuối tháng", "2) CẦN TRAO ĐỔI", "3) CHẤT LƯỢNG BÁN",
                "V.VIP/PTTB", "Camera/online", "cả chi nhánh", "online/ngày"):
        assert cum in tin, cum
    assert re.search(r"Dự báo cuối tháng: [\d.]+ \([\d.]+\)", tin)
    assert len(tin) <= bt.TOI_DA_KY_TU and "đấu nối" not in tin.lower()
    tq = chung["tq"]
    q = tq[tq.phong_code == "IBB7"].iloc[0]
    assert f"Online luỹ kế: {bt._so(q['online'])}" in tin
    bn = bcp.bang_nhan_su("2026-09", 11, "IBB7")
    assert int(q["online"]) == int(bn[bn.loai_dong == "total"].iloc[0]["online"])


def test_tong_nhan_su_ca_truong_phong_bang_dong_tong_va_bao_cao_tong():
    chung = tp.nap_chung(NGAY)
    bn = bcp.bang_nhan_su("2026-09", 11, "IBB7")
    data, tong = bn[bn.loai_dong == "data"], bn[bn.loai_dong == "total"].iloc[0]
    q = chung["tq"][chung["tq"].phong_code == "IBB7"].iloc[0]
    assert sum(int(x) for x in data.online) == int(tong["online"]) == int(q["online"])


def test_hang_cung_cach_xep_bao_cao_phong():
    chung = tp.nap_chung(NGAY)
    hang, so = tp._hang(chung, "IBB7")
    ss, _ = bcp.so_sanh_phong("2026-09", 11, "IBB7")
    r = ss[ss.khoa == "online"].iloc[0]
    assert (hang, so) == (int(r["hang"]), int(r["so_phong"]))
    assert f"hạng {hang}/{so}" in tp.dung_tin_phong(NGAY, "IBB7", chung)[0][1]


def test_tin_tong_quan_co_ly_do_can_trao_doi():
    chung = tp.nap_chung(NGAY)
    _, xet, _ = tp._nhan_su(chung, "IBB7")
    co = xet[xet.muc_chu_y.isin([canh_bao.TRAO_DOI_NGAY, canh_bao.THEO_DOI])]
    assert len(co)
    tin = str(tp.dung_tin_phong(NGAY, "IBB7", chung)[0][1])
    for _, r in co.head(2).iterrows():
        assert str(r["ho_ten"]) in tin
    assert canh_bao.THEO_DOI in tin or canh_bao.TRAO_DOI_NGAY in tin


def test_tin_tong_quan_dai_thi_cat_gon_van_trong_gioi_han(monkeypatch):
    day_du = tp.dung_tin_phong(NGAY, "IBB7")[0][1]
    monkeypatch.setattr(bt, "TOI_DA_KY_TU", len(day_du) - 150)
    ngan = tp.dung_tin_phong(NGAY, "IBB7")[0][1]
    assert len(ngan) <= len(day_du) - 150 and "1) TIẾN ĐỘ" in ngan


def test_kieu_chu_dung_vi_tri_va_mau():
    tin = tp.dung_tin_phong(NGAY, "IBB7")[0][1]
    tong = len(tin.encode("utf-16-le")) // 2
    assert tin.kieu and all(k["start"] >= 0 and k["len"] > 0 and k["start"] + k["len"] <= tong for k in tin.kieu)
    doan = _doan_kieu(tin, tin.kieu)
    assert any(c.startswith("Số chốt ngày") and "b" in st for c, st in doan)
    for tieu_de in ("1) TIẾN ĐỘ", "2) CẦN TRAO ĐỔI"):
        assert any(c == tieu_de and "b" in st for c, st in doan)
    assert any(c in (canh_bao.TRAO_DOI_NGAY, canh_bao.THEO_DOI) and any(s.startswith("c_") for s in st) for c, st in doan)


def test_phong_khong_co_nguoi_can_trao_doi_ghi_dong_xanh():
    chung = tp.nap_chung(NGAY)
    _, xet, _ = tp._nhan_su(chung, "IBB7")
    can = tp.can_trao_doi(xet.assign(muc_chu_y="", ck_online=0), "IBB7")      # không cảnh báo, không ai thấp hơn cùng kỳ
    s = tp._khoi_trao_doi(can, "8").xong()
    assert ("\nKhông có nhân sự cần trao đổi.", ["c_15a85f"]) in _doan_kieu(s, s.kieu)


def _xet_gia(n: int, **kw):
    import pandas as pd
    return pd.DataFrame([{"acc_norm": f"a{i}", "ho_ten": f"Người {i}", "online": 10, "ck_online": 20, "muc_chu_y": "",
                          "chu_y": "", **kw} for i in range(n)])


def test_can_trao_doi_them_nguoi_thap_hon_cung_ky_va_khong_gioi_han():
    import pandas as pd
    x = pd.concat([_xet_gia(1, muc_chu_y=canh_bao.TRAO_DOI_NGAY, chu_y="7 ngày chưa có số"),
                   _xet_gia(30).assign(acc_norm=lambda d: "g" + d.acc_norm),
                   _xet_gia(3, ck_online=5).assign(acc_norm=lambda d: "t" + d.acc_norm)], ignore_index=True)
    can = tp.can_trao_doi(x, "IBB2")
    assert len(can) == 31                                  # 1 có cảnh báo + 30 giảm so cùng kỳ, 3 người tăng bị bỏ
    assert can.iloc[0]["muc"] == canh_bao.TRAO_DOI_NGAY and set(can.iloc[1:]["muc"]) == {tp.GIAM_CUNG_KY}
    dong = str(tp._dong_trao_doi(can.iloc[5], "9").xong())
    assert "giảm 10 so T9 (-50%)" in dong and "10 online" in dong


def test_can_trao_doi_ibb7_bo_khanh_va_duy_nhung_phong_khac_van_co():
    x = _xet_gia(3)
    x["acc_norm"] = ["dng.khanhvhg", "dng.duynt121", "dng.rinnd2"]
    assert list(tp.can_trao_doi(x, "IBB7")["acc_norm"]) == ["dng.rinnd2"]
    assert len(tp.can_trao_doi(x, "IBB2")) == 3


def test_danh_sach_trao_doi_dai_thi_tach_tin_rieng_du_nguoi(monkeypatch):
    chung = tp.nap_chung(NGAY)
    can = tp.can_trao_doi(_xet_gia(70), "IBB2")
    tin = tp.dung_tin_trao_doi(chung, "IBB7", can)
    assert len(tin) >= 2 and all(len(t) <= bt.TOI_DA_KY_TU for t in tin)
    assert all(f"Người {i}" in "\n".join(tin) for i in range(70))
    monkeypatch.setattr(tp, "can_trao_doi", lambda *_a, **_k: can)
    phan = tp.dung_tin_phong(NGAY, "IBB7", chung)
    ten = [p for p, _ in phan]
    assert ten[0] == "tq" and ten[1] == "td1" and any(p.startswith("ns") for p in ten)
    assert "danh sách ở tin kế tiếp" in phan[0][1] and len(phan[0][1]) <= bt.TOI_DA_KY_TU


def test_khong_co_ten_khach_hang():
    from sqlalchemy import text

    from app.db import engine
    bi_mat = "KHACH_BI_MAT_XYZ"
    with engine.begin() as c:
        c.execute(text("UPDATE fact_internet SET ten_khach_hang = :t WHERE ten_khach_hang IS NULL"), {"t": bi_mat})
    try:
        chu = " ".join(str(t) for _, t in tp.dung_tin_phong(NGAY, "IBB7"))
    finally:
        with engine.begin() as c:
            c.execute(text("UPDATE fact_internet SET ten_khach_hang = NULL WHERE ten_khach_hang = :t"), {"t": bi_mat})
    assert bi_mat not in chu


# ------------------------------------------------------------------ tin 2: từng nhân sự
def test_tin_nhan_su_khong_co_truong_phong_va_nguoi_nghi_nhung_so_phong_van_du(monkeypatch):
    bn = bcp.bang_nhan_su("2026-09", 11, "IBB7")
    data = bn[bn.loai_dong == "data"]
    top, nghi = data.iloc[0], data.iloc[1]
    monkeypatch.setattr(canh_bao, "acc_khong_xet",
                        lambda them=(): {top.acc_norm: "Trưởng phòng", nghi.acc_norm: "Đã nghỉ"})
    tin = tp.dung_tin_phong(NGAY, "IBB7")
    chu = "\n".join(str(t) for p, t in tin if p.startswith("ns"))
    assert str(top.ho_ten) not in chu and str(nghi.ho_ten) not in chu and "Số chốt ngày 11/09 - IBB7" in chu
    assert str(top.ho_ten) not in str(tin[0][1])
    tong = sum(int(x) for x in data.online)
    assert f"Online luỹ kế: {bt._so(tong)}" in str(tin[0][1])        # số phòng vẫn gồm cả hai người đó


def test_tin_nhan_su_xep_online_giam_dan_va_chenh_cung_ky():
    chung = tp.nap_chung(NGAY)
    _, xet, _ = tp._nhan_su(chung, "IBB7")
    ns = [t for p, t in tp.dung_tin_phong(NGAY, "IBB7", chung) if p.startswith("ns")]
    dong = [d for t in ns for d in str(t).split("\n") if d.startswith("• ")]
    assert len(dong) == len(xet)
    online = [int(d.split(": ")[1].split(" online")[0].replace(".", "")) for d in dong]
    assert online == sorted(online, reverse=True)
    r = xet.sort_values("online", ascending=False, kind="stable").iloc[0]
    chenh = int(r["online"]) - int(r["ck_online"])
    assert (f"{chenh:+d}" if chenh else "0") in dong[0] and "so T8" in dong[0]


def test_tin_nhan_su_tach_tin_con_khi_vuot_1900_ky_tu():
    chung = {"ngay_iso": NGAY, "thang_truoc": "2026-08"}
    xet = pd.DataFrame({"ho_ten": [f"Nhân sự số {i:03d} có tên khá dài" for i in range(120)],
                        "online": list(range(120, 0, -1)), "online_ngay": [1] * 120, "ck_online": [5] * 120})
    ds = tp.dung_tin_nhan_su(chung, "IBB7", xet)
    assert len(ds) >= 3 and all(len(t) <= 1900 for t in ds)
    assert all(f"({i}/{len(ds)})" in t for i, t in enumerate(ds, 1))
    dong = [d for t in ds for d in str(t).split("\n") if d.startswith("• ")]
    assert len(dong) == 120 and dong[0].startswith("• Nhân sự số 000") and dong[-1].startswith("• Nhân sự số 119")
    for t in ds:                                           # kiểu chữ khớp vị trí UTF-16 (tên đậm, chênh có màu)
        doan = _doan_kieu(t, t.kieu)
        assert any(c.startswith("Nhân sự số") and "b" in st for c, st in doan)
        assert any(c.startswith("+") and "c_15a85f" in st for c, st in doan)


def test_khong_co_nhan_su_thi_bo_tin_2():
    chung = {"ngay_iso": NGAY, "thang_truoc": "2026-08"}
    assert tp.dung_tin_nhan_su(chung, "IBB7", pd.DataFrame(columns=["ho_ten", "online"])) == []


# ------------------------------------------------------------------ gửi
def test_chua_chot_hoac_truoc_8h_khong_gui(gia, monkeypatch):
    _them("TP", ["IBB7"])
    assert bt.chay(gio_vn=datetime(2026, 9, 12, 7, 59))["da_gui"] == [] and gia.tin == []
    monkeypatch.setattr(overview, "trang_thai_ngay", lambda iso: (True, datetime(2026, 9, 11, 14, 30)))
    assert bt.chay(gio_vn=SANG_8H)["da_gui"] == [] and gia.tin == [] and _nhat_ky() == []


def test_gui_dung_nguoi_dung_phong(gia):
    _them("TP A", ["IBB7"], chat="a")
    _them("TP B", ["IBB3"], chat="b")
    _them("TP tắt", ["IBB7"], chat="t", bat=False)
    _them("Anh BGĐ", None, chat="g", loai="bgd")
    kq = bt.chay(gio_vn=SANG_8H)
    assert gia.cho("t") == []
    assert all("IBB7" in t for t in gia.cho("a")) and not any("IBB3" in t for t in gia.cho("a"))
    assert all("IBB3" in t for t in gia.cho("b")) and not any("IBB7" in t for t in gia.cho("b"))
    assert len(gia.cho("g")) == 1 and "Toàn chi nhánh" in gia.cho("g")[0]
    assert set(kq["da_gui"]) == {"Anh BGĐ", "TP A (phòng IBB7)", "TP B (phòng IBB3)"}
    assert gia.cho("a")[0].startswith("Số chốt ngày 11/09 - IBB7")        # tin 1 trước tin 2


def test_nguoi_hai_phong_nhan_du_hai_bo_va_goi_hai_lan_khong_trung(gia):
    _them("TP", ["IBB7", "IBB3"], chat="a")
    bt.chay(gio_vn=SANG_8H)
    so_tin = len(gia.cho("a"))
    chu = "\n".join(map(str, gia.cho("a")))
    assert so_tin >= 4 and "- IBB7" in chu and "- IBB3" in chu
    kq = bt.chay(gio_vn=SANG_8H)
    assert len(gia.cho("a")) == so_tin and kq["da_gui"] == []
    loai = {ten for _, ten, k in _nhat_ky() if k == "ok"}
    assert {"tp:IBB7:tq", "tp:IBB7:ht", "tp:IBB3:tq", "tp:IBB3:ht"} <= loai


def test_nap_lai_file_khong_gui_lai(gia, monkeypatch):
    _them("TP", ["IBB7"], chat="a")
    bt.chay(gio_vn=SANG_8H)
    n = len(gia.cho("a"))
    monkeypatch.setattr(overview, "trang_thai_ngay", lambda iso: (False, datetime(2026, 9, 12, 9, 30)))
    bt.chay(gio_vn=datetime(2026, 9, 12, 9, 45))
    assert len(gia.cho("a")) == n


def test_loi_giua_chung_lan_sau_gui_tiep_phan_con_thieu(gia):
    _them("TP", ["IBB7"], chat="a")
    gia.hong_lan = {2}                                     # tin 1 ok, tin 2 lỗi
    kq = bt.chay(gio_vn=SANG_8H)
    assert len(gia.cho("a")) == 1 and kq["loi"][0]["nguoi"] == "TP (phòng IBB7)" and kq["da_gui"] == []
    gia.hong_lan = set()
    kq = bt.chay(gio_vn=SANG_8H)
    assert kq["da_gui"] == ["TP (phòng IBB7)"] and len(gia.cho("a")) >= 2
    chu = list(map(str, gia.cho("a")))
    assert sum("Tổng quan phòng IBB7" in t for t in chu) == 1            # tin 1 không gửi lại
    bt.chay(gio_vn=SANG_8H)
    assert len(gia.cho("a")) == len(chu)


def test_mot_phong_dung_loi_khong_chan_phong_khac_va_bgd(gia, monkeypatch):
    _them("TP A", ["IBB7"], chat="a")
    _them("TP B", ["IBB3"], chat="b")
    _them("Anh BGĐ", None, chat="g", loai="bgd")
    goc = tp.dung_tin_phong

    def hong(ngay, ma, chung=None):
        if ma == "IBB3":
            raise RuntimeError("https://x/botSECRET")
        return goc(ngay, ma, chung)
    monkeypatch.setattr(tp, "dung_tin_phong", hong)
    kq = bt.chay(gio_vn=SANG_8H)
    assert gia.cho("b") == [] and gia.cho("a") and len(gia.cho("g")) == 1
    assert any("IBB3" in e["nguoi"] for e in kq["loi"]) and "SECRET" not in json.dumps(kq, ensure_ascii=False)


def test_loi_ben_truong_phong_khong_lam_hong_bgd(gia, monkeypatch):
    _them("Anh BGĐ", None, chat="g", loai="bgd")
    monkeypatch.setattr(tp, "_chay_truong_phong", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    kq = bt.chay(gio_vn=SANG_8H)
    assert kq["da_gui"] == ["Anh BGĐ"] and kq["loi"][0]["nguoi"] == "(trưởng phòng)"


def test_het_thoi_gian_thi_de_lai_luot_sau(gia):
    _them("TP", ["IBB7"], chat="a")
    kq = bt.chay(gio_vn=SANG_8H, han_giay=-1)
    assert gia.tin == [] and "thời gian" in kq["ly_do"]
    assert bt.chay(gio_vn=SANG_8H)["da_gui"] == ["TP (phòng IBB7)"]


# ------------------------------------------------------------------ chạy thử + gửi thử + API
def test_kho_khong_gui_khong_ghi_va_tra_tin_cua_phong(gia):
    _them("TP A", ["IBB7"], chat="a")
    _them("TP tắt", ["IBB3"], chat="t", bat=False)
    kq = bt.chay(gio_vn=SANG_8H, kho=True, phong="IBB7")
    assert gia.tin == [] and _nhat_ky() == [] and "Toàn chi nhánh" in kq["noi_dung"]
    assert kq["truong_phong"] == [{"ten": "TP A", "phong": ["IBB7"]}]
    assert kq["noi_dung_phong"][0].startswith("Số chốt ngày 11/09 - IBB7")
    assert "noi_dung_phong" not in bt.chay(gio_vn=SANG_8H, kho=True)
    assert "ly_do_phong" in bt.chay(gio_vn=SANG_8H, kho=True, phong="KT_DNG1")


def test_api_kho_voi_phong_can_khoa(monkeypatch, gia):
    from app.ui.app import server
    monkeypatch.setenv("BAN_TIN_KHOA", "khoa-thu")
    may = server.test_client()
    assert may.post("/api/ban-tin/chay?kho=1&phong=IBB7").status_code == 403
    r = may.post("/api/ban-tin/chay?kho=1&phong=IBB7", headers={"X-Ban-Tin-Khoa": "khoa-thu"}).get_json()
    assert r["kho"] and r["noi_dung_phong"] and gia.tin == [] and _nhat_ky() == []


def test_gui_thu_truong_phong(gia):
    _them("TP", ["IBB7", "IBB3"], chat="a")
    ok, msg = bt.gui_thu(bt.ds_nguoi_nhan()[0]["id"])
    assert ok and "IBB7" in msg
    chu = gia.cho("a")
    assert len(chu) >= 4 and all(t.startswith("[BẢN THỬ - chưa tính là đã gửi]\n") for t in chu)
    assert any(c.startswith("Số chốt ngày") and "b" in st for c, st in _doan_kieu(str(chu[0]), gia.kieu[0]))
    assert _nhat_ky() == []
    gia.hong.add("a")
    assert not bt.gui_thu(bt.ds_nguoi_nhan()[0]["id"])[0]


def test_nhat_ky_gan_day_nhan_tin_va_an_dong_hoan_tat(gia):
    _them("TP", ["IBB7"], chat="a")
    bt.chay(gio_vn=SANG_8H)
    nk = bt.nhat_ky_gan_day(10)
    assert all(not r["loai"].endswith("ht") for r in nk)
    assert any(r["loai"] == "TP IBB7 · tổng quan" for r in nk) and any("nhân sự 1" in r["loai"] for r in nk)
