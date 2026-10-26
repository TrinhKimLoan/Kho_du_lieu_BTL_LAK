# Sửa lỗi fileno trước khi bootstrap CDC

Lượt chạy 26/10/2026 10:16:39–10:16:56 UTC trên project lak-rebuild-b406a316e7 gặp UnsupportedOperation: fileno. Nguyên nhân: subprocess.run nhận stdin=io.BytesIO, trong khi Popen cần file descriptor của hệ điều hành. Kafka/Connect đã được khởi động, nhưng child process tạo tài khoản CDC chưa được spawn; bước prepare epoch nằm sau đó nên chưa chạy.

Sửa cách truyền SQL qua tempfile.TemporaryFile, đóng tự động sau subprocess. Không đưa SQL/password vào argv hoặc in SQL ra màn hình. Có phép thử subprocess Python thật nhận đúng byte UTF-8; không giả lập file descriptor.

Chỉ cho phép tự chạy lại nếu bootstrap.json của cùng project ghi passed=false, error_type=UnsupportedOperation, safe_message=fileno và thư mục chỉ chứa bootstrap.json, bootstrap.log, runtime.py. Nếu xuất hiện epoch-plan.json hoặc bằng chứng bước khác, từ chối để xem xét. Thư mục lỗi được đổi tên cdc-failed-fileno-<UTC>-<suffix>, giữ nguyên nội dung; lượt mới dùng lại thư mục cdc. Không xóa/khởi tạo lại DB, Kafka hoặc volume.
