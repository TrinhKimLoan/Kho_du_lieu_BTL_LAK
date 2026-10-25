# Pha 3 bản vá tên cột có chữ số

Log người dùng xác nhận patch pha 3 đã áp dụng, sáu test offline đạt, MySQL
Healthy và install passed với binlog ROW/FULL, server_id 274103.
load-history dừng ValueError Invalid internal SQL identifier trước khi commit.

Nguyên nhân: helper identifier chỉ nhận [a-z_]+, trong khi provenance dùng
file_sha256 và payload_sha256. Sửa thành [a-z_][a-z0-9_]*, tiếp tục quote bằng
backtick và truyền giá trị bằng tham số. Không nới lỏng dấu cách, dấu chấm,
dấu quote hoặc dấu phân cách lệnh SQL.

Thêm ba test: toàn bộ identifier thuộc hợp đồng, identifier sai và câu lệnh
import_rows giữ payload trong tham số. Đây là hồi quy ở chính đường dựng câu
lệnh đã lỗi, không phải kiểm thử MySQL giả định.

Không đổi DDL, ownership, source_epoch, SQL checksum, mật khẩu hoặc volume.
Không reset nguồn. load_history rollback khi lỗi; chạy lại runner sẽ nạp lại
và đối soát. Chưa xác nhận MySQL pha 3 đạt trước khi người dùng gửi log mới.

Lưu LAK-Analytics-Phase3-Fix1.zip tại G:\, giải nén tới G:\LAK-Phase3-Fix1,
chạy apply_update.py --target G:\LAK-Analytics. Sau đó chạy ba test hotfix và
scripts/run_phase3.ps1. Runner tự rebuild image chứa src mới, dùng lại cache
thư viện và giữ nguyên thông tin kết nối. Không cần tải lại gói pha 3 trước đó.
