"""Nội dung tin trả lời của bot Zalo Tra cứu giá (chốt 05/11/2026): chữ trơn, mỗi tin tối đa 2.000 ký tự.

Chỉ DỰNG CHỮ từ dữ liệu `app/gia_fpt.py` (không tự tính giá, không viết lại công thức phí). Phí hòa mạng thiếu thì ghi
"chưa rõ, xem fpt.vn", không bao giờ ghi "Miễn phí" khi chỉ là mất dòng (quy tắc ở AGENTS.md, mục Tra cứu giá).
Giai đoạn 2 sẽ thêm ảnh banner gói: chỗ cắm là `anh_banner_goi` (chưa dựng ảnh).
"""
from __future__ import annotations

from app import gia_fpt as gf
from app.thoi_gian import chu_gio_vn

TOI_DA_TIN = 1900                  # Zalo cho 2.000; chừa chỗ cho đầu đề "(2/3)"
CHUA_RO = "Chưa rõ, xem trên fpt.vn"

HUONG_DAN = (
    "Mình tra giá gói cước FPT theo phường/xã, lấy trực tiếp từ fpt.vn.\n"
    "Cách hỏi (trong nhóm nhớ @ tên bot):\n"
    "1) Giá cước Giga ở phường Hải Châu, Đà Nẵng\n"
    "2) Giá Meta F1 xã Quế Sơn\n"
    "3) Giá gói doanh nghiệp phường Nam Nha Trang, Khánh Hòa\n"
    "Chỉ gõ \"giá + phường\" thì mình liệt kê các gói. Gõ thêm tên gói để xem chi tiết: giá từng cách thanh toán, "
    "số tháng được tặng, phí hòa mạng.\n"
    "Lệnh: /help xem hướng dẫn · /id xem mã chat")

CHUA_CAP_QUYEN = "Chat này chưa được cấp quyền. Mã chat: {id}. Gửi mã này cho Admin để được mở."


def anh_banner_goi(goi: dict, ct: dict | None) -> None:
    """Giai đoạn 2: dựng ảnh banner của gói để gửi kèm. Chưa làm, để sẵn chỗ cắm."""
    return None


def chia_tin(khoi: list[str], toi_da: int = TOI_DA_TIN) -> list[str]:
    """Gộp các khối chữ thành các tin ≤ `toi_da` ký tự, không cắt giữa một dòng. Nhiều tin thì thêm "(1/3)" ở đầu."""
    tin: list[str] = []
    hien = ""
    for k in (x.strip() for x in khoi if x and x.strip()):
        manh = [k] if len(k) <= toi_da else _chia_dong(k, toi_da)
        for m in manh:
            if hien and len(hien) + 2 + len(m) > toi_da:
                tin.append(hien)
                hien = m
            else:
                hien = f"{hien}\n\n{m}" if hien else m
    if hien:
        tin.append(hien)
    if len(tin) > 1:
        tin = [f"({i}/{len(tin)}) {t}" for i, t in enumerate(tin, 1)]
    return tin


def _chia_dong(k: str, toi_da: int) -> list[str]:
    ra, hien = [], ""
    for dong in k.split("\n"):
        dong = dong[:toi_da]
        if hien and len(hien) + 1 + len(dong) > toi_da:
            ra.append(hien)
            hien = dong
        else:
            hien = f"{hien}\n{dong}" if hien else dong
    return ra + ([hien] if hien else [])


def _gia(g: dict) -> str:
    return f"{gf.chu_tien(g['gia'])}/tháng" if g.get("gia") is not None else "chưa rõ giá"


def _dong_thanh_toan(z: dict) -> str:
    nhan = gf.nhan_thoi_han(z["hinh_thuc"], z["thang"])
    tong = gf.chu_tien(z["tong"]) if z.get("tong") else "chưa rõ"
    if gf._la_tra_sau(z["hinh_thuc"], z["thang"]):
        d = f"• {nhan}: {tong}/tháng"
    else:
        d = f"• {nhan}: {tong}"
        if z.get("tang") and z.get("thang_dong"):
            d += f" (đóng {z['thang_dong']:g} tháng, tặng {z['tang']:g} tháng)"
    return d + (f" · {z['qua']}" if z.get("qua") else "")


