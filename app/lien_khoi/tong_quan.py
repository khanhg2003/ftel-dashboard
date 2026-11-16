"""Số đo điều hành trên ảnh chụp dữ liệu hiện tại; lọc theo nhóm HĐ, không giả lập lịch sử."""
from __future__ import annotations

import pandas as pd
from app.lien_khoi import hieu_qua as hq, luat, nguon, theo_doi as td
from app.lien_khoi.su_kien import chuan_hd


def ty_le(tu, mau):
    return round(100 * tu / mau, 1) if mau else None


def doc_nguon():
    """Mỗi nguồn đọc một lần; các biểu đồ dùng cùng một ảnh chụp."""
    now = td.bay_gio()
    return dict(kd=nguon.kd(), bd=nguon.sr_bi_dong(), cd=nguon.sr_chu_dong(),
                kt=nguon.kt(), block=nguon.kt_block(), dv=nguon.dich_vu_kem(),
                no=nguon.danh_sach_dvkh(), giao=td.danh_sach_day_du(now), now=now,
                ref=nguon.ngay_tham_chieu(), demo=nguon.la_demo())


def chuan(df):
    d = df.copy()
    if 'so_hd' in d:
        d['so_hd'] = chuan_hd(d['so_hd'])
        d = d[d.so_hd.ne('')].copy()
    return d


def chuan_kd(df):
    d = chuan(df)
    for c in nguon.COT_KD + ['cn_quan_ly']:
        if c not in d:
            d[c] = pd.NA
    # Một HĐ một dòng. Không có timestamp phiên bản nên giữ dòng cuối theo thứ tự file.
    d = d.drop_duplicates('so_hd', keep='last').copy()
    for c in ['ngay_tao', 'ngay_online', 'ngay_huy']:
        d[c] = pd.to_datetime(d[c], errors='coerce')
    d['ton'] = d.ton.astype('string').str.lower().isin(['1', 'true'])
    d['huy'] = d.ngay_huy.notna() | d.tinh_trang.eq('Đã chấm dứt hợp đồng').fillna(False)
    d['online'] = d.ngay_online.notna() & ~d.huy
    d['cho'] = d.ton & d.ngay_online.isna() & ~d.huy
    for c in ['phong', 'cn_quan_ly', 'sale', 'goi']:
        d[c] = d[c].fillna('').replace('', 'Chưa có thông tin')
    return d


def loc_kd(d, tu=None, den=None, cn='all', phong='all'):
    m = pd.Series(True, index=d.index)
    if tu:
        m &= d.ngay_tao >= pd.Timestamp(tu).normalize()
    if den:
        m &= d.ngay_tao < pd.Timestamp(den).normalize() + pd.Timedelta(days=1)
    if cn and cn != 'all':
        m &= d.cn_quan_ly.eq(cn)
    if phong and phong != 'all':
        m &= d.phong.eq(phong)
    return d[m].copy()


def dem(d, cot, ten='so_luong', n=12):
    if cot not in d or d.empty:
        return pd.DataFrame(columns=['nhom', ten])
    s = d[cot].fillna('').astype(str).replace('', 'Chưa có thông tin')
    g = s.value_counts().rename_axis('nhom').reset_index(name=ten)
    if n and len(g) > n:
        g = pd.concat([g.iloc[:n], pd.DataFrame([{'nhom': 'Các nhóm còn lại', ten: g.iloc[n:][ten].sum()}])], ignore_index=True)
    return g


def viec_tu_nguon(kd, bd, cd, kt, no, ref):
    """Gọi lại đúng bốn luật đã có, trên nguồn đầy đủ rồi mới lọc HĐ."""
    han = f"Trong {int((luat.rules_config().get('lien_khoi') or {}).get('han_gio', 24))} giờ"
    a, b, s, c = [luat.cau_hinh(k) for k in ['cho_online', 'loi_som', 'su_co_lap', 'co_y_roi']]
    dvkh = luat.nguoi_dvkh(bd, cd)
    tap_no = set(no.loc[no.loai.eq('no_cuoc'), 'so_hd']) if 'loai' in no else set()
    if 'no_cuoc' in cd:
        tap_no |= set(cd.loc[pd.to_numeric(cd.no_cuoc, errors='coerce').fillna(0).eq(1), 'so_hd'])
    rows = [luat.luat_cho_online(kd, ref, int(a.get('so_ngay', 2)), int(a.get('cao_tu', 7)), han, kt),
            luat.luat_loi_som(kd, bd, int(b.get('so_ngay', 30)), tuple(b.get('loai_yc') or ('Khiếu nại, phàn nàn',)), han, dvkh, kt),
            luat.luat_su_co_lap(kd, kt, bd, int(s.get('tu_lan', 2)), int(s.get('cao_tu_lan', 3)), han, dvkh),
            luat.luat_co_y_roi(bd, cd, kd, tap_no, int(c.get('so_ngay_gan', 3)), float(c.get('diem_rm_cao', 800)), han, dvkh)]
    return pd.concat(rows, ignore_index=True), tap_no


