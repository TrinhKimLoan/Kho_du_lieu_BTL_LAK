"""Operate a recorded isolated rebuild without using the original project name."""
import argparse,json,re,subprocess,sys
from pathlib import Path
from restore_candidate import FILES
from release import check_images


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['status','start','stop','logs']);p.add_argument('--rebuild',type=Path,required=True);a=p.parse_args();root=a.rebuild.resolve()
    metadata=json.loads((root/'evidence/phase13/restore/restore.json').read_text(encoding='utf-8'));project=metadata['project']
    if not metadata['passed'] or not re.fullmatch('lak-rebuild-[a-f0-9]{10}',project) or Path(metadata['directory']).resolve()!=root:raise RuntimeError('Isolated project guard failed')
    command=['docker','compose','--project-name',project,'--env-file',str(root/'.runtime/lak.env')]
    for name in FILES:command+=['-f',str(root/'infra'/name)]
    command+=['--profile','news-scheduler','--profile','ml-inference','--profile','dashboard']
    services=['mysql','postgres','kafka','connect','collector','applier','inference-worker','news-airflow','dashboard']
    if a.action=='start':
        bootstrap=json.loads((root/'evidence/phase13/cdc/bootstrap.json').read_text(encoding='utf-8'))
        if not bootstrap['passed']:raise RuntimeError('CDC bootstrap must pass before operational start')
        check_images(root);command+=['up','-d','--no-build','--pull','never','--wait','--wait-timeout','240',*services]
    elif a.action=='stop':command+=['stop',*reversed(services)]
    elif a.action=='status':command+=['ps','-a']
    else:command+=['logs','--tail','100',*services]
    subprocess.run(command,check=True)


if __name__=='__main__':
    try:main()
    except (RuntimeError,OSError,ValueError,subprocess.CalledProcessError) as exc:
        print('REBUILD OPERATION STOPPED: '+str(exc),file=sys.stderr);raise SystemExit(1)
