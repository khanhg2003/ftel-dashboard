"""Đăng nhập, phân quyền và phạm vi dữ liệu người dùng được xem."""
from __future__ import annotations

import json
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from flask import session as flask_session
from flask_login import LoginManager, UserMixin, current_user
from sqlalchemy import select

from app.db import session_scope
from app.models import AuditLog, User
from app.thoi_gian import chu_gio_vn, utc_bay_gio

ph = PasswordHasher()
login_manager = LoginManager()
login_manager.login_view = "login"

KHOA_SAU = 5            # sai 5 lần thì khoá
KHOA_PHUT = 15

ROLE_LABEL = {"admin": "Quản trị (BGD)", "operator": "Nhập liệu",
              "phong": "Trưởng phòng", "nvkd": "Nhân viên KD", "nhanvien": "Nhân viên"}
# Nạp dữ liệu: Trưởng phòng được nạp 3 file bán hàng (họ là người tải file hằng ngày), nhưng
# file NSLĐ và Danh mục nhân viên thì chỉ Quản trị (BGĐ) - BGĐ chốt 16/09/2026.
ROLE_UPLOAD = {"admin", "operator", "phong"}
LOAI_SO_BAN = {"internet", "fptplay", "camera"}
LOAI_NHAN_SU = {"nhan_su", "danh_muc_nv"}
ROLE_UPLOAD_NHAN_SU = {"admin"}
ROLE_CHAT = {"admin"}
ROLE_SETTINGS = {"admin"}
# Hai lớp dữ liệu:
# - SỐ CHUNG (theo phòng, bầy, chi nhánh): Quản trị, Nhập liệu, Trưởng phòng đều xem toàn chi nhánh.
# - CHI TIẾT NHÂN SỰ (tên, acc, số từng người): Quản trị xem mọi phòng, Trưởng phòng chỉ phòng
#   mình phụ trách, Nhập liệu không xem.
ROLE_XEM_NHAN_SU = {"admin", "phong", "nvkd"}
# Nhân viên KD (tài khoản dùng chung của một phòng, chốt 21/09/2026): chỉ vào đúng các trang này,
# chi tiết nhân sự chỉ phòng mình, Ads chỉ khi phòng mình là phòng chạy Ads.
TRANG_NVKD = {"/nhapton", "/phong", "/ads", "/taikhoan", "/huongdan"}
PHONG_ADS = "IBB7"


class SessionUser(UserMixin):
    def __init__(self, row: User):
        self.id = str(row.id)
        self.username = row.username
        self.ho_ten = row.ho_ten or row.username
        self.role = row.role
        self.ma_nv = row.ma_nv
        self.session_version = getattr(row, "session_version", 0) or 0
        self.scope = json.loads(row.scope) if row.scope else []
        if self.role == "bay":       # vai trò Giám đốc Bầy đã bỏ: tài khoản cũ quy về Trưởng phòng
            self.role = "phong"      # của các phòng trong bầy đó, không bị mở rộng quyền
            self.scope = _phong_cua_bay(self.scope)

    # --- quyền
    @property
    def duoc_upload(self) -> bool:
        return self.role in ROLE_UPLOAD

    def loai_duoc_nap(self) -> set[str]:
        """Các loại file tài khoản này được nạp (và được gỡ)."""
        if not self.duoc_upload:
            return set()
        if self.role in ROLE_UPLOAD_NHAN_SU:
            return LOAI_SO_BAN | LOAI_NHAN_SU
        return set(LOAI_SO_BAN)

    def duoc_nap(self, dataset: str) -> bool:
        return dataset in self.loai_duoc_nap()

    @property
    def duoc_chat(self) -> bool:
        return self.role in ROLE_CHAT

    @property
    def duoc_cau_hinh(self) -> bool:
        return self.role in ROLE_SETTINGS

    @property
    def duoc_xem_nhan_su(self) -> bool:
        return self.role in ROLE_XEM_NHAN_SU

    @property
    def duoc_xem_ads(self) -> bool:
        """Xem Ads IBB7 (chỉ xem). Sửa cấu hình Ads vẫn là duoc_cau_hinh."""
        return self.duoc_cau_hinh or (self.role == "nvkd" and PHONG_ADS in self.scope)

    def phong_nhap_ton(self) -> list[str]:
        """Phòng được xem / ghi Nhập tồn: phòng bật mục này (rules.yml) giao với phạm vi nhân sự."""
        from app.config import rules_config
        bat = list((rules_config().get("nhap_ton") or {}).get("phong") or [])
        pham_vi = self.phong_nhan_su()
        return bat if pham_vi is None else [c for c in bat if c in set(pham_vi)]

    @property
    def duoc_nhap_ton(self) -> bool:
        return bool(self.phong_nhap_ton())

    def vao_duoc(self, path: str) -> bool:
        """Nhân viên KD chỉ vào các trang của mình; vai trò khác do từng trang tự kiểm."""
        return self.role != "nvkd" or path in TRANG_NVKD

    def phong_duoc_xem(self) -> list[str] | None:
        """Phạm vi SỐ CHUNG. None = toàn chi nhánh, ngược lại là danh sách mã phòng."""
        if self.role in ("admin", "operator", "phong", "nvkd"):
            return None
        if self.role == "nhanvien":
            return self.phong_cua_minh()
        return list(self.scope)

    def phong_nhan_su(self) -> list[str] | None:
        """Phạm vi CHI TIẾT NHÂN SỰ. None = mọi phòng, [] = không được xem ai."""
        if self.role == "admin":
            return None
        if self.role in ("phong", "nvkd"):
            return list(self.scope)
        return []

    def phong_cua_minh(self) -> list[str]:
        """Nhân viên chỉ thấy phòng của chính mình (tra theo mã NV, sau đó tới phạm vi)."""
        if self.ma_nv:
            from sqlalchemy import select as _select

            from app.ingest.normalize import norm_manv
            from app.models import StaffMap
            ma = norm_manv(self.ma_nv)          # so khớp bỏ qua số 0 ở đầu
            with session_scope() as s:
                codes = [r.phong_code for r in s.execute(
                    _select(StaffMap).where(StaffMap.ma_nv.isnot(None))).scalars()
                    if r.phong_code and norm_manv(r.ma_nv) == ma]
            if codes:
                return sorted(set(codes))
        return list(self.scope)


