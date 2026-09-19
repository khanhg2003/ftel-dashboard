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

from app.db import engine, session_scope
from app.models import AdsKpi, AdsLead, AdsNgay, AdsPage, AdsPic, AdsSale, AdsThang, AuditLog, CaiDat

BANG = (AdsPage, AdsSale, AdsPic, AdsNgay, AdsLead, AdsThang, AdsKpi)
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
    return pd.read_sql(text(sql), engine, params=p)


def ds_page() -> pd.DataFrame:
    return _q("SELECT id, ma, ten, loai, tinh_trang, ghi_chu, link FROM ads_page ORDER BY ten")


def ds_pic() -> pd.DataFrame:
    df = _q("SELECT id, page_id, sale, tu_ngay, den_ngay, ty_le FROM ads_pic")
    for c in ("tu_ngay", "den_ngay"):
        df[c] = pd.to_datetime(df[c]).dt.date
    return df


def ds_sale() -> pd.DataFrame:
    return _q("SELECT ten, acc FROM ads_sale ORDER BY ten")


def ty_gia(thang: str) -> float:
    """Tỷ giá tháng; chưa nhập thì lấy tháng gần nhất trước đó, không có nữa thì mặc định."""
    df = _q("SELECT ty_gia FROM ads_thang WHERE thang <= :t ORDER BY thang DESC LIMIT 1", t=thang)
    return float(df.ty_gia.iloc[0]) if len(df) else TY_GIA_MAC_DINH


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


def tracking(thang: str, chi_so: str = "chi_tieu") -> tuple[pd.DataFrame, int]:
    """Bảng page × ngày trong tháng (như TRACKING NGÀY)."""
    from app.metrics import month_range
    dau, cuoi, so_ngay = month_range(thang)
    df = theo_ngay(dau, cuoi)
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


def luu_thang(thang: str, rate: float | None, kpi: dict[int, int | None], nguoi: str) -> None:
    dam_bao_bang()
    with session_scope() as s:
        if rate:
            x = s.get(AdsThang, thang) or AdsThang(thang=thang, ty_gia=rate)
            x.ty_gia = float(rate)
            s.add(x)
        for pid, v in kpi.items():
            x = s.execute(select(AdsKpi).where(AdsKpi.thang == thang, AdsKpi.page_id == pid)).scalars().first()
            if v in (None, "", 0):
                if x:
                    s.delete(x)
                continue
            if x is None:
                x = AdsKpi(thang=thang, page_id=pid, kpi_pttb=int(v))
                s.add(x)
            x.kpi_pttb = int(v)
        s.add(AuditLog(username=nguoi, action="ads_cau_hinh_thang", detail=f"{thang}: tỷ giá {rate}, {len(kpi)} KPI"))


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


def bao_cao_bot(tu: date, den: date) -> dict:
    """Báo cáo gửi về Telegram (thay Apps Script đọc sheet): lead / PTTB / chi tiêu từng page, page đang chạy chưa có số."""
    tp = theo_page(tu, den)
    co_so = tp[(tp.lead > 0) | (tp.pttb > 0)].sort_values(["pttb", "lead"], ascending=False)

    def so(x):
        return f"{x:,.2f}".rstrip("0").rstrip(".")

    dong = []
    for r in co_so.itertuples():
        t = f"📌 {r.ten}: {int(r.lead)} leads | {int(r.pttb)} PTTB"
        if r.chi_tieu > 0:
            t += f" | {so(r.chi_tieu)}$" + (f" ({so(r.cp_pttb)}$/PTTB)" if r.pttb else "")
        dong.append(t)
    chua = tp[(tp.lead == 0) & (tp.pttb == 0) & (tp.tinh_trang == "Đang chạy")].ten.tolist()
    ngay = tu.strftime("%d/%m/%Y") if tu == den else f"{tu:%d/%m/%Y} - {den:%d/%m/%Y}"
    chi = float(tp.chi_tieu.sum())
    return {"date": ngay, "details_text": "\n".join(dong) or "Chưa có lead / PTTB nào.",
            "total_leads": int(tp.lead.sum()), "total_pttb": int(tp.pttb.sum()), "total_spend": round(chi, 2),
            "ineffective_pages": chua,
            "ineffective_pages_text": ("\n\n⚠️ Page chưa hiệu quả: " + ", ".join(chua)) if chua
            else "\n\n✅ Tất cả page đang chạy đều có hiệu quả!"}


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


