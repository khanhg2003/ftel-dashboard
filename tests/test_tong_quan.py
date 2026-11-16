"""Đối chiếu mẫu số, phạm vi nối dữ liệu và tính trung thực của các chỉ số mới."""
from datetime import datetime
import pandas as pd
import pytest
from app.lien_khoi import nguon, tong_quan as sl
from app.ui.pages import lienkhoi_tq as tongquan, lienkhoi_tq_chart as chart

@pytest.fixture(autouse=True)
def _nguon_minh_hoa(monkeypatch, tmp_path):
    monkeypatch.setenv("LIEN_KHOI_NGUON", "demo")
    monkeypatch.setenv("LIEN_KHOI_DB", str(tmp_path / "state.db"))


@pytest.fixture
def data():
    sources = dict(kd=nguon.kd().iloc[:0],bd=nguon.sr_bi_dong().iloc[:0],cd=nguon.sr_chu_dong().iloc[:0],
                   kt=nguon.kt().iloc[:0],dv=nguon.dich_vu_kem().iloc[:0],no=nguon.danh_sach_dvkh().iloc[:0],
                   block=nguon.kt_block().iloc[:0],giao=pd.DataFrame(),now=datetime(2026,11,14),ref=pd.Timestamp('2026-11-14'),demo=True)
    def row(hd,**kw):
        return dict(so_hd=hd,ngay_tao='2026-11-01',ngay_online=None,ngay_huy=None,
                    sale='Sale A',phong='P1',cn_quan_ly='DNG',goi='Giga',tinh_trang='Bình thường',ton=True,**kw)
    a=row('A')
    b={**row('B'),'ngay_tao':'2026-11-03','ngay_online':'2026-11-04','ton':False}
    c={**row('C'),'ngay_huy':'2026-11-05','tinh_trang':'Đã chấm dứt hợp đồng'}
    d={**row('D'),'ngay_tao':None,'phong':'P2','cn_quan_ly':'QNM'}
    e={**row('E'),'ngay_tao':'2026-11-10','ngay_online':'2026-11-09','ton':False}
    sources['kd']=pd.DataFrame([a,b,c,d,e])
    return sources


def test_rate_uses_unique_filtered_contracts_and_cancelled_is_not_backlog(data):
    data['kd']=pd.concat([data['kd'],data['kd'].iloc[[0]]],ignore_index=True)
    d=sl.tong_hop(data)
    m=d['metrics']
    assert m['total']==5 and m['duplicate_kd']==1
    assert m['pending']==2 and m['pending_rate']==40.0
    assert m['online']==2 and m['cancelled']==1 and m['cancelled_rate']==20.0
    assert m['pending_old']==1 and m['age_unknown']==1 and m['invalid_dates']==1
    assert list(d['pending'].so_hd)==['A','D']
    assert d['pending'].iloc[0].so_ngay_cho==13
    assert pd.isna(d['pending'].iloc[1].so_ngay_cho)


def test_date_filters_select_creation_cohort_with_inclusive_end_date(data):
    d=sl.tong_hop(data,'2026-11-03','2026-11-03')
    assert list(d['kd'].so_hd)==['B']
    assert d['metrics']['total']==1 and d['metrics']['online']==1
    # Không phải ảnh chụp ngày 03/11: HĐ online ngày 04/11 vẫn được tính.
    assert sl.tong_hop(data,cn='QNM')['metrics']['total']==1
    assert sl.tong_hop(data,phong='P2')['metrics']['pending']==1


def test_unknown_dates_and_empty_scope_are_not_fabricated_as_zero_rates(data):
    d=sl.tong_hop(data,cn='KHONG_CO')
    assert d['metrics']['total']==0 and d['metrics']['pending_rate'] is None
    assert d['metrics']['debt_rate'] is None and d['metrics']['cancelled_rate'] is None
    for g in ['overview','kd','dvkh','kt','tasks']:
        for _,_,_,fig in chart.figures(d,g):
            fig.to_json()
    output=tongquan.render(d,'overview')
    assert 'Không có hợp đồng' in str(output[4])


