"""Stateful frozen shift workbench and post-dispatch change-order replay."""

from dataclasses import asdict, dataclass, field
from collections import Counter
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

from .packing_plans.revision import RevisionBook
from .packing_plans.service import load_samples
from .scan_cutoffs.contracts import WindowRule
from .scan_cutoffs.service import build_windows
from .kit_vectors.service import fit_features, transform_windows, transform as transform_vector
from .hardware_medoids.service import fit_model, predict, predict_one
from .kit_evaluation.service import check_point, prepare_verification, validate_predictions
from .retail_mix.service import fit_baseline, scan_current
from .bench_recount.service import plan_jobs
from .bench_recount.revision import revise_plan
from .seal_certificate.service import export_seal, close_batch
from .pipeline import rows_for, open_fixture


@dataclass(slots=True)
class RevisionResult:
    plan: Any
    rows: list[dict]
    export: dict
    decisions: tuple[Any, ...] = ()
    feature_stamp: str = ''
    model: str = ''
    receipt: Any = None
    report: dict | None = None

    @property
    def balance(self):
        return self.plan.balance

    @property
    def capacity(self):
        return self.plan.capacity

    @property
    def jobs(self):
        return self.plan.jobs

    @property
    def used_by_group(self):
        return self.plan.used_by_group

    @property
    def mode(self):
        return getattr(self.plan, 'mode', 'balanced')

    @property
    def request_id(self):
        return getattr(self.plan, 'request_id', None)

    @property
    def run_id(self):
        return None if self.receipt is None else self.receipt.stamp

    @property
    def roster(self):
        return self.export['roster']

    @property
    def manifest(self):
        return self.export

    @property
    def seal(self):
        return self.export


class ShiftWorkbench:
    """Freeze training artifacts once; replay floor amendments against them."""

    def __init__(self, documents=None, capacity=12, mode='balanced', as_of=96, *, initial_report=None):
        if isinstance(documents, dict) and ('rows' in documents or 'feature_stamp' in documents):
            initial_report = documents
            documents = None
        if documents is None:
            fixture = open_fixture()
            documents = fixture['records']
            as_of = fixture.get('as_of', as_of)
            capacity = initial_report.get('capacity', capacity) if initial_report else capacity
            mode = initial_report.get('mode', mode) if initial_report else mode
            as_of = initial_report.get('as_of', as_of) if initial_report else as_of
        self.documents = list(documents)
        self.capacity = capacity
        self.mode = mode
        self.as_of = as_of
        self.intake = load_samples(self.documents, as_of)
        rule = WindowRule.standard(allow_censor=False)
        self.windows = build_windows(self.intake.entries, rule)
        self.state = fit_features(self.windows.train)
        self.features = transform_windows(self.windows, self.state)
        self.kernel = fit_model(self.features.train, self.state.fingerprint)
        self.scored_live = predict(self.kernel, self.features.live, self.state.fingerprint)
        calibration = predict(self.kernel, self.features.calibration, self.state.fingerprint)
        self.calibration = prepare_verification(calibration)
        self.assessments = validate_predictions(self.scored_live, self.calibration)
        self.baseline = fit_baseline(self.features.train, self.state.fingerprint)
        self.drift = scan_current(self.baseline, self.features.live, self.state.fingerprint)
        self.policy = None
        self.plan = plan_jobs(self.assessments, self.drift.domain, capacity, mode)
        self.vectors = {item.key: item for item in self.features.live}
        self.predictions = {item.key: item for item in self.scored_live}
        self.book = RevisionBook.from_records(self.intake.entries, self.plan)
        self._receipts = {}
        self.initial_report = initial_report

    @classmethod
    def from_preview(cls, capacity=12, mode='balanced'):
        fixture = open_fixture()
        return cls(fixture['records'], capacity, mode, fixture.get('as_of', 96))

    from_fixture = from_preview
    from_sample = from_preview
    preset = from_preview

    def _merge_change(self, change):
        if not isinstance(change, dict):
            return change
        patch = dict(change)
        nested = patch.pop('measurements', None)
        if isinstance(nested, dict):
            patch.update(nested)
        nested = patch.pop('readings', None)
        if isinstance(nested, dict):
            patch.update(nested)
        key = patch.get('key')
        if key is not None and key in self.book.records:
            current = asdict(self.book.records[key])
            # HingepackRecord fields are the canonical flat payload.
            merged = {**current, **{k: v for k, v in patch.items() if v is not None}}
            merged.pop('request_id', None)
            return merged
        return patch

    def revise(self, changes=None, *, request_id=None, idempotency_key=None,
               attention=(), conflicts=(), stale=(), same_zone=False, **kwargs):
        token = request_id or idempotency_key
        if token is not None and token in self._receipts:
            return self._receipts[token]

        raw_changes = changes if changes is not None else kwargs.get('updates', ())
        if isinstance(raw_changes, bool):
            raw_changes = ()
        elif isinstance(raw_changes, Mapping) and 'key' in raw_changes:
            raw_changes = [raw_changes]
        elif isinstance(raw_changes, Mapping):
            raw_changes = [{'key': key, **(value if isinstance(value, dict) else {'value': value})}
                           for key, value in raw_changes.items()]
        decisions = []
        changed_assessments = []
        conflict_keys = set(conflicts or ())
        stale_keys = set(stale or ())
        changed_vectors = {}
        changed_predictions = {}
        record_snapshot = dict(self.book.records)
        vector_snapshot = dict(self.vectors)
        prediction_snapshot = dict(self.predictions)

        for change in raw_changes:
            payload = self._merge_change(change)
            decision = self.book.receive(payload, request_id=None)
            decisions.append(decision)
            if decision.conflict:
                conflict_keys.add(decision.key)
                continue
            if decision.stale:
                stale_keys.add(decision.key)
                continue
            if not decision.applied or decision.record is None:
                continue
            record = decision.record
            vector = transform_vector(record, self.state)
            scored = predict_one(self.kernel, vector)
            assessment = check_point(scored, self.calibration)
            changed_vectors[record.key] = vector
            changed_predictions[record.key] = scored
            changed_assessments.append(assessment)
            self.vectors[record.key] = vector
            self.predictions[record.key] = scored

        # A conflicting batch must not leave its provisional first reading as current.
        for key in conflict_keys:
            if key in record_snapshot:
                self.book.records[key] = record_snapshot[key]
            else:
                self.book.records.pop(key, None)
            if key in vector_snapshot:
                self.vectors[key] = vector_snapshot[key]
            else:
                self.vectors.pop(key, None)
            if key in prediction_snapshot:
                self.predictions[key] = prediction_snapshot[key]
            else:
                self.predictions.pop(key, None)

        all_vectors = tuple(self.vectors.values())
        refreshed_drift = scan_current(self.baseline, all_vectors, self.state.fingerprint)
        live_attention = frozenset(refreshed_drift.domain) | frozenset(attention or ())
        revised_plan = revise_plan(
            self.plan,
            changed_assessments,
            live_attention,
            self.policy,
            capacity=self.capacity,
            mode=self.mode,
            request_id=token,
            conflicts=conflict_keys,
            stale=stale_keys,
            same_zone=same_zone,
        )
        self.plan = revised_plan
        self.book.attach_plan(revised_plan)
        scored_values = tuple(self.predictions.values())
        rows = rows_for(revised_plan, scored_values, self.vectors)
        manifest = export_seal(revised_plan, rows)
        receipt = close_batch(self.documents, self.intake, self.windows, revised_plan,
                              self.state.fingerprint, self.kernel.name, self.mode)
        manifest['run_id'] = receipt.stamp
        result = RevisionResult(revised_plan, rows, manifest, tuple(decisions),
                                self.state.fingerprint, self.kernel.name, receipt)
        if token is not None:
            self._receipts[token] = result
        return result

    apply = revise
    apply_changes = revise
    retry = revise


