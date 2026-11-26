from bisect import bisect_right
from collections import defaultdict
from math import fsum, isfinite, log, log1p

from .contracts import Verification, Assessment, CalibrationRow, ModelReport
from .slices import replay_slices


def clip_risk(number):
    return min(1-1e-12,max(1e-12,number))


def stable_loss(probability, outcome):
    clipped = clip_risk(probability)
    return -(log(clipped) if outcome==1 else log1p(-clipped))



def monotone_steps(rows):
    blocks = []
    for limit, errors, size in rows:
        blocks.append((limit,errors,size))
        while len(blocks)>1 and blocks[-2][1]/blocks[-2][2] > blocks[-1][1]/blocks[-1][2]:
            _, prior_bad, prior_stock = blocks[-2]
            cutoff, next_bad, next_stock = blocks[-1]
            blocks[-2:] = [(cutoff,prior_bad+next_bad,prior_stock+next_stock)]
    return tuple(box[0] for box in blocks),tuple(box[1]/box[2] for box in blocks)



def kit_risk_from_neighbors(checks):
    ranked = sorted(checks,key=lambda box:(box.score,box.key))
    width = max(2,len(ranked)//6)
    local = [ranked[start:start+width] for start in range(0,len(ranked),width)]
    histogram = [(chunk[-1].score, 1+sum(point.outcome for point in chunk), len(chunk)+2) for chunk in local]
    return monotone_steps(histogram)


def calibrated_kit_risk_from_neighbors(model, p):
    borders, rates = model
    box = min(bisect_right(borders,p),len(rates)-1)
    return rates[box]


def prepare_verification(pairs, *, coverage=.85):
    confirmed = []
    positive = 0
    for gate in pairs:
        target = gate.outcome
        if target is None or not gate.observed:
            continue
        if not isfinite(gate.score) or target not in {0,1}:
            raise ValueError('异常度复核需有已确认的正常或异常标签')
        confirmed.append(gate)
        positive += target==1
    n = len(confirmed)
    if n>=8 and 0<positive<n:
        conversion = kit_risk_from_neighbors(confirmed)
        return Verification('kit_risk_from_neighbors',conversion,n,positive)
    return Verification('sparse-risk',(),n,positive)


def check_point(scored, anchor):
    if not isfinite(scored.score):
        raise ValueError('异常离差分已失效')
    outrank = clip_risk(scored.score)
    provisional = not anchor.parameters
    matched = outrank if provisional else calibrated_kit_risk_from_neighbors(anchor.parameters,outrank)
    return Assessment(scored,matched,None,None,provisional)


def validate_predictions(scored, prepared):
    return tuple(map(lambda issue:check_point(issue,prepared),scored))


def reliability_rows(cases):
    consensus = [(0.,0,0) for _ in range(4)]
    boundaries = (.15,.4,.68)
    for forecast,observed in cases:
        i = bisect_right(boundaries,forecast)
        sum_forecast, total_positive, size = consensus[i]
        consensus[i] = sum_forecast+forecast,total_positive+observed,size+1
    return tuple(CalibrationRow(i,est/num if num else None,seen/num if num else None,num)
                 for i,(est,seen,num) in enumerate(consensus))


def performance(assessments):
    history = [(check.estimate,check.raw.outcome) for check in assessments if check.raw.observed and check.raw.outcome is not None]
    n = len(history)
    if not n:
        return ModelReport('NO_MATURE_RESULT',0,None,None,(),None)
    deviations = tuple(abs(estimated-confirmed) for estimated,confirmed in history)
    count = sum(outcome==1 for _,outcome in history)
    status = 'READY' if count else 'NO_POSITIVES'
    loss = fsum(stable_loss(*record) for record in history)
    return ModelReport(status,n,fsum(deviations)/n,loss/n,reliability_rows(history),count)


def calibration_evidence(report):
    segments = ('0–15%','15–40%','40–68%','68–100%')
    cards = [{'核验':report.status,'确认单量':report.count,'异常单量':report.auxiliary,
              '平均绝对残差':report.mae,'反常概率损失':report.error}]
    for span, group in zip(segments,report.buckets):
        cards.append({'异常概率区间':span,'样本数':group.count,'预测异常率':group.predicted,'实证异常率':group.observed})
    return cards


def sector_replay(checked, line):
    return replay_slices(checked,line)


def boundary_diagnostics(checks, threshold):
    joined = [row for row in checks if row.raw.observed and row.raw.outcome is not None]
    hit = sum(row.estimate>=threshold and row.raw.outcome==1 for row in joined)
    actual = sum(row.raw.outcome==1 for row in joined)
    forecast = sum(row.estimate>=threshold for row in joined)
    return {'临界判断':'五金件差错','实绩超线':actual,'估计超线':forecast,'额外复测':forecast-hit,'漏查':actual-hit,
            '优先队列命中率':hit/forecast if forecast else None,'已确认异常覆盖率':hit/actual if actual else None}
