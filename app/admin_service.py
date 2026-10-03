"""Nghiệp vụ quản trị: tài khoản, danh mục nhân sự, lịch sử nạp, chất lượng dữ liệu."""
from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd

from app.bo_nho import ghi
from argon2 import PasswordHasher
from sqlalchemy import delete, select, text

from app.canh_bao import la_acc_tam
from app.db import engine, session_scope
from app.ingest.normalize import ma_nv_nhu_nhap, norm_acc, norm_text, parse_date
from app.models import (AuditLog, FactCamera, FactFptPlay, FactInternet, HrMonthly, StaffMap,
                        UploadBatch, User)
from app.org import phong_order
from app.thoi_gian import chu_gio_vn, gio_viet_nam, utc_bay_gio

ph = PasswordHasher()
ROLES = [("admin", "Quản trị (BGD)"), ("operator", "Nhập liệu"), ("phong", "Trưởng phòng"),
         ("nvkd", "Nhân viên KD")]
ROLE_CO_PHONG = {"phong", "nvkd"}       # vai trò phải gán phòng (Nhân viên KD: tài khoản dùng chung của phòng)
ROLE_TEN = {**dict(ROLES), "bay": "Trưởng phòng", "nhanvien": "Nhân viên"}
TEN_ROLE = {v: k for k, v in ROLES}
FACTS = {"internet": FactInternet, "fptplay": FactFptPlay, "camera": FactCamera}


# ------------------------------------------------------------------ tài khoản
def danh_sach_user() -> pd.DataFrame:
    df = pd.read_sql_query(text("""SELECT id, username, ho_ten, email, role, scope, ma_nv, active,
                                    last_login, locked_until
                             FROM users ORDER BY role, username"""), engine)
    if df.empty:
        return df
    # Giữ nguyên mã NV dạng chuỗi (kể cả số 0 ở đầu). pd.read_sql tự suy kiểu numeric
    # cho cột toàn chữ số, khiến "067376" thành 67376 → mất số 0.
    if "ma_nv" in df.columns:
        df["ma_nv"] = df["ma_nv"].apply(lambda v: str(v).split(".")[0] if pd.notna(v) and v != "" else "")
    df["vai_tro"] = df["role"].map(ROLE_TEN).fillna(df["role"])
    df["pham_vi"] = [_scope_text(s) if r in ROLE_CO_PHONG | {"bay"} else "Toàn chi nhánh"
                     for s, r in zip(df["scope"], df["role"])]
    df["trang_thai"] = df.apply(
        # locked_until trống đọc ra NaT - NaT vẫn "đúng" khi xét if và str(NaT)="NaT" > "2026..." nên trước đây mọi
        # tài khoản bị hiện "Đang khoá" ngay khi có một người bị khoá (cột chuyển sang kiểu ngày giờ)
        lambda r: "Đang khoá" if (pd.notna(r.locked_until) and pd.Timestamp(r.locked_until) > pd.Timestamp(utc_bay_gio()))
        else ("Đang dùng" if r.active else "Ngừng dùng"), axis=1)
    df["lan_cuoi"] = [chu_gio_vn(v) for v in df["last_login"]]
    return df


def _scope_text(scope) -> str:
    if not scope:
        return "Chưa chọn phòng"
    try:
        ma = json.loads(scope)
    except (TypeError, ValueError):
        return str(scope)
    ten = {p["code"]: p["ten"] for p in phong_order()}
    from app.org import bay_info
    ten.update({c: b["ten"] for c, b in bay_info().items()})
    return ", ".join(ten.get(m, m) for m in ma) if ma else "Chưa chọn phòng"


