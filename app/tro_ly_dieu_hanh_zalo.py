"""Kênh ZALO của Trợ lý điều hành: gửi đề xuất / nhắc / báo cấp trên / kết quả kiểm chứng bằng bot Bản tin sẵn có (`zalo_bot`, người nhận lấy từ
`ban_tin_nguoi_nhan`), và nhận lệnh trả lời qua webhook của Bản tin (`ban_tin_cho_duyet.xu_ly_su_kien` gọi vào `xu_ly_webhook`).

Lệnh (gõ có dấu hay không đều được): `dong y <số> [A|B|C]`, `sua <số> <ý kiến>`, `bac <số> <lý do>`, `quyet dinh` (liệt kê đề xuất đang chờ mình).
Chỉ người nhận quyết đúng phần của mình hoặc Ban Giám đốc quyết được; người ngoài danh sách bị bỏ qua (luồng thêm người nhận cũ vẫn chạy như trước). Quyết chỉ GHI SỔ,
không tự thực thi gì khác. Hàm gửi chỉ chạy khi người gọi bật (`gui=True` ở vòng chạy); công tắc `bat` tắt thì webhook không đọc lệnh nào. Mỗi tin gửi đúng một lần nhờ
các cột `da_gui_luc`, `nhac_luc`, `leo_thang_luc`, `bao_kiem_chung_luc` của sổ.
"""
from __future__ import annotations

import os
import unicodedata
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime

from app import ban_tin as bt, tro_ly_dieu_hanh as td, tro_ly_dieu_hanh_so as so, zalo_bot
from app.thoi_gian import chu_gio_vn, utc_bay_gio

XANH_DUONG, CAM, DO, XAM = "c_0072bc", "c_f27806", "c_db342e", "c_667789"
GIOI_HAN = bt.TOI_DA_KY_TU
LOAI_CHAT_RIENG = ("PRIVATE", "USER")
CUA_LENH = {"dong y": "dong_y", "sua": "sua", "bac": "bac", "xem": "xem", "bao cao": "bao_cao", "quyet dinh": "danh_sach"}
TEN_KHOI = {"kd": "KINH DOANH", "dvkh": "DỊCH VỤ KHÁCH HÀNG", "chung": "CHUNG"}
MUC_CHU = {"cao": "Cao", "trung_binh": "Trung bình", "thap": "Thấp"}
TOI_DA_DONG = 10                          # số đề xuất ghi riêng từng dòng trong tin tổng hợp, còn lại gộp thành một dòng


