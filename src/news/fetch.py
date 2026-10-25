import calendar
import json
from datetime import date
from src.source.data import ROOT
from src.cdc.project import category
from .api import MediaCloud,pages
from .model import digest
from .store import begin_run,finish_run,ingest_page


def config():
    return json.loads((ROOT/'config/category_rules.json').read_text())['queries']


def signature(group,query,collection_id,month):
    return digest({'group':group,'query':query,'collection':collection_id,'month':month.isoformat(),'platform':'onlinenews-mediacloud'})


def prepare_coverage(connection,collection_id=34412246):
    from psycopg.types.json import Jsonb
    months=connection.execute("SELECT generate_series(date_trunc('month',min(packed_at)),date_trunc('month',max(packed_at)),interval '1 month')::date AS month FROM dw.v_sales_analysis").fetchall()
    for item in months:
        month=item['month']
        for group,query in config().items():
            connection.execute('''INSERT INTO audit.news_coverage(month_start,category_key,query_signature,origin,status,observed_at,details)
                VALUES(%s,%s,%s,'api','NOT_FETCHED',now(),%s) ON CONFLICT DO NOTHING''',(month,category(connection,group),signature(group,query,collection_id,month),Jsonb({'collection_id':collection_id,'query':query})))


def fetch_month(connection,year,month,fetch=None,page_size=100,max_pages=2,collection_id=34412246):
    from psycopg.types.json import Jsonb
    start=date(year,month,1);last=date(year,month,calendar.monthrange(year,month)[1])
    today=date.today();end=min(last,today)
    if start>today:raise ValueError('Cannot fetch a future month')
    run_id=begin_run(connection,'api',{'start':start.isoformat(),'end':end.isoformat(),'collection_id':collection_id})
    results={};failed=False
    try:
        fetch=fetch or MediaCloud()
        for group,query in config().items():
            sig=signature(group,query,collection_id,start)
            summary={'pages':0,'rows':0,'invalid':0,'status':'PARTIAL','reason':None,'changes':{}}
            try:
                for number,body,status,reason in pages(fetch,query,start,end,collection_id,page_size,max_pages):
                    stats=ingest_page(connection,run_id,group,number,body,'api',{'query':query,'start':start.isoformat(),'end':end.isoformat(),'collection_id':collection_id,'page_size':page_size})
                    summary.update(pages=number,status=status,reason=reason)
                    summary['rows']+=len(body['stories']);summary['invalid']+=stats['INVALID']
                    for kind,n in stats.items():summary['changes'][kind]=summary['changes'].get(kind,0)+n
                if summary['invalid']:summary.update(status='PARTIAL',reason='INVALID_RECORDS')
                if end<last:summary.update(status='PARTIAL',reason='MONTH_NOT_FINISHED')
            except Exception as exc:
                failed=True;summary.update(status='FAILED',reason=type(exc).__name__+': '+str(exc)[:500])
            results[group]=summary
            connection.execute('''INSERT INTO audit.news_fetch_windows(run_id,query_group,query_signature,start_date,end_date,status,pages,rows_seen,invalid_rows,reason)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',(run_id,group,sig,start,end,summary['status'],summary['pages'],summary['rows'],summary['invalid'],summary['reason']))
            connection.execute('''INSERT INTO audit.news_coverage(month_start,category_key,query_signature,origin,status,observed_at,details)
                VALUES(%s,%s,%s,'api',%s,now(),%s) ON CONFLICT(month_start,category_key,query_signature,origin)
                DO UPDATE SET status=excluded.status,observed_at=excluded.observed_at,details=excluded.details''',(start,category(connection,group),sig,summary['status'],Jsonb(dict(summary,run_id=str(run_id),collection_id=collection_id,query=query))))
        status='FAILED' if failed else 'PARTIAL' if any(r['status']!='COMPLETE' for r in results.values()) else 'SUCCESS'
        result={'run_id':str(run_id),'live_api':True,'status':status,'groups':results,'collection_id':collection_id,
                'note':'COMPLETE means requested queries exhausted for this month, not all news on the internet'}
        finish_run(connection,run_id,status,result)
        return result
    except Exception as exc:
        finish_run(connection,run_id,'FAILED',{'error_type':type(exc).__name__});raise
