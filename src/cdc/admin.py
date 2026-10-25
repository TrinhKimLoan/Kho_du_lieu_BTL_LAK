import hashlib
import json
import os
import time
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from src.source.data import ROOT,prepare
from src.source.runtime import connect,identity,reconcile
from .codec import PREFIX,DATABASE,TOPICS
from .store import pg

CONNECTOR='lak-source-v1'
CONNECT_URL='http://connect:8083'


def http(path,method='GET',data=None):
    request=Request(CONNECT_URL+path,data=json.dumps(data).encode() if data is not None else None,
        headers={'Content-Type':'application/json'},method=method)
    with urlopen(request,timeout=15) as response:
        payload=response.read()
        return json.loads(payload) if payload else None


def config():
    return {'connector.class':'io.debezium.connector.mysql.MySqlConnector','tasks.max':'1',
        'database.hostname':'mysql','database.port':'3306','database.user':'lak_cdc',
        'database.password':os.environ['LAK_CDC_PASSWORD'],'database.server.id':'274104',
        'topic.prefix':PREFIX,'database.include.list':DATABASE,
        'table.include.list':r'lak_source\.(customers|products|orders)',
        'snapshot.mode':'initial','snapshot.fetch.size':'1000',
        'schema.history.internal.kafka.bootstrap.servers':'kafka:19092',
        'schema.history.internal.kafka.topic':PREFIX+'.source-schema-history',
        'provide.transaction.metadata':'true','decimal.handling.mode':'string',
        'time.precision.mode':'adaptive_time_microseconds','include.schema.changes':'false',
        'tombstones.on.delete':'true','key.converter':'org.apache.kafka.connect.json.JsonConverter',
        'key.converter.schemas.enable':'false','value.converter':'org.apache.kafka.connect.json.JsonConverter',
        'value.converter.schemas.enable':'false','topic.creation.default.replication.factor':'1',
        'topic.creation.default.partitions':'1'}


def ensure_topics():
    from confluent_kafka.admin import AdminClient,NewTopic
    client=AdminClient({'bootstrap.servers':'kafka:19092'})
    topics=TOPICS+[PREFIX+'.source-schema-history']
    existing=client.list_topics(timeout=20)
    missing=[NewTopic(name,num_partitions=1,replication_factor=1,config={'retention.ms':'-1','cleanup.policy':'delete'}) for name in topics if name not in existing.topics]
    for name,future in client.create_topics(missing).items() if missing else []:future.result(timeout=30)
    metadata=client.list_topics(timeout=20)
    for name in topics:
        if name not in metadata.topics or len(metadata.topics[name].partitions)!=1:
            raise RuntimeError('CDC topic missing or not single-partition: '+name)


