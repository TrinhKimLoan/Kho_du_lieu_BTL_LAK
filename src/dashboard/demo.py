import re
from src.source.runtime import connect
from src.source.demo import action


def validate_suffix(suffix):
    if not isinstance(suffix,str) or not re.fullmatch(r'WEB11_[0-9a-f]{10}',suffix):raise ValueError('Chỉ thao tác phiên demo website hợp lệ.')
    return suffix


def perform(suffix,command):
    validate_suffix(suffix)
    if command not in ('insert','update','delete','status'):raise ValueError('Thao tác demo không hợp lệ.')
    with connect() as connection:return action(connection,command,suffix)
