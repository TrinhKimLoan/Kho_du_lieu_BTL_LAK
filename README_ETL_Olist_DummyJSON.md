# ETL cuối kỳ — Olist + DummyJSON

## 1. Mục tiêu và giới hạn

- Olist là nguồn giao dịch chính; DummyJSON là nguồn dữ liệu mẫu bổ sung ngữ cảnh Rating theo Category.
- Pipeline sử dụng đủ **9 CSV Olist** và một file JSON raw từ DummyJSON.
- Mô hình đầu ra gồm **3 Fact + 4 Dimension**. Ba Fact không nối trực tiếp với nhau; chúng chia sẻ các Dimension phù hợp.
- `dummyjson_category_avg_rating` là Rating trung bình của các sản phẩm DummyJSON trong Category được ánh xạ, **không phải Rating thật của SKU Olist**. Phản hồi thật của khách Olist được lấy riêng từ `olist_order_reviews_dataset.csv` và tổng hợp vào `Fact_Orders`.
- Các quy tắc mapping là proxy theo Category, không phải bằng chứng hai danh mục hoàn toàn đồng nhất. Những Category chưa có ánh xạ đáng tin cậy được để chưa ánh xạ, không tự gán Rating 4.00.

## 2. Cấu trúc thư mục

Đặt hai script ở thư mục gốc dự án, cùng cấp với `datalake/`:

```text
OlistProject/
├── etl_olist_enrichment_final.py
├── ingest_dummyjson_products.py
└── datalake/
    ├── raw/
    │   ├── olist_customers_dataset.csv
    │   ├── olist_geolocation_dataset.csv
    │   ├── olist_order_items_dataset.csv
    │   ├── olist_order_payments_dataset.csv
    │   ├── olist_order_reviews_dataset.csv
    │   ├── olist_orders_dataset.csv
    │   ├── olist_products_dataset.csv
    │   ├── olist_sellers_dataset.csv
    │   ├── product_category_name_translation.csv
    │   └── dummyjson_products_raw.json   # được tạo bởi script ingestion
    └── processed/                         # ETL tự tạo
```

Tải bộ Olist từ Kaggle: <https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce>. Giải nén và đặt đúng **9 tên file CSV** bên trên vào `datalake/raw/`. Không cần tải hoặc dán từng file CSV vào ChatGPT.

DummyJSON endpoint: <https://dummyjson.com/products?limit=0>. Tài liệu API nêu rõ `limit=0` trả về toàn bộ sản phẩm thay vì chỉ 30 sản phẩm mặc định: <https://dummyjson.com/docs/products>.

## 3. Cách chạy trên Windows PowerShell

Mở PowerShell tại thư mục gốc dự án. Cài thư viện một lần:

```powershell
python -m pip install pandas numpy
```

### Bước A — nạp JSON raw từ DummyJSON

```powershell
python ingest_dummyjson_products.py
```

Script sẽ lưu nguyên phản hồi API vào `datalake/raw/dummyjson_products_raw.json` và metadata vào `datalake/raw/dummyjson_ingestion_metadata.json`. Nó kiểm tra số bản ghi tải được so với trường `total` của API.

### Bước B — chạy ETL

```powershell
python etl_olist_enrichment_final.py
```

Chỉ dùng bộ CSV đầu ra khi `datalake/processed/etl_quality_report.json` có:

```json
"run_status": "success"
```

Nếu báo `failed` hoặc `failed_quality_checks`, không bàn giao các CSV cũ còn sót từ lần chạy trước như thể đó là dữ liệu mới. Đọc trường `error`, `checks` và `join_audit` trong file report để xử lý nguyên nhân.

## 4. Mô hình dữ liệu

### Dimensions (4 bảng)

