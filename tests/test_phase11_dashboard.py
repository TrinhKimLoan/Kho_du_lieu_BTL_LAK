import unittest
import subprocess
import sys
from datetime import date,datetime,timezone,timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch,Mock
from streamlit.testing.v1 import AppTest
from src.dashboard.formatting import money,compact_money,number,period,safe_url,csv_bytes
from src.dashboard.demo import validate_suffix,perform
from src.dashboard.repository import Repository

BASE=Path(__file__).resolve().parents[1]


def salesrow(**overrides):
    return dict(order_count=2,customer_count=2,goods_amount=Decimal('400000.00'),total_paid=Decimal('445000.00'),vat_amount=Decimal('40000.00'),
      shipping_fee=Decimal('5000.00'),quantity_sum=4,avg_order_goods=Decimal('200000'),avg_delivery_hours=Decimal('27'),
      delivery_hours_sum=Decimal('54'),delivered_orders=2,**overrides)


def model(algorithm):
    candidate={'k':2,'validation':{'silhouette':.4,'davies_bouldin':.8},'median_stability_ari':.9,'eligible':True}
    rfm={'selected_k':2,'test':{'silhouette':.4,'davies_bouldin':.8},'candidates':[candidate]}
    rf={'test':{'mae_hours':18.73,'rmse_hours':22.90},'baselines':{'test':{'global':{'mae_hours':47.8,'rmse_hours':61.3},'by_shipping_method':{'mae_hours':18.83,'rmse_hours':23.09}}},
        'test_error_groups':{'shipping_method':[{'group':'FAST','forest':{'count':1,'mae_hours':1},'baseline':{'mae_hours':2},'small_group':True}]},
        'permutation_importance_test':[{'feature':'shipping_method','mae_increase_hours':.5,'std_hours':.1}]}
    return {'algorithm':algorithm,'model_id':'km-fixture' if algorithm=='kmeans_rfm' else 'rf-fixture','created_at':datetime.now(timezone.utc),
            'snapshot_id':'fixture','metadata':{'evaluation':rfm if algorithm=='kmeans_rfm' else rf}}


