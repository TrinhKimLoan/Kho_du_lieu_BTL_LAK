import argparse,json,time,statistics,math,uuid,random,hashlib,traceback
from pathlib import Path
from datetime import datetime,timezone
from src.cdc.store import pg
from src.cdc.cli import sanitize
from src.source.runtime import connect
from src.source.demo import action
from src.inference.checks import business,registry
from src.marts.queries import sales_query


def summary(values):
    values=sorted(values)
    if not values or any(not math.isfinite(v) or v<0 for v in values):raise ValueError('Invalid timing samples')
    def percentile(p):
        point=(len(values)-1)*p;lo=int(point);hi=min(lo+1,len(values)-1)
        return values[lo]+(values[hi]-values[lo])*(point-lo)
    return {'n':len(values),'mean_seconds':statistics.mean(values),'median_seconds':percentile(.5),'p95_seconds':percentile(.95),'max_seconds':max(values)}


def observe(c,oid,cid,operation,timeout=240):
    deadline=time.perf_counter()+timeout;dw_at=None
    while time.perf_counter()<deadline:
        f=c.execute('SELECT quantity,is_deleted FROM dw.fact_sales WHERE order_id=%s',(oid,)).fetchone()
        expected=f and (f['is_deleted'] if operation=='delete' else not f['is_deleted'] and f['quantity']==(2 if operation=='insert' else 3))
        if expected:
            if dw_at is None:dw_at=time.perf_counter()
            row=c.execute('''SELECT h.state,h.input FROM ml.rfm_current_assignments a JOIN ml.rfm_assignment_history h USING(job_id)
              JOIN dw.dim_customer cu ON cu.customer_key=a.customer_key JOIN ml.inference_config cfg ON cfg.singleton
              WHERE cu.customer_id=%s AND a.is_demo AND a.model_id=cfg.rfm_model_id AND a.reference_date=cfg.reference_date''',(cid,)).fetchone()
            p=c.execute('''SELECT p.prediction_id,o.state FROM ml.live_delivery_predictions p LEFT JOIN LATERAL
              (SELECT state FROM ml.delivery_outcome_history x WHERE x.prediction_id=p.prediction_id ORDER BY job_id DESC LIMIT 1)o ON true
              WHERE p.order_id=%s AND p.is_demo''',(oid,)).fetchone()
            rfm_ok=row and (row['state']=='NO_HISTORY' if operation=='delete' else row['state']=='ASSIGNED' and float(row['input']['monetary'])==(200000 if operation=='insert' else 300000))
            delivery_ok=p and p['state']=={'insert':'PENDING','update':'RECEIVED','delete':'DELETED'}[operation]
            if rfm_ok and delivery_ok:return dw_at,time.perf_counter()
        time.sleep(.1)
    raise RuntimeError('Timeout observing '+operation+' for '+oid)


