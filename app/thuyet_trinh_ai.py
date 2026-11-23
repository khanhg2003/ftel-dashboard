"""AI của "Thuyết trình AI" (`app/thuyet_trinh.py`): viết LỜI NÓI cho các slide và trả lời câu hỏi về slide đang xem.

Lời nói: MỘT lần gọi AI cho cả bài; mỗi lời chỉ được nhận khi mọi con số trong đó có trong `su_that` của đúng slide (`kiem_so` của Trợ lý điều hành), không có chữ cấm và
độ dài hợp lý; không đạt thì slide giữ lời mẫu do code viết. AI tắt / hết hạn mức / lỗi thì cả bài dùng lời mẫu (vẫn đầy đủ, chỉ kém tự nhiên).
Hỏi đáp: dùng đúng bộ công cụ của Fox (`tro_ly_du_lieu`: mọi truy vấn và quyền đi qua `chay_cong_cu`, ở đây không tự viết truy vấn nào), kèm ngữ cảnh slide đang xem.
Không đưa tên khách hàng vào lời gửi AI; tên nhân sự chỉ nằm ở slide Nhân sự / Vì sao và chỉ Ban Giám đốc dùng trang này.
"""
from __future__ import annotations

import json
import re

from app import thuyet_trinh as tt, tro_ly, tro_ly_du_lieu as dl
from app.tro_ly_dieu_hanh_nd import doc_json, kiem_so

LOI_TOI_THIEU, LOI_TOI_DA = 40, 1400        # số ký tự của một lời nói hợp lệ
HAN_VIET_LOI = 90                            # giây chờ AI viết cả bài (một lượt gọi)
TOI_DA_SU_THAT = 6000                        # cắt phần số liệu của slide đưa vào hỏi đáp

