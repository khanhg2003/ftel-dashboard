"""Nhóm gói của Tra cứu giá chia như website fpt.vn (app/gia_fpt_nhom.py, chốt 23/10/2026).

Không gọi mạng: `_tai_trang` được thay bằng HTML mẫu cùng dạng với trang thật (dấu nháy bị escape `\\"`)."""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import gia_fpt as gf  # noqa: E402
from app import gia_fpt_nhom as gn  # noqa: E402
from app.bo_nho import xoa  # noqa: E402

# Mẩu cắt nguyên văn từ HTML thật của https://fpt.vn/vi (tab "Internet gia đình"), còn nguyên các dấu \" của dữ liệu Next.js.
MAU_THAT = (r'{\"id\":65,\"name\":\"internet-gia-dinh-trang-chu\",\"title\":\"Internet gia đình\",\"type\":\"tab\",\"order\":1,\"content\":null,'
            r'\"icon\":null,\"icon_active\":null,\"icon_position\":null,\"attributes\":null,\"cta\":{\"text\":\"Xem tất cả\",\"url\":\"/internet/gia-dinh\",'
            r'\"style\":null},\"banner\":null,\"items\":[{\"package_id\":88,\"product_code\":\"goi-speedx1-f1\",\"source\":\"ECP\"},{\"package_id\":16,'
            r'\"product_code\":\"goi-sky-f1\",\"source\":\"ECP\"},{\"package_id\":17,\"product_code\":\"goi-sky-f2\",\"source\":\"ECP\"},{\"package_id\":18,'
            r'\"product_code\":\"goi-meta-f1\",\"source\":\"ECP\"}]},')


def _items(ma):
    return ",".join('{"package_id":%d,"product_code":"%s","source":"ECP"}' % (i, m) for i, m in enumerate(ma, 1))


def _tab(khoa, ma):
    return ('{"id":1,"name":"%s","title":"Tên tab","type":"tab","order":0,"content":null,"cta":{"text":"Xem","url":"/x","style":null},"banner":null,'
            '"items":[%s]}' % (khoa, _items(ma)))


def _khoi(khoa, ma):
    return ('{"id":25,"name":"%s","title":"SPDV","type":"slider","order":0,"content":null,"cta":{"text":"","url":"/internet","style":null},'
            '"banner":null,"items":[%s]}' % (khoa, _items(ma)))


def _trang(cac_khoi: dict[str, tuple[str, list[str]]]) -> str:
    """HTML mẫu: các khối nối nhau rồi escape dấu nháy như trang thật. cac_khoi = {khoá: (kiểu, mã)}."""
    return "<script>" + "".join((_tab if kieu == "tab" else _khoi)(k, ma) for k, (kieu, ma) in cac_khoi.items()).replace('"', '\\"') + "</script>"


def _html_day_du(bo=None, doi=None) -> dict[str, str]:
    """{url: html} đủ mọi nhóm của BAN_CHUP (kiểu tab cho trang chủ, khối cho hai trang kia); `bo` = khoá bỏ đi, `doi` = {khoá: mã mới}."""
    ra: dict[str, dict] = {}
    for (nhan, url, khoa), (_, ma) in zip(gn.NGUON, gn.BAN_CHUP):
        if khoa == bo:
            continue
        ra.setdefault(url, {})[khoa] = ("tab" if url == gn.TRANG_CHU else "khoi", (doi or {}).get(khoa, ma))
    return {u: _trang(k) for u, k in ra.items()}


class Mang:
    """Thay `_tai_trang`: đếm số lần gọi, trả HTML mẫu hoặc ném lỗi."""
    def __init__(self):
        self.goi: list[str] = []
        self.trang: dict[str, str] = _html_day_du()
        self.loi = False
        self.cham = 0.0

    def __call__(self, url):
        self.goi.append(url)
        if self.cham:
            time.sleep(self.cham)
        if self.loi:
            raise OSError("mạng hỏng")
        return self.trang[url]


@pytest.fixture(autouse=True)
def mang(monkeypatch):
    """Luôn chặn mạng thật; mỗi test bắt đầu với bộ nhớ tạm và mốc lỗi sạch."""
    def reset():
        xoa("gia_fpt")
        gn._loi_luc, gn._tot_luc = None, None
    reset()
    m = Mang()
    monkeypatch.setattr(gn, "_tai_trang", m)
    yield m
    reset()


