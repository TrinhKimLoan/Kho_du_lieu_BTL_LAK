# KẾ HOẠCH NÂNG CẤP LAK

## 1. Mục tiêu và phạm vi dự án

**Tên đề xuất:**

> **LAK Analytics — Hệ thống kho dữ liệu, phân tích kinh doanh và khai phá dữ liệu cho thương mại điện tử linh kiện máy tính.**

Hệ thống phục vụ ba nhóm nhu cầu:

| Nhu cầu                           | Câu hỏi hệ thống cần trả lời                                                                                         |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| Phân tích kinh doanh              | Doanh thu biến động thế nào? Sản phẩm, nhóm hàng, địa bàn nào đóng góp nhiều?                                        |
| Phân tích khách hàng và giao hàng | Khách hàng thuộc nhóm nào? Đơn hàng có thể mất bao lâu để giao?                                                      |
| Theo dõi thông tin thị trường     | Tin tức liên quan đến nhóm sản phẩm thay đổi thế nào theo thời gian? Có cùng biến động với hoạt động bán hàng không? |

**Yêu cầu bắt buộc của bản nâng cấp:**

1. Có kho dữ liệu với mô hình chiều, xác định rõ mức chi tiết của từng bảng fact.
2. Có **CDC thực sự cho dữ liệu giao dịch**, xử lý được thêm, sửa, xóa.
3. Có đối soát và kiểm tra chất lượng dữ liệu.
4. Có OLAP và trực quan hóa bằng bảng kết hợp biểu đồ.
5. Có tối thiểu **hai thuật toán ML khác nhau**:
   - KMeans để phân khúc khách hàng bằng RFM.
   - Random Forest Regressor để dự đoán thời gian giao hàng, nếu dữ liệu đạt điều kiện.
6. Có website thể hiện rõ phần phân tích, phần ML và phần vận hành CDC.
7. Có kiểm thử, tài liệu, kịch bản demo và hướng dẫn chạy trên máy khác.

**Không đưa vào phạm vi bắt buộc:**

- Website bán hàng, thanh toán, quản lý giỏ hàng.
- Hệ thống đề xuất sản phẩm.
- Dự báo giá linh kiện hoặc khẳng định tin tức gây ra thay đổi doanh thu.
- Huấn luyện lại mô hình sau mỗi sự kiện CDC.
- Kafka, Spark hoặc công cụ khác chỉ để làm kiến trúc trông lớn hơn.

Các phần mở rộng chỉ làm sau khi phần bắt buộc đã hoàn thành và được kiểm chứng.

## 2. Những nguyên tắc phải giữ khi triển khai

**Giữ nguyên bản LAK và CommerceInsight hiện tại.** Làm bản nâng cấp trong thư mục hoặc nhánh Git riêng, đặt tên dự kiến `LAK-Analytics`.

Trước khi viết mã:

- Đọc source thực tế, cấu trúc dữ liệu, tài liệu và cấu hình hiện có.
- Phân biệt rõ chức năng đã có, chức năng mới chỉ được mô tả và chức năng cần sửa.
- Không mặc định những kết luận từ đoạn chat cũ đều đúng với phiên bản source mới nhất.
- Không tự thay dữ liệu LAK bằng Online Retail II.
- Không mang mô hình KMeans đã huấn luyện trên Online Retail II sang dự đoán cho LAK.
- Không thay đổi nghiệp vụ chỉ để khớp với mã CommerceInsight.

Trong quá trình làm:

- Mỗi giai đoạn có đầu ra, kiểm tra và commit riêng.
- Giải thích cho sinh viên hiểu trước khi yêu cầu chạy lệnh.
- Lệnh phải phù hợp Windows PowerShell.
- Không xóa volume hoặc reset dữ liệu để xử lý lỗi thông thường.
- Không ghi đè bằng chứng kiểm thử cũ mà không phân biệt lần chạy.
- Không tuyên bố hoàn thành chỉ vì script không báo lỗi.
- Không khẳng định dự án đạt điểm cao nhất; phải chứng minh bằng kết quả.

## 3. Kiến trúc dự kiến

Hệ thống có **hai luồng dữ liệu riêng**.

**Luồng giao dịch:**

