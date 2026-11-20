"""Nguồn quét khối KINH DOANH của Trợ lý điều hành: mọi nhân sự được xét của mọi phòng bán hàng, rồi mọi phòng, rồi cả chi nhánh.

Số liệu lấy từ `bao_cao_phong.bang_nhan_su` (online, cùng kỳ tháng trước, tuần này / tuần trước, tồn, V.VIP, Camera, mức cảnh báo chung của `canh_bao`) và
`du_bao.du_bao_thang` (đánh giá An toàn / Cần tăng tốc / Rủi ro đã có, KHÔNG tính lại). Ở đây chỉ thêm cách ĐỌC: so mỗi người với chính họ kỳ trước và với đồng
nghiệp cùng phòng (lệch xa trung vị theo MAD). Trưởng phòng, người nghỉ, acc tạm không bị nêu (`khong_xet`) nhưng số của họ vẫn nằm trong số phòng. Mọi ngưỡng ở đầu file.
Người quyết: vấn đề của một phòng về trưởng phòng đó (`tp:<mã phòng>`), toàn chi nhánh về Ban Giám đốc (`bgd`).
"""
from __future__ import annotations

import pandas as pd

from app import bao_cao_phong as bcp, du_bao, org, overview
from app.tro_ly_dieu_hanh_quet import CAO, THAP, TB, NguonQuet, chi_so, dang_ky, lay, ph

LOAI_PHONG_KD = ("IBB", "DIABAN")
GIAM_CK_TOI_THIEU = 5              # chỉ so với cùng kỳ tháng trước khi kỳ đó có từ bấy nhiêu online (số nhỏ thì tỷ lệ vô nghĩa)
GIAM_TB, GIAM_CAO, CHENH_CAO = 0.4, 0.6, 6     # online thấp hơn cùng kỳ từ 40% (60% và ít nhất 6 online thì mức cao)
CHENH_TB = 4
DONG_NGHIEP_TOI_THIEU, TRUNG_VI_TOI_THIEU = 5, 8   # cần từ 5 người xét và trung vị phòng từ 8 online mới so với đồng nghiệp
Z_TB, Z_CAO = 2.5, 3.5             # độ lệch theo MAD (đã nhân 1,4826) dưới trung vị
TY_LE_TB, TY_LE_CAO = 0.4, 0.25    # và online của người đó <= 40% (25%) trung vị phòng
TON_TB, TON_CAO = bcp.TON_LAU_CANH_BAO, 6      # hợp đồng chờ online từ 7 ngày
BAN_KEM_TOI_THIEU = 8              # từ 8 online mà chưa có V.VIP (Camera) nào thì nêu (mức thấp)
PHONG_NGAY_TOI_THIEU = 5           # trước ngày 5 của tháng dự báo cuối tháng chưa đủ tin cậy: không đánh giá phòng theo dự báo
PHONG_GIAM_CK, PHONG_CK_TOI_THIEU = 0.85, 20   # phòng online dưới 85% cùng kỳ (kỳ đó từ 20 online) thì nêu mức trung bình
NHOM_NS, NHOM_PHONG, NHOM_CN = "kd:nhan_su:", "kd:phong:", "kd:chi_nhanh"


def _so(df: pd.DataFrame, cot: str) -> pd.Series:
    return pd.to_numeric(df[cot], errors="coerce").fillna(0) if cot in df else pd.Series(0, index=df.index)


def _ph_ns(phong: str, r: dict, facet: str, muc: str, diem: float, tieu_de: str, bc: dict) -> dict:
    acc = r["acc_norm"]
    return ph("kd_nhan_su", NHOM_NS + phong, ma=f"kd.nhansu.{acc}.{facet}", khoi="kd", cap="nhan_su", doi_tuong=acc, muc=muc, diem=diem, tieu_de=tieu_de,
              bang_chung={"phong": phong, **bc}, duong_dan=f"/phong?phong={phong}", nguoi_quyet=f"tp:{phong}", don_vi="nhân sự", nhan_nhom=f"Nhân sự cần chú ý ở {phong}",
              chi_so=chi_so("kd_nhan_su_chu_y", {"phong": phong}, f"Số nhân sự cần chú ý của {phong}", "người"))


