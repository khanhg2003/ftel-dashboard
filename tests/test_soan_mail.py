"""Kiểm thử Soạn email (chốt 10/10/2026): khuôn ba loại mail, gợi ý người nhận, Fox viết đoạn tình huống (không lộ dữ liệu khách)."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import soan_mail as sm                                         # noqa: E402
from app import tro_ly as ai                                            # noqa: E402
from app.config import DATA_DIR                                          # noqa: E402

CHUNG = {"chao", "tinh_huong", "y_them"}
CA_HOT = {"hop_dong": "DAAAP6381", "dia_chi": "K62/H75/17 Nguyễn Phan Vinh, Sơn Trà, Đà Nẵng", "han_lap": "17h chiều nay",
          "chao": "anh Bình", "tinh_huong": "Hiện case này khách cần lắp đặt trong 17h chiều nay."}


def test_moi_o_trong_khuon_deu_co_nguon_du_lieu():
    """Gõ nhầm tên ô trong khuôn thì mail ra [tên ô] mãi mãi - bắt ngay lúc kiểm thử."""
    for loai, L in sm.LOAI.items():
        co = {t["khoa"] for t in L["truong"]} | CHUNG
        dung = set(re.findall(r"\{\??(\w+)\}", " ".join(L["than"]) + " " + L["tieu_de"]))
        assert dung <= co, (loai, dung - co)
        assert L["goi_y"].keys() == {"den", "cc"} and L["vi_du"] and L["fox"]


def test_mail_ca_hot_dung_cau_chu_mail_mau():
    kq = sm.dung("ca_hot", CA_HOT)
    assert kq["thieu"] == [] and kq["tieu_de"] == "DAAAP6381 - CA HOT CẦN HỖ TRỢ LẮP ĐẶT TRƯỚC 17h chiều nay"
    assert kq["text"] == ("Dear anh Bình,\n\nEm có HĐ: DAAAP6381\nĐịa chỉ: K62/H75/17 Nguyễn Phan Vinh, Sơn Trà, Đà Nẵng\n\n"
                          "Hiện case này khách cần lắp đặt trong 17h chiều nay.\n\nEm xin chân thành cảm ơn ạ!")
    assert ("DAAAP6381", True) in kq["doan"][1]                 # mã hợp đồng in đậm


def test_o_trong_hien_trong_ngoac_va_liet_ke_o_thieu():
    kq = sm.dung("ca_hot", {**CA_HOT, "hop_dong": "", "dia_chi": " "})
    assert "[Mã hợp đồng]" in kq["text"] and "[Địa chỉ lắp đặt]" in kq["text"]
    assert kq["thieu"] == ["Mã hợp đồng", "Địa chỉ lắp đặt"]
    assert "[Mã hợp đồng]" in kq["tieu_de"]


def test_mail_ket_thuc_bang_cau_cam_on_khong_co_chu_ky():
    """Chủ app bỏ ô Người gửi (12/10/2026): sale ký tên bằng chữ ký có sẵn của Outlook."""
    assert sm.dung("ca_hot", CA_HOT)["text"].endswith("Em xin chân thành cảm ơn ạ!")


def test_mail_xin_hoa_don_dn_du_cac_dong_cua_mail_mau():
    v = {"hop_dong": "NTAAQ4015", "dia_chi": "225 Cầu Dừa, Nha Trang, Khánh Hòa", "dia_chi_hd": "Số 02L Ngô Quyền, Sơn Trà, Đà Nẵng",
         "mst": "4201591367", "sdt": "0963901900", "goi_cuoc": "combo vvip trả trước 6 tháng", "chao": "anh Ý",
         "tinh_huong": "Hiện khách chỉ muốn đăng ký gói trả trước 6 tháng."}
    kq = sm.dung("hoa_don", v)
    assert kq["thieu"] == [] and kq["text"].startswith("Kính gửi anh Ý,")
    for dong in ("Em có hd: NTAAQ4015 muốn lắp gói cá nhân nhưng xin đứng tên và xuất hóa đơn doanh nghiệp.",
                 "D/c lắp đặt: 225 Cầu Dừa, Nha Trang, Khánh Hòa", "Đc xuất hóa đơn: Số 02L Ngô Quyền, Sơn Trà, Đà Nẵng",
                 "Mã số thuế: 4201591367", "Số điện thoại: 0963901900", "Gói cước: combo vvip trả trước 6 tháng"):
        assert dong in kq["text"]
    assert kq["text"].endswith("Em xin chân thành cảm ơn ạ!")


def test_mail_ha_tang_dung_cau_mau_va_cau_mac_dinh_khi_khong_co_y_rieng():
    v = {"hop_dong": "CMAAE5918", "dia_chi": "x", "tap_diem": "CMUP003.0008/HO", "port_hien_tai": "8", "port_nang_cap": "16",
         "thoi_gian_cho": "2 đến 3 ngày", "chao": "anh Hiếu", "tinh_huong": ""}
    kq = sm.dung("ha_tang", v)
    assert kq["thieu"] == []                                   # ô tình huống không bắt buộc ở loại này
    assert "nâng cấp tập điểm CMUP003.0008/HO từ 8 port lên 16 port" in kq["text"]
    assert kq["text"].count("anh Hiếu") == 2                   # lời chào + "nhờ anh Hiếu hỗ trợ"
    assert "có thể đợi khoảng 2 đến 3 ngày." in kq["text"]
    assert "khách rất gấp" in sm.dung("ha_tang", {**v, "tinh_huong": "khách rất gấp."})["text"]


def test_loi_chao_do_sale_tu_go_va_trong_thi_bao_con_thieu():
    """Chủ app (10/10/2026): bỏ ô chọn anh / chị, sale tự gõ "phòng kỹ thuật DNG"..."""
    v = {**CA_HOT, "chao": "phòng kỹ thuật DNG"}
    assert sm.dung("ca_hot", v)["text"].startswith("Dear phòng kỹ thuật DNG,")
    kq = sm.dung("ca_hot", {**CA_HOT, "chao": ""})
    assert kq["text"].startswith("Dear [Lời chào],") and "Lời chào" in kq["thieu"]


def test_che_so_dai_va_email_truoc_khi_gui_ai():
    assert sm._che("khách 0963901900 mst 4201 591 367 mail a.b@fpt.com") == "khách [số] mst [số] mail [email]"
    assert sm._che("đợi 2 đến 3 ngày, 8 port lên 16 port") == "đợi 2 đến 3 ngày, 8 port lên 16 port"


# ------------------------------------------------------------------ Fox
class _Tk(SimpleNamespace):
    la_superadmin = False


def _gia_ai(monkeypatch, tra="**Hiện** khách cần gấp.", da_dung=0):
    gui = {}
    monkeypatch.setattr(ai, "kiem_tra", lambda user: {"model_chat": "m", "key": "k"})
    monkeypatch.setattr(ai, "luot_hom_nay", lambda *_a, **_k: da_dung)

    def hoi(messages, model, key, username, loai, **kw):
        gui.update(messages=messages, loai=loai)
        return {"content": tra}
    monkeypatch.setattr(ai, "hoi", hoi)
    monkeypatch.setattr(sm, "ghi_log", lambda *a, **k: None)
    return gui


def test_fox_khong_gui_so_dien_thoai_email_len_ai_va_lam_sach_dau_markdown(monkeypatch):
    gui = _gia_ai(monkeypatch)
    kq = sm.viet_tinh_huong("ca_hot", "khách 0963901900 a@fpt.com chỉ rảnh chiều nay", {"Hạn cần lắp": "17h"}, _Tk(username="u"))
    nd = gui["messages"][1]["content"]
    assert "0963901900" not in nd and "a@fpt.com" not in nd and "[số]" in nd and "Hạn cần lắp: 17h" in nd
    assert kq == "Hiện khách cần gấp." and gui["loai"] == sm.LOAI_AI                  # bỏ ** của markdown
    assert "Ví dụ" in gui["messages"][0]["content"]


def test_fox_chan_y_trong_va_het_luot_trong_ngay(monkeypatch):
    _gia_ai(monkeypatch)
    with pytest.raises(ai.LoiAI, match="ý chính"):
        sm.viet_tinh_huong("ca_hot", "  ", {}, _Tk(username="u"))
    with pytest.raises(ai.LoiAI, match="Loại mail"):
        sm.viet_tinh_huong("khong_co", "x", {}, _Tk(username="u"))
    _gia_ai(monkeypatch, da_dung=sm.TOI_DA_NGAY)
    with pytest.raises(ai.LoiAI, match="hết"):
        sm.viet_tinh_huong("ca_hot", "x", {}, _Tk(username="u"))
    sm.viet_tinh_huong("ca_hot", "x", {}, _Tk(username="u", la_superadmin=True))      # admin không giới hạn


# ------------------------------------------------------------------ gợi ý người nhận (cần danh bạ trong database kiểm thử)
@pytest.fixture
def danh_ba_mau():
    import test_danh_ba as t
    from sqlalchemy import text

    from app import danh_ba as db
    from app.bo_nho import xoa
    from app.db import engine
    db.dam_bao_bang()

    def don():
        with engine.begin() as c:
            c.execute(text("DELETE FROM danh_ba"))
            c.execute(text("DELETE FROM audit_log WHERE username LIKE 'kiemthu%'"))
        xoa("danh_ba")
    don()
    db.nap(t._xlsx({"TĐĐT": t.PNC_TD}), "pnc.xlsx", "PNC", "kiemthu.admin")
    yield
    don()


pytestmark_db = pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(), reason="Chưa dựng được database kiểm thử")


@pytestmark_db
def test_goi_y_ca_hot_chon_doi_truong_theo_dia_chi(danh_ba_mau):
    g = sm.goi_y("ca_hot", None, CA_HOT["dia_chi"])
    assert g["don_vi"] == "Đà Nẵng" and g["khu_vuc_ro"] is True
    assert [p["ten"] for p in g["den"]] == ["Tô Duy Bình"] and g["den"][0]["email"] == "BinhTD@vienthongtin.com"
    g = sm.goi_y("ca_hot", None, "12 Lê Duẩn, Hải Châu, Đà Nẵng")          # địa chỉ chưa khớp block nào
    assert g["khu_vuc_ro"] is False and [p["ten"] for p in g["den"]] == ["Tô Duy Bình"]      # hiện mọi đội trưởng, sale chọn


@pytestmark_db
def test_goi_y_hoa_don_gui_pho_giam_doc_noi_lap_cc_giam_doc_hai_noi(danh_ba_mau):
    g = sm.goi_y("hoa_don", None, "225 Cầu Dừa, Phước Long, Nha Trang, Khánh Hòa")
    assert g["don_vi"] == "Khánh Hòa"
    assert [p["ten"] for p in g["den"]] == ["Lê Cảnh Ý"]
    assert [p["ten"] for p in g["cc"]] == ["Hoàng Anh", "Nguyễn Đăng Duy"]       # GĐ nơi lắp + GĐ chi nhánh của sale
    assert sm.goi_y("hoa_don", "Đà Nẵng", "đâu đó")["don_vi"] == "Đà Nẵng"      # sale chọn tay thì theo sale


@pytestmark_db
def test_goi_y_ha_tang_va_chi_nhanh_khong_co_ai(danh_ba_mau):
    g = sm.goi_y("ha_tang", "Đà Nẵng", "")
    assert [p["ten"] for p in g["den"]] == ["Châu Ngọc Vinh"] and [p["ten"] for p in g["cc"]] == ["Nguyễn Đăng Duy"]
    g = sm.goi_y("ha_tang", "Cà Mau", "")
    assert g["den"] == [] and g["cc"] == []                                      # không bịa: để sale tra danh bạ


def test_trang_soan_email_dung_duoc_ma_khong_can_database():
    from app.ui.pages import soanmail
    kq = sm.dung("ca_hot", CA_HOT)
    nguoi = {"den": [{"ten": "Tô Duy Bình", "email": "a@fpt.com", "chuc_vu": "", "don_vi": ""}], "cc": []}
    hd = soanmail._hanh_dong("ca_hot", kq, nguoi)
    nut = hd[0].children
    mo = nut[0].to_plotly_json()["props"]
    assert mo["data-outlook"] == "web" and mo["data-den"] == "a@fpt.com" and mo["data-tieu-nguon"] == "#sm-tieu"
    assert mo["data-chep-nguon"] == "#sm-than" and len(nut) == 2                         # chỉ hai nút: mở Outlook + copy nội dung
    form = soanmail._o_form("hoa_don").children
    assert len(form[0].children) == len(sm.LOAI["hoa_don"]["truong"]) and len(form) == 3      # ô · tình huống · ý riêng
    assert all(t["dai"] for t in sm.LOAI["hoa_don"]["truong"] if t["khoa"].startswith("dia_chi"))


def _cac_id(nut) -> list[str]:
    """Mọi id trong cây thành phần Dash (id kiểu dict đổi sang chuỗi để so trùng)."""
    ids, dung = [], [nut]
    while dung:
        n = dung.pop()
        if isinstance(n, (list, tuple)):
            dung.extend(n)
            continue
        i = getattr(n, "id", None)
        if i is not None:
            ids.append(str(sorted(i.items())) if isinstance(i, dict) else i)
        dung.extend([c for c in [getattr(n, "children", None)] if c is not None])
    return ids


def test_hai_trang_dung_duoc_va_khong_trung_id():
    """Lỗi thật 10/10/2026: `html.Input` không tồn tại nên trang Danh bạ nổ 500 mà các test hàm không bắt được."""
    from flask_login import login_user

    from app.auth import SessionUser
    from app.ui.app import server
    from app.ui.pages import danhba, soanmail
    ad = SessionUser(SimpleNamespace(id=1, username="kiemthu.admin", ho_ten="K", role="admin", ma_nv=None,
                                     session_version=0, scope="[]"))
    with server.test_request_context("/"):
        login_user(ad)
        for trang in (danhba, soanmail):
            ids = _cac_id(trang.layout())
            assert ids and not {i for i in ids if ids.count(i) > 1}, trang.__name__
            assert trang.topbar()
        ids = _cac_id(soanmail.layout())
        assert {"sm-tieu", "sm-than", "sm-sua-bao", "sm-dung-lai", "sm-kq", "sm-chao", "sm-dv"} <= set(ids)
        assert {"sm-form", "sm-loai", "sm-db-kq", "sm-db-tim", "sm-db-dv-tim", "sm-db-dv-ds", "sm-db-dem", "sm-du-lieu", "sm-sk-chon"} <= set(ids)
        assert {"db-kq", "db-dem", "db-tim", "db-dv-tim", "db-dv-ds", "db-sk-sua", "db-du-lieu"} <= set(_cac_id(danhba.layout()))
        # cả ba biểu mẫu có mặt sẵn, mỗi ô mang tên loại để không trùng nhau
        assert all(f"sm-form-{loai}" in ids for loai in sm.LOAI)


def test_y_them_nam_truoc_cau_cam_on_va_bo_ca_doan_khi_trong():
    """Ô "Thêm ý riêng" là cách thêm ý ngoài khuôn mà vẫn tự cập nhật; để trống thì mail không thừa dòng trắng."""
    for loai in sm.LOAI:
        v = {**CA_HOT, "hop_dong": "X1", "tinh_huong": "Hiện khách cần gấp."} if loai == "ca_hot" else {"tinh_huong": "Hiện khách cần gấp."}
        goc = sm.dung(loai, v)["text"]
        co = sm.dung(loai, {**v, "y_them": "Khách quen, nhờ anh ưu tiên giúp em.\nEm cảm ơn."})["text"]
        assert "Khách quen" not in goc and "\n\n\n" not in goc
        assert co.index("Khách quen") < co.index("Trân trọng" if loai == "ha_tang_moi" else "Em xin chân thành cảm ơn")      # mẫu đầu tư tập điểm mới kết bằng "Em cảm ơn ... Trân trọng."
        assert "Khách quen, nhờ anh ưu tiên giúp em.\nEm cảm ơn." in co


def test_ban_xem_truoc_ve_tren_trinh_duyet_dung_dam_xuong_dong_va_o_thieu():
    """soan_mail.js vẽ thư từ `doan` của máy chủ: chữ đậm, xuống dòng, ô còn trống tô nổi, ký tự HTML bị thoát."""
    import json
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("Máy không có Node để chạy phần vẽ thư của trình duyệt")
    kq = sm.dung("ca_hot", {**CA_HOT, "hop_dong": "", "tinh_huong": "Cần <gấp> & sớm"})
    code = ("const m=require(process.argv[1]);let d='';process.stdin.on('data',c=>d+=c).on('end',()=>console.log(m.htmlThan(JSON.parse(d))));")
    js = Path(__file__).resolve().parent.parent / "assets" / "soan_mail.js"
    out = subprocess.run([node, "-e", code, str(js)], input=json.dumps(kq["doan"]), capture_output=True, text=True,
                         encoding="utf-8", check=True).stdout
    assert '<span class="sm-thieu">[Mã hợp đồng]</span>' in out and "<br>" in out
    assert "Cần &lt;gấp&gt; &amp; sớm" in out and out.count("<p>") == len(kq["doan"])


def test_link_outlook_web_dien_san_den_cc_tieu_de_noi_dung():
    """Nút Mở thư trong Outlook: thư mới trên Outlook web có sẵn Đến, CC, tiêu đề, nội dung (sale đỡ điền / dán lại)."""
    import json
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("Máy không có Node")
    code = ("const m=require(process.argv[1]);"
            "console.log(JSON.stringify({a:m.taoLinkOutlook(['a@fpt.com','b@fpt.com'],['c@fpt.com'],'HĐ X1 & gấp','Dear anh,\\n\\nEm cảm ơn'),"
            "b:m.taoLinkOutlook(['a@fpt.com'],[],'T',''),c:m.danhSach('a@x.vn; b@x.vn ;'),"
            "d:m.taoLinkOutlook(['a@fpt.com'],[],'T','ế'.repeat(5000))}))")
    js = Path(__file__).resolve().parent.parent / "assets" / "sao_chep.js"
    o = json.loads(subprocess.run([node, "-e", code, str(js)], capture_output=True, text=True, encoding="utf-8", check=True).stdout)
    from urllib.parse import quote
    goc = "https://outlook.office.com/mail/deeplink/compose?mailtouri="
    mt = ("mailto:a@fpt.com,b@fpt.com?cc=c@fpt.com&subject=H%C4%90%20X1%20%26%20g%E1%BA%A5p"
          "&body=Dear%20anh%2C%0D%0A%0D%0AEm%20c%E1%BA%A3m%20%C6%A1n")
    assert o["a"] == goc + quote(mt, safe="")                      # CC nằm trong mailto: Outlook web chỉ đọc đủ CC theo đường này
    assert o["b"] == goc + quote("mailto:a@fpt.com?subject=T", safe="") and o["c"] == ["a@x.vn", "b@x.vn"]
    assert o["d"] == goc + quote("mailto:a@fpt.com?subject=T", safe="")      # nội dung quá dài: bỏ khỏi link, vẫn có trong clipboard


def test_nvkd_ibb7_luon_cc_phuc_con_admin_thi_khong():
    """Chủ app chốt 10/10/2026: tài khoản nvkd IBB7 phải CC PhucVHD@fpt.com. Gộp ở bản sao hiển thị, không lưu vào danh sách của sale."""
    nvkd = SimpleNamespace(role="nvkd", phong_soan_mail=lambda: ["IBB7"])
    khac = SimpleNamespace(role="nvkd", phong_soan_mail=lambda: ["IBB2"])
    admin = SimpleNamespace(role="admin", phong_soan_mail=lambda: ["IBB7"])
    assert [p["email"] for p in sm.cc_bat_buoc(nvkd)] == ["PhucVHD@fpt.com"] and sm.cc_bat_buoc(khac) == [] and sm.cc_bat_buoc(admin) == []
    goc = {"den": [{"ten": "A", "email": "a@fpt.com"}], "cc": [{"ten": "B", "email": "b@fpt.com"}]}
    g = sm.gop_cc_bat_buoc(goc, nvkd)
    assert [p["email"] for p in g["cc"]] == ["b@fpt.com", "PhucVHD@fpt.com"] and g["cc"][1]["khoa"] and len(goc["cc"]) == 1
    cu = {"den": [], "cc": [{"ten": "P", "email": "phucvhd@FPT.com"}]}               # đã tự thêm: không nhân đôi
    assert len(sm.gop_cc_bat_buoc(cu, nvkd)["cc"]) == 1
    assert sm.gop_cc_bat_buoc({}, admin) == {"den": [], "cc": []}


def test_cc_bat_buoc_ap_dung_voi_tai_khoan_that():
    import json

    from app.auth import SessionUser

    def tk(role, scope):
        return SessionUser(SimpleNamespace(id=1, username=f"kiemthu.{role}", ho_ten="K", role=role, ma_nv=None,
                                           session_version=0, scope=json.dumps(scope)))
    assert [p["email"] for p in sm.cc_bat_buoc(tk("nvkd", ["IBB7"]))] == ["PhucVHD@fpt.com"]
    assert sm.cc_bat_buoc(tk("nvkd", ["IBB2"])) == [] and sm.cc_bat_buoc(tk("admin", [])) == []


def test_goi_y_gon_trong_mot_nut_xo_xuong_moi_nguoi_mot_dong_co_den_cc():
    from app.ui.pages import soanmail
    g = {"den": [{"ten": "A", "email": "a@fpt.com", "chuc_vu": "Đội trưởng"}], "cc": [{"ten": "B", "email": "b@fpt.com", "chuc_vu": ""}],
         "don_vi": "Đà Nẵng", "khu_vuc_ro": True}
    kq = soanmail._goi_y_khung(g)
    assert len(kq) == 1 and kq[0].className == "sm-gy-dd"
    dong = kq[0].children[1].children
    assert [d.to_plotly_json()["props"]["data-email"] for d in dong] == ["a@fpt.com", "b@fpt.com"]
    assert [b.to_plotly_json()["props"]["data-vt"] for b in dong[0].children[1:]] == ["den", "cc"]       # nút chính theo gợi ý, nút kia đổi vị trí
    assert [b.to_plotly_json()["props"]["data-vt"] for b in dong[1].children[1:]] == ["cc", "den"]
    assert "Chưa có gợi ý" in soanmail._goi_y_khung({"den": [], "cc": [], "don_vi": "X", "khu_vuc_ro": True})[0].children


MOI = {"hop_dong": "CMAAE5918", "ten_kh": "Ngô Lâm Thái Bảo", "sdt": "0372256684", "dia_chi": "Ấp 5, Xã Mỹ Hạnh, Tây Ninh",
       "toa_do": "(10.8304167, 106.4760000)", "chao": "anh Thịnh"}


def test_mail_dau_tu_tap_diem_moi_dung_theo_mail_mau_cua_chu_app():
    """Chủ app 16/10/2026: thêm mẫu "hỗ trợ đầu tư tập điểm mới" vào nhóm Xin đầu tư hạ tầng (cạnh mẫu nâng cấp tập điểm)."""
    kq = sm.dung("ha_tang_moi", MOI)
    assert kq["thieu"] == [] and kq["tieu_de"] == "CMAAE5918 - XIN HỖ TRỢ ĐẦU TƯ TẬP ĐIỂM MỚI"
    t = kq["text"]
    assert t.startswith("Dear anh Thịnh,\n\nEm có hợp đồng khách hàng đăng ký lắp mới Internet tại khu vực:\n• Tên KH: Ngô Lâm Thái Bảo\n• SĐT: 0372256684\n"
                        "• Địa chỉ: Ấp 5, Xã Mỹ Hạnh, Tây Ninh\n• Tọa độ: (10.8304167, 106.4760000)")
    assert "Khách hàng đã xác nhận nhu cầu sử dụng thực tế và sẵn sàng triển khai dịch vụ." in t
    assert "Bên cạnh nhu cầu của khách hàng hiện hữu, khu vực này còn có nhiều hộ dân đang sinh sống" in t       # câu mẫu khi sale không gõ gì
    assert "Kính mong anh Thịnh xem xét hỗ trợ phương án đầu tư tập điểm mới" in t
    assert t.endswith("Em cảm ơn anh Thịnh.\nTrân trọng.")
    rieng = sm.dung("ha_tang_moi", {**MOI, "tinh_huong": "Khu vực nhiều nhà trọ công nhân."})["text"]
    assert "Khu vực nhiều nhà trọ công nhân." in rieng and "Bên cạnh nhu cầu của khách hàng hiện hữu" not in rieng       # sale gõ thì thay câu mẫu
    assert "[Tên khách hàng]" in sm.dung("ha_tang_moi", {**MOI, "ten_kh": ""})["text"]


def test_hai_mau_ha_tang_chung_mot_the_nhung_hai_bieu_mau_rieng():
    from app.ui.pages import soanmail
    nhom = dict(sm.nhom_mau())
    assert nhom["ha_tang"] == ["ha_tang", "ha_tang_moi"] and nhom["ca_hot"] == ["ca_hot"] and len(nhom) == 3        # vẫn ba thẻ chọn
    the = soanmail._chon_loai().children
    ha = next(t for t in the if getattr(t, "className", "").startswith("sm-loai-the") and t.to_plotly_json()["props"].get("data-loai") == "ha_tang")
    assert ha.to_plotly_json()["props"]["data-nhom"] == "ha_tang ha_tang_moi"
    for k in ("ha_tang", "ha_tang_moi"):
        con = soanmail._o_form(k).children[0]                                    # hai nút nhỏ đổi mẫu nằm đầu biểu mẫu
        assert [b.children for b in con.children] == ["Nâng cấp tập điểm", "Đầu tư tập điểm mới"]
        assert [("chon" in b.className) for b in con.children] == [k == "ha_tang", k == "ha_tang_moi"]
    assert len(soanmail._o_form("hoa_don").children) == 3                         # mẫu đứng một mình không có nút đổi mẫu
    assert sm.goi_y("ha_tang_moi", "Đà Nẵng", "")["don_vi"] == "Đà Nẵng"           # gợi ý người nhận dùng chung quy tắc hạ tầng
