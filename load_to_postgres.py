#!/usr/bin/env python3
"""Load the validated Olist ETL CSV outputs into PostgreSQL as a full refresh.

Loads 4 dimensions, 3 facts, and category_mapping_audit into schema `dwh`.
The existing schema is replaced atomically in one PostgreSQL transaction.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, Float, Integer, MetaData, Numeric,
    SmallInteger, String, Text, create_engine, text,
)
from sqlalchemy.engine import URL

BASE_DIR = Path(__file__).resolve().parent
PROCESSED_DIR = BASE_DIR / "datalake" / "processed"
SCHEMA = os.getenv("DWH_SCHEMA", "dwh")
if not SCHEMA.isidentifier():
    raise ValueError("DWH_SCHEMA chỉ được gồm chữ, số và dấu gạch dưới, không bắt đầu bằng số.")

TABLE_FILES = {
    "dim_customer": "dim_customer.csv",
    "dim_product": "dim_product.csv",
    "dim_seller": "dim_seller.csv",
    "dim_time": "dim_time.csv",
    "fact_sales": "fact_sales.csv",
    "fact_payments": "fact_payments.csv",
    "fact_orders": "fact_orders.csv",
    "category_mapping_audit": "category_mapping_audit.csv",
}

STRING_COLUMNS = {
    "dim_customer": ["customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state"],
    "dim_product": ["product_id", "product_category_name", "category_olist", "category_translation_status", "dummyjson_mapped_categories", "dummyjson_categories_found", "mapping_status", "mapping_confidence", "mapping_notes"],
    "dim_seller": ["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"],
    "dim_time": ["month_name", "day_of_week"],
    "fact_sales": ["order_id", "order_status"],
    "fact_payments": ["order_id", "order_status", "payment_type"],
    "fact_orders": ["order_id", "order_status"],
    "category_mapping_audit": ["category_olist", "category_translation_status", "dummyjson_mapped_categories", "dummyjson_categories_found", "mapping_status", "mapping_confidence", "mapping_notes"],
}

INTEGER_COLUMNS = {
    "dim_customer": ["customer_sk", "zip_geo_coordinate_rows"],
    "dim_product": ["product_sk", "dummyjson_products_count", "dummyjson_rated_products_count"],
    "dim_seller": ["seller_sk", "zip_geo_coordinate_rows"],
    "dim_time": ["time_sk", "year", "quarter", "month", "day", "day_of_week_num"],
    "fact_sales": ["order_item_id", "customer_sk", "product_sk", "seller_sk", "time_sk"],
    "fact_payments": ["payment_sk", "payment_sequential", "customer_sk", "time_sk", "payment_installments"],
    "fact_orders": ["customer_sk", "purchase_time_sk", "approved_time_sk", "carrier_time_sk", "delivered_time_sk", "estimated_delivery_time_sk", "review_creation_time_sk", "review_answer_time_sk", "review_count", "review_score_count", "review_comment_count"],
    "category_mapping_audit": ["olist_product_count", "dummyjson_products_count", "dummyjson_rated_products_count"],
}

BOOLEAN_COLUMNS = {
    "dim_customer": ["has_geolocation"],
    "dim_product": ["product_weight_g_was_missing", "product_length_cm_was_missing", "product_height_cm_was_missing", "product_width_cm_was_missing"],
    "dim_seller": ["has_geolocation"],
    "dim_time": ["is_weekend"],
    "fact_sales": [],
    "fact_payments": [],
    "fact_orders": ["is_delivered", "is_cancelled", "is_late_delivery", "has_review", "has_review_comment"],
    "category_mapping_audit": [],
}

DATETIME_COLUMNS = {
    "fact_sales": ["shipping_limit_date"],
    "fact_payments": [],
    "fact_orders": ["order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date", "review_creation_date", "review_answer_timestamp"],
}

FLOAT_COLUMNS = {
    "dim_customer": ["customer_latitude", "customer_longitude"],
    "dim_product": ["dummyjson_category_avg_rating", "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"],
    "dim_seller": ["seller_latitude", "seller_longitude"],
    "fact_sales": [],
    "fact_payments": [],
    "fact_orders": [],
    "category_mapping_audit": [],
}

# SQLAlchemy column types are declared explicitly so nullable integer keys (for example
# approved_time_sk) do not become DOUBLE PRECISION when read from CSV.
DTYPES: dict[str, dict[str, Any]] = {
    "dim_customer": {
        "customer_sk": BigInteger(), "customer_id": String(64), "customer_unique_id": String(64),
        "customer_zip_code_prefix": String(16), "customer_city": Text(), "customer_state": String(8),
        "customer_latitude": Float(), "customer_longitude": Float(), "zip_geo_coordinate_rows": BigInteger(), "has_geolocation": Boolean(),
    },
    "dim_product": {
        "product_sk": BigInteger(), "product_id": String(64), "product_category_name": Text(),
        "category_olist": Text(), "category_translation_status": String(40),
        "dummyjson_mapped_categories": Text(), "dummyjson_categories_found": Text(),
        "mapping_status": String(50), "mapping_confidence": String(30), "mapping_notes": Text(),
        "dummyjson_category_avg_rating": Float(), "dummyjson_products_count": BigInteger(),
        "dummyjson_rated_products_count": BigInteger(), "product_weight_g": Float(),
        "product_length_cm": Float(), "product_height_cm": Float(), "product_width_cm": Float(),
        "product_weight_g_was_missing": Boolean(), "product_length_cm_was_missing": Boolean(),
        "product_height_cm_was_missing": Boolean(), "product_width_cm_was_missing": Boolean(),
    },
    "dim_seller": {
        "seller_sk": BigInteger(), "seller_id": String(64), "seller_zip_code_prefix": String(16),
        "seller_city": Text(), "seller_state": String(8), "seller_latitude": Float(),
        "seller_longitude": Float(), "zip_geo_coordinate_rows": BigInteger(), "has_geolocation": Boolean(),
    },
    "dim_time": {
        "time_sk": BigInteger(), "full_date": Date(), "year": Integer(), "quarter": SmallInteger(),
        "month": SmallInteger(), "month_name": String(20), "day": SmallInteger(),
        "day_of_week": String(20), "day_of_week_num": SmallInteger(), "is_weekend": Boolean(),
    },
    "fact_sales": {
        "order_id": String(64), "order_item_id": BigInteger(), "customer_sk": BigInteger(),
        "product_sk": BigInteger(), "seller_sk": BigInteger(), "time_sk": BigInteger(),
        "order_status": String(40), "item_price": Numeric(14, 2), "freight_value": Numeric(14, 2),
        "shipping_limit_date": DateTime(),
    },
    "fact_payments": {
        "payment_sk": BigInteger(), "order_id": String(64), "payment_sequential": BigInteger(),
        "customer_sk": BigInteger(), "time_sk": BigInteger(), "order_status": String(40),
        "payment_type": String(40), "payment_installments": BigInteger(), "payment_value": Numeric(14, 2),
    },
    "fact_orders": {
        "order_id": String(64), "customer_sk": BigInteger(), "purchase_time_sk": BigInteger(),
        "approved_time_sk": BigInteger(), "carrier_time_sk": BigInteger(), "delivered_time_sk": BigInteger(),
        "estimated_delivery_time_sk": BigInteger(), "review_creation_time_sk": BigInteger(),
        "review_answer_time_sk": BigInteger(), "order_status": String(40),
        "order_purchase_timestamp": DateTime(), "order_approved_at": DateTime(),
        "order_delivered_carrier_date": DateTime(), "order_delivered_customer_date": DateTime(),
        "order_estimated_delivery_date": DateTime(), "delivery_days": Numeric(12, 3),
        "delivery_delay_days": Numeric(12, 3), "is_delivered": Boolean(), "is_cancelled": Boolean(),
        "is_late_delivery": Boolean(), "review_score_avg": Numeric(5, 3), "review_count": BigInteger(),
        "review_score_count": BigInteger(), "review_comment_count": BigInteger(),
        "review_creation_date": DateTime(), "review_answer_timestamp": DateTime(),
        "has_review": Boolean(), "has_review_comment": Boolean(),
    },
    "category_mapping_audit": {
        "category_olist": Text(), "category_translation_status": String(40), "olist_product_count": BigInteger(),
        "dummyjson_mapped_categories": Text(), "dummyjson_categories_found": Text(),
        "mapping_status": String(50), "mapping_confidence": String(30), "mapping_notes": Text(),
        "dummyjson_products_count": BigInteger(), "dummyjson_rated_products_count": BigInteger(),
        "dummyjson_category_avg_rating": Float(), "olist_product_share_pct": Numeric(8, 2),
    },
}

EXPECTED_COLUMNS = {
    "dim_customer": {"customer_sk", "customer_id", "customer_unique_id"},
    "dim_product": {"product_sk", "product_id", "category_olist"},
    "dim_seller": {"seller_sk", "seller_id"},
    "dim_time": {"time_sk", "full_date"},
    "fact_sales": {"order_id", "order_item_id", "customer_sk", "product_sk", "seller_sk", "time_sk", "item_price", "freight_value"},
    "fact_payments": {"payment_sk", "order_id", "payment_sequential", "customer_sk", "time_sk", "payment_value"},
    "fact_orders": {"order_id", "customer_sk", "purchase_time_sk", "order_status"},
    "category_mapping_audit": {"category_olist", "mapping_status", "olist_product_count"},
}


def load_and_normalize(table: str, filename: str) -> pd.DataFrame:
    path = PROCESSED_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy file đầu vào: {path}")
    frame = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    missing = EXPECTED_COLUMNS[table] - set(frame.columns)
    if missing:
        raise ValueError(f"{filename} thiếu các cột bắt buộc: {sorted(missing)}")

    for col in STRING_COLUMNS.get(table, []):
        if col in frame.columns:
            frame[col] = frame[col].astype("string")

    for col in INTEGER_COLUMNS.get(table, []):
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="raise").astype("Int64")

    for col in FLOAT_COLUMNS.get(table, []):
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="raise")

    for col in BOOLEAN_COLUMNS.get(table, []):
        if col in frame.columns:
            normalized = frame[col].astype("string").str.strip().str.lower()
            mapping = {"true": True, "1": True, "yes": True, "false": False, "0": False, "no": False}
            invalid = normalized.notna() & ~normalized.isin(mapping)
            if invalid.any():
                raise ValueError(f"{filename}.{col} có giá trị boolean không hợp lệ: {normalized[invalid].head(5).tolist()}")
            frame[col] = normalized.map(mapping).astype("boolean")

    for col in DATETIME_COLUMNS.get(table, []):
        if col in frame.columns:
            original = frame[col]
            parsed = pd.to_datetime(original, errors="coerce")
            invalid = original.notna() & parsed.isna()
            if invalid.any():
                raise ValueError(f"{filename}.{col} có timestamp không hợp lệ.")
            frame[col] = parsed

    if table == "dim_time" and "full_date" in frame.columns:
        parsed = pd.to_datetime(frame["full_date"], errors="raise")
        frame["full_date"] = parsed.dt.date

    # Check primary/business key candidates before creating database constraints.
    key_columns = {
        "dim_customer": ["customer_sk", "customer_id"],
        "dim_product": ["product_sk", "product_id"],
        "dim_seller": ["seller_sk", "seller_id"],
        "dim_time": ["time_sk", "full_date"],
        "fact_sales": ["order_id", "order_item_id"],
        "fact_payments": ["payment_sk", "order_id", "payment_sequential"],
        "fact_orders": ["order_id"],
    }.get(table, [])
    for col in key_columns:
        if frame[col].isna().any():
            raise ValueError(f"{filename}.{col} có giá trị khóa bị thiếu.")
    if table == "fact_sales" and frame.duplicated(["order_id", "order_item_id"]).any():
        raise ValueError("fact_sales.csv trùng khóa (order_id, order_item_id).")
    if table == "fact_payments" and frame.duplicated(["order_id", "payment_sequential"]).any():
        raise ValueError("fact_payments.csv trùng khóa (order_id, payment_sequential).")
    return frame


def add_constraints(conn) -> None:
    statements = [
        f"ALTER TABLE {SCHEMA}.dim_customer ADD CONSTRAINT pk_dim_customer PRIMARY KEY (customer_sk)",
        f"ALTER TABLE {SCHEMA}.dim_customer ADD CONSTRAINT uq_dim_customer_customer_id UNIQUE (customer_id)",
        f"ALTER TABLE {SCHEMA}.dim_product ADD CONSTRAINT pk_dim_product PRIMARY KEY (product_sk)",
        f"ALTER TABLE {SCHEMA}.dim_product ADD CONSTRAINT uq_dim_product_product_id UNIQUE (product_id)",
        f"ALTER TABLE {SCHEMA}.dim_seller ADD CONSTRAINT pk_dim_seller PRIMARY KEY (seller_sk)",
        f"ALTER TABLE {SCHEMA}.dim_seller ADD CONSTRAINT uq_dim_seller_seller_id UNIQUE (seller_id)",
        f"ALTER TABLE {SCHEMA}.dim_time ADD CONSTRAINT pk_dim_time PRIMARY KEY (time_sk)",
        f"ALTER TABLE {SCHEMA}.dim_time ADD CONSTRAINT uq_dim_time_full_date UNIQUE (full_date)",
        f"ALTER TABLE {SCHEMA}.fact_sales ADD CONSTRAINT pk_fact_sales PRIMARY KEY (order_id, order_item_id)",
        f"ALTER TABLE {SCHEMA}.fact_sales ADD CONSTRAINT fk_sales_customer FOREIGN KEY (customer_sk) REFERENCES {SCHEMA}.dim_customer(customer_sk)",
        f"ALTER TABLE {SCHEMA}.fact_sales ADD CONSTRAINT fk_sales_product FOREIGN KEY (product_sk) REFERENCES {SCHEMA}.dim_product(product_sk)",
        f"ALTER TABLE {SCHEMA}.fact_sales ADD CONSTRAINT fk_sales_seller FOREIGN KEY (seller_sk) REFERENCES {SCHEMA}.dim_seller(seller_sk)",
        f"ALTER TABLE {SCHEMA}.fact_sales ADD CONSTRAINT fk_sales_time FOREIGN KEY (time_sk) REFERENCES {SCHEMA}.dim_time(time_sk)",
        f"ALTER TABLE {SCHEMA}.fact_payments ADD CONSTRAINT pk_fact_payments PRIMARY KEY (payment_sk)",
        f"ALTER TABLE {SCHEMA}.fact_payments ADD CONSTRAINT uq_fact_payment_source_key UNIQUE (order_id, payment_sequential)",
        f"ALTER TABLE {SCHEMA}.fact_payments ADD CONSTRAINT fk_payments_customer FOREIGN KEY (customer_sk) REFERENCES {SCHEMA}.dim_customer(customer_sk)",
        f"ALTER TABLE {SCHEMA}.fact_payments ADD CONSTRAINT fk_payments_time FOREIGN KEY (time_sk) REFERENCES {SCHEMA}.dim_time(time_sk)",
        f"ALTER TABLE {SCHEMA}.fact_orders ADD CONSTRAINT pk_fact_orders PRIMARY KEY (order_id)",
        f"ALTER TABLE {SCHEMA}.fact_orders ADD CONSTRAINT fk_orders_customer FOREIGN KEY (customer_sk) REFERENCES {SCHEMA}.dim_customer(customer_sk)",
    ]
    for key_col in ["purchase_time_sk", "approved_time_sk", "carrier_time_sk", "delivered_time_sk", "estimated_delivery_time_sk", "review_creation_time_sk", "review_answer_time_sk"]:
        statements.append(
            f"ALTER TABLE {SCHEMA}.fact_orders ADD CONSTRAINT fk_orders_{key_col} FOREIGN KEY ({key_col}) REFERENCES {SCHEMA}.dim_time(time_sk)"
        )
    for stmt in statements:
        conn.execute(text(stmt))

    # Useful indexes for filters and joins in Power BI / SQL.
    index_statements = [
        f"CREATE INDEX ix_fact_sales_customer ON {SCHEMA}.fact_sales(customer_sk)",
        f"CREATE INDEX ix_fact_sales_product ON {SCHEMA}.fact_sales(product_sk)",
        f"CREATE INDEX ix_fact_sales_seller ON {SCHEMA}.fact_sales(seller_sk)",
        f"CREATE INDEX ix_fact_sales_time ON {SCHEMA}.fact_sales(time_sk)",
        f"CREATE INDEX ix_fact_sales_order ON {SCHEMA}.fact_sales(order_id)",
        f"CREATE INDEX ix_fact_payments_type ON {SCHEMA}.fact_payments(payment_type)",
        f"CREATE INDEX ix_fact_payments_customer ON {SCHEMA}.fact_payments(customer_sk)",
        f"CREATE INDEX ix_fact_orders_customer ON {SCHEMA}.fact_orders(customer_sk)",
        f"CREATE INDEX ix_fact_orders_purchase_time ON {SCHEMA}.fact_orders(purchase_time_sk)",
    ]
    for stmt in index_statements:
        conn.execute(text(stmt))


def main() -> int:
    report_path = PROCESSED_DIR / "etl_quality_report.json"
    if not report_path.is_file():
        raise FileNotFoundError(f"Không có báo cáo quality gate: {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("run_status") != "success":
        raise RuntimeError(f"Không load vào DWH: ETL run_status={report.get('run_status')!r}.")
    checks = report.get("checks", {})
    failed = [name for name, passed in checks.items() if passed is not True]
    if not checks or failed:
        raise RuntimeError(f"Không load vào DWH: quality checks không đạt hoặc thiếu. Failed: {failed}")

    host = os.getenv("DWH_HOST", "localhost")
    port = int(os.getenv("DWH_PORT", "5433"))
    database = os.getenv("DWH_DATABASE", "olist_dwh")
    username = os.getenv("DWH_USER", "dwh_user")
    password = os.getenv("DWH_PASSWORD", "dwh_password")
    url = URL.create("postgresql+psycopg2", username=username, password=password, host=host, port=port, database=database)
    engine = create_engine(url, pool_pre_ping=True)

    frames = {table: load_and_normalize(table, filename) for table, filename in TABLE_FILES.items()}
    expected_rows = {table: len(frame) for table, frame in frames.items()}
    print(f"ETL quality gate: success; {len(checks)} checks all passed.")
    print(f"Connecting to PostgreSQL {host}:{port}/{database}, schema={SCHEMA}")

    try:
        # PostgreSQL DDL is transactional: if a load or constraint fails, rollback restores
        # the previous dwh schema rather than leaving a half-loaded set of tables.
        with engine.begin() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
            conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
            for table, frame in frames.items():
                frame.to_sql(
                    name=table,
                    con=conn,
                    schema=SCHEMA,
                    if_exists="fail",
                    index=False,
                    chunksize=1000,
                    method="multi",
                    dtype=DTYPES[table],
                )
                print(f"Loaded {SCHEMA}.{table}: {len(frame):,} rows")
            add_constraints(conn)
            db_counts: dict[str, int] = {}
            for table, expected in expected_rows.items():
                count = conn.execute(text(f"SELECT COUNT(*) FROM {SCHEMA}.{table}")).scalar_one()
                db_counts[table] = int(count)
                if count != expected:
                    raise RuntimeError(f"Row count mismatch for {table}: CSV={expected}, PostgreSQL={count}")
            print("PostgreSQL row counts verified:", json.dumps(db_counts, ensure_ascii=False))
    finally:
        engine.dispose()

    load_report = {
        "run_status": "success",
        "loaded_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "host": host,
        "port": port,
        "database": database,
        "schema": SCHEMA,
        "rows": expected_rows,
        "quality_report_status": report.get("run_status"),
        "quality_checks_passed": len(checks),
    }
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    (PROCESSED_DIR / "dwh_load_report.json").write_text(
        json.dumps(load_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("LOAD SUCCESS: all dimensions, facts, and category_mapping_audit committed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"LOAD FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
