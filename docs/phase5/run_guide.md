# Pha 5 — Lịch sử dimension, chất lượng và đối soát

## Mục đích và đầu ra

Kho phải trả lời được vì sao dữ liệu được giữ lại, phiên bản sản phẩm nào được sử dụng, và dữ liệu nguồn có khớp số liệu phân tích không. `audit.pipeline_runs` lưu từng lần kiểm tra, `audit.quality_findings` lưu từng khóa/rule vi phạm. JSON ngoài database được lưu theo từng thư mục mới trong `evidence/phase5/run-*`.

Nền đầu vào được người dùng xác nhận: pha 4 PASSED, source Windows commit `f537de1`, sau bản vá UUID và truy vấn replay giữ `-infinity`. Kết quả runtime chi tiết của pha 5 phải được xác nhận trên máy người dùng, không suy ra từ unit test.

## Quy tắc lịch sử

- Sản phẩm: SCD2 cho tên, nhóm và mã danh mục. Khoảng `[valid_from, valid_to)` dùng **thời gian projector quan sát/áp dụng**, không phải ngày đặt hàng. Chưa thu thập thì không dựng ngược lịch sử.
- Đơn đã tồn tại giữ product_key/category_key cũ khi vẫn tham chiếu cùng product_id, kể cả đơn được cập nhật sau đó. Đơn mới lấy phiên bản hiện hành. Nếu product_id của đơn đổi, projector lấy phiên bản hiện hành của sản phẩm mới.
- Khách hàng: Type 1 cho giới tính và địa lý hồ sơ; cùng customer_key. Không coi đây là lịch sử địa chỉ giao hàng; địa bàn giao hàng nằm riêng trên fact.
- Giá catalog và size band ở staging, không tạo phiên bản dimension. Giá giao dịch ở fact là giá của đơn, không lấy giá catalog hiện tại để tính lại tiền.
- Xóa nguồn được phản ánh bằng cờ; giữ các fact và phiên bản đã lưu. Dữ liệu demo và đã xóa không đi vào view phân tích.
- Thành viên sản phẩm UNKNOWN có valid_from `-infinity`; giữ nguyên và đối soát bằng JSON PostgreSQL khi đọc toàn bộ lịch sử.

## Migration

Pha 2 đã cài cột, exclusion constraint chống chồng khoảng, unique current index và FK cho SCD2. Pha 5 **không tạo lại** schema hoặc sửa DDL nền. `sql/phase5/001_quality_history.sql` bổ sung hai index phục vụ audit và marker `lak-phase5-v1`. Script xác nhận exclusion constraint tồn tại. Kiểm thử PostgreSQL trực tiếp xác nhận chồng khoảng bị chặn và khoảng liền kề được nhận.

## Kiểm tra chất lượng

17 quy tắc bao gồm thành viên chưa biết, grain, khóa ngoại (cả bốn vai trò ngày), tiền chính xác, ngày, khoảng và phiên bản SCD2, danh mục fact theo phiên bản sản phẩm, loại demo khỏi phân tích, nhãn giao hàng, lỗi projector chưa giải quyết, và cảnh báo mốc thời gian.

Đối soát đọc toàn bộ trường nghiệp vụ từ MySQL/staging/DW so với dữ liệu Excel đã kiểm tra, cùng manifest/provenance và tổng tiền. Đây là kiểm tra cho lịch sử LAK đang cố định; nếu chủ ý thay đổi dữ liệu lịch sử, baseline cần được quản lý phiên bản trước, không sửa Excel để làm test xanh.

Cảnh báo ban đầu dự kiến: 880 đơn gửi trước đóng gói, 118 đơn dự kiến trước gửi, 0 đơn nhận trước gửi. Tổng số finding không nhất thiết là số đơn duy nhất vì một đơn có thể vi phạm nhiều quy tắc. Giữ nguyên dữ liệu và cảnh báo, không tự sửa ngày. Target thời gian giao hàng sai/thếu được để NULL theo quy tắc DW; pipeline ML sau này quyết định tiêu chí sử dụng.

Không log tên, số điện thoại, địa chỉ đầy đủ; findings lưu business key và rule. Mỗi run có kết quả riêng. Không đánh dấu các findings cũ biến mất; xem kết quả theo run_id mới nhất để biết trạng thái hiện tại.

## Kiểm thử thực tế

```powershell
Set-Location G:\LAK-Analytics
python -m unittest discover -s tests -p 'test_phase5*.py' -v
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_phase5.ps1
```

Runner dựng lại image hiện có, cập nhật collector/applier; không thay volume hoặc mật khẩu, không tạo connector mới. Sau đó: quality trước → fixture PostgreSQL rollback → demo SCD2/Type 1 qua CDC → quality sau và so sánh mã toàn bộ fact lịch sử. Marker PASS chỉ xuất hiện khi cả bốn bước đạt.

Demo tự tạo mã DEMO_SCD5_*, đổi tên/nhóm sản phẩm, đổi địa lý khách hàng, kiểm tra đơn cũ/đơn mới và giá catalog, rồi xóa dữ liệu demo tại nguồn. Soft-delete và phiên bản demo ở kho được giữ để truy vết. Nếu có sự cố lúc dọn demo, giữ bằng chứng và gửi log; không reset dữ liệu.

Fixture SQL chạy trong transaction rollback, gồm constraint và lifecycle retry. Identity sequence có thể tăng dù rollback, đây là hành vi bình thường, không phải mất dữ liệu. Fixture retry không thay thế kiểm thử sự cố worker thực tế đã làm ở pha 4 hoặc kiểm thử toàn hệ thống pha 12.

## Retry có kiểm soát

Sau khi **sửa nguyên nhân bên ngoài** (mã ánh xạ, cấu hình hoặc tài nguyên), có thể yêu cầu thử lại một projection error đã xác định:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/retry_phase5.ps1 -ErrorId 123
```

123 chỉ là ví dụ, phải lấy đúng error_id từ audit. OPEN → RETRYING tăng attempts một lần cho mỗi yêu cầu mới; yêu cầu trùng không tăng. Worker khởi động lại đọc lại raw event chưa processed, giữ checkpoint/payload. Khi processed, OPEN/RETRYING → RESOLVED. Không bỏ qua raw event không hợp lệ, không giả nhận thành công và không khẳng định sửa được poison event bằng cách bấm retry. Lỗi chưa xử lý làm quality gate thất bại.

## Giới hạn kiểm chứng

Unit test kiểm tra logic severity và retry. Máy chuẩn bị không có Docker/PostgreSQL/MySQL/PowerShell; toàn bộ DDL thực thi, constraint, CDC/SCD2 và đối soát runtime vẫn chờ kết quả người dùng. Chưa triển khai tin tức, mart, ML hoặc website trong pha này.
