from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from decimal import Decimal

from .data import ROOT, FIELDS, KEYS, canonical, fingerprint, json_text, table_digest

SCHEMA_VERSION = 'lak-source-phase3-v1'
SQL_PATH = ROOT / 'sql/phase3/001_mysql_source.sql'
TABLES = {'source_identity','customers','products','orders','import_files','import_rows'}


def connect():
    import pymysql
    password = os.environ.get('MYSQL_PASSWORD')
    if not password:
        raise RuntimeError('MYSQL_PASSWORD is missing; use the supplied Compose runner')
    connection = pymysql.connect(host=os.environ.get('MYSQL_HOST','mysql'),
        port=int(os.environ.get('MYSQL_PORT','3306')), user=os.environ.get('MYSQL_USER','lak_app'),
        password=password, database=os.environ.get('MYSQL_DATABASE','lak_source'),
        charset='utf8mb4', autocommit=False, cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=15, read_timeout=180, write_timeout=180)
    with connection.cursor() as cursor:
        cursor.execute("SET SESSION time_zone='+00:00'")
        cursor.execute("SET SESSION sql_mode='STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION'")
    return connection


def identity(connection, ready=True):
    with connection.cursor() as cursor:
        cursor.execute('SELECT * FROM source_identity WHERE singleton_id=1')
        row = cursor.fetchone()
    expected = hashlib.sha256(SQL_PATH.read_bytes()).hexdigest()
    if not row or row['project_name'] != 'LAK-Analytics' or row['schema_version'] != SCHEMA_VERSION or row['ddl_sha256'] != expected:
        raise RuntimeError('Database identity/schema fingerprint differs; refusing to overwrite an existing source')
    if ready and row['install_state'] != 'READY':
        raise RuntimeError('Source installation is not READY; run install and inspect its evidence')
    return row


def install(connection):
    sql = SQL_PATH.read_text(encoding='utf-8')
    statements = [part.strip() for part in sql.split(';') if part.strip()]
    with connection.cursor() as cursor:
        cursor.execute('SHOW TABLES')
        existing = {next(iter(row.values())) for row in cursor.fetchall()}
        if existing and 'source_identity' not in existing:
            raise RuntimeError('Existing database has no LAK identity; no schema was overwritten')
        if not existing:
            cursor.execute(statements[0])
            cursor.execute('INSERT INTO source_identity(singleton_id,project_name,source_epoch,schema_version,ddl_sha256,install_state) VALUES(1,%s,%s,%s,%s,%s)',
                ('LAK-Analytics',str(uuid.uuid4()),SCHEMA_VERSION,hashlib.sha256(SQL_PATH.read_bytes()).hexdigest(),'PREPARING'))
            connection.commit()
        current = identity(connection, ready=False)
        if existing - TABLES:
            raise RuntimeError('Unexpected tables in dedicated LAK source; investigate before continuing')
        for statement in statements[1:]:
            cursor.execute(statement)
        for table, fields in FIELDS.items():
            cursor.execute('SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s',(table,))
            actual = {row['COLUMN_NAME'] for row in cursor.fetchall()}
            if actual != set(fields) | {'updated_at'}:
                raise RuntimeError('MySQL columns differ from contract: ' + table)
        cursor.execute('SELECT @@log_bin AS log_bin,@@binlog_format AS binlog_format,@@binlog_row_image AS binlog_row_image,@@server_id AS server_id')
        settings = cursor.fetchone()
        if int(settings['log_bin']) != 1 or settings['binlog_format'] != 'ROW' or settings['binlog_row_image'] != 'FULL' or int(settings['server_id']) != 274103:
            raise RuntimeError('MySQL binlog configuration differs from phase 3 contract')
        cursor.execute("UPDATE source_identity SET install_state='READY' WHERE singleton_id=1")
    connection.commit()
    return {'source_epoch': current['source_epoch'], 'schema_version': SCHEMA_VERSION, 'binlog': settings}


def identifier(value):
    if not re.fullmatch(r'[a-z_]+',value):
        raise ValueError('Invalid internal SQL identifier')
    return '`' + value + '`'


