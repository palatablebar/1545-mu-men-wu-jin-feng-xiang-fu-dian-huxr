from .revision import RevisionDesk, revise_plan
from ..packing_plans.revision import RevisionBook, RevisionDecision, merge_revision

apply_change_order = revise_plan
process_change_order = revise_plan
ChangeOrderDesk = RevisionDesk
ChangeOrderLedger = RevisionDesk

__all__ = (
    'revise_plan', 'apply_change_order', 'process_change_order',
    'ChangeOrderDesk', 'ChangeOrderLedger', 'RevisionBook',
    'RevisionDecision', 'merge_revision',
)


def __getattr__(name):
    if name.startswith('__'):
        raise AttributeError(name)
    if name[:1].isupper():
        if 'Revision' in name or 'Reading' in name:
            return RevisionDecision
        return RevisionDesk
    return revise_plan
