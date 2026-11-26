from dataclasses import replace

from hingepack.bench_recount.contracts import RISK_CUTOFF
from hingepack.bench_recount.service import plan_jobs, revise_plan
from hingepack.bench_recount import RevisionDesk, export_seal
from hingepack.kit_evaluation.contracts import Assessment
from hingepack.packing_plans.revision import RevisionBook


def _candidate(prediction, key, **values):
    raw = replace(prediction, key=key, cohort=values.pop('cohort', '标准门'),
                  input_values=values.pop('input_values', (19.0, 18.0, 2725.0, 5.0, 4.5, 7.0)))
    return Assessment(raw, RISK_CUTOFF * 2, None, None, False)


def test_lowered_dispatched_ticket_keeps_seat(prediction):
    records = [_candidate(prediction, str(i)) for i in range(3)]
    plan = plan_jobs(records, (), 5, 'focus')
    assert all(job.state == '已分派' for job in plan.jobs if job.key in {'0', '1'})

    lowered = [replace(records[0], estimate=0.01)]
    revised = revise_plan(plan, lowered, (), 5, 'focus')
    job = next(job for job in revised.jobs if job.key == '0')
    assert job.state == '已分派'
    assert job.estimate == 0.01
    assert revised.balance == plan.balance


def test_hard_or_untrusted_dispatch_releases_and_backfills(prediction):
    records = [_candidate(prediction, str(i)) for i in range(8)]
    plan = plan_jobs(records, (), 5, 'focus')

    hard_raw = replace(prediction, key='0', cohort='标准门',
                       input_values=(13, 17, 1800, 4, 2, 13))
    revised = revise_plan(plan, [Assessment(hard_raw, 0.01, None, None, False)], (), 5, 'focus')
    hard = next(job for job in revised.jobs if job.key == '0')
    assert hard.state == '暂停' and hard.reason == 'REPEAT_SCAN'
    assert next(job for job in revised.jobs if job.key == '2').state == '已分派'
    assert sum(job.cost for job in revised.jobs if job.state == '已分派') + revised.balance == 5

    uncertain = revise_plan(plan, [replace(records[0], uncertain=True)], (), 5, 'focus')
    assert next(job for job in uncertain.jobs if job.key == '0').state == '人工判读'
    assert next(job for job in uncertain.jobs if job.key == '2').state == '已分派'


def test_conflict_keeps_original_job(prediction):
    records = [_candidate(prediction, str(i)) for i in range(4)]
    plan = plan_jobs(records, (), 5, 'focus')
    original = next(job for job in plan.jobs if job.key == '0')
    revised = revise_plan(plan, [replace(records[0], estimate=0.9)], (), 5, 'focus',
                          conflicts={'0'})
    assert next(job for job in revised.jobs if job.key == '0') == original
    assert revised.conflicts == ('0',)


def test_retry_token_returns_same_seat_plan(prediction):
    records = [_candidate(prediction, str(i)) for i in range(8)]
    plan = plan_jobs(records, (), 5, 'focus')
    desk = RevisionDesk(plan)
    change = [replace(records[0], uncertain=True)]
    first = desk.apply(change, request_id='retry-1')
    second = desk.apply(change, request_id='retry-1')
    assert first is second
    assert desk.balance == first.balance == 1


def test_seal_export_uses_revised_roster_and_balance(prediction):
    records = [_candidate(prediction, str(i)) for i in range(8)]
    plan = plan_jobs(records, (), 5, 'focus')
    revised = revise_plan(plan, [replace(records[0], uncertain=True)], (), 5, 'focus')
    seal = export_seal(revised)
    assert seal['balance'] == revised.balance
    assert seal['dispatched'] == {job.key: job.cost for job in revised.jobs if job.state == '已分派'}


def test_revision_book_ignores_old_and_conflicting_readings(observation):
    book = RevisionBook.from_records([observation])
    # Move to a newer revision, then an out-of-order old arrival.
    second = book.receive({**observation, 'revision': 2, 'mass_g': observation['mass_g'] + 10})
    assert second.applied
    stale = book.receive({**observation, 'revision': 1, 'mass_g': 999})
    assert stale.stale and book.records[observation['key']].revision == 2

    conflict = book.receive({**observation, 'revision': 2, 'mass_g': observation['mass_g'] + 20})
    assert conflict.conflict
    assert conflict.record.mass_g == observation['mass_g'] + 10
