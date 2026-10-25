# Trạng thái dự án

## Đã xác nhận trên máy sinh viên

- Giai đoạn 0: PHASE 0 CHECKS PASSED, commit f214c8d.
- Giai đoạn 1: PHASE 1 DATA CHECKS PASSED WITH OBSERVATIONS, năm test đạt,
  commit 3e43b27. Người dùng gửi kết quả PowerShell, thời gian test 8.929 giây.
- Đường dẫn bằng chứng do người dùng báo:
  `G:\LAK-phase1\LAK-Analytics\evidence\phase1\run-20261025T153752Z-b47083`.
  Đây là thông tin người dùng xác nhận, không phải thư mục đã được tải về môi
  trường trợ lý và không thay thế nội dung profile.json chưa được gửi.

## Gói giai đoạn 2

Đã chuẩn bị DDL cho CSDL riêng, ERD, grain, ánh xạ, hợp đồng thay đổi,
lint thiết kế và test Python. Gói giữ nguyên source LAK gốc và kế hoạch.

Chưa xác nhận PostgreSQL thực thi DDL hoặc PowerShell trong môi trường trợ lý:
không có Docker, PostgreSQL hoặc PowerShell. Script thử trên Windows tạo một
container tạm riêng; chỉ khi có kết quả thực tế mới ghi schema runtime PASS.
Chưa triển khai giai đoạn 3 hay các worker/model/giao diện của giai đoạn sau.

Giữ hai thuật toán và phần tin tức theo yêu cầu trực tiếp của giảng viên do
người dùng xác nhận. Không làm phân công nhóm, báo cáo/slide để sau sản phẩm.
Nguồn gốc/giấy phép Excel và timezone/ý nghĩa thời gian gốc chưa xác minh;
các lựa chọn vận hành được công bố trong business_definitions và thiết kế.
