"""Số liệu của khối Kỹ thuật (nhánh thi-lien-khoi): hợp đồng tồn và lịch hẹn, triển khai đúng hẹn, checklist lặp, cáp LAN, hiệu suất KTV.

Nguồn duy nhất là `app/lien_khoi/nguon.py` (`kt()` theo mã hợp đồng, `kt_block()` theo block): dữ liệu minh hoạ hoặc các file báo cáo Kỹ thuật trong
thư mục `LIEN_KHOI_KT_THU_MUC`. Không đọc database. Mọi hàm ở đây là hàm thuần trên DataFrame (trừ `su_kien`, `kpi_block`, `bay_gio` lấy từ nguồn)
nên kiểm thử được bằng bảng nhỏ. Ngưỡng nằm đầu file.

Quy ước (theo tên cột trong file Kỹ thuật, chưa có tài liệu chính thức): "quá mốc hẹn xanh / đỏ" = mốc `TG Hẹn xanh` / `TG Hẹn đỏ` của hợp đồng tồn
đã qua so với ngày dữ liệu mà hợp đồng vẫn còn tồn. Tỷ lệ của file KPI theo block tự tính lại từ SỐ ĐẾM (đúng hẹn / tổng) để cộng được nhiều block.
"""
from __future__ import annotations

import json

import pandas as pd

from app.bo_nho import nho
from app.lien_khoi import doc_kt, nguon

TON_LAU_NGAY = 7                  # tồn từ ngày này trở đi là "tồn lâu"
DUNG_HEN_L1_THAP = 60.0           # % đúng hẹn lần 1 dưới mức này là cần chú ý
DUNG_HEN_THAP = 90.0
BAO_TRI_24H_CAO = 25.0            # % bảo trì quá 24 giờ trên mức này là cần chú ý
TOI_THIEU_BLOCK = 15              # block dưới số lần hẹn này không đem ra so sánh
TOI_THIEU_KTV_TON = 5
NHOM_TUOI = [("Dưới 1 ngày", 0, 1), ("1 - 3 ngày", 1, 3), ("3 - 7 ngày", 3, 7), ("7 - 14 ngày", 7, 14), ("Trên 14 ngày", 14, 10**6)]
COT_TON = ["so_hd", "nguoi", "tinh_trang", "loai_trien_khai", "tao_luc", "ngay_ton", "hen_xanh", "hen_do", "qua_xanh", "qua_do", "tuoi",
           "ly_do_ma", "ly_do", "ghi_chu_luc", "gio_im_lang", "phan_tuyen"]
GIAI_DOAN_TON = ["Đã phân công", "Đã nhận ca", "Đang xử lý", "Đã xử lý đang theo dõi"]
THU_TU_NHOM = ["khach", "ky_thuat", "ha_tang", "kinh_doanh", "he_thong", "chua_ghi"]
GIO_IM_LANG = 24                  # ca tồn không có cập nhật ghi chú từ ngần này giờ là "im lặng"
TOI_THIEU_KHAU = 5                # khâu có ít hợp đồng hơn mức này thì chỉ ghi "mẫu nhỏ", không kết luận
# các khâu của một hợp đồng triển khai (khoá mốc trong thuộc tính của file "triển khai đúng hạn"): từ mốc đầu tới mốc sau
KHAU = [("tao_hd", "tao_ptc", "Sale chuyển phiếu thi công"), ("tao_ptc", "phan_cong", "Phân công người làm"),
        ("phan_cong", "checkin", "Chờ KTV tới nhà khách"), ("checkin", "hoan_tat", "Thi công tại nhà khách")
]


def _json(s) -> dict:
    try:
        v = json.loads(s) if isinstance(s, str) and s else {}
        return v if isinstance(v, dict) else {}
    except ValueError:
        return {}


def _tt(d: pd.DataFrame, khoa: str) -> pd.Series:
    return d["thuoc_tinh"].map(lambda s: _json(s).get(khoa, "")).astype(str)