def luu_user(rows: list[dict], nguoi_thuc_hien: str) -> tuple[int, list[str]]:
    """Thêm/cập nhật tài khoản từ bảng trên giao diện. Trả về (số bản ghi, cảnh báo)."""
    ten2ma = {p["ten"]: p["code"] for p in phong_order()}
    from app.org import bay_info
    ten2ma.update({b["ten"]: c for c, b in bay_info().items()})
    canh_bao: list[str] = []
    n = 0
    with session_scope() as s:
        for r in rows or []:
            username = norm_text(r.get("username")).lower()
            if not username:
                continue
            row = s.execute(select(User).where(User.username == username)).scalars().first()
            moi = row is None
            if moi:
                row = User(username=username, password_hash=ph.hash("Ftel@2026"))
                s.add(row)
                canh_bao.append(f"{username}: mật khẩu khởi tạo là Ftel@2026")
            row.ho_ten = norm_text(r.get("ho_ten")) or username
            row.email = norm_text(r.get("email")) or None
            role = TEN_ROLE.get(norm_text(r.get("vai_tro")), r.get("vai_tro") or "phong")
            row.role = role if role in dict(ROLES) else "phong"
            row.ma_nv = ma_nv_nhu_nhap(r.get("ma_nv")) or None
            pv = [x.strip() for x in norm_text(r.get("pham_vi")).split(",") if x.strip()]
            pv = [ten2ma.get(x, x) for x in pv if x.lower() != "toàn chi nhánh"]
            if row.role not in ROLE_CO_PHONG:
                pv = []                  # Quản trị / Nhập liệu luôn xem toàn chi nhánh
            row.scope = json.dumps(pv, ensure_ascii=False) if pv else None
            row.active = norm_text(r.get("trang_thai")) != "Ngừng dùng"
            if norm_text(r.get("trang_thai")) != "Đang khoá":
                row.locked_until = None
                row.failed_logins = 0
            n += 1
        s.add(AuditLog(username=nguoi_thuc_hien, action="luu_tai_khoan", detail=f"{n} tài khoản"))
    return n, canh_bao


def pham_vi_options() -> list[dict]:
    """Danh sách phòng để chọn phòng phụ trách của Trưởng phòng (không phải gõ tay)."""
    return [{"label": p["ten"], "value": p["code"]} for p in phong_order()]


def them_user(d: dict, nguoi_thuc_hien: str) -> tuple[bool, str]:
    """Tạo tài khoản mới từ hộp thoại. Trả về (thành công, thông báo)."""
    username = norm_text(d.get("username")).lower()
    mat_khau = d.get("mat_khau") or ""
    if not username:
        return False, "Chưa nhập tên tài khoản."
    if len(username) < 3 or " " in username:
        return False, "Tên tài khoản từ 3 ký tự và không chứa dấu cách."
    if len(mat_khau) < 8:
        return False, "Mật khẩu phải từ 8 ký tự."
    role = d.get("role") or "phong"
    if role not in ROLE_TEN:
        return False, "Vai trò không hợp lệ."
    pham_vi = [x for x in (d.get("pham_vi") or []) if x]
    if role in ROLE_CO_PHONG and not pham_vi:
        return False, f"{ROLE_TEN[role]} bắt buộc chọn phòng phụ trách."
    if role not in ROLE_CO_PHONG:
        pham_vi = []
    with session_scope() as s:
        if s.execute(select(User).where(User.username == username)).scalars().first():
            return False, f"Tài khoản “{username}” đã tồn tại."
        s.add(User(username=username, ho_ten=norm_text(d.get("ho_ten")) or username,
                   email=norm_text(d.get("email")) or None, role=role,
                   ma_nv=ma_nv_nhu_nhap(d.get("ma_nv")) or None,
                   scope=json.dumps(pham_vi, ensure_ascii=False) if pham_vi else None,
                   password_hash=ph.hash(mat_khau), active=True))
        s.add(AuditLog(username=nguoi_thuc_hien, action="them_tai_khoan", detail=username))
    return True, f"Đã tạo tài khoản “{username}” ({ROLE_TEN[role]})."


def xoa_user(usernames: list[str], nguoi_thuc_hien: str) -> tuple[int, list[str]]:
    """Xoá tài khoản. Không cho tự xoá mình và không cho xoá tài khoản quản trị cuối cùng."""
    bo_qua: list[str] = []
    n = 0
    with session_scope() as s:
        con_admin = s.query(User).filter(User.role == "admin", User.active.is_(True)).count()
        for u in usernames or []:
            u = norm_text(u).lower()
            if u == norm_text(nguoi_thuc_hien).lower():
                bo_qua.append(f"{u}: không tự xoá tài khoản đang đăng nhập")
                continue
            row = s.execute(select(User).where(User.username == u)).scalars().first()
            if row is None:
                continue
            if row.role == "admin" and con_admin <= 1:
                bo_qua.append(f"{u}: phải còn ít nhất một tài khoản quản trị")
                continue
            if row.role == "admin":
                con_admin -= 1
            s.delete(row)
            n += 1
        s.add(AuditLog(username=nguoi_thuc_hien, action="xoa_tai_khoan",
                       detail=", ".join(usernames or [])))
    return n, bo_qua


SO_NGAY_TU_XOA = 5  # Trưởng phòng không đăng nhập bao nhiêu ngày thì tự xoá


