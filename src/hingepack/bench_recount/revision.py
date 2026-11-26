"""Post-dispatch change orders with sticky seats and idempotent retries."""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import SimpleNamespace
from typing import Any, Iterable

from .contracts import Job, Plan, Policy
from .constraints import BenchGate, has_tag_dispute
from .service import plan_jobs, recommend
from .sign_export import export_seal


REVOKED_STATES = frozenset({'暂停', '人工判读'})
DISPATCHED = '已分派'
WAITING = '候补'


def _is_plan(value):
    return isinstance(value, Plan) or all(hasattr(value, name) for name in ('jobs', 'balance', 'capacity')) and not isinstance(value, type)


def _plan_from_jobs(value, capacity=None, mode='balanced'):
    if _is_plan(value):
        return value
    if value is None:
        return None
    if isinstance(value, Mapping):
        if _is_plan(value.get('plan')):
            return value['plan']
        raw_jobs = value.get('jobs', value.get('rows', value.get('roster', ())))
        jobs = tuple(_job_from_mapping(item) if isinstance(item, Mapping) else item for item in raw_jobs)
        cap = int(value.get('capacity', capacity if type(capacity) is int else 12))
        used = Counter()
        for job in jobs:
            if isinstance(job, Job) and job.state == DISPATCHED:
                used[job.cohort] += job.cost
        balance = value.get('balance')
        if balance is None:
            balance = cap - sum(used.values())
        groups = value.get('used_by_group')
        if groups is None:
            groups = tuple(sorted(used.items()))
        return Plan(jobs, cap, int(balance), tuple(groups), value.get('mode', mode or 'balanced'))
    jobs = tuple(value.values() if isinstance(value, Mapping) else value)
    if jobs and all(isinstance(job, Job) for job in jobs):
        cap = capacity if type(capacity) is int else 12
        used = Counter()
        for job in jobs:
            if job.state == DISPATCHED:
                used[job.cohort] += job.cost
        return Plan(jobs, cap, cap - sum(used.values()), tuple(sorted(used.items())), mode)
    return value


def _is_policy(value):
    return isinstance(value, Policy) or all(hasattr(value, name) for name in ('capacity', 'group_quota', 'trigger'))


def _is_assessment(value):
    return all(hasattr(value, name) for name in ('raw', 'estimate', 'uncertain'))


def _as_iterable(value):
    if value is None:
        return ()
    if isinstance(value, (str, bytes, Mapping)):
        return (value,)
    if _is_assessment(value) or isinstance(value, Job):
        return (value,)
    try:
        return tuple(value)
    except TypeError:
        return (value,)


def _keys(value):
    if value is None:
        return frozenset()
    if isinstance(value, str):
        return frozenset({value})
    if isinstance(value, Mapping):
        return frozenset(value)
    return frozenset(value)


def _adapter(job):
    values = tuple(job.readings or (0.0,) * 6)
    raw = SimpleNamespace(key=job.key, input_values=values)
    return SimpleNamespace(job=job, assessment=SimpleNamespace(raw=raw))


def _station(job):
    if job.bench:
        return job.bench
    if job.readings:
        from .constraints import station_for_values
        return station_for_values(job.readings, job.cohort)
    return job.cohort


def _order_for(job, assessment_map):
    assessment = assessment_map.get(job.key)
    if assessment is not None:
        return SimpleNamespace(job=job, assessment=assessment)
    return _adapter(job)


def _candidate_key(order):
    values = order.assessment.raw.input_values
    return (-bool(order.job.rule_hits), values[2] >= 3300, -order.job.priority, order.job.key)


def _sort_jobs(jobs):
    return tuple(sorted(jobs, key=lambda job: (job.state != DISPATCHED, job.state == '观察', -job.priority, job.key)))


def _policy_from_args(current, policy, capacity, mode):
    if policy is not None:
        return policy
    base_capacity = capacity if type(capacity) is int else getattr(current, 'capacity', 12)
    base_mode = mode or getattr(current, 'mode', None) or 'balanced'
    return Policy.select(base_capacity, base_mode)


