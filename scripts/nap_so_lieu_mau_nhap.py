"""Số liệu MINH HOẠ cho các trang nhập liệu và công cụ của khối Kinh doanh: Báo cáo ngày + Theo dõi Online (IBB7 và nhóm Phòng Online), Nhập tồn (IBB7), Ads IBB7, Danh bạ.

Tách khỏi `nap_so_lieu_mau.py` cho file không quá dài. Chạy SAU khi đã có hợp đồng (fact_internet) và danh mục nhân sự, vì số bán / online từng người lấy từ đó.
Đi qua đường ghi có sẵn của app (`bao_cao_ngay.luu`, `nhap_ton.luu`, `ads.nhan_chi_tieu`...); riêng phiếu Theo dõi Online và Danh bạ ghi bằng model vì cần
đặt giờ bấm Đã online / bản chụp nhiều người trong quá khứ mà đường ghi của app không cho. Tên người, acc, mã hợp đồng, email, số điện thoại đều bịa.
"""
from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta

NGUOI = "demo"
PHONG_BC = "IBB7"
KHUNG = [("08-10", 10 * 60), ("10-12", 12 * 60), ("1330-1530", 15 * 60 + 30), ("1530-1730", 17 * 60 + 30), ("sau", 20 * 60)]
NHAN_KHUNG = {"08-10": "08h–10h", "10-12": "10h–12h", "1330-1530": "13h30–15h30", "1530-1730": "15h30–17h30", "sau": "Sau 17h30", "chua": "Chưa hẹn giờ"}
GHI_CHU_NGAY = ["Khách hẹn lắp sau giờ làm", "Đã gọi xác nhận, khách có nhà", "Chờ kỹ thuật phân tuyến", "Khách đổi địa chỉ lắp", "Cần mang thêm dây quang", "Khách nhờ gọi lại buổi chiều"]
GHI_CHU_TON = ["Khách đi công tác, hẹn về mới lắp", "Chờ chủ nhà ký giấy", "Đã gọi 2 lần chưa bắt máy", "Chờ hạ tầng khu vực", "Khách muốn đổi gói trước khi lắp", "Hẹn kỹ thuật qua khảo sát",
                "Khách đang so giá với nhà mạng khác", "Tòa nhà chưa cho đi dây", "Đã gửi lại báo giá qua Zalo"]
TRONG_TAM = ["Chốt các ca hẹn sáng, không để dồn sang chiều.", "Gọi lại toàn bộ KHTN trên 3 ngày chưa chốt.", "Ưu tiên ca đã hẹn kỹ thuật, bán kèm V.VIP khi tư vấn."]
NHAN_DINH = ["Nhịp bán đều, cuối tuần giảm nhẹ; PTTB luỹ kế bám sát mục tiêu.", "Số hợp đồng chờ online còn nhiều, cần đẩy kỹ thuật xếp lịch sớm.", "KHTN tăng nhưng tỷ lệ chốt thấp, cần rà lại câu hỏi tư vấn."]
THONG_DIEP = ["Cả phòng giữ nhịp, mỗi người chốt thêm ít nhất một ca trong ngày.", "Báo cáo đủ và đúng giờ để trưởng phòng theo dõi kịp."]


def _gio_vn_sang_utc(ngay: date, phut: int) -> datetime:
    return datetime(ngay.year, ngay.month, ngay.day) + timedelta(minutes=phut) - timedelta(hours=7)


# ---------------------------------------------------------------- dữ liệu nền đọc từ database
def _nguoi(phong_thuc: list[str], loc: set[str] | None, tc: date) -> list[str]:
    """acc_norm nhân sự đang làm của phòng (không trưởng phòng), đúng danh sách Báo cáo ngày đang dùng."""
    from app import bao_cao_ngay as bc
    df = bc._nhan_su_dang_lam(phong_thuc, date(tc.year, tc.month, 1), tc)
    return [a for a in dict.fromkeys(df.acc_norm) if loc is None or a in loc]


