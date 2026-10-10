"""Danh bạ liên hệ nội bộ cho Soạn email + tra cứu (chốt 10/10/2026; người dùng: admin + nhân viên KD IBB7).

Dữ liệu đến từ hai file Excel của công ty, MỖI THÁNG nạp lại:
- PNC (Đà Nẵng vào Nam, mới hơn) và TIN (Đà Nẵng ra Bắc) - khác tên cột, khác vị trí dòng tiêu đề, tên chi nhánh chỉ ghi
  ở dòng đầu mỗi nhóm (ô gộp), nên bộ đọc nhận tiêu đề theo TÊN CỘT chứ không theo vị trí (`_doc_sheet`).
- Người sale tự thêm (nguồn TAY) cho người không có trong file, ví dụ người CC trong mail mẫu.

Lưu theo từng nguồn (nạp lại file nào thì thay đúng dòng của nguồn đó); trùng người giữa các nguồn thì gộp lúc ĐỌC
(`tat_ca`): TAY > PNC > TIN, email lệch giữ làm "email khác" để sale tự chọn. Không đưa file vào git, không lưu file gốc.
"""
from __future__ import annotations

import io
import re

import pandas as pd
from sqlalchemy import delete, text

from app.bo_nho import ghi, nho
from app.db import engine, session_scope
from app.giong_noi import bo_dau
from app.models import AuditLog, DanhBa
from app.thoi_gian import chu_gio_vn, utc_bay_gio

NGUON_FILE = {"PNC": "PNC (Đà Nẵng vào Nam)", "TIN": "TIN (Đà Nẵng ra Bắc)"}
UU_TIEN = {"TAY": 0, "PNC": 1, "TIN": 2}          # trùng người: nguồn đứng trước thắng (PNC T10 mới hơn TIN T8)
NHOM = {"giam_doc": "Giám đốc", "pho_giam_doc": "Phó giám đốc", "truong_phong_kt": "TP kỹ thuật / đối tác",
        "ha_tang": "Hạ tầng", "doi_truong": "Đội trưởng", "ke_toan": "Kế toán", "dvkh": "DVKH",
        "hcns": "Hành chính nhân sự", "khac": "Khác"}
DV_UU_TIEN = ("da nang", "quang nam")              # chi nhánh của sale: luôn xếp lên đầu kết quả
GIOI_HAN = {"ho_ten": 120, "chuc_vu": 160, "email": 160, "ext": 30, "di_dong": 30, "don_vi": 80, "khu_vuc": 80}
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_da_tao = False


class LoiDanhBa(ValueError):
    """Lỗi hiện thẳng cho người dùng (đã viết bằng tiếng Việt)."""


def dam_bao_bang() -> None:
    global _da_tao
    if not _da_tao:
        DanhBa.__table__.create(engine, checkfirst=True)
        _da_tao = True


# ------------------------------------------------------------------ chuẩn hoá từng ô
def _o(v) -> str:
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else re.sub(r"\s+", " ", str(v)).strip()


def _email(v: str) -> str | None:
    m = _EMAIL.search(v or "")
    return m.group(0) if m else None


def _sdt(v: str) -> str | None:
    """"974887968" -> "0974 887 968"; ô có chữ khác ngoài số thì giữ nguyên."""
    v = _o(v)
    if not v:
        return None
    if not re.fullmatch(r"[\d\s.\-]+", v):
        return v
    d = re.sub(r"\D", "", v)
    d = "0" + d if len(d) == 9 else d
    return f"{d[:4]} {d[4:7]} {d[7:]}" if len(d) == 10 else d


def _ext(v: str) -> str | None:
    v = re.sub(r"\.0$", "", _o(v))
    return v or None


def chuan_don_vi(v) -> str:
    """Khoá so khớp chi nhánh: bỏ dấu, bỏ chữ "Chi nhánh"."""
    return re.sub(r"^(chi nhanh|cn)\s+", "", bo_dau(_o(v))).strip()


