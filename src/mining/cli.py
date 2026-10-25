import argparse
import json
import sys
import traceback
import uuid
from datetime import datetime,timezone
from pathlib import Path
from src.cdc.store import pg
from src.cdc.cli import sanitize
from .store import acquire,migrate,capture,register
from .artifacts import build,sha
from .verify import verify


def main():
    parser=argparse.ArgumentParser(description='LAK phase 8 versioned RFM/KMeans training')
    parser.add_argument('command',choices=['train','verify'])
    parser.add_argument('--evidence-dir',type=Path,required=True)
    parser.add_argument('--label',default='result')
    parser.add_argument('--model-id')
    args=parser.parse_args()
    if not args.label.replace('-','').isalnum():parser.error('Invalid evidence label')
    args.evidence_dir.mkdir(parents=True,exist_ok=True);destination=args.evidence_dir/(args.label+'.json')
    if destination.exists():parser.error('Evidence already exists')
    result={'phase':8,'command':args.command,'passed':False,'checked_at_utc':datetime.now(timezone.utc).isoformat()}
    run_id=uuid.uuid4()
    try:
        with pg() as connection:
            from psycopg.types.json import Jsonb
            acquire(connection);migrate(connection)
            connection.execute("INSERT INTO audit.pipeline_runs(run_id,pipeline,status) VALUES(%s,'phase8-kmeans','RUNNING')",(run_id,))
            try:
                if args.command=='train':
                    snapshot,rows,captured=capture(connection)
                    model_id,directory,metadata,report,profiles,assignments,reused=build(snapshot,rows)
                    after,_,_=capture(connection)
                    if after!=snapshot:raise RuntimeError('RFM source cohort changed during training; rerun after source writers finish')
                    with connection.transaction():
                        register(connection,model_id,snapshot,'kmeans_rfm/'+model_id,sha(directory/'manifest.json'),dict(metadata,evaluation=report),rows,profiles,assignments)
                        data=verify(connection,model_id)
                    data.update(artifact_reused=reused,source_snapshot_unchanged=True)
                else:
                    if not args.model_id:raise ValueError('--model-id is required')
                    data=verify(connection,args.model_id)
                result.update(passed=True,result=data)
                connection.execute("UPDATE audit.pipeline_runs SET status='SUCCESS',finished_at=now(),details=%s WHERE run_id=%s",(Jsonb({'model_id':data['model_id'],'snapshot_id':data['snapshot_id']}),run_id))
            except Exception as exc:
                connection.execute("UPDATE audit.pipeline_runs SET status='FAILED',finished_at=now(),details=%s WHERE run_id=%s",(Jsonb({'error_type':type(exc).__name__}),run_id));raise
    except Exception as exc:
        result.update(error_type=type(exc).__name__,safe_message=sanitize(str(exc))[:2400])
        print(sanitize(traceback.format_exc(limit=8)),file=sys.stderr)
    text=json.dumps(result,ensure_ascii=False,indent=2,default=str)+'\n';destination.write_text(text,encoding='utf-8')
    print(text);print('Evidence: '+str(destination))
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
