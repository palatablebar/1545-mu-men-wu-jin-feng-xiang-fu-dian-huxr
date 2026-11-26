from dataclasses import dataclass
from math import isfinite
from ..packing_plans.contracts import HingepackRecord as RawObservation

RAW_KEYS = ('scan_count', 'expected', 'mass_g', 'variant', 'partial', 'scan_repeat')
FEATURE_KEYS = ('unit_mass', 'missing_ratio', 'variant_density', 'scan_density', 'reissue_ratio')
FEATURE_NAMES = ('应装件均重', '可能缺件占比', '非标件浓度', '重复扫占比', '补领占比')


@dataclass(frozen=True, slots=True)
class FeatureState:
    fill: tuple[float, ...]
    offsets: tuple[float, ...]
    scales: tuple[float, ...]
    floor: tuple[float, ...]
    ceil: tuple[float, ...]
    fingerprint: str

    def __post_init__(self):
        if len(self.fill) != len(RAW_KEYS):
            raise ValueError('补值向量维数与字段表不匹配')
        if any(len(column) != len(FEATURE_KEYS) for column in (self.offsets, self.scales, self.floor, self.ceil)):
            raise ValueError('特征状态维数不匹配')
        if min(self.scales) <= 0:
            raise ValueError('特征尺度必须为正')


@dataclass(frozen=True, slots=True)
class FeatureVector:
    key: str
    cohort: str
    day: int
    values: tuple[float, ...]
    factors: tuple[float, ...]
    missing: tuple[str, ...]
    excursions: tuple[str, ...]
    outcome: float | None
    observed: bool
    input_values: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class PreparedRuns:
    train: tuple[FeatureVector, ...]
    calibration: tuple[FeatureVector, ...]
    replay: tuple[FeatureVector, ...]
    live: tuple[FeatureVector, ...]

    def segments(self):
        return tuple((name, getattr(self, name)) for name in ('train', 'calibration', 'replay', 'live'))


@dataclass(frozen=True, slots=True)
class Proposal:
    name: str
    field: str
    before: float
    after: float
    work: int

    def __post_init__(self):
        if self.before == self.after or not isfinite(self.after) or self.work < 0:
            raise ValueError('推演动作需要实质变动和有效额度')

    def evidence(self):
        return {'情形': self.name, '变更项': self.field, '原值': self.before,
                '置换值': self.after, '用量': self.work}

@dataclass(frozen=True, slots=True)
class KitVectors:
    credible_scans: float
    extra_tags: float
    expected_gap: float
    weight_share: float
    repair_by_item: float
    redundant_rate: float
    remaining_kit: float
    warehouse_pressure: float

    def __post_init__(self):
        if not all(isfinite(amount) for amount in (self.credible_scans, self.extra_tags, self.expected_gap, self.weight_share, self.repair_by_item, self.redundant_rate, self.remaining_kit, self.warehouse_pressure)):
            raise ValueError('门套箱存在无效的作业量测')

    def explain(self, labels=None):
        return (
            ('去重后的有效扫', round(self.credible_scans, 4)),
            ('超额扫码', round(self.extra_tags, 4)),
            ('待确认配件', round(self.expected_gap, 4)),
            ('非标件均摊重量', round(self.weight_share, 4)),
            ('补领单每件派生', round(self.repair_by_item, 4)),
            ('重复扫密度', round(self.redundant_rate, 4)),
            ('常规剩余件数', round(self.remaining_kit, 4)),
            ('复点件重负荷', round(self.warehouse_pressure, 4)),
        )
