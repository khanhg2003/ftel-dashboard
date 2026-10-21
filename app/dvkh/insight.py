"""Nhận định tự động cho khối DVKH: LUẬT cố định đọc số rồi viết thành câu (không dùng AI, số nào cũng truy được về bảng).

Mỗi nhận định là một dict: muc (Nghiêm trọng / Cần chú ý / Thông tin / Tốt), chu_de, tieu_de, noi_dung, goi_y.
Ngưỡng nằm ở đầu file để chỉnh một chỗ. Chỉ nêu điều có số liệu; mẫu quá nhỏ thì bỏ qua thay vì đoán.
"""
from __future__ import annotations

import pandas as pd

from app.bo_nho import nho
from app.dvkh import cheo, so_lieu as sl

NGHIEM_TRONG, CAN_CHU_Y, THONG_TIN, TOT = "Nghiêm trọng", "Cần chú ý", "Thông tin", "Tốt"
THU_TU_MUC = {NGHIEM_TRONG: 0, CAN_CHU_Y: 1, THONG_TIN: 2, TOT: 3}
NGUONG_QUA_HAN_BD = (20, 30)          # % SR bị động quá hạn: cần chú ý / nghiêm trọng
NGUONG_TON_CD = (25, 40)              # % SR chủ động tồn (chưa xử lý + chưa phân công + đang xử lý)
NGUONG_KHONG_LIEN_LAC = (20, 30)      # % không liên lạc được trên SR đã thử liên hệ
NGUONG_THU_NO_CHAM = 1.0              # điểm % thu nợ thấp hơn cùng ngày kỳ trước thì cần chú ý
MAU_TOI_THIEU = 30
CHU_DE = ["Giữ chân khách", "Chất lượng xử lý", "Tốc độ", "Nguyên nhân", "Tài chính", "Nguồn lực", "Hiệu quả liên hệ", "Dự báo rời mạng", "Công nợ",
          "Rời mạng", "Điểm nóng", "SR bị động", "SR chủ động"]


