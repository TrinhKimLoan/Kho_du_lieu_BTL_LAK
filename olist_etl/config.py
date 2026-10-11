"""Project paths and business configuration for Olist + DummyJSON ETL."""
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
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

