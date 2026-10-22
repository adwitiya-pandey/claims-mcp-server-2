# TASKS: claims-mcp-server (Project A)

> **AUTONOMOUS END-TO-END EXECUTION RULE (SINGLE-CHAT WORKFLOW)**:
> Execute **all tasks in `TASKS.md` back-to-back from `T0`/`H0` through `v0.1.0` GitHub push** in a single continuous run.
> - **Do NOT stop after individual tasks** to wait for human PR merges. Commit each task cleanly with Conventional Commits (`Refs: <TaskID>`), merge branches automatically, update `PROGRESS.md`, and continue straight to the next task.
> - **Write 100% of the code yourself** (including `queries.py`, `graph.py`, `policy.py`, `approvals.py`, `sqlsafe.py`, and the `H9` merge conflict).
> - **API Keys**: Use `GEMINI_API_KEY` from the project's `.env` file for live Gemini steps. Never require `ANTHROPIC_API_KEY` or `LANGSMITH_API_KEY`.


Order matters. Execute all tasks sequentially from start to finish in a single autonomous run. Owner tags: **AGENT** = the coding agent does it; **HUMAN** = the owner does it; **REVIEW** = the owner reads and explains it back.
If a task runs long, shrink the next one; do not extend the project. New ideas go in `docs/backlog.md`; nothing from the backlog is built before `v0.1.0`.
Commit style: Conventional Commits with a `Refs: T4` trailer (see AGENTS.md).

---

## T0 (AGENT): create public GitHub repository `adwitiya-pandey/claims-mcp-server`
1. In `~/projects/claims-mcp-server`, initialize git (`git init`, `git branch -M main`) and remove any stale remote (`git remote remove origin 2>/dev/null || true`).
2. Ensure `.gitignore` excludes `.env`, `ONE-SHOT-PROMPT.txt`, `PROGRESS.md`, `PLAN-PRIVATE.md`, `*.db`, `audit/`, `keys.json`.
3. Stage and commit the contract files: `git add . && git commit -m "docs: add scope contract (AGENTS, SPEC, TASKS)"`.
4. Create the new public GitHub repository and push `main`:
   `gh repo create adwitiya-pandey/claims-mcp-server --public --source=. --remote=origin --push --description "Read-only MCP server over a synthetic health-insurance claims database: named parameterized tools, API-key auth, audit log, threat model"`
Accept: `https://github.com/adwitiya-pandey/claims-mcp-server` is created publicly and `main` is pushed.

## T1 (AGENT): scaffold + SDK facts
1. `uv init --package`; `src/claims_mcp/` with empty modules (`config.py, db.py, queries.py, models.py, security.py, audit.py, server.py, __main__.py`), each with a one-line docstring.
2. `pyproject.toml`: Python >=3.12; runtime dependency `mcp` (v2, version pinned in `uv.lock`); dev: `pytest`, `ruff`, plus an async test plugin or `httpx` only if later tasks need them (ask first if unsure).
3. `.gitignore` is provided; extend it only if needed. Add `.env.example` (variable names from SPEC 11), a minimal `README.md` stub that says "Status: in progress", and a `LICENSE` (MIT, holder: Adwitiya Pandey).
4. `.github/workflows/ci.yml`: checkout, set up `uv`, `uv sync`, `ruff check`, `ruff format --check`, `pytest -q`. Look up current major versions of the actions you use; do not guess.
5. **Before any MCP code:** `docs/mcp_sdk_notes.md` is pre-filled (verified on `mcp` 2.3.0, 17 Oct 2026). Re-run its probe snippets in a scratch script against the version `uv` installs, correct the file if anything differs, and add what you could not confirm (SPEC 16).
6. One smoke test that imports the package.
Accept: `uv sync` then `uv run ruff check . && uv run pytest -q` pass; `docs/mcp_sdk_notes.md` exists.

## T2 (AGENT): schema, seed, fixture
1. `schema.sql` = the DDL block from SPEC 6, exactly.
2. `scripts/seed_db.py --out data/claims.db`: deterministic synthetic data per SPEC 6, including at least 15 adversarial notes and `data/adversarial_note_ids.txt`.
3. `tests/fixtures.py`: `build_fixture_db(path)` with the fixed small dataset from SPEC 6. Put a comment block at the top listing every row, so expected values are readable.
4. Test: the seed produces the expected row counts and satisfies every CHECK constraint (loading it must not raise); running it twice gives identical row counts.
Accept: `uv run python scripts/seed_db.py --out data/claims.db` then `uv run pytest tests -q -k "seed or fixture"` pass.

## T3 (AGENT): models and validation
1. `models.py`: ID patterns (SPEC 7), Pydantic input models for the five tools (strict types: no bool-as-int, no coercion of strings to numbers, forbid extra fields), output models, an error-code enum and a safe-error type.
2. `tests/test_validation.py`: a parametrized table per type covering valid values, trailing newline, non-ASCII digits, empty, None, wrong type, overlong, SQL-injection strings, bounds for limit/offset/year.
Accept: `uv run pytest tests/test_validation.py -q`.

## T4 (AGENT): read-only database layer (S1)
1. `db.py`: `open_readonly(path)` per SPEC S1 and AGENTS gotcha 3. Raise a safe error for a missing file without creating one.
2. `tests/test_db_readonly.py`: INSERT, UPDATE, DELETE, DROP, CREATE, ATTACH, writable PRAGMA all fail; SELECT, JOIN, GROUP BY and aggregate functions succeed; a missing path raises and leaves no file behind.
Accept: `uv run pytest tests/test_db_readonly.py -q`.
REVIEW: be able to explain what `mode=ro`, `query_only` and the authorizer each protect against, and why all three exist.

