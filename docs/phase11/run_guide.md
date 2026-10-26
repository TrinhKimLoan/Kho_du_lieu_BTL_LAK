# Phase 11 — Website LAK Analytics

## Trạng thái và chạy trên Windows

Phase 10 đã chạy đạt trên máy người dùng: evidence/phase10/run-20261026T061947Z-d698d17d, gồm CDC → ML, khôi phục worker, replay và cleanup nguồn demo. Giữ nguyên hệ thống và model hiện có.

Sau khi áp dụng Phase 11 patch trong G:\LAK-Analytics, chạy:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_phase11.ps1
```

Script dựng image Streamlit/Plotly, chạy 14 unit test/UI test với fixture tách riêng, truy vấn read-only PostgreSQL thực tế, thực thi tám trang bằng Streamlit AppTest với kết nối thực, đối soát tổng quan/OLAP và số dòng test của RF. Sau đó khởi động dashboard, kiểm tra HTTP health và giữ website chạy ở **http://localhost:8501**.

Không tạo Site trên cloud, không dùng schema legacy của backend/main.py, không gọi vòng qua FastAPI cũ. Đây là website Streamlit theo kế hoạch đã chốt, đọc trực tiếp truy vấn dùng chung và mart hiện tại. Không có model mới hoặc huấn luyện lại trong Phase 11. Không reset dữ liệu, volume, mô hình hoặc bằng chứng cũ.

Các dịch vụ CDC, Airflow, inference-worker của Phase 4–10 cần tiếp tục chạy. Script không xóa các container bị cảnh báo orphan do chúng thuộc Compose file khác. Docker build lần đầu có thể tải thêm thư viện giao diện.

## Tám trang đã triển khai

| Trang | Nguồn và hành vi |
| --- | --- |
| Tổng quan kinh doanh | KPI tiền hàng, đơn, khách duy nhất, giá trị đơn; xu hướng tháng, nhóm hàng, top sản phẩm/phiên bản và bảng chi tiết. Dùng mart; ngày theo packed_at. |
| Bán hàng & OLAP | Roll-up năm; drill-down năm/quý/tháng; slice năm; dice theo bộ lọc ngày/nhóm/địa bàn; pivot tiền hàng năm × nhóm và heatmap. Số khách/trung bình tính lại qua truy vấn, không cộng các ô. |
| Khách hàng & phân khúc | Tách RFM/nhóm hiện tại từ Phase 10 khỏi báo cáo snapshot K-Means cố định từ Phase 8. Có quy mô, R/F/M, scatter, hồ sơ nhóm, lựa chọn K/độ ổn định và gợi ý chăm sóc chưa kiểm chứng tác động. |
| Giao hàng & dự đoán | Giờ giao thực theo dispatched_at; dự đoán ban đầu và outcome hiện tại từ Phase 10; báo cáo RF test cố định, baseline toàn train/theo loại giao, sai số nhóm và permutation importance. Không gọi accuracy hoặc SLA khi chưa đủ căn cứ. |
| Tin tức & thị trường | Bài/nguồn/nhóm liên quan, lý do rule, nguồn nạp seed/api, phân trang và CSV; độ phủ tháng/nhóm; đối chiếu một nhóm hàng theo cùng cửa sổ ngày, aggregate sales và news độc lập. Thiếu COMPLETE thì comparable_article_count là NULL, không nối giả thành 0. |
| Tra cứu chi tiết | Mã khách/mã đơn tham số hóa; tối đa 100 đơn, lịch sử nhóm và dự đoán. Mã đơn demo được gắn cờ. Không xuất tên, điện thoại, địa chỉ đầy đủ. |
| Vận hành dữ liệu | Trạng thái connector/task từ REST trạng thái, worker heartbeat, raw pending, queue ML, findings, lỗi theo mã, audit runs, registry và lịch sử ngày tham chiếu. Không lấy cấu hình connector chứa password hoặc payload CDC để hiển thị. |
| Demo CDC | Tạo suffix WEB11 riêng cho phiên, chỉ có ba nút insert/update/delete gọi hàm demo nguồn đã dùng ở Phase 3–10. Theo dõi fact/queue/RFM/input/model/outcome. Các thay đổi chạy qua MySQL và CDC, không sửa thẳng bảng kho. |

## Phạm vi, đơn vị và độ mới

- Thanh bên có khoảng ngày bao gồm cả ngày cuối, chọn nhiều nhóm hàng và quận/huyện. Kho truy vấn dùng end exclusive của ngày tiếp theo. Những trang không dùng bộ lọc kinh doanh ghi rõ trên trang.
- Tổng quan/OLAP theo ngày đóng gói; giao thực theo ngày giao đi; tin theo ngày xuất bản. packed_at không được đổi tên thành ngày đặt hàng. Đơn thiếu packed_at vẫn giữ trong fact và được cảnh báo riêng vì không thể gán vào một khoảng thời gian đóng gói.
- Tiền hàng, VAT, phí, tổng thanh toán tách riêng. Giá trị trung bình mỗi đơn dùng tiền hàng/số đơn; không suy ra lợi nhuận hoặc đã thu tiền thực tế. Thẻ tiền lớn dùng triệu/tỷ và vẫn ghi số VND đầy đủ ở caption/bảng/CSV. Tiền trong kho không chuyển float để sửa dữ liệu.
- Header ghi thời điểm refresh mart và thời điểm đọc kho hiện tại. Mart có lịch Phase 7 là 15 phút; UI cảnh báo nếu snapshot đã quá 30 phút. Không tự refresh mart trên mỗi lần mở trang để che độ trễ.
- Từng lần đọc trang dùng transaction PostgreSQL REPEATABLE READ READ ONLY và statement timeout 15 giây; dữ liệu mart và live có vai trò/thời điểm riêng. Không dùng cache để che thay đổi CDC trên trang demo; bấm Làm mới dữ liệu để xem trạng thái mới.
- RFM dùng inference_config.reference_date. Báo cáo K-Means/RF dùng model đã ghim và snapshot đánh giá cố định; các bộ lọc doanh số không tái tạo tập test hoặc chọn lại model.
- Một đơn chỉ có dự đoán ban đầu; các outcome mới nhất được đọc riêng. Đơn lịch sử đã nhận không có dự đoán trực tuyến thì UI hiển thị trạng thái trống, không lấy dự đoán offline làm giả trực tuyến.
- RF tốt hơn baseline mạnh khoảng 6,1 phút trong kết quả đã kiểm chứng Phase 9. UI tính lại chênh lệch từ report tương ứng model và không khẳng định hiệu quả vận tải thật.
- Heartbeat 30 giây là kiểm tra worker có cập nhật gần đây. Capture → processed là khoảng thời gian giữa hai mốc đã lưu trong raw CDC; không gọi đó là độ trễ đầu cuối từ MySQL. Đo hiệu năng đầy đủ dành cho Phase 12.
- Audit pipeline là bằng chứng pipeline đã ghi nhận; không khẳng định Airflow scheduler hiện đang chạy chỉ từ bản ghi cũ. Trang vận hành không giả trạng thái container/scheduler không quan sát được.
- Tin IRRELEVANT/UNCLASSIFIED vẫn xem được trong danh sách khi không lọc nhóm. So sánh thị trường dùng DIRECT/INDIRECT trong mart membership; không nhân bản tiền qua bridge. Không suy ra quan hệ nhân quả.
- Bảng có nút CSV và thông báo giới hạn hiển thị 300 dòng; CSV chứa toàn bộ kết quả truy vấn đó. Tin mỗi trang 30 bài, detail tối đa 100 đơn, live delivery tối đa 300 đơn mới nhất, audit tối đa 30 run; UI ghi rõ giới hạn. Header CSV dùng tên trường gốc để đối soát. Chuỗi có thể bị phần mềm bảng tính coi là công thức được thêm dấu nháy bảo vệ.
- Mốc giao dịch giữ timestamp không timezone theo dữ liệu nguồn; mốc vận hành ghi UTC. Không tự đổi mốc nghiệp vụ sang UTC khi nguồn chưa xác minh timezone.

## Demo trên giao diện

1. Mở Demo CDC. Ghi nhận mã DEMO_WEB11_... đang hiển thị (được tạo tự động, không cho nhập mã lịch sử để sửa).
2. Bấm Thêm đơn demo. Bấm Làm mới dữ liệu sau vài giây: nguồn có đơn, fact quantity=2, M=200.000 và dự đoán ban đầu có model/input.
3. Bấm Sửa và ghi nhận đã nhận. Làm mới: fact quantity=3, M=300.000; outcome thực tế 27 giờ. Đầu vào dự đoán ban đầu quantity=2 được giữ nguyên.
4. Bấm Xóa đơn demo sau khi xem xong. Làm mới: fact is_deleted=true, RFM NO_HISTORY, outcome DELETED. Lịch sử minh chứng được giữ.

Chỉ các suffix WEB11_[10 ký tự hex] do ứng dụng sinh mới được chấp nhận phía server. Hàm nguồn còn kiểm tra is_demo và namespace trước khi ghi. Không có form SQL, nút sửa hàng lịch sử, tự đổi ngày tham chiếu hoặc train từ website.

Nếu nguồn hoặc CDC chưa đáp ứng, UI báo chờ/lỗi và không giả thành công. Việc ghi vào MySQL thành công không đồng nghĩa CDC/ML đã xong; theo dõi các bảng tương ứng sau khi làm mới. Cần xóa demo trước khi đóng phiên nếu đã thêm; phiên mới có suffix mới để tránh thao tác nhầm fixture khác.

## Kiểm tra trực quan trước khi chốt

AppTest là thực thi widget/SQL trong runtime Streamlit, không phải ảnh chụp trình duyệt. Môi trường chuẩn bị chưa chạy được preview Streamlit trong hạ tầng browser nên chưa kiểm chứng trực quan tại đó. Sau khi script đạt, mở http://localhost:8501 để kiểm tra bố cục, chữ, biểu đồ và thao tác trên trình duyệt Windows. Gửi ảnh trang Tổng quan để rà hiển thị, rồi xem các tab ML/OLAP và demo.

Bằng chứng tự động: evidence/phase11/run-.../dashboard-checks.json, phase11.log, check.json. browser_visual_verified luôn false trong các script này để không nhận nhầm kiểm thử chương trình thành kiểm tra hình ảnh. Chỉ chốt Phase 11 sau khi dữ liệu/runtime đạt và giao diện đã được người dùng xem.

## Khởi động lại lần sau

Bổ sung `-f infra/compose.dashboard.yaml --profile dashboard` và `-f infra/compose.inference.yaml --profile ml-inference` vào danh sách Compose đang dùng (lak/news/mart/ml/delivery tùy công cụ cần chạy), dùng project lak-analytics và env .runtime/lak.env như cũ. Chỉ `up -d`; không cần down hoặc xóa volume. Dashboard chỉ bind localhost:8501, chưa triển khai công khai ra Internet.
