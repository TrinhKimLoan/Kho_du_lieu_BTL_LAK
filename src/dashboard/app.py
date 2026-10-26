import uuid
import json
from datetime import date,datetime,timezone,timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from src.dashboard.repository import Repository
from src.dashboard.formatting import money,compact_money,number,period,csv_bytes,safe_url
from src.dashboard.demo import perform

PAGES={
 'overview':('Tổng quan kinh doanh','Bức tranh doanh số từ kho dữ liệu','◈'),
 'olap':('Bán hàng & OLAP','Khám phá dữ liệu theo nhiều chiều','▦'),
 'customers':('Khách hàng & phân khúc','RFM và K-Means: từ hành vi đến nhóm khách','◎'),
 'shipping':('Giao hàng & dự đoán','Thời gian giao thực tế và mô hình Random Forest','↗'),
 'news':('Tin tức & thị trường','Tin đã quan sát, nhóm liên quan và độ phủ nguồn','◷'),
 'detail':('Tra cứu chi tiết','Theo dấu một khách hàng hoặc một đơn hàng','⌕'),
 'operations':('Vận hành dữ liệu','Theo dõi luồng CDC, chất lượng và hàng đợi ML','◉'),
 'demo':('Demo CDC','Thêm · sửa · xóa và quan sát kết quả đầu cuối','▷')}
COLORS=['#087F8C','#3169BE','#8262AA','#DE9B32','#4D9E7B','#ED8D85']
LABELS={'order_id':'Mã đơn','customer_id':'Mã khách','product_version':'Sản phẩm / phiên bản',
 'order_count':'Số đơn','customer_count':'Số khách duy nhất','goods_amount':'Tiền hàng (₫)','total_paid':'Tổng thanh toán (₫)',
 'vat_amount':'VAT (₫)','shipping_fee':'Phí vận chuyển (₫)','quantity_sum':'Số lượng','avg_order_goods':'Giá trị tiền hàng / đơn (₫)',
 'avg_delivery_hours':'Giao trung bình (giờ)','delivery_hours_sum':'Tổng giờ giao hợp lệ','delivered_orders':'Đơn có giờ giao hợp lệ',
 'month':'Tháng','year':'Năm','quarter':'Quý','category':'Nhóm hàng','district':'Quận / huyện',
 'cluster_id':'Cụm','recency_days':'R — ngày','frequency':'F — đơn','monetary':'M — tiền hàng (₫)',
 'model_id':'Phiên bản mô hình','state':'Trạng thái','reference_date':'Ngày tham chiếu','predicted_hours':'Dự đoán (giờ)',
 'actual_hours':'Thực tế (giờ)','baseline_hours':'Baseline (giờ)','error_hours':'Sai số dự đoán − thực tế (giờ)',
 'published_date':'Ngày xuất bản','title':'Tiêu đề','domain':'Nguồn','canonical_url':'Liên kết','relevance_level':'Mức liên quan',
 'relevance_reason':'Lý do phân loại','articles':'Bài quan sát','category_code':'Nhóm hàng','api_status':'Độ phủ API',
 'origin':'Nguồn nạp (seed/api)','heartbeat_at':'Heartbeat lúc','safe_error':'Lỗi tóm tắt','findings':'Phát hiện','unresolved':'Chưa xử lý','errors':'Số lỗi','attempts':'Lần thử','enqueued_at':'Vào hàng đợi lúc','finished_at':'Hoàn tất lúc','started_at':'Bắt đầu lúc','created_at':'Tạo lúc','assigned_at':'Gán nhóm lúc','predicted_at':'Dự đoán lúc (UTC)','packed_at':'Đóng gói lúc','dispatched_at':'Giao đi lúc','received_at':'Thực nhận lúc',
 'month_start':'Tháng','pipeline':'Pipeline','status':'Trạng thái','worker':'Worker','healthy':'Heartbeat còn mới',
 'age_seconds':'Tuổi heartbeat (giây)','kind':'Loại','jobs':'Công việc','is_demo':'Dữ liệu demo','is_deleted':'Đã xóa'}


