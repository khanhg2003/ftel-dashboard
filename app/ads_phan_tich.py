"""Ads IBB7 - phần phân tích trên số đã có: nhận định hiệu quả page, kiểm tra dữ liệu thiếu / lạ, chi tiết một page
(như trang tính của sheet), chi tiết một sale, báo cáo gửi bot Telegram, tên page rút gọn cho biểu đồ.
Số gốc và quy tắc chia tiền ở app/ads.py."""
from __future__ import annotations

import calendar
from datetime import date, timedelta

import pandas as pd

from app.ads import (CHUA_PHAN_CONG, CONG_TY, NGUONG_TOT, TOI_DA_PIC, _q, _tien, cuoi_tu_bang,
                     ds_page, ds_pic, ngay_cuoi_chi, nhom_hieu_qua, phan_bo, phan_chia, theo_ngay, theo_page,
                     tien_tong_thang, ty_gia)
from app.bo_nho import nho


def bao_cao_bot(tu: date, den: date) -> dict:
    """Báo cáo gửi về Telegram (thay Apps Script đọc sheet): lead / PTTB / chi tiêu từng page, page đang chạy chưa có số."""
    tp = theo_page(tu, den)
    co_so = tp[(tp.lead > 0) | (tp.pttb > 0)].sort_values(["pttb", "lead"], ascending=False)

    def so(x):
        return f"{x:,.2f}".rstrip("0").rstrip(".")

    dong = []
    for r in co_so.itertuples():
        t = f"📌 {r.ten}: {int(r.lead)} leads | {int(r.pttb)} PTTB"
        if r.chi_tieu > 0:
            t += f" | {so(r.chi_tieu)}$" + (f" ({so(r.cp_pttb)}$/PTTB)" if r.pttb else "")
        dong.append(t)
    chua = tp[(tp.lead == 0) & (tp.pttb == 0) & (tp.tinh_trang == "Đang chạy")].ten.tolist()
    ngay = tu.strftime("%d/%m/%Y") if tu == den else f"{tu:%d/%m/%Y} - {den:%d/%m/%Y}"
    chi = float(tp.chi_tieu.sum())
    return {"date": ngay, "details_text": "\n".join(dong) or "Chưa có lead / PTTB nào.",
            "total_leads": int(tp.lead.sum()), "total_pttb": int(tp.pttb.sum()), "total_spend": round(chi, 2),
            "ineffective_pages": chua,
            "ineffective_pages_text": ("\n\n⚠️ Page chưa hiệu quả: " + ", ".join(chua)) if chua
            else "\n\n✅ Tất cả page đang chạy đều có hiệu quả!"}


