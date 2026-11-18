"""Trợ lý điều hành liên khối (nhánh thi-lien-khoi): bộ quét -> vấn đề -> bản LUẬT / LLM giả có kiểm số -> đề xuất -> quyết qua Zalo -> nhắc, leo thang -> kiểm chứng.
Trạng thái ở file sqlite tạm; LLM luôn là hàm giả (không gọi mạng)."""
from __future__ import annotations

import json
import re
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
import pytest

from app.lien_khoi import luat, quyet_dinh as qd, theo_doi as td, tro_ly_dieu_hanh as tdh, zalo_lenh as zl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_lien_khoi_quan_ly import NGUOI, T0, _dat, _viec, ql, thu_zalo  # noqa: E402,F401


@pytest.fixture(autouse=True)
def _khong_kt(monkeypatch):
    monkeypatch.setattr(tdh, "_kt_du_lieu", lambda: None)
    monkeypatch.delenv("TRO_LY_DIEU_HANH_TRAN_NGAY", raising=False)


def _team(n: int = 4, **kw) -> None:
    """n việc quá hạn của team tpkd_01 (chỉ phần của sale, không có DVKH / Kỹ thuật)."""
    td.dong_bo(_viec(*[dict(so_hd=f"MHAAA{i:04d}", giao_dvkh="", giao_kt="", **kw) for i in range(1, n + 1)]), T0)


NOW = T0 + timedelta(hours=30)                   # quá hạn 24 giờ của mọi việc giao lúc T0


def _llm_dung(he_thong, nguoi_dung):
    bc = json.loads(nguoi_dung)["bang_su_that"]["bang_chung"]
    return json.dumps({"nhan_dinh": f"Có {bc.get('qua_han', 0)} việc quá hạn, cần xử lý trong ngày.",
                       "phuong_an": [{"ma": "A", "tieu_de": "Họp nhanh với team", "mo_ta": "Quản lý chốt từng việc."}, {"ma": "B", "tieu_de": "Chia lại việc", "mo_ta": "Giao cho người nhẹ việc."}],
                       "khuyen_nghi": "A"}, ensure_ascii=False)


def _van_de():
    vs = tdh.thu_su_that(NOW)
    assert vs, "phải có vấn đề"
    return vs[0]


# ------------------------------------------------------------------ bộ quét và gom vấn đề
def test_quet_ra_van_de_team_qua_han_co_chi_so_va_nguoi_quyet(ql):
    _team(4)
    v = _van_de()
    assert v["loai"] == "qua_han_team" and v["nguoi_quyet"] == "tpkd_01" and v["muc"] == tdh.TB
    assert v["su_that"]["bang_chung"]["qua_han"] == 4 and v["chi_so"]["gia_tri"] == 4 and v["chi_so"]["loai"] == "qua_han_team"
    assert v["ma_van_de"].endswith(":qua_han_team:tpkd_01") and v["su_that"]["duong_dan"].startswith("/lienkhoi?tab=td")
    assert tdh.thu_su_that(T0) == []                                               # chưa quá hạn thì không có vấn đề


def test_ba_viec_quan_ha_chua_toi_nguong_va_chinh_nhanh_ca_mat_cao(ql):
    _team(2)
    assert tdh.thu_su_that(NOW) == []
    _team(9)
    v = tdh.thu_su_that(NOW)
    assert any(x["muc"] == tdh.CAO and x["loai"] == "qua_han_team" for x in v)
    assert any(x["loai"] == "cao_chi_nhanh" and x["nguoi_quyet"] == "gd_01" for x in v)      # việc mức Cao toàn chi nhánh về giám đốc


def test_hang_cho_ve_truong_phong_khoi(ql):
    td.dong_bo(_viec(*[dict(so_hd=f"MHAAA{i:04d}", giao_sale="", giao_kt="", giao_dvkh=luat.GIAO_DVKH) for i in range(1, 7)]), T0)
    v = [x for x in tdh.thu_su_that(T0 + timedelta(hours=1)) if x["loai"] == "hang_cho"]
    assert v and v[0]["nguoi_quyet"] == "tp_dvkh_01" and v[0]["su_that"]["bang_chung"]["hang_cho"] == 6 and v[0]["chi_so"]["loai"] == "hang_cho"


def _kt_gia(gios):
    il = pd.DataFrame([{"so_hd": f"MHKTA{i:04d}", "gio_im_lang": g, "ngay_ton": g / 24} for i, g in enumerate(gios, 1)])
    return lambda: {"ton": il.copy(), "im_lang": il}


