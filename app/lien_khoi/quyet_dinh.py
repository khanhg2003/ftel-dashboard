"""Sổ quyết định của TRỢ LÝ ĐIỀU HÀNH (nhánh thi-lien-khoi): mỗi đề xuất của trợ lý là một dòng, người có quyền quyết chọn phương án,
trợ lý theo dõi và kiểm chứng kết quả sau đó. Lưu trong file trạng thái riêng của hướng liên khối (`theo_doi.py`), KHÔNG dùng database của app.

Trạng thái: `cho_quyet` -> `da_quyet` (hoặc `bac`) -> `da_kiem_chung`. Quá `han_quyet` mà chưa quyết thì nhắc, quá nữa thì báo cấp trên
và đổi sang `qua_han` (vẫn quyết được). Mọi thay đổi đều ghi nhật ký (ai, lúc nào, làm gì). Mốc giờ lưu UTC không kèm múi giờ như phần còn lại.
Hàm ở đây chỉ lưu và đọc; việc dựng đề xuất ở `tro_ly_dieu_hanh.py`, lệnh Zalo ở `zalo_lenh.py`.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pandas as pd

from app.config import rules_config
from app.lien_khoi import theo_doi as td

TRANG_THAI = {"cho_quyet": "Chờ quyết", "da_quyet": "Đã quyết", "bac": "Đã bác", "qua_han": "Quá hạn quyết", "da_kiem_chung": "Đã kiểm chứng"}
CHO = ("cho_quyet", "qua_han")                                   # còn quyết được
LUA_CHON_SUA = "sua"
COT_JSON = ("su_that", "phuong_an", "chi_so_truoc", "chi_so_sau")
COT_GHI = ("ma_van_de", "tieu_de", "khoi", "nguoi_quyet", "su_that", "nhan_dinh", "phuong_an", "khuyen_nghi", "han_quyet", "han_kiem_chung", "chi_so_truoc", "nguon_noi_dung")
MAC_DINH = {"han_quyet_gio": 8, "leo_thang_gio": 16, "kiem_chung_gio": 48}


def cau_hinh() -> dict:
    """Mốc giờ của vòng quyết định (đổi ở `rules.yml` → `lien_khoi.tro_ly`): hạn quyết sau khi trợ lý đề xuất, quá hạn thêm bao lâu thì báo cấp trên, bao lâu sau khi quyết thì đo lại."""
    c = ((rules_config().get("lien_khoi") or {}).get("tro_ly")) or {}
    return {k: float(c.get(k, v)) for k, v in MAC_DINH.items()}


def _json(v) -> dict | list:
    try:
        return json.loads(v) if isinstance(v, str) and v else {}
    except ValueError:
        return {}


def _dong(r) -> dict:
    d = dict(r)
    for c in COT_JSON:
        d[c] = _json(d.get(c))
    return d


def _nk(c, qd_id: int, luc: datetime, boi: str, hanh_dong: str, ghi_chu: str = "") -> None:
    c.execute("INSERT INTO quyet_dinh_nk (quyet_dinh_id, luc, boi, hanh_dong, ghi_chu) VALUES (?,?,?,?,?)", (qd_id, td._s(luc), boi, hanh_dong, ghi_chu or ""))


# ------------------------------------------------------------------ tạo và đọc
def tao(van_de: dict, now: datetime | None = None) -> int | None:
    """Thêm một đề xuất mới (`van_de` gồm các khoá của `COT_GHI`; trường JSON truyền dạng dict / list). Cùng `ma_van_de` đã có thì không tạo nữa, trả None."""
    now = now or td.bay_gio()
    gia_tri = [json.dumps(van_de[c], ensure_ascii=False) if c in COT_JSON else van_de.get(c) for c in COT_GHI]
    with td._KHOA, td._kn() as c:
        if c.execute("SELECT 1 FROM quyet_dinh WHERE ma_van_de=?", (van_de["ma_van_de"],)).fetchone():
            return None
        qid = c.execute(f"INSERT INTO quyet_dinh ({', '.join(COT_GHI)}, trang_thai, tao_luc, cap_nhat_luc) VALUES ({', '.join('?' * len(COT_GHI))}, 'cho_quyet', ?, ?)",
                        (*gia_tri, td._s(now), td._s(now))).lastrowid
        _nk(c, qid, now, "tro_ly", "de_xuat", van_de.get("tieu_de", ""))
    return qid


def doc(qid: int) -> dict | None:
    r = td._cau("SELECT * FROM quyet_dinh WHERE id=?", (int(qid),))
    return _dong(r[0]) if r else None


def doc_theo_ma(ma_van_de: str) -> dict | None:
    r = td._cau("SELECT * FROM quyet_dinh WHERE ma_van_de=?", (ma_van_de,))
    return _dong(r[0]) if r else None


def liet_ke(trang_thai: str | None = None) -> list[dict]:
    """Toàn bộ sổ quyết định, mới nhất trước (có thể lọc theo một trạng thái)."""
    sql, tham = "SELECT * FROM quyet_dinh", ()
    if trang_thai:
        sql, tham = sql + " WHERE trang_thai=?", (trang_thai,)
    return [_dong(r) for r in td._cau(sql + " ORDER BY id DESC", tham)]


def danh_sach(trang_thai: str | None = None) -> pd.DataFrame:
    return pd.DataFrame(liet_ke(trang_thai))


def cho_quyet(ma_nguoi: str, ds: pd.DataFrame | None = None) -> list[dict]:
    """Đề xuất còn chờ MÀ người này quyết được: thuộc phần của họ hoặc của cấp dưới (cấp trên quyết thay được). Cũ nhất trước."""
    ds = td.nguoi_nhan().fillna("") if ds is None else ds
    duoc = td.pham_vi(ma_nguoi, ds) if ma_nguoi else set()
    return [_dong(r) for r in td._cau(f"SELECT * FROM quyet_dinh WHERE trang_thai IN ({','.join('?' * len(CHO))}) ORDER BY id", CHO) if r["nguoi_quyet"] in duoc]


def duoc_quyet(ma_nguoi: str, qd: dict, ds: pd.DataFrame | None = None) -> bool:
    """Chỉ người nhận quyết hoặc quản lý cấp trên của họ."""
    ds = td.nguoi_nhan().fillna("") if ds is None else ds
    return bool(ma_nguoi) and qd["nguoi_quyet"] in td.pham_vi(ma_nguoi, ds)


def qua_han(now: datetime | None = None) -> list[dict]:
    """Đề xuất còn chờ mà đã quá `han_quyet`."""
    s = td._s(now or td.bay_gio())
    return [_dong(r) for r in td._cau(f"SELECT * FROM quyet_dinh WHERE trang_thai IN ({','.join('?' * len(CHO))}) AND han_quyet <= ? ORDER BY id", (*CHO, s))]


def can_kiem_chung(now: datetime | None = None) -> list[dict]:
    """Quyết định đã quyết, tới hạn đo lại mà chưa kiểm chứng."""
    s = td._s(now or td.bay_gio())
    return [_dong(r) for r in td._cau("SELECT * FROM quyet_dinh WHERE trang_thai='da_quyet' AND han_kiem_chung IS NOT NULL AND han_kiem_chung <= ? ORDER BY id", (s,))]


def nhat_ky(qid: int) -> pd.DataFrame:
    return pd.DataFrame([dict(r) for r in td._cau("SELECT luc, boi, hanh_dong, ghi_chu FROM quyet_dinh_nk WHERE quyet_dinh_id=? ORDER BY id", (int(qid),))],
                        columns=["luc", "boi", "hanh_dong", "ghi_chu"])


def tom_tat() -> dict:
    d = danh_sach()
    dem = d["trang_thai"].value_counts() if len(d) else {}
    return {"tong": int(len(d)), "cho_quyet": int(dem.get("cho_quyet", 0) + dem.get("qua_han", 0)), "da_quyet": int(dem.get("da_quyet", 0)),
            "bac": int(dem.get("bac", 0)), "qua_han": int(dem.get("qua_han", 0)), "da_kiem_chung": int(dem.get("da_kiem_chung", 0))}


# ------------------------------------------------------------------ đổi trạng thái
def _doi(qid: int, tu: tuple, cot: dict, boi: str, hanh_dong: str, ghi_chu: str, now: datetime) -> bool:
    """Chỉ đổi khi đang ở một trong các trạng thái `tu` (hai người cùng quyết một lúc thì chỉ một lượt được ghi)."""
    cot = {**cot, "cap_nhat_luc": td._s(now)}
    with td._KHOA, td._kn() as c:
        n = c.execute(f"UPDATE quyet_dinh SET {', '.join(f'{k}=?' for k in cot)} WHERE id=? AND trang_thai IN ({','.join('?' * len(tu))})", (*cot.values(), int(qid), *tu)).rowcount
        if n:
            _nk(c, int(qid), now, boi, hanh_dong, ghi_chu)
    return bool(n)


def quyet(qid: int, boi: str, lua_chon: str, ghi_chu: str = "", now: datetime | None = None) -> bool:
    """Ghi quyết định: `lua_chon` là mã phương án (A, B, C) hoặc "sua" (người quyết sửa ý, `ghi_chu` là ý kiến). Đặt luôn hạn kiểm chứng. False nếu không còn ở trạng thái chờ."""
    now = now or td.bay_gio()
    han = now + timedelta(hours=cau_hinh()["kiem_chung_gio"])
    return _doi(qid, CHO, {"trang_thai": "da_quyet", "lua_chon": lua_chon, "ghi_chu": ghi_chu or None, "quyet_boi": boi, "quyet_luc": td._s(now), "han_kiem_chung": td._s(han)},
                boi, "da_quyet", f"{lua_chon}: {ghi_chu}" if ghi_chu else lua_chon, now)


def bac(qid: int, boi: str, ly_do: str, now: datetime | None = None) -> bool:
    now = now or td.bay_gio()
    return _doi(qid, CHO, {"trang_thai": "bac", "ghi_chu": ly_do or None, "quyet_boi": boi, "quyet_luc": td._s(now)}, boi, "bac", ly_do, now)


def het_han(qid: int, now: datetime | None = None) -> bool:
    """Quá hạn quyết đã báo cấp trên: đổi sang `qua_han` (vẫn quyết được)."""
    now = now or td.bay_gio()
    return _doi(qid, ("cho_quyet",), {"trang_thai": "qua_han"}, "he_thong", "qua_han", "Quá hạn quyết, đã báo cấp trên", now)


def danh_dau(qid: int, cot: str, now: datetime | None = None) -> None:
    """Ghi giờ đã gửi tin đề xuất / nhắc / báo cấp trên / báo kiểm chứng (mỗi loại chỉ một lần)."""
    if cot not in ("da_gui_luc", "nhac_luc", "leo_thang_luc", "bao_kiem_chung_luc"):
        return
    td._ghi(f"UPDATE quyet_dinh SET {cot}=? WHERE id=?", (td._s(now or td.bay_gio()), int(qid)))


def ghi_kiem_chung(qid: int, chi_so_sau: dict, ket_qua: str, nguon_noi_dung: str, now: datetime | None = None) -> bool:
    now = now or td.bay_gio()
    return _doi(qid, ("da_quyet",), {"trang_thai": "da_kiem_chung", "chi_so_sau": json.dumps(chi_so_sau, ensure_ascii=False), "ket_qua": ket_qua},
                "tro_ly", "kiem_chung", f"{ket_qua} ({nguon_noi_dung})", now)
