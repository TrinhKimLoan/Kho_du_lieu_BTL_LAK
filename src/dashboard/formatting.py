import csv
import io
from datetime import date,timedelta
from decimal import Decimal
from urllib.parse import urlsplit


def money(value):
    return f'{Decimal(str(value or 0)):,.0f}'.replace(',','.')+' ₫'


def compact_money(value):
    value=Decimal(str(value or 0))
    if abs(value)>=Decimal('1000000000'):return number(value/Decimal('1000000000'),2)+' tỷ ₫'
    if abs(value)>=Decimal('1000000'):return number(value/Decimal('1000000'),2)+' triệu ₫'
    return money(value)


def number(value,digits=0):
    if value is None:return '—'
    return f'{float(value):,.{digits}f}'.replace(',','_').replace('.',',').replace('_','.')


def period(start,end,categories=(),districts=()):
    if type(start) is not date or type(end) is not date or end<start:raise ValueError('Chọn khoảng ngày hợp lệ.')
    result={'start':start.isoformat(),'end':(end+timedelta(days=1)).isoformat()}
    if categories:result['categories']=list(categories)
    if districts:result['districts']=list(districts)
    return result


def safe_url(value):
    try:
        parsed=urlsplit(value or '')
        return value if parsed.scheme.lower() in ('http','https') and parsed.hostname and not parsed.username and not parsed.password else None
    except ValueError:return None


def csv_bytes(rows):
    if not rows:return b''
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
    def clean(value):
        if isinstance(value,str) and value.startswith(('=','+','-','@','\t','\r')):return "'"+value
        return value
    writer.writeheader();writer.writerows({k:clean(v) for k,v in r.items()} for r in rows)
    return stream.getvalue().encode('utf-8-sig')