def bang_nguy_co(kd, cd, viec):
    """Điểm mới nhất mỗi HĐ; điểm thiếu là thiếu, không gán thành nguy cơ thấp."""
    d = kd[['so_hd', 'sale', 'phong', 'huy']].copy()
    scores = cd.copy()
    for c in ['tg_do', 'diem_rm', 'tinh_trang', 'ket_qua_tu_van']:
        if c not in scores:
            scores[c] = pd.NA
    scores['tg_do'] = pd.to_datetime(scores.tg_do, errors='coerce')
    scores['diem_rm'] = pd.to_numeric(scores.diem_rm, errors='coerce')
    scores['diem_rm'] = scores.diem_rm.where(scores.diem_rm.ge(0))
    scores = scores.sort_values('tg_do', na_position='first', kind='stable').drop_duplicates('so_hd', keep='last')
    d = d.merge(scores[['so_hd', 'diem_rm', 'tinh_trang', 'ket_qua_tu_van']], on='so_hd', how='left')
    v = viec[viec.luat.eq('co_y_roi')].drop_duplicates('so_hd').set_index('so_hd')
    d['muc_luat'] = d.so_hd.map(v.muc)
    d['ly_do'] = d.so_hd.map(v.ly_do).astype('string').fillna('')
    threshold = float(luat.cau_hinh('co_y_roi').get('diem_rm_cao', 800))
    d['nhom'] = 'Chưa có điểm / tín hiệu'
    d.loc[d.diem_rm.notna(), 'nhom'] = f'Điểm dưới {threshold:g}'
    d.loc[d.diem_rm.ge(threshold), 'nhom'] = f'Điểm từ {threshold:g}'
    d.loc[d.muc_luat.notna(), 'nhom'] = 'Có tín hiệu theo luật'
    d.loc[d.muc_luat.eq(luat.CAO), 'nhom'] = 'Cần giữ chân · mức Cao'
    d['can_chu_y'] = (d.diem_rm.ge(threshold) | d.muc_luat.notna()) & ~d.huy
    return d[~d.huy].sort_values(['can_chu_y', 'diem_rm', 'so_hd'], ascending=[False, False, True], na_position='last')


