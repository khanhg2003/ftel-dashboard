"""Trích phần KPIs của web TAIHD (taihd1dhtinhue) đã lưu bằng Chrome (Ctrl+S) cho trang /kt/kpi.

Giữ NGUYÊN giao diện gốc (HTML + CSS của web, biểu đồ Plotly đã thành SVG lúc lưu) để màu sắc y hệt, nhưng:
- chỉ lấy phần nội dung chính (<main>), bỏ menu, script, nút, ô nhập;
- bỏ hẳn cột có thông tin khách hàng / chữ tự do (tên khách, địa chỉ, MAC, ghi chú...);
- đổi tên NV, Điều hành, mã HĐ, mã thiết bị sang mã giả bằng CÙNG bảng mã với Báo cáo tồn; che số điện thoại.
Gọi từ scripts/trich_bao_cao_ton.py (một lần chạy cho cả hai báo cáo để mã giả thống nhất).
"""
from __future__ import annotations

import base64
import html
import json
import re
from pathlib import Path

THU_MUC = Path(__file__).resolve().parents[1] / "demo" / "lien_khoi" / "kt_kpi"
MUC = [("tong", "Tổng quan"), ("nhan_su", "KPI nhân sự"), ("huy", "Hủy dịch vụ"), ("hifpt", "HiFPT"), ("csat", "CSAT"),
       ("lap", "Lặp"), ("thu_hoi", "Thu hồi thiết bị"), ("suy_hao", "Suy hao TK-BT"), ("swap", "SWAP WiFI4")]
BO_COT = re.compile(r"khách hàng|địa chỉ|\bmac\b|ghi ch|ghi nhận|nội dung|hướng xử lý|sđt|điện thoại|thao tác|xử lý$|^✎", re.I)
TEN_DH = r"(?i)(?<!\w)t[aà]i\s*hd\d*(?!\w)"            # Điều hành viết có dấu ở cột Đội trưởng ("TÀI HD1" = TAIHD)
MA_HD = r"(?<![A-Za-z0-9])(HUEP[A-Za-z0-9]+|HU[A-Za-z]{1,3}\d{4,6}|[A-Z]{2,4}\d{8,})(?![A-Za-z0-9])"


def la_kpi(t: str) -> bool:
    return 'class="kpi-subnav"' in t


def muc_cua(t: str) -> str:
    """Mục = nút (kpi-pill) đang bật trên thanh mục KPI."""
    m = re.search(r'<a class="kpi-pill active"[^>]*>(.*?)</a>', t, re.S)
    ten = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", m.group(1)))).strip().lower() if m else ""
    return next((ma for ma, t2 in MUC if t2.lower() == ten), "")


def chot_luc(t: str) -> str:
    m = re.search(r"Số liệu KPI lúc\s*([0-9/]+ [0-9:]+)", t)
    return m.group(1) if m else ""


def _bo_cot(bang: str) -> str:
    """Bỏ các cột nhạy cảm (tiêu đề + ô cùng vị trí) trong một <table>."""
    dau = re.search(r"<tr.*?</tr>", bang, re.S)
    if dau is None:
        return bang
    tieu_de = re.findall(r"<th[^>]*>(.*?)</th>", dau.group(0), re.S)
    bo ={i for i, c in enumerate(tieu_de) if BO_COT.search(re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip())}
    if not bo:
        return bang

    def dong(m):
        o = re.findall(r"<t[hd][^>]*>.*?</t[hd]>", m.group(2), re.S)
        if len(o) != len(tieu_de):          # dòng gộp cột (vd "Không có dữ liệu") giữ nguyên
            return m.group(0)
        return m.group(1) + "".join(x for i, x in enumerate(o) if i not in bo) + "</tr>"
    return re.sub(r"(<tr[^>]*>)(.*?)</tr>", dong, bang, flags=re.S)


BO_KHOI = ("taihdKpiExportGroups", "taihdStaffSwitchBar")      # khung chọn xuất ảnh / đổi nhân sự: chỉ dùng được trên web gốc


def bo_khoi(h: str, id_: str) -> str:
    """Gỡ trọn một <div id=...> (đếm div lồng nhau để cắt đúng thẻ đóng)."""
    m = re.search(rf'<div\b[^>]*\bid="{id_}"[^>]*>', h)
    if not m:
        return h
    sau, tang = m.end(), 1
    for the in re.finditer(r"<(/?)div\b[^>]*>", h[sau:]):
        tang += -1 if the.group(1) else 1
        if tang == 0:
            return h[:m.start()] + h[sau + the.end():]
    return h


def lam_sach(t: str) -> tuple[str, str]:
    """(style riêng của trang, nội dung <main> đã bỏ phần thừa và cột nhạy cảm)."""
    main = re.search(r"<main[^>]*>.*</main>", t, re.S).group(0)
    for the in ("script", "button", "form", "select", "textarea", "noscript"):
        main = re.sub(rf"<{the}\b.*?</{the}>", "", main, flags=re.S | re.I)
    main = re.sub(r"<input\b[^>]*>", "", main, flags=re.I)
    for id_ in BO_KHOI:
        main = bo_khoi(main, id_)
    main = re.sub(r"\son\w+=\"[^\"]*\"", "", main)                          # bỏ onclick=... còn sót
    main = re.sub(r"<table.*?</table>", lambda m: _bo_cot(m.group(0)), main, flags=re.S)
    dau = t[: t.find("<body")]
    kieu = "\n".join(re.findall(r"<style[^>]*>.*?</style>", dau, re.S))
    return kieu, main


