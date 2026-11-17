"""Số liệu MINH HOẠ cho khối DVKH (SR bị động, SR chủ động, rời mạng, công nợ): sinh ngẫu nhiên có hạt giống rồi ghi bằng `app.dvkh.nap.nap`.

Tách khỏi `nap_so_lieu_mau.py` cho file không quá dài. Mọi tên người, mã hợp đồng, mã SR đều bịa (`cskh_NN`, `MHDV#####`). Cách dựng theo đúng hình dạng file thật
(`app/dvkh/doc_file.py`) nên các trang /dvkh/... đọc ra như đã nạp file Excel.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta

import pandas as pd

KHOI_DAU = date(2026, 9, 1)
SO_HD = 3600                                   # số hợp đồng trong "quỹ" (một hợp đồng có thể gọi nhiều lần: SR lặp)
SO_CSKH = 14
# phường / xã (tên mới, như file SR) -> (chi nhánh, KH đang hoạt động)
PHUONG = {
    "Phường An Hải": ("DNG_01", 6800), "Phường Sơn Trà": ("DNG_01", 8800), "Phường Ngũ Hành Sơn": ("DNG_01", 6900), "Phường Hòa Cường": ("DNG_01", 8200),
    "Phường Hải Châu": ("DNG_01", 9800), "Phường Cẩm Lệ": ("DNG_01", 7500), "Phường An Khê": ("DNG_01", 5200), "Phường Hòa Xuân": ("DNG_01", 5600),
    "Phường Thanh Khê": ("DNG_02", 9100), "Phường Liên Chiểu": ("DNG_02", 6400), "Phường Hòa Khánh": ("DNG_02", 7100), "Phường Hải Vân": ("DNG_02", 4300),
    "Xã Bà Nà": ("DNG_02", 800), "Xã Hòa Tiến": ("DNG_02", 1900), "Xã Hòa Vang": ("DNG_02", 3100),
}
LOAI_YC = [("Khiếu nại, phàn nàn", 0.52), ("Thắc mắc", 0.19), ("Thanh lý", 0.12), ("Tạm ngưng", 0.06), ("Khôi phục dịch vụ", 0.04), ("Chuyển địa điểm", 0.04), ("Đổi gói cước", 0.03)]
PHAN_LOAI = [("Chất lượng dịch vụ", 0.42), ("Cước phí", 0.30), ("Chính sách", 0.08), ("Chất lượng phục vụ", 0.08), ("Sản phẩm dịch vụ", 0.07), (None, 0.05)]
NGUYEN_NHAN_KN = ["Hỗ trợ nhiều lần nhưng dịch vụ không ổn định", "Chất lượng Thiết bị FPT cung cấp", "Thắc mắc về tiền cước trên hóa đơn", "Không sử dụng được dịch vụ do lỗi FTEL",
                  "Từ phía Khách hàng", "Thay đổi cước phí", "Không cung cấp đúng chính sách đã cam kết", "Thắc mắc do Nâng cấp Combo V.VIP", "Thông báo cước", "Chất lượng bảo trì"]
NGUYEN_NHAN_TL = ["Chuyển nơi ở", "Giá cước cao", "Chất lượng dịch vụ không ổn định", "Chuyển sang nhà mạng khác", "Không còn nhu cầu", "Chất lượng Thiết bị FPT cung cấp"]
KENH = [("Điện thoại", 0.28), ("Zalo", 0.22), ("AnsCall", 0.14), ("Hi FPT Chat", 0.08), ("Hi FPT", 0.08), ("Quầy giao dịch", 0.05), ("CSKH mở rộng", 0.05), ("Fpt.vn", 0.04), ("MobiX", 0.03), ("Email", 0.03)]
LIEN_HE = [("Gặp trực tiếp người sử dụng", 0.55), ("Không liên lạc được", 0.18), ("Gặp KH, KH từ chối", 0.08), ("Không gặp trực tiếp KH", 0.09), (None, 0.10)]
TU_VAN_TL = [("Khách hàng đồng ý sử dụng tiếp và không cần hỗ trợ", 0.26), ("Khách hàng không đồng ý sử dụng tiếp", 0.34), ("Khách hàng đang suy nghĩ", 0.16), (None, 0.24)]
TU_VAN_KHAC = [("Khách hàng đồng ý, không cần hỗ trợ thêm", 0.50), ("Khách hàng đồng ý, cần hỗ trợ thêm", 0.30), ("Khách hàng đang suy nghĩ", 0.08), (None, 0.12)]
DON_VI_TAO = [("Phòng dịch vụ khách hàng 1", 0.30), ("Phòng dịch vụ khách hàng 2", 0.25), ("Phòng Kinh doanh IBB", 0.15), ("Phòng triển khai bảo trì", 0.15), ("Phòng hỗ trợ khách hàng", 0.15)]
# chương trình SR chủ động -> (nhóm chương trình, trọng số)
CHUONG_TRINH = {
    "Ngưng kết nối": ("Nguy cơ rời mạng (SOS)", 0.09), "Dự đoán RM": ("Nguy cơ rời mạng (SOS)", 0.12), "Nguy cơ sang rời mạng nợ cước (CTBDV)": ("Nguy cơ rời mạng (SOS)", 0.04),
    "CSKH không PSLL vết T": ("Nhóm chất lượng dịch vụ", 0.08), "CSKH không PSLL vết T-": ("Nhóm chất lượng dịch vụ", 0.08), "CSKH có Checklist lặp": ("Nhóm chất lượng hạ tầng", 0.09),
    "Chất lượng kết nối NET": ("Nhóm chất lượng hạ tầng", 0.16), "Homewifi": ("Nhóm chất lượng hạ tầng", 0.13), "CSKH yêu câu hủy": ("Nhóm chương trình sự kiện", 0.05),
    "CSKH sau nâng gói & chuyển đổi Wifi6": ("Nhóm chương trình sự kiện", 0.07), "CSKH sau khóa vi phạm CMR Buffet": ("Nhóm chương trình sự kiện", 0.04),
    "Khôi phục dịch vụ": ("Nhóm chương trình sự kiện", 0.05),
}
TU_VAN_CD = [("Thuê bao không liên lạc được", 0.30), ("Chưa bắt máy", 0.12), ("KH đồng ý sử dụng tiếp và không cần hỗ trợ", 0.28), ("KH đồng ý sử dụng tiếp và cần hỗ trợ", 0.10),
             ("KH không đồng ý, yêu cầu thanh lý", 0.12), (None, 0.08)]
# chuỗi gốc của file thật có dạng "<loại đề xuất> - <trạng thái>" (`khai_thac.duyet_de_xuat` tách theo " - ")
DUYET_DE_XUAT = ["Miễn giảm - Đã xử lý", "Miễn giảm - Đã xử lý", "Miễn giảm - Từ chối", "Miễn giảm - Đang chờ duyệt", "Đổi câu lệnh giá - Đã xử lý", "Đổi câu lệnh giá - Từ chối",
                 "Khoá rời mạng - Đã xử lý", "Khoá rời mạng - Đang chờ duyệt", None, None]
GOI_NET = [("Giga", 0.35), ("Sky", 0.30), ("Meta", 0.2), ("Sky F1", 0.08), ("Giga Plus", 0.07)]
GOI_PAY = [("V.VIP", 0.35), ("MAXY", 0.08), ("Max", 0.07), ("VIP", 0.15), ("ZPlay", 0.05), (None, 0.30)]
GOI_CAM = [("Cloud 7 ngày", 0.2), ("Cloud 30 ngày", 0.1), (None, 0.7)]


def _chon(rng, bang):
    return rng.choices([b[0] for b in bang], [b[1] for b in bang])[0]


def _gio(rng, ngay: date, nang: float = 1.0) -> datetime:
    """Giờ phát sinh trong ngày: dồn vào giờ hành chính và đầu giờ tối."""
    h = rng.choices(range(24), [0.2] * 6 + [1] * 2 + [4, 6, 6, 4, 3, 3, 4, 5, 5, 4, 3, 3, 2, 1, 0.5, 0.3])[0]
    return datetime(ngay.year, ngay.month, ngay.day, h, rng.randint(0, 59), rng.randint(0, 59))


def _soi_nhip(rng, tc: date, nen: float, cao_diem: tuple[date, float] | None = None) -> list[tuple[date, int]]:
    """Số SR mỗi ngày: thấp vào Chủ nhật, tăng nhẹ theo thời gian, có một ngày sự cố đột biến."""
    out, ngay = [], KHOI_DAU
    while ngay <= tc:
        he = 0.45 if ngay.weekday() == 6 else 1.0
        he *= 1 + 0.18 * (ngay - KHOI_DAU).days / max(1, (tc - KHOI_DAU).days)
        if cao_diem and abs((ngay - cao_diem[0]).days) <= 1:
            he *= cao_diem[1]
        out.append((ngay, max(0, round(rng.gauss(nen * he, nen * he * 0.15)))))
        ngay += timedelta(days=1)
    return out


def _cskh(rng) -> str:
    return f"cskh_{rng.choices(range(1, SO_CSKH + 1), [1.6, 1.4, 1.3, 1.2, 1.1, 1.0, 1.0, 0.9, 0.9, 0.8, 0.8, 0.7, 0.6, 0.5])[0]:02d}"


def _hd(rng) -> str:
    """Mã hợp đồng: dồn vào đầu quỹ để một số hợp đồng gọi nhiều lần (SR lặp), phần còn lại gọi một lần."""
    return f"MHDV{int(SO_HD * rng.random() ** 1.7) + 1:05d}"


def _trang_thai_mo(rng, tuoi_ngay: int) -> bool:
    return rng.random() < max(0.035, 0.55 * math.exp(-tuoi_ngay / 3.5))


def sinh_sr_bi_dong(rng, tc: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, them, stt = [], [], 0
    phuong, trong_so = list(PHUONG), [v[1] for v in PHUONG.values()]
    for ngay, n in _soi_nhip(rng, tc, 34, (date(2026, 10, 22), 1.7)):
        for _ in range(n):
            stt += 1
            ten_phuong = rng.choices(phuong, trong_so)[0]
            loai = _chon(rng, LOAI_YC)
            tl = loai == "Thanh lý"
            tg = _gio(rng, ngay)
            tuoi = (tc - ngay).days
            la_dvkh = rng.random() < 0.78
            mo = _trang_thai_mo(rng, tuoi)
            tu_van = _chon(rng, TU_VAN_TL if tl else TU_VAN_KHAC)
            net = "Đã chấm dứt hợp đồng" if (tl and tu_van and "không đồng ý" in tu_van and rng.random() < 0.56) or rng.random() < 0.01 else "Đang hoạt động"
            xu_ly = rng.lognormvariate(math.log(14), 0.9)
            qua_han_xong = rng.random() < 0.12
            dau = tg + timedelta(minutes=rng.lognormvariate(math.log(28), 0.8))
            cuoi = None if mo else tg + timedelta(hours=xu_ly)
            tinh_trang = rng.choices(["Đang xử lý", "Chưa xử lý"], [0.65, 0.35])[0] if mo else rng.choices(["Đã xử lý", "Đã hoàn tất", "Xử lý không thành công"], [0.6, 0.36, 0.04])[0]
            phi = float(rng.choice([100000, 150000, 200000, 300000])) if loai in ("Khôi phục dịch vụ", "Tạm ngưng", "Chuyển địa điểm") else 0.0
            mien = phi * (1.12 if loai == "Khôi phục dịch vụ" and rng.random() < 0.7 else (0.4 if phi and rng.random() < 0.4 else 0.0))
            ma = f"SRBD-{ngay:%y%m%d}-{stt:05d}"
            rows.append({
                "ma_sr": ma, "chi_nhanh": PHUONG[ten_phuong][0], "quan": ten_phuong, "so_hd": _hd(rng), "loai_yc": loai,
                "phan_loai": _chon(rng, PHAN_LOAI) if loai == "Khiếu nại, phàn nàn" else None, "hinh_thuc_kn": "Khác văn bản" if loai == "Khiếu nại, phàn nàn" else None,
                "nguyen_nhan_1": rng.choice(NGUYEN_NHAN_TL if tl else NGUYEN_NHAN_KN) if loai in ("Khiếu nại, phàn nàn", "Thanh lý") else None,
                "nguyen_nhan_2": None, "nguyen_nhan_3": None, "loai_dv": "Internet", "kenh": _chon(rng, KENH), "nguon_tao": rng.choice(["Khách hàng", "Nhân viên", "Hệ thống"]),
                "tg_yc": tg, "ket_qua_lien_he": _chon(rng, LIEN_HE), "cong_cu": "Điện thoại", "tg_cn_dau": dau, "ket_qua_tu_van": None if mo and rng.random() < 0.5 else tu_van,
                "tinh_trang": tinh_trang, "phuong_an": None, "tg_cn_cuoi": cuoi, "net_tao": "Đang hoạt động", "net_hien": net,
                "pay_hien": _chon(rng, GOI_PAY), "cam_hien": None,
                "nguoi_xu_ly": (_cskh(rng) if la_dvkh else f"ktv_{rng.randint(1, 20):02d}") if not (mo and tinh_trang == "Chưa xử lý" and rng.random() < 0.4) else None,
                "don_vi_xu_ly": "Phòng dịch vụ khách hàng 1" if la_dvkh else rng.choice(["Phòng triển khai bảo trì 1", "Phòng hỗ trợ khách hàng"]),
                "nhan_su_au": _cskh(rng), "acc_tao": rng.choice(["khách hàng", "khách hàng", "daisy_bot", f"cskh_{rng.randint(1, SO_CSKH):02d}"]),
                "phi": phi, "mien_giam_phi": mien, "so_lan_cap_nhat": rng.choice([1, 1, 2, 3]),
                "qua_han": ("Quá hạn đang xử lý" if tuoi >= 2 else "Đang trong hạn") if mo else ("Hoàn tất quá hạn" if qua_han_xong else "Hoàn tất trong hạn")})
            them.append({"ma_sr": ma, "goi_net": _chon(rng, GOI_NET), "goi_pay": _chon(rng, GOI_PAY), "goi_cam": _chon(rng, GOI_CAM),
                         "don_vi_tao": _chon(rng, DON_VI_TAO), "duyet_de_xuat": rng.choice(DUYET_DE_XUAT),
                         "trung": rng.choice([0, 0, 0, 1, 2])})
    df = pd.DataFrame(rows)
    for c in ("tg_yc", "tg_cn_dau", "tg_cn_cuoi"):
        df[c] = pd.to_datetime(df[c])
    return df, pd.DataFrame(them)


def sinh_sr_chu_dong(rng, tc: date, bd: pd.DataFrame) -> pd.DataFrame:
    rows, stt = [], 0
    ten_ct, trong_so = list(CHUONG_TRINH), [v[1] for v in CHUONG_TRINH.values()]
    phuong, tl = list(PHUONG), [v[1] for v in PHUONG.values()]
    loai_bd = bd.groupby("so_hd")["loai_yc"].first().to_dict()
    for ngay, n in _soi_nhip(rng, tc, 40):
        for _ in range(n):
            stt += 1
            ct = rng.choices(ten_ct, trong_so)[0]
            tuoi = (tc - ngay).days
            mo = _trang_thai_mo(rng, tuoi)
            tg = _gio(rng, ngay)
            tu_dong = rng.random() < 0.12
            tinh_trang = (rng.choices(["Chưa xử lý", "Đang xử lý", "Chưa phân công"], [0.5, 0.38, 0.12])[0] if mo
                          else ("Đóng tự động bởi hệ thống" if tu_dong and rng.random() < 0.5 else rng.choices(["Đã xử lý", "Đã hoàn tất", "Xử lý không thành công"], [0.6, 0.36, 0.04])[0]))
            chua_lam = tinh_trang in ("Chưa xử lý", "Chưa phân công")
            nguoi = None if tinh_trang == "Chưa phân công" else ("autocall" if tu_dong else _cskh(rng))
            lien_he = None if chua_lam else _chon(rng, LIEN_HE)
            ten_phuong = rng.choices(phuong, tl)[0]
            ma_hd = _hd(rng)
            rows.append({
                "ma_sr": f"SRCD-{ngay:%y%m%d}-{stt:05d}", "chi_nhanh": PHUONG[ten_phuong][0], "quan": ten_phuong, "so_hd": ma_hd, "nhom_ct": CHUONG_TRINH[ct][0],
                "chuong_trinh": ct, "tinh_trang_dau": "Chưa xử lý", "do_uu_tien": rng.choices(["Rất cao", "Khá cao", "Thấp"], [0.15, 0.5, 0.35])[0],
                "diem_rm": float(rng.randint(560, 995)) if ct in ("Dự đoán RM", "Ngưng kết nối") else -1.0, "uu_tien_cs": rng.choice(["1", "2", "3"]),
                "nguon_pp": rng.choice(["AUTO", "MANUAL"]), "tg_do": tg, "tg_phan_cong": None if tinh_trang == "Chưa phân công" else tg + timedelta(hours=rng.uniform(0.2, 9)),
                "ket_qua_lien_he": lien_he, "cong_cu": None if chua_lam else "Điện thoại",
                "tg_cn_dau": None if chua_lam else tg + timedelta(hours=rng.lognormvariate(math.log(5), 0.8)),
                "ket_qua_tu_van": None if chua_lam else _chon(rng, TU_VAN_CD),
                "tinh_trang": tinh_trang, "phuong_an": None, "tg_cn_cuoi": None if mo else tg + timedelta(hours=rng.lognormvariate(math.log(20), 0.7)),
                "nguoi_xu_ly": nguoi, "nhan_su_au": nguoi if nguoi and nguoi != "autocall" else _cskh(rng), "so_lan_cs": 0 if chua_lam else rng.choice([1, 1, 1, 2, 3]),
                "ly_do_khong_lh": "Khách đã được CSKH gọi" if lien_he is None and not chua_lam else None, "ly_do_mat_kn": rng.choice(["Mất điện", "Hỏng thiết bị", None, None]) if ct == "Ngưng kết nối" else None,
                "qua_han": "Chưa xử lý" if chua_lam else (("Quá hạn đang xử lý" if tuoi >= 3 else "Đang trong hạn") if mo else ("Hoàn tất quá hạn" if rng.random() < 0.1 else "Hoàn tất trong hạn")),
                "sr_bd_trung": loai_bd.get(ma_hd)})
    df = pd.DataFrame(rows)
    for c in ("tg_do", "tg_phan_cong", "tg_cn_dau", "tg_cn_cuoi"):
        df[c] = pd.to_datetime(df[c])
    return df


# ---------------------------------------------------------------- rời mạng, công nợ
def _roi_mang_ngay(rng, ngay: date, he_so: dict[str, float]) -> list[dict]:
    """Ảnh chụp rời mạng LUỸ KẾ THÁNG tại `ngay`: theo phường / xã rồi cộng lên hai phòng DNG-01, DNG-02 và cả Đà Nẵng."""
    tiep = ngay.day / 30
    quan = []
    for p, (cn, active) in PHUONG.items():
        ten = "Phuong " if p.startswith("Phường") else "Xa "
        ten += _bo_dau(p.split(" ", 1)[1])
        k = he_so[p]
        roi = round(active * 0.0082 * tiep * k)
        gross = round(active * 0.0148 * tiep * rng.uniform(0.9, 1.1))
        quan.append(_dong_roi(ten, cn, active, roi, gross, "quan"))
    out = list(quan)
    for ten, cn in (("DNG-01", "DNG_01"), ("DNG-02", "DNG_02"), ("05.Da Nang", None)):
        sub = [q for q in quan if cn is None or q["_cn"] == cn]
        out.append(_dong_roi(ten, cn, sum(q["kh_active"] for q in sub), sum(q["kh_roi_mang"] for q in sub), sum(q["gross_pttb"] for q in sub), "phong"))
    return [{k: v for k, v in d.items() if k != "_cn"} for d in out]


def _dong_roi(ten, cn, active, roi, gross, cap) -> dict:
    net = gross - roi
    return {"_cn": cn, "cap": cap, "ten": ten, "kh_active": float(active), "kh_dau_ky": float(active - net), "gross_pttb": float(gross),
            "huy_tsd": float(round(roi * 0.06)), "huy_ssd": float(round(roi * 0.46)), "ctbdv": float(round(roi * 0.28)), "ctbdv_khoi_phuc": float(round(roi * 0.05)),
            "hssd_khoi_phuc": float(round(roi * 0.03)), "ctbdv_chuyen_hssd": float(round(roi * 0.02)), "cho_thanh_ly": float(round(roi * 0.4)),
            "cho_tl_kpdv": float(round(roi * 0.2)), "cho_tl_hssd": float(round(roi * 0.2)), "ctbdv_du_kien": float(round(roi * 0.25)), "kh_roi_mang": float(roi),
            "ty_le_roi_active": roi * 100 / active, "ty_le_roi_gross": roi * 100 / gross if gross else None, "net_pttb": float(net),
            "ty_le_giu": 100 - roi * 100 / active, "ty_le_tang": net * 100 / (active - net) if active - net else None}


def _bo_dau(s: str) -> str:
    from app.dvkh.doc_file import bo_dau
    return " ".join(w.capitalize() for w in bo_dau(s).split())


QUAN_CU_CHUOI = {"DNG 1": ["Q.Hai Chau", "Q.Son Tra", "Q.Ngu Hanh Son", "Q.Cam Le"], "DNG 2": ["Q.Thanh Khe", "Q.Lien Chieu", "Huyen Hoa Vang"]}


def _duong_thu(rng, k: float, lech: float) -> list[float]:
    """Tỷ lệ thu luỹ kế (0..1) theo ngày 1..n trong một kỳ thu: nhanh những ngày đầu, chậm dần về cuối; mỗi đơn vị lệch một chút."""
    out, cu = [], 0.0
    for n in range(1, 32):
        v = 0.93 * (1 - math.exp(-(n + 2) / 8.0)) * k + lech + rng.gauss(0, 0.002)
        cu = max(cu, min(v, 0.985))
        out.append(cu)
    return out


def sinh_cong_no(rng, tc: date) -> tuple[list[dict], list[dict]]:
    """(chuỗi thu theo ngày, ảnh chụp công nợ). Hoá đơn tháng 9 thu trong tháng 10 (đủ 31 ngày), hoá đơn tháng 10 thu trong tháng 11 (tới ngày tham chiếu)."""
    chuoi = []
    don_vi = [("phong", "DNG1"), ("phong", "DNG2"), ("phong", "To tal DNG CN 30"), ("quan", "DNG"), ("quan", "DNG 1"), ("quan", "DNG 2")] + [("quan", q) for qs in QUAN_CU_CHUOI.values() for q in qs]
    lech_dv = {dv: rng.uniform(-0.03, 0.03) for dv in don_vi}
    for ky, dau, he in (("2026-08", date(2026, 9, 1), 1.0), ("2026-09", date(2026, 10, 1), 1.0), ("2026-10", date(2026, 11, 1), 0.975)):
        so_ngay = ((date(dau.year + dau.month // 12, dau.month % 12 + 1, 1) - dau).days)
        for cap, ten in don_vi:
            duong = _duong_thu(rng, he, lech_dv[(cap, ten)])
            for n in range(1, so_ngay + 1):
                ngay = dau + timedelta(days=n - 1)
                if ngay > tc:
                    break
                bill = duong[n - 1]
                chuoi.append({"ky_no": ky, "ngay": ngay, "cap": cap, "ten": ten, "ty_le_dt": min(0.99, bill * rng.uniform(0.97, 0.995)), "ty_le_bill": bill})
    chot = []
    tong = {"hd": 0, "tt": 0, "da": 0, "tt_da": 0}
    for p, (cn, active) in PHUONG.items():
        so_hd = round(active * rng.uniform(0.9, 1.0))
        tong_tien = so_hd * rng.uniform(185000, 215000)
        ty = rng.uniform(0.80, 0.90)
        da, tt_da = round(so_hd * ty), tong_tien * ty * rng.uniform(1.0, 1.015)
        chot.append(_dong_chot("quan", cn.replace("_0", "_"), "Phuong " + _bo_dau(p.split(" ", 1)[1]) if p.startswith("Phường") else "Xa " + _bo_dau(p.split(" ", 1)[1]), so_hd, tong_tien, da, tt_da))
        tong["hd"] += so_hd
        tong["tt"] += tong_tien
        tong["da"] += da
        tong["tt_da"] += tt_da
    for cn in ("DNG_1", "DNG_2"):
        sub = [c for c in chot if c["cap"] == "quan" and c["chi_nhanh"] == cn]
        chot.append(_dong_chot("phong", cn, cn, sum(c["so_hd"] for c in sub), sum(c["tong_tien"] for c in sub), sum(c["hd_da_tt"] for c in sub), sum(c["tt_da_tt"] for c in sub)))
    chot.append(_dong_chot("phong", "", "Đà Nẵng", tong["hd"], tong["tt"], tong["da"], tong["tt_da"]))
    return chuoi, chot


def _dong_chot(cap, chi_nhanh, ten, so_hd, tong_tien, da, tt_da) -> dict:
    tt_da = min(tt_da, tong_tien)
    return {"cap": cap, "chi_nhanh": chi_nhanh, "ten": ten, "ky_no": "2026-10", "so_hd": float(so_hd), "tong_tien": float(round(tong_tien)), "hd_da_tt": float(da),
            "tt_da_tt": float(round(tt_da)), "hd_con_no": float(so_hd - da), "tt_con_no": float(round(tong_tien - tt_da)),
            "ty_le_dt": tt_da * 100 / tong_tien, "ty_le_bill": da * 100 / so_hd}


# ---------------------------------------------------------------- ghi vào database
def nap_dvkh_mau(rng, tc: date) -> dict:
    """Sinh rồi ghi bằng `dvkh.nap.nap`. Các ảnh chụp rời mạng cuối các kỳ trước ghi trước (không kèm SR), ảnh chụp mới nhất ghi sau cùng kèm toàn bộ SR."""
    from app.dvkh import nap

    sr_bd, them = sinh_sr_bi_dong(rng, tc)
    sr_cd = sinh_sr_chu_dong(rng, tc, sr_bd)
    chuoi, chot = sinh_cong_no(rng, tc)
    he_so = {p: rng.uniform(0.7, 1.45) for p in PHUONG}
    quy_hd = sorted({h for h in set(sr_bd["so_hd"]) | set(sr_cd["so_hd"])})
    ych = sorted(rng.sample(quy_hd, 130))
    no = sorted(rng.sample(quy_hd, 190))
    so_kh_au = [{"acc": f"cskh_{i:02d}", "so_kh": int(rng.uniform(3200, 6800))} for i in range(1, SO_CSKH + 1)]
    trong = pd.DataFrame()
    for ngay in (date(2026, 9, 30), date(2026, 10, 14), date(2026, 10, 31), date(2026, 11, 7)):
        nap.nap({"sr_bd": trong, "sr_cd": trong, "roi_mang": _roi_mang_ngay(rng, ngay, he_so), "chuoi_cong_no": [], "chot_cong_no": [], "ych": [], "no_cuoc": []},
                ngay, f"du_lieu_mau_{ngay:%Y%m%d}", "demo")
    kq = nap.nap({"sr_bd": sr_bd, "sr_bd_them": them, "sr_cd": sr_cd, "roi_mang": _roi_mang_ngay(rng, tc, he_so), "chuoi_cong_no": chuoi, "chot_cong_no": chot,
                  "ych": ych, "no_cuoc": no, "so_kh_au": so_kh_au}, tc, f"du_lieu_mau_{tc:%Y%m%d}", "demo")
    return kq
