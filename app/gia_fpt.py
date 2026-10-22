"""Tra cứu giá gói cước FPT theo khu vực (chủ app chốt 22/10/2026).

Giá lấy THẲNG từ dịch vụ mà website fpt.vn đang gọi (`apis.fpt.vn/ecp/public`): gửi mã tỉnh + mã phường, nhận lại các gói
đang bán và giá đúng khu vực đó, nên số khớp website. Đây không phải API chính thức: nếu FPT đổi cách gọi hoặc dịch vụ
không trả lời thì hàm ném `LoiGia` (trang báo bằng lời dễ hiểu), và `goi_theo_phuong` trả lại bản lần gần nhất đã lấy được.
Không lưu giá vào database; mỗi khu vực nhớ tạm `TTL_GOI` giây trong máy chủ.

Giá trên website đã gồm VAT. Gói Internet có nhiều lựa chọn thời hạn (1 tháng trả sau, 3 / 6 / 13 / 26 tháng trả trước):
`chi_tiet_goi` đọc các lựa chọn đó. Quét cả tỉnh (`quet_tinh`) gọi mỗi phường một lần nên chỉ chạy khi người dùng bấm.
"""
from __future__ import annotations

import json
import re
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor, TimeoutError as HetGio, as_completed
from datetime import datetime, timedelta

from app.bo_nho import nho
from app.thoi_gian import LECH_GIO_VN, chu_gio_vn, utc_bay_gio

GOC = "https://apis.fpt.vn/ecp/public"
HAN_GOI = 15                  # giây chờ một lần gọi
TTL_GOI = 900                 # giá một khu vực: 15 phút
TTL_DANH_MUC = 86400          # danh sách tỉnh / phường ít đổi
SO_LUONG_QUET = 8
HAN_QUET = 45                 # Vercel cho chạy tối đa 60 giây: quá hạn này thì trả phần đã quét được

TINH_MAC_DINH = 511           # Đà Nẵng (đã gồm Quảng Nam cũ)
KHACH = {"ca_nhan": "Cá nhân", "doanh_nghiep": "Doanh nghiệp"}
# Chỉ lấy Internet, Camera, FPT Play (chủ app chốt 22/10/2026: không cần Smart TV, Tăng tốc, Smart Home, thiết bị mạng)
NHOM_THEO_LOAI = {"internet": "Internet", "fpt-camera": "Camera", "fpt-play": "FPT Play"}
THU_TU_NHOM = ["Internet", "Combo Internet + V.VIP", "Internet + Camera An Tâm", "Camera", "FPT Play"]
NHAN_PHU = {"Nổi bật", "Phổ biến", "Mới", "Hot"}   # nhãn của website, không phải ưu đãi
DON_VI_GIA = {"Camera": "giá thiết bị"}          # các nhóm còn lại là giá mỗi tháng

_GAN_NHAT: dict = {}          # bản giá lần gần nhất lấy được, dùng khi dịch vụ lỗi
_khoa = threading.Lock()


class LoiGia(Exception):
    """Không lấy được giá từ fpt.vn (mạng, dịch vụ đổi cách trả lời...)."""


def chu_tien(v) -> str:
    return "–" if v is None else f"{v:,.0f}".replace(",", ".") + "đ"


def _goi_dich_vu(duong: str, noi_dung: dict, han: float = HAN_GOI):
    req = urllib.request.Request(
        f"{GOC}{duong}", data=json.dumps(noi_dung).encode(), method="POST",
        headers={"Content-Type": "application/json", "Accept": "*/*", "client-id": "fptvn"})
    try:
        with urllib.request.urlopen(req, timeout=han) as r:
            kq = json.loads(r.read())
    except Exception as e:
        raise LoiGia("Chưa lấy được giá từ fpt.vn lúc này.") from e
    if not isinstance(kq, dict) or kq.get("success") is False or kq.get("data") is None:
        raise LoiGia("fpt.vn trả lời không đúng dạng mong đợi.")
    return kq["data"]