def test_kt_im_lang_gom_nhieu_ca_thanh_mot_van_de_va_dong_thap_gop_dong(ql, monkeypatch):
    monkeypatch.setattr(tdh, "_kt_du_lieu", _kt_gia([100, 90, 50, 30, 26]))
    v = tdh.thu_su_that(T0)
    kt = [x for x in v if x["loai"] == "kt_im_lang"]
    assert len(kt) == 1 and kt[0]["nguoi_quyet"] == "tp_kt_01" and kt[0]["muc"] == tdh.CAO
    bc = kt[0]["su_that"]["bang_chung"]
    assert (bc["so_muc"], bc["so_cao"], bc["so_trung_binh"], bc["so_thap"]) == (5, 2, 1, 2)
    assert [f["doi_tuong"] for f in kt[0]["su_that"]["phat_hien_cao"]] == ["MHKTA0001", "MHKTA0002"]
    # LLM bỏ sót mã mức cao -> code tự chèn; mức thấp gộp thành dòng "còn N mục nhỏ"
    kq = tdh.soan(kt[0], _llm_dung_kt)
    assert kq["nguon_noi_dung"] == "llm" and "MHKTA0001" in kq["nhan_dinh"] and "MHKTA0002" in kq["nhan_dinh"] and "Còn 2 mục nhỏ" in kq["nhan_dinh"]


def _llm_dung_kt(he_thong, nguoi_dung):
    bc = json.loads(nguoi_dung)["bang_su_that"]["bang_chung"]
    return json.dumps({"nhan_dinh": f"Có {bc['so_muc']} ca im lặng.", "phuong_an": [{"ma": "A", "tieu_de": "Gọi từng ca", "mo_ta": "Điều hành hỏi lại."}, {"ma": "B", "tieu_de": "Chuyển ca", "mo_ta": "Cho người rảnh."}],
                       "khuyen_nghi": "B"}, ensure_ascii=False)


def test_dang_ky_them_bo_quet_va_so_do_phu(ql, monkeypatch):
    monkeypatch.setattr(tdh, "NGUON_QUET", list(tdh.NGUON_QUET))
    ph = tdh._ph("nguon_moi", "nguon_moi:x", ma="nguon_moi:x", khoi="DVKH", cap="nhan_su", doi_tuong="x", muc=tdh.CAO, diem=50, tieu_de="Vấn đề từ nguồn mới", bang_chung={"so": 7},
                 duong_dan="/dvkh", nguoi_quyet="tp_dvkh_01", chi_so=tdh._chi_so("cao_cn", {}, 7, "Chỉ số mới", "việc"))
    tdh.dang_ky(tdh.NguonQuet("nguon_moi", "Nguồn mới", lambda c: [ph], lambda c: {"don_vi": "người", "da_quet": 3, "tong": 4}))
    v = tdh.thu_su_that(T0)
    assert [x["loai"] for x in v] == ["nguon_moi"] and v[0]["nguoi_quyet"] == "tp_dvkh_01"
    phu = {x["nguon"]: x for x in tdh.so_do_phu(T0)}
    assert phu["nguon_moi"]["da_quet"] == 3 and phu["nguon_moi"]["tong"] == 4 and {"qua_han_team", "hang_cho", "cao_chi_nhanh", "kt_im_lang"} <= set(phu)
    assert phu["kt_im_lang"]["co_nguon"] is False or phu["kt_im_lang"]["tong"] == 0         # chưa có nguồn Kỹ thuật thì ghi 0 / 0
    tdh.dang_ky(tdh.NguonQuet("loi", "Nguồn hỏng", lambda c: 1 / 0, lambda c: 1 / 0))
    assert tdh.thu_su_that(T0) and any(x["nguon"] == "loi" and x["co_nguon"] is False for x in tdh.so_do_phu(T0))   # nguồn hỏng không làm hỏng cả buổi


# ------------------------------------------------------------------ soạn: luật, LLM giả, kiểm số
def test_ban_luat_luon_ra_khi_khong_co_llm(ql):
    _team(4)
    kq = tdh.soan(_van_de(), None, {"tpkd_01": "TPKD team 1"})
    assert kq["nguon_noi_dung"] == "luat" and kq["ly_do_luat"] == "chua_bat_ai"
    assert [p["ma"] for p in kq["phuong_an"]] == ["A", "B", "C"] and kq["khuyen_nghi"] in "ABC"
    assert "TPKD team 1" in kq["nhan_dinh"] and "4 việc quá hạn" in kq["nhan_dinh"]


