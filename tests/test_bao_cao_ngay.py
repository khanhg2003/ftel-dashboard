"""Kiểm thử Báo cáo đầu ngày (chốt với chủ app 24/09/2026)."""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import bao_cao_ngay as bc                                      # noqa: E402
from app.config import DATA_DIR                                          # noqa: E402

pytestmark = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(),
                                reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")
NGAY = date(2026, 9, 10)          # nằm trong kỳ dữ liệu gốc 01-11/09/2026
PHONG = ["IBB7"]


def _tk(role: str, scope: list[str]):
    from app.auth import SessionUser
    return SessionUser(SimpleNamespace(id=1, username=f"kiemthu.{role}", ho_ten="Kiểm thử", role=role,
                                       ma_nv=None, session_version=0, scope=json.dumps(scope)))


@pytest.fixture(autouse=True)
def _don_ngay_thu():
    """Xoá số đã nhập của ngày kiểm thử trước mỗi phép thử - database kiểm thử dùng lại qua nhiều lần chạy,
    còn sót dữ liệu cũ thì "chưa nhập" và "đã nhập số 0" không phân biệt được nữa."""
    from sqlalchemy import delete
    from app.db import session_scope
    from app.models import BaoCaoNgay, BaoCaoNgayChu
    bc.dam_bao_bang()
    with session_scope() as s:
        s.execute(delete(BaoCaoNgay).where(BaoCaoNgay.ngay == NGAY))
        s.execute(delete(BaoCaoNgayChu).where(BaoCaoNgayChu.ngay == NGAY))


@pytest.fixture()
def mot_nguoi():
    bc.dam_bao_bang()
    df = bc.bang(PHONG, NGAY)
    assert not df.empty, "phòng IBB7 phải có số trong kỳ kiểm thử"
    return df.iloc[0].acc_norm


# ------------------------------------------------------------------ số liệu
def test_sale_chi_nhap_5_o_con_lai_app_tu_lay(mot_nguoi):
    """Chủ app chốt: sale nhập mục tiêu / KHTN / ONL sáng / ONL chiều / ghi chú, còn lại app tự tính."""
    bc.luu(mot_nguoi, {"muc_tieu": 2, "khtn": 3, "onl_sang": 1, "onl_chieu": 2, "ghi_chu": "Care KHTN cũ"},
           PHONG, "kiemthu.tp", NGAY)
    r = bc.bang(PHONG, NGAY).set_index("acc_norm").loc[mot_nguoi]
    assert (r.muc_tieu, r.khtn, r.onl_sang, r.onl_chieu) == (2, 3, 1, 2)
    assert r.dk_onl == 3                                  # dự kiến tổng = sáng + chiều, không nhập riêng
    assert r.con_phai_onl == 3 - r.thuc_hien
    assert r.pttb_thang >= 0 and r.vvip_thang >= 0        # app tự lấy từ file Internet
    assert r.da_nhap


def test_chua_nhap_thi_khac_voi_nhap_so_0(mot_nguoi):
    """Ô trống (chưa báo cáo) phải phân biệt được với số 0 thật, nếu không trưởng phòng không biết ai thiếu."""
    df = bc.bang(PHONG, NGAY)
    chua = df[df.acc_norm != mot_nguoi].iloc[0]
    assert not chua.da_nhap and chua.khtn == 0
    bc.luu(chua.acc_norm, {"muc_tieu": 0, "khtn": 0, "onl_sang": 0, "onl_chieu": 0}, PHONG, "kiemthu.tp", NGAY)
    r = bc.bang(PHONG, NGAY).set_index("acc_norm").loc[chua.acc_norm]
    assert r.da_nhap and r.khtn == 0


