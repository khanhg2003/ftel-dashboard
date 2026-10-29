"""Bản tin 8h cho TRƯỞNG PHÒNG (CEO chốt 29/10/2026): mỗi người nhận loại `truong_phong` nhận số của đúng (các) phòng
admin đã chọn tay ở Quản trị, không tự liên kết với tài khoản app.

Số lấy từ đúng hàm của Báo cáo phòng / Báo cáo Tổng (không viết lại công thức). Mỗi phòng có tin 1 "Tổng quan"
và tin 2 "Từng nhân sự" (tách nhiều tin con khi dài). Mã loại tin trong nhật ký chống trùng: `tp:<phòng>:<phần>`
(`tq`, `ns1`, `ns2`...) cộng dòng `tp:<phòng>:ht` ghi khi đã gửi đủ mọi phần: cột `loai` chỉ dài 20 ký tự nên mã phòng
tối đa `TOI_DA_MA_PHONG`. Trưởng phòng và người đã nghỉ không vào bảng nhân sự, nhưng số của họ vẫn nằm trong số phòng.
"""
from __future__ import annotations

import math
import os
import time
from datetime import date

import pandas as pd
from sqlalchemy import delete, select

from app import ban_tin as bt
from app import bao_cao_phong as bcp
from app import canh_bao, du_bao, metrics, org, overview, zalo_bot
from app.config import rules_config
from app.auth import ghi_log
from app.db import session_scope
from app.models import BanTinNguoiNhanPhong, BanTinNhatKy

TOI_DA_MA_PHONG = 12             # "tp:" + mã + ":ns99" phải vừa cột loai (20 ký tự)
PHAN_TONG_QUAN, PHAN_TRAO_DOI, PHAN_XONG = "tq", "td", "ht"
GIAM_CUNG_KY = "Giảm so cùng kỳ"      # nhãn cho người chỉ có vấn đề là thấp hơn cùng kỳ tháng trước
LY_DO_TOI_DA = 70
TIN_TOI_DA_NGUOI = 6             # số tên liệt kê tối đa ở mục chất lượng bán


# ------------------------------------------------------------------ phòng gắn với người nhận
def phong_chon_duoc() -> list[dict]:
    """Chỉ phòng bán hàng (IBB và địa bàn), và mã đủ ngắn để vừa mã loại tin."""
    ds = [p for p in org.phong_all() if p["loai"] in bt.LOAI_PHONG_KD and len(p["code"]) <= TOI_DA_MA_PHONG]
    return sorted(ds, key=lambda p: (str(p.get("chi_nhanh")), p.get("thu_tu") or 0))


def chu_phong(codes: list[str]) -> str:
    ten = {p["code"]: p["ten"] for p in org.phong_all()}
    return ", ".join(c if ten.get(c, c) == c else f"{c} ({ten[c]})" for c in codes)


def chuan_phong(phong) -> list[str]:
    ra: list[str] = []
    for p in phong or []:
        p = str(p or "").strip()
        if p and p not in ra:
            ra.append(p)
    return ra


def kiem_phong(phong: list[str]) -> str:
    """Câu báo lỗi, rỗng nếu hợp lệ."""
    if not phong:
        return "Trưởng phòng cần chọn ít nhất một phòng."
    hop_le = {p["code"] for p in phong_chon_duoc()}
    if any(p not in hop_le for p in phong):
        return "Chỉ chọn được phòng bán hàng (IBB và địa bàn)."
    return ""


def phong_theo_nguoi() -> dict[int, list[str]]:
    kq: dict[int, list[str]] = {}
    with session_scope() as s:
        for r in s.execute(select(BanTinNguoiNhanPhong).order_by(BanTinNguoiNhanPhong.id)).scalars():
            kq.setdefault(r.nguoi_nhan_id, []).append(r.ma_phong)
    return kq


