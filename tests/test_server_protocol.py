"""Protocol tests for claims-mcp-server (SPEC 8, SPEC 12, TASKS T9).

Asserts through a real MCP Client:
1. Exactly five tools are listed with read-only annotations.
2. Each tool's happy path returns valid JSON.
3. NOT_FOUND error behavior.
4. INVALID_INPUT error behavior.
5. FORBIDDEN_TOOL error behavior.
6. SDK-rejected calls (missing, extra, wrongly typed arguments) give safe
   errors and one audit line.
7. HTTP 401 on missing or invalid Bearer key.
8. Exact SPEC 8 error format wire contract.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from mcp import Client
from starlette.testclient import TestClient

from claims_mcp.audit import AuditLogger
from claims_mcp.config import ServerConfig
from claims_mcp.security import KeyEntry, KeyStore, hash_key
from claims_mcp.server import bound_caller, create_server
from tests.fixtures import build_fixture_db

SPEC_ERROR_PATTERN = re.compile(
    r"^(RATE_LIMITED|FORBIDDEN_TOOL|INVALID_INPUT|NOT_FOUND|INTERNAL)(: .*)?$"
)


@pytest.fixture
def protocol_env(tmp_path: Path):
    db_path = tmp_path / "protocol_claims.db"
    build_fixture_db(db_path)
    audit_path = tmp_path / "audit.jsonl"
    logger = AuditLogger(audit_path)

    key_store = KeyStore(
        [
            KeyEntry(
                key_id="analyst-full",
                sha256=hash_key("full-secret-key"),
                allowed_tools=["all"],
            ),
            KeyEntry(
                key_id="analyst-restricted",
                sha256=hash_key("restricted-secret-key"),
                allowed_tools=["get_claim"],
            ),
        ]
    )

    cfg = ServerConfig(db_path=db_path, audit_path=audit_path)
    server = create_server(cfg, key_store=key_store, audit_logger=logger)
    return server, audit_path, key_store


@pytest.mark.asyncio
async def test_tools_listing(protocol_env):
    server, _, _ = protocol_env
    async with Client(server) as client:
        tool_list = await client.list_tools()

    tool_names = {t.name for t in tool_list.tools}
    assert tool_names == {
        "get_claim",
        "list_member_claims",
        "get_coverage_rule",
        "get_member_ytd_summary",
        "get_claim_notes",
    }
    assert len(tool_list.tools) == 5

    # Check annotations (read_only=True, destructive=False)
    for t in tool_list.tools:
        assert t.annotations is not None
        assert t.annotations.read_only_hint is True
        assert t.annotations.destructive_hint is False


@pytest.mark.asyncio
async def test_happy_path_get_claim(protocol_env):
    server, _, _ = protocol_env
    async with Client(server) as client:
        result = await client.call_tool("get_claim", {"claim_id": "CLM00000001"})

    assert result.is_error is False
    assert len(result.content) == 1
    data = json.loads(result.content[0].text)
    assert data["claim_id"] == "CLM00000001"
    assert data["member_id"] == "M000001"
    assert data["plan_id"] == "PLN001"
    assert data["provider_id"] == "PRV0001"
    assert data["provider_network_status"] == "IN_NETWORK"
    assert data["procedure_code"] == "PX0001"
    assert data["billed_amount"] == 1500.0
    assert data["status"] == "PAID"


@pytest.mark.asyncio
async def test_happy_path_list_member_claims(protocol_env):
    server, _, _ = protocol_env
    async with Client(server) as client:
        result = await client.call_tool("list_member_claims", {"member_id": "M000001"})

    assert result.is_error is False
    data = json.loads(result.content[0].text)
    assert data["total"] == 4  # CLM00000001, 2, 3, 8
    assert len(data["items"]) == 4
    item = data["items"][0]
    assert "claim_id" in item
    assert "service_date" in item
    assert "procedure_code" in item
    assert "billed_amount" in item
    assert "status" in item


@pytest.mark.asyncio
async def test_happy_path_get_coverage_rule(protocol_env):
    server, _, _ = protocol_env
    async with Client(server) as client:
        result = await client.call_tool(
            "get_coverage_rule",
            {"plan_id": "PLN001", "procedure_code": "PX0001"},
        )

    assert result.is_error is False
    data = json.loads(result.content[0].text)
    assert data["plan_id"] == "PLN001"
    assert data["procedure_code"] == "PX0001"
    assert data["covered"] is True
    assert data["requires_preauth"] is False
    assert data["max_allowed"] == 5000.0


@pytest.mark.asyncio
async def test_happy_path_get_member_ytd_summary(protocol_env):
    server, _, _ = protocol_env
    async with Client(server) as client:
        result = await client.call_tool(
            "get_member_ytd_summary",
            {"member_id": "M000001", "year": 2025},
        )

    assert result.is_error is False
    data = json.loads(result.content[0].text)
    assert data["member_id"] == "M000001"
    assert data["year"] == 2025
    assert data["plan_id"] == "PLN001"
    assert data["annual_limit"] == 100000.0
    assert data["deductible"] == 1000.0
    assert isinstance(data["by_status"], list)
    assert data["remaining_annual_limit"] == 99000.0


@pytest.mark.asyncio
async def test_happy_path_get_claim_notes(protocol_env):
    server, _, _ = protocol_env
    async with Client(server) as client:
        result = await client.call_tool("get_claim_notes", {"claim_id": "CLM00000001"})

    assert result.is_error is False
    data = json.loads(result.content[0].text)
    assert data["claim_id"] == "CLM00000001"
    assert data["untrusted"] is True
    assert len(data["notes"]) == 2
    note = data["notes"][0]
    assert "note_id" in note
    assert "author_type" in note
    assert "text" in note
    assert "truncated" in note


@pytest.mark.asyncio
async def test_not_found_errors(protocol_env):
    server, _, _ = protocol_env
    async with Client(server) as client:
        # Unknown claim
        r1 = await client.call_tool("get_claim", {"claim_id": "CLM99999999"})
        assert r1.is_error is True
        assert r1.content[0].text == "NOT_FOUND"
        assert SPEC_ERROR_PATTERN.match(r1.content[0].text)

        # Unknown member
        r2 = await client.call_tool("list_member_claims", {"member_id": "M999999"})
        assert r2.is_error is True
        assert r2.content[0].text == "NOT_FOUND"

        # Unknown coverage rule
        r3 = await client.call_tool(
            "get_coverage_rule",
            {"plan_id": "PLN001", "procedure_code": "PX9999"},
        )
        assert r3.is_error is True
        assert r3.content[0].text == "NOT_FOUND"

        # Unknown member for YTD
        r4 = await client.call_tool(
            "get_member_ytd_summary",
            {"member_id": "M999999", "year": 2025},
        )
        assert r4.is_error is True
        assert r4.content[0].text == "NOT_FOUND"

        # Unknown claim for notes
        r5 = await client.call_tool("get_claim_notes", {"claim_id": "CLM99999999"})
        assert r5.is_error is True
        assert r5.content[0].text == "NOT_FOUND"


@pytest.mark.asyncio
async def test_invalid_input_error(protocol_env):
    server, _, _ = protocol_env
    async with Client(server) as client:
        result = await client.call_tool("get_claim", {"claim_id": "INVALID"})

    assert result.is_error is True
    assert result.content[0].text == "INVALID_INPUT: claim_id is invalid"
    assert SPEC_ERROR_PATTERN.match(result.content[0].text)


@pytest.mark.asyncio
async def test_forbidden_tool(protocol_env):
    server, audit_path, key_store = protocol_env
    restricted_entry = key_store.verify("restricted-secret-key")
    assert restricted_entry is not None

    with bound_caller(
        caller="analyst-restricted",
        key_entry=restricted_entry,
        transport="http",
    ):
        async with Client(server) as client:
            result = await client.call_tool(
                "list_member_claims", {"member_id": "M000001"}
            )

    assert result.is_error is True
    assert result.content[0].text == "FORBIDDEN_TOOL"
    assert SPEC_ERROR_PATTERN.match(result.content[0].text)

    # Check audit log
    lines = [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    last = lines[-1]
    assert last["outcome"] == "denied"
    assert last["error_code"] == "FORBIDDEN_TOOL"
    assert last["caller"] == "analyst-restricted"


@pytest.mark.asyncio
async def test_sdk_rejected_calls_safety(protocol_env):
    server, audit_path, _ = protocol_env
    async with Client(server) as client:
        # Missing argument
        r_missing = await client.call_tool("get_claim", {})
        assert r_missing.is_error is True
        assert r_missing.content[0].text == "INVALID_INPUT: claim_id is invalid"

        # Extra unexpected argument
        secret = "ATTACKER_INJECTED_STRING_XYZ"
        r_extra = await client.call_tool(
            "get_claim", {"claim_id": "CLM00000001", "extra_bad": secret}
        )
        assert r_extra.is_error is True
        assert r_extra.content[0].text == "INVALID_INPUT: extra_bad is invalid"
        assert secret not in r_extra.content[0].text

        # Wrong type
        r_type = await client.call_tool("get_claim", {"claim_id": 99999999})
        assert r_type.is_error is True
        assert r_type.content[0].text == "INVALID_INPUT: claim_id is invalid"
        assert "99999999" not in r_type.content[0].text

    # Verify audit lines for the 3 invalid calls
    lines = [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    invalid_logs = [entry for entry in lines if entry["outcome"] == "invalid"]
    assert len(invalid_logs) == 3
    for log in invalid_logs:
        assert log["args"] is None
        assert "invalid_fields" in log
        assert secret not in json.dumps(log)


def test_http_401_without_key_or_invalid_key(protocol_env):
    server, _, _ = protocol_env
    app = server.streamable_http_app()

    with TestClient(app) as test_client:
        # Missing Authorization header
        r1 = test_client.post("/mcp")
        assert r1.status_code == 401
        assert r1.content == b""

        # Non-bearer Authorization header
        r2 = test_client.post("/mcp", headers={"Authorization": "Basic dXNlcjpwYXNz"})
        assert r2.status_code == 401
        assert r2.content == b""

        # Invalid bearer key
        r3 = test_client.post("/mcp", headers={"Authorization": "Bearer wrong-key"})
        assert r3.status_code == 401
        assert r3.content == b""

        # Valid bearer key receives non-401 response
        r4 = test_client.post(
            "/mcp", headers={"Authorization": "Bearer full-secret-key"}
        )
        assert r4.status_code != 401
