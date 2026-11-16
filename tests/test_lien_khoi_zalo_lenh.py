"""Bot Zalo hai chiều cho quản lý, giao theo mã / chia đều, xuất Excel, tổng kết (nhánh thi-lien-khoi)."""
from __future__ import annotations

import io
import json
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from openpyxl import load_workbook

from app import zalo_bot
from app.lien_khoi import dieu_phoi as dp, luat, theo_doi as td, xuat, zalo_lenh as zl, zalo_viec as zv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_lien_khoi_quan_ly import NGUOI, T0, _viec, ql, thu_zalo, _dat  # noqa: E402,F401


def _tai(*dong) -> None:
    td.dong_bo(_viec(*dong), T0)


def _thu(d: pd.DataFrame, **loc) -> pd.DataFrame:
    for k, v in loc.items():
        d = d[d[k] == v]
    return d


def test_lenh_menu_viec_qua_han_chi_tiet_va_khong_lo_tin_cua_quan_ly_khac(ql):
    _tai(dict(so_hd="MHAAA0001"), dict(so_hd="MHAAA0002", luat="loi_som", ten_luat="Lỗi sớm", muc="Trung bình"))
    menu = zl.xu_ly("tpkd_01", "menu", T0)
    assert "giao MÃ" in menu and "chia deu" in menu and "excel" in menu
    viec = zl.xu_ly("tpkd_01", "Việc", T0)                                       # có dấu, hoa thường đều được
    assert "MHAAA0001" in viec and "2 việc" in viec and "Cao" in viec and "http" in viec
    assert "Không có việc" in zl.xu_ly("tpkd_01", "qua han", T0 + timedelta(hours=1))            # chưa quá hạn
    qh = zl.xu_ly("tpkd_01", "quá hạn", T0 + timedelta(hours=30))
    assert "VIỆC QUÁ HẠN" in qh and "MHAAA0001" in qh and "quá" in qh
    ct = zl.xu_ly("tpkd_01", "chi tiet mhaaa0001", T0)
    assert "Sự cố lặp" in ct and "Sale 01" in ct and "Kỹ thuật ghi checklist lặp" in ct
    assert "Không thấy" in zl.xu_ly("tpkd_02", "MHAAA0001", T0)                  # team khác không xem được việc của team này
    assert "chưa hiểu" in zl.xu_ly("tpkd_01", "bla bla", T0)
    assert "chưa biết anh/chị là ai" in zl.xu_ly("khong_ai", "menu", T0)
    assert "gửi việc cho quản lý" in zl.xu_ly("sale_01", "viec", T0)             # nhân viên không phải quản lý


def test_giao_theo_ma_chi_giao_phan_viec_dung_khoi_va_hoi_lai_khi_trung_ten(ql):
    _tai(dict(so_hd="MHAAA0001"))
    r = zl.xu_ly("tpkd_01", "giao MHAAA0001 cho Sale 01", T0 + timedelta(hours=1))
    assert "Đã giao 1 phần việc" in r and "Sale 01" in r
    d = td.danh_sach(T0)
    s = _thu(d, so_hd="MHAAA0001", vai_tro="sale").iloc[0]
    assert s["giao_cho"] == "sale_01" and s["trang_thai"] == "da_nhan"
    assert _thu(d, so_hd="MHAAA0001", vai_tro="dvkh").iloc[0]["trang_thai"] == "moi"            # phần của DVKH không bị đụng
    assert "không thấy" in zl.xu_ly("tpkd_01", "giao MHAAA0001 cho Người Lạ", T0)
    assert "nhắn đủ mã" in zl.xu_ly("tpkd_01", "giao cho Sale 01", T0).lower()
    gd = zl.xu_ly("gd_01", "giao MHAAA0001 cho KTV 01", T0)                      # giám đốc thấy hết, chỉ giao phần Kỹ thuật cho kỹ thuật viên
    assert "Đã giao 1 phần việc" in gd and _thu(td.danh_sach(T0), so_hd="MHAAA0001", vai_tro="dvkh").iloc[0]["trang_thai"] == "moi"