def _han_chinh_sach(lua_chon: list[dict]) -> str:
    den = sorted({z["den"] for z in lua_chon if z.get("den")}, key=lambda x: (x[6:], x[3:5], x[:2]))
    if not den:
        return ""
    return f"Chính sách áp dụng đến hết {den[0]}" if len(den) == 1 else f"Chính sách sớm nhất hết hạn {den[0]}"


def chi_tiet(g: dict, ct: dict | None, vi_tri: str) -> str:
    """Một gói: tốc độ, giá tháng, phí hòa mạng, từng cách thanh toán (tổng tiền, tháng tặng), hạn, thiết bị / quà."""
    dong = [f"📦 {g['ten']} - {vi_tri}"]
    dong.append(" · ".join(x for x in (f"Tốc độ: {g['toc_do']}" if g.get("toc_do") else "", f"Giá: {_gia(g)}") if x))
    if ct is None:
        dong.append(f"Phí hòa mạng: {CHUA_RO}")
        dong.append("Chưa lấy được chính sách chi tiết của gói này, xem thêm trên fpt.vn.")
        return "\n".join(dong)
    dong.append("Phí hòa mạng: " + (gf.chu_phi_hoa_mang(ct, True) or CHUA_RO))
    dong.append("Cách thanh toán:")
    dong += [_dong_thanh_toan(z) for z in ct["lua_chon"]]
    if ct.get("thiet_bi"):
        dong.append(f"Thiết bị đi kèm: {gf.chu_khoang(ct['thiet_bi'])}")
    if g.get("uu_dai"):
        dong.append(f"Ưu đãi: {g['uu_dai']}")
    if han := _han_chinh_sach(ct["lua_chon"]):
        dong.append(han)
    return "\n".join(dong)


def danh_sach(nhom: dict[str, list[dict]], vi_tri: str, tieu_de: str = "") -> list[str]:
    """Các khối chữ liệt kê gói theo nhóm như trang Tra cứu giá (mỗi nhóm một khối); gói nằm ở nhiều nhóm thì hiện ở mỗi nhóm."""
    khoi = [tieu_de or f"📋 Các gói đang bán tại {vi_tri}:"]
    for ten_nhom, goi in nhom.items():
        dong = [ten_nhom]
        dong += [f"• {g['ten']}: {_gia(g)}" + (f" - {g['toc_do']}" if g.get("toc_do") else "") for g in goi]
        khoi.append("\n".join(dong))
    khoi.append("Gõ thêm tên gói để xem chi tiết, ví dụ: giá Giga phường " + vi_tri.split(",")[0].split(" ", 1)[-1] + ".")
    return khoi


def danh_sach_don(goi: list[dict]) -> str:
    return "\n".join(f"• {g['ten']}: {_gia(g)}" for g in goi)


def lua_chon(tieu_de: str, nhan: list[str], con_lai: int = 0) -> str:
    d = [tieu_de] + [f"{i}. {n}" for i, n in enumerate(nhan, 1)]
    if con_lai:
        d.append(f"(còn {con_lai} kết quả khác, gõ rõ hơn để thu hẹp)")
    d.append("Trả lời bằng số (trả lời trực tiếp tin này của bot).")
    return "\n".join(d)


def chan_trang(luc, cu: bool = False) -> str:
    gio = chu_gio_vn(luc)
    chu = "Giá lấy từ fpt.vn" + (f" lúc {gio}" if gio else "") + ", đã gồm VAT."
    return chu + (" Lần này fpt.vn chưa trả lời kịp nên dùng bản lấy trước đó." if cu else "")

