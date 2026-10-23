"""Read-only SQLite database access.

Opens connections with three layers of defense (SPEC S1, decisions D2/D10):
1. URI mode=ro: the connection is read-only at the VFS level.
2. PRAGMA query_only=ON: an additional write barrier inside SQLite.
3. An authorizer callback that allows only SELECT, READ and FUNCTION
   operations and denies everything else (including PRAGMA and ATTACH).

Each call opens and closes its own connection (decision D10) because
the SDK may run plain `def` handlers in worker threads and SQLite
connections are not thread-safe by default.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

# Authorizer action codes
SQLITE_SELECT = 21
SQLITE_READ = 20
SQLITE_FUNCTION = 31

_ALLOWED_ACTIONS = frozenset({SQLITE_SELECT, SQLITE_READ, SQLITE_FUNCTION})


def _authorizer(
    action: int,
    _arg1: str | None,
    _arg2: str | None,
    _db_name: str | None,
    _trigger: str | None,
) -> int:
    """Allow only read operations; deny everything else."""
    if action in _ALLOWED_ACTIONS:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


class DatabaseError(Exception):
    """Raised when the database cannot be opened or is missing."""


def open_readonly(path: Path) -> sqlite3.Connection:
    """Open a read-only SQLite connection with defense-in-depth.

    Args:
        path: Path to the SQLite database file.

    Returns:
        A read-only connection with an authorizer installed.

    Raises:
        DatabaseError: If the file does not exist or cannot be opened.
    """
    resolved = path.resolve()
    if not resolved.is_file():
        raise DatabaseError(f"Database file not found: {resolved}")

    uri = resolved.as_uri() + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.OperationalError as exc:
        raise DatabaseError(f"Cannot open database: {exc}") from exc

    conn.row_factory = sqlite3.Row

    # Set query_only BEFORE installing the authorizer (the authorizer
    # blocks PRAGMA).
    conn.execute("PRAGMA query_only = ON")

    conn.set_authorizer(_authorizer)

    return conn
