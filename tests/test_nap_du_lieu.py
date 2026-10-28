"""Kiểm thử đường nạp dữ liệu: ghi hàng loạt (executemany) và chỉ đọc file một lần.

Hai chỗ này được sửa ngày 27/09/2026 để rút thời gian nạp file cuối tháng (file luỹ kế
cả tháng ~5.000 dòng). Con số ghi ra phải không đổi so với cách cũ, nên các phép kiểm ở
đây bám vào KẾT QUẢ (thêm mới / cập nhật / giá trị từng cột), không bám vào tốc độ.
"""
from __future__ import annotations

import base64
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import DATA_DIR                                        # noqa: E402

pytestmark = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(),
                                reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")

MA = "KIEMTHU_UPSERT_"


def _don_dep(s):
    from sqlalchemy import delete
    from app.models import FactInternet
    s.execute(delete(FactInternet).where(FactInternet.hop_dong.like(f"{MA}%")))


def _dong(i: int, **doi):
    return {"hop_dong": f"{MA}{i}", "acc_nhan_vien": "DNG.Test1", "acc_norm": "dng.test1",
            "phong_code": "IBB7", "ngay_online": date(2026, 9, 5), "goi_dich_vu": "Goi A", **doi}


# ------------------------------------------------------- ghi hàng loạt (executemany)
def test_upsert_dem_dung_them_moi_va_cap_nhat():
    from app.db import session_scope
    from app.ingest.commit import _upsert
    from app.models import FactInternet
    with session_scope() as s:
        _don_dep(s)
        new, upd = _upsert(s, FactInternet, [_dong(i) for i in range(3)], "hop_dong")
        assert (new, upd) == (3, 0)
    with session_scope() as s:
        # 3 dòng cũ + 2 dòng mới: phải đếm đúng 2 thêm mới, 3 cập nhật
        new, upd = _upsert(s, FactInternet, [_dong(i) for i in range(5)], "hop_dong")
        assert (new, upd) == (2, 3)
        _don_dep(s)


def test_upsert_ghi_de_gia_tri_cu():
    """Nạp lại cùng hợp đồng với giá trị mới thì giá trị trong database phải đổi theo."""
    from sqlalchemy import select
    from app.db import session_scope
    from app.ingest.commit import _upsert
    from app.models import FactInternet
    with session_scope() as s:
        _don_dep(s)
        _upsert(s, FactInternet, [_dong(0, goi_dich_vu="Goi A")], "hop_dong")
    with session_scope() as s:
        _upsert(s, FactInternet, [_dong(0, goi_dich_vu="Goi B")], "hop_dong")
    with session_scope() as s:
        r = s.execute(select(FactInternet).where(FactInternet.hop_dong == f"{MA}0")).scalar_one()
        assert r.goi_dich_vu == "Goi B"
        _don_dep(s)


def test_upsert_chay_duoc_khi_cac_dong_khong_cung_bo_cot():
    """executemany đòi mọi dòng cùng bộ cột. Dòng thiếu cột phải được điền đủ, không nổ lỗi."""
    from sqlalchemy import select
    from app.db import session_scope
    from app.ingest.commit import _upsert
    from app.models import FactInternet
    rong = {"hop_dong": f"{MA}9", "acc_nhan_vien": "DNG.Test1"}     # thiếu hẳn các cột khác
    with session_scope() as s:
        _don_dep(s)
        new, upd = _upsert(s, FactInternet, [_dong(0), rong], "hop_dong")
        assert (new, upd) == (2, 0)
    with session_scope() as s:
        r = s.execute(select(FactInternet).where(FactInternet.hop_dong == f"{MA}9")).scalar_one()
        assert r.acc_nhan_vien == "DNG.Test1" and r.goi_dich_vu is None
        _don_dep(s)


def test_upsert_chia_lo_van_ra_dung_so_dong():
    """Số dòng lớn hơn một lô (CHUNK) vẫn phải vào đủ."""
    from sqlalchemy import func, select
    from app.db import session_scope
    from app.ingest import commit as C
    from app.models import FactInternet
    n = C.CHUNK + 50
    with session_scope() as s:
        _don_dep(s)
        new, upd = C._upsert(s, FactInternet, [_dong(i) for i in range(n)], "hop_dong")
        assert (new, upd) == (n, 0)
    with session_scope() as s:
        co = s.execute(select(func.count()).select_from(FactInternet)
                       .where(FactInternet.hop_dong.like(f"{MA}%"))).scalar_one()
        assert co == n
        _don_dep(s)