def _dem_theo_ngay(accs: list[str], tu: date, den: date) -> dict[tuple[str, date], dict]:
    """{(acc_norm, ngày): {"ban": số hợp đồng tạo mới, "onl": số online}} từ file Internet mẫu."""
    import pandas as pd
    from sqlalchemy import text

    from app.db import engine
    kq: dict[tuple[str, date], dict] = {}
    cho = ", ".join(f":a{i}" for i in range(len(accs)))
    ma = {f"a{i}": a for i, a in enumerate(accs)}
    for cot, khoa in (("ngay_tao_hd", "ban"), ("ngay_online", "onl")):
        df = pd.read_sql_query(text(f"SELECT acc_norm, {cot} AS d, COUNT(*) AS n FROM fact_internet WHERE acc_norm IN ({cho}) AND {cot} >= :tu AND {cot} <= :den GROUP BY acc_norm, {cot}"),
                               engine, params={**ma, "tu": tu.isoformat(), "den": den.isoformat()})
        for a, d, n in zip(df.acc_norm, pd.to_datetime(df.d).dt.date, df.n):
            kq.setdefault((a, d), {"ban": 0, "onl": 0})[khoa] = int(n)
    return kq


# ---------------------------------------------------------------- Báo cáo ngày
def nap_bao_cao_ngay(rng: random.Random, tc: date, hom: date) -> int:
    """Báo cáo của hai nhóm (IBB7 và Phòng Online) từ 20 ngày trước ngày tham chiếu tới hôm nay (tối đa 7 ngày nhập trước như app cho phép).
    Ngày đã có số thì mọi ô đầy đủ; ngày chưa có số (nhập trước, hôm nay sau ngày tham chiếu) chỉ có mục tiêu, KHTN, dự kiến online."""
    from app import bao_cao_ngay as bc
    from app import phong_online as po
    n = 0
    cuoi = max(tc + timedelta(days=1), min(hom, tc + timedelta(days=7)))
    ngay_ds = [tc - timedelta(days=k) for k in range(20, -1, -1)] + [tc + timedelta(days=k) for k in range(1, (cuoi - tc).days + 1)]
    nhom = [([PHONG_BC], [PHONG_BC], None, False), ([bc.PHONG_ONLINE], [po.phong_goc()], set(po.acc_nhom()), True)]
    for phong, thuc, loc, la_online in nhom:
        accs = list(bc.bang(phong, tc).acc_norm)                  # đúng những dòng bảng đang hiện (có cả người chỉ có số bán như trưởng phòng)
        dem = _dem_theo_ngay(accs, ngay_ds[0], tc)
        ten_mt = {a: rng.randint(14, 24) for a in accs}
        for thang in ("2026-10", "2026-11"):
            for a in accs:
                bc.dat_muc_tieu(thang, "NHAN_VIEN", a, "internet", ten_mt[a] if thang == "2026-10" else ten_mt[a] + rng.randint(0, 4), NGUOI)
        for d in ngay_ds:
            co_so = d <= tc
            for a in accs:
                if rng.random() < 0.07 and d != tc:
                    continue                                          # có người quên báo cáo vài ngày
                so = dem.get((a, d), {"ban": 0, "onl": 0})
                truong = {"muc_tieu": rng.choice([1, 2, 2, 3]), "khtn": rng.randint(6, 36)}
                if rng.random() < 0.2:
                    truong["ghi_chu"] = rng.choice(GHI_CHU_NGAY)
                if d <= hom:                                         # ngày đã qua / hôm nay: số thực hiện sale tự gõ (sau ngày tham chiếu chưa có file nên gõ số nhỏ)
                    truong["da_ban"] = so["ban"] if co_so else rng.choice([0, 1, 1, 2])
                if not la_online:                                    # ONL sáng / chiều / Đã online: sale gõ tay ở IBB7, còn nhóm Online tự đếm từ ca (không gõ được)
                    truong.update(onl_sang=rng.choice([0, 1, 1, 2]), onl_chieu=rng.choice([0, 1, 1, 2]))
                    if d <= hom:
                        truong["da_online"] = so["onl"] if co_so else rng.choice([0, 1, 1, 2])
                bc.luu(a, truong, phong, NGUOI, d)
                n += 1
        if not la_online:
            for k, d in enumerate([tc - timedelta(days=2), tc - timedelta(days=1), tc, ngay_ds[-1]]):
                bc.luu_chu(PHONG_BC, {"trong_tam": TRONG_TAM[k % 3], "nhan_dinh": NHAN_DINH[k % 3], "thong_diep": THONG_DIEP[k % 2]}, NGUOI, d)
    return n