def test_llm_gia_tra_so_dung_thi_dung_ban_cua_llm(ql):
    _team(4)
    kq = tdh.soan(_van_de(), _llm_dung)
    assert kq["nguon_noi_dung"] == "llm" and kq["nhan_dinh"].startswith("Có 4 việc quá hạn") and [p["ma"] for p in kq["phuong_an"]] == ["A", "B"] and kq["khuyen_nghi"] == "A"


@pytest.mark.parametrize("raw,ly_do", [
    (json.dumps({"nhan_dinh": "Có 40 việc quá hạn.", "phuong_an": [{"ma": "A", "tieu_de": "a", "mo_ta": "b"}, {"ma": "B", "tieu_de": "a", "mo_ta": "b"}], "khuyen_nghi": "A"}), "sai_dinh_dang_hoac_so"),
    ("không phải json", "sai_dinh_dang_hoac_so"),
    (json.dumps({"nhan_dinh": "ok", "phuong_an": [{"ma": "A", "tieu_de": "a", "mo_ta": "b"}], "khuyen_nghi": "A"}), "sai_dinh_dang_hoac_so"),                      # chỉ một phương án
    (json.dumps({"nhan_dinh": "Việc đấu nối chậm.", "phuong_an": [{"ma": "A", "tieu_de": "a", "mo_ta": "b"}, {"ma": "B", "tieu_de": "a", "mo_ta": "b"}], "khuyen_nghi": "A"}), "sai_dinh_dang_hoac_so"),
    (json.dumps({"nhan_dinh": "ok", "phuong_an": [{"ma": "A", "tieu_de": "a", "mo_ta": "b"}, {"ma": "B", "tieu_de": "a", "mo_ta": "b"}], "khuyen_nghi": "C"}), "sai_dinh_dang_hoac_so"),
])
def test_llm_sai_thi_roi_ve_luat(ql, raw, ly_do):
    _team(4)
    kq = tdh.soan(_van_de(), lambda h, n: raw)
    assert kq["nguon_noi_dung"] == "luat" and kq["ly_do_luat"] == ly_do and "4 việc quá hạn" in kq["nhan_dinh"]


def test_llm_nem_loi_thi_roi_ve_luat(ql):
    _team(4)

    def hong(h, n):
        raise RuntimeError("mạng lỗi")
    kq = tdh.soan(_van_de(), hong)
    assert kq["nguon_noi_dung"] == "luat" and kq["ly_do_luat"] == "loi_ai"


def test_kiem_so_doc_duoc_dinh_dang_viet_nam():
    bang = {"a": 1234, "b": 5.4, "c": "hạn 18/11", "d": [7, {"e": 62}]}
    assert tdh.kiem_so("Có 1.234 việc, tăng 5,4%, hạn 18/11, 7 người và 62%.", bang)
    assert tdh.kiem_so("Không có số nào.", bang)
    assert not tdh.kiem_so("Có 12 việc.", bang)
    assert not tdh.kiem_so("Hạn 19/11.", bang)
    assert tdh.kiem_so("Team tpkd_01, hợp đồng MHAAA0001 và dh_kt_01.", bang)                # số nằm trong mã không tính


def test_tran_luot_goi_llm_moi_ngay_va_nho_ket_qua(ql, monkeypatch):
    monkeypatch.setenv("TRO_LY_DIEU_HANH_TRAN_NGAY", "1")
    _team(4)
    v = _van_de()
    goi = []

    def llm(h, n):
        goi.append(1)
        return _llm_dung(h, n)
    assert tdh.soan(v, llm, now=NOW)["nguon_noi_dung"] == "llm" and tdh.dem_llm(NOW) == 1
    assert tdh.soan(v, llm, now=NOW)["nguon_noi_dung"] == "llm" and len(goi) == 1          # cùng vấn đề và cùng bảng sự thật: dùng lại kết quả đã nhớ, không tốn lượt
    v2 = {**v, "ma_van_de": v["ma_van_de"] + "x"}
    kq = tdh.soan(v2, llm, now=NOW)
    assert kq["nguon_noi_dung"] == "luat" and kq["ly_do_luat"] == "het_tran" and len(goi) == 1
    assert not tdh.trang_thai_ai(NOW)["dung_ai"]