def _vi_tri(tinh: int, phuong: int) -> dict:
    return {"province_id": int(tinh), "ward_id": int(phuong)}


# ------------------------------------------------------------------ danh mục khu vực
@nho("gia_fpt", TTL_DANH_MUC)
def danh_sach_tinh() -> list[dict]:
    """[{id, ten}] theo thứ tự website (thành phố lớn trước)."""
    ds = _goi_dich_vu("/v1/locations/provinces/list", {"address_level": "Level2"})
    return [{"id": int(t["id"]), "ten": t["text"]} for t in ds]


@nho("gia_fpt", TTL_DANH_MUC)
def danh_sach_phuong(tinh: int) -> list[dict]:
    ds = _goi_dich_vu("/v1/locations/wards/list", {"location_id": int(tinh), "address_level": "Level2"})
    return sorted(({"id": int(p["id"]), "ten": p["text"]} for p in ds), key=lambda p: p["ten"])


# ------------------------------------------------------------------ gói theo khu vực
def _spec(x: dict, *tu_khoa: str):
    for s in x.get("product_spec_characteristics") or []:
        ten = (s.get("name") or "").lower()
        if all(k in ten for k in tu_khoa):
            return s.get("value")
    return None


def _la_doanh_nghiep(x: dict) -> bool:
    chu = f"{x.get('name') or ''} {x.get('tagline') or ''} {x.get('card_description') or ''}"
    return bool(re.search(r"\bbiz\b|\blux\b|doanh nghiệp", chu, re.I))


def _nhom(x: dict) -> str:
    ten = (x.get("name") or "")
    nhom = NHOM_THEO_LOAI.get(x.get("type"), (x.get("type_name") or "Khác"))
    if nhom != "Internet":
        return nhom
    if re.search(r"v\.?vip", ten, re.I):
        return "Combo Internet + V.VIP"
    if "an tâm" in ten.lower():
        return "Internet + Camera An Tâm"
    return nhom


def _toc_do(x: dict, mo_ta: list[str]) -> str | None:
    xuong, len_ = _spec(x, "download"), _spec(x, "upload")
    if xuong and len_:
        return f"{xuong} / {len_}"
    for dong in mo_ta:
        m = re.search(r"download/upload\s+(.+)", dong, re.I)
        if m:
            return m.group(1).replace("/", " / ")
    return None


def _chuan_goi(x: dict) -> dict:
    gia = x.get("price") or {}
    mo_ta = [d.strip() for d in (x.get("card_description") or "").split("\n") if d.strip()]
    tb = _spec(x, "thiết bị")
    return {"id": int(x["id"]), "code": x.get("code") or x.get("slug"), "ten": x.get("name") or x.get("title") or "",
            "nhom": _nhom(x), "khach": "doanh_nghiep" if _la_doanh_nghiep(x) else "ca_nhan",
            "gia": gia.get("price") if gia.get("price") is not None else gia.get("min_price"),
            "toc_do": _toc_do(x, mo_ta), "thiet_bi": int(tb) if str(tb or "").isdigit() else None,
            "uu_dai": "" if (x.get("tagline") or "") in NHAN_PHU else (x.get("tagline") or "").replace("12T", "12 tháng"),   # website lúc ghi 12T lúc 12 tháng
            "nhan": x.get("tagline") if (x.get("tagline") or "") in NHAN_PHU else "", "mo_ta": mo_ta}


def _thu_tu(g: dict):
    nhom = g["nhom"]
    return (THU_TU_NHOM.index(nhom) if nhom in THU_TU_NHOM else len(THU_TU_NHOM), g["khach"], g["gia"] or 0, g["ten"])


