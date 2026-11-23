"""Thuyết trình AI cho khối KINH DOANH (chủ app chốt 23/11/2026, bản đầu): dựng một bài thuyết trình nhiều slide từ số liệu của app để Ban Giám đốc nghe và hỏi lại từng slide.

Nguyên tắc giống Trợ lý điều hành: CODE giữ mọi con số, biểu đồ, bảng và câu chữ hiển thị trên slide (lấy từ các hàm có sẵn: `ban_tin`, `ban_tin_nd`, `du_bao`, `metrics`, `phan_tich`,
`fox_nguyen_nhan`, bộ quét nhân sự của Trợ lý điều hành, không viết lại công thức nào). AI chỉ viết LỜI NÓI cho từng slide (`thuyet_trinh_ai`), mọi số trong lời nói phải có
trong `su_that` của slide, sai thì dùng lời nói mẫu do code viết ở đây. Không có tên khách hàng. Tên nhân sự chỉ hiện cho Ban Giám đốc (`duoc_cau_hinh`).

Một slide: {id, tieu_de, kpi[], hinh (figure dict), bang {cot, dong}, diem[] (gạch đầu dòng hiển thị), su_that {} (số để kiểm lời nói và để AI hiểu slide), loi_noi (chữ để đọc), nguon_loi}.
Bài: {ngay, ngay_hien, tam_tinh, slides[], dung_ai, ly_do_luat}.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime

import pandas as pd

from app import ban_tin as bt, ban_tin_nd as bnd, du_bao, metrics, overview, thuyet_trinh_ve as ve
from app import phan_tich as pt

TOI_DA_NHAN_SU = 8             # số nhân sự nêu trong bảng slide "Nhân sự cần chú ý"
TOI_DA_DONG_NGUYEN_NHAN = 6    # số dòng chẩn đoán nêu trong slide "Vì sao"
DO_DAI_DONG = 170              # cắt mỗi dòng gạch đầu dòng dài hơn bấy nhiêu ký tự
_so = bt._so


# ------------------------------------------------------------------ chữ cho giọng đọc
def cho_giong(chu: str) -> str:
    """Chuẩn hoá chữ cho trình duyệt đọc to: bỏ định dạng, bỏ dấu chấm ngăn nghìn (1.234 -> 1234), %, +, ngày tháng, mã phòng dính số (IBB7 -> IBB 7)."""
    chu = re.sub(r"\*\*|__|`|#+\s*", "", chu or "")
    chu = re.sub(r"^\s*[-•*]\s+", "", chu, flags=re.M)
    while re.search(r"\d\.\d{3}(?!\d)", chu):
        chu = re.sub(r"(\d)\.(\d{3})(?!\d)", r"\1\2", chu)

    def ngay_thang(m):
        a, b = int(m.group(1)), int(m.group(2))
        return f"ngày {a} tháng {b}" if a <= 31 and b <= 12 else f"{a} trên {b}"
    chu = re.sub(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?![\d/])", ngay_thang, chu)
    chu = re.sub(r"(\d)\s*%", r"\1 phần trăm", chu)
    chu = re.sub(r"(?<![\w])\+(\d)", r"tăng \1", chu)
    chu = re.sub(r"(?<=[\s(=,;])-(\d)", r"âm \1", chu)
    chu = re.sub(r"(?<=[A-Za-z])\.(?=[A-Za-z])", " ", chu)                  # DNG.Longph -> DNG Longph
    chu = re.sub(r"/ngày", " mỗi ngày", chu)
    chu = chu.replace("V.VIP", "V VIP").replace("_", " ")
    chu = re.sub(r"([A-Za-zÀ-ỹ]{2,})(\d+)", r"\1 \2", chu)
    chu = re.sub(r"\s*[()]\s*", ", ", chu)
    chu = re.sub(r"\s*\n+\s*", ". ", chu)
    chu = re.sub(r"\s+([,.])", r"\1", chu)
    return re.sub(r"[,.]\s*([,.])+", r"\1", chu).strip(" ,.") + "."


def _cat(chu: str, n: int = DO_DAI_DONG) -> str:
    chu = " ".join(str(chu).split())
    return chu if len(chu) <= n else chu[:n - 1].rstrip() + "…"


def _ds_ten(ds: list[tuple]) -> str:
    return ", ".join(f"{t} {v}" for t, v in ds)


def _doi(n: int) -> str:
    return f"tăng {abs(n)}" if n > 0 else f"giảm {abs(n)}" if n < 0 else "bằng"


# ------------------------------------------------------------------ ngữ cảnh chung
def _ngu_canh(ngay_iso: str | None) -> dict:
    ngay_iso = ngay_iso or metrics.ngay_moi_nhat()
    if not ngay_iso:
        raise ValueError("Chưa có số liệu để thuyết trình.")
    sl = bt._so_lieu_bgd(ngay_iso)
    thang, ngay = ngay_iso[:7], int(ngay_iso[8:10])
    so_ngay = metrics.month_range(thang)[2]
    try:
        tam_tinh = bool(overview.trang_thai_ngay(ngay_iso)[0])
    except Exception:
        tam_tinh = False
    return {"sl": sl, "ngay_iso": ngay_iso, "thang": thang, "ngay": ngay, "thang_so": int(thang[5:7]), "so_ngay": so_ngay, "con_lai": so_ngay - ngay, "tam_tinh": tam_tinh,
            "ten_phong": {r["phong_code"]: str(r["phong"]) for _, r in sl["phong"].iterrows()}, "ma_ban_hang": bnd._ma_ban_hang(sl)}


def _tuyet_doi(x, kq: set | None = None) -> set:
    kq = set() if kq is None else kq
    if isinstance(x, bool) or x is None:
        return kq
    if isinstance(x, (int, float)):
        if x < 0:
            kq.add(abs(x))
    elif isinstance(x, dict):
        for v in x.values():
            _tuyet_doi(v, kq)
    elif isinstance(x, (list, tuple)):
        for v in x:
            _tuyet_doi(v, kq)
    return kq


def bang_kiem_so(su_that: dict) -> list:
    """Bảng số dùng để kiểm lời nói: số của slide cộng giá trị TUYỆT ĐỐI của mọi số âm (lời nói viết "giảm 20", bảng ghi -20)."""
    return [su_that, sorted(_tuyet_doi(su_that))]


def _co(c: dict, **them) -> dict:
    """Phần số dùng chung cho mọi `su_that`: ngày, tháng, số ngày, để lời nói nhắc tới thời gian vẫn hợp lệ."""
    return {"ngay": c["ngay"], "thang": c["thang_so"], "so_ngay_thang": c["so_ngay"], "con_lai": c["con_lai"], **them}


def _slide(id_: str, tieu_de: str, diem: list[str], su_that: dict, loi: str, kpi=None, hinh=None, bang=None) -> dict:
    return {"id": id_, "tieu_de": tieu_de, "kpi": kpi or [], "hinh": hinh, "bang": bang, "diem": [_cat(d) for d in diem], "su_that": su_that, "loi_noi": loi, "nguon_loi": "luat"}


# ------------------------------------------------------------------ các slide
def _tong_quan(c: dict) -> dict:
    sl = c["sl"]
    db, t = sl["du_bao"], sl["tong"]
    mt, luy, dub, nhip = int(db["mt"]), int(db["luy_ke"]), int(db["du_bao"]), int(db["du_bao_nhip"])
    ngay, so_ngay, con = c["ngay"], c["so_ngay"], c["con_lai"]
    pct_dat, pct_tg = bt._pct(luy, mt), bt._pct(ngay, so_ngay)
    hut = max(0, mt - dub)
    can = None if pd.isna(db["can_moi_ngay"]) else int(db["can_moi_ngay"])
    tb = float(db["tb_ngay"])
    ck = int(t["ck_online"] or 0)
    chenh = luy - ck
    tang = None if pd.isna(t["tang_truong"]) else float(t["tang_truong"])
    danh_gia = str(db["danh_gia"])
    mau_dg = {"An toàn": "tot", "Cần tăng tốc": "vang", "Rủi ro": "xau"}.get(danh_gia, "")
    kpi = [{"nhan": "Online luỹ kế", "gia_tri": _so(luy), "phu": f"{pct_dat}% mục tiêu", "mau": ""},
           {"nhan": "Mục tiêu tháng", "gia_tri": _so(mt), "phu": f"đã qua {ngay}/{so_ngay} ngày", "mau": ""},
           {"nhan": "Dự báo cuối tháng", "gia_tri": _so(dub), "phu": f"theo nhịp cuối tháng: {_so(nhip)} · {danh_gia}", "mau": mau_dg},
           {"nhan": "Cần mỗi ngày", "gia_tri": _so(can) if can is not None else "–", "phu": f"hiện {_so(tb, 1)}/ngày · còn {con} ngày", "mau": "xau" if can is not None and can > tb else "tot"},
           {"nhan": "So cùng kỳ tháng trước", "gia_tri": f"{chenh:+d}", "phu": (f"{tang:+.0f}%" if tang is not None else ""), "mau": "tot" if chenh >= 0 else "xau"}]
    diem = [f"Luỹ kế {_so(luy)} online, bằng {pct_dat}% mục tiêu {_so(mt)} khi thời gian đã qua {pct_tg}%.",
            f"Dự báo cuối tháng {_so(dub)} (theo nhịp cuối tháng {_so(nhip)}), " + (f"hụt {_so(hut)} so với mục tiêu" if hut else "đạt mục tiêu") + f"; đánh giá: {danh_gia}.",
            (f"Cần {_so(can)} online mỗi ngày trong {con} ngày còn lại, hiện đang đạt {_so(tb, 1)}/ngày." if can is not None else "Đã hết tháng."),
            f"So với cùng kỳ tháng trước: {chenh:+d} online" + (f" ({tang:+.0f}%)." if tang is not None else ".")]
    if c["tam_tinh"]:
        diem.append("Ngày cuối đang cập nhật nên số còn tạm tính.")
    su_that = _co(c, luy_ke=luy, muc_tieu=mt, pct_dat=pct_dat, pct_thoi_gian=pct_tg, du_bao=dub, du_bao_nhip=nhip, hut=hut, can_moi_ngay=can, tb_ngay=round(tb, 1), cung_ky=ck, chenh=chenh,
                  chenh_tuyet_doi=abs(chenh), tang_truong_pct=tang, danh_gia=danh_gia, so_tam_tinh=c["tam_tinh"])
    loi = (f"Kính chào Ban giám đốc. Đây là báo cáo kinh doanh tính đến ngày {ngay} tháng {c['thang_so']}. Toàn chi nhánh đã có {luy} online, bằng {pct_dat}% mục tiêu {mt}, "
           f"trong khi thời gian đã qua {pct_tg}%. " + (f"Dự báo cuối tháng khoảng {dub} online, hụt {hut} so với mục tiêu, đánh giá mức {danh_gia}. " if hut else f"Dự báo cuối tháng khoảng {dub} online, đạt mục tiêu. ")
           + (f"Để kịp mục tiêu cần {can} online mỗi ngày trong {con} ngày còn lại, hiện đang đạt {_so(tb, 1)}. " if can is not None else "")
           + f"So với cùng kỳ tháng trước, {_doi(chenh)} online" + (f", tương ứng {abs(tang):.0f}%." if tang is not None else "."))
    return _slide("tong_quan", f"Toàn chi nhánh · tới ngày {ngay:02d}/{c['thang_so']:02d}", diem, su_that, loi, kpi=kpi)


def _phong_du_bao(c: dict) -> dict:
    sl = c["sl"]
    d = sl["phong"][sl["phong"]["phong_code"].isin(c["ma_ban_hang"])].dropna(subset=["pct_mt"]).sort_values("pct_mt")
    ten, pct, dg = [str(x) for x in d["phong"]], [float(x) for x in d["pct_mt"]], [str(x) for x in d["danh_gia"]]
    n, rr, tt, at = len(d), dg.count(du_bao.RUI_RO), dg.count(du_bao.TANG_TOC), dg.count(du_bao.AN_TOAN)
    thap = list(zip(ten[:3], [f"{round(p)}%" for p in pct[:3]]))
    cao = list(zip(ten[::-1][:2], [f"{round(p)}%" for p in pct[::-1][:2]]))
    can = bnd._phong_can_chu_y(sl)
    hut = [(str(r["phong"]), int(r["hut"])) for _, r in can[can["hut"] > 0].head(3).iterrows()]
    diem = [f"{rr}/{n} phòng ở mức Rủi ro, {tt} phòng cần tăng tốc, {at} phòng an toàn.", f"Dự báo thấp nhất: {_ds_ten(thap)}." if thap else "",
            f"Cao nhất: {_ds_ten(cao)}." if cao else "", ("Hụt nhiều nhất so với mục tiêu: " + ", ".join(f"{t} (hụt {_so(v)})" for t, v in hut) + ".") if hut else "Không phòng nào hụt so với mục tiêu."]
    su_that = _co(c, so_phong=n, rui_ro=rr, can_tang_toc=tt, an_toan=at, pct_du_bao={t: round(p) for t, p in zip(ten, pct)}, hut_nhieu_nhat={t: v for t, v in hut})
    loi = (f"Về từng phòng bán hàng: có {rr} trên {n} phòng đang ở mức Rủi ro, {tt} phòng cần tăng tốc và {at} phòng an toàn. "
           + (f"Thấp nhất là {_ds_ten([(t, v.replace('%', ' phần trăm')) for t, v in thap])} mục tiêu. " if thap else "")
           + (f"Cao nhất là {_ds_ten([(t, v.replace('%', ' phần trăm')) for t, v in cao])}. " if cao else "")
           + (("Phòng hụt nhiều nhất so với mục tiêu: " + ", ".join(f"{t} hụt {v}" for t, v in hut) + ".") if hut else ""))
    return _slide("phong", "Dự báo cuối tháng của từng phòng", [x for x in diem if x], su_that, loi, hinh=ve.du_bao_theo_phong(ten, pct, dg))


def _cung_ky(c: dict) -> dict:
    sl = c["sl"]
    tq = sl["tq"]
    d = tq[(tq["loai_dong"] == "data") & tq["phong_code"].isin(c["ma_ban_hang"])].copy()
    d["chenh"] = (pd.to_numeric(d["online"], errors="coerce").fillna(0) - pd.to_numeric(d["ck_online"], errors="coerce").fillna(0)).astype(int)
    d = d.sort_values("chenh")
    ten, chenh = [str(x) for x in d["phong"]], [int(x) for x in d["chenh"]]
    giam = [(t, v) for t, v in zip(ten, chenh) if v < 0][:3]
    tang = [(t, v) for t, v in list(zip(ten, chenh))[::-1] if v > 0][:3]
    n_giam, n_tang = sum(1 for v in chenh if v < 0), sum(1 for v in chenh if v > 0)
    tong = sum(chenh)
    diem = [f"{n_tang} phòng tăng, {n_giam} phòng giảm so với cùng kỳ tháng trước; cộng các phòng bán hàng: {tong:+d} online.",
            ("Giảm nhiều nhất: " + ", ".join(f"{t} ({v:+d})" for t, v in giam) + ".") if giam else "Không phòng nào giảm.",
            ("Tăng nhiều nhất: " + ", ".join(f"{t} ({v:+d})" for t, v in tang) + ".") if tang else "Không phòng nào tăng."]
    su_that = _co(c, phong_tang=n_tang, phong_giam=n_giam, tong_chenh=tong, tong_chenh_tuyet_doi=abs(tong), giam_nhieu={t: v for t, v in giam}, tang_nhieu={t: v for t, v in tang},
                  chenh_phong={t: v for t, v in zip(ten, chenh)})
    loi = (f"So với cùng kỳ tháng trước, có {n_tang} phòng tăng và {n_giam} phòng giảm, cộng lại các phòng bán hàng {_doi(tong)} online. "
           + (("Giảm nhiều nhất là " + ", ".join(f"{t} giảm {abs(v)}" for t, v in giam) + ". ") if giam else "")
           + (("Tăng nhiều nhất là " + ", ".join(f"{t} tăng {v}" for t, v in tang) + ".") if tang else ""))
    return _slide("cung_ky", "So với cùng kỳ tháng trước", diem, su_that, loi, hinh=ve.chenh_cung_ky(ten, chenh))


def _nhip(c: dict) -> dict:
    sl = c["sl"]
    thang, ngay, pm = c["thang"], c["ngay"], metrics.prev_month(c["thang"])
    nay_s, truoc_s = metrics.daily_counts(thang, "online").sum(axis=0), metrics.daily_counts(pm, "online").sum(axis=0)
    ngays = list(range(1, ngay + 1))
    nay, truoc = [int(nay_s.get(k, 0)) for k in ngays], [int(truoc_s.get(k, 0)) for k in ngays]
    db = sl["du_bao"]
    can = None if pd.isna(db["can_moi_ngay"]) else float(db["can_moi_ngay"])
    tb7 = round(sum(nay[-7:]) / len(nay[-7:]), 1) if nay else 0.0
    tb7_truoc = round(sum(nay[-14:-7]) / 7, 1) if ngay >= 14 else None
    xet = nay[:-1] if c["tam_tinh"] and len(nay) > 1 else nay                # ngày cuối còn tạm tính thì không coi là "ngày thấp nhất"
    cao_d = max(range(len(xet)), key=lambda i: xet[i]) + 1 if xet else None
    thap_d = min(range(len(xet)), key=lambda i: xet[i]) + 1 if xet else None
    xu_huong = "" if tb7_truoc is None else (" Đang tăng nhịp." if tb7 > tb7_truoc * 1.05 else " Đang chậm nhịp." if tb7 < tb7_truoc * 0.95 else " Nhịp đi ngang.")
    diem = [f"Bình quân cả tháng {_so(db['tb_ngay'], 1)} online mỗi ngày" + (f", cần {_so(can)} để kịp mục tiêu." if can is not None else "."),
            f"7 ngày gần nhất bình quân {_so(tb7, 1)}/ngày" + (f", 7 ngày trước đó {_so(tb7_truoc, 1)}/ngày.{xu_huong}" if tb7_truoc is not None else "."),
            (f"Ngày cao nhất: ngày {cao_d} ({xet[cao_d - 1]} online); thấp nhất: ngày {thap_d} ({xet[thap_d - 1]} online)." if xet else "")]
    su_that = _co(c, tb_ngay=round(float(db["tb_ngay"]), 1), can_moi_ngay=can, tb_7_ngay=tb7, tb_7_ngay_truoc=tb7_truoc, ngay_cao_nhat=cao_d, so_ngay_cao_nhat=xet[cao_d - 1] if xet else None,
                  ngay_thap_nhat=thap_d, so_ngay_thap_nhat=xet[thap_d - 1] if xet else None, theo_ngay={str(k): v for k, v in zip(ngays, nay)})
    loi = (f"Về nhịp bán hàng, bình quân cả tháng là {_so(db['tb_ngay'], 1)} online mỗi ngày" + (f", trong khi cần {_so(can)} mỗi ngày để kịp mục tiêu. " if can is not None else ". ")
           + f"Bảy ngày gần nhất bình quân {_so(tb7, 1)} mỗi ngày" + (f", so với {_so(tb7_truoc, 1)} của bảy ngày trước đó.{xu_huong} " if tb7_truoc is not None else ". ")
           + (f"Ngày cao nhất là ngày {cao_d} với {xet[cao_d - 1]} online, thấp nhất là ngày {thap_d} với {xet[thap_d - 1]} online." if xet else ""))
    return _slide("nhip", "Nhịp online từng ngày", [x for x in diem if x], su_that, loi, hinh=ve.nhip_theo_ngay(ngays, nay, truoc, can, f"Tháng {pm[5:7].lstrip('0')}"))


def _chat_luong(c: dict) -> dict:
    sl = c["sl"]
    t, truoc = sl["tong"], sl["truoc"]
    d = sl["tq"][(sl["tq"]["loai_dong"] == "data") & sl["tq"]["phong_code"].isin(c["ma_ban_hang"])]
    d = d[pd.to_numeric(d["online"], errors="coerce").fillna(0) >= bnd.TOI_THIEU_ONLINE_PHONG]
    ten = [str(x) for x in d["phong"]]
    vvip = [float(x or 0) for x in d["vvip_ty_le"]]
    cam = [bnd._ty_le_camera(o, k) or 0 for o, k in zip(d["online"], d["camera"])]
    v, cm = t["vvip_ty_le"], bnd._ty_le_camera(t["online"], t["camera"])
    vt = None if truoc is None else truoc["vvip_ty_le"]
    ct = None if truoc is None else bnd._ty_le_camera(truoc["online"], truoc["camera"])
    thap = bnd._phong_thap_chat_luong(sl)
    diem = [f"V.VIP chi nhánh {_so(v)}% trên online" + (f", tháng trước cùng kỳ {_so(vt)}%." if vt is not None else "."), f"Camera chi nhánh {cm}% trên online" + (f", tháng trước cùng kỳ {ct}%." if ct is not None else ".")]
    for ten_cs, ds in thap.items():
        if ds:
            diem.append(f"{ten_cs} thấp hơn mức chung từ {bnd.CHENH_CHAT_LUONG} điểm: " + ", ".join(f"{p} {_so(x)}%" for p, x, _ in ds) + ".")
    if not any(thap.values()):
        diem.append(f"Không phòng nào thấp hơn mức chung của chi nhánh quá {bnd.CHENH_CHAT_LUONG} điểm.")
    su_that = _co(c, vvip_chi_nhanh=v, camera_chi_nhanh=cm, vvip_thang_truoc=vt, camera_thang_truoc=ct, chenh_nguong=bnd.CHENH_CHAT_LUONG,
                  phong_thap={k: {p: x for p, x, _ in ds} for k, ds in thap.items() if ds})
    loi = (f"Về chất lượng bán, tỷ lệ V.VIP trên online của chi nhánh là {_so(v)} phần trăm" + (f", cùng kỳ tháng trước là {_so(vt)}" if vt is not None else "")
           + f"; tỷ lệ Camera là {cm} phần trăm" + (f", cùng kỳ tháng trước là {ct}. " if ct is not None else ". ")
           + " ".join(f"{k} thấp ở " + ", ".join(f"{p} {_so(x)} phần trăm" for p, x, _ in ds) + "." for k, ds in thap.items() if ds))
    return _slide("chat_luong", "Chất lượng bán: V.VIP và Camera", diem, su_that, loi, hinh=ve.chat_luong(ten, vvip, cam, None if v is None else float(v), cm))


def _ton(c: dict) -> dict:
    sl = c["sl"]
    tong_lau, theo = bnd._ton_lau_theo_phong(sl)
    tong_ton = int(sl["tong"]["so_ton"] or 0)
    top = [(c["ten_phong"].get(p, p), int(n)) for p, n in theo.head(8).items()]
    top3 = top[:3]
    chia = bt._pct(sum(n for _, n in top3), tong_lau)
    diem = [f"{_so(tong_lau)} hợp đồng chờ online từ {bnd.TON_QUA_NGAY} ngày, trong tổng {_so(tong_ton)} hợp đồng tồn.", ("Nhiều nhất: " + ", ".join(f"{t} ({n})" for t, n in top3) + (f", chiếm {chia}% số này." if chia else ".")) if top3 else ""]
    su_that = _co(c, ton_lau=tong_lau, tong_ton=tong_ton, nguong_ngay=bnd.TON_QUA_NGAY, ton_theo_phong={t: n for t, n in top}, ba_phong_dau_pct=chia)
    loi = (f"Về hợp đồng tồn, hiện có {tong_lau} hợp đồng chờ online từ {bnd.TON_QUA_NGAY} ngày trở lên, trong tổng số {tong_ton} hợp đồng tồn. "
           + (("Nhiều nhất là " + ", ".join(f"{t} {n} hợp đồng" for t, n in top3) + (f", ba phòng này chiếm {chia} phần trăm số hợp đồng tồn lâu." if chia else ".")) if top3 else ""))
    return _slide("ton", "Hợp đồng tồn lâu", [x for x in diem if x], su_that, loi, hinh=ve.ton_lau([t for t, _ in top], [n for _, n in top]) if top else None)


def _tinh(c: dict) -> dict:
    from app.org import loc_chi_nhanh
    from app.ui.pages.phantich_tinh import hinh_tinh
    thang, ngay = c["thang"], c["ngay"]
    tu, den = f"{thang}-01", c["ngay_iso"]
    ck = pt.cung_ky_thang_truoc(thang, ngay)
    scope = loc_chi_nhanh(None, "all", thang)
    bang = pt.bang_tinh(pt.online_theo_tinh(tu, den, scope), pt.online_theo_tinh(*ck, scope))
    bang = bang[bang["online"] > 0]
    tong = int(bang["online"].sum())
    noi = int(bang[bang["noi_tinh"]]["online"].sum())
    ngoai = bang[~bang["noi_tinh"]]
    top_ngoai = [(str(r.tinh), int(r.online)) for r in ngoai.head(3).itertuples()]
    nhieu = [(str(r.tinh), int(r.online), float(r.ty_trong)) for r in bang.head(3).itertuples()]
    tang = bang.sort_values("chenh", ascending=False).head(2)
    giam = bang.sort_values("chenh").head(2)
    tang_l = [(str(r.tinh), int(r.chenh)) for r in tang.itertuples() if r.chenh > 0]
    giam_l = [(str(r.tinh), int(r.chenh)) for r in giam.itertuples() if r.chenh < 0]
    noi_pct = bt._pct(noi, tong) or 0
    diem = [f"{_so(tong)} hợp đồng online luỹ kế; nội tỉnh (Đà Nẵng và Quảng Nam) {noi_pct}%, ngoại tỉnh {100 - noi_pct}% ({len(ngoai)} tỉnh).",
            ("Nhiều nhất: " + ", ".join(f"{t} {n} ({p:.0f}%)" for t, n, p in nhieu) + ".") if nhieu else "",
            ("Ngoại tỉnh nhiều nhất: " + ", ".join(f"{t} ({n})" for t, n in top_ngoai) + ".") if top_ngoai else "",
            ("Tăng nhiều nhất so cùng kỳ: " + ", ".join(f"{t} ({v:+d})" for t, v in tang_l) + ".") if tang_l else "",
            ("Giảm nhiều nhất so cùng kỳ: " + ", ".join(f"{t} ({v:+d})" for t, v in giam_l) + ".") if giam_l else ""]
    su_that = _co(c, tong=tong, noi_tinh_pct=noi_pct, ngoai_tinh_pct=100 - noi_pct, so_tinh_ngoai=len(ngoai), nhieu_nhat={t: n for t, n, _ in nhieu}, ty_trong={t: round(p) for t, _, p in nhieu},
                  ngoai_tinh_nhieu_nhat={t: n for t, n in top_ngoai}, tang_nhieu={t: v for t, v in tang_l}, giam_nhieu={t: v for t, v in giam_l})
    loi = (f"Về địa bàn, luỹ kế có {tong} hợp đồng online, trong đó nội tỉnh Đà Nẵng và Quảng Nam chiếm {noi_pct} phần trăm, ngoại tỉnh {100 - noi_pct} phần trăm với {len(ngoai)} tỉnh. "
           + (("Ngoại tỉnh nhiều nhất là " + ", ".join(f"{t} {n} hợp đồng" for t, n in top_ngoai) + ". ") if top_ngoai else "")
           + (("So với cùng kỳ, tăng nhiều nhất là " + ", ".join(f"{t} tăng {v}" for t, v in tang_l) + ". ") if tang_l else "")
           + (("Giảm nhiều nhất là " + ", ".join(f"{t} giảm {abs(v)}" for t, v in giam_l) + ".") if giam_l else ""))
    hinh = json.loads(hinh_tinh(bang.head(12), f"Tháng {ck[0][5:7].lstrip('0')}").to_json())
    hinh["layout"]["height"] = 420
    return _slide("tinh", "Online theo tỉnh", [x for x in diem if x], su_that, loi, hinh=hinh)


def _nhan_su(c: dict, user) -> dict | None:
    from app import tro_ly_dieu_hanh_quet as q, tro_ly_dieu_hanh_quet_kd as qkd
    from app.tro_ly_dieu_hanh_nd import hien
    ctx = q.ngu_canh()
    ctx.update({"ngay_iso": c["ngay_iso"], "thang": c["thang"], "ngay": c["ngay"]})
    fs = [f for f in qkd.quet_nhan_su(ctx) if f["muc"] != q.THAP]
    if not fs:
        return None
    ten = ctx["ten"]
    theo: dict[str, dict] = {}
    for f in sorted(fs, key=lambda f: (q.HANG_MUC[f["muc"]], -float(f["diem"]))):
        theo.setdefault(f["doi_tuong"], f)
    xep = sorted(theo.values(), key=lambda f: (q.HANG_MUC[f["muc"]], -float(f["diem"])))
    so_nguoi, so_cao = len(theo), sum(1 for f in theo.values() if f["muc"] == q.CAO)
    theo_phong: dict[str, int] = {}
    for f in theo.values():
        theo_phong[f["bang_chung"].get("phong", "")] = theo_phong.get(f["bang_chung"].get("phong", ""), 0) + 1
    nhieu = sorted(theo_phong.items(), key=lambda x: -x[1])[:3]
    dong = []
    for f in xep[:TOI_DA_NHAN_SU]:
        bc, nm = f["bang_chung"], ten.get(f["doi_tuong"], f["doi_tuong"])
        ly_do = hien(f["tieu_de"], ten)
        ly_do = ly_do[len(nm):].strip() if ly_do.startswith(nm) else ly_do
        dong.append([c["ten_phong"].get(bc.get("phong"), bc.get("phong", "")), nm, bc.get("online", ""), bc.get("cung_ky", ""), _cat(ly_do, 90)])
    diem = [f"{so_nguoi} nhân sự cần chú ý, trong đó {so_cao} người ở mức cao.", ("Nhiều nhất ở: " + ", ".join(f"{c['ten_phong'].get(p, p)} ({n})" for p, n in nhieu) + ".") if nhieu else "",
            "Trưởng phòng, người đã nghỉ và acc tạm không được xét; số của họ vẫn nằm trong số phòng."]
    su_that = _co(c, so_nguoi=so_nguoi, so_muc_cao=so_cao, theo_phong={c["ten_phong"].get(p, p): n for p, n in nhieu},
                  nguoi=[{"phong": d[0], "ten": d[1], "online": d[2], "cung_ky": d[3]} for d in dong])
    co_ten = [d for d in dong if not re.fullmatch(r"[\w.]*\d[\w.]*", str(d[1]))] or dong       # acc chưa có họ tên (vd acc là dãy số) thì để sau
    top3 = ", ".join(f"{d[1]} ở {d[0]}" for d in co_ten[:3])
    loi = (f"Về nhân sự, có {so_nguoi} người cần chú ý, trong đó {so_cao} người ở mức cao. "
           + (("Nhiều nhất ở " + ", ".join(f"{c['ten_phong'].get(p, p)} {n} người" for p, n in nhieu) + ". ") if nhieu else "")
           + (f"Cần trao đổi sớm với {top3}." if top3 else ""))
    bang = {"cot": ["Phòng", "Nhân sự", "Online", "Cùng kỳ", "Lý do"], "dong": dong}
    return _slide("nhan_su", "Nhân sự cần chú ý", [x for x in diem if x], su_that, loi, bang=bang)


def _nguyen_nhan(c: dict, user) -> dict | None:
    from app.fox_nguyen_nhan import nguyen_nhan
    can = bnd._phong_can_chu_y(c["sl"])
    can = can[can["hut"] > 0] if len(can) else can
    if can.empty:
        return None
    code, ten = str(can.iloc[0]["phong_code"]), str(can.iloc[0]["phong"])
    van_ban = nguyen_nhan(user, c["ngay_iso"], code)
    dong = [x.strip() for x in van_ban.split("\n")]
    ket_qua = next((x for x in dong if x.startswith("Kết quả:")), "")
    gach = [x.strip()[2:].strip() for x in van_ban.split("\n") if x.startswith("   - ")][:TOI_DA_DONG_NGUYEN_NHAN]
    ket_qua = re.sub(r"\s*Mỗi phần dưới đây[^.]*\.", "", ket_qua)
    diem = ([_cat(ket_qua)] if ket_qua else []) + [_cat(x) for x in gach]
    su_that = _co(c, phong=ten, van_ban_chan_doan=van_ban)
    loi = " ".join(x.rstrip(".") + "." for x in [f"Đi sâu vào {ten}, phòng đang hụt nhiều nhất so với mục tiêu", re.sub(r"\s*=\s*", ", tức ", ket_qua.replace("Kết quả:", "").strip()), *gach[:3]] if x)
    return _slide("nguyen_nhan", f"Vì sao {ten} đang hụt?", diem, su_that, loi)


def _ket_luan(c: dict, nhan_su: dict | None) -> dict:
    sl = c["sl"]
    can = bnd._phong_can_chu_y(sl)
    thap = bnd._phong_thap_chat_luong(sl)
    ton_tong, ton_theo = bnd._ton_lau_theo_phong(sl)
    han = bnd.han_xu_ly(c["ngay_iso"])
    hop = can[can["hut"] > 0].head(bnd.TOI_DA_PHONG_HOP)
    diem, loi, su = [], [], {}
    if len(hop) and c["con_lai"] > 0:
        ds = ", ".join(str(x) for x in hop["phong"])
        hut = int(hop["hut"].sum())
        diem.append(f"Họp nhanh với {ds} để chốt kế hoạch bù {_so(hut)} online.")
        loi.append(f"Thứ nhất, họp nhanh với {ds} để chốt kế hoạch bù {hut} online.")
        su.update(phong_hop=ds, hut_can_bu=hut)
    for ten_cs, ds_ in thap.items():
        if ds_:
            diem.append(f"{ds_[0][0]} nâng {ten_cs} lên từ {_so(ds_[0][2])}% (mức chung của chi nhánh).")
            loi.append(f"Nâng tỷ lệ {ten_cs} của {ds_[0][0]} lên từ {_so(ds_[0][2])} phần trăm, bằng mức chung.")
            su[f"nang_{ten_cs}"] = {ds_[0][0]: round(ds_[0][2])}
    top = [(c["ten_phong"].get(p, p), int(n)) for p, n in ton_theo.head(bnd.TOI_DA_PHONG_TON).items()]
    if top and sum(n for _, n in top) > 0:
        diem.append(f"{', '.join(t for t, _ in top)} xử lý dứt điểm {_so(sum(n for _, n in top))} hợp đồng tồn lâu.")
        loi.append(f"{', '.join(t for t, _ in top)} xử lý dứt điểm {sum(n for _, n in top)} hợp đồng tồn lâu.")
        su.update(ton_xu_ly=sum(n for _, n in top))
    if nhan_su:
        cao, tong = int(nhan_su["su_that"]["so_muc_cao"]), int(nhan_su["su_that"]["so_nguoi"])
        diem.append(f"Trưởng phòng trao đổi trước với {cao} nhân sự ở mức cao (trong {tong} người cần chú ý, xem slide Nhân sự cần chú ý).")
        loi.append(f"Trưởng phòng trao đổi trước với {cao} nhân sự ở mức cao, trong tổng {tong} người cần chú ý.")
        su.update(nhan_su_muc_cao=cao, nhan_su_can_chu_y=tong)
    if not diem:
        diem.append("Chưa có phòng nào cần can thiệp: giữ nhịp và rà hợp đồng tồn mỗi ngày.")
        loi.append("Hiện chưa có phòng nào cần can thiệp, đề nghị giữ nhịp và rà hợp đồng tồn mỗi ngày.")
    diem.append(f"Hạn xử lý nhanh: trước ngày {bnd.ngay_vn(han)}.")
    loi.append(f"Đề nghị hoàn thành trước ngày {han.day} tháng {han.month}.")
    su.update(han_ngay=han.day, han_thang=han.month)
    return _slide("ket_luan", "Kết luận và việc cần làm", diem, _co(c, **su), "Tổng kết lại, việc cần làm. " + " ".join(loi))


# ------------------------------------------------------------------ dựng bài
def dung_bai(user, ngay_iso: str | None = None) -> dict:
    """Bài thuyết trình khối Kinh doanh theo số mới nhất (hoặc `ngay_iso`). Slide nào không dựng được (thiếu nguồn) thì bỏ, không làm hỏng cả bài."""
    c = _ngu_canh(ngay_iso)
    slides = [_tong_quan(c)]
    nhan_su = None
    for ham in (_phong_du_bao, _cung_ky, _nhip, _chat_luong, _ton, _tinh):
        try:
            slides.append(ham(c))
        except Exception:
            continue
    for ten, ham in (("nhan_su", _nhan_su), ("nguyen_nhan", _nguyen_nhan)):
        try:
            s = ham(c, user)
        except Exception:
            s = None
        if s:
            slides.append(s)
            if ten == "nhan_su":
                nhan_su = s
    slides.append(_ket_luan(c, nhan_su))
    ngay = date.fromisoformat(c["ngay_iso"])
    return {"ngay": c["ngay_iso"], "ngay_hien": f"{ngay:%d/%m/%Y}", "tam_tinh": c["tam_tinh"], "slides": slides, "dung_ai": False, "ly_do_luat": "", "tao_luc": datetime.now().isoformat(timespec="seconds")}