def nhom_chuc(chuc_vu) -> str:
    """Nhóm chức danh từ chữ tự do ("Trưởng phòng KT Hạ Tầng", "Phó Giám đốc Chi nhánh"...). Hạ tầng xét trước
    kỹ thuật vì "Trưởng phòng KT Hạ Tầng" thuộc cả hai."""
    c = bo_dau(chuc_vu)
    if re.search(r"\bpho (giam doc|gd)\b|\bpgd\b", c):
        return "pho_giam_doc"
    if re.search(r"\bgiam doc\b|^gd\b", c):
        return "giam_doc"
    if "ha tang" in c:
        return "ha_tang"
    if re.search(r"\b(truong|pho) phong (kt|ky thuat|quan ly doi tac)\b", c):
        return "truong_phong_kt"
    if "doi truong" in c:
        return "doi_truong"
    if "ke toan" in c:
        return "ke_toan"
    if re.search(r"\bdvkh\b|dich vu khach hang", c):
        return "dvkh"
    if re.search(r"hanh chinh|hcns|nhan su|\bhr\b", c):
        return "hcns"
    return "khac"


def ten_goi(ho_ten) -> str:
    """"Tô Duy Bình" -> "Bình" (cách người Việt gọi trong mail)."""
    t = _o(ho_ten).split()
    return t[-1] if t else ""


# ------------------------------------------------------------------ đọc file Excel
def _cot_tu_tieu_de(dong: list[str]) -> dict:
    """Tên cột (bỏ dấu) -> vị trí. Hai file gọi cùng một thứ bằng nhiều tên (Email / Mail, EXT / IP phone / IPP)."""
    cot: dict = {"ghi_chu": []}
    for j, c in enumerate(bo_dau(x) for x in dong):
        if c in ("ho ten", "ho va ten"):
            cot.setdefault("ho_ten", j)
        elif c in ("chuc vu", "chuc danh"):
            cot.setdefault("chuc_vu", j)
        elif c in ("email", "mail"):
            cot.setdefault("email", j)
        elif c in ("ext", "ip phone", "ipp", "so may le"):
            cot.setdefault("ext", j)
        elif c in ("di dong", "so di dong"):
            cot.setdefault("di_dong", j)
        elif c in ("khu vuc", "phong ban", "don vi", "phong"):
            cot.setdefault("don_vi", j)
        elif c.startswith(("ghi chu", "note", "khu vuc phu trach", "kiem nhiem")):
            cot["ghi_chu"].append(j)
    return cot


def _doc_sheet(df: pd.DataFrame, ten_sheet: str) -> list[dict]:
    """Một sheet -> danh sách người; sheet không có cột Họ tên + Email (vd bảng địa chỉ chi nhánh) thì trả rỗng."""
    hdr = next((i for i in range(min(10, len(df))) if {"ho ten", "ho va ten"} & {bo_dau(_o(v)) for v in df.iloc[i]}
                and {"email", "mail"} & {bo_dau(_o(v)) for v in df.iloc[i]}), None)
    if hdr is None:
        return []
    cot = _cot_tu_tieu_de([_o(v) for v in df.iloc[hdr]])
    lay = lambda r, k: r[cot[k]] if k in cot and cot[k] < len(r) else ""         # noqa: E731
    muc = cn_muc = don_vi_cu = ""
    out = []
    for i in range(hdr + 1, len(df)):
        r = [_o(v) for v in df.iloc[i]]
        ten = lay(r, "ho_ten")
        if not ten:
            if r and r[0] and not r[0].isdigit():       # dòng chỉ có nhãn mục: "Chi nhánh Huế", "BAN GIÁM ĐỐC"...
                nhan = r[0]
                cn_muc = re.sub(r"^chi nhánh\s+", "", nhan, flags=re.I) if bo_dau(nhan).startswith("chi nhanh") else ""
                muc = nhan
            continue
        if bo_dau(ten) in ("ho ten", "ho va ten"):
            continue
        cell = lay(r, "don_vi")
        don_vi_cu = cell or don_vi_cu             # ô gộp: người dưới kế thừa khu vực / phòng ban phía trên
        out.append({
            "ho_ten": ten, "chuc_vu": lay(r, "chuc_vu") or None, "email": _email(lay(r, "email")),
            "ext": _ext(lay(r, "ext")), "di_dong": _sdt(lay(r, "di_dong")),
            "don_vi": cn_muc or don_vi_cu or muc or ten_sheet, "khu_vuc": ten_sheet,
            "ghi_chu": " · ".join(x for x in (r[j] for j in cot["ghi_chu"] if j < len(r)) if x) or None})
    return out


