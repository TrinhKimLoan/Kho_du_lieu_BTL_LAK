# Danh sách giữ lại sửa và bổ sung

| Thành phần | Quyết định | Việc tiếp theo |
| --- | --- | --- |
| Sáu Excel LAK | Giữ làm nguồn lịch sử | Xác nhận xuất xứ, ẩn danh phù hợp, profile và nạp có truy vết |
| Tin mẫu và MediaCloud | Giữ | Kiểm tra nguồn, phân trang, độ phủ, khóa, phân loại và fallback |
| Đọc XLSX, CLI | Giữ để đối chiếu | Kiểm chứng kiểu dữ liệu, ngày giờ và Decimal trước tái sử dụng |
| Luật liên quan và tests | Giữ | Kiểm tra mẫu có nhãn người đánh giá, không gọi là ML được train |
| FastAPI chỉ đọc | Giữ trong bản nền | Chỉ tích hợp khi có nhu cầu, chưa bắt Streamlit phải gọi qua API |
| Airflow DAG | Giữ nghiệp vụ lịch chạy | Xác nhận tài nguyên, metadata và trạng thái lỗi |
| SQL raw/staging/DW/ops | Sửa theo thiết kế mới | Grain, đầy đủ cột cập nhật, khóa, ngày theo vai trò và audit |
| Docker và môi trường | Sửa ở giai đoạn triển khai | Project, volume, cổng, topic độc lập; khóa phiên bản sau kiểm chứng |
| CSDL MySQL nguồn | Thêm | Lược đồ phù hợp LAK, nạp idempotent, dữ liệu demo riêng |
| Debezium và Kafka | Thêm | Snapshot, metadata, offset và kiểm thử thêm/sửa/xóa |
| Collector/applier | Thêm có tham khảo CommerceInsight | Đổi schema/topic, ledger, replay, delete và recovery |
| SCD2 và chất lượng | Thêm theo thuộc tính cần thiết | Không tự suy diễn lịch sử nghiệp vụ chưa quan sát |
| Mart/cube và năm thao tác OLAP | Thêm/hoàn thiện | Định nghĩa KPI, khối con, đối soát với fact |
| RFM + K-Means | Thêm | Snapshot, chia tập, baseline, đánh giá và model metadata |
| Random Forest giao hàng | Thêm theo điều kiện dữ liệu trong kế hoạch | Chốt thời điểm dự đoán, nhãn và baseline, tránh tương lai |
| Worker suy luận và model version | Thêm | Kết nối CDC, hàng đợi bền vững, không train mỗi sự kiện |
| Website Streamlit và Plotly | Thêm | Bảng + biểu đồ, ML, dữ liệu chờ/lỗi và CDC demo |
| Kiểm thử đầu cuối và release | Thêm | Bằng chứng riêng LAK, dựng sạch và ghi thao tác thủ công |
| Model/số liệu Online Retail II | Không dùng làm kết quả LAK | Huấn luyện và kiểm chứng lại trên dữ liệu LAK |
| Website bán hàng, gợi ý sản phẩm | Không triển khai | Ngoài phạm vi kế hoạch |
| Phân công nhóm | Không thực hiện | Người dùng xác nhận nhóm một người |
| Báo cáo môn học và slide | Để sau sản phẩm | Vẫn lưu tài liệu kỹ thuật và bằng chứng từng giai đoạn |