> Excel lịch sử LAK → nạp vào MySQL nguồn → Debezium đọc binlog → Kafka → bộ thu sự kiện → PostgreSQL raw/staging → kho dữ liệu → bảng tổng hợp → ML và website.

MySQL đóng vai trò **hệ thống giao dịch mô phỏng**. Những thay đổi dùng để demo sẽ được thực hiện tại MySQL.

Cần trình bày đúng:

> Dữ liệu Excel được dùng để khởi tạo lịch sử. CDC bắt thay đổi trong MySQL sau khi nạp, không trực tiếp theo dõi thay đổi của file Excel.

**Luồng tin tức:**

> MediaCloud API → tác vụ thu thập theo lịch → raw snapshot → phát hiện thay đổi bằng khóa và hash → chuẩn hóa, phân loại liên quan → kho dữ liệu tin tức → website.

Cần phân biệt:

- CDC giao dịch: dựa trên binlog.
- Phát hiện thay đổi tin tức: dựa trên việc gọi API định kỳ và so sánh dữ liệu.

Không coi một bài báo không xuất hiện trong một lần gọi API là đã bị xóa.

**Công nghệ dự kiến:**

| Thành phần               | Công nghệ                                                        |
| ------------------------ | ---------------------------------------------------------------- |
| Môi trường               | Windows, WSL2, Docker Compose, Python                            |
| CSDL giao dịch           | MySQL                                                            |
| CDC                      | Debezium, Kafka                                                  |
| Kho dữ liệu              | PostgreSQL                                                       |
| Xử lý dữ liệu            | Python, pandas, SQLAlchemy, psycopg                              |
| Điều phối tác vụ định kỳ | Airflow hiện có, sau khi đánh giá tài nguyên                     |
| ML                       | scikit-learn                                                     |
| Website phân tích        | Streamlit, Plotly                                                |
| API                      | Giữ và điều chỉnh FastAPI hiện có nếu có nhu cầu sử dụng thực tế |
| Kiểm thử                 | pytest, kiểm thử SQL, kiểm thử tích hợp                          |
| Quản lý phiên bản        | Git, cấu hình môi trường và phiên bản mô hình                    |

**Không bắt Streamlit gọi vòng qua FastAPI cho mọi truy vấn nếu điều đó chỉ làm hệ thống phức tạp hơn.** Logic nghiệp vụ và truy vấn phải được tổ chức dùng chung; API được giữ khi có vai trò rõ ràng.

Máy triển khai có khoảng 16 GB RAM, vì vậy phải đo tài nguyên và cân nhắc chạy Airflow theo profile riêng khi cần.

---

## Giai đoạn 0 — Kiểm kê source và giữ bản gốc

**Mục đích:** Biết chính xác chúng ta đang có gì trước khi sửa.

**Công việc:**

- Đọc source LAK và tài liệu tổng quan.
- Đọc các phần CommerceInsight có khả năng tái sử dụng.
- Lập danh sách:
  - Thành phần giữ lại.
  - Thành phần cần sửa.
  - Thành phần bổ sung.
  - Thành phần không sử dụng.
- Kiểm tra cấu hình, biến môi trường, thư viện, Docker và các lệnh khởi động.
- Tạo bản nâng cấp riêng và commit nền ban đầu.

**Sản phẩm:**

- `docs/current_state.md`
- `docs/upgrade_plan.md`
- Sơ đồ kiến trúc hiện tại và kiến trúc mục tiêu.

**Điều kiện hoàn thành:** Xác định được đường chạy của dữ liệu hiện tại và không làm thay đổi hai bản gốc.

---

## Giai đoạn 1 — Kiểm tra dữ liệu và chốt nghiệp vụ

**Mục đích:** Tránh thiết kế kho và ML dựa trên những giả định sai.

**Công việc:**

Kiểm tra toàn bộ các file LAK:

- Số dòng, số khóa duy nhất, dữ liệu thiếu và trùng.
- Quan hệ giữa đơn hàng, khách hàng, sản phẩm, giao hàng và thanh toán.
- Một đơn có một hay nhiều sản phẩm.
- Một đơn có một hay nhiều lần giao.
- Ý nghĩa chính xác của từng trường ngày.
- Công thức tiền hàng, thuế, phí vận chuyển và tổng thanh toán.
- Tình trạng đơn hủy, hoàn hàng, giao thất bại nếu có.
- Nguồn gốc dữ liệu: thực tế, tổng hợp hay giả lập.
- Phạm vi thời gian của giao dịch và tin tức.
- Các trường thông tin cá nhân cần hạn chế hiển thị.

