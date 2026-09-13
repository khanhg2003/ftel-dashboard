"""Đăng nhập, phân quyền và phạm vi dữ liệu người dùng được xem."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from flask_login import LoginManager, UserMixin, current_user
from sqlalchemy import select

from app.db import session_scope
from app.models import AuditLog, User

ph = PasswordHasher()
login_manager = LoginManager()
login_manager.login_view = "login"

KHOA_SAU = 5            # sai 5 lần thì khoá
KHOA_PHUT = 15

ROLE_LABEL = {"admin": "Quản trị (BGD)", "operator": "Nhập liệu",
              "phong": "Trưởng phòng", "nhanvien": "Nhân viên"}
ROLE_UPLOAD = {"admin", "operator"}
ROLE_CHAT = {"admin"}
ROLE_SETTINGS = {"admin"}
# Hai lớp dữ liệu:
# - SỐ CHUNG (theo phòng, bầy, chi nhánh): Quản trị, Nhập liệu, Trưởng phòng đều xem toàn chi nhánh.
# - CHI TIẾT NHÂN SỰ (tên, acc, số từng người): Quản trị xem mọi phòng, Trưởng phòng chỉ phòng
#   mình phụ trách, Nhập liệu không xem.
ROLE_XEM_NHAN_SU = {"admin", "phong"}


class SessionUser(UserMixin):
    def __init__(self, row: User):
        self.id = str(row.id)
        self.username = row.username
        self.ho_ten = row.ho_ten or row.username
        self.role = row.role
        self.ma_nv = row.ma_nv
        self.scope = json.loads(row.scope) if row.scope else []
        if self.role == "bay":       # vai trò Giám đốc Bầy đã bỏ: tài khoản cũ quy về Trưởng phòng
            self.role = "phong"      # của các phòng trong bầy đó, không bị mở rộng quyền
            self.scope = _phong_cua_bay(self.scope)

    # --- quyền
    @property
    def duoc_upload(self) -> bool:
        return self.role in ROLE_UPLOAD

    @property
    def duoc_chat(self) -> bool:
        return self.role in ROLE_CHAT

    @property
    def duoc_cau_hinh(self) -> bool:
        return self.role in ROLE_SETTINGS

    @property
    def duoc_xem_nhan_su(self) -> bool:
        return self.role in ROLE_XEM_NHAN_SU

    def phong_duoc_xem(self) -> list[str] | None:
        """Phạm vi SỐ CHUNG. None = toàn chi nhánh, ngược lại là danh sách mã phòng."""
        if self.role in ("admin", "operator", "phong"):
            return None
        if self.role == "nhanvien":
            return self.phong_cua_minh()
        return list(self.scope)

    def phong_nhan_su(self) -> list[str] | None:
        """Phạm vi CHI TIẾT NHÂN SỰ. None = mọi phòng, [] = không được xem ai."""
        if self.role == "admin":
            return None
        if self.role == "phong":
            return list(self.scope)
        return []

    def phong_cua_minh(self) -> list[str]:
        """Nhân viên chỉ thấy phòng của chính mình (tra theo mã NV, sau đó tới phạm vi)."""
        if self.ma_nv:
            from sqlalchemy import select as _select

            from app.models import StaffMap
            with session_scope() as s:
                codes = [r.phong_code for r in s.execute(
                    _select(StaffMap).where(StaffMap.ma_nv == self.ma_nv)).scalars()
                    if r.phong_code]
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
        return SessionUser(row) if row and row.active else None


def xac_thuc(username: str, password: str) -> tuple[SessionUser | None, str]:
    with session_scope() as s:
        row = s.execute(select(User).where(User.username == username)).scalars().first()
        if row is None or not row.active:
            return None, "Sai tài khoản hoặc mật khẩu."
        if row.locked_until and row.locked_until > datetime.now():
            return None, f"Tài khoản đang bị khoá tới {row.locked_until:%H:%M}."
        try:
            ph.verify(row.password_hash, password)
        except VerifyMismatchError:
            row.failed_logins = (row.failed_logins or 0) + 1
            if row.failed_logins >= KHOA_SAU:
                row.locked_until = datetime.now() + timedelta(minutes=KHOA_PHUT)
                row.failed_logins = 0
            s.add(AuditLog(username=username, action="login_fail"))
            return None, "Sai tài khoản hoặc mật khẩu."
        row.failed_logins = 0
        row.last_login = datetime.now()
        s.add(AuditLog(username=username, action="login_ok"))
        return SessionUser(row), ""


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
        s.add(AuditLog(username=username, action="doi_mat_khau"))
    return ""


def ghi_log(action: str, detail: str = "") -> None:
    user = getattr(current_user, "username", None)
    with session_scope() as s:
        s.add(AuditLog(username=user, action=action, detail=detail))
