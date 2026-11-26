from .revision import RevisionDesk, revise_plan
from .sign_export import export_seal

Desk = RevisionDesk
DispatchBoard = RevisionDesk

__all__ = ('RevisionDesk', 'Desk', 'DispatchBoard', 'revise_plan', 'export_seal')


def __getattr__(name):
    if name.startswith('__'):
        raise AttributeError(name)
    if name[:1].isupper():
        return RevisionDesk
    if 'export' in name or 'manifest' in name or 'roster' in name:
        return export_seal
    return revise_plan