def chi_tiet_page(page_id: int, tu: date, den: date) -> dict:
    """Từng camp từng ngày, ngày tăng dần như trang tính của sheet: camp, tình trạng, ngày, chi tiêu, tin nhắn,
    số điện thoại, PTTB (ghi ở dòng đầu của ngày), PIC 1-3, tiền mỗi người. Kèm tổng tiền từng sale của page."""
    page_id = int(page_id)
    camp = _q("""SELECT ngay, camp, tinh_trang, chi_tieu, tin_nhan FROM ads_ngay
                 WHERE page_id = :p AND ngay >= :tu AND ngay <= :den ORDER BY ngay, camp""", p=page_id, tu=tu, den=den)
    ld = _q("""SELECT ngay, SUM(lead) AS lead, SUM(pttb) AS pttb FROM ads_lead
               WHERE page_id = :p AND ngay >= :tu AND ngay <= :den GROUP BY ngay""", p=page_id, tu=tu, den=den)
    for x in (camp, ld):
        x["ngay"] = pd.to_datetime(x["ngay"]).dt.date
    pg = ds_page().set_index("id")
    loai = pg.loai.get(page_id)
    pics = ds_pic()
    lead = {d: (float(a), float(b)) for d, a, b in zip(ld.ngay, ld["lead"], ld.pttb)}
    rows, so_pic = [], 1 if loai == "cong_ty" else 0
    for d in sorted(set(camp.ngay) | set(lead)):
        pc = [] if loai == "cong_ty" else phan_chia(pics, page_id, d)
        so_pic = max(so_pic, len(pc))
        deu = len({round(t, 3) for _, t in pc}) <= 1
        cs = camp[camp.ngay == d]
        ds_dong = list(cs.itertuples()) or [None]
        for j, r in enumerate(ds_dong):
            chi = float(r.chi_tieu) if r is not None else 0.0
            dong = {"ngay": d.strftime("%d/%m/%Y"), "camp": r.camp if r is not None else "",
                    "tinh_trang": (r.tinh_trang or "") if r is not None else "",
                    "chi_tieu": round(chi, 2) if r is not None else None,
                    "tin_nhan": int(r.tin_nhan or 0) if r is not None else None,
                    "lead": (lead.get(d, (0, 0))[0] or None) if j == 0 else None,
                    "pttb": (lead.get(d, (0, 0))[1] or None) if j == 0 else None}
            for k, (sale, _t) in enumerate(pc[:TOI_DA_PIC], start=1):
                dong[f"pic{k}"] = sale
            if loai == "cong_ty":
                dong["pic1"] = CONG_TY
            if r is not None and pc:
                dong["tien_nguoi"] = _tien(chi / len(pc)) if deu else \
                    " · ".join(f"{s_} {_tien(chi * t)}" for s_, t in pc)
            rows.append(dong)
    pb = phan_bo(tu, den)
    pb = pb[pb.page_id == page_id] if len(pb) else pb
    tong_sale = [(s_, round(float(v), 2)) for s_, v in
                 pb.groupby("sale").chi_tieu.sum().sort_values(ascending=False).items()] if len(pb) else []
    t = {"chi_tieu": float(camp.chi_tieu.sum()), "tin_nhan": float(camp.tin_nhan.sum()),
         "lead": float(ld["lead"].sum()), "pttb": float(ld.pttb.sum())}
    info = pg.loc[page_id] if page_id in pg.index else None
    return {"rows": rows, "so_pic": so_pic, "tong_sale": tong_sale, "tong": t,
            "ten": info.ten if info is not None else "", "ma": info.ma if info is not None else "",
            "link": (info.link if isinstance(info.link, str) else None) if info is not None else None,
            "tinh_trang": info.tinh_trang if info is not None else None}


