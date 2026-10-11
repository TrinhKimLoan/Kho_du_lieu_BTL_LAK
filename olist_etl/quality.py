"""Create the category audit and the original ETL quality report."""
from typing import Any

import numpy as np
import pandas as pd

from .config import CATEGORY_MAPPING
from .models import DimensionData, FactData, SourceData
from .utils import assert_unique_key

def build_category_audit(dim_product: pd.DataFrame) -> pd.DataFrame:
    # K. Mapping audit: one row per Olist category and coverage by category/product counts.
    category_audit = dim_product.groupby(
        ["category_olist", "category_translation_status"], dropna=False, as_index=False
    ).agg(
        olist_product_count=("product_id", "nunique"),
        dummyjson_mapped_categories=("dummyjson_mapped_categories", "first"),
        dummyjson_categories_found=("dummyjson_categories_found", "first"),
        mapping_status=("mapping_status", "first"),
        mapping_confidence=("mapping_confidence", "first"),
        mapping_notes=("mapping_notes", "first"),
        dummyjson_products_count=("dummyjson_products_count", "first"),
        dummyjson_rated_products_count=("dummyjson_rated_products_count", "first"),
        dummyjson_category_avg_rating=("dummyjson_category_avg_rating", "first"),
    )
    category_audit["olist_product_share_pct"] = (category_audit["olist_product_count"] / max(len(dim_product), 1) * 100).round(2)
    category_audit = category_audit.sort_values(["mapping_status", "olist_product_count"], ascending=[True, False], kind="stable").reset_index(drop=True)
    return category_audit

