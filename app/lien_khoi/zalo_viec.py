"""Giao việc liên khối qua Zalo (nhánh thi-lien-khoi): soạn tin, gửi, nhắc quá hạn, báo quản lý, đọc trả lời của người nhận.

Gửi đi đâu do `kenh()` quyết định, mặc định KHÔNG gửi gì ra ngoài:
- chạy minh hoạ (`LIEN_KHOI_NGUON=demo`): chỉ ghi vào hộp thư giả lập (`theo_doi.hop_thu`), không có tin nào rời máy;
- dữ liệu thật: chỉ gửi thật khi có đủ `LIEN_KHOI_ZALO_TOKEN` (bot RIÊNG, không dùng chung bot Bản tin / Tra giá) và `LIEN_KHOI_ZALO_GUI=1`; thiếu thì ghi "chưa cấu hình".
Tin không có tên khách hàng (chỉ mã hợp đồng, luật, lý do, đề xuất).

Tin gửi cho AI (`tin_cho()`): mặc định "quan_ly" - mỗi quản lý (trưởng phòng KD của team, trưởng nhóm / trưởng phòng DVKH, trưởng phòng / điều hành Kỹ thuật) nhận MỘT tin tổng hợp
việc của team mình, tự giao cho cấp dưới và cập nhật TRÊN APP (chọn nhiều việc, giao một lần; không phải trả lời từng mã hợp đồng trên Zalo). Quá hạn thì nhắc quản lý,
quá mốc báo thì báo GIÁM ĐỐC CHI NHÁNH. "nhan_vien" giữ cách cũ: giao thẳng từng người, người nhận trả lời "nhận MÃ", "xong MÃ", "không được MÃ lý do".

Chế độ THỬ ZALO (`kenh()` = "zalo_thu"): dữ liệu vẫn là bộ MINH HOẠ nhưng tin được gửi THẬT tới vài người đại diện (Kinh doanh, DVKH, Kỹ thuật, Ban giám đốc) để cảm nhận tin thật.
Chỉ bật khi đủ cả ba: `LIEN_KHOI_ZALO_TOKEN`, `LIEN_KHOI_ZALO_GUI=1` và file `data/zalo_thu.json` (mã chat của người thử, do `scripts/lien_khoi_zalo_thu.py` ghi).
Chỉ gửi tới mã chat có trong file đó; tin của các quản lý khác chỉ ghi vào hộp thư giả lập; mọi tin ghi rõ là thử nghiệm, không có tên khách hàng thật.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd

from app import zalo_bot
from app.config import BASE_DIR, rules_config
from app.lien_khoi import nguon, theo_doi as td

TOI_DA_KY_TU = 1700                                  # dưới giới hạn tin của Zalo (có chừa chỗ cho phần mở đầu / hướng dẫn)
HUONG_DAN = 'Trả lời: "nhận MÃ", "xong MÃ" hoặc "không được MÃ lý do". Nhiều mã cách nhau bằng dấu cách.'
MA_HD = re.compile(r"\b([A-Za-z]{5}\d{4})\b")
LENH = [("khong_lam_duoc", re.compile(r"\b(khong lam duoc|khong duoc|chua duoc|ket)\b")),
        ("da_xong", re.compile(r"\b(da xong|xong|hoan tat|done)\b")),
        ("da_nhan", re.compile(r"\b(da nhan|nhan|ok)\b"))]
TEN_TT = {"da_nhan": "Đã nhận", "da_xong": "Đã xong", "khong_lam_duoc": "Không làm được"}


def tin_cho() -> str:
    """"quan_ly" (mặc định) hoặc "nhan_vien". Đổi bằng biến môi trường `LIEN_KHOI_TIN_CHO` hoặc `rules.yml` → `lien_khoi.tin_cho`."""
    v = (os.getenv("LIEN_KHOI_TIN_CHO") or str((rules_config().get("lien_khoi") or {}).get("tin_cho", "quan_ly"))).strip().lower()
    return "nhan_vien" if v == "nhan_vien" else "quan_ly"


KHOI_THU = ("KD", "DVKH", "KT", "BGD")
MA_DAI_DIEN_THU = {"KD": "tpkd_01", "DVKH": "tn_dvkh_01", "KT": "dh_kt_01", "BGD": "gd_01"}     # quản lý của bộ minh hoạ mà người thử đóng vai, mỗi khối một người


def duong_dan_thu() -> Path:
    return Path(os.getenv("LIEN_KHOI_ZALO_THU") or Path(BASE_DIR) / "data" / "zalo_thu.json")


def dai_dien_thu() -> dict[str, str]:
    """{khối: mã chat Zalo} của người thử (KD, DVKH, KT, BGD). File thiếu, hỏng hoặc rỗng thì {}."""
    try:
        d = json.loads(duong_dan_thu().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: str(v).strip() for k, v in d.items() if k in KHOI_THU and isinstance(v, (str, int)) and str(v).strip()} if isinstance(d, dict) else {}


def kenh() -> str:
    """"gia_lap" (minh hoạ), "zalo_thu" (minh hoạ nhưng gửi thật tới người thử), "zalo" (dữ liệu thật, gửi thật) hoặc "chua_cau_hinh"."""
    if nguon.la_demo():
        return "zalo_thu" if os.getenv("LIEN_KHOI_ZALO_TOKEN") and os.getenv("LIEN_KHOI_ZALO_GUI") == "1" and dai_dien_thu() else "gia_lap"
    return "zalo" if os.getenv("LIEN_KHOI_ZALO_TOKEN") and os.getenv("LIEN_KHOI_ZALO_GUI") == "1" else "chua_cau_hinh"


def _gui(ma: str, chat_id: str, loai: str, chu: str, now: datetime) -> str:
    """Gửi (hoặc giả lập) MỘT tin và ghi hộp thư. Trả về kết quả: ok | gia_lap | chua_cau_hinh | thieu_chat_id | loi: ..."""
    k = kenh()
    if k == "zalo_thu":
        return _gui_thu(ma, loai, chu, now)
    if k == "zalo" and not chat_id:
        kq = "thieu_chat_id"
    elif k == "zalo":
        try:
            zalo_bot.gui_tin_du_phong(chat_id, chu, token=os.environ["LIEN_KHOI_ZALO_TOKEN"])
            kq = "ok"
        except zalo_bot.LoiZalo as e:
            kq = f"loi: {e}"
    else:
        kq = k
    td.ghi_hop_thu(ma, chat_id, loai, chu, k, kq, now)
    return kq


def _gui_thu(ma: str, loai: str, chu: str, now: datetime) -> str:
    """Chế độ thử: chỉ quản lý được người thử đóng vai (`MA_DAI_DIEN_THU`) mới được gửi THẬT, tới mã chat của người đó; các quản lý khác chỉ ghi hộp thư giả lập."""
    khoi = next((k for k, m in MA_DAI_DIEN_THU.items() if m == ma), "")
    cid = dai_dien_thu().get(khoi, "") if khoi else ""
    if not khoi or not cid:
        kq = "gia_lap"
        td.ghi_hop_thu(ma, "", loai, chu, "gia_lap", kq, now)
        return kq
    ten = ma
    try:
        x = td.nguoi_nhan().fillna("")
        ten = str(x.loc[x["ma"] == ma, "ten"].iloc[0]) if (x["ma"] == ma).any() else ma
    except Exception:
        pass
    dau = f"[THỬ NGHIỆM · dữ liệu minh hoạ] Tin gửi thay cho {ten}\n\n"
    if getattr(chu, "kieu", None):
        from app.ban_tin import _voi_dau                                    # dời vị trí kiểu chữ cho khớp dòng đầu thêm vào
        noi = _voi_dau(dau, chu)
    else:
        noi = dau + chu
    try:
        zalo_bot.gui_tin_du_phong(cid, noi, token=os.environ["LIEN_KHOI_ZALO_TOKEN"])
        kq = "ok"
    except zalo_bot.LoiZalo as e:
        kq = f"loi: {e}"
    td.ghi_hop_thu(ma, cid, loai, noi, "zalo_thu", kq, now)
    return kq


def tra_loi_chat(ma: str, chat_id: str, noi, now: datetime) -> str:
    """Bot trả lời ĐÚNG chat vừa nhắn (không đi qua cơ chế "gửi thay" của chế độ thử), kèm ghi hộp thư. Chạy minh hoạ không có token thì chỉ ghi hộp thư."""
    k = kenh()
    if k in ("zalo_thu", "zalo") and chat_id:
        try:
            zalo_bot.gui_tin_du_phong(chat_id, noi, token=os.environ["LIEN_KHOI_ZALO_TOKEN"])
            kq = "ok"
        except zalo_bot.LoiZalo as e:
            kq = f"loi: {e}"
    else:
        kq = "thieu_chat_id" if k == "zalo" else k
    td.ghi_hop_thu(ma or chat_id, chat_id, "phan_hoi", str(noi), k, kq, now)
    return kq


def _da_giao(kq: str) -> bool:
    """Tin coi là đã tới tay (hoặc đã giả lập) thì mới đánh dấu "đã gửi"; chưa cấu hình / lỗi thì lượt sau gửi lại."""
    return kq in ("ok", "gia_lap")


def thuc(d: pd.DataFrame) -> pd.Series:
    """Phần việc THẬT (không phải lịch sử mô phỏng của bản minh hoạ): chỉ những phần này được gửi, nhắc, báo quản lý hoặc nhận trả lời."""
    return d["mo_phong"].fillna(0) == 0 if "mo_phong" in d.columns else pd.Series(True, index=d.index)


def _ngay(t) -> str:
    return pd.Timestamp(t).strftime("%d/%m %H:%M")


def _dong(i: int, r) -> str:
    goc = f" (việc của hàng chờ {td.VAI_TRO[r['vai_tro']]}: anh/chị phân cho người phù hợp)" if r["nguoi_goc"] else ""
    return f"{i}) {r['so_hd']} · {r['ten_luat']} ({r['muc']})\n   {r['ly_do']}\n   Cần làm ({td.VAI_TRO[r['vai_tro']]}): {r['de_xuat']}{goc}"


def soan_giao(ten: str, rows: list, han_gio: int) -> list[str]:
    """Tin giao việc cho MỘT người; nhiều việc thì tách thành nhiều tin dưới giới hạn của Zalo."""
    dau = f"Chào {ten}. Có {len(rows)} việc cần xử lý trong {han_gio} giờ:"
    khoi, cur = [], dau
    for i, r in enumerate(rows, 1):
        d = _dong(i, r)
        if len(cur) + len(d) + 2 > TOI_DA_KY_TU and cur != dau:
            khoi.append(cur)
            cur = f"(tiếp) {d}"
        else:
            cur += "\n\n" + d
    khoi.append(cur)
    khoi[-1] += "\n\n" + HUONG_DAN
    return khoi


def _theo_nguoi(d: pd.DataFrame) -> dict:
    return {ma: g.to_dict("records") for ma, g in d.groupby("nguoi", sort=False)}


def _chu_nguoi(ds: pd.DataFrame) -> dict:
    return {r["ma"]: r for r in ds.fillna("").to_dict("records")}


TOI_DA_VIEC_CAO = 3


def goc_app() -> str:
    """Gốc địa chỉ app: `LIEN_KHOI_APP_URL`, hoặc `APP_URL`, mặc định bản xem thử trên máy (http://127.0.0.1:8060, chỉ mở được trên chính máy đang chạy)."""
    return (os.getenv("LIEN_KHOI_APP_URL") or os.getenv("APP_URL") or "http://127.0.0.1:8060").strip().rstrip("/")


def lien_ket_app(ma_ql: str = "") -> str:
    """Đường dẫn mở thẳng trang Theo dõi của app với đúng quản lý đã chọn sẵn (`ma_ql` rỗng hoặc "all": xem mọi team)."""
    return f"{goc_app()}/lienkhoi?tab=td&ql={ma_ql or 'all'}"


def lien_ket_excel(ma_ql: str = "", loc: str = "mo") -> str:
    """Đường dẫn tải Excel của đúng quản lý (cần đăng nhập app bằng tài khoản Quản trị)."""
    return f"{goc_app()}/lien-khoi/xuat.xlsx?ql={ma_ql or 'all'}&loc={loc}"


def _ngan(chu: str, n: int = 70) -> str:
    chu = re.sub(r"\s+", " ", str(chu or "")).strip()
    return chu if len(chu) <= n else chu[:n - 1].rstrip() + "…"


def _ly_do_ngan(r: dict, n: int = 70) -> str:
    """Lý do một dòng: lấy ý đầu tiên (trước dấu chấm phẩy), cắt gọn."""
    return _ngan(str(r.get("ly_do") or "").split(";")[0], n)


def _ten(ds: dict, ma: str) -> str:
    return (ds.get(ma, {}).get("ten") or ma) if ma else "(chưa rõ)"


# Kiểu chữ của Zalo (`text_styles`): "b" đậm, "c_<mã màu>" màu, "f_<cỡ>" cỡ chữ (13 nhỏ, 18 lớn). Dựng bằng bộ dựng chung của Bản tin 8h (`ban_tin._Soan`); Zalo từ chối kiểu thì tự gửi lại chữ trơn.
XANH_DUONG, DO, CAM, XAM = "c_0072bc", "c_db342e", "c_f27806", "c_6b7785"
CO_LON, CO_NHO = "f_18", "f_13"


def _soan():
    from app.ban_tin import _Soan                                         # nạp khi cần: bộ dựng này nằm cùng module với Bản tin 8h
    return _Soan()


def _cat_tin(tin, n: int = TOI_DA_KY_TU):
    if len(tin) <= n:
        return tin
    from app.ban_tin import _cat
    return _cat(tin, n)


def soan_tong_hop(ten: str, rows: list, han_gio: int, ds: dict, ma_ql: str = "", them: bool = False) -> list[str]:
    """MỘT tin tổng hợp cho một quản lý, ngắn và có phân cấp để đọc nhanh trên Zalo: tiêu đề lớn, số việc đậm (mức Cao màu đỏ), nhãn nhỏ,
    loại việc và người nhiều việc nhất, 3 việc mức Cao nên giao trước, cuối tin là ĐƯỜNG DẪN mở thẳng danh sách đầy đủ của quản lý đó trên app."""
    cao = [r for r in rows if r["muc"] == "Cao"]
    theo_luat: dict[str, int] = {}
    theo_nguoi: dict[str, int] = {}
    for r in rows:
        theo_luat[r["ten_luat"]] = theo_luat.get(r["ten_luat"], 0) + 1
        k = "Chưa có người phụ trách" if r["nguoi_goc"] else _ten(ds, r["nguoi"])
        theo_nguoi[k] = theo_nguoi.get(k, 0) + 1
    s = _soan().them("VIỆC MỚI PHÁT SINH" if them else "VIỆC CẦN XỬ LÝ HÔM NAY", "b", CO_LON, XANH_DUONG).them(f"\n{ten}", "b")
    s.them(f"\n\n{len(rows)} việc", "b", CO_LON).them("  ·  ").them(f"{len(cao)} mức Cao", "b", CO_LON, DO)
    s.them(f"\ncần có kết quả trong {han_gio} giờ", CO_NHO, XAM)
    s.them("\n\nNHIỀU NHẤT", "b", CO_NHO, XAM).them("\n")
    for i, (t, n) in enumerate(sorted(theo_luat.items(), key=lambda x: -x[1])[:3]):
        s.them(" · " if i else "").them(f"{t} ").them(str(n), "b")
    s.them("\n\nNHIỀU VIỆC NHẤT", "b", CO_NHO, XAM).them("\n")
    for i, (t, n) in enumerate(sorted(theo_nguoi.items(), key=lambda x: -x[1])[:3]):
        s.them(" · " if i else "").them(f"{t} ").them(f"({n})", "b")
    if cao:
        s.them(f"\n\n{min(len(cao), TOI_DA_VIEC_CAO)} VIỆC MỨC CAO NÊN GIAO TRƯỚC", "b", CO_NHO, DO)
        for i, r in enumerate(cao[:TOI_DA_VIEC_CAO], 1):
            s.them(f"\n{i}. ").them(r["so_hd"], "b").them(" – ").them(r["ten_luat"], "b", CAM).them(f"\n    {_ly_do_ngan(r)}", CO_NHO)
        if len(cao) > TOI_DA_VIEC_CAO:
            s.them(f"\n(còn {len(cao) - TOI_DA_VIEC_CAO} việc mức Cao khác)", CO_NHO, XAM)
    s.them(f"\n\n👉 Xem đủ {len(rows)} việc và giao việc:", "b").them(f"\n{lien_ket_app(ma_ql)}", XANH_DUONG)
    s.them("\n\nHoặc nhắn lại bot: ", CO_NHO, XAM)
    for i, lenh in enumerate(("viec", "chia deu", "excel", "menu")):
        s.them(" · " if i else "", CO_NHO, XAM).them(lenh, "b", CO_NHO)
    return [_cat_tin(s.xong())]


def _theo_quan_ly(d: pd.DataFrame, ds: dict) -> dict:
    """Việc gom theo quản lý nhận tin. Nhân viên chưa có quản lý trong danh sách thì về giám đốc chi nhánh (không để việc rơi mất)."""
    gd = td.giam_doc(pd.DataFrame(list(ds.values()), columns=td.COT_NGUOI)) if ds else ""
    kq: dict[str, list] = {}
    for r in d.to_dict("records"):
        kq.setdefault(r.get("quan_ly") or gd or "", []).append(r)
    return kq


def _gui_tong_hop(now: datetime) -> dict:
    d = td.danh_sach(now)
    if d.empty:
        return {"nguoi": 0, "viec": 0, "tin": 0}
    han, _ = td.cau_hinh_gio()
    ds = _chu_nguoi(td.nguoi_nhan())
    da_co = set(d.loc[d["dang_mo"] & d["da_gui_luc"].notna() & thuc(d), "quan_ly"])      # quản lý đã nhận tin tổng hợp trước đó: lần này là đợt việc mới phát sinh
    d = d[d["dang_mo"] & d["da_gui_luc"].isna() & thuc(d)]
    n_ql = n_viec = n_tin = 0
    for ma, rows in _theo_quan_ly(d, ds).items():
        p = ds.get(ma, {"ten": ma or "(chưa có quản lý)", "chat_id": ""})
        kq = [_gui(ma or "(chưa có quản lý)", p.get("chat_id", ""), "giao", chu, now) for chu in soan_tong_hop(p.get("ten") or ma, rows, han, ds, ma, ma in da_co)]
        n_tin += len(kq)
        if all(_da_giao(x) for x in kq):
            td.danh_dau([r["id"] for r in rows], "da_gui_luc", now)
            n_ql, n_viec = n_ql + 1, n_viec + len(rows)
    return {"nguoi": n_ql, "viec": n_viec, "tin": n_tin}


def gui_viec_moi(now: datetime | None = None) -> dict:
    """Gửi các phần việc còn mở mà chưa gửi lần nào: mặc định cho từng QUẢN LÝ một tin tổng hợp, hoặc giao thẳng từng người (`tin_cho()`)."""
    now = now or td.bay_gio()
    if tin_cho() == "quan_ly":
        return _gui_tong_hop(now)
    d = td.danh_sach(now)
    if d.empty:
        return {"nguoi": 0, "viec": 0, "tin": 0}
    han, _ = td.cau_hinh_gio()
    ds = _chu_nguoi(td.nguoi_nhan())
    d = d[d["dang_mo"] & d["da_gui_luc"].isna() & thuc(d)]
    n_nguoi = n_viec = n_tin = 0
    for ma, rows in _theo_nguoi(d).items():
        p = ds.get(ma, {"ten": ma, "chat_id": ""})
        kq = [_gui(ma, p.get("chat_id", ""), "giao", chu, now) for chu in soan_giao(p.get("ten") or ma, rows, han)]
        n_tin += len(kq)
        if all(_da_giao(x) for x in kq):
            td.danh_dau([r["id"] for r in rows], "da_gui_luc", now)
            n_nguoi, n_viec = n_nguoi + 1, n_viec + len(rows)
    return {"nguoi": n_nguoi, "viec": n_viec, "tin": n_tin}


def _tom_tat_viec(rows: list, toi_da: int = 8) -> str:
    rows = list({(r["so_hd"], r["luat"]): r for r in rows}.values())
    dong = [f"- {r['so_hd']} · {r['ten_luat']} ({r['muc']}), giao {_ngay(r['tao_luc'])}" for r in rows[:toi_da]]
    return "\n".join(dong) + (f"\n- ... và {len(rows) - toi_da} việc nữa" if len(rows) > toi_da else "")


def _chay_nhac_quan_ly(now: datetime) -> dict:
    """Quá hạn thì nhắc QUẢN LÝ nhận tin (một lần); quá mốc báo thì gửi giám đốc chi nhánh MỘT tin tổng hợp theo từng quản lý (một lần)."""
    han, ql = td.cau_hinh_gio()
    d = td.danh_sach(now)
    if d.empty:
        return {"nhac": 0, "bao_quan_ly": 0}
    ds = _chu_nguoi(td.nguoi_nhan())
    gd = td.giam_doc(td.nguoi_nhan())
    mo = d[d["dang_mo"] & thuc(d)]
    a = mo[(mo["tao_luc"] + pd.Timedelta(hours=han) <= pd.Timestamp(now)) & mo["nhac_luc"].isna()]
    for ma, rows in _theo_quan_ly(a, ds).items():
        p = ds.get(ma, {"chat_id": ""})
        chua_giao = sum(1 for r in rows if not r.get("giao_cho"))
        hd = list(dict.fromkeys(r["so_hd"] for r in rows))
        t = _soan().them("NHẮC", "b", CO_LON, CAM).them(f"\n{_ten(ds, ma)}", "b")
        t.them(f"\n\nCòn {len(rows)} việc", "b", CO_LON, DO).them(f" quá {han} giờ chưa xong")
        if chua_giao:
            t.them(f"\n{chua_giao} việc chưa giao cho ai", "b", DO)
        t.them("\n\nQUÁ HẠN LÂU NHẤT", "b", CO_NHO, XAM).them(f"\n{', '.join(hd[:3])}{' ...' if len(hd) > 3 else ''}")
        t.them("\n\n👉 Xử lý tại:", "b").them(f"\n{lien_ket_app(ma)}", XANH_DUONG)
        chu = t.xong()
        if _da_giao(_gui(ma or "(chưa có quản lý)", p.get("chat_id", ""), "nhac", chu, now)):
            td.danh_dau([r["id"] for r in rows], "nhac_luc", now)
    b = mo[(mo["tao_luc"] + pd.Timedelta(hours=ql) <= pd.Timestamp(now)) & mo["bao_quan_ly_luc"].isna()]
    n_ql = 0
    if len(b):
        nhom = _theo_quan_ly(b, ds)
        dong = []
        for ma, v in sorted(nhom.items(), key=lambda kv: -len(kv[1])):
            dong.append((_ten(ds, ma), len(v)))
        t = _soan().them("BÁO GIÁM ĐỐC CHI NHÁNH", "b", CO_LON, DO)
        t.them(f"\n\n{len(b)} việc", "b", CO_LON, DO).them(f" quá {ql} giờ chưa xong")
        t.them("\n\nTHEO TỪNG TEAM", "b", CO_NHO, XAM)
        for line_ten, line_n in dong:
            t.them("\n• ").them(line_ten, "b").them(f": {line_n} việc")
        t.them("\n\n👉 Xem chi tiết:", "b").them(f"\n{lien_ket_app('all')}", XANH_DUONG)
        chu = t.xong()
        p = ds.get(gd, {"chat_id": ""})
        kq = _gui(gd, p.get("chat_id", ""), "quan_ly", chu, now) if gd else "khong_co_quan_ly"
        if not gd:
            td.ghi_hop_thu("(chưa có giám đốc)", "", "quan_ly", chu, kenh(), kq, now)
        if _da_giao(kq) or kq == "khong_co_quan_ly":
            td.danh_dau([int(i) for i in b["id"]], "bao_quan_ly_luc", now)
            n_ql = 1
    return {"nhac": len(a), "bao_quan_ly": n_ql, "viec_bao": len(b)}


def chay_nhac(now: datetime | None = None) -> dict:
    """Quá hạn thì nhắc người nhận (một lần), quá mốc báo quản lý thì báo quản lý của họ (một lần). Chế độ quản lý: nhắc quản lý, báo giám đốc chi nhánh."""
    now = now or td.bay_gio()
    if tin_cho() == "quan_ly":
        return _chay_nhac_quan_ly(now)
    han, ql = td.cau_hinh_gio()
    d = td.danh_sach(now)
    if d.empty:
        return {"nhac": 0, "bao_quan_ly": 0}
    ds = _chu_nguoi(td.nguoi_nhan())
    mo = d[d["dang_mo"] & thuc(d)]
    a = mo[(mo["tao_luc"] + pd.Timedelta(hours=han) <= pd.Timestamp(now)) & mo["nhac_luc"].isna()]
    for ma, rows in _theo_nguoi(a).items():
        p = ds.get(ma, {"chat_id": ""})
        chu = f"Nhắc: anh/chị còn {len(rows)} việc quá {han} giờ chưa xong:\n{_tom_tat_viec(rows)}\n\n{HUONG_DAN}"
        if _da_giao(_gui(ma, p.get("chat_id", ""), "nhac", chu, now)):
            td.danh_dau([r["id"] for r in rows], "nhac_luc", now)
    b = mo[(mo["tao_luc"] + pd.Timedelta(hours=ql) <= pd.Timestamp(now)) & mo["bao_quan_ly_luc"].isna()]
    n_ql = 0
    quan_ly: dict[str, list] = {}
    for ma, rows in _theo_nguoi(b).items():
        quan_ly.setdefault(ds.get(ma, {}).get("quan_ly", "") or "", []).extend([{**r, "ten_nguoi": ds.get(ma, {}).get("ten") or ma} for r in rows])
    for ma_ql, rows in quan_ly.items():
        theo_ten: dict[str, list] = {}
        for r in rows:
            theo_ten.setdefault(r["ten_nguoi"], []).append(r)
        chu = f"Báo quản lý: có {len(rows)} việc quá {ql} giờ chưa xong:\n" + "\n".join(f"* {t}: {len(v)} việc ({', '.join(x['so_hd'] for x in v[:4])}{'...' if len(v) > 4 else ''})"
                                                                                for t, v in theo_ten.items())
        p = ds.get(ma_ql, {"chat_id": ""})
        kq = _gui(ma_ql or "(chưa có quản lý)", p.get("chat_id", ""), "quan_ly", chu, now) if ma_ql else "khong_co_quan_ly"
        if not ma_ql:
            td.ghi_hop_thu("(chưa có quản lý)", "", "quan_ly", chu, kenh(), kq, now)
        if _da_giao(kq) or kq == "khong_co_quan_ly":
            td.danh_dau([r["id"] for r in rows], "bao_quan_ly_luc", now)
            n_ql += 1
    return {"nhac": len(a), "bao_quan_ly": n_ql}


# ------------------------------------------------------------------ đọc trả lời
def _bo_dau(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def doc_lenh(chu: str) -> tuple[str | None, list[str], str]:
    """Câu trả lời -> (trạng thái mới hoặc None, các mã hợp đồng, ghi chú / lý do)."""
    ma = [m.upper() for m in MA_HD.findall(chu or "")]
    goc = _bo_dau(MA_HD.sub(" ", chu or ""))
    for tt, mau in LENH:
        m = mau.search(goc)
        if m:
            return tt, list(dict.fromkeys(ma)), re.sub(r"\s+", " ", (goc[:m.start()] + " " + goc[m.end():])).strip() if tt == "khong_lam_duoc" else ""
    return None, list(dict.fromkeys(ma)), ""


def xu_ly_tra_loi(nguoi: str, chu: str, now: datetime | None = None) -> str:
    """Người nhận (mã hoặc mã chat Zalo) trả lời bằng chữ; cập nhật trạng thái và trả về câu phản hồi (cũng được gửi / ghi hộp thư)."""
    now = now or td.bay_gio()
    if tin_cho() == "quan_ly":                                                  # quản lý nhắn lệnh cho bot (xem việc, giao, chia đều, tổng kết, excel...)
        from app.lien_khoi import zalo_lenh
        return zalo_lenh.xu_ly(nguoi, chu, now)
    ds = td.nguoi_nhan().fillna("")
    kt = ds[(ds["ma"] == nguoi) | ((ds["chat_id"] == nguoi) & (ds["chat_id"] != ""))]
    ma = str(kt["ma"].iloc[0]) if len(kt) else ""
    chat_id = str(kt["chat_id"].iloc[0]) if len(kt) else ""
    td.ghi_hop_thu(ma or nguoi, chat_id, "nhan_tu_nguoi", chu or "", kenh(), "da_nhan", now)
    if not ma:
        phan_hoi = "Em chưa biết anh/chị là ai trong danh sách người nhận việc. Anh/chị nhờ quản trị thêm mã chat này vào danh sách."
    else:
        phan_hoi = _ap_dung(ma, chu, now)
    _gui(ma or nguoi, chat_id, "phan_hoi", phan_hoi, now)
    return phan_hoi


# ------------------------------------------------------------------ webhook Zalo (tin trả lời thật)
DUONG_DAN_WEBHOOK = "/api/lien-khoi/zalo-webhook"


def khoa_webhook() -> str:
    """HMAC-SHA256(APP_SECRET_KEY, "lien-khoi-webhook") dạng hex: khác khoá của bot Bản tin / Tra giá, không phải lưu thêm gì."""
    from app.config import SECRET_KEY
    return hmac.new(SECRET_KEY.encode(), b"lien-khoi-webhook", hashlib.sha256).hexdigest()


def khoa_dung(khoa: str | None) -> bool:
    """Đường webhook chỉ mở khi đang cấu hình gửi thật; chưa cấu hình (hoặc chạy minh hoạ) thì luôn từ chối dù đúng khoá."""
    return kenh() == "zalo" and hmac.compare_digest((khoa or "").encode(), khoa_webhook().encode())


def url_webhook() -> str | None:
    goc = (os.environ.get("APP_URL") or "").strip().rstrip("/")
    return f"{goc}{DUONG_DAN_WEBHOOK}" if goc else None


def xu_ly_su_kien(payload) -> None:
    """Zalo gọi vào: chỉ nhận tin CHỮ của người thật trong chat riêng; không bao giờ ném lỗi (webhook phải trả 200 để Zalo khỏi gửi lại)."""
    try:
        from app.zalo_gia import doc_tin
        t = doc_tin(payload)
        if t and not t["la_bot"] and t["loai_chat"] in ("", "PRIVATE"):
            xu_ly_tra_loi(t["chat_id"], t["text"])
    except Exception:
        pass


def _ap_dung(ma: str, chu: str, now: datetime) -> str:
    tt, codes, ghi_chu = doc_lenh(chu)
    if tt is None:
        return "Em chưa hiểu. " + HUONG_DAN
    d = td.danh_sach(now)
    if len(d) and tin_cho() == "quan_ly":
        ds = td.nguoi_nhan().fillna("")
        pv = td.pham_vi(ma, ds)
        mo = d[((d["nguoi"] == ma) | d["quan_ly"].isin(pv)) & d["dang_mo"] & thuc(d)]
    else:
        mo = d[(d["nguoi"] == ma) & d["dang_mo"] & thuc(d)] if len(d) else d
    if not codes:
        hd = list(dict.fromkeys(mo["so_hd"])) if len(mo) else []
        if len(hd) != 1:
            if not hd:
                return "Hiện anh/chị không có việc nào đang mở. Cảm ơn anh/chị."
            return f"Anh/chị đang có {len(hd)} việc mở. Nhớ ghi mã hợp đồng, ví dụ: xong {hd[0]}. " + HUONG_DAN
        codes = hd
    if tt == "khong_lam_duoc" and not ghi_chu:
        return "Anh/chị ghi thêm lý do giúp em, ví dụ: không được " + codes[0] + " khách hẹn tuần sau."
    ket = []
    for c in codes:
        x = mo[mo["so_hd"] == c] if len(mo) else mo
        for gid in (x["id"].tolist() if len(x) else []):
            td.cap_nhat(int(gid), tt, ma, ghi_chu, now)
        ket.append(f"{c}: {TEN_TT[tt]}" + (f" ({len(x)} phần việc)" if len(x) > 1 else "") if len(x) else f"{c}: không thấy việc đang mở của anh/chị")
    return "Đã ghi nhận.\n" + "\n".join(ket)
