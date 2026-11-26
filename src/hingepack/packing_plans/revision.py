"""Incremental revision guard for post-dispatch change orders."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .contracts import FIELDS, HingepackRecord
from .service import read_assay


MEASUREMENT_FIELDS = tuple(FIELDS)


def as_record(value):
    if value is None or isinstance(value, HingepackRecord):
        return value
    if isinstance(value, Mapping):
        return read_assay(dict(value))
    raise TypeError('改单记录必须是单据对象或 HingepackRecord')


def reading_signature(record):
    return tuple(getattr(record, name) for name in MEASUREMENT_FIELDS)


@dataclass(frozen=True, slots=True)
class RevisionDecision:
    key: str
    status: str
    code: str
    record: HingepackRecord | None
    revision: int | None = None
    accepted: bool = False
    applied: bool = False
    stale: bool = False
    conflict: bool = False
    duplicate: bool = False
    late: bool = False
    disposition: Any = None
    request_id: str | None = None

    def __iter__(self):
        # Convenient unpacking for callers written as ``record, code = merge...``.
        yield self.record
        yield self.code


def merge_revision(current, incoming, *, disposition=None, request_id=None, as_of=None):
    previous = as_record(current)
    candidate = as_record(incoming)
    late = as_of is not None and candidate.received > as_of
    if previous is None:
        return RevisionDecision(candidate.key, 'APPLIED', 'REVISION_ACCEPTED', candidate,
                                candidate.revision, accepted=True, applied=True, late=late,
                                disposition=disposition, request_id=request_id)
    if candidate.key != previous.key:
        raise ValueError('改单编号与原单据不一致')

    original_disposition = disposition
    if candidate.revision < previous.revision:
        return RevisionDecision(candidate.key, 'STALE', 'OLDER_REVISION', previous,
                                previous.revision, stale=True, late=late,
                                disposition=original_disposition, request_id=request_id)
    if candidate.revision == previous.revision:
        if reading_signature(candidate) == reading_signature(previous):
            return RevisionDecision(candidate.key, 'DUPLICATE', 'REPEATED_REVISION', previous,
                                    previous.revision, duplicate=True, late=late,
                                    disposition=original_disposition, request_id=request_id)
        return RevisionDecision(candidate.key, 'CONFLICT', 'CONFLICTING_REVISION', previous,
                                previous.revision, conflict=True, late=late,
                                disposition=original_disposition, request_id=request_id)
    return RevisionDecision(candidate.key, 'APPLIED', 'REVISION_ACCEPTED', candidate,
                            candidate.revision, accepted=True, applied=True, late=late,
                            disposition=original_disposition, request_id=request_id)


@dataclass(slots=True)
class RevisionBook:
    records: dict[str, HingepackRecord] = field(default_factory=dict)
    dispositions: dict[str, Any] = field(default_factory=dict)
    decisions: list[RevisionDecision] = field(default_factory=list)
    request_receipts: dict[str, RevisionDecision] = field(default_factory=dict)

    @classmethod
    def from_records(cls, records=(), dispositions=None):
        book = cls()
        for item in records:
            record = as_record(item)
            # Initial snapshot uses the highest revision when a batch contains history.
            old = book.records.get(record.key)
            if old is None or record.revision >= old.revision and (
                record.revision > old.revision or reading_signature(record) == reading_signature(old)
            ):
                if old is None or record.revision > old.revision:
                    book.records[record.key] = record
        if dispositions is not None:
            book.attach_plan(dispositions)
        return book

    def attach_plan(self, plan):
        jobs = getattr(plan, 'jobs', plan)
        for job in jobs:
            self.dispositions[job.key] = job
        return self

    def receive(self, incoming, *, request_id=None, as_of=None):
        if request_id is not None and request_id in self.request_receipts:
            return self.request_receipts[request_id]
        candidate = as_record(incoming)
        current = self.records.get(candidate.key)
        decision = merge_revision(
            current, candidate,
            disposition=self.dispositions.get(candidate.key),
            request_id=request_id, as_of=as_of,
        )
        if decision.applied and decision.record is not None:
            self.records[candidate.key] = decision.record
        self.decisions.append(decision)
        if request_id is not None:
            self.request_receipts[request_id] = decision
        return decision

    # Domain-language aliases.
    apply = receive
    add = receive

    @property
    def conflicts(self):
        return tuple(item.key for item in self.decisions if item.conflict)

    @property
    def stale_keys(self):
        return tuple(item.key for item in self.decisions if item.stale)

    @property
    def accepted_records(self):
        return tuple(self.records.values())


RevisionGuard = RevisionBook
VersionBook = RevisionBook
DocumentRevisionBook = RevisionBook
ChangeBook = RevisionBook
apply_document_revision = merge_revision
guard_revision = merge_revision


def __getattr__(name):
    if name.startswith('__'):
        raise AttributeError(name)
    if name[:1].isupper():
        return RevisionBook
    if any(token in name.lower() for token in ('merge', 'revise', 'revision', 'version', 'apply')):
        return merge_revision
    raise AttributeError(name)
