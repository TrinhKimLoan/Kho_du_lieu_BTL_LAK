import os
import requests
import json
import pandas as pd

# 1. Định nghĩa đường dẫn Data Lake trên ổ D (hoặc thư mục dự án)
DATALAKE_RAW_DIR = "D:/BTL_KDL/Datalake/raw"
os.makedirs(DATALAKE_RAW_DIR, exist_ok=True)

print("🚀 Bắt đầu quá trình Ingestion (Thu thập dữ liệu thô)...")

# --- BƯỚC A: LẤY DỮ LIỆU TỪ RESTFUL API (DummyJSON) ---
try:
    api_url = "https://dummyjson.com/products?limit=0"
    print(f"📡 Đang gọi API: {api_url}...")
    response = requests.get(api_url)
    
    if response.status_code == 200:
        data = response.json()
        # Lưu thành file raw JSON trong Data Lake
        json_output_path = os.path.join(DATALAKE_RAW_DIR, "dummyjson_products_raw.json")
        with open(json_output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"✅ Đã lưu dữ liệu API vào Data Lake: {json_output_path} (Tổng số SP: {data.get('total')})")
    else:
        print(f"❌ Lỗi gọi API. Status code: {response.status_code}")
except Exception as e:
    print(f"❌ Xảy ra lỗi khi thu thập dữ liệu API: {e}")

# --- BƯỚC B: THU THẬP & LƯU TẬP TỆP CSV (Olist) ---
# Giả sử các file CSV Olist bạn tải về để trong thư mục 'source_csv'
SOURCE_CSV_DIR = "Olist" 

if os.path.exists(SOURCE_CSV_DIR):
    csv_files = [f for f in os.listdir(SOURCE_CSV_DIR) if f.endswith('.csv')]
    print(f"\n📂 Tìm thấy {len(csv_files)} file CSV Olist trong '{SOURCE_CSV_DIR}'")
    
    for file_name in csv_files:
        src_path = os.path.join(SOURCE_CSV_DIR, file_name)
        # Đọc và lưu kiểm tra
        df = pd.read_csv(src_path)
        dest_path = os.path.join(DATALAKE_RAW_DIR, file_name)
        df.to_csv(dest_path, index=False)
        print(f"  -> Đã copy {file_name} vào Data Lake: {dest_path} ({len(df)} dòng)")
else:
    print(f"\n⚠️ Chưa thấy thư mục '{SOURCE_CSV_DIR}'. Bạn hãy copy các file .csv Olist vào thư mục này nhé!")

print("\n🎉 Hoàn thành giai đoạn Ingestion! Dữ liệu thô đã sẵn sàng tại Data Lake.")