"""Luật liên khối: từ sự kiện của các khối sinh ra VIỆC, ghi rõ giao cho ai và vì sao (nhánh thi-lien-khoi, 14/11/2026).

Bốn luật (ngưỡng ở `config/rules.yml` → `lien_khoi`, không nằm trong code):
- `cho_online`: hợp đồng đã tạo nhưng chưa online sau N ngày (Kinh doanh -> Kỹ thuật + sale).
- `loi_som`: vừa online xong đã có SR khiếu nại của DVKH hoặc checklist sau triển khai của Kỹ thuật (cả ba khối cùng biết).
- `su_co_lap`: Kỹ thuật ghi checklist lặp từ 2 lần (DVKH gọi hỏi thăm từ xa trước, Kỹ thuật chỉ đến nhà khi cần).
- `co_y_roi`: khách nói muốn thanh lý / không ở lại (mức Cao), hoặc đang suy nghĩ / điểm nguy cơ rời mạng cao mà SR còn mở (mức Trung bình).
  Nợ cước chỉ ghi thêm vào lý do, KHÔNG nâng mức: danh sách nợ cước của file DVKH có tới ~55 nghìn hợp đồng, gần như mọi khách đều nằm trong đó.

Mỗi luật là hàm thuần nhận DataFrame (dễ kiểm thử, không đọc database). Người nhận chưa biết thì ghi tên hàng chờ thay vì để trống:
sale lấy từ file bán hàng, người DVKH là "Nhân sự AU" của SR gần nhất (chỉ có cho hợp đồng đã có SR), KTV là người trong sự kiện Kỹ thuật gần nhất.
Việc không chứa tên khách hàng. Số liệu lấy qua `nguon.py` (thật hoặc minh hoạ).
"""
from __future__ import annotations

import pandas as pd

from app.bo_nho import nho
from app.config import rules_config
from app.lien_khoi import nguon
from app.lien_khoi import su_kien as sk
from app.lien_khoi.su_kien import chuan_hd

CAO, TB = "Cao", "Trung bình"
GIAO_KT = "Hàng chờ Kỹ thuật"
GIAO_DVKH = "Hàng chờ đội trưởng DVKH"
KHONG_CO_SALE = "Không có trong file bán hàng"
TEN_LUAT = {"cho_online": "Chờ online lâu", "loi_som": "Lỗi sớm sau lắp", "su_co_lap": "Sự cố lặp", "co_y_roi": "Khách có ý rời"}
DE_XUAT = {"cho_online": "Kỹ thuật xếp lịch lắp, sale báo khách tiến độ",
           "loi_som": "Kỹ thuật kiểm tra lại đường truyền, DVKH gọi hỏi thăm, sale cùng giữ khách",
           "su_co_lap": "DVKH gọi hỏi thăm từ xa trước, Kỹ thuật chỉ đến nhà khi cần, sale nắm tình hình",
           "co_y_roi": "DVKH liên hệ giữ khách, sale cùng theo dõi"}
COT_VIEC = ["so_hd", "luat", "ten_luat", "muc", "giao_sale", "giao_dvkh", "giao_kt", "han", "phat_sinh", "ly_do", "de_xuat"]


def cau_hinh(ten: str) -> dict:
    return (rules_config().get("lien_khoi") or {}).get(ten) or {}


def _ngay(t) -> str:
    return "" if pd.isna(t) else pd.Timestamp(t).strftime("%d/%m")


def _viec(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=COT_VIEC)


def _dong(luat: str, **kw) -> dict:
    return dict(luat=luat, ten_luat=TEN_LUAT[luat], de_xuat=DE_XUAT[luat], **kw)


def _kt(kt: pd.DataFrame | None) -> pd.DataFrame:
    return kt if kt is not None else pd.DataFrame(columns=nguon.COT_KT)


