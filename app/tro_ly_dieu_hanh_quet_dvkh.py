"""Nguồn quét khối DVKH của Trợ lý điều hành: mọi CSKH (tải việc, % quá hạn), SR bị động / chủ động tồn và quá hạn, rời mạng, công nợ so với kỳ trước.

Số liệu lấy từ `dvkh.so_lieu` / `dvkh.tong_quan` / `dvkh.khai_thac` (đã nhớ tạm, đã đối chiếu với file báo cáo), không tính lại công thức; ngưỡng mức "cần chú ý /
nghiêm trọng" dùng lại của `dvkh.insight` để Trợ lý và trang Nhận định không nói hai chuyện khác nhau. Ngày xem = ngày mới nhất của file SR. Vấn đề DVKH về Ban Giám đốc (`bgd`).
Chỉ CSKH từ `MAU_TOI_THIEU` SR trở lên mới bị xét (mẫu nhỏ làm tỷ lệ nhiễu); tài khoản máy gọi `autocall` đã được tách sẵn khỏi bảng nhân sự.
"""
from __future__ import annotations

import pandas as pd

from app.dvkh import insight, khai_thac, so_lieu as sl, tong_quan
from app.tro_ly_dieu_hanh_quet import CAO, THAP, TB, NguonQuet, chi_so, dang_ky, lay, ph

QUA_HAN_NGUOI = (25, 40)            # % SR của một CSKH quá hạn: cần chú ý / nghiêm trọng
QUA_HAN_TOI_THIEU = 10              # và ít nhất bấy nhiêu SR quá hạn
TAI_Z = 3.0                         # tồn của một người lệch trên trung vị đồng nghiệp từ bấy nhiêu MAD
TON_NGUOI_TOI_THIEU = 20
SR_QUA_HAN_TOI_THIEU, SR_TON_TOI_THIEU = 10, 20
TANG_QUA_HAN_TB = 5.0               # % quá hạn tăng từ bấy nhiêu điểm so với cùng kỳ tháng trước
ROI_TANG_TB, ROI_TANG_CAO, ROI_TOI_THIEU = 0.15, 0.30, 30   # số khách rời mạng tăng tương đối so với tháng trước (kỳ trước có từ 30 khách)
CONG_NO_CAO = 3.0                   # thu nợ thấp hơn kỳ trước từ bấy nhiêu điểm % là mức cao (mức trung bình dùng `insight.NGUONG_THU_NO_CHAM`)
PHONG_DV = ("DNG1", "DNG2")
NHOM_CSKH, NHOM_SR, NHOM_RM, NHOM_CN = "dvkh:cskh", "dvkh:sr", "dvkh:roi_mang", "dvkh:cong_no"


def _muc_nguong(v, nguong) -> str:
    return THAP if v is None or pd.isna(v) else CAO if v >= nguong[1] else TB if v >= nguong[0] else THAP


def _ph(nguon: str, nhom: str, ma: str, cap: str, doi_tuong: str, muc: str, diem: float, tieu_de: str, bc: dict, duong: str, nhan_nhom: str, cs: dict, don_vi: str = "mục") -> dict:
    return ph(nguon, nhom, ma=ma, khoi="dvkh", cap=cap, doi_tuong=doi_tuong, muc=muc, diem=diem, tieu_de=tieu_de, bang_chung=bc, duong_dan=duong, nguoi_quyet="bgd",
              don_vi=don_vi, nhan_nhom=nhan_nhom, chi_so=cs)


