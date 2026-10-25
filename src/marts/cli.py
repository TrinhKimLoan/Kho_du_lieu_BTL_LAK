import argparse
import csv
import json
import sys
import traceback
from datetime import datetime,timezone
from pathlib import Path
from src.cdc.store import pg
from src.cdc.cli import sanitize
from .refresh import acquire,migrate,refresh,source_state
from .checks import reconcile,fixtures
from .queries import examples,news


def main():
    parser=argparse.ArgumentParser(description='LAK phase 7 mart refresh, reconciliation and OLAP')
    parser.add_argument('command',choices=['check','refresh','verify'])
    parser.add_argument('--evidence-dir',type=Path,required=True)
    parser.add_argument('--label',default='result')
    args=parser.parse_args()
    if not args.label.replace('-','').isalnum():parser.error('Invalid evidence label')
    args.evidence_dir.mkdir(parents=True,exist_ok=True);path=args.evidence_dir/(args.label+'.json')
    if path.exists():parser.error('Evidence already exists')
    result={'phase':7,'command':args.command,'passed':False,'checked_at_utc':datetime.now(timezone.utc).isoformat()}
    try:
        with pg() as connection:
            acquire(connection);migrate(connection)
            before=source_state(connection)
            data={}
            if args.command in ('check','refresh'):data['refresh']=refresh(connection)
            with connection.transaction():
                connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
                data['reconciliation']=reconcile(connection)
                data['olap']=examples(connection)
                data['news_month_category']=news(connection)
            if args.command=='check':
                data['fixtures']=fixtures(connection)
                with connection.transaction():
                    connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
                    data['after_fixtures']=reconcile(connection)
            if source_state(connection)!=before:raise RuntimeError('Source data changed during mart checks; rerun after source writers finish')
            data['source_facts_and_news_unchanged']=True
        result.update(passed=True,result=data)
    except Exception as exc:
        result.update(error_type=type(exc).__name__,safe_message=sanitize(str(exc))[:2400])
        print(sanitize(traceback.format_exc(limit=8)),file=sys.stderr)
    text=json.dumps(result,ensure_ascii=False,indent=2,default=str)+'\n';path.write_text(text,encoding='utf-8')
    exports=dict(result.get('result',{}).get('olap',{}))
    if result['passed']:exports['news-month-category']=result['result']['news_month_category']
    for name,table in exports.items():
        rows=table.get('rows',[]) if name=='pivot' else table
        if rows:
            with (args.evidence_dir/(args.label+'-'+name+'.csv')).open('w',encoding='utf-8-sig',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    summary={k:v for k,v in result.items() if k!='result'}
    if result['passed']:
        data=result['result'];summary.update(refresh=data.get('refresh'),reconciliation=data['reconciliation'],
            fixtures=data.get('fixtures'),olap_examples=list(data['olap']),source_facts_and_news_unchanged=True)
    print(json.dumps(summary,ensure_ascii=False,indent=2,default=str));print('Evidence: '+str(path))
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