def latency(c,folder,n):
    rows=[]
    with connect() as source:
        for i in range(n):
            suffix='MEASURE12_'+uuid.uuid4().hex[:10];oid='DEMO_'+suffix+'_O';cid='DEMO_'+suffix+'_C'
            try:
                for operation in ['insert','update','delete']:
                    start=time.perf_counter();action(source,operation,suffix);ack=time.perf_counter()
                    dw,ml=observe(c,oid,cid,operation)
                    rows.append({'sample':i+1,'operation':operation,'order_id':oid,'request_to_ack_seconds':ack-start,
                                 'request_to_dw_observed_seconds':dw-start,'request_to_ml_observed_seconds':ml-start,
                                 'ack_to_dw_observed_seconds':max(0,dw-ack),'ack_to_ml_observed_seconds':max(0,ml-ack)})
                    (folder/'latency-samples.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
                    print('Measured',i+1,operation,flush=True)
            finally:action(source,'delete',suffix)
    return {op:{field:summary([r[field] for r in rows if r['operation']==op]) for field in rows[0] if field.endswith('_seconds')} for op in ['insert','update','delete']}


def queries(folder):
    from src.marts.refresh import acquire,refresh
    from src.marts.checks import reconcile
    results=[];rng=random.Random(12)
    with pg() as c:
        acquire(c);refresh(c)
        with c.transaction():
            c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            checks=reconcile(c)
            for label,dims,filters in [('total',(),{}),('year',('year',),{}),('month_category',('month','category'),{}),
                                      ('district',('month','district'),{}),('product',('product_version',),{}),('slice_2024',('category',),{'years':[2024]})]:
                sql={s:sales_query(dims,filters,s) for s in ['fact','mart']};times={'fact':[],'mart':[]};plans={}
                baseline=None
                for warm in range(2):
                    for s in ['fact','mart']:
                        data=c.execute(*sql[s]).fetchall()
                        if baseline is None:baseline=data
                        if data!=baseline:raise RuntimeError('Fact/mart output differs: '+label)
                for repetition in range(10):
                    order=['fact','mart'];rng.shuffle(order)
                    for s in order:
                        start=time.perf_counter();data=c.execute(*sql[s]).fetchall();elapsed=time.perf_counter()-start
                        if data!=baseline:raise RuntimeError('Timed output differs: '+label)
                        times[s].append(elapsed)
                for s in ['fact','mart']:plans[s]=c.execute('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) '+sql[s][0],sql[s][1]).fetchone()['QUERY PLAN']
                results.append({'query':label,'rows':len(baseline),'dimensions':dims,'filters':filters,'equal_results':True,
                                'timings':{s:summary(v) for s,v in times.items()},'raw_seconds':times,'plans':plans})
            sizes=c.execute("SELECT n.nspname AS schema,sum(pg_total_relation_size(t.oid)) AS bytes FROM pg_class t JOIN pg_namespace n ON n.oid=t.relnamespace WHERE t.relkind='r' AND n.nspname IN ('raw','staging','dw','mart','audit','ml') GROUP BY n.nspname ORDER BY n.nspname").fetchall()
            db_size=c.execute('SELECT pg_database_size(current_database()) AS bytes').fetchone()['bytes']
    data={'queries':results,'mart_reconciliation':checks,'postgres_schema_bytes':sizes,'postgres_database_bytes':db_size,
          'method':'2 warmups + 10 timed repeats per source/query; randomized paired order seed 12; fetchall included; same repeatable-read snapshot; warm shared caches; no cache flush; no speedup guaranteed'}
    (folder/'query-benchmark.json').write_text(json.dumps(data,indent=2,default=str)+'\n',encoding='utf-8')
    return data


def main():
    p=argparse.ArgumentParser();p.add_argument('--evidence-dir',type=Path,required=True);p.add_argument('--samples',type=int,default=20);args=p.parse_args()
    if not 5<=args.samples<=100:raise SystemExit('samples must be 5..100')
    folder=args.evidence_dir;folder.mkdir(parents=True,exist_ok=True);destination=folder/'measurement.json'
    if destination.exists():raise SystemExit('Evidence already exists')
    report={'phase':12,'stage':'measurements','passed':False,'started_at_utc':datetime.now(timezone.utc).isoformat(),
            'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'method':{'samples_per_operation':args.samples,'operations':['insert','update','delete'],'poll_seconds':.1,'clock':'one process perf_counter monotonic',
                      'start':'before source action; includes identity/SQL/commit round trip','ack':'after source action returns',
                      'end':'polling sees matching committed DW state, then matching RFM and delivery outcome',
                      'limitations':['Observed upper-bound timings, not exact binlog-commit timestamps.','Serial demo workload, no concurrency or capacity claim.','ML observed after DW check; may already have been ready.','Does not measure 15-minute scheduled mart propagation or browser rendering.','n=20 p95 is descriptive and unstable, no production SLA claim.']}}
    try:
        with pg() as c:
            before=business(c);models=registry(c)
            report['latency']=latency(c,folder,args.samples)
            if business(c)!=before or registry(c)!=models:raise RuntimeError('Business facts/model registry changed during demo measurements')
            report['historical_facts_unchanged']=True;report['no_retraining']=True
        q=queries(folder);report['query_cases']=len(q['queries']);report['passed']=True
    except Exception as exc:
        report.update(error_type=type(exc).__name__,safe_message=sanitize(str(exc))[:2400]);print(sanitize(traceback.format_exc(limit=8)),flush=True)
    report['finished_at_utc']=datetime.now(timezone.utc).isoformat()
    destination.write_text(json.dumps(report,indent=2,default=str)+'\n',encoding='utf-8');print(json.dumps(report,indent=2,default=str));print('Evidence:',destination)
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
