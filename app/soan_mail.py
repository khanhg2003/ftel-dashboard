"""Soạn email cho nhân viên KD (chốt 10/10/2026; người dùng: admin + nvkd IBB7, `auth.duoc_soan_mail`).

Bốn thẻ mail mẫu (từ mail thật chủ app đưa): ca hot triển khai, xin xuất hoá đơn doanh nghiệp, xin đầu tư hạ tầng, xin hỗ trợ thêm bộ phát (17/10/2026). Nhóm hạ tầng có HAI mẫu
(chủ app 16/10/2026): nâng cấp tập điểm đầy port (`ha_tang`) và hỗ trợ đầu tư tập điểm mới (`ha_tang_moi`), cùng một thẻ chọn, sale đổi qua lại bằng hai nút nhỏ
trong biểu mẫu. Sale chỉ điền các ô thay đổi; phần cố định do KHUÔN điền; người nhận chỉ GỢI Ý, sale tự chọn; xong bấm
Copy rồi dán vào Outlook. App KHÔNG gửi mail, không lưu nội dung mail (chỉ ghi nhật ký ai soạn loại nào, mã HĐ nào).

Fox chỉ viết MỘT đoạn "tình huống" từ ý chính của sale. Địa chỉ, SĐT, MST, tên khách không bao giờ gửi lên AI (quy tắc
dữ liệu khách của AGENTS.md): Fox chỉ thấy ý chính + hạn lắp + loại mail, và số dài 6 chữ số trở lên bị che trước khi gửi.
"""
from __future__ import annotations

import re

from app import danh_ba as db
from app import tro_ly as ai
from app.auth import ghi_log
from app.config import rules_config

LOAI_AI = "viet_mail"
TOI_DA_NGAY = 100                 # lượt Fox viết / ngày / tài khoản (tài khoản sale dùng chung cả phòng); admin không giới hạn
TOI_DA_Y = 600                    # ký tự ý chính sale gõ cho Fox
TOI_DA_DOAN = 1200                # ký tự đoạn tình huống
THIEU = "[{}]"                    # chỗ còn trống trong bản xem trước: [Mã hợp đồng]


def _o(khoa, nhan, goi_y="", dai=False, bat_buoc=True, mac_dinh=""):
    """Một ô sale điền. `mac_dinh` (chỉ cho ô không bắt buộc): để trống thì mail dùng chữ này."""
    return {"khoa": khoa, "nhan": nhan, "goi_y": goi_y, "dai": dai, "bat_buoc": bat_buoc, "mac_dinh": mac_dinh}