def _doc_goi(tinh: int, phuong: int) -> list[dict]:
    ds = _goi_dich_vu("/v1.1/packages/list", {"page_size": 100, "location": _vi_tri(tinh, phuong)})
    return sorted((_chuan_goi(x) for x in ds if x.get("type") in NHOM_THEO_LOAI), key=_thu_tu)


@nho("gia_fpt", TTL_GOI)
def _goi_moi(tinh: int, phuong: int) -> dict:
    return {"goi": _doc_goi(tinh, phuong), "luc": utc_bay_gio(), "cu": False}


def goi_theo_phuong(tinh: int, phuong: int) -> dict:
    """{goi, luc, cu}: các gói đang bán ở phường đó. Dịch vụ lỗi mà đã có bản trước thì trả bản đó (cu=True)."""
    try:
        kq = _goi_moi(tinh, phuong)
    except LoiGia:
        with _khoa:
            cu = _GAN_NHAT.get((tinh, phuong))
        if cu is None:
            raise
        return {**cu, "cu": True}
    with _khoa:
        _GAN_NHAT[(tinh, phuong)] = kq
    return kq


def _chon(v) -> set | None:
    """Giá trị ô lọc (một chữ hoặc danh sách chọn nhiều) -> tập giá trị; None = không lọc (rỗng hoặc "all")."""
    ds = {v} if isinstance(v, str) else set(v or [])
    return None if not ds or "all" in ds else ds


def loc_goi(goi: list[dict], khach="all", nhom="all") -> list[dict]:
    """Lọc theo khách hàng và nhóm sản phẩm; mỗi ô nhận một giá trị hoặc nhiều giá trị (chọn nhiều thì lấy các gói thuộc BẤT KỲ giá trị nào)."""
    k, n = _chon(khach), _chon(nhom)
    return [g for g in goi if (k is None or g["khach"] in k) and (n is None or g["nhom"] in n)]


def cac_nhom(goi: list[dict]) -> list[str]:
    co = {g["nhom"] for g in goi}
    return [n for n in THU_TU_NHOM if n in co] + sorted(co - set(THU_TU_NHOM))


# ------------------------------------------------------------------ chi tiết một gói
def _tien(o) -> int | None:
    return o.get("price") if isinstance(o, dict) else None


def _gio_vn(chuoi: str) -> datetime:
    return datetime.strptime(chuoi[:19], "%Y-%m-%d %H:%M:%S") + LECH_GIO_VN


def _khoang(gia_tri) -> list | None:
    """[thấp nhất, cao nhất] của các số dương; không có số nào thì None (không có khoản phí này)."""
    ds = [v for v in gia_tri if v]
    return [min(ds), max(ds)] if ds else None


