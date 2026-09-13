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

ROLE_LABEL = {"admin": "Quản trị (BGD)", "operator": "Nhập liệu", "bay": "Giám đốc Bầy",
              "phong": "Trưởng phòng", "nhanvien": "Nhân viên"}
ROLE_UPLOAD = {"admin", "operator"}
ROLE_CHAT = {"admin", "bay"}
ROLE_SETTINGS = {"admin"}


class SessionUser(UserMixin):
    def __init__(self, row: User):
        self.id = str(row.id)
        self.username = row.username
        self.ho_ten = row.ho_ten or row.username
        self.role = row.role
        self.ma_nv = row.ma_nv
        self.scope = json.loads(row.scope) if row.scope else []

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

    def phong_duoc_xem(self) -> list[str] | None:
        """None = xem tất cả. Ngược lại là danh sách mã phòng."""
        from app.org import phong_order

        if self.role in ("admin", "operator"):
            return None
        if self.role == "bay":
            return [p["code"] for p in phong_order() if p["bay"] in self.scope]
        if self.role == "nhanvien":
            return self.phong_cua_minh()
        return list(self.scope)

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
