"""Bộ cột, màu ô và thẻ tóm tắt của Báo cáo phòng - MỘT nguồn cho bảng trên web (`ui/pages/phong.py`) và
ảnh PNG (`export_phong.py`), để hai bên không bao giờ lệch nhau.

Quy ước: mỗi cột có `kieu` (cách hiện chữ) và `mau` (luật tô màu). Luật màu viết MỘT lần ở `luat_mau` dưới
dạng (điều kiện JS cho ag-grid, hàm Python tương đương, kiểu ô); test `tests/test_anh_khop_bang.py` chạy
cả hai vế bằng Node để chắc chắn chúng cho cùng kết quả.
"""
from __future__ import annotations

import math
from typing import Callable, NamedTuple

from app import bao_cao_phong as bp
from app import canh_bao as quy_tac
from app import mttn

HANG_TP = 999          # trưởng phòng không xếp hạng: hạng giả để luôn nằm cuối bảng, ô hiện "TP"
CHE_DO = ("ban", "theo_doi", "tat_ca")

# kiểu ô: (nền, màu chữ, đậm). None = giữ nền / màu của dòng.
DO = ("F7BDBD", "7F1D1D", True)
VANG = ("FCEBB4", "6B5104", False)
XANH = ("D3EBD4", "14532D", True)
CHU_DUONG = (None, "0A7A3D", True)
CHU_AM = (None, "B42318", True)
MAU_CHU_Y = "93241C"   # chữ cột "Cần chú ý"
MAU_TEN = "0B6BB5"     # tên nhân sự bấm được để mở chi tiết (chữ xanh trên web)


class Cot(NamedTuple):
    field: str
    ten: str
    kieu: str          # so | pct | chenh | hang | chu
    w: int = 74        # bề rộng tối thiểu trên web
    flex: float = 1
    mau: str = ""      # tên luật tô màu trong `luat_mau`
    dam: bool = False  # in đậm ở mọi dòng
    tip: str = ""


def cot(khoa: str, thang: str) -> Cot:
    ck = bp.thang_truoc_nhan(thang)
    return {
        "hang": Cot("hang", "Hạng", "hang", 68, 0, tip="Trưởng phòng (TP) không xếp hạng"),
        "ten": Cot("ho_ten", "Nhân sự", "chu", 150, 1.6, dam=True),
        "tham_nien": Cot("tham_nien_bucket", "Thâm niên", "chu", 80, .8),
        "online": Cot("online", "Online", "so", 74, dam=True),
        "ck": Cot("ck_online", f"Cùng kỳ {ck}", "so", 72),
        "chenh": Cot("chenh_ck", "+/−", "chenh", 58, mau="chenh", tip="Online so với cùng kỳ"),
        "mttn": Cot("mttn", "MTTN", "so", 66, tip="Online có khách ở tỉnh Miền Trung - Tây Nguyên "
                                                    "(theo CN Quản lý)"),
        "ty_le_mttn": Cot("ty_le_mttn", "% MTTN", "pct", 70, mau="ty_le", tip="Số online MTTN / số online"),
        "vvip": Cot("vvip", "V.VIP", "so"),
        "kem_vvip": Cot("kem_vvip", "VVIP/PTTB", "pct", 78, mau="ty_le", tip="Số V.VIP / số online"),
        "camera": Cot("camera", "Camera", "so"),
        "kem_camera": Cot("kem_camera", "Camera/PTTB", "pct", 78, mau="ty_le", tip="Số camera / số online"),
        "ban_moi_ngay": Cot("ban_moi_ngay", "Bán mới", "so"),
        "online_ngay": Cot("online_ngay", "Online", "so"),
        "ban_moi": Cot("ban_moi", "Bán mới tháng", "so", 84),
        "so_ngay": Cot("so_ngay_co_so", "Số ngày có số", "so", 70),
        "ngay_lien": Cot("ngay_lien_chua_co_so", "Ngày liền chưa có số", "so", 84, mau="ngay_lien"),
        "tuan_nay": Cot("tuan_nay", "Tuần này", "so"),
        "tuan_truoc": Cot("tuan_truoc", "Tuần trước", "so"),
        "ton": Cot("ton", "Chưa online", "so", 72),
        "ton7": Cot("ton_qua_7", "Chờ từ 7 ngày", "so", 78, mau="ton7"),
        "onl1": Cot("onl_1_ngay", "Online trong 1 ngày", "pct", 80,
                    tip="Online trong ngày tạo hoặc hôm sau"),
        "du3": Cot("du_3", "Đủ 3 DV", "pct", tip="Hợp đồng online có cả V.VIP và Camera"),
        "tra_truoc": Cot("tra_truoc", "Trả trước", "pct", tip="Có trả trước 3, 6 hoặc 12 tháng"),
        "nsld": Cot("ket_luan", "NSLĐ kỳ trước", "chu", 86, .9, mau="nsld"),
        "muc": Cot("muc_chu_y", "Mức", "chu", 104, .9, mau="muc"),
        "chu_y": Cot("chu_y", "Cần chú ý", "chu", 160, 3),
    }[khoa]


