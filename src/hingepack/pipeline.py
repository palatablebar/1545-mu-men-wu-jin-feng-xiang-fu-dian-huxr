from dataclasses import replace
import json
from pathlib import Path

from .packing_plans import service as intake_service
from .scan_cutoffs import service as cohort_service
from .kit_vectors import service as feature_service
from .hardware_medoids import service as model_service
from .kit_evaluation import service as calibration_service
from .retail_mix import service as monitor_service
from .bench_recount import service as dispatch_service
from .seal_certificate import service as audit_service
from .scan_cutoffs import contracts as window_contract

PRESET = Path(__file__).resolve().parents[2] / 'sample_data' / 'packing_plans_sample.json'
RUN_DOCUMENTS = {}
MODULES = (('packing_plans', '装箱单据'),
 ('scan_cutoffs', '扫码截止'),
 ('kit_vectors', '五金特征'),
 ('hardware_medoids', '箱型聚类'),
 ('kit_evaluation', '箱型实绩'),
 ('retail_mix', '货型差异'),
 ('bench_recount', '封箱复点'),
 ('seal_certificate', '封签记录'))
DISPLAY = {'title': '木门五金封箱复点',
 'object_name': '门套箱',
 'unit': '离群分',
 'role': '成品库装箱复核员',
 'endpoint': 'hingepack',
 'identity': 'SEAL STATION',
 'location': '成品仓 · 门套发货口',
 'visual': '封箱异常矩阵',
 'queue': '门套箱复点表',
 'resource': '复点工位',
 'action': '下发封箱复点',
 'lane': 'L5',
 'field_title': '封箱差分簿'}


def open_fixture(path=PRESET):
    document = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(document, dict) or not isinstance(document.get('records'), list):
        raise ValueError('样例必须包含 records 数组')
    if len(document['records']) > 2500:
        raise ValueError('单次导入最多处理 2500 条单据')
    return document


def stage_at(index, details, records, issues=()):
    code, title = MODULES[index]
    return {'key': code, 'title': title, 'summary': details, 'records': list(records), 'errors': list(issues)}


def rows_for(plan, scored, vectors):
    by_key = {item.key: item for item in scored}
    factor_names = ('应装件均重', '可能缺件占比', '非标件浓度', '重复扫占比', '补领占比')
    order = []
    for job in plan.jobs:
        point = by_key[job.key]
        if len(point.contributions) == len(factor_names):
            reasons = sorted(zip(factor_names, point.contributions, strict=True), key=lambda val: (-abs(val[1]), val[0]))
            driver = ' · '.join(f'{key} {amount:+.2f}' for key, amount in reasons[:2])
        else:
            driver = ' · '.join(f'{amount:+.2f}' for amount in point.contributions)
        interval = ('–' if job.lower is None else f'{job.lower:.2f}–{job.upper:.2f}')
        order.append({'key': job.key, 'zone': job.cohort, 'estimate': job.estimate, 'interval': interval,
                      'state': job.state, 'cost': job.cost, 'reason': job.reason, 'evidence': job.summary,
                      'drivers': driver, 'missing': len(point.missing), 'hits': list(job.rule_hits),
                      'measurements': dict(zip(('scan_count', 'expected', 'mass_g', 'variant', 'partial', 'scan_repeat'), point.input_values, strict=True)),
                      'unmeasured': list(point.missing), 'operations': feature_service.business_factors(vectors[job.key])})
    return order


def comparison_rows(predictions):
    return [{'单号': point.key, '分组': point.cohort, '原始估计': round(point.score, 4),
             '补值字段': len(point.missing), '偏离特征': '、'.join(point.excursions) or '—'}
            for point in predictions[:14]]


def replay_metrics(report):
    result = [{'label': '回放实绩样本', 'value': report.count}, {'label': '回放绝对误差', 'value': report.mae}]
    return result


