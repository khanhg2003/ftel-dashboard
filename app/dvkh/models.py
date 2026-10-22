"""Bảng dữ liệu của khối Dịch vụ khách hàng (DVKH), tiền tố `dv_`.

Nguồn: file Excel "Báo cáo DVKH" (SR bị động, SR chủ động, rời mạng, công nợ, hai danh sách YCH / nợ cước).
- SR (yêu cầu của khách / chăm sóc chủ động) lưu từng dòng, khoá là Mã SR: mỗi lần nạp file luỹ kế của tháng thì
  dòng đã có được cập nhật theo trạng thái mới nhất, không cộng dồn các lần nạp.
- Rời mạng và công nợ là số đã tổng hợp sẵn trong file, lưu theo ngày chốt để vẽ xu hướng.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class DvNap(Base):
    """Lịch sử mỗi lần nạp file DVKH (để biết dữ liệu mới tới ngày nào, ai nạp, nạp bao nhiêu dòng)."""
    __tablename__ = "dv_nap"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ngay_chot: Mapped[date] = mapped_column(Date, index=True)               # ngày báo cáo người nạp chọn
    ten_file: Mapped[str] = mapped_column(String(200))
    nap_luc: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())   # UTC
    nap_boi: Mapped[str | None] = mapped_column(String(60), nullable=True)
    so_sr_bd: Mapped[int] = mapped_column(Integer, default=0)
    so_sr_cd: Mapped[int] = mapped_column(Integer, default=0)
    so_dong_roi_mang: Mapped[int] = mapped_column(Integer, default=0)
    so_dong_cong_no: Mapped[int] = mapped_column(Integer, default=0)
    tg_sr_bd_moi_nhat: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)   # SR bị động mới nhất trong file
    tg_sr_cd_moi_nhat: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ghi_chu: Mapped[str | None] = mapped_column(Text, nullable=True)


class DvSrBiDong(Base):
    """SR bị động: khách chủ động yêu cầu / khiếu nại / thanh lý... (một dòng = một Mã SR)."""
    __tablename__ = "dv_sr_bi_dong"
    ma_sr: Mapped[str] = mapped_column(String(60), primary_key=True)
    batch_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    chi_nhanh: Mapped[str | None] = mapped_column(String(10), index=True, nullable=True)          # DNG_01 / DNG_02
    quan: Mapped[str | None] = mapped_column(String(60), index=True, nullable=True)                # phường / xã (tên mới)
    so_hd: Mapped[str | None] = mapped_column(String(30), index=True, nullable=True)
    loai_yc: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    phan_loai: Mapped[str | None] = mapped_column(String(100), nullable=True)                     # loại khiếu nại / thay đổi / giải đáp
    hinh_thuc_kn: Mapped[str | None] = mapped_column(String(60), nullable=True)
    nguyen_nhan_1: Mapped[str | None] = mapped_column(String(200), nullable=True)
    nguyen_nhan_2: Mapped[str | None] = mapped_column(String(200), nullable=True)
    nguyen_nhan_3: Mapped[str | None] = mapped_column(String(200), nullable=True)
    loai_dv: Mapped[str | None] = mapped_column(String(80), nullable=True)
    kenh: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)               # kênh tiếp nhận
    nguon_tao: Mapped[str | None] = mapped_column(String(40), nullable=True)
    tg_yc: Mapped[datetime | None] = mapped_column(DateTime, index=True, nullable=True)           # giờ Việt Nam
    ngay_yc: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)
    ket_qua_lien_he: Mapped[str | None] = mapped_column(String(60), nullable=True)
    cong_cu: Mapped[str | None] = mapped_column(String(40), nullable=True)
    tg_cn_dau: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ket_qua_tu_van: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tinh_trang: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)         # Đã hoàn tất / Đang xử lý...
    phuong_an: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tg_cn_cuoi: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    net_tao: Mapped[str | None] = mapped_column(String(40), nullable=True)
    net_hien: Mapped[str | None] = mapped_column(String(40), nullable=True)
    pay_hien: Mapped[str | None] = mapped_column(String(40), nullable=True)
    cam_hien: Mapped[str | None] = mapped_column(String(40), nullable=True)
    nguoi_xu_ly: Mapped[str | None] = mapped_column(String(60), nullable=True)
    don_vi_xu_ly: Mapped[str | None] = mapped_column(String(80), nullable=True)
    nhan_su_au: Mapped[str | None] = mapped_column(String(60), index=True, nullable=True)         # CSKH phụ trách (Account IS)
    acc_tao: Mapped[str | None] = mapped_column(String(80), nullable=True)
    phi: Mapped[float | None] = mapped_column(Float, nullable=True)
    mien_giam_phi: Mapped[float | None] = mapped_column(Float, nullable=True)
    so_lan_cap_nhat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qua_han: Mapped[str | None] = mapped_column(String(30), index=True, nullable=True)            # Hoàn tất trong hạn / quá hạn...
    ych: Mapped[int] = mapped_column(Integer, default=0)                                            # 1 = hợp đồng nằm trong danh sách YCH
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DvSrChuDong(Base):
    """SR chủ động: DVKH chủ động chăm sóc khách có nguy cơ rời mạng / chất lượng kém (một dòng = một Mã SR)."""
    __tablename__ = "dv_sr_chu_dong"
    ma_sr: Mapped[str] = mapped_column(String(90), primary_key=True)
    batch_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    chi_nhanh: Mapped[str | None] = mapped_column(String(10), index=True, nullable=True)
    quan: Mapped[str | None] = mapped_column(String(60), index=True, nullable=True)
    so_hd: Mapped[str | None] = mapped_column(String(30), index=True, nullable=True)
    nhom_ct: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)           # nhóm chương trình
    chuong_trinh: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    tinh_trang_dau: Mapped[str | None] = mapped_column(String(120), nullable=True)
    do_uu_tien: Mapped[str | None] = mapped_column(String(20), nullable=True)
    diem_rm: Mapped[float | None] = mapped_column(Float, nullable=True)                           # điểm nguy cơ rời mạng, -1 = không có
    uu_tien_cs: Mapped[str | None] = mapped_column(String(10), nullable=True)
    nguon_pp: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tg_do: Mapped[datetime | None] = mapped_column(DateTime, index=True, nullable=True)           # giờ hệ thống đổ SR về
    ngay_do: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)
    tg_phan_cong: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ket_qua_lien_he: Mapped[str | None] = mapped_column(String(60), nullable=True)
    cong_cu: Mapped[str | None] = mapped_column(String(40), nullable=True)
    tg_cn_dau: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ket_qua_tu_van: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tinh_trang: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    phuong_an: Mapped[str | None] = mapped_column(String(60), nullable=True)
    tg_cn_cuoi: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    nguoi_xu_ly: Mapped[str | None] = mapped_column(String(60), nullable=True)
    nhan_su_au: Mapped[str | None] = mapped_column(String(60), index=True, nullable=True)
    so_lan_cs: Mapped[int | None] = mapped_column(Integer, nullable=True)                        # số lần chăm sóc
    ly_do_khong_lh: Mapped[str | None] = mapped_column(String(80), nullable=True)                 # lý do không cần liên hệ
    ly_do_mat_kn: Mapped[str | None] = mapped_column(String(80), nullable=True)                   # lý do mất kết nối
    qua_han: Mapped[str | None] = mapped_column(String(30), index=True, nullable=True)
    no_cuoc: Mapped[int] = mapped_column(Integer, default=0)                                        # 1 = hợp đồng đang nợ cước
    ych: Mapped[int] = mapped_column(Integer, default=0)                                            # 1 = hợp đồng nằm trong danh sách YCH
    sr_bd_trung: Mapped[str | None] = mapped_column(String(80), nullable=True)                    # loại SR bị động trùng hợp đồng
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DvRoiMang(Base):
    """Rời mạng đã tổng hợp theo phòng hoặc theo phường / xã tại một ngày chốt."""
    __tablename__ = "dv_roi_mang"
    __table_args__ = (UniqueConstraint("ngay_chot", "cap", "ten", name="uq_dv_roi_mang"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ngay_chot: Mapped[date] = mapped_column(Date, index=True)
    cap: Mapped[str] = mapped_column(String(10))                                   # phong | quan
    ten: Mapped[str] = mapped_column(String(80))
    kh_active: Mapped[float | None] = mapped_column(Float, nullable=True)         # KH Active hiện hành
    kh_dau_ky: Mapped[float | None] = mapped_column(Float, nullable=True)
    gross_pttb: Mapped[float | None] = mapped_column(Float, nullable=True)
    huy_tsd: Mapped[float | None] = mapped_column(Float, nullable=True)
    huy_ssd: Mapped[float | None] = mapped_column(Float, nullable=True)
    ctbdv: Mapped[float | None] = mapped_column(Float, nullable=True)
    ctbdv_khoi_phuc: Mapped[float | None] = mapped_column(Float, nullable=True)
    hssd_khoi_phuc: Mapped[float | None] = mapped_column(Float, nullable=True)
    ctbdv_chuyen_hssd: Mapped[float | None] = mapped_column(Float, nullable=True)
    cho_thanh_ly: Mapped[float | None] = mapped_column(Float, nullable=True)
    cho_tl_kpdv: Mapped[float | None] = mapped_column(Float, nullable=True)
    cho_tl_hssd: Mapped[float | None] = mapped_column(Float, nullable=True)
    ctbdv_du_kien: Mapped[float | None] = mapped_column(Float, nullable=True)
    kh_roi_mang: Mapped[float | None] = mapped_column(Float, nullable=True)
    ty_le_roi_active: Mapped[float | None] = mapped_column(Float, nullable=True)  # % rời mạng so với KH Active
    ty_le_roi_gross: Mapped[float | None] = mapped_column(Float, nullable=True)   # % rời mạng so với Gross PTTB
    net_pttb: Mapped[float | None] = mapped_column(Float, nullable=True)
    ty_le_giu: Mapped[float | None] = mapped_column(Float, nullable=True)
    ty_le_tang: Mapped[float | None] = mapped_column(Float, nullable=True)


class DvCongNo(Base):
    """Tỷ lệ thu công nợ theo ngày (tháng nợ, đơn vị): mỗi ngày hai số, theo doanh thu và theo số hoá đơn (bill)."""
    __tablename__ = "dv_cong_no"
    __table_args__ = (UniqueConstraint("ky_no", "ngay", "cap", "ten", name="uq_dv_cong_no"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ky_no: Mapped[str] = mapped_column(String(7), index=True)                      # tháng của hoá đơn, vd 2026-09
    ngay: Mapped[date] = mapped_column(Date, index=True)                           # ngày thu
    cap: Mapped[str] = mapped_column(String(10))                                   # phong | quan
    ten: Mapped[str] = mapped_column(String(60))
    ty_le_dt: Mapped[float | None] = mapped_column(Float, nullable=True)           # 0..1
    ty_le_bill: Mapped[float | None] = mapped_column(Float, nullable=True)         # 0..1


class DvCongNoChot(Base):
    """Ảnh chụp công nợ hệ thống đổ hằng ngày (số HĐ, tổng tiền, đã thanh toán, còn nợ) theo phòng hoặc phường / xã."""
    __tablename__ = "dv_cong_no_chot"
    __table_args__ = (UniqueConstraint("ngay_chot", "cap", "ten", "chi_nhanh", name="uq_dv_cong_no_chot"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ngay_chot: Mapped[date] = mapped_column(Date, index=True)
    ky_no: Mapped[str | None] = mapped_column(String(7), nullable=True)
    cap: Mapped[str] = mapped_column(String(10))                                   # phong | quan
    chi_nhanh: Mapped[str] = mapped_column(String(10), default="")                 # DNG_1 / DNG_2 (rỗng với cấp phòng tổng)
    ten: Mapped[str] = mapped_column(String(80))
    so_hd: Mapped[float | None] = mapped_column(Float, nullable=True)
    tong_tien: Mapped[float | None] = mapped_column(Float, nullable=True)
    hd_da_tt: Mapped[float | None] = mapped_column(Float, nullable=True)
    tt_da_tt: Mapped[float | None] = mapped_column(Float, nullable=True)
    hd_con_no: Mapped[float | None] = mapped_column(Float, nullable=True)
    tt_con_no: Mapped[float | None] = mapped_column(Float, nullable=True)
    ty_le_dt: Mapped[float | None] = mapped_column(Float, nullable=True)           # %
    ty_le_bill: Mapped[float | None] = mapped_column(Float, nullable=True)         # %


class DvSrBdThem(Base):
    """Cột bổ sung của SR bị động (gói dịch vụ hiện tại, đơn vị tạo SR, duyệt đề xuất, số lần trùng).

    Tách bảng riêng, khoá cùng Mã SR, để thêm phân tích mà không phải sửa cấu trúc bảng SR đã có trên Supabase.
    """
    __tablename__ = "dv_sr_bd_them"
    ma_sr: Mapped[str] = mapped_column(String(60), primary_key=True)
    batch_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    goi_net: Mapped[str | None] = mapped_column(String(60), nullable=True)
    goi_pay: Mapped[str | None] = mapped_column(String(60), nullable=True)
    goi_cam: Mapped[str | None] = mapped_column(String(80), nullable=True)
    don_vi_tao: Mapped[str | None] = mapped_column(String(80), nullable=True)
    duyet_de_xuat: Mapped[str | None] = mapped_column(String(120), nullable=True)
    trung: Mapped[int | None] = mapped_column(Integer, nullable=True)


class DvAuKh(Base):
    """Số khách hàng mỗi CSKH (Account IS) phụ trách, lấy từ bảng "Count of Acc NVVP" của sheet BC SR bị động.

    Dùng làm mẫu số để so tải việc công bằng giữa các CSKH (người phụ trách nhiều khách thì nhiều SR là bình thường).
    """
    __tablename__ = "dv_au_kh"
    __table_args__ = (UniqueConstraint("ngay_chot", "acc", name="uq_dv_au_kh"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ngay_chot: Mapped[date] = mapped_column(Date, index=True)
    acc: Mapped[str] = mapped_column(String(60))
    so_kh: Mapped[int] = mapped_column(Integer)


class DvDanhSach(Base):
    """Hai danh sách hợp đồng dùng để gắn cờ SR: YCH (yêu cầu huỷ) và nợ cước."""
    __tablename__ = "dv_danh_sach"
    __table_args__ = (UniqueConstraint("loai", "so_hd", name="uq_dv_danh_sach"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    loai: Mapped[str] = mapped_column(String(10), index=True)                      # ych | no_cuoc
    so_hd: Mapped[str] = mapped_column(String(30), index=True)
    ngay_chot: Mapped[date] = mapped_column(Date)