def xoa_truong_phong_khong_dang_nhap() -> list[str]:
    """Tự động xoá tài khoản Trưởng phòng không đăng nhập trong 5 ngày gần nhất.

    Chỉ áp dụng cho role "phong" (Trưởng phòng). Tài khoản chưa từng đăng nhập
    (last_login IS NULL) thì tính từ lúc tạo tài khoản (created_at).
    """
    han = utc_bay_gio() - timedelta(days=SO_NGAY_TU_XOA)
    da_xoa: list[str] = []
    with session_scope() as s:
        tat_ca = s.execute(
            select(User).where(User.role == "phong", User.active.is_(True))
        ).scalars().all()
        for u in tat_ca:
            # Nếu chưa đăng nhập thì tính từ lúc tạo tài khoản
            moc_thoi_gian = u.last_login or u.created_at
            if moc_thoi_gian and moc_thoi_gian < han:
                da_xoa.append(u.username)
                s.delete(u)
        if da_xoa:
            s.add(AuditLog(
                username="hệ thống",
                action="tu_xoa_tp_khong_login",
                detail=f"{len(da_xoa)} tài khoản: {', '.join(da_xoa)}",
            ))
    return da_xoa


def lay_user(username: str) -> dict | None:
    """Thông tin một tài khoản để điền sẵn vào hộp thoại Sửa."""
    df = danh_sach_user()
    if df.empty:
        return None
    r = df[df.username == norm_text(username).lower()]
    if r.empty:
        return None
    r = r.iloc[0]
    try:
        pham_vi = json.loads(r.scope) if r.scope else []
    except (TypeError, ValueError):
        pham_vi = []
    return {"username": r.username, "ho_ten": r.ho_ten or "", "role": r.role, "pham_vi": pham_vi,
            "ma_nv": r.ma_nv or "", "email": r.email or "", "active": bool(r.active),
            "dang_khoa": r.trang_thai == "Đang khoá", "trang_thai": r.trang_thai, "lan_cuoi": r.lan_cuoi}


def sua_user(username: str, d: dict, nguoi_thuc_hien: str) -> tuple[bool, str]:
    """Sửa tài khoản từ hộp thoại. Không cho tự hạ quyền / tự ngừng dùng tài khoản đang đăng nhập,
    và luôn phải còn ít nhất một Quản trị đang dùng."""
    username = norm_text(username).lower()
    role = d.get("role") or ""
    if role not in dict(ROLES):
        return False, "Vai trò không hợp lệ."
    ma_phong = {p["code"] for p in phong_order()}
    pham_vi = [x for x in (d.get("pham_vi") or []) if x in ma_phong]
    if role in ROLE_CO_PHONG and not pham_vi:
        return False, f"{ROLE_TEN[role]} bắt buộc chọn phòng phụ trách."
    if role not in ROLE_CO_PHONG:
        pham_vi = []
    active = d.get("trang_thai", "Đang dùng") != "Ngừng dùng"
    email = norm_text(d.get("email"))
    if email and ("@" not in email or " " in email):
        return False, "Email không đúng định dạng."
    ban_than = username == norm_text(nguoi_thuc_hien).lower()
    with session_scope() as s:
        row = s.execute(select(User).where(User.username == username)).scalars().first()
        if row is None:
            return False, f"Không tìm thấy tài khoản “{username}”."
        if ban_than and (role != row.role or not active):
            return False, "Không tự đổi vai trò hoặc ngừng dùng tài khoản đang đăng nhập."
        if row.role == "admin" and row.active and (role != "admin" or not active):
            con = s.query(User).filter(User.role == "admin", User.active.is_(True)).count()
            if con <= 1:
                return False, "Phải còn ít nhất một tài khoản Quản trị đang dùng."
        truoc = (row.role, row.scope, row.active)
        row.ho_ten = norm_text(d.get("ho_ten")) or username
        row.email = email or None
        row.ma_nv = ma_nv_nhu_nhap(d.get("ma_nv")) or None
        row.role = role
        row.scope = json.dumps(pham_vi, ensure_ascii=False) if pham_vi else None
        row.active = active
        if d.get("mo_khoa"):
            row.locked_until = None
            row.failed_logins = 0
        doi = []
        if truoc[0] != row.role:
            doi.append(f"vai trò {ROLE_TEN.get(truoc[0], truoc[0])} → {ROLE_TEN[role]}")
        if truoc[1] != row.scope:
            doi.append("phòng phụ trách")
        if truoc[2] != row.active:
            doi.append("đang dùng" if active else "ngừng dùng")
        s.add(AuditLog(username=nguoi_thuc_hien, action="sua_tai_khoan",
                       detail=f"{username}: {', '.join(doi) or 'thông tin'}"))
    return True, f"Đã lưu tài khoản “{username}”."