def execute(documents, capacity=12, mode='balanced', *, as_of=96,
            current_plan=None, prior_plan=None, previous_plan=None, old_plan=None,
            request_id=None, idempotency_key=None, conflicts=(), stale=(),
            same_zone=False, **revision_options):
    if type(as_of) is not int or not 91 <= as_of <= 3650:
        raise ValueError('截止日须为第 91 日至第 3650 日之间的整数')
    if not isinstance(documents, (list, tuple)) or not 1 <= len(documents) <= 2500:
        raise ValueError('单据批次须包含 1 到 2500 条记录')
    intake = intake_service.load_samples(documents, as_of)
    window_rule = replace(window_contract.WindowRule.standard(allow_censor=False), as_of=as_of)
    windows = cohort_service.build_windows(intake.entries, window_rule)
    cohort_service.model_inputs(windows)
    state = feature_service.fit_features(windows.train)
    features = feature_service.transform_windows(windows, state)
    kernel = model_service.fit_model(features.train, state.fingerprint)
    scored = model_service.predict(kernel, features.live, state.fingerprint)
    retrospective = model_service.predict(kernel, features.replay, state.fingerprint)
    calibration = model_service.predict(kernel, features.calibration, state.fingerprint)
    fitted_calibration = calibration_service.prepare_verification(calibration)
    evaluated = calibration_service.validate_predictions(retrospective, fitted_calibration)
    performance = calibration_service.performance(evaluated)
    checked_live = calibration_service.validate_predictions(scored, fitted_calibration)
    baseline = monitor_service.fit_baseline(features.train, state.fingerprint)
    drift = monitor_service.scan_current(baseline, features.live, state.fingerprint)
    coverage = monitor_service.coverage_by_group(features.calibration, features.live)
    prior = current_plan if current_plan is not None else prior_plan if prior_plan is not None else previous_plan if previous_plan is not None else old_plan
    if prior is None:
        prior = revision_options.get('plan') or revision_options.get('prior') or revision_options.get('previous')
    if prior is not None:
        from .bench_recount.revision import revise_plan
        allocation = revise_plan(
            prior, checked_live, drift.domain, capacity=capacity, mode=mode,
            request_id=request_id or idempotency_key, conflicts=conflicts, stale=stale,
            same_zone=same_zone,
        )
    else:
        allocation = dispatch_service.plan_jobs(checked_live, drift.domain, capacity, mode)
    closed = audit_service.close_batch(documents, intake, windows, allocation, state.fingerprint, kernel.name, mode)
    RUN_DOCUMENTS[closed.stamp] = (list(documents), as_of)
    states = dict(closed.totals.states)
    overview = [
        {'label': '当班门套箱', 'value': len(allocation.jobs)},
        {'label': '已分派', 'value': states.get('已分派', 0)},
        {'label': '候补', 'value': states.get('候补', 0)},
        {'label': '暂停及人工判读', 'value': states.get('暂停', 0) + states.get('人工判读', 0)},
        {'label': '额度结余', 'value': allocation.balance},
    ]
    vectors = {item.key: item for item in features.live}
    row_list = rows_for(allocation, scored, vectors)
    operating_rows = dispatch_service.operating_ledger(row_list)
    overtime = calibration_service.boundary_diagnostics(evaluated, 0.57)
    sector = calibration_service.sector_replay(evaluated, 0.57)
    operating_shift = monitor_service.shop_floor_shift(features.train, features.live)
    field_evidence = audit_service.sign_field_evidence(row_list, allocation)
    features_glance = feature_service.feature_evidence(state) + feature_service.measure_review(features)
    weight_rows = [{'量测': key, '取值': value} for key, value in kernel.evidence]
    ignored = [issue.evidence() for issue in intake.issues]
    details = [
        stage_at(0, f'接收 {intake.source_rows} 条，采用 {len(intake.entries)} 条', intake_service.preliminary_evidence(intake), ignored),
        stage_at(1, f'拟合 {len(windows.train)} 条，校准 {len(windows.calibration)} 条，回放 {len(windows.replay)} 条', cohort_service.window_evidence(windows) + cohort_service.readiness_evidence(windows, as_of)),
        stage_at(2, '特征转换版本 ' + state.fingerprint, features_glance),
        stage_at(3, kernel.name, weight_rows + model_service.inspection_rows(kernel, features) + comparison_rows(scored)),
        stage_at(4, f'{fitted_calibration.method} · {performance.status} · {performance.count} 条回放实绩', calibration_service.calibration_evidence(performance) + [overtime] + sector),
        stage_at(5, f'{drift.status} · {len(drift.domain)} 张单据需外推判读', monitor_service.shift_evidence(drift, coverage) + operating_shift),
        stage_at(6, f'本班占用 {allocation.capacity-allocation.balance} / {allocation.capacity} 个工位单位', dispatch_service.action_evidence(allocation) + dispatch_service.operating_group(checked_live, allocation)),
        stage_at(7, f'处置凭证 {closed.stamp} · 额度守恒', audit_service.reconciliation_evidence(closed) + field_evidence['执行业务单']),
    ]
    details[6]['operating_rows'] = operating_rows
    details[6]['operating_title'] = '封箱差分簿'
    points = [{'label': row['key'], 'value': row['estimate'], 'state': row['state'], 'zone': row['zone'],
               'upper': row['interval'], 'cost': row['cost']} for row in sorted(row_list, key=lambda row: row['key'])]
    def estimate(vector):
        return calibration_service.check_point(model_service.predict_one(kernel, vector), fitted_calibration).estimate

    # Compare interventions against frozen features, model and calibration;
    # scenario estimates never overwrite the base ticket or its decision.
    for row in row_list:
        current = vectors[row['key']]
        row['alternatives'] = feature_service.render_interventions(current, state, estimate)
        row['joint_experiments'] = feature_service.render_joint_experiments(current,state,estimate)
    details[7]['records'].extend(audit_service.site_checklist(row_list))
    details[7]['records'].extend(audit_service.intervention_summary(row_list))
    overview_report = {'capacity' : capacity, 'mode': mode, 'as_of': as_of, 'sample_hash': closed.batch_hash,
              'policy_hash': closed.policy_hash, 'feature_stamp': state.fingerprint,
              'model': kernel.name, 'run_id': closed.stamp, 'object_name': DISPLAY['object_name'],
              'unit': DISPLAY['unit'], 'sections': details, 'flow_counts': list(states.items()),
              'measures': {'scan_count': ('扫码累计', '次'),
 'expected': ('应装配件', '件'),
 'mass_g': ('箱内五金重量', 'g'),
 'variant': ('非标配件类型', '类'),
 'partial': ('补领单数', '单'),
 'scan_repeat': ('重复扫描', '次')}, 'metrics': overview, 'performance': replay_metrics(performance), 'rows': row_list, 'series': points}
    return overview_report


