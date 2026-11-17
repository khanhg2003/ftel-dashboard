"""Trích số liệu từ trang "Báo cáo tồn" (NKN Huế) đã lưu bằng Chrome (Ctrl+S) ra file JSON cho trang /kt/bao-cao-ton.

Mỗi mục của trang gốc (Tổng quan, Tổng hợp, Nhân sự, Chi tiết tồn, Mất tín) lưu thành một file; script tự nhận
file nào là mục nào nhờ nút mục đang bật. Tên NV, Điều hành, mã HĐ, mã thiết bị được đổi sang mã giả; cột ghi chú
tự do (có thể chứa số điện thoại / tên khách) bị bỏ hẳn.

Cách chạy:
    python scripts/trich_bao_cao_ton.py "Tổng quan.html" "Tổng hợp.html" "Nhân sự.html" ...
Kết quả: demo/lien_khoi/kt_bao_cao_ton.json (bản chốt, không tự cập nhật).
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

RA = Path(__file__).resolve().parents[1] / "demo" / "lien_khoi" / "kt_bao_cao_ton.json"
MUC = ("tong", "block", "staff", "detail", "mt")
BO_COT = re.compile(r"ghi ch|ttscb|tstc", re.I)          # cột chữ tự do / cổng thiết bị: không đưa vào bản chốt


def chu(s: str) -> str:
    """Bỏ thẻ HTML, giải mã ký tự, gộp khoảng trắng."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def lay_json(t: str, id_: str):
    m = re.search(rf'id="{id_}"[^>]*>(.*?)</script>', t, re.S)
    return json.loads(m.group(1)) if m else None


def the_canh_bao(t: str) -> list[dict]:
    """Các thẻ số ở đầu trang (Chưa có ca trước 9h, Mất tín, Công nợ...)."""
    ds = []
    for m in re.finditer(r'<(a|div) class="ton-card ([^"]*)"[^>]*>(.*?)</\1>', t, re.S):
        phan = {k: chu(v) for k, v in re.findall(r'<span class="(l|n|s)"[^>]*>(.*?)</span>', m.group(3), re.S)}
        muc = "bad" if "red" in m.group(2) else ("warn" if "amber" in m.group(2) else "")
        nhom = re.findall(r'<p class="ton-sec">(.*?)</p>', t[:m.start()], re.S)          # tên nhóm thẻ đứng trước (Tổng hợp)
        ds.append({"nhan": phan.get("l", ""), "so": phan.get("n", ""), "ghi_chu": phan.get("s", ""), "muc": muc,
                   "nhom": chu(nhom[-1]) if nhom else "", "lop": " ".join(m.group(2).split())})      # lop: kiểu thẻ gốc (red / k-ton / k-done...)
    return ds


def mau_o(thuoc_tinh: str) -> str:
    """Màu nền / màu chữ web gốc gắn thẳng vào ô (style="background:#..."), giữ lại để tô y hệt."""
    st = re.search(r'style="([^"]*)"', thuoc_tinh)
    phan = re.findall(r"(background(?:-color)?|color)\s*:\s*(#[0-9a-fA-F]{3,8}|[a-z]+)", st.group(1) if st else "")
    return ";".join(f"{'background' if k.startswith('background') else 'color'}:{v.lower()}" for k, v in phan)      # chữ thường: #FAFA04 không bị ẩn danh nhầm


def bang(khoi: str) -> dict:
    """Một bảng: tên cột + các dòng (giữ nguyên chữ như trên web) + màu từng ô."""
    tb = re.search(r"<table.*?</table>", khoi, re.S).group(0)
    cot = [chu(c) for c in re.findall(r"<th[^>]*>(.*?)</th>", tb, re.S)]
    than = re.search(r"<tbody.*?</tbody>", tb, re.S)
    dong, mau = [], []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", than.group(0) if than else tb, re.S):
        o = re.findall(r"<td([^>]*)>(.*?)</td>", tr, re.S)
        if len(o) == len(cot):
            dong.append([chu(v) for _, v in o])
            mau.append([mau_o(a) for a, _ in o])
    giu = [i for i, c in enumerate(cot) if not BO_COT.search(c)]
    return {"cot": [cot[i] for i in giu], "dong": [[d[i] for i in giu] for d in dong], "mau": [[d[i] for i in giu] for d in mau]}