def phat_hien_cskh(hs: pd.DataFrame) -> list[dict]:
    """Mỗi CSKH từ MAU_TOI_THIEU SR: % quá hạn cao, bị nhãn "Cần hỗ trợ" / "Cần nhắc" của `khai_thac`, hoặc số SR tồn lệch xa đồng nghiệp."""
    if hs.empty:
        return []
    d = hs[hs["tong_tai"].fillna(0) >= insight.MAU_TOI_THIEU]
    if d.empty:
        return []
    ton = pd.to_numeric(d["tong_ton"], errors="coerce").fillna(0)
    med = float(ton.median())
    mad = max(float((ton - med).abs().median()) * 1.4826, 1.0)
    cs = chi_so("dvkh_cskh", {}, "Số CSKH có tải việc hoặc quá hạn bất thường", "người")
    kq = []
    for r, t in zip(d.to_dict("records"), ton):
        ten, tai, qh = str(r["nhan_su"]), int(r["tong_tai"]), float(r.get("ty_le_qua_han") or 0)
        so_qh = int(r.get("tong_qua_han") or 0)
        bc = {"tai": tai, "ton": int(t), "qua_han": so_qh, "ty_le_qua_han": round(qh, 1)}
        muc = _muc_nguong(qh, QUA_HAN_NGUOI) if so_qh >= QUA_HAN_TOI_THIEU else THAP
        if muc == THAP and str(r.get("nhan") or "") in ("Cần hỗ trợ", "Cần nhắc"):
            muc = TB
        if muc != THAP:
            kq.append(_ph("dvkh_cskh", NHOM_CSKH, f"dvkh.cskh.{ten}.qua_han", "nhan_su", ten, muc, qh, f"{ten} có {so_qh} SR quá hạn trên {tai} SR ({qh:.0f}%)", bc, "/dvkh/nhan-su", "CSKH cần chú ý", cs, "người"))
        if t >= TON_NGUOI_TOI_THIEU and (t - med) / mad >= TAI_Z:
            kq.append(_ph("dvkh_cskh", NHOM_CSKH, f"dvkh.cskh.{ten}.ton_lech", "nhan_su", ten, TB, float(t - med), f"{ten} đang tồn {int(t)} SR, vượt xa đồng nghiệp (trung vị {med:.0f})",
                          {**bc, "trung_vi": round(med)}, "/dvkh/nhan-su", "CSKH cần chú ý", cs, "người"))
    return kq


def phat_hien_sr(sr: dict, sr_truoc: dict) -> list[dict]:
    """SR bị động quá hạn, SR chủ động tồn và không liên lạc được theo từng phòng DVKH (DNG1, DNG2), kèm so với cùng kỳ tháng trước."""
    kq = []
    for p in PHONG_DV:
        bd, cd = (sr.get(p) or {}).get("bd"), (sr.get(p) or {}).get("cd")
        bd0 = ((sr_truoc or {}).get(p) or {}).get("bd")
        if bd and bd["so_sr"] >= insight.MAU_TOI_THIEU:
            qh = bd["ty_le_qua_han"]
            muc = _muc_nguong(qh, insight.NGUONG_QUA_HAN_BD) if bd["qua_han"] >= SR_QUA_HAN_TOI_THIEU else THAP
            tang = None if not bd0 or bd0.get("ty_le_qua_han") is None or qh is None else qh - bd0["ty_le_qua_han"]
            if muc == THAP and tang is not None and tang >= TANG_QUA_HAN_TB and bd["qua_han"] >= SR_QUA_HAN_TOI_THIEU:
                muc = TB
            if muc != THAP:
                kq.append(_ph("dvkh_sr", NHOM_SR, f"dvkh.sr.{p}.bd_qua_han", "phong", p, muc, float(qh or 0), f"{p}: {bd['qua_han']} SR bị động quá hạn ({qh:.0f}%)",
                              {"qua_han": bd["qua_han"], "ty_le_qua_han": round(qh), "so_sr": bd["so_sr"], "ton": bd["ton"], "cung_ky_pct": None if not bd0 or bd0.get("ty_le_qua_han") is None else round(bd0["ty_le_qua_han"])},
                              "/dvkh/sr-bi-dong", "SR bị động / chủ động", chi_so("dvkh_sr_qua_han", {"phong": p}, f"Số SR bị động quá hạn của {p}", "SR"), "phòng"))
        if cd and cd["so_sr"] >= insight.MAU_TOI_THIEU:
            muc = _muc_nguong(cd["ty_le_ton"], insight.NGUONG_TON_CD) if cd["ton"] >= SR_TON_TOI_THIEU else THAP
            if muc != THAP:
                kq.append(_ph("dvkh_sr", NHOM_SR, f"dvkh.sr.{p}.cd_ton", "phong", p, muc, float(cd["ty_le_ton"]), f"{p}: {cd['ton']} SR chủ động còn tồn ({cd['ty_le_ton']:.0f}%)",
                              {"ton": cd["ton"], "ty_le_ton": round(cd["ty_le_ton"]), "so_sr": cd["so_sr"]}, "/dvkh/sr-chu-dong", "SR bị động / chủ động",
                              chi_so("dvkh_sr_cd_ton", {"phong": p}, f"Số SR chủ động tồn của {p}", "SR"), "phòng"))
    return kq