class FakeRepo:
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def settings(self):
        now=datetime.now(timezone.utc)
        return {'categories':['RAM'],'districts':['D1'],'bounds':{'first_date':date(2020,1,1),'last_date':date(2025,12,31)},
          'snapshot':{'refreshed_at':now},'queried_at':now,'inference':{'reference_date':date(2026,1,1)}}
    def overview(self,filters):return {'kpi':salesrow(),'trend':[salesrow(month='2025-01')],'categories':[salesrow(category='RAM')],'products':[salesrow(product_version='P1: RAM')]}
    def olap(self,filters,year):return {'roll_up':[salesrow(year=2025)],'drill_down':[salesrow(year=2025,quarter='2025-Q1',month='2025-01')],
        'slice':[salesrow(category='RAM')],'dice':[salesrow(month='2025-01',category='RAM',district='D1')],
        'pivot':{'rows':[{'category':'RAM','2025':400000}]},'grand_total':salesrow()}
    def customers(self):return {'model':model('kmeans_rfm'),'expected':2,
        'rows':[{'customer_id':'C1','cluster_id':0,'state':'ASSIGNED','recency_days':'12','frequency':'2','monetary':'200000.00','reference_date':date(2026,1,1)},
                {'customer_id':'C2','cluster_id':1,'state':'ASSIGNED','recency_days':'35','frequency':'3','monetary':'300000.00','reference_date':date(2026,1,1)}],
        'profiles':[{'cluster_id':i,'display_name':name,'customer_count':1,
          'profile':{'cluster_id':i,'name':name,'customers':1,'share':.5,'median_R_days':r,'median_F_orders':f,
                     'median_M_vnd':m,'monetary_total_vnd':str(m),'split_counts':{'train':1,'validation':0,'test':0}}}
          for i,name,r,f,m in [(0,'Gần đây; mua ít; chi tiêu thấp',12,2,200000),(1,'Lâu chưa quay lại; mua thường xuyên; chi tiêu cao',35,3,300000)]]}
    def shipping(self,filters):return {'model':model('random_forest_delivery'),
        'actual':[{'order_id':'O1','delivery_hours':27,'shipping_method':'FAST','district':'D1','dispatched_at':datetime(2025,1,1)}],
        'live':[{'order_id':'O2','predicted_hours':28,'actual_hours':None,'state':'PENDING'}],
        'test':[{'order_id':'O1','actual_hours':27,'predicted_hours':28,'error_hours':1,'baseline_hours':29}]}
    def news(self,filters,page=1,category=None):return {'count':1,
        'articles':[{'article_key':'A1','title':'RAM fixture — dữ liệu kiểm thử','canonical_url':'https://example.org/a','domain':'example.org','published_date':date(2024,1,1),'relevance_level':'DIRECT','origin':'seed'}],
        'monthly':[{'month':'2024-01','articles':1}],'sources':[{'domain':'example.org','articles':1}],
        'coverage':[{'month_start':date(2024,1,1),'api_status':'PARTIAL'}],
        'comparison':[{'month_start':date(2024,1,1),'goods_amount':100000,'observed_articles':1,'comparable_article_count':None,'api_coverage':'PARTIAL'}]}
    def detail(self,kind,value):return {'orders':[{'order_id':'O1','customer_id':'C1','goods_amount':100000,'packed_at':datetime(2025,1,1),'is_demo':False,'is_deleted':False}],'segments':[],'predictions':[]}
    def operations(self):return {'connector':{'connector':'RUNNING','tasks':[{'task':0,'state':'RUNNING'}]},
        'cdc':{'events':3,'pending':0,'latest_capture':datetime.now(timezone.utc),'latest_projection':datetime.now(timezone.utc),'avg_capture_to_process_seconds':.2},
        'workers':[{'worker':'collector','healthy':True}],'event_series':[{'minute':datetime.now(timezone.utc),'events':3}],
        'queues':[{'kind':'RFM','state':'DONE','is_demo':False,'jobs':2}],'errors':[],'quality':[],
        'runs':[{'pipeline':'fixture','status':'SUCCESS'}],'models':[],'clock':[]}
    def demo(self,suffix):return {'order_id':'DEMO_'+suffix+'_O','fact':None,'jobs':[],'segments':[],'predictions':[],'outcomes':[]}


