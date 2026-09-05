"""One agent per user session.

Autostart plus a manual launch is an easy way to end up with two agents, and two agents
double every heartbeat and every session they will produce in Phase 5. The lock is a
file held open for the life of the process: the OS releases it if the process dies, so
a crash never leaves a stale lock that blocks the next start.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .config import data_dir

LOCK_FILENAME = "agent.lock"


class AlreadyRunning(Exception):
    """Another agent holds the lock."""


class SingleInstance:
    """Context manager around an exclusively-locked file."""

    def __init__(self, path: Path | None = None):
        self.path = path or (data_dir() / LOCK_FILENAME)
        self._handle = None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+")  # noqa: SIM115 - held for the process lifetime
        try:
            self._lock(handle)
        except OSError as exc:
            handle.close()
            raise AlreadyRunning(f"Another agent is already running ({self.path}).") from exc

        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        self._handle = handle
        return self

    def release(self):
        if self._handle is None:
            return
        try:
            self._unlock(self._handle)
        finally:
            self._handle.close()
            self._handle = None

    # --- Platform detail ---------------------------------------------------

    @staticmethod
    def _lock(handle):
        if sys.platform == "win32":
            import msvcrt

            # msvcrt locks a byte range starting at the *current position*, so the seek
            # is load-bearing: opened in append mode the position starts at EOF, and two
            # instances would each lock a different byte and both believe they won.
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    @staticmethod
    def _unlock(handle):
        try:
            if sys.platform == "win32":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            # Releasing a lock we are about to close by exiting is not worth an error.
            pass

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc_info):
        self.release()
        return False
