def collect_duplicate_barcode(measures, missing, estimate):
    scan_count = measures['scan_count']
    scan_repeat = measures['scan_repeat']
    if not (scan_repeat>=4):
        return None
    value=scan_count-scan_repeat
    return {'现场复核':'去重扫码','可复查值':round(value,3),'单位':'条','归档要求':'从装箱单追回重复条码',
            '需补测':not set(missing).isdisjoint(('scan_count', 'scan_repeat'))}


def collect_kit_pickup(measures, missing, estimate):
    partial = measures['partial']
    if not (partial>=2):
        return None
    value=partial
    return {'现场复核':'补领单对账','可复查值':round(value,3),'单位':'张','归档要求':'旁证补领件已经入箱',
            '需补测':not set(missing).isdisjoint(('partial',))}


def collect_sample_mass(measures, missing, estimate):
    expected = measures['expected']
    mass_g = measures['mass_g']
    if not (mass_g/expected>=170):
        return None
    value=mass_g/expected
    return {'现场复核':'抽重','可复查值':round(value,3),'单位':'g/件','归档要求':'用空托盘扣皮后复称',
            '需补测':not set(missing).isdisjoint(('expected', 'mass_g'))}


def collect_nonstandard_component(measures, missing, estimate):
    variant = measures['variant']
    if not (variant>=4):
        return None
    value=variant
    return {'现场复核':'核对非标件','可复查值':round(value,3),'单位':'种','归档要求':'按项目门型核对五金套件',
            '需补测':not set(missing).isdisjoint(('variant',))}


def check_seal_certificate(records):
    guide = []
    for ticket in records:
        if ticket['state'] not in ('已分派','暂停','人工判读'):
            continue
        measures=ticket['measurements']
        absent=ticket['unmeasured']
        estimate=ticket['estimate']
        checks = (
            collect_duplicate_barcode(measures,absent,estimate),
            collect_kit_pickup(measures,absent,estimate),
            collect_sample_mass(measures,absent,estimate),
            collect_nonstandard_component(measures,absent,estimate),
        )
        required=tuple(check for check in checks if check is not None)
        if not required:
            continue
        review=ticket['key']
        for check in required:
            guide.append({'签收单':review,'作业区':ticket['zone'],'处置':ticket['state'],**check})
    return guide
