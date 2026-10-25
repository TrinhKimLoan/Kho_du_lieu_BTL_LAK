# Pha 6 — Luồng tin tức có truy vết và giới hạn rõ ràng

## Mục đích

Nạp metadata bài báo MediaCloud vào kho mới, giữ raw và lineage, phân biệt NEW/UPDATED/UNCHANGED, phân loại theo quy tắc và báo độ phủ trước khi ghép chỉ tiêu bán hàng. Đây là polling API, **không phải CDC binlog**. Hai thuật toán mining bắt buộc vẫn là KMeans và Random Forest ở các pha sau.

Pha 5 đã được người dùng xác nhận `PHASE 5 QUALITY AND SCD2 CHECKS PASSED`, evidence `G:\LAK-Analytics\evidence\phase5\run-20261025T182247Z-67e968f6`.

## Kiến trúc và khả năng tương thích

Giữ nguyên DDL nền pha 2, source Excel/MySQL, connector và volume. Tái dùng `raw.news_snapshots` và `staging.news_articles` đã được thiết kế ở pha 2. Bổ sung `raw.news_pages`, `raw.news_observations` (mọi dòng, gồm dòng lỗi và trùng), `audit.news_changes`, `audit.news_fetch_windows` và liên kết `last_snapshot_id` trên staging. Baseline raw.news_snapshots lưu quan sát đầu tiên của mỗi run/article; raw.news_observations lưu chi tiết mọi trang/dòng. Hash DDL riêng được bảo vệ trong audit.news_pipeline_identity.

Fact một dòng/bài; bridge một dòng/bài/nhóm. Cập nhật bài thay đổi sẽ thay bridge của riêng bài đó, không xóa bridge toàn bảng. Raw được commit trước khi chuẩn hóa/project; nếu project lỗi, giữ raw page và processing_error, không giả nhận thành công.

Source cũ app.core/dags vẫn được giữ để tham khảo; không chạy bootstrap/ETL hoặc DAG cũ vào kho mới. Compose mới là `infra/compose.news.yaml`, được ghép với `infra/compose.lak.yaml`, không dùng docker-compose.yml ở gốc vì file đó trỏ kiến trúc cũ.

## Định danh và thay đổi

Khóa bài = SHA256 URL chuẩn hóa: host viết thường, bỏ www, port mặc định, fragment, utm_* và một số tracking id; sắp thứ tự query nhưng giữ id/nội dung query. Không tự coi http=https, URL amp=URL desktop hoặc dấu / cuối là tương đương. Đây là quy tắc định danh dựa URL, chưa phải nhận diện bài trùng ngữ nghĩa.

Hash nội dung gồm tiêu đề, URL, miền nguồn, ngày xuất bản và kết quả/phiên bản quy tắc. External ID và indexed_at không làm phát sinh UPDATED. Ngày xuất bản, ngày chỉ mục của MediaCloud và first/last_seen_at của hệ thống là ba khái niệm riêng. First_seen không được lấy từ ngày xuất bản. Không coi bài vắng mặt trong trang API là đã xóa.

Dữ liệu CSV seed không ghi đè bài đã quan sát qua API: lưu raw và SKIPPED_SEED. Khi API có cùng hash với seed, vẫn cập nhật metadata, lineage và origin sang api, giữ first_seen. Demo dùng miền .invalid, chạy trong giao dịch rollback và không lọt view phân tích.

## Thu thập API

Adapter HTTP dùng thư viện chuẩn Python, theo giao thức trong client chính thức MediaCloud: Authorization Token, endpoint search/story-list, tham số q/start/end/cs/platform/page_size và pagination_token. Nguồn đối chiếu ngày 26/10/2026:

- https://github.com/mediacloud/api-client/blob/main/mediacloud/api.py
- https://www.mediacloud.org/documentation/search-api-guide

Giữ 5 nhóm truy vấn gốc GPU/CPU/SSD/RAM/NETWORK và collection mặc định 34412246. Nhóm được truy vấn và nhóm được phân loại là hai khái niệm khác nhau. Bài có thể được nhiều truy vấn tìm thấy nhưng vẫn có một fact. Sáu nhóm hàng còn lại không tự được coi là đã quét API đầy đủ.

