"""Dashboard điều hành: bộ lọc nhóm HĐ, biểu đồ tương tác và mở hồ sơ từ xếp hạng."""
from __future__ import annotations
import re
import pandas as pd
from dash import ALL, Input, Output, ctx, dcc, html
from dash.exceptions import PreventUpdate
from app.lien_khoi import nguon, tong_quan as sl
from app.ui.components import alert, callback_can_quyen, card, chu_giai, seg_control
from app.ui.luoi import SO_1, bang
from app.ui.pages import lienkhoi_tq_chart as chart

GROUPS = [('overview','Toàn cảnh'),('kd','Kinh doanh'),('dvkh','Chăm sóc & giữ chân'),('kt','Kỹ thuật'),('tasks','Giao việc & SLA')]
CONFIG = dict(displaylogo=False, responsive=True, modeBarButtonsToRemove=['lasso2d','select2d'],
              toImageButtonOptions=dict(format='png',scale=2,filename='dieu-hanh-lien-khoi'))
TON_COLUMNS = [
    dict(headerName='Mã hợp đồng',field='so_hd',width=140,cellClass='o-bam',pinned='left'),
    dict(headerName='Ngày chờ',field='so_ngay_cho',width=110,type='numericColumn'),
    dict(headerName='Nhân sự bán',field='sale',minWidth=160,flex=1),
    dict(headerName='Phòng',field='phong',width=120),dict(headerName='Gói',field='goi',width=130),
    dict(headerName='Ngày tạo',field='ngay_tao',width=130),
]
RISK_COLUMNS = [
    dict(headerName='Mã hợp đồng',field='so_hd',width=140,cellClass='o-bam',pinned='left'),
    dict(headerName='Điểm mới nhất',field='diem_rm',width=140,type='numericColumn',valueFormatter=SO_1),
    dict(headerName='Phân loại',field='nhom',width=210),
    dict(headerName='Nhân sự bán',field='sale',width=140),
    dict(headerName='Dẫn chứng từ luật',field='ly_do',minWidth=280,flex=1,tooltipField='ly_do'),
]


def layout():
    kd = sl.chuan_kd(nguon.kd())
    opts = lambda c: [{'label':'Tất cả','value':'all'}]+[{'label':s,'value':s} for s in sorted(kd[c].unique())]
    return html.Div([
        html.Div([html.Div([html.Span('ĐIỀU HÀNH / TỔNG QUAN',className='lktq-eyebrow'),html.H2('Toàn cảnh vận hành'),
                           html.P('Từ dấu hiệu đến hành động. Theo dõi hợp đồng, chất lượng dịch vụ và phối hợp ba khối.')]),
                  html.Div(id='lktq-date',className='lktq-source-date')],className='lktq-intro'),
        html.Div([
            html.Div([html.Label('Ngày tạo hợp đồng'),dcc.DatePickerRange(id='lktq-dates',display_format='DD/MM/YYYY',
                start_date_placeholder_text='Từ ngày',end_date_placeholder_text='Đến ngày',clearable=True,
                minimum_nights=0,first_day_of_week=1)],className='lktq-date-filter'),
            html.Div([html.Label('Chi nhánh quản lý'),dcc.Dropdown(id='lktq-cn',options=opts('cn_quan_ly'),value='all',clearable=False)]),
            html.Div([html.Label('Phòng'),dcc.Dropdown(id='lktq-phong',options=opts('phong'),value='all',clearable=False)]),
            html.Div([html.Button('Bỏ lọc',id='lktq-reset',n_clicks=0,className='btn'),
                      html.Button('↻ Cập nhật',id='lktq-refresh',n_clicks=0,className='btn primary')],className='lktq-filter-actions'),
        ],className='lktq-filters'),
        html.Div(id='lktq-note',className='lktq-note'),
        html.Div(id='lktq-kpi',className='lktq-kpis'),
        html.Div(seg_control('lktq-group',GROUPS,'overview'),className='lktq-groups'),
        html.Div(id='lktq-support',className='lktq-support'),
        html.Div(id='lktq-charts',className='lktq-charts'),
        html.Details([html.Summary('Danh sách ca tồn · bấm mã hợp đồng để xem hồ sơ'),
                      bang('lktq-ton-grid',TON_COLUMNS,cao=330,tuy_chon={'rowHeight':42})],className='lktq-detail'),
        html.Details([html.Summary('Danh sách hợp đồng cần chú ý về rời mạng'),
                      bang('lktq-risk-grid',RISK_COLUMNS,cao=330,tuy_chon={'rowHeight':42})],className='lktq-detail'),
        chu_giai('Phạm vi dữ liệu & cách đọc chỉ số',[
            ('Tỷ lệ tồn chưa online','HĐ còn cờ tồn, chưa có ngày online và chưa huỷ / tổng HĐ trong bộ lọc. Không phải phần bù của tỷ lệ online khi có HĐ đã huỷ hoặc thiếu trạng thái.'),
            ('Bộ lọc ngày','Chọn nhóm HĐ theo ngày tạo, sau đó xem trạng thái hiện tại của nhóm này. Đây không phải báo cáo trạng thái tại một ngày trong quá khứ. Bỏ lọc ngày để bao gồm HĐ thiếu ngày tạo.'),
            ('Tuổi tồn','Ngày tham chiếu trừ ngày tạo hợp đồng. Dữ liệu demo dùng ngày 14/11/2026; dữ liệu thật dùng ngày mới nhất của nguồn Kinh doanh. Ngày thiếu hoặc nằm sau ngày tham chiếu không gán thành 0.'),
            ('Rời mạng','Điểm nguy cơ lấy trên SR chủ động mới nhất; giá trị âm (mã thiếu như -1) được xem là chưa có điểm, không phải xác suất. Ngưỡng điểm lấy từ cấu hình luật (hiện 800). Có tín hiệu theo luật và đã huỷ là hai khái niệm khác nhau.'),
            ('Phạm vi liên khối','Chỉ nối vào HĐ có trong Kinh doanh. Các mã chưa khớp được báo riêng. KPI block Kỹ thuật không có mã HĐ nên ẩn khi có bộ lọc để tránh gán nhầm.'),
            ('Dịch vụ kèm','Mỗi loại đếm HĐ duy nhất có dịch vụ, chia tổng HĐ trong bộ lọc. Một HĐ có thể có nhiều loại dịch vụ nên các tỷ lệ không cộng thành 100%.'),
            ('Hiệu quả giao việc','Dùng lại cách tính SLA hiện có: xong đúng hạn / đã tới hạn. Việc hết dấu hiệu bị loại; dưới 4 phần việc tới hạn không xếp hạng người. Khi bỏ lọc, tính toàn bộ lịch sử giao việc, gồm lịch sử mô phỏng nếu có.'),
        ]),
    ],className='lktq-dashboard')


