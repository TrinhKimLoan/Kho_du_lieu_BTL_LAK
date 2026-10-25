# Trạng thái dự án

## Đã xác nhận trên máy sinh viên

- Giai đoạn 0: PHASE 0 CHECKS PASSED, commit f214c8d.
- Giai đoạn 1: PHASE 1 DATA CHECKS PASSED WITH OBSERVATIONS, năm test đạt,
  commit 3e43b27. Người dùng gửi kết quả PowerShell, thời gian test 8.929 giây.
- Đường dẫn bằng chứng do người dùng báo:
  `G:\LAK-phase1\LAK-Analytics\evidence\phase1\run-20261025T153752Z-b47083`.
  Đây là thông tin người dùng xác nhận, không phải thư mục đã được tải về môi
  trường trợ lý và không thay thế nội dung profile.json chưa được gửi.

## Giai đoạn 2 đã được người dùng xác nhận

Đã chuẩn bị DDL cho CSDL riêng, ERD, grain, ánh xạ, hợp đồng thay đổi,
lint thiết kế và test Python. Gói giữ nguyên source LAK gốc và kế hoạch.

Người dùng đã gửi bốn test đạt, PostgreSQL thực thi DDL và fixture PASS trên
Windows. NOTICE hiển thị kiểu NativeCommandError không làm script thất bại;
log có DO, ROLLBACK và PHASE 2 POSTGRES CHECKS PASSED. Bằng chứng do người dùng
báo: `G:\LAK-Phase2\LAK-Analytics\evidence\phase2\run-20261025T162012Z-71514af8`.
Chưa tải thư mục đó về môi trường trợ lý. Source đã được người dùng chuyển
đến `G:\LAK-Analytics`, HEAD 3ec2598. Không tạo thư mục dự án mới ở mỗi pha.

## Gói pha 3

Cập nhật nối tiếp bằng patch; có MySQL riêng, loader lịch sử, provenance,
demo và runner kiểm thử. Chưa xác nhận MySQL runtime, Docker/PowerShell ở
môi trường trợ lý. Chỉ chuyển pha 4 sau kết quả thực tế từ người dùng.

Giữ hai thuật toán và phần tin tức theo yêu cầu trực tiếp của giảng viên do
người dùng xác nhận. Không làm phân công nhóm, báo cáo/slide để sau sản phẩm.
Nguồn gốc/giấy phép Excel và timezone/ý nghĩa thời gian gốc chưa xác minh;
các lựa chọn vận hành được công bố trong business_definitions và thiết kế.