def nhung_anh(h: str, f: Path) -> str:
    """Ảnh trỏ vào thư mục _files đã lưu (vd logo HiFPT) → nhúng thẳng base64 vì thư mục đó không đi theo; không tìm thấy thì bỏ ảnh."""
    def doi(m):
        duong = f.parent / html.unescape(m.group(2)).lstrip("./")
        if not duong.exists():
            return ""
        kieu = "image/svg+xml" if duong.suffix == ".svg" else f"image/{duong.suffix.lstrip('.').replace('jpg', 'jpeg')}"
        return f'{m.group(1)}data:{kieu};base64,{base64.b64encode(duong.read_bytes()).decode()}{m.group(3)}'
    return re.sub(r'(<img\b[^>]*\ssrc=")(\./[^"]+_files/[^"]+)("[^>]*>)', doi, h)


def _doi_chu(h: str, ham) -> str:
    """Áp `ham` lên phần CHỮ (giữa các thẻ) và vài thuộc tính hiển thị; không đụng <style>, đường vẽ SVG, tên lớp."""
    phan = re.split(r"(<style\b.*?</style>)", h, flags=re.S)
    for i in range(0, len(phan), 2):
        p = re.sub(r">([^<]+)<", lambda m: ">" + ham(m.group(1)) + "<", phan[i])
        phan[i] = re.sub(r'(\s(?:title|alt|aria-label|value|data-[\w-]+)=")([^"]*)(")', lambda m: m.group(1) + ham(m.group(2)) + m.group(3), p)
    return "".join(phan)


def chu_hien(h: str) -> str:
    """Toàn bộ phần chữ hiển thị (để dò sót tên thật)."""
    ds = []
    _doi_chu(h, lambda s: ds.append(s) or s)
    return "\n".join(ds)


def an_danh_kpi(trang: dict, bo) -> dict:
    """Lượt 1: hueti.xxx → KTV, mã HĐ / OLT / hoá đơn → mã giả, che số điện thoại.
    Lượt 2: mọi tên thật đã biết (từ cả Báo cáo tồn) xuất hiện ở dạng nào, hoa hay thường, cũng đổi theo."""
    def luot1(s):
        s = re.sub(r"(?i)\bhueti\.([a-z0-9]+)", lambda m: bo.ma(m.group(1).upper()), s)
        s = re.sub(TEN_DH, lambda m: bo.ma("TAIHD"), s)
        s = re.sub(MA_HD, lambda m: bo.ma(m.group(0)), s)
        return re.sub(r"(?<!\d)\d{9,}(?!\d)", lambda m: m.group(0)[:2] + "*" * (len(m.group(0)) - 2), s)
    trang = {k: _doi_chu(v, luot1) for k, v in trang.items()}
    biet = sorted((k for k in bo.ten_that() if len(k) >= 4), key=len, reverse=True)
    mau = re.compile(r"(?i)(?<![A-Za-z0-9])(" + "|".join(map(re.escape, biet)) + r")(?![A-Za-z0-9])")
    return {k: _doi_chu(v, lambda s: mau.sub(lambda m: bo.ma(m.group(0)), s)) for k, v in trang.items()}


def kiem_sot(trang: dict, bo) -> list[str]:
    """Danh sách chữ thật còn sót (rỗng = sạch)."""
    sot = []
    biet = {k.lower() for k in bo.ten_that()}
    for ma, h in trang.items():
        chu = chu_hien(h)
        sot += [f"{ma}: {x}" for x in re.findall(r"(?i)hueti\.\w+|" + MA_HD, chu)]
        sot += [f"{ma}: {x}" for x in set(re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", chu)) if x.lower() in biet]
        sot += [f"{ma}: số dài {x}" for x in re.findall(r"(?<!\d)\d{9,}(?!\d)", chu)]
        sot += [f"{ma}: {x}" for x in re.findall(TEN_DH, chu)]
    return sot


def css_goc(cac_file: list[Path]) -> str:
    """Gộp CSS của web gốc (bootstrap, theme, app...) từ các thư mục _files đã lưu, mỗi file một lần."""
    da, kq = set(), []
    for f in cac_file:
        thu_muc = f.with_name(f.stem + "_files")
        for c in sorted(thu_muc.glob("*.css")) if thu_muc.exists() else []:
            if c.name not in da and "icons" not in c.name:
                da.add(c.name)
                kq.append(f"/* {c.name} */\n" + c.read_text(encoding="utf-8", errors="ignore"))
    bootstrap = [x for x in kq if x.startswith("/* bootstrap")]
    return "\n".join(bootstrap + [x for x in kq if x not in bootstrap])          # bootstrap trước, theme / app đè lên sau


def ghi(trang: dict, kieu: dict, cac_file: list[Path], chot: str) -> None:
    THU_MUC.mkdir(parents=True, exist_ok=True)
    for ma, h in trang.items():
        (THU_MUC / f"{ma}.html").write_text(kieu[ma] + "\n" + h, encoding="utf-8")
    (THU_MUC / "kpi.css").write_text(css_goc(cac_file), encoding="utf-8")
    (THU_MUC / "meta.json").write_text(json.dumps({"chot_luc": chot, "muc": [m for m, _ in MUC if m in trang]}, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
