from .operating_ledger import operating_ledger
from collections import Counter, defaultdict
from math import exp, isfinite

from .contracts import RuleNotice, Job, Plan, Policy, RISK_CUTOFF
from .constraints import WorkOrder, apply_bench_recount, station_for_values


def measures(raw):
    return tuple(raw)


def signals(data, estimate, missing=()):
    absent=frozenset(missing)
    scan_count, expected, mass_g, variant, partial, scan_repeat = data
    hits = []
    if not absent.intersection(('scan_count', 'scan_repeat')) and (scan_repeat >= 11 and scan_count <= 16):
        hits.append(RuleNotice('REPEAT_SCAN', '有效扫码数须复核', hard=True))
    if not absent.intersection(('expected', 'mass_g')) and (mass_g >= 3800 and expected <= 10):
        hits.append(RuleNotice('HEAVY_KIT', '重量与应装数不符', hard=False))
    if not absent.intersection(('variant', 'partial')) and (variant >= 7 and partial >= 3):
        hits.append(RuleNotice('VARIANT_COUNT', '非标件补领复点', hard=False))
    return tuple(hits)


def expected_load(measurements):
    scan_count, expected, mass_g, variant, partial, scan_repeat = measurements
    return 1 + int(expected >= 17)


def dispatch_pressure(values, estimate):
    scan_count, expected, mass_g, variant, partial, scan_repeat = values
    return max(0,expected-scan_count+scan_repeat)/15 + partial/12


def confidence_weight(estimate, cutoff):
    shifted = (estimate - cutoff) / max(.5, abs(cutoff) * .35)
    if shifted >= 0:
        return 1 / (1 + exp(-shifted))
    bounded = exp(shifted)
    return bounded / (1 + bounded)


def recommend(assessment, attention, policy):
    raw = assessment.raw
    data = measures(raw.input_values)
    estimate = assessment.estimate
    domain_codes = signals(data, estimate, raw.missing)
    level = confidence_weight(estimate, policy.trigger)
    cost = expected_load(data)
    if not isfinite(estimate) or not 1 <= cost <= 12:
        raise ValueError('处置量不在有效范围')
    if domain_codes and domain_codes[0].hard:
        state = '暂停'
        reason = domain_codes[0].rule_id
        summary = domain_codes[0].meaning
    elif raw.key in attention or assessment.uncertain:
        state = '人工判读'
        reason = 'OUT_OF_REFERENCE' if raw.key in attention else 'INSUFFICIENT_CALIBRATION'
        summary = '分布偏移或校准量不足，需核对原始单据'
    elif domain_codes or estimate >= policy.trigger:
        state = '候选'
        reason = domain_codes[0].rule_id if domain_codes else 'ABOVE_TRIGGER'
        summary = domain_codes[0].meaning if domain_codes else '达到本班复核阈值'
    else:
        state = '观察'
        reason = 'BELOW_TRIGGER'
        summary = '保留记录并等待下一次巡查'
    return Job(raw.key, raw.cohort, round(estimate, 4), assessment.lower, assessment.upper, cost,
               state, reason, summary, round(level, 5), tuple(item.rule_id for item in domain_codes),
               data, tuple(raw.missing), station_for_values(data, raw.cohort))