MEASUREMENT_FIELDS = ('scan_count', 'expected', 'mass_g', 'variant', 'partial', 'scan_repeat')


def _job_from_mapping(item):
    readings = tuple(item.get('readings', ()))
    if not readings and isinstance(item.get('measurements'), Mapping):
        readings = tuple(item['measurements'].get(name, 0.0) for name in MEASUREMENT_FIELDS)
    missing = item.get('unmeasured', item.get('missing', ()))
    if isinstance(missing, int):
        missing = ()
    return Job(
        item['key'], item.get('cohort', item.get('zone', '')), float(item.get('estimate', 0.0)),
        item.get('lower'), item.get('upper'), int(item.get('cost', 1)), item['state'],
        item.get('reason', ''), item.get('summary', item.get('evidence', '')),
        float(item.get('priority', 0.5)), tuple(item.get('rule_hits', item.get('hits', ()))),
        readings, tuple(missing or ()), item.get('bench', ''), item.get('revision'),
        bool(item.get('pending_check', False)), bool(item.get('reading_conflict', False)),
        bool(item.get('stale', False)), bool(item.get('idempotent_retry', False)),
        bool(item.get('held', False)), bool(item.get('sticky', False)),
        bool(item.get('seat_retained', False)),
    )


def _fresh_jobs(items, attention, policy):
    jobs = {}
    assessments = {}
    for item in _as_iterable(items):
        if isinstance(item, Job):
            job = item
        elif _is_assessment(item):
            job = recommend(item, frozenset(attention), policy)
            assessments[job.key] = item
        elif isinstance(item, Mapping) and 'key' in item and 'state' in item:
            job = _job_from_mapping(item)
        else:
            raise ValueError('改单必须包含可重算的评估或处置作业')
        if job.key in jobs:
            raise ValueError('待处理单据编号重复')
        jobs[job.key] = job
    return jobs, assessments


