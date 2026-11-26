from collections.abc import Mapping
from decimal import Decimal

from .contracts import MeasureIssue


from dataclasses import dataclass


def form_number(form, sheet, name, minimum, maximum):
    from .service import number

    table = form.get(sheet)
    if not isinstance(table, Mapping):
        raise MeasureIssue(sheet, 'FORM_SECTION_REQUIRED')
    return Decimal(str(number(table.get(name), name, minimum, maximum)))


@dataclass(frozen=True, slots=True)
class PackingPlansSheet:
    barcode_reads: Decimal
    bom_parts: Decimal
    mass_mg: Decimal
    nonstandard_sku: Decimal
    counter_issue: Decimal
    second_reads: Decimal

    def fields(self):
        return {
            'scan_count': float(self.barcode_reads),
            'expected': float(self.bom_parts),
            'mass_g': float(self.mass_mg) / 1000,
            'variant': float(self.nonstandard_sku),
            'partial': float(self.counter_issue),
            'scan_repeat': float(self.second_reads),
        }

    def validation(self):
        fields = self.fields()
        scan_count = fields['scan_count']
        expected = fields['expected']
        mass_g = fields['mass_g']
        variant = fields['variant']
        partial = fields['partial']
        scan_repeat = fields['scan_repeat']
        first_reads = scan_count-scan_repeat
        custom_share = variant/expected
        count_discrepancy = expected-first_reads
        unit_mass_g = mass_g/expected
        alerts = []
        if first_reads < 0:
            alerts.append(('second_reads', 'REPEAT_EXCEEDS_TOTAL_SCAN'))
        if custom_share>1:
            alerts.append(('nonstandard_sku', 'VARIANTS_EXCEED_PARTS'))
        if count_discrepancy>0 and unit_mass_g>700:
            alerts.append(('mass_mg', 'MASS_INCONSISTENT_WITH_SCANS'))
        return tuple(alerts)


def read_packing_plans(form):
    return PackingPlansSheet(
        barcode_reads=form_number(form, '手持扫条', 'barcode_reads', 2, 36),
        bom_parts=form_number(form, '手持扫条', 'bom_parts', 3, 33),
        mass_mg=form_number(form, '应装清册', 'mass_mg', 150000, 5300000),
        nonstandard_sku=form_number(form, '应装清册', 'nonstandard_sku', 0, 10),
        counter_issue=form_number(form, '磅重补领', 'counter_issue', 0, 9),
        second_reads=form_number(form, '磅重补领', 'second_reads', 0, 14),
    )


def explicit_rows(form):
    if not isinstance(form, Mapping):
        raise MeasureIssue('form', 'FORM_OBJECT_REQUIRED')
    note = read_packing_plans(form)
    return note.fields(), note.validation()


def check_native_history(source):
    if not isinstance(source, Mapping) or 'form' not in source:
        return source
    if any(key in source for key in ('scan_count', 'expected', 'mass_g', 'variant', 'partial', 'scan_repeat')):
        raise MeasureIssue('form','MIXED_FORM_AND_FLAT_READING')
    converted, flags = explicit_rows(source['form'])
    if flags:
        raise MeasureIssue(*flags[0])
    return {**source, **converted}
