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
from app.metrics import METRICS, cac_ngay_co_du_lieu, daily_counts, month_range
from app.org import loc_chi_nhanh, phong_order
from app.overview import TEN_PHAM_VI, bang_tong_quan
from app.tro_ly import LoiAI

COT_TONG = {"phong": "Phòng", "nhan_su": "Nhân sự", "mt_internet": "MT Internet", "online": "Online",
            "htkh_internet": "%HTKH", "ck_online": "Cùng kỳ", "tang_truong": "%Tăng trưởng",
            "so_ton": "Số tồn", "vvip": "V.VIP", "vvip_ty_le": "%VVIP/PTTB", "fpl_combo": "FPT Play",
            "camera": "Camera", "mt_camera": "MT Camera", "htkh_camera": "%HTKH Camera",
            "cnql": "PTTB CNQL", "ngay_online": "Online ngày cuối", "mt_ngay": "MT ngày"}
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
    gon = df[co].astype(object).map(lambda v: int(v) if isinstance(v, float) and v.is_integer() else v)
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


def _bang_tong(d: date, thang: str, cn: str, tu: str, scope, chi: set[str] | None = None) -> str:
    """Bảng Báo cáo Tổng dạng CSV. `chi`: chỉ lấy các phòng này (kèm dòng tổng) - chat hỏi vài phòng cho gọn token."""
    df, _ = bang_tong_quan(thang, d.day, chi_phong=scope, chi_nhanh=cn, tu=tu)
    if chi:
        df = df[df.phong_code.isin(chi) | (df.loai_dong == "total")]
    return (f"Kỳ: {tu} đến {d.isoformat()} · phạm vi {TEN_PHAM_VI.get(cn, cn)}. Cột 'Online ngày cuối' "
            f"và 'MT ngày' là của riêng ngày {d:%d/%m}.\n"
            f"BẢNG KẾT QUẢ THEO PHÒNG (dòng TỔNG ... là tổng bầy / chi nhánh):\n{csv(df, COT_TONG)}")


def _du_lieu_tong(d: date, thang: str, cn: str, tu: str, scope) -> str:
    db = du_bao_thang(thang, d.day, scope)
    return (f"{_bang_tong(d, thang, cn, tu, scope)}\n\n"
               f"DỰ BÁO CUỐI THÁNG {d.month} (luỹ kế từ 01, hệ số cuối tháng {db.attrs['he_so']}):\n"
               f"{csv(db, COT_DU_BAO)}")


YEU_CAU_TONG = ("Nhận xét Báo cáo Tổng: tình hình chung so với mục tiêu và cùng kỳ; phòng nổi bật; "
                "phòng rủi ro không đạt mục tiêu tháng theo dự báo; điểm đáng chú ý về V.VIP, Camera, số tồn.")
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
    return (f"Phòng {bp.ten_phong(code)} · luỹ kế 01 đến {d:%d/%m/%Y}.\n"
               "VỊ TRÍ SO VỚI CÁC PHÒNG KINH DOANH (mức chung: tỷ lệ là toàn chi nhánh, số lượng là "
               f"bình quân một phòng):\n"
               f"{csv(ss, {'chi_so': 'Chỉ số', 'gia_tri': 'Phòng', 'muc_chung': 'Mức chung', 'vi_tri': 'Hạng'})}\n\n"
               f"DỰ BÁO CUỐI THÁNG:\n{csv(db[db.phong_code == code], COT_DU_BAO)}\n\n"
               f"NHÂN SỰ (dòng cuối là tổng phòng):\n{csv(nv, COT_NV)}")


YEU_CAU_PHONG = ("Nhận xét cho trưởng phòng: phòng đang ở đâu so với mục tiêu (theo dự báo) và các phòng "
                 "khác; nhân sự nổi bật; nhân sự cần trao đổi ngay / theo dõi và lý do (dựa cột Cần chú ý); "
                 "gợi ý việc cụ thể cho từng người cần chú ý (tối đa 5 người).")


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
    return (f"Phạm vi {TEN_PHAM_VI.get(cn, cn)} · luỹ kế 01 đến {d:%d/%m/%Y}. Tỷ lệ tính trên số online.\n"
               f"CHỈ SỐ CHUNG:\n{csv(chung, {'ky': 'Kỳ', 'online': 'Online', **ty_le})}\n\n"
               f"THEO PHÒNG:\n{csv(bang, {'phong': 'Phòng', 'online': 'Online', **ty_le, 'ton': 'Tồn', 'ton_qua_7': 'Tồn ≥7 ngày'})}\n\n"
               f"SỐ TỒN THEO THỜI GIAN CHỜ:\n{csv(tuoi, {'phong': 'Phòng', 'tong': 'Tổng', **{m[2]: m[2] for m in pt.MOC_TON}})}\n\n"
               f"BÁN KÈM THEO NHÓM GÓI:\n{csv(pt.kem_theo_goi(df), {'nhom_goi': 'Nhóm gói', 'so_hd': 'Số HĐ', 'vvip': '%V.VIP', 'camera': '%Camera', 'du_3': '%đủ 3'})}\n\n"
               f"DỰ BÁO CUỐI THÁNG (tổng):\n{csv(db[db.phong_code == 'TOTAL'], COT_DU_BAO)}")


