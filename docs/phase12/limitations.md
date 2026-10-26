# Giới hạn và sự cố đã khắc phục

1. 998 cảnh báo chất lượng nguồn được giữ và công bố; 0 phát hiện ERROR. Không sửa âm thầm timestamp, không tuyên bố sạch mọi bất thường dữ liệu.
2. Dữ liệu LAK phục vụ học tập; RF cải thiện MAE rất nhỏ so baseline vận chuyển. KMeans mô tả snapshot; chưa xác minh hành vi tương lai.
3. 60 thao tác tuần tự, mỗi loại n=20; không kiểm thử concurrent load/capacity, không suy diễn SLA. Polling tạo độ trễ quan sát; ML được quan sát sau DW có thể đã sẵn sàng trước đó.
4. Không đo browser rendering hoặc độ trễ lịch mart định kỳ 15 phút. AppTest thực thi trang và truy vấn, không phải browser visual review. Người dùng chấp nhận giao diện trong hội thoại.
5. Benchmark 6 query, 10 lần/query/nguồn, cache ấm; mart chưa chứng minh tăng tốc rõ rệt. Không có suy luận ý nghĩa thống kê.
6. Recovery chỉ ba worker nghiệp vụ có stop/restart có kiểm soát; không kiểm thử mất điện, mất broker/DB, hỏng volume hay failover. Retry fixture chỉ vòng đời CSDL, không poison-event process recovery.
7. Fixture tái phân bổ mart kiểm tra PostgreSQL projection→mart và rollback, không phải sửa MySQL xuyên CDC. Chuỗi nguồn→CDC→DW→ML và web được kiểm tra bằng các lượt bổ sung, không phải một browser transaction xuyên mọi tầng.
8. CPU/RAM là mẫu Docker, không phải peak tuyệt đối hay sử dụng toàn máy. Disk GLOBAL có tài nguyên ngoài LAK; schema/database bytes không phải dung lượng file VHD vật lý.
9. Lần đo `measure-20261026T081418Z-63e11e77` thất bại import src trước khi tạo demo. Đã thêm PYTHONPATH=/opt/project và chạy cửa sổ mới `measure-20261026T082221Z-b0e86798`; giữ cả log thất bại, không dùng nó làm kết quả đạt.
10. Recovery ban đầu gặp lỗi quoting `utf`; đã chuyển Python qua stdin và tiếp tục, không reset volume. Lỗi cold import Streamlit được sửa ở Phase 11 Fix 2, kiểm tra cold import Phase 12 đạt. Cảnh báo ScriptRunContext bare-mode không làm AppTest thất bại.
11. Đóng gói và dựng lại sạch chưa thực hiện; thuộc Phase 13. Không yêu cầu thay thuật toán, công nghệ hoặc giao diện để hoàn thành Phase 12.

Việc sử dụng AI: trợ lý hỗ trợ mã, lệnh, thiết kế kiểm thử, phân tích bằng chứng và soạn báo cáo; người dùng chạy lệnh Docker trên máy Windows và gửi kết quả thực tế. Không tạo số đo mô phỏng thay bằng chứng.