def ghi_phong(s, nguoi_id: int, phong: list[str]) -> None:
    """Đặt đúng tập phòng của người nhận (rỗng = xoá hết). Chạy trong phiên của `luu_nguoi_nhan`."""
    cu = set(s.execute(select(BanTinNguoiNhanPhong.ma_phong).where(
        BanTinNguoiNhanPhong.nguoi_nhan_id == nguoi_id)).scalars())
    bo = cu - set(phong)
    if bo:
        s.execute(delete(BanTinNguoiNhanPhong).where(BanTinNguoiNhanPhong.nguoi_nhan_id == nguoi_id,
                                                     BanTinNguoiNhanPhong.ma_phong.in_(bo)))
    for p in phong:
        if p not in cu:
            s.add(BanTinNguoiNhanPhong(nguoi_nhan_id=nguoi_id, ma_phong=p))


def ma_loai(ma_phong: str, phan: str) -> str:
    return f"tp:{ma_phong}:{phan}"


def nhan_loai_tin(loai: str) -> str:
    if loai.startswith("tp:"):
        _, ma, phan = (loai.split(":") + ["", ""])[:3]
        mo_ta = ("tổng quan" if phan == PHAN_TONG_QUAN else f"cần trao đổi {phan[2:]}" if phan.startswith(PHAN_TRAO_DOI)
                 else f"nhân sự {phan[2:]}")
        return f"TP {ma} · {mo_ta}"
    return "Bản tin" if loai == "bgd" else "Nhắc nạp file"


# ------------------------------------------------------------------ số liệu
def nap_chung(ngay_iso: str) -> dict:
    """Phần dùng chung mọi phòng, đọc một lần mỗi lượt."""
    thang, ngay = ngay_iso[:7], int(ngay_iso[8:10])
    tq, _ = overview.bang_tong_quan(thang, ngay, chi_nhanh="all")
    return {"ngay_iso": ngay_iso, "thang": thang, "ngay": ngay, "tq": tq,
            "db": du_bao.du_bao_thang(thang, ngay), "thang_truoc": metrics.prev_month(thang)}


def _dong(df: pd.DataFrame, code: str, ten: str) -> pd.Series:
    d = df[df["phong_code"] == code]
    if d.empty:
        raise ValueError(f"Phòng {code} không có trong {ten}.")
    return d.iloc[0]


def _hang(chung: dict, code: str) -> tuple[int, int] | None:
    nhom = bcp.phong_cung_nhom(code, chung["thang"])
    d = chung["tq"]
    d = d[(d["loai_dong"] == "data") & d["phong_code"].isin(nhom)]
    mine = d[d["phong_code"] == code]
    if mine.empty:
        return None
    return int((d["online"] > mine.iloc[0]["online"]).sum() + 1), len(d)      # cùng cách xếp "Số online tháng" ở Báo cáo phòng


def _nhan_su(chung: dict, code: str):
    """(tất cả dòng, dòng được xét, dòng TỔNG PHÒNG). Được xét = không phải trưởng phòng / đã nghỉ / acc tạm."""
    bn = bcp.bang_nhan_su(chung["thang"], chung["ngay"], code)
    data = bn[bn["loai_dong"] == "data"].copy()
    xet = data[data["khong_xet"].map(lambda v: not v)].copy()
    for c in ("online", "online_ngay", "ck_online", "vvip", "camera"):
        xet[c] = pd.to_numeric(xet[c]).fillna(0).astype(int)
    return data, xet, bn[bn["loai_dong"] == "total"].iloc[0]


def _ngan(chu: str, n: int = LY_DO_TOI_DA) -> str:
    return chu if len(chu) <= n else chu[:n - 1].rstrip() + "…"


def _so_voi_chung(s: bt._Soan, phong, chung_cn) -> None:
    """Số phòng so với cả chi nhánh: cao hơn xanh, thấp hơn đỏ."""
    if phong is None:
        s.them("–")
        return
    mau = [] if chung_cn is None else [bt.XANH if phong >= chung_cn else bt.DO]
    s.them(f"{bt._so(phong)}%", "b", *mau)
    s.them(f" (cả chi nhánh {bt._so(chung_cn)}%)" if chung_cn is not None else "")


def _ty_le(tu, mau):
    return round(float(tu) / float(mau) * 100) if mau else None


