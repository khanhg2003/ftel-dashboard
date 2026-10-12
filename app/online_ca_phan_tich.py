"""Thống kê cho mục Theo dõi Online (chốt 12/10/2026): tỷ lệ ca lên ĐÚNG dự kiến và xu hướng theo ngày.

Quy tắc "đúng hẹn" (mỗi ca xét theo khung giờ sale HẸN LÚC TẠO, `khung_dau`, không phải khung sau khi dời):
- `dung`: đã online và lúc sale bấm "Đã online" còn trong hạn của khung giờ hẹn (hạn = giờ hết khung của ngày đó).
- `tre`: đã online nhưng muộn hơn hạn, hoặc online ngày khác.
- `chua_len`: quá hạn mà vẫn chưa online (ngày đã qua, hoặc hôm nay đã qua giờ hết khung), hoặc đã dời sang ngày mai.
- `cho`: chưa tới hạn (khung chưa hết). Không tính vào tỷ lệ.
- `khong_hen`: ca khai ở "Chưa hẹn giờ" nên không có hẹn để so. Không tính vào tỷ lệ.
Tỷ lệ đúng hẹn = dung / (dung + tre + chua_len). Giờ online là giờ sale BẤM nút (có thể muộn hơn giờ thật nếu sale quên bấm).
Số liệu xu hướng lấy từ bảng Báo cáo ngày (từ ngày 12/10/2026 báo cáo các ngày đã qua được giữ lại, trước đó đã bị xoá).
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select, text

from app import bao_cao_ngay as bc
from app import online_ca as oc
from app.db import engine, session_scope
from app.models import OnlineCa
from app.thoi_gian import gio_viet_nam, sang_gio_vn

KY = {"hn": "Hôm nay", "7": "7 ngày", "thang": "Tháng này"}


def khoang(ky: str, hom: date | None = None) -> tuple[date, date]:
    hom = hom or bc.hom_nay()
    if ky == "7":
        return hom - timedelta(days=6), hom
    if ky == "thang":
        return date(hom.year, hom.month, 1), hom
    return hom, hom


def _phut(hhmm: str) -> int | None:
    try:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def ket_qua(r: dict, hom: date, now: int) -> str:
    """Kết quả của một ca (xem quy tắc ở đầu file). `r` có ngay, tt, khung, khung_dau, online_luc (UTC hoặc None)."""
    k0 = r.get("khung_dau") or r["khung"]
    if k0 == "chua":
        return "khong_hen"
    han = next((_phut(k["den"]) for k in oc.khung() if k["ma"] == k0), None)
    if r["tt"] == "da_online":
        luc = sang_gio_vn(r.get("online_luc"))
        if luc is None:                                    # ca cũ chưa ghi giờ bấm: chưa dời khung thì coi là đúng
            return "dung" if r["khung"] == k0 else "tre"
        return "dung" if luc.date() == r["ngay"] and han is not None and luc.hour * 60 + luc.minute <= han else "tre"
    if r["tt"] == "doi_mai":
        return "chua_len"
    if r["ngay"] < hom or (r["ngay"] == hom and han is not None and now >= han):
        return "chua_len"
    return "cho"


def _ca(phong: list[str], tu: date, den: date) -> list[dict]:
    oc.dam_bao_bang()
    with session_scope() as s:
        rows = s.execute(select(OnlineCa).where(OnlineCa.ngay >= tu, OnlineCa.ngay <= den, OnlineCa.phong_code.in_(phong))).scalars().all()
        return [{"ngay": r.ngay, "acc": r.acc_norm, "khung": r.khung, "khung_dau": r.khung_dau, "tt": r.trang_thai,
                 "online_luc": r.online_luc} for r in rows]


def _ten(accs) -> dict:
    ds = list(dict.fromkeys(accs))
    if not ds:
        return {}
    ten = pd.read_sql_query(text("SELECT acc_norm, ho_ten FROM dim_employee WHERE acc_norm IS NOT NULL"), engine)
    ten = ten.drop_duplicates("acc_norm").set_index("acc_norm").ho_ten
    tam = pd.read_sql_query(text("SELECT acc_norm, ten_hien_thi FROM staff_map WHERE ten_hien_thi IS NOT NULL"), engine)
    tam = tam.drop_duplicates("acc_norm").set_index("acc_norm").ten_hien_thi
    return {a: str(ten.get(a) or tam.get(a) or a) for a in ds}


def _tinh(ds: list[dict]) -> dict:
    n = {k: sum(c["kq"] == k for c in ds) for k in ("dung", "tre", "chua_len", "cho", "khong_hen")}
    xet = n["dung"] + n["tre"] + n["chua_len"]
    return {"ca": len(ds), **n, "ty_le": round(n["dung"] * 100 / xet) if xet else None}


def hieu_qua(phong: list[str], tu: date, den: date, now: int | None = None) -> dict:
    """{"tong": {...}, "nv": [{acc, ten, ca, dung, tre, chua_len, cho, khong_hen, ty_le}], "khung": [{ma, nhan, ...}]} - khung xếp theo khung HẸN."""
    hom = bc.hom_nay()
    if now is None:
        g = gio_viet_nam()
        now = g.hour * 60 + g.minute
    ca = _ca(phong, tu, den)
    for c in ca:
        c["kq"] = ket_qua(c, hom, now)
    ten = _ten(c["acc"] for c in ca)
    nv = [{"acc": a, "ten": ten.get(a, a), **_tinh([c for c in ca if c["acc"] == a])} for a in dict.fromkeys(c["acc"] for c in ca)]
    nv.sort(key=lambda x: (x["ty_le"] is None, -(x["ty_le"] or 0), x["ten"]))
    kh = [{"ma": k["ma"], "nhan": k["nhan"], **_tinh([c for c in ca if (c["khung_dau"] or c["khung"]) == k["ma"]])} for k in oc.khung()]
    return {"tong": _tinh(ca), "nv": nv, "khung": [k for k in kh if k["ca"]], "tu": tu, "den": den}


def xu_huong(phong: list[str], tu: date, den: date) -> dict:
    """Số liệu Báo cáo ngày theo ngày và theo nhân viên trong khoảng: mục tiêu ngày, thực hiện (bán), dự kiến online, đã online.
    {"ngay": [{ngay, mt, ban, dk, onl, nguoi}], "nv": [{acc, ten, so_ngay, mt, ban, dk, onl}], "tu_ngay_co": ngày sớm nhất có số liệu}."""
    bc.dam_bao_bang()
    ma = {f"p{i}": c for i, c in enumerate(phong)}
    cho = ", ".join(f":{k}" for k in ma)
    gom = """SUM(COALESCE(muc_tieu, 0)), SUM(COALESCE(da_ban, 0)), SUM(COALESCE(onl_sang, 0) + COALESCE(onl_chieu, 0)),
             SUM(COALESCE(da_online, 0)), COUNT(*)"""
    tham = {**ma, "tu": tu.isoformat(), "den": den.isoformat()}
    loc = f"phong_code IN ({cho}) AND ngay >= :tu AND ngay <= :den"
    with engine.connect() as c:
        theo_ngay = c.execute(text(f"SELECT ngay, {gom} FROM bao_cao_ngay WHERE {loc} GROUP BY ngay ORDER BY ngay"), tham).all()
        theo_nv = c.execute(text(f"SELECT acc_norm, {gom} FROM bao_cao_ngay WHERE {loc} GROUP BY acc_norm"), tham).all()
    ngay = [{"ngay": date.fromisoformat(str(r[0])[:10]), "mt": int(r[1]), "ban": int(r[2]), "dk": int(r[3]), "onl": int(r[4]), "nguoi": int(r[5])}
            for r in theo_ngay]
    ten = _ten(r[0] for r in theo_nv)
    nv = [{"acc": r[0], "ten": ten.get(r[0], r[0]), "mt": int(r[1]), "ban": int(r[2]), "dk": int(r[3]), "onl": int(r[4]), "so_ngay": int(r[5])}
          for r in theo_nv]
    nv.sort(key=lambda x: x["ten"].split()[-1] if x["ten"].split() else x["ten"])
    return {"ngay": ngay, "nv": nv, "tu_ngay_co": ngay[0]["ngay"] if ngay else None}
