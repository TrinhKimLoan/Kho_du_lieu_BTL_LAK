"""One atomic analytical snapshot every fifteen minutes when unpaused."""
from datetime import datetime,timezone,timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator


def rebuild():
    from src.cdc.store import pg
    from src.marts.refresh import acquire,migrate,refresh
    from src.marts.checks import reconcile
    with pg() as connection:
        acquire(connection);migrate(connection)
        result=refresh(connection)
        with connection.transaction():
            connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            reconcile(connection)
        return result


with DAG('lak_mart_refresh_phase7',start_date=datetime(2024,1,1,tzinfo=timezone.utc),
         schedule='*/15 * * * *',catchup=False,max_active_runs=1,is_paused_upon_creation=True,
         default_args={'owner':'lak','retries':1,'retry_delay':timedelta(minutes=2)},
         tags=['lak','mart','olap']) as dag:
    PythonOperator(task_id='refresh_and_reconcile',python_callable=rebuild)
