from dataclasses import dataclass, field, replace

RISK_CUTOFF = 0.57


@dataclass(frozen=True, slots=True)
class Policy:
    capacity: int
    group_quota: int
    trigger: float

    @classmethod
    def select(cls, capacity, mode):
        if type(capacity) is not int or not 1 <= capacity <= 60:
            raise ValueError('本班额度须在 1 至 60 之间')
        if mode == 'balanced':
            per_group = max(3, (capacity*3 + 4)//5)
            return cls(capacity, per_group, RISK_CUTOFF)
        if mode == 'focus':
            return cls(capacity, capacity, RISK_CUTOFF * .92)
        raise ValueError('未知复核策略')


@dataclass(frozen=True, slots=True)
class RuleNotice:
    rule_id: str
    meaning: str
    hard: bool = False


@dataclass(frozen=True, slots=True)
class Job:
    key: str
    cohort: str
    estimate: float
    lower: float | None
    upper: float | None
    cost: int
    state: str
    reason: str
    summary: str
    priority: float
    rule_hits: tuple[str, ...]
    readings: tuple[float, ...] = field(default=(), compare=False, repr=False)
    missing: tuple[str, ...] = field(default=(), compare=False, repr=False)
    bench: str = field(default='', compare=False, repr=False)
    revision: int | None = field(default=None, compare=False)
    pending_check: bool = field(default=False, compare=False)
    reading_conflict: bool = field(default=False, compare=False)
    stale: bool = field(default=False, compare=False)
    idempotent_retry: bool = field(default=False, compare=False)
    held: bool = field(default=False, compare=False)
    sticky: bool = field(default=False, compare=False)
    seat_retained: bool = field(default=False, compare=False)

    def change(self, state, reason, summary):
        return replace(self, state=state, reason=reason, summary=summary)


@dataclass(frozen=True, slots=True)
class Plan:
    jobs: tuple[Job, ...]
    capacity: int
    balance: int
    used_by_group: tuple[tuple[str, int], ...]
    mode: str = field(default='balanced', compare=False)
    retained: tuple[str, ...] = field(default=(), compare=False)
    released: tuple[str, ...] = field(default=(), compare=False)
    promoted: tuple[str, ...] = field(default=(), compare=False)
    conflicts: tuple[str, ...] = field(default=(), compare=False)
    stale: tuple[str, ...] = field(default=(), compare=False)
    request_id: str | None = field(default=None, compare=False)
