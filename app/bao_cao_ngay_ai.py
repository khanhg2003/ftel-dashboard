"""Fox viết ba khối chữ cho ảnh báo cáo đầu ngày (trọng tâm · đánh giá · thông điệp).

Chỉ gửi lên AI số tổng hợp của phòng và tên + số của từng nhân sự trong phòng người hỏi được xem -
không có tên khách hàng, không có gì vượt quyền (AGENTS mục 5.6). Trưởng phòng luôn đọc lại và sửa
trước khi tạo ảnh, nên đây là bản nháp chứ không phải số liệu.
"""
from __future__ import annotations

from datetime import date

from app import bao_cao_ngay as bc
from app import tro_ly

DAU = {"trong_tam": "TRỌNG TÂM HÔM NAY", "nhan_dinh": "ĐÁNH GIÁ & NHẬN ĐỊNH",
       "thong_diep": "THÔNG ĐIỆP NGÀY MỚI"}

YEU_CAU = """Viết phần chữ cho ảnh BÁO CÁO ĐẦU NGÀY của một phòng kinh doanh, gửi nhóm Zalo lúc đầu giờ sáng.

Trả về ĐÚNG ba phần, mỗi phần bắt đầu bằng một dòng tiêu đề viết hoa như dưới đây, không thêm phần nào khác,
không dùng bảng, không in đậm:

TRỌNG TÂM HÔM NAY
- 4 đến 5 gạch đầu dòng, mỗi dòng một việc cụ thể phải làm trong ngày, bám đúng số ở trên (số ca dự kiến
  online, số KHTN, ai đang hụt nhiều nhất). Mỗi dòng tối đa 18 từ.

ĐÁNH GIÁ & NHẬN ĐỊNH
- 4 gạch đầu dòng: (1) kết quả ngày hôm qua so với mục tiêu ngày; (2) nguồn đầu vào sáng nay (KHTN) so với
  mục tiêu; (3) dự kiến online hôm nay đủ hay thiếu bao nhiêu so với mục tiêu ngày; (4) luỹ kế tháng và
  phần còn thiếu, kèm tên 1-2 người cần chú ý nhất. Mỗi dòng tối đa 22 từ, mỗi câu phải có số.

THÔNG ĐIỆP NGÀY MỚI
- Một đoạn 2 đến 3 câu động viên cả team, nhắc đúng việc trọng tâm, không sáo rỗng, không hô khẩu hiệu."""


def _du_lieu(phong: list[str], ngay: date) -> str:
    t = bc.tom_tat(phong, ngay)
    df = bc.bang(phong, ngay)
    dong = [
        f"Ngày báo cáo: {ngay:%d/%m/%Y}. Phòng: {phong[0]}.",
        f"Hôm qua ({t['hom_qua']:%d/%m}): online thật {t['hq_thuc_te']}, mục tiêu ngày {t['hq_muc_tieu']}, "
        f"thiếu {t['hq_thieu']}, đạt {t['hq_ty_le']}%.",
        f"Sáng nay: KHTN đang có {t['khtn']}, mục tiêu PTTB/ngày {t['mt_ngay']}, dự kiến online sáng "
        f"{t['onl_sang']} + chiều {t['onl_chieu']} = {t['dk_onl']}, đã online {t['da_online']}, "
        f"còn phải online {t['con_phai_onl']}.",
        f"Luỹ kế tháng: {t['luy_ke']}/{t['mt_thang']} PTTB ({t['ty_le_thang']:g}%), còn thiếu "
        f"{t['con_thieu']}. V.VIP luỹ kế {t['vvip_thang']}.",
        f"Số người trong phòng: {t['so_nguoi']}, chưa nhập báo cáo sáng nay: {t['chua_nhap']}.",
        "",
        "Từng nhân sự (tên · mục tiêu ngày · KHTN · dự kiến online · đã online hôm nay · "
        "PTTB luỹ kế/mục tiêu tháng):",
    ]
    for r in df.itertuples():
        mt = f"{int(r.pttb_thang)}/{int(r.mt_thang)}" if r.mt_thang else f"{int(r.pttb_thang)}"
        dong.append(f"- {r.ho_ten} · {int(r.muc_tieu)} · {int(r.khtn)} · {int(r.dk_onl)} · "
                    f"{int(r.thuc_hien)} · {mt}")
    return "\n".join(dong)


def _tach(chu: str) -> dict:
    """Cắt bài trả lời thành ba khối theo dòng tiêu đề; thiếu tiêu đề thì dồn hết vào khối đầu."""
    ra = {k: [] for k in DAU}
    dang = None
    for d in (chu or "").splitlines():
        khoa = next((k for k, v in DAU.items() if d.strip().upper().startswith(v)), None)
        if khoa:
            dang = khoa
            continue
        if dang and d.strip():
            ra[dang].append(d.strip().lstrip("-•* ").strip())
    if not any(ra.values()):
        ra["trong_tam"] = [d.strip() for d in (chu or "").splitlines() if d.strip()]
    return {k: "\n".join(v) for k, v in ra.items()}


def fox_viet(user, phong: list[str], ngay: date) -> dict:
    """Gọi AI một lượt, trả về ba khối chữ. Ném `tro_ly.LoiAI` với lời đã viết sẵn tiếng Việt."""
    # chi_viet=True: tài khoản Nhân viên KD bấm được nút này dù không được mở quyền chat
    kq = tro_ly.tao_nhan_xet(user, "bao_cao_ngay", f"{phong[0]}|{ngay:%Y-%m-%d}",
                             _du_lieu(phong, ngay), YEU_CAU, chi_viet=True)
    return _tach(kq["noi_dung"])