@nho("ads")
def nhan_dinh(tu: date, den: date) -> dict:
    """Nhận định page cho quản lý: nhóm hiệu quả, xu hướng 7 ngày, điểm nghẽn phễu (tin nhắn → số → PTTB), page chạy
    nhiều ngày liền chưa ra PTTB, gợi ý dời ngân sách. Chỉ tính tới ngày đã có chi tiêu (chi tiêu về trễ 1 ngày) để
    tiền và PTTB cùng khoảng."""
    cuoi = ngay_cuoi_chi(tu, den) or den
    tp = theo_page(tu, cuoi)
    tp = tp[(tp.chi_tieu > 0) | (tp.pttb > 0)].copy()
    rong = {"den": cuoi, "page": pd.DataFrame(), "the": [], "xu_huong": pd.DataFrame(), "pheu": pd.DataFrame(),
            "chuoi": pd.DataFrame(), "cp_tb": None, "tl_so": None, "tl_chot": None}
    if tp.empty:
        return rong
    tp["nhom"] = [nhom_hieu_qua(c, p) for c, p in zip(tp.chi_tieu, tp.pttb)]
    tong_chi, tong_pttb = float(tp.chi_tieu.sum()), float(tp.pttb.sum())
    tp["ty_trong_chi"] = (tp.chi_tieu / tong_chi * 100).round(1) if tong_chi else 0.0
    tp["ty_trong_pttb"] = (tp.pttb / tong_pttb * 100).round(1) if tong_pttb else 0.0
    cp_tb = tong_chi / tong_pttb if tong_pttb else None

    # xu hướng: 7 ngày gần nhất so với 7 ngày trước đó
    a = cuoi - timedelta(days=6)
    df = theo_ngay(cuoi - timedelta(days=13), cuoi)
    xu = pd.DataFrame()
    if len(df):
        df["ky"] = ["nay" if x >= a else "truoc" for x in df.ngay]
        g = df.groupby(["page_id", "ky"])[["chi_tieu", "pttb", "lead"]].sum().unstack("ky").fillna(0)
        g.columns = [f"{c}_{k}" for c, k in g.columns]
        for c in ("chi_tieu_nay", "chi_tieu_truoc", "pttb_nay", "pttb_truoc", "lead_nay", "lead_truoc"):
            if c not in g:
                g[c] = 0.0
        g["cp_nay"] = (g.chi_tieu_nay / g.pttb_nay.where(g.pttb_nay > 0)).round(2)
        g["cp_truoc"] = (g.chi_tieu_truoc / g.pttb_truoc.where(g.pttb_truoc > 0)).round(2)
        g["doi_cp"] = ((g.cp_nay - g.cp_truoc) / g.cp_truoc * 100).round(0)
        g["ten"] = ds_page().set_index("id").ten.reindex(g.index).values
        xu = g[(g.chi_tieu_nay >= 5) | (g.chi_tieu_truoc >= 5)].reset_index()

    # phễu: tin nhắn -> số điện thoại -> PTTB
    ph = tp[["page_id", "ten", "tin_nhan", "lead", "pttb", "chi_tieu"]].copy()
    ph["tl_so"] = (ph.lead / ph.tin_nhan.where(ph.tin_nhan > 0) * 100).round(0)
    ph["tl_chot"] = (ph.pttb / ph.lead.where(ph.lead > 0) * 100).round(0)
    tong_tn, tong_lead = float(ph.tin_nhan.sum()), float(ph.lead.sum())
    tl_so = tong_lead / tong_tn * 100 if tong_tn else None
    tl_chot = tong_pttb / tong_lead * 100 if tong_lead else None

    def van_de(r):
        if tl_so and r.tin_nhan >= 20 and (0 if pd.isna(r.tl_so) else r.tl_so) < tl_so * 0.5:
            return "Nhiều tin nhắn, ít số điện thoại"
        if tl_chot and r.lead >= 5 and (0 if pd.isna(r.tl_chot) else r.tl_chot) < tl_chot * 0.5:
            return "Có số nhưng chốt được ít"
        return ""
    ph["van_de"] = [van_de(r) for r in ph.itertuples()]

    # chuỗi ngày liền (tính lùi từ ngày cuối) có chi tiêu mà chưa ra PTTB
    d30 = theo_ngay(max(tu, cuoi - timedelta(days=30)), cuoi)
    chuoi = []
    if len(d30):
        for pid, g in d30.groupby("page_id"):
            g = g.groupby("ngay").agg(chi_tieu=("chi_tieu", "sum"), pttb=("pttb", "sum"), ten=("ten", "first"))
            n, tien, d = 0, 0.0, cuoi
            while d in g.index and g.loc[d, "chi_tieu"] > 0 and g.loc[d, "pttb"] == 0:
                n, tien, d = n + 1, tien + float(g.loc[d, "chi_tieu"]), d - timedelta(days=1)
            if n >= 3:
                chuoi.append({"page_id": pid, "ten": g.ten.iloc[0], "so_ngay": n, "tien": round(tien, 2)})
    chuoi = pd.DataFrame(chuoi, columns=["page_id", "ten", "so_ngay", "tien"]).sort_values("tien", ascending=False)

    # thẻ nhận định: mỗi thẻ = con số chính + biểu đồ nhỏ + một câu việc cần làm
    the = []
    kem, tot = tp[tp.nhom == "Kém"], tp[tp.nhom == "Hiệu quả cao"]

    def bar(df, cot, chu, vach=None, ten_vach=None, mau=None):
        return {"kieu": "bar", "nhan": ten_gon_ds(df.ten), "gia_tri": [float(x) for x in df[cot]],
                "chu": list(chu), "vach": vach, "ten_vach": ten_vach, "mau": mau}

    if len(kem):
        ct = kem.chi_tieu.sum() / tong_chi * 100
        pt = kem.pttb.sum() / tong_pttb * 100 if tong_pttb else 0
        x = kem.assign(_cp=kem.cp_pttb.fillna(kem.chi_tieu)).nlargest(5, "chi_tieu")
        the.append({"muc": "bad", "tieu_de": f"{len(kem)} page chi phí/PTTB cao",
                    "so": f"{ct:.0f}% ngân sách → {pt:.0f}% PTTB",
                    "bd": bar(x, "_cp", [f"{_tien(c)}$/PTTB" if p else f"{_tien(t)}$, chưa có PTTB"
                                         for c, p, t in zip(x.cp_pttb, x.pttb, x.chi_tieu)],
                              NGUONG_TOT, f"mức tốt {NGUONG_TOT:.0f}$", "#D64534"),
                    "noi_dung": "Xem lại nội dung camp, tệp khách; không cải thiện sau 3-5 ngày thì giảm ngân sách."})
    if len(chuoi):
        x = chuoi.head(5)
        the.append({"muc": "bad", "tieu_de": "Chạy liền nhiều ngày chưa ra PTTB",
                    "so": f"{len(chuoi)} page · {_tien(chuoi.tien.sum())}$ chưa ra PTTB",
                    "bd": bar(x, "so_ngay", [f"{n} ngày · {_tien(t)}$" for n, t in zip(x.so_ngay, x.tien)],
                              mau="#D64534"),
                    "noi_dung": "Kiểm tra camp có đúng tệp khách, tin nhắn có được trả lời kịp; cân nhắc tạm dừng."})
    if len(xu):
        xau = xu[(xu.doi_cp >= 30) & (xu.pttb_nay > 0) & (xu.pttb_truoc >= 2)].sort_values("doi_cp", ascending=False)
        tot_len = xu[(xu.doi_cp <= -30) & (xu.pttb_nay >= 2)].sort_values("doi_cp")
        if len(xau):
            x = xau.head(4)
            the.append({"muc": "warn", "tieu_de": "Chi phí/PTTB tăng mạnh (7 ngày gần nhất)",
                        "so": f"{len(xau)} page đắt lên từ 30%",
                        "bd": {"kieu": "doi", "nhan": ten_gon_ds(x.ten), "truoc": list(x.cp_truoc),
                               "sau": list(x.cp_nay), "xau": True},
                        "noi_dung": "Thường do quảng cáo cũ đã mỏi hoặc tệp khách bão hoà: đổi hình / nội dung mới."})
        if len(tot_len):
            x = tot_len.head(4)
            the.append({"muc": "ok", "tieu_de": "Đang tốt lên so với 7 ngày trước",
                        "so": f"{len(tot_len)} page rẻ đi từ 30%",
                        "bd": {"kieu": "doi", "nhan": ten_gon_ds(x.ten), "truoc": list(x.cp_truoc),
                               "sau": list(x.cp_nay), "xau": False},
                        "noi_dung": "Ghi lại camp / nội dung đang chạy ở các page này để nhân rộng."})
    so = ph[ph.van_de == "Nhiều tin nhắn, ít số điện thoại"]
    chot = ph[ph.van_de == "Có số nhưng chốt được ít"]
    if len(so):
        x = so.head(5)
        the.append({"muc": "warn", "tieu_de": "Nhiều tin nhắn nhưng ít xin được số",
                    "so": f"{len(so)} page dưới nửa mức chung {tl_so:.0f}%",
                    "bd": bar(x, "tl_so", [f"{v:.0f}% ({int(t)} tin → {int(l)} số)"
                                           for v, t, l in zip(x.tl_so.fillna(0), x.tin_nhan, x.lead)],
                              tl_so, f"mức chung {tl_so:.0f}%", "#E3A008"),
                    "noi_dung": "Xem lại kịch bản trả lời và tốc độ phản hồi tin nhắn."})
    if len(chot):
        x = chot.head(5)
        the.append({"muc": "warn", "tieu_de": "Có số điện thoại nhưng chốt PTTB thấp",
                    "so": f"{len(chot)} page dưới nửa mức chung {tl_chot:.0f}%",
                    "bd": bar(x, "tl_chot", [f"{v:.0f}% ({int(l)} số → {int(p)} PTTB)"
                                             for v, l, p in zip(x.tl_chot.fillna(0), x.lead, x.pttb)],
                              tl_chot, f"mức chung {tl_chot:.0f}%", "#E3A008"),
                    "noi_dung": "Sale gọi lại sớm trong ngày, bám khách chưa chốt."})
    if len(tot):
        x = tot.nsmallest(5, "cp_pttb")
        the.append({"muc": "ok", "tieu_de": f"{len(tot)} page hiệu quả cao",
                    "so": f"≤ {NGUONG_TOT:.0f}$/PTTB · {tot.pttb.sum() / tong_pttb * 100:.0f}% tổng PTTB"
                    if tong_pttb else f"≤ {NGUONG_TOT:.0f}$/PTTB",
                    "bd": bar(x, "cp_pttb", [f"{_tien(c)}$/PTTB · {int(p)} PTTB" for c, p in zip(x.cp_pttb, x.pttb)],
                              NGUONG_TOT, f"mức tốt {NGUONG_TOT:.0f}$", "#1E9E5A"),
                    "noi_dung": "Tăng ngân sách từ từ (10-20% mỗi lần), theo dõi chi phí/PTTB có giữ được không."})
    if len(kem) and len(tot) and tot.pttb.sum():
        ngay_chay = max((cuoi - tu).days + 1, 1)
        so_ngay_thang = calendar.monthrange(tu.year, tu.month)[1]
        doi = kem.chi_tieu.sum() / ngay_chay * 0.3
        cp_tot = tot.chi_tieu.sum() / tot.pttb.sum()
        cp_kem = kem.chi_tieu.sum() / kem.pttb.sum() if kem.pttb.sum() else None
        them = (doi / cp_tot - (doi / cp_kem if cp_kem else 0)) * so_ngay_thang
        hien = tong_pttb / ngay_chay * so_ngay_thang
        if them > 0:
            the.append({"muc": "info", "tieu_de": "Gợi ý dời ngân sách",
                        "so": f"+{them:.0f} PTTB/tháng (ước tính)",
                        "bd": {"kieu": "cot", "nhan": ["Giữ như hiện tại", "Dời 30% nhóm Kém"],
                               "gia_tri": [round(hien), round(hien + them)],
                               "chu": [f"{hien:.0f} PTTB", f"{hien + them:.0f} PTTB"]},
                        "noi_dung": f"Chuyển khoảng {_tien(doi)}$/ngày từ nhóm Kém sang nhóm hiệu quả cao (đang "
                                    f"{_tien(cp_tot)}$/PTTB). Hiệu quả thường giảm dần khi tăng ngân sách."})
    return {**rong, "page": tp, "the": the, "xu_huong": xu, "pheu": ph, "chuoi": chuoi,
            "cp_tb": cp_tb, "tl_so": tl_so, "tl_chot": tl_chot}


