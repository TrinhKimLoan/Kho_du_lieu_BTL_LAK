"""Load, normalize, and validate raw Olist/DummyJSON source files."""
from typing import Any

import pandas as pd

from .config import INPUT_FILES, ORDER_DATE_COLUMNS, PRODUCT_MEASURE_COLUMNS, RAW_DIR
from .models import SourceData
from .utils import (
    assert_unique_key,
    clean_text_columns,
    drop_exact_duplicates,
    load_dummyjson,
    load_geolocation,
    read_csv_raw,
    require_columns,
    standardize_zip_prefix,
)

def load_and_validate_sources(quality: dict[str, Any]) -> SourceData:
    """Perform the same source-read, schema, cleanup, and key checks as the original ETL."""
    # A. Read 8 tabular Olist files and DummyJSON JSON. Geolocation is read separately for lower memory use.
    customers = read_csv_raw(INPUT_FILES["customers"])
    items = read_csv_raw(INPUT_FILES["items"])
    payments = read_csv_raw(INPUT_FILES["payments"])
    reviews = read_csv_raw(INPUT_FILES["reviews"])
    orders = read_csv_raw(INPUT_FILES["orders"])
    products = read_csv_raw(INPUT_FILES["products"])
    sellers = read_csv_raw(INPUT_FILES["sellers"])
    translation = read_csv_raw(INPUT_FILES["translation"])
    dummy = load_dummyjson(RAW_DIR / INPUT_FILES["dummyjson"])
    geo_centroids, geo_meta = load_geolocation(RAW_DIR / INPUT_FILES["geolocation"])
    quality["geolocation"] = geo_meta

    quality["source_rows_before_cleaning"] = {
        "customers": int(len(customers)), "geolocation_raw": geo_meta["raw_geolocation_rows"],
        "items": int(len(items)), "payments": int(len(payments)), "reviews": int(len(reviews)),
        "orders": int(len(orders)), "products": int(len(products)), "sellers": int(len(sellers)),
        "translation": int(len(translation)), "dummyjson_products": int(len(dummy)),
    }

    # B. Validate expected source schemas (Olist's nine CSVs, not only the seven used by the earlier script).
    require_columns(customers, ["customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state"], "Olist customers")
    require_columns(items, ["order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date", "price", "freight_value"], "Olist order items")
    require_columns(payments, ["order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"], "Olist payments")
    require_columns(reviews, ["review_id", "order_id", "review_score", "review_comment_title", "review_comment_message", "review_creation_date", "review_answer_timestamp"], "Olist reviews")
    require_columns(orders, ["order_id", "customer_id", "order_status", *ORDER_DATE_COLUMNS], "Olist orders")
    require_columns(products, ["product_id", "product_category_name", *PRODUCT_MEASURE_COLUMNS], "Olist products")
    require_columns(sellers, ["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"], "Olist sellers")
    require_columns(translation, ["product_category_name", "product_category_name_english"], "Olist category translation")

    customers = clean_text_columns(customers, ["customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state"])
    items = clean_text_columns(items, ["order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date"])
    payments = clean_text_columns(payments, ["order_id", "payment_sequential", "payment_type", "payment_installments"])
    reviews = clean_text_columns(reviews, ["review_id", "order_id", "review_comment_title", "review_comment_message"])
    orders = clean_text_columns(orders, ["order_id", "customer_id", "order_status"])
    products = clean_text_columns(products, ["product_id", "product_category_name"])
    sellers = clean_text_columns(sellers, ["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"])
    translation = clean_text_columns(translation, ["product_category_name", "product_category_name_english"])

    # C. Remove only exact row duplicates. Conflicting natural-key duplicates stop ETL.
    duplicate_removed: dict[str, int] = {}
    for key, frame in [
        ("customers", customers), ("items", items), ("payments", payments), ("reviews", reviews),
        ("orders", orders), ("products", products), ("sellers", sellers), ("translation", translation),
    ]:
        cleaned, removed = drop_exact_duplicates(frame, key)
        duplicate_removed[key] = removed
        if key == "customers": customers = cleaned
        elif key == "items": items = cleaned
        elif key == "payments": payments = cleaned
        elif key == "reviews": reviews = cleaned
        elif key == "orders": orders = cleaned
        elif key == "products": products = cleaned
        elif key == "sellers": sellers = cleaned
        elif key == "translation": translation = cleaned
    quality["exact_duplicate_rows_removed"] = duplicate_removed

    assert_unique_key(customers, ["customer_id"], "customers")
    if customers["customer_unique_id"].isna().any():
        raise ValueError(
            f"Customers có {int(customers['customer_unique_id'].isna().sum())} dòng thiếu customer_unique_id; "
            "không thể tính RFM tin cậy nếu không xác định được khách hàng thực."
        )
    assert_unique_key(items, ["order_id", "order_item_id"], "order_items")
    assert_unique_key(payments, ["order_id", "payment_sequential"], "order_payments")
    assert_unique_key(orders, ["order_id"], "orders")
    assert_unique_key(products, ["product_id"], "products")
    assert_unique_key(sellers, ["seller_id"], "sellers")
    assert_unique_key(translation, ["product_category_name"], "category_translation")
    # Reviews are intentionally not required to be unique by order_id/review_id:
    # several review rows can relate to one order and are aggregated below.

    # The original ETL standardizes these prefixes after source key validation and before dimension joins.
    customers["customer_zip_code_prefix"] = standardize_zip_prefix(customers["customer_zip_code_prefix"])
    sellers["seller_zip_code_prefix"] = standardize_zip_prefix(sellers["seller_zip_code_prefix"])

    return SourceData(
        customers=customers,
        items=items,
        payments=payments,
        reviews=reviews,
        orders=orders,
        products=products,
        sellers=sellers,
        translation=translation,
        dummy=dummy,
        geo_centroids=geo_centroids,
    )
