# Đánh giá dữ liệu LAK giai đoạn 1

## Kết luận phục vụ triển khai

Dữ liệu đủ để tiếp tục thiết kế kho, RFM/K-Means và thử nghiệm Random Forest
giao hàng trong môi trường mô phỏng. Không có lỗi khóa hay công thức tiền ở
bộ đã kiểm tra. Có bất nhất thời gian, hạn chế nguồn gốc và độ phủ tin cần
được ghi nhận rõ. Chưa có kết quả train hay đánh giá mô hình.

Script: `scripts/profile_lak_data.py`. Bằng chứng chạy tại môi trường trợ lý:
`evidence/phase1/assistant-final/profile.json`. Đây là kết quả dữ liệu, không phải
kiểm thử Docker/CDC hoặc xác nhận đã chạy trên Windows của sinh viên.

## Quy mô và tính đầy đủ

| Nguồn | Số dòng | Cột | Khóa |
| --- | ---: | ---: | --- |
| Đơn hàng | 10000 | 9 | Ma_Don |
| Khách hàng | 3282 | 10 | Ma_Khach_Hang |
| Sản phẩm | 15 | 8 | Ma_San_Pham |
| Thời gian giao nhận | 10000 | 10 | Ma_Don |
| Thanh toán | 10000 | 7 | Ma_Don |
| Vận chuyển | 10000 | 7 | Ma_Don |
| Tin mẫu | 360 | 10 | article_key theo quy tắc pipeline |

Không thiếu giá trị ở các cột hiện có của sáu Excel; tỷ lệ thiếu từng cột và
số giá trị phân biệt ở `docs/data_dictionary.md` và profile.json. Không có
khóa trùng, dòng trùng hoàn toàn hoặc tham chiếu khách/sản phẩm bị thiếu.
Tập mã đơn giữa bảng 01, 04, 05, 06 trùng khớp.

Tính đầy đủ theo cột hiện có không có nghĩa đầy đủ nghiệp vụ: thiếu ngày đặt,
ngày thanh toán, trạng thái hủy/hoàn, dòng giỏ hàng và lần giao độc lập.
Không tự coi thiếu cột nghiệp vụ là tỷ lệ NULL bằng 0.

## Đối soát tiền

| Chỉ tiêu | Tổng VND |
| --- | ---: |
| Tiền hàng | 618293800000 |
| VAT | 61829380000 |
| Vận chuyển | 1138180904 |
| Tổng thanh toán | 681261360904 |

Công thức tiền từng đơn, số lượng giữa hai bảng và đơn giá hiện tại giữa danh
mục/thanh toán khớp. Số đơn/tổng thanh toán theo khách khớp bảng 02.
Số đơn/số lượng/tiền hàng theo sản phẩm khớp bảng 03. Các tổng có sẵn chỉ dùng
đối soát; không dùng làm đặc trưng cho một thời điểm quá khứ.

## Chất lượng thời gian và địa bàn

| Quan sát | Số đơn | Cách xử lý đã chọn |
| --- | ---: | --- |
| Giao đi trước đóng gói khi ghép cả giờ | 880 | Gắn cờ, không sửa raw; không dùng packed_at trong RF ban đầu |
| Dự kiến tới trước giao đi khi ghép cả giờ | 118 | Gắn cờ, không dùng expected_at làm feature/SLA chính |
| Nhận trước giao đi | 0 | Nhãn số giờ vận chuyển không âm trong bộ hiện có |
| Nhận sau dự kiến nếu tính cả giờ | 5170 | Quan sát chưa có SLA xác nhận |
| Nhận sau dự kiến nếu chỉ tính ngày | 1987 | Khác định nghĩa với dòng trên, không trộn hai phép đo |
| Địa chỉ theo đơn khác hồ sơ khách | 6070 | Giữ địa chỉ đơn; khác nhau chưa chứng minh lỗi |

Các nhóm cảnh báo có thể giao nhau. Không cộng chúng để báo tổng số đơn lỗi.
Số lượng cảnh báo không tự quyết định loại giao dịch khỏi tổng tiền.
Chỉ có TP Hồ Chí Minh trong nguồn; phân tích địa lý chi tiết theo quận/huyện.

## Khả năng khai phá

RFM: 3282 khách; 1307 khách mua một lần toàn lịch sử. Năm 2025 có 1159 khách
hoạt động, trong đó 852 khách chỉ một đơn. Cửa sổ ban đầu lấy toàn lịch sử;
phải xem độ ổn định và ý nghĩa cụm thay vì chỉ báo điểm hình học.

Random Forest: đủ 10000 cặp giao đi/nhận để dựng nhãn giờ giao. Nếu tính ngày
lịch, giao nhanh 1–3 ngày, bình thường 4–5 ngày, chậm 6–10 ngày. Phân bố này
gợi ý loại giao là biến mạnh và dữ liệu có quy luật mô phỏng. Cần baseline
trung vị theo loại giao và chia tập theo thời gian trước khi kết luận giá trị.

Thời điểm dự đoán, feature được phép dùng, cửa sổ RFM và điều kiện nhãn sẵn có
được ghi ở `docs/business_definitions.md`. Giai đoạn 1 chưa huấn luyện hay
chọn tham số trên test, chưa có MAE/RMSE/Silhouette để báo cáo.

## Tin tức và nguồn gốc

360 tin hợp lệ theo bộ đọc, 360 article_key khác nhau. Ngày đăng từ 2024-01-04
đến 2024-12-31. Luật hiện tại gán 19 DIRECT, 6 INDIRECT, 335 IRRELEVANT.
Đây không phải phép đo accuracy. Chưa có mẫu người gán nhãn hoặc API live
được kiểm chứng trong lượt này. Độ phủ tin sáu năm chưa đạt.

API source ghi bán hàng mô phỏng; chưa có tài liệu nguồn/giấy phép hay mã sinh
Excel để xác nhận độc lập. Không tự gán giấy phép và không khẳng định dữ liệu
doanh nghiệp thật. Chưa xác nhận tên/địa chỉ trong nguồn là dữ liệu giả hoàn toàn.
Không đưa những giá trị này vào profile hoặc feature; trước bản nộp cần xử lý
bộ dữ liệu chia sẻ theo yêu cầu ẩn danh.

## Trạng thái giai đoạn

Đã có script chạy lại được, từ điển và định nghĩa nghiệp vụ. Cần sinh viên chạy
trên Windows để xác nhận cùng nguồn. Nguồn gốc/quyền sử dụng và ý nghĩa gốc
ngày giờ vẫn là thông tin cần bổ sung, không ghi là đã xác minh.
Tiếp theo là thiết kế mô hình kho, chưa tự ý triển khai giai đoạn 2 trong gói này.
