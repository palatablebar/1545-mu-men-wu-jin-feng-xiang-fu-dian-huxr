from argparse import ArgumentParser
from functools import lru_cache
import json
from pathlib import Path
from flask import Blueprint, Flask, current_app, request, render_template
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge, UnsupportedMediaType

from .pipeline import DISPLAY, MODULES, RUN_DOCUMENTS, execute, open_fixture, preview
from .workbench import ShiftWorkbench, revision_report

routes = Blueprint('hingepack', __name__)
CACHE = lru_cache(maxsize=10)(preview)
WORKBENCHES = {}
REVISION_FIELDS = {
    'change', 'changes', 'revision', 'revisions', 'update', 'updates',
    'amendment', 'amendments', 'change_order', 'change_orders',
    'floor_update', 'floor_updates', 'recheck',
    'request_id', 'idempotency_key', 'run_id', 'prior_run_id', 'same_zone',
}


def failure(message, status=422, code='INVALID_BATCH'):
    return {'code':code, 'message':message},status


def seating(quantity, mode):
    if type(quantity) is not int or not 1 <= quantity <= 60:
        raise ValueError('复核额度限 1 至 60 的整数')
    if mode not in ('balanced','focus'):
        raise ValueError('派单模式不可用')
    return quantity,mode


@routes.route('/')
def home():
    return render_template('desk.html',display=DISPLAY,modules=MODULES)


@routes.route('/health')
def health():
    return dict(status='ok',service='hingepack')


@routes.route('/api/hingepack/overview')
def overview():
    return CACHE()


@routes.post('/api/hingepack/run')
def run_case():
    try:
        request_data=request.get_json()
    except (BadRequest,UnsupportedMediaType):
        return failure('应采用 JSON 单据',400,'INVALID_JSON')
    if not isinstance(request_data,dict):
        return failure('请求体应为 JSON 对象')
    fields=set(request_data)
    if fields-{'capacity','strategy','records','as_of'}-REVISION_FIELDS:
        return failure('包含不支持的字段')
    if fields & REVISION_FIELDS:
        return revise_case()
    try:
        stock,method=seating(request_data.get('capacity',12),request_data.get('strategy','balanced'))
        if 'records' in fields:
            return execute(request_data['records'],stock,method,as_of=request_data.get('as_of',96))
        if 'as_of' in fields:
            raise ValueError('调整截止日时需一并提交单据')
        return CACHE(stock,method)
    except ValueError as invalid:
        return failure(str(invalid))


@routes.post('/api/hingepack/revise')
@routes.post('/api/hingepack/revision')
@routes.post('/api/hingepack/revisions')
@routes.post('/api/hingepack/change')
@routes.post('/api/hingepack/changes')
@routes.post('/api/hingepack/change-order')
@routes.post('/api/hingepack/recheck')
def revise_case():
    try:
        request_data = request.get_json()
    except (BadRequest, UnsupportedMediaType):
        return failure('应采用 JSON 改单', 400, 'INVALID_JSON')
    if not isinstance(request_data, dict):
        return failure('请求体应为 JSON 对象')
    fields = set(request_data)
    if fields - {'capacity', 'strategy', 'records', 'as_of'} - REVISION_FIELDS:
        return failure('包含不支持的字段')
    try:
        stock, method = seating(request_data.get('capacity', 12), request_data.get('strategy', 'balanced'))
        as_of = request_data.get('as_of', 96)
        if type(as_of) is not int or not 91 <= as_of <= 3650:
            raise ValueError('截止日须为第 91 日至第 3650 日之间的整数')
        run_token = request_data.get('run_id') or request_data.get('prior_run_id')
        idempotency = (request_data.get('request_id') or request_data.get('idempotency_key')
                       or request.headers.get('Idempotency-Key') or request.headers.get('X-Request-ID'))
        cache_key = run_token or (f'idempotency:{idempotency}' if idempotency else None)
        bench = WORKBENCHES.get(cache_key) if cache_key else None
        if bench is None:
            if 'records' in request_data:
                records = request_data['records']
            elif run_token in RUN_DOCUMENTS:
                records, as_of = RUN_DOCUMENTS[run_token]
            else:
                fixture = open_fixture()
                records = fixture['records']
                as_of = fixture.get('as_of', as_of)
            if not isinstance(records, list) or not 1 <= len(records) <= 2500:
                raise ValueError('单据批次须包含 1 到 2500 条记录')
            bench = ShiftWorkbench(records, stock, method, as_of)
            if cache_key:
                WORKBENCHES[cache_key] = bench
        changes = None
        for name in ('changes', 'change', 'revisions', 'revision', 'updates', 'update',
                     'amendments', 'amendment', 'change_orders', 'change_order',
                     'floor_updates', 'floor_update', 'recheck'):
            if name in request_data:
                changes = request_data[name]
                break
        result = bench.revise(
            changes or (),
            request_id=idempotency,
            same_zone=bool(request_data.get('same_zone', False)),
        )
        report = revision_report(result)
        if run_token:
            report['prior_run_id'] = run_token
        if idempotency:
            report['request_id'] = idempotency
        return report
    except ValueError as invalid:
        return failure(str(invalid))


