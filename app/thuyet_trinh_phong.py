"""Bài thuyết trình cho MỘT phòng kinh doanh (yêu cầu kiểu "phân tích phòng IBB7"): tổng quan phòng, nhịp ngày, nhân sự, vì sao tăng giảm, chất lượng bán so chi nhánh, tồn, tỉnh, việc cần làm.

Số liệu lấy từ các hàm có sẵn như bài chi nhánh (`ban_tin._so_lieu_bgd` cho hàng của phòng, `bao_cao_phong.bang_nhan_su` cho từng người, `metrics.daily_counts`, `phan_tich` cho tỉnh,
`fox_nguyen_nhan` cho nguyên nhân); không viết lại công thức. Quy tắc nhân sự như Báo cáo phòng: trưởng phòng, người nghỉ, acc tạm không được xét (`khong_xet`) nhưng số của họ vẫn nằm trong số phòng.
Mọi slide dùng chung khuôn `thuyet_trinh._slide` (số hiện trên slide do code viết, `su_that` để kiểm lời nói của AI).
"""
from __future__ import annotations

import pandas as pd

from app import ban_tin as bt, ban_tin_nd as bnd, bao_cao_phong as bcp, metrics, thuyet_trinh as tt, thuyet_trinh_ve as ve

TOI_DA_NGUOI_BIEU_DO = 10        # số nhân sự nêu trên biểu đồ
TOI_DA_NGUOI_BANG = 6            # số nhân sự cần trao đổi nêu trong bảng
BAN_KEM_TOI_THIEU = 8            # từ bấy nhiêu online mà chưa có V.VIP / Camera nào thì nêu (cùng ngưỡng bộ quét của Trợ lý điều hành)
_so, _slide, _co, _doi = tt._so, tt._slide, tt._co, tt._doi


def _num(v) -> int:
    return int(float(v)) if v is not None and not pd.isna(v) else 0


def _du_lieu(c: dict, code: str) -> dict:
    """Hàng của phòng ở các bảng của lượt này, kèm bảng nhân sự; ném ValueError (câu tiếng Việt) nếu phòng không có số."""
    sl = c["sl"]
    db = sl["phong"][sl["phong"]["phong_code"] == code]
    tq = sl["tq"][(sl["tq"]["loai_dong"] == "data") & (sl["tq"]["phong_code"] == code)]
    if db.empty or tq.empty:
        raise ValueError(f"Phòng {code} chưa có mục tiêu hoặc số liệu trong kỳ này nên chưa thuyết trình được.")
    ns = bcp.bang_nhan_su(c["thang"], c["ngay"], code)
    data = ns[ns["loai_dong"] == "data"] if len(ns) else ns
    nguoi = data[data["khong_xet"].fillna("").eq("")] if "khong_xet" in data else data
    return {"db": db.iloc[0], "tq": tq.iloc[0], "ns": data, "nguoi": nguoi, "ten": str(db.iloc[0]["phong"])}