BO_DAU_TEN = ("LẮP MẠNG WIFI FPT ", "LẮP MẠNG WIFI ", "LẮP WIFI FPT ", "LẮP WIFI ", "LẮP ĐẶT WIFI ", "LẮP INTERNET ",
              "LẮP MẠNG FPT ", "FPT TELECOM - ", "FPT TELECOM ", "PAGE ")


def ten_gon(ten, toi_da: int = 24) -> str:
    """Tên ngắn cho biểu đồ: bỏ tiền tố quảng cáo ('Lắp WIFI FPT Kon Tum' -> 'Kon Tum'), cắt nếu còn dài."""
    s = str(ten or "").strip()
    for d in BO_DAU_TEN:
        if s.upper().startswith(d) and len(s) > len(d) + 2:
            s = s[len(d):]
            break
    return s if len(s) <= toi_da else s[:toi_da - 1].rstrip() + "…"


def ten_gon_ds(ds) -> list[str]:
    """Tên ngắn cho biểu đồ. Chỉ rút gọn khi tên ngắn không trùng với page nào khác (VD đã có page 'Huế' thì 'Lắp Mạng
    WIFI Huế' giữ nguyên) - tránh gộp nhầm hai page vào một thanh hoặc đọc nhầm page."""
    ds = [str(x or "") for x in ds]
    tat_ca = [str(x) for x in ds_page().ten] + ds
    gon_all = {}
    for x in dict.fromkeys(tat_ca):
        gon_all.setdefault(ten_gon(x).upper(), set()).add(x)
    out = []
    for x in ds:
        g = ten_gon(x)
        out.append(g if len(gon_all[g.upper()]) == 1 else (x if len(x) <= 40 else x[:39] + "…"))
    return out


