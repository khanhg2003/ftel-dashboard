"""Hook của Claude Code (scripts/claude_hook.py): chặn lệnh git sai quy tắc, ghi nhật ký cho trang Văn phòng AI mà không lộ mật khẩu."""
from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

GOC = Path(__file__).resolve().parent.parent


@pytest.fixture
def hook(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("claude_hook", GOC / "scripts" / "claude_hook.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "THU_MUC", tmp_path)
    monkeypatch.setattr(mod, "NHAT_KY", tmp_path / "su_kien.jsonl")
    monkeypatch.setattr(mod, "HANG_DOI", tmp_path / "viec.json")
    return mod


def _bash(lenh: str) -> dict:
    return {"tool_input": {"command": lenh}}


def test_chan_git_add_ca_thu_muc(hook, capsys):
    for lenh in ("git add -A", "git add --all && git status", "git add . ", "cd x; git add .; git status"):
        assert hook.truoc_bash(_bash(lenh)) == 2, lenh
        assert "từng file cụ thể" in capsys.readouterr().err
    for lenh in ("git add app/x.py tests/y.py", "git status", "git add .claude/settings.json", "git diff --stat"):
        assert hook.truoc_bash(_bash(lenh)) == 0, lenh
    # chữ nằm trong lời commit hoặc thân heredoc không phải lệnh thật
    assert hook.truoc_bash(_bash('echo "đừng dùng git add -A"')) == 0
    assert hook.truoc_bash(_bash("python - <<'EOF'\nprint('git add .')\nEOF\necho xong")) == 0
    assert hook.truoc_bash(_bash("python - <<'EOF'\nx = 1\nEOF\ngit add -A")) == 2


def test_loi_cu_phap_duoc_bao_ngay(hook, tmp_path, capsys):
    hong, tot = tmp_path / "hong.py", tmp_path / "tot.py"
    hong.write_text("def f(:\n    pass\n", encoding="utf-8")
    tot.write_text("def f():\n    return 1\n", encoding="utf-8")
    assert hook.sau_sua({"tool_input": {"file_path": str(hong)}}) == 2 and "hong.py" in capsys.readouterr().err
    assert hook.sau_sua({"tool_input": {"file_path": str(tot)}}) == 0
    assert hook.sau_sua({"tool_input": {"file_path": str(tmp_path / "ghi_chu.md")}}) == 0       # không phải .py: bỏ qua


def test_nhat_ky_ghi_su_kien_va_che_mat_khau(hook):
    hook.ghi({"hook_event_name": "PreToolUse", "tool_name": "Agent", "session_id": "abcdef123456",
              "tool_input": {"subagent_type": "coder", "description": "Sửa trang giá postgresql://u:matkhau@host/db"}})
    hook.ghi({"hook_event_name": "SubagentStop", "agent_type": "coder", "agent_id": "a1", "session_id": "abcdef123456",
              "last_assistant_message": "Xong. password=abc123 rồi"})
    hook.ghi({"hook_event_name": "PostToolUse", "tool_name": "Bash", "agent_type": "tester", "session_id": "abcdef123456",
              "tool_input": {"command": "DATABASE_URL=x token=zzz9 python run.py"}})
    ds = [json.loads(d) for d in hook.NHAT_KY.read_text(encoding="utf-8").splitlines()]
    assert [e["su_kien"] for e in ds] == ["giao_viec", "SubagentStop", "PostToolUse"]
    assert ds[0]["chi_tiet"].startswith("coder: Sửa trang giá") and ds[1]["agent"] == "coder" and ds[2]["agent"] == "tester"
    chu = hook.NHAT_KY.read_text(encoding="utf-8")
    assert "matkhau" not in chu and "abc123" not in chu and "zzz9" not in chu                   # không để lọt mật khẩu / token vào nhật ký


def test_hang_doi_viec_in_ra_dau_phien(hook, capsys):
    assert hook.bat_dau({}) == 0 and capsys.readouterr().out == ""                              # chưa có file: im lặng
    hook.HANG_DOI.write_text(json.dumps([{"noi_dung": "Làm bảng A", "trang_thai": "cho"}, {"noi_dung": "Việc cũ", "trang_thai": "xong"}]), encoding="utf-8")
    hook.bat_dau({})
    ra = capsys.readouterr().out
    assert "Làm bảng A" in ra and "Việc cũ" not in ra


def test_doc_dau_vao_hong_khong_lam_vo_hook(hook, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO("không phải json".encode("utf-8"))))
    assert hook.doc_dau_vao() == {}
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps({"p": "E:/App Báo cáo"}, ensure_ascii=False).encode("utf-8"))))
    assert hook.doc_dau_vao() == {"p": "E:/App Báo cáo"}                                          # đường dẫn có dấu giữ nguyên
