"""Nạp số liệu MINH HOẠ (tổng hợp ngẫu nhiên, hạt giống cố định) cho bản demo công khai.

    DATABASE_URL=sqlite:///data/demo_lien_khoi.db python scripts/nap_so_lieu_mau.py [--nap-lai]

Vì sao có: bản demo chỉ có trang Điều hành liên khối (đọc CSV); Báo cáo Tổng, Tracking, Báo cáo phòng, Phân tích bán hàng và 8 trang DVKH đọc thẳng
database nên trống. Script này ghi dữ liệu giả vào đúng các bảng đó qua đường ghi có sẵn của app (`ingest.commit.commit_result`, `dvkh.nap.nap`).

- KHÔNG dùng dữ liệu thật: tên người, acc, mã hợp đồng đều bịa (`DNG.demo...`, `MHKD...`, `MHDV...`, `cskh_NN`). Số sai cũng được, chỉ để hình dung.
- Chỉ chạy với database SQLite (từ chối Postgres / Supabase) để không bao giờ ghi nhầm vào database thật.
- Kinh doanh: tháng 10 + tháng 11/2026 tới ngày tham chiếu `demo/lien_khoi/meta.json`. DVKH: SR / rời mạng / công nợ ~ 2,5 tháng (xem `nap_so_lieu_mau_dvkh.py`).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

GOC = Path(__file__).resolve().parents[1]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))
os.environ.setdefault("LIEN_KHOI_NGUON", "demo")      # đừng để app tự chèn nhân sự thật (app/db.py) vào database minh hoạ

HAT_GIONG = 20261114
THANG_KY = "2026-11"
THANG_TRUOC = "2026-10"
# phòng bán hàng: (mã phòng, số nhân viên, CN bán, hệ số năng suất, tiền tố acc, nhãn acc)
PHONG_BAN = [
    ("IBB1", 8, "DNG_01", 1.00, "DNG", 1), ("IBB2", 9, "DNG_01", 1.10, "DNG", 2), ("IBB3", 7, "DNG_01", 0.90, "DNG", 3),
    ("IBB4", 8, "DNG_01", 1.00, "DNG", 4), ("IBB5", 8, "DNG_02", 1.05, "DNG", 5), ("IBB6", 7, "DNG_02", 0.95, "DNG", 6),
    ("IBB7", 9, "DNG_02", 1.15, "DNG", 7), ("HOIAN", 4, "QNM", 1.00, "QNM", 8), ("TAMKY", 4, "QNM", 0.90, "QNM", 9),
    ("NUITHANH", 3, "QNM", 0.80, "QNM", 10), ("DAILOC", 3, "QNM", 0.85, "QNM", 11), ("DIENBAN", 4, "QNM", 1.00, "QNM", 12),
]
TINH_KHAC = ["QNI_01", "HUE_01", "KHA_01", "GLI_01", "DLK_01", "HNI_02", "HCM_08"]
PHUONG = ["Hải Châu", "Thanh Khê", "Sơn Trà", "Ngũ Hành Sơn", "Cẩm Lệ", "Liên Chiểu", "Hòa Vang", "An Hải", "Hòa Khánh", "Hòa Xuân"]
GOI = [("Giga", 0.34), ("Sky", 0.30), ("Meta", 0.16), ("Giga Plus", 0.08), ("Sky F1", 0.07), ("Meta F1", 0.05)]
LAG_ONLINE = ([0, 1, 2, 3, 4, 5, 6, 7, 9, 12], [0.30, 0.27, 0.15, 0.09, 0.06, 0.04, 0.03, 0.02, 0.03, 0.01])
KHOI_TAO = date(2026, 9, 28)         # ngày tạo sớm nhất: đủ để tháng 10 có số online từ ngày 01


def ngay_tham_chieu() -> date:
    f = GOC / "demo" / "lien_khoi" / "meta.json"
    try:
        return date.fromisoformat(json.loads(f.read_text(encoding="utf-8"))["ngay_tc"])
    except Exception:
        return date(2026, 11, 14)


def _tron(x: float) -> int:
    return int(x + 0.5)


# ---------------------------------------------------------------- danh bạ nhân sự bịa
def acc_phong_online() -> list[str]:
    """5 acc của nhóm Phòng Online khai ở `config/rules.yml` (thuộc IBB2): trang /phongonline chỉ hiện đúng các acc này nên dữ liệu mẫu phải có chúng (tên người vẫn bịa)."""
    from app.config import rules_config
    return [str(a).strip() for a in ((rules_config().get("phong_online") or {}).get("acc") or [])]


def dung_nhan_su(rng: random.Random) -> list[dict]:
    """Mỗi phòng: 1 trưởng phòng (ghi chú "Truong phong" không dấu như danh mục thật: `canh_bao._tp_va_danh_muc` nhận diện trưởng phòng bằng chữ này) + nhân viên; vài người nghỉ để bảng có đủ trạng thái."""
    ds, online = [], acc_phong_online()
    for code, n, cn_ban, he_so, tien_to, so in PHONG_BAN:
        for i in range(n + 1):
            tp = i == 0
            nghi = (not tp) and i == n and so in (2, 5, 9)
            acc = online[i - 1] if code == "IBB2" and 1 <= i <= len(online) else f"{tien_to}.demo{so}{i:02d}"
            ds.append({"phong": code, "cn_ban": cn_ban, "tp": tp, "nghi": nghi, "so": so, "i": i,
                       "acc": acc, "ma_nv": f"DM{so:02d}{i:02d}",
                       "ho_ten": f"Trưởng phòng {code}" if tp else f"Nhân viên {code}-{i:02d}",
                       "nang_suat": (0.35 if tp else rng.lognormvariate(0, 0.38)) * he_so,
                       "p_vvip": rng.uniform(0.22, 0.78), "p_camera": rng.uniform(0.05, 0.42),
                       "vao_lam": (date(2026, 8, 20) + timedelta(days=rng.randint(0, 70))) if (not tp and rng.random() < 0.12) else date(2025, 1, 1) + timedelta(days=rng.randint(0, 520))})
    return ds


# ---------------------------------------------------------------- hợp đồng
def _hd_chung(rng, ma, ngay_tao, ngay_onl, acc, ma_nv, cn_ban, cn_ql, phong_ht="Phòng kinh doanh", doi_tuong="Đối tượng khác") -> dict:
    return {"hop_dong": ma, "cn_quan_ly": cn_ql, "cn_ban": cn_ban, "phong_he_thong": phong_ht, "nguon_ban": "IBB",
            "tinh_trang": "Bình thường", "ten_khach_hang": "Khách " + ma[-5:], "ngay_tao_hd": ngay_tao, "ngay_online": ngay_onl,
            "ngay_huy": None, "acc_nhan_vien": acc, "ma_nhan_vien": ma_nv, "doi_tuong_kh": doi_tuong,
            "quan_huyen": rng.choice(PHUONG), "xa_phuong": "Phường " + rng.choice(PHUONG), "tap_diem": f"TD{rng.randint(1, 400):03d}"}


def _internet_them(rng, r: dict) -> dict:
    goi = rng.choices([g for g, _ in GOI], [w for _, w in GOI])[0]
    tra_truoc = rng.choices([0, 6, 12, 13], [0.45, 0.20, 0.10, 0.25])[0]
    cuoc = rng.choice([165000, 185000, 215000, 255000, 330000])
    r.update({"goi_dich_vu": goi, "chinh_sach_ban": f"Tra truoc {tra_truoc}T, 300k PHM" if tra_truoc else "Tra sau, 300k PHM",
              "tien_hoa_mang": 300000.0, "so_thang_tra_truoc": float(tra_truoc),
              "hinh_thuc_tt": rng.choice(["Chuyen khoan ngan hang", "Tien mat", "Vi dien tu"]),
              "so_tien_tra_truoc": float(tra_truoc * cuoc * 0.92), "arpu_tra_truoc": float(cuoc) if tra_truoc else None,
              "arpu_tra_sau": None if tra_truoc else float(cuoc)})
    return r


def _fpt_play(rng, hd: dict, p_vvip: float) -> dict:
    vvip = rng.random() < p_vvip
    goi = rng.choice(["V.VIP", "V.VIP", "V.VIP Plus"]) if vvip else rng.choice(["VIP", "KXD", "VIP"])
    r = {k: hd[k] for k in ("hop_dong", "cn_quan_ly", "cn_ban", "phong_he_thong", "goi_dich_vu", "nguon_ban", "tinh_trang", "ten_khach_hang",
                            "ngay_tao_hd", "ngay_online", "ngay_huy", "acc_nhan_vien", "ma_nhan_vien", "tap_diem", "doi_tuong_kh")}
    r.update({"goi_fpt_play": goi, "loai_box": rng.choice(["Box 2022", "Box 2024", "Không box"]), "chinh_sach_ban": "Combo truyen hinh",
              "gia_box": rng.choice([0.0, 490000.0, 790000.0]), "so_thang_tra_truoc": float(rng.choice([0, 6, 12])),
              "ngay_ban": hd["ngay_tao_hd"], "tinh_trang_fpl": "Đã kích hoạt" if hd["ngay_online"] else "Chờ kích hoạt"})
    return r


def _camera(rng, hd: dict, tc: date) -> list[dict]:
    onl = hd["ngay_online"] + timedelta(days=rng.choice([0, 0, 1, 2, 3]))
    if onl > tc:
        return []
    ds = []
    for k in range(rng.choice([1, 1, 2, 3])):
        goi = rng.choice([("Cloud 7 ngày", 49000), ("Cloud 14 ngày", 79000), ("Cloud 30 ngày", 129000)])
        r = {c: hd[c] for c in ("hop_dong", "cn_quan_ly", "cn_ban", "phong_he_thong", "goi_dich_vu", "nguon_ban", "tinh_trang", "ten_khach_hang",
                                "ngay_tao_hd", "ngay_huy", "acc_nhan_vien", "ma_nhan_vien", "doi_tuong_kh")}
        r.update({"ngay_online": onl, "ten_goi_cloud": goi[0], "so_luong_cloud": 1.0, "gia_cuoc_cloud": float(goi[1]), "ky_tt": float(rng.choice([1, 6, 12])),
                  "don_gia": float(rng.choice([990000, 1290000, 1590000])), "so_luong": 1.0, "tong_tien": float(rng.choice([990000, 1290000, 1590000])),
                  "phan_loai": rng.choice(["Camera trong nhà", "Camera ngoài trời"])})
        r["_row_hash"] = hashlib.md5(f"{hd['hop_dong']}|{k}|{goi[0]}|{onl}".encode()).hexdigest()
        ds.append(r)
    return ds


def sinh_hop_dong(rng: random.Random, nhan_su: list[dict], tc: date) -> tuple[list, list, list]:
    """(internet, fptplay, camera): mỗi nhân viên một nhịp bán riêng; tháng 10 chậm hơn tháng 11 để có số tăng trưởng; một phần hợp đồng chưa online (tồn)."""
    net, fpl, cam, seq = [], [], [], [0]

    def mot_hd(ngay, acc, ma_nv, cn_ban, cn_ql, p_vvip, p_cam, **kw):
        seq[0] += 1
        ma = f"MHKD{seq[0]:05d}"
        treo = rng.random() < 0.045
        onl = ngay + timedelta(days=rng.choices(*LAG_ONLINE)[0])
        if treo and ngay < date(2026, 10, 12):
            return                                     # hợp đồng treo từ lâu đã rớt khỏi file, không còn là tồn
        onl = None if (treo or onl > tc) else onl
        hd = _internet_them(rng, _hd_chung(rng, ma, ngay, onl, acc, ma_nv, cn_ban, cn_ql, **kw))
        net.append(hd)
        if rng.random() < 0.62:
            fpl.append(_fpt_play(rng, hd, p_vvip))
        if onl and rng.random() < p_cam:
            cam.extend(_camera(rng, hd, tc))

    ngay = KHOI_TAO
    while ngay <= tc:
        he_ngay = 0.45 if ngay.weekday() == 6 else 1.0
        he_thang = 1.0 if ngay.month == 11 else 0.84
        for ns in nhan_su:
            if ns["nghi"]:
                continue
            for _ in range(_poisson(rng, 0.6 * ns["nang_suat"] * he_ngay * he_thang)):
                cn_ql = ns["cn_ban"] if rng.random() < 0.9 else rng.choice(TINH_KHAC + ["QNM", "DNG_01"])
                mot_hd(ngay, ns["acc"], ns["ma_nv"], ns["cn_ban"], cn_ql, ns["p_vvip"], ns["p_camera"])
        _hop_dong_khac(rng, mot_hd, ngay, he_ngay)
        ngay += timedelta(days=1)
    return net, fpl, cam


def _hop_dong_khac(rng, mot_hd, ngay, he_ngay) -> None:
    """Hợp đồng không thuộc nhân sự trong danh mục: ECOM, khách VIP 7 (ANCS), phòng kỹ thuật / CUS, và sale chi nhánh khác bán hộ (không tính vào số Đà Nẵng + Quảng Nam)."""
    for _ in range(_poisson(rng, 0.7 * he_ngay)):
        cn = rng.choice(["DNG_01", "DNG_02", "QNM"])
        mot_hd(ngay, f"ECOM.demo{rng.randint(1, 3):02d}", "DM9001", "HCM_ECOM", cn, 0.4, 0.1)
    for _ in range(_poisson(rng, 0.3 * he_ngay)):
        mot_hd(ngay, "DNG.demoancs", "DM9002", "DNG_01", rng.choice(["DNG_01", "QNM"]), 0.5, 0.1, doi_tuong="VIP 7")
    for _ in range(_poisson(rng, 0.4 * he_ngay)):
        cn = rng.choice(["DNG_01", "DNG_02", "QNM"])
        mot_hd(ngay, f"DNG.demokt{rng.randint(1, 3)}", "DM9003", cn, cn, 0.2, 0.05, phong_ht="Phòng kỹ thuật")
    for _ in range(_poisson(rng, 0.15 * he_ngay)):
        cn = rng.choice(["DNG_01", "DNG_02", "QNM"])
        mot_hd(ngay, "DNG.democus1", "DM9004", cn, cn, 0.2, 0.05, phong_ht="Phòng CUS")
    for _ in range(_poisson(rng, 0.2 * he_ngay)):
        mot_hd(ngay, "HNI.demo01", "DM9005", "HNI_01", "DNG_01", 0.3, 0.05)


def _poisson(rng: random.Random, lam: float) -> int:
    import math
    nguong, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= nguong:
            return k
        k += 1


# ---------------------------------------------------------------- ghi vào database
def _ghi_danh_muc(s, nhan_su: list[dict]) -> None:
    from app.ingest.normalize import norm_acc
    from app.models import Employee, StaffMap
    from app.org import sync_org_to_db
    sync_org_to_db(s)
    for ns in nhan_su:
        s.add(StaffMap(acc=ns["acc"], acc_norm=norm_acc(ns["acc"]), ma_nv=ns["ma_nv"], phong_code=ns["phong"], ten_hien_thi=ns["ho_ten"],
                       ghi_chu="Truong phong" if ns["tp"] else ("Nghỉ việc" if ns["nghi"] else None), nguon="demo"))
        s.add(Employee(ma_nv=ns["ma_nv"], ho_ten=ns["ho_ten"], acc=ns["acc"], acc_norm=norm_acc(ns["acc"]), vi_tri="NVKD",
                       don_vi_ps="QNM" if ns["cn_ban"] == "QNM" else "DNG", phong_ps=ns["phong"], khu_vuc="Đà Nẵng",
                       ngay_tinh_luong=ns["vao_lam"], trang_thai="Nghỉ việc" if ns["nghi"] else "Đang làm việc"))
    s.flush()


def _nhom_tham_nien(thang: int) -> str:
    return "MOI" if thang <= 3 else ("DANG_LEN" if thang <= 6 else ("ON_DINH" if thang <= 12 else "LAU_NAM"))


THANG_NSLD = [f"2026-{m:02d}" for m in range(1, 12)]


def _ghi_nsld(s, nhan_su: list[dict], net: list[dict], rng: random.Random) -> int:
    """NSLĐ từ tháng 1 tới tháng 11 (đủ 11 file, trang Chất lượng dữ liệu không báo thiếu tháng). Tháng 10 và 11: ITN = số online thật trong tháng, đạt khi từ 12 (T10) / 6 (T11) online;
    các tháng trước sinh theo năng suất từng người. Trưởng phòng có dòng NSLĐ nhưng không xét điểm."""
    from app.models import HrMonthly
    from app.ingest.normalize import norm_acc
    n = 0
    for thang in THANG_NSLD:
        itn: dict[str, int] = {}
        for h in net:
            if h["ngay_online"] and f"{h['ngay_online']:%Y-%m}" == thang:
                itn[norm_acc(h["acc_nhan_vien"])] = itn.get(norm_acc(h["acc_nhan_vien"]), 0) + 1
        co_that = thang in (THANG_TRUOC, THANG_KY)
        for ns in nhan_su:
            vao = ns["vao_lam"]
            if vao > date(int(thang[:4]), int(thang[5:]), 28):
                continue                                     # chưa vào làm
            tn = max(1, (int(thang[:4]) - vao.year) * 12 + int(thang[5:]) - vao.month + 1)
            diem = itn.get(norm_acc(ns["acc"]), 0) if co_that else max(0, _tron(rng.gauss(12 * ns["nang_suat"] + 1, 3)))
            s.add(HrMonthly(ma_nv=ns["ma_nv"], thang=thang, acc=ns["acc"], ho_ten=ns["ho_ten"], vi_tri="Trưởng phòng" if ns["tp"] else "NVKD", phong_ps=f"DNGB{ns['so']}",
                            tham_nien_bucket=str(min(tn, 24)), tham_nien_thang=tn, nhom_tham_nien=_nhom_tham_nien(tn),
                            trang_thai="Nghỉ việc" if ns["nghi"] else "Bình thường", dieu_kien="Không xét NSLĐ" if ns["tp"] else "Xét NSLĐ",
                            diem_itn=float(diem), diem_fpt_play=0.0, diem_tong=float(diem),
                            ket_luan="" if ns["tp"] else ("OK" if diem >= (12 if thang != THANG_KY else 6) else "NOT OK")))
            n += 1
    return n


def _ghi_muc_tieu(s, rng: random.Random) -> int:
    """Mục tiêu tháng 10 và 11 cho MỌI phòng kinh doanh, kỹ thuật, CUS, ECOM (Internet, Camera, mục tiêu ngày), quanh số online thật của tháng 10 trong database;
    tháng 11 đặt cao hơn một chút để có tiến độ và dự báo. Phòng gần như không có số (ECOM, KT, CUS) vẫn có mục tiêu nhỏ để không bị báo thiếu."""
    from sqlalchemy import text

    from app.models import Target
    from app.org import phong_order
    onl = {r[0]: int(r[1]) for r in s.execute(text("SELECT phong_code, COUNT(*) FROM fact_internet WHERE ngay_online >= '2026-10-01' AND ngay_online <= '2026-10-31' GROUP BY phong_code"))}
    n = 0
    for p in phong_order(THANG_KY):
        if p.get("loai") not in ("IBB", "DIABAN", "KT", "CUS", "ECOM"):
            continue
        so = max(onl.get(p["code"], 0), 8)
        for thang, he in ((THANG_TRUOC, rng.uniform(0.92, 1.08)), (THANG_KY, rng.uniform(1.0, 1.2))):
            mt = _tron(so * he / 5) * 5
            for chi_tieu, gia_tri in (("internet", mt), ("camera", max(5, _tron(mt * 0.22 / 5) * 5)), ("ngay", max(1, _tron(mt / 30)))):
                s.add(Target(thang=thang, doi_tuong="PHONG", ma_doi_tuong=p["code"], chi_tieu=chi_tieu, gia_tri=float(gia_tri)))
                n += 1
    return n


def sinh_pheu(rng: random.Random) -> list[dict]:
    """Phễu bán hàng tháng 11 theo đơn vị: mỗi tầng = chuyển đổi + chưa chuyển đổi, tầng sau lấy đúng số đã chuyển đổi của tầng trước."""
    don_vi = [(f"DNGB{i}", rng.uniform(3000, 9000)) for i in range(1, 8)] + [("DNGBT1", 200.0), ("DNGBT2", 300.0), ("DNGCS1", 150.0), ("DNGCS2", 180.0), ("DNGDA", 20.0)]
    out = []
    for ten, n0 in don_vi:
        r = {"don_vi": ten}
        tong = _tron(n0)
        for tang, ty in (("thu_thap", 0.45), ("lien_he", 0.55), ("tu_van", 0.5), ("len_don", 0.72), ("hoan_tat", 1.0)):
            cd = _tron(tong * ty * rng.uniform(0.85, 1.15)) if tang != "hoan_tat" else _tron(tong * rng.uniform(0.55, 0.9))
            cd = min(cd, tong)
            r[f"{tang}_cd"], r[f"{tang}_ccd"] = cd, tong - cd
            tong = cd
        r["kh_cham_soc"] = r["hoan_tat_cd"]
        out.append(r)
    return out


def nap_kinh_doanh(rng: random.Random, tc: date) -> dict:
    import pandas as pd

    from app.bo_nho import xoa
    from app.db import session_scope
    from app.ingest.commit import commit_result
    from app.ingest.loader import LoadResult
    from sqlalchemy import text

    nhan_su = dung_nhan_su(rng)
    net, fpl, cam = sinh_hop_dong(rng, nhan_su, tc)

    def kq(ten: str, du_lieu: list[dict]) -> LoadResult:
        df = pd.DataFrame(du_lieu).astype(object)
        return LoadResult(dataset=ten, ten_hien_thi=ten, nguon="du_lieu_mau", header_row=0, df=df.where(df.notna(), None), rows_total=len(df))

    out: dict = {}
    with session_scope() as s:
        _ghi_danh_muc(s, nhan_su)
        for ten, ds in (("internet", net), ("fptplay", fpl), ("camera", cam)):
            st = commit_result(s, kq(ten, ds), nguon_file=f"du_lieu_mau_{ten}.csv", hash_file="demo" + ten, user="demo", thang=THANG_KY)
            out[ten] = st.get("them_moi", 0)
        pheu = commit_result(s, kq("pheu_ban_hang", sinh_pheu(rng)), nguon_file="du_lieu_mau_pheu.csv", hash_file="demopheu", user="demo", thang=THANG_KY)
        out["pheu"] = pheu.get("them_moi", 0)
        out["nsld"] = _ghi_nsld(s, nhan_su, net, rng)
        out["muc_tieu"] = _ghi_muc_tieu(s, rng)
        out["nhan_su"] = len(nhan_su)
        # giờ nạp cuối đặt cố định (sau ngày tham chiếu) để ngày tham chiếu hiện là số đã chốt, không phải "đang cập nhật"
        luc = datetime.combine(tc + timedelta(days=1), datetime.min.time()) + timedelta(hours=2, minutes=30)
        s.execute(text("UPDATE upload_batch SET uploaded_at = :t WHERE dataset IN ('internet', 'fptplay', 'camera')"), {"t": luc})
    xoa()
    return out


# ---------------------------------------------------------------- điểm vào
def _dem(bang: str) -> int:
    from sqlalchemy import text

    from app.db import engine
    try:
        with engine.connect() as c:
            return int(c.execute(text(f"SELECT COUNT(*) FROM {bang}")).scalar() or 0)
    except Exception:
        return 0


def can_nap() -> dict[str, bool]:
    """Bảng nào còn trống thì cần nạp (kinh doanh đo bằng fact_internet, DVKH bằng dv_nap)."""
    from app.db import init_db
    init_db()
    from app.dvkh import nap as dv_nap
    dv_nap.dam_bao_bang(them=True)
    from app import bao_cao_ngay as bc
    bc.dam_bao_bang()
    return {"kd": _dem("fact_internet") == 0, "dvkh": _dem("dv_nap") == 0, "nhap": _dem("bao_cao_ngay") == 0}


def _xoa_so_lieu_mau() -> None:
    """Dọn các bảng script này ghi (chỉ database demo SQLite) để nạp lại từ đầu."""
    from sqlalchemy import text

    from app.bo_nho import xoa
    from app.db import engine
    from app.dvkh import nap as dv_nap
    bang = ["fact_internet", "fact_fptplay", "fact_camera", "staff_map", "dim_employee", "hr_monthly", "target_monthly", "fact_pheu_ban_hang",
            "dv_nap", "dv_sr_bi_dong", "dv_sr_chu_dong", "dv_roi_mang", "dv_cong_no", "dv_cong_no_chot", "dv_danh_sach", "dv_sr_bd_them", "dv_au_kh",
            "bao_cao_ngay", "bao_cao_ngay_chu", "ton_theo_doi", "online_ca", "danh_ba", "ads_lead", "ads_ngay", "ads_pic", "ads_sale", "ads_page", "ads_thang", "phan_hoi_he_thong"]
    with engine.begin() as c:
        for b in bang:
            try:
                c.execute(text(f"DELETE FROM {b}"))
            except Exception:
                pass
        c.execute(text("DELETE FROM upload_batch WHERE file_name LIKE 'du_lieu_mau_%'"))
    dv_nap._DA_TAO.update({"goc": False, "them": False})
    xoa()


def nap_mau(nap_lai: bool = False) -> dict:
    """Nạp số liệu mẫu vào database hiện tại (DATABASE_URL). Chỉ nạp phần còn trống, trừ khi `nap_lai`. Trả số dòng đã nạp từng bảng."""
    from app.config import DATABASE_URL
    if not DATABASE_URL.startswith("sqlite"):
        raise RuntimeError("Số liệu mẫu chỉ được nạp vào database SQLite của bản demo, không bao giờ vào Postgres / Supabase.")
    from app.db import init_db
    init_db()
    if nap_lai:
        _xoa_so_lieu_mau()
    can = can_nap()
    tc = ngay_tham_chieu()
    kq: dict = {"ngay_tc": tc.isoformat()}
    if can["kd"]:
        kq["kinh_doanh"] = nap_kinh_doanh(random.Random(f"{HAT_GIONG}:kd"), tc)
    if can["dvkh"]:
        from scripts.nap_so_lieu_mau_dvkh import nap_dvkh_mau
        kq["dvkh"] = nap_dvkh_mau(random.Random(f"{HAT_GIONG}:dvkh"), tc)
    if can["nhap"]:
        from scripts.nap_so_lieu_mau_nhap import nap_nhap_lieu
        kq["nhap_lieu"] = nap_nhap_lieu(random.Random(f"{HAT_GIONG}:nhap"), tc)
    return kq


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--nap-lai", action="store_true", help="xoá số liệu mẫu cũ rồi nạp lại từ đầu")
    a = ap.parse_args()
    if not os.environ.get("DATABASE_URL"):
        print("Cần đặt DATABASE_URL trỏ vào database SQLite của bản demo (vd sqlite:///data/demo_lien_khoi.db); từ chối chạy để khỏi ghi nhầm vào database mặc định.")
        return 1
    try:
        print(json.dumps(nap_mau(a.nap_lai), ensure_ascii=False, indent=1))
    except RuntimeError as e:
        print(e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