def _n(v, nd: int = 0) -> str:
    if v is None or v != v:
        return "–"
    return f"{v:,.{nd}f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ------------------------------------------------------------------ nguồn
@nho("so_lieu", 60)
def su_kien() -> pd.DataFrame:
    return nguon.kt()


@nho("so_lieu", 60)
def kpi_block() -> pd.DataFrame:
    return nguon.kt_block()


def co_du_lieu() -> bool:
    return not su_kien().empty or not kpi_block().empty


def bay_gio(ev: pd.DataFrame | None = None) -> pd.Timestamp:
    """"Bây giờ" của số liệu: bộ minh hoạ có ngày chốt riêng; dữ liệu thật lấy theo sự kiện mới nhất (file xuất lúc nào thì số tới lúc đó)."""
    tc = nguon.ngay_tham_chieu()
    if tc is not None:
        return tc + pd.Timedelta(hours=12)
    ev = su_kien() if ev is None else ev
    return ev["thoi_diem"].max() if len(ev) and ev["thoi_diem"].notna().any() else pd.Timestamp.now().floor("h")


def nguon_ghi_chu() -> str:
    if nguon.la_demo():
        return "Dữ liệu MINH HOẠ: mã hợp đồng, tên người và tên block là giả định, số đếm lấy từ file báo cáo Kỹ thuật."
    p = nguon.thu_muc_kt()
    return f"Đọc các file báo cáo Kỹ thuật trong thư mục {p.name}." if p else "Chưa đặt thư mục file Kỹ thuật (biến LIEN_KHOI_KT_THU_MUC)."


# ------------------------------------------------------------------ tồn và lịch hẹn
def ton(ev: pd.DataFrame, now: pd.Timestamp) -> pd.DataFrame:
    """Hợp đồng đang tồn Kỹ thuật: tuổi tồn (ngày), quá mốc hẹn xanh / đỏ, nhóm tuổi. Tồn lâu nhất trước."""
    d = ev[ev["loai"] == "ton_kt"].copy()
    if d.empty:
        return pd.DataFrame(columns=COT_TON)
    d["tinh_trang"], d["loai_trien_khai"] = _tt(d, "tinh_trang"), _tt(d, "loai_trien_khai")
    d["hen_xanh"] = pd.to_datetime(_tt(d, "hen_xanh").replace("", None), errors="coerce")
    d["hen_do"] = pd.to_datetime(_tt(d, "hen_do").replace("", None), errors="coerce")
    d["tao_luc"] = pd.to_datetime(d["thoi_diem"])
    d["ngay_ton"] = ((now - d["tao_luc"]).dt.total_seconds() / 86400).clip(lower=0).round(1)
    d["qua_xanh"] = d["hen_xanh"].notna() & (d["hen_xanh"] < now)
    d["qua_do"] = d["hen_do"].notna() & (d["hen_do"] < now)
    d["tuoi"] = d["ngay_ton"].map(lambda x: next((t for t, a, b in NHOM_TUOI if a <= x < b), NHOM_TUOI[-1][0]))
    d["nguoi"] = d["nguoi"].fillna("").replace("", "Chưa phân công")
    ma = _tt(d, "ly_do").replace("", "chua_ghi")
    d["ly_do_ma"], d["ly_do"] = ma, ma.map(doc_kt.NHOM_GHI_CHU).fillna("Chưa ghi lý do")
    d["ghi_chu_luc"] = pd.to_datetime(_tt(d, "ghi_chu_luc").replace("", None), errors="coerce")
    d["gio_im_lang"] = ((now - d["ghi_chu_luc"]).dt.total_seconds() / 3600).clip(lower=0).round(1)
    d["phan_tuyen"] = pd.to_numeric(_tt(d, "so_lan_phan_tuyen"), errors="coerce").fillna(0).astype(int)
    return d.sort_values("ngay_ton", ascending=False)[COT_TON].reset_index(drop=True)