def test_tom_tat_ba_khoi_khop_voi_bang():
    bc.luu(bc.bang(PHONG, NGAY).iloc[0].acc_norm, {"khtn": 4, "onl_sang": 2, "onl_chieu": 1},
           PHONG, "kiemthu.tp", NGAY)
    df, t = bc.bang(PHONG, NGAY), bc.tom_tat(PHONG, NGAY)
    assert t["khtn"] == int(df.khtn.sum()) and t["dk_onl"] == int(df.dk_onl.sum())
    assert t["dk_onl"] == t["onl_sang"] + t["onl_chieu"]
    assert t["hom_qua"] == NGAY - timedelta(days=1)
    assert t["con_thieu"] == max(t["mt_thang"] - t["luy_ke"], 0)
    assert t["luy_ke"] == int(df.pttb_thang.sum())        # luỹ kế phòng = tổng luỹ kế từng người


def test_da_online_sale_go_tay_duoc(mot_nguoi):
    """File Internet chỉ về vào hôm sau nên buổi sáng số từ file luôn 0; sale phải gõ tay được thì
    "còn phải online" mới có nghĩa. Hiển thị lấy số LỚN HƠN giữa số gõ tay và số từ file."""
    tu_file = int(bc.bang(PHONG, NGAY).set_index("acc_norm").at[mot_nguoi, "thuc_hien"])

    bc.luu(mot_nguoi, {"onl_sang": 3, "onl_chieu": 2, "da_online": tu_file + 2},
           PHONG, "kiemthu.tp", NGAY)
    r = bc.bang(PHONG, NGAY).set_index("acc_norm").loc[mot_nguoi]
    assert int(r.thuc_hien) == tu_file + 2                      # số gõ tay lớn hơn thì dùng số gõ tay
    assert int(r.con_phai_onl) == 5 - (tu_file + 2)             # còn phải online tính theo số đó

    bc.luu(mot_nguoi, {"da_online": 0}, PHONG, "kiemthu.tp", NGAY)
    r = bc.bang(PHONG, NGAY).set_index("acc_norm").loc[mot_nguoi]
    assert int(r.thuc_hien) == tu_file                          # file không đếm dư nên không tụt xuống


def test_thuc_hien_la_o_sale_tu_nhap(mot_nguoi):
    """Cột "Thực hiện" (thêm 26/09/2026) là ô sale TỰ NHẬP, không lấy gì từ file: chủ app chốt đây
    là số khai báo của sale để đối chiếu với ô "MT ngày" của chính họ."""
    assert int(bc.bang(PHONG, NGAY).da_ban.sum()) == 0        # chưa ai nhập thì bằng 0, kể cả ngày có bán

    bc.luu(mot_nguoi, {"da_ban": 4}, PHONG, "kiemthu.tp", NGAY)
    assert int(bc.bang(PHONG, NGAY).set_index("acc_norm").at[mot_nguoi, "da_ban"]) == 4

    bc.luu(mot_nguoi, {"da_ban": 0}, PHONG, "kiemthu.tp", NGAY)        # sửa về 0 thì phải nhận 0
    assert int(bc.bang(PHONG, NGAY).set_index("acc_norm").at[mot_nguoi, "da_ban"]) == 0


def test_vvip_dem_giong_bao_cao_phong():
    """Số V.VIP phải đếm từ file FPT Play (mỗi dòng la_vvip là một V.VIP, theo ngày online của
    chính gói đó) - KHÔNG đếm gián tiếp qua cờ V.VIP của hợp đồng Internet, vì gói V.VIP có thể
    online khác ngày hoặc bán thêm trên hợp đồng tháng trước."""
    import pandas as pd
    from app import bao_cao_phong as bp

    df = bc.bang(PHONG, NGAY)
    phong = bp.bang_nhan_su(f"{NGAY:%Y-%m}", NGAY.day, PHONG[0])
    phong = phong[phong.acc_norm.notna() & (phong.acc_norm != "TOTAL")]

    assert int(df.vvip_thang.sum()) == int(phong.vvip.sum())      # tổng phòng khớp
    a = df.set_index("acc_norm").vvip_thang
    b = phong.set_index("acc_norm").vvip
    chung = pd.DataFrame({"a": a, "b": b}).fillna(0).astype(int)
    assert (chung.a == chung.b).all()                             # từng người cũng khớp


