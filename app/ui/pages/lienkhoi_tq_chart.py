"""Biểu đồ Plotly dùng cùng bảng số đo và cấu hình hiển thị."""
from __future__ import annotations
import pandas as pd
import plotly.graph_objects as go
from app.lien_khoi import tong_quan as sl, hieu_qua as hq
from app.lien_khoi.doc_kt import TEN_LOAI_KT
from app.lien_khoi.ho_so import _dong, thuoc_tinh
from app.lien_khoi.theo_doi import TRANG_THAI

GREEN, BLUE, AMBER, RED, GREY = '#258276', '#6586b3', '#d9a142', '#cc665c', '#bac8c3'
PALETTE = [GREEN, BLUE, AMBER, RED, GREY, '#8b80a5']


def base(f, height=320):
    f.update_layout(height=height, margin=dict(l=14, r=24, t=24, b=32), template='plotly_white',
                    font=dict(family='Inter, Segoe UI, sans-serif', size=11, color='#506660'),
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    legend=dict(orientation='h', y=1.12, x=0), hoverlabel=dict(bgcolor='white'),
                    colorway=PALETTE, bargap=.34)
    f.update_xaxes(gridcolor='#edf1ee', zeroline=False, automargin=True)
    f.update_yaxes(gridcolor='#edf1ee', zeroline=False, automargin=True)
    if not f.data:
        f.add_annotation(text='Chưa đủ dữ liệu trong bộ lọc này', showarrow=False, x=.5, y=.5, xref='paper', yref='paper')
        f.update_xaxes(visible=False)
        f.update_yaxes(visible=False)
    return f


def bar(d, label='nhom', value='so_luong', color=GREEN, custom=None, pct=False):
    f = go.Figure()
    if len(d) and label in d and value in d:
        d = d.dropna(subset=[value])
        if len(d):
            f.add_bar(x=d[value], y=d[label].astype(str), orientation='h', marker_color=color,
                      customdata=d[custom] if custom else None,
                      text=d[value].round(1), textposition='auto',
                      hovertemplate='%{y}<br>%{x:,.1f}' + ('%' if pct else '') + '<extra></extra>')
    base(f, max(285, min(520, 70+len(d)*27)))
    f.update_yaxes(autorange='reversed', showgrid=False)
    if pct:
        f.update_xaxes(range=[0, 105], ticksuffix='%')
    return f


def donut(d, label='nhom', value='so_luong', center=None):
    f = go.Figure()
    d = d[d[value].gt(0)].copy()
    if len(d) and d[value].sum() > 0:
        f.add_pie(labels=d[label], values=d[value], hole=.72, sort=False, marker=dict(colors=PALETTE, line=dict(color='white', width=3)),
                  textinfo='percent', textposition='outside', hovertemplate='%{label}<br>%{value:,} · %{percent}<extra></extra>')
        if center:
            f.add_annotation(text=center, x=.5, y=.5, showarrow=False, font=dict(size=20, color='#183b33'))
    base(f)
    f.update_layout(legend=dict(orientation='h', x=.5, xanchor='center', y=-.08), margin=dict(t=24, b=54, l=20, r=20))
    return f


def trend(kd, ref):
    d = sl.xu_huong(kd)
    d = d[d.ngay.between(pd.Timestamp(ref)-pd.Timedelta(days=89), pd.Timestamp(ref))]
    f = go.Figure()
    if len(d):
        f.add_scatter(x=d.ngay, y=d['Tạo mới'], name='HĐ tạo mới', mode='lines', line=dict(color=BLUE, width=2))
        f.add_scatter(x=d.ngay, y=d['Đã online'], name='HĐ online', mode='lines', line=dict(color=GREEN, width=2.5), fill='tozeroy', fillcolor='rgba(37,130,118,.08)')
    base(f)
    f.update_yaxes(rangemode='tozero', dtick=1 if len(d) and d[['Tạo mới','Đã online']].max().max()<8 else None)
    return f


def status(d):
    m = d['metrics']
    rows = [('Đã online', m['online']), ('Tồn chưa online', m['pending']), ('Đã huỷ / chấm dứt', m['cancelled']),
            ('Chưa rõ trạng thái', m['total']-m['online']-m['pending']-m['cancelled'])]
    return donut(pd.DataFrame(rows, columns=['nhom','so_luong']), center=f"<b>{m['total']:,}</b><br><span style='font-size:11px'>HỢP ĐỒNG</span>")


def aging(d):
    order = ['0–2 ngày','3–6 ngày','7–13 ngày','14–29 ngày','Từ 30 ngày','Chưa rõ ngày']
    counts = d['pending'].nhom_tuoi.value_counts().reindex(order, fill_value=0)
    return bar(counts.rename_axis('nhom').reset_index(name='so_luong'), color=AMBER)


