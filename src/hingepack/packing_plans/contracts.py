from dataclasses import dataclass

FIELDS = {'scan_count': ('扫码累计', '次', 2, 36),
 'expected': ('应装配件', '件', 3, 33),
 'mass_g': ('箱内五金重量', 'g', 150, 5300),
 'variant': ('非标配件类型', '类', 0, 10),
 'partial': ('补领单数', '单', 0, 9),
 'scan_repeat': ('重复扫描', '次', 0, 14)}
LIMITS = {'result_max': 1}


class MeasureIssue(ValueError):
    def __init__(self, field: str, code: str):
        super().__init__(f'{field}:{code}')
        self.field = field
        self.code = code


@dataclass(frozen=True, slots=True)
class HingepackRecord:
    key: str
    cohort: str
    day: int
    received: int
    revision: int
    result_day: int | None
    outcome: float | None
    observed: bool
    scan_count: float | None
    expected: float | None
    mass_g: float | None
    variant: float | None
    partial: float | None
    scan_repeat: float | None

    def signature(self):
        return (self.key, self.cohort, self.day, self.revision, self.result_day, self.outcome, self.observed,
                *(getattr(self, key) for key in FIELDS))


@dataclass(frozen=True, slots=True)
class Issue:
    source_row: int
    key: str
    field: str
    code: str

    def evidence(self):
        return {'行号': self.source_row, '单号': self.key, '字段': FIELDS.get(self.field, (self.field,))[0],
                '原因': self.code}


@dataclass(frozen=True, slots=True)
class DecodeResult:
    entries: tuple[HingepackRecord, ...]
    issues: tuple[Issue, ...]
    source_rows: int