Mỗi request cách nhau ít nhất 32 giây, tối đa 3 lần thử cho lỗi mạng/429/5xx; tôn trọng Retry-After theo giới hạn chờ của adapter. Lỗi 401/403 không giả thành danh sách rỗng. Không lưu header xác thực hoặc in response body lỗi. Giới hạn mặc định 100 bài/trang, 2 trang/nhóm/tháng. Còn token khi chạm cap → PARTIAL; token lặp hoặc lỗi → FAILED. Chỉ COMPLETE khi hết token, không dòng lỗi và đã thu thập hết tháng yêu cầu. COMPLETE chỉ nói về các truy vấn/collection được chọn, không phải toàn bộ internet.

Raw page lưu response JSON và tham số không bí mật. Phản hồi HTTP/JSON không đọc được được ghi thành run FAILED, không lưu như một raw JSON hợp lệ. Query_signature gắn với query, collection, platform và tháng, nên thay query không kế thừa kết luận COMPLETE cũ.

## Độ phủ và tổng hợp

360 bài CSV: 19 DIRECT, 6 INDIRECT, 335 IRRELEVANT theo quy tắc cũ, xuất bản trong 2024. Đây là số liệu **quan sát trong file**, không chứng minh đầy đủ thị trường. Seed luôn PARTIAL. Matrix API gồm cả NOT_FETCHED theo các tháng bán hàng, không biến thiếu dữ liệu thành số 0 tin tức thực tế.

Một bài nhiều nhóm có các bridge riêng. Bảng theo nhóm hiển thị count distinct bài trong nhóm và article_weight=1/số nhóm. Tổng bài toàn bộ dùng COUNT DISTINCT news_key; không cộng máy móc các count theo nhóm. View dw.v_news_category_analysis loại IRRELEVANT, demo, soft-deleted. Không cộng trọng số thành doanh số.

Phải tổng hợp sales và news riêng về cùng grain tháng/nhóm trước khi join. Pha 7 sẽ xây mart. Pha 6 không join fact sales trực tiếp vào bridge tin tức và không khẳng định quan hệ nhân quả.

## Rà soát mẫu

`config/news_review_sample.json` lưu 35 nhận xét từ đọc tiêu đề: toàn bộ 25 bài quy tắc đánh DIRECT/INDIRECT và 10 bài IRRELEVANT chọn cố định. Trợ lý AI đã đọc và ghi nhãn đối chiếu dựa metadata; `human_verified=false`. Không giả mạo người duyệt, không coi đây là nhãn chuẩn hay accuracy ML. Có 30/35 đồng thuận mức liên quan và 33/35 đồng thuận tập nhóm; đây là chẩn đoán trên mẫu thiên lệch có chủ đích, không phải ước lượng chất lượng toàn bộ dữ liệu.

Ví dụ cần xem xét: microSD so với SSD; nâng cấu hình RAM của MacBook; DRAM đi kèm GPU; CPU có lỗ hổng; bài tối ưu SSD; chip AI thiếu từ khóa CPU. Giữ quy tắc v1 để kết quả tái lập, ghi rõ hạn chế thay vì âm thầm sửa nhãn cho khớp. Sinh viên có thể kiểm tra từng dòng qua CSV review hoặc giao diện sau này; chưa có xác nhận nhãn độc lập của con người.

## Lệnh chạy và bằng chứng

```powershell
Set-Location G:\LAK-Analytics
python -m unittest discover -s tests -p 'test_phase6*.py' -v
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_phase6.ps1
```

Runner tạo .runtime/news.env nếu chưa có, không đổi .runtime/lak.env. Nạp seed hai lần, đối soát raw/staging/fact/bridge, kiểm tra weights, fixture NEW/UPDATED/UNCHANGED, không-xóa-do-vắng-mặt, raw dòng lỗi, demo rollback và sales fingerprint trước/sau. Mỗi lần chạy có thư mục evidence/phase6/run-* riêng, chứa JSON chi tiết, coverage CSV và review CSV. CLI chỉ in tóm tắt để log dễ đọc.

