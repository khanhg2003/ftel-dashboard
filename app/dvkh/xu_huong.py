"""Xu hướng và dự báo của khối DVKH: luồng SR vào - ra - tồn theo ngày, hướng tăng giảm, dự báo cuối tháng và cuối kỳ thu nợ.

Mọi con số đều tính từ dữ liệu trong file, không đoán:
- *Vào* = số SR phát sinh (bị động) hoặc đổ về (chủ động) trong ngày. *Ra* = số SR đã rời hàng chờ (xử lý xong, tự đóng, chuyển)
  tính theo ngày cập nhật lần cuối. *Tồn cuối ngày* = tổng vào trừ tổng ra luỹ kế, tức SR của tháng này còn đang chờ.
- Dự báo cuối tháng chỉ là "nếu giữ nhịp như các ngày đã có": luôn kèm số ngày dữ liệu để người đọc biết độ tin cậy.
- Dự báo cuối kỳ thu nợ: phần chưa thu của kỳ này giảm theo đúng hình dạng đường thu của kỳ trước đã chạy hết.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SO_NGAY_SO_SANH = 3            # xu hướng = trung bình 3 ngày gần nhất so với các ngày trước đó
NGUONG_ON_DINH = 0.07          # chênh dưới 7% coi là đi ngang
TOI_THIEU_NGAY_TIN_CAY = 14    # dưới hai tuần dữ liệu thì dự báo chỉ mang tính tham khảo (chưa thấy hết nhịp các thứ trong tuần)
TON_DONG = ("Chưa xử lý", "Đang xử lý", "Chưa phân công")


def luong_theo_ngay(df: pd.DataFrame, cot_ngay: str) -> pd.DataFrame:
    """Mỗi ngày một dòng: vao, ra, ton_cuoi_ngay (luỹ kế). Ngày trống được điền 0 để biểu đồ liền mạch."""
    cot = ["ngay", "vao", "ra", "ton_cuoi_ngay"]
    if df.empty or cot_ngay not in df:
        return pd.DataFrame(columns=cot)
    vao = df.groupby(cot_ngay).size()
    dong = df[~df["tinh_trang"].isin(TON_DONG) & df["tg_cn_cuoi"].notna()]
    ra = dong.groupby(dong["tg_cn_cuoi"].dt.normalize()).size()
    ngay = pd.date_range(min(vao.index.min(), ra.index.min() if len(ra) else vao.index.min()), vao.index.max())
    out = pd.DataFrame({"ngay": ngay})
    out["vao"] = vao.reindex(ngay, fill_value=0).to_numpy()
    out["ra"] = ra.reindex(ngay, fill_value=0).to_numpy()
    out["ton_cuoi_ngay"] = (out["vao"].cumsum() - out["ra"].cumsum()).clip(lower=0)
    return out


def huong(chuoi: pd.Series, k: int = SO_NGAY_SO_SANH) -> dict | None:
    """Hướng đi của một chuỗi theo ngày: k ngày gần nhất so với các ngày trước đó.

    Trả {"huong": "tang" | "giam" | "di_ngang", "chenh_pct", "gan", "truoc"}; None nếu chưa đủ k + 2 ngày để so sánh."""
    v = chuoi.dropna().to_numpy(dtype=float)
    if len(v) < k + 2:
        return None
    gan, truoc = float(v[-k:].mean()), float(v[:-k].mean())
    if truoc == 0:
        return {"huong": "tang" if gan > 0 else "di_ngang", "chenh_pct": None, "gan": gan, "truoc": truoc}
    c = (gan - truoc) / truoc
    return {"huong": "di_ngang" if abs(c) < NGUONG_ON_DINH else ("tang" if c > 0 else "giam"), "chenh_pct": c * 100, "gan": gan, "truoc": truoc}


def danh_gia_huong(h: dict | None, tang_la_tot: bool) -> str:
    """Quy hướng đi về tốt / xấu / trung tính để tô màu: tang_la_tot=False nghĩa là chỉ số càng thấp càng tốt (tồn, quá hạn...)."""
    if not h or h["huong"] == "di_ngang":
        return "trung_tinh"
    return "tot" if (h["huong"] == "tang") == tang_la_tot else "xau"


def du_bao_thang(vao: pd.Series, so_ngay_thang: int) -> dict | None:
    """Ước tính tổng SR cả tháng nếu giữ nhịp trung bình các ngày đã có; khoảng thấp - cao theo phân vị 25 và 75 của số SR mỗi ngày."""
    v = vao.dropna().to_numpy(dtype=float)
    if len(v) < 3:
        return None
    da_co, con = float(v.sum()), max(so_ngay_thang - len(v), 0)
    tb, thap, cao = float(v.mean()), float(np.percentile(v, 25)), float(np.percentile(v, 75))
    return {"du_bao": da_co + tb * con, "thap": da_co + thap * con, "cao": da_co + cao * con, "da_co": da_co, "so_ngay_co": len(v),
            "trung_binh_ngay": tb, "con_lai": con, "tin_cay": "thấp" if len(v) < TOI_THIEU_NGAY_TIN_CAY else "khá"}


def theo_thu(df_ngay: pd.DataFrame, cot: str = "vao") -> pd.DataFrame:
    """Số SR trung bình mỗi ngày theo thứ trong tuần (kèm số ngày mẫu) để biết thứ nào đông."""
    if df_ngay.empty:
        return pd.DataFrame(columns=["thu", "tb", "so_ngay"])
    g = df_ngay.assign(thu=df_ngay["ngay"].dt.dayofweek).groupby("thu")[cot].agg(tb="mean", so_ngay="size").reset_index()
    return g


# ------------------------------------------------------------------ công nợ
def du_bao_cong_no(cn: pd.DataFrame, ten: str, cot: str = "ty_le_bill", cap: str = "phong") -> dict | None:
    """Dự báo tỷ lệ thu cuối kỳ của kỳ nợ mới nhất.

    Phần chưa thu của kỳ này giảm theo cùng hình dạng với kỳ trước: ở mỗi ngày n của tháng sau hôm nay,
    chua_thu_moi(n) = chua_thu_hien_tai × chua_thu_truoc(n) / chua_thu_truoc(hôm nay). Cần kỳ trước đã có số tới ngày cuối."""
    if cn.empty:
        return None
    d = cn[(cn["cap"] == cap) & (cn["ten"] == ten)].dropna(subset=[cot])
    ky = sorted(d["ky_no"].unique())
    if len(ky) < 2:
        return None
    moi, cu = d[d["ky_no"] == ky[-1]].sort_values("so_ngay"), d[d["ky_no"] == ky[-2]].sort_values("so_ngay")
    if moi.empty or cu.empty:
        return None
    n0 = int(moi["so_ngay"].max())
    h0 = float(moi.iloc[-1][cot])
    cu0 = cu[cu["so_ngay"] <= n0]
    if cu0.empty or cu["so_ngay"].max() <= n0 or cu0.iloc[-1][cot] >= 1:
        return None
    c0 = float(cu0.iloc[-1][cot])
    sau = cu[cu["so_ngay"] > n0]
    du_bao = 1 - (1 - h0) * (1 - sau[cot].to_numpy()) / (1 - c0)
    return {"ky_moi": ky[-1], "ky_cu": ky[-2], "so_ngay": n0, "hien_tai": h0, "cung_ngay_ky_cu": c0, "cuoi_ky_cu": float(cu.iloc[-1][cot]),
            "du_bao_cuoi_ky": float(du_bao[-1]), "ngay_du_bao": sau["so_ngay"].to_numpy(), "duong_du_bao": du_bao}


def chenh_dich_chuyen(cn: pd.DataFrame, cot: str = "ty_le_bill") -> pd.DataFrame:
    """Ma trận (quận × ngày n của tháng) = tỷ lệ thu kỳ mới trừ kỳ trước cùng ngày lịch, theo điểm %. Âm = đang thu chậm hơn kỳ trước."""
    d = cn[(cn["cap"] == "quan") & cn["ten"].str.startswith(("Q.", "Huyen"))].dropna(subset=[cot])      # bỏ các dòng tổng DNG / DNG 1 / DNG 2
    ky = sorted(d["ky_no"].unique())
    if len(ky) < 2:
        return pd.DataFrame()
    moi = d[d["ky_no"] == ky[-1]].pivot_table(index="ten", columns="so_ngay", values=cot)
    cu = d[d["ky_no"] == ky[-2]].pivot_table(index="ten", columns="so_ngay", values=cot)
    chung = [c for c in moi.columns if c in cu.columns]
    return (moi[chung] - cu.reindex(index=moi.index, columns=chung)) * 100