def dat_lai_mat_khau(username: str, nguoi_thuc_hien: str) -> str:
    import secrets
    # mật khẩu tạm ngẫu nhiên (trước là Ftel@ + ngày tháng - đoán được)
    mk = "Ftel@" + "".join(secrets.choice("abcdefghjkmnpqrstuvwxyz23456789") for _ in range(6))
    with session_scope() as s:
        row = s.execute(select(User).where(User.username == username)).scalars().first()
        if row is None:
            return ""
        row.password_hash = ph.hash(mk)
        row.session_version = (row.session_version or 0) + 1  # buộc đăng nhập lại mọi máy
        row.failed_logins = 0
        row.locked_until = None
        s.add(AuditLog(username=nguoi_thuc_hien, action="dat_lai_mat_khau", detail=username))
    return mk


# ------------------------------------------------------- danh mục nhân sự
def danh_sach_staff() -> pd.DataFrame:
    df = pd.read_sql_query(text("""SELECT s.id, s.acc, s.ma_nv, s.phong_code, p.ten AS phong,
                                    s.hieu_luc_tu, s.hieu_luc_den, s.ghi_chu, s.ten_hien_thi
                             FROM staff_map s LEFT JOIN dim_phong p ON p.code = s.phong_code
                             ORDER BY p.thu_tu, s.acc"""), engine)
    # Giữ nguyên mã NV dạng chuỗi (kể cả số 0 ở đầu) trước khi astype(object).
    if "ma_nv" in df.columns:
        df["ma_nv"] = df["ma_nv"].apply(lambda v: str(v).split(".")[0] if pd.notna(v) and v != "" else "")
    for c in ("hieu_luc_tu", "hieu_luc_den", "ghi_chu", "phong", "ten_hien_thi"):
        if c in df.columns:
            df[c] = df[c].astype(object).where(df[c].notna(), "")
    return df


def luu_staff(rows: list[dict], nguoi_thuc_hien: str) -> tuple[int, list[str]]:
    ten2ma = {p["ten"]: p["code"] for p in phong_order()}
    loi: list[str] = []
    n = 0
    with session_scope() as s:
        for r in rows or []:
            acc = norm_text(r.get("acc"))
            if not acc:
                continue
            code = ten2ma.get(norm_text(r.get("phong")))
            if not code:
                loi.append(f"{acc}: chưa chọn phòng hợp lệ")
                continue
            row = (s.get(StaffMap, int(r["id"])) if str(r.get("id") or "").isdigit() else None)
            if row is None:
                row = StaffMap(acc=acc, acc_norm=norm_acc(acc))
                s.add(row)
            row.acc, row.acc_norm = acc, norm_acc(acc)
            row.ma_nv = ma_nv_nhu_nhap(r.get("ma_nv")) or None
            row.phong_code = code
            row.hieu_luc_tu = parse_date(r.get("hieu_luc_tu"))
            row.hieu_luc_den = parse_date(r.get("hieu_luc_den"))
            row.ghi_chu = norm_text(r.get("ghi_chu")) or None
            row.nguon = "giao diện"
            n += 1
        s.add(AuditLog(username=nguoi_thuc_hien, action="luu_danh_muc_nv", detail=f"{n} dòng"))
    return n, loi


def lay_staff(id_: int) -> dict | None:
    with session_scope() as s:
        r = s.get(StaffMap, int(id_))
        if r is None:
            return None
        return {"id": r.id, "acc": r.acc, "phong_code": r.phong_code, "ma_nv": r.ma_nv or "",
                "hieu_luc_tu": r.hieu_luc_tu.isoformat() if r.hieu_luc_tu else None,
                "hieu_luc_den": r.hieu_luc_den.isoformat() if r.hieu_luc_den else None,
                "ghi_chu": r.ghi_chu or "", "da_nghi": "nghỉ" in (r.ghi_chu or "").lower(),
                "tinh_trang": ("nghi" if "nghỉ" in (r.ghi_chu or "").lower() else
                               "nhap" if la_acc_tam(r.ghi_chu) else "lam"),
                "ten_hien_thi": r.ten_hien_thi or ""}


def _ghi_chu_tinh_trang(ghi_chu: str, tinh_trang: str) -> str | None:
    """Tình trạng lưu trong ghi chú, như import danh mục: "Nghỉ" (đã nghỉ) hoặc "Acc tạm" (chỉ nhập liệu, không
    tính vào nhân sự) - giữ phần ghi chú khác."""
    phan = [x.strip() for x in (ghi_chu or "").split("·") if x.strip()]
    nghi = [x for x in phan if "nghỉ" in x.lower()]
    tam = [x for x in phan if la_acc_tam(x) and "nghỉ" not in x.lower()]
    khac = [x for x in phan if x not in nghi and x not in tam]
    if tinh_trang == "nghi":
        khac = (nghi[:1] or [f"Nghỉ ({gio_viet_nam():%d/%m/%Y})"]) + khac
    elif tinh_trang == "nhap":
        khac = (tam[:1] or ["Acc tạm"]) + khac
    return " · ".join(khac) or None