def bo_cot(che_do: str, thang: str, ngay: int, co_mttn: bool) -> list:
    """Thứ tự cột của từng chế độ xem: khoá cột lẻ, hoặc (tên nhóm, [khoá cột])."""
    m = int(thang[5:7])
    mt = ["mttn", "ty_le_mttn"] if co_mttn else []
    nhom_ngay = (f"NGÀY {ngay:02d}/{m:02d}", ["ban_moi_ngay", "online_ngay"])
    nhip = ("NHỊP CÓ SỐ", ["so_ngay", "ngay_lien", "tuan_nay", "tuan_truoc"])
    ton = ("SỐ TỒN", ["ton", "ton7"])
    if che_do == "theo_doi":
        return ["hang", "ten", "tham_nien", nhip, ton, "nsld", "muc", "chu_y"]
    if che_do == "tat_ca":
        thang_cot = ["online", "ck", "chenh", *mt, "ban_moi", "vvip", "kem_vvip", "camera", "kem_camera",
                     "du3", "tra_truoc", "onl1"]
        return ["hang", "ten", "tham_nien", (f"LUỸ KẾ THÁNG {m}", thang_cot), nhom_ngay, ton, nhip,
                "nsld", "muc", "chu_y"]
    thang_cot = ["online", "ck", "chenh", *mt, "vvip", "kem_vvip", "camera", "kem_camera"]
    return ["hang", "ten", (f"LUỸ KẾ THÁNG {m}", thang_cot), nhom_ngay, "muc", "chu_y"]


def chuan_che_do(che_do: str | None) -> str:
    """Nhận cả "ban_hang" (tên gọi trong yêu cầu) lẫn "ban" (giá trị nút trên web)."""
    return "ban" if che_do in (None, "", "ban_hang") else (che_do if che_do in CHE_DO else "ban")


def cot_phang(che_do: str, thang: str, ngay: int, co_mttn: bool) -> list[tuple[str, str, Cot]]:
    """[(tên nhóm hoặc "", khoá cột, cột)] theo thứ tự trái -> phải (cột lẻ có tên nhóm rỗng)."""
    ra = []
    for muc in bo_cot(che_do, thang, ngay, co_mttn):
        if isinstance(muc, str):
            ra.append(("", muc, cot(muc, thang)))
        else:
            ra += [(muc[0], k, cot(k, thang)) for k in muc[1]]
    return ra


