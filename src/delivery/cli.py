import argparse
import json
import sys
import traceback
import uuid
from datetime import datetime,timezone
from pathlib import Path
from src.cdc.store import pg
from src.cdc.cli import sanitize
from src.mining.artifacts import sha
from .store import acquire,capture,register,verify
from .artifacts import build


def main():
    parser=argparse.ArgumentParser(description='LAK phase 9 versioned Random Forest delivery regression')
    parser.add_argument('command',choices=['preflight','train','verify'])
    parser.add_argument('--evidence-dir',type=Path,required=True)
    parser.add_argument('--label',default='result');parser.add_argument('--model-id')
    args=parser.parse_args()
    if not args.label.replace('-','').isalnum():parser.error('Invalid evidence label')
    args.evidence_dir.mkdir(parents=True,exist_ok=True);destination=args.evidence_dir/(args.label+'.json')
    if destination.exists():parser.error('Evidence already exists')
    result={'phase':9,'command':args.command,'passed':False,'checked_at_utc':datetime.now(timezone.utc).isoformat()}
    run_id=uuid.uuid4()
    try:
        with pg() as connection:
            from psycopg.types.json import Jsonb
            acquire(connection)
            connection.execute("INSERT INTO audit.pipeline_runs(run_id,pipeline,status) VALUES(%s,'phase9-delivery','RUNNING')",(run_id,))
            try:
                if args.command=='preflight':
                    from src.mining.verify import verify as verify_kmeans
                    previous=connection.execute("SELECT model_id FROM ml.model_registry WHERE algorithm='kmeans_rfm' AND status='READY' ORDER BY active DESC,created_at DESC LIMIT 1").fetchone()
                    data={'phase8_verification':verify_kmeans(connection,previous['model_id']),
                          'analytical_orders':connection.execute('SELECT count(*) AS n FROM dw.v_sales_analysis').fetchone()['n']}
                elif args.command=='train':
                    snapshot,rows,observations=capture(connection)
                    model_id,directory,metadata,report,predictions,reused=build(snapshot,rows)
                    after,_,_=capture(connection)
                    if after!=snapshot:raise RuntimeError('Delivery cohort changed during training; retry after writers finish')
                    with connection.transaction():
                        register(connection,model_id,snapshot,directory,metadata,report,predictions)
                        data=verify(connection,model_id)
                    data.update(artifact_reused=reused,source_snapshot_unchanged=True,observations=observations)
                else:
                    if not args.model_id:raise ValueError('--model-id required')
                    data=verify(connection,args.model_id)
                result.update(passed=True,result=data)
                connection.execute("UPDATE audit.pipeline_runs SET status='SUCCESS',finished_at=now(),details=%s WHERE run_id=%s",(Jsonb({'command':args.command,'model_id':data.get('model_id')}),run_id))
            except Exception as exc:
                connection.execute("UPDATE audit.pipeline_runs SET status='FAILED',finished_at=now(),details=%s WHERE run_id=%s",(Jsonb({'error_type':type(exc).__name__}),run_id));raise
    except Exception as exc:
        result.update(error_type=type(exc).__name__,safe_message=sanitize(str(exc))[:2400]);print(sanitize(traceback.format_exc(limit=8)),file=sys.stderr)
    text=json.dumps(result,ensure_ascii=False,indent=2,default=str)+'\n';destination.write_text(text,encoding='utf-8')
    print(text);print('Evidence: '+str(destination))
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
