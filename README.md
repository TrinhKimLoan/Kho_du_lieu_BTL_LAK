# LAK Analytics

Bản nâng cấp độc lập từ LAK, thực hiện theo `docs/upgrade_plan.md`.
Đây là bản nâng cấp đến pha 6, chưa phải sản phẩm hoàn chỉnh.

Hướng dẫn chạy mới nhất: `docs/phase6/run_guide.md`.
Giai đoạn 0 đã được người dùng xác nhận PASS trên Windows, commit `f214c8d`.
Giai đoạn 1 đã được người dùng xác nhận PASS trên Windows, commit `3e43b27`.
Giai đoạn 2 đã được người dùng xác nhận PostgreSQL PASS, commit `3ec2598`.
Thư mục cố định là `G:\LAK-Analytics`. Pha 3 có MySQL nguồn, loader và demo;
đã được người dùng xác nhận runtime PASS sau Fix2. Pha 4 CDC đã được người dùng xác nhận PASS tại commit f537de1.
Pha 5 chất lượng/SCD2 đã được người dùng xác nhận PASS.
Pha 6 tin tức đang chờ kiểm thử dữ liệu lưu sẵn, API thật và DAG Airflow. Chưa triển khai ML/giao diện mới.

## Phạm vi đã xác nhận ngày 25 tháng 10 năm 2026

Giữ nghiệp vụ bán hàng và tin tức của LAK. Giảng viên đã yêu cầu bổ sung
tối thiểu hai thuật toán và phần tin tức trong buổi demo. Giữ K-Means phân
khúc khách hàng và Random Forest Regressor dự đoán thời gian giao hàng theo
điều kiện dữ liệu trong kế hoạch. RFM là đặc trưng, không phải thuật toán thứ ba.
Không chuyển Random Forest thành hạng mục tùy chọn chỉ vì slide hướng dẫn chung.

Chỉ một sinh viên thực hiện cùng trợ giúp của AI. Không tạo phân công nhóm.
Ưu tiên hoàn thành và kiểm thử sản phẩm. Báo cáo môn học và slide làm sau.
Tài liệu kỹ thuật và bằng chứng từng giai đoạn vẫn được lưu để làm đúng sản phẩm.

## Bắt đầu trên Windows

Giải nén để có thư mục `G:\LAK-Analytics`, tách khỏi `G:\CommerceInsight`
và thư mục LAK gốc. Không ghi đè dự án cũ.

Chạy trong PowerShell tại thư mục chứa README này:

```powershell
Set-Location G:\LAK-Analytics
python scripts/verify_phase0.py
git log -1 --oneline
```

Nếu máy chỉ nhận Python Launcher, dùng `py scripts/verify_phase0.py`.
Bộ kiểm tra giai đoạn 0 chỉ dùng thư viện chuẩn Python 3.11 trở lên,
không cần cài pytest, pandas, PostgreSQL hoặc Docker.
Kết quả mong đợi: `PHASE 0 CHECKS PASSED` và một commit mốc giai đoạn 0.

Chưa chạy Docker Compose ở mốc này. Cấu hình LAK gốc còn dùng cổng 5433,
trùng cổng PostgreSQL trong cấu hình CommerceInsight đã gửi. Giai đoạn triển khai
hạ tầng sẽ cấp project, topic, cổng và volume riêng, không xóa volume cũ.

## Đầu ra giai đoạn 0

- `docs/current_state.md`: chức năng thực sự có và giới hạn kiểm chứng.
- `docs/component_inventory.md`: danh sách giữ lại, sửa, thêm và không dùng.
- `docs/upgrade_plan.md`: kế hoạch người dùng gửi, giữ nguyên nội dung.
- `docs/confirmed_scope.md`: xác nhận mới nhất của người dùng và thứ tự làm việc.
- `docs/architecture.md`: luồng hiện tại và mục tiêu.
- `docs/baseline_files.json`: fingerprint từng tệp LAK gốc.
- `scripts/verify_phase0.py`: kiểm tra lại tính nguyên vẹn và các test nguồn.
- `evidence/phase0/check.json`: bằng chứng kiểm tra trong môi trường trợ lý.

Bộ giai đoạn 1 có `scripts/profile_lak_data.py`, `docs/data_dictionary.md`,
`docs/data_quality_profile.md`, `docs/business_definitions.md` và bằng chứng riêng.
Thiết kế giai đoạn 2 ở `docs/phase2`, DDL ở `sql/phase2`. Pha 3 dùng compose
riêng `infra/compose.lak.yaml`, không dùng docker-compose.yml LAK cũ.
Pha 4 nối CDC đầu cuối, dùng lại nguồn MySQL của pha 3 và thêm volume kho/Kafka.
verify_phase0 xác minh byte checkpoint gốc; không dùng làm gate chung sau khi
các pha sau đã chủ động sửa tệp, ví dụ .gitignore trong pha 3.