# ------------------------------------------------------------------ màu ô
def luat_mau(khoa_cot: str, tong: dict) -> list[tuple[str, Callable, tuple]]:
    """Luật tô màu của một cột, theo thứ tự ưu tiên (điều kiện đầu tiên khớp thắng):
    [(điều kiện JS trên params.value, hàm Python tương đương, kiểu ô)]. Rỗng nếu cột không tô.

    Các luật số có kèm điều kiện "khác trống và không phải dòng ghim" ở phía JS (xem `LUAT_SO`);
    luật chữ (Mức, NSLĐ) thì không cần vì dòng ghim để trống."""
    c = cot(khoa_cot, "2000-01")
    if c.mau == "ty_le":
        chung = tong.get(c.field)
        if chung is None:
            return []
        return [(f"params.value <= {chung - 10}", lambda v: v <= chung - 10, DO),
                (f"params.value < {chung - 5}", lambda v: v < chung - 5, VANG),
                (f"params.value >= {chung + 5}", lambda v: v >= chung + 5, XANH)]
    if c.mau == "chenh":
        return [("params.value > 0", lambda v: v > 0, CHU_DUONG), ("params.value < 0", lambda v: v < 0, CHU_AM)]
    if c.mau == "ngay_lien":
        return [(f"params.value >= {quy_tac.NGAY_TRAO_DOI_NGAY}", lambda v: v >= quy_tac.NGAY_TRAO_DOI_NGAY, DO),
                (f"params.value >= {bp.NGAY_LIEN_CANH_BAO}", lambda v: v >= bp.NGAY_LIEN_CANH_BAO, VANG)]
    if c.mau == "ton7":
        return [(f"params.value >= {bp.TON_LAU_CANH_BAO}", lambda v: v >= bp.TON_LAU_CANH_BAO, DO),
                ("params.value > 0", lambda v: v > 0, VANG)]
    if c.mau == "muc":
        return [(f"params.value == '{quy_tac.TRAO_DOI_NGAY}'", lambda v: v == quy_tac.TRAO_DOI_NGAY, DO),
                (f"params.value == '{quy_tac.THEO_DOI}'", lambda v: v == quy_tac.THEO_DOI, VANG)]
    if c.mau == "nsld":
        return [("params.value == 'NOT OK'", lambda v: v == "NOT OK", DO)]
    return []


LUAT_SO = ("ty_le", "chenh", "ngay_lien", "ton7")    # luật số: bỏ qua ô trống và dòng ghim
GOC_JS = "params.value != null && !params.node.rowPinned && "


def kieu_o(khoa: str, v, tong: dict, ghim: bool = False) -> tuple | None:
    """Kiểu ô (nền, chữ, đậm) mà luật màu cho giá trị `v`, hoặc None. Dòng ghim (TỔNG) không tô luật số."""
    c = cot(khoa, "2000-01")
    if v is None or (ghim and c.mau in LUAT_SO):
        return None
    for _, py, kieu in luat_mau(khoa, tong):
        if py(v):
            return kieu
    return None


# ------------------------------------------------------------------ chữ trong ô
def _lam_tron(v) -> int:
    """Làm tròn như `Math.round` của JavaScript (0,5 lên) để chữ trong ảnh trùng chữ trên web."""
    return math.floor(float(v) + 0.5)