def test_nhap_truoc_cho_ngay_tuong_lai(mot_nguoi):
    """Sale hay điền trước cho hôm sau (chốt 26/09/2026): mở và lưu được báo cáo của ngày chưa tới,
    nhưng chỉ trong TRUOC_TOI_DA ngày để không ai gõ nhầm sang tháng khác."""
    from datetime import timedelta
    from sqlalchemy import delete
    from app.db import session_scope
    from app.models import BaoCaoNgay
    from app.ui.pages.baocaongay import _ngay_hop_le

    mai = bc.hom_nay() + timedelta(days=1)
    assert _ngay_hop_le(mai.isoformat()) == mai                      # ngày mai: mở được
    qua_xa = bc.hom_nay() + timedelta(days=bc.TRUOC_TOI_DA + 5)
    assert _ngay_hop_le(qua_xa.isoformat()) == bc.ngay_xa_nhat()     # quá xa: kéo về mốc cho phép

    try:
        bc.luu(mot_nguoi, {"muc_tieu": 3, "ghi_chu": "nhập trước"}, PHONG, "kiemthu.tp", mai)
        r = bc.bang(PHONG, mai).set_index("acc_norm").loc[mot_nguoi]
        assert int(r.muc_tieu) == 3 and r.ghi_chu == "nhập trước"
        assert int(r.thuc_hien) == 0        # ngày chưa tới nên chưa có gì online
    finally:
        with session_scope() as s:
            s.execute(delete(BaoCaoNgay).where(BaoCaoNgay.ngay == mai))


def test_con_phai_onl_cong_doc_va_cong_ngang_deu_khop(mot_nguoi):
    """Chủ app chốt 26/09/2026: mọi con số trong bảng phải cộng được cả hai chiều.
    Người online vượt dự kiến để SỐ ÂM, nhờ vậy cộng dọc cột "Còn phải ONL" ra đúng dòng TỔNG,
    và dòng TỔNG vẫn bằng tổng DK ONL trừ tổng Đã online."""
    from sqlalchemy import delete
    from app.db import session_scope
    from app.models import BaoCaoNgay
    from app.ui.pages.baocaongay import _ghim

    df = bc.bang(PHONG, NGAY)
    vuot = df[df.thuc_hien >= 2].iloc[0]           # người đã online nhiều -> cho dự kiến thấp
    thieu = df[df.thuc_hien == 0].iloc[0]          # người chưa online -> cho dự kiến cao
    try:
        bc.luu(vuot.acc_norm, {"onl_sang": 1, "onl_chieu": 0}, PHONG, "kiemthu.tp", NGAY)
        bc.luu(thieu.acc_norm, {"onl_sang": 2, "onl_chieu": 1}, PHONG, "kiemthu.tp", NGAY)
        d = bc.bang(PHONG, NGAY)
        r = d.set_index("acc_norm").loc[vuot.acc_norm]
        assert int(r.con_phai_onl) == 1 - int(r.thuc_hien) < 0      # vượt dự kiến thì để số âm

        t = _ghim(d)[0]
        assert t["con_phai_onl"] == int(d.con_phai_onl.sum())       # cộng dọc khớp
        assert t["con_phai_onl"] == t["dk_onl"] - t["thuc_hien"]    # cộng ngang cũng khớp
        assert bc.tom_tat(PHONG, NGAY)["con_phai_onl"] == t["con_phai_onl"]   # ảnh báo cáo cùng số
    finally:
        with session_scope() as s:
            s.execute(delete(BaoCaoNgay).where(BaoCaoNgay.ngay == NGAY))


