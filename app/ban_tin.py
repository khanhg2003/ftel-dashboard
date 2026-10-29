"""Bản tin 8h sáng gửi qua Zalo Bot (giai đoạn 1: Ban Giám đốc + nhắc Admin nạp file).

n8n (hoặc cron) chỉ làm đồng hồ, gọi `chay()` mỗi 15 phút từ 8h tới 11h giờ Việt Nam; app tự quyết có gửi hay không.
Gửi khi ngày số mới nhất đã CHỐT: không còn "đang cập nhật" (`overview.trang_thai_ngay`) VÀ lần nạp cuối nằm sau
06:00 sáng hôm sau ngày số đó (file nạp 14:30 trong ngày chỉ là số tạm). Mỗi (ngày số, người nhận, loại tin) gửi
đúng một lần nhờ khoá duy nhất ở `BanTinNhatKy`; gửi lỗi thì lượt sau thử lại tối đa `TOI_DA_LAN`, đã ok thì không
bao giờ gửi lại dù file nạp lại và số đổi. Nội dung do code dựng bằng khuôn cố định (không gọi AI), số lấy đúng
từ các hàm của Báo cáo Tổng.
"""
from __future__ import annotations

import os
import time
from datetime import date, datetime, time as gio_gio, timedelta

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.exc import IntegrityError

from app import du_bao, metrics, overview, zalo_bot
from app.auth import ghi_log
from app.db import engine, session_scope
from app.models import BanTinNguoiNhan, BanTinNhatKy
from app.thoi_gian import gio_viet_nam, utc_bay_gio

LOAI_NHAN = {"bgd": "Ban Giám đốc", "admin": "Admin (nhắc nạp file)"}
GIO_GUI = gio_gio(8, 0)
GIO_NHAC = gio_gio(10, 30)
MOC_CHOT = gio_gio(6, 0)              # lần nạp cuối phải sau mốc này của SÁNG HÔM SAU ngày số
TOI_DA_LAN = 3
QUA_HAN_DANG_GUI = timedelta(minutes=10)
TOI_DA_KY_TU = 1900
HAN_GIAY = 45                          # vercel.json: maxDuration 60


def dam_bao_bang() -> None:
    """Tạo hai bảng nếu chưa có (Supabase không chạy create_all lúc khởi động)."""
    try:
        for b in (BanTinNguoiNhan, BanTinNhatKy):
            b.__table__.create(bind=engine, checkfirst=True)
    except Exception:
        pass


dam_bao_bang()


# ------------------------------------------------------------------ người nhận
def ds_nguoi_nhan(loai: str | None = None, chi_bat: bool = False) -> list[dict]:
    with session_scope() as s:
        q = select(BanTinNguoiNhan).order_by(BanTinNguoiNhan.id)
        if loai:
            q = q.where(BanTinNguoiNhan.loai == loai)
        if chi_bat:
            q = q.where(BanTinNguoiNhan.bat.is_(True))
        return [{"id": r.id, "ten": r.ten, "loai": r.loai, "loai_nhan": LOAI_NHAN.get(r.loai, r.loai),
                 "chat_id": r.chat_id, "bat": bool(r.bat), "bat_nhan": "Bật" if r.bat else "Tắt"}
                for r in s.execute(q).scalars()]


def lay_nguoi_nhan(id_: int) -> dict | None:
    return next((r for r in ds_nguoi_nhan() if r["id"] == int(id_)), None)


def luu_nguoi_nhan(id_: int | None, ten: str, loai: str, chat_id: str, bat: bool) -> tuple[bool, str]:
    ten, chat_id = (ten or "").strip(), (chat_id or "").strip()
    if not ten or not chat_id:
        return False, "Cần nhập tên và chat_id."
    if loai not in LOAI_NHAN:
        return False, "Loại người nhận không hợp lệ."
    with session_scope() as s:
        r = s.get(BanTinNguoiNhan, int(id_)) if id_ else None
        if id_ and not r:
            return False, "Không tìm thấy người nhận này."
        if not r:
            r = BanTinNguoiNhan(tao_luc=utc_bay_gio())
            s.add(r)
        r.ten, r.loai, r.chat_id, r.bat = ten[:120], loai, chat_id[:80], bool(bat)
    ghi_log("ban_tin_nguoi_nhan", f"{'Sửa' if id_ else 'Thêm'} {ten} ({loai}, chat_id {chat_id})")
    return True, f"Đã lưu người nhận “{ten}”."