# ------------------------------------------------------------------ chi tiết một page (như trang tính từng page)
def chi_tiet_page(page_id: int, tu: date, den: date) -> dict:
    """Từng camp từng ngày, ngày tăng dần như trang tính của sheet: camp, tình trạng, ngày, chi tiêu, tin nhắn,
    số điện thoại, PTTB (ghi ở dòng đầu của ngày), PIC 1-3, tiền mỗi người. Kèm tổng tiền từng sale của page."""
    page_id = int(page_id)
    camp = _q("""SELECT ngay, camp, tinh_trang, chi_tieu, tin_nhan FROM ads_ngay
                 WHERE page_id = :p AND ngay >= :tu AND ngay <= :den ORDER BY ngay, camp""", p=page_id, tu=tu, den=den)
    ld = _q("""SELECT ngay, SUM(lead) AS lead, SUM(pttb) AS pttb FROM ads_lead
               WHERE page_id = :p AND ngay >= :tu AND ngay <= :den GROUP BY ngay""", p=page_id, tu=tu, den=den)
    for x in (camp, ld):
        x["ngay"] = pd.to_datetime(x["ngay"]).dt.date
    pg = ds_page().set_index("id")
    loai = pg.loai.get(page_id)
    pics = ds_pic()
    lead = {d: (float(a), float(b)) for d, a, b in zip(ld.ngay, ld["lead"], ld.pttb)}
    rows, so_pic = [], 1 if loai == "cong_ty" else 0
    for d in sorted(set(camp.ngay) | set(lead)):
        pc = [] if loai == "cong_ty" else phan_chia(pics, page_id, d)
        so_pic = max(so_pic, len(pc))
        deu = len({round(t, 3) for _, t in pc}) <= 1
        cs = camp[camp.ngay == d]
        ds_dong = list(cs.itertuples()) or [None]
        for j, r in enumerate(ds_dong):
            chi = float(r.chi_tieu) if r is not None else 0.0
            dong = {"ngay": d.strftime("%d/%m/%Y"), "camp": r.camp if r is not None else "",
                    "tinh_trang": (r.tinh_trang or "") if r is not None else "",
                    "chi_tieu": round(chi, 2) if r is not None else None,
                    "tin_nhan": int(r.tin_nhan or 0) if r is not None else None,
                    "lead": (lead.get(d, (0, 0))[0] or None) if j == 0 else None,
                    "pttb": (lead.get(d, (0, 0))[1] or None) if j == 0 else None}
            for k, (sale, _t) in enumerate(pc[:TOI_DA_PIC], start=1):
                dong[f"pic{k}"] = sale
            if loai == "cong_ty":
                dong["pic1"] = CONG_TY
            if r is not None and pc:
                dong["tien_nguoi"] = _tien(chi / len(pc)) if deu else \
                    " · ".join(f"{s_} {_tien(chi * t)}" for s_, t in pc)
            rows.append(dong)
    pb = phan_bo(tu, den)
    pb = pb[pb.page_id == page_id] if len(pb) else pb
    tong_sale = [(s_, round(float(v), 2)) for s_, v in
                 pb.groupby("sale").chi_tieu.sum().sort_values(ascending=False).items()] if len(pb) else []
    t = {"chi_tieu": float(camp.chi_tieu.sum()), "tin_nhan": float(camp.tin_nhan.sum()),
         "lead": float(ld["lead"].sum()), "pttb": float(ld.pttb.sum())}
    info = pg.loc[page_id] if page_id in pg.index else None
    return {"rows": rows, "so_pic": so_pic, "tong_sale": tong_sale, "tong": t,
            "ten": info.ten if info is not None else "", "ma": info.ma if info is not None else "",
            "link": (info.link if isinstance(info.link, str) else None) if info is not None else None,
            "tinh_trang": info.tinh_trang if info is not None else None}


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


def ngay_cuoi_chi(tu: date, den: date) -> date | None:
    r = _q("""SELECT ngay, COUNT(DISTINCT page_id) AS n FROM ads_ngay WHERE ngay >= :tu AND ngay <= :den
              AND chi_tieu > 0 GROUP BY ngay""", tu=tu, den=den)
    if r.empty:
        return None
    r["ngay"] = pd.to_datetime(r["ngay"]).dt.date
    return _ngay_du(r.set_index("ngay").n)


