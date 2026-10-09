#!/usr/bin/env python3
"""Final ETL for Olist + DummyJSON: 3 facts + 4 dimensions.

Expected project structure:
  project_root/
    etl_olist_enrichment_final.py
    datalake/raw/
      olist_customers_dataset.csv
      olist_geolocation_dataset.csv
      olist_order_items_dataset.csv
      olist_order_payments_dataset.csv
      olist_order_reviews_dataset.csv
      olist_orders_dataset.csv
      olist_products_dataset.csv
      olist_sellers_dataset.csv
      product_category_name_translation.csv
      dummyjson_products_raw.json

Outputs (only committed when critical validations pass): datalake/processed/
  dim_customer.csv, dim_product.csv, dim_seller.csv, dim_time.csv,
  fact_sales.csv, fact_payments.csv, fact_orders.csv,
  category_mapping_audit.csv, etl_quality_report.json

Fact grains:
  Fact_Sales    : one row per (order_id, order_item_id)
  Fact_Payments : one row per (order_id, payment_sequential)
  Fact_Orders   : one row per order_id; order reviews are aggregated to this grain

The script expects DummyJSON to have been ingested into raw JSON separately.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "datalake" / "raw"
PROCESSED_DIR = BASE_DIR / "datalake" / "processed"
STAGING_DIR = PROCESSED_DIR / ".etl_staging"

INPUT_FILES = {
    "customers": "olist_customers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "items": "olist_order_items_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "translation": "product_category_name_translation.csv",
    "dummyjson": "dummyjson_products_raw.json",
}

ORDER_DATE_COLUMNS = [
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
]
PRODUCT_MEASURE_COLUMNS = [
    "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"
]
OUTPUT_CSVS = [
    "dim_customer.csv", "dim_product.csv", "dim_seller.csv", "dim_time.csv",
    "fact_sales.csv", "fact_payments.csv", "fact_orders.csv", "category_mapping_audit.csv"
]

# Deliberately conservative semantic mapping. Targets must be category slugs that
# actually exist in DummyJSON. A mapping means "use as contextual proxy", not that
# the two source categories are identical and not that individual products match.
CATEGORY_MAPPING: dict[str, dict[str, Any]] = {
    "perfumery": {
        "targets": ["fragrances"], "confidence": "high",
        "notes": "Close category-level correspondence: perfumery and fragrances."
    },
    "furniture_decor": {
        "targets": ["home-decoration"], "confidence": "high",
        "notes": "Close correspondence for decorative home products; not every Olist SKU is identical."
    },
    "furniture_bedroom": {
        "targets": ["furniture"], "confidence": "partial",
        "notes": "Bedroom furniture is represented by the broader DummyJSON furniture category."
    },
    "furniture_living_room": {
        "targets": ["furniture"], "confidence": "partial",
        "notes": "Living-room furniture is represented by the broader DummyJSON furniture category."
    },
    "furniture_mattress_and_upholstery": {
        "targets": ["furniture"], "confidence": "partial",
        "notes": "Related to furniture but more specialized than the DummyJSON category."
    },
    "office_furniture": {
        "targets": ["furniture"], "confidence": "partial",
        "notes": "Related category proxy; office furniture is not identical to all furniture."
    },
    "health_beauty": {
        "targets": ["beauty", "skin-care"], "confidence": "partial",
        "notes": "Broad source category; the targets represent only part of health and beauty."
    },
    "telephony": {
        "targets": ["smartphones"], "confidence": "partial",
        "notes": "Phone-related proxy only; telephony can include products outside smartphones."
    },
    "computers": {
        "targets": ["laptops"], "confidence": "partial",
        "notes": "Laptop rating is a proxy for a subset of computer products."
    },
    "tablets_printing_image": {
        "targets": ["tablets"], "confidence": "partial",
        "notes": "Only the tablet part is represented; printing and imaging products are not."
    },
    "fashion_shoes": {
        "targets": ["mens-shoes", "womens-shoes"], "confidence": "partial",
        "notes": "Shoes proxy; DummyJSON does not necessarily represent every Olist shoe segment."
    },
    "fashion_bags_accessories": {
        "targets": ["womens-bags", "sunglasses", "womens-jewellery"], "confidence": "partial",
        "notes": "Selected accessories only; the mapping does not cover every bag/accessory type."
    },
    "watches_gifts": {
        "targets": ["mens-watches", "womens-watches"], "confidence": "partial",
        "notes": "Watches are represented; the gifts portion is not."
    },
    "fashion_male_clothing": {
        "targets": ["mens-shirts"], "confidence": "partial",
        "notes": "Shirts represent only part of men's clothing."
    },
    "fashio_female_clothing": {
        "targets": ["womens-dresses", "tops"], "confidence": "partial",
        "notes": "Dresses/tops represent only part of women's clothing."
    },
    "fashion_sport": {
        "targets": ["sports-accessories"], "confidence": "partial",
        "notes": "Sports accessories are a proxy for only part of sporting apparel/products."
    },
    "sports_leisure": {
        "targets": ["sports-accessories"], "confidence": "partial",
        "notes": "Partial sports proxy; leisure products may be broader."
    },
    "auto": {
        "targets": ["vehicle", "motorcycle"], "confidence": "partial",
        "notes": "Vehicle/motorcycle proxy; not all automotive products are covered."
    },
    "food": {
        "targets": ["groceries"], "confidence": "partial",
        "notes": "Broad food-to-groceries proxy; category definitions may differ."
    },
    "food_drink": {
        "targets": ["groceries"], "confidence": "partial",
        "notes": "Grocery proxy; the source food/drink range may be broader."
    },
    "home_comfort_2": {
        "targets": ["home-decoration"], "confidence": "partial",
        "notes": "Broad home-related proxy, not an exact match."
    },
    "home_confort": {
        "targets": ["home-decoration"], "confidence": "partial",
        "notes": "Likely home-comfort spelling variant; source translation should be reviewed."
    },
    "housewares": {
        "targets": ["kitchen-accessories"], "confidence": "partial",
        "notes": "Kitchen accessories cover only a subset of housewares."
    },
    "la_cuisine": {
        "targets": ["kitchen-accessories"], "confidence": "partial",
        "notes": "Kitchen-related proxy category."
    },
    "small_appliances_home_oven_and_coffee": {
        "targets": ["kitchen-accessories"], "confidence": "partial",
        "notes": "Kitchen accessories are an approximate proxy, not an exact appliance category."
    },
}


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S")


def require_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(
            f"Không tìm thấy file: {path}\n"
            "Hãy đặt đủ 9 CSV Olist và dummyjson_products_raw.json trong datalake/raw/."
        )


def read_csv_raw(filename: str) -> pd.DataFrame:
    path = RAW_DIR / filename
    require_file(path)
    df = pd.read_csv(path, dtype="string", keep_default_na=True, low_memory=False)
    df.columns = [str(c).strip() for c in df.columns]
    logging.info("Đọc %-43s : %s dòng, %s cột", filename, f"{len(df):,}", len(df.columns))
    return df


def require_columns(df: pd.DataFrame, required: list[str], table_name: str) -> None:
    missing = sorted(set(required) - set(df.columns))
    if missing:
        raise ValueError(f"{table_name} thiếu các cột bắt buộc: {missing}")


def clean_text_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if col in out.columns:
            out[col] = out[col].astype("string").str.strip().replace("", pd.NA)
    return out


def standardize_zip_prefix(series: pd.Series) -> pd.Series:
    """Keep zip prefixes as strings and normalize to five digits for safe joins."""
    values = series.astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    values = values.replace("", pd.NA)
    numeric_like = values.str.fullmatch(r"\d+").fillna(False)
    values.loc[numeric_like] = values.loc[numeric_like].str.zfill(5)
    return values


def drop_exact_duplicates(df: pd.DataFrame, table_name: str) -> tuple[pd.DataFrame, int]:
    before = len(df)
    out = df.drop_duplicates().copy().reset_index(drop=True)
    removed = before - len(out)
    if removed:
        logging.warning("%s: đã loại %s dòng trùng hoàn toàn ở nguồn.", table_name, f"{removed:,}")
    return out, int(removed)


def assert_unique_key(df: pd.DataFrame, columns: list[str], table_name: str) -> None:
    if df[columns].isna().any(axis=1).any():
        count = int(df[columns].isna().any(axis=1).sum())
        raise ValueError(f"{table_name}: có {count} dòng thiếu khóa {columns}.")
    dup = df.duplicated(subset=columns, keep=False)
    if dup.any():
        sample = df.loc[dup, columns].head(8).to_dict("records")
        raise ValueError(
            f"{table_name}: khóa {columns} không duy nhất ({int(dup.sum())} dòng thuộc nhóm trùng). "
            f"Ví dụ: {sample}. Không tự động xóa vì có thể làm mất giao dịch hợp lệ."
        )


def numeric_nonnegative(df: pd.DataFrame, col: str, table_name: str, allow_na: bool = False) -> pd.Series:
    values = pd.to_numeric(df[col], errors="coerce")
    if not allow_na and values.isna().any():
        raise ValueError(f"{table_name}.{col}: có {int(values.isna().sum())} giá trị thiếu/không phải số.")
    negative = values.notna() & (values < 0)
    if negative.any():
        raise ValueError(f"{table_name}.{col}: có {int(negative.sum())} giá trị âm cần kiểm tra.")
    return values


def merge_many_to_one_checked(
    left: pd.DataFrame,
    right: pd.DataFrame,
    on: str | list[str],
    label: str,
    audit: list[dict[str, Any]],
    preserve_measure_cols: list[str] | None = None,
) -> pd.DataFrame:
    """Perform a left many-to-one join; log row counts, matches and measure sums."""
    preserve_measure_cols = preserve_measure_cols or []
    before_rows = len(left)
    before_sums = {
        c: float(pd.to_numeric(left[c], errors="coerce").sum())
        for c in preserve_measure_cols if c in left.columns
    }
    merged = left.merge(right, on=on, how="left", validate="many_to_one", indicator="__join_status__")
    after_rows = len(merged)
    matched = int((merged["__join_status__"] == "both").sum())
    unmatched = int((merged["__join_status__"] == "left_only").sum())
    after_sums = {
        c: float(pd.to_numeric(merged[c], errors="coerce").sum())
        for c in preserve_measure_cols if c in merged.columns
    }
    sums_preserved = {
        c: bool(np.isclose(before_sums[c], after_sums[c], rtol=1e-9, atol=0.02))
        for c in before_sums
    }
    record = {
        "join": label,
        "left_rows_before": int(before_rows),
        "right_rows": int(len(right)),
        "left_rows_after": int(after_rows),
        "matched_left_rows": matched,
        "unmatched_left_rows": unmatched,
        "measure_sums_before": {k: round(v, 4) for k, v in before_sums.items()},
        "measure_sums_after": {k: round(v, 4) for k, v in after_sums.items()},
        "measure_sums_preserved": sums_preserved,
        "left_join_row_count_preserved": after_rows == before_rows,
    }
    audit.append(record)
    logging.info("JOIN %-43s %s -> %s rows | khớp=%s | không khớp=%s", label, f"{before_rows:,}", f"{after_rows:,}", f"{matched:,}", f"{unmatched:,}")
    if after_rows != before_rows:
        raise ValueError(f"{label}: số dòng thay đổi sau LEFT JOIN ({before_rows} -> {after_rows}).")
    return merged.drop(columns="__join_status__")


def assert_fk_complete(df: pd.DataFrame, columns: list[str], table_name: str) -> None:
    for col in columns:
        bad = df[col].isna()
        if bad.any():
            candidates = [c for c in ["order_id", "order_item_id", "product_id", "seller_id", "customer_id"] if c in df.columns]
            sample = df.loc[bad, candidates].head(8).to_dict("records") if candidates else []
            raise ValueError(f"{table_name}: {int(bad.sum())} dòng thiếu FK {col} sau JOIN. Ví dụ: {sample}")


def make_surrogate_dimension(source: pd.DataFrame, natural_key: str, surrogate_key: str, table_name: str) -> pd.DataFrame:
    assert_unique_key(source, [natural_key], table_name)
    out = source.sort_values(natural_key, kind="stable").reset_index(drop=True).copy()
    out.insert(0, surrogate_key, np.arange(1, len(out) + 1, dtype=np.int64))
    return out


def load_dummyjson(path: Path) -> pd.DataFrame:
    require_file(path)
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if isinstance(payload, dict) and isinstance(payload.get("products"), list):
        records = payload["products"]
        reported_total = payload.get("total")
    elif isinstance(payload, list):
        records, reported_total = payload, None
    else:
        raise ValueError("dummyjson_products_raw.json phải là danh sách sản phẩm hoặc object có khóa 'products'.")
    if not records:
        raise ValueError("DummyJSON raw không có sản phẩm nào.")
    if reported_total is not None and int(reported_total) != len(records):
        raise ValueError(
            f"DummyJSON JSON chỉ có {len(records)} sản phẩm nhưng API báo total={reported_total}. "
            "Hãy nạp lại bằng https://dummyjson.com/products?limit=0."
        )
    df = pd.DataFrame(records)
    require_columns(df, ["id", "category", "rating"], "DummyJSON products")
    df["category"] = df["category"].astype("string").str.strip().str.lower()
    df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
    invalid = df["rating"].notna() & ~df["rating"].between(0, 5)
    if invalid.any():
        logging.warning("DummyJSON: %s Rating ngoài khoảng 0–5 được đặt NA.", int(invalid.sum()))
        df.loc[invalid, "rating"] = np.nan
    if df["id"].isna().any() or df["id"].duplicated(keep=False).any():
        raise ValueError("DummyJSON có id bị thiếu hoặc trùng; kiểm tra file raw trước khi chạy ETL.")
    logging.info("DummyJSON products: %s sản phẩm; %s category", f"{len(df):,}", df["category"].nunique())
    return df


def load_geolocation(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Reduce the large geolocation source to one centroid per zip prefix before joining."""
    require_file(path)
    usecols = ["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng"]
    geo = pd.read_csv(
        path,
        usecols=usecols,
        dtype={"geolocation_zip_code_prefix": "string"},
        low_memory=False,
    )
    geo.columns = [str(c).strip() for c in geo.columns]
    geo["zip_prefix"] = standardize_zip_prefix(geo["geolocation_zip_code_prefix"])
    geo["latitude"] = pd.to_numeric(geo["geolocation_lat"], errors="coerce")
    geo["longitude"] = pd.to_numeric(geo["geolocation_lng"], errors="coerce")
    valid = (
        geo["zip_prefix"].notna()
        & geo["latitude"].between(-90, 90)
        & geo["longitude"].between(-180, 180)
    )
    invalid_rows = int((~valid).sum())
    geo = geo.loc[valid, ["zip_prefix", "latitude", "longitude"]]
    # Olist has multiple coordinates for a postal prefix. Aggregate before joining
    # so one customer/seller row cannot multiply.
    centroids = geo.groupby("zip_prefix", as_index=False).agg(
        geo_latitude=("latitude", "mean"),
        geo_longitude=("longitude", "mean"),
        geo_coordinate_rows=("latitude", "size"),
    )
    meta = {
        "raw_geolocation_rows": int(len(geo) + invalid_rows),
        "invalid_geolocation_rows_excluded": invalid_rows,
        "unique_zip_prefix_centroids": int(len(centroids)),
        "aggregation": "mean latitude/longitude per normalized 5-digit zip prefix",
    }
    logging.info("Geolocation: %s raw rows -> %s zip-prefix centroids; loại %s dòng không hợp lệ", f"{meta['raw_geolocation_rows']:,}", f"{len(centroids):,}", f"{invalid_rows:,}")
    return centroids, meta


