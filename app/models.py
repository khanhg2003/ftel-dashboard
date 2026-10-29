"""Mô hình dữ liệu.

Nguyên tắc:
- Khoá của nhân sự là MÃ NV (đã bỏ số 0 đầu), acc inside là khoá phụ.
- Mỗi hợp đồng chỉ tồn tại 1 dòng -> không thể đếm trùng như file Excel hiện tại.
- Cơ cấu tổ chức tách 2 chiều: phòng kinh doanh (báo cáo) và phòng theo PS (hành chính).
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (Boolean, Date, DateTime, Float, ForeignKey, Index, Integer,
                        String, Text, UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


# ---------------------------------------------------------------- danh mục
class Bay(Base):
    """Danh mục Bầy - quản lý ở Quản trị → Cơ cấu tổ chức (YAML chỉ dùng để khởi tạo lần đầu)."""
    __tablename__ = "dim_bay"
    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    ten: Mapped[str] = mapped_column(String(60))
    ten_tong: Mapped[str | None] = mapped_column(String(60), nullable=True)
    thu_tu: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Phong(Base):
    __tablename__ = "dim_phong"
    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    ten: Mapped[str] = mapped_column(String(80))
    bay: Mapped[str] = mapped_column(String(20), index=True)
    loai: Mapped[str] = mapped_column(String(20))          # IBB/DIABAN/KT/CUS/ECOM/KHAC
    chi_nhanh: Mapped[str] = mapped_column(String(10))     # DNG/QNM
    nhom_khac: Mapped[str | None] = mapped_column(String(10), nullable=True)
    thu_tu: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class StaffMap(Base):
    """Danh mục: acc nhân viên -> phòng kinh doanh (có hiệu lực theo thời gian)."""
    __tablename__ = "staff_map"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    acc: Mapped[str] = mapped_column(String(80))
    acc_norm: Mapped[str] = mapped_column(String(80), index=True)
    ma_nv: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    phong_code: Mapped[str] = mapped_column(ForeignKey("dim_phong.code"))
    hieu_luc_tu: Mapped[date | None] = mapped_column(Date, nullable=True)
    hieu_luc_den: Mapped[date | None] = mapped_column(Date, nullable=True)
    ghi_chu: Mapped[str | None] = mapped_column(String(200), nullable=True)
    nguon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Tên hiển thị khi acc chưa có trong NSLĐ / dim_employee (vd acc tạm cấp trước khi có acc inside
    # chính thức) - các báo cáo ưu tiên tên NSLĐ trước, cột này chỉ là tầng dự phòng cuối trước khi
    # phải hiện acc thô. Chốt 01/10/2026.
    ten_hien_thi: Mapped[str | None] = mapped_column(String(120), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PhongBayThang(Base):
    """Cơ cấu Bầy theo từng tháng (mỗi tháng phòng có thể đổi bầy)."""
    __tablename__ = "phong_bay_thang"
    __table_args__ = (UniqueConstraint("thang", "phong_code", name="uq_phong_bay_thang"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thang: Mapped[str] = mapped_column(String(7), index=True)
    phong_code: Mapped[str] = mapped_column(ForeignKey("dim_phong.code"))
    bay: Mapped[str] = mapped_column(String(20))
    thu_tu: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Employee(Base):
    __tablename__ = "dim_employee"
    ma_nv: Mapped[str] = mapped_column(String(20), primary_key=True)
    ho_ten: Mapped[str | None] = mapped_column(String(120), nullable=True)
    acc: Mapped[str | None] = mapped_column(String(80), nullable=True)
    acc_norm: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    vi_tri: Mapped[str | None] = mapped_column(String(30), nullable=True)     # NVKD/CTV
    vi_tri_inside: Mapped[str | None] = mapped_column(String(120), nullable=True)
    don_vi_ps: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phong_ps: Mapped[str | None] = mapped_column(String(20), nullable=True)
    khu_vuc: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ngay_tinh_luong: Mapped[date | None] = mapped_column(Date, nullable=True)
    trang_thai: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ngay_nghi_viec: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class HrMonthly(Base):
    """Ảnh chụp nhân sự + NSLĐ theo từng tháng (giữ lịch sử, không ghi đè)."""
    __tablename__ = "hr_monthly"
    __table_args__ = (UniqueConstraint("ma_nv", "thang", name="uq_hr_thang"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ma_nv: Mapped[str] = mapped_column(String(20), index=True)
    thang: Mapped[str] = mapped_column(String(7), index=True)      # YYYY-MM
    acc: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ho_ten: Mapped[str | None] = mapped_column(String(120), nullable=True)
    vi_tri: Mapped[str | None] = mapped_column(String(30), nullable=True)
    phong_ps: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tham_nien_bucket: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tham_nien_thang: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nhom_tham_nien: Mapped[str | None] = mapped_column(String(20), nullable=True)
    trang_thai: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ngay_nghi_viec: Mapped[date | None] = mapped_column(Date, nullable=True)
    ngay_gian_doan: Mapped[float | None] = mapped_column(Float, nullable=True)
    dieu_kien: Mapped[str | None] = mapped_column(String(40), nullable=True)
    diem_itn: Mapped[float | None] = mapped_column(Float, nullable=True)
    diem_fpt_play: Mapped[float | None] = mapped_column(Float, nullable=True)
    diem_tong: Mapped[float | None] = mapped_column(Float, nullable=True)
    ket_luan: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tong_bao_lanh: Mapped[float | None] = mapped_column(Float, nullable=True)
    ghi_chu: Mapped[str | None] = mapped_column(String(200), nullable=True)
    batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


# ---------------------------------------------------------------- dữ liệu bán
class _FactCommon:
    cn_quan_ly: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cn_ban: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phong_he_thong: Mapped[str | None] = mapped_column(String(60), nullable=True)
    goi_dich_vu: Mapped[str | None] = mapped_column(String(60), nullable=True)
    nguon_ban: Mapped[str | None] = mapped_column(String(30), nullable=True)
    tinh_trang: Mapped[str | None] = mapped_column(String(60), nullable=True)
    ten_khach_hang: Mapped[str | None] = mapped_column(String(160), nullable=True)
    ngay_tao_hd: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)
    ngay_online: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)
    ngay_huy: Mapped[date | None] = mapped_column(Date, nullable=True)
    acc_nhan_vien: Mapped[str | None] = mapped_column(String(80), nullable=True)
    acc_norm: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    ma_nhan_vien: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    quan_huyen: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tap_diem: Mapped[str | None] = mapped_column(String(30), nullable=True)
    doi_tuong_kh: Mapped[str | None] = mapped_column(String(60), nullable=True)
    phong_code: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    la_ecom: Mapped[bool] = mapped_column(Boolean, default=False)
    batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class FactInternet(Base, _FactCommon):
    __tablename__ = "fact_internet"
    hop_dong: Mapped[str] = mapped_column(String(30), primary_key=True)
    chinh_sach_ban: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tien_hoa_mang: Mapped[float | None] = mapped_column(Float, nullable=True)
    so_thang_tra_truoc: Mapped[float | None] = mapped_column(Float, nullable=True)
    hinh_thuc_tt: Mapped[str | None] = mapped_column(String(120), nullable=True)
    so_tien_tra_truoc: Mapped[float | None] = mapped_column(Float, nullable=True)
    arpu_tra_truoc: Mapped[float | None] = mapped_column(Float, nullable=True)
    arpu_tra_sau: Mapped[float | None] = mapped_column(Float, nullable=True)
    xa_phuong: Mapped[str | None] = mapped_column(String(80), nullable=True)


class FactFptPlay(Base, _FactCommon):
    __tablename__ = "fact_fptplay"
    hop_dong: Mapped[str] = mapped_column(String(30), primary_key=True)
    goi_fpt_play: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    la_vvip: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    loai_box: Mapped[str | None] = mapped_column(String(40), nullable=True)
    chinh_sach_ban: Mapped[str | None] = mapped_column(String(200), nullable=True)
    gia_box: Mapped[float | None] = mapped_column(Float, nullable=True)
    so_thang_tra_truoc: Mapped[float | None] = mapped_column(Float, nullable=True)
    ngay_ban: Mapped[date | None] = mapped_column(Date, nullable=True)
    tinh_trang_fpl: Mapped[str | None] = mapped_column(String(60), nullable=True)


class FactCamera(Base, _FactCommon):
    """Khoá là mã băm của cả dòng: 2 dòng giống hệt nhau = 1 camera (BGD chốt)."""
    __tablename__ = "fact_camera"
    row_hash: Mapped[str] = mapped_column(String(40), primary_key=True)
    hop_dong: Mapped[str] = mapped_column(String(30), index=True)
    ten_goi_cloud: Mapped[str | None] = mapped_column(String(80), nullable=True)
    so_luong_cloud: Mapped[float | None] = mapped_column(Float, nullable=True)
    gia_cuoc_cloud: Mapped[float | None] = mapped_column(Float, nullable=True)
    ky_tt: Mapped[float | None] = mapped_column(Float, nullable=True)
    don_gia: Mapped[float | None] = mapped_column(Float, nullable=True)
    so_luong: Mapped[float | None] = mapped_column(Float, nullable=True)
    tong_tien: Mapped[float | None] = mapped_column(Float, nullable=True)
    phan_loai: Mapped[str | None] = mapped_column(String(30), nullable=True)


class FactPheu(Base):
    """Số liệu Phễu bán hàng theo từng tháng và đơn vị (chốt 28/10/2026)."""
    __tablename__ = "fact_pheu_ban_hang"
    khoa: Mapped[str] = mapped_column(String(60), primary_key=True)
    thang: Mapped[str] = mapped_column(String(7), index=True)
    don_vi: Mapped[str] = mapped_column(String(40), index=True)
    phong_code: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    chi_nhanh: Mapped[str | None] = mapped_column(String(10), index=True, nullable=True)
    thu_thap_cd: Mapped[int] = mapped_column(Integer, default=0)
    thu_thap_ccd: Mapped[int] = mapped_column(Integer, default=0)
    lien_he_cd: Mapped[int] = mapped_column(Integer, default=0)
    lien_he_ccd: Mapped[int] = mapped_column(Integer, default=0)
    tu_van_cd: Mapped[int] = mapped_column(Integer, default=0)
    tu_van_ccd: Mapped[int] = mapped_column(Integer, default=0)
    len_don_cd: Mapped[int] = mapped_column(Integer, default=0)
    len_don_ccd: Mapped[int] = mapped_column(Integer, default=0)
    hoan_tat_cd: Mapped[int] = mapped_column(Integer, default=0)
    hoan_tat_ccd: Mapped[int] = mapped_column(Integer, default=0)
    kh_cham_soc: Mapped[int] = mapped_column(Integer, default=0)
    batch_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


Index("ix_internet_thang", FactInternet.ngay_online, FactInternet.phong_code)
Index("ix_fptplay_thang", FactFptPlay.ngay_online, FactFptPlay.phong_code)
Index("ix_camera_thang", FactCamera.ngay_online, FactCamera.phong_code)


# ---------------------------------------------------------------- chỉ tiêu & vận hành
class Target(Base):
    __tablename__ = "target_monthly"
    __table_args__ = (UniqueConstraint("thang", "doi_tuong", "ma_doi_tuong", "chi_tieu",
                                       name="uq_target"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thang: Mapped[str] = mapped_column(String(7), index=True)
    doi_tuong: Mapped[str] = mapped_column(String(10))        # PHONG | BAY | CHI_NHANH
    ma_doi_tuong: Mapped[str] = mapped_column(String(20))
    chi_tieu: Mapped[str] = mapped_column(String(30))         # internet | camera | ngay | net...
    gia_tri: Mapped[float] = mapped_column(Float)
    ghi_chu: Mapped[str | None] = mapped_column(String(200), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class UploadBatch(Base):
    __tablename__ = "upload_batch"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset: Mapped[str] = mapped_column(String(30), index=True)
    file_name: Mapped[str] = mapped_column(String(260))
    file_hash: Mapped[str] = mapped_column(String(40), index=True)
    thang: Mapped[str | None] = mapped_column(String(7), nullable=True)
    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    rows_valid: Mapped[int] = mapped_column(Integer, default=0)
    rows_invalid: Mapped[int] = mapped_column(Integer, default=0)
    rows_new: Mapped[int] = mapped_column(Integer, default=0)
    rows_updated: Mapped[int] = mapped_column(Integer, default=0)
    rows_duplicate: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[str | None] = mapped_column(String(60), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    ho_ten: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))   # admin|operator|bay|phong|nhanvien
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)   # JSON list mã bầy/phòng
    ma_nv: Mapped[str | None] = mapped_column(String(20), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    session_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    username: Mapped[str | None] = mapped_column(String(60), nullable=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------- trợ lý AI
class CaiDat(Base):
    """Cài đặt dạng khoá - giá trị chỉnh trên giao diện (VD cấu hình trợ lý AI)."""
    __tablename__ = "cai_dat"
    khoa: Mapped[str] = mapped_column(String(60), primary_key=True)
    gia_tri: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(60), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AiSuDung(Base):
    """Mỗi lần gọi OpenAI một dòng: để giới hạn lượt/ngày và trần chi phí tháng."""
    __tablename__ = "ai_su_dung"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    username: Mapped[str | None] = mapped_column(String(60), index=True, nullable=True)
    loai: Mapped[str] = mapped_column(String(20))            # chat | nhan_xet | thu
    model: Mapped[str | None] = mapped_column(String(60), nullable=True)
    token_vao: Mapped[int] = mapped_column(Integer, default=0)
    token_ra: Mapped[int] = mapped_column(Integer, default=0)
    chi_phi_usd: Mapped[float] = mapped_column(Float, default=0)


class AiNhanXet(Base):
    """Nhận xét đã tạo, dùng lại cho người mở sau khi số liệu chưa đổi."""
    __tablename__ = "ai_nhan_xet"
    khoa: Mapped[str] = mapped_column(String(64), primary_key=True)
    loai: Mapped[str] = mapped_column(String(20))
    noi_dung: Mapped[str] = mapped_column(Text)
    username: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ---------------------------------------------------------------- quảng cáo Facebook IBB7
class AdsPage(Base):
    """Fanpage chạy quảng cáo. `ma` = tên chuẩn n8n / bot Telegram gửi lên (VD 'KON TUM')."""
    __tablename__ = "ads_page"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ma: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    ten: Mapped[str] = mapped_column(String(120))
    loai: Mapped[str] = mapped_column(String(10), default="sale")        # sale | cong_ty (không chia cho sale)
    tinh_trang: Mapped[str] = mapped_column(String(20), default="Đang chạy")   # Đang chạy | Đang nuôi | Tắt
    ghi_chu: Mapped[str | None] = mapped_column(String(300), nullable=True)
    link: Mapped[str | None] = mapped_column(String(300), nullable=True)                # link fanpage
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AdsSale(Base):
    """Tên gọi của sale trong phân công page (VD 'C. Chi') -> acc inside để nối số bán thật."""
    __tablename__ = "ads_sale"
    ten: Mapped[str] = mapped_column(String(60), primary_key=True)
    acc: Mapped[str | None] = mapped_column(String(80), nullable=True)


class AdsPic(Base):
    """Sale chạy page trong một khoảng ngày; chi tiêu mỗi ngày chia đều cho các sale đang chạy ngày đó."""
    __tablename__ = "ads_pic"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("ads_page.id"), index=True)
    sale: Mapped[str] = mapped_column(String(60))
    tu_ngay: Mapped[date] = mapped_column(Date)
    den_ngay: Mapped[date | None] = mapped_column(Date, nullable=True)
    ty_le: Mapped[float | None] = mapped_column(Float, nullable=True)   # % chia riêng (VD 70 / 30); trống = chia đều


class AdsNgay(Base):
    """Chi tiêu một camp trong một ngày (n8n gửi lên, gửi lại thì ghi đè - không nhân đôi)."""
    __tablename__ = "ads_ngay"
    __table_args__ = (UniqueConstraint("page_id", "camp", "ngay", name="uq_ads_ngay"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("ads_page.id"), index=True)
    camp: Mapped[str] = mapped_column(String(160))
    ngay: Mapped[date] = mapped_column(Date, index=True)
    tinh_trang: Mapped[str | None] = mapped_column(String(30), nullable=True)
    chi_tieu: Mapped[float] = mapped_column(Float, default=0)          # USD
    tin_nhan: Mapped[int] = mapped_column(Integer, default=0)
    nguon: Mapped[str] = mapped_column(String(20), default="n8n")      # n8n | import | tay
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AdsLead(Base):
    """Mỗi lần bot Telegram (hoặc nhập tay) báo có số điện thoại / PTTB của page - một dòng, sửa/xoá được."""
    __tablename__ = "ads_lead"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("ads_page.id"), index=True)
    ngay: Mapped[date] = mapped_column(Date, index=True)
    lead: Mapped[int] = mapped_column(Integer, default=0)
    pttb: Mapped[int] = mapped_column(Integer, default=0)
    nguon: Mapped[str] = mapped_column(String(20), default="telegram")  # telegram | import | tay
    nguoi: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ghi_chu: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AdsThang(Base):
    """Cấu hình theo tháng: tỷ giá USD -> VNĐ."""
    __tablename__ = "ads_thang"
    thang: Mapped[str] = mapped_column(String(7), primary_key=True)
    ty_gia: Mapped[float] = mapped_column(Float)


# ---------------------------------------------------------------- nhập tồn
class BaoCaoNgay(Base):
    """Báo cáo đầu ngày của sale: 7 ô sale tự nhập. PTTB luỹ kế và số V.VIP app tự lấy từ file nên
    không lưu ở đây - tránh hai nguồn số lệch nhau."""
    __tablename__ = "bao_cao_ngay"
    __table_args__ = (UniqueConstraint("ngay", "acc_norm", name="uq_bao_cao_ngay"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ngay: Mapped[date] = mapped_column(Date, index=True)
    acc_norm: Mapped[str] = mapped_column(String(60), index=True)
    phong_code: Mapped[str] = mapped_column(String(20), index=True)
    muc_tieu: Mapped[int] = mapped_column(Integer, default=0)          # mục tiêu bán hôm nay
    khtn: Mapped[int] = mapped_column(Integer, default=0)              # KHTN đang có
    # số bán thực hiện trong ngày: cùng cách hiểu với `da_online`, để TRỐNG nghĩa là chưa đếm tay
    da_ban: Mapped[int | None] = mapped_column(Integer, nullable=True)
    onl_sang: Mapped[int] = mapped_column(Integer, default=0)          # dự kiến online buổi sáng
    onl_chieu: Mapped[int] = mapped_column(Integer, default=0)
    # đã online trong ngày: để TRỐNG nghĩa là chưa đếm tay, lúc đó lấy số từ file Internet.
    # File chỉ về vào hôm sau nên buổi sáng số từ file luôn bằng 0 - phải cho sale gõ thì
    # "còn phải online" mới có nghĩa.
    da_online: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ghi_chu: Mapped[str | None] = mapped_column(Text, nullable=True)
    cap_nhat_luc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)   # UTC
    cap_nhat_boi: Mapped[str | None] = mapped_column(String(60), nullable=True)


class BaoCaoNgayChu(Base):
    """Ba khối chữ trong ảnh báo cáo đầu ngày (Fox viết từ số liệu, Trưởng phòng sửa lại được)."""
    __tablename__ = "bao_cao_ngay_chu"
    __table_args__ = (UniqueConstraint("ngay", "phong_code", name="uq_bao_cao_ngay_chu"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ngay: Mapped[date] = mapped_column(Date, index=True)
    phong_code: Mapped[str] = mapped_column(String(20), index=True)
    trong_tam: Mapped[str | None] = mapped_column(Text, nullable=True)
    nhan_dinh: Mapped[str | None] = mapped_column(Text, nullable=True)
    thong_diep: Mapped[str | None] = mapped_column(Text, nullable=True)
    cap_nhat_luc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cap_nhat_boi: Mapped[str | None] = mapped_column(String(60), nullable=True)


class TonTheoDoi(Base):
    """Sale ghi tình trạng hợp đồng chưa online (trang Nhập tồn). Giữ theo mã HĐ qua các ngày; phần hợp đồng
    (tên KH, ngày tạo, acc) luôn đọc từ fact_internet nên không lưu lại ở đây."""
    __tablename__ = "ton_theo_doi"
    hop_dong: Mapped[str] = mapped_column(String(30), primary_key=True)
    ghi_chu: Mapped[str | None] = mapped_column(Text, nullable=True)
    loai_moc: Mapped[str | None] = mapped_column(String(10), nullable=True)      # hen | tra_ve
    ngay_moc: Mapped[date | None] = mapped_column(Date, nullable=True)
    phuong_an: Mapped[str | None] = mapped_column(String(60), nullable=True)
    cap_nhat_luc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)   # UTC
    cap_nhat_boi: Mapped[str | None] = mapped_column(String(60), nullable=True)


class DanhBa(Base):
    """Danh bạ liên hệ nội bộ (Soạn email + Danh bạ, chốt 10/10/2026). Mỗi nguồn là một bản chụp theo file:
    nạp lại file nào thì thay đúng các dòng của nguồn đó (PNC = Đà Nẵng vào Nam, TIN = Đà Nẵng ra Bắc).
    Người sale tự thêm là nguồn TAY. Hai file trùng người thì gộp lúc ĐỌC (`danh_ba.tat_ca`), không gộp lúc lưu."""
    __tablename__ = "danh_ba"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nguon: Mapped[str] = mapped_column(String(8), index=True)                     # PNC | TIN | TAY
    ho_ten: Mapped[str] = mapped_column(String(120))
    chuc_vu: Mapped[str | None] = mapped_column(String(160), nullable=True)
    email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    ext: Mapped[str | None] = mapped_column(String(30), nullable=True)
    di_dong: Mapped[str | None] = mapped_column(String(30), nullable=True)
    don_vi: Mapped[str | None] = mapped_column(String(80), nullable=True)          # chi nhánh / đơn vị: Đà Nẵng, Khánh Hòa...
    khu_vuc: Mapped[str | None] = mapped_column(String(80), nullable=True)         # sheet / khu vực lớn
    ghi_chu: Mapped[str | None] = mapped_column(Text, nullable=True)
    cap_nhat_luc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # UTC
    cap_nhat_boi: Mapped[str | None] = mapped_column(String(60), nullable=True)


class OnlineCa(Base):
    """Một ca chờ online trong ngày (mục Theo dõi Online của trang Báo cáo ngày, chốt 12/10/2026). Mỗi mã hợp đồng là MỘT
    phiếu riêng: gắn nhân viên, khung giờ dự kiến, trạng thái; mọi lần dời / đổi trạng thái ghi vào `lich_su` (JSON).
    Không lưu tên khách hàng. Sale TỰ cập nhật trạng thái, không lấy từ file Internet."""
    __tablename__ = "online_ca"
    __table_args__ = (UniqueConstraint("ngay", "phong_code", "ma_hd", name="uq_online_ca"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ngay: Mapped[date] = mapped_column(Date, index=True)
    phong_code: Mapped[str] = mapped_column(String(20), index=True)
    ma_hd: Mapped[str] = mapped_column(String(30))
    acc_norm: Mapped[str] = mapped_column(String(60), index=True)
    khung: Mapped[str] = mapped_column(String(16))                              # mã khung giờ HIỆN TẠI, xem online_ca.khung()
    khung_dau: Mapped[str | None] = mapped_column(String(16), nullable=True)    # khung giờ sale hẹn LÚC TẠO (để tính tỷ lệ đúng hẹn)
    trang_thai: Mapped[str] = mapped_column(String(12), default="du_kien")      # du_kien | dang_lam | da_online | doi_mai
    online_luc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # UTC, lúc sale bấm Đã online
    ghi_chu: Mapped[str | None] = mapped_column(Text, nullable=True)
    lich_su: Mapped[str | None] = mapped_column(Text, nullable=True)
    tao_luc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)   # UTC
    tao_boi: Mapped[str | None] = mapped_column(String(60), nullable=True)
    cap_nhat_luc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cap_nhat_boi: Mapped[str | None] = mapped_column(String(60), nullable=True)


class PhanHoi(Base):
    """Phản hồi hệ thống của người dùng gửi về Quản trị (chốt 28/10/2026)."""
    __tablename__ = "phan_hoi_he_thong"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(60), index=True)
    ho_ten: Mapped[str | None] = mapped_column(String(120), nullable=True)
    vai_tro: Mapped[str | None] = mapped_column(String(40), nullable=True)
    phong: Mapped[str | None] = mapped_column(String(120), nullable=True)
    loai: Mapped[str] = mapped_column(String(60), index=True)
    muc: Mapped[str] = mapped_column(String(120), index=True)
    noi_dung: Mapped[str] = mapped_column(Text)
    trang_thai: Mapped[str] = mapped_column(String(20), default="moi", index=True)   # moi | dang_xu_ly | da_xu_ly
    ghi_chu_admin: Mapped[str | None] = mapped_column(Text, nullable=True)
    tao_luc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    xu_ly_luc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    xu_ly_boi: Mapped[str | None] = mapped_column(String(60), nullable=True)


class BanTinNguoiNhan(Base):
    """Người nhận Bản tin 8h sáng qua Zalo Bot (giai đoạn 1: loại `bgd` và `admin`)."""
    __tablename__ = "ban_tin_nguoi_nhan"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ten: Mapped[str] = mapped_column(String(120))
    loai: Mapped[str] = mapped_column(String(20), index=True)
    chat_id: Mapped[str] = mapped_column(String(80))
    bat: Mapped[bool] = mapped_column(Boolean, default=True)
    tao_luc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class BanTinNhatKy(Base):
    """Mỗi (ngày số, người nhận, loại tin) đúng MỘT dòng: khoá duy nhất này chặn gửi trùng kể cả khi hai lượt gọi
    chạy cùng lúc. `ket_qua`: dang_gui | ok | loi (loi được thử lại tới `so_lan` tối đa)."""
    __tablename__ = "ban_tin_nhat_ky"
    __table_args__ = (UniqueConstraint("ngay_so", "nguoi_nhan_id", "loai", name="uq_ban_tin_nhat_ky"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ngay_so: Mapped[date] = mapped_column(Date, index=True)
    nguoi_nhan_id: Mapped[int] = mapped_column(Integer)
    ten_nguoi: Mapped[str] = mapped_column(String(120))
    loai: Mapped[str] = mapped_column(String(20))                    # bgd | nhac_admin
    ket_qua: Mapped[str] = mapped_column(String(12), default="dang_gui")
    ly_do: Mapped[str | None] = mapped_column(String(200), nullable=True)
    so_lan: Mapped[int] = mapped_column(Integer, default=1)
    gio_gui: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)   # UTC


class BanTinChoDuyet(Base):
    """Người vừa nhắn Zalo Bot, chờ Quản trị duyệt thành người nhận bản tin. KHÔNG lưu nội dung tin nhắn."""
    __tablename__ = "ban_tin_cho_duyet"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    ten: Mapped[str] = mapped_column(String(120))
    nhan_dau: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)      # UTC
    nhan_cuoi: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)     # UTC


from app.dvkh import models as _dvkh_models  # noqa: E402,F401  (đăng ký các bảng dv_* của khối DVKH để init_db tạo bảng)