- **Dim_Customer**: một dòng cho mỗi `customer_id`; giữ `customer_unique_id` để gộp các đơn của cùng một người khi tính RFM. Bổ sung tọa độ trung bình theo mã bưu chính từ geolocation.
- **Dim_Product**: một dòng cho mỗi `product_id`; có Category Olist đã dịch, thông tin trọng lượng/kích thước, trạng thái Mapping và `dummyjson_category_avg_rating`.
- **Dim_Seller**: một dòng cho mỗi `seller_id`; bổ sung tọa độ trung bình theo mã bưu chính.
- **Dim_Time**: lịch ngày liên tục từ mốc ngày sớm nhất đến muộn nhất của các sự kiện có ngày hợp lệ.

### Facts (3 bảng)

- **Fact_Sales**: một dòng cho mỗi `(order_id, order_item_id)`. Measures chính: `item_price`, `freight_value`. Có `order_status` để lọc đơn phù hợp cho phân tích doanh thu.
- **Fact_Payments**: một dòng cho mỗi `(order_id, payment_sequential)`. Measure `payment_value` được giữ ở grain thanh toán; không cộng lặp tổng thanh toán trên từng mặt hàng.
- **Fact_Orders**: một dòng cho mỗi `order_id`. Chứa trạng thái, ngày đặt/giao/dự kiến, `delivery_days`, `delivery_delay_days` và thông tin review Olist đã tổng hợp theo đơn (`review_score_avg`, số review, số review có comment).

### Quan hệ Power BI

- `Dim_Customer[customer_sk]` → `Fact_Sales[customer_sk]`, `Fact_Payments[customer_sk]`, `Fact_Orders[customer_sk]`.
- `Dim_Product[product_sk]` → `Fact_Sales[product_sk]`.
- `Dim_Seller[seller_sk]` → `Fact_Sales[seller_sk]`.
- `Dim_Time[time_sk]` → `Fact_Sales[time_sk]`, `Fact_Payments[time_sk]`.
- `Fact_Orders` có nhiều khóa ngày vai trò: `purchase_time_sk`, `approved_time_sk`, `carrier_time_sk`, `delivered_time_sk`, `estimated_delivery_time_sk`, `review_creation_time_sk`, `review_answer_time_sk`. Trong Power BI, có thể dùng một quan hệ ngày chính và quan hệ không hoạt động cho ngày khác, hoặc tạo các bản sao role-playing của Dim_Time khi cần phân tích nhiều loại ngày trên cùng trang.
- **Không tạo quan hệ trực tiếp Fact_Sales ↔ Fact_Payments ↔ Fact_Orders.** Khi tính doanh thu hàng hóa, dùng `SUM(Fact_Sales[item_price])`; khi phân tích tiền thanh toán, dùng `SUM(Fact_Payments[payment_value])`. Hai measure có định nghĩa khác nhau nên không mặc định bằng nhau.

## 5. Quy tắc làm sạch và mapping

1. Chuẩn hóa chuỗi, mã bưu chính, kiểu số và timestamp.
2. Loại dòng trùng **toàn bộ cột** ở nguồn; nếu khóa nghiệp vụ vẫn trùng nhưng các cột khác nhau, ETL dừng để tránh tự xóa giao dịch hợp lệ.
3. Với trọng lượng/kích thước sản phẩm thiếu, dùng trung vị của cột nếu tính được; các cột `*_was_missing` đánh dấu giá trị đã bị thiếu trước khi điền. Không gán giá trị giả nếu toàn cột không có dữ liệu.
4. Với geolocation, tổng hợp nhiều điểm thành một tọa độ trung bình theo zip prefix **trước khi JOIN**. Nhờ vậy không làm tăng số dòng khách hàng/người bán.
5. Chỉ các quy tắc Category được định nghĩa tường minh mới bổ sung Rating. Rating lấy trung bình theo sản phẩm DummyJSON hợp lệ trong target category; không có dữ liệu thì để NA.
6. Phần lớn Mapping là `partial`; cần báo cáo như tín hiệu tham khảo, không diễn giải thành so sánh đánh giá trực tiếp giữa hai marketplace.
7. Review score Olist hợp lệ nằm trong khoảng 1–5; điểm ngoài khoảng được chuyển thành NA và ghi vào report. Nhiều bản ghi review trong một đơn được tổng hợp thành một dòng trước khi nối `Fact_Orders`.
8. ETL là **full refresh**: surrogate keys được tạo lại một cách xác định từ natural keys đã sắp xếp. Đây chưa phải thiết kế incremental/CDC.