def init():
    dataset=prepare()
    with connect() as source:
        source_identity=identity(source)
        source_check=reconcile(source,dataset)
    import pymysql
    probe=pymysql.connect(host='mysql',user='lak_cdc',password=os.environ['LAK_CDC_PASSWORD'],database=DATABASE,charset='utf8mb4',connect_timeout=15)
    probe.close()
    source_epoch=source_identity['source_epoch']
    schema_path=ROOT/'sql/phase2/001_warehouse_schema.sql'
    schema_sha=hashlib.sha256(schema_path.read_bytes()).hexdigest()
    with pg() as target:
        exists=target.execute("SELECT to_regclass('audit.schema_versions') AS name").fetchone()['name']
        if exists is None:
            if target.execute("SELECT count(*) n FROM pg_namespace WHERE nspname IN ('raw','staging','dw','mart','audit','ml')").fetchone()['n']:
                raise RuntimeError('Unknown existing warehouse schemas; refusing takeover')
            target.execute(schema_path.read_text(encoding='utf-8'),prepare=False)
        if not target.execute("SELECT 1 FROM audit.schema_versions WHERE version='lak-phase2-v1'").fetchone():
            raise RuntimeError('Unknown warehouse schema version')
        target.execute('CREATE TABLE IF NOT EXISTS audit.pipeline_identity(singleton boolean PRIMARY KEY CHECK(singleton),source_epoch uuid NOT NULL,warehouse_ddl_sha256 text NOT NULL)')
        target.execute('CREATE TABLE IF NOT EXISTS audit.worker_heartbeats(worker text PRIMARY KEY,heartbeat_at timestamptz NOT NULL,safe_error text)')
        previous=target.execute('SELECT * FROM audit.pipeline_identity WHERE singleton=true').fetchone()
        if previous and (str(previous['source_epoch'])!=source_epoch or previous['warehouse_ddl_sha256']!=schema_sha):
            raise RuntimeError('Warehouse belongs to a different source epoch/schema')
        target.execute('INSERT INTO audit.pipeline_identity(singleton,source_epoch,warehouse_ddl_sha256) VALUES(true,%s,%s) ON CONFLICT(singleton) DO NOTHING',(source_epoch,schema_sha))
        from psycopg.types.json import Jsonb
        with target.transaction():
            with target.cursor() as cursor:
                cursor.executemany('INSERT INTO raw.import_rows(file_name,file_sha256,excel_row_number,entity_type,entity_key,sanitized_payload,redaction_version) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                    [(r['file_name'],r['file_sha256'],r['excel_row_number'],r['entity_type'],r['entity_key'],Jsonb(json.loads(r['sanitized_payload'])),r['redaction_version']) for r in dataset['import_rows']])
            rows=target.execute('SELECT file_name,file_sha256,excel_row_number,entity_type,entity_key,sanitized_payload,redaction_version FROM raw.import_rows').fetchall()
            expected={(r['file_name'],r['file_sha256'],r['excel_row_number']):r for r in dataset['import_rows']}
            if len(rows)!=len(expected):raise RuntimeError('Warehouse provenance count differs')
            for row in rows:
                original=expected.get((row['file_name'],row['file_sha256'],row['excel_row_number']))
                if original is None or row['sanitized_payload']!=json.loads(original['sanitized_payload']) or any(row[k]!=original[k] for k in ('entity_type','entity_key','redaction_version')):
                    raise RuntimeError('Warehouse provenance differs from validated source input')
    ensure_topics()
    deadline=time.monotonic()+180
    while True:
        try:
            http('/connectors');break
        except (URLError,TimeoutError):
            if time.monotonic()>=deadline:raise RuntimeError('Kafka Connect did not become ready')
            time.sleep(2)
    desired=config()
    try:existing=http('/connectors/'+CONNECTOR+'/config')
    except HTTPError as exc:
        if exc.code!=404:raise
        existing=None
    if existing:
        if any(str(existing.get(k))!=v for k,v in desired.items() if k!='database.password'):
            raise RuntimeError('Existing connector differs; offsets were not reset')
    else:http('/connectors','POST',{'name':CONNECTOR,'config':desired})
    return {'source_epoch':source_epoch,'warehouse_ddl_sha256':schema_sha,'provenance_rows':len(dataset['import_rows']),
            'connector':CONNECTOR,'topics':TOPICS,'historical_source_digest':source_check['history_state_sha256']}


def connector_running():
    status=http('/connectors/'+CONNECTOR+'/status')
    if status['connector']['state']=='FAILED' or any(task['state']=='FAILED' for task in status['tasks']):
        traces='\n'.join(task.get('trace','') for task in status['tasks'] if task['state']=='FAILED')
        for name,value in os.environ.items():
            if ('PASSWORD' in name or 'SECRET' in name) and len(value)>=4:traces=traces.replace(value,'[REDACTED]')
        raise RuntimeError('Debezium connector/task FAILED: '+traces[-1800:])
    return status['connector']['state']=='RUNNING' and bool(status['tasks']) and all(task['state']=='RUNNING' for task in status['tasks'])
