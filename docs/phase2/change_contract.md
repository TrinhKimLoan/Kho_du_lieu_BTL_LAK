# Hợp đồng thay đổi và chất lượng

Đây là quy tắc để triển khai ở giai đoạn 3–5, chưa phải worker đã chạy.

## Định danh và thứ tự

1. Mỗi lần cài nguồn độc lập có source_epoch UUID bền vững. Kafka topic hoặc
   binlog khởi tạo lại là một thế hệ khác; không so sánh offset/vị trí giữa epoch.
2. Raw duy nhất theo (source_epoch, topic, partition_id, kafka_offset).
   Cùng tọa độ và cùng bytes là replay. Cùng tọa độ nhưng khác checksum là lỗi
   nghiêm trọng, không được ON CONFLICT DO NOTHING để che khác biệt.
3. Lưu raw cùng checkpoint next_offset trong một transaction PostgreSQL;
   chỉ xác nhận Kafka sau commit. Checkpoint nằm ngoài retention Kafka phải
   báo lỗi có hướng dẫn, không tự nhảy latest để bỏ dữ liệu.
4. Metadata transaction topic có một partition. Applier xét END theo offset
   tăng trên topic đó; không lấy raw event_id của các partition dữ liệu làm
   thứ tự commit nguồn. Trong một transaction dùng total_order, đợi đủ dữ liệu.
5. expected_data_events đếm đúng data_collections của ba entity được theo dõi.
   Không tính metadata, tombstone hoặc bảng provenance không được capture vào
   số sự kiện cần chờ. BEGIN/END lặp phải kiểm tra tương thích với ledger.
   applied_data_events đếm các sự kiện dữ liệu được xác minh, không đếm số dòng
   fact thay đổi sau khi squash nhiều update cùng entity trong một transaction.
6. Snapshot op=r có đường xử lý riêng: upsert idempotent, kích hoạt chỉ sau
   khi có dimension phù hợp, đối soát đủ nguồn trước khi đánh dấu bootstrap xong.
7. Vị trí entity so sánh tuple số (file_number, position, row_number, total_order)
   trong cùng epoch, không so chuỗi tên file hoặc offset Kafka khác partition.
   Giá trị chưa đủ để xác định thứ tự phải chờ/báo lỗi, không tự đoán.

Nguồn MySQL sẽ có foreign key chống order tham chiếu khách/sản phẩm không tồn
tại. Trong kho, key 0 vẫn có vai trò xử lý thiếu chiều chưa tới hoặc giá trị
chưa biết, kèm quality finding. Key 0 không dùng để che vĩnh viễn lỗi ghép nguồn.

## Thay đổi entity

| Sự kiện | Staging | DW và tác động phía sau |
| --- | --- | --- |
| Snapshot / INSERT customer | Trạng thái hiện có với vị trí nguồn | Upsert dim_customer Type 1, xử lý fact chờ nếu có |
| UPDATE customer | Cập nhật đủ cột thuộc hợp đồng | Đổi hồ sơ hiện tại; không sửa địa bàn giao trên fact cũ |
| INSERT product | Trạng thái sản phẩm | Tạo phiên bản quan sát đầu |
| UPDATE product | Cập nhật đủ cột | Tên/nhóm/category đổi tạo SCD2; đổi giá danh mục không tính lại giá đơn |
| INSERT order | Lưu một row hợp nhất, kiểm tra giá/khóa | Một fact theo order_id; tra ngày/chiều và phân biệt demo |
| UPDATE order | So phiên bản, thay đủ cột mới | Sửa cùng fact, sửa cả ngày, khách, sản phẩm, địa bàn và tiền khi chúng đổi |
| DELETE order | Giữ before/key, source_is_deleted=true | Soft delete fact; loại khỏi view phân tích, mart và RFM |
| DELETE dimension entity | Giữ trạng thái xóa | Không cascade xóa fact; giữ surrogate lịch sử và cờ xóa |
| Kafka tombstone | Lưu raw | Không tính thêm một lần xóa hoặc trừ doanh thu |
| Replay / sự kiện cũ | Ghi nhận idempotence / stale | Không tạo fact/version dimension/biến động tiền lặp |

Một transaction chiếu staging, dimension, fact và ledger nguyên tử; không công
bố fact nửa cập nhật. Khi mart/cube được triển khai, phần cần đồng bộ cùng fact
phải ở cùng transaction hoặc có watermark nhất quán công khai. RFM/inference
được phép bất đồng bộ nhưng phải hiện pending/computed_at/model_version.
Giai đoạn 2 chưa tạo queue hay schema ML; chúng được triển khai đúng giai đoạn 10.

Sửa order có thể ảnh hưởng khách cũ/mới, kỳ cũ/mới, địa bàn cũ/mới, category cũ/mới.
Applier phải giữ before/current state để cập nhật cả hai phía. Không chỉ enqueue
khách mới hoặc cộng tiền mới mà bỏ tiền cũ. Demo không thay lịch sử đánh giá.

## Gate và lỗi

- Lỗi bắt buộc: không parse được số/ngày, quantity không hợp lệ, tiền sai,
  sự kiện mâu thuẫn, transaction thiếu hoặc khóa nguồn vi phạm hợp đồng.
- Cảnh báo thời gian: giao đi trước đóng gói, dự kiến tới trước giao đi;
  không đổi raw để ép hợp lệ. Khác địa chỉ hồ sơ/đơn là quan sát, chưa tự là lỗi.
- Nhãn giao âm hoặc thiếu mốc không dùng cho RF; tiền đơn hợp lệ vẫn được giữ.
- Chưa có SLA nên không quảng bá tỷ lệ trễ như KPI cam kết đã kiểm chứng.

Raw được giữ để truy vết. Lỗi parse còn nguyên bytes trong raw, không ép vào
kiểu typed staging sai. Lỗi nghiệp vụ đã parse có thể nằm staging cùng finding,
nhưng transaction không được có ledger APPLIED cho trạng thái không đạt gate.
Triển khai phải dùng transaction/savepoint hoặc bước kiểm tra ngoài projection
để lưu finding/error sau khi rollback phần chiếu, không để lỗi bị rollback mất.

Nếu DW còn trạng thái tốt trước đó khi một update mới bị lỗi, phải hiển thị
chưa đồng bộ/error; không báo kho đã mới nhất chỉ vì còn đọc được fact cũ.
Retry sau sửa nguyên nhân dùng lại raw, không xóa volume hay lịch sử ledger.

## Tin tức

Polling so khóa/hash là luồng khác binlog. Ngày đăng, indexed_at, fetched_at
phải phân biệt. Reclassify thay nhãn và bridge có rule_version, không gọi đây
là thay đổi từ nhà xuất bản khi chỉ thay bộ luật trong hệ thống.
Status PARTIAL khi hết page cap/thiếu phân trang; COMPLETE theo cấu hình query
chứ không phải chứng minh mọi bài của thị trường đều được thu thập.

Các điều kiện và nhánh khôi phục sẽ có test runtime ở giai đoạn 4–5 và 12.
Các constraint và fixture giai đoạn 2 không thay thế những bằng chứng đó.
