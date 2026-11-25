"""Version compatibility helpers exposed under a concise module name."""
from app.release.compat import (
    can_release_table,
    check_table_versions,
    compare_fields,
    compatibility_report,
    normalize_fields,
)
from app.release.service import (
    ReleaseService,
    check,
    register_read_version,
    register_write_version,
    sign,
    submit_batch,
)

__all__ = [
    'compare_fields', 'compatibility_report', 'normalize_fields', 'can_release_table',
    'check_table_versions', 'ReleaseService', 'check', 'sign', 'submit_batch',
    'register_read_version', 'register_write_version',
]