def cac_bang(t: str) -> list[dict]:
    """Mỗi khối <section>/<details> có bảng → tiêu đề, con số, mô tả, bảng."""
    ds = []
    for m in re.finditer(r'<(section|details) class="card[^"]*"(?: id="([^"]*)")?[^>]*>(.*?)</\1>', t, re.S):
        khoi = m.group(3)
        if "<table" not in khoi:
            continue
        sm = re.search(r"<summary>(.*?)</summary>", khoi, re.S)
        if sm:      # khối thu gọn: <span class=t> tiêu đề, <span class=b> số, <span class=pv> tóm tắt
            p = {k: chu(v) for k, v in re.findall(r'<span class="(t|b|pv)">(.*?)</span>', sm.group(1), re.S)}
            tieu_de, so, tom_tat = p.get("t", ""), p.get("b", ""), p.get("pv", "")
        else:       # khối mở sẵn: tiêu đề <h2/h3>, tóm tắt ở dòng mô tả đầu
            h = re.search(r"<h[1-4][^>]*>(.*?)</h[1-4]>", khoi, re.S)
            tieu_de, so, tom_tat = chu(h.group(1)) if h else "", "", ""
        mo_ta = re.search(r'<p class="muted[^"]*">(.*?)</p>', khoi, re.S)
        ds.append({"ma": m.group(2) or f"bang{len(ds) + 1}", "tieu_de": tieu_de, "so": so, "tom_tat": tom_tat,
                   "mo_ta": chu(mo_ta.group(1)) if mo_ta else "", **bang(khoi)})
    return ds


def muc_cua(t: str) -> str:
    """Mục của trang đã lưu = nút mục đang bật (class "on") trên thanh Tổng quan / Tổng hợp / ..."""
    m = re.search(r'<a[^>]*href="[^"]*\?v=(\w+)[^"]*"[^>]*class="[^"]*\bon\b', t) or re.search(r'<a[^>]*class="[^"]*\bon\b[^"]*"[^>]*href="[^"]*\?v=(\w+)', t)
    return m.group(1) if m and m.group(1) in MUC else ""


def trich_mot(t: str) -> dict:
    return {"the": the_canh_bao(t), "bieu_do": lay_json(t, "tonChartData") or {},
            "nhan_dinh": [d for d in (lay_json(t, "tonTxtData") or "").splitlines()[1:] if d.strip()],
            "bang": cac_bang(t)}


def trich(cac_file: list[Path]) -> dict:
    kq = {"chot_luc": "", "khu_vuc": "TIN Huế", "muc": {}}
    for f in cac_file:
        t = f.read_text(encoding="utf-8")
        muc = muc_cua(t)
        if not muc:
            sys.exit(f"Không nhận ra mục của file {f.name} (không phải trang Báo cáo tồn?)")
        m = re.search(r"Excel tồn cập nhật lúc\s*(?:<[^>]+>\s*)*([0-9:]+ [0-9/]+)", t)
        kq["chot_luc"] = kq["chot_luc"] or (m.group(1) if m else "")
        kq["muc"][muc] = trich_mot(t)
        print(f"  {f.name} → mục {muc}")
    return kq


# ---------- Ẩn danh: số giữ nguyên, mọi tên người / mã hợp đồng / mã thiết bị đổi sang mã giả ----------
MA = r"(?<![A-Za-z0-9])(?=[A-Za-z0-9]*[A-Z]{2})[A-Za-z][A-Za-z0-9]{2,}(?![A-Za-z0-9])"     # chữ dạng mã: có ≥ 2 chữ hoa liền nhau
GIU = {"KTV", "OLT", "TIN", "CSAT", "CSATBT", "CSATTK", "HIFPT", "HTBT", "NEW", "NSLD", "SWAP", "TKM", "WIFI", "RPT"}      # chữ thường gặp trên giao diện, không phải tên
GIA = re.compile(r"KTV\d{2}|MHAAA\d{4}|MHHDC\d{4}|OLT\d{2}")


def _duyet(x, ham):
    """Áp `ham` lên mọi chuỗi (kể cả khoá của dict màu theo Điều hành)."""
    if isinstance(x, str):
        return ham(x)
    if isinstance(x, list):
        return [_duyet(v, ham) for v in x]
    if isinstance(x, dict):
        return {(ham(k) if k[:1].isupper() else k): _duyet(v, ham) for k, v in x.items()}
    return x