## 6. File đầu ra

| File | Dùng cho |
|---|---|
| `dim_customer.csv` | Khu vực khách hàng, RFM, vị trí bản đồ |
| `dim_product.csv` | Category Olist, thuộc tính sản phẩm, Rating tham khảo DummyJSON |
| `dim_seller.csv` | Khu vực người bán, vị trí bản đồ |
| `dim_time.csv` | Phân tích ngày/tháng/quý/năm |
| `fact_sales.csv` | Doanh thu hàng hóa, chi phí vận chuyển, sản phẩm bán chạy, Apriori |
| `fact_payments.csv` | Tiền thanh toán theo phương thức, số kỳ thanh toán |
| `fact_orders.csv` | Trạng thái đơn, giao hàng, review_score thực của Olist |
| `category_mapping_audit.csv` | Coverage Category và Mapping, số sản phẩm Olist/DummyJSON, trạng thái/tin cậy |
| `etl_quality_report.json` | Kiểm tra khóa, số dòng, sums, geolocation coverage, mapping coverage, log từng JOIN |

## 7. Kiểm tra bắt buộc sau khi chạy

- `run_status` là `success` và mọi giá trị trong `checks` đều là `true`.
- `fact_sales_count_equals_deduplicated_item_source`, `fact_payments_count_equals_deduplicated_payment_source`, `fact_orders_count_equals_deduplicated_order_source` đều đạt.
- `item_price_sum_preserved`, `freight_sum_preserved`, `payment_value_sum_preserved_in_payment_fact` đều đạt.
- `join_audit` cho từng LEFT JOIN có số dòng trước/sau bằng nhau; phần measure sums không thay đổi.
- `category_mapping_audit.csv` được xem để hiểu danh mục nào được ánh xạ, loại ánh xạ nào là partial và Rating nào thực sự có dữ liệu.
- Đừng yêu cầu tỷ lệ Mapping phải bằng 100%: ánh xạ chính xác quan trọng hơn việc ép ghép các danh mục không tương đương.

## 8. Cách tạo RFM cho Khánh

Khi tính RFM, nối `Fact_Sales` với `Dim_Customer` và `Dim_Time`, lọc các trạng thái đơn mà nhóm thống nhất (ví dụ chỉ `delivered` nếu xem là giao dịch hoàn tất), sau đó nhóm theo **`customer_unique_id`**, không phải `customer_sk` hay `customer_id`.

- Recency: số ngày từ lần mua gần nhất đến ngày tham chiếu (thường là một ngày sau ngày mua cuối cùng trong dữ liệu).
- Frequency: số `order_id` khác nhau.
- Monetary: tổng `item_price` theo chính sách trạng thái đơn hàng mà nhóm đã công bố.

Với Apriori, tạo một transaction cho mỗi `order_id`, dùng `category_olist` từ `Dim_Product`, loại cặp trùng Category trong cùng một đơn trước khi chạy thuật toán.

## 9. Giới hạn kiểm thử

File ETL cần được chạy tại máy của nhóm trên đủ nguồn Olist thật. Trước khi có `etl_quality_report.json` từ bản raw đó, không thể khẳng định dữ liệu Olist thực đã qua tất cả quality gates. Gói đi kèm đã được kiểm thử cú pháp và chạy thử bằng bộ dữ liệu mẫu nhỏ; đó không thay thế cho việc kiểm tra trên dữ liệu gốc.