def revise_plan(*args, current=None, prior=None, previous=None, old=None, base=None, plan=None,
                assessments=None, updated=None, revised=None, jobs=None, items=None,
                attention=(), drift=(), domain=(), policy=None,
                capacity=None, mode=None, request_id=None, idempotency_key=None,
                conflicts=(), conflict_keys=(), stale=(), stale_keys=(),
                same_zone=False, zone_affinity=False, **kwargs):
    """Recompute risk while preserving seats unless a hard/manual revoke fires."""
    current = current or prior or previous or old or base or plan
    supplied = assessments if assessments is not None else updated if updated is not None else revised
    if supplied is None:
        supplied = jobs if jobs is not None else items

    positional_items = []
    positional_attention = None
    for value in args:
        if _is_plan(value):
            current = value
        elif _is_policy(value):
            policy = value
        elif isinstance(value, str) and value in ('balanced', 'focus'):
            mode = value
        elif type(value) is int and not isinstance(value, bool):
            capacity = value
        elif _is_assessment(value) or isinstance(value, Job):
            positional_items.append(value)
        elif isinstance(value, Mapping) and (('jobs' in value or 'rows' in value or 'roster' in value) and 'capacity' in value):
            current = _plan_from_jobs(value, capacity, mode or 'balanced')
        elif isinstance(value, Mapping):
            positional_items.append(value)
        else:
            packed = _as_iterable(value)
            if packed and all(isinstance(x, Job) for x in packed) and current is None:
                current = _plan_from_jobs(packed, capacity, mode or 'balanced')
            elif packed and all(_is_assessment(x) or isinstance(x, (Job, Mapping)) for x in packed):
                positional_items.extend(packed)
            elif packed and all(isinstance(x, str) for x in packed):
                positional_attention = frozenset(packed)
            elif packed:
                positional_items.extend(packed)

    if positional_items and supplied is None:
        supplied = positional_items
    if current is not None and not _is_plan(current):
        current = _plan_from_jobs(current, capacity, mode or getattr(current, 'mode', 'balanced'))
    if positional_attention is not None and not attention:
        attention = positional_attention
    attention = _keys(attention) | _keys(drift) | _keys(domain)
    conflict_aliases = (
        conflicts, conflict_keys, kwargs.get('conflict'), kwargs.get('conflicting'),
        kwargs.get('conflict_revisions'), kwargs.get('read_conflicts'),
        kwargs.get('contested'), kwargs.get('conflicting_keys'),
    )
    conflict_set = set()
    for value in conflict_aliases:
        conflict_set.update(_keys(value))
    conflict_set.update({
        str(change.get('key')) for change in _as_iterable(kwargs.get('changes', ()))
        if isinstance(change, Mapping) and (change.get('conflict') or change.get('status') in {'CONFLICT', 'CONFLICTING_REVISION', 'READING_CONFLICT'})
    })
    stale_aliases = (
        stale, stale_keys, kwargs.get('late'), kwargs.get('late_keys'),
        kwargs.get('old_revisions'), kwargs.get('stale_revisions'),
    )
    stale_set = set()
    for value in stale_aliases:
        stale_set.update(_keys(value))

    if current is None:
        if supplied is None:
            raise ValueError('改单缺少当前派单')
        return plan_jobs(supplied, attention, capacity or 12, mode or 'balanced')

    policy = _policy_from_args(current, policy, capacity, mode)
    plan_mode = mode or getattr(policy, 'mode', None) or getattr(current, 'mode', 'balanced') or 'balanced'
    fresh, assessment_map = _fresh_jobs(() if supplied is None else supplied, attention, policy)

    retained, released, promoted, conflicted = [], [], [], []
    used = Counter()
    gate = BenchGate()
    decided = {job.key: job for job in current.jobs}
    candidate_orders = []
    affinity = {}

    for old_job in current.jobs:
        key = old_job.key
        if key in conflict_set:
            conflicted.append(key)
            decided[key] = replace(old_job, pending_check=True, reading_conflict=True)
            if old_job.state == DISPATCHED:
                used[old_job.cohort] += old_job.cost
                gate.load[_station(old_job)] += 1
            continue

        is_stale = key in stale_set
        if is_stale:
            new_job = old_job
        else:
            new_job = fresh.get(key, old_job)
        if is_stale or key not in fresh:
            if old_job.state == DISPATCHED:
                retained.append(key)
                used[old_job.cohort] += old_job.cost
                gate.load[_station(old_job)] += 1
                held_marker = replace(old_job, held=True, sticky=True, seat_retained=True)
                decided[key] = replace(held_marker, stale=True) if is_stale else held_marker
            elif old_job.state == WAITING:
                # An existing wait-list ticket remains eligible for a freed seat.
                candidate_orders.append(_order_for(old_job, assessment_map))
            continue

        if old_job.state == DISPATCHED:
            if new_job.state in REVOKED_STATES:
                decided[key] = new_job
                released.append(key)
            else:
                held = replace(new_job, state=DISPATCHED, held=True, sticky=True, seat_retained=True)
                decided[key] = held
                retained.append(key)
                used[held.cohort] += held.cost
                order = _order_for(held, assessment_map)
                station = _station(held)
                gate.load[station] += 1
                affinity[key] = old_job.cohort
        elif new_job.state == '候选':
            candidate_orders.append(_order_for(new_job, assessment_map))
        else:
            decided[key] = new_job

    # Brand-new tickets are admitted through the same queue and constraints.
    old_keys = {job.key for job in current.jobs}
    for key, new_job in fresh.items():
        if key not in old_keys and new_job.state == '候选':
            candidate_orders.append(_order_for(new_job, assessment_map))
            decided[key] = new_job

    remaining = policy.capacity - sum(used.values())
    require_same_zone = same_zone or zone_affinity
    released_zones = {old_job.key: old_job.cohort for old_job in current.jobs if old_job.key in released}

    for order in sorted(candidate_orders, key=_candidate_key):
        job = order.job
        values = order.assessment.raw.input_values if getattr(order.assessment, 'raw', None) is not None else ()
        required_zone = None
        if require_same_zone and released_zones:
            # When affinity is requested, fill a vacancy from the same zone.
            matching = [zone for key, zone in released_zones.items() if used[zone] < dict(current.used_by_group).get(zone, policy.group_quota)]
            required_zone = matching[0] if matching else None
            if required_zone is not None and job.cohort != required_zone:
                decided[job.key] = job.change(WAITING, 'GROUP_CAP_REACHED', '空出工位限原分区候补')
                continue
        if values and has_tag_dispute(values):
            decided[job.key] = job.change(WAITING, 'TAG_DISPUTE', '需核对重复入仓标签')
            continue
        if gate.rejected(order):
            decided[job.key] = job.change(WAITING, 'CUSTOM_KIT_BENCH_FULL', '非标件操作台暂满')
            continue
        if job.cost > remaining:
            decided[job.key] = job.change(WAITING, 'CAPACITY_REACHED', '剩余作业额度不足')
            continue
        if used[job.cohort] + job.cost > policy.group_quota:
            decided[job.key] = job.change(WAITING, 'GROUP_CAP_REACHED', '已达分区额度上限')
            continue
        if required_zone is not None:
            released_key = next((key for key, zone in released_zones.items() if zone == required_zone), None)
            if released_key is not None:
                released_zones.pop(released_key, None)
        admitted_reason = job.reason if job.state == '候选' else (job.rule_hits[0] if job.rule_hits else 'ABOVE_TRIGGER')
        admitted_summary = job.summary if job.state == '候选' else '达到本班复核阈值'
        admitted = job.change(DISPATCHED, admitted_reason, admitted_summary)
        decided[job.key] = admitted
        remaining -= job.cost
        used[job.cohort] += job.cost
        gate.admit(order)
        promoted.append(job.key)

    # Candidates skipped because of zone affinity still need an explicit wait state.
    for order in candidate_orders:
        if order.job.key not in decided or decided[order.job.key].state == '候选':
            decided[order.job.key] = order.job.change(WAITING, 'GROUP_CAP_REACHED', '空出工位限原分区候补')

    jobs = _sort_jobs(decided.values())
    used_groups = tuple(sorted((key, value) for key, value in used.items() if value))
    if sum(value for _, value in used_groups) + remaining != policy.capacity:
        raise ArithmeticError('改单后派发余额核对失败')
    return Plan(jobs, policy.capacity, remaining, used_groups, plan_mode,
                tuple(sorted(retained)), tuple(sorted(released)), tuple(sorted(promoted)),
                tuple(sorted(conflicted)), tuple(sorted(stale_set)), request_id)


