"""Airflow DAG: ingest raw sources -> clean/transform -> load PostgreSQL DWH."""
from __future__ import annotations

import json
import subprocess
from datetime import timedelta
import sys
from pathlib import Path

import pendulum
from airflow.sdk import dag, task

PROJECT_DIR = Path("/opt/airflow/project")
RAW_DIR = PROJECT_DIR / "datalake" / "raw"
PROCESSED_DIR = PROJECT_DIR / "datalake" / "processed"
OLIST_CSV_FILES = [
    "olist_customers_dataset.csv",
    "olist_geolocation_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "olist_orders_dataset.csv",
    "olist_products_dataset.csv",
    "olist_sellers_dataset.csv",
    "product_category_name_translation.csv",
]


def run_python_script(script_name: str) -> None:
    script_path = PROJECT_DIR / script_name
    if not script_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy script: {script_path}")
    subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(PROJECT_DIR),
        check=True,
    )


@dag(
    dag_id="olist_ingest_transform_load_dwh",
    description="Olist CSV + DummyJSON API -> quality-checked ETL -> PostgreSQL DWH",
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Bangkok"),
    schedule=None,  # Trigger manually while developing; can change after testing.
    catchup=False,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=3)},
    tags=["olist", "etl", "postgres", "data-warehouse"],
)
def olist_ingest_transform_load_dwh():
    @task(task_id="task_1_ingest_data")
    def ingest_data() -> None:
        # Olist is a static Kaggle snapshot downloaded manually once; fail early if any CSV is absent.
        missing = [name for name in OLIST_CSV_FILES if not (RAW_DIR / name).is_file()]
        if missing:
            raise FileNotFoundError(
                "Thiếu CSV Olist trong datalake/raw: " + ", ".join(missing)
            )
        # Refresh DummyJSON API snapshot and verify that its ingestion script succeeded.
        run_python_script("ingest_dummyjson_products.py")
        dummyjson_path = RAW_DIR / "dummyjson_products_raw.json"
        if not dummyjson_path.is_file():
            raise FileNotFoundError(f"Không có JSON DummyJSON sau ingestion: {dummyjson_path}")
        print(f"Ingest OK: found {len(OLIST_CSV_FILES)} Olist CSV files + DummyJSON JSON.")

    @task(task_id="task_2_clean_transform_validate")
    def clean_transform_validate() -> None:
        run_python_script("etl_olist_enrichment_final.py")
        report_path = PROCESSED_DIR / "etl_quality_report.json"
        if not report_path.is_file():
            raise FileNotFoundError(f"ETL không tạo quality report: {report_path}")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        checks = report.get("checks", {})
        failed = [name for name, passed in checks.items() if passed is not True]
        if report.get("run_status") != "success" or not checks or failed:
            raise RuntimeError(
                f"ETL quality gate không đạt: status={report.get('run_status')}; failed_checks={failed}"
            )
        print(f"Transform OK: {len(checks)} quality checks passed.")

    @task(task_id="task_3_load_to_postgresql_dwh")
    def load_to_dwh() -> None:
        run_python_script("load_to_postgres.py")

    task_ingest = ingest_data()
    task_transform = clean_transform_validate()
    task_load = load_to_dwh()
    task_ingest >> task_transform >> task_load


olist_ingest_transform_load_dwh()