def number(x, percent=False):
    if x is None or pd.isna(x):
        return '—'
    return (f'{x:.1f}%'.replace('.',',') if percent else f'{x:,.0f}'.replace(',','.'))


def kpis(d):
    m,s = d['metrics'],d['task_metrics']
    specs = [
        ('HỢP ĐỒNG TRONG PHẠM VI',number(m['total']),f"{m['online']} đã online · {m['cancelled']} đã huỷ",'neutral'),
        ('TỶ LỆ TỒN CHƯA ONLINE',number(m['pending_rate'],True),f"{m['pending']} / {m['total']} hợp đồng đã lọc",'amber'),
        ('TỒN TỪ 7 NGÀY',number(m['pending_old']),f"{m['age_unknown']} ca chưa rõ ngày tạo",'red'),
        ('HỢP ĐỒNG CẦN GIỮ CHÂN',number(m['risk']),f"{m['scored']} HĐ có điểm nguy cơ mới nhất",'red'),
        ('HỢP ĐỒNG NỢ CƯỚC',number(m['debt']),f"{number(m['debt_rate'],True)} trên HĐ đã lọc",'amber'),
        ('TỶ LỆ ĐÃ HUỶ / CHẤM DỨT',number(m['cancelled_rate'],True),'Trạng thái ghi nhận · không phải dự báo','neutral'),
        ('CẢNH BÁO MỨC CAO',number(m['high_jobs']),f"Trong {m['jobs']} việc từ các luật",'red'),
        ('PHẦN VIỆC XONG ĐÚNG HẠN',number(s['ty_le'],True),f"{s['dung_han']} / {s['den_han']} phần việc đã tới hạn",'green'),
    ]
    return [html.Div([html.Div(label,className='lktq-kpi-label'),html.Div(value,className='lktq-kpi-value'),
                      html.Div(hint,className='lktq-kpi-hint')],className=f'lktq-kpi {tone}') for label,value,hint,tone in specs]


def records(d):
    d = d.copy()
    for c in ['ngay_tao']:
        if c in d:
            d[c] = d[c].dt.strftime('%d/%m/%Y')
    return d.astype(object).where(d.notna(),None).to_dict('records')