# ---------------------------------------------------------------- Theo dõi Online (phiếu ca)
def _phieu(rng, d: date, phong_code: str, ma: str, acc: str, tt: str, hom: date, tre: bool):
    from app.models import OnlineCa
    khung, han = rng.choices(KHUNG, [3, 3, 3, 3, 1])[0]
    ls = [{"luc": f"{d:%Y-%m-%d}T07:40", "ai": NGUOI, "viec": f"Tạo ca, khung {NHAN_KHUNG[khung]}"}]
    luc = None
    if tt == "da_online":
        phut = han + rng.randint(40, 170) if tre else han - rng.randint(10, 110)
        phut = min(max(phut, 8 * 60 + 5), 23 * 60 + 30)
        luc = _gio_vn_sang_utc(d, phut)
        ls.append({"luc": f"{d:%Y-%m-%d}T{phut // 60:02d}:{phut % 60:02d}", "ai": NGUOI, "viec": "Dự kiến → Đã online"})
    elif tt == "dang_lam":
        ls.append({"luc": f"{d:%Y-%m-%d}T09:10", "ai": NGUOI, "viec": "Dự kiến → Đang triển khai"})
    bay_gio = _gio_vn_sang_utc(d, 7 * 60 + 40)
    return OnlineCa(ngay=d, phong_code=phong_code, ma_hd=ma, acc_norm=acc, khung=khung, khung_dau=khung, trang_thai=tt, online_luc=luc,
                    ghi_chu=rng.choice(GHI_CHU_NGAY) if rng.random() < 0.25 else None, lich_su=json.dumps(ls, ensure_ascii=False),
                    tao_luc=bay_gio, tao_boi=NGUOI, cap_nhat_luc=luc or bay_gio, cap_nhat_boi=NGUOI)


def nap_online_ca(rng: random.Random, tc: date, hom: date) -> int:
    """Phiếu ca của 11 ngày tới ngày tham chiếu cho hai nhóm: mỗi hợp đồng online trong ngày là một ca (phần lớn lên đúng hẹn, vài ca muộn), thêm vài ca chưa lên;
    hôm nay (sau ngày tham chiếu) có ca dự kiến / đang triển khai để mục này không trống."""
    import pandas as pd
    from sqlalchemy import text

    from app import bao_cao_ngay as bc
    from app import phong_online as po
    from app.db import engine, session_scope
    n = 0
    nhom = [(PHONG_BC, [PHONG_BC], None), (bc.PHONG_ONLINE, [po.phong_goc()], set(po.acc_nhom()))]
    with session_scope() as s:
        for ma_phong, thuc, loc in nhom:
            accs = _nguoi(thuc, loc, tc)
            cho = ", ".join(f":a{i}" for i in range(len(accs)))
            tham = {f"a{i}": a for i, a in enumerate(accs)}
            hd = pd.read_sql_query(text(f"SELECT hop_dong, acc_norm, ngay_tao_hd, ngay_online FROM fact_internet WHERE acc_norm IN ({cho}) AND ngay_tao_hd >= :tu ORDER BY ngay_tao_hd"),
                                   engine, params={**tham, "tu": (tc - timedelta(days=12)).isoformat()})
            hd["ngay_tao_hd"] = pd.to_datetime(hd.ngay_tao_hd).dt.date
            hd["ngay_online"] = [d.date() if pd.notna(d) else None for d in pd.to_datetime(hd.ngay_online)]
            da = set()
            for r in hd.itertuples():
                if r.ngay_online and tc - timedelta(days=10) <= r.ngay_online <= tc:
                    tt = "da_online"
                    d, tre = r.ngay_online, rng.random() < 0.22
                elif not r.ngay_online and r.ngay_tao_hd >= tc - timedelta(days=6) and rng.random() < 0.7:
                    d, tt, tre = r.ngay_tao_hd + timedelta(days=1), "du_kien", False       # ca hẹn mà chưa lên (tồn)
                else:
                    continue
                if d > tc or (d, r.hop_dong) in da:
                    continue
                da.add((d, r.hop_dong))
                s.add(_phieu(rng, d, ma_phong, r.hop_dong, r.acc_norm, tt, hom, tre))
                n += 1
            if hom > tc:                                                  # hôm nay chưa có file: vài ca đang chờ để mục Theo dõi Online có nội dung
                gan = hd[hd.ngay_tao_hd >= tc - timedelta(days=4)].head(7)
                for r, tt in zip(gan.itertuples(), ["da_online", "da_online", "dang_lam", "dang_lam", "du_kien", "du_kien", "du_kien"]):
                    if (hom, r.hop_dong) not in da:
                        s.add(_phieu(rng, hom, ma_phong, r.hop_dong, r.acc_norm, tt, hom, False))
                        n += 1
    return n


