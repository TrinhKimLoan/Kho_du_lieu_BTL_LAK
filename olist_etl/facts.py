"""Build the three fact tables at their original, explicitly defined grains."""
from typing import Any

import numpy as np
import pandas as pd

from .models import DimensionData, FactData, SourceData
from .dimensions import time_sk_for
from .utils import (
    assert_fk_complete,
    assert_unique_key,
    merge_many_to_one_checked,
    numeric_nonnegative,
)


def build_facts(
    sources: SourceData,
    dimensions: DimensionData,
    join_audit: list[dict[str, Any]],
) -> FactData:
    orders = dimensions.orders
    items = sources.items
    payments = sources.payments
    review_summary = dimensions.review_summary
    customer_sk_map = dimensions.customer_sk_map
    product_sk_map = dimensions.product_sk_map
    seller_sk_map = dimensions.seller_sk_map

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
    orders_en["review_creation_time_sk"] = time_sk_for(orders_en["review_creation_date"], dimensions.date_to_sk)
    orders_en["review_answer_time_sk"] = time_sk_for(orders_en["review_answer_timestamp"], dimensions.date_to_sk)
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

    return FactData(
        fact_orders=fact_orders,
        fact_sales=fact_sales,
        fact_payments=fact_payments,
        orders_en=orders_en,
        negative_delivery_count=negative_delivery_count,
    )
