import os
import time
from src.source.data import json_text
from .codec import decode,GROUP,TOPICS


def pg():
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(host=os.environ.get('PG_HOST','postgres'),dbname='lak_warehouse',
        user='lak_dw',password=os.environ['LAK_POSTGRES_PASSWORD'],autocommit=True,row_factory=dict_row)


def epoch(connection):
    row=connection.execute('SELECT source_epoch FROM audit.pipeline_identity WHERE singleton=true').fetchone()
    if not row:raise RuntimeError('CDC pipeline identity missing; run init first')
    return row['source_epoch']


def heartbeat(connection,worker,error=None):
    connection.execute('INSERT INTO audit.worker_heartbeats(worker,heartbeat_at,safe_error) VALUES(%s,now(),%s) ON CONFLICT(worker) DO UPDATE SET heartbeat_at=now(),safe_error=excluded.safe_error',(worker,error))


def persist(connection,source_epoch,messages):
    from psycopg.types.json import Jsonb
    inserted=0;positions={}
    with connection.transaction():
        for message in messages:
            row=decode(message.topic(),message.partition(),message.offset(),message.key(),message.value())
            row['source_epoch']=source_epoch
            fields=list(row)
            values=[Jsonb(v) if field in ('record_key','record_value') and v is not None else v for field,v in row.items()]
            result=connection.execute('INSERT INTO raw.cdc_events('+','.join(fields)+') VALUES('+','.join(['%s']*len(fields))+') ON CONFLICT(source_epoch,topic,partition_id,kafka_offset) DO NOTHING RETURNING event_id',values).fetchone()
            if result:inserted+=1
            else:
                old=connection.execute('SELECT content_sha256 FROM raw.cdc_events WHERE source_epoch=%s AND topic=%s AND partition_id=%s AND kafka_offset=%s',
                    (source_epoch,row['topic'],row['partition_id'],row['kafka_offset'])).fetchone()
                if old['content_sha256']!=row['content_sha256']:raise RuntimeError('Kafka coordinate reused with different bytes')
            key=(row['topic'],row['partition_id'])
            positions[key]=max(positions.get(key,0),row['kafka_offset']+1)
        for (topic,partition),offset in positions.items():
            connection.execute('INSERT INTO raw.kafka_checkpoints(source_epoch,consumer_group,topic,partition_id,next_offset) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(source_epoch,consumer_group,topic,partition_id) DO UPDATE SET next_offset=greatest(raw.kafka_checkpoints.next_offset,excluded.next_offset),updated_at=now()',
                (source_epoch,GROUP,topic,partition,offset))
    return inserted,positions


def consumer(group):
    from confluent_kafka import Consumer
    return Consumer({'bootstrap.servers':os.environ.get('KAFKA_BOOTSTRAP','kafka:19092'),
        'group.id':group,'enable.auto.commit':False,'auto.offset.reset':'error','session.timeout.ms':30000})


def capture():
    from confluent_kafka import TopicPartition
    with pg() as connection:
        source_epoch=epoch(connection);client=consumer(GROUP)
        def assign(c,partitions):
            chosen=[]
            for part in partitions:
                low,high=c.get_watermark_offsets(part,timeout=15)
                saved=connection.execute('SELECT next_offset FROM raw.kafka_checkpoints WHERE source_epoch=%s AND consumer_group=%s AND topic=%s AND partition_id=%s',
                    (source_epoch,GROUP,part.topic,part.partition)).fetchone()
                offset=saved['next_offset'] if saved else 0
                if not low<=offset<=high:raise RuntimeError('Saved checkpoint outside Kafka retained history')
                chosen.append(TopicPartition(part.topic,part.partition,offset))
            c.assign(chosen)
        client.subscribe(TOPICS,on_assign=assign)
        try:
            while True:
                messages=client.consume(num_messages=500,timeout=1)
                if any(m.error() for m in messages):raise RuntimeError('Kafka consumer returned an error')
                if messages:
                    _,positions=persist(connection,source_epoch,messages)
                    committed=client.commit(offsets=[TopicPartition(t,p,o) for (t,p),o in positions.items()],asynchronous=False)
                    if any(part.error for part in (committed or [])):raise RuntimeError('Kafka acknowledgment failed after raw persistence')
                heartbeat(connection,'collector')
        except Exception as exc:
            heartbeat(connection,'collector',type(exc).__name__+': '+str(exc)[:500])
            raise
        finally:client.close()


def caught_up(connection,source_epoch):
    from confluent_kafka import TopicPartition
    client=consumer('lak-probe-'+str(time.time_ns()))
    try:
        for topic in TOPICS:
            low,high=client.get_watermark_offsets(TopicPartition(topic,0),timeout=10)
            saved=connection.execute('SELECT next_offset FROM raw.kafka_checkpoints WHERE source_epoch=%s AND consumer_group=%s AND topic=%s AND partition_id=0',(source_epoch,GROUP,topic)).fetchone()
            if high and (not saved or saved['next_offset']!=high):return False
        return True
    finally:client.close()
