"""Bộ RÀ SOÁT của Trợ lý điều hành: quét TẤT CẢ thực thể ở mọi cấp (nhân sự, phòng, khối, chi nhánh) để lãnh đạo không phải bấm từng người.

Chỉ ĐỌC số liệu qua hàm sẵn có của app (`bao_cao_phong.bang_nhan_su`, `overview`, `du_bao`, `dvkh.*`...), không tính lại công thức nào.
Mỗi nguồn quét là một hàm nhận NGỮ CẢNH `c` (đọc lười, mỗi nguồn dữ liệu đọc đúng một lần) và trả danh sách PHÁT HIỆN theo khuôn `_ph`; nguồn mới cắm thêm
bằng `dang_ky` (Kinh doanh ở `tro_ly_dieu_hanh_quet_kd.py`, DVKH ở `tro_ly_dieu_hanh_quet_dvkh.py`), không sửa lõi. Mỗi nguồn kèm `do_phu` báo "đã quét X/Y thực thể"
và mốc dữ liệu mới nhất. Một nguồn hỏng chỉ làm mất nguồn đó (ghi vào `c["loi"]`), không làm hỏng cả lượt. Nguyên tắc nghiệp vụ (AGENTS.md mục 4): trưởng phòng
không vào chỉ số cá nhân, người nghỉ / acc tạm không bị nêu nhưng số vẫn nằm trong số phòng, dùng chữ "online" cho hợp đồng đã lắp xong (xem AGENTS.md mục 4).
"""
from __future__ import annotations

from collections import namedtuple
from datetime import date, datetime

import pandas as pd

from app import metrics
from app.thoi_gian import LECH_GIO_VN, utc_bay_gio

CAO, TB, THAP = "cao", "trung_binh", "thap"
HANG_MUC = {CAO: 0, TB: 1, THAP: 2}
NHAN_MUC = {CAO: "Cao", TB: "Trung bình", THAP: "Thấp"}
TRE_KD_TB, TRE_KD_CAO = 2, 3          # số kinh doanh chậm hơn bấy nhiêu ngày so với hôm nay (hôm qua là bình thường)
TRE_DVKH_TB, TRE_DVKH_CAO = 4, 7      # file DVKH do người nạp tay nên chậm hơn
NguonQuet = namedtuple("NguonQuet", "ten nhan khoi quet do_phu")
NGUON_QUET: list[NguonQuet] = []
DO_CHI_SO: dict = {}                  # loại chỉ số -> hàm(c, tham_so) đo lại bằng ĐÚNG cách đã đo lúc đề xuất
_da_nap = False


def dang_ky(nguon: NguonQuet, do_chi_so: dict | None = None) -> None:
    """Cắm thêm một nguồn quét (Kinh doanh, DVKH, Kỹ thuật...). `quet(c)` trả danh sách phát hiện (`ph`), `do_phu(c)` trả {don_vi, da_quet, tong, du_lieu_luc}."""
    NGUON_QUET[:] = [n for n in NGUON_QUET if n.ten != nguon.ten] + [nguon]
    DO_CHI_SO.update(do_chi_so or {})


def _nap_nguon() -> None:
    """Nạp các nguồn có sẵn một lần (trong hàm để tránh vòng lặp import: hai module nguồn import lại module này)."""
    global _da_nap
    if not _da_nap:
        _da_nap = True
        from app import tro_ly_dieu_hanh_quet_dvkh, tro_ly_dieu_hanh_quet_kd  # noqa: F401  (đăng ký khi import)


def ngay_vn(c: dict) -> date:
    return (c["now"] + LECH_GIO_VN).date()


def ngu_canh(now: datetime | None = None) -> dict:
    """Ngữ cảnh một lượt quét: ngày số kinh doanh mới nhất, kho nhớ tạm của lượt, kho lỗi nguồn, từ điển acc -> họ tên (điền khi quét)."""
    now = now or utc_bay_gio()
    moi = metrics.ngay_moi_nhat()
    return {"now": now, "ngay_iso": moi, "thang": moi[:7] if moi else None, "ngay": int(moi[8:10]) if moi else None, "cache": {}, "loi": {}, "ten": {}}