def doc_file(noi_dung: bytes) -> tuple[list[dict], list[str]]:
    """File Excel danh bạ -> (người, tên các sheet bị bỏ qua vì không phải bảng danh bạ)."""
    try:
        x = pd.ExcelFile(io.BytesIO(noi_dung))
    except Exception:
        raise LoiDanhBa("Không mở được file. Hãy chọn file Excel (.xlsx) danh bạ.") from None
    rows, bo = [], []
    for s in x.sheet_names:
        r = _doc_sheet(x.parse(s, header=None, dtype=str), s.strip())
        rows.extend(r) if r else bo.append(s.strip())
    if not rows:
        raise LoiDanhBa("Không tìm thấy bảng danh bạ nào (cần cột Họ tên và Email).")
    return rows, bo


@ghi("danh_ba")
def nap(noi_dung: bytes, ten_file: str, nguon: str, nguoi: str) -> dict:
    """Nạp file của một nguồn: thay TOÀN BỘ dòng của nguồn đó (file là bản chụp mới nhất, không cộng dồn)."""
    if nguon not in NGUON_FILE:
        raise LoiDanhBa("Nguồn phải là PNC hoặc TIN.")
    rows, bo = doc_file(noi_dung)
    dam_bao_bang()
    bay_gio = utc_bay_gio()
    cot = [*GIOI_HAN, "ghi_chu"]
    moi = [{**{c: (r.get(c) or None) and str(r[c])[:GIOI_HAN.get(c, 5000)] for c in cot}, "nguon": nguon,
            "cap_nhat_luc": bay_gio, "cap_nhat_boi": nguoi[:60]} for r in rows]
    with session_scope() as s:
        cu = s.execute(delete(DanhBa).where(DanhBa.nguon == nguon)).rowcount or 0
        s.execute(DanhBa.__table__.insert(), moi)                # executemany: mọi dòng cùng bộ cột
        s.add(AuditLog(username=nguoi, action="nap_danh_ba", detail=f"{nguon} {ten_file}: {len(moi)} người"))
    return {"nguon": nguon, "so_nguoi": len(moi), "so_cu": int(cu), "bo_qua": bo,
            "co_email": sum(1 for r in moi if r["email"])}


# ------------------------------------------------------------------ người sale tự thêm
@ghi("danh_ba")
def luu_tay(truong: dict, nguoi: str, id_: int | None = None) -> int:
    """Thêm / sửa một người nguồn TAY. File PNC / TIN chỉ đổi bằng cách nạp lại file."""
    ten = _o(truong.get("ho_ten"))
    email, sdt = _email(_o(truong.get("email"))), _sdt(truong.get("di_dong"))
    if not ten:
        raise LoiDanhBa("Nhập họ tên.")
    if _o(truong.get("email")) and not email:
        raise LoiDanhBa("Email chưa đúng, ví dụ TenHo@fpt.com.")
    if not (email or sdt):
        raise LoiDanhBa("Nhập ít nhất email hoặc số điện thoại.")
    dam_bao_bang()
    gia_tri = {"ho_ten": ten, "chuc_vu": _o(truong.get("chuc_vu")) or None, "email": email, "di_dong": sdt,
               "ext": _ext(truong.get("ext")), "don_vi": _o(truong.get("don_vi")) or "Khác",
               "khu_vuc": "Thêm tay", "ghi_chu": _o(truong.get("ghi_chu")) or None}
    gia_tri = {k: (v[:GIOI_HAN[k]] if k in GIOI_HAN and v else v) for k, v in gia_tri.items()}
    with session_scope() as s:
        row = s.get(DanhBa, id_) if id_ else DanhBa(nguon="TAY")
        if row is None or row.nguon != "TAY":
            raise LoiDanhBa("Chỉ sửa được người do sale tự thêm. Người từ file thì nạp lại file.")
        for k, v in gia_tri.items():
            setattr(row, k, v)
        row.cap_nhat_luc, row.cap_nhat_boi = utc_bay_gio(), nguoi[:60]
        s.add(row)
        s.flush()
        s.add(AuditLog(username=nguoi, action="danh_ba_tay", detail=f"{'sửa' if id_ else 'thêm'} {ten}"))
        return int(row.id)