def test_ten_nguoi_trung_thi_bot_liet_ke_de_hoi_lai(ql, monkeypatch):
    them = pd.DataFrame([dict(ma="sale_03", ten="Sale 03", khoi="KD", vai_tro="nhan_vien", quan_ly="tpkd_01", chat_id="")])
    monkeypatch.setattr(td, "nguoi_nhan", lambda: pd.concat([NGUOI, them], ignore_index=True))
    _tai(dict(so_hd="MHAAA0001"))
    r = zl.xu_ly("tpkd_01", "giao MHAAA0001 cho sale", T0)
    assert "2 người khớp" in r and "sale_01" in r and "sale_03" in r
    assert td.danh_sach(T0)["giao_cho"].isna().all()                           # chưa giao khi chưa rõ người


def test_chia_deu_viec_hang_cho_theo_tai_va_dung_khoi(ql, monkeypatch):
    them = pd.DataFrame([dict(ma="cskh_02", ten="CSKH 02", khoi="DVKH", vai_tro="nhan_vien", quan_ly="tn_dvkh_01", chat_id="")])
    monkeypatch.setattr(td, "nguoi_nhan", lambda: pd.concat([NGUOI, them], ignore_index=True))
    _tai(*[dict(so_hd=f"MHAAA000{i}", giao_sale="", giao_kt="", giao_dvkh=luat.GIAO_DVKH) for i in range(1, 6)])
    r = zl.xu_ly("tp_dvkh_01", "chia đều", T0 + timedelta(hours=1))
    assert "Đã chia đều 5 phần việc" in r
    d = _thu(td.danh_sach(T0), vai_tro="dvkh")
    dem = d["giao_cho"].value_counts().to_dict()
    assert dem == {"cskh_01": 3, "cskh_02": 2} or dem == {"cskh_02": 3, "cskh_01": 2}
    assert (d["trang_thai"] == "da_nhan").all()
    assert "Không còn việc hàng chờ" in zl.xu_ly("tp_dvkh_01", "chia deu", T0)  # chạy lại không giao đôi
    assert dp.chia_deu("tp_dvkh_01", T0)["giao"] == 0


def test_chia_deu_ca_viec_phan_bo_tuong_doi_khi_da_co_viec(ql, monkeypatch):
    them = pd.DataFrame([dict(ma="cskh_02", ten="CSKH 02", khoi="DVKH", vai_tro="nhan_vien", quan_ly="tn_dvkh_01", chat_id="")])
    monkeypatch.setattr(td, "nguoi_nhan", lambda: pd.concat([NGUOI, them], ignore_index=True))
    _tai(dict(so_hd="MHAAA0001"), *[dict(so_hd=f"MHAAA010{i}", giao_sale="", giao_kt="", giao_dvkh=luat.GIAO_DVKH) for i in range(3)])      # cskh_01 đã có 1 việc riêng
    r = dp.chia_deu("tp_dvkh_01", T0)
    assert r["theo_nguoi"] == {"CSKH 02": 2, "CSKH 01": 1}                      # cuối cùng mỗi người 2 việc


def test_xong_va_khong_duoc_van_chay_qua_lenh_cu(ql):
    _tai(dict(so_hd="MHAAA0001"))
    assert "Đã ghi nhận" in zl.xu_ly("tpkd_01", "xong MHAAA0001", T0 + timedelta(hours=1))
    assert _thu(td.danh_sach(T0), so_hd="MHAAA0001", vai_tro="sale").iloc[0]["trang_thai"] == "da_xong"
    assert "lý do" in zl.xu_ly("tn_dvkh_01", "không được MHAAA0001", T0)


def test_tong_ket_va_link_excel(ql):
    _tai(dict(so_hd="MHAAA0001"), dict(so_hd="MHAAA0002"))
    zl.xu_ly("tpkd_01", "xong MHAAA0001", T0 + timedelta(hours=2))
    tk = zl.xu_ly("gd_01", "tổng kết", T0 + timedelta(hours=3))
    assert "TỔNG KẾT HÔM NAY" in tk and "THEO TỪNG TEAM" in tk and "TPKD team 1" in tk
    t = dp.tong_ket("gd_01", T0 + timedelta(hours=3))
    assert t["xong_24h"] == 1 and t["mo"] == 5 and t["chua_giao"] == 5
    link = zl.xu_ly("tpkd_01", "excel", T0)
    assert "/lien-khoi/xuat.xlsx?ql=tpkd_01" in link


