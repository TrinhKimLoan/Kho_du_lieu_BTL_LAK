from __future__ import annotations

import argparse
import json
import re
from datetime import datetime,timezone
from pathlib import Path
import uuid

from .data import ROOT,canonical,prepare
from .runtime import connect,install,load_history,reconcile
from .demo import action,cycle,constraint_checks


def main():
    parser=argparse.ArgumentParser(description='LAK phase 3 sanitized MySQL source')
    parser.add_argument('command',choices=['install','load-history','check','constraints','demo-cycle','demo'])
    parser.add_argument('--action',choices=['insert','update','delete','status'],default='status')
    parser.add_argument('--evidence-dir',type=Path)
    parser.add_argument('--label',default='result')
    args=parser.parse_args()
    if not re.fullmatch(r'[a-z0-9_-]+',args.label):
        parser.error('Invalid evidence label')
    folder=args.evidence_dir or ROOT/'evidence/phase3'/('run-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6])
    folder.mkdir(parents=True,exist_ok=True)
    destination=folder/(args.label+'.json')
    if destination.exists():
        parser.error('Evidence file already exists; use a new label or run directory')
    report={'phase':3,'command':args.command,'passed':False,'checked_at_utc':datetime.now(timezone.utc).isoformat()}
    connection=None
    try:
        connection=connect()
        if args.command=='install':
            report['result']=install(connection)
        elif args.command=='demo':
            report['result']=action(connection,args.action)
        elif args.command=='constraints':
            report['result']=constraint_checks(connection)
        else:
            dataset=prepare()
            if args.command=='load-history':
                report['result']=load_history(connection,dataset)
            elif args.command=='check':
                report['result']=reconcile(connection,dataset)
            else:
                report['result']=cycle(connection,dataset)
        report['passed']=True
    except Exception as exc:
        report['error_type']=type(exc).__name__
        if isinstance(exc,(ValueError,RuntimeError)):
            report['safe_message']=str(exc)
        elif getattr(exc,'args',None) and isinstance(exc.args[0],int):
            report['driver_errno']=exc.args[0]
        print('SOURCE CHECK FAILED: '+report['error_type'])
    finally:
        if connection is not None:
            connection.close()
        destination.write_text(json.dumps(canonical(report),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(canonical(report),ensure_ascii=False,indent=2))
    print('Evidence: '+str(destination))
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
