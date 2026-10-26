# Khởi tạo CDC sau khi restore logic

Chạy bootstrap_rebuild.py với đường dẫn bản sao đã đạt restore CSDL/mô hình. Host script kiểm tra restore.json, project prefix ngẫu nhiên, nhãn ownership của hai DB và tên volume theo project. Từ chối thư mục gốc; mọi Compose action dùng project bản sao và các compose đã đổi cổng. Không dùng ops.py của project gốc cho thao tác này.

## Cách bootstrap

1. Bật Kafka và Connect mới. Tạo tài khoản lak_cdc bằng credential riêng trong bản sao, không dùng password từ project gốc.
2. Đối soát toàn bộ field nguồn MySQL với Excel hợp đồng và staging/DW đã restore. Lưu hash trạng thái business fact và model registry vào epoch-plan.json.
3. Tạo source_epoch mới trong MySQL identity và PostgreSQL pipeline identity. Chuyển epoch staging sang mới, đặt bốn trường thứ tự binlog về 0. Giữ nguyên payload staging, fact, khóa surrogate, SCD2, mô hình và lịch sử dự đoán.
4. Raw events, ledger, checkpoints cũ được giữ dưới epoch cũ để truy vết. Collector mới không dùng checkpoint epoch cũ; các topic mới bắt đầu ở offset 0. Không xóa volume hoặc dùng TRUNCATE CASCADE.
5. Đăng ký connector mới `snapshot.mode=no_data`: chỉ lấy schema và bắt đầu stream từ binlog hiện hành. Dữ liệu nền đã được restore và đối soát tường minh; không nạp lại toàn bộ snapshot lên fact lịch sử. Debezium mô tả no_data tại https://debezium.io/documentation/reference/stable/connectors/mysql.html .
6. Bật collector/applier; kiểm tra caught-up, snapshot reconciliation và demo thêm/sửa/xóa mới. Tên phép kiểm tra snapshot ở đây là đối soát trạng thái, không phải bằng chứng Debezium đã phát READ snapshot mới.
7. Xác minh mô hình/config đã lưu, seed demo trong lúc inference worker chưa bật, bật worker rồi chạy kiểm tra insert/update/delete, prediction bất biến, tick demo, queue idempotence và cleanup. Không train.
8. Refresh mart, xác nhận business fact hash/model registry không đổi; có checkpoint bền vững ở epoch mới và connector/task RUNNING. Chạy 8 trang AppTest, bật dashboard cổng 18501. Bật Airflow mới, kiểm tra scheduler heartbeat và unpause riêng DAG mart; API key để trống, không unpause fetch API tin tức.

`dw.fact_sales.source_epoch` trên các fact lịch sử vẫn là provenance nguồn cũ, trong khi staging và pipeline đã chuyển epoch vận hành mới. Đây là thay đổi provenance có chủ đích: fact cũ không bị ghi lại chỉ vì chuyển môi trường; thay đổi mới qua CDC cập nhật metadata của bản ghi tương ứng. Không gọi `src.cdc.cli init` mặc định trên bản sao này: config mặc định initial khác no_data và phải bị từ chối thay thế ngầm.

## Bằng chứng và giới hạn

Thư mục evidence/phase13/cdc thuộc bản sao lưu plan, log, các JSON và bootstrap.json. Chỉ báo đạt khi chuỗi kiểm tra trên hoàn tất. Phase 13 vẫn chờ đóng gói tài liệu/bằng chứng cuối. Một số bước thay đổi epoch đi qua hai DB, không có distributed transaction; nếu bị ngắt giữa chừng phải xem plan và khôi phục tường minh. Script chặn chạy lại khi đã có thư mục bootstrap để tránh reset metadata trên pipeline đã chạy; gửi lỗi/bằng chứng thay vì tự xóa thư mục.

Bản sao dùng cùng Docker engine với project gốc nhưng thư mục/network/volume/credential/cổng riêng. Các bước không chứng minh chạy trên máy/engine vật lý khác. Chưa có quyền đảm bảo không mất thay đổi nếu có client khác ghi MySQL giữa restore và bootstrap; vì vậy không ghi trực tiếp hoặc thao tác demo trên bản sao trước khi phép kiểm tra này đạt. Các phép đối soát phát hiện sai khác dữ liệu nền trước khi đăng ký connector.
