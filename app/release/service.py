from __future__ import annotations

from pathlib import Path

from app.release.board import ReleaseBoard
from app.release.store import ReleaseStore


class ReleaseService:
    """Application service.

    It accepts either an existing review :class:`app.review.store.Store`, a
    filesystem path, a :class:`ReleaseStore`, or no argument (thread-safe
    in-memory board).
    """

    def __init__(self, store=None, db=None, path=None):
        source = store if store is not None else db if db is not None else path
        if isinstance(source, ReleaseBoard):
            self.store = None
            self.board = source
        elif source is None:
            self.store = None
            self.board = ReleaseBoard()
        elif isinstance(source, ReleaseStore):
            self.store = source
            self.board = ReleaseBoard()
        elif hasattr(source, 'path'):
            # Existing review Store exposes .path; str/Path are accepted directly.
            self.store = ReleaseStore(source)
            self.board = ReleaseBoard()
        elif hasattr(source, 'mutate') and hasattr(source, 'run'):
            self.store = source
            self.board = ReleaseBoard()
        elif isinstance(source, (dict, list)):
            self.store = None
            self.board = ReleaseBoard(source)
        else:
            self.store = ReleaseStore(source)
            self.board = ReleaseBoard()

    def _run(self, method, *args, **kwargs):
        if self.store is None:
            return getattr(self.board, method)(*args, **kwargs)
        return self.store.run(method, *args, **kwargs)

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)

        def delegate(*args, **kwargs):
            return self._run(name, *args, **kwargs)

        delegate.__name__ = name
        return delegate

    def create_table(self, *args, **kwargs):
        return self._run('create_table', *args, **kwargs)

    register_table = add_table = create_table

    def register_write_version(self, *args, **kwargs):
        return self._run('register_write_version', *args, **kwargs)

    register_write = add_write = add_write_version = add_candidate = register_candidate = register_write_version

    def register_read_version(self, *args, **kwargs):
        return self._run('register_read_version', *args, **kwargs)

    register_read = add_read = add_read_version = add_reader = register_reader = register_read_version

    def retire_read_version(self, *args, **kwargs):
        return self._run('retire_read_version', *args, **kwargs)

    def restore_read_version(self, *args, **kwargs):
        return self._run('restore_read_version', *args, **kwargs)

    retire_reader = deactivate_read_version = retire_read_version
    restore_reader = activate_read_version = reactivate_read_version = restore_read_version

    def check(self, *args, **kwargs):
        return self._run('check', *args, **kwargs)

    verify = check_table = verify_table = check_release = verify_release = check_compatibility = recheck = check

    def is_compatible(self, *args, **kwargs):
        return self._run('is_compatible', *args, **kwargs)

    can_release = is_compatible

    def sign(self, *args, **kwargs):
        return self._run('sign', *args, **kwargs)

    release = approve = sign_off = sign_table = release_table = approve_table = commit_table = commit_release = sign

    def submit_batch(self, *args, **kwargs):
        return self._run('submit_batch', *args, **kwargs)

    submit = submit_batch
    release_batch = commit_batch = sign_batch = submit_batch

    def table(self, *args, **kwargs):
        return self._run('table', *args, **kwargs)

    def list_tables(self, *args, **kwargs):
        return self._run('list_tables', *args, **kwargs)

    def get_batch(self, *args, **kwargs):
        return self._run('get_batch', *args, **kwargs)

    def snapshot(self, *args, **kwargs):
        if self.store is None:
            return self.board.snapshot()
        return self.store.read()


# Function-style API matching app.review.service conventions.
def create_service(store=None):
    return ReleaseService(store)


def create_table(store, *args, **kwargs):
    return ReleaseService(store).create_table(*args, **kwargs)


def register_write_version(store, *args, **kwargs):
    return ReleaseService(store).register_write_version(*args, **kwargs)


def register_read_version(store, *args, **kwargs):
    return ReleaseService(store).register_read_version(*args, **kwargs)


def retire_read_version(store, *args, **kwargs):
    return ReleaseService(store).retire_read_version(*args, **kwargs)


def restore_read_version(store, *args, **kwargs):
    return ReleaseService(store).restore_read_version(*args, **kwargs)


def check(store, *args, **kwargs):
    return ReleaseService(store).check(*args, **kwargs)


verify = check


def sign(store, *args, **kwargs):
    return ReleaseService(store).sign(*args, **kwargs)


release = sign


def submit_batch(store, *args, **kwargs):
    return ReleaseService(store).submit_batch(*args, **kwargs)


def get_batch(store, batch_id):
    return ReleaseService(store).get_batch(batch_id)


def list_tables(store):
    return ReleaseService(store).list_tables()


def snapshot(store):
    return ReleaseService(store).snapshot()


release_batch = submit_batch
commit_batch = submit_batch
sign_batch = submit_batch


def _delegate(method):
    def wrapper(store, *args, **kwargs):
        return getattr(ReleaseService(store), method)(*args, **kwargs)

    wrapper.__name__ = method
    return wrapper


for _name in (
    'create_table', 'register_table', 'add_table',
    'register_write_version', 'add_write_version', 'register_write', 'add_write',
    'add_candidate', 'register_candidate',
    'register_read_version', 'add_read_version', 'register_read', 'add_read',
    'add_reader', 'register_reader',
    'retire_read_version', 'restore_read_version', 'retire', 'restore',
    'update_read_version', 'set_read_version_status',
    'retire_reader', 'restore_reader',
    'activate_read_version', 'reactivate_read_version',
    'check_table', 'verify_table', 'check_candidate', 'verify_candidate',
    'check_release', 'verify_release', 'check_versions', 'verify_versions',
    'check_compatibility', 'verify_compatibility', 'recheck',
    'is_compatible', 'can_release',
    'sign_table', 'release_table', 'approve_table', 'issue_table', 'commit_table',
    'commit_release', 'sign_off',
):
    globals()[_name] = _delegate(_name)

verify = check
release = sign
approve = sign
review_table = sign_table
