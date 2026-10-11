"""Typed containers for data passed between ETL stages."""
from dataclasses import dataclass
from typing import Any

import pandas as pd

@dataclass
class SourceData:
    customers: pd.DataFrame
    items: pd.DataFrame
    payments: pd.DataFrame
    reviews: pd.DataFrame
    orders: pd.DataFrame
    products: pd.DataFrame
    sellers: pd.DataFrame
    translation: pd.DataFrame
    dummy: pd.DataFrame
    geo_centroids: pd.DataFrame

@dataclass
class DimensionData:
    dim_customer: pd.DataFrame
    dim_product: pd.DataFrame
    dim_seller: pd.DataFrame
    dim_time: pd.DataFrame
    customer_sk_map: pd.DataFrame
    product_sk_map: pd.DataFrame
    seller_sk_map: pd.DataFrame
    orders: pd.DataFrame
    reviews: pd.DataFrame
    review_summary: pd.DataFrame
    date_to_sk: pd.Series

@dataclass
class FactData:
    fact_orders: pd.DataFrame
    fact_sales: pd.DataFrame
    fact_payments: pd.DataFrame
    orders_en: pd.DataFrame
    negative_delivery_count: int