HE_THONG = (
    "Bạn là Fox, chuyên viên phân tích kinh doanh của FTEL chi nhánh Đà Nẵng và Quảng Nam, đang đứng thuyết trình trước Ban Giám đốc. Em xưng 'em', gọi người nghe là 'anh chị' (hoặc 'các anh chị'). "
    "Em KHÔNG đọc lại slide: người nghe đã thấy số và biểu đồ ngay trước mắt. Việc của em là nói điều slide chưa nói: nhìn ra điều gì đang diễn ra, nó tốt hay xấu và xấu ở đâu, đáng lo hay đáng mừng, "
    "và nếu là em thì sẽ ưu tiên làm gì. Giống một người chuyên gia kể câu chuyện của con số, có chính kiến, dám nhận định.\n"
    "Bạn nhận danh sách slide, mỗi slide có bang_su_that (số liệu do hệ thống tính, đây là SỰ THẬT DUY NHẤT) và ban_mau (lời mẫu máy viết, chỉ để tham khảo ý, tuyệt đối không chép lại). Viết LỜI NÓI cho từng slide.\n"
    "CÁCH NÓI:\n"
    "- Mở slide bằng nhận định của em, không mở bằng việc đọc số. Ví dụ kiểu 'Điểm em muốn anh chị chú ý ở đây là...', 'Nhìn kỹ thì bức tranh này không đều...', 'Tin tốt là..., nhưng có một điều em chưa yên tâm...'. "
    "Mỗi slide mở một kiểu khác nhau, không lặp cụm mở đầu.\n"
    "- Chọn 2 đến 3 con số quan trọng nhất của slide, nói nó có nghĩa gì (so với thời gian đã qua, so với cùng kỳ, so với phòng khác, so với mục tiêu) rồi rút ra kết luận. Không đọc lần lượt các chỉ số, không đọc lại bảng hay từng dòng gạch đầu dòng. "
    "Số không quan trọng thì bỏ, đừng nhắc.\n"
    "- Phải có chính kiến: đánh giá mức độ ('đây là mức đáng lo', 'đây là tín hiệu tốt nhưng chưa chắc chắn'), chỉ ra điều gì đang kéo kết quả lên hoặc xuống ngay trong số liệu của slide, điều gì dễ bị bỏ qua, và rủi ro nếu cứ giữ nhịp này. "
    "Có thể so sánh các phần với nhau bằng lời ('hụt chủ yếu nằm ở hai phòng', 'phần lớn mức tăng đến từ một người') miễn là suy ra được từ bang_su_that.\n"
    "- Nối các slide thành MỘT câu chuyện: slide sau nối tiếp ý slide trước bằng một câu chuyển tự nhiên ('Vậy hụt này đến từ đâu? Em xin đi vào...'). Có thể nhắc lại điều đã nói ở phần trước bằng lời, nhưng không chép số của slide khác. "
    "Slide đầu mở bằng lời chào ngắn và nói thẳng kết luận lớn nhất của cả bài trong một câu. Slide cuối (id ket_luan) chốt 2 đến 3 việc em đề xuất ưu tiên và nói rõ vì sao, kết bằng một câu ngắn mời anh chị cho ý kiến hoặc hỏi thêm.\n"
    "- Văn NÓI như người thật: câu ngắn xen câu vừa, có từ nối tự nhiên ('thế nhưng', 'nói cách khác', 'quan trọng hơn', 'đáng nói là', 'nếu để ý'), có lúc đặt câu hỏi rồi tự trả lời. Không văn bản hành chính, không liệt kê khô cứng, không sáo rỗng.\n"
    "QUY TẮC BẮT BUỘC (hệ thống kiểm tra từng con số, sai là lời bị loại):\n"
    "- Mọi con số em nói ra phải có trong bang_su_that của ĐÚNG slide đó: chép đúng, không tự tính thêm, không làm tròn lại, không đổi đơn vị. Muốn so sánh mà không có sẵn số thì nói bằng lời ('gần gấp đôi', 'chưa tới một nửa', 'nhỉnh hơn một chút'), không tự tạo con số mới. Không có số thì nói bằng lời, đừng bịa.\n"
    "- Nhận định phải dựa trên số liệu có trong slide. KHÔNG khẳng định nguyên nhân bên ngoài hay lý do cá nhân (thời tiết, chính sách, đối thủ, tâm lý nhân viên...). Số liệu chưa cho biết lý do thì nói 'số liệu chưa cho biết lý do, phần này cần anh chị trao đổi thêm với phòng'. "
    "Được nêu giả thuyết khi nói rõ đó là giả thuyết cần kiểm tra. Việc đề xuất chỉ là việc trong tầm quản lý số liệu (tập trung vào phòng nào, người nào, mảng nào, theo dõi chỉ số gì, trong bao lâu); không đề xuất tăng người, tăng ca, đổi chính sách.\n"
    "- Độ dài mỗi slide khoảng 70 đến 120 từ (slide nguyen_nhan và ket_luan được tới 150 từ), chia thành các câu ngắn dễ nghe.\n"
    "- Văn nói tiếng Việt, không gạch đầu dòng, không markdown, không ngoặc đơn, không ký hiệu như % + = /; viết 'phần trăm', 'tăng', 'giảm'. Giữ nguyên tên phòng, tên người.\n"
    "- Chỉ dùng chữ 'online' cho hợp đồng đã lắp xong, không dùng cách gọi khác. 'Tồn' là hợp đồng chưa online. 'Cùng kỳ' là cùng khoảng ngày tháng trước. Bài có thể là cả chi nhánh hoặc MỘT phòng (tên phòng nằm trong bang_su_that).\n"
    "Trả về MỘT đối tượng JSON: {\"loi_noi\": {\"<id slide>\": \"<lời nói>\", ...}} với đủ mọi id đã nhận.")

Y_NGUYEN_NHAN = re.compile(r"vì sao|tại sao|do đâu|nguyên nhân|lý do|phân tích|vấn đề gì|sao lại|tại làm sao", re.I)