# ---------------------------------------------------------------- Nhập tồn (IBB7)
def nap_nhap_ton(rng: random.Random, hom: date) -> int:
    """Ghi tình trạng cho các hợp đồng tồn của IBB7: đủ mọi nhóm cảnh báo (đỏ quá hạn, vàng hôm nay, hẹn sắp tới, đã triển khai, huỷ, KH suy nghĩ) và vài ca chưa cập nhật."""
    from app import nhap_ton as nt
    ton = nt.danh_sach([PHONG_BC])
    if ton.empty:
        return 0
    pa = nt.cau_hinh()["phuong_an"]
    kieu = [("hen", -2, 0), ("hen", -1, 0), ("hen", 0, 0), ("hen", 1, 0), ("hen", 2, 0), ("tra_ve", -3, 0), ("tra_ve", -1, 0), ("tra_ve", 0, 0), ("hen", 3, 3),
            ("hen", 1, 1), (None, 0, 0), ("hen", 2, 2), ("tra_ve", 1, 3), ("hen", 4, 0), (None, 0, 0), ("hen", -4, 0), ("hen", 0, 0), ("tra_ve", -2, 0), ("hen", 5, 0)]
    n = 0
    for i, hd in enumerate(ton.hop_dong):
        loai, lech, chon_pa = kieu[i % len(kieu)]
        if loai is None and i % 3 == 0:
            continue                                                  # chưa cập nhật gì
        truong = {"ghi_chu": rng.choice(GHI_CHU_TON), "phuong_an": pa[chon_pa % len(pa)] if pa else None}
        if loai:
            truong.update(loai_moc=loai, ngay_moc=(hom + timedelta(days=lech)).isoformat())
        nt.luu(hd, truong, [PHONG_BC], NGUOI)
        n += 1
    return n


