import argparse
import json
import sys
import traceback
from pathlib import Path
from datetime import datetime,date,timezone
from src.cdc.store import pg
from src.cdc.cli import sanitize


def main():
    parser=argparse.ArgumentParser(description='LAK Phase 10 frozen-model inference')
    parser.add_argument('command',choices=['init','worker','status','seed','finish','cleanup','advance-reference','retry-failed'])
    parser.add_argument('--evidence-dir',type=Path);parser.add_argument('--label',default='result');parser.add_argument('--seed-file',type=Path)
    parser.add_argument('--date',type=date.fromisoformat);parser.add_argument('--reason');parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    if args.command=='worker':
        from .worker import run
        run(args.once);return 0
    if not args.evidence_dir or not args.label.replace('-','').isalnum():parser.error('Evidence directory and valid label required')
    args.evidence_dir.mkdir(parents=True,exist_ok=True);path=args.evidence_dir/(args.label+'.json')
    if path.exists():parser.error('Evidence already exists')
    result={'phase':10,'command':args.command,'passed':False,'checked_at_utc':datetime.now(timezone.utc).isoformat()}
    try:
        with pg() as connection:
            from . import checks,store
            if args.command=='init':data=store.initialize(connection)
            elif args.command=='status':data=checks.status(connection,True)
            elif args.command=='seed':data=checks.seed(connection)
            elif args.command in ['finish','cleanup']:
                if not args.seed_file:raise ValueError('--seed-file required')
                seed=json.loads(args.seed_file.read_text(encoding='utf-8'))
                if not seed['passed']:raise ValueError('Seed did not pass')
                data=getattr(checks,args.command)(connection,seed['result'])
            elif args.command=='advance-reference':
                if not args.date or not args.reason:raise ValueError('--date and --reason required')
                data=store.advance(connection,args.date,args.reason)
            else:
                changed=connection.execute("UPDATE ml.inference_jobs SET state='PENDING',attempts=0,available_at=now(),safe_error=NULL WHERE state='FAILED' RETURNING job_id").fetchall()
                data={'retried_jobs':len(changed),'models_retrained':False}
            result.update(passed=True,result=data)
    except Exception as exc:
        result.update(error_type=type(exc).__name__,safe_message=sanitize(str(exc))[:2400]);print(sanitize(traceback.format_exc(limit=8)),file=sys.stderr)
    text=json.dumps(result,ensure_ascii=False,indent=2,default=str)+'\n';path.write_text(text,encoding='utf-8');print(text);print('Evidence: '+str(path))
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