# ------------------------------------------------------- chỉ đọc file một lần
def _file_thu(tmp_path: Path) -> tuple[Path, str]:
    """File Internet thật thu nhỏ (lấy từ database kiểm thử) - trả về (đường dẫn, nội dung base64).

    Dựng từ dữ liệu thật để `load_file` nhận diện được đúng loại và cho ok=True, thay vì
    một file bịa ra sẽ trượt ngay ở bước kiểm cột.
    """
    from sqlalchemy import text
    from app.config import columns_config
    from app.db import engine
    df = pd.read_sql(text("SELECT * FROM fact_internet LIMIT 20"), engine)
    if df.empty:
        pytest.skip("Database kiểm thử chưa có dữ liệu Internet")
    ten = {c["field"]: c["ten"][0] for c in columns_config()["datasets"]["internet"]["cot"]}
    ra = pd.DataFrame({v: (df[k].astype(str) if k in df.columns else "x") for k, v in ten.items()})
    p = tmp_path / "Internet thu.xlsx"
    ra.to_excel(p, index=False)
    return p, "data:x;base64," + base64.b64encode(p.read_bytes()).decode()


def test_luu_tam_cung_noi_dung_ra_cung_duong_dan(tmp_path):
    """Lúc xem trước và lúc lưu ghi ra cùng một file tạm, không ghi hai bản."""
    from app.ui.pages import upload as U
    _, noi_dung = _file_thu(tmp_path)
    a = U._luu_tam("Internet thu.xlsx", noi_dung)
    b = U._luu_tam("Internet thu.xlsx", noi_dung)
    assert a == b and a.exists()


def test_luu_dung_lai_ket_qua_da_doc_luc_xem_truoc(tmp_path):
    from app.ui.pages import upload as U
    p, _ = _file_thu(tmp_path)
    from app.ingest.loader import load_file
    goc = load_file(p)
    U._nho_ket_qua(p, goc)
    _, lay = U._doc_mot_lan(p)
    assert lay is goc, "phải lấy lại đúng kết quả cũ, không đọc file lần nữa"


def test_khong_co_san_thi_van_doc_lai_duoc(tmp_path):
    """Trên Vercel hai thao tác có thể rơi vào hai máy chủ khác nhau: phải tự đọc lại."""
    from app.ui.pages import upload as U
    p, _ = _file_thu(tmp_path)
    U._DA_DOC.clear()
    ma, kq = U._doc_mot_lan(p)
    assert ma and [r for r in kq if r.ok], "không có sẵn thì phải đọc lại được từ file"


def test_chi_giu_lai_vai_file_de_khong_phinh_bo_nho(tmp_path):
    from app.ui.pages import upload as U
    U._DA_DOC.clear()
    for i in range(U._GIU_TOI_DA + 3):
        p = tmp_path / f"f{i}.xlsx"
        pd.DataFrame({"a": [1]}).to_excel(p, index=False)
        U._nho_ket_qua(p, [])
    assert len(U._DA_DOC) <= U._GIU_TOI_DA



def test_nap_file_pheu_ban_hang_hai_dong_tieu_de(tmp_path):
    """File Phễu bán hàng có tiêu đề gộp 2 dòng: phải đọc đúng, lưu vào DB và tính đúng 5 tầng."""
    from sqlalchemy import delete
    from app import pheu_ban_hang as pbh
    from app.db import session_scope
    from app.ingest.commit import commit_result, file_hash
    from app.ingest.loader import load_file
    from app.models import FactPheu, UploadBatch

    dong = [
        ["Danh sách khách hàng chưa chuyển đổi theo từng đơn vị"] + [""] * 12,
        ["STT", "Đơn vị", "Thu thập", "", "Liên hệ", "", "Tư vấn", "", "Lên đơn", "", "Hoàn tất", "", "Khách chăm sóc hiện có"],
        ["", "", "Chuyển đổi", "Chưa chuyển đổi", "Chuyển đổi", "Chưa chuyển đổi", "Chuyển đổi", "Chưa chuyển đổi",
         "Chuyển đổi", "Chưa chuyển đổi", "Chuyển đổi", "Chưa chuyển đổi", ""],
        [1, "ZZ_DNGB1", 100, 50, 60, 40, 30, 30, 20, 10, 15, 5, 15],
        [2, "ZZ_DNGB7", 200, 100, 120, 80, 90, 30, 70, 20, 50, 20, 50],
    ]
    p = tmp_path / "Pheu_thu.xlsx"
    pd.DataFrame(dong).to_excel(p, index=False, header=False)
    kq = load_file(p)
    assert len(kq) == 1 and kq[0].dataset == "pheu_ban_hang" and kq[0].rows_valid == 2
    with session_scope() as s:
        st = commit_result(s, kq[0], nguon_file=p.name, hash_file=file_hash(p), user="zz_test_pheu")
        assert st["them_moi"] == 2 and st["cap_nhat"] == 0
    try:
        df = pbh.bang_pheu()
        sub = df[df["don_vi"].isin(["ZZ_DNGB1", "ZZ_DNGB7"])]
        tang = pbh.tinh_pheu(sub)
        assert [t["tong"] for t in tang] == [450, 300, 180, 120, 90]
        assert [t["ty_le"] for t in tang] == [None, 66.67, 60.0, 66.67, 75.0]
    finally:
        with session_scope() as s:
            s.execute(delete(FactPheu).where(FactPheu.don_vi.like("ZZ_%")))
            s.execute(delete(UploadBatch).where(UploadBatch.uploaded_by == "zz_test_pheu"))
