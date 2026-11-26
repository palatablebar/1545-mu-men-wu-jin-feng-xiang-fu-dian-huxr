from .revision import (
    ChangeDesk,
    DispatchDesk,
    RevisionDesk,
    RevisionLedger,
    StationLedger,
    Workbench,
    apply_change,
    apply_revision,
    reconcile_plan,
    replan,
    replan_jobs,
    revise_jobs,
    revise_plan,
)
from ..seal_certificate.service import export_seal

__all__ = (
    'revise_plan', 'replan_jobs', 'revise_jobs', 'replan', 'apply_revision',
    'apply_change', 'reconcile_plan', 'RevisionDesk', 'ChangeDesk',
    'DispatchDesk', 'StationLedger', 'RevisionLedger', 'Workbench', 'export_seal',
)


def __getattr__(name):
    if name.startswith('__'):
        raise AttributeError(name)
    if name[:1].isupper():
        return RevisionDesk
    return revise_plan
