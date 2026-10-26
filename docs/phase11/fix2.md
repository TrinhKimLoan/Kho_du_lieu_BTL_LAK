# Phase 11 Fix 2 — khởi động lạnh Streamlit và tên module app

Người dùng ghi nhận script data/UI passed tại evidence/phase11/run-20261026T073001Z-5a5ccbb7, nhưng trình duyệt lỗi ImportError: cannot import name perform from partially initialized module src.dashboard.demo.

Nguyên nhân: Streamlit chạy trực tiếp src/dashboard/app.py và đưa thư mục script lên đầu sys.path. Khi src.source.data import app.core, Python chọn nhầm src/dashboard/app.py thay vì gói app/ ở thư mục gốc, từ đó lặp lại import demo. Kiểm thử cũ chạy trong tiến trình đã import app.core trước đó nên không phát hiện trường hợp khởi động lạnh này.

Đã tái hiện cùng ImportError trong tiến trình Python hoàn toàn mới, với thư mục dashboard đứng đầu sys.path. Sửa bằng cách:

- Đổi src/dashboard/app.py thành src/dashboard/ui.py, loại bỏ tên file trùng gói app.
- Thêm streamlit_app.py ở gốc làm điểm khởi động; Docker và AppTest dùng cùng điểm này.
- Giữ nguyên gói app/core.py, dữ liệu, schema, model và worker CDC/ML.
- Kiểm thử UI tham chiếu repository qua module để không giữ lớp mock đã cache từ lần kiểm thử trước.
- Thêm kiểm thử import trong tiến trình Python mới, xác nhận app.core trỏ đúng gói gốc.
- dashboard-checks chạy thêm import lạnh trong tiến trình mới bên trong image thực tế trước khi thực thi tám trang.

16 kiểm thử Phase 11 đạt sau sửa. Phần hiển thị trình duyệt vẫn cần kiểm tra trên máy Windows sau khi áp dụng bản vá và chạy lại scripts/run_phase11.ps1. Script tự dựng lại image và cập nhật container dashboard bằng up -d; không cần down hoặc reset volume.

Sau khi lệnh đạt, mở http://localhost:8501 và nhấn Ctrl+F5. Chưa chốt Phase 11 chỉ từ HTTP Healthy; cần xác nhận ứng dụng thực sự mở được trong trình duyệt.
