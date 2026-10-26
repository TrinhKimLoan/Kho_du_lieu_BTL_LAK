# Báo cáo tổng kết LAK Analytics

## 1. Mục tiêu và dữ liệu

Hệ thống tích hợp dữ liệu bán linh kiện điện tử và tin tức để phân tích doanh số, khách hàng, giao hàng và thông tin liên quan. Dữ liệu LAK phục vụ học tập, gồm 10.000 đơn, 3.282 khách hàng, 15 sản phẩm, với 43.297 dòng provenance từ Excel. Snapshot tin tức dùng trong kiểm thử có 2.145 fact tin tức. Không gán hiệu quả kinh doanh thực tế cho dữ liệu mô phỏng.

## 2. Kiến trúc và công nghệ

MySQL nguồn dùng binlog ROW/FULL. Debezium 3.2 phát sự kiện vào Kafka 3.9.1; collector lưu raw theo tọa độ bất biến và applier chiếu vào staging/DW trên PostgreSQL 16.15. Airflow lập lịch pipeline tin tức và refresh mart. Hai mô hình là RFM/KMeans và Random Forest dự đoán số giờ giao. Streamlit 1.45.1 và Plotly 6.0.1 hiển thị 8 trang.

Source → CDC → DW → mart → ML → web được kiểm thử qua nhiều kịch bản bổ sung, không khẳng định một browser transaction đơn lẻ đã tự kiểm chứng mọi tầng. Image và môi trường Python đã khóa bằng inventory thực; byte 13 image đi kèm release. Khi dựng lại dùng image đã xác minh, không tuyên bố một source build mới từ base image chưa khóa sẽ tái tạo bit-for-bit.

## 3. Kho dữ liệu

Hai fact bán hàng và tin tức có grain riêng. Dimension bao gồm các vai trò ngày, khách hàng, phiên bản sản phẩm, phân loại, địa bàn, phương thức giao và nguồn tin. Sản phẩm dùng SCD2 khi đổi tên/nhóm/category; đơn cũ giữ khóa phiên bản cũ, đơn mới dùng hiện hành. Hồ sơ địa bàn khách hàng dùng Type 1. Fact bán hàng giữ bốn vai trò ngày và kiểm tra công thức tiền.

Không join trực tiếp hai fact làm nhân doanh số; các phép tổng hợp/bridge và grand total được đối soát. Các mart phục vụ tổng hợp ngày/tháng, sản phẩm, khách hàng, giao nhận và tin tức, với snapshot state rõ thời điểm refresh.

Tổng tiền được kiểm chứng: tiền hàng 618.293.800.000 VND; VAT 61.829.380.000 VND; phí vận chuyển 1.138.180.904 VND; thanh toán 681.261.360.904 VND. Số liệu nguồn và DW/mart khớp.

## 4. CDC, chất lượng và phục hồi

Tọa độ Kafka và source epoch giúp định danh raw event; ledger transaction và thứ tự binlog hỗ trợ chiếu idempotent. Xóa nguồn được phản ánh qua trạng thái xóa trong kho; demo được cô lập khỏi phân tích lịch sử.

Kiểm thử tắt collector, applier và inference worker, ghi thay đổi khi worker dừng, bật lại và xử lý bù đều đạt. Replay Kafka/projection không thêm tọa độ trùng, không đổi lịch sử fact hoặc phiên bản sản phẩm. Retry được kiểm tra ở vòng đời CSDL; không phóng đại thành kiểm thử mọi poison-event/crash/network partition.

Chất lượng ghi nhận 0 ERROR và 998 WARNING: 880 DISPATCH_BEFORE_PACK, 118 EXPECTED_BEFORE_DISPATCH. Đây là số phát hiện theo rule, không đồng nghĩa 998 đơn riêng biệt. Giữ nguyên nguồn, không âm thầm sửa timestamp. Chưa có SLA được xác minh nên không công bố tỷ lệ vi phạm SLA.

## 5. ML và đánh giá

RFM/KMeans xử lý 3.282 khách hàng; train/validation/test lần lượt 1.969/656/657. K=2 được chọn bằng validation, tiền xử lý chỉ fit train; test silhouette khoảng 0,4043. Hai phân khúc có 1.993 và 1.289 khách hàng; nhãn được diễn giải từ đặc trưng, không khẳng định dự đoán hành vi tương lai.

Random Forest dùng temporal holdout và label availability, tiền xử lý/baseline chỉ fit train. Test 1.599 mẫu: MAE 18,7329166932 giờ, baseline theo phương thức vận chuyển 18,8346183379 giờ; cải thiện khoảng 0,1017 giờ (~6,1 phút), rất nhỏ. Không dùng test chọn tham số hoặc refit holdout. Mô hình, checksum và dự đoán được tái lập từ tệp đã lưu.

