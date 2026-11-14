"""Dựng bộ dữ liệu MINH HOẠ đã ghép mã cho hướng điều hành liên khối (nhánh thi-lien-khoi).

    python scripts/dung_demo_lien_khoi.py --kt E:\\ --db data/thi.db

Ba khối đang lấy từ ba chi nhánh khác nhau nên mã hợp đồng không trùng. Script này lấy các hợp đồng trong 5 file báo cáo Kỹ thuật làm gốc,
đặt cho mỗi hợp đồng một mã GIẢ (MHAAA0001...), rồi gắn thêm hợp đồng Kinh doanh và SR DVKH (mượn từ dữ liệu DVKH sẵn có, đổi mã) để cả ba khối
cùng nói về một hợp đồng. Ngày tháng được căn cho khớp thứ tự (tạo -> online -> checklist -> SR). Kết quả ghi vào demo/lien_khoi/*.csv.

Riêng tư: không bao giờ ghi tên khách hàng. Mã hợp đồng, tên tài khoản sale / CSKH / KTV đều bị đổi (sale_01, cskh_01, ktv_01...). Cuối script
tự kiểm: nếu còn bất kỳ tên khách, mã hợp đồng thật hay tài khoản thật nào trong file kết quả thì dừng và không để lại file.
Chạy lại cho ra đúng cùng kết quả (hạt giống cố định).
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
import sys
from pathlib import Path

import pandas as pd

GOC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GOC))
from app.lien_khoi import doc_kt                      # noqa: E402

NGAY_TC = pd.Timestamp("2026-11-14")
HAT_GIONG = 20261114
MAU_FILE = ["bao_cao_chi_tiet_ton*.xlsx", "Bao_cao_trien_khai*.xlsx", "Baocao_CLL30Ngay*.xlsx", "Baocao_CheckListSauTK*.xlsx", "Bao_cao_CapLan*.xlsx"]
COT_NHAY_CAM = ["Tên KH", "Tên khách hàng", "Khách Hàng", "Khách khàng", "Tên truy cập", "Sale HĐ", "Nhân sự", "Nhân viên", "Mã NV", "Người nhập",
                "Số HĐ", "Số hợp đồng", "Hợp đồng", "HĐ", "Đối tác", "Block", "Lô", "Chi nhánh", "Tỉnh thành", "Mac", "Block nhân sự", "Đối tác quản lý",
                "Block quản lý", "Account tích L2", "Account tạo PTC", "Account hoàn tất", "Account CLPS"]
GOI_MAU = ["Sky", "Giga", "Sky F1", "Giga F1", "Giga F2"]


def _cat(t: pd.Timestamp) -> pd.Timestamp:
    """Không để sự kiện nào nằm sau ngày hôm nay của bộ minh hoạ."""
    return min(t, NGAY_TC + pd.Timedelta(hours=12))


def _gio(ngay, rng: random.Random) -> pd.Timestamp:
    return pd.Timestamp(ngay).normalize() + pd.Timedelta(hours=rng.randint(8, 17), minutes=rng.randint(0, 59))


def _doc_kt(thu_muc: Path) -> tuple[pd.DataFrame, list[pd.DataFrame]]:
    files = [f for m in MAU_FILE for f in sorted(thu_muc.glob(m))]
    if len(files) < len(MAU_FILE):
        sys.exit(f"Thiếu file Kỹ thuật trong {thu_muc} (tìm thấy {len(files)}/{len(MAU_FILE)}).")
    return doc_kt.su_kien_tu_cac_file(files), [doc_kt.doc_bang(f) for f in files]


def _ma_gia(kt: pd.DataFrame) -> dict[str, str]:
    return {h: f"MHAAA{i:04d}" for i, h in enumerate(dict.fromkeys(kt["so_hd"]), 1)}


def _bo_xung_dot(kt: pd.DataFrame) -> pd.DataFrame:
    """Hợp đồng có mặt ở nhiều file mà sự kiện mâu thuẫn (đang tồn mà vẫn có checklist...) thì giữ file ưu tiên cao hơn."""
    loai = kt.groupby("so_hd")["loai"].agg(set)
    dang_ton = {h for h, s in loai.items() if "ton_kt" in s}                  # đang tồn tức chưa online: bỏ checklist / triển khai của cùng hợp đồng
    kt = kt[~(kt["so_hd"].isin(dang_ton) & kt["loai"].ne("ton_kt"))]
    cll = set(kt.loc[kt["loai"] == "checklist", "so_hd"])
    return kt[~(kt["so_hd"].isin(cll) & kt["loai"].eq("checklist_sau_tk"))].reset_index(drop=True)


def _dung_kd(kt: pd.DataFrame, ma: dict, mask_sale: dict, pool_sale: list, rng: random.Random) -> pd.DataFrame:
    rows = []
    for h, g in kt.groupby("so_hd", sort=False):
        loai = set(g["loai"])
        ngay_ev = g["thoi_diem"].min().normalize()
        ton = False
        online = pd.NaT
        goi = next((x for x in g["goi"].dropna().astype(str) if x), "") or rng.choice(GOI_MAU)
        sale = pool_sale[0]
        if "ton_kt" in loai:
            ton = True
            tao = ngay_ev - pd.Timedelta(days=rng.randint(1, 3))
            sale = mask_sale.get(str(g["sale"].dropna().iloc[0]), rng.choice(pool_sale))
        elif "trien_khai" in loai:
            t = g[g["loai"] == "trien_khai"].iloc[0]
            tao, online = pd.Timestamp(t["tg_tao_hd"]).normalize(), pd.Timestamp(t["tg_online"]).normalize()
            sale = rng.choice(pool_sale)
        elif "checklist" in loai:
            tg = g["tg_online"].dropna()
            online = pd.Timestamp(tg.iloc[0]).normalize() if len(tg) else pd.Timestamp("2025-01-01") + pd.Timedelta(days=rng.randint(0, 500))
            tao = online - pd.Timedelta(days=2)
            sale = rng.choice(pool_sale)
        elif "checklist_sau_tk" in loai:
            online = ngay_ev - pd.Timedelta(days=rng.randint(3, 20))
            tao = online - pd.Timedelta(days=rng.randint(1, 3))
            sale = rng.choice(pool_sale)
        else:                                                   # cap_lan
            online = ngay_ev - pd.Timedelta(days=rng.randint(0, 2))
            tao = online - pd.Timedelta(days=rng.randint(2, 5))
            sale = rng.choice(pool_sale)
        rows.append(dict(so_hd=ma[h], ngay_tao=tao.date(), ngay_online=online.date() if pd.notna(online) else "", ngay_huy="", sale=sale,
                         phong="DEMO", goi=goi, tinh_trang="Bình thường", ton="1" if ton else "0"))
    return pd.DataFrame(rows)


def _donor(db: sqlite3.Connection, sql: str) -> list[tuple]:
    return db.execute(sql).fetchall()


def _dung_sr(kt: pd.DataFrame, kd: pd.DataFrame, ma: dict, db: sqlite3.Connection, mask_cskh: list, rng: random.Random) -> tuple[pd.DataFrame, pd.DataFrame]:
    """SR DVKH mượn từ dữ liệu thật (chỉ lấy loại yêu cầu / kết quả tư vấn / tình trạng, đổi mã hợp đồng và người)."""
    kn = _donor(db, "SELECT tinh_trang, ket_qua_tu_van FROM dv_sr_bi_dong WHERE loai_yc='Khiếu nại, phàn nàn' ORDER BY ma_sr")
    manh = _donor(db, "SELECT loai_yc, tinh_trang, ket_qua_tu_van FROM dv_sr_bi_dong WHERE ket_qua_tu_van LIKE '%không đồng ý sử dụng tiếp%' ORDER BY ma_sr")
    nghi = _donor(db, "SELECT loai_yc, tinh_trang, ket_qua_tu_van FROM dv_sr_bi_dong WHERE ket_qua_tu_van='Khách hàng đang suy nghĩ' ORDER BY ma_sr")
    hoi = _donor(db, "SELECT tinh_trang, ket_qua_tu_van FROM dv_sr_bi_dong WHERE loai_yc='Thắc mắc' ORDER BY ma_sr")
    sos = _donor(db, "SELECT chuong_trinh, diem_rm, tinh_trang FROM dv_sr_chu_dong WHERE nhom_ct='Nguy cơ rời mạng (SOS)' AND diem_rm>=800 "
                     "AND tinh_trang IN ('Chưa xử lý','Đang xử lý','Chưa phân công') ORDER BY ma_sr")
    tl = _donor(db, "SELECT nhom_ct, chuong_trinh, tinh_trang, ket_qua_tu_van, diem_rm FROM dv_sr_chu_dong WHERE ket_qua_tu_van LIKE '%yêu cầu thanh lý%' ORDER BY ma_sr")
    khac = _donor(db, "SELECT nhom_ct, chuong_trinh, tinh_trang, ket_qua_tu_van, diem_rm FROM dv_sr_chu_dong WHERE nhom_ct<>'Nguy cơ rời mạng (SOS)' ORDER BY ma_sr")
    ds = list(dict.fromkeys(kt["so_hd"]))
    cskh = {h: ("" if rng.random() < 0.12 else rng.choice(mask_cskh)) for h in ds}      # ~12% hợp đồng chưa có người DVKH phụ trách: vào hàng chờ
    nhom = {k: list(dict.fromkeys(kt.loc[kt["loai"] == k, "so_hd"])) for k in ("ton_kt", "trien_khai", "checklist", "checklist_sau_tk", "cap_lan")}
    bd, cd = [], []

    def them_bd(h, t, loai_yc, tt, kq, net="Đang hoạt động"):
        bd.append(dict(so_hd=ma[h], tg_yc=_cat(t), loai_yc=loai_yc, tinh_trang=tt, ket_qua_tu_van=kq, nhan_su_au=cskh[h], net_hien=net))

    def thoi(h, loai):
        return kt[(kt["so_hd"] == h) & (kt["loai"] == loai)]["thoi_diem"].max()

    for h in nhom["checklist_sau_tk"]:                                   # lỗi sớm: Kỹ thuật checklist + khách khiếu nại
        d = rng.choice(kn)
        them_bd(h, _gio(thoi(h, "checklist_sau_tk") + pd.Timedelta(days=rng.randint(0, 3)), rng), "Khiếu nại, phàn nàn", d[0], d[1])
    for h in rng.sample(nhom["trien_khai"], 4):
        d = rng.choice(kn)
        on = pd.Timestamp(kd.loc[kd["so_hd"] == ma[h], "ngay_online"].iloc[0])
        them_bd(h, _gio(on + pd.Timedelta(days=rng.randint(1, 10)), rng), "Khiếu nại, phàn nàn", d[0], d[1])
    cll = nhom["checklist"]
    co_kn = rng.sample(cll, 26)
    for h in co_kn:                                                      # sự cố lặp + khiếu nại
        d = rng.choice(kn)
        them_bd(h, _gio(thoi(h, "checklist") + pd.Timedelta(days=rng.randint(0, 6)), rng), "Khiếu nại, phàn nàn", d[0], d[1])
    for h in co_kn[:8]:                                                  # rồi khách nói không ở lại (mức Cao)
        d = rng.choice(manh)
        them_bd(h, _gio(NGAY_TC - pd.Timedelta(days=rng.randint(0, 3)), rng), d[0], d[1], d[2])
    for h in co_kn[8:14]:                                                # khách đang suy nghĩ (mức Trung bình)
        d = rng.choice(nghi)
        them_bd(h, _gio(NGAY_TC - pd.Timedelta(days=rng.randint(0, 3)), rng), d[0], d[1], d[2])
    for h in rng.sample(nhom["ton_kt"], 8):                              # khách hỏi tiến độ lắp
        d = rng.choice(hoi)
        them_bd(h, _gio(thoi(h, "ton_kt") + pd.Timedelta(days=rng.randint(1, 3)), rng), "Thắc mắc", d[0], d[1])
    for h in rng.sample(nhom["cap_lan"], 3):
        d = rng.choice(kn)
        them_bd(h, _gio(thoi(h, "cap_lan") + pd.Timedelta(days=rng.randint(0, 2)), rng), "Khiếu nại, phàn nàn", d[0], d[1])

    def them_cd(h, t, nhom_ct, ct, tt, kq, diem):
        cd.append(dict(so_hd=ma[h], tg_do=_cat(t), nhom_ct=nhom_ct, chuong_trinh=ct, tinh_trang=tt, ket_qua_tu_van=kq, diem_rm=diem,
                       nhan_su_au=cskh[h], no_cuoc="0"))

    con_lai = [h for h in cll if h not in co_kn]
    for h in co_kn[14:20]:                                               # SR chủ động: điểm nguy cơ rời mạng cao, còn mở (Trung bình)
        d = rng.choice(sos)
        them_cd(h, _gio(NGAY_TC - pd.Timedelta(days=rng.randint(0, 2)), rng), "Nguy cơ rời mạng (SOS)", d[0], d[2], "", d[1])
    for h in con_lai[:6]:                                                # SR chủ động: khách yêu cầu thanh lý (Cao)
        d = rng.choice(tl)
        them_cd(h, _gio(NGAY_TC - pd.Timedelta(days=rng.randint(0, 2)), rng), d[0], d[1], d[2], d[3], d[4])
    for h in rng.sample(ds, 30):                                         # nền: SR chủ động khác, không kích hoạt luật
        d = rng.choice(khac)
        them_cd(h, _gio(NGAY_TC - pd.Timedelta(days=rng.randint(4, 12)), rng), d[0], d[1], d[2], d[3], d[4])
    return pd.DataFrame(bd), pd.DataFrame(cd)


def _no_cuoc(ma: dict, bd: pd.DataFrame, rng: random.Random) -> pd.DataFrame:
    codes = list(ma.values())
    chon = set(rng.sample(codes, int(len(codes) * 0.35))) | set(bd["so_hd"].head(5))
    return pd.DataFrame({"loai": "no_cuoc", "so_hd": sorted(chon), "ngay_chot": NGAY_TC.date().isoformat()})


def _kt_csv(kt: pd.DataFrame, ma: dict, mask_ktv: dict) -> pd.DataFrame:
    d = kt.copy()
    d["so_hd"] = d["so_hd"].map(ma)
    d["nguoi"] = d["nguoi"].map(lambda x: mask_ktv.get(str(x), "") if str(x) else "")
    d["thoi_diem"] = pd.to_datetime(d["thoi_diem"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    d["so_lan"] = pd.to_numeric(d["so_lan"], errors="coerce").astype("Int64").astype(str).replace("<NA>", "")
    return d[["so_hd", "loai", "thoi_diem", "chi_tiet", "nguoi", "so_lan"]]


def _kiem_an_toan(ra: dict[str, pd.DataFrame], bang_kt: list[pd.DataFrame], db: sqlite3.Connection) -> None:
    """Dừng nếu còn tên khách, mã hợp đồng hay tài khoản thật trong dữ liệu minh hoạ."""
    cam: set[str] = set()
    for b in bang_kt:
        for c in COT_NHAY_CAM:
            if c in b.columns:
                cam |= {str(v).strip().lower() for v in b[c].dropna() if len(str(v).strip()) >= 3}
    for sql in ("SELECT so_hd FROM dv_sr_bi_dong", "SELECT so_hd FROM dv_sr_chu_dong", "SELECT so_hd FROM dv_danh_sach", "SELECT hop_dong FROM fact_internet",
                "SELECT nhan_su_au FROM dv_sr_bi_dong", "SELECT nguoi_xu_ly FROM dv_sr_bi_dong", "SELECT nhan_su_au FROM dv_sr_chu_dong", "SELECT acc_nhan_vien FROM fact_internet"):
        cam |= {str(r[0]).strip().lower() for r in db.execute(sql) if r[0] and len(str(r[0]).strip()) >= 3}
    dai = [c for c in cam if len(c) >= 8 and not re.fullmatch(r"[a-z]{5}\d{4}", c)]
    ma_that = re.compile(r"^(?!mh)[a-z]{5}\d{4}$")
    loi = []
    for ten, d in ra.items():
        for cot in d.columns:
            for v in d[cot].fillna("").astype(str).str.strip().str.lower().unique():
                if v in cam or ma_that.match(v) or any(x in v for x in dai):
                    loi.append((ten, cot))
                    break
    if loi:
        sys.exit(f"DỪNG: còn dữ liệu thật trong bộ minh hoạ ở {sorted(set(loi))}. Không ghi file.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kt", default="E:\\", help="thư mục chứa 5 file báo cáo Kỹ thuật")
    ap.add_argument("--db", default=str(GOC / "data" / "thi.db"), help="database có dữ liệu DVKH để mượn loại SR")
    ap.add_argument("--out", default=str(GOC / "demo" / "lien_khoi"))
    a = ap.parse_args()
    rng = random.Random(HAT_GIONG)
    kt, bang_kt = _doc_kt(Path(a.kt))
    kt = _bo_xung_dot(kt)
    ma = _ma_gia(kt)
    mask_sale = {s: f"sale_{i:02d}" for i, s in enumerate(dict.fromkeys(kt["sale"].dropna().astype(str)), 1) if s}
    pool_sale = list(mask_sale.values())
    mask_ktv = {s: f"ktv_{i:02d}" for i, s in enumerate(dict.fromkeys(kt["nguoi"].dropna().astype(str)), 1) if s}
    mask_cskh = [f"cskh_{i:02d}" for i in range(1, 13)]
    db = sqlite3.connect(a.db)
    kd = _dung_kd(kt, ma, mask_sale, pool_sale, rng)
    bd, cd = _dung_sr(kt, kd, ma, db, mask_cskh, rng)
    bd["tg_yc"] = pd.to_datetime(bd["tg_yc"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    cd["tg_do"] = pd.to_datetime(cd["tg_do"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    ra = {"kd": kd, "kt": _kt_csv(kt, ma, mask_ktv), "sr_bi_dong": bd, "sr_chu_dong": cd, "no_cuoc": _no_cuoc(ma, bd, rng)}
    _kiem_an_toan(ra, bang_kt, db)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for ten, d in ra.items():
        d.to_csv(out / f"{ten}.csv", index=False, encoding="utf-8")
    (out / "meta.json").write_text(json.dumps({"ngay_tc": NGAY_TC.date().isoformat(), "so_hop_dong": len(ma), "hat_giong": HAT_GIONG,
                                               "ghi_chu": "Dữ liệu MINH HOẠ đã ghép mã, mã hợp đồng và tên người là giả định."}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Đã dựng:", {k: len(v) for k, v in ra.items()}, "| hợp đồng minh hoạ:", len(ma))


if __name__ == "__main__":
    main()
