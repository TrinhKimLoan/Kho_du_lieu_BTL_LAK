import uuid
from src.source.data import ROOT,prepare,canonical
from src.source.runtime import connect,reconcile
from src.cdc.store import pg,epoch
from src.cdc.checks import wait_idle,history
from .rules import RULES,summarize


def migrate(connection):
    if not connection.execute("SELECT 1 FROM audit.schema_versions WHERE version='lak-phase2-v1'").fetchone():
        raise RuntimeError('Phase 2 warehouse is required')
    with connection.transaction():
        connection.execute((ROOT/'sql/phase5/001_quality_history.sql').read_text(),prepare=False)
    constraints=connection.execute("SELECT contype FROM pg_constraint WHERE conrelid='dw.dim_product'::regclass").fetchall()
    if not any(r['contype']=='x' for r in constraints):raise RuntimeError('SCD2 overlap exclusion constraint is missing')


def check():
    from psycopg.types.json import Jsonb
    dataset=prepare();run_id=uuid.uuid4()
    with pg() as target:
        migrate(target)
        target.execute("INSERT INTO audit.pipeline_runs(run_id,pipeline,status) VALUES(%s,'phase5-quality','RUNNING')",(run_id,))
        counts={};reconciliation={};failure=None
        try:
            wait_idle(target,epoch(target))
            with target.transaction():
                target.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
                for rule in RULES:
                    found=target.execute(rule.sql).fetchall();counts[rule.code]=len(found)
                    if found:
                        target.cursor().executemany('''INSERT INTO audit.quality_findings(run_id,entity_type,entity_key,rule_code,severity,details)
                            VALUES(%s,%s,%s,%s,%s,%s)''',[(run_id,rule.entity,str(r['entity_key']),rule.code,rule.severity,Jsonb({'scope':'current warehouse snapshot'})) for r in found])
                reconciliation['warehouse']=history(target,dataset)
            with connect() as source:
                reconciliation['source']=reconcile(source,dataset)
        except Exception as exc:
            failure=type(exc).__name__+': '+str(exc)[:1500]
            target.execute("INSERT INTO audit.quality_findings(run_id,entity_type,entity_key,rule_code,severity,details) VALUES(%s,'pipeline','phase5','RECONCILIATION_OR_CHECK_FAILED','ERROR',%s)",(run_id,Jsonb({'message':failure})))
        summary=summarize(counts)
        if failure:summary['error_findings']+=1;summary['passed']=False
        result=dict(summary,run_id=str(run_id),rule_counts=counts,reconciliation=reconciliation,
                    warning_policy='Retain anomalous sales; do not silently repair source timestamps.',failure=failure)
        target.execute("UPDATE audit.pipeline_runs SET status=%s,finished_at=now(),details=%s WHERE run_id=%s",('SUCCESS' if summary['passed'] else 'FAILED',Jsonb(canonical(result)),run_id))
        return result
