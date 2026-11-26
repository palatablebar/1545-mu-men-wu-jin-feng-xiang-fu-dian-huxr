from math import exp, log, fsum, sqrt
from statistics import median, mean, quantiles

from .medoids_model import score_kernel
from .medoids_model import l1


def explain_hardware_medoids(fit, calibration, replay, live):
    medoids, scale = fit.parameters
    populations = [[] for _ in medoids]
    example = {group: [] for group in range(len(medoids))}
    for box in live:
        index = min(range(len(medoids)),key=lambda i:(l1(box.values,medoids[i]),i))
        precision = l1(box.values,medoids[index])
        example[index].append((precision,box.key))
        populations[index].append(box.input_values[1] - box.input_values[0] + box.input_values[-1])
    rows = []
    for group, examples in example.items():
        if not examples:
            continue
        closest = min(examples)
        outermost = max(examples)
        rows.append({'箱型簇':group+1,'当班箱单':len(examples),'代表箱':closest[1],'最远纸箱':outermost[1],
                     '最远距离比':round(outermost[0]/scale,3),'缺件中位':median(populations[group])})
    return rows
