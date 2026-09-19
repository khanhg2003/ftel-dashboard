"""Kiểm thử bộ nhớ tạm kết quả đọc database (app/bo_nho.py)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import bo_nho                                                # noqa: E402


def test_nho_tra_ban_sao_va_xoa_theo_nhom():
    dem = {"n": 0}

    @bo_nho.nho("kt", 60)
    def doc(tu, ds=None):
        dem["n"] += 1
        return pd.DataFrame({"a": [1, 2]})

    a = doc("x", ["P1"])
    a["a"] = 99                                              # sửa bản trả ra không ảnh hưởng lần sau
    b = doc("x", ["P1"])
    assert dem["n"] == 1 and b.a.tolist() == [1, 2]
    doc("y", ["P1"])
    assert dem["n"] == 2                                     # tham số khác -> đọc lại

    @bo_nho.ghi("kt")
    def viet():
        return "ok"
    viet()
    doc("x", ["P1"])
    assert dem["n"] == 3                                     # ghi xong -> bỏ nhớ nhóm


def test_het_han_thi_doc_lai(monkeypatch):
    dem = {"n": 0}
    gio = {"t": 1000.0}
    monkeypatch.setattr(bo_nho.time, "monotonic", lambda: gio["t"])

    @bo_nho.nho("kt2", 20)
    def doc():
        dem["n"] += 1
        return [dem["n"]]
    doc()
    gio["t"] += 19
    doc()
    gio["t"] += 2
    assert doc() == [2] and dem["n"] == 2
