"""Parameterized SQL query functions for the five tools.

Each function receives a read-only sqlite3.Connection and validated
scalar parameters, executes a fixed parameterized query using ?
placeholders, and returns a dict matching the SPEC 7 output contract.

No f-strings, .format(), %, or string concatenation is used to build
SQL. All inputs are bound as parameters.
"""

from __future__ import annotations

import sqlite3

# Maximum length for note text before truncation (SPEC S7)
_NOTE_TEXT_CAP = 1000


def get_claim(conn: sqlite3.Connection, claim_id: str) -> dict | None:
    """Fetch one claim joined with its provider's network status and the
    member's plan.

    SQL concepts: a JOIN across claims, providers, members.

    Returns a dict with keys: claim_id, member_id, plan_id, provider_id,
    provider_network_status, procedure_code, diagnosis_code, service_date,
    submitted_on, billed_amount, allowed_amount, paid_amount, status.
    Returns None if not found.
    """
    row = conn.execute(
        """
        SELECT
            c.claim_id,
            c.member_id,
            m.plan_id,
            c.provider_id,
            p.network_status AS provider_network_status,
            c.procedure_code,
            c.diagnosis_code,
            c.service_date,
            c.submitted_on,
            c.billed_amount,
            c.allowed_amount,
            c.paid_amount,
            c.status
        FROM claims c
        JOIN providers p ON c.provider_id = p.provider_id
        JOIN members m ON c.member_id = m.member_id
        WHERE c.claim_id = ?
        """,
        (claim_id,),
    ).fetchone()

    if row is None:
        return None

    return dict(row)


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
    # Check member exists
    exists = conn.execute(
        "SELECT 1 FROM members WHERE member_id = ?", (member_id,)
    ).fetchone()
    if exists is None:
        return None

    # Build the query with an optional status filter.
    # We use two separate fixed SQL strings to avoid dynamic SQL.
    if status is not None:
        count_row = conn.execute(
            "SELECT COUNT(*) FROM claims WHERE member_id = ? AND status = ?",
            (member_id, status),
        ).fetchone()
        total = count_row[0]

        rows = conn.execute(
            """
            SELECT claim_id, service_date, procedure_code, billed_amount, status
            FROM claims
            WHERE member_id = ? AND status = ?
            ORDER BY service_date DESC, claim_id DESC
            LIMIT ? OFFSET ?
            """,
            (member_id, status, limit, offset),
        ).fetchall()
    else:
        count_row = conn.execute(
            "SELECT COUNT(*) FROM claims WHERE member_id = ?",
            (member_id,),
        ).fetchone()
        total = count_row[0]

        rows = conn.execute(
            """
            SELECT claim_id, service_date, procedure_code, billed_amount, status
            FROM claims
            WHERE member_id = ?
            ORDER BY service_date DESC, claim_id DESC
            LIMIT ? OFFSET ?
            """,
            (member_id, limit, offset),
        ).fetchall()

    items = [dict(r) for r in rows]

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": items,
    }


def get_coverage_rule(
    conn: sqlite3.Connection, plan_id: str, procedure_code: str
) -> dict | None:
    """Look up a coverage rule for a plan and procedure code.

    Returns a dict with keys: plan_id, procedure_code, covered (bool),
    requires_preauth (bool), max_allowed (number or null).
    Returns None if not found.
    """
    row = conn.execute(
        """
        SELECT plan_id, procedure_code, covered, requires_preauth, max_allowed
        FROM coverage_rules
        WHERE plan_id = ? AND procedure_code = ?
        """,
        (plan_id, procedure_code),
    ).fetchone()

    if row is None:
        return None

    return {
        "plan_id": row["plan_id"],
        "procedure_code": row["procedure_code"],
        "covered": bool(row["covered"]),
        "requires_preauth": bool(row["requires_preauth"]),
        "max_allowed": row["max_allowed"],
    }


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
    # Check member exists and get plan info
    member_row = conn.execute(
        """
        SELECT m.member_id, m.plan_id, p.annual_limit, p.deductible
        FROM members m
        JOIN plans p ON m.plan_id = p.plan_id
        WHERE m.member_id = ?
        """,
        (member_id,),
    ).fetchone()

    if member_row is None:
        return None

    plan_id = member_row["plan_id"]
    annual_limit = member_row["annual_limit"]
    deductible = member_row["deductible"]

    # Year prefix for service_date filtering: match YYYY- prefix
    year_str = str(year)

    # Get by-status aggregation
    status_rows = conn.execute(
        """
        SELECT
            status,
            COUNT(*) AS claim_count,
            SUM(billed_amount) AS total_billed,
            SUM(COALESCE(paid_amount, 0)) AS total_paid
        FROM claims
        WHERE member_id = ?
          AND substr(service_date, 1, 4) = ?
        GROUP BY status
        """,
        (member_id, year_str),
    ).fetchall()

    by_status = []
    total_paid_for_paid = 0.0
    for row in status_rows:
        entry = {
            "status": row["status"],
            "claim_count": row["claim_count"],
            "total_billed": row["total_billed"],
            "total_paid": row["total_paid"],
        }
        by_status.append(entry)
        if row["status"] == "PAID":
            total_paid_for_paid = row["total_paid"]

    remaining = max(0.0, annual_limit - total_paid_for_paid)

    return {
        "member_id": member_id,
        "year": year,
        "plan_id": plan_id,
        "annual_limit": annual_limit,
        "deductible": deductible,
        "by_status": by_status,
        "remaining_annual_limit": remaining,
    }


def get_claim_notes(
    conn: sqlite3.Connection, claim_id: str, limit: int = 10
) -> dict | None:
    """Fetch notes for a claim, newest first.

    Returns a dict with keys: claim_id, untrusted (always True),
    notes (list of {note_id, created_on, author_type, text, truncated}).
    text is raw from the DB here; sanitization happens in the server layer.
    Returns None if the claim does not exist.
    """
    # Check claim exists
    exists = conn.execute(
        "SELECT 1 FROM claims WHERE claim_id = ?", (claim_id,)
    ).fetchone()
    if exists is None:
        return None

    rows = conn.execute(
        """
        SELECT note_id, created_on, author_type, note_text
        FROM claim_notes
        WHERE claim_id = ?
        ORDER BY created_on DESC, note_id DESC
        LIMIT ?
        """,
        (claim_id, limit),
    ).fetchall()

    notes = []
    for row in rows:
        raw_text = row["note_text"]
        truncated = len(raw_text) > _NOTE_TEXT_CAP
        text = raw_text[:_NOTE_TEXT_CAP] if truncated else raw_text
        notes.append(
            {
                "note_id": row["note_id"],
                "created_on": row["created_on"],
                "author_type": row["author_type"],
                "text": text,
                "truncated": truncated,
            }
        )

    return {
        "claim_id": claim_id,
        "untrusted": True,
        "notes": notes,
    }
