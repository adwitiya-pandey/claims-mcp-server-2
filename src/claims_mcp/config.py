"""Configuration loading and validation.

SPEC references: S10 (config validation), SPEC 11 (env vars).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv


class ConfigError(Exception):
    """Raised when configuration is missing or invalid."""


@dataclass(frozen=True)
class ServerConfig:
    """Server configuration values."""

    db_path: Path
    keys_file: Path | None = None
    audit_path: Path = Path("audit/audit.jsonl")
    rate_limit_per_min: int = 60
    http_host: str = "127.0.0.1"
    http_port: int = 8765


def load_config(env: Mapping[str, str] | None = None) -> ServerConfig:
    """Load configuration from environment variables or a mapping.

    If env is None, loads from .env file and os.environ.
    """
    if env is None:
        load_dotenv()
        env = os.environ

    db_path_str = env.get("CLAIMS_DB_PATH")
    if not db_path_str:
        raise ConfigError("CLAIMS_DB_PATH is required")
    db_path = Path(db_path_str)

    keys_file_str = env.get("CLAIMS_KEYS_FILE")
    keys_file = Path(keys_file_str) if keys_file_str else None

    audit_path_str = env.get("CLAIMS_AUDIT_PATH", "audit/audit.jsonl")
    audit_path = Path(audit_path_str)

    rate_limit_str = env.get("CLAIMS_RATE_LIMIT_PER_MIN", "60")
    try:
        rate_limit = int(rate_limit_str)
        if rate_limit <= 0:
            raise ValueError
    except ValueError as exc:
        raise ConfigError(
            f"CLAIMS_RATE_LIMIT_PER_MIN must be a positive integer: {rate_limit_str}"
        ) from exc

    http_host = env.get("CLAIMS_HTTP_HOST", "127.0.0.1")

    http_port_str = env.get("CLAIMS_HTTP_PORT", "8765")
    try:
        http_port = int(http_port_str)
        if not (1 <= http_port <= 65535):
            raise ValueError
    except ValueError as exc:
        raise ConfigError(
            f"CLAIMS_HTTP_PORT must be a valid port number (1-65535): {http_port_str}"
        ) from exc

    return ServerConfig(
        db_path=db_path,
        keys_file=keys_file,
        audit_path=audit_path,
        rate_limit_per_min=rate_limit,
        http_host=http_host,
        http_port=http_port,
    )


def validate_config(config: ServerConfig, transport: str = "stdio") -> None:
    """Validate configuration at startup (SPEC S10).

    Refuses to start on:
    - missing DB file
    - (HTTP mode) missing keys file or empty keys list
    """
    resolved_db = config.db_path.resolve()
    if not resolved_db.is_file():
        raise ConfigError(f"Database file not found: {resolved_db}")

    if transport == "http":
        if config.keys_file is None:
            raise ConfigError("CLAIMS_KEYS_FILE keys file is required in HTTP mode")
        resolved_keys = config.keys_file.resolve()
        if not resolved_keys.is_file():
            raise ConfigError(f"Keys file not found: {resolved_keys}")

        try:
            data = json.loads(resolved_keys.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ConfigError(f"Invalid keys JSON file: {exc}") from exc

        keys = data.get("keys", [])
        if not isinstance(keys, list) or len(keys) == 0:
            raise ConfigError("Keys file contains no keys")