def phat_hien_roi_mang(rm: dict, rm_truoc: dict) -> list[dict]:
    """Số khách rời mạng tăng so với tháng trước (chỉ khi file đã có tháng trước) ở từng phòng DVKH và cả Đà Nẵng."""
    kq = []
    for p in (*PHONG_DV, "DNG"):
        a, b = (rm or {}).get(p), (rm_truoc or {}).get(p)
        if not a or not b or float(b.get("kh_roi_mang") or 0) < ROI_TOI_THIEU:
            continue
        x, y = float(a["kh_roi_mang"] or 0), float(b["kh_roi_mang"])
        tang = x / y - 1
        muc = CAO if tang >= ROI_TANG_CAO else TB if tang >= ROI_TANG_TB else THAP
        if muc != THAP:
            kq.append(_ph("dvkh_roi_mang", NHOM_RM, f"dvkh.roi_mang.{p}.tang", "phong" if p != "DNG" else "chi_nhanh", p if p != "DNG" else "Đà Nẵng", muc, tang * 100,
                          f"{p}: khách rời mạng {x:.0f}, tăng {tang * 100:.0f}% so với tháng trước ({y:.0f})",
                          {"roi_mang": int(x), "thang_truoc": int(y), "tang_pct": round(tang * 100), "ty_le_roi_active": a.get("ty_le_roi_active")}, "/dvkh/roi-mang", "Rời mạng",
                          chi_so("dvkh_roi_mang", {"phong": p}, f"Số khách rời mạng của {p}", "khách"), "phòng"))
    return kq


def phat_hien_cong_no(cn: dict, cn_truoc: dict, ky: str | None) -> list[dict]:
    """Thu nợ (theo số hoá đơn) thấp hơn kỳ trước cùng ngày: từ `NGUONG_THU_NO_CHAM` điểm là mức trung bình, từ `CONG_NO_CAO` điểm là mức cao."""
    kq = []
    for p in (*PHONG_DV, "DNG"):
        a, b = (cn or {}).get(p), (cn_truoc or {}).get(p)
        if not a or not b or a.get("bill") is None or b.get("bill") is None:
            continue
        chenh = a["bill"] - b["bill"]
        muc = CAO if chenh <= -CONG_NO_CAO else TB if chenh <= -insight.NGUONG_THU_NO_CHAM else THAP
        if muc != THAP:
            kq.append(_ph("dvkh_cong_no", NHOM_CN, f"dvkh.cong_no.{p}.cham", "phong" if p != "DNG" else "chi_nhanh", p if p != "DNG" else "Đà Nẵng", muc, -chenh,
                          f"{p}: thu nợ chậm hơn kỳ trước {abs(chenh):.1f} điểm % (cùng ngày)", {"thu_bill": round(a["bill"], 1), "ky_truoc": round(b["bill"], 1), "chenh_diem": round(chenh, 1), "ky_no": ky},
                          "/dvkh/cong-no", "Công nợ", chi_so("dvkh_cong_no", {"phong": p}, f"Số điểm % thu nợ của {p} chậm hơn kỳ trước", "điểm"), "phòng"))
    return kq


# ------------------------------------------------------------------ đọc dữ liệu (một lần mỗi lượt) và cắm vào bộ quét
def dv(c: dict) -> dict | None:
    def nap():
        if not sl.co_du_lieu():
            return None
        nd = sl.ngay_du_lieu()
        ngay = nd.get("sr_bd") or nd.get("sr_cd")
        if ngay is None:
            return None
        dau = pd.Timestamp(ngay).replace(day=1)
        bd = sl.loc(sl.sr_bi_dong(), None, dau, ngay, "ngay_yc")
        cd = sl.loc(sl.sr_chu_dong(), None, dau, ngay, "ngay_do")
        hs = khai_thac.cho_nao_tot_xau(khai_thac.gan_so_khach(sl.hieu_suat_nhan_su(bd, cd), sl.so_kh_au())) if len(bd) or len(cd) else pd.DataFrame()
        return {"ngay": ngay, "nd": nd, "hs": hs, "tq": tong_quan.tinh(ngay, "luy_ke")}
    return lay(c, "dvkh", nap)


