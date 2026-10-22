"""Tests for input validation models (SPEC 7, S2, S3)."""

from __future__ import annotations

import pytest

from claims_mcp.models import (
    ErrorCode,
    ToolError,
    validate_claim_id,
    validate_get_claim,
    validate_get_claim_notes,
    validate_get_coverage_rule,
    validate_get_member_ytd_summary,
    validate_limit,
    validate_list_member_claims,
    validate_member_id,
    validate_offset,
    validate_plan_id,
    validate_procedure_code,
    validate_status,
    validate_year,
)

# ---------- claim_id ----------


class TestClaimIdValidation:
    @pytest.mark.parametrize(
        "value",
        [
            "CLM00000001",
            "CLM99999999",
            "CLM00000042",
        ],
    )
    def test_valid(self, value: str) -> None:
        assert validate_claim_id(value) is None

    @pytest.mark.parametrize(
        "value,reason",
        [
            ("CLM0000001", "too short"),
            ("CLM000000001", "too long"),
            ("clm00000001", "lowercase"),
            ("CLM0000000\n", "trailing newline"),
            ("CLM0000000١", "non-ASCII digit (Arabic-Indic)"),
            ("", "empty"),
            (None, "None"),
            (12345678, "integer"),
            ("CLM0000000 ", "trailing space"),
            ("' OR 1=1 --", "SQL injection"),
            ("CLM00000001; DROP TABLE claims", "SQL injection 2"),
        ],
    )
    def test_invalid(self, value: object, reason: str) -> None:
        assert validate_claim_id(value) == "claim_id"


# ---------- member_id ----------


class TestMemberIdValidation:
    @pytest.mark.parametrize("value", ["M000001", "M999999"])
    def test_valid(self, value: str) -> None:
        assert validate_member_id(value) is None

    @pytest.mark.parametrize(
        "value,reason",
        [
            ("M00001", "too short"),
            ("M0000001", "too long"),
            ("m000001", "lowercase"),
            ("M00000\n", "trailing newline"),
            ("M00000١", "non-ASCII digit"),
            ("", "empty"),
            (None, "None"),
            (123456, "integer"),
            ("' OR 1=1 --", "SQL injection"),
        ],
    )
    def test_invalid(self, value: object, reason: str) -> None:
        assert validate_member_id(value) == "member_id"


# ---------- plan_id ----------


class TestPlanIdValidation:
    @pytest.mark.parametrize("value", ["PLN001", "PLN999"])
    def test_valid(self, value: str) -> None:
        assert validate_plan_id(value) is None

    @pytest.mark.parametrize(
        "value,reason",
        [
            ("PLN01", "too short"),
            ("PLN0001", "too long"),
            ("pln001", "lowercase"),
            ("PLN00\n", "trailing newline"),
            ("PLN00١", "non-ASCII digit"),
            ("", "empty"),
            (None, "None"),
            (1, "integer"),
        ],
    )
    def test_invalid(self, value: object, reason: str) -> None:
        assert validate_plan_id(value) == "plan_id"


# ---------- procedure_code ----------


class TestProcedureCodeValidation:
    @pytest.mark.parametrize("value", ["PX0001", "PX9999"])
    def test_valid(self, value: str) -> None:
        assert validate_procedure_code(value) is None

    @pytest.mark.parametrize(
        "value,reason",
        [
            ("PX001", "too short"),
            ("PX00001", "too long"),
            ("px0001", "lowercase"),
            ("PX000\n", "trailing newline"),
            ("PX000١", "non-ASCII digit"),
            ("", "empty"),
            (None, "None"),
        ],
    )
    def test_invalid(self, value: object, reason: str) -> None:
        assert validate_procedure_code(value) == "procedure_code"


# ---------- status ----------


class TestStatusValidation:
    @pytest.mark.parametrize(
        "value",
        ["SUBMITTED", "PENDED", "APPROVED", "DENIED", "PAID"],
    )
    def test_valid(self, value: str) -> None:
        assert validate_status(value) is None

    def test_none_is_valid(self) -> None:
        assert validate_status(None) is None

    @pytest.mark.parametrize(
        "value,reason",
        [
            ("submitted", "lowercase"),
            ("INVALID", "not a status"),
            ("", "empty"),
            (1, "integer"),
            (True, "bool"),
        ],
    )
    def test_invalid(self, value: object, reason: str) -> None:
        assert validate_status(value) == "status"


# ---------- limit ----------


class TestLimitValidation:
    @pytest.mark.parametrize("value", [1, 20, 50])
    def test_valid(self, value: int) -> None:
        assert validate_limit(value, 1, 50) is None

    def test_none_is_valid(self) -> None:
        assert validate_limit(None, 1, 50) is None

    @pytest.mark.parametrize(
        "value,reason",
        [
            (0, "below min"),
            (51, "above max"),
            (-1, "negative"),
            (True, "bool (not int)"),
            (False, "bool false"),
            ("20", "string"),
            (3.14, "float"),
        ],
    )
    def test_invalid(self, value: object, reason: str) -> None:
        assert validate_limit(value, 1, 50) == "limit"


