"""Đọc file export -> nhận diện loại dữ liệu -> dò cột theo TÊN -> kiểm tra từng dòng.

Chống lệch cột bằng 2 lớp:
1. Dò theo tên cột (không dùng vị trí). Tên cột được chuẩn hoá NFC + bỏ khoảng trắng + chữ thường.
2. Kiểm tra kiểu dữ liệu từng ô. Một dòng sai kiểu ở >= 2 cột được đánh dấu "nghi lệch cột"
   và không được ghi vào database cho tới khi người dùng xử lý.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from app.config import columns_config
from app.ingest.normalize import CHECKERS, CONVERTERS, norm_acc, norm_header, norm_text

MAX_HEADER_SCAN = 15


@dataclass
class ColumnMatch:
    field: str
    header: str
    col_index: int
    kieu: str
    bat_buoc: bool


@dataclass
class LoadResult:
    dataset: str
    ten_hien_thi: str
    nguon: str                      # tên file / tên khối
    header_row: int
    cols: list[ColumnMatch] = field(default_factory=list)
    thieu_cot: list[str] = field(default_factory=list)
    cot_khong_dung: list[str] = field(default_factory=list)
    df: pd.DataFrame | None = None          # dữ liệu hợp lệ đã đổi kiểu
    loi: pd.DataFrame | None = None         # dòng lỗi + lý do
    rows_total: int = 0
    canh_bao: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.thieu_cot and self.df is not None and len(self.df) > 0

    @property
    def rows_valid(self) -> int:
        return 0 if self.df is None else len(self.df)

    @property
    def rows_invalid(self) -> int:
        return 0 if self.loi is None else len(self.loi)


# ------------------------------------------------------------------ đọc file
def read_raw(path: str | Path, sheet=0) -> pd.DataFrame:
    """Đọc nguyên trạng, mọi ô là chuỗi, chưa lấy dòng nào làm header."""
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        raw = pd.read_excel(path, sheet_name=sheet, header=None, dtype=str)
    else:
        raw = pd.read_csv(path, header=None, dtype=str, keep_default_na=False,
                          encoding="utf-8-sig", engine="python", on_bad_lines="skip")
    return raw.fillna("")


def find_header_row(raw: pd.DataFrame) -> int:
    """Dòng header là dòng khớp nhiều tên cột đã biết nhất."""
    known = set()
    for spec in columns_config()["datasets"].values():
        for c in spec["cot"]:
            known.update(norm_header(t) for t in c["ten"])
    best, best_score = 0, -1
    for i in range(min(MAX_HEADER_SCAN, len(raw))):
        score = sum(1 for v in raw.iloc[i] if norm_header(v) in known)
        if score > best_score:
            best, best_score = i, score
    return best


def split_blocks(headers: list[str]) -> list[tuple[int, int]]:
    """Tách các khối dữ liệu ghép cạnh nhau (ngăn bởi cột không có tên)."""
    blocks, start = [], None
    for i, h in enumerate(headers):
        if norm_text(h):
            start = i if start is None else start
        else:
            if start is not None:
                blocks.append((start, i - 1))
                start = None
    if start is not None:
        blocks.append((start, len(headers) - 1))
    return [b for b in blocks if b[1] - b[0] >= 2]


def detect_dataset(headers_norm: set[str]) -> str | None:
    cfg = columns_config()["datasets"]
    for key, spec in cfg.items():
        nd = spec.get("nhan_dien", {})
        if all(h in headers_norm for h in nd.get("phai_co", [])) and \
           not any(h in headers_norm for h in nd.get("khong_duoc_co", [])):
            return key
    return None


def build_mapping(headers: list[str], spec: dict, offset: int = 0):
    """Gắn từng trường với cột theo tên. Tên trùng nhau thì lấy cột chưa dùng, từ trái sang."""
    norm = [norm_header(h) for h in headers]
    used: set[int] = set()
    cols: list[ColumnMatch] = []
    thieu: list[str] = []
    for c in spec["cot"]:
        idx = None
        for ten in c["ten"]:
            t = norm_header(ten)
            for i, h in enumerate(norm):
                if h == t and i not in used:
                    idx = i
                    break
            if idx is not None:
                break
        if idx is None:
            if c.get("bat_buoc"):
                thieu.append(c["ten"][0])
            continue
        used.add(idx)
        cols.append(ColumnMatch(c["field"], headers[idx], idx + offset,
                                c.get("kieu", "str"), bool(c.get("bat_buoc"))))
    khong_dung = [headers[i] for i in range(len(headers))
                  if i not in used and norm_text(headers[i])]
    return cols, thieu, khong_dung


def _row_hash(values) -> str:
    return hashlib.sha1("|".join(norm_text(v) for v in values).encode()).hexdigest()[:32]


def typed_frame(raw: pd.DataFrame, header_row: int, cols: list[ColumnMatch]):
    """Đổi kiểu + kiểm tra từng dòng. Trả về (df hợp lệ, df lỗi)."""
    body = raw.iloc[header_row + 1:]
    if body.empty:
        return pd.DataFrame(), pd.DataFrame()

    idx = [c.col_index for c in cols]
    sub = body.iloc[:, idx].copy()
    sub.columns = [c.field for c in cols]

    header_vals = {norm_text(raw.iat[header_row, c.col_index]) for c in cols}
    is_header_repeat = sub.apply(lambda r: norm_text(r.iloc[0]) in header_vals, axis=1)
    is_empty = sub.apply(lambda r: all(norm_text(v) == "" for v in r), axis=1)
    sub = sub[~(is_header_repeat | is_empty)]
    if sub.empty:
        return pd.DataFrame(), pd.DataFrame()

    sub["_row_hash"] = [_row_hash(r) for r in sub.itertuples(index=False)]
    sub["_dong_file"] = sub.index + 1

    ly_do: list[str] = []
    for _, r in sub.iterrows():
        sai_kieu, thieu_bb = [], []
        for c in cols:
            v = r[c.field]
            if not CHECKERS.get(c.kieu, CHECKERS["str"])(v):
                sai_kieu.append(c.header)
            # chỉ bắt buộc có giá trị với cột khoá (mã HĐ, acc); các cột khác trống vẫn nạp
            if c.bat_buoc and c.kieu == "ma" and norm_text(v) == "":
                thieu_bb.append(c.header)
        if len(sai_kieu) >= 2:
            ly_do.append("Nghi lệch cột: sai định dạng ở " + ", ".join(sai_kieu[:4]))
        elif sai_kieu:
            ly_do.append("Sai định dạng: " + sai_kieu[0])
        elif thieu_bb:
            ly_do.append("Thiếu dữ liệu bắt buộc: " + ", ".join(thieu_bb[:3]))
        else:
            ly_do.append("")
    sub["_ly_do"] = ly_do

    good = sub[sub._ly_do == ""].copy()
    bad = sub[sub._ly_do != ""].copy()

    for c in cols:
        conv = CONVERTERS.get(c.kieu, norm_text)
        good[c.field] = [conv(v) for v in good[c.field]]
    if "acc_nhan_vien" in good.columns:
        good["acc_norm"] = [norm_acc(v) for v in good["acc_nhan_vien"]]
    if "acc" in good.columns:
        good["acc_norm"] = [norm_acc(v) for v in good["acc"]]
    return good, bad


def load_file(path: str | Path, sheet=0, chi_lay_khoi_dau: bool = True) -> list[LoadResult]:
    """Đọc 1 file, trả về danh sách kết quả (file ghép nhiều khối -> nhiều kết quả)."""
    raw = read_raw(path, sheet)
    header_row = find_header_row(raw)
    headers = [norm_text(v) for v in raw.iloc[header_row]]
    cfg = columns_config()["datasets"]
    results: list[LoadResult] = []
    da_co: set[str] = set()

    blocks = split_blocks(headers) or [(0, len(headers) - 1)]
    for start, end in blocks:
        hs = headers[start:end + 1]
        ds = detect_dataset({norm_header(h) for h in hs})
        if ds is None:
            continue
        spec = cfg[ds]
        cols, thieu, khong_dung = build_mapping(hs, spec, offset=start)
        res = LoadResult(dataset=ds, ten_hien_thi=spec["ten_hien_thi"],
                         nguon=f"{Path(path).name}[cột {start + 1}-{end + 1}]",
                         header_row=header_row, cols=cols, thieu_cot=thieu,
                         cot_khong_dung=khong_dung)
        if ds in da_co and chi_lay_khoi_dau:
            res.canh_bao.append("Bỏ qua: đã có khối cùng loại ở phía trước (khối cũ/lặp).")
            results.append(res)
            continue
        if thieu:
            res.canh_bao.append("Thiếu cột bắt buộc, không thể nạp.")
            results.append(res)
            continue
        good, bad = typed_frame(raw, header_row, cols)
        res.df, res.loi = good, bad
        res.rows_total = len(good) + len(bad)
        if len(bad):
            res.canh_bao.append(f"{len(bad)} dòng bị loại (xem tab Dòng lỗi).")
        da_co.add(ds)
        results.append(res)
    return results