# ------------------------------------------------------------------ các slide
def _tong_quan(c: dict, code: str, d: dict) -> dict:
    db, tq, ten = d["db"], d["tq"], d["ten"]
    mt, luy, dub, nhip = int(db["mt"]), int(db["luy_ke"]), int(db["du_bao"]), int(db["du_bao_nhip"])
    ngay, so_ngay, con = c["ngay"], c["so_ngay"], c["con_lai"]
    pct_dat, pct_tg, hut = bt._pct(luy, mt), bt._pct(ngay, so_ngay), max(0, mt - dub)
    can = None if pd.isna(db["can_moi_ngay"]) else int(db["can_moi_ngay"])
    tb, ck = float(db["tb_ngay"]), _num(tq["ck_online"])
    chenh = luy - ck
    dg = str(db["danh_gia"])
    ban_hang = c["sl"]["phong"][c["sl"]["phong"]["phong_code"].isin(c["ma_ban_hang"])].dropna(subset=["pct_mt"]).sort_values("pct_mt", ascending=False)
    ma = list(ban_hang["phong_code"])
    hang, n_phong = (ma.index(code) + 1 if code in ma else None), len(ma)
    so_nguoi = len(d["nguoi"])
    mau_dg = {"An toàn": "tot", "Cần tăng tốc": "vang", "Rủi ro": "xau"}.get(dg, "")
    kpi = [{"nhan": "Online luỹ kế", "gia_tri": _so(luy), "phu": f"{pct_dat}% mục tiêu {_so(mt)}", "mau": ""},
           {"nhan": "Dự báo cuối tháng", "gia_tri": _so(dub), "phu": f"theo nhịp cuối tháng: {_so(nhip)} · {dg}", "mau": mau_dg},
           {"nhan": "Cần mỗi ngày", "gia_tri": _so(can) if can is not None else "–", "phu": f"hiện {_so(tb, 1)}/ngày · còn {con} ngày", "mau": "xau" if can is not None and can > tb else "tot"},
           {"nhan": "So cùng kỳ tháng trước", "gia_tri": f"{chenh:+d}", "phu": f"cùng kỳ {_so(ck)}", "mau": "tot" if chenh >= 0 else "xau"},
           {"nhan": "Hạng dự báo", "gia_tri": f"{hang}/{n_phong}" if hang else "–", "phu": f"{so_nguoi} nhân sự được xét", "mau": ""}]
    diem = [f"Luỹ kế {_so(luy)} online, bằng {pct_dat}% mục tiêu {_so(mt)} khi thời gian đã qua {pct_tg}%.",
            f"Dự báo cuối tháng {_so(dub)} (theo nhịp cuối tháng {_so(nhip)}), " + (f"hụt {_so(hut)} so với mục tiêu" if hut else "đạt mục tiêu") + f"; đánh giá: {dg}.",
            (f"Cần {_so(can)} online mỗi ngày trong {con} ngày còn lại, hiện đang đạt {_so(tb, 1)}/ngày." if can is not None else "Đã hết tháng."),
            f"So với cùng kỳ tháng trước: {chenh:+d} online." + (f" Xếp hạng dự báo {hang}/{n_phong} phòng bán hàng." if hang else "")]
    su_that = _co(c, phong=ten, luy_ke=luy, muc_tieu=mt, pct_dat=pct_dat, pct_thoi_gian=pct_tg, du_bao=dub, du_bao_nhip=nhip, hut=hut, can_moi_ngay=can, tb_ngay=round(tb, 1), cung_ky=ck,
                  chenh=chenh, chenh_tuyet_doi=abs(chenh), danh_gia=dg, hang=hang, so_phong=n_phong, so_nhan_su=so_nguoi)
    loi = (f"Kính chào Ban giám đốc. Đây là phân tích phòng {ten} tính đến ngày {ngay} tháng {c['thang_so']}. Phòng đã có {luy} online, bằng {pct_dat}% mục tiêu {mt}, khi thời gian đã qua {pct_tg}%. "
           + (f"Dự báo cuối tháng khoảng {dub} online, hụt {hut} so với mục tiêu, đánh giá mức {dg}. " if hut else f"Dự báo cuối tháng khoảng {dub} online, đạt mục tiêu. ")
           + (f"Cần {can} online mỗi ngày trong {con} ngày còn lại, hiện đang đạt {_so(tb, 1)}. " if can is not None else "")
           + f"So với cùng kỳ tháng trước, {_doi(chenh)} online." + (f" Phòng đứng hạng {hang} trên {n_phong} phòng bán hàng theo dự báo." if hang else ""))
    return _slide("tong_quan_phong", f"Phòng {ten} · tới ngày {ngay:02d}/{c['thang_so']:02d}", diem, su_that, loi, kpi=kpi, phong_chinh={"ma": code, "ten": ten})


