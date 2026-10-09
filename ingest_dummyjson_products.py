#!/usr/bin/env python3
"""Fetch all DummyJSON products and save the raw API response without transforming it."""
from __future__ import annotations
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_URL = "https://dummyjson.com/products?limit=0"
BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "datalake" / "raw"
OUTPUT = RAW_DIR / "dummyjson_products_raw.json"


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(API_URL, headers={"User-Agent": "Olist-DummyJSON-ETL-Student-Project/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            if response.status != 200:
                raise RuntimeError(f"API trả về HTTP {response.status}")
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"Không tải được DummyJSON: {exc}", file=sys.stderr)
        return 1

    products = payload.get("products") if isinstance(payload, dict) else None
    total = payload.get("total") if isinstance(payload, dict) else None
    if not isinstance(products, list) or not products:
        print("API không trả về danh sách products hợp lệ.", file=sys.stderr)
        return 1
    if total is not None and int(total) != len(products):
        print(f"Dữ liệu chưa đầy đủ: lấy {len(products)} sản phẩm nhưng API báo total={total}.", file=sys.stderr)
        return 1

    # Keep the API response as raw data. Add ingestion metadata in a sidecar file,
    # rather than changing the JSON response structure.
    temp = OUTPUT.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(OUTPUT)
    meta = {
        "source_url": API_URL,
        "ingested_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "products_downloaded": len(products),
        "api_total": total,
        "categories": sorted({str(p.get("category", "")) for p in products}),
        "file": str(OUTPUT),
    }
    OUTPUT.with_name("dummyjson_ingestion_metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Đã lưu {len(products)} sản phẩm vào: {OUTPUT}")
    print(f"API total={total}; số category={len(meta['categories'])}")
    print("Đây là raw API snapshot; file chưa được làm sạch hoặc biến đổi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
