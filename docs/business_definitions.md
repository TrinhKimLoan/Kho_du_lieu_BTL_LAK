# Định nghĩa nghiệp vụ sau kiểm tra dữ liệu

Áp dụng cho bản LAK hiện được cung cấp. Đây là các lựa chọn triển khai được
ghi rõ để có thể giải thích và kiểm thử, không phải xác nhận từ doanh nghiệp.
Không thay đổi dữ liệu nguồn hay phạm vi hai mô hình trong kế hoạch.

## Nguồn và giới hạn

Nguồn có 10.000 đơn, 3.282 khách, 15 sản phẩm. Bốn bảng theo đơn ghép một-một.
Mỗi đơn có một sản phẩm, một bộ thời gian và một dòng thông tin vận chuyển.
Không có mã dòng hàng, mã lần giao, trạng thái hủy/hoàn, ngày đặt hàng,
ngày thanh toán hoặc nhãn giao thất bại. Không tự sinh những trường này như
sự thật lịch sử. API LAK mô tả bán hàng là mô phỏng. Nguồn gốc, quyền sử dụng
và mã sinh dữ liệu chưa được cung cấp; lưu trạng thái chưa xác minh.

## Đơn và tiền

- Đơn hợp lệ cho phân tích lịch sử: mã duy nhất, ghép được khách/sản phẩm,
  số lượng dương nguyên và công thức tiền hợp lệ. Đây không phải khẳng định
  tất cả đơn đã thanh toán hoặc không từng bị hủy trong thực tế.
- Một bản ghi bán hàng hiện đại diện một đơn một sản phẩm. Chưa thiết kế
  giỏ hàng đa sản phẩm hoặc phân bổ phí theo dòng ở giai đoạn này.
- Tiền hàng = So_Luong × Don_Gia_San_Pham trong bảng thanh toán.
- VAT theo quy tắc dữ liệu = 10% tiền hàng; không khái quát thành quy định thuế.
- Tổng thanh toán trong nguồn = tiền hàng + VAT + phí vận chuyển.
- Dùng Decimal khi xử lý và DECIMAL/NUMERIC khi lưu. Không tính lại giá giao dịch
  quá khứ theo giá danh mục mới. Khác giá danh mục là quan sát, không tự sửa.
- Doanh số tiền hàng và tổng thanh toán là hai chỉ tiêu riêng. Không có giá vốn,
  không hiển thị lợi nhuận. Không suy ra thời điểm ghi nhận doanh thu kế toán.
- Số đơn = COUNT DISTINCT mã đơn. Trung bình và số khách duy nhất phải tính
  lại đúng phạm vi, không cộng trung bình hoặc cộng số khách giữa các khối.

## Địa bàn và thời gian

Địa bàn phân tích bán hàng/giao nhận lấy từ đơn trong bảng 06. Hồ sơ khách
ở bảng 02 có vai trò riêng; khác địa chỉ không tự coi là lỗi. Toàn bộ dữ liệu
hiện chỉ có một tỉnh/thành, nên dùng quận/huyện để có biến thiên địa lý.
Giữ nhãn địa bàn lịch sử trong bộ dữ liệu, không áp nhãn địa giới hiện tại.

Ghép từng cặp ngày và giờ thành timestamp địa phương không timezone theo nguồn,
làm tròn đến giây. Chưa có bằng chứng timezone gốc nên không tự chuyển UTC.
Tên vận hành: packed_at, dispatched_at, expected_at, received_at.
Diễn giải Thoi_Gian_Giao_Hang là ngày giao đi, không phải ngày nhận.

packed_at không phải order_created_at. Biểu đồ dùng nó phải ghi rõ ngày đóng gói.
Ngày dự kiến/giờ dự kiến chưa có căn cứ là SLA cam kết. Chưa công bố tỷ lệ giao trễ
làm KPI chính; chỉ có thống kê so sánh với dự kiến với nhãn hạn chế rõ ràng.

880 đơn có dispatched_at < packed_at và 118 đơn có expected_at < dispatched_at:
lưu cờ chất lượng và giữ raw. Không tự đổi chỗ thời gian, không sửa giờ cho đẹp.
Các cờ có thể chồng nhau, không cộng chúng để suy ra số đơn lỗi duy nhất.
Điều kiện dùng cho mỗi phân tích được đánh giá riêng, không loại cả đơn khỏi tiền hàng.

## RFM và K-Means

RFM dùng lịch sử bán hàng hợp lệ trong bộ mô phỏng, không phải xác nhận đã thu tiền.
Ngày tham chiếu ban đầu cố định là 2026-01-01, cửa sổ toàn lịch sử nguồn trước ngày đó.
Giai đoạn 8 có thể so sánh cửa sổ ngắn hơn trên train/validation theo kế hoạch,
nhưng chưa thay snapshot hoặc chọn K theo số đẹp ở giai đoạn này.

- R = ngày tham chiếu trừ ngày đóng gói gần nhất của khách. Ngày đóng gói là
  đại diện hoạt động mua vì thiếu ngày đặt; giao diện phải giải thích giới hạn này.
- F = số mã đơn khác nhau trong cửa sổ, không phải tổng số lượng sản phẩm.
- M = tổng tiền hàng trong cửa sổ, không cộng VAT/phí vận chuyển.
- So_Don_Hang, Tong_Chi_Tieu và các tổng sẵn có chỉ để đối soát,
  không dùng trực tiếp làm đặc trưng tại snapshot quá khứ.
