# Vận hành LAK hiện tại trên Windows

Chạy từ PowerShell; Python host chỉ dùng thư viện chuẩn cho script Phase 13. Docker Desktop phải ở chế độ Linux containers. Các môi trường Python của ứng dụng nằm trong image, không cần cài chung 9 môi trường lên Windows.

```powershell
Set-Location 'G:\LAK-Analytics'
python scripts/phase13/ops.py status
python scripts/phase13/ops.py start
python scripts/phase13/ops.py logs
python scripts/phase13/ops.py stop
```

- `status`: xem toàn bộ dịch vụ của project.
- `start`: xác minh ID của 13 image theo inventory, rồi khởi động 9 dịch vụ hiện có bằng `--no-build --pull never`. Image thiếu/khác sẽ dừng để xem xét, không tự thay phiên bản.
- `logs`: tối đa 100 dòng mỗi dịch vụ; không theo dõi vô hạn.
- `stop`: dừng dịch vụ, giữ nguyên container, network và volume. Không dùng `down`, `--remove-orphans`, prune hoặc `-v` trong vận hành thông thường.

Website: http://localhost:8501. Cổng hiện có chỉ bind localhost: MySQL 3310, PostgreSQL 5435, Connect 8085. Mật khẩu lấy từ `.runtime/lak.env`; API key trong `.runtime/news.env`. Không in hai tệp này ra log hoặc đưa vào bản nộp.

## Mẫu môi trường

`infra/env/lak.env.example` chứa bốn tên biến credential LAK, không chứa mật khẩu thật. `infra/env/news.env.example` có API key trống. Đây là mẫu cho môi trường mới; **không copy đè `.runtime` hiện có**. Việc tạo credential mới và đăng ký connector ở môi trường dựng lại sẽ dùng quy trình Stage B. `.env.example` gốc và các compose gốc ngoài `infra/` là tài liệu tương thích ban đầu, không phải cấu hình runtime LAK hiện tại.

Không cần API key để xem dữ liệu tin tức đã có trong PostgreSQL. Thiếu key không chứng minh fetch API hoạt động; gói ứng viên Stage A chưa chứa dữ liệu PostgreSQL. Ở môi trường mới, cần restore dữ liệu lưu sẵn theo Stage B hoặc nhập/fetch có API key hợp lệ. Dữ liệu lưu sẵn phải được ghi nhãn và giữ thông tin nguồn/quyền sử dụng; không sao chép toàn văn bài báo ngoài phạm vi được phép.

## Khi có lỗi

Giữ output và thư mục Evidence. Không chạy lại `init` hoặc reset nguồn để chữa lỗi import/network. Với image mismatch, gửi tên image và thông báo; không tự build đè image đã khóa. Bản sao dữ liệu, ảnh Docker và credential là ba loại khác nhau; khóa digest/checksum không thay thế các byte cần restore.
