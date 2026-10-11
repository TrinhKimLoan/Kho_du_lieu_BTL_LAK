"""Shared I/O, validation, cleaning, and join-audit helpers."""
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import RAW_DIR

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

def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

def write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, encoding="utf-8-sig")
    logging.info("Xuất %-33s : %s dòng", path.name, f"{len(df):,}")
