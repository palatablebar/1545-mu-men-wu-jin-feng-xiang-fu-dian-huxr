from math import exp, fsum
from statistics import median


def l1(left, right):
    return fsum(abs(a - b) for a, b in zip(left, right, strict=True))


def fit_kernel(rows):
    observed = [row for row in rows if row.outcome < .5] or list(rows)
    stock = tuple(sorted(observed, key=lambda item: item.key))
    distance_matrix = {(a.key, b.key): l1(a.values, b.values) for a in stock for b in stock}
    centres = [min(stock, key=lambda a: (sum(distance_matrix[a.key, b.key] for b in stock), a.key))]
    while len(centres) < min(3, len(stock)):
        remaining = (sample for sample in stock if sample not in centres)
        centres.append(min(remaining, key=lambda a: (-min(distance_matrix[a.key, b.key] for b in centres), a.key)))
    for iteration in range(12):
        clusters = {centre.key: [] for centre in centres}
        for sample in stock:
            winner = min(centres, key=lambda centre: (distance_matrix[sample.key, centre.key], centre.key))
            clusters[winner.key].append(sample)
        changed = []
        for centre in centres:
            nearby = clusters[centre.key]
            changed.append(min(nearby, key=lambda a: (sum(distance_matrix[a.key, b.key] for b in nearby), a.key)) if nearby else centre)
        if changed == centres:
            break
        centres = changed
    typical = [min(l1(record.values, centre.values) for centre in centres) for record in stock]
    scale = max(.2, median(typical))
    return (tuple(centre.values for centre in centres), scale), (('有效常态箱', len(stock)), ('簇心数', len(centres)), ('中位距离', scale))


def score_kernel(archive, sample):
    centres, scale = archive
    closest = min(centres, key=lambda candidate: (l1(candidate, sample.values), candidate))
    gaps = tuple(abs(actual - reference) for actual, reference in zip(sample.values, closest, strict=True))
    distance = sum(gaps) / scale
    score = -__import__('math').expm1(-max(0, distance - .7) / 2.3)
    return score, gaps
