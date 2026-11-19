"""Báo cáo đầu ngày của phòng kinh doanh (thay sheet "Mục tiêu và công việc đầu ngày").

Chốt với chủ app 24/09/2026:
- Sale nhập 7 ô: mục tiêu bán hôm nay, KHTN đang có, số bán thực hiện, dự kiến online sáng,
  dự kiến online chiều, đã online, ghi chú. PTTB luỹ kế tháng và số V.VIP app tự lấy từ file
  đã nạp, để luôn khớp Báo cáo phòng - không có hai nguồn số.
- "Thực hiện" (thêm 26/09/2026, cột `da_ban`) là số bán sale TỰ NHẬP, để đối chiếu thẳng với ô
  "MT ngày" của chính họ. Không lấy gì từ file - chủ app chốt đây là ô khai báo của sale.
- "Đã online" (đổi 06/10/2026) là ô sale TỰ GÕ như một ô Google Sheet, KHÔNG liên quan tới file Internet.
  Trước đó (25/09) hiển thị số lớn hơn giữa số gõ và số file; sale gõ 1 mà file ghi 4 thì ô nhảy 4,
  gõ lại vẫn 4, sale tưởng lỗi nhập liệu nên chủ app bỏ hẳn việc trộn. Chưa gõ thì tính 0.
- Mục tiêu tháng của từng người nhập ngay trong bảng này, lưu vào `target_monthly` với
  `doi_tuong = "NHAN_VIEN"` (mọi chỗ khác đều lọc `doi_tuong = 'PHONG'` nên không đụng nhau).
- Mục tiêu tháng của PHÒNG (chốt 02/10/2026) là ô RIÊNG của trang này: `doi_tuong = "PHONG"`,
  `chi_tieu = "bcn_thang"`. Không dùng chung chỉ tiêu Internet của Báo cáo Tổng, để BGĐ sửa mục tiêu
  ở đây không làm lệch số của các trang khác. Chưa đặt riêng thì tạm đọc chỉ tiêu Internet của phòng.
  Mục tiêu mỗi ngày mặc định chia đều mục tiêu tháng cho số ngày của tháng đó, nhưng BGĐ đặt tay được
  cho cả tháng (chốt 08/10/2026, `CHI_TIEU_NGAY`); để trống thì quay về tự chia.
- "Pay" trong ảnh báo cáo = số V.VIP luỹ kế tháng của người đó, đếm từ file FPT Play
  (`_vvip_theo_acc`) đúng như Báo cáo Tổng và Báo cáo phòng.
- Dự kiến online tổng = sáng + chiều (không nhập riêng); còn phải online = tổng dự kiến - đã online.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from sqlalchemy.exc import IntegrityError
from sqlalchemy import delete, select, text

from app import phan_tich as pt
from app.bo_nho import xoa
from app.db import engine, session_scope
from app.metrics import month_range
from app.models import AuditLog, BaoCaoNgay, BaoCaoNgayChu, Target
from app.thoi_gian import gio_viet_nam, utc_bay_gio

O_NHAP = ("muc_tieu", "khtn", "da_ban", "onl_sang", "onl_chieu", "da_online", "ghi_chu")
O_TU_CA = ("onl_sang", "onl_chieu", "da_online")      # ba ô này tự đếm từ ca ở Theo dõi Online (xem `che_do_onl`)
# cột thêm sau, phải tự vá vào database đang chạy: tên cột -> kiểu
COT_THEM = {"da_online": "INTEGER", "da_ban": "INTEGER"}
GHI_CHU_TOI_DA = 400
TOI_DA = 999                       # chặn gõ nhầm 9999
TRUOC_TOI_DA = 7                   # số ngày tương lai được phép nhập trước (chốt 26/09/2026)
_da_tao = False
PHONG_ONLINE = "ONLINE"            # "phòng" ảo của nhóm Phòng Online (app/phong_online.py): số nhập lưu với mã này, riêng hẳn IBB7


def _nguon(phong: list[str]) -> tuple[list[str], set[str] | None]:
    """(mã phòng THẬT để đọc file, acc được giữ lại). Phòng thường: (phong, None); nhóm Phòng Online: đọc IBB2 rồi chỉ giữ 5 người của nhóm."""
    if PHONG_ONLINE in phong:
        from app import phong_online as po
        return [po.phong_goc()], set(po.acc_nhom())
    return list(phong), None


class LoiBaoCao(ValueError):
    """Lỗi hiện thẳng cho người dùng (đã viết bằng tiếng Việt)."""


def dam_bao_bang() -> None:
    global _da_tao
    if not _da_tao:
        BaoCaoNgay.__table__.create(engine, checkfirst=True)
        BaoCaoNgayChu.__table__.create(engine, checkfirst=True)
        from sqlalchemy import inspect
        co = {c["name"] for c in inspect(engine).get_columns("bao_cao_ngay")}
        for ten, kieu in COT_THEM.items():
            if ten not in co:
                with engine.begin() as c:
                    c.execute(text(f"ALTER TABLE bao_cao_ngay ADD COLUMN {ten} {kieu}"))
        _da_tao = True


def hom_nay() -> date:
    return gio_viet_nam().date()


def onl_tu_ca_bat(phong: list[str] | None = None) -> bool:
    """Công tắc `rules.yml` → `bao_cao_ngay.onl_tu_ca`: tắt thì ba ô ONL sáng / chiều / Đã online luôn do sale gõ tay (xem `che_do_onl`).
    Nhóm Phòng Online có công tắc riêng `phong_online.onl_tu_ca` (chủ app mở 10/11/2026), độc lập với IBB7."""
    if phong and PHONG_ONLINE in phong:
        from app import phong_online as po
        return po.onl_tu_ca()
    return bool(cau_hinh().get("onl_tu_ca"))


def che_do_onl(ngay: date, phong: list[str] | None = None) -> str:
    """Ba ô ONL sáng / ONL chiều / Đã online lấy số từ đâu (chủ app chốt 13/10/2026, phương án A): sale thường nhập dự kiến cho ngày mai vào tối hôm trước,
    còn đến ngày đó thì số phải theo ca thật ở Theo dõi Online (xếp khung giờ + đổi tình trạng ở thẻ ca là số nhảy).
      "" = ngày CHƯA TỚI: sale gõ tay, ô nào cũng sửa được.
      "het" = HÔM NAY: cả phòng tự đếm từ ca (người chưa có ca thì 0), không gõ tay; số sale đã gõ tối hôm trước vẫn còn trong database để đối chiếu.
      "co_ca" = ngày ĐÃ QUA: người nào có ca thì tự đếm, người không có ca (ngày trước khi có mục Theo dõi Online) giữ số đã gõ và vẫn sửa được."""
    if not onl_tu_ca_bat(phong):
        return ""
    h = hom_nay()
    return "" if ngay > h else "het" if ngay == h else "co_ca"


def khtn_tu_lead_bat(phong: list[str] | None = None) -> bool:
    """KHTN của Phòng Online tự đếm từ Lead Online (chốt 19/11/2026, `rules.yml` → `phong_online.khtn_tu_lead`)
    thay vì sale gõ tay - ô bị khoá khi công tắc này bật. Chỉ áp cho mã ảo ONLINE, không áp IBB7."""
    if not phong or PHONG_ONLINE not in phong:
        return False
    from app import phong_online as po
    return po.khtn_tu_lead()


def khoa_onl(acc_norm: str, phong: list[str], ngay: date) -> bool:
    """True nếu ba ô tự đếm của người này trong ngày KHÔNG được gõ tay."""
    m = che_do_onl(ngay, phong)
    if not m:
        return False
    if m == "het":
        return True
    from app import online_ca as oc
    return acc_norm in oc.dem_theo_nguoi(phong, ngay)


def ngay_xa_nhat() -> date:
    """Ngày xa nhất được phép mở báo cáo. Sale hay điền trước cho hôm sau nên phải cho chọn ngày
    tương lai, nhưng chặn trong TRUOC_TOI_DA ngày để không ai gõ nhầm sang tháng khác."""
    return hom_nay() + timedelta(days=TRUOC_TOI_DA)


def cau_hinh() -> dict:
    from app.config import rules_config
    c = rules_config().get("bao_cao_ngay") or {}
    return {"phong": list(c.get("phong") or []), "giong_noi": list(c.get("giong_noi") or []), "onl_tu_ca": bool(c.get("onl_tu_ca"))}


# ------------------------------------------------------------------ mục tiêu (dùng lại target_monthly)
def _muc_tieu(thang: str, doi_tuong: str, ma: str, chi_tieu: str) -> float | None:
    with engine.connect() as c:
        return c.execute(text("""SELECT gia_tri FROM target_monthly WHERE thang = :t AND doi_tuong = :d
                                 AND ma_doi_tuong = :m AND chi_tieu = :k"""),
                         {"t": thang, "d": doi_tuong, "m": ma, "k": chi_tieu}).scalar()


def dat_muc_tieu(thang: str, doi_tuong: str, ma: str, chi_tieu: str, gia_tri: float, nguoi: str) -> None:
    """Ghi một ô mục tiêu. Dùng cho cả mục tiêu tháng từng người và mục tiêu PTTB/ngày của phòng."""
    if gia_tri < 0 or gia_tri > 100000:
        raise LoiBaoCao("Mục tiêu không hợp lệ.")
    with session_scope() as s:
        r = s.execute(select(Target).where(Target.thang == thang, Target.doi_tuong == doi_tuong,
                                           Target.ma_doi_tuong == ma, Target.chi_tieu == chi_tieu)
                      ).scalars().first()
        if r is None:
            r = Target(thang=thang, doi_tuong=doi_tuong, ma_doi_tuong=ma, chi_tieu=chi_tieu)
            s.add(r)
        r.gia_tri = float(gia_tri)
        s.add(AuditLog(username=nguoi, action="sua_muc_tieu",
                       detail=f"{thang} {doi_tuong} {ma} {chi_tieu} = {gia_tri:g}"))
    xoa("so_lieu")


CHI_TIEU_THANG = "bcn_thang"       # ô mục tiêu tháng riêng của Báo cáo ngày (không đụng chỉ tiêu chung)


def muc_tieu_thang(thang: str, phong: list[str]) -> int:
    """Mục tiêu PTTB tháng của phòng dùng cho Báo cáo ngày.

    Chưa đặt riêng thì tạm lấy chỉ tiêu Internet của phòng (chỉ ĐỌC, không ghi đè) để thẻ Luỹ kế
    tháng không trống trước khi BGĐ nhập lần đầu."""
    tong = 0
    for c in phong:
        v = _muc_tieu(thang, "PHONG", c, CHI_TIEU_THANG)
        if v is None and c == PHONG_ONLINE:        # chưa đặt riêng: cộng mục tiêu tháng từng người trong nhóm
            from app import phong_online as po
            mt = _mt_nhan_vien(thang)
            v = sum(float(mt.get(a, 0) or 0) for a in po.acc_nhom())
        elif v is None:
            v = _muc_tieu(thang, "PHONG", c, "internet")
        tong += int(v or 0)
    return tong


def muc_tieu_ngay(mt_thang: int, thang: str) -> int:
    """Mục tiêu mỗi ngày = mục tiêu tháng chia đều cho số ngày của tháng đó (chủ app chốt 02/10/2026).

    Làm tròn đến số gần nhất: 650 / 31 = 20,97 -> 21. Ai cũng nhân chia lại được bằng tay."""
    days = month_range(thang)[2]
    return int(mt_thang / days + 0.5) if days else 0


def dat_muc_tieu_thang(thang: str, phong_code: str, gia_tri: float, nguoi: str) -> None:
    dat_muc_tieu(thang, "PHONG", phong_code, CHI_TIEU_THANG, gia_tri, nguoi)


CHI_TIEU_NGAY = "bcn_ngay"         # mục tiêu mỗi ngày đặt tay cho cả tháng; không có thì tự chia


def muc_tieu_ngay_phong(thang: str, phong: list[str]) -> int:
    """Mục tiêu PTTB mỗi ngày của phòng trong tháng.

    BGĐ đặt tay được (chủ app chốt 08/10/2026: tháng 750 tự chia ra 24 mà muốn giao 25/ngày); phòng nào chưa
    đặt thì tự chia đều như `muc_tieu_ngay`. Trống hết thì giữ đúng cách cũ: chia tổng mục tiêu tháng."""
    rieng = {c: _muc_tieu(thang, "PHONG", c, CHI_TIEU_NGAY) for c in phong}
    if not any(rieng.values()):
        return muc_tieu_ngay(muc_tieu_thang(thang, phong), thang)
    return sum(int(rieng[c]) if rieng[c] else muc_tieu_ngay(muc_tieu_thang(thang, [c]), thang) for c in phong)


def muc_tieu_ngay_rieng(thang: str, phong_code: str) -> int | None:
    """Số BGĐ đã đặt tay cho một phòng; None là đang để tự chia."""
    v = _muc_tieu(thang, "PHONG", phong_code, CHI_TIEU_NGAY)
    return int(v) if v else None


def dat_muc_tieu_ngay_phong(thang: str, phong_code: str, gia_tri: float | None, nguoi: str) -> None:
    """Đặt mục tiêu mỗi ngày của phòng; để trống hoặc 0 là bỏ số đã đặt, quay về tự chia."""
    if gia_tri:
        return dat_muc_tieu(thang, "PHONG", phong_code, CHI_TIEU_NGAY, gia_tri, nguoi)
    with session_scope() as s:
        s.execute(delete(Target).where(Target.thang == thang, Target.doi_tuong == "PHONG",
                                       Target.ma_doi_tuong == phong_code, Target.chi_tieu == CHI_TIEU_NGAY))
        s.add(AuditLog(username=nguoi, action="sua_muc_tieu", detail=f"{thang} PHONG {phong_code} {CHI_TIEU_NGAY} = tự chia"))
    xoa("so_lieu")


def _mt_nhan_vien(thang: str) -> pd.Series:
    df = pd.read_sql_query(text("""SELECT ma_doi_tuong, gia_tri FROM target_monthly
                                   WHERE thang = :t AND doi_tuong = 'NHAN_VIEN' AND chi_tieu = 'internet'"""),
                           engine, params={"t": thang})
    return df.set_index("ma_doi_tuong").gia_tri if len(df) else pd.Series(dtype=float)


# ------------------------------------------------------------------ bảng của một ngày
def _da_nhap(ngay: date, phong: list[str]) -> pd.DataFrame:
    df = pd.read_sql_query(text("SELECT * FROM bao_cao_ngay WHERE ngay = :n"), engine,
                           params={"n": ngay.isoformat()})
    if df.empty:
        return pd.DataFrame(columns=["acc_norm", *O_NHAP])
    return df[df.phong_code.isin(set(phong))][["acc_norm", *O_NHAP]]


def _vvip_theo_acc(phong: list[str], tu: str, den: str) -> pd.Series:
    """Số V.VIP luỹ kế của từng người, đếm ĐÚNG cách Báo cáo Tổng và Báo cáo phòng đang đếm:
    mỗi dòng `la_vvip` trong file FPT Play là một V.VIP, tính theo ngày online của chính gói đó.

    Không đếm gián tiếp qua cờ V.VIP của hợp đồng Internet: gói V.VIP có thể online khác ngày với
    hợp đồng Internet, hoặc bán thêm trên hợp đồng của tháng trước, nên đếm kiểu đó sẽ lệch với
    Báo cáo phòng (đã đo trên IBB7 tháng 9: lệch 2 V.VIP, 4 người sai).
    """
    if not phong:
        return pd.Series(dtype=int)
    ma = {f"p{i}": c for i, c in enumerate(phong)}
    cho = ", ".join(f":{k}" for k in ma)
    df = pd.read_sql_query(text(f"""SELECT acc_norm, COUNT(*) AS n FROM fact_fptplay
                                    WHERE phong_code IN ({cho}) AND la_vvip = TRUE
                                      AND ngay_online >= :tu AND ngay_online <= :den
                                    GROUP BY acc_norm"""),
                           engine, params={**ma, "tu": tu, "den": den})
    return df.set_index("acc_norm")["n"] if not df.empty else pd.Series(dtype=int)


def _nhan_su_dang_lam(phong: list[str], dau: date, den: date) -> pd.DataFrame:
    """Nhân sự đang thuộc phòng theo danh mục (staff_map), lọc đúng hiệu lực trong kỳ - cùng cách
    Báo cáo phòng lấy roster (`bao_cao_phong.bang_nhan_su`). Đây phải là NGUỒN CHÍNH của danh sách,
    không phải suy ra từ "có bán hay chưa": lỗi thật 01/10/2026, nhân sự mới hoặc tháng này chưa bán
    gì (Mỹ Chi, Thanh Toàn, Gia Khánh, Trúc Duy) bị rớt hẳn khỏi bảng vì roster cũ chỉ lấy người có
    hợp đồng/báo cáo/V.VIP trong tháng.

    Loại người đã ghi "Nghỉ" trong danh mục (lỗi thật khác phát hiện ngay sau: Phan Tư Duy vẫn hiện
    dù đã nghỉ, vì ngày nghỉ không phải lúc nào cũng điền vào hiệu_luc_den) và trưởng phòng - cùng
    quy tắc "không vào bảng nhân viên" đang dùng ở Báo cáo Tổng (`overview._nhan_su`)."""
    if not phong:
        return pd.DataFrame(columns=["acc", "acc_norm", "ten_hien_thi"])
    from app.canh_bao import acc_truong_phong
    ma = {f"p{i}": c for i, c in enumerate(phong)}
    cho = ", ".join(f":{k}" for k in ma)
    sql = text(f"""SELECT acc, acc_norm, ten_hien_thi FROM staff_map WHERE phong_code IN ({cho})
                   AND (hieu_luc_den IS NULL OR hieu_luc_den >= :tu)
                   AND (hieu_luc_tu IS NULL OR hieu_luc_tu <= :den)
                   AND COALESCE(ghi_chu, '') NOT LIKE '%Ngh%'""")
    df = pd.read_sql_query(sql, engine, params={**ma, "tu": dau.isoformat(), "den": den.isoformat()})
    return df[~df.acc_norm.isin(acc_truong_phong())]


def bang(phong: list[str], ngay: date | None = None) -> pd.DataFrame:
    """Mỗi dòng một nhân sự của phòng: 6 ô sale nhập + các số app tự lấy.

    Danh sách người = toàn bộ nhân sự đang thuộc phòng theo danh mục (`_nhan_su_dang_lam`, lọc hiệu
    lực), cộng người có bán/báo cáo/V.VIP trong tháng nhưng không (còn) có trong danh mục - hiếm,
    phòng khi danh mục chưa cập nhật kịp. Không suy roster từ "có bán hay chưa" nữa (xem
    `_nhan_su_dang_lam`): nhờ vậy đầu tháng mới (chưa ai nạp file) hay nhân sự chưa bán gì trong
    tháng vẫn có dòng để nhập."""
    dam_bao_bang()
    ngay = ngay or hom_nay()
    thang = f"{ngay:%Y-%m}"
    dau, _, _ = month_range(thang)
    thuc, loc = _nguon(phong)
    hd = pt.hop_dong_online(dau.isoformat(), ngay.isoformat(), thuc)
    vvip = _vvip_theo_acc(thuc, dau.isoformat(), ngay.isoformat())
    nhap = _da_nhap(ngay, phong)
    staff = _nhan_su_dang_lam(thuc, dau, ngay)
    if loc is not None:
        hd, staff = hd[hd.acc_norm.isin(loc)], staff[staff.acc_norm.isin(loc)]
        vvip = vvip[vvip.index.isin(loc)]
    if hd.empty and staff.empty and nhap.empty and vvip.empty:
        return pd.DataFrame()

    g = (hd.groupby("acc_norm").agg(acc=("acc_nhan_vien", "first"), phong_code=("phong_code", "first"),
                                    pttb_thang=("hop_dong", "size"))
         if len(hd) else pd.DataFrame(columns=["acc", "phong_code", "pttb_thang"],
                                      index=pd.Index([], name="acc_norm")))
    df = g.reset_index()
    if loc is not None:
        df["phong_code"] = phong[0]
    # Nhân sự trong danh mục chưa bán gì trong tháng, hoặc người chỉ bán V.VIP/đã tự nhập (chưa có
    # hợp đồng Internet online), cũng phải có dòng - nếu không dòng TỔNG sẽ thiếu so với Báo cáo
    # phòng, và nhân sự đó không nhập báo cáo được (lỗi thật 01/10/2026).
    acc_cua_staff = staff.set_index("acc_norm").acc if len(staff) else pd.Series(dtype=str)
    thieu = (set(staff.acc_norm) | set(nhap.acc_norm) | set(vvip.index)) - set(df.acc_norm)
    if thieu:
        ds_thieu = sorted(thieu)
        them = pd.DataFrame({"acc_norm": ds_thieu,
                             "acc": [acc_cua_staff.get(a, a) for a in ds_thieu],
                             "phong_code": phong[0], "pttb_thang": 0})
        df = pd.concat([df, them], ignore_index=True)
    df["vvip_thang"] = df.acc_norm.map(vvip).fillna(0).astype(int)

    ten = pd.read_sql_query(text("SELECT acc_norm, ho_ten FROM dim_employee WHERE acc_norm IS NOT NULL"), engine)
    ten = ten.drop_duplicates("acc_norm").set_index("acc_norm").ho_ten
    # chưa có trong NSLĐ (dim_employee) thì dùng tên hiển thị tạm đặt trong danh mục, cuối cùng mới acc
    ten_tam = (staff.set_index("acc_norm").ten_hien_thi.replace("", None)
              if len(staff) else pd.Series(dtype=str))
    df["ho_ten"] = df.acc_norm.map(ten).fillna(df.acc_norm.map(ten_tam)).fillna(df.acc)
    df["mt_thang"] = df.acc_norm.map(_mt_nhan_vien(thang)).fillna(0).astype(int)
    df = df.merge(nhap, on="acc_norm", how="left")
    for c in ("muc_tieu", "khtn", "da_ban", "onl_sang", "onl_chieu"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    df["ghi_chu"] = df.ghi_chu.where(df.ghi_chu.notna(), "")
    # "Đã online" là ô sale TỰ GÕ như một ô Google Sheet, không lấy gì từ file Internet (chủ app chốt
    # 06/10/2026, thay quy tắc 25/09 "lấy số lớn hơn giữa số gõ và số file": sale gõ 1 mà file ghi 4 thì
    # ô nhảy 4, sale tưởng lỗi nhập liệu). Chưa gõ thì tính 0.
    df["thuc_hien"] = pd.to_numeric(df.get("da_online"), errors="coerce").fillna(0).astype(int)
    df["dk_toi_qua"] = df.onl_sang + df.onl_chieu                # số sale GÕ TAY (thường là tối hôm trước); hôm nay chỉ để đối chiếu với số ca đã xếp
    df["tu_ca"], df["chua_xep"] = False, 0
    che_do = che_do_onl(ngay, phong)
    if che_do:
        from app import online_ca as oc
        dem = oc.dem_theo_nguoi(phong, ngay)
        tu = df.acc_norm.isin(dem) if che_do == "co_ca" else pd.Series(True, index=df.index)
        for cot, khoa in (("onl_sang", "sang"), ("onl_chieu", "chieu"), ("thuc_hien", "da_onl")):
            df[cot] = [dem.get(a, {}).get(khoa, 0) if t else v for a, t, v in zip(df.acc_norm, tu, df[cot])]
        df["chua_xep"] = [dem.get(a, {}).get("chua", 0) for a in df.acc_norm]
        df["tu_ca"] = tu
    df["dk_onl"] = df.onl_sang + df.onl_chieu
    # KHÔNG kẹp ở 0: người online vượt dự kiến để số âm thì cộng dọc cột mới ra đúng
    # tổng dự kiến - tổng đã online (chủ app chốt 26/09/2026: mọi con số phải cộng được).
    df["con_phai_onl"] = df.dk_onl - df.thuc_hien
    df["da_nhap"] = df.acc_norm.isin(set(nhap.acc_norm))       # đã có bản ghi hôm nay hay chưa
    df["id"] = df.acc_norm
    df["khtn_tu_dong"] = khtn_tu_lead_bat(phong)                # KHTN tự đếm từ Lead Online, ô khoá (xem `luu`)
    cot = ["id", "acc_norm", "acc", "ho_ten", "phong_code", "muc_tieu", "khtn", "da_ban", "onl_sang",
           "onl_chieu", "dk_onl", "thuc_hien", "con_phai_onl", "pttb_thang", "mt_thang", "vvip_thang",
           "ghi_chu", "da_nhap", "tu_ca", "dk_toi_qua", "chua_xep", "khtn_tu_dong"]
    return df[cot].sort_values(["pttb_thang", "ho_ten"], ascending=[False, True]).reset_index(drop=True)


def tom_tat(phong: list[str], ngay: date | None = None) -> dict:
    """Ba khối số đầu ảnh báo cáo: kết quả hôm qua, tình hình sáng nay, luỹ kế tháng."""
    ngay = ngay or hom_nay()
    thang = f"{ngay:%Y-%m}"
    dau, _, _ = month_range(thang)
    df = bang(phong, ngay)
    thuc, loc = _nguon(phong)
    hd = pt.hop_dong_online(dau.isoformat(), ngay.isoformat(), thuc)
    if loc is not None:
        hd = hd[hd.acc_norm.isin(loc)]
    hqua = ngay - timedelta(days=1)
    onl_hqua = int((hd.ngay_online.dt.date == hqua).sum()) if len(hd) else 0
    mt_thang = muc_tieu_thang(thang, phong)
    mt_ngay = muc_tieu_ngay_phong(thang, phong)
    # Hôm qua có thể thuộc tháng trước (ngày 1) nên mục tiêu ngày của nó phải lấy theo tháng của chính nó.
    thang_hq = f"{hqua:%Y-%m}"
    mt_hq = mt_ngay if thang_hq == thang else muc_tieu_ngay_phong(thang_hq, phong)
    luy_ke = len(hd)
    s = (lambda c: int(df[c].sum())) if not df.empty else (lambda c: 0)
    return {
        "ngay": ngay, "hom_qua": hqua, "thang": thang,
        "hq_thuc_te": onl_hqua, "hq_muc_tieu": mt_hq,
        "hq_thieu": max(mt_hq - onl_hqua, 0), "hq_ty_le": round(onl_hqua / mt_hq * 100) if mt_hq else 0,
        "khtn": s("khtn"), "mt_ngay": mt_ngay, "mt_ngay_nhap": s("muc_tieu"), "da_ban": s("da_ban"),
        "onl_sang": s("onl_sang"), "onl_chieu": s("onl_chieu"), "dk_onl": s("dk_onl"),
        "da_online": s("thuc_hien"), "con_phai_onl": s("dk_onl") - s("thuc_hien"),
        "luy_ke": luy_ke, "mt_thang": mt_thang, "con_thieu": max(mt_thang - luy_ke, 0),
        "so_ngay_thang": month_range(thang)[2],
        "ty_le_thang": round(luy_ke / mt_thang * 100, 1) if mt_thang else 0.0,
        "vvip_thang": s("vvip_thang"),
        "so_nguoi": len(df), "chua_nhap": int((~df.da_nhap).sum()) if not df.empty else 0,
    }


# ------------------------------------------------------------------ ghi
def _so(v) -> int:
    try:
        n = int(float(v or 0))
    except (TypeError, ValueError):
        raise LoiBaoCao("Chỉ được nhập số.") from None
    if n < 0 or n > TOI_DA:
        raise LoiBaoCao(f"Số phải trong khoảng 0 - {TOI_DA}.")
    return n


def luu(acc_norm: str, truong: dict, phong: list[str], nguoi: str, ngay: date | None = None,
        ghi_ten: str | None = None) -> None:
    """Ghi phần sale nhập cho một người.

    Tài khoản sale dùng chung sửa được mọi dòng (chủ app chốt 24/09/2026); `ghi_ten` là tên người đang
    chọn ở ô "Tôi là", lưu vào "cập nhật bởi" để Trưởng phòng biết ai sửa - nhật ký vẫn ghi tài khoản thật."""
    dam_bao_bang()
    ngay = ngay or hom_nay()
    d = {}
    for k, v in truong.items():
        if k not in O_NHAP:
            continue
        d[k] = (str(v or "").strip()[:GHI_CHU_TOI_DA] or None) if k == "ghi_chu" else _so(v)
    if not d:
        return
    if any(k in O_TU_CA for k in d) and khoa_onl(acc_norm, phong, ngay):
        raise LoiBaoCao("ONL sáng / ONL chiều / Đã online của ngày này tự đếm từ ca ở mục Theo dõi Online bên dưới. "
                        "Xếp khung giờ và đổi tình trạng ở thẻ ca là số tự nhảy." if ngay == hom_nay() else
                        "Người này đã có ca ở mục Theo dõi Online nên ONL sáng / ONL chiều / Đã online tự đếm từ ca, không gõ tay được.")
    if "khtn" in d and khtn_tu_lead_bat(phong):
        raise LoiBaoCao("KHTN giờ tự đếm từ Lead Online (số lead đang mở), không gõ tay được nữa.")
    code = _phong_cua(acc_norm, phong)
    for lan in (1, 2):
        try:
            with session_scope() as s:
                r = s.execute(select(BaoCaoNgay).where(BaoCaoNgay.ngay == ngay,
                                                       BaoCaoNgay.acc_norm == acc_norm)).scalars().first()
                if r is None:
                    r = BaoCaoNgay(ngay=ngay, acc_norm=acc_norm, phong_code=code)
                    s.add(r)
                for k, v in d.items():
                    setattr(r, k, v)
                r.cap_nhat_luc, r.cap_nhat_boi = utc_bay_gio(), (ghi_ten or nguoi)[:60]
            return
        except IntegrityError:
            # Hai ô đầu tiên của cùng một người được lưu cùng lúc (Tab nhanh, hoặc hai máy chủ): cả hai thấy "chưa có dòng" và cùng chèn,
            # ràng buộc duy nhất chặn lần thứ hai nên ô đó MẤT. Đọc lại và cập nhật vào dòng đã có.
            if lan == 2:
                raise


def dong_bo_khtn() -> int:
    """Ghi KHTN hôm nay của Phòng Online = số lead đang mở của từng người trong Lead Online (chốt 19/11/2026).

    Cron gọi hàm này mỗi 15 phút (qua `POST /api/lead/canh-bao`, cùng lượt quét SLA lead) thay vì sale gõ
    tay: số của ngày hôm nay cứ thế được ghi đè liên tục, qua nửa đêm thì số cuối cùng trở thành lịch sử
    của ngày đó - bảng xu hướng `phong_online.khtn_theo_ngay` không cần sửa gì, vẫn đọc đúng cột `khtn`
    này. Không chạy gì khi công tắc `phong_online.khtn_tu_lead` đang tắt."""
    from app import phong_online as po
    if not po.khtn_tu_lead():
        return 0
    dam_bao_bang()
    from app import leads
    ngay = hom_nay()
    dem = leads.tai_dang_xu_ly()
    n = 0
    for acc_norm, so in dem.items():
        for lan in (1, 2):
            try:
                with session_scope() as s:
                    r = s.execute(select(BaoCaoNgay).where(BaoCaoNgay.ngay == ngay,
                                                           BaoCaoNgay.acc_norm == acc_norm)).scalars().first()
                    if r is None:
                        r = BaoCaoNgay(ngay=ngay, acc_norm=acc_norm, phong_code=PHONG_ONLINE)
                        s.add(r)
                    r.khtn = int(so)
                    r.cap_nhat_luc, r.cap_nhat_boi = utc_bay_gio(), "he_thong"
                n += 1
                break
            except IntegrityError:
                if lan == 2:
                    raise
    return n


def _phong_cua(acc_norm: str, phong: list[str]) -> str:
    with engine.connect() as c:
        code = c.execute(text("""SELECT phong_code FROM fact_internet WHERE acc_norm = :a
                                 AND phong_code IS NOT NULL ORDER BY ngay_online DESC LIMIT 1"""),
                         {"a": acc_norm}).scalar()
    return code if code in set(phong) else phong[0]


def moc_cap_nhat(phong: list[str], ngay: date | None = None) -> str:
    """Dấu vết lần sửa gần nhất của cả phòng trong ngày, để trang tự nạp lại khi người khác vừa gõ."""
    if not phong:
        return ""
    ngay = ngay or hom_nay()
    ma = {f"p{i}": c for i, c in enumerate(phong)}
    cho = ", ".join(f":{k}" for k in ma)
    with engine.connect() as c:
        r = c.execute(text(f"""SELECT COUNT(*), MAX(cap_nhat_luc) FROM bao_cao_ngay
                               WHERE ngay = :n AND phong_code IN ({cho})"""),
                      {**ma, "n": ngay.isoformat()}).one()
    moc = f"{r[0]}|{r[1] or ''}"
    if che_do_onl(ngay, phong):                                        # số tự đếm từ ca nên ca đổi là bảng phải nạp lại
        from app import online_ca as oc
        moc += "|" + oc.moc(phong, ngay)
    return moc


def chu(phong_code: str, ngay: date | None = None) -> dict:
    dam_bao_bang()
    ngay = ngay or hom_nay()
    with session_scope() as s:
        r = s.execute(select(BaoCaoNgayChu).where(BaoCaoNgayChu.ngay == ngay,
                                                  BaoCaoNgayChu.phong_code == phong_code)).scalars().first()
        return {"trong_tam": r.trong_tam or "", "nhan_dinh": r.nhan_dinh or "",
                "thong_diep": r.thong_diep or ""} if r else {"trong_tam": "", "nhan_dinh": "", "thong_diep": ""}


def luu_chu(phong_code: str, moi: dict, nguoi: str, ngay: date | None = None) -> None:
    dam_bao_bang()
    ngay = ngay or hom_nay()
    with session_scope() as s:
        r = s.execute(select(BaoCaoNgayChu).where(BaoCaoNgayChu.ngay == ngay,
                                                  BaoCaoNgayChu.phong_code == phong_code)).scalars().first()
        if r is None:
            r = BaoCaoNgayChu(ngay=ngay, phong_code=phong_code)
            s.add(r)
        for k in ("trong_tam", "nhan_dinh", "thong_diep"):
            if k in moi:
                setattr(r, k, (moi[k] or "").strip() or None)
        r.cap_nhat_luc, r.cap_nhat_boi = utc_bay_gio(), nguoi[:60]
