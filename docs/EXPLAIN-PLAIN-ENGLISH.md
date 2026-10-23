# EXPLAIN-PLAIN-ENGLISH.md

Plain-English explanations of every SQL query in `src/claims_mcp/queries.py`.
Written for someone who knows what a database is but not SQL.

---

## 1. `get_claim(claim_id)`

**What it does:** Looks up a single insurance claim and brings back everything
about it — including who the provider is, whether they're in-network, and
which plan the member belongs to.

**How it works (SQL):** We *join* three tables together:
- `claims` — the claim itself (dates, amounts, status)
- `providers` — to get the provider's network status (IN_NETWORK or OUT_OF_NETWORK)
- `members` — to get the member's plan_id

We match rows where the claim's provider_id equals the provider table's
provider_id, and the claim's member_id equals the member table's member_id.
Then we filter by the one `claim_id` we're looking for.

**Parameters:** The `claim_id` is passed as a `?` placeholder — it never
touches the SQL text.

---

## 2. `list_member_claims(member_id, status, limit, offset)`

**What it does:** Lists all claims for a specific member, newest first.
Optionally filters by status (e.g., only PAID claims). Supports pagination.

**How it works (SQL):**
1. First we check the member exists (a simple lookup in the `members` table).
   If not found, we return `None` immediately — SPEC says "NOT_FOUND, not an
   empty list."
2. We count how many matching claims there are (the `total`).
3. We fetch the actual rows with `ORDER BY service_date DESC, claim_id DESC`
   (newest first, tie-break on claim_id), and `LIMIT ? OFFSET ?` for
   pagination.

If a status filter is provided, we add `AND status = ?` to both the count
and the fetch query. We use two separate hard-coded SQL strings (one with
the filter, one without) to avoid any dynamic SQL construction.

---

## 3. `get_coverage_rule(plan_id, procedure_code)`

**What it does:** Checks whether a specific procedure is covered under a
specific plan, whether it needs pre-authorization, and what the maximum
allowed amount is.

**How it works (SQL):** A straightforward single-table lookup on
`coverage_rules` with a compound primary key (`plan_id`, `procedure_code`).
The `covered` and `requires_preauth` columns store 0/1 in SQLite; we
convert them to Python booleans.

---

## 4. `get_member_ytd_summary(member_id, year)`

**What it does:** Shows a year-to-date financial summary for a member:
how many claims in each status, how much was billed, how much was paid,
and how much of their annual limit remains.

**How it works (SQL):**
1. Look up the member and JOIN to the `plans` table to get the annual limit
   and deductible.
2. Query the `claims` table, filtering by `member_id` and the year portion
   of `service_date` (using `substr(service_date, 1, 4)`). GROUP BY `status`
   to get counts and sums per status.
3. Calculate `remaining_annual_limit = annual_limit - sum(paid_amount for PAID claims)`,
   floored at 0 so it never goes negative.

Statuses with zero claims in that year are simply omitted from the output.

---

## 5. `get_claim_notes(claim_id, limit)`

**What it does:** Fetches the notes attached to a claim, newest first.
These notes are *untrusted free text* — they could contain anything,
including hostile instructions.

**How it works (SQL):**
1. Check the claim exists. If not, return `None`.
2. Query `claim_notes` filtered by `claim_id`, ordered by `created_on DESC`
   then `note_id DESC`, with `LIMIT ?`.
3. Each note's text is capped at 1,000 characters here; the `truncated`
   flag tells the caller whether it was cut.
4. The output always includes `"untrusted": true` as a signal to any
   downstream consumer that this text should not be trusted.

Sanitization of control characters and Unicode tricks happens later, in
the server layer (see `security.py`).

---

## Security notes (applies to all queries)

- Every query uses `?` parameter placeholders. User input is **never**
  part of the SQL string.
- The database connection is opened read-only with three layers of
  protection (URI `mode=ro`, `PRAGMA query_only=ON`, and an authorizer
  callback). See `db.py`.
- An AST test scans `queries.py` and fails if it finds f-strings,
  `.format()`, `%` formatting, or string concatenation with variables.
