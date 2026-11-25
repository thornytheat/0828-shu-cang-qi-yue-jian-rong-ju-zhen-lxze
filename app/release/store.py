from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.release.board import ReleaseBoard


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')

SCHEMA = """
CREATE TABLE IF NOT EXISTS release_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    revision INTEGER NOT NULL DEFAULT 0,
    payload TEXT NOT NULL,
    updated TEXT NOT NULL
);
"""


class ReleaseStore:
    """SQLite-backed aggregate store for the table release workbench.

    The whole workbench state is stored as one JSON aggregate and mutated under
    ``BEGIN IMMEDIATE``.  Release decisions are short and this makes the
    compare-and-set/fencing logic impossible to split across racing writers.
    """

    def __init__(self, source=None):
        if source is None:
            self.path = None
        elif hasattr(source, 'path'):
            self.path = Path(source.path)
        else:
            self.path = Path(source)

    def _connect(self):
        if self.path is None:
            raise RuntimeError('ReleaseStore requires a path')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute(SCHEMA)
        return db

    def load_board(self, db=None):
        close = db is None
        if db is None:
            db = self._connect()
        try:
            row = db.execute('SELECT payload FROM release_state WHERE id=1').fetchone()
            board = ReleaseBoard()
            if row:
                payload = json.loads(row['payload'])
                board.tables = payload.get('tables', {})
                board.checks = payload.get('checks', {})
                board.releases = payload.get('releases', {})
                board.batches = payload.get('batches', {})
            return board
        finally:
            if close:
                db.close()

    def read(self):
        with closing(self._connect()) as db:
            return self.load_board(db).snapshot()

    def mutate(self, callback):
        with closing(self._connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            board = self.load_board(db)
            try:
                result = callback(board)
                payload = json.dumps(
                    {
                        'tables': board.tables,
                        'checks': board.checks,
                        'releases': board.releases,
                        'batches': board.batches,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
                db.execute(
                    '''INSERT INTO release_state(id,revision,payload,updated)
                       VALUES (1, 1, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET
                         revision=revision+1, payload=excluded.payload, updated=excluded.updated''',
                    (payload, _now()),
                )
                db.commit()
                return result
            except Exception:
                db.rollback()
                raise

    # Convenience wrappers used by thin service/function APIs.
    def run(self, method, *args, **kwargs):
        def action(board):
            return getattr(board, method)(*args, **kwargs)

        return self.mutate(action)

    def new_id(self, prefix):
        return f'{prefix}_{uuid4().hex[:16]}'
