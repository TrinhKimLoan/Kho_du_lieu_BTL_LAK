# Từ điển dữ liệu LAK

Sinh từ sáu Excel nguồn. Không đưa giá trị tên, điện thoại hoặc địa chỉ vào tài liệu.

Ngày trong XLSX lưu bằng serial; giờ lưu bằng phần thập phân của một ngày.
Script ghép ngày và giờ, làm tròn đến giây. Tiền tính bằng Decimal, đơn vị VND.

## 01_don_hang.xlsx

Số dòng: 10000. Khóa: `Ma_Don`.

| Cột | Ý nghĩa | Thiếu | Tỷ lệ thiếu | Số giá trị khác nhau |
| --- | --- | ---: | ---: | ---: |
| Ma_Don | Mã đơn, khóa nghiệp vụ; mỗi đơn hiện có một sản phẩm | 0 | 0.0% | 10000 |
| Ma_Khach_Hang | Mã khách, dùng ghép lịch sử mua; không dùng như đặc trưng số | 0 | 0.0% | 3282 |
| Ma_San_Pham | Mã sản phẩm, dùng ghép danh mục | 0 | 0.0% | 15 |
| Loai_Giao_Hang | Loại dịch vụ giao: nhanh, bình thường hoặc chậm | 0 | 0.0% | 3 |
| So_Luong | Số đơn vị sản phẩm trong đơn | 0 | 0.0% | 20 |
| Muc_Hang_Hoa | Nhóm ít/vừa/nhiều; cần phân biệt phân nhóm theo đơn và sản phẩm | 0 | 0.0% | 3 |
| Kho_Xuat | Kho xuất của đơn | 0 | 0.0% | 5 |
| Xe_Van_Chuyen | Loại phương tiện giao | 0 | 0.0% | 3 |
| Tai_Xe | Tên tài xế trong nguồn; không đưa tên vào dashboard/bản nộp | 0 | 0.0% | 10 |

## 02_thong_tin_khach_hang.xlsx

Số dòng: 3282. Khóa: `Ma_Khach_Hang`.

| Cột | Ý nghĩa | Thiếu | Tỷ lệ thiếu | Số giá trị khác nhau |
| --- | --- | ---: | ---: | ---: |
| Ma_Khach_Hang | Mã khách, dùng ghép lịch sử mua; không dùng như đặc trưng số | 0 | 0.0% | 3282 |
| Ten_Khach_Hang | Tên khách trong nguồn; loại khỏi tập phân tích công khai | 0 | 0.0% | 1300 |
| Gioi_Tinh | Giới tính ghi trong nguồn; không cần cho RFM | 0 | 0.0% | 2 |
| SDT | Số điện thoại; không đưa vào đặc trưng hoặc đầu ra phân tích | 0 | 0.0% | 3282 |
| Dia_Chi_Giao | Địa chỉ theo khách hoặc theo đơn; không đồng nhất hai vai trò | 0 | 0.0% | 10 |
| Tinh_Thanh | Địa bàn cấp tỉnh/thành theo bảng nguồn; hiện chỉ có TP Hồ Chí Minh | 0 | 0.0% | 1 |
| Quan_Huyen | Địa bàn chi tiết theo nguồn; giữ nguyên nhãn lịch sử | 0 | 0.0% | 8 |
| So_Lan_Mua_Goc | Số lần mua tổng hợp sẵn; không dùng cho snapshot quá khứ | 0 | 0.0% | 20 |
| So_Don_Hang | Số đơn tổng hợp toàn bộ nguồn; chỉ dùng đối soát | 0 | 0.0% | 20 |
| Tong_Chi_Tieu | Tổng thanh toán cả lịch sử theo khách, gồm VAT/phí; chỉ đối soát | 0 | 0.0% | 3282 |

## 03_linh_kien_dien_tu_san_pham.xlsx

Số dòng: 15. Khóa: `Ma_San_Pham`.

| Cột | Ý nghĩa | Thiếu | Tỷ lệ thiếu | Số giá trị khác nhau |
| --- | --- | ---: | ---: | ---: |
| Ma_San_Pham | Mã sản phẩm, dùng ghép danh mục | 0 | 0.0% | 15 |
| Loai_Hang | Nhóm hàng rộng trong nguồn; hiện chỉ có Linh kiện điện tử | 0 | 0.0% | 1 |
| Ten_Hang_Hoa | Tên sản phẩm trong danh mục hiện có | 0 | 0.0% | 15 |
| Muc_Hang_Hoa | Nhóm ít/vừa/nhiều; cần phân biệt phân nhóm theo đơn và sản phẩm | 0 | 0.0% | 3 |
| Don_Gia_San_Pham | Đơn giá VND; lấy giá ở bảng thanh toán làm giá của giao dịch | 0 | 0.0% | 15 |
| So_Don_Co_San_Pham | Số đơn tổng hợp theo sản phẩm; chỉ đối soát | 0 | 0.0% | 15 |
| Tong_So_Luong_Ban | Số lượng tổng hợp theo sản phẩm; chỉ đối soát | 0 | 0.0% | 15 |
| Tong_Doanh_Thu_Hang | Tiền hàng tổng hợp theo sản phẩm, chưa VAT/phí | 0 | 0.0% | 15 |

