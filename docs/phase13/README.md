# Phase 13 — Đóng gói, dựng lại và chuẩn bị bảo vệ

## Trạng thái

**Đã kiểm chứng dựng lại môi trường riêng; chờ chạy lệnh tạo release cuối trên máy người dùng.** Xem [bàn giao cuối](final/README.md), [báo cáo tổng kết](final/project-report.md) và `final/release.json`. Bằng chứng đã bao gồm restore CSDL/mô hình, bootstrap CDC, inference, 8 trang web và scheduler; phạm vi cùng Docker engine với volume/network/credential riêng. Các trạng thái pending của Stage A được giữ trong JSON gốc để truy vết.

Đầu vào: Phase 12 đã được người dùng áp dụng và xác minh tại commit `2534fc1abb2a17eb8b2da29d9e22a32117d07c79`. Inventory máy người dùng ngày 26/10/2026 lúc 16:14:25 UTC+7: 13 image linux/amd64, 9 môi trường Python, 19 tệp mô hình (11.547.443 byte). Những commit trợ lý tạo ở môi trường soạn mã có thể mang hash khác; installer so sánh nội dung, không giả định hash HEAD hai máy giống nhau.

## Tài liệu

- [Vận hành](operations.md): khởi động, dừng giữ volume, trạng thái, log.
- [Đóng gói và dựng lại](release-guide.md): ứng viên và điều kiện để trở thành release cuối.
- [Bản đồ thư mục](directory-map.md).
- [Kịch bản demo và câu hỏi bảo vệ](defense.md).
- `inventory/`: bản gốc người dùng cung cấp, giữ nguyên byte.
- `infra/locks/`: image ID/digest quan sát, khóa package riêng từng môi trường và checksum mô hình.

Các giai đoạn cũ không bị đổi thuật toán, công nghệ hoặc nghiệp vụ. Không thay credential đang chạy, không reset volume, không retrain. Các script Phase 3–11 phục vụ triển khai/kiểm thử từng pha có thể build image; lệnh vận hành thông thường ở tài liệu này không build hay pull ngầm.
