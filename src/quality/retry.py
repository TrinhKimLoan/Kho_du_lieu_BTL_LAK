def request_retry(connection,error_id):
    """Retry the unchanged raw event after its external cause has been fixed."""
    with connection.transaction():
        row=connection.execute('''SELECT e.*,r.processed_at FROM audit.projection_errors e
            JOIN raw.cdc_events r USING(event_id) WHERE e.error_id=%s FOR UPDATE OF e''',(error_id,)).fetchone()
        if not row:raise ValueError('Projection error ID not found')
        if row['state']=='RESOLVED':return {'error_id':error_id,'state':'RESOLVED','changed':False}
        if row['processed_at'] is not None:
            connection.execute("UPDATE audit.projection_errors SET state='RESOLVED',resolved_at=now() WHERE error_id=%s",(error_id,))
            return {'error_id':error_id,'state':'RESOLVED','changed':True}
        if row['state']=='RETRYING':return {'error_id':error_id,'state':'RETRYING','changed':False}
        connection.execute("UPDATE audit.projection_errors SET state='RETRYING',attempts=attempts+1,resolved_at=NULL WHERE error_id=%s",(error_id,))
        return {'error_id':error_id,'state':'RETRYING','changed':True}


def resolve_processed(connection):
    return connection.execute("""UPDATE audit.projection_errors e SET state='RESOLVED',resolved_at=now()
        FROM raw.cdc_events r WHERE e.event_id=r.event_id AND e.state IN ('OPEN','RETRYING') AND r.processed_at IS NOT NULL""").rowcount
