# Lược đồ quan hệ kho LAK

## Bán hàng

```mermaid
erDiagram
    direction TB
    dim_category ||--o{ fact_sales : category_key
    dim_product ||--o{ fact_sales : product_key
    dim_customer ||--o{ fact_sales : customer_key
    dim_geography ||--o{ fact_sales : delivery_geography_key
    dim_shipping_method ||--o{ fact_sales : shipping_method_key
    dim_date ||--o{ fact_sales : "four date roles"
    dim_geography ||--o{ dim_customer : profile_geography_key
    dim_category {
        bigint category_key PK
        text category_code UK
    }
    dim_product {
        bigint product_key PK
        text product_id
        text category_code
        timestamptz valid_from
        timestamptz valid_to
    }
    dim_customer {
        bigint customer_key PK
        text customer_id UK
    }
    fact_sales {
        bigint sales_key PK
        text order_id UK
        bigint product_key FK
        numeric goods_amount
        numeric delivery_hours
    }
    dim_geography {
        bigint geography_key PK
        text geography_code UK
    }
    dim_shipping_method {
        bigint shipping_method_key PK
        text shipping_method_code UK
    }
    dim_date {
        integer date_key PK
        date full_date UK
    }
```

Bốn vai trò cùng tham chiếu dim_date: packed_date_key, dispatched_date_key,
expected_date_key và received_date_key. Có key 0 để biểu diễn chưa biết.
Một product_id có nhiều phiên bản, fact chỉ trỏ một product_key cụ thể.

## Tin tức

```mermaid
erDiagram
    direction TB
    dim_date ||--o{ fact_news : published_date_key
    dim_news_source ||--o{ fact_news : news_source_key
    fact_news ||--o{ bridge_news_category : news_key
    dim_category ||--o{ bridge_news_category : category_key
    fact_news {
        bigint news_key PK
        text article_key UK
        integer published_date_key FK
        bigint news_source_key FK
    }
    bridge_news_category {
        bigint news_key PK,FK
        bigint category_key PK,FK
    }
    dim_news_source {
        bigint news_source_key PK
        text domain UK
    }
```

dim_date và dim_category là các chiều dùng chung giữa hai sơ đồ, không phải
hai bảng sao chép. Bridge cho phép một bài nhiều danh mục. Fact bán hàng
tham chiếu trực tiếp các chiều để truy vấn hình sao. category_code được giữ
trên version sản phẩm để biết cách gán category_key của fact tại lúc chiếu.

Các cột đầy đủ, constraint và chỉ mục nằm trong SQL. Hai sơ đồ chỉ thể hiện
quan hệ phân tích; raw/staging/audit có hợp đồng truy vết riêng.