def nguoi_dvkh(bd: pd.DataFrame, cd: pd.DataFrame) -> dict[str, str]:
    """Mã hợp đồng -> "Nhân sự AU" của SR gần nhất (cả bị động lẫn chủ động). Hợp đồng chưa có SR thì không có trong từ điển."""
    phan = []
    if len(bd):
        phan.append(pd.DataFrame({"so_hd": chuan_hd(bd["so_hd"]), "t": bd["tg_yc"], "n": bd["nhan_su_au"]}))
    if len(cd):
        phan.append(pd.DataFrame({"so_hd": chuan_hd(cd["so_hd"]), "t": cd["tg_do"], "n": cd["nhan_su_au"]}))
    if not phan:
        return {}
    p = pd.concat(phan, ignore_index=True)
    p = p[p["n"].fillna("").ne("")].sort_values("t")
    return dict(zip(p["so_hd"], p["n"]))             # dòng sau đè dòng trước -> còn lại SR gần nhất


def nguoi_kt(kt: pd.DataFrame | None) -> dict[str, str]:
    """Mã hợp đồng -> KTV trong sự kiện Kỹ thuật gần nhất có ghi tên người."""
    k = _kt(kt)
    if k.empty:
        return {}
    k = k[k["nguoi"].fillna("").ne("")].sort_values("thoi_diem")
    return dict(zip(chuan_hd(k["so_hd"]), k["nguoi"]))


def luat_cho_online(kd: pd.DataFrame, ngay_tc: pd.Timestamp, so_ngay: int = 2, cao_tu: int = 7, han: str = "",
                    kt: pd.DataFrame | None = None) -> pd.DataFrame:
    if kd.empty:
        return _viec([])
    d = kd[kd["ton"] & kd["ngay_tao"].notna() & kd["ngay_huy"].isna() & kd["phong"].ne("NGOAI_CN")
           & kd["tinh_trang"].ne("Đã chấm dứt hợp đồng")].copy()      # HĐ của chi nhánh khác bán hộ không phải việc của Đà Nẵng
    d["cho"] = (ngay_tc - d["ngay_tao"].dt.normalize()).dt.days
    d = d[d["cho"] >= so_ngay]
    k = _kt(kt)
    ton_kt = k[k["loai"] == "ton_kt"].sort_values("thoi_diem")
    ct_kt = dict(zip(chuan_hd(ton_kt["so_hd"]), ton_kt["chi_tiet"])) if len(ton_kt) else {}
    ktv = nguoi_kt(k)
    return _viec([_dong("cho_online", so_hd=r.so_hd, muc=CAO if r.cho >= cao_tu else TB, giao_sale=r.sale or KHONG_CO_SALE, giao_dvkh="",
                        giao_kt=ktv.get(r.so_hd) or GIAO_KT, han=han, phat_sinh=r.ngay_tao,
                        ly_do=f"Tạo {_ngay(r.ngay_tao)}, đến {_ngay(ngay_tc)} đã {int(r.cho)} ngày chưa online" + (f" (gói {r.goi})" if r.goi else "")
                              + (f"; {ct_kt[r.so_hd]}" if r.so_hd in ct_kt else ""))
                  for r in d.itertuples()])