def moment(value):
    if value is None:return 'chưa có'
    if isinstance(value,str):return value
    if isinstance(value,datetime) and value.tzinfo:return value.astimezone(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')
    return str(value)


def frame(rows):return pd.DataFrame(rows)


def numeric(rows,columns):
    df=frame(rows)
    for c in columns:
        if c in df:df[c]=pd.to_numeric(df[c],errors='coerce')
    return df


def chart(fig,key):
    fig.update_layout(template='plotly_white',colorway=COLORS,font=dict(family='Segoe UI, sans-serif',color='#182C43',size=12),
       margin=dict(l=16,r=16,t=30,b=25),paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',
       legend=dict(orientation='h',y=-.2),height=335)
    fig.update_xaxes(showgrid=False);fig.update_yaxes(gridcolor='#E9EDF3',zeroline=False)
    st.plotly_chart(fig,use_container_width=True,config={'displaylogo':False},key=key)


def table(rows,title,key):
    st.markdown('**'+title+'**')
    if not rows:
        st.info('Chưa có bản ghi phù hợp.');return
    df=frame(rows).rename(columns=LABELS)
    config={'Liên kết':st.column_config.LinkColumn('Liên kết',display_text='Đọc bài gốc')} if 'Liên kết' in df else None
    st.dataframe(df.head(300),hide_index=True,use_container_width=True,height=min(410,40+len(df.head(300))*35),column_config=config)
    if len(rows)>300:st.caption(f'Hiển thị 300 / {len(rows):,} dòng. CSV chứa toàn bộ kết quả truy vấn này.')
    st.download_button('↓ Xuất CSV',csv_bytes(rows),file_name=key+'.csv',mime='text/csv',key='download-'+key)


def kpis(items):
    cols=st.columns(len(items))
    for col,(label,value,note) in zip(cols,items):
        with col.container(border=True):
            st.metric(label,value)
            st.caption(note)


def model_card(model):
    if not model:st.warning('Chưa có mô hình được ghim cho suy luận.');return
    st.caption(f"{model['algorithm']} · {model['model_id']} · tạo {moment(model['created_at'])} · snapshot {model['snapshot_id']} · ngày snapshot {model.get('reference_date','—')}")


def overview(repo,filters):
    data=repo.overview(filters);k=data['kpi']
    st.caption('Phạm vi thời gian: ngày đóng gói. Tiền hàng không gồm VAT/phí vận chuyển; không phải lợi nhuận.')
    kpis([('Tiền hàng',compact_money(k['goods_amount']),money(k['goods_amount'])),('Số đơn',number(k['order_count']),'Mỗi đơn một sản phẩm'),
          ('Khách hàng',number(k['customer_count']),'Đếm duy nhất trong phạm vi'),('Giá trị / đơn',money(k['avg_order_goods']) if k['avg_order_goods'] is not None else '—','Tiền hàng chia số đơn')])
    if not k['order_count']:st.info('Không có giao dịch trong bộ lọc này. Thử mở rộng ngày, nhóm hàng hoặc địa bàn.');return
    a,b=st.columns([2,1])
    with a:
        st.subheader('Nhịp doanh số theo tháng')
        df=numeric(data['trend'],['goods_amount']);df['billion_vnd']=df['goods_amount']/1e9
        chart(px.area(df,x='month',y='billion_vnd',labels={'month':'Tháng đóng gói','billion_vnd':'Tỷ đồng'},color_discrete_sequence=[COLORS[0]]),'overview-trend')
    with b:
        st.subheader('Đóng góp theo nhóm hàng')
        df=numeric(data['categories'],['goods_amount'])
        chart(px.pie(df,names='category',values='goods_amount',hole=.65,color_discrete_sequence=COLORS),'overview-mix')
    a,b=st.columns([2,1])
    with a:
        st.subheader('10 sản phẩm có tiền hàng cao nhất')
        df=numeric(data['products'],['goods_amount']);df['billion_vnd']=df['goods_amount']/1e9
        chart(px.bar(df.sort_values('goods_amount'),x='billion_vnd',y='product_version',orientation='h',labels={'billion_vnd':'Tỷ đồng','product_version':''},color_discrete_sequence=[COLORS[1]]),'overview-products')
    with b:
        st.subheader('Các khoản tiền')
        st.metric('Tổng thanh toán',money(k['total_paid']))
        st.metric('VAT theo dữ liệu',money(k['vat_amount']))
        st.metric('Phí vận chuyển',money(k['shipping_fee']))
        st.caption('Không suy ra đã thu tiền thực tế khi nguồn không có trạng thái thanh toán.')
    table(data['trend'],'Bảng doanh số theo tháng','overview-monthly')


def olap(repo,filters):
    st.caption('Ngày đóng gói · Bộ lọc ở thanh bên áp dụng cho mọi phép OLAP. Tổng số khách và trung bình được tính lại theo từng phạm vi.')
    start=date.fromisoformat(filters['start']);end=date.fromisoformat(filters['end'])
    years=list(range(start.year,(end-timedelta(days=1)).year+1));year=st.selectbox('Năm dùng cho drill-down và slice',years,index=len(years)-1,key='olap-year')
    data=repo.olap(filters,year)
    tabs=st.tabs(['Roll-up','Drill-down','Slice','Dice','Pivot'])
    with tabs[0]:
        st.markdown('Gộp dữ liệu lên cấp năm.')
        if data['roll_up']:chart(px.bar(numeric(data['roll_up'],['goods_amount']),x='year',y='goods_amount',labels=LABELS,color_discrete_sequence=[COLORS[0]]),'olap-roll')
        table(data['roll_up'],'Tổng hợp theo năm','olap-roll')
    with tabs[1]:
        st.markdown(f'Đi sâu từ năm **{year} → quý → tháng**.')
        if data['drill_down']:chart(px.bar(numeric(data['drill_down'],['goods_amount']),x='month',y='goods_amount',color='quarter',labels=LABELS,color_discrete_sequence=COLORS),'olap-drill')
        table(data['drill_down'],'Chi tiết quý và tháng','olap-drill')
    with tabs[2]:
        st.markdown(f'Cố định chiều năm ở **{year}**, xem theo nhóm hàng.')
        if data['slice']:chart(px.bar(numeric(data['slice'],['goods_amount']),x='category',y='goods_amount',labels=LABELS,color_discrete_sequence=[COLORS[1]]),'olap-slice')
        table(data['slice'],'Lát cắt theo nhóm hàng','olap-slice')
    with tabs[3]:
        st.markdown('Chọn đồng thời khoảng ngày, nhóm hàng và quận/huyện ở thanh bên; xem các ô tháng × nhóm × địa bàn.')
        table(data['dice'],'Khối dữ liệu đã lọc','olap-dice')
    with tabs[4]:
        st.markdown('Xoay nhóm hàng thành dòng và năm thành cột. Giá trị: tiền hàng (₫).')
        rows=data['pivot']['rows']
        if rows:
            df=frame(rows).set_index('category').apply(pd.to_numeric,errors='coerce')
            chart(px.imshow(df,aspect='auto',color_continuous_scale=['#EEF8F7','#087F8C'],labels={'x':'Năm','y':'Nhóm hàng','color':'Tiền hàng (₫)'}),'olap-pivot')
        table(rows,'Bảng pivot tiền hàng','olap-pivot')
    st.caption('Tổng toàn phạm vi: '+money(data['grand_total']['goods_amount'])+' · '+number(data['grand_total']['customer_count'])+' khách duy nhất. Không cộng số khách giữa các ô để lấy tổng.')


def customers(repo,filters):
    data=repo.customers();model=data['model'];model_card(model)
    st.info('Trang ML dùng ngày tham chiếu logic và model đã ghim; bộ lọc bán hàng ở thanh bên không đổi snapshot đánh giá hoặc tập khách suy luận.')
    live,evaluation=st.tabs(['Phân khúc hiện tại','Đánh giá K-Means'])
    with live:
        rows=data['rows'];assigned=[r for r in rows if r['state']=='ASSIGNED']
        kpis([('Khách đã xử lý',number(len(rows)),f"Trên {data['expected']} khách trong kho"),('Có phân khúc',number(len(assigned)),'Dùng model cố định'),
              ('Ngày tham chiếu',str(rows[0]['reference_date']) if rows else '—','Không lấy ngầm ngày hệ thống')])
        if len(rows)<data['expected']:st.warning('Worker chưa xử lý đủ khách ở ngày tham chiếu hiện tại. Xem hàng đợi tại trang Vận hành dữ liệu.')
        if assigned:
            df=numeric(assigned,['recency_days','frequency','monetary']);df['cluster']=df['cluster_id'].astype(int).astype(str)
            a,b=st.columns([1,2])
            with a:
                st.subheader('Quy mô nhóm hiện tại')
                sizes=df.groupby('cluster').size().reset_index(name='customers')
                chart(px.bar(sizes,x='cluster',y='customers',labels={'cluster':'Cụm','customers':'Khách'},color='cluster',color_discrete_sequence=COLORS),'customer-size')
            with b:
                st.subheader('Mức gần đây và giá trị mua')
                sample=df.sort_values('customer_id').head(2000)
                chart(px.scatter(sample,x='recency_days',y='monetary',color='cluster',log_y=True,hover_data=['customer_id','frequency'],labels={'recency_days':'R (ngày)','monetary':'M (₫), thang log','cluster':'Cụm'},color_discrete_sequence=COLORS),'customer-scatter')
                st.caption(f'Hiển thị tối đa 2.000 khách theo mã; bảng CSV có toàn bộ khách đã xử lý. Cụm 0 không mặc định là VIP.')
            for col,field,label in zip(st.columns(3),['recency_days','frequency','monetary'],['R — ngày từ lần mua gần nhất','F — số đơn','M — tiền hàng (₫)']):
                with col:chart(px.box(df,x='cluster',y=field,labels={'cluster':'Cụm',field:label},color='cluster',color_discrete_sequence=COLORS),'customer-box-'+field)
        table(rows,'RFM và nhãn nhóm hiện tại','customer-live')
        st.caption('R dựa trên ngày đóng gói gần nhất; F là số đơn; M là tiền hàng. Khách không còn lịch sử hợp lệ có trạng thái NO_HISTORY.')
    with evaluation:
        ev=model['metadata']['evaluation']
        kpis([('K được chọn',str(ev['selected_k']),'Chọn từ validation'),('Silhouette test',number(ev['test']['silhouette'],3),'Điểm hình học, không phải accuracy'),('Davies–Bouldin test',number(ev['test']['davies_bouldin'],3),'Thấp hơn thường tốt hơn')])
        profile_rows=[{**r['profile'],'cluster_id':r['cluster_id'],'display_name':r['display_name']} for r in data['profiles']]
        table(profile_rows,'Hồ sơ nhóm trên snapshot huấn luyện','customer-profiles')
        st.markdown('**Gợi ý chăm sóc theo hồ sơ nhóm**')
        for row in data['profiles']:
            name=row['display_name']
            care='Ưu tiên tái kết nối và hỏi nhu cầu mua tiếp theo' if 'Lâu chưa quay lại' in name else 'Theo dõi sau mua và hỗ trợ lựa chọn linh kiện tương thích'
            if 'mua thường xuyên' in name:care+='; duy trì hậu mãi cho khách mua lặp lại'
            st.write(f"• Cụm {row['cluster_id']} — {name}. Gợi ý: {care.lower()}.")
        st.caption('Các gợi ý chăm sóc dựa trên mô tả hồ sơ nhóm, chưa được kiểm chứng bằng thử nghiệm kinh doanh.')
        candidates=[{'K':r['k'],'Silhouette validation':r['validation']['silhouette'],'DBI validation':r['validation']['davies_bouldin'],'ARI ổn định':r['median_stability_ari'],'Đạt điều kiện':r['eligible']} for r in ev['candidates']]
        table(candidates,'Lựa chọn K và độ ổn định','customer-candidates')
        st.caption('Chia theo khách; tiền xử lý chỉ fit train. Phân cụm không có nhãn VIP chuẩn, chưa đánh giá hành vi tương lai.')


def shipping(repo,filters):
    data=repo.shipping(filters)
    actual,live,evaluation=st.tabs(['Giao hàng thực tế','Dự đoán hiện tại','Đánh giá Random Forest'])
    with actual:
        st.caption('Bộ lọc ngày áp dụng theo thời điểm giao đi. Thời lượng = giờ thực nhận − giờ giao đi; không dùng ngày dự kiến làm SLA.')
        df=numeric(data['actual'],['delivery_hours']);valid=df.dropna(subset=['delivery_hours']) if not df.empty else df
        kpis([('Đơn giao đi',number(len(df)),'Trong bộ lọc'),('Có thời lượng hợp lệ',number(len(valid)),'Không âm và đủ hai mốc'),('Trung vị',number(valid['delivery_hours'].median(),1)+' giờ' if len(valid) else '—','Thời gian giao quan sát')])
        if len(valid):
            a,b=st.columns(2)
            with a:chart(px.histogram(valid,x='delivery_hours',nbins=40,labels={'delivery_hours':'Thời gian giao (giờ)'},color_discrete_sequence=[COLORS[0]]),'shipping-hist')
            with b:chart(px.box(valid,x='shipping_method',y='delivery_hours',color='shipping_method',color_discrete_sequence=COLORS,labels={'shipping_method':'Loại giao','delivery_hours':'Giờ'}),'shipping-box')
        table(data['actual'],'Thời gian giao theo đơn','shipping-actual')
    with live:
        st.caption('Dữ liệu hiện tại từ worker Phase 10; toàn bộ đơn thật đã có dự đoán, không áp bộ lọc doanh số. Hiển thị tối đa 300 đơn gần nhất. Demo xem ở trang Demo CDC.')
        if not data['live']:st.info('Chưa có dự đoán trực tuyến cho đơn thật. Các đơn lịch sử đã nhận không được tạo dự đoán hồi tố giả là trực tuyến.')
        table(data['live'],'Dự đoán ban đầu và outcome mới nhất','shipping-live')
        st.caption('Dự đoán ban đầu được giữ nguyên. DISPATCH_CORRECTED và INVALID_TIME không được gộp vào sai số hợp lệ.')
    with evaluation:
        model=data['model'];model_card(model);ev=model['metadata']['evaluation'];baseline=ev['baselines']['test']['by_shipping_method']
        st.info('Đánh giá cố định: train 2020–2023, validation 2024, test 2025; chỉ dùng nhãn đã nhận trước cutoff. Bộ lọc bán hàng không thay đổi tập test.')
        kpis([('MAE Random Forest',number(ev['test']['mae_hours'],2)+' giờ','Sai số tuyệt đối trung bình'),('MAE baseline',number(baseline['mae_hours'],2)+' giờ','Trung vị theo loại giao từ train'),('RMSE Random Forest',number(ev['test']['rmse_hours'],2)+' giờ','Nhạy với sai số lớn')])
        delta=(baseline['mae_hours']-ev['test']['mae_hours'])*60
        direction='giảm' if delta>=0 else 'tăng'
        st.warning(f'So với baseline theo loại giao, MAE Random Forest {direction} {number(abs(delta),1)} phút. Chênh lệch trên dữ liệu mô phỏng chưa chứng minh hiệu quả vận tải thật.')
        baselines=[{'Mô hình':'Random Forest','MAE (giờ)':ev['test']['mae_hours'],'RMSE (giờ)':ev['test']['rmse_hours']}]
        for key,label in [('global','Trung vị toàn train'),('by_shipping_method','Trung vị theo loại giao')]:
            value=ev['baselines']['test'].get(key)
            if value:baselines.append({'Mô hình':label,'MAE (giờ)':value['mae_hours'],'RMSE (giờ)':value['rmse_hours']})
        table(baselines,'So sánh trên cùng tập test cố định','rf-baselines')
        if data['test']:
            df=numeric(data['test'],['actual_hours','predicted_hours','error_hours']);a,b=st.columns(2)
            with a:
                fig=px.scatter(df,x='actual_hours',y='predicted_hours',opacity=.5,labels=LABELS,color_discrete_sequence=[COLORS[1]])
                lo=min(df['actual_hours'].min(),df['predicted_hours'].min());hi=max(df['actual_hours'].max(),df['predicted_hours'].max())
                fig.add_trace(go.Scatter(x=[lo,hi],y=[lo,hi],mode='lines',name='Dự đoán = thực tế',line=dict(color='#91A2B5',dash='dash')));chart(fig,'rf-scatter')
            with b:chart(px.histogram(df,x='error_hours',nbins=40,labels=LABELS,color_discrete_sequence=[COLORS[0]]),'rf-errors')
        groups=[]
        for dimension,items in ev['test_error_groups'].items():
            for r in items:groups.append({'Chiều':dimension,'Nhóm':r['group'],'Số mẫu':r['forest']['count'],'MAE RF (giờ)':r['forest']['mae_hours'],'MAE baseline (giờ)':r['baseline']['mae_hours'],'Ít hơn 30 mẫu':r['small_group']})
        table(groups,'Sai số test theo nhóm','rf-groups')
        importance=ev['permutation_importance_test']
        if importance:chart(px.bar(frame(importance).sort_values('mae_increase_hours'),x='mae_increase_hours',y='feature',orientation='h',error_x='std_hours',labels={'feature':'Đặc trưng','mae_increase_hours':'Tăng MAE khi xáo trộn (giờ)'},color_discrete_sequence=[COLORS[0]]),'rf-importance')
        st.caption('Permutation importance trên test chỉ để giải thích sau khi đóng băng mô hình; không chọn lại đặc trưng từ test, không diễn giải quan hệ nhân quả. Các đầu vào phải được biết tại lúc giao đi; Excel chưa có nhật ký nhập để chứng minh.')
        if ev.get('candidates'):
            rows=[{'max_depth':r['max_depth'],'min_samples_leaf':r['min_samples_leaf'],'MAE validation (giờ)':r['validation']['mae_hours'],'RMSE validation (giờ)':r['validation']['rmse_hours']} for r in ev['candidates']]
            table(rows,'Lựa chọn cấu hình trên validation','rf-candidates')
        st.download_button('↓ Báo cáo đánh giá mô hình (JSON)',json.dumps(ev,ensure_ascii=False,indent=2),file_name='rf-evaluation.json',mime='application/json',key='rf-report')
        table(data['test'],'Dự đoán và sai số trên test','rf-test')


def news(repo,filters):
    st.caption('Theo ngày xuất bản và nhóm hàng; bộ lọc địa bàn không áp dụng cho trang tin tức. Bài báo đọc từ kho hiện tại; độ phủ và đối chiếu đọc từ snapshot mart.')
    page=int(st.number_input('Trang danh sách tin (30 bài / trang)',min_value=1,value=1,step=1,key='news-page'))
    choices=filters.get('categories') or st.session_state['category_options']
    if not choices:st.info('Chưa có nhóm hàng để đối chiếu.');return
    category=st.selectbox('Nhóm dùng cho biểu đồ đối chiếu',choices,key='news-comparison')
    data=repo.news(filters,page,category)
    complete=sum(r['api_status']=='COMPLETE' for r in data['coverage'])
    kpis([('Bài quan sát',number(data['count']),'Đếm bài duy nhất trong kho'),('Tháng–nhóm API đầy đủ',number(complete),f"Trên {len(data['coverage'])} cửa sổ trong mart"),('Trang danh sách',number(page),f"Tối đa {max(1,(data['count']+29)//30)} trang")])
    st.warning('Phân loại DIRECT / INDIRECT / IRRELEVANT là quy tắc theo tiêu đề, không phải model ML. Seed là dữ liệu lưu sẵn; API là dữ liệu đã gọi nguồn. Thiếu độ phủ không đồng nghĩa không có tin.')
    a,b=st.columns([2,1])
    with a:
        st.subheader('Tin đã quan sát theo tháng')
        if data['monthly']:chart(px.bar(frame(data['monthly']),x='month',y='articles',labels=LABELS,color_discrete_sequence=[COLORS[0]]),'news-monthly')
        else:st.info('Chưa có tin trong khoảng chọn.')
    with b:
        st.subheader('Nguồn có nhiều bài')
        if data['sources']:chart(px.bar(frame(data['sources']).sort_values('articles'),x='articles',y='domain',orientation='h',labels=LABELS,color_discrete_sequence=[COLORS[1]]),'news-sources')
    for row in data['articles']:row['canonical_url']=safe_url(row.get('canonical_url'))
    table(data['articles'],'Danh sách bài báo và lý do liên quan','news-articles-page-'+str(page))
    with st.expander('Độ phủ API theo tháng và nhóm',expanded=False):table(data['coverage'],'Trạng thái độ phủ','news-coverage')
    st.subheader('Đối chiếu theo tháng · '+category)
    st.caption('Tổng hợp tiền hàng và tin DIRECT/INDIRECT riêng theo tháng rồi ghép; địa bàn là toàn bộ. Giữ đúng khoảng ngày chọn, kể cả tháng chưa trọn. Chỉ nối số tin so sánh khi API có độ phủ COMPLETE.')
    if data['comparison']:
        df=numeric(data['comparison'],['goods_amount','comparable_article_count'])
        fig=make_subplots(specs=[[{'secondary_y':True}]])
        fig.add_trace(go.Bar(x=df['month_start'],y=df['goods_amount']/1e9,name='Tiền hàng (tỷ ₫)',marker_color=COLORS[0]),secondary_y=False)
        fig.add_trace(go.Scatter(x=df['month_start'],y=df['comparable_article_count'],mode='lines+markers',name='Tin có độ phủ đầy đủ',connectgaps=False,line=dict(color=COLORS[3])),secondary_y=True)
        fig.update_yaxes(title_text='Tỷ đồng',secondary_y=False);fig.update_yaxes(title_text='Bài',secondary_y=True)
        chart(fig,'news-comparison-chart');table(data['comparison'],'Bảng đối chiếu và phần thiếu độ phủ','news-comparison-data')
    st.caption('Doanh số là mô phỏng; sự trùng thời gian với tin tức không chứng minh tin tức gây ra thay đổi doanh số.')


def detail(repo,filters):
    st.caption('Tra cứu toàn bộ lịch sử theo mã; không áp bộ lọc doanh số ở thanh bên. Chỉ hiển thị mã khách, không tên, số điện thoại hoặc địa chỉ đầy đủ.')
    with st.form('detail-search'):
        kind=st.selectbox('Loại tra cứu',['order','customer'],format_func=lambda x:'Đơn hàng' if x=='order' else 'Khách hàng',key='detail-kind')
        value=st.text_input('Mã cần tìm',max_chars=120,key='detail-value',placeholder='Nhập chính xác mã khách hoặc mã đơn')
        submitted=st.form_submit_button('Tra cứu')
    if not submitted and not st.session_state.get('detail-last'):st.info('Nhập mã để xem giao dịch, lịch sử nhóm và dự đoán đã lưu.');return
    if submitted:
        if not value.strip():st.warning('Nhập mã trước khi tra cứu.');return
        st.session_state['detail-last']=(kind,value.strip())
    kind,value=st.session_state['detail-last'];data=repo.detail(kind,value)
    if not data['orders']:st.info('Không tìm thấy giao dịch phù hợp với mã này.');return
    if any(r['is_demo'] for r in data['orders']):st.warning('Đang xem dữ liệu DEMO; các bản ghi này không được tính vào KPI kinh doanh.')
    table(data['orders'],'Giao dịch · tối đa 100 đơn gần nhất','detail-orders')
    df=numeric([r for r in data['orders'] if not r['is_deleted'] and r['packed_at'] is not None],['goods_amount'])
    if not df.empty:
        st.subheader('Lịch sử mua trong các đơn đang hiển thị')
        chart(px.scatter(df,x='packed_at',y='goods_amount',hover_data=['order_id'],labels={'packed_at':'Ngày đóng gói','goods_amount':'Tiền hàng (₫)'},color_discrete_sequence=[COLORS[0]]),'detail-timeline')
    table(data['segments'],'Lịch sử RFM và gán nhóm · tối đa 30 lần','detail-segments')
    table(data['predictions'],'Dự đoán ban đầu và outcome mới nhất','detail-predictions')


def operations(repo,filters):
    data=repo.operations();cdc=data['cdc'];workers=data['workers'];connector=data['connector']
    st.caption('Toàn hệ thống, không áp bộ lọc doanh số. Mốc vận hành hiển thị UTC. Tuổi heartbeat không phải độ trễ đầu cuối từ MySQL.')
    good=connector['connector']=='RUNNING' and bool(connector['tasks']) and all(r['state']=='RUNNING' for r in connector['tasks'])
    kpis([('Connector',connector['connector'],'Truy vấn trạng thái hiện tại'),('Worker còn heartbeat',f"{sum(bool(r['healthy']) for r in workers)} / {len(workers)}",'Ngưỡng 30 giây'),
          ('Sự kiện chờ chiếu',number(cdc['pending']),'Đã capture, chưa processed'),('Sự kiện đã lưu',number(cdc['events']),'Raw CDC bền vững')])
    if not good:st.warning('Chưa xác nhận connector và các task đều RUNNING. Xem bảng trạng thái và kiểm tra dịch vụ nguồn.')
    if any(not r['healthy'] for r in workers):st.warning('Có worker heartbeat cũ hoặc đang báo lỗi.')
    st.caption('Capture gần nhất: '+moment(cdc['latest_capture'])+' · Chiếu gần nhất: '+moment(cdc['latest_projection'])+
               ' · Trung bình capture → processed đã ghi nhận: '+number(cdc['avg_capture_to_process_seconds'],2)+' giây. Đây không phải phép đo end-to-end Phase 12.')
    if data['event_series']:chart(px.bar(frame(data['event_series']),x='minute',y='events',labels={'minute':'Phút capture (UTC)','events':'Sự kiện'},color_discrete_sequence=[COLORS[0]]),'ops-events')
    a,b=st.columns(2)
    with a:table(workers,'Worker và heartbeat','ops-workers')
    with b:table(data['queues'],'Hàng đợi suy luận','ops-queue')
    table(connector['tasks'],'Task của connector','ops-connector')
    tabs=st.tabs(['Chất lượng & lỗi','Lịch sử pipeline','Phiên bản mô hình','Ngày tham chiếu'])
    with tabs[0]:
        table(data['quality'],'Findings theo quy tắc · gồm lịch sử, không chỉ một lần chạy','ops-quality')
        table(data['errors'],'Lỗi chiếu theo mã và trạng thái','ops-errors')
    with tabs[1]:
        table(data['runs'],'30 lần chạy gần nhất được pipeline ghi nhận','ops-runs')
        st.caption('Đây là audit của pipeline, không thay thế trạng thái scheduler/DagRun bên trong Airflow. Trang này không khẳng định scheduler đang chạy chỉ từ các bản ghi cũ.')
    with tabs[2]:
        table(data['models'],'Phiên bản trong model registry','ops-models')
        st.caption('Model phục vụ suy luận lấy từ inference_config đã ghim. Cờ active trong registry không tự chuyển model của worker.')
    with tabs[3]:table(data['clock'],'Lịch sử đổi ngày RFM thật · preview demo không thay config','ops-clock')


def demo(repo,filters):
    if 'demo-suffix' not in st.session_state:st.session_state['demo-suffix']='WEB11_'+uuid.uuid4().hex[:10]
    suffix=st.session_state['demo-suffix'];data=repo.demo(suffix)
    st.info('Các nút chỉ thao tác đơn DEMO của phiên website này trong MySQL. CDC và worker tự xử lý phần tiếp theo; dữ liệu demo tách khỏi KPI và tập huấn luyện.')
    st.code(data['order_id'],language=None)
    try:source=perform(suffix,'status')
    except Exception:source=None;st.warning('Chưa đọc được nguồn MySQL. Kiểm tra dịch vụ rồi làm mới trang.')
    present=bool(source and source['exists'])
    a,b,c=st.columns(3)
    actions=[(a,'1. Thêm đơn demo','insert',present or source is None),(b,'2. Sửa và ghi nhận đã nhận','update',not present),(c,'3. Xóa đơn demo','delete',not present)]
    for col,label,command,disabled in actions:
        if col.button(label,key='demo-'+command,disabled=disabled,use_container_width=True):
            try:
                result=perform(suffix,command);st.session_state['demo-last-action']=result
                st.rerun()
            except Exception as exc:st.error('Chưa thực hiện được thao tác demo ('+type(exc).__name__+'). Kiểm tra nguồn và thử lại.')
    if st.session_state.get('demo-last-action'):st.success('Lệnh nguồn gần nhất: '+st.session_state['demo-last-action']['action']+'. Bấm Làm mới dữ liệu để theo dõi CDC và ML.')
    kpis([('MySQL',('Có đơn' if present else 'Chưa có / đã xóa') if source is not None else 'Chưa kết nối','Trạng thái nguồn hiện tại'),
          ('Kho dữ liệu','Đã xóa' if data['fact'] and data['fact']['is_deleted'] else 'Có đơn' if data['fact'] else 'Đang chờ','Trạng thái sau CDC'),
          ('Dự đoán đã lưu',number(len(data['predictions'])),'Dự đoán ban đầu giữ nguyên')])
    if present and not data['fact']:st.warning('Nguồn đã có đơn; đang chờ CDC chuyển vào kho. Làm mới sau vài giây.')
    table([data['fact']] if data['fact'] else [],'Đơn demo trong fact','demo-fact')
    a,b=st.columns(2)
    with a:table(data['jobs'],'Công việc suy luận gần nhất','demo-jobs')
    with b:table(data['segments'],'RFM và lịch sử nhóm demo','demo-segments')
    table(data['predictions'],'Dự đoán gốc · input và model version','demo-predictions')
    table(data['outcomes'],'Kết quả thực nhận và sai số ghi thêm','demo-outcomes')
    st.caption('Sau khi demo xong, bấm Xóa đơn demo để dọn nguồn. Kho giữ tombstone, lịch sử RFM và dự đoán làm bằng chứng. Đây là trạng thái quan sát hiện tại, chưa phải phép đo hiệu năng.')


RENDERERS={'overview':overview,'olap':olap,'customers':customers,'shipping':shipping,'news':news,'detail':detail,'operations':operations,'demo':demo}


def main():
    st.set_page_config(page_title='LAK Analytics · Kho dữ liệu & ML',page_icon='◈',layout='wide',initial_sidebar_state='expanded')
    st.markdown('''<style>
    .block-container{padding-top:1.7rem;padding-bottom:3rem;max-width:1550px}
    h1,h2,h3{letter-spacing:-.035em}h1{font-size:2.25rem!important}h3{font-size:1.18rem!important}
    [data-testid="stSidebar"]{background:#fff;border-right:1px solid #e4eaf2}
    [data-testid="stMetricValue"]{font-size:1.6rem;font-weight:650;letter-spacing:-.035em}
    [data-testid="stVerticalBlockBorderWrapper"]{border-radius:15px}
    .lak-brand{font-size:1.45rem;font-weight:800;letter-spacing:-.06em;color:#16324f}.lak-brand span{color:#087f8c}
    .lak-label{font-size:.7rem;font-weight:700;letter-spacing:.17em;color:#8291a3;margin:1.2rem 0 .5rem}
    .lak-banner{padding:14px 19px;border-radius:13px;background:linear-gradient(110deg,#153c52,#087f8c);color:white;margin-bottom:22px;font-size:.88rem}
    .lak-banner b{letter-spacing:.08em;margin-right:12px}.lak-foot{font-size:.74rem;color:#8291a3;margin-top:25px;line-height:1.6}
    </style>''',unsafe_allow_html=True)
    with st.sidebar:
        st.markdown('<div class="lak-brand">LAK<span> / Analytics</span></div>',unsafe_allow_html=True)
        st.caption('Kho dữ liệu · Khai phá dữ liệu')
        st.markdown('<div class="lak-label">KHÔNG GIAN PHÂN TÍCH</div>',unsafe_allow_html=True)
        page=st.radio('Điều hướng',list(PAGES),format_func=lambda x:PAGES[x][2]+'  '+PAGES[x][0],key='page',label_visibility='collapsed')
        if st.button('↻ Làm mới dữ liệu',use_container_width=True,key='refresh'):st.rerun()
    try:
        with Repository() as repo:
            settings=repo.settings();st.session_state['category_options']=settings['categories']
            with st.sidebar:
                st.markdown('<div class="lak-label">BỘ LỌC KINH DOANH</div>',unsafe_allow_html=True)
                bounds=settings['bounds'] or {};first=bounds.get('first_date') or date(2020,1,1);last=bounds.get('last_date') or date(2025,12,31)
                chosen=st.date_input('Từ ngày — đến ngày',value=(first,last),format='DD/MM/YYYY',key='date-range')
                categories=st.multiselect('Nhóm hàng',settings['categories'],placeholder='Tất cả nhóm hàng',key='categories')
                districts=st.multiselect('Quận / huyện',settings['districts'],placeholder='Tất cả địa bàn',key='districts')
                st.caption('Giờ giao dịch giữ theo nguồn; mốc vận hành ghi UTC.')
                st.caption('Bộ lọc áp dụng cho bán hàng, giao thực tế và tin tức theo mô tả từng trang. Đánh giá ML dùng snapshot riêng.')
                cfg=settings['inference'] or {};st.caption('Ngày RFM logic: '+str(cfg.get('reference_date','chưa có')))
                st.markdown('<div class="lak-foot">LAK Analytics<br>Dữ liệu giao dịch mô phỏng<br>Giao diện nội bộ phục vụ phân tích</div>',unsafe_allow_html=True)
            title,description,_=PAGES[page]
            st.markdown('<div class="lak-banner"><b>LAK ANALYTICS</b> KHO DỮ LIỆU &nbsp; / &nbsp; MINING &nbsp; / &nbsp; CDC</div>',unsafe_allow_html=True)
            st.title(title);st.caption(description)
            snapshot=settings['snapshot'] or {}
            st.caption('Mart cập nhật: '+moment(snapshot.get('refreshed_at'))+' · Kho hiện tại được đọc lúc: '+moment(settings['queried_at']))
            if settings.get('missing_packed',{}).get('orders'):
                st.warning('Có '+number(settings['missing_packed']['orders'])+' đơn thiếu ngày đóng gói ('+money(settings['missing_packed']['goods_amount'])+'). Chúng vẫn nằm trong fact, không nằm trong bộ lọc thời gian đóng gói.')
            if not snapshot:st.warning('Mart chưa có snapshot. Chưa thể hiển thị KPI đã đối soát.')
            elif snapshot.get('refreshed_at') and (settings['queried_at']-snapshot['refreshed_at']).total_seconds()>1800:
                st.warning('Snapshot mart đã quá 30 phút. Kiểm tra lịch refresh; số liệu trực tiếp từ kho có thể mới hơn mart.')
            if len(chosen)!=2:st.warning('Chọn đủ ngày bắt đầu và ngày kết thúc.');return
            filters=period(chosen[0],chosen[1],categories,districts)
            RENDERERS[page](repo,filters)
    except Exception as exc:
        st.error('Chưa tải được dữ liệu ('+type(exc).__name__+'). Kiểm tra kết nối kho và dịch vụ liên quan, rồi bấm Làm mới dữ liệu.')
        import logging
        from src.cdc.cli import sanitize
        logging.getLogger('lak.dashboard').error('%s',sanitize(str(exc)))


if __name__=='__main__':main()
