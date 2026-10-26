# Phase 13B — Xuất dữ liệu logic

Chạy `python scripts/phase13/export_data.py --output G:\LAK-Releases` khi không thao tác demo hoặc ghi nguồn qua client khác.

Script kiểm tra nhãn ownership của container, tạm dừng dashboard, Airflow scheduler, collector, applier và inference nếu đang chạy; MySQL, PostgreSQL, Kafka và Connect vẫn chạy. Xuất database nguồn bằng mysqldump single-transaction (không xuất database hệ thống chứa tài khoản), xuất PostgreSQL bằng pg_dump custom format không owner/ACL. Kho PostgreSQL bao gồm metadata tin tức đã lưu và bảng ML. Hai snapshot riêng nhất quán trong từng DB; không tuyên bố snapshot nguyên tử xuyên hệ thống hoặc queue đã được drain.

Trong finally, mọi dịch vụ đã được thử dừng đều được khởi động lại. Trạng thái Running sau start được kiểm tra; không đồng nghĩa healthcheck đã hồi phục ngay. Báo cáo ghi lỗi restart và script trả mã lỗi nếu cần khôi phục thủ công. Dùng `python scripts/phase13/ops.py status` để xem trạng thái, chờ healthcheck và thu bằng chứng.

Tệp dump ghi qua Python binary stream, tránh chuyển mã dữ liệu nhị phân trong PowerShell. Password được đọc từ môi trường bên trong MySQL container, không đưa giá trị vào argv host hoặc log. pg_restore --list chỉ xác minh thư mục archive, không phải restore thử.

Đầu ra mỗi lượt có tên riêng gồm mysql-source.sql, warehouse.dump, warehouse-toc.txt và export.json với kích thước/SHA-256. Tệp .partial của lượt lỗi được giữ để truy vết, không dùng làm snapshot đạt. Không upload hai dump để gửi kết quả; chỉ gửi export.json và trạng thái dịch vụ.

Không xuất byte Kafka/Connect volumes, MySQL system users hoặc Airflow SQLite. Khi dựng lại phải tạo credential riêng và thiết kế bootstrap CDC phù hợp nguồn/epoch/offset mới; không tái sử dụng checkpoint cũ trên Kafka mới một cách máy móc. Đã có snapshot không có nghĩa đã dựng lại thành công. Các dump có dữ liệu nghiệp vụ/metadata và chỉ dùng trong gói release phù hợp quyền truy cập, không bao gồm API key thật.