def lay(c: dict, khoa: str, ham):
    """Đọc một nguồn dữ liệu đúng một lần trong lượt; lỗi thì ghi vào `c["loi"]` và trả None (nguồn đó coi như chưa có)."""
    if khoa not in c["cache"]:
        try:
            c["cache"][khoa] = ham()
        except Exception as e:
            c["cache"][khoa], c["loi"][khoa] = None, type(e).__name__
    return c["cache"][khoa]


def ph(nguon: str, nhom: str, **kw) -> dict:
    """Một PHÁT HIỆN theo khuôn chung: ma ổn định, khoi (kd|dvkh), cap (nhan_su|phong|khoi|chi_nhanh), doi_tuong, muc, diem (để xếp), tieu_de, bang_chung (dict số),
    duong_dan (trang xem chi tiết), nguoi_quyet ("bgd" | "tp:<phòng>"), chi_so (khuôn đo lại để kiểm chứng)."""
    kw.setdefault("bang_chung", {})
    return {"nguon": nguon, "nhom": nhom, "nhan_nhom": kw.get("tieu_de", ""), "don_vi": "", **kw}


def chi_so(loai: str, tham_so: dict, nhan: str, don_vi: str, tot_khi: str = "giam") -> dict:
    """Khuôn chỉ số theo dõi; `gia_tri` được điền khi gom vấn đề bằng chính hàm đo lại (`do_chi_so`)."""
    return {"loai": loai, "tham_so": tham_so, "nhan": nhan, "don_vi": don_vi, "tot_khi": tot_khi}


def quet(c: dict) -> list[dict]:
    """Chạy mọi nguồn đã đăng ký; một nguồn hỏng thì các nguồn khác vẫn chạy."""
    _nap_nguon()
    kq = []
    for n in NGUON_QUET:
        try:
            kq += n.quet(c)
        except Exception as e:
            c["loi"]["quet:" + n.ten] = type(e).__name__
    return kq


def so_do_phu(now: datetime | None = None, c: dict | None = None) -> list[dict]:
    """Độ phủ từng nguồn: đã quét X trên tổng Y thực thể + mốc dữ liệu mới nhất, để biết trợ lý nhìn được bao nhiêu (nguồn hỏng ghi `co_nguon` = False)."""
    _nap_nguon()
    c = c or ngu_canh(now)
    kq = []
    for n in NGUON_QUET:
        try:
            kq.append({"nguon": n.ten, "ten": n.nhan, "khoi": n.khoi, "co_nguon": True, "du_lieu_luc": "", "ghi_chu": "", **n.do_phu(c)})
        except Exception as e:
            c["loi"]["phu:" + n.ten] = type(e).__name__
            kq.append({"nguon": n.ten, "ten": n.nhan, "khoi": n.khoi, "co_nguon": False, "don_vi": "", "da_quet": 0, "tong": 0, "du_lieu_luc": "", "ghi_chu": ""})
    return kq


def do_chi_so(loai: str, tham_so: dict, c: dict):
    """Đo lại một chỉ số bằng CHÍNH hàm lúc đề xuất (dùng khi gom vấn đề và khi kiểm chứng)."""
    _nap_nguon()
    if loai not in DO_CHI_SO:
        raise ValueError(f"Chỉ số lạ: {loai}")
    return DO_CHI_SO[loai](c, tham_so)


# ------------------------------------------------------------------ nguồn "dữ liệu thiếu": khối / nguồn nào chưa có số hôm nay cũng là một phát hiện
def _muc_tre(tre: int, tb: int, cao: int) -> str:
    return CAO if tre >= cao else TB if tre >= tb else THAP