def _nhip(c: dict, code: str, d: dict) -> dict:
    thang, ngay, pm = c["thang"], c["ngay"], metrics.prev_month(c["thang"])
    ten, db = d["ten"], d["db"]
    hang_nay, hang_truoc = metrics.daily_counts(thang, "online"), metrics.daily_counts(pm, "online")
    ngays = list(range(1, ngay + 1))
    nay = [_num(hang_nay.loc[code].get(k, 0)) if code in hang_nay.index else 0 for k in ngays]
    truoc = [_num(hang_truoc.loc[code].get(k, 0)) if code in hang_truoc.index else 0 for k in ngays]
    can = None if pd.isna(db["can_moi_ngay"]) else float(db["can_moi_ngay"])
    tb7 = round(sum(nay[-7:]) / len(nay[-7:]), 1) if nay else 0.0
    tb7_truoc = round(sum(nay[-14:-7]) / 7, 1) if ngay >= 14 else None
    xet = nay[:-1] if c["tam_tinh"] and len(nay) > 1 else nay
    cao_d = max(range(len(xet)), key=lambda i: xet[i]) + 1 if xet else None
    thap_d = min(range(len(xet)), key=lambda i: xet[i]) + 1 if xet else None
    ngay_khong = sum(1 for v in xet if v == 0)
    xu_huong = "" if tb7_truoc is None else (" Đang tăng nhịp." if tb7 > tb7_truoc * 1.05 else " Đang chậm nhịp." if tb7 < tb7_truoc * 0.95 else " Nhịp đi ngang.")
    diem = [f"Bình quân cả tháng {_so(db['tb_ngay'], 1)} online mỗi ngày" + (f", cần {_so(can)} để kịp mục tiêu." if can is not None else "."),
            f"7 ngày gần nhất bình quân {_so(tb7, 1)}/ngày" + (f", 7 ngày trước đó {_so(tb7_truoc, 1)}/ngày.{xu_huong}" if tb7_truoc is not None else "."),
            (f"Ngày cao nhất: ngày {cao_d} ({xet[cao_d - 1]} online); thấp nhất: ngày {thap_d} ({xet[thap_d - 1]} online)." if xet else ""),
            (f"Có {ngay_khong} ngày phòng không có online nào." if ngay_khong else "")]
    su_that = _co(c, phong=ten, tb_ngay=round(float(db["tb_ngay"]), 1), can_moi_ngay=can, tb_7_ngay=tb7, tb_7_ngay_truoc=tb7_truoc, ngay_cao_nhat=cao_d, so_ngay_cao_nhat=xet[cao_d - 1] if xet else None,
                  ngay_thap_nhat=thap_d, so_ngay_thap_nhat=xet[thap_d - 1] if xet else None, so_ngay_khong_co_online=ngay_khong, theo_ngay={str(k): v for k, v in zip(ngays, nay)})
    loi = (f"Về nhịp của {ten}, bình quân cả tháng là {_so(db['tb_ngay'], 1)} online mỗi ngày" + (f", trong khi cần {_so(can)} mỗi ngày để kịp mục tiêu. " if can is not None else ". ")
           + f"Bảy ngày gần nhất bình quân {_so(tb7, 1)} mỗi ngày" + (f", so với {_so(tb7_truoc, 1)} của bảy ngày trước đó.{xu_huong} " if tb7_truoc is not None else ". ")
           + (f"Ngày cao nhất là ngày {cao_d} với {xet[cao_d - 1]} online, thấp nhất là ngày {thap_d} với {xet[thap_d - 1]} online." if xet else ""))
    return _slide("nhip_phong", f"Nhịp online từng ngày · {ten}", [x for x in diem if x], su_that, loi, hinh=ve.nhip_theo_ngay(ngays, nay, truoc, can, f"Tháng {pm[5:7].lstrip('0')}"), phong_chinh={"ma": code, "ten": ten})