@nho("gia_fpt", TTL_GOI)
def chi_tiet_goi(code: str, tinh: int, phuong: int, gia_thang: float | None) -> dict:
    """Các lựa chọn thời hạn / hình thức thanh toán đang áp dụng cho gói ở phường đó.

    `thang_dong` = số tháng thực phải đóng (tổng tiền dịch vụ / giá tháng); `tang` = số tháng được tặng thêm
    (VD 13 tháng chỉ đóng 12). `gia_thang` lấy từ danh sách gói (giá "price" của dịch vụ chi tiết là giá theo thời hạn
    ngắn nhất, không phải giá tháng). Chính sách hết hạn rồi thì bỏ."""
    d = _goi_dich_vu("/v1.1/packages/get", {"code": code, "location": _vi_tri(tinh, phuong)})
    gia = gia_thang
    qua = {}
    for p in ((d.get("display_contents") or {}).get("promotion_contents") or []):
        qua[(p.get("contract_length_months"), p.get("charge_type"))] = p.get("tag_line") or ""
    bay_gio = utc_bay_gio() + LECH_GIO_VN
    lua_chon = []
    for o in d.get("product_offering_price") or []:
        if o.get("status") not in (None, "active"):
            continue
        den = _gio_vn(o["effective_to"]) if o.get("effective_to") else None
        if den and den < bay_gio:
            continue
        tu = _gio_vn(o["effective_from"]) if o.get("effective_from") else None
        if tu and tu > bay_gio:
            continue
        sm = o.get("summary") or {}
        thang = o.get("contract_length_months") or 1
        tong = _tien(sm.get("service_price"))
        tra_truoc = (o.get("billing_type_name") or "") == "Trả trước"
        thang_dong = round(tong / gia, 1) if tong and gia else None
        tang = round(thang - thang_dong, 1) if tra_truoc and thang_dong and thang - thang_dong > 0.05 else 0
        lua_chon.append({
            "hinh_thuc": o.get("billing_type_name") or "", "thang": thang, "tong": tong, "phi_lap": _tien(sm.get("fee_price")),
            "thiet_bi": _tien(sm.get("device_price")), "thang_dong": thang_dong, "tang": tang,
            "binh_quan": round(tong / thang) if tong else None,
            "qua": qua.get((thang, "tra-truoc" if tra_truoc else "tra-sau"), ""),
            "chinh_sach": o.get("name") or "", "ma": o.get("sale_platform_code") or "",
            "den": (den - timedelta(seconds=1)).strftime("%d/%m/%Y") if den else ""})
    lua_chon.sort(key=lambda z: (z["thang"], z["hinh_thuc"], z["chinh_sach"]))
    return {"ten": d.get("name") or "", "gia": gia, "phi_lap": _khoang(z["phi_lap"] for z in lua_chon),
            "thiet_bi": _khoang(z["thiet_bi"] for z in lua_chon), "mo_ta": [x.strip() for x in (d.get("card_description") or "").split("\n") if x.strip()],
            "lua_chon": lua_chon, "luc": utc_bay_gio()}


def chi_tiet_nhieu(tinh: int, phuong: int, goi: list[dict]) -> dict:
    """{code: chi tiết hoặc None} của nhiều gói, gọi song song. Mỗi gói đã nhớ tạm riêng nên lần xem lại phường đó không gọi nữa."""
    def mot(g):
        try:
            return g["code"], chi_tiet_goi(g["code"], tinh, phuong, g["gia"])
        except LoiGia:
            return g["code"], None
    with ThreadPoolExecutor(SO_LUONG_QUET) as ex:
        return dict(ex.map(mot, goi))


def khoa_nhom(g: dict) -> str:
    return f"{g['nhom']}|{g['khach']}"


def tieu_de_nhom(khoa: str) -> str:
    nhom, khach = khoa.split("|")
    return nhom + (" · doanh nghiệp" if khach == "doanh_nghiep" else (" · cá nhân" if nhom == "Internet" else ""))


def nhan_thoi_han(hinh_thuc: str, thang: int) -> str:
    return "Trả theo tháng" if _la_tra_sau(hinh_thuc, thang) else f"Trả trước {thang} tháng"


def _la_tra_sau(hinh_thuc: str, thang: int) -> bool:
    return thang == 1 and hinh_thuc != "Trả trước"


def chu_thanh_toan(tra_sau: bool, tra_truoc: list[int]) -> str:
    phan = (["trả theo tháng"] if tra_sau else []) + ([f"trả trước {' / '.join(str(t) for t in tra_truoc)} tháng"] if tra_truoc else [])
    return " · ".join(phan)


