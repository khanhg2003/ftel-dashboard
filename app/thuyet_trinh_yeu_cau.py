"""Hiểu YÊU CẦU thuyết trình bằng chữ (gõ hoặc nói): "báo cáo toàn bộ chi nhánh từ đầu tháng 11 đến 22/11", "phân tích phòng IBB7".

Bằng luật cố định, không gọi AI (rẻ, nhanh, ai cũng đoán trước được kết quả): tìm mã phòng (IBB7, B7, "ibb bảy", tên phòng như Tam Kỳ) và ngày kết thúc (dd/mm, "ngày 22 tháng 11", "tháng 10",
"hôm qua"); không nói gì thì là toàn chi nhánh, ngày có số mới nhất. App chỉ có số LUỸ KẾ TỪ NGÀY 01 của tháng nên ngày bắt đầu chỉ để báo lại cho người nghe, không đổi số. Luôn trả kèm câu `ghi_chu`
nói rõ app đã hiểu thế nào để người dùng sửa nếu hiểu sai.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta

SO_CHU = {"mot": 1, "hai": 2, "ba": 3, "bon": 4, "tu": 4, "nam": 5, "sau": 6, "bay": 7, "tam": 8, "chin": 9}


def _bo_dau(chu: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", chu.replace("đ", "d").replace("Đ", "D")) if unicodedata.category(c) != "Mn").lower()


def tim_phong(cau: str, phongs: list[dict]) -> str | None:
    """Mã phòng được nhắc trong câu: IBB7 / B7 / "ibb 7" / "phòng ibb bảy" / tên phòng (Tam Kỳ, Hội An...); không có thì None."""
    n = _bo_dau(cau)
    m = re.search(r"(?<![a-z0-9])(?:ibb|b)\s*(\d)(?!\d)", n) or re.search(r"(?<![a-z0-9])ibb\s*(" + "|".join(SO_CHU) + r")(?![a-z])", n)
    if m:
        so = int(m.group(1)) if m.group(1).isdigit() else SO_CHU[m.group(1)]
        for x in phongs:
            if x["code"].lower() == f"ibb{so}":
                return x["code"]
    for x in sorted(phongs, key=lambda x: -len(x["ten"])):
        if len(x["ten"]) >= 4 and _bo_dau(x["ten"]) in n:
            return x["code"]
    for x in phongs:
        if len(x["code"]) >= 4 and re.search(rf"(?<![a-z0-9]){re.escape(x['code'].lower())}(?![a-z0-9])", n):
            return x["code"]
    return None


def _ngay_nhac(n: str, nam: int) -> list[tuple[int, date]]:
    """Các ngày dd/mm hoặc "ngày d tháng m" nhắc trong câu (đã bỏ dấu), theo thứ tự xuất hiện."""
    kq = []
    for m in re.finditer(r"(?<!\d)(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?(?!\d)|(?<!\d)(\d{1,2})\s*thang\s*(\d{1,2})(?!\d)", n):
        d, th, y = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(4), m.group(5), None)
        try:
            kq.append((m.start(), date(int(y) + 2000 if y and len(y) == 2 else int(y) if y else nam, int(th), int(d))))
        except ValueError:
            continue
    return kq


def phan_tich(cau: str, ngays: list[str], phongs: list[dict]) -> dict:
    """{phong: mã | None, ngay: yyyy-mm-dd, tu: yyyy-mm-dd | None, ghi_chu}. `ngays`: các ngày có số (tăng dần). Ném ValueError (câu tiếng Việt) nếu yêu cầu không có số liệu."""
    if not ngays:
        raise ValueError("Chưa có số liệu để thuyết trình.")
    moi = date.fromisoformat(ngays[-1])
    n = _bo_dau(cau or "")
    code = tim_phong(cau or "", phongs)
    ten = next((x["ten"] for x in phongs if x["code"] == code), None)
    ds = [d for _, d in _ngay_nhac(n, moi.year)]
    yeu_cau_tu = ds[0] if len(ds) >= 2 else None
    muon = ds[-1] if ds else None
    if muon is None and "hom qua" in n:
        muon = moi - timedelta(days=1)
    thang_nhac = re.search(r"thang\s*(\d{1,2})(?!\d|\s*/)", n)
    if muon is None and thang_nhac and 1 <= int(thang_nhac.group(1)) <= 12:
        mm = int(thang_nhac.group(1))
        nam = moi.year if mm <= moi.month else moi.year - 1
        cuoi = max((d for d in ngays if d.startswith(f"{nam}-{mm:02d}")), default=None)
        if cuoi is None:
            raise ValueError(f"Chưa có số liệu của tháng {mm}/{nam}.")
        muon = date.fromisoformat(cuoi)
    if yeu_cau_tu is None and "dau thang" in n and muon is not None:
        yeu_cau_tu = muon.replace(day=1)
    muon = muon or moi
    ghi = []
    kha_dung = [d for d in ngays if d <= muon.isoformat()]
    if not kha_dung:
        raise ValueError(f"Chưa có số liệu tới ngày {muon:%d/%m/%Y}.")
    den = kha_dung[-1]
    if den != muon.isoformat():
        ghi.append(f"Ngày {muon:%d/%m} chưa có số nên dùng ngày {date.fromisoformat(den):%d/%m}.")
    d_den = date.fromisoformat(den)
    pham_vi = f"phòng {ten}" if ten else "toàn chi nhánh"
    tu_chu = f"01/{d_den:%m/%Y}"
    ghi.insert(0, f"Hiểu yêu cầu: {pham_vi}, luỹ kế từ {tu_chu} đến {d_den:%d/%m/%Y}.")
    if yeu_cau_tu is not None and (yeu_cau_tu.day != 1 or yeu_cau_tu.month != d_den.month):
        ghi.append("App chỉ có số luỹ kế từ ngày 01 của tháng nên ngày bắt đầu bạn nêu được tính từ ngày 01.")
    return {"phong": code, "ngay": den, "tu": f"{d_den:%Y-%m}-01", "ghi_chu": " ".join(ghi)}