# ---------------------------------------------------------------- Ads IBB7
def nap_ads(rng: random.Random, tc: date) -> dict:
    """10 fanpage (8 chia cho sale IBB7, 1 nuôi, 1 tài khoản công ty): chi tiêu USD + tin nhắn từng camp từng ngày (tới ngày liền trước ngày tham chiếu, đúng như chi tiêu thật về trễ 1 ngày),
    số điện thoại (lead) và PTTB mỗi ngày, tỷ giá hai tháng, phân công sale chạy page.
    Phải có ít nhất một phân công đã kết thúc (có `den_ngay`): nếu mọi phân công đều đang mở thì cột đó toàn rỗng, pandas đọc thành kiểu ngày giờ và `ads.theo_page` lỗi khi so với một ngày."""
    from app import ads

    sale = [(f"A. Demo {i}", f"DNG.demo7{i:02d}") for i in range(1, 7)]
    for ten, acc in sale:
        ads.them_sale(ten, acc, NGUOI)
    trang = [(f"DEMO PAGE {i:02d}", rng.uniform(0.7, 1.5), rng.uniform(0.6, 1.6)) for i in range(1, 9)] + [("DEMO PAGE NUÔI", 0.4, 1.0), ("TRUNG LẬP DEMO", 0.9, 1.2)]
    dau, cuoi = date(2026, 10, 1), tc - timedelta(days=1)
    chi, lead = [], []
    d = dau
    while d <= tc:
        for ten, he, chat in trang:                                # `chat`: mỗi page một mức đổi tin nhắn thành số điện thoại / PTTB, để có page tốt và page kém
            he_ngay = (0.8 if d.weekday() in (5, 6) else 1.0) * (1 + 0.12 * (d - dau).days / 45)
            tong = 0.0
            for camp, ty in (("Camp Internet", 0.65), ("Camp Camera", 0.35)):
                tien = round(rng.uniform(12, 42) * he * he_ngay * ty * 1.4, 2)
                tong += tien
                if d <= cuoi:
                    chi.append({"page": ten, "camp": camp, "ngay": d.isoformat(), "chi_tieu": tien, "tin_nhan": int(tien * rng.uniform(1.2, 3.8)), "tinh_trang": "Đang chạy"})
            sdt = int(tong * rng.uniform(0.45, 0.9) * chat)
            if sdt:
                lead.append({"page": ten, "ngay": d.isoformat(), "lead": sdt, "pttb": round(sdt * rng.uniform(0.1, 0.3) * chat)})
        d += timedelta(days=1)
    kq = {"chi_tieu": ads.nhan_chi_tieu(chi, nguon="import", nguoi=NGUOI)["moi"], "lead": ads.nhan_lead(lead, nguon="import", nguoi=NGUOI)["ghi"]}
    for thang in ("2026-10", "2026-11"):
        ads.luu_thang(thang, 26394.0 if thang == "2026-10" else 26410.0, NGUOI)
    pages = ads.ds_page()
    id_theo_ma = dict(zip(pages.ma, pages.id))
    for i, (ten, _, _) in enumerate(trang):
        if "TRUNG LẬP" in ten:
            continue
        if "NUÔI" in ten:
            ads.sua_page(int(id_theo_ma[ads.chuan_ma(ten)]), ten, None, "Đang nuôi", NGUOI)
            continue
        a, b = sale[i % len(sale)][0], sale[(i + 2) % len(sale)][0]
        ma = int(id_theo_ma[ads.chuan_ma(ten)])
        if i % 3 == 0:                                                   # đổi người chạy giữa tháng (A chạy tới 14/10, B từ 15/10); cũng để cột den_ngay có ngày (xem ghi chú dưới)
            ads.them_pic(ma, [a], dau, date(2026, 10, 14), NGUOI)
            ads.them_pic(ma, [b], date(2026, 10, 15), None, NGUOI)
        else:
            ads.them_pic(ma, [a] if i % 3 == 1 else [a, b], dau, None, NGUOI)
    return kq


# ---------------------------------------------------------------- Danh bạ (Soạn email + Danh bạ)
HO = ["Nguyễn", "Trần", "Lê", "Phạm", "Huỳnh", "Võ", "Đặng", "Bùi", "Đỗ", "Hồ", "Ngô", "Dương", "Lý"]
DEM = ["Văn", "Thị", "Minh", "Quốc", "Hoài", "Ngọc", "Thanh", "Anh", "Đức", "Gia"]
TEN = ["An", "Bình", "Cường", "Dũng", "Giang", "Hải", "Hiếu", "Hùng", "Khoa", "Lan", "Linh", "Long", "Mai", "Nam", "Phúc", "Quân", "Sơn", "Tâm", "Thảo", "Trang", "Tuấn", "Vy"]
# (chi nhánh, sheet khu vực, nguồn): file PNC là bản mới (Đà Nẵng vào Nam), TIN là bản cũ (Đà Nẵng ra Bắc); Đà Nẵng có ở cả hai để thấy gộp trùng
CHI_NHANH = [("Đà Nẵng", "Tây Nguyên - Miền Trung", "PNC"), ("Quảng Nam", "Tây Nguyên - Miền Trung", "PNC"), ("Huế", "Tây Nguyên - Miền Trung", "PNC"), ("Quảng Ngãi", "Tây Nguyên - Miền Trung", "PNC"),
             ("Khánh Hòa", "Tây Nguyên - Miền Trung", "PNC"), ("Sài Gòn 1", "Đông Nam Bộ", "PNC"), ("Cần Thơ", "Tây Nam Bộ", "PNC"), ("BGĐ", "Ban giám đốc", "PNC"),
             ("Quảng Bình", "Tây Nguyên - Miền Trung", "TIN"), ("Hà Nội 1", "CN HNX", "TIN"), ("Hải Phòng", "Đông Bắc Bộ", "TIN"), ("Nghệ An", "Tây Bắc Bộ", "TIN")]
