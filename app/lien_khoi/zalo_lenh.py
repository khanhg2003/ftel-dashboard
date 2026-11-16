"""Bot Zalo HAI CHIỀU cho quản lý (nhánh thi-lien-khoi): quản lý nhắn lệnh ngắn, bot trả lời đúng số liệu trong phạm vi của họ.

Lệnh (không phân biệt hoa thường và dấu): menu · viec · qua han · chua giao · <MÃ HĐ> · giao MÃ [MÃ...] cho TÊN · chia deu · xong MÃ · khong duoc MÃ lý do ·
tong ket · excel · vai KD|DVKH|KT|BGD (chỉ bản minh hoạ). Việc số lượng lớn thì làm trên app (chọn nhiều dòng, chia đều, Excel); bot lo phần xem nhanh và giao gọn.
Quản lý được nhận ra bằng mã chat Zalo trong danh sách người nhận. Chế độ THỬ ZALO (một người đóng nhiều vai): chat đăng ký ở `data/zalo_thu.json`, vai đang dùng lưu ở
`cai_dat` và đổi bằng lệnh "vai". Không có tên khách hàng trong bất kỳ câu trả lời nào.
"""
from __future__ import annotations

import re
from datetime import datetime

import pandas as pd

from app.lien_khoi import dieu_phoi as dp, luat, mo_phong as mp, nguon, theo_doi as td, zalo_viec as zv

TOI_DA_VIEC_XEM = 6
TEN_VAI = {"KD": "Kinh doanh", "DVKH": "Dịch vụ khách hàng", "KT": "Kỹ thuật", "BGD": "Ban giám đốc"}
XANH, DO, CAM, XAM, LON, NHO = zv.XANH_DUONG, zv.DO, zv.CAM, zv.XAM, zv.CO_LON, zv.CO_NHO
LENH_XONG = re.compile(r"\b(da xong|xong|hoan tat|done|khong lam duoc|khong duoc|chua duoc|ket|da nhan|nhan|ok)\b")


def nhan_dien(nguoi: str) -> tuple[str, str, list[str]]:
    """(mã người, mã chat, các vai thử của chat). Nhận mã người, mã chat trong danh sách người nhận, hoặc mã chat đăng ký thử Zalo (đóng 1-4 vai).
    Không nhận ra thì mã người rỗng."""
    ds = td.nguoi_nhan().fillna("")
    kt = ds[(ds["ma"] == nguoi) | ((ds["chat_id"] == nguoi) & (ds["chat_id"] != ""))]
    if len(kt):
        return str(kt["ma"].iloc[0]), str(kt["chat_id"].iloc[0]), []
    if nguon.la_demo():
        vai = [k for k, c in zv.dai_dien_thu().items() if c == nguoi]
        if vai:
            hien = td.doc_cai_dat(f"vai_zalo:{nguoi}", "BGD")
            hien = hien if hien in vai else ("BGD" if "BGD" in vai else vai[0])
            return zv.MA_DAI_DIEN_THU[hien], nguoi, vai
    return "", "", []


def _ten(ma: str) -> str:
    ds = td.nguoi_nhan().fillna("")
    x = ds[ds["ma"] == ma]
    return str(x["ten"].iloc[0]) if len(x) else ma


def _tin(tieu_de: str, mau=XANH):
    return zv._soan().them(tieu_de, "b", LON, mau)


def _hai_dong(r) -> str:
    return f"{r['so_hd']} – {r['ten_luat']}"


def _con_lai(r) -> str:
    g = abs(r["con_lai_gio"])
    return f"quá {g:.0f} giờ" if r["con_lai_gio"] < 0 else f"còn {g:.0f} giờ"


def _duy_nhat(d: pd.DataFrame) -> list[dict]:
    return list({(r["so_hd"], r["luat"]): r for r in d.to_dict("records")}.values())


