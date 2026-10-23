# Threat Model: claims-mcp-server

This threat model outlines the security architecture, trust boundaries, threat analysis (STRIDE), requirement-to-test verification mapping, and residual risks for the Meridian Health Claims MCP Server.

---

## 1. Assets

The system manages and protects the following assets:

1. **Synthetic Claims Database (`claims.db`)**: 6 relational tables containing plan terms, member demographics, provider networks, procedure coverage rules, claims, and claim notes. Must remain strictly read-only and uncorrupted.
2. **API Keys Store (`keys.json`)**: SHA-256 hashed API keys and associated tool permission allowlists. Plaintext keys must never be stored, logged, or retrievable.
3. **Audit Log (`audit/audit.jsonl`)**: An immutable, append-only JSONL record of all access requests. Must not leak sensitive payload contents or attacker-controlled invalid strings.
4. **Host System Integrity**: Execution environment (WSL2 / Linux container); must prevent command injection, arbitrary file writes, and unauthorized network egress.

---

## 2. Trust Boundaries

```
[ Untrusted Client / AI Assistant ]
               |
====== TRUST BOUNDARY 1: MCP & HTTP Transport (Bearer Auth, Rate Limiting) ======
               v
   [ ASGI Middleware / MCPServer Pipeline Interceptor ]
               |
====== TRUST BOUNDARY 2: Pipeline Validation (Models, Allowlist, S13 Interception) ======
               v
     [ Parameterized SQL Queries (queries.py) ]
               |
====== TRUST BOUNDARY 3: Read-Only DB Barrier (mode=ro, query_only, Authorizer) ======
               v
      [ SQLite claims.db ]
```

- **Boundary 1 (External Inbound)**: Untrusted AI agents and HTTP clients. Can send arbitrary JSON payloads, malformed arguments, hostile prompt injection strings, and high-frequency request floods.
- **Boundary 2 (Application Pipeline)**: Intercepts raw tool calls before SDK validation. Validates input scalars, enforces per-key tool allowlists, sanitizes text notes, and writes fail-closed audit logs.
- **Boundary 3 (Database Interface)**: SQLite VFS and engine boundary. Enforces three independent layers of write-blocking defense.

---

## 3. STRIDE Threat Analysis