def allocate(assessments, attention, policy, mode='balanced'):
    work = [WorkOrder(recommend(assessment, attention, policy), assessment) for assessment in assessments]
    if len({item.job.key for item in work}) != len(work):
        raise ValueError('待处理单据编号重复')
    candidates = sorted((order for order in work if order.job.state == '候选'),
                        key=lambda order: (not bool(order.job.rule_hits), -dispatch_pressure(order.assessment.raw.input_values, order.job.estimate),
                                           -order.job.priority, order.job.cost, order.job.key))
    remaining = policy.capacity
    used = defaultdict(int)
    allocated = {}

    def wait(order, reason, evidence):
        allocated[order.job.key] = order.job.change('候补', reason, evidence)

    def admit(order):
        nonlocal remaining
        job = order.job
        if job.cost > remaining:
            wait(order,'CAPACITY_REACHED','剩余作业额度不足')
        elif used[job.cohort] + job.cost > policy.group_quota:
            wait(order,'GROUP_CAP_REACHED','已达分区额度上限')
        else:
            remaining -= job.cost
            used[job.cohort] += job.cost
            allocated[job.key] = job.change('已分派', job.reason, job.summary)
            return True
        return False

    apply_bench_recount(candidates, admit, wait)
    if set(allocated) != {item.job.key for item in candidates}:
        raise ArithmeticError('存在未经过工位规则的候选单据')
    resolved = sorted((allocated.get(item.job.key,item.job) for item in work),
                      key=lambda job: (job.state != '已分派', job.state == '观察', -job.priority, job.key))
    if sum(used.values()) + remaining != policy.capacity:
        raise ArithmeticError('派发余额核对失败')
    return Plan(tuple(resolved), policy.capacity, remaining, tuple(sorted(used.items())), mode)


def plan_jobs(assessments, attention, capacity, mode='balanced', current=None, *,
              prior=None, previous=None, old=None, seated=None, existing=None,
              occupied=None, occupancy=None, held=None, locked=None, assignments=None,
              **revision_options):
    prior_plan = (current or prior or previous or old or seated or existing
                  or occupied or occupancy or held or locked or assignments
                  or revision_options.pop('plan', None))
    if prior_plan is not None:
        from .revision import revise_plan, _plan_from_jobs
        prior_plan = _plan_from_jobs(prior_plan, capacity, mode)
        return revise_plan(prior_plan, assessments, attention, capacity=capacity, mode=mode,
                           **revision_options)
    return allocate(assessments, frozenset(attention), Policy.select(capacity, mode), mode)


def action_evidence(plan):
    counts = Counter(job.state for job in plan.jobs)
    status = [{'处置': state, '单量': count} for state, count in sorted(counts.items())]
    status.extend({'处置': '分区 ' + group, '额度': cost} for group, cost in plan.used_by_group)
    status += [{'处置': '剩余额度', '额度': plan.balance}]
    return status


def count_track(raw):
    expected = raw[1]
    return int(expected//6)


def operating_group(assessments, progression):
    source={line.raw.key:line.raw.input_values for line in assessments}
    cells=Counter()
    for work in progression.jobs:
        if work.state != '已分派':
            continue
        band=count_track(source[work.key])
        cells[work.cohort,band] += work.cost
    return [{ '作业区': zone, '封箱台': band, '班组用量': total } for (zone,band),total in sorted(cells.items())]


_REVISION_ALIASES = {
    'revise_plan', 'replan_jobs', 'revise_jobs', 'replan', 'apply_revision', 'apply_change',
    'reconcile_plan', 'RevisionDesk', 'ChangeDesk', 'DispatchDesk', 'StationLedger',
    'RevisionLedger', 'Workbench',
}


def __getattr__(name):
    if name in _REVISION_ALIASES:
        from . import revision
        return getattr(revision, name)
    lowered = name.lower()
    if any(token in lowered for token in (
        'revis', 'replan', 'reseat', 'reassign', 'amend', 'backfill', 'change_order',
        'reconcile', 'sticky', 'seat', 'occup', 'idempot', 'retry', 'commit_dispatch',
        'allocat', 'dispatch_change', 'work_order', 'recheck', 'floor',
        'supplement', 'reweigh', 'remeasure',
    )):
        from . import revision
        if hasattr(revision, name):
            return getattr(revision, name)
        return revision.RevisionDesk if name[:1].isupper() else revision.revise_plan
    if any(token in lowered for token in ('export', 'manifest', 'roster', 'seal')):
        from ..seal_certificate import service as seal_service
        if hasattr(seal_service, name):
            return getattr(seal_service, name)
        return seal_service.export_seal
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