def phan_chung(goi: list[dict], chi_tiet: dict) -> dict:
    """Điều kiện chung của các gói cùng nhóm: những gì giống hệt nhau ở MỌI gói thì lôi ra ngoài, trong chi tiết từng gói chỉ ghi chỗ khác.

    Chỉ so khi có từ 2 gói lấy được chi tiết. Gồm: dòng mô tả + ưu đãi, các hình thức thanh toán, số tháng tặng, phí lắp đặt, thiết bị, hạn chính sách."""
    cac = [(g, chi_tiet[g["code"]]) for g in goi if chi_tiet.get(g["code"])]
    if len(cac) < 2:
        return {}
    ct = [c for _, c in cac]
    uu_dai = {g["uu_dai"] for g, _ in cac}
    han = [{(z["hinh_thuc"], z["thang"]) for z in c["lua_chon"]} for c in ct]
    dung_chung = set.intersection(*han)
    tang = {}
    for hinh_thuc, thang in dung_chung:
        v = {next(z["tang"] for z in c["lua_chon"] if (z["hinh_thuc"], z["thang"]) == (hinh_thuc, thang)) for c in ct}
        if len(v) == 1 and v != {0}:
            tang[thang] = v.pop()
    den = {z["den"] for c in ct for z in c["lua_chon"] if z["den"]}
    return {"uu_dai": uu_dai.pop() if len(uu_dai) == 1 else "",
            "tra_sau": any(_la_tra_sau(h, t) for h, t in dung_chung),
            "tra_truoc": sorted(t for h, t in dung_chung if not _la_tra_sau(h, t)), "tang": {str(k): v for k, v in tang.items()},
            "phi_lap": ct[0]["phi_lap"] if all(c["phi_lap"] == ct[0]["phi_lap"] for c in ct) else None,
            "thiet_bi": ct[0]["thiet_bi"] if all(c["thiet_bi"] == ct[0]["thiet_bi"] for c in ct) else None,
            "den": min(den, key=lambda x: (x[6:], x[3:5], x[:2])) if den else "", "so_den": len(den), "so_goi": len(cac)}


def chu_phi_hoa_mang(ct: dict | None) -> str:
    """Phí hòa mạng (phí lắp đặt) của gói: số tiền hoặc khoảng; "Miễn phí" khi dịch vụ không ghi khoản phí nào; rỗng nếu chưa có chi tiết."""
    if ct is None:
        return ""
    return chu_khoang(ct["phi_lap"]) or "Miễn phí"


def chu_khoang(kh: list | None) -> str:
    if not kh:
        return ""
    return chu_tien(kh[0]) if kh[0] == kh[1] else f"{chu_tien(kh[0])} - {chu_tien(kh[1])}"


def dong_chung(c: dict) -> list[str]:
    """Các dòng điều kiện chung để hiện ngoài danh sách (và trong chữ copy)."""
    if not c:
        return []
    d = []
    if c.get("tra_sau") or c.get("tra_truoc"):
        d.append("Thanh toán: " + chu_thanh_toan(c.get("tra_sau"), c.get("tra_truoc") or []))
    for thang, tang in sorted(c.get("tang", {}).items(), key=lambda x: int(x[0])):
        d.append(f"Trả trước {thang} tháng: tặng thêm {tang:g} tháng")
    if c.get("phi_lap"):
        d.append(f"Phí hòa mạng: {chu_khoang(c['phi_lap'])}")
    if c.get("thiet_bi"):
        d.append(f"Thiết bị đi kèm: {chu_khoang(c['thiet_bi'])}")
    if c.get("uu_dai"):
        d.append(c["uu_dai"])
    if c.get("den"):
        d.append(f"Chính sách áp dụng đến hết {c['den']}" if c.get("so_den") == 1 else f"Chính sách sớm nhất hết hạn {c['den']}")
    return d


def khac_biet(g: dict, ct: dict | None, c: dict) -> dict:
    """Những gì của gói này KHÔNG nằm trong phần chung của nhóm (nhóm chưa có phần chung thì là toàn bộ; chưa có chi tiết thì rỗng)."""
    if not ct:
        return {}
    c = c or {}
    kb = {}
    if g["uu_dai"] and g["uu_dai"] != c.get("uu_dai"):
        kb["uu_dai"] = g["uu_dai"]
    if ct["phi_lap"] and ct["phi_lap"] != c.get("phi_lap"):
        kb["phi_lap"] = ct["phi_lap"]
    if ct["thiet_bi"] and ct["thiet_bi"] != c.get("thiet_bi"):
        kb["thiet_bi"] = ct["thiet_bi"]
    return kb