def _ph_thieu(nguon: str, ma: str, khoi: str, tieu_de: str, muc: str, diem: float, bc: dict, duong_dan: str, doi_tuong: str) -> dict:
    return ph(nguon, "du_lieu:" + ma, ma="du_lieu." + ma, khoi=khoi, cap="khoi", doi_tuong=doi_tuong, muc=muc, diem=diem, tieu_de=tieu_de, bang_chung=bc,
              duong_dan=duong_dan, nguoi_quyet="bgd", don_vi="nguồn", nhan_nhom="Dữ liệu chưa cập nhật",
              chi_so=chi_so("du_lieu_tre", {"nguon": ma}, f"Số ngày chậm của nguồn {doi_tuong}", "ngày"))


def _nguon_dvkh(c: dict) -> dict | None:
    from app.dvkh import so_lieu as sl
    return lay(c, "dv_ngay", lambda: sl.ngay_du_lieu() if sl.co_du_lieu() else None)


def tre_ngay(c: dict, ma: str):
    """Số ngày chậm của một nguồn so với hôm nay (None nếu nguồn chưa có dữ liệu nào)."""
    if ma == "kd":
        return None if not c["ngay_iso"] else (ngay_vn(c) - date.fromisoformat(c["ngay_iso"])).days
    nd = _nguon_dvkh(c) or {}
    d = nd.get(ma)
    return None if d is None else (ngay_vn(c) - pd.Timestamp(d).date()).days


NGUON_DU_LIEU = (("kd", "kd", "Kinh doanh (file số bán)", "/chatluong", TRE_KD_TB, TRE_KD_CAO),
                 ("sr_bd", "dvkh", "DVKH: SR bị động", "/dvkh/nap", TRE_DVKH_TB, TRE_DVKH_CAO), ("sr_cd", "dvkh", "DVKH: SR chủ động", "/dvkh/nap", TRE_DVKH_TB, TRE_DVKH_CAO),
                 ("roi_mang", "dvkh", "DVKH: rời mạng", "/dvkh/nap", TRE_DVKH_TB, TRE_DVKH_CAO), ("cong_no", "dvkh", "DVKH: công nợ", "/dvkh/nap", TRE_DVKH_TB, TRE_DVKH_CAO))


def quet_du_lieu(c: dict) -> list[dict]:
    kq = []
    for ma, khoi, ten, duong, tb, cao in NGUON_DU_LIEU:
        tre = tre_ngay(c, ma)
        if tre is None:                      # chưa có dòng nào: DVKH chưa nạp gì thì nêu một lần cho cả khối, đã nạp mà thiếu nguồn con thì nêu nguồn đó
            hoi_het = khoi == "dvkh" and _nguon_dvkh(c) is None
            if khoi == "kd" or not hoi_het or ma == "sr_bd":
                ten_hien = "Khối DVKH" if hoi_het else ten
                kq.append(_ph_thieu("du_lieu", ma, khoi, f"{ten_hien} chưa có dữ liệu nào", CAO if khoi == "kd" else TB, 50, {"ngay_tre": 999}, duong, ten_hien))
            continue
        muc = _muc_tre(tre, tb, cao)
        if muc != THAP:
            kq.append(_ph_thieu("du_lieu", ma, khoi, f"{ten} chậm {tre} ngày so với hôm nay", muc, float(tre), {"ngay_tre": tre}, duong, ten))
    return kq


def phu_du_lieu(c: dict) -> dict:
    co = [m for m, *_ in NGUON_DU_LIEU if tre_ngay(c, m) is not None]
    moi = [str(c["ngay_iso"])] if c["ngay_iso"] else []
    return {"don_vi": "nguồn dữ liệu", "da_quet": len(co), "tong": len(NGUON_DU_LIEU), "du_lieu_luc": "; ".join(moi + [f"{m}={tre_ngay(c, m)} ngày trước" for m in co if m != "kd"])[:200]}


def do_tre(c: dict, ts: dict):
    t = tre_ngay(c, ts["nguon"])
    return 999 if t is None else int(t)


dang_ky(NguonQuet("du_lieu", "Dữ liệu cập nhật chậm", "chung", quet_du_lieu, phu_du_lieu), {"du_lieu_tre": do_tre})