def populate_quality_report(
    sources: SourceData,
    dimensions: DimensionData,
    facts: FactData,
    category_audit: pd.DataFrame,
    quality: dict[str, Any],
    join_audit: list[dict[str, Any]],
) -> dict[str, Any]:
    # L. Quality gates: row-grain keys, preservation of additive measures, dimensions and FK integrity.
    items = sources.items
    payments = sources.payments
    orders = dimensions.orders
    dummy = sources.dummy
    dim_customer = dimensions.dim_customer
    dim_product = dimensions.dim_product
    dim_seller = dimensions.dim_seller
    dim_time = dimensions.dim_time
    review_summary = dimensions.review_summary
    orders_en = facts.orders_en
    fact_orders = facts.fact_orders
    fact_sales = facts.fact_sales
    fact_payments = facts.fact_payments
    negative_delivery_count = facts.negative_delivery_count

    item_price_sum_source = float(items["price"].sum())
    item_price_sum_fact = float(fact_sales["item_price"].sum())
    freight_sum_source = float(items["freight_value"].sum())
    freight_sum_fact = float(fact_sales["freight_value"].sum())
    payment_sum_source = float(payments["payment_value"].sum())
    payment_sum_fact = float(fact_payments["payment_value"].sum())
    close_money = lambda a, b: bool(np.isclose(a, b, rtol=1e-9, atol=0.02))
    time_diffs = dim_time["full_date"].diff().dropna().dt.days
    checks = {
        "fact_sales_count_equals_deduplicated_item_source": len(fact_sales) == len(items),
        "fact_payments_count_equals_deduplicated_payment_source": len(fact_payments) == len(payments),
        "fact_orders_count_equals_deduplicated_order_source": len(fact_orders) == len(orders),
        "fact_sales_business_key_unique": not fact_sales.duplicated(["order_id", "order_item_id"]).any(),
        "fact_payments_business_key_unique": not fact_payments.duplicated(["order_id", "payment_sequential"]).any(),
        "fact_orders_order_id_unique": not fact_orders["order_id"].duplicated().any(),
        "item_price_sum_preserved": close_money(item_price_sum_source, item_price_sum_fact),
        "freight_sum_preserved": close_money(freight_sum_source, freight_sum_fact),
        "payment_value_sum_preserved_in_payment_fact": close_money(payment_sum_source, payment_sum_fact),
        "fact_sales_foreign_keys_complete": not fact_sales[["customer_sk", "product_sk", "seller_sk", "time_sk"]].isna().any().any(),
        "fact_payments_foreign_keys_complete": not fact_payments[["customer_sk", "time_sk"]].isna().any().any(),
        "fact_orders_customer_purchase_date_keys_complete": not fact_orders[["customer_sk", "purchase_time_sk"]].isna().any().any(),
        "fact_orders_all_present_event_dates_have_time_keys": all(
            orders_en[source_col].isna().equals(orders_en[key_col].isna())
            for source_col, key_col in [
                ("order_approved_at", "approved_time_sk"),
                ("order_delivered_carrier_date", "carrier_time_sk"),
                ("order_delivered_customer_date", "delivered_time_sk"),
                ("order_estimated_delivery_date", "estimated_delivery_time_sk"),
                ("review_creation_date", "review_creation_time_sk"),
                ("review_answer_timestamp", "review_answer_time_sk"),
            ]
        ),
        "dim_time_is_contiguous_daily_calendar": bool(time_diffs.eq(1).all()),
        "geolocation_joins_do_not_expand_customer_or_seller_rows": len(dim_customer) == len(sources.customers) and len(dim_seller) == len(sources.sellers),
        "review_summary_is_one_row_per_order": not review_summary["order_id"].duplicated().any(),
        "all_measured_left_joins_preserved_sums": all(
            passed for row in join_audit for passed in row.get("measure_sums_preserved", {}).values()
        ),
    }
    quality["checks"] = checks
    quality["join_audit"] = join_audit
    quality["measure_totals"] = {
        "source_item_price_sum": round(item_price_sum_source, 2),
        "fact_sales_item_price_sum": round(item_price_sum_fact, 2),
        "source_freight_sum": round(freight_sum_source, 2),
        "fact_sales_freight_sum": round(freight_sum_fact, 2),
        "source_payment_value_sum": round(payment_sum_source, 2),
        "fact_payments_payment_value_sum": round(payment_sum_fact, 2),
    }
    quality["output_rows"] = {
        "dim_customer": int(len(dim_customer)), "dim_product": int(len(dim_product)),
        "dim_seller": int(len(dim_seller)), "dim_time": int(len(dim_time)),
        "fact_sales": int(len(fact_sales)), "fact_payments": int(len(fact_payments)),
        "fact_orders": int(len(fact_orders)), "category_mapping_audit": int(len(category_audit)),
    }
    quality["geolocation_coverage"] = {
        "customers_with_coordinates": int(dim_customer["has_geolocation"].sum()),
        "customers_coordinate_coverage_pct": round(float(dim_customer["has_geolocation"].mean() * 100), 2) if len(dim_customer) else 0.0,
        "sellers_with_coordinates": int(dim_seller["has_geolocation"].sum()),
        "sellers_coordinate_coverage_pct": round(float(dim_seller["has_geolocation"].mean() * 100), 2) if len(dim_seller) else 0.0,
        "note": "Missing coordinates are allowed; city/state and postal prefix remain available."
    }
    quality["delivery_quality"] = {
        "orders_missing_actual_delivery_date": int(orders["order_delivered_customer_date"].isna().sum()),
        "orders_with_negative_delivery_duration_set_to_na": negative_delivery_count,
        "orders_with_delivery_delay_available": int(fact_orders["delivery_delay_days"].notna().sum()),
    }
    map_statuses = {"mapped_high", "mapped_partial"}
    usable_statuses = map_statuses
    n_categories = max(int(category_audit["category_olist"].nunique(dropna=True)), 1)
    mapped_categories_count = int(category_audit.loc[category_audit["mapping_status"].isin(map_statuses), "category_olist"].nunique(dropna=True))
    usable_cat_count = int(category_audit.loc[
        category_audit["mapping_status"].isin(usable_statuses) & category_audit["dummyjson_category_avg_rating"].notna(),
        "category_olist",
    ].nunique(dropna=True))
    mapped_product_count = int(dim_product["mapping_status"].isin(map_statuses).sum())
    usable_product_count = int((dim_product["mapping_status"].isin(usable_statuses) & dim_product["dummyjson_category_avg_rating"].notna()).sum())
    target_categories = {target for rule in CATEGORY_MAPPING.values() for target in rule["targets"]}
    available_categories = set(dummy["category"].dropna().unique())
    quality["category_mapping"] = {
        "unique_olist_categories_with_nonmissing_names": int(category_audit["category_olist"].nunique(dropna=True)),
        "categories_with_mapping_rule_and_target_present": mapped_categories_count,
        "category_mapping_rule_coverage_pct_by_category": round(mapped_categories_count / n_categories * 100, 2),
        "categories_with_usable_dummyjson_rating": usable_cat_count,
        "usable_rating_coverage_pct_by_category": round(usable_cat_count / n_categories * 100, 2),
        "olist_products_with_mapping_rule_pct": round(mapped_product_count / max(len(dim_product), 1) * 100, 2),
        "olist_products_with_usable_rating_enrichment_pct": round(usable_product_count / max(len(dim_product), 1) * 100, 2),
        "configured_dummyjson_categories_missing_from_raw_snapshot": sorted(target_categories - available_categories),
        "note": "Coverage describes proxy mapping, not exact product matches; partial mappings must be disclosed.",
    }
    quality["run_status"] = "success" if all(checks.values()) else "failed_quality_checks"
    quality["failed_checks"] = [name for name, passed in checks.items() if not passed]
    return quality
