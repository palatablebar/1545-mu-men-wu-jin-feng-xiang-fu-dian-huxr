from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class JointAction:
    case: str
    work_units: int
    notes: str
    changes: dict[str, tuple[float, float]]

    def evidence(self, old_value, new_value, extrapolates):
        return {'联动推演':self.case, '用量':self.work_units, '先决条件':self.notes,
                '原预测':round(old_value,4), '替换预测':round(new_value,4),
                '变化':round(new_value-old_value,4), '超训练域':bool(extrapolates),
                '联动量测':{item:{'原值':before,'替换值':after} for item,(before,after) in self.changes.items()}}


def simulate_reconcile_scan(readings, invalid):
    scan_count, scan_repeat = readings[0], readings[5]
    if invalid.intersection(('scan_count', 'scan_repeat')):
        return None
    if not (scan_repeat>=4 and scan_count>=8):
        return None
    scan_repeat_adjusted = scan_repeat-3
    scan_count_adjusted = scan_count-3
    inspected = {
        'scan_repeat': (scan_repeat, scan_repeat_adjusted),
        'scan_count': (scan_count, scan_count_adjusted),
    }
    if any(new != old for old,new in inspected.values()):
        return JointAction('扫码去重复点', 2, '先核销重复记录再计算有效数', inspected)
    return None


def simulate_recover_components(readings, invalid):
    scan_count, partial = readings[0], readings[4]
    if invalid.intersection(('scan_count', 'partial')):
        return None
    if not (partial>=2 and scan_count<=32):
        return None
    partial_adjusted = partial-2
    scan_count_adjusted = scan_count+3
    inspected = {
        'partial': (partial, partial_adjusted),
        'scan_count': (scan_count, scan_count_adjusted),
    }
    if any(new != old for old,new in inspected.values()):
        return JointAction('追回补领并重扫', 2, '复点新入箱补领包', inspected)
    return None


def simulate_retally_custom_kit(readings, invalid):
    mass_g, variant = readings[2], readings[3]
    if invalid.intersection(('mass_g', 'variant')):
        return None
    if not (mass_g>=575 and variant>=2):
        return None
    mass_g_adjusted = mass_g-350
    variant_adjusted = variant-1
    inspected = {
        'mass_g': (mass_g, mass_g_adjusted),
        'variant': (variant, variant_adjusted),
    }
    if any(new != old for old,new in inspected.values()):
        return JointAction('重称去皮复点异形件', 3, '去掉临时料盒后重扫异形件', inspected)
    return None


def simulate_split_variant_lot(readings, invalid):
    scan_count, expected, variant = readings[0], readings[1], readings[3]
    if invalid.intersection(('scan_count', 'expected', 'variant')):
        return None
    if not (expected>=13 and variant>=4 and scan_count>=9):
        return None
    expected_adjusted = expected-6
    variant_adjusted = variant-3
    scan_count_adjusted = scan_count-5
    inspected = {
        'expected': (expected, expected_adjusted),
        'variant': (variant, variant_adjusted),
        'scan_count': (scan_count, scan_count_adjusted),
    }
    if any(new != old for old,new in inspected.values()):
        return JointAction('拆分不同门型', 2, '拆到二次封箱台分别复点', inspected)
    return None


def simulate_confirm_bom(readings, invalid):
    expected, partial = readings[1], readings[4]
    if invalid.intersection(('expected', 'partial')):
        return None
    if not (expected>=10 and partial>=3):
        return None
    expected_adjusted = expected-2
    partial_adjusted = partial-2
    inspected = {
        'expected': (expected, expected_adjusted),
        'partial': (partial, partial_adjusted),
    }
    if any(new != old for old,new in inspected.values()):
        return JointAction('份数与补领并账', 1, '与申领员确认作废配件数', inspected)
    return None


def options(values, missing):
    measurements=tuple(values)
    unobserved=frozenset(missing)
    cases=(
        simulate_reconcile_scan(measurements, unobserved),
        simulate_recover_components(measurements, unobserved),
        simulate_retally_custom_kit(measurements, unobserved),
        simulate_split_variant_lot(measurements, unobserved),
        simulate_confirm_bom(measurements, unobserved),
    )
    return tuple(action for action in cases if action is not None)
