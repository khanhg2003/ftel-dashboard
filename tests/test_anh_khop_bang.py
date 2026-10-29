"""Ảnh PNG phải khớp 100% bảng trên màn hình (Báo cáo Tổng và Báo cáo phòng).

Cách kiểm: dựng cấu hình cột ag-grid mà trang gửi cho trình duyệt (valueFormatter, cellStyle, màu dòng), CHẠY
đúng các đoạn JavaScript đó bằng Node cho từng ô, rồi so với chữ + màu nền + màu chữ + đậm mà ảnh sẽ vẽ
(`luoi_tong_quan`, `luoi_phong`). Sửa bảng trên web mà quên ảnh (hoặc ngược lại) thì test đỏ ngay.

Ngoại lệ có chủ ý, không so: dấu ⓘ trong tiêu đề cột (chỉ để rê chuột), nền xen kẽ #FCFDFE của hàng lẻ (gần
như trắng), căn lề số (web căn phải ở Báo cáo phòng, ảnh căn giữa), và chế độ "Gọn" của Báo cáo Tổng (chỉ dành
cho điện thoại; ảnh luôn đủ cột).
"""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from app import bao_cao_phong as bp
from app import cot_phong as cp
from app import export_phong as ep
from app import export_png as epng
from app.config import DATA_DIR
from app.overview import bang_tong_quan

THANG, NGAY = "2026-09", 11
pytestmark = [pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(), reason="Chưa dựng được database kiểm thử"),
              pytest.mark.skipif(shutil.which("node") is None, reason="Không có Node để chạy đoạn JS của bảng")]

MA_NODE = r"""
const inp = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const f = (e) => new Function('params', 'return (' + e + ')');
const khop = (dks, p) => { for (const c of dks) { if (f(c.condition)(p)) return c.style; } return {}; };
const rs = inp.row_style ? inp.row_style.styleConditions : [];
const kq = inp.rows.map((r) => inp.cols.map((c) => {
  const p = {value: r.data[c.field], data: r.data, node: {rowPinned: r.ghim}};
  let t = c.valueFormatter ? f(c.valueFormatter.function)(p) : p.value;
  const cs = c.cellStyle ? (c.cellStyle.styleConditions ? khop(c.cellStyle.styleConditions, p) : c.cellStyle) : {};
  const st = Object.assign({}, khop(rs, p), cs);
  return {chu: t == null ? '' : String(t), nen: st.backgroundColor || null, mau: st.color || null,
          dam: parseInt(st.fontWeight || '400', 10) >= 600};
}));
process.stdout.write(JSON.stringify(kq));
"""


def _sach(v):
    return None if v != v else v          # NaN -> None


def _json_dong(r: dict) -> dict:
    return {k: (_sach(v.item() if hasattr(v, "item") else v)) for k, v in r.items()}


def _la(cols: list[dict], nhom: str = "") -> list[tuple[str, dict]]:
    """Làm phẳng cột ag-grid thành [(tên nhóm, cột lá)]."""
    ra = []
    for c in cols:
        if "children" in c:
            ra += _la(c["children"], c["headerName"])
        else:
            ra.append((nhom, c))
    return ra


