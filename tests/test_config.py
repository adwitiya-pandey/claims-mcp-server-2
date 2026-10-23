"""Tests for configuration loading and validation (SPEC 11, S10)."""

import json
from pathlib import Path

import pytest

from claims_mcp.config import ConfigError, ServerConfig, load_config, validate_config


def test_default_config(tmp_path: Path):
    db_file = tmp_path / "claims.db"
    db_file.touch()

    env = {"CLAIMS_DB_PATH": str(db_file)}
    cfg = load_config(env=env)

    assert cfg.db_path == db_file
    assert cfg.audit_path == Path("audit/audit.jsonl")
    assert cfg.rate_limit_per_min == 60
    assert cfg.http_host == "127.0.0.1"
    assert cfg.http_port == 8765
    assert cfg.keys_file is None


def test_custom_config(tmp_path: Path):
    db_file = tmp_path / "custom.db"
    db_file.touch()
    keys_file = tmp_path / "keys.json"
    audit_file = tmp_path / "custom_audit.jsonl"

    env = {
        "CLAIMS_DB_PATH": str(db_file),
        "CLAIMS_KEYS_FILE": str(keys_file),
        "CLAIMS_AUDIT_PATH": str(audit_file),
        "CLAIMS_RATE_LIMIT_PER_MIN": "120",
        "CLAIMS_HTTP_HOST": "0.0.0.0",
        "CLAIMS_HTTP_PORT": "9000",
    }
    cfg = load_config(env=env)

    assert cfg.db_path == db_file
    assert cfg.keys_file == keys_file
    assert cfg.audit_path == audit_file
    assert cfg.rate_limit_per_min == 120
    assert cfg.http_host == "0.0.0.0"
    assert cfg.http_port == 9000


def test_missing_db_raises():
    cfg = ServerConfig(db_path=Path("non_existent_db.sqlite"))
    with pytest.raises(ConfigError, match="Database file not found"):
        validate_config(cfg, transport="stdio")


def test_missing_db_env_raises():
    with pytest.raises(ConfigError, match="CLAIMS_DB_PATH is required"):
        load_config(env={})


def test_http_mode_requires_keys_file(tmp_path: Path):
    db_file = tmp_path / "claims.db"
    db_file.touch()
    cfg = ServerConfig(db_path=db_file, keys_file=None)

    with pytest.raises(ConfigError, match="keys file is required in HTTP mode"):
        validate_config(cfg, transport="http")


def test_http_mode_missing_keys_file_on_disk(tmp_path: Path):
    db_file = tmp_path / "claims.db"
    db_file.touch()
    cfg = ServerConfig(db_path=db_file, keys_file=tmp_path / "missing_keys.json")

    with pytest.raises(ConfigError, match="Keys file not found"):
        validate_config(cfg, transport="http")


def test_http_mode_empty_keys_file(tmp_path: Path):
    db_file = tmp_path / "claims.db"
    db_file.touch()
    keys_file = tmp_path / "keys.json"
    keys_file.write_text(json.dumps({"keys": []}))

    cfg = ServerConfig(db_path=db_file, keys_file=keys_file)
    with pytest.raises(ConfigError, match="Keys file contains no keys"):
        validate_config(cfg, transport="http")


def test_http_mode_valid_keys_file(tmp_path: Path):
    db_file = tmp_path / "claims.db"
    db_file.touch()
    keys_file = tmp_path / "keys.json"
    keys_file.write_text(
        json.dumps(
            {
                "keys": [
                    {
                        "key_id": "test",
                        "sha256": "abc",
                        "allowed_tools": ["get_claim"],
                    }
                ]
            }
        )
    )

    cfg = ServerConfig(db_path=db_file, keys_file=keys_file)
    validate_config(cfg, transport="http")  # Should not raise


def test_stdio_mode_does_not_require_keys(tmp_path: Path):
    db_file = tmp_path / "claims.db"
    db_file.touch()
    cfg = ServerConfig(db_path=db_file, keys_file=None)
    validate_config(cfg, transport="stdio")  # Should not raise
