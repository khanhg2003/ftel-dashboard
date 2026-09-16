"""Kiểm thử các chức năng giao diện thêm ở đợt tối ưu trải nghiệm (nhóm A → F).

Chốt những thứ dễ vỡ khi sửa về sau: ảnh PNG, cỡ bảng vừa màn hình, lọc chi nhánh,
thêm/xoá tài khoản, xoá bầy/phòng có ràng buộc, trang 404.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import DATA_DIR                                       # noqa: E402
from app.db import session_scope                                      # noqa: E402
from app.org import loc_chi_nhanh, phong_order, xoa_bay, xoa_phong    # noqa: E402

THANG = "2026-09"
pytestmark = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(),
                                reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")


# --------------------------------------------------------------- ảnh báo cáo
def test_chup_anh_bao_cao_day_du_ca_bang():
    from PIL import Image

    from app.export_png import anh_tong_quan
    from app.overview import bang_tong_quan
    noi_dung, ten = anh_tong_quan(THANG)
    assert ten == "BaoCaoTong_ToanCN_202609_ngay11.png"
    img = Image.open(io.BytesIO(noi_dung))
    df, _ = bang_tong_quan(THANG)
    # đủ chiều cao cho toàn bộ số dòng (không cắt bớt như chụp màn hình)
    from app.export_png import CAO_DONG, TY_LE_MIN
    assert img.height > len(df) * CAO_DONG * TY_LE_MIN
    # ngang khoảng 2.400px: đủ nét mà Zalo không thu nhỏ
    assert 2000 < img.width <= 2600 and img.mode == "RGB"


def test_anh_dung_font_tieng_viet_di_kem_app():
    """Máy chủ Vercel không có font tiếng Việt - phải dùng font trong assets/fonts."""
    from app.export_png import THU_MUC_FONT, _duong_dan_font
    for kieu in ("thuong", "vua", "dam", "rat_dam"):
        assert _duong_dan_font(kieu).parent == THU_MUC_FONT


# ------------------------------------------------------------ cỡ bảng vừa màn hình
@pytest.mark.parametrize("rong_man_hinh, toi_da", [(1366, 0.75), (1536, 0.85), (2560, 1.0)])
def test_ty_le_vua_man_hinh(rong_man_hinh, toi_da):
    from app.ui.pages.tongquan import _cols, ty_le_vua_man_hinh
    cols = _cols(THANG, 11)
    ty_le = ty_le_vua_man_hinh(cols, {"w": rong_man_hinh})
    assert 0.3 < ty_le <= toi_da
    # thu gọn sidebar thì được rộng hơn
    assert ty_le_vua_man_hinh(cols, {"w": rong_man_hinh}, True) >= ty_le


def test_tieu_de_cot_du_rong_de_khong_bi_cat():
    """Tiêu đề xuống dòng được thì mới không hiện dấu ... - phải bật đúng hai tuỳ chọn."""
    from app.ui.pages.tongquan import layout
    grid = _tim(layout(), "tq-grid")
    assert grid.defaultColDef["wrapHeaderText"] and grid.defaultColDef["autoHeaderHeight"]


def test_tracking_ghim_tieu_de_bang_chieu_cao_co_dinh():
    from app.ui.pages.tracking import layout
    grid = _tim(layout(), "tk-grid")
    assert grid.dashGridOptions["domLayout"] == "normal"     # cuộn trong bảng -> tiêu đề ở lại
    assert grid.style["height"].endswith("px")


def _tim(node, id_can_tim):
    """Tìm một component theo id trong cây layout (children có thể là 1 hoặc nhiều)."""
    if getattr(node, "id", None) == id_can_tim:
        return node
    con = getattr(node, "children", None)
    if con is None or isinstance(con, str):
        return None
    for c in (con if isinstance(con, (list, tuple)) else [con]):
        kq = _tim(c, id_can_tim)
        if kq is not None:
            return kq
    return None


# ---------------------------------------------------------------- lọc chi nhánh
def test_loc_chi_nhanh_cat_dung_danh_sach_phong():
    tat_ca = {p["code"] for p in phong_order(THANG)}
    dng = set(loc_chi_nhanh(None, "DNG", THANG))
    qnm = set(loc_chi_nhanh(None, "QNM", THANG))
    assert dng and qnm and not (dng & qnm)
    assert dng | qnm == tat_ca
    assert loc_chi_nhanh(None, "all", THANG) is None
    # giao với quyền: trưởng phòng IBB2 chọn QNM thì không còn phòng nào
    assert loc_chi_nhanh(["IBB2"], "DNG", THANG) == ["IBB2"]
    assert loc_chi_nhanh(["IBB2"], "QNM", THANG) == []


def test_bao_cao_theo_chi_nhanh_cong_lai_bang_tong():
    from app.overview import bang_tong_quan

    def tong(cn):
        df, _ = bang_tong_quan(THANG, chi_phong=loc_chi_nhanh(None, cn, THANG))
        return int(df[df.loai_dong == "total"].iloc[0].online)

    assert tong("DNG") + tong("QNM") == tong("all") == 1394


def test_nhan_su_co_cot_chi_nhanh():
    from app.hr_metrics import hieu_suat_nhan_su
    df = hieu_suat_nhan_su(THANG)
    assert "chi_nhanh" in df.columns
    assert {"Đà Nẵng", "Quảng Nam"} <= set(df.chi_nhanh.unique())


# ------------------------------------------------------------------ tài khoản
def test_them_va_xoa_tai_khoan():
    from app.admin_service import them_user, xoa_user
    ok, msg = them_user({"username": "zz_ui_test", "ho_ten": "Kiểm thử giao diện",
                         "role": "phong", "pham_vi": ["IBB2"], "mat_khau": "Kiemthu@2026"},
                        "admin")
    assert ok, msg
    ok2, msg2 = them_user({"username": "zz_ui_test", "role": "phong", "pham_vi": ["IBB2"],
                           "mat_khau": "Kiemthu@2026"}, "admin")
    assert not ok2 and "đã tồn tại" in msg2            # không cho trùng tên
    n, _ = xoa_user(["zz_ui_test"], "admin")
    assert n == 1


@pytest.mark.parametrize("du_lieu, loi_mong_doi", [
    ({"username": "", "mat_khau": "Kiemthu@2026"}, "Chưa nhập"),
    ({"username": "zz_x", "mat_khau": "123"}, "8 ký tự"),
    ({"username": "zz_x", "mat_khau": "Kiemthu@2026", "role": "phong", "pham_vi": []},
     "phòng phụ trách"),
])
def test_tao_tai_khoan_thieu_thong_tin_thi_bao_loi(du_lieu, loi_mong_doi):
    from app.admin_service import them_user
    ok, msg = them_user(du_lieu, "admin")
    assert not ok and loi_mong_doi in msg


def test_khong_xoa_duoc_chinh_minh_va_admin_cuoi_cung():
    from app.admin_service import xoa_user
    n, bo_qua = xoa_user(["admin"], "admin")
    assert n == 0 and "không tự xoá" in " ".join(bo_qua)


# -------------------------------------------------------------- bầy và phòng
def test_khong_xoa_bay_con_phong_va_phong_dang_co_du_lieu():
    from app.org import bay_info
    ma_bay = next(c for c, _ in bay_info().items()
                  if any(p["bay"] == c for p in phong_order()))
    with session_scope() as s:
        n, bo_qua = xoa_bay(s, [ma_bay])
        assert n == 0 and "còn" in bo_qua[0]
        n2, bo_qua2 = xoa_phong(s, ["IBB2"])
        assert n2 == 0 and "Ngừng dùng" in bo_qua2[0]


# ------------------------------------------------------------------- 404
def test_duong_dan_la_hien_trang_404():
    from flask_login import login_user
    from sqlalchemy import select

    from app.auth import SessionUser
    from app.models import User
    from app.ui.app import _router, server
    with session_scope() as s:
        u = SessionUser(s.execute(select(User).where(User.role == "admin")).scalars().first())
    with server.test_request_context("/"):
        login_user(u)
        noi_dung, _ = _router("/khong-co-trang-nay")
    assert "404" in str(noi_dung.children[0].children)


# --------------------------------------------------------- chọn kỳ & hướng dẫn
def test_chon_ky_khong_con_tab_thang_cung():
    """Tháng mới có dữ liệu là tự hiện ra, không phải sửa code mỗi đầu tháng."""
    from app.metrics import cac_thang_co_du_lieu
    from app.ui.components import chon_ky, ten_ky
    thangs = cac_thang_co_du_lieu()
    bo_chon = chon_ky("kt-thang", thangs)
    dd = bo_chon.children[1]
    assert [o["value"] for o in dd.options] == thangs
    assert dd.value == thangs[0]                      # mặc định là kỳ mới nhất
    assert ten_ky("2026-09") == "Tháng 09/2026"


def test_trang_huong_dan_dung_duoc():
    from app.ui.pages.huongdan import layout, topbar
    assert layout() is not None and topbar() is not None


def test_nap_duoc_nhieu_file_mot_luot():
    from app.ui.pages.upload import layout
    up = _tim(layout(), "up-file")
    assert up.multiple is True


# ------------------------------------------------------ bố cục & khả năng đọc
@pytest.mark.parametrize("trang, id_bang, cao_toi_da", [
    ("hr", "hr-canhbao", 400), ("hr", "hr-grid", 520),
    ("sosanh", "ss-hut", 460), ("quantri", "qt-staff-grid", 500),
])
def test_bang_dai_cuon_trong_khung(trang, id_bang, cao_toi_da):
    """Bảng dài phải cuộn trong khung để tiêu đề cột không trôi mất khi lướt."""
    import importlib
    mod = importlib.import_module(f"app.ui.pages.{trang}")
    grid = _tim(mod.layout(), id_bang)
    opts = grid.dashGridOptions
    # "normal" = cuộn trong khung; hoặc chia trang thì cũng không bao giờ dài quá màn hình
    assert opts.get("domLayout", "normal") == "normal" or opts.get("pagination")
    assert int(grid.style["height"].replace("px", "")) <= cao_toi_da


@pytest.mark.parametrize("trang, id_loc", [
    ("tongquan", "tq-cn"), ("tracking", "tk-cn"), ("hr", "hr-cn"), ("chatluong", "cl-cn"),
])
def test_thanh_loc_dinh_tren_dau_trang(trang, id_loc):
    """Thanh lọc kỳ + chi nhánh phải dính lại khi cuộn (class loc-trang)."""
    import importlib
    mod = importlib.import_module(f"app.ui.pages.{trang}")
    goc = mod.layout()
    assert _co_class(goc, "loc-trang"), f"{trang}: thiếu thanh lọc dính"
    assert _tim(goc, id_loc) is not None


def _co_class(node, ten_class: str) -> bool:
    if ten_class in (getattr(node, "className", "") or ""):
        return True
    con = getattr(node, "children", None)
    if con is None or isinstance(con, str):
        return False
    return any(_co_class(c, ten_class)
               for c in (con if isinstance(con, (list, tuple)) else [con]))


def test_bieu_do_xem_duoc_theo_bay_va_theo_phong():
    from app.ui.pages.tracking import layout
    seg = _tim(layout(), "tk-nhom")
    assert [c.value for c in seg.children] == ["bay", "phong"]


# ------------------------------------------------------ Báo cáo Tổng (bản sắp xếp lại)
@pytest.mark.parametrize("cn, ten", [("all", "TỔNG TOÀN CHI NHÁNH"), ("DNG", "TỔNG ĐÀ NẴNG"),
                                     ("QNM", "TỔNG QUẢNG NAM")])
def test_dong_tong_doi_ten_theo_chi_nhanh(cn, ten):
    from app.org import loc_chi_nhanh
    from app.overview import bang_tong_quan
    df, _ = bang_tong_quan(THANG, chi_phong=loc_chi_nhanh(None, cn, THANG), chi_nhanh=cn)
    assert df.iloc[-1]["phong"] == ten


def test_ngay_dang_cap_nhat_ghi_chua_dat_thay_vi_khong_dat():
    from app.overview import bang_tong_quan
    chot, _ = bang_tong_quan(THANG, 11)
    tam, _ = bang_tong_quan(THANG, 11, tam_tinh=True)
    assert "Chưa đạt" not in set(chot.ket_luan)
    assert set(tam.ket_luan) - {"Đạt", "—"} <= {"Chưa đạt"}
    # chỉ đổi chữ, không đổi số
    assert chot.online.tolist() == tam.online.tolist()


def test_dien_thoai_khong_thu_nho_qua_muc_doc_duoc():
    from app.ui.pages.tongquan import TY_LE_TOI_THIEU_DT, _cols, ty_le_vua_man_hinh
    for gon in (True, False):
        assert ty_le_vua_man_hinh(_cols(THANG, 11, gon), {"w": 375}) >= TY_LE_TOI_THIEU_DT


def test_bao_cao_tong_co_chu_giai_mau_va_trang_thai_so_lieu():
    from app.ui.pages.tongquan import layout
    goc = layout()
    for id_ in ("tq-canh-bao", "tq-xem-chot", "tq-cot", "tq-nho", "tq-to", "tq-png", "tq-xls"):
        assert _tim(goc, id_) is not None, id_
    assert _co_class(goc, "chu-giai")
    assert _tim(goc, "tq-export") is None          # bỏ nút CSV


def test_anh_png_ghi_ro_pham_vi_va_so_tam_tinh():
    from datetime import datetime
    from app.export_png import anh_tong_quan
    from app.org import loc_chi_nhanh
    noi_dung, ten = anh_tong_quan(THANG, 11, chi_phong=loc_chi_nhanh(None, "QNM", THANG),
                                  chi_nhanh="QNM", tam_tinh=True, luc=datetime(2026, 9, 11, 15, 38))
    assert noi_dung[:8] == b"\x89PNG\r\n\x1a\n" and ten == "BaoCaoTong_QuangNam_202609_ngay11.png"


def test_tieu_de_cot_khong_bi_cat_ngang_tu():
    """Mọi bảng: tiêu đề chỉ xuống dòng giữa các từ, cột hẹp thì tự nới (assets/khong_rot_chu.js)."""
    from pathlib import Path
    goc = Path(__file__).resolve().parent.parent / "assets"
    css = (goc / "style.css").read_text(encoding="utf-8")
    assert "word-break: keep-all" in css
    js = (goc / "khong_rot_chu.js").read_text(encoding="utf-8")
    assert "setColumnWidths" in js and ".ag-theme-ftel" in js


def test_moi_bang_deu_cho_boi_den_va_copy():
    """AG Grid mặc định chặn chọn chữ trong ô - app bật lại ở app/ui/components.py."""
    import dash_ag_grid as dag

    from app.ui.pages import chatluong
    from app.ui.viet_hoa import viet_hoa
    viet_hoa()

    def cac_bang(node):
        if isinstance(node, (list, tuple)):
            for x in node:
                yield from cac_bang(x)
            return
        if getattr(node, "dashGridOptions", None) is not None:
            yield node
        con = getattr(node, "children", None)
        if con is not None:
            yield from cac_bang(con)

    assert dag.AgGrid(id="x").dashGridOptions["enableCellTextSelection"] is True
    bang = list(cac_bang(chatluong.layout()))
    assert bang and all(b.dashGridOptions.get("enableCellTextSelection") for b in bang)



def test_ma_nv_luon_du_8_so():
    from app.ui.components import MA_NV, ma_nv_hien
    assert ma_nv_hien(56966) == "00056966" and ma_nv_hien("172290") == "00172290"
    assert ma_nv_hien(None) == "" and ma_nv_hien("abc") == "abc"
    assert "padStart(8, '0')" in MA_NV["function"]
