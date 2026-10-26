# Báo cáo đối soát Phase 12

## Nguồn → CDC → DW

Nguồn và staging đối soát 3.282 khách hàng, 15 sản phẩm, 10.000 đơn; 43.297 dòng provenance. Snapshot không còn sự kiện chờ. Digest từng bảng nguồn/staging khớp; hash trạng thái fact trước/sau kiểm thử:

`8a86593176d87fad40a4a116038aeba8bd2199c85b9e0a0bcab2f5a292b543ea`

| Đại lượng | VND |
|---|---:|
| Tiền hàng | 618293800000.00 |
| VAT | 61829380000.00 |
| Vận chuyển | 1138180904.00 |
| Tổng thanh toán | 681261360904.00 |

Replay Kafka không thêm tọa độ raw mới; replay projection giữ nguyên lịch sử fact và phiên bản sản phẩm. Thêm/sửa/xóa được kiểm chứng ở recovery, ML và 60 thao tác đo mới.

## Chất lượng và SCD2

0 phát hiện mức ERROR; **998 phát hiện WARNING**: DISPATCH_BEFORE_PACK=880, EXPECTED_BEFORE_DISPATCH=118. Đây là số phát hiện theo quy tắc, không khẳng định 998 đơn riêng biệt. Giữ nguyên dấu thời gian nguồn, không âm thầm sửa hoặc loại khỏi doanh số; không công bố tỷ lệ trễ SLA khi SLA chưa xác minh.

SCD2 sản phẩm tạo hai phiên bản liền kề; đơn cũ giữ phiên bản/category cũ, đơn mới nhận phiên bản/category hiện hành. Địa bàn hồ sơ khách hàng cập nhật Type 1 giữ khóa; giá catalog không tạo phiên bản. Dữ liệu demo nguồn đã dọn, lịch sử kinh doanh không đổi.

Các fixture kiểm tra ràng buộc overlap/second-current, tiền, FK, vai trò ngày và retry đều đạt và rollback. Retry là kiểm tra vòng đời CSDL; không phải kiểm thử poison event sau crash tiến trình.

## DW → mart/cube

10.000 fact bán hàng, 2.145 fact tin tức; cube grand total khớp, liên kết chéo hai fact không nhân doanh số. Fixture thay tiền/ngày/sản phẩm/địa bàn, refresh và soft-delete đều đạt; thay đổi thử nghiệm rollback. Phạm vi fixture là PostgreSQL projection → mart, không phải một lượt sửa MySQL → CDC mới.

Sáu nhóm truy vấn fact/mart có cùng đầu ra ở mỗi lần đo.

## ML → web

KMeans `km-rfm-6ea5a87000cce054c9fa28c9`: 3.282 khách hàng; kiểm tra checksum, tiền xử lý chỉ fit train, chọn cấu hình không dùng test và tái lập dự đoán đạt. Đây là phân cụm snapshot, không xác nhận dự báo hành vi tương lai.

Random Forest `rf-delivery-4a60b2b333abc46ef35bb5f6`: 1.599 mẫu test; kiểm tra temporal holdout/label availability, train-only preprocessing, checksum và tái lập dự đoán đạt. Test MAE 18,7329166932 giờ; baseline theo phương thức vận chuyển 18,8346183379 giờ. Cải thiện chỉ khoảng 0,102 giờ (6,1 phút), không suy diễn hiệu quả thực tế.

Dashboard: cold import và 8 trang thực thi thành công bằng Streamlit AppTest với kho thật; tổng quan khớp OLAP, fact hiện hành khớp mart; connector/task RUNNING. Không có mutation demo trong lượt AppTest. Kiểm tra này không đo render trình duyệt; người dùng đã xác nhận mở web và chấp nhận giao diện hiện tại.

Bằng chứng: các thư mục `quality-replay-*`, `integration-*`, `ml-web-*` dưới `evidence/phase12/` trong bản lưu, và recovery ML Phase 10.