# Mỗi mẫu: `nhom` (có thì các mẫu cùng nhóm dùng chung MỘT thẻ chọn, `nhan_con` là tên nút nhỏ), ô sale điền (`truong`; `dai` = chiếm cả hàng), khuôn (`than`: mỗi phần tử một đoạn; **đậm**; {khoa} = ô điền; {?khoa} = bỏ cả đoạn nếu
# ô đó trống; {?y_them} là đoạn sale tự thêm), tiêu đề, gợi ý người nhận (`goi_y`: (nhóm chức danh, nơi)), và lời dặn Fox (`fox`).
LOAI = {
    "ca_hot": {
        "ten": "Ca hot triển khai",
        "truong": [_o("hop_dong", "Mã hợp đồng", "VD: DAAAP6381"),
                   _o("dia_chi", "Địa chỉ lắp đặt", "Số nhà, đường, quận / huyện, tỉnh", dai=True),
                   _o("han_lap", "Cần lắp trước", "VD: 17h chiều nay")],
        "y_chinh": "Tình huống (gõ ý chính, Fox viết giúp)",
        "y_mau": "khách chỉ rảnh chiều nay vì tăng ca cả tuần, không kịp thì huỷ, sợ mất khách sang đối thủ",
        "tieu_de": "{hop_dong} - CA HOT CẦN HỖ TRỢ LẮP ĐẶT TRƯỚC {han_lap}",
        "than": ["Dear {chao},", "Em có HĐ: **{hop_dong}**\nĐịa chỉ: {dia_chi}", "{tinh_huong}",
                 "{?y_them}", "Em xin chân thành cảm ơn ạ!"],
        "goi_y": {"den": [("doi_truong", "khu_vuc")], "cc": [("truong_phong_kt", "lap")]},
        "fox": ("Viết đoạn nêu ca hot: khách cần lắp gấp, hiện chưa có mốc hẹn phù hợp, sale đã care khách, và nhờ người nhận "
                "hỗ trợ phương án phân công kỹ thuật kịp thời gian để tránh khách huỷ hoặc lắp mạng đối thủ."),
        "vi_du": ("Ý chính: khách chỉ rảnh chiều nay, tăng ca cả tuần, không kịp thì huỷ. Hạn lắp: 17h chiều nay.\n"
                  "Đoạn: Hiện case này khách cần lắp đặt trong 17h chiều nay nhưng mốc tích hẹn xanh hôm nay không có, em có "
                  "care khách theo lịch xanh gần nhất nhưng khách báo chỉ sắp xếp được chiều nay vì đi làm tăng ca cả tuần, "
                  "nếu không lắp kịp thì hủy. Nhờ anh hỗ trợ phương án phân công kỹ thuật hỗ trợ ca vụ này trong chiều để "
                  "tránh khách hủy TSD và lắp mạng đối thủ ạ."),
    },
    "hoa_don": {
        "ten": "Xin xuất hoá đơn DN",
        "truong": [_o("hop_dong", "Mã hợp đồng", "VD: NTAAQ4015"),
                   _o("dia_chi", "Địa chỉ lắp đặt", "Số nhà, đường, phường / xã, tỉnh", dai=True),
                   _o("dia_chi_hd", "Địa chỉ xuất hoá đơn", "Địa chỉ trên giấy phép doanh nghiệp", dai=True),
                   _o("mst", "Mã số thuế", "VD: 4201591367"),
                   _o("sdt", "Số điện thoại khách", "VD: 0963901900"),
                   _o("goi_cuoc", "Gói cước", "VD: combo vvip no box SKY trả trước 6 tháng", dai=True)],
        "y_chinh": "Lý do / nhu cầu của khách (gõ ý chính, Fox viết giúp)",
        "y_mau": "khách chỉ đăng ký gói trả trước 6 tháng, đứng tên doanh nghiệp, dùng cho 3 máy tính nhân viên, đang mở thêm chi nhánh",
        "tieu_de": "{hop_dong} - HỖ TRỢ CF KHÁCH HÀNG LẮP GÓI CÁ NHÂN MUỐN XHĐ DOANH NGHIỆP",
        "than": ["Kính gửi {chao},",
                 "Em có HĐ: **{hop_dong}** muốn **lắp gói cá nhân nhưng xin đứng tên và xuất hóa đơn doanh nghiệp.**",
                 "{tinh_huong}",
                 "Địa chỉ lắp đặt: {dia_chi}\nĐịa chỉ xuất hóa đơn: **{dia_chi_hd}**\nMã số thuế: **{mst}**\nSố điện thoại: {sdt}\n"
                 "Gói cước: {goi_cuoc}",
                 "{?y_them}", "Em xin chân thành cảm ơn ạ!"],
        "goi_y": {"den": [("pho_giam_doc", "lap")], "cc": [("giam_doc", "lap"), ("giam_doc", "nha")]},
        "nhac": "Nhớ đính kèm ảnh CCCD hai mặt của chủ hợp đồng vào mail trong Outlook (app không lưu ảnh).",
        "fox": ("Viết đoạn nói rõ khách chỉ muốn đăng ký gói gì, đứng tên doanh nghiệp và xuất hoá đơn, nhu cầu sử dụng, rồi "
                "kính nhờ người nhận hỗ trợ CF sớm để sale lên hợp đồng và lắp đặt cho khách."),
        "vi_du": ("Ý chính: khách chỉ đăng ký gói trả trước 6 tháng, 3 máy tính nhân viên, đang mở nhiều chi nhánh, khách quý "
                  "đã lắp nhiều line.\nĐoạn: Hiện tại khách hàng chỉ muốn đăng ký gói trả trước 6 tháng và muốn đứng tên doanh "
                  "nghiệp + xuất hóa đơn, nhu cầu chủ yếu sử dụng cho 3 máy tính nội bộ nhân viên. Khách đang chuẩn bị mở "
                  "nhiều chi nhánh và muốn ủng hộ dịch vụ FPT lâu dài (khách quý đã lắp nhiều line doanh nghiệp và gia đình "
                  "trước đó), nên kính nhờ anh hỗ trợ CF giúp em sớm để em có thể lên hợp đồng và hỗ trợ lắp đặt sớm cho "
                  "khách hàng ạ."),
    },
    "ha_tang": {
        "ten": "Xin đầu tư hạ tầng",
        "nhom": "ha_tang", "nhan_con": "Nâng cấp tập điểm",
        "truong": [_o("hop_dong", "Mã hợp đồng", "VD: CMAAE5918"),
                   _o("dia_chi", "Địa chỉ lắp đặt", "Số nhà, đường, phường / xã, tỉnh", dai=True),
                   _o("tap_diem", "Tập điểm (TD)", "VD: CMUP003.0008/HO"),
                   _o("port_hien_tai", "Số port hiện có", "VD: 8"),
                   _o("port_nang_cap", "Nâng cấp lên (port)", "VD: 16"),
                   _o("thoi_gian_cho", "Khách có thể đợi", "VD: 2 đến 3 ngày")],
        "y_chinh": "Lý do khách cần gấp (không bắt buộc, trống thì dùng câu mẫu)",
        "y_mau": "khách cần sớm để làm việc và gia đình sử dụng",
        "y_tuy_chon": True,
        "mac_dinh": "hiện khách đang cần sớm để phục vụ cho công việc và gia đình sử dụng, có thể đợi khoảng {thoi_gian_cho}.",
        "tieu_de": "{hop_dong} - ĐỀ NGHỊ NÂNG CẤP TẬP ĐIỂM {tap_diem} LÊN {port_nang_cap} PORT",
        "than": ["Dear {chao},", "Em có HĐ: **{hop_dong}**\nĐịa chỉ: {dia_chi}",
                 "Hiện kỹ thuật qua khảo sát báo lại nhà KH kéo về TD **{tap_diem}** hiện đang full {port_hien_tai} port cần "
                 "nâng cấp để có thể triển khai cho khách hàng, nhờ {chao} hỗ trợ phương án nâng cấp tập điểm **{tap_diem}** "
                 "từ {port_hien_tai} port lên {port_nang_cap} port để có thể sớm hỗ trợ cho khách hàng với ạ, {tinh_huong}",
                 "{?y_them}", "Em xin chân thành cảm ơn ạ!"],
        "goi_y": {"den": [("ha_tang", "lap")], "cc": [("giam_doc", "lap")]},
        "fox": ("Viết MỘT mệnh đề ngắn (không có chủ ngữ mở đầu, nối tiếp sau chữ 'với ạ,') nói vì sao khách cần sớm và có thể "
                "đợi bao lâu nếu sale nhắc. Chỉ dùng ý sale đưa."),
        "vi_du": ("Ý chính: khách cần sớm để làm việc và gia đình, đợi được 2-3 ngày.\n"
                  "Đoạn: hiện khách đang cần sớm để phục vụ cho công việc và gia đình sử dụng, có thể đợi khoảng 2 đến 3 ngày."),
    },
    "ha_tang_moi": {
        "ten": "Xin đầu tư hạ tầng",
        "nhom": "ha_tang", "nhan_con": "Đầu tư tập điểm mới",
        "truong": [_o("hop_dong", "Mã hợp đồng", "VD: CMAAE5918"),
                   _o("ten_kh", "Tên khách hàng", "VD: Ngô Lâm Thái Bảo"),
                   _o("sdt", "Số điện thoại khách", "VD: 0372256684"),
                   _o("dia_chi", "Địa chỉ lắp đặt", "Số nhà / ấp, xã (phường), tỉnh", dai=True),
                   _o("toa_do", "Tọa độ", "VD: (10.8304167, 106.4760000)", dai=True)],
        "y_chinh": "Tiềm năng khu vực (không bắt buộc, trống thì dùng câu mẫu)",
        "y_mau": "khu vực có nhiều nhà trọ công nhân và hộ dân mới xây, chưa có nhà mạng khác phủ",
        "y_tuy_chon": True,
        "mac_dinh": ("Bên cạnh nhu cầu của khách hàng hiện hữu, khu vực này còn có nhiều hộ dân đang sinh sống, tiềm năng phát triển thêm thuê bao "
                     "trong thời gian tới. Việc đầu tư tập điểm mới sẽ giúp đáp ứng nhu cầu trước mắt của khách hàng, đồng thời mở rộng vùng phủ "
                     "và tạo điều kiện phát triển thuê bao lâu dài."),
        "tieu_de": "{hop_dong} - XIN HỖ TRỢ ĐẦU TƯ TẬP ĐIỂM MỚI",
        "than": ["Dear {chao},",
                 "Em có hợp đồng khách hàng đăng ký lắp mới Internet tại khu vực:\n• Tên KH: {ten_kh}\n• SĐT: {sdt}\n• Địa chỉ: {dia_chi}\n"
                 "• Tọa độ: {toa_do}",
                 "Khách hàng đã xác nhận nhu cầu sử dụng thực tế và sẵn sàng triển khai dịch vụ. Tuy nhiên hiện tại khu vực chưa có hạ tầng "
                 "đáp ứng, cần đầu tư tập điểm mới để phục vụ lắp đặt.",
                 "{tinh_huong}",
                 "Kính mong {chao} xem xét hỗ trợ phương án đầu tư tập điểm mới để triển khai hợp đồng và khai thác hiệu quả khu vực.",
                 "{?y_them}", "Em cảm ơn {chao}.\nTrân trọng."],
        "goi_y": {"den": [("ha_tang", "lap")], "cc": [("giam_doc", "lap")]},
        "fox": ("Viết 1-2 câu nối tiếp sau đoạn 'khu vực chưa có hạ tầng, cần đầu tư tập điểm mới', nói về tiềm năng phát triển thuê bao của khu vực "
                "(dân cư, nhu cầu, đối thủ chưa phủ) và lợi ích của việc đầu tư tập điểm mới. Chỉ dùng ý sale đưa, không nhắc lại thông tin khách."),
        "vi_du": ("Ý chính: khu vực nhiều nhà trọ công nhân, hộ dân mới xây, chưa có nhà mạng khác phủ.\n"
                  "Đoạn: Bên cạnh nhu cầu của khách hàng hiện hữu, khu vực này còn có nhiều nhà trọ công nhân và hộ dân mới xây, chưa có nhà mạng "
                  "khác phủ sóng, tiềm năng phát triển thêm thuê bao trong thời gian tới. Việc đầu tư tập điểm mới sẽ giúp đáp ứng nhu cầu trước "
                  "mắt của khách hàng, đồng thời mở rộng vùng phủ và tạo điều kiện phát triển thuê bao lâu dài."),
    },
    "bo_phat": {
        "ten": "Xin thêm bộ phát",
        "truong": [_o("hop_dong", "Mã hợp đồng", "VD: DAAAR2260"),
                   _o("ten_kh", "Tên khách hàng", "VD: Nguyễn Văn Phúc"),
                   _o("dia_chi", "Địa chỉ lắp đặt", "Số nhà, đường, phường / xã, tỉnh", dai=True),
                   _o("thiet_bi", "Xin hỗ trợ thêm", "Để trống = bộ phát phụ (VD: 2 bộ phát phụ, bộ mesh)", dai=True, bat_buoc=False, mac_dinh="bộ phát phụ")],
        "y_chinh": "Tình huống (bấm gợi ý bên dưới hoặc gõ ý chính, Fox viết giúp)",
        "y_mau": "khách đăng ký gói giga kèm camera trả trước 6 tháng, nhà 2 tầng, thiết bị cũ yếu, khách không muốn mua thêm",
        "goi_y_cau": [("Nhà nhiều tầng", "Nhà khách hàng có nhiều tầng nên sóng wifi hiện tại không phủ hết các tầng."),
                      ("Nhà rộng", "Nhà khách hàng có diện tích rộng, một bộ phát không đủ phủ sóng toàn nhà."),
                      ("Thiết bị cũ yếu", "Khách hàng đã có thiết bị phát cũ nhưng không đảm bảo, sóng yếu và hay chập chờn."),
                      ("Dùng nhiều thiết bị", "Khách hàng dùng nhiều thiết bị cùng lúc (làm việc, học online, camera) nên cần sóng ổn định."),
                      ("Không mua thêm", "Khách hàng không muốn tốn thêm chi phí mua thiết bị, nên sale chưa tư vấn mua thêm."),
                      ("Gói cao, trả trước", "Khách hàng đăng ký gói cao cấp và trả trước dài hạn, mong được hỗ trợ để sử dụng ổn định lâu dài.")],
        "tieu_de": "{hop_dong} - XIN HỖ TRỢ THÊM BỘ PHÁT",
        "than": ["Dear {chao},", "Khách hàng: {ten_kh} (**{hop_dong}**)\nĐịa chỉ lắp đặt: {dia_chi}", "{tinh_huong}",
                 "Nhờ {chao} xem xét ca này có thể hỗ trợ thêm {thiet_bi} được không để khách hàng sử dụng lâu dài ạ.",
                 "{?y_them}", "Trân trọng cảm ơn!"],
        "goi_y": {"den": [], "cc": []},
        "fox": ("Viết 2-4 câu nêu tình huống: gói khách đăng ký, nhà mấy tầng hay rộng thế nào, thiết bị hiện có và vì sao chưa đảm bảo, khách "
                "có muốn mua thêm không và sale đã tư vấn gì. KHÔNG viết câu nhờ hỗ trợ cuối (đã có sẵn trong mail). Chỉ dùng ý sale đưa."),
        "vi_du": ("Ý chính: gói giga kèm camera trả trước 6 tháng, nhà 2 tầng, thiết bị cũ không đảm bảo, khách khó tính không muốn mua thêm.\n"
                  "Đoạn: Khách hàng đăng ký gói giga kèm camera ngoài trả trước 6 tháng. Nhà khách hàng 2 tầng đã có thiết bị phát cũ nhưng không "
                  "đảm bảo, khách đang dùng sóng thu và hơi kỹ tính. Do khách hơi khó tính nên sale không tư vấn mua thêm thiết bị vì khách không "
                  "muốn tốn thêm chi phí do tháng này chi phí ra quá nhiều rồi."),
    },
}


