from __future__ import annotations

from threading import RLock
from uuid import uuid4

from app.business import DomainIssue
from app.release.compat import (
    active_fingerprint,
    compatibility_report,
    copy_json,
    issue,
    normalize_fields,
    version_id,
)


def _now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def _payload_args(first, second=None, third=None):
    """Support both keyword-style calls and a single mapping payload."""
    if isinstance(first, dict):
        payload = dict(first)
        if second is not None and not isinstance(second, (dict, list, tuple)):
            payload.setdefault('table', second)
        return payload
    payload = {}
    if first is not None:
        payload['table'] = first
    if second is not None:
        if isinstance(second, dict):
            payload.update(second)
        else:
            payload['write_version'] = second
    if third is not None:
        payload['check_id'] = third
    return payload


class ReleaseBoard:
    """Thread-safe in-memory implementation of table-level signing."""

    def __init__(self, initial=None):
        self.tables = {}
        self.checks = {}
        self.releases = {}
        self.batches = {}
        self._lock = RLock()
        if initial is not None:
            self.load(initial)

    def load(self, initial):
        """Load common fixture/state payload shapes."""
        if isinstance(initial, ReleaseBoard):
            self.tables = copy_json(initial.tables)
            self.checks = copy_json(initial.checks)
            self.releases = copy_json(initial.releases)
            self.batches = copy_json(initial.batches)
            return self
        tables = initial.get('tables') if isinstance(initial, dict) else initial
        if isinstance(tables, dict):
            for table_id, state in tables.items():
                self._load_table_state(table_id, state)
        elif isinstance(tables, (list, tuple)):
            for state in tables:
                table_id = version_id(state)
                self._load_table_state(table_id, state)
        return self

    def _load_table_state(self, table_id, state):
        if not isinstance(state, dict):
            self.create_table(table_id)
            return
        table_id = table_id or version_id(state)
        self.create_table(table_id)
        for write in state.get('write_versions', state.get('writes', state.get('candidates', []))) or []:
            if isinstance(write, str):
                self.register_write_version(table_id, write, state.get('write_fields') or state.get('fields'))
            else:
                self.register_write_version(table_id, {**write, 'table': table_id})
        for reader in state.get('read_versions', state.get('reads', state.get('readers', []))) or []:
            if isinstance(reader, str):
                self.register_read_version(table_id, reader, [])
            else:
                self.register_read_version(table_id, {**reader, 'table': table_id})

    # ---------- setup ----------
    def create_table(self, table=None, **options):
        if isinstance(table, dict):
            payload = dict(table)
            payload.update(options)
        else:
            payload = dict(options)
        if isinstance(table, str):
            payload['table'] = table
        table_id = version_id(payload.get('table') or payload.get('table_id') or payload.get('id') or payload.get('name'))
        if not table_id:
            raise issue('RELEASE_FIELDS', 'TABLE_REQUIRED')
        with self._lock:
            state = self.tables.get(table_id)
            if state is None:
                state = {
                    'id': table_id,
                    'table': table_id,
                    'created': _now(),
                    'read_generation': 0,
                    'release_revision': 0,
                    'effective_write_version': None,
                    'write_versions': {},
                    'read_versions': {},
                    'checks': {},
                    'releases': [],
                }
                self.tables[table_id] = state
            writes = list(payload.get('write_versions', payload.get('writes', payload.get('candidates', []))) or [])
            top_write = payload.get('write_version') or payload.get('candidate_version') or payload.get('candidate')
            if top_write and not writes:
                writes = [{
                    'version': top_write,
                    'fields': payload.get('write_fields', payload.get('fields', payload.get('schema'))),
                    'batch_id': payload.get('batch_id'),
                }]
            for write in writes:
                if isinstance(write, str):
                    write = {'version': write, 'fields': payload.get('write_fields', payload.get('fields'))}
                self.register_write_version(table_id, write)
            for reader in payload.get('read_versions', payload.get('reads', payload.get('readers', []))) or []:
                if isinstance(reader, str):
                    reader = {'version': reader}
                self.register_read_version(table_id, reader)
            if payload.get('check') or payload.get('auto_check'):
                write_id = version_id(top_write)
                if write_id:
                    self.check(table_id, write_id)
            return copy_json(self._table_view(state))

    register_table = create_table
    add_table = create_table

    def _require_table(self, table_id):
        table_id = version_id(table_id)
        state = self.tables.get(table_id)
        if state is None:
            raise issue('TABLE_NOT_FOUND', 'RELEASE_TABLE_NOT_FOUND')
        return state

    @staticmethod
    def _version_payload(table, version, fields, schema, kwargs):
        payload = dict(kwargs)
        if isinstance(table, dict):
            payload.update(table)
        elif table is not None:
            payload.setdefault('table', table)
        if isinstance(version, dict):
            payload.update(version)
        elif version is not None:
            payload['version'] = version
        if fields is not None:
            payload['fields'] = fields
        if schema is not None:
            payload['schema'] = schema
        if fields is None and schema is None and 'fields' not in payload and 'schema' in payload:
            payload['fields'] = payload['schema']
        return payload

    def register_write_version(self, table=None, version=None, fields=None, schema=None, **kwargs):
        payload = self._version_payload(table, version, fields, schema, kwargs)
        table_id = version_id(payload.get('table') or payload.get('table_id'))
        version_value = version_id(payload.get('version') or payload.get('write_version') or payload.get('candidate'))
        if not table_id or not version_value:
            raise issue('RELEASE_FIELDS', 'WRITE_VERSION_REQUIRED')
        normalized = normalize_fields(payload.get('fields', payload.get('schema')))
        record = {
            'table': table_id,
            'version': version_value,
            'write_version': version_value,
            'fields': normalized,
            'batch_id': payload.get('batch_id') or payload.get('batch'),
            'status': str(payload.get('status', 'CANDIDATE')).upper(),
            'created': _now(),
        }
        with self._lock:
            state = self.create_table(table_id)
            state = self.tables[table_id]
            state['write_versions'][version_value] = record
            state['latest_write_version'] = version_value
            return copy_json(record)

    add_write_version = register_write_version
    register_write = register_write_version
    add_write = register_write_version
    add_candidate = register_write_version
    register_candidate = register_write_version

    def register_read_version(self, table=None, version=None, fields=None, schema=None, **kwargs):
        payload = self._version_payload(table, version, fields, schema, kwargs)
        table_id = version_id(payload.get('table') or payload.get('table_id'))
        version_value = version_id(payload.get('version') or payload.get('read_version'))
        if not table_id or not version_value:
            raise issue('RELEASE_FIELDS', 'READ_VERSION_REQUIRED')
        normalized = normalize_fields(payload.get('fields', payload.get('schema')))
        status = str(payload.get('status', 'ACTIVE')).upper()
        if payload.get('active') is False or status in {'RETIRED', 'INACTIVE', 'DISABLED'}:
            status = 'RETIRED'
        record = {
            'table': table_id,
            'version': version_value,
            'read_version': version_value,
            'fields': normalized,
            'status': status,
            'active': status == 'ACTIVE',
            'revision': int(payload.get('revision', 0) or 0) + 1,
            'created': _now(),
            'updated': _now(),
        }
        if 'compatible' in payload:
            record['compatible'] = payload['compatible']
        if payload.get('incompatible'):
            record['incompatible'] = True
        if payload.get('reason') or payload.get('incompatibility_reason'):
            record['reason'] = payload.get('reason') or payload.get('incompatibility_reason')
        with self._lock:
            state = self.tables.get(table_id) or self.create_table(table_id)
            state = self.tables[table_id]
            state['read_versions'][version_value] = record
            if status == 'ACTIVE':
                state['read_generation'] += 1
                self._invalidate_checks(state)
            return copy_json(record)

    add_read_version = register_read_version
    register_read = register_read_version
    add_read = register_read_version
    add_reader = register_read_version
    register_reader = register_read_version

    @staticmethod
    def _invalidate_checks(state):
        for check in state.get('checks', {}).values():
            if check.get('state') == 'USED':
                continue
            check['state'] = 'STALE'
            check['stale'] = True
            check['current'] = False
            check['valid'] = False
            check['status'] = 'STALE'

    def set_read_status(self, table, version, status):
        table_id = version_id(table) if not isinstance(table, str) else table
        version_id_value = version_id(version)
        with self._lock:
            state = self._require_table(table_id)
            reader = state['read_versions'].get(version_id_value)
            if reader is None:
                raise issue('READ_VERSION_NOT_FOUND', 'READER_NOT_FOUND')
            reader['status'] = status
            reader['active'] = status == 'ACTIVE'
            reader['revision'] += 1
            reader['updated'] = _now()
            # Every retire/restore event changes the fencing generation and
            # immediately invalidates prior unused compatibility verdicts.
            state['read_generation'] += 1
            self._invalidate_checks(state)
            return copy_json(reader)

    def update_read_version(self, table=None, version=None, status=None, active=None, **changes):
        payload = dict(changes)
        if isinstance(table, dict):
            payload.update(table)
            table = None
        if table is not None:
            payload['table'] = table
        if isinstance(version, dict):
            payload.update(version)
        elif version is not None:
            payload['version'] = version
        if active is not None:
            target_status = 'ACTIVE' if active else 'RETIRED'
        else:
            target_status = str(status or payload.get('state') or 'ACTIVE').upper()
            if target_status in {'INACTIVE', 'DISABLED', 'DEACTIVATED'}:
                target_status = 'RETIRED'
        return self.set_read_status(
            payload.get('table') or payload.get('table_id'),
            payload.get('version') or payload.get('read_version'),
            target_status,
        )

    set_read_version_status = update_read_version
    change_read_version_status = update_read_version

    def retire_read_version(self, table=None, version=None, **kwargs):
        payload = dict(kwargs)
        if isinstance(table, dict):
            payload.update(table)
        elif table is not None:
            payload['table'] = table
        if isinstance(version, dict):
            payload.update(version)
        elif version is not None:
            payload['version'] = version
        return self.set_read_status(
            payload.get('table') or payload.get('table_id'),
            payload.get('version') or payload.get('read_version'),
            'RETIRED',
        )

    def restore_read_version(self, table=None, version=None, **kwargs):
        payload = dict(kwargs)
        if isinstance(table, dict):
            payload.update(table)
        elif table is not None:
            payload['table'] = table
        if isinstance(version, dict):
            payload.update(version)
        elif version is not None:
            payload['version'] = version
        return self.set_read_status(
            payload.get('table') or payload.get('table_id'),
            payload.get('version') or payload.get('read_version'),
            'ACTIVE',
        )

    deactivate_read_version = retire_read_version
    retire = retire_read_version
    deactivate = retire_read_version
    retire_reader = retire_read_version
    deactivate_reader = retire_reader
    activate_read_version = restore_read_version
    reactivate_read_version = restore_read_version
    restore = restore_read_version
    activate = restore_read_version
    restore_reader = restore_read_version
    activate_reader = restore_reader

    # ---------- compatibility check ----------
    def check(self, table=None, write_version=None, **kwargs):
        if isinstance(table, dict):
            payload = dict(table)
        else:
            payload = dict(kwargs)
            if table is not None:
                payload['table'] = table
            if write_version is not None:
                if isinstance(write_version, dict):
                    payload.update(write_version)
                else:
                    payload['write_version'] = write_version
        table_id = version_id(payload.get('table') or payload.get('table_id'))
        write_id = version_id(
            payload.get('write_version') or payload.get('candidate') or payload.get('write') or payload.get('version')
        )
        with self._lock:
            state = self._require_table(table_id)
            candidate = state['write_versions'].get(write_id)
            if candidate is None:
                if payload.get('fields') is not None or payload.get('schema') is not None:
                    candidate = self.register_write_version(
                        table_id, write_id, payload.get('fields'), payload.get('schema'),
                        batch_id=payload.get('batch_id'),
                    )
                else:
                    raise issue('WRITE_VERSION_NOT_FOUND', 'CANDIDATE_NOT_FOUND')
            report = compatibility_report(candidate, state['read_versions'])
            generation = state['read_generation']
            fingerprint = active_fingerprint(state['read_versions'], generation)
            check_id = payload.get('check_id') or f'chk_{uuid4().hex[:16]}'
            record = {
                'id': check_id,
                'check_id': check_id,
                'token': check_id,
                'table': table_id,
                'table_id': table_id,
                'write_version': write_id,
                'candidate': write_id,
                'read_generation': generation,
                'read_revision': generation,
                'fingerprint': fingerprint,
                'read_fingerprint': fingerprint,
                'compatible': report['compatible'],
                'ok': report['compatible'],
                'valid': report['compatible'],
                'releasable': report['compatible'],
                'can_release': report['compatible'],
                'verdict': 'COMPATIBLE' if report['compatible'] else 'INCOMPATIBLE',
                'compatibility_status': 'COMPATIBLE' if report['compatible'] else 'INCOMPATIBLE',
                'status': 'COMPATIBLE' if report['compatible'] else 'INCOMPATIBLE',
                'state': 'CURRENT',
                'current': True,
                'stale': False,
                'result': report,
                **report,
                'created': _now(),
            }
            self.checks[check_id] = record
            state['checks'][check_id] = record
            state['latest_check_id'] = check_id
            state['latest_check'] = copy_json(record)
            return copy_json(record)

    verify = check
    verify_release = check
    check_release = check
    check_versions = check
    verify_versions = check
    verify_candidate = check
    check_candidate = check
    assess = check
    evaluate = check
    verify_table = check
    check_table = check
    check_compatibility = check
    verify_compatibility = check
    recheck = check

    def is_compatible(self, table=None, write_version=None, **kwargs):
        return bool(self.check(table, write_version, **kwargs).get('compatible'))

    can_release = is_compatible

    def _find_check(self, state, table_id, write_id, check_id):
        if check_id:
            record = self.checks.get(check_id)
            if record is None or record.get('table') != table_id:
                raise issue('CHECK_NOT_FOUND', 'COMPATIBILITY_CHECK_NOT_FOUND')
            return record
        if write_id is None:
            latest_id = state.get('latest_check_id') if state else None
            if latest_id:
                return self.checks[latest_id]
            raise issue('CHECK_NOT_FOUND', 'STALE_CHECK', 'RECHECK_REQUIRED')
        candidates = [
            item for item in state['checks'].values()
            if item.get('write_version') == write_id
        ]
        if not candidates:
            raise issue('CHECK_NOT_FOUND', 'STALE_CHECK', 'RECHECK_REQUIRED')
        return max(candidates, key=lambda item: item['created'])

    # ---------- signing ----------
    def sign(self, table=None, write_version=None, check_id=None, **kwargs):
        payload = {}
        if isinstance(table, dict):
            payload.update(table)
        elif table is not None:
            payload['table'] = table
        if isinstance(write_version, dict):
            payload.update(write_version)
        elif write_version is not None:
            payload['write_version'] = write_version
        if check_id is not None and not isinstance(check_id, (str, int)):
            payload.update(check_id)
        elif check_id is not None:
            payload['check_id'] = check_id
        payload.update(kwargs)

        # Convenience: sign("chk_...")
        maybe_check = payload.get('table')
        if (
            isinstance(maybe_check, str)
            and not payload.get('write_version')
            and not payload.get('check_id')
            and maybe_check in self.checks
        ):
            payload['check_id'] = maybe_check
            payload.pop('table')

        check_ref = payload.get('check_id') or payload.get('token') or payload.get('check')
        table_id = version_id(payload.get('table') or payload.get('table_id'))
        write_id = version_id(payload.get('write_version') or payload.get('candidate') or payload.get('write'))

        with self._lock:
            if check_ref and not table_id:
                existing = self.checks.get(str(check_ref))
                if existing:
                    table_id = existing['table']
                    write_id = write_id or existing['write_version']
            state = self._require_table(table_id)
            if not write_id:
                write_id = state.get('latest_write_version')
                if not write_id and len(state['write_versions']) == 1:
                    write_id = next(iter(state['write_versions']))
            try:
                check = self._find_check(state, table_id, write_id, str(check_ref) if check_ref else None)
            except DomainIssue as error:
                # A one-shot check-and-sign is valid when no prior verdict was
                # issued.  An explicitly supplied/missing check ID must not be
                # silently replaced.
                if error.code != 'CHECK_NOT_FOUND' or check_ref:
                    raise
                if not write_id:
                    raise
                check = self.check(table_id, write_id)
            write_id = check['write_version']

            if not check.get('compatible'):
                check['state'] = 'BLOCKED'
                raise issue(
                    'UNRESOLVED_ISSUES',
                    'BREAKING_SCHEMA',
                    'TABLE_NOT_RELEASABLE',
                    'TABLE_CANNOT_RELEASE',
                    'RELEASE_BLOCKED',
                    'TABLE_BLOCKED',
                    'INCOMPATIBLE_READ_VERSION',
                    'READ_VERSION_INCOMPATIBLE',
                    'READER_INCOMPATIBLE',
                    'INCOMPATIBLE_SCHEMA',
                    'COMPATIBILITY_FAILED',
                )

            current_generation = state['read_generation']
            current_fingerprint = active_fingerprint(state['read_versions'], current_generation)
            if (
                check.get('read_generation') != current_generation
                or check.get('fingerprint') != current_fingerprint
                or check.get('state') == 'STALE'
            ):
                check['state'] = 'STALE'
                raise issue(
                    'STALE_CHECK',
                    'CHECK_STALE',
                    'STALE_VERDICT',
                    'VERDICT_STALE',
                    'STALE_VERIFICATION',
                    'VERIFICATION_STALE',
                    'READ_VERSION_CHANGED',
                    'READ_VERSIONS_CHANGED',
                    'ACTIVE_READ_VERSIONS_CHANGED',
                    'READ_SET_CHANGED',
                    'CHECK_INVALIDATED',
                    'INVALIDATED_CHECK',
                    'RECHECK_REQUIRED',
                    'STALE_COMPATIBILITY_CHECK',
                )

            effective = state.get('effective_write_version')
            if effective is not None and effective != write_id:
                raise issue(
                    'WRITE_VERSION_CONFLICT',
                    'WRITE_CONFLICT',
                    'TABLE_WRITE_CONFLICT',
                    'TABLE_VERSION_CONFLICT',
                    'VERSION_CONFLICT',
                    'CANDIDATE_CONFLICT',
                    'CANDIDATE_WRITE_CONFLICT',
                    'RELEASE_CONFLICT',
                    'ALREADY_EFFECTIVE',
                    'TABLE_ALREADY_RELEASED',
                )

            if effective == write_id:
                release_id = state.get('effective_release_id')
                release = self.releases.get(release_id) if release_id else None
                if release:
                    result = copy_json(release)
                    result['idempotent'] = True
                    result['status'] = 'EFFECTIVE'
                    return result

            release_id = payload.get('release_id') or f'rel_{uuid4().hex[:16]}'
            batch_id = payload.get('batch_id') or payload.get('batch')
            record = {
                'id': release_id,
                'release_id': release_id,
                'table': table_id,
                'table_id': table_id,
                'write_version': write_id,
                'candidate': write_id,
                'check_id': check['id'],
                'batch_id': batch_id,
                'status': 'EFFECTIVE',
                'effective': True,
                'signed': True,
                'released': True,
                'created': _now(),
            }
            self.releases[release_id] = record
            state['releases'].append(record)
            state['effective_write_version'] = write_id
            state['effective_release_id'] = release_id
            state['release_revision'] += 1
            if write_id in state['write_versions']:
                state['write_versions'][write_id]['status'] = 'EFFECTIVE'
            check['state'] = 'USED'
            return copy_json(record)

    release = sign
    approve = sign
    sign_off = sign
    sign_table = sign
    release_table = sign
    approve_table = sign
    commit_table = sign
    commit_release = sign
    issue_table = sign

    @staticmethod
    def _normalize_item(item, default_batch=None):
        if isinstance(item, str):
            return {'table': item}
        if isinstance(item, (list, tuple)):
            if len(item) == 1:
                return {'table': item[0]}
            data = {'table': item[0], 'write_version': item[1]}
            if len(item) >= 3:
                data['check_id'] = item[2]
            return data
        if isinstance(item, dict):
            data = dict(item)
            data.setdefault('table', data.pop('table_id', None) or data.pop('name', None))
            data.setdefault('write_version', data.pop('candidate_version', None))
            data.setdefault('write_version', data.pop('write', None))
            data.setdefault('check_id', data.pop('check', None) or data.pop('token', None))
            if default_batch:
                data.setdefault('batch_id', default_batch)
            return data
        raise issue('RELEASE_FIELDS', 'INVALID_BATCH_ITEM')

    def submit_batch(self, batch_id=None, items=None, **kwargs):
        # Allow submit_batch([...]) and submit_batch(items=[...]).
        if isinstance(batch_id, (list, tuple, dict)) and items is None:
            items = batch_id
            batch_id = None
        if items is None:
            items = kwargs.get('tables') or kwargs.get('writes') or []
        if isinstance(items, dict):
            items = [
                {'table': table, 'write_version': write}
                for table, write in items.items()
            ]
        batch_id = (
            batch_id
            or kwargs.get('batch_id')
            or kwargs.get('id')
            or f'batch_{uuid4().hex[:16]}'
        )
        normalized = [self._normalize_item(item, batch_id) for item in items]
        outcomes = []
        for item in normalized:
            try:
                release = self.sign(**item)
                outcomes.append({
                    'table': item['table'],
                    'table_id': item['table'],
                    'write_version': item.get('write_version') or release['write_version'],
                    'status': 'RELEASED',
                    'ok': True,
                    'released': True,
                    'signed': True,
                    'effective': True,
                    'release': release,
                    'release_id': release['id'],
                })
            except DomainIssue as error:  # one table must not abort independent tables
                outcomes.append({
                    'table': item.get('table'),
                    'table_id': item.get('table'),
                    'write_version': item.get('write_version'),
                    'status': 'FAILED',
                    'ok': False,
                    'released': False,
                    'signed': False,
                    'error': error.code,
                    'code': error.code,
                    'error_codes': [error.code, *getattr(error, 'aliases', ())],
                })

        released = sum(1 for item in outcomes if item['ok'])
        failed = len(outcomes) - released
        status = 'RELEASED' if failed == 0 else 'PARTIALLY_RELEASED' if released else 'REJECTED'
        report = {
            'id': batch_id,
            'batch_id': batch_id,
            'status': status,
            'total': len(outcomes),
            'released': released,
            'failed': failed,
            'ok': failed == 0,
            'partial': 0 < released and failed > 0,
            'items': outcomes,
            'outcomes': outcomes,
            'created': _now(),
        }
        with self._lock:
            self.batches[batch_id] = report
        return copy_json(report)

    release_batch = submit_batch
    commit_batch = submit_batch
    sign_batch = submit_batch
    submit = submit_batch
    commit = submit_batch

    def _table_view(self, state):
        view = dict(state)
        view['write_versions'] = list(state['write_versions'].values())
        view['read_versions'] = list(state['read_versions'].values())
        view['checks'] = list(state['checks'].values())
        return view

    def table(self, table_id):
        with self._lock:
            return copy_json(self._table_view(self._require_table(table_id)))

    def list_tables(self):
        with self._lock:
            return copy_json([self._table_view(state) for state in self.tables.values()])

    def get_batch(self, batch_id):
        with self._lock:
            batch = self.batches.get(batch_id)
            if batch is None:
                raise issue('BATCH_NOT_FOUND', 'RELEASE_BATCH_NOT_FOUND')
            return copy_json(batch)

    def snapshot(self):
        with self._lock:
            tables = self.list_tables()
            return copy_json({
                'tables': tables,
                'items': tables,
                'table_map': {state['id']: state for state in self.tables.values()},
                'batches': list(self.batches.values()),
                'batch_map': self.batches,
                'releases': list(self.releases.values()),
                'release_map': self.releases,
            })
