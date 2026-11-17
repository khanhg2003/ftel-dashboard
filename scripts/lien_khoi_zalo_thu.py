"""Đăng ký người THỬ ZALO cho hướng điều hành liên khối (nhánh thi-lien-khoi): mỗi người đại diện một khối (KD, DVKH, KT) hoặc Ban giám đốc (BGD).

Chạy:  python scripts/lien_khoi_zalo_thu.py dang-ky | xem | thu | go

- dang-ky: chờ tin nhắn gửi cho bot. Người thử nhắn các chữ KD, DVKH, KT, BGD (có thể nhiều chữ trong một tin, hoặc ALL cho cả bốn vai). Script ghi mã chat của họ vào `data/zalo_thu.json` (cùng cách `getUpdates`, không cần địa chỉ https).
- xem: in danh sách đã đăng ký (che bớt mã chat).
- thu: gửi một tin thử cho từng người đã đăng ký.
- go: xoá file đăng ký (tắt chế độ thử).

Cần biến môi trường LIEN_KHOI_ZALO_TOKEN (token của bot RIÊNG của hướng liên khối). Không in token ra màn hình. Bot đang gắn webhook thì không dùng getUpdates được:
chạy `python scripts/lien_khoi_webhook.py go` trước.
"""
from __future__ import annotations

import os
import re
import sys
import time
import unicodedata
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TEN_VAI = {"KD": "Kinh doanh", "DVKH": "Dịch vụ khách hàng", "KT": "Kỹ thuật", "BGD": "Ban giám đốc chi nhánh"}