YEU_CAU_PHAN_TICH = ("Nhận định chất lượng bán: xu hướng tỷ lệ bán kèm so cùng kỳ, nhóm gói, phòng kéo tụt "
                     "tỷ lệ, số tồn chờ lâu cần rà soát, rủi ro mục tiêu tháng theo dự báo.")


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


def chay_cong_cu(user, ten: str, ts: dict) -> str:
    if ten == "bao_cao_tong":
        d = _ngay_hop_le(ts.get("den"))
        thang, cn = f"{d.year}-{d.month:02d}", ts.get("chi_nhanh") or "all"
        tu = str(ts.get("tu") or "")[:10]
        tu = tu if tu and tu <= d.isoformat() else d.replace(day=1).isoformat()
        chi = {_ma_phong(x) for x in str(ts.get("phong") or "").split(",") if x.strip()}
        return _bang_tong(d, thang, cn, tu, loc_chi_nhanh(user.phong_duoc_xem(), cn, thang), chi or None)
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
    "- Câu hỏi có số: LUÔN gọi công cụ lấy số; không dùng lại số trong hội thoại nếu khác kỳ hoặc phạm vi, "
    "không trả lời bằng hiểu biết chung.\n"
    "- Mở đầu bằng kỳ và phạm vi của số (VD: 'Luỹ kế 01-16/09, toàn chi nhánh:').\n"
    "- Ưu tiên số có sẵn trong bảng; chỉ tự cộng/trừ/chia khi bảng chưa có và ghi rõ phép tính.\n"
    "- Không suy đoán nguyên nhân ngoài số liệu; giả thuyết phải ghi 'có thể'.\n"
    "- Công cụ báo LỖI hoặc không có dữ liệu thì nói thẳng, không đoán. LỖI quyền thì nói người hỏi không có quyền.\n"
    "- Chỉ trả lời về số bán, dự báo, NSLĐ/tân binh; câu ngoài phạm vi thì từ chối lịch sự.\n"
    "- Trả lời thẳng câu hỏi, ngắn (tối đa khoảng 150 từ); chỉ thêm 'Việc nên làm' khi câu hỏi cần đánh giá.\n"
    "- Gọi ít công cụ nhất có thể; hỏi vài phòng thì truyền tham số phòng.\n"
    "- Câu hỏi so sánh / xếp hạng ('phòng nào', 'bầy nào', 'ai nhất') luôn xét MỌI phòng/bầy trong phạm vi được xem, "
    "không thu hẹp về phòng đang chọn. Chỉ giới hạn một phòng khi câu hỏi nói 'phòng này', 'phòng mình' hoặc nêu tên "
    "phòng.\n"
    "- Trả lời đúng trọng tâm câu hỏi; câu hỏi khác nhau thì không lặp lại cùng một bài tóm tắt.")


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
    phong = "\n".join(f"{p['code']} | {p['ten']} | bầy {p['bay']} | {p.get('chi_nhanh') or ''}"
                      for p in phong_order() if pv is None or p["code"] in pv)
    quyen = ("được xem chi tiết nhân sự mọi phòng" if pns is None else
             f"chỉ xem chi tiết nhân sự phòng {', '.join(pns)}" if pns else "KHÔNG được xem chi tiết nhân sự")
    moi_nhat = ngays[-1] if ngays else None
    tam_tinh = bool(moi_nhat) and trang_thai_ngay(moi_nhat)[0]
    co_dinh = QUY_TAC_CHAT + f"\n\nDANH SÁCH PHÒNG (mã | tên | bầy | chi nhánh):\n{phong}"
    thay_doi = (f"Hôm nay {gio_viet_nam():%d/%m/%Y}. Số liệu có đến ngày {moi_nhat or '(chưa có)'}"
                + (" (ngày này đang cập nhật, số tạm tính - nói rõ khi dùng)" if tam_tinh else "") + ".\n"
                f"Người hỏi: vai trò {user.role}, {quyen}.\n"
                f"Đang xem trang {trang}; bộ lọc trên trang: "
                + (", ".join(f"{TEN_BO_LOC[k]} {v}" for k, v in bo_loc_trang(duong_dan, ky).items()) or "mặc định")
                + ". Câu hỏi không nói kỳ thì dùng kỳ đang xem (không có thì luỹ kế tháng có số mới nhất) và nói rõ "
                "kỳ đã dùng. Chi nhánh, phòng đang chọn chỉ là ngữ cảnh, không phải giới hạn của câu hỏi.")
    return co_dinh, thay_doi