# ------------------------------------------------------------------ so sánh hai khu vực
def so_sanh(goi_a: list[dict], goi_b: list[dict]) -> list[dict]:
    """Mỗi dòng một gói có ở ít nhất một bên. chenh = giá B - giá A (âm: B rẻ hơn)."""
    a, b = {g["id"]: g for g in goi_a}, {g["id"]: g for g in goi_b}
    dong = []
    for i in a.keys() | b.keys():
        g = a.get(i) or b[i]
        ga, gb = (a[i]["gia"] if i in a else None), (b[i]["gia"] if i in b else None)
        if i not in b:
            tt = "chi_a"
        elif i not in a:
            tt = "chi_b"
        elif ga is None or gb is None or ga == gb:
            tt = "bang"
        else:
            tt = "b_re" if gb < ga else "b_dat"
        chenh = gb - ga if ga is not None and gb is not None else None
        dong.append({"id": i, "ten": g["ten"], "nhom": g["nhom"], "khach": g["khach"], "gia_a": ga, "gia_b": gb,
                     "chenh": chenh, "pct": round(chenh * 100 / ga, 1) if chenh is not None and ga else None, "tinh_trang": tt})
    dong.sort(key=lambda r: _thu_tu({"nhom": r["nhom"], "khach": r["khach"], "gia": r["gia_a"] or r["gia_b"], "ten": r["ten"]}))
    return dong


def dem_so_sanh(dong: list[dict]) -> dict:
    d = {"b_re": 0, "b_dat": 0, "bang": 0, "chi_a": 0, "chi_b": 0}
    for r in dong:
        d[r["tinh_trang"]] += 1
    return d


# ------------------------------------------------------------------ quét giá cả tỉnh
def quet_tinh(tinh: int) -> dict:
    """Giá mọi gói ở mọi phường của một tỉnh (dạng JSON để người dùng giữ ở trình duyệt, máy chủ khác vẫn dùng được).

    Gọi song song `SO_LUONG_QUET` luồng; quá `HAN_QUET` giây thì trả phần đã quét được, phường chưa kịp ghi vào `loi`."""
    phuong = danh_sach_phuong(tinh)
    gia, goi, loi = {}, {}, []

    def mot(p):
        try:
            return p["id"], _doc_goi(tinh, p["id"])
        except LoiGia:                  # thỉnh thoảng một phường chậm: thử lại một lần trước khi bỏ
            return p["id"], _doc_goi(tinh, p["id"])

    ex = ThreadPoolExecutor(SO_LUONG_QUET)
    cho = {ex.submit(mot, p): p for p in phuong}
    xong = set()
    try:
        for f in as_completed(cho, timeout=HAN_QUET):
            xong.add(f)
            try:
                pid, ds = f.result()
            except LoiGia:
                loi.append(cho[f]["id"])
                continue
            gia[str(pid)] = {str(g["id"]): g["gia"] for g in ds}
            for g in ds:
                goi.setdefault(str(g["id"]), {"ten": g["ten"], "nhom": g["nhom"], "khach": g["khach"]})
    except HetGio:
        loi.extend(p["id"] for f, p in cho.items() if f not in xong)
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return {"tinh": tinh, "luc": utc_bay_gio().isoformat(), "phuong": {str(p["id"]): p["ten"] for p in phuong},
            "gia": gia, "goi": goi, "loi": [str(i) for i in loi]}


def vung_gia(du_lieu: dict, goi_id) -> list[dict]:
    """Nhóm phường theo giá của một gói: [{gia, phuong: [tên]}] giá tăng dần, phường không bán gói đó ở cuối (gia=None)."""
    nhom: dict = {}
    for pid, bang in du_lieu["gia"].items():
        nhom.setdefault(bang.get(str(goi_id)), []).append(du_lieu["phuong"].get(pid, pid))
    return [{"gia": g, "phuong": sorted(p)} for g, p in sorted(nhom.items(), key=lambda kv: (kv[0] is None, kv[0] or 0))]


