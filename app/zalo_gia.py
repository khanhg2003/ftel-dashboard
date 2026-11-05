"""Bot Zalo TRA CỨU GIÁ gói cước FPT (chốt 05/11/2026): sale gõ "Giá cước Giga ở phường Nam Nha Trang, Khánh Hòa" trong nhóm
(@bot) hoặc nhắn riêng, bot trả giá lấy THẲNG từ `app/gia_fpt.py` (không gọi fpt.vn bằng đường khác, không tự tính phí).

Vì sao một bot riêng (`ZALO_GIA_TOKEN`): một bot chỉ gắn được MỘT webhook, mà bot Bản tin đang dùng webhook của nó để nhận người nhận mới.
Tách câu hỏi bằng quy tắc (không AI): bỏ dấu, khớp tên tỉnh / phường / gói theo cụm từ trọn vẹn. Mơ hồ thì hỏi lại bằng danh sách
đánh số; câu đang hỏi dở nằm ở database (`ZaloGiaHoiLai`, hết hạn 10 phút) vì Vercel chạy nhiều máy. Mỗi tin chỉ xử lý MỘT lần
(`ZaloGiaTin.ma_tin` duy nhất) nên Zalo gửi lại sự kiện cũng không trả lời hai lần. Chỉ chat có mã trong `ZALO_GIA_CHO_PHEP`
được trả lời giá. KHÔNG lưu nội dung tin; nhật ký chỉ ghi mã chat + gói + phường. Phần dựng chữ ở `app/zalo_gia_nd.py`.
"""
from __future__ import annotations

import difflib
import hashlib
import hmac
import json
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, TimeoutError as HetGio
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app import gia_fpt as gf
from app import gia_fpt_nhom as gn
from app import zalo_bot
from app import zalo_gia_ai as za_ai
from app import zalo_gia_nd as nd
from app.auth import ghi_log
from app.config import SECRET_KEY
from app.db import engine, session_scope
from app.models import ZaloGiaHoiLai, ZaloGiaTin
from app.thoi_gian import utc_bay_gio

DUONG_DAN = "/api/zalo-gia/webhook"
HAN_HOI_LAI = timedelta(minutes=10)
TOI_DA_CAU_PHUT = 10              # số câu mỗi chat trong 1 phút
HAN_TRA_LOI = 40                  # giây; Vercel cho 60
TOI_DA_LUA_CHON = 8
TOI_DA_GOI_CHI_TIET = 3
SO_LUONG = 8
GIOI_HAN_LOG = 500

_LOAI_PHUONG = ("thi tran", "dac khu", "phuong", "xa", "tt")
_BI_DANH = {"hcm": "ho chi minh", "tphcm": "ho chi minh", "sai gon": "ho chi minh", "hn": "ha noi", "quang nam": "da nang"}  # Quảng Nam cũ nằm trong Đà Nẵng
_TU_CHUNG = set("gia cuoc goi internet combo o tai phuong xa thi tran dac khu tinh thanh pho tp cho la bao nhieu the nao oi nhe a vay giup "
                "minh em anh chi toi xem tra cuu hoi bot ban dang hien nay cac tat ca va cua co khong gi vui long lam on may tien phi "
                "uu dai ap dung".split())
# Chủ app chốt 05/11/2026: bot chỉ hiện ba nhóm dưới đây, theo thứ tự này. Muốn bật lại nhóm nào thì bỏ khỏi NHOM_AN.
NHOM_AN = {"Internet game thủ", "Internet doanh nghiệp", "Combo Internet Camera"}
NHOM_THU_TU = ["Internet cá nhân", "Internet gia đình", "Combo Internet + V.VIP"]
# Nhóm V.VIP chỉ giữ hai combo này (chủ app chốt 05/11/2026; bỏ Meta, Lux 800 và mọi combo V.VIP khác). Muốn thêm combo thì thêm mã vào đây.
NHOM_VVIP = "Combo Internet + V.VIP"
COMBO_VVIP_GIU = {"combo-internet-giga-vvip-lite", "combo-internet-sky-vvip-lite"}
_NHOM_TU_KHOA = [(tk, nhan) for tk, nhan in [
    ("doanh nghiep", "Internet doanh nghiệp"), ("camera", "Combo Internet Camera"), ("vvip", "Combo Internet + V.VIP"),
    ("v vip", "Combo Internet + V.VIP"), ("gia dinh", "Internet gia đình"), ("game thu", "Internet game thủ"),
    ("game", "Internet game thủ"), ("ca nhan", "Internet cá nhân")] if nhan not in NHOM_AN]