def kiem_tra(tu: date, den: date, hom_nay: date) -> list[tuple[str, str]]:
    """Những chỗ số liệu có thể thiếu / sai để người quản trị xử lý: [(mức 'bad' | 'warn' | 'info', câu)]."""
    ds = []
    df = theo_ngay(tu, den)
    cuoi = cuoi_tu_bang(df)
    hom_qua = hom_nay - timedelta(days=1)
    if tu <= hom_qua <= den and (cuoi is None or cuoi < hom_qua - timedelta(days=1)):
        ds.append(("bad", (f"Chi tiêu mới có đến {cuoi:%d/%m}" if cuoi else "Tháng này chưa có chi tiêu nào")
                   + " - kiểm tra workflow n8n (bình thường 7h sáng đã có số của hôm qua)."))
    if cuoi is not None:
        gan = df[(df.ngay > cuoi - timedelta(days=3)) & (df.ngay < cuoi) & (df.chi_tieu > 0)]
        co_cuoi = set(df[(df.ngay == cuoi) & (df.chi_tieu > 0)].page_id)
        thieu = gan[~gan.page_id.isin(co_cuoi) & (gan.tinh_trang == "Đang chạy")].ten.dropna().unique().tolist()
        som = df[(df.ngay > cuoi) & (df.chi_tieu > 0)]
        if len(som):
            ds.append(("info", f"{', '.join(sorted(som.ten.dropna().unique()))} đã có chi tiêu sau {cuoi:%d/%m} (nhập tay"
                               f" / gửi sớm) - các page khác chưa có nên số chung vẫn tính tới {cuoi:%d/%m}."))
        if thieu:
            ds.append(("warn", f"{len(thieu)} page đang chạy mà ngày {cuoi:%d/%m} không có chi tiêu: {', '.join(thieu)} - "
                               "đã tắt camp thì đổi tình trạng page, còn chạy thì kiểm tra n8n."))
    pb = phan_bo(tu, den)
    if len(pb):
        cpc = pb[pb.sale == CHUA_PHAN_CONG]
        if len(cpc) and cpc.chi_tieu.sum() > 0:
            ten = ds_page().set_index("id").ten
            ds.append(("warn", f"{_tien(cpc.chi_tieu.sum())}$ chưa chia cho sale nào (page chưa khai người chạy: "
                               f"{', '.join(sorted({str(ten.get(i, i)) for i in cpc.page_id}))}) - khai ở Cấu hình → "
                               "Người chạy page."))
    if len(df):
        g = df.groupby(["page_id", "ten"])[["chi_tieu", "lead", "pttb"]].sum().reset_index()
        la = g[(g.chi_tieu == 0) & ((g.lead > 0) | (g.pttb > 0))]
        if len(la):
            ds.append(("warn", f"Có lead / PTTB nhưng cả tháng không có chi tiêu: {', '.join(la.ten.astype(str))} - "
                               "thường do gõ sai tên page khi báo qua bot (app tự tạo page mới). Xoá dòng sai ở Nhật ký."))
        vuot = g[g.pttb > g.lead]
        if len(vuot):
            ds.append(("info", f"PTTB nhiều hơn số điện thoại ở: {', '.join(vuot.ten.astype(str))} - kiểm tra lại lần báo."))
    tay = tien_tong_thang(tu, den)
    if len(tay):
        ds.append(("info", f"{_tien(tay.chi_tieu.sum())}$ là tiền nhập tay tổng tháng ({', '.join(tay.ten.astype(str))})"
                           " - không có số từng ngày nên không vẽ vào biểu đồ theo ngày và không tính vào dự kiến."))
    thang = f"{tu.year}-{tu.month:02d}"
    if _q("SELECT COUNT(*) AS n FROM ads_thang WHERE thang = :t", t=thang).n.iloc[0] == 0:
        ds.append(("info", f"Chưa lưu tỷ giá tháng {tu.month:02d}/{tu.year} - VNĐ đang đổi theo {ty_gia(thang):,.0f}"
                   .replace(",", ".") + " (tab Theo sale → Lưu tỷ giá)."))
    return ds


