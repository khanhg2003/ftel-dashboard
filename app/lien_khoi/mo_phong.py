"""Mô phỏng người nhận "làm việc" cho bản minh hoạ (nhánh thi-lien-khoi), để tab "Hiệu quả" và kịch bản demo có số đo hợp lý.

Hai việc, CHỈ chạy được ở chế độ minh hoạ (`LIEN_KHOI_NGUON=demo`):
1. `nap_lich_su` / `chuan_bi_demo`: dựng 14 ngày giao việc đã diễn ra (mã `MHLS0001...`, mọi dòng đánh dấu `mo_phong`, giao diện ghi rõ "mô phỏng").
2. `tien_thoi_gian`: khi đồng hồ minh hoạ chạy tới, các phần việc THẬT đang mở của hôm nay được "người nhận" xử lý theo tốc độ riêng từng người
   (người nhanh làm xong trong ngày, người chậm quá hạn, có người không làm được, có người không phản hồi), nên lùi đồng hồ không làm số đo tụt vô lý.
Mọi quyết định (ai nhanh, ai chậm, xong hay không) lấy từ hạt giống cố định theo mã hợp đồng và người nhận: chạy lại ra đúng cùng kết quả.
Không có tên khách hàng. Lịch sử mô phỏng không bao giờ bị gửi, nhắc hay báo quản lý (xem `zalo_viec.py`).
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta

from app.lien_khoi import luat, nguon, theo_doi as td

HAT_GIONG = 20261114
SO_NGAY = 14
VIEC_MOI_NGAY = 24
VAI_TRO_THEO_LUAT = {"cho_online": ("sale", "kt"), "loi_som": ("sale", "dvkh", "kt"), "su_co_lap": ("sale", "dvkh", "kt"), "co_y_roi": ("sale", "dvkh")}
TRONG_SO_LUAT = {"cho_online": 0.35, "su_co_lap": 0.30, "co_y_roi": 0.20, "loi_som": 0.15}
KHOI_CUA_VAI_TRO = {"sale": "KD", "dvkh": "DVKH", "kt": "KT"}
XONG_CO_BAN = {"sale": 0.85, "dvkh": 0.72, "kt": 0.78}                 # xác suất làm xong của người có tốc độ trung bình
TOC_DO = [0.55, 0.8, 1.0, 1.0, 1.25, 2.1]                              # hệ số thời gian của mỗi người: nhỏ = nhanh
LY_DO_KHONG_LAM_DUOC = ["Khách hẹn tuần sau", "Chưa liên lạc được khách", "Đang chờ vật tư", "Khách từ chối hỗ trợ", "Hợp đồng đã chuyển đơn vị khác"]
MAU_LY_DO = {"cho_online": "Mô phỏng: hợp đồng chờ online quá hạn", "loi_som": "Mô phỏng: lỗi sớm sau lắp", "su_co_lap": "Mô phỏng: checklist lặp từ 2 lần",
             "co_y_roi": "Mô phỏng: khách có ý rời"}


def _s(t: datetime) -> str:
    return t.strftime("%Y-%m-%d %H:%M:%S")


def toc_do_nguoi(ma: str) -> float:
    """Tốc độ của một người (cố định theo mã người)."""
    return random.Random(f"{HAT_GIONG}:toc_do:{ma}").choice(TOC_DO)


def _log_chuan(rng: random.Random, trung_vi: float, do_lech: float) -> float:
    return math.exp(rng.gauss(math.log(trung_vi), do_lech))


def _ket_qua(rng: random.Random, vai_tro: str, toc: float, toc_ql: float | None = None) -> dict:
    """Mọi quyết định của MỘT phần việc, rút theo thứ tự cố định để chạy lúc nào cũng ra cùng kết quả: xong / không làm được / bỏ ngỏ, giờ phản hồi, giờ xử lý.
    Giờ phản hồi là lúc QUẢN LÝ nhận tin và giao việc (tốc độ của quản lý, `toc_ql`); giờ xử lý là của người làm (`toc`)."""
    p_xong = max(0.25, min(0.95, XONG_CO_BAN[vai_tro] - 0.14 * (toc - 1)))
    r1, r2 = rng.random(), rng.random()
    gio_ph = _log_chuan(rng, 1.6 * (toc if toc_ql is None else toc_ql), 0.7)
    gio_xl = max(gio_ph + 0.2, _log_chuan(rng, 13 * toc, 0.55))
    return {"kq": "xong" if r1 < p_xong else ("khong" if r2 < 0.3 else "bo_ngo"), "gio_ph": gio_ph, "gio_xl": gio_xl, "nhan_truoc": rng.random() < 0.6,
            "nhan_bo_ngo": rng.random() < 0.4, "ly_do": rng.choice(LY_DO_KHONG_LAM_DUOC)}


def _mot_phan_viec(rng: random.Random, ma_hd: str, luat_ma: str, vai_tro: str, nguoi: str, tao: datetime, now: datetime, han: int, ql: int, quan_ly: str = "") -> dict:
    """Một phần việc đã diễn ra: quản lý `quan_ly` nhận tin rồi giao cho `nguoi`, bao lâu, xong / không làm được / còn bỏ ngỏ (quá hạn, đã nhắc, báo giám đốc)."""
    k = _ket_qua(rng, vai_tro, toc_do_nguoi(nguoi), toc_do_nguoi(quan_ly) if quan_ly else None)
    muc = luat.CAO if rng.random() < 0.45 else luat.TB
    nhat_ky = [(_s(tao), "he_thong", "giao", MAU_LY_DO[luat_ma])]
    trang_thai, cap_nhat, ghi_chu, giao_luc = "moi", None, None, None
    if k["kq"] != "bo_ngo" and tao + timedelta(hours=k["gio_xl"]) <= now:
        cap_nhat = tao + timedelta(hours=k["gio_xl"])
        if k["nhan_truoc"] and k["gio_ph"] < k["gio_xl"]:                     # nhiều quản lý giao việc trước rồi người làm mới xong
            giao_luc = tao + timedelta(hours=k["gio_ph"])
            nhat_ky.append((_s(giao_luc), quan_ly or nguoi, "giao_cho", nguoi))
        if k["kq"] == "xong":
            trang_thai = "da_xong"
            nhat_ky.append((_s(cap_nhat), nguoi, "da_xong", ""))
        else:
            trang_thai, ghi_chu = "khong_lam_duoc", k["ly_do"]
            nhat_ky.append((_s(cap_nhat), nguoi, "khong_lam_duoc", ghi_chu))
    elif k["kq"] == "bo_ngo" and k["nhan_bo_ngo"] and tao + timedelta(hours=k["gio_ph"]) <= now:     # nhận rồi nhưng không làm tiếp
        trang_thai = "da_nhan"
        cap_nhat = giao_luc = tao + timedelta(hours=k["gio_ph"])
        nhat_ky.append((_s(cap_nhat), quan_ly or nguoi, "giao_cho", nguoi))
    han_luc = tao + timedelta(hours=han)
    dang_mo = trang_thai in td.MO
    return {"so_hd": ma_hd, "luat": luat_ma, "vai_tro": vai_tro, "nguoi": nguoi, "ten_luat": luat.TEN_LUAT[luat_ma], "muc": muc,
            "ly_do": MAU_LY_DO[luat_ma], "de_xuat": luat.DE_XUAT[luat_ma], "trang_thai": trang_thai, "tao_luc": _s(tao), "han_luc": _s(han_luc),
            "da_gui_luc": _s(tao + timedelta(minutes=5)), "nhac_luc": _s(han_luc) if dang_mo and han_luc <= now else None,
            "bao_quan_ly_luc": _s(tao + timedelta(hours=ql)) if dang_mo and tao + timedelta(hours=ql) <= now else None,
            "cap_nhat_luc": _s(cap_nhat) if cap_nhat else None, "cap_nhat_boi": nguoi if cap_nhat else None, "ghi_chu": ghi_chu, "nhat_ky": nhat_ky,
            "giao_cho": nguoi if giao_luc else None, "giao_luc": _s(giao_luc) if giao_luc else None}


def dung_lich_su(nguoi_nhan, now: datetime, so_ngay: int = SO_NGAY, viec_moi_ngay: int = VIEC_MOI_NGAY, hat: int = HAT_GIONG) -> list[dict]:
    """Danh sách phần việc mô phỏng của `so_ngay` ngày trước `now` (thuần: không ghi gì)."""
    rng = random.Random(hat)
    han, ql = td.cau_hinh_gio()
    nv = nguoi_nhan[nguoi_nhan["vai_tro"] == "nhan_vien"]
    theo_khoi = {k: sorted(nv.loc[nv["khoi"] == k, "ma"]) for k in ("KD", "DVKH", "KT")}
    cua = dict(zip(nv["ma"], nv["quan_ly"]))                                   # nhân viên -> quản lý nhận tin
    luat_ds, w = list(TRONG_SO_LUAT), list(TRONG_SO_LUAT.values())
    rows, dem = [], 0
    for ngay in range(so_ngay, 0, -1):
        for _ in range(viec_moi_ngay):
            dem += 1
            lm = rng.choices(luat_ds, w)[0]
            tao = now - timedelta(days=ngay) + timedelta(hours=rng.uniform(-4, 4))
            for vt in VAI_TRO_THEO_LUAT[lm]:
                ds = theo_khoi[KHOI_CUA_VAI_TRO[vt]]
                if ds:
                    ma = rng.choice(ds)
                    rows.append(_mot_phan_viec(rng, f"MHLS{dem:04d}", lm, vt, ma, tao, now, han, ql, cua.get(ma, "")))
    return rows


def nap_lich_su(now: datetime | None = None) -> int:
    """Ghi lịch sử mô phỏng vào file trạng thái minh hoạ. Trả về số phần việc đã nạp."""
    if not nguon.la_demo():
        raise RuntimeError("Chỉ được nạp lịch sử mô phỏng ở chế độ minh hoạ.")
    return td.chen_lich_su(dung_lich_su(td.nguoi_nhan(), now or td.bay_gio()))


def tien_thoi_gian(now: datetime | None = None) -> dict:
    """Đồng hồ minh hoạ vừa chạy tới `now`: người nhận xử lý các phần việc THẬT đang mở theo tốc độ riêng (nhận, xong, không làm được, hoặc bỏ ngỏ).
    Gọi lại nhiều lần an toàn: chỉ đụng việc còn mở và quyết định luôn như nhau."""
    if not nguon.la_demo():
        raise RuntimeError("Chỉ được mô phỏng người nhận ở chế độ minh hoạ.")
    now = now or td.bay_gio()
    d = td.danh_sach(now)
    if d.empty:
        return {"xong": 0, "khong_lam_duoc": 0, "da_nhan": 0}
    d = d[d["dang_mo"] & (d["mo_phong"].fillna(0) == 0)]
    dem = {"xong": 0, "khong_lam_duoc": 0, "da_nhan": 0}
    thay_doi, giao = [], []
    for r in d.to_dict("records"):
        ql = r.get("quan_ly") or ""
        k = _ket_qua(random.Random(f"{HAT_GIONG}:{r['so_hd']}:{r['luat']}:{r['vai_tro']}"), r["vai_tro"], toc_do_nguoi(r["nguoi"]), toc_do_nguoi(ql) if ql else None)
        tao, gid, ai = r["tao_luc"].to_pydatetime(), int(r["id"]), r["nguoi"]
        xong_luc = tao + timedelta(hours=k["gio_xl"])
        if k["kq"] != "bo_ngo" and xong_luc <= now:
            if r["trang_thai"] == "moi" and k["nhan_truoc"] and k["gio_ph"] < k["gio_xl"]:
                giao.append((gid, ai, ql or ai, tao + timedelta(hours=k["gio_ph"])))
            tt = "da_xong" if k["kq"] == "xong" else "khong_lam_duoc"
            thay_doi.append((gid, tt, ai, "" if tt == "da_xong" else k["ly_do"], xong_luc))
            dem["xong" if tt == "da_xong" else "khong_lam_duoc"] += 1
        elif k["kq"] == "bo_ngo" and k["nhan_bo_ngo"] and r["trang_thai"] == "moi" and tao + timedelta(hours=k["gio_ph"]) <= now:
            giao.append((gid, ai, ql or ai, tao + timedelta(hours=k["gio_ph"])))
            dem["da_nhan"] += 1
    td.giao_nhieu(giao)
    td.cap_nhat_nhieu(thay_doi)
    return dem


def chuan_bi_demo(now: datetime | None = None) -> dict:
    """Một nút chuẩn bị demo: xoá trạng thái cũ, nạp 14 ngày mô phỏng, rồi lấy việc HÔM NAY từ các luật (chưa gửi, để lúc demo bấm gửi)."""
    td.xoa_het_minh_hoa()
    n_ls = nap_lich_su(now)
    return {"mo_phong": n_ls, **td.dong_bo(luat.danh_sach_viec(), now or td.bay_gio())}
