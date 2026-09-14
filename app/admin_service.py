"""Nghiệp vụ quản trị: tài khoản, danh mục nhân sự, lịch sử nạp, chất lượng dữ liệu."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import pandas as pd
from argon2 import PasswordHasher
from sqlalchemy import delete, select, text

from app.db import engine, session_scope
from app.ingest.normalize import norm_acc, norm_manv, norm_text, parse_date
from app.models import (AuditLog, FactCamera, FactFptPlay, FactInternet, HrMonthly, StaffMap,
                        UploadBatch, User)
from app.org import phong_order
from app.thoi_gian import chu_gio_vn, gio_viet_nam, utc_bay_gio

ph = PasswordHasher()
ROLES = [("admin", "Quản trị (BGD)"), ("operator", "Nhập liệu"), ("phong", "Trưởng phòng")]
ROLE_TEN = {**dict(ROLES), "bay": "Trưởng phòng", "nhanvien": "Nhân viên"}
TEN_ROLE = {v: k for k, v in ROLES}
FACTS = {"internet": FactInternet, "fptplay": FactFptPlay, "camera": FactCamera}


# ------------------------------------------------------------------ tài khoản
def danh_sach_user() -> pd.DataFrame:
    df = pd.read_sql(text("""SELECT id, username, ho_ten, email, role, scope, ma_nv, active,
                                    last_login, locked_until
                             FROM users ORDER BY role, username"""), engine)
    if df.empty:
        return df
    df["vai_tro"] = df["role"].map(ROLE_TEN).fillna(df["role"])
    df["pham_vi"] = [_scope_text(s) if r in ("phong", "bay") else "Toàn chi nhánh"
                     for s, r in zip(df["scope"], df["role"])]
    df["trang_thai"] = df.apply(
        lambda r: "Đang khoá" if (r.locked_until and str(r.locked_until) > str(utc_bay_gio()))
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
            row.ma_nv = norm_manv(r.get("ma_nv")) or None
            pv = [x.strip() for x in norm_text(r.get("pham_vi")).split(",") if x.strip()]
            pv = [ten2ma.get(x, x) for x in pv if x.lower() != "toàn chi nhánh"]
            if row.role != "phong":
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
    if role == "phong" and not pham_vi:
        return False, "Trưởng phòng bắt buộc chọn phòng phụ trách."
    if role != "phong":
        pham_vi = []
    with session_scope() as s:
        if s.execute(select(User).where(User.username == username)).scalars().first():
            return False, f"Tài khoản “{username}” đã tồn tại."
        s.add(User(username=username, ho_ten=norm_text(d.get("ho_ten")) or username,
                   email=norm_text(d.get("email")) or None, role=role,
                   ma_nv=norm_manv(d.get("ma_nv")) or None,
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


def dat_lai_mat_khau(username: str, nguoi_thuc_hien: str) -> str:
    mk = "Ftel@" + datetime.now().strftime("%d%m")
    with session_scope() as s:
        row = s.execute(select(User).where(User.username == username)).scalars().first()
        if row is None:
            return ""
        row.password_hash = ph.hash(mk)
        row.failed_logins = 0
        row.locked_until = None
        s.add(AuditLog(username=nguoi_thuc_hien, action="dat_lai_mat_khau", detail=username))
    return mk


# ------------------------------------------------------- danh mục nhân sự
def danh_sach_staff() -> pd.DataFrame:
    df = pd.read_sql(text("""SELECT s.id, s.acc, s.ma_nv, s.phong_code, p.ten AS phong,
                                    s.hieu_luc_tu, s.hieu_luc_den, s.ghi_chu
                             FROM staff_map s LEFT JOIN dim_phong p ON p.code = s.phong_code
                             ORDER BY p.thu_tu, s.acc"""), engine)
    for c in ("hieu_luc_tu", "hieu_luc_den", "ma_nv", "ghi_chu", "phong"):
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
            row.ma_nv = norm_manv(r.get("ma_nv")) or None
            row.phong_code = code
            row.hieu_luc_tu = parse_date(r.get("hieu_luc_tu"))
            row.hieu_luc_den = parse_date(r.get("hieu_luc_den"))
            row.ghi_chu = norm_text(r.get("ghi_chu")) or None
            row.nguon = "giao diện"
            n += 1
        s.add(AuditLog(username=nguoi_thuc_hien, action="luu_danh_muc_nv", detail=f"{n} dòng"))
    return n, loi


def xoa_staff(ids: list[int], nguoi_thuc_hien: str) -> int:
    if not ids:
        return 0
    with session_scope() as s:
        s.execute(delete(StaffMap).where(StaffMap.id.in_(ids)))
        s.add(AuditLog(username=nguoi_thuc_hien, action="xoa_danh_muc_nv", detail=str(ids)))
    return len(ids)


# ------------------------------------------------------- lịch sử nạp dữ liệu
def lich_su_nap(limit: int = 50) -> pd.DataFrame:
    df = pd.read_sql(text("""SELECT id, dataset, file_name, thang, rows_total, rows_valid,
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
    df = pd.read_sql(text(f"SELECT COUNT(*) n FROM {bang} WHERE batch_id = :b"),
                     engine, params={"b": batch_id})
    return int(df.iloc[0, 0])