def im_lang(t: pd.DataFrame, gio: int = GIO_IM_LANG) -> pd.DataFrame:
    """Ca tồn "im lặng": ghi chú cập nhật cuối đã quá `gio` giờ, hoặc chưa từng có ghi chú mà đã tồn trên 1 ngày. Im lặng lâu nhất trước."""
    if t.empty:
        return t
    chua_ghi = t["ghi_chu_luc"].isna() & (t["ngay_ton"] >= 1)
    d = t[(t["gio_im_lang"] >= gio) | chua_ghi].copy()
    d["gio_im_lang"] = d["gio_im_lang"].fillna(d["ngay_ton"] * 24)             # chưa từng ghi: tính từ lúc tạo phiếu
    return d.sort_values("gio_im_lang", ascending=False).reset_index(drop=True)


def theo_giai_doan(t: pd.DataFrame) -> pd.DataFrame:
    """Hợp đồng tồn đang nằm ở giai đoạn nào (phễu hiện tại): số ca, tuổi tồn trung bình, từ 7 ngày, quá mốc đỏ."""
    rows = []
    for g in GIAI_DOAN_TON + sorted(set(t["tinh_trang"]) - set(GIAI_DOAN_TON) if len(t) else []):
        a = t[t["tinh_trang"] == g] if len(t) else t
        rows.append({"giai_doan": g, "so": len(a), "tuoi_tb": round(float(a["ngay_ton"].mean()), 1) if len(a) else None,
                     "tu_7_ngay": int((a["ngay_ton"] >= TON_LAU_NGAY).sum()) if len(a) else 0, "qua_do": int(a["qua_do"].sum()) if len(a) else 0})
    return pd.DataFrame(rows)


def cham_do_ai(t: pd.DataFrame) -> pd.DataFrame:
    """Ca tồn đang chờ phía nào (nhãn từ ghi chú của KTV, luật từ khoá ở `doc_kt.phan_loai_ghi_chu`): số ca, tỷ lệ, tuổi tồn, im lặng."""
    cot = ["ma", "nhom", "so", "ty_le", "tuoi_tb", "tu_7_ngay", "im_lang", "qua_do"]
    if t.empty:
        return pd.DataFrame(columns=cot)
    il = set(im_lang(t)["so_hd"])
    rows = []
    for m in THU_TU_NHOM:
        a = t[t["ly_do_ma"] == m]
        rows.append({"ma": m, "nhom": doc_kt.NHOM_GHI_CHU[m], "so": len(a), "ty_le": round(100.0 * len(a) / len(t), 1), "tuoi_tb": round(float(a["ngay_ton"].mean()), 1) if len(a) else None,
                     "tu_7_ngay": int((a["ngay_ton"] >= TON_LAU_NGAY).sum()), "im_lang": int(a["so_hd"].isin(il).sum()), "qua_do": int(a["qua_do"].sum())})
    return pd.DataFrame(rows, columns=cot)


def _mo(d: pd.DataFrame, khoa: str) -> pd.Series:
    return pd.to_datetime(_tt(d, khoa).replace("", None), errors="coerce")