def test_loi_gui_llm_khong_co_ten_khach_sdt_hay_ten_nhan_su(ql):
    _team(4)
    thu = []
    tdh.soan(_van_de(), lambda h, n: (thu.append(h + n), _llm_dung(h, n))[1], {"tpkd_01": "TPKD team 1"})
    chu = thu[0]
    assert not re.search(r"\d{7,}", chu) and "TPKD team 1" not in chu and "Sale 01" not in chu and "KTV 01" not in chu
    assert "tpkd_01" in chu and "đấu nối" not in chu.replace("không dùng chữ 'đấu nối'", "")


# ------------------------------------------------------------------ vòng khép kín
def _sang(**kw):
    return tdh.chay_buoi_sang(NOW, goi_llm=kw.get("goi_llm"))


def test_buoi_sang_tao_de_xuat_gui_dung_nguoi_va_khong_trung_trong_ngay(ql):
    _team(4)
    r = _sang()
    assert r["moi"] == 1 and r["gui"] == 1 and r["luat"] == 1
    d = qd.liet_ke()[0]
    assert d["trang_thai"] == "cho_quyet" and d["nguoi_quyet"] == "tpkd_01" and d["nguon_noi_dung"] == "luat" and d["chi_so_truoc"]["gia_tri"] == 4
    assert "TPKD team 1" in d["tieu_de"] and d["han_quyet"]
    tin = [t for t in td.hop_thu().to_dict("records") if t["loai"] == "quyet_dinh"]
    assert len(tin) == 1 and tin[0]["den_nguoi"] == "tpkd_01" and len(tin[0]["noi_dung"]) < 1700
    assert f"dong y {d['id']}" in tin[0]["noi_dung"] and "sua" in tin[0]["noi_dung"] and "bac" in tin[0]["noi_dung"] and "Hạn quyết" in tin[0]["noi_dung"]
    r2 = _sang()
    assert r2["moi"] == 0 and r2["gui"] == 0 and len(qd.liet_ke()) == 1
    assert len([t for t in td.hop_thu().to_dict("records") if t["loai"] == "quyet_dinh"]) == 1


def test_lenh_zalo_quyet_bac_sua_va_quyen(ql):
    _team(4)
    _sang()
    qid = qd.liet_ke()[0]["id"]
    assert f"#{qid}" in zl.xu_ly("tpkd_01", "quyet dinh", NOW)
    assert "Không có đề xuất" in zl.xu_ly("tpkd_02", "quyet dinh", NOW)
    assert "thuộc về" in zl.xu_ly("tpkd_02", f"dong y {qid} A", NOW) and qd.doc(qid)["trang_thai"] == "cho_quyet"       # team khác không quyết được
    assert "Bot này gửi việc cho quản lý" in zl.xu_ly("sale_01", f"dong y {qid} A", NOW)
    assert "không có phương án D" in zl.xu_ly("tpkd_01", f"dong y {qid} D", NOW) and qd.doc(qid)["trang_thai"] == "cho_quyet"
    r = zl.xu_ly("tpkd_01", f"đồng ý {qid} B", NOW)
    assert "Đã ghi quyết định" in r and "phương án B" in r and "đo lại" in r
    d = qd.doc(qid)
    assert d["trang_thai"] == "da_quyet" and d["lua_chon"] == "B" and d["quyet_boi"] == "tpkd_01" and d["han_kiem_chung"]
    assert "đã ở trạng thái Đã quyết" in zl.xu_ly("tpkd_01", f"dong y {qid} A", NOW)
    assert [x for x in qd.nhat_ky(qid)["hanh_dong"]] == ["de_xuat", "da_quyet"]


