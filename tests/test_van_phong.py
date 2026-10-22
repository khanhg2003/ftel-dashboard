"""Văn phòng AI (app/van_phong.py + trang /vanphong): nhân viên đọc từ .claude/agents, trạng thái suy ra từ nhật ký hook, hàng đợi việc, quyền."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import van_phong as vp  # noqa: E402
from app.config import DATA_DIR  # noqa: E402

TS = 1_792_650_000.0                         # một mốc cố định; "bây giờ" của các test lấy theo mốc này


def _su_kien(*ds):
    return [{"ts": TS + i * 10, **d} for i, d in enumerate(ds)]


def test_nhan_vien_doc_tu_file_agent():
    nv = {x["id"]: x for x in vp.doc_nhan_vien()}
    assert {"main", "planner", "coder", "tester", "ui-reviewer"} <= set(nv)
    assert nv["planner"]["vai_tro"] == "Kế hoạch" and nv["planner"]["cong_cu"] == ["Read", "Glob", "Grep"]
    assert nv["ui-reviewer"]["ten"] == "Ui Reviewer" and nv["coder"]["model"] == "inherit"
    assert all(x["mo_ta"] for x in nv.values())


def test_trang_thai_tu_nhat_ky():
    nv = vp.doc_nhan_vien()
    sk = _su_kien(
        {"su_kien": "UserPromptSubmit", "lenh": "Thêm cột vào bảng giá"},
        {"su_kien": "giao_viec", "chi_tiet": "coder: Sửa bảng giá"},
        {"su_kien": "SubagentStart", "agent": "coder"},
        {"su_kien": "PostToolUse", "agent": "coder", "cong_cu": "Edit", "chi_tiet": "giafpt.py"})
    tt = vp.trang_thai(nv, sk, TS + 40)
    assert tt["coder"]["dang_lam"] and tt["coder"]["viec"] == "Sửa bảng giá" and tt["coder"]["cong_cu"] == "Edit giafpt.py"
    assert tt["main"]["dang_lam"] and tt["main"]["viec"] == "Thêm cột vào bảng giá"
    assert not tt["tester"]["dang_lam"]
    xong = sk + _su_kien({"su_kien": "SubagentStop", "agent": "coder", "ket_qua": "Đã sửa xong 2 file"})
    for e in xong[-1:]:
        e["ts"] = TS + 100
    tt = vp.trang_thai(nv, xong, TS + 110)
    assert not tt["coder"]["dang_lam"] and tt["coder"]["gan_nhat"] == "Đã sửa xong 2 file" and tt["coder"]["luc_xong"] == TS + 100
    assert vp.viec_vua_xong(xong)[0]["agent"] == "coder" and vp.lenh_ceo(xong)[0]["lenh"] == "Thêm cột vào bảng giá"


def test_agent_ngat_giua_chung_khong_treo_mai_la_dang_lam():
    sk = _su_kien({"su_kien": "SubagentStart", "agent": "tester"})
    assert vp.trang_thai(vp.doc_nhan_vien(), sk, TS + 60)["tester"]["dang_lam"]
    assert not vp.trang_thai(vp.doc_nhan_vien(), sk, TS + vp.NGUONG_TREO + 60)["tester"]["dang_lam"]


def test_agent_la_van_co_the():
    sk = _su_kien({"su_kien": "SubagentStart", "agent": "Explore"}, {"su_kien": "SubagentStop", "agent": "Explore", "ket_qua": "ok"})
    tt = vp.trang_thai(vp.doc_nhan_vien(), sk, TS + 30)
    assert "Explore" in tt and tt["Explore"]["gan_nhat"] == "ok"


@pytest.fixture
def hang_doi(tmp_path, monkeypatch):
    monkeypatch.setattr(vp, "HANG_DOI", tmp_path / "viec.json")
    return tmp_path / "viec.json"


def test_hang_doi_viec(hang_doi):
    assert vp.doc_hang_doi() == [] and vp.them_viec("   ") is None
    a = vp.them_viec("  Làm   bảng A  ")
    assert a["noi_dung"] == "Làm bảng A" and a["trang_thai"] == "cho"
    vp.them_viec("x" * 1000)
    assert len(vp.doc_hang_doi()[1]["noi_dung"]) == vp.TOI_DA_CHU
    for tt in ("dang_lam", "xong", "cho"):
        vp.doi_trang_thai(a["id"])
        assert vp.doc_hang_doi()[0]["trang_thai"] == tt
    vp.xoa_viec(a["id"])
    assert [v["id"] for v in vp.doc_hang_doi()] != [a["id"]] and len(vp.doc_hang_doi()) == 1
    hang_doi.write_text("không phải json", encoding="utf-8")
    assert vp.doc_hang_doi() == []                                                  # file hỏng: coi như rỗng, không làm vỡ trang
    hang_doi.write_text(json.dumps([{"id": "a", "noi_dung": "x", "trang_thai": "lạ"}]), encoding="utf-8")
    vp.doi_trang_thai("a")                                                          # trạng thái lạ: không nổ
    assert vp.doc_hang_doi()[0]["trang_thai"] == "dang_lam"


def test_hang_doi_co_tran_viec_chua_xong(hang_doi):
    for i in range(vp.TOI_DA_VIEC):
        assert vp.them_viec(f"việc {i}")
    assert vp.them_viec("thừa") is None


def _tk(role: str):
    from app.auth import SessionUser
    return SessionUser(SimpleNamespace(id=1, username=f"kiemthu.{role}", ho_ten="Kiểm thử", role=role, ma_nv=None, session_version=0, scope="[]"))


@pytest.mark.skipif(not (DATA_DIR / "kiemthu.db").exists(), reason="Chưa dựng được database kiểm thử (xem tests/conftest.py)")
def test_chi_quan_tri_vao_va_goi_duoc(hang_doi):
    from dash._callback_context import context_value
    from dash._utils import AttributeDict
    from dash.exceptions import PreventUpdate
    from flask_login import login_user

    from app.ui.app import app, server

    def goi(dau_ra, tai_khoan, *args):
        ham = next(getattr(v["callback"], "__wrapped__", v["callback"]) for k, v in app.callback_map.items() if "callback" in v and dau_ra in k)
        with server.test_request_context("/"):
            login_user(tai_khoan)
            context_value.set(AttributeDict(triggered_inputs=[], inputs_list=[], states_list=[], outputs_list=[]))
            return ham(*args)

    tom_tat, ban, xong, lenh = goi("vp-ban.children", _tk("admin"), 0)
    assert len(ban) >= 5                                                            # điều phối + 4 nhân viên
    with pytest.raises(PreventUpdate):
        goi("vp-ban.children", _tk("nvkd"), 0)                                      # nvkd gọi thẳng callback cũng bị chặn
    with pytest.raises(PreventUpdate):
        goi("vp-hang-doi.children", _tk("phong"), 0, [], [], "x")
    assert not _tk("nvkd").vao_duoc("/vanphong")
    ds, o = goi("vp-hang-doi.children", _tk("admin"), 0, [], [], "x")               # lần dựng đầu: chỉ vẽ lại danh sách
    assert o is not None
