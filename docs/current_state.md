# Hiện trạng LAK tại giai đoạn 0

Kiểm tra trên bản sao của `LAK_Khodulieu-main(1).zip` được cung cấp ngày 2026-10-25.
Không có phiên bản chạy CSDL của người dùng trong môi trường này.

## Chức năng có trong source

- `app/core.py`: đọc XLSX, nạp raw và staging, xây dimension/fact và view tổng hợp.
- `app/cli.py`: bootstrap, excel, seed-news, fetch-news, marts, validate,
  all-offline, backfill-month, backfill-range, reclassify-news và health.
- `app/relevance.py`, `config/category_rules.json`: luật gắn mức liên quan tin tức.
- `data/excel`: sáu Excel; `data/news_seed`: tệp 360 tin mẫu năm 2024.
- `sql/001_schema.sql`: raw, staging, dw, ops; fact_sales, fact_news và bridge.
- `dags/ecom_dwh_pipelines.py`: lịch ETL Excel hằng tuần, tin tức hằng ngày,
  health check mỗi sáu giờ. DAG được cấu hình tạm dừng khi mới tạo.
- `backend/main.py`: FastAPI chỉ đọc, endpoint tổng quan, sản phẩm, RFM thô,
  vận chuyển, tin tức và trạng thái pipeline.
- Endpoint phân cụm hiện trả 501, có thông báo chưa huấn luyện mô hình.
- `tests/test_transform.py`: ba test unittest.
- `tests/test_relevance.py`: sáu hàm test dạng pytest, không phải unittest.

## Chức năng chưa có

Chưa có MySQL nguồn, Debezium, Kafka, collector/applier giao dịch, SCD2,
mô hình ML đã huấn luyện, worker suy luận hoặc giao diện website.
`test_cdc_insert.py` gọi nhập một bài tin mẫu, không chứng minh CDC binlog
hoặc thay đổi giao dịch đầu cuối. Không chạy tệp này khi chỉ kiểm tra offline.

## Kết nối dữ liệu hiện tại

Excel được nạp thẳng PostgreSQL. Tin tức được polling theo cửa sổ thời gian,
so sánh khóa/hash, ghi INSERT/UPDATE; không phải CDC binlog. API đọc từ DW/ops.
Các view monthly_sales/monthly_news là tổng hợp hiện có, chưa phải bộ kiểm chứng
đủ năm thao tác OLAP và các khối con trong kế hoạch mới.

## Vấn đề cần sửa ở các giai đoạn sau

1. Grain fact_sales hiện một order_id/một sản phẩm; chưa có giỏ hàng nhiều dòng.
2. Ngày đóng gói bị ánh xạ thành order_date. Phải chốt nghĩa và tên trước thiết kế mới.
3. Các cột giờ giao nhận chưa được pipeline sử dụng khi tính thời gian giao hàng.
4. `money()` chuyển sang float; cần dùng Decimal/NUMERIC và công thức đối soát.
5. Nhánh upsert staging và fact cập nhật chưa đủ toàn bộ cột có thể thay đổi.
   Ví dụ sửa khách/sản phẩm/địa bàn có thể để sót giá trị cũ; cần test riêng.
6. Validation chủ yếu in số liệu, chỉ có assertion tổng quan về grain, chưa
   có gate đầy đủ cho công thức tiền, thời gian, quan hệ và dữ liệu lỗi.
7. Raw Excel hiện upsert theo khóa, chưa giữ mọi phiên bản nhập file.
8. Bridge bị xóa rồi dựng lại; thiết kế mới cần xác định cập nhật và kiểm chứng
   phép join nhiều danh mục không làm nhân doanh thu.
9. Dependency mediacloud chưa khóa phiên bản; PostgreSQL dùng tag postgres:16.
10. Airflow đang dùng SequentialExecutor và SQLite để lưu metadata. Cần đánh giá
    tài nguyên thực tế trước khi giữ hay điều chỉnh cấu hình vận hành.
11. Chưa có tài liệu xác nhận nguồn/giấy phép hay mã sinh sáu Excel trong gói.
    API có ghi dữ liệu bán hàng là mô phỏng. Không suy diễn danh tính người thật
    hay khẳng định dữ liệu doanh nghiệp thực. Cần xử lý trường cá nhân trước bản nộp.

## Số liệu kiểm tra sơ bộ đã có

10.000 đơn; 3.282 khách; 15 sản phẩm; bảng thời gian/thanh toán/vận chuyển
mỗi bảng 10.000 dòng. Khóa ghép đủ. Công thức tiền và tổng hợp khách/sản phẩm khớp.
Ngày đóng gói từ 2020-01-01 đến 2025-12-20.

880 bản ghi có thời điểm giao đi trước đóng gói; 118 bản ghi có thời điểm dự kiến
đến trước giao đi. Đếm trễ theo ngày cho 1.987 đơn, theo ngày và giờ cho 5.170 đơn.
Địa chỉ theo đơn khác hồ sơ khách ở 6.070 đơn, chưa tự coi là lỗi.
Tin mẫu: 19 DIRECT, 6 INDIRECT, 335 IRRELEVANT theo bộ luật hiện tại,
chưa phải đánh giá độ chính xác bằng nhãn con người.

Các số trên là quan sát trong lượt kiểm tra trước giai đoạn 0. Giai đoạn 1
phải đưa thành script và bằng chứng chạy lại được, cùng định nghĩa từng phép đo.

## Mức kiểm chứng

Giai đoạn 0 kiểm tra bytes nguồn, cú pháp Python và chín test logic hiện có.
Không cài thêm gói Python. Chưa chạy Docker, CSDL, Airflow, API trực tiếp,
MediaCloud live, CDC hoặc ML trong môi trường này. Docker CLI không có sẵn.
Không dùng các test offline để suy ra dịch vụ hay hệ thống đầu cuối đã chạy.