def luat_loi_som(kd: pd.DataFrame, bd: pd.DataFrame, so_ngay: int = 30, loai_yc=("Khiếu nại, phàn nàn",), han: str = "",
                 dvkh: dict | None = None, kt: pd.DataFrame | None = None) -> pd.DataFrame:
    """Hợp đồng online xong trong `so_ngay` ngày đã có SR bị động thuộc `loai_yc` (DVKH) hoặc checklist sau triển khai (Kỹ thuật).
    Từ 2 dấu hiệu trở lên (SR lặp, hoặc cả hai khối cùng ghi nhận) là mức Cao."""
    on = kd[kd["ngay_online"].notna()][["so_hd", "ngay_online", "sale"]] if not kd.empty else kd
    phan = []
    if len(bd):
        x = bd[bd["loai_yc"].isin(list(loai_yc))]
        phan.append(pd.DataFrame({"so_hd": chuan_hd(x["so_hd"]), "t": x["tg_yc"],
                                  "mo_ta": "SR \"" + x["loai_yc"].fillna("") + "\" (tình trạng: " + x["tinh_trang"].fillna("").replace("", "chưa rõ") + ")"}))
    k = _kt(kt)
    sau_tk = k[k["loai"] == "checklist_sau_tk"]
    if len(sau_tk):
        phan.append(pd.DataFrame({"so_hd": chuan_hd(sau_tk["so_hd"]), "t": sau_tk["thoi_diem"], "mo_ta": "checklist sau triển khai của Kỹ thuật"}))
    if on.empty or not phan:
        return _viec([])
    x = pd.concat(phan, ignore_index=True).merge(on, on="so_hd")
    x["sau"] = (x["t"].dt.normalize() - x["ngay_online"]).dt.days
    x = x[(x["sau"] >= 0) & (x["sau"] <= so_ngay)].sort_values("t")
    dvkh, ktv = dvkh or {}, nguoi_kt(k)
    rows = []
    for so_hd, g in x.groupby("so_hd", sort=False):
        a = g.iloc[0]
        rows.append(_dong("loi_som", so_hd=so_hd, muc=CAO if len(g) >= 2 else TB, giao_sale=a["sale"] or KHONG_CO_SALE,
                          giao_dvkh=dvkh.get(so_hd) or GIAO_DVKH, giao_kt=ktv.get(so_hd) or GIAO_KT, han=han, phat_sinh=a["t"],
                          ly_do=f"Online {_ngay(a['ngay_online'])}, sau {int(a['sau'])} ngày có {a['mo_ta']}"
                                + (f"; tổng {len(g)} dấu hiệu trong {so_ngay} ngày đầu" if len(g) >= 2 else "")))
    return _viec(rows)


def luat_su_co_lap(kd: pd.DataFrame, kt: pd.DataFrame | None, bd: pd.DataFrame, tu_lan: int = 2, cao_tu_lan: int = 3, han: str = "",
                   dvkh: dict | None = None) -> pd.DataFrame:
    """Kỹ thuật ghi checklist lặp (cùng hợp đồng) từ `tu_lan` lần. Mức Cao: lặp từ `cao_tu_lan` lần hoặc DVKH cũng có SR khiếu nại cùng hợp đồng."""
    k = _kt(kt)
    k = k[k["loai"] == "checklist"]
    if k.empty:
        return _viec([])
    k = k.assign(so_hd=chuan_hd(k["so_hd"])).sort_values("thoi_diem")
    kn = set(chuan_hd(bd.loc[bd["loai_yc"].eq("Khiếu nại, phàn nàn"), "so_hd"])) if len(bd) else set()
    sale = dict(zip(kd["so_hd"], kd["sale"])) if len(kd) else {}
    da_cham_dut = set(kd.loc[kd["tinh_trang"].eq("Đã chấm dứt hợp đồng"), "so_hd"]) if len(kd) else set()
    dvkh = dvkh or {}
    rows = []
    for so_hd, g in k.groupby("so_hd", sort=False):
        n = int(max(pd.to_numeric(g["so_lan"], errors="coerce").max() if g["so_lan"].notna().any() else 0, len(g)))
        if n < tu_lan or so_hd in da_cham_dut:
            continue
        ktv = next((x for x in reversed(g["nguoi"].fillna("").tolist()) if x), "")
        co_kn = so_hd in kn
        rows.append(_dong("su_co_lap", so_hd=so_hd, muc=CAO if (n >= cao_tu_lan or co_kn) else TB, giao_sale=sale.get(so_hd) or KHONG_CO_SALE,
                          giao_dvkh=dvkh.get(so_hd) or GIAO_DVKH, giao_kt=ktv or GIAO_KT, han=han, phat_sinh=g["thoi_diem"].max(),
                          ly_do=f"Kỹ thuật ghi checklist lặp {n} lần (lần gần nhất {_ngay(g['thoi_diem'].max())})"
                                + ("; DVKH cũng có SR khiếu nại của khách" if co_kn else "")))
    return _viec(rows)