def tong_hop(data, tu=None, den=None, cn='all', phong='all'):
    kd_all = chuan_kd(data['kd'])
    ref = pd.Timestamp(data['ref']) if data.get('ref') is not None else luat.ngay_tham_chieu_kd(kd_all)
    kd = loc_kd(kd_all, tu, den, cn, phong)
    ids = set(kd.so_hd)
    tables = {k: chuan(data[k]) for k in ['bd', 'cd', 'kt', 'dv', 'no']}
    jobs, no = viec_tu_nguon(kd_all, tables['bd'], tables['cd'], tables['kt'], tables['no'], ref)
    jobs = jobs[jobs.so_hd.isin(ids)].copy()
    all_event_ids = set().union(*(set(t.so_hd) for t in tables.values() if 'so_hd' in t))
    unmatched = len(all_event_ids - set(kd_all.so_hd))
    tables = {k: t[t.so_hd.isin(ids)].copy() for k, t in tables.items()}
    pending = kd[kd.cho].copy()
    pending['so_ngay_cho'] = (ref.normalize() - pending.ngay_tao).dt.days.where(pending.ngay_tao.le(ref), pd.NA)
    pending = pending.sort_values(['so_ngay_cho', 'so_hd'], ascending=[False, True], na_position='last')
    pending['nhom_tuoi'] = pd.cut(pending.so_ngay_cho, [-1, 2, 6, 13, 29, float('inf')],
                                labels=['0–2 ngày', '3–6 ngày', '7–13 ngày', '14–29 ngày', 'Từ 30 ngày']).astype('string').fillna('Chưa rõ ngày')
    risk = bang_nguy_co(kd, tables['cd'], jobs)
    scoped = bool(tu or den or cn not in ('all', None) or phong not in ('all', None))
    tasks = data['giao'].copy()
    if scoped and 'so_hd' in tasks:
        tasks = tasks[tasks.so_hd.isin(ids)]
    tasks = hq.chuan_bi(tasks, data['now'])
    debt_ids = no & ids
    coverage = [{'nhom': 'Kinh doanh', 'so_luong': len(ids)}] + [
        {'nhom': label, 'so_luong': len(set(tables[k].so_hd))} for k, label in [('bd', 'SR bị động'), ('cd', 'SR chủ động'), ('kt', 'Kỹ thuật')]]
    metrics = dict(total=len(kd), pending=len(pending), pending_rate=ty_le(len(pending), len(kd)), online=int(kd.online.sum()),
                   cancelled=int(kd.huy.sum()), cancelled_rate=ty_le(int(kd.huy.sum()), len(kd)),
                   pending_old=int(pending.so_ngay_cho.ge(7).sum()), age_unknown=int(pending.so_ngay_cho.isna().sum()),
                   risk=int(risk.can_chu_y.sum()), scored=int(risk.diem_rm.notna().sum()), debt=len(debt_ids),
                   debt_rate=ty_le(len(debt_ids), len(kd)), jobs=len(jobs), high_jobs=int(jobs.muc.eq(luat.CAO).sum()),
                   unmatched=unmatched, duplicate_kd=len(chuan(data['kd']))-len(kd_all),
                   invalid_dates=int((kd.ngay_online.lt(kd.ngay_tao) | kd.ngay_tao.gt(ref)).sum()))
    return dict(**tables, kd=kd, pending=pending, risk=risk, jobs=jobs, tasks=tasks, metrics=metrics,
                block=data['block'].copy() if not scoped else pd.DataFrame(), scoped=scoped, ref=ref,
                demo=data.get('demo', False), now=data['now'], debt_ids=debt_ids,
                coverage=pd.DataFrame(coverage), task_metrics=hq.so_do(tasks))


def xu_huong(kd):
    a = kd.dropna(subset=['ngay_tao']).groupby(kd.ngay_tao.dt.normalize()).so_hd.nunique().rename('Tạo mới')
    b = kd.dropna(subset=['ngay_online']).groupby(kd.ngay_online.dt.normalize()).so_hd.nunique().rename('Đã online')
    if a.empty and b.empty:
        return pd.DataFrame(columns=['ngay', 'Tạo mới', 'Đã online'])
    d = pd.concat([a, b], axis=1, sort=True).fillna(0).sort_index()
    return d.reindex(pd.date_range(d.index.min(), d.index.max(), freq='D'), fill_value=0).rename_axis('ngay').reset_index()


def ton_theo_sale(kd):
    d = kd.groupby('sale', dropna=False).agg(tong=('so_hd', 'nunique'), ton=('cho', 'sum')).reset_index()
    d['ty_le'] = (100*d.ton/d.tong).round(1)
    return d[d.ton.gt(0)].sort_values(['ton', 'ty_le'], ascending=False).head(15)


def block_kpi(d):
    cols = ['tong', 'tong_l1', 'dung_hen', 'dung_hen_l1', 'qua_hen', 'bao_tri_24h', 'tong_tgxl']
    if d.empty or not {'block', *cols}.issubset(d.columns):
        return pd.DataFrame(columns=['block', *cols, 'dung_hen_pct', 'lan1_pct', 'gio_tb'])
    d = d.copy()
    for c in cols:
        d[c] = pd.to_numeric(d[c], errors='coerce')
    g = d.groupby('block')[cols].sum(min_count=1).reset_index()
    g['dung_hen_pct'] = (100*g.dung_hen/g.tong.where(g.tong.gt(0))).round(1)
    g['lan1_pct'] = (100*g.dung_hen_l1/g.tong_l1.where(g.tong_l1.gt(0))).round(1)
    g['gio_tb'] = (g.tong_tgxl/g.tong.where(g.tong.gt(0))).round(1)
    return g.sort_values('dung_hen_pct', na_position='last')
