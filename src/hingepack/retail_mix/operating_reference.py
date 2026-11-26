from dataclasses import dataclass
from math import sqrt, fsum
from statistics import median


@dataclass(frozen=True, slots=True)
class DomainStudy:
    counts: tuple[int, int, int]
    rate: float | None
    midpoint: float | None
    expected: float | None
    drift: float | None

def retail_mix_domains(vectors):
    credible_scans = []
    extra_tags = []
    expected_gap = []
    weight_share = []
    repair_by_item = []
    redundant_rate = []
    remaining_kit = []
    warehouse_pressure = []
    for measurement in vectors:
        unobserved = frozenset(measurement.missing)
        scan_count, expected, mass_g, variant, partial, scan_repeat = measurement.input_values
        if unobserved.isdisjoint(('scan_count', 'partial', 'scan_repeat')):
            credible_scans.append((round(scan_count-min(scan_repeat,scan_count), 4), partial>=4))
        if unobserved.isdisjoint(('scan_count', 'expected', 'variant', 'scan_repeat')):
            extra_tags.append((round(scan_count-min(scan_repeat,scan_count)-expected, 4), variant<=1 and expected>=12))
        if unobserved.isdisjoint(('scan_count', 'expected', 'mass_g', 'scan_repeat')):
            expected_gap.append((round(max(0,expected-scan_count+scan_repeat), 4), mass_g/expected>240))
        if unobserved.isdisjoint(('mass_g', 'variant', 'scan_repeat')):
            weight_share.append((round(mass_g/max(1,variant+1), 4), scan_repeat>=6))
        if unobserved.isdisjoint(('scan_count', 'expected', 'partial', 'scan_repeat')):
            repair_by_item.append((round(partial/expected, 4), scan_count-scan_repeat<expected-6))
        if unobserved.isdisjoint(('scan_count', 'partial', 'scan_repeat')):
            redundant_rate.append((round(min(scan_repeat,scan_count)/scan_count, 4), partial>=4))
        if unobserved.isdisjoint(('expected', 'variant')):
            remaining_kit.append((round(max(0,expected-variant), 4), variant<=1 and expected>=12))
        if unobserved.isdisjoint(('expected', 'mass_g', 'partial')):
            warehouse_pressure.append((round(mass_g*(1+partial/10)/1000, 4), mass_g/expected>240))
    return {
        '去重后的有效扫 · 补领密集': tuple(credible_scans),
        '超额扫码 · 标准箱轻件': tuple(extra_tags),
        '待确认配件 · 称重超常': tuple(expected_gap),
        '非标件均摊重量 · 双次扫争议': tuple(weight_share),
        '补领单每件派生 · 有效扫少': tuple(repair_by_item),
        '重复扫密度 · 补领密集': tuple(redundant_rate),
        '常规剩余件数 · 标准箱轻件': tuple(remaining_kit),
        '复点件重负荷 · 称重超常': tuple(warehouse_pressure),
    }


def evaluate_domains(training, current):
    references = retail_mix_domains(training)
    activity = retail_mix_domains(current)
    diagnostics = []
    for domain, observed in activity.items():
        baseline = references.get(domain, ())
        study = characterize(baseline, observed)
        diagnostics.append({'观察维度': domain, '训练有效量': study.counts[0], '当班有效量': study.counts[1],
                            '越线量':study.counts[2], '越线比例':study.rate, '参考中位':study.midpoint,
                            '当班中位':study.expected, '相对训练变化':study.drift})
    return diagnostics


def characterize(before, after):
    history = tuple(value for value, _ in before)
    observed = tuple(value for value, _ in after)
    violating = sum(flag for _, flag in after)
    old = median(history) if history else None
    new = median(observed) if observed else None
    pct = round(violating / len(after), 4) if after else None
    movement = round(new - old, 4) if old is not None and new is not None else None
    return DomainStudy((len(before),len(after),violating),pct,old,new,movement)
