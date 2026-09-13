"""Đối chiếu con số báo cáo giữa database trên máy và Supabase - phải khớp tuyệt đối.

Chạy:  python scripts/doi_chieu_supabase.py

Không chỉ so số dòng mà chạy đúng các hàm tính báo cáo của app ở hai nơi rồi so từng con số:
tổng Báo cáo Tổng, từng phòng, Tracking ngày, So sánh kỳ, Nhân sự, Chất lượng dữ liệu.
Khớp hết thì mới được đổi app sang dùng Supabase.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GOC = Path(__file__).resolve().parent.parent


def _tinh() -> dict:
    """Chạy trong tiến trình con: DATABASE_URL đã được đặt sẵn."""
    sys.path.insert(0, str(GOC))
    from app.admin_service import acc_la, chua_gan_phong, ton_dong_lau
    from app.hr_metrics import canh_bao_nhan_su, hieu_suat_nhan_su, thoi_gian_trien_khai
    from app.metrics import (cac_ngay_co_du_lieu, cac_thang_co_du_lieu, so_sanh_acc,
                             tracking_table)
    from app.overview import bang_tong_quan

    kq: dict = {}
    thangs = cac_thang_co_du_lieu()
    kq["thang"] = thangs
    kq["so_ngay"] = len(cac_ngay_co_du_lieu())
    for t in thangs[:2]:
        df, ngay = bang_tong_quan(t)
        so = ["online", "vvip", "camera", "cnql", "fpl_combo", "so_ton", "ngay_online"]
        kq[f"tong_{t}"] = {r["phong"]: [int(r[c] or 0) for c in so]
                           for r in df.to_dict("records")}
        tk = tracking_table(t, "online")
        kq[f"tracking_{t}"] = {r["phong"] or r["bay"]: int(r["Tổng"])
                               for r in tk.to_dict("records")}
        kq[f"nhansu_{t}"] = int(hieu_suat_nhan_su(t).online.sum())
        kq[f"canhbao_{t}"] = len(canh_bao_nhan_su(t))
        kq[f"trienkhai_{t}"] = round(float(thoi_gian_trien_khai(t).tb_ngay.sum() or 0), 1)
        kq[f"chuagan_{t}"] = int(chua_gan_phong(t).so_hd.sum() or 0)
        kq[f"accla_{t}"] = len(acc_la(t))
    kq["tondong"] = int(ton_dong_lau(7).so_hd.sum() or 0)
    d2 = so_sanh_acc(("2026-08-16", "2026-08-22"), ("2026-08-23", "2026-08-29"))
    kq["d2"] = {r["acc"]: [int(r["ky1"]), int(r["ky2"])] for r in d2.head(30).to_dict("records")}
    return kq


def _chay(url: str) -> dict:
    env = {**os.environ, "DATABASE_URL": url, "PYTHONIOENCODING": "utf-8"}
    env.pop("VERCEL", None)
    kq = subprocess.run([sys.executable, __file__, "--con"], env=env, cwd=str(GOC),
                        capture_output=True, text=True, encoding="utf-8")
    if kq.returncode != 0:
        sys.exit(f"Lỗi khi tính trên {url.split('@')[-1]}:\n{kq.stderr[-3000:]}")
    return json.loads(kq.stdout.strip().splitlines()[-1])


def main() -> None:
    from dotenv import load_dotenv
    load_dotenv(GOC / ".env")
    sb = os.getenv("SUPABASE_DB_URL", "").strip()
    if not sb:
        sys.exit("Chưa có SUPABASE_DB_URL trong file .env")
    may = f"sqlite:///{(GOC / 'data' / 'ftel.db').as_posix()}"

    print("Đang tính trên máy...")
    a = _chay(may)
    print("Đang tính trên Supabase...")
    b = _chay(sb)

    lech = []
    for khoa in sorted(set(a) | set(b)):
        if a.get(khoa) != b.get(khoa):
            lech.append(khoa)
    so_muc = sum(len(v) if isinstance(v, (dict, list)) else 1 for v in a.values())
    if not lech:
        print(f"\nKHỚP TUYỆT ĐỐI · {len(a)} nhóm chỉ số · {so_muc} con số")
        return
    print(f"\nLỆCH {len(lech)} nhóm chỉ số:")
    for khoa in lech:
        va, vb = a.get(khoa), b.get(khoa)
        if isinstance(va, dict) and isinstance(vb, dict):
            for k in sorted(set(va) | set(vb)):
                if va.get(k) != vb.get(k):
                    print(f"  {khoa} · {k}: máy={va.get(k)} · Supabase={vb.get(k)}")
        else:
            print(f"  {khoa}: máy={va} · Supabase={vb}")
    sys.exit(1)


if __name__ == "__main__":
    if "--con" in sys.argv:
        print(json.dumps(_tinh(), ensure_ascii=False, default=str))
    else:
        main()
