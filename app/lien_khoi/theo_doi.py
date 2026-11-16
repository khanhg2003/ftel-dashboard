"""Trạng thái từng việc đã giao + hộp thư Zalo của hướng liên khối (nhánh thi-lien-khoi).

Lưu trong MỘT FILE SQLITE RIÊNG (`data/lien_khoi.db`; chạy minh hoạ thì `data/lien_khoi_demo.db`; đổi bằng biến `LIEN_KHOI_DB`), KHÔNG dùng database của app,
nên dù nhánh này gộp vào bản đang chạy thì cũng không đụng bảng nào của app.
Mốc thời gian lưu giờ UTC không kèm múi giờ (như quy ước của app), hiển thị đổi sang giờ Việt Nam.

Mỗi dòng `giao` là MỘT phần việc của MỘT người (vai trò sale / DVKH / Kỹ thuật) cho một (hợp đồng, luật):
mới giao -> đã nhận -> đã xong | không làm được. Quá hạn (mặc định 24 giờ) thì nhắc, quá 48 giờ thì báo quản lý (xem `zalo_viec.py`).
Việc mà luật không còn thấy dấu hiệu thì tự chuyển "hết dấu hiệu". Người nhận chưa biết (hàng chờ) thì giao cho đội trưởng khối đó.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from app.config import BASE_DIR, rules_config
from app.lien_khoi import luat, nguon
from app.thoi_gian import utc_bay_gio

TRANG_THAI = {"moi": "Mới giao", "da_nhan": "Đã nhận", "da_xong": "Đã xong", "khong_lam_duoc": "Không làm được", "tu_het": "Hết dấu hiệu"}
MO = ("moi", "da_nhan")                                   # còn phải làm
VAI_TRO = {"sale": "Sale", "dvkh": "DVKH", "kt": "Kỹ thuật"}
COT_NGUOI = ["ma", "ten", "khoi", "vai_tro", "quan_ly", "chat_id"]
_KHOA = threading.Lock()
_DA_TAO: set[str] = set()
DDL = """
CREATE TABLE IF NOT EXISTS giao (id INTEGER PRIMARY KEY AUTOINCREMENT, so_hd TEXT NOT NULL, luat TEXT NOT NULL, vai_tro TEXT NOT NULL, nguoi TEXT NOT NULL,
  nguoi_goc TEXT, ten_luat TEXT, muc TEXT, ly_do TEXT, de_xuat TEXT, trang_thai TEXT NOT NULL, tao_luc TEXT NOT NULL, han_luc TEXT NOT NULL, da_gui_luc TEXT,
  nhac_luc TEXT, bao_quan_ly_luc TEXT, cap_nhat_luc TEXT, cap_nhat_boi TEXT, ghi_chu TEXT, mo_phong INTEGER DEFAULT 0, giao_cho TEXT, giao_luc TEXT,
  UNIQUE (so_hd, luat, vai_tro));