def _ten_chua_ban_kem(xet: pd.DataFrame, cot: str) -> list[str]:
    """Bán nhiều (online từ 3) mà chưa bán kèm: đúng quy tắc `_chu_y` của Báo cáo phòng."""
    return [str(r["ho_ten"]) for _, r in xet[(xet["online"] >= 3) & (xet[cot] == 0)].iterrows()]


def _liet_ke(ten: list[str]) -> str:
    return ", ".join(ten[:TIN_TOI_DA_NGUOI]) + (f" và {len(ten) - TIN_TOI_DA_NGUOI} người khác"
                                                 if len(ten) > TIN_TOI_DA_NGUOI else "")


# ------------------------------------------------------------------ tin 1: tổng quan phòng
def _khoi_tien_do(c: dict, q: pd.Series, d: pd.Series, hang) -> bt._Soan:
    online, mt, ck = int(q["online"]), int(q["mt_internet"] or 0), int(q["ck_online"] or 0)
    tt = c["thang_truoc"][5:7].lstrip("0")
    s = bt._Soan().them("1) TIẾN ĐỘ", "b", bt.CO_TIEU_DE)
    s.them(f"\nOnline luỹ kế: {bt._so(online)}"
           + (f" / {bt._so(mt)} mục tiêu tháng ({bt._pct(online, mt)}%)" if mt else " (chưa có mục tiêu tháng)"))
    if hang:
        s.them(f" · hạng {hang[0]}/{hang[1]} phòng bán hàng", "b")
    mt_ngay = int(q["mt_ngay"] or 0)
    if mt_ngay > 0:
        on = int(q["ngay_online"] or 0)
        s.them(f"\nOnline ngày {c['ngay']:02d}/{c['thang'][5:7]}: ").them(
            f"{bt._so(on)}", "b", bt.XANH if on >= mt_ngay else bt.DO).them(f" / mục tiêu ngày {bt._so(mt_ngay)}")
    if ck:
        v = round((online - ck) / ck * 100)
        s.them(f"\nCùng kỳ tháng {tt}: {bt._so(ck)} online, ")
        s.them(f"tăng {v}%" if v > 0 else f"giảm {-v}%" if v < 0 else "bằng nhau", *(["b", bt.XANH] if v > 0 else
                                                                                        ["b", bt.DO] if v < 0 else []))
    s.them(f"\nDự báo cuối tháng: {bt._so(d['du_bao'])} ({bt._so(d['du_bao_nhip'])})")
    if mt:
        mau = bt.MAU_DANH_GIA.get(d["danh_gia"])
        s.them(" · ").them(str(d["danh_gia"]), "b", *([mau] if mau else []))
        thieu = mt - round(float(d["du_bao"]))
        s.them("\nDự báo ")
        if thieu > 0:
            s.them(f"hụt {bt._so(thieu)}", "b", bt.DO).them(f" so với mục tiêu {bt._so(mt)}")
        else:
            s.them("đạt mục tiêu", "b", bt.XANH).them(f" {bt._so(mt)}")
    return s.them("\nSố trong ngoặc tính thêm nhịp dồn cuối tháng.", bt.CO_NHO)


def can_trao_doi(xet: pd.DataFrame, code: str) -> pd.DataFrame:
    """Nhân sự cần trao đổi: có mức cảnh báo chung (`canh_bao`) HOẶC online luỹ kế thấp hơn cùng kỳ tháng trước.
    KHÔNG giới hạn số người (CEO chốt 29/10/2026). `rules.yml` -> `ban_tin.khong_trao_doi.<phòng>` loại riêng vài người
    của một phòng khỏi danh sách này (họ vẫn có trong bảng từng nhân sự)."""
    bo = set((((rules_config().get("ban_tin") or {}).get("khong_trao_doi")) or {}).get(code) or [])
    x = xet[~xet["acc_norm"].isin(bo)].copy()
    if x.empty:
        return x.assign(chenh=0, muc="", _t=0)
    x["chenh"] = x["online"] - x["ck_online"]
    muc = x["muc_chu_y"].map(lambda m: m if m in canh_bao.THU_TU_MUC and m != "" else "")
    x["muc"] = muc.where(muc != "", x["chenh"].map(lambda c: GIAM_CUNG_KY if c < 0 else ""))
    x = x[x["muc"] != ""].copy()
    x["_t"] = x["muc"].map(lambda m: canh_bao.THU_TU_MUC.get(m, 99))
    return x.sort_values(["_t", "chenh"], kind="stable")