def nhom_mau() -> list[tuple[str, list[str]]]:
    """[(mẫu đầu của nhóm, [các mẫu cùng nhóm])] theo thứ tự khai báo: mỗi nhóm một thẻ chọn trên trang (mẫu không khai `nhom` tự thành nhóm một mẫu)."""
    nhom: dict[str, list[str]] = {}
    for k, L in LOAI.items():
        nhom.setdefault(L.get("nhom") or k, []).append(k)
    return [(ds[0], ds) for ds in nhom.values()]


class LoiSoanMail(ValueError):
    """Lỗi hiện thẳng cho người dùng (đã viết bằng tiếng Việt)."""


# ------------------------------------------------------------------ dựng mail từ khuôn
# Lời chào (`chao`) do sale TỰ GÕ (VD "phòng kỹ thuật DNG", "anh Bình"): chủ app bỏ ô chọn anh / chị (10/10/2026) vì mail
# hay gửi cả một phòng. Để trống thì mail hiện [Lời chào] và báo còn trống.
def _gia_tri(loai: str, v: dict) -> dict:
    """Giá trị đã chuẩn hoá để điền khuôn: bỏ khoảng trắng thừa, ô tình huống trống thì lấy câu mẫu (nếu loại có)."""
    kq = {k: re.sub(r"[ \t]+", " ", str(x or "")).strip() for k, x in v.items()}
    L = LOAI[loai]
    for t in L["truong"]:
        if t["mac_dinh"] and not kq.get(t["khoa"]):
            kq[t["khoa"]] = t["mac_dinh"]
    if not kq.get("tinh_huong") and L.get("mac_dinh"):
        kq["tinh_huong"] = L["mac_dinh"].format(thoi_gian_cho=kq.get("thoi_gian_cho") or THIEU.format("Khách có thể đợi"))
    return kq


