# Chỉ tiêu và grain của mart

Mọi bảng loại `is_demo` và `is_deleted` qua view phân tích, tiền VND dùng NUMERIC. packed_at là ngày đóng gói, không phải ngày đặt hoặc ngày ghi nhận doanh thu kế toán. Địa bàn lấy từ đơn, không lấy địa bàn hồ sơ khách.

| Chỉ tiêu | Công thức tại đúng phạm vi lọc | Quy tắc cộng |
|---|---|---|
| Số đơn | COUNT fact/order_id duy nhất | Cộng được qua các cell bán hàng không chồng nhau |
| Số lượng | Tổng quantity | Cộng được |
| Tiền hàng | Tổng goods_amount | Cộng được, không phải lợi nhuận |
| VAT/phí/tổng thanh toán | Tổng từng cột tương ứng | Cộng được; không trộn với tiền hàng |
| Số khách | COUNT DISTINCT customer_key | Tính lại từ cells; không cộng số khách của các ngày/nhóm |
| Giá trị đơn tiền hàng trung bình | SUM(goods_amount)/SUM(order_count) | Không cộng hoặc lấy AVG các trung bình con |
| Thời gian giao trung bình, giờ | SUM(delivery_hours_sum)/SUM(delivered_orders) | Giữ tổng giờ và số nhãn hợp lệ, không AVG trung bình nhóm |
| Số đơn có nhãn giao hợp lệ | COUNT(delivery_hours) | Nhãn NULL không vào mẫu số; đơn vẫn được tính tiền |
| Tỷ lệ vi phạm SLA | Không công bố | expected_at chưa được xác minh là cam kết |
| Số bài tổng cộng | Tổng news_daily.article_count | Một article có một ngày/nguồn/mức liên quan, cộng được qua các cell không chồng |
| Số bài theo nhóm/toàn bộ nhóm | COUNT DISTINCT news_key trên news_membership | Không cộng số bài của các nhóm khi bài thuộc nhiều nhóm |
| Số nguồn tin | COUNT DISTINCT news_source_key | Không cộng số nguồn giữa các ngày/nhóm |
| Bài có trọng số | SUM(1/số nhóm của bài) | Tổng các nhóm bằng số bài có phân loại; không coi là số bài nguyên |

Một nguồn tin có thể xuất hiện nhiều tháng. Một khách có thể mua nhiều nhóm. Bridge không tạo thêm fact và không cho phép nhân doanh số.

| Bảng | Một dòng đại diện |
|---|---|
| mart.sales_cells | Một tổ hợp ngày đóng gói, ngày gửi, nhóm hàng, địa bàn giao, phiên bản sản phẩm, khách, hình thức vận chuyển |
| mart.sales_daily | Ngày đóng gói × nhóm × địa bàn giao |
| mart.product_daily | Ngày đóng gói × phiên bản sản phẩm × nhóm |
| mart.customer_summary | Một khách trên toàn snapshot hiện tại; chưa phải dataset RFM/model phiên bản |
| mart.delivery_daily | Ngày gửi × hình thức vận chuyển × địa bàn giao |
| mart.news_daily | Ngày xuất bản × nguồn × mức liên quan, gồm cả IRRELEVANT |
| mart.news_membership | Một bài × một nhóm, chỉ DIRECT/INDIRECT |
| mart.news_category_daily | Ngày xuất bản × nhóm × nguồn × mức liên quan |
| mart.news_coverage | Tháng × nhóm, trạng thái truy vấn API hiện hành |

Số khách đã lưu trong sales_daily/product_daily chỉ đúng tại grain đó. Truy vấn roll-up dùng sales_cells với DISTINCT; customer_summary không dùng để trả lời số khách riêng cho một năm bằng cách lọc nhầm snapshot toàn lịch sử.

Truy vấn sản phẩm có thể gộp business ID hoặc tách product_version. Join theo surrogate product_key để giữ tên/nhóm lịch sử; không lọc is_current khi đọc các fact cũ.

Trong v_month_category_comparison, bán hàng và tin tức được tổng hợp riêng trước khi FULL JOIN một dòng/tháng/nhóm. Số tin quan sát có thể là 0 trong phạm vi đã lưu; comparable_article_count vẫn NULL nếu coverage chưa COMPLETE. Khi chỉ có tin ngoài thời gian bán hàng, giá trị sales là NULL, không tự gọi đó là doanh số thực tế bằng 0. COMPLETE chỉ áp dụng query/collection cấu hình, không chứng minh đầy đủ toàn thị trường. Không suy ra quan hệ nhân quả từ bảng này.
