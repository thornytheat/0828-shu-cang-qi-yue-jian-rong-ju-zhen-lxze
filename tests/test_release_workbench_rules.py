from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from app.business import DomainIssue
from app.release.board import ReleaseBoard
from app.release.service import ReleaseService


def fields(*specs):
    return [
        dict(field=str(field), data_type=dtype, scale=scale, nullable=nullable, has_default=default)
        for field, dtype, scale, nullable, default in specs
    ]


WIDEN_WRITE = fields((1, 1, 0, 0, 0))
WIDEN_READER = fields((1, 2, 0, 0, 0))
BREAKING_READER = fields((1, 3, 0, 0, 0))


def test_every_active_read_version_must_be_compatible():
    board = ReleaseBoard()
    board.register_write_version('orders', 'w2', WIDEN_WRITE)
    board.register_read_version('orders', 'r-compatible', WIDEN_READER)
    board.register_read_version('orders', 'r-breaking', BREAKING_READER)

    check = board.check('orders', 'w2')

    assert check['compatible'] is False
    assert check['blocking_read_versions'] == ['r-breaking']
    with pytest.raises(DomainIssue) as caught:
        board.sign(check['id'])
    assert caught.value.code == 'UNRESOLVED_ISSUES'


def test_retire_after_check_invalidates_original_conclusion():
    board = ReleaseBoard()
    board.register_write_version('orders', 'w2', WIDEN_WRITE)
    board.register_read_version('orders', 'r1', WIDEN_READER)
    check = board.check('orders', 'w2')
    assert check['compatible'] is True

    board.retire_read_version('orders', 'r1')

    with pytest.raises(DomainIssue, match='STALE_CHECK'):
        board.sign(check['id'])

    recheck = board.check('orders', 'w2')
    assert recheck['read_generation'] > check['read_generation']
    assert board.sign(recheck['id'])['status'] == 'EFFECTIVE'


def test_restore_after_check_invalidates_original_conclusion():
    board = ReleaseBoard()
    board.register_write_version('orders', 'w2', WIDEN_WRITE)
    board.register_read_version('orders', 'r1', WIDEN_READER, status='RETIRED')
    check = board.check('orders', 'w2')
    assert check['active_read_versions'] == []

    board.restore_read_version('orders', 'r1')

    with pytest.raises(DomainIssue, match='STALE_CHECK'):
        board.sign(check['id'])
    recheck = board.check('orders', 'w2')
    assert recheck['compatible'] is True


def test_concurrent_candidates_have_one_winner_but_other_tables_release(tmp_path):
    service = ReleaseService(tmp_path / 'release.db')
    for table in ('shared', 'only-a', 'only-b'):
        service.create_table(table)
        service.register_read_version(table, 'r1', WIDEN_READER)
    service.register_write_version('shared', 'wa', WIDEN_WRITE)
    service.register_write_version('shared', 'wb', WIDEN_WRITE)
    service.register_write_version('only-a', 'wa', WIDEN_WRITE)
    service.register_write_version('only-b', 'wb', WIDEN_WRITE)

    checks = {
        (table, version): service.check(table, version)['id']
        for table, version in (
            ('shared', 'wa'), ('shared', 'wb'), ('only-a', 'wa'), ('only-b', 'wb')
        )
    }
    start = Barrier(2)

    def batch_a():
        start.wait(3)
        return service.submit_batch('batch-a', [
            {'table': 'shared', 'write_version': 'wa', 'check_id': checks['shared', 'wa']},
            {'table': 'only-a', 'write_version': 'wa', 'check_id': checks['only-a', 'wa']},
        ])

    def batch_b():
        start.wait(3)
        return service.submit_batch('batch-b', [
            {'table': 'shared', 'write_version': 'wb', 'check_id': checks['shared', 'wb']},
            {'table': 'only-b', 'write_version': 'wb', 'check_id': checks['only-b', 'wb']},
        ])

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(lambda fn: fn(), [batch_a, batch_b]))

    reports = {report['id']: report for report in (first, second)}
    shared = []
    independent = []
    for report in reports.values():
        for item in report['items']:
            if item['table'] == 'shared':
                shared.append(item)
            else:
                independent.append(item)

    assert sorted(item['status'] for item in shared) == ['FAILED', 'RELEASED']
    assert {item['code'] for item in shared if not item['ok']} == {'WRITE_VERSION_CONFLICT'}
    assert all(item['status'] == 'RELEASED' for item in independent)
    assert service.table('shared')['effective_write_version'] in {'wa', 'wb'}
    assert service.table('only-a')['effective_write_version'] == 'wa'
    assert service.table('only-b')['effective_write_version'] == 'wb'


def test_http_check_stale_and_table_release_routes(client):
    table = 'http_orders'
    write_fields = [{'field': '1', 'data_type': 1, 'scale': 0, 'nullable': 0, 'has_default': 0}]
    read_fields = [{'field': '1', 'data_type': 2, 'scale': 0, 'nullable': 0, 'has_default': 0}]
    client.post('/api/tables', json={'table': table})
    client.post(f'/api/tables/{table}/write-versions', json={'version': 'w1', 'fields': write_fields})
    client.post(f'/api/tables/{table}/read-versions', json={'version': 'r1', 'fields': read_fields})

    checked = client.post(f'/api/tables/{table}/check', json={'write_version': 'w1'})
    assert checked.status_code == 200 and checked.json['compatible'] is True

    retired = client.post(f'/api/tables/{table}/read-versions/r1/retire')
    assert retired.status_code == 200 and retired.json['status'] == 'RETIRED'

    stale = client.post(f'/api/release/checks/{checked.json["id"]}/release', json={})
    assert stale.status_code == 409 and stale.json['code'] == 'STALE_CHECK'

    recheck = client.post(f'/api/tables/{table}/check', json={'write_version': 'w1'})
    released = client.post(f'/api/tables/{table}/release', json={'check_id': recheck.json['id']})
    assert released.status_code == 200 and released.json['effective'] is True