def _chay_js(cols: list[dict], rows: list[tuple[dict, bool]], row_style: dict) -> list[list[dict]]:
    vao = {"cols": [{"field": c["field"], "valueFormatter": c.get("valueFormatter"), "cellStyle": c.get("cellStyle")}
                    for c in cols],
           "rows": [{"data": _json_dong(d), "ghim": g} for d, g in rows], "row_style": row_style}
    kq = subprocess.run([shutil.which("node"), "-e", MA_NODE], input=json.dumps(vao, default=str),
                        capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert kq.returncode == 0, kq.stderr
    return json.loads(kq.stdout)


def _chu_xanh_tu_css(ghim: bool, web: dict, c: dict) -> dict:
    """Tên nhân sự (dòng thường) đổi sang chữ xanh bằng CSS `ngan_nhan_su.lop`, không nằm trong cấu hình cột."""
    if c["field"] == "ho_ten" and not ghim:
        return {**web, "mau": "#" + cp.MAU_TEN}
    return web


def _so_o(web: dict, anh: dict, ve: str):
    assert web["chu"] == anh["chu"], f"{ve}: chữ web {web['chu']!r} ≠ ảnh {anh['chu']!r}"
    assert (web["nen"] or "").upper() == (anh["nen"] or "").upper(), f"{ve} {web['chu']!r}: nền web {web['nen']} ≠ ảnh {anh['nen']}"
    assert (web["mau"] or epng.CHU_THUONG).upper() == anh["mau_chu"].upper(), \
        f"{ve} {web['chu']!r}: màu chữ web {web['mau']} ≠ ảnh {anh['mau_chu']}"
    assert web["dam"] == anh["dam"], f"{ve} {web['chu']!r}: đậm web {web['dam']} ≠ ảnh {anh['dam']}"


# ------------------------------------------------------------------ Báo cáo Tổng
CA_TONG = [("all", None, False), ("DNG", None, False), ("QNM", None, False), ("all", "2026-09-03", False),
           ("all", None, True)]


@pytest.mark.parametrize("chi_nhanh,tu,tam_tinh", CA_TONG)
def test_anh_tong_quan_khop_bang_web(chi_nhanh, tu, tam_tinh):
    from app.org import loc_chi_nhanh
    from app.ui.pages import tongquan as tq
    scope = loc_chi_nhanh(None, chi_nhanh, THANG)
    df, ngay = bang_tong_quan(THANG, NGAY, chi_phong=scope, chi_nhanh=chi_nhanh, tam_tinh=tam_tinh, tu=tu)
    web_cols = _la(tq._cols(THANG, ngay, gon=False, tu=tu))
    anh = epng.luoi_tong_quan(THANG, NGAY, scope, chi_nhanh, tam_tinh, tu)

    # cùng cột, cùng thứ tự, cùng tiêu đề, cùng nhóm
    ten_web = [(n, c["field"], c["headerName"].replace(" ⓘ", "")) for n, c in web_cols]
    ten_anh = [(n, k, t) for n, nhom in anh["ct"] for t, k, _ in nhom]
    assert ten_web == ten_anh

    rows = df.to_dict("records")
    kq = _chay_js([c for _, c in web_cols], [(r, False) for r in rows], tq.ROW_STYLE)
    assert len(kq) == len(anh["dong"]) == len(rows)
    for i, (dong_web, dong_anh) in enumerate(zip(kq, anh["dong"])):
        for (_, c), w, a in zip(web_cols, dong_web, dong_anh["o"]):
            _so_o(w, a, f"{rows[i]['phong']} / {c['field']}")


# ------------------------------------------------------------------ Báo cáo phòng
def _web_phong(thang, ngay, nv, che_do, chi_chu_y):
    from app.ui.pages import phong as pg
    rows, tong = cp.dong_nhan_su(nv, chi_chu_y)
    cols = _la(pg._cot_nv(thang, ngay, tong, che_do))
    kq = _chay_js([c for _, c in cols], [(r, False) for r in rows] + [(tong, True)], pg.ROW_STYLE)
    return cols, rows, kq


def _kiem_phong(code, che_do, chi_chu_y=False):
    anh = ep.luoi_phong(THANG, NGAY, code, che_do, chi_chu_y)
    nv = bp.bang_nhan_su(THANG, NGAY, code)
    cols, rows, kq = _web_phong(THANG, NGAY, nv, anh["che_do"], chi_chu_y)
    # cùng cột, thứ tự, tiêu đề, nhóm
    assert [(n, c["field"], c["headerName"]) for n, c in cols] == [(n, c.field, c.ten) for n, _, c in anh["cot"]]
    assert len(kq) == len(anh["dong"]) == len(rows) + 1
    for i, (dong_web, dong_anh) in enumerate(zip(kq, anh["dong"])):
        ten = "TỔNG" if i == len(rows) else rows[i].get("ho_ten")
        for (_, c), w, a in zip(cols, dong_web, dong_anh["o"]):
            _so_o(_chu_xanh_tu_css(i == len(rows), w, c), a, f"{code}/{che_do}/{ten}/{c['field']}")
    return anh, rows


@pytest.mark.parametrize("code", ["IBB7", "IBB2", "HOIAN"])         # có MTTN · phòng IBB thường · địa bàn
@pytest.mark.parametrize("che_do", ["ban_hang", "theo_doi", "tat_ca"])
def test_anh_phong_khop_bang_web(code, che_do):
    anh, _ = _kiem_phong(code, che_do)
    assert ("mttn" in [k for _, k, _ in anh["cot"]]) == (code == "IBB7" and che_do != "theo_doi")


def test_anh_phong_loc_chi_nguoi_can_chu_y_khop_bang_web():
    anh, rows = _kiem_phong("IBB2", "ban", chi_chu_y=True)
    assert rows and all(r["muc_chu_y"] for r in rows) and len(anh["dong"]) == len(rows) + 1


def test_anh_phong_truong_phong_hien_tp_o_cuoi(monkeypatch):
    nv = bp.bang_nhan_su(THANG, NGAY, "IBB2").copy()
    nv.loc[0, "khong_xet"] = "Trưởng phòng"
    nv.loc[0, "hang"] = None
    monkeypatch.setattr(bp, "bang_nhan_su", lambda *a, **k: nv)
    anh = ep.luoi_phong(THANG, NGAY, "IBB2", "ban")
    cols, rows, kq = _web_phong(THANG, NGAY, nv, "ban", False)
    assert rows[-1]["hang"] == cp.HANG_TP and anh["dong"][len(rows) - 1]["o"][0]["chu"] == "TP"
    for i, (dong_web, dong_anh) in enumerate(zip(kq, anh["dong"])):
        for (_, c), w, a in zip(cols, dong_web, dong_anh["o"]):
            _so_o(_chu_xanh_tu_css(i == len(rows), w, c), a, "TP")


def test_mau_ten_nhan_su_co_trong_css():
    assert cp.MAU_TEN.upper() in (epng.THU_MUC_FONT.parent / "style.css").read_text(encoding="utf-8").upper()


def test_anh_phong_the_tom_tat_cung_nguon_voi_trang():
    """Thẻ đầu trang: web (`phong._kpis`) và ảnh cùng lấy từ `cot_phong.the_tom_tat`."""
    from app.ui.pages import phong as pg
    anh = ep.luoi_phong(THANG, NGAY, "IBB7", "ban")
    ss, dong = bp.so_sanh_phong(THANG, NGAY, "IBB7", False)
    the_web = pg._kpis(THANG, NGAY, "IBB7", dong, ss, False)
    assert len(the_web) == len(anh["the"]) == 7
    for kpi, t in zip(the_web, anh["the"]):
        label, value, hint = (x.children for x in kpi.children)
        assert (label, value, hint) == (t.nhan, t.gia_tri, t.phu)
        assert kpi.className == f"kpi {t.tt}".strip()


def test_ve_anh_ba_che_do_va_dat_ten_file():
    import io

    from PIL import Image
    for che_do, hau in (("ban_hang", ""), ("theo_doi", "_theodoi"), ("tat_ca", "_tatca")):
        png, ten = ep.anh_bao_cao_phong(THANG, NGAY, "IBB7", che_do=che_do)
        assert ten == f"BaoCaoPhong_IBB7_202609_ngay11{hau}.png"
        assert Image.open(io.BytesIO(png)).width > 1500
    assert ep.anh_bao_cao_phong(THANG, NGAY, "IBB7")[1] == "BaoCaoPhong_IBB7_202609_ngay11.png"   # mặc định = Bán hàng


def test_excel_phong_van_dung_luat_mau_chung():
    """Excel vẫn tô màu bốn cột cũ, nay lấy luật từ cot_phong (cùng ngưỡng với web)."""
    tong = {"kem_vvip": 50.0}
    assert ep.mau_o("kem_vvip", 60, tong) == cp.XANH[0] and ep.mau_o("kem_vvip", 44, tong) == cp.VANG[0]
    assert ep.mau_o("kem_vvip", 30, tong) == cp.DO[0] and ep.mau_o("kem_vvip", 52, tong) is None
    assert ep.mau_o("ton_qua_7", 3, {}) == cp.DO[0] and ep.mau_o("ton_qua_7", 1, {}) == cp.VANG[0]
    assert ep.mau_o("ton_qua_7", 0, {}) is None and ep.mau_o("online", 5, tong) is None
