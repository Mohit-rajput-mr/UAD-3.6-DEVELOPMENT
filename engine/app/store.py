"""Shared, durable state for a report under review.

Edits are the record: whoever opens the report sees the same values, on any
device, and a change one reviewer makes reaches everyone who has it open.  The
store keeps each field separately so two people working in different parts of
the report never overwrite one another — last writer wins per field, not per
report.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS edits (
    report_id  TEXT NOT NULL,
    field_id   TEXT NOT NULL,
    value      TEXT NOT NULL,
    editor     TEXT NOT NULL DEFAULT '',
    revision   INTEGER NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (report_id, field_id)
);
CREATE TABLE IF NOT EXISTS revisions (
    report_id TEXT PRIMARY KEY,
    revision  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS edits_by_revision ON edits (report_id, revision);
"""


@dataclass
class Change:
    field_id: str
    value: str
    editor: str
    revision: int


class Store:
    """Field-level edits, durable in SQLite and broadcast to open viewers."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._subscribers: list[Queue] = []
        self._presence: dict[str, tuple[str, float]] = {}

        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")  # concurrent readers during a write
        return conn

    # --------------------------------------------------------------- reading
    def values(self, report_id: str) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT field_id, value FROM edits WHERE report_id = ?", (report_id,)
            ).fetchall()
        return {field_id: value for field_id, value in rows}

    def revision(self, report_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT revision FROM revisions WHERE report_id = ?", (report_id,)
            ).fetchone()
        return row[0] if row else 0

    def since(self, report_id: str, revision: int) -> list[Change]:
        """Everything changed after a revision, for a viewer catching up."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT field_id, value, editor, revision FROM edits "
                "WHERE report_id = ? AND revision > ? ORDER BY revision",
                (report_id, revision),
            ).fetchall()
        return [Change(*row) for row in rows]

    # --------------------------------------------------------------- writing
    def apply(self, report_id: str, edits: dict[str, Any], editor: str = "") -> int:
        """Record a set of field edits and tell every open viewer.

        Only fields whose value actually changed are written, so a viewer
        saving an untouched form does not bump the revision or wake anyone.
        """
        with self._lock:
            current = self.values(report_id)
            changed = {
                field_id: str(value)
                for field_id, value in edits.items()
                if str(value) != current.get(field_id)
            }
            if not changed:
                return self.revision(report_id)

            revision = self.revision(report_id) + 1
            now = time.time()
            with self._connect() as conn:
                conn.executemany(
                    "INSERT INTO edits (report_id, field_id, value, editor, revision,"
                    " updated_at) VALUES (?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT(report_id, field_id) DO UPDATE SET"
                    " value=excluded.value, editor=excluded.editor,"
                    " revision=excluded.revision, updated_at=excluded.updated_at",
                    [(report_id, f, v, editor, revision, now) for f, v in changed.items()],
                )
                conn.execute(
                    "INSERT INTO revisions (report_id, revision) VALUES (?, ?)"
                    " ON CONFLICT(report_id) DO UPDATE SET revision=excluded.revision",
                    (report_id, revision),
                )

        self._broadcast(
            {
                "type": "changes",
                "revision": revision,
                "editor": editor,
                "changes": changed,
            }
        )
        return revision

    def reset(self, report_id: str) -> None:
        """Discard every edit and return the report to what the engine produced."""
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM edits WHERE report_id = ?", (report_id,))
            conn.execute("DELETE FROM revisions WHERE report_id = ?", (report_id,))
        self._broadcast({"type": "reset"})

    # -------------------------------------------------------------- presence
    def seen(self, editor: str, name: str) -> None:
        self._presence[editor] = (name, time.time())

    def editors(self, window: float = 45.0) -> list[str]:
        """Who has the report open right now."""
        cutoff = time.time() - window
        self._presence = {
            key: value for key, value in self._presence.items() if value[1] > cutoff
        }
        return sorted({name for name, _ in self._presence.values()})

    # ------------------------------------------------------------- streaming
    def subscribe(self) -> Queue:
        queue: Queue = Queue(maxsize=64)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: Queue) -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    def _broadcast(self, message: dict) -> None:
        payload = json.dumps(message)
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(payload)
            except Exception:
                # A viewer that cannot keep up is dropped; it re-syncs on reconnect.
                self.unsubscribe(queue)

    def stream(self, queue: Queue, keepalive: float = 20.0) -> Iterator[str]:
        """Server-sent events for one viewer."""
        yield ": connected\n\n"
        while True:
            try:
                payload = queue.get(timeout=keepalive)
                yield f"data: {payload}\n\n"
            except Empty:
                yield ": keepalive\n\n"
