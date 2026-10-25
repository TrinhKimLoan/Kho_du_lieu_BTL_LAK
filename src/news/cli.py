import argparse
import csv
import json
import sys
import traceback
from datetime import datetime,timezone,date
from pathlib import Path
from src.cdc.cli import sanitize
from src.cdc.store import pg
from .store import migrate


def main():
    parser=argparse.ArgumentParser(description='LAK phase 6 MediaCloud metadata and stored-news checks')
    parser.add_argument('command',choices=['check','fetch','report'])
    parser.add_argument('--evidence-dir',type=Path)
    parser.add_argument('--label',default='result')
    parser.add_argument('--year',type=int,default=2024)
    parser.add_argument('--month',type=int,default=12)
    parser.add_argument('--collection-id',type=int,default=34412246)
    parser.add_argument('--max-pages',type=int,default=2)
    args=parser.parse_args()
    if args.evidence_dir is None:parser.error('--evidence-dir is required')
    if not args.label.replace('-','').isalnum():parser.error('Invalid evidence label')
    args.evidence_dir.mkdir(parents=True,exist_ok=True);path=args.evidence_dir/(args.label+'.json')
    if path.exists():parser.error('Evidence already exists')
    result={'phase':6,'command':args.command,'passed':False,'checked_at_utc':datetime.now(timezone.utc).isoformat()}
    try:
        with pg() as connection:
            if not connection.execute('SELECT pg_try_advisory_lock(274106) locked').fetchone()['locked']:raise RuntimeError('Another news writer is running')
            migrate(connection)
            if args.command=='check':
                from .checks import check
                data=check(connection);passed=data['passed']
            elif args.command=='fetch':
                from .fetch import fetch_month
                from .report import report
                data=fetch_month(connection,args.year,args.month,collection_id=args.collection_id,max_pages=args.max_pages)
                data['news_report']=report(connection,args.collection_id);passed=data['status']!='FAILED'
            else:
                from .report import report
                data=report(connection,args.collection_id);passed=True
        result.update(passed=passed,result=data)
    except Exception as exc:
        result.update(error_type=type(exc).__name__,safe_message=sanitize(str(exc))[:2400])
        print(sanitize(traceback.format_exc(limit=8)),file=sys.stderr)
    text=json.dumps(result,ensure_ascii=False,indent=2,default=str)+'\n'
    path.write_text(text,encoding='utf-8')
    data=result.get('result',{})
    for suffix,rows in [('coverage',data.get('news_report',{}).get('coverage',[])),('review',data.get('sample_review',{}).get('comparisons',[]))]:
        if rows:
            with (args.evidence_dir/(args.label+'-'+suffix+'.csv')).open('w',encoding='utf-8-sig',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    summary={k:v for k,v in result.items() if k!='result'}
    if result['passed']:
        summary['result']={k:v for k,v in data.items() if k not in ('news_report','sample_review')}
        if 'news_report' in data:summary['news_counts']=data['news_report']['counts_by_relevance']
        if 'sample_review' in data:
            summary['sample_review']={k:v for k,v in data['sample_review'].items() if k!='comparisons'}
    print(json.dumps(summary,ensure_ascii=False,indent=2,default=str));print('Evidence: '+str(path))
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