def _s(v, nd: int = 0) -> str:
    """Số kiểu Việt Nam: 1.234 hoặc 12,5."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "–"
    t = f"{v:,.{nd}f}"
    return t.replace(",", "#").replace(".", ",").replace("#", ".")


def _p(v, nd: int = 1) -> str:
    return "–" if v is None or pd.isna(v) else _s(v, nd) + "%"


def _nd(muc, chu_de, tieu_de, noi_dung, goi_y="") -> dict:
    return {"muc": muc, "chu_de": chu_de, "tieu_de": tieu_de, "noi_dung": noi_dung, "goi_y": goi_y}


def _muc(v, nguong, cao_xau: bool = True) -> str:
    if v is None or pd.isna(v):
        return THONG_TIN
    a, b = nguong
    return NGHIEM_TRONG if v >= b else (CAN_CHU_Y if v >= a else TOT) if cao_xau else TOT


# ------------------------------------------------------------------ SR bị động
def _bd(bd: pd.DataFrame) -> list[dict]:
    out: list[dict] = []
    if len(bd) < MAU_TOI_THIEU:
        return out
    k = sl.kpi_bd(bd)
    ch = "SR bị động"
    muc = _muc(k["ty_le_qua_han"], NGUONG_QUA_HAN_BD)
    theo = sl.theo_loai_yc(bd)
    cao = theo.sort_values("qua_han", ascending=False).head(2)
    top = " và ".join(f"{r.loai_yc} ({_s(r.qua_han)} SR)" for r in cao.itertuples())
    out.append(_nd(muc, ch, f"{_p(k['ty_le_qua_han'])} SR bị động quá hạn xử lý",
                   f"{_s(k['qua_han'])} trên {_s(k['so_sr'])} SR đã quá hạn. Nhiều nhất ở {top}. Còn {_s(k['ton'])} SR chưa xong, "
                   f"trong đó {_s(k['dang_xu_ly'])} đang xử lý.",
                   "Ưu tiên dọn nhóm Thắc mắc và Tư vấn trước vì xử lý nhanh; giao người theo dõi riêng SR đang xử lý quá hạn."))
    tl = bd[bd["loai_yc"] == "Thanh lý"]
    if len(tl) >= MAU_TOI_THIEU:
        co_tv = tl[tl["ket_qua_tu_van"].notna()]
        o_lai, khong, chet = co_tv["o_lai"].sum(), co_tv["muon_di"].sum(), tl["roi_mang_sau"].sum()
        out.append(_nd(CAN_CHU_Y if len(tl) / len(bd) > .1 else THONG_TIN, "Giữ chân khách",
                       f"Yêu cầu thanh lý chiếm {_p(len(tl) * 100 / len(bd))} SR, chỉ giữ lại được {_p(o_lai * 100 / max(len(co_tv), 1), 0)} khách",
                       f"{_s(len(tl))} SR thanh lý, {_s(tl['ton'].sum())} SR còn tồn ({_p(tl['ton'].mean() * 100)}). Trong {_s(len(co_tv))} SR đã tư vấn có "
                       f"{_s(o_lai)} khách đồng ý dùng tiếp và {_s(khong)} khách nhất định không dùng. Đã có {_s(chet)} hợp đồng chấm dứt thật.",
                       "Đặt SLA riêng cho thanh lý (xử lý trong ngày), gọi lại nhóm 'đang suy nghĩ' sau 24 giờ, đối chiếu lý do với nhóm khiếu nại cước và chất lượng."))
    if k["hd_lap"]:
        pt = bd.groupby("so_hd").size()
        nhieu = int((pt >= 4).sum())
        out.append(_nd(CAN_CHU_Y if k["ty_le_lap"] and k["ty_le_lap"] > 30 else THONG_TIN, "Chất lượng xử lý",
                       f"{_s(k['hd_lap'])} hợp đồng gọi từ 2 lần trở lên ({_p(k['ty_le_lap'], 0)} khối lượng SR)",
                       f"{_s(k['sr_lap'])} SR thuộc nhóm hợp đồng gọi lặp; có {_s(nhieu)} hợp đồng gọi từ 4 lần. Lặp nhiều thường là lần xử lý trước chưa dứt điểm.",
                       "Mở danh sách hợp đồng gọi lặp ở trang SR bị động (tab Hợp đồng gọi lặp), giao một người phụ trách đến khi khách ổn định."))
    kn = bd[bd["loai_yc"] == "Khiếu nại, phàn nàn"]
    if len(kn) >= MAU_TOI_THIEU:
        pl = sl.dem_theo(kn, "phan_loai", 3)
        nn = sl.dem_theo(kn[kn["nguyen_nhan_1"].notna()], "nguyen_nhan_1", 2)
        out.append(_nd(THONG_TIN, "Nguyên nhân",
                       f"Khiếu nại nhiều nhất về {pl.iloc[0]['phan_loai'].lower()} ({_p(pl.iloc[0]['ty_trong'], 0)})",
                       "Top phân loại: " + "; ".join(f"{r.phan_loai} {_s(r.so)} SR" for r in pl.itertuples()) +
                       ". Top nguyên nhân: " + "; ".join(f"{r.nguyen_nhan_1} {_s(r.so)}" for r in nn.itertuples()) + ".",
                       "Chuyển nhóm cước phí cho tổ thu cước / chăm sóc hoá đơn; nhóm chất lượng dịch vụ báo kỹ thuật để xử lý gốc."))
    ph = bd["phan_hoi_phut"].dropna()
    if len(ph) >= MAU_TOI_THIEU:
        out.append(_nd(CAN_CHU_Y if k["trong_60p"] < 80 else TOT, "Tốc độ",
                       f"{_p(k['trong_60p'], 0)} SR được phản hồi trong 60 phút",
                       f"Trung vị {_s(k['phan_hoi_p50'], 0)} phút nhưng 10% SR chậm nhất chờ trên {_s(k['phan_hoi_p90'], 0)} phút. Thời gian đóng SR trung vị {_s(k['xu_ly_p50_gio'], 1)} giờ.",
                       "Bật cảnh báo SR chưa phản hồi sau 30 phút ở các giờ cao điểm 10 đến 11 giờ và 14 đến 17 giờ."))
    if k["phi"] > 0:
        out.append(_nd(THONG_TIN, "Tài chính",
                       f"Miễn giảm phí bằng {_p(k['mien_giam'] * 100 / k['phi'], 0)} số phí phát sinh",
                       f"Phí phát sinh {_s(k['phi'] / 1e6, 1)} triệu đồng, đã miễn giảm {_s(k['mien_giam'] / 1e6, 1)} triệu đồng.",
                       "Kiểm tra nhóm lý do miễn giảm để chặn sớm các trường hợp lặp."))
    ns = sl.theo_nhan_su_bd(bd)
    if len(ns) >= 5:
        tb, mx = ns["phan_cong"].median(), ns["phan_cong"].max()
        if mx > 1.5 * tb:
            out.append(_nd(THONG_TIN, "Nguồn lực", f"Tải SR bị động chênh nhau tới {_s(mx / tb, 1)} lần giữa các CSKH",
                           f"Trung vị {_s(tb)} SR mỗi người, cao nhất {_s(mx)} SR ({ns.iloc[0]['nhan_su']}).",
                           "Cân lại cách chia SR theo tải đang mở, không chia vòng tròn."))
    return out


# ------------------------------------------------------------------ SR chủ động
def _cd(cd: pd.DataFrame) -> list[dict]:
    out: list[dict] = []
    if len(cd) < MAU_TOI_THIEU:
        return out
    k = sl.kpi_cd(cd)
    ch = "SR chủ động"
    muc = _muc(k["ty_le_ton"], NGUONG_TON_CD)
    ct = sl.theo_chuong_trinh(cd)
    cham = ct[ct["so_sr"] >= MAU_TOI_THIEU].sort_values("ty_le_ton", ascending=False).head(3)
    out.append(_nd(muc, ch, f"{_p(k['ty_le_ton'], 0)} SR chủ động chưa xử lý xong",
                   f"{_s(k['ton'])} SR tồn: {_s(k['chua_xu_ly'])} chưa xử lý, {_s(k['chua_phan_cong'])} chưa phân công, {_s(k['dang_xu_ly'])} đang xử lý. "
                   "Tồn nặng nhất: " + "; ".join(f"{r.chuong_trinh.strip()} {_p(r.ty_le_ton, 0)}" for r in cham.itertuples()) + ".",
                   "Chương trình tồn gần hết là chương trình chưa có người nhận: phân công rõ người phụ trách từng chương trình."))
    if k["tu_dong"]:
        td = cd[cd["tu_dong"]]
        out.append(_nd(CAN_CHU_Y if td["ton"].mean() > .5 else THONG_TIN, "Nguồn lực",
                       f"Máy gọi tự động đang giữ {_s(len(td))} SR, còn tồn {_s(td['ton'].sum())}",
                       f"Tài khoản autocall nhận {_p(len(td) * 100 / len(cd), 0)} tổng SR chủ động; {_p(td['khong_lien_lac'].sum() * 100 / max(td['da_thu_lien_he'].sum(), 1), 0)} cuộc đã thử là không liên lạc được.",
                       "SR mà máy gọi không liên lạc được cần chuyển CSKH gọi tay trong 24 giờ, nếu không sẽ tồn vô hạn."))
    muc_kll = _muc(k["ty_le_khong_lien_lac"], NGUONG_KHONG_LIEN_LAC)
    kll = ct[(ct["thu"] >= MAU_TOI_THIEU)].sort_values("ty_le_khong_lien_lac", ascending=False).head(2)
    out.append(_nd(muc_kll, "Hiệu quả liên hệ", f"{_p(k['ty_le_khong_lien_lac'], 0)} SR đã thử liên hệ là không liên lạc được",
                   f"Gặp được khách {_p(k['ty_le_gap'], 0)}. Khó liên lạc nhất: " +
                   "; ".join(f"{r.chuong_trinh.strip()} {_p(r.ty_le_khong_lien_lac, 0)}" for r in kll.itertuples()) + ".",
                   "Thử gọi lại vào khung 18 đến 20 giờ, nhắn Zalo / ZNS khi gọi hai lần không được."))
    if k["ty_le_khong_can_lh"]:
        ly = sl.dem_theo(cd[cd["khong_can_lh"] & cd["ly_do_khong_lh"].notna()], "ly_do_khong_lh", 3)
        out.append(_nd(CAN_CHU_Y if k["ty_le_khong_can_lh"] > 20 else THONG_TIN, "Hiệu quả liên hệ",
                       f"{_p(k['ty_le_khong_can_lh'], 0)} SR được ghi 'không cần liên hệ', {_p(k['ty_le_dong_tu_dong'], 0)} bị hệ thống tự đóng",
                       "Lý do chính: " + "; ".join(f"{r.ly_do_khong_lh} {_s(r.so)}" for r in ly.itertuples()) +
                       ". Đây là công sức phân công và chờ xử lý không tạo giá trị.",
                       "Lọc các trường hợp 'không thỏa điều kiện', 'KH đã online', 'đang được chăm ở tool khác' ngay từ nguồn đổ SR."))
    mk = cd[cd["ly_do_mat_kn"].notna()]
    if len(mk) >= MAU_TOI_THIEU:
        top = sl.dem_theo(mk, "ly_do_mat_kn", 2)
        out.append(_nd(THONG_TIN, "Nguyên nhân", f"{_p(top.iloc[0]['ty_trong'], 0)} SR mất kết nối là do {top.iloc[0]['ly_do_mat_kn'].lower()}",
                       "; ".join(f"{r.ly_do_mat_kn} {_s(r.so)} SR" for r in top.itertuples()) +
                       ". Nguyên nhân do khách hoặc hạ tầng điện không cần CSKH gọi.",
                       "Đồng bộ lịch cúp điện để tự đóng nhóm này; đứt cáp chuyển thẳng kỹ thuật."))
    bac = sl.theo_bac_diem(cd)
    if not bac.empty and bac["so_sr"].sum() >= 200:
        co = bac[bac["bac_diem"] != "Không có điểm"]
        cao = bac[bac["bac_diem"] == "Từ 800"]
        nen = bac["muon_thanh_ly"].sum() * 100 / max(bac["so_sr"].sum(), 1)
        if len(cao):
            r = cao.iloc[0]
            out.append(_nd(THONG_TIN, "Dự báo rời mạng", f"Điểm nguy cơ từ 800 có {_p(r['ty_le_thanh_ly'])} khách đòi thanh lý (mức chung {_p(nen)})",
                           f"Chỉ {_s(co['so_sr'].sum())} trên {_s(bac['so_sr'].sum())} SR có điểm; nhóm 300 đến 799 không ghi nhận khách đòi thanh lý nào. Điểm hiện chưa phân biệt rõ ràng khách sắp rời mạng.",
                           "Đối chiếu điểm với kết quả thực tế 3 tháng để hiệu chỉnh trước khi dùng điểm để xếp ưu tiên."))
    if k["no_cuoc"]:
        out.append(_nd(THONG_TIN, "Công nợ", f"{_p(k['no_cuoc'] * 100 / k['so_sr'], 0)} SR chủ động thuộc hợp đồng đang nợ cước",
                       f"{_s(k['no_cuoc'])} trên {_s(k['so_sr'])} SR. Nên chăm sóc kèm nhắc thanh toán một lần để tránh gọi hai lần.",
                       "Gộp danh sách chăm sóc và danh sách nợ cước theo hợp đồng."))
    return out


# ------------------------------------------------------------------ rời mạng, công nợ, điểm nóng
def _roi_mang_va_cong_no(bd: pd.DataFrame, cd: pd.DataFrame) -> list[dict]:
    out: list[dict] = []
    rm = sl.roi_mang_moi_nhat()
    if not rm.empty:
        p = rm[(rm["cap"] == "phong") & rm["ten"].str.startswith("05")]
        if len(p):
            r = p.iloc[0]
            out.append(_nd(CAN_CHU_Y if r["ty_le_roi_gross"] and r["ty_le_roi_gross"] > 40 else THONG_TIN, "Rời mạng",
                           f"Rời mạng bằng {_p(r['ty_le_roi_gross'], 0)} khách mới (Gross PTTB)",
                           f"{_s(r['kh_roi_mang'])} khách rời mạng, {_s(r['gross_pttb'])} khách phát triển mới, Net PTTB {_s(r['net_pttb'])}. "
                           f"Tỷ lệ rời mạng {_p(r['ty_le_roi_active'], 2)} trên {_s(r['kh_active'])} khách đang hoạt động.",
                           "Cứ 2 khách mới thì mất gần 1 khách cũ: tăng chăm sóc nhóm Hủy SSD và CTBDV dự kiến."))
        pc = rm[(rm["cap"] == "phong") & rm["ten"].isin(["DNG-01", "DNG-02"])]
        if len(pc) == 2:
            a, b = pc.sort_values("ty_le_roi_active").iloc[[0, 1]].to_dict("records")
            out.append(_nd(THONG_TIN, "Rời mạng", f"{b['ten']} rời mạng cao hơn {a['ten']} ({_p(b['ty_le_roi_active'], 2)} so với {_p(a['ty_le_roi_active'], 2)})",
                           f"{b['ten']} có {_s(b['kh_roi_mang'])} khách rời mạng (Hủy SSD {_s(b['huy_ssd'])}); {a['ten']} có {_s(a['kh_roi_mang'])} (Hủy SSD {_s(a['huy_ssd'])}).",
                           "Tìm xem chênh lệch đến từ phường nào ở tab Điểm nóng."))
    cn = sl.cong_no_ngay()
    if not cn.empty:
        t = cn[(cn["cap"] == "phong") & (cn["ten"] == "To tal DNG CN 30")]
        if not t.empty and t["ky_no"].nunique() >= 2:
            ky = sorted(t["ky_no"].unique())
            moi, cu = ky[-1], ky[-2]
            ngay = int(t[t["ky_no"] == moi]["so_ngay"].max())
            a = t[(t["ky_no"] == moi) & (t["so_ngay"] == ngay)]
            b = t[(t["ky_no"] == cu) & (t["so_ngay"] <= ngay)].sort_values("so_ngay")
            if len(a) and len(b):
                chenh = (a.iloc[0]["ty_le_dt"] - b.iloc[-1]["ty_le_dt"]) * 100
                chenh_b = (a.iloc[0]["ty_le_bill"] - b.iloc[-1]["ty_le_bill"]) * 100
                out.append(_nd(CAN_CHU_Y if chenh < -NGUONG_THU_NO_CHAM else (TOT if chenh > NGUONG_THU_NO_CHAM else THONG_TIN), "Công nợ",
                               f"Thu nợ tháng {moi[-2:]} {'chậm hơn' if chenh < 0 else 'nhanh hơn'} tháng trước {_s(abs(chenh), 1)} điểm % cùng ngày thu thứ {ngay}",
                               f"Theo doanh thu {_p(a.iloc[0]['ty_le_dt'] * 100)} (kỳ trước {_p(b.iloc[-1]['ty_le_dt'] * 100)}); theo số hoá đơn {_p(a.iloc[0]['ty_le_bill'] * 100)} "
                               f"(kỳ trước {_p(b.iloc[-1]['ty_le_bill'] * 100)}, chênh {_s(chenh_b, 1)} điểm).",
                               "Dồn lực gọi nhắc vào phường thu chậm nhất (tab Công nợ, bảng theo phường)."))
    hot = sl.diem_nong_phuong(bd, cd)
    if not hot.empty and (hot["so_chi_so_top3"] >= 2).any():
        top = hot[hot["so_chi_so_top3"] >= 2].head(3)
        out.append(_nd(CAN_CHU_Y, "Điểm nóng", "Phường nằm trong top 3 ở từ hai chỉ số xấu trở lên: " + ", ".join(top["ten"].map(sl.ten_phuong)),
                       "Ba chỉ số xét: SR bị động trên 1.000 khách, tỷ lệ rời mạng, tỷ lệ chưa thu công nợ. " +
                       "; ".join(f"{sl.ten_phuong(r.ten)}: {_s(r.sr_bd_1000, 1)} SR/1.000 KH, rời mạng {_p(r.ty_le_roi_active, 2)}" for r in top.itertuples()),
                       "Lập kế hoạch chăm sóc riêng cho các phường này: gặp trực tiếp khách lớn, phối hợp kỹ thuật kiểm tra hạ tầng."))
    return out


def _cheo(bd: pd.DataFrame, cd: pd.DataFrame) -> list[dict]:
    out: list[dict] = []
    tl = cheo.thanh_ly_ton(bd, cd)
    if len(tl) >= 10:
        cu = tl[tl["thoi_gian"] < tl["thoi_gian"].max() - pd.Timedelta(days=1)]
        out.append(_nd(NGHIEM_TRONG if len(tl) >= 100 else CAN_CHU_Y, "Giữ chân khách", f"{_s(len(tl))} SR thanh lý hoặc khách đòi thanh lý chưa xử lý xong",
                       f"{_s((tl['nguon'] == 'SR bị động: thanh lý').sum())} từ SR bị động và {_s((tl['nguon'] != 'SR bị động: thanh lý').sum())} từ SR chủ động; "
                       f"{_s(len(cu))} SR đã chờ trên 24 giờ. Mỗi SR là một khách có thể mất.",
                       "Gọi trong ngày, ưu tiên SR chờ lâu nhất. Danh sách ở mục Phân tích chéo của trang này."))
    h = cheo.hop_dong_hai_nguon(bd, cd)
    if len(h) >= 20:
        ton = int((h["con_ton"] > 0).sum())
        out.append(_nd(THONG_TIN, "Chất lượng xử lý", f"{_s(len(h))} hợp đồng vừa gọi vào vừa được DVKH chủ động chăm sóc",
                       f"{_s(ton)} hợp đồng trong số đó còn SR chưa xong. Khách có thể bị liên hệ hai lần cho cùng một việc.",
                       "Gộp hai hàng chờ theo hợp đồng: SR bị động đang xử lý thì SR chủ động tạm dừng."))
    return out


@nho("dvkh", 60)
def tao_nhan_dinh(phong: str | None = None) -> list[dict]:
    """Toàn bộ nhận định, nghiêm trọng nhất lên đầu. `phong` = DNG1 / DNG2 / None (cả Đà Nẵng)."""
    if not sl.co_du_lieu():
        return []
    bd = sl.loc(sl.sr_bi_dong(), phong)
    cd = sl.loc(sl.sr_chu_dong(), phong, cot_ngay="ngay_do")
    ds = _bd(bd) + _cd(cd) + _cheo(bd, cd) + _roi_mang_va_cong_no(sl.sr_bi_dong(), sl.sr_chu_dong())
    return sorted(ds, key=lambda x: THU_TU_MUC[x["muc"]])
