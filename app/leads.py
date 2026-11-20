"""Lead Phòng Online: một kho duy nhất thay cho nhiều tab Google Sheet theo tỉnh (chốt 16/11/2026).

Danh mục page/tỉnh (`CrmPage`) là CỦA RIÊNG Phòng Online - không liên quan `ads_page` (Ads IBB7, phòng khác).
`cap_nhat_luc` là mốc "chăm sóc gần nhất" dùng để tính SLA (app/canh_bao_lead.py): đổi `tinh_trang_xu_ly`,
người phụ trách hoặc `ghi_chu` đều coi là một lần chăm sóc.

**Sale 1/2/3** (chốt 20/11/2026, thay cơ chế "sửa ô Sale tư vấn = nhận chéo" cũ): lead gắn với MỘT người
trong 5 bạn Phòng Online vào `sale_1` lúc tạo; quá hạn mà người khác nhận thì vào `sale_2`, dội tiếp thì
`sale_3` (dội quá 3 lần thì ghi đè `sale_3`). `nguoi_phu_trach()` = ô CUỐI CÙNG đã điền - đây mới là người
dùng để tính SLA / KHTN / báo Zalo, không phải `sale_1`. Thao tác "nhận" (`nhan_cheo`) tự tìm đúng ô trống
kế tiếp để điền, không cần biết người gọi đang sửa ô nào.

**Ghi chú** (chốt 20/11/2026): gộp 5 ô ít dùng trước đây (Địa chỉ, Nhu cầu, KH dùng mạng, Mô hình, Tư vấn)
thành một ô ghi chú tự do `ghi_chu`.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime

import pandas as pd
from sqlalchemy import select, text

from app import phong_online as po
from app.bo_nho import ghi, nho
from app.db import engine, session_scope
from app.models import AuditLog, CrmPage, Employee, Lead, StaffMap

BANG = (CrmPage, Lead)
_da_tao = False
# cột thêm sau 16/11/2026, phải tự vá vào database đang chạy (cùng cách bao_cao_ngay.COT_THEM)
COT_THEM = {"sale_2": "VARCHAR(80)", "sale_3": "VARCHAR(80)", "ghi_chu": "TEXT"}

TRANG_THAI = ["Mới", "Đang tư vấn", "Hẹn gọi lại", "Đồng ý", "Đã chốt", "Đã lên online", "Không nhu cầu", "Huỷ"]
# "Đã lên online" (thêm 19/11/2026): dịch vụ đã kích hoạt xong, khác "Đã chốt" (mới là khách đồng ý/tạo HĐ) -
# để phân biệt "chốt nhưng chưa lắp" với "đã lắp xong" khi xem lại. Không tính SLA / không đếm vào tải việc
# đang xử lý, giống các trạng thái đóng khác.
TRANG_THAI_DONG = {"Đã chốt", "Đã lên online", "Không nhu cầu", "Huỷ"}
HAN_SLA_GIO = 24
_RE_SDT = re.compile(r"(0\d{9,10})")


class LoiLead(Exception):
    """Lỗi dữ liệu / thao tác - câu tiếng Việt trả thẳng cho người dùng."""


def dam_bao_bang() -> None:
    global _da_tao
    if not _da_tao:
        for b in BANG:
            b.__table__.create(engine, checkfirst=True)
        from sqlalchemy import inspect
        co = {c["name"] for c in inspect(engine).get_columns("crm_lead")}
        for ten, kieu in COT_THEM.items():
            if ten not in co:
                with engine.begin() as c:
                    c.execute(text(f"ALTER TABLE crm_lead ADD COLUMN {ten} {kieu}"))
        _da_tao = True


def nguoi_phu_trach(sale_1, sale_2, sale_3) -> str | None:
    """Người ĐANG phụ trách lead = ô cuối cùng đã điền trong sale_1 -> sale_2 -> sale_3. Đây là người dùng
    để tính SLA / KHTN / báo Zalo, không phải `sale_1` (người nhận đầu tiên có thể đã bị dội từ lâu)."""
    return sale_3 or sale_2 or sale_1


def tim_sdt(chu: str | None) -> str | None:
    """Bắt số điện thoại Việt Nam trong tin nhắn thô (Messenger) - không chặn nếu không thấy."""
    m = _RE_SDT.search(str(chu or "").replace(" ", "").replace(".", "").replace("-", ""))
    return m.group(1) if m else None


def _khoa_ten(ten) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(ten or ""))).strip().lower()


# ------------------------------------------------------------------ 5 bạn Phòng Online
@nho("leads")
def nguoi_online() -> list[dict]:
    """5 bạn Phòng Online: acc_norm + tên hiển thị (ưu tiên NSLĐ, dự phòng danh mục nhân sự, cuối cùng phần
    sau dấu chấm của acc)."""
    accs = po.acc_nhom()
    if not accs:
        return []
    with session_scope() as s:
        emp = {e.acc_norm: e.ho_ten for e in s.execute(
            select(Employee).where(Employee.acc_norm.in_(accs))).scalars() if e.ho_ten}
        sm = {m.acc_norm: m.ten_hien_thi for m in s.execute(
            select(StaffMap).where(StaffMap.acc_norm.in_(accs))).scalars() if m.ten_hien_thi}
    return [{"acc_norm": a, "ten": emp.get(a) or sm.get(a) or a.split(".")[-1]} for a in accs]


def _acc_hop_le(acc: str | None) -> bool:
    return not acc or acc in {a["acc_norm"] for a in nguoi_online()}


# ------------------------------------------------------------------ danh mục page/tỉnh (RIÊNG Phòng Online)
@nho("leads")
def ds_page() -> pd.DataFrame:
    dam_bao_bang()
    return pd.read_sql_query(text("SELECT id, ten, ghi_chu, fb_page_id, active FROM crm_page "
                                  "ORDER BY ten"), engine)


@ghi("leads")
def them_page(ten: str, ghi_chu: str | None, nguoi: str) -> str:
    dam_bao_bang()
    ten = re.sub(r"\s+", " ", str(ten or "")).strip()
    if not ten:
        raise LoiLead("Nhập tên page / tỉnh.")
    with session_scope() as s:
        trung = [p.ten for p in s.execute(select(CrmPage)).scalars() if _khoa_ten(p.ten) == _khoa_ten(ten)]
        if trung:
            raise LoiLead(f"Đã có page '{trung[0]}'.")
        s.add(CrmPage(ten=ten[:120], ghi_chu=(ghi_chu or "").strip()[:200] or None))
        s.add(AuditLog(username=nguoi, action="lead_them_page", detail=ten))
    return f"Đã thêm page {ten}."


@ghi("leads")
def sua_page(page_id: int, ten: str | None, ghi_chu: str | None, active: bool, nguoi: str) -> str:
    dam_bao_bang()
    with session_scope() as s:
        p = s.get(CrmPage, int(page_id))
        if p is None:
            raise LoiLead("Không tìm thấy page này.")
        if ten:
            ten = re.sub(r"\s+", " ", ten).strip()
            trung = [x.ten for x in s.execute(select(CrmPage)).scalars()
                    if x.id != p.id and _khoa_ten(x.ten) == _khoa_ten(ten)]
            if trung:
                raise LoiLead(f"Tên '{ten}' đang dùng cho page khác.")
            p.ten = ten[:120]
        if ghi_chu is not None:
            p.ghi_chu = ghi_chu.strip()[:200] or None
        p.active = bool(active)
        s.add(AuditLog(username=nguoi, action="lead_sua_page", detail=f"{p.id}: {p.ten}"))
    return f"Đã lưu page {p.ten}."


@ghi("leads")
def luu_fb_cau_hinh(page_id: int, fb_page_id: str, token: str, nguoi: str) -> str:
    """Gắn Facebook Page ID + Page Access Token cho webhook Messenger tự bắt lead (Giai đoạn B)."""
    dam_bao_bang()
    fb_page_id, token = str(fb_page_id or "").strip(), str(token or "").strip()
    if not fb_page_id or not token:
        raise LoiLead("Nhập đủ Facebook Page ID và Page Access Token.")
    with session_scope() as s:
        p = s.get(CrmPage, int(page_id))
        if p is None:
            raise LoiLead("Không tìm thấy page này.")
        trung = s.execute(select(CrmPage).where(CrmPage.fb_page_id == fb_page_id,
                                                CrmPage.id != p.id)).scalars().first()
        if trung:
            raise LoiLead(f"Facebook Page ID này đang gắn cho page '{trung.ten}'.")
        p.fb_page_id, p.page_access_token = fb_page_id, token
        s.add(AuditLog(username=nguoi, action="lead_fb_cau_hinh", detail=f"{p.ten} -> fb {fb_page_id}"))
    return f"Đã lưu kết nối Messenger cho {p.ten}."


# ------------------------------------------------------------------ lead
@ghi("leads")
def tao_lead(du_lieu: dict, nguoi: str) -> int:
    """Thêm 1 lead nhập tay (thay thao tác gõ vào Google Sheet). Trả về id lead mới."""
    dam_bao_bang()
    page_id = du_lieu.get("page_id")
    if not page_id:
        raise LoiLead("Chọn page / tỉnh.")
    sale = (du_lieu.get("sale_1") or "").strip() or None
    if not _acc_hop_le(sale):
        raise LoiLead("Sale 1 không hợp lệ.")
    with session_scope() as s:
        if s.get(CrmPage, int(page_id)) is None:
            raise LoiLead("Không tìm thấy page này.")
        now = datetime.utcnow()
        ngay = du_lieu.get("ngay")
        ngay = date.fromisoformat(ngay[:10]) if isinstance(ngay, str) and ngay else (ngay or date.today())
        r = Lead(page_id=int(page_id), ngay=ngay,
                 ten_kh=(du_lieu.get("ten_kh") or "").strip()[:160] or None,
                 sdt=(du_lieu.get("sdt") or "").strip()[:20] or None,
                 tinh_trang_xu_ly=(du_lieu.get("tinh_trang_xu_ly") or "Mới").strip()[:40],
                 sale_1=sale, ghi_chu=(du_lieu.get("ghi_chu") or "").strip() or None,
                 nguon="tay", tao_luc=now, tao_boi=nguoi, cap_nhat_luc=now, cap_nhat_boi=nguoi)
        s.add(r)
        s.flush()
        s.add(AuditLog(username=nguoi, action="lead_them",
                       detail=f"#{r.id} {r.ten_kh or ''} ({r.sdt or 'không có SĐT'})"))
        return r.id


@ghi("leads")
def cap_nhat_lead(lead_id: int, du_lieu: dict, nguoi: str) -> None:
    """Sửa 1 lead (KHÔNG gồm Sale 1/2/3 - dùng `nhan_cheo` để nhận lead). Đổi tình trạng xử lý hoặc ghi chú
    đều coi là một lần chăm sóc: ghi lại mốc `cap_nhat_luc` và xoá `canh_bao_luc` cũ để tính lại hạn SLA."""
    dam_bao_bang()
    with session_scope() as s:
        r = s.get(Lead, int(lead_id))
        if r is None:
            raise LoiLead("Không tìm thấy lead này.")
        truoc = (r.tinh_trang_xu_ly, r.ghi_chu)
        for cot, gioi_han in (("ten_kh", 160), ("sdt", 20), ("tinh_trang_xu_ly", 40), ("sale_len", 80)):
            if cot in du_lieu:
                setattr(r, cot, str(du_lieu[cot] or "").strip()[:gioi_han] or None)
        if "ghi_chu" in du_lieu:
            r.ghi_chu = str(du_lieu["ghi_chu"] or "").strip() or None
        if (r.tinh_trang_xu_ly, r.ghi_chu) != truoc:
            r.cap_nhat_luc, r.cap_nhat_boi, r.canh_bao_luc = datetime.utcnow(), nguoi, None
        s.add(AuditLog(username=nguoi, action="lead_sua", detail=f"#{r.id}"))


@ghi("leads")
def nhan_cheo(lead_id: int, acc_nhan: str, nguoi: str) -> str:
    """Nhận lead: điền vào Ô TRỐNG KẾ TIẾP trong sale_1 -> sale_2 -> sale_3 (chốt 20/11/2026, thay cơ chế
    "sửa ô Sale tư vấn" cũ). sale_1 trống thì đây là lần gán đầu; sale_1 đã có thì đây là lần dội đầu tiên
    (vào sale_2); sale_2 cũng đã có thì vào sale_3 - dội quá 3 lần thì GHI ĐÈ sale_3 (không chặn quy trình
    vì giới hạn giao diện). Luôn tính lại hạn SLA từ lúc này vì người phụ trách vừa đổi."""
    if not acc_nhan or not _acc_hop_le(acc_nhan):
        raise LoiLead("Người nhận không hợp lệ.")
    with session_scope() as s:
        r = s.get(Lead, int(lead_id))
        if r is None:
            raise LoiLead("Không tìm thấy lead này.")
        cu = nguoi_phu_trach(r.sale_1, r.sale_2, r.sale_3)
        if not r.sale_1:
            r.sale_1 = acc_nhan
        elif not r.sale_2:
            r.sale_2 = acc_nhan
        else:
            r.sale_3 = acc_nhan
        r.cap_nhat_luc, r.cap_nhat_boi, r.canh_bao_luc = datetime.utcnow(), nguoi, None
        s.add(AuditLog(username=nguoi, action="lead_nhan_cheo", detail=f"#{r.id}: {cu} -> {acc_nhan}"))
    return f"Đã gán lead #{lead_id} cho {acc_nhan}."


@ghi("leads")
def xoa_lead(ids: list[int], nguoi: str) -> int:
    dam_bao_bang()
    with session_scope() as s:
        n = 0
        for i in ids:
            r = s.get(Lead, int(i))
            if r:
                s.delete(r)
                n += 1
        s.add(AuditLog(username=nguoi, action="lead_xoa", detail=f"{n} dòng"))
    return n


def _q(sql: str, **p) -> pd.DataFrame:
    dam_bao_bang()
    return pd.read_sql_query(text(sql), engine, params=p)


@nho("leads", 10)
def danh_sach(page_id: int | None = None, sale: str | None = None, tinh_trang: str | None = None) -> pd.DataFrame:
    """Mọi lead (mới nhất lên trước), kèm `gio_tre`/`qua_han` tính theo giờ hiện tại và `phu_trach` (người
    đang phụ trách - ô cuối cùng trong sale_1/2/3 đã điền, xem `nguoi_phu_trach`)."""
    df = _q("""SELECT l.id, l.page_id, p.ten AS tinh, l.ngay, l.ten_kh, l.sdt, l.ghi_chu,
                      l.tinh_trang_xu_ly, l.sale_tu_van AS sale_1, l.sale_2, l.sale_3, l.sale_len,
                      l.nguon, l.tao_luc, l.cap_nhat_luc, l.canh_bao_luc
               FROM crm_lead l JOIN crm_page p ON p.id = l.page_id
               ORDER BY COALESCE(l.cap_nhat_luc, l.tao_luc) DESC""")
    if df.empty:
        return df
    for c in ("tao_luc", "cap_nhat_luc", "canh_bao_luc"):
        df[c] = pd.to_datetime(df[c])
    ten = {a["acc_norm"]: a["ten"] for a in nguoi_online()}
    for c in ("sale_1", "sale_2", "sale_3"):
        df[f"{c}_ten"] = df[c].map(ten).fillna(df[c])
    df["phu_trach"] = df.sale_3.fillna(df.sale_2).fillna(df.sale_1)
    moc = df.cap_nhat_luc.fillna(df.tao_luc)
    gio_tre = (pd.Timestamp(datetime.utcnow()) - moc).dt.total_seconds() / 3600
    df["gio_tre"] = gio_tre.round(1)
    df["qua_han"] = (gio_tre > HAN_SLA_GIO) & (~df.tinh_trang_xu_ly.isin(TRANG_THAI_DONG))
    if page_id:
        df = df[df.page_id == int(page_id)]
    if sale:
        df = df[df.phu_trach == sale]
    if tinh_trang:
        df = df[df.tinh_trang_xu_ly == tinh_trang]
    return df.reset_index(drop=True)


def tai_dang_xu_ly() -> dict[str, int]:
    """Số lead đang mở (chưa đóng) của từng acc_norm trong nhóm, tính theo NGƯỜI ĐANG PHỤ TRÁCH (sale_3 nếu
    có, không thì sale_2, không thì sale_1) - dùng để gợi ý người nhận chéo (ít việc nhất)."""
    dam_bao_bang()
    placeholders = ", ".join(f":d{i}" for i in range(len(TRANG_THAI_DONG)))
    params = {f"d{i}": v for i, v in enumerate(TRANG_THAI_DONG)}
    df = _q(f"""SELECT COALESCE(sale_3, sale_2, sale_tu_van) AS acc, COUNT(*) AS n FROM crm_lead
                WHERE COALESCE(sale_3, sale_2, sale_tu_van) IS NOT NULL
                  AND tinh_trang_xu_ly NOT IN ({placeholders}) GROUP BY acc""", **params)
    dem = dict(zip(df.acc, df.n)) if len(df) else {}
    return {a["acc_norm"]: int(dem.get(a["acc_norm"], 0)) for a in nguoi_online()}


def de_xuat_nhan_cheo(acc_hien_tai: str | None) -> str | None:
    """Người có ít lead đang xử lý nhất trong nhóm, khác người đang phụ trách."""
    tai = tai_dang_xu_ly()
    tai.pop(acc_hien_tai, None)
    if not tai:
        return None
    return min(tai, key=lambda a: tai[a])