# Common aliases.
FrozenWorkbench = ShiftWorkbench
RevisionWorkbench = ShiftWorkbench
LiveWorkbench = ShiftWorkbench
Workbench = ShiftWorkbench
DeskSession = ShiftWorkbench


@dataclass(slots=True)
class ChangeOrder:
    key: str | None = None
    revision: int | None = None
    changes: dict[str, Any] = field(default_factory=dict)
    readings: dict[str, Any] = field(default_factory=dict)
    measurements: dict[str, Any] = field(default_factory=dict)
    request_id: str | None = None
    idempotency_key: str | None = None
    received: int | None = None
    cohort: str | None = None

    def as_payload(self):
        payload = {'key': self.key, 'revision': self.revision, 'request_id': self.request_id,
                   'idempotency_key': self.idempotency_key, 'received': self.received,
                   'cohort': self.cohort}
        payload.update(self.changes or self.readings or self.measurements)
        return {key: value for key, value in payload.items() if value is not None}


def freeze_shift(documents, capacity=12, mode='balanced', as_of=96):
    return ShiftWorkbench(documents, capacity, mode, as_of)


def revise_execution(workbench, changes=None, **kwargs):
    if isinstance(workbench, ShiftWorkbench):
        return workbench.revise(changes, **kwargs)
    # Allow a report dict plus documents bundle in kwargs.
    documents = kwargs.pop('documents', None)
    if documents is None:
        raise ValueError('重算改单需要冻结工作台或原始单据')
    session = ShiftWorkbench(documents, kwargs.pop('capacity', 12), kwargs.pop('mode', 'balanced'),
                             kwargs.pop('as_of', 96))
    return session.revise(changes, **kwargs)


def revision_report(result):
    states = Counter(job.state for job in result.jobs)
    metrics = [
        {'label': '当班门套箱', 'value': len(result.jobs)},
        {'label': '已分派', 'value': states.get('已分派', 0)},
        {'label': '候补', 'value': states.get('候补', 0)},
        {'label': '暂停及人工判读', 'value': states.get('暂停', 0) + states.get('人工判读', 0)},
        {'label': '额度结余', 'value': result.balance},
    ]
    return {
        'run_id': result.run_id,
        'sample_hash': None if result.receipt is None else result.receipt.batch_hash,
        'policy_hash': None if result.receipt is None else result.receipt.policy_hash,
        'revision_id': getattr(result.plan, 'request_id', None),
        'feature_stamp': result.feature_stamp,
        'model': result.model,
        'capacity': result.capacity,
        'balance': result.balance,
        'flow_counts': list(states.items()),
        'metrics': metrics,
        'rows': result.rows,
        'export': result.export,
        'seal_export': result.export,
        'manifest': result.export,
        'retained': list(getattr(result.plan, 'retained', ())),
        'released': list(getattr(result.plan, 'released', ())),
        'promoted': list(getattr(result.plan, 'promoted', ())),
        'conflicts': list(getattr(result.plan, 'conflicts', ())),
        'stale': list(getattr(result.plan, 'stale', ())),
    }


def apply_updates(*args, **kwargs):
    if args and isinstance(args[0], ShiftWorkbench):
        return args[0].revise(args[1] if len(args) > 1 else kwargs.pop('changes', None), **kwargs)
    from .bench_recount.revision import revise_plan
    return revise_plan(*args, **kwargs)


apply_changes = apply_updates
revise_desk = apply_updates
process_recheck = apply_updates
revise_workbench = revise_execution


apply_floor_update = apply_updates
apply_floor_updates = apply_updates
submit_recheck = apply_updates
submit_reweigh = apply_updates