def chi_tiet_sale(sale: str, tu: date, den: date) -> pd.DataFrame:
    """Các page một sale được chia tiền: số ngày chạy, tiền được chia, phần của sale trong tiền page, người chạy cùng."""
    pb = phan_bo(tu, den)
    if pb.empty:
        return pd.DataFrame()
    x = pb[pb.sale == sale]
    if x.empty:
        return pd.DataFrame()
    tong_page = pb.groupby("page_id").chi_tieu.sum()
    co = x[x.chi_tieu > 0]
    g = co.groupby("page_id").agg(chi_tieu=("chi_tieu", "sum"), so_ngay=("ngay", "nunique"),
                                  tu=("ngay", "min"), den=("ngay", "max")).reset_index()
    if g.empty:
        return pd.DataFrame()
    g["phan"] = (g.chi_tieu / g.page_id.map(tong_page) * 100).round(0)
    cung = pb[pb.page_id.isin(g.page_id) & (pb.sale != sale)].groupby("page_id").sale \
        .agg(lambda v: ", ".join(sorted(set(v))))
    g["cung"] = g.page_id.map(cung).fillna("")
    g["ten"] = g.page_id.map(ds_page().set_index("id").ten)
    g["tu"] = [f"{d:%d/%m}" for d in g.tu]
    g["den"] = [f"{d:%d/%m}" for d in g.den]
    return g.sort_values("chi_tieu", ascending=False).reset_index(drop=True)
