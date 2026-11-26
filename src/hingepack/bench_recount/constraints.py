from collections import Counter, defaultdict
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


def apply_bench_recount(boxes, admit: Callable, wait: Callable):
    recount_load = Counter()
    # Heavy custom kits consume the same bench group even across box types.
    for box in sorted(boxes, key=lambda item: (-bool(item.job.rule_hits), item.assessment.raw.input_values[2] >= 3300, -item.job.priority, item.job.key)):
        scans, expected, weight, variant, reissue, duplicated = box.assessment.raw.input_values
        if (scans - duplicated) > expected + 9 and reissue == 0:
            wait(box, 'TAG_DISPUTE', '需核对重复入仓标签')
            continue
        station = '重箱复点' if weight >= 3300 or variant >= 7 else box.job.cohort
        if recount_load[station] >= 3 and variant >= 4:
            wait(box, 'CUSTOM_KIT_BENCH_FULL', '非标件操作台暂满')
        elif admit(box):
            recount_load[station] += 1
