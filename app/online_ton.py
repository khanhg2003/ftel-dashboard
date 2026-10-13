"""Liên kết Theo dõi Online (app/online_ca.py) với Nhập tồn (app/nhap_ton.py) - chủ app chốt 12/10/2026, để hai nơi cùng một sự thật:

- Ca có mốc "Hẹn thi công" đúng NGÀY đang xem (theo Nhập tồn) mà chưa có ca trong Theo dõi Online thì phải nhắc sale xếp khung giờ (`hen_cho_ngay`),
  và tính vào số ca còn thiếu giờ của người đó (`online_ca.thieu_gio`).
- Sale thêm ca vào một ngày nhưng Nhập tồn đang hẹn / trả về NGÀY KHÁC thì PHẢI hỏi lại trước (`xung_dot`); đồng ý thì ca được thêm và ngày hẹn
  ở Nhập tồn tự đổi theo (`dong_bo_hen`). Chưa có mốc nào ở Nhập tồn thì tự điền Hẹn thi công theo ngày của ca (không cần hỏi).
- GHI CHÚ liên kết HAI CHIỀU (chủ app 13/10/2026, để sale khỏi nhập lại): ghi chú của ca ở Theo dõi Online và "Ghi chú tình trạng" ở Nhập tồn là CÙNG MỘT chữ.
  Sửa bên nào thì bên kia đổi theo (`ca_sang_ton` / `online_ca.ghi_chu_tu_ton`, bản ghi sau cùng thắng). Ca mới tạo mà không gõ ghi chú thì lấy sẵn ghi chú Nhập tồn;
  gõ ghi chú riêng cho ca mới khi Nhập tồn đã có chữ thì NỐI vào cuối (`gop_ghi_chu`) để không xoá lịch sử tình trạng đã ghi. Mã không có trong tồn thì bỏ qua.
- Dời ca sang ngày khác thì Nhập tồn tự đổi ngày hẹn theo ngày mới. Ca bấm "Đã online" thì phương án ở Nhập tồn thành "Đã triển khai" (chờ file
  Internet về); bỏ "Đã online" thì trả về "Đang chờ triển khai" (chỉ khi phương án đang là Đã triển khai).
HĐ không còn trong danh sách tồn (đã online theo file, hoặc mã lạ) thì bỏ qua, không báo lỗi. Ghi vào Nhập tồn luôn đi qua `nhap_ton.luu` nên
cũng có nhật ký như sale tự sửa ở trang Nhập tồn.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app import nhap_ton as nt
from app import phan_tich as pt
from app.db import session_scope
from app.models import OnlineCa, TonTheoDoi

PA_CHO = "Đang chờ triển khai"


def _moc(mas) -> dict[str, dict]:
    """Mốc đang ghi ở Nhập tồn của các mã: {ma: {loai, ngay (date | None), pa}}."""
    nt.dam_bao_bang()
    mas = list(mas)
    if not mas:
        return {}
    with session_scope() as s:
        return {r.hop_dong: {"loai": r.loai_moc, "ngay": r.ngay_moc, "pa": r.phuong_an}
                for r in s.execute(select(TonTheoDoi).where(TonTheoDoi.hop_dong.in_(mas))).scalars()}


def ghi_chu_ton(mas) -> dict[str, str]:
    """Ghi chú tình trạng đang có ở Nhập tồn của các mã (chỉ mã đã có chữ)."""
    mas = list(mas)
    if not mas:
        return {}
    nt.dam_bao_bang()
    with session_scope() as s:
        return {r.hop_dong: r.ghi_chu for r in s.execute(select(TonTheoDoi).where(TonTheoDoi.hop_dong.in_(mas))).scalars() if r.ghi_chu}


def gop_ghi_chu(co_san: str, moi: str) -> str:
    """Ghi chú của ca mới: bỏ trống thì lấy sẵn chữ Nhập tồn; có gõ thì nối vào cuối chữ đã có (không xoá lịch sử). Quá dài thì giữ riêng chữ vừa gõ."""
    co_san, moi = (co_san or "").strip(), (moi or "").strip()
    if not moi or moi in co_san:
        return co_san
    if not co_san:
        return moi
    gop = f"{co_san} · {moi}"
    return gop if len(gop) <= nt.GHI_CHU_TOI_DA else moi


def ca_sang_ton(ma: str, ghi_chu: str, phong: list[str], ai: str) -> None:
    """Chép ghi chú của ca sang "Ghi chú tình trạng" ở Nhập tồn (giống chữ thì thôi). HĐ không còn trong tồn thì bỏ qua."""
    gc = (ghi_chu or "").strip()
    if gc == ghi_chu_ton([ma]).get(ma, ""):
        return
    try:
        nt.luu(ma, {"ghi_chu": gc}, list(phong), ai, ghi_ten=ai)
    except nt.LoiNhapTon:
        return


def _ton(phong: list[str]):
    return pt.hop_dong_ton(list(phong))


def hen_cho_ngay(phong: list[str], ngay: date) -> dict[str, list[dict]]:
    """Ca hẹn thi công đúng `ngay` theo Nhập tồn mà CHƯA có ca ở Theo dõi Online hôm đó: {acc_norm: [{ma, ton}]}. Bỏ ca đã chọn Huỷ / Đã triển khai."""
    ton = _ton(phong)
    if ton.empty:
        return {}
    nt.dam_bao_bang()
    with session_scope() as s:
        hen = {r.hop_dong: r.phuong_an for r in s.execute(select(TonTheoDoi).where(TonTheoDoi.loai_moc == "hen", TonTheoDoi.ngay_moc == ngay)).scalars()}
        co = set(s.execute(select(OnlineCa.ma_hd).where(OnlineCa.ngay == ngay, OnlineCa.phong_code.in_(phong))).scalars())
    ton = ton[ton.hop_dong.isin([m for m, pa in hen.items() if pa not in (nt.PA_HUY, nt.PA_DA_TRIEN_KHAI)]) & ~ton.hop_dong.isin(co)]
    ton = ton.assign(acc=nt._acc(ton)[1]) if len(ton) else ton
    out: dict[str, list[dict]] = {}
    for r in ton.sort_values("so_ngay_cho", ascending=False).itertuples():
        out.setdefault(r.acc, []).append({"ma": r.hop_dong, "ton": int(r.so_ngay_cho or 0)})
    return out


def xung_dot(mas, ngay: date, phong: list[str]) -> list[dict]:
    """Mã (còn tồn) mà Nhập tồn đang hẹn / trả về vào NGÀY KHÁC `ngay`: [{ma, loai, ngay: iso}]. Mã chưa có mốc hoặc đã khớp ngày thì không xung đột."""
    mas = list(mas)
    if not mas:
        return []
    ton = _ton(phong)
    con = set(ton.hop_dong) if not ton.empty else set()
    moc = _moc(m for m in mas if m in con)
    return [{"ma": m, "loai": x["loai"], "ngay": x["ngay"].isoformat()} for m, x in moc.items()
            if x["ngay"] is not None and x["loai"] in ("hen", "tra_ve") and (x["loai"] != "hen" or x["ngay"] != ngay)]


def lech_ngay(ca: list[dict], ngay: date, phong: list[str]) -> dict[str, dict]:
    """Ca đang trên bảng mà Nhập tồn ghi ngày hẹn khác ngày của ca: {ma: {loai, ngay: iso}} (để hiện nhãn lệch trên thẻ)."""
    return {x["ma"]: {"loai": x["loai"], "ngay": x["ngay"]} for x in xung_dot([c["ma"] for c in ca], ngay, phong)}


def dong_bo_hen(mas, ngay: date, phong: list[str], ai: str) -> int:
    """Đặt mốc Hẹn thi công `ngay` ở Nhập tồn cho các mã (bỏ qua mã đã khớp hoặc không còn tồn). Trả số mã đã sửa."""
    mas = list(mas)
    if not mas:
        return 0
    moc = _moc(mas)
    n = 0
    for ma in mas:
        x = moc.get(ma)
        if x and x["loai"] == "hen" and x["ngay"] == ngay:
            continue
        try:
            nt.luu(ma, {"loai_moc": "hen", "ngay_moc": ngay.isoformat()}, list(phong), ai, ghi_ten=ai)
            n += 1
        except nt.LoiNhapTon:
            continue                                      # đã online theo file hoặc mã không có trong tồn
    return n


def dong_bo_tt(ma: str, tt: str, phong: list[str], ai: str) -> None:
    """Ca đổi trạng thái: Đã online -> phương án "Đã triển khai"; bỏ Đã online -> về "Đang chờ triển khai" nếu đang là Đã triển khai."""
    x = _moc([ma]).get(ma)
    if tt == "da_online":
        pa = nt.PA_DA_TRIEN_KHAI
    elif x and x["pa"] == nt.PA_DA_TRIEN_KHAI:
        pa = PA_CHO
    else:
        return
    if x and x["pa"] == pa:
        return
    try:
        nt.luu(ma, {"phuong_an": pa}, list(phong), ai, ghi_ten=ai)
    except nt.LoiNhapTon:
        return