# ------------------------------------------------------------------ các lệnh
def menu(ma: str, vai_thu: list[str], hien: str = "") -> str:
    s = _tin("BOT ĐIỀU PHỐI LIÊN KHỐI").them(f"\n{_ten(ma)}", "b")
    if vai_thu:
        s.them(f"\nĐang dùng vai {hien}. Đổi: vai KD · DVKH · KT · BGD", NHO, XAM)
    s.them("\n\nXEM", "b", NHO, XAM)
    for lenh, mo_ta in (("viec", "việc đang mở, việc cần xử lý trước"), ("qua han", "việc quá hạn"), ("chua giao", "việc chưa giao cho ai"),
                        ("MÃ_HĐ", "chi tiết một hợp đồng"), ("tong ket", "số liệu hôm nay"), ("excel", "link tải file Excel")):
        s.them("\n• ").them(lenh, "b").them(f" – {mo_ta}")
    s.them("\n\nLÀM", "b", NHO, XAM)
    for lenh, mo_ta in (("giao MÃ MÃ cho TÊN", "giao việc"), ("chia deu", "chia đều việc hàng chờ cho nhân viên"), ("xong MÃ", "báo đã xong"), ("khong duoc MÃ lý do", "báo không làm được")):
        s.them("\n• ").them(lenh, "b").them(f" – {mo_ta}")
    if vai_thu:
        s.them("\n\nĐIỀU KHIỂN DEMO", "b", NHO, XAM)
        for lenh, mo_ta in (("demo gui", "gửi tin giao việc cho các quản lý"), ("demo lui 25", "lùi đồng hồ 25 giờ"), ("demo nhac", "chạy nhắc và báo giám đốc"), ("demo moi", "làm lại từ đầu")):
            s.them("\n• ").them(lenh, "b").them(f" – {mo_ta}")
    s.them("\n\nViệc nhiều thì làm trên app (chọn nhiều dòng, xuất Excel):", NHO, XAM).them(f"\n{zv.lien_ket_app(ma)}", XANH)
    return zv._cat_tin(s.xong())


def danh_sach_viec(ma: str, loc: str, now: datetime | None = None) -> str:
    """`loc`: mo | qua_han | chua_giao."""
    d = dp.viec_cua(ma, now)
    if loc == "qua_han":
        d = d[d["qua_han"]] if len(d) else d
    elif loc == "chua_giao":
        d = d[d["giao_cho"].fillna("").eq("") & d["trang_thai"].eq("moi")] if len(d) else d
    tieu = {"mo": "VIỆC ĐANG MỞ", "qua_han": "VIỆC QUÁ HẠN", "chua_giao": "VIỆC CHƯA GIAO"}[loc]
    if d.empty:
        return str(_tin(tieu).them(f"\n{_ten(ma)}", "b").them("\n\nKhông có việc nào. Nhắn ").them("viec", "b").them(" để xem tất cả việc đang mở.").xong())
    ds = _duy_nhat(d)
    cao = sum(1 for r in ds if r["muc"] == "Cao")
    s = _tin(tieu).them(f"\n{_ten(ma)}", "b").them(f"\n\n{len(ds)} việc", "b", LON).them("  ·  ").them(f"{cao} mức Cao", "b", LON, DO if cao else XAM)
    s.them("\n\nCẦN XỬ LÝ TRƯỚC", "b", NHO, XAM)
    for i, r in enumerate(ds[:TOI_DA_VIEC_XEM], 1):
        s.them(f"\n{i}. ").them(_hai_dong(r), "b").them(f" ({r['muc']}, {_con_lai(r)})", NHO, DO if r["qua_han"] else XAM)
        s.them(f"\n    {zv._ly_do_ngan(r, 60)}", NHO)
    if len(ds) > TOI_DA_VIEC_XEM:
        s.them(f"\n... còn {len(ds) - TOI_DA_VIEC_XEM} việc nữa", NHO, XAM)
    s.them("\n\n👉 Giao nhanh: ", "b").them("chia deu", "b").them(" hoặc ").them("giao MÃ cho TÊN", "b")
    s.them("\n👉 Xem đủ và xuất Excel:", "b").them(f"\n{zv.lien_ket_app(ma)}", XANH)
    return zv._cat_tin(s.xong())


