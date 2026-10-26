# Phase 13 — Dựng lại CSDL và mô hình trong project riêng

Script restore_candidate.py nhận candidate ZIP/checksum, image tar/checksum và thư mục snapshot có export.json. Kiểm tra đầu vào trước khi tạo tài nguyên Docker. Giải nén vào thư mục mới, tạo credential riêng, load byte image đã xuất, kiểm tra ID image, tạo project tên ngẫu nhiên lak-rebuild-*, với volume và network riêng theo project.

Cổng bản sao: MySQL 13310, PostgreSQL 15435; cổng Connect/dashboard dự kiến 18085/18501 khi các dịch vụ đó được bật ở bước CDC kế tiếp. Lượt này chỉ chạy hai DB và container công cụ tạm để đối soát nguồn, mart, hai mô hình và AppTest 8 trang. Không bật collector, applier, inference worker, scheduler hoặc dashboard server. Không sử dụng .runtime hay volume gốc. Dữ liệu tin tức được khôi phục từ snapshot, API key để trống; không tuyên bố fetch API mới.

Kết quả đạt chỉ xác nhận phạm vi restore CSDL/mô hình/AppTest. Kafka/Connect mới chưa có offsets tương thích với raw ledger bản sao, do đó chưa được bật pipeline hoặc thao tác demo trên bản sao. Bước sau phải bootstrap CDC đúng epoch/checkpoint và kiểm tra thay đổi mới, rồi mới chốt Phase 13.

Môi trường mới nằm trên cùng Docker engine với máy người dùng (có thể dùng chung cache/layer image), không phải bằng chứng đã thử máy vật lý/engine sạch. Bằng chứng load tar, checksum và volume/project mới được lưu rõ. Không tự xóa resource khi lỗi để bảo toàn chẩn đoán; hai DB bản sao có thể vẫn chạy. Stack gốc không bị dừng bởi script này.

Các source file compose sau giải nén được đổi cổng để cách ly. Đó là bước cấu hình môi trường dựng lại được ghi nhận, không phải sửa source ứng viên trên máy gốc. Các credential mới chỉ nằm trong .runtime của bản sao và không được đưa vào bản nộp.