CHUC_VU = [("Giám đốc Chi nhánh", 1, ""), ("Phó Giám đốc Chi nhánh", 2, ""), ("Trưởng phòng Kỹ thuật", 1, ""), ("Phó phòng Kỹ thuật", 1, ""), ("Trưởng phòng KT Hạ Tầng", 1, ""),
           ("Kế toán trưởng", 1, ""), ("Trưởng phòng DVKH", 1, ""), ("Chuyên viên Hành chính nhân sự", 1, "")]
KHU_DOI = ["Sơn Trà", "Hải Châu", "Thanh Khê", "Liên Chiểu", "Ngũ Hành Sơn", "Cẩm Lệ"]


def _bo_dau(s: str) -> str:
    from app.dvkh.doc_file import bo_dau
    return bo_dau(s).replace(" ", "").lower()


def nap_danh_ba(rng: random.Random) -> int:
    """~100 người bịa của 12 chi nhánh (đủ nhóm: giám đốc, phó giám đốc, kỹ thuật, hạ tầng, đội trưởng theo khu vực, kế toán, DVKH, hành chính nhân sự), email `@example.com`,
    số điện thoại giả 0900...; vài người thêm tay. Đà Nẵng có ở cả hai file nên đội trưởng và vài người trùng để thấy gộp trùng."""
    from app import danh_ba
    from app.db import session_scope
    from app.models import DanhBa
    danh_ba.dam_bao_bang()
    bay_gio = datetime.utcnow()
    rows, da_co = [], set()

    def them(nguon, don_vi, khu_vuc, chuc, ghi_chu=None, ten=None):
        ten = ten or f"{rng.choice(HO)} {rng.choice(DEM)} {rng.choice(TEN)}"
        so = len(rows) + 1
        rows.append({"nguon": nguon, "ho_ten": ten, "chuc_vu": chuc, "email": f"{_bo_dau(ten.split()[-1])}{_bo_dau(ten.split()[0])[:2]}{so:03d}@example.com", "ext": f"{200 + so}",
                     "di_dong": f"090000{so:04d}", "don_vi": don_vi, "khu_vuc": khu_vuc, "ghi_chu": ghi_chu, "cap_nhat_luc": bay_gio, "cap_nhat_boi": NGUOI})
        da_co.add((nguon, ten, don_vi))
        return ten

    for don_vi, khu_vuc, nguon in CHI_NHANH:
        for chuc, so_nguoi, ghi_chu in CHUC_VU:
            if don_vi == "BGĐ" and not chuc.startswith(("Giám", "Phó Giám")):
                continue
            for _ in range(so_nguoi + (1 if chuc.startswith("Trưởng phòng Kỹ") and don_vi == "Đà Nẵng" else 0)):
                them(nguon, don_vi, khu_vuc, chuc, ghi_chu or None)
        if don_vi in ("Đà Nẵng", "Quảng Nam", "Huế"):
            for khu in (KHU_DOI if don_vi == "Đà Nẵng" else KHU_DOI[:3]):
                them(nguon, don_vi, khu_vuc, "Đội trưởng kỹ thuật", f"Block {khu}")
    gd = next(r for r in rows if r["don_vi"] == "Đà Nẵng" and r["chuc_vu"].startswith("Giám đốc"))
    rows.append({**gd, "nguon": "TIN", "email": "gd.cu@example.com", "chuc_vu": "Giám đốc Chi nhánh (bản cũ)"})              # cùng người ở file cũ: gộp, email lệch giữ thành "email khác"
    rows.append({**next(r for r in rows if r["don_vi"] == "Đà Nẵng" and r["chuc_vu"].startswith("Kế toán")), "nguon": "TIN"})
    tay = [("Chị Hạ tầng đối tác Đà Nẵng", "Đối tác quản lý hạ tầng", "Đà Nẵng"), ("Anh Đối tác Quảng Nam", "Đối tác kỹ thuật", "Quảng Nam")]
    for i, (ten, chuc, dv) in enumerate(tay, start=1):
        rows.append({"nguon": "TAY", "ho_ten": ten, "chuc_vu": chuc, "email": f"doitac{i}@example.com", "ext": None, "di_dong": f"090009{i:04d}", "don_vi": dv, "khu_vuc": "Thêm tay",
                     "ghi_chu": None, "cap_nhat_luc": bay_gio, "cap_nhat_boi": NGUOI})
    with session_scope() as s:
        s.execute(DanhBa.__table__.insert(), rows)                    # executemany: mọi dòng cùng bộ cột
    from app.bo_nho import xoa
    xoa()
    return len(rows)


