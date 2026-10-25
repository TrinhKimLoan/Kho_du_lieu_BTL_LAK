# Pha 4 CDC giao dịch đầu cuối

## Mục đích

Pha 3 đã được người dùng xác nhận MySQL PASS sau Fix2. Pha 4 nối MySQL hiện
có tới Debezium, Kafka và PostgreSQL, thử snapshot, thêm/sửa/xóa, replay và
worker recovery. Chưa xây mart/cube, giao diện, model hoặc pipeline tin mới.
SCD2 tối thiểu phục vụ chiếu sản phẩm; kiểm thử chất lượng/SCD2 chuyên sâu
thuộc pha 5. Không khẳng định HA hoặc exactly-once tuyệt đối.

Giữ một thư mục dự án G:\LAK-Analytics. Tải LAK-Analytics-Phase4-Patch.zip
vào G:\, giải nén tới G:\LAK-Phase4-Patch rồi áp dụng apply_update.py
theo lệnh trong chat. Gói chỉ gồm thay đổi, kiểm tra SHA256 và sao lưu
tệp cần sửa, không ghi đè Git, Excel, mật khẩu hoặc bằng chứng người dùng.

## Chạy sau khi áp dụng patch

```powershell
Set-Location G:\LAK-Analytics
python -m unittest discover -s tests -p test_phase4_codec.py -v
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_phase4.ps1
```

Mở Docker Desktop ở Linux containers. Test offline chỉ cần Python 3.11 trở
lên, không cài Kafka/PG driver lên host. Lần đầu có thể mất vài phút tải image,
build cdc-tools và chờ snapshot. Không chạy reset hoặc xóa volume khi chờ.

Runner giữ mật khẩu MySQL cũ, chỉ thêm LAK_POSTGRES_PASSWORD và LAK_CDC_PASSWORD
nếu chưa có trong .runtime/lak.env. Không gửi tệp này. Nó không sửa .env cũ.

| Dịch vụ | Vị trí |
| --- | --- |
| MySQL nguồn | Giữ cổng 3310, lak_source và volume mysql_source_data của LAK |
| PostgreSQL kho | Cổng 5435 trên 127.0.0.1, DB lak_warehouse, volume riêng |
| Kafka | Chỉ nội bộ Docker, volume kafka_data riêng |
| Connect | Cổng 8085 trên 127.0.0.1, connector lak-source-v1 |
| collector/applier | Hai worker chạy liên tục trong Docker project lak-analytics |

MySQL service giữ nguyên cấu hình có từ pha 3. Cổng mới bận thì gửi lỗi;
không dừng/xóa dịch vụ khác hoặc docker compose down -v để ép chạy.

## Những phép kiểm tra runner thực hiện

1. Cấp quyền đọc binlog cho tài khoản CDC qua Unix socket trong MySQL hiện có.
2. Kiểm tra nguồn bằng loader/reconciliation pha 3, xác nhận source epoch.
3. Tạo kho từ DDL pha 2 nếu DB mới rỗng, kiểm tra ownership/checksum nếu có sẵn.
4. Chuyển provenance đã kiểm tra sang raw, giữ encoding float-repr của Fix2.
5. Tạo topic một partition và cấu hình connector nếu chưa có, không xóa offset.
6. Chạy hai worker, đợi đủ snapshot và so toàn bộ trường staging/fact với nguồn.
7. INSERT/UPDATE/DELETE demo: kiểm tra tiền và thời điểm nhận thực tế tới fact.
8. Đọc Kafka từ offset 0: không thêm raw coordinate lặp, cùng tọa độ khác bytes phải lỗi.
9. Đưa raw qua applier lần nữa: fact lịch sử và version sản phẩm phải giữ nguyên.
10. Dừng hai worker, commit đơn mới ở nguồn, chạy lại và xác nhận xử lý bù,
    sau đó cập nhật/xóa demo và đối soát cuối.

Kết quả mong đợi: 17 test offline đạt và PHASE 4 CDC CHECKS PASSED.
Mỗi bước có JSON passed=true trong evidence/phase4/run-... cùng phase4.log,
không chỉ một dòng chữ trong console. Dữ liệu lịch sử vẫn 10000 fact,
3282 khách, 15 sản phẩm; tiền hàng và tổng thanh toán khớp pha 3.

## Hợp đồng xử lý

Collector giữ key/value bytes và hash phân biệt null/empty. Raw cùng next_offset
commit trước Kafka acknowledgment. Tọa độ gồm epoch/topic/partition/offset;
trùng tọa độ cùng bytes là replay, khác bytes phải dừng.

Applier ưu tiên snapshot dimension và chờ đủ khóa cho order. Giao dịch live
đợi END và đủ data_collections của ba bảng được theo dõi; xử lý theo END
offset trên topic metadata một partition. Trong giao dịch dùng total_order.
Các cập nhật cùng entity được chiếu trạng thái cuối nhưng count vẫn là số
sự kiện được xác minh. Ledger, staging và fact commit cùng transaction.

So replay source event theo operation, key, vị trí nguồn, before/after nghiệp
vụ; timestamp xử lý thay đổi không tự tạo phiên bản mới. END lặp count 0 đi
qua nhánh ledger đã có chỉ khi raw gốc vẫn đủ và không mâu thuẫn. Không bỏ qua
mọi END thiếu dữ liệu. Snapshot/replay giữ version đã gắn với fact lịch sử.

Delete đơn thành soft-delete DW. Tombstone chỉ lưu raw, không xóa/trừ tiền
lần nữa. Demo bị loại bởi view phân tích lịch sử. Unknown timezone của
DATETIME vẫn được công bố; không tự đổi mốc nghiệp vụ sang giờ khác.

Raw parse/projection lỗi được giữ lại, có heartbeat/error; không gọi APPLIED
khi transaction chưa đủ hoặc còn lỗi. Không tự bỏ dữ liệu lỗi để báo thành công.

## Tham chiếu cấu hình

Tài liệu chính thức Debezium MySQL 3.2:
https://debezium.io/documentation/reference/3.2/connectors/mysql.html

Trong adaptive_time_microseconds, DATETIME không fractional seconds là epoch
milliseconds, khác DATETIME(6). Các cột TIMESTAMP updated_at không dùng làm
thời gian giao nhận hoặc nhãn mining. Tiền nhận dạng decimal string, không float.

## Mức kiểm chứng

Trợ lý chạy test codec, kiểm tra Python/YAML và thử patch trên bản sao nguồn.
Chưa có Docker/Kafka/PG/PowerShell ở môi trường trợ lý để xác nhận runtime.
Phép thử đầu cuối chỉ được đánh dấu đạt sau log máy em. Nếu FAILED, gửi phần
lỗi và Evidence, không chuyển pha 5.