def _mot(f):
    def quet(c: dict) -> list[dict]:
        d = dv(c)
        return [] if d is None else f(d)
    return quet


def phu_cskh(c: dict) -> dict:
    d = dv(c)
    hs = pd.DataFrame() if d is None else d["hs"]
    return {"don_vi": "CSKH", "da_quet": 0 if hs.empty else int((hs["tong_tai"].fillna(0) >= insight.MAU_TOI_THIEU).sum()), "tong": len(hs),
            "du_lieu_luc": "" if d is None else f"SR tới {pd.Timestamp(d['ngay']):%d/%m}", "ghi_chu": f"Chỉ xét CSKH từ {insight.MAU_TOI_THIEU} SR trở lên (mẫu nhỏ thì tỷ lệ nhiễu)"}


def _phu_phong(ten: str, lay_du_lieu):
    def phu(c: dict) -> dict:
        d = dv(c)
        co = 0 if d is None else sum(1 for p in PHONG_DV if lay_du_lieu(d, p))
        return {"don_vi": ten, "da_quet": co, "tong": len(PHONG_DV), "du_lieu_luc": "" if d is None else f"tới {pd.Timestamp(d['ngay']):%d/%m}"}
    return phu


def _gia_tri_sr(chi: str):
    def do(c: dict, ts: dict) -> int:
        d = dv(c)
        k = ((d["tq"]["sr"].get(ts["phong"]) or {}).get(chi)) if d else None
        return int((k or {}).get("qua_han" if chi == "bd" else "ton", 0))
    return do


def do_cskh(c: dict, ts: dict) -> int:
    d = dv(c)
    return len({f["doi_tuong"] for f in phat_hien_cskh(d["hs"])}) if d else 0


def do_roi_mang(c: dict, ts: dict) -> int:
    d = dv(c)
    return int(float(((d["tq"]["roi_mang"] or {}).get(ts["phong"]) or {}).get("kh_roi_mang") or 0)) if d else 0


def do_cong_no(c: dict, ts: dict) -> float:
    d = dv(c)
    a, b = ((d["tq"]["cong_no"] or {}).get(ts["phong"]), (d["tq"]["cong_no_truoc"] or {}).get(ts["phong"])) if d else (None, None)
    return 0.0 if not a or not b or a.get("bill") is None or b.get("bill") is None else round(max(0.0, b["bill"] - a["bill"]), 1)


dang_ky(NguonQuet("dvkh_cskh", "DVKH: từng CSKH", "dvkh", _mot(lambda d: phat_hien_cskh(d["hs"])), phu_cskh), {"dvkh_cskh": do_cskh})
dang_ky(NguonQuet("dvkh_sr", "DVKH: SR bị động / chủ động", "dvkh", _mot(lambda d: phat_hien_sr(d["tq"]["sr"], d["tq"]["sr_truoc"])),
                  _phu_phong("phòng DVKH", lambda d, p: (d["tq"]["sr"].get(p) or {}).get("bd") or (d["tq"]["sr"].get(p) or {}).get("cd"))),
         {"dvkh_sr_qua_han": _gia_tri_sr("bd"), "dvkh_sr_cd_ton": _gia_tri_sr("cd")})
dang_ky(NguonQuet("dvkh_roi_mang", "DVKH: rời mạng", "dvkh", _mot(lambda d: phat_hien_roi_mang(d["tq"]["roi_mang"], d["tq"]["roi_mang_truoc"])),
                  _phu_phong("phòng / chi nhánh có số rời mạng", lambda d, p: (d["tq"]["roi_mang"] or {}).get(p))), {"dvkh_roi_mang": do_roi_mang})
dang_ky(NguonQuet("dvkh_cong_no", "DVKH: công nợ", "dvkh", _mot(lambda d: phat_hien_cong_no(d["tq"]["cong_no"], d["tq"]["cong_no_truoc"], d["tq"]["ky_no"])),
                  _phu_phong("phòng có số công nợ", lambda d, p: (d["tq"]["cong_no"] or {}).get(p))), {"dvkh_cong_no": do_cong_no})