def _dong_trao_doi(r, tt: str) -> bt._Soan:
    chenh, ck = int(r["chenh"]), int(r["ck_online"])
    giam = ""
    if chenh < 0:
        giam = f"giảm {-chenh} so T{tt}" + (f" (-{round(-chenh / ck * 100)}%)" if ck else "")
    s = bt._Soan().them("• ").them(str(r["ho_ten"]), "b").them(" · ").them(r["muc"], "b", bt.DO)
    if r["muc"] == GIAM_CUNG_KY:
        return s.them(f": {bt._so(r['online'])} online, {giam}")
    return s.them(f": {_ngan(str(r['chu_y']))}" + (f" · {giam}" if giam else ""))


def _khoi_trao_doi(can: pd.DataFrame, tt: str) -> bt._Soan:
    s = bt._Soan().them("2) CẦN TRAO ĐỔI", "b", bt.CO_TIEU_DE)
    if can.empty:
        return s.them("\nKhông có nhân sự cần trao đổi.", bt.XANH)
    for _, r in can.iterrows():
        s.them("\n")
        s.phan.extend(_dong_trao_doi(r, tt).phan)
    return s


def _khoi_tro_trao_doi(n: int) -> bt._Soan:
    """Khi danh sách quá dài để nằm chung tin 1: tin 1 chỉ ghi số người, danh sách ở tin riêng ngay sau."""
    return (bt._Soan().them("2) CẦN TRAO ĐỔI", "b", bt.CO_TIEU_DE)
            .them("\n").them(f"{n} nhân sự", "b", bt.DO).them(", danh sách ở tin kế tiếp."))


def _khoi_chat_luong(q: pd.Series, tong_cn: pd.Series, xet: pd.DataFrame, co_ten: bool) -> bt._Soan | None:
    online = int(q["online"])
    if not online:
        return None
    s = bt._Soan().them("3) CHẤT LƯỢNG BÁN", "b", bt.CO_TIEU_DE).them(" (luỹ kế tháng)", bt.CO_NHO)
    s.them("\nV.VIP/PTTB: ")
    _so_voi_chung(s, q["vvip_ty_le"], tong_cn["vvip_ty_le"])
    s.them("\nCamera/online: ")
    _so_voi_chung(s, _ty_le(q["camera"], online), _ty_le(tong_cn["camera"], tong_cn["online"]))
    if co_ten:
        for cot, nhan in (("vvip", "V.VIP"), ("camera", "Camera")):
            ten = _ten_chua_ban_kem(xet, cot)
            if ten:
                s.them(f"\nChưa bán kèm {nhan} (online từ 3): ").them(_liet_ke(ten), "b")
    return s


def _khoi_ton(tong: pd.Series) -> bt._Soan | None:
    lau = int(tong["ton_qua_7"] or 0)
    if lau <= 0:
        return None
    s = bt._Soan().them("4) HỢP ĐỒNG TỒN", "b", bt.CO_TIEU_DE)
    return s.them("\n").them(f"{lau} hợp đồng", "b", bt.DO).them(f" chờ online từ 7 ngày trở lên (tổng tồn {bt._so(tong['ton'])}).")