class DashboardTests(unittest.TestCase):
    def test_inclusive_ui_end_becomes_exclusive_query_end(self):
        f=period(date(2025,1,1),date(2025,1,31),['RAM'],['D1'])
        self.assertEqual(f['end'],'2025-02-01');self.assertEqual(f['categories'],['RAM'])
    def test_invalid_period(self):
        with self.assertRaises(ValueError):period(date(2025,2,1),date(2025,1,1))
    def test_money_keeps_decimal(self):self.assertEqual(money(Decimal('618293800000')),'618.293.800.000 ₫')
    def test_compact_money_preserves_unit(self):self.assertEqual(compact_money(618293800000),'618,29 tỷ ₫')
    def test_safe_links(self):
        for url in ['javascript:alert(1)','file:///etc/passwd','https://u:p@example.org/a','https://[invalid']:
            self.assertIsNone(safe_url(url))
        self.assertEqual(safe_url('https://example.org/a'),'https://example.org/a')
    def test_csv_formula_and_encoding(self):
        result=csv_bytes([{'title':'=1+1','money':Decimal('123.45')}]).decode('utf-8-sig')
        self.assertIn("'=1+1",result);self.assertIn('123.45',result)
    def test_arbitrary_demo_suffix_rejected(self):
        for suffix in ['MANUAL','REAL_O1','WEB11_abc;drop','WEB11_123']:
            with self.assertRaises(ValueError):validate_suffix(suffix)
    def test_demo_write_guard_before_connection(self):
        with patch('src.dashboard.demo.connect') as connection:
            with self.assertRaises(ValueError):perform('REAL','delete')
            connection.assert_not_called()
    def test_demo_only_allowed_actions(self):
        with self.assertRaises(ValueError):perform('WEB11_0123456789','truncate')
    def test_detail_value_is_bound_parameter(self):
        repo=Repository();repo.all=Mock(return_value=[])
        dangerous="x'; DROP TABLE dw.fact_sales; --"
        repo.detail('order',dangerous)
        for call in repo.all.call_args_list:
            self.assertNotIn(dangerous,call.args[0]);self.assertIn(dangerous,call.args[1])
    def test_all_eight_ui_pages(self):
        with patch('src.dashboard.repository.Repository',FakeRepo),patch('src.dashboard.ui.perform',return_value={'exists':False}):
            at=AppTest.from_file(str(BASE/'streamlit_app.py'),default_timeout=30).run()
            for page in ['overview','olap','customers','shipping','news','detail','operations','demo']:
                at.radio(key='page').set_value(page).run()
                self.assertFalse(at.exception,repr(at.exception));self.assertFalse(at.error,repr(at.error))

    def test_customer_profile_with_nested_cluster_id(self):
        with patch('src.dashboard.repository.Repository',FakeRepo):
            at=AppTest.from_file(str(BASE/'streamlit_app.py'),default_timeout=30).run()
            at.radio(key='page').set_value('customers').run()
            self.assertFalse(at.exception);self.assertFalse(at.error)
            tables=[element.value for element in at.dataframe if 'display_name' in element.value.columns]
            self.assertEqual(len(tables),1)
            self.assertEqual(tables[0]['Cụm'].tolist(),[0,1])
            self.assertEqual(tables[0]['customers'].sum(),2)

    def test_cold_import_in_fresh_python_process(self):
        code="""import sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import src.dashboard.ui
import app.core
assert Path(app.core.__file__).resolve()==Path(sys.argv[2]).resolve()
assert callable(src.dashboard.ui.main)
"""
        result=subprocess.run([sys.executable,'-c',code,str(BASE/'src/dashboard'),str(BASE/'app/core.py')],
                              cwd=BASE,capture_output=True,text=True,timeout=45)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse((BASE/'src/dashboard/app.py').exists())

    def test_ui_lookup(self):
        with patch('src.dashboard.repository.Repository',FakeRepo),patch('src.dashboard.ui.perform',return_value={'exists':False}):
            at=AppTest.from_file(str(BASE/'streamlit_app.py'),default_timeout=30).run()
            at.radio(key='page').set_value('detail').run();at.text_input(key='detail-value').set_value('O1')
            at.button(key='FormSubmitter:detail-search-Tra cứu').click().run()
            self.assertFalse(at.error);self.assertFalse(at.exception);self.assertGreater(len(at.dataframe),0)
    def test_ui_demo_buttons_use_generated_scope(self):
        state={'exists':False};mutations=[]
        def source(suffix,command):
            validate_suffix(suffix)
            if command=='status':return {'exists':state['exists']}
            mutations.append(command);state['exists']=command!='delete';return {'action':command}
        with patch('src.dashboard.repository.Repository',FakeRepo),patch('src.dashboard.ui.perform',side_effect=source):
            at=AppTest.from_file(str(BASE/'streamlit_app.py'),default_timeout=30).run();at.radio(key='page').set_value('demo').run()
            for command in ['insert','update','delete']:at.button(key='demo-'+command).click().run()
            self.assertEqual(mutations,['insert','update','delete']);self.assertFalse(at.error);self.assertFalse(at.exception)
    def test_ui_connection_error_hides_secret(self):
        with patch.dict('os.environ',{'LAK_POSTGRES_PASSWORD':'fixture-sensitive-value'}),patch('src.dashboard.repository.Repository',side_effect=RuntimeError('fixture-sensitive-value')):
            at=AppTest.from_file(str(BASE/'streamlit_app.py'),default_timeout=30).run()
            self.assertTrue(at.error);self.assertNotIn('fixture-sensitive-value',at.error[0].value)
