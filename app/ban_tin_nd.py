"""Tin chữ "NHẬN ĐỊNH & HÀNH ĐỘNG" của Bản tin 8h cho Ban Giám đốc (CEO chốt 29/10/2026), đi sau ảnh Báo cáo Tổng.

Ảnh đã có bảng số; tin này chỉ nói điều ảnh chưa nói thẳng: mục tiêu cần đạt mỗi ngày, phòng cần bù số, chất lượng bán so
với mặt bằng chung, hợp đồng tồn lâu, rồi hành động đề xuất. Mọi câu do LUẬT cố định sinh ra từ số đã có (không gọi AI),
không có tên khách hàng và không nêu tên nhân sự. Một tin duy nhất, tối đa `bt.TOI_DA_KY_TU` ký tự: dài thì bớt dần
số dòng liệt kê (`_MUC_BOT`) rồi mới cắt.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import pandas as pd

from app import ban_tin as bt
from app import du_bao, metrics
from app import phan_tich as pt

# ---- ngưỡng (đặt ở đây để CEO đổi một chỗ)
HAN_XU_LY_NGAY = 2           # việc "xử lý nhanh" có hạn = ngày số + 2 ngày (không quá cuối tháng)
TON_QUA_NGAY = 7             # HĐ chờ online từ bấy nhiêu ngày là tồn lâu (cùng ngưỡng cột "Chờ online từ 7 ngày")
CHENH_CHAT_LUONG = 10        # V.VIP / Camera của phòng thấp hơn mức chi nhánh từ bấy nhiêu điểm % mới nêu
TOI_THIEU_ONLINE_PHONG = 30  # phòng có ít online hơn thì tỷ lệ chưa đủ tin cậy, không đem so
TOI_DA_PHONG_CHAT_LUONG = 3  # mỗi chỉ số nêu tối đa bấy nhiêu phòng thấp nhất
TOI_DA_PHONG_TON = 3         # mục tồn nêu bấy nhiêu phòng tồn nhiều nhất
TOI_DA_PHONG_HOP = 3         # hành động "họp nhanh" gọi tối đa bấy nhiêu phòng hụt nhiều nhất
_MUC_BOT = (5, 3, 2)         # số phòng tối đa liệt kê ở mục "Phòng cần bù số", thử lần lượt tới khi vừa độ dài


# ------------------------------------------------------------------ dùng chung với tin trưởng phòng
def cuoi_thang(ngay_iso: str) -> date:
    d = date.fromisoformat(ngay_iso)
    return d.replace(day=metrics.month_range(ngay_iso[:7])[2])


def han_xu_ly(ngay_iso: str) -> date:
    """Hạn cho việc xử lý nhanh: ngày số + `HAN_XU_LY_NGAY`, không vượt cuối tháng."""
    return min(date.fromisoformat(ngay_iso) + timedelta(days=HAN_XU_LY_NGAY), cuoi_thang(ngay_iso))


def ngay_vn(d: date) -> str:
    return f"{d:%d/%m}"


def muc(tieu_de: str, dong: list[bt._Soan], nhan_nho: str = "") -> list[bt._Soan]:
    """Mục có tiêu đề: tiêu đề đi cùng dòng đầu (không bị bỏ lẻ cuối một tin con). Không có dòng thì trả rỗng."""
    if not dong:
        return []
    dau = bt._Soan().them(tieu_de, "b", bt.CO_TIEU_DE)
    if nhan_nho:
        dau.them(f" {nhan_nho}", bt.CO_NHO)
    dau.them("\n")
    dau.phan.extend(dong[0].phan)
    return [dau] + dong[1:]


def dong_gach(*phan) -> bt._Soan:
    """Dòng gạch đầu: mỗi phần là chữ trơn hoặc (chữ, kiểu...)."""
    s = bt._Soan().them("• ")
    for p in phan:
        if isinstance(p, str):
            s.them(p)
        else:
            s.them(p[0], *p[1:])
    return s


def ghep(dau: bt._Soan, cac_muc: list[list[bt._Soan]]) -> bt.TinZalo:
    """Đầu tin, rồi mỗi mục cách nhau một dòng trống; các dòng trong một mục liền nhau."""
    s = bt._Soan()
    s.phan.extend(dau.phan)
    for m in cac_muc:
        if not m:
            continue
        s.them("\n\n")
        for i, d in enumerate(m):
            if i:
                s.them("\n")
            s.phan.extend(d.phan)
    return s.xong()


def can_moi_ngay(muc_tieu: int, luy_ke: int, con_lai: int) -> int | None:
    """Số online mỗi ngày cần đạt trong `con_lai` ngày để chạm mục tiêu tháng; None nếu hết tháng."""
    return math.ceil((muc_tieu - luy_ke) / con_lai) if con_lai > 0 else None


# ------------------------------------------------------------------ số liệu
def _phong_can_chu_y(sl: dict) -> pd.DataFrame:
    """Phòng bán hàng ở mức Rủi ro HOẶC online thấp hơn cùng kỳ tháng trước, kèm hụt dự báo so mục tiêu, xếp hụt nhiều trước."""
    ds = sl["phong"][sl["phong"]["phong_code"].isin(_ma_ban_hang(sl))].copy()
    ds.attrs = {}
    if ds.empty:
        return ds.assign(online=0, ck_online=0, hut=0)
    tq = sl["tq"].set_index("phong_code")
    ds["online"] = ds["phong_code"].map(tq["online"]).fillna(0).astype(int)
    ds["ck_online"] = ds["phong_code"].map(tq["ck_online"]).fillna(0).astype(int)
    ds["hut"] = (ds["mt"] - ds["du_bao"]).clip(lower=0).astype(int)
    can = ds[(ds["danh_gia"] == du_bao.RUI_RO) | (ds["online"] < ds["ck_online"])]
    return can.sort_values(["hut", "mt"], ascending=False, kind="stable")


def _ma_ban_hang(sl: dict) -> set[str]:
    nhom = bt._phong_ban_hang(sl)
    return {c for g in nhom.values() for c in g["phong_code"]}


def _ton_lau_theo_phong(sl: dict) -> tuple[int, pd.Series]:
    """(tổng HĐ tồn từ 7 ngày, số đó theo từng phòng bán hàng xếp nhiều trước). Tổng khớp cột TOTAL của Báo cáo phòng."""
    ton = pt.hop_dong_ton()
    lau = ton[ton["so_ngay_cho"] >= TON_QUA_NGAY]
    theo = lau[lau["phong_code"].isin(_ma_ban_hang(sl))].groupby("phong_code").size().sort_values(ascending=False, kind="stable")
    return len(lau), theo


def _ty_le_camera(online, camera):
    return round(float(camera) / float(online) * 100) if online else None


def _phong_thap_chat_luong(sl: dict) -> dict[str, list[tuple[str, float, float]]]:
    """{'V.VIP' | 'Camera': [(phòng, tỷ lệ phòng, tỷ lệ chi nhánh)]} cho phòng bán hàng thấp hơn chi nhánh từ `CHENH_CHAT_LUONG` điểm."""
    tq, tong = sl["tq"], sl["tong"]
    chung = {"V.VIP": tong["vvip_ty_le"], "Camera": _ty_le_camera(tong["online"], tong["camera"])}
    ra: dict[str, list] = {"V.VIP": [], "Camera": []}
    ma_ban_hang = _ma_ban_hang(sl)
    for _, r in tq[tq["phong_code"].isin(ma_ban_hang)].iterrows():
        if int(r["online"] or 0) < TOI_THIEU_ONLINE_PHONG:
            continue
        gia_tri = {"V.VIP": r["vvip_ty_le"], "Camera": _ty_le_camera(r["online"], r["camera"])}
        for ten, v in gia_tri.items():
            if v is not None and chung[ten] is not None and float(chung[ten]) - float(v) >= CHENH_CHAT_LUONG:
                ra[ten].append((str(r["phong"]), float(v), float(chung[ten])))
    return {k: sorted(v, key=lambda x: x[1] - x[2])[:TOI_DA_PHONG_CHAT_LUONG] for k, v in ra.items()}


# ------------------------------------------------------------------ các mục (tin BGĐ, gọn)
def _dong_muc_tieu(ten: str, online: int, mt: int, con: int, ngay: int, so_ngay_thang: int) -> bt._Soan | None:
    if not mt:
        return None
    if online >= mt:
        return dong_gach((ten, "b"), ": ", (f"đã đạt mục tiêu ({bt._so(online)}/{bt._so(mt)})", "b", bt.XANH))
    cung = can_moi_ngay(mt, online, con)
    if cung is None:
        return dong_gach((ten, "b"), f": hết tháng, đạt {bt._pct(online, mt)}% mục tiêu")
    hut = mt - du_bao._tron(online / ngay * so_ngay_thang)
    s = dong_gach((ten, "b"), ": cần ", (f"{bt._so(cung)}/ngày", "b", bt.DO), f" (hiện {bt._so(online / ngay, 1)})")
    return s.them(f" · hụt {bt._so(hut)}" if hut > 0 else " · dự báo vẫn đạt")


def _muc_tieu(sl: dict) -> list[bt._Soan]:
    t, tq, ngay, thang = sl["tong"], sl["tq"], sl["ngay"], sl["thang"]
    so_ngay_thang = metrics.month_range(thang)[2]
    con = so_ngay_thang - ngay
    dong = [_dong_muc_tieu("Chi nhánh", int(t["online"]), int(t["mt_internet"] or 0), con, ngay, so_ngay_thang)]
    for ma, nhan in (("DNG", "Đà Nẵng"), ("QNM", "Quảng Nam")):
        r = tq[tq["phong_code"] == f"CN_{ma}"]
        if len(r):
            dong.append(_dong_muc_tieu(nhan, int(r.iloc[0]["online"]), int(r.iloc[0]["mt_internet"] or 0),
                                       con, ngay, so_ngay_thang))
    return muc("1) MỤC TIÊU CẦN ĐẠT", [d for d in dong if d is not None], "(online/ngày)")


def _muc_phong(can: pd.DataFrame, toi_da: int, tt: str) -> list[bt._Soan]:
    dong = []
    for _, r in can.head(toi_da).iterrows():
        s = dong_gach((str(r["phong"]), "b"), f": {bt._so(r['can_moi_ngay'])}/ngày (hiện {bt._so(r['tb_ngay'], 1)})")
        if r["hut"] > 0:
            s.them(f" · hụt {bt._so(r['hut'])}")
        if r["online"] < r["ck_online"]:
            s.them(" · ").them(f"-{round((r['ck_online'] - r['online']) / r['ck_online'] * 100)}% so T{tt}", "b", bt.DO)
        dong.append(s)
    if len(can) > toi_da:
        dong.append(bt._Soan().them(f"… và {len(can) - toi_da} phòng khác (xem ảnh)."))
    return muc("2) PHÒNG CẦN BÙ SỐ", dong, "(Rủi ro hoặc giảm so cùng kỳ)")


def _muc_chat_luong(sl: dict, thap: dict) -> list[bt._Soan]:
    t = sl["tong"]
    cam = _ty_le_camera(t["online"], t["camera"])
    dong = []
    if t["vvip_ty_le"] is not None and cam is not None:
        dong.append(dong_gach("Chi nhánh: V.VIP ", (f"{bt._so(t['vvip_ty_le'])}%", "b"), " · Camera ", (f"{cam}%", "b")))
    for ten, ds in thap.items():
        if ds:
            dong.append(dong_gach(f"{ten} thấp: " + ", ".join(f"{p} {bt._so(v)}%" for p, v, _ in ds)))
    if dong and not any(thap.values()):
        dong.append(dong_gach(f"Không phòng nào thấp hơn chi nhánh quá {CHENH_CHAT_LUONG} điểm."))
    return muc("3) CHẤT LƯỢNG BÁN", dong, "(luỹ kế tháng)")


def _muc_ton(tong: int, theo: pd.Series, ten: dict) -> list[bt._Soan]:
    if tong <= 0:
        return []
    cu_the = ", ".join(f"{ten.get(p, p)} {n}" for p, n in theo.head(TOI_DA_PHONG_TON).items())
    s = dong_gach((f"{bt._so(tong)} HĐ", "b", bt.DO), f" chờ online từ {TON_QUA_NGAY} ngày")
    s.them(f". Nhiều nhất: {cu_the}" if cu_the else "")
    return muc("4) HỢP ĐỒNG TỒN", [s])


# ------------------------------------------------------------------ hành động đề xuất (luật cố định)
def _hanh_dong(ngay_iso: str, sl: dict, can: pd.DataFrame, thap: dict, ton_theo: pd.Series, ten: dict) -> list[bt._Soan]:
    han = ngay_vn(han_xu_ly(ngay_iso))
    con = metrics.month_range(sl["thang"])[2] - sl["ngay"]
    dong: list[bt._Soan] = []
    hop = can[can["hut"] > 0].head(TOI_DA_PHONG_HOP)
    if len(hop) and con > 0:
        dong.append(dong_gach("Họp nhanh với ", (", ".join(str(x) for x in hop["phong"]), "b"),
                              f": chốt kế hoạch bù {bt._so(hop['hut'].sum())} online."))
    con_lai = can[can["hut"] > 0].iloc[len(hop):]
    if len(con_lai) and con > 0:
        dong.append(dong_gach(f"{len(con_lai)} phòng còn lại ở mục 2 gửi kế hoạch bù số."))
    nang = [f"{ds[0][0]} nâng {chi_so} lên ≥{bt._so(ds[0][2])}%" for chi_so, ds in thap.items() if ds]
    if nang:
        dong.append(dong_gach("; ".join(nang) + "."))
    top = ton_theo.head(TOI_DA_PHONG_TON)
    if int(top.sum()) > 0:
        dong.append(dong_gach((", ".join(ten.get(p, p) for p in top.index), "b"),
                              f" xử lý dứt điểm {bt._so(top.sum())} HĐ tồn."))
    if not dong:
        dong.append(dong_gach(("Chưa có phòng nào cần can thiệp:", "b", bt.XANH), " giữ nhịp và rà HĐ tồn mỗi ngày."))
    return muc("5) HÀNH ĐỘNG ĐỀ XUẤT", dong, f"(trước {han})")


# ------------------------------------------------------------------ dựng tin
def dung_nhan_dinh_bgd(ngay_iso: str) -> bt.TinZalo:
    """Tin "NHẬN ĐỊNH & HÀNH ĐỘNG" cho Ban Giám đốc, GỌN (CEO 29/10/2026). Một tin ≤ `bt.TOI_DA_KY_TU` ký tự: dài thì bớt dòng ở mục 2, rồi cắt."""
    sl = bt._so_lieu_bgd(ngay_iso)
    ngay = date.fromisoformat(ngay_iso)
    con = metrics.month_range(sl["thang"])[2] - sl["ngay"]
    tt = sl["thang_truoc"][5:7].lstrip("0")
    ten = {r["phong_code"]: str(r["phong"]) for _, r in sl["phong"].iterrows()}
    can = _phong_can_chu_y(sl)
    thap = _phong_thap_chat_luong(sl)
    ton_tong, ton_theo = _ton_lau_theo_phong(sl)
    dau = (bt._Soan().them(f"NHẬN ĐỊNH & HÀNH ĐỘNG · {ngay:%d/%m}", "b", bt.CO_DAU)
           .them(f"\nLuỹ kế tháng {ngay.month} · còn {con} ngày", bt.CO_NHO))
    chat_luong = _muc_chat_luong(sl, thap)
    for toi_da in _MUC_BOT:
        chu = ghep(dau, [_muc_tieu(sl), _muc_phong(can, toi_da, tt), chat_luong, _muc_ton(ton_tong, ton_theo, ten),
                         _hanh_dong(ngay_iso, sl, can, thap, ton_theo, ten)])
        if len(chu) <= bt.TOI_DA_KY_TU:
            return chu
    return bt._cat(chu, bt.TOI_DA_KY_TU)
