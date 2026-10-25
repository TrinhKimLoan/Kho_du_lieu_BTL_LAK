# Chạy kiểm tra giai đoạn 1 trên Windows

## Mục đích

Kiểm tra sáu Excel và tin mẫu bằng cùng một script, không sửa nguồn, không cần
Docker hay API key. Mỗi lần chạy tạo thư mục bằng chứng riêng nên không ghi đè
kết quả cũ. Đọc bộ đếm lỗi và cảnh báo để biết dữ liệu đủ cho thiết kế nào.

Gói giai đoạn 1 là bản đầy đủ, có mốc Git giai đoạn 0 và commit mới. Để giữ
nguyên thư mục em đã chạy, giải nén gói mới vào `G:\LAK-Phase1`, khi đó project
nằm ở `G:\LAK-Phase1\LAK-Analytics`. Chưa xóa `G:\LAK-Analytics` cũ.

```powershell
Set-Location G:\LAK-Phase1\LAK-Analytics
python scripts/profile_lak_data.py
python -m unittest discover -s tests -p test_phase1_profile.py -v
git log -2 --oneline
```

Có thể thay `python` bằng `py` nếu đó là Python Launcher trên máy em.
Dùng Python 3.11 trở lên, không cần cài thêm thư viện.

## Kết quả mong đợi

- Orders 10000, customers 3282, products 15.
- Dòng `PHASE 1 DATA CHECKS PASSED WITH OBSERVATIONS`.
- Cảnh báo sent_before_pack_timestamp: 880.
- Cảnh báo expected_before_sent_timestamp: 118.
- So sánh trễ theo timestamp: 5170, theo ngày: 1987. Đây chưa phải KPI SLA.
- Khác địa chỉ hồ sơ khách: 6070, không tự coi là lỗi.
- Năm test giai đoạn 1 đều đạt.

`profile.json` chứa fingerprint, tỷ lệ thiếu theo cột, lỗi đối soát, tổng tiền,
phân bố mua và giao hàng. `data_dictionary.md` là từ điển sáu bảng Excel;
`profile.md` là bảng đọc nhanh. Các tệp không chứa giá trị tên/điện thoại/địa chỉ.

Bằng chứng `assistant-run` là lần chạy ở môi trường trợ lý. Lần em chạy có tên
`run-...` mới. Không đổi tên hoặc ghi đè bằng chứng của hai môi trường cho nhau.

Nếu script FAILED, gửi lỗi và file profile.json mới. Không sửa Excel để ép khớp
các con số mẫu. Nếu nguồn có thay đổi, cần giải thích chênh lệch trước khi đi tiếp.

Sau khi em xác nhận kết quả, bước tiếp theo là giai đoạn 2: thiết kế grain,
fact/dimension, ánh xạ và hợp đồng CDC. Chưa chạy MySQL/CDC/ML trong giai đoạn 1.