@routes.post('/api/hingepack/export')
@routes.post('/api/hingepack/seal-export')
@routes.post('/api/hingepack/seal/export')
def export_case():
    response = revise_case()
    if isinstance(response, tuple):
        return response
    return response['export']


@routes.route('/api/hingepack/stages/<stage>')
def phase(stage):
    known=dict((entry[0],i) for i,entry in enumerate(MODULES))
    if stage not in known:
        return failure('此处置阶段尚未登记',404,'UNKNOWN_STAGE')
    try:
        number=request.args.get('capacity','12')
        if not number.isascii() or not number.isdecimal() or len(number)>2:
            raise ValueError('复核额度写法不正确')
        result=CACHE(*seating(int(number),request.args.get('strategy','balanced')))
    except ValueError as invalid:
        return failure(str(invalid))
    return dict(result['sections'][known[stage]],run_id=result['run_id'])


def make_app():
    configured=Flask(__name__,static_folder='web/static',template_folder='web/templates')
    configured.config.update(MAX_CONTENT_LENGTH=1_500_000)
    configured.json.sort_keys=False
    configured.register_blueprint(routes)
    configured.register_error_handler(RequestEntityTooLarge,lambda _:failure('导入批次超过 1.5 MB',413,'PAYLOAD_TOO_LARGE'))
    return configured


app=make_app()


def main():
    parser=ArgumentParser(prog='hingepack')
    commands=parser.add_subparsers(required=True,dest='operation')
    web=commands.add_parser('serve')
    web.add_argument('--port',type=int,default=8000)
    local=commands.add_parser('evaluate')
    local.add_argument('--capacity',type=int,default=12)
    local.add_argument('--strategy',choices=('balanced','focus'),default='balanced')
    local.add_argument('--input',type=Path)
    local.add_argument('--output',type=Path)
    action=parser.parse_args()
    if action.operation=='serve':
        from waitress import serve
        CACHE()
        serve(app,listen=f'0.0.0.0:{action.port}',threads=4)
    else:
        try:
            limits=seating(action.capacity,action.strategy)
            if action.input is not None:
                batch=open_fixture(action.input)
                result=execute(batch['records'],*limits,as_of=batch.get('as_of',96))
            else:
                result=CACHE(*limits)
            text=json.dumps(result,ensure_ascii=False,allow_nan=False,indent=2)+'\n'
            if action.output is not None:
                action.output.write_text(text,encoding='utf-8')
            else:
                print(text,end='')
        except (ValueError,OSError) as failure:
            parser.error(str(failure))


if __name__=='__main__':
    main()