def bien_dong(du_lieu: dict) -> list[dict]:
    """Mỗi gói một dòng: giá thấp nhất / cao nhất / số mức giá / số phường bán và không bán. Gói giá khác nhau nhiều xếp trước."""
    tong = len(du_lieu["gia"])
    dong = []
    for goi_id, tt in du_lieu["goi"].items():
        gia = [b.get(goi_id) for b in du_lieu["gia"].values() if b.get(goi_id) is not None]
        if not gia:
            continue
        dong.append({"id": goi_id, "ten": tt["ten"], "nhom": tt["nhom"], "khach": tt["khach"], "thap": min(gia), "cao": max(gia),
                     "chenh": max(gia) - min(gia), "so_muc": len(set(gia)), "ban": len(gia), "khong_ban": tong - len(gia)})
    dong.sort(key=lambda r: (-r["chenh"], -r["khong_ban"], r["ten"]))
    return dong


# ------------------------------------------------------------------ chữ để copy gửi khách
def van_ban_bao_gia(khu_vuc: str, goi: list[dict], luc, chung: dict | None = None, chi_tiet: dict | None = None) -> str:
    """Chữ để dán gửi khách: theo nhóm, mỗi nhóm có dòng điều kiện chung (nếu đã có) rồi tới từng gói."""
    chung = chung or {}
    dong = [f"BẢNG GIÁ FPT TELECOM · {khu_vuc}", f"(Cập nhật {chu_gio_vn(luc)} · giá đã gồm VAT)"]
    khoa_cu = None
    for g in goi:
        khoa = khoa_nhom(g)
        if khoa != khoa_cu:
            dong += ["", tieu_de_nhom(khoa).upper()]
            dong += [f"  - {d}" for d in dong_chung(chung.get(khoa, {}))]
            khoa_cu = khoa
        don_vi = DON_VI_GIA.get(g["nhom"])
        phan = [f"{g['ten']}: {chu_tien(g['gia'])}" + (f" ({don_vi})" if don_vi else "/tháng")]
        if g["toc_do"]:
            phan.append(f"tốc độ {g['toc_do']}")
        phi = chu_phi_hoa_mang((chi_tiet or {}).get(g["code"]) if chi_tiet else None)
        if phi and g["nhom"] != "Camera":
            phan.append("miễn phí hòa mạng" if phi == "Miễn phí" else f"phí hòa mạng {phi}")
        if g["uu_dai"] and g["uu_dai"] != chung.get(khoa, {}).get("uu_dai"):
            phan.append(g["uu_dai"])
        dong.append("• " + " · ".join(phan))
    return "\n".join(dong)


def van_ban_so_sanh(ten_a: str, ten_b: str, dong: list[dict], luc) -> str:
    kq = [f"SO GIÁ FPT TELECOM: {ten_a} và {ten_b}", f"(Cập nhật {chu_gio_vn(luc)} · giá đã gồm VAT)", ""]
    for r in dong:
        if r["tinh_trang"] == "chi_a":
            phan = f"chỉ bán ở {ten_a} ({chu_tien(r['gia_a'])})"
        elif r["tinh_trang"] == "chi_b":
            phan = f"chỉ bán ở {ten_b} ({chu_tien(r['gia_b'])})"
        elif r["tinh_trang"] == "bang":
            phan = f"{chu_tien(r['gia_a'])} (như nhau)"
        else:
            phan = f"{ten_a} {chu_tien(r['gia_a'])} · {ten_b} {chu_tien(r['gia_b'])}"
        kq.append(f"• {r['ten']}: {phan}")
    return "\n".join(kq)