def category_mapping_details(category_value: Any, translation_status: str, dummy: pd.DataFrame) -> dict[str, Any]:
    if pd.isna(category_value) or not str(category_value).strip():
        return {
            "dummyjson_mapped_categories": "", "dummyjson_categories_found": "",
            "mapping_status": "missing_olist_category", "mapping_confidence": "none",
            "mapping_notes": "Olist source category is missing.",
            "dummyjson_category_avg_rating": np.nan, "dummyjson_products_count": 0,
            "dummyjson_rated_products_count": 0,
        }
    category = str(category_value).strip().lower()
    if translation_status != "translated":
        return {
            "dummyjson_mapped_categories": "", "dummyjson_categories_found": "",
            "mapping_status": "unmapped_untranslated", "mapping_confidence": "none",
            "mapping_notes": "No usable English translation; mapping was intentionally not guessed.",
            "dummyjson_category_avg_rating": np.nan, "dummyjson_products_count": 0,
            "dummyjson_rated_products_count": 0,
        }
    rule = CATEGORY_MAPPING.get(category)
    if rule is None:
        return {
            "dummyjson_mapped_categories": "", "dummyjson_categories_found": "",
            "mapping_status": "unmapped_no_reliable_match", "mapping_confidence": "none",
            "mapping_notes": "No sufficiently defensible category proxy is configured.",
            "dummyjson_category_avg_rating": np.nan, "dummyjson_products_count": 0,
            "dummyjson_rated_products_count": 0,
        }
    targets = rule["targets"]
    subset = dummy[dummy["category"].isin(targets)]
    ratings = subset["rating"].dropna()
    found = sorted(subset["category"].dropna().unique().tolist())
    status = "mapped_high" if rule["confidence"] == "high" else "mapped_partial"
    if not found:
        status = "mapped_targets_missing_in_snapshot"
    return {
        "dummyjson_mapped_categories": ", ".join(targets),
        "dummyjson_categories_found": ", ".join(found),
        "mapping_status": status,
        "mapping_confidence": rule["confidence"],
        "mapping_notes": rule["notes"],
        "dummyjson_category_avg_rating": round(float(ratings.mean()), 4) if not ratings.empty else np.nan,
        "dummyjson_products_count": int(len(subset)),
        "dummyjson_rated_products_count": int(len(ratings)),
    }