def xoa_nguoi_nhan(ids: list[int]) -> int:
    ids = [int(i) for i in ids]
    if not ids:
        return 0
    with session_scope() as s:
        n = int(s.execute(delete(BanTinNguoiNhan).where(BanTinNguoiNhan.id.in_(ids))).rowcount or 0)
    if n:
        ghi_log("ban_tin_nguoi_nhan", f"Xoá {n} người nhận: {ids}")
    return n


def nhat_ky_gan_day(n: int = 10) -> list[dict]:
    with session_scope() as s:
        rows = s.execute(select(BanTinNhatKy).order_by(BanTinNhatKy.gio_gui.desc(), BanTinNhatKy.id.desc())
                         .limit(n)).scalars().all()
        nhan = {"ok": "Đã gửi", "loi": "Lỗi", "dang_gui": "Đang gửi"}
        return [{"id": r.id, "ngay_so": r.ngay_so.strftime("%d/%m/%Y"), "ten_nguoi": r.ten_nguoi,
                 "loai": "Bản tin" if r.loai == "bgd" else "Nhắc nạp file",
                 "gio_gui": (r.gio_gui + timedelta(hours=7)).strftime("%d/%m %H:%M") if r.gio_gui else "",
                 "ket_qua": nhan.get(r.ket_qua, r.ket_qua), "ly_do": r.ly_do or ""} for r in rows]


def gui_thu(id_: int) -> tuple[bool, str]:
    """Gửi thử bản tin của ngày số mới nhất (đầu tin có nhãn "BẢN THỬ") để xem trên Zalo; không cần chờ chốt số,
    không ghi nhật ký gửi ngày nên bản tin thật vẫn đi bình thường. Không dựng được nội dung thì gửi tin ngắn kiểm kết nối."""
    nguoi = lay_nguoi_nhan(id_)
    if not nguoi:
        return False, "Không tìm thấy người nhận này."
    chu = "Thử bản tin: kết nối Zalo của app báo cáo FTEL hoạt động."
    try:
        ngay_iso = metrics.ngay_moi_nhat()
        if ngay_iso:
            chu = f"[BẢN THỬ - chưa tính là đã gửi]\n{dung_noi_dung_bgd(ngay_iso)}"[:TOI_DA_KY_TU]
    except Exception:
        pass
    try:
        zalo_bot.gui_tin(nguoi["chat_id"], chu)
        ket = (True, f"Đã gửi tin thử cho {nguoi['ten']}.")
    except zalo_bot.LoiZalo as e:
        ket = (False, f"Chưa gửi được cho {nguoi['ten']}: {e}")
    ghi_log("ban_tin_gui_thu", f"{nguoi['ten']}: {'ok' if ket[0] else ket[1]}"[:200])
    return ket


# ------------------------------------------------------------------ chốt số
def da_chot(ngay_iso: str) -> tuple[bool, str]:
    """(đã chốt?, lý do nếu chưa). Chốt = không còn đang cập nhật và lần nạp cuối sau 06:00 sáng hôm sau."""
    dang, luc = overview.trang_thai_ngay(ngay_iso)
    ngay = date.fromisoformat(ngay_iso)
    if luc is None:
        return False, "Chưa có lần nạp số nào."
    if dang:
        return False, f"Số ngày {ngay:%d/%m} vẫn đang cập nhật."
    if luc < datetime.combine(ngay + timedelta(days=1), MOC_CHOT):
        return False, f"Số ngày {ngay:%d/%m} mới nạp tạm, chưa có lần nạp từ 06:00 sáng hôm sau."
    return True, ""


# ------------------------------------------------------------------ nội dung bản tin
def _so(v, tp: int = 0) -> str:
    if v is None:
        return "–"
    s = f"{float(v):,.{tp}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def _pct(tu, mau) -> int | None:
    return round(float(tu) / float(mau) * 100) if mau else None


