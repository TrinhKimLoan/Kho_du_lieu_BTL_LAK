# Ánh xạ nguồn vào hệ thống LAK mới

MySQL được tạo ở giai đoạn 3 với ba entity giao dịch dự kiến: customers,
products, orders. Bốn Excel theo đơn ghép một-một thành orders trước khi nhập
MySQL để tiền, giao nhận và địa bàn của đơn được sửa cùng một row transaction.
Không giả lập nhiều bảng chuẩn hóa chỉ để tạo nhiều sự kiện CDC.

## Ánh xạ Excel

| Excel và trường | MySQL nguồn / staging dự kiến | Kho / quy tắc |
| --- | --- | --- |
| 02.Ma_Khach_Hang | customers.customer_id | dim_customer.customer_id, surrogate customer_key |
| 02.Gioi_Tinh | customers.gender | dim_customer.gender, Type 1 |
| 02.Tinh_Thanh / Quan_Huyen | customers.profile_city / profile_district | profile_geography_key, không thay địa bàn đơn |
| 03.Ma_San_Pham | products.product_id | dim_product.product_id, version theo quan sát |
| 03.Ten_Hang_Hoa / Loai_Hang | products.product_name / product_group | SCD2 tên/nhóm |
| Luật phân loại tên sản phẩm | products.category_code | category_code trên version sản phẩm, category_key trực tiếp trên fact |
| 03.Don_Gia_San_Pham | products.catalog_unit_price | Chỉ staging để đối chiếu, không tính lại tiền fact |
| 03.Muc_Hang_Hoa | products.product_size_band | Giữ tại staging; không đồng nhất với mức hàng theo đơn |
| 01.Ma_Don | orders.order_id | fact_sales.order_id duy nhất |
| 01.Ma_Khach_Hang / Ma_San_Pham | orders.customer_id / product_id | Tra surrogate keys, không lưu mã dưới dạng số đo |
| 01.So_Luong | orders.quantity | fact_sales.quantity; đối chiếu 05.So_Luong |
| 01.Loai_Giao_Hang | orders.shipping_method | Tra FAST/NORMAL/SLOW; đối chiếu bảng 04 |
| 01.Muc_Hang_Hoa | orders.quantity_band | Thuộc tính đơn, giữ nguyên nhãn |
| 04.Các cặp ngày/giờ | orders.packed_at / dispatched_at / expected_at / received_at | Giữ timestamp và bốn khóa ngày theo vai trò |
| 05.Don_Gia_San_Pham | orders.transaction_unit_price | Giá giao dịch trên fact |
| 05.Tong_Gia_Tri_Hang / VAT_10 | orders.goods_amount / vat_amount | NUMERIC; kiểm tra công thức |
| 05.Phi_Van_Chuyen / Tong_Thanh_Toan | orders.shipping_fee / total_paid | Phí theo đơn; không nhân theo số lượng |
| 06.Kho_Xuat / Xe_Van_Chuyen | orders.warehouse_name / vehicle_type | Thuộc tính mô tả đơn; đối chiếu bản sao bảng 01 |
| 06.Tinh_Thanh / Quan_Huyen | orders.delivery_city / delivery_district | fact_sales.delivery_geography_key |
| Cờ thêm khi nhập/demo | is_demo | Lịch sử false, demo true; phân biệt ngay từ nguồn |
| SHA256 file và vị trí dòng | raw.import_rows | Số dòng Excel gồm header: dòng dữ liệu đầu là 2 |

Ma_Don ở bảng 04/05/06 chỉ là khóa ghép, không sinh thêm đơn. Cột Kho_Xuat,
Xe_Van_Chuyen trùng bảng 01 phải đối chiếu, không tự chọn một bên khi mâu thuẫn.
Tên tài xế trùng giữa bảng 01 và 06 chỉ đối chiếu trong bộ đọc tại máy; không
đưa tên vào MySQL phân tích, raw sanitized, model hoặc báo cáo công khai.

Tên khách, số điện thoại và địa chỉ đầy đủ cũng không nhập vào nguồn mới.
So_Lan_Mua_Goc, So_Don_Hang, Tong_Chi_Tieu và các tổng sẵn theo sản phẩm
giữ trong raw nhập đã tối thiểu hóa để đối soát; không đưa vào features hoặc
trạng thái nguồn giao dịch. Không tạo các tổng đó thành dữ liệu sự kiện mới.

Một đơn có bốn bản ghi truy vết tương ứng bốn tệp 01/04/05/06. Mỗi bản ghi
raw.import_rows dùng (file_name, file_sha256, excel_row_number) để không nhập
lặp ngoài ý muốn; mã entity giúp đi từ fact tới bản ghi gốc qua business key.

## Mã chuẩn hóa

Chuẩn hóa thành Unicode NFC, bỏ khoảng trắng đầu/cuối, gộp khoảng trắng lặp,
casefold để tạo mã địa bàn từ cặp [city,district] theo JSON UTF-8 cố định và
SHA256. Nhãn hiển thị giữ dạng nguồn đã sửa khoảng trắng, không tự đổi địa giới.
geography_code là mã kỹ thuật, không phải mã hành chính do Nhà nước ban hành.

Loại giao: Giao hàng nhanh → FAST; Giao hàng bình thường → NORMAL;
Giao hàng chậm → SLOW. Nhãn ngoài từ điển phải có cảnh báo và xử lý bổ sung,
không tự gán là một trong ba loại chỉ để model dự đoán được.

category_code lấy theo bộ quy tắc có phiên bản. Danh mục UNKNOWN dành cho
thiếu thông tin; OTHER dành cho sản phẩm đã xem nhưng chưa thuộc nhóm định nghĩa.

## Ánh xạ tin

| Nguồn | Staging | Kho |
| --- | --- | --- |
| id | external_id | Truy vết ngoài, không coi luôn là khóa bài canonical |
| url | canonical_url, article_key theo quy tắc định danh | fact_news.article_key / canonical_url |
| title | title | fact_news.title |
| publish_date | published_date | published_date_key |
| indexed_date | indexed_at | Giữ ở staging, khác ngày đăng và ngày thu thập |
| media_name, media_url / URL domain | source_domain chuẩn hóa | dim_news_source |
| Luật title/category | category_codes, relevance_level/reason, rule_version | fact_news và bridge |
| Lần gọi API / seed | raw.news_snapshots, origin, fetched_at | Độ phủ theo query và thời gian trong audit |
| topic, query của seed | payload raw | Metadata thu thập, không dùng như nhãn ML chuẩn |

Không trộn bài demo origin=demo vào số tin thật. Không suy ra bài xóa khi không
trả về trong một cửa sổ API. Cập nhật bridge chỉ thay quan hệ của những bài đã
được xử lý trong transaction tương ứng, không xóa cả bridge khi có một tin mới.