def render(d, group):
    m,s = d['metrics'], d['task_metrics']
    cards = [card([html.P(desc,className='lktq-chart-desc'),dcc.Graph(id={'type':'lktq-chart','index':key},figure=figure,config=CONFIG)],title=title)
             for key,title,desc,figure in chart.figures(d,group)]
    note = f"Ảnh chụp trạng thái hiện tại · {m['total']} HĐ đã lọc. Toàn nguồn có {m['unmatched']} mã ở nguồn khác chưa khớp Kinh doanh."
    if m['duplicate_kd']:
        note += f" {m['duplicate_kd']} dòng Kinh doanh trùng mã được gộp, giữ dòng cuối file."
    if m['invalid_dates']:
        note += f" {m['invalid_dates']} HĐ có ngày bất thường, cần kiểm tra nguồn."
    support = [html.Span(f"{len(d['bd'])} SR bị động"),html.Span(f"{len(d['cd'])} SR chủ động"),
               html.Span(f"{len(d['kt'])} sự kiện Kỹ thuật"),html.Span(f"{s['giao']} phần việc theo dõi")]
    if s['mo_phong']:
        support.append(html.Span(f"Gồm {s['mo_phong']} phần việc MÔ PHỎNG",className='lktq-simulated'))
    if group == 'kt' and d['scoped']:
        support.append(html.Span('Bỏ toàn bộ bộ lọc để xem KPI block',className='lktq-simulated'))
    if not m['total']:
        cards.insert(0,alert('Không có hợp đồng phù hợp. Thử bỏ bộ lọc hoặc kiểm tra nguồn dữ liệu.','info'))
    date = [html.Span('DỮ LIỆU MINH HOẠ' if d['demo'] else 'NGÀY THAM CHIẾU'),html.Strong(f"{d['ref']:%d.%m.%Y}")]
    return (date,note,kpis(d),support,cards,records(d['pending']),records(d['risk'][d['risk'].can_chu_y]))


def register(app):
    cb = callback_can_quyen(app,'duoc_cau_hinh')

    @cb(Output('lktq-dates','start_date'),Output('lktq-dates','end_date'),Output('lktq-cn','value'),Output('lktq-phong','value'),
        Input('lktq-reset','n_clicks'),prevent_initial_call=True)
    def reset(n):
        if not n:
            raise PreventUpdate
        return None,None,'all','all'

    @cb(Output('lktq-date','children'),Output('lktq-note','children'),Output('lktq-kpi','children'),Output('lktq-support','children'),
        Output('lktq-charts','children'),Output('lktq-ton-grid','rowData'),Output('lktq-risk-grid','rowData'),
        Input('lk-tab','value'),Input('lktq-group','value'),Input('lktq-dates','start_date'),Input('lktq-dates','end_date'),
        Input('lktq-cn','value'),Input('lktq-phong','value'),Input('lktq-refresh','n_clicks'),Input('lk-td-tick','data'))
    def update(tab,group,tu,den,cn,phong,_refresh,_tick):
        if tab != 'tongquan':
            raise PreventUpdate
        if tu and den and tu > den:
            return [],'Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.',[],[],[],[],[]
        try:
            return render(sl.tong_hop(sl.doc_nguon(),tu,den,cn,phong),group or 'overview')
        except (FileNotFoundError, KeyError, ValueError):
            return [],'Nguồn dữ liệu chưa đầy đủ hoặc sai cấu trúc. Kiểm tra các file CSV trong cấu hình.',[],[],[],[],[]

    @cb(Output('lk-tab','value',allow_duplicate=True),Output('lk-hd-ma','value',allow_duplicate=True),
        Input({'type':'lktq-chart','index':ALL},'clickData'),Input('lktq-ton-grid','cellClicked'),
        Input('lktq-risk-grid','cellClicked'),prevent_initial_call=True)
    def open_contract(_charts,_pending,_risk):
        target = ctx.triggered_id
        value = ctx.triggered[0].get('value') or {}
        if isinstance(target,dict):
            if target.get('index') not in ('pending','risk','repeat'):
                raise PreventUpdate
            points = value.get('points',[])
            ma = points[0].get('customdata','') if points else ''
        else:
            if value.get('colId') != 'so_hd':
                raise PreventUpdate
            ma = value.get('value','')
        if not isinstance(ma,str) or not re.fullmatch(r'[A-Z0-9._-]{1,80}',ma):
            raise PreventUpdate
        return 'hd',ma
