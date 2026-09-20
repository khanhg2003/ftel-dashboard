"""Quảng cáo Facebook IBB7: nhận chi tiêu hằng ngày từ n8n, lead / PTTB từ bot Telegram, chia chi phí cho sale.

Thay cho file Google Sheet mỗi tháng một file, mỗi page một trang tính:
- Một kho duy nhất: page × camp × ngày (`ads_ngay`) - xem tháng nào thì lọc tháng đó, không phải đổi file.
- Page mới: lần đầu n8n / bot gửi dữ liệu của page lạ thì app tự tạo page (chưa phân công sale).
- Phân công (PIC) khai theo khoảng ngày (`ads_pic`), tối đa 3 sale mỗi ngày: chi tiêu mỗi ngày chia đều cho các
  sale chạy page ngày đó (giống cột Tiền/Người của sheet). Page tài khoản công ty (loại 'cong_ty') không chia.
- Đánh giá page theo chi phí / PTTB (USD): <= 6 Tốt, <= 10 Trung bình, còn lại Kém (như DASHBOARD của sheet);
  chưa có PTTB mà đã tiêu từ 10$ cũng là Kém, dưới 10$ là Chưa đủ số.
- Chi tiêu về trễ một ngày (n8n gửi 7h sáng hôm sau) còn PTTB về ngay: chi phí / số ĐT, chi phí / PTTB chỉ tính lead /
  PTTB tới ngày đã có chi tiêu, để tiền và kết quả cùng khoảng ngày.
Tiền lưu bằng USD như Facebook; đổi VNĐ theo tỷ giá từng tháng (`ads_thang`).
"""
from __future__ import annotations

import calendar
import hashlib
import hmac
import math
import re
import secrets
import unicodedata
from datetime import date, datetime, timedelta

import pandas as pd
from sqlalchemy import select, text

from app.bo_nho import ghi, nho
from app.db import engine, session_scope
from app.models import AdsLead, AdsNgay, AdsPage, AdsPic, AdsSale, AdsThang, AuditLog, CaiDat

BANG = (AdsPage, AdsSale, AdsPic, AdsNgay, AdsLead, AdsThang)
TY_GIA_MAC_DINH = 26394.0
NGUONG_TOT, NGUONG_BINH_THUONG = 6.0, 10.0      # USD / PTTB
CONG_TY, CHUA_PHAN_CONG = "Công ty", "Chưa phân công"
TINH_TRANG_PAGE = ["Đang chạy", "Đang nuôi", "Tắt"]
TOI_DA_PIC = 3
CAMP_TONG_THANG = "Nhập tay (tổng tháng từ sheet)"     # tiền cả tháng ghi vào ngày 01 (không có số từng ngày)
KHOA_TOKEN = "ads.token"
_da_tao = False


class LoiAds(Exception):
    """Lỗi dữ liệu gửi lên / thao tác - câu tiếng Việt trả thẳng cho người dùng hoặc n8n."""


def dam_bao_bang() -> None:
    global _da_tao
    if not _da_tao:
        for b in BANG:
            b.__table__.create(engine, checkfirst=True)
        from sqlalchemy import inspect
        if "link" not in {c["name"] for c in inspect(engine).get_columns("ads_page")}:     # cột thêm sau
            with engine.begin() as c:
                c.execute(text("ALTER TABLE ads_page ADD COLUMN link VARCHAR(300)"))
        _da_tao = True


