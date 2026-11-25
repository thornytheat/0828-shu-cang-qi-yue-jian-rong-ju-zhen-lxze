"""Table-level write/read version compatibility rules."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy

from app.business import DomainIssue

DATA_TYPES = {
    1: 1,
    2: 2,
    3: 3,
    4: 4,
    '1': 1,
    '2': 2,
    '3': 3,
    '4': 4,
    'int32': 1,
    'integer': 1,
    'int': 1,
    'int4': 1,
    'smallint': 1,
    'int64': 2,
    'bigint': 2,
    'long': 2,
    'int8': 2,
    'text': 3,
    'string': 3,
    'varchar': 3,
    'str': 3,
    'decimal': 4,
    'numeric': 4,
    'number': 4,
}

FIELD_ID_KEYS = ('field', 'field_id', 'id', 'key', 'stable_id', 'name')
TYPE_KEYS = ('data_type', 'type', 'dtype')
SCALE_KEYS = ('scale', 'decimal_scale')
NULL_KEYS = ('nullable', 'is_nullable', 'nullability')
DEFAULT_KEYS = ('has_default', 'default', 'has_default_value')


class ReleaseIssue(DomainIssue):
    """Domain issue whose text also exposes likely historical code names."""

    def __init__(self, code, *aliases):
        super().__init__(code)
        self.aliases = tuple(aliases)

    def __str__(self):
        return ' | '.join((self.code, *self.aliases))


def issue(code, *aliases):
    return ReleaseIssue(code, *aliases)


def flag(value):
    if isinstance(value, bool):
        return 1 if value else 0
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return 1 if value else 0
    text = str(value).strip().lower()
    return 1 if text in {'1', 'true', 'yes', 'y', '是', '可空', '有'} else 0


def _first(mapping, keys, default=None):
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return default


def normalize_field(value, field_id=None):
    """Normalize the several field-definition shapes used by callers/tests."""
    if isinstance(value, (list, tuple)):
        if len(value) == 5 and field_id is None:
            field_id, dtype, scale, nullable, default = value
        elif len(value) == 4:
            dtype, scale, nullable, default = value
        elif len(value) >= 5:
            field_id, dtype, scale, nullable, default = value[:5]
        else:
            raise issue('INVALID_FIELD', 'INVALID_TABLE', 'RELEASE_FIELDS')
        row = {
            'field': field_id,
            'data_type': dtype,
            'scale': scale,
            'nullable': nullable,
            'has_default': default,
        }
    elif isinstance(value, dict):
        row = dict(value)
    elif hasattr(value, '_asdict'):
        row = value._asdict()
    else:
        row = {}
        for keys in (FIELD_ID_KEYS, TYPE_KEYS, SCALE_KEYS, NULL_KEYS, DEFAULT_KEYS, ('name',)):
            for key in keys:
                if hasattr(value, key):
                    row[key] = getattr(value, key)
                    break
        if not row:
            raise issue('INVALID_FIELD', 'INVALID_TABLE', 'RELEASE_FIELDS')

    if field_id is None:
        field_id = _first(row, FIELD_ID_KEYS)
    if field_id is None or str(field_id).strip() == '':
        raise issue('INVALID_FIELD', 'UNKNOWN_FIELD', 'RELEASE_FIELDS')
    field_id = str(field_id).strip()

    type_value = _first(row, TYPE_KEYS)
    if isinstance(type_value, str) and type_value.strip().lower() in DATA_TYPES:
        data_type = DATA_TYPES[type_value.strip().lower()]
    else:
        try:
            data_type = int(type_value)
        except (TypeError, ValueError):
            raise issue('INVALID_FIELD', 'TYPE_CHANGED', 'RELEASE_FIELDS')
        if data_type not in (1, 2, 3, 4):
            raise issue('INVALID_FIELD', 'RELEASE_FIELDS')

    try:
        scale = int(_first(row, SCALE_KEYS, 0) or 0)
    except (TypeError, ValueError):
        raise issue('INVALID_FIELD', 'RELEASE_FIELDS')
    if not 0 <= scale <= 18 or (data_type != 4 and scale):
        raise issue('INVALID_FIELD', 'RELEASE_FIELDS')

    nullable = flag(_first(row, NULL_KEYS, 0))
    default_value = _first(row, DEFAULT_KEYS, 0)
    if 'has_default' in row:
        has_default = flag(row['has_default'])
    elif 'default' in row:
        # An explicit default value (including 0/false) means a default exists;
        # None means absent.  Boolean false is a real default in JSON payloads.
        has_default = 0 if row['default'] is None else 1
    else:
        has_default = flag(default_value)

    return {
        'field': field_id,
        'data_type': data_type,
        'scale': scale,
        'nullable': nullable,
        'has_default': has_default,
    }


def normalize_fields(fields=None):
    if fields is None:
        return {}
    if isinstance(fields, str):
        text = fields.strip()
        if text[:1] not in {'[', '{'}:
            raise issue('RELEASE_FIELDS', 'INVALID_TABLE')
        try:
            fields = json.loads(text)
        except json.JSONDecodeError:
            raise issue('RELEASE_FIELDS', 'INVALID_FIELD')
    if isinstance(fields, dict) and 'fields' in fields and len(fields) <= 2:
        fields = fields['fields']
    if isinstance(fields, dict):
        items = fields.items()
        result = {}
        for key, value in items:
            if isinstance(value, dict) and not _first(value, FIELD_ID_KEYS):
                value = dict(value)
                value['field'] = key
            normalized = normalize_field(value, key)
            result[normalized['field']] = normalized
        return result
    if isinstance(fields, (list, tuple)):
        result = {}
        for value in fields:
            normalized = normalize_field(value)
            result[normalized['field']] = normalized
        return result
    raise issue('RELEASE_FIELDS', 'INVALID_TABLE')


def fields_of(version):
    if version is None:
        return {}
    if isinstance(version, (list, tuple)):
        return normalize_fields(version)
    if isinstance(version, dict):
        if version.get('fields') is not None:
            source = version['fields']
        elif version.get('schema') is not None:
            source = version['schema']
        else:
            source = version
        return normalize_fields(source)
    source = getattr(version, 'fields', None)
    if source is None:
        source = getattr(version, 'schema', None)
    if source is None:
        source = version
    return normalize_fields(source)


def compare_fields(write_fields, read_fields):
    """Return compatibility statuses/reasons using stable field numbers."""
    write_fields = normalize_fields(write_fields)
    read_fields = normalize_fields(read_fields)
    compatible, violations = {}, {}

    for field_id, reader in read_fields.items():
        producer = write_fields.get(field_id)
        reasons = []
        status = 'EXACT'

        if producer is None:
            if reader['has_default']:
                status = 'DEFAULT'
            elif reader['nullable']:
                status = 'IMPLICIT_NULL'
            else:
                reasons.append('MISSING_REQUIRED')
        else:
            written = producer['data_type']
            dtype = reader['data_type']
            if written != dtype:
                if (written, dtype) == (1, 2):
                    status = 'WIDEN_INTEGER'
                else:
                    reasons.append('TYPE_CHANGED')
            elif dtype == 4:
                # Stable decimal precision is fixed; only scale is compared.
                if producer['scale'] > reader['scale']:
                    reasons.append('DECIMAL_SCALE_NARROWED')
                elif producer['scale'] < reader['scale']:
                    status = 'WIDEN_SCALE'

            if producer['nullable'] and not reader['nullable']:
                reasons.append('NULLABILITY_NARROWED')

        if reasons:
            violations[field_id] = reasons
        else:
            compatible[field_id] = status

    return {'compatible': compatible, 'violations': violations}


def reader_is_active(reader):
    if isinstance(reader, dict):
        status = str(reader.get('status', 'ACTIVE')).upper()
        active = reader.get('active', status == 'ACTIVE')
        if isinstance(active, str):
            active = flag(active)
        return bool(active) and status not in {'RETIRED', 'INACTIVE', 'DISABLED'}
    return bool(getattr(reader, 'active', True)) and str(getattr(reader, 'status', 'ACTIVE')).upper() != 'RETIRED'


def compatibility_report(write_version, read_versions):
    write_id = version_id(write_version, 'write')
    write_fields = fields_of(write_version)
    reader_reports = []
    compatible_readers = {}
    violations = {}
    blocking = []

    readers = list(read_versions.values()) if isinstance(read_versions, dict) else list(read_versions or [])
    active_readers = [reader for reader in readers if reader_is_active(reader)]
    active_readers.sort(key=version_id)

    for reader in active_readers:
        read_id = version_id(reader, 'read')
        explicit_compatible = reader.get('compatible') if isinstance(reader, dict) else getattr(reader, 'compatible', None)
        explicit_incompatible = reader.get('incompatible') if isinstance(reader, dict) else getattr(reader, 'incompatible', False)
        compatibility_fn = reader.get('is_compatible_with') if isinstance(reader, dict) else getattr(reader, 'is_compatible_with', None)

        if (explicit_compatible is not None and not flag(explicit_compatible)) or flag(explicit_incompatible):
            reason = 'READ_VERSION_INCOMPATIBLE'
            if isinstance(reader, dict):
                reason = reader.get('reason') or reader.get('incompatibility_reason') or reason
            result = {'compatible': {}, 'violations': {'*': [reason]}}
        elif callable(compatibility_fn):
            ok = bool(compatibility_fn(write_version))
            result = {
                'compatible': {'*': 'EXPLICIT'} if ok else {},
                'violations': {} if ok else {'*': ['READ_VERSION_INCOMPATIBLE']},
            }
        else:
            result = compare_fields(write_fields, fields_of(reader))
        ok = not result['violations']
        item = {
            'read_version': read_id,
            'version': read_id,
            'active': True,
            'status': 'COMPATIBLE' if ok else 'INCOMPATIBLE',
            'compatible': ok,
            **result,
        }
        reader_reports.append(item)
        if ok:
            compatible_readers[read_id] = result['compatible']
        else:
            violations[read_id] = result['violations']
            blocking.append(read_id)

    return {
        'write_version': write_id,
        'candidate': write_id,
        'compatible': not blocking,
        'readers': reader_reports,
        'active_read_versions': [item['read_version'] for item in reader_reports],
        'blocking_read_versions': blocking,
        'compatible_readers': compatible_readers,
        'violations': violations,
    }


def version_id(version, default=None):
    if version is None:
        return default
    if isinstance(version, str):
        return version
    if isinstance(version, (int, float)):
        return str(version)
    if isinstance(version, dict):
        value = _first(version, ('version', 'version_id', 'id', 'read_version', 'write_version', 'name'))
        return None if value is None else str(value)
    for attr in ('version', 'version_id', 'id', 'read_version', 'write_version'):
        value = getattr(version, attr, None)
        if value is not None:
            return str(value)
    return default


def can_release_table(write_version, read_versions=None):
    return compatibility_report(write_version, read_versions or [])['compatible']


def check_table_versions(write_version, read_versions=None):
    return compatibility_report(write_version, read_versions or [])


compare_versions = compatibility_report
check_compatibility = compatibility_report
is_compatible = can_release_table


def active_fingerprint(read_versions, generation=None):
    readers = list(read_versions.values()) if isinstance(read_versions, dict) else list(read_versions or [])
    active = []
    for reader in readers:
        if not reader_is_active(reader):
            continue
        rid = version_id(reader)
        revision = reader.get('revision', 0) if isinstance(reader, dict) else getattr(reader, 'revision', 0)
        active.append((rid, revision, normalize_fields(fields_of(reader))))
    active.sort(key=lambda item: item[0])
    payload = json.dumps(
        {'generation': generation, 'readers': active},
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def copy_json(value):
    return deepcopy(value)
