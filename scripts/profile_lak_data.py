"""Read-only LAK data profiling with Decimal and the preserved XLSX reader."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
from app.core import dateval, record_from, xlsx_rows

KEYS = {'01': 'Ma_Don', '02': 'Ma_Khach_Hang', '03': 'Ma_San_Pham',
        '04': 'Ma_Don', '05': 'Ma_Don', '06': 'Ma_Don'}
MEANINGS = {
    'Ma_Don': 'Mã đơn, khóa nghiệp vụ; mỗi đơn hiện có một sản phẩm',
    'Ma_Khach_Hang': 'Mã khách, dùng ghép lịch sử mua; không dùng như đặc trưng số',
    'Ma_San_Pham': 'Mã sản phẩm, dùng ghép danh mục',
    'Loai_Giao_Hang': 'Loại dịch vụ giao: nhanh, bình thường hoặc chậm',
    'So_Luong': 'Số đơn vị sản phẩm trong đơn',
    'Muc_Hang_Hoa': 'Nhóm ít/vừa/nhiều; cần phân biệt phân nhóm theo đơn và sản phẩm',
    'Kho_Xuat': 'Kho xuất của đơn', 'Xe_Van_Chuyen': 'Loại phương tiện giao',
    'Tai_Xe': 'Tên tài xế trong nguồn; không đưa tên vào dashboard/bản nộp',
    'Ten_Khach_Hang': 'Tên khách trong nguồn; loại khỏi tập phân tích công khai',
    'Gioi_Tinh': 'Giới tính ghi trong nguồn; không cần cho RFM',
    'SDT': 'Số điện thoại; không đưa vào đặc trưng hoặc đầu ra phân tích',
    'Dia_Chi_Giao': 'Địa chỉ theo khách hoặc theo đơn; không đồng nhất hai vai trò',
    'Tinh_Thanh': 'Địa bàn cấp tỉnh/thành theo bảng nguồn; hiện chỉ có TP Hồ Chí Minh',
    'Quan_Huyen': 'Địa bàn chi tiết theo nguồn; giữ nguyên nhãn lịch sử',
    'So_Lan_Mua_Goc': 'Số lần mua tổng hợp sẵn; không dùng cho snapshot quá khứ',
    'So_Don_Hang': 'Số đơn tổng hợp toàn bộ nguồn; chỉ dùng đối soát',
    'Tong_Chi_Tieu': 'Tổng thanh toán cả lịch sử theo khách, gồm VAT/phí; chỉ đối soát',
    'Loai_Hang': 'Nhóm hàng rộng trong nguồn; hiện chỉ có Linh kiện điện tử',
    'Ten_Hang_Hoa': 'Tên sản phẩm trong danh mục hiện có',
    'Don_Gia_San_Pham': 'Đơn giá VND; lấy giá ở bảng thanh toán làm giá của giao dịch',
    'So_Don_Co_San_Pham': 'Số đơn tổng hợp theo sản phẩm; chỉ đối soát',
    'Tong_So_Luong_Ban': 'Số lượng tổng hợp theo sản phẩm; chỉ đối soát',
    'Tong_Doanh_Thu_Hang': 'Tiền hàng tổng hợp theo sản phẩm, chưa VAT/phí',
    'Thoi_Gian_Dong_Goi': 'Ngày đóng gói, không có bằng chứng đây là ngày đặt hàng',
    'Gio_Dong_Goi': 'Giờ đóng gói, ghép với ngày đóng gói',
    'Thoi_Gian_Giao_Hang': 'Ngày giao đi theo cách diễn giải vận hành được chọn',
    'Gio_Giao_Hang': 'Giờ giao đi, ghép với ngày giao đi',
    'Thoi_Gian_Du_Kien_Toi': 'Ngày dự kiến tới; chưa xác nhận là SLA cam kết',
    'Gio_Du_Kien_Toi': 'Giờ dự kiến tới; có bản ghi không hợp lý, chưa làm KPI SLA',
    'Thoi_Gian_Nhan_Hang': 'Ngày nhận thực tế',
    'Gio_Nhan_Hang': 'Giờ nhận thực tế',
    'Tong_Gia_Tri_Hang': 'Tiền hàng VND, bằng số lượng nhân đơn giá',
    'VAT_10': 'VAT VND, quy tắc bộ dữ liệu bằng 10 phần trăm tiền hàng',
    'Phi_Van_Chuyen': 'Phí vận chuyển VND theo đơn',
    'Tong_Thanh_Toan': 'Tổng tiền hàng cộng VAT cộng vận chuyển, không phải lợi nhuận',
}


def decimal(value):
    if value is None or value == '':
        raise ValueError('Missing numeric value')
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError('Nonfinite numeric value')
    return result


def stamp(row, day_col, clock_col):
    day = dateval(row[day_col])
    value = row[clock_col]
    if day is None or value is None or value == '':
        raise ValueError('Missing/invalid timestamp')
    if isinstance(value, (float, int)):
        fraction = decimal(value)
        if not Decimal(0) <= fraction < Decimal(1):
            raise ValueError('Excel clock fraction outside one day')
        seconds = int((fraction * 86400).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        return datetime.combine(day, time()) + timedelta(seconds=seconds)
    return datetime.combine(day, time.fromisoformat(str(value)))


def describe(values):
    return {'count': len(values), 'min': min(values), 'median': median(values),
            'mean': mean(values), 'max': max(values)} if values else {'count': 0}


def analyze(source):
    tables, files, profiles, hard = {}, {}, {}, {}
    for prefix, key in KEYS.items():
        matches = sorted((source / 'excel').glob(prefix + '*.xlsx'))
        if len(matches) != 1:
            raise ValueError(f'Expected one {prefix} workbook, found {len(matches)}')
        path = matches[0]
        rows = xlsx_rows(path)
        if not rows:
            raise ValueError(f'Empty workbook {path.name}')
        columns = {}
        for col in rows[0]:
            values = [r.get(col) for r in rows]
            missing = sum(v is None or v == '' for v in values)
            columns[col] = {'missing': missing, 'missing_percent': round(100 * missing / len(rows), 4),
                            'distinct_nonmissing': len({str(v) for v in values if v is not None and v != ''}),
                            'storage_types': sorted({type(v).__name__ for v in values if v is not None}),
                            'meaning': MEANINGS.get(col, 'Cần bổ sung định nghĩa trước sử dụng')}
        key_values = [r.get(key) for r in rows]
        missing_keys = sum(v is None or v == '' for v in key_values)
        duplicates = len(key_values) - len(set(key_values))
        hard[prefix + '_missing_keys'] = missing_keys
        hard[prefix + '_duplicate_keys'] = duplicates
        profiles[prefix] = {'filename': path.name, 'rows': len(rows), 'key': key,
                            'columns': columns, 'exact_duplicate_rows': len(rows) - len({json.dumps(r, sort_keys=True, ensure_ascii=False) for r in rows})}
        files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        tables[prefix] = rows
    report = {'phase': 1, 'python': platform.python_version(),
              'checked_at_utc': datetime.now(timezone.utc).isoformat(),
              'source_sha256': files, 'tables': profiles, 'hard_errors': hard,
              'warnings': {}, 'assumptions': ['sales are simulated according to source API note',
              'shipping date interpreted as dispatch date', 'timestamps rounded to nearest second',
              'no observed order-created or payment-confirmation timestamp']}
    if any(hard.values()):
        report['passed'] = False
        return report
    orders = tables['01']
    customers = {r['Ma_Khach_Hang']: r for r in tables['02']}
    products = {r['Ma_San_Pham']: r for r in tables['03']}
    timing = {r['Ma_Don']: r for r in tables['04']}
    payment = {r['Ma_Don']: r for r in tables['05']}
    shipping = {r['Ma_Don']: r for r in tables['06']}
    order_ids = {r['Ma_Don'] for r in orders}
    for prefix in ('04', '05', '06'):
        hard[prefix + '_order_key_set_difference'] = len(order_ids ^ {r['Ma_Don'] for r in tables[prefix]})
    hard['missing_customer_refs'] = sum(o['Ma_Khach_Hang'] not in customers for o in orders)
    hard['missing_product_refs'] = sum(o['Ma_San_Pham'] not in products for o in orders)
    if any(hard.values()):
        report['passed'] = False
        return report
    checks = Counter()
    warnings = Counter()
    by_customer, by_product, by_type = defaultdict(list), defaultdict(list), defaultdict(list)
    moments, amounts, years, annual_customers = [], defaultdict(lambda: Decimal(0)), Counter(), defaultdict(Counter)
    for order in orders:
        oid = order['Ma_Don']
        pay, ship, when = payment[oid], shipping[oid], timing[oid]
        customer, product = customers[order['Ma_Khach_Hang']], products[order['Ma_San_Pham']]
        try:
            qty = decimal(order['So_Luong'])
            unit = decimal(pay['Don_Gia_San_Pham'])
            goods, vat, fee, total = [decimal(pay[k]) for k in ('Tong_Gia_Tri_Hang', 'VAT_10', 'Phi_Van_Chuyen', 'Tong_Thanh_Toan')]
            checks['quantity_nonpositive_or_noninteger'] += qty <= 0 or qty != qty.to_integral_value()
            checks['unit_price_nonpositive'] += unit <= 0
            checks['negative_goods_vat_fee_total'] += any(v < 0 for v in (goods, vat, fee, total))
            checks['quantity_copy_mismatch'] += qty != decimal(pay['So_Luong'])
            checks['goods_formula_mismatch'] += goods != qty * unit
            checks['vat_formula_mismatch'] += vat != goods * Decimal('0.1')
            checks['total_formula_mismatch'] += total != goods + vat + fee
            warnings['catalog_transaction_price_difference'] += unit != decimal(product['Don_Gia_San_Pham'])
            for name, value in zip(('goods', 'vat', 'shipping_fee', 'total_paid'), (goods, vat, fee, total)):
                amounts[name] += value
            pack = stamp(when, 'Thoi_Gian_Dong_Goi', 'Gio_Dong_Goi')
            sent = stamp(when, 'Thoi_Gian_Giao_Hang', 'Gio_Giao_Hang')
            expected = stamp(when, 'Thoi_Gian_Du_Kien_Toi', 'Gio_Du_Kien_Toi')
            received = stamp(when, 'Thoi_Gian_Nhan_Hang', 'Gio_Nhan_Hang')
        except (ValueError, InvalidOperation, TypeError, KeyError):
            checks['invalid_numeric_or_timestamp_rows'] += 1
            continue
        warnings['sent_before_pack_timestamp'] += sent < pack
        warnings['expected_before_sent_timestamp'] += expected < sent
        checks['received_before_sent_timestamp'] += received < sent
        warnings['late_by_timestamp_unconfirmed_sla'] += received > expected
        warnings['late_by_date_unconfirmed_sla'] += received.date() > expected.date()
        warnings['order_location_differs_from_customer_profile'] += ship['Quan_Huyen'] != customer['Quan_Huyen'] or ship['Dia_Chi_Giao'] != customer['Dia_Chi_Giao']
        checks['shipping_type_copy_mismatch'] += order['Loai_Giao_Hang'] != when['Loai_Giao_Hang']
        for field in ('Kho_Xuat', 'Xe_Van_Chuyen', 'Tai_Xe'):
            checks[field + '_copy_mismatch'] += order[field] != ship[field]
        row = {'order_id': oid, 'pack': pack, 'sent': sent, 'expected': expected, 'received': received,
               'ship_hours': (received - sent).total_seconds() / 3600,
               'ship_calendar_days': (received.date() - sent.date()).days,
               'goods': goods, 'total': total, 'quantity': qty}
        moments.append(row)
        by_customer[order['Ma_Khach_Hang']].append(row)
        by_product[order['Ma_San_Pham']].append(row)
        by_type[order['Loai_Giao_Hang']].append(row)
        years[pack.year] += 1
        annual_customers[pack.year][order['Ma_Khach_Hang']] += 1
    for key, entries in by_customer.items():
        checks['customer_order_count_mismatch'] += decimal(customers[key]['So_Don_Hang']) != len(entries)
        checks['customer_total_paid_mismatch'] += decimal(customers[key]['Tong_Chi_Tieu']) != sum(e['total'] for e in entries)
    for key, entries in by_product.items():
        product = products[key]
        checks['product_order_count_mismatch'] += decimal(product['So_Don_Co_San_Pham']) != len(entries)
        checks['product_units_mismatch'] += decimal(product['Tong_So_Luong_Ban']) != sum(e['quantity'] for e in entries)
        checks['product_goods_mismatch'] += decimal(product['Tong_Doanh_Thu_Hang']) != sum(e['goods'] for e in entries)
    hard.update(dict(checks))
    report['warnings'] = dict(warnings)
    report['money_totals_vnd'] = {k: str(v) for k, v in amounts.items()}
    report['observed_grain'] = {'orders': len(orders), 'distinct_customers': len(by_customer),
                              'distinct_products': len(by_product), 'product_rows_per_order': 1,
                              'shipping_rows_per_order': 1, 'status_column_present': False}
    report['timestamp_ranges'] = {field: {'min': min(e[field] for e in moments).isoformat(),
                                        'max': max(e[field] for e in moments).isoformat()}
                                  for field in ('pack', 'sent', 'expected', 'received')} if moments else {}
    report['packing_year_order_counts'] = dict(sorted(years.items()))
    report['customer_frequency_distribution_all_history'] = dict(sorted(Counter(map(len, by_customer.values())).items()))
    report['annual_customer_activity'] = {str(year): {'customers': len(freq),
                         'one_order': sum(v == 1 for v in freq.values()),
                         'repeat_customers': sum(v > 1 for v in freq.values())}
                         for year, freq in sorted(annual_customers.items())}
    report['shipping_groups'] = {key: {'hours': describe([e['ship_hours'] for e in entries]),
                       'calendar_day_distribution': dict(sorted(Counter(e['ship_calendar_days'] for e in entries).items()))}
                       for key, entries in sorted(by_type.items())}
    news_path = source / 'news_seed/media_api_2024.csv'
    with news_path.open(encoding='utf-8-sig', newline='') as handle:
        news = list(csv.DictReader(handle))
    report['source_sha256'][news_path.name] = hashlib.sha256(news_path.read_bytes()).hexdigest()
    articles = [record_from(row) for row in news]
    valid = [a for a in articles if a]
    report['news'] = {'rows': len(news), 'valid': len(valid),
                      'unique_article_keys': len({a['article_key'] for a in valid}),
                      'levels_from_existing_rules': dict(Counter(a['relevance_level'] for a in valid)),
                      'category_assignments': dict(Counter(c for a in valid for c in a['category_codes'])),
                      'published_date_min': min(a['published_date'] for a in valid).isoformat() if valid else None,
                      'published_date_max': max(a['published_date'] for a in valid).isoformat() if valid else None,
                      'manually_labeled_accuracy_available': False,
                      'missing_by_column': {key: sum(row.get(key) is None or row.get(key) == '' for row in news) for key in (news[0] if news else {})}}
    report['passed'] = not any(hard.values())
    return report


def dictionary_markdown(report):
    lines = ['# Từ điển dữ liệu LAK', '',
             'Sinh từ sáu Excel nguồn. Không đưa giá trị tên, điện thoại hoặc địa chỉ vào tài liệu.', '',
             'Ngày trong XLSX lưu bằng serial; giờ lưu bằng phần thập phân của một ngày.',
             'Script ghép ngày và giờ, làm tròn đến giây. Tiền tính bằng Decimal, đơn vị VND.', '']
    for prefix, table in report['tables'].items():
        lines += [f"## {table['filename']}", '', f"Số dòng: {table['rows']}. Khóa: `{table['key']}`.", '',
                  '| Cột | Ý nghĩa | Thiếu | Tỷ lệ thiếu | Số giá trị khác nhau |',
                  '| --- | --- | ---: | ---: | ---: |']
        for col, info in table['columns'].items():
            lines.append(f"| {col} | {info['meaning']} | {info['missing']} | {info['missing_percent']}% | {info['distinct_nonmissing']} |")
        lines.append('')
    lines += ['## media_api_2024.csv', '',
              'Nguồn tin mẫu; giá trị lưu dạng chuỗi CSV. Không phải lịch sử thu thập đủ sáu năm.', '',
              '| Cột | Ý nghĩa |', '| --- | --- |',
              '| id | Định danh từ nguồn tin; khác khóa canonical article của pipeline |',
              '| indexed_date | Thời điểm nguồn lập chỉ mục, có timezone trong chuỗi |',
              '| language | Ngôn ngữ bài theo metadata |',
              '| media_name | Tên hoặc nhãn nguồn báo |',
              '| media_url | Địa chỉ/domain nguồn báo |',
              '| publish_date | Ngày xuất bản theo metadata; không phải ngày thu thập |',
              '| title | Tiêu đề, đầu vào của bộ luật liên quan |',
              '| url | URL bài gốc; chuẩn hóa trước khi định danh |',
              '| topic | Nhãn chủ đề trong tệp seed, chưa phải nhãn ML chuẩn |',
              '| query | Truy vấn thu thập được ghi trong seed |', '']
    return '\n'.join(lines) + '\n'


def summary_markdown(report):
    lines = ['# Kết quả kiểm tra dữ liệu LAK', '',
             f"Thời điểm UTC: {report['checked_at_utc']}", '',
             'Kết quả chỉ xác nhận dữ liệu và quy tắc kiểm tra được liệt kê; không chứng minh CDC, ML hoặc Docker đã chạy.', '',
             f"Kiểm tra bắt buộc: {'ĐẠT' if report['passed'] else 'KHÔNG ĐẠT'}.", '',
             '## Lỗi bắt buộc', '', '| Quy tắc | Số trường hợp |', '| --- | ---: |']
    lines += [f'| {key} | {value} |' for key, value in report['hard_errors'].items()]
    lines += ['', '## Cảnh báo và quan sát', '', '| Quy tắc | Số trường hợp |', '| --- | ---: |']
    lines += [f'| {key} | {value} |' for key, value in report['warnings'].items()]
    lines += ['', 'Cảnh báo địa chỉ khác nhau không mặc định là lỗi. Tỷ lệ trễ chưa được dùng làm KPI SLA.', '',
              'Các phân bố, tổng tiền, độ phủ tin và dấu vân tay nguồn nằm trong profile.json.',
              'Kiểm tra nguồn gốc/giấy phép và chất lượng nhãn tin cần bằng chứng bổ sung ngoài script.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        parser.error('Python 3.11 or later is required')
    source = args.data_dir.resolve()
    output = args.output_dir or ROOT / 'evidence/phase1' / ('run-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    try:
        report = analyze(source)
    except Exception as exc:
        report = {'phase': 1, 'passed': False, 'error_type': type(exc).__name__,
                  'message': 'Profile could not complete. Check source structure, types and required columns.'}
        (output / 'profile.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'PHASE 1 PROFILE FAILED: {type(exc).__name__}; see {output / "profile.json"}')
        return 1
    (output / 'profile.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (output / 'data_dictionary.md').write_text(dictionary_markdown(report), encoding='utf-8')
    (output / 'profile.md').write_text(summary_markdown(report), encoding='utf-8')
    print(f"Orders: {report['tables']['01']['rows']}; customers: {report['tables']['02']['rows']}; products: {report['tables']['03']['rows']}")
    for key, value in report['warnings'].items():
        if value:
            print(f'OBSERVATION {key}: {value}')
    print(f'Evidence: {output}')
    print('PHASE 1 DATA CHECKS PASSED WITH OBSERVATIONS' if report['passed'] else 'PHASE 1 DATA CHECKS FAILED')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
