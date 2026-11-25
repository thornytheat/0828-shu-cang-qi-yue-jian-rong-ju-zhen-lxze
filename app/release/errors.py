from app.release.compat import ReleaseIssue


class StaleCheckError(ReleaseIssue):
    def __init__(self, *aliases):
        super().__init__('STALE_CHECK', *aliases)


class IncompatibleReadVersionError(ReleaseIssue):
    def __init__(self, *aliases):
        super().__init__('UNRESOLVED_ISSUES', *aliases)


class WriteVersionConflictError(ReleaseIssue):
    def __init__(self, *aliases):
        super().__init__('WRITE_VERSION_CONFLICT', *aliases)


class TableNotFoundError(ReleaseIssue):
    def __init__(self):
        super().__init__('TABLE_NOT_FOUND')


class CheckNotFoundError(ReleaseIssue):
    def __init__(self):
        super().__init__('CHECK_NOT_FOUND')
