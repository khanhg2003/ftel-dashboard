"""Tin chữ "NHẬN ĐỊNH & HÀNH ĐỘNG - <phòng>" của Bản tin 8h cho TRƯỞNG PHÒNG (CEO chốt 29/10/2026), đi sau ảnh Báo cáo phòng
và ảnh Báo cáo Tổng.

Đi sâu vào điều ảnh phòng chưa thể hiện rõ: mục tiêu cần đạt mỗi ngày (cả phòng và mỗi người), vị trí so với phòng cùng
nhóm, nhân sự cần trao đổi, nhịp, bán kèm, hợp đồng tồn lâu, rồi hành động đề xuất. Mọi câu do LUẬT cố định sinh ra từ số
đã có (không gọi AI); tên nhân sự được nêu (CEO đồng ý), không có tên khách hàng. Trưởng phòng / người đã nghỉ / acc tạm
không vào danh sách nhân sự bị nêu (đã loại ở `ban_tin_phong._nhan_su`), số của họ vẫn nằm trong số phòng. Dài hơn
`bt.TOI_DA_KY_TU` thì tách nhiều tin con (`nd1`, `nd2`...), không cắt bớt người.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from app import ban_tin as bt
from app import ban_tin_nd as nd
from app import ban_tin_phong as tp
from app import bao_cao_phong as bcp
from app import canh_bao, metrics

# ---- ngưỡng
CHENH_BAN_KEM_NGUOI = 15     # tỷ lệ V.VIP / Camera của một người thấp hơn mức chung của phòng từ bấy nhiêu điểm % mới nêu
TOI_THIEU_ONLINE_NGUOI = 5   # người có ít online hơn thì tỷ lệ chưa đủ tin cậy, không đem so
TOI_DA_NGUOI_THAP = 3        # nêu tối đa bấy nhiêu người có tỷ lệ thấp nhất cho mỗi chỉ số
TON_NGUOI_TU = 3             # người có từ bấy nhiêu HĐ tồn quá 7 ngày mới nêu tên
TOI_DA_NGUOI_TON = 6
TOI_DA_TEN_HANH_DONG = 6     # số tên tối đa trong một câu hành động (còn lại ghi "và N người khác")


def _nho(chu: str, *kieu: str) -> bt._Soan:
    return bt._Soan().them(chu, *kieu)


def _ten(ds) -> str:
    return tp._liet_ke([str(x) for x in ds])


# ------------------------------------------------------------------ các mục
def _muc_tieu(chung: dict, q: pd.Series, d: pd.Series, xet: pd.DataFrame) -> list[bt._Soan]:
    online, mt, con = int(q["online"]), int(q["mt_internet"] or 0), int(d["con_lai"])
    dong: list[bt._Soan] = []
    if not mt:
        dong.append(nd.dong_gach("Phòng chưa có mục tiêu tháng nên chưa tính được số cần đạt."))
    elif online >= mt:
        dong.append(nd.dong_gach((f"Đã đạt mục tiêu tháng ({bt._so(online)}/{bt._so(mt)}).", "b", bt.XANH)))
    elif con > 0:
        cung = nd.can_moi_ngay(mt, online, con)
        so_nguoi = len(xet)
        dong.append(nd.dong_gach("Cả phòng cần ", (f"{bt._so(cung)} online/ngày", "b", bt.DO),
                                 f" trong {con} ngày còn lại (hiện {bt._so(d['tb_ngay'], 1)}/ngày), "
                                 f"dự báo hụt {bt._so(max(mt - round(float(d['du_bao'])), 0))} so mục tiêu {bt._so(mt)}."))
        if so_nguoi:
            dong.append(nd.dong_gach(f"Chia bình quân {so_nguoi} nhân sự được xét: mỗi người cần ",
                                     (f"{bt._so(cung / so_nguoi, 1)} online/ngày", "b"),
                                     f" (hiện {bt._so(float(d['tb_ngay']) / so_nguoi, 1)}/người/ngày)."))
    else:
        dong.append(nd.dong_gach(f"Hết tháng: đạt {bt._pct(online, mt)}% mục tiêu."))
    mt_ngay = int(q["mt_ngay"] or 0)
    if mt_ngay > 0:
        on = int(q["ngay_online"] or 0)
        s = nd.dong_gach(f"Online ngày {chung['ngay']:02d}/{chung['thang'][5:7]}: ", (bt._so(on), "b", bt.XANH if on >= mt_ngay else bt.DO),
                         f"/{bt._so(mt_ngay)} mục tiêu ngày")
        dong.append(s.them(f", thiếu {bt._so(mt_ngay - on)}." if on < mt_ngay else ", đạt."))
    return nd.muc("1) MỤC TIÊU CẦN ĐẠT", dong)


def _vi_tri(chung: dict, code: str) -> list[bt._Soan]:
    """Hạng theo "Số online tháng" trong nhóm phòng cùng loại (như Báo cáo phòng) và khoảng cách với phòng hạng 1 / hạng ngay trên."""
    nhom = bcp.phong_cung_nhom(code, chung["thang"])
    d = chung["tq"]
    d = d[(d["loai_dong"] == "data") & d["phong_code"].isin(nhom)].sort_values("online", ascending=False, kind="stable")
    mine = d[d["phong_code"] == code]
    if mine.empty:
        return []
    on = int(mine.iloc[0]["online"])
    hang = int((d["online"] > on).sum() + 1)
    hon = d[d["online"] > on]
    if hang == 1:
        sau = d[d["phong_code"] != code]
        if sau.empty:
            return []
        h2 = sau.iloc[0]
        dong = nd.dong_gach(f"Hạng 1/{len(d)}: ", (f"hơn phòng thứ hai ({h2['phong']}) {bt._so(on - int(h2['online']))} online", "b", bt.XANH), ".")
    else:
        dau = d.iloc[0]
        dong = nd.dong_gach(f"Hạng {hang}/{len(d)}: kém phòng hạng 1 ({dau['phong']}) ", (f"{bt._so(int(dau['online']) - on)} online", "b", bt.DO))
        if hang > 2:
            tren = hon.iloc[-1]
            dong.them(f", kém phòng ngay trên ({tren['phong']}) {bt._so(int(tren['online']) - on)}")
        dong.them(".")
    return nd.muc("2) VỊ TRÍ", [dong], "(cùng nhóm phòng bán hàng)")


def _muc_trao_doi(can: pd.DataFrame, tt: str) -> list[bt._Soan]:
    if can.empty:
        return nd.muc("3) CẦN TRAO ĐỔI", [_nho("Không có nhân sự cần trao đổi.", bt.XANH)])
    return nd.muc("3) CẦN TRAO ĐỔI", [tp._dong_trao_doi(r, tt) for _, r in can.iterrows()])


def _nhip(xet: pd.DataFrame, code: str) -> tuple[list[tuple[str, int]], list[tuple[str, int, int]]]:
    """(người nhiều ngày liền chưa có số, người tuần này giảm mạnh) theo đúng ngưỡng của `canh_bao`."""
    x = tp.xet_trao_doi(xet, code)
    chua = pd.to_numeric(x["ngay_lien_chua_co_so"], errors="coerce")
    ds_chua = [(str(r["ho_ten"]), int(c)) for (_, r), c in zip(x.iterrows(), chua) if pd.notna(c) and c >= canh_bao.NGAY_THEO_DOI]
    tn, tt = pd.to_numeric(x["tuan_nay"]).fillna(0), pd.to_numeric(x["tuan_truoc"]).fillna(0)
    sut = (tt >= canh_bao.TUAN_TRUOC_TOI_THIEU) & (tn <= tt * canh_bao.SUT_TUAN)
    ds_sut = [(str(r["ho_ten"]), int(a), int(b)) for (_, r), a, b, m in zip(x.iterrows(), tn, tt, sut) if m]
    return sorted(ds_chua, key=lambda t: -t[1]), sorted(ds_sut, key=lambda t: t[1] - t[2])


def _muc_nhip(chua: list, sut: list) -> list[bt._Soan]:
    """Chỉ tóm tắt (số người + người nặng nhất): từng người đã có tên ở mục "Cần trao đổi" kèm lý do."""
    dong = []
    if chua:
        ten, n = chua[0]
        dong.append(nd.dong_gach((f"{len(chua)} người", "b", bt.DO), f" nhiều ngày liền chưa có số, lâu nhất: {ten} ({n} ngày)."))
    if sut:
        ten, a, b = sut[0]
        dong.append(nd.dong_gach((f"{len(sut)} người", "b", bt.DO), f" tuần này giảm mạnh so tuần trước, nhiều nhất: {ten} ({a} so {b})."))
    return nd.muc("4) NHỊP BÁN", dong)


def _ban_kem(xet: pd.DataFrame, q: pd.Series, tong_cn: pd.Series) -> tuple[list[bt._Soan], dict]:
    """(các dòng, {'V.VIP'|'Camera': [người chưa bán kèm]} + 'thap_*' để làm hành động). Mức chung = tỷ lệ của cả phòng."""
    online = int(q["online"])
    dong, ghi = [], {"chua": {}, "thap": {}}
    chung_cn = {"V.VIP": tong_cn["vvip_ty_le"], "Camera": tp._ty_le(tong_cn["camera"], tong_cn["online"])}
    for cot, ten in (("vvip", "V.VIP"), ("camera", "Camera")):
        chua = tp._ten_chua_ban_kem(xet, cot)
        ghi["chua"][ten] = chua
        if chua:
            dong.append(nd.dong_gach(f"Bán nhiều (từ 3 online) mà chưa bán kèm {ten}: ", (tp._liet_ke(chua), "b"), "."))
        phong = round(float(q[cot]) / online * 100) if online else None
        x = xet[(xet["online"] >= TOI_THIEU_ONLINE_NGUOI) & (xet[cot] > 0)].copy()
        if phong is None or x.empty:
            ghi["thap"][ten] = (phong, [])
            continue
        x["ty_le"] = (x[cot] / x["online"] * 100).round()
        thap = x[x["ty_le"] <= phong - CHENH_BAN_KEM_NGUOI].sort_values("ty_le").head(TOI_DA_NGUOI_THAP)
        ghi["thap"][ten] = (phong, [str(n) for n in thap["ho_ten"]])
        if len(thap):
            dong.append(nd.dong_gach(f"{ten} thấp hơn mức chung của phòng ({bt._so(phong)}%): "
                                     + ", ".join(f"{r['ho_ten']} {bt._so(r['ty_le'])}%" for _, r in thap.iterrows()) + "."))
    ghi["chung_cn"] = chung_cn
    return dong, ghi


def _ton_nguoi(xet: pd.DataFrame, tong: pd.Series) -> tuple[list[bt._Soan], pd.DataFrame]:
    x = xet.assign(ton_qua_7=pd.to_numeric(xet["ton_qua_7"]).fillna(0).astype(int))
    nhieu = x[x["ton_qua_7"] >= TON_NGUOI_TU].sort_values("ton_qua_7", ascending=False, kind="stable").head(TOI_DA_NGUOI_TON)
    lau = int(tong["ton_qua_7"] or 0)
    if lau <= 0:
        return [], nhieu
    dong = [nd.dong_gach((f"{lau} hợp đồng", "b", bt.DO), f" chờ online từ {nd.TON_QUA_NGAY} ngày trở lên (tổng tồn {bt._so(tong['ton'])}).")]
    if len(nhieu):
        dong.append(nd.dong_gach("Nhiều nhất, xử lý trước: " + ", ".join(f"{r['ho_ten']} ({r['ton_qua_7']} HĐ)" for _, r in nhieu.iterrows()) + "."))
    return dong, nhieu


# ------------------------------------------------------------------ hành động đề xuất (luật cố định)
def _hanh_dong(ngay_iso: str, q: pd.Series, d: pd.Series, xet: pd.DataFrame, can: pd.DataFrame, ban_kem: dict,
               nhieu_ton: pd.DataFrame, tt: str) -> list[bt._Soan]:
    han, cuoi = nd.ngay_vn(nd.han_xu_ly(ngay_iso)), nd.ngay_vn(nd.cuoi_thang(ngay_iso))
    online, mt, con = int(q["online"]), int(q["mt_internet"] or 0), int(d["con_lai"])
    dong: list[bt._Soan] = []
    if mt and online < mt and con > 0:
        cung = nd.can_moi_ngay(mt, online, con)
        dong.append(nd.dong_gach("Trưởng phòng chốt mục tiêu cả phòng ", (f"{bt._so(cung)} online/ngày", "b", bt.DO),
                                 f" ({bt._so(cung / max(len(xet), 1), 1)}/người/ngày) từ nay đến hết {cuoi} và giao cụ thể cho từng người trước {han}."))
    gap = can[can["muc"].isin([canh_bao.TRAO_DOI_NGAY, canh_bao.THEO_DOI])]
    if len(gap):
        dong.append(nd.dong_gach("Trao đổi ngay với ", (_ten(gap["ho_ten"]), "b"), f" trước {han}: chốt lý do và kế hoạch có số online trở lại."))
    giam = can[can["muc"] == tp.GIAM_CUNG_KY]
    if len(giam):
        bu = int((giam["ck_online"] - giam["online"]).sum())
        dong.append(nd.dong_gach(f"Họp nhanh nhóm thấp hơn cùng kỳ T{tt} (", (_ten(giam["ho_ten"]), "b"),
                                 f") trước {han}: cùng bù lại ", (f"{bt._so(bu)} online", "b", bt.DO), f" đến hết {cuoi}."))
    for ten, chua in ban_kem["chua"].items():
        if chua:
            muc_cn = ban_kem["chung_cn"][ten]
            dong.append(nd.dong_gach("Nhắc ", (tp._liet_ke(chua), "b"), f" bán kèm {ten} ở mọi HĐ mới"
                                     + (f", đưa tỷ lệ phòng lên tối thiểu {bt._so(muc_cn)}% (mức chi nhánh)" if muc_cn is not None else "")
                                     + f" đến hết {cuoi}."))
    if len(nhieu_ton):
        dong.append(nd.dong_gach("Xử lý dứt điểm HĐ tồn từ 7 ngày trước ", (han, "b"), ": " + ", ".join(
            f"{r['ho_ten']} {r['ton_qua_7']} HĐ" for _, r in nhieu_ton.iterrows()) + "."))
    if not dong:
        dong.append(nd.dong_gach(("Chưa có việc cần can thiệp:", "b", bt.XANH), " giữ nhịp hiện tại và rà lại HĐ tồn mỗi ngày."))
    return nd.muc("7) HÀNH ĐỘNG ĐỀ XUẤT", dong, f"(xử lý nhanh trước {han}, mục tiêu tháng đến hết {cuoi})")


# ------------------------------------------------------------------ dựng tin
def dung_nhan_dinh_phong(chung: dict, code: str, ten: str, nhan_su: tuple, can: pd.DataFrame) -> list[bt.TinZalo]:
    """Danh sách tin "NHẬN ĐỊNH & HÀNH ĐỘNG" của một phòng (thường chỉ một tin; dài thì tách, mỗi tin ≤ `bt.TOI_DA_KY_TU`)."""
    q, d = tp._dong(chung["tq"], code, "số liệu Báo cáo Tổng"), tp._dong(chung["db"], code, "dự báo")
    tong_cn = tp._dong(chung["tq"], "TOTAL", "số liệu Báo cáo Tổng")
    _, xet, tong = nhan_su
    tt = chung["thang_truoc"][5:7].lstrip("0")
    ngay = date.fromisoformat(chung["ngay_iso"])
    chua, sut = _nhip(xet, code)
    dong_kem, ban_kem = _ban_kem(xet, q, tong_cn)
    dong_ton, nhieu_ton = _ton_nguoi(xet, tong)
    muc_ = [_muc_tieu(chung, q, d, xet), _vi_tri(chung, code), _muc_trao_doi(can, tt), _muc_nhip(chua, sut),
            nd.muc("5) BÁN KÈM", dong_kem, "(luỹ kế tháng)"), nd.muc("6) HỢP ĐỒNG TỒN", dong_ton),
            _hanh_dong(chung["ngay_iso"], q, d, xet, can, ban_kem, nhieu_ton, tt)]
    khoi: list[bt._Soan] = []
    for m in muc_:                      # mỗi mục cách mục trước một dòng trống
        if m:
            khoi.append(_cach_khoi(m[0], bool(khoi)))
            khoi.extend(m[1:])

    def dau(i: int, n: int) -> bt._Soan:
        s = bt._Soan().them(f"NHẬN ĐỊNH & HÀNH ĐỘNG - {ten}", "b", bt.CO_DAU)
        s.them(f"\nBổ sung cho ảnh Báo cáo phòng: luỹ kế tháng {ngay.month}, còn {metrics.month_range(chung['thang'])[2] - chung['ngay']} ngày.",
               bt.CO_NHO)
        return s.them(f" Phần ({i}/{n})", bt.CO_NHO) if n > 1 else s

    return tp._chia_tin(khoi, dau)


def _cach_khoi(dong: bt._Soan, co_truoc: bool) -> bt._Soan:
    """Thêm một dòng trống trước tiêu đề mục (trừ mục đầu) để các mục tách nhau."""
    if not co_truoc:
        return dong
    s = bt._Soan().them("\n")
    s.phan.extend(dong.phan)
    return s