def insert_noop(cursor, table, rows, fields, primary_key):
    sql = 'INSERT INTO ' + identifier(table) + ' (' + ','.join(map(identifier,fields)) + ') VALUES (' + ','.join(['%s'] * len(fields)) + ') ON DUPLICATE KEY UPDATE ' + identifier(primary_key) + '=' + identifier(primary_key)
    for start in range(0,len(rows),500):
        cursor.executemany(sql, [tuple(row[field] for field in fields) for row in rows[start:start+500]])


def reconcile(connection, dataset):
    identity_row = identity(connection)
    digests, counts, state = {}, {}, {}
    with connection.cursor() as cursor:
        for table, fields in FIELDS.items():
            cursor.execute('SELECT ' + ','.join(map(identifier,fields)) + ',updated_at FROM ' + identifier(table) + ' WHERE is_demo=0')
            actual = cursor.fetchall()
            digests[table] = table_digest(actual, fields, KEYS[table])
            counts[table] = len(actual)
            if digests[table] != dataset['digests'][table] or len(actual) != len(dataset[table]):
                raise RuntimeError('Historical rows differ from Excel, including full field values: ' + table)
            state[table] = fingerprint(sorted(actual,key=lambda row: row[KEYS[table]]))
        cursor.execute('SELECT file_name,file_sha256,row_count FROM import_files')
        actual_files = cursor.fetchall()
        if sorted(actual_files,key=lambda row:row['file_name']) != sorted(dataset['import_files'],key=lambda row:row['file_name']):
            raise RuntimeError('Imported file manifests differ')
        cursor.execute('SELECT * FROM import_rows')
        provenance = cursor.fetchall()
        expected = {(r['file_name'],r['file_sha256'],r['excel_row_number']): r for r in dataset['import_rows']}
        if len(provenance) != len(expected):
            raise RuntimeError('Provenance row count differs')
        for row in provenance:
            key = (row['file_name'],row['file_sha256'],row['excel_row_number'])
            target = expected.get(key)
            payload = row['sanitized_payload']
            payload = json.loads(payload) if isinstance(payload,str) else payload
            if target is None or fingerprint(payload) != row['payload_sha256'] or row['payload_sha256'] != target['payload_sha256']:
                raise RuntimeError('Provenance payload/fingerprint mismatch')
            if any(row[f] != target[f] for f in ('entity_type','entity_key','redaction_version')):
                raise RuntimeError('Provenance entity mapping mismatch')
        cursor.execute('SELECT SUM(goods_amount) goods,SUM(vat_amount) vat,SUM(shipping_fee) shipping_fee,SUM(total_paid) total_paid FROM orders WHERE is_demo=0')
        totals = cursor.fetchone()
        if any(totals[key] != Decimal(value) for key,value in dataset['money_totals_vnd'].items()):
            raise RuntimeError('Monetary reconciliation failed')
        cursor.execute('SELECT COUNT(*) n FROM orders WHERE is_demo=1')
        demo_count = cursor.fetchone()['n']
    return {'source_epoch':identity_row['source_epoch'],'counts':counts,'digests':digests,
        'history_state_sha256':fingerprint(state),'provenance_rows':len(provenance),
        'money_totals_vnd':canonical(totals),'demo_orders':demo_count,'observations':dataset['observations']}


def load_history(connection, dataset):
    identity(connection)
    connection.rollback()
    connection.begin()
    try:
        with connection.cursor() as cursor:
            for table, fields in FIELDS.items():
                insert_noop(cursor,table,dataset[table],fields,KEYS[table])
            insert_noop(cursor,'import_files',dataset['import_files'],['file_name','file_sha256','row_count'],'file_name')
            insert_noop(cursor,'import_rows',dataset['import_rows'],
                ['file_name','file_sha256','excel_row_number','entity_type','entity_key','sanitized_payload','payload_sha256','redaction_version'],'file_name')
        result = reconcile(connection,dataset)
        connection.commit()
        return result
    except Exception:
        connection.rollback()
        raise