def _nhan_su(c: dict, code: str, d: dict) -> dict:
    ten, ng = d["ten"], d["nguoi"].copy()
    ng["online"] = pd.to_numeric(ng["online"], errors="coerce").fillna(0).astype(int)
    ng["ck_online"] = pd.to_numeric(ng["ck_online"], errors="coerce").fillna(0).astype(int)
    ng["chenh"] = ng["online"] - ng["ck_online"]
    ng = ng.sort_values(["online", "ck_online"], ascending=False)
    top = ng.head(TOI_DA_NGUOI_BIEU_DO)
    giam = ng[ng["chenh"] < 0].sort_values("chenh")
    tang = ng[ng["chenh"] > 0].sort_values("chenh", ascending=False)
    tong_online = int(ng["online"].sum())
    top3 = int(ng["online"].head(3).sum())
    phu_thuoc = bt._pct(top3, tong_online) or 0
    giam_l = [(str(r.ho_ten), int(r.chenh)) for r in giam.head(3).itertuples()]
    tang_l = [(str(r.ho_ten), int(r.chenh)) for r in tang.head(3).itertuples()]
    cho_nhau = ng[ng["muc_chu_y"].fillna("") != ""]
    diem = [f"{len(ng)} nhân sự được xét: {len(tang)} người tăng, {len(giam)} người giảm so với cùng kỳ tháng trước.",
            f"3 người đứng đầu làm {phu_thuoc}% số online của nhóm được xét.",
            ("Giảm nhiều nhất: " + ", ".join(f"{t} ({v:+d})" for t, v in giam_l) + ".") if giam_l else "Không có ai giảm so với cùng kỳ.",
            ("Tăng nhiều nhất: " + ", ".join(f"{t} ({v:+d})" for t, v in tang_l) + ".") if tang_l else ""]
    bang = None
    if len(cho_nhau):
        dong = [[str(r.ho_ten), int(r.online), int(r.ck_online), _num(r.ton_qua_7), str(r.muc_chu_y), tt._cat(str(r.chu_y or ""), 70)] for r in cho_nhau.head(TOI_DA_NGUOI_BANG).itertuples()]
        bang = {"cot": ["Nhân sự", "Online", "Cùng kỳ", "Tồn từ 7 ngày", "Mức", "Lý do"], "dong": dong}
    su_that = _co(c, phong=ten, so_nguoi=len(ng), nguoi_tang=len(tang), nguoi_giam=len(giam), top3_pct=phu_thuoc, giam_nhieu={t: abs(v) for t, v in giam_l}, tang_nhieu={t: v for t, v in tang_l},
                  can_trao_doi=len(cho_nhau), online_nguoi={str(r.ho_ten): int(r.online) for r in top.itertuples()})
    loi = (f"Về nhân sự của {ten}, có {len(ng)} người được xét, {len(tang)} người tăng và {len(giam)} người giảm so với cùng kỳ tháng trước. Ba người đứng đầu làm {phu_thuoc} phần trăm số online. "
           + (("Giảm nhiều nhất là " + ", ".join(f"{t} giảm {abs(v)}" for t, v in giam_l) + ". ") if giam_l else "")
           + (("Tăng nhiều nhất là " + ", ".join(f"{t} tăng {v}" for t, v in tang_l) + ". ") if tang_l else "")
           + (f"Có {len(cho_nhau)} người cần trao đổi." if len(cho_nhau) else ""))
    hinh = ve.nhan_su_online([str(x) for x in top["ho_ten"]], [int(x) for x in top["online"]], [int(x) for x in top["ck_online"]])
    return _slide("nhan_su_phong", f"Nhân sự {ten}: ai kéo, ai giảm", diem, su_that, loi, hinh=hinh, bang=bang, phong_chinh={"ma": code, "ten": ten})