Đặc biệt phải kiểm tra:

- Trường đang được gọi là ngày đặt hàng có thực sự là **ngày đóng gói** không.
- Dữ liệu có đủ khách hàng mua nhiều lần để phân khúc có ý nghĩa không.
- Dữ liệu giao hàng có đủ thông tin sẵn có tại thời điểm dự đoán không.
- Dữ liệu có thực sự chứa nhiều sản phẩm trên cùng một đơn hay không.

**Sản phẩm:**

- `docs/data_dictionary.md`
- `docs/data_quality_profile.md`
- `docs/business_definitions.md`
- Script kiểm tra dữ liệu chạy lại được.

**Điều kiện hoàn thành:** Chốt được định nghĩa chỉ tiêu, khóa, quan hệ, ngày tháng và tính khả thi của hai bài toán ML.

**Nếu dữ liệu không phù hợp với bài toán dự đoán giao hàng:** báo rõ nguyên nhân và đề xuất bài toán thay thế trước khi viết mô hình; không tự tạo nhãn để có đủ hai thuật toán.

---

## Giai đoạn 2 — Thiết kế kho dữ liệu và hợp đồng dữ liệu

**Mục đích:** Xây nền tảng đúng cho các phép tổng hợp, CDC và ML.

**Công việc:**

Thiết kế các tầng:

- `raw`: dữ liệu gốc và sự kiện.
- `staging`: dữ liệu chuẩn hóa, trạng thái nguồn.
- `dw`: fact và dimension.
- `mart`: bảng phục vụ phân tích.
- `audit`: đối soát, lỗi và lịch sử xử lý.
- `ml`: phiên bản mô hình và kết quả dự đoán.

Các dimension dự kiến:

- Ngày.
- Khách hàng.
- Sản phẩm.
- Nhóm sản phẩm.
- Địa lý.
- Hình thức vận chuyển.
- Nguồn tin tức.

Các fact:

- Fact bán hàng: mức đơn hoặc dòng đơn, chốt sau giai đoạn 1.
- Fact tin tức: một bản ghi cho một bài báo theo quy tắc định danh.
- Fact giao hàng: chỉ tách riêng nếu nghiệp vụ và mức chi tiết thực sự cần.

Quy định:

- Tiền dùng `DECIMAL/NUMERIC`.
- Có surrogate key và business key rõ ràng.
- Có thành viên “chưa biết” cho khóa thiếu khi phù hợp.
- Có khóa ngày theo vai trò: đóng gói, gửi, nhận, dự kiến… theo dữ liệu thực có.
- Không nhân đôi thuế hoặc phí vận chuyển khi chuyển sang mức dòng đơn.
- Bridge tin tức–nhóm sản phẩm phải có quy tắc tổng hợp tránh đếm trùng.

**Sản phẩm:**

- ERD.
- Tài liệu grain của từng fact.
- SQL tạo schema.
- Quy tắc ánh xạ nguồn → staging → DW.
- Quy tắc thêm, sửa, xóa.

**Điều kiện hoàn thành:** Có thể giải thích bằng một ví dụ cụ thể: “một dòng trong bảng này đại diện cho điều gì”.

---

## Giai đoạn 3 — Xây hệ thống giao dịch nguồn và nạp lịch sử

**Mục đích:** Tạo nguồn giao dịch có thể phát sinh thay đổi để CDC theo dõi.

**Công việc:**

- Tạo schema MySQL phù hợp dữ liệu LAK.
- Viết chương trình nhập dữ liệu lịch sử.
- Giữ thông tin truy vết file và dòng nguồn.
- Kiểm tra khóa ngoại và các phép tính tiền.
- Chạy lại chương trình không tạo bản sao ngoài ý muốn.
- Tạo bộ dữ liệu demo riêng có cờ phân biệt.
- Xây thao tác demo thêm, sửa, xóa giao dịch.

**Sản phẩm:**

- SQL nguồn.
- Script nạp lịch sử.
- Script demo giao dịch.
- Báo cáo đối soát Excel → MySQL.