| Threat Category | Threat Description | Mitigation | Verified by Test |
|---|---|---|---|
| **Spoofing** | Attacker calls HTTP endpoints without valid credentials or impersonates legitimate analyst key. | HTTP transport requires `Authorization: Bearer <key>`. Keys stored only as SHA-256 hashes; verified using `hmac.compare_digest` in constant time (S4). Returns HTTP 401 with empty body. | `test_security.py::test_verify_valid_key`<br>`test_security.py::test_verify_invalid_key`<br>`test_server_protocol.py::test_http_401_without_key_or_invalid_key` |
| **Tampering** (Database) | Attacker injects SQL statements (e.g. `DROP TABLE`, `INSERT`) via input parameters. | 1. SQLite URI opened with `mode=ro`<br>2. `PRAGMA query_only = ON`<br>3. SQLite authorizer denies all operations except SELECT, READ, FUNCTION (S1)<br>4. AST scan verifies zero dynamic SQL in `queries.py` (S2, S3). | `test_db_readonly.py::test_insert_fails`<br>`test_db_readonly.py::test_update_fails`<br>`test_db_readonly.py::test_delete_fails`<br>`test_db_readonly.py::test_drop_fails`<br>`test_queries.py::test_no_string_formatting_in_sql_ast`<br>`test_injection.py` (SQL injection cases) |
| **Tampering** (Audit Trail) | Attacker attempts to bypass auditing or suppress audit record creation. | Fail-closed audit design: if `audit.py` fails to write, query data is discarded, no result is returned, and `INTERNAL` error code is emitted (S9). | `test_audit.py::test_fail_closed_on_write_error` |
| **Repudiation** | Caller denies executing a specific claim lookup or abuse attempt. | Every call—including denied, invalid, not-found, and rate-limited—writes a structured JSONL audit entry with UTC timestamp, unique request ID, caller ID, tool name, duration, and error codes (S9, SPEC 10). | `test_audit.py::test_audit_entry_fields`<br>`test_server_protocol.py`<br>`test_injection.py` |
| **Information Disclosure** (Error Echo) | SDK echoes raw invalid inputs (e.g. `DROP TABLE`, prompt injection text) in error responses (SPEC S13). | Subclassed `MCPServer.call_tool` intercepts requests before SDK Pydantic schema validation runs, converting all invalid arguments to safe fixed error codes (S8, S13). | `test_s13_server.py::test_s13_extra_argument`<br>`test_s13_server.py::test_s13_wrongly_typed_argument`<br>`test_server_protocol.py::test_sdk_rejected_calls_safety` |
| **Information Disclosure** (Audit Poisoning) | Attacker injects sensitive or exploit payloads into invalid parameters to pollute audit logs. | Invalid calls log `args: null` and record only `invalid_fields` (parameter names), never raw attacker values (SPEC 10). Note text and query payloads are never logged. | `test_audit.py::test_audit_invalid_fields_only`<br>`test_audit.py::test_no_payload_in_audit_log`<br>`test_s13_server.py` |
| **Information Disclosure** (Stack Leaks) | Internal file paths, database structure, or exception tracebacks leak to client. | All exceptions map strictly to the SPEC 8 error taxonomy (`INTERNAL: reference <request_id>`). Technical details stay in server-side logs. | `test_server_protocol.py`<br>`test_injection.py` |
| **Denial of Service** | Caller floods server with queries to exhaust CPU or SQLite file handles. | Per-key fixed-window rate limiter (default 60 requests/min) with injectable monotonic clock (S6). SQLite opens one read-only connection per call and closes immediately in `finally` (D10). | `test_security.py::test_rate_limiter_blocks_over_limit`<br>`test_injection.py::test_rate_limit_hostile_abuse` |
| **Elevation of Privilege** | Key authorized only for `get_claim` attempts to call other tools. | Server checks key's `allowed_tools` allowlist before executing query; unauthorized calls return `FORBIDDEN_TOOL` and log `outcome="denied"` (S5). | `test_security.py::test_tool_forbidden`<br>`test_server_protocol.py::test_forbidden_tool` |
| **Indirect Prompt Injection** | Hostile instructions embedded in free-text claim notes trick reader AI. | `sanitize_untrusted_text` strips control characters, strips Unicode Cf characters (bidi overrides, zero-width spaces), caps length at 1,000 characters, and always flags payload `untrusted: true` (S7). | `test_security.py::test_sanitize_removes_control_characters`<br>`test_security.py::test_sanitize_removes_unicode_cf`<br>`test_security.py::test_sanitize_caps_at_1000`<br>`test_injection.py::test_adversarial_note_sanitized_and_untrusted_flag` |

---

## 4. Security Requirement to Test Mapping (S1–S13)

