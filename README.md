# Meridian Health Claims MCP Server

A secure, read-only Model Context Protocol (MCP) server over a synthetic health-insurance claims database.

## What and Why

Meridian Health TPA (fictional) processes approximately 3,000 health insurance claims daily across four commercial insurers and requires AI assistants to assist analysts in querying claims data. Compliance and security enforce an absolute boundary: **no AI assistant ever receives direct SQL or direct database access**, and every interaction must leave an immutable, auditable trail. This project serves as the controlled intermediary—exposing five named, strictly parameterized read-only tools with defense-in-depth SQLite protection, API key authentication, per-tool authorization, rate limiting, input sanitization, and fail-closed audit logging.

## Quickstart

Run these three commands to set up the environment, seed synthetic data, and start the server:

```bash
# 1. Install dependencies
uv sync

# 2. Seed synthetic database and generate an API key
uv run python scripts/seed_db.py --out data/claims.db && uv run python scripts/make_key.py --id demo-analyst --tools all

# 3. Start the server (stdio transport for inspector / agents)
CLAIMS_DB_PATH=data/claims.db uv run python -m claims_mcp --transport stdio
```

### Running the Live HTTP Demo Client

To test the server over Streamable HTTP with live API key authentication:

```bash
# In terminal 1: Start HTTP server
CLAIMS_DB_PATH=data/claims.db CLAIMS_KEYS_FILE=keys.json uv run python -m claims_mcp --transport http

# In terminal 2: Run the demo client with the generated key
uv run python scripts/demo_client.py --key <YOUR_GENERATED_RAW_KEY>
```

## Architecture

The server processes every request through an immutable 9-step pipeline where any failure short-circuits to the audit logger:

```
MCP client (agent / inspector / demo_client.py)
        |  stdio  or  streamable HTTP (127.0.0.1, Bearer key)
        v
+-----------------------------------------------------------+
| server.py  (MCPServer, 5 tools, handlers are plain `def`) |
|                                                           |
|  1 authenticate -> key_id        (security.py)            |
|  2 rate limit per key_id         (security.py)            |
|  3 authorize tool for key_id     (security.py)            |
|  4 validate inputs               (models.py)              |
|  5 open read-only connection     (db.py)  one per call    |
|  6 run fixed parameterized SQL   (queries.py)             |
|  7 build output, sanitize text   (models.py, security.py) |
|  8 write audit line, FAIL CLOSED (audit.py)               |
|  9 return result                                          |
+-----------------------------------------------------------+
        |                                  |
        v                                  v
   claims.db (read-only)           audit.jsonl (append-only)
```

## Named Read-Only Tools

1. `get_claim(claim_id)`: Fetches a claim joined with member plan and provider network status.
2. `list_member_claims(member_id, status=None, limit=20, offset=0)`: Lists member claims ordered newest first.
3. `get_coverage_rule(plan_id, procedure_code)`: Looks up coverage and prior authorization rules.
4. `get_member_ytd_summary(member_id, year)`: Aggregates claim totals by status and calculates remaining annual limit.
5. `get_claim_notes(claim_id, limit=10)`: Retrieves claimant, provider, or analyst notes, sanitized, capped, and flagged `untrusted: true`.

## Security Summary

- **Connection Read-Only Guarantee (S1)**: SQLite opened with URI `mode=ro`, `PRAGMA query_only=ON`, and an authorizer callback that allows only `SELECT`, `READ`, and `FUNCTION` operations while denying `INSERT`, `UPDATE`, `DELETE`, `ATTACH`, and `PRAGMA`.
- **Zero Dynamic SQL (S2, S3)**: All SQL queries in `queries.py` use strictly parameterized `?` placeholders. Zero string interpolation, formatting, or concatenation is used.
- **S13 Input Interception**: Tool calls are intercepted before SDK-level argument parsing to prevent raw inputs from echoing back to the caller in error messages and to guarantee that invalid or hostile requests are audited.
- **Authentication & Authorization (S4, S5)**: Bearer tokens are SHA-256 hashed at rest in `keys.json` and verified with `hmac.compare_digest` in constant time. Per-key tool allowlists restrict permissions.
- **Fail-Closed Audit Log (S9)**: Every call writes an append-only JSONL record (`audit/audit.jsonl`). If the audit line cannot be written, no data is returned and a safe `INTERNAL` code is emitted.
- **Untrusted Text Sanitization (S7)**: Note text is stripped of control characters and Unicode Cf category characters (zero-width, bidi overrides), truncated to 1,000 characters, and permanently flagged `untrusted: true`.

For full threat analysis and proof mapping, see [THREAT_MODEL.md](THREAT_MODEL.md).

## Honest Limitations

As documented in SPEC 15:
- **Prompt Injection Defense Boundary**: Sanitizing and flagging notes as `untrusted: true` informs downstream consumers but does NOT prevent a large language model from obeying adversarial text. True protection relies on read-only access, absence of write tools, and human-in-the-loop validation.
- **Transport Security**: Intended for localhost (127.0.0.1); production deployment requires an external TLS reverse proxy (e.g., Nginx, Envoy).
- **Process Concurrency**: The in-memory fixed-window rate limiter operates within a single process.
- **Key Management**: API key storage and rotation are manual file-based operations.
- **Audit Tamper-Resistance**: Audit logs are append-only text lines without cryptographic forward secrecy.
