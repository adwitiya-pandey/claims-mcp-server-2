"""Security: authentication, authorization, rate limiting, text sanitization.

SPEC references: S4 (auth), S5 (tool allowlists), S6 (rate limiting),
S7 (untrusted text sanitization).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Callable

# ---------- Key store (S4) ----------


class KeyEntry:
    """One API key entry: key_id, sha256 hash, allowed tools."""

    __slots__ = ("key_id", "sha256", "allowed_tools")

    def __init__(self, key_id: str, sha256: str, allowed_tools: list[str]) -> None:
        self.key_id = key_id
        self.sha256 = sha256
        self.allowed_tools = allowed_tools


class KeyStore:
    """Load and verify API keys from a keys.json file."""

    def __init__(self, entries: list[KeyEntry]) -> None:
        self._by_hash: dict[str, KeyEntry] = {e.sha256: e for e in entries}
        # Keep a dummy hash for constant-time comparison when key is unknown
        self._dummy_hash = hashlib.sha256(b"__dummy__").hexdigest()

    @classmethod
    def load(cls, path: Path) -> "KeyStore":
        """Load keys from a JSON file matching SPEC 11 format."""
        data = json.loads(path.read_text())
        entries = []
        for k in data["keys"]:
            entries.append(
                KeyEntry(
                    key_id=k["key_id"],
                    sha256=k["sha256"],
                    allowed_tools=k["allowed_tools"],
                )
            )
        return cls(entries)

    def verify(self, raw_key: str) -> KeyEntry | None:
        """Verify a raw API key. Returns the KeyEntry or None.

        Uses hmac.compare_digest for constant-time comparison (S4).
        """
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        # Always compare against something to avoid timing leaks
        found: KeyEntry | None = None
        for stored_hash, entry in self._by_hash.items():
            if hmac.compare_digest(key_hash, stored_hash):
                found = entry
                break
        else:
            # Compare against dummy to keep timing constant
            hmac.compare_digest(key_hash, self._dummy_hash)
        return found


def hash_key(raw_key: str) -> str:
    """Hash a raw API key with SHA-256."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


# ---------- Authorization (S5) ----------


def check_tool_allowed(entry: KeyEntry, tool_name: str) -> bool:
    """Check if a key is allowed to call a tool."""
    if "all" in entry.allowed_tools:
        return True
    return tool_name in entry.allowed_tools


# ---------- Rate limiting (S6) ----------


class RateLimiter:
    """Fixed-window per-key rate limiter with injectable clock.

    Default: 60 calls per minute (SPEC S6).
    """

    def __init__(
        self,
        max_calls: int = 60,
        window_seconds: int = 60,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._max_calls = max_calls
        self._window = window_seconds
        self._clock = clock or time.monotonic
        self._windows: dict[str, tuple[float, int]] = {}

    def check(self, key_id: str) -> bool:
        """Check if a call is within the rate limit.

        Returns True if allowed, False if rate limited.
        """
        now = self._clock()
        window_start, count = self._windows.get(key_id, (0.0, 0))

        if now - window_start >= self._window:
            # New window
            self._windows[key_id] = (now, 1)
            return True

        if count >= self._max_calls:
            return False

        self._windows[key_id] = (window_start, count + 1)
        return True


# ---------- Text sanitization (S7) ----------

# Control characters to remove, except \n (0x0A) and \t (0x09)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x0d\x0e-\x1f\x7f]")

# Maximum note text length after sanitization
_TEXT_CAP = 1000


def sanitize_untrusted_text(text: str) -> tuple[str, bool]:
    """Sanitize untrusted text per SPEC S7.

    1. Remove control characters except newline and tab.
    2. Remove Unicode category Cf characters (zero-width, bidi overrides).
    3. Cap at 1,000 characters.

    Returns (sanitized_text, was_truncated).
    """
    # Remove control characters (keep \n and \t)
    result = _CONTROL_RE.sub("", text)

    # Remove Unicode Cf category characters (zero-width, bidi, etc.)
    result = "".join(ch for ch in result if unicodedata.category(ch) != "Cf")

    # Cap length
    truncated = len(result) > _TEXT_CAP
    if truncated:
        result = result[:_TEXT_CAP]

    return result, truncated