def test_don_ngay_cu_giu_hom_nay_va_ngay_nhap_truoc(mot_nguoi):
    """Chốt 26/09/2026: báo cáo của ngày đã qua xoá đi cho nhẹ bảng, chỉ giữ hôm nay và ngày
    nhập trước. Dọn theo NGÀY nên phải giữ nguyên các dòng của hôm nay."""
    from datetime import timedelta
    from sqlalchemy import delete, select
    from app.db import session_scope
    from app.models import BaoCaoNgay

    hn, hqua = bc.hom_nay(), bc.hom_nay() - timedelta(days=1)
    mai = bc.hom_nay() + timedelta(days=1)
    try:
        for d in (hqua, hn, mai):
            bc.luu(mot_nguoi, {"khtn": 1}, PHONG, "kiemthu.tp", d)
        bc._ngay_don = None                      # ép dọn lại trong cùng lần chạy
        bc.don_ngay_cu()
        with session_scope() as s:
            con = {r.ngay for r in s.execute(select(BaoCaoNgay)).scalars()
                   if r.acc_norm == mot_nguoi}
        assert hqua not in con                   # ngày đã qua: xoá
        assert hn in con and mai in con          # hôm nay và ngày nhập trước: giữ
    finally:
        bc._ngay_don = None
        with session_scope() as s:
            for d in (hqua, hn, mai):
                s.execute(delete(BaoCaoNgay).where(BaoCaoNgay.ngay == d))


def test_chan_so_vo_ly(mot_nguoi):
    for xau in (-1, 5000, "abc"):
        with pytest.raises(bc.LoiBaoCao):
            bc.luu(mot_nguoi, {"khtn": xau}, PHONG, "kiemthu.tp", NGAY)


def test_tai_khoan_sale_sua_duoc_moi_dong_va_ghi_dung_ten(mot_nguoi):
    """Chủ app chốt 24/09/2026: tài khoản sale dùng chung full quyền. Ô tên chỉ để ghi "cập nhật bởi"."""
    from sqlalchemy import select
    from app.db import session_scope
    from app.models import BaoCaoNgay
    df = bc.bang(PHONG, NGAY)
    nguoi_khac = df[df.acc_norm != mot_nguoi].iloc[0].acc_norm
    bc.luu(nguoi_khac, {"khtn": 1}, PHONG, "kiemthu.nvkd", NGAY, ghi_ten="Hồ Thị Mỹ Chi")
    bc.luu(mot_nguoi, {"khtn": 2}, PHONG, "kiemthu.nvkd", NGAY)
    with session_scope() as s:
        boi = {r.acc_norm: r.cap_nhat_boi for r in
               s.execute(select(BaoCaoNgay).where(BaoCaoNgay.ngay == NGAY)).scalars()}
    assert boi[nguoi_khac] == "Hồ Thị Mỹ Chi"          # có chọn tên thì ghi tên người đó
    assert boi[mot_nguoi] == "kiemthu.nvkd"            # không chọn thì ghi tên tài khoản


# ------------------------------------------------------------------ mục tiêu
def test_muc_tieu_tung_nguoi_khong_dung_vao_muc_tieu_phong(mot_nguoi):
    """Mục tiêu tháng từng người lưu chung bảng target_monthly nhưng khác `doi_tuong`,
    không được làm lệch mục tiêu phòng của Báo cáo Tổng."""
    thang = f"{NGAY:%Y-%m}"
    truoc = bc.tom_tat(PHONG, NGAY)["mt_thang"]
    bc.dat_muc_tieu(thang, "NHAN_VIEN", mot_nguoi, "internet", 60, "kiemthu.tp")
    assert bc.tom_tat(PHONG, NGAY)["mt_thang"] == truoc
    assert bc.bang(PHONG, NGAY).set_index("acc_norm").loc[mot_nguoi].mt_thang == 60


def test_dong_tong_co_du_so(mot_nguoi):
    """Dòng TỔNG phải mang cờ `da_nhap` / `la_tong`, nếu không quy tắc "chưa nhập thì để ô trống"
    ăn luôn cả dòng tổng (chủ app báo 24/09/2026: bốn ô đầu của dòng TỔNG bị trắng)."""
    from app.ui.pages.baocaongay import _ghim
    bc.luu(mot_nguoi, {"muc_tieu": 2, "khtn": 3, "onl_sang": 1, "onl_chieu": 2}, PHONG, "kiemthu.tp", NGAY)
    df = bc.bang(PHONG, NGAY)
    g = _ghim(df)[0]
    assert g["da_nhap"] is True and g["la_tong"] is True
    assert g["muc_tieu"] == int(df.muc_tieu.sum()) and g["khtn"] == int(df.khtn.sum())
    assert g["onl_sang"] == int(df.onl_sang.sum()) and g["onl_chieu"] == int(df.onl_chieu.sum())
    assert _ghim(df.iloc[0:0]) == []


