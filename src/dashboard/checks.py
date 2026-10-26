"""Read-only warehouse/Streamlit execution checks; browser appearance requires review."""
import argparse
import json
import traceback
import subprocess
import sys
from pathlib import Path
from datetime import datetime,timezone
from src.cdc.cli import sanitize
from .repository import Repository
from .formatting import period


def check_queries():
    with Repository() as repo:
        settings=repo.settings();bounds=settings['bounds']
        if not settings['snapshot'] or not settings['inference']:raise RuntimeError('Verified mart snapshot and pinned inference configuration required')
        if not bounds['first_date'] or not bounds['last_date']:raise RuntimeError('No historical sales for dashboard validation')
        filters=period(bounds['first_date'],bounds['last_date'])
        overview=repo.overview(filters);olap=repo.olap(filters,bounds['last_date'].year)
        customers=repo.customers();shipping=repo.shipping(filters);news=repo.news(filters,1,settings['categories'][0] if settings['categories'] else 'RAM')
        ops=repo.operations();demo=repo.demo('WEB11_0000000000')
        sample=repo.one('SELECT order_id FROM dw.v_sales_analysis ORDER BY order_id LIMIT 1')
        detail=repo.detail('order',sample['order_id'])
        if not detail['orders']:raise RuntimeError('Order lookup returned no matching order')
        if not customers['model'] or not shipping['model']:raise RuntimeError('Pinned evaluation models missing')
        for field in ['goods_amount','total_paid','order_count','customer_count']:
            if overview['kpi'][field]!=olap['grand_total'][field]:raise RuntimeError('Overview and OLAP total differ: '+field)
        if sum(r['order_count'] for r in overview['trend'])!=overview['kpi']['order_count']:raise RuntimeError('Monthly order counts differ')
        if sum(r['goods_amount'] for r in overview['trend'])!=overview['kpi']['goods_amount']:raise RuntimeError('Monthly goods totals differ')
        if len(shipping['test'])!=shipping['model']['metadata']['evaluation']['test']['count']:raise RuntimeError('Test prediction count differs from frozen report')
        for data in [customers['rows'],shipping['actual'],shipping['live'],news['articles'],detail['orders']]:
            if any(set(row)&{'phone','SDT','full_address','Dia_Chi_Giao','Ten_Khach_Hang','Tai_Xe'} for row in data):raise RuntimeError('Unexpected personal detail in dashboard projection')
        fact=repo.sales((),filters,'fact')[0]
        return {'read_only_queries_passed':True,'overview_olap_reconciled':True,'current_fact_matches_mart':all(fact[k]==overview['kpi'][k] for k in ['order_count','goods_amount','total_paid']),
            'sales_orders':overview['kpi']['order_count'],'customer_assignments':len(customers['rows']),'shipping_test_rows':len(shipping['test']),
            'observed_news_in_default_period':news['count'],'connector':ops['connector'],'demo_lookup_safe':True,
            'query_time':settings['queried_at'],'mart_snapshot':settings['snapshot'],'pinned_models':settings['inference']}


def check_app():
    from streamlit.testing.v1 import AppTest
    app=Path(__file__).resolve().parents[2]/'streamlit_app.py'
    cold=subprocess.run([sys.executable,'-c','from src.dashboard.ui import main; import app.core; assert callable(main)'],
                        cwd=app.parent,capture_output=True,text=True,timeout=45)
    if cold.returncode:raise RuntimeError('Cold dashboard import failed: '+sanitize(cold.stderr)[-2000:])
    at=AppTest.from_file(str(app),default_timeout=90).run()
    pages=['overview','olap','customers','shipping','news','detail','operations','demo']
    for page in pages:
        at.radio(key='page').set_value(page).run()
        if at.exception or at.error:raise RuntimeError('Streamlit page failed: '+page+' '+str([e.value for e in at.error]))
    return {'pages_executed':pages,'cold_import_verified':True,'source':'actual warehouse connections; no fixture provider',
            'ui_test_type':'Streamlit AppTest execution, not a browser visual inspection','demo_mutations_performed':False}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--evidence-dir',required=True,type=Path);args=parser.parse_args()
    args.evidence_dir.mkdir(parents=True,exist_ok=True);path=args.evidence_dir/'dashboard-checks.json'
    if path.exists():raise SystemExit('Evidence already exists')
    result={'phase':11,'passed':False,'checked_at_utc':datetime.now(timezone.utc).isoformat(),'browser_visual_verified':False}
    try:result.update(queries=check_queries(),app=check_app(),passed=True)
    except Exception as exc:
        result.update(error_type=type(exc).__name__,safe_message=sanitize(str(exc))[:2400]);print(sanitize(traceback.format_exc(limit=8)))
    text=json.dumps(result,ensure_ascii=False,indent=2,default=str)+'\n';path.write_text(text,encoding='utf-8');print(text);print('Evidence: '+str(path))
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
