import os
import json
import pandas as pd
import numpy as np

# 1. Đường dẫn thư mục Data Lake
RAW_DIR = "datalake/raw"
PROCESSED_DIR = "datalake/processed"
os.makedirs(PROCESSED_DIR, exist_ok=True)

print("🚀 BẮT ĐẦU CHẠY ETL PIPELINE (ĐÃ TÍCH HỢP DATA CLEANING)...")

# ==========================================
# 1. TẠO & LÀM SẠCH BẢNG DIM_PRODUCT
# ==========================================
print("\n📦 1/5. Đang xử lý & Làm sạch Bảng Dim_Product...")
df_products = pd.read_csv(os.path.join(RAW_DIR, "olist_products_dataset.csv"))
df_trans = pd.read_csv(os.path.join(RAW_DIR, "product_category_name_translation.csv"))

# A. Xử lý Missing Values & Dịch danh mục
df_prod_en = pd.merge(df_products, df_trans, on="product_category_name", how="left")
df_prod_en["product_category_name_english"] = df_prod_en["product_category_name_english"].fillna("others")

# B. LÀM SẠCH: Đền bù Missing values cho trọng lượng/kích thước bằng giá trị trung vị (Median)
df_prod_en["product_weight_g"] = df_prod_en["product_weight_g"].fillna(df_prod_en["product_weight_g"].median())

# C. Đọc & Mapping từ DummyJSON API
with open(os.path.join(RAW_DIR, "dummyjson_products_raw.json"), "r", encoding="utf-8") as f:
    api_data = json.load(f)
df_api = pd.DataFrame(api_data["products"])
api_summary = df_api.groupby("category")["rating"].mean().to_dict()

category_mapping = {
    "telephony": "smartphones", "fixed_telephony": "smartphones",
    "computers_accessories": ["laptops", "mobile-accessories"], "computers": "laptops",
    "tablets_printing_image": "tablets", "perfumery": "fragrances",
    "health_beauty": ["beauty", "skin-care"], "furniture_decor": "furniture",
    "office_furniture": "furniture", "furniture_bedroom": "furniture",
    "furniture_living_room": "furniture", "furniture_mattress_and_upholstery": "furniture",
    "home_comfort_2": "home-decoration", "home_confort": "home-decoration",
    "housewares": "kitchen-accessories", "la_cuisine": "kitchen-accessories",
    "kitchen_dining_laundry_garden_furniture": "kitchen-accessories",
    "fashion_shoes": ["mens-shoes", "womens-shoes"], "fashion_bags_accessories": ["womens-bags", "sunglasses"],
    "watches_gifts": ["mens-watches", "womens-watches"], "fashion_male_clothing": "mens-shirts",
    "fashio_female_clothing": "womens-dresses", "fashion_underwear_beach": "tops",
    "fashion_sport": "sports-accessories", "auto": ["vehicle", "motorcycle"],
    "sports_leisure": "sports-accessories", "food": "groceries", "food_drink": "groceries", "drinks": "groceries"
}

def calculate_mapped_rating(cat_en):
    mapped_val = category_mapping.get(cat_en, None)
    if not mapped_val: return 4.00
    if isinstance(mapped_val, list):
        ratings = [api_summary.get(c, 4.0) for c in mapped_val if c in api_summary]
        return round(np.mean(ratings), 2) if ratings else 4.00
    return round(api_summary.get(mapped_val, 4.00), 2)

def get_mapped_category_str(cat_en):
    mapped_val = category_mapping.get(cat_en, "unmapped")
    return ", ".join(mapped_val) if isinstance(mapped_val, list) else str(mapped_val)

df_prod_en["market_rating_score"] = df_prod_en["product_category_name_english"].apply(calculate_mapped_rating)
df_prod_en["mapped_api_category"] = df_prod_en["product_category_name_english"].apply(get_mapped_category_str)

# D. LÀM SẠCH: Loại bỏ trùng lặp nếu có & Tạo Surrogate Key
df_prod_en = df_prod_en.drop_duplicates(subset=["product_id"]).reset_index(drop=True)
df_prod_en["product_sk"] = np.arange(1, len(df_prod_en) + 1)

dim_product_final = df_prod_en[[
    "product_sk", "product_id", "product_category_name_english", 
    "mapped_api_category", "market_rating_score", "product_weight_g"
]].rename(columns={"product_category_name_english": "category_olist"})

dim_product_final.to_csv(os.path.join(PROCESSED_DIR, "dim_product.csv"), index=False)
print("   -> ✅ Đã làm sạch & xuất 'dim_product.csv'")


# ==========================================
# 2. TẠO & LÀM SẠCH BẢNG DIM_CUSTOMER
# ==========================================
print("\n👤 2/5. Đang xử lý & Làm sạch Bảng Dim_Customer...")
df_customers = pd.read_csv(os.path.join(RAW_DIR, "olist_customers_dataset.csv"))
df_customers = df_customers.drop_duplicates(subset=["customer_id"]).reset_index(drop=True) # Chuẩn hóa lặp
df_customers["customer_sk"] = np.arange(1, len(df_customers) + 1)

dim_customer_final = df_customers[[
    "customer_sk", "customer_id", "customer_unique_id", 
    "customer_zip_code_prefix", "customer_city", "customer_state"
]]
dim_customer_final.to_csv(os.path.join(PROCESSED_DIR, "dim_customer.csv"), index=False)
print("   -> ✅ Đã làm sạch & xuất 'dim_customer.csv'")