def khau_trien_khai(ev: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Thời gian từng khâu (giờ) của các hợp đồng đã triển khai xong. Trả (từng hợp đồng, tóm tắt từng khâu).
    Mốc đảo ngược (khâu sau xảy ra trước khâu trước, do file ghi lệch) không tính vào khâu đó."""
    d = ev[ev["loai"] == "trien_khai"]
    cot = ["khau", "so_mau", "trung_vi", "tb", "lon_nhat"]
    if d.empty:
        return pd.DataFrame(columns=["so_hd"]), pd.DataFrame(columns=cot)
    ct = pd.DataFrame({"so_hd": d["so_hd"].values})
    tom = []
    for a, b, ten in KHAU + [("tao_hd", "online", "Tổng: từ tạo hợp đồng tới online")]:
        gio = ((_mo(d, b).values - _mo(d, a).values) / pd.Timedelta(hours=1))
        gio = pd.Series(gio, dtype="float64").where(lambda x: x >= 0)
        ct[ten] = gio.values
        g = gio.dropna()
        tom.append({"khau": ten, "so_mau": len(g), "trung_vi": round(float(g.median()), 1) if len(g) else None, "tb": round(float(g.mean()), 1) if len(g) else None,
                    "lon_nhat": round(float(g.max()), 1) if len(g) else None})
    return ct, pd.DataFrame(tom, columns=cot)


def ly_do_hen_lai(ev: pd.DataFrame) -> pd.DataFrame:
    """Hợp đồng đã triển khai phải hẹn nhiều lần: lần hẹn lại sau cùng do phía nào (cột "Nguyên nhân tích L2" của file; trống là chưa ghi)."""
    d = ev[ev["loai"] == "trien_khai"]
    d = d[pd.to_numeric(d["so_lan"], errors="coerce") >= 2]
    if d.empty:
        return pd.DataFrame(columns=["nhom", "so"])
    v = _tt(d, "nguyen_nhan_l2").replace({"": "Chưa ghi nguyên nhân"}).value_counts()
    return pd.DataFrame({"nhom": v.index, "so": v.values})


def ton_theo_tuoi(t: pd.DataFrame) -> pd.DataFrame:
    dem = t["tuoi"].value_counts() if len(t) else pd.Series(dtype=int)
    return pd.DataFrame({"nhom": [n for n, _, _ in NHOM_TUOI], "so": [int(dem.get(n, 0)) for n, _, _ in NHOM_TUOI]})


# ------------------------------------------------------------------ KPI theo block
def _ty_le(tu, mau):
    return None if not mau else round(100.0 * tu / mau, 1)


def theo_block(kpi: pd.DataFrame) -> pd.DataFrame:
    """Mỗi block một dòng (cộng các lô), tỷ lệ tự tính lại từ số đếm. Thấp nhất về đúng hẹn lần 1 trước."""
    if kpi.empty:
        return pd.DataFrame(columns=["block", "tong", "tong_l1", "dung_hen_l1_pct", "dung_hen_pct", "qua_hen", "bao_tri_pct", "tgxl_tb", "tin_pnc_pct"])
    g = kpi.groupby("block", sort=False)[["dung_hen_l1", "dung_hen", "qua_hen", "tich_tin_pnc", "bao_tri_24h", "tong_l1", "tong", "tong_tgxl"]].sum().reset_index()
    return pd.DataFrame({"block": g["block"], "tong": g["tong"].astype(int), "tong_l1": g["tong_l1"].astype(int),
                         "dung_hen_l1_pct": [_ty_le(a, b) for a, b in zip(g["dung_hen_l1"], g["tong_l1"])],
                         "dung_hen_pct": [_ty_le(a, b) for a, b in zip(g["dung_hen"], g["tong"])], "qua_hen": g["qua_hen"].astype(int),
                         "bao_tri_pct": [_ty_le(a, b) for a, b in zip(g["bao_tri_24h"], g["tong"])],
                         "tgxl_tb": [None if not b else round(a / b, 1) for a, b in zip(g["tong_tgxl"], g["tong"])],
                         "tin_pnc_pct": [_ty_le(a, b) for a, b in zip(g["tich_tin_pnc"], g["tong"])]}).sort_values("dung_hen_l1_pct", na_position="last").reset_index(drop=True)


# ------------------------------------------------------------------ checklist, triển khai, cáp LAN
def nhom_loi(ev: pd.DataFrame, khoa: str, loai: str = "checklist", top: int = 10) -> pd.DataFrame:
    """Đếm theo một thuộc tính của checklist (phần tử lỗi, nguyên nhân, hướng xử lý, triệu chứng). Ô trống gom thành "Không ghi"."""
    d = ev[ev["loai"] == loai]
    if d.empty:
        return pd.DataFrame(columns=["nhom", "so", "pct"])
    v = _tt(d, khoa).replace({"": "Không ghi", "Không xác định": "Không xác định"})
    dem = v.value_counts().head(top)
    return pd.DataFrame({"nhom": dem.index, "so": dem.values, "pct": (100.0 * dem.values / len(d)).round(1)})


def hop_dong_lap(ev: pd.DataFrame, tu_lan: int = 2) -> pd.DataFrame:
    """Hợp đồng có checklist lặp từ `tu_lan` lần trong 30 ngày (số lần lấy từ file, không tự đếm thêm)."""
    d = ev[ev["loai"] == "checklist"]
    if d.empty:
        return pd.DataFrame(columns=["so_hd", "nguoi", "so_lan", "phan_tu_loi", "nguyen_nhan", "gan_nhat"])
    d = d.assign(phan_tu_loi=_tt(d, "phan_tu_loi"), nguyen_nhan=_tt(d, "nguyen_nhan_loi")).sort_values("thoi_diem")
    g = d.groupby("so_hd").agg(nguoi=("nguoi", "last"), so_lan=("so_lan", "max"), phan_tu_loi=("phan_tu_loi", "last"), nguyen_nhan=("nguyen_nhan", "last"),
                               gan_nhat=("thoi_diem", "max")).reset_index()
    return g[g["so_lan"] >= tu_lan].sort_values(["so_lan", "gan_nhat"], ascending=False).reset_index(drop=True)


def cap_lan(ev: pd.DataFrame) -> dict:
    """Cáp LAN: bao nhiêu hợp đồng kích hoạt bằng LAN so với WIFI, và lý do không dùng LAN."""
    d = ev[ev["loai"] == "cap_lan"]
    if d.empty:
        return {"tong": 0, "lan": 0, "wifi": 0, "pct_lan": None, "ly_do": pd.DataFrame(columns=["nhom", "so", "pct"])}
    kieu = _tt(d, "active_by").str.upper()
    ly_do = _tt(d, "nguyen_nhan").replace({"": "Không ghi", "Không chọn nguyên nhân": "Không ghi"})
    ly_do = ly_do[kieu != "LAN"].value_counts()
    return {"tong": len(d), "lan": int((kieu == "LAN").sum()), "wifi": int((kieu == "WIFI").sum()), "pct_lan": _ty_le((kieu == "LAN").sum(), len(d)),
            "ly_do": pd.DataFrame({"nhom": ly_do.index, "so": ly_do.values, "pct": [_ty_le(x, ly_do.sum()) for x in ly_do.values]})}


def trien_khai(ev: pd.DataFrame) -> pd.DataFrame:
    """Hợp đồng đã triển khai xong (file "triển khai đúng hạn"): số lần hẹn, có đúng hẹn không, thời gian xử lý 72 giờ."""
    d = ev[ev["loai"] == "trien_khai"]
    if d.empty:
        return pd.DataFrame(columns=["so_hd", "nguoi", "so_lan", "dung_hen", "tgxl_72h", "xong_luc"])
    return pd.DataFrame({"so_hd": d["so_hd"].values, "nguoi": d["nguoi"].fillna("").values, "so_lan": pd.to_numeric(d["so_lan"], errors="coerce").values,
                         "dung_hen": (~d["chi_tiet"].fillna("").str.contains("không đúng hẹn")).values,
                         "tgxl_72h": pd.to_numeric(_tt(d, "tgxl_72h"), errors="coerce").values, "xong_luc": d["thoi_diem"].values}).sort_values("so_lan", ascending=False)


# ------------------------------------------------------------------ KTV
def theo_ktv(ev: pd.DataFrame, now: pd.Timestamp) -> pd.DataFrame:
    """Một dòng mỗi KTV: tồn, quá mốc hẹn, checklist (lỗi sớm / lặp), triển khai không đúng hẹn. Nhiều tồn trước."""
    t = ton(ev, now)
    cot = ["ktv", "ton", "ton_lau", "qua_xanh", "qua_do", "tuoi_tb", "checklist", "hd_lap", "sau_tk", "khong_dung_hen"]
    ds = ev[ev["nguoi"].fillna("").ne("")]
    if ds.empty and t.empty:
        return pd.DataFrame(columns=cot)
    ma = sorted(set(ds["nguoi"]) | set(t.loc[t["nguoi"].ne("Chưa phân công"), "nguoi"]))
    cl, lap, stk, tk = ds[ds["loai"] == "checklist"], hop_dong_lap(ev), ds[ds["loai"] == "checklist_sau_tk"], trien_khai(ev)
    rows = []
    for m in ma:
        a = t[t["nguoi"] == m]
        rows.append({"ktv": m, "ton": len(a), "ton_lau": int((a["ngay_ton"] >= TON_LAU_NGAY).sum()), "qua_xanh": int(a["qua_xanh"].sum()), "qua_do": int(a["qua_do"].sum()),
                     "tuoi_tb": round(a["ngay_ton"].mean(), 1) if len(a) else None, "checklist": int((cl["nguoi"] == m).sum()),
                     "hd_lap": int((lap["nguoi"] == m).sum()), "sau_tk": int((stk["nguoi"] == m).sum()),
                     "khong_dung_hen": int(((tk["nguoi"] == m) & ~tk["dung_hen"]).sum())})
    return pd.DataFrame(rows, columns=cot).sort_values(["ton", "checklist"], ascending=False).reset_index(drop=True)


# ------------------------------------------------------------------ tổng hợp và nhận định
def tom_tat(ev: pd.DataFrame, kpi: pd.DataFrame, now: pd.Timestamp) -> dict:
    t = ton(ev, now)
    tong, tong_l1 = float(kpi["tong"].sum()), float(kpi["tong_l1"].sum())
    cl = ev[ev["loai"] == "checklist"]
    return {"so_ton": len(t), "ton_lau": int((t["ngay_ton"] >= TON_LAU_NGAY).sum()), "qua_xanh": int(t["qua_xanh"].sum()), "qua_do": int(t["qua_do"].sum()),
            "tuoi_tb": round(t["ngay_ton"].mean(), 1) if len(t) else None,
            "dung_hen_pct": _ty_le(kpi["dung_hen"].sum(), tong), "dung_hen_l1_pct": _ty_le(kpi["dung_hen_l1"].sum(), tong_l1),
            "bao_tri_pct": _ty_le(kpi["bao_tri_24h"].sum(), tong), "tgxl_tb": None if not tong else round(float(kpi["tong_tgxl"].sum()) / tong, 1),
            "so_lan_hen": int(tong), "hd_checklist": int(cl["so_hd"].nunique()), "hd_lap": len(hop_dong_lap(ev)),
            "hd_lap3": len(hop_dong_lap(ev, 3)), "pct_lan": cap_lan(ev)["pct_lan"]}


def _nd(muc: str, chu_de: str, tieu_de: str, noi_dung: str, goi_y: str = "") -> dict:
    return {"muc": muc, "chu_de": chu_de, "tieu_de": tieu_de, "noi_dung": noi_dung, "goi_y": goi_y}


def nhan_dinh(ev: pd.DataFrame, kpi: pd.DataFrame, now: pd.Timestamp) -> list[dict]:
    """Nhận định do LUẬT cố định viết (không dùng AI), ngưỡng nằm đầu file. Nghiêm trọng trước."""
    s, blk, ktv = tom_tat(ev, kpi, now), theo_block(kpi), theo_ktv(ev, now)
    kq = []
    if s["qua_do"]:
        kq.append(_nd("Nghiêm trọng", "Tồn và lịch hẹn", f"{s['qua_do']} hợp đồng đã quá mốc hẹn đỏ mà vẫn còn tồn",
                      f"Trong {s['so_ton']} hợp đồng tồn Kỹ thuật, {s['qua_do']} hợp đồng đã qua mốc hẹn đỏ ({s['qua_xanh']} hợp đồng đã qua mốc hẹn xanh).",
                      "Đội trưởng rà từng hợp đồng quá mốc đỏ, chốt lại lịch hẹn hoặc đổi người."))
    if s["so_ton"] and s["ton_lau"] >= max(3, 0.2 * s["so_ton"]):
        kq.append(_nd("Cần chú ý", "Tồn và lịch hẹn", f"{s['ton_lau']} hợp đồng tồn từ {TON_LAU_NGAY} ngày trở lên",
                      f"Chiếm {_n(100 * s['ton_lau'] / s['so_ton'])}% số hợp đồng tồn; tuổi tồn trung bình {_n(s['tuoi_tb'], 1)} ngày.",
                      "Hỏi nguyên nhân từng ca (khách hẹn lại, thiếu vật tư, chưa có tuyến) và đưa vào việc liên khối nếu cần Kinh doanh hoặc DVKH can thiệp."))
    if s["dung_hen_l1_pct"] is not None and s["dung_hen_l1_pct"] < DUNG_HEN_L1_THAP:
        kq.append(_nd("Cần chú ý", "Triển khai đúng hẹn", f"Đúng hẹn lần 1 chỉ {_n(s['dung_hen_l1_pct'], 1)}%",
                      f"Đúng hẹn chung (kể cả hẹn lại) là {_n(s['dung_hen_pct'], 1)}%: nhiều hợp đồng phải hẹn lại lần hai mới đúng.",
                      "Xem block có tỷ lệ lần 1 thấp nhất để biết hẹn lần đầu bị lệch vì khâu nào."))
    dang_xet = blk[blk["tong_l1"] >= TOI_THIEU_BLOCK].dropna(subset=["dung_hen_l1_pct"])
    if len(dang_xet) >= 3:
        x = dang_xet.iloc[0]
        kq.append(_nd("Thông tin", "Triển khai đúng hẹn", f"{x['block']} thấp nhất: đúng hẹn lần 1 {_n(x['dung_hen_l1_pct'], 1)}%",
                      f"Trong {len(dang_xet)} block đủ {TOI_THIEU_BLOCK} lần hẹn trở lên, block này thấp nhất (chung {_n(s['dung_hen_l1_pct'], 1)}%)."))
    if s["bao_tri_pct"] is not None and s["bao_tri_pct"] > BAO_TRI_24H_CAO:
        kq.append(_nd("Cần chú ý", "Chất lượng sau lắp", f"{_n(s['bao_tri_pct'], 1)}% hợp đồng phải bảo trì sau 24 giờ",
                      "Tỷ lệ bảo trì quá 24 giờ cao là dấu hiệu lắp đặt chưa đạt ngay lần đầu.", "Đối chiếu với danh sách checklist lặp để tìm phần tử lỗi chung."))
    lap = hop_dong_lap(ev)
    if len(lap):
        ro = nhom_loi(ev, "phan_tu_loi")
        ro = ro[~ro["nhom"].isin(["Không xác định", "Không ghi"])]
        top = ro.iloc[0] if len(ro) else None
        kq.append(_nd("Nghiêm trọng" if s["hd_lap3"] >= 5 else "Cần chú ý", "Sự cố lặp", f"{len(lap)} hợp đồng có checklist lặp từ 2 lần ({s['hd_lap3']} hợp đồng từ 3 lần)",
                      f"Phần tử lỗi hay gặp nhất: {top['nhom']} ({_n(top['pct'], 1)}% số checklist)." if top is not None else "Phần lớn checklist chưa ghi rõ phần tử lỗi.",
                      "Các hợp đồng này đã tự vào danh sách việc của Điều hành liên khối (luật Sự cố lặp)."))
    if len(ktv) and s["so_ton"] >= TOI_THIEU_KTV_TON * 2:
        x = ktv.iloc[0]
        if x["ton"] >= TOI_THIEU_KTV_TON and x["ton"] >= 0.25 * s["so_ton"]:
            kq.append(_nd("Thông tin", "Hiệu suất KTV", f"{x['ktv']} đang giữ {x['ton']} hợp đồng tồn",
                          f"Chiếm {_n(100 * x['ton'] / s['so_ton'])}% số hợp đồng tồn của cả đội; {x['qua_do']} hợp đồng quá mốc đỏ.", "Cân nhắc chia lại việc."))
    if s["dung_hen_pct"] is not None and s["dung_hen_pct"] >= DUNG_HEN_THAP and not s["qua_do"]:
        kq.append(_nd("Tốt", "Triển khai đúng hẹn", f"Đúng hẹn {_n(s['dung_hen_pct'], 1)}% và không có hợp đồng nào quá mốc đỏ", "Giữ nhịp hiện tại."))
    t = ton(ev, now)
    cd = cham_do_ai(t)
    if len(t) >= 10 and len(cd):
        co_ly_do = cd[cd["ma"] != "chua_ghi"]
        khach = cd.loc[cd["ma"] == "khach", "so"].iloc[0]
        if khach >= 0.25 * len(t):
            kq.append(_nd("Thông tin", "Chậm do ai", f"{int(khach)} ca tồn ({_n(100 * khach / len(t))}%) đang chờ phía khách hàng",
                          "Khách hẹn lại, nhà chưa xây xong, chưa có điện hoặc không nghe máy. Đây chưa phải lỗi của Kỹ thuật.",
                          "Đừng chấm các ca này là Kỹ thuật chậm; nhờ Kinh doanh gọi khách chốt lịch cụ thể."))
        chua = cd.loc[cd["ma"] == "chua_ghi", "so"].iloc[0]
        if chua >= 0.4 * len(t):
            kq.append(_nd("Cần chú ý", "Chậm do ai", f"{int(chua)} ca tồn ({_n(100 * chua / len(t))}%) chưa ghi lý do",
                          "Không có ghi chú, hoặc chỉ có dòng phân tuyến, nên không biết ca đang chờ ai.", "Yêu cầu KTV ghi lý do mỗi lần liên hệ khách, kể cả khi chưa lắp được."))
        if len(co_ly_do) and (co_ly_do["ma"] == "kinh_doanh").any() and co_ly_do.loc[co_ly_do["ma"] == "kinh_doanh", "so"].iloc[0]:
            n_kd = int(co_ly_do.loc[co_ly_do["ma"] == "kinh_doanh", "so"].iloc[0])
            kq.append(_nd("Cần chú ý", "Chậm do ai", f"{n_kd} ca tồn đang chờ Kinh doanh", "Chờ sale xử lý hoá đơn, thanh toán hoặc liên hệ khách.", "Chuyển danh sách này cho trưởng phòng Kinh doanh."))
    n_im = len(im_lang(t))
    if n_im >= 5:
        kq.append(_nd("Cần chú ý", "Chậm do ai", f"{n_im} ca tồn không có cập nhật quá {GIO_IM_LANG} giờ", "Ghi chú cuối đã cũ hoặc chưa từng có.", "Đội trưởng nhắc KTV cập nhật tình trạng từng ca."))
    _ct, kh = khau_trien_khai(ev)
    kh = kh[(kh["so_mau"] >= TOI_THIEU_KHAU) & ~kh["khau"].str.startswith("Tổng")].dropna(subset=["trung_vi"])
    if len(kh):
        x = kh.sort_values("trung_vi", ascending=False).iloc[0]
        kq.append(_nd("Thông tin", "Phễu triển khai", f"Khâu chậm nhất: {x['khau']} (trung vị {_n(x['trung_vi'], 1)} giờ)", f"Tính trên {int(x['so_mau'])} hợp đồng đã triển khai xong."))
    thu_tu = {"Nghiêm trọng": 0, "Cần chú ý": 1, "Thông tin": 2, "Tốt": 3}
    return sorted(kq, key=lambda x: thu_tu[x["muc"]])

