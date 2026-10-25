# Pha 3 tạo MySQL nguồn và nạp lịch sử

## Mục đích

Chuyển sáu Excel thành nguồn giao dịch mô phỏng có thể thêm/sửa/xóa để CDC
theo dõi ở pha 4. Pha này chưa chạy Debezium, Kafka hoặc ghi fact vào PostgreSQL.
Giữ hai mô hình và tin tức trong kế hoạch; chưa triển khai ở pha này.
Chỉ có một thư mục làm việc: `G:\LAK-Analytics`. Không tạo lại dự án và không
chép Git từ gói khác. Gói cập nhật chỉ mang phần thay đổi từ pha 2.

## Tải và áp dụng

Lưu `LAK-Analytics-Phase3-Patch.zip` trực tiếp tại `G:\`, rồi chạy:

```powershell
Set-Location G:\
Expand-Archive -LiteralPath 'G:\LAK-Analytics-Phase3-Patch.zip' -DestinationPath 'G:\LAK-Phase3-Patch' -Force
python 'G:\LAK-Phase3-Patch\apply_update.py' --target 'G:\LAK-Analytics'
```

Chỉ tiếp tục khi có `PHASE 3 PATCH APPLIED` hoặc `PHASE 3 PATCH ALREADY APPLIED`.
Nếu UPDATE STOPPED, gửi nguyên thông báo; không bỏ qua guard. Installer kiểm
tra mốc pha 2 và SHA256, sao lưu tệp thay đổi trong `.runtime/updates`, áp dụng
patch và commit đúng các tệp thuộc gói. Nó không thay `.git`, Excel, `.env`,
mật khẩu runtime hoặc bằng chứng người dùng đã chạy. Hash commit mới trên
máy em có thể khác môi trường trợ lý; nội dung được kiểm tra bằng SHA256.

## Kiểm thử

```powershell
Set-Location G:\LAK-Analytics
python -m unittest discover -s tests -p test_phase3_source.py -v
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_phase3.ps1
```

Python 3.11 trở lên; test offline không cần cài thêm thư viện. Mở Docker
Desktop ở chế độ Linux containers. Lần đầu có thể tải image và build tools.
PyMySQL chạy bên trong container, không cài vào Python máy em.

Runner tự tạo mật khẩu ở `.runtime/lak.env` nếu chưa có và giữ lại cho các
lần sau. Không in mật khẩu vào bằng chứng. Không xóa tệp này khi volume
MySQL còn tồn tại, không gửi nó trong chat/bản nộp. Không đổi `.env` cũ.

Docker project `lak-analytics`; MySQL cổng host 3310 bind 127.0.0.1.
Volume riêng `lak-analytics_mysql_source_data`, không dùng volume cũ. Nếu
cổng bận hoặc Docker lỗi, gửi log; không xóa hay dừng dịch vụ khác để ép chạy.
MySQL được giữ sau kiểm thử để tiếp tục pha 4, khác container tạm pha 2.

## Kết quả mong đợi

- Sáu test Python đạt.
- 3282 khách, 15 sản phẩm, 10000 đơn lịch sử trong MySQL.
- 43297 dòng truy vết sáu Excel; một đơn có bốn dòng theo bốn tệp.
- Tiền hàng 618293800000.00 VND; tổng thanh toán 681261360904.00 VND.
- Nạp lần hai không đổi dữ liệu hoặc updated_at của lịch sử.
- MySQL từ chối sai tổng tiền, số lượng âm, thiếu khách và cờ demo sai namespace.
- Demo INSERT/UPDATE/DELETE có commit tại nguồn, sau cùng không còn đơn của
  lượt demo-cycle và lịch sử không thay đổi.
- Dòng `PHASE 3 SOURCE CHECKS PASSED` cùng đường dẫn bằng chứng Windows.

Mỗi lần chạy có `evidence/phase3/run-...`, gồm install, load-first, load-second,
constraints, demo-cycle, final-check và check.json/log. Từng bước phải passed=true.

## Demo nguồn cho pha sau

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/source_demo.ps1 -Action insert
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/source_demo.ps1 -Action update
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/source_demo.ps1 -Action status
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/source_demo.ps1 -Action delete
```

Chỉ thao tác DEMO_MANUAL_C/P/O có is_demo=true. Insert tạo đơn chưa nhận;
update thay số lượng/tiền và thời điểm nhận. Delete chỉ xóa entity demo script
sở hữu, không còn được đơn khác tham chiếu. Chưa cần chạy riêng bốn lệnh này
để nghiệm thu pha 3 vì demo-cycle đã thử luồng tương đương.

## Quy tắc nhập và giới hạn

Giữ bất nhất ngày giờ của nguồn để gắn cờ, không sửa cho đẹp. Không đưa tên
khách/tài xế, điện thoại và địa chỉ chi tiết vào MySQL mới. Tên sản phẩm và
kho là thuộc tính nghiệp vụ, không phải tên người. Tệp Excel gốc vẫn là đầu vào
ở máy/Docker image cục bộ; bản nộp công khai xử lý theo yêu cầu ẩn danh sau.

DDL MySQL không nguyên tử như DML. Installer có ownership, source_epoch và
fingerprint schema; không tự tiếp quản DB cũ không nhận diện. Nếu cài đặt
gián đoạn, gửi lỗi; không mô tả bootstrap tự phục hồi hoàn toàn.

Nạp lịch sử dùng transaction và no-op khi trùng khóa, rồi đọc lại toàn bộ
trường nghiệp vụ và provenance để đối soát trước commit. Cùng khóa khác nội
dung sẽ báo lỗi/rollback, không âm thầm sửa lịch sử. Không dùng loader reset
nguồn sau khi lịch sử đã được sửa phục vụ thử nghiệm CDC.

Binlog ROW/FULL đã cấu hình nhưng chưa có connector; PASS pha 3 không phải
PASS CDC. Môi trường trợ lý không có MySQL/Docker/PowerShell; chỉ test Python
offline đã chạy. Cần kết quả MySQL từ máy em trước khi chuyển pha 4.
