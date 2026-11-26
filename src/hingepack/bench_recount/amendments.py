from .revision import RevisionDesk, revise_plan

apply_amendment = revise_plan
apply_amendments = revise_plan
AmendmentDesk = RevisionDesk

__all__ = ('apply_amendment', 'apply_amendments', 'AmendmentDesk', 'revise_plan', 'RevisionDesk')


def __getattr__(name):
    if name.startswith('__'):
        raise AttributeError(name)
    if name[:1].isupper():
        return AmendmentDesk
    return revise_plan
