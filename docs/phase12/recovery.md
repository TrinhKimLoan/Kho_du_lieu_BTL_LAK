# Báo cáo recovery Phase 12

| Worker | Bằng chứng | Kết quả |
|---|---|---|
| Collector | phase12/recovery-20261026T080142Z/collector-recovered.json | Thay đổi commit khi worker dừng được xử lý bù; insert/update/delete đạt |
| Applier | phase12/recovery-continue-20261026T080507Z/applier-recovered.json | Thay đổi commit khi worker dừng được xử lý bù; insert/update/delete đạt |
| ML inference | run-20261026T080552Z-585e9b00/seed.json, checks.json, cleanup.json | 2 job pending khi worker dừng; queue bền vững qua restart; replay idempotent; dọn demo nguồn |

Collector và applier giữ cùng hash lịch sử fact đã ghi trong release.json. ML xác nhận nguồn → inference thêm/sửa/xóa, RFM monetary 200.000 → 300.000 VND rồi NO_HISTORY sau xóa, prediction ban đầu bất biến, tick ngày tham chiếu chỉ áp dụng demo và không retrain. Business facts giữ nguyên; evidence và prediction history được bảo toàn.

Phép thử là dừng/khởi động có kiểm soát từng worker nghiệp vụ collector, applier, inference. Không mô phỏng mất điện, hỏng volume, partition mạng hoặc failover database/broker. Không có bằng chứng crash recovery cho mọi tiến trình hạ tầng. Các log kèm theo giữ nguyên sự kiện dừng/khởi động thực tế; không suy diễn thời gian phục hồi thành SLA.

Lỗi thao tác ban đầu: PowerShell/Python quoting làm `encoding="utf-8"` mất dấu nháy, gây NameError; đã chuyển cách truyền Python qua stdin và tiếp tục. Collector đã phục hồi trước lỗi đó; kết quả applier/ML nằm trong lượt tiếp tục. Không reset volume hay khởi tạo lại dữ liệu.
