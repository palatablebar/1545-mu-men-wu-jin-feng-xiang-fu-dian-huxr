from hingepack.pipeline import preview
from hingepack.bench_recount.service import operating_ledger


def note(key, measures, *, zone='甲区', state='已分派', estimate=0, hits=(), missing=()):
    return {'key':key,'zone':zone,'state':state,'estimate':estimate,'hits':hits,
            'unmeasured':missing,'measurements':dict(zip(('scan_count', 'expected', 'mass_g', 'variant', 'partial', 'scan_repeat'),measures,strict=True))}


def test_field_plan_is_visible_and_references_real_tickets():
    desk = preview()
    plan = desk['sections'][6]
    assert plan['operating_title'] == '封箱差分簿'
    assert plan['operating_rows']
    scoped = {item['关联单据'] for item in plan['operating_rows'] if '关联单据' in item}
    assert scoped and scoped <= {row['key'] for row in desk['rows']}
    assert all(item['业务安排'] for item in plan['operating_rows'])


def test_duplicate_scans_do_not_credit_extra_hardware():
    overread = note('BX-1',(5,12,1900,4,2,13),state='暂停')
    slip, tally = operating_ledger([overread])
    assert slip['应装减有效码']==12
    assert slip['业务安排']=='拆包倒箱核重'
    assert slip['校验净重偏差克'] is None
    assert tally['短件']==12 and tally['待倒箱']==1
