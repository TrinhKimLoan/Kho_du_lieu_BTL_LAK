"""Run only inside a checked isolated rebuild tools container."""
import argparse,json,os,uuid
from pathlib import Path
from src.source.runtime import connect,identity,reconcile
from src.source.data import fingerprint,prepare
from src.cdc.store import pg
from src.cdc.checks import history
from src.cdc.admin import ensure_topics,http,config,CONNECTOR

p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','register','verify']);p.add_argument('--folder',type=Path,required=True);a=p.parse_args()
project=os.environ.get('LAK_REBUILD_PROJECT','')
if not project.startswith('lak-rebuild-'):raise SystemExit('Isolated project guard missing')
plan_path=a.folder/'epoch-plan.json'
with pg() as target,connect() as source:
    if a.action=='prepare':
        if plan_path.exists():raise RuntimeError('Epoch plan exists; send evidence before rerunning bootstrap')
        old=str(identity(source)['source_epoch']);wh=str(target.execute('SELECT source_epoch FROM audit.pipeline_identity WHERE singleton').fetchone()['source_epoch'])
        if old!=wh:raise RuntimeError('Source and warehouse epoch do not agree before bootstrap')
        dataset=prepare();reconcile(source,dataset)
        baseline=history(target,dataset)
        registry=fingerprint(target.execute('SELECT model_id,manifest_sha256,created_at FROM ml.model_registry ORDER BY model_id').fetchall())
        new=str(uuid.uuid4());plan={'project':project,'old_epoch':old,'new_epoch':new,'baseline':baseline,'registry_sha256':registry,'prepared':False}
        plan_path.write_text(json.dumps(plan,indent=2)+'\n',encoding='utf-8')
        with source.cursor() as cur:cur.execute('UPDATE source_identity SET source_epoch=%s WHERE singleton_id=1',(new,))
        source.commit()
        with target.transaction():
            target.execute('UPDATE audit.pipeline_identity SET source_epoch=%s WHERE singleton',(new,))
            for table in ['customers','products','orders']:
                target.execute('UPDATE staging.'+table+' SET source_epoch=%s,source_file_number=0,source_position=0,source_row_number=0,tx_total_order=0',(new,))
            target.execute('DELETE FROM audit.worker_heartbeats')
        after=history(target,prepare())
        if after['fact_state_sha256']!=baseline['fact_state_sha256']:raise RuntimeError('Historical fact state changed during epoch preparation')
        plan['prepared']=True;plan_path.write_text(json.dumps(plan,indent=2)+'\n',encoding='utf-8')
        print('ISOLATED CDC EPOCH PREPARED; restored business facts preserved')
    else:
        plan=json.loads(plan_path.read_text(encoding='utf-8'))
        if not plan['prepared'] or plan['project']!=project:raise RuntimeError('Invalid preparation plan')
        if str(identity(source)['source_epoch'])!=plan['new_epoch'] or str(target.execute('SELECT source_epoch FROM audit.pipeline_identity WHERE singleton').fetchone()['source_epoch'])!=plan['new_epoch']:raise RuntimeError('Rebuild epoch mismatch')
        if a.action=='register':
            ensure_topics();desired=config();desired['snapshot.mode']='no_data'
            if http('/connectors'):raise RuntimeError('Expected fresh Connect without connectors')
            http('/connectors','POST',{'name':CONNECTOR,'config':desired})
            print('NEW CONNECTOR REGISTERED: no_data bootstrap after validated logical restore')
        else:
            after=history(target,prepare())
            registry=fingerprint(target.execute('SELECT model_id,manifest_sha256,created_at FROM ml.model_registry ORDER BY model_id').fetchall())
            if after['fact_state_sha256']!=plan['baseline']['fact_state_sha256'] or registry!=plan['registry_sha256']:raise RuntimeError('Historical facts or model registry changed')
            status=http('/connectors/'+CONNECTOR+'/status')
            if status['connector']['state']!='RUNNING' or not status['tasks'] or any(x['state']!='RUNNING' for x in status['tasks']):raise RuntimeError('Connector/task not RUNNING')
            checkpoints=target.execute('SELECT count(*) n FROM raw.kafka_checkpoints WHERE source_epoch=%s',(plan['new_epoch'],)).fetchone()['n']
            if not checkpoints:raise RuntimeError('New epoch has no durable Kafka checkpoints')
            result={'passed':True,'project':project,'new_epoch':plan['new_epoch'],'historical_facts_unchanged':True,'model_registry_unchanged':True,'new_epoch_checkpoint_rows':checkpoints,'connector_running':True,'snapshot_mode':'no_data','bootstrap_basis':'explicitly restored and reconciled source/DW; fresh binlog position and Kafka offsets; old ledger preserved under old epoch'}
            (a.folder/'cdc-verified.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,indent=2))
