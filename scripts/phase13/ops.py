"""Operate the existing LAK stack; isolated rebuild is a separate workflow."""
import argparse
from pathlib import Path
import subprocess
import sys
from release import check_images


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['status','start','stop','logs'])
    parser.add_argument('--target',type=Path,default=Path(__file__).resolve().parents[2])
    args=parser.parse_args()
    root=args.target.resolve()
    for name in ['lak.env','news.env']:
        if not (root/'.runtime'/name).is_file():
            raise RuntimeError('Existing .runtime/'+name+' is required; do not replace active credentials')
    files=['compose.lak.yaml','compose.news.yaml','compose.mart.yaml','compose.ml.yaml',
           'compose.delivery.yaml','compose.inference.yaml','compose.dashboard.yaml','compose.release-lock.yaml']
    command=['docker','compose','--project-name','lak-analytics','--env-file',str(root/'.runtime/lak.env')]
    for name in files:command+=['-f',str(root/'infra'/name)]
    command+=['--profile','news-scheduler','--profile','ml-inference','--profile','dashboard']
    services=['mysql','postgres','kafka','connect','collector','applier','news-airflow','inference-worker','dashboard']
    if args.action=='start':
        check_images(root)
        command+=['up','-d','--no-build','--pull','never','--wait','--wait-timeout','240',*services]
    elif args.action=='stop':
        command+=['stop',*reversed(services)]
    elif args.action=='status':
        command+=['ps','-a']
    else:
        command+=['logs','--tail','100',*services]
    subprocess.run(command,cwd=root,check=True)
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (RuntimeError,OSError,subprocess.CalledProcessError) as exc:
        print('LAK OPERATION STOPPED: '+str(exc),file=sys.stderr);raise SystemExit(1)
