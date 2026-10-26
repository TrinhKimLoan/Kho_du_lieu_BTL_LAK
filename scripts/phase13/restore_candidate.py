"""Restore explicit candidate/data/images into a new isolated project; CDC stays off."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import uuid
import zipfile
from release import verify_package,check_images

FILES=['compose.lak.yaml','compose.news.yaml','compose.mart.yaml','compose.ml.yaml','compose.delivery.yaml','compose.inference.yaml','compose.dashboard.yaml','compose.release-lock.yaml']


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()


def checked(args,log,stdin=None):
    with log.open('ab') as f:
        result=subprocess.run(args,stdin=stdin,stdout=f,stderr=f)
    if result.returncode:raise RuntimeError('Command failed with code '+str(result.returncode)+'; see '+str(log))


def validate_inputs(args):
    for path,want in [(args.candidate,args.candidate_sha256),(args.images,args.images_sha256)]:
        if digest(path)!=want.lower():raise RuntimeError('Input checksum differs: '+path.name)
    verify_package(args.candidate)
    data=json.loads((args.data/'export.json').read_text(encoding='utf-8-sig'))
    if not data['passed'] or not data['services_resumed']:raise RuntimeError('Data export was incomplete')
    if {x['name'] for x in data['files']}!={'mysql-source.sql','warehouse.dump','warehouse-toc.txt'}:raise RuntimeError('Unexpected dump inventory')
    for item in data['files']:
        path=args.data/item['name']
        if path.stat().st_size!=item['bytes'] or digest(path)!=item['sha256']:raise RuntimeError('Dump checksum differs: '+item['name'])
    return data


def restore(args):
    print('Verifying candidate, image archive and database dump checksums...',flush=True)
    data=validate_inputs(args)
    suffix=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]
    root=args.output/('LAK-Rebuild-'+suffix)
    if args.output.resolve().is_relative_to(Path(__file__).resolve().parents[2]):raise RuntimeError('Use output outside original project')
    root.mkdir(parents=True,exist_ok=False)
    project='lak-rebuild-'+uuid.uuid4().hex[:10]
    evidence=root/'evidence/phase13/restore';evidence.mkdir(parents=True)
    log=evidence/'restore.log'
    report={'phase':13,'stage':'isolated-database-model-restore','passed':False,'phase13_complete':False,
            'project':project,'directory':str(root),'original_project_modified':False,
            'cdc_bootstrap_verified':False,'runtime_scope':'two new database volumes; source, mart, model and 8-page AppTest checks; CDC/workers/scheduler/dashboard server not started',
            'image_archive_sha256':args.images_sha256,'candidate_sha256':args.candidate_sha256,
            'data_export':data,'started_at_utc':datetime.now(timezone.utc).isoformat()}
    try:
        # Archive member safety and hashes were validated before creating any Docker resource.
        with zipfile.ZipFile(args.candidate) as archive:
            for name in archive.namelist():
                dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True)
                with archive.open(name) as src,dest.open('xb') as target:shutil.copyfileobj(src,target)
        runtime=root/'.runtime';runtime.mkdir()
        values={key:secrets.token_hex(24) for key in ['LAK_MYSQL_ROOT_PASSWORD','LAK_MYSQL_APP_PASSWORD','LAK_POSTGRES_PASSWORD','LAK_CDC_PASSWORD']}
        (runtime/'lak.env').write_text(''.join(k+'='+v+'\n' for k,v in values.items()),encoding='utf-8')
        (runtime/'news.env').write_text('MEDIACLOUD_API_KEY=\n',encoding='utf-8')
        # Modify only extracted compose files, with project-prefixed default volumes/networks.
        changes={'127.0.0.1:3310:3306':'127.0.0.1:13310:3306','127.0.0.1:5435:5432':'127.0.0.1:15435:5432',
                 '127.0.0.1:8085:8083':'127.0.0.1:18085:8083','127.0.0.1:8501:8501':'127.0.0.1:18501:8501'}
        for name in FILES:
            path=root/'infra'/name;text=path.read_text(encoding='utf-8')
            for old,new in changes.items():text=text.replace(old,new)
            path.write_text(text,encoding='utf-8')
        print('Loading explicitly exported Docker images...',flush=True)
        checked(['docker','image','load','--input',str(args.images)],log)
        check_images(root)
        command=['docker','compose','--project-name',project,'--env-file',str(runtime/'lak.env')]
        for name in FILES:command+=['-f',str(root/'infra'/name)]
        checked(command+['config','--quiet'],log)
        # Pre-existing resources with this generated project are forbidden.
        ids=subprocess.check_output(['docker','ps','-aq','--filter','label=com.docker.compose.project='+project],text=True).strip()
        volumes=subprocess.check_output(['docker','volume','ls','-q','--filter','label=com.docker.compose.project='+project],text=True).strip()
        if ids or volumes:raise RuntimeError('Isolated project unexpectedly already exists')
        print('Starting two isolated databases...',flush=True)
        checked(command+['up','-d','--no-build','--pull','never','--wait','--wait-timeout','240','mysql','postgres'],log)
        print('Restoring MySQL and PostgreSQL...',flush=True)
        with (args.data/'mysql-source.sql').open('rb') as stream:
            checked(command+['exec','-T','mysql','sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot'],log,stream)
        with (args.data/'warehouse.dump').open('rb') as stream:
            checked(command+['exec','-T','postgres','pg_restore','-U','lak_dw','-d','lak_warehouse','--no-owner','--no-acl','--exit-on-error'],log,stream)
        inside='/opt/project/evidence/phase13/restore'
        checks=[('source-tools',['--entrypoint','python'],['-m','src.source.cli','check','--evidence-dir',inside,'--label','source-restored'],'source-restored.json'),
                ('mart-tools',[],['verify','--evidence-dir',inside,'--label','mart-restored'],'mart-restored.json'),
                ('inference-tools',['--entrypoint','python'],['-m','src.mining.cli','verify','--model-id','km-rfm-6ea5a87000cce054c9fa28c9','--evidence-dir',inside,'--label','kmeans-restored'],'kmeans-restored.json'),
                ('inference-tools',['--entrypoint','python'],['-m','src.delivery.cli','verify','--model-id','rf-delivery-4a60b2b333abc46ef35bb5f6','--evidence-dir',inside,'--label','rf-restored'],'rf-restored.json'),
                ('dashboard-tools',[],['--evidence-dir',inside],'dashboard-checks.json')]
        for service,options,tail,filename in checks:
            print('Verifying restored data: '+filename,flush=True)
            checked(command+['run','--rm','-T','--no-deps','--pull','never',*options,service,*tail],log)
            result=json.loads((evidence/filename).read_text(encoding='utf-8'))
            if not result['passed']:raise RuntimeError('Restored verification failed: '+filename)
        report['passed']=True
    except (Exception,KeyboardInterrupt) as exc:
        report['error_type']=type(exc).__name__;report['safe_message']=str(exc)
    finally:
        report['finished_at_utc']=datetime.now(timezone.utc).isoformat()
        (evidence/'restore.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k!='data_export'},indent=2));print('Evidence: '+str(evidence))
    if not report['passed']:raise RuntimeError('Isolated restore incomplete; original stack was not stopped. Keep evidence for diagnosis.')
    print('PHASE 13 ISOLATED DATA AND MODEL RESTORE PASSED')
    print('CDC bootstrap remains pending; do not run demo mutations in this restored copy yet.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['candidate','images','data','output']:p.add_argument('--'+name,type=Path,required=True)
    for name in ['candidate-sha256','images-sha256']:p.add_argument('--'+name,required=True)
    args=p.parse_args()
    try:restore(args)
    except (RuntimeError,OSError,ValueError,subprocess.CalledProcessError) as exc:
        print('RESTORE STOPPED: '+str(exc),file=sys.stderr);raise SystemExit(1)
