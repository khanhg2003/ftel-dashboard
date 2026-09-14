"""Ghi dữ liệu đã kiểm tra vào database (thêm mới hoặc cập nhật theo khoá)."""
from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.config import rules_config
from app.db import engine
from app.ingest.loader import LoadResult
from app.ingest.normalize import norm_acc, norm_text
from app.models import (AuditLog, Employee, FactCamera, FactFptPlay, FactInternet,
                        HrMonthly, Phong, StaffMap, UploadBatch)
from app.org import assign_phong, load_staff_map, phong_by_name

FACT_MODELS = {"internet": FactInternet, "fptplay": FactFptPlay, "camera": FactCamera}
KEYS = {"internet": "hop_dong", "fptplay": "hop_dong", "camera": "row_hash"}
CHUNK = 800
LUU_TEN_KHACH_HANG = os.getenv("LUU_TEN_KHACH_HANG", "false").lower() == "true"


def file_hash(path: str | Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()[:32]


def _bo_dau(chu: str) -> str:
    import unicodedata
    chu = unicodedata.normalize("NFD", chu)
    return "".join(c for c in chu if not unicodedata.combining(c)).replace("đ", "d").replace("Đ", "D")


def thang_tu_ten_file(name: str, hom_nay: datetime | None = None) -> str | None:
    """Tháng ghi trong tên file: 'NSLĐ T8.2026' / 'Tháng 7.2026' / '2026-05' -> 'YYYY-MM'.

    Chỉ ghi tháng ('T5.xlsx', 'NSLĐ tháng 5') thì lấy năm hiện tại; tháng lớn hơn tháng hiện tại
    thì hiểu là năm trước (đầu năm nạp bù file tháng 12).
    """
    ten = _bo_dau(Path(name).stem).lower()
    m = re.search(r"(?:^|[^a-z])(?:t|thang)\s*0?(\d{1,2})\s*[.\-_/ ]\s*(\d{4})", ten)
    if m and 1 <= int(m.group(1)) <= 12:
        return f"{int(m.group(2)):04d}-{int(m.group(1)):02d}"
    m = re.search(r"(\d{4})[-_.](\d{1,2})(?!\d)", ten)
    if m and 1 <= int(m.group(2)) <= 12:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
    m = re.search(r"(?:^|[^a-z])(?:t|thang)\s*0?(\d{1,2})(?!\d)", ten)
    if m and 1 <= int(m.group(1)) <= 12:
        from app.thoi_gian import gio_viet_nam
        nay = hom_nay or gio_viet_nam()
        thang = int(m.group(1))
        nam = nay.year if thang <= nay.month else nay.year - 1
        return f"{nam:04d}-{thang:02d}"
    return None


def thang_nsld_tu_noi_dung(df: pd.DataFrame) -> tuple[str | None, float]:
    """Tháng của file NSLĐ suy ra từ chính dữ liệu, không cần tên file.

    Người có "Tháng NSLĐ" ghi số (1-12) và có Ngày tính lương: tháng của file = tháng vào làm + số
    tháng NSLĐ - 1 (đã đối chiếu khớp 100% với file thật). Trả về (tháng, tỷ lệ người đồng thuận).
    """
    from collections import Counter
    dem: Counter = Counter()
    if df is None or "tham_nien_bucket" not in df or "ngay_tinh_luong" not in df:
        return None, 0.0
    for b, vao in zip(df["tham_nien_bucket"], df["ngay_tinh_luong"]):
        k = str(b).strip()
        if not k.isdigit() or not (1 <= int(k) <= 12) or vao is None or pd.isna(vao):
            continue
        vao = pd.Timestamp(vao)
        chi_so = vao.year * 12 + vao.month - 1 + int(k) - 1
        dem[f"{chi_so // 12:04d}-{chi_so % 12 + 1:02d}"] += 1
    if not dem:
        return None, 0.0
    thang, n = dem.most_common(1)[0]
    return thang, n / sum(dem.values())


def _insert_stmt(table):
    return sqlite_insert(table) if engine.dialect.name == "sqlite" else pg_insert(table)


def _upsert(session, model, rows: list[dict], key: str) -> tuple[int, int]:
    """Trả về (số dòng thêm mới, số dòng cập nhật)."""
    if not rows:
        return 0, 0
    keys = [r[key] for r in rows]
    existing = set()
    for i in range(0, len(keys), 500):
        part = keys[i:i + 500]
        col = getattr(model, key)
        existing.update(x[0] for x in session.execute(select(col).where(col.in_(part))).all())
    new = sum(1 for k in keys if k not in existing)
    upd = len(keys) - new

    table = model.__table__
    cols = {c.name for c in table.columns}
    for i in range(0, len(rows), CHUNK):
        batch = [{k: v for k, v in r.items() if k in cols} for r in rows[i:i + CHUNK]]
        stmt = _insert_stmt(table).values(batch)
        upd_cols = {c: getattr(stmt.excluded, c) for c in batch[0] if c != key}
        upd_cols["updated_at"] = datetime.now()
        session.execute(stmt.on_conflict_do_update(index_elements=[key], set_=upd_cols))
    return new, upd


def _fact_rows(res: LoadResult, staff_map: dict[str, str], batch_id: int) -> list[dict]:
    rules = rules_config()
    goi_vvip = {norm_text(x).lower() for x in rules["vvip"]["goi_tinh_vvip"]}
    df = res.df.copy()
    rows: list[dict] = []
    for r in df.to_dict("records"):
        acc = r.get("acc_nhan_vien", "")
        code, la_ecom = assign_phong(acc, r.get("phong_he_thong"), r.get("cn_ban"),
                                     r.get("cn_quan_ly"), staff_map)
        r["phong_code"] = code
        r["la_ecom"] = la_ecom
        if not LUU_TEN_KHACH_HANG:
            # báo cáo không dùng tên khách -> không lưu, tránh mang dữ liệu cá nhân lên cloud
            r["ten_khach_hang"] = None
        r["acc_norm"] = norm_acc(acc)
        r["batch_id"] = batch_id
        if res.dataset == "fptplay":
            r["la_vvip"] = norm_text(r.get("goi_fpt_play")).lower() in goi_vvip
        if res.dataset == "camera":
            r["row_hash"] = r["_row_hash"]
        rows.append(r)
    return rows


def _bo_dong_camera_cu(session, rows: list[dict]) -> int:
    """Camera khoá theo mã băm cả dòng, nên khi một hợp đồng đổi thông tin (vừa online, đổi hình
    thức thanh toán...) file mới sinh ra dòng có mã băm khác. Nạp lại file 3 tháng mà không bỏ dòng
    cũ thì camera đó bị đếm hai lần. File mới là bản đầy đủ nhất của các hợp đồng có trong nó,
    nên xoá các dòng cũ của đúng những hợp đồng này rồi ghi lại."""
    moi = {r["row_hash"] for r in rows}
    hop_dong = sorted({r["hop_dong"] for r in rows})
    bo = 0
    for i in range(0, len(hop_dong), 500):
        cu = session.execute(select(FactCamera.row_hash).where(
            FactCamera.hop_dong.in_(hop_dong[i:i + 500]))).scalars().all()
        xoa = [h for h in cu if h not in moi]
        for j in range(0, len(xoa), 500):
            session.execute(delete(FactCamera).where(FactCamera.row_hash.in_(xoa[j:j + 500])))
        bo += len(xoa)
    return bo


def commit_result(session, res: LoadResult, *, nguon_file: str, hash_file: str,
                  user: str = "system", thang: str | None = None) -> dict:
    """Ghi 1 khối dữ liệu vào DB, trả về thống kê để hiển thị cho người dùng."""
    if not res.ok:
        return {"dataset": res.dataset, "bo_qua": True, "ly_do": "; ".join(res.canh_bao)}

    batch = UploadBatch(dataset=res.dataset, file_name=nguon_file, file_hash=hash_file,
                        thang=thang, rows_total=res.rows_total, rows_valid=res.rows_valid,
                        rows_invalid=res.rows_invalid, uploaded_by=user,
                        note="; ".join(res.canh_bao) or None)
    session.add(batch)
    session.flush()

    stats = {"dataset": res.dataset, "batch_id": batch.id, "hop_le": res.rows_valid,
             "loi": res.rows_invalid, "them_moi": 0, "cap_nhat": 0, "trung_trong_file": 0}

    if res.dataset in FACT_MODELS:
        staff_map = load_staff_map(session)
        rows = _fact_rows(res, staff_map, batch.id)
        key = KEYS[res.dataset]
        before = len(rows)
        seen, uniq = set(), []
        for r in rows:                      # bỏ dòng trùng ngay trong file
            if r[key] in seen:
                continue
            seen.add(r[key])
            uniq.append(r)
        stats["trung_trong_file"] = before - len(uniq)
        if res.dataset == "camera":
            stats["thay_the"] = _bo_dong_camera_cu(session, uniq)
        new, upd = _upsert(session, FACT_MODELS[res.dataset], uniq, key)
        stats.update(them_moi=new, cap_nhat=upd)

    elif res.dataset == "nhan_su":
        if not thang:
            raise ValueError("Cần chọn tháng cho file nhân sự.")
        new = upd = 0
        records = [r for r in res.df.to_dict("records") if r.get("ma_nv")]
        # đọc sẵn một lần cho cả file (Supabase ở xa, mỗi câu truy vấn mất vài chục ms)
        ds_ma = sorted({r["ma_nv"] for r in records})
        emps, hrs, moi_nhat = {}, {}, {}
        for i in range(0, len(ds_ma), 500):
            lo = ds_ma[i:i + 500]
            emps.update({e.ma_nv: e for e in session.execute(
                select(Employee).where(Employee.ma_nv.in_(lo))).scalars()})
            hrs.update({h.ma_nv: h for h in session.execute(
                select(HrMonthly).where(HrMonthly.thang == thang, HrMonthly.ma_nv.in_(lo))).scalars()})
            moi_nhat.update(dict(session.execute(
                select(HrMonthly.ma_nv, func.max(HrMonthly.thang)).where(HrMonthly.ma_nv.in_(lo))
                .group_by(HrMonthly.ma_nv)).all()))
        for r in records:
            ma_nv = r["ma_nv"]
            emp = emps.get(ma_nv)
            if emp is None:
                emp = emps[ma_nv] = Employee(ma_nv=ma_nv)
                session.add(emp)
            # nạp bù file tháng cũ thì không ghi đè hồ sơ mới hơn - chỉ bổ sung ngày vào làm
            thang_moi_nhat = moi_nhat.get(ma_nv)
            if not thang_moi_nhat or thang >= thang_moi_nhat:
                emp.ho_ten, emp.acc = r.get("ho_ten"), r.get("acc")
                emp.acc_norm = norm_acc(r.get("acc"))
                emp.vi_tri, emp.vi_tri_inside = r.get("vi_tri"), r.get("vi_tri_inside")
                emp.don_vi_ps, emp.phong_ps = r.get("don_vi_ps"), r.get("phong_ps")
                emp.khu_vuc = r.get("khu_vuc")
                emp.trang_thai, emp.ngay_nghi_viec = r.get("trang_thai"), r.get("ngay_nghi_viec")
            emp.ngay_tinh_luong = r.get("ngay_tinh_luong") or emp.ngay_tinh_luong

            hr = hrs.get(ma_nv)
            if hr is None:
                hr = hrs[ma_nv] = HrMonthly(ma_nv=ma_nv, thang=thang)
                session.add(hr)
                new += 1
            else:
                upd += 1
            for f in ("acc", "ho_ten", "vi_tri", "phong_ps", "tham_nien_bucket", "trang_thai",
                      "ngay_nghi_viec", "ngay_gian_doan", "dieu_kien", "diem_itn",
                      "diem_fpt_play", "diem_tong", "ket_luan", "tong_bao_lanh", "ghi_chu"):
                if f in r:
                    setattr(hr, f, r[f])
            hr.tham_nien_thang = _tham_nien_thang(r.get("tham_nien_bucket"))
            hr.nhom_tham_nien = _nhom_tham_nien(hr.tham_nien_thang)
            hr.batch_id = batch.id
        stats.update(them_moi=new, cap_nhat=upd)

    elif res.dataset == "danh_muc_nv":
        name2code = phong_by_name()
        session.execute(delete(StaffMap))
        n, bo_qua = 0, []
        for r in res.df.to_dict("records"):
            acc = norm_text(r.get("acc"))
            if not acc:
                continue
            code = name2code.get(norm_text(r.get("phong")).lower())
            if not code:
                bo_qua.append(norm_text(r.get("phong")))
                continue
            session.add(StaffMap(acc=acc, acc_norm=norm_acc(acc), ma_nv=r.get("ma_nv") or None,
                                 phong_code=code, ghi_chu=r.get("ghi_chu") or None,
                                 nguon=nguon_file))
            n += 1
        stats.update(them_moi=n)
        if bo_qua:
            stats["phong_chua_khai_bao"] = sorted(set(bo_qua))

    batch.rows_new = stats.get("them_moi", 0)
    batch.rows_updated = stats.get("cap_nhat", 0)
    batch.rows_duplicate = stats.get("trung_trong_file", 0)
    session.add(AuditLog(username=user, action=f"commit:{res.dataset}",
                         detail=f"{nguon_file} | {stats}"))
    return stats


def _tham_nien_thang(bucket) -> int | None:
    s = norm_text(bucket)
    if not s:
        return None
    if s.endswith("+"):
        return int(re.sub(r"[^0-9]", "", s) or 0)
    if "-" in s:
        return int(s.split("-")[0])
    try:
        return int(float(s))
    except ValueError:
        return None


def _nhom_tham_nien(thang: int | None) -> str | None:
    if thang is None:
        return None
    for g in rules_config()["tham_nien"]:
        if g["tu"] <= thang <= g["den"]:
            return g["code"]
    return None


def recompute_phong(session) -> int:
    """Chạy lại việc gán phòng cho toàn bộ dữ liệu (dùng sau khi sửa danh mục NV)."""
    staff_map = load_staff_map(session)
    total = 0
    for model in (FactInternet, FactFptPlay, FactCamera):
        for obj in session.execute(select(model)).scalars():
            code, la_ecom = assign_phong(obj.acc_nhan_vien, obj.phong_he_thong, obj.cn_ban,
                                         obj.cn_quan_ly, staff_map)
            if obj.phong_code != code or obj.la_ecom != la_ecom:
                obj.phong_code, obj.la_ecom = code, la_ecom
                total += 1
    return total