# ------------------------------------------------------------------ quyền
def test_quyen_theo_phong():
    assert _tk("nvkd", ["IBB7"]).phong_bao_cao_ngay() == ["IBB7"]
    assert _tk("nvkd", ["IBB7"]).duoc_bao_cao_ngay
    assert _tk("nvkd", ["IBB2"]).phong_bao_cao_ngay() == []
    assert _tk("nvkd", ["IBB7"]).vao_duoc("/baocaongay")


def test_tai_khoan_xem_nhieu_phong_khong_vao_bao_cao_ngay():
    """Chủ app chốt 26/09/2026: Nhập tồn và Báo cáo ngày là chỗ NHẬP LIỆU của đúng một phòng.
    Tài khoản được mở rộng xem nhiều phòng (cấp trên, giám sát) tuy có IBB7 trong phạm vi nhưng
    không phải người vận hành phòng đó nên không được vào. Quản trị (BGĐ) vẫn vào được."""
    rong = _tk("phong", ["IBB1", "IBB2", "IBB7"])        # xem nhiều phòng, có cả IBB7
    assert rong.phong_bao_cao_ngay() == [] and not rong.duoc_bao_cao_ngay
    assert rong.phong_nhap_ton() == [] and not rong.duoc_nhap_ton

    tp = _tk("phong", ["IBB7"])                          # Trưởng phòng đúng phòng đó: vẫn vào
    assert tp.duoc_bao_cao_ngay and tp.duoc_nhap_ton
    assert _tk("admin", []).duoc_bao_cao_ngay            # Quản trị (BGĐ) luôn vào được


# ------------------------------------------------------------------ chữ + ảnh
def test_nvkd_bam_duoc_fox_nhung_khong_chat():
    """Chủ app chốt 25/09/2026: tài khoản Nhân viên KD bấm được nút "Fox viết giúp" ở Báo cáo ngày,
    nhưng KHÔNG mở khung chat Hỏi Fox và không bấm được nút nhận xét ở các trang khác."""
    from app import tro_ly as ai
    ch = {**ai.MAC_DINH, "bat": True, "tai_khoan": []}
    sale = SimpleNamespace(role="nvkd", username="ibb7.sale")

    assert ai.duoc_dung(sale, ch, chi_viet=True)                        # nút Fox viết giúp
    assert not ai.duoc_dung(sale, ch)                                   # chat / nhận xét trang khác
    assert not ai.duoc_dung(sale, {**ch, "bat": False}, chi_viet=True)  # AI tắt thì không ai bấm được
    for vt in ("admin", "operator", "phong"):
        assert ai.duoc_dung(SimpleNamespace(role=vt, username=f"kiemthu.{vt}"), ch)

    # qua được cửa quyền thì lỗi tiếp theo phải là thiếu mã API, không phải lỗi quyền
    with pytest.raises(ai.LoiAI, match="mã API"):
        ai.kiem_tra(sale, {**ch, "key": None}, chi_viet=True)


def test_tach_ba_khoi_chu_cua_fox():
    from app.bao_cao_ngay_ai import _tach
    chu = ("TRỌNG TÂM HÔM NAY\n- Bám 18 ca online\n- Chăm 6 KHTN\n"
           "ĐÁNH GIÁ & NHẬN ĐỊNH\n1. Hôm qua 15/25\n2. Luỹ kế 497/700\n"
           "THÔNG ĐIỆP NGÀY MỚI\nCả team cố lên.")
    r = _tach(chu)
    assert r["trong_tam"].splitlines() == ["Bám 18 ca online", "Chăm 6 KHTN"]
    assert r["nhan_dinh"].splitlines() == ["1. Hôm qua 15/25", "2. Luỹ kế 497/700"]
    assert r["thong_diep"] == "Cả team cố lên."
    assert _tach("chỉ một đoạn")["trong_tam"] == "chỉ một đoạn"      # AI quên tiêu đề vẫn không mất chữ


