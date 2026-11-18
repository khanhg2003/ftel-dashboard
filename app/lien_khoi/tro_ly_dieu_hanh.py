"""TRỢ LÝ ĐIỀU HÀNH (nhánh thi-lien-khoi): vòng khép kín cho lãnh đạo.
QUAN SÁT (các bộ quét) -> NHẬN ĐỊNH -> ĐỀ XUẤT 2-3 PHƯƠNG ÁN -> CHỜ NGƯỜI QUYẾT -> NHẮC / LEO THANG -> KIỂM CHỨNG bằng chính chỉ số đã đo lúc đề xuất.

Nguyên tắc:
- LUẬT giữ vai SỰ THẬT: mọi số do code lấy (từ `dieu_phoi`, `theo_doi`, `app/kt/so_lieu`), LLM chỉ VIẾT lại nhận định và phương án từ "bảng sự thật" và mọi số trong câu của nó
  phải có trong bảng (`kiem_so`). Sai số, JSON hỏng, LLM lỗi, hết trần lượt gọi, chưa bật AI thì dùng bản LUẬT dựng bằng khuôn cố định: tin vẫn đi.
- Trợ lý chỉ ĐỀ XUẤT. Không tự giao việc, không nhắn khách. Người quyết ghi quyết định qua Zalo (`zalo_lenh.py`) hoặc xem ở tab Trợ lý điều hành.
- Lời gửi LLM không có tên khách, số điện thoại, tên nhân sự: chỉ mã team / mã hợp đồng và số tổng hợp. Có trần lượt gọi LLM mỗi ngày
  (`TRO_LY_DIEU_HANH_TRAN_NGAY`, mặc định 30) và nhớ kết quả theo (vấn đề, bảng sự thật). Khoá API và hạn mức tháng dùng của `app/tro_ly.py`.
- Bộ quét CẮM THÊM được: mỗi nguồn là một hàm trả danh sách PHÁT HIỆN theo khuôn chung (`NGUON_QUET`); thêm nguồn cho Kinh doanh / DVKH / Kỹ thuật bằng `dang_ky`, không sửa lõi.
  Mọi phát hiện mức cao phải có mặt trong nội dung gửi (thiếu thì code tự chèn); phát hiện mức thấp gộp thành dòng "còn N mục nhỏ".
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import namedtuple
from datetime import datetime, timedelta

import pandas as pd

from app.lien_khoi import dieu_phoi as dp, quyet_dinh as qd, theo_doi as td, zalo_viec as zv

CAO, TB, THAP = "cao", "trung_binh", "thap"
HANG_MUC = {CAO: 0, TB: 1, THAP: 2}
TOI_DA_VAN_DE = 5
TOI_DA_CAO_NEU = 8                              # số mã mức cao liệt kê trong bảng sự thật / nhận định (còn lại ghi "còn N mục")
QUA_HAN_TOI_THIEU, QUA_HAN_CAO = 3, 8           # việc quá hạn của MỘT team
HANG_CHO_TOI_THIEU, HANG_CHO_CAO = 5, 15        # việc hàng chờ chưa giao của một quản lý
CAO_CN_TOI_THIEU, CAO_CN_CAO = 5, 15            # việc mức Cao đang mở của cả chi nhánh
KT_IM_LANG_GIO, KT_CAO_GIO, KT_TB_GIO = 24, 72, 48
TOI_DA_KY_TU = zv.TOI_DA_KY_TU
TRAN_NGAY_MAC_DINH = 30
MAC_DINH = object()                              # "dùng LLM thật nếu có" (khác với None = chỉ dùng luật)
NguonQuet = namedtuple("NguonQuet", "ten nhan quet do_phu")
_SO = re.compile(r"(?<![\w.,/:])\d+(?:[.,/:]\d+)*%?")
_NGOAI_LE_CHU = re.compile(r"đấu\s*nối", re.I)


# ------------------------------------------------------------------ định dạng, thời gian
def _so(x) -> str:
    return f"{x:,.0f}".replace(",", ".") if float(x).is_integer() else f"{x:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _vn(t) -> str:
    return "" if t is None or pd.isna(t) else (pd.Timestamp(t) + pd.Timedelta(hours=7)).strftime("%d/%m %H:%M")


def _ngay(now: datetime) -> tuple[str, str]:
    t = pd.Timestamp(now) + pd.Timedelta(hours=7)
    return t.strftime("%Y%m%d"), t.strftime("%d/%m")


def _hien(chu: str, ten: dict | None) -> str:
    """Thay mã team trong chữ bằng tên quản lý (chỉ dùng cho chữ hiện ra với người, không bao giờ cho lời gửi LLM)."""
    for ma in sorted(ten or {}, key=len, reverse=True):
        if ma and ten[ma] and ma in chu:
            chu = re.sub(rf"(?<!\w){re.escape(ma)}(?!\w)", lambda _m, t=ten[ma]: t, chu)
    return chu


# ------------------------------------------------------------------ ngữ cảnh và các bộ quét
def ngu_canh(now: datetime | None = None) -> dict:
    """Đọc một lần: người nhận, giám đốc chi nhánh, việc đang mở (thật) của cả chi nhánh kèm cột `ql` (quản lý của team; việc chưa có quản lý về giám đốc)."""
    now = now or td.bay_gio()
    ds = td.nguoi_nhan().fillna("")
    gd = td.giam_doc(ds)
    d = dp.viec_cua(gd, now) if gd else pd.DataFrame()
    if len(d):
        d = d.assign(ql=d["quan_ly"].replace("", gd))
    return {"now": now, "ds": ds, "gd": gd, "d": d, "ten": dict(zip(ds["ma"], ds["ten"])), "khoi": dict(zip(ds["ma"], ds["khoi"])), "cache": {}}


def _hang_cho(x: pd.DataFrame) -> pd.Series:
    return (x["trang_thai"] == "moi") & x["nguoi_goc"].fillna("").ne("") & x["giao_cho"].fillna("").eq("")


def _muc(n: float, cao: float, thieu: float) -> str:
    return CAO if n >= cao else TB if n >= thieu else THAP


def _kt_du_lieu() -> dict | None:
    """Ca tồn Kỹ thuật và ca im lặng từ `app/kt/so_lieu`; chưa có nguồn thì None."""
    from app.kt import so_lieu as sl
    ev = sl.su_kien()
    if ev.empty:
        return None
    t = sl.ton(ev, sl.bay_gio(ev))
    return {"ton": t, "im_lang": sl.im_lang(t, KT_IM_LANG_GIO)}


def _kt(c: dict) -> dict | None:
    if "kt" not in c["cache"]:
        try:
            c["cache"]["kt"] = _kt_du_lieu()
        except Exception:                        # nguồn Kỹ thuật hỏng không được làm hỏng cả buổi sáng
            c["cache"]["kt"] = None
    return c["cache"]["kt"]


def _chi_so(loai: str, tham_so: dict, gia_tri: int, nhan: str, don_vi: str) -> dict:
    return {"loai": loai, "tham_so": tham_so, "gia_tri": int(gia_tri), "nhan": nhan, "don_vi": don_vi, "tot_khi": "giam"}


def _ph(nguon: str, nhom: str, **kw) -> dict:
    """Một PHÁT HIỆN theo khuôn chung của mọi bộ quét."""
    kw.setdefault("bang_chung", {})
    return {"nguon": nguon, "nhom": nhom, "nhan_nhom": kw.get("tieu_de", ""), "don_vi": "", **kw}


def quet_qua_han_team(c: dict) -> list[dict]:
    d = c["d"]
    kq = []
    for ql, x in (d.groupby("ql") if len(d) else []):
        n = int(x["qua_han"].sum())
        if n < QUA_HAN_TOI_THIEU:
            continue
        bc = {"qua_han": n, "dang_mo": len(x), "ty_le_qua_han": round(100 * n / len(x)), "chua_giao": int(x["giao_cho"].fillna("").eq("").sum()), "muc_cao": int((x["muc"] == "Cao").sum())}
        kq.append(_ph("qua_han_team", f"qua_han_team:{ql}", ma=f"qua_han:{ql}", khoi=c["khoi"].get(ql, ""), cap="doi", doi_tuong=ql, muc=_muc(n, QUA_HAN_CAO, QUA_HAN_TOI_THIEU),
                      diem=n * 3, tieu_de=f"Team {ql} có {n} việc quá hạn", bang_chung=bc, duong_dan=f"/lienkhoi?tab=td&ql={ql}", nguoi_quyet=ql,
                      chi_so=_chi_so("qua_han_team", {"ql": ql}, n, f"Việc quá hạn của team {ql}", "việc")))
    return kq


def phu_qua_han_team(c: dict) -> dict:
    ql = c["ds"][c["ds"]["vai_tro"].isin(td.VAI_TRO_QUAN_LY) & (c["ds"]["vai_tro"] != "giam_doc")]
    return {"don_vi": "team", "da_quet": int(c["d"]["ql"].nunique()) if len(c["d"]) else 0, "tong": len(ql)}


def quet_hang_cho(c: dict) -> list[dict]:
    d = c["d"]
    kq = []
    for ql, x in (d[_hang_cho(d)].groupby("ql") if len(d) else []):
        n = len(x)
        if n < HANG_CHO_TOI_THIEU:
            continue
        kq.append(_ph("hang_cho", f"hang_cho:{ql}", ma=f"hang_cho:{ql}", khoi=c["khoi"].get(ql, ""), cap="khoi", doi_tuong=ql, muc=_muc(n, HANG_CHO_CAO, HANG_CHO_TOI_THIEU),
                      diem=n * 2, tieu_de=f"{n} việc hàng chờ của {ql} chưa giao cho ai", bang_chung={"hang_cho": n, "muc_cao": int((x["muc"] == "Cao").sum())},
                      duong_dan=f"/lienkhoi?tab=td&ql={ql}", nguoi_quyet=ql, chi_so=_chi_so("hang_cho", {"ql": ql}, n, f"Việc hàng chờ chưa giao của {ql}", "việc")))
    return kq


def phu_viec_mo(c: dict) -> dict:
    tat = td.danh_sach(c["now"])
    tong = int((tat["dang_mo"] & dp._thuc(tat)).sum()) if len(tat) else 0
    return {"don_vi": "phần việc đang mở", "da_quet": len(c["d"]), "tong": tong}


def quet_cao_chi_nhanh(c: dict) -> list[dict]:
    d = c["d"]
    n = int((d["muc"] == "Cao").sum()) if len(d) else 0
    if n < CAO_CN_TOI_THIEU or not c["gd"]:
        return []
    cao = d[d["muc"] == "Cao"]
    return [_ph("cao_chi_nhanh", "cao_chi_nhanh", ma="cao_chi_nhanh", khoi="BGD", cap="chi_nhanh", doi_tuong="Chi nhánh", muc=_muc(n, CAO_CN_CAO, CAO_CN_TOI_THIEU), diem=n * 2,
                tieu_de=f"Chi nhánh đang có {n} việc mức Cao chưa xong", bang_chung={"muc_cao": n, "qua_han_muc_cao": int(cao["qua_han"].sum()), "chua_giao_muc_cao": int(cao["giao_cho"].fillna("").eq("").sum())},
                duong_dan="/lienkhoi?tab=td&ql=all", nguoi_quyet=c["gd"], chi_so=_chi_so("cao_cn", {}, n, "Việc mức Cao đang mở của chi nhánh", "việc"))]


def quet_kt_im_lang(c: dict) -> list[dict]:
    kt = _kt(c)
    if kt is None or kt["im_lang"].empty:
        return []
    nq = td.doi_truong("KT", c["ds"]) or c["gd"]
    cs = _chi_so("kt_im_lang", {}, len(kt["im_lang"]), "Số ca tồn Kỹ thuật im lặng", "ca")
    kq = []
    for r in kt["im_lang"].to_dict("records"):
        gio = float(r["gio_im_lang"])
        kq.append(_ph("kt_im_lang", f"kt_im_lang:{nq}", ma=f"kt_im_lang:{r['so_hd']}", khoi="KT", cap="hop_dong", doi_tuong=str(r["so_hd"]), muc=_muc(gio, KT_CAO_GIO, KT_TB_GIO), diem=gio / 24,
                      tieu_de=f"Ca {r['so_hd']} im lặng {gio:.0f} giờ", nhan_nhom="Ca tồn Kỹ thuật im lặng", don_vi="ca",
                      bang_chung={"gio_im_lang": round(gio), "ngay_ton": round(float(r["ngay_ton"]), 1), "nguong_gio": KT_IM_LANG_GIO},
                      duong_dan="/kt/bao-cao-ton", nguoi_quyet=nq, chi_so=cs))
    return kq


def phu_kt(c: dict) -> dict:
    kt = _kt(c)
    return {"don_vi": "ca tồn Kỹ thuật", "da_quet": 0 if kt is None else len(kt["ton"]), "tong": 0 if kt is None else len(kt["ton"]), "co_nguon": kt is not None}


NGUON_QUET: list[NguonQuet] = [
    NguonQuet("qua_han_team", "Việc quá hạn theo team", quet_qua_han_team, phu_qua_han_team),
    NguonQuet("hang_cho", "Việc hàng chờ chưa giao", quet_hang_cho, phu_viec_mo),
    NguonQuet("cao_chi_nhanh", "Việc mức Cao của chi nhánh", quet_cao_chi_nhanh, phu_viec_mo),
    NguonQuet("kt_im_lang", "Ca tồn Kỹ thuật im lặng", quet_kt_im_lang, phu_kt),
]


def dang_ky(nguon: NguonQuet) -> None:
    """Cắm thêm bộ quét (Kinh doanh, DVKH, Kỹ thuật...). `quet(ngữ cảnh)` trả danh sách phát hiện (xem `_ph`), `do_phu(ngữ cảnh)` trả {don_vi, da_quet, tong}."""
    NGUON_QUET[:] = [n for n in NGUON_QUET if n.ten != nguon.ten] + [nguon]


def quet(c: dict) -> list[dict]:
    kq = []
    for n in NGUON_QUET:
        try:
            kq += n.quet(c)
        except Exception:                        # một bộ quét hỏng thì các bộ khác vẫn chạy
            continue
    return kq


def so_do_phu(now: datetime | None = None, c: dict | None = None) -> list[dict]:
    """Độ phủ của từng nguồn quét: số thực thể đã quét trên tổng (để biết trợ lý nhìn được bao nhiêu)."""
    c = c or ngu_canh(now)
    kq = []
    for n in NGUON_QUET:
        try:
            kq.append({"nguon": n.ten, "ten": n.nhan, "co_nguon": True, **n.do_phu(c)})
        except Exception:
            kq.append({"nguon": n.ten, "ten": n.nhan, "co_nguon": False, "don_vi": "", "da_quet": 0, "tong": 0})
    return kq


def do_chi_so(loai: str, tham_so: dict, c: dict) -> int:
    """Đo lại một chỉ số bằng CHÍNH cách đã đo lúc đề xuất (dùng khi kiểm chứng)."""
    d = c["d"]
    if loai in ("qua_han_team", "hang_cho"):
        x = d[d["ql"] == tham_so["ql"]] if len(d) else d
        return 0 if not len(x) else int(x["qua_han"].sum()) if loai == "qua_han_team" else int(_hang_cho(x).sum())
    if loai == "cao_cn":
        return int((d["muc"] == "Cao").sum()) if len(d) else 0
    if loai == "kt_im_lang":
        kt = _kt(c)
        return 0 if kt is None else len(kt["im_lang"])
    raise ValueError(f"Chỉ số lạ: {loai}")


# ------------------------------------------------------------------ gom phát hiện thành vấn đề
def _gom_nhom(g: list[dict], ngay: str, ngay_hien: str, c: dict) -> dict:
    lead = max(g, key=lambda f: (-HANG_MUC[f["muc"]], f["diem"]))
    dem = {m: sum(1 for f in g if f["muc"] == m) for m in HANG_MUC}
    cao = sorted((f for f in g if f["muc"] == CAO), key=lambda f: -f["diem"])
    bc = {**lead["bang_chung"], "so_muc": len(g), "so_cao": dem[CAO], "so_trung_binh": dem[TB], "so_thap": dem[THAP]}
    nq = lead["nguoi_quyet"] or c["gd"]
    tieu_de = lead["tieu_de"] if len(g) == 1 else f"{lead['nhan_nhom']}: {len(g)} {lead['don_vi'] or 'mục'}"
    su_that = {"loai": lead["nguon"], "khoi": lead["khoi"], "cap": lead["cap"], "muc": lead["muc"], "ngay": ngay_hien, "bang_chung": bc, "duong_dan": lead["duong_dan"],
               "phat_hien_cao": [{"doi_tuong": f["doi_tuong"], **f["bang_chung"]} for f in cao[:TOI_DA_CAO_NEU]], "chi_so": lead["chi_so"],
               "han_quyet_gio": int(qd.cau_hinh()["han_quyet_gio"]), "kiem_chung_gio": int(qd.cau_hinh()["kiem_chung_gio"])}
    return {"ma_van_de": f"{ngay}:{lead['nhom']}", "loai": lead["nguon"], "tieu_de": tieu_de, "khoi": c["khoi"].get(nq) or lead["khoi"], "nguoi_quyet": nq, "muc": lead["muc"],
            "diem": sum(f["diem"] for f in g), "su_that": su_that, "chi_so": lead["chi_so"]}


def gom(fs: list[dict], now: datetime, c: dict) -> list[dict]:
    """Các phát hiện cùng nguồn và cùng người quyết thành MỘT vấn đề. Nhóm chỉ có phát hiện mức thấp thì không thành vấn đề."""
    ngay, ngay_hien = _ngay(now)
    nhom: dict[str, list] = {}
    for f in fs:
        nhom.setdefault(f["nhom"], []).append(f)
    return [_gom_nhom(g, ngay, ngay_hien, c) for g in nhom.values() if any(f["muc"] != THAP for f in g)]


def thu_su_that(now: datetime | None = None, toi_da: int = TOI_DA_VAN_DE, c: dict | None = None) -> list[dict]:
    """3-5 vấn đề lớn nhất trong ngày (mức cao xếp trước, rồi điểm); mọi vấn đề mức cao luôn được giữ dù vượt `toi_da`."""
    now = now or td.bay_gio()
    c = c or ngu_canh(now)
    vs = sorted(gom(quet(c), now, c), key=lambda v: (HANG_MUC[v["muc"]], -v["diem"]))
    return vs[:max(toi_da, sum(1 for v in vs if v["muc"] == CAO))]


# ------------------------------------------------------------------ bản LUẬT (khuôn cố định)
def _pa(ma: str, tieu_de: str, mo_ta: str) -> dict:
    return {"ma": ma, "tieu_de": tieu_de, "mo_ta": mo_ta}


def _noi_dung_luat(v: dict) -> tuple[str, list[dict], str]:
    s = v["su_that"]
    bc = s["bang_chung"]
    loai = s["loai"]
    if loai == "qua_han_team":
        ql = v["nguoi_quyet"]
        nd = (f"Team {ql} có {_so(bc['qua_han'])} việc quá hạn trên {_so(bc['dang_mo'])} việc đang mở ({bc['ty_le_qua_han']}%), trong đó {_so(bc['chua_giao'])} việc chưa giao cho ai "
              f"và {_so(bc['muc_cao'])} việc mức Cao.")
        pa = [_pa("A", "Họp nhanh chốt từng việc quá hạn", "Quản lý team rà từng việc quá hạn trong ngày: ai làm, xong khi nào."),
              _pa("B", "Chia lại việc cho người đang nhẹ việc", "Giao lại hoặc chia đều để người ít việc nhất nhận thêm, ưu tiên việc mức Cao."),
              _pa("C", "Chấp nhận trễ có kiểm soát", "Báo các bên liên quan, dời hạn và chỉ tập trung việc mức Cao trước.")]
        return nd, pa, "B" if bc["chua_giao"] * 2 >= bc["qua_han"] else "A"
    if loai == "hang_cho":
        nd = f"Quản lý {v['nguoi_quyet']} có {_so(bc['hang_cho'])} việc hàng chờ chưa giao cho ai, trong đó {_so(bc['muc_cao'])} việc mức Cao. Việc không có người phụ trách sẽ tiếp tục quá hạn."
        pa = [_pa("A", "Chia đều việc hàng chờ ngay", "Dùng lệnh chia deu để giao cho nhân viên đúng khối, ai ít việc nhận trước."),
              _pa("B", "Xin thêm người hỗ trợ", "Nhờ team khác cùng khối nhận bớt việc trong vài ngày."),
              _pa("C", "Chỉ xử lý việc mức Cao trước", "Giao riêng việc mức Cao, các việc còn lại chờ đợt chia sau.")]
        return nd, pa, "A"
    if loai == "cao_chi_nhanh":
        nd = (f"Chi nhánh đang có {_so(bc['muc_cao'])} việc mức Cao chưa xong, {_so(bc['qua_han_muc_cao'])} việc đã quá hạn và {_so(bc['chua_giao_muc_cao'])} việc chưa giao cho ai.")
        pa = [_pa("A", "Mỗi khối chốt người xử lý việc mức Cao", "Yêu cầu từng khối nêu người phụ trách và giờ xong cho mọi việc mức Cao trong ngày."),
              _pa("B", "Lập nhóm xử lý nhanh liên khối", "Cử một đầu mối cho mỗi hợp đồng có việc ở nhiều khối để khỏi chờ nhau."),
              _pa("C", "Theo dõi thêm một ngày", "Chưa can thiệp, kiểm lại số việc mức Cao vào ngày mai.")]
        return nd, pa, "A"
    if loai == "kt_im_lang":
        nd = (f"Có {_so(bc['so_muc'])} ca tồn Kỹ thuật không có cập nhật ghi chú từ {_so(bc.get('nguong_gio', KT_IM_LANG_GIO))} giờ, trong đó {_so(bc['so_cao'])} ca im lặng rất lâu. "
              "Ca im lặng thường là ca chưa ai đụng tới.")
        pa = [_pa("A", "Điều hành gọi từng ca và bắt buộc ghi chú", "Người điều hành Kỹ thuật hỏi lại tình hình từng ca im lặng và yêu cầu ghi chú trong ngày."),
              _pa("B", "Chuyển ca sang kỹ thuật viên đang rảnh", "Phân tuyến lại các ca im lặng lâu nhất cho người ít ca tồn."),
              _pa("C", "Nhờ DVKH và Kinh doanh chủ động báo khách", "Báo khách tiến độ để giảm khiếu nại trong lúc Kỹ thuật xử lý.")]
        return nd, pa, "A"
    nd = f"{v['tieu_de']}. Cần người có thẩm quyền xem chi tiết và giao người xử lý."
    return nd, [_pa("A", "Xem chi tiết và giao người xử lý", "Mở trang chi tiết, chốt người và hạn xử lý trong ngày."), _pa("B", "Theo dõi thêm một ngày", "Chưa can thiệp, kiểm lại vào ngày mai.")], "A"


def _bo_sung(nd: str, s: dict) -> str:
    """Bước ghép bản tin: mọi phát hiện mức cao phải có trong nội dung (thiếu thì chèn); phát hiện mức thấp gộp thành một dòng."""
    thieu = [f["doi_tuong"] for f in s["phat_hien_cao"] if f["doi_tuong"].lower() not in nd.lower()]
    if thieu:
        nd += f" Cần xem: {', '.join(thieu)}."
    if s["bang_chung"]["so_cao"] > len(s["phat_hien_cao"]):
        nd += f" Còn {s['bang_chung']['so_cao'] - len(s['phat_hien_cao'])} mục mức cao khác."
    if s["bang_chung"]["so_thap"]:
        nd += f" Còn {s['bang_chung']['so_thap']} mục nhỏ (mức thấp) chưa nêu riêng."
    return nd


# ------------------------------------------------------------------ LLM: gọi, kiểm số, trần lượt, nhớ kết quả
def _tran_ngay() -> int:
    try:
        return int(os.getenv("TRO_LY_DIEU_HANH_TRAN_NGAY", TRAN_NGAY_MAC_DINH))
    except ValueError:
        return TRAN_NGAY_MAC_DINH


def _khoa_ngay(now: datetime) -> str:
    return "tdh_llm:" + _ngay(now)[0]


def dem_llm(now: datetime | None = None) -> int:
    return int(td.doc_cai_dat(_khoa_ngay(now or td.bay_gio()), "0") or 0)


def _ung_vien(tok: str) -> list:
    """Các cách đọc một số trong câu: "1.234" là nghìn hoặc thập phân, "5,4%" là 5.4, ngày giờ giữ nguyên chữ."""
    t = tok.rstrip("%")
    if "/" in t or ":" in t:
        return [t]
    cach = [float(t.replace(",", "."))] if t.count(",") <= 1 and t.count(".") <= 1 else []
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", t):
        cach.append(float(t.replace(".", "").replace(",", ".")))
    return cach or [t]


def _so_cho_phep(x, kq: set) -> set:
    if isinstance(x, bool) or x is None:
        return kq
    if isinstance(x, (int, float)):
        kq.update([round(float(x), 6)])
    elif isinstance(x, str):
        for tok in _SO.findall(x):
            kq.update(round(v, 6) if isinstance(v, float) else v for v in _ung_vien(tok))
    elif isinstance(x, dict):
        for v in x.values():
            _so_cho_phep(v, kq)
    elif isinstance(x, (list, tuple)):
        for v in x:
            _so_cho_phep(v, kq)
    return kq


def kiem_so(chu: str, bang_su_that) -> bool:
    """Đúng khi mọi số / ngày trong `chu` có trong bảng sự thật (so khớp theo giá trị, đọc được kiểu 1.234 và 5,4%)."""
    cho_phep = _so_cho_phep(bang_su_that, set())
    for tok in _SO.findall(chu or ""):
        if not any((round(v, 6) if isinstance(v, float) else v) in cho_phep for v in _ung_vien(tok)):
            return False
    return True


def _doc_json(raw: str) -> dict | None:
    t = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(), flags=re.M).strip()
    try:
        j = json.loads(t)
    except ValueError:
        return None
    return j if isinstance(j, dict) else None


def _kiem_ket_qua(j: dict | None, bang: dict) -> dict | None:
    """Chỉ nhận JSON đúng khuôn: nhận định ngắn, 2-3 phương án mã A/B/C, khuyến nghị là một trong các phương án, mọi số có trong bảng, không dùng chữ cấm."""
    try:
        nd, pa, kn = str(j["nhan_dinh"]).strip(), j["phuong_an"], str(j["khuyen_nghi"]).strip().upper()
        ds = [_pa(str(p["ma"]).strip().upper(), str(p["tieu_de"]).strip(), str(p["mo_ta"]).strip()) for p in pa]
    except (TypeError, KeyError, ValueError, AttributeError):
        return None
    if not (2 <= len(ds) <= 3) or [p["ma"] for p in ds] != ["A", "B", "C"][:len(ds)] or kn not in {p["ma"] for p in ds}:
        return None
    if not nd or len(nd) > 600 or any(not p["tieu_de"] or not p["mo_ta"] or len(p["tieu_de"]) > 90 or len(p["mo_ta"]) > 220 for p in ds):
        return None
    chu = " ".join([nd, *[p["tieu_de"] + " " + p["mo_ta"] for p in ds]])
    return None if _NGOAI_LE_CHU.search(chu) or not kiem_so(chu, bang) else {"nhan_dinh": nd, "phuong_an": ds, "khuyen_nghi": kn}


HE_THONG = ("Bạn là trợ lý điều hành của một chi nhánh viễn thông, viết cho trưởng phòng / giám đốc đọc trên điện thoại. Chỉ dùng số có trong bảng_su_that: chép đúng, "
            "không tính thêm, không làm tròn lại, không đánh số thứ tự. Gọi team và hợp đồng bằng đúng mã trong bảng, không bịa tên, không bịa nguyên nhân. Dùng chữ 'online', không dùng chữ 'đấu nối'. "
            "Viết tiếng Việt dễ hiểu, câu ngắn. Trả về MỘT đối tượng JSON: {\"nhan_dinh\": tối đa 3 câu, \"phuong_an\": [{\"ma\": \"A\", \"tieu_de\": ..., \"mo_ta\": ...}, ...] gồm 2 hoặc 3 phương án mã A, B, C, "
            "\"khuyen_nghi\": mã một phương án}. Mỗi phương án nêu việc cần làm và ai làm. Hướng gợi ý nằm ở phuong_an_mau, được viết lại cho sát tình hình.")


def _goi_va_kiem(v: dict, goi_llm, nd: str, pa: list[dict], kn: str, now: datetime) -> tuple[dict | None, str]:
    """(kết quả đã kiểm, lý do dùng luật). Nhớ theo (vấn đề, bảng sự thật); tính một lượt vào trần ngày trước khi gọi."""
    bang = v["su_that"]
    khoa = "tdh_nho:" + hashlib.sha1((v["ma_van_de"] + json.dumps(bang, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()
    da_nho = td.doc_cai_dat(khoa)
    if da_nho:
        j = _kiem_ket_qua(_doc_json(da_nho), bang)
        if j:
            return j, ""
    if dem_llm(now) >= _tran_ngay():
        return None, "het_tran"
    td.ghi_cai_dat(_khoa_ngay(now), str(dem_llm(now) + 1))
    try:
        raw = goi_llm(HE_THONG, json.dumps({"bang_su_that": bang, "phuong_an_mau": [{"ma": p["ma"], "tieu_de": p["tieu_de"]} for p in pa], "khuyen_nghi_mau": kn}, ensure_ascii=False))
    except Exception:
        return None, "loi_ai"
    j = _kiem_ket_qua(_doc_json(raw), bang)
    if not j:
        return None, "sai_dinh_dang_hoac_so"
    td.ghi_cai_dat(khoa, json.dumps(j, ensure_ascii=False))
    return j, ""


def soan(v: dict, goi_llm=None, ten: dict | None = None, now: datetime | None = None) -> dict:
    """Dựng nhận định + phương án + khuyến nghị cho một vấn đề. `goi_llm(he_thong, nguoi_dung) -> chuỗi JSON` (None = chỉ dùng luật).
    Trả {nhan_dinh, phuong_an, khuyen_nghi, nguon_noi_dung: "llm" | "luat", ly_do_luat}."""
    now = now or td.bay_gio()
    nd, pa, kn = _noi_dung_luat(v)
    nguon, ly_do = "luat", "chua_bat_ai" if goi_llm is None else ""
    if goi_llm is not None:
        j, ly_do = _goi_va_kiem(v, goi_llm, nd, pa, kn, now)
        if j:
            nd, pa, kn, nguon = j["nhan_dinh"], j["phuong_an"], j["khuyen_nghi"], "llm"
    nd = _bo_sung(nd, v["su_that"])
    h = lambda t: _hien(t, ten)
    return {"nhan_dinh": h(nd), "phuong_an": [{**p, "tieu_de": h(p["tieu_de"]), "mo_ta": h(p["mo_ta"])} for p in pa], "khuyen_nghi": kn, "nguon_noi_dung": nguon, "ly_do_luat": ly_do}


# ------------------------------------------------------------------ trạng thái AI và hàm gọi LLM thật
def trang_thai_ai(now: datetime | None = None) -> dict:
    """AI đang BẬT hay đang dùng BẢN LUẬT, và vì sao. Chỉ đọc cấu hình, không gọi mạng."""
    tran, dem = _tran_ngay(), dem_llm(now)
    kq = {"dung_ai": False, "ly_do": "", "luot_hom_nay": dem, "tran_ngay": tran}
    if os.getenv("LIEN_KHOI_TRO_LY_AI", "1").strip() == "0":
        return {**kq, "ly_do": "Đã tắt bằng biến môi trường LIEN_KHOI_TRO_LY_AI=0."}
    try:
        from app import tro_ly
        ch = tro_ly.cau_hinh()
        if not ch["bat"]:
            return {**kq, "ly_do": "Trợ lý AI của app đang tắt (Quản trị → Trợ lý AI)."}
        if not ch["key"]:
            return {**kq, "ly_do": "Chưa có khoá API (dán ở Quản trị → Trợ lý AI)."}
        if tro_ly.chi_phi_thang() >= ch["tran_usd"]:
            return {**kq, "ly_do": "Đã hết ngân sách AI của tháng này."}
    except Exception:
        return {**kq, "ly_do": "Không đọc được cấu hình Trợ lý AI."}
    if dem >= tran:
        return {**kq, "ly_do": f"Đã dùng hết {tran} lượt gọi AI của hôm nay."}
    return {**kq, "dung_ai": True}


def goi_llm_mac_dinh():
    """Hàm gọi LLM thật qua `app/tro_ly.py` (khoá và hạn mức tháng của app); None nếu AI chưa dùng được."""
    if not trang_thai_ai()["dung_ai"]:
        return None
    from app import tro_ly
    ch = tro_ly.cau_hinh()

    def goi(he_thong: str, nguoi_dung: str) -> str:
        msg = tro_ly.hoi([{"role": "system", "content": he_thong}, {"role": "user", "content": nguoi_dung}], ch["model_chat"], ch["key"], "tro_ly_dieu_hanh", "dieu_hanh",
                         han=40, toi_da=1800, dinh_dang={"type": "json_object"})
        return msg.get("content") or ""
    return goi


# ------------------------------------------------------------------ tin Zalo
def _soan_tin(tieu_de: str, mau=zv.XANH_DUONG):
    return zv._soan().them(tieu_de, "b", zv.CO_LON, mau)


def tin_de_xuat(r: dict, ten: dict, gioi_han: int = TOI_DA_KY_TU) -> object:
    """Tin đề xuất cho người quyết: tiêu đề, nhận định, các phương án, khuyến nghị, hạn, lệnh trả lời. Dài quá thì rút gọn mô tả phương án (không bao giờ cắt lệnh trả lời)."""
    s = r["su_that"]
    for gh in (150, 100, 60, 0):
        t = _soan_tin(f"ĐỀ XUẤT CẦN QUYẾT #{r['id']}").them(f"\n{_hien(r['tieu_de'], ten)}", "b")
        t.them(f"\n\n{r['nhan_dinh']}")
        t.them("\n\nPHƯƠNG ÁN", "b", zv.CO_NHO, zv.XAM)
        for p in r["phuong_an"]:
            sao = " (khuyến nghị)" if p["ma"] == r["khuyen_nghi"] else ""
            t.them(f"\n{p['ma']}. ", "b").them(p["tieu_de"] + sao, "b").them(f" – {zv._ngan(p['mo_ta'], gh)}" if gh else "")
        t.them(f"\n\nKhuyến nghị: {r['khuyen_nghi']}", "b", zv.CAM)
        thieu = [_hien(f["doi_tuong"], ten) for f in s["phat_hien_cao"] if _hien(f["doi_tuong"], ten) not in "".join(c for c, _ in t.phan)]
        if thieu:
            t.them(f"\nCần xem: {', '.join(thieu)}", zv.CO_NHO)
        t.them(f"\nHạn quyết: {_vn(r['han_quyet'])}", zv.CO_NHO, zv.XAM)
        t.them(f"\n\nTrả lời: dong y {r['id']} {r['khuyen_nghi']} | sua {r['id']} <ý kiến> | bac {r['id']} <lý do>", "b", zv.CO_NHO)
        t.them(f"\nXem chi tiết: {zv.goc_app()}{s.get('duong_dan', '')}", zv.CO_NHO, zv.XANH_DUONG)
        tin = t.xong()
        if len(tin) <= gioi_han:
            return tin
    return zv._cat_tin(tin, gioi_han)


def tin_nhac(r: dict, ten: dict) -> object:
    t = _soan_tin("NHẮC QUYẾT ĐỊNH", zv.CAM).them(f"\n#{r['id']} {_hien(r['tieu_de'], ten)}", "b")
    t.them(f"\n\nĐề xuất từ {_vn(r['tao_luc'])}, hạn quyết {_vn(r['han_quyet'])} đã qua. Khuyến nghị của trợ lý: phương án {r['khuyen_nghi']}.")
    t.them(f"\n\nTrả lời: dong y {r['id']} {r['khuyen_nghi']} | sua {r['id']} <ý kiến> | bac {r['id']} <lý do>", "b", zv.CO_NHO)
    return zv._cat_tin(t.xong())


def tin_leo_thang(r: dict, ten: dict) -> object:
    t = _soan_tin("ĐỀ XUẤT QUÁ HẠN QUYẾT", zv.DO).them(f"\n#{r['id']} {_hien(r['tieu_de'], ten)}", "b")
    t.them(f"\n\n{ten.get(r['nguoi_quyet'], r['nguoi_quyet'])} chưa quyết sau hạn {_vn(r['han_quyet'])}. Anh/chị cấp trên có thể quyết thay hoặc nhắc người phụ trách.")
    t.them(f"\n\nTrả lời: dong y {r['id']} {r['khuyen_nghi']} | sua {r['id']} <ý kiến> | bac {r['id']} <lý do>", "b", zv.CO_NHO)
    return zv._cat_tin(t.xong())


def tin_kiem_chung(r: dict, ten: dict) -> object:
    ds = {p["ma"]: p for p in r["phuong_an"]}
    lc = ds[r["lua_chon"]]["tieu_de"] if r["lua_chon"] in ds else "Người quyết sửa ý: " + zv._ngan(r["ghi_chu"] or "", 120)
    t = _soan_tin("KẾT QUẢ SAU QUYẾT ĐỊNH").them(f"\n#{r['id']} {_hien(r['tieu_de'], ten)}", "b")
    t.them(f"\n\nĐã chọn: {lc}", "b").them(f"\nQuyết lúc {_vn(r['quyet_luc'])}, đo lại lúc {_vn(r['han_kiem_chung'])}.", zv.CO_NHO, zv.XAM)
    t.them(f"\n\n{r['ket_qua']}")
    return zv._cat_tin(t.xong())


def _gui_cho(ma: str, ds: pd.DataFrame, loai: str, tin, now: datetime) -> bool:
    x = ds[ds["ma"] == ma]
    return zv._da_giao(zv._gui(ma, str(x["chat_id"].iloc[0]) if len(x) else "", loai, tin, now))


# ------------------------------------------------------------------ vòng chạy
def _ghi_van_de(v: dict, kq: dict, ten: dict, now: datetime) -> int | None:
    h = qd.cau_hinh()
    return qd.tao({"ma_van_de": v["ma_van_de"], "tieu_de": _hien(v["tieu_de"], ten), "khoi": v["khoi"], "nguoi_quyet": v["nguoi_quyet"],
                   "su_that": {**v["su_that"], "soan_luat_vi": kq["ly_do_luat"]}, "nhan_dinh": kq["nhan_dinh"], "phuong_an": kq["phuong_an"], "khuyen_nghi": kq["khuyen_nghi"],
                   "han_quyet": td._s(now + timedelta(hours=h["han_quyet_gio"])), "han_kiem_chung": None, "chi_so_truoc": {**v["chi_so"], "luc": td._s(now)},
                   "nguon_noi_dung": kq["nguon_noi_dung"]}, now)


def chay_buoi_sang(now: datetime | None = None, goi_llm=MAC_DINH) -> dict:
    """Quét, tạo đề xuất cho các vấn đề CHƯA có hôm nay (không tạo trùng), rồi gửi các đề xuất chưa tới tay người quyết. Trả {moi, gui, ai, luat}."""
    now = now or td.bay_gio()
    goi = goi_llm_mac_dinh() if goi_llm is MAC_DINH else goi_llm
    c = ngu_canh(now)
    moi = ai = 0
    for v in thu_su_that(now, c=c):
        if qd.doc_theo_ma(v["ma_van_de"]):
            continue
        kq = soan(v, goi, c["ten"], now)
        if _ghi_van_de(v, kq, c["ten"], now):
            moi += 1
            ai += kq["nguon_noi_dung"] == "llm"
    gui = 0
    for r in qd.liet_ke("cho_quyet"):
        if not r["da_gui_luc"] and _gui_cho(r["nguoi_quyet"], c["ds"], "quyet_dinh", tin_de_xuat(r, c["ten"]), now):
            qd.danh_dau(r["id"], "da_gui_luc", now)
            gui += 1
    return {"moi": moi, "gui": gui, "ai": ai, "luat": moi - ai}


def _cap_tren(ma: str, c: dict) -> str:
    x = c["ds"][c["ds"]["ma"] == ma]
    ql = str(x["quan_ly"].iloc[0]) if len(x) else ""
    return ql or (c["gd"] if c["gd"] != ma else "")


def nhac_quyet(now: datetime | None = None) -> dict:
    """Quá hạn quyết thì nhắc người quyết (một lần); quá thêm `leo_thang_gio` thì báo cấp trên (một lần) và đổi sang "quá hạn quyết"."""
    now = now or td.bay_gio()
    c = ngu_canh(now)
    leo = timedelta(hours=qd.cau_hinh()["leo_thang_gio"])
    nhac = bao = 0
    for r in qd.qua_han(now):
        if not r["nhac_luc"] and _gui_cho(r["nguoi_quyet"], c["ds"], "nhac_quyet", tin_nhac(r, c["ten"]), now):
            qd.danh_dau(r["id"], "nhac_luc", now)
            nhac += 1
        if not r["leo_thang_luc"] and pd.Timestamp(r["han_quyet"]) + leo <= pd.Timestamp(now):
            tren = _cap_tren(r["nguoi_quyet"], c)
            if not tren or _gui_cho(tren, c["ds"], "leo_thang", tin_leo_thang(r, c["ten"]), now):
                qd.danh_dau(r["id"], "leo_thang_luc", now)
                qd.het_han(r["id"], now)
                bao += 1
    return {"nhac": nhac, "bao_cap_tren": bao}


def cau_ket_qua(cs: dict, sau: int) -> str:
    """Câu kết quả bằng luật: so chỉ số đo lúc đề xuất với số đo lại."""
    truoc, nhan, dv = cs["gia_tri"], cs["nhan"], cs.get("don_vi", "")
    if sau == truoc:
        return f"{nhan} không đổi, vẫn {_so(sau)} {dv}. Chưa cải thiện."
    huong = "giảm" if sau < truoc else "tăng"
    giua = "xuống" if sau < truoc else "lên"
    pt = f" ({huong} {_so(round(abs(sau - truoc) / truoc * 100))}%)" if truoc else ""
    tot = (sau < truoc) == (cs.get("tot_khi", "giam") == "giam")
    return f"{nhan} {huong} từ {_so(truoc)} {giua} {_so(sau)} {dv}{pt}. {'Đã cải thiện.' if tot else 'Chưa cải thiện.'}"


def _viet_lai_ket_qua(cs: dict, sau: int, luat: str, goi_llm, ten: dict, now: datetime) -> tuple[str, str]:
    if goi_llm is None or dem_llm(now) >= _tran_ngay():
        return _hien(luat, ten), "luat"
    bang = {"chi_so": cs["nhan"], "don_vi": cs.get("don_vi", ""), "truoc": cs["gia_tri"], "sau": sau, "cau_luat": luat}
    td.ghi_cai_dat(_khoa_ngay(now), str(dem_llm(now) + 1))
    try:
        j = _doc_json(goi_llm("Viết lại MỘT hoặc hai câu kết quả ngắn gọn cho lãnh đạo từ bảng_su_that, chỉ dùng số trong bảng, không chữ 'đấu nối'. Trả JSON {\"ket_qua\": \"...\"}.",
                              json.dumps({"bang_su_that": bang}, ensure_ascii=False)))
        kq = str(j["ket_qua"]).strip() if j else ""
    except Exception:
        kq = ""
    if not kq or len(kq) > 300 or _NGOAI_LE_CHU.search(kq) or not kiem_so(kq, bang):
        return _hien(luat, ten), "luat"
    return _hien(kq, ten), "llm"


def kiem_chung(now: datetime | None = None, goi_llm=MAC_DINH) -> dict:
    """Quyết định tới hạn đo lại: đo bằng CÙNG hàm lúc đề xuất, ghi trước / sau và một câu kết quả, báo giám đốc (và người quyết) đúng một lần."""
    now = now or td.bay_gio()
    c = ngu_canh(now)
    cho = qd.can_kiem_chung(now)
    goi = (goi_llm_mac_dinh() if goi_llm is MAC_DINH else goi_llm) if cho else None
    xong = 0
    for r in cho:
        cs = r["chi_so_truoc"]
        sau = do_chi_so(cs["loai"], cs["tham_so"], c)
        kq, nguon = _viet_lai_ket_qua(cs, sau, cau_ket_qua(cs, sau), goi, c["ten"], now)
        xong += qd.ghi_kiem_chung(r["id"], {"gia_tri": sau, "luc": td._s(now)}, kq, nguon, now)
    bao = 0
    for r in qd.liet_ke("da_kiem_chung"):
        if r["bao_kiem_chung_luc"]:
            continue
        tin = tin_kiem_chung(r, c["ten"])
        nguoi = [m for m in dict.fromkeys([c["gd"], r["nguoi_quyet"]]) if m]
        if all([_gui_cho(m, c["ds"], "kiem_chung", tin, now) for m in nguoi]):
            qd.danh_dau(r["id"], "bao_kiem_chung_luc", now)
            bao += 1
    return {"kiem_chung": xong, "da_bao": bao}


def vong_tu_dong(now: datetime | None = None, goi_llm=MAC_DINH) -> dict:
    """Một vòng của script tự chạy: buổi sáng đúng một lần mỗi ngày, nhắc và kiểm chứng ở mọi vòng."""
    now = now or td.bay_gio()
    ngay = _ngay(now)[0]
    sang = {"moi": 0, "gui": 0, "ai": 0, "luat": 0}
    if td.doc_cai_dat("tdh_buoi_sang") != ngay:
        sang = chay_buoi_sang(now, goi_llm)
        td.ghi_cai_dat("tdh_buoi_sang", ngay)
    return {**sang, **nhac_quyet(now), **kiem_chung(now, goi_llm)}
