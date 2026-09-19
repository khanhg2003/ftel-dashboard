"""Mã tỉnh trong cột CN Quản lý (phần trước dấu '_': DNG_01 -> DNG, HCM_08 -> HCM) -> tên tỉnh.

Dùng tên tỉnh cũ (trước sáp nhập 2025) vì mã chi nhánh FPT vẫn theo tỉnh cũ. Mã chưa có trong bảng thì hiện
nguyên mã để dễ phát hiện và bổ sung.
"""
from __future__ import annotations

TEN_TINH = {
    "AGG": "An Giang", "BDG": "Bình Dương", "BDH": "Bình Định", "BGG": "Bắc Giang", "BLU": "Bạc Liêu",
    "BNH": "Bắc Ninh", "BPC": "Bình Phước", "BTE": "Bến Tre", "BTN": "Bình Thuận", "CBG": "Cao Bằng",
    "CMU": "Cà Mau", "CTO": "Cần Thơ", "DBN": "Điện Biên", "DKG": "Đắk Nông", "DLK": "Đắk Lắk",
    "DNG": "Đà Nẵng", "DNI": "Đồng Nai", "DTP": "Đồng Tháp", "GLI": "Gia Lai", "HAG": "Hà Giang",
    "HBH": "Hoà Bình", "HCM": "Hồ Chí Minh", "HDG": "Hải Dương", "HGG": "Hậu Giang", "HNI": "Hà Nội",
    "HNM": "Hà Nam", "HPG": "Hải Phòng", "HTH": "Hà Tĩnh", "HUE": "Huế", "HYN": "Hưng Yên",
    "KGG": "Kiên Giang", "KHA": "Khánh Hoà", "KTM": "Kon Tum", "LAN": "Long An", "LCI": "Lào Cai",
    "LDG": "Lâm Đồng", "LSN": "Lạng Sơn", "NAN": "Nghệ An", "NBH": "Ninh Bình", "NDH": "Nam Định",
    "NTN": "Ninh Thuận", "PTO": "Phú Thọ", "PYN": "Phú Yên", "QBH": "Quảng Bình", "QNH": "Quảng Ninh",
    "QNI": "Quảng Ngãi", "QNM": "Quảng Nam", "QTI": "Quảng Trị", "SLA": "Sơn La", "STG": "Sóc Trăng",
    "TBH": "Thái Bình", "TGG": "Tiền Giang", "THA": "Thanh Hoá", "TNH": "Tây Ninh", "TNN": "Thái Nguyên",
    "TQG": "Tuyên Quang", "TVH": "Trà Vinh", "VLG": "Vĩnh Long", "VPC": "Vĩnh Phúc", "VTU": "Vũng Tàu",
    "YBI": "Yên Bái", "LCU": "Lai Châu", "BKN": "Bắc Kạn", "DNO": "Đắk Nông",
}
NOI_TINH = {"DNG", "QNM"}           # địa bàn của chi nhánh (Đà Nẵng + Quảng Nam)


def ma_tinh(cn) -> str:
    s = str(cn or "").strip().upper()
    return s.split("_")[0] if s else ""


def ten_tinh(ma: str) -> str:
    return TEN_TINH.get(ma, ma or "Không rõ")
