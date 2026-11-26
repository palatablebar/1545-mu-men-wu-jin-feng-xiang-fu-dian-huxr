from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable

from .contracts import Job


@dataclass(frozen=True, slots=True)
class WorkOrder:
    job: Job
    assessment: Any

    def __post_init__(self):
        if self.job.key != self.assessment.raw.key:
            raise ValueError('处置工位与单据不匹配')


def order_values(box):
    """Return the six readings for a WorkOrder or a lightweight job adapter."""
    return tuple(box.assessment.raw.input_values)


def station_for_values(values, cohort):
    _scans, _expected, weight, variant, _reissue, _duplicated = values
    # Heavy custom kits consume the same bench group even across box types.
    return '重箱复点' if weight >= 3300 or variant >= 7 else cohort


def station_for_order(box):
    values = order_values(box)
    return station_for_values(values, box.job.cohort)


def has_tag_dispute(values):
    scans, expected, _weight, _variant, reissue, duplicated = values
    return (scans - duplicated) > expected + 9 and reissue == 0


class BenchGate:
    """Physical bench occupancy; one admitted ticket consumes one bench slot."""

    def __init__(self, load=None):
        self.load = Counter(load or ())

    def station(self, box):
        return station_for_order(box)

    def rejected(self, box):
        _scans, _expected, _weight, variant, _reissue, _duplicated = order_values(box)
        station = self.station(box)
        return self.load[station] >= 3 and variant >= 4

    def admit(self, box):
        self.load[self.station(box)] += 1
        return True


def apply_bench_recount(boxes, admit: Callable, wait: Callable):
    recount_load = Counter()
    gate = BenchGate(recount_load)
    for box in sorted(boxes, key=lambda item: (-bool(item.job.rule_hits), item.assessment.raw.input_values[2] >= 3300, -item.job.priority, item.job.key)):
        values = order_values(box)
        if has_tag_dispute(values):
            wait(box, 'TAG_DISPUTE', '需核对重复入仓标签')
            continue
        station = gate.station(box)
        _scans, _expected, _weight, variant, _reissue, _duplicated = values
        if gate.rejected(box):
            wait(box, 'CUSTOM_KIT_BENCH_FULL', '非标件操作台暂满')
        elif admit(box):
            gate.admit(box)
