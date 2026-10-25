# Kiểm tra giai đoạn 2 trên Windows

## Mục đích và đầu ra

Giai đoạn 2 có thiết kế grain, ERD, ánh xạ nguồn và quy tắc thay đổi, SQL schema
mới, hợp đồng JSON và bộ thử. Chưa tạo CSDL MySQL, CDC worker hoặc model.
Tài liệu bắt đầu từ `warehouse_design.md`, `erd.md`, `source_mapping.md` và
`change_contract.md` trong cùng thư mục.

Gói đầy đủ có mốc giai đoạn 0, 1 và commit giai đoạn 2. Giải nén vào
`G:\LAK-Phase2` để có `G:\LAK-Phase2\LAK-Analytics`; giữ nguyên thư mục trước.

## Kiểm tra hợp đồng và SQL ở mức văn bản

```powershell
Set-Location G:\LAK-Phase2\LAK-Analytics
python scripts/verify_phase2.py
python -m unittest discover -s tests -p test_phase2_contract.py -v
git log -3 --oneline
```

Mong đợi `PHASE 2 DESIGN CHECKS PASSED`, bốn test đạt. Đây chưa phải kiểm tra
cú pháp hoặc thực thi PostgreSQL. Không dùng kết quả này để đánh dấu schema chạy.

## Kiểm tra schema trên PostgreSQL thật

Mở Docker Desktop ở chế độ Linux containers, rồi chạy:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test_phase2_postgres.ps1
```

Bypass chỉ áp dụng cho tiến trình PowerShell chạy tệp này, không đổi policy
toàn máy. Script dùng image PostgreSQL 16.15-trixie trong bản cấu hình
CommerceInsight đã cung cấp; có thể cần tải image nếu máy chưa có.

Script tự tạo container `lak-phase2-check-...` với tên ngẫu nhiên, không mở cổng,
không gắn volume, không nối mạng container khác và dữ liệu nằm trên tmpfs.
Nó tạo một CSDL thử rỗng, chạy schema rồi fixture. Cuối cùng gỡ chính container
vừa tạo. Không đụng container, dữ liệu hoặc volume cũ. Không sửa compose cũ.

Các fixture kiểm tra thành viên 0, khóa Kafka, tiền, FK, ngày theo vai trò,
delivery_hours, xử lý nhãn giao âm, SCD2, loại demo/xóa, bridge và ví dụ tổng
hợp trước khi ghép hai fact. Fixture được rollback sau thử.

Mong đợi `PHASE 2 POSTGRES CHECKS PASSED` và đường dẫn bằng chứng trong
`evidence/phase2/run-...`: check.json và postgres-check.log.

Nếu báo FAILED, gửi toàn bộ đoạn lỗi hoặc hai tệp bằng chứng. Không chạy SQL
vào CSDL cũ, không xóa volume và không tiếp tục giai đoạn 3 để né lỗi schema.

## Mức chứng cứ

Môi trường trợ lý không có PostgreSQL, Docker hoặc PowerShell. Trợ lý chỉ chạy
lint hợp đồng, test Python và đối chiếu source; lần chạy PostgreSQL trên Windows
mới là bằng chứng thực thi DDL. Giai đoạn 2 chưa được xác nhận runtime trước
khi có kết quả thực tế đó. Bằng chứng giai đoạn 1 trên Windows đã được người
dùng xác nhận, không giả lập đường dẫn đó thành tệp có sẵn trong gói trợ lý.