| ID | Requirement Statement | Implementing Module | Test Verification File | Specific Test Functions |
|---|---|---|---|---|
| **S1** | SQLite opened `mode=ro`, `PRAGMA query_only=ON`, and read-only authorizer blocking writes, PRAGMA, and ATTACH. | `src/claims_mcp/db.py` | `tests/test_db_readonly.py` | `test_insert_fails`<br>`test_update_fails`<br>`test_delete_fails`<br>`test_drop_fails`<br>`test_create_fails`<br>`test_attach_fails`<br>`test_pragma_fails`<br>`test_select_works`<br>`test_missing_file_raises_and_creates_nothing` |
| **S2** | No tool parameter becomes SQL text, table name, or column name; parameters validated before query. | `src/claims_mcp/models.py`<br>`src/claims_mcp/queries.py` | `tests/test_validation.py`<br>`tests/test_injection.py` | `TestClaimIdValidation`<br>`TestMemberIdValidation`<br>`TestPlanIdValidation`<br>`TestProcedureCodeValidation`<br>`test_hostile_inputs_safe_rejection` |
| **S3** | All SQL in `queries.py` strictly uses `?` placeholders. No f-strings, `.format()`, `%`, or `+` concatenation. | `src/claims_mcp/queries.py` | `tests/test_queries.py` | `test_no_string_formatting_in_sql_ast`<br>`test_all_queries_use_parameter_placeholders` |
| **S4** | HTTP transport requires Bearer key; keys SHA-256 hashed at rest; constant-time comparison. Missing/invalid yields HTTP 401 empty body. | `src/claims_mcp/security.py`<br>`src/claims_mcp/server.py` | `tests/test_security.py`<br>`tests/test_server_protocol.py` | `test_verify_valid_key`<br>`test_verify_invalid_key`<br>`test_verify_missing_key`<br>`test_constant_time_comparison`<br>`test_http_401_without_key_or_invalid_key` |
| **S5** | Per-key tool allowlist; non-permitted tools return `FORBIDDEN_TOOL`. | `src/claims_mcp/security.py`<br>`src/claims_mcp/server.py` | `tests/test_security.py`<br>`tests/test_server_protocol.py` | `test_tool_allowed_all`<br>`test_tool_allowed_specific`<br>`test_tool_forbidden`<br>`test_forbidden_tool` |
| **S6** | Per-key rate limiting (default 60/min) with injectable clock. | `src/claims_mcp/security.py`<br>`src/claims_mcp/server.py` | `tests/test_security.py`<br>`tests/test_injection.py` | `test_rate_limiter_allows_under_limit`<br>`test_rate_limiter_blocks_over_limit`<br>`test_rate_limiter_resets_after_window`<br>`test_rate_limit_hostile_abuse` |
| **S7** | `get_claim_notes` output sanitized (remove control chars, Unicode Cf, cap at 1,000 chars, flag `untrusted: true`). | `src/claims_mcp/security.py`<br>`src/claims_mcp/server.py` | `tests/test_security.py`<br>`tests/test_injection.py` | `test_sanitize_removes_control_characters`<br>`test_sanitize_removes_unicode_cf`<br>`test_sanitize_caps_at_1000`<br>`test_sanitize_preserves_newline_tab`<br>`test_adversarial_note_sanitized_and_untrusted_flag` |
| **S8** | Safe error taxonomy; unexpected exceptions return `INTERNAL: reference <request_id>` with details kept server-side. | `src/claims_mcp/server.py`<br>`src/claims_mcp/models.py` | `tests/test_server_protocol.py`<br>`tests/test_injection.py` | `test_not_found_errors`<br>`test_invalid_input_error`<br>`test_hostile_inputs_safe_rejection` |
| **S9** | Append-only JSONL audit log per call; fail closed (no data returned on audit failure). | `src/claims_mcp/audit.py`<br>`src/claims_mcp/server.py` | `tests/test_audit.py` | `test_audit_entry_fields`<br>`test_audit_invalid_fields_only`<br>`test_fail_closed_on_write_error`<br>`test_no_payload_in_audit_log` |
| **S10** | Config validated at startup; refuse to start on missing DB or invalid keys in HTTP mode. | `src/claims_mcp/config.py`<br>`src/claims_mcp/__main__.py` | `tests/test_config.py` | `test_missing_db_raises`<br>`test_missing_db_env_raises`<br>`test_http_mode_requires_keys_file`<br>`test_http_mode_empty_keys_file`<br>`test_http_mode_missing_keys_file_on_disk` |
| **S11** | No secrets, keys, audit logs, or database files committed to git. | `.gitignore` | `tests/test_smoke.py`<br>`git status` checks | Verified via repository gitignore rules and clean git status checks |
| **S12** | Minimal dependencies locked in `uv.lock`. | `pyproject.toml`<br>`uv.lock` | `pyproject.toml` | Lockfile committed; verified in CI workflow |
| **S13** | No call rejected by SDK before pipeline runs; prevents input echoing and ensures audit on invalid calls. | `src/claims_mcp/server.py` (`ClaimsMCPServer.call_tool`) | `tests/test_s13_server.py`<br>`tests/test_server_protocol.py` | `test_s13_missing_argument`<br>`test_s13_extra_argument`<br>`test_s13_wrongly_typed_argument`<br>`test_sdk_rejected_calls_safety` |

---

## 5. Residual Risks

1. **Semantic Influence of Hostile Notes**: Sanitizing text (removing control characters and bidi overrides) and setting `untrusted: true` informs downstream AI agents that the content is untrusted, but cannot mathematically prevent an LLM from being swayed by clever natural-language social engineering. Primary mitigations must be architectural: read-only database access, absence of write capabilities, and a human-in-the-loop gate before claims adjudication.
2. **Plaintext Transport on Localhost**: The server binds `127.0.0.1` and does not provide TLS termination. If exposed across network boundaries, a TLS reverse proxy (e.g., Nginx, Envoy, or Caddy) must be deployed in front.
3. **Single-Process Rate Limiter**: The fixed-window rate limiter stores timestamps in-memory. In a multi-worker deployment, rate limits would not be shared across processes without an external backend like Redis.
4. **Key Rotation & Audit Storage**: Key addition and rotation require updating `keys.json`. Audit logs are append-only text files on the local filesystem; centralized log shipping with write-once-read-many (WORM) storage is recommended for production enterprise auditing.
