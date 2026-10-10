"""Kiểm thử Danh bạ (chốt 10/10/2026): đọc hai kiểu file Excel, gộp trùng, tra cứu bỏ dấu, người sale tự thêm."""
from __future__ import annotations

import io
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import danh_ba as db                                          # noqa: E402
from app.config import DATA_DIR                                         # noqa: E402

pytestmark = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(), reason="Chưa dựng được database kiểm thử")

PNC_TD = [["DANH BẠ KHU VỰC", None, None, None, None, None, None],
          ["Khu vực", "Họ tên", "Chức vụ", "Email", "EXT", "Di động", "Ghi chú"],
          ["KHỐI BÁN HÀNG", None, None, None, None, None, None],
          ["Đà Nẵng", "Nguyễn Đăng Duy", "Giám Đốc", "DuyND10@fpt.com", "51177", "0903 505 960", None],
          [None, "Tô Duy Bình", "Đội trưởng TKBT", "BinhTD@vienthongtin.com", "51212.0", "962523713", "Block Sơn Trà"],
          [None, "Châu Ngọc Vinh", "Trưởng phòng KT Hạ Tầng", "VinhCN2@fpt.com", "51156", None, None],
          ["Khánh Hòa", "Lê Cảnh Ý", "Phó Giám đốc", "YLC@fpt.com", None, "0979999093", None],
          [None, "Hoàng Anh", "Giám Đốc", "AnhH4@fpt.com", "5678", None, None]]
TIN_MT = [["STT", "Họ tên", "Đơn vị", "Chức vụ", "IP phone", "Mail", "Kiêm nhiệm"],
          ["Chi nhánh Đà Nẵng", None, None, "Chi nhánh Đà Nẵng", None, None, None],
          [1, "Tô Duy Bình", "DNG", "Đội trưởng", "51212", "BinhTD7@fpt.com", "Block Sơn Trà"],
          [2, "Phan Anh Tú", "DNG", "Trưởng phòng Quản lý đối tác 2", "51148", "Tupa9@fpt.com", None],
          ["Chi nhánh Huế", None, None, "Chi nhánh Huế", None, None, None],
          [1, "Đào Thanh Vũ", "HUE", "Giám đốc Chi nhánh", None, "VuDT4@fpt.com", None]]


def _xlsx(sheets: dict) -> bytes:
    b = io.BytesIO()
    with pd.ExcelWriter(b, engine="openpyxl") as w:
        for ten, rows in sheets.items():
            pd.DataFrame(rows).to_excel(w, sheet_name=ten, header=False, index=False)
    return b.getvalue()


@pytest.fixture
def sach():
    """Dọn bảng danh_ba trước và sau test (database kiểm thử dùng chung)."""
    from sqlalchemy import text

    from app.bo_nho import xoa
    from app.db import engine
    db.dam_bao_bang()

    def don():
        with engine.begin() as c:
            c.execute(text("DELETE FROM danh_ba"))
            c.execute(text("DELETE FROM audit_log WHERE username LIKE 'kiemthu%'"))
        xoa("danh_ba")
    don()
    yield
    don()


def test_doc_file_kieu_pnc_nhan_ten_cot_va_bo_sheet_dia_chi():
    ds, bo = db.doc_file(_xlsx({"TĐĐT": PNC_TD, "Đia chỉ CN": [["Chi nhánh", "Địa chỉ cũ"], ["DNG", "Số 1"]]}))
    assert bo == ["Đia chỉ CN"] and len(ds) == 5
    ten = {r["ho_ten"]: r for r in ds}
    assert ten["Nguyễn Đăng Duy"]["don_vi"] == "Đà Nẵng"
    assert ten["Tô Duy Bình"]["don_vi"] == "Đà Nẵng"                 # ô gộp: người dưới kế thừa chi nhánh
    assert ten["Tô Duy Bình"]["ext"] == "51212" and ten["Tô Duy Bình"]["di_dong"] == "0962 523 713"   # 51212.0, thiếu số 0
    assert ten["Lê Cảnh Ý"]["don_vi"] == "Khánh Hòa" and ten["Lê Cảnh Ý"]["khu_vuc"] == "TĐĐT"
    assert ten["Châu Ngọc Vinh"]["di_dong"] is None