def test_lenh_zalo_cap_tren_quyet_thay_bac_phai_co_ly_do_va_sua_ghi_y_kien(ql):
    _team(4)
    _sang()
    qid = qd.liet_ke()[0]["id"]
    assert "ghi thêm lý do" in zl.xu_ly("gd_01", f"bac {qid}", NOW)
    assert "bác đề xuất" in zl.xu_ly("gd_01", f"bac {qid} đã có người lo", NOW)                      # giám đốc là cấp trên nên quyết thay được
    d = qd.doc(qid)
    assert d["trang_thai"] == "bac" and d["quyet_boi"] == "gd_01" and d["ghi_chu"] == "đã có người lo"
    td.dong_bo(_viec(*[dict(so_hd=f"MHCCC{i:04d}", giao_dvkh="", giao_kt="", giao_sale="sale_02") for i in range(1, 5)]), T0)
    _sang()
    moi = qd.liet_ke("cho_quyet")
    assert [x["nguoi_quyet"] for x in moi] == ["tpkd_02"]                                         # đề xuất mới của team 2; đề xuất cũ của team 1 đã bác nên không tạo lại trong ngày
    assert "thuộc về" in zl.xu_ly("tpkd_01", f"dong y {moi[0]['id']} A", NOW)
    assert "Đã ghi quyết định" in zl.xu_ly("tpkd_02", f"dong y {moi[0]['id']}", NOW) and qd.doc(moi[0]["id"])["lua_chon"] == moi[0]["khuyen_nghi"]     # bỏ chữ cái: theo khuyến nghị


def test_sua_ghi_y_kien_rieng(ql):
    _team(4)
    _sang()
    qid = qd.liet_ke()[0]["id"]
    assert "ghi thêm ý kiến" in zl.xu_ly("tpkd_01", f"sua {qid}", NOW)
    assert "ý kiến của anh/chị" in zl.xu_ly("tpkd_01", f"sua {qid} chia lại việc cho người nhẹ việc", NOW)
    d = qd.doc(qid)
    assert d["trang_thai"] == "da_quyet" and d["lua_chon"] == "sua" and d["ghi_chu"] == "chia lại việc cho người nhẹ việc"


def test_nhac_va_leo_thang_dung_mot_lan(ql):
    _team(4)
    _sang()
    qid = qd.liet_ke()[0]["id"]
    han = pd.Timestamp(qd.doc(qid)["han_quyet"]).to_pydatetime()
    assert tdh.nhac_quyet(NOW) == {"nhac": 0, "bao_cap_tren": 0}                                      # chưa quá hạn quyết
    r = tdh.nhac_quyet(han + timedelta(hours=1))
    assert r == {"nhac": 1, "bao_cap_tren": 0}
    assert tdh.nhac_quyet(han + timedelta(hours=2)) == {"nhac": 0, "bao_cap_tren": 0}                  # không nhắc lại
    r = tdh.nhac_quyet(han + timedelta(hours=17))
    assert r == {"nhac": 0, "bao_cap_tren": 1} and qd.doc(qid)["trang_thai"] == "qua_han"
    assert tdh.nhac_quyet(han + timedelta(hours=40)) == {"nhac": 0, "bao_cap_tren": 0}
    loai = {(t["loai"], t["den_nguoi"]) for t in td.hop_thu().to_dict("records")}
    assert ("nhac_quyet", "tpkd_01") in loai and ("leo_thang", "gd_01") in loai
    assert "Đã ghi quyết định" in zl.xu_ly("tpkd_01", f"dong y {qid} A", han + timedelta(hours=41))       # quá hạn vẫn quyết được
    assert qd.doc(qid)["trang_thai"] == "da_quyet"


def test_kiem_chung_do_lai_dung_chi_so_truoc_sau_va_chi_mot_lan(ql):
    _team(4)
    _sang()
    qid = qd.liet_ke()[0]["id"]
    zl.xu_ly("tpkd_01", f"dong y {qid} A", NOW)
    han_kc = pd.Timestamp(qd.doc(qid)["han_kiem_chung"]).to_pydatetime()
    assert tdh.kiem_chung(NOW, goi_llm=None) == {"kiem_chung": 0, "da_bao": 0}                         # chưa tới hạn đo lại
    ids = [int(i) for i in td.danh_sach(NOW)["id"]][:3]
    for i in ids:
        td.cap_nhat(i, "da_xong", "sale_01", "", NOW)                                                  # 3 trên 4 việc xong
    r = tdh.kiem_chung(han_kc + timedelta(hours=1), goi_llm=None)
    assert r == {"kiem_chung": 1, "da_bao": 1}
    d = qd.doc(qid)
    assert d["trang_thai"] == "da_kiem_chung" and d["chi_so_truoc"]["gia_tri"] == 4 and d["chi_so_sau"]["gia_tri"] == 1
    assert "giảm từ 4 xuống 1 việc (giảm 75%)" in d["ket_qua"] and "Đã cải thiện" in d["ket_qua"] and "TPKD team 1" in d["ket_qua"]
    assert tdh.kiem_chung(han_kc + timedelta(hours=5), goi_llm=None) == {"kiem_chung": 0, "da_bao": 0}  # chỉ một lần
    bao = [(t["loai"], t["den_nguoi"]) for t in td.hop_thu().to_dict("records") if t["loai"] == "kiem_chung"]
    assert sorted(bao) == [("kiem_chung", "gd_01"), ("kiem_chung", "tpkd_01")]