def nhan_dinh(tu: date, den: date) -> dict:
    """Nhận định page cho quản lý: nhóm hiệu quả, xu hướng 7 ngày, điểm nghẽn phễu (tin nhắn → số → PTTB), page chạy
    nhiều ngày liền chưa ra PTTB, gợi ý dời ngân sách. Chỉ tính tới ngày đã có chi tiêu (chi tiêu về trễ 1 ngày) để
    tiền và PTTB cùng khoảng."""
    cuoi = ngay_cuoi_chi(tu, den) or den
    tp = theo_page(tu, cuoi)
    tp = tp[(tp.chi_tieu > 0) | (tp.pttb > 0)].copy()
    rong = {"den": cuoi, "page": pd.DataFrame(), "the": [], "xu_huong": pd.DataFrame(), "pheu": pd.DataFrame(),
            "chuoi": pd.DataFrame(), "cp_tb": None, "tl_so": None, "tl_chot": None}
    if tp.empty:
        return rong
    tp["nhom"] = [nhom_hieu_qua(c, p) for c, p in zip(tp.chi_tieu, tp.pttb)]
    tong_chi, tong_pttb = float(tp.chi_tieu.sum()), float(tp.pttb.sum())
    tp["ty_trong_chi"] = (tp.chi_tieu / tong_chi * 100).round(1) if tong_chi else 0.0
    tp["ty_trong_pttb"] = (tp.pttb / tong_pttb * 100).round(1) if tong_pttb else 0.0
    cp_tb = tong_chi / tong_pttb if tong_pttb else None

    # xu hướng: 7 ngày gần nhất so với 7 ngày trước đó
    a = cuoi - timedelta(days=6)
    df = theo_ngay(cuoi - timedelta(days=13), cuoi)
    xu = pd.DataFrame()
    if len(df):
        df["ky"] = ["nay" if x >= a else "truoc" for x in df.ngay]
        g = df.groupby(["page_id", "ky"])[["chi_tieu", "pttb", "lead"]].sum().unstack("ky").fillna(0)
        g.columns = [f"{c}_{k}" for c, k in g.columns]
        for c in ("chi_tieu_nay", "chi_tieu_truoc", "pttb_nay", "pttb_truoc", "lead_nay", "lead_truoc"):
            if c not in g:
                g[c] = 0.0
        g["cp_nay"] = (g.chi_tieu_nay / g.pttb_nay.where(g.pttb_nay > 0)).round(2)
        g["cp_truoc"] = (g.chi_tieu_truoc / g.pttb_truoc.where(g.pttb_truoc > 0)).round(2)
        g["doi_cp"] = ((g.cp_nay - g.cp_truoc) / g.cp_truoc * 100).round(0)
        g["ten"] = ds_page().set_index("id").ten.reindex(g.index).values
        xu = g[(g.chi_tieu_nay >= 5) | (g.chi_tieu_truoc >= 5)].reset_index()

    # phễu: tin nhắn -> số điện thoại -> PTTB
    ph = tp[["page_id", "ten", "tin_nhan", "lead", "pttb", "chi_tieu"]].copy()
    ph["tl_so"] = (ph.lead / ph.tin_nhan.where(ph.tin_nhan > 0) * 100).round(0)
    ph["tl_chot"] = (ph.pttb / ph.lead.where(ph.lead > 0) * 100).round(0)
    tong_tn, tong_lead = float(ph.tin_nhan.sum()), float(ph.lead.sum())
    tl_so = tong_lead / tong_tn * 100 if tong_tn else None
    tl_chot = tong_pttb / tong_lead * 100 if tong_lead else None

    def van_de(r):
        if tl_so and r.tin_nhan >= 20 and (0 if pd.isna(r.tl_so) else r.tl_so) < tl_so * 0.5:
            return "Nhiều tin nhắn, ít số điện thoại"
        if tl_chot and r.lead >= 5 and (0 if pd.isna(r.tl_chot) else r.tl_chot) < tl_chot * 0.5:
            return "Có số nhưng chốt được ít"
        return ""
    ph["van_de"] = [van_de(r) for r in ph.itertuples()]

    # chuỗi ngày liền (tính lùi từ ngày cuối) có chi tiêu mà chưa ra PTTB
    d30 = theo_ngay(max(tu, cuoi - timedelta(days=30)), cuoi)
    chuoi = []
    if len(d30):
        for pid, g in d30.groupby("page_id"):
            g = g.groupby("ngay").agg(chi_tieu=("chi_tieu", "sum"), pttb=("pttb", "sum"), ten=("ten", "first"))
            n, tien, d = 0, 0.0, cuoi
            while d in g.index and g.loc[d, "chi_tieu"] > 0 and g.loc[d, "pttb"] == 0:
                n, tien, d = n + 1, tien + float(g.loc[d, "chi_tieu"]), d - timedelta(days=1)
            if n >= 3:
                chuoi.append({"page_id": pid, "ten": g.ten.iloc[0], "so_ngay": n, "tien": round(tien, 2)})
    chuoi = pd.DataFrame(chuoi, columns=["page_id", "ten", "so_ngay", "tien"]).sort_values("tien", ascending=False)

    # thẻ nhận định: mỗi thẻ = con số chính + biểu đồ nhỏ + một câu việc cần làm
    the = []
    kem, tot = tp[tp.nhom == "Kém"], tp[tp.nhom == "Hiệu quả cao"]

    def bar(df, cot, chu, vach=None, ten_vach=None, mau=None):
        return {"kieu": "bar", "nhan": ten_gon_ds(df.ten), "gia_tri": [float(x) for x in df[cot]],
                "chu": list(chu), "vach": vach, "ten_vach": ten_vach, "mau": mau}

    if len(kem):
        ct = kem.chi_tieu.sum() / tong_chi * 100
        pt = kem.pttb.sum() / tong_pttb * 100 if tong_pttb else 0
        x = kem.assign(_cp=kem.cp_pttb.fillna(kem.chi_tieu)).nlargest(5, "chi_tieu")
        the.append({"muc": "bad", "tieu_de": f"{len(kem)} page chi phí/PTTB cao",
                    "so": f"{ct:.0f}% ngân sách → {pt:.0f}% PTTB",
                    "bd": bar(x, "_cp", [f"{_tien(c)}$/PTTB" if p else f"{_tien(t)}$, chưa có PTTB"
                                         for c, p, t in zip(x.cp_pttb, x.pttb, x.chi_tieu)],
                              NGUONG_TOT, f"mức tốt {NGUONG_TOT:.0f}$", "#D64534"),
                    "noi_dung": "Xem lại nội dung camp, tệp khách; không cải thiện sau 3-5 ngày thì giảm ngân sách."})
    if len(chuoi):
        x = chuoi.head(5)
        the.append({"muc": "bad", "tieu_de": "Chạy liền nhiều ngày chưa ra PTTB",
                    "so": f"{len(chuoi)} page · {_tien(chuoi.tien.sum())}$ chưa ra PTTB",
                    "bd": bar(x, "so_ngay", [f"{n} ngày · {_tien(t)}$" for n, t in zip(x.so_ngay, x.tien)],
                              mau="#D64534"),
                    "noi_dung": "Kiểm tra camp có đúng tệp khách, tin nhắn có được trả lời kịp; cân nhắc tạm dừng."})
    if len(xu):
        xau = xu[(xu.doi_cp >= 30) & (xu.pttb_nay > 0) & (xu.pttb_truoc >= 2)].sort_values("doi_cp", ascending=False)
        tot_len = xu[(xu.doi_cp <= -30) & (xu.pttb_nay >= 2)].sort_values("doi_cp")
        if len(xau):
            x = xau.head(4)
            the.append({"muc": "warn", "tieu_de": "Chi phí/PTTB tăng mạnh (7 ngày gần nhất)",
                        "so": f"{len(xau)} page đắt lên từ 30%",
                        "bd": {"kieu": "doi", "nhan": ten_gon_ds(x.ten), "truoc": list(x.cp_truoc),
                               "sau": list(x.cp_nay), "xau": True},
                        "noi_dung": "Thường do quảng cáo cũ đã mỏi hoặc tệp khách bão hoà: đổi hình / nội dung mới."})
        if len(tot_len):
            x = tot_len.head(4)
            the.append({"muc": "ok", "tieu_de": "Đang tốt lên so với 7 ngày trước",
                        "so": f"{len(tot_len)} page rẻ đi từ 30%",
                        "bd": {"kieu": "doi", "nhan": ten_gon_ds(x.ten), "truoc": list(x.cp_truoc),
                               "sau": list(x.cp_nay), "xau": False},
                        "noi_dung": "Ghi lại camp / nội dung đang chạy ở các page này để nhân rộng."})
    so = ph[ph.van_de == "Nhiều tin nhắn, ít số điện thoại"]
    chot = ph[ph.van_de == "Có số nhưng chốt được ít"]
    if len(so):
        x = so.head(5)
        the.append({"muc": "warn", "tieu_de": "Nhiều tin nhắn nhưng ít xin được số",
                    "so": f"{len(so)} page dưới nửa mức chung {tl_so:.0f}%",
                    "bd": bar(x, "tl_so", [f"{v:.0f}% ({int(t)} tin → {int(l)} số)"
                                           for v, t, l in zip(x.tl_so.fillna(0), x.tin_nhan, x.lead)],
                              tl_so, f"mức chung {tl_so:.0f}%", "#E3A008"),
                    "noi_dung": "Xem lại kịch bản trả lời và tốc độ phản hồi tin nhắn."})
    if len(chot):
        x = chot.head(5)
        the.append({"muc": "warn", "tieu_de": "Có số điện thoại nhưng chốt PTTB thấp",
                    "so": f"{len(chot)} page dưới nửa mức chung {tl_chot:.0f}%",
                    "bd": bar(x, "tl_chot", [f"{v:.0f}% ({int(l)} số → {int(p)} PTTB)"
                                             for v, l, p in zip(x.tl_chot.fillna(0), x.lead, x.pttb)],
                              tl_chot, f"mức chung {tl_chot:.0f}%", "#E3A008"),
                    "noi_dung": "Sale gọi lại sớm trong ngày, bám khách chưa chốt."})
    if len(tot):
        x = tot.nsmallest(5, "cp_pttb")
        the.append({"muc": "ok", "tieu_de": f"{len(tot)} page hiệu quả cao",
                    "so": f"≤ {NGUONG_TOT:.0f}$/PTTB · {tot.pttb.sum() / tong_pttb * 100:.0f}% tổng PTTB"
                    if tong_pttb else f"≤ {NGUONG_TOT:.0f}$/PTTB",
                    "bd": bar(x, "cp_pttb", [f"{_tien(c)}$/PTTB · {int(p)} PTTB" for c, p in zip(x.cp_pttb, x.pttb)],
                              NGUONG_TOT, f"mức tốt {NGUONG_TOT:.0f}$", "#1E9E5A"),
                    "noi_dung": "Tăng ngân sách từ từ (10-20% mỗi lần), theo dõi chi phí/PTTB có giữ được không."})
    if len(kem) and len(tot) and tot.pttb.sum():
        ngay_chay = max((cuoi - tu).days + 1, 1)
        so_ngay_thang = calendar.monthrange(tu.year, tu.month)[1]
        doi = kem.chi_tieu.sum() / ngay_chay * 0.3
        cp_tot = tot.chi_tieu.sum() / tot.pttb.sum()
        cp_kem = kem.chi_tieu.sum() / kem.pttb.sum() if kem.pttb.sum() else None
        them = (doi / cp_tot - (doi / cp_kem if cp_kem else 0)) * so_ngay_thang
        hien = tong_pttb / ngay_chay * so_ngay_thang
        if them > 0:
            the.append({"muc": "info", "tieu_de": "Gợi ý dời ngân sách",
                        "so": f"+{them:.0f} PTTB/tháng (ước tính)",
                        "bd": {"kieu": "cot", "nhan": ["Giữ như hiện tại", "Dời 30% nhóm Kém"],
                               "gia_tri": [round(hien), round(hien + them)],
                               "chu": [f"{hien:.0f} PTTB", f"{hien + them:.0f} PTTB"]},
                        "noi_dung": f"Chuyển khoảng {_tien(doi)}$/ngày từ nhóm Kém sang nhóm hiệu quả cao (đang "
                                    f"{_tien(cp_tot)}$/PTTB). Hiệu quả thường giảm dần khi tăng ngân sách."})
    return {**rong, "page": tp, "the": the, "xu_huong": xu, "pheu": ph, "chuoi": chuoi,
            "cp_tb": cp_tb, "tl_so": tl_so, "tl_chot": tl_chot}


