# Chốt Phase 13 và bàn giao

## Kết quả thực nghiệm

Đã kiểm chứng môi trường dựng lại riêng `lak-rebuild-b406a316e7` trên cùng Docker engine người dùng: restore hai CSDL, nạp mô hình, đối soát nguồn/mart, xác minh hai mô hình, cold import và 8 trang AppTest; sau đó bootstrap CDC mới, demo thêm/sửa/xóa qua ML, kiểm tra fact lịch sử/model registry giữ nguyên, dashboard healthy và scheduler check/unpause mart đạt. Khoảng chạy cuối: 26/10/2026 17:20:38–17:26:18 UTC+7. Bằng chứng gốc trong `evidence/`; script xác minh `scripts/phase13/verify_final_evidence.py` kiểm tra hash 40 tệp và các kết quả quan trọng.

Epoch mới `4f98ca52-2555-4307-9cdb-54b473e1bb5b`, có 4 dòng checkpoint mới. Dữ liệu nền được restore tường minh; connector no_data bắt schema/stream mới, không khẳng định có READ snapshot mới. Raw/ledger/checkpoint cũ được giữ dưới epoch cũ. Khóa surrogate/fact lịch sử không bị ghi lại chỉ vì chuyển môi trường; model không retrain. Chi tiết phục hồi thủ công và giới hạn tại ../rebuild-cdc.md.

`release.json` ở đây xác nhận bằng chứng dựng lại và chờ tạo bản đóng gói cuối tại máy có byte mô hình/image/dump. Các cờ false/pending trong JSON từng bước là trạng thái lịch sử tại thời điểm bước đó, được giữ nguyên. `RELEASE-MANIFEST.json` của bundle cuối là trạng thái đóng gói cuối cùng; không sửa bằng chứng cũ để đổi false thành true.

## Tạo bản giao nộp

Sau khi áp dụng patch chốt và Git commit hoàn tất, chạy finalize_release.py với candidate cũ, image tar và thư mục snapshot đã kiểm chứng. Nó kiểm tra bằng chứng, source/model, copy đúng tài sản theo checksum, tạo source/model/tooling mới có tài liệu cuối, ZIP64 hoàn chỉnh, checksum SHA-256 và installer độc lập. Giữ ZIP cuối, tệp SHA-256 và installer liền kề; không phải tải các dump hoặc ảnh Docker lên hội thoại.

Bundle gồm assets/verified-candidate.zip (đầu vào thực đã test), assets/tooling/ (source hiện hành, model, docs, evidence và toàn bộ helper dựng lại), assets/images/images.tar, assets/data/ (hai dump, TOC và export.json), metadata/ và README-START-HERE.md. Không có .runtime, password thật, API key, volume hoặc toàn văn báo ngoài phạm vi dữ liệu đã lưu. Toàn bộ tài sản đã liệt kê tường minh; cần chuyển cả bundle khi dựng lại máy khác.

ZIP có thành viên images.tar >2 GiB nên dùng Python ZIP64/installer đi kèm; không dùng PowerShell Compress-Archive để tạo bundle cuối. Installer xác minh SHA toàn ZIP và từng thành viên rồi extract tooling. Dùng --rebuild-output để chạy restore hai DB, tiếp đó chạy bootstrap_rebuild.py theo thư mục được in. Quy trình này tạo credential mới và project/volume/network/cổng riêng. Không cần Git để restore; Git cần cho quy trình tạo ứng viên source mới.

Cần Docker Desktop Linux amd64, Python host 3.11+; thư viện ứng dụng nằm trong 13 image đã lưu và khóa theo ID. Không cần pip install chín môi trường lên host. Cổng bản sao 13310/15435/18085/18501 phải trống. Hai stack đã chạy trên Docker khoảng 7,6 GiB nhưng không coi đó là cam kết tài nguyên tối thiểu cho mọi máy. Tệp images.tar khoảng 2,02 GiB, dump khoảng 35,84 MiB; cần thêm chỗ cho giải nén và volume DB.

## Vận hành sau bàn giao

Project gốc: `python scripts/phase13/ops.py status|start|stop|logs`, website http://localhost:8501.

Bản sao đã đạt bootstrap:

```powershell
python scripts/phase13/rebuild_ops.py status --rebuild 'G:\LAK-Rebuilds\LAK-Rebuild-20261026T095955Z-f2faba'
python scripts/phase13/rebuild_ops.py stop --rebuild 'G:\LAK-Rebuilds\LAK-Rebuild-20261026T095955Z-f2faba'
python scripts/phase13/rebuild_ops.py start --rebuild 'G:\LAK-Rebuilds\LAK-Rebuild-20261026T095955Z-f2faba'
```

`stop` giữ nguyên volume; `start` là vận hành thường lệ, không chạy lại bootstrap. Không dùng ops.py mặc định project gốc cho bản sao. Khi lỗi giữ bằng chứng, không tự xóa folder epoch hoặc reset volume.

## Hạn chế được giữ khi kết luận

- Đã dựng môi trường riêng trên cùng Docker engine, không thử máy vật lý/engine khác. Final ZIP được ráp sau khi kiểm chứng đúng các đầu vào candidate/image/dump; chưa chạy lại chính byte ZIP cuối từ đầu.
- Hai dump nhất quán riêng từng CSDL, không có distributed transaction; ứng dụng ghi đã được dừng, không được ghi qua client khác trong cửa sổ xuất/khôi phục.
- Một lỗi fileno ở script được sửa bằng TemporaryFile; log lỗi và lượt chạy lại thành công được giữ. Không có reset volume.
- 998 cảnh báo timestamp nguồn, 0 ERROR chất lượng. ML/RF cải thiện nhỏ, phân cụm mô tả snapshot. Hiệu năng là tải tuần tự và cache ấm; không suy diễn SLA/capacity.
- API key trống ở môi trường mới; tin tức trên bản sao là metadata lưu sẵn được restore, không phải lượt fetch API mới. Giữ nguồn và quyền sử dụng; không công bố tỷ lệ trễ SLA chưa xác minh.
- AI hỗ trợ mã/lệnh/tài liệu/phân tích; người dùng thực chạy Docker và cung cấp bằng chứng. Các kết quả runtime không phải số liệu do trợ lý mô phỏng.
