"""Nhập Báo cáo ngày bằng giọng nói (chốt 08/10/2026; phòng được dùng ghi ở `config/rules.yml` → `bao_cao_ngay.giong_noi`).

Luồng: trình duyệt nghe -> CHỮ (mặc định dùng nhận dạng có sẵn của trình duyệt, miễn phí; Quản trị đổi sang OpenAI ở
Quản trị → Trợ lý AI nếu nghe chưa chuẩn) -> AI chỉ TÁCH ra từng người + con số -> CODE khớp tên với nhân sự của phòng và
kiểm số -> sale xem lại rồi mới bấm Lưu. AI không chọn nhân sự, không ghi dữ liệu. Không lưu ghi âm.

Quyền: tài khoản vào được Báo cáo ngày (`duoc_bao_cao_ngay`) VÀ phòng nằm trong `giong_noi` VÀ đã được mở quyền AI.
Không gửi tên khách hàng lên AI: chỉ gửi câu sale nói và tên nhân sự của chính phòng đó.
"""
from __future__ import annotations

import base64
import binascii
import difflib
import json
import re
import unicodedata
from datetime import date

from app import bao_cao_ngay as bc
from app import tro_ly as ai
from app.auth import ghi_log

LOAI = "giong_noi"
TOI_DA_NGAY = 150                 # lượt / ngày / tài khoản (tài khoản sale dùng chung cả phòng); admin không giới hạn
TOI_DA_CHU = 1500                 # ký tự của một lần nói
TOI_DA_AM = 3_000_000             # byte file ghi âm (Vercel nhận tối đa ~4,5 MB mỗi yêu cầu)
# khoá AI trả về -> cột của Báo cáo ngày
KHOA = {"mt": "muc_tieu", "khtn": "khtn", "thuc_hien": "da_ban", "dk_sang": "onl_sang", "dk_chieu": "onl_chieu",
        "da_online": "da_online"}
NHAN = {"muc_tieu": "MT ngày", "khtn": "KHTN", "da_ban": "Thực hiện", "onl_sang": "ONL sáng",
        "onl_chieu": "ONL chiều", "da_online": "Đã online"}
TIEN_TO = {"anh", "chị", "em", "bạn", "cô", "chú", "bác"}

LOI_DAN = """Bạn tách số liệu từ câu nói của nhân viên kinh doanh để điền Báo cáo đầu ngày. Chỉ trả JSON đúng khuôn.
Mỗi người được nhắc là một mục. Trường `ten`: đúng tên người nói; nếu nghe giống một tên trong danh sách nhân sự thì viết đúng chính tả tên đó.
Các trường số là số nguyên, hoặc null nếu người nói KHÔNG nhắc tới - tuyệt đối không đoán, không tự tính.
Quy ước:
- "mục tiêu" -> mt.
- "khách hàng tiềm năng", "KHTN", "khách đang theo" -> khtn.
- "đã thực hiện bán", "thực hiện", "đã bán", "bán được" -> thuc_hien (là số bán, KHÔNG phải số online).
- "dự kiến online sáng", "sáng online" -> dk_sang. "dự kiến online chiều", "chiều online" -> dk_chieu.
- "đã online", "online được" -> da_online.
- "ghi chú ..." -> ghi_chu: giữ nguyên lời, không thêm bớt; không có thì null.
Số đọc bằng chữ đổi sang chữ số: không = 0, hai = 2, mười = 10, hai mươi lăm = 25. Bỏ qua các từ "hôm nay", "báo cáo".
Một người nhắc nhiều lần thì gộp thành một mục.
Ví dụ: "hôm nay Cẩm Tiên mục tiêu 3, đã thực hiện bán 2, dự kiến online sáng 2, chiều online 1" ->
{"nguoi":[{"ten":"Cẩm Tiên","mt":3,"khtn":null,"thuc_hien":2,"dk_sang":2,"dk_chieu":1,"da_online":null,"ghi_chu":null}]}
Ví dụ: "Khái khách tiềm năng 5 đã online 1, Chi mục tiêu hai ghi chú chờ thi công" ->
{"nguoi":[{"ten":"Khái","mt":null,"khtn":5,"thuc_hien":null,"dk_sang":null,"dk_chieu":null,"da_online":1,"ghi_chu":null},
{"ten":"Chi","mt":2,"khtn":null,"thuc_hien":null,"dk_sang":null,"dk_chieu":null,"da_online":null,"ghi_chu":"chờ thi công"}]}"""

KHUON = {"type": "json_schema", "json_schema": {"name": "bao_cao_ngay", "strict": True, "schema": {
    "type": "object", "additionalProperties": False, "required": ["nguoi"],
    "properties": {"nguoi": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["ten", *KHOA, "ghi_chu"],
        "properties": {"ten": {"type": "string"}, "ghi_chu": {"type": ["string", "null"]},
                       **{k: {"type": ["integer", "null"]} for k in KHOA}}}}}}}}


