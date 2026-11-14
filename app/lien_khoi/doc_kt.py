"""Đọc các file báo cáo của khối Kỹ thuật và đổi thành sự kiện theo mã hợp đồng (nhánh thi-lien-khoi).

Có 5 loại file theo mã hợp đồng (nhận ra bằng tên cột, không phụ thuộc tên file): tồn Kỹ thuật, triển khai đúng hạn, checklist lặp 30 ngày,
checklist sau triển khai, cáp LAN. File KPI theo block không có mã hợp đồng nên bỏ qua. Tên khách hàng KHÔNG được đọc ra.

File xuất từ hệ thống Kỹ thuật có phần định dạng mà openpyxl không mở được ("xfid"), nên đọc thẳng XML bên trong file .xlsx.
"""
from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET

import pandas as pd

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
KT_COT = ["so_hd", "loai", "thoi_diem", "chi_tiet", "nguoi", "so_lan", "goi", "sale", "tg_tao_hd", "tg_online"]
TEN_LOAI_KT = {"ton_kt": "Tồn Kỹ thuật", "trien_khai": "Triển khai", "checklist": "Checklist lặp (sự cố)",
               "checklist_sau_tk": "Checklist sau triển khai", "cap_lan": "Cáp LAN"}


def _ten_cot(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group():
        n = n * 26 + ord(ch) - 64
    return n - 1


def doc_xlsx(duong_dan) -> dict[str, list[list]]:
    """{tên sheet: các dòng} đọc thẳng từ XML trong file; ô trống là None."""
    z = zipfile.ZipFile(duong_dan)
    chuoi = []
    if "xl/sharedStrings.xml" in z.namelist():
        chuoi = ["".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])) for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS)]
    sheets = ET.fromstring(z.read("xl/workbook.xml")).find("m:sheets", NS)
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    kq = {}
    for sh in sheets:
        dich = rels[sh.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")]
        dong = []
        for r in ET.fromstring(z.read("xl/" + dich.lstrip("/").replace("xl/", ""))).iter("{%s}row" % NS["m"]):
            o = {}
            for c in r.findall("m:c", NS):
                v, t = c.find("m:v", NS), c.get("t")
                if t == "inlineStr":
                    o[_ten_cot(c.get("r"))] = "".join(x.text or "" for x in c.iter("{%s}t" % NS["m"]))
                elif v is not None:
                    o[_ten_cot(c.get("r"))] = chuoi[int(v.text)] if t == "s" else v.text
            dong.append([o.get(i) for i in range(max(o) + 1)] if o else [])
        kq[sh.get("name")] = dong
    return kq


def doc_bang(duong_dan) -> pd.DataFrame:
    """Sheet đầu tiên: dòng đầu là tên cột."""
    dong = next(iter(doc_xlsx(duong_dan).values()))
    if not dong:
        return pd.DataFrame()
    cot = [str(c or "").strip() for c in dong[0]]
    return pd.DataFrame([(r + [None] * len(cot))[:len(cot)] for r in dong[1:]], columns=cot)


def _t(s, ngay_truoc: bool = True) -> pd.Series:
    """Ngày giờ kiểu 03/11/2026 12:32:16 hoặc 03-11-2026 12:32:16 (ngày trước tháng). File cáp LAN ghi THÁNG trước ngày: truyền ngay_truoc=False."""
    return pd.to_datetime(pd.Series(s).replace("", None), format="mixed", dayfirst=ngay_truoc, errors="coerce")


def _chu(s) -> pd.Series:
    return pd.Series(s).fillna("").astype(str).str.strip()


def _so(s) -> pd.Series:
    return pd.to_numeric(pd.Series(s), errors="coerce")


def loai_file(cot) -> str | None:
    """Nhận ra file Kỹ thuật theo tên cột."""
    c = set(cot)
    if {"Số HĐ", "TG tạo PTC", "Sale HĐ"} <= c:
        return "ton"
    if {"Số hợp đồng", "Số lần hẹn"} <= c:
        return "trien_khai"
    if {"Số HĐ", "Số lần lặp"} <= c:
        return "checklist"
    if {"Hợp đồng", "Ngày checklist"} <= c:
        return "checklist_sau_tk"
    if {"HĐ", "Ngày active"} <= c:
        return "cap_lan"
    return None


def _khung(**cot) -> pd.DataFrame:
    n = max((len(v) for v in cot.values() if not isinstance(v, str)), default=0)           # chữ đơn (loai) áp cho mọi dòng
    d = pd.DataFrame({k: pd.Series([v] * n) if isinstance(v, str) else pd.Series(v).reset_index(drop=True) for k, v in cot.items()})
    for c in KT_COT:
        if c not in d.columns:
            d[c] = pd.NA
    d["so_hd"] = _chu(d["so_hd"]).str.upper()
    return d[d["so_hd"].ne("") & d["thoi_diem"].notna()][KT_COT].reset_index(drop=True)


def su_kien_tu_bang(d: pd.DataFrame) -> pd.DataFrame:
    """Một bảng đã đọc -> sự kiện chuẩn `KT_COT`. Không nhận ra loại file thì trả bảng rỗng."""
    k = loai_file(d.columns)
    if k == "ton":
        return _khung(so_hd=d["Số HĐ"], loai="ton_kt", thoi_diem=_t(d["TG tạo PTC"]), nguoi=_chu(d["Nhân sự"]), goi=_chu(d["Gói dịch vụ"]),
                      sale=_chu(d["Sale HĐ"]),
                      chi_tiet="Tồn Kỹ thuật: " + _chu(d["Tình trạng"]) + " - " + _chu(d["Loại triển khai"]))
    if k == "trien_khai":
        hoan_tat = _t(d["Ngày hoàn tất PTC"]).fillna(_t(d["Ngày online"]))
        dung = _chu(d["Đúng hẹn"]).eq("1")
        return _khung(so_hd=d["Số hợp đồng"], loai="trien_khai", thoi_diem=hoan_tat, nguoi=_chu(d["Nhân viên"]), so_lan=_so(d["Số lần hẹn"]),
                      goi=_chu(d["Gói dịch vụ"]), tg_tao_hd=_t(d["Ngày tạo hợp đồng"]), tg_online=_t(d["Ngày online"]),
                      chi_tiet="Triển khai: hẹn " + _chu(d["Số lần hẹn"]) + " lần, " + dung.map({True: "đúng hẹn", False: "không đúng hẹn"}))
    if k == "checklist":
        return _khung(so_hd=d["Số HĐ"], loai="checklist", thoi_diem=_t(d["Tg tạo CL"]), nguoi=_chu(d["Nhân viên"]), so_lan=_so(d["Số lần lặp"]),
                      tg_online=_t(d["Tg online"]), chi_tiet="Checklist lặp lần thứ " + _chu(d["Số lần lặp"]) + " trong 30 ngày")
    if k == "checklist_sau_tk":
        return _khung(so_hd=d["Hợp đồng"], loai="checklist_sau_tk", thoi_diem=_t(d["Ngày checklist"]), nguoi=_chu(d["Nhân viên"]),
                      goi=_chu(d["Gói dịch vụ"]), chi_tiet="Checklist sau triển khai: " + _chu(d["Tình trạng"]))
    if k == "cap_lan":
        ly_do = _chu(d["Nguyên nhân không dùng Cap Lan"]).where(lambda x: ~x.isin(["", "Không chọn nguyên nhân"]), "")
        return _khung(so_hd=d["HĐ"], loai="cap_lan", thoi_diem=_t(d["Ngày active"], ngay_truoc=False), nguoi=_chu(d["Nhân sự"]),
                      chi_tiet="Cáp LAN: kích hoạt bằng " + _chu(d["Active by"]) + ly_do.map(lambda x: f" ({x})" if x else ""))
    return pd.DataFrame(columns=KT_COT)


def su_kien_tu_cac_file(duong_dan: list) -> pd.DataFrame:
    """Gộp sự kiện của nhiều file Kỹ thuật (file không nhận ra thì bỏ qua)."""
    ds = [su_kien_tu_bang(doc_bang(p)) for p in duong_dan]
    ds = [d for d in ds if len(d)]
    return pd.concat(ds, ignore_index=True) if ds else pd.DataFrame(columns=KT_COT)
