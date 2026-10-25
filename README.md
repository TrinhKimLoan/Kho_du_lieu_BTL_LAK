# LAK Analytics

Bản nâng cấp độc lập từ LAK, thực hiện theo `docs/upgrade_plan.md`.
Đây là mốc giai đoạn 0, chưa phải sản phẩm hoàn chỉnh.

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

Bước kế tiếp là giai đoạn 1: kiểm tra dữ liệu có thể chạy lại, từ điển dữ liệu,
định nghĩa nghiệp vụ và xác định điều kiện dùng cho hai mô hình. Chưa viết schema
mới hay huấn luyện ở giai đoạn 0.