@ghi("danh_ba")
def xoa_tay(id_: int, nguoi: str) -> None:
    dam_bao_bang()
    with session_scope() as s:
        row = s.get(DanhBa, id_)
        if row is None or row.nguon != "TAY":
            raise LoiDanhBa("Chỉ xoá được người do sale tự thêm.")
        s.add(AuditLog(username=nguoi, action="danh_ba_tay", detail=f"xoá {row.ho_ten}"))
        s.delete(row)


# ------------------------------------------------------------------ đọc + tra cứu
COT_RA = ["id", "nguon", "nguon_ds", "ho_ten", "chuc_vu", "email", "email_khac", "ext", "di_dong", "don_vi",
          "khu_vuc", "ghi_chu", "cap_nhat_luc", "id_tay", "dv_chuan", "nhom", "ten_kd", "tim"]


@nho("danh_ba", 60)
def tat_ca() -> pd.DataFrame:
    """Mỗi NGƯỜI một dòng (đã gộp trùng giữa các nguồn). Gộp theo tên + chi nhánh; mỗi cột lấy giá trị đầu tiên
    khác rỗng theo thứ tự ưu tiên nguồn, nên số điện thoại có ở TIN mà PNC thiếu vẫn được giữ."""
    dam_bao_bang()
    df = pd.read_sql_query(text("SELECT * FROM danh_ba"), engine)
    if df.empty:
        return pd.DataFrame(columns=COT_RA)
    df["dv_chuan"] = df.don_vi.map(chuan_don_vi)
    df["khoa"] = df.ho_ten.map(bo_dau) + "|" + df.dv_chuan
    df = df.assign(uu=df.nguon.map(UU_TIEN)).sort_values(["uu", "id"])
    out = df.groupby("khoa", sort=False).first()
    khac: dict[str, set] = {}
    for k, e in zip(df.khoa, df.email):
        if isinstance(e, str) and e.lower() != str(out.at[k, "email"]).lower():
            khac.setdefault(k, set()).add(e)
    out["email_khac"] = [", ".join(sorted(khac.get(k, ()))) or None for k in out.index]
    out["nguon_ds"] = df.groupby("khoa", sort=False).nguon.agg(lambda s: "+".join(dict.fromkeys(s)))
    out["id_tay"] = df[df.nguon == "TAY"].groupby("khoa").id.first()
    out["cap_nhat_luc"] = df.groupby("khoa", sort=False).cap_nhat_luc.max()
    out = out.reset_index(drop=True)
    out["nhom"] = out.chuc_vu.map(nhom_chuc)
    out["ten_kd"] = out.ho_ten.map(bo_dau)
    out["tim"] = (out[["ho_ten", "chuc_vu", "don_vi", "khu_vuc", "email", "ghi_chu"]].fillna("").agg(" ".join, axis=1)
                  .map(bo_dau) + " " + out.di_dong.fillna("").str.replace(r"\D", "", regex=True))
    return out[COT_RA]


@nho("danh_ba", 60)
def lan_nap_cuoi() -> dict:
    """{nguồn: lần cập nhật gần nhất}: để người dùng biết dữ liệu PNC / TIN đang cũ hay mới."""
    dam_bao_bang()
    with engine.connect() as c:
        return {n: t for n, t in c.execute(text("SELECT nguon, MAX(cap_nhat_luc) FROM danh_ba GROUP BY nguon"))}


def ds_don_vi() -> list[str]:
    """Các chi nhánh / đơn vị có trong danh bạ (chi nhánh của sale đứng đầu, còn lại theo chữ cái)."""
    df = tat_ca()
    ten = df.groupby("dv_chuan").don_vi.first()
    return [ten[k] for k in sorted(ten.index, key=lambda k: (k not in DV_UU_TIEN, k)) if ten[k]]


def _s(v) -> str:
    return v if isinstance(v, str) else ""


