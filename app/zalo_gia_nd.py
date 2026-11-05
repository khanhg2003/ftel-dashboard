"""Nội dung tin trả lời của bot Zalo Tra cứu giá (chốt 05/11/2026): mỗi tin tối đa 1.900 ký tự.

Danh sách và chi tiết gói dùng `text_styles` của Zalo (tên đậm, GIÁ đậm + cam + cỡ lớn) qua `ban_tin._Soan` / `TinZalo` (đã có sẵn cho
Bản tin): tổng kiểu mỗi tin giữ dưới `TRAN_KIEU` (quá thì `_giam_kieu` bỏ cỡ chữ / đậm phụ trước, giữ giá); Zalo từ chối thì
`zalo_bot.gui_tin_du_phong` gửi lại chữ trơn. Tin hướng dẫn / hỏi lại / báo lỗi là chữ trơn.

Chỉ DỰNG CHỮ từ dữ liệu `app/gia_fpt.py` (không tự tính giá, không viết lại công thức phí). Phí hòa mạng thiếu thì ghi
"Chưa rõ, xem trên fpt.vn", không bao giờ ghi "Miễn phí" khi chỉ là mất dòng (quy tắc ở AGENTS.md, mục Tra cứu giá).
Giai đoạn 2 sẽ thêm ảnh banner gói: chỗ cắm là `anh_banner_goi` (chưa dựng ảnh).
"""
from __future__ import annotations

from app import ban_tin as bt
from app import gia_fpt as gf
from app.thoi_gian import chu_gio_vn

TOI_DA_TIN = 1900                  # Zalo cho 2.000; chừa chỗ cho đầu đề "(2/3)"
TRAN_KIEU = 35                     # dưới trần 40 của Bản tin: Zalo từ chối tin có quá nhiều kiểu chữ
KIEU_GIA = ("b", "c_f27806")      # giá: đậm + cam, cỡ chữ thường (chủ app 05/11/2026: cỡ lớn chiếm chỗ)
CHUA_RO = "Chưa rõ, xem trên fpt.vn"

HUONG_DAN = (
    "Mình tra giá gói cước FPT theo phường/xã, lấy trực tiếp từ fpt.vn.\n"
    "Cách hỏi (trong nhóm nhớ @ tên bot):\n"
    "1) Giá cước Giga ở phường Hải Châu, Đà Nẵng\n"
    "2) Giá Meta F1 xã Quế Sơn\n"
    "3) Giá gói gia đình phường Nam Nha Trang, Khánh Hòa\n"
    "Chỉ gõ \"giá + phường\" thì mình liệt kê các gói. Gõ thêm tên gói để xem chi tiết: giá từng cách thanh toán, "
    "số tháng được tặng, phí hòa mạng.\n"
    "Lệnh: /help xem hướng dẫn · /id xem mã chat")

CHUA_CAP_QUYEN = "Chat này chưa được cấp quyền. Mã chat: {id}. Gửi mã này cho Admin để được mở."


def anh_banner_goi(goi: dict, ct: dict | None) -> None:
    """Giai đoạn 2: dựng ảnh banner của gói để gửi kèm. Chưa làm, để sẵn chỗ cắm."""
    return None


# ------------------------------------------------------------------ ghép dòng / khối / tin
def dong_chu(chu: str) -> "bt._Soan":
    return _dong(chu)


def _dong(*phan) -> "bt._Soan":
    """Một dòng từ các đoạn: chuỗi trơn, hoặc (chữ, kiểu...) cho đoạn có kiểu."""
    s = bt._Soan()
    for p in phan:
        if isinstance(p, str):
            s.them(p)
        else:
            s.them(p[0], *p[1:])
    return s


def _chu(dong: "bt._Soan") -> str:
    return "".join(c for c, _ in dong.phan)


def _ghep(khoi: list[list]) -> "bt._Soan":
    """Các khối (mỗi khối là danh sách dòng): dòng cách nhau một xuống dòng, khối cách nhau một dòng trống."""
    s = bt._Soan()
    for i, k in enumerate(khoi):
        for j, d in enumerate(k):
            if i or j:
                s.them("\n\n" if j == 0 else "\n")
            s.phan.extend(d.phan)
    return s


def _chia_khoi(k: list, toi_da: int) -> list[list]:
    ra, hien = [], []
    for d in k:
        if hien and len(_chu(_ghep([hien + [d]]))) > toi_da:
            ra.append(hien)
            hien = []
        hien.append(d)
    return ra + ([hien] if hien else [])


def chia_tin(khoi: list[list], toi_da: int = TOI_DA_TIN) -> list:
    """Gộp các khối thành các tin ≤ `toi_da` ký tự, không cắt giữa một dòng. Nhiều tin thì thêm "(1/3)" ở đầu. Trả về `TinZalo` (có `.kieu`)."""
    cac: list[list[list]] = []
    for k in (x for x in khoi if x):
        for m in (_chia_khoi(k, toi_da) if len(_chu(_ghep([k]))) > toi_da else [k]):
            if cac and len(_chu(_ghep(cac[-1] + [m]))) <= toi_da:
                cac[-1].append(m)
            else:
                cac.append([m])
    tin = []
    for i, c in enumerate(cac, 1):
        t = _ghep(c).xong()
        if len(cac) > 1:
            t = bt._voi_dau(f"({i}/{len(cac)}) ", t)
        t.kieu = bt._giam_kieu(t.kieu, TRAN_KIEU)
        tin.append(t)
    return tin


