"""Kiểm thử Nhập tồn + tài khoản Nhân viên KD (chốt với chủ app 21/09/2026)."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import nhap_ton as nt                                          # noqa: E402
from app.config import DATA_DIR                                          # noqa: E402

pytestmark = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(),
                                reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")


def _tk(role: str, scope: list[str]):
    from app.auth import SessionUser
    return SessionUser(SimpleNamespace(id=1, username=f"kiemthu.{role}", ho_ten="Kiểm thử", role=role, ma_nv=None,
                                       session_version=0, scope=json.dumps(scope)))


# ------------------------------------------------------------------ cảnh báo
def test_tra_ve_han_chot_la_het_ngay_d_cong_3():
    """Chủ app: trả về ngày 19/9 thì hạn chót là hết ngày 22/9, quá hạn HĐ tự huỷ - luôn báo đỏ cho TP."""
    d = date(2026, 9, 19)
    muc, chu, _ = nt.trang_thai("tra_ve", d, None, date(2026, 9, 21))
    assert muc == "do" and "còn 1 ngày" in chu and "22/09" in chu
    assert len(chu) <= 34, "chữ cảnh báo phải ngắn, cột hẹp - dài quá là dòng cao 5 hàng"
    muc, chu, _ = nt.trang_thai("tra_ve", d, None, date(2026, 9, 22))
    assert muc == "do" and "hạn hết hôm nay" in chu
    muc, chu, thu_tu = nt.trang_thai("tra_ve", d, None, date(2026, 9, 23))
    assert muc == "do" and "Quá hạn 1 ngày" in chu and thu_tu == 0      # quá hạn đứng đầu cụm


def test_hen_thi_cong_qua_ngay_bao_do_dung_hom_nay_bao_vang():
    hom = date(2026, 9, 21)
    assert nt.trang_thai("hen", date(2026, 9, 19), None, hom)[:2] == ("do", "Quá hẹn 2 ngày")
    assert nt.trang_thai("hen", hom, None, hom)[0] == "vang"
    assert nt.trang_thai("hen", date(2026, 9, 25), None, hom)[0] == ""


def test_phuong_an_huy_va_da_trien_khai_khong_bao_do():
    hom = date(2026, 9, 21)
    assert nt.trang_thai("hen", date(2026, 9, 1), nt.PA_HUY, hom)[0] == "huy"
    assert nt.trang_thai("tra_ve", date(2026, 9, 1), nt.PA_DA_TRIEN_KHAI, hom)[0] == ""


# ------------------------------------------------------------------ đọc sheet cũ
@pytest.mark.parametrize("chu, loai, ngay", [
    ("29/9", "hen", date(2026, 9, 29)),
    ("Trả về 19/9", "tra_ve", date(2026, 9, 19)),
    ("trả về 20/9", "tra_ve", date(2026, 9, 20)),
    ("trả vè 18/9", "tra_ve", date(2026, 9, 18)),          # gõ sai dấu trên sheet thật
    ("treo 13/9", None, None),                            # Treo, CPTC: chủ app chốt ghi vào ghi chú
    ("cptc 22/9", None, None),
    ("đang hoàn tiền", None, None),
])
def test_doc_moc_viet_tay_tren_sheet(chu, loai, ngay):
    assert nt.doc_moc(chu, date(2026, 9, 21)) == (loai, ngay)


def test_chi_nhan_dung_phuong_an_trong_danh_sach():
    assert nt._chuan({"phuong_an": "Huỷ"}) == {"phuong_an": "Huỷ"}
    with pytest.raises(nt.LoiNhapTon):
        nt._chuan({"phuong_an": "Treo"})
    with pytest.raises(nt.LoiNhapTon):
        nt._chuan({"ghi_chu": "x" * (nt.GHI_CHU_TOI_DA + 1)})
    assert nt.cau_hinh()["phuong_an"] == ["Đang chờ triển khai", "Huỷ", "KH đang suy nghĩ - Chốt lại",
                                           "Đã triển khai"]


# ------------------------------------------------------------------ quyền
def test_quyen_nhan_vien_kd_ibb7():
    tk = _tk("nvkd", ["IBB7"])
    assert tk.duoc_xem_nhan_su and tk.phong_nhan_su() == ["IBB7"]
    assert tk.phong_nhap_ton() == ["IBB7"] and tk.duoc_nhap_ton
    assert tk.duoc_xem_ads and not tk.duoc_cau_hinh                # Ads chỉ xem, không sửa
    for trang in ("/nhapton", "/phong", "/ads", "/phantich"):         # /phantich: chỉ hai phần Bán theo tỉnh (22/10/2026, xem tests/test_ban_tinh.py)
        assert tk.vao_duoc(trang)
    for trang in ("/", "/hr", "/upload", "/quantri", "/tracking"):
        assert not tk.vao_duoc(trang), trang
    assert not tk.duoc_upload


def test_nhan_vien_kd_mo_app_la_vao_thang_bao_cao_ngay():
    """Việc đầu tiên trong ngày của sale là báo cáo đầu ngày (chốt 24/09/2026).
    (test_trang_mo_dau_theo_vai_tro trong test_he_thong_hoa đang hỏng sẵn vì môi trường, kiểm riêng ở đây.)"""
    from app.ui.app import trang_mo_dau
    assert trang_mo_dau(_tk("nvkd", ["IBB7"])) == "/baocaongay"
    assert trang_mo_dau(_tk("phong", ["IBB7"])) == "/phong"


def test_nhan_vien_kd_phong_khac_khong_thay_ads_va_nhap_ton():
    tk = _tk("nvkd", ["IBB2"])
    assert not tk.duoc_xem_ads and tk.phong_nhap_ton() == []


def test_truong_phong_ibb7_theo_doi_duoc_nhap_ton():
    assert _tk("phong", ["IBB7"]).phong_nhap_ton() == ["IBB7"]
    assert _tk("phong", ["IBB2"]).phong_nhap_ton() == []
    assert _tk("phong", ["IBB7"]).vao_duoc("/hr")                  # vai trò khác không bị giới hạn trang


# ------------------------------------------------------------------ danh sách + ghi
def test_danh_sach_xep_theo_tung_cum_nhan_vien():
    df = nt.danh_sach(["IBB7"])
    if df.empty:
        pytest.skip("database kiểm thử không có HĐ tồn IBB7")
    doi = (df.acc_norm != df.acc_norm.shift()).sum()
    assert doi == df.acc_norm.nunique()                            # mỗi người một cụm liền nhau
    assert {"hop_dong", "ten_khach_hang", "ngay_tao_hd", "acc", "ho_ten"} <= set(df.columns)


@pytest.fixture
def mot_ca():
    from sqlalchemy import delete

    from app.db import session_scope
    from app.models import AuditLog, TonTheoDoi
    df = nt.danh_sach(["IBB7"])
    if df.empty:
        pytest.skip("database kiểm thử không có HĐ tồn IBB7")
    r = df.iloc[0]
    yield r
    with session_scope() as s:
        s.execute(delete(TonTheoDoi).where(TonTheoDoi.hop_dong == r.hop_dong))
        s.execute(delete(AuditLog).where(AuditLog.username.like("kiemthu%")))


def test_tai_khoan_dung_chung_ghi_duoi_ten_nguoi_dang_chon(mot_ca):
    """Sale full quyền (chốt 24/09/2026) nên trang không truyền `chi_acc` nữa; ô tên chỉ để ghi
    "cập nhật bởi" cho Trưởng phòng biết ai sửa."""
    r = mot_ca
    nt.luu(r.hop_dong, {"ghi_chu": "KH hẹn cuối tuần", "loai_moc": "hen", "ngay_moc": "2026-09-27",
                        "phuong_an": "Đang chờ triển khai"}, ["IBB7"], "kiemthu.nvkd",
           ghi_ten="Nguyễn Văn Kiểm")
    moi = nt.danh_sach(["IBB7"]).set_index("hop_dong").loc[r.hop_dong]
    assert moi.cap_nhat_boi == "Nguyễn Văn Kiểm" and moi.cap_nhat.endswith("· Kiểm")
    assert moi.ghi_chu == "KH hẹn cuối tuần" and not moi.thieu


def test_sale_sua_duoc_ca_cua_nguoi_khac(mot_ca):
    """Chủ app chốt 24/09/2026: tài khoản sale full quyền, ai cũng sửa hộ được ca của đồng đội."""
    nt.luu(mot_ca.hop_dong, {"ghi_chu": "Sửa hộ đồng đội"}, ["IBB7"], "kiemthu.nvkd", ghi_ten="Ai Đó")
    assert nt.danh_sach(["IBB7"]).set_index("hop_dong").loc[mot_ca.hop_dong].ghi_chu == "Sửa hộ đồng đội"


def test_khong_ghi_duoc_hop_dong_ngoai_danh_sach_ton():
    with pytest.raises(nt.LoiNhapTon, match="không còn trong danh sách tồn"):
        nt.luu("KHONGCO999", {"ghi_chu": "x"}, ["IBB7"], "kiemthu.tp")


# ------------------------------------------------------------------ tên khách hàng (dữ liệu cá nhân)
def test_chi_luu_ten_khach_hang_cua_phong_bat_nhap_ton(monkeypatch):
    """Chốt 21/09/2026: tên KH chỉ lưu cho phòng bật Nhập tồn (IBB7) và chỉ file Internet; phòng khác vẫn bỏ."""
    import pandas as pd

    from app.ingest import commit as cm
    assert cm.phong_luu_ten_kh() == {"IBB7"}
    monkeypatch.setattr(cm, "LUU_TEN_KHACH_HANG", False)
    monkeypatch.setattr(cm, "assign_phong", lambda acc, *a: ({"sale.ibb7": "IBB7"}.get(acc, "IBB2"), False))
    df = pd.DataFrame([{"hop_dong": "HD1", "acc_nhan_vien": "sale.ibb7", "ten_khach_hang": "Nguyen Van A"},
                       {"hop_dong": "HD2", "acc_nhan_vien": "sale.ibb2", "ten_khach_hang": "Tran Thi B"}])
    net = cm._fact_rows(SimpleNamespace(df=df, dataset="internet"), {}, 1)
    assert [r["ten_khach_hang"] for r in net] == ["Nguyen Van A", None]
    fpl = cm._fact_rows(SimpleNamespace(df=df, dataset="fptplay"), {}, 1)
    assert [r["ten_khach_hang"] for r in fpl] == [None, None]


# ------------------------------------------------------------------ giao diện (chủ app 21/09: bấm tên phải thấy đổi ngay)
def test_o_nhan_vien_tick_nhieu_nguoi():
    """Chủ app chốt 21/09/2026: ô thả xuống có ô tick, chọn nhiều người; rỗng = tất cả."""
    import pandas as pd

    from app.ui.pages.nhapton import _ds_acc, _nhan_nv, _tieu_de
    tong = pd.DataFrame({"acc_norm": ["a", "b", "c", "d"], "ho_ten": ["An", "Bình", "Chi", "Dũng"],
                         "ton": [21, 6, 3, 1], "gap": [6, 0, 1, 0], "chua_cap_nhat": [2, 4, 0, 0]})
    r = next(tong.itertuples())
    assert _nhan_nv(r) == "An · 21 ca · 6 gấp · 2 chưa cập nhật"
    assert _nhan_nv(list(tong.itertuples())[3]) == "Dũng · 1 ca"                  # không có gì đáng lo thì gọn
    assert _ds_acc(None) == [] and _ds_acc([]) == [] and _ds_acc("all") == [] and _ds_acc(["a", "b"]) == ["a", "b"]
    assert _tieu_de(tong, []) == "Tất cả nhân viên"
    assert _tieu_de(tong, ["a", "c"]) == "An, Chi"
    assert _tieu_de(tong, ["a", "b", "c", "d"]) == "4 nhân viên"
    df = pd.DataFrame({"acc_norm": ["a", "a", "b", "c"], "thu_tu": [5] * 4, "thieu": [False] * 4,
                       "hop_dong": ["1", "2", "3", "4"], "ten_khach_hang": [""] * 4})
    assert len(nt.loc(df, ["a", "c"])) == 3 and len(nt.loc(df, [])) == 4 and len(nt.loc(df, "b")) == 1


def test_bang_theo_nhan_vien_va_dong_ca_phong():
    """Tổng quan từng nhân sự + dòng ghim "Cả phòng" (chủ app yêu cầu 24/09/2026)."""
    import pandas as pd

    from app.ui.pages.nhapton import _cot_nv, _dong_nv
    tong = pd.DataFrame({"acc_norm": ["a", "b"], "acc": ["DNG.A", "DNG.B"], "ho_ten": ["An", "Bình"],
                         "ton": [10, 5], "gap": [2, 0], "den_han": [1, 0], "chua_cap_nhat": [4, 5]})
    ds, ghim = _dong_nv(tong)
    assert [r["ho_ten"] for r in ds] == ["An", "Bình"]
    assert ds[0]["pct"] == 60 and ds[1]["pct"] == 0                       # 6/10 và 0/5 đã điền đủ
    assert ghim[0]["ho_ten"] == "Cả phòng" and ghim[0]["acc"] == "2 nhân viên"
    assert ghim[0]["ton"] == 15 and ghim[0]["gap"] == 2 and ghim[0]["chua_cap_nhat"] == 9 and ghim[0]["pct"] == 40
    assert _dong_nv(pd.DataFrame()) == ([], [])
    assert [c["field"] for c in _cot_nv()][:3] == ["ho_ten", "acc", "ton"]


def test_bon_o_so_noi_ro_dang_dem_cho_ai():
    """Chu app hoi "tong ton 16 la sao?": 4 o dem theo o Nhan vien dang tick nen phai ghi ro pham vi."""
    import pandas as pd

    from app.ui.pages.nhapton import _kpi, _pham_vi
    tong = pd.DataFrame({"acc_norm": ["a", "b"], "acc": ["DNG.A", "DNG.B"], "ho_ten": ["An", "Binh"],
                         "ton": [16, 153], "gap": [5, 44], "den_han": [0, 8], "chua_cap_nhat": [4, 76]})
    chu = "".join(x if isinstance(x, str) else x.children for x in _pham_vi(tong, []))
    assert "cả phòng" in chu and "2 nhân viên" in chu and "169 ca" in chu
    chu = "".join(x if isinstance(x, str) else x.children for x in _pham_vi(tong, ["a"]))
    assert "chỉ là số của" in chu and "An" in chu and "Bỏ tick" in chu
    d = {"ton": 16, "chua_cap_nhat": 4, "gap": 5, "den_han": 0, "tra_ve": 0, "qua_hen": 5, "huy": 0}
    assert _kpi(d, "all", "An")[0].children[2].children == "Tất cả ca của An"


def test_bang_nhan_vien_xep_nguoi_con_nhieu_viec_len_dau():
    import pandas as pd

    from app.ui.pages.nhapton import _dong_nv
    tong = pd.DataFrame({"acc_norm": ["a", "b", "c"], "acc": ["A", "B", "C"], "ho_ten": ["An", "Bình", "Chi"],
                         "ton": [4, 17, 14], "gap": [0, 5, 8], "den_han": [0, 0, 2],
                         "chua_cap_nhat": [4, 8, 1]})
    ds, _ = _dong_nv(tong)
    assert [r["ho_ten"] for r in ds] == ["Chi", "Bình", "An"]           # gấp nhiều nhất lên đầu


def test_dong_tieu_de_cum_gon_va_bo_khi_xem_mot_nguoi():
    """Ô ghim bên trái hiện "N ca", ô dài hiện tên - acc - việc còn lại (không lặp tên).
    Xem đúng một người thì bỏ dòng tiêu đề cụm cho đỡ rối."""
    import pandas as pd

    from app.ui.pages.nhapton import _dong_luoi
    df = pd.DataFrame({"acc_norm": ["a", "a"], "acc": ["DNG.A"] * 2, "ho_ten": ["Bùi Ngô Anh Thắng"] * 2,
                       "hop_dong": ["H1", "H2"], "ten_khach_hang": ["KH1", "KH2"], "loai_moc": ["hen", None],
                       "so_ngay_cho": [3, 4], "thu_tu": [5, 5], "thieu": [True, False], "muc": ["", ""]})
    dong = _dong_luoi(df)
    assert dong[0]["hop_dong"] == "2 ca" and dong[0]["loai_dong"] == "nhom"
    assert dong[0]["ten_khach_hang"] == "Bùi Ngô Anh Thắng · DNG.A · 1 chưa cập nhật"
    assert len(dong) == 3
    mot = _dong_luoi(df, nhom=False)
    assert len(mot) == 2 and all(r.get("loai_dong") is None for r in mot)


def test_o_so_cung_la_nut_loc_va_danh_dau_o_dang_chon():
    from app.ui.pages.nhapton import _kpi
    d = {"ton": 32, "chua_cap_nhat": 5, "gap": 2, "den_han": 1, "tra_ve": 1, "qua_hen": 1, "huy": 0}
    o = _kpi(d, "gap")
    assert [x.id["v"] for x in o] == ["all", "gap", "den_han", "thieu"]      # gấp đứng ngay sau tổng
    assert ["dang-chon" in x.className for x in o] == [False, True, False, False]
    assert "bad" in o[1].className                                          # còn ca gấp thì đỏ


# ------------------------------------------------- rà soát UX 27/09/2026
def test_loc_theo_so_ngay_ton():
    """Ô "Ngày tồn" lọc ra các ca tồn lâu - ca tồn lâu là ca dễ tự huỷ nhất."""
    import pandas as pd
    df = pd.DataFrame({"acc_norm": ["a"] * 4, "hop_dong": list("ABCD"), "ten_khach_hang": [""] * 4,
                       "so_ngay_cho": [3, 8, 20, 45], "thu_tu": [5] * 4, "thieu": [False] * 4,
                       "muc": [""] * 4})
    assert len(nt.loc(df, None, None, None, "all")) == 4
    assert list(nt.loc(df, None, None, None, "7").hop_dong) == ["B", "C", "D"]
    assert list(nt.loc(df, None, None, None, "14").hop_dong) == ["C", "D"]
    assert list(nt.loc(df, None, None, None, "30").hop_dong) == ["D"]
    assert len(nt.loc(df, None, None, None, None)) == 4      # chưa chọn thì không lọc


def test_cot_so_ngay_ton_khong_con_ten_cho():
    """Chủ app chốt 27/09/2026: gọi "Ngày tồn", không gọi "Chờ" (có test chặn để khỏi đổi ngược)."""
    import pandas as pd

    from app.ui.pages.nhapton import _cot
    cot = {c["field"]: c for c in _cot(3, ["Huỷ"]) if "field" in c}
    assert cot["so_ngay_cho"]["headerName"] == "Ngày tồn"
    assert cot["so_ngay_cho"]["width"] >= 66                 # "Ngày tồn" dài hơn "Chờ", đừng bóp lại
    df = pd.DataFrame({"ho_ten": ["A"], "acc": ["a"], "hop_dong": ["H1"], "ten_khach_hang": [""],
                       "ngay_tao_hd": ["2026-09-01"], "so_ngay_cho": [12], "ghi_chu": [""],
                       "loai_moc": [""], "ngay_moc": [""], "phuong_an": [""], "canh_bao": [""],
                       "cap_nhat": [""]})
    assert "Số ngày tồn" in nt.file_excel(df).columns      # file Excel gọi giống hệt trên bảng


def test_hai_phuong_an_da_chot_co_hai_mau_dong_khac_nhau():
    """Huỷ và "KH đang suy nghĩ - Chốt lại" phải nhìn ra ngay là hai trạng thái khác nhau."""
    from app.ui.pages.nhapton import DONG_HUY, DONG_SUY_NGHI, LOP_PA
    assert LOP_PA[nt.PA_HUY] != LOP_PA[nt.PA_SUY_NGHI]
    assert nt.PA_HUY in DONG_HUY and nt.PA_SUY_NGHI in DONG_SUY_NGHI
    assert DONG_HUY != DONG_SUY_NGHI


def test_bang_bat_lui_lai_lam_lai():
    """Ctrl+Z phải được bật ở chính bảng, và Ctrl+Shift+Z do assets/lam_lai_o.js gắn thêm
    (ag-grid chỉ tự nhận Ctrl+Y). Vá dòng phải HOÃN vì ag-grid xoá undo stack mỗi lần vá."""
    from pathlib import Path
    from app.ui.pages import nhapton
    from app.ui.pages.nhapton import _cot

    luoi = nhapton.bang("nt-luoi", _cot(3, ["Huỷ"]), cao=640,
                        tuy_chon={"undoRedoCellEditing": True, "undoRedoCellEditingLimit": 25})
    assert luoi.dashGridOptions["undoRedoCellEditing"] is True
    js = (Path(__file__).resolve().parent.parent / "assets" / "lam_lai_o.js").read_text(encoding="utf-8")
    assert "redoCellEditing" in js and "shiftKey" in js
    assert nhapton.CHO_VA >= 3, "hoãn quá ngắn thì gõ chưa xong đã mất Ctrl+Z"
    assert nhapton.NHIP_MS <= nhapton.CHO_VA * 1000, "nhịp phải dày hơn thời gian chờ mới vá đúng lúc"


def test_mau_dong_huy_phai_dung_sau_mau_canh_bao():
    """Ca đã huỷ thì không còn việc phải làm, nên màu xám phải đè lên đỏ/vàng.
    CSS cùng độ đặc hiệu nên luật đứng sau thắng - đừng đảo thứ tự hai khối này."""
    from pathlib import Path
    css = (Path(__file__).resolve().parent.parent / "assets" / "style.css").read_text(encoding="utf-8")
    assert css.index(".ag-row.dong-suy-nghi") < css.index(".ag-row.dong-do")
    assert css.index(".ag-row.dong-do") < css.index(".ag-row.dong-huy,")
