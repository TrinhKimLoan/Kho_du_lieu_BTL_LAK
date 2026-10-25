# Pha 3 bản vá đối soát JSON truy vết

Người dùng xác nhận Fix1 và ba test đạt; MySQL install vẫn READY với cùng
source_epoch. Lần nạp tiếp theo rollback vì Provenance payload/fingerprint mismatch.
Thông báo cũ chưa chỉ rõ file/cột, nên chưa có bằng chứng xác định một dòng
cụ thể hoặc phép biến đổi số nào trong MySQL gây sai khác.

Bản vá loại bỏ phụ thuộc vào cách MySQL JSON đọc/ghi số floating-point của
Excel: các float trong sanitized_payload được mã hóa thành object có tag
__lak_type__=excel_float_repr và value=repr(float) dạng chuỗi. Số nguyên giữ
nguyên. Có thể phục hồi giá trị float bằng float(value); không làm tròn hoặc
dùng epsilon để bỏ qua sai khác. SHA file và dòng Excel vẫn là dấu vết nguồn.
Encoding được ghi nhận bằng redaction_version lak-minimal-v2-float-repr.

Thay đổi chỉ ở provenance. Giá trị tiền Decimal, timestamp giao dịch, số đơn,
checksum schema, source_epoch và mật khẩu không đổi. Không migrate DDL hoặc
xóa volume. Lần nạp lỗi trước nằm trong transaction và có rollback.

Validator tiếp tục kiểm tra cả payload đọc lại, hash đã lưu, hash từ đầu vào và
entity/version. Nếu còn lỗi, báo file, số dòng Excel, loại sai lệch và tên cột;
không in giá trị tên, điện thoại hoặc địa chỉ vào log. Không bỏ phép đối soát.

Thêm năm test cho round-trip encoding, biến đổi định dạng JSON, sai một chữ
số, sửa stored hash và số không hữu hạn. Test Python không thay thế MySQL thật.
Sau cập nhật, chạy tests test_phase3*.py rồi runner pha 3 để build lại tools,
nạp hai lần, thử constraint và demo với nguồn hiện có. Chưa sang pha 4.
