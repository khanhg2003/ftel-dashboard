"""Chạy TỰ ĐỘNG hướng điều hành liên khối: bot tự lấy việc từ các luật, gửi tin tổng hợp cho quản lý, nhắc quá hạn và báo giám đốc chi nhánh (không phải bấm nút).

    python scripts/lien_khoi_chay_tu_dong.py [--moi PHUT] [--gio-moi-vong GIO] [--so-vong N] [--chuan-bi]

- Mỗi vòng làm đủ ba bước như bấm tay ở tab Theo dõi & Zalo: lấy việc từ các luật -> gửi việc mới -> nhắc quá hạn và báo giám đốc chi nhánh.
  Việc đã gửi / đã nhắc / đã báo thì KHÔNG gửi lại, nên chạy lặp an toàn.
- `--moi PHUT`: nghỉ bao nhiêu phút giữa hai vòng (mặc định 15).
- `--tong-ket`: gửi thêm tin tổng kết cho từng quản lý còn việc (mỗi người một tin mỗi ngày).
- `--lich`: CHẾ ĐỘ LỊCH dùng thật, chỉ gửi trong khung giờ làm việc (xem `trong_gio_lam_viec`), từ 17:30 gửi thêm tổng kết. Ví dụ: `python scripts/lien_khoi_chay_tu_dong.py --lich --moi 15`.
- `--tro-ly`: chạy thêm TRỢ LÝ ĐIỀU HÀNH (`app/lien_khoi/tro_ly_dieu_hanh.py`): mỗi ngày một lần quét và đề xuất cho người quyết, mỗi vòng nhắc quyết / báo cấp trên / kiểm chứng. Tự bật khi có `--lich`.
- `--so-vong N`: dừng sau N vòng (mặc định 0 = chạy mãi, dừng bằng Ctrl+C).
- CHỈ minh hoạ: `--chuan-bi` làm lại từ đầu (xoá trạng thái cũ, nạp 14 ngày mô phỏng và việc hôm nay) trước vòng đầu;
  `--gio-moi-vong GIO` cho đồng hồ minh hoạ chạy tới GIO giờ trước mỗi vòng (người nhận mô phỏng làm việc theo đó). Ví dụ `--moi 1 --gio-moi-vong 24`: mỗi PHÚT thật là một NGÀY của
  bản minh hoạ, nên bot tự gửi tin giao việc (vòng 1), nhắc (vòng 2) và báo giám đốc chi nhánh (vòng 3) mà anh chỉ ngồi xem.
- Kênh gửi theo cấu hình như trên app (`zalo_viec.kenh()`): minh hoạ mặc định chỉ ghi hộp thư; chế độ THỬ ZALO gửi thật tới người đã đăng ký.
Dùng chung file trạng thái với trang web, nên có thể mở trang cùng lúc để xem kết quả.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GOC = Path(__file__).resolve().parent.parent
os.chdir(GOC)
sys.path.insert(0, str(GOC))
os.environ.setdefault("LIEN_KHOI_NGUON", "demo")                      # mặc định CHẠY MINH HOẠ; muốn dùng dữ liệu thật phải đặt LIEN_KHOI_NGUON=that rõ ràng
if os.environ["LIEN_KHOI_NGUON"].strip().lower() == "demo":
    (GOC / "data").mkdir(exist_ok=True)
    os.environ.setdefault("DATABASE_URL", "sqlite:///" + (GOC / "data" / "demo_lien_khoi.db").as_posix())      # không chạm database của app


def mot_vong(gio_moi_vong: float = 0.0, tong_ket: bool = False, tro_ly: bool = False) -> str:
    """Một vòng tự động; trả về dòng tóm tắt. `gio_moi_vong` > 0 chỉ dùng được ở chế độ minh hoạ."""
    from app.lien_khoi import luat, mo_phong as mp, nguon, theo_doi as td, zalo_lenh, zalo_viec as zv
    if gio_moi_vong > 0:
        if not nguon.la_demo():
            raise RuntimeError("--gio-moi-vong chỉ dùng được ở chế độ minh hoạ (LIEN_KHOI_NGUON=demo).")
        td.them_gio_gia_lap(gio_moi_vong)
        mp.tien_thoi_gian()
    dong_bo = td.dong_bo(luat.danh_sach_viec())
    gui = zv.gui_viec_moi()
    nhac = zv.chay_nhac()
    tk = f" · tổng kết {zalo_lenh.gui_tong_ket()['tin']} tin" if tong_ket else ""
    if tro_ly:                                                           # trợ lý điều hành: buổi sáng một lần mỗi ngày, nhắc quyết và kiểm chứng mỗi vòng
        from app.lien_khoi import tro_ly_dieu_hanh as tdh
        t = tdh.vong_tu_dong()
        tk += (f" · trợ lý điều hành: đề xuất mới {t['moi']} ({t['ai']} AI, {t['luat']} luật), đã gửi {t['gui']}, nhắc {t['nhac']}, báo cấp trên {t['bao_cap_tren']}, "
               f"kiểm chứng {t['kiem_chung']}")
    return (f"giờ hệ thống {td.bay_gio():%d/%m %H:%M} · kênh {zv.kenh()} · việc mới {dong_bo['moi']} · đã gửi {gui['tin']} tin cho {gui['nguoi']} quản lý ({gui['viec']} việc) · "
            f"nhắc {nhac['nhac']} việc quá hạn · báo giám đốc {nhac.get('viec_bao', nhac['bao_quan_ly'])} việc{tk}")


def trong_gio_lam_viec(luc: datetime, tu: str = "08:00", den: str = "18:00", bo_chu_nhat: bool = True) -> bool:
    """`luc` là giờ Việt Nam. Chế độ lịch chỉ gửi trong khung giờ làm việc (mặc định 08:00 - 18:00, bỏ Chủ nhật)."""
    if bo_chu_nhat and luc.weekday() == 6:
        return False
    return tu <= f"{luc:%H:%M}" < den


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Chạy tự động điều hành liên khối")
    ap.add_argument("--moi", type=float, default=15, help="nghỉ bao nhiêu phút giữa hai vòng")
    ap.add_argument("--so-vong", type=int, default=0, help="dừng sau N vòng (0 = chạy mãi)")
    ap.add_argument("--gio-moi-vong", type=float, default=0, help="CHỈ minh hoạ: cho đồng hồ chạy tới thêm GIO giờ trước mỗi vòng")
    ap.add_argument("--tong-ket", action="store_true", help="mỗi vòng gửi thêm tin TỔNG KẾT cho từng quản lý (mỗi người một tin mỗi ngày)")
    ap.add_argument("--lich", action="store_true", help="CHẾ ĐỘ LỊCH (dùng thật): mỗi --moi phút trong khung giờ làm việc (--tu 08:00 --den 18:00, bỏ Chủ nhật) lấy việc từ các luật, gửi việc mới, nhắc 24 giờ, báo 48 giờ; từ 17:30 gửi thêm tổng kết (mỗi quản lý một tin mỗi ngày). Ngoài khung giờ thì chờ")
    ap.add_argument("--tro-ly", action="store_true", help="chạy thêm TRỢ LÝ ĐIỀU HÀNH (đề xuất mỗi sáng, nhắc quyết, kiểm chứng); tự bật khi dùng --lich")
    ap.add_argument("--tu", default="08:00", help="giờ bắt đầu của chế độ lịch (giờ Việt Nam)")
    ap.add_argument("--den", default="18:00", help="giờ kết thúc của chế độ lịch (giờ Việt Nam)")
    ap.add_argument("--chuan-bi", action="store_true", help="CHỈ minh hoạ: làm lại từ đầu trước vòng đầu")
    a = ap.parse_args(argv)
    if a.chuan_bi:
        from app.lien_khoi import mo_phong as mp, nguon
        if not nguon.la_demo():
            print("--chuan-bi chỉ dùng được ở chế độ minh hoạ (LIEN_KHOI_NGUON=demo).")
            return 1
        r = mp.chuan_bi_demo()
        print(f"Đã chuẩn bị: {r['mo_phong']} phần việc mô phỏng của 14 ngày qua và {r['moi']} phần việc mới hôm nay.")
    vong = 0
    try:
        while True:
            vong += 1
            if a.lich:
                from datetime import timedelta, timezone
                vn = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=7))).replace(tzinfo=None)
                if not trong_gio_lam_viec(vn, a.tu, a.den):
                    vong -= 1
                    time.sleep(60)
                    continue
                a.tong_ket = f"{vn:%H:%M}" >= "17:30"
            gio = a.gio_moi_vong if vong > 1 else 0.0                          # vòng đầu chạy ngay ở "hôm nay"; các vòng sau mới cho đồng hồ chạy tới
            try:
                print(f"[{datetime.now():%H:%M:%S}] Vòng {vong}: {mot_vong(gio, a.tong_ket, a.tro_ly or a.lich)}", flush=True)
            except RuntimeError as e:
                print(str(e))
                return 1
            if a.so_vong and vong >= a.so_vong:
                break
            time.sleep(max(a.moi, 0) * 60)
    except KeyboardInterrupt:
        print("\nĐã dừng.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
