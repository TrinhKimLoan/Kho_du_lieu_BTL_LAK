import argparse
import json
import os
import sys
import traceback
import uuid
from datetime import datetime,timezone
from pathlib import Path


def sanitize(text):
    for name,value in os.environ.items():
        if ('PASSWORD' in name or 'SECRET' in name) and len(value)>=4:text=text.replace(value,'[REDACTED]')
    return text


def main():
    parser=argparse.ArgumentParser(description='LAK phase 4 CDC runtime and evidence')
    parser.add_argument('command',choices=['init','capture','apply','snapshot','demo','replay','recovery-seed','recovery-finish'])
    parser.add_argument('--evidence-dir',type=Path)
    parser.add_argument('--label',default='result')
    parser.add_argument('--seed-file',type=Path)
    args=parser.parse_args()
    if args.command=='capture':
        from .store import capture
        capture();return 0
    if args.command=='apply':
        from .project import run
        run();return 0
    if not args.label.replace('-','').replace('_','').isalnum():parser.error('Invalid evidence label')
    folder=args.evidence_dir or Path('/opt/project/evidence/phase4')/('run-'+uuid.uuid4().hex[:10])
    folder.mkdir(parents=True,exist_ok=True);destination=folder/(args.label+'.json')
    if destination.exists():parser.error('Evidence label already exists')
    result={'phase':4,'command':args.command,'passed':False,'checked_at_utc':datetime.now(timezone.utc).isoformat()}
    try:
        if args.command=='init':
            from .admin import init
            data=init()
        else:
            from . import checks
            if args.command=='recovery-finish':
                if args.seed_file is None:raise ValueError('Recovery seed file is required')
                data=checks.recovery_finish(args.seed_file)
            else:data=getattr(checks,args.command.replace('-','_'))()
        result.update(passed=True,result=data)
    except Exception as exc:
        result.update(error_type=type(exc).__name__,safe_message=sanitize(str(exc))[:2400])
        print(sanitize(traceback.format_exc(limit=8)),file=sys.stderr)
    destination.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2,default=str))
    print('Evidence: '+str(destination))
    return 0 if result['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