def chi_tiet(ma: str, codes: list[str], now: datetime | None = None) -> str:
    d = dp.viec_cua(ma, now, chi_mo=False)
    s = None
    for c in codes[:3]:
        x = d[d["so_hd"] == c] if len(d) else d
        if s is None:
            s = _tin("HỢP ĐỒNG")
        s.them(f"\n\n{c}", "b", LON)
        if x.empty:
            s.them("\nKhông thấy trong phạm vi của anh/chị (có thể đã đóng, hoặc thuộc team khác).", NHO, XAM)
            continue
        for r in x.to_dict("records"):
            phu_trach = _ten(r["giao_cho"] or r["nguoi"]) + (" (hàng chờ, chưa có người)" if r["nguoi_goc"] and not r["giao_cho"] else "")
            s.them(f"\n{td.VAI_TRO[r['vai_tro']]} · ", "b").them(f"{r['ten_luat']} ({r['muc']})", "b", DO if r["muc"] == "Cao" else CAM)
            s.them(f"\nPhụ trách: {phu_trach}\nTrạng thái: {td.TRANG_THAI[r['trang_thai']]}" + (f", {_con_lai(r)}" if r["dang_mo"] else ""))
            s.them(f"\nLý do: {zv._ngan(r['ly_do'], 160)}", NHO).them(f"\nĐề xuất: {zv._ngan(r['de_xuat'], 120)}", NHO)
    return zv._cat_tin(s.xong())


def tong_ket(ma: str, now: datetime | None = None) -> str:
    t = dp.tong_ket(ma, now)
    s = _tin("TỔNG KẾT HÔM NAY").them(f"\n{_ten(ma)}", "b")
    s.them(f"\n\n{t['mo']} việc đang mở", "b", LON).them("  ·  ").them(f"{t['qua_han']} quá hạn", "b", LON, DO if t["qua_han"] else XAM)
    s.them(f"\n{t['cao']} mức Cao · {t['chua_giao']} chưa giao · {t['dang_lam']} đang làm", NHO)
    s.them(f"\nTrong 24 giờ qua: {t['xong_24h']} việc xong, {t['khong_24h']} không làm được", NHO)
    if t["theo_team"]:
        s.them("\n\nTHEO TỪNG TEAM", "b", NHO, XAM)
        for x in t["theo_team"][:6]:
            s.them("\n• ").them(x["ten"], "b").them(f": {x['mo']} việc", ).them(f", {x['qua_han']} quá hạn" if x["qua_han"] else "", DO)
    s.them("\n\n👉 Chi tiết:", "b").them(f"\n{zv.lien_ket_app(ma)}", XANH)
    return zv._cat_tin(s.xong())


def giao(ma: str, chu_goc: str, now: datetime | None = None) -> str:
    """"giao MÃ [MÃ...] cho TÊN"."""
    codes = [m.upper() for m in zv.MA_HD.findall(chu_goc)]
    sau = re.split(r"\bcho\b", dp.bo_dau(zv.MA_HD.sub(" ", chu_goc)), maxsplit=1)
    ten = sau[1].strip() if len(sau) == 2 else ""
    if not codes or not ten:
        return 'Nhắn đủ mã hợp đồng và tên người nhận, ví dụ: giao MHAAA0001 MHAAA0002 cho Sale 01. Muốn giao nhiều việc một lần thì nhắn "chia deu" hoặc làm trên app.'
    ds, ghi = dp.tim_nguoi(ten, ma)
    if ghi == "khong":
        return f'Em không thấy "{ten}" trong team của anh/chị. Nhắn lại tên hoặc mã người (ví dụ sale_01).'
    if ghi == "nhieu":
        return f'Có {len(ds)} người khớp "{ten}": ' + "; ".join(f"{r['ten']} ({r['ma']})" for r in ds[:6]) + ". Anh/chị nhắn lại cho rõ hơn (tên đầy đủ hoặc mã)."
    r = dp.giao_theo_ma(ma, codes, ds[0], now)
    kq = []
    if r["giao"]:
        kq.append(f"Đã giao {r['giao']} phần việc ({', '.join(r['ma_giao'])}) cho {ds[0]['ten']}.")
    if r["khac_khoi"]:
        kq.append(f"{', '.join(r['khac_khoi'])}: không có phần việc thuộc khối {ds[0]['khoi']} của {ds[0]['ten']}.")
    if r["khong_thay"]:
        kq.append(f"Không thấy việc đang mở của {', '.join(r['khong_thay'])} trong phạm vi của anh/chị.")
    return "\n".join(kq)