def bo_dau(chu: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", chu.replace("đ", "d").replace("Đ", "D")) if unicodedata.category(ch) != "Mn").lower()


# ------------------------------------------------------------------ dựng tin
def _dau(tieu_de: str, mau: str = XANH_DUONG) -> bt._Soan:
    return bt._Soan().them(tieu_de, "b", bt.CO_TIEU_DE, mau)


def _goc() -> str:
    return (os.environ.get("APP_URL") or "").strip().rstrip("/")


def _gio(v) -> str:
    return chu_gio_vn(v, "%d/%m %H:%M")


def _ngan(chu: str, n: int) -> str:
    return chu if len(chu) <= n else chu[:n - 1].rstrip() + "…"


def _tra_loi_mau(r: dict) -> str:
    return f"dong y {r['id']} {r['khuyen_nghi']} | sua {r['id']} <ý kiến> | bac {r['id']} <lý do>"


def tin_de_xuat(r: dict) -> bt.TinZalo:
    """Tiêu đề, nhận định, các phương án, khuyến nghị, hạn, lệnh trả lời. Dài quá thì rút gọn mô tả phương án (không bao giờ cắt lệnh trả lời)."""
    s = r["su_that"]
    for gh in (150, 100, 60, 0):
        t = _dau(f"ĐỀ XUẤT CẦN QUYẾT #{r['id']}").them(f"\n{r['tieu_de']}", "b").them(f"\n\n{r['nhan_dinh']}")
        t.them("\n\nPHƯƠNG ÁN", "b", bt.CO_NHO, XAM)
        for p in r["phuong_an"]:
            t.them(f"\n{p['ma']}. ", "b").them(p["tieu_de"] + (" (khuyến nghị)" if p["ma"] == r["khuyen_nghi"] else ""), "b").them(f" - {_ngan(p['mo_ta'], gh)}" if gh else "")
        t.them(f"\n\nKhuyến nghị: {r['khuyen_nghi']}", "b", CAM)
        t.them(f"\nHạn quyết: {_gio(r['han_quyet'])}", bt.CO_NHO, XAM)
        t.them(f"\n\nTrả lời: {_tra_loi_mau(r)}", "b", bt.CO_NHO)
        if _goc() and s.get("duong_dan"):
            t.them(f"\nXem chi tiết: {_goc()}{s['duong_dan']}", bt.CO_NHO, XANH_DUONG)
        tin = t.xong()
        if len(tin) <= GIOI_HAN:
            return tin
    return bt._cat(tin, GIOI_HAN)


def tin_tong_hop(rows: list[dict], khoi: str | None = None) -> bt.TinZalo:
    """MỘT tin liệt kê các đề xuất đang chờ (mức cao trước), mỗi dòng: số, mức, tiêu đề, khuyến nghị. Dài quá thì bớt dòng, không bao giờ cắt hướng dẫn trả lời."""
    ds = sorted(rows, key=lambda r: ({"cao": 0, "trung_binh": 1}.get(r["su_that"].get("muc"), 2), r["id"]))
    for n in (TOI_DA_DONG, 6, 3, 1):
        hien = ds[:n]
        t = _dau(f"CẦN QUYẾT{' - KHỐI ' + TEN_KHOI.get(khoi, str(khoi).upper()) if khoi else ''}: {len(ds)} ĐỀ XUẤT")
        for r in hien:
            t.them(f"\n#{r['id']} ", "b").them(f"[{MUC_CHU.get(r['su_that'].get('muc'), '')}] {_ngan(r['tieu_de'], 80)} (khuyến nghị {r['khuyen_nghi']})")
        if len(ds) > len(hien):
            t.them(f"\n… và {len(ds) - len(hien)} đề xuất khác, gõ quyet dinh để xem hết.", bt.CO_NHO, XAM)
        t.them("\n\nXem đủ phương án: xem <số>", "b", bt.CO_NHO)
        t.them("\nQuyết: dong y <số> [A|B|C] | sua <số> <ý kiến> | bac <số> <lý do>", "b", bt.CO_NHO)
        if _goc():
            t.them(f"\nTrang đầy đủ: {_goc()}/trolydieuhanh", bt.CO_NHO, XANH_DUONG)
        tin = t.xong()
        if len(tin) <= GIOI_HAN:
            return tin
    return bt._cat(tin, GIOI_HAN)


def tin_nhac(r: dict) -> bt.TinZalo:
    t = _dau("NHẮC QUYẾT ĐỊNH", CAM).them(f"\n#{r['id']} {r['tieu_de']}", "b")
    t.them(f"\n\nĐề xuất từ {_gio(r['tao_luc'])}, hạn quyết {_gio(r['han_quyet'])} đã qua. Khuyến nghị của trợ lý: phương án {r['khuyen_nghi']}.")
    t.them(f"\n\nTrả lời: {_tra_loi_mau(r)}", "b", bt.CO_NHO)
    return bt._cat(t.xong(), GIOI_HAN)


def tin_leo_thang(r: dict, ten_nguoi: str) -> bt.TinZalo:
    t = _dau("ĐỀ XUẤT QUÁ HẠN QUYẾT", DO).them(f"\n#{r['id']} {r['tieu_de']}", "b")
    t.them(f"\n\n{ten_nguoi} chưa quyết sau hạn {_gio(r['han_quyet'])}. Anh/chị cấp trên có thể quyết thay hoặc nhắc người phụ trách.")
    t.them(f"\n\nTrả lời: {_tra_loi_mau(r)}", "b", bt.CO_NHO)
    return bt._cat(t.xong(), GIOI_HAN)


def lua_chon_chu(r: dict) -> str:
    if r["lua_chon"] == so.LUA_CHON_SUA:
        return "Sửa ý: " + _ngan(r["ghi_chu"] or "", 120)
    pa = {p["ma"]: p for p in r["phuong_an"]}
    return f"{r['lua_chon']} - {pa[r['lua_chon']]['tieu_de']}" if r["lua_chon"] in pa else (("Bác: " + (r["ghi_chu"] or "")) if r["trang_thai"] == "bac" else "")


def tin_kiem_chung(r: dict) -> bt.TinZalo:
    t = _dau("KẾT QUẢ SAU QUYẾT ĐỊNH").them(f"\n#{r['id']} {r['tieu_de']}", "b")
    t.them(f"\n\nĐã chọn: {lua_chon_chu(r)}", "b").them(f"\nQuyết lúc {_gio(r['quyet_luc'])}, đo lại lúc {_gio(r['han_kiem_chung'])}.", bt.CO_NHO, XAM)
    t.them(f"\n\n{r['ket_qua']}")
    return bt._cat(t.xong(), GIOI_HAN)


# ------------------------------------------------------------------ gửi
_CHI_GUI: ContextVar[dict | None] = ContextVar("tdh_chi_gui", default=None)


@contextmanager
def chi_gui_cho(chat_id: str):
    """Chế độ GỬI THỬ: trong khối này mọi tin của trợ lý chỉ đi tới đúng một chat (nhãn "GỬI THỬ"), người quyết thật KHÔNG nhận gì và tin KHÔNG bị đánh dấu là đã gửi
    (nên lúc gửi thật họ vẫn nhận đủ). Trả {chat_id, so_tin, loi} để trang báo số tin đã đi."""
    kq = {"chat_id": str(chat_id), "so_tin": 0, "loi": 0}
    mo = _CHI_GUI.set(kq)
    try:
        yield kq
    finally:
        _CHI_GUI.reset(mo)


def _gui_mot(chat_id: str, tin) -> bool:
    """Gửi một tin cho một chat. Chế độ gửi thử: chỉ gửi cho chat được chọn (nhãn GỬI THỬ), đếm số tin và luôn trả False (không đánh dấu đã gửi)."""
    thu = _CHI_GUI.get()
    try:
        if thu is not None:
            zalo_bot.gui_tin_du_phong(thu["chat_id"], bt._voi_dau("[GỬI THỬ - người quyết thật chưa nhận tin này]\n", tin))
            thu["so_tin"] += 1
            return False
        zalo_bot.gui_tin_du_phong(str(chat_id), tin)
        return True
    except Exception:                       # một người lỗi (hoặc bot chưa cài) không làm hỏng các người khác; lượt sau thử lại vì chưa đánh dấu
        if thu is not None:
            thu["loi"] += 1
        return False


def gui_cho(khoa: str, tin, now: datetime | None = None) -> bool:
    """Gửi một tin cho mọi người nhận (đang bật) của khoá người quyết; True nếu ít nhất một người nhận được (Zalo từ chối kiểu chữ thì tự gửi chữ trơn).
    Đang ở chế độ gửi thử (`chi_gui_cho`) thì chỉ gửi cho chat được chọn và luôn trả False (không đánh dấu đã gửi)."""
    if not so.bat():
        return False
    if _CHI_GUI.get() is not None:
        _gui_mot("", tin)
        return False
    ok = False
    for n in td.nguoi_nhan_cua(khoa):
        ok = _gui_mot(n["chat_id"], tin) or ok
    return ok


def gui_de_xuat_chua_gui(now: datetime | None = None, khoi: str | None = None) -> int:
    """Gửi các đề xuất đang chờ mà chưa tới tay người quyết (của `khoi`, None = mọi khối), gom MỘT tin tổng hợp cho mỗi người nhận;
    trả số đề xuất đã tới tay ít nhất một người (các đề xuất đó được đánh dấu, mỗi đề xuất đúng một lần)."""
    if not so.bat():
        return 0
    now = now or utc_bay_gio()
    thu = _CHI_GUI.get()
    theo_chat: dict[str, list[dict]] = {}
    for r in sorted(so.liet_ke(so.CHO), key=lambda r: r["id"]):
        if r["da_gui_luc"] or (khoi is not None and r["khoi"] != khoi):
            continue
        for chat in [thu["chat_id"]] if thu else [n["chat_id"] for n in td.nguoi_nhan_cua(r["nguoi_quyet"])]:
            theo_chat.setdefault(chat, []).append(r)
    xong: set[int] = set()
    for chat, rows in theo_chat.items():
        if _gui_mot(chat, tin_tong_hop(rows, khoi)):
            xong.update(r["id"] for r in rows)
    for id_ in xong:
        so.danh_dau(id_, "da_gui_luc", now)
    return len(xong)


def bao_kiem_chung(now: datetime | None = None) -> int:
    """Báo kết quả kiểm chứng cho Ban Giám đốc và người quyết (đúng một lần mỗi quyết định); trả số quyết định đã báo."""
    now = now or utc_bay_gio()
    n = 0
    for r in so.liet_ke("da_kiem_chung"):
        if r["bao_kiem_chung_luc"]:
            continue
        tin = tin_kiem_chung(r)
        if all([gui_cho(k, tin, now) for k in dict.fromkeys(["bgd", r["nguoi_quyet"]])]):
            so.danh_dau(r["id"], "bao_kiem_chung_luc", now)
            n += 1
    return n


# ------------------------------------------------------------------ nhận lệnh
def phan_tich_lenh(text: str) -> dict | None:
    """"dong y 12 B" / "sua 12 ý kiến" / "bac 12 lý do" / "xem 12" / "bao cao [kd|dvkh]" / "quyet dinh" -> {lenh, id, chon, y_kien}; không phải lệnh của trợ lý thì None.
    Tách theo từ trên chữ GỐC để giữ nguyên dấu và hoa thường của phần ý kiến."""
    tu = (text or "").split()
    nho = [bo_dau(t) for t in tu]
    if nho[:2] == ["quyet", "dinh"] and len(tu) == 2:
        return {"lenh": "danh_sach", "id": None, "chon": None, "y_kien": ""}
    if nho[:2] == ["bao", "cao"] and len(tu) <= 3 and (len(tu) == 2 or nho[2] in td.KHOI_HOP_LE):
        return {"lenh": "bao_cao", "id": None, "chon": nho[2] if len(tu) == 3 else td.KHOI_MAC_DINH, "y_kien": ""}
    n = 2 if nho[:2] == ["dong", "y"] else 1 if nho[:1] in (["sua"], ["bac"], ["xem"]) else 0
    if not n or len(tu) <= n or not tu[n].lstrip("#").isdigit():
        return None
    lenh = CUA_LENH[" ".join(nho[:n])]
    con = tu[n + 1:]
    chon = con[0].upper() if lenh == "dong_y" and con and con[0].upper() in ("A", "B", "C") else None
    return {"lenh": lenh, "id": int(tu[n].lstrip("#")), "chon": chon, "y_kien": " ".join(con[1:] if chon else con)}


def _liet_ke_cho(chat_id: str) -> str:
    ds = [r for r in sorted(so.liet_ke(so.CHO), key=lambda r: r["id"]) if td.duoc_quyet(chat_id, r)]
    if not ds:
        return "Không có đề xuất nào đang chờ bạn quyết."
    dong = [f"#{r['id']} {_ngan(r['tieu_de'], 90)} (hạn {_gio(r['han_quyet'])}, khuyến nghị {r['khuyen_nghi']})" for r in ds[:10]]
    return "Đề xuất đang chờ bạn quyết:\n" + "\n".join(dong) + "\n\nTrả lời: dong y <số> [A|B|C] | sua <số> <ý kiến> | bac <số> <lý do>"


def _bao_cao_khoi(chat_id: str, khoi: str):
    """Trả lời lệnh "bao cao [khối]": tin tổng hợp các đề xuất ĐANG CHỜ của khối đó mà người hỏi quyết được (không quét lại số liệu, không gửi cho ai khác)."""
    ds = [r for r in so.liet_ke(so.CHO) if r["khoi"] == khoi and td.duoc_quyet(chat_id, r)]
    if not ds:
        return f"Không có đề xuất nào đang chờ bạn ở khối {TEN_KHOI.get(khoi, khoi).lower()}. Muốn rà soát khối này, chạy trợ lý ở trang Trợ lý điều hành."
    return tin_tong_hop(ds, khoi)


def thuc_hien(chat_id: str, lenh: dict, now: datetime | None = None) -> str:
    """Thực hiện một lệnh của người ĐÃ là người nhận; trả câu trả lời gửi lại họ. Chỉ ghi sổ."""
    from app.auth import ghi_log
    now = now or utc_bay_gio()
    if lenh["lenh"] == "danh_sach":
        return _liet_ke_cho(chat_id)
    if lenh["lenh"] == "bao_cao":
        return _bao_cao_khoi(chat_id, lenh["chon"])
    r = so.doc(lenh["id"])
    if r is None:
        return f"Không có đề xuất #{lenh['id']}."
    if not td.duoc_quyet(chat_id, r):
        return f"Bạn không có quyền quyết đề xuất #{r['id']} (thuộc {td.ten_nguoi_quyet(r['nguoi_quyet'])})."
    if lenh["lenh"] == "xem":
        return tin_de_xuat(r)
    if r["trang_thai"] not in so.CHO:
        return f"Đề xuất #{r['id']} đang ở trạng thái “{so.TRANG_THAI.get(r['trang_thai'], r['trang_thai'])}”, không đổi được nữa."
    ten = f"{td.nguoi_theo_chat(chat_id)['ten']} (Zalo)"
    ma = {p["ma"] for p in r["phuong_an"]}
    if lenh["lenh"] == "dong_y":
        chon = lenh["chon"] or r["khuyen_nghi"]
        if chon not in ma:
            return f"Đề xuất #{r['id']} chỉ có phương án {', '.join(sorted(ma))}."
        ok, mo_ta = so.quyet(r["id"], ten, chon, "", now), f"chọn phương án {chon}"
    elif lenh["lenh"] == "sua":
        if not lenh["y_kien"]:
            return "Cần ghi ý kiến, ví dụ: sua 12 giao thêm cho phòng khác."
        ok, mo_ta = so.quyet(r["id"], ten, so.LUA_CHON_SUA, lenh["y_kien"], now), "ghi ý kiến của bạn"
    else:
        ok, mo_ta = so.bac(r["id"], ten, lenh["y_kien"], now), "bác đề xuất"
    if not ok:
        return f"Đề xuất #{r['id']} vừa được người khác quyết, không đổi được nữa."
    ghi_log("tro_ly_dieu_hanh_quyet", f"#{r['id']} {lenh['lenh']} {lenh['chon'] or ''} boi {ten}"[:200])
    sau = f" Trợ lý sẽ đo lại kết quả sau {so.cau_hinh()['kiem_chung_gio']} giờ." if lenh["lenh"] != "bac" else ""
    return f"Đã ghi nhận: {mo_ta} cho đề xuất #{r['id']}. Quyết định này chỉ được lưu vào sổ, trợ lý không tự làm gì khác.{sau}"


def xu_ly_webhook(payload) -> bool:
    """True nếu sự kiện là lệnh của trợ lý từ một người nhận đã biết (đã trả lời họ); False thì webhook Bản tin xử lý như cũ.
    Tắt công tắc thì luôn False (không đọc, không phản hồi)."""
    if not so.bat():
        return False
    from app import zalo_gia
    tin = zalo_gia.doc_tin(payload)
    if not tin or tin["la_bot"] or tin["loai_chat"] not in LOAI_CHAT_RIENG:
        return False
    lenh = phan_tich_lenh(tin["text"])
    if lenh is None or td.nguoi_theo_chat(tin["chat_id"]) is None:
        return False
    tra_loi = thuc_hien(tin["chat_id"], lenh)
    try:
        if getattr(tra_loi, "kieu", None):
            zalo_bot.gui_tin_du_phong(tin["chat_id"], tra_loi, han=4)
        else:
            zalo_bot.gui_tin(tin["chat_id"], tra_loi, han=4)
    except Exception:                          # trả lời hỏng không làm mất việc đã ghi sổ
        pass
    return True