# ------------------------------------------------------------------ chuẩn hoá
def chuan_ma(ten) -> str:
    """Tên page chuẩn: bỏ khoảng trắng thừa, chữ hoa, Unicode dựng sẵn (NFC) - 'Kon  tum' -> 'KON TUM'."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(ten or ""))).strip().upper()


def khoa_sale(ten) -> str:
    """So khớp tên sale không phân biệt hoa thường / khoảng trắng: 'C.HỒNG' = 'C. Hồng'."""
    return re.sub(r"[\s.]+", "", unicodedata.normalize("NFC", str(ten or ""))).lower()


def doc_ngay(v) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def doc_so(v, mac_dinh=0.0) -> float:
    """Số từ n8n / sheet: 4.93, '4,93', '1.234,5', '' -> mặc định."""
    if v is None or v == "":
        return mac_dinh
    if isinstance(v, (int, float)):
        return mac_dinh if isinstance(v, float) and math.isnan(v) else float(v)
    s = str(v).strip().replace(" ", "").replace("$", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        raise LoiAds(f"Không đọc được số '{v}'.") from None


def _page(s, ten, tao: bool = True, ten_hien: str | None = None) -> AdsPage | None:
    ma = chuan_ma(ten)
    if not ma:
        raise LoiAds("Thiếu tên page.")
    p = s.execute(select(AdsPage).where(AdsPage.ma == ma)).scalars().first()
    if p is None and tao:
        p = AdsPage(ma=ma, ten=ten_hien or str(ten).strip(), loai="cong_ty" if "TRUNG LẬP" in ma else "sale",
                    tinh_trang="Đang chạy")
        s.add(p)
        s.flush()
    return p


# ------------------------------------------------------------------ mã kết nối n8n
def co_token() -> bool:
    dam_bao_bang()
    with session_scope() as s:
        return s.get(CaiDat, KHOA_TOKEN) is not None


@ghi("ads")
def tao_token(nguoi: str) -> str:
    """Tạo mã mới (mã cũ hết hiệu lực). Chỉ lưu dạng băm - mã gốc hiện đúng một lần."""
    dam_bao_bang()
    tok = "ads_" + secrets.token_urlsafe(24)
    bam = hashlib.sha256(tok.encode()).hexdigest()
    with session_scope() as s:
        r = s.get(CaiDat, KHOA_TOKEN)
        if r is None:
            s.add(CaiDat(khoa=KHOA_TOKEN, gia_tri=bam, updated_by=nguoi))
        else:
            r.gia_tri, r.updated_by, r.updated_at = bam, nguoi, datetime.utcnow()
        s.add(AuditLog(username=nguoi, action="ads_tao_ma", detail="Tạo mã kết nối n8n mới"))
    return tok


def kiem_token(tok: str | None) -> bool:
    if not tok:
        return False
    with session_scope() as s:
        r = s.get(CaiDat, KHOA_TOKEN)
        luu = r.gia_tri if r else None
    return bool(luu) and hmac.compare_digest(hashlib.sha256(tok.encode()).hexdigest(), luu)


# ------------------------------------------------------------------ nhận dữ liệu
def _dong(du_lieu) -> list[dict]:
    """Chấp nhận: 1 dòng, danh sách dòng, hoặc {page, rows: [...]} (dòng không ghi page thì lấy page ngoài)."""
    if isinstance(du_lieu, list):
        out = []
        for x in du_lieu:
            out += _dong(x)
        return out
    if not isinstance(du_lieu, dict):
        raise LoiAds("Dữ liệu phải là JSON object hoặc danh sách.")
    rows = du_lieu.get("rows") or du_lieu.get("dong")
    if isinstance(rows, list):
        return [{"page": du_lieu.get("page"), **r} for r in rows]
    return [du_lieu]


def _lay(r: dict, *ten):
    for t in ten:
        if t in r and r[t] not in (None, ""):
            return r[t]
    return None


@ghi("ads")
def nhan_chi_tieu(du_lieu, nguon: str = "n8n", nguoi: str = "n8n") -> dict:
    """Ghi chi tiêu từng camp từng ngày. Cùng page + camp + ngày gửi lại thì ghi đè (n8n chạy lại không bị nhân đôi).
    Đọc sẵn một lần các dòng đã có của những page / ngày liên quan - không tra database từng dòng."""
    dam_bao_bang()
    dong = _dong(du_lieu)
    kq = {"nhan": len(dong), "moi": 0, "cap_nhat": 0, "page_moi": [], "loi": []}
    sach = []
    for i, r in enumerate(dong, start=1):
        try:
            camp = str(_lay(r, "camp", "ten_camp", "campaign", "campaign_name") or "").strip()[:160]
            ngay = doc_ngay(_lay(r, "ngay", "date", "date_start"))
            if not camp or not ngay:
                raise LoiAds("thiếu tên camp hoặc ngày")
            ma = chuan_ma(_lay(r, "page", "trang", "ten_page", "fanpage"))
            if not ma:
                raise LoiAds("thiếu tên page")
            sach.append((ma, camp, ngay, str(_lay(r, "tinh_trang", "status", "trang_thai") or "")[:30] or None,
                         round(doc_so(_lay(r, "chi_tieu", "spend")), 4),
                         int(doc_so(_lay(r, "tin_nhan", "messages", "tong_tin_nhan")))))
        except LoiAds as e:
            kq["loi"].append(f"dòng {i}: {e}")
    with session_scope() as s:
        pages = {p.ma: p for p in s.execute(select(AdsPage)).scalars()}
        for ma in dict.fromkeys(x[0] for x in sach):
            if ma not in pages:
                pages[ma] = _page(s, ma)
                kq["page_moi"].append(ma)
        co = {}
        if sach:
            ids = {pages[x[0]].id for x in sach}
            for row in s.execute(select(AdsNgay).where(AdsNgay.page_id.in_(ids),
                                                        AdsNgay.ngay >= min(x[2] for x in sach),
                                                        AdsNgay.ngay <= max(x[2] for x in sach))).scalars():
                co[(row.page_id, row.camp, row.ngay)] = row
        for ma, camp, ngay, tt, chi, tin in sach:
            k = (pages[ma].id, camp, ngay)
            row = co.get(k)
            if row is None:
                row = co[k] = AdsNgay(page_id=k[0], camp=camp, ngay=ngay)
                s.add(row)
                kq["moi"] += 1
            else:
                kq["cap_nhat"] += 1
            row.tinh_trang = tt or row.tinh_trang
            row.chi_tieu, row.tin_nhan, row.nguon, row.updated_at = chi, tin, nguon, datetime.utcnow()
        s.add(AuditLog(username=nguoi, action="ads_nhan_chi_tieu",
                       detail=f"{nguon}: {kq['moi']} mới, {kq['cap_nhat']} cập nhật, {len(kq['loi'])} lỗi"
                              + (f", page mới {', '.join(kq['page_moi'])}" if kq["page_moi"] else "")))
    return kq


@ghi("ads")
def nhan_lead(du_lieu, nguon: str = "telegram", nguoi: str | None = None) -> dict:
    """Mỗi lần báo có số điện thoại / PTTB: +lead, +pttb cho page trong ngày (mặc định hôm nay theo giờ VN)."""
    dam_bao_bang()
    from app.thoi_gian import gio_viet_nam
    dong = _dong(du_lieu)
    kq = {"nhan": len(dong), "ghi": 0, "page_moi": [], "loi": []}
    with session_scope() as s:
        cu = {p.ma for p in s.execute(select(AdsPage)).scalars()}
        for i, r in enumerate(dong, start=1):
            try:
                p = _page(s, _lay(r, "page", "trang", "ten_page", "fanpage"))
                if p.ma not in cu:
                    cu.add(p.ma)
                    kq["page_moi"].append(p.ma)
                lead, pttb = int(doc_so(_lay(r, "lead", "so_dien_thoai", "sdt"))), int(doc_so(_lay(r, "pttb")))
                if not lead and not pttb:
                    raise LoiAds("lead và pttb đều bằng 0")
                s.add(AdsLead(page_id=p.id, ngay=doc_ngay(_lay(r, "ngay", "date")) or gio_viet_nam().date(),
                              lead=lead, pttb=pttb, nguon=nguon,
                              nguoi=str(_lay(r, "nguoi", "user", "tu") or nguoi or "")[:80] or None,
                              ghi_chu=str(_lay(r, "ghi_chu", "note") or "")[:300] or None))
                kq["ghi"] += 1
            except LoiAds as e:
                kq["loi"].append(f"dòng {i}: {e}")
        s.add(AuditLog(username=nguoi or nguon, action="ads_nhan_lead",
                       detail=f"{nguon}: {kq['ghi']} dòng, {len(kq['loi'])} lỗi"))
    return kq


# ------------------------------------------------------------------ đọc số liệu
def _q(sql: str, **p) -> pd.DataFrame:
    dam_bao_bang()
    return pd.read_sql_query(text(sql), engine, params=p)


@nho("ads")
def ds_page() -> pd.DataFrame:
    return _q("SELECT id, ma, ten, loai, tinh_trang, ghi_chu, link FROM ads_page ORDER BY ten")


@nho("ads")
def ds_pic() -> pd.DataFrame:
    df = _q("SELECT id, page_id, sale, tu_ngay, den_ngay, ty_le FROM ads_pic")
    for c in ("tu_ngay", "den_ngay"):
        df[c] = pd.to_datetime(df[c]).dt.date
    return df


@nho("ads")
def ds_sale() -> pd.DataFrame:
    return _q("SELECT ten, acc FROM ads_sale ORDER BY ten")


@nho("ads")
def ty_gia(thang: str) -> float:
    """Tỷ giá tháng; chưa nhập thì lấy tháng gần nhất trước đó, không có nữa thì mặc định."""
    df = _q("SELECT ty_gia FROM ads_thang WHERE thang <= :t ORDER BY thang DESC LIMIT 1", t=thang)
    return float(df.ty_gia.iloc[0]) if len(df) else TY_GIA_MAC_DINH


@nho("ads")
def theo_ngay(tu: date, den: date) -> pd.DataFrame:
    """Dòng = page × ngày: chi tiêu, tin nhắn, lead, PTTB (kèm thông tin page)."""
    a = _q("""SELECT page_id, ngay, SUM(chi_tieu) AS chi_tieu, SUM(tin_nhan) AS tin_nhan FROM ads_ngay
              WHERE ngay >= :tu AND ngay <= :den GROUP BY page_id, ngay""", tu=tu, den=den)
    b = _q("""SELECT page_id, ngay, SUM(lead) AS lead, SUM(pttb) AS pttb FROM ads_lead
              WHERE ngay >= :tu AND ngay <= :den GROUP BY page_id, ngay""", tu=tu, den=den)
    for x in (a, b):
        x["ngay"] = pd.to_datetime(x["ngay"]).dt.date
    df = a.merge(b, on=["page_id", "ngay"], how="outer")
    for c in ("chi_tieu", "tin_nhan", "lead", "pttb"):
        df[c] = pd.to_numeric(df.get(c), errors="coerce").fillna(0)
    pg = ds_page().rename(columns={"id": "page_id"})
    return df.merge(pg, on="page_id", how="left")


DANH_GIA = {"Hiệu quả cao": "Tốt", "Trung bình": "Trung bình", "Kém": "Kém", "Chưa đủ dữ liệu": "Chưa đủ số"}


def danh_gia(chi: float, pttb: float) -> str:
    """Nhãn ngắn của nhóm hiệu quả (cùng quy tắc với tab Nhận định)."""
    if not chi and not pttb:
        return ""
    if not chi:
        return "Chưa có chi tiêu"
    return DANH_GIA[nhom_hieu_qua(chi, pttb)]


def _chi_so(g: pd.DataFrame) -> pd.DataFrame:
    """CPL, CP/PTTB dùng lead / PTTB khớp ngày chi tiêu (cột lead_cp / pttb_cp nếu có), tỷ lệ chốt dùng số đầy đủ."""
    g = g.copy()
    co_chi = g.chi_tieu > 0
    ld = g["lead_cp"] if "lead_cp" in g else g.lead
    pt = g["pttb_cp"] if "pttb_cp" in g else g.pttb
    ch = g["chi_cp"] if "chi_cp" in g else g.chi_tieu
    g["cpl"] = (ch / ld.where(ld > 0)).where(co_chi).round(2)
    g["cp_pttb"] = (ch / pt.where(pt > 0)).where(co_chi).round(2)
    g["ty_le_chot"] = (g.pttb / g.lead.where(g.lead > 0) * 100).round(0)
    g["cp_tin_nhan"] = (g.chi_tieu / g.tin_nhan.where(g.tin_nhan > 0)).round(2)
    return g


def lui_thang(d: date) -> date:
    dau = d.replace(day=1) - timedelta(days=1)
    return dau.replace(day=min(d.day, dau.day))


def theo_page(tu: date, den: date, ck: tuple[date, date] | None = None, df: pd.DataFrame | None = None) \
        -> pd.DataFrame:
    """Dòng = page: tổng chi tiêu / tin nhắn / lead / PTTB, CPL, CP/PTTB, tỷ lệ chốt, đánh giá, kỳ so sánh (mặc định
    cùng kỳ tháng trước)."""
    df = theo_ngay(tu, den) if df is None else df
    pg = ds_page()
    cot = ["chi_tieu", "tin_nhan", "lead", "pttb"]
    g = df.groupby("page_id")[cot].sum() if len(df) else pd.DataFrame(columns=cot)
    out = pg.set_index("id").join(g, how="left").fillna({c: 0 for c in cot})
    cuoi = cuoi_tu_bang(df)
    if cuoi is not None:
        k = df[df.ngay <= cuoi].groupby("page_id")[["chi_tieu", "lead", "pttb"]].sum()
        out["chi_cp"] = k["chi_tieu"].reindex(out.index).fillna(0)
        out["lead_cp"] = k["lead"].reindex(out.index).fillna(0)
        out["pttb_cp"] = k["pttb"].reindex(out.index).fillna(0)
    out = out[(out[cot].sum(axis=1) > 0) | (out.tinh_trang == "Đang chạy")]
    ck = theo_ngay(*(ck or (lui_thang(tu), lui_thang(den))))
    ckg = ck.groupby("page_id")[["chi_tieu", "pttb"]].sum() if len(ck) else pd.DataFrame(columns=["chi_tieu", "pttb"])
    out["ck_chi_tieu"] = ckg.chi_tieu.reindex(out.index).fillna(0)
    out["ck_pttb"] = ckg.pttb.reindex(out.index).fillna(0)
    out = _chi_so(out)
    pt = out["pttb_cp"] if "pttb_cp" in out else out.pttb
    ch = out["chi_cp"] if "chi_cp" in out else out.chi_tieu
    out["danh_gia"] = [danh_gia(c, p) if c or not t else danh_gia(t, p) for c, p, t in zip(ch, pt, out.chi_tieu)]
    pics = ds_pic()
    out["pic"] = [", ".join(sale_dang_chay(pics, i, den)) or ("—" if l == "cong_ty" else CHUA_PHAN_CONG)
                  for i, l in zip(out.index, out.loai)]
    out.attrs.update(cuoi=cuoi)
    return out.reset_index().rename(columns={"index": "page_id", "id": "page_id"}).sort_values(
        "chi_tieu", ascending=False)


def _pic_ngay(pics: pd.DataFrame, page_id: int, d: date) -> pd.DataFrame:
    x = pics[(pics.page_id == page_id) & (pics.tu_ngay <= d) & (pics.den_ngay.isna() | (pics.den_ngay >= d))]
    return x.sort_values("tu_ngay").drop_duplicates("sale").head(TOI_DA_PIC)


def sale_dang_chay(pics: pd.DataFrame, page_id: int, d: date) -> list[str]:
    return list(_pic_ngay(pics, page_id, d).sale)


def phan_chia(pics: pd.DataFrame, page_id: int, d: date) -> list[tuple[str, float]]:
    """[(sale, phần)] của một page một ngày: có tỷ lệ riêng cho mọi người thì theo tỷ lệ, không thì chia đều."""
    x = _pic_ngay(pics, page_id, d)
    if x.empty:
        return []
    tl = pd.to_numeric(x.ty_le, errors="coerce")
    if tl.notna().all() and tl.sum() > 0:
        return [(s_, float(t) / float(tl.sum())) for s_, t in zip(x.sale, tl)]
    return [(s_, 1 / len(x)) for s_ in x.sale]


@nho("ads")
def phan_bo(tu: date, den: date) -> pd.DataFrame:
    """Chia từng page × ngày cho các sale chạy page ngày đó: chi tiêu chia đều; lead / PTTB cũng chia đều để so
    hiệu quả theo sale. Page công ty -> 'Công ty'; page chưa khai PIC -> 'Chưa phân công'."""
    df = theo_ngay(tu, den)
    if df.empty:
        return pd.DataFrame(columns=["sale", "page_id", "ngay", "chi_tieu", "tin_nhan", "lead", "pttb"])
    pics = ds_pic()
    rows = []
    for r in df.itertuples():
        if r.loai == "cong_ty":
            ai = [(CONG_TY, 1.0)]
        else:
            ai = phan_chia(pics, r.page_id, r.ngay) or [(CHUA_PHAN_CONG, 1.0)]
        for a, phan in ai:
            rows.append({"sale": a, "page_id": r.page_id, "ngay": r.ngay, "chi_tieu": r.chi_tieu * phan,
                         "tin_nhan": r.tin_nhan * phan, "lead": r.lead * phan, "pttb": r.pttb * phan})
    return pd.DataFrame(rows)


def theo_sale(tu: date, den: date) -> pd.DataFrame:
    """Dòng = sale: số page, chi phí được chia (USD) và dự kiến chi tới hết tháng.
    Dự kiến = đã chi + (trung bình/ngày của 5 ngày gần nhất có số chi tiêu) × số ngày còn lại của tháng. Trung bình
    tính trên phần tiền được chia của mọi page sale chạy trong 5 ngày đó (ngày không chạy tính 0)."""
    pb = phan_bo(tu, den)
    if pb.empty:
        return pd.DataFrame()
    g = pb.groupby("sale").agg(chi_tieu=("chi_tieu", "sum"), tin_nhan=("tin_nhan", "sum"), lead=("lead", "sum"),
                                pttb=("pttb", "sum"), so_page=("page_id", "nunique")).reset_index()
    g = _chi_so(g)
    ds = ds_sale()
    acc = {khoa_sale(t): a for t, a in zip(ds.ten, ds.acc) if a}
    g["acc"] = [acc.get(khoa_sale(t)) or None for t in g.sale]
    cuoi = ngay_cuoi_chi(tu, den)
    g["tb_5_ngay"], g["du_kien"] = None, g.chi_tieu
    if cuoi:
        a = max(tu, cuoi - timedelta(days=4))
        so_ngay = (cuoi - a).days + 1
        gan = pb[(pb.ngay >= a) & (pb.ngay <= cuoi)].groupby("sale").chi_tieu.sum()
        g["tb_5_ngay"] = (g.sale.map(gan).fillna(0) / so_ngay).round(2)
        con = calendar.monthrange(cuoi.year, cuoi.month)[1] - cuoi.day
        g["du_kien"] = (g.chi_tieu + g.tb_5_ngay * con).round(2)
    tay = tien_tong_thang(tu, den)
    g["ghi_chu"] = ""
    if len(tay):
        tay_sale = pb.merge(tay[["page_id", "ngay"]].drop_duplicates(), on=["page_id", "ngay"]) \
            .groupby("sale").chi_tieu.sum()
        g["ghi_chu"] = [f"Có {_tien(tay_sale[x])}$ nhập tay tổng tháng (không có số từng ngày) nên dự kiến "
                        "không ước được phần chạy tiếp của page đó" if x in tay_sale.index else "" for x in g.sale]
    g.attrs.update(cuoi=cuoi)
    thu_tu = {CONG_TY: 2, CHUA_PHAN_CONG: 3}
    return g.assign(_o=g.sale.map(thu_tu).fillna(0)).sort_values(["_o", "chi_tieu"], ascending=[True, False]) \
            .drop(columns="_o").reset_index(drop=True)


def tracking(thang: str, chi_so: str = "chi_tieu", loai: str = "all") -> tuple[pd.DataFrame, int]:
    """Bảng page × ngày trong tháng (như TRACKING NGÀY). `loai`: all | sale | cong_ty (page tài khoản công ty)."""
    from app.metrics import month_range
    dau, cuoi, so_ngay = month_range(thang)
    df = theo_ngay(dau, cuoi)
    if loai in ("sale", "cong_ty") and len(df):
        df = df[df.loai == loai]
    if df.empty:
        return pd.DataFrame(), so_ngay
    df["d"] = [x.day for x in df.ngay]
    if chi_so == "cp_pttb":                     # chi phí / PTTB từng ngày; ngày chưa có PTTB để trống
        c = df.pivot_table(index=["page_id", "ten"], columns="d", values="chi_tieu", aggfunc="sum", fill_value=0)
        p = df.pivot_table(index=["page_id", "ten"], columns="d", values="pttb", aggfunc="sum", fill_value=0)
        pv = (c / p.where(p > 0)).round(2).reindex(columns=range(1, so_ngay + 1))
        tc, tp_ = c.sum(axis=1), p.sum(axis=1)
        pv["tong"] = (tc / tp_.where(tp_ > 0)).round(2)
        cn, pn = c.sum(axis=0), p.sum(axis=0)
        tong = {str(d): round(float(cn.get(d, 0)) / float(pn[d]), 2) for d in range(1, so_ngay + 1)
                if d in pn.index and pn[d] > 0}
        tong["tong"] = round(float(tc.sum()) / float(tp_.sum()), 2) if tp_.sum() else None
        pv = pv.sort_values("tong").reset_index()
        pv.attrs.update(tong=tong)
        return pv, so_ngay
    pv = df.pivot_table(index=["page_id", "ten"], columns="d", values=chi_so, aggfunc="sum", fill_value=0)
    pv = pv.reindex(columns=range(1, so_ngay + 1), fill_value=0)
    pv["tong"] = pv.sum(axis=1)
    tong = {str(k): round(float(v), 2) for k, v in pv.sum(axis=0).items()}
    pv = pv.sort_values("tong", ascending=False).reset_index()
    pv.attrs.update(tong=tong)
    return pv, so_ngay


def tong_quan(tu: date, den: date, ck: tuple[date, date] | None = None, df: pd.DataFrame | None = None) -> dict:
    """Số chính của kỳ. Chi phí / số ĐT, chi phí / PTTB chỉ tính lead / PTTB tới ngày đã có chi tiêu (`den_cp`)."""
    df = theo_ngay(tu, den) if df is None else df
    ck = theo_ngay(*(ck or (lui_thang(tu), lui_thang(den))))
    t = {c: float(df[c].sum()) if len(df) else 0.0 for c in ("chi_tieu", "tin_nhan", "lead", "pttb")}
    c = {c: float(ck[c].sum()) if len(ck) else 0.0 for c in ("chi_tieu", "tin_nhan", "lead", "pttb")}
    cuoi = cuoi_tu_bang(df)
    khop = df[df.ngay <= cuoi] if cuoi else df.iloc[0:0]
    chi_cp = float(khop.chi_tieu.sum()) if len(khop) else 0.0
    lead_cp, pttb_cp = float(khop.lead.sum()) if len(khop) else 0.0, float(khop.pttb.sum()) if len(khop) else 0.0
    rate = ty_gia(f"{den.year}-{den.month:02d}")
    return {**t, "ck": c, "ty_gia": rate, "vnd": t["chi_tieu"] * rate,
            "cpl": chi_cp / lead_cp if lead_cp and chi_cp else None,
            "cp_pttb": chi_cp / pttb_cp if pttb_cp and chi_cp else None,
            "ty_le_chot": t["pttb"] / t["lead"] * 100 if t["lead"] else None,
            "ck_cp_pttb": c["chi_tieu"] / c["pttb"] if c["pttb"] and c["chi_tieu"] else None,
            "so_page": int((df.groupby("page_id").chi_tieu.sum() > 0).sum()) if len(df) else 0,
            "den_cp": cuoi, "pttb_chua_khop": t["pttb"] - pttb_cp if cuoi else 0.0,
            "ngay_moi_nhat": cuoi}


def nhat_ky_lead(tu: date, den: date) -> pd.DataFrame:
    df = _q("""SELECT l.id, l.ngay, p.ten AS page, l.lead, l.pttb, l.nguon, l.nguoi, l.ghi_chu, l.created_at
               FROM ads_lead l JOIN ads_page p ON p.id = l.page_id
               WHERE l.ngay >= :tu AND l.ngay <= :den ORDER BY l.created_at DESC""", tu=tu, den=den)
    return df


# ------------------------------------------------------------------ cấu hình
def _khoa_ten(ten) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(ten or ""))).strip().lower()


def _kiem_trung_ten(s, doi: dict[int, str]) -> None:
    """Không cho hai page trùng tên hiển thị (biểu đồ / bảng sẽ không phân biệt được). `doi` = {page_id: tên mới}."""
    ten = {p.id: p.ten for p in s.execute(select(AdsPage)).scalars()}
    ten.update(doi)
    gap = {}
    for pid, t in ten.items():
        gap.setdefault(_khoa_ten(t), []).append(pid)
    for pid, t in doi.items():
        khac = [i for i in gap[_khoa_ten(t)] if i != pid]
        if khac:
            ma = s.get(AdsPage, khac[0]).ma
            raise LoiAds(f"Tên '{t}' đang dùng cho page {ma} - mỗi page cần một tên riêng để không lẫn trên báo cáo.")


def trung_ten() -> list[tuple[str, list[str]]]:
    """Các tên hiển thị đang bị nhiều page dùng chung: [(tên, [tên chuẩn...])]."""
    pg = ds_page()
    pg["k"] = [_khoa_ten(t) for t in pg.ten]
    return [(g.ten.iloc[0], list(g.ma)) for _, g in pg.groupby("k") if len(g) > 1]


@ghi("ads")
def luu_page(rows: list[dict], nguoi: str) -> int:
    dam_bao_bang()
    n = 0
    with session_scope() as s:
        _kiem_trung_ten(s, {int(r["id"]): str(r.get("ten") or "").strip() for r in rows
                            if str(r.get("ten") or "").strip()
                            and _khoa_ten(r.get("ten")) != _khoa_ten(s.get(AdsPage, int(r["id"])).ten)})
        for r in rows:
            p = s.get(AdsPage, int(r["id"]))
            if p is None:
                continue
            ten = str(r.get("ten") or p.ten).strip()
            loai = "cong_ty" if r.get("loai") in ("cong_ty", "Công ty") else "sale"
            tt = r.get("tinh_trang") if r.get("tinh_trang") in TINH_TRANG_PAGE else p.tinh_trang
            link = chuan_link(r["link"]) if "link" in r else p.link
            moi = (ten, loai, tt, r.get("ghi_chu") or None, link)
            if (p.ten, p.loai, p.tinh_trang, p.ghi_chu, p.link) != moi:
                p.ten, p.loai, p.tinh_trang, p.ghi_chu, p.link = moi
                n += 1
        s.add(AuditLog(username=nguoi, action="ads_sua_page", detail=f"{n} page"))
    return n


@ghi("ads")
def them_page(ma, ten: str | None, loai: str, link: str | None, tinh_trang: str | None, nguoi: str) -> str:
    """Tạo page trước khi có số (VD page chạy tài khoản ngoài n8n để nhập tay). `ma` = tên chuẩn n8n / bot sẽ gửi."""
    dam_bao_bang()
    ma_c = chuan_ma(ma)
    if not ma_c:
        raise LoiAds("Nhập tên chuẩn của page (tên n8n / bot Telegram gửi lên).")
    ten = re.sub(r"\s+", " ", str(ten or "")).strip() or str(ma).strip()
    lk = chuan_link(link)
    with session_scope() as s:
        if s.execute(select(AdsPage).where(AdsPage.ma == ma_c)).scalars().first():
            raise LoiAds(f"Đã có page tên chuẩn '{ma_c}'.")
        s.add(p := AdsPage(ma=ma_c, ten=ten[:120], link=lk,
                           loai="cong_ty" if loai in ("cong_ty", "Công ty") or "TRUNG LẬP" in ma_c else "sale",
                           tinh_trang=tinh_trang if tinh_trang in TINH_TRANG_PAGE else "Đang chạy"))
        s.flush()
        _kiem_trung_ten(s, {p.id: p.ten})
        s.add(AuditLog(username=nguoi, action="ads_them_page", detail=f"{ma_c} ({p.ten})"))
    return f"Đã thêm page {ten} (tên chuẩn {ma_c})."


@ghi("ads")
def them_sale(ten: str, acc: str | None, nguoi: str) -> str:
    """Thêm tên gọi sale (dùng trong phân công page) và acc inside."""
    dam_bao_bang()
    ten = re.sub(r"\s+", " ", str(ten or "")).strip()
    if not ten:
        raise LoiAds("Nhập tên gọi của sale (VD: C. Lan).")
    if len(ten) > 60:
        raise LoiAds("Tên gọi tối đa 60 ký tự.")
    with session_scope() as s:
        trung = [x.ten for x in s.execute(select(AdsSale)).scalars() if khoa_sale(x.ten) == khoa_sale(ten)]
        if trung:
            raise LoiAds(f"Đã có sale '{trung[0]}'.")
        s.add(AdsSale(ten=ten, acc=str(acc or "").strip() or None))
        s.add(AuditLog(username=nguoi, action="ads_them_sale", detail=ten))
    return f"Đã thêm sale {ten}."


@ghi("ads")
def them_pic(page_id: int, sales: list[str], tu: date, den: date | None, nguoi: str,
             ty_le: list[float | None] | None = None) -> str:
    """Khai sale chạy page từ ngày `tu` (đến `den`, trống = đến nay). Các khai báo cũ còn mở của page được đóng lại
    ở ngày trước `tu` - đúng cách đổi người chạy giữa tháng (A+B 01-10, A+C từ 11)."""
    dam_bao_bang()
    sales = [x.strip() for x in sales if x and x.strip()]
    if not sales:
        raise LoiAds("Chọn ít nhất 1 sale.")
    if len(sales) > TOI_DA_PIC:
        raise LoiAds(f"Một page tối đa {TOI_DA_PIC} sale cùng chạy.")
    if den and den < tu:
        raise LoiAds("Ngày kết thúc phải sau ngày bắt đầu.")
    ty_le = [(float(x) if x not in (None, "") else None) for x in (ty_le or [])][:len(sales)]
    ty_le += [None] * (len(sales) - len(ty_le))
    if any(x is not None for x in ty_le):
        if any(x is None or x <= 0 for x in ty_le):
            raise LoiAds("Chia theo tỷ lệ thì nhập % cho đủ mọi sale (VD 70 và 30); để trống hết = chia đều.")
        if abs(sum(ty_le) - 100) > 0.5:
            raise LoiAds(f"Tổng tỷ lệ phải là 100% (đang {sum(ty_le):g}%).")
    with session_scope() as s:
        p = s.get(AdsPage, page_id)
        if p is None:
            raise LoiAds("Không có page này.")
        for x in s.execute(select(AdsPic).where(AdsPic.page_id == page_id)).scalars():
            if x.tu_ngay >= tu and (den is None or x.tu_ngay <= den):
                s.delete(x)                                        # khai báo bị thay hoàn toàn
            elif x.tu_ngay < tu and (x.den_ngay is None or x.den_ngay >= tu):
                x.den_ngay = tu - timedelta(days=1)                # đóng khai báo cũ trước ngày đổi
        for sale, tl in zip(sales, ty_le):
            s.add(AdsPic(page_id=page_id, sale=sale, tu_ngay=tu, den_ngay=den, ty_le=tl))
            if s.get(AdsSale, sale) is None:
                s.add(AdsSale(ten=sale))
        s.add(AuditLog(username=nguoi, action="ads_phan_cong",
                       detail=f"{p.ten}: {', '.join(sales)} từ {tu:%d/%m/%Y}" + (f" đến {den:%d/%m/%Y}" if den else "")))
    chia = (" (" + " / ".join(f"{x:g}%" for x in ty_le) + ")") if ty_le[0] is not None else ""
    return (f"{p.ten}: {', '.join(sales)}{chia} chạy từ {tu:%d/%m/%Y}" + (f" đến {den:%d/%m/%Y}" if den else "")
            + ".")


@ghi("ads")
def xoa_pic(ids: list[int], nguoi: str) -> int:
    dam_bao_bang()
    with session_scope() as s:
        n = 0
        for i in ids:
            x = s.get(AdsPic, int(i))
            if x:
                s.delete(x)
                n += 1
        s.add(AuditLog(username=nguoi, action="ads_xoa_phan_cong", detail=f"{n} dòng"))
    return n


@ghi("ads")
def luu_sale(rows: list[dict], nguoi: str) -> int:
    dam_bao_bang()
    n = 0
    with session_scope() as s:
        for r in rows:
            ten = str(r.get("ten") or "").strip()
            if not ten:
                continue
            x = s.get(AdsSale, ten) or AdsSale(ten=ten)
            acc = str(r.get("acc") or "").strip() or None
            if (x.acc or None) != acc:
                x.acc = acc
                s.add(x)
                n += 1
        s.add(AuditLog(username=nguoi, action="ads_sua_sale", detail=f"{n} sale"))
    return n


@ghi("ads")
def luu_thang(thang: str, rate: float | None, nguoi: str) -> None:
    """Lưu tỷ giá USD -> VNĐ của tháng."""
    dam_bao_bang()
    with session_scope() as s:
        if rate:
            x = s.get(AdsThang, thang) or AdsThang(thang=thang, ty_gia=rate)
            x.ty_gia = float(rate)
            s.add(x)
        s.add(AuditLog(username=nguoi, action="ads_cau_hinh_thang", detail=f"{thang}: tỷ giá {rate}"))


@ghi("ads")
def xoa_lead(ids: list[int], nguoi: str) -> int:
    dam_bao_bang()
    with session_scope() as s:
        n = 0
        for i in ids:
            x = s.get(AdsLead, int(i))
            if x:
                s.delete(x)
                n += 1
        s.add(AuditLog(username=nguoi, action="ads_xoa_lead", detail=f"{n} dòng"))
    return n


# ------------------------------------------------------------------ nạp file Google Sheet cũ
@ghi("ads")
def nap_file_sheet(noi_dung: bytes, nguoi: str) -> dict:
    """Nạp file 'BÁO CÁO CHI TIÊU ADS' (tải về từ Google Sheet) để có dữ liệu các tháng đã chạy trên sheet:
    - BẢNG TỔNG: danh mục page (tên, tên chuẩn, tình trạng); page tên có 'TRUNG LẬP' = tài khoản công ty;
    - mỗi trang tính page (dòng 3 có 'TÊN CAMP'): chi tiêu / tin nhắn từng camp, lead / PTTB, PIC từng dòng
      -> đổi thành phân công theo khoảng ngày.
    Nạp lại cùng file / cùng tháng không nhân đôi (chi tiêu ghi đè theo camp + ngày; lead / PTTB nạp từ file của
    các page, tháng đó được thay mới; phân công của tháng đó được dựng lại)."""
    import io

    from openpyxl import load_workbook
    dam_bao_bang()
    wb = load_workbook(io.BytesIO(noi_dung), data_only=True, read_only=True)
    wf = load_workbook(io.BytesIO(noi_dung), read_only=True)          # để biết ô nào là số gõ tay
    ten_hien, tinh_trang, tay, pic_tong = {}, {}, {}, {}
    if "BẢNG TỔNG" in wb.sheetnames:
        cong_thuc = [r for r in wf["BẢNG TỔNG"].iter_rows(min_row=4, values_only=True)]
        for k, r in enumerate(wb["BẢNG TỔNG"].iter_rows(min_row=4, values_only=True)):
            if not r or len(r) < 14 or not r[1]:
                continue
            ma = chuan_ma(r[2] or r[1])
            ten_hien[ma] = str(r[1]).strip()
            tt = str(r[13] or "").strip()
            tinh_trang[ma] = "Đang nuôi" if "nuôi" in tt.lower() else ("Tắt" if "tắt" in tt.lower() else "Đang chạy")
            goc = cong_thuc[k][3] if k < len(cong_thuc) and len(cong_thuc[k]) > 3 else None
            if isinstance(goc, (int, float)) and goc:                  # tổng tiền gõ tay (page không có số n8n)
                tay[ma] = float(goc)
            pic_tong[ma] = [str(x).strip() for x in r[8:11] if x and chuan_ma(x) != ma and "TRUNG LẬP" not in chuan_ma(x)]
    chi, lead, pic, loi, ty_le = [], {}, {}, [], {}
    for ws_f in wf.worksheets:            # tổng tiền của sale ghi '=E5*70%' -> page chia theo tỷ lệ, không đều
        if ws_f.title == "BẢNG TỔNG":
            continue
        r12 = list(ws_f.iter_rows(min_row=1, max_row=2, values_only=True))
        if len(r12) == 2:
            for ten_, ct in zip(r12[0][1:6], r12[1][1:6]):
                m = re.fullmatch(r"=\s*\$?E\$?5\s*\*\s*(\d+(?:[.,]\d+)?)\s*%", str(ct or "").strip())
                if ten_ and m:
                    ty_le.setdefault(chuan_ma(ws_f.title), {})[khoa_sale(ten_)] = float(m.group(1).replace(",", "."))
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(min_row=1, max_row=ws.max_row, values_only=True))
        if len(rows) < 6 or len(rows[2]) < 8 or str(rows[2][1] or "").strip().upper() != "TÊN CAMP":
            continue
        ma = chuan_ma(ws.title)
        hdr = [str(x or "").strip().upper() for x in rows[2]]
        cot_pic = [i for i, h in enumerate(hdr) if h.startswith("PIC")][:TOI_DA_PIC]
        for r in rows[5:]:
            d = doc_ngay(r[3] if len(r) > 3 else None)
            if not d:
                continue
            camp = str(r[1] or "").strip()
            if camp and r[4] not in (None, ""):
                chi.append({"page": ma, "camp": camp, "ngay": d, "tinh_trang": r[2], "chi_tieu": r[4],
                            "tin_nhan": r[5] or 0})
            l, p = int(doc_so(r[6])), int(doc_so(r[7]))
            if l or p:
                a = lead.setdefault((ma, d), [0, 0])
                a[0] += l
                a[1] += p
            ai = [str(r[i]).strip() for i in cot_pic if i < len(r) and r[i] and chuan_ma(r[i]) != ma
                  and "TRUNG LẬP" not in chuan_ma(r[i])]
            if ai:
                pic.setdefault(ma, {}).setdefault(d, [])
                for x in ai:
                    if khoa_sale(x) not in {khoa_sale(y) for y in pic[ma][d]}:
                        pic[ma][d].append(x)
    if not chi and not lead:
        raise LoiAds("Không thấy trang tính page nào (dòng 3 phải có cột 'TÊN CAMP'). Hãy dùng file báo cáo ads.")
    thang0 = sorted({x["ngay"] for x in chi} | {k[1] for k in lead})[0].replace(day=1)
    co_chi = {x["page"] for x in chi}
    for ma, tien in tay.items():                  # chi tiêu chỉ có ở BẢNG TỔNG -> một dòng nhập tay ngày 01
        if ma not in co_chi:
            chi.append({"page": ma, "camp": "Nhập tay (tổng tháng từ sheet)", "ngay": thang0,
                        "tinh_trang": "NHẬP TAY", "chi_tieu": tien, "tin_nhan": 0})
    for ma, ds in pic_tong.items():               # page không ghi PIC từng dòng -> lấy PIC ở BẢNG TỔNG cả tháng
        if ds and ma not in pic and (ma in co_chi or ma in tay or any(k[0] == ma for k in lead)):
            pic[ma] = {thang0: ds[:TOI_DA_PIC]}
    # tên sale: gộp cách viết khác nhau ('C.HỒNG' / 'C.Hồng') về cách viết gặp nhiều nhất
    dem: dict[str, dict[str, int]] = {}
    for ngay_ in pic.values():
        for ds in ngay_.values():
            for x in ds:
                dem.setdefault(khoa_sale(x), {}).setdefault(x, 0)
                dem[khoa_sale(x)][x] += 1
    ten_sale = {k: max(v, key=v.get) for k, v in dem.items()}
    kq_chi = nhan_chi_tieu(chi, nguon="import", nguoi=nguoi) if chi else {"moi": 0, "cap_nhat": 0, "page_moi": []}
    thang_file = sorted({d.strftime("%Y-%m") for d in [x["ngay"] for x in chi] + [k[1] for k in lead]})
    with session_scope() as s:
        pages = {}
        for ma in set(ten_hien) | {k[0] for k in lead} | set(pic) | {x["page"] for x in chi}:
            p = _page(s, ma, ten_hien=ten_hien.get(ma, ma.title()))
            if ma in ten_hien:
                p.ten = ten_hien[ma]
                p.tinh_trang = tinh_trang.get(ma, p.tinh_trang)
            pages[ma] = p
        for t in thang_file:
            dau = date.fromisoformat(f"{t}-01")
            cuoi = (dau + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            ids = [pages[m].id for m in {k[0] for k in lead if k[1].strftime('%Y-%m') == t}]
            if ids:
                s.execute(text("DELETE FROM ads_lead WHERE nguon = 'import' AND ngay >= :a AND ngay <= :b "
                               "AND page_id IN (" + ",".join(str(i) for i in ids) + ")"), {"a": dau, "b": cuoi})
        for (ma, d), (l, p) in lead.items():
            s.add(AdsLead(page_id=pages[ma].id, ngay=d, lead=l, pttb=p, nguon="import", nguoi=nguoi,
                          ghi_chu="Nạp từ file sheet"))
        so_pic = 0
        for ma, theo_ngay_ in pic.items():
            pid = pages[ma].id
            ngays = sorted(theo_ngay_)
            s.execute(text("DELETE FROM ads_pic WHERE page_id = :p AND tu_ngay >= :a AND tu_ngay <= :b"),
                      {"p": pid, "a": ngays[0], "b": ngays[-1]})
            # các ngày liền nhau có cùng nhóm sale -> một khoảng; khoảng cuối để mở (đang chạy tiếp)
            khoang, dau_k, nhom = [], ngays[0], None
            for i, d in enumerate(ngays):
                g = tuple(sorted(ten_sale[khoa_sale(x)] for x in theo_ngay_[d]))
                if nhom is None:
                    nhom = g
                elif g != nhom:
                    khoang.append((dau_k, ngays[i - 1], nhom))
                    dau_k, nhom = d, g
            khoang.append((dau_k, None, nhom))
            tl = ty_le.get(ma, {})
            for tu_, den_, g in khoang:
                dung_tl = all(khoa_sale(x) in tl for x in g)
                for sale in g:
                    s.add(AdsPic(page_id=pid, sale=sale, tu_ngay=tu_, den_ngay=den_,
                                 ty_le=tl[khoa_sale(sale)] if dung_tl else None))
                    so_pic += 1
        for ten_ in set(ten_sale.values()):
            if s.get(AdsSale, ten_) is None:
                s.add(AdsSale(ten=ten_, acc=GOI_Y_ACC.get(khoa_sale(ten_))))
        s.add(AuditLog(username=nguoi, action="ads_nap_file",
                       detail=f"{len(chi)} dòng chi tiêu, {len(lead)} ngày có lead/PTTB, {so_pic} phân công, "
                              f"tháng {', '.join(thang_file)}"))
    return {"chi_tieu": len(chi), "moi": kq_chi["moi"], "cap_nhat": kq_chi["cap_nhat"], "lead": len(lead),
            "pic": so_pic, "page": len(pages), "thang": thang_file, "loi": loi}


# Gợi ý acc cho tên gọi sale (đọc từ trang TRACKING IBB7 của sheet) - chỉ điền lần đầu, sửa được ở Cấu hình
GOI_Y_ACC = {khoa_sale(k): v for k, v in {
    "Rin": "DNG.RinND2", "Vy": "DNG.VyMTT2", "C. Tiên": "DNG.Tienvtc7", "C. Chi": "DNG.ChiHTM4",
    "K. Chi": "DNG.ChiLTK15", "Linh": "DNG.LinhPNA", "C. Hoàng": "DNG.HoangDTM3", "Sơn": "DNG.SonLQT",
    "C.Hồng": "DNG.HongDTA3", "Đ.Anh": "DNG.AnhTD63", "A.Thắng": "DNG.ThangBNA", "Kiều": "DNG.KieuMTT",
    "Khái": "DNG.KhaiPN10", "Toàn": "DNG.ToanHT11", "C. My": "DNG.Myltm", "A. Phúc": "DNG.Phucvhd"}.items()}


# ------------------------------------------------------------------ page: đổi tên, link fanpage
def chuan_link(v) -> str | None:
    """Link fanpage: bỏ khoảng trắng, thiếu http thì thêm https://; chỉ nhận link web."""
    s = str(v or "").strip()
    if not s:
        return None
    if not re.match(r"^https?://", s, re.I):
        s = "https://" + s.lstrip("/")
    if " " in s or "." not in s:
        raise LoiAds("Link fanpage không hợp lệ (VD: https://www.facebook.com/tenpage).")
    return s[:300]


