"""Lead Phòng Online: một kho duy nhất thay cho nhiều tab Google Sheet theo tỉnh (chốt 16/11/2026).

Danh mục page/tỉnh (`CrmPage`) là CỦA RIÊNG Phòng Online - không liên quan `ads_page` (Ads IBB7, phòng khác).
Mỗi lead gắn với một page và một người trong 5 bạn Phòng Online (`sale_tu_van`, acc_norm lấy từ
`config/rules.yml` -> `phong_online.acc`). `cap_nhat_luc` là mốc "chăm sóc gần nhất" dùng để tính SLA
(app/canh_bao_lead.py): đổi `tinh_trang_xu_ly`, `sale_tu_van` hoặc `tu_van_1` đều coi là một lần chăm sóc.
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

TRANG_THAI = ["Mới", "Đang tư vấn", "Hẹn gọi lại", "Đồng ý", "Đã chốt", "Không nhu cầu", "Huỷ"]
TRANG_THAI_DONG = {"Đã chốt", "Không nhu cầu", "Huỷ"}        # không tính SLA / không đếm vào tải việc đang xử lý
HAN_SLA_GIO = 24
_RE_SDT = re.compile(r"(0\d{9,10})")


class LoiLead(Exception):
    """Lỗi dữ liệu / thao tác - câu tiếng Việt trả thẳng cho người dùng."""


def dam_bao_bang() -> None:
    global _da_tao
    if not _da_tao:
        for b in BANG:
            b.__table__.create(engine, checkfirst=True)
        _da_tao = True


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
    sale = (du_lieu.get("sale_tu_van") or "").strip() or None
    if not _acc_hop_le(sale):
        raise LoiLead("Sale tư vấn không hợp lệ.")
    with session_scope() as s:
        if s.get(CrmPage, int(page_id)) is None:
            raise LoiLead("Không tìm thấy page này.")
        now = datetime.utcnow()
        ngay = du_lieu.get("ngay")
        ngay = date.fromisoformat(ngay[:10]) if isinstance(ngay, str) and ngay else (ngay or date.today())
        r = Lead(page_id=int(page_id), ngay=ngay,
                 ten_kh=(du_lieu.get("ten_kh") or "").strip()[:160] or None,
                 sdt=(du_lieu.get("sdt") or "").strip()[:20] or None,
                 dia_chi=(du_lieu.get("dia_chi") or "").strip()[:200] or None,
                 nhu_cau=(du_lieu.get("nhu_cau") or "").strip()[:60] or None,
                 tinh_trang_xu_ly=(du_lieu.get("tinh_trang_xu_ly") or "Mới").strip()[:40],
                 sale_tu_van=sale, kh_dung_mang=(du_lieu.get("kh_dung_mang") or "").strip()[:60] or None,
                 mo_hinh=(du_lieu.get("mo_hinh") or "").strip()[:80] or None,
                 tu_van_1=(du_lieu.get("tu_van_1") or "").strip() or None,
                 nguon="tay", tao_luc=now, tao_boi=nguoi, cap_nhat_luc=now, cap_nhat_boi=nguoi)
        s.add(r)
        s.flush()
        s.add(AuditLog(username=nguoi, action="lead_them",
                       detail=f"#{r.id} {r.ten_kh or ''} ({r.sdt or 'không có SĐT'})"))
        return r.id


@ghi("leads")
def cap_nhat_lead(lead_id: int, du_lieu: dict, nguoi: str) -> None:
    """Sửa 1 lead. Đổi tình trạng xử lý / sale tư vấn / ghi chú tư vấn đều coi là một lần chăm sóc: ghi lại mốc
    `cap_nhat_luc` và xoá `canh_bao_luc` cũ để tính lại hạn SLA từ đầu."""
    dam_bao_bang()
    with session_scope() as s:
        r = s.get(Lead, int(lead_id))
        if r is None:
            raise LoiLead("Không tìm thấy lead này.")
        truoc = (r.tinh_trang_xu_ly, r.sale_tu_van, r.tu_van_1)
        for cot, gioi_han in (("ten_kh", 160), ("sdt", 20), ("dia_chi", 200), ("nhu_cau", 60),
                              ("tinh_trang_xu_ly", 40), ("kh_dung_mang", 60), ("sale_len", 80), ("mo_hinh", 80)):
            if cot in du_lieu:
                setattr(r, cot, str(du_lieu[cot] or "").strip()[:gioi_han] or None)
        if "sale_tu_van" in du_lieu:
            sale = (du_lieu["sale_tu_van"] or "").strip() or None
            if not _acc_hop_le(sale):
                raise LoiLead("Sale tư vấn không hợp lệ.")
            r.sale_tu_van = sale
        if "tu_van_1" in du_lieu:
            r.tu_van_1 = str(du_lieu["tu_van_1"] or "").strip() or None
        if (r.tinh_trang_xu_ly, r.sale_tu_van, r.tu_van_1) != truoc:
            r.cap_nhat_luc, r.cap_nhat_boi, r.canh_bao_luc = datetime.utcnow(), nguoi, None
        s.add(AuditLog(username=nguoi, action="lead_sua", detail=f"#{r.id}"))


@ghi("leads")
def nhan_cheo(lead_id: int, acc_nhan: str, nguoi: str) -> str:
    """Một bạn trong nhóm bấm "Nhận chéo": chuyển `sale_tu_van`, ghi người đã nhận, tính lại hạn SLA từ lúc này."""
    if not acc_nhan or not _acc_hop_le(acc_nhan):
        raise LoiLead("Người nhận chéo không hợp lệ.")
    with session_scope() as s:
        r = s.get(Lead, int(lead_id))
        if r is None:
            raise LoiLead("Không tìm thấy lead này.")
        cu = r.sale_tu_van
        r.sale_tu_van, r.care_cheo_boi = acc_nhan, acc_nhan
        r.cap_nhat_luc, r.cap_nhat_boi, r.canh_bao_luc = datetime.utcnow(), nguoi, None
        s.add(AuditLog(username=nguoi, action="lead_nhan_cheo", detail=f"#{r.id}: {cu} -> {acc_nhan}"))
    return f"Đã chuyển lead #{lead_id} cho {acc_nhan}."


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
    """Mọi lead (mới nhất lên trước), kèm `gio_tre`/`qua_han` tính theo giờ hiện tại."""
    df = _q("""SELECT l.id, l.page_id, p.ten AS tinh, l.ngay, l.ten_kh, l.sdt, l.dia_chi, l.nhu_cau,
                      l.tinh_trang_xu_ly, l.sale_tu_van, l.kh_dung_mang, l.sale_len, l.mo_hinh, l.tu_van_1,
                      l.nguon, l.care_cheo_boi, l.tao_luc, l.cap_nhat_luc, l.canh_bao_luc
               FROM crm_lead l JOIN crm_page p ON p.id = l.page_id
               ORDER BY COALESCE(l.cap_nhat_luc, l.tao_luc) DESC""")
    if df.empty:
        return df
    for c in ("tao_luc", "cap_nhat_luc", "canh_bao_luc"):
        df[c] = pd.to_datetime(df[c])
    ten = {a["acc_norm"]: a["ten"] for a in nguoi_online()}
    df["sale_ten"] = df.sale_tu_van.map(ten).fillna(df.sale_tu_van)
    moc = df.cap_nhat_luc.fillna(df.tao_luc)
    gio_tre = (pd.Timestamp(datetime.utcnow()) - moc).dt.total_seconds() / 3600
    df["gio_tre"] = gio_tre.round(1)
    df["qua_han"] = (gio_tre > HAN_SLA_GIO) & (~df.tinh_trang_xu_ly.isin(TRANG_THAI_DONG))
    if page_id:
        df = df[df.page_id == int(page_id)]
    if sale:
        df = df[df.sale_tu_van == sale]
    if tinh_trang:
        df = df[df.tinh_trang_xu_ly == tinh_trang]
    return df.reset_index(drop=True)


def tai_dang_xu_ly() -> dict[str, int]:
    """Số lead đang mở (chưa đóng) của từng acc_norm trong nhóm - dùng để gợi ý người nhận chéo (ít việc nhất)."""
    dam_bao_bang()
    placeholders = ", ".join(f":d{i}" for i in range(len(TRANG_THAI_DONG)))
    params = {f"d{i}": v for i, v in enumerate(TRANG_THAI_DONG)}
    df = _q(f"SELECT sale_tu_van, COUNT(*) AS n FROM crm_lead WHERE sale_tu_van IS NOT NULL "
            f"AND tinh_trang_xu_ly NOT IN ({placeholders}) GROUP BY sale_tu_van", **params)
    dem = dict(zip(df.sale_tu_van, df.n)) if len(df) else {}
    return {a["acc_norm"]: int(dem.get(a["acc_norm"], 0)) for a in nguoi_online()}


def de_xuat_nhan_cheo(acc_hien_tai: str | None) -> str | None:
    """Người có ít lead đang xử lý nhất trong nhóm, khác người đang phụ trách."""
    tai = tai_dang_xu_ly()
    tai.pop(acc_hien_tai, None)
    if not tai:
        return None
    return min(tai, key=lambda a: tai[a])
