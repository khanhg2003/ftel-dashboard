"""Bổ sung bộ minh hoạ cho phần Phân loại khách hàng (chạy lại ra đúng cùng kết quả, hạt giống cố định trong meta.json).

Bộ minh hoạ gốc (167 hợp đồng) dồn nhiều ca có vấn đề để các luật có chỗ chạy, gần như không có khách ổn định. Script này thêm:
1. 60 hợp đồng ỔN ĐỊNH (`MHAAA0168`..`MHAAA0227`) vào kd.csv: đã online 3-40 tháng, không có SR, không nợ; Kỹ thuật chỉ có một lần
   triển khai đúng hẹn (kt.csv). Một phần đã có FPT Play / Camera (dich_vu.csv). Đây là nhóm để minh hoạ báo cáo Bán thêm.
2. `cuoc.csv`: lịch sử kỳ cước cho MỌI hợp đồng đã online:
   - chu kỳ = số tháng trả trước (không có thì 1 tháng), kỳ đầu bắt đầu ở ngày online, hạn thanh toán là ngày đầu kỳ;
   - số tiền = cước tháng x số tháng của kỳ (thiếu cước thì 180.000 đ/tháng), làm tròn nghìn đồng;
   - giữ tối đa 12 tháng gần nhất cộng kỳ kế tiếp đã phát hành (phát hành 10 ngày trước đầu kỳ);
   - hợp đồng nằm trong danh sách nợ: kỳ đã tới hạn gần nhất CHƯA thanh toán (khớp với no_cuoc.csv);
   - khoảng 1/6 hợp đồng "hay trả trễ": các kỳ cũ trả sau hạn 3-25 ngày; số còn lại trả trước hoặc đúng hạn.
Mọi số ở đây là GIẢ ĐỊNH. Không có tên khách hàng, địa chỉ hay số điện thoại.

Chạy: python scripts/bo_sung_demo.py
"""
import json
import random
from pathlib import Path

import pandas as pd

THU_MUC = Path(__file__).resolve().parents[1] / "demo" / "lien_khoi"
COT = ["so_hd", "ky_tu", "ky_den", "so_tien", "han_tt", "ngay_tt", "hinh_thuc"]


GOC = 167                                # số hợp đồng của bộ minh hoạ gốc
THEM = 60                                # số hợp đồng ổn định bổ sung


def _ma(i: int) -> str:
    return f"MHAAA{i:04d}"


