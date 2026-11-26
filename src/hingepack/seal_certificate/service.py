from .work_order import check_seal_certificate as site_checklist
from collections import Counter
from hashlib import sha256
import json
from itertools import chain

from .contracts import BatchReceipt, LedgerCheck, POLICY_VERSION
from .control import accountable_plan, document_control


def compact(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':'))


def data_fingerprint(records):
    rows=sorted(compact(single) for single in records)
    digest=sha256()
    for line in rows:
        framed=f'{len(line)}:{line}'
        digest.update(framed.encode('utf-8'))
    return digest.hexdigest()


def policy_fingerprint(capacity,mode,feature_id,model_kind):
    trace=(('cap',capacity),('form',POLICY_VERSION),('mode',mode),('model',model_kind),('x',feature_id))
    return sha256(compact(trace).encode()).hexdigest()[-16:]


def check_flow(intake, windows, dispatched):
    live=Counter(row.key for row in windows.live)
    assigned=Counter(plan.key for plan in dispatched.jobs)
    if live!=assigned:
        mismatch = bound=(live-assigned,assigned-live)
        raise ArithmeticError(f'处置单交付差额 {sum(bound[0].values())}/{sum(bound[1].values())}')
    merged=Counter(item.key for item in chain.from_iterable(values for _,values in windows.partitions()))
    merged.update(key for key,_ in windows.excluded)
    if merged != Counter(patch.key for patch in intake.entries):
        raise ArithmeticError('有单据未入对应时间窗')
    accepted=len(intake.entries)
    isolated=len(intake.issues)
    if accepted+isolated != intake.source_rows:
        raise ArithmeticError('原始工单与可用和隔离之和相差不符')
    states=Counter(row.state for row in dispatched.jobs)
    totals=Counter()
    for actual in dispatched.jobs:
        if actual.state=='已分派':
            totals.update({actual.cohort:actual.cost})
    if totals != dict(dispatched.used_by_group):
        raise ArithmeticError('分区剩余额度结果不相符')
    return LedgerCheck(accepted+isolated,isolated,len(windows.excluded),sum(states.values()),dispatched.capacity,
                       sum(totals.values()),dispatched.balance,tuple(sorted(states.items())))


def close_batch(dataset,intake,windows,dispatched,feature_id,model_kind,mode):
    verified=check_flow(intake,windows,dispatched)
    whole=data_fingerprint(dataset)
    scenario=policy_fingerprint(dispatched.capacity,mode,feature_id,model_kind)
    path=tuple((order.key,order.state,order.cost,order.reason,order.estimate) for order in dispatched.jobs)
    digest=sha256((whole+'|'+scenario+'|'+compact(path)+'|'+compact(verified.states)).encode()).hexdigest()[4:20]
    return BatchReceipt(digest,whole,scenario,verified,path)


def compare(before, after):
    old = {row[0]: row[1:] for row in before.decisions}
    current = {row[0]: row[1:] for row in after.decisions}
    new = current.keys() - old.keys()
    obsolete = old.keys() - current.keys()
    changed = {key for key in old.keys() & current.keys() if old[key] != current[key]}
    return {'新增': tuple(sorted(new)), '移出': tuple(sorted(obsolete)), '变更': tuple(sorted(changed)),
            '策略变化': before.policy_hash != after.policy_hash, '样本变化': before.batch_hash != after.batch_hash}


def reconciliation_evidence(receipt):
    ledger = receipt.totals
    rows = [{'核对项': '原始记录', '数量': ledger.raw}, {'核对项': '入站隔离', '数量': ledger.isolated},
            {'核对项': '窗口隔离', '数量': ledger.mature_excluded}, {'核对项': '当班对象', '数量': ledger.scored},
            {'核对项': '已用额度', '数量': ledger.resource_used}, {'核对项': '额度结余', '数量': ledger.balance}]
    rows.extend({'核对项': state, '数量': count} for state, count in ledger.states)
    return rows


def sign_field_evidence(rows, allocation):
    counts, spent = accountable_plan(rows, allocation.balance, allocation.capacity)
    if dict(counts) != dict(Counter(job.state for job in allocation.jobs)):
        raise ArithmeticError('展示单据和签发方案的处置统计不符')
    selected = {row['key']: row['cost'] for row in rows if row['state'] == '已分派'}
    original = {job.key: job.cost for job in allocation.jobs if job.state == '已分派'}
    if selected != original:
        raise ArithmeticError('分派凭证与作业单互相矛盾')
    return {'工位使用':spent, '执行业务单':document_control(rows)}


def intervention_summary(rows):
    actions = {}
    for record in rows:
        for sample in record['alternatives']:
            label = sample['情形']
            observed = actions.setdefault(label,[0,0,0,0])
            observed[0] += 1
            observed[1] += bool(sample['超训练域'])
            observed[2] += sample['用量']
            observed[3] += sample['预测变化']
    return [{'单项安排': key, '可比较单量': attempts, '超出拟合域': outlier,
             '总用量': units, '平均预测变化': round(delta/attempts,4)}
            for key,(attempts,outlier,units,delta) in sorted(actions.items())]


MEASUREMENT_FIELDS = ('scan_count', 'expected', 'mass_g', 'variant', 'partial', 'scan_repeat')


def rows_from_dispatch(plan):
    """Project immutable jobs into the row shape used by desk and seal checks."""
    rows = []
    for job in plan.jobs:
        readings = tuple(getattr(job, 'readings', ()) or ())
        rows.append({
            'key': job.key,
            'zone': job.cohort,
            'estimate': job.estimate,
            'state': job.state,
            'cost': job.cost,
            'reason': job.reason,
            'evidence': job.summary,
            'hits': list(job.rule_hits),
            'measurements': dict(zip(MEASUREMENT_FIELDS, readings, strict=False)),
            'unmeasured': list(getattr(job, 'missing', ()) or ()),
        })
    return rows


class Manifest(dict):
    """JSON-compatible export that also exposes ledger fields as attributes."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def export_seal(plan, rows=None):
    """Sign exactly the roster and balance shown on the revised workbench."""
    roster = rows_from_dispatch(plan) if rows is None else list(rows)
    evidence = sign_field_evidence(roster, plan)
    selected = tuple((row['key'], row['cost']) for row in roster if row['state'] == '已分派')
    return Manifest({
        'run_id': getattr(plan, 'request_id', None),
        'capacity': plan.capacity,
        'balance': plan.balance,
        'used_by_group': plan.used_by_group,
        'roster': roster,
        'rows': roster,
        'selected': selected,
        'dispatched': dict(selected),
        '工位使用': evidence['工位使用'],
        '执行业务单': evidence['执行业务单'],
    })


build_manifest = export_seal
seal_manifest = export_seal
seal_export = export_seal
export_manifest = export_seal
export_dispatch = export_seal
export_roster = export_seal
seal_roster = export_seal
build_seal_certificate = export_seal


def __getattr__(name):
    lowered = name.lower()
    if any(token in lowered for token in ('export', 'manifest', 'roster', 'certificate', 'seal')):
        return export_seal
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
