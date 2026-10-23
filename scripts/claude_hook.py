"""Hook của Claude Code cho dự án này (cấu hình ở `.claude/settings.json`). Một file, chọn việc bằng tham số đầu:

- `sau_sua`   : sau khi Edit / Write file .py -> báo ngay lỗi cú pháp / tên chưa định nghĩa (chạy ruff trên đúng file đó).
- `truoc_bash`: trước mỗi lệnh Bash -> chặn `git add -A` / `git add .` (AGENTS.md mục 7) và chặn `git commit` nếu ruff hoặc test mới đang lỗi.
- `gioi_han`  : trước khi giao việc cho agent `coder` -> chặn nếu đã gọi quá `TOI_DA_CODER` lần cho MỘT lệnh của CEO (lần đầu + 2 vòng sửa), để agent không tự cãi nhau đốt token.
- `ghi`       : ghi sự kiện (giao việc, agent bắt đầu / xong, dùng công cụ nào) vào `data/van_phong/su_kien.jsonl` để giao diện văn phòng AI bên ngoài app đọc.

Thoát mã 2 = chặn / báo lỗi cho Claude (stderr là lời nhắn); mã 0 = không có ý kiến. Nhật ký chỉ nằm ở `data/` (không lên GitHub); câu lệnh và lời
nhắc được che các chuỗi nhạy cảm (đường dẫn kết nối có mật khẩu, password= / token= / key=) trước khi ghi.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent
THU_MUC = GOC / "data" / "van_phong"
NHAT_KY = THU_MUC / "su_kien.jsonl"
TOI_DA_DONG = 3000
VONG_CODER = THU_MUC / "vong_coder.json"
TOI_DA_CODER = 3            # lần đầu + 2 vòng sửa cho một lệnh của CEO; lệnh mới của CEO thì đếm lại
_NHAY_CAM = [(re.compile(r"[a-z][a-z0-9+.-]*://[^\s'\"]*@[^\s'\"]+", re.I), "[đường dẫn đã che]"),
             (re.compile(r"(password|passwd|token|secret|api[_-]?key|key)\s*[=:]\s*\S+", re.I), r"\1=[đã che]")]


def che(chu: str) -> str:
    for mau, thay in _NHAY_CAM:
        chu = mau.sub(thay, chu)
    return chu


def doc_dau_vao() -> dict:
    try:
        return json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")      # đọc thẳng UTF-8: Windows mặc định cp1252 làm vỡ đường dẫn có dấu
    except ValueError:
        return {}


def chay(lenh: list[str], han: int) -> tuple[int, str]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    kq = subprocess.run(lenh, cwd=GOC, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=han, env=env)
    return kq.returncode, (kq.stdout + kq.stderr).strip()


def sau_sua(d: dict) -> int:
    duong = str((d.get("tool_input") or {}).get("file_path") or "")
    if not duong.endswith(".py"):
        return 0
    ma, ra = chay([sys.executable, "-m", "ruff", "check", duong, "--select", "E9,F821", "--output-format", "concise"], 60)
    if ma == 0:
        return 0
    print(f"ruff báo lỗi trong {Path(duong).name}:\n{ra[-1500:]}", file=sys.stderr)
    return 2


def bo_chu_trong_ngoac(lenh: str) -> str:
    """Bỏ phần chữ nằm trong dấu nháy và thân heredoc: lời commit hay đoạn script có nhắc tới `git add -A` không phải là lệnh thật."""
    lenh = re.sub(r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n.*?\n\s*\1\b", "<<", lenh, flags=re.S)
    return re.sub(r'"[^"]*"|\'[^\']*\'', '""', lenh)


def truoc_bash(d: dict) -> int:
    lenh = bo_chu_trong_ngoac(str((d.get("tool_input") or {}).get("command") or ""))
    if re.search(r"\bgit\s+add\s+(-A\b|--all\b|\.(\s|$|;|&|\|))", lenh):
        print("AGENTS.md mục 7: chỉ `git add` từng file cụ thể, không dùng `git add -A` hoặc `git add .`.", file=sys.stderr)
        return 2
    if not re.search(r"\bgit\b[^&;|]*\bcommit\b", lenh):
        return 0
    ma, ra = chay([sys.executable, "-m", "ruff", "check", "app", "--select", "F,E9"], 120)
    if ma != 0:
        print(f"Chặn commit: ruff còn cảnh báo (AGENTS.md mục 2.10):\n{ra[-1500:]}", file=sys.stderr)
        return 2
    lenh_test = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    try:
        ma, ra = chay(lenh_test, 280)
    except subprocess.TimeoutExpired:
        print("Chặn commit: chạy test quá 280 giây. Chạy tay `python -m pytest -q` rồi commit lại.", file=sys.stderr)
        return 2
    if ma != 0:
        print("Chặn commit: còn test lỗi:\n" + ra[-1800:], file=sys.stderr)
        return 2
    return 0


def tom_tat_cong_cu(ten: str, vao: dict) -> str:
    if ten in ("Edit", "Write", "Read", "NotebookEdit"):
        return Path(str(vao.get("file_path") or "")).name
    if ten == "Bash":
        return che(str(vao.get("command") or "").splitlines()[0] if vao.get("command") else "")[:90]
    if ten in ("Grep", "Glob"):
        return che(str(vao.get("pattern") or ""))[:60]
    if ten in ("Agent", "Task"):
        return f"{vao.get('subagent_type') or 'general-purpose'}: {che(str(vao.get('description') or ''))[:100]}"
    return ""


def gioi_han(d: dict) -> int:
    """Chặn lần gọi `coder` thứ `TOI_DA_CODER` + 1 trong cùng một lệnh của CEO: dừng lại báo CEO thay vì để hai agent sửa qua sửa lại."""
    if str((d.get("tool_input") or {}).get("subagent_type") or "") != "coder":
        return 0
    phien = str(d.get("session_id") or "")[:8]
    try:
        dem = json.loads(VONG_CODER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dem = {}
    n = int(dem.get(phien, 0)) + 1
    if n > TOI_DA_CODER:
        print(f"Chặn: đã giao việc cho coder {TOI_DA_CODER} lần cho lệnh này của CEO (lần đầu + 2 vòng sửa). Dừng lại, báo CEO "
              "log lỗi cuối và nghi ngờ nguyên nhân để CEO quyết; đừng gọi coder thêm.", file=sys.stderr)
        return 2
    dem[phien] = n
    THU_MUC.mkdir(parents=True, exist_ok=True)
    VONG_CODER.write_text(json.dumps(dem), encoding="utf-8")
    return 0


def dem_lai(phien: str) -> None:
    try:
        dem = json.loads(VONG_CODER.read_text(encoding="utf-8"))
        if dem.pop(phien, None) is not None:
            VONG_CODER.write_text(json.dumps(dem), encoding="utf-8")
    except (OSError, ValueError):
        pass


def ghi(d: dict) -> int:
    ten = d.get("hook_event_name") or ""
    ev = {"ts": round(time.time(), 1), "su_kien": ten, "agent": d.get("agent_type") or "", "agent_id": d.get("agent_id") or "",
          "phien": str(d.get("session_id") or "")[:8]}
    if ten in ("PreToolUse", "PostToolUse"):
        ev["cong_cu"] = d.get("tool_name") or ""
        ev["chi_tiet"] = tom_tat_cong_cu(ev["cong_cu"], d.get("tool_input") or {})
        if ten == "PreToolUse":
            ev["su_kien"] = "giao_viec"                        # chỉ ghi khi giao việc cho agent con (matcher Agent|Task)
    elif ten == "SubagentStop":
        ev["ket_qua"] = che(str(d.get("last_assistant_message") or ""))[:400]
    elif ten == "UserPromptSubmit":
        ev["lenh"] = che(str(d.get("prompt") or ""))[:160]
        dem_lai(ev["phien"])                                       # lệnh mới của CEO: đếm lại số lần gọi coder
    THU_MUC.mkdir(parents=True, exist_ok=True)
    with NHAT_KY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    if NHAT_KY.stat().st_size > 2_000_000:
        dong = NHAT_KY.read_text(encoding="utf-8").splitlines()[-TOI_DA_DONG:]
        NHAT_KY.write_text("\n".join(dong) + "\n", encoding="utf-8")
    return 0


VIEC = {"sau_sua": sau_sua, "truoc_bash": truoc_bash, "gioi_han": gioi_han, "ghi": ghi}

if __name__ == "__main__":
    for luong in (sys.stdout, sys.stderr):                      # Windows mặc định cp1252: lời nhắn tiếng Việt sẽ bị vỡ chữ
        luong.reconfigure(encoding="utf-8")
    try:
        sys.exit(VIEC[sys.argv[1]](doc_dau_vao()))
    except Exception as loi:                                    # hook hỏng không được làm hỏng phiên làm việc
        print(f"claude_hook: {type(loi).__name__}: {loi}", file=sys.stderr)
        sys.exit(1)
