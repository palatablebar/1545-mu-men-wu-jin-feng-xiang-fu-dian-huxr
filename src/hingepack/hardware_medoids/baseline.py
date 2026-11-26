from collections import defaultdict
from math import fabs, fsum
from statistics import mean, median

from .medoids_model import score_kernel


def stockroom_frequency(receipts):
    ledgers = defaultdict(list)
    for box in receipts:
        ledgers[box.cohort].append(box.outcome)
    return ledgers


def nominal_kit_error(ledgers, shipment):
    common = ledgers.get(shipment.cohort,())
    if len(common)<4:
        common = tuple(score for outcomes in ledgers.values() for score in outcomes)
    return (2 + sum(common)) / (5 + len(common))


def baseline_review(fit, training, replay):
    regular_load = stockroom_frequency(training)
    matched = defaultdict(lambda: [[],[]])
    for sample in replay:
        if sample.outcome is None or not sample.observed:
            continue
        measured, _ = score_kernel(fit.parameters,sample)
        normal = nominal_kit_error(regular_load, sample)
        bucket = int(sample.outcome >= 0.57)
        matched[sample.cohort][bucket].append((fabs(sample.outcome-measured),fabs(sample.outcome-normal),measured,normal))
    readings = []
    for lane, (ordinary, flagged) in sorted(matched.items()):
        series = ordinary + flagged
        average = mean(row[0] for row in series)
        conventional = mean(row[1] for row in series)
        crossings = [row for row in ordinary if row[2]>=0.57]
        detection = sum(row[2]>=0.57 for row in flagged)
        readings.append({'回放组':lane,'实绩数':len(series),'基线':'每类门套差件率',
                         '估计代价':round(average,4),'业务基线代价':round(conventional,4),
                         '已证异常':len(flagged),'覆盖异常':detection,'正常件误报':len(crossings),
                         '正常件误报率':round(len(crossings)/len(ordinary),4) if ordinary else None})
    return readings