**Điều kiện hoàn thành:** Số dòng và các tổng tiền khớp với dữ liệu đã chuẩn hóa; demo không ảnh hưởng dữ liệu lịch sử.

---

## Giai đoạn 4 — Triển khai CDC đầu cuối

**Mục đích:** Thay đổi trong MySQL tự đi vào kho dữ liệu.

**Công việc:**

- Cấu hình binlog MySQL và Debezium.
- Tạo topic, khóa sự kiện và cấu hình connector.
- Chụp snapshot ban đầu.
- Lưu raw event bền vững trước khi xác nhận Kafka offset.
- Áp dụng giao dịch vào staging và DW.
- Xử lý `insert`, `update`, `delete`, snapshot và tombstone.
- Chờ đủ sự kiện của giao dịch khi cần.
- Chống áp dụng lặp bằng khóa sự kiện và transaction ledger.
- Xử lý khởi động lại và sự kiện metadata lặp một cách có kiểm chứng.
- Ghi nhận lỗi để có thể sửa và chạy lại.

**Sản phẩm:**

- Cấu hình connector.
- Raw collector.
- Warehouse applier.
- Script kiểm tra snapshot.
- Kiểm thử CDC trực tiếp và replay.

**Điều kiện hoàn thành:**

- Snapshot đối soát khớp nguồn.
- Thêm, sửa, xóa xuất hiện đúng trong DW.
- Replay không nhân đôi doanh thu.
- Dừng rồi chạy lại tiếp tục được từ trạng thái đã lưu.

---

## Giai đoạn 5 — Lịch sử dimension, chất lượng và đối soát

**Mục đích:** Kho dữ liệu đáng tin cậy và giải thích được khi có sai lệch.

**Công việc:**

- Chọn thuộc tính cần SCD Type 2, ưu tiên sản phẩm nếu có thay đổi phân loại hoặc tên.
- Quy định rõ thuộc tính cập nhật Type 1.
- Định nghĩa thời gian hiệu lực là thời gian nghiệp vụ hay thời gian hệ thống quan sát.
- Không tự suy diễn lịch sử trước thời điểm bắt đầu thu thập.
- Kiểm tra:
  - Khóa duy nhất.
  - Quan hệ fact–dimension.
  - Công thức tiền.
  - Khoảng thời gian hợp lệ.
  - SCD2 không chồng khoảng.
  - Fact trỏ đúng phiên bản dimension.
  - Dữ liệu cần xem xét nghiệp vụ.
- Đối soát nguồn → staging → DW.
- Phân biệt lỗi kỹ thuật và cảnh báo nghiệp vụ.
- Có cơ chế retry sau khi sửa nguyên nhân lỗi.

**Sản phẩm:**

- Migration SCD2.
- Bộ quy tắc chất lượng.
- Bảng lỗi, cảnh báo và lịch sử kiểm tra.
- Báo cáo đối soát.

**Điều kiện hoàn thành:** Lỗi nghiêm trọng bằng 0; cảnh báo còn lại có giải thích và không bị âm thầm loại bỏ.

---

## Giai đoạn 6 — Hoàn thiện luồng tin tức

**Mục đích:** Biến tin tức thành một phần phân tích có ý nghĩa, có nguồn gốc và giới hạn rõ ràng.

**Công việc:**

- Rà soát luồng MediaCloud hiện có.
- Chuẩn hóa URL, khóa bài và hash nội dung.
- Phân biệt bài mới, bài thay đổi và bài không đổi.
- Lưu thời điểm xuất bản và thời điểm thu thập riêng.
- Ghi nhận tình trạng phân trang, giới hạn API và lần thu thập chưa đầy đủ.
- Rà soát quy tắc gắn bài với CPU/GPU/RAM/SSD hoặc nhóm thực tế.
- Hiển thị lý do phân loại.
- Kiểm tra thủ công một mẫu để đánh giá mức phù hợp.
- Xác định cách xử lý bài thuộc nhiều nhóm.
- Kiểm tra độ phủ thời gian trước khi so sánh với doanh số.

**Sản phẩm:**

- Pipeline tin tức được kiểm tra.
- Fact tin tức và bridge.
- Báo cáo độ phủ dữ liệu.
- Tài liệu quy tắc liên quan.

