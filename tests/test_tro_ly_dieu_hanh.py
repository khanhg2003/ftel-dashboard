"""Trợ lý điều hành: bộ quét có bắt hết bất thường cài sẵn không (đo recall / báo nhầm), nội dung luật + LLM giả, sổ quyết định, nhắc / leo thang / kiểm chứng,
lệnh Zalo, công tắc tắt và quyền. Không gọi mạng thật; dữ liệu cài sẵn dựng bằng bảng nhỏ trong test, không sửa dữ liệu số liệu nào của database kiểm thử."""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest
from dash.exceptions import PreventUpdate
from sqlalchemy import delete

from app import ban_tin, ban_tin_cho_duyet as cd, tro_ly_dieu_hanh as tdh, tro_ly_dieu_hanh_nd as nd, tro_ly_dieu_hanh_quet as q, tro_ly_dieu_hanh_so as so, tro_ly_dieu_hanh_zalo as tz, zalo_bot
from app import tro_ly_dieu_hanh_quet_dvkh as qdv, tro_ly_dieu_hanh_quet_kd as qkd
from app.config import DATA_DIR
from app.db import session_scope
from app.models import BanTinChoDuyet, TdPhu, TdQuyetDinh, TdQuyetDinhNk

pytestmark = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(), reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")
NOW = datetime(2026, 9, 16, 1, 0)                        # UTC = 08:00 ngày 16/09 giờ Việt Nam; ngày số 15/09 nên chậm đúng 1 ngày (bình thường)
NGUOI = [{"id": 1, "ten": "Anh Giám đốc", "loai": "bgd", "chat_id": "G1", "phong": [], "bat": True},
         {"id": 2, "ten": "Chị TP bảy", "loai": "truong_phong", "chat_id": "T7", "phong": ["IBB7"], "bat": True},
         {"id": 3, "ten": "Anh TP sáu", "loai": "truong_phong", "chat_id": "T6", "phong": ["IBB6"], "bat": True},
         {"id": 4, "ten": "Admin nạp file", "loai": "admin", "chat_id": "A1", "phong": [], "bat": True}]


# ------------------------------------------------------------------ nền
@pytest.fixture(autouse=True)
def sach():
    def don():
        so.dam_bao_bang()
        with session_scope() as s:
            for b in (TdQuyetDinh, TdQuyetDinhNk, TdPhu, BanTinChoDuyet):
                s.execute(delete(b))
    cd.dam_bao_bang()
    don()
    yield
    don()
    q.DO_CHI_SO.pop("kiem_thu", None)


@pytest.fixture()
def bat(monkeypatch):
    """Công tắc BẬT (mặc định thật là tắt)."""
    cfg = {**so.MAC_DINH, "bat": True}
    monkeypatch.setattr(so, "cau_hinh", lambda: cfg)
    return cfg


@pytest.fixture()
def zalo(monkeypatch):
    """Chặn mạng: ghi lại tin gửi (qua gui_tin_du_phong) và tin trả lời lệnh (qua gui_tin); người nhận giả."""
    gui, tra = [], []
    monkeypatch.setattr(ban_tin, "ds_nguoi_nhan", lambda loai=None, chi_bat=False: [n for n in NGUOI if not loai or n["loai"] == loai])
    monkeypatch.setattr(zalo_bot, "gui_tin_du_phong", lambda chat, tin, *a, **k: gui.append((chat, str(tin))) or False)
    monkeypatch.setattr(zalo_bot, "gui_tin", lambda chat, noi, *a, **k: tra.append((chat, noi)))
    return SimpleNamespace(gui=gui, tra=tra)


# ------------------------------------------------------------------ dữ liệu cài sẵn
def _ns(i: int, **ghi_de) -> dict:
    """Một nhân sự BÌNH THƯỜNG của bảng `bang_nhan_su`: online xấp xỉ cùng kỳ, không tồn lâu, có bán kèm."""
    d = {"acc_norm": f"dng.nv{i:02d}", "acc": f"DNG.NV{i:02d}", "ho_ten": f"Nhân Viên {i:02d}", "loai_dong": "data", "khong_xet": "", "online": 20 + i % 5, "ck_online": 20 + (i * 3) % 5,
         "tuan_nay": 5, "tuan_truoc": 5, "ngay_lien_chua_co_so": 0, "ton": 1, "ton_qua_7": 1, "vvip": 3, "camera": 2, "muc_chu_y": "", "chu_y": ""}
    return {**d, **ghi_de}


def _bang_ns(so_binh_thuong: int = 30):
    """Bảng một phòng: `so_binh_thuong` người bình thường + 8 người cài sẵn bất thường + trưởng phòng và người nghỉ (số xấu nhưng KHÔNG được xét)."""
    thuong = [_ns(i) for i in range(so_binh_thuong)]
    cai = {  # acc -> (các facet phải bắt được, dữ liệu)
        "dng.sg01": ({"online_giam"}, _ns(100, acc_norm="dng.sg01", online=8, ck_online=30)),
        "dng.sg02": ({"online_giam"}, _ns(101, acc_norm="dng.sg02", online=9, ck_online=20)),
        "dng.sg03": ({"online_giam"}, _ns(102, acc_norm="dng.sg03", online=6, ck_online=12)),
        "dng.cb01": ({"canh_bao"}, _ns(103, acc_norm="dng.cb01", muc_chu_y="Trao đổi ngay", chu_y="9 ngày chưa có số")),
        "dng.cb02": ({"canh_bao"}, _ns(104, acc_norm="dng.cb02", muc_chu_y="Theo dõi", chu_y="Tuần này 2, tuần trước 9 (−78%)")),
        "dng.tk01": ({"ton_lau"}, _ns(105, acc_norm="dng.tk01", ton_qua_7=4)),
        "dng.tk02": ({"ton_lau"}, _ns(106, acc_norm="dng.tk02", ton_qua_7=7)),
        "dng.ld01": ({"lech_dong_nghiep"}, _ns(107, acc_norm="dng.ld01", online=5, ck_online=6)),
    }
    khong_xet = [_ns(200, acc_norm="dng.tpx", khong_xet="Trưởng phòng", online=0, ck_online=30, ton_qua_7=9, muc_chu_y="Trao đổi ngay", chu_y="trưởng phòng"),
                 _ns(201, acc_norm="dng.nghi", khong_xet="Đã nghỉ", online=0, ck_online=25, ton_qua_7=8, muc_chu_y="Trao đổi ngay", chu_y="đã nghỉ")]
    return pd.DataFrame(thuong + [v[1] for v in cai.values()] + khong_xet), cai, {t["acc_norm"] for t in thuong}


