"""Báo cáo đầu ngày của phòng kinh doanh (thay sheet "Mục tiêu và công việc đầu ngày").

Chốt với chủ app 24/09/2026:
- Sale nhập 6 ô: mục tiêu bán hôm nay, KHTN đang có, dự kiến online sáng, dự kiến online chiều,
  đã online, ghi chú. PTTB luỹ kế tháng và số V.VIP app tự lấy từ file đã nạp, để luôn khớp
  Báo cáo phòng - không có hai nguồn số.
- "Đã online" (chốt 25/09/2026): file Internet chỉ về vào hôm sau nên buổi sáng số từ file luôn
  bằng 0, "còn phải online" thành vô nghĩa. Cho sale gõ tay, và lấy số LỚN HƠN giữa số gõ tay và
  số từ file: file chỉ có thể chậm chứ không đếm dư, nên cách này không bao giờ báo thiếu.
- Mục tiêu tháng của từng người nhập ngay trong bảng này, lưu vào `target_monthly` với
  `doi_tuong = "NHAN_VIEN"` (mọi chỗ khác đều lọc `doi_tuong = 'PHONG'` nên không đụng nhau).
  Mục tiêu PTTB/ngày của phòng dùng chung ô `chi_tieu = "ngay"` đã có sẵn của Báo cáo Tổng.
- "Pay" trong ảnh báo cáo = số V.VIP luỹ kế tháng của người đó, đếm từ file FPT Play
  (`_vvip_theo_acc`) đúng như Báo cáo Tổng và Báo cáo phòng.
- Dự kiến online tổng = sáng + chiều (không nhập riêng); còn phải online = tổng dự kiến - đã online.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select, text

from app import phan_tich as pt
from app.bo_nho import xoa
from app.db import engine, session_scope
from app.metrics import month_range
from app.models import AuditLog, BaoCaoNgay, BaoCaoNgayChu, Target
from app.thoi_gian import gio_viet_nam, utc_bay_gio

O_NHAP = ("muc_tieu", "khtn", "onl_sang", "onl_chieu", "da_online", "ghi_chu")
GHI_CHU_TOI_DA = 400
TOI_DA = 999                       # chặn gõ nhầm 9999
_da_tao = False


class LoiBaoCao(ValueError):
    """Lỗi hiện thẳng cho người dùng (đã viết bằng tiếng Việt)."""


def dam_bao_bang() -> None:
    global _da_tao
    if not _da_tao:
        BaoCaoNgay.__table__.create(engine, checkfirst=True)
        BaoCaoNgayChu.__table__.create(engine, checkfirst=True)
        from sqlalchemy import inspect
        if "da_online" not in {c["name"] for c in inspect(engine).get_columns("bao_cao_ngay")}:
            with engine.begin() as c:                                  # cột thêm sau (25/09/2026)
                c.execute(text("ALTER TABLE bao_cao_ngay ADD COLUMN da_online INTEGER"))
        _da_tao = True


def hom_nay() -> date:
    return gio_viet_nam().date()


def cau_hinh() -> dict:
    from app.config import rules_config
    c = rules_config().get("bao_cao_ngay") or {}
    return {"phong": list(c.get("phong") or [])}


# ------------------------------------------------------------------ mục tiêu (dùng lại target_monthly)
def _muc_tieu(thang: str, doi_tuong: str, ma: str, chi_tieu: str) -> float | None:
    with engine.connect() as c:
        return c.execute(text("""SELECT gia_tri FROM target_monthly WHERE thang = :t AND doi_tuong = :d
                                 AND ma_doi_tuong = :m AND chi_tieu = :k"""),
                         {"t": thang, "d": doi_tuong, "m": ma, "k": chi_tieu}).scalar()


def dat_muc_tieu(thang: str, doi_tuong: str, ma: str, chi_tieu: str, gia_tri: float, nguoi: str) -> None:
    """Ghi một ô mục tiêu. Dùng cho cả mục tiêu tháng từng người và mục tiêu PTTB/ngày của phòng."""
    if gia_tri < 0 or gia_tri > 100000:
        raise LoiBaoCao("Mục tiêu không hợp lệ.")
    with session_scope() as s:
        r = s.execute(select(Target).where(Target.thang == thang, Target.doi_tuong == doi_tuong,
                                           Target.ma_doi_tuong == ma, Target.chi_tieu == chi_tieu)
                      ).scalars().first()
        if r is None:
            r = Target(thang=thang, doi_tuong=doi_tuong, ma_doi_tuong=ma, chi_tieu=chi_tieu)
            s.add(r)
        r.gia_tri = float(gia_tri)
        s.add(AuditLog(username=nguoi, action="sua_muc_tieu",
                       detail=f"{thang} {doi_tuong} {ma} {chi_tieu} = {gia_tri:g}"))
    xoa("so_lieu")


def _mt_nhan_vien(thang: str) -> pd.Series:
    df = pd.read_sql_query(text("""SELECT ma_doi_tuong, gia_tri FROM target_monthly
                                   WHERE thang = :t AND doi_tuong = 'NHAN_VIEN' AND chi_tieu = 'internet'"""),
                           engine, params={"t": thang})
    return df.set_index("ma_doi_tuong").gia_tri if len(df) else pd.Series(dtype=float)


# ------------------------------------------------------------------ bảng của một ngày
def _da_nhap(ngay: date, phong: list[str]) -> pd.DataFrame:
    df = pd.read_sql_query(text("SELECT * FROM bao_cao_ngay WHERE ngay = :n"), engine,
                           params={"n": ngay.isoformat()})
    if df.empty:
        return pd.DataFrame(columns=["acc_norm", *O_NHAP])
    return df[df.phong_code.isin(set(phong))][["acc_norm", *O_NHAP]]


def _vvip_theo_acc(phong: list[str], tu: str, den: str) -> pd.Series:
    """Số V.VIP luỹ kế của từng người, đếm ĐÚNG cách Báo cáo Tổng và Báo cáo phòng đang đếm:
    mỗi dòng `la_vvip` trong file FPT Play là một V.VIP, tính theo ngày online của chính gói đó.

    Không đếm gián tiếp qua cờ V.VIP của hợp đồng Internet: gói V.VIP có thể online khác ngày với
    hợp đồng Internet, hoặc bán thêm trên hợp đồng của tháng trước, nên đếm kiểu đó sẽ lệch với
    Báo cáo phòng (đã đo trên IBB7 tháng 9: lệch 2 V.VIP, 4 người sai).
    """
    if not phong:
        return pd.Series(dtype=int)
    ma = {f"p{i}": c for i, c in enumerate(phong)}
    cho = ", ".join(f":{k}" for k in ma)
    df = pd.read_sql_query(text(f"""SELECT acc_norm, COUNT(*) AS n FROM fact_fptplay
                                    WHERE phong_code IN ({cho}) AND la_vvip = TRUE
                                      AND ngay_online >= :tu AND ngay_online <= :den
                                    GROUP BY acc_norm"""),
                           engine, params={**ma, "tu": tu, "den": den})
    return df.set_index("acc_norm")["n"] if not df.empty else pd.Series(dtype=int)


def bang(phong: list[str], ngay: date | None = None) -> pd.DataFrame:
    """Mỗi dòng một nhân sự của phòng: 6 ô sale nhập + các số app tự lấy.

    Danh sách người = người có bán trong tháng, cộng người đã nhập báo cáo hôm nay (người mới chưa có số)."""
    dam_bao_bang()
    ngay = ngay or hom_nay()
    thang = f"{ngay:%Y-%m}"
    dau, _, _ = month_range(thang)
    hd = pt.hop_dong_online(dau.isoformat(), ngay.isoformat(), list(phong))
    vvip = _vvip_theo_acc(phong, dau.isoformat(), ngay.isoformat())
    nhap = _da_nhap(ngay, phong)
    if hd.empty and nhap.empty and vvip.empty:
        return pd.DataFrame()

    g = (hd.groupby("acc_norm").agg(acc=("acc_nhan_vien", "first"), phong_code=("phong_code", "first"),
                                    pttb_thang=("hop_dong", "size"))
         if len(hd) else pd.DataFrame(columns=["acc", "phong_code", "pttb_thang"],
                                      index=pd.Index([], name="acc_norm")))
    hom = hd[hd.ngay_online.dt.date == ngay] if len(hd) else hd
    g["onl_file"] = (hom.groupby("acc_norm").size().reindex(g.index).fillna(0).astype(int)
                     if len(g) else pd.Series(dtype=int))
    df = g.reset_index()
    # người chỉ bán V.VIP (chưa có hợp đồng Internet online) cũng phải có dòng, nếu không
    # dòng TỔNG sẽ thiếu V.VIP so với Báo cáo phòng
    thieu = (set(nhap.acc_norm) | set(vvip.index)) - set(df.acc_norm)
    if thieu:
        them = pd.DataFrame({"acc_norm": sorted(thieu), "acc": sorted(thieu), "phong_code": phong[0],
                             "pttb_thang": 0, "onl_file": 0})
        df = pd.concat([df, them], ignore_index=True)
    df["vvip_thang"] = df.acc_norm.map(vvip).fillna(0).astype(int)

    ten = pd.read_sql_query(text("SELECT acc_norm, ho_ten FROM dim_employee WHERE acc_norm IS NOT NULL"), engine)
    ten = ten.drop_duplicates("acc_norm").set_index("acc_norm").ho_ten
    df["ho_ten"] = df.acc_norm.map(ten).fillna(df.acc)
    df["mt_thang"] = df.acc_norm.map(_mt_nhan_vien(thang)).fillna(0).astype(int)
    df = df.merge(nhap, on="acc_norm", how="left")
    for c in ("muc_tieu", "khtn", "onl_sang", "onl_chieu"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    df["ghi_chu"] = df.ghi_chu.where(df.ghi_chu.notna(), "")
    # "Đã online": lấy số LỚN HƠN giữa số sale gõ tay và số từ file. File Internet chỉ về vào hôm sau
    # nên buổi sáng số file luôn 0; ngược lại file có thể ghi nhận ca sale chưa kịp đếm. File không
    # bao giờ đếm dư, nên lấy số lớn hơn thì không bao giờ báo thiếu.
    df["da_online"] = pd.to_numeric(df.get("da_online"), errors="coerce")
    df["thuc_hien"] = df[["onl_file", "da_online"]].max(axis=1).fillna(0).astype(int)
    df["dk_onl"] = df.onl_sang + df.onl_chieu
    df["con_phai_onl"] = (df.dk_onl - df.thuc_hien).clip(lower=0)
    df["da_nhap"] = df.acc_norm.isin(set(nhap.acc_norm))       # đã có bản ghi hôm nay hay chưa
    df["id"] = df.acc_norm
    cot = ["id", "acc_norm", "acc", "ho_ten", "phong_code", "muc_tieu", "khtn", "onl_sang", "onl_chieu",
           "dk_onl", "thuc_hien", "con_phai_onl", "pttb_thang", "mt_thang", "vvip_thang", "ghi_chu", "da_nhap"]
    return df[cot].sort_values(["pttb_thang", "ho_ten"], ascending=[False, True]).reset_index(drop=True)


def tom_tat(phong: list[str], ngay: date | None = None) -> dict:
    """Ba khối số đầu ảnh báo cáo: kết quả hôm qua, tình hình sáng nay, luỹ kế tháng."""
    ngay = ngay or hom_nay()
    thang = f"{ngay:%Y-%m}"
    dau, _, _ = month_range(thang)
    df = bang(phong, ngay)
    hd = pt.hop_dong_online(dau.isoformat(), ngay.isoformat(), list(phong))
    hqua = ngay - timedelta(days=1)
    onl_hqua = int((hd.ngay_online.dt.date == hqua).sum()) if len(hd) else 0
    mt_ngay = int(_muc_tieu(thang, "PHONG", phong[0], "ngay") or 0) if len(phong) == 1 else 0
    mt_thang = sum(int(_muc_tieu(thang, "PHONG", c, "internet") or 0) for c in phong)
    luy_ke = len(hd)
    s = (lambda c: int(df[c].sum())) if not df.empty else (lambda c: 0)
    return {
        "ngay": ngay, "hom_qua": hqua, "thang": thang,
        "hq_thuc_te": onl_hqua, "hq_muc_tieu": mt_ngay,
        "hq_thieu": max(mt_ngay - onl_hqua, 0), "hq_ty_le": round(onl_hqua / mt_ngay * 100) if mt_ngay else 0,
        "khtn": s("khtn"), "mt_ngay": mt_ngay, "mt_ngay_nhap": s("muc_tieu"),
        "onl_sang": s("onl_sang"), "onl_chieu": s("onl_chieu"), "dk_onl": s("dk_onl"),
        "da_online": s("thuc_hien"), "con_phai_onl": max(s("dk_onl") - s("thuc_hien"), 0),
        "luy_ke": luy_ke, "mt_thang": mt_thang, "con_thieu": max(mt_thang - luy_ke, 0),
        "ty_le_thang": round(luy_ke / mt_thang * 100, 1) if mt_thang else 0.0,
        "vvip_thang": s("vvip_thang"),
        "so_nguoi": len(df), "chua_nhap": int((~df.da_nhap).sum()) if not df.empty else 0,
    }


# ------------------------------------------------------------------ ghi
def _so(v) -> int:
    try:
        n = int(float(v or 0))
    except (TypeError, ValueError):
        raise LoiBaoCao("Chỉ được nhập số.") from None
    if n < 0 or n > TOI_DA:
        raise LoiBaoCao(f"Số phải trong khoảng 0 - {TOI_DA}.")
    return n


def luu(acc_norm: str, truong: dict, phong: list[str], nguoi: str, ngay: date | None = None,
        ghi_ten: str | None = None) -> None:
    """Ghi phần sale nhập cho một người.

    Tài khoản sale dùng chung sửa được mọi dòng (chủ app chốt 24/09/2026); `ghi_ten` là tên người đang
    chọn ở ô "Tôi là", lưu vào "cập nhật bởi" để Trưởng phòng biết ai sửa - nhật ký vẫn ghi tài khoản thật."""
    dam_bao_bang()
    ngay = ngay or hom_nay()
    d = {}
    for k, v in truong.items():
        if k not in O_NHAP:
            continue
        d[k] = (str(v or "").strip()[:GHI_CHU_TOI_DA] or None) if k == "ghi_chu" else _so(v)
    if not d:
        return
    code = _phong_cua(acc_norm, phong)
    with session_scope() as s:
        r = s.execute(select(BaoCaoNgay).where(BaoCaoNgay.ngay == ngay,
                                               BaoCaoNgay.acc_norm == acc_norm)).scalars().first()
        if r is None:
            r = BaoCaoNgay(ngay=ngay, acc_norm=acc_norm, phong_code=code)
            s.add(r)
        for k, v in d.items():
            setattr(r, k, v)
        r.cap_nhat_luc, r.cap_nhat_boi = utc_bay_gio(), (ghi_ten or nguoi)[:60]


def _phong_cua(acc_norm: str, phong: list[str]) -> str:
    with engine.connect() as c:
        code = c.execute(text("""SELECT phong_code FROM fact_internet WHERE acc_norm = :a
                                 AND phong_code IS NOT NULL ORDER BY ngay_online DESC LIMIT 1"""),
                         {"a": acc_norm}).scalar()
    return code if code in set(phong) else phong[0]


def chu(phong_code: str, ngay: date | None = None) -> dict:
    dam_bao_bang()
    ngay = ngay or hom_nay()
    with session_scope() as s:
        r = s.execute(select(BaoCaoNgayChu).where(BaoCaoNgayChu.ngay == ngay,
                                                  BaoCaoNgayChu.phong_code == phong_code)).scalars().first()
        return {"trong_tam": r.trong_tam or "", "nhan_dinh": r.nhan_dinh or "",
                "thong_diep": r.thong_diep or ""} if r else {"trong_tam": "", "nhan_dinh": "", "thong_diep": ""}


def luu_chu(phong_code: str, moi: dict, nguoi: str, ngay: date | None = None) -> None:
    dam_bao_bang()
    ngay = ngay or hom_nay()
    with session_scope() as s:
        r = s.execute(select(BaoCaoNgayChu).where(BaoCaoNgayChu.ngay == ngay,
                                                  BaoCaoNgayChu.phong_code == phong_code)).scalars().first()
        if r is None:
            r = BaoCaoNgayChu(ngay=ngay, phong_code=phong_code)
            s.add(r)
        for k in ("trong_tam", "nhan_dinh", "thong_diep"):
            if k in moi:
                setattr(r, k, (moi[k] or "").strip() or None)
        r.cap_nhat_luc, r.cap_nhat_boi = utc_bay_gio(), nguoi[:60]