LOI_DAN_NOI = (
    "\n\nĐANG THUYẾT TRÌNH BẰNG GIỌNG NÓI (quy định này GHI ĐÈ mọi quy định về độ dài và định dạng ở trên): trả lời bằng LỜI NÓI tự nhiên, liền mạch như một chuyên gia đang giải thích "
    "trước phòng họp. KHÔNG markdown, KHÔNG gạch đầu dòng, KHÔNG tiêu đề, KHÔNG ngoặc đơn, KHÔNG ký hiệu % + = /; nói 'phần trăm', 'tăng', 'giảm'. Khoảng 60 đến 130 từ. Nói nhận định của em trước (đáng lo hay đáng mừng, vì sao), rồi mới dẫn số liệu làm chứng, đừng chỉ đọc lại số; có chính kiến, giọng như người thật. "
    "Câu hỏi 'vì sao / nguyên nhân / do đâu': trả lời bằng kết quả phân tích nguyên nhân (đã được tra sẵn bên dưới, hoặc TỰ gọi công cụ phan_tich_nguyen_nhan cho đúng phòng), nêu 2-3 nguyên nhân theo mức ảnh hưởng kèm số, "
    "nói rõ điều KHÔNG phải nguyên nhân nếu số cho thấy, rồi việc nên làm. Câu hỏi giải thích một con số trên slide thì giải thích con số đó nghĩa là gì và vì sao quan trọng bằng chính số liệu của slide, "
    "chỉ gọi công cụ khi cần đào sâu hơn slide. TỰ tra số cần thiết rồi trả lời: TUYỆT ĐỐI không bảo người nghe 'cần phân tích thêm', 'cần dùng công cụ', 'hãy yêu cầu tra'; không nhắc tên công cụ. "
    "Chỉ khi tra rồi mà số liệu vẫn không cho biết thì nói 'số liệu chưa cho biết lý do'. Không nói 'slide' trừ khi người hỏi nhắc tới.")


# ------------------------------------------------------------------ lời nói cho cả bài
def _hop_le(chu: str, su_that: dict) -> bool:
    chu = (chu or "").strip()
    return LOI_TOI_THIEU <= len(chu) <= LOI_TOI_DA and not re.search(r"đấu\s*nối", chu, re.I) and kiem_so(chu, tt.bang_kiem_so(su_that))


def viet_loi(user, bai: dict) -> dict:
    """Thêm lời nói do AI viết vào `bai` (sửa tại chỗ và trả lại): slide nào lời hợp lệ thì `nguon_loi = "ai"`. Không dùng được AI thì ghi lý do ở `ly_do_luat`."""
    try:
        ch = tro_ly.kiem_tra(user)
    except tro_ly.LoiAI as e:
        bai["dung_ai"], bai["ly_do_luat"] = False, str(e)
        return bai
    dau_vao = {"ngay_so": bai["ngay_hien"], "slides": [{"id": s["id"], "tieu_de": s["tieu_de"], "bang_su_that": s["su_that"], "ban_mau": s["loi_noi"]} for s in bai["slides"]]}
    try:
        msg = tro_ly.hoi([{"role": "system", "content": HE_THONG}, {"role": "user", "content": json.dumps(dau_vao, ensure_ascii=False, default=str)}],
                         ch["model_chat"], ch["key"], user.username, "thuyet_trinh", toi_da=9000, han=HAN_VIET_LOI, dinh_dang={"type": "json_object"})
    except tro_ly.LoiAI as e:
        bai["dung_ai"], bai["ly_do_luat"] = False, f"AI chưa viết được lời nói ({e})"
        return bai
    ra = (doc_json(msg.get("content") or "") or {}).get("loi_noi")
    ra = ra if isinstance(ra, dict) else {}
    dung = 0
    for s in bai["slides"]:
        chu = ra.get(s["id"])
        if isinstance(chu, str) and _hop_le(tro_ly.lam_sach(chu), s["su_that"]):
            s["loi_noi"], s["nguon_loi"] = tro_ly.lam_sach(chu).strip(), "ai"
            dung += 1
    bai["dung_ai"] = dung > 0
    bai["ly_do_luat"] = "" if dung == len(bai["slides"]) else ("AI viết sai số hoặc sai khuôn ở mọi slide nên dùng lời mẫu." if not dung else f"{len(bai['slides']) - dung} slide dùng lời mẫu vì lời AI có số không khớp bảng số liệu.")
    return bai