def dung(loai: str, v: dict) -> dict:
    """{tieu_de, doan: [[(chữ, đậm?)...] ...], text, thieu: [tên ô còn trống]}. Một nguồn chung cho xem trước và copy:
    trang dựng giao diện từ `doan`, `text` dùng cho kiểm thử và nhật ký."""
    if loai not in LOAI:
        raise LoiSoanMail("Loại mail không có trong danh sách.")
    L = LOAI[loai]
    kq, nhan = _gia_tri(loai, v), {t["khoa"]: t["nhan"] for t in L["truong"]}
    nhan.update({"tinh_huong": "Tình huống", "chao": "Lời chào", "y_them": "Ý thêm"})
    thieu: list[str] = []

    def dien(mau: str) -> str | None:
        for k in re.findall(r"\{\?(\w+)\}", mau):
            if not kq.get(k):
                return None                                  # đoạn tuỳ chọn mà ô trống: bỏ cả đoạn
        mau = re.sub(r"\{\?(\w+)\}", r"{\1}", mau)

        def thay(m):
            k = m.group(1)
            if kq.get(k):
                return kq[k]
            nhan_k = nhan.get(k, k)
            if nhan_k not in thieu and not (k == "tinh_huong" and L.get("y_tuy_chon")):
                thieu.append(nhan_k)
            return THIEU.format(nhan_k)
        return re.sub(r"\{(\w+)\}", thay, mau)

    doan = []
    for mau in L["than"]:
        chu = dien(mau)
        if chu:
            doan.append([(p.strip("*") if p.startswith("**") else p, p.startswith("**"))
                         for p in re.split(r"(\*\*.+?\*\*)", chu) if p])
    tieu_de = dien(L["tieu_de"]) or ""
    text = "\n\n".join("".join(c for c, _ in d) for d in doan)
    return {"tieu_de": tieu_de, "doan": doan, "text": text, "thieu": thieu}


