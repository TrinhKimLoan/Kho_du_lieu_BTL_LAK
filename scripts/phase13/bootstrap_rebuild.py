"""Bootstrap CDC and verify fresh inference/web changes in the restored copy only."""
import argparse,json,re,shutil,subprocess,sys,time,tempfile,uuid
from datetime import datetime,timezone
from pathlib import Path
from restore_candidate import FILES,checked


def prepare_evidence_folder(folder,project):
    if folder.exists():
        report_path=folder/'bootstrap.json'
        if not report_path.is_file():raise RuntimeError('Existing bootstrap evidence requires review')
        old=json.loads(report_path.read_text(encoding='utf-8'))
        allowed={'bootstrap.json','bootstrap.log','runtime.py'}
        if (old.get('project')!=project or old.get('passed') is not False
            or old.get('error_type')!='UnsupportedOperation' or old.get('safe_message')!='fileno'
            or any(p.name not in allowed or not p.is_file() for p in folder.iterdir())):
            raise RuntimeError('Existing bootstrap evidence is not the pre-SQL fileno failure; send evidence before rerunning')
        archive=folder.with_name('cdc-failed-fileno-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6])
        folder.rename(archive)
        print('Previous failure evidence preserved: '+str(archive),flush=True)
    folder.mkdir(parents=True)


def send_sql(command,log,sql):
    # subprocess requires an actual OS file descriptor for stdin.
    with tempfile.TemporaryFile(mode='w+b') as stream:
        stream.write(sql.encode('utf-8'));stream.seek(0)
        checked(command,log,stream)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--rebuild',type=Path,required=True);a=p.parse_args();root=a.rebuild.resolve()
    original=Path(__file__).resolve().parents[2]
    if root==original or root.is_relative_to(original):raise RuntimeError('Rebuild must be outside original project')
    restored=json.loads((root/'evidence/phase13/restore/restore.json').read_text(encoding='utf-8'))
    project=restored['project']
    if not restored['passed'] or not re.fullmatch(r'lak-rebuild-[a-f0-9]{10}',project) or Path(restored['directory']).resolve()!=root:raise RuntimeError('Restore evidence/project guard failed')
    for service in ['mysql','postgres']:
        data=json.loads(subprocess.check_output(['docker','inspect',project+'-'+service+'-1']))[0]
        labels=data['Config']['Labels']
        if labels.get('com.docker.compose.project')!=project or labels.get('com.docker.compose.service')!=service or not data['State']['Running']:raise RuntimeError('Rebuild database ownership/state differs')
        if not all(x.get('Name','').startswith(project+'_') for x in data['Mounts'] if x['Type']=='volume'):raise RuntimeError('Unexpected shared database volume')
    folder=root/'evidence/phase13/cdc'
    prepare_evidence_folder(folder,project)
    log=folder/'bootstrap.log';inside='/opt/project/evidence/phase13/cdc'
    shutil.copy2(Path(__file__).with_name('rebuild_cdc_runtime.py'),folder/'runtime.py')
    command=['docker','compose','--project-name',project,'--env-file',str(root/'.runtime/lak.env')]
    for name in FILES:command+=['-f',str(root/'infra'/name)]
    command+=['--profile','ml-inference','--profile','dashboard','--profile','news-scheduler']
    result={'phase':13,'stage':'isolated-cdc-ml-web','passed':False,'phase13_complete':False,'project':project,'directory':str(root),'original_stack_stopped':False,'started_at_utc':datetime.now(timezone.utc).isoformat()}
    def run(parts):checked(command+parts,log)
    def tool(service,tail,label=None):
        run(['run','--rm','-T','--no-deps','--pull','never','-e','PYTHONPATH=/opt/project','-e','LAK_REBUILD_PROJECT='+project,'--entrypoint','python',service,*tail])
        if label and not json.loads((folder/label).read_text(encoding='utf-8'))['passed']:raise RuntimeError('Check failed: '+label)
    def runtime(action):tool('cdc-tools',[inside+'/runtime.py',action,'--folder',inside])
    def cli(service,module,action,label,extra=None):
        tool(service,['-m',module,action,'--evidence-dir',inside,'--label',label,*(extra or [])],label+'.json')
    try:
        print('Starting fresh Kafka/Connect in isolated project...',flush=True)
        run(['up','-d','--no-build','--pull','never','--wait','--wait-timeout','240','kafka','connect'])
        values=dict(line.split('=',1) for line in (root/'.runtime/lak.env').read_text().splitlines() if '=' in line)
        password=values['LAK_CDC_PASSWORD']
        if not re.fullmatch('[a-f0-9]{48}',password):raise RuntimeError('Expected separately generated hexadecimal CDC credential')
        sql="CREATE USER 'lak_cdc'@'%' IDENTIFIED BY '"+password+"'; GRANT SELECT ON lak_source.* TO 'lak_cdc'@'%'; GRANT RELOAD, SHOW DATABASES, REPLICATION SLAVE, REPLICATION CLIENT, LOCK TABLES ON *.* TO 'lak_cdc'@'%';"
        send_sql(command+['exec','-T','mysql','sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot'],log,sql)
        print('Preparing a separate CDC epoch; preserving restored business facts...',flush=True)
        runtime('prepare')
        # Connect REST may need extra startup time even after the container starts.
        probe='import time; from src.cdc.admin import http\nfor n in range(90):\n try: http("/connectors"); break\n except Exception:\n  if n==89: raise\n  time.sleep(2)\n'
        tool('cdc-tools',['-c',probe])
        runtime('register')
        run(['up','-d','--no-build','--pull','never','collector','applier'])
        cli('cdc-tools','src.cdc.cli','snapshot','new-epoch-reconciliation')
        cli('cdc-tools','src.cdc.cli','demo','new-cdc-demo')
        cli('inference-tools','src.inference.cli','init','ml-init')
        cli('inference-tools','src.inference.cli','seed','ml-seed')
        run(['up','-d','--no-build','--pull','never','--wait','--wait-timeout','240','inference-worker'])
        try:
            cli('inference-tools','src.inference.cli','finish','ml-finish',['--seed-file',inside+'/ml-seed.json'])
        finally:
            cli('inference-tools','src.inference.cli','cleanup','ml-cleanup',['--seed-file',inside+'/ml-seed.json'])
        cli('mart-tools','src.marts.cli','refresh','mart-refreshed')
        runtime('verify')
        tool('dashboard-tools',['-m','src.dashboard.checks','--evidence-dir',inside],'dashboard-checks.json')
        run(['up','-d','--no-build','--pull','never','--wait','--wait-timeout','240','dashboard'])
        run(['up','-d','--no-build','--pull','never','news-airflow'])
        print('Waiting for the isolated Airflow scheduler...',flush=True)
        for attempt in range(60):
            try:
                run(['exec','-T','news-airflow','airflow','jobs','check','--job-type','SchedulerJob','--local'])
                break
            except RuntimeError:
                if attempt==59:raise
                time.sleep(3)
        run(['exec','-T','news-airflow','airflow','dags','unpause','lak_mart_refresh_phase7'])
        run(['ps','-a'])
        result.update(passed=True,cdc_bootstrap_verified=True,fresh_source_to_ml_insert_update_delete_verified=True,dashboard_pages_verified=8,website='http://localhost:18501')
    except (Exception,KeyboardInterrupt) as exc:
        result.update(error_type=type(exc).__name__,safe_message=str(exc))
    finally:
        result['finished_at_utc']=datetime.now(timezone.utc).isoformat()
        (folder/'bootstrap.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result,indent=2));print('Evidence: '+str(folder))
    if not result['passed']:raise RuntimeError('Rebuild CDC verification incomplete; send bootstrap log/evidence; do not reset volumes')
    print('PHASE 13 ISOLATED CDC ML AND WEB CHECKS PASSED')


if __name__=='__main__':
    try:main()
    except (RuntimeError,OSError,ValueError,subprocess.CalledProcessError) as exc:
        print('BOOTSTRAP STOPPED: '+str(exc),file=sys.stderr);raise SystemExit(1)
