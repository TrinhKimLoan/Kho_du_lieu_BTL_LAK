# Pha 8 — Snapshot RFM, K-Means và phiên bản mô hình

## Mục đích

Tìm nhóm khách có hành vi mua khác nhau từ dữ liệu LAK, giải thích được đặc trưng mỗi nhóm và giữ được input/mô hình để chạy lại. Đây là thuật toán ML thứ nhất; RFM là tạo đặc trưng, Random Forest vẫn thuộc pha 9 theo kế hoạch.

Pha 7 đã được người dùng xác nhận `PHASE 7 MART AND OLAP CHECKS PASSED`, evidence `G:\LAK-Analytics\evidence\phase7\run-20261025T193240Z-3d53e43e`, sau sửa month_start alias. Không ghi đoán commit máy người dùng. Bản vá pha 8 bảo vệ hash của bản sửa đó và tất cả đầu vào đã chốt.

## RFM và snapshot

Ngày tham chiếu cố định **2026-01-01**, cửa sổ toàn lịch sử có packed_at trước ngày này. Không dùng ngày hệ thống để âm thầm tăng R. Ngày đóng gói là proxy do không có ngày đặt hàng thật, không đổi tên thành ngày đặt hàng.

- R: số ngày từ ngày đóng gói gần nhất đến ngày tham chiếu.
- F: số mã đơn khác nhau, không phải số lượng sản phẩm.
- M: tổng tiền hàng, không gồm VAT/phí; tính và lưu bằng Decimal/NUMERIC.
- Bản ghi demo/deleted được loại qua dw.v_sales_analysis. Thiếu packed_at bị loại khỏi RFM và được đếm rõ, vẫn nằm trong số liệu tiền của kho. Giao trước đóng gói không tự loại toàn bộ đơn khỏi RFM vì đây là vấn đề riêng về các mốc vận chuyển.
- Timestamp địa phương không timezone từ nguồn được giữ nguyên, không tự chuyển UTC trước khi tính R.

Capture thực hiện trong transaction REPEATABLE READ, đối soát SUM(F) với số đơn đủ điều kiện và SUM(M) với tiền hàng đủ điều kiện, giữ source SHA và dataset SHA. Feature snapshot có ID gắn với input RFM, thứ tự chuẩn, hợp đồng, split và input nguồn; cùng snapshot không được ghi đè. Surrogate customer_key không được dùng làm đặc trưng ML. File chỉ chứa mã khách, không tên/điện thoại/địa chỉ.

`ml.feature_snapshots` và `ml.rfm_features` lưu phiên bản dataset. Mỗi feature row có hash riêng. Snapshot không lấy customer_summary toàn lịch sử rồi gắn nhầm vào một mốc quá khứ; nó được tính trực tiếp từ các fact trong cửa sổ đúng.

## Chia tập và tiền xử lý

Xếp khách theo SHA256 của seed cố định và customer_id, chia 60% train / 20% validation / phần còn lại test, không trùng khách. Hash ID chỉ phục vụ chia tập, không là feature. Với dữ liệu gốc: 1969 / 656 / 657. Không đảo split do thứ tự nhập source.

Chỉ fit trên train: ngưỡng clipping 1%–99%, log1p, StandardScaler, K-Means. Mọi khách vẫn được giữ, không âm thầm xóa ngoại lệ. Giá trị gốc R/F/M còn trong snapshot và profile; clipping chỉ áp dụng không gian mô hình. M được chuyển float64 cho học máy, không dùng float đó để sửa các tổng tiền VND.

K thử 2–8, random_state=42, n_init=20. Độ ổn định: ARI giữa phân cụm train của seed chính và 3 seed khác 7/23/71, độc lập với tên nhãn cụm. Không gọi ARI này là độ chính xác so với khách VIP thật.

Tiêu chí hợp lệ khai báo trước: cụm nhỏ nhất >=3% train, >=2% validation, median ARI >=0.6, Silhouette validation tính được. Chọn Silhouette validation cao nhất, hòa thì DBI thấp hơn, rồi K nhỏ hơn. Nếu không candidate nào đạt, báo thất bại thay vì tự tạo nhãn/ép K. Giữ mô hình đã fit train, không refit trên cả tập sau khi chọn.

Test chỉ được transform/evaluate sau khi K đã chốt. Chạy lại để kiểm tra tái lập không phải cơ hội chọn lại mô hình dựa test. Clipping/scaler được kiểm chứng lại từ đúng các khách train đã lưu.

## Đánh giá và hồ sơ cụm

Báo Silhouette (cao hơn thường tách cụm tốt hơn), Davies–Bouldin (thấp hơn thường tách tốt hơn), kích thước cụm và ARI ổn định. Không có nhãn chuẩn, không báo accuracy, không gọi 0.40 Silhouette là chính xác 40%.

So sánh baseline nghiệp vụ: ba ngưỡng median train cho R thấp/F cao/M cao tạo tối đa 8 nhóm bit-pattern. Baseline được đánh giá trong cùng không gian tiền xử lý train-only. K-Means K=2 và baseline tối đa 8 nhóm có độ chi tiết khác nhau; chỉ số hình học không chứng minh ưu thế kinh doanh hoặc tác động chiến dịch.

