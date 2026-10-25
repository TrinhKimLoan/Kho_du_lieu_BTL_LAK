# Thiết kế kho dữ liệu LAK

## Phạm vi giai đoạn 2

Thiết kế này dựa trên dữ liệu giai đoạn 1 được người dùng xác nhận PASS trên
Windows, commit 3e43b27. Có hai fact và bảy dimension. Không thêm dữ liệu nghiệp
vụ, không đổi hai thuật toán, không thay bộ Excel bằng Online Retail II.

SQL ở `sql/phase2/001_warehouse_schema.sql` chỉ dành cho CSDL LAK mới và rỗng.
Nó cố ý không âm thầm sửa schema cũ. Không chạy nó vào CSDL của LAK gốc hoặc
CommerceInsight. Đây chưa phải hệ thống CDC hay loader đã được cài đặt.

## Các tầng

| Schema | Vai trò | Ví dụ |
| --- | --- | --- |
| raw | Dữ liệu nhập đã loại trường cá nhân không cần thiết và sự kiện nguồn bền vững | import_rows, cdc_events, news_snapshots |
| staging | Trạng thái hiện có của nguồn, đã chuyển kiểu, giữ cờ xóa và vị trí nguồn | customers, products, orders, news_articles |
| dw | Mô hình chiều và fact với khóa liên kết/ràng buộc | dim_product, fact_sales |
| mart | Dành cho khối con và bảng phân tích giai đoạn 7 | Chưa tạo bảng tổng hợp ở giai đoạn 2 |
| audit | Ledger, lỗi, chất lượng, lần chạy và độ phủ tin | applied_source_transactions, news_coverage |
| ml | Dành cho snapshot, phiên bản model và kết quả ở giai đoạn 8–10 | Chưa tạo model hoặc bảng gán cụm giả |

Raw mới là bản ghi đầu vào đã được tối thiểu hóa thông tin cá nhân; tệp Excel
gốc được giữ riêng làm bằng chứng. Không gọi sanitized_payload là bản sao nguyên
byte của dòng Excel. Giữ SHA256 của tệp và số dòng Excel để truy vết.

## Grain và khóa

| Bảng | Một dòng đại diện | Khóa nghiệp vụ | Khóa kho |
| --- | --- | --- | --- |
| dw.fact_sales | Trạng thái một đơn với một sản phẩm | order_id | sales_key |
| dw.fact_news | Trạng thái một bài theo khóa canonical của pipeline | article_key | news_key |
| dw.bridge_news_category | Một cặp bài và danh mục được gán | news_key + category_key | Khóa ghép |

Ví dụ: DH000001 có số lượng 4 nhưng vẫn chỉ có một fact bán hàng, không phải
bốn dòng fact. Ảnh chụp sự kiện sửa DH000001 nằm ở raw; fact giữ trạng thái đã
chiếu mới nhất của chính đơn này, không thêm một dòng doanh thu thứ hai.

Không tách fact giao hàng: nguồn có đúng một bộ giao nhận theo đơn, chưa có mã
lần giao hoặc nhiều kiện. Tách lúc này sẽ nhân bản grain và phí mà không thêm
thông tin. Các mốc giao nhận và chỉ tiêu vận chuyển nằm trong fact_sales.

Không ghép business key cùng cờ demo làm khóa mới: order_id vẫn duy nhất toàn
nguồn. Mã demo có namespace riêng, is_demo không được đổi để biến lịch sử thành
demo. Không tạo đơn mới trùng mã lịch sử.

## Dimension

