"""Parameterized SQL query functions for the five tools.

Each function receives a read-only sqlite3.Connection and validated
scalar parameters, executes a fixed parameterized query using ?
placeholders, and returns a dict matching the SPEC 7 output contract.

No f-strings, .format(), %, or string concatenation is used to build
SQL. All inputs are bound as parameters.
"""

from __future__ import annotations

import sqlite3


def get_claim(conn: sqlite3.Connection, claim_id: str) -> dict | None:
    """Fetch one claim joined with its provider's network status and the
    member's plan.

    SQL concepts: a JOIN across claims, providers, members.

    Returns a dict with keys: claim_id, member_id, plan_id, provider_id,
    provider_network_status, procedure_code, diagnosis_code, service_date,
    submitted_on, billed_amount, allowed_amount, paid_amount, status.
    Returns None if not found.
    """
    raise NotImplementedError


def list_member_claims(
    conn: sqlite3.Connection,
    member_id: str,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict | None:
    """List claims for a member, newest first (service_date DESC, then
    claim_id DESC). Optional status filter.

    SQL concepts: optional filter, ORDER BY, LIMIT/OFFSET, a COUNT query.

    Returns a dict with keys: total, limit, offset, items.
    Each item: claim_id, service_date, procedure_code, billed_amount, status.
    Returns None if the member does not exist.
    """
    raise NotImplementedError


def get_coverage_rule(
    conn: sqlite3.Connection, plan_id: str, procedure_code: str
) -> dict | None:
    """Look up a coverage rule for a plan and procedure code.

    Returns a dict with keys: plan_id, procedure_code, covered (bool),
    requires_preauth (bool), max_allowed (number or null).
    Returns None if not found.
    """
    raise NotImplementedError


def get_member_ytd_summary(
    conn: sqlite3.Connection, member_id: str, year: int
) -> dict | None:
    """Year-to-date summary for a member.

    SQL concepts: GROUP BY, SUM, COUNT, filtering by year, a JOIN to plans.

    Returns a dict with keys: member_id, year, plan_id, annual_limit,
    deductible, by_status (list of {status, claim_count, total_billed,
    total_paid}), remaining_annual_limit.
    remaining_annual_limit = annual_limit - sum(paid of PAID claims that year),
    floored at 0. Statuses with no claims are omitted from by_status.
    Returns None if the member does not exist.
    """
    raise NotImplementedError


def get_claim_notes(
    conn: sqlite3.Connection, claim_id: str, limit: int = 10
) -> dict | None:
    """Fetch notes for a claim, newest first.

    Returns a dict with keys: claim_id, untrusted (always True),
    notes (list of {note_id, created_on, author_type, text, truncated}).
    text is raw from the DB here; sanitization happens in the server layer.
    Returns None if the claim does not exist.
    """
    raise NotImplementedError
