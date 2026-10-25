from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from app.core import product_cat, xlsx_rows
from scripts.profile_lak_data import analyze, decimal, stamp

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = json.loads((ROOT / 'docs/phase2/data_contract.json').read_text(encoding='utf-8'))
FIELDS = {name: entity['fields'] for name, entity in CONTRACT['source_entities'].items()}
KEYS = {name: entity['key'] for name, entity in CONTRACT['source_entities'].items()}
PERSONAL_FIELDS = {'Ten_Khach_Hang', 'SDT', 'Dia_Chi_Giao', 'Tai_Xe'}


def canonical(value):
    if isinstance(value, Decimal):
        return format(value.quantize(Decimal('0.01')), 'f')
    if isinstance(value, datetime):
        return value.isoformat(timespec='microseconds')
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, dict):
        return {k: canonical(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [canonical(v) for v in value]
    return value


def json_text(value):
    return json.dumps(canonical(value), sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def fingerprint(value):
    return hashlib.sha256(json_text(value).encode('utf-8')).hexdigest()


def table_digest(rows, fields, key):
    material = [{f: r[f] for f in fields} for r in sorted(rows, key=lambda r: r[key])]
    return fingerprint(material)


def provenance_payload(value):
    """Encode Excel floats explicitly so MySQL JSON cannot rewrite their digits."""
    if isinstance(value,float):
        if not math.isfinite(value):
            raise ValueError('Nonfinite Excel numeric value')
        return {'__lak_type__':'excel_float_repr','value':repr(value)}
    if isinstance(value,dict):
        return {k:provenance_payload(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):
        return [provenance_payload(v) for v in value]
    return value


def prepare(data_root=None):
    data_root = Path(data_root or ROOT / 'data')
    profile = analyze(data_root)
    if not profile['passed']:
        raise ValueError('Input data failed phase 1 checks; do not edit data to force import')
    tables, files, provenance = {}, [], []
    for prefix in ('01','02','03','04','05','06'):
        path = next((data_root / 'excel').glob(prefix + '*.xlsx'))
        rows = xlsx_rows(path)
        tables[prefix] = rows
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files.append({'file_name': path.name, 'file_sha256': digest, 'row_count': len(rows)})
        entity = 'customers' if prefix == '02' else 'products' if prefix == '03' else 'orders'
        key = 'Ma_Khach_Hang' if prefix == '02' else 'Ma_San_Pham' if prefix == '03' else 'Ma_Don'
        for number, row in enumerate(rows, 2):
            sanitized = provenance_payload({k: v for k, v in row.items() if k not in PERSONAL_FIELDS})
            provenance.append({'file_name': path.name, 'file_sha256': digest,
                'excel_row_number': number, 'entity_type': entity, 'entity_key': row[key],
                'sanitized_payload': json_text(sanitized), 'payload_sha256': fingerprint(sanitized),
                'redaction_version': 'lak-minimal-v2-float-repr'})
    customers = [{'customer_id': r['Ma_Khach_Hang'], 'gender': r['Gioi_Tinh'],
        'profile_city': r['Tinh_Thanh'], 'profile_district': r['Quan_Huyen'], 'is_demo': False}
        for r in tables['02']]
    products = [{'product_id': r['Ma_San_Pham'], 'product_name': r['Ten_Hang_Hoa'],
        'product_group': r['Loai_Hang'], 'category_code': product_cat(r['Ten_Hang_Hoa']),
        'catalog_unit_price': decimal(r['Don_Gia_San_Pham']),
        'product_size_band': r['Muc_Hang_Hoa'], 'is_demo': False} for r in tables['03']]
    timing = {r['Ma_Don']: r for r in tables['04']}
    payment = {r['Ma_Don']: r for r in tables['05']}
    shipping = {r['Ma_Don']: r for r in tables['06']}
    orders = []
    for row in tables['01']:
        oid = row['Ma_Don']
        pay, ship, when = payment[oid], shipping[oid], timing[oid]
        orders.append({'order_id': oid, 'customer_id': row['Ma_Khach_Hang'],
            'product_id': row['Ma_San_Pham'], 'quantity': int(row['So_Luong']),
            'transaction_unit_price': decimal(pay['Don_Gia_San_Pham']),
            'goods_amount': decimal(pay['Tong_Gia_Tri_Hang']), 'vat_amount': decimal(pay['VAT_10']),
            'shipping_fee': decimal(pay['Phi_Van_Chuyen']), 'total_paid': decimal(pay['Tong_Thanh_Toan']),
            'shipping_method': row['Loai_Giao_Hang'], 'quantity_band': row['Muc_Hang_Hoa'],
            'warehouse_name': ship['Kho_Xuat'], 'vehicle_type': ship['Xe_Van_Chuyen'],
            'delivery_city': ship['Tinh_Thanh'], 'delivery_district': ship['Quan_Huyen'],
            'packed_at': stamp(when, 'Thoi_Gian_Dong_Goi','Gio_Dong_Goi'),
            'dispatched_at': stamp(when,'Thoi_Gian_Giao_Hang','Gio_Giao_Hang'),
            'expected_at': stamp(when,'Thoi_Gian_Du_Kien_Toi','Gio_Du_Kien_Toi'),
            'received_at': stamp(when,'Thoi_Gian_Nhan_Hang','Gio_Nhan_Hang'), 'is_demo': False})
    result = {'customers': customers, 'products': products, 'orders': orders,
              'import_files': files, 'import_rows': provenance,
              'observations': profile['warnings'], 'money_totals_vnd': profile['money_totals_vnd']}
    result['digests'] = {name: table_digest(result[name], FIELDS[name], KEYS[name]) for name in FIELDS}
    return result