def test_latest_score_does_not_become_probability_or_imply_missing_is_low(data):
    def sr(hd,time,score):
        return dict(so_hd=hd,tg_do=pd.Timestamp(time),diem_rm=score,tinh_trang='Chưa xử lý',
                    ket_qua_tu_van='',nhom_ct='Nguy cơ rời mạng (SOS)',nhan_su_au='CS1',no_cuoc=0)
    data['cd']=pd.DataFrame([sr('A','2026-11-12',990),sr('A','2026-11-13',300),sr('B','2026-11-13',-1),sr('C','2026-11-13',999)])
    d=sl.tong_hop(data)
    r=d['risk'].set_index('so_hd')
    assert r.loc['A','diem_rm']==300
    assert pd.isna(r.loc['B','diem_rm']) and r.loc['B','nhom']=='Chưa có điểm / tín hiệu'
    assert 'C' not in r.index
    assert d['metrics']['scored']==1
    assert 'xác suất' in str(tongquan.layout())


def test_debt_union_counts_each_contract_once_and_reports_unmatched(data):
    data['no']=pd.DataFrame([dict(loai='no_cuoc',so_hd=x) for x in ['A','A','D','UNMATCHED']])
    d=sl.tong_hop(data)
    assert d['metrics']['debt']==2 and d['metrics']['debt_rate']==40
    assert d['metrics']['unmatched']==1
    assert d['debt_ids']=={'A','D'}


def test_block_ratio_uses_sum_of_denominators_and_is_hidden_for_filtered_cohort(data):
    data['block']=pd.DataFrame([
        dict(block='B1',tong=100,tong_l1=10,dung_hen=90,dung_hen_l1=9,qua_hen=10,bao_tri_24h=1,tong_tgxl=100),
        dict(block='B1',tong=10,tong_l1=10,dung_hen=1,dung_hen_l1=1,qua_hen=9,bao_tri_24h=1,tong_tgxl=10),
        dict(block='B2',tong=0,tong_l1=0,dung_hen=0,dung_hen_l1=0,qua_hen=0,bao_tri_24h=0,tong_tgxl=0),
    ])
    g=sl.block_kpi(sl.tong_hop(data)['block']).set_index('block')
    assert g.loc['B1','dung_hen_pct']==82.7 and g.loc['B1','lan1_pct']==50
    assert pd.isna(g.loc['B2','dung_hen_pct'])
    assert sl.tong_hop(data,cn='DNG')['block'].empty


def test_service_attach_is_distinct_contracts_not_line_count(data):
    data['dv']=pd.DataFrame([dict(so_hd='A',nhom='Camera',vvip='0'),dict(so_hd='A',nhom='Camera',vvip='0'),dict(so_hd='B',nhom='FPT Play',vvip='1')])
    f=chart.service_attach(sl.tong_hop(data))
    assert list(f.data[0].x)==[20,20,20]


def test_demo_matches_existing_four_rules_and_all_chart_groups(monkeypatch,tmp_path):
    from app.bo_nho import xoa
    from app.lien_khoi import luat
    monkeypatch.setenv('LIEN_KHOI_NGUON','demo')
    monkeypatch.setenv('LIEN_KHOI_DB',str(tmp_path/'state.db'))
    xoa()
    d=sl.tong_hop(sl.doc_nguon())
    assert d['metrics']['total']==227 and d['metrics']['pending']==79
    assert d['metrics']['pending_rate']==34.8 and d['metrics']['pending_old']==39
    assert d['metrics']['risk']==26 and d['metrics']['debt']==60
    existing=luat.danh_sach_viec()
    assert set(map(tuple,d['jobs'][['so_hd','luat','muc']].values))==set(map(tuple,existing[['so_hd','luat','muc']].values))
    figures=[f for g in ['overview','kd','dvkh','kt','tasks'] for f in chart.figures(d,g)]
    assert len(figures)==43
    for _,_,_,f in figures:
        f.to_json()


def test_fee_chart_reuses_existing_currency_normalization(data):
    data['kd']['cuoc_thang']=[500,100000,None,None,None]
    f=chart.fee_by_plan(sl.tong_hop(data))
    assert list(f.data[0].x)==[300000]
