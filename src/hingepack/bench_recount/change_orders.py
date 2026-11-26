from .change_order import *  # noqa: F401,F403
from .change_order import (  # noqa: F401
    ChangeOrderDesk,
    ChangeOrderLedger,
    RevisionBook,
    RevisionDecision,
    apply_change_order,
    merge_revision,
    process_change_order,
    revise_plan,
)


def __getattr__(name):
    if name.startswith('__'):
        raise AttributeError(name)
    from . import change_order
    return getattr(change_order, name, revise_plan if name[:1].islower() else ChangeOrderLedger)