def dam_bao_bang() -> None:
    for b in (ZaloGiaTin, ZaloGiaHoiLai):
        try:
            b.__table__.create(bind=engine, checkfirst=True)
        except Exception:
            pass


dam_bao_bang()


# ------------------------------------------------------------------ khoá, quyền
def khoa_webhook() -> str:
    """HMAC-SHA256(APP_SECRET_KEY, "zalo-gia-webhook") dạng hex: không phải lưu thêm gì."""
    return hmac.new(SECRET_KEY.encode(), b"zalo-gia-webhook", hashlib.sha256).hexdigest()


def khoa_dung(khoa: str | None) -> bool:
    return hmac.compare_digest((khoa or "").encode(), khoa_webhook().encode())


def url_webhook() -> str | None:
    goc = (os.environ.get("APP_URL") or "").strip().rstrip("/")
    return f"{goc}{DUONG_DAN}" if goc else None


def cho_phep(chat_id: str) -> bool:
    ds = {x.strip() for x in re.split(r"[,;\s]+", os.environ.get("ZALO_GIA_CHO_PHEP") or "") if x.strip()}
    return str(chat_id) in ds


# ------------------------------------------------------------------ chuẩn hoá chữ
def bo_dau(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def chuan(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", bo_dau(s))).strip()


def _co_cum(chuoi: str, cum: str) -> bool:
    return bool(cum) and f" {cum} " in f" {chuoi} "


def _bo_cum(chuoi: str, cum: str) -> str:
    return re.sub(r"\s+", " ", re.sub(rf"(?<![a-z0-9]){re.escape(cum)}(?![a-z0-9])", " ", chuoi)).strip() if cum else chuoi


def bo_mention(text: str) -> str:
    """Bỏ phần @tên-bot khỏi câu (tên bot có dấu cách thì đặt ZALO_GIA_TEN_BOT cho đúng)."""
    text = text or ""
    ten = (os.environ.get("ZALO_GIA_TEN_BOT") or "").strip().lstrip("@")
    if ten:
        text = re.sub(r"@\s*" + re.escape(ten), " ", text, flags=re.I)
    return re.sub(r"@\S+", " ", text).strip()


# ------------------------------------------------------------------ đọc sự kiện Zalo
def doc_tin(payload) -> dict | None:
    """Tin chữ người thật gửi -> {chat_id, loai_chat, nguoi_id, ma_tin, text}; không đọc được thì None. Chịu cả dạng bọc trong "result"."""
    p = payload.get("result") if isinstance(payload, dict) and isinstance(payload.get("result"), dict) else payload
    msg = p.get("message") if isinstance(p, dict) else None
    ev = str(p.get("event_name") or "") if isinstance(p, dict) else ""
    if not isinstance(msg, dict) or (ev.startswith("message.") and ".text." not in ev):     # ảnh, nhãn dán... không phải câu hỏi
        return None
    chat, nguoi = msg.get("chat"), msg.get("from")
    chat_id = str((chat or {}).get("id") or "").strip()[:80] if isinstance(chat, dict) else ""
    text = msg.get("text")
    if not chat_id or not isinstance(text, str) or not text.strip():
        return None
    nguoi = nguoi if isinstance(nguoi, dict) else {}
    ma = str(msg.get("message_id") or "").strip()
    nguoi_id = str(nguoi.get("id") or chat_id)[:80]
    return {"chat_id": chat_id, "loai_chat": str(chat.get("chat_type") or "").upper(), "nguoi_id": nguoi_id,
            "la_bot": bool(nguoi.get("is_bot")), "text": text,
            "ma_tin": (ma or hashlib.sha256(f"{chat_id}|{nguoi_id}|{text}|{msg.get('date')}".encode()).hexdigest())[:120]}


def _la_su_kien_chu(payload) -> bool:
    """Sự kiện lẽ ra là tin chữ (nên đọc được): ảnh, nhãn dán... thì không cần ghi nhật ký."""
    p = payload.get("result") if isinstance(payload, dict) and isinstance(payload.get("result"), dict) else payload
    return not isinstance(p, dict) or str(p.get("event_name") or "message.text.received") == "message.text.received"


def _ghi_payload_la(payload) -> None:
    """Payload không đọc được: ghi nhật ký tối đa 500 ký tự (đã xoá token) để chủ app gửi lại cho người sửa code."""
    try:
        chu = json.dumps(payload, ensure_ascii=False, default=str)
        for t in (zalo_bot.token_gia(), os.environ.get("ZALO_BOT_TOKEN") or ""):
            chu = chu.replace(t, "***") if t else chu
        ghi_log("zalo_gia_la", chu[:GIOI_HAN_LOG])
    except Exception:
        pass


# ------------------------------------------------------------------ tìm tỉnh / phường / gói
def _tach_loai(n: str) -> tuple[str, str]:
    for loai in _LOAI_PHUONG:
        if n.startswith(loai + " "):
            return loai, n[len(loai) + 1:]
    return "", n


def _tim_tinh(q: str, ds_tinh: list[dict]) -> tuple[int | None, str]:
    """(mã tỉnh, cụm chữ đã khớp trong câu): cụm dài nhất thắng."""
    tot: tuple[int, int, str] | None = None
    for t in ds_tinh:
        sach = re.sub(r"^(tinh|thanh pho|tp) ", "", chuan(t["ten"]))
        cum = [sach] + [k for k, v in _BI_DANH.items() if v == sach]
        for c in cum:
            if _co_cum(q, c) and (tot is None or len(c) > len(tot[2])):
                tot = (t["id"], len(c), c)
    return (tot[0], tot[2]) if tot else (None, "")


def _nap_phuong(ds_tinh: list[dict], tinh: int | None) -> list[dict]:
    ten = {t["id"]: t["ten"] for t in ds_tinh}

    def mot(i):
        try:
            return i, gf.danh_sach_phuong(i)
        except gf.LoiGia:
            return i, None
    with ThreadPoolExecutor(SO_LUONG) as ex:
        kq = list(ex.map(mot, [tinh] if tinh else list(ten)))
    if all(ds is None for _, ds in kq):
        raise gf.LoiGia("Không lấy được danh sách phường.")
    ra = []
    for i, ds in kq:
        for p in ds or []:
            loai, sach = _tach_loai(chuan(p["ten"]))
            ra.append({"tinh": i, "tinh_ten": ten.get(i, ""), "id": p["id"], "ten": p["ten"], "loai": loai, "sach": sach})
    return ra


def _khop_phuong_tron(q: str, wards: list[dict]) -> list[dict]:
    """Phường có tên nằm trọn trong câu; tên dài hơn thắng tên ngắn nằm trong nó, gõ rõ "phường/xã" thắng, rồi tên nhiều chữ hơn."""
    co = [w for w in wards if len(w["sach"]) >= 2 and not w["sach"].isdigit() and _co_cum(q, w["sach"])]
    co = [w for w in co if not any(o["sach"] != w["sach"] and _co_cum(o["sach"], w["sach"]) for o in co)]
    if len(co) > 1:
        goi_ro = [w for w in co if w["loai"] and _co_cum(q, f"{w['loai']} {w['sach']}")]
        if goi_ro:
            return goi_ro
        dai = max(len(w["sach"].split()) for w in co)
        co = [w for w in co if len(w["sach"].split()) == dai]
    return co


def _cum_phuong_go(q: str) -> list[str]:
    m = re.search(r"\b(?:phuong|xa|thi tran|dac khu)\s+(.+)$", q)
    return m.group(1).split() if m else []


def _khop_phuong_gan(cum: list[str], wards: list[dict]) -> list[dict]:
    """Gõ thiếu / sai chút: cụm là một phần tên phường (thử từ cả cụm bớt dần), hoặc gần giống (difflib) -> luôn HỎI LẠI, không tự chọn."""
    for n in range(len(cum), 0, -1):
        c = " ".join(cum[:n])
        co = [w for w in wards if c in w["sach"]]
        if co:
            return co
    sach = [w["sach"] for w in wards]
    gan = set(difflib.get_close_matches(" ".join(cum), sach, n=5, cutoff=0.75))
    return [w for w in wards if w["sach"] in gan]


def nhom_hien(goi: list[dict], ch: dict | None = None) -> dict[str, list[dict]]:
    """Các nhóm bot được hiện, mỗi gói CHỈ MỘT lần: gói nằm ở nhiều nhóm (Sky F1, Combo Lux 800...) giữ ở nhóm đứng trước theo `NHOM_THU_TU`,
    nhóm hết gói thì bỏ. Trong nhóm giữ thứ tự giá thấp -> cao của `gia_fpt_nhom`. Gói chỉ thuộc nhóm bị ẩn thì không hiện và không khớp tên."""
    nhom = {k: v for k, v in gn.chia_nhom(goi, ch).items() if k not in NHOM_AN}
    thu_tu = [k for k in NHOM_THU_TU if k in nhom] + [k for k in nhom if k not in NHOM_THU_TU]
    da, ra = set(), {}
    for k in thu_tu:
        moi = [g for g in nhom[k] if g["code"] not in da and (k != NHOM_VVIP or g["code"] in COMBO_VVIP_GIU)]
        da |= {g["code"] for g in moi}
        if moi:
            ra[k] = moi
    return ra


def _ten_goi(g: dict) -> list[str]:
    """Tên gói bỏ chữ Internet / Gói / Combo và đuôi V.VIP: "Combo Giga - V.VIP" và "Gói Giga" cùng ra ["giga"], phân biệt bằng `_la_combo`."""
    t = [x for x in chuan(g["ten"]).split() if x not in ("internet", "goi", "combo")]
    while t and t[-1] in ("v", "vip", "vvip"):
        t.pop()
    return t


def _la_combo(g: dict) -> bool:
    return chuan(g["ten"]).startswith("combo")


def _uu_tien_combo(ds: list[dict], combo: bool) -> list[dict]:
    """Người hỏi có nói "combo" / V.VIP thì chỉ lấy combo; không nói thì bỏ combo (hỏi "giga" là Gói Giga). Không còn gì thì giữ nguyên."""
    loc = [g for g in ds if _la_combo(g) == combo]
    return loc or ds


def _khop_goi(tokens: list[str], goi: list[dict], combo: bool = False) -> list[dict]:
    chuoi = " ".join(tokens)
    co = []
    for g in goi:
        t = _ten_goi(g)
        if t and (_co_cum(chuoi, " ".join(t)) or "".join(t) in tokens):
            co.append(g)
    co = _uu_tien_combo(co, combo)
    return [g for g in co if not any(o is not g and len(_ten_goi(o)) > len(_ten_goi(g)) and _co_cum(" ".join(_ten_goi(o)), " ".join(_ten_goi(g)))
                                    for o in co)]


def _tach_nhom(q: str) -> tuple[str, list[str]]:
    """(câu đã bỏ từ khoá nhóm, các nhóm được nhắc tới: "doanh nghiệp", "camera", "V.VIP"...)."""
    ra = []
    for tk, nhan in _NHOM_TU_KHOA:
        if _co_cum(q, tk):
            q = _bo_cum(q, tk)
            if nhan not in ra:
                ra.append(nhan)
    return q, ra


# ------------------------------------------------------------------ giải câu hỏi
def _hoi(tin: str, **trang_thai) -> dict:
    return {"tin": [tin], "hoi": trang_thai, "nhat_ky": None}


def _thieu_phuong(ctx: dict, tinh_ten: str, bo: list[str]) -> dict:
    ve = f" ở {tinh_ten}" if tinh_ten else ""
    return _hoi(f"Anh/chị cho mình biết phường/xã nào{ve}? Ví dụ: giá Giga phường Hải Châu, Đà Nẵng",
                buoc="cho_phuong", q=ctx["q"], bo=bo, tinh=ctx.get("tinh"))


def _tim_vi_tri(ctx: dict, ds_tinh: list[dict]) -> tuple[dict | None, dict | None, list[str]]:
    """(phường đã chọn, câu trả lời nếu phải hỏi / báo, các cụm đã dùng để chỉ vị trí)."""
    q, bo, tinh = ctx["q"], list(ctx.get("bo") or []), ctx.get("tinh")
    if tinh is None:
        tinh, cum = _tim_tinh(q, ds_tinh)
        if cum:
            bo.append(cum)
    ctx = {**ctx, "tinh": tinh}
    tinh_ten = next((t["ten"] for t in ds_tinh if t["id"] == tinh), "")
    q_phuong = q
    for c in bo:
        q_phuong = _bo_cum(q_phuong, c)
    wards = _nap_phuong(ds_tinh, tinh)
    co = _khop_phuong_tron(q_phuong, wards)
    if len(co) == 1:
        return co[0], None, bo + [co[0]["sach"]]
    if len(co) > 1:
        return None, _chon_phuong(ctx, co, bo), bo
    cum = _cum_phuong_go(q_phuong)
    if not cum:
        return None, _thieu_phuong(ctx, tinh_ten, bo), bo
    gan = _khop_phuong_gan(cum, wards)
    if not gan:
        return None, {"tin": [f"Mình chưa tìm thấy phường/xã “{' '.join(cum)}”" + (f" ở {tinh_ten}" if tinh_ten else "")
                              + ". Anh/chị kiểm tra lại tên (gõ không dấu cũng được) hoặc thêm tên tỉnh nhé."], "hoi": None, "nhat_ky": None}, bo
    return None, _chon_phuong(ctx, gan, bo + [" ".join(cum)]), bo


def _chon_phuong(ctx: dict, co: list[dict], bo: list[str]) -> dict:
    ds = [{"tinh": w["tinh"], "phuong": w["id"], "sach": w["sach"], "nhan": f"{w['ten']}, {w['tinh_ten']}"} for w in co[:TOI_DA_LUA_CHON]]
    return _hoi(nd.lua_chon("Anh/chị muốn hỏi phường/xã nào?", [d["nhan"] for d in ds], max(0, len(co) - TOI_DA_LUA_CHON)),
                buoc="chon_phuong", q=ctx["q"], bo=bo, tinh=ctx.get("tinh"), ds=ds)


def giai(ctx: dict) -> dict:
    """Câu hỏi + phần đã biết (`tinh`, `phuong`, `goi`, `bo`) -> {"tin": [chữ...], "hoi": trạng thái hỏi lại | None, "nhat_ky": (gói, phường) | None}."""
    ds_tinh = gf.danh_sach_tinh()
    ten_tinh = {t["id"]: t["ten"] for t in ds_tinh}
    bo = list(ctx.get("bo") or [])
    phuong, tinh = ctx.get("phuong"), ctx.get("tinh")
    if phuong is None:
        w, ket, bo = _tim_vi_tri(ctx, ds_tinh)
        if ket:
            return ket
        phuong, tinh, ten_phuong = w["id"], w["tinh"], w["ten"]
    else:
        ten_phuong = ctx.get("ten_phuong") or ""
    q = ctx["q"]
    for c in bo:
        q = _bo_cum(q, c)
    return _tra_goi({**ctx, "q": q, "bo": bo}, tinh, phuong, f"{ten_phuong}, {ten_tinh.get(tinh, '')}".strip(", "))


def _tra_goi(ctx: dict, tinh: int, phuong: int, vi_tri: str) -> dict:
    res = gf.goi_theo_phuong(tinh, phuong)
    nhom_dep = nhom_hien(res["goi"], gn.cau_hinh())
    goi = [g for gs in nhom_dep.values() for g in gs]
    if not goi:
        return {"tin": [f"Hiện chưa thấy gói Internet nào đang bán ở {vi_tri}."], "hoi": None, "nhat_ky": None}
    chan = nd.chan_trang(res["luc"], res.get("cu", False))
    q, nhom_hoi = _tach_nhom(ctx["q"])
    tokens = [t for t in q.split() if t not in _TU_CHUNG]
    combo = "combo" in q.split() or NHOM_VVIP in nhom_hoi
    chon = [g for g in goi if g["code"] in (ctx.get("goi") or [])] or _khop_goi(q.split(), goi, combo)
    if not chon and tokens:
        gan = _uu_tien_combo([g for g in goi if set(_ten_goi(g)) & set(tokens)], combo)
        if len(gan) == 1:
            chon = gan
        elif gan:
            ds = [{"code": g["code"], "nhan": f"{g['ten']} - {gf.chu_tien(g['gia'])}/tháng"} for g in gan[:TOI_DA_LUA_CHON]]
            return _hoi(nd.lua_chon(f"Anh/chị muốn xem gói nào ở {vi_tri}?", [d["nhan"] for d in ds], max(0, len(gan) - TOI_DA_LUA_CHON)),
                        buoc="chon_goi", q=ctx["q"], bo=ctx.get("bo"), tinh=tinh, phuong=phuong, ten_phuong=vi_tri.split(",")[0], ds=ds)
    if len(chon) > TOI_DA_GOI_CHI_TIET:
        chon = chon[:TOI_DA_GOI_CHI_TIET]
    if chon:
        return _chi_tiet(chon, goi, tinh, phuong, vi_tri, chan)
    return _liet_ke(nhom_dep, vi_tri, chan, nhom_hoi, tokens)


def _chi_tiet(chon: list[dict], goi: list[dict], tinh: int, phuong: int, vi_tri: str, chan: list) -> dict:
    ct = gf.chi_tiet_nhieu(tinh, phuong, chon)
    khoi = [nd.chi_tiet(g, ct.get(g["code"]), vi_tri) for g in chon]
    ten_chon = {g["code"] for g in chon}
    gan = [g for g in goi if g["code"] not in ten_chon and any(" ".join(_ten_goi(c)) in " ".join(_ten_goi(g)) for c in chon)]
    if gan:
        khoi.append([nd.dong_chu("Gói tương tự (gõ tên đầy đủ để xem):")] + nd.danh_sach_don(gan[:4]))
    khoi.append(chan)
    return {"tin": nd.chia_tin(khoi), "hoi": None, "nhat_ky": (", ".join(g["ten"] for g in chon), vi_tri)}


def _liet_ke(nhom: dict[str, list[dict]], vi_tri: str, chan: list, nhom_hoi: list[str], tokens: list[str]) -> dict:
    nhom = {k: v for k, v in nhom.items() if k in nhom_hoi} or nhom
    tieu_de = (f"Mình chưa thấy gói “{' '.join(tokens)}” ở {vi_tri}. Các gói đang bán:" if tokens else "")
    khoi = nd.danh_sach(nhom, vi_tri, tieu_de) + [chan]
    return {"tin": nd.chia_tin(khoi), "hoi": None, "nhat_ky": ("danh sách", vi_tri)}


# ------------------------------------------------------------------ trạng thái hỏi lại, chống trùng, giới hạn tốc độ (database)
def _nhan_tin(tin: dict) -> int | None:
    """Ghi tin vào sổ; None nếu tin này đã xử lý rồi (Zalo gửi lại). Trả về số câu của chat trong 1 phút (kể cả tin này)."""
    bay_gio = utc_bay_gio()
    try:
        with session_scope() as s:
            s.add(ZaloGiaTin(ma_tin=tin["ma_tin"], chat_id=tin["chat_id"], luc=bay_gio))
    except IntegrityError:
        return None
    with session_scope() as s:
        n = s.execute(select(func.count()).select_from(ZaloGiaTin).where(
            ZaloGiaTin.chat_id == tin["chat_id"], ZaloGiaTin.luc >= bay_gio - timedelta(minutes=1))).scalar() or 0
        s.execute(delete(ZaloGiaTin).where(ZaloGiaTin.luc < bay_gio - timedelta(hours=1)))
        s.execute(delete(ZaloGiaHoiLai).where(ZaloGiaHoiLai.het_han < bay_gio))
    return int(n)


def _khoa_hoi(tin: dict) -> str:
    return f"{tin['chat_id']}:{tin['nguoi_id']}"[:180]


def doc_hoi_lai(khoa: str) -> dict | None:
    with session_scope() as s:
        r = s.execute(select(ZaloGiaHoiLai).where(ZaloGiaHoiLai.khoa == khoa)).scalar_one_or_none()
        if not r or r.het_han < utc_bay_gio():
            return None
        try:
            return json.loads(r.du_lieu)
        except ValueError:
            return None


def luu_hoi_lai(khoa: str, trang_thai: dict | None) -> None:
    """Lưu câu đang hỏi dở (None = xoá). Hai tin tới cùng lúc: bên nào ghi sau thắng."""
    for _ in range(2):
        try:
            with session_scope() as s:
                r = s.execute(select(ZaloGiaHoiLai).where(ZaloGiaHoiLai.khoa == khoa)).scalar_one_or_none()
                if trang_thai is None:
                    if r:
                        s.delete(r)
                    return
                du_lieu, het = json.dumps(trang_thai, ensure_ascii=False), utc_bay_gio() + HAN_HOI_LAI
                if r:
                    r.du_lieu, r.het_han = du_lieu, het
                else:
                    s.add(ZaloGiaHoiLai(khoa=khoa, du_lieu=du_lieu, het_han=het))
            return
        except IntegrityError:
            continue


# ------------------------------------------------------------------ một lượt hỏi - đáp
def _lenh(q: str) -> str | None:
    if q in ("help", "start", "tro giup", "huong dan", "gioi thieu") or q.startswith(("help ", "huong dan ")) \
            or q.endswith(" huong dan"):
        return nd.HUONG_DAN
    return None


def tra_loi(text: str, hoi_lai: dict | None) -> dict:
    """Câu gõ + câu đang hỏi dở (nếu có) -> {"tin", "hoi", "nhat_ky"}. Không ghi database, không gửi tin."""
    q_goc = bo_mention(text)
    q = chuan(q_goc)
    if not q:
        return {"tin": [nd.HUONG_DAN], "hoi": None, "nhat_ky": None}
    if (huong_dan := _lenh(q)):
        return {"tin": [huong_dan], "hoi": None, "nhat_ky": None}
    if re.fullmatch(r"\d{1,2}", q):
        return _chon_so(int(q), hoi_lai)
    ctx = {"q": q}
    if hoi_lai and hoi_lai.get("buoc") == "cho_phuong" and not _co_cum(q, "gia") and not _co_cum(q, "cuoc"):
        ctx = {"q": f"{hoi_lai['q']} {q}", "bo": hoi_lai.get("bo"), "tinh": hoi_lai.get("tinh")}
    return _chay(ctx)


def _chon_so(n: int, hoi_lai: dict | None) -> dict:
    ds = (hoi_lai or {}).get("ds")
    if not hoi_lai or not ds:
        return {"tin": ["Mình chưa có câu hỏi nào đang chờ anh/chị chọn. Gõ /help để xem cách hỏi."], "hoi": None, "nhat_ky": None}
    if not 1 <= n <= len(ds):
        return {"tin": [f"Số này không có trong danh sách. Anh/chị trả lời từ 1 đến {len(ds)}, hoặc gõ câu hỏi mới."], "hoi": hoi_lai, "nhat_ky": None}
    d = ds[n - 1]
    if hoi_lai["buoc"] == "chon_phuong":
        ctx = {"q": hoi_lai["q"], "bo": (hoi_lai.get("bo") or []) + [d["sach"]], "tinh": d["tinh"], "phuong": d["phuong"],
               "ten_phuong": d["nhan"].split(",")[0]}
    else:
        ctx = {"q": hoi_lai["q"], "bo": hoi_lai.get("bo"), "tinh": hoi_lai["tinh"], "phuong": hoi_lai["phuong"],
               "ten_phuong": hoi_lai.get("ten_phuong"), "goi": [d["code"]]}
    return _chay(ctx)


def _chay(ctx: dict) -> dict:
    """Chạy `giai` có thời hạn: fpt.vn chậm thì báo "thử lại sau ít giây" thay vì treo (kết quả đã tải vẫn được nhớ cho lần sau)."""
    ex = ThreadPoolExecutor(1)
    try:
        return ex.submit(giai, ctx).result(timeout=HAN_TRA_LOI)
    except HetGio:
        return {"tin": ["Đang lấy giá từ fpt.vn, hơi lâu một chút. Anh/chị gõ lại câu hỏi sau ít giây nhé."], "hoi": None, "nhat_ky": None}
    except gf.LoiGia:
        return {"tin": ["Chưa lấy được giá từ fpt.vn lúc này. Anh/chị thử lại sau ít phút nhé."], "hoi": None, "nhat_ky": None}
    finally:
        ex.shutdown(wait=False)


def _gui(chat_id: str, tin: list) -> None:
    """Tin có kiểu chữ (`.kieu`) mà Zalo từ chối thì tự gửi lại bản chữ trơn."""
    token = zalo_bot.token_gia()
    for t in tin:
        try:
            zalo_bot.gui_tin_du_phong(chat_id, t, token=token)
        except zalo_bot.LoiZalo:
            return


def _tra_loi_dinh_tuyen(tin: dict, khoa: str) -> dict:
    """Câu giá đi đường quy tắc cũ (không AI); câu số liệu đi trợ lý AI bằng tài khoản admin đại diện (`zalo_gia_ai`). Mơ hồ: giá trước."""
    text, hoi_lai = tin["text"], doc_hoi_lai(khoa)
    q_goc = bo_mention(text)
    huong = za_ai.huong(chuan(q_goc), hoi_lai, za_ai.dang_hoi(khoa) if za_ai.bat() else False)
    if huong == "ai_mem" and za_ai.tai_khoan() is None:
        huong = "gia"
    kq = tra_loi(text, hoi_lai) if huong in ("gia", "gia_roi_ai") else None
    if huong == "gia_roi_ai" and not za_ai.gia_khong_ra_gi(kq):
        huong = "gia"
    if kq is not None and huong != "gia_roi_ai":
        luu_hoi_lai(khoa, kq["hoi"])
        return kq
    luu_hoi_lai(khoa, None)
    return {"tin": za_ai.tra_loi(tin["chat_id"], khoa, q_goc), "hoi": None, "nhat_ky": None}


def _xu_ly(payload) -> None:
    tin = doc_tin(payload)
    if os.environ.get("ZALO_GIA_GHI_LOG") == "1" or (not tin and _la_su_kien_chu(payload)):
        _ghi_payload_la(payload)
    if not tin:
        return
    if tin["la_bot"] or not zalo_bot.token_gia():
        return
    so_cau = _nhan_tin(tin)
    if so_cau is None:
        return
    chat_id = tin["chat_id"]
    if so_cau > TOI_DA_CAU_PHUT:
        if so_cau == TOI_DA_CAU_PHUT + 1:
            _gui(chat_id, ["Anh/chị hỏi nhanh quá, đợi khoảng một phút rồi hỏi tiếp nhé."])
        return
    if chuan(bo_mention(tin["text"])) == "id":
        _gui(chat_id, [f"Mã chat này: {chat_id}"])
        return
    if not cho_phep(chat_id):
        _gui(chat_id, [nd.CHUA_CAP_QUYEN.format(id=chat_id)])
        return
    khoa = _khoa_hoi(tin)
    kq = _tra_loi_dinh_tuyen(tin, khoa)
    _gui(chat_id, kq["tin"])
    if kq["nhat_ky"]:
        ghi_log("zalo_gia", f"chat {chat_id}: gói={kq['nhat_ky'][0]}; phường={kq['nhat_ky'][1]}")


def xu_ly_su_kien(payload) -> None:
    """Không bao giờ ném lỗi: webhook phải trả 200 để Zalo khỏi gửi lại."""
    try:
        _xu_ly(payload)
    except Exception:
        pass
