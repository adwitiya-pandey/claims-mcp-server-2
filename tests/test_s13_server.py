"""Tests for SPEC S13: no call rejected by the SDK before the pipeline runs.

Every call, including ones with missing, extra, or wrongly typed arguments,
must reach the pipeline, receive a safe SPEC 8 error, write exactly one
audit line, and NEVER echo the raw input in error text or audit logs.
"""

import json
from pathlib import Path

import pytest
from mcp import Client

from claims_mcp.audit import AuditLogger
from claims_mcp.config import ServerConfig
from claims_mcp.server import create_server
from tests.fixtures import build_fixture_db


@pytest.fixture
def test_setup(tmp_path: Path):
    db_path = tmp_path / "test.db"
    build_fixture_db(db_path)
    audit_path = tmp_path / "audit.jsonl"
    logger = AuditLogger(audit_path)
    cfg = ServerConfig(db_path=db_path, audit_path=audit_path)
    srv = create_server(cfg, audit_logger=logger)
    return srv, audit_path


@pytest.mark.asyncio
async def test_s13_missing_argument(test_setup):
    srv, audit_path = test_setup
    async with Client(srv) as client:
        result = await client.call_tool("get_claim", {})

    assert result.is_error is True
    assert len(result.content) == 1
    text = result.content[0].text
    assert text == "INVALID_INPUT: claim_id is invalid"

    lines = [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) == 1
    log = lines[0]
    assert log["outcome"] == "invalid"
    assert log["tool"] == "get_claim"
    assert log["args"] is None
    assert log["invalid_fields"] == ["claim_id"]
    assert log["error_code"] == "INVALID_INPUT"


@pytest.mark.asyncio
async def test_s13_extra_argument(test_setup):
    srv, audit_path = test_setup
    secret_payload = "SECRET_SQL_INJECTION_OR_PROMPT"
    async with Client(srv) as client:
        result = await client.call_tool(
            "get_claim",
            {"claim_id": "CLM00000001", "unexpected_extra": secret_payload},
        )

    assert result.is_error is True
    assert len(result.content) == 1
    text = result.content[0].text
    assert text == "INVALID_INPUT: unexpected_extra is invalid"
    # Never echo raw input
    assert secret_payload not in text

    raw_audit = audit_path.read_text(encoding="utf-8")
    assert secret_payload not in raw_audit

    lines = [json.loads(line) for line in raw_audit.splitlines() if line.strip()]
    assert len(lines) == 1
    log = lines[0]
    assert log["outcome"] == "invalid"
    assert log["tool"] == "get_claim"
    assert log["args"] is None
    assert log["invalid_fields"] == ["unexpected_extra"]


@pytest.mark.asyncio
async def test_s13_wrongly_typed_argument(test_setup):
    srv, audit_path = test_setup
    raw_int = 12345678
    async with Client(srv) as client:
        result = await client.call_tool("get_claim", {"claim_id": raw_int})

    assert result.is_error is True
    assert len(result.content) == 1
    text = result.content[0].text
    assert text == "INVALID_INPUT: claim_id is invalid"
    assert str(raw_int) not in text

    raw_audit = audit_path.read_text(encoding="utf-8")
    assert str(raw_int) not in raw_audit

    lines = [json.loads(line) for line in raw_audit.splitlines() if line.strip()]
    assert len(lines) == 1
    log = lines[0]
    assert log["outcome"] == "invalid"
    assert log["tool"] == "get_claim"
    assert log["args"] is None
    assert log["invalid_fields"] == ["claim_id"]
