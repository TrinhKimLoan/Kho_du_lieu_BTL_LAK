# Chuẩn bị demo và bảo vệ — bản đầu

## Dàn ý trình bày

1. Bài toán LAK, dữ liệu nguồn học tập và hai fact bán hàng/tin tức.
2. Kiến trúc MySQL → Debezium/Kafka → collector/raw → applier/PostgreSQL → mart/cube → ML → Streamlit; Airflow lập lịch.
3. Grain fact, khóa surrogate, các vai trò ngày; SCD2 sản phẩm và Type 1 hồ sơ khách hàng.
4. Idempotence qua tọa độ CDC, tombstone/soft-delete và recovery worker.
5. KMeans/RFM và Random Forest: đặc trưng, split, baseline và chống leakage.
6. Website 8 trang, nguồn số liệu và snapshot mart.
7. Kết quả Phase 12: 60 thao tác, 6 query tương đương, 30 mẫu tài nguyên; công bố cả cảnh báo và giới hạn.
8. Release và dựng lại: cập nhật slide sau khi Stage B có bằng chứng; hiện chưa được nói “dựng lại sạch thành công”.

## Kịch bản demo dự kiến

- Mở tổng quan, lọc thời gian và đối chiếu trang OLAP.
- Xem phân khúc khách hàng, giải thích nhãn mô tả và quy mô từng nhóm.
- Xem đánh giá giao hàng: MAE giờ, baseline, giới hạn cải thiện nhỏ.
- Xem tin tức lưu sẵn, nhãn thời gian/nguồn và mức liên quan; không nói đang fetch live nếu chưa gọi API.
- Tại trang demo, dùng riêng mã demo; thêm → sửa → xóa, quan sát trạng thái xử lý và lịch sử dự đoán. Không sửa đơn lịch sử để minh họa.
- Xem trang vận hành: connector/task, worker, snapshot và lỗi.
- Trình bày bằng chứng recovery/replay đã lưu; nếu dừng worker trực tiếp cần kịch bản và thời gian chờ riêng.

## Câu hỏi bảo vệ

| Câu hỏi | Ý chính trả lời |
|---|---|
| Vì sao không join hai fact trực tiếp theo ngày? | Hai grain khác nhau gây nhân dòng; tổng hợp/bridge có kiểm soát trước khi kết hợp và đối soát grand total. |
| SCD2 giữ lịch sử thế nào? | Mỗi phiên bản có khóa và khoảng hiệu lực; đơn cũ giữ product_key/category cũ, đơn mới dùng phiên bản hiện hành. |
| Replay có tạo đơn trùng không? | Tọa độ raw và quy tắc projection idempotent; Phase 12 xác minh không thêm raw coordinate và không đổi fact/product versions. |
| Worker tắt có mất dữ liệu không? | Đã thử tắt từng worker nghiệp vụ, ghi nguồn khi dừng, bật lại và xử lý bù; không suy diễn thành bảo đảm mọi dạng sự cố. |
| Làm sao tránh leakage? | Preprocessing/baseline chỉ fit train, chọn cấu hình trên validation; RF kiểm tra temporal split và thời điểm label sẵn có. |
| KMeans có dự báo khách hàng tương lai không? | Không; phân cụm mô tả snapshot RFM. Chưa kiểm chứng hành vi tương lai. |
| RF tốt hơn baseline bao nhiêu? | Test MAE 18,733 so với 18,835 giờ, chỉ hơn khoảng 6,1 phút; không phóng đại hiệu quả. |
| Mart có nhanh hơn fact không? | 6 query cùng đầu ra; chênh lệch nhỏ, query product chậm hơn; chưa chứng minh tăng tốc rõ rệt. |
| Dữ liệu có sạch không? | 0 ERROR nhưng 998 WARNING theo quy tắc timestamp; giữ và công bố, không âm thầm sửa nguồn. |
| Độ trễ khoảng 2 giây có phải SLA không? | Không; 20 mẫu mỗi thao tác, tuần tự, polling 0,1 giây, chưa đo tải đồng thời/browser/lịch mart. |
| Checksum có chứng minh dựng lại không? | Chỉ chứng minh tính nguyên vẹn; phải có byte image/dữ liệu, cấu hình mới và bằng chứng dựng lại riêng. |

## Ghi nhận AI

Trợ lý hỗ trợ thiết kế, mã/lệnh, kiểm thử, phân tích log và tài liệu. Người dùng thực chạy Docker trên Windows, gửi bằng chứng và chấp nhận giao diện. Các kết quả runtime là từ bằng chứng thực; không dùng số liệu giả. Nhóm cần tự hiểu và giải thích các quyết định khi bảo vệ.
