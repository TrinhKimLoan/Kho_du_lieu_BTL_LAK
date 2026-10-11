"""Category-level mapping between Olist English categories and DummyJSON categories.

Mappings are contextual proxies, not individual product matches.
"""
from typing import Any

import numpy as np
import pandas as pd

from .config import CATEGORY_MAPPING

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