def go_bo_lan_nap(batch_id: int, nguoi_thuc_hien: str) -> dict:
    """Xoá các dòng dữ liệu mà lần nạp này ghi vào (và chưa bị lần nạp sau ghi đè)."""
    with session_scope() as s:
        batch = s.get(UploadBatch, batch_id)
        if batch is None:
            return {"ok": False, "msg": "Không tìm thấy lần nạp."}
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
    return pd.read_sql(text(sql), engine, params=params or {})


def _khoang(thang: str) -> dict:
    """Điều kiện theo tháng viết bằng khoảng ngày - chạy được cả SQLite lẫn PostgreSQL
    và tận dụng được chỉ mục trên cột ngày."""
    from app.metrics import month_range
    tu, den, _ = month_range(thang)
    return {"tu": tu.isoformat(), "den": den.isoformat()}


def chua_gan_phong(thang: str) -> pd.DataFrame:
    return _sql_df("""SELECT acc_nhan_vien AS acc, ma_nhan_vien AS ma_nv, phong_he_thong,
                             cn_ban, COUNT(*) AS so_hd, MIN(ngay_online) AS tu_ngay,
                             MAX(ngay_online) AS den_ngay
                      FROM fact_internet
                      WHERE phong_code = 'CHUA_GAN'
                        AND ngay_online >= :tu AND ngay_online <= :den
                      GROUP BY acc_nhan_vien, ma_nhan_vien, phong_he_thong, cn_ban
                      ORDER BY so_hd DESC""", _khoang(thang))


def acc_la(thang: str) -> pd.DataFrame:
    """Acc có phát sinh số nhưng không có trong danh mục NV và cũng không có trong hồ sơ NSLĐ."""
    return _sql_df("""SELECT f.acc_nhan_vien AS acc, COUNT(*) AS so_hd,
                             MAX(f.ngay_online) AS gan_nhat
                      FROM fact_internet f
                      LEFT JOIN staff_map s ON s.acc_norm = f.acc_norm
                      LEFT JOIN dim_employee e ON e.acc_norm = f.acc_norm
                      WHERE f.ngay_online >= :tu AND f.ngay_online <= :den
                        AND s.id IS NULL AND e.ma_nv IS NULL AND f.la_ecom = FALSE
                      GROUP BY f.acc_nhan_vien ORDER BY so_hd DESC""", _khoang(thang))


def nv_thieu_ho_so(thang: str) -> pd.DataFrame:
    """Có trong danh mục nhưng chưa có hồ sơ NSLĐ (thường là nhân sự QNM chưa nạp)."""
    return _sql_df("""SELECT s.acc, p.ten AS phong, s.ma_nv
                      FROM staff_map s
                      LEFT JOIN dim_phong p ON p.code = s.phong_code
                      LEFT JOIN dim_employee e ON e.acc_norm = s.acc_norm
                      WHERE e.ma_nv IS NULL ORDER BY p.thu_tu, s.acc""")


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
    """Hợp đồng đã hủy hoặc ngưng nhưng vẫn nằm trong số liệu tháng."""
    return _sql_df("""SELECT hop_dong, acc_nhan_vien AS acc, tinh_trang, ngay_online, ngay_huy
                      FROM fact_internet
                      WHERE ngay_online >= :tu AND ngay_online <= :den
                        AND (ngay_huy IS NOT NULL OR tinh_trang <> 'Bình thường')
                      ORDER BY ngay_online DESC""", _khoang(thang))


def ton_dong_lau(so_ngay: int = 7) -> pd.DataFrame:
    """Hợp đồng đã tạo nhưng chưa online quá N ngày - điểm nghẽn triển khai."""
    from app.metrics import dieu_kien_ton
    from app.sql_dialect import so_ngay_den_hom_nay
    tuoi = so_ngay_den_hom_nay("f.ngay_tao_hd")
    dk, p = dieu_kien_ton("f.")
    return _sql_df(f"""SELECT p.ten AS phong, COUNT(*) AS so_hd,
                              ROUND(CAST(AVG({tuoi}) AS NUMERIC), 1) AS tuoi_tb
                       FROM fact_internet f LEFT JOIN dim_phong p ON p.code = f.phong_code
                       WHERE {dk} AND {tuoi} >= :n
                       GROUP BY p.ten ORDER BY so_hd DESC""", {"n": so_ngay, **p})


def tom_tat_chat_luong(thang: str) -> dict:
    return {
        "chua_gan": int(chua_gan_phong(thang).so_hd.sum()) if not chua_gan_phong(thang).empty else 0,
        "acc_la": len(acc_la(thang)),
        "thieu_ho_so": len(nv_thieu_ho_so(thang)),
        "ngay_thieu": ngay_thieu_du_lieu(thang),
        "hd_bat_thuong": len(hd_bat_thuong(thang)),
    }
