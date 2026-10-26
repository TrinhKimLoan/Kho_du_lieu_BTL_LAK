# Bản đồ thư mục LAK

| Vị trí | Nội dung |
|---|---|
| `data/excel/` | Excel nguồn phục vụ học tập; không sửa âm thầm |
| `data/models/` | Hai mô hình versioned; ngoài Git, được bổ sung tường minh vào candidate bằng checksum |
| `src/source/` | Chuẩn hóa, nạp và thao tác demo nguồn MySQL |
| `src/cdc/` | Collector, raw event ledger, applier, replay và recovery |
| `src/quality/` | Quy tắc dữ liệu, SCD2, fixture và retry |
| `src/news/` | Tin tức MediaCloud metadata, lưu trữ và đánh giá liên quan |
| `src/marts/` | Refresh mart, cube/OLAP, truy vấn và đối soát |
| `src/mining/`, `src/delivery/` | RFM/KMeans và Random Forest dự đoán thời gian giao |
| `src/inference/` | Hàng đợi bền vững, inference và lịch sử dự đoán |
| `src/dashboard/`, `streamlit_app.py` | Repository, 8 trang Streamlit và entrypoint gốc |
| `sql/`, `dags/` | Schema/migration và lịch Airflow |
| `infra/` | Compose/Dockerfile của LAK; `locks/` lưu inventory phiên bản |
| `scripts/phase12/` | Harness đo và runner PowerShell |
| `scripts/phase13/` | Kiểm tra lock, vận hành và đóng gói candidate |
| `docs/phase12/` | Báo cáo đối soát/recovery/hiệu năng/hạn chế và 53 tệp bằng chứng đã chấp nhận |
| `docs/phase13/` | Inventory, hướng dẫn release/vận hành và chuẩn bị bảo vệ |
| `tests/` | Unit/integration fixture tests; không thay kết quả runtime máy người dùng |
| `.runtime/` | Credential và backup thao tác tại máy; không đưa vào candidate |
| `evidence/` | Bằng chứng chạy từng pha, không tự gom tất cả vào bản nộp |

Các tệp Compose/Dockerfile và backend gốc ngoài `infra/` được bảo tồn để truy vết lịch sử. Runtime LAK dùng các tệp `infra/compose.*.yaml` được wrapper liệt kê tường minh.
