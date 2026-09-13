"""Chuẩn hoá dữ liệu đầu vào.

Bài học từ file thật:
- 45 tên cột trong file đang ở Unicode dạng tổ hợp (NFD): "CN Bán" nhìn giống nhưng
  so chuỗi KHÔNG bằng "CN Bán". Bắt buộc chuẩn hoá NFC trước khi so tên cột.
- Acc nhân viên có lệch hoa/thường (TIN.Minhlh1 vs TIN.MinhLH1) -> so sánh bằng acc_norm.
- Mã NV có số 0 ở đầu trong file HR (00036393) nhưng không có trong file bán (36393).
- Cột tiền lẫn nhiều định dạng: 1,063,636 / 158,01 / 300.000.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime

_WS = re.compile(r"\s+")
_RE_MA = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{4,}$")
_RE_ACC = re.compile(r"^[A-Za-z]{2,6}(\.[A-Za-z0-9]+)+$")
_RE_PHONE = re.compile(r"^0?\d{8,11}$")
_RE_MANV = re.compile(r"^\d{1,10}$")

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%m/%d/%Y",
                 "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M")


def nfc(value) -> str:
    """Chuẩn hoá Unicode + bỏ ký tự trắng lạ."""
    if value is None:
        return ""
    s = str(value)
    s = s.replace(" ", " ").replace("﻿", "")
    return unicodedata.normalize("NFC", s)


def norm_header(value) -> str:
    """Tên cột -> dạng so khớp: NFC, gộp khoảng trắng, bỏ đầu/cuối, chữ thường."""
    return _WS.sub(" ", nfc(value)).strip().lower()


def norm_text(value) -> str:
    return _WS.sub(" ", nfc(value)).strip()


def norm_acc(value) -> str:
    """Acc inside -> khoá so khớp (không phân biệt hoa/thường)."""
    return norm_text(value).lower()


def norm_manv(value) -> str:
    """Mã NV -> chuỗi số, bỏ số 0 ở đầu. '00036393' và '36393' cho cùng kết quả."""
    s = re.sub(r"[^0-9]", "", norm_text(value))
    s = s.lstrip("0")
    return s


def parse_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = norm_text(value)
    if not s or s.startswith("#"):
        return None
    s = s.split(" ")[0] if len(s) > 10 and " " in s else s
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_number(value):
    """Đọc số với các định dạng lẫn lộn: 1,063,636 | 158,01 | 300.000 | 1.234,56."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    s = norm_text(value).replace(" ", "")
    if not s or s.startswith("#"):
        return None
    neg = s.startswith("-")
    s = s.lstrip("+-")
    s = s.replace("%", "")
    if not re.fullmatch(r"[0-9.,]+", s):
        return None
    if "," in s and "." in s:                       # dấu xuất hiện sau cùng là thập phân
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        thou = "." if dec == "," else ","
        s = s.replace(thou, "").replace(dec, ".")
    elif "," in s or "." in s:
        sep = "," if "," in s else "."
        parts = s.split(sep)
        if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]) and len(parts[0]) <= 3:
            s = "".join(parts)                      # ngăn cách hàng nghìn
        else:
            s = parts[0] + "." + "".join(parts[1:])  # dấu thập phân
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


# ----------------------------------------------------------- kiểm tra kiểu ô
def _ok_empty(s: str) -> bool:
    return s == "" or s.startswith("#")


def check_ma(v) -> bool:
    s = norm_text(v)
    return _ok_empty(s) or bool(_RE_MA.match(s))


def check_acc(v) -> bool:
    s = norm_text(v)
    return _ok_empty(s) or bool(_RE_ACC.match(s)) or bool(_RE_PHONE.match(s))


def check_manv(v) -> bool:
    s = norm_text(v)
    return _ok_empty(s) or bool(_RE_MANV.match(s))


def check_ngay(v) -> bool:
    s = norm_text(v)
    return _ok_empty(s) or parse_date(v) is not None


def check_so(v) -> bool:
    s = norm_text(v)
    return _ok_empty(s) or parse_number(v) is not None


def check_str(v) -> bool:
    return True


CHECKERS = {"ma": check_ma, "acc": check_acc, "manv": check_manv, "ngay": check_ngay,
            "so": check_so, "str": check_str, "pii": check_str}

CONVERTERS = {"ngay": parse_date, "so": parse_number, "manv": norm_manv,
              "ma": norm_text, "acc": norm_text, "str": norm_text, "pii": norm_text}