def pending_rank(d):
    return bar(d['pending'].dropna(subset=['so_ngay_cho']).head(15), 'so_hd', 'so_ngay_cho', RED, 'so_hd')


def risk_rank(d):
    return bar(d['risk'].dropna(subset=['diem_rm']).sort_values('diem_rm',ascending=False).head(15),
               'so_hd', 'diem_rm', RED, 'so_hd')


def count_chart(d, table, col, colors=GREEN):
    return bar(sl.dem(d[table], col), color=colors)


def sale_rank(d):
    g = sl.ton_theo_sale(d['kd'])
    f = go.Figure()
    if len(g):
        f.add_bar(y=g.sale, x=g.ton, orientation='h', marker_color=AMBER,
                  customdata=g[['tong','ty_le']], hovertemplate='%{y}<br>Tồn: %{x}<br>Tổng HĐ: %{customdata[0]}<br>Tỷ lệ tồn: %{customdata[1]}%<extra></extra>')
    base(f, max(285, len(g)*27+70)).update_yaxes(autorange='reversed', showgrid=False)
    return f


def service_attach(d):
    dv = d['dv']
    rows = []
    for nhom in ['FPT Play', 'Camera']:
        n = dv.loc[dv.nhom.eq(nhom),'so_hd'].nunique() if 'nhom' in dv else 0
        rows.append(dict(nhom=nhom, so_luong=sl.ty_le(n,len(d['kd']))))
    if 'vvip' in dv:
        rows.append(dict(nhom='V.VIP',so_luong=sl.ty_le(dv.loc[dv.vvip.astype(str).isin(['1','True','true']),'so_hd'].nunique(),len(d['kd']))))
    return bar(pd.DataFrame(rows), pct=True)


def online_delay(d):
    k = d['kd']
    days = (k.ngay_online-k.ngay_tao).dt.total_seconds()/86400
    f = go.Figure()
    values = days[days.ge(0)].dropna()
    if len(values):
        f.add_histogram(x=values, xbins=dict(start=0,size=1), marker_color=GREEN, hovertemplate='%{x:.0f} ngày<br>%{y} HĐ<extra></extra>')
    base(f).update_xaxes(title='Ngày từ tạo HĐ tới online')
    return f


def kt_repeat(d):
    k = d['kt']
    k = k[k.loai.eq('checklist')].copy() if 'loai' in k else k
    if 'so_lan' in k:
        k['so_lan'] = pd.to_numeric(k.so_lan,errors='coerce')
        k = k.groupby('so_hd').so_lan.max().dropna().sort_values(ascending=False).head(15).reset_index()
    return bar(k,'so_hd','so_lan',RED,'so_hd')


def fee_by_plan(d):
    k = d['kd'].copy()
    if 'cuoc_thang' not in k:
        return base(go.Figure())
    k['cuoc_dong'] = k.cuoc_thang.map(_dong)
    g = k.dropna(subset=['cuoc_dong']).groupby('goi').cuoc_dong.mean().round().sort_values(ascending=False).reset_index()
    return bar(g,'goi','cuoc_dong',BLUE)


def prepaid(d):
    k = d['kd']
    f = go.Figure()
    if 'so_thang_tra_truoc' in k:
        x = pd.to_numeric(k.so_thang_tra_truoc,errors='coerce').dropna()
        if len(x):
            f.add_histogram(x=x,xbins=dict(size=1),marker_color=GREEN)
    base(f).update_xaxes(title='Số tháng trả trước theo file')
    return f


def debt_attention(d):
    r = d['risk'].copy()
    r['nhom'] = r.apply(lambda x: ('Cần chú ý' if x.can_chu_y else 'Chưa có tín hiệu cao') +
                       (' · có nợ cước' if x.so_hd in d['debt_ids'] else ' · chưa ghi nhận nợ'),axis=1)
    return donut(sl.dem(r,'nhom'))


def technical_attribute(d, field):
    k = d['kt']
    if k.empty or 'thuoc_tinh' not in k:
        return base(go.Figure())
    k = k[k.loai.isin(['checklist','checklist_sau_tk'])].copy()
    k['nhom'] = k.thuoc_tinh.map(lambda s: thuoc_tinh(s).get(field,''))
    return bar(sl.dem(k,'nhom'),color=AMBER)


