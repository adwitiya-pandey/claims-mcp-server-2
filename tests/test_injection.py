"""Hostile input and security abuse test suite (SPEC 9, SPEC 12, TASKS T10).

Parametrizes 30+ hostile cases across all tools:
- SQL injection attempts in every ID parameter of every tool
- Unicode digit tricks and newline/null byte tricks
- Oversized values
- Negative, zero, huge, and non-integer limit/offset
- Extra unexpected parameters across all tools
- Adversarial notes returned sanitized, capped, and flagged untrusted
- Rate limit exhaustion

Each test asserts:
1. Safe error (or sanitized output)
2. No internal details (traceback, SQL, schemas, paths, input echoes) leaked
3. Exactly one audit line written per call
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from mcp import Client

from claims_mcp.audit import AuditLogger
from claims_mcp.config import ServerConfig
from claims_mcp.security import RateLimiter
from claims_mcp.server import create_server
from tests.fixtures import build_fixture_db

LEAK_PATTERNS = [
    "Traceback",
    "sqlite3",
    "OperationalError",
    "CREATE TABLE",
    "claims_mcp",
    "/home/",
    "SELECT ",
    "FROM claims",
    "FROM members",
]

HOSTILE_INPUT_CASES = [
    # 1-4: SQL injection in get_claim
    ("get_claim", {"claim_id": "CLM00000001' OR '1'='1"}, "INVALID_INPUT"),
    (
        "get_claim",
        {"claim_id": "CLM00000001; DROP TABLE claims;"},
        "INVALID_INPUT",
    ),
    (
        "get_claim",
        {"claim_id": "CLM00000001' UNION SELECT * FROM claims --"},
        "INVALID_INPUT",
    ),
    ("get_claim", {"claim_id": "admin'--"}, "INVALID_INPUT"),
    # 5-7: SQL injection in list_member_claims
    ("list_member_claims", {"member_id": "M000001' OR '1'='1"}, "INVALID_INPUT"),
    (
        "list_member_claims",
        {"member_id": "M000001; DELETE FROM claims;"},
        "INVALID_INPUT",
    ),
    (
        "list_member_claims",
        {"member_id": "M000001' UNION SELECT NULL --"},
        "INVALID_INPUT",
    ),
    # 8-10: SQL injection in get_coverage_rule
    (
        "get_coverage_rule",
        {"plan_id": "PLN001' OR '1'='1", "procedure_code": "PX0001"},
        "INVALID_INPUT",
    ),
    (
        "get_coverage_rule",
        {
            "plan_id": "PLN001",
            "procedure_code": "PX0001'; DROP TABLE coverage_rules; --",
        },
        "INVALID_INPUT",
    ),
    (
        "get_coverage_rule",
        {"plan_id": "'; DROP TABLE plans; --", "procedure_code": "PX0001"},
        "INVALID_INPUT",
    ),
    # 11-12: SQL injection in get_member_ytd_summary
    (
        "get_member_ytd_summary",
        {"member_id": "M000001' OR 1=1 --", "year": 2025},
        "INVALID_INPUT",
    ),
    (
        "get_member_ytd_summary",
        {"member_id": "M000001", "year": "2025; DROP TABLE claims"},
        "INVALID_INPUT",
    ),
    # 13-14: SQL injection in get_claim_notes
    (
        "get_claim_notes",
        {"claim_id": "CLM00000001' OR '1'='1"},
        "INVALID_INPUT",
    ),
    (
        "get_claim_notes",
        {"claim_id": "CLM00000001; SELECT * FROM sqlite_master"},
        "INVALID_INPUT",
    ),
    # 15-20: Unicode digits, newlines, and null bytes
    ("get_claim", {"claim_id": "CLM00000001\n"}, "INVALID_INPUT"),
    ("get_claim", {"claim_id": "CLM00000001\r\n"}, "INVALID_INPUT"),
    ("get_claim", {"claim_id": "CLM0000000١"}, "INVALID_INPUT"),  # Arabic-Indic
    ("list_member_claims", {"member_id": "M०००००१"}, "INVALID_INPUT"),  # Devanagari
    (
        "get_coverage_rule",
        {"plan_id": "PLN००१", "procedure_code": "PX0001"},
        "INVALID_INPUT",
    ),
    ("get_claim", {"claim_id": "CLM00000001\x00"}, "INVALID_INPUT"),
    # 21-23: Oversized values
    ("get_claim", {"claim_id": "CLM" + "0" * 10000}, "INVALID_INPUT"),
    ("list_member_claims", {"member_id": "M" + "0" * 10000}, "INVALID_INPUT"),
    (
        "get_coverage_rule",
        {"plan_id": "PLN" + "0" * 10000, "procedure_code": "PX0001"},
        "INVALID_INPUT",
    ),
    # 24-30: Limit & offset bounds and type violations
    ("list_member_claims", {"member_id": "M000001", "limit": -1}, "INVALID_INPUT"),
    ("list_member_claims", {"member_id": "M000001", "limit": 0}, "INVALID_INPUT"),
    ("list_member_claims", {"member_id": "M000001", "limit": 51}, "INVALID_INPUT"),
    ("list_member_claims", {"member_id": "M000001", "limit": 999999}, "INVALID_INPUT"),
    ("list_member_claims", {"member_id": "M000001", "limit": "20"}, "INVALID_INPUT"),
    ("list_member_claims", {"member_id": "M000001", "limit": True}, "INVALID_INPUT"),
    ("list_member_claims", {"member_id": "M000001", "offset": -1}, "INVALID_INPUT"),
    ("list_member_claims", {"member_id": "M000001", "offset": 10001}, "INVALID_INPUT"),
    ("get_claim_notes", {"claim_id": "CLM00000001", "limit": -1}, "INVALID_INPUT"),
    ("get_claim_notes", {"claim_id": "CLM00000001", "limit": 0}, "INVALID_INPUT"),
    ("get_claim_notes", {"claim_id": "CLM00000001", "limit": 21}, "INVALID_INPUT"),
    # 31-35: Extra unexpected parameters
    (
        "get_claim",
        {"claim_id": "CLM00000001", "role": "admin"},
        "INVALID_INPUT",
    ),
    (
        "list_member_claims",
        {"member_id": "M000001", "bypass": True},
        "INVALID_INPUT",
    ),
    (
        "get_coverage_rule",
        {"plan_id": "PLN001", "procedure_code": "PX0001", "override": "yes"},
        "INVALID_INPUT",
    ),
    (
        "get_member_ytd_summary",
        {"member_id": "M000001", "year": 2025, "hack": "test"},
        "INVALID_INPUT",
    ),
    (
        "get_claim_notes",
        {"claim_id": "CLM00000001", "limit": 10, "format": "raw"},
        "INVALID_INPUT",
    ),
]


@pytest.fixture
def injection_server(tmp_path: Path):
    db_path = tmp_path / "hostile.db"
    build_fixture_db(db_path)
    audit_path = tmp_path / "audit_hostile.jsonl"
    logger = AuditLogger(audit_path)
    cfg = ServerConfig(db_path=db_path, audit_path=audit_path)
    server = create_server(cfg, audit_logger=logger)
    return server, audit_path


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name,args,expected_code", HOSTILE_INPUT_CASES)
async def test_hostile_inputs_safe_rejection(
    injection_server, tool_name: str, args: dict[str, Any], expected_code: str
):
    server, audit_path = injection_server
    start_lines = 0
    if audit_path.exists():
        start_lines = len(
            [line for line in audit_path.read_text().splitlines() if line.strip()]
        )

    async with Client(server) as client:
        result = await client.call_tool(tool_name, args)

    assert result.is_error is True
    assert len(result.content) == 1
    text = result.content[0].text
    assert text.startswith(expected_code)

    # Assert no internal leak in error response
    for pattern in LEAK_PATTERNS:
        assert pattern not in text

    # Assert exactly one audit line written
    current_lines = [
        line for line in audit_path.read_text().splitlines() if line.strip()
    ]
    assert len(current_lines) == start_lines + 1

    last_entry = json.loads(current_lines[-1])
    assert last_entry["outcome"] == "invalid"
    assert last_entry["tool"] == tool_name
    assert last_entry["args"] is None
    assert "invalid_fields" in last_entry


@pytest.mark.asyncio
async def test_adversarial_note_sanitized_and_untrusted_flag(injection_server):
    """Note 4 on CLM00000002 contains prompt injection text."""
    server, audit_path = injection_server
    async with Client(server) as client:
        result = await client.call_tool("get_claim_notes", {"claim_id": "CLM00000002"})

    assert result.is_error is False
    assert len(result.content) == 1
    data = json.loads(result.content[0].text)

    # S7: untrusted flag MUST be True
    assert data["untrusted"] is True
    notes = data["notes"]
    assert len(notes) >= 1

    # Find the adversarial note
    adv_note = next((n for n in notes if n["note_id"] == 4), None)
    assert adv_note is not None
    assert "IGNORE PREVIOUS INSTRUCTIONS" in adv_note["text"]
    assert len(adv_note["text"]) <= 1000

    # Assert audit line
    audit_lines = [line for line in audit_path.read_text().splitlines() if line.strip()]
    last_entry = json.loads(audit_lines[-1])
    assert last_entry["outcome"] == "ok"
    assert last_entry["tool"] == "get_claim_notes"
    # Never log note text in audit log
    assert "IGNORE PREVIOUS INSTRUCTIONS" not in audit_lines[-1]


@pytest.mark.asyncio
async def test_rate_limit_hostile_abuse(tmp_path: Path):
    """Exceed rate limit and assert RATE_LIMITED error and audit line."""
    db_path = tmp_path / "rate.db"
    build_fixture_db(db_path)
    audit_path = tmp_path / "rate_audit.jsonl"
    logger = AuditLogger(audit_path)

    # 3 calls max
    limiter = RateLimiter(max_calls=3, window_seconds=60)
    cfg = ServerConfig(db_path=db_path, audit_path=audit_path)
    server = create_server(cfg, rate_limiter=limiter, audit_logger=logger)

    async with Client(server) as client:
        # First 3 should succeed
        for _ in range(3):
            r = await client.call_tool("get_claim", {"claim_id": "CLM00000001"})
            assert r.is_error is False

        # 4th call must be RATE_LIMITED
        r_blocked = await client.call_tool("get_claim", {"claim_id": "CLM00000001"})
        assert r_blocked.is_error is True
        assert r_blocked.content[0].text == "RATE_LIMITED: try again later"

    # Verify audit lines
    audit_lines = [line for line in audit_path.read_text().splitlines() if line.strip()]
    assert len(audit_lines) == 4
    blocked_entry = json.loads(audit_lines[-1])
    assert blocked_entry["outcome"] == "rate_limited"
    assert blocked_entry["error_code"] == "RATE_LIMITED"
