"""Cho bot Zalo liên khối NGHE quản lý nhắn lệnh và trả lời (hai chiều), bằng getUpdates (không cần địa chỉ https). Nhánh thi-lien-khoi.

    python scripts/lien_khoi_zalo_nghe.py

Cần LIEN_KHOI_ZALO_TOKEN (bot riêng). Chạy minh hoạ cần thêm LIEN_KHOI_ZALO_GUI=1 và đã đăng ký người thử (scripts/lien_khoi_zalo_thu.py dang-ky) để bot trả lời được.
Dữ liệu và trạng thái dùng chung file với trang web. Bot đang gắn webhook thì chạy `python scripts/lien_khoi_webhook.py go` trước (webhook và getUpdates không dùng chung được).
Lệnh quản lý nhắn: xem `app/lien_khoi/zalo_lenh.py` (menu, viec, qua han, chua giao, MÃ_HĐ, giao MÃ cho TÊN, chia deu, xong MÃ, tong ket, excel, vai ...). Dừng: Ctrl+C.
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GOC = Path(__file__).resolve().parent.parent
os.chdir(GOC)
sys.path.insert(0, str(GOC))
os.environ.setdefault("LIEN_KHOI_NGUON", "demo")
if os.environ["LIEN_KHOI_NGUON"].strip().lower() == "demo":
    (GOC / "data").mkdir(exist_ok=True)
    os.environ.setdefault("DATABASE_URL", "sqlite:///" + (GOC / "data" / "demo_lien_khoi.db").as_posix())


def _che(cid: str) -> str:
    return cid if len(cid) <= 6 else cid[:3] + "…" + cid[-3:]


def bo_mention(chu: str) -> str:
    """Trong nhóm Zalo người dùng gõ "@Tên bot lệnh": bỏ phần @tên bot (tên lấy từ `LIEN_KHOI_TEN_BOT`, mặc định tên bot demo) và mọi chữ @ đứng đầu."""
    ten = os.environ.get("LIEN_KHOI_TEN_BOT", "Bot Điều Hành Liên Khối")
    chu = re.sub(r"@?\s*" + re.escape(ten), " ", chu or "", flags=re.IGNORECASE)
    return re.sub(r"^\s*(@\S+\s*)+", "", chu).strip()


def xu_ly_mot(sk: dict) -> str | None:
    """Một sự kiện Zalo -> trả lời nếu là tin chữ của người thật, trong chat riêng hoặc NHÓM (nhóm phải @ bot). Trả về dòng nhật ký (hoặc None nếu bỏ qua)."""
    from app.lien_khoi import zalo_viec as zv
    from app.zalo_gia import doc_tin
    t = doc_tin(sk)
    if not t or t["la_bot"]:
        return None
    nhom = t["loai_chat"] not in ("", "PRIVATE")
    chu = bo_mention(t["text"]) if nhom else t["text"]
    zv.xu_ly_tra_loi(t["chat_id"], chu or "menu", la_nhom=nhom)
    return f"{'nhóm ' if nhom else ''}{_che(t['chat_id'])}: {chu[:50]!r}"


def main() -> int:
    token = os.environ.get("LIEN_KHOI_ZALO_TOKEN", "").strip()
    if not token:
        print("Chưa đặt biến môi trường LIEN_KHOI_ZALO_TOKEN.")
        return 1
    from app import zalo_bot
    from app.lien_khoi import zalo_viec as zv
    print(f"Bot đang nghe (kênh {zv.kenh()}). Quản lý nhắn menu để xem lệnh. Ctrl+C để dừng.")
    try:
        while True:
            try:
                kq = zalo_bot._goi_api("getUpdates", {"timeout": "30"}, han=45, token=token)
            except zalo_bot.LoiZalo as e:
                if "408" in str(e):                                              # chưa có tin mới trong 30 giây: bình thường
                    continue
                print(f"Zalo báo: {e}. Thử lại sau 5 giây.")
                time.sleep(5)
                continue
            r = kq.get("result")
            for sk in ([x for x in r if isinstance(x, dict)] if isinstance(r, list) else [r] if isinstance(r, dict) and r else []):
                try:
                    dong = xu_ly_mot(sk)
                except Exception as e:                                           # một tin lỗi không làm bot dừng
                    print(f"Lỗi khi xử lý tin: {type(e).__name__}: {str(e)[:120]}")
                    continue
                if dong:
                    print("Đã trả lời", dong)
                elif os.environ.get("LIEN_KHOI_GHI_SU_KIEN") == "1":                     # dò dạng tin của nhóm Zalo (Beta): ghi sự kiện không đọc được, đã cắt ngắn
                    print("Sự kiện bỏ qua:", str(sk)[:300].replace(token, "***"))
    except KeyboardInterrupt:
        print("\nĐã dừng.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
