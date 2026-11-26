from dataclasses import replace
from statistics import median

from .contracts import KitVectors, Proposal


def measure_kit_vectors(values) -> KitVectors:
    scan_count, expected, mass_g, variant, partial, scan_repeat = values
    return KitVectors(
        credible_scans=scan_count-min(scan_repeat,scan_count),
        extra_tags=scan_count-min(scan_repeat,scan_count)-expected,
        expected_gap=max(0,expected-scan_count+scan_repeat),
        weight_share=mass_g/max(1,variant+1),
        repair_by_item=partial/expected,
        redundant_rate=min(scan_repeat,scan_count)/scan_count,
        remaining_kit=max(0,expected-variant),
        warehouse_pressure=mass_g*(1+partial/10)/1000,
    )


def propose_bench_recount(values, missing=()):
    scan_count, expected, mass_g, variant, partial, scan_repeat = values
    if 'scan_repeat' not in missing and (scan_repeat>=2):
        yield Proposal('核销两张重复条码', 'scan_repeat', scan_repeat, max(0,scan_repeat-2), 1)
    if 'scan_count' not in missing and (scan_count<=33 and scan_count-scan_repeat<expected):
        yield Proposal('补扫三件', 'scan_count', scan_count, min(36,scan_count+3), 1)
    if 'partial' not in missing and (partial>=2):
        yield Proposal('清结补领', 'partial', partial, max(0,partial-2), 2)
    if 'mass_g' not in missing and (mass_g>=370):
        yield Proposal('重新去皮后称量', 'mass_g', mass_g, max(150,mass_g-220), 2)