@ghi("ads")
def sua_page(page_id: int, ten: str | None, link: str | None, tinh_trang: str | None, nguoi: str) -> str:
    """Đổi tên hiển thị / link fanpage / tình trạng của một page (tên chuẩn n8n gửi không đổi)."""
    dam_bao_bang()
    ten = re.sub(r"\s+", " ", str(ten or "")).strip()
    if not ten:
        raise LoiAds("Tên page không được để trống.")
    lk = chuan_link(link)
    with session_scope() as s:
        p = s.get(AdsPage, int(page_id))
        if p is None:
            raise LoiAds("Không tìm thấy page.")
        cu = p.ten
        if _khoa_ten(ten) != _khoa_ten(cu):
            _kiem_trung_ten(s, {p.id: ten})
        p.ten, p.link = ten[:120], lk
        if tinh_trang in TINH_TRANG_PAGE:
            p.tinh_trang = tinh_trang
        s.add(AuditLog(username=nguoi, action="ads_sua_page", detail=f"{p.ma}: '{cu}' -> '{p.ten}'"))
    return f"Đã lưu page {ten}."


# ------------------------------------------------------------------ nhận định hiệu quả page
NHOM_HQ = ["Hiệu quả cao", "Trung bình", "Kém", "Chưa đủ dữ liệu"]
CHI_TOI_THIEU = 10.0          # USD: chi dưới mức này mà chưa ra PTTB thì chưa kết luận


