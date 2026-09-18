"""Số liệu đưa cho trợ lý AI: ngữ cảnh nhận xét từng trang và các công cụ tra số của chatbot.

Mọi hàm đều lọc theo quyền của người đang hỏi, giống hệt giao diện:
- số chung theo phòng: phạm vi `phong_duoc_xem()`;
- chi tiết nhân sự, NSLĐ: chỉ vai trò được xem nhân sự, Trưởng phòng chỉ phòng mình.
Bảng gửi đi dạng CSV cho gọn token. Không có tên khách hàng.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pandas as pd

from app import bao_cao_phong as bp
from app import nsld
from app import phan_tich as pt
from app.du_bao import du_bao_thang
from app.metrics import METRICS, cac_ngay_co_du_lieu, daily_counts, month_range, tong_theo_phong
from app.org import loc_chi_nhanh, phong_order
from app.overview import TEN_PHAM_VI, bang_tong_quan
from app.tro_ly import MAU_NHO_CUNG_KY, LoiAI

COT_TONG = {"phong": "Phòng", "nhan_su": "Nhân sự", "mt_internet": "MT Internet", "online": "Online",
            "htkh_internet": "%HTKH", "ck_online": "Cùng kỳ", "tang_truong": "%Tăng trưởng",
            "so_ton": "Số tồn", "vvip": "V.VIP", "vvip_ty_le": "%VVIP/PTTB", "fpl_combo": "FPT Play",
            "camera": "Camera", "mt_camera": "MT Camera", "htkh_camera": "%HTKH Camera",
            "cnql": "PTTB CNQL", "ngay_online": "Online ngày cuối", "mt_ngay": "MT ngày",
            # tính sẵn cho insight - AI không phải tự làm phép tính
            "chenh_tien_do": "Chênh tiến độ", "chenh_ck": "Chênh cùng kỳ (số)", "dong_gop": "% trong tổng tăng/giảm",
            "mau_nho": "Mẫu nhỏ", "tuan_nay": "7 ngày gần nhất", "tuan_truoc": "7 ngày trước đó",
            "ton_qua_7": "Tồn chờ ≥7 ngày"}
COT_DU_BAO = {"phong": "Phòng", "mt": "MT tháng", "luy_ke": "Luỹ kế", "tb_ngay": "TB/ngày",
              "du_bao": "Dự báo cuối tháng", "pct_mt": "%MT dự báo", "can_moi_ngay": "Cần mỗi ngày",
              "danh_gia": "Đánh giá"}
COT_NV = {"ho_ten": "Họ tên", "acc": "Acc", "hang": "Hạng", "online": "Online", "ck_online": "Cùng kỳ",
          "online_ngay": "Online ngày cuối", "vvip": "V.VIP", "camera": "Camera", "ban_moi": "Bán mới",
          "ton": "Tồn", "ton_qua_7": "Tồn ≥7 ngày", "ngay_lien_chua_co_so": "Ngày liền chưa có số",
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
    raise LoiAI(f"Không có phòng '{phong}'. Dùng mã phòng trong danh sách ngữ cảnh.")


def _chan_nhan_su(user, code: str | None = None) -> None:
    if not user.duoc_xem_nhan_su:
        raise LoiAI("Tài khoản này không được xem chi tiết nhân sự / NSLĐ.")
    pv = user.phong_nhan_su()
    if code and pv is not None and code not in pv:
        raise LoiAI("Bạn chỉ được xem chi tiết nhân sự của phòng mình phụ trách.")


# ------------------------------------------------------------------ nhận xét từng trang
def ngu_canh_tong(user, tu: str | None, den: str | None, chi_nhanh: str | None) -> tuple[str, Callable[[], str]]:
    """(khoá lưu, hàm dựng số liệu) cho Báo cáo Tổng - khoá tính nhanh để tra bản đã lưu trước."""
    d = _ngay_hop_le(den)
    thang, cn = f"{d.year}-{d.month:02d}", chi_nhanh or "all"
    tu = tu[:10] if tu and tu[:10] <= d.isoformat() else d.replace(day=1).isoformat()
    scope = loc_chi_nhanh(user.phong_duoc_xem(), cn, thang)
    return f"{tu}|{d}|{cn}|{scope}", lambda: _du_lieu_tong(d, thang, cn, tu, scope)


def thoi_gian_da_qua(d: date) -> int:
    """% số ngày của tháng đã qua tính đến ngày d."""
    return round(d.day / month_range(f"{d.year}-{d.month:02d}")[2] * 100)


def dong_thoi_gian(d: date) -> str:
    return (f"Tiến độ thời gian: đã qua {d.day}/{month_range(f'{d.year}-{d.month:02d}')[2]} ngày của tháng = "
            f"{thoi_gian_da_qua(d)}% thời gian.")


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
    df["tuan_nay"] = theo_khoang(d - pd.Timedelta(days=6), d)
    df["tuan_truoc"] = theo_khoang(d - tuan - pd.Timedelta(days=6), d - tuan)
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


def _bang_tong(d: date, thang: str, cn: str, tu: str, scope, chi: set[str] | None = None) -> str:
    """Bảng Báo cáo Tổng dạng CSV. `chi`: chỉ lấy các phòng này (kèm dòng tổng) - chat hỏi vài phòng cho gọn token."""
    df, _ = bang_tong_quan(thang, d.day, chi_phong=scope, chi_nhanh=cn, tu=tu)
    df = _them_insight(df, d, tu)
    if chi:
        df = df[df.phong_code.isin(chi) | (df.loai_dong == "total")]
    return (f"Kỳ: {tu} đến {d.isoformat()} · phạm vi {TEN_PHAM_VI.get(cn, cn)}. Cột 'Online ngày cuối' "
            f"và 'MT ngày' là của riêng ngày {d:%d/%m}. {dong_thoi_gian(d)} '7 ngày gần nhất' = "
            f"{(d - pd.Timedelta(days=6)):%d/%m}-{d:%d/%m}.\n"
            f"BẢNG KẾT QUẢ THEO PHÒNG (dòng TỔNG ... là tổng bầy / chi nhánh):\n{csv(df, COT_TONG)}")


def _du_lieu_tong(d: date, thang: str, cn: str, tu: str, scope) -> str:
    db = du_bao_thang(thang, d.day, scope)
    return (f"{_bang_tong(d, thang, cn, tu, scope)}\n\n"
               f"DỰ BÁO CUỐI THÁNG {d.month} (luỹ kế từ 01, hệ số cuối tháng {db.attrs['he_so']}):\n"
               f"{csv(db, COT_DU_BAO)}")


YEU_CAU_TONG = ("Nhận xét Báo cáo Tổng cho Ban giám đốc: toàn chi nhánh có kịp mục tiêu tháng không, phòng / "
                "bầy nào quyết định kết quả (kéo tụt hoặc kéo lên nhiều nhất), và BGĐ nên chỉ đạo gì trong tuần này.")
YEU_CAU_ANH = ("Viết nhận xét RẤT NGẮN để in dưới ảnh báo cáo gửi nhóm Zalo: đúng 3 gạch đầu dòng bắt đầu "
               "bằng '- ', mỗi dòng tối đa 25 từ, có số cụ thể, không tiêu đề, không in đậm, không mục "
               "Việc nên làm.")


def ngu_canh_phong(user, den: str | None, code: str) -> tuple[str, Callable[[], str]]:
    _chan_nhan_su(user, code)
    d = _ngay_hop_le(den)
    return f"{d}|{code}", lambda: _du_lieu_phong(d, code)


def _du_lieu_phong(d: date, code: str) -> str:
    thang = f"{d.year}-{d.month:02d}"
    ss, _ = bp.so_sanh_phong(thang, d.day, code)
    nv = bp.bang_nhan_su(thang, d.day, code)
    db = du_bao_thang(thang, d.day, [code])
    ss = ss.assign(vi_tri=[f"{h}/{n}" if h else "" for h, n in zip(ss.hang, ss.so_phong)])
    return (f"Phòng {bp.ten_phong(code)} · luỹ kế 01 đến {d:%d/%m/%Y}. {dong_thoi_gian(d)}\n"
               "VỊ TRÍ SO VỚI CÁC PHÒNG KINH DOANH (mức chung: tỷ lệ là toàn chi nhánh, số lượng là "
               f"bình quân một phòng):\n"
               f"{csv(ss, {'chi_so': 'Chỉ số', 'gia_tri': 'Phòng', 'muc_chung': 'Mức chung', 'vi_tri': 'Hạng'})}\n\n"
               f"DỰ BÁO CUỐI THÁNG:\n{csv(db[db.phong_code == code], COT_DU_BAO)}\n\n"
               f"NHÂN SỰ (dòng cuối là tổng phòng):\n{csv(nv, COT_NV)}")


YEU_CAU_PHONG = ("Nhận xét cho trưởng phòng: phòng có kịp mục tiêu tháng không và vì sao (nhân sự nào kéo lên / "
                 "kéo xuống, nhịp 7 ngày gần), và trưởng phòng nên làm gì với tối đa 3 nhân sự cần trao đổi "
                 "(dựa cột Cần chú ý, số tồn chờ lâu).")


def ngu_canh_phan_tich(user, den: str | None, chi_nhanh: str | None) -> tuple[str, Callable[[], str]]:
    d = _ngay_hop_le(den)
    cn = chi_nhanh or "all"
    scope = loc_chi_nhanh(user.phong_duoc_xem(), cn, f"{d.year}-{d.month:02d}")
    return f"{d}|{cn}|{scope}", lambda: _du_lieu_phan_tich(d, cn, scope)


def _du_lieu_phan_tich(d: date, cn: str, scope) -> str:
    thang, ngay = f"{d.year}-{d.month:02d}", d.day
    df = pt.hop_dong_online(f"{thang}-01", d.isoformat(), scope)
    tu_t, den_t = pt.cung_ky_thang_truoc(thang, ngay)
    ton = pt.hop_dong_ton(scope)
    chung = pd.DataFrame([{"ky": f"01-{ngay:02d}/{d.month:02d}", **pt.chi_so_chung(df)},
                          {"ky": f"cùng kỳ {tu_t[8:]}-{den_t[8:]}/{den_t[5:7]}",
                           **pt.chi_so_chung(pt.hop_dong_online(tu_t, den_t, scope))}])
    ty_le = {"kem_vvip": "%kèm V.VIP", "kem_camera": "%kèm Camera", "du_3": "%đủ 3 DV",
             "tra_truoc": "%trả trước", "onl_1_ngay": "%online trong 1 ngày", "ngoai_tinh": "%bán ngoại tỉnh"}
    bang = pt.bang_theo_phong(df, ton, thang)
    tuoi = pt.ton_theo_tuoi(ton, thang)
    if len(tuoi):
        tuoi = tuoi.rename(columns={f"m{i}": m[2] for i, m in enumerate(pt.MOC_TON)})
    db = du_bao_thang(thang, ngay, scope)
    return (f"Phạm vi {TEN_PHAM_VI.get(cn, cn)} · luỹ kế 01 đến {d:%d/%m/%Y}. Tỷ lệ tính trên số online. "
            f"{dong_thoi_gian(d)}\n"
               f"CHỈ SỐ CHUNG:\n{csv(chung, {'ky': 'Kỳ', 'online': 'Online', **ty_le})}\n\n"
               f"THEO PHÒNG:\n{csv(bang, {'phong': 'Phòng', 'online': 'Online', **ty_le, 'ton': 'Tồn', 'ton_qua_7': 'Tồn ≥7 ngày'})}\n\n"
               f"SỐ TỒN THEO THỜI GIAN CHỜ:\n{csv(tuoi, {'phong': 'Phòng', 'tong': 'Tổng', **{m[2]: m[2] for m in pt.MOC_TON}})}\n\n"
               f"BÁN KÈM THEO NHÓM GÓI:\n{csv(pt.kem_theo_goi(df), {'nhom_goi': 'Nhóm gói', 'so_hd': 'Số HĐ', 'vvip': '%V.VIP', 'camera': '%Camera', 'du_3': '%đủ 3'})}\n\n"
               f"DỰ BÁO CUỐI THÁNG (tổng):\n{csv(db[db.phong_code == 'TOTAL'], COT_DU_BAO)}")


YEU_CAU_PHAN_TICH = ("Nhận định chất lượng bán: tỷ lệ bán kèm đang tốt lên hay xấu đi so cùng kỳ và phòng nào "
                     "kéo tụt, số tồn chờ lâu cần rà soát - và nên làm gì để cải thiện.")


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
                 "kèm nhân sự kéo tăng/kéo giảm nhiều nhất so cùng kỳ và so 7 ngày trước.",
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
            _cong_cu("nsld", "NSLĐ (điểm ITN bình quân) theo phòng từng tháng và tân binh (tỷ lệ nghỉ, ITN "
                     "theo tháng làm việc). Có mã phòng thì kèm từng nhân sự của phòng đó.",
                     nam={"type": "integer"}, den_thang={"type": "integer", "description": "1-12"},
                     phong={"type": "string", "description": "Mã phòng (tuỳ chọn)", "tuy_chon": True}),
        ]
    return ds


def chan_doan(user, den: str | None, code: str | None) -> str:
    """Số để trả lời 'vì sao': nhịp từng ngày, ngày thấp bất thường, nhân sự kéo tăng/giảm (nếu có quyền)."""
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
    nv = nv[nv.loai_dong == "data"].copy()
    for c in ("online", "ck_online", "chenh_ck", "tuan_nay", "tuan_truoc"):
        nv[c] = pd.to_numeric(nv[c]).fillna(0).astype(int)
    nv["chenh_tuan"] = nv.tuan_nay - nv.tuan_truoc
    cot = {"ho_ten": "Họ tên", "online": "Online", "ck_online": "Cùng kỳ", "chenh_ck": "Chênh cùng kỳ",
           "tuan_nay": "7 ngày gần", "tuan_truoc": "7 ngày trước", "ngay_lien_chua_co_so": "Ngày liền chưa có số"}
    kq += [f"Nhân sự kéo TĂNG nhiều nhất so cùng kỳ:\n{csv(nv.nlargest(3, 'chenh_ck'), cot)}",
           f"Nhân sự kéo GIẢM nhiều nhất so cùng kỳ:\n{csv(nv.nsmallest(3, 'chenh_ck'), cot)}",
           f"Nhân sự chậm lại nhiều nhất 7 ngày gần so 7 ngày trước:\n{csv(nv.nsmallest(3, 'chenh_tuan'), cot)}"]
    return "\n\n".join(kq)


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
        return (f"Luỹ kế 01-{d:%d/%m/%Y}, tháng có {db.attrs['so_ngay']} ngày, hệ số cuối tháng "
                f"{db.attrs['he_so']}.\n{csv(db, COT_DU_BAO)}")
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
    "2. HỎI TIẾP NGẮN (VD 'các phòng IBB á', 'còn IBB5?', 'tháng trước thì sao?') là giữ nguyên câu hỏi trước "
    "và chỉ đổi điều kiện đó rồi trả lời lại theo đúng ý câu hỏi trước.\n"
    "3. NHÓM PHÒNG: dùng cột 'loại' trong danh sách phòng (IBB, DIABAN = địa bàn, KT, CUS, ECOM, KHAC). "
    "'Phòng kinh doanh' = IBB + DIABAN. Chỉ xét đúng các phòng thuộc nhóm được hỏi; truyền mã các phòng đó vào "
    "tham số 'phong' của công cụ.\n"
    "4. KHÔNG GÁN NHẦM SỐ TỔNG: dòng 'TỔNG TOÀN CHI NHÁNH' là toàn chi nhánh, dòng 'BẦY ...'/'TỔNG ...' là tổng "
    "bầy, không phải tổng của một nhóm phòng tự chọn. Cần tổng một nhóm thì tự cộng các dòng phòng và ghi rõ là tự "
    "cộng; không chắc thì không nêu.\n"
    "5. SỐ LIỆU: câu có số thì LUÔN lấy qua công cụ, không dùng số nhớ trong hội thoại nếu khác kỳ/phạm vi, không "
    "trả lời bằng hiểu biết chung. Ưu tiên cột tính sẵn; tự tính thì ghi phép tính. Công cụ báo LỖI hoặc trống "
    "thì nói thẳng; LỖI quyền thì nói người hỏi không có quyền.\n"
    "6. Mở đầu gọn bằng kỳ trong ngoặc (VD '(01-16/09)'), không nhắc lại câu hỏi. Chỉ trả lời về số bán, dự "
    "báo, NSLĐ/tân binh; ngoài phạm vi thì từ chối lịch sự.\n"
    "7. Câu 'phòng nào/bầy nào' xét MỌI phòng/bầy trong phạm vi được xem, không thu hẹp về phòng đang chọn trên "
    "trang; chỉ giới hạn khi câu hỏi nói 'phòng này', 'phòng mình' hoặc nêu tên.\n"
    "8. Gọi ít công cụ nhất có thể.")

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
    return co_dinh, thay_doi
