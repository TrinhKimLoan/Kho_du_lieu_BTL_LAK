# Phase 10 — ML dùng cùng CDC, giữ cố định model

Chỉ áp dụng sau Phase 9 chạy đạt. Đã ghi nhận bằng chứng người dùng: evidence/phase9/run-20261026T060146Z-fe4c3559; model RF rf-delivery-4a60b2b333abc46ef35bb5f6; MAE 18,7329 giờ so với baseline 18,8346 giờ. Mức cải thiện nhỏ (~6,1 phút); không suy ra hiệu quả vận tải thật.

## Chạy trên máy triển khai

Giữ các dịch vụ Phase 4–9 đang chạy, file .runtime/lak.env và các artifact model. Sau khi áp dụng ZIP patch, chạy:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_phase10.ps1
```

Script dựng image suy luận riêng; chạy 12 unit test mới; xác minh đầy đủ mô hình Phase 8/9 trong DB và file; tạo schema/outbox trigger cùng config ghim model; tạo backlog RFM hiện tại và các đơn đã khai báo giao đi nhưng chưa có kết quả nhận. Không tạo dự đoán trực tuyến giả cho 10.000 đơn lịch sử đã nhận.

Để kiểm chứng queue bền vững, script tạm dừng riêng inference-worker trong tối đa 10 giây trước khi tạo một đơn DEMO_ML10_... trong MySQL. Collector/applier/DB/Kafka vẫn chạy. Sau khi xác nhận job tồn tại trong PostgreSQL, worker khởi động lại, xử lý backlog rồi kiểm tra đầu cuối:

1. Insert đơn demo chưa nhận: RFM F=1, M=200.000; dự đoán giao hàng lưu đầu vào số lượng 2 cùng model ID.
2. Đổi ngày tham chiếu cho preview demo thêm một ngày dù không tạo giao dịch mới: R tăng 1; không đổi ngày tham chiếu kinh doanh.
3. Update nguồn: M=300.000, đã nhận sau 27 giờ. RFM được cập nhật; outcome ghi actual/error; input ban đầu số lượng 2 và predicted_hours giữ nguyên.
4. SQL thử sửa dự đoán ban đầu bị trigger từ chối trong transaction rollback.
5. Delete nguồn demo: RFM NO_HISTORY, outcome DELETED, giữ dự đoán/hồ sơ gốc.
6. Đưa lại job đã xử lý vào queue: receipt nhận diện lặp, không nhân đôi lịch sử hoặc sửa dự đoán.
7. Đối chiếu hash business fact và registry: lịch sử kinh doanh không thay đổi; không có model mới hoặc train lại.

Worker mới được giữ chạy sau kiểm thử; compose profile là ml-inference. Lần khởi động dự án sau cần thêm `-f infra/compose.inference.yaml --profile ml-inference` vào danh sách Compose hiện có. Không dùng down/reset volume để sửa lỗi.

## Schema và cơ chế

- ml.inference_config ghim hai model version, ngày tham chiếu logic. Registry READY/không active của RF từ Phase 9 không bị âm thầm sửa; config Phase 10 công khai lựa chọn model để suy luận.
- Trigger AFTER INSERT/UPDATE trên dw.fact_sales tạo job trong cùng transaction với projector. Rollback fact đồng nghĩa rollback job. Không sửa image collector/applier hay bootstrap CDC. Update customer của đơn sẽ enqueue cả customer cũ và mới.
- ml.inference_jobs có khóa chống lặp theo source_epoch/event_id, loại công việc, thực thể, model, ngày tham chiếu. Payload giao hàng được chụp lúc sự kiện vào fact, bao gồm input đã biết và phần outcome riêng. Queue nằm trong volume PostgreSQL.
- Một worker giữ advisory lock; lấy job bằng FOR UPDATE SKIP LOCKED. Kết quả, receipt và trạng thái DONE commit cùng nhau; tiến trình bị dừng giữa chừng thì transaction rollback và job còn chờ. Lỗi retry 5 lần, sau đó FAILED và heartbeat báo lỗi; không âm thầm bỏ job.
- RFM được tính lại từ trạng thái fact mới nhất lúc worker xử lý, theo ngày tham chiếu của job. Đây là lịch sử snapshot quan sát bởi worker, không bảo đảm ghi riêng mọi trạng thái trung gian của nhiều sự kiện đến nhanh.
- RFM chỉ lấy các đơn cùng cohort is_demo, chưa xóa, packed_at trước ngày tham chiếu; F DISTINCT do order_id unique; M tiền hàng. Khách không còn đơn -> NO_HISTORY; M=0 -> NO_POSITIVE_VALUE. Không đưa các trường hợp đó vào pipeline có miền M>0.
- ml.rfm_assignment_history lưu input/hash/model/nhóm; ml.rfm_current_assignments trỏ đến job mới nhất cho từng customer/cohort/model/ngày tham chiếu. Để xem hiện tại, lọc ngày theo inference_config; preview demo và ngày cũ là snapshot riêng. Mã cụm không phải thứ hạng VIP.
- ml.live_delivery_predictions là dự đoán đầu tiên cho mỗi order/cohort, không UPDATE/DELETE được. Thời điểm dự đoán là khi worker quan sát khai báo dispatched_at; có enqueued_at/observed_at/predicted_at, không khẳng định đã dự đoán đúng tức khắc tại mốc lịch sử. Nguồn chưa có status giao thực tế; dispatched_at phải được nhập tại lúc giao đi, không dùng làm lịch tương lai.
- Đơn đã có received_at trước khi lần đầu worker thấy sẽ SKIPPED_ALREADY_RECEIVED, không dùng outcome để tạo dự đoán ban đầu. Sau khi có dự đoán, các sự kiện chỉ append outcome. Nếu dispatched_at bị sửa sau đó: DISPATCH_CORRECTED và không tính error với nhãn không tương thích. Thời gian âm: INVALID_TIME. Nhận chưa có: PENDING. Xóa: DELETED.
- ml.delivery_outcome_history lưu các revision kết quả; không ghi đè dự đoán gốc. Các bảng demo có is_demo và chỉ tiêu kinh doanh vẫn dùng dw.v_sales_analysis. Huấn luyện Phase 8/9 cũng loại demo. Pipeline không train lại.
- Artifact chỉ được mount đọc. Worker kiểm tra checksum trước khi nạp và cache model trong bộ nhớ. Thay đổi model phải qua cấu hình có kiểm soát; Phase 10 không tự chuyển sang phiên bản mới.

## Đổi ngày tham chiếu khi không có giao dịch mới

Ngày logic ban đầu 2026-01-01 giữ theo dataset. Không tự lấy đồng hồ máy để biến tất cả khách thành lâu không mua. Khi chủ động đổi ngày, CLI advance-reference cập nhật config, ghi ml.rfm_reference_history và enqueue lại tất cả khách trong một transaction, dù không có event mới. Không cho lùi ngày; việc dùng model cũ cho ngày mới phải được hiểu là suy luận bằng model cố định với phân phối có thể thay đổi.

Ví dụ cú pháp bên trong inference-tools:

```text
advance-reference --date 2026-01-02 --reason daily-logical-clock --evidence-dir /opt/project/evidence/phase10/clock-UNIQUE
```

Đây là thao tác đổi ngày thật; không cần chạy để kiểm thử Phase 10 vì script dùng preview demo riêng. Không gắn thêm lịch tự động theo ngày hệ thống vào bộ lịch sử mô phỏng.

## Lỗi và bằng chứng

Mỗi lần chạy tạo evidence/phase10/run-...: init.json, seed.json, status.json, checks.json, cleanup.json, check.json và phase10.log. Script cố gắng khởi động lại worker và dọn nguồn demo trong finally; nếu cleanup thất bại, tổng check sẽ FAILED. Các artifact và lịch sử dự đoán minh chứng vẫn giữ để xem.

FAILED job được xem trong ml.inference_jobs.safe_error. Sau khi sửa nguyên nhân, CLI retry-failed đưa chúng về PENDING; không xóa queue. Không sửa fingerprint schema hoặc file model để ép qua kiểm tra.

## Giới hạn xác nhận

Unit test Python kiểm tra input live tương đương input huấn luyện, không dùng outcome/PII, giữ dự đoán gốc, sửa dispatch, thời gian âm, feature thiếu/mới và từ chối model sai. Không coi các test này là bằng chứng CDC, SQL trigger, Docker hay worker đã chạy thành công. Các phần đó cần script chạy trên máy người dùng. Chỉ chốt Phase 10 sau khi checks.json và check.json passed.
