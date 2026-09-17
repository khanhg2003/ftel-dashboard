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
