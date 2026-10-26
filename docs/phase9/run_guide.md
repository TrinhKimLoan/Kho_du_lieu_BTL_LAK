# Phase 9 — Random Forest dự đoán thời gian giao hàng

Giữ nguyên định nghĩa đã chốt ở Phase 1: dự đoán tại lúc giao đi. Nhãn là số giờ liên tục từ dispatched_at đến received_at. Ngày dự kiến chưa được xác nhận là SLA; không dự đoán tỷ lệ trễ cam kết.

## Chạy nối tiếp trên Windows

Giữ nguyên dự án G:\LAK-Analytics, file .runtime/lak.env, volume Docker và thư mục data/models. Áp dụng ZIP patch bằng apply_update.py, rồi chạy:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_phase9.ps1
```

Script dựng image công cụ riêng, kiểm tra mô hình Phase 8 trong DB và artifact, chạy 10 unit test Phase 9, tạo snapshot từ PostgreSQL, huấn luyện RF, nạp lại mô hình, đối soát bảng dự đoán và chạy lại để kiểm tra dùng lại cùng phiên bản. Không chạy lại CDC bootstrap hoặc nhập lịch sử. Không dừng các dịch vụ đang chạy. Chưa bật cập nhật dự đoán theo CDC; đó là Phase 10.

Mỗi lần chạy tạo evidence/phase9/run-... riêng: phase9.log, preflight.json, train.json, verify.json, replay.json, check.json. Nếu lỗi, gửi phần cuối phase9.log và JSON tương ứng; không reset DB hoặc xóa volume.

## Hợp đồng dữ liệu và đánh giá

- Train: giao đi 2020–2023, thực nhận trước 01/01/2024.
- Validation: giao đi năm 2024, thực nhận trước 01/01/2025.
- Test: giao đi năm 2025, thực nhận trước 01/01/2026.
- Thiếu mốc, thời gian âm, ngoài cửa sổ, nhãn chưa có tại cutoff được ghi riêng trong observations. Tiền hàng trong fact không bị loại bỏ.
- Đặc trưng: số lượng, giá trị hàng, tháng/thứ/giờ giao đi; loại giao, nhóm số lượng, kho, loại xe, quận/huyện. Tên tài xế, địa chỉ đầy đủ, khách hàng, mã đơn, ngày nhận, ngày dự kiến và thời lượng thực không vào ma trận X. order_id chỉ là khóa truy vết.
- Không dùng product_id dạng số thứ tự; không lấy thông tin sản phẩm cập nhật hiện tại để giả định là thông tin đã biết trong quá khứ.
- Giả định các đầu vào đã biết tại lúc giao đi phải được giữ khi nhập/demo. Excel không có nhật ký nhập để chứng minh. Snapshot lịch sử lấy từ trạng thái DW hiện tại, không tuyên bố là bản dựng lại dữ liệu as-of lịch sử trước mọi chỉnh sửa.
- Chỉ fit imputer/encoder/forest trên train. Thử 4 cấu hình (150 cây, depth 6/không giới hạn; leaf tối thiểu 5/20), chọn MAE validation rồi RMSE để phân xử. Seed 42, một luồng để hạn chế tài nguyên. Không refit toàn bộ hoặc dùng test để chọn.
- Baseline toàn train và trung vị theo loại giao (fallback toàn train cho loại mới). MAE/RMSE/bias đơn vị giờ. Không gọi accuracy.
- Báo sai số test theo quận/huyện, loại giao và nhóm số lượng; nhóm dưới 30 đơn gắn cờ ít mẫu.
- Permutation importance trên test có mức tăng MAE và độ lệch chuẩn. Chỉ diễn giải sau khi đóng băng model; không chọn lại đặc trưng/cấu hình từ kết quả này. Không diễn giải nhân quả.
- Model có thể không vượt baseline; kết quả vẫn được lưu và kiểm tra đúng. READY chỉ xác nhận artifact đã kiểm chứng, không đồng nghĩa hiệu quả kinh doanh. Chưa tự kích hoạt RF trong model registry; Phase 10 xử lý chính sách sử dụng model.

## Kết quả lưu

Model: data/models/random_forest_delivery/rf-delivery-.../

- pipeline.joblib: pipeline imputer, encoder, RF.
- metadata.json, feature_contract.json, manifest.json: danh tính, thư viện, cấu hình, hash mã và checksum từng file.
- features.json/csv: snapshot dataset và split; received_at và target chỉ dành cho nhãn/đối soát, không đưa vào predictor.
- predictions.json/csv: actual, predicted, baseline, error theo đơn và split. Sai số train là trong mẫu, chỉ test dùng để báo chất lượng cuối.
- evaluation.json: lựa chọn cấu hình, baseline, metrics, sai số nhóm, importance, giới hạn.
- feature_explanation.md: trang giải thích để đọc trong VS Code và dùng lại cho website Phase 11.

PostgreSQL: ml.feature_snapshots, ml.delivery_features, ml.model_registry, ml.delivery_predictions; giữ nguyên bảng của K-Means. Snapshot, model ID và artifact đều có phiên bản; chạy lại cùng dữ liệu/mã/cấu hình/thư viện dùng lại artifact sau kiểm tra checksum và dự đoán. Không tự ghi đè phiên bản cũ.

## Bằng chứng ở môi trường chuẩn bị

Huấn luyện thật trên Excel LAK gốc: 6.682 train, 1.671 validation, 1.599 test; 14 đơn train và 34 đơn validation chưa có nhãn trước cutoff bị loại khỏi ML. RF MAE test xấp xỉ 18,73 giờ; baseline theo loại giao xấp xỉ 18,83 giờ. Cải thiện khoảng 0,10 giờ (~6 phút), chưa chứng minh có ý nghĩa thống kê hay kinh doanh. Không quảng bá độ chính xác cao hoặc vận tải thực.

Đã chạy unit test và offline training tại môi trường chuẩn bị. Chưa kiểm chứng PostgreSQL/Compose/PowerShell thực tế tại đó. Chỉ chốt Phase 9 sau khi script chạy đạt trên máy người dùng.

Có thể tái lập kiểm tra Excel ở môi trường đã cài requirements-phase8.txt bằng `python -m scripts.offline_phase9 --output <thư_mục_riêng>`; đây không thay thế kiểm tra PostgreSQL.