## 04_thoi_gian_giao_hang.xlsx

Số dòng: 10000. Khóa: `Ma_Don`.

| Cột | Ý nghĩa | Thiếu | Tỷ lệ thiếu | Số giá trị khác nhau |
| --- | --- | ---: | ---: | ---: |
| Ma_Don | Mã đơn, khóa nghiệp vụ; mỗi đơn hiện có một sản phẩm | 0 | 0.0% | 10000 |
| Loai_Giao_Hang | Loại dịch vụ giao: nhanh, bình thường hoặc chậm | 0 | 0.0% | 3 |
| Thoi_Gian_Dong_Goi | Ngày đóng gói, không có bằng chứng đây là ngày đặt hàng | 0 | 0.0% | 2153 |
| Gio_Dong_Goi | Giờ đóng gói, ghép với ngày đóng gói | 0 | 0.0% | 8742 |
| Thoi_Gian_Giao_Hang | Ngày giao đi theo cách diễn giải vận hành được chọn | 0 | 0.0% | 2145 |
| Gio_Giao_Hang | Giờ giao đi, ghép với ngày giao đi | 0 | 0.0% | 8982 |
| Thoi_Gian_Du_Kien_Toi | Ngày dự kiến tới; chưa xác nhận là SLA cam kết | 0 | 0.0% | 2167 |
| Gio_Du_Kien_Toi | Giờ dự kiến tới; có bản ghi không hợp lý, chưa làm KPI SLA | 0 | 0.0% | 9106 |
| Thoi_Gian_Nhan_Hang | Ngày nhận thực tế | 0 | 0.0% | 2165 |
| Gio_Nhan_Hang | Giờ nhận thực tế | 0 | 0.0% | 9152 |

## 05_chi_phi_thanh_toan.xlsx

Số dòng: 10000. Khóa: `Ma_Don`.

| Cột | Ý nghĩa | Thiếu | Tỷ lệ thiếu | Số giá trị khác nhau |
| --- | --- | ---: | ---: | ---: |
| Ma_Don | Mã đơn, khóa nghiệp vụ; mỗi đơn hiện có một sản phẩm | 0 | 0.0% | 10000 |
| So_Luong | Số đơn vị sản phẩm trong đơn | 0 | 0.0% | 20 |
| Don_Gia_San_Pham | Đơn giá VND; lấy giá ở bảng thanh toán làm giá của giao dịch | 0 | 0.0% | 15 |
| Tong_Gia_Tri_Hang | Tiền hàng VND, bằng số lượng nhân đơn giá | 0 | 0.0% | 250 |
| VAT_10 | VAT VND, quy tắc bộ dữ liệu bằng 10 phần trăm tiền hàng | 0 | 0.0% | 250 |
| Phi_Van_Chuyen | Phí vận chuyển VND theo đơn | 0 | 0.0% | 9729 |
| Tong_Thanh_Toan | Tổng tiền hàng cộng VAT cộng vận chuyển, không phải lợi nhuận | 0 | 0.0% | 9995 |

## 06_van_chuyen_kho_tai_xe.xlsx

Số dòng: 10000. Khóa: `Ma_Don`.

| Cột | Ý nghĩa | Thiếu | Tỷ lệ thiếu | Số giá trị khác nhau |
| --- | --- | ---: | ---: | ---: |
| Ma_Don | Mã đơn, khóa nghiệp vụ; mỗi đơn hiện có một sản phẩm | 0 | 0.0% | 10000 |
| Kho_Xuat | Kho xuất của đơn | 0 | 0.0% | 5 |
| Xe_Van_Chuyen | Loại phương tiện giao | 0 | 0.0% | 3 |
| Tai_Xe | Tên tài xế trong nguồn; không đưa tên vào dashboard/bản nộp | 0 | 0.0% | 10 |
| Tinh_Thanh | Địa bàn cấp tỉnh/thành theo bảng nguồn; hiện chỉ có TP Hồ Chí Minh | 0 | 0.0% | 1 |
| Quan_Huyen | Địa bàn chi tiết theo nguồn; giữ nguyên nhãn lịch sử | 0 | 0.0% | 8 |
| Dia_Chi_Giao | Địa chỉ theo khách hoặc theo đơn; không đồng nhất hai vai trò | 0 | 0.0% | 10 |