# ------------------------------------------------------------------ quyền
def phong_duoc_dung(user) -> list[str]:
    """Phòng mà tài khoản này dùng được nhập giọng nói (không tính AI đã mở quyền hay chưa)."""
    ham = getattr(user, "phong_bao_cao_ngay", None)
    bat = set(bc.cau_hinh()["giong_noi"])
    return [c for c in (ham() if ham else []) if c in bat]


def kiem_tra(user, phong_code: str) -> dict:
    """Trả về cấu hình AI nếu người này được nhập giọng nói cho phòng đó ngay bây giờ, ngược lại ném `LoiAI`."""
    if phong_code not in phong_duoc_dung(user):
        raise ai.LoiAI("Tài khoản này chưa được dùng nhập báo cáo bằng giọng nói cho phòng này.")
    ch = ai.kiem_tra(user)
    if not getattr(user, "la_superadmin", False) and ai.luot_hom_nay(user.username, (LOAI,)) >= TOI_DA_NGAY:
        raise ai.LoiAI(f"Hôm nay đã dùng hết {TOI_DA_NGAY} lượt nhập bằng giọng nói. Mai dùng tiếp nhé.")
    return ch


# ------------------------------------------------------------------ khớp tên
def bo_dau(chu) -> str:
    s = unicodedata.normalize("NFD", str(chu or "").lower().replace("đ", "d"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _tu(chu) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", bo_dau(chu)) if t]


def _tu_noi(cum: str) -> list[str]:
    """Bỏ "anh / chị / em..." đứng đầu cụm (chỉ khi còn từ khác - "Chị" một mình có thể là tên Chi)."""
    w = str(cum or "").lower().split()
    while len(w) > 1 and w[0] in TIEN_TO:
        w.pop(0)
    return _tu(" ".join(w))


def khop_ten(cum: str, ds: list[dict]) -> list[str]:
    """acc_norm khớp nhất với cụm tên người nói. 1 phần tử = chắc; nhiều = mơ hồ (hai người cùng tên gọi);
    rỗng = không thấy. Bỏ dấu để chịu được nghe sai thanh điệu (Tiên / Tiến)."""
    ung = _khop(_tu_noi(cum), ds)
    return ung or (_khop(_tu(cum), ds) if _tu(cum) != _tu_noi(cum) else [])     # "Anh Tú" là acc DNG.AnhTu


def _khop(noi: list[str], ds: list[dict]) -> list[str]:
    if not noi:
        return []
    chuoi, diem = "".join(noi), {}
    for r in ds:
        ten = _tu(r["ho_ten"])
        acc = "".join(_tu(str(r.get("acc") or "").split(".")[-1]))         # DNG.AnhTu -> anhtu
        k = len(noi)
        if noi == ten:
            d = 5.0
        elif acc and chuoi == acc:
            d = 4.0
        elif k <= len(ten) and ten[-k:] == noi:
            d = 4.0 if k > 1 else 3.0                                       # khớp đuôi tên: "Cẩm Tiên", "Tiên"
        elif any(ten[i:i + k] == noi for i in range(len(ten) - k + 1)):
            d = 2.0
        else:
            ti_le = difflib.SequenceMatcher(None, chuoi, "".join(ten[-k:])).ratio() if len(ten) >= k else 0
            d = ti_le if ti_le >= 0.8 else 0.0
        if d:
            diem[r["acc_norm"]] = d
    cao = max(diem.values(), default=0)
    return [a for a, d in diem.items() if d == cao]


# ------------------------------------------------------------------ nghe + tách
def _tach(van_ban: str, ten_nhan_su: list[str], ch: dict, username: str) -> list[dict]:
    """Gọi AI tách câu nói thành từng người + số. Chỉ gửi câu nói và tên nhân sự của phòng."""
    msg = ai.hoi([{"role": "system", "content": LOI_DAN},
                  {"role": "user", "content": "Nhân sự trong phòng: " + ", ".join(ten_nhan_su)
                   + "\nCâu nói: " + van_ban}],
                 ch["model_chat"], ch["key"], username, LOAI, toi_da=2500, dinh_dang=KHUON)
    try:
        return json.loads(msg.get("content") or "{}").get("nguoi") or []
    except (ValueError, AttributeError):
        raise ai.LoiAI("AI trả lời không đúng khuôn, bấm Phân tích lại.") from None


def _so_hop_le(v) -> int | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return int(v) if 0 <= v <= bc.TOI_DA else None


def phan_tich(van_ban: str, phong: list[str], ngay: date, user, ch: dict | None = None) -> dict:
    """Câu nói -> đề xuất điền cho từng người. Chưa ghi gì vào dữ liệu."""
    van_ban = (van_ban or "").strip()
    if not van_ban:
        raise ai.LoiAI("Chưa nghe được gì, bạn nói lại hoặc gõ vào ô bên dưới nhé.")
    if len(van_ban) > TOI_DA_CHU:
        raise ai.LoiAI("Nói dài quá - chia làm hai lần cho dễ kiểm tra.")
    ch = ch or kiem_tra(user, phong[0])
    df = bc.bang(phong, ngay)
    ds = df[["acc_norm", "ho_ten", "acc"]].to_dict("records")
    nguoi: dict[str, dict] = {}
    for it in _tach(van_ban, [r["ho_ten"] for r in ds], ch, user.username):
        ten = str(it.get("ten") or "").strip()
        truong = {col: _so_hop_le(it.get(k)) for k, col in KHOA.items()}
        truong = {c: v for c, v in truong.items() if v is not None}
        ghi_chu = str(it.get("ghi_chu") or "").strip()[:bc.GHI_CHU_TOI_DA]
        if not ten or not (truong or ghi_chu):
            continue
        ung = khop_ten(ten, ds)
        khoa = ung[0] if len(ung) == 1 else f"?{len(nguoi)}"          # chưa chắc là ai thì không gộp với ai
        cu = nguoi.setdefault(khoa, {"ten_noi": ten, "acc_norm": ung[0] if len(ung) == 1 else None,
                                     "mo_ho": ung if len(ung) > 1 else [], "truong": {}, "ghi_chu": ""})
        cu["truong"].update(truong)
        cu["ghi_chu"] = (cu["ghi_chu"] + " " + ghi_chu).strip() if ghi_chu else cu["ghi_chu"]
    dang_co = {r.acc_norm: ({c: int(getattr(r, c)) for c in NHAN} if r.da_nhap else {})
               for r in df.assign(da_online=df.thuc_hien).itertuples()}
    ghi_log("giong_noi", f"{phong[0]} {len(nguoi)} người {sum(len(m['truong']) for m in nguoi.values())} ô")
    return {"van_ban": van_ban, "nguoi": list(nguoi.values()), "dang_co": dang_co,
            "ds": [{"label": r["ho_ten"], "value": r["acc_norm"]} for r in ds]}


def van_ban_tu_am(b64: str, kieu: str, phong: list[str], ngay: date, user) -> str:
    """Đường dự phòng: trình duyệt không tự nhận dạng được (hoặc Quản trị chọn OpenAI) thì gửi ghi âm lên."""
    ch = kiem_tra(user, phong[0])
    try:
        tho = base64.b64decode(b64.split(",", 1)[-1], validate=False)
    except (binascii.Error, ValueError):
        raise ai.LoiAI("Không đọc được bản ghi âm, thử ghi lại nhé.") from None
    if not tho or len(tho) > TOI_DA_AM:
        raise ai.LoiAI("Bản ghi âm trống hoặc quá dài (tối đa khoảng 1 phút).")
    return ai.phien_am(tho, str(kieu or "audio/webm")[:40], ch, user.username,
                       "Báo cáo đầu ngày bán hàng: mục tiêu, KHTN, thực hiện, dự kiến online sáng chiều. Nhân sự: "
                       + ", ".join(bc.bang(phong, ngay).ho_ten))


# ------------------------------------------------------------------ lưu
def dem_sua(goc: list[dict], moi: list[dict]) -> int:
    """Số ô sale đã sửa so với đề xuất của AI (để đo độ chính xác). Người bị đổi hẳn thì tính hết các ô của người đó."""
    n = 0
    for g, m in zip(goc or [], moi):
        tg, tm = g.get("truong") or {}, m.get("truong") or {}
        if g.get("acc_norm") != m.get("acc_norm"):
            n += len(tm)
        else:
            n += sum(1 for c in set(tg) | set(tm) if tg.get(c) != tm.get(c))
        n += int((g.get("ghi_chu") or "") != (m.get("ghi_chu") or ""))
    return n


def luu_nhieu(muc: list[dict], phong: list[str], ngay: date, user, ghi_ten: str | None = None,
              goc: list[dict] | None = None) -> dict:
    """Ghi các dòng sale đã kiểm tra: [{"acc_norm", "truong": {cột: số}, "ghi_chu"}]. Chỉ ghi người thuộc phòng và chỉ
    ô có giá trị - ô trống là KHÔNG ĐỔI, không bị ghi đè thành 0."""
    kiem_tra(user, phong[0])
    df = bc.bang(phong, ngay)
    ten = dict(zip(df.acc_norm, df.ho_ten))
    da, n_o, loi = [], 0, []
    for m in muc:
        acc = m.get("acc_norm")
        if acc not in ten:
            if m.get("truong") or m.get("ghi_chu"):
                loi.append(f"Chưa chọn người cho “{m.get('ten_noi') or 'dòng này'}”.")
            continue
        truong = {c: v for c, v in (m.get("truong") or {}).items() if c in NHAN and v is not None}
        if (m.get("ghi_chu") or "").strip():
            truong["ghi_chu"] = m["ghi_chu"]
        if not truong:
            continue
        try:
            bc.luu(acc, truong, phong, user.username, ngay, ghi_ten=ghi_ten)
        except bc.LoiBaoCao as e:
            loi.append(f"{ten[acc]}: {e}")
            continue
        da.append(acc)
        n_o += len(truong)
    ghi_log("giong_noi_luu", f"{phong[0]} {len(da)} người {n_o} ô, sửa {dem_sua(goc or [], muc)} ô")
    return {"da": da, "n_o": n_o, "loi": loi}