Tên cụm dựa median R/F/M của khách đã gán sau khi mô hình cố định và các ngưỡng 1/3–2/3 trên train. Profile toàn bộ và số khách từng split được lưu; việc mô tả profile không fit lại mô hình. Tên “gần đây/chi tiêu cao” là tương đối trong tập mô phỏng, không phải chuẩn tuyệt đối hoặc cam kết khách VIP. Cluster 0/1 không là thứ hạng.

Snapshot chính ở 2026-01-01 và không có giao dịch lịch sử được cung cấp sau mốc đó, nên chưa đánh giá hành vi tương lai sau snapshot này. Không khẳng định mô hình dự đoán giữ chân khách hay đem lại doanh thu thực tế. Có sáu năm dữ liệu trước snapshot không đồng nghĩa có tương lai sau snapshot. Không thay đổi snapshot chính sang 2025 để tô đẹp một phép thử khác.

Nguồn lý thuyết/thư viện:
- https://scikit-learn.org/stable/modules/clustering.html
- https://scikit-learn.org/stable/common_pitfalls.html#data-leakage
- https://scikit-learn.org/stable/modules/generated/sklearn.cluster.KMeans.html

## Kết quả chuẩn bị offline — chưa phải kết quả PostgreSQL của người dùng

Đã tính feature từ các file LAK gốc và huấn luyện thật ở môi trường trợ lý, với các thư viện khóa trong requirements-phase8.txt:

- 3282 khách, SUM(F)=10000, SUM(M)=618293800000.00 VND.
- K=2 được chọn, không đặt cố định từ trước.
- Validation: Silhouette 0.432779, DBI 0.910034; test: Silhouette 0.404266, DBI 0.959806.
- Baseline validation Silhouette 0.185189, test 0.165818; khác số nhóm nên không coi đây là kết luận ưu thế kinh doanh.
- Hai cụm toàn tập: 1993 và 1289 khách. Median lần lượt R=994/F=1/M=51200000; R=224/F=5/M=288600000.
- Joblib roundtrip và artifact reuse đã kiểm tra. ID/hash model offline có thể khác bản Docker vì metadata lưu cả phiên bản Python; không yêu cầu ID máy em bằng ID trợ lý.

Các số này là kiểm chứng thuật toán trên dữ liệu nguồn, không thay thế snapshot SQL, publish registry và kiểm thử Docker trên máy em. Nếu output máy em khác, đọc bằng chứng để xác định nguyên nhân, không sửa dữ liệu để khớp số dự kiến.

## Artifact và registry

Folder `G:\LAK-Analytics\data\models\kmeans_rfm\<model_id>` chứa pipeline.joblib, metadata.json, evaluation.json, profiles.json, assignments CSV/JSON, features.csv, feature_contract.json và manifest.json. Manifest SHA từng file, database giữ SHA manifest. Không đưa các artifact vào image/Git; chúng được giữ bằng bind mount trên ổ G: và sẽ đóng gói có kiểm soát ở pha 13.

Model ID gắn snapshot, cấu hình, thư viện/Python và checksum code học máy. Folder mới được ghi vào thư mục tạm rồi rename. Cùng ID chỉ được reuse sau khi checksum và prediction khớp, không overwrite artifact. Sửa artifact dù một ký tự làm verify thất bại.

`ml.model_registry`, `ml.customer_segments`, `ml.segment_profiles` lưu model version và kết quả. Publish registry/assignments trong cùng transaction và chỉ commit sau verify. Mô hình hợp lệ đầu tiên tự active; phiên bản mới sau đó không tự thay active pointer để suy luận sau này được giữ có kiểm soát. Chưa có worker ML live ở pha này, phần đó thuộc pha 10. File model là dữ liệu do pipeline này tạo, không tải model lạ để nạp tùy tiện.

## Chạy kiểm thử

Chỉ cần Python chuẩn để áp dụng patch. Các test cần NumPy/sklearn chạy **trong Docker**; không yêu cầu em cài pip trên Windows:

```powershell
Set-Location G:\LAK-Analytics
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_phase8.ps1
```

Runner dựng image ML mới, chạy 9 unit tests, capture/huấn luyện/publish, verify ở container mới rồi chạy lại để chứng minh reuse cùng model/snapshot. Không thay MySQL/CDC, mart, tin tức hoặc lịch Airflow. Mật khẩu được giữ trong .runtime/lak.env, không vào artifact.

PASS: `PHASE 8 RFM AND KMEANS CHECKS PASSED`, theo sau đường dẫn model và evidence/phase8/run-*. Evidence có train.json, verify.json, replay.json, check.json và phase8.log. Không tiến hành Random Forest pha 9 trước khi người dùng gửi PASS thực tế.

## Giới hạn hiện tại

Có unit tests và huấn luyện/joblib thật trên dữ liệu LAK ở môi trường trợ lý. Không có Docker/PostgreSQL/PowerShell ở đây để chạy SQL registry/capture/publish; vẫn chờ bằng chứng từ máy người dùng. Chưa đo tác động kinh doanh, chưa có nhãn VIP do người gán, chưa đánh giá vận hành dữ liệu thực của doanh nghiệp.