# ------------------------------------------------------------------ hỏi đáp một slide
def _ngu_canh_slide(bai: dict, i: int) -> str:
    s = bai["slides"][i]
    so = json.dumps(s["su_that"], ensure_ascii=False, default=str)[:TOI_DA_SU_THAT]
    return (f"\n\nĐANG XEM SLIDE {i + 1}/{len(bai['slides'])}: {s['tieu_de']} (số liệu tới ngày {bai['ngay_hien']}).\nCác ý hiển thị trên slide:\n"
            + "\n".join(f"- {d}" for d in s["diem"]) + f"\nSố liệu của slide (JSON): {so}\nCâu hỏi 'cái này', 'phòng này', 'con số này' là nói về slide đang xem.")


def _phong_trong_cau(cau: str) -> str | None:
    """Mã phòng được nhắc trong câu hỏi (IBB5, "B5", tên phòng như Tam Kỳ); không có thì None."""
    from app.org import phong_order
    chu = cau.lower()
    m = re.search(r"\b(?:ibb|b)\s*(\d)\b", chu)
    ds = list(phong_order())
    if m:
        for x in ds:
            if x["code"].lower() == f"ibb{m.group(1)}":
                return x["code"]
    for x in sorted(ds, key=lambda x: -len(x["ten"])):
        if len(x["ten"]) >= 4 and x["ten"].lower() in chu:
            return x["code"]
    return None


def _tra_san_nguyen_nhan(user, bai: dict, i: int, cau: str) -> str:
    """Câu hỏi "vì sao..." thì tra SẴN chẩn đoán nguyên nhân của phòng được nhắc (hoặc phòng chính của slide) và đưa vào ngữ cảnh: không phụ thuộc việc AI có tự gọi công cụ hay không."""
    if not Y_NGUYEN_NHAN.search(cau):
        return ""
    code = _phong_trong_cau(cau) or ((bai["slides"][i].get("phong_chinh") or {}).get("ma"))
    if not code:
        return ""
    from app.fox_nguyen_nhan import nguyen_nhan
    try:
        van_ban = nguyen_nhan(user, bai["ngay"], code)
    except Exception:
        return ""
    return (f"\n\nKẾT QUẢ PHÂN TÍCH NGUYÊN NHÂN ĐÃ TRA SẴN cho phòng {code} (đã tách theo người, nguồn hợp đồng, tuần, đầu vào - đầu ra; dùng để trả lời, không cần tra lại):\n{van_ban[:9000]}")


def lam_sach_noi(chu: str) -> str:
    """Chữ trả lời của AI -> chữ hiển thị: bỏ markdown, gộp dòng, không còn gạch đầu dòng."""
    from app.zalo_gia_ai import bo_markdown
    chu = bo_markdown(tro_ly.lam_sach(chu or ""))
    chu = re.sub(r"^\s*•\s*", "", chu, flags=re.M)
    chu = re.sub(r"\s*\n+\s*", " ", chu).strip()
    ten = re.escape(str(tro_ly.cau_hinh().get("ten") or "Fox"))
    return re.sub(rf"\s*[-—–]*\s*(?:{ten}|Fox)\.?\s*$", "", chu).strip()            # bỏ chữ ký nhân vật cuối câu trả lời


def hoi(user, bai: dict, i: int, cau_hoi: str, lich_su: list[dict]) -> str:
    """Trả lời `cau_hoi` về slide thứ `i` (có thể đào sâu bằng công cụ của Fox). Ném `tro_ly.LoiAI` (câu tiếng Việt) nếu AI không dùng được."""
    i = max(0, min(int(i), len(bai["slides"]) - 1))
    co_dinh, thay_doi = dl.ngu_canh_chat(user, "/", {})
    tra_san = _tra_san_nguyen_nhan(user, bai, i, cau_hoi)
    tra_loi = tro_ly.chat(user, lich_su[-6:], cau_hoi.strip()[:500], (co_dinh, thay_doi + _ngu_canh_slide(bai, i) + tra_san + LOI_DAN_NOI), dl.cong_cu(user),
                          lambda ten, ts: dl.chay_cong_cu(user, ten, ts))
    return lam_sach_noi(tra_loi)