**Điều kiện hoàn thành:** Truy vết được bài báo về nguồn; so sánh tin tức–doanh thu không làm nhân bản doanh thu.

**Giới hạn bắt buộc:** Phân loại bằng từ khóa phải gọi đúng là phân loại theo quy tắc, không tính là một thuật toán ML đã huấn luyện.

---

## Giai đoạn 7 — Data mart, OLAP và chỉ tiêu phân tích

**Mục đích:** Chuẩn bị dữ liệu nhanh, nhất quán cho website.

**Công việc:**

Xây các mart phù hợp:

- Bán hàng theo thời gian, nhóm hàng và địa bàn.
- Sản phẩm.
- Khách hàng.
- Giao hàng.
- Tin tức theo thời gian và nhóm hàng.

Hỗ trợ:

- Roll-up.
- Drill-down.
- Slice.
- Dice.
- Pivot.

Chỉ tiêu phải có định nghĩa:

- Tiền hàng, thuế, phí vận chuyển, tổng thanh toán.
- Số đơn và số khách hàng.
- Giá trị đơn trung bình.
- Thời gian giao hàng.
- Tỷ lệ giao trễ **chỉ khi có mốc cam kết đủ tin cậy**.
- Số bài báo và số nguồn tin.

Chọn cập nhật tăng dần hoặc refresh theo lịch cho từng mart; ghi rõ độ trễ.

**Sản phẩm:**

- SQL mart/cube.
- Bộ truy vấn OLAP.
- Tài liệu KPI.
- Kiểm thử mart so với fact.

**Điều kiện hoàn thành:** Kết quả tổng hợp khớp fact, không cộng trực tiếp các chỉ tiêu không cộng được như số khách duy nhất hoặc trung bình.

---

## Giai đoạn 8 — ML số 1: Phân khúc khách hàng bằng KMeans

**Mục đích:** Tìm những nhóm khách hàng có hành vi mua khác nhau để hỗ trợ chăm sóc khách hàng.

**Công việc:**

- Chốt ngày tham chiếu và cửa sổ quan sát.
- Xác định giao dịch hợp lệ cho RFM.
- Tính:
  - Recency: thời gian từ lần mua gần nhất.
  - Frequency: số đơn mua.
  - Monetary: giá trị mua theo định nghĩa đã chốt.
- Xử lý dữ liệu thiếu, ngoại lệ và phân phối lệch.
- Chia train/validation/test theo khách hàng.
- Chỉ fit bước tiền xử lý trên train.
- Thử một dải K phù hợp quy mô dữ liệu.
- Đánh giá:
  - Silhouette.
  - Davies–Bouldin.
  - Quy mô nhóm.
  - Độ ổn định.
  - Khả năng giải thích.
- So sánh với phân nhóm nghiệp vụ đơn giản.
- Đặt tên nhóm theo hồ sơ thực tế, không mặc định cluster 0 là VIP.
- Nếu thời gian dữ liệu đủ, xem hành vi mua trong giai đoạn tương lai.

**Sản phẩm:**

- Dataset RFM có phiên bản.
- Pipeline tiền xử lý và mô hình.
- Báo cáo lựa chọn K.
- Hồ sơ từng nhóm.
- Bảng gán nhóm khách hàng.
- Model metadata và checksum.

**Điều kiện hoàn thành:** Kết quả tái lập được, không rò rỉ dữ liệu và giải thích được mỗi nhóm khác nhau ở đâu.

**Lưu ý:** RFM là cách tạo đặc trưng; KMeans mới là thuật toán học máy.

---

## Giai đoạn 9 — ML số 2: Dự đoán thời gian giao hàng

**Thuật toán chính:** Random Forest Regressor.

**Mục đích:** Ước lượng thời gian giao hàng tại một thời điểm nghiệp vụ xác định.

**Công việc:**

- Chốt thời điểm dự đoán, ví dụ lúc đóng gói, nếu phù hợp dữ liệu.
- Định nghĩa nhãn chính xác: từ thời điểm nào đến thời điểm nào.
- Chỉ dùng đặc trưng đã biết tại thời điểm dự đoán.
- Loại bỏ thông tin tương lai:
  - Ngày thực nhận.
  - Thời gian giao thực tế.
  - Trạng thái phát sinh sau khi giao.
  - Các trường được tính trực tiếp từ nhãn.