def chu_o(kieu: str, v) -> str:
    """Chữ hiện trong ô - cùng kết quả với valueFormatter của bảng web (SO, PCT_GACH, CHENH, hạng)."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "–" if kieu == "pct" else ""
    if kieu == "so":
        return f"{_lam_tron(v):,}".replace(",", ".")
    if kieu == "pct":
        return f"{_lam_tron(v)}%"
    if kieu == "chenh":
        v = int(v) if float(v).is_integer() else v
        return f"{'+' if v > 0 else ''}{v}"
    if kieu == "hang":
        return "TP" if v >= HANG_TP else str(int(v))
    return str(v)


# ------------------------------------------------------------------ dòng nhân sự
def dong_nhan_su(nv, chi_chu_y: bool = False) -> tuple[list[dict], dict]:
    """(các dòng nhân sự đã sắp như trên web, dòng TỔNG PHÒNG). Trưởng phòng mang hạng giả HANG_TP."""
    du_lieu = nv[nv.loai_dong == "data"]
    if chi_chu_y:
        du_lieu = du_lieu[du_lieu.muc_chu_y.fillna("") != ""]
    rows = du_lieu.to_dict("records")
    for r in rows:
        if r.get("khong_xet") == "Trưởng phòng":
            r["hang"] = HANG_TP
    rows.sort(key=lambda r: HANG_TP + 1 if r.get("hang") is None else r["hang"])    # ổn định: bằng hạng giữ thứ tự
    return rows, nv[nv.loai_dong == "total"].iloc[0].to_dict()


# ------------------------------------------------------------------ thẻ tóm tắt đầu trang
class The(NamedTuple):
    nhan: str
    gia_tri: str
    phu: str
    tt: str = ""       # "" | ok | warn | bad: màu vạch đầu thẻ


def _pct(v) -> str:
    return "–" if v is None else f"{float(v):.0f}%"


def _so(v) -> str:
    return f"{int(v or 0):,}".replace(",", ".")


def the_tom_tat(thang: str, ngay: int, code: str, dong: dict, ss, tam_tinh: bool) -> list[The]:
    """Các thẻ chỉ số đầu trang Báo cáo phòng (web hiện y hệt; ảnh PNG vẽ lại đúng các thẻ này)."""
    hang = ss.set_index("khoa")
    h_htkh = hang.loc["htkh_internet"]
    h = h_htkh if h_htkh.hang else hang.loc["online"]
    tt = dong.get("tang_truong")
    kl = dong.get("ket_luan")
    the = [
        The("Online tháng", _so(dong.get("online")),
            f"Mục tiêu {_so(dong.get('mt_internet'))} · HTKH {_pct(dong.get('htkh_internet'))}"
            if dong.get("mt_internet") else "Chưa nhập chỉ tiêu tháng"),
        The("Tăng trưởng", "–" if tt is None else f"{tt:+.0f}%",
            f"Cùng kỳ {bp.thang_truoc_nhan(thang)}: {_so(dong.get('ck_online'))} online",
            "" if tt is None else ("ok" if tt >= 0 else "bad")),
        The("VVIP/PTTB", _pct(dong.get("vvip_ty_le")), f"{_so(dong.get('vvip'))} V.VIP"),
        The("Camera", _so(dong.get("camera")),
            f"Mục tiêu {_so(dong.get('mt_camera'))} · HTKH {_pct(dong.get('htkh_camera'))}"
            if dong.get("mt_camera") else "Chưa nhập chỉ tiêu camera"),
        The(f"Online ngày {ngay:02d}/{thang[5:7]}", _so(dong.get("ngay_online")),
            f"Mục tiêu {_so(dong.get('mt_ngay'))} · {kl}" if dong.get("mt_ngay")
            else f"Bán mới {_so(dong.get('ngay_ban_moi'))}",
            "" if not dong.get("mt_ngay") else
            ("ok" if kl == "Đạt" else ("warn" if tam_tinh else "bad"))),
        The("Hạng phòng", f"{h.hang}/{h.so_phong}" if h.hang else "–",
            ("Theo tỷ lệ HTKH" if h is h_htkh else "Theo số online") + " · phòng kinh doanh",
            "" if not h.hang else ("ok" if h.hang <= h.so_phong / 3 else
                                   ("bad" if h.hang > h.so_phong * 2 / 3 else "warn"))),
    ]
    if mttn.ap_dung(code):
        the.insert(1, the_mttn(mttn.tong_hop(thang, ngay, code)))
    return the


def the_mttn(m: dict) -> The:
    """Thẻ MTTN: tỷ lệ số online có khách ở tỉnh MTTN, so với mục tiêu % của tháng."""
    tl_ = "–" if m["ty_le"] is None else f"{m['ty_le']:.0f}%"
    phu = f"{_so(m['mttn'])}/{_so(m['tong'])} online"
    if m["muc_tieu"] is None:
        return The(m["ten"], tl_, phu + " · chưa nhập mục tiêu %")
    phu += f" · mục tiêu {m['muc_tieu']:.0f}%" + (f" · cần thêm {_so(m['can_them'])} số MTTN"
                                                  if m["can_them"] else " · đạt")
    return The(m["ten"], tl_, phu, "" if m["dat"] is None else ("ok" if m["dat"] else "bad"))