def _bo_dau(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def _che(cid: str) -> str:
    return cid if len(cid) <= 6 else cid[:3] + "…" + cid[-3:]


def _doc() -> dict:
    from app.lien_khoi import zalo_viec
    return zalo_viec.dai_dien_thu()


def _ghi(d: dict) -> None:
    """Ghi đăng ký: người vừa đăng ký đứng đầu danh sách của vai, những người khác (kể cả nhóm Zalo) và khoá QUAN_TRI được giữ nguyên."""
    from app.lien_khoi import zalo_viec
    ds = zalo_viec.danh_sach_thu()
    for k, cid in d.items():
        ds[k] = [cid] + [x for x in ds.get(k, []) if x != cid]
    zalo_viec.ghi_dang_ky_thu(ds)


def _cac_su_kien(kq: dict) -> list[dict]:
    r = kq.get("result")
    if isinstance(r, list):
        return [x for x in r if isinstance(x, dict)]
    return [r] if isinstance(r, dict) and r else []


def _cac_vai(chu: str) -> list[str]:
    """Các vai trong một tin: mỗi chữ KD / DVKH / KT / BGD (không phân biệt hoa thường, dấu, xuống dòng hay dấu phẩy); "ALL" hoặc "tất cả" là cả bốn vai."""
    goc = _bo_dau(chu).strip()
    chu_ = [t for t in re.split(r"[\s,;.]+", goc) if t]
    if "tat ca" in goc or any(t in ("all", "tatca") for t in chu_):
        return list(TEN_VAI)
    anh_xa = {"kd": "KD", "dvkh": "DVKH", "kt": "KT", "bgd": "BGD"}
    return list(dict.fromkeys(anh_xa[t] for t in chu_ if t in anh_xa))


def dang_ky(token: str) -> int:
    from app import zalo_bot
    from app.zalo_gia import doc_tin
    try:
        url = zalo_bot.thong_tin_webhook(token).get("url")
    except zalo_bot.LoiZalo as e:
        if "404" not in str(e):                                       # Zalo trả 404 khi bot chưa đặt webhook: đó là trường hợp bình thường
            print(f"Không kiểm tra được bot: {e}")
            return 1
        url = None
    if url:
        print("Bot đang gắn webhook nên không đọc tin bằng getUpdates được. Chạy trước: python scripts/lien_khoi_webhook.py go")
        return 1
    d = _doc()
    print("Chờ người thử nhắn cho bot: KD, DVKH, KT, BGD (nhiều chữ trong một tin được, hoặc ALL cho cả bốn vai). Nhấn Ctrl+C để dừng.")
    print("Đã có:", ", ".join(f"{k}={_che(v)}" for k, v in d.items()) or "(chưa ai)")
    try:
        while set(d) < set(TEN_VAI):
            try:
                kq = zalo_bot._goi_api("getUpdates", {"timeout": "30"}, han=45, token=token)
            except zalo_bot.LoiZalo as e:
                if "408" in str(e):                                       # hết thời gian chờ mà chưa có tin mới: bình thường với long polling, hỏi tiếp ngay
                    continue
                print(f"Zalo báo: {e}. Thử lại sau 5 giây.")
                time.sleep(5)
                continue
            for sk in _cac_su_kien(kq):
                t = doc_tin(sk)
                if not t:
                    print(f"Nhận một sự kiện nhưng không đọc được nội dung tin chữ: {str(sk.get('event_name') or '(không rõ loại)')[:60]}")
                    continue
                print(f"Nhận tin từ {_che(t['chat_id'])} ({t['loai_chat'] or 'không rõ loại chat'}): {t['text'][:40]!r}")
                if t["la_bot"] or t["loai_chat"] not in ("", "PRIVATE"):
                    continue
                vais = _cac_vai(t["text"])
                if not vais:
                    zalo_bot.gui_tin(t["chat_id"], "Bạn nhắn giúp các chữ để đăng ký vai thử nghiệm: KD (Kinh doanh), DVKH, KT (Kỹ thuật), BGD (Ban giám đốc), hoặc ALL để nhận cả bốn vai.", token=token)
                    continue
                for vai in vais:
                    d[vai] = t["chat_id"]
                _ghi(d)
                zalo_bot.gui_tin(t["chat_id"], "Đã ghi nhận bạn là đại diện: " + ", ".join(TEN_VAI[v] for v in vais) + ". Dữ liệu trong lần thử hệ thống Điều hành liên khối là dữ liệu minh hoạ, không có khách hàng thật.", token=token)
                print(f"Đã ghi {', '.join(vais)} = {_che(t['chat_id'])}. Còn thiếu: {', '.join(sorted(set(TEN_VAI) - set(d))) or '(đủ)'}")
    except KeyboardInterrupt:
        print("\nĐã dừng.")
    print("Đã đăng ký:", ", ".join(f"{k}={_che(v)}" for k, v in d.items()) or "(chưa ai)")
    return 0


def main(lenh: str) -> int:
    if lenh == "xem":
        d = _doc()
        for k in TEN_VAI:
            print(f"{k:5} {TEN_VAI[k]:28} {_che(d[k]) if k in d else '(chưa đăng ký)'}")
        return 0
    if lenh == "go":
        from app.lien_khoi import zalo_viec
        p = zalo_viec.duong_dan_thu()
        if p.exists():
            p.unlink()
        print("Đã xoá file đăng ký: chế độ thử Zalo tắt.")
        return 0
    token = os.environ.get("LIEN_KHOI_ZALO_TOKEN", "").strip()
    if not token:
        print("Chưa đặt biến môi trường LIEN_KHOI_ZALO_TOKEN.")
        return 1
    if lenh == "dang-ky":
        return dang_ky(token)
    if lenh == "thu":
        from app import zalo_bot
        d = _doc()
        if not d:
            print("Chưa có ai đăng ký. Chạy: python scripts/lien_khoi_zalo_thu.py dang-ky")
            return 1
        for k, cid in d.items():
            try:
                zalo_bot.gui_tin(cid, f"[THỬ NGHIỆM] Tin thử từ hệ thống Điều hành liên khối cho {TEN_VAI[k]}. Nếu bạn đọc được tin này là đã thông.", token=token)
                print(f"{k}: đã gửi")
            except zalo_bot.LoiZalo as e:
                print(f"{k}: lỗi - {e}")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
