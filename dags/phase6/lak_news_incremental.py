"""The upgraded news DAG is isolated from the legacy LAK DAG folder."""
from datetime import datetime,timezone,timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator


def collect_month():
    from datetime import date
    from src.cdc.store import pg
    from src.news.store import migrate
    from src.news.fetch import fetch_month
    with pg() as connection:
        if not connection.execute('SELECT pg_try_advisory_lock(274106) locked').fetchone()['locked']:
            raise RuntimeError('Another LAK news writer is running')
        migrate(connection)
        today=date.today()
        result=fetch_month(connection,today.year,today.month)
        if result['status']=='FAILED':raise RuntimeError('MediaCloud fetch failed; inspect audit.pipeline_runs and audit.news_fetch_windows')
        return {'run_id':result['run_id'],'status':result['status']}


with DAG('lak_news_incremental_phase6',start_date=datetime(2024,1,1,tzinfo=timezone.utc),
         schedule='@daily',catchup=False,max_active_runs=1,is_paused_upon_creation=True,
         default_args={'owner':'lak','retries':1,'retry_delay':timedelta(minutes=5)},
         tags=['lak','news','polling']) as dag:
    PythonOperator(task_id='fetch_and_project_month',python_callable=collect_month)