def test_doc_file_kieu_tin_lay_chi_nhanh_tu_dong_nhan_muc():
    ds, _ = db.doc_file(_xlsx({"Miền Trung": TIN_MT}))
    ten = {r["ho_ten"]: r for r in ds}
    assert len(ds) == 3
    assert ten["Tô Duy Bình"]["don_vi"] == "Đà Nẵng" and ten["Tô Duy Bình"]["email"] == "BinhTD7@fpt.com"
    assert ten["Đào Thanh Vũ"]["don_vi"] == "Huế"                    # nhãn "Chi nhánh Huế" thắng cột Đơn vị (HUE)
    assert ten["Tô Duy Bình"]["ghi_chu"] == "Block Sơn Trà"


def test_file_khong_phai_danh_ba_bao_loi_de_hieu():
    with pytest.raises(db.LoiDanhBa, match="Họ tên và Email"):
        db.doc_file(_xlsx({"Linh tinh": [["a", "b"], [1, 2]]}))
    with pytest.raises(db.LoiDanhBa, match="Excel"):
        db.doc_file(b"khong phai excel")


@pytest.mark.parametrize("cv, nhom", [
    ("Giám Đốc ", "giam_doc"), ("Giám đốc Chi nhánh", "giam_doc"), ("Phó Giám đốc Chi nhánh", "pho_giam_doc"),
    ("PGĐ TTPT&QLHT", "pho_giam_doc"), ("GĐ TTPT&QLHT MN", "giam_doc"),
    ("Trưởng phòng KT Hạ Tầng", "ha_tang"), ("CB Quản lý hạ tầng", "ha_tang"),
    ("Trưởng phòng KT TKBT  2", "truong_phong_kt"), ("Trưởng phòng Kỹ thuật hệ thống mạng", "truong_phong_kt"),
    ("Trưởng phòng Quản lý đối tác 1", "truong_phong_kt"), ("Phó phòng Kỹ thuật", "truong_phong_kt"),
    ("Đội trưởng TKBT", "doi_truong"), ("Kế toán trưởng", "ke_toan"), ("Trưởng Phòng DVKH", "dvkh"),
    ("AD - HR", "hcns"), ("Hành chính nhân sự", "hcns"), ("Quản lý User", "khac"), (None, "khac")])
def test_nhom_chuc_danh(cv, nhom):
    assert db.nhom_chuc(cv) == nhom


def test_ten_goi_va_so_dien_thoai():
    assert db.ten_goi("Tô Duy Bình") == "Bình" and db.ten_goi("") == ""
    assert db._sdt("974887968") == "0974 887 968" and db._sdt("0908 319 389") == "0908 319 389"
    assert db._sdt("nội bộ 12") == "nội bộ 12" and db._sdt(None) is None


def test_nap_thay_dung_nguon_va_gop_trung_giua_hai_file(sach):
    db.nap(_xlsx({"TĐĐT": PNC_TD}), "pnc.xlsx", "PNC", "kiemthu.admin")
    kq = db.nap(_xlsx({"Miền Trung": TIN_MT}), "tin.xlsx", "TIN", "kiemthu.admin")
    assert kq["so_nguoi"] == 3 and kq["so_cu"] == 0
    df = db.tat_ca()
    binh = df[df.ho_ten == "Tô Duy Bình"]
    assert len(binh) == 1                                            # cùng tên + chi nhánh -> một người
    r = binh.iloc[0]
    assert r.email == "BinhTD@vienthongtin.com" and r.email_khac == "BinhTD7@fpt.com" and r.nguon_ds == "PNC+TIN"
    assert r.nhom == "doi_truong"
    # nạp lại PNC chỉ thay dòng PNC, TIN còn nguyên
    kq2 = db.nap(_xlsx({"TĐĐT": PNC_TD[:5]}), "pnc2.xlsx", "PNC", "kiemthu.admin")
    ten = set(db.tat_ca().ho_ten)
    assert kq2["so_cu"] == 5 and "Lê Cảnh Ý" not in ten and "Đào Thanh Vũ" in ten
    with pytest.raises(db.LoiDanhBa):
        db.nap(b"", "x", "KHAC", "kiemthu.admin")