BO_DAU_TEN = ("LẮP MẠNG WIFI FPT ", "LẮP MẠNG WIFI ", "LẮP WIFI FPT ", "LẮP WIFI ", "LẮP ĐẶT WIFI ", "LẮP INTERNET ",
              "LẮP MẠNG FPT ", "FPT TELECOM - ", "FPT TELECOM ", "PAGE ")


def ten_gon(ten, toi_da: int = 24) -> str:
    """Tên ngắn cho biểu đồ: bỏ tiền tố quảng cáo ('Lắp WIFI FPT Kon Tum' -> 'Kon Tum'), cắt nếu còn dài."""
    s = str(ten or "").strip()
    for d in BO_DAU_TEN:
        if s.upper().startswith(d) and len(s) > len(d) + 2:
            s = s[len(d):]
            break
    return s if len(s) <= toi_da else s[:toi_da - 1].rstrip() + "…"



def ten_gon_ds(ds) -> list[str]:
    """Tên ngắn cho biểu đồ. Chỉ rút gọn khi tên ngắn không trùng với page nào khác (VD đã có page 'Huế' thì 'Lắp Mạng
    WIFI Huế' giữ nguyên) - tránh gộp nhầm hai page vào một thanh hoặc đọc nhầm page."""
    ds = [str(x or "") for x in ds]
    tat_ca = [str(x) for x in ds_page().ten] + ds
    gon_all = {}
    for x in dict.fromkeys(tat_ca):
        gon_all.setdefault(ten_gon(x).upper(), set()).add(x)
    out = []
    for x in ds:
        g = ten_gon(x)
        out.append(g if len(gon_all[g.upper()]) == 1 else (x if len(x) <= 40 else x[:39] + "…"))
    return out