def _chat_luong(c: dict, code: str, d: dict) -> dict:
    ten, tq, tong, ng = d["ten"], d["tq"], c["sl"]["tong"], d["nguoi"]
    v_p, v_c = tq["vvip_ty_le"], tong["vvip_ty_le"]
    cam_p, cam_c = bnd._ty_le_camera(tq["online"], tq["camera"]), bnd._ty_le_camera(tong["online"], tong["camera"])
    onl = pd.to_numeric(ng["online"], errors="coerce").fillna(0)
    thieu_v = [str(r.ho_ten) for r, o in zip(ng.itertuples(), onl) if o >= BAN_KEM_TOI_THIEU and _num(r.vvip) == 0][:3]
    thieu_c = [str(r.ho_ten) for r, o in zip(ng.itertuples(), onl) if o >= BAN_KEM_TOI_THIEU and _num(r.camera) == 0][:3]
    diem = [f"V.VIP {_so(v_p)}% trên online của phòng, chi nhánh {_so(v_c)}%.", f"Camera {cam_p}% trên online của phòng, chi nhánh {cam_c}%.",
            (f"Từ {BAN_KEM_TOI_THIEU} online mà chưa bán V.VIP: {', '.join(thieu_v)}." if thieu_v else ""), (f"Từ {BAN_KEM_TOI_THIEU} online mà chưa bán Camera: {', '.join(thieu_c)}." if thieu_c else "")]
    su_that = _co(c, phong=ten, vvip_phong=v_p, vvip_chi_nhanh=v_c, camera_phong=cam_p, camera_chi_nhanh=cam_c, nguong_online=BAN_KEM_TOI_THIEU, chua_ban_vvip=len(thieu_v), chua_ban_camera=len(thieu_c))
    loi = (f"Về chất lượng bán, tỷ lệ V.VIP của {ten} là {_so(v_p)} phần trăm, chi nhánh là {_so(v_c)}; tỷ lệ Camera của phòng là {cam_p} phần trăm, chi nhánh là {cam_c}. "
           + (f"Những người từ {BAN_KEM_TOI_THIEU} online mà chưa bán V.VIP gồm {', '.join(thieu_v)}. " if thieu_v else "")
           + (f"Chưa bán Camera gồm {', '.join(thieu_c)}." if thieu_c else ""))
    return _slide("chat_luong_phong", f"Chất lượng bán · {ten} so với chi nhánh", [x for x in diem if x], su_that, loi,
                  hinh=ve.chat_luong([f"Phòng {ten}", "Chi nhánh"], [float(v_p or 0), float(v_c or 0)], [float(cam_p or 0), float(cam_c or 0)], None, None), phong_chinh={"ma": code, "ten": ten})


def _ton(c: dict, code: str, d: dict) -> dict:
    ten, ns, tq = d["ten"], d["ns"].copy(), d["tq"]
    ns["lau"] = pd.to_numeric(ns["ton_qua_7"], errors="coerce").fillna(0).astype(int)
    tong_lau = int(ns["lau"].sum())
    tong_ton = _num(tq["so_ton"])
    top = [(str(r.ho_ten), int(r.lau)) for r in ns.sort_values("lau", ascending=False).head(8).itertuples() if r.lau > 0]
    diem = [f"{_so(tong_lau)} hợp đồng chờ online từ {bnd.TON_QUA_NGAY} ngày, trong tổng {_so(tong_ton)} hợp đồng tồn của phòng.", ("Nhiều nhất: " + ", ".join(f"{t} ({n})" for t, n in top[:3]) + ".") if top else "Không ai có hợp đồng tồn lâu."]
    su_that = _co(c, phong=ten, ton_lau=tong_lau, tong_ton=tong_ton, nguong_ngay=bnd.TON_QUA_NGAY, ton_theo_nguoi={t: n for t, n in top})
    loi = (f"Về hợp đồng tồn của {ten}, hiện có {tong_lau} hợp đồng chờ online từ {bnd.TON_QUA_NGAY} ngày trở lên, trong tổng số {tong_ton} hợp đồng tồn. "
           + (("Nhiều nhất là " + ", ".join(f"{t} {n} hợp đồng" for t, n in top[:3]) + ".") if top else ""))
    return _slide("ton_phong", f"Hợp đồng tồn lâu · {ten}", diem, su_that, loi, hinh=ve.ton_lau([t for t, _ in top], [n for _, n in top]) if top else None, phong_chinh={"ma": code, "ten": ten})