# ---------- offset ----------


class TestOffsetValidation:
    @pytest.mark.parametrize("value", [0, 100, 10000])
    def test_valid(self, value: int) -> None:
        assert validate_offset(value) is None

    def test_none_is_valid(self) -> None:
        assert validate_offset(None) is None

    @pytest.mark.parametrize(
        "value,reason",
        [
            (-1, "negative"),
            (10001, "above max"),
            (True, "bool"),
            ("0", "string"),
        ],
    )
    def test_invalid(self, value: object, reason: str) -> None:
        assert validate_offset(value) == "offset"


# ---------- year ----------


class TestYearValidation:
    @pytest.mark.parametrize("value", [2000, 2025, 2100])
    def test_valid(self, value: int) -> None:
        assert validate_year(value) is None

    @pytest.mark.parametrize(
        "value,reason",
        [
            (1999, "below min"),
            (2101, "above max"),
            (True, "bool"),
            ("2025", "string"),
            (2025.0, "float"),
        ],
    )
    def test_invalid(self, value: object, reason: str) -> None:
        assert validate_year(value) == "year"


# ---------- get_claim validator ----------


class TestValidateGetClaim:
    def test_valid(self) -> None:
        result = validate_get_claim({"claim_id": "CLM00000001"})
        assert isinstance(result, dict)
        assert result["claim_id"] == "CLM00000001"

    def test_invalid_id(self) -> None:
        result = validate_get_claim({"claim_id": "bad"})
        assert isinstance(result, ToolError)
        assert result.code == ErrorCode.INVALID_INPUT
        assert "claim_id" in result.message

    def test_missing_id(self) -> None:
        result = validate_get_claim({})
        assert isinstance(result, ToolError)

    def test_extra_parameter(self) -> None:
        result = validate_get_claim({"claim_id": "CLM00000001", "extra": "bad"})
        assert isinstance(result, ToolError)

    def test_sql_injection(self) -> None:
        result = validate_get_claim({"claim_id": "' OR 1=1 --"})
        assert isinstance(result, ToolError)
        # Must not echo the injection string
        assert "OR 1=1" not in result.message


# ---------- list_member_claims validator ----------


class TestValidateListMemberClaims:
    def test_valid_minimal(self) -> None:
        result = validate_list_member_claims({"member_id": "M000001"})
        assert isinstance(result, dict)
        assert result["limit"] == 20
        assert result["offset"] == 0

    def test_valid_full(self) -> None:
        result = validate_list_member_claims(
            {
                "member_id": "M000001",
                "status": "PAID",
                "limit": 10,
                "offset": 5,
            }
        )
        assert isinstance(result, dict)

    def test_invalid_status(self) -> None:
        result = validate_list_member_claims(
            {"member_id": "M000001", "status": "INVALID"}
        )
        assert isinstance(result, ToolError)

    def test_bool_as_limit(self) -> None:
        result = validate_list_member_claims({"member_id": "M000001", "limit": True})
        assert isinstance(result, ToolError)


# ---------- get_coverage_rule validator ----------


class TestValidateGetCoverageRule:
    def test_valid(self) -> None:
        result = validate_get_coverage_rule(
            {"plan_id": "PLN001", "procedure_code": "PX0001"}
        )
        assert isinstance(result, dict)

    def test_missing_procedure_code(self) -> None:
        result = validate_get_coverage_rule({"plan_id": "PLN001"})
        assert isinstance(result, ToolError)


# ---------- get_member_ytd_summary validator ----------


class TestValidateGetMemberYtdSummary:
    def test_valid(self) -> None:
        result = validate_get_member_ytd_summary({"member_id": "M000001", "year": 2025})
        assert isinstance(result, dict)

    def test_string_year(self) -> None:
        result = validate_get_member_ytd_summary(
            {"member_id": "M000001", "year": "2025"}
        )
        assert isinstance(result, ToolError)


# ---------- get_claim_notes validator ----------


class TestValidateGetClaimNotes:
    def test_valid_minimal(self) -> None:
        result = validate_get_claim_notes({"claim_id": "CLM00000001"})
        assert isinstance(result, dict)
        assert result["limit"] == 10

    def test_limit_bounds(self) -> None:
        result = validate_get_claim_notes({"claim_id": "CLM00000001", "limit": 21})
        assert isinstance(result, ToolError)

    def test_extra_parameter(self) -> None:
        result = validate_get_claim_notes({"claim_id": "CLM00000001", "extra": 1})
        assert isinstance(result, ToolError)
