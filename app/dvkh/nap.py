"""Ghi dữ liệu file DVKH vào database.

Mỗi lần nạp là bản chụp luỹ kế của tháng: dòng SR đã có thì thay bằng trạng thái mới nhất (khoá = Mã SR), không cộng
dồn. Rời mạng và công nợ lưu theo ngày chốt / ngày thu nên nạp lại cùng ngày thì ghi đè.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import delete, insert, inspect, select

from app.bo_nho import ghi
from app.db import Base, engine, session_scope
from app.dvkh import doc_file as df_
from app.dvkh.models import (DvAuKh, DvCongNo, DvCongNoChot, DvDanhSach, DvNap, DvRoiMang, DvSrBdThem, DvSrBiDong, DvSrChuDong)
from app.models import AuditLog

BANG = [DvNap, DvSrBiDong, DvSrChuDong, DvRoiMang, DvCongNo, DvCongNoChot, DvDanhSach]
BANG_THEM = [DvSrBdThem, DvAuKh]            # bảng bổ sung: chỉ được tạo khi nạp file (người nạp chủ động), trang chỉ đọc nếu đã có
KICH_CO_LO = 500
_DA_CO_BANG: set[str] = set()
_DA_TAO = {"goc": False, "them": False}


def dam_bao_bang(them: bool = False) -> None:
    """Tạo các bảng dv_* nếu chưa có (không đụng bảng khác). `them=True` tạo cả bảng bổ sung (chỉ lúc nạp file).

    Mỗi bảng chỉ kiểm tra một lần cho mỗi tiến trình: kiểm tra mỗi lượt mở trang là bảy câu hỏi database thừa."""
    khoa = "them" if them else "goc"
    if _DA_TAO[khoa]:
        return
    Base.metadata.create_all(engine, tables=[m.__table__ for m in BANG + (BANG_THEM if them else [])])
    _DA_TAO[khoa] = True
    if them:
        _DA_TAO["goc"] = True


def co_bang(ten: str) -> bool:
    """Bảng bổ sung đã có trong database chưa. Chưa nạp lại file sau khi thêm tính năng thì trang bỏ qua phần đó thay vì lỗi."""
    if ten in _DA_CO_BANG:
        return True
    if inspect(engine).has_table(ten):
        _DA_CO_BANG.add(ten)
        return True
    return False


def _gia_tri(v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime()
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        return v.item()
    return v


def _dong(df: pd.DataFrame, cot: set[str], them: dict) -> list[dict]:
    keep = [c for c in df.columns if c in cot]
    out = []
    for r in df[keep].itertuples(index=False, name=None):
        d = {c: _gia_tri(v) for c, v in zip(keep, r)}
        out.append({**{c: None for c in cot}, **d, **them})
    return out


def _chen_lo(s, model, dong: list[dict]) -> None:
    for i in range(0, len(dong), KICH_CO_LO):
        s.execute(insert(model), dong[i:i + KICH_CO_LO])


def _thay_sr(s, model, df: pd.DataFrame, them: dict, ma_hd_flag: dict[str, set[str]]) -> int:
    """Xoá các dòng cùng Mã SR rồi chèn bản mới - gọn hơn so với cập nhật từng dòng."""
    if df.empty:
        return 0
    df = df.copy()
    for cot, tap in ma_hd_flag.items():
        df[cot] = df["so_hd"].map(lambda h: int(h in tap) if isinstance(h, str) else 0)
    df["ngay_yc" if "tg_yc" in df.columns else "ngay_do"] = (
        df["tg_yc" if "tg_yc" in df.columns else "tg_do"].dt.date)
    cot = {c.name for c in model.__table__.columns} - {"updated_at"}
    dong = _dong(df, cot, them)
    ma = [d["ma_sr"] for d in dong]
    for i in range(0, len(ma), KICH_CO_LO):
        s.execute(delete(model).where(model.ma_sr.in_(ma[i:i + KICH_CO_LO])))
    _chen_lo(s, model, dong)
    return len(dong)


def _thay_them(s, df: pd.DataFrame | None, batch_id: int) -> None:
    """Cột bổ sung của SR bị động: xoá dòng cùng Mã SR rồi chèn bản mới, như bảng SR chính."""
    if df is None or df.empty:
        return
    dong = _dong(df, {c.name for c in DvSrBdThem.__table__.columns}, {"batch_id": batch_id})
    ma = [d["ma_sr"] for d in dong]
    for i in range(0, len(ma), KICH_CO_LO):
        s.execute(delete(DvSrBdThem).where(DvSrBdThem.ma_sr.in_(ma[i:i + KICH_CO_LO])))
    _chen_lo(s, DvSrBdThem, dong)


def _thay_so_kh_au(s, ds: list[dict], ngay_chot: date) -> None:
    if not ds:
        return
    s.execute(delete(DvAuKh).where(DvAuKh.ngay_chot == ngay_chot))
    _chen_lo(s, DvAuKh, [{**d, "ngay_chot": ngay_chot} for d in ds])


@ghi("dvkh")
def nap(kq: dict, ngay_chot: date, ten_file: str, nguoi: str | None = None) -> dict:
    """Ghi kết quả của `doc_file.doc_file` vào database. Trả số dòng đã ghi."""
    dam_bao_bang(them=True)
    ych, no = set(kq["ych"]), set(kq["no_cuoc"])
    with session_scope() as s:
        lo = DvNap(ngay_chot=ngay_chot, ten_file=ten_file[:200], nap_boi=nguoi)
        s.add(lo)
        s.flush()
        them = {"batch_id": lo.id}
        lo.so_sr_bd = _thay_sr(s, DvSrBiDong, kq["sr_bd"], them, {"ych": ych})
        lo.so_sr_cd = _thay_sr(s, DvSrChuDong, kq["sr_cd"], them, {"no_cuoc": no, "ych": ych})
        if not kq["sr_bd"].empty:
            lo.tg_sr_bd_moi_nhat = _gia_tri(kq["sr_bd"]["tg_yc"].max())
        if not kq["sr_cd"].empty:
            lo.tg_sr_cd_moi_nhat = _gia_tri(kq["sr_cd"]["tg_do"].max())

        _thay_them(s, kq.get("sr_bd_them"), lo.id)
        _thay_so_kh_au(s, kq.get("so_kh_au") or [], ngay_chot)

        s.execute(delete(DvRoiMang).where(DvRoiMang.ngay_chot == ngay_chot))
        cot_rm = {c.name for c in DvRoiMang.__table__.columns} - {"id"}
        rm = [{**{c: None for c in cot_rm}, **d, "ngay_chot": ngay_chot} for d in kq["roi_mang"]]
        _chen_lo(s, DvRoiMang, rm)
        lo.so_dong_roi_mang = len(rm)

        chuoi = kq["chuoi_cong_no"]
        ky = {d["ky_no"] for d in chuoi if d["ky_no"]}
        if ky:
            s.execute(delete(DvCongNo).where(DvCongNo.ky_no.in_(ky)))
        _chen_lo(s, DvCongNo, [d for d in chuoi if d["ky_no"]])
        s.execute(delete(DvCongNoChot).where(DvCongNoChot.ngay_chot == ngay_chot))
        _chen_lo(s, DvCongNoChot, [{**d, "ngay_chot": ngay_chot} for d in kq["chot_cong_no"]])
        lo.so_dong_cong_no = len(chuoi)

        for loai, ds in (("ych", ych), ("no_cuoc", no)):
            if ds:
                s.execute(delete(DvDanhSach).where(DvDanhSach.loai == loai))
                _chen_lo(s, DvDanhSach, [{"loai": loai, "so_hd": h, "ngay_chot": ngay_chot} for h in sorted(ds)])
        s.add(AuditLog(username=nguoi, action="dvkh_nap",
                       detail=f"{ten_file[:80]} | ngày chốt {ngay_chot} | SR bị động {lo.so_sr_bd} | SR chủ động {lo.so_sr_cd}"))
        return {"id": lo.id, "sr_bd": lo.so_sr_bd, "sr_cd": lo.so_sr_cd, "roi_mang": lo.so_dong_roi_mang,
                "cong_no": lo.so_dong_cong_no, "chot_cong_no": len(kq["chot_cong_no"]), "ych": len(ych), "no_cuoc": len(no),
                "sr_bd_them": 0 if kq.get("sr_bd_them") is None else len(kq["sr_bd_them"]), "so_kh_au": len(kq.get("so_kh_au") or [])}


def nap_file(duong_dan_hoac_bytes, ngay_chot: date | None = None, ten_file: str = "", nguoi: str | None = None) -> dict:
    """Đọc rồi ghi một file DVKH. Ngày chốt mặc định là hôm nay (giờ Việt Nam)."""
    from app.thoi_gian import gio_viet_nam
    kq = df_.doc_file(duong_dan_hoac_bytes)
    res = nap(kq, ngay_chot or gio_viet_nam().date(), ten_file or str(duong_dan_hoac_bytes)[-80:], nguoi)
    res["canh_bao"] = kq["canh_bao"]
    return res


def lich_su(gioi_han: int = 30) -> list[dict]:
    dam_bao_bang()
    with session_scope() as s:
        rows = s.execute(select(DvNap).order_by(DvNap.id.desc()).limit(gioi_han)).scalars().all()
        return [{"id": r.id, "ngay_chot": r.ngay_chot, "ten_file": r.ten_file, "nap_luc": r.nap_luc, "nap_boi": r.nap_boi,
                 "so_sr_bd": r.so_sr_bd, "so_sr_cd": r.so_sr_cd, "tg_sr_bd": r.tg_sr_bd_moi_nhat,
                 "tg_sr_cd": r.tg_sr_cd_moi_nhat, "roi_mang": r.so_dong_roi_mang, "cong_no": r.so_dong_cong_no}
                for r in rows]
