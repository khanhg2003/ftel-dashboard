"""Nhớ tạm kết quả đọc database trong vài chục giây.

Một lần mở trang có nhiều callback chạy gần như cùng lúc và hỏi database cùng một câu (danh sách ngày có số, hợp
đồng online của tháng, chi tiêu ads theo ngày...). Nhớ tạm kết quả thì chỉ hỏi một lần. Số không bị cũ lâu:
- mỗi kết quả chỉ giữ `giay` giây (mặc định 20);
- nạp / gỡ file, sửa cấu hình ads... gọi `xoa(nhom)` để bỏ ngay phần liên quan trong máy chủ đó.
Kết quả trả ra là bản sao (DataFrame / list / dict) nên nơi gọi sửa thoải mái không ảnh hưởng lần gọi sau.
"""
from __future__ import annotations

import functools
import threading
import time

import pandas as pd

_kho: dict = {}
_khoa = threading.Lock()
TOI_DA = 256


def _khoa_tham_so(v):
    if isinstance(v, (list, set)):
        return tuple(sorted(v, key=str)) if isinstance(v, set) else tuple(v)
    if isinstance(v, dict):
        return tuple(sorted((k, _khoa_tham_so(x)) for k, x in v.items()))
    return v


def _sao(v):
    if isinstance(v, (pd.DataFrame, pd.Series)):
        return v.copy()
    if isinstance(v, list):
        return list(v)
    if isinstance(v, dict):
        return dict(v)
    return v


def nho(nhom: str, giay: float = 20):
    """Trang trí hàm đọc số: cùng tham số trong `giay` giây thì trả lại kết quả đã có."""
    def boc(ham):
        @functools.wraps(ham)
        def f(*args, **kw):
            k = (nhom, ham.__module__, ham.__qualname__, tuple(_khoa_tham_so(a) for a in args),
                 tuple(sorted((a, _khoa_tham_so(b)) for a, b in kw.items())))
            try:
                hash(k)
            except TypeError:
                return ham(*args, **kw)
            bay_gio = time.monotonic()
            with _khoa:
                co = _kho.get(k)
            if co is not None and bay_gio - co[0] < giay:
                return _sao(co[1])
            kq = ham(*args, **kw)
            with _khoa:
                if len(_kho) >= TOI_DA:
                    _kho.clear()
                _kho[k] = (bay_gio, kq)
            return _sao(kq)
        f.goc = ham
        return f
    return boc


def xoa(nhom: str | None = None) -> None:
    """Bỏ kết quả đã nhớ của một nhóm (None = tất cả)."""
    with _khoa:
        if nhom is None:
            _kho.clear()
        else:
            for k in [k for k in _kho if k[0] == nhom]:
                del _kho[k]


def ghi(nhom: str):
    """Trang trí hàm GHI dữ liệu: chạy xong thì bỏ kết quả đã nhớ của nhóm (kể cả khi hàm báo lỗi giữa chừng)."""
    def boc(ham):
        @functools.wraps(ham)
        def f(*args, **kw):
            try:
                return ham(*args, **kw)
            finally:
                xoa(nhom)
        return f
    return boc
