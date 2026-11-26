from .revision import *  # noqa: F401,F403
from .revision import RevisionDesk, revise_plan

apply_live_update = revise_plan
process_live_updates = revise_plan
LiveUpdateDesk = RevisionDesk


def __getattr__(name):
    if name.startswith('__'):
        raise AttributeError(name)
    if name[:1].isupper():
        return RevisionDesk
    return revise_plan