def chia_deu(ma: str, now: datetime | None = None) -> str:
    r = dp.chia_deu(ma, now)
    if not r["giao"] and not r["thieu_nguoi"]:
        return "Không còn việc hàng chờ nào chưa giao. Nhắn viec để xem việc đang mở."
    dong = [f"Đã chia đều {r['giao']} phần việc hàng chờ:"] + [f"• {t}: {n} việc" for t, n in r["theo_nguoi"].items()]
    if r["thieu_nguoi"]:
        dong.append(f"{r['thieu_nguoi']} việc chưa chia được vì team không có nhân viên đúng khối.")
    return "\n".join(dong)


def demo(chu_goc: str, vai_thu: list[str]) -> str:
    """Điều khiển kịch bản demo ngay từ Zalo (CHỈ khi chạy thử Zalo, tức bộ minh hoạ + người thử đã đăng ký): `demo gui` (lấy việc mới và gửi tin tổng hợp cho các quản lý),
    `demo nhac` (nhắc quá hạn và báo giám đốc), `demo lui [giờ]` (lùi đồng hồ minh hoạ, mặc định 25 giờ), `demo moi` (làm lại từ đầu, nạp 14 ngày mô phỏng)."""
    if not vai_thu or zv.kenh() != "zalo_thu":
        return "Lệnh demo chỉ dùng khi chạy thử Zalo với dữ liệu minh hoạ."
    g = dp.bo_dau(chu_goc)
    if re.search(r"\bmoi\b|\blam lai\b|\breset\b", g):
        r = mp.chuan_bi_demo()
        return f"Đã làm lại demo từ đầu: {r['mo_phong']} phần việc lịch sử và {r['moi']} việc mới hôm nay (chưa gửi). Nhắn demo gui để gửi tin cho các quản lý."
    if re.search(r"\bgui\b", g):
        td.dong_bo(luat.danh_sach_viec())
        r = zv.gui_viec_moi()
        return f"Đã gửi {r['tin']} tin tổng hợp cho {r['nguoi']} quản lý ({r['viec']} phần việc). Tin của 4 vai đại diện về chat này, mỗi tin ghi rõ gửi thay cho ai."
    if re.search(r"\bnhac\b", g):
        r = zv.chay_nhac()
        return f"Đã nhắc quản lý {r['nhac']} phần việc quá hạn và báo giám đốc chi nhánh {r.get('viec_bao', 0)} việc quá {td.cau_hinh_gio()[1]} giờ chưa xong."
    if re.search(r"\blui\b", g):
        n = re.search(r"\d+", g)
        gio = td.them_gio_gia_lap(float(n.group()) if n else 25.0)
        r = mp.tien_thoi_gian()
        return f"Đã lùi đồng hồ minh hoạ, tổng cộng {gio:.0f} giờ. Người nhận mô phỏng đã làm xong {r['xong']} phần việc, không làm được {r['khong_lam_duoc']}, mới nhận {r['da_nhan']}. Nhắn demo nhac để chạy nhắc."
    return "Lệnh demo: demo gui · demo nhac · demo lui 25 · demo moi."


def doi_vai(nguoi: str, vai_thu: list[str], chu: str) -> str:
    if not vai_thu:
        return "Lệnh vai chỉ dùng khi thử nghiệm một người đóng nhiều vai."
    muon = next((v for v in TEN_VAI if re.search(rf"\b{v.lower()}\b", dp.bo_dau(chu))), "")
    if not muon:
        return "Nhắn: vai KD, vai DVKH, vai KT hoặc vai BGD."
    if muon not in vai_thu:
        return f"Chat này chưa đăng ký vai {muon}. Các vai đang có: {', '.join(vai_thu)}."
    td.ghi_cai_dat(f"vai_zalo:{nguoi}", muon)
    return f"Đã chuyển sang vai {muon} ({_ten(zv.MA_DAI_DIEN_THU[muon])}). Nhắn viec để xem việc của vai này."


# ------------------------------------------------------------------ cửa vào
def xu_ly(nguoi: str, chu: str, now: datetime | None = None) -> str:
    """Quản lý (mã người hoặc mã chat Zalo) nhắn một câu: nhận diện, chạy lệnh, trả lời đúng chat đó và ghi hộp thư. Trả về nội dung câu trả lời."""
    now = now or td.bay_gio()
    ma, chat_id, vai_thu = nhan_dien(nguoi)
    td.ghi_hop_thu(ma or nguoi, chat_id, "nhan_tu_nguoi", chu or "", zv.kenh(), "da_nhan", now)
    noi = _tra_loi(ma, nguoi, vai_thu, chu or "", now)
    zv.tra_loi_chat(ma, chat_id, noi, now)
    return str(noi)