def _g(code, ten, gia):
    return {"id": hash(code) % 10000, "code": code, "ten": ten, "gia": gia, "khach": "ca_nhan"}


# ------------------------------------------------------------------ đọc HTML
def test_doc_mau_cat_tu_html_that():
    html = MAU_THAT.replace('\\"', '"')
    assert gn._doc_khoa(html, "internet-gia-dinh-trang-chu") == ["goi-speedx1-f1", "goi-sky-f1", "goi-sky-f2", "goi-meta-f1"]
    assert gn._doc_khoa(html, "wifi-7-trang-chu") == []                                 # khoá không có trong mẩu: rỗng, không đọc nhầm khối khác


def test_phan_tich_du_khoi_giu_thu_tu_items_cua_website(mang):
    nguoc = list(reversed(gn.BAN_CHUP[0][1]))
    mang.trang = _html_day_du(doi={"internet-ca-nhan-trang-chu": nguoc})
    kq = gn._phan_tich({u: mang(u) for u in mang.trang})
    assert kq["nguon"] == "website" and [n for n, _ in kq["nhom"]] == [n for n, _ in gn.BAN_CHUP]
    assert dict(kq["nhom"])["Internet cá nhân"] == nguoc                                 # đúng thứ tự items của website, không sắp theo giá hay tên
    assert dict(kq["nhom"])["Internet doanh nghiệp"] == dict(gn.BAN_CHUP)["Internet doanh nghiệp"]


def test_phan_tich_html_rac_rong_hoac_thieu_khoi_thi_bao_loi(mang):
    for trang in ({}, {u: "" for u in mang.trang}, {u: "<html>Access denied</html>" for u in mang.trang}):
        with pytest.raises(gn.LoiNhom):
            gn._phan_tich(trang)
    with pytest.raises(gn.LoiNhom):                                                     # thiếu MỘT khối là bỏ cả kết quả
        gn._phan_tich(_html_day_du(bo="internet-game-thu-trang-chu"))
    with pytest.raises(gn.LoiNhom):                                                     # khối có mà không có mã nào
        gn._phan_tich(_html_day_du(doi={"internet-game-thu-trang-chu": []}))


# ------------------------------------------------------------------ cau_hinh: website, bản chụp, nhớ tạm, nghỉ sau lỗi
def test_cau_hinh_doc_duoc_website(mang):
    mang.trang = _html_day_du(doi={"spdv-internet-doanh-nghiep": ["moi-1", "moi-2"]})
    ch = gn.cau_hinh()
    assert ch["nguon"] == "website" and dict(ch["nhom"])["Internet doanh nghiệp"] == ["moi-1", "moi-2"]
    assert set(mang.goi) == {gn.TRANG_CHU, gn.TRANG_DN, gn.TRANG_CN}                    # đúng ba trang


def test_cau_hinh_html_rac_thi_dung_nguyen_ban_chup_khong_tron(mang):
    mang.trang = {u: "<html>khong co gi</html>" for u in mang.trang}
    ch = gn.cau_hinh()
    assert ch == gn.ban_chup() and ch["nguon"] == "luu_san"
    mang.trang = _html_day_du(bo="internet-game-thu-trang-chu", doi={"spdv-internet-doanh-nghiep": ["moi-1"]})   # thiếu một nhóm: bỏ HẾT, kể cả nhóm đọc được
    gn._loi_luc = None
    xoa("gia_fpt")
    ch = gn.cau_hinh()
    assert ch == gn.ban_chup() and dict(ch["nhom"])["Internet doanh nghiệp"] != ["moi-1"]


def test_ban_chup_la_ban_sao_khong_bi_sua_nguoc():
    ch = gn.ban_chup()
    ch["nhom"][0][1].append("x")
    assert "x" not in gn.BAN_CHUP[0][1]


def test_thanh_cong_nho_tam_sau_do_khong_tai_lai_ke_ca_khi_bam_lam_moi(mang):
    gn.cau_hinh()
    so_lan = len(mang.goi)
    gn.cau_hinh()
    xoa("gia_fpt")                                                                       # nút "Làm mới giá" xoá nhớ tạm của cả nhóm
    gn.cau_hinh()
    assert len(mang.goi) == so_lan == 3                                                  # vẫn dùng kết quả đã tải: không gọi lại website