| Dimension | Business key | Lịch sử | Vai trò |
| --- | --- | --- | --- |
| dim_date | full_date, key YYYYMMDD | Lịch cố định | Bốn vai trò ngày của đơn và ngày đăng tin |
| dim_customer | customer_id | Type 1 | Hồ sơ hiện tại, không khẳng định địa bàn khách trong quá khứ |
| dim_product | product_id + khoảng quan sát | Type 2 | Giữ phiên bản tên, nhóm và danh mục sản phẩm |
| dim_category | category_code | Code ổn định, sửa tên hiển thị Type 1 | Chiều dùng chung giữa bán hàng và tin |
| dim_geography | geography_code từ city/district chuẩn hóa | Tuple địa lý ổn định | Địa bàn theo đơn và vai trò hồ sơ khách |
| dim_shipping_method | FAST/NORMAL/SLOW | Sửa tên hiển thị Type 1 | Dịch vụ vận chuyển |
| dim_news_source | domain canonical | Sửa tên hiển thị Type 1 | Nguồn bài báo |

Mọi dimension có thành viên chưa biết key 0. Key 0 không phải OTHER: OTHER là
danh mục đã phân loại nhưng không thuộc nhóm được định nghĩa; UNKNOWN là chưa
đủ thông tin. Thiếu thông tin được gắn cờ, không tự gán thành một nhóm thật.

dim_geography có hai vai trò: delivery_geography_key trong fact lấy từ bảng 06;
profile_geography_key trong dim_customer lấy từ bảng 02. Không dùng địa chỉ hồ
sơ hiện tại để ghi đè địa bàn của tất cả giao dịch cũ.

Kho xuất, loại xe và nhãn mức hàng nằm trên fact như thuộc tính mô tả đơn.
Chưa tạo dimension riêng vì phạm vi hiện tại chưa cần lịch sử thuộc tính kho/xe.
Tên tài xế, khách, điện thoại, địa chỉ đầy đủ không nằm trong schema phân tích mới.

## SCD2 theo thời điểm quan sát

Các thuộc tính tạo version mới: product_name, product_group, category_code.
Fact tham chiếu trực tiếp dim_category qua category_key để phân tích theo hình
sao. Khi chiếu đơn, tra category_key từ category_code của version sản phẩm đã
gắn; không lấy danh mục hiện tại để đổi lại fact cũ. Chất lượng phải đối soát
category_code trên version với category_code của category_key trên fact.
Giá danh mục giữ ở staging.products để đối chiếu, không lấy nó tính lại tiền đơn
và không trình bày nó như lịch sử giá giao dịch. Đơn giá giao dịch nằm trên fact.

Khoảng hiệu lực là [valid_from, valid_to), valid_to NULL cho phiên bản hiện tại.
DDL có exclusion constraint chống chồng khoảng và unique index một bản hiện tại.
Extension btree_gist phục vụ ràng buộc này; script test dùng PostgreSQL riêng.

valid_from là thời điểm hệ thống áp dụng và quan sát trạng thái, không phải ngày
sản phẩm thật thay tên ngoài thị trường. Applier lưu mốc áp dụng trong ledger;
mỗi product chỉ chiếu trạng thái cuối cùng của một transaction. Nếu nhiều thay
đổi có cùng độ phân giải đồng hồ, runtime phải đảm bảo mốc version tăng nghiêm
ngặt thay vì tạo khoảng rỗng; logic này kiểm thử ở giai đoạn 5.

Snapshot đầu có thể quan sát sản phẩm năm 2026 rồi gắn đơn năm 2020 vào phiên
bản bootstrap đó. Đây là phiên bản danh mục được biết lúc nạp, không phải bằng
chứng tên sản phẩm tại giao dịch năm 2020. Không join packed_at vào khoảng SCD2
quan sát để giả vờ có lịch sử nghiệp vụ trước lúc thu thập.

Khi chỉ thay tên/danh mục sản phẩm, không đổi product_key/category_key trên fact đã có.
Khi sửa một đơn mà product_id không đổi, giữ product_key của đơn. Nếu chính đơn
được sửa sang product_id khác, gắn version và danh mục của sản phẩm mới tại thời
điểm áp dụng. Đổi is_deleted của sản phẩm không làm mất số tiền trên các fact
đã tham chiếu. Không lọc số tiền lịch sử theo is_current của dim_product.