# ------------------------------------------------------------------ tiền nhập tay tổng tháng, kiểm tra dữ liệu
def tien_tong_thang(tu: date, den: date) -> pd.DataFrame:
    """Chi tiêu cả tháng nạp từ BẢNG TỔNG của sheet (page không có số từng ngày) - ghi ở ngày 01 nên làm cột ngày 01 cao
    bất thường; biểu đồ theo ngày và dự kiến tách phần này ra."""
    df = _q("""SELECT n.page_id, p.ten, n.ngay, n.chi_tieu FROM ads_ngay n JOIN ads_page p ON p.id = n.page_id
                 WHERE n.camp = :c AND n.ngay >= :tu AND n.ngay <= :den""", c=CAMP_TONG_THANG, tu=tu, den=den)
    df["ngay"] = pd.to_datetime(df["ngay"]).dt.date
    return df


def kiem_tra(tu: date, den: date, hom_nay: date) -> list[tuple[str, str]]:
    """Những chỗ số liệu có thể thiếu / sai để người quản trị xử lý: [(mức 'bad' | 'warn' | 'info', câu)]."""
    ds = []
    df = theo_ngay(tu, den)
    cuoi = cuoi_tu_bang(df)
    hom_qua = hom_nay - timedelta(days=1)
    if tu <= hom_qua <= den and (cuoi is None or cuoi < hom_qua - timedelta(days=1)):
        ds.append(("bad", (f"Chi tiêu mới có đến {cuoi:%d/%m}" if cuoi else "Tháng này chưa có chi tiêu nào")
                   + " - kiểm tra workflow n8n (bình thường 7h sáng đã có số của hôm qua)."))
    if cuoi is not None:
        gan = df[(df.ngay > cuoi - timedelta(days=3)) & (df.ngay < cuoi) & (df.chi_tieu > 0)]
        co_cuoi = set(df[(df.ngay == cuoi) & (df.chi_tieu > 0)].page_id)
        thieu = gan[~gan.page_id.isin(co_cuoi) & (gan.tinh_trang == "Đang chạy")].ten.dropna().unique().tolist()
        som = df[(df.ngay > cuoi) & (df.chi_tieu > 0)]
        if len(som):
            ds.append(("info", f"{', '.join(sorted(som.ten.dropna().unique()))} đã có chi tiêu sau {cuoi:%d/%m} (nhập tay"
                               f" / gửi sớm) - các page khác chưa có nên số chung vẫn tính tới {cuoi:%d/%m}."))
        if thieu:
            ds.append(("warn", f"{len(thieu)} page đang chạy mà ngày {cuoi:%d/%m} không có chi tiêu: {', '.join(thieu)} - "
                               "đã tắt camp thì đổi tình trạng page, còn chạy thì kiểm tra n8n."))
    pb = phan_bo(tu, den)
    if len(pb):
        cpc = pb[pb.sale == CHUA_PHAN_CONG]
        if len(cpc) and cpc.chi_tieu.sum() > 0:
            ten = ds_page().set_index("id").ten
            ds.append(("warn", f"{_tien(cpc.chi_tieu.sum())}$ chưa chia cho sale nào (page chưa khai người chạy: "
                               f"{', '.join(sorted({str(ten.get(i, i)) for i in cpc.page_id}))}) - khai ở Cấu hình → "
                               "Người chạy page."))
    if len(df):
        g = df.groupby(["page_id", "ten"])[["chi_tieu", "lead", "pttb"]].sum().reset_index()
        la = g[(g.chi_tieu == 0) & ((g.lead > 0) | (g.pttb > 0))]
        if len(la):
            ds.append(("warn", f"Có lead / PTTB nhưng cả tháng không có chi tiêu: {', '.join(la.ten.astype(str))} - "
                               "thường do gõ sai tên page khi báo qua bot (app tự tạo page mới). Xoá dòng sai ở Nhật ký."))
        vuot = g[g.pttb > g.lead]
        if len(vuot):
            ds.append(("info", f"PTTB nhiều hơn số điện thoại ở: {', '.join(vuot.ten.astype(str))} - kiểm tra lại lần báo."))
    tay = tien_tong_thang(tu, den)
    if len(tay):
        ds.append(("info", f"{_tien(tay.chi_tieu.sum())}$ là tiền nhập tay tổng tháng ({', '.join(tay.ten.astype(str))})"
                           " - không có số từng ngày nên không vẽ vào biểu đồ theo ngày và không tính vào dự kiến."))
    thang = f"{tu.year}-{tu.month:02d}"
    if _q("SELECT COUNT(*) AS n FROM ads_thang WHERE thang = :t", t=thang).n.iloc[0] == 0:
        ds.append(("info", f"Chưa lưu tỷ giá tháng {tu.month:02d}/{tu.year} - VNĐ đang đổi theo {ty_gia(thang):,.0f}"
                   .replace(",", ".") + " (tab Theo sale → Lưu tỷ giá)."))
    return ds