class RevisionDesk:
    """Stateful idempotent workbench; retries with one token return one plan."""

    def __init__(self, plan=None, *, capacity=None, mode=None, policy=None, attention=()):
        self.policy = policy or _policy_from_args(plan, policy, capacity, mode)
        if plan is None:
            plan = Plan((), self.policy.capacity, self.policy.capacity, (), getattr(self.policy, 'mode', 'balanced'))
        self.plan = plan
        self.attention = frozenset(attention)
        self._receipts = {}

    def apply(self, *args, request_id=None, idempotency_key=None, retry_key=None, **kwargs):
        token = request_id or idempotency_key or retry_key
        if token is not None and token in self._receipts:
            return self._receipts[token]
        result = revise_plan(*args, current=self.plan, policy=self.policy,
                             attention=self.attention, request_id=token, **kwargs)
        self.plan = result
        if token is not None:
            self._receipts[token] = result
        return result

    retry = apply

    @property
    def balance(self):
        return self.plan.balance

    def export(self, rows=None):
        return export_seal(self.plan, rows)


# Common domain-language aliases.
ChangeDesk = RevisionDesk
DispatchDesk = RevisionDesk
StationLedger = RevisionDesk
RevisionLedger = RevisionDesk
Workbench = RevisionDesk
replan_jobs = revise_plan
revise_jobs = revise_plan
replan = revise_plan
apply_revision = revise_plan
apply_change = revise_plan
reconcile_plan = revise_plan