def luat_co_y_roi(bd: pd.DataFrame, cd: pd.DataFrame, kd: pd.DataFrame, no_cuoc: set[str], so_ngay_gan: int = 3,
                  diem_cao: float = 800, han: str = "", dvkh: dict | None = None) -> pd.DataFrame:
    """Khách có ý rời trong `so_ngay_gan` ngày gần nhất của dữ liệu DVKH (chỉ việc MỚI). Hợp đồng đã chấm dứt thì bỏ (hết việc để giữ).
    Mức Cao: khách nói không ở lại hoặc yêu cầu thanh lý mà chưa giữ được. Trung bình: khách đang suy nghĩ, hoặc điểm nguy cơ cao mà SR còn mở."""
    ts = [t for t in (bd["tg_yc"].max() if len(bd) else pd.NaT, cd["tg_do"].max() if len(cd) else pd.NaT) if pd.notna(t)]
    if not ts:
        return _viec([])
    moc = max(ts).normalize() - pd.Timedelta(days=so_ngay_gan)
    phan = []
    if len(bd):
        tv = bd["ket_qua_tu_van"].fillna("")
        giu_duoc = tv.str.startswith("Khách hàng đồng ý")           # "không đồng ý" cũng chứa chữ "đồng ý": chỉ lấy câu bắt đầu bằng đồng ý
        manh = tv.str.contains("không đồng ý") | (bd["loai_yc"].eq("Thanh lý") & ~giu_duoc & ~tv.eq("Khách hàng đang suy nghĩ"))
        b = bd[(manh | tv.eq("Khách hàng đang suy nghĩ")) & ~bd["net_hien"].eq("Đã chấm dứt hợp đồng") & (bd["tg_yc"] >= moc)]
        phan.append(pd.DataFrame({"so_hd": chuan_hd(b["so_hd"]), "t": b["tg_yc"], "n": b["nhan_su_au"].fillna(""), "cao": manh[b.index],
                                  "ly": "SR bị động \"" + b["loai_yc"].fillna("") + "\"" + tv[b.index].map(lambda v: f" - {v}" if v else "")}))
    if len(cd):
        tvc = cd["ket_qua_tu_van"].fillna("")
        yeu = tvc.str.contains("yêu cầu thanh lý", case=False)
        diem = cd["diem_rm"].fillna(-1)
        mo = cd["tinh_trang"].isin(("Chưa xử lý", "Đang xử lý", "Chưa phân công"))
        sos = cd["nhom_ct"].eq("Nguy cơ rời mạng (SOS)") & (diem >= diem_cao) & mo
        c = cd[(yeu | sos) & (cd["tg_do"] >= moc)]
        ly = pd.Series(["SR chủ động: khách yêu cầu thanh lý" if y else f"SR chủ động: điểm nguy cơ rời mạng {int(d)}"
                        for y, d in zip(yeu[c.index], diem[c.index])], index=c.index, dtype=str)
        phan.append(pd.DataFrame({"so_hd": chuan_hd(c["so_hd"]), "t": c["tg_do"], "n": c["nhan_su_au"].fillna(""), "cao": yeu[c.index], "ly": ly}))
    phan = [p for p in phan if len(p)]
    if not phan:
        return _viec([])
    p = pd.concat(phan, ignore_index=True).sort_values("t")
    sale = dict(zip(kd["so_hd"], kd["sale"])) if len(kd) else {}
    da_cham_dut = set(kd.loc[kd["tinh_trang"].eq("Đã chấm dứt hợp đồng"), "so_hd"]) if len(kd) else set()
    dvkh = dvkh or {}
    rows = []
    for so_hd, g in p.groupby("so_hd", sort=False):
        if so_hd in da_cham_dut:
            continue
        nguoi = next((n for n in reversed(g["n"].tolist()) if n), "") or dvkh.get(so_hd, "")
        no = so_hd in no_cuoc
        rows.append(_dong("co_y_roi", so_hd=so_hd, muc=CAO if g["cao"].any() else TB, giao_sale=sale.get(so_hd) or KHONG_CO_SALE,
                          giao_dvkh=nguoi or GIAO_DVKH, giao_kt="", han=han, phat_sinh=g["t"].max(),
                          ly_do="; ".join(dict.fromkeys(g["ly"])) + ("; nằm trong danh sách nợ cước của DVKH" if no else "")))
    return _viec(rows)


