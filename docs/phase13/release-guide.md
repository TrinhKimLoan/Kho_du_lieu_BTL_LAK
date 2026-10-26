# Ứng viên release và quy trình dựng lại

## Stage A — Đã triển khai, chờ kết quả trên máy người dùng

```powershell
python scripts/phase13/release.py check-local --target 'G:\LAK-Analytics'
python scripts/phase13/release.py check-images --target 'G:\LAK-Analytics'
python scripts/phase13/release.py package --target 'G:\LAK-Analytics' --output 'G:\LAK-Releases'
```

Lệnh đóng gói yêu cầu source đã commit, không có thay đổi tracked chưa commit. Untracked nằm trong `evidence/` được để nguyên nhưng không tự động đưa vào gói; bằng chứng Phase 12 đã chấp nhận nằm trong `docs/phase12/evidence/` và được đưa vào vì đã tracked. Untracked source ngoài `evidence/` phải được xem xét; không tự xóa hoặc tự commit thay người dùng.

Ứng viên chứa toàn bộ tệp Git tracked hiện tại (gồm Excel nguồn, SQL, code, tài liệu và bằng chứng đã chọn), cộng đúng 19 tệp của hai mô hình theo checksum. `.git`, `.runtime`, virtualenv, credential và private key không được đưa vào. Không chạy model/joblib khi đóng gói. Không ghi source/model mới hoặc huấn luyện lại. Chỉ tạo file ngoài project tại thư mục đầu ra.

Mỗi lần tạo tên duy nhất, có ZIP, `.zip.sha256`, `.summary.json`. `RELEASE-MANIFEST.json` bên trong ghi file/byte/SHA-256, Git HEAD và các cờ phạm vi. Xác minh:

```powershell
python scripts/phase13/release.py verify-package --archive 'G:\LAK-Releases\TEN-UNG-VIEN.zip'
Get-FileHash -Algorithm SHA256 'G:\LAK-Releases\TEN-UNG-VIEN.zip'
```

Kiểm tra toàn bộ thành viên ZIP, từ chối đường dẫn thoát thư mục, tệp lặp, thêm/bớt tệp và checksum sai. Đây là kiểm tra nguyên vẹn gói, không phải kết quả dựng lại ứng dụng.

## Khóa phiên bản

- `infra/locks/images.json`: ID và RepoDigests thực quan sát. `infra/compose.release-lock.yaml` cố định tag, platform và pull_policy=never; wrapper so sánh tag→ID trước khi start. Dùng tag làm địa chỉ local, ID làm kiểm tra tính toàn vẹn; tên tag không phải bằng chứng bất biến.
- `infra/locks/python/*.lock.txt`: `pip freeze --all` riêng từng image, gồm package trực tiếp/gián tiếp. Không cài chín lock vào một môi trường chung.
- Một cảnh báo cache pip của Airflow được tách khỏi lock; nguyên văn còn trong inventory. JSON image từ PowerShell bị bỏ dấu nháy quanh key; chỉ các key đã biết được chuẩn hóa rồi parse JSON, giữ nguyên bản gốc để truy vết.
- Các lock là ảnh chụp môi trường đang chạy, không tự sửa Dockerfile, không khóa digest base Python/Airflow của một lần source build mới. Image LAK local dù có RepoDigest trong inventory vẫn chưa được chứng minh tồn tại trên registry công khai. Không thể dựng lại offline chỉ từ tên/digest.

## Stage B — Chưa thực hiện

1. Xuất byte các image đã kiểm chứng ra archive có checksum, hoặc hoàn thiện và kiểm chứng source build có khóa base/dẫn xuất. Giữ thông tin provenance: image từng pha có thể chứa source đóng băng ở thời điểm build, khác các tài liệu/script mới thêm.
2. Xuất dữ liệu cần thiết một cách rõ ràng: snapshot nguồn/DW, tin tức metadata đã lưu nếu được phép, trạng thái mô hình; ghi phương pháp nhất quán và cửa sổ tạm dừng writer nếu cần. Không đưa password/API key thật vào bản nộp.
3. Xác định quy trình khôi phục CDC: MySQL binlog/epoch, Kafka offsets và Connect state không được giả định tương thích khi restore SQL sang instance mới. Không đơn thuần restore DW rồi gắn connector cũ vào nguồn mới.
4. Dựng project khác, thư mục/volume/network/cổng khác; tạo credential riêng. Với Docker giới hạn khoảng 7,6 GiB, bố trí tài nguyên trước khi chạy hai stack; nếu cần dừng stack gốc thì dùng `stop` và khôi phục sau thử nghiệm, không xóa volume.
5. Dựng từ gói + các archive được kê khai; chạy snapshot/reconcile, ML verify, dashboard, rồi thay đổi demo mới qua CDC. Không mượn volume hoặc `.runtime` âm thầm từ project gốc.
6. Ghi mọi bước phục hồi thủ công, output/checksum và hạn chế; hoàn thiện release cuối, báo cáo và dàn ý bảo vệ.

**Ứng viên Stage A không có database dump, byte Docker image, credential, trạng thái volume hay bằng chứng dựng lại. Không sử dụng nó như gói cài đặt độc lập hoàn chỉnh. Phase 13 vẫn đang thực hiện.**
