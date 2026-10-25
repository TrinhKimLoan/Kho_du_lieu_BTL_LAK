# Pha 7 — Data mart và OLAP

## Mục đích và đầu ra

Chuẩn bị số liệu nhất quán cho website và các pha ML tiếp theo; chưa huấn luyện mô hình. SQL tạo mart/cube, hàm truy vấn được tái dùng, 5 ví dụ OLAP và CSV kết quả đi kèm JSON bằng chứng. Định nghĩa KPI/grain: `docs/phase7/kpi_definitions.md`.

Đầu vào đã được người dùng xác nhận: pha 6 stored/news API PASS, evidence API `G:\LAK-Analytics\evidence\phase6\run-20261025T185216Z-d98ec5d2`; DagRun Airflow success, evidence `G:\LAK-Analytics\evidence\phase6\run-airflow-20261025T190519Z`. Lịch news vẫn paused tại checkpoint đó. Không ghi đoán commit máy người dùng.

## Refresh và độ trễ

Chọn full refresh trong một giao dịch REPEATABLE READ cho quy mô LAK hiện tại. Các bảng được DELETE/INSERT trong cùng transaction, cùng snapshot đọc fact; cập nhật mart.snapshot_state và pipeline status trong cùng commit. Nếu lỗi, rollback, giữ snapshot thành công trước. Không TRUNCATE/CASCADE, không reset volume hoặc sửa nguồn. Advisory lock ngăn hai writer mart; chờ tối đa 60 giây rồi báo lỗi, không ghi chồng.

Bảng snapshot_state có refresh_id, source_observed_at, refreshed_at, số fact và SHA nguồn. Tuổi snapshot phải hiển thị trên website sau này. Độ trễ mart gồm: source→DW CDC/polling + chờ lần refresh + thời gian refresh. Không tuyên bố mart đồng bộ tức thời. Khi lịch hoạt động tốt, khoảng chờ lịch danh định tối đa 15 phút; lỗi/tạm dừng có thể làm trễ hơn, phải xem timestamp thật.

DAG mới `lak_mart_refresh_phase7` chạy `*/15 * * * *`, không catchup, một run đồng thời, retry một lần. Dùng Airflow profile đã kiểm chứng pha 6, chỉ bổ sung DAG và mã mart. Không tự bật DAG news. Runner kiểm thử mart, dựng lại Airflow, thực thi DagRun mart qua executor, xác nhận state success, đối soát sau đó mới unpause lịch mart. Kết quả đó chứng minh một lần thực thi, chưa chứng minh hoạt động định kỳ lâu dài; phần quan sát vận hành/hiệu năng tiếp tục ở pha 12.

## Năm thao tác OLAP

- Roll-up: từ cell lên năm, tính lại DISTINCT khách và trung bình theo tổng/mẫu số.
- Drill-down: năm 2024 → quý → tháng, không gộp tháng trùng tên của các năm khác.
- Slice: cắt năm 2024, xem theo nhóm hàng.
- Dice: năm 2024, nhóm CPU/RAM, đồng thời phân theo tháng và quận/huyện.
- Pivot: nhóm hàng thành dòng, năm thành cột tiền hàng; mỗi cell đã được tổng hợp đúng trước khi xoay. Không cộng các DISTINCT/trung bình để tạo tổng biên.

`src.marts.queries.sales/news` hỗ trợ dimensions theo allowlist và filter tham số hóa. start bao gồm, end loại trừ; năm/nhóm/quận/thành phố đúng kiểu. Chỉ tiêu thiếu dữ liệu giữ NULL, không tự thay trung bình trống bằng 0. Tin tức có helper DISTINCT bài/nguồn qua membership; news_daily phục vụ số bài mọi mức liên quan.

`mart.v_sales_cube` dùng GROUP BY CUBE cho năm/nhóm/thành phố. grouping_mask=7 là grand total; mask phân biệt subtotal với NULL nghiệp vụ. Chưa đo khẳng định tốc độ nhanh hơn; chỉ chọn cấu trúc và kiểm chứng tính đúng. Dữ liệu hiện một thành phố, dùng quận/huyện khi cần chiều có biến thiên.