@nho("danh_ba", 60)
def cho_trinh_duyet() -> dict:
    """Toàn bộ danh bạ dạng gọn để TRÌNH DUYỆT tự lọc (`assets/danh_ba.js`): tìm, chi nhánh, nhóm chức danh đổi là ra
    ngay, không hỏi máy chủ và không dựng hàng nghìn thành phần Dash (đã đo: chuyển nhóm bị trễ rõ). Đã xếp sẵn: chi nhánh
    của sale đứng đầu, rồi nhóm chức danh (Giám đốc trước), rồi tên. Khoá ngắn để payload nhỏ: i id, t tên, c chức vụ,
    e email, k email khác, x máy lẻ, d di động, v chi nhánh, g ghi chú, n nhóm, s nguồn, u ngày cập nhật, y id nếu sale tự
    thêm (sửa được), q chuỗi tìm (đã bỏ dấu), b tên bỏ dấu."""
    df = tat_ca()
    thu_tu = {n: i for i, n in enumerate(NHOM)}
    df = df.assign(_dv=~df.dv_chuan.isin(DV_UU_TIEN), _nhom=df.nhom.map(thu_tu)).sort_values(
        ["_dv", "_nhom", "ho_ten"], kind="stable")
    ds = [{"i": int(r.id), "t": r.ho_ten, "c": _s(r.chuc_vu), "e": _s(r.email), "k": _s(r.email_khac), "x": _s(r.ext),
           "d": _s(r.di_dong), "v": _s(r.don_vi), "g": _s(r.ghi_chu), "n": r.nhom, "s": r.nguon_ds,
           "u": chu_gio_vn(r.cap_nhat_luc, "%d/%m") if pd.notna(r.cap_nhat_luc) else "",
           "y": int(r.id_tay) if pd.notna(r.id_tay) else 0, "q": r.tim, "b": r.ten_kd}
          for r in df.itertuples()]
    moi = " · ".join(f"{n} cập nhật {chu_gio_vn(t, '%d/%m/%Y')}" for n, t in sorted(lan_nap_cuoi().items())
                     if n != "TAY" and t)
    return {"ds": ds, "moi": moi, "nhom": NHOM, "dv": ds_don_vi()}


def theo_nhom(don_vi: str, nhom: str) -> pd.DataFrame:
    """Người của một chi nhánh theo nhóm chức danh, dùng để gợi ý người nhận. Chi nhánh có trong cả hai file thì
    lấy bản mới (PNC) / người sale tự thêm; chỉ khi không có mới dùng bản cũ (TIN)."""
    df = tat_ca()
    df = df[(df.dv_chuan == chuan_don_vi(don_vi)) & (df.nhom == nhom)]
    moi = df[df.nguon_ds.str.contains("PNC|TAY", regex=True)]
    return moi if not moi.empty else df


def doi_truong_theo_dia_chi(don_vi: str, dia_chi: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(đội trưởng phụ trách khu vực trong địa chỉ, mọi đội trưởng của chi nhánh). Khu vực phụ trách chỉ là chữ tự do
    ở cột ghi chú ("Block Sơn Trà", "Hòa Bắc, Hòa Liên") nên khớp từng cụm với địa chỉ (bỏ dấu)."""
    ds = theo_nhom(don_vi, "doi_truong")
    dc = bo_dau(dia_chi)

    def khop(ghi_chu) -> bool:
        cum = re.split(r"[,;+/\n·]|\bva\b", bo_dau(ghi_chu))
        cum = [re.sub(r"^(block|phu trach chung|phu trach|dng \d+)\s*", "", c).strip() for c in cum]
        return any(len(c) >= 3 and not c.isdigit() and c in dc for c in cum)

    return (ds[ds.ghi_chu.map(khop)] if dc and not ds.empty else ds.iloc[0:0]), ds


def doan_don_vi(dia_chi: str) -> str | None:
    """Chi nhánh nhắc trong địa chỉ ("... Nha Trang, Khánh Hòa" -> Khánh Hòa); lấy tên dài nhất khớp."""
    dc, tot = bo_dau(dia_chi), None
    for dv in ds_don_vi():
        k = chuan_don_vi(dv)
        if len(k) >= 4 and re.search(rf"\b{re.escape(k)}\b", dc) and (tot is None or len(k) > len(chuan_don_vi(tot))):
            tot = dv
    return tot