def _khoi_nhan_dinh(c: dict, q: pd.Series, d: pd.Series, can: pd.DataFrame) -> bt._Soan:
    """Vài câu nhận định do LUẬT cố định sinh ra từ số đã có (không dùng AI)."""
    online, mt, con = int(q["online"]), int(q["mt_internet"] or 0), int(d["con_lai"])
    s = bt._Soan().them("NHẬN ĐỊNH NHANH", "b", bt.CO_TIEU_DE)
    if mt and online >= mt:
        s.them("\n• ").them(f"Đã đạt mục tiêu tháng ({bt._so(online)}/{bt._so(mt)}).", "b", bt.XANH)
    elif mt and con > 0:
        s.them("\n• ").them(f"Cần {bt._so(math.ceil((mt - online) / con))} online/ngày", "b", bt.DO)
        s.them(f" trong {con} ngày còn lại, hiện bình quân {bt._so(d['tb_ngay'], 1)}/ngày.")
    elif mt:
        s.them(f"\n• Hết tháng: đạt {bt._pct(online, mt)}% mục tiêu.")
    else:
        s.them("\n• Phòng chưa có mục tiêu tháng nên chưa đánh giá tiến độ.")
    dem = {m: int((can["muc"] == m).sum()) for m in (canh_bao.TRAO_DOI_NGAY, canh_bao.THEO_DOI, GIAM_CUNG_KY)}
    if len(can):
        chi_tiet = ", ".join(f"{n} {nhan}" for n, nhan in ((dem[canh_bao.TRAO_DOI_NGAY], "trao đổi ngay"),
                                                         (dem[canh_bao.THEO_DOI], "theo dõi"),
                                                         (dem[GIAM_CUNG_KY], "giảm so cùng kỳ")) if n)
        s.them("\n• ").them(f"{len(can)} nhân sự cần trao đổi", "b", bt.DO)
        s.them(f" ({chi_tiet}).")
    return s


def _tin_tong_quan(chung: dict, code: str, ten: str, data, can: pd.DataFrame) -> tuple[bt.TinZalo, bool]:
    """(tin 1, danh sách trao đổi có nằm trong tin 1 không). Tối đa 1.900 ký tự: dài quá thì bớt tên ở mục chất lượng bán,
    rồi tách danh sách cần trao đổi ra tin riêng (KHÔNG cắt bớt người)."""
    q, d, tong_cn = _dong(chung["tq"], code, "số liệu Báo cáo Tổng"), _dong(chung["db"], code, "dự báo"), \
        _dong(chung["tq"], "TOTAL", "số liệu Báo cáo Tổng")
    _, xet, tong = data
    tt = chung["thang_truoc"][5:7].lstrip("0")
    ngay = date.fromisoformat(chung["ngay_iso"])
    dau = (bt._Soan().them(f"Số chốt ngày {ngay:%d/%m} - {ten}", "b", bt.CO_DAU)
           .them(f"\nTổng quan phòng {ten}, luỹ kế tháng {ngay.month} (tới ngày {ngay:%d/%m}).", bt.CO_NHO))
    link = (os.environ.get("APP_URL") or "").strip()
    chan = bt._Soan().them(f"Xem chi tiết: {link}") if link else None
    nd, td = _khoi_nhan_dinh(chung, q, d, can), _khoi_tien_do(chung, q, d, _hang(chung, code))
    ton = _khoi_ton(tong)
    for nhung, co_ten in ((True, True), (True, False), (False, True), (False, False)):
        muc2 = _khoi_trao_doi(can, tt) if nhung or can.empty else _khoi_tro_trao_doi(len(can))
        chu = bt._ghep([dau, nd, td, muc2, _khoi_chat_luong(q, tong_cn, xet, co_ten), ton, chan])
        if len(chu) <= bt.TOI_DA_KY_TU:
            return chu, nhung or can.empty
    return bt._cat(chu, bt.TOI_DA_KY_TU), False


def dung_tin_tong_quan(chung: dict, code: str, ten: str, data=None) -> bt.TinZalo:
    data = data if data is not None else _nhan_su(chung, code)
    return _tin_tong_quan(chung, code, ten, data, can_trao_doi(data[1], code))[0]


# ------------------------------------------------------------------ tin 2: từng nhân sự
def _dong_nhan_su(r, tt: str, ngay: date) -> bt._Soan:
    chenh = int(r["online"]) - int(r["ck_online"])
    mau = [bt.XANH] if chenh > 0 else [bt.DO] if chenh < 0 else []
    s = bt._Soan().them("• ").them(str(r["ho_ten"]), "b")
    s.them(f": {bt._so(r['online'])} online · ")
    return s.them(f"{chenh:+d}" if chenh else "0", "b", *mau).them(f" so T{tt}")