def test_chat_dang_ky_thu_nhan_vai_doi_vai_va_tra_loi_dung_chat_khong_kem_gui_thay(thu_zalo, monkeypatch):
    f, gui = thu_zalo
    f.write_text(json.dumps({"KD": "chat-a", "DVKH": "chat-a", "KT": "chat-a", "BGD": "chat-a"}), encoding="utf-8")
    _dat(monkeypatch)
    _tai(dict(so_hd="MHAAA0001"))
    r = zl.xu_ly("chat-a", "menu", T0)                                          # một chat đóng 4 vai: mặc định vai Ban giám đốc
    assert "Đang dùng vai BGD" in r
    assert gui and gui[-1][0] == "chat-a" and "Tin gửi thay" not in str(gui[-1][1])
    assert "Đã chuyển sang vai KD" in zl.xu_ly("chat-a", "vai KD", T0)
    assert zl.nhan_dien("chat-a")[0] == "tpkd_01"
    assert "MHAAA0001" in zl.xu_ly("chat-a", "viec", T0)
    assert "Lệnh vai chỉ dùng" in zl.xu_ly("tpkd_01", "vai KD", T0)


def test_chat_chua_dang_ky_khong_duoc_xem_gi(thu_zalo, monkeypatch):
    f, gui = thu_zalo
    f.write_text(json.dumps({"KD": "chat-a"}), encoding="utf-8")
    _dat(monkeypatch)
    _tai(dict(so_hd="MHAAA0001"))
    assert "chưa biết anh/chị là ai" in zl.xu_ly("chat-la", "viec", T0)
    assert "MHAAA0001" not in " ".join(str(g[1]) for g in gui if g[0] == "chat-la")


def test_tin_tong_hop_dot_bo_sung_ghi_viec_moi_phat_sinh_va_co_dong_nhac_lenh(ql):
    _tai(dict(so_hd="MHAAA0001"))
    zv.gui_viec_moi(T0)
    td.dong_bo(_viec(dict(so_hd="MHAAA0001"), dict(so_hd="MHAAA0009")), T0 + timedelta(hours=1))
    zv.gui_viec_moi(T0 + timedelta(hours=1))
    nd = [r for r in td.hop_thu().to_dict("records") if r["loai"] == "giao" and r["den_nguoi"] == "tpkd_01"]
    assert len(nd) == 2
    moi, dau = nd[0]["noi_dung"], nd[1]["noi_dung"]
    assert "VIỆC MỚI PHÁT SINH" in moi and "VIỆC CẦN XỬ LÝ HÔM NAY" in dau and "chia deu" in moi


def test_gui_tong_ket_moi_quan_ly_mot_tin_moi_ngay(ql):
    _tai(dict(so_hd="MHAAA0001"))
    n = zl.gui_tong_ket(T0)["tin"]
    assert n >= 3 and zl.gui_tong_ket(T0)["tin"] == 0                           # cùng ngày thì không gửi lại
    assert zl.gui_tong_ket(T0 + timedelta(hours=26))["tin"] >= 3                # sang ngày mới thì gửi tiếp


def test_nguoi_nghe_xu_ly_tin_chu_cua_nguoi_that_bo_qua_bot_va_nhom(ql):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import lien_khoi_zalo_nghe as ng
    sk = lambda text, bot=False, kieu="PRIVATE": {"event_name": "message.text.received", "message": {"chat": {"id": "tpkd_01", "chat_type": kieu}, "from": {"id": "u", "is_bot": bot}, "text": text, "message_id": "m"}}
    assert "'menu'" in ng.xu_ly_mot(sk("menu"))
    assert ng.xu_ly_mot(sk("menu", bot=True)) is None and ng.xu_ly_mot(sk("menu", kieu="GROUP")) is None and ng.xu_ly_mot({"event_name": "x"}) is None