def _loc_js(du_lieu: dict, q="", dv="", nhom="all") -> list[str]:
    """Chạy ĐÚNG hàm lọc của trình duyệt (assets/danh_ba.js) bằng Node - bộ lọc không còn nằm ở Python."""
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("Máy không có Node để chạy bộ lọc của trình duyệt")
    js = Path(__file__).resolve().parent.parent / "assets" / "danh_ba.js"
    code = ("const m=require(process.argv[1]);let d='';process.stdin.on('data',c=>d+=c).on('end',()=>{const a=JSON.parse(d);"
            "console.log(JSON.stringify(m.loc(a.ds,a.q,a.dv,a.nhom).map(r=>r.t)));});")
    kq = subprocess.run([node, "-e", code, str(js)], input=json.dumps({"ds": du_lieu["ds"], "q": q, "dv": dv, "nhom": nhom}),
                        capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(kq.stdout)


def test_du_lieu_cho_trinh_duyet_gon_va_da_xep(sach):
    db.nap(_xlsx({"TĐĐT": PNC_TD}), "pnc.xlsx", "PNC", "kiemthu.admin")
    db.nap(_xlsx({"Miền Trung": TIN_MT}), "tin.xlsx", "TIN", "kiemthu.admin")
    d = db.cho_trinh_duyet()
    assert d["dv"][0] == "Đà Nẵng" and "PNC cập nhật" in d["moi"] and "TIN cập nhật" in d["moi"]
    assert d["nhom"]["giam_doc"] == "Giám đốc" and len(d["ds"]) == 7
    assert d["ds"][0]["v"] == "Đà Nẵng" and d["ds"][0]["n"] == "giam_doc"        # chi nhánh của sale, giám đốc trước
    binh = next(r for r in d["ds"] if r["t"] == "Tô Duy Bình")
    assert binh["e"] == "BinhTD@vienthongtin.com" and binh["k"] == "BinhTD7@fpt.com" and binh["y"] == 0
    assert set(binh) == {"i", "t", "c", "e", "k", "x", "d", "v", "g", "n", "s", "u", "y", "q", "b"}
    db.luu_tay({"ho_ten": "Người Tay", "email": "tay@fpt.com", "don_vi": "Đà Nẵng"}, "kiemthu.nvkd")
    assert next(r for r in db.cho_trinh_duyet()["ds"] if r["t"] == "Người Tay")["y"] > 0      # có id => hiện nút Sửa


def test_bo_loc_trinh_duyet_bo_dau_chi_nhanh_nhom_so_dien_thoai(sach):
    db.nap(_xlsx({"TĐĐT": PNC_TD}), "pnc.xlsx", "PNC", "kiemthu.admin")
    d = db.cho_trinh_duyet()
    assert _loc_js(d, "binh") == ["Tô Duy Bình"]                              # không dấu vẫn ra "Bình"
    assert len(_loc_js(d, "giam doc")) == 3                                   # Giám Đốc ×2 + Phó Giám đốc
    assert set(_loc_js(d, dv="Khánh Hòa")) == {"Lê Cảnh Ý", "Hoàng Anh"}
    assert set(_loc_js(d, nhom="giam_doc")) == {"Nguyễn Đăng Duy", "Hoàng Anh"}
    assert _loc_js(d, "0962523713") == ["Tô Duy Bình"]                        # tìm theo số điện thoại
    assert _loc_js(d, "khong co ai") == [] and len(_loc_js(d)) == 5
    assert _loc_js(d, "duy")[0] == "Nguyễn Đăng Duy"                          # khớp ngay trong TÊN xếp trước ("Tô Duy Bình" cũng khớp)


def test_goi_y_doi_truong_theo_dia_chi_va_doan_chi_nhanh(sach):
    db.nap(_xlsx({"TĐĐT": PNC_TD}), "pnc.xlsx", "PNC", "kiemthu.admin")
    khop, tat_ca = db.doi_truong_theo_dia_chi("Đà Nẵng", "K62/H75/17 Nguyễn Phan Vinh, Sơn Trà, Đà Nẵng")
    assert list(khop.ho_ten) == ["Tô Duy Bình"] and len(tat_ca) == 1
    khop, _ = db.doi_truong_theo_dia_chi("Đà Nẵng", "12 Lê Duẩn, Hải Châu, Đà Nẵng")
    assert khop.empty                                                  # địa chỉ khác block: để sale tự chọn
    assert db.doan_don_vi("225 Cầu Dừa, Phước Long, Nha Trang, Khánh Hòa") == "Khánh Hòa"
    assert db.doan_don_vi("123 đường abc") is None


def test_theo_nhom_uu_tien_ban_moi_khi_chi_nhanh_co_trong_hai_file(sach):
    db.nap(_xlsx({"TĐĐT": PNC_TD}), "pnc.xlsx", "PNC", "kiemthu.admin")
    tin = [TIN_MT[0], ["Chi nhánh Đà Nẵng", None, None, "x", None, None, None],
           [1, "Huỳnh Bá Duy", "DNG", "Giám đốc Chi nhánh", "51181", "DuyHB2@fpt.com", None]]
    db.nap(_xlsx({"Miền Trung": tin}), "tin.xlsx", "TIN", "kiemthu.admin")
    assert list(db.theo_nhom("Đà Nẵng", "giam_doc").ho_ten) == ["Nguyễn Đăng Duy"]       # bản PNC T10 mới hơn TIN T8
    assert list(db.theo_nhom("Huế", "giam_doc").ho_ten) == []                            # chi nhánh không có ai ở nhóm đó


def test_nguoi_sale_tu_them_sua_xoa_va_chi_sua_duoc_nguoi_tay(sach):
    id_ = db.luu_tay({"ho_ten": "Võ Hoàng Đức Phúc", "email": " PhucVHD@fpt.com ", "don_vi": "Khánh Hòa"}, "kiemthu.nvkd")
    r = db.tat_ca().set_index("ho_ten").loc["Võ Hoàng Đức Phúc"]
    assert r.email == "PhucVHD@fpt.com" and r.nguon == "TAY" and int(r.id_tay) == id_
    db.luu_tay({"ho_ten": "Võ Hoàng Đức Phúc", "di_dong": "901234567", "don_vi": "Khánh Hòa"}, "kiemthu.nvkd", id_)
    assert db.tat_ca().set_index("ho_ten").loc["Võ Hoàng Đức Phúc"].di_dong == "0901 234 567"
    for sai, thong_bao in (({"ho_ten": ""}, "họ tên"), ({"ho_ten": "A", "email": "khong-phai-mail"}, "Email"),
                           ({"ho_ten": "A"}, "email hoặc số")):
        with pytest.raises(db.LoiDanhBa, match=thong_bao):
            db.luu_tay(sai, "kiemthu.nvkd")
    db.nap(_xlsx({"TĐĐT": PNC_TD}), "pnc.xlsx", "PNC", "kiemthu.admin")
    id_file = int(db.tat_ca().set_index("ho_ten").loc["Lê Cảnh Ý"].id)
    with pytest.raises(db.LoiDanhBa, match="sale tự thêm"):
        db.xoa_tay(id_file, "kiemthu.nvkd")
    db.xoa_tay(id_, "kiemthu.nvkd")
    assert "Võ Hoàng Đức Phúc" not in set(db.tat_ca().ho_ten)


def test_quyen_soan_email_chi_admin_va_nvkd_ibb7():
    from app.auth import SessionUser

    def tk(role, scope):
        return SessionUser(SimpleNamespace(id=1, username=f"kiemthu.{role}", ho_ten="K", role=role, ma_nv=None,
                                           session_version=0, scope=json.dumps(scope)))
    assert tk("admin", []).duoc_soan_mail and tk("nvkd", ["IBB7"]).duoc_soan_mail
    assert not tk("nvkd", ["IBB2"]).duoc_soan_mail and not tk("phong", ["IBB7"]).duoc_soan_mail
    for trang in ("/soanmail", "/danhba"):
        assert tk("nvkd", ["IBB7"]).vao_duoc(trang)