- Bản ghi demo và bản ghi bị xóa khỏi trạng thái nguồn không trộn vào lịch sử
  đánh giá; chính sách hoàn/hủy không thể suy ra khi nguồn không có trạng thái.

K-Means là thuật toán phân cụm, RFM là bộ đặc trưng. Chưa có nhãn VIP chuẩn,
không báo accuracy. Giai đoạn 8 chia theo khách, fit tiền xử lý trên train,
chọn trên validation, giữ test; đánh giá Silhouette, DBI, kích thước/độ ổn định
và ý nghĩa cụm. So sánh phân nhóm nghiệp vụ cơ sở. Chưa train ở giai đoạn 1.

Ngày tham chiếu của demo cũng phải công bố. Không dùng ngày hệ thống năm 2026
để âm thầm làm mọi khách thành lâu không mua trong khi demo lịch sử năm 2025.

## Random Forest dự đoán giao hàng

Giữ Random Forest Regressor là thuật toán thứ hai. Dữ liệu có thể dựng nhãn:
không có nhận trước giao đi trong 10.000 đơn, đủ biến thiên thời gian giao.
Đây là tính khả thi kỹ thuật, chưa chứng minh mô hình hữu ích hơn baseline.

Điểm dự đoán được chọn là lúc giao đi. Nhãn chính:

delivery_hours = (received_at - dispatched_at).total_seconds / 3600.

Đây là số giờ liên tục, không phải số ngày lịch. Dashboard có thể quy đổi sang
ngày 24 giờ nhưng phải ghi đơn vị; không trộn với phép trừ hai ngày lịch.
Không chọn thời gian đóng gói đến nhận làm nhãn vận chuyển.

Đặc trưng có thể dùng nếu được nhập trước/lúc giao đi trong hệ thống mô phỏng:
loại giao, số lượng, sản phẩm/danh mục, giá trị hàng, kho xuất, loại xe,
quận/huyện nhận, tháng và thứ của dispatched_at. Đây là hợp đồng đầu vào
cần được bảo đảm ở MySQL/demo, chưa được dữ liệu lịch sử chứng minh bằng log.

Không dùng received_at, độ trễ, thời gian thực tế, số tiền chi tiêu toàn lịch sử,
mã đơn/mã khách/mã sản phẩm như số thứ tự, hoặc giá trị tính trực tiếp từ nhãn.
Không dùng expected_at trong bộ đặc trưng khởi đầu vì chất lượng và quy luật
sinh dự kiến chưa rõ. Không dùng packed_at làm đặc trưng khởi đầu vì 880 bất nhất.
Tên tài xế, địa chỉ đầy đủ và điện thoại không đưa vào mô hình.

Giai đoạn 9 dự kiến train 2020–2023, validation 2024, test 2025 theo dispatched_at.
Khi fit/chọn mô hình tại mỗi mốc, chỉ dùng nhãn đã nhận trước mốc đó.
Đơn vượt ranh giới thời gian phải được lọc theo điều kiện nhãn sẵn có,
không để dữ liệu của kỳ sau ảnh hưởng model tại kỳ trước. Không đảo ngẫu nhiên
các đơn của cả sáu năm để báo kết quả tương lai.

Baseline dùng trung vị giờ giao trên train theo loại giao, fallback trung vị
toàn train cho loại chưa thấy. MAE/RMSE báo theo giờ, phân tích theo nhóm.
Chưa gán sẵn mức tốt hơn cần đạt; nếu Random Forest không vượt baseline,
giữ kết quả và giải thích. Phân bố ngày theo loại giao rất rõ, mô hình có thể
chủ yếu học quy luật mô phỏng; không quảng bá là đã xác nhận trên vận tải thực.

## Tin tức

Một bài được định danh theo quy tắc article_key hiện có; timestamp xuất bản,
index và thu thập có ý nghĩa riêng. Một bài có thể nhiều danh mục.
Gắn DIRECT/INDIRECT/IRRELEVANT hiện là luật theo tiêu đề, không phải model ML.
360 tin mẫu năm 2024 không đại diện đủ sáu năm giao dịch.
19 DIRECT là số được luật xếp loại, không phải độ chính xác được kiểm chứng.

Hiển thị tin cùng danh mục và thời gian để tham khảo. Không gán quan hệ nhân quả
với doanh số mô phỏng. Tháng chưa thu thập đủ là thiếu độ phủ, không mặc định 0 tin.
Tổng số bài dùng DISTINCT article_key khi ghép bridge; chỉ ghép tổng hợp
doanh số và tổng hợp tin cùng mức để tránh nhân tiền hàng.

## Thông tin cá nhân và nguồn gốc

Chỉ giữ mã khách cho phân tích; bỏ tên, điện thoại, địa chỉ chi tiết và tên tài xế
khỏi đầu ra công khai, features và bằng chứng. Không xác nhận các tên trong Excel
là người thật hoặc giả chỉ dựa trên mẫu. Giữ bản gốc để đối chiếu trong phạm vi
được cung cấp, xử lý bản dữ liệu dùng nộp theo yêu cầu ẩn danh trước release.

Thông tin cần người dùng bổ sung: người tạo/nguồn tải Excel, điều kiện sử dụng,
mã sinh dữ liệu nếu có, định nghĩa các mốc thời gian. Chưa có tài liệu này không
được tự điền một giấy phép hoặc khẳng định dataset thật của doanh nghiệp.
