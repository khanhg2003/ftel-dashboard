"""Phân loại khách hàng từ dữ liệu ghép ba khối: mỗi hợp đồng được xếp vào (không loại trừ nhau) ba nhóm cần hành động.

1. Chăm sóc chủ động (nguy cơ rời mạng): cộng điểm theo tín hiệu của cả ba khối - điểm nguy cơ và ý rời (DVKH), khiếu nại (DVKH),
   sự cố lặp (Kỹ thuật), nợ quá hạn và thói quen trả trễ (cước). Đây là điểm theo LUẬT để xếp thứ tự gọi, KHÔNG phải xác suất rời mạng.
2. Nhắc cước: kỳ cước chưa thanh toán xếp theo hạn (quá hạn, trong 7 ngày, trong 30 ngày), kỳ kế tiếp dự kiến, và hợp đồng nằm trong
   danh sách nợ của DVKH mà chưa có kỳ cước để đối chiếu.
3. Bán thêm: khách đang ổn định (không nợ, không khiếu nại, không sự cố lặp, không thuộc nhóm 1) mà còn thiếu dịch vụ - gợi ý đúng dịch vụ còn thiếu.

Chỉ ĐỌC nguồn; không ghi gì, không gửi tin. Không có tên khách hàng. Ngày "hôm nay" là ngày tham chiếu của nguồn (bộ minh hoạ: meta.json).
"""
from __future__ import annotations

import pandas as pd

from app.bo_nho import nho
from app.config import rules_config
from app.lien_khoi import luat, nguon
from app.lien_khoi.su_kien import chuan_hd

CAO, TB, THAP = "Cao", "Trung bình", "Thấp"
MAC_DINH = {"so_ngay_xet": 90, "diem_rm_cao": 800, "diem_rm_vua": 600, "nguong_cao": 60, "nguong_nhom": 30, "nhac_truoc_ngay": 7, "tam_nhin_ngay": 30}
DIEM = {"rm_cao": 40, "rm_vua": 20, "y_roi": 30, "khieu_nai": 10, "khieu_nai_toi_da": 20, "su_co_lap": 15, "no_qua_han": 15, "hay_tra_tre": 10}
NHOM_CUOC = ["Quá hạn", "Đến hạn trong 7 ngày", "Đến hạn trong 30 ngày", "Kỳ kế tiếp (dự kiến)", "Trong danh sách nợ, chưa có kỳ cước"]
GOI_Y = ["FPT Play", "Camera", "Nâng gói lên Sky", "Chuyển sang trả trước"]
COT_RM = ["so_hd", "muc", "diem", "diem_rm", "ly_do", "de_xuat", "phu_trach", "sale", "goi", "cuoc_thang", "tham_nien", "dang_no"]
COT_CUOC = ["so_hd", "nhom", "han_tt", "con_ngay", "so_tien", "so_ky", "ky_tre", "hinh_thuc_tt", "de_xuat", "phu_trach", "sale", "goi"]
COT_BAN = ["so_hd", "muc", "goi_y", "so_goi_y", "ly_do", "de_xuat", "dich_vu", "goi", "cuoc_thang", "tham_nien", "sale"]


def cau_hinh() -> dict:
    return {**MAC_DINH, **{k: v for k, v in (rules_config().get("phan_loai") or {}).items() if k in MAC_DINH}}


def _tien_dong(s: pd.Series) -> pd.Series:
    """Cước trong file bán hàng lúc ghi nghìn đồng, lúc ghi đồng: dưới 5.000 coi là nghìn đồng (cùng quy ước với hồ sơ hợp đồng)."""
    x = pd.to_numeric(s, errors="coerce")
    return x.where(x >= 5000, x * 1000).where(x > 0)


def _rong(cot: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=cot)


