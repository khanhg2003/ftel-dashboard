"""Đặt / gỡ / xem webhook của bot Zalo GIAO VIỆC LIÊN KHỐI (bot RIÊNG, không dùng chung với Bản tin hay Tra cứu giá: mỗi bot chỉ gắn được một webhook).

Chạy:  python scripts/lien_khoi_webhook.py dat | go | xem

Đọc từ biến môi trường: LIEN_KHOI_ZALO_TOKEN (token bot), APP_URL (địa chỉ app, https), APP_SECRET_KEY. Địa chỉ webhook = APP_URL + /api/lien-khoi/zalo-webhook.
Đường webhook chỉ nhận tin khi đã đặt thêm LIEN_KHOI_ZALO_GUI=1. Không in token ra màn hình.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main(lenh: str) -> int:
    from app import zalo_bot
    from app.lien_khoi import zalo_viec
    token = os.environ.get("LIEN_KHOI_ZALO_TOKEN", "").strip()
    if not token:
        print("Chưa đặt biến môi trường LIEN_KHOI_ZALO_TOKEN.")
        return 1
    try:
        if lenh == "xem":
            url = zalo_bot.thong_tin_webhook(token)["url"]
            mong = zalo_viec.url_webhook()
            print(f"Webhook hiện tại: {url or '(chưa đặt)'}")
            print("Khớp với app." if url and url == mong else f"Địa chỉ mong muốn: {mong or '(chưa đặt APP_URL)'}")
        elif lenh == "go":
            zalo_bot.go_webhook(token)
            print("Đã gỡ webhook.")
        elif lenh == "dat":
            url = zalo_viec.url_webhook()
            if not url or not url.startswith("https://"):
                print("Cần đặt APP_URL bắt đầu bằng https:// (vd https://ten-app.duckdns.org).")
                return 1
            kq = zalo_bot.dat_webhook(url, zalo_viec.khoa_webhook(), token)
            print(f"Đã đặt webhook: {kq['url']}")
            if not kq["kiem_tra_ok"]:
                print(f"Zalo gọi thử chưa được ({kq['ket_qua_kiem_tra'] or 'không rõ lý do'}). Hãy chắc app đã triển khai bản mới và đã đặt LIEN_KHOI_ZALO_GUI=1.")
        else:
            print(__doc__)
            return 1
    except zalo_bot.LoiZalo as e:
        print(f"Lỗi: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