def nhom_hieu_qua(chi: float, pttb: float) -> str:
    if pttb > 0:
        cp = chi / pttb
        return NHOM_HQ[0] if cp <= NGUONG_TOT else NHOM_HQ[1] if cp <= NGUONG_BINH_THUONG else NHOM_HQ[2]
    return NHOM_HQ[2] if chi >= CHI_TOI_THIEU else NHOM_HQ[3]


def _tien(v) -> str:
    return "–" if v is None or pd.isna(v) else f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _ngay_du(dem: pd.Series) -> date | None:
    """Ngày gần nhất đã có chi tiêu của đa số page (>= nửa số page của ngày đông nhất trong 8 ngày cuối). Một page
    nhập tay trước ngày n8n gửi thì chưa tính là ngày đã có số."""
    dem = dem[dem > 0].sort_index()
    if dem.empty:
        return None
    moc = dem.tail(8).max() * 0.5
    return max(d for d, n in dem.items() if n >= moc)


def cuoi_tu_bang(df: pd.DataFrame) -> date | None:
    """`_ngay_du` từ bảng theo_ngay (page × ngày)."""
    if df is None or df.empty or not (df.chi_tieu > 0).any():
        return None
    return _ngay_du(df[df.chi_tieu > 0].groupby("ngay").page_id.nunique())