def test_ve_duoc_anh_bao_cao():
    from app.export_png_ngay import anh_bao_cao_ngay
    bc.luu_chu("IBB7", {"trong_tam": "Bám 18 ca online", "nhan_dinh": "Hôm qua 15/25",
                        "thong_diep": "Cả team cố lên."}, "kiemthu.tp", NGAY)
    png = anh_bao_cao_ngay("IBB7", NGAY)
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 20_000
    assert bc.chu("IBB7", NGAY)["thong_diep"] == "Cả team cố lên."


def test_va_dong_phai_hoan_de_giu_duoc_ctrl_z():
    """ag-grid XOÁ SẠCH undo stack mỗi lần nhận transaction (đo 27/09/2026), nên sau khi sale
    sửa một ô thì bảng phải chờ rồi mới làm mới - vá ngay là Ctrl+Z hết tác dụng."""
    from pathlib import Path
    from app.ui.pages import baocaongay as bn
    assert bn.CHO_VA >= 3 and bn.NHIP_VA_MS <= bn.CHO_VA * 1000
    js = (Path(__file__).resolve().parent.parent / "assets" / "lam_lai_o.js").read_text(encoding="utf-8")
    assert "redoCellEditing" in js, "Ctrl+Shift+Z do file này gắn, ag-grid chỉ tự nhận Ctrl+Y"


def test_cong_thuc_trinh_duyet_tu_tinh_khop_voi_cong_thuc_python():
    """DK ONL và Còn phải ONL được tính Ở TRÌNH DUYỆT để đổi ngay lúc gõ (chốt 27/09/2026),
    nhưng ảnh PNG và dòng TỔNG vẫn tính bằng Python. Hai bên PHẢI ra cùng một số.

    Ở đây kiểm số Python thoả đúng công thức mà JavaScript đang dùng - lệch là ảnh gửi nhóm Zalo
    khác với số trên màn hình."""
    from app.ui.pages.baocaongay import CON_PHAI_ONL, DK_ONL
    df = bc.bang(PHONG, NGAY)
    assert not df.empty, "phòng IBB7 phải có số trong kỳ kiểm thử"
    # nhập số thật cho một người, kể cả ca online vượt dự kiến (còn phải ONL âm)
    bc.luu(df.iloc[0].acc_norm, {"onl_sang": 4, "onl_chieu": 3, "da_online": 9},
           PHONG, "kiemthu.tp", NGAY)
    df = bc.bang(PHONG, NGAY)
    for r in df.itertuples():
        assert r.dk_onl == r.onl_sang + r.onl_chieu, f"{r.acc_norm}: DK ONL không bằng sáng + chiều"
        assert r.con_phai_onl == r.dk_onl - r.thuc_hien, f"{r.acc_norm}: còn phải ONL sai"
    # và công thức JS phải đúng ba cột đó, có bọc Number (ô vừa gõ trả về chuỗi: "5" + 0 = "50")
    for js in (DK_ONL["function"], CON_PHAI_ONL["function"]):
        assert js.count("Number(") == js.count("params.data.")
    assert "onl_sang" in DK_ONL["function"] and "onl_chieu" in DK_ONL["function"]
    assert "thuc_hien" in CON_PHAI_ONL["function"] and " - " in CON_PHAI_ONL["function"]


def test_dong_tong_khong_di_qua_dashgridoptions():
    """Dòng TỔNG phải đặt qua `bn-ghim` (trình duyệt gọi setGridOption), KHÔNG qua `dashGridOptions`.

    Gửi qua `dashGridOptions` thì Dash nạp lại trọn gói tuỳ chọn và ag-grid xoá sạch undo stack,
    Ctrl+Z hết tác dụng (đo 27/09/2026). Đổi riêng dòng ghim thì undo còn nguyên."""
    import inspect
    from app.ui.pages import baocaongay as bn
    ma = inspect.getsource(bn.register)
    assert "setGridOption('pinnedBottomRowData'" in ma, "dòng TỔNG phải đặt thẳng ở trình duyệt"
    assert '"dashGridOptions"' not in ma, "đừng gửi dashGridOptions từ máy chủ, sẽ mất Ctrl+Z"
