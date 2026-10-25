import time
import uuid
from src.source.data import prepare,FIELDS,canonical,fingerprint
from src.source.runtime import connect,insert_noop
from src.source.demo import action,demo_rows
from src.cdc.store import pg,epoch
from src.cdc.checks import wait_idle,wait_fact,history


def until(target,query,params,accept,seconds=120):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        row=target.execute(query,params).fetchone()
        if row and accept(row):return row
        time.sleep(0.5)
    raise RuntimeError('Timeout waiting for phase 5 dimension state')


def check():
    suffix='SCD5_'+uuid.uuid4().hex[:8]
    customer,product,order=demo_rows(suffix)
    second_id=order['order_id']+'_NEW'
    dataset=prepare();steps=[]
    with pg() as target,connect() as source:
        wait_idle(target,epoch(target));before=history(target,dataset)
        try:
            action(source,'insert',suffix)
            original=wait_fact(target,order['order_id'],2)
            old_key=original['product_key'];customer_key=original['customer_key']
            old_geo=target.execute('SELECT profile_geography_key FROM dw.dim_customer WHERE customer_key=%s',(customer_key,)).fetchone()['profile_geography_key']
            source.rollback();source.begin()
            with source.cursor() as cur:
                cur.execute("UPDATE products SET product_name=%s,category_code='SSD' WHERE product_id=%s AND is_demo=1",('LAK demo SSD version 2',product['product_id']))
                cur.execute("UPDATE customers SET profile_city=%s,profile_district=%s WHERE customer_id=%s AND is_demo=1",('Hà Nội','Cầu Giấy',customer['customer_id']))
            source.commit()
            current=until(target,'SELECT product_key FROM dw.dim_product WHERE product_id=%s AND is_current',(product['product_id'],),lambda r:r['product_key']!=old_key)
            customer_now=until(target,'SELECT customer_key,profile_geography_key FROM dw.dim_customer WHERE customer_id=%s',(customer['customer_id'],),lambda r:r['profile_geography_key']!=old_geo)
            if customer_now['customer_key']!=customer_key:raise RuntimeError('Type 1 customer created a new surrogate key')
            versions=target.execute('SELECT product_key,valid_from,valid_to,is_current,category_code FROM dw.dim_product WHERE product_id=%s ORDER BY valid_from',(product['product_id'],)).fetchall()
            if len(versions)!=2 or versions[0]['valid_to']!=versions[1]['valid_from'] or versions[0]['is_current'] or not versions[1]['is_current']:
                raise RuntimeError('SCD2 expected exactly two adjacent product versions')
            action(source,'update',suffix)
            retained=wait_fact(target,order['order_id'],3)
            if retained['product_key']!=old_key or retained['category_key']!=original['category_key']:
                raise RuntimeError('Existing fact lost its original product version/category')
            source.rollback();source.begin()
            with source.cursor() as cur:
                second=dict(order,order_id=second_id)
                insert_noop(cur,'orders',[second],FIELDS['orders'],'order_id')
            source.commit()
            newest=wait_fact(target,second_id,2)
            if newest['product_key']!=current['product_key'] or newest['category_key']==original['category_key']:
                raise RuntimeError('New order did not use current product version/category')
            source.rollback();source.begin()
            with source.cursor() as cur:
                cur.execute('UPDATE products SET catalog_unit_price=123456.00 WHERE product_id=%s AND is_demo=1',(product['product_id'],))
            source.commit()
            until(target,'SELECT catalog_unit_price FROM staging.products WHERE product_id=%s',(product['product_id'],),lambda r:str(r['catalog_unit_price'])=='123456.00')
            wait_idle(target,epoch(target))
            count=target.execute('SELECT count(*) n FROM dw.dim_product WHERE product_id=%s',(product['product_id'],)).fetchone()['n']
            if count!=2:raise RuntimeError('Catalog price unexpectedly created an SCD2 version')
            steps=['product name/category create adjacent SCD2 version','customer geography updates Type 1 with same key',
                   'existing order retains original version/category after update','new order uses current product version/category',
                   'catalog price is staging-only and does not create a dimension version']
        finally:
            source.rollback();source.begin()
            try:
                with source.cursor() as cur:cur.execute('DELETE FROM orders WHERE order_id=%s AND is_demo=1',(second_id,))
                source.commit()
            except Exception:
                source.rollback();raise
            finally:action(source,'delete',suffix)
        wait_idle(target,epoch(target));after=history(target,dataset)
        if before['fact_state_sha256']!=after['fact_state_sha256']:raise RuntimeError('Dimension demo changed historical fact state')
        return {'passed':True,'steps':steps,'historical_facts_unchanged':True,'product_id':product['product_id'],
                'source_demo_rows_removed':True,'old_product_key':old_key,'new_product_key':current['product_key']}
