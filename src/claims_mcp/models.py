"""Input validation models and output models.

ID patterns (SPEC 7), Pydantic input models for the five tools,
output models, error-code enum and safe-error type.
"""

from __future__ import annotations

import enum
import re
from typing import Any

# ---------- ID patterns (SPEC 7, re.fullmatch, ASCII digits only) ----------

CLAIM_ID_RE = re.compile(r"CLM[0-9]{8}")
MEMBER_ID_RE = re.compile(r"M[0-9]{6}")
PLAN_ID_RE = re.compile(r"PLN[0-9]{3}")
PROCEDURE_CODE_RE = re.compile(r"PX[0-9]{4}")

VALID_STATUSES = frozenset({"SUBMITTED", "PENDED", "APPROVED", "DENIED", "PAID"})


# ---------- Error codes (SPEC 8) ----------


class ErrorCode(str, enum.Enum):
    UNAUTHENTICATED = "UNAUTHENTICATED"
    RATE_LIMITED = "RATE_LIMITED"
    FORBIDDEN_TOOL = "FORBIDDEN_TOOL"
    INVALID_INPUT = "INVALID_INPUT"
    NOT_FOUND = "NOT_FOUND"
    INTERNAL = "INTERNAL"


class ToolError:
    """A safe error value to return from tool handlers."""

    def __init__(
        self,
        code: ErrorCode,
        detail: str | None = None,
        invalid_fields: list[str] | None = None,
    ):
        self.code = code
        self.detail = detail
        if invalid_fields is not None:
            self.invalid_fields = invalid_fields
        elif detail and detail.endswith(" is invalid"):
            self.invalid_fields = [detail.removesuffix(" is invalid")]
        else:
            self.invalid_fields = []

    @property
    def message(self) -> str:
        if self.detail:
            return f"{self.code.value}: {self.detail}"
        return self.code.value


# ---------- Validation helpers ----------


def validate_claim_id(value: Any) -> str | None:
    """Validate a claim ID. Returns the field name if invalid."""
    if not isinstance(value, str):
        return "claim_id"
    if not re.fullmatch(CLAIM_ID_RE, value):
        return "claim_id"
    return None


def validate_member_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return "member_id"
    if not re.fullmatch(MEMBER_ID_RE, value):
        return "member_id"
    return None


def validate_plan_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return "plan_id"
    if not re.fullmatch(PLAN_ID_RE, value):
        return "plan_id"
    return None


def validate_procedure_code(value: Any) -> str | None:
    if not isinstance(value, str):
        return "procedure_code"
    if not re.fullmatch(PROCEDURE_CODE_RE, value):
        return "procedure_code"
    return None


def validate_status(value: Any) -> str | None:
    """Validate optional status filter."""
    if value is None:
        return None
    if not isinstance(value, str):
        return "status"
    if value not in VALID_STATUSES:
        return "status"
    return None


def validate_limit(value: Any, lo: int, hi: int) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "limit"
    if not isinstance(value, int):
        return "limit"
    if value < lo or value > hi:
        return "limit"
    return None


def validate_offset(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "offset"
    if not isinstance(value, int):
        return "offset"
    if value < 0 or value > 10000:
        return "offset"
    return None


def validate_year(value: Any) -> str | None:
    if isinstance(value, bool):
        return "year"
    if not isinstance(value, int):
        return "year"
    if value < 2000 or value > 2100:
        return "year"
    return None


# ---------- Input validation (one function per tool) ----------


def validate_get_claim(args: dict[str, Any]) -> ToolError | dict[str, Any]:
    """Validate get_claim arguments. Returns ToolError or clean args."""
    invalid_fields: list[str] = []

    err = validate_claim_id(args.get("claim_id"))
    if err:
        invalid_fields.append(err)

    # Check for unexpected extra parameters
    expected = {"claim_id"}
    extra = set(args.keys()) - expected
    if extra:
        invalid_fields.extend(sorted(extra))

    if invalid_fields:
        return ToolError(
            ErrorCode.INVALID_INPUT,
            f"{invalid_fields[0]} is invalid",
        )

    return {"claim_id": args["claim_id"]}


def validate_list_member_claims(
    args: dict[str, Any],
) -> ToolError | dict[str, Any]:
    invalid_fields: list[str] = []

    err = validate_member_id(args.get("member_id"))
    if err:
        invalid_fields.append(err)

    err = validate_status(args.get("status"))
    if err:
        invalid_fields.append(err)

    err = validate_limit(args.get("limit"), 1, 50)
    if err:
        invalid_fields.append(err)

    err = validate_offset(args.get("offset"))
    if err:
        invalid_fields.append(err)

    expected = {"member_id", "status", "limit", "offset"}
    extra = set(args.keys()) - expected
    if extra:
        invalid_fields.extend(sorted(extra))

    if invalid_fields:
        return ToolError(
            ErrorCode.INVALID_INPUT,
            f"{invalid_fields[0]} is invalid",
        )

    return {
        "member_id": args["member_id"],
        "status": args.get("status"),
        "limit": args.get("limit", 20),
        "offset": args.get("offset", 0),
    }


def validate_get_coverage_rule(
    args: dict[str, Any],
) -> ToolError | dict[str, Any]:
    invalid_fields: list[str] = []

    err = validate_plan_id(args.get("plan_id"))
    if err:
        invalid_fields.append(err)

    err = validate_procedure_code(args.get("procedure_code"))
    if err:
        invalid_fields.append(err)

    expected = {"plan_id", "procedure_code"}
    extra = set(args.keys()) - expected
    if extra:
        invalid_fields.extend(sorted(extra))

    if invalid_fields:
        return ToolError(
            ErrorCode.INVALID_INPUT,
            f"{invalid_fields[0]} is invalid",
        )

    return {
        "plan_id": args["plan_id"],
        "procedure_code": args["procedure_code"],
    }


def validate_get_member_ytd_summary(
    args: dict[str, Any],
) -> ToolError | dict[str, Any]:
    invalid_fields: list[str] = []

    err = validate_member_id(args.get("member_id"))
    if err:
        invalid_fields.append(err)

    err = validate_year(args.get("year"))
    if err:
        invalid_fields.append(err)

    expected = {"member_id", "year"}
    extra = set(args.keys()) - expected
    if extra:
        invalid_fields.extend(sorted(extra))

    if invalid_fields:
        return ToolError(
            ErrorCode.INVALID_INPUT,
            f"{invalid_fields[0]} is invalid",
        )

    return {
        "member_id": args["member_id"],
        "year": args["year"],
    }


def validate_get_claim_notes(
    args: dict[str, Any],
) -> ToolError | dict[str, Any]:
    invalid_fields: list[str] = []

    err = validate_claim_id(args.get("claim_id"))
    if err:
        invalid_fields.append(err)

    err = validate_limit(args.get("limit"), 1, 20)
    if err:
        invalid_fields.append(err)

    expected = {"claim_id", "limit"}
    extra = set(args.keys()) - expected
    if extra:
        invalid_fields.extend(sorted(extra))

    if invalid_fields:
        return ToolError(
            ErrorCode.INVALID_INPUT,
            f"{invalid_fields[0]} is invalid",
        )

    return {
        "claim_id": args["claim_id"],
        "limit": args.get("limit", 10),
    }


# ---------- Validators mapping ----------

VALIDATORS = {
    "get_claim": validate_get_claim,
    "list_member_claims": validate_list_member_claims,
    "get_coverage_rule": validate_get_coverage_rule,
    "get_member_ytd_summary": validate_get_member_ytd_summary,
    "get_claim_notes": validate_get_claim_notes,
}
