# Trạng thái dự án

## Checkpoint mới nhất — pha 7 đã xác nhận, pha 8 chờ kiểm thử

Người dùng gửi `PHASE 7 MART AND OLAP CHECKS PASSED` và evidence
G:\LAK-Analytics\evidence\phase7\run-20261025T193240Z-3d53e43e.
Đã sửa hai dòng alias month_start trong src/marts/refresh.py sau lỗi SQL thực tế.
Chưa nhận toàn bộ JSON của run PASS và chưa biết commit mới của máy người dùng.
Không suy đoán số đo hiệu năng từ một dòng docker stats.

Pha 8 chuẩn bị snapshot RFM reference 2026-01-01, phân chia theo khách,
preprocessing train-only, chọn K 2–8 bằng validation, đánh giá test/baseline,
registry và artifact có checksum. Đã huấn luyện/roundtrip thật trên dữ liệu LAK
ở môi trường chuẩn bị; SQL capture/publish và Docker runtime còn chờ người dùng.
Các checkpoint dưới đây được giữ làm lịch sử.

## Checkpoint mới nhất — pha 6 đã xác nhận, pha 7 chờ kiểm thử

Người dùng xác nhận stored news PASS tại evidence/phase6/run-20261025T184339Z-2082b9cb,
API thật + after-api PASS tại run-20261025T185216Z-d98ec5d2 và DagRun Airflow success
+ PHASE 6 AIRFLOW EXECUTION CHECK PASSED tại run-airflow-20261025T190519Z.
Các đường dẫn đều ở G:\LAK-Analytics\evidence\phase6. Token được giữ tại máy người dùng,
không gửi cho trợ lý. Chỉ xác nhận một lần thực thi DAG; lịch news vẫn paused,
không tuyên bố đã vận hành hằng ngày lâu dài. Mẫu 35 nhãn tiêu đề vẫn chưa human-verified.

Pha 7 chuẩn bị mart/cube, 5 thao tác OLAP, đối soát từng dòng, fixture mutation rollback
và DAG refresh 15 phút; chưa có kết quả PostgreSQL/Airflow runtime pha 7.
Các mục dưới đây giữ lại để truy vết các checkpoint cũ.

## Checkpoint mới nhất — pha 5 đã xác nhận, pha 6 chờ kiểm thử

Người dùng xác nhận `PHASE 5 QUALITY AND SCD2 CHECKS PASSED` ngày 26/10/2026.
Evidence: G:\LAK-Analytics\evidence\phase5\run-20261025T182247Z-67e968f6.
Đã gửi marker PASS và đường dẫn quality-after.json; chưa cung cấp toàn bộ JSON.
Không suy đoán commit pha 5 của máy người dùng từ commit môi trường chuẩn bị.

Pha 6 bổ sung pipeline metadata tin tức vào kho mới, nguồn gốc raw, hash,
coverage, bridge, rà soát 35 tiêu đề có ghi rõ do AI và chưa human-verified.
73 kiểm thử Python pha 1–6 đạt; PostgreSQL seed, API thật, Airflow runtime còn
chờ kết quả trên máy người dùng. Giữ các checkpoint cũ dưới đây làm lịch sử.

## Checkpoint mới nhất — pha 4 đã xác nhận, pha 5 chờ kiểm thử

Ngày 26/10/2026, người dùng báo `PHASE 4 CDC CHECKS PASSED` và HEAD
`f537de1`, sau commit UUID `9afa9e5` và CDC `115570c`.
Log chi tiết trước đó đã xác nhận snapshot 3282/15/10000, tiền khớp và CRUD.
Người dùng gửi marker PASS cho toàn bộ runner sau sửa replay đọc `-infinity`.
Chưa có bản sao đầy đủ log PASS cuối trong workspace; đường dẫn evidence hiển thị
bị PowerShell cắt ngắn, vì vậy không ghi đoán tên run.
Hai thư mục evidence/phase2 chưa track được giữ nguyên; không phải lỗi source.

Pha 5 bổ sung quality audit, migration index và marker, kiểm thử SCD2/Type 1
qua CDC, fixture PostgreSQL rollback và lifecycle retry. Đã kiểm thử offline;
PostgreSQL/CDC thực tế vẫn chờ người dùng. Các mục cũ dưới đây là lịch sử checkpoint.

## Cập nhật ngày 26 tháng 10 năm 2026

Người dùng đã xác nhận pha 3 sau Fix2 PASS trên Windows, HEAD c311716:
14 test đạt, nạp hai lần cùng fingerprint, 4 constraint bị từ chối đúng,
demo INSERT/UPDATE/DELETE không đổi lịch sử, final-check PASS.
Bằng chứng do người dùng gửi trong log:
G:\LAK-Analytics\evidence\phase3\run-20261025T170534Z-eb946ea2.
Nguồn có 3282 khách, 15 sản phẩm, 10000 đơn, 43297 dòng provenance.
history_state_sha256: e3efd13dee43746344c3cc2ad5402744aca705fd3f48dc09530da6775910246a.

Pha 4 được chuẩn bị bằng patch nối tiếp: Debezium/Kafka/PostgreSQL và hai
worker, phép thử snapshot/CRUD/replay/recovery. Chưa có xác nhận runtime pha 4
ở môi trường trợ lý (không Docker/DB), chờ kết quả máy em trước pha 5.
Các mục phía dưới là trạng thái checkpoint trước khi có cập nhật này.

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
