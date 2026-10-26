"""Export logical LAK databases and resume previously running application services."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid

PROJECT='lak-analytics'
WORKERS=['dashboard','news-airflow','collector','applier','inference-worker']


def container(service):return PROJECT+'-'+service+'-1'


def call(args,**kwargs):
    result=subprocess.run(['docker',*args],stderr=subprocess.PIPE,**kwargs)
    if result.returncode:
        # Keep database stderr private; do not print potential row data/credentials.
        raise RuntimeError('Docker failed ('+str(result.returncode)+'): '+args[0])
    return result


def inspect(service):
    result=call(['inspect',container(service)],stdout=subprocess.PIPE)
    data=json.loads(result.stdout)[0]
    labels=data['Config'].get('Labels',{})
    if labels.get('com.docker.compose.project')!=PROJECT or labels.get('com.docker.compose.service')!=service:
        raise RuntimeError('Unexpected container ownership: '+service)
    return data['State']['Running']


def dump(service,command,path):
    with path.open('xb') as stream:
        call(['exec',container(service),*command],stdout=stream)
    if path.stat().st_size<100:
        raise RuntimeError('Dump appears empty: '+path.name)


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(4*1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def export(output):
    if not inspect('mysql') or not inspect('postgres'):
        raise RuntimeError('Both database containers must be running')
    running=[s for s in WORKERS if inspect(s)]
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]
    folder=output/('Data-Snapshot-'+stamp);folder.mkdir(parents=True,exist_ok=False)
    report={'phase':13,'stage':'logical-data-export','passed':False,'restore_verified':False,
            'started_at_utc':datetime.now(timezone.utc).isoformat(),'previously_running':running,
            'snapshot_method':'Application services stopped; separate consistent logical database dumps. Not an atomic distributed snapshot. Do not write to source through other clients during export.',
            'kafka_connect_state_included':False,'database_user_credentials_included':False,
            'airflow_state_included':False,'files':[],'restart_errors':[]}
    attempted=[];failure=None
    try:
        for service in running:
            attempted.append(service)
            print('Stopping temporarily: '+service,flush=True)
            call(['stop','--time','45',container(service)],stdout=subprocess.PIPE)
        print('Exporting MySQL source...',flush=True)
        source=folder/'mysql-source.sql.partial'
        dump('mysql',['sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -uroot --single-transaction --skip-lock-tables --no-tablespaces --set-gtid-purged=OFF --hex-blob --databases lak_source'],source)
        source.rename(folder/'mysql-source.sql')
        print('Exporting PostgreSQL warehouse (including stored news and ML tables)...',flush=True)
        warehouse=folder/'warehouse.dump.partial'
        dump('postgres',['pg_dump','-U','lak_dw','-d','lak_warehouse','-Fc','--no-owner','--no-acl'],warehouse)
        warehouse.rename(folder/'warehouse.dump')
        # pg_restore --list validates the archive table of contents, not an actual restore.
        print('Checking PostgreSQL archive directory...',flush=True)
        with (folder/'warehouse.dump').open('rb') as stream:
            result=call(['exec','-i',container('postgres'),'pg_restore','--list'],stdin=stream,stdout=subprocess.PIPE)
        (folder/'warehouse-toc.txt').write_bytes(result.stdout)
        for name in ['mysql-source.sql','warehouse.dump','warehouse-toc.txt']:
            path=folder/name;report['files'].append({'name':name,'bytes':path.stat().st_size,'sha256':digest(path)})
        report['export_completed']=True
    except (Exception,KeyboardInterrupt) as exc:
        failure=type(exc).__name__+': '+str(exc)
        report['error']=failure
    finally:
        # Restart every service for which stopping was attempted, even after dump failure.
        for service in reversed(attempted):
            try:
                print('Resuming: '+service,flush=True)
                call(['start',container(service)],stdout=subprocess.PIPE)
                if not inspect(service):raise RuntimeError('Container is not running')
            except Exception as exc:
                report['restart_errors'].append({'service':service,'error_type':type(exc).__name__})
        report['passed']=failure is None and not report['restart_errors']
        report['finished_at_utc']=datetime.now(timezone.utc).isoformat()
        report['services_resumed']=not report['restart_errors']
        (folder/'export.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report,indent=2));print('Evidence: '+str(folder),flush=True)
    if not report['passed']:raise RuntimeError('Export/resume incomplete; inspect export.json and service status')
    print('PHASE 13 DATA EXPORT PASSED')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:export(args.output)
    except (RuntimeError,OSError,ValueError) as exc:
        print('PHASE 13 DATA EXPORT STOPPED: '+str(exc),file=sys.stderr);raise SystemExit(1)