def luu_mot_staff(id_: int | None, d: dict, nguoi_thuc_hien: str) -> tuple[bool, str, bool]:
    """Thêm (id_ None) hoặc sửa một dòng danh mục từ hộp thoại.

    Trả (thành công, thông báo, cần tính lại gán phòng). Chặn khai trùng: cùng acc đã có dòng khác mà
    khoảng hiệu lực chồng nhau - số sẽ không biết về phòng nào.
    """
    acc = norm_text(d.get("acc"))
    code = d.get("phong_code")
    if not acc or " " in acc:
        return False, "Acc inside bắt buộc và không chứa dấu cách.", False
    if code not in {p["code"] for p in phong_order()}:
        return False, "Chưa chọn phòng hợp lệ.", False
    tu, den = parse_date(d.get("hieu_luc_tu")), parse_date(d.get("hieu_luc_den"))
    if tu and den and tu > den:
        return False, "Ngày “Hiệu lực từ” phải trước ngày “Hiệu lực đến”.", False
    ten = {p["code"]: p["ten"] for p in phong_order()}
    with session_scope() as s:
        khac = [r for r in s.execute(select(StaffMap).where(StaffMap.acc_norm == norm_acc(acc))).scalars()
                if r.id != id_]
        for r in khac:
            if (tu or date.min) <= (r.hieu_luc_den or date.max) and (r.hieu_luc_tu or date.min) <= (den or date.max):
                return False, (f"{r.acc} đã có trong danh mục ở {ten.get(r.phong_code, r.phong_code)} cùng "
                               "thời gian hiệu lực. Sửa dòng đó, hoặc ghi ngày hiệu lực để tách hai giai đoạn "
                               "(vd chuyển phòng giữa tháng)."), False
        row = s.get(StaffMap, int(id_)) if id_ else None
        if id_ and row is None:
            return False, "Dòng này không còn trong danh mục (có thể vừa bị xoá).", False
        moi = row is None
        if moi:
            row = StaffMap(acc=acc, acc_norm=norm_acc(acc))
            s.add(row)
        doi_gan = moi or (row.acc_norm, row.phong_code, row.hieu_luc_tu, row.hieu_luc_den) !=             (norm_acc(acc), code, tu, den)
        cu = ten.get(row.phong_code, row.phong_code) if not moi else ""
        row.acc, row.acc_norm, row.phong_code = acc, norm_acc(acc), code
        row.ma_nv = ma_nv_nhu_nhap(d.get("ma_nv")) or None
        row.hieu_luc_tu, row.hieu_luc_den = tu, den
        row.ghi_chu = _ghi_chu_tinh_trang(norm_text(d.get("ghi_chu")),
                                          d.get("tinh_trang") or ("nghi" if d.get("da_nghi") else "lam"))
        row.ten_hien_thi = norm_text(d.get("ten_hien_thi")) or None
        row.nguon = "giao diện"
        chi_tiet = acc + (f": {cu} → {ten[code]}" if not moi and cu != ten[code] else f" ({ten[code]})")
        s.add(AuditLog(username=nguoi_thuc_hien, action="them_danh_muc_nv" if moi else "sua_danh_muc_nv",
                       detail=chi_tiet))
    return True, (f"Đã thêm {acc} vào {ten[code]}." if moi else f"Đã lưu {acc} ({ten[code]})."), doi_gan


def xoa_staff(ids: list[int], nguoi_thuc_hien: str) -> int:
    if not ids:
        return 0
    with session_scope() as s:
        s.execute(delete(StaffMap).where(StaffMap.id.in_(ids)))
        s.add(AuditLog(username=nguoi_thuc_hien, action="xoa_danh_muc_nv", detail=str(ids)))
    return len(ids)


# ------------------------------------------------------- lịch sử nạp dữ liệu
def lich_su_nap(limit: int = 50) -> pd.DataFrame:
    df = pd.read_sql_query(text("""SELECT id, dataset, file_name, thang, rows_total, rows_valid,
                                    rows_invalid, rows_new, rows_updated, rows_duplicate,
                                    uploaded_by, uploaded_at, note
                             FROM upload_batch ORDER BY id DESC LIMIT :n"""),
                     engine, params={"n": limit})
    if df.empty:
        return df
    df["thoi_diem"] = [chu_gio_vn(v, "%H:%M %d/%m/%Y") for v in df["uploaded_at"]]
    df["thoi_diem_sx"] = [chu_gio_vn(v, "%Y-%m-%d %H:%M") for v in df["uploaded_at"]]
    df["con_lai"] = [_dem_dong_batch(int(i), d) for i, d in zip(df.id, df.dataset)]
    return df


