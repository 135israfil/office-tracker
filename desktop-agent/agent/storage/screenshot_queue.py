"""The offline buffer for captured screenshots (§19, §34 Local Storage).

A separate queue from `storage.queue.SessionQueue`, deliberately: a screenshot
is one large binary blob per row, not a small structured record, and a
confirmed upload is deleted immediately rather than kept for a grace period —
unlike a session, there is nothing left to debug locally once the image is
safely on the server and viewable there.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path

from ..config import data_dir

log = logging.getLogger(__name__)

QUEUE_FILENAME = "screenshots.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS screenshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at TEXT NOT NULL,
    image BLOB NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0
);
"""

# A machine offline for a while must not fill the disk with images. Much
# lower than SessionQueue's row cap on purpose: these rows are large.
MAX_PENDING_ROWS = 500


class ScreenshotQueue:
    """Durable FIFO of captured screenshots awaiting upload."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else (data_dir() / QUEUE_FILENAME)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(str(self.path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        with self._connection:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=FULL")
            self._connection.executescript(SCHEMA)

    def close(self):
        with self._lock:
            self._connection.close()

    # --- Writing -------------------------------------------------------------

    def enqueue(self, captured_at: str, image: bytes) -> int | None:
        """Store one captured screenshot. Returns its row id, or None if the
        local buffer is full (dropped and logged, same as SessionQueue)."""
        with self._lock, self._connection:
            if self._pending_count() >= MAX_PENDING_ROWS:
                log.error(
                    "Screenshot queue is full (%s pending); dropping capture",
                    MAX_PENDING_ROWS,
                )
                return None
            cursor = self._connection.execute(
                "INSERT INTO screenshots (captured_at, image) VALUES (?, ?)",
                (captured_at, image),
            )
            return cursor.lastrowid

    # --- Reading ---------------------------------------------------------------

    def pending(self, limit: int = 5) -> list[dict]:
        """Oldest-first batch of screenshots still awaiting a 2xx."""
        with self._lock:
            rows = self._connection.execute(
                "SELECT id, captured_at, image FROM screenshots ORDER BY id LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {"id": row["id"], "captured_at": row["captured_at"], "image": bytes(row["image"])}
            for row in rows
        ]

    def pending_count(self) -> int:
        with self._lock:
            return self._pending_count()

    def _pending_count(self) -> int:
        return self._connection.execute("SELECT COUNT(*) FROM screenshots").fetchone()[0]

    # --- Bookkeeping -------------------------------------------------------

    def mark_uploaded(self, row_id: int) -> None:
        """A confirmed upload is deleted immediately — unlike a session,
        there is no local grace-period value in keeping a copy of an image
        the server already has and can now be viewed through."""
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM screenshots WHERE id = ?", (row_id,))

    def record_attempt(self, row_id: int) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE screenshots SET attempts = attempts + 1 WHERE id = ?", (row_id,)
            )

    def discard(self, row_id: int) -> None:
        """Drop a row the server has permanently rejected as invalid.

        Without this, one screenshot the server will never accept (a bad image, a bad
        timestamp) would sit at the head of the queue forever, retried every cycle and
        blocking every capture behind it — the same failure `SessionQueue.discard`
        exists to prevent for sessions.
        """
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM screenshots WHERE id = ?", (row_id,))
