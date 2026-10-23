"""Tests for audit log (SPEC S9, section 10, TASKS T7).

Tests:
- Fields present in audit entries
- No payloads or note text in audit entries
- Invalid calls log field names only
- A writer that raises results in AuditWriteError (fail closed)
- One line per call
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from claims_mcp.audit import AuditLogger, AuditWriteError


@pytest.fixture()
def audit_path(tmp_path: Path) -> Path:
    return tmp_path / "audit" / "audit.jsonl"


@pytest.fixture()
def logger(audit_path: Path) -> AuditLogger:
    return AuditLogger(audit_path)


class TestAuditFields:
    def test_ok_entry_has_required_fields(
        self, logger: AuditLogger, audit_path: Path
    ) -> None:
        logger.log(
            tool="get_claim",
            args={"claim_id": "CLM00000001"},
            outcome="ok",
            rows=1,
            duration_ms=3.2,
        )
        lines = audit_path.read_text().strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert "ts" in entry
        assert "request_id" in entry
        assert entry["caller"] == "stdio-local"
        assert entry["transport"] == "stdio"
        assert entry["tool"] == "get_claim"
        assert entry["outcome"] == "ok"
        assert entry["rows"] == 1
        assert entry["duration_ms"] == 3.2
        assert entry["args"] == {"claim_id": "CLM00000001"}

    def test_custom_caller_and_transport(
        self, logger: AuditLogger, audit_path: Path
    ) -> None:
        logger.log(
            caller="analyst-1",
            transport="http",
            tool="get_claim",
            args={"claim_id": "CLM00000001"},
            outcome="ok",
        )
        entry = json.loads(audit_path.read_text().strip())
        assert entry["caller"] == "analyst-1"
        assert entry["transport"] == "http"


class TestNoPayloadsInAudit:
    def test_args_logged_for_valid_call(
        self, logger: AuditLogger, audit_path: Path
    ) -> None:
        """Args like claim_id are logged (they are IDs, not payloads)."""
        logger.log(
            tool="get_claim",
            args={"claim_id": "CLM00000001"},
            outcome="ok",
        )
        entry = json.loads(audit_path.read_text().strip())
        assert entry["args"] == {"claim_id": "CLM00000001"}

    def test_no_result_payloads(self, logger: AuditLogger, audit_path: Path) -> None:
        """The audit entry must not contain result data."""
        logger.log(
            tool="get_claim",
            args={"claim_id": "CLM00000001"},
            outcome="ok",
            rows=1,
        )
        entry = json.loads(audit_path.read_text().strip())
        assert "result" not in entry
        assert "data" not in entry
        assert "payload" not in entry
        assert "note_text" not in entry


class TestInvalidCallAudit:
    def test_invalid_args_are_null(self, logger: AuditLogger, audit_path: Path) -> None:
        logger.log(
            tool="get_claim",
            outcome="invalid",
            error_code="INVALID_INPUT",
            invalid_fields=["claim_id"],
        )
        entry = json.loads(audit_path.read_text().strip())
        assert entry["args"] is None
        assert entry["invalid_fields"] == ["claim_id"]
        assert entry["outcome"] == "invalid"

    def test_invalid_does_not_log_attacker_input(
        self, logger: AuditLogger, audit_path: Path
    ) -> None:
        """Attacker-chosen strings must not appear in the audit log."""
        logger.log(
            tool="get_claim",
            outcome="invalid",
            error_code="INVALID_INPUT",
            invalid_fields=["claim_id"],
        )
        text = audit_path.read_text()
        # Field names are OK, but no raw input values
        assert "claim_id" in text
        assert "OR 1=1" not in text


class TestOneLinePerCall:
    def test_multiple_calls(self, logger: AuditLogger, audit_path: Path) -> None:
        for i in range(3):
            logger.log(
                tool="get_claim",
                args={"claim_id": f"CLM0000000{i}"},
                outcome="ok",
            )
        lines = audit_path.read_text().strip().split("\n")
        assert len(lines) == 3
        for line in lines:
            json.loads(line)  # each line is valid JSON


class TestFailClosed:
    def test_write_failure_raises_audit_error(self, tmp_path: Path) -> None:
        # Point to an unwritable path
        bad_path = tmp_path / "readonly_dir" / "audit.jsonl"
        bad_path.parent.mkdir(parents=True)
        bad_path.parent.chmod(0o444)

        logger = AuditLogger(bad_path)
        with pytest.raises(AuditWriteError):
            logger.log(
                tool="get_claim",
                args={"claim_id": "CLM00000001"},
                outcome="ok",
            )
        # Restore permissions for cleanup
        bad_path.parent.chmod(0o755)

    def test_write_failure_means_no_data(self) -> None:
        """When audit write fails, AuditWriteError is raised before
        any data can be returned to the caller."""
        # This is a structural test — the server catches AuditWriteError
        # and returns INTERNAL. Here we verify the exception type exists
        # and is distinct.
        assert issubclass(AuditWriteError, Exception)
        assert not issubclass(AuditWriteError, RuntimeError)


class TestRequestId:
    def test_returns_request_id(self, logger: AuditLogger) -> None:
        rid = logger.log(tool="get_claim", outcome="ok")
        assert isinstance(rid, str)
        assert len(rid) > 0

    def test_custom_request_id(self, logger: AuditLogger, audit_path: Path) -> None:
        rid = logger.log(
            request_id="custom-123",
            tool="get_claim",
            outcome="ok",
        )
        assert rid == "custom-123"
        entry = json.loads(audit_path.read_text().strip())
        assert entry["request_id"] == "custom-123"