# ------------------------------------------------------------------ gợi ý người nhận (chỉ gợi ý, sale tự chọn)
def goi_y(loai: str, don_vi_lap: str | None, dia_chi: str) -> dict:
    """{"den": [...], "cc": [...], "don_vi": chi nhánh nơi lắp, "khu_vuc_ro": bool} - mỗi người là dict
    {id, ten, email, chuc_vu, don_vi}. Chỉ lấy người có email. Quy tắc nằm ở LOAI[...]["goi_y"]; chi nhánh nơi lắp lấy theo
    ô chọn, không có thì đoán từ địa chỉ, không đoán được thì chi nhánh của sale."""
    nha = rules_config().get("soan_mail", {}).get("chi_nhanh_nha") or "Đà Nẵng"
    dv = don_vi_lap or db.doan_don_vi(dia_chi or "") or nha
    out = {"den": [], "cc": [], "don_vi": dv, "khu_vuc_ro": True}
    for vt, quy_tac in LOAI[loai]["goi_y"].items():
        for nhom, noi in quy_tac:
            noi_dv = {"lap": dv, "nha": nha, "khu_vuc": dv}[noi]
            if noi == "khu_vuc":
                khop, tat = db.doi_truong_theo_dia_chi(noi_dv, dia_chi or "")
                out["khu_vuc_ro"] = not khop.empty
                ds = khop if not khop.empty else tat
            else:
                ds = db.theo_nhom(noi_dv, nhom)
            for r in ds.itertuples():
                if isinstance(r.email, str) and r.email and r.email not in {p["email"] for p in out[vt]}:
                    out[vt].append(nguoi_dict(r))
    return out