def _ket_luan(c: dict, code: str, d: dict) -> dict:
    ten, db, ng = d["ten"], d["db"], d["nguoi"].copy()
    ng["chenh"] = pd.to_numeric(ng["online"], errors="coerce").fillna(0) - pd.to_numeric(ng["ck_online"], errors="coerce").fillna(0)
    giam = ng[ng["chenh"] < 0].sort_values("chenh")
    can = None if pd.isna(db["can_moi_ngay"]) else int(db["can_moi_ngay"])
    n_nguoi = max(len(ng), 1)
    ns, tq, tong = d["ns"], d["tq"], c["sl"]["tong"]
    lau = int(pd.to_numeric(ns["ton_qua_7"], errors="coerce").fillna(0).sum())
    han = bnd.han_xu_ly(c["ngay_iso"])
    diem, loi, su = [], [], {}
    if can is not None and c["con_lai"] > 0 and int(db["du_bao"]) < int(db["mt"]):
        moi = round(can / n_nguoi, 1)
        diem.append(f"Chốt mục tiêu cả phòng {_so(can)} online mỗi ngày, chia bình quân {_so(moi, 1)} online mỗi người trong {c['con_lai']} ngày còn lại.")
        loi.append(f"Chốt mục tiêu cả phòng {can} online mỗi ngày, chia bình quân {_so(moi, 1)} online mỗi người trong {c['con_lai']} ngày còn lại.")
        su.update(can_moi_ngay=can, moi_nguoi=moi, so_nguoi=n_nguoi)
    if len(giam):
        ds, bu = ", ".join(str(x) for x in giam["ho_ten"].head(3)), int(-giam["chenh"].sum())
        diem.append(f"Trưởng phòng kèm {len(giam)} người đang giảm, trước hết {ds}; nếu về mức cùng kỳ thì phòng thêm {_so(bu)} online.")
        loi.append(f"Trưởng phòng kèm {len(giam)} người đang giảm, trước hết {ds}; nếu họ về mức cùng kỳ thì phòng thêm {bu} online.")
        su.update(nguoi_giam=len(giam), bu_duoc=bu)
    if lau:
        top = ", ".join(str(r.ho_ten) for r in ns.assign(l=pd.to_numeric(ns["ton_qua_7"], errors="coerce").fillna(0)).sort_values("l", ascending=False).head(3).itertuples() if r.l > 0)
        diem.append(f"Xử lý dứt điểm {_so(lau)} hợp đồng tồn lâu" + (f", tập trung {top}." if top else "."))
        loi.append(f"Xử lý dứt điểm {lau} hợp đồng tồn lâu" + (f", tập trung {top}." if top else "."))
        su.update(ton_lau=lau)
    for nhan, p, ch in (("V.VIP", tq["vvip_ty_le"], tong["vvip_ty_le"]), ("Camera", bnd._ty_le_camera(tq["online"], tq["camera"]), bnd._ty_le_camera(tong["online"], tong["camera"]))):
        if p is not None and ch is not None and float(ch) - float(p) >= bnd.CHENH_CHAT_LUONG:
            diem.append(f"Nâng tỷ lệ {nhan} từ {_so(p)}% lên mức chung của chi nhánh {_so(ch)}%.")
            loi.append(f"Nâng tỷ lệ {nhan} từ {_so(p)} phần trăm lên mức chung của chi nhánh là {_so(ch)}.")
            su[f"nang_{nhan}"] = {"tu": round(float(p)), "len": round(float(ch))}
    if not diem:
        diem.append("Chưa có việc cần can thiệp: giữ nhịp và rà hợp đồng tồn mỗi ngày.")
        loi.append("Hiện chưa có việc cần can thiệp, đề nghị giữ nhịp và rà hợp đồng tồn mỗi ngày.")
    diem.append(f"Hạn xử lý nhanh: trước ngày {bnd.ngay_vn(han)}.")
    loi.append(f"Đề nghị hoàn thành trước ngày {han.day} tháng {han.month}.")
    su.update(han_ngay=han.day, han_thang=han.month, phong=ten)
    return _slide("ket_luan", f"Việc cần làm · {ten}", diem, _co(c, **su), f"Tổng kết lại các việc cần làm của {ten}. " + " ".join(loi), phong_chinh={"ma": code, "ten": ten})


# ------------------------------------------------------------------ dựng
def dung_slide(c: dict, user, code: str) -> list[dict]:
    """Các slide của một phòng. Thiếu số của phòng thì ném ValueError; slide nào lỗi nguồn thì bỏ."""
    d = _du_lieu(c, code)
    slides = [_tong_quan(c, code, d)]
    for ham in (_nhip, _nhan_su):
        try:
            slides.append(ham(c, code, d))
        except Exception:
            continue
    try:
        slides.append(tt.slide_nguyen_nhan(c, user, code, d["ten"]))
    except Exception:
        pass
    for ham in (_chat_luong, _ton):
        try:
            slides.append(ham(c, code, d))
        except Exception:
            continue
    try:
        slides.append(tt._tinh(c, code, d["ten"]))
    except Exception:
        pass
    slides.append(_ket_luan(c, code, d))
    return slides