def test_kiem_chung_llm_viet_lai_co_kiem_so_va_roi_ve_luat_khi_sai(ql):
    _team(4)
    _sang()
    qid = qd.liet_ke()[0]["id"]
    zl.xu_ly("tpkd_01", f"dong y {qid} A", NOW)
    han_kc = pd.Timestamp(qd.doc(qid)["han_kiem_chung"]).to_pydatetime()
    cs = qd.doc(qid)["chi_so_truoc"]
    ket = tdh.cau_ket_qua(cs, 4)
    assert "không đổi" in ket and "Chưa cải thiện" in ket
    sai = lambda h, n: json.dumps({"ket_qua": "Quá hạn giảm 99%."})
    tdh.kiem_chung(han_kc + timedelta(hours=1), goi_llm=sai)
    d = qd.doc(qid)
    assert d["trang_thai"] == "da_kiem_chung" and "99" not in d["ket_qua"] and "không đổi" in d["ket_qua"]


def test_kiem_chung_llm_viet_lai_so_dung(ql):
    _team(4)
    _sang()
    qid = qd.liet_ke()[0]["id"]
    zl.xu_ly("tpkd_01", f"dong y {qid} A", NOW)
    han_kc = pd.Timestamp(qd.doc(qid)["han_kiem_chung"]).to_pydatetime()
    tdh.kiem_chung(han_kc + timedelta(hours=1), goi_llm=lambda h, n: json.dumps({"ket_qua": "Số việc quá hạn vẫn là 4, chưa có chuyển biến."}))
    d = qd.liet_ke()[0]
    assert d["ket_qua"].startswith("Số việc quá hạn vẫn là 4")


def test_bac_khong_duoc_kiem_chung(ql):
    _team(4)
    _sang()
    qid = qd.liet_ke()[0]["id"]
    zl.xu_ly("tpkd_01", f"bac {qid} chưa cần", NOW)
    assert tdh.kiem_chung(NOW + timedelta(days=9), goi_llm=None) == {"kiem_chung": 0, "da_bao": 0}


def test_vong_tu_dong_buoi_sang_moi_ngay_mot_lan(ql, monkeypatch):
    monkeypatch.setattr(tdh, "goi_llm_mac_dinh", lambda: None)
    _team(4)
    r = tdh.vong_tu_dong(NOW)
    assert r["moi"] == 1 and r["gui"] == 1
    r2 = tdh.vong_tu_dong(NOW + timedelta(hours=1))
    assert r2["moi"] == 0 and r2["gui"] == 0 and r2["nhac"] == 0


def test_tom_tat_so_cho_quyet_da_quyet_qua_han_va_kiem_chung(ql):
    _team(4)
    _sang()
    assert qd.tom_tat()["cho_quyet"] == 1 and qd.tom_tat()["da_kiem_chung"] == 0
    assert qd.cho_quyet("gd_01") and qd.cho_quyet("tpkd_02") == []


def test_menu_co_lenh_quyet_dinh_va_demo_agent(thu_zalo, monkeypatch):
    f, gui = thu_zalo
    f.write_text(json.dumps({"KD": "chat-a", "DVKH": "chat-a", "KT": "chat-a", "BGD": "chat-a"}), encoding="utf-8")
    _dat(monkeypatch)
    monkeypatch.setattr(tdh, "goi_llm_mac_dinh", lambda: None)
    assert "dong y SỐ A" in zl.xu_ly("chat-a", "menu", T0) and "demo agent" in zl.xu_ly("chat-a", "menu", T0)
    zl.xu_ly("chat-a", "demo moi", T0)
    r = zl.xu_ly("chat-a", "demo agent", T0)
    assert "Trợ lý điều hành đã đề xuất" in r
    assert "Lệnh demo:" in zl.xu_ly("chat-a", "demo", T0) and "demo agent" in zl.xu_ly("chat-a", "demo", T0)
    r2 = zl.xu_ly("chat-a", "demo kiem chung", T0)
    assert "Trợ lý nhắc" in r2 and td.gio_gia_lap() >= 49