def _chat_luong_thang_truoc(thang: str, ngay: int):
    """Dòng tổng của tháng trước, cùng số ngày; None nếu chưa có số (tháng đầu dùng app)."""
    pm = metrics.prev_month(thang)
    try:
        df, _ = overview.bang_tong_quan(pm, min(ngay, metrics.month_range(pm)[2]), chi_nhanh="all")
        t = df[df.loai_dong == "total"].iloc[0]
        return t if float(t["online"] or 0) > 0 else None
    except Exception:
        return None


def _so_lieu_bgd(ngay_iso: str) -> dict:
    thang, ngay = ngay_iso[:7], int(ngay_iso[8:10])
    df, _ = overview.bang_tong_quan(thang, ngay, chi_nhanh="all")
    db = du_bao.du_bao_thang(thang, ngay)
    return {"thang": thang, "ngay": ngay, "tong": df[df.loai_dong == "total"].iloc[0],
            "du_bao": db[db.phong_code == "TOTAL"].iloc[0], "phong": db[db.phong_code != "TOTAL"],
            "truoc": _chat_luong_thang_truoc(thang, ngay), "thang_truoc": metrics.prev_month(thang)}


def _khoi_tong_quan(sl: dict) -> str:
    t, d, tt = sl["tong"], sl["du_bao"], sl["thang_truoc"][5:7].lstrip("0")
    online, mt, ck = int(t["online"]), int(t["mt_internet"] or 0), int(t["ck_online"] or 0)
    dong = [f"- Online luỹ kế: {_so(online)}" + (f" / {_so(mt)} mục tiêu tháng ({_pct(online, mt)}%)." if mt
                                                else " (chưa có mục tiêu tháng).")]
    if ck:
        c = round((online - ck) / ck * 100)
        dong.append(f"- Cùng kỳ tháng {tt}: {_so(ck)} online, " + (f"tăng {c}%." if c > 0 else
                                                                  f"giảm {-c}%." if c < 0 else "bằng nhau."))
    dong.append(f"- Dự báo cuối tháng: {_so(d['du_bao'])} ({_so(d['du_bao_nhip'])})"
                + (f", mức {d['danh_gia']}." if mt else "."))
    dong.append("  Số trong ngoặc tính thêm nhịp dồn cuối tháng.")
    return "1) TỔNG QUAN\n" + "\n".join(dong)


def _khoi_phong(sl: dict, n_thap: int) -> str:
    p = sl["phong"]
    co_mt = p[(p["mt"] > 0) & ~p["phong_code"].isin(overview.phong_khong_cong_tong())]      # ANCS... không cộng vào tổng nên không xếp hạng
    thap = co_mt.dropna(subset=["pct_mt"]).sort_values("pct_mt").head(n_thap)
    dong = ["Thấp nhất so với mục tiêu (xếp theo dự báo cuối tháng):"]
    dong += [f"- {r['phong']}: {_so(r['luy_ke'])}/{_so(r['mt'])} ({_pct(r['luy_ke'], r['mt'])}%), "
             f"dự báo {int(r['pct_mt'])}% mục tiêu" + (" - Rủi ro" if r["danh_gia"] == du_bao.RUI_RO else "")
             for _, r in thap.iterrows()]
    rui_ro = [r["phong"] for _, r in co_mt.iterrows() if r["danh_gia"] == du_bao.RUI_RO]
    if rui_ro:
        ds = ", ".join(rui_ro[:8]) + (f" và {len(rui_ro) - 8} phòng khác" if len(rui_ro) > 8 else "")
        dong.append(f"Phòng ở mức Rủi ro ({len(rui_ro)}): {ds}.")
    elif len(thap):
        dong.append("Không có phòng nào ở mức Rủi ro.")
    return "2) PHÒNG CẦN CHÚ Ý\n" + "\n".join(dong) if len(thap) else ""


