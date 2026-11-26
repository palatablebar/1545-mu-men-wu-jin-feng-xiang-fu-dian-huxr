from .revision import RevisionDesk, revise_plan

reseat_plan = revise_plan
reseat_jobs = revise_plan
reassign_plan = revise_plan
backfill_plan = revise_plan
SeatingDesk = RevisionDesk
SeatLedger = RevisionDesk

__all__ = ('reseat_plan', 'reseat_jobs', 'reassign_plan', 'backfill_plan', 'SeatingDesk', 'SeatLedger')


def __getattr__(name):
    if name.startswith('__'):
        raise AttributeError(name)
    if name[:1].isupper():
        return RevisionDesk
    return revise_plan