- Chia train/validation/test theo thời gian.
- Tạo baseline, ví dụ dự đoán trung vị từ train.
- Huấn luyện và điều chỉnh Random Forest trên train/validation.
- Đánh giá test bằng MAE và RMSE.
- Phân tích sai số theo địa bàn, hình thức vận chuyển và nhóm đơn.
- Đánh giá vai trò đặc trưng trên tập giữ lại.
- Lưu mô hình và giới hạn sử dụng.

**Sản phẩm:**

- Dataset huấn luyện.
- Baseline.
- Mô hình Random Forest.
- Báo cáo đánh giá.
- Bảng dự đoán và sai số.
- Trang giải thích đặc trưng.

**Điều kiện hoàn thành:** Có đánh giá trung thực so với baseline. Nếu mô hình không tốt hơn, phải báo kết quả đó và phân tích nguyên nhân.

Không cam kết trước mô hình sẽ đạt một mức “accuracy”; đây là bài toán hồi quy.

---

## Giai đoạn 10 — Kết nối ML với dữ liệu đang thay đổi

**Mục đích:** Chứng minh ML dùng được cùng pipeline, đồng thời giữ việc huấn luyện có kiểm soát.

**Công việc:**

- Lưu model version, thời điểm train, đặc trưng và chỉ số đánh giá.
- Khi giao dịch đổi, đưa khách hàng bị ảnh hưởng vào hàng đợi tính lại RFM.
- Dùng mô hình đã cố định để dự đoán lại nhóm.
- Lưu lịch sử thay đổi nhóm nếu cần.
- Khi đơn hàng đạt thời điểm dự đoán, tạo dự đoán giao hàng và lưu input/model version.
- Khi có kết quả giao thực tế, đối chiếu với dự đoán đã lưu.
- Không dùng thông tin thực nhận để ghi đè dự đoán ban đầu.
- Có cách xử lý khi ngày tham chiếu RFM thay đổi dù không có giao dịch mới.
- Tách dữ liệu demo khỏi chỉ tiêu kinh doanh.

**Sản phẩm:**

- Worker hoặc tác vụ suy luận.
- Hàng đợi bền vững.
- Lịch sử gán nhóm và dự đoán.
- Kiểm thử cập nhật sau CDC.

**Điều kiện hoàn thành:** Thay đổi nguồn đi được đến kết quả ML liên quan, có model version và không tự huấn luyện lại tùy tiện.

---

## Giai đoạn 11 — Xây website phân tích

**Mục đích:** Người xem nhận ra ngay dự án làm gì và phần mining nằm ở đâu.

Website dự kiến có các trang sau:

| Trang                        | Nội dung                                        | Biểu đồ chính                                          |
| ---------------------------- | ----------------------------------------------- | ------------------------------------------------------ |
| Tổng quan kinh doanh         | KPI, bộ lọc thời gian, nhóm hàng, địa bàn       | Xu hướng doanh số, cơ cấu nhóm hàng, top sản phẩm      |
| Phân tích bán hàng & OLAP    | Năm thao tác OLAP, bảng tổng hợp, drill-down    | So sánh kỳ, thanh xếp hạng, heatmap                    |
| Khách hàng & phân khúc ML    | Hồ sơ RFM, nhóm khách, chiến lược chăm sóc      | Quy mô nhóm, phân phối R/F/M, scatter                  |
| Giao hàng & dự đoán ML       | Giao thực tế, dự đoán, sai số và baseline       | Phân phối thời gian, thực tế–dự đoán, sai số theo nhóm |
| Tin tức & thị trường         | Danh sách bài, nguồn, nhóm liên quan, độ phủ    | Số bài theo thời gian, theo nhóm và nguồn              |
| Chi tiết khách hàng/đơn hàng | Tra cứu, lịch sử giao dịch, nhóm và dự đoán     | Lịch sử mua theo thời gian                             |
| Vận hành dữ liệu             | Connector, worker, hàng đợi, lỗi, chất lượng    | Độ trễ và lượng sự kiện theo thời gian                 |
| Demo CDC                     | Thêm, sửa, xóa dữ liệu demo và theo dõi kết quả | Trạng thái từng bước và biến động chỉ tiêu             |