def phat_hien_nhan_su(df: pd.DataFrame, phong: str) -> list[dict]:
    """Mọi nhân sự được xét của MỘT phòng (bảng `bang_nhan_su`, dòng nhân sự; dòng đã `khong_xet` bị bỏ). Sáu cách nhìn, mỗi cách một phát hiện riêng:
    online_giam (so với chính họ kỳ trước), canh_bao (mức cảnh báo chung của app), lech_dong_nghiep (lệch xa trung vị phòng), ton_lau, thieu_vvip, thieu_camera."""
    d = df[df["khong_xet"].fillna("").eq("")] if "khong_xet" in df else df
    d = d[d["loai_dong"].eq("data")] if "loai_dong" in d else d
    if d.empty:
        return []
    online, n = _so(d, "online"), len(d)
    med = float(online.median())
    mad = float((online - med).abs().median()) * 1.4826
    kq: list[dict] = []
    for r, onl in zip(d.to_dict("records"), online):
        ck, onl = int(float(r.get("ck_online") or 0)), int(onl)
        bc_ck = {"online": onl, "cung_ky": ck}
        chenh = ck - onl
        if ck >= GIAM_CK_TOI_THIEU and chenh >= CHENH_TB and chenh / ck >= GIAM_TB:
            cao = chenh / ck >= GIAM_CAO and chenh >= CHENH_CAO
            kq.append(_ph_ns(phong, r, "online_giam", CAO if cao else TB, chenh, f"{r['acc_norm']} online {onl}, thấp hơn cùng kỳ tháng trước ({ck})",
                             {**bc_ck, "giam_pct": round(chenh / ck * 100)}))
        if str(r.get("muc_chu_y") or ""):
            cao = r["muc_chu_y"] == "Trao đổi ngay"
            kq.append(_ph_ns(phong, r, "canh_bao", CAO if cao else TB, 20 if cao else 10, f"{r['acc_norm']}: {r.get('chu_y') or r['muc_chu_y']}",
                             {"online": onl, "ngay_chua_co_so": r.get("ngay_lien_chua_co_so"), "tuan_nay": r.get("tuan_nay"), "tuan_truoc": r.get("tuan_truoc"), "canh_bao": r["muc_chu_y"]}))
        if n >= DONG_NGHIEP_TOI_THIEU and med >= TRUNG_VI_TOI_THIEU and onl <= TY_LE_TB * med:
            z = (med - onl) / max(mad, 1.0)
            if z >= Z_TB:
                kq.append(_ph_ns(phong, r, "lech_dong_nghiep", CAO if z >= Z_CAO and onl <= TY_LE_CAO * med else TB, z,
                                 f"{r['acc_norm']} online {onl}, thấp xa đồng nghiệp cùng phòng (trung vị {med:.0f})", {"online": onl, "trung_vi_phong": round(med), "do_lech": round(z, 1)}))
        ton = int(float(r.get("ton_qua_7") or 0))
        if ton >= TON_TB:
            kq.append(_ph_ns(phong, r, "ton_lau", CAO if ton >= TON_CAO else TB, ton, f"{r['acc_norm']} có {ton} hợp đồng chờ online từ 7 ngày", {"ton_qua_7": ton, "ton": r.get("ton")}))
        if onl >= BAN_KEM_TOI_THIEU:
            for cot, facet, ten in (("vvip", "thieu_vvip", "V.VIP"), ("camera", "thieu_camera", "Camera")):
                if int(float(r.get(cot) or 0)) == 0:
                    kq.append(_ph_ns(phong, r, facet, THAP, onl, f"{r['acc_norm']} online {onl} mà chưa bán kèm {ten}", {"online": onl, cot: 0}))
    return kq


def phat_hien_phong(db: pd.DataFrame, tq: pd.DataFrame, ma_phong: list[str], ten: dict, ngay: int) -> list[dict]:
    """Mỗi phòng bán hàng một phát hiện nếu đánh giá dự báo (`du_bao`) là Rủi ro / Cần tăng tốc, hoặc online thấp hơn cùng kỳ tháng trước; dòng TỔNG là cấp chi nhánh."""
    if ngay < PHONG_NGAY_TOI_THIEU:
        return []
    tqi = tq.set_index("phong_code") if "phong_code" in tq else pd.DataFrame()
    kq = []
    for code in [*ma_phong, "TOTAL"]:
        x = db[db["phong_code"] == code]
        if x.empty or not float(x.iloc[0]["mt"] or 0):
            continue
        r = x.iloc[0]
        t = tqi.loc[code] if code in tqi.index else None
        if code == "TOTAL":
            t = tq[tq["loai_dong"] == "total"].iloc[0] if "loai_dong" in tq and (tq["loai_dong"] == "total").any() else None
        onl, ck = (int(float(t["online"] or 0)), int(float(t["ck_online"] or 0))) if t is not None else (int(r["luy_ke"]), 0)
        hut = max(0, int(r["mt"]) - int(r["du_bao"]))
        muc = CAO if r["danh_gia"] == du_bao.RUI_RO else TB if r["danh_gia"] == du_bao.TANG_TOC else THAP
        thap_ck = ck >= PHONG_CK_TOI_THIEU and onl < ck * PHONG_GIAM_CK
        if muc == THAP and thap_ck:
            muc = TB
        if muc == THAP:
            continue
        nhan = ten.get(code, code)
        la_cn = code == "TOTAL"
        bc = {"muc_tieu": int(r["mt"]), "luy_ke": int(r["luy_ke"]), "du_bao": int(r["du_bao"]), "du_bao_nhip": int(r["du_bao_nhip"]), "dat_pct": r["pct_mt"], "hut": hut,
              "can_moi_ngay": r["can_moi_ngay"], "tb_ngay": r["tb_ngay"], "con_lai": int(r["con_lai"]), "danh_gia": r["danh_gia"], "online": onl, "cung_ky": ck}
        kq.append(ph("kd_phong", NHOM_CN if la_cn else NHOM_PHONG + code, ma=f"kd.{'chinhanh' if la_cn else 'phong.' + code}.muc_tieu", khoi="kd", cap="chi_nhanh" if la_cn else "phong",
                     doi_tuong="Chi nhánh" if la_cn else code, muc=muc, diem=hut, tieu_de=(f"{'Chi nhánh' if la_cn else nhan}: dự báo {int(r['du_bao'])}/{int(r['mt'])} online, {r['danh_gia']}"),
                     bang_chung=bc, duong_dan="/" if la_cn else f"/phong?phong={code}", nguoi_quyet="bgd" if la_cn else f"tp:{code}", don_vi="phòng", nhan_nhom="Dự báo so mục tiêu tháng",
                     chi_so=chi_so("kd_chi_nhanh_hut" if la_cn else "kd_phong_hut", {} if la_cn else {"phong": code}, f"Dự báo hụt so mục tiêu tháng của {'chi nhánh' if la_cn else nhan}", "online")))
    return kq


