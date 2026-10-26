# Phase 11 Fix 1 — hồ sơ cụm có cluster_id trong JSON

Lỗi người dùng ghi nhận: evidence/phase11/run-20261026T071158Z-17b7e3d0. Kiểm thử với DB thật dừng ở trang customers: dict() got multiple values for keyword argument 'cluster_id'.

ml.segment_profiles có cluster_id ở cột quan hệ và trong profile JSON do Phase 8 đã lưu. Giao diện cũ gọi dict(cluster_id=..., **profile), khiến Python báo trùng keyword. Fixture ban đầu đã thiếu cluster_id bên trong JSON nên không phát hiện được lỗi này.

Sửa thành dictionary unpacking rồi gán rõ cluster_id/display_name từ cột quan hệ. Không đổi schema, dữ liệu, thuật toán, model hoặc logic suy luận. Không cần nạp lại lịch sử hoặc train lại.

Fixture cập nhật đủ cấu trúc Phase 8 (cluster_id/name/customers/share/median R-F-M/tổng M/split counts). Bổ sung kiểm thử hồi quy trang customers và bảng hồ sơ. Trước sửa, fixture mới làm 2 kiểm thử giao diện thất bại đúng nguyên nhân; sau sửa chạy đạt 15 test Phase 11 và 130 test toàn bộ.

Áp dụng Fix 1 lên G:\LAK-Analytics hiện tại bằng apply_update.py, rồi chạy lại scripts/run_phase11.ps1. Script tự dựng lại image với mã mới và tạo thư mục bằng chứng mới. PostgreSQL/Streamlit/Docker thực tế vẫn cần chạy lại trên máy người dùng. Không xóa orphan container Airflow/inference-worker; chúng không phải nguyên nhân lỗi.
