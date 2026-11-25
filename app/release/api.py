from concurrent.futures import ThreadPoolExecutor
import json
from threading import Barrier
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, request

release_api = Blueprint('release_api', __name__, url_prefix='/api')


def service():
    return current_app.extensions['release_service']


def payload():
    data = request.get_json(silent=True)
    if data is None:
        data = request.form.to_dict(flat=True)
    if not isinstance(data, dict):
        # A raw JSON list is valid for batch submission.
        return {'items': data if isinstance(data, list) else []}
    data = {**request.args.to_dict(flat=True), **data}
    for key in ('fields', 'schema', 'write_fields', 'read_versions', 'reads',
                'writes', 'candidates', 'items', 'tables', 'releases'):
        value = data.get(key)
        if isinstance(value, str) and value.strip()[:1] in {'[', '{'}:
            try:
                data[key] = json.loads(value)
            except json.JSONDecodeError:
                pass
    return data


@release_api.get('/release/state')
def release_state():
    return jsonify(service().snapshot())


@release_api.get('/release/tables')
@release_api.get('/tables')
def release_tables():
    tables = service().list_tables()
    return jsonify(items=tables, tables=tables)


@release_api.post('/release/tables')
@release_api.post('/tables')
def create_release_table():
    body = payload()
    if isinstance(body, dict) and 'table' not in body and 'id' in body:
        body['table'] = body['id']
    return jsonify(service().create_table(body))


@release_api.get('/release/tables/<table>')
@release_api.get('/tables/<table>')
def release_table(table):
    return jsonify(service().table(table))


@release_api.post('/release/tables/<table>/write-versions')
@release_api.post('/release/tables/<table>/writes')
@release_api.post('/tables/<table>/write-versions')
@release_api.post('/tables/<table>/candidates')
def add_write_version(table):
    body = payload()
    return jsonify(service().register_write_version({**body, 'table': table}))


@release_api.post('/release/tables/<table>/write-versions/<version>')
@release_api.put('/release/tables/<table>/write-versions/<version>')
@release_api.post('/tables/<table>/write-versions/<version>')
@release_api.put('/tables/<table>/write-versions/<version>')
def put_write_version(table, version):
    body = payload()
    if 'fields' not in body and 'schema' not in body and 'items' in body:
        body['fields'] = body['items']
    body['version'] = version
    return jsonify(service().register_write_version({**body, 'table': table}))


@release_api.post('/release/tables/<table>/read-versions')
@release_api.post('/release/tables/<table>/reads')
@release_api.post('/tables/<table>/read-versions')
def add_read_version(table):
    body = payload()
    return jsonify(service().register_read_version({**body, 'table': table}))


@release_api.post('/release/tables/<table>/read-versions/<version>')
@release_api.put('/release/tables/<table>/read-versions/<version>')
@release_api.post('/tables/<table>/read-versions/<version>')
@release_api.put('/tables/<table>/read-versions/<version>')
def put_read_version(table, version):
    body = payload()
    if 'fields' not in body and 'schema' not in body and 'items' in body:
        body['fields'] = body['items']
    body['version'] = version
    return jsonify(service().register_read_version({**body, 'table': table}))


@release_api.post('/release/tables/<table>/read-versions/<version>/retire')
@release_api.post('/release/tables/<table>/read-versions/<version>/deactivate')
@release_api.post('/release/read-versions/<table>/<version>/retire')
@release_api.post('/tables/<table>/read-versions/<version>/retire')
@release_api.post('/tables/<table>/read-versions/<version>/deactivate')
def retire_read_version(table, version):
    return jsonify(service().retire_read_version(table, version))


@release_api.post('/release/tables/<table>/read-versions/<version>/restore')
@release_api.post('/release/tables/<table>/read-versions/<version>/activate')
@release_api.post('/release/read-versions/<table>/<version>/restore')
@release_api.post('/tables/<table>/read-versions/<version>/restore')
@release_api.post('/tables/<table>/read-versions/<version>/activate')
def restore_read_version(table, version):
    return jsonify(service().restore_read_version(table, version))


