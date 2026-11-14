"""Hướng liên khối với khối Kỹ thuật và bộ dữ liệu minh hoạ (nhánh thi-lien-khoi): bộ đọc file Kỹ thuật, luật dùng sự kiện Kỹ thuật,
chọn nguồn (mặc định LUÔN là dữ liệu thật) và các chốt chặn riêng tư của bộ minh hoạ."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pytest

from app.lien_khoi import doc_kt, luat, nguon, su_kien as sk

T = pd.Timestamp
NGAY_TC = T("2026-09-12")
DEMO = Path(__file__).resolve().parents[1] / "demo" / "lien_khoi"


def _kd(*dong) -> pd.DataFrame:
    mac = dict(so_hd="DAAAA0001", ngay_tao=T("2026-09-07"), ngay_online=pd.NaT, ngay_huy=pd.NaT, sale="DNG.A", phong="IBB7", goi="Sky",
               tinh_trang="Bình thường", ton=True)
    return pd.DataFrame([{**mac, **d} for d in dong])


def _bd(*dong) -> pd.DataFrame:
    mac = dict(so_hd="DAAAA0001", tg_yc=T("2026-10-07 09:00"), loai_yc="Thắc mắc", tinh_trang="Đang xử lý", ket_qua_tu_van=None, nhan_su_au="cskh1",
               net_hien="Đang hoạt động")
    return pd.DataFrame([{**mac, **d} for d in dong])


def _kt(*dong) -> pd.DataFrame:
    mac = dict(so_hd="DAAAA0001", loai="checklist", thoi_diem=T("2026-11-03 10:00"), chi_tiet="x", nguoi="ktv1", so_lan=2)
    return pd.DataFrame([{**mac, **d} for d in dong], columns=nguon.COT_KT)


# ------------------------------------------------------------------ luật dùng sự kiện Kỹ thuật
def test_cho_online_giao_dung_ktv_va_ghi_tinh_trang_ton_ky_thuat():
    kd = _kd(dict(so_hd="DAAAA0001"), dict(so_hd="DAAAA0002"))
    kt = _kt(dict(so_hd="DAAAA0001", loai="ton_kt", chi_tiet="Tồn Kỹ thuật: Đã phân công - Triển khai mới", nguoi="ktv9"))
    v = luat.luat_cho_online(kd, NGAY_TC, kt=kt).set_index("so_hd")
    assert v.loc["DAAAA0001", "giao_kt"] == "ktv9" and "Đã phân công" in v.loc["DAAAA0001", "ly_do"]
    assert v.loc["DAAAA0002", "giao_kt"] == luat.GIAO_KT        # Kỹ thuật chưa biết hợp đồng này: hàng chờ


def test_loi_som_tinh_ca_checklist_sau_trien_khai_va_hai_khoi_cung_ghi_nhan_la_cao():
    kd = _kd(dict(so_hd="DAAAA0001", ngay_online=T("2026-10-20")), dict(so_hd="DAAAA0002", ngay_online=T("2026-10-20")))
    kt = _kt(dict(so_hd="DAAAA0001", loai="checklist_sau_tk", thoi_diem=T("2026-10-25"), nguoi="ktv7"),
             dict(so_hd="DAAAA0002", loai="checklist_sau_tk", thoi_diem=T("2026-10-25"), nguoi="ktv8"))
    bd = _bd(dict(so_hd="DAAAA0002", loai_yc="Khiếu nại, phàn nàn", tg_yc=T("2026-10-26 09:00")))
    v = luat.luat_loi_som(kd, bd, kt=kt).set_index("so_hd")
    assert v.loc["DAAAA0001", "muc"] == luat.TB and "checklist sau triển khai" in v.loc["DAAAA0001", "ly_do"]
    assert v.loc["DAAAA0001", "giao_kt"] == "ktv7"
    assert v.loc["DAAAA0002", "muc"] == luat.CAO               # Kỹ thuật và DVKH cùng ghi nhận


def test_su_co_lap_tu_2_lan_trung_binh_tu_3_lan_hoac_co_sr_khieu_nai_la_cao():
    kd = _kd(dict(so_hd="DAAAA0001"), dict(so_hd="DAAAA0002"), dict(so_hd="DAAAA0003"), dict(so_hd="DAAAA0004"),
             dict(so_hd="DAAAA0005", tinh_trang="Đã chấm dứt hợp đồng"))
    kt = _kt(dict(so_hd="DAAAA0001", so_lan=2), dict(so_hd="DAAAA0002", so_lan=3), dict(so_hd="DAAAA0003", so_lan=2),
             dict(so_hd="DAAAA0004", so_lan=1), dict(so_hd="DAAAA0005", so_lan=3), dict(so_hd="DAAAA0006", so_lan=2, loai="cap_lan"))
    bd = _bd(dict(so_hd="DAAAA0003", loai_yc="Khiếu nại, phàn nàn"))
    v = luat.luat_su_co_lap(kd, kt, bd, dvkh={"DAAAA0001": "cskh1"}).set_index("so_hd")
    assert set(v.index) == {"DAAAA0001", "DAAAA0002", "DAAAA0003"}      # 1 lần: chưa lặp; đã chấm dứt: bỏ; loại khác (cáp LAN): không tính
    assert v.loc["DAAAA0001", "muc"] == luat.TB and v.loc["DAAAA0002", "muc"] == luat.CAO and v.loc["DAAAA0003", "muc"] == luat.CAO
    assert v.loc["DAAAA0001", "giao_dvkh"] == "cskh1" and v.loc["DAAAA0002", "giao_dvkh"] == luat.GIAO_DVKH
    assert v.loc["DAAAA0001", "giao_kt"] == "ktv1" and "khiếu nại" in v.loc["DAAAA0003", "ly_do"]
    assert "từ xa" in v.loc["DAAAA0001", "de_xuat"]                    # DVKH gọi trước, Kỹ thuật chỉ đến nhà khi cần


# ------------------------------------------------------------------ bộ đọc file Kỹ thuật
def test_nhan_ra_loai_file_ky_thuat_theo_ten_cot():
    assert doc_kt.loai_file(["STT", "Số HĐ", "TG tạo PTC", "Sale HĐ"]) == "ton"
    assert doc_kt.loai_file(["Số hợp đồng", "Số lần hẹn"]) == "trien_khai"
    assert doc_kt.loai_file(["Số HĐ", "Số lần lặp"]) == "checklist"
    assert doc_kt.loai_file(["Hợp đồng", "Ngày checklist"]) == "checklist_sau_tk"
    assert doc_kt.loai_file(["HĐ", "Ngày active"]) == "cap_lan"
    assert doc_kt.loai_file(["Vùng", "Đối tác", "Block", "Lô"]) is None        # file KPI theo block: không có mã hợp đồng


def test_doc_file_ky_thuat_khong_lay_ten_khach_va_hieu_dung_ngay_thang():
    ton = pd.DataFrame([{"Số HĐ": "ktaab6951", "Tên KH": "Nguoi Khach", "Tình trạng": "Đã nhận ca", "Loại triển khai": "Triển khai mới",
                         "TG tạo PTC": "07-11-2026 10:13:51", "Nhân sự": "KTMPN.A", "Gói dịch vụ": "Sky", "Sale HĐ": "dng.b"}])
    e = doc_kt.su_kien_tu_bang(ton)
    assert e["so_hd"].iloc[0] == "KTAAB6951" and e["thoi_diem"].iloc[0] == T("2026-11-07 10:13:51")
    assert "Nguoi Khach" not in " ".join(map(str, e.to_numpy().ravel()))                # tên khách không bao giờ đi vào sự kiện
    lan = pd.DataFrame([{"HĐ": "KTAAB6868", "Ngày active": "11/02/2026 17:26:47", "Active by": "WIFI", "Nhân sự": "x",
                         "Nguyên nhân không dùng Cap Lan": "Không chọn nguyên nhân"}])
    assert doc_kt.su_kien_tu_bang(lan)["thoi_diem"].iloc[0] == T("2026-11-02 17:26:47")   # file cáp LAN ghi tháng trước ngày
    cll = pd.DataFrame([{"Số HĐ": "KTAAB1837", "Tg tạo CL": "03/10/2026 12:00:31", "Nhân viên": "k", "Số lần lặp": "2", "Tg online": "10/12/2025 14:49:57"}])
    k = doc_kt.su_kien_tu_bang(cll)
    assert k["so_lan"].iloc[0] == 2 and k["thoi_diem"].iloc[0] == T("2026-10-03 12:00:31") and k["tg_online"].iloc[0] == T("2025-12-10 14:49:57")


def test_doc_xlsx_doc_thang_xml_dung_gia_tri_chu_va_so(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Số HĐ", "Số lần lặp"])
    ws.append(["KTAAB1", 2])
    f = tmp_path / "t.xlsx"
    wb.save(f)
    d = doc_kt.doc_bang(f)
    assert list(d.columns) == ["Số HĐ", "Số lần lặp"] and d.iloc[0].tolist() == ["KTAAB1", "2"]


# ------------------------------------------------------------------ chọn nguồn: mặc định LUÔN là dữ liệu thật
def test_mac_dinh_la_du_lieu_that_va_chi_dung_bo_minh_hoa_khi_dat_dung_bien(monkeypatch):
    monkeypatch.delenv("LIEN_KHOI_NGUON", raising=False)
    assert nguon.che_do() == "that" and not nguon.la_demo() and nguon.kt().empty and nguon.ngay_tham_chieu() is None
    monkeypatch.setenv("LIEN_KHOI_NGUON", "bat_ky_gia_tri_khac")
    assert nguon.che_do() == "that"                                      # chỉ đúng chữ "demo" mới bật
    monkeypatch.setenv("LIEN_KHOI_NGUON", "demo")
    assert nguon.che_do() == "demo" and nguon.ngay_tham_chieu() == T("2026-11-14")


def test_module_lien_khoi_khong_ghi_database():
    """Hướng liên khối chỉ ĐỌC: không có lệnh ghi / commit nào trong các module của nó."""
    goc = Path(__file__).resolve().parents[1] / "app" / "lien_khoi"
    ma = "\n".join(p.read_text(encoding="utf-8") for p in goc.glob("*.py") if p.name != "theo_doi.py")      # theo_doi.py chỉ ghi FILE SQLITE RIÊNG (xem test_lien_khoi_theo_doi.py)
    assert not re.search(r"\b(INSERT|UPDATE|DELETE)\b|\.commit\(|session_scope|\.add\(|to_sql", ma)


# ------------------------------------------------------------------ bộ minh hoạ: chốt chặn riêng tư + chạy được cả ba khối
def _doc_demo() -> dict[str, pd.DataFrame]:
    return {f.stem: pd.read_csv(f, dtype=str, keep_default_na=False) for f in DEMO.glob("*.csv")}


def test_bo_minh_hoa_khong_chua_ma_hop_dong_ten_hay_tai_khoan_that():
    d = _doc_demo()
    assert set(d) == {"kd", "kt", "kt_block", "sr_bi_dong", "sr_chu_dong", "no_cuoc", "dich_vu", "nguoi_nhan"}
    for ten, bang in d.items():
        assert not any(re.search(r"ten_kh|ten_khach|khach|dia_chi|sdt|phone|email", c, re.I) for c in bang.columns), ten      # không có cột nhạy cảm
        assert "so_hd" not in bang.columns or bang["so_hd"].str.fullmatch(r"MHAAA\d{4}").all(), ten                                          # mọi mã đều là mã giả
    nn = d["nguoi_nhan"]
    nguoi = pd.concat([d["kd"]["sale"], d["kt"]["nguoi"], d["sr_bi_dong"]["nhan_su_au"], d["sr_chu_dong"]["nhan_su_au"], nn["ma"], nn["quan_ly"]])
    assert nn["chat_id"].str.startswith("demo:").all()                                                          # mã chat chỉ là chữ giả, không phải mã Zalo thật
    assert nguoi[nguoi != ""].str.fullmatch(r"(sale|cskh|ktv|tp_kd|dt_dvkh|dt_kt|gd)_\d{2}").all()                                     # mọi tên người đã bị đổi
    toan_bo = " ".join(" ".join(b.astype(str).to_numpy().ravel()) for b in d.values())
    assert not re.search(r"\b(?!MH)[A-Z]{5}\d{4}\b", toan_bo)                                                   # không còn mã hợp đồng dạng thật
    assert not re.search(r"dng\.|tin\.|hni\.|ktm|kon tum|(?<![\d.])\d{9,}", toan_bo, re.I)                             # không còn tài khoản / địa danh / số điện thoại


def test_bo_minh_hoa_noi_duoc_ca_ba_khoi_va_chay_du_bon_luat(monkeypatch):
    monkeypatch.setenv("LIEN_KHOI_NGUON", "demo")
    kh = sk.khop_giua_khoi()
    assert kh["ca_ba"] > 0 and kh["kd"] == kh["kt"]                      # mọi hợp đồng có Kỹ thuật và Kinh doanh, nhiều hợp đồng có cả DVKH
    assert all(s["co_nguon"] for s in sk.trang_thai_nguon())
    v = luat.danh_sach_viec()
    assert set(v["luat"]) == set(luat.TEN_LUAT)                          # đủ 4 luật đều ra việc
    assert v["giao_kt"].str.startswith("ktv_").any() and (v["giao_dvkh"] == luat.GIAO_DVKH).any()   # có việc giao đúng KTV và có việc vào hàng chờ DVKH
    assert v["muc"].isin([luat.CAO, luat.TB]).all() and not v["ly_do"].str.contains("None|nan").any()