# ------------------------------------------------------------------ nội dung
def toc_do_gon(toc_do: str | None) -> str:
    """"300 Mbps / 300 Mbps" -> "300 Mbps"; hai chiều khác nhau thì giữ cả hai."""
    phan = [x.strip() for x in (toc_do or "").split("/") if x.strip()]
    return phan[0] if phan and len(set(phan)) == 1 else " / ".join(phan)


def _gia(g: dict) -> str:
    return gf.chu_tien(g["gia"]) if g.get("gia") is not None else "chưa rõ giá"


def dong_goi(g: dict) -> "bt._Soan":
    """Một gói một dòng ngắn: tên đậm, giá nổi, tốc độ gọn."""
    toc = toc_do_gon(g.get("toc_do"))
    return _dong("• ", (g["ten"], "b"), ": ", (_gia(g), *KIEU_GIA), "/tháng" if g.get("gia") is not None else "", f" · {toc}" if toc else "")


def _dong_thanh_toan(z: dict) -> "bt._Soan":
    nhan = gf.nhan_thoi_han(z["hinh_thuc"], z["thang"])
    tong = gf.chu_tien(z["tong"]) if z.get("tong") else "chưa rõ"
    tra_sau = gf._la_tra_sau(z["hinh_thuc"], z["thang"])
    phan = ["• ", f"{nhan} · ", (tong + ("/tháng" if tra_sau else ""), "b")]
    if not tra_sau and z.get("tang") and z.get("thang_dong"):
        phan.append(f" (đóng {z['thang_dong']:g}, tặng {z['tang']:g})")
    if z.get("qua"):
        phan.append(f" · {z['qua']}")
    return _dong(*phan)


def _han_chinh_sach(lua_chon: list[dict]) -> str:
    den = sorted({z["den"] for z in lua_chon if z.get("den")}, key=lambda x: (x[6:], x[3:5], x[:2]))
    if not den:
        return ""
    return f"Chính sách áp dụng đến hết {den[0]}" if len(den) == 1 else f"Chính sách sớm nhất hết hạn {den[0]}"


def chi_tiet(g: dict, ct: dict | None, vi_tri: str) -> list:
    """Một gói (một khối dòng): tiêu đề, giá tháng nổi, tốc độ, phí hòa mạng, từng cách thanh toán, thiết bị / ưu đãi, hạn."""
    dong = [_dong("📦 ", (f"{g['ten']} - {vi_tri}", "b")),
            _dong("Giá tháng: ", (_gia(g), *KIEU_GIA), "/tháng" if g.get("gia") is not None else "")]
    if g.get("toc_do"):
        dong.append(_dong(f"Tốc độ: {toc_do_gon(g['toc_do'])}"))
    if ct is None:
        dong.append(_dong("Phí hòa mạng: ", (CHUA_RO, "b")))
        dong.append(_dong("Chưa lấy được chính sách chi tiết của gói này, xem thêm trên fpt.vn."))
        return dong
    dong.append(_dong("Phí hòa mạng: ", (gf.chu_phi_hoa_mang(ct, True) or CHUA_RO, "b")))
    dong.append(_dong("Cách thanh toán:"))
    dong += [_dong_thanh_toan(z) for z in ct["lua_chon"]]
    if ct.get("thiet_bi"):
        dong.append(_dong(f"Thiết bị đi kèm: {gf.chu_khoang(ct['thiet_bi'])}"))
    if g.get("uu_dai"):
        dong.append(_dong(f"Ưu đãi: {g['uu_dai']}"))
    if han := _han_chinh_sach(ct["lua_chon"]):
        dong.append(_dong(han))
    return dong


def danh_sach(nhom: dict[str, list[dict]], vi_tri: str, tieu_de: str = "") -> list[list]:
    """Các khối liệt kê gói theo nhóm (mỗi nhóm một khối, mỗi gói một dòng); `nhom` đã loại trùng ở `zalo_gia.nhom_hien`."""
    khoi = [[_dong((tieu_de or f"📋 Các gói đang bán tại {vi_tri}:", "b"))]]
    for ten_nhom, goi in nhom.items():
        khoi.append([_dong((ten_nhom, "b"))] + [dong_goi(g) for g in goi])
    khoi.append([_dong("Gõ tên gói để xem chi tiết, ví dụ: giá Giga phường " + vi_tri.split(",")[0].split(" ", 1)[-1] + ".")])
    return khoi


def danh_sach_don(goi: list[dict]) -> list:
    return [dong_goi(g) for g in goi]


def lua_chon(tieu_de: str, nhan: list[str], con_lai: int = 0) -> str:
    d = [tieu_de] + [f"{i}. {n}" for i, n in enumerate(nhan, 1)]
    if con_lai:
        d.append(f"(còn {con_lai} kết quả khác, gõ rõ hơn để thu hẹp)")
    d.append("Trả lời bằng số (trả lời trực tiếp tin này của bot).")
    return "\n".join(d)


def chan_trang(luc, cu: bool = False) -> list:
    gio = chu_gio_vn(luc)
    chu = "Giá lấy từ fpt.vn" + (f" lúc {gio}" if gio else "") + ", đã gồm VAT."
    return [_dong(chu + (" Lần này fpt.vn chưa trả lời kịp nên dùng bản lấy trước đó." if cu else ""))]
