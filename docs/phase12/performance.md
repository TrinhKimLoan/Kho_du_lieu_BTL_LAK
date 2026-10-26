# Báo cáo hiệu năng Phase 12

## Cấu hình và cửa sổ đo

i5-12450H: 8 core/12 logical; RAM máy 15,7 GiB. Docker 29.1.5 Linux: 12 CPU, 8.167.567.360 byte (~7,607 GiB). Baseline ổ G: tổng 244,14 GiB, trống 113,19 GiB; đây là trạng thái baseline, không phải mức ghi đĩa trong cửa sổ đo.

Run: `measure-20261026T082221Z-b0e86798`; từ 2026-10-26T08:22:31.779352+00:00 đến 2026-10-26T08:24:32.398108+00:00 (UTC).

## Độ trễ

20 mẫu mỗi thao tác, tổng 60. Đồng hồ perf_counter monotonic trong một tiến trình; bắt đầu trước source action, kết thúc khi polling quan sát đúng trạng thái committed DW rồi đúng RFM/delivery. Poll 0,1 giây. Đơn vị giây.

| Thao tác | n | DW mean | DW p95 | ML mean | ML p95 | ML max |
|---|---:|---:|---:|---:|---:|---:|
| insert | 20 | 1.0713 | 1.5712 | 1.6165 | 2.0538 | 2.0893 |
| update | 20 | 1.0442 | 1.6355 | 1.5045 | 2.0580 | 2.0685 |
| delete | 20 | 1.0867 | 1.6405 | 1.6571 | 2.0657 | 2.0872 |

Có cả request→ack và ack→DW/ML trong measurement.json. p95 nội suy tuyến tính; n=20 chỉ mô tả cửa sổ nhỏ. Đây là độ trễ quan sát có polling, gồm thời gian SQL/commit round trip, không phải timestamp commit binlog chính xác. Không đo lịch mart 15 phút hoặc browser rendering.

## Fact và mart

Mỗi nguồn/query có 2 warmup và 10 lượt tính giờ, thứ tự cặp ngẫu nhiên seed 12, cùng repeatable-read snapshot. Thời gian gồm execute + fetchall/giải mã Python; cache ấm, không flush cache. Mỗi lượt kiểm tra đầu ra bằng nhau. Đơn vị ms.

| Query | Dòng kết quả | Fact mean | Mart mean | Fact p95 | Mart p95 |
|---|---:|---:|---:|---:|---:|
| total | 1 | 44.792 | 44.451 | 72.768 | 72.498 |
| year | 6 | 29.283 | 28.947 | 34.064 | 35.810 |
| month_category | 792 | 92.771 | 85.634 | 169.891 | 120.974 |
| district | 576 | 97.736 | 96.047 | 144.736 | 151.024 |
| product | 15 | 42.739 | 46.049 | 55.652 | 71.613 |
| slice_2024 | 11 | 30.379 | 30.052 | 56.901 | 57.138 |

Mart không nhanh hơn rõ rệt trên workload này; query product chậm hơn fact. Không chọn riêng lượt nhanh để báo cáo. Raw timings và EXPLAIN ANALYZE BUFFERS có trong query-benchmark.json.

## Tài nguyên

30 mẫu docker stats; 9–10 container/mẫu (tool tạm thời có thể xuất hiện). Tổng RAM container mean 2.803 GiB, max quan sát 2.883 GiB. Tổng CPU mean 95.89%, max 447.19% theo quy ước Docker 100%=một CPU; chia cho 12 tương ứng 7.99% / 37.27% năng lực 12 CPU.

Thời điểm ghi mẫu bao quanh lệnh docker stats; có độ trễ lấy mẫu. Không phải peak tuyệt đối, RAM toàn VM hoặc RAM Windows. Không suy diễn khả năng chịu tải đồng thời từ số đo tuần tự.

PostgreSQL database 169.054 MiB. Sáu schema raw/staging/dw/mart/audit/ml gồm bảng + index/TOAST tổng 159.062 MiB. Database size và schema sum khác phạm vi.

Docker system df GLOBAL: images 10,56 GB; containers 63,09 MB; volumes 15,23 GB; build cache 4,134 GB. Đây là toàn Docker, không riêng LAK; không cộng thành mức đĩa vật lý dự án. NetIO/BlockIO là counter từ khi container chạy, không phải throughput riêng cửa sổ. Không chạy prune để thay đổi kết quả.