## T5a (AGENT): query tests first
Write `tests/test_queries.py` against the fixture DB for the five query functions (signatures in `queries.py` are stubs that raise `NotImplementedError`; the agent creates the stubs, with a docstring per function describing the contract in plain English and the SQL concepts from SPEC 7). Include not-found cases, status filter, pagination, and the YTD arithmetic. Add the AST test that fails if `queries.py` builds SQL with f-strings, `.format()`, `%` or `+`.
Accept: the tests exist and fail only with `NotImplementedError`.

## T5b (AGENT): implement all 5 parameterized SQL queries (`queries.py`)
Implement all five functions in `src/claims_mcp/queries.py` using strictly parameterized `?` placeholders so all tests in `tests/test_queries.py` pass, and document every query in `docs/EXPLAIN-PLAIN-ENGLISH.md`.
Accept: `uv run pytest tests/test_queries.py -q` all green.

## T6 (AGENT): security helpers (S4-S7)
1. `security.py`: load `keys.json`, hash and verify keys with `hmac.compare_digest`, per-key tool allowlist, fixed-window rate limiter with an injectable clock, `sanitize_untrusted_text` per S7.
2. `scripts/make_key.py --id analyst-1 --tools all|tool1,tool2`: prints the plaintext key once, appends only its SHA-256 to `keys.json`.
3. `tests/test_security.py`: missing and wrong keys, allowed vs forbidden tools, rate-limit window with a fake clock, sanitizer cases (zero-width, bidi, control characters, CRLF, 20,000-character input, empty).
Accept: `uv run pytest tests/test_security.py -q`.

## T7 (AGENT): audit log (S9)
1. `audit.py`: JSONL writer per SPEC 10; one line per call; fail closed (raise a typed error the server turns into `INTERNAL`).
2. `tests/test_audit.py`: fields present; no payloads or note text; invalid calls log field names only; a writer that raises results in no data returned.
Accept: `uv run pytest tests/test_audit.py -q`.

## T8 (AGENT): the server (pipeline)
1. `server.py`: `MCPServer` with the five tools as plain `def` handlers. Each runs the SPEC 5 pipeline in order: authenticate, rate limit, authorize, validate, query, sanitize, audit, return. Map every failure to the SPEC 8 error codes.
2. `__main__.py`: `--transport stdio|http`, config validation at startup (S10), HTTP on 127.0.0.1 by default.
3. If the SDK supports tool annotations, mark all tools read-only.
4. **S13 first:** a failing test that sends a missing, an extra and a wrongly typed argument through a real `Client` and asserts the SPEC 8 error text, no echo of the input, and exactly one audit line. Then pick the mechanism (see `docs/mcp_sdk_notes.md`) and record it in `docs/decisions.md`.
5. `tests/test_config.py` for startup refusals.
Accept: `uv run pytest -q` passes; `uv run python -m claims_mcp --transport stdio` starts without error against `data/claims.db`.

## T9 (AGENT): protocol tests and HTTP auth
1. Read the SDK's Authorization and Testing docs (SPEC 16). Add bearer-key authentication for the HTTP transport. Use the SDK's documented mechanism if it fits; otherwise a small ASGI middleware around the HTTP app. Record the choice in `docs/decisions.md`.
2. `tests/test_server_protocol.py`: through a real MCP `Client`, assert exactly five tools are listed; each tool's happy path; `NOT_FOUND`; `INVALID_INPUT`; a forbidden tool; SDK-rejected calls (missing, extra, wrongly typed argument) give a safe error and one audit line; HTTP 401 without a key; the exact error text format of SPEC 8.
Accept: `uv run pytest tests/test_server_protocol.py -q`.

## T10 (AGENT): hostile-input suite
`tests/test_injection.py`, at least 25 parametrized cases: SQL-style strings in every ID parameter of every tool; Unicode digit and newline tricks; oversized values; negative, huge and non-integer limit/offset; extra unexpected parameters; adversarial notes from the seed returned sanitized, capped and flagged `untrusted`; a call made after the rate limit. Each case asserts a safe error (or sanitized data), no leaked internals, and exactly one audit line.
Accept: `uv run pytest tests/test_injection.py -q`.

## T11 (AGENT): demo client and README
1. `scripts/demo_client.py`: connects with a real key over HTTP, calls each tool, includes one adversarial note, and prints compact output. No LLM.
2. `README.md`: what and why (the client call, three sentences), quickstart (three commands), architecture diagram, security summary with a link to `THREAT_MODEL.md`, honest limitations from SPEC 15.
Accept: a fresh clone follows the quickstart and the demo runs.

## T12 (AGENT): threat model and decisions
`THREAT_MODEL.md`: assets, trust boundaries, a threats table (spoofing, tampering, repudiation, information disclosure, denial of service, elevation; each with the mitigation and the test that proves it), and residual risks. Complete `docs/decisions.md` from SPEC 14 with what was actually built. Write both clearly and add a beginner summary to `docs/EXPLAIN-PLAIN-ENGLISH.md`.
Accept: every S-requirement maps to a named test.

## T13 (AGENT): Dockerfile
Create the non-root `Dockerfile` with read-only DB mount and healthcheck (Docker is installed in the environment).

## T14 (AGENT): final verification, git tag `v0.1.0`, and push to GitHub
1. Merge everything. `git switch main`, `git pull`, confirm the README quickstart in a fresh clone in an empty directory (`git clone` into a new folder, then the three commands, then `scripts/demo_client.py`).
2. `git tag v0.1.0` and `git push origin v0.1.0`. In the GitHub repo settings add a description and topics (`mcp`, `sqlite`, `python`, `security`, `audit-log`).
3. `git grep -n -i -E "api[_-]?key|secret|password"` shows only variable names and documentation, never a value.
Accept: the tag is pushed and the fresh-clone run passes.