Inference dùng queue bền vững và mô hình đã pin; cập nhật kết quả khi thêm/sửa/xóa. Dự đoán giao ban đầu bất biến, outcome/lịch sử được ghi riêng. Tick ngày tham chiếu không đòi giao dịch mới và phép thử chỉ đổi ngày demo. Không huấn luyện lại trong các lượt đo và dựng lại.

## 6. Website

8 trang: tổng quan, OLAP, khách hàng, giao hàng, tin tức, tra cứu, vận hành, demo. Truy vấn read-only và bộ lọc được kiểm tra với kho thật; tổng quan khớp OLAP, fact khớp mart, tra cứu đơn có dữ liệu. Cold import từng lỗi do app.py che khuất package app; đã đổi entrypoint gốc và xác minh lại.

AppTest chạy đủ 8 trang trong bản gốc và bản restore; đó là thực thi UI, không phải kiểm tra pixel trên browser. Người dùng đã mở và chấp nhận giao diện bản gốc. Website gốc ở localhost:8501, bản sao ở localhost:18501.

## 7. Hiệu năng

Máy i5-12450H, 8 core/12 logical, RAM 15,7 GiB; Docker Linux 12 CPU, khoảng 7,607 GiB. Cửa sổ đo mới có 20 mẫu mỗi thao tác, tổng 60, polling 0,1 giây và cùng đồng hồ monotonic.

| Thao tác | DW mean (s) | ML mean (s) | ML p95 (s) |
|---|---:|---:|---:|
| Insert | 1,0713 | 1,6165 | 2,0538 |
| Update | 1,0442 | 1,5045 | 2,0580 |
| Delete | 1,0867 | 1,6571 | 2,0657 |

Sáu query fact/mart cho cùng đầu ra; mỗi nguồn/query có 2 warmup, 10 lần đo, thứ tự cặp ngẫu nhiên, cùng snapshot và tính cả fetchall. Mart chênh lệch nhỏ, query sản phẩm chậm hơn fact; chưa chứng minh tăng tốc rõ rệt.

30 mẫu Docker stats: RAM cộng container trung bình 2,803 GiB, max quan sát 2,883 GiB. CPU cộng trung bình 95,89%, max 447,19% theo 100%=một CPU, tương đương 7,99%/37,27% trên 12 CPU. Database PostgreSQL khoảng 169,054 MiB; sáu schema cộng khoảng 159,063 MiB gồm bảng/index/TOAST. Docker system df là toàn engine, không riêng LAK. Không coi mẫu cao nhất là peak tuyệt đối hoặc phép thử tuần tự là benchmark tải đồng thời.

## 8. Release và dựng lại

Candidate source/model/evidence có checksum; 13 image được xuất thành tar 2.172.470.272 byte. MySQL dump 25.806.538 byte, PostgreSQL custom dump 11.770.732 byte, mỗi tệp có SHA-256. Dừng writer ứng dụng trong lúc dump rồi bật lại, không reset volume.

Restore thực hiện trên project lak-rebuild-b406a316e7 với hai volume DB mới, network/cổng/credential riêng. Nạp lại source/DW và metadata tin tức lưu sẵn, kiểm tra mô hình, mart và 8 trang. CDC tạo epoch mới, dùng no_data sau đối soát dữ liệu nền, giữ old ledger ở epoch cũ. Có 4 checkpoint mới, connector/task RUNNING; demo mới qua ML và web đạt, fact lịch sử/model registry không đổi. Airflow scheduler được kiểm tra và DAG mart được unpause.

Đã kiểm chứng môi trường riêng trên cùng Docker engine, chưa thử máy/engine vật lý khác. Bundle cuối bảo tồn đúng đầu vào đã kiểm chứng và thêm tooling/tài liệu hiện hành; byte ZIP cuối được tạo sau lượt thử, không giả định đã chạy lại chính ZIP đó. Final manifest ghi rõ sự khác nhau này.

## 9. Sử dụng AI và kết luận

Trợ lý hỗ trợ thiết kế, mã, script, kiểm thử, phân tích bằng chứng và tài liệu; người dùng thực chạy hệ thống Windows/Docker và gửi output. Nhóm chịu trách nhiệm hiểu nghiệp vụ, kiểm tra kết quả và trình bày trung thực. Các hạn chế về dữ liệu, đánh giá ML, đo lường và phạm vi dựng lại được giữ trong báo cáo và slide.

Hệ thống đáp ứng phạm vi 13 giai đoạn đã chốt khi bundle cuối được tạo và kiểm tra tại máy người dùng; không bổ sung thuật toán/công nghệ ngoài kế hoạch. Cải tiến sau này cần tách thành công việc mới, không dùng để thay đổi kết quả hoặc che hạn chế của bản hiện tại.
