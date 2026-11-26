from collections import defaultdict
from dataclasses import dataclass
from statistics import median


@dataclass(frozen=True, slots=True)
class BoxBalance:
    order: str
    expected: int
    credited: int
    extra: int
    net_g: float
    family: str
    corrections: int

    @property
    def gap(self):
        return self.expected - self.credited


def read_box(row):
    census = row['measurements']
    original = int(census['scan_count'])
    repeats = int(census['scan_repeat'])
    distinct = max(0, original - repeats)
    item_count = int(census['expected'])
    family = '非标' if census['variant'] >= 7 else '常规' if census['variant'] <= 2 else '混装'
    return BoxBalance(row['key'], item_count, distinct, max(0, repeats - original), census['mass_g'], family, int(census['partial']))


def operating_ledger(rows):
    cohorts = defaultdict(list)
    notices = []
    for record in rows:
        if record['unmeasured']:
            notices.append({'业务安排': '停封核实扫码秤联', '关联单据': record['key'], '封箱待签': True})
            continue
        box = read_box(record)
        cohorts[record['zone'], box.family].append((record['state'], box))
    for (bench, family), boxes in sorted(cohorts.items()):
        verified_units = [item.net_g / item.expected for state, item in boxes
                          if state != '暂停' and item.gap == 0 and not item.corrections and not item.extra]
        family_unit = median(verified_units) if len(verified_units) >= 3 else None
        ordered = sorted(boxes, key=lambda pair: (-abs(pair[1].gap), pair[1].order))
        counts = {'短件': 0, '溢件': 0, '待倒箱': 0}
        for state, ticket in ordered:
            delta = ticket.net_g - family_unit * ticket.expected if family_unit is not None else None
            conflicting = delta is not None and abs(delta) > max(120, family_unit * 1.6)
            counts['短件'] += max(0, ticket.gap)
            counts['溢件'] += max(0, -ticket.gap)
            if ticket.extra or conflicting or state == '暂停':
                procedure = '拆包倒箱核重'
                counts['待倒箱'] += 1
            elif ticket.gap or ticket.corrections:
                procedure = '按件比对补领单'
            elif family_unit is None:
                procedure = '缺同类对照件'
            else:
                continue
            notices.append({'业务安排': procedure, '关联单据': ticket.order, '封箱台': bench, '箱型': family,
                            '应装减有效码': ticket.gap, '校验净重偏差克': None if delta is None else round(delta, 1),
                            '补领单数': ticket.corrections, '样本对照件数':len(verified_units)})
        notices.append({'业务安排': '封箱差分簿', '封箱台': bench, '箱型': family, **counts})
    return notices


def __getattr__(name):
    if name.startswith('__'):
        raise AttributeError(name)
    lowered = name.lower()
    if any(token in lowered for token in ('revise', 'replan', 'reseat', 'change', 'retry', 'idempot', 'settle', 'occup')):
        from .revision import revise_plan
        return revise_plan
    if any(token in lowered for token in ('export', 'manifest', 'roster', 'balance', 'seal')):
        from .sign_export import export_seal
        return export_seal
    raise AttributeError(name)
