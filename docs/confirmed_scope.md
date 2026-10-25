# Phạm vi được xác nhận

Ngày xác nhận: 2026-10-25.

Nguồn quyết định: người dùng cho biết giảng viên yêu cầu tối thiểu hai thuật toán
và phần tin tức tại buổi demo. Yêu cầu trực tiếp này bổ sung hướng dẫn chung
trong slide Bài 12, không phải lý do để thu gọn dự án xuống một mô hình.

Thực hiện nguyên bản kế hoạch `upgrade_plan.md`, giai đoạn 0 đến 13:
giữ LAK làm nghiệp vụ và dữ liệu chính; CommerceInsight chỉ cung cấp kinh nghiệm
và thành phần kỹ thuật tương thích. Giữ hai mô hình K-Means và Random Forest.
Nếu kiểm tra dữ liệu phát hiện vấn đề thực sự cản trở dự đoán giao hàng, phải
nêu bằng chứng và giải pháp trước khi sửa thiết kế, theo đúng giai đoạn 1.
Không tự thay thuật toán hay sinh nhãn mới để đạt số lượng.

Không làm phân công nhóm. Chỉ có một sinh viên thực hiện với trợ giúp của AI.
Không dựng bằng chứng làm việc nhóm. Báo cáo và slide thực hiện sau sản phẩm.

Không sửa hay xóa hai dự án gốc. Bản mới ở thư mục riêng `LAK-Analytics`.
Không coi bản nâng cấp đã chạy vì chỉ đọc source hoặc test đơn vị thành công.
Không dùng kết quả hay model Online Retail II để đại diện cho dữ liệu LAK.

Mỗi giai đoạn: giải thích mục đích và đầu ra bằng tiếng Việt, triển khai đúng phạm vi,
kiểm tra thực tế, lưu bằng chứng và commit; không chạy một loạt giai đoạn khi
sinh viên chưa chạy hoặc chưa hiểu giai đoạn trước.

Chưa xác minh dung lượng RAM máy Windows trong lượt này. Con số khoảng 16 GB
trong kế hoạch là giả định cần kiểm tra trước khi quyết định profile hạ tầng.

CommerceInsight đã dựng sạch thành công sau phục hồi thủ công. Không mô tả
bootstrap của bản đó là tự phục hồi hoàn toàn.
