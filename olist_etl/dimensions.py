"""Build the four dimensions and prepare order/review timestamps for the facts."""
from typing import Any

import numpy as np
import pandas as pd

from .config import ORDER_DATE_COLUMNS, PRODUCT_MEASURE_COLUMNS
from .mapping import build_category_mapping
from .models import DimensionData, SourceData
from .utils import (
    assert_unique_key,
    make_surrogate_dimension,
    merge_many_to_one_checked,
)

def build_dimensions(
    sources: SourceData,
    quality: dict[str, Any],
    join_audit: list[dict[str, Any]],
) -> DimensionData:
    customers = sources.customers
    items = sources.items
    reviews = sources.reviews
    orders = sources.orders
    products = sources.products
    sellers = sources.sellers
    translation = sources.translation
    dummy = sources.dummy
    geo_centroids = sources.geo_centroids

    # D. Aggregate geolocation by zip prefix before dimension joins.
    customer_source = customers.copy()
    customer_source["customer_city"] = customer_source["customer_city"].astype("string").str.strip().str.title()
    customer_source["customer_state"] = customer_source["customer_state"].astype("string").str.strip().str.upper()
    customer_source = customer_source.rename(columns={"customer_zip_code_prefix": "zip_prefix"})
    customer_geo = merge_many_to_one_checked(
        customer_source, geo_centroids, on="zip_prefix", label="Dim_Customer -> geolocation centroid", audit=join_audit
    )
    customer_geo["has_geolocation"] = customer_geo["geo_latitude"].notna() & customer_geo["geo_longitude"].notna()
    dim_customer = make_surrogate_dimension(
        customer_geo[["customer_id", "customer_unique_id", "zip_prefix", "customer_city", "customer_state", "geo_latitude", "geo_longitude", "geo_coordinate_rows", "has_geolocation"]],
        "customer_id", "customer_sk", "Dim_Customer",
    )
    dim_customer = dim_customer.rename(columns={"zip_prefix": "customer_zip_code_prefix", "geo_latitude": "customer_latitude", "geo_longitude": "customer_longitude", "geo_coordinate_rows": "zip_geo_coordinate_rows"})
    customer_sk_map = dim_customer[["customer_id", "customer_sk"]]

    seller_source = sellers.copy()
    seller_source["seller_city"] = seller_source["seller_city"].astype("string").str.strip().str.title()
    seller_source["seller_state"] = seller_source["seller_state"].astype("string").str.strip().str.upper()
    seller_source = seller_source.rename(columns={"seller_zip_code_prefix": "zip_prefix"})
    seller_geo = merge_many_to_one_checked(
        seller_source, geo_centroids, on="zip_prefix", label="Dim_Seller -> geolocation centroid", audit=join_audit
    )
    seller_geo["has_geolocation"] = seller_geo["geo_latitude"].notna() & seller_geo["geo_longitude"].notna()
    dim_seller = make_surrogate_dimension(
        seller_geo[["seller_id", "zip_prefix", "seller_city", "seller_state", "geo_latitude", "geo_longitude", "geo_coordinate_rows", "has_geolocation"]],
        "seller_id", "seller_sk", "Dim_Seller",
    )
    dim_seller = dim_seller.rename(columns={"zip_prefix": "seller_zip_code_prefix", "geo_latitude": "seller_latitude", "geo_longitude": "seller_longitude", "geo_coordinate_rows": "zip_geo_coordinate_rows"})
    seller_sk_map = dim_seller[["seller_id", "seller_sk"]]

    # E. Translate Olist category and enrich by a defensible category-level DummyJSON proxy.
    product_en = merge_many_to_one_checked(
        products, translation, on="product_category_name", label="Dim_Product: products -> category translation", audit=join_audit
    )
    product_en["category_translation_status"] = np.where(
        product_en["product_category_name"].isna(), "missing_source_category",
        np.where(product_en["product_category_name_english"].notna(), "translated", "untranslated")
    )
    product_en["category_olist"] = product_en["product_category_name_english"].fillna(product_en["product_category_name"])
    for col in PRODUCT_MEASURE_COLUMNS:
        product_en[col] = pd.to_numeric(product_en[col], errors="coerce")
        product_en[f"{col}_was_missing"] = product_en[col].isna()
        median_value = product_en[col].median(skipna=True)
        if pd.notna(median_value):
            product_en[col] = product_en[col].fillna(float(median_value))
    map_lookup = build_category_mapping(product_en, dummy)
    product_en = merge_many_to_one_checked(
        product_en,
        map_lookup,
        on=["category_olist", "category_translation_status"],
        label="Dim_Product -> category mapping lookup",
        audit=join_audit,
    )

    # Product dimension uses deterministic SKs generated from natural product IDs.
    product_source = product_en.sort_values("product_id", kind="stable").reset_index(drop=True).copy()
    product_source.insert(0, "product_sk", np.arange(1, len(product_source) + 1, dtype=np.int64))
    product_dim_columns = [
        "product_sk", "product_id", "product_category_name", "category_olist", "category_translation_status",
        "dummyjson_mapped_categories", "dummyjson_categories_found", "mapping_status", "mapping_confidence",
        "mapping_notes", "dummyjson_category_avg_rating", "dummyjson_products_count", "dummyjson_rated_products_count",
        *PRODUCT_MEASURE_COLUMNS, *[f"{c}_was_missing" for c in PRODUCT_MEASURE_COLUMNS],
    ]
    dim_product = product_source[product_dim_columns].copy()
    assert_unique_key(dim_product, ["product_id"], "Dim_Product")
    product_sk_map = dim_product[["product_id", "product_sk"]]

    # F. Parse event dates and aggregate review rows to one record per order.
    for col in ORDER_DATE_COLUMNS:
        orders[col] = pd.to_datetime(orders[col], errors="coerce")
    if orders["order_purchase_timestamp"].isna().any():
        count = int(orders["order_purchase_timestamp"].isna().sum())
        raise ValueError(f"Orders có {count} dòng thiếu/sai order_purchase_timestamp.")
    orders["order_status"] = orders["order_status"].fillna("unknown").astype("string").str.strip().str.lower()

    for col in ["review_creation_date", "review_answer_timestamp"]:
        reviews[col] = pd.to_datetime(reviews[col], errors="coerce")
    reviews["review_score"] = pd.to_numeric(reviews["review_score"], errors="coerce")
    invalid_review_score_mask = reviews["review_score"].notna() & ~reviews["review_score"].between(1, 5)
    invalid_review_score_count = int(invalid_review_score_mask.sum())
    reviews.loc[invalid_review_score_mask, "review_score"] = np.nan
    reviews["review_has_comment"] = (
        reviews["review_comment_title"].fillna("").astype("string").str.strip().ne("")
        | reviews["review_comment_message"].fillna("").astype("string").str.strip().ne("")
    )
    reviews_with_order_key = reviews.loc[reviews["order_id"].notna()].copy()
    review_order_ids_not_in_orders = int((~reviews_with_order_key["order_id"].isin(orders["order_id"])).sum())
    review_summary = reviews_with_order_key.groupby("order_id", as_index=False).agg(
        review_score_avg=("review_score", "mean"),
        review_count=("review_id", "size"),
        review_score_count=("review_score", "count"),
        review_comment_count=("review_has_comment", "sum"),
        review_creation_date=("review_creation_date", "min"),
        review_answer_timestamp=("review_answer_timestamp", "max"),
    )
    assert_unique_key(review_summary, ["order_id"], "review_summary")
    quality["review_quality"] = {
        "review_rows_after_exact_duplicate_removal": int(len(reviews)),
        "review_rows_missing_order_id": int(reviews["order_id"].isna().sum()),
        "review_scores_outside_1_to_5_set_to_na": invalid_review_score_count,
        "review_rows_whose_order_id_is_not_in_orders": review_order_ids_not_in_orders,
        "orders_with_at_least_one_review_summary": int(len(review_summary)),
        "rule": "reviews are aggregated by order_id; review_score_avg averages valid 1-5 scores only",
    }

    # G. Build continuous Dim_Time covering all order/review/shipping event dates.
    date_series: list[pd.Series] = [orders[c].dropna().dt.normalize() for c in ORDER_DATE_COLUMNS]
    date_series.append(pd.to_datetime(items["shipping_limit_date"], errors="coerce").dropna().dt.normalize())
    date_series.append(reviews["review_creation_date"].dropna().dt.normalize())
    date_series.append(reviews["review_answer_timestamp"].dropna().dt.normalize())
    all_event_dates = pd.concat(date_series, ignore_index=True)
    if all_event_dates.empty:
        raise ValueError("Không có ngày hợp lệ để tạo Dim_Time.")
    date_range = pd.date_range(start=all_event_dates.min(), end=all_event_dates.max(), freq="D")
    dim_time = pd.DataFrame({"full_date": date_range})
    dim_time["time_sk"] = dim_time["full_date"].dt.strftime("%Y%m%d").astype("int64")
    dim_time["year"] = dim_time["full_date"].dt.year.astype("int64")
    dim_time["quarter"] = dim_time["full_date"].dt.quarter.astype("int64")
    dim_time["month"] = dim_time["full_date"].dt.month.astype("int64")
    dim_time["month_name"] = dim_time["full_date"].dt.month_name()
    dim_time["day"] = dim_time["full_date"].dt.day.astype("int64")
    dim_time["day_of_week"] = dim_time["full_date"].dt.day_name()
    dim_time["day_of_week_num"] = dim_time["full_date"].dt.dayofweek.astype("int64")
    dim_time["is_weekend"] = dim_time["day_of_week_num"].isin([5, 6])
    assert_unique_key(dim_time, ["full_date"], "Dim_Time")
    date_to_sk = dim_time.set_index("full_date")["time_sk"]

    def time_sk_for(series: pd.Series) -> pd.Series:
        parsed = pd.to_datetime(series, errors="coerce")
        return parsed.dt.normalize().map(date_to_sk).astype("Int64")

    orders["purchase_time_sk"] = time_sk_for(orders["order_purchase_timestamp"])
    for col, source_col in [
        ("approved_time_sk", "order_approved_at"),
        ("carrier_time_sk", "order_delivered_carrier_date"),
        ("delivered_time_sk", "order_delivered_customer_date"),
        ("estimated_delivery_time_sk", "order_estimated_delivery_date"),
    ]:
        orders[col] = time_sk_for(orders[source_col])
    if orders["purchase_time_sk"].isna().any():
        raise ValueError("Có đơn hàng không tìm được purchase_time_sk trong Dim_Time.")

    return DimensionData(
        dim_customer=dim_customer,
        dim_product=dim_product,
        dim_seller=dim_seller,
        dim_time=dim_time,
        customer_sk_map=customer_sk_map,
        product_sk_map=product_sk_map,
        seller_sk_map=seller_sk_map,
        orders=orders,
        reviews=reviews,
        review_summary=review_summary,
        date_to_sk=date_to_sk,
    )


def time_sk_for(series: pd.Series, date_to_sk: pd.Series) -> pd.Series:
    """Map event timestamps to Dim_Time keys; preserves the original Int64 behavior."""
    parsed = pd.to_datetime(series, errors="coerce")
    return parsed.dt.normalize().map(date_to_sk).astype("Int64")