CREATE TABLE IF NOT EXISTS nhat_ky (id INTEGER PRIMARY KEY AUTOINCREMENT, giao_id INTEGER, luc TEXT, boi TEXT, hanh_dong TEXT, ghi_chu TEXT);
CREATE TABLE IF NOT EXISTS hop_thu (id INTEGER PRIMARY KEY AUTOINCREMENT, luc TEXT, den_nguoi TEXT, chat_id TEXT, loai TEXT, noi_dung TEXT, kenh TEXT, ket_qua TEXT);
CREATE TABLE IF NOT EXISTS cai_dat (khoa TEXT PRIMARY KEY, gia_tri TEXT);
CREATE TABLE IF NOT EXISTS nguoi_nhan (ma TEXT PRIMARY KEY, ten TEXT, khoi TEXT, vai_tro TEXT, quan_ly TEXT, chat_id TEXT);
"""


def duong_dan() -> Path:
    import os
    if os.getenv("LIEN_KHOI_DB"):
        return Path(os.environ["LIEN_KHOI_DB"])
    return Path(BASE_DIR) / "data" / ("lien_khoi_demo.db" if nguon.la_demo() else "lien_khoi.db")


def _ket_noi() -> sqlite3.Connection:
    p = duong_dan()
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p, timeout=20)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA synchronous=NORMAL")                       # file trạng thái nhỏ, ghi rất nhiều lần: không cần chờ đĩa ở mỗi lần lưu
    if str(p) not in _DA_TAO:                                    # tạo bảng một lần cho mỗi file trong mỗi tiến trình (mở kết nối rất nhiều lần)
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(DDL)
        co = {r[1] for r in c.execute("PRAGMA table_info(giao)")}
        for cot, kieu in (("mo_phong", "INTEGER DEFAULT 0"), ("giao_cho", "TEXT"), ("giao_luc", "TEXT")):      # file trạng thái tạo từ bản cũ: thêm cột còn thiếu
            if cot not in co:
                c.execute(f"ALTER TABLE giao ADD COLUMN {cot} {kieu}")
        c.commit()
        _DA_TAO.add(str(p))
    return c


@contextmanager
def _kn():
    """Mở file trạng thái, lưu khi xong, luôn đóng (sqlite3 tự không đóng kết nối khi dùng `with`)."""
    c = _ket_noi()
    try:
        yield c
        c.commit()
    finally:
        c.close()


def _cau(sql: str, tham_so: tuple = ()) -> list[sqlite3.Row]:
    with _kn() as c:
        return c.execute(sql, tham_so).fetchall()


def _ghi(sql: str, tham_so: tuple = ()) -> int:
    with _KHOA, _kn() as c:
        return c.execute(sql, tham_so).lastrowid


def _s(t: datetime) -> str:
    return t.strftime("%Y-%m-%d %H:%M:%S")


def bay_gio() -> datetime:
    """Giờ UTC hiện tại; chạy minh hoạ có thể "lùi" thêm vài giờ để xem nhắc / báo quản lý mà không phải chờ."""
    t = utc_bay_gio().replace(tzinfo=None)
    return t + timedelta(hours=gio_gia_lap()) if nguon.la_demo() else t


def gio_gia_lap() -> float:
    r = _cau("SELECT gia_tri FROM cai_dat WHERE khoa='gio_gia_lap'")
    return float(r[0]["gia_tri"]) if r else 0.0


def them_gio_gia_lap(gio: float) -> float:
    """Chỉ có tác dụng ở chế độ minh hoạ."""
    if not nguon.la_demo():
        return 0.0
    moi = gio_gia_lap() + gio
    _ghi("INSERT INTO cai_dat (khoa, gia_tri) VALUES ('gio_gia_lap', ?) ON CONFLICT(khoa) DO UPDATE SET gia_tri=excluded.gia_tri", (str(moi),))
    return moi


def cau_hinh_gio() -> tuple[int, int]:
    c = rules_config().get("lien_khoi") or {}
    return int(c.get("han_gio", 24)), int(c.get("bao_quan_ly_gio", 48))


# ------------------------------------------------------------------ người nhận
def nguoi_nhan_that() -> pd.DataFrame:
    return pd.DataFrame([dict(r) for r in _cau("SELECT * FROM nguoi_nhan")], columns=COT_NGUOI)


def nap_nguoi_nhan(df: pd.DataFrame) -> int:
    """Nạp / cập nhật danh sách người nhận việc (cột `COT_NGUOI`; `chat_id` lấy từ người nhắn bot). Thay theo mã."""
    n = 0
    for r in df.fillna("").to_dict("records"):
        _ghi("INSERT INTO nguoi_nhan (ma, ten, khoi, vai_tro, quan_ly, chat_id) VALUES (?,?,?,?,?,?) ON CONFLICT(ma) DO UPDATE SET ten=excluded.ten, "
             "khoi=excluded.khoi, vai_tro=excluded.vai_tro, quan_ly=excluded.quan_ly, chat_id=excluded.chat_id",
             tuple(str(r.get(c, "")) for c in COT_NGUOI))
        n += 1
    return n


def nguoi_nhan() -> pd.DataFrame:
    return nguon.nguoi_nhan() if nguon.la_demo() else nguoi_nhan_that()


VAI_TRO_QUAN_LY = ("tp_khoi", "truong_phong", "truong_nhom", "dieu_hanh", "doi_truong", "giam_doc")
THU_TU_HANG_CHO = ("tp_khoi", "doi_truong")                # ai nhận việc hàng chờ của một khối: trưởng phòng khối trước, không có thì đội trưởng


def doi_truong(khoi: str, ds: pd.DataFrame) -> str:
    """Mã người nhận hàng chờ của một khối (trưởng phòng khối, không có thì đội trưởng). Chưa có thì rỗng."""
    for vt in THU_TU_HANG_CHO:
        x = ds[(ds["khoi"] == khoi) & (ds["vai_tro"] == vt)]
        if len(x):
            return str(x["ma"].iloc[0])
    return ""


def quan_ly_cua(ma: str, ds: pd.DataFrame) -> str:
    """Quản lý trực tiếp nhận tin của một phần việc: nhân viên thì lấy quản lý trong danh sách; người nhận đã là quản lý (việc hàng chờ) thì chính họ."""
    x = ds[ds["ma"] == ma]
    if x.empty:
        return ""
    r = x.iloc[0]
    return str(r["quan_ly"] or "") if r["vai_tro"] == "nhan_vien" else str(ma)


def giam_doc(ds: pd.DataFrame) -> str:
    """Mã giám đốc chi nhánh (nhận báo cáo việc quá mốc báo quản lý). Chưa có thì rỗng."""
    x = ds[ds["vai_tro"] == "giam_doc"]
    return str(x["ma"].iloc[0]) if len(x) else ""


def cap_duoi(ma_ql: str, ds: pd.DataFrame) -> pd.DataFrame:
    """Người báo cáo trực tiếp cho một quản lý: nhân viên trong team và các quản lý cấp dưới. Dùng cho danh sách "Giao cho"."""
    return ds[ds["quan_ly"] == ma_ql].copy()


def pham_vi(ma_ql: str, ds: pd.DataFrame) -> set[str]:
    """Mọi mã quản lý nằm dưới (và gồm cả) một quản lý: trưởng phòng khối xem việc của các trưởng nhóm / điều hành dưới mình."""
    kq, cho = {ma_ql}, [ma_ql]
    while cho:
        con = set(ds.loc[ds["quan_ly"].isin(cho) & ds["vai_tro"].isin(VAI_TRO_QUAN_LY), "ma"]) - kq
        kq |= con
        cho = list(con)
    return kq


def _nguoi_giao(r, ds: pd.DataFrame) -> list[tuple[str, str, str]]:
    """Việc này giao cho ai: [(vai_tro, mã người, nguồn gốc)]. Hàng chờ -> đội trưởng khối đó; "không có trong file bán hàng" thì không có người nhận."""
    out = []
    for vt, gia_tri, hang_cho, khoi in (("sale", r["giao_sale"], None, "KD"), ("dvkh", r["giao_dvkh"], luat.GIAO_DVKH, "DVKH"), ("kt", r["giao_kt"], luat.GIAO_KT, "KT")):
        gt = str(gia_tri or "").strip()
        if not gt or gt == luat.KHONG_CO_SALE:
            continue
        if hang_cho and gt == hang_cho:
            dt = doi_truong(khoi, ds)
            if dt:
                out.append((vt, dt, gt))
            continue
        out.append((vt, gt, ""))
    return out


# ------------------------------------------------------------------ đồng bộ với các luật
def dong_bo(viec: pd.DataFrame, now: datetime | None = None) -> dict:
    """Đưa việc hiện tại của các luật vào bảng giao việc: việc mới thì thêm, việc cũ giữ nguyên trạng thái, việc hết dấu hiệu thì đóng.
    Làm trong MỘT lần mở file (hàng trăm phần việc, mở từng lần rất chậm)."""
    now = now or bay_gio()
    han, _ = cau_hinh_gio()
    ds = nguoi_nhan()
    hien_co: set[tuple] = set()
    moi = mo_lai = het = 0
    tao, han_luc = _s(now), _s(now + timedelta(hours=han))
    nk = "INSERT INTO nhat_ky (giao_id, luc, boi, hanh_dong, ghi_chu) VALUES (?,?,?,?,?)"
    with _KHOA, _kn() as c:
        for r in viec.to_dict("records"):
            for vt, ma_nguoi, goc in _nguoi_giao(r, ds):
                khoa = (r["so_hd"], r["luat"], vt)
                hien_co.add(khoa)
                cu = c.execute("SELECT id, trang_thai FROM giao WHERE so_hd=? AND luat=? AND vai_tro=?", khoa).fetchone()
                if cu is None:
                    gid = c.execute("INSERT INTO giao (so_hd, luat, vai_tro, nguoi, nguoi_goc, ten_luat, muc, ly_do, de_xuat, trang_thai, tao_luc, han_luc) "
                                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (*khoa, ma_nguoi, goc, r["ten_luat"], r["muc"], r["ly_do"], r["de_xuat"], "moi", tao, han_luc)).lastrowid
                    c.execute(nk, (gid, tao, "he_thong", "giao", r["ly_do"]))
                    moi += 1
                elif cu["trang_thai"] == "tu_het":                       # dấu hiệu quay lại: mở lại, tính hạn mới
                    c.execute("UPDATE giao SET trang_thai='moi', tao_luc=?, han_luc=?, da_gui_luc=NULL, nhac_luc=NULL, bao_quan_ly_luc=NULL, muc=?, ly_do=?, de_xuat=? WHERE id=?",
                              (tao, han_luc, r["muc"], r["ly_do"], r["de_xuat"], cu["id"]))
                    c.execute(nk, (cu["id"], tao, "he_thong", "mo_lai", "Dấu hiệu quay lại"))
                    mo_lai += 1
                elif cu["trang_thai"] in MO:
                    c.execute("UPDATE giao SET muc=?, ly_do=?, de_xuat=? WHERE id=?", (r["muc"], r["ly_do"], r["de_xuat"], cu["id"]))
        for r in c.execute("SELECT id, so_hd, luat, vai_tro FROM giao WHERE trang_thai IN ('moi','da_nhan') AND COALESCE(mo_phong, 0) = 0").fetchall():   # lịch sử mô phỏng không bị luật đóng
            if (r["so_hd"], r["luat"], r["vai_tro"]) not in hien_co:
                c.execute("UPDATE giao SET trang_thai='tu_het', cap_nhat_luc=?, cap_nhat_boi='he_thong', ghi_chu='Luật không còn thấy dấu hiệu' WHERE id=?", (tao, r["id"]))
                c.execute(nk, (r["id"], tao, "he_thong", "tu_het", "Luật không còn thấy dấu hiệu"))
                het += 1
    return {"moi": moi, "mo_lai": mo_lai, "het": het}


# ------------------------------------------------------------------ đọc và cập nhật
def danh_sach(now: datetime | None = None) -> pd.DataFrame:
    """Mọi phần việc đã giao kèm cờ quá hạn; việc quá hạn xếp trước, rồi mức Cao, rồi việc mới nhất."""
    now = now or bay_gio()
    d = pd.DataFrame([dict(r) for r in _cau("SELECT * FROM giao")])
    if d.empty:
        return d
    for c in ("tao_luc", "han_luc"):
        d[c] = pd.to_datetime(d[c])
    ds = nguoi_nhan().fillna("")
    d["quan_ly"] = d["nguoi"].map(lambda m: quan_ly_cua(m, ds))
    d["con_lai_gio"] = ((d["han_luc"] - pd.Timestamp(now)).dt.total_seconds() / 3600).round(1)
    d["dang_mo"] = d["trang_thai"].isin(MO)
    d["qua_han"] = d["dang_mo"] & (d["con_lai_gio"] < 0)
    d["_t"] = (~d["qua_han"]).astype(int) * 10 + d["muc"].map({luat.CAO: 0, luat.TB: 1}).fillna(2)
    return d.sort_values(["_t", "tao_luc"], ascending=[True, False]).drop(columns="_t").reset_index(drop=True)


def danh_sach_day_du(now: datetime | None = None) -> pd.DataFrame:
    """`danh_sach` kèm `phan_hoi_luc` (lần đầu người nhận làm gì đó với phần việc: nhận, xong hoặc không làm được) để đo thời gian phản hồi."""
    d = danh_sach(now)
    if d.empty:
        return d.assign(phan_hoi_luc=pd.NaT)
    ph = pd.DataFrame([dict(r) for r in _cau("SELECT giao_id, MIN(luc) AS luc FROM nhat_ky WHERE hanh_dong IN ('giao_cho','da_nhan','da_xong','khong_lam_duoc') GROUP BY giao_id")],
                      columns=["giao_id", "luc"])
    ph["luc"] = pd.to_datetime(ph["luc"])
    d = d.merge(ph.rename(columns={"giao_id": "id", "luc": "phan_hoi_luc"}), on="id", how="left")
    d["cap_nhat_luc"] = pd.to_datetime(d["cap_nhat_luc"])
    d["bao_quan_ly_luc"] = pd.to_datetime(d["bao_quan_ly_luc"])
    return d


def chen_lich_su(rows: list[dict]) -> int:
    """Nạp lịch sử MÔ PHỎNG (chỉ chế độ minh hoạ, xem `mo_phong.py`): mỗi dòng gồm các cột `giao` và `nhat_ky` = [(luc, boi, hanh_dong, ghi_chu)]. Mọi dòng bị đánh dấu `mo_phong`."""
    if not nguon.la_demo():
        raise RuntimeError("Chỉ được nạp lịch sử mô phỏng ở chế độ minh hoạ.")
    cot = ("so_hd", "luat", "vai_tro", "nguoi", "ten_luat", "muc", "ly_do", "de_xuat", "trang_thai", "tao_luc", "han_luc", "da_gui_luc", "nhac_luc",
           "bao_quan_ly_luc", "cap_nhat_luc", "cap_nhat_boi", "ghi_chu", "giao_cho", "giao_luc")
    with _KHOA, _kn() as c:
        for r in rows:
            gid = c.execute(f"INSERT OR IGNORE INTO giao ({', '.join(cot)}, mo_phong) VALUES ({', '.join('?' * len(cot))}, 1)", tuple(r.get(k) for k in cot)).lastrowid
            if gid:
                c.executemany("INSERT INTO nhat_ky (giao_id, luc, boi, hanh_dong, ghi_chu) VALUES (?,?,?,?,?)", [(gid, *n) for n in r.get("nhat_ky", [])])
    return len(rows)


def doc_moc() -> dict:
    """Mốc đo được TRƯỚC khi dùng hệ thống (người dùng nhập): {"gio_xu_ly": số giờ, "ty_le_dung_han": %}. Chưa nhập thì không có khoá đó."""
    return {r["khoa"][4:]: float(r["gia_tri"]) for r in _cau("SELECT khoa, gia_tri FROM cai_dat WHERE khoa LIKE 'moc_%'") if r["gia_tri"] not in (None, "")}


def ghi_moc(gio_xu_ly: float | None, ty_le_dung_han: float | None) -> None:
    for k, v in (("moc_gio_xu_ly", gio_xu_ly), ("moc_ty_le_dung_han", ty_le_dung_han)):
        if v is None:
            _ghi("DELETE FROM cai_dat WHERE khoa=?", (k,))
        else:
            _ghi("INSERT INTO cai_dat (khoa, gia_tri) VALUES (?, ?) ON CONFLICT(khoa) DO UPDATE SET gia_tri=excluded.gia_tri", (k, str(float(v))))


def tom_tat(d: pd.DataFrame) -> dict:
    if d.empty:
        return {"tong": 0, "moi": 0, "da_nhan": 0, "da_xong": 0, "khong_lam_duoc": 0, "tu_het": 0, "qua_han": 0, "da_bao_ql": 0, "ty_le_xong": None}
    dem = d["trang_thai"].value_counts()
    thuc = int(len(d) - dem.get("tu_het", 0))
    return {"tong": int(len(d)), **{k: int(dem.get(k, 0)) for k in TRANG_THAI}, "qua_han": int(d["qua_han"].sum()),
            "da_bao_ql": int(d["bao_quan_ly_luc"].notna().sum()), "ty_le_xong": round(100 * int(dem.get("da_xong", 0)) / thuc, 1) if thuc else None}


def cap_nhat(giao_id: int, trang_thai: str, boi: str, ghi_chu: str = "", now: datetime | None = None) -> bool:
    """Người nhận cập nhật trạng thái phần việc của mình. False nếu không có việc đó hoặc trạng thái không hợp lệ."""
    if trang_thai not in ("da_nhan", "da_xong", "khong_lam_duoc") or not _cau("SELECT id FROM giao WHERE id=?", (giao_id,)):
        return False
    now = now or bay_gio()
    _ghi("UPDATE giao SET trang_thai=?, cap_nhat_luc=?, cap_nhat_boi=?, ghi_chu=? WHERE id=?", (trang_thai, _s(now), boi, ghi_chu or None, giao_id))
    _ghi("INSERT INTO nhat_ky (giao_id, luc, boi, hanh_dong, ghi_chu) VALUES (?,?,?,?,?)", (giao_id, _s(now), boi, trang_thai, ghi_chu))
    return True


def cap_nhat_nhieu(thay_doi: list[tuple]) -> int:
    """Như nhiều lần `cap_nhat` nhưng trong MỘT lần mở file: [(giao_id, trạng thái, người, ghi chú, giờ UTC)]. Dòng có trạng thái lạ bị bỏ qua."""
    n = 0
    with _KHOA, _kn() as c:
        for gid, tt, boi, ghi_chu, luc in thay_doi:
            if tt not in ("da_nhan", "da_xong", "khong_lam_duoc"):
                continue
            c.execute("UPDATE giao SET trang_thai=?, cap_nhat_luc=?, cap_nhat_boi=?, ghi_chu=? WHERE id=?", (tt, _s(luc), boi, ghi_chu or None, int(gid)))
            c.execute("INSERT INTO nhat_ky (giao_id, luc, boi, hanh_dong, ghi_chu) VALUES (?,?,?,?,?)", (int(gid), _s(luc), boi, tt, ghi_chu or ""))
            n += 1
    return n


def giao_viec(ids: list[int], giao_cho: str, boi: str, now: datetime | None = None) -> int:
    """Quản lý `boi` giao các phần việc cho nhân viên `giao_cho` (một lần cho nhiều việc). Việc mới giao chuyển sang "đã nhận"; việc đã xong hoặc đã đóng không đổi.
    Trả về số phần việc được ghi nhận."""
    now = now or bay_gio()
    n = 0
    with _KHOA, _kn() as c:
        for gid in ids:
            r = c.execute("SELECT trang_thai FROM giao WHERE id=?", (int(gid),)).fetchone()
            if r is None or r["trang_thai"] not in MO:
                continue
            c.execute("UPDATE giao SET giao_cho=?, giao_luc=?, trang_thai='da_nhan', cap_nhat_luc=?, cap_nhat_boi=? WHERE id=?", (giao_cho, _s(now), _s(now), boi, int(gid)))
            c.execute("INSERT INTO nhat_ky (giao_id, luc, boi, hanh_dong, ghi_chu) VALUES (?,?,?,?,?)", (int(gid), _s(now), boi, "giao_cho", giao_cho))
            n += 1
    return n


def giao_nhieu(thay_doi: list[tuple]) -> int:
    """Như nhiều lần `giao_viec` trong MỘT lần mở file (dùng cho mô phỏng): [(giao_id, giao_cho, người giao, giờ UTC)]."""
    n = 0
    with _KHOA, _kn() as c:
        for gid, giao_cho, boi, luc in thay_doi:
            c.execute("UPDATE giao SET giao_cho=?, giao_luc=?, trang_thai='da_nhan', cap_nhat_luc=?, cap_nhat_boi=? WHERE id=?", (giao_cho, _s(luc), _s(luc), boi, int(gid)))
            c.execute("INSERT INTO nhat_ky (giao_id, luc, boi, hanh_dong, ghi_chu) VALUES (?,?,?,?,?)", (int(gid), _s(luc), boi, "giao_cho", giao_cho))
            n += 1
    return n


def danh_dau(ids: list[int], cot: str, now: datetime | None = None) -> None:
    """Ghi giờ đã gửi tin giao việc / nhắc / báo quản lý cho các phần việc (mỗi loại chỉ gửi một lần)."""
    if cot not in ("da_gui_luc", "nhac_luc", "bao_quan_ly_luc") or not ids:
        return
    _ghi(f"UPDATE giao SET {cot}=? WHERE id IN ({','.join('?' * len(ids))})", (_s(now or bay_gio()), *[int(i) for i in ids]))


def nhat_ky(giao_id: int) -> pd.DataFrame:
    return pd.DataFrame([dict(r) for r in _cau("SELECT luc, boi, hanh_dong, ghi_chu FROM nhat_ky WHERE giao_id=? ORDER BY id", (giao_id,))],
                        columns=["luc", "boi", "hanh_dong", "ghi_chu"])


def ghi_hop_thu(den_nguoi: str, chat_id: str, loai: str, noi_dung: str, kenh: str, ket_qua: str, now: datetime | None = None) -> None:
    _ghi("INSERT INTO hop_thu (luc, den_nguoi, chat_id, loai, noi_dung, kenh, ket_qua) VALUES (?,?,?,?,?,?,?)",
         (_s(now or bay_gio()), den_nguoi, chat_id, loai, noi_dung, kenh, ket_qua))


def hop_thu(toi_da: int = 100) -> pd.DataFrame:
    return pd.DataFrame([dict(r) for r in _cau("SELECT * FROM hop_thu ORDER BY id DESC LIMIT ?", (toi_da,))],
                        columns=["id", "luc", "den_nguoi", "chat_id", "loai", "noi_dung", "kenh", "ket_qua"])


def xoa_het_minh_hoa() -> None:
    """Làm lại từ đầu (CHỈ chạy minh hoạ): xoá giao việc, nhật ký, hộp thư và giờ giả lập của file trạng thái minh hoạ."""
    if not nguon.la_demo():
        raise RuntimeError("Chỉ được xoá ở chế độ minh hoạ.")
    with _KHOA, _kn() as c:
        for t in ("giao", "nhat_ky", "hop_thu", "cai_dat"):
            c.execute(f"DELETE FROM {t}")
