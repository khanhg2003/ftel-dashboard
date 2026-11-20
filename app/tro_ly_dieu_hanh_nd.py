"""Nội dung của Trợ lý điều hành: NHẬN ĐỊNH + 2-3 PHƯƠNG ÁN (A/B/C) + KHUYẾN NGHỊ cho một vấn đề.

LUẬT giữ vai SỰ THẬT, LLM chỉ VIẾT. Code dựng "bảng sự thật" (số đã đo bằng hàm sẵn có của app); LLM nhận bảng đó và viết lại nhận định, phương án, mọi số trong câu của nó
phải có trong bảng (`kiem_so`). Sai số, JSON hỏng, LLM lỗi, hết trần lượt gọi mỗi ngày, chưa bật AI hay hết hạn mức tháng thì dùng bản LUẬT dựng bằng khuôn cố định: vẫn đầy đủ
nhận định và phương án. Lời gửi LLM không có tên khách; nhân sự đi bằng MÃ acc, tên thật chỉ được thay vào chữ SAU khi LLM trả về (`hien`). Khoá API, hạn mức tháng dùng của
`app/tro_ly.py` (không sửa lõi đó). Test bằng LLM giả: truyền `goi_llm(he_thong, nguoi_dung) -> chuỗi JSON`.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime

from app import tro_ly_dieu_hanh_so as so
from app.thoi_gian import LECH_GIO_VN, utc_bay_gio

TOI_DA_CAO_NEU = 8                                # số phát hiện mức cao đưa vào bảng sự thật / nhận định (còn lại ghi "còn N mục")
TOI_DA_DONG_CHI_TIET = 4
TRAN_NGAY_MAC_DINH = 30
_SO = re.compile(r"(?<![\w.,/:])\d+(?:[.,/:]\d+)*%?")
_NGOAI_LE_CHU = re.compile(r"đấu\s*nối", re.I)
_THOI_HAN = re.compile(r"\d+\s*(?:giờ|ngày|tuần|phút)\b", re.I)       # "trong 8 giờ", "sau 2 ngày": hạn việc cần làm, không phải số liệu để kiểm


def dinh_so(x) -> str:
    """Số kiểu Việt Nam: 1.234 và 5,4."""
    x = float(x)
    return f"{x:,.0f}".replace(",", ".") if x.is_integer() else f"{x:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def hien(chu: str, ten: dict | None) -> str:
    """Thay mã acc nhân sự trong chữ bằng họ tên (chỉ cho chữ hiện ra với người, KHÔNG BAO GIỜ cho lời gửi LLM)."""
    for ma in sorted(ten or {}, key=len, reverse=True):
        if ma and ten[ma] and ma in chu:
            chu = re.sub(rf"(?<![\w.]){re.escape(ma)}(?!\w)", lambda _m, t=ten[ma]: t, chu)
    return chu


def ngay_hom_nay(now: datetime | None = None) -> str:
    """Ngày theo giờ Việt Nam dạng yyyymmdd (mốc `now` là UTC như mọi mốc ghi database)."""
    return ((now or utc_bay_gio()) + LECH_GIO_VN).strftime("%Y%m%d")


# ------------------------------------------------------------------ bản LUẬT (khuôn cố định)
def _pa(ma: str, tieu_de: str, mo_ta: str) -> dict:
    return {"ma": ma, "tieu_de": tieu_de, "mo_ta": mo_ta}


def _chi_tiet(s: dict) -> str:
    dong = [f"{f['tieu_de']}" for f in s["phat_hien_cao"][:TOI_DA_DONG_CHI_TIET]]
    return (" Nổi bật: " + "; ".join(dong) + ".") if dong else ""


def _khuon(s: dict) -> tuple[str, list[dict], str]:
    bc, loai = s["bang_chung"], s["loai"]
    so_cao = bc["so_cao"]
    if loai == "kd_nhan_su":
        nd = (f"Phòng {bc['phong']} có {dinh_so(bc['so_nguoi'])} nhân sự cần chú ý, trong đó {dinh_so(bc['so_cao_nguoi'])} người ở mức cao." + _chi_tiet(s))
        return nd, [_pa("A", "Trưởng phòng trao đổi trực tiếp từng người", "Gặp từng người trong danh sách, hỏi nguyên nhân, chốt số cần đạt và hạn trong 2 ngày."),
                    _pa("B", "Ghép cặp kèm cặp với đồng nghiệp làm tốt", "Mỗi người cần chú ý đi cùng một đồng nghiệp đang bán tốt để học cách làm trong tuần."),
                    _pa("C", "Theo dõi thêm một ngày", "Chưa can thiệp, kiểm lại số online vào ngày mai.")], "A" if so_cao or bc["so_nguoi"] >= 3 else "C"
    if loai == "kd_phong":
        ten = "Toàn chi nhánh" if s["cap"] == "chi_nhanh" else f"Phòng {s['doi_tuong']}"
        can = f", cần {dinh_so(bc['can_moi_ngay'])} online mỗi ngày trong {dinh_so(bc['con_lai'])} ngày còn lại (hiện bình quân {dinh_so(bc['tb_ngay'])})" if bc.get("can_moi_ngay") else ""
        nd = (f"{ten} dự báo đạt {dinh_so(bc['du_bao'])}/{dinh_so(bc['muc_tieu'])} online cuối tháng ({bc['danh_gia']}), hụt {dinh_so(bc['hut'])} so với mục tiêu{can}. "
              f"Luỹ kế hiện có {dinh_so(bc['luy_ke'])} online.")
        return nd, [_pa("A", "Họp nhanh chốt kế hoạch bù số", "Chốt số online cần đạt mỗi ngày, giao từng người và hạn xong trong ngày."),
                    _pa("B", "Dồn lực xử lý hợp đồng tồn và hẹn online sớm", "Rà hợp đồng đang chờ online, hẹn lại giờ lắp để chuyển thành online sớm nhất."),
                    _pa("C", "Giữ kế hoạch, kiểm lại sau 2 ngày", "Chưa đổi cách làm, đo lại dự báo sau 2 ngày.")], "A" if s["muc"] == "cao" else "B"
    if loai == "dvkh_cskh":
        nd = f"Có {dinh_so(bc['so_nguoi'])} CSKH có tải việc hoặc tỷ lệ quá hạn bất thường, trong đó {dinh_so(bc['so_cao_nguoi'])} người ở mức cao." + _chi_tiet(s)
        return nd, [_pa("A", "Trưởng nhóm rà SR quá hạn của người đứng đầu danh sách", "Ngồi lại với từng người, chốt SR nào xong trong ngày, SR nào cần hỗ trợ."),
                    _pa("B", "Chia lại SR tồn cho CSKH đang nhẹ việc", "Giao bớt SR tồn và SR quá hạn sang người ít việc nhất trong khối."),
                    _pa("C", "Theo dõi thêm một ngày", "Chưa can thiệp, kiểm lại tỷ lệ quá hạn vào ngày mai.")], "A" if so_cao else "B"
    if loai == "dvkh_sr":
        nd = f"Khối DVKH có {dinh_so(bc['so_muc'])} chỉ số SR vượt ngưỡng ({dinh_so(so_cao)} mức cao)." + _chi_tiet(s)
        return nd, [_pa("A", "Chốt người xử lý và giờ xong cho SR quá hạn", "Mỗi SR quá hạn có tên người xử lý và giờ hoàn tất ngay trong ngày."),
                    _pa("B", "Điều thêm người cho phòng tồn nhiều", "Chuyển bớt người từ phòng nhẹ việc sang phòng đang tồn nhiều SR."),
                    _pa("C", "Theo dõi thêm một ngày", "Chưa can thiệp, kiểm lại số SR tồn vào ngày mai.")], "A"
    if loai == "dvkh_roi_mang":
        nd = f"Số khách rời mạng tăng so với tháng trước ở {dinh_so(bc['so_muc'])} đơn vị ({dinh_so(so_cao)} mức cao)." + _chi_tiet(s)
        return nd, [_pa("A", "Gọi chăm sóc nhóm khách có nguy cơ rời mạng", "Ưu tiên khách chờ thanh lý và hủy sau sử dụng ở đơn vị tăng nhiều nhất."),
                    _pa("B", "Rà nguyên nhân rời mạng theo phường", "Mở tab Điểm nóng, tìm phường rời mạng cao và phối hợp kỹ thuật kiểm tra hạ tầng."),
                    _pa("C", "Theo dõi thêm một tuần", "Chưa can thiệp, đo lại số khách rời mạng sau một tuần.")], "A"
    if loai == "dvkh_cong_no":
        nd = f"Thu nợ chậm hơn kỳ trước (cùng ngày) ở {dinh_so(bc['so_muc'])} đơn vị ({dinh_so(so_cao)} mức cao)." + _chi_tiet(s)
        return nd, [_pa("A", "Dồn lực gọi nhắc phường thu chậm nhất", "Chọn các phường còn nhiều hoá đơn chưa thu và giao người gọi nhắc trong tuần."),
                    _pa("B", "Tăng số lần nhắc nợ trong những ngày còn lại của kỳ", "Thêm một vòng nhắc bằng tin nhắn và gọi điện cho khách chưa thanh toán."),
                    _pa("C", "Theo dõi thêm vài ngày", "Chưa can thiệp, đo lại tỷ lệ thu nợ sau vài ngày.")], "A"
    nd = f"{s['tieu_de']}. Cần người phụ trách nạp lại dữ liệu để các số trên trang không bị cũ."
    return nd, [_pa("A", "Nhờ người phụ trách nạp file ngay hôm nay", "Báo người nạp dữ liệu hoàn tất trong ngày."),
                _pa("B", "Kiểm tra lịch nạp và nguồn xuất file", "Xem file có được xuất đúng hạn không, có lỗi gì chặn không."),
                _pa("C", "Chờ thêm một ngày", "Chưa can thiệp, kiểm lại vào ngày mai.")], "A"


def bo_sung(nd: str, s: dict) -> str:
    """Bước ghép bản tin: mọi phát hiện mức cao phải có trong nội dung (thiếu thì code tự chèn); mục thấp gộp thành một dòng, không bỏ im lặng."""
    thieu = [d for d in dict.fromkeys(f["doi_tuong"] for f in s["phat_hien_cao"]) if d.lower() not in nd.lower()]
    if thieu:
        nd += f" Cần xem: {', '.join(thieu)}."
    if s["bang_chung"]["so_cao"] > len(s["phat_hien_cao"]):
        nd += f" Còn {s['bang_chung']['so_cao'] - len(s['phat_hien_cao'])} mục mức cao khác."
    if s["bang_chung"]["so_thap"]:
        nd += f" Còn {s['bang_chung']['so_thap']} mục nhỏ (mức thấp) chưa nêu riêng, xem hết ở {s['duong_dan']}."
    return nd


# ------------------------------------------------------------------ kiểm số
def _ung_vien(tok: str) -> list:
    """Các cách đọc một số trong câu: "1.234" là nghìn hoặc thập phân, "5,4%" là 5.4, ngày giờ giữ nguyên chữ."""
    t = tok.rstrip("%")
    if "/" in t or ":" in t:
        return [t]
    cach = [float(t.replace(",", "."))] if t.count(",") <= 1 and t.count(".") <= 1 else []
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", t):
        cach.append(float(t.replace(".", "").replace(",", ".")))
    return cach or [t]


def _so_cho_phep(x, kq: set) -> set:
    if isinstance(x, bool) or x is None:
        return kq
    if isinstance(x, (int, float)):
        kq.update([round(float(x), 6)])
    elif isinstance(x, str):
        for tok in _SO.findall(x):
            kq.update(round(v, 6) if isinstance(v, float) else v for v in _ung_vien(tok))
    elif isinstance(x, dict):
        for v in x.values():
            _so_cho_phep(v, kq)
    elif isinstance(x, (list, tuple)):
        for v in x:
            _so_cho_phep(v, kq)
    return kq


def kiem_so(chu: str, bang_su_that) -> bool:
    """Đúng khi mọi số / ngày trong `chu` có trong bảng sự thật (so khớp theo giá trị, đọc được kiểu 1.234 và 5,4%)."""
    cho_phep = _so_cho_phep(bang_su_that, set())
    return all(any((round(v, 6) if isinstance(v, float) else v) in cho_phep for v in _ung_vien(tok)) for tok in _SO.findall(chu or ""))


def doc_json(raw: str) -> dict | None:
    t = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(), flags=re.M).strip()
    try:
        j = json.loads(t)
    except ValueError:
        return None
    return j if isinstance(j, dict) else None


def kiem_ket_qua(j: dict | None, bang: dict) -> dict | None:
    """Chỉ nhận JSON đúng khuôn: nhận định ngắn, 2-3 phương án mã A/B/C, khuyến nghị là một trong các phương án, mọi số có trong bảng, không dùng chữ cấm."""
    try:
        nd, pa, kn = str(j["nhan_dinh"]).strip(), j["phuong_an"], str(j["khuyen_nghi"]).strip().upper()
        ds = [_pa(str(p["ma"]).strip().upper(), str(p["tieu_de"]).strip(), str(p["mo_ta"]).strip()) for p in pa]
    except (TypeError, KeyError, ValueError, AttributeError):
        return None
    if not (2 <= len(ds) <= 3) or [p["ma"] for p in ds] != ["A", "B", "C"][:len(ds)] or kn not in {p["ma"] for p in ds}:
        return None
    if not nd or len(nd) > 700 or any(not p["tieu_de"] or not p["mo_ta"] or len(p["tieu_de"]) > 90 or len(p["mo_ta"]) > 220 for p in ds):
        return None
    chu = " ".join([nd, *[p["tieu_de"] + " " + p["mo_ta"] for p in ds]])
    chu_so = " ".join([nd, *[_THOI_HAN.sub("", p["tieu_de"] + " " + p["mo_ta"]) for p in ds]])       # nhận định phải đúng từng số; phương án được tự đặt thời hạn (giờ / ngày / tuần)
    return None if _NGOAI_LE_CHU.search(chu) or not kiem_so(chu_so, bang) else {"nhan_dinh": nd, "phuong_an": ds, "khuyen_nghi": kn}


# ------------------------------------------------------------------ LLM: trần lượt, nhớ kết quả, gọi
HE_THONG = ("Bạn là trợ lý điều hành của một chi nhánh viễn thông, viết cho trưởng phòng / giám đốc đọc trên điện thoại. Chỉ dùng số có trong bang_su_that: chép đúng, "
            "không tính thêm, không làm tròn lại, không đánh số thứ tự. Gọi nhân sự bằng đúng mã acc và phòng bằng đúng mã trong bảng, không bịa tên, không bịa nguyên nhân. "
            "Chỉ dùng chữ 'online' khi nói về hợp đồng đã lắp xong; không dùng cách gọi khác. Viết tiếng Việt dễ hiểu, câu ngắn. Trả về MỘT đối tượng JSON: {\"nhan_dinh\": tối đa 3 câu, \"phuong_an\": "
            "[{\"ma\": \"A\", \"tieu_de\": ..., \"mo_ta\": ...}, ...] gồm 2 hoặc 3 phương án mã A, B, C, \"khuyen_nghi\": mã một phương án}. Mỗi phương án nêu việc cần làm và ai làm. "
            "Hướng gợi ý nằm ở phuong_an_mau, được viết lại cho sát tình hình.")


def tran_ngay() -> int:
    try:
        return int(os.getenv("TRO_LY_DIEU_HANH_TRAN_NGAY", so.cau_hinh()["tran_llm_ngay"]))
    except ValueError:
        return TRAN_NGAY_MAC_DINH


def _khoa_ngay(now: datetime) -> str:
    return "llm:" + ngay_hom_nay(now)


def dem_llm(now: datetime | None = None) -> int:
    return int(so.doc_phu(_khoa_ngay(now or utc_bay_gio()), "0") or 0)


def tinh_luot(now: datetime) -> None:
    so.ghi_phu(_khoa_ngay(now), str(dem_llm(now) + 1))


def _goi_va_kiem(v: dict, goi_llm, pa: list[dict], kn: str, now: datetime) -> tuple[dict | None, str]:
    """(kết quả đã kiểm, lý do dùng luật). Nhớ theo (vấn đề, bảng sự thật); tính một lượt vào trần ngày trước khi gọi."""
    bang = v["su_that"]
    khoa = "nho:" + hashlib.sha1((v["ma_van_de"] + json.dumps(bang, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()
    da_nho = so.doc_phu(khoa)
    if da_nho:
        j = kiem_ket_qua(doc_json(da_nho), bang)
        if j:
            return j, ""
    if dem_llm(now) >= tran_ngay():
        return None, "het_tran"
    tinh_luot(now)
    try:
        raw = goi_llm(HE_THONG, json.dumps({"bang_su_that": bang, "phuong_an_mau": [{"ma": p["ma"], "tieu_de": p["tieu_de"]} for p in pa], "khuyen_nghi_mau": kn}, ensure_ascii=False))
    except Exception:
        return None, "loi_ai"
    j = kiem_ket_qua(doc_json(raw), bang)
    if not j:
        return None, "sai_dinh_dang_hoac_so"
    so.ghi_phu(khoa, json.dumps(j, ensure_ascii=False))
    return j, ""


def soan(v: dict, goi_llm=None, ten: dict | None = None, now: datetime | None = None) -> dict:
    """Dựng nhận định + phương án + khuyến nghị cho một vấn đề (`v` từ `tro_ly_dieu_hanh.gom`). `goi_llm` None = chỉ dùng luật.
    Trả {nhan_dinh, phuong_an, khuyen_nghi, nguon_noi_dung: "llm" | "luat", ly_do_luat}."""
    now = now or utc_bay_gio()
    nd, pa, kn = _khuon(v["su_that"])
    nguon, ly_do = "luat", "chua_bat_ai" if goi_llm is None else ""
    if goi_llm is not None:
        j, ly_do = _goi_va_kiem(v, goi_llm, pa, kn, now)
        if j:
            nd, pa, kn, nguon = j["nhan_dinh"], j["phuong_an"], j["khuyen_nghi"], "llm"
    nd = bo_sung(nd, v["su_that"])
    return {"nhan_dinh": hien(nd, ten), "phuong_an": [{**p, "tieu_de": hien(p["tieu_de"], ten), "mo_ta": hien(p["mo_ta"], ten)} for p in pa],
            "khuyen_nghi": kn, "nguon_noi_dung": nguon, "ly_do_luat": ly_do}


# ------------------------------------------------------------------ trạng thái AI và hàm gọi LLM thật
def trang_thai_ai(now: datetime | None = None) -> dict:
    """AI đang BẬT hay đang dùng BẢN LUẬT, và vì sao. Chỉ đọc cấu hình, không gọi mạng."""
    tran, dem = tran_ngay(), dem_llm(now)
    kq = {"dung_ai": False, "ly_do": "", "luot_hom_nay": dem, "tran_ngay": tran}
    if os.getenv("TRO_LY_DIEU_HANH_AI", "1").strip() == "0":
        return {**kq, "ly_do": "Đã tắt bằng biến môi trường TRO_LY_DIEU_HANH_AI=0."}
    try:
        from app import tro_ly
        ch = tro_ly.cau_hinh()
        if not ch["bat"]:
            return {**kq, "ly_do": "Trợ lý AI của app đang tắt (Quản trị → Trợ lý AI)."}
        if not ch["key"]:
            return {**kq, "ly_do": "Chưa có khoá API (dán ở Quản trị → Trợ lý AI)."}
        if tro_ly.chi_phi_thang() >= ch["tran_usd"]:
            return {**kq, "ly_do": "Đã hết ngân sách AI của tháng này."}
    except Exception:
        return {**kq, "ly_do": "Không đọc được cấu hình Trợ lý AI."}
    if dem >= tran:
        return {**kq, "ly_do": f"Đã dùng hết {tran} lượt gọi AI của hôm nay."}
    return {**kq, "dung_ai": True}


def goi_llm_mac_dinh():
    """Hàm gọi LLM thật qua `app/tro_ly.py` (khoá và hạn mức tháng của app); None nếu AI chưa dùng được."""
    if not trang_thai_ai()["dung_ai"]:
        return None
    from app import tro_ly
    ch = tro_ly.cau_hinh()

    def goi(he_thong: str, nguoi_dung: str) -> str:
        msg = tro_ly.hoi([{"role": "system", "content": he_thong}, {"role": "user", "content": nguoi_dung}], ch["model_chat"], ch["key"], "tro_ly_dieu_hanh", "dieu_hanh",
                         han=40, toi_da=1800, dinh_dang={"type": "json_object"})
        return msg.get("content") or ""
    return goi


# ------------------------------------------------------------------ câu kết quả kiểm chứng
def cau_ket_qua(cs: dict, sau) -> str:
    """Câu kết quả bằng luật: so chỉ số đo lúc đề xuất với số đo lại."""
    truoc, nhan, dv = cs["gia_tri"], cs["nhan"], cs.get("don_vi", "")
    if sau == truoc:
        return f"{nhan} không đổi, vẫn {dinh_so(sau)} {dv}. Chưa cải thiện."
    huong, giua = ("giảm", "xuống") if sau < truoc else ("tăng", "lên")
    pt = f" ({huong} {dinh_so(round(abs(sau - truoc) / truoc * 100))}%)" if truoc else ""
    tot = (sau < truoc) == (cs.get("tot_khi", "giam") == "giam")
    return f"{nhan} {huong} từ {dinh_so(truoc)} {giua} {dinh_so(sau)} {dv}{pt}. {'Đã cải thiện.' if tot else 'Chưa cải thiện.'}"


def viet_lai_ket_qua(cs: dict, sau, luat: str, goi_llm, ten: dict, now: datetime) -> tuple[str, str]:
    """(câu kết quả, "llm" | "luat"): LLM chỉ viết lại câu luật, kiểm số với bảng {trước, sau}; mọi trục trặc thì giữ câu luật."""
    if goi_llm is None or dem_llm(now) >= tran_ngay():
        return hien(luat, ten), "luat"
    bang = {"chi_so": cs["nhan"], "don_vi": cs.get("don_vi", ""), "truoc": cs["gia_tri"], "sau": sau, "cau_luat": luat}
    tinh_luot(now)
    try:
        j = doc_json(goi_llm("Viết lại MỘT hoặc hai câu kết quả ngắn gọn cho lãnh đạo từ bang_su_that, chỉ dùng số trong bảng, dùng chữ 'online' khi nói về hợp đồng đã lắp xong. Trả JSON {\"ket_qua\": \"...\"}.",
                             json.dumps({"bang_su_that": bang}, ensure_ascii=False)))
        kq = str(j["ket_qua"]).strip() if j else ""
    except Exception:
        kq = ""
    if not kq or len(kq) > 300 or _NGOAI_LE_CHU.search(kq) or not kiem_so(kq, bang):
        return hien(luat, ten), "luat"
    return hien(kq, ten), "llm"