def chi_tiet_sale(sale: str, tu: date, den: date) -> pd.DataFrame:
    """Các page một sale được chia tiền: số ngày chạy, tiền được chia, phần của sale trong tiền page, người chạy cùng."""
    pb = phan_bo(tu, den)
    if pb.empty:
        return pd.DataFrame()
    x = pb[pb.sale == sale]
    if x.empty:
        return pd.DataFrame()
    tong_page = pb.groupby("page_id").chi_tieu.sum()
    co = x[x.chi_tieu > 0]
    g = co.groupby("page_id").agg(chi_tieu=("chi_tieu", "sum"), so_ngay=("ngay", "nunique"),
                                  tu=("ngay", "min"), den=("ngay", "max")).reset_index()
    if g.empty:
        return pd.DataFrame()
    g["phan"] = (g.chi_tieu / g.page_id.map(tong_page) * 100).round(0)
    cung = pb[pb.page_id.isin(g.page_id) & (pb.sale != sale)].groupby("page_id").sale \
        .agg(lambda v: ", ".join(sorted(set(v))))
    g["cung"] = g.page_id.map(cung).fillna("")
    g["ten"] = g.page_id.map(ds_page().set_index("id").ten)
    g["tu"] = [f"{d:%d/%m}" for d in g.tu]
    g["den"] = [f"{d:%d/%m}" for d in g.den]
    return g.sort_values("chi_tieu", ascending=False).reset_index(drop=True)
