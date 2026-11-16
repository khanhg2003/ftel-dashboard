"""Khối làm việc của app: Kinh doanh (KD), Dịch vụ khách hàng (DVKH), Kỹ thuật (KT).

Mỗi khối có bộ trang và menu riêng. Quản trị (BGĐ) chuyển được giữa các khối; tài khoản của một khối chỉ thấy khối mình.
Đường dẫn quyết định khối: `/dvkh...` là DVKH, `/kt...` là Kỹ thuật, trang dùng chung (tài khoản, hướng dẫn, quản trị)
không thuộc khối nào và giữ nguyên khối đang xem. Thêm khối mới = thêm một mục vào `KHOI` và một mảng menu.
"""
from __future__ import annotations

KD, DVKH, KT = "KD", "DVKH", "KT"
KHOI = {
    KD: {"ten": "Kinh doanh", "ten_day_du": "Khối Kinh doanh", "mo_ta": "Sales & HR Performance", "trang_chu": "/", "tien_to": "", "san_sang": True,
         "ten_ngan": "Khối KD"},
    DVKH: {"ten": "Dịch vụ khách hàng", "ten_day_du": "Khối Dịch vụ khách hàng", "mo_ta": "Customer Service Control", "trang_chu": "/dvkh",
           "tien_to": "/dvkh", "san_sang": True, "ten_ngan": "Khối DVKH"},
    KT: {"ten": "Kỹ thuật", "ten_day_du": "Khối Kỹ thuật", "mo_ta": "Technical Operations", "trang_chu": "/kt", "tien_to": "/kt", "san_sang": True,
         "ten_ngan": "Khối KT"},
}
THU_TU = [KD, DVKH, KT]
TRANG_DUNG_CHUNG = {"/taikhoan", "/huongdan", "/quantri", "/settings", "/phanhoi", "/lienkhoi"}


def khoi_cua_duong_dan(path: str) -> str | None:
    """Khối của một đường dẫn; None nếu là trang dùng chung."""
    path = path or "/"
    for k in (DVKH, KT):
        t = KHOI[k]["tien_to"]
        if path == t or path.startswith(t + "/"):
            return k
    return None if path in TRANG_DUNG_CHUNG else KD


# (nhóm, [(đường dẫn, nhãn, icon, quyền)]) - quyền là tên thuộc tính của người dùng, None = ai vào khối cũng thấy
NAV_DVKH = [
    ("Điều hành", [("/dvkh", "Tổng quan KPI", "dashboard", None), ("/dvkh/nhan-su", "Hiệu suất CSKH", "users", None)]),
    ("4 nhóm KPI", [("/dvkh/sr-bi-dong", "SR bị động", "inbox", None), ("/dvkh/sr-chu-dong", "SR chủ động", "phone", None),
                    ("/dvkh/roi-mang", "Rời mạng", "trend", None), ("/dvkh/cong-no", "Công nợ", "wallet", None)]),
    ("Phân tích", [("/dvkh/insight", "Nhận định & phân tích sâu", "pie", None)]),
    ("Liên khối", [("/lienkhoi", "Điều hành liên khối", "trend", "settings")]),
    ("Dữ liệu", [("/dvkh/nap", "Cập nhật Excel", "upload", "duoc_nap_dvkh")]),
    ("Hệ thống", [("/quantri", "Quản trị", "settings", "settings"), ("/phanhoi", "Phản hồi", "phan_hoi", "settings")]),
]
NAV_KT = [
    ("Điều hành", [("/kt", "Tổng quan Kỹ thuật", "dashboard", None), ("/kt/nhan-su", "Hiệu suất KTV", "users", None)]),
    ("Chỉ số", [("/kt/ton", "Tồn và lịch hẹn", "inbox", None), ("/kt/phau", "Phễu triển khai", "trend", None), ("/kt/cham-do-ai", "Chậm do ai", "alert", None),
                ("/kt/trien-khai", "Triển khai đúng hẹn", "check", None),
                ("/kt/su-co", "Sự cố và checklist", "tool", None)]),
    ("Liên khối", [("/lienkhoi", "Điều hành liên khối", "trend", "settings")]),
    ("Hệ thống", [("/quantri", "Quản trị", "settings", "settings"), ("/phanhoi", "Phản hồi", "phan_hoi", "settings")]),
]
