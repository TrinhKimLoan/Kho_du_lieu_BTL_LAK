"""Orchestrate the ETL stages and commit outputs only after quality gates pass."""
import logging
import shutil
import sys
from datetime import datetime
from typing import Any

from .config import BASE_DIR, OUTPUT_CSVS, PROCESSED_DIR, RAW_DIR, STAGING_DIR
from .dimensions import build_dimensions
from .facts import build_facts
from .quality import build_category_audit, populate_quality_report
from .sources import load_and_validate_sources
from .utils import configure_logging, write_csv, write_json

def run_etl() -> dict[str, Any]:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    if STAGING_DIR.exists():
        shutil.rmtree(STAGING_DIR)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    join_audit: list[dict[str, Any]] = []
    quality: dict[str, Any] = {
        "run_status": "running",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "raw_directory": str(RAW_DIR),
        "processed_directory": str(PROCESSED_DIR),
        "source_definition": "9 Olist CSV files + DummyJSON products JSON",
        "fact_grains": {
            "Fact_Sales": "one row per (order_id, order_item_id)",
            "Fact_Payments": "one row per (order_id, payment_sequential)",
            "Fact_Orders": "one row per order_id; review information aggregated to order grain",
        },
        "important_semantics": [
            "DummyJSON category average Rating is contextual sample data, not actual Olist product/customer feedback.",
            "Olist review_score is genuine review data contained in the Olist dataset and is separate from DummyJSON Rating.",
            "For realized sales analysis, use a documented order-status filter (often delivered); fact tables retain statuses for transparency.",
            "Full-refresh surrogate keys are deterministic for this complete source snapshot, but are not an incremental-ETL key strategy.",
        ],
    }

    try:
        sources = load_and_validate_sources(quality)
        dimensions = build_dimensions(sources, quality, join_audit)
        facts = build_facts(sources, dimensions, join_audit)
        category_audit = build_category_audit(dimensions.dim_product)
        populate_quality_report(sources, dimensions, facts, category_audit, quality, join_audit)

        # Save the audit to staging first. If any gate fails, don't replace final CSVs.
        write_csv(category_audit, STAGING_DIR / "category_mapping_audit.csv")
        if quality["failed_checks"]:
            quality["message"] = "Không commit các bảng đầu ra vì một hoặc nhiều kiểm tra chất lượng thất bại. Xem checks/join_audit."
            write_json(PROCESSED_DIR / "etl_quality_report.json", quality)
            raise ValueError(f"Quality gates failed: {quality['failed_checks']}")

        output_tables = {
            "dim_customer.csv": dimensions.dim_customer,
            "dim_product.csv": dimensions.dim_product,
            "dim_seller.csv": dimensions.dim_seller,
            "dim_time.csv": dimensions.dim_time,
            "fact_sales.csv": facts.fact_sales,
            "fact_payments.csv": facts.fact_payments,
            "fact_orders.csv": facts.fact_orders,
            "category_mapping_audit.csv": category_audit,
        }
        for filename, frame in output_tables.items():
            write_csv(frame, STAGING_DIR / filename)
        write_json(STAGING_DIR / "etl_quality_report.json", quality)
        # Commit only after all files are created and the quality checks pass.
        for filename in OUTPUT_CSVS + ["etl_quality_report.json"]:
            (STAGING_DIR / filename).replace(PROCESSED_DIR / filename)
        shutil.rmtree(STAGING_DIR, ignore_errors=True)

        logging.info("=" * 72)
        logging.info("ETL HOÀN THÀNH: tất cả quality gates đạt.")
        logging.info("Dimensions: Customer=%s | Product=%s | Seller=%s | Time=%s", f"{len(dimensions.dim_customer):,}", f"{len(dimensions.dim_product):,}", f"{len(dimensions.dim_seller):,}", f"{len(dimensions.dim_time):,}")
        logging.info("Facts: Sales=%s | Payments=%s | Orders=%s", f"{len(facts.fact_sales):,}", f"{len(facts.fact_payments):,}", f"{len(facts.fact_orders):,}")
        logging.info("Tổng item_price=%.2f | freight=%.2f | payment_value=%.2f", facts.fact_sales["item_price"].sum(), facts.fact_sales["freight_value"].sum(), facts.fact_payments["payment_value"].sum())
        logging.info("Mapping coverage: %.2f%% category rules; %.2f%% Olist products have usable Rating enrichment.", quality["category_mapping"]["category_mapping_rule_coverage_pct_by_category"], quality["category_mapping"]["olist_products_with_usable_rating_enrichment_pct"])
        logging.info("Đọc etl_quality_report.json và category_mapping_audit.csv trước khi bàn giao cho BI/Data Mining.")
        return quality
    except Exception as exc:
        if quality.get("run_status") != "failed_quality_checks":
            quality["run_status"] = "failed"
        quality["error"] = f"{type(exc).__name__}: {exc}"
        quality["join_audit"] = join_audit
        write_json(PROCESSED_DIR / "etl_quality_report.json", quality)
        shutil.rmtree(STAGING_DIR, ignore_errors=True)
        raise

def main() -> int:
    configure_logging()
    try:
        run_etl()
        return 0
    except Exception as exc:
        logging.exception("ETL THẤT BẠI: %s", exc)
        logging.error("Không dùng bộ CSV mới nếu etl_quality_report.json không có run_status='success'.")
        return 1