def _dai(s: bt._Soan) -> int:
    return sum(len(c) for c, _ in s.phan)


def _chia_tin(dong: list[bt._Soan], dau) -> list[bt.TinZalo]:
    """Chia các dòng thành nhiều tin con, mỗi tin ≤ `TOI_DA_KY_TU` ký tự; `dau(i, n)` dựng phần đầu của tin thứ i / n."""
    cho = bt.TOI_DA_KY_TU - _dai(dau(99, 99))
    nhom: list[list[bt._Soan]] = [[]]
    dung = 0
    for d in dong:
        if nhom[-1] and dung + 1 + _dai(d) > cho:
            nhom.append([])
            dung = 0
        nhom[-1].append(d)
        dung += 1 + _dai(d)
    return [bt._ghep([dau(i, len(nhom)), _noi_dong(g)]) for i, g in enumerate(nhom, 1)]


def dung_tin_nhan_su(chung: dict, ten: str, xet: pd.DataFrame) -> list[bt.TinZalo]:
    """Mỗi người một dòng, xếp online giảm dần, tách tin con khi vượt `TOI_DA_KY_TU` ký tự. Không có ai thì trả rỗng."""
    if xet.empty:
        return []
    ngay, tt = date.fromisoformat(chung["ngay_iso"]), chung["thang_truoc"][5:7].lstrip("0")
    xs = xet.sort_values("online", ascending=False, kind="stable")
    chenh = xs["online"] - xs["ck_online"]
    dong: list[bt._Soan] = []
    for nhan, mau, g in ((f"TĂNG hoặc bằng cùng kỳ T{tt}", bt.XANH, xs[chenh >= 0]),
                         (f"GIẢM so với cùng kỳ T{tt}", bt.DO, xs[chenh < 0])):
        if g.empty:
            continue
        hang = [_dong_nhan_su(r, tt, ngay) for _, r in g.iterrows()]
        dau_nhom = bt._Soan().them("\n" if dong else "").them(f"{nhan} ({len(g)} người)", "b", mau).them("\n")
        dau_nhom.phan.extend(hang[0].phan)        # tiêu đề nhóm đi cùng dòng đầu để không bị bỏ lẻ cuối một tin con
        dong += [dau_nhom] + hang[1:]

    def dau(i: int, n: int) -> bt._Soan:
        s = bt._Soan().them(f"Số chốt ngày {ngay:%d/%m} - {ten}", "b", bt.CO_DAU)
        return s.them(f"\nPhần ({i}/{n})", bt.CO_NHO) if n > 1 else s

    return _chia_tin(dong, dau)


def dung_tin_trao_doi(chung: dict, ten: str, can: pd.DataFrame) -> list[bt.TinZalo]:
    """Danh sách cần trao đổi ở tin riêng (khi quá dài để nằm chung tin 1); tách nhiều tin con nếu cần."""
    ngay, tt = date.fromisoformat(chung["ngay_iso"]), chung["thang_truoc"][5:7].lstrip("0")

    def dau(i: int, n: int) -> bt._Soan:
        return (bt._Soan().them(f"Số chốt ngày {ngay:%d/%m} - {ten}", "b", bt.CO_DAU)
                .them(f"\nNhân sự cần trao đổi{f' ({i}/{n})' if n > 1 else ''}.", bt.CO_NHO))

    return _chia_tin([_dong_trao_doi(r, tt) for _, r in can.iterrows()], dau)


def _noi_dong(dong: list[bt._Soan]) -> bt._Soan:
    s = bt._Soan()
    for i, d in enumerate(dong):
        s.them("\n" if i else "")
        s.phan.extend(d.phan)
    return s


