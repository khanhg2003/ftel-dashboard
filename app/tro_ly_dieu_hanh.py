"""TRỢ LÝ ĐIỀU HÀNH: vòng khép kín cho lãnh đạo / trưởng phòng.
RÀ SOÁT TOÀN DIỆN (`tro_ly_dieu_hanh_quet`) -> NHẬN ĐỊNH + 2-3 PHƯƠNG ÁN (`tro_ly_dieu_hanh_nd`) -> CHỜ NGƯỜI QUYẾT (sổ ở `tro_ly_dieu_hanh_so`) -> NHẮC / LEO THANG ->
KIỂM CHỨNG bằng chính chỉ số đã đo lúc đề xuất. Gửi Zalo và nhận lệnh ở `tro_ly_dieu_hanh_zalo`.

Quy tắc cốt lõi:
- Chỉ ĐỌC số liệu có sẵn của app; chỉ ghi vào ba bảng `td_*`. Toàn tính năng nằm sau công tắc `rules.yml` → `tro_ly_dieu_hanh.bat` (mặc định tắt): tắt thì các hàm chạy
  ở đây trả {"tat": True} và không làm gì. Gửi Zalo CHỈ khi người gọi truyền `gui=True` (trang: ô tick của quản trị; đường tự động: công tắc `tu_dong`).
- Phát hiện cùng nhóm (cùng nguồn + cùng người quyết, vd mọi nhân sự cần chú ý của một phòng) gom thành MỘT vấn đề; vấn đề chỉ toàn mức thấp thì không thành đề xuất nhưng vẫn
  được đếm ("còn N mục nhỏ"). Mọi vấn đề mức cao luôn được giữ dù vượt trần `toi_da_van_de`; phần trung bình bị bỏ được đếm trong kết quả, không im lặng.
- Người quyết: vấn đề của một phòng về trưởng phòng đúng phòng đó (`tp:<mã>`), toàn chi nhánh / DVKH / dữ liệu về Ban Giám đốc (`bgd`); người nhận lấy từ danh sách người nhận
  Bản tin (`ban_tin_nguoi_nhan`, `ban_tin_nguoi_nhan_phong`). Phòng chưa có trưởng phòng nhận tin thì tin về Ban Giám đốc.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from app import tro_ly_dieu_hanh_nd as nd, tro_ly_dieu_hanh_quet as q, tro_ly_dieu_hanh_so as so
from app.thoi_gian import utc_bay_gio

MAC_DINH = object()                              # "dùng LLM thật nếu có" (khác với None = chỉ dùng luật)
TAT = {"tat": True}


# ------------------------------------------------------------------ người quyết
def nguoi_nhan_cua(khoa: str) -> list[dict]:
    """Người nhận (đang bật) của một khoá người quyết: trưởng phòng đúng phòng, không có thì Ban Giám đốc."""
    from app import ban_tin
    ds = ban_tin.ds_nguoi_nhan(chi_bat=True)
    if khoa.startswith("tp:"):
        tp = [n for n in ds if n["loai"] == ban_tin.LOAI_TRUONG_PHONG and khoa[3:] in n["phong"]]
        if tp:
            return tp
    return [n for n in ds if n["loai"] == "bgd"]


def ten_nguoi_quyet(khoa: str) -> str:
    ten = ", ".join(n["ten"] for n in nguoi_nhan_cua(khoa))
    return ten or ("Ban Giám đốc" if khoa == "bgd" else f"Trưởng phòng {khoa[3:]}")


def cap_tren(khoa: str) -> str | None:
    return "bgd" if khoa.startswith("tp:") else None


def nguoi_theo_chat(chat_id: str) -> dict | None:
    from app import ban_tin
    return next((n for n in ban_tin.ds_nguoi_nhan(chi_bat=True) if n["chat_id"] == str(chat_id)), None)


def duoc_quyet(chat_id: str, r: dict) -> bool:
    """Chỉ người nhận quyết đúng phần của mình hoặc Ban Giám đốc (cấp trên quyết thay được); người ngoài danh sách thì không."""
    n = nguoi_theo_chat(chat_id)
    if not n:
        return False
    return n["loai"] == "bgd" or (n["loai"] == "truong_phong" and r["nguoi_quyet"] in {f"tp:{p}" for p in n["phong"]})


# ------------------------------------------------------------------ gom phát hiện thành vấn đề
def _gom_nhom(nhom: str, g: list[dict], ngay: str, c: dict) -> dict:
    lead = max(g, key=lambda f: (-q.HANG_MUC[f["muc"]], f["diem"]))
    dem = {m: sum(1 for f in g if f["muc"] == m) for m in q.HANG_MUC}
    cao = sorted((f for f in g if f["muc"] == q.CAO), key=lambda f: -f["diem"])
    nguoi = {f["doi_tuong"] for f in g if f["muc"] != q.THAP}
    nguoi_cao = {f["doi_tuong"] for f in cao}
    bc = {**lead["bang_chung"], "so_muc": len(g), "so_cao": dem[q.CAO], "so_trung_binh": dem[q.TB], "so_thap": dem[q.THAP], "so_nguoi": len(nguoi), "so_cao_nguoi": len(nguoi_cao)}
    cs = dict(lead["chi_so"])
    try:
        cs["gia_tri"] = q.do_chi_so(cs["loai"], cs["tham_so"], c)
    except Exception:
        cs["gia_tri"] = None
    tieu_de = lead["tieu_de"] if len(g) == 1 else f"{lead['nhan_nhom']}: {len(nguoi) or len(g)} {lead['don_vi'] or 'mục'}"
    ngay_so = f"{c['ngay_iso'][8:10]}/{c['ngay_iso'][5:7]}" if c.get("ngay_iso") else ""
    su_that = {"loai": lead["nguon"], "tieu_de": tieu_de, "khoi": lead["khoi"], "cap": lead["cap"], "doi_tuong": lead["doi_tuong"], "muc": lead["muc"], "ngay_so": ngay_so, "bang_chung": bc,
               "duong_dan": lead["duong_dan"], "phat_hien_cao": [{"doi_tuong": f["doi_tuong"], "tieu_de": f["tieu_de"], **f["bang_chung"]} for f in cao[:nd.TOI_DA_CAO_NEU]],
               "chi_so": cs, "han_quyet_gio": so.cau_hinh()["han_quyet_gio"], "kiem_chung_gio": so.cau_hinh()["kiem_chung_gio"]}
    su_that, cs = so.sach(su_that), so.sach(cs)
    return {"ma_van_de": f"{ngay}:{nhom}", "nhom": nhom, "loai": lead["nguon"], "tieu_de": tieu_de, "khoi": lead["khoi"], "nguoi_quyet": lead["nguoi_quyet"], "muc": lead["muc"],
            "diem": sum(f["diem"] for f in g), "su_that": su_that, "chi_so": cs}


def gom(fs: list[dict], now: datetime, c: dict) -> list[dict]:
    """Các phát hiện cùng nhóm thành MỘT vấn đề. Nhóm chỉ có phát hiện mức thấp thì không thành vấn đề."""
    ngay = nd.ngay_hom_nay(now)
    nhom: dict[str, list] = {}
    for f in fs:
        nhom.setdefault(f["nhom"], []).append(f)
    return [_gom_nhom(k, g, ngay, c) for k, g in nhom.items() if any(f["muc"] != q.THAP for f in g)]


KHOI_MAC_DINH = "kd"                      # chưa yêu cầu khối nào thì chỉ báo khối Kinh doanh
KHOI_HOP_LE = ("kd", "dvkh")


def thu_su_that(now: datetime | None = None, toi_da: int | None = None, c: dict | None = None, khoi: str | None = None) -> tuple[list[dict], int]:
    """(các vấn đề được đề xuất, số vấn đề mức trung bình bị bỏ vì vượt trần). Mức cao xếp trước rồi điểm; mọi vấn đề mức cao luôn được giữ.
    `khoi` ("kd" / "dvkh") chỉ giữ vấn đề của khối đó; None = mọi khối."""
    now = now or utc_bay_gio()
    c = c or q.ngu_canh(now)
    toi_da = so.cau_hinh()["toi_da_van_de"] if toi_da is None else toi_da
    vs = sorted((v for v in gom(q.quet(c), now, c) if khoi is None or v["khoi"] == khoi), key=lambda v: (q.HANG_MUC[v["muc"]], -v["diem"]))
    giu = vs[:max(toi_da, sum(1 for v in vs if v["muc"] == q.CAO))]
    return giu, len(vs) - len(giu)


# ------------------------------------------------------------------ vòng chạy
def _ghi_van_de(v: dict, kq: dict, ten: dict, now: datetime) -> int | None:
    h = so.cau_hinh()
    return so.tao({"ma_van_de": v["ma_van_de"], "nhom": v["nhom"], "tieu_de": nd.hien(v["tieu_de"], ten)[:300], "khoi": v["khoi"], "nguoi_quyet": v["nguoi_quyet"],
                   "su_that": {**v["su_that"], "soan_luat_vi": kq["ly_do_luat"]}, "nhan_dinh": kq["nhan_dinh"], "phuong_an": kq["phuong_an"], "khuyen_nghi": kq["khuyen_nghi"],
                   "han_quyet": now + timedelta(hours=h["han_quyet_gio"]), "han_kiem_chung": None, "chi_so_truoc": {**v["chi_so"], "luc": now.isoformat()},
                   "nguon_noi_dung": kq["nguon_noi_dung"]}, now)


def chay_buoi_sang(now: datetime | None = None, goi_llm=MAC_DINH, gui: bool = False, khoi: str | None = None) -> dict:
    """Rà soát, tạo đề xuất cho các vấn đề CHƯA có (không tạo trùng trong ngày, không tạo khi nhóm đó còn đang theo dõi). `khoi` chỉ rà một khối (None = mọi khối).
    `gui=True` mới gửi Zalo cho người quyết, MỘT tin tổng hợp mỗi người, những đề xuất chưa tới tay họ (của khối đang rà).
    Trả {moi, gui, ai, luat, da_co, bo_qua_trung_binh, nho_con_lai, loi_nguon}."""
    if not so.bat():
        return dict(TAT)
    now = now or utc_bay_gio()
    goi = nd.goi_llm_mac_dinh() if goi_llm is MAC_DINH else goi_llm
    c = q.ngu_canh(now)
    vs, bo = thu_su_that(now, c=c, khoi=khoi)
    moi = ai = da_co = 0
    for v in vs:
        if so.doc_theo_ma(v["ma_van_de"]):
            da_co += 1
            continue
        kq = nd.soan(v, goi, c["ten"], now)
        if _ghi_van_de(v, kq, c["ten"], now):
            moi += 1
            ai += kq["nguon_noi_dung"] == "llm"
    so.ghi_phu("buoi_sang", nd.ngay_hom_nay(now))
    from app import tro_ly_dieu_hanh_zalo as tz
    return {"moi": moi, "ai": ai, "luat": moi - ai, "da_co": da_co, "bo_qua_trung_binh": bo, "loi_nguon": dict(c["loi"]), "gui": tz.gui_de_xuat_chua_gui(now, khoi) if gui else 0}


def nhac_quyet(now: datetime | None = None, gui: bool = False) -> dict:
    """Quá hạn quyết thì nhắc người quyết (một lần); quá thêm `leo_thang_gio` thì báo cấp trên (một lần) rồi đổi sang "quá hạn quyết".
    Không gửi (`gui=False`) thì không đánh dấu gì, lượt có gửi sau vẫn nhắc đủ."""
    if not so.bat():
        return dict(TAT)
    from app import tro_ly_dieu_hanh_zalo as tz
    now = now or utc_bay_gio()
    leo = timedelta(hours=so.cau_hinh()["leo_thang_gio"])
    nhac = bao = 0
    for r in so.qua_han(now) if gui else []:
        if not r["nhac_luc"] and tz.gui_cho(r["nguoi_quyet"], tz.tin_nhac(r), now):
            so.danh_dau(r["id"], "nhac_luc", now)
            nhac += 1
        if not r["leo_thang_luc"] and r["han_quyet"] + leo <= now:
            tren = cap_tren(r["nguoi_quyet"])
            if tren is None or tz.gui_cho(tren, tz.tin_leo_thang(r, ten_nguoi_quyet(r["nguoi_quyet"])), now):
                so.danh_dau(r["id"], "leo_thang_luc", now)
                so.het_han(r["id"], now)
                bao += 1
    return {"nhac": nhac, "bao_cap_tren": bao}


def kiem_chung(now: datetime | None = None, goi_llm=MAC_DINH, gui: bool = False) -> dict:
    """Quyết định tới hạn đo lại: đo bằng CÙNG hàm lúc đề xuất, ghi trước / sau và một câu kết quả; `gui=True` mới báo người quyết và Ban Giám đốc (đúng một lần)."""
    if not so.bat():
        return dict(TAT)
    from app import tro_ly_dieu_hanh_zalo as tz
    now = now or utc_bay_gio()
    cho = so.can_kiem_chung(now)
    goi = (nd.goi_llm_mac_dinh() if goi_llm is MAC_DINH else goi_llm) if cho else None
    c = q.ngu_canh(now)
    xong = 0
    for r in cho:
        cs = r["chi_so_truoc"]
        try:
            sau = q.do_chi_so(cs["loai"], cs["tham_so"], c)
        except Exception:
            continue                               # không đo lại được lượt này thì giữ nguyên "da_quyet", lượt sau thử lại
        if cs.get("gia_tri") is None:
            kq, nguon = "Không có số đo lúc đề xuất nên chưa so sánh được.", "luat"
        else:
            kq, nguon = nd.viet_lai_ket_qua(cs, sau, nd.cau_ket_qua(cs, sau), goi, c["ten"], now)
        xong += so.ghi_kiem_chung(r["id"], {"gia_tri": sau, "luc": now.isoformat()}, kq, nguon, now)
    return {"kiem_chung": xong, "da_bao": tz.bao_kiem_chung(now) if gui else 0}


def vong_tu_dong(now: datetime | None = None, goi_llm=MAC_DINH) -> dict:
    """Một vòng cho đồng hồ bên ngoài (chỉ khi `tu_dong` bật): buổi sáng đúng một lần mỗi ngày, nhắc và kiểm chứng ở mọi vòng; có gửi Zalo."""
    if not (so.bat() and so.cau_hinh()["tu_dong"]):
        return dict(TAT)
    now = now or utc_bay_gio()
    sang = {"moi": 0, "gui": 0, "ai": 0, "luat": 0}
    if so.doc_phu("buoi_sang") != nd.ngay_hom_nay(now):
        sang = chay_buoi_sang(now, goi_llm, gui=True, khoi=KHOI_MAC_DINH)
    else:
        from app import tro_ly_dieu_hanh_zalo as tz
        sang["gui"] = tz.gui_de_xuat_chua_gui(now, KHOI_MAC_DINH)
    return {**sang, **nhac_quyet(now, gui=True), **kiem_chung(now, goi_llm, gui=True)}
