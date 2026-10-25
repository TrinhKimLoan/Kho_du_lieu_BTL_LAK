import argparse
import json
import sys
import traceback
from datetime import datetime,timezone
from pathlib import Path
from src.cdc.cli import sanitize


def main():
    parser=argparse.ArgumentParser(description='LAK phase 5 warehouse quality and SCD2 checks')
    parser.add_argument('command',choices=['quality','dimensions','fixtures','retry'])
    parser.add_argument('--evidence-dir',type=Path,required=True)
    parser.add_argument('--label',required=True)
    parser.add_argument('--error-id',type=int)
    args=parser.parse_args()
    if not args.label.replace('-','').isalnum():parser.error('Invalid evidence label')
    args.evidence_dir.mkdir(parents=True,exist_ok=True)
    path=args.evidence_dir/(args.label+'.json')
    if path.exists():parser.error('Evidence file already exists')
    result={'phase':5,'command':args.command,'passed':False,'checked_at_utc':datetime.now(timezone.utc).isoformat()}
    try:
        if args.command=='retry':
            if args.error_id is None or args.error_id<1:raise ValueError('A positive --error-id is required')
            from src.cdc.store import pg
            from .retry import request_retry
            with pg() as connection:data=request_retry(connection,args.error_id)
            data['passed']=True
        else:
            if args.command=='quality':from .audit import check
            elif args.command=='dimensions':from .dimensions import check
            else:from .fixtures import check
            data=check()
        result.update(passed=data['passed'],result=data)
    except Exception as exc:
        result.update(error_type=type(exc).__name__,safe_message=sanitize(str(exc))[:2400])
        print(sanitize(traceback.format_exc(limit=8)),file=sys.stderr)
    text=json.dumps(result,ensure_ascii=False,indent=2,default=str)+'\n'
    path.write_text(text,encoding='utf-8');print(text);print('Evidence: '+str(path))
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
