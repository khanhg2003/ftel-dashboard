"""Văn phòng AI (chủ app chốt 22/10/2026): CEO xem các "nhân viên AI" của dự án đang làm gì, và để lại hàng đợi việc.

Nhân viên = file `.claude/agents/*.md` (Claude Code đọc chính các file đó; trường `vai_tro` là của riêng app, Claude Code bỏ qua). Hoạt động đến từ
nhật ký `data/van_phong/su_kien.jsonl` do hook `scripts/claude_hook.py` ghi mỗi khi Claude Code chạy TRÊN MÁY NÀY (giao việc, agent bắt đầu / xong,
công cụ vừa dùng). Hàng đợi việc là `data/van_phong/viec.json`: CEO thêm ở trang, hook đầu phiên in ra để Claude Code biết. Cả hai nằm trong `data/`
(không lên GitHub); trên Vercel không có nhật ký nên trang chỉ hiện danh sách nhân viên. Không có tên khách hàng hay số liệu kinh doanh ở đây.
"""
from __future__ import annotations

import json
import re
import secrets
import time
from datetime import datetime
from pathlib import Path

import yaml

from app.config import BASE_DIR, DATA_DIR
from app.thoi_gian import sang_gio_vn

THU_MUC_AGENT = BASE_DIR / ".claude" / "agents"
NHAT_KY = DATA_DIR / "van_phong" / "su_kien.jsonl"
HANG_DOI = DATA_DIR / "van_phong" / "viec.json"
NGUONG_TREO = 900                    # giây không thấy động tĩnh gì thì coi như đã nghỉ (agent bị ngắt giữa chừng không gửi sự kiện "xong")
TOI_DA_VIEC, TOI_DA_CHU = 50, 300
TRANG_THAI_VIEC = ["cho", "dang_lam", "xong"]
NHAN_VIEC = {"cho": "Chờ", "dang_lam": "Đang làm", "xong": "Xong"}
DIEU_PHOI = {"id": "main", "ten": "Trợ lý điều phối", "vai_tro": "Điều phối", "mo_ta": "Nhận lệnh của CEO, giao việc cho các nhân viên, gom kết quả báo lại.",
             "model": "theo phiên", "cong_cu": []}


def doc_nhan_vien() -> list[dict]:
    """Điều phối (cố định) + mọi agent trong `.claude/agents`, theo tên."""
    ra = [dict(DIEU_PHOI)]
    for f in sorted(THU_MUC_AGENT.glob("*.md")):
        m = re.match(r"---\s*\n(.*?)\n---", f.read_text(encoding="utf-8"), re.S)
        try:
            d = yaml.safe_load(m.group(1)) if m else None
        except yaml.YAMLError:
            d = None
        if not isinstance(d, dict) or not d.get("name"):
            continue
        cc = d.get("tools")
        ra.append({"id": str(d["name"]), "ten": str(d["name"]).replace("-", " ").title(), "vai_tro": str(d.get("vai_tro") or "Nhân viên AI"),
                   "mo_ta": str(d.get("description") or ""), "model": str(d.get("model") or "inherit"),
                   "cong_cu": [t.strip() for t in cc.split(",")] if isinstance(cc, str) else list(cc or [])})
    return ra


def doc_su_kien(toi_da: int = 600) -> list[dict]:
    try:
        dong = NHAT_KY.read_text(encoding="utf-8").splitlines()[-toi_da:]
    except OSError:
        return []
    ra = []
    for d in dong:
        try:
            ra.append(json.loads(d))
        except ValueError:
            continue
    return ra


def gio(ts: float | None, dang: str = "%H:%M") -> str:
    return f"{sang_gio_vn(datetime.utcfromtimestamp(ts)):{dang}}" if ts else ""