# ------------------------------------------------------------------ Excel
def test_xuat_excel_co_sheet_tong_hop_va_sheet_tung_nhan_vien_khong_ten_khach(ql):
    _tai(dict(so_hd="MHAAA0001"), dict(so_hd="MHAAA0002", muc="Trung bình"))
    zl.xu_ly("tpkd_01", "giao MHAAA0001 cho Sale 01", T0 + timedelta(hours=1))
    wb = load_workbook(io.BytesIO(xuat.xuat_excel("gd_01", "mo", T0 + timedelta(hours=2))))
    assert wb.sheetnames[:2] == ["Tất cả việc", "Theo nhân viên"] and "Sale 01" in wb.sheetnames
    ws = wb["Tất cả việc"]
    dau = [c.value for c in ws[1]]
    assert dau[:3] == ["Mã hợp đồng", "Loại việc", "Mức"] and ws.freeze_panes == "A2" and ws.auto_filter.ref
    assert ws.max_row == 1 + 6                                                  # 2 hợp đồng x 3 vai trò
    sheet_nv = wb["Sale 01"]
    assert sheet_nv.max_row == 3 and sheet_nv["A2"].value == "MHAAA0001" and sheet_nv["E2"].value == "Sale 01"
    tat = " ".join(str(c.value) for row in ws.iter_rows() for c in row if c.value is not None)
    assert "Kỹ thuật ghi checklist lặp" in tat and "sale_01" not in tat       # tên người, không phải mã nội bộ
    tong = wb["Theo nhân viên"]
    assert [c.value for c in tong[1]][:3] == ["Người phụ trách", "Tổng việc", "Đang mở"]


def test_xuat_excel_theo_pham_vi_quan_ly_va_bo_loc_va_tat_ca_khong_loi_khi_rong(ql):
    _tai(dict(so_hd="MHAAA0001"))
    ws = load_workbook(io.BytesIO(xuat.xuat_excel("tpkd_01", "mo", T0)))["Tất cả việc"]
    assert ws.max_row == 2 and ws["E2"].value == "Sale 01"                      # chỉ việc của team tpkd_01
    rong = load_workbook(io.BytesIO(xuat.xuat_excel("tpkd_02", "mo", T0)))
    assert rong["Tất cả việc"].max_row == 1                                     # không có việc: vẫn ra file có tiêu đề
    assert load_workbook(io.BytesIO(xuat.xuat_excel("all", "da_xong", T0)))["Tất cả việc"].max_row == 1
    assert xuat.ten_file("tpkd_01", T0).startswith("ViecLienKhoi_tpkdteam1_") and xuat.ten_file("all", T0).startswith("ViecLienKhoi_ToanChiNhanh_")


def test_ten_sheet_khong_trung_khong_ky_tu_cam_va_toi_da_31():
    da = set()
    a, b = xuat._ten_sheet("Nguyễn/Văn:A?", da), xuat._ten_sheet("Nguyễn/Văn:A?", da)
    assert a != b and len(a) <= 31 and len(b) <= 31 and not any(c in a + b for c in "/:?[]*\\")


def test_duong_xuat_excel_can_quyen_quan_tri(ql, monkeypatch):
    from flask import Flask
    from app.api_lien_khoi import bp
    _tai(dict(so_hd="MHAAA0001"))
    app = Flask(__name__)
    app.register_blueprint(bp)
    c = app.test_client()
    monkeypatch.setattr("flask_login.current_user", SimpleNamespace(duoc_cau_hinh=False))
    assert c.get("/lien-khoi/xuat.xlsx").status_code == 403
    monkeypatch.setattr("flask_login.current_user", SimpleNamespace(duoc_cau_hinh=True))
    r = c.get("/lien-khoi/xuat.xlsx?ql=tpkd_01&loc=mo")
    assert r.status_code == 200 and "spreadsheetml" in r.mimetype and ".xlsx" in r.headers["Content-Disposition"]
    assert load_workbook(io.BytesIO(r.data)).sheetnames[0] == "Tất cả việc"


def test_zalo_bot_khong_gui_that_o_che_do_minh_hoa_khi_tra_loi(ql, monkeypatch):
    monkeypatch.setattr(zalo_bot, "gui_tin", lambda *a, **k: (_ for _ in ()).throw(AssertionError("không được gửi")))
    _tai(dict(so_hd="MHAAA0001"))
    zl.xu_ly("tpkd_01", "viec", T0)
    h = td.hop_thu().to_dict("records")
    assert any(r["loai"] == "phan_hoi" and r["kenh"] == "gia_lap" for r in h) and any(r["loai"] == "nhan_tu_nguoi" for r in h)
