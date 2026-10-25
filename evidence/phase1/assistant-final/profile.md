# Kết quả kiểm tra dữ liệu LAK

Thời điểm UTC: 2026-10-25T15:30:43.447565+00:00

Kết quả chỉ xác nhận dữ liệu và quy tắc kiểm tra được liệt kê; không chứng minh CDC, ML hoặc Docker đã chạy.

Kiểm tra bắt buộc: ĐẠT.

## Lỗi bắt buộc

| Quy tắc | Số trường hợp |
| --- | ---: |
| 01_missing_keys | 0 |
| 01_duplicate_keys | 0 |
| 02_missing_keys | 0 |
| 02_duplicate_keys | 0 |
| 03_missing_keys | 0 |
| 03_duplicate_keys | 0 |
| 04_missing_keys | 0 |
| 04_duplicate_keys | 0 |
| 05_missing_keys | 0 |
| 05_duplicate_keys | 0 |
| 06_missing_keys | 0 |
| 06_duplicate_keys | 0 |
| 04_order_key_set_difference | 0 |
| 05_order_key_set_difference | 0 |
| 06_order_key_set_difference | 0 |
| missing_customer_refs | 0 |
| missing_product_refs | 0 |
| quantity_nonpositive_or_noninteger | 0 |
| unit_price_nonpositive | 0 |
| negative_goods_vat_fee_total | 0 |
| quantity_copy_mismatch | 0 |
| goods_formula_mismatch | 0 |
| vat_formula_mismatch | 0 |
| total_formula_mismatch | 0 |
| received_before_sent_timestamp | 0 |
| shipping_type_copy_mismatch | 0 |
| Kho_Xuat_copy_mismatch | 0 |
| Xe_Van_Chuyen_copy_mismatch | 0 |
| Tai_Xe_copy_mismatch | 0 |
| customer_order_count_mismatch | 0 |
| customer_total_paid_mismatch | 0 |
| product_order_count_mismatch | 0 |
| product_units_mismatch | 0 |
| product_goods_mismatch | 0 |

## Cảnh báo và quan sát

| Quy tắc | Số trường hợp |
| --- | ---: |
| catalog_transaction_price_difference | 0 |
| sent_before_pack_timestamp | 880 |
| expected_before_sent_timestamp | 118 |
| late_by_timestamp_unconfirmed_sla | 5170 |
| late_by_date_unconfirmed_sla | 1987 |
| order_location_differs_from_customer_profile | 6070 |

Cảnh báo địa chỉ khác nhau không mặc định là lỗi. Tỷ lệ trễ chưa được dùng làm KPI SLA.

Các phân bố, tổng tiền, độ phủ tin và dấu vân tay nguồn nằm trong profile.json.
Kiểm tra nguồn gốc/giấy phép và chất lượng nhãn tin cần bằng chứng bổ sung ngoài script.