## Thời gian và số đo

Phân cấp chính: năm → quý → tháng → ngày. Các thuộc tính tháng được đọc cùng
năm khi tổng hợp nhiều năm; không gộp mọi tháng 1 của sáu năm ngoài chủ đích.
iso_week chỉ là thuộc tính hỗ trợ, chưa dùng một phân cấp năm ISO chưa định nghĩa.

packed/dispatched/expected/received_at là timestamp địa phương chưa xác minh
timezone. Các thời điểm capture/apply/kiểm tra dùng timestamptz. Ngày không biết
là key 0 và full_date NULL, không tạo một ngày 1900 giả làm giao dịch thật.

Tiền dùng NUMERIC: đơn giá 18,2; tổng tiền 20,2. Số lượng nguyên dương. Quy tắc
VAT 10% là quy tắc của bộ mô phỏng, không phải phát biểu về thuế hiện hành.
Fact có ràng buộc tiền hàng, VAT và tổng thanh toán. Giao dịch không đạt gate tiền
không được đánh dấu áp dụng thành công; raw và lỗi phải được giữ để sửa/retry.

delivery_hours tính từ nhận trừ giao đi khi đủ hai mốc và không âm. Nhãn âm
cho NULL và bật received_before_dispatched; vẫn giữ tiền hàng. Khi thiếu giờ
hoặc chưa nhận thì delivery_hours NULL, không biến thành 0 giờ.
dispatched_before_packed và expected_before_dispatched là cờ quan sát riêng.
Các cờ có thể NULL khi thiếu mốc; NULL không đồng nghĩa đã kiểm tra và hợp lệ.

## Tổng hợp và ML

quantity, goods_amount, vat_amount, shipping_fee, total_paid cộng được ở grain
hiện tại. transaction_unit_price, delivery_hours trung bình, số khách duy nhất
và AOV không cộng trực tiếp giữa các khối. Trung bình phải dùng tổng và mẫu số
hợp lệ; số khách phải đếm distinct trên đúng phạm vi.

Hai khối con dự kiến giai đoạn 7: bán hàng theo tháng × danh mục, bán hàng/giao
nhận theo tháng × quận/huyện × loại giao. Cả hai phải đối soát fact. Chưa tạo
materialized view hoặc cube trong gói giai đoạn 2 để không đi trước kế hoạch.

RFM đọc dw.v_sales_analysis, lấy customer_id qua dim_customer, R theo ngày đóng
gói đại diện, F distinct order_id, M goods_amount. Random Forest dùng cùng view
và hợp đồng feature tại dispatched_at đã chốt giai đoạn 1. Chưa có model mới.

## Tin và bridge

Không có foreign key trực tiếp từ bán hàng tới một bài báo. Chỉ so sánh sau khi
tổng hợp riêng theo cùng kỳ và danh mục. Đếm tin bằng DISTINCT news_key để không
cộng đúp bài đa danh mục; doanh số không join thẳng tới bridge rồi SUM.

audit.news_coverage theo tháng/danh mục/chữ ký truy vấn/origin. COMPLETE chỉ có
nghĩa hoàn thành truy vấn được công bố trong tháng và phân trang, không có nghĩa
đã thu được mọi bài trên Internet. Seed 2024 không tự tạo COMPLETE cho sáu năm.
Độ phủ thiếu trả NULL/chưa đủ dữ liệu thay vì suy ra 0 tin.

## Giới hạn chứng cứ giai đoạn 2

DDL, hợp đồng và bộ thử constraint không thực hiện CDC, retry hoặc SCD2 runtime.
Fixture PostgreSQL chỉ kiểm tra schema/ràng buộc và ví dụ join. Không dùng kết
quả này để tuyên bố collector/applier, snapshot nguồn hay model đã hoạt động.
