"""Chẩn đoán NGUYÊN NHÂN online của một phòng (hoặc cả phạm vi) tăng / giảm so với cùng kỳ tháng trước.

Fox không tự dò bảng rồi đoán: app TÁCH SẴN mức chênh lệch thành các phần cộng lại đúng bằng mức chênh, mỗi
phần có số và có tên người (khi người hỏi được xem nhân sự). Fox chỉ xếp theo mức ảnh hưởng và diễn giải.

Bốn cách tách (mỗi cách cộng lại bằng đúng mức chênh lệch online):
1. Theo NGƯỜI: người tăng, người giảm, người hết số (nghỉ / chuyển phòng / còn trong phòng nhưng không có
   số), người mới có số.
2. Theo NGUỒN hợp đồng: hợp đồng ký TRƯỚC đầu tháng rồi online trong kỳ (hàng chờ từ tháng trước) và hợp đồng
   ký VÀ online ngay trong tháng.
3. Theo TUẦN trong tháng: chênh lệch mở ra ở tuần nào.
4. Đầu vào - đầu ra: số bán mới (hợp đồng ký) và số tồn, để biết nghẽn ở khâu bán hay khâu triển khai.
Trưởng phòng và người đã nghỉ vẫn nằm trong số tổng nhưng không bị nêu tên.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import text

from app import canh_bao as cb
from app import fox_insight as fi
from app import phan_tich as pt
from app.db import engine
from app.du_bao import du_bao_thang
from app.metrics import daily_counts, month_range, prev_month, tong_theo_acc
from app.org import phong_order

TOI_DA_TEN = 4            # số người nêu tên trong mỗi nhóm
NGUONG_DANG_KE = 3        # nhóm lệch dưới chừng này online thì coi như không đáng kể


def _so(v) -> str:
    return f"{int(round(v)):,}".replace(",", ".")


def _d(v) -> str:
    """Số có dấu: +12 / -5 / 0."""
    v = int(round(v))
    return f"{v:+d}" if v else "0"


def _pham_vi(user, code: str | None) -> tuple[list[str], str]:
    """(các mã phòng xét, tên gọi). Không có `code` = mọi phòng người hỏi được xem, trừ phòng không cộng tổng."""
    from app.overview import phong_khong_cong_tong
    from app.tro_ly import LoiAI
    pv = user.phong_duoc_xem()
    ten = {p["code"]: p["ten"] for p in phong_order()}
    if code:
        if code not in ten:
            raise LoiAI("Không có phòng này trong danh sách.")
        if pv is not None and code not in pv:
            raise LoiAI("Bạn không được xem phòng này.")
        return [code], ten[code]
    bo = phong_khong_cong_tong()
    ma = [c for c in ten if (pv is None or c in pv) and c not in bo]
    return ma, "cả phạm vi được xem"


def _theo_acc(tu: str, den: str, codes: list[str]) -> pd.DataFrame:
    """Online theo acc trong [tu, den] ở các phòng `codes`: acc_norm, acc, phong_code (nơi nhiều số nhất), n."""
    df = tong_theo_acc(tu, den)
    df = df[df.phong_code.isin(set(codes))].copy()
    df["acc_norm"] = df.acc_norm.fillna("").astype(str)
    df = df[df.acc_norm != ""]
    if df.empty:
        return pd.DataFrame(columns=["acc_norm", "acc", "phong_code", "n"])
    chinh = df.sort_values("n", ascending=False).drop_duplicates("acc_norm")[["acc_norm", "acc", "phong_code"]]
    return chinh.merge(df.groupby("acc_norm", as_index=False).n.sum(), on="acc_norm")


def _thong_tin_nguoi(thang: str, ngay: int, accs: set[str]) -> pd.DataFrame:
    """Tên, phòng hiện tại, còn làm không, loại (NV / Trưởng phòng / Đã nghỉ) của từng acc."""
    hs = fi._hieu_suat(thang, None, ngay).drop_duplicates("acc_norm").set_index("acc_norm")
    out = pd.DataFrame(index=sorted(accs))
    out["ho_ten"] = hs.ho_ten.reindex(out.index)
    out["phong_nay"] = hs.phong_code.reindex(out.index)
    out["dang_lam"] = hs.dang_lam.reindex(out.index).fillna(False).astype(bool)
    out["tham_nien"] = hs.tham_nien.reindex(out.index).fillna("")
    khong_xet = cb.acc_khong_xet(accs)
    # nghỉ TẠM (thai sản...) = ghi "Nghỉ" và có ngày quay lại (hieu_luc_den): vẫn là nhân sự của phòng, không phải đã nghỉ
    sm = pd.read_sql_query(text("SELECT acc_norm, ghi_chu, hieu_luc_den FROM staff_map"), engine)
    tam = set(sm[sm.ghi_chu.fillna("").str.contains("Nghỉ") & sm.hieu_luc_den.notna()].acc_norm)
    out["nghi_tam"] = [a in tam for a in out.index]
    tp = cb.acc_truong_phong(accs)
    out["loai"] = ["TP" if a in tp or khong_xet.get(a) == "Trưởng phòng" else
                   "NGHI" if khong_xet.get(a) == "Đã nghỉ" or (a in hs.index and not out.at[a, "dang_lam"]) else "NV"
                   for a in out.index]
    return out


def _doi(ck: int, nay: int) -> str:
    """'từ 14 còn 6' / 'từ 13 lên 22' - không dùng ký hiệu mũi tên (Fox cấm ký hiệu)."""
    return f"từ {int(ck)} {'lên' if nay > ck else 'còn'} {int(nay)}"


def _ten(r, acc: str) -> str:
    return str(r.ho_ten) if isinstance(r.ho_ten, str) and r.ho_ten else acc


def loc_duoc_nem_ten(nv: pd.DataFrame, phong: pd.Series, duoc_ten) -> pd.DataFrame:
    """Giữ các dòng người mà người hỏi được xem tên. Dùng mặt nạ Series: danh sách rỗng đưa thẳng vào `nv[[]]` sẽ chọn CỘT (bảng không còn cột nào) và làm hỏng bước sau
    (lỗi thật 23/11/2026 ở phòng IBB7: nhóm "mất số" chỉ toàn trưởng phòng / người nghỉ nên không còn ai để nêu tên)."""
    return nv[pd.Series([bool(duoc_ten(phong.get(a))) for a in nv.index], index=nv.index, dtype=bool)]


def cau_noi_theo_nguoi(nay: pd.DataFrame, ck: pd.DataFrame, codes: list[str], thang: str, ngay: int,
                       duoc_ten) -> tuple[list[str], dict]:
    """Tách mức chênh thành các nhóm người. `duoc_ten(phong_code)` cho biết người hỏi có được xem tên không."""
    df = pd.DataFrame({"nay": nay.set_index("acc_norm").n, "ck": ck.set_index("acc_norm").n}).fillna(0).astype(int)
    phong = pd.concat([ck.set_index("acc_norm").phong_code, nay.set_index("acc_norm").phong_code])
    phong = phong[~phong.index.duplicated(keep="last")]
    acc = pd.concat([ck.set_index("acc_norm").acc, nay.set_index("acc_norm").acc])
    acc = acc[~acc.index.duplicated(keep="last")]
    df["chenh"] = df.nay - df.ck
    tt = _thong_tin_nguoi(thang, ngay, set(df.index))
    df = df.join(tt)
    ten_phong = {p["code"]: p["ten"] for p in phong_order(thang)}

    def nhom(r) -> str:
        if r.ck > 0 and r.nay == 0:
            return "mat"
        if r.ck == 0 and r.nay > 0:
            return "moi"
        return "tang" if r.chenh > 0 else "giam" if r.chenh < 0 else "giu"
    df["nhom"] = [nhom(r) for r in df.itertuples()]
    tong = int(df.chenh.sum())
    dong = [f"1) THEO NGƯỜI (cộng lại = {_d(tong)} online so với cùng kỳ; {len(df)} người có số ở một trong hai kỳ):"]

    def liet_ke(sub: pd.DataFrame, cot_so: str, chi_nv: bool = True) -> str:
        """Tên các người đáng kể nhất trong nhóm; người không được nêu tên (trưởng phòng, đã nghỉ, ngoài quyền) gộp."""
        nv = sub[(sub.loai == "NV") if chi_nv else sub.index == sub.index]
        nv = loc_duoc_nem_ten(nv, phong, duoc_ten)
        nv = nv.reindex(nv[cot_so].abs().sort_values(ascending=False).index).head(TOI_DA_TEN)
        return ", ".join(f"{_ten(r, a)} ({_doi(r.ck, r.nay)})" for a, r in nv.iterrows())

    def khac(sub: pd.DataFrame, da_neu: str) -> str:
        n_neu = len([x for x in da_neu.split(", ") if x])
        con = len(sub) - n_neu
        return f" và {con} người khác" if con > 0 else ""

    g = {k: df[df.nhom == k] for k in ("tang", "giam", "mat", "moi", "giu")}
    for k, nhan, dau in (("giam", "Người VẪN CÓ SỐ nhưng GIẢM so cùng kỳ", ""), ("mat", "Người kỳ trước có số, kỳ này KHÔNG CÓ SỐ nào", ""),
                         ("tang", "Người TĂNG so cùng kỳ", ""), ("moi", "Người MỚI có số (cùng kỳ chưa có)", "")):
        sub = g[k]
        if sub.empty:
            continue
        ds = liet_ke(sub, "chenh" if k != "mat" else "ck")
        dong.append(f"   - {nhan}: {len(sub)} người, {_d(sub.chenh.sum())} online" + (f". Nhiều nhất: {ds}{khac(sub, ds)}" if ds else "")
                    + ("" if k != "moi" else f". Trong đó người mới vào làm (thâm niên 1-3 tháng): "
                       f"{int((sub.tham_nien.isin(['1 tháng', '2 tháng', '3 tháng'])).sum())} người"))
        if k == "mat":
            ly_do: dict[str, list[str]] = {}
            for a, r in sub.iterrows():
                if r.loai == "TP":
                    lb = "trưởng phòng"
                elif r.nghi_tam:
                    lb = "đang nghỉ tạm (có ngày quay lại)"
                elif r.loai == "NGHI":
                    lb = "đã nghỉ"
                elif r.phong_nay and r.phong_nay not in codes and r.phong_nay in ten_phong:
                    lb = f"đã chuyển sang {ten_phong[r.phong_nay]}"
                elif r.dang_lam:
                    lb = "vẫn trong phòng nhưng chưa có số kỳ này"
                else:
                    lb = "đã nghỉ hoặc không còn trong danh sách nhân sự đang làm"
                ly_do.setdefault(lb, []).append(a)
            dong.append("     Lý do (theo danh mục): " + "; ".join(
                f"{lb} {len(v)} người ({_d(sub.loc[v].chenh.sum())} online)" for lb, v in
                sorted(ly_do.items(), key=lambda x: sub.loc[x[1]].chenh.sum())))
    if len(g["giu"]):
        dong.append(f"   - Giữ nguyên số: {len(g['giu'])} người")
    co_nay, co_ck = int((df.nay > 0).sum()), int((df.ck > 0).sum())
    dong.append(f"   - Số người có số: {co_nay} (cùng kỳ {co_ck}); online bình quân mỗi người có số: "
                f"{str(round(df.nay.sum() / co_nay, 1)).replace('.', ',') if co_nay else 0} "
                f"(cùng kỳ {str(round(df.ck.sum() / co_ck, 1)).replace('.', ',') if co_ck else 0}).")
    top_nay = df.nay.nlargest(3).sum() / df.nay.sum() * 100 if df.nay.sum() else 0
    top_ck = df.ck.nlargest(3).sum() / df.ck.sum() * 100 if df.ck.sum() else 0
    dong.append(f"   - Mức phụ thuộc: 3 người đứng đầu làm {round(top_nay)}% số online (cùng kỳ {round(top_ck)}%).")
    return dong, {"giam": int(-g["giam"].chenh.sum()), "n_giam": len(g["giam"])}


def cau_noi_theo_nguon(nay: pd.DataFrame, ck: pd.DataFrame, tu: str, tu_ck: str) -> list[str]:
    """Hợp đồng ký TRƯỚC đầu tháng (hàng chờ từ tháng trước) và hợp đồng ký trong tháng, online trong kỳ."""
    def tach(df: pd.DataFrame, moc: str) -> tuple[int, int]:
        truoc = int((df.ngay_tao_hd < pd.Timestamp(moc)).sum())
        return truoc, len(df) - truoc
    a1, b1 = tach(nay, tu)
    a0, b0 = tach(ck, tu_ck)
    dong = [f"2) THEO NGUỒN HỢP ĐỒNG (cộng lại = {_d(a1 + b1 - a0 - b0)}):",
            f"   - Online từ hợp đồng ký TRƯỚC đầu tháng (hàng chờ chuyển từ tháng trước sang): {a1} so với {a0} "
            f"cùng kỳ ({_d(a1 - a0)}).",
            f"   - Online từ hợp đồng ký NGAY TRONG tháng: {b1} so với {b0} cùng kỳ ({_d(b1 - b0)})."]
    return dong


def dong_tuan(thang: str, ngay: int, nay: pd.Series, ck: pd.Series) -> list[str]:
    """`nay`, `ck`: online từng ngày (chỉ số = ngày 1..n) của kỳ này và của tháng trước, cộng các phòng xét."""
    pm = prev_month(thang)
    ngay_ck = min(ngay, month_range(pm)[2])
    tuan = []
    for a in range(1, ngay + 1, 7):
        b = min(a + 6, ngay)
        tuan.append((a, b, int(nay.loc[a:b].sum()), int(ck.loc[a:min(b, ngay_ck)].sum()) if a <= ngay_ck else 0))
    dong = [f"3) THEO TUẦN TRONG THÁNG (online kỳ này so với cùng kỳ {pm[5:7]}):"]
    dong.append("   - " + "; ".join(f"{a:02d}-{b:02d}/{thang[5:7]}: {x} so với {y} ({_d(x - y)})" for a, b, x, y in tuan) + ".")
    xau = min(tuan, key=lambda t: t[2] - t[3])
    if len(tuan) > 1 and xau[2] - xau[3] < 0:
        dong.append(f"   - Tuần hụt nhiều nhất: {xau[0]:02d}-{xau[1]:02d}/{thang[5:7]} ({_d(xau[2] - xau[3])}).")
    dong.append("   - Online từng ngày (14 ngày gần nhất): " + ", ".join(
        f"{n:02d}/{thang[5:7]}={int(nay[n])}" for n in range(max(1, ngay - 13), ngay + 1)) + ".")
    tb = float(nay.loc[1:ngay].mean()) if ngay else 0
    thap = [f"{n:02d}/{thang[5:7]} ({int(nay[n])})" for n in range(1, ngay) if tb and nay[n] < 0.5 * tb]
    if thap:
        dong.append(f"   - Ngày thấp bất thường (dưới nửa bình quân {str(round(tb, 1)).replace('.', ',')}/ngày): " + ", ".join(thap) + ".")
    ngay_0 = [f"{n:02d}" for n in range(1, ngay) if int(nay[n]) == 0]
    if ngay_0:
        dong.append("   - Ngày không có online nào: " + ", ".join(ngay_0) + ".")
    # lịch: số Chủ nhật hai kỳ và Chủ nhật so với ngày thường của tháng trước
    cn_nay = sum(1 for n in range(1, ngay + 1) if date(int(thang[:4]), int(thang[5:7]), n).weekday() == 6)
    cn_ck = sum(1 for n in range(1, ngay_ck + 1) if date(int(pm[:4]), int(pm[5:7]), n).weekday() == 6)
    if cn_nay != cn_ck:
        cn = [n for n in range(1, month_range(pm)[2] + 1) if date(int(pm[:4]), int(pm[5:7]), n).weekday() == 6]
        thuong = [n for n in range(1, month_range(pm)[2] + 1) if n not in cn]
        if cn and thuong and ck.loc[thuong].mean():
            dong.append(f"   - Lịch: kỳ này có {cn_nay} Chủ nhật, cùng kỳ có {cn_ck}; tháng trước Chủ nhật bình quân bằng "
                        f"{round(float(ck.loc[cn].mean() / ck.loc[thuong].mean()) * 100)}% một ngày thường.")
    return dong


def dong_dau_vao_dau_ra(codes: list[str], bm_nay: int, bm_ck: int, nay: pd.DataFrame, ck: pd.DataFrame) -> list[str]:
    """Khâu bán (hợp đồng ký mới) so với khâu triển khai (online, tồn, tốc độ)."""
    onl_nay, onl_ck = len(nay), len(ck)
    dong = ["4) ĐẦU VÀO - ĐẦU RA (bán hay triển khai đang nghẽn):",
            f"   - Bán mới (hợp đồng ký): {_so(bm_nay)} so với {_so(bm_ck)} cùng kỳ ({_d(bm_nay - bm_ck)}). "
            f"Online: {_so(onl_nay)} so với {_so(onl_ck)} ({_d(onl_nay - onl_ck)})."]
    if bm_ck and bm_nay <= bm_ck * 0.9:
        dong.append("   - Cách đọc: bán mới GIẢM rõ, vấn đề bắt đầu từ khâu bán (số hợp đồng ký ít hơn), không phải do triển khai.")
    elif onl_ck and onl_nay <= onl_ck * 0.9:
        dong.append("   - Cách đọc: bán mới tương đương hoặc tăng nhưng online giảm, chỗ nghẽn nằm ở khâu chuyển hợp đồng đã ký "
                    "thành online (xem số tồn và tốc độ triển khai bên dưới).")
    elif bm_ck and bm_nay >= bm_ck * 1.1 and onl_nay < bm_nay:
        dong.append("   - Cách đọc: bán mới tăng nhiều hơn online, phần hợp đồng ký thêm đang chờ online ở các ngày sau "
                    "(hợp đồng ký cuối kỳ chưa kịp online là bình thường), chưa phải dấu hiệu nghẽn.")
    ton = pt.hop_dong_ton(codes)
    if len(ton):
        dong.append(f"   - Số tồn hiện tại (đã ký, chưa online): {len(ton)} hợp đồng, trong đó chờ từ 7 ngày "
                    f"{int((ton.so_ngay_cho >= 7).sum())}, từ 15 ngày {int((ton.so_ngay_cho >= 15).sum())}, "
                    f"trên 30 ngày {int((ton.so_ngay_cho > 30).sum())}.")
    if onl_nay and onl_ck:
        a, b = nay.onl_nhanh.mean() * 100, ck.onl_nhanh.mean() * 100
        dong.append(f"   - Tốc độ triển khai: {round(a)}% hợp đồng online trong 1 ngày (cùng kỳ {round(b)}%, "
                    f"{round(a - b):+d} điểm); chờ trung vị {str(float(nay.so_ngay_cho.median())).replace('.', ',')} ngày "
                    f"(cùng kỳ {str(float(ck.so_ngay_cho.median())).replace('.', ',')}).")
    return dong


def dong_chat_luong(nay: pd.DataFrame, ck: pd.DataFrame) -> list[str]:
    if nay.empty or ck.empty:
        return []
    a, b = fi._ty_le(nay), fi._ty_le(ck)
    return ["5) CHẤT LƯỢNG BÁN (chỉ nêu khi đổi từ 5 điểm; còn lại tương đương): " + (
        "; ".join(f"{fi.TY_LE[k]} {round(a[k])}% (cùng kỳ {round(b[k])}%, {round(a[k] - b[k]):+d} điểm"
                  + ("; chênh quá lớn, nên kiểm tra dữ liệu cùng kỳ đã đủ chưa" if abs(a[k] - b[k]) >= 40 else "") + ")"
                  for k in fi.TY_LE if a.get(k) is not None and b.get(k) is not None and abs(a[k] - b[k]) >= 5)
        or "không có chỉ số nào đổi đáng kể.")]


def dong_chu_y_du_dia(d: date, code: str | None, codes: list[str], tom: dict, duoc_ten, ngay_: pd.Series) -> list[str]:
    """Việc có thể làm ngay: người cần chú ý hôm nay (một phòng, có quyền xem tên) và phần online có thể thêm."""
    from app.tro_ly_du_lieu import _nhan_su_phong, ngay_chot_7
    thang = f"{d.year}-{d.month:02d}"
    dong = ["6) VIỆC CÓ THỂ LÀM NGAY (app đã tính sẵn):"]
    c = ngay_chot_7(d)
    if c.month == d.month and c.day >= 14:
        nay7, truoc7 = int(ngay_.loc[c.day - 6:c.day].sum()), int(ngay_.loc[c.day - 13:c.day - 7].sum())
        dong.append(f"   - 7 ngày đã chốt gần nhất ({c.day - 6:02d}-{c:%d/%m}): {nay7} online so với {truoc7} của 7 ngày trước đó "
                    f"({_d(nay7 - truoc7)}).")
    ton = pt.hop_dong_ton(codes)
    ton7 = int((ton.so_ngay_cho >= 7).sum()) if len(ton) else 0
    if tom.get("giam"):
        dong.append(f"   - Nếu {tom['n_giam']} người đang giảm lấy lại mức cùng kỳ thì thêm {tom['giam']} online.")
    if ton7:
        dong.append(f"   - Nếu chuyển được một nửa số hợp đồng chờ từ 7 ngày ({ton7}) thành online thì thêm khoảng {round(ton7 / 2)} online.")
    if code and duoc_ten(code):
        nv = _nhan_su_phong(thang, d.day, code)
        nv = nv[(nv.loai_dong == "data") & (nv.khong_xet.fillna("") == "")]
        cc = nv[nv.muc_chu_y.fillna("") != ""].head(5)
        if len(cc):
            dong.append("   - Người cần chú ý hôm nay (quy tắc chung của app): " + "; ".join(
                f"{r.ho_ten} ({r.muc_chu_y}: {r.chu_y})" for r in cc.itertuples()) + ".")
        ton_lau = nv[pd.to_numeric(nv.ton_qua_7, errors="coerce").fillna(0) > 0].copy()
        ton_lau["ton_qua_7"] = pd.to_numeric(ton_lau.ton_qua_7)
        ton_lau = ton_lau.nlargest(3, "ton_qua_7")
        if len(ton_lau):
            dong.append("   - Hợp đồng chờ từ 7 ngày nằm nhiều ở: " + ", ".join(
                f"{r.ho_ten} {int(r.ton_qua_7)}" for r in ton_lau.itertuples()) + ".")
    return dong if len(dong) > 1 else []


def nguyen_nhan(user, den: str | None, code: str | None) -> str:
    """Số liệu để trả lời "vì sao online của phòng / phạm vi tăng hay giảm so với cùng kỳ tháng trước"."""
    from app.tro_ly_du_lieu import _ngay_hop_le, dong_thoi_gian
    d = _ngay_hop_le(den)
    thang = f"{d.year}-{d.month:02d}"
    codes, ten = _pham_vi(user, code)
    if not codes:
        return "Không có phòng nào trong phạm vi được xem."
    tu, tu_ck, den_ck = f"{thang}-01", *pt.cung_ky_thang_truoc(thang, d.day)
    pns = user.phong_nhan_su()

    def duoc_ten(p) -> bool:
        return bool(user.duoc_xem_nhan_su) and (pns is None or p in pns)

    nay_acc, ck_acc = _theo_acc(tu, d.isoformat(), codes), _theo_acc(tu_ck, den_ck, codes)
    nay, ck = pt.hop_dong_online(tu, d.isoformat(), codes), pt.hop_dong_online(tu_ck, den_ck, codes)
    chenh = len(nay) - len(ck)
    dong = [f"CHẨN ĐOÁN NGUYÊN NHÂN · {ten} · luỹ kế {tu[8:]}-{d:%d/%m} so với cùng kỳ {tu_ck[8:]}-{den_ck[8:]}/{den_ck[5:7]}. "
            f"{dong_thoi_gian(d)}",
            f"Kết quả: {_so(len(nay))} online so với {_so(len(ck))} cùng kỳ = {_d(chenh)}"
            + (f" ({round(chenh / len(ck) * 100):+d}%)" if len(ck) else "") + ". Mỗi phần dưới đây cộng lại bằng đúng mức chênh này."]
    db = du_bao_thang(thang, d.day, codes)
    t = db[db.phong_code == (code or "TOTAL")]
    if len(t) and t.iloc[0].mt:
        r = t.iloc[0]
        dong.append(f"Mục tiêu tháng {_so(r.mt)}: đạt {_so(r.luy_ke)} = {round(r.luy_ke / r.mt * 100)}%, dự báo cuối tháng "
                    f"{_so(r.du_bao)} = {int(r.pct_mt)}% ({r.danh_gia}). Cần {_so(r.can_moi_ngay or 0)}/ngày, đang "
                    f"{str(r.tb_ngay).replace('.', ',')}/ngày.")
    from app.tro_ly_du_lieu import so_voi_thang_truoc
    nhip = so_voi_thang_truoc(thang, d.day, codes)
    if nhip:
        dong.append(nhip.lstrip("- "))
    from app.overview import trang_thai_ngay
    if trang_thai_ngay(d.isoformat())[0]:
        dong.append("Lưu ý: ngày cuối đang cập nhật, số tạm tính - không kết luận giảm chỉ dựa vào riêng ngày đó.")
    if len(codes) > 1:
        a = nay.groupby("phong_code").size()
        b = ck.groupby("phong_code").size()
        ch = (a.reindex(codes).fillna(0) - b.reindex(codes).fillna(0)).astype(int)
        mp = {p["code"]: p["ten"] for p in phong_order(thang)}
        giam, tang = ch[ch < 0].sort_values().head(4), ch[ch > 0].sort_values(ascending=False).head(3)
        dong.append("0) THEO PHÒNG: giảm nhiều nhất " + (", ".join(f"{mp[c]} {_d(v)}" for c, v in giam.items()) or "không có")
                    + "; tăng nhiều nhất " + (", ".join(f"{mp[c]} {_d(v)}" for c, v in tang.items()) or "không có") + ".")
    d_nguoi, tom = cau_noi_theo_nguoi(nay_acc, ck_acc, codes, thang, d.day, duoc_ten)
    dong += d_nguoi
    dong += cau_noi_theo_nguon(nay, ck, tu, tu_ck)
    pm = prev_month(thang)
    onl_nay, onl_ck = (daily_counts(m, "online").loc[codes].sum() for m in (thang, pm))
    bm_nay, bm_ck = (daily_counts(m, "ban_moi").loc[codes].sum() for m in (thang, pm))
    dong += dong_tuan(thang, d.day, onl_nay, onl_ck)
    dong += dong_dau_vao_dau_ra(codes, int(bm_nay.loc[1:d.day].sum()), int(bm_ck.loc[1:min(d.day, month_range(pm)[2])].sum()),
                                nay, ck)
    dong += dong_chat_luong(nay, ck)
    dong += dong_chu_y_du_dia(d, code, codes, tom, duoc_ten, onl_nay)
    if not (user.duoc_xem_nhan_su and (pns is None or code in (pns or []))) and code:
        dong.append("(Người hỏi không được xem chi tiết nhân sự của phòng này nên phần theo người không nêu tên.)")
    dong.append("CÁCH DÙNG: xếp các phần theo mức ảnh hưởng (số lớn nhất lên trước), mỗi nguyên nhân phải trích số ở trên. "
                "Không suy diễn lý do ngoài những gì dữ liệu cho thấy (VD vì sao một người nghỉ, nghỉ phép, thời tiết).")
    return "\n".join(dong)