**Yêu cầu giao diện:**

- Có bảng chi tiết đi cùng các biểu đồ tổng hợp thích hợp.
- Không chuyển mọi bảng thành biểu đồ một cách máy móc.
- Thể hiện rõ đơn vị, bộ lọc, thời gian dữ liệu và thời điểm cập nhật.
- Tách “kết quả đánh giá mô hình” khỏi “dự đoán hiện tại”.
- Có giải thích ngắn bằng tiếng Việt cho KPI và ML.
- Có trạng thái trống, lỗi và chờ xử lý.
- Có xuất CSV cho các bảng phù hợp.
- Hạn chế hiển thị tên, điện thoại và địa chỉ cá nhân.
- Chức năng sửa dữ liệu chỉ áp dụng cho dữ liệu demo.

**Điều kiện hoàn thành:** Người chưa đọc source vẫn chỉ được đâu là kho dữ liệu, đâu là mining và đâu là CDC.

---

## Giai đoạn 12 — Kiểm thử toàn hệ thống và đo hiệu năng

**Mục đích:** Có bằng chứng thực nghiệm cho báo cáo.

**Công việc:**

- Kiểm thử nguồn → CDC → DW → mart → ML → web.
- Kiểm thử snapshot, thêm/sửa/xóa và replay.
- Dừng từng worker rồi khởi động lại.
- Kiểm tra dữ liệu thay đổi trong lúc worker dừng được xử lý bù.
- Kiểm tra SCD2 và các phép join không nhân dòng.
- Kiểm tra cube/mart sau khi sửa ngày, địa bàn hoặc sản phẩm.
- Kiểm tra chất lượng dữ liệu, lỗi và retry.
- Kiểm tra ML không dùng thông tin tương lai.
- Kiểm tra các trang web và bộ lọc.
- Đo độ trễ trên một cửa sổ thử nghiệm mới.
- So sánh truy vấn fact với mart có cùng kết quả.
- Đo RAM, CPU và dung lượng đĩa.

**Sản phẩm:**

- Bộ test.
- Báo cáo đối soát.
- Báo cáo recovery.
- Báo cáo hiệu năng có số mẫu và cấu hình máy.
- Danh sách hạn chế.

**Điều kiện hoàn thành:** Không còn lỗi nghiêm trọng, các kết quả đo có phương pháp rõ ràng và dữ liệu lịch sử không bị demo làm thay đổi.

---

## Giai đoạn 13 — Đóng gói, dựng lại và chuẩn bị bảo vệ

**Mục đích:** Người khác có thể chạy và nhóm có thể giải thích dự án.

**Công việc:**

- Khóa phiên bản thư viện và image.
- Có `.env.example`, không đưa mật khẩu thật vào bản nộp.
- Có lệnh khởi động, dừng và xem trạng thái.
- Có hướng dẫn chuẩn bị dữ liệu và API key.
- Có phương án xem dữ liệu tin tức đã lưu khi không có API key, nếu điều kiện sử dụng cho phép; ghi rõ đây là dữ liệu lưu sẵn.
- Đóng gói source, model, cấu hình, tài liệu và bằng chứng cần thiết.
- Dựng lại trong môi trường riêng.
- Ghi rõ mọi thao tác khôi phục thủ công nếu có.
- Soạn hướng dẫn sử dụng và bản đồ thư mục.
- Soạn báo cáo, dàn ý slide, kịch bản demo và câu hỏi bảo vệ.
- Ghi nhận việc sử dụng AI đúng thực tế.

**Sản phẩm cuối cùng:**

1. Source code có quản lý phiên bản.
2. Cấu hình Docker và các script vận hành.
3. Kho dữ liệu với CDC.
4. Pipeline tin tức.
5. Hai mô hình ML và báo cáo đánh giá.
6. Website phân tích.
7. Bộ kiểm thử và bằng chứng đối soát.
8. Bộ tài liệu kỹ thuật, hướng dẫn sử dụng và bảo vệ.
9. Gói release có checksum.
10. Bằng chứng dựng lại từ gói release.

**Điều kiện hoàn thành:** Một máy hoặc môi trường sạch có thể dựng dự án theo hướng dẫn; không phụ thuộc vào dữ liệu âm thầm tồn tại trên máy người phát triển.