def _dem_dong_batch(batch_id: int, dataset: str) -> int:
    bang = {"internet": "fact_internet", "fptplay": "fact_fptplay", "camera": "fact_camera",
            "nhan_su": "hr_monthly"}.get(dataset)
    if not bang:
        return 0
    df = pd.read_sql_query(text(f"SELECT COUNT(*) n FROM {bang} WHERE batch_id = :b"),
                     engine, params={"b": batch_id})
    return int(df.iloc[0, 0])


@ghi("so_lieu")
def go_bo_lan_nap(batch_id: int, nguoi_thuc_hien: str, loai_cho_phep: set[str] | None = None,
                  chi_cua_minh: bool = False) -> dict:
    """Xoá các dòng dữ liệu mà lần nạp này ghi vào (và chưa bị lần nạp sau ghi đè).

    `loai_cho_phep` / `chi_cua_minh`: giới hạn theo quyền - Trưởng phòng chỉ gỡ được file bán hàng
    do chính mình nạp, không đụng tới file NSLĐ hay lần nạp của người khác.
    """
    with session_scope() as s:
        batch = s.get(UploadBatch, batch_id)
        if batch is None:
            return {"ok": False, "msg": "Không tìm thấy lần nạp."}
        if loai_cho_phep is not None and batch.dataset not in loai_cho_phep:
            return {"ok": False, "msg": "Tài khoản này không có quyền gỡ loại dữ liệu đó."}
        if chi_cua_minh and (batch.uploaded_by or "") != nguoi_thuc_hien:
            return {"ok": False, "msg": "Chỉ gỡ được lần nạp do chính mình thực hiện."}
        n = 0
        model = FACTS.get(batch.dataset)
        if model is not None:
            n = s.query(model).filter(model.batch_id == batch_id).delete(synchronize_session=False)
        elif batch.dataset == "nhan_su":
            n = s.query(HrMonthly).filter(HrMonthly.batch_id == batch_id).delete(
                synchronize_session=False)
        else:
            return {"ok": False, "msg": "Loại dữ liệu này không gỡ tự động được."}
        batch.note = ((batch.note or "") + f" | Đã gỡ {n} dòng lúc "
                      f"{gio_viet_nam():%H:%M %d/%m/%Y} bởi {nguoi_thuc_hien}").strip(" |")
        s.add(AuditLog(username=nguoi_thuc_hien, action="go_bo_lan_nap",
                       detail=f"batch {batch_id} ({batch.dataset}): {n} dòng"))
    return {"ok": True, "so_dong": n, "dataset": batch.dataset}


# ------------------------------------------------------- chất lượng dữ liệu
def _sql_df(sql: str, params: dict | None = None) -> pd.DataFrame:
    return pd.read_sql_query(text(sql), engine, params=params or {})


def _khoang(thang: str) -> dict:
    """Điều kiện theo tháng viết bằng khoảng ngày - chạy được cả SQLite lẫn PostgreSQL
    và tận dụng được chỉ mục trên cột ngày."""
    from app.metrics import month_range
    tu, den, _ = month_range(thang)
    return {"tu": tu.isoformat(), "den": den.isoformat()}


BANG_SO = [("Internet", "fact_internet"), ("Truyền hình", "fact_fptplay"), ("Camera", "fact_camera")]
LOAI_KINH_DOANH = ("IBB", "DIABAN")


def do_moi_du_lieu() -> list[dict]:
    """Ngày có số mới nhất của từng loại file - lệch nhau nghĩa là quên nạp một file."""
    out = []
    for ten, bang in BANG_SO:
        v = _sql_df(f"SELECT MAX(ngay_online) AS d FROM {bang}").iloc[0, 0]
        out.append({"loai": ten, "ngay": str(v)[:10] if v is not None and str(v) != "None" else None})
    return out


def chua_gan_phong(thang: str) -> pd.DataFrame:
    """Hợp đồng online trong tháng chưa về phòng nào - cả Internet, Truyền hình, Camera."""
    phan = []
    for ten, bang in BANG_SO:
        phan.append(f"""SELECT '{ten}' AS loai, acc_nhan_vien AS acc, ma_nhan_vien AS ma_nv,
                               phong_he_thong, cn_ban, COUNT(*) AS so_hd,
                               MIN(ngay_online) AS tu_ngay, MAX(ngay_online) AS den_ngay
                        FROM {bang}
                        WHERE phong_code = 'CHUA_GAN' AND ngay_online >= :tu AND ngay_online <= :den
                        GROUP BY acc_nhan_vien, ma_nhan_vien, phong_he_thong, cn_ban""")
    df = _sql_df(" UNION ALL ".join(phan), _khoang(thang))
    return df.sort_values("so_hd", ascending=False).reset_index(drop=True) if len(df) else df