def _db(rows: list[tuple]) -> pd.DataFrame:
    """Bảng dự báo giả: (mã, mục tiêu, luỹ kế, dự báo, đánh giá)."""
    return pd.DataFrame([{"phong_code": ma, "phong": ma, "mt": mt, "luy_ke": lk, "du_bao": db, "du_bao_nhip": db, "pct_mt": round(db / mt * 100), "can_moi_ngay": max(0, (mt - lk) // 15),
                          "tb_ngay": round(lk / 15, 1), "con_lai": 15, "danh_gia": dg} for ma, mt, lk, db, dg in rows])


def _tq(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame([{"phong_code": ma, "online": onl, "ck_online": ck, "loai_dong": "total" if ma == "TOTAL" else "data"} for ma, onl, ck in rows])


def _kpi_bd(so_sr, qua_han, ty):
    return {"so_sr": so_sr, "qua_han": qua_han, "ty_le_qua_han": ty, "ton": qua_han + 5}


def _kpi_cd(so_sr, ton, ty):
    return {"so_sr": so_sr, "ton": ton, "ty_le_ton": ty}


def _hs() -> tuple[pd.DataFrame, set, set]:
    """CSKH: 14 người bình thường, 4 cài sẵn bất thường, 1 người mẫu nhỏ (rất xấu nhưng dưới 30 SR: KHÔNG được xét)."""
    thuong = [{"nhan_su": f"cs{i:02d}", "tong_tai": 60 + i, "tong_ton": 8 + i % 4, "tong_qua_han": 3 + i % 3, "ty_le_qua_han": 5 + i % 4, "nhan": ""} for i in range(14)]
    cai = [{"nhan_su": "csx1", "tong_tai": 66, "tong_ton": 10, "tong_qua_han": 30, "ty_le_qua_han": 45.0, "nhan": ""},
           {"nhan_su": "csx2", "tong_tai": 50, "tong_ton": 9, "tong_qua_han": 25, "ty_le_qua_han": 50.0, "nhan": ""},
           {"nhan_su": "csx3", "tong_tai": 100, "tong_ton": 90, "tong_qua_han": 4, "ty_le_qua_han": 4.0, "nhan": ""},
           {"nhan_su": "csx4", "tong_tai": 70, "tong_ton": 10, "tong_qua_han": 6, "ty_le_qua_han": 9.0, "nhan": "Cần hỗ trợ"}]
    nho = [{"nhan_su": "csnho", "tong_tai": 10, "tong_ton": 9, "tong_qua_han": 9, "ty_le_qua_han": 90.0, "nhan": ""}]
    return pd.DataFrame(thuong + cai + nho), {c["nhan_su"] for c in cai}, {t["nhan_su"] for t in thuong} | {"csnho"}


def _tq_dv() -> dict:
    return {"sr": {"DNG1": {"bd": _kpi_bd(114, 40, 35.0), "cd": _kpi_cd(200, 10, 5.0)}, "DNG2": {"bd": _kpi_bd(120, 12, 14.0), "cd": _kpi_cd(200, 90, 45.0)}},
            "sr_truoc": {"DNG1": {"bd": _kpi_bd(110, 12, 10.0)}, "DNG2": {"bd": _kpi_bd(118, 8, 7.0)}},
            "roi_mang": {"DNG1": {"kh_roi_mang": 100}, "DNG2": {"kh_roi_mang": 150}, "DNG": {"kh_roi_mang": 250}},
            "roi_mang_truoc": {"DNG1": {"kh_roi_mang": 95}, "DNG2": {"kh_roi_mang": 100}, "DNG": {"kh_roi_mang": 200}},
            "cong_no": {"DNG1": {"bill": 80.0}, "DNG2": {"bill": 75.0}, "DNG": {"bill": 78.0}},
            "cong_no_truoc": {"DNG1": {"bill": 80.5}, "DNG2": {"bill": 80.0}, "DNG": {"bill": 79.5}}, "ky_no": "2026-08"}


def _ngu_canh() -> dict:
    """Ngữ cảnh GIẢ đã điền sẵn kho nhớ của lượt: hai phòng (IBB7 có người bất thường, IBB6 toàn người bình thường) + khối DVKH có bất thường ở cả bốn nguồn."""
    c = q.ngu_canh(NOW)
    c.update(ngay_iso="2026-09-15", thang="2026-09", ngay=15)
    bang7, _, _ = _bang_ns()
    ds = [{"code": "IBB7", "ten": "IBB7"}, {"code": "IBB6", "ten": "IBB6"}]
    hs, _, _ = _hs()
    d = date(2026, 9, 15)
    c["cache"].update({
        "kd_phong": ds, "kd_ns:IBB7": bang7, "kd_ns:IBB6": pd.DataFrame([_ns(i) for i in range(12)]),
        "kd_db": _db([("IBB7", 800, 420, 700, "Rủi ro"), ("IBB6", 700, 480, 760, "An toàn"), ("TOTAL", 1500, 900, 1460, "Cần tăng tốc")]),
        "kd_tq": _tq([("IBB7", 420, 500), ("IBB6", 480, 470), ("TOTAL", 900, 970)]),
        "dv_ngay": {"sr_bd": d, "sr_cd": d, "roi_mang": d, "cong_no": d},
        "dvkh": {"ngay": d, "nd": {}, "hs": hs, "tq": _tq_dv()}})
    c["ten"].update({f"dng.nv{i:02d}": f"Nhân Viên {i:02d}" for i in range(30)} | {"dng.sg01": "Sang Một", "dng.cb01": "Công Bảo", "dng.tk02": "Tồn Hai"})
    return c


@pytest.fixture()
def c_gia(monkeypatch):
    c = _ngu_canh()
    monkeypatch.setattr(q, "ngu_canh", lambda now=None: c)
    return c


def _in(chu: str) -> None:
    """In số đo (xem bằng pytest -s); console Windows cp1252 không in được tiếng Việt thì bỏ qua, không làm hỏng test."""
    try:
        print(chu)
    except UnicodeEncodeError:
        print(chu.encode("ascii", "replace").decode())


def _ma(fs: list[dict]) -> set[str]:
    return {f["ma"] for f in fs}


# ------------------------------------------------------------------ độ bỏ sót: nhân sự
def test_do_bo_sot_nhan_su_bat_100_phan_tram_va_khong_bao_nham(capsys):
    df, cai, thuong = _bang_ns()
    fs = qkd.phat_hien_nhan_su(df, "IBB7")
    ma = _ma(fs)
    bat_duoc = {acc: all(f"kd.nhansu.{acc}.{fa}" in ma for fa in facets) for acc, (facets, _) in cai.items()}
    bi_nghi = {f["doi_tuong"] for f in fs if f["muc"] != q.THAP}
    nham = thuong & bi_nghi
    recall, fp = sum(bat_duoc.values()) / len(bat_duoc), len(nham) / len(thuong)
    _in(f"\n[ĐO] Nhân sự: recall {recall:.0%} ({sum(bat_duoc.values())}/{len(bat_duoc)} bất thường cài sẵn), báo nhầm {fp:.0%} ({len(nham)}/{len(thuong)} người bình thường)")
    assert recall == 1.0, [a for a, v in bat_duoc.items() if not v]
    assert fp == 0.0, nham
    assert not {"dng.tpx", "dng.nghi"} & {f["doi_tuong"] for f in fs}, "trưởng phòng / người nghỉ không được vào chỉ số cá nhân"


def test_muc_do_nhan_su_dung_va_ban_kem_chi_la_muc_thap():
    df, _, _ = _bang_ns()
    fs = {f["ma"]: f for f in qkd.phat_hien_nhan_su(df, "IBB7")}
    assert fs["kd.nhansu.dng.cb01.canh_bao"]["muc"] == q.CAO and fs["kd.nhansu.dng.cb02.canh_bao"]["muc"] == q.TB
    assert fs["kd.nhansu.dng.tk02.ton_lau"]["muc"] == q.CAO and fs["kd.nhansu.dng.tk01.ton_lau"]["muc"] == q.TB
    df2 = pd.DataFrame([_ns(i) for i in range(10)] + [_ns(50, acc_norm="dng.bk", vvip=0, camera=0, online=22, ck_online=22)])
    muc = {f["ma"]: f["muc"] for f in qkd.phat_hien_nhan_su(df2, "IBB7")}
    assert muc == {"kd.nhansu.dng.bk.thieu_vvip": q.THAP, "kd.nhansu.dng.bk.thieu_camera": q.THAP}


# ------------------------------------------------------------------ độ bỏ sót: phòng, DVKH
def test_do_bo_sot_phong_va_chi_nhanh(capsys):
    codes = [f"R{i}" for i in range(1, 9)]
    db = _db([("R1", 800, 400, 700, "Rủi ro"), ("R2", 900, 450, 800, "Rủi ro"), ("R3", 700, 450, 690, "Cần tăng tốc"), ("R4", 600, 400, 640, "An toàn"),
              *[(c, 600, 420, 650, "An toàn") for c in codes[4:]], ("TOTAL", 5000, 3000, 4700, "Cần tăng tốc")])
    tq = _tq([("R1", 400, 450), ("R2", 450, 440), ("R3", 450, 400), ("R4", 50, 80), *[(c, 420, 400) for c in codes[4:]], ("TOTAL", 3000, 3200)])
    fs = qkd.phat_hien_phong(db, tq, codes, {}, ngay=15)
    bat = {f["doi_tuong"]: f["muc"] for f in fs}
    cai = {"R1": q.CAO, "R2": q.CAO, "R3": q.TB, "R4": q.TB, "Chi nhánh": q.TB}
    _in(f"\n[ĐO] Phòng: bắt {len(set(cai) & set(bat))}/{len(cai)} bất thường cài sẵn, báo nhầm {len(set(bat) - set(cai))}/{len(codes) - 4} phòng bình thường")
    assert bat == cai
    assert qkd.phat_hien_phong(db, tq, codes, {}, ngay=3) == [], "đầu tháng dự báo chưa đủ tin cậy: không đánh giá"


def test_do_bo_sot_dvkh_cskh_sr_roi_mang_cong_no(capsys):
    hs, cai, thuong = _hs()
    cskh = {f["doi_tuong"] for f in qdv.phat_hien_cskh(hs)}
    t = _tq_dv()
    sr = {f["ma"]: f["muc"] for f in qdv.phat_hien_sr(t["sr"], t["sr_truoc"])}
    rm = {f["ma"]: f["muc"] for f in qdv.phat_hien_roi_mang(t["roi_mang"], t["roi_mang_truoc"])}
    cn = {f["ma"]: f["muc"] for f in qdv.phat_hien_cong_no(t["cong_no"], t["cong_no_truoc"], "2026-08")}
    cai_sr = {"dvkh.sr.DNG1.bd_qua_han": q.CAO, "dvkh.sr.DNG2.cd_ton": q.CAO, "dvkh.sr.DNG2.bd_qua_han": q.TB}
    cai_rm = {"dvkh.roi_mang.DNG2.tang": q.CAO, "dvkh.roi_mang.DNG.tang": q.TB}
    cai_cn = {"dvkh.cong_no.DNG2.cham": q.CAO, "dvkh.cong_no.DNG.cham": q.TB}
    tong_cai = len(cai) + len(cai_sr) + len(cai_rm) + len(cai_cn)
    bat = len(cai & cskh) + sum(sr.get(k) == v for k, v in cai_sr.items()) + sum(rm.get(k) == v for k, v in cai_rm.items()) + sum(cn.get(k) == v for k, v in cai_cn.items())
    nham = len(thuong & cskh) + len(set(sr) - set(cai_sr)) + len(set(rm) - set(cai_rm)) + len(set(cn) - set(cai_cn))
    _in(f"\n[ĐO] DVKH: recall {bat / tong_cai:.0%} ({bat}/{tong_cai} bất thường cài sẵn), báo nhầm {nham} (CSKH mẫu nhỏ, phòng bình thường)")
    assert bat == tong_cai and nham == 0


# ------------------------------------------------------------------ nguồn "dữ liệu thiếu" và độ phủ
def test_du_lieu_cham_va_chua_co_thanh_phat_hien():
    c = _ngu_canh()
    assert q.quet_du_lieu(c) == []
    c["now"] = NOW + timedelta(days=3)                            # số kinh doanh chậm 4 ngày, DVKH chậm 4 ngày
    fs = {f["ma"]: f for f in q.quet_du_lieu(c)}
    assert fs["du_lieu.kd"]["muc"] == q.CAO and fs["du_lieu.sr_bd"]["muc"] == q.TB
    c2 = _ngu_canh()
    c2["cache"]["dv_ngay"] = None                                  # DVKH chưa nạp gì: nêu một lần cho cả khối
    c2["ngay_iso"] = None
    fs2 = q.quet_du_lieu(c2)
    assert {f["ma"] for f in fs2} == {"du_lieu.kd", "du_lieu.sr_bd"} and all("chưa có dữ liệu" in f["tieu_de"] for f in fs2)


def test_so_do_phu_noi_ro_da_quet_tren_tong():
    c = _ngu_canh()
    phu = {p["nguon"]: p for p in q.so_do_phu(c=c)}
    assert phu["kd_nhan_su"]["tong"] == 52 and phu["kd_nhan_su"]["da_quet"] == 50 and "trưởng phòng" in phu["kd_nhan_su"]["ghi_chu"]
    assert phu["kd_phong"]["da_quet"] == phu["kd_phong"]["tong"] == 3
    assert phu["dvkh_cskh"]["tong"] == 19 and phu["dvkh_cskh"]["da_quet"] == 18        # người mẫu nhỏ không được xét
    assert phu["du_lieu"]["da_quet"] == 5 and all(p["co_nguon"] for p in phu.values())


def test_mot_nguon_hong_khong_lam_hong_ca_luot():
    c = _ngu_canh()
    c["cache"].pop("kd_db")
    c["cache"]["kd_db"] = None
    assert qkd.quet_phong(c) == [] and q.quet(c)                                    # nguồn phòng rỗng, các nguồn khác vẫn ra phát hiện


# ------------------------------------------------------------------ bắt thật trên database kiểm thử (chỉ đọc)
def test_quet_database_that_dung_khuon_va_khong_nem_truong_phong():
    from app import canh_bao
    c = q.ngu_canh()
    fs = q.quet(c)
    assert not [k for k in c["loi"] if k.startswith("quet:")], c["loi"]
    cot = {"ma", "nguon", "nhom", "khoi", "cap", "doi_tuong", "muc", "diem", "tieu_de", "bang_chung", "duong_dan", "nguoi_quyet", "chi_so"}
    assert fs and all(cot <= set(f) and f["muc"] in q.HANG_MUC for f in fs)
    assert len({f["ma"] for f in fs}) == len(fs), "mã phát hiện phải duy nhất và ổn định"
    khong_xet = set(canh_bao.acc_khong_xet(f["doi_tuong"] for f in fs if f["nguon"] == "kd_nhan_su"))
    assert not {f["doi_tuong"] for f in fs if f["nguon"] == "kd_nhan_su"} & khong_xet
    phu = {p["nguon"]: p for p in q.so_do_phu(c=c)}
    assert phu["kd_nhan_su"]["da_quet"] > 0 and phu["kd_phong"]["da_quet"] > 0


# ------------------------------------------------------------------ gom, nội dung luật, LLM giả
def _van_de(c_gia, nhom="kd:nhan_su:IBB7"):
    vs, _ = tdh.thu_su_that(NOW, c=c_gia)
    return next(v for v in vs if v["nhom"] == nhom)


def test_gom_moi_vi_pham_cao_deu_co_trong_noi_dung_va_ten_duoc_thay(c_gia, bat):
    vs, bo = tdh.thu_su_that(NOW, c=c_gia)
    assert {v["nhom"] for v in vs} == {"kd:nhan_su:IBB7", "kd:phong:IBB7", "kd:chi_nhanh", "dvkh:cskh", "dvkh:sr", "dvkh:roi_mang", "dvkh:cong_no"} and bo == 0
    v = next(v for v in vs if v["nhom"] == "kd:nhan_su:IBB7")
    assert v["nguoi_quyet"] == "tp:IBB7" and v["su_that"]["chi_so"]["gia_tri"] == 8 and v["su_that"]["bang_chung"]["so_nguoi"] == 8
    kq = nd.soan(v, None, c_gia["ten"], NOW)
    cao = {f["doi_tuong"] for f in v["su_that"]["phat_hien_cao"]}
    assert cao and all(a not in kq["nhan_dinh"] for a in cao & set(c_gia["ten"])), "tên thật phải thay mã acc"
    assert all(c_gia["ten"].get(a, a) in kq["nhan_dinh"] for a in cao)
    assert nd.hien("dng.sg01 online 8", c_gia["ten"]) == "Sang Một online 8"
    assert qdv.NHOM_CSKH in {v["nhom"] for v in vs} and next(v for v in vs if v["nhom"] == "kd:chi_nhanh")["nguoi_quyet"] == "bgd"


def test_tran_van_de_giu_moi_van_de_muc_cao_va_dem_phan_bi_bo(c_gia):
    tat_ca, _ = tdh.thu_su_that(NOW, toi_da=50, c=c_gia)
    n_cao = sum(v["muc"] == q.CAO for v in tat_ca)
    giu, bo = tdh.thu_su_that(NOW, toi_da=1, c=_ngu_canh_lai(c_gia))
    assert len(giu) == max(1, n_cao) and all(v["muc"] == q.CAO for v in giu) and len(giu) + bo == len(tat_ca)


def _ngu_canh_lai(c: dict) -> dict:
    return {**c, "cache": dict(c["cache"]), "loi": {}}


def test_ban_luat_luon_ra_khi_khong_co_llm(c_gia):
    vs, _ = tdh.thu_su_that(NOW, c=c_gia)
    for v in vs:
        kq = nd.soan(v, None, c_gia["ten"], NOW)
        assert kq["nguon_noi_dung"] == "luat" and kq["ly_do_luat"] == "chua_bat_ai"
        assert kq["nhan_dinh"] and 2 <= len(kq["phuong_an"]) <= 3 and kq["khuyen_nghi"] in {p["ma"] for p in kq["phuong_an"]}
        assert "đấu nối" not in kq["nhan_dinh"].lower()


def test_ban_luat_cho_van_de_du_lieu_cham(c_gia, bat):
    c_gia["now"] = NOW + timedelta(days=4)                                          # số kinh doanh và DVKH chậm
    bat["toi_da_van_de"] = 50                                                       # không để trần số vấn đề cắt bớt vấn đề mức trung bình
    vs, _ = tdh.thu_su_that(c_gia["now"], c=c_gia)
    du_lieu = [v for v in vs if v["nhom"].startswith("du_lieu:")]
    assert {v["nhom"] for v in du_lieu} == {"du_lieu:kd", "du_lieu:sr_bd", "du_lieu:sr_cd", "du_lieu:roi_mang", "du_lieu:cong_no"} and all(v["nguoi_quyet"] == "bgd" for v in du_lieu)
    for v in du_lieu:
        kq = nd.soan(v, None, {}, c_gia["now"])
        assert "nạp lại dữ liệu" in kq["nhan_dinh"] and len(kq["phuong_an"]) == 3
    assert tdh.chay_buoi_sang(c_gia["now"], goi_llm=None)["moi"] == len(vs)


def _llm_dung(v):
    so_nguoi = v["su_that"]["bang_chung"]["so_nguoi"]
    return json.dumps({"nhan_dinh": f"Phòng có {so_nguoi} nhân sự cần chú ý.", "khuyen_nghi": "A", "phuong_an": [
        {"ma": "A", "tieu_de": "Trưởng phòng gặp từng người", "mo_ta": "Gặp trực tiếp và chốt số cần đạt."}, {"ma": "B", "tieu_de": "Ghép cặp", "mo_ta": "Kèm cặp trong tuần."}]}, ensure_ascii=False)


def test_llm_gia_dung_so_thi_dung_sai_so_loi_json_hong_thi_ve_luat(c_gia):
    v = _van_de(c_gia)
    lan = []
    dung = lambda ht, nguoi: lan.append(nguoi) or _llm_dung(v)
    kq = nd.soan(v, dung, c_gia["ten"], NOW)
    assert kq["nguon_noi_dung"] == "llm" and "8 nhân sự" in kq["nhan_dinh"]
    nd.soan(v, dung, c_gia["ten"], NOW)
    assert len(lan) == 1, "cùng vấn đề + cùng bảng sự thật thì nhớ kết quả, không gọi lại"
    cac_ca = [("sai_dinh_dang_hoac_so", lambda a, b: _llm_dung(v).replace("8 nhân sự", "999 nhân sự")), ("sai_dinh_dang_hoac_so", lambda a, b: "không phải json"),
              ("sai_dinh_dang_hoac_so", lambda a, b: json.dumps({"nhan_dinh": "x", "phuong_an": [{"ma": "A", "tieu_de": "a", "mo_ta": "b"}], "khuyen_nghi": "A"})),
              ("sai_dinh_dang_hoac_so", lambda a, b: _llm_dung(v).replace("Ghép cặp", "đấu nối")), ("loi_ai", lambda a, b: (_ for _ in ()).throw(RuntimeError("mạng")))]
    for i, (ly_do, ham) in enumerate(cac_ca):
        v2 = {**v, "ma_van_de": v["ma_van_de"] + f"#{i}"}                # khác khoá nhớ để chắc chắn gọi LLM
        kq = nd.soan(v2, ham, c_gia["ten"], NOW)
        assert kq["nguon_noi_dung"] == "luat" and kq["ly_do_luat"] == ly_do and len(kq["phuong_an"]) == 3, (i, kq["ly_do_luat"])


def test_tran_luot_goi_llm_moi_ngay(c_gia, monkeypatch):
    monkeypatch.setenv("TRO_LY_DIEU_HANH_TRAN_NGAY", "1")
    vs, _ = tdh.thu_su_that(NOW, c=c_gia)
    goi = []
    ham = lambda a, b: goi.append(1) or "{}"
    k1, k2 = nd.soan(vs[0], ham, {}, NOW), nd.soan(vs[1], ham, {}, NOW)
    assert len(goi) == 1 and k1["ly_do_luat"] == "sai_dinh_dang_hoac_so" and k2["ly_do_luat"] == "het_tran" and nd.dem_llm(NOW) == 1


def test_loi_gui_llm_khong_co_ten_khach_sdt_va_ten_nhan_su(c_gia):
    v = _van_de(c_gia)
    gui = []
    nd.soan(v, lambda ht, nguoi: gui.append(nguoi) or _llm_dung(v), c_gia["ten"], NOW)
    chu = gui[0]
    assert "dng.sg01" in chu, "nhân sự đi bằng mã acc"
    assert not [t for t in c_gia["ten"].values() if t in chu], "tên thật chỉ thay vào chữ SAU khi LLM trả về"
    assert not re.search(r"\b0\d{9,10}\b|\+84\d{8,}", chu), "không có số điện thoại"


def test_kiem_so_doc_duoc_so_viet_nam():
    bang = {"a": 1234, "b": 5.4, "c": "15/11", "d": "có 7 người"}
    assert nd.kiem_so("Có 1.234 người, 5,4% và ngày 15/11, trong đó 7.", bang)
    assert not nd.kiem_so("Có 999 người.", bang) and not nd.kiem_so("Ngày 16/11.", bang)
    assert nd.dinh_so(1234) == "1.234" and nd.dinh_so(5.4) == "5,4"


# ------------------------------------------------------------------ sổ quyết định và vòng chạy
def test_cong_tac_tat_khong_chay_khong_gui_khong_nhan_lenh(zalo, monkeypatch):
    monkeypatch.setattr(so, "cau_hinh", lambda: {**so.MAC_DINH, "bat": False})
    assert so.bat() is False
    assert tdh.chay_buoi_sang() == tdh.TAT and tdh.nhac_quyet(gui=True) == tdh.TAT and tdh.kiem_chung(gui=True) == tdh.TAT and tdh.vong_tu_dong() == tdh.TAT
    assert so.tom_tat()["tong"] == 0
    assert tz.gui_cho("bgd", "x") is False and zalo.gui == []
    assert tz.xu_ly_webhook(_su_kien("T7", "quyet dinh")) is False
    cd.xu_ly_su_kien(_su_kien("T7", "dong y 1"))
    assert zalo.tra == [("T7", cd.LOI_CHAO)], "tắt công tắc thì tin đi luồng thêm người nhận như cũ"


def test_gui_thu_chi_toi_mot_nguoi_va_khong_danh_dau_da_gui(c_gia, bat, zalo):
    with tz.chi_gui_cho("G1") as kq:
        r = tdh.chay_buoi_sang(NOW, goi_llm=None, gui=True)
    assert r["moi"] == 7 and r["gui"] == 0 and kq["so_tin"] == 7 and kq["loi"] == 0
    assert {c for c, _ in zalo.gui} == {"G1"}, "người quyết thật (T7) không được nhận tin nào"
    assert all(str(t).startswith("[GỬI THỬ") for _, t in zalo.gui)
    assert all(not r["da_gui_luc"] for r in so.liet_ke()), "gửi thử không đánh dấu đã gửi"
    zalo.gui.clear()
    assert tdh.chay_buoi_sang(NOW, goi_llm=None, gui=True)["gui"] == 7 and "T7" in {c for c, _ in zalo.gui}, "gửi thật sau đó vẫn tới đủ người quyết"


def test_chay_buoi_sang_khong_tao_trung_khong_gui_khi_chua_tick(c_gia, bat, zalo):
    r1 = tdh.chay_buoi_sang(NOW, goi_llm=None)
    assert r1["moi"] == 7 and r1["gui"] == 0 and r1["luat"] == 7 and zalo.gui == [] and so.tom_tat()["cho_quyet"] == 7
    r2 = tdh.chay_buoi_sang(NOW + timedelta(hours=1), goi_llm=None)
    assert r2["moi"] == 0 and r2["da_co"] == 7
    r3 = tdh.chay_buoi_sang(NOW + timedelta(days=1), goi_llm=None)
    assert r3["moi"] == 0, "nhóm còn đang chờ quyết thì không đề xuất mới mỗi ngày"
    hang = next(r for r in so.liet_ke() if r["nhom"] == "kd:nhan_su:IBB7")
    assert hang["nguoi_quyet"] == "tp:IBB7" and hang["nguon_noi_dung"] == "luat" and hang["han_quyet"] == NOW + timedelta(hours=8)
    assert hang["chi_so_truoc"]["gia_tri"] == 8 and "Sang Một" in hang["nhan_dinh"]
    r4 = tdh.chay_buoi_sang(NOW, goi_llm=None, gui=True)
    assert r4["gui"] == 7 and {c for c, _ in zalo.gui} == {"T7", "G1"}
    assert tdh.chay_buoi_sang(NOW, goi_llm=None, gui=True)["gui"] == 0, "mỗi đề xuất gửi đúng một lần"
    tin = next(t for c, t in zalo.gui if c == "T7")
    assert "ĐỀ XUẤT CẦN QUYẾT" in tin and "dong y" in tin and "sua" in tin and "bac" in tin and len(tin) <= 1900


def test_phong_chua_co_truong_phong_thi_tin_ve_ban_giam_doc(c_gia, bat, zalo, monkeypatch):
    monkeypatch.setattr(ban_tin, "ds_nguoi_nhan", lambda loai=None, chi_bat=False: [n for n in NGUOI if n["chat_id"] != "T7" and (not loai or n["loai"] == loai)])
    assert [n["chat_id"] for n in tdh.nguoi_nhan_cua("tp:IBB7")] == ["G1"] and [n["chat_id"] for n in tdh.nguoi_nhan_cua("tp:IBB6")] == ["T6"]


def _de_xuat(han_quyet: datetime, nguoi: str = "tp:IBB7", nhom: str = "kt:nhom") -> int:
    return so.tao({"ma_van_de": f"20260916:{nhom}", "nhom": nhom, "tieu_de": "Phòng IBB7 cần bù số", "khoi": "kd", "nguoi_quyet": nguoi, "su_that": {"muc": "cao", "duong_dan": "/phong?phong=IBB7"},
                   "nhan_dinh": "Nhận định thử.", "phuong_an": [{"ma": "A", "tieu_de": "Làm A", "mo_ta": "mô tả A"}, {"ma": "B", "tieu_de": "Làm B", "mo_ta": "mô tả B"}], "khuyen_nghi": "A",
                   "han_quyet": han_quyet, "chi_so_truoc": {"loai": "kiem_thu", "tham_so": {}, "gia_tri": 9, "nhan": "Số ca thử", "don_vi": "ca", "tot_khi": "giam", "luc": NOW.isoformat()},
                   "nguon_noi_dung": "luat"}, NOW)


def test_nhac_va_leo_thang_dung_mot_lan(bat, zalo):
    qid = _de_xuat(NOW)
    assert tdh.nhac_quyet(NOW + timedelta(hours=1), gui=False) == {"nhac": 0, "bao_cap_tren": 0} and zalo.gui == []
    assert tdh.nhac_quyet(NOW + timedelta(hours=1), gui=True) == {"nhac": 1, "bao_cap_tren": 0}
    assert [c for c, _ in zalo.gui] == ["T7"] and "NHẮC QUYẾT ĐỊNH" in zalo.gui[0][1]
    assert tdh.nhac_quyet(NOW + timedelta(hours=2), gui=True) == {"nhac": 0, "bao_cap_tren": 0}, "nhắc đúng một lần"
    assert tdh.nhac_quyet(NOW + timedelta(hours=17), gui=True) == {"nhac": 0, "bao_cap_tren": 1}
    assert [c for c, _ in zalo.gui] == ["T7", "G1"] and "QUÁ HẠN QUYẾT" in zalo.gui[1][1]
    assert so.doc(qid)["trang_thai"] == "qua_han"
    assert tdh.nhac_quyet(NOW + timedelta(hours=30), gui=True) == {"nhac": 0, "bao_cap_tren": 0} and len(zalo.gui) == 2
    assert so.quyet(qid, "G1", "B", "", NOW + timedelta(hours=31)), "quá hạn vẫn quyết được"


def test_kiem_chung_do_dung_mot_lan_va_ghi_cau_ket_qua(bat, zalo):
    qid = _de_xuat(NOW + timedelta(hours=8))
    q.DO_CHI_SO["kiem_thu"] = lambda c, ts: 5
    assert so.quyet(qid, "Chị TP bảy (Zalo)", "A", "", NOW)
    assert so.doc(qid)["han_kiem_chung"] == NOW + timedelta(hours=48)
    assert tdh.kiem_chung(NOW + timedelta(hours=47), goi_llm=None, gui=True) == {"kiem_chung": 0, "da_bao": 0}, "chưa tới hạn đo lại"
    kq = tdh.kiem_chung(NOW + timedelta(hours=49), goi_llm=None, gui=True)
    r = so.doc(qid)
    assert kq == {"kiem_chung": 1, "da_bao": 1} and r["trang_thai"] == "da_kiem_chung" and r["chi_so_sau"]["gia_tri"] == 5
    assert r["ket_qua"] == "Số ca thử giảm từ 9 xuống 5 ca (giảm 44%). Đã cải thiện."
    assert sorted(c for c, _ in zalo.gui) == ["G1", "T7"] and "KẾT QUẢ SAU QUYẾT ĐỊNH" in zalo.gui[0][1]
    assert tdh.kiem_chung(NOW + timedelta(days=5), goi_llm=None, gui=True) == {"kiem_chung": 0, "da_bao": 0} and len(zalo.gui) == 2


def test_kiem_chung_bang_chi_so_that_cua_bo_quet(c_gia, bat, zalo):
    tdh.chay_buoi_sang(NOW, goi_llm=None)
    r = next(r for r in so.liet_ke() if r["nhom"] == "kd:nhan_su:IBB7")
    so.quyet(r["id"], "G1", "A", "", NOW)
    c_gia["cache"] = {k: v for k, v in c_gia["cache"].items() if not k.startswith("kd_ns_ph:")}
    c_gia["cache"]["kd_ns:IBB7"] = pd.DataFrame([_ns(i) for i in range(12)])                # sau 2 ngày mọi người đã bình thường
    c_gia["now"] = NOW + timedelta(hours=50)
    assert tdh.kiem_chung(NOW + timedelta(hours=50), goi_llm=None)["kiem_chung"] == 1
    assert so.doc(r["id"])["ket_qua"] == "Số nhân sự cần chú ý của IBB7 giảm từ 8 xuống 0 người (giảm 100%). Đã cải thiện."


def test_kiem_chung_llm_chi_viet_lai_va_sai_so_thi_giu_cau_luat(bat):
    cs = {"gia_tri": 9, "nhan": "Số ca thử", "don_vi": "ca", "tot_khi": "giam"}
    luat = nd.cau_ket_qua(cs, 5)
    ok, nguon = nd.viet_lai_ket_qua(cs, 5, luat, lambda a, b: json.dumps({"ket_qua": "Số ca thử giảm từ 9 xuống 5."}), {}, NOW)
    assert nguon == "llm" and ok == "Số ca thử giảm từ 9 xuống 5."
    sai, nguon2 = nd.viet_lai_ket_qua(cs, 5, luat, lambda a, b: json.dumps({"ket_qua": "Số ca thử giảm từ 9 xuống 3."}), {}, NOW)
    assert nguon2 == "luat" and sai == luat
    assert nd.cau_ket_qua(cs, 12).endswith("Chưa cải thiện.") and "không đổi" in nd.cau_ket_qua(cs, 9)


# ------------------------------------------------------------------ lệnh Zalo
def _su_kien(chat_id: str, text: str, loai: str = "PRIVATE") -> dict:
    return {"event_name": "message.text.received", "message": {"message_id": f"m-{chat_id}-{text}", "date": 1, "text": text,
                                                              "from": {"id": chat_id, "display_name": "Ai đó", "is_bot": False}, "chat": {"id": chat_id, "chat_type": loai}}}


def _gui_lenh(chat_id: str, text: str, loai: str = "PRIVATE") -> bool:
    return tz.xu_ly_webhook(_su_kien(chat_id, text, loai))


def test_phan_tich_lenh_co_dau_khong_dau():
    pt = tz.phan_tich_lenh
    assert pt("dong y 12 B") == {"lenh": "dong_y", "id": 12, "chon": "B", "y_kien": ""}
    assert pt("Đồng ý #12") == {"lenh": "dong_y", "id": 12, "chon": None, "y_kien": ""}
    assert pt("sua 7 Giao thêm cho phòng khác nhé") == {"lenh": "sua", "id": 7, "chon": None, "y_kien": "Giao thêm cho phòng khác nhé"}
    assert pt("bac 3 chưa cần") == {"lenh": "bac", "id": 3, "chon": None, "y_kien": "chưa cần"}
    assert pt("quyết định")["lenh"] == "danh_sach"
    assert pt("xin chào") is None and pt("dong y") is None and pt("sua abc") is None and pt("") is None


def test_lenh_dung_nguoi_duoc_ghi_so_sai_nguoi_bi_tu_choi(bat, zalo):
    q1, q2 = _de_xuat(NOW + timedelta(hours=8), "tp:IBB7", "n1"), _de_xuat(NOW + timedelta(hours=8), "tp:IBB6", "n2")
    assert _gui_lenh("T7", "dong y %d" % q1) is True
    r = so.doc(q1)
    assert r["trang_thai"] == "da_quyet" and r["lua_chon"] == "A" and r["quyet_boi"] == "Chị TP bảy (Zalo)" and r["han_kiem_chung"] is not None
    assert zalo.tra[-1][0] == "T7" and "chỉ được lưu vào sổ" in zalo.tra[-1][1]
    assert _gui_lenh("T7", "dong y %d B" % q2) is True and so.doc(q2)["trang_thai"] == "cho_quyet" and "không có quyền" in zalo.tra[-1][1]
    assert _gui_lenh("T7", "bac %d" % q1) is True and so.doc(q1)["trang_thai"] == "da_quyet" and "trạng thái “Đã quyết”" in zalo.tra[-1][1]
    assert _gui_lenh("G1", "sua %d" % q2) is True and so.doc(q2)["trang_thai"] == "cho_quyet" and "ý kiến" in zalo.tra[-1][1]
    assert _gui_lenh("G1", "sua %d Giao thêm người" % q2) is True
    r2 = so.doc(q2)
    assert r2["trang_thai"] == "da_quyet" and r2["lua_chon"] == "sua" and r2["ghi_chu"] == "Giao thêm người", "cấp trên quyết thay được"
    assert so.nhat_ky(q2)[-1]["hanh_dong"] == "da_quyet" and so.nhat_ky(q2)[-1]["boi"] == "Anh Giám đốc (Zalo)"


def test_lenh_bac_danh_sach_phuong_an_la_va_de_xuat_khong_ton_tai(bat, zalo):
    q1 = _de_xuat(NOW + timedelta(hours=8))
    assert _gui_lenh("T7", "dong y %d C" % q1) and so.doc(q1)["trang_thai"] == "cho_quyet" and "chỉ có phương án A, B" in zalo.tra[-1][1]
    assert _gui_lenh("T7", "quyet dinh") and f"#{q1}" in zalo.tra[-1][1]
    assert _gui_lenh("T6", "quyet dinh") and "Không có đề xuất nào" in zalo.tra[-1][1]
    assert _gui_lenh("T7", "bac %d Chưa cần" % q1) and so.doc(q1)["trang_thai"] == "bac" and so.doc(q1)["ghi_chu"] == "Chưa cần"
    assert _gui_lenh("G1", "dong y 999") and "Không có đề xuất #999" in zalo.tra[-1][1]
    assert _gui_lenh("G1", "dong y %d" % q1) and "không đổi được nữa" in zalo.tra[-1][1]


def test_nguoi_la_hoac_admin_khong_quyet_duoc_va_luong_them_nguoi_nhan_van_chay(bat, zalo):
    q1 = _de_xuat(NOW + timedelta(hours=8))
    assert _gui_lenh("A1", "dong y %d" % q1) is True and so.doc(q1)["trang_thai"] == "cho_quyet" and "không có quyền" in zalo.tra[-1][1], "loại admin (nhắc nạp file) không quyết"
    zalo.tra.clear()
    cd.xu_ly_su_kien(_su_kien("NGUOILA", "dong y %d" % q1))
    assert so.doc(q1)["trang_thai"] == "cho_quyet", "người lạ không quyết được"
    assert [r["chat_id"] for r in cd.ds_cho_duyet()] == ["NGUOILA"] and zalo.tra == [("NGUOILA", cd.LOI_CHAO)], "người lạ vẫn vào danh sách chờ duyệt như cũ"
    assert _gui_lenh("T7", "xin chào") is False and _gui_lenh("T7", "dong y %d" % q1, loai="GROUP") is False, "câu thường và nhóm: để luồng cũ"
    cd.xu_ly_su_kien(_su_kien("T7", "dong y %d" % q1))
    assert so.doc(q1)["trang_thai"] == "da_quyet" and cd.ds_cho_duyet()[0]["chat_id"] == "NGUOILA" and len(cd.ds_cho_duyet()) == 1, "lệnh của người nhận được xử lý trước, không vào danh sách chờ"


# ------------------------------------------------------------------ đường tự động, quyền, menu
def test_duong_tu_dong_chi_chay_khi_bat_va_tu_dong_va_dung_khoa(monkeypatch):
    from app.ui.app import server
    may = server.test_client()
    monkeypatch.setenv("BAN_TIN_KHOA", "khoa-thu")
    monkeypatch.setattr(tdh, "vong_tu_dong", lambda: {"moi": 0})
    h = {"X-Ban-Tin-Khoa": "khoa-thu"}
    assert may.post("/api/ban-tin/tro-ly/chay", headers=h).status_code == 403, "mặc định tắt"
    monkeypatch.setattr(so, "cau_hinh", lambda: {**so.MAC_DINH, "bat": True, "tu_dong": False})
    assert may.post("/api/ban-tin/tro-ly/chay", headers=h).status_code == 403
    monkeypatch.setattr(so, "cau_hinh", lambda: {**so.MAC_DINH, "bat": True, "tu_dong": True})
    assert may.post("/api/ban-tin/tro-ly/chay", headers={"X-Ban-Tin-Khoa": "sai"}).status_code == 403
    r = may.post("/api/ban-tin/tro-ly/chay", headers=h)
    assert r.status_code == 200 and r.get_json() == {"ok": True, "moi": 0}


def _dang_nhap(role: str):
    from flask_login import login_user

    from app.auth import SessionUser
    login_user(SessionUser(SimpleNamespace(id=9, username=f"zz_td_{role}", ho_ten=role, role=role, ma_nv=None, scope=None, session_version=0)))


def test_chi_bgd_vao_trang_va_menu_chi_hien_khi_bat(monkeypatch):
    from app.ui import app as ung_dung
    from app.ui.app import server
    with server.test_request_context("/"):
        _dang_nhap("admin")
        monkeypatch.setattr(so, "cau_hinh", lambda: {**so.MAC_DINH, "bat": False})
        assert "Trợ lý điều hành" not in repr(ung_dung._sidebar("/", "KD")), "tắt công tắc thì không có menu"
        assert "chưa được bật" in repr(ung_dung._router("/trolydieuhanh", "", None)[0])
        monkeypatch.setattr(so, "cau_hinh", lambda: {**so.MAC_DINH, "bat": True})
        assert "Trợ lý điều hành" in repr(ung_dung._sidebar("/", "KD")) and "Trợ lý điều hành" in repr(ung_dung._sidebar("/dvkh", "DVKH"))
        assert "tdh-luoi" in repr(ung_dung._router("/trolydieuhanh", "", None)[0])
        for role in ("phong", "operator", "nvkd", "online", "nhanvien", "dvkh"):
            _dang_nhap(role)
            assert "Trợ lý điều hành" not in repr(ung_dung._sidebar("/", "KD")), role
            giao_dien = repr(ung_dung._router("/trolydieuhanh", "", None)[0])
            assert "tdh-luoi" not in giao_dien, role


def test_callback_trang_tra_rong_khi_khong_phai_bgd_hoac_cong_tac_tat(monkeypatch):
    from app.ui.app import server
    from app.ui.pages import trolydh
    with server.test_request_context("/"):
        _dang_nhap("phong")
        monkeypatch.setattr(so, "cau_hinh", lambda: {**so.MAC_DINH, "bat": True})
        for f, tham in ((trolydh.cb_chay, (1, 0, ["gui"], None, 0)), (trolydh.cb_ve, (0,)), (trolydh.cb_phu, (0,))):
            with pytest.raises(PreventUpdate):
                f(*tham)
        assert trolydh.cb_chon([{"id": 1}]) == ""
        _dang_nhap("admin")
        monkeypatch.setattr(so, "cau_hinh", lambda: dict(so.MAC_DINH))
        for f, tham in ((trolydh.cb_chay, (1, 0, ["gui"], None, 0)), (trolydh.cb_ve, (0,)), (trolydh.cb_phu, (0,))):
            with pytest.raises(PreventUpdate):
                f(*tham)


def test_trang_dung_duoc_voi_so_va_chi_tiet(c_gia, bat, zalo):
    from app.ui.app import server
    from app.ui.pages import trolydh
    tdh.chay_buoi_sang(NOW, goi_llm=None)
    r = next(r for r in so.liet_ke() if r["nhom"] == "kd:nhan_su:IBB7")
    so.quyet(r["id"], "Anh Giám đốc (Zalo)", "A", "", NOW)
    with server.test_request_context("/"):
        _dang_nhap("admin")
        ai, kpis, rows = trolydh.cb_ve(0)
        assert len(rows) == 7 and next(x for x in rows if x["id"] == r["id"])["trang_thai_ten"] == "Đã quyết" and next(x for x in rows if x["id"] == r["id"])["lua_chon_ten"].startswith("A - ")
        assert len(kpis) == 4 and "BẢN LUẬT" in repr(ai)
        assert "Sang Một" in repr(trolydh.cb_chon([{"id": r["id"]}]))
        assert trolydh.cb_chon([{"id": 99999}]) == ""
        assert "tdh-sang" in repr(trolydh.layout())
