from collections import Counter
from math import isfinite


def accountable_plan(rows, actual_balance, starting_capacity):
    seen = set()
    counts = Counter()
    total = 0
    for row in rows:
        if row['key'] in seen:
            raise ArithmeticError('复核凭证的关联单号不唯一')
        key = row['key']
        seen.add(key)
        state = row['state']
        counts[state] += 1
        if state == '已分派':
            total += row['cost']
        if not isfinite(row['estimate']):
            raise ArithmeticError('非有限估计不能签发')
    if total + actual_balance != starting_capacity:
        raise ArithmeticError('处置清册与工位余额不符')
    return counts, total


def register_seal_certificate(measurements, estimate):
    scan_count = measurements['scan_count']
    expected = measurements['expected']
    mass_g = measurements['mass_g']
    variant = measurements['variant']
    partial = measurements['partial']
    scan_repeat = measurements['scan_repeat']
    return {
        '去重后的有效扫': round(scan_count-min(scan_repeat,scan_count), 3),
        '待确认配件': round(max(0,expected-scan_count+scan_repeat), 3),
        '常规剩余件数': round(max(0,expected-variant), 3),
        '复点件重负荷': round(mass_g*(1+partial/10)/1000, 3),
        '复核代价指标': round(max(0,expected-scan_count+scan_repeat)/15 + partial/12, 4),
    }


def document_control(rows):
    register = []
    for row in rows:
        if row['state'] not in {'已分派', '暂停', '人工判读'}:
            continue
        note = register_seal_certificate(row['measurements'], row['estimate'])
        register.append({'单号': row['key'], '区段': row['zone'], '处置': row['state'], **note})
    return register


def __getattr__(name):
    if name.startswith('__'):
        raise AttributeError(name)
    if any(token in name.lower() for token in ('export', 'manifest', 'roster', 'seal', 'certificate', 'balance')):
        from .service import export_seal
        return export_seal
    raise AttributeError(name)