def build_category_mapping(products_en: pd.DataFrame, dummy: pd.DataFrame) -> pd.DataFrame:
    categories = products_en[["category_olist", "category_translation_status"]].drop_duplicates().reset_index(drop=True)
    records = [category_mapping_details(row.category_olist, row.category_translation_status, dummy) for row in categories.itertuples(index=False)]
    return pd.concat([categories, pd.DataFrame(records)], axis=1)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)


def write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, encoding="utf-8-sig")
    logging.info("Xuất %-33s : %s dòng", path.name, f"{len(df):,}")


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

        # D. Aggregate geolocation by zip prefix before dimension joins.
        customers["customer_zip_code_prefix"] = standardize_zip_prefix(customers["customer_zip_code_prefix"])
        sellers["seller_zip_code_prefix"] = standardize_zip_prefix(sellers["seller_zip_code_prefix"])
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

        # H. Build Fact_Orders (one row/order), including actual Olist reviews and delivery measures.
        orders_en = merge_many_to_one_checked(
            orders, customer_sk_map, on="customer_id", label="Fact_Orders -> Dim_Customer", audit=join_audit
        )
        missing_customer_orders = orders_en["customer_sk"].isna()
        if missing_customer_orders.any():
            sample = orders_en.loc[missing_customer_orders, ["order_id", "customer_id"]].head(8).to_dict("records")
            raise ValueError(f"Fact_Orders có order không khớp customer. Ví dụ: {sample}")
        orders_en = merge_many_to_one_checked(
            orders_en, review_summary, on="order_id", label="Fact_Orders -> aggregated Olist reviews", audit=join_audit
        )
        orders_en["review_creation_time_sk"] = time_sk_for(orders_en["review_creation_date"])
        orders_en["review_answer_time_sk"] = time_sk_for(orders_en["review_answer_timestamp"])
        orders_en["review_count"] = orders_en["review_count"].fillna(0).astype("int64")
        orders_en["review_score_count"] = orders_en["review_score_count"].fillna(0).astype("int64")
        orders_en["review_comment_count"] = orders_en["review_comment_count"].fillna(0).astype("int64")

        delivery_days = (orders_en["order_delivered_customer_date"] - orders_en["order_purchase_timestamp"]).dt.total_seconds() / 86400.0
        negative_delivery_count = int((delivery_days < 0).sum())
        delivery_days = delivery_days.where(delivery_days >= 0, np.nan)
        delivery_delay_days = (orders_en["order_delivered_customer_date"] - orders_en["order_estimated_delivery_date"]).dt.total_seconds() / 86400.0
        # Nullable boolean: unknown for undelivered orders / missing estimated date.
        is_late_delivery = delivery_delay_days.gt(0).astype("boolean")
        is_late_delivery = is_late_delivery.mask(delivery_delay_days.isna(), pd.NA)
        fact_orders = pd.DataFrame({
            "order_id": orders_en["order_id"],
            "customer_sk": orders_en["customer_sk"].astype("int64"),
            "purchase_time_sk": orders_en["purchase_time_sk"].astype("int64"),
            "approved_time_sk": orders_en["approved_time_sk"].astype("Int64"),
            "carrier_time_sk": orders_en["carrier_time_sk"].astype("Int64"),
            "delivered_time_sk": orders_en["delivered_time_sk"].astype("Int64"),
            "estimated_delivery_time_sk": orders_en["estimated_delivery_time_sk"].astype("Int64"),
            "review_creation_time_sk": orders_en["review_creation_time_sk"].astype("Int64"),
            "review_answer_time_sk": orders_en["review_answer_time_sk"].astype("Int64"),
            "order_status": orders_en["order_status"],
            "order_purchase_timestamp": orders_en["order_purchase_timestamp"],
            "order_approved_at": orders_en["order_approved_at"],
            "order_delivered_carrier_date": orders_en["order_delivered_carrier_date"],
            "order_delivered_customer_date": orders_en["order_delivered_customer_date"],
            "order_estimated_delivery_date": orders_en["order_estimated_delivery_date"],
            "delivery_days": delivery_days.round(3),
            "delivery_delay_days": delivery_delay_days.round(3),
            "is_delivered": orders_en["order_delivered_customer_date"].notna(),
            "is_cancelled": orders_en["order_status"].eq("canceled"),
            "is_late_delivery": is_late_delivery,
            "review_score_avg": pd.to_numeric(orders_en["review_score_avg"], errors="coerce").round(3),
            "review_count": orders_en["review_count"],
            "review_score_count": orders_en["review_score_count"],
            "review_comment_count": orders_en["review_comment_count"],
            "review_creation_date": orders_en["review_creation_date"],
            "review_answer_timestamp": orders_en["review_answer_timestamp"],
        })
        fact_orders["has_review"] = fact_orders["review_count"].gt(0)
        fact_orders["has_review_comment"] = fact_orders["review_comment_count"].gt(0)
        assert_unique_key(fact_orders, ["order_id"], "Fact_Orders")
        assert_fk_complete(fact_orders, ["customer_sk", "purchase_time_sk"], "Fact_Orders")

        # I. Build Fact_Sales (one row/order item); preserve measures through every join.
        items["order_item_id"] = pd.to_numeric(items["order_item_id"], errors="coerce")
        if items["order_item_id"].isna().any():
            raise ValueError("Order items có order_item_id thiếu/không hợp lệ.")
        items["order_item_id"] = items["order_item_id"].astype("int64")
        items["price"] = numeric_nonnegative(items, "price", "order_items")
        items["freight_value"] = numeric_nonnegative(items, "freight_value", "order_items")
        items["shipping_limit_date"] = pd.to_datetime(items["shipping_limit_date"], errors="coerce")
        sales = merge_many_to_one_checked(
            items, orders_en[["order_id", "customer_id", "order_status", "purchase_time_sk"]],
            on="order_id", label="Fact_Sales: items -> orders", audit=join_audit,
            preserve_measure_cols=["price", "freight_value"],
        )
        if sales["customer_id"].isna().any():
            raise ValueError(f"Fact_Sales: có {int(sales['customer_id'].isna().sum())} item không khớp orders.")
        sales = merge_many_to_one_checked(
            sales, customer_sk_map, on="customer_id", label="Fact_Sales -> Dim_Customer", audit=join_audit,
            preserve_measure_cols=["price", "freight_value"],
        )
        sales = merge_many_to_one_checked(
            sales, product_sk_map, on="product_id", label="Fact_Sales -> Dim_Product", audit=join_audit,
            preserve_measure_cols=["price", "freight_value"],
        )
        sales = merge_many_to_one_checked(
            sales, seller_sk_map, on="seller_id", label="Fact_Sales -> Dim_Seller", audit=join_audit,
            preserve_measure_cols=["price", "freight_value"],
        )
        sales = sales.rename(columns={"purchase_time_sk": "time_sk"})
        assert_fk_complete(sales, ["customer_sk", "product_sk", "seller_sk", "time_sk"], "Fact_Sales")
        fact_sales = sales[[
            "order_id", "order_item_id", "customer_sk", "product_sk", "seller_sk", "time_sk",
            "order_status", "price", "freight_value", "shipping_limit_date",
        ]].rename(columns={"price": "item_price"}).copy()
        for col in ["customer_sk", "product_sk", "seller_sk", "time_sk"]:
            fact_sales[col] = fact_sales[col].astype("int64")
        fact_sales["item_price"] = fact_sales["item_price"].round(2)
        fact_sales["freight_value"] = fact_sales["freight_value"].round(2)
        assert_unique_key(fact_sales, ["order_id", "order_item_id"], "Fact_Sales")

        # J. Build Fact_Payments at the source payment-record grain; never copy order-level totals onto items.
        payments["payment_sequential"] = pd.to_numeric(payments["payment_sequential"], errors="coerce")
        payments["payment_installments"] = pd.to_numeric(payments["payment_installments"], errors="coerce")
        if payments["payment_sequential"].isna().any():
            raise ValueError("Payments có payment_sequential thiếu/không hợp lệ.")
        payments["payment_sequential"] = payments["payment_sequential"].astype("int64")
        payments["payment_value"] = numeric_nonnegative(payments, "payment_value", "order_payments")
        payments["payment_type"] = payments["payment_type"].fillna("unknown").astype("string").str.strip().str.lower()
        payment_en = merge_many_to_one_checked(
            payments, orders_en[["order_id", "customer_id", "order_status", "purchase_time_sk"]],
            on="order_id", label="Fact_Payments: payments -> orders", audit=join_audit,
            preserve_measure_cols=["payment_value"],
        )
        if payment_en["customer_id"].isna().any():
            raise ValueError(f"Fact_Payments: có {int(payment_en['customer_id'].isna().sum())} payment không khớp orders.")
        payment_en = merge_many_to_one_checked(
            payment_en, customer_sk_map, on="customer_id", label="Fact_Payments -> Dim_Customer", audit=join_audit,
            preserve_measure_cols=["payment_value"],
        )
        payment_en = payment_en.rename(columns={"purchase_time_sk": "time_sk"})
        assert_fk_complete(payment_en, ["customer_sk", "time_sk"], "Fact_Payments")
        payment_en = payment_en.sort_values(["order_id", "payment_sequential"], kind="stable").reset_index(drop=True)
        payment_en.insert(0, "payment_sk", np.arange(1, len(payment_en) + 1, dtype=np.int64))
        fact_payments = payment_en[[
            "payment_sk", "order_id", "payment_sequential", "customer_sk", "time_sk", "order_status",
            "payment_type", "payment_installments", "payment_value",
        ]].copy()
        fact_payments["customer_sk"] = fact_payments["customer_sk"].astype("int64")
        fact_payments["time_sk"] = fact_payments["time_sk"].astype("int64")
        fact_payments["payment_value"] = fact_payments["payment_value"].round(2)
        assert_unique_key(fact_payments, ["order_id", "payment_sequential"], "Fact_Payments")

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

        # L. Quality gates: row-grain keys, preservation of additive measures, dimensions and FK integrity.
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
            "geolocation_joins_do_not_expand_customer_or_seller_rows": len(dim_customer) == len(customers) and len(dim_seller) == len(sellers),
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

        # Save the audit to staging first. If any gate fails, don't replace final CSVs.
        write_csv(category_audit, STAGING_DIR / "category_mapping_audit.csv")
        if quality["failed_checks"]:
            quality["message"] = "Không commit các bảng đầu ra vì một hoặc nhiều kiểm tra chất lượng thất bại. Xem checks/join_audit."
            write_json(PROCESSED_DIR / "etl_quality_report.json", quality)
            raise ValueError(f"Quality gates failed: {quality['failed_checks']}")

        output_tables = {
            "dim_customer.csv": dim_customer,
            "dim_product.csv": dim_product,
            "dim_seller.csv": dim_seller,
            "dim_time.csv": dim_time,
            "fact_sales.csv": fact_sales,
            "fact_payments.csv": fact_payments,
            "fact_orders.csv": fact_orders,
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
        logging.info("Dimensions: Customer=%s | Product=%s | Seller=%s | Time=%s", f"{len(dim_customer):,}", f"{len(dim_product):,}", f"{len(dim_seller):,}", f"{len(dim_time):,}")
        logging.info("Facts: Sales=%s | Payments=%s | Orders=%s", f"{len(fact_sales):,}", f"{len(fact_payments):,}", f"{len(fact_orders):,}")
        logging.info("Tổng item_price=%.2f | freight=%.2f | payment_value=%.2f", item_price_sum_fact, freight_sum_fact, payment_sum_fact)
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


if __name__ == "__main__":
    sys.exit(main())