@nho("ads")
def ngay_cuoi_chi(tu: date, den: date) -> date | None:
    r = _q("""SELECT ngay, COUNT(DISTINCT page_id) AS n FROM ads_ngay WHERE ngay >= :tu AND ngay <= :den
              AND chi_tieu > 0 GROUP BY ngay""", tu=tu, den=den)
    if r.empty:
        return None
    r["ngay"] = pd.to_datetime(r["ngay"]).dt.date
    return _ngay_du(r.set_index("ngay").n)


# ------------------------------------------------------------------ tiền nhập tay tổng tháng, kiểm tra dữ liệu
@nho("ads")
def tien_tong_thang(tu: date, den: date) -> pd.DataFrame:
    """Chi tiêu cả tháng nạp từ BẢNG TỔNG của sheet (page không có số từng ngày) - ghi ở ngày 01 nên làm cột ngày 01 cao
    bất thường; biểu đồ theo ngày và dự kiến tách phần này ra."""
    df = _q("""SELECT n.page_id, p.ten, n.ngay, n.chi_tieu FROM ads_ngay n JOIN ads_page p ON p.id = n.page_id
                 WHERE n.camp = :c AND n.ngay >= :tu AND n.ngay <= :den""", c=CAMP_TONG_THANG, tu=tu, den=den)
    df["ngay"] = pd.to_datetime(df["ngay"]).dt.date
    return df


# Phần phân tích (nhận định, kiểm tra dữ liệu, chi tiết page / sale, báo cáo bot) ở app/ads_phan_tich.py - nạp lại
# vào đây để nơi khác vẫn gọi ads.nhan_dinh(...), ads.kiem_tra(...) như cũ.
from app.ads_phan_tich import (BO_DAU_TEN, bao_cao_bot, chi_tiet_page, chi_tiet_sale, kiem_tra,  # noqa: E402,F401
                               nhan_dinh, ten_gon, ten_gon_ds)