def cc_bat_buoc(user) -> list[dict]:
    """Người luôn phải CC theo phòng của tài khoản nvkd (config/rules.yml → soan_mail.cc_bat_buoc, chủ app chốt 10/10/2026:
    nvkd IBB7 luôn CC PhucVHD). Admin không bị áp. Mỗi người có cờ `khoa` để giao diện không cho gỡ."""
    if getattr(user, "role", None) != "nvkd":
        return []
    ch = rules_config().get("soan_mail", {}).get("cc_bat_buoc") or {}
    phong = set(user.phong_soan_mail())
    return [{"id": 0, "ten": e.split("@")[0], "email": e, "chuc_vu": "CC bắt buộc", "don_vi": "", "khoa": True}
            for p, ds in ch.items() if p in phong for e in ds]


def gop_cc_bat_buoc(nguoi: dict, user) -> dict:
    """Danh sách người nhận kèm CC bắt buộc (bản sao, chỉ để hiển thị / dựng mail, không lưu lại). Ai đã có sẵn ở Đến hoặc CC thì
    không thêm lần nữa."""
    nguoi = {"den": list(nguoi.get("den") or []), "cc": list(nguoi.get("cc") or [])}
    co = {p["email"].lower() for p in nguoi["den"] + nguoi["cc"]}
    nguoi["cc"] += [p for p in cc_bat_buoc(user) if p["email"].lower() not in co]
    return nguoi