def _dac_diem(c: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp] | None:
    """Bảng một dòng một hợp đồng với các đặc điểm ghép từ ba khối + bảng kỳ cước đã chuẩn hoá + ngày tham chiếu."""
    kd = nguon.kd().copy()
    if kd.empty:
        return None
    kd["so_hd"] = chuan_hd(kd["so_hd"])
    kd = kd[kd["so_hd"].ne("")].drop_duplicates("so_hd", keep="last").set_index("so_hd")
    hom_nay = pd.Timestamp(nguon.ngay_tham_chieu() or luat.ngay_tham_chieu_kd(kd.reset_index())).normalize()
    tu = hom_nay - pd.Timedelta(days=int(c["so_ngay_xet"]))
    bd, cd, kt, dv, cu = nguon.sr_bi_dong(), nguon.sr_chu_dong(), nguon.kt(), nguon.dich_vu_kem(), nguon.cuoc()
    for d in (bd, cd, kt, dv):
        if len(d):
            d["so_hd"] = chuan_hd(d["so_hd"])
    b = pd.DataFrame(index=kd.index)
    b["sale"] = kd["sale"].fillna("").astype(str)
    b["goi"] = kd["goi"].fillna("").astype(str)
    b["cuoc_thang"] = _tien_dong(kd["cuoc_thang"]) if "cuoc_thang" in kd else float("nan")
    b["tra_truoc_thang"] = pd.to_numeric(kd["so_thang_tra_truoc"], errors="coerce").fillna(0) if "so_thang_tra_truoc" in kd else 0
    b["hinh_thuc_tt"] = kd["hinh_thuc_tt"].fillna("").astype(str) if "hinh_thuc_tt" in kd else ""
    da_huy = kd["ngay_huy"].notna() | kd["tinh_trang"].eq("Đã chấm dứt hợp đồng")
    b["hoat_dong"] = kd["ngay_online"].notna() & ~da_huy
    b["da_huy"] = da_huy
    b["tham_nien"] = ((hom_nay - kd["ngay_online"]).dt.days // 30).where(b["hoat_dong"])
    # DVKH
    b["diem_rm"] = float("nan")
    if len(cd):
        co_diem = cd[cd["diem_rm"].fillna(-1) >= 0].sort_values("tg_do")
        b["diem_rm"] = co_diem.groupby("so_hd")["diem_rm"].last().reindex(b.index)
    gan = bd[bd["tg_yc"] >= tu] if len(bd) else bd
    b["khieu_nai"] = (gan[gan["loai_yc"].eq("Khiếu nại, phàn nàn")].groupby("so_hd").size().reindex(b.index).fillna(0) if len(gan) else 0)
    b["yc_roi"] = b.index.isin(set(gan.loc[gan["loai_yc"].isin(("Thanh lý", "Tạm ngưng")), "so_hd"])) if len(gan) else False
    viec = luat.danh_sach_viec()
    y_roi = viec[viec["luat"] == "co_y_roi"] if len(viec) else viec
    b["y_roi"] = b.index.isin(set(y_roi["so_hd"])) if len(y_roi) else False
    b["phu_trach"] = pd.Series(luat.nguoi_dvkh(bd, cd)).reindex(b.index).fillna("").astype(str) if len(bd) or len(cd) else ""
    # Kỹ thuật
    b["su_co"] = 0
    if len(kt):
        ck = kt[(kt["loai"] == "checklist") & (pd.to_datetime(kt["thoi_diem"], errors="coerce") >= tu)]
        if len(ck):
            dem = pd.concat([ck.groupby("so_hd").size(), pd.to_numeric(ck["so_lan"], errors="coerce").groupby(ck["so_hd"]).max()], axis=1).max(axis=1)
            b["su_co"] = dem.reindex(b.index).fillna(0).astype(int)
    # dịch vụ kèm
    for cot, nhom in (("co_play", "FPT Play"), ("co_camera", "Camera")):
        b[cot] = b.index.isin(set(dv.loc[dv["nhom"].eq(nhom), "so_hd"])) if len(dv) else False
    # cước
    cu = cu[cu["so_hd"].ne("") & cu["han_tt"].notna()].copy()
    cu["chua_tt"] = cu["ngay_tt"].isna()
    cu["qua_han"] = cu["chua_tt"] & (cu["han_tt"] < hom_nay)
    cu["tre"] = ~cu["chua_tt"] & (cu["ngay_tt"].dt.normalize() > cu["han_tt"])
    nam = cu[cu["han_tt"] >= hom_nay - pd.DateOffset(months=12)]
    g = lambda d: d.groupby("so_hd").size().reindex(b.index).fillna(0).astype(int) if len(d) else 0
    b["ky_tre"], b["ky_dung"] = g(nam[nam["tre"]]), g(nam[~nam["chua_tt"] & ~nam["tre"]])
    qh = cu[cu["qua_han"]]
    b["tien_qua_han"] = qh.groupby("so_hd")["so_tien"].sum().reindex(b.index).fillna(0) if len(qh) else 0
    b["qua_han_ngay"] = ((hom_nay - qh.groupby("so_hd")["han_tt"].min()).dt.days.reindex(b.index).fillna(0).astype(int)) if len(qh) else 0
    b["trong_ds_no"] = b.index.isin(luat.no_cuoc_dvkh(cd))
    b["dang_no"] = b["trong_ds_no"] | (b["qua_han_ngay"] > 0)
    return b, cu, hom_nay


# ------------------------------------------------------------------ nhóm 1: chăm sóc chủ động
def _roi_mang(b: pd.DataFrame, c: dict) -> pd.DataFrame:
    rows = []
    for ma, r in b[b["hoat_dong"]].iterrows():
        diem, ly = 0, []
        if pd.notna(r["diem_rm"]) and r["diem_rm"] >= c["diem_rm_cao"]:
            diem += DIEM["rm_cao"]
            ly.append(f"Điểm nguy cơ rời mạng {r['diem_rm']:.0f} (từ {c['diem_rm_cao']})")
        elif pd.notna(r["diem_rm"]) and r["diem_rm"] >= c["diem_rm_vua"]:
            diem += DIEM["rm_vua"]
            ly.append(f"Điểm nguy cơ rời mạng {r['diem_rm']:.0f}")
        if r["y_roi"] or r["yc_roi"]:
            diem += DIEM["y_roi"]
            ly.append("Khách có ý rời hoặc yêu cầu thanh lý / tạm ngưng")
        if r["khieu_nai"]:
            diem += min(DIEM["khieu_nai"] * int(r["khieu_nai"]), DIEM["khieu_nai_toi_da"])
            ly.append(f"{int(r['khieu_nai'])} khiếu nại trong {c['so_ngay_xet']} ngày")
        if r["su_co"] >= 2:
            diem += DIEM["su_co_lap"]
            ly.append(f"Sự cố kỹ thuật lặp {int(r['su_co'])} lần")
        if r["qua_han_ngay"] > 0:
            diem += DIEM["no_qua_han"]
            ly.append(f"Nợ cước quá hạn {int(r['qua_han_ngay'])} ngày")
        elif r["trong_ds_no"]:
            diem += DIEM["no_qua_han"]
            ly.append("Nằm trong danh sách nợ cước")
        if r["ky_tre"] >= 2:
            diem += DIEM["hay_tra_tre"]
            ly.append(f"Trả trễ {int(r['ky_tre'])} kỳ trong 12 tháng")
        diem = min(diem, 100)
        if diem < c["nguong_nhom"]:
            continue
        if r["y_roi"] or r["yc_roi"]:
            dx = "Trưởng nhóm DVKH gọi giữ chân trong 24 giờ, chuẩn bị sẵn ưu đãi phù hợp"
        elif r["su_co"] >= 2:
            dx = "Kỹ thuật kiểm tra tận nơi trước, DVKH gọi lại sau khi xử lý xong"
        elif r["khieu_nai"]:
            dx = "DVKH gọi xác nhận khiếu nại đã được giải quyết, ghi nhận mức hài lòng"
        elif r["dang_no"]:
            dx = "Nhắc cước kèm hỏi thăm chất lượng dịch vụ, tìm lý do chậm thanh toán"
        else:
            dx = "DVKH gọi chăm sóc chủ động trong tuần"
        rows.append({"so_hd": ma, "muc": CAO if diem >= c["nguong_cao"] else TB, "diem": diem, "diem_rm": r["diem_rm"], "ly_do": "; ".join(ly), "de_xuat": dx,
                     "phu_trach": r["phu_trach"] or luat.GIAO_DVKH, "sale": r["sale"], "goi": r["goi"], "cuoc_thang": r["cuoc_thang"], "tham_nien": r["tham_nien"],
                     "dang_no": "Có" if r["dang_no"] else ""})
    d = pd.DataFrame(rows, columns=COT_RM)
    return d.sort_values(["diem", "diem_rm"], ascending=False, kind="stable").reset_index(drop=True)


# ------------------------------------------------------------------ nhóm 2: nhắc cước
def _nhac_cuoc(b: pd.DataFrame, cu: pd.DataFrame, hom_nay: pd.Timestamp, c: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, co_ky = [], set()
    them = lambda ma: {"ky_tre": int(b.at[ma, "ky_tre"]), "hinh_thuc_tt": b.at[ma, "hinh_thuc_tt"], "phu_trach": b.at[ma, "phu_trach"] or luat.GIAO_DVKH,
                       "sale": b.at[ma, "sale"], "goi": b.at[ma, "goi"]}
    cu = cu[cu["so_hd"].isin(b.index[~b["da_huy"]])]
    chua = cu[cu["chua_tt"]]
    for ma, g in chua.groupby("so_hd", sort=False):
        han = g["han_tt"].min()
        con = int((han - hom_nay).days)
        if con > c["tam_nhin_ngay"]:
            continue
        co_ky |= {ma}
        if con < 0:
            nhom, dx = NHOM_CUOC[0], ("DVKH gọi thu cước, báo trước ngày tạm ngưng dịch vụ" if con <= -15 else "Nhắn nhắc cước, gọi nếu sau 3 ngày chưa thanh toán")
        elif con <= c["nhac_truoc_ngay"]:
            nhom, dx = NHOM_CUOC[1], "Nhắn nhắc trước hạn kèm cách thanh toán nhanh"
        else:
            nhom, dx = NHOM_CUOC[2], "Đưa vào lịch nhắc tự động trước hạn 7 ngày"
        rows.append({"so_hd": ma, "nhom": nhom, "han_tt": han, "con_ngay": con, "so_tien": float(g["so_tien"].sum()), "so_ky": int(len(g)), "de_xuat": dx, **them(ma)})
    if len(cu):                                                    # mọi kỳ đã trả: kỳ kế tiếp dự kiến bắt đầu ngay sau kỳ cuối
        cuoi = cu.sort_values("ky_tu").groupby("so_hd").last()
        for ma, r in cuoi.iterrows():
            if ma in co_ky or pd.isna(r["ky_den"]) or not b.at[ma, "hoat_dong"] or ma in set(chua["so_hd"]):
                continue
            han = (r["ky_den"] + pd.Timedelta(days=1)).normalize()
            con = int((han - hom_nay).days)
            if 0 <= con <= c["tam_nhin_ngay"]:
                rows.append({"so_hd": ma, "nhom": NHOM_CUOC[3], "han_tt": han, "con_ngay": con, "so_tien": float(r["so_tien"] or 0), "so_ky": 1,
                             "de_xuat": "Báo trước kỳ cước mới; khách trả đúng hạn thì mời chuyển trả trước", **them(ma)})
                co_ky |= {ma}
    for ma in b.index[b["trong_ds_no"] & ~b["da_huy"] & ~b.index.isin(co_ky)]:
        rows.append({"so_hd": ma, "nhom": NHOM_CUOC[4], "han_tt": pd.NaT, "con_ngay": None, "so_tien": None, "so_ky": 0,
                     "de_xuat": "Đối chiếu công nợ với DVKH rồi nhắc cước", **them(ma)})
    d = pd.DataFrame(rows, columns=COT_CUOC)
    d["_t"] = d["nhom"].map({n: i for i, n in enumerate(NHOM_CUOC)})
    d = d.sort_values(["_t", "han_tt", "so_tien"], ascending=[True, True, False], kind="stable").drop(columns="_t").reset_index(drop=True)
    lich = d[d["han_tt"].notna() & (d["con_ngay"] >= 0)].groupby("han_tt").agg(so_hd=("so_hd", "size"), so_tien=("so_tien", "sum")).reset_index()
    return d, lich


# ------------------------------------------------------------------ nhóm 3: bán thêm
def _ban_them(b: pd.DataFrame, rm: pd.DataFrame) -> pd.DataFrame:
    nguy_co = set(rm["so_hd"])
    on = b[b["hoat_dong"] & ~b["dang_no"] & b["khieu_nai"].eq(0) & (b["su_co"] < 2) & ~b["y_roi"] & ~b["yc_roi"] & ~b.index.isin(nguy_co)]
    rows = []
    for ma, r in on.iterrows():
        goi_y = []
        if not r["co_play"]:
            goi_y.append(GOI_Y[0])
        if not r["co_camera"]:
            goi_y.append(GOI_Y[1])
        if r["goi"].strip().lower().startswith("giga"):
            goi_y.append(GOI_Y[2])
        if r["tra_truoc_thang"] <= 1 and r["ky_dung"] >= 3 and r["ky_tre"] == 0:
            goi_y.append(GOI_Y[3])
        if not goi_y:
            continue
        tn = 0 if pd.isna(r["tham_nien"]) else int(r["tham_nien"])
        dung = r["ky_dung"] >= 3 and r["ky_tre"] == 0
        diem = 10 * len(goi_y) + min(tn, 24) + (10 if dung else 0)
        ly = ["Không nợ, không khiếu nại, không sự cố lặp"] + ([f"thanh toán đúng hạn {int(r['ky_dung'])} kỳ"] if dung else []) + ([f"dùng {tn} tháng"] if tn else ["mới online"])
        co = [n for n, k in (("FPT Play", "co_play"), ("Camera", "co_camera")) if r[k]]
        rows.append({"so_hd": ma, "muc": CAO if diem >= 40 else (TB if diem >= 25 else THAP), "goi_y": " · ".join(goi_y), "so_goi_y": len(goi_y), "ly_do": ", ".join(ly),
                     "de_xuat": f"Sale {'gọi' if tn >= 3 else 'chào khi chăm sóc sau lắp'}: mời {goi_y[0]}" + (f", sau đó {goi_y[1]}" if len(goi_y) > 1 else ""),
                     "dich_vu": " · ".join(co) or "Chỉ Internet", "goi": r["goi"], "cuoc_thang": r["cuoc_thang"], "tham_nien": r["tham_nien"], "sale": r["sale"], "_d": diem})
    d = pd.DataFrame(rows, columns=COT_BAN + ["_d"])
    return d.sort_values("_d", ascending=False, kind="stable").drop(columns="_d").reset_index(drop=True)


# ------------------------------------------------------------------ tổng hợp
@nho("so_lieu", 60)
def tong_hop() -> dict:
    """Ba bảng phân loại + số tóm tắt. Kết quả được nhớ tạm: nơi gọi KHÔNG sửa trực tiếp các bảng trả về."""
    c = cau_hinh()
    dd = _dac_diem(c)
    if dd is None:
        return {"hom_nay": None, "demo": nguon.la_demo(), "co_nguon_cuoc": False, "tong": 0, "hoat_dong": 0, "roi_mang": _rong(COT_RM), "nhac_cuoc": _rong(COT_CUOC),
                "lich_cuoc": _rong(["han_tt", "so_hd", "so_tien"]), "ban_them": _rong(COT_BAN), "dac_diem": pd.DataFrame(), "cuoc": _rong(nguon.COT_CUOC), "cau_hinh": c}
    b, cu, hom_nay = dd
    rm = _roi_mang(b, c)
    nc, lich = _nhac_cuoc(b, cu, hom_nay, c)
    return {"hom_nay": hom_nay, "demo": nguon.la_demo(), "co_nguon_cuoc": bool(len(cu)), "tong": int(len(b)), "hoat_dong": int(b["hoat_dong"].sum()),
            "roi_mang": rm, "nhac_cuoc": nc, "lich_cuoc": lich, "ban_them": _ban_them(b, rm), "dac_diem": b, "cuoc": cu, "cau_hinh": c}


def tom_tat(t: dict) -> dict:
    rm, nc, bt = t["roi_mang"], t["nhac_cuoc"], t["ban_them"]
    dem = nc["nhom"].value_counts() if len(nc) else {}
    theo_dv = {g: int(bt["goi_y"].str.contains(g, regex=False).sum()) if len(bt) else 0 for g in GOI_Y}
    return {"rm": int(len(rm)), "rm_cao": int((rm["muc"] == CAO).sum()), "rm_cuoc": float(rm["cuoc_thang"].sum()) if len(rm) else 0.0,
            "cuoc": int(len(nc)), "cuoc_theo_nhom": {n: int(dem.get(n, 0)) for n in NHOM_CUOC},
            "cuoc_qua_han_tien": float(nc.loc[nc["nhom"] == NHOM_CUOC[0], "so_tien"].sum()) if len(nc) else 0.0,
            "cuoc_sap_toi_tien": float(nc.loc[nc["nhom"].isin(NHOM_CUOC[1:4]), "so_tien"].sum()) if len(nc) else 0.0,
            "ban": int(len(bt)), "ban_cao": int((bt["muc"] == CAO).sum()), "ban_theo_dv": theo_dv}


def cua_hop_dong(so_hd: str) -> dict:
    """Phần phân loại và cước của MỘT hợp đồng cho trang hồ sơ: thuộc nhóm nào (kèm lý do, đề xuất) và lịch sử các kỳ cước (mới nhất ở trên)."""
    ma = str(so_hd or "").strip().upper()
    t = tong_hop()
    nhom = []
    for khoa, ten in (("roi_mang", "Chăm sóc chủ động"), ("nhac_cuoc", "Nhắc cước"), ("ban_them", "Bán thêm")):
        d = t[khoa]
        x = d[d["so_hd"] == ma] if len(d) else d
        if len(x):
            r = x.iloc[0]
            nhom.append({"ma": khoa, "ten": ten, "muc": r.get("muc") or r.get("nhom"), "ly_do": r.get("ly_do") or r.get("nhom"), "de_xuat": r["de_xuat"],
                         "goi_y": r.get("goi_y", "")})
    cu = t["cuoc"]
    ky = cu[cu["so_hd"] == ma].sort_values("ky_tu", ascending=False).reset_index(drop=True) if len(cu) else cu
    tt = {"so_ky": int(len(ky)), "chua_tt": int(ky["chua_tt"].sum()) if len(ky) else 0, "qua_han": int(ky["qua_han"].sum()) if len(ky) else 0,
          "tre": int(ky["tre"].sum()) if len(ky) else 0, "tien_chua_tt": float(ky.loc[ky["chua_tt"], "so_tien"].sum()) if len(ky) else 0.0}
    return {"nhom": nhom, "ky": ky, "tom_tat": tt, "hom_nay": t["hom_nay"], "co_nguon_cuoc": t["co_nguon_cuoc"]}