@release_api.post('/release/tables/<table>/read-versions/<version>/status')
@release_api.patch('/release/tables/<table>/read-versions/<version>')
@release_api.post('/tables/<table>/read-versions/<version>/status')
@release_api.patch('/tables/<table>/read-versions/<version>')
def update_read_version(table, version):
    body = payload()
    return jsonify(service().update_read_version({**body, 'table': table, 'version': version}))


@release_api.post('/release/tables/<table>/checks')
@release_api.post('/release/tables/<table>/check')
@release_api.post('/release/tables/<table>/verify')
@release_api.post('/release/tables/<table>/recheck')
@release_api.post('/tables/<table>/check')
@release_api.post('/tables/<table>/verify')
@release_api.post('/tables/<table>/recheck')
def check_table(table):
    body = payload()
    return jsonify(service().check({**body, 'table': table}))


@release_api.post('/release/checks/<check_id>/sign')
@release_api.post('/release/checks/<check_id>/release')
@release_api.post('/release/checks/<check_id>/approve')
@release_api.post('/release/checks/<check_id>/commit')
@release_api.post('/checks/<check_id>/release')
@release_api.post('/checks/<check_id>/sign')
def sign_check(check_id):
    body = payload()
    return jsonify(service().sign({**body, 'check_id': check_id}))


@release_api.post('/release/tables/<table>/sign')
@release_api.post('/release/tables/<table>/release')
@release_api.post('/release/tables/<table>/approve')
@release_api.post('/release/tables/<table>/commit')
@release_api.post('/tables/<table>/release')
@release_api.post('/tables/<table>/sign')
@release_api.post('/tables/<table>/approve')
@release_api.post('/tables/<table>/commit')
def sign_table(table):
    body = payload()
    return jsonify(service().sign({**body, 'table': table}))


@release_api.post('/release/batches')
@release_api.post('/release/release-batches')
@release_api.post('/release/submit')
@release_api.post('/release-batches')
@release_api.post('/table-releases')
def submit_release_batch():
    body = request.get_json(silent=True)
    if isinstance(body, list):
        result = service().submit_batch(items=body)
    elif isinstance(body, dict):
        batch_id = body.get('batch_id') or body.get('id')
        items = body.get('items') or body.get('tables') or body.get('releases') or []
        result = service().submit_batch(batch_id, items)
    else:
        result = service().submit_batch()
    return jsonify(result)


@release_api.get('/release/batches/<batch_id>')
@release_api.get('/release-batches/<batch_id>')
def release_batch(batch_id):
    return jsonify(service().get_batch(batch_id))


@release_api.post('/release/check')
@release_api.post('/release/verify')
@release_api.post('/check')
@release_api.post('/verify')
def generic_check():
    body = payload()
    return jsonify(service().check(body))


@release_api.post('/release/sign')
@release_api.post('/release/release')
@release_api.post('/release/approve')
@release_api.post('/release/commit')
@release_api.post('/sign')
@release_api.post('/release')
@release_api.post('/approve')
@release_api.post('/commit')
def generic_sign():
    body = payload()
    if isinstance(body, dict) and (body.get('items') or body.get('tables') or body.get('releases')):
        batch_id = body.get('batch_id') or body.get('id')
        items = body.get('items') or body.get('tables') or body.get('releases')
        return jsonify(service().submit_batch(batch_id, items))
    return jsonify(service().sign(body))


@release_api.patch('/read-versions/<version>')
@release_api.post('/read-versions/<version>/status')
def update_read_version_by_version(version):
    body = payload()
    return jsonify(service().update_read_version({**body, 'version': version}))


@release_api.post('/read-versions/<version>/retire')
@release_api.post('/read-versions/<version>/deactivate')
def retire_read_version_by_version(version):
    body = payload()
    return jsonify(service().retire_read_version(body.get('table') or body.get('table_id'), version))


@release_api.post('/read-versions/<version>/restore')
@release_api.post('/read-versions/<version>/activate')
def restore_read_version_by_version(version):
    body = payload()
    return jsonify(service().restore_read_version(body.get('table') or body.get('table_id'), version))


@release_api.post('/batches')
def submit_batches_alias():
    return submit_release_batch()


@release_api.post('/batches/<batch_id>/release')
@release_api.post('/batches/<batch_id>/sign')
def release_named_batch(batch_id):
    body = payload()
    items = body.get('items') or body.get('tables') or []
    return jsonify(service().submit_batch(batch_id, items))