def _chu(v) -> str:
    return v if isinstance(v, str) else ""


def nguoi_dict(r) -> dict:
    return {"id": int(r.id), "ten": r.ho_ten, "email": r.email, "chuc_vu": _chu(r.chuc_vu), "don_vi": _chu(r.don_vi)}


# ------------------------------------------------------------------ Fox viết đoạn tình huống
def _che(chu: str) -> str:
    """Che số dài (SĐT, MST, CCCD) và email trước khi gửi AI; sale đừng gõ tên khách hay địa chỉ ở ô này."""
    chu = re.sub(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", "[email]", chu)
    return re.sub(r"\d[\d .-]{4,}\d", "[số]", chu)


def kiem_tra_fox(user) -> dict:
    ch = ai.kiem_tra(user)
    if not getattr(user, "la_superadmin", False) and ai.luot_hom_nay(user.username, (LOAI_AI,)) >= TOI_DA_NGAY:
        raise ai.LoiAI(f"Hôm nay đã dùng hết {TOI_DA_NGAY} lượt Fox viết mail. Mai dùng tiếp nhé, hoặc tự gõ vào ô.")
    return ch


def viet_tinh_huong(loai: str, y_chinh: str, boi_canh: dict, user) -> str:
    """Ý chính của sale -> một đoạn văn lịch sự. Chưa ghi gì; sale đọc lại và sửa được."""
    if loai not in LOAI:
        raise ai.LoiAI("Loại mail không có trong danh sách.")
    y = _che(str(y_chinh or "").strip())[:TOI_DA_Y]
    if not y:
        raise ai.LoiAI("Gõ vài ý chính vào ô trước, Fox sẽ viết thành câu hoàn chỉnh.")
    ch = kiem_tra_fox(user)
    L = LOAI[loai]
    he = ("Bạn viết một đoạn trong email nội bộ để nhân viên kinh doanh FPT Telecom gửi cấp kỹ thuật / quản lý. "
          "Xưng 'em', lịch sự, ngắn gọn (2-4 câu), nêu rõ vấn đề và đề nghị cụ thể. "
          f"{L['fox']} Chỉ dùng thông tin trong ý chính, KHÔNG bịa số liệu, giờ giấc, tên người hay địa chỉ. Không viết lời "
          "chào, lời cảm ơn, mã hợp đồng, địa chỉ (đã có chỗ khác trong mail). Không dùng markdown hay gạch đầu dòng. "
          "Chỉ trả đúng đoạn văn.\n\nVí dụ:\n" + L["vi_du"])
    nd = "Ý chính: " + y + "".join(f"\n{k}: {_che(str(v))}" for k, v in (boi_canh or {}).items() if v)
    msg = ai.hoi([{"role": "system", "content": he}, {"role": "user", "content": nd}], ch["model_chat"], ch["key"],
                 user.username, LOAI_AI, toi_da=1500)
    doan = re.sub(r"\*\*|^#+ ?|^- ", "", (msg.get("content") or "").strip(), flags=re.M).strip()[:TOI_DA_DOAN]
    if not doan:
        raise ai.LoiAI("Fox chưa viết được, bấm lại hoặc tự gõ vào ô.")
    ghi_log("soan_mail_fox", loai)
    return doan