def acc_la(thang: str) -> pd.DataFrame:
    """Acc có số trong tháng nhưng không có trong danh mục nhân sự (bỏ hợp đồng ECOM).

    Phần lớn là nhân viên kỹ thuật / CUS: app vẫn gán đúng phòng KT/CUS theo quy tắc nên KHÔNG
    phải lỗi. Cột "Đang tính cho" để soát nhanh có nhân viên kinh doanh nào lọt vào đây không.
    """
    df = _sql_df("""SELECT f.acc_nhan_vien AS acc, f.phong_code, COUNT(*) AS so_hd,
                           MAX(f.ngay_online) AS gan_nhat,
                           MAX(CASE WHEN e.ma_nv IS NULL THEN 0 ELSE 1 END) AS co_nsld
                    FROM fact_internet f
                    LEFT JOIN staff_map s ON s.acc_norm = f.acc_norm
                    LEFT JOIN dim_employee e ON e.acc_norm = f.acc_norm
                    WHERE f.ngay_online >= :tu AND f.ngay_online <= :den
                      AND s.id IS NULL AND f.la_ecom = FALSE
                    GROUP BY f.acc_nhan_vien, f.phong_code""", _khoang(thang))
    if df.empty:
        return pd.DataFrame(columns=["acc", "dang_tinh_cho", "so_hd", "gan_nhat", "co_nsld", "nhom"])
    ten = {p["code"]: p for p in phong_order()}
    df["dang_tinh_cho"] = [ten.get(c, {}).get("ten", c) for c in df.phong_code]
    loai = [ten.get(c, {}).get("loai") for c in df.phong_code]
    df["nhom"] = ["Cần xem" if (lo in LOAI_KINH_DOANH or c == "CHUA_GAN" or nsld) else "Kỹ thuật / CUS"
                  for lo, c, nsld in zip(loai, df.phong_code, df.co_nsld)]
    df["co_nsld"] = df.co_nsld.map({1: "Có", 0: ""})
    return (df.sort_values(["nhom", "so_hd"], ascending=[True, False])
            [["acc", "dang_tinh_cho", "so_hd", "gan_nhat", "co_nsld", "nhom"]].reset_index(drop=True))


def nv_thieu_ho_so(thang: str) -> pd.DataFrame:
    """Nhân sự phòng kinh doanh (đang làm) không có trong file NSLĐ gần nhất của kỳ."""
    df = _sql_df("""SELECT s.acc, s.acc_norm, s.ma_nv, p.ten AS phong, p.chi_nhanh, p.thu_tu
                    FROM staff_map s JOIN dim_phong p ON p.code = s.phong_code
                    WHERE p.loai IN ('IBB', 'DIABAN') AND COALESCE(s.ghi_chu, '') NOT LIKE '%Nghỉ%'
                      AND (s.hieu_luc_den IS NULL OR s.hieu_luc_den >= CURRENT_DATE)""")
    t = _sql_df("SELECT MAX(thang) AS t FROM hr_monthly WHERE thang <= :t", {"t": thang}).iloc[0, 0]
    if df.empty:
        return pd.DataFrame(columns=["acc", "phong", "ma_nv", "chi_nhanh"])
    co = set()
    if t:
        hr = _sql_df("SELECT acc, ma_nv FROM hr_monthly WHERE thang = :t", {"t": t})
        co = set(hr.acc.fillna("").str.strip().str.lower())
        ma = set(hr.ma_nv.fillna("").astype(str).str.lstrip("0"))
        df = df[~(df.acc_norm.isin(co) | df.ma_nv.fillna("").astype(str).str.lstrip("0").isin(ma - {""}))]
    else:
        df = df.copy()
    df["thang_nsld"] = t
    return df.sort_values(["thu_tu", "acc"])[["acc", "phong", "ma_nv", "chi_nhanh", "thang_nsld"]]


def ngay_thieu_du_lieu(thang: str) -> list[str]:
    """Ngày nằm trong khoảng đã có dữ liệu nhưng không có hợp đồng nào (nghi thiếu file)."""
    df = _sql_df("""SELECT DISTINCT ngay_online AS d FROM fact_internet
                    WHERE ngay_online >= :tu AND ngay_online <= :den ORDER BY d""",
                 _khoang(thang))
    co = [str(x)[:10] for x in df["d"].dropna()]
    if not co:
        return []
    d0, d1 = date.fromisoformat(co[0]), date.fromisoformat(co[-1])
    tat_ca = [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]
    return [d for d in tat_ca if d not in set(co)]