def _khoi_chat_luong(sl: dict) -> str:
    t, tr, tt = sl["tong"], sl["truoc"], sl["thang_truoc"][5:7].lstrip("0")
    dong = []
    if t["vvip_ty_le"] is not None:
        dong.append(f"- V.VIP: {_so(t['vvip'])}, bằng {_so(t['vvip_ty_le'])}% số online"
                    + (f", cùng kỳ tháng {tt}: {_so(tr['vvip_ty_le'])}%." if tr is not None
                       and tr["vvip_ty_le"] is not None else "."))
    if t["htkh_camera"] is not None:
        dong.append(f"- Camera: {_so(t['camera'])}/{_so(t['mt_camera'])} mục tiêu ({_so(t['htkh_camera'])}%)"
                    + (f", cùng kỳ tháng {tt}: {_so(tr['htkh_camera'])}%." if tr is not None
                       and tr["htkh_camera"] is not None else "."))
    return "3) CHẤT LƯỢNG BÁN (luỹ kế tháng)\n" + "\n".join(dong) if dong else ""


def dung_noi_dung_bgd(ngay_iso: str) -> str:
    """Bản tin Ban Giám đốc, tối đa 1.900 ký tự: dài quá thì bỏ mục 3 rồi bớt phòng ở mục 2 trước."""
    sl = _so_lieu_bgd(ngay_iso)
    ngay = date.fromisoformat(ngay_iso)
    dau = f"Số chốt ngày {ngay:%d/%m}\nToàn chi nhánh, luỹ kế tháng {ngay.month} (tới ngày {ngay:%d/%m})."
    link = (os.environ.get("APP_URL") or "").strip()
    chan = f"Xem chi tiết: {link}" if link else ""
    tq, cl = _khoi_tong_quan(sl), _khoi_chat_luong(sl)
    for n_thap, co_cl in ((3, True), (3, False), (2, False), (1, False)):
        khoi = [dau, tq, _khoi_phong(sl, n_thap), cl if co_cl else "", chan]
        chu = "\n\n".join(k for k in khoi if k)
        if len(chu) <= TOI_DA_KY_TU:
            return chu
    return chu[:TOI_DA_KY_TU]


# ------------------------------------------------------------------ gửi + nhật ký chống trùng
def _giu_cho(ngay: date, nguoi: dict, loai: str) -> int | None:
    """Giành quyền gửi: trả id dòng nhật ký nếu lượt này được gửi, None nếu đã ok / đang gửi / hết lượt thử.
    Chèn dòng mới (khoá duy nhất quyết định ai thắng khi hai lượt chạy cùng lúc) hoặc giành lại dòng lỗi / treo."""
    bay_gio = utc_bay_gio()
    khoa = and_(BanTinNhatKy.ngay_so == ngay, BanTinNhatKy.nguoi_nhan_id == nguoi["id"], BanTinNhatKy.loai == loai)
    try:
        with session_scope() as s:
            r = BanTinNhatKy(ngay_so=ngay, nguoi_nhan_id=nguoi["id"], ten_nguoi=nguoi["ten"], loai=loai,
                             ket_qua="dang_gui", so_lan=1, gio_gui=bay_gio)
            s.add(r)
            s.flush()
            return r.id
    except IntegrityError:
        pass
    with session_scope() as s:
        da_giu = s.execute(update(BanTinNhatKy).where(
            khoa, BanTinNhatKy.so_lan < TOI_DA_LAN,
            or_(BanTinNhatKy.ket_qua == "loi", and_(BanTinNhatKy.ket_qua == "dang_gui",
                                                    BanTinNhatKy.gio_gui < bay_gio - QUA_HAN_DANG_GUI)),
        ).values(ket_qua="dang_gui", gio_gui=bay_gio, so_lan=BanTinNhatKy.so_lan + 1)).rowcount
        return s.execute(select(BanTinNhatKy.id).where(khoa)).scalar() if da_giu == 1 else None


def _ghi_ket_qua(id_: int, ok: bool, ly_do: str = "") -> None:
    with session_scope() as s:
        r = s.get(BanTinNhatKy, id_)
        if r:
            r.ket_qua, r.ly_do, r.gio_gui = ("ok" if ok else "loi"), (ly_do[:200] or None), utc_bay_gio()


def _da_gui_ok(ngay: date, loai: str) -> set[int]:
    with session_scope() as s:
        return set(s.execute(select(BanTinNhatKy.nguoi_nhan_id).where(
            BanTinNhatKy.ngay_so == ngay, BanTinNhatKy.loai == loai, BanTinNhatKy.ket_qua == "ok")).scalars())