Marker **PHASE 6 STORED NEWS CHECKS PASSED** chỉ xác nhận phần dữ liệu lưu sẵn và kiểm thử pipeline; API thật chưa được xác nhận.

Để kiểm tra API thật, dùng API key của em; không gửi key vào chat:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_phase6.ps1 -LiveApi -Year 2024 -Month 12
```

Nếu thiếu key, script hỏi bằng ô nhập ẩn và giữ trong .runtime/news.env (Git ignore). Sau seed check, gọi API thật rồi đối soát lại. Marker **PHASE 6 NEWS PIPELINE CHECKS PASSED** yêu cầu API không FAILED và kiểm tra sau API đạt. Các nhóm vẫn có thể PARTIAL vì page cap; kết quả coverage phải được báo đúng. Chưa chốt kiểm chứng toàn bộ pha 6 trước khi đọc kết quả API thật.

## Điều phối định kỳ bằng Airflow

Giữ Airflow theo kế hoạch, nhưng tách DAG nâng cấp `dags/phase6/lak_news_incremental.py` khỏi DAG cũ vì DAG cũ gọi ETL/schema cũ. Profile news-scheduler dùng Airflow 2.10.5, SequentialExecutor, metadata SQLite và volume riêng; chưa bật mặc định trên máy 16 GB. Không khởi động DAG cũ vào kho mới. Không tự tiêu quota API khi mới cài patch.

Sau khi API thật đạt và có đủ RAM, có thể dựng profile riêng, xem DAG import rồi mới bật lịch:

```powershell
Set-Location G:\LAK-Analytics
docker compose --project-name lak-analytics --env-file .runtime/lak.env -f infra/compose.lak.yaml -f infra/compose.news.yaml --profile news-scheduler up -d --build news-airflow

docker compose --project-name lak-analytics --env-file .runtime/lak.env -f infra/compose.lak.yaml -f infra/compose.news.yaml exec -T news-airflow airflow dags list-import-errors

docker compose --project-name lak-analytics --env-file .runtime/lak.env -f infra/compose.lak.yaml -f infra/compose.news.yaml exec -T news-airflow airflow dags unpause lak_news_incremental_phase6
```

Scheduler cần thời gian khởi tạo metadata và đọc DAG. Chưa chạy các lệnh profile này trong lượt kiểm thử seed. Ghi tài nguyên thực tế trước khi quyết định giữ scheduler chạy thường trực:

```powershell
docker stats --no-stream
```

DAG chạy hằng ngày, không catchup, chỉ một run đồng thời, thu thập tháng hiện tại có cap. Tháng chưa kết thúc vẫn PARTIAL. Muốn bổ sung tháng cũ dùng lệnh `-LiveApi -Year ... -Month ...`; không tuyên bố đã tự backfill toàn bộ lịch sử. Profile này phục vụ demo một máy, không phải cấu hình Airflow production.

Tạm dừng riêng scheduler:

```powershell
docker compose --project-name lak-analytics --env-file .runtime/lak.env -f infra/compose.lak.yaml -f infra/compose.news.yaml stop news-airflow
```

Advisory lock ngăn hai news writer cùng hoạt động. Dừng scheduler trước khi chạy kiểm tra thủ công nếu nó đang thu thập. DAG còn chờ kiểm chứng import và chạy thực tế trên máy người dùng; không coi có file DAG là đã tích hợp lịch thành công.

## Giới hạn xác nhận

Unit test dùng phản hồi HTTP giả lập để kiểm tra header, tham số, pagination, lỗi và retry. Không có API key, Docker/PostgreSQL/PowerShell trong môi trường chuẩn bị; không tuyên bố kiểm thử API hay DB thực tế đã đạt. Quyền sử dụng/giấy phép seed gốc chưa được cung cấp; không tự khẳng định được phép tái phân phối toàn văn. Pipeline chỉ xử lý metadata hiện có, không tải toàn văn bài báo.
