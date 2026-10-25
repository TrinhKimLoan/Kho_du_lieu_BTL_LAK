# Luồng dữ liệu hiện tại và mục tiêu

## Hiện tại

Excel đi qua app.core.load_excel vào PostgreSQL raw/staging, rồi build_marts
tạo dimension, fact và view. Tin mẫu hoặc MediaCloud đi qua ingest_news,
lưu raw snapshot, so sánh hash và làm mới DW. Airflow điều phối theo lịch.
FastAPI đọc DW/ops. Chưa có giao diện và mô hình huấn luyện.

## Mục tiêu theo kế hoạch được xác nhận

Excel lịch sử khởi tạo MySQL nghiệp vụ mô phỏng. Debezium đọc binlog MySQL,
gửi Kafka. Collector lưu sự kiện raw bền vững, applier cập nhật staging/DW
với khóa sự kiện và transaction ledger. Fact/dimension phục vụ mart/OLAP.
Thay đổi có liên quan đưa vào hàng đợi tính đặc trưng và suy luận ML.

MediaCloud vẫn là luồng API theo lịch riêng: raw snapshot, chuẩn hóa URL,
khóa/hash, phân loại liên quan, fact tin tức và bridge danh mục. Không tự
coi bài không xuất hiện trong một lần polling là bị xóa.

Streamlit hiển thị phân tích, OLAP, RFM/K-Means, Random Forest giao hàng,
tin thị trường và trạng thái pipeline. Dùng chung truy vấn/nghiệp vụ;
FastAPI chỉ tham gia nếu có vai trò thực tế. Airflow dành cho tác vụ lịch,
không dùng để khởi động lại toàn pipeline trên mỗi sự kiện giao dịch.

Đây là kiến trúc mục tiêu, chưa được triển khai ở giai đoạn 0. Grain,
khóa ngày, dimension SCD2 và nhãn giao hàng chốt sau kiểm tra dữ liệu.
Hai dự án cũ giữ nguyên; không dùng chung volume, topic hoặc consumer group.