def _gui_cho(nguoi: dict, ngay: date, loai: str, chu: str, kq: dict) -> None:
    """Giành quyền gửi, gửi một tin, ghi nhật ký, cộng vào `kq`."""
    id_ = _giu_cho(ngay, nguoi, loai)
    if id_ is None:
        kq["bo_qua"].append({"nguoi": nguoi["ten"], "ly_do": "đã gửi, đang gửi hoặc hết lượt thử lại"})
        return
    try:
        zalo_bot.gui_tin(nguoi["chat_id"], chu)
    except zalo_bot.LoiZalo as e:
        ly_do = str(e)
    except Exception as e:                       # chưa gửi được thì thôi, không làm sập cả lượt (không in thông báo gốc: có thể lộ địa chỉ gọi)
        ly_do = f"Lỗi không xác định khi gửi ({type(e).__name__})."
    else:
        _ghi_ket_qua(id_, True)
        kq["da_gui"].append(nguoi["ten"])
        return
    _ghi_ket_qua(id_, False, ly_do)
    kq["loi"].append({"nguoi": nguoi["ten"], "ly_do": ly_do})


def _gui_nhom(loai_nhan: str, loai_tin: str, ngay: date, dung, kq: dict, t0: float, han: float) -> None:
    """Gửi cho mọi người nhận còn bật mà chưa ok; `dung()` dựng nội dung đúng một lần, chỉ khi có người cần."""
    ds = [n for n in ds_nguoi_nhan(loai_nhan, chi_bat=True) if n["id"] not in _da_gui_ok(ngay, loai_tin)]
    if not ds:
        kq["ly_do"] = kq["ly_do"] or "Không có ai cần nhận thêm."
        return
    try:
        chu = dung()
    except Exception as e:
        kq["loi"].append({"nguoi": "(tất cả)", "ly_do": f"Không dựng được nội dung bản tin ({type(e).__name__})."})
        return
    for n in ds:
        if time.monotonic() - t0 > han:
            kq["ly_do"] = "Gần hết thời gian cho phép, phần còn lại để lượt sau."
            return
        _gui_cho(n, ngay, loai_tin, chu, kq)


def chay(gio_vn: datetime | None = None, kho: bool = False, han_giay: float = HAN_GIAY) -> dict:
    """Một lượt do đồng hồ gọi. `kho=True`: chạy thử, dựng nội dung nhưng không gửi và không ghi nhật ký."""
    t0 = time.monotonic()
    gio = gio_vn or gio_viet_nam()
    ngay_iso = metrics.ngay_moi_nhat()
    kq = {"ngay_so": ngay_iso, "da_gui": [], "bo_qua": [], "loi": [], "ly_do": None, "kho": kho}
    if not ngay_iso:
        kq["ly_do"] = "Chưa có số liệu nào."
        return kq
    ngay = date.fromisoformat(ngay_iso)
    chot, ly_chua = da_chot(ngay_iso)
    sau_8h = gio.time() >= GIO_GUI
    if kho:
        kq["se_gui"] = sau_8h and chot
        kq["ly_do"] = None if kq["se_gui"] else ("Chưa tới 08:00 giờ Việt Nam." if not sau_8h else ly_chua)
        kq["nguoi_nhan"] = [n["ten"] for n in ds_nguoi_nhan("bgd", chi_bat=True)]
        kq["noi_dung"] = dung_noi_dung_bgd(ngay_iso)
        return kq
    if not sau_8h:
        kq["ly_do"] = "Chưa tới 08:00 giờ Việt Nam."
    elif chot:
        _gui_nhom("bgd", "bgd", ngay, lambda: dung_noi_dung_bgd(ngay_iso), kq, t0, han_giay)
    elif gio.time() >= GIO_NHAC:
        kq["ly_do"] = ly_chua
        _gui_nhom("admin", "nhac_admin", ngay,
                  lambda: f"Chưa có số chốt của ngày {ngay:%d/%m}, hãy nạp file.", kq, t0, han_giay)
    else:
        kq["ly_do"] = ly_chua
    for loi in kq["loi"]:
        ghi_log("ban_tin_loi", f"{loi['nguoi']}: {loi['ly_do']}"[:200])
    if kq["da_gui"]:
        ghi_log("ban_tin_gui", f"Ngày số {ngay:%d/%m}: {', '.join(kq['da_gui'])}"[:200])
    return kq