PHAN_HOI = [("Cải thiện tính năng", "Báo cáo ngày", "Cho phép sao chép nhanh số của hôm qua sang hôm nay để đỡ gõ lại.", "da_xu_ly", "Đã thêm nút sao chép ở bản cập nhật tuần này."),
            ("Bổ sung tính năng", "Nhập tồn", "Thêm bộ lọc theo khu vực lắp đặt để tìm ca nhanh hơn.", "dang_xu_ly", "Đang xem xét cùng nhóm Kỹ thuật."),
            ("Cải thiện tính năng", "Báo cáo phòng", "Bảng nhân sự nên có cột chênh lệch so với hôm qua.", "moi", None),
            ("Khác", "Tra cứu giá", "Giá gói Combo hiển thị chậm lúc đầu giờ sáng.", "moi", None),
            ("Bổ sung tính năng", "Soạn email", "Thêm mẫu mail xin hỗ trợ khảo sát hạ tầng nhanh.", "da_xu_ly", "Đã có mẫu mới ở mục Soạn email.")]


def nap_phan_hoi() -> int:
    """Vài phản hồi bịa của sale để Quản trị → Phản hồi có nội dung (đủ ba trạng thái)."""
    from app.db import session_scope
    from app.models import PhanHoi
    from app.phan_hoi import dam_bao_bang_phan_hoi
    dam_bao_bang_phan_hoi()
    bay_gio = datetime.utcnow()
    with session_scope() as s:
        for i, (loai, muc, nd, tt, gc) in enumerate(PHAN_HOI):
            s.add(PhanHoi(username="sale_demo", ho_ten="Nhân viên IBB7-0" + str(i + 1), vai_tro="Nhân viên KD", phong=PHONG_BC, loai=loai, muc=muc, noi_dung=nd, trang_thai=tt, ghi_chu_admin=gc,
                          tao_luc=bay_gio - timedelta(days=6 - i, hours=i), xu_ly_luc=bay_gio - timedelta(days=5 - i) if tt != "moi" else None, xu_ly_boi=NGUOI if tt != "moi" else None))
    return len(PHAN_HOI)


def nap_nhap_lieu(rng: random.Random, tc: date) -> dict:
    """Điểm vào: nạp toàn bộ phần nhập liệu / công cụ. Gọi sau khi đã có hợp đồng và danh mục nhân sự."""
    from app import bao_cao_ngay as bc
    from app.bo_nho import xoa
    hom = bc.hom_nay()
    kq = {"bao_cao_ngay": nap_bao_cao_ngay(rng, tc, hom), "online_ca": nap_online_ca(rng, tc, hom), "nhap_ton": nap_nhap_ton(rng, hom), "ads": nap_ads(rng, tc), "danh_ba": nap_danh_ba(rng),
          "phan_hoi": nap_phan_hoi()}
    xoa()
    return kq
