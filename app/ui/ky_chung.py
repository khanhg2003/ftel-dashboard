"""Bộ lọc dùng chung giữa các trang: kỳ báo cáo, chi nhánh, phòng.

Chọn ở trang nào thì sang trang khác vẫn giữ (lưu trong phiên trình duyệt), và được ghi lên đường
dẫn (?tu=2026-09-01&den=2026-09-12&cn=DNG&phong=IBB2) để gửi link là người nhận mở đúng kỳ đó.

Chỉ lựa chọn người dùng tự đổi mới được lưu; chưa đổi gì thì mỗi trang dùng mặc định như cũ.
Mỗi trang tự quy về kiểu kỳ của mình: trang xem luỹ kế đến một ngày lấy "đến ngày", trang xem theo
tháng lấy tháng của "đến ngày". Giá trị trên đường dẫn chỉ là giá trị ban đầu của ô lọc - quyền xem
vẫn kiểm tra ở máy chủ như mọi lựa chọn khác.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from urllib.parse import parse_qs

from dash import Input, Output, State, no_update

KHOA = ("tu", "den", "cn", "phong")
CHI_NHANH = {"all", "DNG", "QNM"}
_NGAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PHONG = re.compile(r"^[A-Za-z0-9_\-]{1,40}$")


def _ngay(v) -> str | None:
    v = str(v or "")[:10]
    if not _NGAY.match(v):
        return None
    try:
        date.fromisoformat(v)
    except ValueError:
        return None
    return v


def lam_sach(d: dict | None) -> dict:
    """Chỉ giữ khoá hợp lệ, đúng định dạng."""
    d = d or {}
    out = {}
    tu, den = _ngay(d.get("tu")), _ngay(d.get("den"))
    if den:
        out["den"] = den
        if tu and tu <= den:
            out["tu"] = tu
    if d.get("cn") in CHI_NHANH:
        out["cn"] = d["cn"]
    if isinstance(d.get("phong"), str) and _PHONG.match(d["phong"]):
        out["phong"] = d["phong"]
    return out


def doc(store: dict | None, search: str | None) -> dict:
    """Bộ lọc ban đầu cho trang: tham số trên đường dẫn ưu tiên hơn lựa chọn đã lưu."""
    q = {k: v[0] for k, v in parse_qs((search or "").lstrip("?")).items() if v}
    tu_url = lam_sach({k: q.get(k) for k in KHOA})
    return {**lam_sach(store), **tu_url}


def ngay_co_so(den: str | None, ngays: list[str]) -> str | None:
    """Ngày có số gần nhất không sau `den` (mặc định: ngày mới nhất)."""
    if not ngays:
        return None
    if not den:
        return ngays[-1]
    truoc = [x for x in ngays if x <= den]
    return truoc[-1] if truoc else ngays[0]


def thang_cua(ky: dict, thangs: list[str]) -> str | None:
    t = (ky.get("den") or "")[:7]
    return t if t in thangs else None


def ghi(app, *inputs: tuple[str, str], chuyen) -> None:
    """Nối các ô lọc của một trang vào bộ lọc chung. `chuyen(*giá_trị)` trả dict phần cần cập nhật."""
    @app.callback(Output("ky-chung", "data", allow_duplicate=True),
                  *[Input(i, p) for i, p in inputs], State("ky-chung", "data"),
                  prevent_initial_call=True)
    def _ghi(*gt):
        *vao, cu = gt
        moi = chuyen(*vao)
        if not moi:
            return no_update
        gop = lam_sach({**(cu or {}), **moi})
        if moi.get("phong") is None and "phong" in moi:
            gop.pop("phong", None)
        return gop if gop != lam_sach(cu) else no_update


def luy_ke(den: str | None) -> dict:
    """Trang xem luỹ kế đến một ngày: kỳ = 01 → ngày đó."""
    den = _ngay(den)
    return {"tu": den[:8] + "01", "den": den} if den else {}


def ca_thang(thang: str | None, ngays: list[str]) -> dict:
    """Trang xem theo tháng: kỳ = 01 → ngày có số cuối cùng của tháng."""
    if not thang:
        return {}
    trong = [x for x in ngays if x[:7] == thang]
    return luy_ke(trong[-1]) if trong else {}


def hai_ky(ky: dict, ngays: list[str]):
    """Kỳ 1, kỳ 2 cho tab So sánh hai kỳ từ bộ lọc chung. None nếu chưa chọn gì."""
    den = ngay_co_so(ky.get("den"), ngays)
    if not ky.get("den") or not den:
        return None
    d2 = date.fromisoformat(den)
    d1 = date.fromisoformat(ky.get("tu") or den[:8] + "01")
    if d1 > d2:
        d1 = d2.replace(day=1)
    if d1.day == 1:                       # luỹ kế tháng -> so với cùng kỳ tháng trước
        cuoi_truoc = d1 - timedelta(days=1)
        k1_tu = cuoi_truoc.replace(day=1)
        k1_den = date(cuoi_truoc.year, cuoi_truoc.month, min(d2.day, cuoi_truoc.day))
    else:                                 # khoảng tự chọn -> so với khoảng liền trước, cùng số ngày
        so_ngay = (d2 - d1).days + 1
        k1_den = d1 - timedelta(days=1)
        k1_tu = k1_den - timedelta(days=so_ngay - 1)
    return k1_tu.isoformat(), k1_den.isoformat(), d1.isoformat(), d2.isoformat()


# Ghi bộ lọc lên đường dẫn, giữ các tham số khác (vd ?tab=). Không tải lại trang.
JS_GHI_DUONG_DAN = """
function(ky, path) {
    const KHONG_GHI = ['/quantri', '/settings', '/upload', '/taikhoan', '/huongdan'];
    try {
        const u = new URL(window.location.href);
        // callback đổi trang (bấm tên phòng) có thể chạy trước khi thanh địa chỉ kịp đổi: lấy đường dẫn từ app
        const doiTrang = path && path !== u.pathname;
        if (doiTrang) { u.pathname = path; u.search = ''; }
        ['tu', 'den', 'cn', 'phong'].forEach(function (k) { u.searchParams.delete(k); });
        if (ky && KHONG_GHI.indexOf(u.pathname) < 0) {
            ['tu', 'den', 'cn', 'phong'].forEach(function (k) {
                if (ky[k] && !(k === 'cn' && ky[k] === 'all')) { u.searchParams.set(k, ky[k]); }
            });
        }
        const moi = u.pathname + (u.searchParams.toString() ? '?' + u.searchParams.toString() : '') + u.hash;
        if (doiTrang) {
            window.history.pushState(window.history.state, '', moi);
        } else if (moi !== window.location.pathname + window.location.search + window.location.hash) {
            window.history.replaceState(window.history.state, '', moi);
        }
    } catch (e) {}
    return window.dash_clientside.no_update;
}
"""