# ==========================================
# 3. TẠO & LÀM SẠCH BẢNG DIM_SELLER
# ==========================================
print("\n🏪 3/5. Đang xử lý & Làm sạch Bảng Dim_Seller...")
df_sellers = pd.read_csv(os.path.join(RAW_DIR, "olist_sellers_dataset.csv"))
df_sellers = df_sellers.drop_duplicates(subset=["seller_id"]).reset_index(drop=True) # Chuẩn hóa lặp
df_sellers["seller_sk"] = np.arange(1, len(df_sellers) + 1)

dim_seller_final = df_sellers[[
    "seller_sk", "seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"
]]
dim_seller_final.to_csv(os.path.join(PROCESSED_DIR, "dim_seller.csv"), index=False)
print("   -> ✅ Đã làm sạch & xuất 'dim_seller.csv'")


# ==========================================
# 4. TẠO & LÀM SẠCH BẢNG DIM_TIME
# ==========================================
print("\n📅 4/5. Đang xử lý & Chuẩn hóa Định dạng Bảng Dim_Time...")
df_orders = pd.read_csv(os.path.join(RAW_DIR, "olist_orders_dataset.csv"))

# LÀM SẠCH: Chuẩn hóa đính dạng Timestamp sang Datetime chuẩn
df_orders["order_purchase_timestamp"] = pd.to_datetime(df_orders["order_purchase_timestamp"], errors='coerce')
df_orders = df_orders.dropna(subset=["order_purchase_timestamp"]) # Bỏ các dòng lỗi ngày

unique_dates = df_orders["order_purchase_timestamp"].dt.date.drop_duplicates().reset_index(drop=True)
dim_time = pd.DataFrame({"full_date": pd.to_datetime(unique_dates)})

dim_time["time_sk"] = dim_time["full_date"].dt.strftime('%Y%m%d').astype(int)
dim_time["year"] = dim_time["full_date"].dt.year
dim_time["quarter"] = dim_time["full_date"].dt.quarter
dim_time["month"] = dim_time["full_date"].dt.month
dim_time["day"] = dim_time["full_date"].dt.day
dim_time["day_of_week"] = dim_time["full_date"].dt.day_name()

dim_time.to_csv(os.path.join(PROCESSED_DIR, "dim_time.csv"), index=False)
print("   -> ✅ Đã chuẩn hóa & xuất 'dim_time.csv'")


# ==========================================
# 5. TẠO & LÀM SẠCH BẢNG FACT_SALES (XỬ LÝ LẶP & ĐỊNH DẠNG TIỀN TỆ)
# ==========================================
print("\n💰 5/5. Đang xử lý, Khử trùng lặp & Chuẩn hóa Bảng Fact_Sales...")
df_items = pd.read_csv(os.path.join(RAW_DIR, "olist_order_items_dataset.csv"))
df_payments = pd.read_csv(os.path.join(RAW_DIR, "olist_order_payments_dataset.csv"))

# LÀM SẠCH PAYMENT: Gom nhóm tổng tiền thanh toán theo từng order_id để tránh nhân bản dòng giao dịch khi merge
df_payments_agg = df_payments.groupby("order_id").agg(
    total_payment_value=("payment_value", "sum"),
    main_payment_type=("payment_type", "first")
).reset_index()

# Merge Đơn hàng + Chi tiết món + Tổng tiền thanh toán đã gom nhóm
fact = pd.merge(df_items, df_orders[["order_id", "customer_id", "order_purchase_timestamp"]], on="order_id", how="inner")
fact = pd.merge(fact, df_payments_agg, on="order_id", how="inner")

# Nối Khóa ngoại (Surrogate Keys)
fact = pd.merge(fact, dim_product_final[["product_id", "product_sk"]], on="product_id", how="left")
fact = pd.merge(fact, dim_customer_final[["customer_id", "customer_sk"]], on="customer_id", how="left")
fact = pd.merge(fact, dim_seller_final[["seller_id", "seller_sk"]], on="seller_id", how="left")

# Nối Time SK
fact["full_date_only"] = pd.to_datetime(fact["order_purchase_timestamp"]).dt.date
dim_time["full_date_only"] = dim_time["full_date"].dt.date
fact = pd.merge(fact, dim_time[["full_date_only", "time_sk"]], on="full_date_only", how="left")

# LÀM SẠCH: Chuẩn hóa kiểu dữ liệu số thực cho giá tiền & Khử trùng lặp cuối cùng
fact["price"] = fact["price"].round(2)
fact["freight_value"] = fact["freight_value"].round(2)
fact["total_payment_value"] = fact["total_payment_value"].round(2)

fact_sales_final = fact[[
    "order_id", "customer_sk", "product_sk", "seller_sk", "time_sk",
    "price", "freight_value", "total_payment_value", "main_payment_type"
]].rename(columns={
    "price": "item_price",
    "total_payment_value": "payment_value",
    "main_payment_type": "payment_type"
})

# LÀM SẠCH: Loại bỏ 100% dòng trùng lặp (Drop Duplicates)
fact_sales_final = fact_sales_final.drop_duplicates().reset_index(drop=True)

fact_sales_final.to_csv(os.path.join(PROCESSED_DIR, "fact_sales.csv"), index=False)
print(f"   -> ✅ Đã làm sạch triệt để! Khử trùng lặp thành công, còn lại {len(fact_sales_final)} dòng giao dịch chuẩn trong 'fact_sales.csv'")

print("\n🎉 HOÀN THÀNH ETL & DATA CLEANING! Dữ liệu đã sạch 100% sẵn sàng cho cả nhóm sử dụng.")