def _tra_loi(ma: str, nguoi: str, vai_thu: list[str], chu: str, now: datetime):
    if not ma:
        return "Em chưa biết anh/chị là ai trong danh sách người nhận việc. Anh/chị nhờ quản trị thêm mã chat này vào danh sách."
    ds = td.nguoi_nhan().fillna("")
    vt = str(ds.loc[ds["ma"] == ma, "vai_tro"].iloc[0]) if (ds["ma"] == ma).any() else ""
    if vt not in td.VAI_TRO_QUAN_LY:
        if LENH_XONG.search(dp.bo_dau(zv.MA_HD.sub(" ", chu))):                  # nhân viên vẫn báo "xong MÃ" cho việc của mình (cách cũ)
            return zv._ap_dung(ma, chu, now)
        return "Bot này gửi việc cho quản lý (trưởng phòng, trưởng nhóm, điều hành). Anh/chị xem việc của mình qua quản lý trực tiếp."
    g = dp.bo_dau(zv.MA_HD.sub(" ", chu))
    codes = list(dict.fromkeys(m.upper() for m in zv.MA_HD.findall(chu)))
    hien = next((k for k, m in zv.MA_DAI_DIEN_THU.items() if m == ma), "")
    if g in ("", "menu", "help", "huong dan", "hi", "hello", "xin chao", "bat dau", "/start", "?", "lenh") and not codes:
        return menu(ma, vai_thu, hien)
    if re.match(r"^vai\b", g):
        return doi_vai(nguoi, vai_thu, chu)
    if re.match(r"^demo\b", g):
        return demo(chu, vai_thu)
    if re.search(r"\b(excel|xlsx|tai file|xuat file|xuat)\b", g):
        return f"File Excel việc đang mở của anh/chị (mở bằng tài khoản Quản trị trên app, có sheet riêng từng nhân viên để gửi thẳng):\n{zv.lien_ket_excel(ma)}"
    if re.search(r"\b(tong ket|bao cao|tong quan|tom tat|so lieu)\b", g):
        return tong_ket(ma, now)
    if re.search(r"\bqua han\b", g):
        return danh_sach_viec(ma, "qua_han", now)
    if re.search(r"\bchua giao\b", g):
        return danh_sach_viec(ma, "chua_giao", now)
    if re.search(r"\bchia (deu|ra)\b", g):
        return chia_deu(ma, now)
    if re.match(r"^giao\b", g):
        return giao(ma, chu, now)
    if LENH_XONG.search(g):
        return zv._ap_dung(ma, chu, now)
    if re.search(r"\b(viec|danh sach|cong viec|ton)\b", g) and not codes:
        return danh_sach_viec(ma, "mo", now)
    if codes:
        return chi_tiet(ma, codes, now)
    return "Em chưa hiểu câu này. Nhắn menu để xem các lệnh."


def gui_tong_ket(now: datetime | None = None) -> dict:
    """Bot chủ động gửi TỔNG KẾT cho từng quản lý còn việc (mỗi người một tin mỗi ngày, gửi rồi thì không gửi lại). Chạy từ script tự động (`--tong-ket`)."""
    now = now or td.bay_gio()
    ngay = (pd.Timestamp(now) + pd.Timedelta(hours=7)).strftime("%Y-%m-%d")
    ds = td.nguoi_nhan().fillna("")
    n = 0
    for r in ds[ds["vai_tro"].isin(td.VAI_TRO_QUAN_LY)].to_dict("records"):
        khoa = f"tong_ket:{r['ma']}"
        if td.doc_cai_dat(khoa) == ngay or dp.viec_cua(r["ma"], now).empty:
            continue
        if zv._da_giao(zv._gui(r["ma"], r["chat_id"], "tong_ket", tong_ket(r["ma"], now), now)):
            td.ghi_cai_dat(khoa, ngay)
            n += 1
    return {"tin": n}