def figures(d, group):
    """Mỗi tab chỉ dựng biểu đồ đang xem; mọi số tỷ lệ có mẫu số rõ ràng."""
    if group == 'overview':
        return [
            ('status','Trạng thái hợp đồng','Mỗi HĐ thuộc một nhóm; ảnh chụp hiện tại.',status(d)),
            ('trend','Nhịp tạo mới & online','90 ngày tới ngày tham chiếu, theo ngày sự kiện của HĐ đã lọc. Các sự kiện cũ hơn không nằm trong biểu đồ này.',trend(d['kd'],d['ref'])),
            ('pending','Ca tồn lâu nhất','Xếp theo số ngày chờ giảm dần · bấm cột để mở hồ sơ.',pending_rank(d)),
            ('aging','Tuổi tồn chưa online',f"Tính tới {d['ref']:%d/%m/%Y}; không tính HĐ đã huỷ.",aging(d)),
            ('risk','Điểm nguy cơ rời mạng cao nhất','Điểm mới nhất mỗi HĐ · không phải % xác suất · bấm để mở hồ sơ.',risk_rank(d)),
            ('rules','Cảnh báo liên khối','Số việc sinh ra từ bốn luật; một HĐ có thể có nhiều việc.',count_chart(d,'jobs','ten_luat',BLUE)),
        ]
    if group == 'kd':
        return [
            ('sale','Nhân sự có nhiều ca tồn','Số HĐ tồn giảm dần; rê chuột để xem mẫu số và tỷ lệ tồn.',sale_rank(d)),
            ('delay','Thời gian tới online','Chỉ HĐ có đủ ngày hợp lệ; không bao gồm HĐ chưa online.',online_delay(d)),
            ('plan','Cơ cấu gói Internet','Số hợp đồng theo gói, gộp các nhóm nhỏ.',count_chart(d,'kd','goi')),
            ('attach','Tỷ lệ dùng dịch vụ kèm','HĐ có dịch vụ / tổng HĐ đã lọc; các nhóm có thể trùng nhau.',service_attach(d)),
            ('pay','Hình thức thanh toán','Theo giá trị được ghi trong file, không tự suy ra dòng tiền.',count_chart(d,'kd','hinh_thuc_tt',BLUE)),
            ('channel_kd','Nguồn bán hàng','Số hợp đồng theo kênh bán.',count_chart(d,'kd','nguon_ban')),
            ('audience','Nhóm đối tượng','Số hợp đồng theo nhóm đối tượng trong file.',count_chart(d,'kd','doi_tuong',BLUE)),
            ('fee','Cước tháng bình quân theo gói','Đồng / HĐ có cước. Dùng cách chuẩn hoá đơn vị sẵn có của hồ sơ; không phải doanh thu đã thu.',fee_by_plan(d)),
            ('prepaid','Số tháng trả trước','Chỉ giá trị có trong file; số 0 là không trả trước.',prepaid(d)),
            ('branch','Hợp đồng theo chi nhánh quản lý','CN quản lý được ghi trong dữ liệu bán hàng.',count_chart(d,'kd','cn_quan_ly')),
        ]
    if group == 'dvkh':
        return [
            ('risk_groups','Phân loại dấu hiệu rời mạng','Ưu tiên mức Cao theo luật; tiếp đến điểm từ ngưỡng 800. Thiếu điểm không có nghĩa an toàn.',donut(sl.dem(d['risk'],'nhom'))),
            ('risk','Xếp hạng điểm nguy cơ','Điểm mới nhất mỗi HĐ đang hiệu lực; không quy đổi thành xác suất.',risk_rank(d)),
            ('debt_risk','Nợ cước & tín hiệu giữ chân','Chỉ HĐ đang hiệu lực; chưa ghi nhận nợ không có nghĩa đã đối soát thanh toán.',debt_attention(d)),
            ('sr_type','Yêu cầu khách hàng','Số dòng SR bị động theo loại yêu cầu.',count_chart(d,'bd','loai_yc',BLUE)),
            ('sr_status','Tiến độ SR bị động','Số dòng trong file; không coi mỗi SR là một HĐ khác nhau.',count_chart(d,'bd','tinh_trang')),
            ('sr_cd','Tiến độ chăm sóc chủ động','Số dòng SR chủ động theo tình trạng.',count_chart(d,'cd','tinh_trang',BLUE)),
            ('cause','Nguyên nhân phản ánh','Nhóm nguyên nhân từ SR bị động.',count_chart(d,'bd','nguyen_nhan_1',AMBER)),
            ('consult','Kết quả tư vấn giữ chân','Kết quả ghi nhận trên SR chủ động, không suy diễn thành tỷ lệ giữ chân thành công.',count_chart(d,'cd','ket_qua_tu_van')),
            ('contact','Kênh liên hệ khách hàng','Phân bố dòng SR bị động theo kênh.',count_chart(d,'bd','kenh',BLUE)),
            ('overdue_sr','Tình trạng hạn xử lý SR','Phân nhóm nguyên văn trường quá hạn của SR bị động.',count_chart(d,'bd','qua_han',AMBER)),
        ]
    if group == 'kt':
        k = d['kt'].copy()
        if 'loai' in k:
            k['nhom'] = k.loai.map(TEN_LOAI_KT).fillna(k.loai)
        block = sl.block_kpi(d['block'])
        return [
            ('kt_events','Cơ cấu sự kiện Kỹ thuật','Số dòng sự kiện, một HĐ có thể xuất hiện nhiều lần.',bar(sl.dem(k,'nhom'))),
            ('kt_staff','Khối lượng sự kiện theo KTV','Số sự kiện ghi nhận, không phải đánh giá năng suất.',count_chart(d,'kt','nguoi',BLUE)),
            ('repeat','Hợp đồng có checklist lặp','Số lần lặp lớn nhất được ghi nhận theo HĐ; bấm để xem hồ sơ.',kt_repeat(d)),
            ('block','Đúng hẹn theo block','Tổng đúng hẹn / tổng lượt; KPI block không có mã HĐ nên chỉ hiện khi bỏ toàn bộ bộ lọc.',bar(block,'block','dung_hen_pct',GREEN,pct=True)),
            ('block_l1','Đúng hẹn lần đầu theo block','Đúng hẹn lần đầu / tổng lượt lần đầu. Chưa có mẫu số thì để trống.',bar(block,'block','lan1_pct',BLUE,pct=True)),
            ('block_late','Số lượt quá hẹn theo block','Số đếm từ KPI block, không phải số HĐ duy nhất.',bar(block,'block','qua_hen',RED)),
            ('block_24h','Số lượt bảo trì quá 24 giờ','Số đếm ghi nhận trong KPI block; bỏ lọc để xem toàn nguồn.',bar(block,'block','bao_tri_24h',AMBER)),
            ('technical_cause','Nguyên nhân lỗi Kỹ thuật','Thuộc tính ghi trong checklist / checklist sau triển khai.',technical_attribute(d,'nguyen_nhan_loi')),
            ('technical_fix','Hướng xử lý Kỹ thuật','Theo dữ liệu đã ghi nhận; ô thiếu được ghi rõ.',technical_attribute(d,'huong_xu_ly')),
            ('block_time','Thời gian xử lý theo block','Tổng thời gian / tổng lượt, theo đơn vị giờ của file nguồn.',bar(block,'block','gio_tb',AMBER)),
        ]
    tasks = d['tasks']
    counts = tasks.copy()
    if 'trang_thai' in counts:
        counts['nhom'] = counts.trang_thai.map(TRANG_THAI).fillna(counts.trang_thai)
    f = go.Figure()
    trend_tasks = hq.xu_huong(tasks) if len(tasks) else pd.DataFrame()
    if len(trend_tasks):
        f.add_bar(x=trend_tasks.ngay,y=trend_tasks.giao,name='Mới giao',marker_color=BLUE)
        f.add_scatter(x=trend_tasks.ngay,y=trend_tasks.xong,name='Đã hoàn tất',mode='lines+markers',line=dict(color=GREEN))
    return [
        ('task_status','Trạng thái phần việc','Bỏ việc hết dấu hiệu. Lịch sử mô phỏng được ghi rõ ở phía trên.',donut(sl.dem(counts,'nhom'))),
        ('task_trend','Nhịp giao & hoàn tất','Theo ngày của các phần việc thuộc phạm vi hiện tại.',base(f)),
        ('task_sla','Tỷ lệ đúng hạn theo khối','Xong đúng hạn / đã tới hạn; dưới 4 việc tới hạn chưa xếp hạng.',bar(hq.tong_hop(tasks,'vai_tro'),'nhom','ty_le',GREEN,pct=True)),
        ('task_people','Tỷ lệ đúng hạn theo người','Người đủ tối thiểu 4 việc tới hạn; tỷ lệ thấp nhất xếp trước.',bar(hq.tong_hop(tasks,'nguoi').head(15),'nhom','ty_le',BLUE,pct=True)),
        ('task_late','Phần việc quá hạn theo người','Số việc đang mở và đã quá hạn; người có nhiều ca cần hỗ trợ xếp trước.',bar(sl.dem(tasks[tasks.qua_han_mo] if 'qua_han_mo' in tasks else tasks,'nguoi'),color=RED)),
        ('task_rules','Việc theo luật','Phân bố phần việc đã giao, khác với số cảnh báo mới từ các luật.',bar(sl.dem(tasks,'ten_luat'))),
        ('coverage','Độ phủ nguồn dữ liệu','HĐ khớp với Kinh doanh trong bộ lọc; mỗi nguồn đếm mã HĐ duy nhất.',bar(d['coverage'],color=BLUE)),
    ]