def _phong_cua_bay(ma_bay: list[str]) -> list[str]:
    from app.org import phong_order
    return [p["code"] for p in phong_order() if p["bay"] in set(ma_bay)]


def loc_nhan_su(scope_so: list[str] | None, scope_nhan_su: list[str] | None) -> list[str] | None:
    """Giao của phạm vi đang lọc trên trang (chi nhánh...) với phạm vi được xem nhân sự."""
    if scope_nhan_su is None:
        return scope_so
    if scope_so is None:
        return list(scope_nhan_su)
    return [c for c in scope_so if c in set(scope_nhan_su)]


@login_manager.user_loader
def load_user(user_id: str):
    with session_scope() as s:
        row = s.get(User, int(user_id))
        if row is None or not row.active:
            return None
        # Kiểm tra phiên bản session: nếu mật khẩu đã đổi thì phiên cũ bị vô hiệu
        sv_session = flask_session.get("_sv")
        sv_db = getattr(row, "session_version", 0) or 0
        if sv_session is not None and sv_session != sv_db:
            return None
        return SessionUser(row)


def xac_thuc(username: str, password: str) -> tuple[SessionUser | None, str]:
    with session_scope() as s:
        row = s.execute(select(User).where(User.username == username)).scalars().first()
        if row is None or not row.active:
            return None, "Sai tài khoản hoặc mật khẩu."
        if row.locked_until and row.locked_until > utc_bay_gio():
            return None, f"Tài khoản đang bị khoá tới {chu_gio_vn(row.locked_until, '%H:%M')}."
        try:
            ph.verify(row.password_hash, password)
        except VerifyMismatchError:
            row.failed_logins = (row.failed_logins or 0) + 1
            if row.failed_logins >= KHOA_SAU:
                row.locked_until = utc_bay_gio() + timedelta(minutes=KHOA_PHUT)
                row.failed_logins = 0
            s.add(AuditLog(username=username, action="login_fail"))
            return None, "Sai tài khoản hoặc mật khẩu."
        row.failed_logins = 0
        row.last_login = utc_bay_gio()
        s.add(AuditLog(username=username, action="login_ok"))
        user = SessionUser(row)
        # Lưu session_version vào Flask session để kiểm tra sau khi đổi mật khẩu
        flask_session["_sv"] = user.session_version
        return user, ""


def doi_mat_khau(username: str, mat_khau_cu: str, mat_khau_moi: str) -> str:
    if len(mat_khau_moi) < 8:
        return "Mật khẩu mới phải từ 8 ký tự."
    with session_scope() as s:
        row = s.execute(select(User).where(User.username == username)).scalars().first()
        if row is None:
            return "Không tìm thấy tài khoản."
        try:
            ph.verify(row.password_hash, mat_khau_cu)
        except VerifyMismatchError:
            return "Mật khẩu hiện tại không đúng."
        row.password_hash = ph.hash(mat_khau_moi)
        # Tăng session_version → buộc các máy khác đăng nhập lại
        row.session_version = (row.session_version or 0) + 1
        s.add(AuditLog(username=username, action="doi_mat_khau"))
        new_sv = row.session_version
    # Cập nhật session hiện tại để người đổi mật khẩu không bị logout
    flask_session["_sv"] = new_sv
    return ""


def ghi_log(action: str, detail: str = "") -> None:
    user = getattr(current_user, "username", None)
    with session_scope() as s:
        s.add(AuditLog(username=user, action=action, detail=detail))
