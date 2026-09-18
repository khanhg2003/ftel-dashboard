"""Tín hiệu insight app TÍNH SẴN cho Fox (trợ lý AI) - để Fox nhận định, không phải tự dò bảng số.

- `boi_canh_chung`: bức tranh tháng dùng chung cho MỌI trang (Báo cáo Tổng, Báo cáo phòng, Phân tích, chat) để
  mỗi trang hiểu bối cảnh của nhau: tiến độ, phòng rủi ro, chất lượng bán, tốc độ triển khai, nhân sự đáng lo.
- `tin_hieu_phan_tich`: lăng kính chất lượng & vận hành: tốc độ triển khai theo khu vực kỹ thuật (CN Quản lý),
  phòng làm tụt tỷ lệ, cơ cấu gói, sale yếu làm phòng chững lại.
Mọi phần theo phạm vi quyền của người hỏi. Trưởng phòng và người đã nghỉ không bị nêu tên (canh_bao.acc_khong_xet).
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from app import phan_tich as pt
from app.du_bao import du_bao_thang
from app.org import phong_order

KHU_VUC = {"DNG_01": "Đà Nẵng 1 (DNG_01)", "DNG_02": "Đà Nẵng 2 (DNG_02)", "QNM": "Quảng Nam (QNM)"}
TY_LE = {"kem_vvip": "bán kèm V.VIP", "kem_camera": "bán kèm Camera", "tra_truoc": "trả trước",
         "onl_1_ngay": "online trong 1 ngày"}
MAU_TOI_THIEU = 30          # phòng / khu vực dưới 30 hợp đồng: không so tỷ lệ
DOI_DANG_KE = 10            # tỷ lệ đổi từ 10 điểm % mới nêu
_cache: dict = {}
_phien: dict = {"luc": 0.0, "gia_tri": None}


def _phien_so_lieu() -> str:
    """Phiên số liệu (đổi khi nạp file / sửa mục tiêu), đọc lại tối đa mỗi 20 giây cho đỡ truy vấn."""
    import time
    from app.tro_ly import phien_du_lieu
    if time.monotonic() - _phien["luc"] > 20:
        _phien.update(luc=time.monotonic(), gia_tri=phien_du_lieu())
    return _phien["gia_tri"]


def nho(ten: str, khoa: tuple, ham):
    """Nhớ kết quả trong phiên số liệu hiện tại: một lần dựng nhận xét / chat không tính lại cùng một bảng."""
    k = (_phien_so_lieu(), ten, khoa)
    if k not in _cache:
        if len(_cache) > 128:
            _cache.clear()
        _cache[k] = ham()
    return _cache[k]


def _tuple(x):
    return tuple(x) if x is not None else None


def _hieu_suat(thang: str, pham_vi, ngay: int):
    from app.hr_metrics import hieu_suat_nhan_su
    return nho("hieu_suat", (thang, _tuple(pham_vi), ngay),
               lambda: hieu_suat_nhan_su(thang, chi_phong=pham_vi, ngay=ngay))


def _so(v) -> str:
    return f"{int(round(v)):,}".replace(",", ".")


def _pct(a, b) -> float | None:
    return round(a / b * 100) if b else None


def _hai_ky(d: date, scope) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    def dung():
        thang = f"{d.year}-{d.month:02d}"
        nay = pt.hop_dong_online(f"{thang}-01", d.isoformat(), scope)
        tu_t, den_t = pt.cung_ky_thang_truoc(thang, d.day)
        return nay, pt.hop_dong_online(tu_t, den_t, scope), f"cùng kỳ 01-{den_t[8:]}/{den_t[5:7]}"
    return nho("hai_ky", (d, _tuple(scope)), dung)


def _ty_le(df: pd.DataFrame) -> dict:
    c = pt.chi_so_chung(df)
    return {k: c.get(k) for k in TY_LE}


def _khu_vuc(df: pd.DataFrame) -> pd.Series:
    return df.cn_quan_ly.fillna("").map(lambda x: x if x in KHU_VUC else "NGOAI_TINH")


def trien_khai(nay: pd.DataFrame, ck: pd.DataFrame) -> list[str]:
    """Tốc độ triển khai (% online trong 1 ngày kể từ lúc tạo hợp đồng, số ngày chờ bình quân) theo khu vực kỹ
    thuật - khu vực = CN Quản lý của khách, là nơi kỹ thuật triển khai."""
    if nay.empty:
        return []
    out = []
    for kv, g in nay.groupby(_khu_vuc(nay)):
        if kv == "NGOAI_TINH" or len(g) < MAU_TOI_THIEU:
            continue
        g0 = ck[_khu_vuc(ck) == kv]
        a, b = _pct(g.onl_nhanh.sum(), len(g)), _pct(g0.onl_nhanh.sum(), len(g0)) if len(g0) >= MAU_TOI_THIEU else None
        out.append((kv, a, b, round(float(g.so_ngay_cho.mean()), 1), len(g)))
    if not out:
        return []
    cham = min(out, key=lambda x: x[1])
    dong = ("- Tốc độ triển khai (online trong 1 ngày kể từ tạo hợp đồng) theo khu vực kỹ thuật: "
            + "; ".join(f"{KHU_VUC[k]} {a}%" + (f" (cùng kỳ {b}%, {a - b:+d} điểm)" if b is not None else "")
                        + f", chờ bình quân {str(n).replace('.', ',')} ngày" for k, a, b, n, _ in out) + ".")
    xau = [x for x in out if x[2] is not None and x[1] - x[2] <= -5]
    if xau:
        dong += (" Chậm đi rõ nhất: " + ", ".join(f"{KHU_VUC[k]} ({a - b:+d} điểm trên {_so(sl)} hợp đồng)"
                                                  for k, a, b, _, sl in sorted(xau, key=lambda x: x[1] - x[2]))
                 + " → việc của kỹ thuật khu vực đó.")
    elif cham[1] is not None:
        dong += f" Chậm nhất hiện là {KHU_VUC[cham[0]]}."
    return [dong]


def phong_lam_tut(nay: pd.DataFrame, ck: pd.DataFrame, thang: str) -> list[str]:
    """Phòng có tỷ lệ tụt từ 10 điểm so cùng kỳ (đủ mẫu), xếp theo mức ảnh hưởng = điểm tụt × số hợp đồng."""
    ten = {p["code"]: p["ten"] for p in phong_order(thang)}
    dong = []
    for k, nhan in TY_LE.items():
        co = {"kem_vvip": "co_vvip", "kem_camera": "co_camera", "tra_truoc": "co_tra_truoc",
              "onl_1_ngay": "onl_nhanh"}[k]
        a = nay.groupby("phong_code")[co].agg(["mean", "size"])
        b = ck.groupby("phong_code")[co].agg(["mean", "size"])
        x = a.join(b, rsuffix="_ck", how="inner")
        x = x[(x["size"] >= MAU_TOI_THIEU) & (x["size_ck"] >= MAU_TOI_THIEU)]
        x["doi"] = ((x["mean"] - x["mean_ck"]) * 100).round()
        x = x[x.doi <= -DOI_DANG_KE]
        if len(x):
            x = x.assign(anh_huong=-x.doi * x["size"]).sort_values("anh_huong", ascending=False).head(2)
            dong.append(f"- Tỷ lệ {nhan} tụt mạnh ở: " + ", ".join(
                f"{ten.get(c, c)} {round(r['mean'] * 100)}% ({int(r.doi):+d} điểm)" for c, r in x.iterrows()) + ".")
    return dong


def co_cau_goi(nay: pd.DataFrame, ck: pd.DataFrame) -> list[str]:
    if nay.empty or ck.empty:
        return []
    a, b = nay.nhom_goi.value_counts(normalize=True) * 100, ck.nhom_goi.value_counts(normalize=True) * 100
    doi = (a.sub(b, fill_value=0)).round()
    doi = doi[doi.abs() >= 5].sort_values()
    if doi.empty:
        return []
    kem = pt.kem_theo_goi(nay).set_index("nhom_goi")
    return ["- Cơ cấu gói đổi so cùng kỳ: " + ", ".join(
        f"{g} {round(a.get(g, 0))}% số hợp đồng ({int(v):+d} điểm"
        + (f"; nhóm này kèm V.VIP {int(kem.at[g, 'vvip'])}%" if g in kem.index and pd.notna(kem.at[g, "vvip"]) else "")
        + ")" for g, v in doi.items()) + "."]


def nhan_su_yeu(user, d: date, scope, gioi_han: int = 5) -> list[str]:
    """Sale có số đặc biệt thấp so với mặt bằng phòng mình (không tính người mới 1-2 tháng, trưởng phòng, người đã
    nghỉ) và sale bán nhiều nhưng gần như không bán kèm - kèm số phòng mất so với mặt bằng."""
    if not user.duoc_xem_nhan_su:
        return []
    from app import canh_bao
    pns = user.phong_nhan_su()
    pham_vi = scope if pns is None else [c for c in (scope or pns) if c in pns]
    thang = f"{d.year}-{d.month:02d}"
    df = _hieu_suat(thang, pham_vi, d.day)
    if df.empty:
        return []
    df = df[df.dang_lam & df.kd & ~df.acc_norm.isin(canh_bao.acc_khong_xet(df.acc_norm))].copy()
    df = df[~df.tham_nien_bucket.astype(str).isin(["1", "2"])]          # người mới 1-2 tháng: chưa so
    if df.empty:
        return []
    tv = df.groupby("phong_code").online.transform("median")
    df["tv_phong"] = tv
    df["thieu"] = (tv - df.online).clip(lower=0)
    yeu = df[(tv >= 6) & (df.online <= tv * 0.5)].sort_values("thieu", ascending=False)
    dong = []
    if len(yeu):
        dong.append("- Sale có số đặc biệt thấp so với mặt bằng phòng (dưới một nửa trung vị phòng, không tính người "
                    "mới 1-2 tháng): " + "; ".join(
                        f"{r.ho_ten} ({r.phong}, {r.tham_nien or 'chưa rõ thâm niên'}) {int(r.online)} online, trung "
                        f"vị phòng {int(r.tv_phong)}" for r in yeu.head(gioi_han).itertuples()) + ".")
        theo_phong = yeu.groupby("phong").agg(so=("acc", "size"), thieu=("thieu", "sum"))
        theo_phong = theo_phong[theo_phong.so >= 2].sort_values("thieu", ascending=False)
        if len(theo_phong):
            dong.append("- Phòng bị nhóm sale yếu làm chững lại: " + ", ".join(
                f"{p} có {int(r.so)} người như vậy, nếu họ đạt mặt bằng phòng thì phòng thêm khoảng {_so(r.thieu)} "
                "online" for p, r in theo_phong.head(3).iterrows()) + ".")
    tl = df.groupby("phong_code").apply(lambda g: g.vvip.sum() / g.online.sum() * 100 if g.online.sum() else None)
    df["tl_phong"] = df.phong_code.map(tl)
    it_kem = df[(df.online >= 10) & (df.ty_le_vvip <= df.tl_phong - 25)].sort_values("online", ascending=False)
    if len(it_kem):
        dong.append("- Sale bán nhiều nhưng ít bán kèm V.VIP (thấp hơn phòng từ 25 điểm): " + ", ".join(
            f"{r.ho_ten} ({r.phong}) {int(r.online)} online, kèm V.VIP {int(r.ty_le_vvip)}% so với phòng "
            f"{round(r.tl_phong)}%" for r in it_kem.head(3).itertuples()) + ".")
    return dong


def tin_hieu_phan_tich(user, d: date, scope) -> str:
    thang = f"{d.year}-{d.month:02d}"
    nay, ck, ten_ck = _hai_ky(d, scope)
    a, b = _ty_le(nay), _ty_le(ck)
    chung = ("- Tỷ lệ chung so " + ten_ck + ": " + "; ".join(
        f"{nhan} {round(a[k])}%" + (f" ({round(a[k] - b[k]):+d} điểm)" if b.get(k) is not None else "")
        for k, nhan in TY_LE.items() if a.get(k) is not None) + ".")
    dong = [chung, *trien_khai(nay, ck), *phong_lam_tut(nay, ck, thang), *co_cau_goi(nay, ck),
            *nhan_su_yeu(user, d, scope)]
    return "TÍN HIỆU CHẤT LƯỢNG & VẬN HÀNH (app đã tính sẵn - ưu tiên dùng):\n" + "\n".join(dong)


def boi_canh_chung(user, d: date, scope, nhan_su: bool = True) -> str:
    """Bức tranh tháng ngắn gọn, dùng chung cho mọi trang và chat (lưu tạm theo phiên số liệu). Chat bỏ phần
    nhân sự (nhanh hơn; hỏi nhân sự thì chat tự gọi công cụ)."""
    nhan_su = nhan_su and user.duoc_xem_nhan_su
    khoa = (_phien_so_lieu(), d, tuple(scope) if scope is not None else None, nhan_su,
            tuple(user.phong_nhan_su() or ()) if user.phong_nhan_su() is not None else None)
    if khoa in _cache:
        return _cache[khoa]
    from app.tro_ly_du_lieu import so_voi_thang_truoc
    thang = f"{d.year}-{d.month:02d}"
    meta = {p["code"]: p for p in phong_order(thang)}
    db = du_bao_thang(thang, d.day, scope).set_index("phong_code")
    t = db.loc["TOTAL"]
    dong = []
    if t.mt:
        dong.append(f"- Tiến độ: dự báo cuối tháng {int(t.pct_mt)}% mục tiêu ({t.danh_gia}); cần "
                    f"{_so(t.can_moi_ngay or 0)} online/ngày, đang làm {_so(t.tb_ngay)}/ngày.")
    ss = so_voi_thang_truoc(thang, d.day, scope)
    if ss:
        dong.append(ss)
    kd = db[[c != "TOTAL" and meta.get(c, {}).get("loai") in ("IBB", "DIABAN") and (db.at[c, "mt"] or 0) > 0
             for c in db.index]]
    if len(kd):
        dong.append("- Phòng kinh doanh rủi ro nhất (dự báo % mục tiêu): " + ", ".join(
            f"{meta[c]['ten']} {int(r.pct_mt)}%" for c, r in kd.sort_values("pct_mt").head(3).iterrows()) + ".")
    nay, ck, ten_ck = _hai_ky(d, scope)
    a, b = _ty_le(nay), _ty_le(ck)
    dong.append("- Chất lượng bán so " + ten_ck + ": " + "; ".join(
        f"{nhan} {round(a[k])}%" + (f" ({round(a[k] - b[k]):+d} điểm)" if b.get(k) is not None else "")
        for k, nhan in TY_LE.items() if a.get(k) is not None) + ".")
    dong += trien_khai(nay, ck)
    if nhan_su:
        from app.hr_metrics import canh_bao_nhan_su
        pns = user.phong_nhan_su()
        pham_vi = scope if pns is None else [c for c in (scope or pns) if c in pns]
        cb = canh_bao_nhan_su(thang, chi_phong=pham_vi, ngay=d.day, df=_hieu_suat(thang, pham_vi, d.day))
        if len(cb):
            from app.canh_bao import TRAO_DOI_NGAY
            ngay_ = cb[cb.muc_rui_ro == TRAO_DOI_NGAY]
            dong.append(f"- Nhân sự: {len(ngay_)} người cần trao đổi ngay (từ 7 ngày không có số), "
                        f"{len(cb) - len(ngay_)} người cần theo dõi; nhiều nhất ở " + ", ".join(
                            f"{p} {n}" for p, n in cb.phong.value_counts().head(3).items()) + ".")
    kq = "BỐI CẢNH THÁNG (chung cho mọi trang - dùng để hiểu bức tranh, trang nào nhận xét theo lăng kính trang đó):\n" \
         + "\n".join(dong)
    if len(_cache) > 64:
        _cache.clear()
    _cache[khoa] = kq
    return kq
