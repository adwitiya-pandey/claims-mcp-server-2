# Meridian Health Claims MCP Server

A secure, read-only Model Context Protocol (MCP) server over a synthetic health-insurance claims database.

[![CI](https://github.com/adwitiya-pandey/claims-mcp-server/actions/workflows/ci.yml/badge.svg)](https://github.com/adwitiya-pandey/claims-mcp-server/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![MCP SDK: v2](https://img.shields.io/badge/MCP%20SDK-2.3.0-green.svg)](https://github.com/modelcontextprotocol/python-sdk)

---

## What and Why (The Client Call)

Meridian Health TPA (fictional) processes approximately 3,000 health insurance claims daily across four commercial insurers and requires AI assistants to help internal teams query claims data. Compliance and security enforce an absolute rule: **no AI assistant ever receives direct SQL or direct database access**, and every interaction must leave an immutable, auditable trail. This server provides the secure Model Context Protocol (MCP) mediation layer exposing five strictly read-only, parameterized tools with defense-in-depth SQLite protection, API key authentication, per-tool authorization, rate limiting, input sanitization, and fail-closed audit logging.

---

## Quickstart

Run these three commands from a clean clone to set up dependencies, generate synthetic data and keys, and launch the server:

```bash
# 1. Install dependencies with uv
uv sync

# 2. Seed deterministic synthetic database and generate an API key
uv run python scripts/seed_db.py --out data/claims.db && uv run python scripts/make_key.py --id analyst-1 --tools all

# 3. Start the MCP server (stdio transport for inspector / local agents)
CLAIMS_DB_PATH=data/claims.db uv run python -m claims_mcp --transport stdio
```

### Running the Live HTTP Demo Client

To test the server over Streamable HTTP with API key authentication, error taxonomy demonstrations, and prompt-injection defense over all 18 seeded adversarial notes:

```bash
# Terminal 1: Launch the HTTP server on port 8765
CLAIMS_DB_PATH=data/claims.db CLAIMS_KEYS_FILE=keys.json uv run python -m claims_mcp --transport http

# Terminal 2: Run the comprehensive live demo client
uv run python scripts/demo_client.py --key <YOUR_GENERATED_RAW_KEY>
```

---

## System Architecture

### Architectural Flowchart

```mermaid
flowchart TB
    Client["MCP Client\n(Claude Desktop / Inspector / AI Agent / demo_client.py)"]
    
    subgraph Transport ["Transport Layer"]
        STDIO["stdio JSON-RPC Transport\n(Local Dev / Inspector)"]
        HTTP["Streamable HTTP Transport (127.0.0.1:8765)\nAuthorization: Bearer <key>"]
    end
    
    subgraph SecurityMiddleware ["Security & Policy Guardrails (T6)"]
        Auth["Bearer Key Verification\n(SHA-256 Hashed, Constant-Time hmac.compare_digest)"]
        RateLimit["Rate Limiter\n(In-Memory Fixed Window: 60 req/min)"]
        Allowlist["Tool Authorization Allowlist\n(Per-Key Tool Restrictions)"]
    end
    
    subgraph S13Pipeline ["Pipeline & Input Interceptor (T8 / S13)"]
        Interceptor["S13 Input Interceptor\n(Pre-SDK CallTool Hook)"]
        Validator["Strict Pydantic Input Validation\n(Regex Patterns, Strict Types, Extra Fields Forbidden)"]
    end
    
    subgraph DatabaseLayer ["Read-Only Database Engine (T4 / T5b)"]
        DBConn["SQLite Connection\n(One Connection Per Call)"]
        Authorizer["Triple-Layer Read Barrier\n1. URI mode=ro\n2. PRAGMA query_only=ON\n3. SQLite Read-Only Authorizer"]
        Queries["Strict Parameterized Queries\n(AST-Enforced ? Placeholders Only)"]
        ClaimsDB[("claims.db\n(Synthetic SQLite Database)")]
    end
    
    subgraph OutputSanitization ["Output Sanitization & Audit (T6 / T7)"]
        Sanitizer["Untrusted Text Sanitizer\n(Strip Control Chars, Unicode Cf, Cap 1000, Flag untrusted: true)"]
        AuditLogger["Fail-Closed Audit Logger\n(Append-Only JSONL + Stderr Log)"]
        AuditFile[("audit/audit.jsonl\n(Fail-Closed JSONL Log)")]
    end
    
    Client --> STDIO
    Client --> HTTP
    HTTP --> Auth
    Auth --> RateLimit
    STDIO --> RateLimit
    RateLimit --> Allowlist
    Allowlist --> Interceptor
    Interceptor --> Validator
    Validator --> DBConn
    DBConn --> Authorizer
    Authorizer --> Queries
    Queries --> ClaimsDB
    ClaimsDB --> Sanitizer
    Sanitizer --> AuditLogger
    AuditLogger --> AuditFile
    AuditLogger --> Client
```

### Complete Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    actor Caller as MCP Client
    participant HTTP as ASGI Middleware
    participant Server as ClaimsMCPServer (Pipeline)
    participant Sec as Security Engine (T6)
    participant DB as SQLite Engine (T4)
    participant Audit as AuditLogger (T7)

    Caller->>HTTP: JSON-RPC tools/call (Bearer Key)
    HTTP->>Sec: Verify Bearer Key Hash (Constant-Time)
    alt Invalid Key
        HTTP-->>Caller: HTTP 401 Unauthorized (Empty Body)
    end
    HTTP->>Server: Forward Request with Caller Context
    
    Server->>Sec: Check Rate Limit (60 req/min)
    alt Rate Limit Exceeded
        Server->>Audit: Log rate_limited outcome
        Server-->>Caller: RATE_LIMITED: try again later (is_error=True)
    end
    
    Server->>Sec: Check Tool Allowlist
    alt Tool Not Permitted
        Server->>Audit: Log denied outcome (FORBIDDEN_TOOL)
        Server-->>Caller: FORBIDDEN_TOOL (is_error=True)
    end
    
    Server->>Server: Validate Input & Check S13
    alt Invalid Input or Extra Parameter
        Server->>Audit: Log invalid outcome (invalid_fields only, args=null)
        Server-->>Caller: INVALID_INPUT: <field> is invalid (is_error=True)
    end
    
    Server->>DB: Open Read-Only Connection (mode=ro, query_only=ON, Authorizer)
    DB->>DB: Execute Fixed SQL Query with ? Parameters
    DB-->>Server: Return Row Data
    Server->>DB: Close Connection
    
    alt Row Not Found
        Server->>Audit: Log not_found outcome
        Server-->>Caller: NOT_FOUND (is_error=True)
    end
    
    opt Tool is get_claim_notes
        Server->>Sec: Sanitize Note Text (Strip Cf, Cap 1000, untrusted: true)
    end
    
    Server->>Audit: Write JSONL Audit Record (ts, request_id, caller, tool, outcome)
    alt Audit Log Write Fails
        Server-->>Caller: INTERNAL: reference <request_id> (Fail Closed)
    else Audit Log Write Succeeds
        Server-->>Caller: CallToolResult JSON Response (is_error=False)
    end
```

---

## Annotated File Structure Tree

```
claims-mcp-server/
│
├── .dockerignore                     # Docker build exclusion rules
├── .env.example                      # Template for environment configuration
├── .gitattributes                    # Line ending LF normalizations
├── .gitignore                        # Git exclusion rules (keys, .env, DBs, logs)
├── .pre-commit-config.yaml           # Pre-commit linting and security hooks
├── .python-version                   # Pinned Python version (3.12)
├── Dockerfile                        # Multi-stage non-root container with health check
├── LICENSE                           # MIT open source license (Adwitiya Pandey)
├── PROGRESS.md                       # Task execution and milestone completion log
├── README.md                         # Enterprise documentation and operational manual
├── SPEC.md                           # Formal scope contract and requirements specification
├── TASKS.md                          # Sequential autonomous implementation task breakdown
├── THREAT_MODEL.md                   # STRIDE threat model and requirement-to-test verification matrix
├── pyproject.toml                    # Package metadata, dependencies, and test configurations
├── schema.sql                        # SQLite DDL schema contract with strict CHECK constraints
├── uv.lock                           # Deterministic cryptographic dependency lockfile
│
├── audit/
│   └── audit.jsonl                   # Append-only fail-closed structured JSONL audit trail
│
├── data/
│   ├── adversarial_note_ids.txt      # Line-delimited IDs of 18 synthetic adversarial test notes
│   └── claims.db                     # Deterministic synthetic claims SQLite database
│
├── docs/
│   ├── EXPLAIN-PLAIN-ENGLISH.md      # Plain-English guide for queries, architecture, and defenses
│   ├── decisions.md                  # Comprehensive architectural decision records (D1–D14)
│   └── mcp_sdk_notes.md              # Verified empirical probe results for MCP Python SDK v2
│
├── scripts/
│   ├── demo_client.py                # Live HTTP client testing all 5 tools and adversarial notes
│   ├── make_key.py                   # Secure CLI generating SHA-256 hashed API keys
│   ├── probe_sdk.py                  # Standalone probe verifying MCP SDK v2 capabilities
│   └── seed_db.py                    # Deterministic synthetic database seeder (Random seed 42)
│
├── src/
│   └── claims_mcp/
│       ├── __init__.py               # Package root exports
│       ├── __main__.py               # CLI entrypoint supporting --transport stdio|http
│       ├── audit.py                  # Fail-closed append-only JSONL & stderr audit logger
│       ├── config.py                 # Startup environment validation (S10)
│       ├── db.py                     # Read-only SQLite connection layer behind authorizer (S1)
│       ├── models.py                 # Pydantic input models, ID regex, and SPEC 8 error taxonomy
│       ├── queries.py                # 5 strictly parameterized SQL queries using ? placeholders
│       ├── security.py               # KeyStore, rate limiting, and untrusted text sanitization (S4-S7)
│       └── server.py                 # MCPServer pipeline, S13 interceptor, and tool registrations
│
└── tests/
    ├── __init__.py                   # Test suite package marker
    ├── fixtures.py                   # Tiny deterministic in-memory fixture database builder
    ├── test_audit.py                 # Tests verifying fail-closed audit logging and payload omission
    ├── test_config.py                # Tests verifying startup configuration refusals (S10)
    ├── test_db_readonly.py           # Tests proving write operations fail against SQLite authorizer (S1)
    ├── test_injection.py             # 40+ parameterized tests verifying hostile abuse rejection
    ├── test_queries.py               # Tests validating query outputs and AST check for ? placeholders
    ├── test_s13_server.py            # Tests verifying pre-SDK input interception and no input echo (S13)
    ├── test_security.py              # Tests verifying constant-time auth, allowlists, and sanitization
    ├── test_seed_fixture.py          # Tests verifying deterministic synthetic DB row counts and CHECKs
    ├── test_server_protocol.py       # Full protocol tests through real MCP Client (tools, errors, HTTP)
    ├── test_smoke.py                 # Basic package import smoke test
    └── test_validation.py            # Comprehensive parameter validation tables for scalars and limits
```

---

## The Five Named Tools

| Tool Name | Parameters | Description |
|---|---|---|
| `get_claim` | `claim_id: str` | Retrieves one claim joined with member plan and provider network status. |
| `list_member_claims` | `member_id: str`<br>`status: str \| None`<br>`limit: int = 20`<br>`offset: int = 0` | Lists claims for a member ordered newest first (`service_date DESC, claim_id DESC`). Returns `NOT_FOUND` if member does not exist. |
| `get_coverage_rule` | `plan_id: str`<br>`procedure_code: str` | Checks coverage status, pre-authorization requirement, and maximum allowable fee. |
| `get_member_ytd_summary` | `member_id: str`<br>`year: int` | Computes year-to-date claim counts, billed/paid totals by status, and remaining plan annual limit. |
| `get_claim_notes` | `claim_id: str`<br>`limit: int = 10` | Returns untrusted notes newest first. Text is stripped of control/bidi characters, capped at 1,000 characters, and flagged `untrusted: true`. |

---

## Security Guarantees & Verification

| Requirement | Defense Implementation | Verification Test File |
|---|---|---|
| **S1: Read-Only Database** | Opened with URI `mode=ro`, `PRAGMA query_only=ON`, and an authorizer denying `INSERT`, `UPDATE`, `DELETE`, `ATTACH`, and `PRAGMA`. | `tests/test_db_readonly.py` |
| **S2/S3: Zero Dynamic SQL** | All queries in `queries.py` use strictly parameterized `?` placeholders. Validated via AST scanner. | `tests/test_queries.py`<br>`tests/test_validation.py` |
| **S4: Hashed Bearer Auth** | HTTP transport enforces Bearer keys stored as SHA-256 hashes and compared in constant time with `hmac.compare_digest`. | `tests/test_security.py`<br>`tests/test_server_protocol.py` |
| **S5: Tool Allowlists** | Per-key `allowed_tools` allowlists enforced before query execution. Unauthorized calls return `FORBIDDEN_TOOL`. | `tests/test_security.py`<br>`tests/test_server_protocol.py` |
| **S6: Rate Limiting** | In-memory fixed window rate limiter (default 60 req/min) with injectable monotonic clock. | `tests/test_security.py`<br>`tests/test_injection.py` |
| **S7: Note Sanitization** | Removes ASCII control characters (except `\n`, `\t`) and Unicode category `Cf` characters. Capped at 1,000 chars. | `tests/test_security.py`<br>`tests/test_injection.py` |
| **S8: Safe Error Taxonomy** | Structured error codes (`RATE_LIMITED`, `FORBIDDEN_TOOL`, `INVALID_INPUT`, `NOT_FOUND`, `INTERNAL`) never leak internals or echo raw input. | `tests/test_server_protocol.py`<br>`tests/test_injection.py` |
| **S9: Fail-Closed Audit** | Every call writes one JSONL record. If the audit log fails to write, query data is suppressed and `INTERNAL` is returned. | `tests/test_audit.py` |
| **S10: Startup Validation** | Server refuses to start on missing SQLite database or unconfigured/empty API keys file in HTTP mode. | `tests/test_config.py` |
| **S13: Pre-SDK Interception** | Intercepts requests before SDK argument parsing, preventing raw attacker payloads from echoing in error responses. | `tests/test_s13_server.py`<br>`tests/test_server_protocol.py` |

Full STRIDE threat model, trust boundary maps, and residual risk analyses are detailed in [THREAT_MODEL.md](THREAT_MODEL.md).

---

## Documented Limitations (SPEC 15)

1. **Prompt Injection Boundary**: Sanitizing text and setting `"untrusted": true` informs consuming AI agents that data is untrusted, but cannot mathematically prevent an LLM from obeying prompt injection. Complete mitigation relies on architectural isolation: read-only database connections, absence of write tools, and human review gates.
2. **Localhost Transport**: The HTTP server binds `127.0.0.1` and provides no native TLS termination; an external reverse proxy (Nginx, Envoy, or Caddy) must terminate TLS in production.
3. **Single-Process Rate Limiter**: Rate limits are tracked in memory per process; clustered deployments require external state backends (e.g. Redis).
4. **Key Management**: API key creation and revocation are file-based (`keys.json`).
5. **Audit Tamper-Resistance**: Audit records are stored as append-only JSONL files without cryptographic forward secrecy.
