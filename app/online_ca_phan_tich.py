"""Thống kê cho mục Theo dõi Online (chốt 12/10/2026, mở rộng 13/10/2026): tỷ lệ ca lên ĐÚNG dự kiến, xu hướng theo ngày, phân tích từng nhân sự.

Quy tắc "đúng hẹn" (mỗi ca xét theo khung giờ sale HẸN LÚC TẠO, `khung_dau`, không phải khung sau khi dời):
- `dung`: đã online và lúc sale bấm "Đã online" còn trong hạn của khung giờ hẹn (hạn = giờ hết khung của ngày đó).
- `tre`: đã online nhưng muộn hơn hạn, hoặc online ngày khác.
- `chua_len`: quá hạn mà vẫn chưa online (ngày đã qua, hoặc hôm nay đã qua giờ hết khung).
- `doi`: ca đã dời sang ngày khác (phiếu `doi_mai`); vẫn tính là KHÔNG lên đúng hẹn của ngày đó, nhưng tách riêng để thấy thói quen dời.
- `cho`: chưa tới hạn (khung chưa hết). Không tính vào tỷ lệ.
- `khong_hen`: ca khai ở "Chưa hẹn giờ" nên không có hẹn để so. Không tính vào tỷ lệ.
Tỷ lệ đúng hẹn = dung / (dung + tre + chua_len + doi). Giờ online là giờ sale BẤM nút (có thể muộn hơn giờ thật nếu sale quên bấm).
Số liệu xu hướng lấy từ bảng Báo cáo ngày (từ ngày 12/10/2026 báo cáo các ngày đã qua được giữ lại, trước đó đã bị xoá).
Mỗi ca dời tạo HAI phiếu (phiếu cũ `doi` ở ngày cũ, phiếu mới ở ngày mới) nên "số ca" là số ca THEO KẾ HOẠCH TỪNG NGÀY, không phải số hợp đồng.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select, text

from app import bao_cao_ngay as bc
from app import online_ca as oc
from app.db import engine, session_scope
from app.models import OnlineCa
from app.thoi_gian import gio_viet_nam, sang_gio_vn

KY = {"hn": "Hôm nay", "7": "7 ngày", "thang": "Tháng này"}
KET_QUA = ("dung", "tre", "chua_len", "doi", "cho", "khong_hen")
NGUONG_TOT, NGUONG_CHU_Y, TOI_THIEU_CA = 80, 50, 3


def khoang(ky: str, hom: date | None = None) -> tuple[date, date]:
    hom = hom or bc.hom_nay()
    if ky == "7":
        return hom - timedelta(days=6), hom
    if ky == "thang":
        return date(hom.year, hom.month, 1), hom
    return hom, hom


def ky_truoc(tu: date, den: date) -> tuple[date, date]:
    """Khoảng liền trước, cùng số ngày (để so sánh)."""
    n = (den - tu).days + 1
    return tu - timedelta(days=n), tu - timedelta(days=1)


def _phut(hhmm: str) -> int | None:
    try:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def _han(khung_ma: str) -> int | None:
    return next((_phut(k["den"]) for k in oc.khung() if k["ma"] == khung_ma), None)


def ket_qua(r: dict, hom: date, now: int) -> str:
    """Kết quả của một ca (xem quy tắc ở đầu file). `r` có ngay, tt, khung, khung_dau, online_luc (UTC hoặc None)."""
    k0 = r.get("khung_dau") or r["khung"]
    if k0 == "chua":
        return "khong_hen"
    han = _han(k0)
    if r["tt"] == "da_online":
        luc = sang_gio_vn(r.get("online_luc"))
        if luc is None:                                    # ca cũ chưa ghi giờ bấm: chưa dời khung thì coi là đúng
            return "dung" if r["khung"] == k0 else "tre"
        return "dung" if luc.date() == r["ngay"] and han is not None and luc.hour * 60 + luc.minute <= han else "tre"
    if r["tt"] == "doi_mai":
        return "doi"
    if r["ngay"] < hom or (r["ngay"] == hom and han is not None and now >= han):
        return "chua_len"
    return "cho"


def _tre_phut(r: dict) -> int | None:
    """Số phút online muộn hơn hạn của khung hẹn (chỉ ca online TRONG CÙNG NGÀY nhưng quá hạn)."""
    luc = sang_gio_vn(r.get("online_luc"))
    han = _han(r.get("khung_dau") or r["khung"])
    if luc is None or han is None or luc.date() != r["ngay"]:
        return None
    muon = luc.hour * 60 + luc.minute - han
    return muon if muon > 0 else None


def _ca(phong: list[str], tu: date, den: date, acc: str | None = None) -> list[dict]:
    oc.dam_bao_bang()
    with session_scope() as s:
        q = select(OnlineCa).where(OnlineCa.ngay >= tu, OnlineCa.ngay <= den, OnlineCa.phong_code.in_(phong))
        if acc:
            q = q.where(OnlineCa.acc_norm == acc)
        out = []
        for r in s.execute(q).scalars().all():
            try:
                so_doi = sum(str(x.get("viec", "")).startswith("Dời sang ngày") for x in json.loads(r.lich_su or "[]"))
            except ValueError:
                so_doi = 0
            out.append({"ngay": r.ngay, "acc": r.acc_norm, "ma": r.ma_hd, "khung": r.khung, "khung_dau": r.khung_dau, "tt": r.trang_thai,
                        "online_luc": r.online_luc, "so_doi": so_doi})
        return out


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
    n = {k: sum(c["kq"] == k for c in ds) for k in KET_QUA}
    xet = n["dung"] + n["tre"] + n["chua_len"] + n["doi"]
    tre = [c["tre_phut"] for c in ds if c.get("tre_phut")]
    return {"ca": len(ds), **n, "xet": xet, "ty_le": round(n["dung"] * 100 / xet) if xet else None,
            "ty_doi": round(n["doi"] * 100 / len(ds)) if ds else None, "tre_tb": round(sum(tre) / len(tre)) if tre else None,
            "doi_nhieu": sum(c["so_doi"] >= 2 and c["kq"] != "doi" for c in ds)}


def danh_gia(ty_le, xet: int) -> tuple[str, str]:
    """(mức, nhãn) của một người / một nhóm: ít hơn `TOI_THIEU_CA` ca đã xét thì chưa đủ dữ liệu để kết luận."""
    if ty_le is None or xet < TOI_THIEU_CA:
        return "it", "Ít dữ liệu"
    return ("tot", "Tốt") if ty_le >= NGUONG_TOT else ("luu_y", "Cần chú ý") if ty_le >= NGUONG_CHU_Y else ("xau", "Cần hỗ trợ")


def hieu_qua(phong: list[str], tu: date, den: date, now: int | None = None, acc: str | None = None) -> dict:
    """{"tong", "nv": [{acc, ten, ...}], "khung": [{ma, nhan, ...}] (theo khung HẸN), "ngay": [{ngay, ...}], "ca": [ca đã có kết quả], "tu", "den"};
    `acc` chỉ xét một người."""
    hom = bc.hom_nay()
    if now is None:
        g = gio_viet_nam()
        now = g.hour * 60 + g.minute
    ca = _ca(phong, tu, den, acc)
    for c in ca:
        c["kq"] = ket_qua(c, hom, now)
        c["tre_phut"] = _tre_phut(c) if c["kq"] == "tre" else None
    ten = _ten(c["acc"] for c in ca)
    nv = [{"acc": a, "ten": ten.get(a, a), **_tinh([c for c in ca if c["acc"] == a])} for a in dict.fromkeys(c["acc"] for c in ca)]
    nv.sort(key=lambda x: (x["ty_le"] is None, -(x["ty_le"] or 0), x["ten"]))
    kh = [{"ma": k["ma"], "nhan": k["nhan"], **_tinh([c for c in ca if (c["khung_dau"] or c["khung"]) == k["ma"]])} for k in oc.khung()]
    ngay = [{"ngay": d, **_tinh([c for c in ca if c["ngay"] == d])} for d in sorted({c["ngay"] for c in ca})]
    return {"tong": _tinh(ca), "nv": nv, "khung": [k for k in kh if k["ca"]], "ngay": ngay, "ca": ca, "tu": tu, "den": den}


def xu_huong(phong: list[str], tu: date, den: date, acc: str | None = None) -> dict:
    """Số liệu Báo cáo ngày theo ngày và theo nhân viên trong khoảng: mục tiêu ngày, thực hiện (bán), dự kiến online, đã online.
    {"ngay": [{ngay, mt, ban, dk, onl, nguoi}], "nv": [{acc, ten, so_ngay, mt, ban, dk, onl}], "tong": {mt, ban, dk, onl}, "tu_ngay_co": ngày sớm nhất có số liệu}."""
    bc.dam_bao_bang()
    ma = {f"p{i}": c for i, c in enumerate(phong)}
    cho = ", ".join(f":{k}" for k in ma)
    gom = """SUM(COALESCE(muc_tieu, 0)), SUM(COALESCE(da_ban, 0)), SUM(COALESCE(onl_sang, 0) + COALESCE(onl_chieu, 0)),
             SUM(COALESCE(da_online, 0)), COUNT(*)"""
    tham = {**ma, "tu": tu.isoformat(), "den": den.isoformat()}
    loc = f"phong_code IN ({cho}) AND ngay >= :tu AND ngay <= :den"
    if acc:
        loc += " AND acc_norm = :acc"
        tham["acc"] = acc
    with engine.connect() as c:
        theo_ngay = c.execute(text(f"SELECT ngay, {gom} FROM bao_cao_ngay WHERE {loc} GROUP BY ngay ORDER BY ngay"), tham).all()
        theo_nv = c.execute(text(f"SELECT acc_norm, {gom} FROM bao_cao_ngay WHERE {loc} GROUP BY acc_norm"), tham).all()
    ngay = [{"ngay": date.fromisoformat(str(r[0])[:10]), "mt": int(r[1]), "ban": int(r[2]), "dk": int(r[3]), "onl": int(r[4]), "nguoi": int(r[5])}
            for r in theo_ngay]
    ten = _ten(r[0] for r in theo_nv)
    nv = [{"acc": r[0], "ten": ten.get(r[0], r[0]), "mt": int(r[1]), "ban": int(r[2]), "dk": int(r[3]), "onl": int(r[4]), "so_ngay": int(r[5])}
          for r in theo_nv]
    nv.sort(key=lambda x: x["ten"].split()[-1] if x["ten"].split() else x["ten"])
    tong = {k: sum(r[k] for r in ngay) for k in ("mt", "ban", "dk", "onl")}
    return {"ngay": ngay, "nv": nv, "tong": tong, "tu_ngay_co": ngay[0]["ngay"] if ngay else None}


# ------------------------------------------------------------------ nhận định (luật cố định, không dùng AI)
def _phan_tram(a: int, b: int) -> int | None:
    return round(a * 100 / b) if b else None


def _so_voi_truoc(ty, ty0, ten_ky="kỳ trước") -> str:
    if ty is None or ty0 is None:
        return ""
    d = ty - ty0
    return f", {'tăng' if d > 0 else 'giảm'} {abs(d)} điểm so với {ten_ky} ({ty0}%)" if d else f", bằng {ten_ky} ({ty0}%)"


def _muc(ty: int | None, tot=NGUONG_TOT, chu_y=NGUONG_CHU_Y) -> str:
    return "tt" if ty is None else "tot" if ty >= tot else "luu_y" if ty >= chu_y else "xau"


def _dong_chot_ban(xh: dict, loi_chot: str = "") -> list[tuple[str, str]]:
    out = []
    t = xh["tong"]
    ty_chot, ty_ban = _phan_tram(t["onl"], t["dk"]), _phan_tram(t["ban"], t["mt"])
    if ty_chot is not None:
        out.append((_muc(ty_chot, 85, 60), f"Đã online {t['onl']}/{t['dk']} so với dự kiến ({ty_chot}%)"
                    + (f". {loi_chot}" if ty_chot < 70 and loi_chot else ".")))
    if ty_ban is not None:
        out.append((_muc(ty_ban), f"Bán {t['ban']}/{t['mt']} so với mục tiêu ngày ({ty_ban}%)."))
    return out


def nhan_dinh_phong(hq: dict, hq0: dict, xh: dict) -> list[tuple[str, str]]:
    """Nhận định tổng quan cả phòng: [(mức tot|luu_y|xau|tt, câu)]. `hq0` là khoảng liền trước để so."""
    t, t0 = hq["tong"], hq0["tong"]
    out = []
    if t["ty_le"] is None:
        out.append(("tt", "Chưa có ca nào đến hạn trong khoảng này nên chưa tính được tỷ lệ đúng hẹn."))
    else:
        out.append((_muc(t["ty_le"]), f"{t['dung']}/{t['xet']} ca lên đúng hẹn ({t['ty_le']}%){_so_voi_truoc(t['ty_le'], t0['ty_le'])}."))
    xet = [n for n in hq["nv"] if n["xet"] >= TOI_THIEU_CA]
    if len(xet) >= 2:
        tot, kem = xet[0], xet[-1]
        out.append(("tot", f"Đúng hẹn tốt nhất: {tot['ten']} ({tot['ty_le']}%, {tot['dung']}/{tot['xet']} ca)."))
        if kem["ty_le"] < NGUONG_TOT:
            out.append((_muc(kem["ty_le"]), f"Cần hỗ trợ: {kem['ten']} ({kem['ty_le']}%): trễ {kem['tre']}, chưa lên {kem['chua_len']}, dời {kem['doi']}."))
    kh = sorted([k for k in hq["khung"] if k["xet"] >= TOI_THIEU_CA and k["ma"] != "chua"], key=lambda k: k["ty_le"])
    if len(kh) >= 2 and kh[0]["ty_le"] < NGUONG_TOT:
        out.append(("luu_y", f"Khung hẹn dễ lỡ nhất: {kh[0]['nhan']} ({kh[0]['ty_le']}% đúng hẹn, {kh[0]['xet']} ca); ổn nhất: {kh[-1]['nhan']} ({kh[-1]['ty_le']}%)."))
    if t["doi"]:
        nhieu = f"; {t['doi_nhieu']} ca đã dời từ 2 lần trở lên" if t["doi_nhieu"] else ""
        out.append(("luu_y" if (t["ty_doi"] or 0) >= 15 else "tt", f"{t['doi']} ca bị dời sang ngày khác ({t['ty_doi']}% số ca){nhieu}."))
    if t["tre_tb"]:
        out.append(("tt", f"Ca trễ thường online muộn khoảng {t['tre_tb']} phút so với hạn khung giờ hẹn."))
    yeu = sorted([d for d in hq["ngay"] if d["xet"] >= TOI_THIEU_CA], key=lambda d: d["ty_le"])
    if len(yeu) >= 2 and yeu[0]["ty_le"] < (t["ty_le"] or 0):
        out.append(("luu_y", f"Ngày yếu nhất: {yeu[0]['ngay']:%d/%m} ({yeu[0]['ty_le']}% đúng hẹn, {yeu[0]['xet']} ca)."))
    return out + _dong_chot_ban(xh, "Dự kiến đang cao hơn thực tế, nên siết lại số hẹn.")


def nhan_dinh_nv(nv: dict, hq: dict, phong: dict, xh: dict) -> list[tuple[str, str]]:
    """Nhận định cho MỘT người. `nv` = dòng của người đó trong `hq["nv"]`, `hq` = hiệu quả riêng người đó, `phong` = `tong` của cả phòng cùng khoảng."""
    t = nv
    out = []
    if t["ty_le"] is None:
        out.append(("tt", "Chưa có ca nào đến hạn trong khoảng này nên chưa tính được tỷ lệ đúng hẹn."))
    else:
        pt = phong.get("ty_le")
        so = f"; cả phòng {pt}%" if pt is not None else ""
        out.append((_muc(t["ty_le"]), f"{t['dung']}/{t['xet']} ca lên đúng hẹn ({t['ty_le']}%{so})."))
    kh = sorted([k for k in hq["khung"] if k["xet"] >= 2 and k["ma"] != "chua"], key=lambda k: k["ty_le"])
    if len(kh) >= 2 and kh[-1]["ty_le"] > kh[0]["ty_le"]:
        out.append(("tot", f"Khung hẹn đúng giờ nhất: {kh[-1]['nhan']} ({kh[-1]['ty_le']}%, {kh[-1]['xet']} ca)."))
        out.append(("luu_y", f"Khung hẹn hay lỡ nhất: {kh[0]['nhan']} ({kh[0]['ty_le']}%, {kh[0]['xet']} ca): nên hẹn khách khung khác hoặc lùi giờ."))
    if t["doi"]:
        nhieu = f"; {t['doi_nhieu']} ca đã dời từ 2 lần trở lên" if t["doi_nhieu"] else ""
        pd_ = phong.get("ty_doi")
        so = f"; cả phòng {pd_}%" if pd_ is not None else ""
        out.append(("luu_y" if (t["ty_doi"] or 0) >= 15 else "tt", f"Dời {t['doi']} ca sang ngày khác ({t['ty_doi']}% số ca{so}){nhieu}."))
    if t["tre_tb"]:
        out.append(("tt", f"Ca trễ thường online muộn khoảng {t['tre_tb']} phút so với hạn."))
    if t["chua_len"]:
        out.append(("xau", f"{t['chua_len']} ca đã quá hạn mà chưa online: cần xử lý hoặc dời ngày."))
    return out + _dong_chot_ban(xh, "Dự kiến đang cao hơn thực tế, nên hẹn sát hơn.")