def test_loi_tai_khong_bi_nho_tam_6_gio(mang):
    mang.loi = True
    assert gn.cau_hinh()["nguon"] == "luu_san"
    mang.loi = False
    gn._loi_luc = time.monotonic() - gn.NGHI_SAU_LOI - 1                                 # đã qua mốc nghỉ
    assert gn.cau_hinh()["nguon"] == "website"                                           # lần sau tải lại được ngay, không bị ghim bản chụp 6 giờ


def test_nghi_sau_loi_khong_goi_lai_website(mang):
    mang.loi = True
    gn.cau_hinh()
    so_lan = len(mang.goi)
    assert so_lan >= 1
    for _ in range(5):
        assert gn.cau_hinh()["nguon"] == "luu_san"
    assert len(mang.goi) == so_lan                                                       # đang nghỉ: không tốn thêm lượt tải nào
    gn._loi_luc = time.monotonic() - gn.NGHI_SAU_LOI - 1
    gn.cau_hinh()
    assert len(mang.goi) > so_lan                                                        # hết nghỉ thì thử lại


def test_nhieu_luot_nguoi_cung_luc_chi_tai_mot_lan(mang):
    mang.cham = 0.2
    kq = []
    ds = [threading.Thread(target=lambda: kq.append(gn.cau_hinh())) for _ in range(6)]
    for t in ds:
        t.start()
    for t in ds:
        t.join()
    assert len(mang.goi) == 3 and len(kq) == 6 and all(k["nguon"] == "website" for k in kq)


# ------------------------------------------------------------------ chia nhóm
CH = {"nhom": [("Internet cá nhân", ["b", "a", "goi-speedx1"]), ("Internet doanh nghiệp", ["lux", "biz"]), ("Combo Internet + V.VIP", ["lux", "ko-co"]),
               ("Internet game thủ", ["goi-speedx1", "nulo"]), ("Wifi 7", ["ko-co"])], "nguon": "website"}


def test_chia_nhom_dung_thu_tu_nut_xep_gia_tang_an_goi_va_bo_goi_khac():
    goi = [_g("a", "Gói A", 300), _g("b", "Gói B", 100), _g("lux", "Combo Lux 800", 900), _g("biz", "Super300 Biz", 450),
           _g("goi-speedx1", "Gói SpeedX1", 350), _g("z0", "Rẻ", 50)]
    nhom = gf.theo_nhom(goi, CH)
    # thứ tự nút của CEO; "Wifi 7" (không còn là nút) và gói không thuộc nhóm nào ("z0") không hiện
    assert list(nhom) == ["Internet cá nhân", "Combo Internet + V.VIP", "Internet game thủ", "Internet doanh nghiệp"]
    assert [g["code"] for g in nhom["Internet cá nhân"]] == ["b", "a"]                   # giá thấp -> cao; SpeedX1 bị ẩn khỏi nhóm này
    assert [g["code"] for g in nhom["Internet doanh nghiệp"]] == ["biz", "lux"]          # 450 trước 900
    assert [g["code"] for g in nhom["Combo Internet + V.VIP"]] == ["lux"]                # Lux800 hiện ở CẢ HAI nút; mã website có mà API không có thì bỏ qua
    assert [g["code"] for g in nhom["Internet game thủ"]] == ["goi-speedx1"]                 # SpeedX1 chỉ ẩn ở Internet cá nhân
    assert gn.nhom_cua_goi(goi, CH)["lux"] == "Combo Internet + V.VIP · Internet doanh nghiệp"
    assert "z0" not in gn.nhom_cua_goi(goi, CH)


def test_gia_thieu_xep_cuoi_nhom():
    goi = [_g("a", "A", None), _g("b", "B", 100)]
    assert [g["code"] for g in gf.theo_nhom(goi, {"nhom": [("Internet cá nhân", ["a", "b"])], "nguon": "website"})["Internet cá nhân"]] == ["b", "a"]


def test_chia_nhom_khong_co_goi_nao_thi_rong_va_khong_goi_mang(mang):
    assert gf.theo_nhom([], CH) == {}
    assert gn.chia_nhom([], gn.ban_chup()) == {}
    assert mang.goi == []                                                                # có sẵn `ch` thì không đụng tới website


def test_ma_lap_trong_mot_nhom_bi_bo_khi_doc():
    assert gn._ma_trong('"product_code":"a","product_code":"a","product_code":"b"') == ["a", "b"]