# ------------------------------------------------------------------ đọc dữ liệu (một lần mỗi lượt) và cắm vào bộ quét
def phong_kd(c: dict) -> list[dict]:
    return lay(c, "kd_phong", lambda: [{"code": p["code"], "ten": p["ten"]} for p in org.phong_order(c["thang"]) if p["loai"] in LOAI_PHONG_KD]) or []


def _db(c: dict):
    return lay(c, "kd_db", lambda: du_bao.du_bao_thang(c["thang"], c["ngay"]))


def _tq(c: dict):
    return lay(c, "kd_tq", lambda: overview.bang_tong_quan(c["thang"], c["ngay"], chi_nhanh="all")[0])


def bang_phong(c: dict, code: str):
    def doc():
        bn = bcp.bang_nhan_su(c["thang"], c["ngay"], code)
        c["ten"].update({str(r["acc_norm"]): str(r["ho_ten"]) for r in bn.to_dict("records") if r.get("acc_norm") and r.get("ho_ten")})
        return bn
    return lay(c, "kd_ns:" + code, doc)


def _ns_phong(c: dict, code: str) -> list[dict]:
    def quet():
        bn = bang_phong(c, code)
        return [] if bn is None else phat_hien_nhan_su(bn, code)
    return lay(c, "kd_ns_ph:" + code, quet) or []


def quet_nhan_su(c: dict) -> list[dict]:
    return [f for p in phong_kd(c) for f in _ns_phong(c, p["code"])] if c["ngay"] else []


def phu_nhan_su(c: dict) -> dict:
    tong = xet = 0
    for p in phong_kd(c):
        bn = bang_phong(c, p["code"])
        if bn is not None:
            d = bn[bn["loai_dong"] == "data"]
            tong += len(d)
            xet += int(d["khong_xet"].fillna("").eq("").sum())
    return {"don_vi": "nhân sự", "da_quet": xet, "tong": tong, "du_lieu_luc": f"ngày số {c['ngay_iso']}" if c["ngay_iso"] else "",
            "ghi_chu": f"{tong - xet} người không xét theo quy tắc (trưởng phòng, đã nghỉ, acc tạm); số của họ vẫn nằm trong số phòng"}


def quet_phong(c: dict) -> list[dict]:
    db, tq = _db(c), _tq(c)
    if db is None or tq is None:
        return []
    ds = phong_kd(c)
    return phat_hien_phong(db, tq, [p["code"] for p in ds], {p["code"]: p["ten"] for p in ds}, c["ngay"])


def phu_phong(c: dict) -> dict:
    db = _db(c)
    ds = phong_kd(c)
    co = 0 if db is None else int(db["phong_code"].isin([p["code"] for p in ds]).sum()) + int((db["phong_code"] == "TOTAL").any())
    return {"don_vi": "phòng + chi nhánh", "da_quet": co, "tong": len(ds) + 1, "du_lieu_luc": f"ngày số {c['ngay_iso']}" if c["ngay_iso"] else ""}


def do_nhan_su(c: dict, ts: dict) -> int:
    return len({f["doi_tuong"] for f in _ns_phong(c, ts["phong"]) if f["muc"] != THAP})


def do_hut(c: dict, ts: dict) -> int:
    db = _db(c)
    r = db[db["phong_code"] == ts.get("phong", "TOTAL")].iloc[0]
    return max(0, int(r["mt"]) - int(r["du_bao"]))


dang_ky(NguonQuet("kd_nhan_su", "Kinh doanh: từng nhân sự", "kd", quet_nhan_su, phu_nhan_su), {"kd_nhan_su_chu_y": do_nhan_su})
dang_ky(NguonQuet("kd_phong", "Kinh doanh: phòng và chi nhánh so mục tiêu", "kd", quet_phong, phu_phong), {"kd_phong_hut": do_hut, "kd_chi_nhanh_hut": do_hut})
