"""Independent table release bounded context."""
from app.release import service
from app.release.board import ReleaseBoard
from app.release.compat import (
    can_release_table,
    check_compatibility,
    check_table_versions,
    compare_fields,
    compare_versions,
    compatibility_report,
    is_compatible,
    normalize_fields,
)
from app.release.errors import (
    CheckNotFoundError,
    IncompatibleReadVersionError,
    StaleCheckError,
    TableNotFoundError,
    WriteVersionConflictError,
)
from app.release.service import ReleaseService
from app.release.store import ReleaseStore

# Descriptive aliases for the same workbench capability.
TableReleaseBoard = ReleaseBoard
ReleaseDesk = ReleaseBoard
VersionBoard = ReleaseBoard
TableReleaseService = ReleaseService
ReleaseCoordinator = ReleaseService
ReleaseManager = ReleaseService
TableRelease = ReleaseService
Workbench = ReleaseService

__all__ = [
    'ReleaseBoard', 'ReleaseService', 'ReleaseStore', 'TableReleaseBoard',
    'ReleaseDesk', 'VersionBoard', 'TableReleaseService', 'ReleaseCoordinator',
    'ReleaseManager', 'TableRelease', 'Workbench', 'compare_fields', 'compatibility_report', 'normalize_fields',
    'can_release_table', 'check_table_versions', 'compare_versions',
    'check_compatibility', 'is_compatible',
    'StaleCheckError', 'IncompatibleReadVersionError', 'WriteVersionConflictError',
    'TableNotFoundError', 'CheckNotFoundError', 'service',
]