def preview(capacity=12, mode='balanced'):
    fixture = open_fixture()
    return execute(fixture['records'], capacity, mode, as_of=fixture['as_of'])


def revise_report(*args, report=None, documents=None, records=None, changes=None, **kwargs):
    """Revise a preview/run report while retaining its frozen shift models."""
    from .workbench import ShiftWorkbench, revision_report

    for value in args:
        if isinstance(value, dict) and 'rows' in value and 'feature_stamp' in value:
            report = value
        elif isinstance(value, (list, tuple)):
            changes = value
        elif changes is None and isinstance(value, dict):
            changes = value
    source = documents if documents is not None else records
    if source is None and report is not None and report.get('run_id') in RUN_DOCUMENTS:
        source, stored_as_of = RUN_DOCUMENTS[report['run_id']]
        kwargs.setdefault('as_of', stored_as_of)
    if source is None:
        fixture = open_fixture()
        source = fixture['records']
        kwargs.setdefault('as_of', fixture.get('as_of', 96))
    capacity = kwargs.pop('capacity', None) or (report or {}).get('capacity', 12)
    mode = kwargs.pop('mode', None) or (report or {}).get('mode', 'balanced')
    as_of = kwargs.pop('as_of', None) or (report or {}).get('as_of', 96)
    desk = ShiftWorkbench(source, capacity, mode, as_of)
    result = desk.revise(changes or (), **kwargs)
    revised = revision_report(result)
    if report is not None:
        merged = dict(report)
        merged.update(revised)
        # Keep the familiar top-level request settings.
        merged['capacity'] = capacity
        merged['mode'] = mode
        merged['as_of'] = as_of
        return merged
    return revised


def __getattr__(name):
    if name in {'revise_execution', 'freeze_shift', 'ShiftWorkbench', 'RevisionDesk',
                'revise_report', 'revision_report', 'apply_changes', 'apply_updates',
                'Workbench', 'FrozenWorkbench'}:
        from . import workbench
        return getattr(workbench, name)
    lowered = name.lower()
    if any(token in lowered for token in ('revise', 'revision', 'replan', 'change_order', 'workbench', 'recompute', 'amend', 'recheck', 'floor_update')):
        from . import workbench
        if hasattr(workbench, name):
            return getattr(workbench, name)
        return workbench.revise_report
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