def trang_thai(nhan_vien: list[dict], su_kien: list[dict], bay_gio: float | None = None) -> dict[str, dict]:
    """Mỗi nhân viên: đang làm gì, việc gần nhất đã xong, số việc xong hôm nay, công cụ vừa dùng. Agent lạ (chưa có file) cũng được thêm thẻ."""
    bay_gio = time.time() if bay_gio is None else bay_gio
    hom_nay = gio(bay_gio, "%Y-%m-%d")
    ra = {nv["id"]: {"dang_lam": False, "viec": "", "gan_nhat": "", "luc_xong": None, "hom_nay": 0, "cong_cu": "", "luc": None} for nv in nhan_vien}
    cho_giao: dict[str, str] = {}
    for e in su_kien:
        ag = e.get("agent") or "main"
        ev, ts = e.get("su_kien"), e.get("ts")
        if ev == "giao_viec":
            ten, _, mo_ta = str(e.get("chi_tiet") or "").partition(": ")
            cho_giao[ten] = mo_ta
            continue
        t = ra.setdefault(ag, {"dang_lam": False, "viec": "", "gan_nhat": "", "luc_xong": None, "hom_nay": 0, "cong_cu": "", "luc": None})
        t["luc"] = ts
        if ev == "SubagentStart" or (ev == "UserPromptSubmit" and ag == "main"):
            t.update(dang_lam=True, viec=cho_giao.pop(ag, "") if ev == "SubagentStart" else str(e.get("lenh") or ""), cong_cu="")
        elif ev == "PostToolUse":
            t["cong_cu"] = f"{e.get('cong_cu', '')} {e.get('chi_tiet', '')}".strip()
            if ag == "main" and not t["dang_lam"]:
                t["dang_lam"] = True
        elif ev == "SubagentStop":
            t.update(dang_lam=False, gan_nhat=str(e.get("ket_qua") or ""), luc_xong=ts, cong_cu="")
            t["hom_nay"] += gio(ts, "%Y-%m-%d") == hom_nay
        elif ev == "Stop":
            t.update(dang_lam=False, cong_cu="", luc_xong=ts)
    for t in ra.values():
        if t["dang_lam"] and (not t["luc"] or bay_gio - t["luc"] > NGUONG_TREO):
            t["dang_lam"] = False
    return ra


def viec_vua_xong(su_kien: list[dict], n: int = 10) -> list[dict]:
    return [e for e in reversed(su_kien) if e.get("su_kien") == "SubagentStop" and e.get("ket_qua")][:n]


def lenh_ceo(su_kien: list[dict], n: int = 6) -> list[dict]:
    return [e for e in reversed(su_kien) if e.get("su_kien") == "UserPromptSubmit" and e.get("lenh")][:n]


# ------------------------------------------------------------------ hàng đợi việc
def doc_hang_doi() -> list[dict]:
    try:
        ds = json.loads(HANG_DOI.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [v for v in ds if isinstance(v, dict) and v.get("id")] if isinstance(ds, list) else []


def _ghi(ds: list[dict]) -> None:
    HANG_DOI.parent.mkdir(parents=True, exist_ok=True)
    tam = Path(f"{HANG_DOI}.tmp")
    tam.write_text(json.dumps(ds, ensure_ascii=False, indent=1), encoding="utf-8")
    tam.replace(HANG_DOI)


def them_viec(noi_dung: str) -> dict | None:
    """Thêm việc vào cuối hàng đợi; rỗng hoặc đã đủ `TOI_DA_VIEC` việc (chưa xong) thì bỏ qua."""
    chu = " ".join((noi_dung or "").split())[:TOI_DA_CHU]
    ds = doc_hang_doi()
    if not chu or sum(v.get("trang_thai") != "xong" for v in ds) >= TOI_DA_VIEC:
        return None
    viec = {"id": secrets.token_hex(4), "noi_dung": chu, "trang_thai": "cho", "tao_luc": round(time.time())}
    _ghi(ds + [viec])
    return viec


def doi_trang_thai(id_: str) -> None:
    """Chờ -> Đang làm -> Xong -> Chờ."""
    ds = doc_hang_doi()
    for v in ds:
        if v["id"] == id_:
            hien = TRANG_THAI_VIEC.index(v["trang_thai"]) if v.get("trang_thai") in TRANG_THAI_VIEC else 0
            v["trang_thai"] = TRANG_THAI_VIEC[(hien + 1) % len(TRANG_THAI_VIEC)]
    _ghi(ds)


def xoa_viec(id_: str) -> None:
    _ghi([v for v in doc_hang_doi() if v["id"] != id_])