def no_cuoc_dvkh(cd: pd.DataFrame) -> set[str]:
    """Hợp đồng nợ cước: danh sách nợ cước của file DVKH cộng cờ nợ cước trên SR chủ động."""
    ds = sk.danh_sach_dvkh()
    tap = set(chuan_hd(ds.loc[ds["loai"] == "no_cuoc", "so_hd"])) if len(ds) else set()
    if len(cd) and "no_cuoc" in cd.columns:
        tap |= set(chuan_hd(cd.loc[cd["no_cuoc"].fillna(0).astype(int) == 1, "so_hd"]))
    return tap


def ngay_tham_chieu_kd(kd: pd.DataFrame) -> pd.Timestamp:
    """Số bán hàng chỉ có đến một ngày: "chờ bao nhiêu ngày" tính tới ngày đó chứ không phải hôm nay."""
    ts = [t for c in ("ngay_tao", "ngay_online") for t in ([kd[c].max()] if len(kd) else []) if pd.notna(t)]
    return max(ts).normalize() if ts else pd.Timestamp.today().normalize()


@nho("so_lieu", 60)
def danh_sach_viec() -> pd.DataFrame:
    """Việc của mọi luật, mức Cao trước, việc chờ lâu nhất trước."""
    kd, bd, cd, kt = nguon.kd(), nguon.sr_bi_dong(), nguon.sr_chu_dong(), nguon.kt()
    han = f"Trong {int((rules_config().get('lien_khoi') or {}).get('han_gio', 24))} giờ"
    dvkh = nguoi_dvkh(bd, cd)
    a, b, s, c = cau_hinh("cho_online"), cau_hinh("loi_som"), cau_hinh("su_co_lap"), cau_hinh("co_y_roi")
    ngay_tc = nguon.ngay_tham_chieu() or ngay_tham_chieu_kd(kd)
    ds = [luat_cho_online(kd, ngay_tc, int(a.get("so_ngay", 2)), int(a.get("cao_tu", 7)), han, kt),
          luat_loi_som(kd, bd, int(b.get("so_ngay", 30)), tuple(b.get("loai_yc") or ("Khiếu nại, phàn nàn",)), han, dvkh, kt),
          luat_su_co_lap(kd, kt, bd, int(s.get("tu_lan", 2)), int(s.get("cao_tu_lan", 3)), han, dvkh),
          luat_co_y_roi(bd, cd, kd, no_cuoc_dvkh(cd), int(c.get("so_ngay_gan", 3)), float(c.get("diem_rm_cao", 800)), han, dvkh)]
    ds = [d for d in ds if len(d)]
    if not ds:
        return _viec([])
    v = pd.concat(ds, ignore_index=True)
    v["_t"] = v["muc"].map({CAO: 0, TB: 1})
    return v.sort_values(["_t", "phat_sinh"], kind="stable").drop(columns="_t").reset_index(drop=True)


def tom_tat(v: pd.DataFrame) -> dict:
    """Số liệu đầu trang: tổng việc, mức Cao, việc chưa biết người DVKH, số việc theo luật."""
    if v.empty:
        return {"tong": 0, "cao": 0, "hang_cho_dvkh": 0, "theo_luat": {}}
    return {"tong": int(len(v)), "cao": int((v["muc"] == CAO).sum()),
            "hang_cho_dvkh": int((v["giao_dvkh"] == GIAO_DVKH).sum()),
            "theo_luat": {k: int((v["luat"] == k).sum()) for k in TEN_LUAT}}