def them_on_dinh() -> tuple[int, int]:
    """Thêm (hoặc dựng lại) các hợp đồng ổn định vào kd.csv và dich_vu.csv. Trả về (số hợp đồng thêm, số dòng dịch vụ thêm)."""
    meta = json.loads((THU_MUC / "meta.json").read_text(encoding="utf-8"))
    hom_nay = pd.Timestamp(meta["ngay_tc"])
    rd = random.Random(meta["hat_giong"] + 11)
    moi = {_ma(i) for i in range(GOC + 1, GOC + THEM + 1)}
    kd = pd.read_csv(THU_MUC / "kd.csv", dtype=str, keep_default_na=False)
    dv = pd.read_csv(THU_MUC / "dich_vu.csv", dtype=str, keep_default_na=False)
    kt = pd.read_csv(THU_MUC / "kt.csv", dtype=str, keep_default_na=False)
    kd, dv, kt = kd[~kd["so_hd"].isin(moi)], dv[~dv["so_hd"].isin(moi)], kt[~kt["so_hd"].isin(moi)]
    ktv = sorted(x for x in set(kt["nguoi"]) if x.startswith("ktv_"))
    sale, cn = sorted(set(kd["sale"])), sorted(set(kd["cn_quan_ly"]) - {""})
    dong_kd, dong_dv, dong_kt = [], [], []
    for ma in sorted(moi):
        online = hom_nay - pd.Timedelta(days=rd.randint(95, 40 * 30))
        tao = online - pd.Timedelta(days=rd.randint(1, 4))
        goi = rd.choices(["Giga", "Sky", "Sky F1", "Giga F1"], [45, 35, 12, 8])[0]
        thang = rd.choices([0, 6, 13], [50, 30, 20])[0]
        gia = rd.choice([150, 165, 180, 195, 205, 235]) + (30 if goi.startswith("Sky") else 0)
        tong = gia * thang if thang else 0
        dong_kd.append({"so_hd": ma, "ngay_tao": f"{tao:%Y-%m-%d}", "ngay_online": f"{online:%Y-%m-%d}", "ngay_huy": "", "sale": rd.choice(sale), "phong": "DEMO",
                        "goi": goi, "tinh_trang": "Bình thường", "ton": "0", "cuoc_thang": f"{gia * 1000:.1f}", "hinh_thuc_tt": rd.choice(["Chuyen khoan ngan hang"] * 4 + ["HiFPT"]),
                        "so_thang_tra_truoc": f"{thang:.1f}" if thang else "", "so_tien_tra_truoc": f"{tong * 1000:.1f}" if thang else "", "tien_hoa_mang": "300000.0",
                        "chinh_sach": f"Tra truoc {thang}T {tong}k/{thang}T, 300k PHM" if thang else f"Basic Net 1T {gia}k/1T, 300k PHM",
                        "doi_tuong": "Đối tượng khác", "nguon_ban": "IBB", "cn_quan_ly": rd.choice(cn)})
        co_play, co_cam = rd.random() < 0.45, rd.random() < 0.2
        dich_vu = "Internet" + (" + FPT Camera Bundle" if co_cam else "") + (" + FPT Play" if co_play else "")
        dong_kt.append({"so_hd": ma, "loai": "trien_khai", "thoi_diem": f"{online:%Y-%m-%d} {rd.randint(8, 16):02d}:{rd.randint(0, 59):02d}:00",
                        "chi_tiet": "Triển khai: hẹn 1 lần, đúng hẹn", "nguoi": rd.choice(ktv), "so_lan": "1",
                        "thuoc_tinh": json.dumps({"so_lan_hen": "1", "loai_dich_vu": dich_vu, "loai_giao_dich": "Triển khai mới", "tgxl_72h": "0",
                                                  "cap_indoor": "0", "cap_outdoor": "0"}, ensure_ascii=False)})
        if co_play:
            vvip = rd.random() < 0.4
            dong_dv.append({"so_hd": ma, "nhom": "FPT Play", "ten": "V.VIP No Box" if vvip else "VIP No Box", "so_luong": "1", "don_gia": "", "vvip": "1" if vvip else "0"})
        if co_cam:
            dong_dv.append({"so_hd": ma, "nhom": "Camera", "ten": "Gói Cloud IQ3+", "so_luong": "1", "don_gia": "", "vvip": "0"})
    pd.concat([kd, pd.DataFrame(dong_kd, columns=kd.columns)], ignore_index=True).to_csv(THU_MUC / "kd.csv", index=False)
    pd.concat([dv, pd.DataFrame(dong_dv, columns=dv.columns)], ignore_index=True).to_csv(THU_MUC / "dich_vu.csv", index=False)
    pd.concat([kt, pd.DataFrame(dong_kt, columns=kt.columns)], ignore_index=True).to_csv(THU_MUC / "kt.csv", index=False)
    meta["so_hop_dong"] = GOC + THEM
    (THU_MUC / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(dong_kd), len(dong_dv)


def dung() -> pd.DataFrame:
    meta = json.loads((THU_MUC / "meta.json").read_text(encoding="utf-8"))
    hom_nay = pd.Timestamp(meta["ngay_tc"])
    rd = random.Random(meta["hat_giong"] + 7)
    kd = pd.read_csv(THU_MUC / "kd.csv", dtype=str, keep_default_na=False)
    no = set(pd.read_csv(THU_MUC / "no_cuoc.csv", dtype=str, keep_default_na=False).query("loai == 'no_cuoc'")["so_hd"])
    dong = []
    for r in kd.sort_values("so_hd").to_dict("records"):
        if not r["ngay_online"] or r["ngay_huy"]:
            continue
        online = pd.Timestamp(r["ngay_online"])
        thang = int(float(r["so_thang_tra_truoc"] or 0)) or 1
        cuoc = float(r["cuoc_thang"] or 0)
        cuoc = (cuoc * 1000 if cuoc < 5000 else cuoc) or 180000
        so_tien = int(round(cuoc * thang, -3))
        hay_tre = rd.random() < 1 / 6
        hinh_thuc = "HiFPT" if r["hinh_thuc_tt"] == "HiFPT" else rd.choice(["Chuyển khoản", "Chuyển khoản", "Ví điện tử", "Tại quầy"])
        ky, i = [], 0
        while True:
            tu = online + pd.DateOffset(months=thang * i)
            if tu - pd.Timedelta(days=10) > hom_nay:                 # kỳ này chưa phát hành
                break
            ky.append(tu)
            i += 1
        ky = [t for t in ky if t >= hom_nay - pd.DateOffset(months=12)] or ky[-1:]
        da_toi_han = [t for t in ky if t <= hom_nay]
        for tu in ky:
            den = tu + pd.DateOffset(months=thang) - pd.Timedelta(days=1)
            if tu > hom_nay:                                        # đã phát hành, chưa tới hạn: một số khách trả sớm
                tt = tu - pd.Timedelta(days=rd.randint(1, 8)) if (r["so_hd"] not in no and rd.random() < 0.35) else None
                tt = tt if tt is not None and tt <= hom_nay else None
            elif r["so_hd"] in no and tu == da_toi_han[-1]:
                tt = None                                           # đang nợ kỳ này
            else:
                tt = tu + pd.Timedelta(days=rd.randint(3, 25) if hay_tre else rd.randint(-6, 0))
                tt = min(tt, hom_nay)
            dong.append({"so_hd": r["so_hd"], "ky_tu": f"{tu:%Y-%m-%d}", "ky_den": f"{den:%Y-%m-%d}", "so_tien": so_tien, "han_tt": f"{tu:%Y-%m-%d}",
                         "ngay_tt": f"{tt:%Y-%m-%d}" if tt is not None else "", "hinh_thuc": hinh_thuc if tt is not None else ""})
    return pd.DataFrame(dong, columns=COT)


if __name__ == "__main__":
    n_kd, n_dv = them_on_dinh()
    print(f"Thêm {n_kd} hợp đồng ổn định và {n_dv} dòng dịch vụ kèm")
    d = dung()
    d.to_csv(THU_MUC / "cuoc.csv", index=False)
    print(f"{len(d)} kỳ cước của {d['so_hd'].nunique()} hợp đồng; {int(d['ngay_tt'].eq('').sum())} kỳ chưa thanh toán")