@release_api.post('/release/demo')
def seed_release_demo():
    return jsonify(seed_demo(service()))


@release_api.post('/release/demo-concurrent')
def seed_concurrent_release_demo():
    svc = service()
    suffix = uuid4().hex[:8]
    shared = f'dw.race_{suffix}.shared'
    only_a = f'dw.race_{suffix}.only_a'
    only_b = f'dw.race_{suffix}.only_b'
    field = [{'field': '1', 'data_type': 3, 'scale': 0, 'nullable': 1, 'has_default': 0}]

    for table in (shared, only_a, only_b):
        svc.create_table(table)
        svc.register_read_version(table, 'r-current', field)

    svc.register_write_version(shared, 'w-batch-a', field)
    svc.register_write_version(shared, 'w-batch-b', field)
    svc.register_write_version(only_a, 'w-a', field)
    svc.register_write_version(only_b, 'w-b', field)

    items_a = [
        {'table': shared, 'write_version': 'w-batch-a'},
        {'table': only_a, 'write_version': 'w-a'},
    ]
    items_b = [
        {'table': shared, 'write_version': 'w-batch-b'},
        {'table': only_b, 'write_version': 'w-b'},
    ]
    for items in (items_a, items_b):
        for item in items:
            check = svc.check(item['table'], item['write_version'])
            item['check_id'] = check['id']

    start = Barrier(2)

    def submit(batch_id, items):
        start.wait(timeout=5)
        return svc.submit_batch(batch_id, items)

    with ThreadPoolExecutor(max_workers=2) as pool:
        future_a = pool.submit(submit, f'demo-a-{suffix}', items_a)
        future_b = pool.submit(submit, f'demo-b-{suffix}', items_b)
        batches = [future_a.result(timeout=10), future_b.result(timeout=10)]

    return jsonify({
        'batches': batches,
        'tables': [svc.table(shared), svc.table(only_a), svc.table(only_b)],
    })


def seed_demo(svc):
    """Create a small deterministic workspace demonstrating all invariants."""
    setup = [
        {
            'table': 'dw.orders',
            'write_version': 'w-20261125',
            'write_fields': [
                {'field': '1', 'data_type': 1, 'scale': 0, 'nullable': 0, 'has_default': 0},
                {'field': '2', 'data_type': 4, 'scale': 6, 'nullable': 1, 'has_default': 0},
            ],
            'readers': [
                ('r-2024', [
                    {'field': '1', 'data_type': 2, 'scale': 0, 'nullable': 0, 'has_default': 0},
                    {'field': '2', 'data_type': 4, 'scale': 6, 'nullable': 1, 'has_default': 0},
                ], 'ACTIVE'),
                ('r-legacy', [
                    {'field': '1', 'data_type': 1, 'scale': 0, 'nullable': 0, 'has_default': 0},
                    {'field': '2', 'data_type': 4, 'scale': 4, 'nullable': 0, 'has_default': 1},
                ], 'ACTIVE'),
            ],
        },
        {
            'table': 'dw.payments',
            'write_version': 'w-20261125',
            'write_fields': [
                {'field': '1', 'data_type': 3, 'scale': 0, 'nullable': 1, 'has_default': 0},
            ],
            'readers': [
                ('r-current', [
                    {'field': '1', 'data_type': 3, 'scale': 0, 'nullable': 1, 'has_default': 0},
                ], 'ACTIVE'),
            ],
        },
        {
            'table': 'dw.shipments',
            'write_version': 'w-batch-b',
            'write_fields': [
                {'field': '7', 'data_type': 2, 'scale': 0, 'nullable': 0, 'has_default': 1},
            ],
            'readers': [
                ('r-current', [
                    {'field': '7', 'data_type': 2, 'scale': 0, 'nullable': 1, 'has_default': 0},
                ], 'ACTIVE'),
            ],
        },
    ]
    for item in setup:
        svc.create_table(item['table'])
        svc.register_write_version(item['table'], item['write_version'], item['write_fields'])
        for version, fields, status in item['readers']:
            svc.register_read_version(item['table'], version, fields, status=status)
        svc.check(item['table'], item['write_version'])
    return svc.snapshot()