## Chạy và điều kiện hoàn thành

```powershell
Set-Location G:\LAK-Analytics
python -m unittest discover -s tests -p 'test_phase7*.py' -v
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_phase7.ps1
```

Runner dùng compose.lak.yaml + compose.mart.yaml cho mart-tools, compose.news.yaml cho Airflow. Không gọi compose cũ ở gốc. Token/mật khẩu và volume được giữ. Airflow rebuild nhận thêm `dags/phase7` (image vẫn chứa DAG news). Mọi lần chạy có thư mục evidence/phase7/run-* riêng.

Các kiểm tra thực tế:

1. Refresh và so sánh từng dòng/từng cột của 8 quan hệ mart với tổng hợp trực tiếp từ fact.
2. So sánh tổng, DISTINCT khách, trung bình và các tổ hợp năm/nhóm/tháng/địa bàn/sản phẩm/khách/vận chuyển.
3. So sánh DISTINCT bài/nguồn và trọng số theo thời gian/nhóm/nguồn/mức liên quan.
4. Cube grand total và bảng ghép monthly news/sales không nhân tiền hàng/số đơn; coverage thiếu giữ NULL.
5. Fixture PostgreSQL trong transaction rollback: thêm một fact phân tích tạm, sửa tiền/ngày/sản phẩm/nhóm/địa bàn và đưa nhãn giao về NULL, refresh từng lần, soft delete rồi refresh. Kiểm tra toàn bộ mart sau mỗi bước, cuối cùng rollback cả fixture và các lần refresh tạm. Dữ liệu đó không bao giờ được commit cho người khác đọc. Identity sequence có thể tăng sau rollback.
6. DagRun mart qua executor phải success, sau đó đối soát nguồn/fact và mart tiếp tục khớp; bật lịch mart 15 phút.

Fixture ở bước 5 là kiểm thử PostgreSQL fact→mart, không giả là thay đổi MySQL/CDC mới. Pha 4 đã kiểm thử MySQL→fact; kiểm thử xuyên suốt và thời gian phục hồi ở pha 12. SQL audit migration lưu marker/fingerprint mới, không sửa DDL nguồn/kho pha 2 hoặc mapping CDC.

Marker: `PHASE 7 MART AND OLAP CHECKS PASSED`. File mart-checks.json, after-airflow.json, check.json và CSV OLAP nằm cạnh phase7.log; log chứa trạng thái DagRun và docker stats một lần. Không coi một snapshot docker stats là benchmark.

## Refresh thủ công hoặc dừng lịch

Sau cài đặt có thể chạy lại runner để kiểm tra toàn bộ. Nếu một refresh khác giữ lock, công cụ chờ tối đa 60 giây. Dừng riêng lịch mart:

```powershell
docker compose --project-name lak-analytics --env-file .runtime/lak.env -f infra/compose.lak.yaml -f infra/compose.news.yaml exec -T news-airflow airflow dags pause lak_mart_refresh_phase7
```

Bật lại bằng `airflow dags unpause lak_mart_refresh_phase7` trong cùng compose. Không cần unpause DAG news khi chỉ muốn refresh mart. Đọc nhiều bảng để trình bày cùng snapshot nên dùng một transaction REPEATABLE READ; giao diện sau này sẽ dùng refresh_id để giải thích độ mới.

## Giới hạn xác nhận

Unit test và kiểm tra cú pháp Python/YAML thực hiện ở môi trường chuẩn bị. Không có PostgreSQL/Docker/PowerShell để thực thi ở đây; toàn bộ SQL refresh, fixture, Airflow vẫn chờ máy người dùng. Chưa có số đo độ trễ hoặc tốc độ truy vấn. KMeans/Random Forest và website sẽ triển khai ở các pha đúng kế hoạch sau khi pha này đạt.
