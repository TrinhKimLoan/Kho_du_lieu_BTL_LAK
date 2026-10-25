from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import uuid

from .data import FIELDS
from .runtime import identity, insert_noop, reconcile


def demo_rows(suffix='MANUAL'):
    customer_id, product_id, order_id = ['DEMO_' + suffix + '_' + kind for kind in ('C','P','O')]
    customer = {'customer_id':customer_id,'gender':None,'profile_city':'TP Hồ Chí Minh',
                'profile_district':'Thủ Đức','is_demo':True}
    product = {'product_id':product_id,'product_name':'LAK demo RAM','product_group':'Linh kiện điện tử',
               'category_code':'RAM','catalog_unit_price':Decimal('100000.00'),'product_size_band':'Hàng ít','is_demo':True}
    order = {'order_id':order_id,'customer_id':customer_id,'product_id':product_id,'quantity':2,
        'transaction_unit_price':Decimal('100000.00'),'goods_amount':Decimal('200000.00'),
        'vat_amount':Decimal('20000.00'),'shipping_fee':Decimal('5000.00'),'total_paid':Decimal('225000.00'),
        'shipping_method':'Giao hàng nhanh','quantity_band':'Hàng ít','warehouse_name':'Kho demo LAK',
        'vehicle_type':'Xe máy','delivery_city':'TP Hồ Chí Minh','delivery_district':'Thủ Đức',
        'packed_at':datetime(2025,12,20,8),'dispatched_at':datetime(2025,12,21,9),
        'expected_at':datetime(2025,12,23,18),'received_at':None,'is_demo':True}
    return customer,product,order


def action(connection, name, suffix='MANUAL'):
    identity(connection)
    customer,product,order = demo_rows(suffix)
    connection.rollback()
    connection.begin()
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT * FROM orders WHERE order_id=%s FOR UPDATE',(order['order_id'],))
            existing = cursor.fetchone()
            if existing and not existing['is_demo']:
                raise RuntimeError('Refusing to mutate a historical order')
            if name == 'insert':
                if existing:
                    result = {'action':'insert','changed':False,'order_id':order['order_id'],'note':'Demo order already exists'}
                else:
                    for table,row,key in [('customers',customer,'customer_id'),('products',product,'product_id')]:
                        cursor.execute('SELECT is_demo FROM ' + table + ' WHERE ' + key + '=%s',(row[key],))
                        found=cursor.fetchone()
                        if found and not found['is_demo']:
                            raise RuntimeError('Reserved demo entity collides with historical data')
                        insert_noop(cursor,table,[row],FIELDS[table],key)
                    insert_noop(cursor,'orders',[order],FIELDS['orders'],'order_id')
                    result = {'action':'insert','changed':True,'order_id':order['order_id'],'quantity':2,'total_paid':'225000.00'}
            elif name == 'update':
                if not existing:
                    raise RuntimeError('Demo order is missing; run insert first')
                cursor.execute('UPDATE orders SET quantity=3,goods_amount=300000.00,vat_amount=30000.00,total_paid=335000.00,received_at=%s WHERE order_id=%s AND is_demo=1',
                    (datetime(2025,12,22,12),order['order_id']))
                result = {'action':'update','changed':cursor.rowcount > 0,'order_id':order['order_id'],'quantity':3,'total_paid':'335000.00'}
            elif name == 'delete':
                cursor.execute('DELETE FROM orders WHERE order_id=%s AND is_demo=1',(order['order_id'],))
                changed = cursor.rowcount > 0
                cursor.execute('DELETE FROM products WHERE product_id=%s AND is_demo=1 AND NOT EXISTS(SELECT 1 FROM orders WHERE orders.product_id=products.product_id)',(product['product_id'],))
                cursor.execute('DELETE FROM customers WHERE customer_id=%s AND is_demo=1 AND NOT EXISTS(SELECT 1 FROM orders WHERE orders.customer_id=customers.customer_id)',(customer['customer_id'],))
                result = {'action':'delete','changed':changed,'order_id':order['order_id']}
            elif name == 'status':
                result = {'action':'status','order_id':order['order_id'],'exists':bool(existing),
                    'quantity':existing['quantity'] if existing else None,
                    'total_paid':str(existing['total_paid']) if existing else None}
            else:
                raise ValueError('Unknown demo action')
        connection.commit()
        return result
    except Exception:
        connection.rollback()
        raise


def constraint_checks(connection):
    import pymysql
    identity(connection)
    customer,product,order = demo_rows('TEST_' + uuid.uuid4().hex[:8])
    passed=[]
    connection.rollback()
    connection.begin()
    try:
        with connection.cursor() as cursor:
            for table,row,key in [('customers',customer,'customer_id'),('products',product,'product_id'),('orders',order,'order_id')]:
                insert_noop(cursor,table,[row],FIELDS[table],key)
            cases = [
                ('wrong_total','UPDATE orders SET total_paid=1 WHERE order_id=%s',(order['order_id'],),3819),
                ('negative_quantity','UPDATE orders SET quantity=-1 WHERE order_id=%s',(order['order_id'],),3819),
                ('missing_customer','UPDATE orders SET customer_id=%s WHERE order_id=%s',('DEMO_NONEXISTENT',order['order_id']),1452),
                ('historical_namespace','UPDATE orders SET is_demo=0 WHERE order_id=%s',(order['order_id'],),3819),
            ]
            for label,sql,params,expected_errno in cases:
                cursor.execute('SAVEPOINT negative_case')
                try:
                    cursor.execute(sql,params)
                except pymysql.MySQLError as exc:
                    if exc.args[0] != expected_errno:
                        raise
                    passed.append(label)
                else:
                    raise RuntimeError('MySQL accepted invalid case: ' + label)
                finally:
                    cursor.execute('ROLLBACK TO SAVEPOINT negative_case')
    finally:
        connection.rollback()
    return {'constraint_checks_passed':passed,'fixtures_rolled_back':True}


def cycle(connection,dataset):
    suffix = 'CYCLE_' + uuid.uuid4().hex[:8]
    before = reconcile(connection,dataset)
    steps=[]
    try:
        for name in ('insert','update','delete'):
            steps.append(action(connection,name,suffix))
        status=action(connection,'status',suffix)
        if status['exists'] or not all(step['changed'] for step in steps):
            raise RuntimeError('Demo cycle did not perform all three mutations')
        after=reconcile(connection,dataset)
        if before['history_state_sha256'] != after['history_state_sha256']:
            raise RuntimeError('Historical source changed during demo')
        return {'steps':steps,'history_unchanged':True,'remaining_cycle_order':False,
                'history_state_sha256':after['history_state_sha256']}
    finally:
        connection.rollback()
        action(connection,'delete',suffix)