def dung_tin_phong(ngay_iso: str, code: str, chung: dict | None = None) -> list[tuple[str, bt.TinZalo]]:
    """[(phần, tin)]: `tq`, rồi `td1`... (chỉ khi danh sách cần trao đổi quá dài để nằm chung tin 1), rồi `ns1`, `ns2`...
    Một lượt đọc số nhân sự dùng cho mọi tin."""
    chung = chung or nap_chung(ngay_iso)
    ten = bcp.ten_phong(code)
    nhan_su = _nhan_su(chung, code)
    can = can_trao_doi(nhan_su[1], code)
    tin1, nhung = _tin_tong_quan(chung, code, ten, nhan_su, can)
    ra = [(PHAN_TONG_QUAN, tin1)]
    if not nhung:
        ra += [(f"{PHAN_TRAO_DOI}{i}", t) for i, t in enumerate(dung_tin_trao_doi(chung, ten, can), 1)]
    ra += [(f"ns{i}", t) for i, t in enumerate(dung_tin_nhan_su(chung, ten, nhan_su[1]), 1)]
    return ra


# ------------------------------------------------------------------ gửi + chống trùng
def _da_ok(ngay: date) -> set[tuple[int, str]]:
    with session_scope() as s:
        return set(s.execute(select(BanTinNhatKy.nguoi_nhan_id, BanTinNhatKy.loai).where(
            BanTinNhatKy.ngay_so == ngay, BanTinNhatKy.ket_qua == "ok", BanTinNhatKy.loai.like("tp:%"))).all())


def _gui_mot(nguoi: dict, chu) -> tuple[str | None, bool]:
    """(None nếu gửi được, ngược lại câu lý do; đã phải gửi chữ trơn vì Zalo từ chối kiểu chữ?)."""
    try:
        return None, zalo_bot.gui_tin_du_phong(nguoi["chat_id"], chu)
    except zalo_bot.LoiZalo as e:
        return str(e), False
    except Exception as e:
        return f"Lỗi không xác định khi gửi ({type(e).__name__}).", False


def _het_gio(kq: dict) -> None:
    """Báo hết giờ; đè lên câu "Không có ai cần nhận thêm" của bản BGĐ vì lúc này còn người trưởng phòng chưa được gửi."""
    if not kq["ly_do"] or kq["ly_do"].startswith("Không có ai"):
        kq["ly_do"] = "Gần hết thời gian cho phép, phần còn lại để lượt sau."


def _gui_cho_phong(nguoi: dict, ma: str, ngay: date, tin: list, ok: set, kq: dict, t0: float, han: float) -> None:
    """Gửi lần lượt các tin của một phòng cho một người; dừng ở tin đầu tiên chưa gửi được để thứ tự không đảo."""
    gui = 0
    ten = f"{nguoi['ten']} (phòng {ma})"
    for phan, chu in tin:
        loai = ma_loai(ma, phan)
        if (nguoi["id"], loai) in ok:
            continue
        if time.monotonic() - t0 > han:
            _het_gio(kq)
            return
        id_ = bt._giu_cho(ngay, nguoi, loai)
        if id_ is None:
            kq["bo_qua"].append({"nguoi": ten, "ly_do": "đã gửi, đang gửi hoặc hết lượt thử lại"})
            return
        ly_do, tron = _gui_mot(nguoi, chu)
        bt._ghi_ket_qua(id_, ly_do is None, ly_do or "")
        if ly_do is not None:
            kq["loi"].append({"nguoi": ten, "ly_do": ly_do})
            return
        if tron:
            kq.setdefault("chu_tron", []).append(f"{ten} · {phan}")
        gui += 1
    xong = bt._giu_cho(ngay, nguoi, ma_loai(ma, PHAN_XONG))
    if xong is not None:
        bt._ghi_ket_qua(xong, True)
    if gui:
        kq["da_gui"].append(ten)


def _chay_truong_phong(ngay_iso: str, kq: dict, t0: float, han: float) -> None:
    ngay = date.fromisoformat(ngay_iso)
    ok = _da_ok(ngay)
    xong = {(i, l) for i, l in ok if l.endswith(f":{PHAN_XONG}")}
    cho: dict[str, list[dict]] = {}
    for n in bt.ds_nguoi_nhan(bt.LOAI_TRUONG_PHONG, chi_bat=True):
        for p in n["phong"]:
            if (n["id"], ma_loai(p, PHAN_XONG)) not in xong:
                cho.setdefault(p, []).append(n)
    chung = None
    for ma, nguoi in cho.items():
        if time.monotonic() - t0 > han:
            _het_gio(kq)
            return
        try:
            chung = chung or nap_chung(ngay_iso)
            tin = dung_tin_phong(ngay_iso, ma, chung)
        except Exception as e:                     # một phòng hỏng không chặn phòng khác
            kq["loi"].append({"nguoi": f"(phòng {ma})", "ly_do": f"Không dựng được tin phòng {ma} ({type(e).__name__})."})
            continue
        for n in nguoi:
            _gui_cho_phong(n, ma, ngay, tin, ok, kq, t0, han)