def hd_bat_thuong(thang: str) -> pd.DataFrame:
    """Hợp đồng online trong tháng nhưng tình trạng hiện tại không còn "Bình thường"
    (ngưng vì thanh toán, chấm dứt, đi vắng) - vẫn đang được tính vào số online."""
    df = _sql_df("""SELECT hop_dong, acc_nhan_vien AS acc, phong_code, tinh_trang, ngay_online, ngay_huy
                    FROM fact_internet
                    WHERE ngay_online >= :tu AND ngay_online <= :den
                      AND (ngay_huy IS NOT NULL OR COALESCE(tinh_trang, '') <> 'Bình thường')
                    ORDER BY ngay_online DESC""", _khoang(thang))
    ten = {p["code"]: p["ten"] for p in phong_order()}
    df["phong"] = [ten.get(c, c) for c in df.phong_code]
    return df.drop(columns="phong_code")


def acc_trung_danh_muc() -> pd.DataFrame:
    """Danh mục có vấn đề làm số về sai phòng:
    - một acc có nhiều dòng mà không phân biệt được ngày hiệu lực;
    - acc đang khai khác phòng đã chốt trong config/staff_overrides.yml (VD TIN.MinhLH1 -> IBB3).
    """
    from app.config import load_yaml
    df = _sql_df("""SELECT s.acc, s.acc_norm, s.phong_code, p.ten AS phong, s.hieu_luc_tu, s.hieu_luc_den
                    FROM staff_map s LEFT JOIN dim_phong p ON p.code = s.phong_code""")
    cot = ["acc", "van_de", "dang_khai"]
    if df.empty:
        return pd.DataFrame(columns=cot)
    out = []
    for a, x in df.groupby("acc_norm"):
        if len(x) > 1 and (x.hieu_luc_den.isna().sum() > 1 or x.hieu_luc_tu.isna().all()):
            out.append({"acc": x.acc.iloc[0], "van_de": f"Khai {len(x)} dòng, không rõ ngày hiệu lực",
                        "dang_khai": ", ".join(map(str, x.phong))})
    try:
        chot = load_yaml("staff_overrides.yml").get("overrides") or []
    except FileNotFoundError:
        chot = []
    ten = {p["code"]: p["ten"] for p in phong_order()}
    for o in chot:
        x = df[df.acc_norm == norm_acc(o.get("acc"))]
        if len(x) and not (x.phong_code == o.get("phong")).any():
            out.append({"acc": x.acc.iloc[0],
                        "van_de": f"Đã chốt tính cho {ten.get(o.get('phong'), o.get('phong'))}"
                                  + (f" ({o['ghi_chu']})" if o.get("ghi_chu") else ""),
                        "dang_khai": ", ".join(map(str, x.phong))})
    return pd.DataFrame(out, columns=cot)


def ton_dong_lau(so_ngay: int = 7) -> pd.DataFrame:
    """Hợp đồng đã tạo nhưng chưa online quá N ngày - điểm nghẽn triển khai."""
    # cùng cách tính với trang Phân tích: tuổi hợp đồng tính đến ngày dữ liệu mới nhất
    # (không tính đến hôm nay - chưa nạp file hôm nay thì mọi hợp đồng không bị "già" thêm)
    from app.phan_tich import hop_dong_ton
    ton = hop_dong_ton()
    if ton.empty:
        return pd.DataFrame(columns=["phong", "so_hd", "tuoi_tb"])
    lau = ton[ton.so_ngay_cho >= so_ngay]
    ten = {p["code"]: p["ten"] for p in phong_order()}
    g = lau.groupby("phong_code").so_ngay_cho.agg(so_hd="count", tuoi_tb="mean").reset_index()
    g["phong"] = [ten.get(c, c) for c in g.phong_code]
    g["tuoi_tb"] = g.tuoi_tb.round(1)
    return g[["phong", "so_hd", "tuoi_tb"]].sort_values("so_hd", ascending=False)


def tom_tat_chat_luong(thang: str) -> dict:
    return {
        "chua_gan": int(chua_gan_phong(thang).so_hd.sum()) if not chua_gan_phong(thang).empty else 0,
        "acc_la": len(acc_la(thang)),
        "thieu_ho_so": len(nv_thieu_ho_so(thang)),
        "ngay_thieu": ngay_thieu_du_lieu(thang),
        "hd_bat_thuong": len(hd_bat_thuong(thang)),
    }
