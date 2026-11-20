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
# Tài khoản kỹ thuật (superadmin): bypass mọi kiểm tra trang nhập liệu hằng ngày.
# BGĐ dùng role "admin" nhưng không phải tài khoản này - chủ app chốt 28/09/2026.
import os as _os
ADMIN_USERNAME: str = _os.getenv("ADMIN_USERNAME", "admin").strip().lower()

ROLE_LABEL = {"admin": "Quản trị (BGD)", "operator": "Nhập liệu",
              "phong": "Trưởng phòng", "nvkd": "Nhân viên KD", "nhanvien": "Nhân viên", "dvkh": "Khối DVKH",
              "online": "Phòng Online"}
# Khối làm việc (app/ui/khoi.py): Quản trị (BGĐ) chuyển được giữa mọi khối; "dvkh" chỉ thấy khối Dịch vụ khách hàng;
# các vai trò còn lại là của khối Kinh doanh. Thêm khối Kỹ thuật thì thêm vai trò "kt" vào đây.
ROLE_KHOI = {"dvkh": "DVKH"}
ROLE_NAP_DVKH = {"admin", "dvkh"}
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
TRANG_NVKD = {"/baocaongay", "/nhapton", "/soanmail", "/danhba", "/giafpt", "/phong", "/ads", "/taikhoan", "/huongdan"}
# Tài khoản vai trò "online" (Phòng Online, chốt 07/11/2026) chỉ vào đúng trang này (+ Tài khoản, Hướng dẫn).
TRANG_ONLINE = {"/phongonline", "/baocaongay", "/soanmail", "/danhba", "/giafpt", "/taikhoan", "/huongdan"}
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
        return dataset in self.loai_duoc_nap() or (dataset == "pheu_ban_hang" and self.duoc_upload)

    @property
    def la_superadmin(self) -> bool:
        """Tài khoản kỹ thuật (username=ADMIN_USERNAME): bypass kiểm tra trang nhập liệu hằng ngày.

        BGĐ dùng role "admin" nhưng KHÔNG phải superadmin - không vào Báo cáo ngày / Nhập tồn /
        Ads IBB7 (chủ app chốt 28/09/2026).
        """
        return self.username.strip().lower() == ADMIN_USERNAME

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
        """Xem Ads IBB7 (chỉ xem). Sửa cấu hình Ads vẫn là duoc_cau_hinh.

        BGĐ (role=admin) KHÔNG xem được: Ads IBB7 là trang nhập liệu hằng ngày của phòng.
        Chỉ superadmin (username=ADMIN_USERNAME) và nvkd IBB7 mới vào.
        """
        return self.la_superadmin or (self.role == "nvkd" and PHONG_ADS in self.scope)

    @property
    def duoc_xem_phong_online(self) -> bool:
        """Trang Phòng Online (nhóm 5 người của IBB2): BGĐ (role admin, KHÔNG phải tài khoản kỹ thuật) và tài khoản
        vai trò "online". Các tài khoản khác kể cả superadmin không xem được (chủ app chốt 07/11/2026)."""
        return self.role == "online" or (self.role == "admin" and not self.la_superadmin)

    def _phong_bat(self, muc: str) -> list[str]:
        """Phòng bật một mục trong rules.yml, giao với phạm vi nhân sự của tài khoản.

        Nhập tồn và Báo cáo ngày là chỗ NHẬP LIỆU hằng ngày của đúng một phòng, không phải chỗ
        xem báo cáo. Chỉ admin (hệ thống) và nvkd của đúng phòng đó mới vào. BGĐ và các tài
        khoản xem nhiều phòng KHÔNG vào - chủ app chốt 28/09/2026.
        """
        from app.config import rules_config
        bat = list((rules_config().get(muc) or {}).get("phong") or [])
        if self.la_superadmin:                          # superadmin: bypass mọi kiểm tra
            return bat
        pham_vi = self.phong_nhan_su()
        if pham_vi is None or not set(pham_vi) <= set(bat):
            return []
        return [c for c in bat if c in set(pham_vi)]

    def phong_nhap_ton(self) -> list[str]:
        """Phòng được xem / ghi Nhập tồn."""
        return self._phong_bat("nhap_ton")

    def phong_bao_cao_ngay(self) -> list[str]:
        """Phòng được xem / ghi Báo cáo đầu ngày (chốt 24/09/2026). Vai trò "online": báo cáo riêng của nhóm Phòng Online (mã ảo
        ONLINE, chốt 10/11/2026), KHÔNG liên quan IBB7; superadmin không thấy mã này."""
        if self.role == "online":
            from app import phong_online as po
            return [po.MA] if po.bao_cao_ngay_bat() else []
        return self._phong_bat("bao_cao_ngay")

    def phong_soan_mail(self) -> list[str]:
        """Phòng được dùng Soạn email + Danh bạ (nvkd của phòng bật ở rules.yml; BGĐ / admin dùng được mọi lúc)."""
        return self._phong_bat("soan_mail")

    def phong_ban_tinh(self) -> list[str]:
        """Phòng được xem hai phần "Bán theo tỉnh" và "Ai bán ở tỉnh nào" của Phân tích bán hàng (nvkd của phòng bật ở rules.yml)."""
        return self._phong_bat("ban_tinh")

    @property
    def duoc_xem_ban_tinh(self) -> bool:
        """Bán theo tỉnh: Quản trị (BGĐ + tài khoản kỹ thuật) và nvkd đúng phòng bật ở rules.yml (IBB7, chủ app chốt 22/10/2026).

        nvkd chỉ thấy đúng hai phần đó; chi tiết nhân viên vẫn bị giới hạn ở phòng mình (`phong_nhan_su`)."""
        return self.role == "admin" or self.la_superadmin or (self.role == "nvkd" and bool(self.phong_ban_tinh()))

    @property
    def duoc_xem_ban_tinh_phong(self) -> bool:
        """Trưởng phòng xem thẻ "Bán theo tỉnh" nhưng CHỈ số của phòng mình (chủ app chốt 20/11/2026); `phantich_tinh` tự lọc theo `scope`."""
        return self.role == "phong" and bool(self.scope)

    @property
    def duoc_soan_mail(self) -> bool:
        """Soạn email + Danh bạ: admin (BGĐ + tài khoản kỹ thuật), nvkd đúng phòng IBB7 (chủ app chốt 10/10/2026) và tài khoản Phòng Online (10/11/2026)."""
        return (self.role in ("admin", "online") or self.la_superadmin
                or (self.role == "nvkd" and bool(self.phong_soan_mail())))

    @property
    def duoc_nhap_ton(self) -> bool:
        return bool(self.phong_nhap_ton())

    @property
    def duoc_bao_cao_ngay(self) -> bool:
        return bool(self.phong_bao_cao_ngay())

    def khoi_duoc_xem(self) -> list[str]:
        """Các khối tài khoản này được vào (theo thứ tự hiển thị). Quản trị: mọi khối."""
        from app.ui.khoi import THU_TU
        if self.role == "admin":
            return list(THU_TU)
        return [ROLE_KHOI.get(self.role, "KD")]

    @property
    def duoc_nap_dvkh(self) -> bool:
        """Cập nhật file Excel của khối DVKH."""
        return self.role in ROLE_NAP_DVKH

    def vao_duoc(self, path: str) -> bool:
        """Chỉ vào trang của khối mình; Nhân viên KD còn bị giới hạn ở danh sách trang riêng, vai trò khác do từng trang tự kiểm."""
        from app.ui.khoi import khoi_cua_duong_dan
        khoi = khoi_cua_duong_dan(path)
        if khoi is not None and khoi not in self.khoi_duoc_xem():
            return False
        if path in ("/phongonline", "/leads"):
            return self.duoc_xem_phong_online
        if self.role == "online":
            return path in TRANG_ONLINE
        if self.role != "nvkd":
            return True
        return path in TRANG_NVKD or (path == "/phantich" and self.duoc_xem_ban_tinh)

    def phong_duoc_xem(self) -> list[str] | None:
        """Phạm vi SỐ CHUNG. None = toàn chi nhánh, ngược lại là danh sách mã phòng."""
        if self.role in ("admin", "operator", "phong", "nvkd"):
            return None
        if self.role == "online":        # chỉ trang Phòng Online, tự lấy số của nhóm; không có số chung nào khác
            return []
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