def gui_truong_phong(ngay_iso: str, kq: dict, t0: float, han: float) -> None:
    """Gửi bản tin trưởng phòng sau bản BGĐ trong cùng lượt; lỗi ở đây không được làm hỏng phần đã gửi cho BGĐ."""
    try:
        _chay_truong_phong(ngay_iso, kq, t0, han)
    except Exception as e:
        kq["loi"].append({"nguoi": "(trưởng phòng)", "ly_do": f"Không gửi được bản tin trưởng phòng ({type(e).__name__})."})


# ------------------------------------------------------------------ gửi thử + chạy thử
def gui_thu_truong_phong(nguoi: dict) -> tuple[bool, str]:
    """Gửi thử các tin của (các) phòng của người này, ngày số mới nhất, nhãn "BẢN THỬ"; không ghi nhật ký ngày."""
    if not nguoi["phong"]:
        return False, f"{nguoi['ten']} chưa được gắn phòng nào."
    ngay_iso = bt.ngay_so_gui() or metrics.ngay_moi_nhat()
    if not ngay_iso:
        return False, "Chưa có số liệu nào để gửi thử."
    try:
        chung = nap_chung(ngay_iso)
        tin = [(ma, p, t) for ma in nguoi["phong"] for p, t in dung_tin_phong(ngay_iso, ma, chung)]
    except Exception as e:
        return False, f"Không dựng được tin thử ({type(e).__name__})."
    tron = []
    for ma, phan, t in tin:
        ly_do, la_tron = _gui_mot(nguoi, bt._voi_dau("[BẢN THỬ]\n", t))
        if ly_do:
            ghi_log("ban_tin_gui_thu", f"{nguoi['ten']} ({ma}/{phan}): {ly_do}"[:200])
            return False, (f"Chưa gửi được cho {nguoi['ten']} ở tin {nhan_loai_tin(ma_loai(ma, phan))} "
                           f"({len(t)} ký tự, {len(t.kieu)} kiểu chữ): {ly_do}")
        if la_tron:
            tron.append(f"{ma}/{phan}")
    ghi_log("ban_tin_gui_thu", f"{nguoi['ten']}: ok ({len(tin)} tin)" + (f", chữ trơn: {', '.join(tron)}" if tron else ""))
    return True, (f"Đã gửi {len(tin)} tin thử cho {nguoi['ten']} (phòng {', '.join(nguoi['phong'])})."
                  + (f" Zalo từ chối kiểu chữ ở {len(tron)} tin nên đã gửi chữ trơn." if tron else ""))


def kho_truong_phong(ngay_iso: str, phong: str | None) -> dict:
    """Phần thêm cho `chay(kho=True)`: người nhận trưởng phòng, và tin của một phòng nếu được hỏi. Không gửi, không ghi."""
    kq = {"truong_phong": [{"ten": n["ten"], "phong": n["phong"]}
                           for n in bt.ds_nguoi_nhan(bt.LOAI_TRUONG_PHONG, chi_bat=True)]}
    if phong:
        if phong not in {p["code"] for p in phong_chon_duoc()}:
            kq["ly_do_phong"] = "Phòng không hợp lệ (chỉ phòng bán hàng IBB và địa bàn)."
        else:
            try:
                tin = dung_tin_phong(ngay_iso, phong)
                kq["noi_dung_phong"] = [str(t) for _, t in tin]
                kq["kich_thuoc"] = [{"phan": p, "ky_tu": len(t), "so_kieu": len(t.kieu)} for p, t in tin]
            except Exception as e:
                kq["ly_do_phong"] = f"Không dựng được tin phòng {phong} ({type(e).__name__})."
    return kq