class BoMa:
    """Bảng đổi mã DÙNG CHUNG cho mọi báo cáo trong một lần chạy: cùng một người / hợp đồng luôn ra cùng một mã giả."""

    def __init__(self, dieu_hanh: list[str]):
        self.doi = {ten.upper(): f"Đội {chr(65 + i)}" for i, ten in enumerate(dieu_hanh)}
        self.bang: dict[str, str] = {}

    def _moi(self, dau: str, so: int) -> str:
        return f"{dau}{sum(v.startswith(dau) for v in self.bang.values()) + 1:0{so}d}"

    def ma(self, goc: str) -> str:
        """Điều hành → Đội A, B...; mã HĐ → MHAAA0001...; mã OLT → OLT01...; hoá đơn → MHHDC0001...; tài khoản NV → KTV01..."""
        k = goc.upper()
        if k in GIU or GIA.fullmatch(goc):
            return goc
        if k in self.doi:
            return self.doi[k]
        if k not in self.bang:
            if k.startswith("HUEP"):
                self.bang[k] = self._moi("OLT", 2)
            elif re.fullmatch(r"[A-Z]{2,4}\d{8,}", k):                                    # mã hoá đơn công nợ (HDC + 16 số)
                self.bang[k] = self._moi("MHHDC", 4)
            elif re.fullmatch(r"HU[A-Z]{1,3}\d{4,6}", k):
                self.bang[k] = self._moi("MHAAA", 4)
            else:
                self.bang[k] = self._moi("KTV", 2)
        return self.bang[k]

    def chu(self, s: str) -> str:
        """Đổi mã trong một đoạn chữ của Báo cáo tồn (HUETI.NAMTVH = NAMTVH)."""
        return re.sub(MA, lambda m: self.ma(m.group(0)), re.sub(r"\bHUETI\.", "", s, flags=re.I))

    def ten_that(self) -> list[str]:
        """Mọi tên / mã thật đã gặp (để dò sót, kể cả dạng chữ thường)."""
        return list(self.doi) + list(self.bang)


def an_danh(d: dict, bo: BoMa | None = None) -> dict:
    """Ẩn danh bản Báo cáo tồn bằng bộ mã `bo` (tạo mới nếu chưa có)."""
    if bo is None:
        bo = BoMa(d["muc"].get("tong", {}).get("bieu_do", {}).get("dh", {}).get("labels") or ["BinhPB", "HuyTH", "TAIHD", "TANNVN"])
    kq = _duyet(d, bo.chu)
    con = {m.group(0) for s in [json.dumps(kq, ensure_ascii=False)] for m in re.finditer(MA, s)} - GIU
    sot = {x for x in con if not GIA.fullmatch(x) and x.upper() not in GIU} - {"Pro"}
    if sot:
        sys.exit(f"Còn chữ giống tên / mã thật, không ghi file: {sorted(sot)[:20]}")
    return kq


def _kpi(cac_file: list[Path], bo: BoMa) -> None:
    """Phần KPIs (web TAIHD): ẩn danh bằng CÙNG bộ mã với Báo cáo tồn rồi ghi demo/lien_khoi/kt_kpi/."""
    import trich_kpi as tk
    trang, kieu, chot = {}, {}, ""
    for f in cac_file:
        t = f.read_text(encoding="utf-8")
        ma = tk.muc_cua(t)
        if not ma:
            sys.exit(f"Không nhận ra mục KPI của file {f.name}")
        kieu[ma], trang[ma] = tk.lam_sach(t)
        trang[ma] = tk.nhung_anh(trang[ma], f)
        chot = chot or tk.chot_luc(t)
        print(f"  {f.name} → KPI / {ma}")
    trang = tk.an_danh_kpi(trang, bo)
    sot = tk.kiem_sot(trang, bo)
    if sot:
        sys.exit("Còn tên / mã thật trong KPI, không ghi file: " + "; ".join(sot[:20]))
    tk.ghi(trang, kieu, cac_file, chot)
    print(f"Đã ghi {tk.THU_MUC} · chốt {chot} · {len(trang)} mục" + (" · thiếu: " + ", ".join(m for m, _ in tk.MUC if m not in trang) if len(trang) < len(tk.MUC) else ""))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        sys.exit("Thiếu file HTML. Ví dụ: python scripts/trich_bao_cao_ton.py \"Tổng quan.html\" \"Tổng hợp.html\" \"KPI_tổng quan.html\" ...")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import trich_kpi as tk
    cac_file = [Path(x) for x in sys.argv[1:]]
    kpi = [f for f in cac_file if tk.la_kpi(f.read_text(encoding="utf-8"))]
    ton = [f for f in cac_file if f not in kpi]
    if not ton:
        sys.exit("Cần đủ file Báo cáo tồn (chạy chung để mã giả của hai báo cáo thống nhất).")
    goc = trich(ton)
    bo = BoMa(goc["muc"].get("tong", {}).get("bieu_do", {}).get("dh", {}).get("labels") or ["BinhPB", "HuyTH", "TAIHD", "TANNVN"])
    d = an_danh(goc, bo)
    if kpi:
        _kpi(kpi, bo)
    RA.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Đã ghi {RA} · chốt {d['chot_luc']}")
    for ma, m in d["muc"].items():
        print(f"  [{ma}] {len(m['the'])} thẻ · {len(m['nhan_dinh'])} nhận định · bảng: " + ", ".join(f"{b['tieu_de']} ({len(b['dong'])})" for b in m["bang"]))
    thieu = [m for m in MUC if m not in d["muc"]]
    if thieu:
        print("  Chưa có file của mục:", ", ".join(thieu))


if __name__ == "__main__":
    main()