---

## 4. Những gì nên tái sử dụng từ CommerceInsight

| Phần                              | Cách sử dụng                                                |
| --------------------------------- | ----------------------------------------------------------- |
| Docker và cấu hình CDC            | Tham khảo, điều chỉnh tên bảng, topic, cổng và môi trường   |
| Raw collector, transaction ledger | Tái sử dụng sau khi kiểm tra tương thích schema LAK         |
| Xử lý replay, soft delete, retry  | Giữ nguyên nguyên tắc; viết lại ánh xạ nghiệp vụ            |
| SCD2                              | Tái sử dụng cách kiểm tra và quản lý phiên bản              |
| Kiểm tra chất lượng               | Tái sử dụng khung, thay quy tắc phù hợp LAK                 |
| Cube và OLAP                      | Tái sử dụng kỹ thuật, thiết kế lại chỉ tiêu và grain        |
| RFM và quy trình đánh giá         | Tái sử dụng quy trình; huấn luyện lại trên LAK              |
| Live RFM, model registry          | Điều chỉnh sau khi mô hình LAK ổn định                      |
| Streamlit                         | Tái sử dụng thành phần giao diện và cấu trúc, thay nội dung |
| Release và vận hành               | Tái sử dụng sau khi sửa cấu hình và kiểm thử                |

**Không tái sử dụng làm kết quả của LAK:** số liệu Online Retail II, mô hình đã train trên dữ liệu đó, checksum và báo cáo kiểm thử của CommerceInsight.

## 5. Cách làm việc bắt buộc trong đoạn chat mới

Mỗi giai đoạn cần thực hiện theo thứ tự:

1. **Giải thích:** đang làm gì, vì sao cần, liên quan bài học nào.
2. **Kiểm tra đầu vào:** source, schema, dữ liệu và trạng thái thực tế.
3. **Triển khai:** sửa đúng phạm vi đã chốt.
4. **Chạy kiểm tra:** cung cấp lệnh và kết quả mong đợi.
5. **Đọc kết quả thực tế:** không suy đoán script đã chạy thành công.
6. **Lưu bằng chứng và commit.**
7. **Tóm tắt:** đã có gì, còn hạn chế gì, bước tiếp theo là gì.

Không triển khai một loạt nhiều giai đoạn khi sinh viên chưa chạy hoặc chưa hiểu bước trước.

## 6. Nội dung gửi mở đầu đoạn chat mới

Em gửi kèm source và dán phần này trước bản kế hoạch:

> Tôi muốn nâng cấp dự án LAK theo kế hoạch bên dưới. Lấy nghiệp vụ và dữ liệu LAK làm chính, tham khảo các thành phần kỹ thuật phù hợp từ CommerceInsight.
>
> Hãy đọc source đính kèm và thực hiện giai đoạn 0 trước. Chưa sửa các bản gốc, chưa triển khai toàn bộ và chưa mặc định schema hoặc dữ liệu đúng như mô tả.
>
> Mục tiêu bắt buộc: kho dữ liệu đúng grain, CDC giao dịch bằng MySQL–Debezium–Kafka, chất lượng và đối soát dữ liệu, OLAP, KMeans phân khúc khách hàng, Random Forest dự đoán thời gian giao hàng nếu dữ liệu phù hợp, website có bảng và biểu đồ, kiểm thử và đóng gói.
>
> Tôi là người mới học. Mỗi giai đoạn cần được giải thích dễ hiểu, có sản phẩm đầu ra, lệnh chạy PowerShell, kiểm tra và commit riêng. Nếu source hoặc dữ liệu mâu thuẫn với kế hoạch, hãy chỉ rõ bằng chứng và đề xuất điều chỉnh trước khi triển khai.
>
> Bắt đầu bằng kiểm kê source và lập danh sách giữ lại/sửa/thêm; sau đó kiểm tra dữ liệu để chốt mô hình kho và tính khả thi của ML.

**Điểm cần chốt đầu tiên ở đoạn chat mới là dữ liệu LAK có đủ và đúng cho các bài toán đã chọn hay không.** Khi điều đó rõ ràng, chúng ta mới viết schema, ML và giao diện; như vậy dự án sẽ dễ bảo vệ và em cũng hiểu được vì sao từng phần tồn tại.