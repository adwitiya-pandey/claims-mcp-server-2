"""Audit log: append-only JSONL writer, fail-closed (SPEC S9, section 10).

One JSON object per call. Rules:
- outcome is one of: ok, denied, invalid, not_found, rate_limited, error
- For invalid calls, args is null and invalid_fields lists field names only
- Never log result payloads or note text
- caller is 'stdio-local' for stdio transport
- If the write fails, raise AuditWriteError so the server returns INTERNAL
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any


class AuditWriteError(Exception):
    """Raised when the audit line cannot be written. The server must
    return INTERNAL and no data (fail closed, SPEC S9)."""


class AuditLogger:
    """Append-only JSONL audit logger."""

    def __init__(self, path: Path | None = None) -> None:
        """Initialize the audit logger.

        Args:
            path: Path to the audit JSONL file. If None, writes only
                  to stderr (for testing / stdio mode).
        """
        self._path = path
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        *,
        request_id: str | None = None,
        caller: str = "stdio-local",
        transport: str = "stdio",
        tool: str,
        args: dict[str, Any] | None = None,
        outcome: str,
        rows: int | None = None,
        duration_ms: float | None = None,
        error_code: str | None = None,
        invalid_fields: list[str] | None = None,
    ) -> str:
        """Write one audit line. Returns the request_id.

        Raises:
            AuditWriteError: If the line cannot be written.
        """
        if request_id is None:
            request_id = uuid.uuid4().hex[:16]

        entry: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z",
            "request_id": request_id,
            "caller": caller,
            "transport": transport,
            "tool": tool,
            "outcome": outcome,
        }

        # For invalid calls, args is null and invalid_fields is set
        if outcome == "invalid":
            entry["args"] = None
            if invalid_fields:
                entry["invalid_fields"] = invalid_fields
        elif args is not None:
            entry["args"] = args

        if rows is not None:
            entry["rows"] = rows
        if duration_ms is not None:
            entry["duration_ms"] = round(duration_ms, 1)
        if error_code is not None:
            entry["error_code"] = error_code

        line = json.dumps(entry, separators=(",", ":"))

        # Write to stderr for structured logging (always)
        try:
            print(line, file=sys.stderr, flush=True)
        except Exception:
            pass  # stderr write failures are not fatal

        # Write to file if configured
        if self._path is not None:
            try:
                with open(self._path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception as exc:
                raise AuditWriteError(f"Failed to write audit log: {exc}") from exc

        return request_id
