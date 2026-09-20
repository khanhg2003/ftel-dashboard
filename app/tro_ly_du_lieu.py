"""Số liệu đưa cho trợ lý AI: ngữ cảnh nhận xét từng trang và các công cụ tra số của chatbot.

Mọi hàm đều lọc theo quyền của người đang hỏi, giống hệt giao diện:
- số chung theo phòng: phạm vi `phong_duoc_xem()`;
- chi tiết nhân sự, NSLĐ: chỉ vai trò được xem nhân sự, Trưởng phòng chỉ phòng mình.
Bảng gửi đi dạng CSV cho gọn token. Không có tên khách hàng.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

import pandas as pd

from app import bao_cao_phong as bp
from app import fox_insight as fi
from app import nsld
from app import phan_tich as pt
from app.du_bao import du_bao_thang
from app.metrics import (METRICS, cac_ngay_co_du_lieu, daily_counts, month_range, prev_month, tong_theo_acc,
                         tong_theo_phong)
from app.org import loc_chi_nhanh, phong_order
from app.overview import TEN_PHAM_VI, bang_tong_quan
from app.tro_ly import MAU_NHO_CUNG_KY, LoiAI

COT_TONG = {"phong": "Phòng", "nhan_su": "Nhân sự", "mt_internet": "MT Internet", "online": "Online",
            "htkh_internet": "%HTKH", "ck_online": "Cùng kỳ", "tang_truong": "%Tăng trưởng",
            "so_ton": "Số tồn", "vvip": "V.VIP", "vvip_ty_le": "%VVIP/PTTB", "fpl_combo": "FPT Play",
            "camera": "Camera", "mt_camera": "MT Camera", "htkh_camera": "%HTKH Camera",
            "cnql": "PTTB CNQL", "ngay_online": "Online ngày cuối", "mt_ngay": "MT ngày",
            # tính sẵn cho insight - AI không phải tự làm phép tính
            "chenh_tien_do": "Chênh tiến độ", "chenh_ck": "Chênh cùng kỳ (số)", "dong_gop": "% phần tăng/giảm của cả chi nhánh",
            "mau_nho": "Mẫu nhỏ", "tuan_nay": "7 ngày gần nhất", "tuan_truoc": "7 ngày trước đó",
            "ton_qua_7": "Hợp đồng chờ quá 7 ngày"}
COT_DU_BAO = {"phong": "Phòng", "mt": "MT tháng", "luy_ke": "Luỹ kế", "tb_ngay": "TB/ngày",
              "du_bao": "Dự báo cuối tháng", "pct_mt": "%MT dự báo",
              "du_bao_tuan": "Nếu chỉ giữ nhịp 7 ngày gần nhất", "can_moi_ngay": "Cần mỗi ngày",
              "danh_gia": "Đánh giá"}
COT_NV = {"ho_ten": "Họ tên", "acc": "Acc", "hang": "Hạng", "online": "Online", "ck_online": "Cùng kỳ",
          "online_ngay": "Online ngày cuối", "vvip": "V.VIP", "camera": "Camera", "ban_moi": "Bán mới",
          "ton": "Tồn", "ton_qua_7": "Hợp đồng chờ quá 7 ngày", "ngay_lien_chua_co_so": "Ngày liền chưa có số",
          "tuan_nay": "7 ngày gần nhất", "tuan_truoc": "7 ngày trước đó", "ket_luan": "NSLĐ tháng gần nhất",
          "muc_chu_y": "Mức chú ý", "chu_y": "Cần chú ý"}
TEN_CHI_SO = {"online": "Số online", "vvip": "V.VIP", "fptplay": "FPT Play (combo)", "camera": "Camera",
              "ban_moi": "Hợp đồng tạo mới"}


def csv(df: pd.DataFrame, cot: dict) -> str:
    if df is None or df.empty:
        return "(không có dữ liệu)"
    co = [c for c in cot if c in df.columns]
    # đổi sẵn ra chữ: 30.0 -> "30", trống -> "" (để pandas không tự đổi cả cột về số thực)
    gon = df[co].astype(object).map(lambda v: "" if v is None or v != v else
                                    str(int(v)) if isinstance(v, float) and v.is_integer() else v)
    return gon.rename(columns=cot).to_csv(index=False).strip()


def _ngay_hop_le(ngay_iso: str | None) -> date:
    ngays = cac_ngay_co_du_lieu()
    if not ngays:
        raise LoiAI("Chưa có số liệu nào được nạp.")
    try:
        d = min(date.fromisoformat(str(ngay_iso)[:10]), date.fromisoformat(ngays[-1]))
    except ValueError:
        d = date.fromisoformat(ngays[-1])
    return d


def _ma_phong(phong: str | None) -> str | None:
    if not phong:
        return None
    p = str(phong).strip().lower()
    for x in phong_order():
        if p in (x["code"].lower(), x["ten"].lower()):
            return x["code"]
    raise LoiAI(f"'{phong}' không phải mã phòng. Nếu đây là một nhân sự thì gọi công cụ nhan_su_ca_nhan; "
                "nếu là phòng thì lấy đúng mã trong danh sách phòng ở ngữ cảnh.")


def _chan_nhan_su(user, code: str | None = None) -> None:
    if not user.duoc_xem_nhan_su:
        raise LoiAI("Tài khoản này không được xem chi tiết nhân sự / NSLĐ.")
    pv = user.phong_nhan_su()
    if code and pv is not None and code not in pv:
        raise LoiAI("Bạn chỉ được xem chi tiết nhân sự của phòng mình phụ trách.")


# ------------------------------------------------------------------ nhận xét từng trang
def _quyen_ns(user) -> str:
    """Phần khoá lưu theo quyền xem nhân sự: nhận xét có thể nêu tên nhân sự, không dùng chung giữa các quyền."""
    return "ns=" + ("-" if not user.duoc_xem_nhan_su else
                    "all" if user.phong_nhan_su() is None else ",".join(sorted(user.phong_nhan_su())))


def ngu_canh_tong(user, tu: str | None, den: str | None, chi_nhanh: str | None) -> tuple[str, Callable[[], str]]:
    """(khoá lưu, hàm dựng số liệu) cho Báo cáo Tổng - khoá tính nhanh để tra bản đã lưu trước."""
    d = _ngay_hop_le(den)
    thang, cn = f"{d.year}-{d.month:02d}", chi_nhanh or "all"
    tu = tu[:10] if tu and tu[:10] <= d.isoformat() else d.replace(day=1).isoformat()
    scope = loc_chi_nhanh(user.phong_duoc_xem(), cn, thang)
    return f"{tu}|{d}|{cn}|{scope}|{_quyen_ns(user)}", lambda: _du_lieu_tong(user, d, thang, cn, tu, scope)


def thoi_gian_da_qua(d: date) -> int:
    """% số ngày của tháng đã qua tính đến ngày d."""
    return round(d.day / month_range(f"{d.year}-{d.month:02d}")[2] * 100)


def dong_thoi_gian(d: date) -> str:
    return (f"Tiến độ thời gian: đã qua {d.day}/{month_range(f'{d.year}-{d.month:02d}')[2]} ngày của tháng = "
            f"{thoi_gian_da_qua(d)}% thời gian.")


def ngay_chot_7(d: date) -> date:
    """Ngày cuối của cửa sổ '7 ngày gần nhất': bỏ ngày d nếu d còn đang nạp số (tạm tính)."""
    from app.overview import trang_thai_ngay
    return d - pd.Timedelta(days=1) if trang_thai_ngay(d.isoformat())[0] else d


def _them_insight(df: pd.DataFrame, d: date, tu: str) -> pd.DataFrame:
    """Thêm cột tính sẵn: chênh tiến độ, chênh cùng kỳ bằng số, % đóng góp, mẫu nhỏ, 7 ngày gần / trước."""
    df = df.copy()
    meta = {p["code"]: p for p in phong_order()}
    ma_cua_dong = {"data": lambda c: [c], "subtotal": lambda c: [k for k, v in meta.items() if f"SUB_{v['bay']}" == c],
                   "chinhanh": lambda c: [k for k, v in meta.items() if f"CN_{v.get('chi_nhanh')}" == c],
                   "total": lambda c: list(df[df.loai_dong == "data"].phong_code)}

    def theo_khoang(a: date, b: date) -> list[int]:
        s = tong_theo_phong(a.isoformat(), b.isoformat(), "online").set_index("phong_code")["n"]
        return [int(s.reindex(ma_cua_dong.get(l, lambda c: [])(c)).fillna(0).sum())
                for l, c in zip(df.loai_dong, df.phong_code)]
    tuan = pd.Timedelta(days=7)
    c = ngay_chot_7(d)                     # ngày cuối đang tạm tính thì so 7 ngày ĐÃ CHỐT, tránh báo "chậm lại" sai
    df["tuan_nay"] = theo_khoang(c - pd.Timedelta(days=6), c)
    df["tuan_truoc"] = theo_khoang(c - tuan - pd.Timedelta(days=6), c - tuan)
    ton = pt.hop_dong_ton()
    ton7 = ton[ton.so_ngay_cho >= 7].groupby("phong_code").size() if len(ton) else pd.Series(dtype=int)
    df["ton_qua_7"] = [int(ton7.reindex(ma_cua_dong.get(l, lambda c: [])(c)).fillna(0).sum())
                       for l, c in zip(df.loai_dong, df.phong_code)]
    df["chenh_ck"] = (df.online - df.ck_online).astype(int)
    # % trong tổng mức tăng (phòng tăng) hoặc tổng mức giảm (phòng giảm) của các phòng - không chia cho chênh ròng
    # vì chênh ròng nhỏ sẽ ra % vô nghĩa (VD 138%)
    phong = df[df.loai_dong == "data"].chenh_ck
    tang, giam = int(phong[phong > 0].sum()), int(-phong[phong < 0].sum())
    df["dong_gop"] = [None if l != "data" or not v else round(v / (tang if v > 0 else giam) * 100)
                      for v, l in zip(df.chenh_ck, df.loai_dong)]
    df["mau_nho"] = ["có" if ck < MAU_NHO_CUNG_KY else "" for ck in df.ck_online]
    luy_ke = tu == d.replace(day=1).isoformat()
    df["chenh_tien_do"] = [None if not luy_ke or h is None else round(h - thoi_gian_da_qua(d))
                           for h in df.htkh_internet]
    return df


def _bang_insight(d: date, thang: str, cn: str, tu: str, scope) -> pd.DataFrame:
    def dung():
        df, _ = bang_tong_quan(thang, d.day, chi_phong=scope, chi_nhanh=cn, tu=tu)
        return _them_insight(df, d, tu)
    return fi.nho("bang_insight", (d, thang, cn, tu, fi._tuple(scope)), dung)


def _nhan_su_phong(thang: str, ngay: int, code: str) -> pd.DataFrame:
    return fi.nho("nhan_su_phong", (thang, ngay, code), lambda: bp.bang_nhan_su(thang, ngay, code))


def _bang_tong(d: date, thang: str, cn: str, tu: str, scope, chi: set[str] | None = None) -> str:
    """Bảng Báo cáo Tổng dạng CSV. `chi`: chỉ lấy các phòng này (kèm dòng tổng) - chat hỏi vài phòng cho gọn token."""
    df = _bang_insight(d, thang, cn, tu, scope)
    if chi:
        df = df[df.phong_code.isin(chi) | (df.loai_dong == "total")]
    return (f"Kỳ: {tu} đến {d.isoformat()} · phạm vi {TEN_PHAM_VI.get(cn, cn)}. Cột 'Online ngày cuối' "
            f"và 'MT ngày' là của riêng ngày {d:%d/%m}. {dong_thoi_gian(d)} '7 ngày gần nhất' = "
            f"{(ngay_chot_7(d) - pd.Timedelta(days=6)):%d/%m}-{ngay_chot_7(d):%d/%m} (chỉ ngày đã chốt số).\n"
            f"BẢNG KẾT QUẢ THEO PHÒNG (dòng TỔNG ... là tổng bầy / chi nhánh):\n{csv(df, COT_TONG)}")


def _so(v) -> str:
    return f"{int(round(v)):,}".replace(",", ".")


def tin_hieu_tong(d: date, thang: str, cn: str, tu: str, scope) -> str:
    """Các tín hiệu then chốt app TÍNH SẴN để AI suy luận sâu mà không phải tự làm phép tính:
    ai gây ra phần thiếu mục tiêu, đòn bẩy nào lấp được bao nhiêu, năng suất, xu hướng 7 ngày đã chốt."""
    from app.overview import phong_khong_cong_tong
    df = _bang_insight(d, thang, cn, tu, scope)
    db = du_bao_thang(thang, d.day, scope).set_index("phong_code")
    meta = {p["code"]: p for p in phong_order(thang)}
    bo = phong_khong_cong_tong()
    ph = df[(df.loai_dong == "data") & ~df.phong_code.isin(bo)].set_index("phong_code")
    ph = ph[ph.index.isin(db.index)]
    tong = db.loc["TOTAL"]
    dong = []
    if tong.mt:
        thieu = max(int(tong.mt) - int(tong.du_bao), 0)
        dong.append(f"- Dự báo toàn phạm vi {_so(tong.du_bao)}/{_so(tong.mt)} = {int(tong.pct_mt)}% mục tiêu, THIẾU "
                    f"{_so(thieu)} online. Cần {_so(tong.can_moi_ngay or 0)}/ngày trong khi đang "
                    f"{str(tong.tb_ngay).replace('.', ',')}/ngày "
                    + (f"(phải nhanh hơn {round((tong.can_moi_ngay / tong.tb_ngay - 1) * 100)}%)."
                       if tong.can_moi_ngay and tong.tb_ngay else "."))
        gap = pd.Series({c: max(int(db.at[c, "mt"] or 0) - int(db.at[c, "du_bao"] or 0), 0) for c in ph.index})
        gap = gap[gap > 0].sort_values(ascending=False)
        if thieu and len(gap):
            top = gap.head(3)
            dong.append("- Hụt nhiều nhất so với mục tiêu tháng (trong ngoặc là phần chiếm trong tổng phần "
                        "còn thiếu của các phòng): " + ", ".join(
                            f"{meta[c]['ten']} hụt {_so(v)} online ({round(v / gap.sum() * 100)}%)"
                            for c, v in top.items()) + f"; {len(gap)} phòng dự báo không đạt.")
        tuan = db.attrs.get("tuan") or {}
        if tong.du_bao_tuan is not None and tuan.get("so_ngay"):
            chenh = int(tong.du_bao) - int(tong.du_bao_tuan)
            dong.append(f"- Kịch bản không bứt tốc: nếu từ giờ tới cuối tháng chỉ bán đều như "
                        f"{tuan['so_ngay']} ngày gần nhất ({str(tuan['tb']).replace('.', ',')} online/ngày) thì "
                        f"cuối tháng {_so(tong.du_bao_tuan)} = {int(tong.pct_tuan)}% mục tiêu"
                        + (f", thấp hơn dự báo chính {_so(chenh)} online - đây là phần đang trông vào nhịp bứt "
                           "cuối tháng." if chenh > 0 else "; tuần vừa rồi đang chạy nhanh hơn nhịp tháng "
                           "trước."))
        ton7 = int(ph.ton_qua_7.sum())
        if ton7:
            dong.append(f"- Hợp đồng chờ lâu: {_so(ton7)} hợp đồng đã chờ quá 7 ngày. Nếu chuyển được một nửa thành online thì "
                        f"dự báo lên khoảng {round((tong.du_bao + ton7 / 2) / tong.mt * 100)}% mục tiêu. Chờ lâu "
                        "nhiều nhất ở: " + ", ".join(f"{meta[c]['ten']} {v}" for c, v in
                                                      ph.ton_qua_7.sort_values(ascending=False).head(3).items()) + ".")
    kd = ph[[meta[c].get("loai") in ("IBB", "DIABAN") for c in ph.index]]
    kd = kd[pd.to_numeric(kd.nhan_su, errors="coerce").fillna(0) >= 5]
    if len(kd):
        ns = (kd.online / kd.nhan_su.astype(float)).round(1)
        tb = round(float(kd.online.sum() / kd.nhan_su.astype(float).sum()), 1)
        dong.append(f"- Năng suất (online / nhân sự, phòng kinh doanh từ 5 người): bình quân {tb}. Thấp nhất: "
                    + ", ".join(f"{meta[c]['ten']} {v} ({int(kd.at[c, 'nhan_su'])} người)"
                                for c, v in ns.sort_values().head(2).items())
                    + "; cao nhất: " + ", ".join(f"{meta[c]['ten']} {v}" for c, v in
                                                  ns.sort_values(ascending=False).head(2).items()) + ".")
    t = df[df.loai_dong == "total"].iloc[0]
    if t.tuan_truoc:
        chenh = (ph.tuan_nay - ph.tuan_truoc).sort_values()
        dong.append(f"- 7 ngày đã chốt gần nhất: {_so(t.tuan_nay)} online so với {_so(t.tuan_truoc)} 7 ngày trước đó "
                    f"({round((t.tuan_nay / t.tuan_truoc - 1) * 100):+d}%). Giảm nhiều nhất: "
                    + ", ".join(f"{meta[c]['ten']} {v:+d}" for c, v in chenh.head(2).items() if v < 0)
                    + "; tăng nhiều nhất: " + ", ".join(f"{meta[c]['ten']} {v:+d}" for c, v in
                                                        chenh.sort_values(ascending=False).head(2).items() if v > 0)
                    + ".")
    ss = so_voi_thang_truoc(thang, d.day, scope)
    if ss:
        dong.insert(1, ss)
    return "TÍN HIỆU CHÍNH (app đã tính sẵn - ưu tiên dùng):\n" + "\n".join(dong)


def so_voi_thang_truoc(thang: str, ngay: int, codes: list[str] | None) -> str:
    """Cùng thời điểm tháng trước: tới ngày này tháng trước đã làm được bao nhiêu % số của CẢ tháng đó (nhịp
    cuối tháng thường bứt lên), và nếu có mục tiêu tháng trước thì kèm % mục tiêu lúc đó / lúc cuối tháng."""
    from app.overview import _targets, phong_khong_cong_tong
    chot = ngay_chot_7(date.fromisoformat(f"{thang}-{ngay:02d}"))     # ngày đang tạm tính thì so tới hôm trước
    if chot.month == int(thang[5:7]):
        ngay = chot.day
    pm = prev_month(thang)
    k = min(ngay, month_range(pm)[2])
    d_nay, d_truoc = daily_counts(thang, "online"), daily_counts(pm, "online")
    giu = lambda d: [c for c in d.index if codes is None or c in codes]      # noqa: E731
    nay = int(d_nay.loc[giu(d_nay), :ngay].to_numpy().sum())
    truoc_ngay = int(d_truoc.loc[giu(d_truoc), :k].to_numpy().sum())
    truoc_ca = int(d_truoc.loc[giu(d_truoc)].to_numpy().sum())
    if not truoc_ca:
        return ""
    ty_trong = truoc_ngay / truoc_ca
    dong = (f"- So cùng thời điểm tháng trước: tới ngày {k:02d}/{pm[5:7]} tháng trước có {_so(truoc_ngay)} online = "
            f"{round(ty_trong * 100)}% số của cả tháng {pm[5:7]} ({_so(truoc_ca)}); nếu tháng này giữ đúng nhịp đó thì "
            f"cuối tháng khoảng {_so(nay / ty_trong)} online (luỹ kế hiện {_so(nay)}). Luỹ kế hiện tại so cùng kỳ "
            f"{round((nay / truoc_ngay - 1) * 100) if truoc_ngay else 0:+d}%.")
    tg = _targets(pm)
    if "internet" in tg.columns:
        bo = phong_khong_cong_tong()
        mt = float(tg["internet"].reindex([c for c in giu(d_truoc) if codes is not None or c not in bo]).fillna(0).sum())
        if mt:
            dong += (f" Tháng trước ở ngày {k:02d} đạt {round(truoc_ngay / mt * 100)}% mục tiêu, cuối tháng về "
                     f"{round(truoc_ca / mt * 100)}%.")
    return dong


def tin_hieu_phong(d: date, code: str) -> str:
    """Tín hiệu then chốt ở mức NHÂN SỰ cho Báo cáo phòng: ai gây phần thiếu, năng suất từng người, ai chững lại
    7 ngày đã chốt, tồn chờ lâu nằm ở ai, phụ thuộc vào vài người."""
    thang = f"{d.year}-{d.month:02d}"
    ten = bp.ten_phong(code)
    db = du_bao_thang(thang, d.day, [code]).set_index("phong_code").loc[code]
    nv = _nhan_su_phong(thang, d.day, code)
    nv = nv[(nv.loai_dong == "data") & (nv.khong_xet != "Trưởng phòng")].copy()   # TP không xếp hạng
    for c in ("online", "ck_online", "ton_qua_7", "ngay_lien_chua_co_so"):
        nv[c] = pd.to_numeric(nv[c], errors="coerce").fillna(0).astype(int)
    dong = []
    if db.mt:
        thieu = max(int(db.mt) - int(db.du_bao), 0)
        dong.append(f"- {ten}: dự báo {_so(db.du_bao)}/{_so(db.mt)} = {int(db.pct_mt)}% mục tiêu"
                    + (f", THIẾU {_so(thieu)} online. Cần {_so(db.can_moi_ngay or 0)}/ngày, đang "
                       f"{str(db.tb_ngay).replace('.', ',')}/ngày."
                       if thieu else ", dự báo đạt."))
    ss = so_voi_thang_truoc(thang, d.day, [code])
    if ss:
        dong.append(ss)
    if len(nv):
        tb = round(float(nv.online.mean()), 1)
        dong.append(f"- {len(nv)} nhân sự, bình quân {tb} online/người. Cao nhất: " + ", ".join(
            f"{r.ho_ten} {r.online}" for r in nv.nlargest(3, "online").itertuples()) + ". Thấp nhất: " + ", ".join(
            f"{r.ho_ten} {r.online}" for r in nv.nsmallest(3, "online").itertuples()) + ".")
        top3 = int(nv.nlargest(3, "online").online.sum())
        if nv.online.sum():
            dong.append(f"- Mức phụ thuộc: 3 người đứng đầu làm {round(top3 / nv.online.sum() * 100)}% số online "
                        "của phòng.")
        chenh = (nv.online - nv.ck_online)
        giam = nv.assign(ch=chenh).nsmallest(3, "ch")
        giam = giam[giam.ch < 0]
        if len(giam):
            dong.append("- Giảm nhiều nhất so cùng kỳ: " + ", ".join(f"{r.ho_ten} {r.ch:+d}"
                                                                          for r in giam.itertuples()) + ".")
        khong_so = nv[(nv.ngay_lien_chua_co_so >= 7) & (nv.khong_xet.fillna("") == "")]
        if len(khong_so):
            dong.append(f"- {len(khong_so)} người từ 7 ngày liền chưa có số: "
                        + ", ".join(f"{r.ho_ten} ({r.ngay_lien_chua_co_so} ngày)" for r in khong_so.head(5).itertuples())
                        + ".")
        ton = nv[nv.ton_qua_7 > 0].nlargest(3, "ton_qua_7")
        if len(ton):
            dong.append(f"- Hợp đồng chờ lâu: {int(nv.ton_qua_7.sum())} hợp đồng đã chờ quá 7 ngày, nhiều nhất ở "
                        + ", ".join(f"{r.ho_ten} {r.ton_qua_7}" for r in ton.itertuples()) + ".")
        # 7 ngày ĐÃ CHỐT theo acc (bảng nhân sự tính cả ngày đang cập nhật)
        c = ngay_chot_7(d)
        tuan = pd.Timedelta(days=7)
        nay = tong_theo_acc((c - pd.Timedelta(days=6)).isoformat(), c.isoformat()).groupby("acc_norm").n.sum()
        truoc = tong_theo_acc((c - tuan - pd.Timedelta(days=6)).isoformat(), (c - tuan).isoformat()
                              ).groupby("acc_norm").n.sum()
        nv["tuan_chot"] = nay.reindex(nv.acc_norm).fillna(0).astype(int).to_numpy()
        nv["tuan_chot_truoc"] = truoc.reindex(nv.acc_norm).fillna(0).astype(int).to_numpy()
        nv["ch7"] = nv.tuan_chot - nv.tuan_chot_truoc
        cham = nv[nv.ch7 <= -3].nsmallest(3, "ch7")
        dong.append(f"- 7 ngày đã chốt ({(c - pd.Timedelta(days=6)):%d/%m}-{c:%d/%m}): phòng {int(nv.tuan_chot.sum())} "
                    f"online so với {int(nv.tuan_chot_truoc.sum())} 7 ngày trước đó"
                    + ("; chững lại rõ nhất: " + ", ".join(f"{r.ho_ten} {r.tuan_chot_truoc}→{r.tuan_chot}"
                                                             for r in cham.itertuples()) if len(cham) else "") + ".")
    return "TÍN HIỆU CHÍNH (app đã tính sẵn - ưu tiên dùng):\n" + "\n".join(dong)


def loi_du_bao(db) -> str:
    """Giải thích hai cột dự báo cho AI bằng lời thường (không dùng chữ 'hệ số')."""
    t = db.attrs.get("tuan") or {}
    return (f"DỰ BÁO CUỐI THÁNG (luỹ kế từ 01). Cột 'Dự báo cuối tháng' = luỹ kế + phần còn lại tính theo "
            f"đúng nhịp tháng trước (tháng trước phần cuối tháng bán nhanh hơn phần đầu tháng "
            f"{str(db.attrs['he_so']).replace('.', ',')} lần). Cột 'Nếu chỉ giữ nhịp 7 ngày gần nhất' = kịch "
            f"bản không bứt tốc, lấy bình quân {str(t.get('tb', 0)).replace('.', ',')} online/ngày của ngày "
            f"{t.get('tu', 0):02d}-{t.get('den', 0):02d} nhân số ngày còn lại. Chênh giữa hai cột là phần "
            "đang trông vào nhịp bứt cuối tháng:")


def _du_lieu_tong(user, d: date, thang: str, cn: str, tu: str, scope) -> str:
    db = du_bao_thang(thang, d.day, scope)
    return (f"{fi.boi_canh_chung(user, d, scope)}\n\n{tin_hieu_tong(d, thang, cn, tu, scope)}\n\n"
            f"{_bang_tong(d, thang, cn, tu, scope)}\n\n"
            f"{loi_du_bao(db)}\n{csv(db, COT_DU_BAO)}")


YEU_CAU_TONG = ("LĂNG KÍNH BÁO CÁO TỔNG - KẾT QUẢ & TIẾN ĐỘ cho Ban giám đốc: tháng này có kịp mục tiêu không (đặt "
                "cạnh nhịp tháng trước), rủi ro nằm ở bầy / phòng nào và vì sao (thiếu người, năng suất thấp, hợp "
                "đồng chờ lâu, triển khai chậm...), BGĐ cần điều phối gì trong tuần này. Chất lượng bán và nhân sự "
                "chỉ nhắc khi chúng là nguyên nhân của rủi ro.")
YEU_CAU_ANH = ("Viết nhận xét RẤT NGẮN để in dưới ảnh báo cáo gửi nhóm Zalo: đúng 3 gạch đầu dòng bắt đầu "
               "bằng '- ', mỗi dòng tối đa 25 từ, có số cụ thể, không tiêu đề, không in đậm, không mục "
               "Việc nên làm.")


def ngu_canh_phong(user, den: str | None, code: str) -> tuple[str, Callable[[], str]]:
    _chan_nhan_su(user, code)
    d = _ngay_hop_le(den)
    return f"{d}|{code}|{_quyen_ns(user)}", lambda: _du_lieu_phong(user, d, code)


def _du_lieu_phong(user, d: date, code: str) -> str:
    thang = f"{d.year}-{d.month:02d}"
    ss, _ = bp.so_sanh_phong(thang, d.day, code)
    nv = _nhan_su_phong(thang, d.day, code)
    db = du_bao_thang(thang, d.day, [code])
    ss = ss.assign(vi_tri=[f"{h}/{n}" if h else "" for h, n in zip(ss.hang, ss.so_phong)])
    rieng = fi.nhan_su_yeu(user, d, [code]) + fi.phong_lam_tut(*fi._hai_ky(d, [code])[:2], thang)
    return (f"{fi.boi_canh_chung(user, d, user.phong_duoc_xem(), nhan_su=False)}\n\n{tin_hieu_phong(d, code)}\n"
            + "\n".join(rieng) + "\n\n"
            f"Phòng {bp.ten_phong(code)} · luỹ kế 01 đến {d:%d/%m/%Y}. {dong_thoi_gian(d)}\n"
               "VỊ TRÍ SO VỚI CÁC PHÒNG KINH DOANH (mức chung: tỷ lệ là toàn chi nhánh, số lượng là "
               f"bình quân một phòng):\n"
               f"{csv(ss, {'chi_so': 'Chỉ số', 'gia_tri': 'Phòng', 'muc_chung': 'Mức chung', 'vi_tri': 'Hạng'})}\n\n"
               f"DỰ BÁO CUỐI THÁNG:\n{csv(db[db.phong_code == code], COT_DU_BAO)}\n\n"
               f"NHÂN SỰ (dòng cuối là tổng phòng):\n{csv(nv, COT_NV)}")


YEU_CAU_PHONG = ("LĂNG KÍNH BÁO CÁO PHÒNG - CON NGƯỜI cho trưởng phòng: phòng có kịp mục tiêu không (đặt cạnh nhịp "
                 "tháng trước và mặt bằng các phòng), phòng đang hụt vì AI (sale số thấp hẳn so mặt bằng, người chững "
                 "lại 7 ngày gần, người lâu không có số, phụ thuộc vào vài người, bán nhiều nhưng ít bán kèm), và "
                 "trưởng phòng cần kèm ai, giao việc gì - tối đa 3 người, ghi rõ phòng thêm được bao nhiêu nếu làm "
                 "được.")


def ngu_canh_phan_tich(user, den: str | None, chi_nhanh: str | None,
                       tu: str | None = None) -> tuple[str, Callable[[], str]]:
    """`tu` trống hoặc là ngày 01 = luỹ kế tháng; khác = khoảng tự chọn (so với khoảng liền trước cùng số ngày)."""
    d = _ngay_hop_le(den)
    cn = chi_nhanh or "all"
    d_tu = _ngay_hop_le(tu) if tu else d.replace(day=1)
    if d_tu > d:
        d_tu = d.replace(day=1)
    scope = loc_chi_nhanh(user.phong_duoc_xem(), cn, f"{d.year}-{d.month:02d}")
    return (f"{d_tu}|{d}|{cn}|{scope}|{_quyen_ns(user)}",
            lambda: _du_lieu_phan_tich(user, d, cn, scope, d_tu))


def _du_lieu_phan_tich(user, d: date, cn: str, scope, d_tu: date | None = None) -> str:
    thang, ngay = f"{d.year}-{d.month:02d}", d.day
    d_tu = d_tu or d.replace(day=1)
    luy_ke = d_tu == d.replace(day=1)
    df = pt.hop_dong_online(d_tu.isoformat(), d.isoformat(), scope)
    if luy_ke:
        tu_t, den_t = pt.cung_ky_thang_truoc(thang, ngay)
        ten_ck = f"cùng kỳ {tu_t[8:]}-{den_t[8:]}/{den_t[5:7]}"
    else:
        e = d_tu - timedelta(days=1)
        tu_t, den_t = (e - timedelta(days=(d - d_tu).days)).isoformat(), e.isoformat()
        ten_ck = f"kỳ trước {tu_t[8:]}/{tu_t[5:7]}-{den_t[8:]}/{den_t[5:7]}"
    ton = pt.hop_dong_ton(scope)
    chung = pd.DataFrame([{"ky": f"{d_tu:%d/%m}-{d:%d/%m}", **pt.chi_so_chung(df)},
                          {"ky": ten_ck, **pt.chi_so_chung(pt.hop_dong_online(tu_t, den_t, scope))}])
    ty_le = {"kem_vvip": "%kèm V.VIP", "kem_camera": "%kèm Camera", "du_3": "%đủ 3 DV",
             "tra_truoc": "%trả trước", "onl_1_ngay": "%online trong 1 ngày", "ngoai_tinh": "%bán ngoại tỉnh"}
    bang = pt.bang_theo_phong(df, ton, thang)
    tuoi = pt.ton_theo_tuoi(ton, thang)
    if len(tuoi):
        tuoi = tuoi.rename(columns={f"m{i}": m[2] for i, m in enumerate(pt.MOC_TON)})
    db = du_bao_thang(thang, ngay, scope)
    return (f"{fi.boi_canh_chung(user, d, scope)}\n\n{fi.tin_hieu_phan_tich(user, d, scope)}\n\n"
            f"Phạm vi {TEN_PHAM_VI.get(cn, cn)} · "
            + (f"luỹ kế 01 đến {d:%d/%m/%Y}" if luy_ke else f"khoảng {d_tu:%d/%m/%Y} - {d:%d/%m/%Y}")
            + ". Tỷ lệ tính trên số online. "
            f"{dong_thoi_gian(d)}\n"
               f"CHỈ SỐ CHUNG:\n{csv(chung, {'ky': 'Kỳ', 'online': 'Online', **ty_le})}\n\n"
               f"THEO PHÒNG:\n{csv(bang, {'phong': 'Phòng', 'online': 'Online', **ty_le, 'ton': 'Tồn', 'ton_qua_7': 'Chờ quá 7 ngày'})}\n\n"
               f"SỐ TỒN THEO THỜI GIAN CHỜ:\n{csv(tuoi, {'phong': 'Phòng', 'tong': 'Tổng', **{m[2]: m[2] for m in pt.MOC_TON}})}\n\n"
               f"BÁN KÈM THEO NHÓM GÓI:\n{csv(pt.kem_theo_goi(df), {'nhom_goi': 'Nhóm gói', 'so_hd': 'Số HĐ', 'vvip': '%V.VIP', 'camera': '%Camera', 'du_3': '%đủ 3'})}\n\n"
               f"DỰ BÁO CUỐI THÁNG (tổng):\n{csv(db[db.phong_code == 'TOTAL'], COT_DU_BAO)}")


YEU_CAU_PHAN_TICH = ("LĂNG KÍNH PHÂN TÍCH BÁN HÀNG - CHẤT LƯỢNG & VẬN HÀNH: chất lượng bán (bán kèm, trả trước, "
                     "cơ cấu gói) đang tốt lên hay xấu đi và vì sao; tốc độ triển khai (online trong 1 ngày) chậm ở "
                     "khu vực kỹ thuật nào; phòng / sale nào làm tụt chất lượng hoặc làm phòng chững lại; hợp đồng "
                     "chờ lâu. Việc cần làm phải giao đúng vai: kỹ thuật khu vực (triển khai nhanh hơn), trưởng phòng "
                     "và sale (bán kèm, kèm sale yếu), BGĐ (điều phối). Không chỉ nói về số tồn.")


# ------------------------------------------------------------------ công cụ chatbot
def _cong_cu(ten, mo_ta, **tham_so):
    bat_buoc = [k for k, v in tham_so.items() if not v.pop("tuy_chon", False)]
    return {"type": "function", "function": {"name": ten, "description": mo_ta, "parameters": {
        "type": "object", "properties": tham_so, "required": bat_buoc}}}


def _ngay(mo_ta):
    return {"type": "string", "description": mo_ta + " (YYYY-MM-DD)"}


def cong_cu(user) -> list[dict]:
    ds = [
        _cong_cu("bao_cao_tong", "Kết quả theo phòng trong một khoảng ngày (như Báo cáo Tổng): nhân sự, mục "
                 "tiêu, online, cùng kỳ tháng trước, tăng trưởng, tồn, V.VIP, FPT Play, Camera; có dòng tổng bầy "
                 "và tổng chi nhánh. Muốn so hai kỳ thì gọi hai lần. Hỏi vài phòng thì truyền 'phong' cho gọn.",
                 tu=_ngay("Từ ngày"), den=_ngay("Đến ngày"),
                 chi_nhanh={"type": "string", "enum": ["all", "DNG", "QNM"], "tuy_chon": True},
                 phong={"type": "string", "description": "Mã phòng cách nhau dấu phẩy; bỏ trống = mọi phòng",
                        "tuy_chon": True}),
        _cong_cu("chat_luong_ban", "Chất lượng bán luỹ kế từ 01 đến ngày (như trang Phân tích): tỷ lệ kèm V.VIP, "
                 "Camera, đủ 3 dịch vụ, trả trước, online trong 1 ngày so cùng kỳ; theo phòng; số tồn theo thời "
                 "gian chờ; bán kèm theo nhóm gói.", den=_ngay("Ngày luỹ kế đến"),
                 chi_nhanh={"type": "string", "enum": ["all", "DNG", "QNM"], "tuy_chon": True}),
        _cong_cu("so_theo_ngay", "Số từng ngày trong một tháng, theo phòng (hoặc một phòng).",
                 thang={"type": "string", "description": "YYYY-MM"},
                 chi_so={"type": "string", "enum": list(TEN_CHI_SO)},
                 phong={"type": "string", "description": "Mã phòng, bỏ trống = mọi phòng", "tuy_chon": True}),
        _cong_cu("chan_doan_phong", "Tìm VÌ SAO một phòng (hoặc cả phạm vi) tăng/giảm: online từng ngày 14 ngày "
                 "gần nhất, ngày thấp bất thường, 7 ngày gần so 7 ngày trước; nếu người hỏi được xem nhân sự thì "
                 "kèm nhân sự tăng / giảm nhiều nhất so cùng kỳ và so 7 ngày trước.",
                 den=_ngay("Ngày luỹ kế đến"),
                 phong={"type": "string", "description": "Mã phòng; bỏ trống = cả phạm vi được xem", "tuy_chon": True}),
        _cong_cu("du_bao_cuoi_thang", "Dự báo online cuối tháng của từng phòng so với mục tiêu tháng "
                 "(công thức của hệ thống).", den=_ngay("Ngày luỹ kế đến"),
                 chi_nhanh={"type": "string", "enum": ["all", "DNG", "QNM"], "tuy_chon": True}),
    ]
    if user.duoc_xem_nhan_su:
        ds += [
            _cong_cu("nhan_su_phong", "Từng nhân sự của một phòng, luỹ kế từ 01 đến ngày: online, cùng kỳ, "
                     "V.VIP, Camera, tồn, số ngày liền chưa có số, NSLĐ, cần chú ý.",
                     phong={"type": "string", "description": "Mã phòng"}, den=_ngay("Ngày luỹ kế đến")),
            _cong_cu("nhan_su_ca_nhan", "Toàn bộ số của MỘT nhân sự (theo acc hoặc họ tên) luỹ kế từ 01 đến "
                     "ngày: online, cùng kỳ, V.VIP, Camera, tồn, số ngày liền chưa có số, NSLĐ, và vị trí của "
                     "người đó trong phòng. Dùng khi câu hỏi nhắc tới một người cụ thể - KHÔNG truyền acc nhân "
                     "sự vào tham số 'phong' của công cụ khác.",
                     nguoi={"type": "string", "description": "Acc (VD DNG.Huyta5) hoặc họ tên nhân sự"},
                     den=_ngay("Ngày luỹ kế đến")),
            _cong_cu("nsld", "NSLĐ (điểm ITN bình quân) theo phòng từng tháng và tân binh (tỷ lệ nghỉ, ITN "
                     "theo tháng làm việc). Có mã phòng thì kèm từng nhân sự của phòng đó.",
                     nam={"type": "integer"}, den_thang={"type": "integer", "description": "1-12"},
                     phong={"type": "string", "description": "Mã phòng (tuỳ chọn)", "tuy_chon": True}),
        ]
    return ds


def chan_doan(user, den: str | None, code: str | None) -> str:
    """Số để trả lời 'vì sao': nhịp từng ngày, ngày thấp bất thường, nhân sự tăng / giảm nhiều nhất (nếu có quyền)."""
    d = _ngay_hop_le(den)
    thang = f"{d.year}-{d.month:02d}"
    pv = user.phong_duoc_xem()
    if code and pv is not None and code not in pv:
        raise LoiAI("Bạn không được xem phòng này.")
    bang = daily_counts(thang, "online")
    giu = [code] if code else [c for c in bang.index if pv is None or c in pv]
    ngay = bang.loc[giu, :d.day].sum()
    tb = float(ngay.mean()) if len(ngay) else 0
    tu14 = max(1, d.day - 13)
    thap = [f"{n:02d}/{d.month:02d} ({int(ngay[n])})" for n in ngay.index if tb and ngay[n] < 0.5 * tb and n < d.day]
    ten_pv = bp.ten_phong(code) if code else "cả phạm vi được xem"
    kq = [f"CHẨN ĐOÁN {ten_pv} · luỹ kế 01-{d:%d/%m}. Bình quân {tb:.1f} online/ngày. {dong_thoi_gian(d)}",
          "Online từng ngày (14 ngày gần nhất): " + ", ".join(f"{n:02d}/{d.month:02d}={int(ngay[n])}"
                                                              for n in range(tu14, d.day + 1)),
          "Ngày thấp bất thường (dưới 50% bình quân, trừ ngày cuối đang có thể tạm tính): "
          + (", ".join(thap) if thap else "không có")]
    if not code:
        return "\n".join(kq)
    if not user.duoc_xem_nhan_su or (user.phong_nhan_su() is not None and code not in user.phong_nhan_su()):
        return "\n".join(kq + ["(Người hỏi không được xem chi tiết nhân sự nên không có phần nhân sự.)"])
    nv = bp.bang_nhan_su(thang, d.day, code)
    nv = nv[(nv.loai_dong == "data") & (nv.khong_xet != "Trưởng phòng")].copy()   # TP không xếp hạng
    for c in ("online", "ck_online", "chenh_ck", "tuan_nay", "tuan_truoc"):
        nv[c] = pd.to_numeric(nv[c]).fillna(0).astype(int)
    nv["chenh_tuan"] = nv.tuan_nay - nv.tuan_truoc
    cot = {"ho_ten": "Họ tên", "online": "Online", "ck_online": "Cùng kỳ", "chenh_ck": "Chênh cùng kỳ",
           "tuan_nay": "7 ngày gần", "tuan_truoc": "7 ngày trước", "ngay_lien_chua_co_so": "Ngày liền chưa có số"}
    kq += [f"Nhân sự tăng nhiều nhất so cùng kỳ:\n{csv(nv.nlargest(3, 'chenh_ck'), cot)}",
           f"Nhân sự giảm nhiều nhất so cùng kỳ:\n{csv(nv.nsmallest(3, 'chenh_ck'), cot)}",
           f"Nhân sự chậm lại nhiều nhất 7 ngày gần so 7 ngày trước:\n{csv(nv.nsmallest(3, 'chenh_tuan'), cot)}"]
    return "\n\n".join(kq)


def tim_nhan_su(user, nguoi: str, d: date) -> str:
    """acc_norm của nhân sự khớp acc hoặc họ tên, trong phạm vi người hỏi được xem nhân sự.
    Khớp nhiều người thì liệt kê để AI hỏi lại, không tự chọn bừa."""
    from app.ingest.commit import _bo_dau
    _chan_nhan_su(user)
    gon = _bo_dau(str(nguoi or "").strip()).lower()
    if not gon:
        raise LoiAI("Chưa nói rõ tên hoặc acc của nhân sự cần xem.")
    df = fi._hieu_suat(f"{d.year}-{d.month:02d}", user.phong_nhan_su(), d.day)
    if df.empty:
        raise LoiAI("Chưa có dữ liệu nhân sự của tháng này.")
    acc = df.acc.fillna("").map(lambda x: _bo_dau(str(x)).lower())
    ho_ten = df.ho_ten.fillna("").map(lambda x: _bo_dau(str(x)).lower())
    hop = df[(acc == gon) | (ho_ten == gon)]
    if hop.empty:
        hop = df[acc.str.contains(gon, regex=False) | ho_ten.str.contains(gon, regex=False)]
    if hop.empty:
        raise LoiAI(f"Không có nhân sự nào tên hoặc acc giống '{nguoi}' trong phạm vi được xem.")
    if len(hop) > 1:
        raise LoiAI(f"Có {len(hop)} người khớp '{nguoi}': "
                    + ", ".join(f"{r.ho_ten} ({r.acc}, {r.phong})" for r in hop.head(6).itertuples())
                    + ". Gọi lại với acc chính xác.")
    return str(hop.iloc[0].acc_norm)


def nhan_su_ca_nhan(user, nguoi: str, den: str | None) -> str:
    """Toàn bộ số của một nhân sự + vị trí của họ trong phòng (để nói được 'cao hay thấp so với ai')."""
    d = _ngay_hop_le(den)
    thang = f"{d.year}-{d.month:02d}"
    acc_norm = tim_nhan_su(user, nguoi, d)
    code = str(fi._hieu_suat(thang, user.phong_nhan_su(), d.day).set_index("acc_norm").at[acc_norm, "phong_code"])
    _chan_nhan_su(user, code)
    nv = _nhan_su_phong(thang, d.day, code)
    dong = nv[nv.acc_norm == acc_norm]
    if dong.empty:
        raise LoiAI("Nhân sự này chưa có dòng số liệu trong tháng đang xem.")
    r = dong.iloc[0]
    ds = nv[nv.loai_dong == "data"].copy()
    ds["online"] = pd.to_numeric(ds.online, errors="coerce").fillna(0)
    so = float(pd.to_numeric(r.online, errors="coerce") or 0)
    kq = [f"NHÂN SỰ {r.ho_ten} ({r.acc}) · phòng {bp.ten_phong(code)} · luỹ kế 01-{d:%d/%m/%Y}. "
          f"{dong_thoi_gian(d)}", csv(dong, COT_NV),
          f"Vị trí trong phòng: đứng thứ {int((ds.online > so).sum()) + 1}/{len(ds)} về online; trung vị phòng "
          f"{int(ds.online.median())}, bình quân {str(round(float(ds.online.mean()), 1)).replace('.', ',')} online/người.",
          f"TỔNG PHÒNG để so sánh:\n{csv(nv[nv.loai_dong == 'total'], COT_NV)}"]
    if str(r.khong_xet or ""):
        kq.append(f"Lưu ý: người này là {r.khong_xet} nên không vào xếp hạng cá nhân.")
    return "\n".join(kq)


def chay_cong_cu(user, ten: str, ts: dict) -> str:
    if ten == "bao_cao_tong":
        d = _ngay_hop_le(ts.get("den"))
        thang, cn = f"{d.year}-{d.month:02d}", ts.get("chi_nhanh") or "all"
        tu = str(ts.get("tu") or "")[:10]
        tu = tu if tu and tu <= d.isoformat() else d.replace(day=1).isoformat()
        chi = {_ma_phong(x) for x in str(ts.get("phong") or "").split(",") if x.strip()}
        return _bang_tong(d, thang, cn, tu, loc_chi_nhanh(user.phong_duoc_xem(), cn, thang), chi or None)
    if ten == "chan_doan_phong":
        return chan_doan(user, ts.get("den"), _ma_phong(ts.get("phong")))
    if ten == "chat_luong_ban":
        return ngu_canh_phan_tich(user, ts.get("den"), ts.get("chi_nhanh"))[1]()
    if ten == "du_bao_cuoi_thang":
        d = _ngay_hop_le(ts.get("den"))
        thang = f"{d.year}-{d.month:02d}"
        db = du_bao_thang(thang, d.day, loc_chi_nhanh(user.phong_duoc_xem(), ts.get("chi_nhanh"), thang))
        return (f"Luỹ kế 01-{d:%d/%m/%Y}, tháng có {db.attrs['so_ngay']} ngày. {loi_du_bao(db)}\n"
                f"{csv(db, COT_DU_BAO)}")
    if ten == "so_theo_ngay":
        thang, chi_so = str(ts.get("thang", ""))[:7], ts.get("chi_so", "online")
        if chi_so not in METRICS:
            raise LoiAI("Chỉ số không hợp lệ.")
        month_range(thang)
        bang = daily_counts(thang, chi_so)
        pv = user.phong_duoc_xem()
        code = _ma_phong(ts.get("phong"))
        giu = [c for c in bang.index if (pv is None or c in pv) and (code is None or c == code)]
        ten_p = {p["code"]: p["ten"] for p in phong_order(thang)}
        co_so = bang.columns[bang.sum().to_numpy() > 0]
        bang = bang.loc[giu, :(co_so.max() if len(co_so) else bang.columns[0])]
        out = bang.rename(index=ten_p)
        out.loc["TỔNG"] = out.sum()
        return f"{TEN_CHI_SO[chi_so]} từng ngày tháng {thang} (cột = ngày):\n" + out.to_csv().strip()
    if ten == "nhan_su_ca_nhan":
        return nhan_su_ca_nhan(user, str(ts.get("nguoi") or ""), ts.get("den"))
    if ten == "nhan_su_phong":
        code = _ma_phong(ts.get("phong"))
        return ngu_canh_phong(user, ts.get("den"), code)[1]()
    if ten == "nsld":
        _chan_nhan_su(user)
        nam, den = int(ts.get("nam")), int(ts.get("den_thang"))
        den = nsld.thang_nsld_den(nam, den)
        if not den:
            return f"Chưa có file NSLĐ nào của năm {nam}."
        df = nsld.du_lieu(nam, den)
        thang = {f"t{i}": f"T{i}" for i in range(1, den + 1)}
        kq = (f"NSLĐ theo phòng năm {nam} (đã có đến T{den}):\n"
              f"{csv(nsld.nsld_theo_phong(df, den), {'phong': 'Phòng', **thang, 'tb': 'TB', 'so_nguoi': 'Số người xét'})}\n\n"
              f"Tân binh theo phòng (k = tháng làm việc thứ k):\n"
              f"{csv(nsld.tan_binh_theo_phong(df, nam, den), {'phong': 'Phòng', 'so_moi': 'Tân binh', 'da_nghi': 'Đã nghỉ', 'ty_le_out': '%nghỉ', **{f'k{i}': f'Tháng {i}' for i in range(1, den + 1)}, 'tb': 'TB'})}")
        code = _ma_phong(ts.get("phong"))
        if code:
            _chan_nhan_su(user, code)
            nv = nsld.nsld_nhan_su(df[df.phong_code == code], den)
            kq += (f"\n\nNSLĐ từng nhân sự phòng {code}:\n"
                   f"{csv(nv, {'ho_ten': 'Họ tên', 'acc': 'Acc', 'vi_tri': 'Vị trí', **thang, 'tb': 'TB', 'trang_thai': 'Trạng thái'})}")
        return kq
    raise LoiAI(f"Không có công cụ {ten}.")


QUY_TAC_CHAT = (
    "\n\nCÁCH TRẢ LỜI CHAT (bắt buộc):\n"
    "1. NGẮN, ĐÚNG TRỌNG TÂM, CÓ INSIGHT. Bảng chi tiết người dùng đã xem trên trang; chat trả lời điều được hỏi "
    "và nói con số đó có ý nghĩa gì:\n"
    "   - Khoảng 80 từ: 1-3 câu hoặc tối đa 3 gạch đầu dòng.\n"
    "   - Cấu trúc: số chính (1-2 số) -> ý nghĩa (tiến độ so thời gian, xu hướng 7 ngày, quy mô/đóng góp, kịp mục "
    "tiêu không) -> CHỈ KHI CÓ RỦI RO RÕ (dự báo 'Rủi ro', chậm tiến độ từ 10 điểm, giảm đáng kể, tồn lâu nhiều) "
    "thêm 1 câu gợi ý hành động cụ thể gắn với số. Không rủi ro thì không gợi ý.\n"
    "   - Câu hỏi chung chung về kết quả: số online, % tăng trưởng so cùng kỳ và 1 ý nghĩa quan trọng nhất.\n"
    "   - KHÔNG liệt kê thêm nhân sự, số tồn, V.VIP, Camera, FPT Play... nếu không giúp trả lời câu hỏi.\n"
    "   - Chỉ trả lời dài, liệt kê đủ số khi người dùng yêu cầu rõ ('chi tiết', 'liệt kê', 'đầy đủ', 'tất cả').\n"
    "   - Câu 'phòng nào/bầy nào/ai ... nhất': tối đa 3 đơn vị mỗi chiều, kèm số và ý nghĩa ngắn.\n"
    "   - Câu 'vì sao/tại sao/do đâu': gọi công cụ chan_doan_phong rồi nêu 1-2 nguyên nhân có số.\n"
    "   - Câu về nhân sự ('ai cần quan tâm', 'nhân sự nào yếu'...): nêu tối đa 3 người đáng lo nhất, mỗi người 1 lý "
    "do ngắn và 1 việc nên làm; KHÔNG chia thành nhiều nhóm / nhiều danh sách.\n"
    "   - Dùng phần BỐI CẢNH THÁNG để giải thích ý nghĩa (VD tăng nhưng vẫn chậm hơn nhịp tháng trước), không chép "
    "lại bối cảnh nếu câu hỏi không cần.\n"
    "2. HỎI TIẾP NGẮN (VD 'các phòng IBB á', 'còn IBB5?', 'tháng trước thì sao?') là giữ nguyên câu hỏi trước "
    "và chỉ đổi điều kiện đó rồi trả lời lại theo đúng ý câu hỏi trước.\n"
    "3. NHÓM PHÒNG: dùng cột 'loại' trong danh sách phòng (IBB, DIABAN = địa bàn, KT, CUS, ECOM, KHAC). "
    "'Phòng kinh doanh' = IBB + DIABAN. Chỉ xét đúng các phòng thuộc nhóm được hỏi; truyền mã các phòng đó vào "
    "tham số 'phong' của công cụ.\n"
    "4. KHÔNG GÁN NHẦM SỐ TỔNG: dòng 'TỔNG TOÀN CHI NHÁNH' là toàn chi nhánh, dòng 'BẦY ...'/'TỔNG ...' là tổng "
    "bầy, không phải tổng của một nhóm phòng tự chọn. Cần tổng một nhóm thì tự cộng các dòng phòng và ghi rõ là tự "
    "cộng; không chắc thì không nêu.\n"
    "5. SỐ LIỆU: câu có số thì LUÔN lấy qua công cụ, không dùng số nhớ trong hội thoại nếu khác kỳ/phạm vi, không "
    "trả lời bằng hiểu biết chung. Ưu tiên cột tính sẵn; tự tính thì ghi phép tính.\n"
    "5b. KHI CÔNG CỤ BÁO LỖI: đọc câu lỗi, SỬA THAM SỐ rồi gọi lại (VD truyền nhầm acc nhân sự vào ô 'phong' "
    "thì gọi nhan_su_ca_nhan; sai mã phòng thì lấy mã trong danh sách phòng). Chỉ sau khi đã thử lại mà vẫn "
    "không có số thì mới trả lời, và nói bằng lời thường ('chưa tra được số của ... trong kỳ này'), TUYỆT ĐỐI "
    "không in chữ 'LỖI' hay câu lỗi kỹ thuật cho người đọc. Lỗi về quyền thì nói người hỏi không có quyền xem.\n"
    "5c. Câu hỏi nhắc tới MỘT người (có acc kiểu DNG.Abc123 hoặc họ tên): gọi nhan_su_ca_nhan, không gọi "
    "nhan_su_phong rồi tự dò.\n"
    "6. Mở đầu gọn bằng kỳ trong ngoặc (VD '(01-16/09)'), không nhắc lại câu hỏi. Chỉ trả lời về số bán, dự "
    "báo, NSLĐ/tân binh; ngoài phạm vi thì từ chối lịch sự.\n"
    "7. Câu 'phòng nào/bầy nào' xét MỌI phòng/bầy trong phạm vi được xem, không thu hẹp về phòng đang chọn trên "
    "trang; chỉ giới hạn khi câu hỏi nói 'phòng này', 'phòng mình' hoặc nêu tên.\n"
    "8. Gọi ít công cụ nhất có thể.\n"
    "9. KHÔNG tự đặt chỉ tiêu mới, KHÔNG đề xuất 'họp gấp', thêm người, tăng ca hay việc không có trong dữ liệu; "
    "không nói 'số do hệ thống tính, tôi chỉ báo cáo'. Xưng hô theo phần NHÂN VẬT, không xưng 'tôi'.")

# Bộ lọc chung (ky-chung) được nhiều trang cùng ghi: chỉ lấy các ô mà trang đang xem thật sự có,
# tránh VD phòng chọn ở Báo cáo phòng vẫn "dính" khi đang hỏi ở Báo cáo Tổng.
BO_LOC_TRANG = {"/": ("tu", "den", "cn"), "/tracking": ("tu", "den", "cn"), "/sosanh": ("tu", "den", "cn"),
                "/phantich": ("den", "cn"), "/phong": ("den", "phong"), "/hr": ("den", "cn", "phong"),
                "/chatluong": ("tu", "den", "cn")}
TEN_BO_LOC = {"tu": "từ ngày", "den": "đến ngày", "cn": "chi nhánh", "phong": "phòng đang chọn"}


def bo_loc_trang(duong_dan: str | None, ky: dict | None) -> dict:
    return {k: (ky or {}).get(k) for k in BO_LOC_TRANG.get(duong_dan or "/", ()) if (ky or {}).get(k)}


def ngu_canh_chat(user, duong_dan: str | None, ky: dict | None) -> tuple[str, str]:
    """(phần cố định, phần thay đổi). Phần cố định đặt đầu lời nhắn để OpenAI tự lưu đệm (token vào của phần
    đó tính 10% giá); phần thay đổi (ngày, trang, bộ lọc, quyền) đặt sau."""
    from app.overview import trang_thai_ngay
    from app.thoi_gian import gio_viet_nam
    ngays = cac_ngay_co_du_lieu()
    trang = {"/": "Báo cáo Tổng", "/tracking": "Tracking ngày & So sánh", "/sosanh": "Tracking ngày & So sánh",
             "/phantich": "Phân tích bán hàng", "/phong": "Báo cáo phòng", "/hr": "Nhân sự & NSLĐ"}.get(
        duong_dan or "/", duong_dan or "")
    pv, pns = user.phong_duoc_xem(), user.phong_nhan_su()
    phong = "\n".join(f"{p['code']} | {p['ten']} | {p.get('loai') or ''} | bầy {p['bay']} | {p.get('chi_nhanh') or ''}"
                      for p in phong_order() if pv is None or p["code"] in pv)
    quyen = ("được xem chi tiết nhân sự mọi phòng" if pns is None else
             f"chỉ xem chi tiết nhân sự phòng {', '.join(pns)}" if pns else "KHÔNG được xem chi tiết nhân sự")
    moi_nhat = ngays[-1] if ngays else None
    tam_tinh = bool(moi_nhat) and trang_thai_ngay(moi_nhat)[0]
    co_dinh = QUY_TAC_CHAT + f"\n\nDANH SÁCH PHÒNG (mã | tên | loại | bầy | chi nhánh):\n{phong}"
    thay_doi = (f"Hôm nay {gio_viet_nam():%d/%m/%Y}. Số liệu có đến ngày {moi_nhat or '(chưa có)'}"
                + (" (ngày này đang cập nhật, số tạm tính - nói rõ khi dùng)" if tam_tinh else "") + ".\n"
                f"Người hỏi: vai trò {user.role}, {quyen}.\n"
                f"Đang xem trang {trang}; bộ lọc trên trang: "
                + (", ".join(f"{TEN_BO_LOC[k]} {v}" for k, v in bo_loc_trang(duong_dan, ky).items()) or "mặc định")
                + ". Câu hỏi không nói kỳ thì dùng kỳ đang xem (không có thì luỹ kế tháng có số mới nhất) và nói rõ "
                "kỳ đã dùng. Chi nhánh, phòng đang chọn chỉ là ngữ cảnh, không phải giới hạn của câu hỏi.")
    if moi_nhat:
        try:
            d = min(_ngay_hop_le(bo_loc_trang(duong_dan, ky).get("den")), date.fromisoformat(moi_nhat))
            thay_doi += "\n\n" + fi.boi_canh_chung(user, d, pv, nhan_su=False)
        except Exception:        # bối cảnh chỉ để hiểu thêm, lỗi thì vẫn trả lời bằng công cụ
            pass
    return co_dinh, thay_doi
